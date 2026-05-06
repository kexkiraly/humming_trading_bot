# ============================================================
# mtf_analyzer.py – Multi-Timeframe Elemzés
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta
from config import SHORT_MA, LONG_MA

logger = logging.getLogger(__name__)

# Vizsgált időkeretek és súlyuk
TIMEFRAMES = {
    "1m":  1,   # 1 perces  – legkisebb súly
    "15m": 2,   # 15 perces – közepes súly
    "1h":  3,   # 1 órás    – nagy súly
    "4h":  4,   # 4 órás    – legnagyobb súly
}

# Minimum egyező időkeretek a kereskedéshez
MIN_TF_AGREEMENT = 3   # legalább 3/4 időkeret kell


def analyze_timeframe(exchange, symbol: str,
                      timeframe: str, limit: int = 60) -> dict:
    """
    Elemez egy adott időkeretet.
    Visszaad egy dict-et a trend irányával és jelzésekkel.
    """
    try:
        ohlcv = exchange.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 30:
            return {"trend": "neutral", "score": 0, "timeframe": timeframe}

        closes  = [c[4] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]
        price   = closes[-1]

        closes_series = pd.Series(closes)

        # --- Mozgóátlagok ---
        ma_short = sum(closes[-SHORT_MA:]) / SHORT_MA
        ma_long  = sum(closes[-LONG_MA:]) / LONG_MA

        # --- RSI ---
        rsi_series = ta.rsi(closes_series, length=14)
        rsi        = rsi_series.iloc[-1] if not rsi_series.empty else 50

        # --- MACD ---
        macd_df    = ta.macd(closes_series)
        macd_line  = macd_df["MACD_12_26_9"].iloc[-1]
        signal_line = macd_df["MACDs_12_26_9"].iloc[-1]

        # --- Bollinger Bands ---
        bb_df      = ta.bbands(closes_series, length=20)
        bb_upper_c = [c for c in bb_df.columns if c.startswith("BBU")][0]
        bb_lower_c = [c for c in bb_df.columns if c.startswith("BBL")][0]
        bb_upper   = bb_df[bb_upper_c].iloc[-1]
        bb_lower   = bb_df[bb_lower_c].iloc[-1]

        # --- Volume ---
        vol_series = pd.Series(volumes)
        avg_vol    = vol_series.rolling(20).mean().iloc[-1]
        vol_ratio  = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

        # --- Pontszám számítás ---
        buy_score  = 0
        sell_score = 0

        if ma_short > ma_long:
            buy_score  += 1
        else:
            sell_score += 1

        if rsi < 40:
            buy_score  += 1
        elif rsi > 60:
            sell_score += 1

        if macd_line > signal_line:
            buy_score  += 1
        elif macd_line < signal_line:
            sell_score += 1

        if price < bb_lower:
            buy_score  += 1
        elif price > bb_upper:
            sell_score += 1

        # Volume bónusz
        if vol_ratio > 1.5:
            if buy_score > sell_score:
                buy_score  += 0.5
            else:
                sell_score += 0.5

        # Trend meghatározása
        if buy_score > sell_score:
            trend = "bullish"
            score = buy_score
        elif sell_score > buy_score:
            trend = "bearish"
            score = -sell_score
        else:
            trend = "neutral"
            score = 0

        logger.debug(
            f"  {timeframe:<4} | {symbol} | "
            f"{'🟢' if trend == 'bullish' else '🔴' if trend == 'bearish' else '⚪'} "
            f"{trend:<8} | Score: {score:+.1f} | "
            f"RSI: {rsi:.1f}"
        )

        return {
            "timeframe":   timeframe,
            "trend":       trend,
            "score":       score,
            "buy_score":   buy_score,
            "sell_score":  sell_score,
            "rsi":         rsi,
            "macd":        macd_line,
            "vol_ratio":   vol_ratio,
            "price":       price,
        }

    except Exception as e:
        logger.error(f"MTF hiba ({timeframe}): {e}")
        return {"trend": "neutral", "score": 0, "timeframe": timeframe}


class MTFAnalyzer:
    """
    Multi-Timeframe Analyzer – 4 időkeret egyidejű elemzése.
    """

    def __init__(self, exchange):
        self.exchange = exchange
        logger.info(
            f"📊 MTF Analyzer inicializálva – "
            f"{len(TIMEFRAMES)} időkeret: "
            f"{', '.join(TIMEFRAMES.keys())}"
        )

    def analyze(self, symbol: str) -> dict:
        """
        Elemzi a symbolt mind a 4 időkereten.
        Visszaad egy összesített döntést.
        """
        results     = {}
        total_score = 0
        weighted_score = 0
        total_weight   = sum(TIMEFRAMES.values())

        logger.info(f"📊 MTF elemzés: {symbol}")

        for tf, weight in TIMEFRAMES.items():
            result = analyze_timeframe(self.exchange, symbol, tf)
            results[tf] = result

            # Súlyozott pontszám
            weighted_score += result["score"] * weight

        # Normalizált súlyozott pontszám
        normalized_score = weighted_score / total_weight

        # Hány időkeret bullish/bearish?
        bullish_tfs = sum(
            1 for r in results.values() if r["trend"] == "bullish"
        )
        bearish_tfs = sum(
            1 for r in results.values() if r["trend"] == "bearish"
        )

        # Végső döntés
        if bullish_tfs >= MIN_TF_AGREEMENT:
            decision = "buy"
            strength = bullish_tfs / len(TIMEFRAMES)
        elif bearish_tfs >= MIN_TF_AGREEMENT:
            decision = "sell"
            strength = bearish_tfs / len(TIMEFRAMES)
        else:
            decision = "wait"
            strength = 0.0

        # Nagy időkeret (4h) irány – ez a legfontosabb
        htf_trend = results.get("4h", {}).get("trend", "neutral")

        logger.info(
            f"📊 MTF összesítés: {symbol} | "
            f"{'🟢' if decision == 'buy' else '🔴' if decision == 'sell' else '⚪'} "
            f"{decision.upper()} | "
            f"Bullish TF: {bullish_tfs}/4 | "
            f"Bearish TF: {bearish_tfs}/4 | "
            f"4h trend: {htf_trend} | "
            f"Súlyozott: {normalized_score:+.2f}"
        )

        return {
            "symbol":          symbol,
            "decision":        decision,
            "strength":        strength,
            "bullish_tfs":     bullish_tfs,
            "bearish_tfs":     bearish_tfs,
            "weighted_score":  normalized_score,
            "htf_trend":       htf_trend,
            "timeframes":      results,
        }

    def is_aligned_for_buy(self, symbol: str) -> tuple:
        """
        Gyors ellenőrzés: vételi jel van-e?
        Visszaad: (bool, strength, details)
        """
        result = self.analyze(symbol)
        is_buy = (
            result["decision"] == "buy" and
            result["htf_trend"] != "bearish"  # 4h ne legyen bearish!
        )
        return is_buy, result["strength"], result

    def is_aligned_for_sell(self, symbol: str) -> tuple:
        """
        Gyors ellenőrzés: eladási jel van-e?
        """
        result = self.analyze(symbol)
        is_sell = result["decision"] == "sell"
        return is_sell, result["strength"], result