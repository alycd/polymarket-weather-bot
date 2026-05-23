# Forecast Pruning & Storage

> 7 nodes · cohesion 0.29

## Key Concepts

- **cmd_backfill** (6 connections) — `main.py`
- **insert_forecast** (2 connections) — `db.py`
- **upsert_historical_obs** (2 connections) — `db.py`
- **upsert_station** (2 connections) — `db.py`
- **insert_forecast_if_missing** (1 connections) — `db.py`
- **prune_old_forecasts** (1 connections) — `db.py`
- **upsert_climatology** (1 connections) — `db.py`

## Relationships

- [[Forecast DB Queries]] (2 shared connections)
- [[Position Query & Sell]] (1 shared connections)

## Source Files

- `db.py`
- `main.py`

## Audit Trail

- EXTRACTED: 15 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*