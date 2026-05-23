# Live Broker Execution

> 21 nodes · cohesion 0.14

## Key Concepts

- **live_broker.py** (16 connections) — `broker/live_broker.py`
- **get_clob_balance()** (11 connections) — `broker/live_broker.py`
- **_get_client()** (8 connections) — `broker/live_broker.py`
- **redeem_positions()** (7 connections) — `broker/live_broker.py`
- **execute_live_trade()** (6 connections) — `broker/live_broker.py`
- **sell_position()** (5 connections) — `broker/live_broker.py`
- **cancel_order()** (3 connections) — `broker/live_broker.py`
- **get_clob_fills()** (3 connections) — `broker/live_broker.py`
- **_get_no_token_id()** (3 connections) — `broker/live_broker.py`
- **get_open_orders()** (3 connections) — `broker/live_broker.py`
- **get_order_status()** (3 connections) — `broker/live_broker.py`
- **Live broker — real order execution via Polymarket CLOB. Real money. Real fills.** (1 connections) — `broker/live_broker.py`
- **Fetch the NO token ID for this market from the Gamma API.     The CLOB market ha** (1 connections) — `broker/live_broker.py`
- **Return current USDC balance in the CLOB wallet (6-decimal raw → dollars).** (1 connections) — `broker/live_broker.py`
- **Submit a real limit order to the Polymarket CLOB.      market: same dict as pape** (1 connections) — `broker/live_broker.py`
- **Cancel an open limit order by ID. Returns True on success.** (1 connections) — `broker/live_broker.py`
- **Return all open (unfilled) orders on the CLOB.** (1 connections) — `broker/live_broker.py`
- **Return all confirmed fills from the CLOB (entire wallet history).** (1 connections) — `broker/live_broker.py`
- **Check if a submitted order has been filled, partially filled, or is still open.** (1 connections) — `broker/live_broker.py`
- **Sell (exit) a position by posting a SELL order on the token.     Used for stop-l** (1 connections) — `broker/live_broker.py`
- **Check for resolved winning positions and report claimable USDC.      On Polymark** (1 connections) — `broker/live_broker.py`

## Relationships

- [[Portfolio Resolution]] (11 shared connections)
- [[CLOB Position Queries]] (6 shared connections)
- [[Terminal Dashboard]] (2 shared connections)
- [[Paper Trading Broker]] (1 shared connections)

## Source Files

- `broker/live_broker.py`

## Audit Trail

- EXTRACTED: 78 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*