# Real Historical Backtest

> 14 nodes · cohesion 0.22

## Key Concepts

- **real_backtest.py** (21 connections) — `real_backtest.py`
- **fetch_resolved_markets()** (6 connections) — `real_backtest.py`
- **main()** (5 connections) — `real_backtest.py`
- **_req_with_retry()** (5 connections) — `real_backtest.py`
- **fetch_era5_for_city_date_range()** (4 connections) — `real_backtest.py`
- **fetch_clob_price_24h_before()** (3 connections) — `real_backtest.py`
- **fetch_day_ahead_forecast()** (3 connections) — `real_backtest.py`
- **run_analysis()** (3 connections) — `real_backtest.py`
- **_safe_mean()** (2 connections) — `real_backtest.py`
- **Fetch CLOB price-history and find the price closest to 24h before end_dt.     Re** (1 connections) — `real_backtest.py`
- **Fetch what a model predicted 1 day ahead for target_date (historical).** (1 connections) — `real_backtest.py`
- **Fetch ERA5 actuals for a city over all needed dates at once.** (1 connections) — `real_backtest.py`
- **GET with one retry on 429.** (1 connections) — `real_backtest.py`
- **Use the Gamma events API with tag_slug=weather to find closed city-specific** (1 connections) — `real_backtest.py`

## Relationships

- [[Polymarket Market Data]] (4 shared connections)
- [[Real Backtest Processing]] (4 shared connections)
- [[Backtest Runner]] (4 shared connections)
- [[Climatology Data]] (2 shared connections)
- [[Forecast Bias Correction]] (2 shared connections)
- [[Confidence Tier System]] (1 shared connections)

## Source Files

- `real_backtest.py`

## Audit Trail

- EXTRACTED: 57 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*