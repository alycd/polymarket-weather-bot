"""
NOAA / Iowa State Mesonet data fetchers.

Two roles:
  1. Iowa State ASOS — historical hourly station obs → compute daily max
     URL: https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py
     Free, no auth, covers most ICAO airport stations.

  2. NOAA Aviation Weather METAR — live current observations
     URL: https://aviationweather.gov/api/data/metar
     Free, no auth, JSON format.
"""
import logging
import requests
from collections import defaultdict
from datetime import datetime, date, timedelta
from config_active import ASOS_URL, METAR_URL
from data.utils import retry

logger = logging.getLogger(__name__)


# ── Iowa State ASOS historical data ──────────────────────────────────────────

from utils import f_to_c as _f_to_c


@retry((requests.exceptions.RequestException, Exception), tries=3, delay=2)
def fetch_asos_daily_max(asos_station: str, start_date: str, end_date: str,
                          use_celsius: bool = True) -> dict[str, float]:
    """
    Fetch hourly ASOS data and compute daily max temperature.
    Returns dict: {date_str: max_temp_c}
    Raises on API failure.

    asos_station: e.g. 'LGA', 'EGLL', 'VHHH', 'CYYZ'
    """
    # Try Celsius directly, fall back to Fahrenheit
    for data_var, is_fahrenheit in [("tmpc", False), ("tmpf", True)]:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end   = datetime.strptime(end_date,   "%Y-%m-%d")
            resp = requests.get(ASOS_URL, params={
                "station": asos_station,
                "data":    data_var,
                "year1":   start.year, "month1": start.month, "day1": start.day,
                "year2":   end.year,   "month2": end.month,   "day2": end.day,
                "tz":      "UTC",
                "format":  "comma",
                "latlon":  "no",
                "missing": "empty",
                "trace":   "empty",
            }, timeout=30)
            resp.raise_for_status()

            lines = [l for l in resp.text.strip().split("\n") if not l.startswith("#")]
            if not lines or "station,valid" not in lines[0]:
                raise ValueError(f"Unexpected ASOS response format for {asos_station}")

            daily_max: dict[str, list[float]] = defaultdict(list)
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                ts_str, temp_str = parts[1].strip(), parts[2].strip()
                if not temp_str or temp_str in ("M", ""):
                    continue
                try:
                    temp = float(temp_str)
                    obs_date = ts_str[:10]  # 'YYYY-MM-DD'
                    if is_fahrenheit:
                        temp = _f_to_c(temp)
                    daily_max[obs_date].append(temp)
                except (ValueError, IndexError):
                    continue

            if not daily_max:
                raise ValueError(f"No valid observations for {asos_station}")

            result = {d: max(temps) for d, temps in daily_max.items() if temps}
            logger.info("ASOS %s: %d days of data (%s–%s)",
                        asos_station, len(result), start_date, end_date)
            return result

        except requests.HTTPError as e:
            if e.response.status_code == 404 and data_var == "tmpc":
                # Try Fahrenheit version
                logger.debug("ASOS %s: tmpc 404, trying tmpf", asos_station)
                continue
            raise

    raise RuntimeError(f"ASOS fetch failed for {asos_station} with both tmpc and tmpf")


@retry((requests.exceptions.RequestException, Exception), tries=3, delay=2)
def fetch_asos_today_hourly(asos_station: str, timezone_str: str = "UTC") -> list[dict]:
    """
    Fetch today's hourly observations for nowcasting.
    Returns list of {time_utc, temp_c} sorted by time.
    Raises on failure.

    timezone_str: pytz timezone name for the city (e.g. 'Asia/Tokyo').
    Uses the local calendar date so cities ahead of UTC (e.g. Tokyo at 2am
    local = previous UTC day) fetch the correct day's observations.
    """
    import pytz
    tz = pytz.timezone(timezone_str)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    resp = requests.get(ASOS_URL, params={
        "station": asos_station,
        "data":    "tmpc",
        "year1":   today.year,    "month1": today.month,    "day1": today.day,
        "year2":   tomorrow.year, "month2": tomorrow.month, "day2": tomorrow.day,
        "tz":      "UTC",
        "format":  "comma",
        "latlon":  "no",
        "missing": "empty",
        "trace":   "empty",
    }, timeout=15)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().split("\n") if not l.startswith("#")]
    obs = []
    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        ts_str, temp_str = parts[1].strip(), parts[2].strip()
        if not temp_str or temp_str in ("M", ""):
            continue
        try:
            obs.append({
                "time_utc": ts_str,
                "temp_c":   float(temp_str),
            })
        except ValueError:
            continue

    if not obs:
        logger.warning("ASOS %s: no today observations yet", asos_station)
    return obs


# ── NOAA METAR live observations ──────────────────────────────────────────────

@retry((requests.exceptions.RequestException, Exception), tries=3, delay=2)
def fetch_metar(icao_list: list[str]) -> dict[str, dict]:
    """
    Fetch the most recent METAR observation for each station.
    Returns dict: {icao: {temp_c, dew_c, report_time, raw}}
    Silently skips stations that have no recent METAR (not every station reports).
    Raises on API failure.
    """
    ids_str = ",".join(icao_list)
    resp = requests.get(METAR_URL, params={
        "ids":    ids_str,
        "format": "json",
        "hours":  3,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = {}
    # Keep only the most recent observation per station
    seen = {}
    for obs in data:
        icao = obs.get("icaoId")
        if not icao:
            continue
        report_time = obs.get("reportTime", "")
        if icao not in seen or report_time > seen[icao]["report_time"]:
            temp = obs.get("temp")
            if temp is None:
                continue
            seen[icao] = {
                "temp_c":      float(temp),
                "dew_c":       float(obs.get("dewp", 0)) if obs.get("dewp") else None,
                "report_time": report_time,
                "raw":         obs.get("rawOb", ""),
            }
    return seen


def get_running_max_today(asos_station: str, city_tz: str) -> dict | None:
    """
    Get the running maximum temperature for today from ASOS hourly obs.
    Returns {running_max_c, obs_count, last_obs_time, temp_rate_c_per_h} or None.

    temp_rate_c_per_h: temperature trend over last ~2h (°C/h).
        > 0  = still warming
        < 0  = cooling / past peak
        None = fewer than 3 obs available

    city_tz: pytz timezone name — used to determine the correct local date
    so cities ahead of UTC (e.g. Tokyo, Hong Kong) fetch today's obs, not
    yesterday's.
    """
    try:
        obs = fetch_asos_today_hourly(asos_station, timezone_str=city_tz)
        if not obs:
            return None
        temps = [o["temp_c"] for o in obs]

        # Rate of change: slope over last 3 obs (≈ last 2 hours at ~1 obs/hr).
        # Using first/last of the window avoids over-sensitivity to a single reading.
        if len(obs) >= 3:
            recent = obs[-3:]
            dt_h = len(recent) - 1   # ≈ 2h
            rate = (recent[-1]["temp_c"] - recent[0]["temp_c"]) / dt_h
        else:
            rate = None

        return {
            "running_max_c":    max(temps),
            "obs_count":        len(obs),
            "last_obs_time":    obs[-1]["time_utc"],
            "temp_rate_c_per_h": rate,
        }
    except Exception as e:
        logger.error("Running max failed for %s: %s", asos_station, e)
        return None
