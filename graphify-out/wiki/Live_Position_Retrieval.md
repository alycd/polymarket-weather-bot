# Live Position Retrieval

> 8 nodes · cohesion 0.25

## Key Concepts

- **_build_polymarket_live_dashboard** (7 connections) — `web_dashboard.py`
- **get_kv** (4 connections) — `db.py`
- **get_ops_snapshot** (3 connections) — `ops_state.py`
- **set_mode** (2 connections) — `db.py`
- **get_clob_positions** (1 connections) — `broker/live_broker.py`
- **get_polymarket_closed_positions** (1 connections) — `broker/live_broker.py`
- **get_polymarket_positions_value_usd** (1 connections) — `broker/live_broker.py`
- **should_run_daily_reconcile** (1 connections) — `ops_state.py`

## Relationships

- [[Terminal Dashboard]] (3 shared connections)
- [[NOAA Weather Fetching]] (1 shared connections)
- [[Forecast DB Queries]] (1 shared connections)
- [[Live CLOB Trade Execution]] (1 shared connections)

## Source Files

- `broker/live_broker.py`
- `db.py`
- `ops_state.py`
- `web_dashboard.py`

## Audit Trail

- EXTRACTED: 20 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*