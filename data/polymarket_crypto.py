"""
Polymarket crypto Up/Down market fetcher and parser.

Fetches active hourly "Bitcoin/Ethereum Up or Down" markets and extracts
the reference price (what the asset must beat to resolve YES) and the
resolution timestamp.
"""
import re
import json
import logging
from datetime import datetime, timezone

import requests

from config import GAMMA_API, CLOB_API

logger = logging.getLogger(__name__)
TIMEOUT = 15

# Supported assets: display name → Deribit symbol
CRYPTO_ASSETS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
}

# Keywords that identify an Up/Down market
_UP_DOWN_KW = "up or down"


MIN_VOLUME_USDC = 1_000   # skip thin/empty markets


def fetch_crypto_markets() -> list[dict]:
    """
    Fetch active crypto Up/Down markets from Polymarket Gamma API.

    Only returns markets expiring within the next 24 hours with volume
    above MIN_VOLUME_USDC. This keeps the scan fast and focused on
    tradeable markets.

    Returns list of dicts:
        market_id, question, clob_token_yes,
        asset ('BTC'|'ETH'),
        end_time (ISO UTC string),
        volume_usdc
    """
    now_utc = datetime.now(timezone.utc)
    window_end = now_utc.strftime("%Y-%m-%dT%H:%M")
    # Only look at markets ending in the next 24 hours
    from datetime import timedelta
    cutoff_dt = now_utc + timedelta(hours=24)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M")

    all_markets = []
    batch = 500
    for offset in range(0, 5_000, batch):
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={
                    "active":     "true",
                    "closed":     "false",
                    "limit":      batch,
                    "offset":     offset,
                    "order":      "endDate",
                    "ascending":  "true",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_markets.extend(data)
            # Stop once all markets in this batch are past our 24h window
            if all(m.get("endDate", "") > cutoff_str for m in data):
                break
        except Exception as e:
            logger.warning("Gamma fetch failed (offset=%d): %s", offset, e)
            break

    candidates = [
        m for m in all_markets
        if _is_crypto_updown(m.get("question", ""))
        and float(m.get("volume", 0) or 0) >= MIN_VOLUME_USDC
    ]
    logger.info("Crypto Up/Down candidates: %d (next 24h, vol≥$%d)",
                len(candidates), MIN_VOLUME_USDC)

    results = []
    now_utc = datetime.now(timezone.utc)

    for m in candidates:
        question = m.get("question", "")
        asset = _parse_asset(question)
        if asset is None:
            continue

        end_time = m.get("endDate", "") or m.get("endDateIso", "")
        if not end_time:
            continue

        # Skip markets that have already closed
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if end_dt <= now_utc:
                continue
        except ValueError:
            continue

        volume = float(m.get("volume", 0) or 0)

        clob_token = ""
        toks = m.get("clobTokenIds") or m.get("clob_token_ids") or []
        if isinstance(toks, str):
            try:
                toks = json.loads(toks)
            except Exception:
                pass
        if isinstance(toks, list) and toks:
            clob_token = toks[0]

        market_id = m.get("conditionId") or m.get("id") or ""

        results.append({
            "market_id":      market_id,
            "question":       question,
            "clob_token_yes": clob_token,
            "asset":          asset,
            "end_time":       end_time,
            "volume_usdc":    volume,
            "market_type":    "crypto",
            # Use asset as city/icao for DB compatibility
            "city":           asset,
            "icao":           asset,
            "target_date":    end_time[:10],
            "bucket_lo":      None,
            "bucket_hi":      None,
            "bucket_unit":    "crypto",
        })

    logger.info("Crypto markets fetched: %d active", len(results))
    return results


def get_crypto_market_prices(market: dict) -> dict:
    """Get live CLOB prices for a crypto market."""
    from data.polymarket import get_market_prices
    return get_market_prices(market)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_crypto_updown(question: str) -> bool:
    ql = question.lower()
    return (
        _UP_DOWN_KW in ql
        and any(asset in ql for asset in CRYPTO_ASSETS)
    )


def _parse_asset(question: str) -> str | None:
    ql = question.lower()
    for name, symbol in CRYPTO_ASSETS.items():
        if name in ql:
            return symbol
    return None
