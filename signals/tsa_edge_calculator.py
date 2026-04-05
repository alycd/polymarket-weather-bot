"""
TSA passenger market edge calculator.

Signal inputs:
  1. Day-of-week baseline (TSA historical data, same page as resolution)
  2. Year-over-year ratio (same source)
  3. Holiday multiplier (hardcoded 2026 date ranges from config)
  4. Hub weather impact (Open-Meteo GFS for KATL/KDFW/KORD/KDEN/KLAX)

Probability model: Gaussian over passenger count, P(count in bucket).
Kelly sizing: identical formula to temperature markets.

Resolution lag: TSA publishes actual counts ~1 day after travel date.
"""
import logging
import math
from datetime import date as _date, timedelta

from scipy.stats import norm

from config import (
    MIN_EDGE, KELLY_FRACTION, MAX_TRADE_FRACTION,
    TSA_HUB_AIRPORTS, TSA_HUB_BAD_WEATHER_MIN_COUNT,
    TSA_WEATHER_DROP_PER_HUB, TSA_BAD_WEATHER_PRECIP_MM, TSA_BAD_WEATHER_WIND_KMH,
    MIN_EDGE_RECENT_MULTIPLIER, MIN_EDGE_RECENT_DAYS,
    HIGH_CONVICTION_EDGE, HIGH_CONVICTION_KELLY_MULT,
)

logger = logging.getLogger(__name__)


# ── Hub weather check ──────────────────────────────────────────────────────────

def check_hub_weather(target_date: str) -> dict:
    """
    Check Open-Meteo GFS for bad weather at the 5 major hub airports on target_date.

    Returns:
        {
            "hub_weather_flag": bool,   # True if >= TSA_HUB_BAD_WEATHER_MIN_COUNT hubs bad
            "bad_hubs":        list,    # ICAO codes of hubs with bad weather
            "weather_factor":  float,   # multiplier to apply to passenger forecast
        }
    """
    import requests
    from config import OPENMETEO_MODELS

    url = OPENMETEO_MODELS.get("gfs", "https://api.open-meteo.com/v1/gfs")
    bad_hubs = []

    for icao, cfg in TSA_HUB_AIRPORTS.items():
        try:
            resp = requests.get(url, params={
                "latitude":          cfg["lat"],
                "longitude":         cfg["lon"],
                "daily":             ["precipitation_sum", "wind_speed_10m_max"],
                "timezone":          cfg["timezone"],
                "forecast_days":     14,
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            times  = data.get("daily", {}).get("time", [])
            precip = data.get("daily", {}).get("precipitation_sum", [])
            wind   = data.get("daily", {}).get("wind_speed_10m_max", [])

            if target_date not in times:
                continue
            idx = times.index(target_date)
            p = precip[idx] if idx < len(precip) else None
            w = wind[idx]   if idx < len(wind)   else None

            if (p is not None and p > TSA_BAD_WEATHER_PRECIP_MM) or \
               (w is not None and w > TSA_BAD_WEATHER_WIND_KMH):
                bad_hubs.append(icao)
                logger.debug("Hub %s: bad weather on %s (precip=%.1f, wind=%.1f)",
                             icao, target_date, p or 0, w or 0)

        except Exception as e:
            logger.debug("Hub weather check failed for %s: %s", icao, e)

    hub_weather_flag = len(bad_hubs) >= TSA_HUB_BAD_WEATHER_MIN_COUNT

    # Weather factor: count drops only for hubs at/beyond the threshold
    affected = max(0, len(bad_hubs) - TSA_HUB_BAD_WEATHER_MIN_COUNT + 1)
    weather_factor = 1.0 - (TSA_WEATHER_DROP_PER_HUB * affected)

    return {
        "hub_weather_flag": hub_weather_flag,
        "bad_hubs":         bad_hubs,
        "weather_factor":   max(0.85, weather_factor),   # floor at -15%
    }


# ── Bucket probability ─────────────────────────────────────────────────────────

def tsa_bucket_prob(mean_m: float, std_m: float,
                    lo_m: float | None, hi_m: float | None) -> float:
    """P(passenger_count in [lo_m, hi_m]) under N(mean_m, std_m). Units: millions."""
    lo = lo_m if lo_m is not None else -math.inf
    hi = hi_m if hi_m is not None else math.inf
    p = norm.cdf(hi, mean_m, std_m) - norm.cdf(lo, mean_m, std_m)
    return float(max(0.0, min(1.0, p)))


# ── Main signal computation ────────────────────────────────────────────────────

def compute_tsa_edge(
    market: dict,
    market_implied_prob: float,
    tsa_data: dict,
    bid: float | None = None,
    ask: float | None = None,
) -> dict | None:
    """
    Compute the full edge signal for one TSA passenger bucket market.

    market: dict with keys target_date, bucket_lo, bucket_hi, bucket_unit='M'
    market_implied_prob: CLOB mid-price for YES outcome
    tsa_data: output of data.tsa.fetch_tsa_data()
    bid/ask: CLOB bid/ask for accurate entry price

    Returns signal dict or None if should be skipped.
    """
    import db
    from data.tsa import (compute_dow_baselines, compute_yoy_ratio,
                          forecast_passengers)

    target_date = str(market.get("target_date", ""))
    bucket_lo   = market.get("bucket_lo")    # millions
    bucket_hi   = market.get("bucket_hi")    # millions

    # ── 1. Build forecast ────────────────────────────────────────────────────
    dow_baselines = compute_dow_baselines(tsa_data)
    yoy_ratio     = compute_yoy_ratio(tsa_data)
    fc = forecast_passengers(target_date, tsa_data, dow_baselines, yoy_ratio)

    if not fc or not fc.get("mean"):
        logger.warning("TSA: no forecast for %s", target_date)
        return None

    # ── 2. Hub weather adjustment ────────────────────────────────────────────
    hub_info = check_hub_weather(target_date)
    adjusted_mean = fc["mean"] / 1_000_000 * hub_info["weather_factor"]  # convert to millions
    adjusted_std  = fc["std"]  / 1_000_000

    # Expand std slightly when hub weather flag is active (higher uncertainty)
    if hub_info["hub_weather_flag"]:
        adjusted_std *= 1.30

    # ── 3. Bucket probability ────────────────────────────────────────────────
    model_prob = tsa_bucket_prob(adjusted_mean, adjusted_std, bucket_lo, bucket_hi)

    # ── 4. Edge ──────────────────────────────────────────────────────────────
    edge      = model_prob - market_implied_prob
    direction = "YES" if model_prob > market_implied_prob else "NO"

    if direction == "YES":
        actual_entry = ask if ask is not None else market_implied_prob
    else:
        actual_entry = (1.0 - bid) if bid is not None else (1.0 - market_implied_prob)

    if direction == "YES":
        effective_edge = model_prob - actual_entry
    else:
        effective_edge = (1.0 - model_prob) - actual_entry

    # ── 5. Skip extreme-entry bets (unrealisable fills in thin markets) ──────
    if direction == "NO" and actual_entry < 0.05:
        return None

    # ── 5b. Skip YES on near-zero buckets ─────────────────────────────────────
    # TSA: threshold is 0.03 (not 0.20 used for temperature).
    # Temperature cheap-YES filter was calibrated on observed 1.5% win rate for
    # buckets the crowd priced near zero — those crowds are well-informed.
    # For TSA, the crowd systematically misprices DOW + holiday interactions, so
    # the correct bucket can genuinely sit at 5–10% market price. We only filter
    # buckets at true noise levels (< 3%).
    if direction == "YES" and market_implied_prob < 0.03:
        return None

    # ── 6. Lead-time aware min edge ──────────────────────────────────────────
    try:
        lead_days = max(1, (_date.fromisoformat(target_date) - _date.today()).days)
    except (ValueError, TypeError):
        lead_days = 3

    if lead_days <= MIN_EDGE_RECENT_DAYS:
        adaptive_min_edge = MIN_EDGE * MIN_EDGE_RECENT_MULTIPLIER
    else:
        adaptive_min_edge = MIN_EDGE

    if abs(effective_edge) < adaptive_min_edge:
        logger.debug("TSA: effective_edge %.3f below threshold %.3f — skip",
                     abs(effective_edge), adaptive_min_edge)
        return None

    # ── 7. Kelly sizing ──────────────────────────────────────────────────────
    bankroll = db.get_bankroll()
    p_win = model_prob if direction == "YES" else (1.0 - model_prob)

    if actual_entry <= 0.001 or actual_entry >= 0.999:
        return None
    b_odds = (1.0 / actual_entry) - 1.0
    if b_odds <= 0:
        return None

    kf = max(0.0, (b_odds * p_win - (1.0 - p_win)) / b_odds)
    kelly_mult = HIGH_CONVICTION_KELLY_MULT if abs(edge) >= HIGH_CONVICTION_EDGE else 1.0
    kf = min(kf * KELLY_FRACTION * kelly_mult, 1.0)
    size_usdc = min(kf * bankroll, MAX_TRADE_FRACTION * bankroll)
    if size_usdc < 1.0:
        return None

    return {
        "direction":           direction,
        "entry_price":         actual_entry,
        "model_prob":          round(model_prob, 4),
        "market_prob":         round(market_implied_prob, 4),
        "edge":                round(edge, 4),
        "effective_edge":      round(effective_edge, 4),
        "size_usdc":           round(size_usdc, 2),
        "kelly_f":             round(kf, 4),
        "lead_days":           lead_days,
        # TSA-specific fields
        "tsa_mean_m":          round(adjusted_mean, 4),
        "tsa_std_m":           round(adjusted_std, 4),
        "tsa_dow_baseline":    round(fc["dow_baseline"] / 1_000_000, 4),
        "tsa_yoy_ratio":       round(fc["yoy_ratio"], 4),
        "tsa_holiday_name":    fc["holiday_name"],
        "tsa_holiday_mult":    fc["holiday_multiplier"],
        "hub_weather_flag":    hub_info["hub_weather_flag"],
        "hub_bad_list":        ",".join(hub_info["bad_hubs"]),
        "weather_factor":      round(hub_info["weather_factor"], 4),
        # Needed by paper_broker
        "ensemble_std_c":      0.0,   # not applicable; sentinel
        "nowcast_weight":      0.0,
        "confidence_tier":     2,     # default tier — TSA data is good quality
    }
