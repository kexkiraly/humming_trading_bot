# ============================================================
# guard.py – Védelmi rendszer (4 réteg)
# ============================================================

import logging
import json
import os
from datetime import datetime, timedelta
from database import DB_FILE
import sqlite3

logger = logging.getLogger(__name__)

GUARD_LOG_FILE  = "guard_log.json"
KILL_SWITCH_FILE = "KILL_SWITCH"  # ha ez a fájl létezik → bot leáll


# ============================================================
# 1. RÉTEG – Kereskedési korlátok
# ============================================================

MAX_DAILY_LOSS_PCT    = 5.0   # max napi veszteség %-ban
MAX_SINGLE_LOSS_PCT   = 2.0   # max egyetlen pozíció vesztesége
MAX_OPEN_POSITIONS    = 1     # max egyidejű nyitott pozíció
MAX_TRADES_PER_DAY    = 20    # max napi megbízás szám
MIN_CONFIDENCE        = 60.0  # ML min. bizalom %


# ============================================================
# 2. RÉTEG – Circuit breaker
# ============================================================

CIRCUIT_BREAKER_FILE = "circuit_breaker.json"

def is_circuit_breaker_active() -> bool:
    """Megnézi, hogy a circuit breaker aktív-e."""
    if not os.path.exists(CIRCUIT_BREAKER_FILE):
        return False
    try:
        with open(CIRCUIT_BREAKER_FILE, "r") as f:
            data = json.load(f)
        # Ha lejárt az ideje, töröljük
        until = datetime.fromisoformat(data["until"])
        if datetime.now() > until:
            os.remove(CIRCUIT_BREAKER_FILE)
            logger.info("✅ Circuit breaker lejárt – kereskedés újraindul.")
            return False
        remaining = (until - datetime.now()).seconds // 60
        logger.warning(f"⚡ Circuit breaker aktív – még {remaining} perc.")
        return True
    except Exception:
        return False


def activate_circuit_breaker(minutes: int = 60, reason: str = ""):
    """Bekapcsolja a circuit breaker-t adott időre."""
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    with open(CIRCUIT_BREAKER_FILE, "w") as f:
        json.dump({"until": until, "reason": reason}, f)
    logger.warning(
        f"⚡ CIRCUIT BREAKER AKTIVÁLVA! "
        f"Szünet: {minutes} perc. Ok: {reason}"
    )


# ============================================================
# 3. RÉTEG – Audit log
# ============================================================

def log_decision(action: str, symbol: str, reason: str,
                 allowed: bool, details: dict = None):
    """
    Minden döntést naplóz – legyen az vétel, eladás, vagy blokkolás.
    """
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action":    action,
        "symbol":    symbol,
        "reason":    reason,
        "allowed":   allowed,
        "details":   details or {}
    }

    # Meglévő log betöltése
    logs = []
    if os.path.exists(GUARD_LOG_FILE):
        try:
            with open(GUARD_LOG_FILE, "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append(entry)

    # Max 1000 bejegyzés
    if len(logs) > 1000:
        logs = logs[-1000:]

    with open(GUARD_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    status = "✅ ENGEDÉLYEZVE" if allowed else "🚫 BLOKKOLVA"
    logger.info(f"📋 Audit: {status} | {action} {symbol} | {reason}")


# ============================================================
# 4. RÉTEG – Kill switch
# ============================================================

def is_kill_switch_active() -> bool:
    """Megnézi hogy a kill switch aktív-e."""
    return os.path.exists(KILL_SWITCH_FILE)


def activate_kill_switch(reason: str = "Manuális leállítás"):
    """Bekapcsolja a kill switch-et."""
    with open(KILL_SWITCH_FILE, "w") as f:
        f.write(f"{datetime.now().isoformat()} – {reason}")
    logger.critical(f"🔴 KILL SWITCH AKTIVÁLVA! Ok: {reason}")


def deactivate_kill_switch():
    """Kikapcsolja a kill switch-et."""
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)
        logger.info("✅ Kill switch kikapcsolva – bot újraindul.")


# ============================================================
# FŐ VÉDELMI ELLENŐRZÉS
# ============================================================

class GuardSystem:
    """
    A fő védelmi rendszer osztály.
    Minden kereskedés előtt meg kell hívni a check() metódust.
    """

    def __init__(self):
        self.daily_loss     = 0.0
        self.daily_trades   = 0
        self.last_reset     = datetime.now().date()
        logger.info("🛡️  Védelmi rendszer inicializálva.")

    def _reset_daily_if_needed(self):
        """Napi számláló visszaállítása éjfélkor."""
        today = datetime.now().date()
        if today > self.last_reset:
            self.daily_loss   = 0.0
            self.daily_trades = 0
            self.last_reset   = today
            logger.info("🔄 Napi számlálók visszaállítva.")

    def check(self, action: str, symbol: str,
              confidence: float = 100.0,
              profit_pct: float = None) -> bool:
        """
        Ellenőrzi, hogy szabad-e kereskedni.
        Visszaad True-t ha igen, False-t ha nem.

        action: 'buy' vagy 'sell'
        symbol: pl. 'BTC/USDT'
        confidence: ML bizalom %
        profit_pct: veszteség esetén negatív szám
        """
        self._reset_daily_if_needed()

        # --- Kill switch ---
        if is_kill_switch_active():
            log_decision(action, symbol, "Kill switch aktív", False)
            return False

        # --- Circuit breaker ---
        if is_circuit_breaker_active():
            log_decision(action, symbol, "Circuit breaker aktív", False)
            return False

        # --- Napi trade limit ---
        if self.daily_trades >= MAX_TRADES_PER_DAY:
            log_decision(
                action, symbol,
                f"Napi limit elérve ({self.daily_trades}/{MAX_TRADES_PER_DAY})",
                False
            )
            return False

        # --- ML bizalom ellenőrzés ---
        if action == "buy" and confidence < MIN_CONFIDENCE:
            log_decision(
                action, symbol,
                f"ML bizalom túl alacsony ({confidence:.1f}% < {MIN_CONFIDENCE}%)",
                False
            )
            return False

        # --- Napi veszteség limit ---
        if self.daily_loss >= MAX_DAILY_LOSS_PCT:
            activate_circuit_breaker(
                minutes=240,
                reason=f"Napi max veszteség elérve ({self.daily_loss:.1f}%)"
            )
            log_decision(
                action, symbol,
                f"Napi veszteség limit ({self.daily_loss:.1f}%)",
                False
            )
            return False

        # --- Egyedi pozíció veszteség ---
        if profit_pct is not None and profit_pct <= -MAX_SINGLE_LOSS_PCT:
            activate_circuit_breaker(
                minutes=30,
                reason=f"Nagy veszteség egy pozíción ({profit_pct:.1f}%)"
            )
            log_decision(
                action, symbol,
                f"Pozíció veszteség limit ({profit_pct:.1f}%)",
                False
            )
            return False

        # --- Minden rendben ---
        self.daily_trades += 1
        if profit_pct and profit_pct < 0:
            self.daily_loss += abs(profit_pct)

        log_decision(
            action, symbol, "Minden ellenőrzés sikeres", True,
            details={
                "confidence":   confidence,
                "daily_trades": self.daily_trades,
                "daily_loss":   self.daily_loss
            }
        )
        return True

    def register_loss(self, loss_pct: float):
        """Veszteség regisztrálása a napi számlálóba."""
        if loss_pct < 0:
            self.daily_loss += abs(loss_pct)
            logger.info(
                f"📉 Napi veszteség eddig: {self.daily_loss:.2f}% "
                f"(limit: {MAX_DAILY_LOSS_PCT}%)"
            )

    def get_status(self) -> dict:
        """Visszaadja a védelmi rendszer aktuális állapotát."""
        return {
            "kill_switch":      is_kill_switch_active(),
            "circuit_breaker":  is_circuit_breaker_active(),
            "daily_trades":     self.daily_trades,
            "daily_loss":       self.daily_loss,
            "max_daily_loss":   MAX_DAILY_LOSS_PCT,
            "max_trades":       MAX_TRADES_PER_DAY,
        }