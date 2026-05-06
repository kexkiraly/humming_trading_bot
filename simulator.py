# ============================================================
# simulator.py – Virtuális tőzsde szimuláció motor
# ============================================================

import sqlite3
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SIM_DB_FILE  = "simulation.db"
SIM_CFG_FILE = "sim_config.json"

# --- Alapbeállítások ---
STARTING_BALANCE  = 10000.0   # induló virtuális egyenleg ($)
TRADING_FEE       = 0.001     # 0.1% kereskedési díj (Binance standard)
SLIPPAGE          = 0.0005    # 0.05% slippage (valódi piaci súrlódás)


# ============================================================
# Adatbázis inicializálás
# ============================================================

def init_sim_db():
    """Létrehozza a szimuláció adatbázisát."""
    conn   = sqlite3.connect(SIM_DB_FILE)
    cursor = conn.cursor()

    # Virtuális megbízások táblája
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sim_trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            side         TEXT NOT NULL,
            price        REAL NOT NULL,
            amount       REAL NOT NULL,
            fee          REAL NOT NULL,
            slippage     REAL NOT NULL,
            balance_after REAL NOT NULL,
            portfolio_value REAL NOT NULL,
            profit_pct   REAL,
            entry_price  REAL
        )
    """)

    # Portfólió snapshot táblája (5 percenként)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sim_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            cash        REAL NOT NULL,
            holdings    TEXT NOT NULL,
            total_value REAL NOT NULL,
            btc_price   REAL
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✅ Szimuláció adatbázis inicializálva.")


# ============================================================
# Fő szimulátor osztály
# ============================================================

class TradingSimulator:
    """
    Virtuális tőzsde szimulátor.
    Valódi piaci feltételeket szimulál:
    - Kereskedési díj
    - Slippage
    - Portfólió követés
    - Teljesítmény mérés
    """

    def __init__(self):
        init_sim_db()
        self._load_state()
        logger.info(
            f"🎮 Szimulátor inicializálva | "
            f"Egyenleg: ${self.cash:.2f} | "
            f"Pozíciók: {len(self.holdings)}"
        )

    def _load_state(self):
        """Betölti az előző állapotot, vagy újat hoz létre."""
        if os.path.exists(SIM_CFG_FILE):
            try:
                with open(SIM_CFG_FILE, "r") as f:
                    state = json.load(f)
                self.cash          = state["cash"]
                self.holdings      = state["holdings"]
                self.total_trades  = state["total_trades"]
                self.winning_trades = state["winning_trades"]
                self.peak_value    = state["peak_value"]
                logger.info("📂 Szimulátor állapot betöltve.")
                return
            except Exception:
                pass

        # Új szimuláció
        self.cash           = STARTING_BALANCE
        self.holdings       = {}   # {"BTC/USDT": {"amount": 0.001, "entry_price": 77349}}
        self.total_trades   = 0
        self.winning_trades = 0
        self.peak_value     = STARTING_BALANCE

    def _save_state(self):
        """Elmenti az aktuális állapotot."""
        state = {
            "cash":           self.cash,
            "holdings":       self.holdings,
            "total_trades":   self.total_trades,
            "winning_trades": self.winning_trades,
            "peak_value":     self.peak_value,
        }
        with open(SIM_CFG_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def get_portfolio_value(self, current_prices: dict) -> float:
        """
        Kiszámítja a teljes portfólió értékét.
        current_prices: {"BTC/USDT": 77349.0, ...}
        """
        total = self.cash
        for symbol, position in self.holdings.items():
            price  = current_prices.get(symbol, position["entry_price"])
            total += position["amount"] * price
        return total

    def buy(self, symbol: str, price: float, amount: float) -> dict | None:
        """
        Virtuális vétel.
        Figyelembe veszi a díjat és a slippage-t.
        """
        # Slippage alkalmazása (kicsit drágábban vesz)
        effective_price = price * (1 + SLIPPAGE)
        cost            = effective_price * amount
        fee             = cost * TRADING_FEE
        total_cost      = cost + fee

        if total_cost > self.cash:
            logger.warning(
                f"🎮 [SIM] Nincs elég egyenleg! "
                f"Szükséges: ${total_cost:.2f} | "
                f"Elérhető: ${self.cash:.2f}"
            )
            return None

        # Pozíció megnyitása
        self.cash -= total_cost
        self.holdings[symbol] = {
            "amount":      amount,
            "entry_price": effective_price,
        }
        self.total_trades += 1

        portfolio_value = self.get_portfolio_value({symbol: price})
        self.peak_value = max(self.peak_value, portfolio_value)

        # Mentés adatbázisba
        self._save_trade_to_db(
            symbol=symbol,
            side="buy",
            price=effective_price,
            amount=amount,
            fee=fee,
            slippage=price * SLIPPAGE * amount,
            balance_after=self.cash,
            portfolio_value=portfolio_value,
        )
        self._save_state()

        logger.info(
            f"🎮 [SIM] VÉTEL | {symbol} @ ${effective_price:.2f} | "
            f"Mennyiség: {amount} | Díj: ${fee:.4f} | "
            f"Egyenleg: ${self.cash:.2f}"
        )
        return {"status": "sim_buy", "price": effective_price, "amount": amount}

    def sell(self, symbol: str, price: float, amount: float) -> dict | None:
        """
        Virtuális eladás.
        Kiszámítja a profitot slippage és díj után.
        """
        if symbol not in self.holdings:
            logger.warning(f"🎮 [SIM] Nincs nyitott pozíció: {symbol}")
            return None

        position        = self.holdings[symbol]
        entry_price     = position["entry_price"]

        # Slippage alkalmazása (kicsit olcsóbban ad el)
        effective_price = price * (1 - SLIPPAGE)
        revenue         = effective_price * amount
        fee             = revenue * TRADING_FEE
        net_revenue     = revenue - fee

        # Profit számítás
        cost       = entry_price * amount
        profit     = net_revenue - cost
        profit_pct = (profit / cost) * 100

        self.cash += net_revenue
        del self.holdings[symbol]

        if profit > 0:
            self.winning_trades += 1

        portfolio_value = self.cash
        self.peak_value = max(self.peak_value, portfolio_value)

        # Mentés adatbázisba
        self._save_trade_to_db(
            symbol=symbol,
            side="sell",
            price=effective_price,
            amount=amount,
            fee=fee,
            slippage=price * SLIPPAGE * amount,
            balance_after=self.cash,
            portfolio_value=portfolio_value,
            profit_pct=profit_pct,
            entry_price=entry_price,
        )
        self._save_state()

        logger.info(
            f"🎮 [SIM] ELADÁS | {symbol} @ ${effective_price:.2f} | "
            f"Profit: {profit_pct:+.2f}% (${profit:+.2f}) | "
            f"Egyenleg: ${self.cash:.2f}"
        )
        return {
            "status":     "sim_sell",
            "price":      effective_price,
            "profit_pct": profit_pct,
            "profit_usd": profit,
        }

    def _save_trade_to_db(self, symbol, side, price, amount, fee,
                          slippage, balance_after, portfolio_value,
                          profit_pct=None, entry_price=None):
        """Elmenti a megbízást az adatbázisba."""
        try:
            conn   = sqlite3.connect(SIM_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sim_trades
                (timestamp, symbol, side, price, amount, fee, slippage,
                 balance_after, portfolio_value, profit_pct, entry_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol, side, price, amount, fee, slippage,
                balance_after, portfolio_value, profit_pct, entry_price
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Szimuláció DB hiba: {e}")

    def save_snapshot(self, current_prices: dict):
        """5 percenként elmenti a portfólió pillanatképét."""
        portfolio_value = self.get_portfolio_value(current_prices)
        try:
            conn   = sqlite3.connect(SIM_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sim_snapshots
                (timestamp, cash, holdings, total_value, btc_price)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.cash,
                json.dumps(self.holdings),
                portfolio_value,
                current_prices.get("BTC/USDT", 0),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Snapshot mentési hiba: {e}")

    def get_stats(self, current_prices: dict = None) -> dict:
        """Visszaadja a szimuláció teljes statisztikáját."""
        current_prices  = current_prices or {}
        portfolio_value = self.get_portfolio_value(current_prices)
        total_return    = ((portfolio_value - STARTING_BALANCE) / STARTING_BALANCE) * 100
        drawdown        = ((self.peak_value - portfolio_value) / self.peak_value) * 100 if self.peak_value > 0 else 0
        win_rate        = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        # Buy and hold összehasonlítás (ha BTC árat tudunk)
        bh_return = None
        if "BTC/USDT" in current_prices:
            # Mekkora lenne ha az induló egyenlegért BTC-t vettünk volna
            try:
                conn   = sqlite3.connect(SIM_DB_FILE)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT price FROM sim_trades
                    WHERE symbol = 'BTC/USDT' AND side = 'buy'
                    ORDER BY id ASC LIMIT 1
                """)
                row = cursor.fetchone()
                conn.close()
                if row:
                    first_btc_price = row[0]
                    btc_bought      = STARTING_BALANCE / first_btc_price
                    bh_value        = btc_bought * current_prices["BTC/USDT"]
                    bh_return       = ((bh_value - STARTING_BALANCE) / STARTING_BALANCE) * 100
            except Exception:
                pass

        return {
            "starting_balance": STARTING_BALANCE,
            "current_cash":     self.cash,
            "portfolio_value":  portfolio_value,
            "total_return_pct": total_return,
            "total_return_usd": portfolio_value - STARTING_BALANCE,
            "total_trades":     self.total_trades,
            "winning_trades":   self.winning_trades,
            "win_rate":         win_rate,
            "max_drawdown":     drawdown,
            "peak_value":       self.peak_value,
            "buy_hold_return":  bh_return,
            "open_positions":   len(self.holdings),
        }

    def print_stats(self, current_prices: dict = None):
        """Kiírja a statisztikákat szépen formázva."""
        s = self.get_stats(current_prices)
        print("\n" + "="*50)
        print("     🎮 SZIMULÁCIÓ STATISZTIKÁK")
        print("="*50)
        print(f"  Induló egyenleg:     ${s['starting_balance']:>10.2f}")
        print(f"  Aktuális portfólió:  ${s['portfolio_value']:>10.2f}")
        profit_sign = "+" if s['total_return_pct'] >= 0 else ""
        print(f"  Összes hozam:        {profit_sign}{s['total_return_pct']:>9.2f}%")
        print(f"  Hozam ($):           ${s['total_return_usd']:>+10.2f}")
        print("-"*50)
        print(f"  Összes megbízás:     {s['total_trades']:>10}")
        print(f"  Nyerő megbízások:    {s['winning_trades']:>10}")
        print(f"  Win rate:            {s['win_rate']:>9.1f}%")
        print(f"  Max drawdown:        {s['max_drawdown']:>9.2f}%")
        print(f"  Csúcsérték:          ${s['peak_value']:>10.2f}")
        if s['buy_hold_return'] is not None:
            print("-"*50)
            bot_vs_bh = s['total_return_pct'] - s['buy_hold_return']
            print(f"  Buy & Hold hozam:    {s['buy_hold_return']:>+9.2f}%")
            print(f"  Bot vs B&H:          {bot_vs_bh:>+9.2f}%")
            verdict = "✅ Bot JOBB!" if bot_vs_bh > 0 else "❌ Bot ROSSZABB!"
            print(f"  Eredmény:            {verdict}")
        print("="*50 + "\n")