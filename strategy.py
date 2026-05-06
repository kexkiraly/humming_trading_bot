# ============================================================
# strategy.py – Multi-coin szavazós stratégia védelemmel
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta

from config import TRADING_PAIRS, ORDER_SIZE, SHORT_MA, LONG_MA, STOP_LOSS, TAKE_PROFIT
from notifier import send_message
from indicators import get_fear_and_greed, get_enhanced_sentiment, get_market_alerts, get_onchain_data
from database import save_trade
from ml_model import load_or_train_model, predict, retrain_periodically
from guard import GuardSystem
from portfolio import PortfolioManager
from mtf_analyzer import MTFAnalyzer
from dashboard import live_data
from coin_scanner import scan_all_coins, get_best_buy_opportunity, get_sell_signal
from orderbook import analyze_orderbook
from sentiment_aggregator import SentimentAggregator
from market_regime import RegimeDetector
from risk_manager import (
    calculate_atr, get_dynamic_stop_loss,
    get_dynamic_take_profit, get_atr_position_size,
    TrailingStopManager
)

logger = logging.getLogger(__name__)

EXTERNAL_DATA_INTERVAL = 120
MIN_VOTES = 3


class SimpleStrategy:
    def __init__(self, exchange):
        self.exchange         = exchange
        self.is_position_open = False
        self.entry_price      = None
        self.current_symbol   = None
        self.loop_counter     = 0
        self.trade_count      = 0
        self._last_rsi        = 50.0
        self._last_macd       = 0.0

        # Külső adatok cache
        self.fear_greed = {"value": 50, "label": "Neutral"}
        self.sentiment  = {"bullish": 0, "bearish": 0, "score": 0}
        self.onchain    = {"signal": "neutral", "score": 0}

        # ML modell és védelmi rendszer
        self.ml_model, self.ml_scaler = load_or_train_model()
        self.guard     = GuardSystem()
        self.portfolio = PortfolioManager()
        self.mtf       = MTFAnalyzer(self.exchange)
        self.sentiment_agg = SentimentAggregator()
        self.trailing_stop = TrailingStopManager()
        self.regime_detector = RegimeDetector()
        self.atr_stops     = {}  # {"BTC/USDT": {"sl": 77000, "tp": 80000}}

        logger.info(f"✅ Stratégia inicializálva – {len(TRADING_PAIRS)} coin figyelve.")

    def update_external_data(self):
        """Külső adatok frissítése ritkábban."""
        self.fear_greed = get_fear_and_greed()
        self.sentiment  = get_enhanced_sentiment()
        self.onchain    = get_onchain_data()

        alerts = get_market_alerts()
        for alert in alerts:
            if alert.get("severity") == "magas":
                send_message(
                    f"🚨 <b>PIACI RIASZTÁS!</b>\n"
                    f"Típus: {alert.get('type')}\n"
                    f"Üzenet: {alert.get('message')}"
                )

    def run(self):
        self.loop_counter += 1

        if self.loop_counter % EXTERNAL_DATA_INTERVAL == 1:
            self.update_external_data()

        try:
            fg_value   = self.fear_greed["value"]
            news_score = self.sentiment.get("score", 0)
            mtf_result = {}
            agg_result = {} # Inicializálás a dashboardhoz

            # --- Az összes coin elemzése ---
            scan_results = scan_all_coins(
                self.exchange, TRADING_PAIRS,
                SHORT_MA, LONG_MA,
                fg_value, news_score,
                onchain_signal=self.onchain.get("signal", "neutral")
            )

            if not scan_results:
                logger.warning("Nem érkezett adat egyetlen coinról sem.")
                return
            # --- Piaci rezsim felismerés ---
            regime = self.regime_detector.get_regime(
                self.exchange, "BTC/USDT"
            )
            regime_name   = regime.get("regime", "unknown")
            regime_config = regime.get("config", {})

            # Extrém volatilis piacban ne kereskedj
            if not self.regime_detector.should_trade():
                logger.warning(
                    f"⚡ Kereskedés szünetel: {regime['description']}"
                )
                return

            # Dinamikus min_votes a rezsim alapján
            dynamic_min_votes = self.regime_detector.get_min_votes()

            # --- Ha NINCS nyitott pozíció (Vételi keresés) ---
            if not self.is_position_open:
                best = get_best_buy_opportunity(
                    scan_results, dynamic_min_votes
                )

                if best:
                    symbol    = best["symbol"]
                    price     = best["price"]
                    buy_votes = best["buy_votes"]
                    rsi       = best["rsi"]
                    macd      = best["macd"]

                    self._last_rsi  = rsi
                    self._last_macd = macd

                    # 1. MTF szűrő
                    mtf_ok, mtf_strength, mtf_result = self.mtf.is_aligned_for_buy(symbol)

                    if not mtf_ok:
                        logger.info(
                            f"📊 MTF blokkolta: {symbol} | "
                            f"Bullish TF: {mtf_result.get('bullish_tfs', 0)}/4 | "
                            f"Minta jel: {best.get('pattern_signal', 'neutral')}"
                        )
                    else:
                        # 2. Sentiment aggregátor
                        agg_result = self.sentiment_agg.aggregate(
                            fear_greed_value = fg_value,
                            news_score       = news_score,
                            onchain_score    = self.onchain.get("score", 0),
                            ob_bid_ask_ratio = best.get("ob_ratio", 1.0),
                            ob_ofi           = best.get("ob_ofi", 0.0),
                        )

                        # Ha az aggregált sentiment bearish → ne vegyen
                        if agg_result["signal"] == "bearish" and agg_result["confidence"] > 60:
                            logger.info(
                                f"📡 Sentiment blokkolta: {symbol} | "
                                f"Bearish {agg_result['confidence']:.0f}% konfidenciával"
                            )
                        else:
                            # 3. Orderbook + ML szűrő
                            ob_data = analyze_orderbook(self.exchange, symbol)
                            should_trade, confidence = predict(
                                self.ml_model, self.ml_scaler,
                                rsi, macd, fg_value, buy_votes,
                                ob_ratio=ob_data.get("bid_ask_ratio", 1.0),
                                ofi=ob_data.get("ofi", 0.0)
                            )

                            if not self.guard.check("buy", symbol, confidence):
                                pass
                            elif should_trade:
                                self.buy(symbol, price, buy_votes, confidence)
                            else:
                                logger.info(
                                    f"🤖 ML blokkolta: {symbol} "
                                    f"(bizalom: {confidence:.1f}% < 60%)"
                                )

            # --- Ha VAN nyitott pozíció (Eladási keresés) ---
            else:
                sell_signal = get_sell_signal(
                    scan_results, self.current_symbol, dynamic_min_votes
                )
                mtf_sell, _, mtf_result = self.mtf.is_aligned_for_sell(self.current_symbol)

                current_data = next(
                    (c for c in scan_results if c["symbol"] == self.current_symbol),
                    None
                )

                if current_data:
                    current_price = current_data["price"]
                    change = (
                        (current_price - self.entry_price) / self.entry_price
                        if self.entry_price else 0
                    )

                    # Normál eladási jelzés (MTF + Technikai szavazat)
                    if sell_signal and mtf_sell:
                        if self.guard.check("sell", self.current_symbol, profit_pct=change * 100):
                            self.sell(self.current_symbol, current_price, sell_signal["sell_votes"])
                            return

                    # --- ATR Stop-loss ---
                    atr_stop = self.atr_stops.get(
                        self.current_symbol, {}
                    )
                    if atr_stop and current_price <= atr_stop["sl"]:
                        logger.warning(
                            f"🛡️  ATR Stop-loss! "
                            f"{self.current_symbol} @ ${current_price:.2f} "
                            f"(SL: ${atr_stop['sl']:.2f})"
                        )
                        self._execute_stop(
                            self.current_symbol,
                            current_price, "ATR Stop-loss"
                        )
                        return

                    # --- ATR Take-profit ---
                    if atr_stop and current_price >= atr_stop["tp"]:
                        logger.info(
                            f"🎯 ATR Take-profit! "
                            f"{self.current_symbol} @ ${current_price:.2f} "
                            f"(TP: ${atr_stop['tp']:.2f})"
                        )
                        self._execute_stop(
                            self.current_symbol,
                            current_price, "ATR Take-profit"
                        )
                        return

                    # --- Trailing Stop ---
                    ts_result = self.trailing_stop.update(
                        self.current_symbol, current_price
                    )
                    if ts_result.get("triggered"):
                        logger.warning(
                            f"🔄 Trailing stop! "
                            f"{self.current_symbol} | "
                            f"Csúcs: ${ts_result['peak']:.2f} | "
                            f"Stop: ${ts_result['stop_price']:.2f}"
                        )
                        self._execute_stop(
                            self.current_symbol,
                            ts_result["stop_price"],
                            "Trailing Stop"
                        )
                        return
                    # Stop-loss védelem
                    elif change <= -STOP_LOSS:
                        logger.warning(f"🛑 Stop-loss! {self.current_symbol} ({change:.2%})")
                        self.guard.register_loss(change * 100)
                        self.exchange.place_order(self.current_symbol, "sell", ORDER_SIZE)
                        send_message(
                            f"🛑 <b>STOP-LOSS!</b>\n"
                            f"Pár: {self.current_symbol}\n"
                            f"Veszteség: {change:.2%}"
                        )
                        save_trade(
                            symbol=self.current_symbol, side="sell",
                            price=current_price, amount=ORDER_SIZE,
                            entry_price=self.entry_price, profit_pct=change * 100
                        )
                        self.portfolio.close_position(self.current_symbol, current_price)
                        self.trailing_stop.deactivate(self.current_symbol)  # ← új sor
                        if self.current_symbol in self.atr_stops:            # ← új sor
                            del self.atr_stops[self.current_symbol]           # ← új sor
                        self.is_position_open = False
                        self.entry_price      = None
                        self.current_symbol   = None

                    # Take-profit védelem
                    elif change >= TAKE_PROFIT:
                        logger.info(f"🎯 Take-profit! {self.current_symbol} ({change:.2%})")
                        self.exchange.place_order(self.current_symbol, "sell", ORDER_SIZE)
                        send_message(
                            f"🎯 <b>TAKE-PROFIT!</b>\n"
                            f"Pár: {self.current_symbol}\n"
                            f"Nyereség: {change:.2%}"
                        )
                        save_trade(
                            symbol=self.current_symbol, side="sell",
                            price=current_price, amount=ORDER_SIZE,
                            entry_price=self.entry_price, profit_pct=change * 100
                        )
                        self.portfolio.close_position(self.current_symbol, current_price)
                        self.trailing_stop.deactivate(self.current_symbol)  # ← új sor
                        if self.current_symbol in self.atr_stops:            # ← új sor
                            del self.atr_stops[self.current_symbol]           # ← új sor
                        self.is_position_open = False
                        self.entry_price      = None
                        self.current_symbol   = None

            # --- Dashboard frissítése ---
            best_coin    = scan_results[0] if scan_results else {}
            guard_status = self.guard.get_status()

            sim_stats = {}
            if hasattr(self.exchange, "simulator") and self.exchange.simulator:
                sim_stats = self.exchange.simulator.get_stats()

            live_data.update({
                "price":           best_coin.get("price", 0),
                "rsi":             best_coin.get("rsi", 0),
                "macd":            best_coin.get("macd", 0),
                "volume_ratio":    best_coin.get("volume_ratio", 0),
                "fg_value":        fg_value,
                "fg_label":        self.fear_greed.get("label", ""),
                "buy_votes":       best_coin.get("buy_votes", 0),
                "sell_votes":      best_coin.get("sell_votes", 0),
                "in_position":     self.is_position_open,
                "entry_price":     self.entry_price or 0.0,
                "current_symbol":  self.current_symbol or "—",
                "status":          "Fut ✅",
                "kill_switch":     guard_status["kill_switch"],
                "circuit_breaker": guard_status["circuit_breaker"],
                "daily_trades":    guard_status["daily_trades"],
                "daily_loss":      guard_status["daily_loss"],
                "top_coins":       scan_results[:5],
                "sim_portfolio":   sim_stats.get("portfolio_value", 10000.0),
                "sim_return":      sim_stats.get("total_return_pct", 0.0),
                "portfolio_status": self.portfolio.get_status(),
                "mtf_bullish_tfs": mtf_result.get("bullish_tfs", 0),
                "mtf_decision":    mtf_result.get("decision", "wait"),
                "sentiment_signal": agg_result.get("signal", "neutral"),
                "sentiment_score":  agg_result.get("weighted_score", 0),
                "regime":          regime_name,
                "regime_desc":     regime.get("description", ""),
                "adx":             regime.get("adx", 0),
            })

        except Exception as e:
            logger.error(f"Hiba a stratégiában: {e}", exc_info=True)

    def buy(self, symbol, price, votes, confidence=50.0):
        logger.info(
            f"🟢 Vétel: {symbol} @ {price:.4f} "
            f"({votes}/8 | ML: {confidence:.1f}%)"
        )
        # ATR alapú pozícióméret és stop-loss
        ohlcv = self.exchange.get_ohlcv(symbol, timeframe="1h", limit=20)
        atr   = calculate_atr(ohlcv)

        # ATR alapú pozícióméret
        free_capital = self.portfolio.free_capital
        if atr > 0:
            amount = get_atr_position_size(free_capital, price, atr)
        else:
            amount = self.portfolio.get_position_size(
                symbol, price, votes, confidence
            )
        order = self.exchange.place_order(symbol, "buy", amount)
        if order:
            self.is_position_open = True
            self.entry_price      = price
            self.current_symbol   = symbol
            self.portfolio.open_position(symbol, price, amount)
            # ATR stop-loss és take-profit beállítása
            sl_price = get_dynamic_stop_loss(price, atr)
            tp_price = get_dynamic_take_profit(price, atr)
            self.atr_stops[symbol] = {
                "sl": sl_price,
                "tp": tp_price,
                "atr": atr,
            }
            # Trailing stop aktiválása
            self.trailing_stop.activate(symbol, price, atr)
            save_trade(
                symbol=symbol, side="buy",
                price=price, amount=amount,
                votes=votes,
                rsi=self._last_rsi,
                macd=self._last_macd,
                fg_value=self.fear_greed.get("value"),
            )
            send_message(
                f"🟢 <b>VÉTEL</b>\n"
                f"Pár: {symbol}\n"
                f"Ár: {price:.4f} USDT\n"
                f"Szavazatok: {votes}/8\n"
                f"ML bizalom: {confidence:.1f}%"
            )
            new_model, new_scaler = retrain_periodically(self.trade_count)
            if new_model:
                self.ml_model  = new_model
                self.ml_scaler = new_scaler

    def _execute_stop(self, symbol: str, price: float, reason: str):
        """Stop-loss vagy take-profit végrehajtása."""
        amount = self.portfolio.positions.get(
            symbol, {}
        ).get("amount", 0.001)

        order = self.exchange.place_order(symbol, "sell", amount)
        if order:
            profit = (
                (price - self.entry_price) / self.entry_price * 100
                if self.entry_price else 0
            )
            if profit < 0:
                self.guard.register_loss(profit)

            self.portfolio.close_position(symbol, price)
            self.trailing_stop.deactivate(symbol)
            if symbol in self.atr_stops:
                del self.atr_stops[symbol]

            save_trade(
                symbol=symbol, side="sell",
                price=price, amount=amount,
                entry_price=self.entry_price,
                profit_pct=profit,
            )
            send_message(
                f"{'🛡️' if profit < 0 else '🎯'} "
                f"<b>{reason}</b>\n"
                f"Pár: {symbol}\n"
                f"Ár: ${price:.2f}\n"
                f"Eredmény: {profit:+.2f}%"
            )
            self.is_position_open = False
            self.entry_price      = None
            self.current_symbol   = None
    def sell(self, symbol, price, votes):
        logger.info(f"🔴 Eladás: {symbol} @ {price:.4f} ({votes}/8)")
        amount = self.portfolio.positions.get(
            symbol, {}
        ).get("amount", ORDER_SIZE)
        order = self.exchange.place_order(symbol, "sell", amount)
        if order:
            profit = (
                (price - self.entry_price) / self.entry_price * 100
                if self.entry_price else 0
            )
            if profit < 0:
                self.guard.register_loss(profit)

            self.portfolio.close_position(symbol, price)
            self.trailing_stop.deactivate(symbol)
            if symbol in self.atr_stops:
                del self.atr_stops[symbol]
            save_trade(
                symbol=symbol, side="sell",
                price=price, amount=amount,
                votes=votes,
                rsi=self._last_rsi,
                macd=self._last_macd,
                fg_value=self.fear_greed.get("value"),
                entry_price=self.entry_price,
                profit_pct=profit,
            )
            send_message(
                f"🔴 <b>ELADÁS</b>\n"
                f"Pár: {symbol}\n"
                f"Ár: {price:.4f} USDT\n"
                f"Eredmény: {profit:+.2f}%\n"
                f"Szavazatok: {votes}/8"
            )
            self.is_position_open = False
            self.entry_price      = None
            self.current_symbol   = None
            self.trade_count     += 1