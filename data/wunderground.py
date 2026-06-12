"""
Wunderground data fetcher — PRIMARY source of truth for temperature resolution.

Polymarket temperature markets resolve from the Weather Underground daily-history
page for the market's airport station (wunderground.com/history/daily/<ICAO>/...).
That page is now JS-rendered and loads its observations client-side from The Weather
Company backend (api.weather.com) — the same data Polymarket reads. We therefore go
straight to that backend (see get_historical_high_native / get_historical_high).

Resolution source priority (position_manager.py.get_actual_high_c):
  1. Wunderground / api.weather.com — Polymarket's own resolution source (PRIMARY)
  2. Iowa State ASOS — official airport obs (fallback)
  3. Open-Meteo Archive — ERA5 reanalysis (last resort)

WU is also used for live intraday obs in the nowcaster (advisory only).

Bucket / rounding semantics (validated against 19 resolved PM settlements, 2026-06):
  Polymarket scores the INTEGER print WU shows for the station's local calendar day.
  Market questions read "be 26°C" (single integer) or "between 74-75°F" (a 2-degree
  inclusive range). Membership is on the integer print in the market's NATIVE unit:
      YES wins iff  bucket_lo <= round(WU_high_native) <= bucket_hi   (closed-closed)
  Converting the integer print to a continuous °C value and using an exclusive upper
  bound (the old position_manager behaviour) mis-scores upper-edge prints — e.g.
  WU=65°F in a 64-65°F market: f_to_c(65)=18.33 == upper edge, 18.33 < 18.33 is False,
  so the old code wrongly excluded it while Polymarket counts it as YES. Resolve in
  native integer units to match PM exactly.
"""
import os
import re
import json
import logging
import time
import requests
from datetime import date, datetime

logger = logging.getLogger(__name__)

# ── api.weather.com backend (the data WU's history page actually displays) ──────
# Public site key embedded in the WU history page HTML. Rotates occasionally; can be
# overridden via the WU_API_KEY env var. _refresh_api_key() re-scrapes it on a 401.
_WU_API_KEY = os.environ.get("WU_API_KEY", "e1f10a1e78da46f5b10a1e78da96f525")
_WX_HOST = "https://api.weather.com"
_country_cache: dict[str, str | None] = {}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.wunderground.com/",
}

TIMEOUT = 20


class WundergroundError(Exception):
    pass


# ── api.weather.com path (primary) ──────────────────────────────────────────────

def _refresh_api_key() -> str | None:
    """Re-scrape the current api.weather.com site key from a WU history page.

    The embedded key rotates periodically; on a 401 we refresh it once. Returns the
    new key (also updates the module global) or None if it can't be found.
    """
    global _WU_API_KEY
    try:
        url = "https://www.wunderground.com/history/daily/KSFO/date/2024-01-01"
        html = requests.get(url, headers=_HEADERS, timeout=TIMEOUT).text
        m = re.search(r"apiKey=([a-f0-9]{32})", html) or re.search(r"['\"]([a-f0-9]{32})['\"]", html)
        if m:
            _WU_API_KEY = m.group(1)
            logger.info("Refreshed WU api.weather.com key")
            return _WU_API_KEY
    except Exception as e:
        logger.warning("WU api key refresh failed: %s", e)
    return None


def _country_code(icao: str) -> str | None:
    """Resolve the ISO country code WU uses for the {ICAO}:9:{CC} location key."""
    if icao in _country_cache:
        return _country_cache[icao]
    try:
        r = requests.get(f"{_WX_HOST}/v3/location/point",
                         params={"apiKey": _WU_API_KEY, "language": "en-US",
                                 "icaoCode": icao, "format": "json"},
                         headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code == 401 and _refresh_api_key():
            r = requests.get(f"{_WX_HOST}/v3/location/point",
                             params={"apiKey": _WU_API_KEY, "language": "en-US",
                                     "icaoCode": icao, "format": "json"},
                             headers=_HEADERS, timeout=TIMEOUT)
        if r.ok:
            cc = r.json().get("location", {}).get("countryCode")
            _country_cache[icao] = cc
            return cc
    except Exception as e:
        logger.warning("WU country-code lookup failed for %s: %s", icao, e)
    _country_cache[icao] = None
    return None


def get_historical_high_native(icao: str, target_date: str, unit: str) -> float:
    """
    Fetch the official WU daily HIGH for the station's local calendar day, returned
    as an INTEGER print in the market's NATIVE unit ('F' → °F, 'C'/'metric' → °C).

    This is the value Polymarket scores from. It is the max over the day's hourly
    observations (WU's history-page 'High'), matched on the station-local day window.

    Raises WundergroundError on failure (so callers can fall back to ASOS/ERA5).
    """
    cc = _country_code(icao)
    if not cc:
        raise WundergroundError(f"WU: no country code for {icao}")
    api_unit = "e" if str(unit).upper().startswith("F") else "m"  # e=°F, m=°C
    loc = f"{icao}:9:{cc}"
    ymd = target_date.replace("-", "")
    url = f"{_WX_HOST}/v1/location/{loc}/observations/historical.json"
    params = {"apiKey": _WU_API_KEY, "units": api_unit, "startDate": ymd, "endDate": ymd}
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code == 401 and _refresh_api_key():
            params["apiKey"] = _WU_API_KEY
            r = requests.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT)
        if not r.ok:
            raise WundergroundError(f"WU api.weather.com HTTP {r.status_code} for {icao} {target_date}")
        obs = r.json().get("observations", [])
        temps = [o.get("temp") for o in obs if o.get("temp") is not None]
        if not temps:
            raise WundergroundError(f"WU api.weather.com no obs for {icao} {target_date}")
        hi = max(temps)
        logger.info("WU %s %s: daily high = %s°%s (api.weather.com, %d obs)",
                    icao, target_date, hi, api_unit.upper(), len(temps))
        return float(hi)
    except WundergroundError:
        raise
    except Exception as e:
        raise WundergroundError(f"WU api.weather.com fetch failed for {icao} {target_date}: {e}") from e


def get_today_max_native(icao: str, today_local: str, unit: str) -> float | None:
    """
    The High WU's page shows for the CURRENT day, in the native unit.

    The page's intraday High is the CONTINUOUS sensor max, not the max of the
    hourly observation table — verified KDEN 2026-06-12: page High 90°F
    (v3 temperatureMaxSince7Am) while the hourly obs list peaked at 87°F (the
    90° spike happened between hourly prints). So: max of the v3 since-7am
    continuous field and today's hourly-obs max (which covers midnight–7am,
    the window since-7am misses). Returns None if both sources fail.
    """
    api_unit = "e" if str(unit).upper().startswith("F") else "m"
    candidates = []
    try:
        r = requests.get(f"{_WX_HOST}/v3/wx/observations/current",
                         params={"apiKey": _WU_API_KEY, "units": api_unit,
                                 "icaoCode": icao, "language": "en-US", "format": "json"},
                         headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code == 401 and _refresh_api_key():
            r = requests.get(f"{_WX_HOST}/v3/wx/observations/current",
                             params={"apiKey": _WU_API_KEY, "units": api_unit,
                                     "icaoCode": icao, "language": "en-US", "format": "json"},
                             headers=_HEADERS, timeout=TIMEOUT)
        if r.ok:
            j = r.json()
            # Guard: only trust since-7am if the ob is actually from today local
            if str(j.get("validTimeLocal", ""))[:10] == today_local:
                v = j.get("temperatureMaxSince7Am")
                if v is not None:
                    candidates.append(float(v))
    except Exception as e:
        logger.debug("WU v3 current obs failed for %s: %s", icao, e)
    try:
        candidates.append(get_historical_high_native(icao, today_local, unit))
    except Exception as e:
        logger.debug("WU hourly-obs max failed for %s: %s", icao, e)
    return max(candidates) if candidates else None


def get_hourly_forecast_native(icao: str, target_date: str, unit: str) -> list[dict]:
    """
    TWC hourly temperature FORECAST for the station's target local date — the same
    forecast rendered on the WU page (api.weather.com backs both). Used by the
    dashboard outlook so its projected high matches what a WU reader sees.

    Returns [{"time": "HH:MM", "temp": float}] in the requested native unit,
    restricted to hours falling on target_date. The feed starts at 'now', so for
    a same-day target the already-elapsed hours are absent — live observations
    cover those. Raises WundergroundError on failure (callers fall back to
    Open-Meteo).
    """
    api_unit = "e" if str(unit).upper().startswith("F") else "m"
    url = f"{_WX_HOST}/v3/wx/forecast/hourly/2day"
    params = {"apiKey": _WU_API_KEY, "units": api_unit, "icaoCode": icao,
              "language": "en-US", "format": "json"}
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code == 401 and _refresh_api_key():
            params["apiKey"] = _WU_API_KEY
            r = requests.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT)
        if not r.ok:
            raise WundergroundError(f"TWC hourly forecast HTTP {r.status_code} for {icao}")
        j = r.json()
        times = j.get("validTimeLocal") or []
        temps = j.get("temperature") or []
        out = [{"time": t[11:16], "temp": float(v)}
               for t, v in zip(times, temps)
               if v is not None and t[:10] == target_date]
        if not out:
            raise WundergroundError(f"TWC hourly forecast: no hours on {target_date} for {icao}")
        return out
    except WundergroundError:
        raise
    except Exception as e:
        raise WundergroundError(f"TWC hourly forecast failed for {icao}: {e}") from e


_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRY_DELAYS = [2, 4]  # seconds between attempts (3 total attempts)


def _fetch_wu_page(icao: str, target_date: str) -> str:
    """Fetch raw HTML of the WU history page for an ICAO station and date.

    Retries up to 3 attempts with exponential backoff (2s, 4s) on transient
    errors: HTTP 429/500/502/503/504, ConnectionError, and Timeout.
    """
    url = f"https://www.wunderground.com/history/daily/{icao}/date/{target_date}"
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.debug("WU retry %d/%d for %s %s (backoff %ds)",
                         attempt + 1, len(_RETRY_DELAYS) + 1, icao, target_date, delay)
            time.sleep(delay)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            logger.debug("WU ConnectionError (attempt %d): %s", attempt + 1, e)
        except requests.exceptions.Timeout as e:
            last_exc = e
            logger.debug("WU Timeout (attempt %d): %s", attempt + 1, e)
        except requests.exceptions.HTTPError as e:
            last_exc = e
            if e.response is not None and e.response.status_code in _RETRY_STATUS_CODES:
                logger.debug("WU HTTP %d (attempt %d): %s",
                             e.response.status_code, attempt + 1, e)
            else:
                raise WundergroundError(
                    f"WU page fetch failed for {icao} {target_date}: {e}"
                ) from e
        except requests.RequestException as e:
            raise WundergroundError(
                f"WU page fetch failed for {icao} {target_date}: {e}"
            ) from e
    raise WundergroundError(
        f"WU page fetch failed for {icao} {target_date} after "
        f"{len(_RETRY_DELAYS) + 1} attempts: {last_exc}"
    ) from last_exc


def _extract_json_blob(html: str) -> dict | None:
    """
    WU embeds its React state in the largest <script> tag as a JSON blob.
    Try to extract temperature observations from it.
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if not scripts:
        return None
    big = max(scripts, key=len)
    try:
        data = json.loads(big)
        return data
    except (json.JSONDecodeError, ValueError):
        return None


def _walk(obj, key, depth=0):
    """Recursively search for a key in a nested dict/list."""
    if depth > 10:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _walk(v, key, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj[:20]:
            r = _walk(item, key, depth + 1)
            if r is not None:
                return r
    return None


def _parse_daily_high_from_blob(data: dict) -> float | None:
    """
    Navigate the WU JSON blob to find the daily high temperature in °C.
    WU stores metric values under 'metric' sub-objects.
    """
    # Try multiple known paths
    for high_key in ["tempHigh", "maxTemp", "high", "maxTempAvg"]:
        val = _walk(data, high_key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    # Try to find hourly obs and compute max
    obs = _walk(data, "observations")
    if obs and isinstance(obs, list) and len(obs) > 1:
        temps = []
        for o in obs:
            # Try metric temp first, then imperial
            t = None
            metric = o.get("metric") or {}
            if "temp" in metric:
                t = metric["temp"]
            elif "tempAvg" in metric:
                t = metric["tempAvg"]
            else:
                imperial = o.get("imperial") or {}
                if "temp" in imperial:
                    try:
                        t = (float(imperial["temp"]) - 32) * 5 / 9  # F → C
                    except (TypeError, ValueError):
                        pass
            if t is not None:
                try:
                    temps.append(float(t))
                except (TypeError, ValueError):
                    pass
        if temps:
            return max(temps)

    return None


def get_historical_high(icao: str, target_date: str) -> float:
    """
    Fetch the daily recorded high temperature (°C) from Wunderground.
    target_date: 'YYYY-MM-DD'
    Raises WundergroundError if unavailable or parsing fails.

    Uses the api.weather.com backend (the data WU's history page renders) first;
    falls back to legacy HTML scraping only if the backend path fails. Returns °C
    (the metric integer print); for native-unit / PM-exact bucket math use
    get_historical_high_native().
    """
    try:
        return get_historical_high_native(icao, target_date, "C")
    except WundergroundError as e:
        logger.warning("WU api.weather.com path failed for %s %s (%s) — trying legacy HTML",
                       icao, target_date, e)

    html = _fetch_wu_page(icao, target_date)
    blob = _extract_json_blob(html)

    if blob:
        high = _parse_daily_high_from_blob(blob)
        if high is not None:
            logger.info("WU %s %s: daily high = %.1f°C", icao, target_date, high)
            return high

    # Attempt regex extraction from raw HTML as last resort
    # Look for the summary table values
    patterns = [
        r'"tempHigh"\s*:\s*(-?\d+\.?\d*)',
        r'"maxTemp"\s*:\s*(-?\d+\.?\d*)',
        r'"highTemp"\s*:\s*(-?\d+\.?\d*)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            val = float(m.group(1))
            logger.info("WU %s %s: regex extracted %.1f°C", icao, target_date, val)
            return val

    raise WundergroundError(
        f"Could not extract daily high from WU page for {icao} {target_date}. "
        f"Page may require JS rendering."
    )


def get_live_hourly(icao: str) -> list[dict]:
    """
    Fetch today's hourly observations from Wunderground.
    Returns list of {time_local, temp_c} sorted by time.
    Raises WundergroundError if unavailable.
    """
    today_str = date.today().isoformat()
    html = _fetch_wu_page(icao, today_str)
    blob = _extract_json_blob(html)

    if not blob:
        raise WundergroundError(f"Could not parse WU JSON for {icao} today")

    obs = _walk(blob, "observations")
    if not obs or not isinstance(obs, list):
        raise WundergroundError(f"No observations in WU response for {icao} today")

    hourly = []
    for o in obs:
        t = None
        time_local = o.get("obsTimeLocal") or o.get("valid_time_gmt", "")

        metric = o.get("metric") or {}
        if "temp" in metric:
            t = metric["temp"]
        elif "tempAvg" in metric:
            t = metric["tempAvg"]
        else:
            imperial = o.get("imperial") or {}
            if "temp" in imperial:
                try:
                    t = (float(imperial["temp"]) - 32) * 5 / 9
                except (TypeError, ValueError):
                    pass

        if t is not None:
            try:
                hourly.append({"time_local": str(time_local), "temp_c": float(t)})
            except (TypeError, ValueError):
                pass

    if not hourly:
        raise WundergroundError(f"Parsed 0 hourly observations for {icao} today")

    return sorted(hourly, key=lambda x: x["time_local"])


def get_running_max_wu(icao: str) -> float | None:
    """
    Get today's running maximum temperature from WU.
    Returns max temp in °C, or None if WU is unavailable.
    Does NOT raise — live obs are optional (METAR is the primary live source).
    """
    try:
        hourly = get_live_hourly(icao)
        if hourly:
            return max(o["temp_c"] for o in hourly)
        return None
    except WundergroundError as e:
        logger.warning("WU live obs unavailable for %s: %s", icao, e)
        return None
