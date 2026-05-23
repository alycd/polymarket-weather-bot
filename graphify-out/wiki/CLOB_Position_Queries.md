# CLOB Position Queries

> 12 nodes · cohesion 0.20

## Key Concepts

- **_build_polymarket_live_dashboard()** (9 connections) — `web_dashboard.py`
- **get_proxy_address()** (7 connections) — `broker/live_broker.py`
- **get_clob_positions()** (6 connections) — `broker/live_broker.py`
- **get_polymarket_closed_positions()** (5 connections) — `broker/live_broker.py`
- **sync_positions_to_db()** (5 connections) — `broker/live_broker.py`
- **cmd_sync_positions()** (5 connections) — `main.py`
- **Fetch all current on-chain positions via Polymarket Gamma API.     Returns list** (1 connections) — `broker/live_broker.py`
- **Polymarket proxy / funder wallet (same as UI portfolio address).** (1 connections) — `broker/live_broker.py`
- **Pull actual on-chain positions from Polymarket data API and reconcile with DB.** (1 connections) — `broker/live_broker.py`
- **Closed positions with realized PnL — matches Polymarket portfolio history.** (1 connections) — `broker/live_broker.py`
- **Pull actual CLOB positions and reconcile with our internal DB.** (1 connections) — `main.py`
- **Entire live view from Polymarket public Data API + CLOB cash (same as UI).** (1 connections) — `web_dashboard.py`

## Relationships

- [[Terminal Dashboard]] (6 shared connections)
- [[Live Broker Execution]] (6 shared connections)
- [[Portfolio Resolution]] (4 shared connections)
- [[Operations State]] (1 shared connections)

## Source Files

- `broker/live_broker.py`
- `main.py`
- `web_dashboard.py`

## Audit Trail

- EXTRACTED: 43 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*