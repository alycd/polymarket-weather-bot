"""
Climatological baseline from Open-Meteo Climate API.

Fetches 30-year historical daily max temperature distributions per station,
aggregated by calendar month. Used to build a prior that sharpens the
Gaussian model when today's forecast deviates from seasonal norms.

API: https://climate-api.open-meteo.com/v1/climate
Model: ERA5 reanalysis (1940–present), globally available, free, no auth.
"""
import logging
import math
import requests
from config_active import CLIMATE_API_URL

logger = logging.getLogger(__name__)

TIMEOUT = 30
CLIMO_START = "1991-01-01"   # 30-year WMO standard period start
CLIMO_END   = "2020-12-31"   # 30-year WMO standard period end


def fetch_climatology(lat: float, lon: float, timezone: str) -> dict[int, dict]:
    """
    Fetch 30-year daily max temperature climatology and compute per-month stats.

    Returns dict: {month (1-12): {mean_c, std_c, p10_c, p90_c, sample_years}}
    Raises on API failure.
    """
    resp = requests.get(CLIMATE_API_URL, params={
        "latitude":         lat,
        "longitude":        lon,
        "start_date":       CLIMO_START,
        "end_date":         CLIMO_END,
        "daily":            "temperature_2m_max",
        "temperature_unit": "celsius",
        "timezone":         timezone,
    }, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    times = data.get("daily", {}).get("time", [])
    temps = data.get("daily", {}).get("temperature_2m_max", [])

    if not times:
        raise ValueError(f"Climate API returned no data for {lat},{lon}")

    # Bucket daily values by calendar month
    by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for t, v in zip(times, temps):
        if v is None:
            continue
        month = int(t[5:7])
        by_month[month].append(float(v))

    result: dict[int, dict] = {}
    for month, vals in by_month.items():
        if not vals:
            continue
        n = len(vals)
        mean = sum(vals) / n
        variance = sum((v - mean) ** 2 for v in vals) / max(n - 1, 1)
        std = math.sqrt(variance)
        sorted_vals = sorted(vals)
        p10 = sorted_vals[max(0, int(0.10 * n))]
        p90 = sorted_vals[min(n - 1, int(0.90 * n))]
        # Approximate number of years: ~30 days/month × years
        sample_years = max(1, round(n / (365.25 / 12)))  # approximate years from monthly count
        result[month] = {
            "mean_c":       round(mean, 2),
            "std_c":        round(std, 2),
            "p10_c":        round(p10, 2),
            "p90_c":        round(p90, 2),
            "sample_years": sample_years,
        }
        logger.debug("Climo M%02d: mean=%.1f std=%.1f p10=%.1f p90=%.1f (n=%d)",
                     month, mean, std, p10, p90, n)

    return result
