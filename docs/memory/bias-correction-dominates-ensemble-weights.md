---
name: bias-correction-dominates-ensemble-weights
description: Bias correction matters ~30x more than ensemble model weighting for forecast accuracy
metadata: 
  node_type: memory
  type: project
  originSessionId: a7b7bd66-46f1-4497-af7b-f9b2221b27c4
---

Out-of-sample (time-split) forecast-vs-obs validation on lead 0–1 short-range forecasts (2026-06-03):
- **Ensemble model weighting is nearly irrelevant.** Hardcoded weights RMSE 1.578 vs data-driven inverse-variance 1.568 (−0.6%) vs equal-weight 1.588. Dropping the worst models (meteofrance, gem) slightly HURTS (1.598) — averaging is robust, even a weak model adds independent info.
- **Bias correction dominates:** same forecasts, +per-city LOO bias correction → RMSE 1.280 (−19%).
- Per-model RMSE ranking (best→worst): icon 1.62, hrrr 1.70, ecmwf 1.85, gfs 1.86, gem 2.14, meteofrance 2.33. So ICON is actually the best model, contradicting the hardcoded weights (ecmwf=1.8 highest, icon=1.3). But re-weighting to match this barely helps because of ensemble averaging.

Implication: invest effort in per-city bias correction ([[excluded-cities-are-bias-driven]]) and probability calibration ([[calibration-shrinkage-inert]]), NOT in tuning `_MODEL_WEIGHTS` in signals/ensemble.py.
