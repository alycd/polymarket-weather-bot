---
name: excluded-cities-are-bias-driven
description: "Most CITY_EXCLUDE cities are excluded for correctable forecast bias, not genuine noise"
metadata: 
  node_type: memory
  type: project
  originSessionId: a7b7bd66-46f1-4497-af7b-f9b2221b27c4
---

The 13 cities in `paper_config.CITY_EXCLUDE` perform terribly (32% win, −49.8% ROI) vs tradeable cities (75% win, +27.1% ROI) — confirmed over 117 resolved paper trades (2026-06-03). But the forecast-vs-obs analysis (lead 0–1, real ASOS/WU obs) shows the bad performance is driven by large *uncorrected* per-city mean bias, not irreducible noise:
- Re-admittable after per-city bias correction (LOO RMSE drops to 0.6–1.4°C): **Ankara (+1.40°C bias), Munich (+1.08), San Francisco (+2.00), Seoul (+1.94), Taipei (+1.62)**.
- Keep excluded (genuinely noisy): Buenos Aires (corr RMSE 2.08), Chongqing (1.49).

There is also a universal +0.53°C cold bias (models under-predict daily high). Fixing per-city bias cut global ensemble RMSE 1.52 → 1.22 (−19%). The existing `bias_corrector` skips many international stations via the circular-ERA5 guard until enough ASOS/WU obs accumulate. See [[calibration-shrinkage-inert]] and [[bias-correction-dominates-ensemble-weights]].

**UPDATE 2026-06-09 — the re-admission FAILED forward; 5 cities re-excluded.** Despite good corrected RMSE, the cold-bias cohort traded badly (watch-list rule = re-exclude if <55% win over ≥5): Tokyo 40%/n5 (rule-triggered), Ankara 0%/n2, San Francisco 25%/n4, Seoul 25%/n4, Munich 33%/n3 — **combined −$154**. Re-excluded those 5 in `paper_config.CITY_EXCLUDE`; kept Beijing (50%, +$2), Taipei (75%, +$3), Warsaw (50%, breakeven n2, on watch). **Lesson: corrected forecast RMSE did NOT predict forward trade quality** — partly because the whole model is badly overconfident on selected bets (see [[calibration-shrinkage-inert]]), so a low-RMSE city can still lose if the bucket-probability edges are noise. Revisit re-admission only if calibration materially improves.
