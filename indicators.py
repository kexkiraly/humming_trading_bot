import requests
import logging

logger = logging.getLogger(__name__)

def get_fear_and_greed():
    """Fear & Greed index lekérése."""
    try:
        url = "https://api.alternative.me/fng/"
        response = requests.get(url, timeout=5)
        data = response.json()
        val = int(data['data'][0]['value'])
        label = data['data'][0]['value_classification']
        return {"value": val, "label": label}
    except Exception as e:
        logger.error(f"Fear & Greed hiba: {e}")
        return {"value": 50, "label": "Neutral"}

def get_enhanced_sentiment():
    """
    Hírek és hangulat elemzése. 
    (Itt most egy egyszerűsített verzió van, ami a F&G-re alapoz, 
    de a stratégia már várja ezt a függvényt.)
    """
    fng = get_fear_and_greed()
    score = 0
    if fng["value"] > 70: score = 10  # Nagyon bullish
    elif fng["value"] < 30: score = -10 # Nagyon bearish
    
    return {
        "bullish": 50 + (fng["value"] - 50),
        "bearish": 50 - (fng["value"] - 50),
        "score": score
    }

def get_market_alerts():
    """
    Piaci riasztások (pl. extrém mozgások).
    Egyelőre üres listát adunk vissza, hogy ne dobjon hibát.
    """
    return []
# On-chain integráció
_onchain_available = False
try:
    from onchain import get_onchain_signal
    _onchain_available = True
    logger.info("✅ On-chain modul betöltve.")
except Exception:
    logger.info("ℹ️  On-chain modul nem elérhető.")


def get_onchain_data() -> dict:
    """
    On-chain adatok lekérése.
    Ha nem elérhető → semleges értéket ad vissza.
    """
    if _onchain_available:
        return get_onchain_signal()
    return {"signal": "neutral", "score": 0}