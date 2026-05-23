# TSA Passenger Forecasting

> 23 nodes · cohesion 0.13

## Key Concepts

- **compute_tsa_edge()** (10 connections) — `signals/tsa_edge_calculator.py`
- **tsa.py** (9 connections) — `data/tsa.py`
- **forecast_passengers()** (8 connections) — `data/tsa.py`
- **tsa_edge_calculator.py** (7 connections) — `signals/tsa_edge_calculator.py`
- **compute_dow_baselines()** (5 connections) — `data/tsa.py`
- **compute_yoy_ratio()** (5 connections) — `data/tsa.py`
- **tsa_bucket_prob()** (4 connections) — `signals/tsa_edge_calculator.py`
- **get_holiday_info()** (3 connections) — `data/tsa.py`
- **_parse_count()** (3 connections) — `data/tsa.py`
- **_parse_tsa_date()** (3 connections) — `data/tsa.py`
- **check_hub_weather()** (3 connections) — `signals/tsa_edge_calculator.py`
- **_safe_weekday()** (2 connections) — `data/tsa.py`
- **TSA passenger volume data fetcher.  Scrapes the TSA daily passenger counts page** (1 connections) — `data/tsa.py`
- **Parse TSA date strings like '3/25/2026' or '2026-03-25' → 'YYYY-MM-DD'.** (1 connections) — `data/tsa.py`
- **Compute mean daily passenger count by day of week.      data: output of fetch_ts** (1 connections) — `data/tsa.py`
- **Compute mean current/prior year ratio over the most recent `lookback_days`.** (1 connections) — `data/tsa.py`
- **Return (holiday_name, multiplier) if target_date falls in a peak-travel period.** (1 connections) — `data/tsa.py`
- **Produce a passenger count forecast for target_date.      Returns:         {** (1 connections) — `data/tsa.py`
- **Strip commas/whitespace and parse to int.** (1 connections) — `data/tsa.py`
- **TSA passenger market edge calculator.  Signal inputs:   1. Day-of-week baseline** (1 connections) — `signals/tsa_edge_calculator.py`
- **Compute the full edge signal for one TSA passenger bucket market.      market: d** (1 connections) — `signals/tsa_edge_calculator.py`
- **Check Open-Meteo GFS for bad weather at the 5 major hub airports on target_date.** (1 connections) — `signals/tsa_edge_calculator.py`
- **P(passenger_count in [lo_m, hi_m]) under N(mean_m, std_m). Units: millions.** (1 connections) — `signals/tsa_edge_calculator.py`

## Relationships

- [[Paper Trading Broker]] (4 shared connections)
- [[Portfolio Resolution]] (1 shared connections)
- [[NOAA Weather Fetching]] (1 shared connections)
- [[Backtest Runner]] (1 shared connections)

## Source Files

- `data/tsa.py`
- `signals/tsa_edge_calculator.py`

## Audit Trail

- EXTRACTED: 71 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*