---
name: polymarket-resolution-semantics
description: "Polymarket temp markets score the INTEGER WU print, closed-closed (lo <= round(high_native) <= hi); WU-first resolution shipped 2026-06-12; api.weather.com backend access"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

Polymarket temperature markets resolve from the WU daily-history page for the market's airport ICAO. Validated against 19 real PM settlements (2026-06): membership is on the **integer print in the market's NATIVE unit, closed-closed** — YES wins iff `bucket_lo <= round(high_native) <= bucket_hi`. A continuous-°C compare with exclusive upper bound (the pre-2026-06-12 code) mis-scores upper-edge prints (65°F in a "64–65°F" market: old code = miss, PM = hit).

**WU history-page High = OBSERVATION max (hourly obs table), NOT the live `temperatureMaxSince7Am` widget (settled 06-13).** Confirmed two ways: Denver 06-12 settled page = 87.8°F (not the 90 the live widget showed intraday); Toronto 06-13 page = 29°C while `temperatureMaxSince7Am` = 86°F = 30.00°C. The resolution fetch `get_historical_high_native` (hourly-table based) was correct ALL ALONG. A 06-12 dashboard helper briefly blended in `temperatureMaxSince7Am` and OVERSHOT — showed Toronto 30 vs page 29, flipping a real HIT into a false MISS on an open NO bet; reverted so `get_today_max_native` just delegates to the resolution fetch. **DO NOT use `temperatureMaxSince7Am` for resolution or display** — it's the live current-conditions widget, more aggressive than the page High. The audit's "3/20 WU≠ASOS divergence" was mostly this artifact, not real gaps. Full writeup: docs/plans/2026-06-12_wu_asos_divergence.md.

**Why:** 1°F buckets mean boundary prints decide outcomes; getting the rounding/interval semantics wrong corrupts paper P&L and calibration on exactly the decisive trades. Audit of the full resolved book found 20/20 PM-settled outcomes already correct (PM's own `winner` field is step 1; the weather fallback rarely fires) and ONE day (Denver 2026-05-28: WU printed 75, PM settled the 74-75 bucket as NOT hit) where WU's revised print disagrees with PM's actual settlement — WU data can be revised post-hoc, so PM's winner field remains the highest truth.

**How to apply:** resolution priority is WU → ASOS → ERA5 (Tel Aviv ASOS-primary) via `get_actual_high_native` / `_yes_won_native` in broker/position_manager.py (shipped 2026-06-12, commit 806781b). WU's JS page is bypassed: `data/wunderground.py` calls the api.weather.com backend directly (embedded site key, auto-refreshed on 401 via `_refresh_api_key`; override with WU_API_KEY env). Same backend serves TWC hourly forecasts (`get_hourly_forecast_native`) used by the dashboard outlook — integer °F, matching the resolution scale. Don't "simplify" the closed-closed integer compare back to continuous °C. See [[live-execution-integrity-spec]].
