# ============================================================
# market_regime.py – Piaci rezsim felismerés
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta
import numpy as np

logger = logging.getLogger(__name__)

# --- Rezsim típusok ---
REGIME_TRENDING  = "trending"
REGIME_RANGING   = "ranging"
REGIME_VOLATILE  = "volatile"
REGIME_UNKNOWN   = "unknown"

# --- Beállítások ---
ADX_TREND_THRESHOLD   = 25    # ADX > 25 → trending piac
ADX_STRONG_THRESHOLD  = 40    # ADX > 40 → erős trend
BB_WIDTH_RANGING      = 0.03  # BB szélesség < 3% → ranging
BB_WIDTH_VOLATILE     = 0.08  # BB szélesség > 8% → volatile
ATR_VOLATILE_MULT     = 1.5   # ATR > 1.5x átlag → volatile


def detect_regime(ohlcv: list) -> dict:
    """
    Felismeri az aktuális piaci rezsimet.

    Három rezsim:
    1. TRENDING  – erős irányított mozgás
    2. RANGING   – oldalazó, konszolidáció
    3. VOLATILE  – hirtelen, kiszámíthatatlan mozgás
    """
    if len(ohlcv) < 30:
        return {
            "regime":      REGIME_UNKNOWN,
            "adx":         0,
            "bb_width":    0,
            "atr_ratio":   1,
            "trend_dir":   "neutral",
            "confidence":  0,
            "description": "Nincs elég adat",
        }

    try:
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]

        # --- ADX (Average Directional Index) ---
        # Megmutatja mennyire erős a trend (0-100)
        # > 25 = trending, < 25 = ranging
        adx_df  = ta.adx(highs, lows, closes, length=14)
        adx     = adx_df["ADX_14"].iloc[-1]
        dmp     = adx_df["DMP_14"].iloc[-1]  # +DI (bullish erő)
        dmn     = adx_df["DMN_14"].iloc[-1]  # -DI (bearish erő)

        # Trend iránya
        if dmp > dmn:
            trend_dir = "bullish"
        elif dmn > dmp:
            trend_dir = "bearish"
        else:
            trend_dir = "neutral"

        # --- Bollinger Band szélesség ---
        # Szűk BB = ranging, széles BB = volatile/trending
        bb_df      = ta.bbands(closes, length=20)
        bb_col_u   = [c for c in bb_df.columns if c.startswith("BBU")][0]
        bb_col_l   = [c for c in bb_df.columns if c.startswith("BBL")][0]
        bb_col_m   = [c for c in bb_df.columns if c.startswith("BBM")][0]
        bb_upper   = bb_df[bb_col_u].iloc[-1]
        bb_lower   = bb_df[bb_col_l].iloc[-1]
        bb_middle  = bb_df[bb_col_m].iloc[-1]
        bb_width   = (bb_upper - bb_lower) / bb_middle

        # --- ATR arány ---
        # Jelenlegi ATR vs. 50 periódusos átlag ATR
        atr_series = ta.atr(highs, lows, closes, length=14)
        current_atr = atr_series.iloc[-1]
        avg_atr     = atr_series.iloc[-50:].mean() if len(atr_series) >= 50 \
                      else atr_series.mean()
        atr_ratio   = current_atr / avg_atr if avg_atr > 0 else 1.0

        # --- Rezsim meghatározása ---
        regime     = REGIME_UNKNOWN
        confidence = 0
        scores     = {
            REGIME_TRENDING: 0,
            REGIME_RANGING:  0,
            REGIME_VOLATILE: 0,
        }

        # Trending jelzések
        if adx > ADX_TREND_THRESHOLD:
            scores[REGIME_TRENDING] += 2
        if adx > ADX_STRONG_THRESHOLD:
            scores[REGIME_TRENDING] += 2
        if bb_width > 0.04 and adx > ADX_TREND_THRESHOLD:
            scores[REGIME_TRENDING] += 1

        # Ranging jelzések
        if adx < ADX_TREND_THRESHOLD:
            scores[REGIME_RANGING] += 2
        if bb_width < BB_WIDTH_RANGING:
            scores[REGIME_RANGING] += 2
        if atr_ratio < 0.8:
            scores[REGIME_RANGING] += 1

        # Volatile jelzések
        if bb_width > BB_WIDTH_VOLATILE:
            scores[REGIME_VOLATILE] += 2
        if atr_ratio > ATR_VOLATILE_MULT:
            scores[REGIME_VOLATILE] += 2
        if adx < 20 and bb_width > 0.05:
            scores[REGIME_VOLATILE] += 1

        # Legtöbb pontot kapott rezsim
        regime     = max(scores, key=scores.get)
        total      = sum(scores.values())
        confidence = (scores[regime] / total * 100) if total > 0 else 0

        # --- Rezsim specifikus beállítások ---
        regime_config = _get_regime_config(regime, trend_dir, adx)

        result = {
            "regime":        regime,
            "trend_dir":     trend_dir,
            "adx":           round(float(adx), 2),
            "bb_width":      round(float(bb_width), 4),
            "atr_ratio":     round(float(atr_ratio), 2),
            "confidence":    round(confidence, 1),
            "scores":        scores,
            "config":        regime_config,
            "description":   _get_description(regime, trend_dir, adx),
        }

        emoji = "📈" if regime == REGIME_TRENDING else \
                "↔️" if regime == REGIME_RANGING else \
                "⚡" if regime == REGIME_VOLATILE else "❓"

        logger.info(
            f"🌊 Rezsim: {emoji} {regime.upper()} "
            f"({confidence:.0f}% bizalom) | "
            f"ADX: {adx:.1f} | "
            f"BB szélesség: {bb_width:.3f} | "
            f"ATR arány: {atr_ratio:.2f} | "
            f"Irány: {trend_dir}"
        )

        return result

    except Exception as e:
        logger.error(f"Rezsim felismerési hiba: {e}")
        return {
            "regime":      REGIME_UNKNOWN,
            "trend_dir":   "neutral",
            "adx":         0,
            "bb_width":    0,
            "atr_ratio":   1,
            "confidence":  0,
            "config":      _get_regime_config(REGIME_UNKNOWN, "neutral", 0),
            "description": f"Hiba: {e}",
        }


def _get_regime_config(regime: str, trend_dir: str,
                       adx: float) -> dict:
    """
    Visszaadja a rezsimhez tartozó stratégia beállításokat.
    """
    if regime == REGIME_TRENDING:
        return {
            "min_votes":          3,     # lazább belépési feltétel
            "position_size_mult": 1.2,   # 20%-kal nagyobb pozíció
            "sl_multiplier":      2.0,   # normál stop-loss
            "use_ma_crossover":   True,  # MA crossover aktív
            "use_rsi_extremes":   False, # RSI extrémek kevésbé fontos
            "description":        "Trend követés – nagyobb pozíciók",
        }
    elif regime == REGIME_RANGING:
        return {
            "min_votes":          4,     # szigorúbb belépési feltétel
            "position_size_mult": 0.8,   # 20%-kal kisebb pozíció
            "sl_multiplier":      1.5,   # szűkebb stop-loss
            "use_ma_crossover":   False, # MA crossover kevésbé megbízható
            "use_rsi_extremes":   True,  # RSI extrémek fontosak
            "description":        "Oldalazó piac – RSI alapú kereskedés",
        }
    elif regime == REGIME_VOLATILE:
        return {
            "min_votes":          5,     # nagyon szigorú belépés
            "position_size_mult": 0.5,   # fél akkora pozíció
            "sl_multiplier":      3.0,   # tágabb stop-loss
            "use_ma_crossover":   False,
            "use_rsi_extremes":   False,
            "description":        "Volatilis piac – óvatos kereskedés",
        }
    else:
        return {
            "min_votes":          4,
            "position_size_mult": 1.0,
            "sl_multiplier":      2.0,
            "use_ma_crossover":   True,
            "use_rsi_extremes":   True,
            "description":        "Ismeretlen rezsim – alap beállítások",
        }


def _get_description(regime: str, trend_dir: str,
                     adx: float) -> str:
    """Emberi olvasható leírás a rezsimről."""
    if regime == REGIME_TRENDING:
        strength = "erős" if adx > ADX_STRONG_THRESHOLD else "közepes"
        return f"{strength} {trend_dir} trend (ADX: {adx:.0f})"
    elif regime == REGIME_RANGING:
        return f"Oldalazó piac – konszolidáció"
    elif regime == REGIME_VOLATILE:
        return f"Volatilis piac – kiszámíthatatlan mozgás"
    return "Ismeretlen piaci állapot"


class RegimeDetector:
    """
    Rezsim detektor osztály – cache-eli az eredményt
    hogy ne kelljen minden körben újraszámolni.
    """

    def __init__(self):
        self.current_regime = None
        self.update_counter = 0
        self.UPDATE_EVERY   = 12  # minden 12. körben frissít (~1 perc)
        logger.info("🌊 Rezsim Detektor inicializálva.")

    def get_regime(self, exchange, symbol: str = "BTC/USDT") -> dict:
        """
        Visszaadja az aktuális rezsimet.
        Cache-eli az eredményt, csak 12 körönként frissít.
        """
        self.update_counter += 1

        if (self.current_regime is None or
                self.update_counter % self.UPDATE_EVERY == 0):
            ohlcv = exchange.get_ohlcv(
                symbol, timeframe="1h", limit=60
            )
            self.current_regime = detect_regime(ohlcv)

        return self.current_regime

    def get_min_votes(self) -> int:
        """Visszaadja a rezsimhez tartozó min_votes értéket."""
        if self.current_regime:
            return self.current_regime["config"]["min_votes"]
        return 3  # alapértelmezett

    def get_position_multiplier(self) -> float:
        """Visszaadja a pozícióméret szorzót."""
        if self.current_regime:
            return self.current_regime["config"]["position_size_mult"]
        return 1.0

    def should_trade(self) -> bool:
        """
        Extrém volatilis piacban megállítja a kereskedést.
        """
        if not self.current_regime:
            return True
        # Ha nagyon volatilis ÉS alacsony bizalom → ne kereskedj
        if (self.current_regime["regime"] == REGIME_VOLATILE and
                self.current_regime["confidence"] > 70):
            logger.warning(
                "⚡ Extrém volatilis piac – kereskedés szünetel!"
            )
            return False
        return True