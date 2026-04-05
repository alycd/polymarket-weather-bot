"""
CLOB price history scraper.

Fetches hourly price snapshots for all resolved + active temperature markets
and stores them in the price_history table for use in real backtests.

Run via: python main.py --scrape-prices
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date

import requests

import db
from config import GAMMA_API, CLOB_API, CITIES
from data.polymarket import parse_question, parse_clob_tokens

logger = logging.getLogger(__name__)

MAX_WORKERS = 8
FIDELITY_MINUTES = 60   # hourly snapshots — best balance of detail vs API load
MARKET_SHRINK = 0.30    # crowd model fallback constant (mirrors simulate.py)
CROWD_STD = 2.5


def _req(url, params=None, timeout=15):
    """GET with exponential backoff on 429/5xx."""
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(2)
    raise RuntimeError("Max retries exceeded")


def _collect_markets() -> list[dict]:
    """
    Collect token_id + market_id for all temp markets:
    - Resolved (closed=true, weather tag, past 90 days)
    - Active (currently open)
    Deduplicates by token_id.
    """
    today = date.today()
    batch = 500
    active_raw = []
    resolved_raw = []

    # Active markets FIRST — these always have price history
    for offset in range(0, 5000, batch):
        try:
            resp = _req(f"{GAMMA_API}/markets", params={
                "active": "true",
                "closed": "false",
                "limit": batch,
                "offset": offset,
            })
            data = resp.json()
        except Exception as e:
            logger.warning("Markets API error at offset=%d: %s", offset, e)
            break
        if not data:
            break
        active_raw.extend(data)
        if len(data) < batch:
            break

    # Resolved markets — ordered newest-first (closest to today = most likely to have history)
    for offset in range(0, 10000, batch):
        try:
            resp = _req(f"{GAMMA_API}/events", params={
                "active":    "false",
                "closed":    "true",
                "tag_slug":  "weather",
                "limit":     batch,
                "offset":    offset,
                "order":     "endDate",
                "ascending": "false",   # newest first
            })
            data = resp.json()
        except Exception as e:
            logger.warning("Events API error at offset=%d: %s", offset, e)
            break
        if not data:
            break
        for event in data:
            for m in event.get("markets", []):
                resolved_raw.append(m)
        if len(data) < batch:
            break

    # Active first so they are never cut off by the max_markets cap
    all_raw = active_raw + resolved_raw

    # Filter and deduplicate
    result = []
    seen_tokens = set()
    for m in all_raw:
        question = m.get("question", "")
        if not any(kw in question for kw in ["°F", "°C"]):
            continue

        tokens = parse_clob_tokens(m.get("clobTokenIds", "[]"))
        if not tokens:
            continue
        token = tokens[0]
        if token in seen_tokens:
            continue

        parsed_q = parse_question(question)
        if not parsed_q or parsed_q.get("city") not in CITIES:
            continue

        # Only within 90 days
        target_date = parsed_q.get("target_date")
        if target_date and (today - target_date).days > 90:
            continue

        seen_tokens.add(token)
        market_id = m.get("conditionId") or m.get("id", "")
        if market_id:
            result.append({"market_id": market_id, "token_id": token})

    return result


def _fetch_and_store_one(market_id: str, token_id: str) -> int:
    """
    Fetch full hourly CLOB price history for one token and store it.
    Returns number of new points stored.
    """
    try:
        resp = _req(f"{CLOB_API}/prices-history", params={
            "market":   token_id,
            "interval": "max",
            "fidelity": FIDELITY_MINUTES,
        })
        data = resp.json()
        history = data.get("history", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        if not history:
            return 0

        rows = []
        for pt in history:
            try:
                ts = int(float(pt["t"]))
                price = float(pt["p"])
                if not (0.001 <= price <= 0.999):
                    continue
                scanned_at = datetime.utcfromtimestamp(ts).isoformat()
                rows.append({
                    "market_id":  market_id,
                    "token_id":   token_id,
                    "scanned_at": scanned_at,
                    "mid_price":  price,
                })
            except (KeyError, ValueError, TypeError):
                continue

        if rows:
            db.bulk_insert_prices(rows)
        return len(rows)

    except Exception as e:
        logger.debug("Price history failed for %s: %s", market_id[:20], e)
        return 0


def scrape_and_store_all_prices(max_markets: int = 500) -> dict:
    """
    Fetch and store hourly CLOB price history for all resolved + active temp markets.
    Safe to re-run — inserts are idempotent (UNIQUE index on market_id + scanned_at).

    Returns summary dict: {markets_scraped, total_points, errors}
    """
    print("Collecting market list...", flush=True)
    markets = _collect_markets()
    print(f"  Found {len(markets)} unique markets", flush=True)

    if len(markets) > max_markets:
        markets = markets[:max_markets]
        print(f"  Capped at {max_markets}", flush=True)

    total_points = 0
    errors = 0
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_and_store_one, m["market_id"], m["token_id"]): m
            for m in markets
        }
        for fut in as_completed(futures):
            done += 1
            try:
                n = fut.result()
                total_points += n
            except Exception:
                errors += 1
            if done % 50 == 0 or done == len(markets):
                print(f"  {done}/{len(markets)} markets done — {total_points:,} price points stored", flush=True)

    return {
        "markets_scraped": done - errors,
        "total_points":    total_points,
        "errors":          errors,
    }
