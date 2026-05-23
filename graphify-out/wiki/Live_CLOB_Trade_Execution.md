# Live CLOB Trade Execution

> 8 nodes · cohesion 0.25

## Key Concepts

- **cmd_resolve** (6 connections) — `main.py`
- **execute_live_trade** (3 connections) — `broker/live_broker.py`
- **get_clob_balance** (3 connections) — `broker/live_broker.py`
- **redeem_positions** (2 connections) — `broker/live_broker.py`
- **sync_positions_to_db** (2 connections) — `broker/live_broker.py`
- **set_bankroll** (2 connections) — `db.py`
- **cmd_sync_positions** (2 connections) — `main.py`
- **Capital Recycle After Resolve Design** (1 connections) — `main.py`

## Relationships

- [[Forecast DB Queries]] (3 shared connections)
- [[Paper Broker Internals]] (1 shared connections)
- [[Live Position Retrieval]] (1 shared connections)
- [[Terminal Dashboard]] (1 shared connections)
- [[Position Query & Sell]] (1 shared connections)

## Source Files

- `broker/live_broker.py`
- `db.py`
- `main.py`

## Audit Trail

- EXTRACTED: 18 (86%)
- INFERRED: 3 (14%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*