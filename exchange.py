# ============================================================
# exchange.py – Tőzsdei kapcsolat és szimulátor híd
# ============================================================

import ccxt
import logging
import os
from config import API_KEY, API_SECRET, EXCHANGE_NAME, DRY_RUN

logger = logging.getLogger(__name__)

class Exchange:
    def __init__(self):
        try:
            exchange_class = getattr(ccxt, EXCHANGE_NAME)
            self.client = exchange_class({
                "apiKey": API_KEY,
                "secret": API_SECRET,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                    "adjustForTimeDifference": True,
                },
            })
            
            # Testnet mód (opcionális, ha a tőzsde támogatja)
            self.client.set_sandbox_mode(True)
            self.dry_run = DRY_RUN

            # --- Szimulációhoz szükséges változók ---
            self.simulator = None
            self._last_price = {}

            if self.dry_run:
                logger.warning("⚠️ DRY RUN mód – valódi megbízás NEM kerül feladásra!")
            
            logger.info(f"✅ Exchange kapcsolódva: {EXCHANGE_NAME.upper()} [TESTNET]")

        except AttributeError:
            raise ValueError(f"Ismeretlen tőzsde: '{EXCHANGE_NAME}'.")
        except Exception as e:
            logger.error(f"Hiba a tőzsde inicializálásakor: {e}")
            raise

    def get_ohlcv(self, symbol, timeframe="1m", limit=50):
        try:
            return self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            logger.error(f"OHLCV hiba ({symbol}): {e}")
            return []

    def get_balance(self, currency="USDT"):
        try:
            balance = self.client.fetch_balance()
            return balance.get("free", {}).get(currency, 0.0)
        except Exception as e:
            logger.error(f"Egyenleg lekérési hiba: {e}")
            return 0.0

    def place_order(self, symbol, side, amount):
        if self.dry_run:
            # Ha van szimulátor csatolva, azt használjuk
            if hasattr(self, 'simulator') and self.simulator:
                # Lekérjük az utolsó ismert árat a szimulált vételhez/eladáshoz
                price = self._last_price.get(symbol, 0)
                if price == 0:
                    # Ha még nincs ár, megpróbáljuk gyorsan lekérni
                    ticker = self.get_ticker(symbol)
                    price = ticker.get("last", 0)

                if side == "buy":
                    return self.simulator.buy(symbol, price, amount)
                else:
                    return self.simulator.sell(symbol, price, amount)
            
            # Ha nincs szimulátor, csak logolunk
            logger.info(f"[DRY RUN] 📋 Szimulált megbízás: {side.upper()} {amount} {symbol}")
            return {"status": "simulated", "side": side, "amount": amount}

        try:
            order = self.client.create_market_order(symbol, side, amount)
            logger.info(f"✅ Megbízás: {side.upper()} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"❌ Megbízási hiba: {e}")
            return None

    def get_ticker(self, symbol):
        try:
            ticker = self.client.fetch_ticker(symbol)
            
            # Mentjük az árat, hogy a szimulátor tudjon számolni vele
            if ticker and "last" in ticker:
                self._last_price[symbol] = ticker["last"]
                
            return ticker
        except Exception as e:
            logger.error(f"Ticker hiba ({symbol}): {e}")
            return {}