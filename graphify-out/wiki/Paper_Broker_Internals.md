# Paper Broker Internals

> 9 nodes · cohesion 0.22

## Key Concepts

- **execute_paper_trade** (11 connections) — `broker/paper_broker.py`
- **get_bankroll** (4 connections) — `db.py`
- **open_trade_atomic** (3 connections) — `db.py`
- **reset (reset_paper.py)** (3 connections) — `reset_paper.py`
- **Order Book Depth Check Design** (1 connections) — `broker/paper_broker.py`
- **Correlated NO Bet Discount Design** (1 connections) — `broker/paper_broker.py`
- **adjust_bankroll** (1 connections) — `db.py`
- **Atomic Trade Open Design (stake deducted at entry)** (1 connections) — `db.py`
- **get_recent_prices** (1 connections) — `db.py`

## Relationships

- [[Forecast DB Queries]] (4 shared connections)
- [[Terminal Dashboard]] (3 shared connections)
- [[Event & KV Store]] (1 shared connections)
- [[Live CLOB Trade Execution]] (1 shared connections)
- [[Backtesting Engine]] (1 shared connections)

## Source Files

- `broker/paper_broker.py`
- `db.py`
- `reset_paper.py`

## Audit Trail

- EXTRACTED: 23 (88%)
- INFERRED: 3 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*