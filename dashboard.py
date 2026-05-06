# ============================================================
# dashboard.py – Web dashboard Flask szerverrel
# ============================================================

from flask import Flask, jsonify, render_template
from database import get_stats
import sqlite3
import logging

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)  # Flask saját logjait elnyomjuk

app = Flask(__name__)
DB_FILE = "trades.db"

# Ez a változó tárolja az aktuális piaci adatokat
# A strategy.py frissíti majd
live_data = {
    "price":          0.0,
    "rsi":            0.0,
    "macd":           0.0,
    "volume_ratio":   0.0,
    "fg_value":       50,
    "fg_label":       "Neutral",
    "buy_votes":      0,
    "sell_votes":     0,
    "in_position":    False,
    "entry_price":    0.0,
    "current_symbol": "—",
    "status":         "Fut ✅",
    "kill_switch":    False,
    "circuit_breaker": False,
    "daily_trades":   0,
    "daily_loss":     0.0,
    "top_coins":      [],
    "sim_portfolio":  10000.0,
    "sim_return":     0.0,
    "sim_win_rate":   0.0,
    "sim_drawdown":   0.0,
    "sim_vs_bh":      0.0,
    "regime":     "unknown",
    "regime_desc": "",
    "adx":        0.0,
}


@app.route("/")
def index():
    """Főoldal – a dashboard HTML-je."""
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Statisztikák API végpont."""
    return jsonify(get_stats())


@app.route("/api/live")
def api_live():
    """Valós idejű piaci adatok API végpont."""
    return jsonify(live_data)


@app.route("/api/trades")
def api_trades():
    """Legutóbbi 20 megbízás API végpont."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, symbol, side, price, amount, profit_pct
            FROM trades
            ORDER BY id DESC
            LIMIT 20
        """)
        rows = cursor.fetchall()
        conn.close()

        trades = []
        for row in rows:
            trades.append({
                "timestamp":  row[0],
                "symbol":     row[1],
                "side":       row[2],
                "price":      row[3],
                "amount":     row[4],
                "profit_pct": row[5],
            })
        return jsonify(trades)
    except Exception as e:
        return jsonify([])


def run_dashboard():
    """Dashboard szerver indítása háttérben."""
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)