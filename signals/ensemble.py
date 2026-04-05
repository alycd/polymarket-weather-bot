"""
Multi-model ensemble disagreement scorer.

Takes the bias-corrected model predictions and:
  1. Computes freshness-adjusted weighted mean
  2. Computes weighted std dev (disagreement)
  3. Scores the ensemble:
     - std < ENSEMBLE_STD_MIN → models agree → high confidence → still trade
     - std > ENSEMBLE_STD_MAX → models chaotic → too uncertain → skip
     - std in [MIN, MAX] → sweet spot → trade

Model weights (based on published skill scores):
  ecmwf        → 1.8x  (consistently best global model)
  hrrr         → 1.5x  (3km CONUS-only; best short-range US — injected when available)
  icon         → 1.3x  (strong mesoscale, especially Europe)
  gfs          → 1.0x
  gem          → 1.0x  (Canadian; good NA coverage)
  meteofrance  → 1.0x  (aka best_match in Open-Meteo)

All base weights are further scaled by a freshness multiplier that decays
exponentially with the age of each model's most recent available cycle.
"""
import math
import logging
from datetime import date as _date
from config import ENSEMBLE_STD_MIN, ENSEMBLE_STD_MAX, BASE_FORECAST_STD_C, KING_CONFLICT_MAX_C
from signals.model_freshness import get_freshness_weights as _get_freshness_weights

logger = logging.getLogger(__name__)

# Weights by model name (keys match OPENMETEO_MODELS in config.py)
_MODEL_WEIGHTS: dict[str, float] = {
    "ecmwf":       1.8,
    "hrrr":        1.5,   # CONUS only, injected when available — high-res short-range
    "icon":        1.3,
    "gfs":         1.0,
    "gem":         1.0,
    "meteofrance": 1.0,
}
_DEFAULT_WEIGHT = 1.0


def compute_ensemble_stats(corrected_forecasts: dict[str, float],
                           override_weights: dict[str, float] | None = None,
                           target_date: str | None = None) -> dict:
    """
    Given {model_name: corrected_high_c}, compute weighted ensemble statistics.

    override_weights: optional data-driven per-model weights (from
        bias_corrector.get_model_weights).  When provided, these replace the
        hardcoded _MODEL_WEIGHTS for any model present in the dict.

    target_date: used to compute lead-time and scale BASE_FORECAST_STD_C.
        Today (T+0) uses a smaller uncertainty buffer (more aggressive),
        T+5 uses a larger one (more conservative).

    Returns dict with:
      mean_c        — weighted ensemble mean prediction
      std_c         — weighted std dev across models (disagreement)
      effective_std — std_c added in quadrature with BASE_FORECAST_STD_C
      n_models      — number of models used
      values        — list of individual predictions
      weights       — list of corresponding weights
      score         — 'agree' | 'sweet_spot' | 'chaotic'
      tradeable     — bool (False only when chaotic)
      weight_source — 'data_driven' | 'hardcoded'
    """
    if not corrected_forecasts:
        raise ValueError("No model forecasts provided")

    names  = list(corrected_forecasts.keys())
    values = [corrected_forecasts[m] for m in names]
    if override_weights:
        base_weights = [override_weights.get(m, _MODEL_WEIGHTS.get(m, _DEFAULT_WEIGHT)) for m in names]
        weight_source = "data_driven"
    else:
        base_weights = [_MODEL_WEIGHTS.get(m, _DEFAULT_WEIGHT) for m in names]
        weight_source = "hardcoded"

    # Apply model freshness multipliers: a cycle initialized 1h ago outweighs
    # one from 5.5h ago. Weights decay exponentially with FRESHNESS_HALFLIFE_H=6.
    try:
        freshness = _get_freshness_weights()
        weights = [bw * freshness.get(m, 1.0) for bw, m in zip(base_weights, names)]
    except Exception:
        weights = base_weights  # freshness must never block ensemble computation

    total_w = sum(weights)
    mean = sum(w * v for w, v in zip(weights, values)) / total_w

    n = len(values)
    if n > 1:
        # Weighted sample variance with Kish effective-sample-size correction.
        # Simple total_w denominator gives the biased population variance; when
        # weights are unequal (ECMWF=1.8, ICON=1.3 vs others=1.0) it understates
        # disagreement by ~10-15%.  Kish (1965) correction:
        #   effective_n = total_w² / Σ(w_i²)
        #   unbiased denominator = total_w * (1 - 1/effective_n)
        sum_w2 = sum(w ** 2 for w in weights)
        effective_n = total_w ** 2 / sum_w2
        denom = total_w * (1.0 - 1.0 / effective_n) if effective_n > 1 else total_w
        variance = sum(w * (v - mean) ** 2 for w, v in zip(weights, values)) / denom
        std = math.sqrt(variance)
    else:
        std = 0.0

    # Dynamic Lead-Time Uncertainty Scaling
    # Base is for T+2. For T+0 we scale down to ~1.2, for T+7 scale up to ~2.8
    lead_days = 2
    if target_date:
        try:
            lead_days = ( _date.fromisoformat(target_date) - _date.today() ).days
        except Exception:
            pass

    # Scale: uncertainty grows by ~0.2°C per day of lead time
    # This makes the bot MUCH more aggressive on same-day trades where models are precise.
    dynamic_base_std = max(1.1, BASE_FORECAST_STD_C - (2 - lead_days) * 0.25)

    # Effective std: model spread + scaled inherent forecast uncertainty (added in quadrature)
    effective_std = math.sqrt(std ** 2 + dynamic_base_std ** 2)

    if std > ENSEMBLE_STD_MAX:
        score = "chaotic"
    elif std < ENSEMBLE_STD_MIN:
        score = "agree"
    else:
        score = "sweet_spot"

    # High consensus (agree) means MORE reliable, not less — only chaotic is untradeable
    tradeable = score != "chaotic"

    logger.debug(
        "Ensemble: mean=%.1f°C  std=%.2f°C  eff_std=%.2f°C  lead=%d  score=%s  n=%d  "
        "weights=%s  source=%s",
        mean, std, effective_std, lead_days, score, n,
        {m: round(w, 1) for m, w in zip(names, weights)},
        weight_source,
    )

    # King Models Conflict: disagreement between the two high-skill global models.
    ecmwf_val = corrected_forecasts.get("ecmwf")
    gfs_val   = corrected_forecasts.get("gfs")
    king_conflict = False
    if ecmwf_val is not None and gfs_val is not None:
        diff = abs(ecmwf_val - gfs_val)
        if diff > KING_CONFLICT_MAX_C:
            king_conflict = True
            logger.warning("KING CONFLICT: ECMWF and GFS disagree by %.2f°C", diff)

    return {
        "mean_c":        mean,
        "std_c":         std,
        "effective_std": effective_std,
        "n_models":      n,
        "values":        values,
        "weights":       weights,
        "model_names":   names,
        "score":         score,
        "tradeable":     tradeable,
        "weight_source": weight_source,
        "king_conflict": king_conflict,
    }
