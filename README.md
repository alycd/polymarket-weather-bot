# Polymarket Weather Prediction Bot

An autonomous quantitative trading system that identifies and exploits pricing inefficiencies in [Polymarket](https://polymarket.com) weather derivative markets. The bot ingests multi-model meteorological ensemble forecasts, computes a probability distribution over temperature outcomes, and bets when its model price diverges significantly from the CLOB market price.

---

## Performance

### Paper Trading (Simulated fills at real CLOB prices)

| Metric | Value |
|--------|-------|
| **Total trades** | 63 resolved positions |
| **Win rate** | **82.5%** (52W / 11L) |
| **Gross P&L** | **+$806.49 USDC** |
| **Total capital deployed** | $2,264.15 USDC |
| **ROI on deployed capital** | **+35.6%** |
| **Avg model edge at entry** | **20.6 percentage points** above market price |
| **Edge range** | 2.5pp – 93pp |
| **Period** | Mar 28 – Apr 3, 2026 (7 days) |

**Direction breakdown:**

| Side | Trades | Win Rate | P&L | ROI |
|------|--------|----------|-----|-----|
| NO   | 60     | 83%      | +$797.68 | +36.1% |
| YES  | 3      | 67%      | +$8.81   | +17.1% |

**Top 5 trades:**

| Market | Entry | Size | P&L | ROI |
|--------|-------|------|-----|-----|
| Houston NO, Mar 28 | $0.06 | $17 | +$249.14 | +1438% |
| Houston NO, Apr 2 | $0.44 | $157 | +$203.39 | +130% |
| Houston NO, Apr 1 | $0.43 | $128 | +$169.26 | +133% |
| Tel Aviv NO, Apr 1 | $0.47 | $138 | +$159.23 | +115% |
| San Francisco NO, Apr 2 | $0.54 | $143 | +$124.10 | +87% |

**City breakdown:**

| City | Trades | Win Rate | P&L | ROI |
|------|--------|----------|-----|-----|
| Houston | 6 | 83% | +$623.53 | +186.7% |
| San Francisco | 2 | 100% | +$230.20 | +90.9% |
| Tel Aviv | 1 | 100% | +$159.23 | +115.1% |
| Dallas | 12 | 92% | +$79.26 | +28.8% |
| Seattle | 5 | 100% | +$17.09 | +42.4% |
| Miami | 6 | 100% | +$14.08 | +23.1% |
| Buenos Aires | 11 | 82% | +$8.59 | +3.1% |
| Paris | 2 | 0% | -$233.64 | -100% |

> **Note:** Paper trading uses real-time CLOB mid prices for entry simulation. Actual live fills would incur bid-ask spread costs (~0.5–2pp per trade) not reflected here.

### Live Trading (Real USDC on-chain)

The system has been deployed live on Polygon via the Polymarket CLOB API. As of Apr 5, 2026, **18 real positions** are on-chain across 8 cities (Atlanta, Buenos Aires, Chicago, Miami, Sao Paulo, Seattle, Munich, San Francisco), entered between Apr 1–3, 2026. Live resolution tracking is active and awaiting market settlement.

---

## Architecture

```
polymarket-weather-bot/
├── main.py                  # CLI entry point — scan, exit-scan, resolve, status
├── daemon.py                # Scheduler: runs scans on NWP model update cadence
├── config.py                # All tunable parameters (edges, Kelly, cities, filters)
├── db.py                    # SQLite layer (paper_trades.db / live_trades.db)
│
├── data/
│   ├── openmeteo.py         # Multi-model forecast fetcher (GFS, ECMWF, ICON, GEM, MF)
│   ├── noaa.py              # ASOS station historical observations
│   ├── polymarket.py        # CLOB price + order book queries
│   ├── climatology.py       # Historical temperature distribution
│   └── ...
│
├── signals/
│   ├── ensemble.py          # Combines 5 NWP models → mean, std, score
│   ├── edge_calculator.py   # Core alpha engine: model prob → Kelly bet
│   ├── nowcaster.py         # Blends live observations into forecast
│   ├── bias_corrector.py    # Per-city/model bias correction
│   └── ...
│
├── broker/
│   ├── paper_broker.py      # Simulated execution with all risk checks
│   ├── live_broker.py       # Real CLOB order submission via py-clob-client
│   └── position_manager.py  # Resolution engine + P&L settlement
│
├── metrics/
│   ├── calibration.py       # Shrinkage factor from resolved trade history
│   ├── sharpe.py            # Rolling risk-adjusted return tracking
│   └── reporting.py         # Dashboard data aggregation
│
└── web_dashboard.py         # Flask dashboard with live P&L + open positions
```

---

## Signal Generation Pipeline

1. **Forecast ingestion** — Fetches the 5 latest NWP runs for the target ICAO station from Open-Meteo: GFS, ECMWF, ICON, GEM, Météo-France.

2. **Ensemble statistics** — Computes mean, standard deviation, and spread score. High std (models disagree) increases position uncertainty. Low std for NO bets is a skip signal — tight model agreement means temperature is likely heading for a specific bucket.

3. **Nowcasting** — If the station has a real-time ASOS observation for the current day, it blends into the forecast using a time-weighted regime (observation weight rises from 0% at midnight to 80% by market close).

4. **Bucket probability** — Integrates a Student-t distribution (ν=4, fat tails) over the temperature bucket `[lo, hi]` to compute `P(actual_high ∈ bucket)`.

5. **Edge calculation** — `edge = model_prob − market_mid_price`. Only signals where `|edge| > adaptive_min_edge` are tradeable.

6. **Filters applied before entry:**
   - Minimum edge threshold (dynamic, scales with lead time)
   - NO entry price gate: 0.20 – 0.75 (empirically optimal range)
   - Ensemble std gate: skip NO bets when std < 0.8°C (model consensus = bad for NO)
   - Order book depth check: skip if top-5 CLOB depth < $150 USDC
   - Timing filter: skip if market price has been converging toward model value
   - Global deployment cap: max 40% of portfolio in open positions

7. **Kelly sizing** — Fractional Kelly (25%) with tier scaling and a hard cap of $15/trade.

---

## Key Parameters (`config.py`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MIN_EDGE` | 0.12 | Minimum model–market gap to enter |
| `KELLY_FRACTION` | 0.10 | Fractional Kelly multiplier (live); 0.25 for paper |
| `MAX_TRADE_USDC` | 15.0 | Hard per-trade dollar cap |
| `MAX_DEPLOYED_FRACTION` | 0.40 | Max % of portfolio in open positions |
| `NO_ENTRY_MIN_PRICE` | 0.35 | Skip NO bets below 35¢ |
| `NO_ENTRY_MAX_PRICE` | 0.75 | Skip NO bets above 75¢ |
| `NO_MIN_ENSEMBLE_STD` | 0.8°C | Skip NO bets when models tightly agree |
| `FORECAST_T_DF` | 4 | Student-t degrees of freedom (fat tails) |

---

## Setup

### Requirements

```bash
pip install -r requirements.txt
# Key deps: py-clob-client, flask, requests, python-dotenv, scipy
```

### Credentials

```bash
cp .env.example .env
# Fill in POLYMARKET_PRIVATE_KEY, POLYMARKET_PROXY_ADDRESS, and API credentials
# Generate CLOB API creds: python scripts/gen_clob_creds.py
```

### Running

```bash
# Paper trading scan (safe, no real money)
python main.py --scan --paper

# Live scan (real orders)
python main.py --scan --live

# Check for exits / stop-losses
python main.py --exit-scan --live

# Resolve settled markets and update P&L
python main.py --resolve --live
```

**`--scan` vs `--exit-scan`**

These do fundamentally different things:

- **`--scan`** finds and enters new positions — fetches open markets, runs the full signal pipeline (NWP models → ensemble → edge calculation), applies entry filters, sizes and executes trades.

- **`--exit-scan`** manages existing positions — loops over all open trades, fetches live prices, and exits early if any of these conditions are met:
  1. **Take profit** — position is worth 3× entry cost
  2. **Edge reversal** — market has moved so much the edge has flipped >0.10 against us
  3. **Closing soon** — market resolves within 2 hours

In the daemon, `--scan` runs at 4 fixed UTC times plus every 30 minutes opportunistically; `--exit-scan` runs every 30 minutes as a risk management check.

```bash

# Web dashboard (port 5001)
python web_dashboard.py

# Autonomous daemon (scheduled scans + exits)
python daemon.py
```

### Deployment (GCP / systemd)

The `polybot.service` and `polybot-dashboard.service` files are ready-to-use systemd unit files for running the daemon and dashboard as persistent services on a GCP VM.

```bash
sudo cp polybot.service /etc/systemd/system/
sudo systemctl enable polybot
sudo systemctl start polybot
```

---

## Paper → Live Migration

After running in paper mode for calibration, use the included migration script to carry over learnings before switching to live trading. The two databases (`paper_trades.db` / `live_trades.db`) share an identical schema — only the calibration tables need to be ported.

**What gets copied:**

| Table | Rows (example) | Why |
|-------|----------------|-----|
| `stations` | 37 | City configs and station status |
| `historical_obs` | ~7,000 | ASOS + ERA5 observed actuals (ground truth) |
| `model_forecasts` | ~1,600 | Historical NWP predictions (needed to recompute bias) |
| `bias_corrections` | ~36 | Per-city/model/month error corrections |
| `climatology` | varies | 30-year WMO baselines |

Trades, P&L, bankroll, and operational state start fresh in the live DB.

**Migration steps:**

```bash
# 1. Freshen paper calibration one last time
python main.py --backfill

# 2. Copy learnings to live DB (backs up live DB automatically before overwriting)
python migrate_paper_to_live.py

# 3. Freshen model forecasts in live DB (~10 min)
python main.py --backfill --live

# 4. Switch daemon to live
python daemon.py --mode live
```

**Bias corrections accumulate over time.** Run `python main.py --backfill` weekly to keep corrections fresh — the bias corrector uses exponential decay with a 180-day halflife, so the most recent observations carry the most weight. Run it immediately after any multi-day temperature anomaly (heatwave, cold snap) to recapture regime shifts.

---

## Data Sources

| Source | Used For |
|--------|----------|
| [Open-Meteo](https://open-meteo.com) | NWP forecasts: GFS, ECMWF, ICON, GEM, Météo-France |
| [NOAA ASOS](https://mesonet.agron.iastate.edu/ASOS/) | Historical + real-time station observations |
| [Polymarket Gamma API](https://gamma-api.polymarket.com) | Market metadata, resolution outcomes |
| [Polymarket CLOB API](https://clob.polymarket.com) | Live order book prices, order submission |
| [Polymarket Data API](https://data-api.polymarket.com) | Portfolio positions, mark-to-market values |

---

## Disclaimer

This is an experimental research project. Prediction market trading involves real financial risk. Past paper trading performance does not guarantee live results. The average edge per trade is small and individual positions can result in total loss.
