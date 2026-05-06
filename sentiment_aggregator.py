# ============================================================
# sentiment_aggregator.py – Sentiment összesítő
# ============================================================

import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SENTIMENT_LOG = "sentiment_log.json"

# --- Súlyok (összeadva 100%) ---
WEIGHTS = {
    "fear_greed":  0.25,   # Fear & Greed Index
    "news":        0.20,   # Google News RSS
    "onchain":     0.25,   # On-chain adatok
    "orderbook":   0.30,   # Orderbook (leghasznosabb)
}


def normalize_fear_greed(value: int) -> float:
    """
    Fear & Greed értéket (-1, +1) skálára normalizál.
    0   = extrém félelem  → -1.0 (bearish)
    50  = semleges        →  0.0
    100 = extrém kapzsiság → +1.0 (bullish)
    """
    return (value - 50) / 50.0


def normalize_news_score(score: int) -> float:
    """
    News score-t (-1, +1) skálára normalizál.
    ±20 felett telítési szint.
    """
    return max(-1.0, min(1.0, score / 20.0))


def normalize_onchain_score(score: int) -> float:
    """
    On-chain score-t (-1, +1) skálára normalizál.
    Max ±4 pont lehetséges.
    """
    return max(-1.0, min(1.0, score / 4.0))


def normalize_orderbook(bid_ask_ratio: float, ofi: float) -> float:
    """
    Orderbook adatokat (-1, +1) skálára normalizál.
    """
    # B/A arány: 1.0 = semleges, 2.0 = erősen bullish
    ba_score = max(-1.0, min(1.0, (bid_ask_ratio - 1.0)))
    # OFI: már -1 és +1 között van
    ofi_score = max(-1.0, min(1.0, ofi))
    return (ba_score + ofi_score) / 2.0


class SentimentAggregator:
    """
    Összegyűjti és súlyozza az összes sentiment forrást.
    Egyetlen megbízható jelzést ad vissza.
    """

    def __init__(self):
        self.history = []
        logger.info("📡 Sentiment Aggregátor inicializálva.")

    def aggregate(self,
                  fear_greed_value: int = 50,
                  news_score: int       = 0,
                  onchain_score: int    = 0,
                  ob_bid_ask_ratio: float = 1.0,
                  ob_ofi: float           = 0.0) -> dict:
        """
        Összesíti az összes sentiment jelet.
        Visszaad egy dict-et a végső jelzéssel és részletekkel.
        """

        # --- Normalizálás ---
        fg_norm = normalize_fear_greed(fear_greed_value)
        news_norm = normalize_news_score(news_score)
        oc_norm   = normalize_onchain_score(onchain_score)
        ob_norm   = normalize_orderbook(ob_bid_ask_ratio, ob_ofi)

        # --- Súlyozott összesítés ---
        weighted_score = (
            fg_norm   * WEIGHTS["fear_greed"] +
            news_norm * WEIGHTS["news"]       +
            oc_norm   * WEIGHTS["onchain"]    +
            ob_norm   * WEIGHTS["orderbook"]
        )

        # --- Jelzés meghatározása ---
        if weighted_score >= 0.2:
            signal   = "bullish"
            strength = "erős" if weighted_score >= 0.4 else "gyenge"
        elif weighted_score <= -0.2:
            signal   = "bearish"
            strength = "erős" if weighted_score <= -0.4 else "gyenge"
        else:
            signal   = "neutral"
            strength = "semleges"

        # --- Konfidencia számítás ---
        # Minél jobban egyeznek a források, annál magasabb
        scores     = [fg_norm, news_norm, oc_norm, ob_norm]
        positives  = sum(1 for s in scores if s > 0.1)
        negatives  = sum(1 for s in scores if s < -0.1)
        agreement  = max(positives, negatives) / len(scores)
        confidence = agreement * 100

        result = {
            "signal":         signal,
            "strength":       strength,
            "weighted_score": weighted_score,
            "confidence":     confidence,
            "sources": {
                "fear_greed": {
                    "raw":        fear_greed_value,
                    "normalized": fg_norm,
                    "weight":     WEIGHTS["fear_greed"],
                },
                "news": {
                    "raw":        news_score,
                    "normalized": news_norm,
                    "weight":     WEIGHTS["news"],
                },
                "onchain": {
                    "raw":        onchain_score,
                    "normalized": oc_norm,
                    "weight":     WEIGHTS["onchain"],
                },
                "orderbook": {
                    "bid_ask":    ob_bid_ask_ratio,
                    "ofi":        ob_ofi,
                    "normalized": ob_norm,
                    "weight":     WEIGHTS["orderbook"],
                },
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # --- Naplózás ---
        emoji = "🟢" if signal == "bullish" else "🔴" if signal == "bearish" else "⚪"
        logger.info(
            f"📡 Sentiment: {emoji} {signal.upper()} ({strength}) | "
            f"Score: {weighted_score:+.3f} | "
            f"Konfidencia: {confidence:.0f}% | "
            f"F&G: {fg_norm:+.2f} | "
            f"News: {news_norm:+.2f} | "
            f"OnChain: {oc_norm:+.2f} | "
            f"OB: {ob_norm:+.2f}"
        )

        # --- Előzmény mentése ---
        self._save_to_history(result)

        return result

    def _save_to_history(self, result: dict):
        """Elmenti a sentiment előzményt fájlba."""
        try:
            history = []
            if os.path.exists(SENTIMENT_LOG):
                with open(SENTIMENT_LOG, "r") as f:
                    history = json.load(f)

            # Csak a lényeges adatokat mentjük
            history.append({
                "timestamp":      result["timestamp"],
                "signal":         result["signal"],
                "weighted_score": result["weighted_score"],
                "confidence":     result["confidence"],
            })

            # Max 1000 bejegyzés
            if len(history) > 1000:
                history = history[-1000:]

            with open(SENTIMENT_LOG, "w") as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            logger.error(f"Sentiment log mentési hiba: {e}")

    def get_trend(self, last_n: int = 10) -> str:
        """
        Megnézi az utolsó N sentiment jelzést.
        Ha egyre bullishabb → 'improving'
        Ha egyre bearishabb → 'deteriorating'
        """
        try:
            if not os.path.exists(SENTIMENT_LOG):
                return "unknown"

            with open(SENTIMENT_LOG, "r") as f:
                history = json.load(f)

            if len(history) < last_n:
                return "unknown"

            recent = history[-last_n:]
            scores = [r["weighted_score"] for r in recent]

            # Lineáris trend
            first_half = sum(scores[:last_n//2]) / (last_n//2)
            second_half = sum(scores[last_n//2:]) / (last_n//2)

            diff = second_half - first_half

            if diff > 0.1:
                return "improving"
            elif diff < -0.1:
                return "deteriorating"
            else:
                return "stable"

        except Exception as e:
            logger.error(f"Trend számítási hiba: {e}")
            return "unknown"

    def print_summary(self, result: dict):
        """Kiírja az összesítést szépen formázva."""
        print(f"\n{'='*55}")
        print(f"  📡 SENTIMENT ÖSSZESÍTŐ")
        print(f"{'='*55}")

        emoji = "🟢" if result["signal"] == "bullish" else \
                "🔴" if result["signal"] == "bearish" else "⚪"
        print(
            f"  Végső jelzés:   {emoji} "
            f"{result['signal'].upper()} ({result['strength']})"
        )
        print(f"  Súlyozott score: {result['weighted_score']:>+.3f}")
        print(f"  Konfidencia:     {result['confidence']:.0f}%")
        print(f"{'─'*55}")
        print(f"  {'Forrás':<15} {'Súly':>6} {'Norm.':>8} {'Raw':>10}")
        print(f"{'─'*55}")

        s = result["sources"]
        print(
            f"  {'Fear&Greed':<15} "
            f"{s['fear_greed']['weight']:>5.0%} "
            f"{s['fear_greed']['normalized']:>+8.2f} "
            f"{s['fear_greed']['raw']:>10}"
        )
        print(
            f"  {'News':<15} "
            f"{s['news']['weight']:>5.0%} "
            f"{s['news']['normalized']:>+8.2f} "
            f"{s['news']['raw']:>10}"
        )
        print(
            f"  {'On-chain':<15} "
            f"{s['onchain']['weight']:>5.0%} "
            f"{s['onchain']['normalized']:>+8.2f} "
            f"{s['onchain']['raw']:>10}"
        )
        print(
            f"  {'Orderbook':<15} "
            f"{s['orderbook']['weight']:>5.0%} "
            f"{s['orderbook']['normalized']:>+8.2f} "
            f"B/A:{s['orderbook']['bid_ask']:>5.2f}"
        )
        print(f"{'='*55}\n")