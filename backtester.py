# ============================================================
# backtester.py – Historikus adatokon való stratégia tesztelés
# ============================================================

import logging
import pandas as pd
import pandas_ta as ta
import sqlite3
import json
from datetime import datetime, timedelta
from config import SHORT_MA, LONG_MA, STOP_LOSS, TAKE_PROFIT

logger = logging.getLogger(__name__)

BACKTEST_DB   = "backtest.db"
TRADING_FEE   = 0.001    # 0.1%
SLIPPAGE      = 0.0005   # 0.05%
STARTING_CASH = 10000.0  # induló virtuális egyenleg


# ============================================================
# Adatbázis
# ============================================================

def init_backtest_db():
    conn   = sqlite3.connect(BACKTEST_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT NOT NULL,
            symbol         TEXT NOT NULL,
            timeframe      TEXT NOT NULL,
            period_days    INTEGER NOT NULL,
            total_trades   INTEGER,
            winning_trades INTEGER,
            win_rate       REAL,
            total_return   REAL,
            max_drawdown   REAL,
            sharpe_ratio   REAL,
            buy_hold_return REAL,
            params         TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL,
            timestamp   TEXT NOT NULL,
            side        TEXT NOT NULL,
            price       REAL NOT NULL,
            amount      REAL NOT NULL,
            profit_pct  REAL,
            balance     REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ============================================================
# Historikus adatok letöltése
# ============================================================

def fetch_historical_data(exchange_client, symbol: str,
                          timeframe: str = "1h",
                          days: int = 90) -> pd.DataFrame:
    """
    Letölti a historikus adatokat az éles Binance-ről.
    Publikus endpoint – nem kell API kulcs!
    """
    import ccxt
    logger.info(
        f"📥 Historikus adatok letöltése: {symbol} | "
        f"{timeframe} | {days} nap..."
    )

    # Éles Binance publikus adatok (nem Testnet!)
    public_exchange = ccxt.binance({
        "enableRateLimit": True,
    })

    since = int(
        (datetime.now() - timedelta(days=days)).timestamp() * 1000
    )
    all_candles = []
    limit       = 500

    while True:
        try:
            candles = public_exchange.fetch_ohlcv(
                symbol, timeframe=timeframe,
                since=since, limit=limit
            )
            if not candles:
                break

            all_candles.extend(candles)
            since = candles[-1][0] + 1

            if len(candles) < limit:
                break

        except Exception as e:
            logger.error(f"Letöltési hiba: {e}")
            break

    if not all_candles:
        logger.error("Nem sikerült adatot letölteni!")
        return pd.DataFrame()

    df = pd.DataFrame(
        all_candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    df = df[~df.index.duplicated(keep="first")]

    logger.info(f"✅ {len(df)} gyertya letöltve ({symbol})")
    return df


# ============================================================
# Indikátorok számítása
# ============================================================

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Kiszámítja az összes indikátort a DataFrame-re."""
    df = df.copy()

    # Mozgóátlagok
    df[f"ma_{SHORT_MA}"] = df["close"].rolling(window=SHORT_MA).mean()
    df[f"ma_{LONG_MA}"]  = df["close"].rolling(window=LONG_MA).mean()

    # RSI
    df["rsi"] = ta.rsi(df["close"], length=14)

    # MACD
    macd_df        = ta.macd(df["close"])
    df["macd"]     = macd_df["MACD_12_26_9"]
    df["macd_sig"] = macd_df["MACDs_12_26_9"]

    # Bollinger Bands
    bb_df = ta.bbands(df["close"], length=20)
    bb_upper_col = [c for c in bb_df.columns if c.startswith("BBU")][0]
    bb_lower_col = [c for c in bb_df.columns if c.startswith("BBL")][0]
    df["bb_upper"] = bb_df[bb_upper_col]
    df["bb_lower"] = bb_df[bb_lower_col]

    # Volume arány
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

    # NaN sorok eltávolítása
    df = df.dropna()
    return df


# ============================================================
# Szavazás egy gyertyán
# ============================================================

def get_votes(row, fear_greed: int = 50, news_score: int = 0) -> tuple:
    """
    Kiszámítja a vételi/eladási szavazatokat egy gyertyán.
    Visszaad: (buy_votes, sell_votes)
    """
    buy_votes  = 0
    sell_votes = 0

    # MA crossover
    if row[f"ma_{SHORT_MA}"] > row[f"ma_{LONG_MA}"]:
        buy_votes  += 1
    else:
        sell_votes += 1

    # RSI
    if row["rsi"] < 40:
        buy_votes  += 1
    elif row["rsi"] > 60:
        sell_votes += 1

    # MACD
    if row["macd"] > row["macd_sig"]:
        buy_votes  += 1
    elif row["macd"] < row["macd_sig"]:
        sell_votes += 1

    # Bollinger
    if row["close"] < row["bb_lower"]:
        buy_votes  += 1
    elif row["close"] > row["bb_upper"]:
        sell_votes += 1

    # Fear & Greed (statikus backtest során)
    if fear_greed < 35:
        buy_votes  += 1
    elif fear_greed > 65:
        sell_votes += 1

    # News score (statikus backtest során)
    if news_score > 5:
        buy_votes  += 1
    elif news_score < -5:
        sell_votes += 1

    return buy_votes, sell_votes


# ============================================================
# Fő backtester
# ============================================================

class Backtester:

    def __init__(self, exchange_client):
        self.exchange = exchange_client
        init_backtest_db()

    def run(self, symbol: str = "BTC/USDT",
            timeframe: str  = "1h",
            days: int       = 90,
            min_votes: int  = 4,
            order_size: float = 0.001,
            fear_greed: int = 50,
            news_score: int = 0) -> dict:
        """
        Lefuttatja a backtestet.
        Visszaadja a teljes statisztikát.
        """
        logger.info(
            f"\n{'='*50}\n"
            f"🔬 BACKTEST INDUL\n"
            f"   Symbol:    {symbol}\n"
            f"   Timeframe: {timeframe}\n"
            f"   Időszak:   {days} nap\n"
            f"   Min votes: {min_votes}/6\n"
            f"{'='*50}"
        )

        # Adatok letöltése
        df = fetch_historical_data(
            self.exchange.client, symbol, timeframe, days
        )
        if df.empty:
            logger.error("Nincs adat a backtesthez!")
            return {}

        # Indikátorok számítása
        df = calculate_indicators(df)
        logger.info(f"📊 {len(df)} gyertya elemzése...")

        # Változók inicializálása
        cash          = STARTING_CASH
        position      = None   # {"price": x, "amount": y}
        trades        = []
        peak_value    = STARTING_CASH
        max_drawdown  = 0.0
        equity_curve  = []

        # Buy & Hold számításhoz
        first_price   = df["close"].iloc[0]
        last_price    = df["close"].iloc[-1]
        bh_return     = ((last_price - first_price) / first_price) * 100

        # Gyertyánként végigmegyünk
        for timestamp, row in df.iterrows():
            price      = row["close"]
            buy_votes, sell_votes = get_votes(
                row, fear_greed, news_score
            )

            # Portfólió értéke
            portfolio_val = cash
            if position:
                portfolio_val += position["amount"] * price

            # Drawdown számítás
            peak_value   = max(peak_value, portfolio_val)
            drawdown     = (peak_value - portfolio_val) / peak_value * 100
            max_drawdown = max(max_drawdown, drawdown)

            equity_curve.append({
                "timestamp": str(timestamp),
                "value":     portfolio_val,
                "price":     price,
            })

            # --- Vételi logika ---
            if buy_votes >= min_votes and position is None:
                eff_price = price * (1 + SLIPPAGE)
                cost      = eff_price * order_size
                fee       = cost * TRADING_FEE
                total     = cost + fee

                if total <= cash:
                    cash    -= total
                    position = {
                        "price":  eff_price,
                        "amount": order_size,
                        "time":   str(timestamp)
                    }
                    trades.append({
                        "timestamp": str(timestamp),
                        "side":      "buy",
                        "price":     eff_price,
                        "amount":    order_size,
                        "profit_pct": None,
                        "balance":   cash,
                    })

            # --- Stop-loss ---
            elif position:
                change = (price - position["price"]) / position["price"]

                if change <= -STOP_LOSS:
                    eff_price  = price * (1 - SLIPPAGE)
                    revenue    = eff_price * position["amount"]
                    fee        = revenue * TRADING_FEE
                    net        = revenue - fee
                    profit_pct = ((net - position["price"] * position["amount"])
                                  / (position["price"] * position["amount"])) * 100
                    cash      += net
                    trades.append({
                        "timestamp":  str(timestamp),
                        "side":       "sell",
                        "price":      eff_price,
                        "amount":     position["amount"],
                        "profit_pct": profit_pct,
                        "balance":    cash,
                    })
                    position = None

                # --- Take-profit ---
                elif change >= TAKE_PROFIT:
                    eff_price  = price * (1 - SLIPPAGE)
                    revenue    = eff_price * position["amount"]
                    fee        = revenue * TRADING_FEE
                    net        = revenue - fee
                    profit_pct = ((net - position["price"] * position["amount"])
                                  / (position["price"] * position["amount"])) * 100
                    cash      += net
                    trades.append({
                        "timestamp":  str(timestamp),
                        "side":       "sell",
                        "price":      eff_price,
                        "amount":     position["amount"],
                        "profit_pct": profit_pct,
                        "balance":    cash,
                    })
                    position = None

                # --- Eladási jel ---
                elif sell_votes >= min_votes:
                    eff_price  = price * (1 - SLIPPAGE)
                    revenue    = eff_price * position["amount"]
                    fee        = revenue * TRADING_FEE
                    net        = revenue - fee
                    profit_pct = ((net - position["price"] * position["amount"])
                                  / (position["price"] * position["amount"])) * 100
                    cash      += net
                    trades.append({
                        "timestamp":  str(timestamp),
                        "side":       "sell",
                        "price":      eff_price,
                        "amount":     position["amount"],
                        "profit_pct": profit_pct,
                        "balance":    cash,
                    })
                    position = None

        # --- Végső statisztikák ---
        final_value = cash
        if position:
            final_value += position["amount"] * last_price

        sells        = [t for t in trades if t["side"] == "sell"]
        winners      = [t for t in sells if (t["profit_pct"] or 0) > 0]
        total_return = ((final_value - STARTING_CASH) / STARTING_CASH) * 100
        win_rate     = len(winners) / len(sells) * 100 if sells else 0

        # Sharpe ratio (egyszerűsített)
        if len(sells) > 1:
            returns     = [t["profit_pct"] for t in sells if t["profit_pct"]]
            avg_return  = sum(returns) / len(returns)
            std_return  = (sum((r - avg_return)**2 for r in returns)
                           / len(returns)) ** 0.5
            sharpe      = (avg_return / std_return) if std_return > 0 else 0
        else:
            sharpe = 0.0

        stats = {
            "symbol":          symbol,
            "timeframe":       timeframe,
            "period_days":     days,
            "candles":         len(df),
            "total_trades":    len(sells),
            "winning_trades":  len(winners),
            "win_rate":        win_rate,
            "total_return":    total_return,
            "final_value":     final_value,
            "max_drawdown":    max_drawdown,
            "sharpe_ratio":    sharpe,
            "buy_hold_return": bh_return,
            "bot_vs_bh":       total_return - bh_return,
        }

        # Mentés adatbázisba
        self._save_to_db(stats, trades)

        # Kiírás
        self._print_results(stats)

        return stats

    def _save_to_db(self, stats: dict, trades: list):
        """Elmenti az eredményeket az adatbázisba."""
        try:
            conn   = sqlite3.connect(BACKTEST_DB)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO backtest_runs
                (timestamp, symbol, timeframe, period_days,
                 total_trades, winning_trades, win_rate,
                 total_return, max_drawdown, sharpe_ratio,
                 buy_hold_return, params)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                stats["symbol"], stats["timeframe"],
                stats["period_days"], stats["total_trades"],
                stats["winning_trades"], stats["win_rate"],
                stats["total_return"], stats["max_drawdown"],
                stats["sharpe_ratio"], stats["buy_hold_return"],
                json.dumps({"short_ma": SHORT_MA, "long_ma": LONG_MA}),
            ))
            run_id = cursor.lastrowid

            for t in trades:
                cursor.execute("""
                    INSERT INTO backtest_trades
                    (run_id, timestamp, side, price, amount,
                     profit_pct, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, t["timestamp"], t["side"],
                    t["price"], t["amount"],
                    t.get("profit_pct"), t["balance"],
                ))
            conn.commit()
            conn.close()
            logger.info(f"💾 Backtest eredmény elmentve (ID: {run_id})")
        except Exception as e:
            logger.error(f"Backtest DB mentési hiba: {e}")

    def _print_results(self, s: dict):
        """Szépen kiírja az eredményeket."""
        print(f"\n{'='*55}")
        print(f"  🔬 BACKTEST EREDMÉNY – {s['symbol']} ({s['timeframe']})")
        print(f"{'='*55}")
        print(f"  Időszak:          {s['period_days']} nap | {s['candles']} gyertya")
        print(f"  Induló egyenleg:  ${STARTING_CASH:>10.2f}")
        print(f"  Végső egyenleg:   ${s['final_value']:>10.2f}")
        sign = "+" if s["total_return"] >= 0 else ""
        print(f"  Összes hozam:     {sign}{s['total_return']:>9.2f}%")
        print(f"{'─'*55}")
        print(f"  Összes trade:     {s['total_trades']:>10}")
        print(f"  Nyerő trade:      {s['winning_trades']:>10}")
        print(f"  Win rate:         {s['win_rate']:>9.1f}%")
        print(f"  Max drawdown:     {s['max_drawdown']:>9.2f}%")
        print(f"  Sharpe ratio:     {s['sharpe_ratio']:>9.2f}")
        print(f"{'─'*55}")
        print(f"  Buy & Hold:       {s['buy_hold_return']:>+9.2f}%")
        print(f"  Bot vs B&H:       {s['bot_vs_bh']:>+9.2f}%")
        verdict = "✅ Bot JOBB!" if s["bot_vs_bh"] > 0 else "❌ Bot ROSSZABB!"
        print(f"  Eredmény:         {verdict:>14}")
        print(f"{'='*55}\n")