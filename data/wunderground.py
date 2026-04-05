"""
Wunderground data fetcher — last-resort fallback for temperature resolution.

Resolution source priority (position_manager.py):
  1. Iowa State ASOS — official airport obs (primary)
  2. Open-Meteo Archive — ERA5 reanalysis (reliable fallback)
  3. Wunderground — this module (last resort; may differ from official records)

WU is also used for live intraday obs in the nowcaster (advisory only).
"""
import re
import json
import logging
import time
import requests
from datetime import date, datetime

logger = logging.getLogger(__name__)

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
    """
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
