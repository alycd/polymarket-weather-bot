# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An autonomous quantitative trading bot that exploits pricing inefficiencies in Polymarket weather derivative markets. It fetches multi-model meteorological ensemble forecasts (GFS, ECMWF, ICON, GEM, Météo-France), computes probability distributions over temperature outcomes, then executes trades when model prices diverge significantly from CLOB market prices.

Operates in two modes: **paper trading** (simulated, safe) and **live trading** (real USDC on Polygon).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in POLYMARKET_PRIVATE_KEY, POLYMARKET_PROXY_ADDRESS
python scripts/gen_clob_creds.py  # Generate CLOB credentials
```

## Common Commands

```bash
# One-off scans
python main.py --scan --paper           # Find and enter positions (paper)
python main.py --resolve --paper        # Settle resolved markets
python main.py --exit-scan --paper      # Risk management exits
python main.py --nowcast --paper        # Intraday forecast update
python main.py --scan --live            # Same, with real money

# Monitoring
python main.py --positions              # Open trades
python main.py --history                # Resolved trades
python main.py --stats                  # Full metrics
python main.py --cities                 # Configured stations
python main.py --export-calibration     # Brier scores CSV

# Web dashboard (port 5001)
python web_dashboard.py

# Autonomous operation (runs all scans on schedule)
python daemon.py --mode paper
python daemon.py --mode live

# Backtesting / simulation
python simulate.py [--seed 42] [--trials 500]
python backtest.py
python real_backtest.py
python reset_paper.py                   # Wipe paper trading state
```

No test suite — correctness is verified via `simulate.py` (Monte Carlo) and `backtest.py` (historical replay).

## Architecture

### Data Flow

```
Open-Meteo (5 NWP models) → bias correction → ensemble stats → bucket probability
                                                                        ↓
NOAA ASOS observations → nowcaster (blends live obs) ────────> edge = model_prob - market_mid
                                                                        ↓
Polymarket Gamma API (markets) + CLOB API (prices) ────────> risk filters → Kelly sizing → execute
```

### Module Responsibilities

**`main.py`** — CLI entry point. Orchestrates the full scan cycle: fetch markets → signals → filters → size → execute. Holds a `polymarket_bot.lock` file to prevent duplicate scans.

**`daemon.py`** — Scheduler. Runs main.py at fixed UTC times (05:30, 09:45, 13:30, 19:17) plus every 30 min for opportunistic/exit scans.

**`config.py`** — Single source of truth for all parameters (MIN_EDGE, Kelly fractions, entry price gates, 40+ city configs, API URLs). Change behavior here, not in source files.

**`db.py`** — All SQLite operations. WAL mode, dual-database switching (paper_trades.db vs live_trades.db). No raw SQL outside this file.

**`data/`** — External data fetchers:
- `openmeteo.py` — 5 NWP models in parallel with retry/rate limiting
- `noaa.py` — ASOS historical obs and daily actuals
- `polymarket.py` — Gamma API (market metadata) + CLOB API (live prices, order submission)

**`signals/`** — Signal pipeline:
- `ensemble.py` — Weighted mean/std (ECMWF=1.8x, HRRR=1.5x), freshness decay
- `edge_calculator.py` — Core alpha engine: Student-t bucket probabilities vs market price
- `nowcaster.py` — Blends ASOS live obs into forecast (0% at midnight → 80% near close)
- `bias_corrector.py` — Per-city/model/month corrections from historical ASOS data

**`broker/`** — Execution:
- `paper_broker.py` — Simulated fills at CLOB mid-prices with full risk checks
- `live_broker.py` — Real CLOB order submission via py-clob-client
- `position_manager.py` — Resolution logic and P&L settlement

**`web_dashboard.py`** — Flask app (port 5001). REST endpoints at `/api/positions`, `/api/history`, `/api/stats`, `/api/run/<cmd>`.

**`ops_state.py`** — Health monitoring, job duration tracking, datasource status.

### Key Risk Parameters (config.py)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `MIN_EDGE` | 0.10 | Min model-market gap to enter |
| `NO_ENTRY_MIN_PRICE` / `MAX_PRICE` | 0.20 / 0.75 | NO bet price gate (empirically tuned) |
| `KELLY_FRACTION` | 0.10 live / 0.25 paper | Fractional Kelly |
| `MAX_TRADE_USDC` | $15 | Hard per-trade cap |
| `MAX_DEPLOYED_FRACTION` | 0.60 | Max % portfolio in open positions |
| `KING_CONFLICT_MAX_C` | 3.5°C | ECMWF vs GFS disagreement threshold |
| `FORECAST_T_DF` | 4 | Student-t df (fat tails for temperature) |
| `BASE_FORECAST_STD_C` | 2.00°C | Additive uncertainty buffer |

### Database Schema

SQLite with WAL mode. Key tables: `stations`, `historical_obs`, `model_forecasts`, `bias_corrections`, `markets`, `trades`, `daily_pnl`, `bankroll`, `scan_log`. All access goes through `db.py` context managers.

### Deployment

```bash
sudo cp polybot.service /etc/systemd/system/
sudo systemctl enable polybot && sudo systemctl start polybot
```
