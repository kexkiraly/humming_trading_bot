# ============================================================
# orderbook.py – Orderbook elemzés
# ============================================================

import logging

logger = logging.getLogger(__name__)

# Beállítások
ORDERBOOK_DEPTH    = 20    # hány szintet vizsgálunk
WALL_THRESHOLD     = 5.0   # ennyi BTC felett "nagy fal"
IMBALANCE_THRESHOLD = 1.5  # bid/ask arány ami jelzést ad


def analyze_orderbook(exchange, symbol: str) -> dict:
    """
    Lekéri és elemzi az orderbook-ot.
    Visszaad egy dict-et a következő infókkal:
    - bid_ask_ratio: vételi/eladási nyomás aránya
    - has_buy_wall: van-e nagy vételi fal
    - has_sell_wall: van-e nagy eladási fal
    - signal: "bullish", "bearish", vagy "neutral"
    - spread_pct: bid-ask spread %-ban
    """
    try:
        ob = exchange.client.fetch_order_book(
            symbol, limit=ORDERBOOK_DEPTH
        )

        bids = ob.get("bids", [])  # [[ár, mennyiség], ...]
        asks = ob.get("asks", [])  # [[ár, mennyiség], ...]

        if not bids or not asks:
            return _neutral_result()

        # --- Spread számítás ---
        best_bid   = bids[0][0]
        best_ask   = asks[0][0]
        spread_pct = ((best_ask - best_bid) / best_bid) * 100

        # --- Bid és ask oldal összesítése ---
        total_bid_volume = sum(b[1] for b in bids)
        total_ask_volume = sum(a[1] for a in asks)

        # Bid/Ask arány – ha > 1.5 → több a vevő → bullish
        bid_ask_ratio = (
            total_bid_volume / total_ask_volume
            if total_ask_volume > 0 else 1.0
        )

        # --- Nagy falak keresése ---
        max_bid_wall = max(b[1] for b in bids)
        max_ask_wall = max(a[1] for a in asks)

        has_buy_wall  = max_bid_wall >= WALL_THRESHOLD
        has_sell_wall = max_ask_wall >= WALL_THRESHOLD

        # A legnagyobb falak ára
        buy_wall_price  = next(
            (b[0] for b in bids if b[1] == max_bid_wall), 0
        )
        sell_wall_price = next(
            (a[0] for a in asks if a[1] == max_ask_wall), 0
        )

        # --- Order Flow Imbalance (OFI) ---
        # Felső 5 szint bid vs ask összehasonlítása
        top_bids = sum(b[1] for b in bids[:5])
        top_asks = sum(a[1] for a in asks[:5])
        ofi      = (top_bids - top_asks) / (top_bids + top_asks) if (top_bids + top_asks) > 0 else 0

        # --- Jelzés meghatározása ---
        buy_score  = 0
        sell_score = 0

        # Bid/Ask arány alapján
        if bid_ask_ratio >= IMBALANCE_THRESHOLD:
            buy_score  += 2
        elif bid_ask_ratio <= (1 / IMBALANCE_THRESHOLD):
            sell_score += 2

        # Nagy vételi fal → támasz → bullish
        if has_buy_wall and not has_sell_wall:
            buy_score  += 1
        elif has_sell_wall and not has_buy_wall:
            sell_score += 1

        # Order Flow Imbalance
        if ofi > 0.3:
            buy_score  += 1
        elif ofi < -0.3:
            sell_score += 1

        # Jelzés
        if buy_score > sell_score:
            signal = "bullish"
        elif sell_score > buy_score:
            signal = "bearish"
        else:
            signal = "neutral"

        result = {
            "symbol":           symbol,
            "signal":           signal,
            "bid_ask_ratio":    bid_ask_ratio,
            "ofi":              ofi,
            "total_bid_vol":    total_bid_volume,
            "total_ask_vol":    total_ask_volume,
            "has_buy_wall":     has_buy_wall,
            "has_sell_wall":    has_sell_wall,
            "buy_wall_price":   buy_wall_price,
            "buy_wall_size":    max_bid_wall,
            "sell_wall_price":  sell_wall_price,
            "sell_wall_size":   max_ask_wall,
            "spread_pct":       spread_pct,
            "buy_score":        buy_score,
            "sell_score":       sell_score,
        }

        logger.info(
            f"📖 Orderbook: {symbol} | "
            f"{'🟢' if signal == 'bullish' else '🔴' if signal == 'bearish' else '⚪'} "
            f"{signal} | "
            f"B/A arány: {bid_ask_ratio:.2f} | "
            f"OFI: {ofi:+.2f} | "
            f"Spread: {spread_pct:.3f}%"
        )

        if has_buy_wall:
            logger.info(
                f"  🏦 Vételi fal: {max_bid_wall:.2f} BTC "
                f"@ ${buy_wall_price:.2f}"
            )
        if has_sell_wall:
            logger.info(
                f"  🧱 Eladási fal: {max_ask_wall:.2f} BTC "
                f"@ ${sell_wall_price:.2f}"
            )

        return result

    except Exception as e:
        logger.error(f"Orderbook hiba ({symbol}): {e}")
        return _neutral_result()


def _neutral_result() -> dict:
    """Semleges eredmény hiba esetén."""
    return {
        "signal":        "neutral",
        "bid_ask_ratio": 1.0,
        "ofi":           0.0,
        "has_buy_wall":  False,
        "has_sell_wall": False,
        "spread_pct":    0.0,
        "buy_score":     0,
        "sell_score":    0,
    }