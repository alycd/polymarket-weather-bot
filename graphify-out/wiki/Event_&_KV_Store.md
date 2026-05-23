# Event & KV Store

> 9 nodes · cohesion 0.22

## Key Concepts

- **set_kv** (7 connections) — `db.py`
- **log_event** (3 connections) — `db.py`
- **acquire_job_lock** (3 connections) — `ops_state.py`
- **mark_job_end** (3 connections) — `ops_state.py`
- **mark_job_start** (2 connections) — `ops_state.py`
- **update_datasource_health** (2 connections) — `ops_state.py`
- **_acquire_scan_lock** (1 connections) — `main.py`
- **_signal_health_policy** (1 connections) — `main.py`
- **release_job_lock** (1 connections) — `ops_state.py`

## Relationships

- [[Forecast DB Queries]] (4 shared connections)
- [[Paper Broker Internals]] (1 shared connections)
- [[Position Query & Sell]] (1 shared connections)
- [[Terminal Dashboard]] (1 shared connections)

## Source Files

- `db.py`
- `main.py`
- `ops_state.py`

## Audit Trail

- EXTRACTED: 19 (83%)
- INFERRED: 4 (17%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*