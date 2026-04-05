"""
Cross-city correlation filter.

Weather systems move — a cold front hitting London and Paris on the same day
is one bet, not two. This filter caps total open exposure to any single
geographic weather region per target date.

Caps are set per-region based on actual synoptic correlation:
  Europe_W : 2 — London/Paris/Madrid/Munich/Milan sit on the same Atlantic
                  frontal systems; they are highly correlated day-to-day.
  NA_East  : 3 — NYC/Chicago/Atlanta/Dallas/Miami span 1500+ miles; a front
                  hitting Chicago often misses Miami. More independent than Europe.
  NA_West  : 2 — Only Seattle; cap rarely binds.
  LatAm    : 3 — Buenos Aires (subtropical pampas) and Sao Paulo (tropical
                  plateau) are ~1000 km apart with different meteorology.
  Other    : 3 — Hong Kong (SE Asia monsoon) and Tel Aviv (Mediterranean) are
                  completely uncorrelated; no reason to cap them together.

Toronto is assigned to NA_East — same Great Lakes/Atlantic synoptic pattern.
"""
import logging
import db

logger = logging.getLogger(__name__)

# Per-region cap: max unique cities with open trades per region per target date
REGION_MAX_POSITIONS: dict[str, int] = {
    "NA_East":  3,
    "NA_West":  2,
    "Europe_W": 3,
    "LatAm":    3,
    "Other":    3,
}
MAX_BUCKETS_PER_CITY_YES = 3   # max open YES bucket trades per city per target date
MAX_BUCKETS_PER_CITY_NO  = 5   # higher cap for NO bets — they're mutually exclusive in loss risk

CITY_REGION: dict[str, str] = {
    "New York City":  "NA_East",
    "Chicago":        "NA_East",
    "Atlanta":        "NA_East",
    "Miami":          "NA_East",
    "Dallas":         "NA_East",
    "Toronto":        "NA_East",
    "Seattle":        "NA_West",
    "London":         "Europe_W",
    "Paris":          "Europe_W",
    "Madrid":         "Europe_W",
    "Munich":         "Europe_W",
    "Milan":          "Europe_W",
    "Buenos Aires":   "LatAm",
    "Sao Paulo":      "LatAm",
    "Hong Kong":      "Other",
    "Tel Aviv":       "Other",
}


def get_open_exposure_by_region(target_date: str,
                                 open_trades: list[dict] | None = None) -> dict[str, int]:
    """
    Count unique cities with open trades per weather region for a given target date.
    Handles both daily trades (target_date match) and weekly trades (date range overlap).
    Pass open_trades to avoid a redundant DB query (e.g. during a scan loop).
    """
    if open_trades is None:
        open_trades = db.get_open_trades()
    region_cities: dict[str, set] = {}
    for trade in open_trades:
        td_start = str(trade.get("target_date", ""))
        td_end   = str(trade.get("target_date_end") or td_start)
        # A trade overlaps target_date if target_date falls in [td_start, td_end]
        if not (td_start <= target_date <= td_end):
            continue
        city   = trade.get("city", "")
        region = CITY_REGION.get(city)
        if region:
            region_cities.setdefault(region, set()).add(city)
    return {r: len(cities) for r, cities in region_cities.items()}


def get_city_bucket_count(city: str, target_date: str,
                           direction: str | None = None,
                           open_trades: list[dict] | None = None) -> int:
    """Count open bucket trades for a specific city that overlap target_date.
    If direction is given, only count trades of that direction."""
    if open_trades is None:
        open_trades = db.get_open_trades()
    count = 0
    for t in open_trades:
        if t.get("city") != city:
            continue
        if direction and t.get("direction") != direction:
            continue
        td_start = str(t.get("target_date", ""))
        td_end   = str(t.get("target_date_end") or td_start)
        if td_start <= target_date <= td_end:
            count += 1
    return count


def correlation_allows_trade(city: str, target_date: str,
                              direction: str = "YES",
                              open_trades: list[dict] | None = None) -> tuple[bool, str]:
    """
    Check whether adding a new trade for `city` on `target_date` is allowed.

    Two checks:
      1. Region cap — at most MAX_REGION_POSITIONS unique cities per weather region
         per date (prevents betting on correlated weather systems independently).
      2. Bucket cap — direction-aware:
           YES bets: max MAX_BUCKETS_PER_CITY_YES (correlated risk, cap tightly)
           NO bets:  max MAX_BUCKETS_PER_CITY_NO  (mutually exclusive loss risk, cap loosely)

    Pass open_trades to avoid a redundant DB query during a scan loop.
    Returns (allowed: bool, reason: str).
    """
    if open_trades is None:
        open_trades = db.get_open_trades()

    region = CITY_REGION.get(city)
    if region is None:
        return True, ""

    # Check 1: region cap (unique cities) — uses per-region limit
    region_cap = REGION_MAX_POSITIONS.get(region, 2)
    exposure = get_open_exposure_by_region(target_date, open_trades=open_trades)
    region_count = exposure.get(region, 0)
    if region_count >= region_cap:
        reason = (
            f"corr_cap: {region} already has {region_count}/{region_cap} "
            f"open trades on {target_date}"
        )
        logger.info("Correlation filter blocked %s: %s", city, reason)
        return False, reason

    # Check 2: per-city bucket cap (direction-aware)
    bucket_cap = MAX_BUCKETS_PER_CITY_YES if direction == "YES" else MAX_BUCKETS_PER_CITY_NO
    bucket_count = get_city_bucket_count(city, target_date, direction=direction,
                                          open_trades=open_trades)
    if bucket_count >= bucket_cap:
        reason = (
            f"bucket_cap: {city} already has {bucket_count}/{bucket_cap} "
            f"open {direction} bucket trades on {target_date}"
        )
        logger.info("Correlation filter blocked %s: %s", city, reason)
        return False, reason

    return True, ""
