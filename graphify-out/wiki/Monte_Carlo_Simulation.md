# Monte Carlo Simulation

> 25 nodes · cohesion 0.12

## Key Concepts

- **simulate.py** (13 connections) — `simulate.py`
- **simulate_one_trial()** (10 connections) — `simulate.py`
- **run_simulation()** (5 connections) — `simulate.py`
- **market_implied_prob()** (4 connections) — `simulate.py`
- **prob_in_bucket()** (4 connections) — `simulate.py`
- **bucket_resolved_yes()** (3 connections) — `simulate.py`
- **compute_ensemble_stats_sim()** (3 connections) — `simulate.py`
- **compute_metrics()** (3 connections) — `simulate.py`
- **compute_pnl()** (3 connections) — `simulate.py`
- **fetch_era5_actuals()** (3 connections) — `simulate.py`
- **generate_buckets()** (3 connections) — `simulate.py`
- **kelly_size()** (3 connections) — `simulate.py`
- **print_iteration_table()** (1 connections) — `simulate.py`
- **Monte Carlo temperature market simulator.  Injects realistic NWP forecast errors** (1 connections) — `simulate.py`
- **P(temp in [lo, hi]) under N(mean, std). None = unbounded.** (1 connections) — `simulate.py`
- **Simulate the market-implied probability for a bucket.      The 'crowd' uses a GF** (1 connections) — `simulate.py`
- **Did the actual temperature fall in this bucket?** (1 connections) — `simulate.py`
- **Binary option PnL.     YES bet: stake size_usdc at entry_price. Win: +size_usdc*** (1 connections) — `simulate.py`
- **Returns (kelly_f, size_usdc).** (1 connections) — `simulate.py`
- **Fetch ERA5 daily max temps from Open-Meteo Archive.** (1 connections) — `simulate.py`
- **One Monte Carlo trial for a single day.     Returns list of signal records (may** (1 connections) — `simulate.py`
- **Compute aggregate metrics from simulation results.** (1 connections) — `simulate.py`
- **Run full Monte Carlo simulation.      Returns dict with metrics + per-city break** (1 connections) — `simulate.py`
- **Generate N_BUCKETS 1°C-wide buckets centred around ensemble_mean_c.     Returns** (1 connections) — `simulate.py`
- **Weighted ensemble stats without DB dependency.** (1 connections) — `simulate.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `simulate.py`

## Audit Trail

- EXTRACTED: 70 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*