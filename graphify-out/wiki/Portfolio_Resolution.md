# Portfolio Resolution

> 21 nodes · cohesion 0.15

## Key Concepts

- **main.py** (64 connections) — `main.py`
- **cmd_scan()** (26 connections) — `main.py`
- **resolve_expired_trades()** (9 connections) — `broker/position_manager.py`
- **cmd_resolve()** (9 connections) — `main.py`
- **get_polymarket_positions_value_usd()** (7 connections) — `broker/live_broker.py`
- **_run_daily_reconciliation_if_due()** (6 connections) — `main.py`
- **find_consistency_signals()** (6 connections) — `signals/consistency_checker.py`
- **get_model_weights()** (5 connections) — `signals/bias_corrector.py`
- **_acquire_scan_lock()** (4 connections) — `main.py`
- **_release_scan_lock()** (3 connections) — `main.py`
- **_signal_health_policy()** (3 connections) — `main.py`
- **mark_daily_reconcile()** (3 connections) — `ops_state.py`
- **should_run_daily_reconcile()** (3 connections) — `ops_state.py`
- **Total mark-to-market value of open positions (Data API — same as UI).** (1 connections) — `broker/live_broker.py`
- **Find all open trades whose target_date has passed and resolve them.      Win/los** (1 connections) — `broker/position_manager.py`
- **Resolve all expired open trades.** (1 connections) — `main.py`
- **1. Fetch all live temperature markets from Polymarket     2. For each market, ge** (1 connections) — `main.py`
- **Acquire an exclusive lockfile to prevent two --scan instances running     simult** (1 connections) — `main.py`
- **Compute data-driven per-model inverse-variance weights for this station.      Us** (1 connections) — `signals/bias_corrector.py`
- **Main entry point.      markets: list of parsed market dicts (same city, filtered** (1 connections) — `signals/consistency_checker.py`
- **_MODEL_WEIGHTS** (1 connections) — `signals/ensemble.py`

## Relationships

- [[Terminal Dashboard]] (13 shared connections)
- [[Live Broker Execution]] (11 shared connections)
- [[Operations State]] (8 shared connections)
- [[NOAA Weather Fetching]] (8 shared connections)
- [[Paper Trading Broker]] (7 shared connections)
- [[Polymarket Position Manager]] (6 shared connections)
- [[Climatology Data]] (6 shared connections)
- [[CLOB Position Queries]] (4 shared connections)
- [[Neighbor Temperature Validation]] (4 shared connections)
- [[Crypto Market Data]] (3 shared connections)
- [[Forecast Bias Correction]] (3 shared connections)
- [[Signal Consistency]] (3 shared connections)

## Source Files

- `broker/live_broker.py`
- `broker/position_manager.py`
- `main.py`
- `ops_state.py`
- `signals/bias_corrector.py`
- `signals/consistency_checker.py`
- `signals/ensemble.py`

## Audit Trail

- EXTRACTED: 156 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*