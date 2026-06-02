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

# Adjacent NO bets on same city/date cancel out when the actual lands in one of the two buckets.
# Block a new NO trade if any existing NO trade (open or in-scan) is within this gap.
MIN_NO_BUCKET_GAP_F = 2.0   # °F — blocks adjacent 1°F buckets (gap ≤ 1°F)
MIN_NO_BUCKET_GAP_C = 1.0   # °C — blocks adjacent 1°C buckets (gap = 0°C)

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


def _bucket_gap(lo1: float | None, hi1: float | None,
                lo2: float | None, hi2: float | None) -> float:
    """Return the numeric gap between two half-open buckets [lo1, hi1) and [lo2, hi2).
    Returns 0.0 if they overlap, inf if either bound is missing."""
    if lo1 is None or lo2 is None:
        return float("inf")
    # Overlap when lo1 < hi2 AND lo2 < hi1
    hi1_eff = hi1 if hi1 is not None else float("inf")
    hi2_eff = hi2 if hi2 is not None else float("inf")
    if lo1 < hi2_eff and lo2 < hi1_eff:
        return 0.0
    if lo2 >= hi1_eff:
        return lo2 - hi1_eff
    return lo1 - hi2_eff


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
                              open_trades: list[dict] | None = None,
                              bucket_lo: float | None = None,
                              bucket_hi: float | None = None,
                              bucket_unit: str = "F",
                              pending_no_buckets: list | None = None) -> tuple[bool, str]:
    """
    Check whether adding a new trade for `city` on `target_date` is allowed.

    Three checks:
      1. Region cap — at most MAX_REGION_POSITIONS unique cities per weather region
         per date (prevents betting on correlated weather systems independently).
      2. Bucket cap — direction-aware:
           YES bets: max MAX_BUCKETS_PER_CITY_YES (correlated risk, cap tightly)
           NO bets:  max MAX_BUCKETS_PER_CITY_NO  (mutually exclusive loss risk, cap loosely)
      3. NO proximity — block a new NO trade whose bucket is within MIN_NO_BUCKET_GAP of
         any existing open or in-scan NO trade on the same city/date. Adjacent NO bets
         cancel out when the actual temperature lands in one of the two buckets.

    Pass open_trades to avoid a redundant DB query during a scan loop.
    Pass pending_no_buckets (list of (lo, hi, unit) tuples) for trades placed in the
    current scan run that are not yet reflected in the DB snapshot.
    Returns (allowed: bool, reason: str).
    """
    if open_trades is None:
        open_trades = db.get_open_trades()

    # Check 3 runs for ALL cities (not region-gated) — do it before the early-return below.
    # Adjacent NO bets on the same city/date cancel each other out when the actual temp
    # lands in one of the two buckets. Block any new NO trade within MIN_NO_BUCKET_GAP.
    if direction == "NO" and bucket_lo is not None:
        min_gap = MIN_NO_BUCKET_GAP_F if bucket_unit == "F" else MIN_NO_BUCKET_GAP_C
        unit_label = "°F" if bucket_unit == "F" else "°C"

        for t in open_trades:
            if t.get("city") != city or t.get("direction") != "NO":
                continue
            td_start = str(t.get("target_date", ""))
            td_end   = str(t.get("target_date_end") or td_start)
            if not (td_start <= target_date <= td_end):
                continue
            gap = _bucket_gap(bucket_lo, bucket_hi, t.get("bucket_lo"), t.get("bucket_hi"))
            if gap < min_gap:
                reason = (
                    f"proximity_cap: NO trade at [{t.get('bucket_lo')},{t.get('bucket_hi')}) "
                    f"is {gap:.1f}{unit_label} away (min {min_gap}{unit_label})"
                )
                logger.info("Proximity filter blocked %s: %s", city, reason)
                return False, reason

        for plo, phi, _punit in (pending_no_buckets or []):
            gap = _bucket_gap(bucket_lo, bucket_hi, plo, phi)
            if gap < min_gap:
                reason = (
                    f"proximity_cap: in-scan NO trade at [{plo},{phi}) "
                    f"is {gap:.1f}{unit_label} away (min {min_gap}{unit_label})"
                )
                logger.info("Proximity filter blocked %s: %s", city, reason)
                return False, reason

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
