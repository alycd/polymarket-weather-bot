# Paper Trading Broker

> 16 nodes · cohesion 0.16

## Key Concepts

- **get_market_prices()** (14 connections) — `data/polymarket.py`
- **execute_paper_trade()** (8 connections) — `broker/paper_broker.py`
- **cmd_scan_tsa()** (8 connections) — `main.py`
- **fetch_tsa_data()** (6 connections) — `data/tsa.py`
- **paper_broker.py** (5 connections) — `broker/paper_broker.py`
- **get_clob_orderbook()** (5 connections) — `data/polymarket.py`
- **cmd_exit_scan()** (5 connections) — `main.py`
- **check_stop_losses()** (2 connections) — `broker/paper_broker.py`
- **Paper broker — simulated order execution at real CLOB prices. Money is fake. Pri** (1 connections) — `broker/paper_broker.py`
- **Execute a paper trade based on an edge signal.      market: DB-style market dict** (1 connections) — `broker/paper_broker.py`
- **Stop-losses are disabled.     Kept as a no-op for compatibility with any older c** (1 connections) — `broker/paper_broker.py`
- **Fetch CLOB order book for a YES token.     Returns dict with 'bids' and 'asks' l** (1 connections) — `data/polymarket.py`
- **Fetch live bid, ask, and mid for a YES token from the CLOB orderbook.     Return** (1 connections) — `data/polymarket.py`
- **Scrape tsa.gov/travel/passenger-volumes.      Returns dict keyed by ISO date str** (1 connections) — `data/tsa.py`
- **Review all open positions and exit early if any of these conditions are met:** (1 connections) — `main.py`
- **Scan for TSA passenger market edges and paper-trade any found.      Pipeline:** (1 connections) — `main.py`

## Relationships

- [[Portfolio Resolution]] (7 shared connections)
- [[TSA Passenger Forecasting]] (4 shared connections)
- [[Crypto Market Data]] (3 shared connections)
- [[Polymarket Market Data]] (3 shared connections)
- [[TSA Market Integration]] (3 shared connections)
- [[Terminal Dashboard]] (2 shared connections)
- [[Live Broker Execution]] (1 shared connections)

## Source Files

- `broker/paper_broker.py`
- `data/polymarket.py`
- `data/tsa.py`
- `main.py`

## Audit Trail

- EXTRACTED: 61 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*