# Polymarket Weather Prediction Bot

An autonomous quantitative trading system that identifies and exploits pricing inefficiencies in [Polymarket](https://polymarket.com) weather derivative markets. The bot ingests multi-model meteorological ensemble forecasts, computes a probability distribution over temperature outcomes, and bets when its model price diverges significantly from the CLOB market price.

---

## Performance

### Paper Trading (Simulated fills at real CLOB prices)

| Metric | Value |
|--------|-------|
| **Total trades** | 104 resolved positions |
| **Win rate** | **66.3%** (69W / 35L) |
| **Gross P&L** | **+$70.30 USDC** |
| **Total capital deployed** | $1,437.09 USDC |
| **ROI on deployed capital** | **+4.9%** |
| **Period** | May 23 – Jun 2, 2026 (10 days) |

**Direction breakdown:**

| Side | Trades | Win Rate | P&L | ROI |
|------|--------|----------|-----|-----|
| NO   | 97     | 68%      | +$118.03 | +8.9% |
| YES  | 7      | 43%      | -$47.73  | -45.5% |

**Top 8 trades:**

| Market | Entry | Size | P&L | ROI |
|--------|-------|------|-----|-----|
| Los Angeles NO [66,67)°F, May 27 | $0.31 | $15 | +$30.48 | +203% |
| Lucknow NO [40.5,41.5)°C, May 27 | $0.39 | $15 | +$22.01 | +147% |
| Paris NO [31.5,32.5)°C, May 24 | $0.40 | $15 | +$19.94 | +133% |
| Tel Aviv NO [25.5,26.5)°C, May 24 | $0.46 | $15 | +$17.70 | +118% |
| Paris NO [30.5,31.5)°C, May 23 | $0.47 | $15 | +$17.10 | +114% |
| Hong Kong NO [30.5,31.5)°C, May 23 | $0.44 | $15 | +$16.02 | +107% |
| Los Angeles NO [68,69)°F, May 28 | $0.54 | $15 | +$12.95 | +86% |
| Miami NO [88,89)°F, May 29 | $0.55 | $15 | +$12.52 | +84% |

**City breakdown:**

| City | Trades | Win Rate | P&L | ROI |
|------|--------|----------|-----|-----|
| Los Angeles | 8 | 88% | +$73.51 | +67.5% |
| Lucknow | 3 | 100% | +$42.22 | +101.9% |
| Tel Aviv | 4 | 100% | +$36.11 | +68.8% |
| Sao Paulo | 4 | 100% | +$29.01 | +48.3% |
| Austin | 4 | 100% | +$25.79 | +43.0% |
| Miami | 3 | 100% | +$25.77 | +62.5% |
| Shenzhen | 3 | 100% | +$17.81 | +49.9% |
| Dallas | 3 | 100% | +$17.29 | +38.4% |
| Seoul | 4 | 25% | -$42.14 | -70.2% |
| San Francisco | 4 | 25% | -$38.85 | -64.9% |
| Tokyo | 5 | 40% | -$27.55 | -38.8% |
| Chicago | 3 | 33% | -$19.63 | -47.3% |

> **Note:** Paper trading uses real-time CLOB mid prices for entry simulation. Actual live fills would incur bid-ask spread costs (~0.5–2pp per trade) not reflected here.

### Live Trading (Real USDC on-chain)

The system has been deployed live on Polygon via the Polymarket CLOB API. Live resolution tracking is active.

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
│   ├── position_manager.py  # Resolution engine + P&L settlement
│   └── correlation_filter.py  # Cross-city region caps, bucket caps, NO proximity filter
│
├── metrics/
│   ├── calibration.py       # Shrinkage factor from resolved trade history
│   ├── sharpe.py            # Rolling risk-adjusted return tracking
│   └── reporting.py         # Dashboard data aggregation
│
└── web_dashboard.py         # Flask dashboard — open positions sorted by soonest expiry
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
   - **Correlation filter** (see below)

7. **Kelly sizing** — Fractional Kelly (25%) with tier scaling and a hard cap of $15/trade.

---

## Correlation Filter (`broker/correlation_filter.py`)

Three independent checks gate every trade before execution:

**Check 1 — Region cap:** At most N unique cities with open positions per weather region per target date. Prevents independently betting on cities in the same synoptic weather system (e.g., a cold front hitting London and Paris is one bet, not two).

| Region | Cap | Cities |
|--------|-----|--------|
| Europe_W | 3 | London, Paris, Madrid, Munich, Milan |
| NA_East | 3 | NYC, Chicago, Atlanta, Dallas, Miami, Toronto |
| NA_West | 2 | Seattle |
| LatAm | 3 | Buenos Aires, Sao Paulo |
| Other | 3 | Hong Kong, Tel Aviv |

**Check 2 — Bucket cap:** Max simultaneous open bucket trades per city per date — 3 for YES bets (correlated upside), 5 for NO bets (mutually exclusive loss risk).

**Check 3 — NO proximity filter:** Adjacent NO bets on the same city and target date partially cancel: if the actual high lands in one bucket, that NO loses while the adjacent NO wins — wasting capital on a net-flat outcome. Any new NO trade whose bucket is within 2°F (1°C) of an existing open NO is evaluated in two modes:

- **Same-scan (race condition):** Blocked unconditionally. Trades entered within the same scan run can't reprice against each other — this is pure duplication.
- **Cross-scan (model updated):** The incumbent trade's unrealized PnL is checked against current CLOB prices. If it's **negative** — the model updated, the market repriced, and the new signal is better — the incumbent is closed at the current market price (`stop_loss`) and the new trade is entered in its place. If the incumbent is still **profitable**, the new trade is skipped.

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

#### Wallet addresses (live account)

| Address | Role |
|---------|------|
| `0xDa77...c6Ed` | Deposit address — send USDC here to top up; UI shows this in the deposit modal |
| `0xE857...66F4` | Account/proxy wallet — holds the pUSD balance, what the bot trades from (`POLYMARKET_PROXY_ADDRESS`) |
| `0x28f6...D48E` | Signer key the bot uses to sign orders (`POLYMARKET_PRIVATE_KEY`) |

Funds deposited via the UI are swept from the deposit address and credited to the
proxy wallet as **pUSD** (not USDC), so `POLYMARKET_SIGNATURE_TYPE=3` is required
in `.env` for the bot to see the balance and sign orders against it.

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
| `kv_store` (`cal_shrinkage_*` only) | 1 | Calibration shrinkage factor — computed from resolved trades, which live starts with none of; without seeding it live falls back to 1.0 (no overconfidence correction) |

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
