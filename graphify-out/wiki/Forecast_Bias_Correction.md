# Forecast Bias Correction

> 11 nodes · cohesion 0.22

## Key Concepts

- **bias_corrector.py** (9 connections) — `signals/bias_corrector.py`
- **get_corrected_ensemble_at_date()** (6 connections) — `signals/bias_corrector.py`
- **station_is_ready()** (6 connections) — `signals/bias_corrector.py`
- **apply_bias()** (4 connections) — `signals/bias_corrector.py`
- **_apply_city_bias()** (4 connections) — `signals/bias_corrector.py`
- **get_persistence_bias()** (3 connections) — `signals/bias_corrector.py`
- **Per-station, per-model, per-calendar-month bias corrector.  bias = mean(actual_h** (1 connections) — `signals/bias_corrector.py`
- **Compute short-term persistence bias: mean(actual - predicted) over last 7 days.** (1 connections) — `signals/bias_corrector.py`
- **Apply stored bias correction to a model forecast.     Blends:       - Seasonal m** (1 connections) — `signals/bias_corrector.py`
- **Apply per-city additive bias from CITY_FORECAST_BIAS_C (config) if present.** (1 connections) — `signals/bias_corrector.py`
- **Point-in-time bias correction: compute bias using only observations     that wer** (1 connections) — `signals/bias_corrector.py`

## Relationships

- [[Backtest Runner]] (5 shared connections)
- [[Portfolio Resolution]] (3 shared connections)
- [[Real Historical Backtest]] (2 shared connections)
- [[Real Backtest Processing]] (2 shared connections)
- [[Polymarket Position Manager]] (1 shared connections)

## Source Files

- `signals/bias_corrector.py`

## Audit Trail

- EXTRACTED: 36 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*