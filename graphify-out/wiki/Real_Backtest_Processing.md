# Real Backtest Processing

> 9 nodes · cohesion 0.22

## Key Concepts

- **compute_ensemble_stats()** (14 connections) — `signals/ensemble.py`
- **process_market()** (10 connections) — `real_backtest.py`
- **_crowd_model_price()** (3 connections) — `real_backtest.py`
- **King Models Conflict Detection (ECMWF vs GFS)** (2 connections) — `signals/ensemble.py`
- **Run the full signal pipeline for one resolved market.     Returns a result row d** (1 connections) — `real_backtest.py`
- **Fallback market price: Gaussian crowd using ensemble mean + MARKET_SHRINK.     U** (1 connections) — `real_backtest.py`
- **Dynamic Lead-Time Uncertainty Scaling** (1 connections) — `signals/ensemble.py`
- **Kish Effective Sample Size Correction** (1 connections) — `signals/ensemble.py`
- **Given {model_name: corrected_high_c}, compute weighted ensemble statistics.** (1 connections) — `signals/ensemble.py`

## Relationships

- [[Real Historical Backtest]] (4 shared connections)
- [[Backtest Runner]] (4 shared connections)
- [[NOAA Weather Fetching]] (3 shared connections)
- [[Forecast Bias Correction]] (2 shared connections)
- [[Portfolio Resolution]] (2 shared connections)
- [[Signal Ensemble Weights]] (2 shared connections)
- [[Confidence Tier System]] (1 shared connections)

## Source Files

- `real_backtest.py`
- `signals/ensemble.py`

## Audit Trail

- EXTRACTED: 33 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*