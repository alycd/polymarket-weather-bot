"""
Per-station, per-model, per-calendar-month bias corrector.

bias = mean(actual_high - model_predicted_high) over the past N days.

Computed from real historical data stored in the DB.
Never hardcoded. Requires MIN_HISTORY_DAYS of observations before trading.
"""
import logging
import math
from collections import defaultdict
from datetime import date as _date, datetime
from config_active import (
    MIN_HISTORY_DAYS, OPENMETEO_MODELS, CITY_FORECAST_BIAS_C,
    PERSISTENCE_BIAS_WEIGHT, MIN_PERSISTENCE_DAYS
)
import db

BIAS_DECAY_HALFLIFE_DAYS = 180   # observations older than 6 months get half the weight
MIN_BIAS_SAMPLES = 5             # minimum matched (actual, forecast) pairs before storing a monthly bias

logger = logging.getLogger(__name__)


def recompute_bias(icao: str) -> dict:
    """
    Recompute and store bias corrections for all models for this station.
    Uses the intersection of historical_obs dates and model_forecasts dates.

    Returns dict: {model_name: {month: bias_c, ...}}
    """
    # Get all historical obs for this station (use 'asos' source preferentially,
    # fall back to 'openmeteo_archive')
    obs_rows = db.get_historical_obs(icao)
    if not obs_rows:
        logger.warning("%s: no historical observations for bias computation", icao)
        return {}

    # Circular bias guard: if ALL obs are from ERA5 archive and the model forecasts
    # stored for this station were also derived from ERA5 archive (backfill proxy),
    # then bias = mean(ERA5 - ERA5) ≈ 0 — meaningless. Detect this by checking
    # whether ANY obs row has source='asos' or 'wunderground' (real-world ground truth).
    # Wunderground is Polymarket's primary resolution source, so it counts as real obs.
    # International stations without ASOS/WU coverage (London, Paris, Milan, etc.) fall
    # into the circular category until WU obs accumulate from live resolution fetches.
    has_real_obs = any(row["source"] in ("asos", "wunderground") for row in obs_rows)
    if not has_real_obs:
        logger.warning(
            "Skipping bias for %s: obs and forecasts both from ERA5 archive (circular) — "
            "no ASOS/Wunderground ground-truth available for this station",
            icao,
        )
        # Still update status so the station can be marked ready for raw forecasting
        n_days = len({row["obs_date"] for row in obs_rows})
        status = "ready" if n_days >= MIN_HISTORY_DAYS else "warming_up"
        db.set_station_status(icao, status, history_days=n_days)
        return {}

    # Build date → actual_high_c map (prefer real obs over ERA5 archive)
    # Priority: ASOS or Wunderground > ERA5 archive (since WU = Polymarket's resolution source)
    date_actual: dict[str, float] = {}
    for row in obs_rows:
        d = row["obs_date"]
        is_real = row["source"] in ("asos", "wunderground")
        if d not in date_actual or is_real:
            date_actual[d] = row["actual_high_c"]

    # Get all model forecasts for this station
    forecast_rows = db.get_historical_forecasts(icao)

    # Build date × model → predicted_high_c (latest forecast per date)
    date_model_pred: dict[str, dict[str, float]] = defaultdict(dict)
    for row in forecast_rows:
        d = row["target_date"]
        m = row["model_name"]
        # Overwrite — later rows (later fetched_at) win
        date_model_pred[d][m] = row["predicted_high_c"]

    # Compute bias per model per month with exponential recency weighting
    # Store (diff, date_str) tuples so we can compute days_ago at weighting time
    biases: dict[str, dict[int, list[tuple[float, str]]]] = {
        model: defaultdict(list) for model in OPENMETEO_MODELS
    }

    matched = 0
    for d, actual in date_actual.items():
        month = int(d[5:7])
        preds = date_model_pred.get(d, {})
        for model, pred in preds.items():
            if model in biases:
                biases[model][month].append((actual - pred, d))
                matched += 1

    logger.info("%s: %d (date, model) pairs matched for bias", icao, matched)

    today_str = _date.today().isoformat()

    # Store in DB — require minimum samples per (model, month) pair to avoid
    # extremely noisy bias estimates from 1-2 data points.
    result = {}
    for model, month_data in biases.items():
        result[model] = {}
        for month, diff_date_pairs in month_data.items():
            if len(diff_date_pairs) < MIN_BIAS_SAMPLES:
                logger.debug("  %s %s M%02d: only %d sample(s) — skipping bias (need %d)",
                             icao, model, month, len(diff_date_pairs), MIN_BIAS_SAMPLES)
                continue
            # Exponential decay: weight = exp(-days_ago / halflife)
            # so that recent observations count more than old ones
            w_sum = 0.0
            wdiff_sum = 0.0
            for diff, d in diff_date_pairs:
                try:
                    days_ago = (_date.fromisoformat(today_str) - _date.fromisoformat(d)).days
                except ValueError:
                    days_ago = 0
                weight = math.exp(-days_ago / BIAS_DECAY_HALFLIFE_DAYS)
                w_sum    += weight
                wdiff_sum += weight * diff
            bias_c = wdiff_sum / w_sum if w_sum > 0 else 0.0
            db.upsert_bias(icao, model, month, bias_c, len(diff_date_pairs))
            result[model][month] = bias_c
            logger.debug("  %s %s M%02d: bias=%.2f°C (n=%d, decay-weighted)",
                         icao, model, month, bias_c, len(diff_date_pairs))

    # Update station status
    n_days = len(date_actual)
    status = "ready" if n_days >= MIN_HISTORY_DAYS else "warming_up"
    db.set_station_status(icao, status, history_days=n_days)
    logger.info("%s: status=%s (%d days of history)", icao, status, n_days)
    return result


def get_persistence_bias(icao: str, model_name: str) -> float:
    """
    Compute short-term persistence bias: mean(actual - predicted) over last 7 days.
    If less than MIN_PERSISTENCE_DAYS available, returns 0.0.
    """
    recent = db.get_recent_performance(icao, days=7)
    if not recent:
        return 0.0

    model_errors = [r["actual_high_c"] - r["predicted_high_c"]
                    for r in recent if r["model_name"] == model_name]

    if len(model_errors) < MIN_PERSISTENCE_DAYS:
        return 0.0

    return sum(model_errors) / len(model_errors)


def apply_bias(icao: str, model_name: str, predicted_high_c: float,
               target_date: str) -> float:
    """
    Apply stored bias correction to a model forecast.
    Blends:
      - Seasonal monthly bias (climatological baseline)
      - Persistence bias (recent 7-day performance alpha)

    Returns bias-corrected prediction in °C.
    """
    month = int(target_date[5:7])
    seasonal_bias = db.get_bias(icao, model_name, month)

    # If no seasonal bias, we have no long-term baseline — use raw
    if seasonal_bias is None:
        logger.debug("%s %s M%02d: no seasonal bias, using raw forecast %.1f°C",
                     icao, model_name, month, predicted_high_c)
        return predicted_high_c

    # Persistence Alpha (Short-term momentum)
    p_bias = get_persistence_bias(icao, model_name)

    # Blend: (1-w)*seasonal + w*persistence
    # Only blend if p_bias is non-zero (meaning we have enough recent data)
    if abs(p_bias) > 0.001:
        combined_bias = (1.0 - PERSISTENCE_BIAS_WEIGHT) * seasonal_bias + \
                         PERSISTENCE_BIAS_WEIGHT * p_bias
        logger.debug("%s %s: seasonal=%.2f recent=%.2f blend=%.2f",
                     icao, model_name, seasonal_bias, p_bias, combined_bias)
    else:
        combined_bias = seasonal_bias

    corrected = predicted_high_c + combined_bias
    logger.debug("%s %s: raw=%.1f combined_bias=%+.2f → corrected=%.1f",
                 icao, model_name, predicted_high_c, combined_bias, corrected)
    return corrected


def _apply_city_bias(icao: str, corrected: dict[str, float]) -> dict[str, float]:
    """Apply per-city additive bias from CITY_FORECAST_BIAS_C (config) if present."""
    from config_active import CITIES
    city = next((c for c, cfg in CITIES.items() if cfg["icao"] == icao), None)
    if city and city in CITY_FORECAST_BIAS_C:
        bias = CITY_FORECAST_BIAS_C[city]
        return {m: v + bias for m, v in corrected.items()}
    return corrected


def get_corrected_ensemble(icao: str, raw_forecasts: dict[str, float],
                            target_date: str) -> dict[str, float]:
    """
    Apply bias correction to all model forecasts.
    Returns {model_name: corrected_high_c}
    """
    corrected = {}
    for model, raw in raw_forecasts.items():
        corrected[model] = apply_bias(icao, model, raw, target_date)
    return _apply_city_bias(icao, corrected)


def get_corrected_ensemble_at_date(icao: str, raw_forecasts: dict[str, float],
                                    target_date: str,
                                    cutoff_date: str) -> dict[str, float]:
    """
    Point-in-time bias correction: compute bias using only observations
    that were available before cutoff_date. Used by backtests to avoid
    look-ahead bias from future observations being baked into corrections.

    Falls back to raw forecast for any model with fewer than 3 matched pairs.
    """
    month = int(target_date[5:7])

    # Only use obs available before the cutoff
    obs_rows = [r for r in db.get_historical_obs(icao) if r["obs_date"] < cutoff_date]
    if not obs_rows:
        return dict(raw_forecasts)

    # Circular bias guard: skip bias correction for stations with only ERA5 obs
    # (ERA5 vs ERA5 model proxy = ~0 bias, meaningless for international stations)
    has_real_obs = any(
        row["source"] in ("asos", "wunderground")
        for row in obs_rows
        if row["obs_date"] < cutoff_date
    )
    if not has_real_obs:
        return dict(raw_forecasts)

    # Build date → actual_high_c (prefer ASOS over archive)
    date_actual: dict[str, float] = {}
    for row in obs_rows:
        d = row["obs_date"]
        if d not in date_actual or row["source"] == "asos":
            date_actual[d] = row["actual_high_c"]

    # Forecasts available before cutoff
    forecast_rows = [r for r in db.get_historical_forecasts(icao) if r["target_date"] < cutoff_date]
    from collections import defaultdict
    date_model_pred: dict[str, dict[str, float]] = defaultdict(dict)
    for row in forecast_rows:
        date_model_pred[row["target_date"]][row["model_name"]] = row["predicted_high_c"]

    # Compute per-model bias for this calendar month using pre-cutoff data only
    corrected = {}
    for model, raw in raw_forecasts.items():
        pairs: list[tuple[float, str]] = []
        for d, actual in date_actual.items():
            if int(d[5:7]) != month:
                continue
            pred = date_model_pred.get(d, {}).get(model)
            if pred is not None:
                pairs.append((actual - pred, d))

        if len(pairs) < 3:
            # Insufficient pre-cutoff data — use raw
            corrected[model] = raw
            continue

        # Exponential decay weighted mean (same as recompute_bias)
        w_sum = wdiff = 0.0
        for diff, d in pairs:
            try:
                days_ago = (_date.fromisoformat(cutoff_date) - _date.fromisoformat(d)).days
            except ValueError:
                days_ago = 0
            w = math.exp(-days_ago / BIAS_DECAY_HALFLIFE_DAYS)
            w_sum += w
            wdiff += w * diff
        bias = wdiff / w_sum if w_sum > 0 else 0.0
        corrected[model] = raw + bias

    return _apply_city_bias(icao, corrected)


def get_model_weights(icao: str) -> dict[str, float] | None:
    """
    Compute data-driven per-model inverse-variance weights for this station.

    Uses historical (actual - model_forecast) squared errors with the same
    exponential recency decay as bias correction.  Models with lower historical
    RMSE receive higher weight.

    Returns {model_name: weight} normalised so mean weight = 1.0.
    Models with fewer than MIN_SAMPLES observations use their hardcoded weight
    instead of a data-driven estimate (per-model fallback, not all-or-nothing).
    Returns None if NO model has MIN_SAMPLES observations (no history at all).
    """
    MIN_SAMPLES = 10

    obs_rows = db.get_historical_obs(icao)
    if not obs_rows:
        return None

    # Build date → actual map; prefer real obs (ASOS/WU) over ERA5 archive
    date_actual: dict[str, float] = {}
    for row in obs_rows:
        d = row["obs_date"]
        is_real = row["source"] in ("asos", "wunderground")
        if d not in date_actual or is_real:
            date_actual[d] = row["actual_high_c"]

    if not date_actual:
        return None

    # Build date × model → predicted (latest fetch wins)
    forecast_rows = db.get_historical_forecasts(icao)
    date_model_pred: dict[str, dict[str, float]] = defaultdict(dict)
    for row in forecast_rows:
        date_model_pred[row["target_date"]][row["model_name"]] = row["predicted_high_c"]

    today_str = _date.today().isoformat()

    # Accumulate weighted squared errors per model
    wmse:  dict[str, float] = {}
    wsum:  dict[str, float] = {}
    count: dict[str, int]   = {}

    for d, actual in date_actual.items():
        preds = date_model_pred.get(d, {})
        try:
            days_ago = (_date.fromisoformat(today_str) - _date.fromisoformat(d)).days
        except ValueError:
            days_ago = 0
        w = math.exp(-days_ago / BIAS_DECAY_HALFLIFE_DAYS)
        for model, pred in preds.items():
            err2 = (actual - pred) ** 2
            wmse[model]  = wmse.get(model, 0.0)  + w * err2
            wsum[model]  = wsum.get(model, 0.0)  + w
            count[model] = count.get(model, 0)   + 1

    # Per-model fallback: if a model has insufficient samples, use its hardcoded weight
    # (instead of returning None and falling back to hardcoded for ALL models).
    # If NO model has MIN_SAMPLES, return None — no data-driven information at all.
    from signals.ensemble import _MODEL_WEIGHTS as _HARDCODED_W, _DEFAULT_WEIGHT

    models_with_data = [m for m in OPENMETEO_MODELS if count.get(m, 0) >= MIN_SAMPLES]
    if not models_with_data:
        logger.debug("%s: no model has %d+ samples yet — using all hardcoded weights", icao, MIN_SAMPLES)
        return None

    for model in OPENMETEO_MODELS:
        if count.get(model, 0) < MIN_SAMPLES:
            logger.debug("%s: %s has only %d samples (< %d) — using hardcoded weight %.1f",
                         icao, model, count.get(model, 0), MIN_SAMPLES,
                         _HARDCODED_W.get(model, _DEFAULT_WEIGHT))

    # Compute RMSE only for models with enough data
    rmse_dd = {m: math.sqrt(wmse[m] / wsum[m]) for m in models_with_data}

    # Inverse-variance for data-driven models; hardcoded for the rest
    # Compute normalisation over data-driven models only, then blend in hardcoded
    raw_w_dd = {m: 1.0 / (r ** 2) for m, r in rmse_dd.items()}
    mean_w_dd = sum(raw_w_dd.values()) / len(raw_w_dd)

    weights = {}
    for model in OPENMETEO_MODELS:
        if model in raw_w_dd:
            weights[model] = max(0.3, min(3.0, raw_w_dd[model] / mean_w_dd))
        else:
            # Use hardcoded weight scaled to the same mean as data-driven models
            weights[model] = _HARDCODED_W.get(model, _DEFAULT_WEIGHT)

    # Re-normalise so mean weight across all models = 1.0
    final_mean = sum(weights.values()) / len(weights)
    weights = {m: max(0.3, min(3.0, w / final_mean)) for m, w in weights.items()}

    logger.info("%s: model weights (dd=%s hardcoded=%s): %s  (rmse: %s)",
                icao,
                sorted(models_with_data),
                sorted(m for m in OPENMETEO_MODELS if m not in models_with_data),
                {m: round(v, 2) for m, v in weights.items()},
                {m: round(r, 2) for m, r in rmse_dd.items()})
    return weights


def station_is_ready(icao: str) -> bool:
    station = db.get_station(icao)
    if not station:
        return False
    return station["status"] == "ready"
