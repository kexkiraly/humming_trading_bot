# ============================================================
# portfolio.py – Portfólió kezelő
# ============================================================

import logging
import json
import os
from config import TRADING_PAIRS

logger = logging.getLogger(__name__)

PORTFOLIO_FILE = "portfolio.json"

# --- Portfólió beállítások ---
MAX_POSITIONS        = 3      # max egyidejű nyitott pozíció
MAX_POSITION_PCT     = 0.30   # max 30% egy coinban
MIN_POSITION_PCT     = 0.05   # min 5% egy pozícióhoz
REBALANCE_THRESHOLD  = 0.10   # 10% eltérés esetén rebalansz
TOTAL_CAPITAL        = 10000.0  # teljes virtuális tőke ($)


class PortfolioManager:
    """
    Portfólió kezelő – több pozíció, dinamikus méret, rebalancing.
    """

    def __init__(self):
        self._load_state()
        logger.info(
            f"💼 Portfólió kezelő inicializálva | "
            f"Pozíciók: {len(self.positions)}/{MAX_POSITIONS} | "
            f"Szabad tőke: ${self.free_capital:.2f}"
        )

    def _load_state(self):
        """Betölti az előző állapotot."""
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, "r") as f:
                    state = json.load(f)
                self.positions    = state["positions"]
                self.free_capital = state["free_capital"]
                self.allocations  = state["allocations"]
                logger.info("📂 Portfólió állapot betöltve.")
                return
            except Exception:
                pass

        # Új portfólió
        self.positions    = {}     # {"BTC/USDT": {"amount": 0.001, "entry": 77349, "allocated": 500}}
        self.free_capital = TOTAL_CAPITAL
        self.allocations  = {}     # {"BTC/USDT": 0.30} – célzott allokáció

    def _save_state(self):
        """Elmenti az aktuális állapotot."""
        state = {
            "positions":    self.positions,
            "free_capital": self.free_capital,
            "allocations":  self.allocations,
        }
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def can_open_position(self, symbol: str) -> bool:
        """
        Megvizsgálja nyitható-e új pozíció.
        """
        # Már van pozíció ebben a coinban?
        if symbol in self.positions:
            logger.info(f"💼 Már van nyitott pozíció: {symbol}")
            return False

        # Max pozíció elérve?
        if len(self.positions) >= MAX_POSITIONS:
            logger.info(
                f"💼 Max pozíció elérve "
                f"({len(self.positions)}/{MAX_POSITIONS})"
            )
            return False

        # Van elég szabad tőke?
        min_capital = TOTAL_CAPITAL * MIN_POSITION_PCT
        if self.free_capital < min_capital:
            logger.info(
                f"💼 Nincs elég szabad tőke: "
                f"${self.free_capital:.2f} < ${min_capital:.2f}"
            )
            return False

        return True

    def get_position_size(self, symbol: str,
                          current_price: float,
                          buy_votes: int,
                          confidence: float) -> float:
        """
        Kiszámítja az optimális pozícióméret.
        Erősebb jel → nagyobb pozíció.
        """
        # Alap allokáció: szabad tőke 20%-a
        base_allocation = self.free_capital * 0.20

        # Jel erőssége alapján skálázás
        signal_strength = (buy_votes / 6) * (confidence / 100)

        # 0.15 – 0.30 közötti allokáció
        allocation_pct  = 0.15 + (signal_strength * 0.15)
        allocation_pct  = min(allocation_pct, MAX_POSITION_PCT)

        allocated_usd   = TOTAL_CAPITAL * allocation_pct
        allocated_usd   = min(allocated_usd, self.free_capital)

        # Összeg → mennyiség
        amount = allocated_usd / current_price

        # Binance minimum kereskedési méret (BTC: 0.00001)
        amount = max(amount, 0.00001)
        amount = round(amount, 5)

        logger.info(
            f"💼 Pozícióméret: {amount} {symbol} | "
            f"${allocated_usd:.2f} ({allocation_pct:.0%}) | "
            f"Jelerő: {signal_strength:.2f}"
        )
        return amount

    def open_position(self, symbol: str, price: float,
                      amount: float):
        """Megnyit egy pozíciót."""
        allocated = price * amount
        self.positions[symbol] = {
            "amount":    amount,
            "entry":     price,
            "allocated": allocated,
        }
        self.free_capital -= allocated
        self.allocations[symbol] = allocated / TOTAL_CAPITAL
        self._save_state()

        logger.info(
            f"💼 Pozíció megnyitva: {symbol} | "
            f"{amount} @ ${price:.2f} | "
            f"Allokáció: ${allocated:.2f} | "
            f"Szabad tőke: ${self.free_capital:.2f}"
        )

    def close_position(self, symbol: str, price: float):
        """Lezár egy pozíciót."""
        if symbol not in self.positions:
            return None

        position   = self.positions[symbol]
        revenue    = price * position["amount"]
        profit     = revenue - position["allocated"]
        profit_pct = (profit / position["allocated"]) * 100

        self.free_capital += revenue
        del self.positions[symbol]
        if symbol in self.allocations:
            del self.allocations[symbol]

        self._save_state()

        logger.info(
            f"💼 Pozíció lezárva: {symbol} | "
            f"{position['amount']} @ ${price:.2f} | "
            f"Profit: {profit_pct:+.2f}% (${profit:+.2f}) | "
            f"Szabad tőke: ${self.free_capital:.2f}"
        )
        return profit_pct

    def get_portfolio_value(self, current_prices: dict) -> float:
        """Kiszámítja a teljes portfólió értékét."""
        total = self.free_capital
        for symbol, pos in self.positions.items():
            price  = current_prices.get(symbol, pos["entry"])
            total += pos["amount"] * price
        return total

    def needs_rebalancing(self, current_prices: dict) -> bool:
        """Megnézi kell-e rebalancing."""
        if not self.positions:
            return False

        portfolio_value = self.get_portfolio_value(current_prices)

        for symbol, pos in self.positions.items():
            price           = current_prices.get(symbol, pos["entry"])
            current_value   = pos["amount"] * price
            current_pct     = current_value / portfolio_value
            target_pct      = self.allocations.get(symbol, MAX_POSITION_PCT)

            if abs(current_pct - target_pct) > REBALANCE_THRESHOLD:
                logger.info(
                    f"💼 Rebalancing szükséges: {symbol} | "
                    f"Jelenlegi: {current_pct:.1%} | "
                    f"Célzott: {target_pct:.1%}"
                )
                return True
        return False

    def get_status(self, current_prices: dict = None) -> dict:
        """Visszaadja a portfólió aktuális állapotát."""
        current_prices  = current_prices or {}
        portfolio_value = self.get_portfolio_value(current_prices)

        positions_info = []
        for symbol, pos in self.positions.items():
            price      = current_prices.get(symbol, pos["entry"])
            value      = pos["amount"] * price
            pnl        = ((price - pos["entry"]) / pos["entry"]) * 100
            positions_info.append({
                "symbol":  symbol,
                "amount":  pos["amount"],
                "entry":   pos["entry"],
                "current": price,
                "value":   value,
                "pnl_pct": pnl,
            })

        return {
            "portfolio_value": portfolio_value,
            "free_capital":    self.free_capital,
            "positions":       positions_info,
            "n_positions":     len(self.positions),
            "max_positions":   MAX_POSITIONS,
        }

    def print_status(self, current_prices: dict = None):
        """Kiírja a portfólió állapotát."""
        s = self.get_status(current_prices)
        print(f"\n{'='*50}")
        print(f"  💼 PORTFÓLIÓ ÁLLAPOT")
        print(f"{'='*50}")
        print(f"  Teljes értéke:    ${s['portfolio_value']:>10.2f}")
        print(f"  Szabad tőke:      ${s['free_capital']:>10.2f}")
        print(f"  Nyitott pozíciók: {s['n_positions']}/{s['max_positions']}")
        if s["positions"]:
            print(f"{'─'*50}")
            for p in s["positions"]:
                sign = "+" if p["pnl_pct"] >= 0 else ""
                print(
                    f"  {p['symbol']:<12} | "
                    f"{p['amount']} db | "
                    f"${p['current']:.2f} | "
                    f"{sign}{p['pnl_pct']:.2f}%"
                )
        print(f"{'='*50}\n")