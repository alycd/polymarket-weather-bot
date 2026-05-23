# Backtesting Engine

> 24 nodes · cohesion 0.11

## Key Concepts

- **real_backtest main** (8 connections) — `real_backtest.py`
- **backtest main** (7 connections) — `backtest.py`
- **CITIES config dict** (6 connections) — `config.py`
- **db (Database Module)** (4 connections) — `db.py`
- **init_db** (4 connections) — `db.py`
- **run_simulation** (4 connections) — `simulate.py`
- **simulate_one_trial** (4 connections) — `simulate.py`
- **Trading Thresholds (MIN_EDGE, KELLY_FRACTION, etc.)** (3 connections) — `config.py`
- **process_market** (3 connections) — `real_backtest.py`
- **fetch_resolved_markets** (2 connections) — `real_backtest.py`
- **run_analysis** (2 connections) — `real_backtest.py`
- **compute_ensemble_stats_sim** (2 connections) — `simulate.py`
- **f_to_c** (2 connections) — `utils.py`
- **fetch_day_ahead_forecast (backtest.py)** (1 connections) — `backtest.py`
- **generate_buckets (backtest.py)** (1 connections) — `backtest.py`
- **kelly_size (backtest.py)** (1 connections) — `backtest.py`
- **Fat-tail Student-t distribution rationale (df=4)** (1 connections) — `config.py`
- **Bankroll Double-Deduction Bug Fix** (1 connections) — `db.py`
- **get_historical_obs** (1 connections) — `db.py`
- **get_price_at_time** (1 connections) — `db.py`
- **compute_metrics (simulate.py)** (1 connections) — `simulate.py`
- **generate_buckets (simulate.py)** (1 connections) — `simulate.py`
- **Monte Carlo NWP Error Injection Design** (1 connections) — `simulate.py`
- **_run_job** (1 connections) — `web_dashboard.py`

## Relationships

- [[Forecast DB Queries]] (2 shared connections)
- [[Paper Broker Internals]] (1 shared connections)
- [[NOAA Weather Fetching]] (1 shared connections)

## Source Files

- `backtest.py`
- `config.py`
- `db.py`
- `real_backtest.py`
- `simulate.py`
- `utils.py`
- `web_dashboard.py`

## Audit Trail

- EXTRACTED: 53 (85%)
- INFERRED: 9 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*