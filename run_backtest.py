# ============================================================
# run_backtest.py – Több paraméter kombinációval
# ============================================================

import logging
from exchange import Exchange
from backtester import Backtester

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

if __name__ == "__main__":
    print("🔬 Backtest motor indítása...")

    exchange   = Exchange()
    backtester = Backtester(exchange)

    results = []

    # Tesztelendő kombinációk
    configs = [
        {"symbol": "BTC/USDT", "timeframe": "1h",  "days": 90, "min_votes": 3},
        {"symbol": "BTC/USDT", "timeframe": "1h",  "days": 90, "min_votes": 4},
        {"symbol": "BTC/USDT", "timeframe": "4h",  "days": 90, "min_votes": 3},
        {"symbol": "BTC/USDT", "timeframe": "4h",  "days": 90, "min_votes": 4},
        {"symbol": "ETH/USDT", "timeframe": "1h",  "days": 90, "min_votes": 3},
        {"symbol": "ETH/USDT", "timeframe": "4h",  "days": 90, "min_votes": 3},
    ]

    for cfg in configs:
        result = backtester.run(**cfg, order_size=0.001)
        if result:
            results.append({**cfg, **result})

    # Összesített rangsor
    print("\n" + "="*65)
    print("  🏆 ÖSSZESÍTETT RANGSOR – Legjobb stratégiák")
    print("="*65)
    print(f"  {'Symbol':<12} {'TF':<5} {'Votes':<7} {'Hozam':>8} {'Win%':>7} {'vs B&H':>8}")
    print("─"*65)

    sorted_results = sorted(
        results, key=lambda x: x.get("total_return", 0), reverse=True
    )

    for r in sorted_results:
        sign = "+" if r.get("total_return", 0) >= 0 else ""
        bh   = r.get("bot_vs_bh", 0)
        bh_s = "+" if bh >= 0 else ""
        print(
            f"  {r['symbol']:<12} {r['timeframe']:<5} "
            f"{r['min_votes']}/6   "
            f"{sign}{r.get('total_return',0):>6.2f}%  "
            f"{r.get('win_rate',0):>5.1f}%  "
            f"{bh_s}{bh:>6.2f}%"
        )

    print("="*65)
    print("\n✅ Backtest kész!")