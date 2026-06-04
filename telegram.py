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

# Colored-circle headers for resolution events. Entry events (PAPER-TRADE /
# LIVE-TRADE) instead use a [TAG] DIRECTION header — see format_trade_card.
_RESOLUTION_EMOJI = {"WIN": "🟢", "LOSS": "🔴", "STOP": "🟡"}


def _post(text: str) -> None:
    """Send a pre-formatted message. Network/HTTP errors are logged, never raised."""
    if not _ENABLED:
        return
    payload = {
        "chat_id": _CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(_URL, json=payload, timeout=(3, 8))
        if not r.ok:
            logger.warning("[TELEGRAM] notify failed (%s): %s", r.status_code, r.text[:160])
    except Exception as e:
        logger.warning("[TELEGRAM] notify error: %s", e)


def _num(val, spec: str) -> str:
    """Format a number defensively — fall back to str() rather than raise.
    Telegram formatting must never crash a trade/resolution path."""
    try:
        return format(float(val), spec)
    except (TypeError, ValueError):
        return "?" if val is None else str(val)


def _signed_dollar(val) -> str:
    """'+$19.85' / '-$5.00' — signed dollar amount, defensive against None."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "?"
    return f"{'+' if v >= 0 else '-'}${abs(v):.2f}"


def format_trade_card(event_type: str, *, direction=None, city=None, target_date=None,
                      entry_price=None, bucket_lo=None, bucket_hi=None,
                      bucket_unit="", edge=None, stake=None, pnl=None) -> str:
    """Build a Telegram trade card.

    Resolution events (WIN/LOSS/STOP) → colored-circle header, no direction.
    Entry events (PAPER-TRADE/LIVE-TRADE) → "[TAG] DIRECTION" header.

    Max Win (full $1 payout minus stake, matching static/js/app.js) is shown on
    every card. PnL is realized only at resolution, so it's shown only when passed.

        🟢 WIN — Paris (2026-06-04)

        🎯 Entry: 0.430
        Bucket: [19.5, 20.5]C
        Edge: -0.340
        Stake: $15.00
        Max Win: +$19.88
        PnL: +$19.85
    """
    emoji = _RESOLUTION_EMOJI.get(event_type)
    if emoji:
        header = f"{emoji} {event_type} — {city} ({target_date})"
    else:
        header = f"[{event_type}] {direction} — {city} ({target_date})"

    lines = [
        f"🎯 Entry: {_num(entry_price, '.3f')}",
        f"Bucket: [{bucket_lo}, {bucket_hi}]{bucket_unit}",
        f"Edge: {_num(edge, '+.3f')}",
        f"Stake: ${_num(stake, '.2f')}",
    ]
    # Max Win = full $1/share payout minus stake (profit if it resolves our way).
    try:
        if entry_price is not None and float(entry_price) > 0 and stake is not None:
            max_win = float(stake) / float(entry_price) - float(stake)
            lines.append(f"Max Win: +${max_win:.2f}")
    except (TypeError, ValueError):
        pass
    if pnl is not None:
        lines.append(f"PnL: {_signed_dollar(pnl)}")

    return f"{header}\n\n" + "\n".join(lines)


def send_trade_event(event_type: str, **fields) -> None:
    """Format and send a trade card. No-ops if disabled; never raises."""
    if not _ENABLED:
        return
    try:
        _post(format_trade_card(event_type, **fields))
    except Exception as e:
        logger.warning("[TELEGRAM] trade-event format/send failed: %s", e)


def send_telegram_notification(event_type: str, message: str) -> None:
    """Legacy raw sender: prefixes [event_type] to a free-form message."""
    _post(f"[{event_type}] {message}")
