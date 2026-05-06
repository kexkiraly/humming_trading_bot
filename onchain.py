# ============================================================
# onchain.py – On-chain adatok elemzése
# ============================================================

import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
logger = logging.getLogger(__name__)

GLASSNODE_KEY = os.getenv("GLASSNODE_API_KEY", "")


# ============================================================
# 1. Blockchain.info – Ingyenes, nem kell API kulcs
# ============================================================

def get_mempool_stats() -> dict:
    """
    Lekéri a Bitcoin mempool állapotát.
    Ha sok tranzakció vár → aktív piac → bullish jel
    """
    try:
        url      = "https://mempool.space/api/mempool"
        response = requests.get(url, timeout=5)
        data     = response.json()

        tx_count  = data.get("count", 0)
        total_fee = data.get("total_fee", 0)

        # Átlagos mempool méret: ~5000-10000 tx
        if tx_count > 15000:
            signal = "bullish"    # nagyon aktív piac
        elif tx_count < 3000:
            signal = "bearish"    # inaktív piac
        else:
            signal = "neutral"

        logger.info(
            f"⛓️  Mempool: {tx_count:,} tranzakció | "
            f"Signal: {signal}"
        )
        return {
            "tx_count":  tx_count,
            "total_fee": total_fee,
            "signal":    signal,
        }
    except Exception as e:
        logger.error(f"Mempool hiba: {e}")
        return {"tx_count": 0, "signal": "neutral"}


def get_blockchain_stats() -> dict:
    """
    Lekéri az általános blockchain statisztikákat.
    """
    try:
        url      = "https://blockchain.info/stats?format=json"
        response = requests.get(url, timeout=5)
        data     = response.json()

        hash_rate      = data.get("hash_rate", 0)
        difficulty     = data.get("difficulty", 0)
        n_tx           = data.get("n_tx", 0)
        total_btc_sent = data.get("total_btc_sent", 0)

        # Hash rate trend – ha növekszik → egészséges hálózat
        signal = "bullish" if hash_rate > 500000000 else "neutral"

        logger.info(
            f"⛓️  Blockchain stats | "
            f"Hash rate: {hash_rate:,.0f} | "
            f"Tranzakciók: {n_tx:,}"
        )
        return {
            "hash_rate":      hash_rate,
            "difficulty":     difficulty,
            "n_tx":           n_tx,
            "btc_sent":       total_btc_sent,
            "signal":         signal,
        }
    except Exception as e:
        logger.error(f"Blockchain stats hiba: {e}")
        return {"signal": "neutral"}


# ============================================================
# 2. Glassnode – Exchange flow (API kulcs kell)
# ============================================================

def get_exchange_flow() -> dict:
    """
    CoinGecko ingyenes API – BTC exchange adatok.
    Nem kell API kulcs!
    """
    try:
        url      = "https://api.coingecko.com/api/v3/coins/bitcoin"
        params   = {
            "localization":   "false",
            "tickers":        "false",
            "market_data":    "true",
            "community_data": "false",
            "developer_data": "false",
        }
        response = requests.get(url, params=params, timeout=10)
        data     = response.json()

        market   = data.get("market_data", {})

        # 24 órás ár változás
        price_change_24h = market.get(
            "price_change_percentage_24h", 0
        )
        # Volumen változás
        volume_24h = market.get(
            "total_volume", {}
        ).get("usd", 0)

        # Ha nagy volumen + pozitív ár → bullish
        if price_change_24h > 2 and volume_24h > 30_000_000_000:
            signal = "bullish"
        elif price_change_24h < -2:
            signal = "bearish"
        else:
            signal = "neutral"

        logger.info(
            f"⛓️  CoinGecko: 24h változás: {price_change_24h:+.2f}% | "
            f"Volumen: ${volume_24h/1e9:.1f}B | "
            f"Signal: {signal}"
        )
        return {
            "price_change_24h": price_change_24h,
            "volume_24h":       volume_24h,
            "signal":           signal,
            "net_flow":         0,
        }

    except Exception as e:
        logger.error(f"CoinGecko hiba: {e}")
        return {"signal": "neutral", "net_flow": 0}


def get_whale_alert() -> dict:
    """
    Egyszerű whale detektálás a mempool nagy tranzakcióiból.
    """
    try:
        url      = "https://mempool.space/api/mempool/recent"
        response = requests.get(url, timeout=5)
        txs      = response.json()

        # Nagy tranzakciók megszámlálása (>10 BTC)
        large_txs = 0
        for tx in txs:
            value = tx.get("value", 0)
            if value > 1_000_000_000:  # satoshi-ban (10 BTC = 1B satoshi)
                large_txs += 1

        if large_txs > 5:
            signal = "bearish"    # sok nagy whale mozgás → eladás?
        elif large_txs == 0:
            signal = "bullish"    # nincs nagy mozgás → stabil
        else:
            signal = "neutral"

        logger.info(
            f"🐋 Whale alert: {large_txs} nagy tranzakció | "
            f"Signal: {signal}"
        )
        return {"large_txs": large_txs, "signal": signal}

    except Exception as e:
        logger.error(f"Whale alert hiba: {e}")
        return {"large_txs": 0, "signal": "neutral"}


# ============================================================
# Fő összesítő függvény
# ============================================================

def get_onchain_signal() -> dict:
    """
    Összesíti az összes on-chain jelet.
    Visszaad egy végső bullish/bearish/neutral jelzést.
    """
    mempool    = get_mempool_stats()
    blockchain = get_blockchain_stats()
    ex_flow    = get_exchange_flow()
    whale      = get_whale_alert()

    # Szavazás
    buy_score  = 0
    sell_score = 0

    for result in [mempool, blockchain, ex_flow, whale]:
        signal = result.get("signal", "neutral")
        if signal == "bullish":
            buy_score  += 1
        elif signal == "bearish":
            sell_score += 1

    if buy_score > sell_score:
        final_signal = "bullish"
        score        = buy_score
    elif sell_score > buy_score:
        final_signal = "bearish"
        score        = -sell_score
    else:
        final_signal = "neutral"
        score        = 0

    logger.info(
        f"⛓️  On-chain összesítés | "
        f"{'🟢' if final_signal == 'bullish' else '🔴' if final_signal == 'bearish' else '⚪'} "
        f"{final_signal} | "
        f"Score: {score:+d}"
    )

    return {
        "signal":     final_signal,
        "score":      score,
        "mempool":    mempool,
        "blockchain": blockchain,
        "ex_flow":    ex_flow,
        "whale":      whale,
    }