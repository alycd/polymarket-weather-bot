"""
Model freshness weighting.

NWP models are initialized at fixed UTC cycle times and take several hours to
process before output is publicly available. A forecast from a model that
became available 30 minutes ago carries more information than one from 5+ hours
ago — the atmosphere has evolved and the newer run has seen that.

Freshness weight = exp(-age_hours / FRESHNESS_HALFLIFE_H)

Age = time elapsed since the model's most recently *available* cycle
      (initialization UTC hour + known processing lag).

This multiplies the base skill weights in compute_ensemble_stats, so a fresh
ECMWF run (1.8 × 0.95 ≈ 1.71) outweighs a stale GFS (1.0 × 0.35 ≈ 0.35)
when the scan happens to fall in that window.
"""
import math
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Half-life for freshness decay. At 6h old a model has 50% of its peak weight;
# at 12h old it has 25%. Models are never fully discarded — floor of ~5%.
FRESHNESS_HALFLIFE_H = 6.0

# UTC availability schedule: (hour, minute) tuples when each model's output
# becomes downloadable = initialization_UTC_hour + processing_lag.
#
# Sources:
#   GFS:         00Z/06Z/12Z/18Z + ~3.5h  → available 03:30 / 09:30 / 15:30 / 21:30
#   ECMWF:       00Z/12Z          + ~6h    → available 06:00 / 18:00
#   ICON:        00Z/06Z/12Z/18Z  + ~3h    → available 03:00 / 09:00 / 15:00 / 21:00
#   GEM:         00Z/12Z          + ~4h    → available 04:00 / 16:00
#   MeteoFrance: 00Z/06Z/12Z/18Z  + ~3h    → available 03:00 / 09:00 / 15:00 / 21:00
#   HRRR:        every hour       + ~1.5h  → handled separately (continuous)
_AVAILABILITY: dict[str, list[tuple[int, int]]] = {
    "gfs":         [(3, 30), (9, 30), (15, 30), (21, 30)],
    "ecmwf":       [(6,  0), (18,  0)],
    "icon":        [(3,  0), (9,  0), (15,  0), (21,  0)],
    "gem":         [(4,  0), (16,  0)],
    "meteofrance": [(3,  0), (9,  0), (15,  0), (21,  0)],
}

_HRRR_LAG_H = 1.5  # HRRR processing lag


def _last_available(model_name: str, now: datetime) -> datetime:
    """Return the UTC datetime of the model's most recently available cycle."""
    if model_name == "hrrr":
        # Continuous hourly cycles: last available = now − lag, floor to hour
        candidate = now - timedelta(hours=_HRRR_LAG_H)
        return candidate.replace(minute=0, second=0, microsecond=0)

    schedule = _AVAILABILITY.get(model_name)
    if not schedule:
        return now  # unknown model → treat as perfectly fresh

    # Check today and yesterday to find the most recent availability time ≤ now
    candidates = []
    for day_offset in (0, -1):
        d = (now + timedelta(days=day_offset)).date()
        for h, m in schedule:
            t = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
            if t <= now:
                candidates.append(t)

    return max(candidates) if candidates else now


def get_freshness_weights(now: datetime | None = None) -> dict[str, float]:
    """
    Return a freshness multiplier in (0, 1] for each known model.

    Call once per scan run and pass the result into compute_ensemble_stats
    via the freshness_weights parameter. Providing `now` explicitly is useful
    for backtests; in live trading omit it to use the current UTC time.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    weights: dict[str, float] = {}
    all_models = list(_AVAILABILITY.keys()) + ["hrrr"]
    for model in all_models:
        last = _last_available(model, now)
        age_h = max(0.0, (now - last).total_seconds() / 3600.0)
        w = max(0.05, math.exp(-age_h / FRESHNESS_HALFLIFE_H))
        weights[model] = w
        logger.debug("Freshness %s: age=%.1fh → weight=%.3f", model, age_h, w)

    return weights
