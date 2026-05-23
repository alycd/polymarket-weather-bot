# Terminal Dashboard

> 68 nodes · cohesion 0.06

## Key Concepts

- **main()** (23 connections) — `main.py`
- **web_dashboard.py** (21 connections) — `web_dashboard.py`
- **dashboard.py** (15 connections) — `dashboard.py`
- **reporting.py** (15 connections) — `metrics/reporting.py`
- **compute_calibration()** (13 connections) — `metrics/calibration.py`
- **compute_pnl_summary()** (13 connections) — `metrics/pnl.py`
- **print_stats()** (12 connections) — `metrics/reporting.py`
- **render_dashboard()** (12 connections) — `dashboard.py`
- **get_open_trades** (11 connections) — `db.py`
- **compute_sharpe()** (11 connections) — `metrics/sharpe.py`
- **_build_data** (9 connections) — `web_dashboard.py`
- **update_shrinkage_factors()** (8 connections) — `metrics/calibration.py`
- **_build_data()** (8 connections) — `web_dashboard.py`
- **render_dashboard** (7 connections) — `dashboard.py`
- **get_resolved_trades** (7 connections) — `db.py`
- **compute_calibration_curve()** (7 connections) — `metrics/calibration.py`
- **calibration.py** (7 connections) — `metrics/calibration.py`
- **print_calibration()** (6 connections) — `metrics/reporting.py`
- **_render_split()** (6 connections) — `dashboard.py`
- **export_calibration_csv()** (5 connections) — `metrics/calibration.py`
- **print_cities()** (4 connections) — `metrics/reporting.py`
- **print_history()** (4 connections) — `metrics/reporting.py`
- **print_positions()** (4 connections) — `metrics/reporting.py`
- **build_city_summary()** (4 connections) — `dashboard.py`
- **build_positions_table()** (4 connections) — `dashboard.py`
- *... and 43 more nodes in this community*

## Relationships

- [[Portfolio Resolution]] (13 shared connections)
- [[Operations State]] (6 shared connections)
- [[CLOB Position Queries]] (6 shared connections)
- [[NOAA Weather Fetching]] (4 shared connections)
- [[Live Position Retrieval]] (3 shared connections)
- [[Paper Broker Internals]] (3 shared connections)
- [[Position Query & Sell]] (2 shared connections)
- [[Paper Trading Broker]] (2 shared connections)
- [[Live Broker Execution]] (2 shared connections)
- [[Forecast DB Queries]] (1 shared connections)
- [[Correlation City Filter]] (1 shared connections)
- [[Live CLOB Trade Execution]] (1 shared connections)

## Source Files

- `dashboard.py`
- `db.py`
- `main.py`
- `metrics/calibration.py`
- `metrics/pnl.py`
- `metrics/reporting.py`
- `metrics/sharpe.py`
- `web_dashboard.py`

## Audit Trail

- EXTRACTED: 308 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*