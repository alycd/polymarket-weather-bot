# Climatology Data

> 24 nodes · cohesion 0.12

## Key Concepts

- **fetch_historical_actuals()** (14 connections) — `data/openmeteo.py`
- **openmeteo.py** (9 connections) — `data/openmeteo.py`
- **cmd_backfill()** (9 connections) — `main.py`
- **fetch_all_models()** (8 connections) — `data/openmeteo.py`
- **_get_with_retry()** (6 connections) — `data/openmeteo.py`
- **fetch_forecast_one_model()** (5 connections) — `data/openmeteo.py`
- **fetch_past_model_forecasts()** (5 connections) — `data/openmeteo.py`
- **fetch_climatology()** (4 connections) — `data/climatology.py`
- **fetch_historical_model_forecast()** (3 connections) — `data/openmeteo.py`
- **_warn_rate_limited()** (3 connections) — `data/openmeteo.py`
- **main()** (3 connections) — `scripts/calibrate_forecast_std.py`
- **calibrate_forecast_std.py** (3 connections) — `scripts/calibrate_forecast_std.py`
- **climatology.py** (2 connections) — `data/climatology.py`
- **fetch_day_ahead_forecast()** (2 connections) — `scripts/calibrate_forecast_std.py`
- **Climatological baseline from Open-Meteo Climate API.  Fetches 30-year historical** (1 connections) — `data/climatology.py`
- **Fetch 30-year daily max temperature climatology and compute per-month stats.** (1 connections) — `data/climatology.py`
- **Open-Meteo multi-model ensemble forecast fetcher. All 5 models are queried indep** (1 connections) — `data/openmeteo.py`
- **Fetch all available Open-Meteo model forecasts for a city/date in parallel.** (1 connections) — `data/openmeteo.py`
- **Fetch historical daily max temperatures from Open-Meteo Archive (ERA5 reanalysis** (1 connections) — `data/openmeteo.py`
- **Fetch what an NWP model predicted for each of the last `past_days` days     usin** (1 connections) — `data/openmeteo.py`
- **GET with exponential backoff on transient errors.** (1 connections) — `data/openmeteo.py`
- **DEPRECATED PROXY: returns ERA5 actuals as a model forecast stand-in.     This is** (1 connections) — `data/openmeteo.py`
- **Fetch daily max temperature (°C) and max precip prob (%) from one Open-Meteo mod** (1 connections) — `data/openmeteo.py`
- **For each city:       1. Pull 180 days of historical ASOS daily-max temps       2** (1 connections) — `main.py`

## Relationships

- [[Portfolio Resolution]] (6 shared connections)
- [[Polymarket Position Manager]] (3 shared connections)
- [[Operations State]] (2 shared connections)
- [[Real Historical Backtest]] (2 shared connections)
- [[Backtest Runner]] (2 shared connections)
- [[NOAA Weather Fetching]] (2 shared connections)
- [[Terminal Dashboard]] (1 shared connections)

## Source Files

- `data/climatology.py`
- `data/openmeteo.py`
- `main.py`
- `scripts/calibrate_forecast_std.py`

## Audit Trail

- EXTRACTED: 85 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*