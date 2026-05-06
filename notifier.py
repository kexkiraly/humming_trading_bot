# ============================================================
# notifier.py – Telegram értesítések kezelése
# ============================================================

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Fontos: Ellenőrizd a .env fájlban, hogy így vannak-e írva (kis/nagybetű)!
TELEGRAM_TOKEN = os.getenv("Telegram_API_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("Telegram_CHAT_ID")


def send_message(text: str):
    """
    Telegram üzenet küldése.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram nincs beállítva – üzenet kihagyva.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=payload, timeout=5)
        if response.status_code == 200:
            logger.debug(f"Telegram üzenet elküldve: {text}")
        else:
            logger.error(f"Telegram hiba: {response.status_code} – {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram kapcsolati hiba: {e}")


# Az utolsó feldolgozott üzenet ID-ja
_last_update_id = 0

def handle_telegram_commands():
    global _last_update_id

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": _last_update_id + 1, "timeout": 1}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        result = None

        for update in data.get("result", []):
            # Frissítjük az offset-et – így a következő hívás kihagyja ezt
            _last_update_id = update["update_id"]

            message = update.get("message", {})
            text    = message.get("text", "").strip().lower()
            chat_id = str(message.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text == "/stop":
                from guard import activate_kill_switch
                activate_kill_switch("Telegram parancs")
                send_message("🔴 <b>Kill switch bekapcsolva!</b>\nA bot leáll.")
                result = "stop"

            elif text == "/start":
                from guard import deactivate_kill_switch
                deactivate_kill_switch()
                send_message("✅ <b>Kill switch kikapcsolva!</b>\nA bot folytatja.")
                result = "start"

            elif text == "/status":
                result = "status"

        return result

    except Exception as e:
        logger.error(f"Telegram parancs hiba: {e}")
        return None