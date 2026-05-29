"""
Mid-day nowcaster.

After 2pm local city time:
  - Pull live METAR + ASOS for today
  - If WU and METAR disagree by > 2°C → flag as uncertain
  - Track running maximum temperature
  - Weight: 0.0 at noon, 0.5 at 2pm, 0.95 at 4pm (linear)
  - If running_max is already outside the crowd's top 2 buckets → near-certain trade

The nowcast confidence weight blends in with the model probability:
  blended_prob = (1 - weight) * model_prob + weight * nowcast_prob
"""
import logging
import math
from datetime import datetime, date
import pytz
from config_active import CITIES
from data.noaa import get_running_max_today, fetch_metar
from data.wunderground import get_running_max_wu

logger = logging.getLogger(__name__)


def _local_hour(timezone_str: str) -> float:
    """Current local hour (fractional) in the given timezone."""
    tz = pytz.timezone(timezone_str)
    now_local = datetime.now(tz)
    return now_local.hour + now_local.minute / 60.0


def nowcast_confidence(timezone_str: str) -> float:
    """
    Returns a confidence weight [0, 1] based on local time.
    0.0 before noon, linearly rising from 0.5 at 2pm to 0.95 at 4pm.
    """
    hour = _local_hour(timezone_str)
    if hour < 12.0:
        return 0.0
    if hour < 14.0:
        # Ramp 0 → 0.5 between noon and 2pm
        return 0.5 * (hour - 12.0) / 2.0
    if hour < 16.0:
        # Ramp 0.5 → 0.95 between 2pm and 4pm
        return 0.5 + 0.45 * (hour - 14.0) / 2.0
    return 0.95


def get_running_max_c(city_name: str) -> tuple[float | None, float | None]:
    """
    Get today's running max temperature and temperature trend for a city.

    Returns (running_max_c, temp_rate_c_per_h).
      running_max_c    — highest temperature observed so far today (°C), or None
      temp_rate_c_per_h — rate of change over last ~2h (°C/h), or None if < 3 obs
          > 0  = still warming
          < 0  = cooling / past peak

    Priority: METAR (point-in-time) combined with ASOS (running max + rate),
    then ASOS alone, then WU alone (no rate available from WU).
    """
    cfg = CITIES.get(city_name)
    if not cfg:
        return None, None
    icao = cfg["icao"]
    asos = cfg["asos_station"]
    tz   = cfg["timezone"]

    # 1. Try METAR (most current point-in-time) combined with ASOS running max + rate
    try:
        metar_data = fetch_metar([icao])
        if icao in metar_data:
            temp_c = metar_data[icao]["temp_c"]
            logger.debug("METAR %s: current %.1f°C", icao, temp_c)
            asos_result = get_running_max_today(asos, tz)
            if asos_result:
                running_max = max(temp_c, asos_result["running_max_c"])
                rate = asos_result.get("temp_rate_c_per_h")
            else:
                running_max = temp_c
                rate = None

            # Cross-check with WU (advisory only — never veto METAR)
            wu_max = get_running_max_wu(icao)
            if wu_max is not None:
                if abs(wu_max - running_max) > 2.0:
                    logger.warning(
                        "%s: WU (%.1f°C) and METAR/ASOS (%.1f°C) disagree by > 2°C — "
                        "trusting METAR/ASOS (WU scraping may be stale)",
                        icao, wu_max, running_max
                    )
                else:
                    running_max = max(running_max, wu_max)

            return running_max, rate
    except Exception as e:
        logger.warning("METAR fetch failed for %s: %s", icao, e)

    # 2. ASOS only
    asos_result = get_running_max_today(asos, tz)
    if asos_result:
        return asos_result["running_max_c"], asos_result.get("temp_rate_c_per_h")

    # 3. WU only (no rate available)
    wu_max = get_running_max_wu(icao)
    return wu_max, None


def compute_nowcast_bucket_prob(
    running_max_c: float,
    confidence: float,
    ensemble_mean_c: float,
    ensemble_effective_std: float,
    bucket_lo_c: float | None,
    bucket_hi_c: float | None,
    temp_rate_c_per_h: float | None = None,
) -> float:
    """
    Blend the model probability with the nowcast observation.

    Strategy: as the day progresses, the running max provides an increasingly
    strong lower bound on the final daily max. We model the final max as:
        final_max ~ max(running_max, t(ensemble_mean, effective_std))
    which we approximate as:
        P(bucket | running_max) ∝ original_prob re-weighted by the observation

    temp_rate_c_per_h: temperature trend from recent ASOS hourly obs.
        < -0.5°C/h  → clearly past peak → boost confidence toward running_max
        > +1.5°C/h  → still warming fast → trust model residual more (reduce confidence)
        Otherwise   → no adjustment
    """
    # Adjust confidence based on temperature trend (rate-of-change)
    if temp_rate_c_per_h is not None:
        if temp_rate_c_per_h < -0.5:
            # Temperature is falling — running_max is almost certainly the day's high
            confidence = min(0.99, confidence + 0.20)
            logger.debug("Rate %.2f°C/h (falling) → confidence boosted to %.2f",
                         temp_rate_c_per_h, confidence)
        elif temp_rate_c_per_h > 1.5:
            # Still warming fast — model's residual upside is plausible
            confidence = max(0.0, confidence - 0.15)
            logger.debug("Rate %.2f°C/h (rising fast) → confidence reduced to %.2f",
                         temp_rate_c_per_h, confidence)

    from scipy.stats import t as _t
    from config_active import FORECAST_T_DF

    # Convert bucket to °C if needed (caller handles unit conversion before calling)
    lo = bucket_lo_c if bucket_lo_c is not None else -999.0
    hi = bucket_hi_c if bucket_hi_c is not None else 999.0

    # Model probability — Student's t for fat-tail consistency with edge_calculator
    model_prob = _t.cdf(hi, FORECAST_T_DF, loc=ensemble_mean_c, scale=ensemble_effective_std) - \
                 _t.cdf(lo, FORECAST_T_DF, loc=ensemble_mean_c, scale=ensemble_effective_std)

    if confidence < 0.05:
        return model_prob

    # ── Hard boundary constraints ──────────────────────────────────────────────
    # daily_max ≥ running_max is a physical certainty (you can't un-observe a temp).
    # When the observation definitively settles the outcome, bypass the soft blend.
    #
    # METAR/ASOS sensors can read 0.5–1°C warmer than the temperature source
    # Polymarket uses for resolution (e.g. airport tarmac vs nearby AWS). A 1°C
    # margin prevents premature hard-zeros caused by this sensor offset.
    _HARD_ZERO_MARGIN_C = 1.0  # °C above bucket_hi before declaring YES impossible

    # Case 1: running_max ≥ bucket_hi + margin → YES is impossible.
    #   e.g. running_max=29°C and bucket=[25.5,26.5)°C — the high is already well
    #   above the ceiling, so the bucket cannot resolve YES regardless of what happens next.
    if bucket_hi_c is not None and running_max_c >= bucket_hi_c + _HARD_ZERO_MARGIN_C:
        logger.debug(
            "Nowcast hard-zero: running_max=%.1f >= bucket_hi=%.1f + margin=%.1f — YES impossible",
            running_max_c, bucket_hi_c, _HARD_ZERO_MARGIN_C,
        )
        return 0.0

    # Case 2: running_max ≥ bucket_lo and bucket has no ceiling (≥X markets) →
    #   YES is already guaranteed (the daily high has hit the threshold).
    if bucket_hi_c is None and bucket_lo_c is not None and running_max_c >= bucket_lo_c:
        logger.debug(
            "Nowcast hard-one: running_max=%.1f >= bucket_lo=%.1f — YES guaranteed",
            running_max_c, bucket_lo_c,
        )
        return 1.0

    # Nowcast lower bound: the final max must be >= running_max
    # P(final_max in [lo, hi] | final_max >= running_max)
    # = P(running_max <= final_max < hi) / P(final_max >= running_max)
    effective_lo = max(lo, running_max_c)
    p_above_running = 1.0 - _t.cdf(running_max_c, FORECAST_T_DF, loc=ensemble_mean_c, scale=ensemble_effective_std)
    if p_above_running < 1e-9:
        # Running max is already way above the distribution
        return 0.0

    nowcast_prob = (
        _t.cdf(hi, FORECAST_T_DF, loc=ensemble_mean_c, scale=ensemble_effective_std) -
        _t.cdf(effective_lo, FORECAST_T_DF, loc=ensemble_mean_c, scale=ensemble_effective_std)
    ) / p_above_running

    nowcast_prob = max(0.0, min(1.0, nowcast_prob))
    blended = (1.0 - confidence) * model_prob + confidence * nowcast_prob

    logger.debug(
        "Nowcast: running_max=%.1f  model_prob=%.3f  nowcast_prob=%.3f  "
        "confidence=%.2f  blended=%.3f",
        running_max_c, model_prob, nowcast_prob, confidence, blended
    )
    return blended
