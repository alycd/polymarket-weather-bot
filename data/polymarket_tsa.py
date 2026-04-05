"""
Polymarket TSA passenger market fetcher and parser.

Fetches active "How many TSA passengers on [date]?" markets from the
Gamma API and parses bucket boundaries (in millions of passengers).
"""
import re
import logging
from datetime import datetime, date

import requests

from config import GAMMA_API, CLOB_API

logger = logging.getLogger(__name__)

TIMEOUT = 15

# Patterns for TSA market questions
# Tries "on/for [Month] [D]" first, then bare "[Month] [D]" as fallback
_TSA_DATE_PATTERN = re.compile(
    r"(?:(?:on|for)\s+)?(\w+)\s+(\d{1,2})(?:,?\s*(\d{4}))?", re.I
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_tsa_question(question: str) -> dict | None:
    """
    Parse a Polymarket TSA passenger question.

    Handles patterns like:
      "Will TSA screen more than 2.6 million passengers on April 1?"
      "TSA passengers on March 28, 2026: over 2.4M?"
      "How many TSA passengers on April 3, 2026? More than 2.8M"
      "TSA checkpoint volume April 5: under 2.2 million?"

    Returns:
        {
            "target_date": "YYYY-MM-DD",
            "bucket_lo": float | None,   # lower bound in millions, None = -inf
            "bucket_hi": float | None,   # upper bound in millions, None = +inf
            "bucket_unit": "M",          # millions
        }
    or None if unparseable.
    """
    q = question.strip()
    ql = q.lower()

    # Must mention TSA and passengers or checkpoint
    if "tsa" not in ql:
        return None
    if not any(kw in ql for kw in ("passenger", "checkpoint", "screen", "traveler")):
        return None

    # ── Parse date ────────────────────────────────────────────────────────────
    target_date = None

    # Try ISO date first
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if iso_match:
        try:
            target_date = date.fromisoformat(iso_match.group(1)).isoformat()
        except ValueError:
            pass

    # Try month-name patterns if ISO didn't match
    if not target_date:
        # Build pattern that only matches valid month names
        month_names = "|".join(_MONTHS.keys())
        month_date_pat = re.compile(
            r"(?:on\s+|for\s+)?(" + month_names + r")\s+(\d{1,2})(?:,?\s*(\d{4}))?",
            re.I
        )
        date_match = month_date_pat.search(ql)
        if date_match:
            month_str = date_match.group(1)
            day_str   = date_match.group(2)
            year_str  = date_match.group(3)
            month = _MONTHS.get(month_str.lower())
            if month:
                year = int(year_str) if year_str else datetime.utcnow().year
                if not year_str:
                    now = datetime.utcnow()
                    if month < now.month:
                        year = now.year + 1
                try:
                    target_date = date(year, month, int(day_str)).isoformat()
                except ValueError:
                    pass

    if not target_date:
        return None

    # ── Parse bucket ──────────────────────────────────────────────────────────
    bucket = _parse_tsa_bucket(q)
    if bucket is None:
        return None

    return {
        "target_date": target_date,
        "bucket_lo":   bucket["lo"],
        "bucket_hi":   bucket["hi"],
        "bucket_unit": "M",
    }


def _parse_tsa_bucket(question: str) -> dict | None:
    """
    Extract passenger count bucket from a question string.

    Handles raw counts and shorthand:
      "be less than 2,200,000"          → {lo: None, hi: 2.2}
      "be between 2,800,000 and 3,000,000" → {lo: 2.8, hi: 3.0}
      "be greater than 3,000,000"       → {lo: 3.0, hi: None}
      "more than 2.6 million"           → {lo: 2.6, hi: None}
      "over 2.8M"                       → {lo: 2.8, hi: None}
      "under 2.2 million"               → {lo: None, hi: 2.2}
    All values normalized to millions.
    """
    ql = question.lower()

    def to_millions(raw: str) -> float | None:
        """Parse a number string to millions. Handles 2,200,000 and 2.2 and 2.2M."""
        raw = raw.replace(",", "").strip()
        try:
            val = float(raw)
            if val >= 1_000:      # raw count like 2200000 → convert to millions
                val /= 1_000_000
            return round(val, 4)
        except ValueError:
            return None

    # Two number patterns: raw counts (1,000,000+) and shorthand (2.2 million / 2.2M)
    raw_num  = r"(\d[\d,]{3,})"                                # 2,200,000 or 2200000
    short_m  = r"(\d[\d]*(?:\.\d+)?)\s*(?:million|m\b)"       # 2.2 million / 2.2M

    def first_two(pat: str, text: str) -> tuple:
        hits = re.findall(pat, text)
        return (hits[0] if len(hits) > 0 else None,
                hits[1] if len(hits) > 1 else None)

    # --- Range: "between X and Y" ---
    # raw counts
    rng = re.search(r"between\s+" + raw_num + r"\s+and\s+" + raw_num, ql)
    if rng:
        lo, hi = to_millions(rng.group(1)), to_millions(rng.group(2))
        if lo is not None and hi is not None and lo < hi:
            return {"lo": lo, "hi": hi}
    # shorthand
    rng = re.search(r"between\s+" + short_m + r"\s+and\s+" + short_m, ql)
    if rng:
        lo, hi = to_millions(rng.group(1)), to_millions(rng.group(2))
        if lo is not None and hi is not None and lo < hi:
            return {"lo": lo, "hi": hi}
    # dash range: 2,800,000-3,000,000 or 2.8M-3.0M
    rng = re.search(raw_num + r"\s*[-–]\s*" + raw_num, ql)
    if rng:
        lo, hi = to_millions(rng.group(1)), to_millions(rng.group(2))
        if lo is not None and hi is not None and lo < hi:
            return {"lo": lo, "hi": hi}

    # --- Upper bound: less than / under / below ---
    upper_kw = r"(?:less than|fewer than|under|below)"
    m = re.search(upper_kw + r"\s+" + raw_num, ql)
    if m:
        hi = to_millions(m.group(1))
        if hi is not None:
            return {"lo": None, "hi": hi}
    m = re.search(upper_kw + r"\s+" + short_m, ql)
    if m:
        hi = to_millions(m.group(1))
        if hi is not None:
            return {"lo": None, "hi": hi}

    # --- Lower bound: greater than / more than / over / above / at least ---
    lower_kw = r"(?:greater than|more than|over|above|at least|exceed)"
    m = re.search(lower_kw + r"\s+" + raw_num, ql)
    if m:
        lo = to_millions(m.group(1))
        if lo is not None:
            return {"lo": lo, "hi": None}
    m = re.search(lower_kw + r"\s+" + short_m, ql)
    if m:
        lo = to_millions(m.group(1))
        if lo is not None:
            return {"lo": lo, "hi": None}

    return None


def fetch_tsa_markets() -> list[dict]:
    """
    Fetch active TSA passenger count markets from Polymarket Gamma API.

    Uses the same paginated approach as fetch_temperature_markets() — iterates
    all active markets ordered by endDate and filters by question keywords.

    Returns list of dicts, each with:
        market_id, question, clob_token_yes,
        target_date, bucket_lo, bucket_hi, bucket_unit,
        volume_usdc
    """
    from config import MIN_MARKET_VOLUME_USDC

    # Paginate through all active markets (same pattern as temperature markets)
    all_markets = []
    batch = 500
    for offset in range(0, 10000, batch):
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": batch,
                    "offset": offset,
                    "order": "endDate",
                    "ascending": "true",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_markets.extend(data)
        except Exception as e:
            logger.warning("Gamma paginated fetch failed (offset=%d): %s", offset, e)
            break

    logger.debug("TSA fetch: %d total active markets scanned", len(all_markets))

    # Filter to TSA passenger market candidates by keyword
    tsa_kw = ["tsa", "checkpoint", "passenger"]
    candidates = [
        m for m in all_markets
        if any(kw in m.get("question", "").lower() for kw in tsa_kw)
    ]
    logger.info("TSA keyword matches: %d", len(candidates))

    # Deduplicate by conditionId
    seen = {}
    for m in candidates:
        cid = m.get("conditionId") or m.get("id") or ""
        if cid and cid not in seen:
            seen[cid] = m
    markets = list(seen.values())

    results = []
    for m in markets:
        question = m.get("question", "")
        parsed = parse_tsa_question(question)
        if not parsed:
            continue

        # Volume filter
        volume = float(m.get("volume", 0) or 0)
        if volume < MIN_MARKET_VOLUME_USDC:
            logger.debug("TSA market skipped (volume $%.0f < threshold): %s",
                         volume, question[:60])
            continue

        # Extract CLOB token
        clob_token = ""
        outcomes = m.get("clobTokenIds") or m.get("clob_token_ids") or []
        if isinstance(outcomes, list) and outcomes:
            clob_token = outcomes[0]
        elif isinstance(outcomes, str):
            import json
            try:
                toks = json.loads(outcomes)
                clob_token = toks[0] if toks else ""
            except Exception:
                pass

        market_id = m.get("conditionId") or m.get("id") or ""

        results.append({
            "market_id":      market_id,
            "question":       question,
            "clob_token_yes": clob_token,
            "city":           "TSA",
            "icao":           "TSA",
            "target_date":    parsed["target_date"],
            "bucket_lo":      parsed["bucket_lo"],
            "bucket_hi":      parsed["bucket_hi"],
            "bucket_unit":    "M",
            "volume_usdc":    volume,
            "market_type":    "tsa",
        })

    logger.info("TSA markets fetched: %d parseable", len(results))
    return results


def get_tsa_market_prices(market: dict) -> dict:
    """Get live CLOB prices for a TSA market. Same interface as get_market_prices()."""
    from data.polymarket import get_market_prices
    return get_market_prices(market)
