# ============================================================
# pattern_detector.py – Gyertya és Chart minta felismerés
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# GYERTYA MINTÁK (Candlestick Patterns)
# ============================================================

def detect_candlestick_patterns(ohlcv: list) -> dict:
    """
    Felismeri a legfontosabb gyertya mintákat.
    Visszaad egy dict-et a talált mintákkal és a jelzéssel.
    """
    if len(ohlcv) < 5:
        return {"signal": "neutral", "patterns": [], "score": 0}

    # DataFrame készítése
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    patterns_found = []
    buy_score      = 0
    sell_score     = 0

    # Utolsó 3 gyertya
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    last = -1   # legutolsó gyertya indexe

    # --- Hammer (bullish) ---
    # Kis test, hosszú alsó kanóc, minimális felső kanóc
    body      = abs(c[last] - o[last])
    lower_wick = min(c[last], o[last]) - l[last]
    upper_wick = h[last] - max(c[last], o[last])
    total_range = h[last] - l[last]

    if total_range > 0:
        if (lower_wick >= 2 * body and
                upper_wick <= 0.1 * total_range and
                body > 0):
            patterns_found.append({
                "name": "Hammer",
                "type": "bullish",
                "strength": "közepes",
            })
            buy_score += 2

    # --- Shooting Star (bearish) ---
    if total_range > 0:
        if (upper_wick >= 2 * body and
                lower_wick <= 0.1 * total_range and
                body > 0):
            patterns_found.append({
                "name": "Shooting Star",
                "type": "bearish",
                "strength": "közepes",
            })
            sell_score += 2

    # --- Doji (bizonytalanság) ---
    if total_range > 0 and body <= 0.05 * total_range:
        patterns_found.append({
            "name": "Doji",
            "type": "neutral",
            "strength": "gyenge",
        })

    # --- Bullish Engulfing ---
    if len(ohlcv) >= 2:
        prev_body = abs(c[-2] - o[-2])
        curr_body = abs(c[last] - o[last])
        if (c[-2] < o[-2] and       # előző bearish
                c[last] > o[last] and   # jelenlegi bullish
                o[last] < c[-2] and     # jelenlegi nyitó alacsonyabb
                c[last] > o[-2] and     # jelenlegi záró magasabb
                curr_body > prev_body):
            patterns_found.append({
                "name": "Bullish Engulfing",
                "type": "bullish",
                "strength": "erős",
            })
            buy_score += 3

    # --- Bearish Engulfing ---
    if len(ohlcv) >= 2:
        if (c[-2] > o[-2] and       # előző bullish
                c[last] < o[last] and   # jelenlegi bearish
                o[last] > c[-2] and     # jelenlegi nyitó magasabb
                c[last] < o[-2]):       # jelenlegi záró alacsonyabb
            patterns_found.append({
                "name": "Bearish Engulfing",
                "type": "bearish",
                "strength": "erős",
            })
            sell_score += 3

    # --- Morning Star (3 gyertya, bullish) ---
    if len(ohlcv) >= 3:
        if (c[-3] < o[-3] and                    # 1. bearish
                abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3 and  # 2. kis test (doji-szerű)
                c[last] > o[last] and              # 3. bullish
                c[last] > (o[-3] + c[-3]) / 2):   # 3. záró az 1. közepénél magasabb
            patterns_found.append({
                "name": "Morning Star",
                "type": "bullish",
                "strength": "erős",
            })
            buy_score += 3

    # --- Evening Star (3 gyertya, bearish) ---
    if len(ohlcv) >= 3:
        if (c[-3] > o[-3] and                    # 1. bullish
                abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3 and  # 2. kis test
                c[last] < o[last] and              # 3. bearish
                c[last] < (o[-3] + c[-3]) / 2):   # 3. záró az 1. közepénél alacsonyabb
            patterns_found.append({
                "name": "Evening Star",
                "type": "bearish",
                "strength": "erős",
            })
            sell_score += 3

    # --- Three White Soldiers (erősen bullish) ---
    if len(ohlcv) >= 3:
        if all(c[i] > o[i] for i in [-3, -2, last]) and \
           c[-2] > c[-3] and c[last] > c[-2]:
            patterns_found.append({
                "name": "Three White Soldiers",
                "type": "bullish",
                "strength": "erős",
            })
            buy_score += 3

    # --- Three Black Crows (erősen bearish) ---
    if len(ohlcv) >= 3:
        if all(c[i] < o[i] for i in [-3, -2, last]) and \
           c[-2] < c[-3] and c[last] < c[-2]:
            patterns_found.append({
                "name": "Three Black Crows",
                "type": "bearish",
                "strength": "erős",
            })
            sell_score += 3

    # --- Végső jelzés ---
    if buy_score > sell_score:
        signal = "bullish"
        score  = buy_score
    elif sell_score > buy_score:
        signal = "bearish"
        score  = -sell_score
    else:
        signal = "neutral"
        score  = 0

    if patterns_found:
        names = [p["name"] for p in patterns_found]
        logger.info(
            f"🕯️  Minták: {', '.join(names)} | "
            f"{'🟢' if signal == 'bullish' else '🔴' if signal == 'bearish' else '⚪'} "
            f"{signal} | Score: {score:+d}"
        )

    return {
        "signal":   signal,
        "score":    score,
        "patterns": patterns_found,
        "buy_score":  buy_score,
        "sell_score": sell_score,
    }


# ============================================================
# CHART MINTÁK (Chart Patterns)
# ============================================================

def detect_chart_patterns(ohlcv: list) -> dict:
    """
    Felismeri a nagyobb chart mintákat.
    Legalább 20 gyertya kell.
    """
    if len(ohlcv) < 20:
        return {"signal": "neutral", "patterns": [], "score": 0}

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    patterns_found = []
    buy_score      = 0
    sell_score     = 0

    # --- Double Bottom (bullish fordulat) ---
    # Két hasonló mélypontot keres
    recent_lows = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            recent_lows.append((i, lows[i]))

    if len(recent_lows) >= 2:
        last_two = recent_lows[-2:]
        low1, low2 = last_two[0][1], last_two[1][1]
        # Ha a két mélypont hasonló (5%-on belül)
        if abs(low1 - low2) / max(low1, low2) < 0.05:
            patterns_found.append({
                "name": "Double Bottom",
                "type": "bullish",
                "strength": "erős",
            })
            buy_score += 3

    # --- Double Top (bearish fordulat) ---
    recent_highs = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            recent_highs.append((i, highs[i]))

    if len(recent_highs) >= 2:
        last_two = recent_highs[-2:]
        high1, high2 = last_two[0][1], last_two[1][1]
        if abs(high1 - high2) / max(high1, high2) < 0.05:
            patterns_found.append({
                "name": "Double Top",
                "type": "bearish",
                "strength": "erős",
            })
            sell_score += 3

    # --- Bull Flag (bullish folytatás) ---
    # Erős emelkedés majd konszolidáció
    if len(closes) >= 15:
        pole_start  = closes[-15]
        pole_end    = closes[-10]
        flag_closes = closes[-10:]

        pole_gain = (pole_end - pole_start) / pole_start
        flag_range = (max(flag_closes) - min(flag_closes)) / pole_end

        if pole_gain > 0.03 and flag_range < 0.02:
            patterns_found.append({
                "name": "Bull Flag",
                "type": "bullish",
                "strength": "közepes",
            })
            buy_score += 2

    # --- Bear Flag (bearish folytatás) ---
    if len(closes) >= 15:
        pole_start  = closes[-15]
        pole_end    = closes[-10]
        flag_closes = closes[-10:]

        pole_drop  = (pole_start - pole_end) / pole_start
        flag_range = (max(flag_closes) - min(flag_closes)) / pole_end

        if pole_drop > 0.03 and flag_range < 0.02:
            patterns_found.append({
                "name": "Bear Flag",
                "type": "bearish",
                "strength": "közepes",
            })
            sell_score += 2

    # --- Ascending Triangle (bullish kitörés) ---
    if len(closes) >= 20:
        recent_highs_vals = [highs[i] for i in range(len(highs)-20, len(highs))]
        recent_lows_vals  = [lows[i]  for i in range(len(lows)-20,  len(lows))]

        # Highs közel azonos szinten (ellenállás)
        high_std = np.std(recent_highs_vals) / np.mean(recent_highs_vals)
        # Lows emelkednek
        low_trend = np.polyfit(range(len(recent_lows_vals)), recent_lows_vals, 1)[0]

        if high_std < 0.01 and low_trend > 0:
            patterns_found.append({
                "name": "Ascending Triangle",
                "type": "bullish",
                "strength": "közepes",
            })
            buy_score += 2

    # --- Descending Triangle (bearish kitörés) ---
    if len(closes) >= 20:
        recent_highs_vals = [highs[i] for i in range(len(highs)-20, len(highs))]
        recent_lows_vals  = [lows[i]  for i in range(len(lows)-20,  len(lows))]

        low_std    = np.std(recent_lows_vals) / np.mean(recent_lows_vals)
        high_trend = np.polyfit(range(len(recent_highs_vals)), recent_highs_vals, 1)[0]

        if low_std < 0.01 and high_trend < 0:
            patterns_found.append({
                "name": "Descending Triangle",
                "type": "bearish",
                "strength": "közepes",
            })
            sell_score += 2

    # --- Végső jelzés ---
    if buy_score > sell_score:
        signal = "bullish"
        score  = buy_score
    elif sell_score > buy_score:
        signal = "bearish"
        score  = -sell_score
    else:
        signal = "neutral"
        score  = 0

    if patterns_found:
        names = [p["name"] for p in patterns_found]
        logger.info(
            f"📈 Chart minták: {', '.join(names)} | "
            f"{'🟢' if signal == 'bullish' else '🔴' if signal == 'bearish' else '⚪'} "
            f"{signal} | Score: {score:+d}"
        )

    return {
        "signal":     signal,
        "score":      score,
        "patterns":   patterns_found,
        "buy_score":  buy_score,
        "sell_score": sell_score,
    }


# ============================================================
# CIKLUS FELISMERÉS
# ============================================================

def detect_time_patterns() -> dict:
    """
    Időalapú ciklus minták felismerése.
    Heti és napi szezonalitás.
    """
    from datetime import datetime, timezone

    now        = datetime.now(timezone.utc)
    hour       = now.hour
    weekday    = now.weekday()  # 0=hétfő, 6=vasárnap

    signals    = []
    buy_score  = 0
    sell_score = 0

    # --- Napi szezonalitás ---
    # Reggel 8-11 UTC: európai nyitás – aktív piac
    if 8 <= hour <= 11:
        signals.append("EU nyitás (aktív)")
        buy_score += 1
    # 13-16 UTC: US nyitás – nagy mozgások
    elif 13 <= hour <= 16:
        signals.append("US nyitás (volatilis)")
    # 2-6 UTC: ázsiai piac – alacsony likviditás
    elif 2 <= hour <= 6:
        signals.append("Ázsiai kereskedés (alacsony likviditás)")
        sell_score += 1  # óvatosság

    # --- Heti szezonalitás ---
    # Hétfő/kedd historikusan gyengébb
    if weekday in [0, 1]:
        signals.append("Hétfő/Kedd (historikusan gyengébb)")
        sell_score += 1
    # Szerda/csütörtök általában erősebb
    elif weekday in [2, 3]:
        signals.append("Sze/Csüt (historikusan erősebb)")
        buy_score += 1
    # Péntek: pozíciók zárása hétvége előtt
    elif weekday == 4:
        signals.append("Péntek (pozíció zárás)")
        sell_score += 1

    if buy_score > sell_score:
        signal = "bullish"
    elif sell_score > buy_score:
        signal = "bearish"
    else:
        signal = "neutral"

    if signals:
        logger.info(
            f"⏰ Időminták: {', '.join(signals)} | "
            f"{'🟢' if signal == 'bullish' else '🔴' if signal == 'bearish' else '⚪'} "
            f"{signal}"
        )

    return {
        "signal":  signal,
        "signals": signals,
        "hour":    hour,
        "weekday": weekday,
    }


# ============================================================
# FŐ ÖSSZESÍTŐ
# ============================================================

def get_pattern_signal(ohlcv: list) -> dict:
    """
    Összesíti az összes minta jelzést.
    """
    candle = detect_candlestick_patterns(ohlcv)
    chart  = detect_chart_patterns(ohlcv)
    timing = detect_time_patterns()

    total_buy  = candle["buy_score"] + chart["buy_score"]
    total_sell = candle["sell_score"] + chart["sell_score"]

    # Időminták módosítása
    if timing["signal"] == "bullish":
        total_buy  += 1
    elif timing["signal"] == "bearish":
        total_sell += 1

    if total_buy > total_sell:
        final_signal = "bullish"
    elif total_sell > total_buy:
        final_signal = "bearish"
    else:
        final_signal = "neutral"

    all_patterns = candle["patterns"] + chart["patterns"]

    return {
        "signal":          final_signal,
        "total_buy":       total_buy,
        "total_sell":      total_sell,
        "candlestick":     candle,
        "chart":           chart,
        "timing":          timing,
        "all_patterns":    all_patterns,
        "pattern_count":   len(all_patterns),
    }