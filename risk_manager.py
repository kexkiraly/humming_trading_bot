# ============================================================
# risk_manager.py – ATR stop-loss + Trailing stop
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# --- Beállítások ---
ATR_PERIOD          = 14      # ATR periódus
ATR_MULTIPLIER_SL   = 2.0     # Stop-loss: ár - 2x ATR
ATR_MULTIPLIER_TP   = 3.0     # Take-profit: ár + 3x ATR
TRAILING_PCT        = 0.02    # Trailing stop: 2% az árcsúcstól
MIN_STOP_PCT        = 0.008   # Minimum stop-loss: 0.8%
MAX_STOP_PCT        = 0.05    # Maximum stop-loss: 5%
MIN_POSITION_PCT    = 0.01    # Minimum pozícióméret tőkéhez képest
MAX_POSITION_PCT    = 0.30    # Maximum pozícióméret


def calculate_atr(ohlcv: list, period: int = ATR_PERIOD) -> float:
    """
    Kiszámítja az ATR (Average True Range) értékét.
    Megmutatja mennyit mozog az ár átlagosan.
    """
    if len(ohlcv) < period + 1:
        return 0.0
    try:
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=period)
        atr        = atr_series.iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0
    except Exception as e:
        logger.error(f"ATR számítási hiba: {e}")
        return 0.0


def get_dynamic_stop_loss(entry_price: float, atr: float) -> float:
    """
    Kiszámítja a dinamikus stop-loss szintet ATR alapján.
    Visszaad egy árat (nem %-ot).
    """
    if atr <= 0 or entry_price <= 0:
        return entry_price * (1 - MIN_STOP_PCT)

    # Stop-loss szint: belépési ár - 2x ATR
    sl_price = entry_price - (ATR_MULTIPLIER_SL * atr)

    # %-ban kifejezve ellenőrzés
    sl_pct = (entry_price - sl_price) / entry_price

    # Minimum és maximum korlátok
    sl_pct  = max(MIN_STOP_PCT, min(MAX_STOP_PCT, sl_pct))
    sl_price = entry_price * (1 - sl_pct)

    logger.info(
        f"🛡️  ATR Stop-loss: ${sl_price:.2f} "
        f"({sl_pct:.1%} az ártól) | ATR: ${atr:.2f}"
    )
    return sl_price


def get_dynamic_take_profit(entry_price: float, atr: float) -> float:
    """
    Kiszámítja a dinamikus take-profit szintet ATR alapján.
    """
    if atr <= 0 or entry_price <= 0:
        return entry_price * 1.03  # 3% alapértelmezett

    tp_price = entry_price + (ATR_MULTIPLIER_TP * atr)
    tp_pct   = (tp_price - entry_price) / entry_price

    logger.info(
        f"🎯 ATR Take-profit: ${tp_price:.2f} "
        f"({tp_pct:.1%} az ártól)"
    )
    return tp_price


def get_atr_position_size(
    capital: float,
    entry_price: float,
    atr: float,
    risk_pct: float = 0.01  # max tőke 1%-át kockáztatjuk
) -> float:
    """
    ATR alapú pozícióméret számítás.
    Volatilis piacban kisebb pozíció, nyugodt piacban nagyobb.
    """
    if atr <= 0 or entry_price <= 0:
        return 0.001  # alapértelmezett

    # Mennyit veszítünk egy egységen stop-loss esetén
    risk_per_unit = ATR_MULTIPLIER_SL * atr

    # Max kockáztatható összeg
    max_risk_usd = capital * risk_pct

    # Pozícióméret
    units = max_risk_usd / risk_per_unit

    # Korlátok
    min_units = (capital * MIN_POSITION_PCT) / entry_price
    max_units = (capital * MAX_POSITION_PCT) / entry_price
    units     = max(min_units, min(max_units, units))
    units     = round(units, 5)

    logger.info(
        f"📏 ATR pozícióméret: {units} egység | "
        f"Kockázat: ${units * risk_per_unit:.2f} "
        f"({risk_pct:.1%} tőkéből)"
    )
    return units


class TrailingStopManager:
    """
    Trailing stop kezelő.
    Követi az árat felfelé, de nem engedi lefelé.
    """

    def __init__(self):
        # {"BTC/USDT": {"peak": 80000, "stop": 78400, "active": True}}
        self.stops = {}
        logger.info("🔄 Trailing Stop Manager inicializálva.")

    def activate(self, symbol: str, entry_price: float,
                 atr: float = 0.0):
        """
        Aktiválja a trailing stop-ot egy pozícióhoz.
        """
        # Kezdeti stop: entry ár - trailing %
        if atr > 0:
            # ATR alapú trailing távolság
            trail_distance = max(
                TRAILING_PCT * entry_price,
                ATR_MULTIPLIER_SL * atr
            )
        else:
            trail_distance = TRAILING_PCT * entry_price

        initial_stop = entry_price - trail_distance

        self.stops[symbol] = {
            "peak":     entry_price,
            "stop":     initial_stop,
            "distance": trail_distance,
            "active":   True,
        }

        logger.info(
            f"🔄 Trailing stop aktiválva: {symbol} | "
            f"Belépés: ${entry_price:.2f} | "
            f"Kezdeti stop: ${initial_stop:.2f} | "
            f"Távolság: ${trail_distance:.2f}"
        )

    def update(self, symbol: str, current_price: float) -> dict:
        """
        Frissíti a trailing stop-ot az aktuális árral.
        Visszaad egy dict-et:
        - triggered: True ha le kell zárni
        - stop_price: aktuális stop ár
        - peak: legmagasabb ár
        - profit_pct: jelenlegi profit %
        """
        if symbol not in self.stops:
            return {"triggered": False, "stop_price": 0}

        ts = self.stops[symbol]

        if not ts["active"]:
            return {"triggered": False, "stop_price": ts["stop"]}

        # Új csúcs esetén: stop felfelé mozdul
        if current_price > ts["peak"]:
            ts["peak"] = current_price
            ts["stop"] = current_price - ts["distance"]
            logger.debug(
                f"🔄 Trailing stop frissítve: {symbol} | "
                f"Csúcs: ${ts['peak']:.2f} | "
                f"Stop: ${ts['stop']:.2f}"
            )

        # Stop triggered?
        if current_price <= ts["stop"]:
            profit_pct = (ts["stop"] / ts["peak"] - 1) * 100
            logger.warning(
                f"🔄 TRAILING STOP TRIGGERELT: {symbol} | "
                f"Ár: ${current_price:.2f} | "
                f"Stop: ${ts['stop']:.2f} | "
                f"Csúcs volt: ${ts['peak']:.2f}"
            )
            return {
                "triggered":  True,
                "stop_price": ts["stop"],
                "peak":       ts["peak"],
                "profit_pct": profit_pct,
            }

        return {
            "triggered":  False,
            "stop_price": ts["stop"],
            "peak":       ts["peak"],
            "profit_pct": (current_price / ts["peak"] - 1) * 100,
        }

    def deactivate(self, symbol: str):
        """Törli a trailing stop-ot egy pozícióhoz."""
        if symbol in self.stops:
            del self.stops[symbol]
            logger.info(f"🔄 Trailing stop törölve: {symbol}")

    def get_status(self, symbol: str) -> dict:
        """Visszaadja a trailing stop állapotát."""
        return self.stops.get(symbol, {})