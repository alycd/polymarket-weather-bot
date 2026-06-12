---
name: polymarket-resolution-semantics
description: "Polymarket temp markets score the INTEGER WU print, closed-closed (lo <= round(high_native) <= hi); WU-first resolution shipped 2026-06-12; api.weather.com backend access"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

Polymarket temperature markets resolve from the WU daily-history page for the market's airport ICAO. Validated against 19 real PM settlements (2026-06): membership is on the **integer print in the market's NATIVE unit, closed-closed** — YES wins iff `bucket_lo <= round(high_native) <= bucket_hi`. A continuous-°C compare with exclusive upper bound (the pre-2026-06-12 code) mis-scores upper-edge prints (65°F in a "64–65°F" market: old code = miss, PM = hit).

**WU page High = CONTINUOUS max, not the hourly table (corrected 06-12 evening):** verified KDEN 06-12 — page High 90°F (v3 `temperatureMaxSince7Am`) while the v1 hourly obs table maxed 87; spikes between hourly prints DO reach the page High. Intraday dashboard reads fixed via `get_today_max_native`. The audit's "3/20 WU≠ASOS divergence" was largely this read artifact (our hourly-table max understated the page High — Denver 05-28 "WU 75" was the table max; page plausibly showed 76, matching ASOS and PM's settlement). **Open (FOLLOWUPS 06-13):** does the completed-day page High persist the continuous max? If yes, `get_historical_high_native` (resolution fetch, hourly-table based) understates and must switch to the page-summary High. Until then PM `winner` is step 1, so resolution risk is contained. Full writeup: docs/plans/2026-06-12_wu_asos_divergence.md.

**Why:** 1°F buckets mean boundary prints decide outcomes; getting the rounding/interval semantics wrong corrupts paper P&L and calibration on exactly the decisive trades. Audit of the full resolved book found 20/20 PM-settled outcomes already correct (PM's own `winner` field is step 1; the weather fallback rarely fires) and ONE day (Denver 2026-05-28: WU printed 75, PM settled the 74-75 bucket as NOT hit) where WU's revised print disagrees with PM's actual settlement — WU data can be revised post-hoc, so PM's winner field remains the highest truth.

**How to apply:** resolution priority is WU → ASOS → ERA5 (Tel Aviv ASOS-primary) via `get_actual_high_native` / `_yes_won_native` in broker/position_manager.py (shipped 2026-06-12, commit 806781b). WU's JS page is bypassed: `data/wunderground.py` calls the api.weather.com backend directly (embedded site key, auto-refreshed on 401 via `_refresh_api_key`; override with WU_API_KEY env). Same backend serves TWC hourly forecasts (`get_hourly_forecast_native`) used by the dashboard outlook — integer °F, matching the resolution scale. Don't "simplify" the closed-closed integer compare back to continuous °C. See [[live-execution-integrity-spec]].
