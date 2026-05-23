# Polymarket Position Manager

> 34 nodes · cohesion 0.09

## Key Concepts

- **position_manager.py** (10 connections) — `broker/position_manager.py`
- **get_historical_high()** (10 connections) — `data/wunderground.py`
- **wunderground.py** (9 connections) — `data/wunderground.py`
- **get_live_hourly()** (8 connections) — `data/wunderground.py`
- **recompute_bias()** (8 connections) — `signals/bias_corrector.py`
- **get_actual_high_c()** (6 connections) — `broker/position_manager.py`
- **_fetch_wu_page()** (6 connections) — `data/wunderground.py`
- **get_running_max_wu()** (6 connections) — `data/wunderground.py`
- **WundergroundError** (6 connections) — `data/wunderground.py`
- **_parse_daily_high_from_blob()** (5 connections) — `data/wunderground.py`
- **_extract_json_blob()** (4 connections) — `data/wunderground.py`
- **_walk()** (4 connections) — `data/wunderground.py`
- **_get_clob_token()** (3 connections) — `broker/position_manager.py`
- **_query_polymarket_outcome()** (3 connections) — `broker/position_manager.py`
- **Imperial-to-Celsius Conversion Fallback** (2 connections) — `data/wunderground.py`
- **Wunderground Last-Resort Fallback Pattern** (2 connections) — `data/wunderground.py`
- **Exponential Decay Weighting for Bias** (2 connections) — `signals/bias_corrector.py`
- **Position manager — resolves open trades against actual temperature outcomes.  Re** (1 connections) — `broker/position_manager.py`
- **Query Polymarket Gamma API to see if a market has resolved.     Returns 'yes' |** (1 connections) — `broker/position_manager.py`
- **Look up clob_token_yes for a trade from the markets table.** (1 connections) — `broker/position_manager.py`
- **Get actual daily high temperature for a station/date.     Returns (temp_c, sourc** (1 connections) — `broker/position_manager.py`
- **Wunderground data fetcher — last-resort fallback for temperature resolution.  Re** (1 connections) — `data/wunderground.py`
- **Recursively search for a key in a nested dict/list.** (1 connections) — `data/wunderground.py`
- **Navigate the WU JSON blob to find the daily high temperature in °C.     WU store** (1 connections) — `data/wunderground.py`
- **Fetch the daily recorded high temperature (°C) from Wunderground.     target_dat** (1 connections) — `data/wunderground.py`
- *... and 9 more nodes in this community*

## Relationships

- [[Portfolio Resolution]] (6 shared connections)
- [[NOAA Weather Fetching]] (4 shared connections)
- [[Climatology Data]] (3 shared connections)
- [[Signal Ensemble Weights]] (1 shared connections)
- [[Forecast Bias Correction]] (1 shared connections)

## Source Files

- `broker/position_manager.py`
- `data/wunderground.py`
- `graphify-out/memory/query_20260523_132645_explain_pnl.md`
- `signals/bias_corrector.py`

## Audit Trail

- EXTRACTED: 108 (97%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 2 (2%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*