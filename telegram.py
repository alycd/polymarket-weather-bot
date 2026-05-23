"""
Telegram notifications for trade events.
Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env.
Silently no-ops if either is missing.
"""
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
_ENABLED = bool(_TOKEN and _CHAT_ID)

if _ENABLED:
    _URL = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"


def send_telegram_notification(event_type: str, message: str) -> None:
    if not _ENABLED:
        return
    payload = {
        "chat_id": _CHAT_ID,
        "text": f"[{event_type}] {message}",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(_URL, json=payload, timeout=(3, 8))
        if not r.ok:
            logger.warning("[TELEGRAM] notify failed (%s): %s", r.status_code, r.text[:160])
    except Exception as e:
        logger.warning("[TELEGRAM] notify error: %s", e)
