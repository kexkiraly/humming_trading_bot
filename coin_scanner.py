# ============================================================
# coin_scanner.py – Top 10 coin párhuzamos elemzése
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta
from orderbook import analyze_orderbook
from pattern_detector import get_pattern_signal

logger = logging.getLogger(__name__)


def moving_average(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def analyze_coin(exchange, symbol, short_ma_period, long_ma_period,
                 fear_greed_value, news_score, onchain_signal="neutral") -> dict:
    """
    Elemez egy adott coint és visszaadja az összes indikátort + szavazatot.
    Visszatér None-nal ha nincs elég adat.
    """
    try:
        # Adatok lekérése
        ohlcv = exchange.get_ohlcv(symbol, timeframe="1m", limit=50)
        if not ohlcv or len(ohlcv) < 30:
            return None

        closes  = [c[4] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]
        current_price = closes[-1]

        closes_series  = pd.Series(closes)
        volumes_series = pd.Series(volumes)

        # --- Indikátorok ---
        short_ma = moving_average(closes, short_ma_period)
        long_ma  = moving_average(closes, long_ma_period)

        rsi_series  = ta.rsi(closes_series, length=14)
        rsi         = rsi_series.iloc[-1]

        macd_df     = ta.macd(closes_series)
        macd_line   = macd_df["MACD_12_26_9"].iloc[-1]
        signal_line = macd_df["MACDs_12_26_9"].iloc[-1]

        bbands_df    = ta.bbands(closes_series, length=20)
        bb_col_upper = [c for c in bbands_df.columns if c.startswith("BBU")][0]
        bb_col_lower = [c for c in bbands_df.columns if c.startswith("BBL")][0]
        bb_upper     = bbands_df[bb_col_upper].iloc[-1]
        bb_lower     = bbands_df[bb_col_lower].iloc[-1]

        avg_volume   = volumes_series.rolling(window=20).mean().iloc[-1]
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0

        # --- Szavazás ---
        buy_votes  = 0
        sell_votes = 0

        if short_ma and long_ma:
            if short_ma > long_ma:
                buy_votes  += 1
            else:
                sell_votes += 1

        if rsi < 40:
            buy_votes  += 1
        elif rsi > 60:
            sell_votes += 1

        if macd_line > signal_line:
            buy_votes  += 1
        elif macd_line < signal_line:
            sell_votes += 1

        if current_price < bb_lower:
            buy_votes  += 1
        elif current_price > bb_upper:
            sell_votes += 1

        if fear_greed_value < 35:
            buy_votes  += 1
        elif fear_greed_value > 65:
            sell_votes += 1

        if news_score > 5:
            buy_votes  += 1
        elif news_score < -5:
            sell_votes += 1
            # Minta felismerés
        pattern_result = get_pattern_signal(ohlcv)
        if pattern_result["signal"] == "bullish":
            buy_votes  += 1
        elif pattern_result["signal"] == "bearish":
            sell_votes += 1
            # Orderbook elemzés
        ob_result = analyze_orderbook(exchange, symbol)
        if ob_result["signal"] == "bullish":
            buy_votes  += 1
        elif ob_result["signal"] == "bearish":
            sell_votes += 1
            # On-chain szavazat (paraméterként érkezik)
        if onchain_signal == "bullish":
            buy_votes  += 1
        elif onchain_signal == "bearish":
            sell_votes += 1

        # --- Pontszám: vétel - eladás + volume bónusz ---
        score = buy_votes - sell_votes
        # OFI bónusz
        if ob_result.get("ofi", 0) > 0.3:
            score += 0.5
        if volume_ratio > 1.5:
            score += 0.5  # nagy forgalom esetén bónusz

        # Minták nevei ha vannak
        pattern_names = ", ".join(
            [p["name"] for p in pattern_result.get("all_patterns", [])]
        ) if pattern_result.get("all_patterns") else "—"

        logger.info(
            f"  {symbol:<12} | Ár: {current_price:>10.4f} | "
            f"RSI: {rsi:>5.1f} | "
            f"🟢 {buy_votes}/8 🔴 {sell_votes}/8 | "
            f"Score: {score:>+.1f} | "
            f"Minták: {pattern_names}"
        )

        return {
            "symbol":        symbol,
            "price":         current_price,
            "rsi":           rsi,
            "macd":          macd_line,
            "volume_ratio":  volume_ratio,
            "buy_votes":     buy_votes,
            "sell_votes":    sell_votes,
            "score":         score,
            "short_ma":      short_ma,
            "long_ma":       long_ma,
            "ob_ratio":      ob_result.get("bid_ask_ratio", 1.0),
            "ob_ofi":        ob_result.get("ofi", 0.0),
            "ob_signal":     ob_result.get("signal", "neutral"),
            "patterns":       pattern_result.get("all_patterns", []),
            "pattern_signal": pattern_result.get("signal", "neutral")
        }

    except Exception as e:
        logger.error(f"  {symbol} elemzési hiba: {e}")
        return None


def scan_all_coins(exchange, trading_pairs, short_ma, long_ma,
                   fear_greed_value, news_score,
                   onchain_signal="neutral") -> list:
    """
    Megvizsgálja az összes coint és visszaadja
    score szerint csökkenő sorrendben.
    """
    logger.info(f"🔍 Coin scanner indul – {len(trading_pairs)} pár elemzése...")
    results = []

    for symbol in trading_pairs:
        result = analyze_coin(
            exchange, symbol, short_ma, long_ma,
            fear_greed_value, news_score,
            onchain_signal=onchain_signal
        )
        if result:
            results.append(result)

    # Score szerint rendezés (legjobb elöl)
    results.sort(key=lambda x: x["score"], reverse=True)

    if results:
        best = results[0]
        logger.info(
            f"🏆 Legjobb lehetőség: {best['symbol']} "
            f"(Score: {best['score']:+.1f} | "
            f"Vétel: {best['buy_votes']}/6)"
        )

    return results


def get_best_buy_opportunity(results: list, min_votes: int = 4) -> dict | None:
    """
    Visszaadja a legjobb vételi lehetőséget ha van.
    Feltétel: legalább min_votes vételi szavazat.
    """
    for coin in results:
        if coin["buy_votes"] >= min_votes:
            return coin
    return None


def get_sell_signal(results: list, symbol: str,
                    min_votes: int = 4) -> dict | None:
    """
    Megnézi, hogy az aktuálisan tartott coinra van-e eladási jel.
    """
    for coin in results:
        if coin["symbol"] == symbol:
            if coin["sell_votes"] >= min_votes:
                return coin
    return None