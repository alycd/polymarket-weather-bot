# NOAA Weather Fetching

> 43 nodes · cohesion 0.07

## Key Concepts

- **compute_edge()** (20 connections) — `signals/edge_calculator.py`
- **edge_calculator.py** (14 connections) — `signals/edge_calculator.py`
- **get_running_max_c()** (14 connections) — `signals/nowcaster.py`
- **nowcast_confidence()** (11 connections) — `signals/nowcaster.py`
- **nowcaster.py** (8 connections) — `signals/nowcaster.py`
- **fetch_asos_daily_max()** (7 connections) — `data/noaa.py`
- **noaa.py** (7 connections) — `data/noaa.py`
- **retry()** (7 connections) — `data/utils.py`
- **compute_nowcast_bucket_prob()** (7 connections) — `signals/nowcaster.py`
- **fetch_metar()** (5 connections) — `data/noaa.py`
- **get_running_max_today()** (5 connections) — `data/noaa.py`
- **get_shrinkage_factor()** (5 connections) — `metrics/calibration.py`
- **cmd_nowcast()** (5 connections) — `main.py`
- **fetch_asos_today_hourly()** (4 connections) — `data/noaa.py`
- **_climo_blend()** (4 connections) — `signals/edge_calculator.py`
- **_get_city_bss()** (4 connections) — `signals/edge_calculator.py`
- **weekly_market_prob()** (3 connections) — `signals/edge_calculator.py`
- **_local_hour()** (3 connections) — `signals/nowcaster.py`
- **cmd_nowcast** (2 connections) — `main.py`
- **King Models Conflict Penalty** (2 connections) — `signals/edge_calculator.py`
- **NOAA / Iowa State Mesonet data fetchers.  Two roles:   1. Iowa State ASOS — hist** (1 connections) — `data/noaa.py`
- **Fetch the most recent METAR observation for each station.     Returns dict: {ica** (1 connections) — `data/noaa.py`
- **Get the running maximum temperature for today from ASOS hourly obs.     Returns** (1 connections) — `data/noaa.py`
- **Fetch hourly ASOS data and compute daily max temperature.     Returns dict: {dat** (1 connections) — `data/noaa.py`
- **Fetch today's hourly observations for nowcasting.     Returns list of {time_utc,** (1 connections) — `data/noaa.py`
- *... and 18 more nodes in this community*

## Relationships

- [[Portfolio Resolution]] (8 shared connections)
- [[Backtest Runner]] (7 shared connections)
- [[Polymarket Position Manager]] (4 shared connections)
- [[Terminal Dashboard]] (4 shared connections)
- [[Real Backtest Processing]] (3 shared connections)
- [[Climatology Data]] (2 shared connections)
- [[Forecast DB Queries]] (2 shared connections)
- [[Live Position Retrieval]] (1 shared connections)
- [[TSA Passenger Forecasting]] (1 shared connections)
- [[Crypto Edge Calculator]] (1 shared connections)
- [[Backtesting Engine]] (1 shared connections)

## Source Files

- `data/noaa.py`
- `data/utils.py`
- `main.py`
- `metrics/calibration.py`
- `signals/edge_calculator.py`
- `signals/nowcaster.py`

## Audit Trail

- EXTRACTED: 151 (94%)
- INFERRED: 9 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*