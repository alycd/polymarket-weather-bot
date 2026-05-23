# Forecast DB Queries

> 9 nodes · cohesion 0.28

## Key Concepts

- **cmd_scan** (23 connections) — `main.py`
- **cmd_scan_tsa** (5 connections) — `main.py`
- **cmd_scan_crypto** (4 connections) — `main.py`
- **record_price** (3 connections) — `db.py`
- **upsert_market** (2 connections) — `db.py`
- **get_forecasts_for_date** (1 connections) — `db.py`
- **record_tsa_prediction** (1 connections) — `db.py`
- **Opportunistic Scan Guards Design** (1 connections) — `main.py`
- **clear_session_cache** (1 connections) — `signals/neighbor_check.py`

## Relationships

- [[Paper Broker Internals]] (4 shared connections)
- [[Event & KV Store]] (4 shared connections)
- [[Live CLOB Trade Execution]] (3 shared connections)
- [[NOAA Weather Fetching]] (2 shared connections)
- [[Forecast Pruning & Storage]] (2 shared connections)
- [[Backtesting Engine]] (2 shared connections)
- [[Terminal Dashboard]] (1 shared connections)
- [[Correlation City Filter]] (1 shared connections)
- [[Model Config Settings]] (1 shared connections)
- [[Live Position Retrieval]] (1 shared connections)

## Source Files

- `db.py`
- `main.py`
- `signals/neighbor_check.py`

## Audit Trail

- EXTRACTED: 39 (95%)
- INFERRED: 2 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*