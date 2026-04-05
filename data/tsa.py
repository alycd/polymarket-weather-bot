"""
TSA passenger volume data fetcher.

Scrapes the TSA daily passenger counts page and computes:
  - Day-of-week baselines (what's normal for Mon/Tue/…/Sun)
  - Year-over-year growth ratio
  - Holiday multipliers (from config)

Source: https://www.tsa.gov/travel/passenger-volumes
"""
import logging
import re
from datetime import date, datetime, timedelta
from functools import lru_cache

import requests

from config import TSA_DATA_URL, TSA_HOLIDAY_PERIODS

logger = logging.getLogger(__name__)

TIMEOUT = 15


def _parse_count(raw: str) -> int | None:
    """Strip commas/whitespace and parse to int."""
    clean = re.sub(r"[^\d]", "", raw.strip())
    return int(clean) if clean else None


def fetch_tsa_data() -> dict[str, dict]:
    """
    Scrape tsa.gov/travel/passenger-volumes.

    Returns dict keyed by ISO date string:
        {
            "2026-03-25": {"current": 2456782, "prior": 2345123},
            ...
        }
    Only includes rows where at least the current-year count is parseable.
    Silently skips malformed rows.
    """
    try:
        resp = requests.get(TSA_DATA_URL, timeout=TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; TSA-bot/1.0)"})
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch TSA data: %s", e)
        return {}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 not installed — run: pip install beautifulsoup4")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the passenger volume table — class varies by site version
    table = (soup.find("table") or
             soup.find("table", {"class": re.compile(r"views|passenger", re.I)}))
    if table is None:
        logger.error("TSA page: no <table> found")
        return {}

    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    # TSA page sometimes has year columns ("2026", "2025") and sometimes just "Numbers"
    date_col    = next((i for i, h in enumerate(headers) if "date" in h), None)
    current_col = next(
        (i for i, h in enumerate(headers)
         if any(yr in h for yr in ("2026", "2025", "2024")) or
            h in ("numbers", "this year", "passengers", "2026 numbers", "travelers")),
        None
    )
    # Fall back: any non-date column is the count column
    if current_col is None and date_col is not None and len(headers) > 1:
        current_col = next(i for i in range(len(headers)) if i != date_col)

    prior_col = next(
        (i for i, h in enumerate(headers) if "2025" in h or "last year" in h or "prior" in h),
        None
    )

    if date_col is None or current_col is None:
        logger.error("TSA table: could not find date/count columns, headers=%s", headers)
        return {}

    rows: dict[str, dict] = {}
    for tr in table.find_all("tr")[1:]:  # skip header row
        cells = tr.find_all(["td", "th"])
        if len(cells) <= max(date_col, current_col):
            continue
        raw_date    = cells[date_col].get_text(strip=True)
        raw_current = cells[current_col].get_text(strip=True)
        raw_prior   = cells[prior_col].get_text(strip=True) if prior_col and len(cells) > prior_col else ""

        # Parse date — TSA uses M/D/YYYY or YYYY-MM-DD
        parsed_date = _parse_tsa_date(raw_date)
        if not parsed_date:
            continue
        current_count = _parse_count(raw_current)
        if not current_count:
            continue
        prior_count = _parse_count(raw_prior)

        rows[parsed_date] = {"current": current_count, "prior": prior_count}

    logger.info("TSA data fetched: %d rows", len(rows))
    return rows


def _parse_tsa_date(raw: str) -> str | None:
    """Parse TSA date strings like '3/25/2026' or '2026-03-25' → 'YYYY-MM-DD'."""
    raw = raw.strip()
    # Try ISO format first
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        pass
    # Try M/D/YYYY
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass
    # Try M/D/YY (two-digit year)
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})$", raw)
    if m:
        year = 2000 + int(m.group(3))
        try:
            return date(year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass
    return None


def compute_dow_baselines(data: dict[str, dict], use_prior: bool = False) -> dict[int, float]:
    """
    Compute mean daily passenger count by day of week.

    data: output of fetch_tsa_data()
    use_prior: if True, use prior-year column (2025 data); else use current (2026)

    Returns {0: mean_monday, 1: mean_tuesday, ..., 6: mean_sunday}
    using Python's date.weekday() convention (0=Mon, 6=Sun).
    """
    buckets: dict[int, list[float]] = {d: [] for d in range(7)}
    for date_str, counts in data.items():
        count = counts.get("prior" if use_prior else "current")
        if not count:
            continue
        try:
            dow = date.fromisoformat(date_str).weekday()
        except ValueError:
            continue
        buckets[dow].append(float(count))

    return {dow: (sum(vals) / len(vals)) for dow, vals in buckets.items() if vals}


def compute_yoy_ratio(data: dict[str, dict], lookback_days: int = 30) -> float:
    """
    Compute mean current/prior year ratio over the most recent `lookback_days`.

    Returns 1.0 if insufficient data (safe default = no growth assumption).
    """
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    ratios = []
    for date_str, counts in data.items():
        if date_str < cutoff:
            continue
        curr  = counts.get("current")
        prior = counts.get("prior")
        if curr and prior and prior > 0:
            ratios.append(curr / prior)
    if not ratios:
        logger.warning("YoY ratio: no data in last %d days, using 1.0", lookback_days)
        return 1.0
    ratio = sum(ratios) / len(ratios)
    logger.debug("YoY ratio (last %d days): %.4f from %d obs", lookback_days, ratio, len(ratios))
    return ratio


def get_holiday_info(target_date: str) -> tuple[str | None, float]:
    """
    Return (holiday_name, multiplier) if target_date falls in a peak-travel period.
    Returns (None, 1.0) if no holiday applies or year not configured.

    config.TSA_HOLIDAY_PERIODS stores periods as MM-DD ranges, keyed by year.
    """
    try:
        year = int(target_date[:4])
        md   = target_date[5:]  # "MM-DD"
    except (ValueError, IndexError):
        return None, 1.0

    periods = TSA_HOLIDAY_PERIODS.get(year, [])
    for period in periods:
        if period["start"] <= md <= period["end"]:
            return period["name"], period["multiplier"]
    return None, 1.0


def forecast_passengers(
    target_date: str,
    data: dict[str, dict],
    dow_baselines: dict[int, float] | None = None,
    yoy_ratio: float | None = None,
) -> dict:
    """
    Produce a passenger count forecast for target_date.

    Returns:
        {
            "mean":            float,   # expected passengers
            "std":             float,   # 1-sigma uncertainty
            "dow_baseline":    float,   # day-of-week mean before adjustments
            "yoy_ratio":       float,
            "holiday_name":    str | None,
            "holiday_multiplier": float,
            "data_points":     int,     # how many historical obs drove DOW baseline
        }
    """
    from config import TSA_FORECAST_STD_FRACTION

    if dow_baselines is None:
        dow_baselines = compute_dow_baselines(data)
    if yoy_ratio is None:
        yoy_ratio = compute_yoy_ratio(data)

    try:
        td = date.fromisoformat(target_date)
    except ValueError:
        logger.error("Invalid target_date: %s", target_date)
        return {}

    dow = td.weekday()
    dow_mean = dow_baselines.get(dow)
    if dow_mean is None:
        logger.warning("No DOW baseline for weekday %d — using overall mean", dow)
        all_vals = [c["current"] for c in data.values() if c.get("current")]
        dow_mean = sum(all_vals) / len(all_vals) if all_vals else 2_400_000.0

    holiday_name, holiday_multiplier = get_holiday_info(target_date)

    mean_passengers = dow_mean * yoy_ratio * holiday_multiplier
    std_passengers  = mean_passengers * TSA_FORECAST_STD_FRACTION

    # Count the data points that drove this estimate
    dow_pts = sum(
        1 for ds, c in data.items()
        if c.get("current") and _safe_weekday(ds) == dow
    )

    return {
        "mean":               mean_passengers,
        "std":                std_passengers,
        "dow_baseline":       dow_mean,
        "yoy_ratio":          yoy_ratio,
        "holiday_name":       holiday_name,
        "holiday_multiplier": holiday_multiplier,
        "data_points":        dow_pts,
    }


def _safe_weekday(date_str: str) -> int | None:
    try:
        return date.fromisoformat(date_str).weekday()
    except ValueError:
        return None
