# Position Query & Sell

> 10 nodes · cohesion 0.20

## Key Concepts

- **resolve_expired_trades** (11 connections) — `broker/position_manager.py`
- **cmd_exit_scan** (3 connections) — `main.py`
- **resolve_trade** (2 connections) — `db.py`
- **sell_position** (1 connections) — `broker/live_broker.py`
- **get_actual_high_c** (1 connections) — `broker/position_manager.py`
- **_query_polymarket_outcome** (1 connections) — `broker/position_manager.py`
- **Two-Step Resolution Strategy (PM outcome + temp for bias)** (1 connections) — `broker/position_manager.py`
- **get_weather_fallback_trades** (1 connections) — `db.py`
- **resolve_tsa_prediction** (1 connections) — `db.py`
- **update_trade_outcome** (1 connections) — `db.py`

## Relationships

- [[Terminal Dashboard]] (2 shared connections)
- [[Forecast Pruning & Storage]] (1 shared connections)
- [[Event & KV Store]] (1 shared connections)
- [[Live CLOB Trade Execution]] (1 shared connections)

## Source Files

- `broker/live_broker.py`
- `broker/position_manager.py`
- `db.py`
- `main.py`

## Audit Trail

- EXTRACTED: 23 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*