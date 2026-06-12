---
name: polymarket-resolution-semantics
description: "Polymarket temp markets score the INTEGER WU print, closed-closed (lo <= round(high_native) <= hi); WU-first resolution shipped 2026-06-12; api.weather.com backend access"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

Polymarket temperature markets resolve from the WU daily-history page for the market's airport ICAO. Validated against 19 real PM settlements (2026-06): membership is on the **integer print in the market's NATIVE unit, closed-closed** — YES wins iff `bucket_lo <= round(high_native) <= bucket_hi`. A continuous-°C compare with exclusive upper bound (the pre-2026-06-12 code) mis-scores upper-edge prints (65°F in a "64–65°F" market: old code = miss, PM = hit).

**WU ≠ ASOS even at end of day:** ~15% of settled days in the audit (3/20: Chicago, Toronto, Denver) ended with WU's final high ≥1°C away from ASOS, unreconciled. Mechanism: WU's daily high = max of the hourly obs list its page shows (routine METARs), while ASOS/IEM includes finer-grained + special obs that catch between-hours spikes WU never prints; WU also revises post-hoc. So intraday "ASOS above WU" is ambiguous (lag vs spike-that-never-prints) — treat risk on the ASOS number but expect settlement on WU's print. Full writeup incl. the nowcaster-vs-settlement boundary risk and follow-up-analysis trigger: docs/plans/2026-06-12_wu_asos_divergence.md.

**Why:** 1°F buckets mean boundary prints decide outcomes; getting the rounding/interval semantics wrong corrupts paper P&L and calibration on exactly the decisive trades. Audit of the full resolved book found 20/20 PM-settled outcomes already correct (PM's own `winner` field is step 1; the weather fallback rarely fires) and ONE day (Denver 2026-05-28: WU printed 75, PM settled the 74-75 bucket as NOT hit) where WU's revised print disagrees with PM's actual settlement — WU data can be revised post-hoc, so PM's winner field remains the highest truth.

**How to apply:** resolution priority is WU → ASOS → ERA5 (Tel Aviv ASOS-primary) via `get_actual_high_native` / `_yes_won_native` in broker/position_manager.py (shipped 2026-06-12, commit 806781b). WU's JS page is bypassed: `data/wunderground.py` calls the api.weather.com backend directly (embedded site key, auto-refreshed on 401 via `_refresh_api_key`; override with WU_API_KEY env). Same backend serves TWC hourly forecasts (`get_hourly_forecast_native`) used by the dashboard outlook — integer °F, matching the resolution scale. Don't "simplify" the closed-closed integer compare back to continuous °C. See [[live-execution-integrity-spec]].
