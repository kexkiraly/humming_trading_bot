# ============================================================
# database.py – Megbízások tárolása és statisztikák
# ============================================================

import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = "trades.db"


def init_db():
    """
    Létrehozza az adatbázist és a táblát, ha még nem léteznek.
    Biztonságos: többször is meghívható, nem töröl semmit.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            side        TEXT NOT NULL,
            price       REAL NOT NULL,
            amount      REAL NOT NULL,
            votes       INTEGER,
            rsi         REAL,
            macd        REAL,
            fg_value    INTEGER,
            entry_price REAL,
            profit_pct  REAL
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✅ Adatbázis inicializálva.")


def save_trade(symbol, side, price, amount, votes=None,
               rsi=None, macd=None, fg_value=None,
               entry_price=None, profit_pct=None):
    """
    Elment egy megbízást az adatbázisba.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trades
            (timestamp, symbol, side, price, amount, votes,
             rsi, macd, fg_value, entry_price, profit_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol, side, price, amount, votes,
            rsi, macd, fg_value, entry_price, profit_pct
        ))

        conn.commit()
        conn.close()
        logger.info(f"💾 Megbízás elmentve: {side.upper()} {symbol} @ {price}")

    except Exception as e:
        logger.error(f"Adatbázis mentési hiba: {e}")


def get_stats():
    """
    Visszaadja az összes statisztikát egy dict-ben.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Összes megbízás
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]

        # Csak eladások (ahol profit_pct nem NULL)
        cursor.execute("""
            SELECT COUNT(*), AVG(profit_pct), SUM(profit_pct),
                   MAX(profit_pct), MIN(profit_pct)
            FROM trades
            WHERE side = 'sell' AND profit_pct IS NOT NULL
        """)
        row = cursor.fetchone()
        total_sells   = row[0] or 0
        avg_profit    = row[1] or 0.0
        total_profit  = row[2] or 0.0
        best_trade    = row[3] or 0.0
        worst_trade   = row[4] or 0.0

        # Nyerő megbízások (profit_pct > 0)
        cursor.execute("""
            SELECT COUNT(*) FROM trades
            WHERE side = 'sell' AND profit_pct > 0
        """)
        winning_trades = cursor.fetchone()[0]

        win_rate = (winning_trades / total_sells * 100) if total_sells > 0 else 0.0

        conn.close()

        return {
            "total_trades":   total_trades,
            "total_sells":    total_sells,
            "win_rate":       win_rate,
            "avg_profit":     avg_profit,
            "total_profit":   total_profit,
            "best_trade":     best_trade,
            "worst_trade":    worst_trade,
        }

    except Exception as e:
        logger.error(f"Statisztika lekérési hiba: {e}")
        return {}


def print_stats():
    """
    Kiírja a statisztikákat a konzolra szépen formázva.
    """
    stats = get_stats()
    if not stats:
        print("Még nincs adat.")
        return

    print("\n" + "="*45)
    print("        📊 TRADING BOT STATISZTIKÁK")
    print("="*45)
    print(f"  Összes megbízás:      {stats['total_trades']}")
    print(f"  Lezárt pozíciók:      {stats['total_sells']}")
    print(f"  Win rate:             {stats['win_rate']:.1f}%")
    print(f"  Átlag profit:         {stats['avg_profit']:+.2f}%")
    print(f"  Összes profit:        {stats['total_profit']:+.2f}%")
    print(f"  Legjobb kereskedés:   {stats['best_trade']:+.2f}%")
    print(f"  Legrosszabb:          {stats['worst_trade']:+.2f}%")
    print("="*45 + "\n")