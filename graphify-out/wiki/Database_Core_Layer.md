# Database Core Layer

> 33 nodes · cohesion 0.12

## Key Concepts

- **db.py** (56 connections) — `db.py`
- **_conn()** (53 connections) — `db.py`
- **adjust_bankroll()** (2 connections) — `db.py`
- **already_in_market()** (2 connections) — `db.py`
- **count_historical_obs()** (2 connections) — `db.py`
- **deactivate_markets_before()** (2 connections) — `db.py`
- **get_active_markets()** (2 connections) — `db.py`
- **get_all_biases()** (2 connections) — `db.py`
- **get_all_climatology()** (2 connections) — `db.py`
- **get_all_stations()** (2 connections) — `db.py`
- **get_all_trades()** (2 connections) — `db.py`
- **get_bankroll()** (2 connections) — `db.py`
- **get_bias()** (2 connections) — `db.py`
- **get_calibration_predictions()** (2 connections) — `db.py`
- **get_climatology()** (2 connections) — `db.py`
- **get_daily_pnl()** (2 connections) — `db.py`
- **get_historical_forecasts()** (2 connections) — `db.py`
- **get_historical_obs()** (2 connections) — `db.py`
- **get_open_trades()** (2 connections) — `db.py`
- **get_station()** (2 connections) — `db.py`
- **init_db()** (2 connections) — `db.py`
- **insert_forecast()** (2 connections) — `db.py`
- **insert_trade()** (2 connections) — `db.py`
- **log_event()** (2 connections) — `db.py`
- **record_prediction()** (2 connections) — `db.py`
- *... and 8 more nodes in this community*

## Relationships

- [[DB Bankroll Management]] (2 shared connections)
- [[DB Historical Obs Upsert]] (2 shared connections)
- [[DB Forecast Dedup]] (2 shared connections)
- [[DB Forecast Date Queries]] (2 shared connections)
- [[DB Forecast Run History]] (2 shared connections)
- [[DB Forecast Pruning]] (2 shared connections)
- [[DB Bias Batch Queries]] (2 shared connections)
- [[DB Performance Metrics]] (2 shared connections)
- [[DB Resolved Trades]] (2 shared connections)
- [[DB Fallback Trade Queries]] (2 shared connections)
- [[DB Trade Outcome Update]] (2 shared connections)
- [[DB Trade Source Update]] (2 shared connections)

## Source Files

- `db.py`

## Audit Trail

- EXTRACTED: 170 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*