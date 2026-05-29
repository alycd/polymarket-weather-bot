"""
Neighbor validation — cross-station sanity filter.

For each city that has a NEIGHBOR_REFS entry in config, fetch the GFS forecast
at a reference coordinate ~25-30km away in climatologically similar terrain.
Compare to the city's ensemble mean.

If |ensemble_mean - reference_temp| > NEIGHBOR_DIVERGENCE_C, the city's forecast
likely contains a model grid artifact (e.g. a front boundary placed exactly on
the city's grid cell). In that case, return a size penalty multiplier.

The fetch uses GFS only (cheapest and globally available). Results are cached
in-session so the same reference point is only fetched once per (city, date)
per scan run.
"""
import logging
import requests
from config_active import (
    OPENMETEO_MODELS, NEIGHBOR_REFS,
    NEIGHBOR_DIVERGENCE_C, NEIGHBOR_PENALTY_MULT,
)

logger = logging.getLogger(__name__)

# In-session cache: {"{city}_{target_date}": reference_temp_c | None}
# None means the fetch was attempted and failed — don't retry.
_session_cache: dict[str, float | None] = {}


def _fetch_reference_temp(city: str, target_date: str, timezone: str) -> float | None:
    """
    Fetch the GFS daily max temperature at the reference coordinate for city.
    Returns °C or None on failure.
    """
    ref = NEIGHBOR_REFS[city]
    try:
        resp = requests.get(
            OPENMETEO_MODELS["gfs"],
            params={
                "latitude":         ref["lat"],
                "longitude":        ref["lon"],
                "daily":            "temperature_2m_max",
                "temperature_unit": "celsius",
                "forecast_days":    14,
                "timezone":         timezone,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        times = data.get("daily", {}).get("time", [])
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if target_date in times:
            idx = times.index(target_date)
            val = temps[idx]
            if val is not None:
                return float(val)
        logger.debug("Neighbor ref %s: target_date %s not in GFS forecast", city, target_date)
    except Exception as e:
        logger.debug("Neighbor ref fetch failed for %s: %s", city, e)
    return None


def get_neighbor_penalty(
    city: str,
    ensemble_mean_c: float,
    target_date: str,
    timezone: str,
) -> tuple[float, str]:
    """
    Returns (size_multiplier, reason_str).

    multiplier = 1.0  — no neighbor ref defined, or divergence within tolerance
    multiplier = NEIGHBOR_PENALTY_MULT — divergence suggests a grid artifact

    Caches the reference fetch so it runs at most once per (city, date) per
    scan session regardless of how many buckets are evaluated.
    """
    if city not in NEIGHBOR_REFS:
        return 1.0, ""

    cache_key = f"{city}_{target_date}"
    if cache_key not in _session_cache:
        _session_cache[cache_key] = _fetch_reference_temp(city, target_date, timezone)

    ref_temp = _session_cache[cache_key]
    if ref_temp is None:
        # Fetch failed — don't penalise, just proceed without the check
        return 1.0, ""

    divergence = abs(ensemble_mean_c - ref_temp)

    if divergence > NEIGHBOR_DIVERGENCE_C:
        reason = (
            f"neighbor_divergence={divergence:.1f}°C "
            f"(city={ensemble_mean_c:.1f}°C  ref={ref_temp:.1f}°C)"
        )
        logger.warning("NEIGHBOR CHECK %s: grid artifact suspected — %s → size ×%.1f",
                       city, reason, NEIGHBOR_PENALTY_MULT)
        return NEIGHBOR_PENALTY_MULT, reason

    logger.debug("Neighbor check %s OK: divergence=%.1f°C (city=%.1f ref=%.1f)",
                 city, divergence, ensemble_mean_c, ref_temp)
    return 1.0, ""


def clear_session_cache() -> None:
    """Clear the in-session cache. The cache clears naturally between process runs."""
    _session_cache.clear()
