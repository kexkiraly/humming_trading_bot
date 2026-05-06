import os
from dotenv import load_dotenv

load_dotenv()

API_KEY       = os.getenv("BINANCE_API_KEY", "")
API_SECRET    = os.getenv("BINANCE_API_SECRET", "")
EXCHANGE_NAME = "binance"
# Multi-coin – Top 10 (stablecoinok és wrapped tokenek nélkül)
TRADING_PAIRS = [
    "BTC/USDT",   # Bitcoin
    "ETH/USDT",   # Ethereum
    "BNB/USDT",   # BNB
    "SOL/USDT",   # Solana
    "XRP/USDT",   # Ripple
    "ADA/USDT",   # Cardano
    "AVAX/USDT",  # Avalanche
    "DOGE/USDT",  # Dogecoin
    "DOT/USDT",   # Polkadot
    "POL/USDT", # Polygon
]
TRADING_PAIR = TRADING_PAIRS[0]  # visszafelé kompatibilitás miatt marad
ORDER_SIZE    = 0.001
LOOP_DELAY    = 5.0
BACKTEST_TIMEFRAME = "1h"   # backtest alapján legjobb
MAX_LOSS_PCT  = 0.02
TAKE_PROFIT   = 0.03
STOP_LOSS     = 0.015
SHORT_MA = 9    # kissé lassabb → kevesebb hamis jel
LONG_MA  = 25   # kissé lassabb → stabilabb trend jelzés
DRY_RUN       = True