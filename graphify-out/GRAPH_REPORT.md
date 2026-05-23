# Graph Report - .  (2026-05-23)

## Corpus Check
- 53 files · ~55,024 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 756 nodes · 1254 edges · 90 communities (48 shown, 42 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 38 edges (avg confidence: 0.84)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Terminal Dashboard|Terminal Dashboard]]
- [[_COMMUNITY_README Docs Index|README Docs Index]]
- [[_COMMUNITY_NOAA Weather Fetching|NOAA Weather Fetching]]
- [[_COMMUNITY_Polymarket Position Manager|Polymarket Position Manager]]
- [[_COMMUNITY_Database Core Layer|Database Core Layer]]
- [[_COMMUNITY_Web Frontend UI|Web Frontend UI]]
- [[_COMMUNITY_Monte Carlo Simulation|Monte Carlo Simulation]]
- [[_COMMUNITY_Backtesting Engine|Backtesting Engine]]
- [[_COMMUNITY_Climatology Data|Climatology Data]]
- [[_COMMUNITY_TSA Passenger Forecasting|TSA Passenger Forecasting]]
- [[_COMMUNITY_Live Broker Execution|Live Broker Execution]]
- [[_COMMUNITY_Portfolio Resolution|Portfolio Resolution]]
- [[_COMMUNITY_Operations State|Operations State]]
- [[_COMMUNITY_Backtest Runner|Backtest Runner]]
- [[_COMMUNITY_Paper Trading Broker|Paper Trading Broker]]
- [[_COMMUNITY_Real Historical Backtest|Real Historical Backtest]]
- [[_COMMUNITY_Polymarket Market Data|Polymarket Market Data]]
- [[_COMMUNITY_CLOB Position Queries|CLOB Position Queries]]
- [[_COMMUNITY_Signal Consistency|Signal Consistency]]
- [[_COMMUNITY_Forecast Bias Correction|Forecast Bias Correction]]
- [[_COMMUNITY_Market Price Scraper|Market Price Scraper]]
- [[_COMMUNITY_Position Query & Sell|Position Query & Sell]]
- [[_COMMUNITY_Crypto Market Data|Crypto Market Data]]
- [[_COMMUNITY_TSA Market Integration|TSA Market Integration]]
- [[_COMMUNITY_Real Backtest Processing|Real Backtest Processing]]
- [[_COMMUNITY_Paper Broker Internals|Paper Broker Internals]]
- [[_COMMUNITY_Forecast DB Queries|Forecast DB Queries]]
- [[_COMMUNITY_Event & KV Store|Event & KV Store]]
- [[_COMMUNITY_Signal Ensemble Weights|Signal Ensemble Weights]]
- [[_COMMUNITY_Live CLOB Trade Execution|Live CLOB Trade Execution]]
- [[_COMMUNITY_Live Position Retrieval|Live Position Retrieval]]
- [[_COMMUNITY_Correlation Risk Filter|Correlation Risk Filter]]
- [[_COMMUNITY_Deribit Options Data|Deribit Options Data]]
- [[_COMMUNITY_Neighbor Temperature Validation|Neighbor Temperature Validation]]
- [[_COMMUNITY_Daemon Job Scheduler|Daemon Job Scheduler]]
- [[_COMMUNITY_Forecast Pruning & Storage|Forecast Pruning & Storage]]
- [[_COMMUNITY_Confidence Tier System|Confidence Tier System]]
- [[_COMMUNITY_Crypto Edge Calculator|Crypto Edge Calculator]]
- [[_COMMUNITY_Model Config Settings|Model Config Settings]]
- [[_COMMUNITY_Temperature Unit Utils|Temperature Unit Utils]]
- [[_COMMUNITY_Correlation City Filter|Correlation City Filter]]
- [[_COMMUNITY_Web UI Loading & Refresh|Web UI Loading & Refresh]]
- [[_COMMUNITY_Claude Settings Config|Claude Settings Config]]
- [[_COMMUNITY_Daemon Schedule Builder|Daemon Schedule Builder]]
- [[_COMMUNITY_Config Module|Config Module]]
- [[_COMMUNITY_DB Bulk Price Insert|DB Bulk Price Insert]]
- [[_COMMUNITY_DB Bias Batch Queries|DB Bias Batch Queries]]
- [[_COMMUNITY_DB Key-Value Store|DB Key-Value Store]]
- [[_COMMUNITY_DB Mode Management|DB Mode Management]]
- [[_COMMUNITY_DB Price History Query|DB Price History Query]]
- [[_COMMUNITY_DB Forecast Run History|DB Forecast Run History]]
- [[_COMMUNITY_DB Performance Metrics|DB Performance Metrics]]
- [[_COMMUNITY_DB Recent Prices|DB Recent Prices]]
- [[_COMMUNITY_DB Resolved Trades|DB Resolved Trades]]
- [[_COMMUNITY_DB Forecast Dedup|DB Forecast Dedup]]
- [[_COMMUNITY_DB Forecast Pruning|DB Forecast Pruning]]
- [[_COMMUNITY_DB Historical Obs Upsert|DB Historical Obs Upsert]]
- [[_COMMUNITY_DB Forecast Date Queries|DB Forecast Date Queries]]
- [[_COMMUNITY_DB Fallback Trade Queries|DB Fallback Trade Queries]]
- [[_COMMUNITY_DB Atomic Trade Open|DB Atomic Trade Open]]
- [[_COMMUNITY_DB TSA Prediction Record|DB TSA Prediction Record]]
- [[_COMMUNITY_DB TSA Prediction Resolve|DB TSA Prediction Resolve]]
- [[_COMMUNITY_DB KV Set Operations|DB KV Set Operations]]
- [[_COMMUNITY_DB Prediction Resolution|DB Prediction Resolution]]
- [[_COMMUNITY_DB Trade Resolution|DB Trade Resolution]]
- [[_COMMUNITY_DB Bankroll Management|DB Bankroll Management]]
- [[_COMMUNITY_DB Mode Set|DB Mode Set]]
- [[_COMMUNITY_DB Trade Outcome Update|DB Trade Outcome Update]]
- [[_COMMUNITY_DB Trade Source Update|DB Trade Source Update]]
- [[_COMMUNITY_CLOB Credentials Generator|CLOB Credentials Generator]]
- [[_COMMUNITY_Web UI Modal & Charts|Web UI Modal & Charts]]
- [[_COMMUNITY_DB Insert Trade|DB Insert Trade]]
- [[_COMMUNITY_DB Active Markets Query|DB Active Markets Query]]
- [[_COMMUNITY_DB Bias Upsert|DB Bias Upsert]]
- [[_COMMUNITY_DB Bias Query|DB Bias Query]]
- [[_COMMUNITY_DB Bulk Price Alt|DB Bulk Price Alt]]
- [[_COMMUNITY_DB Prediction Record|DB Prediction Record]]
- [[_COMMUNITY_DB All Biases Query|DB All Biases Query]]
- [[_COMMUNITY_TSA Hub Airport Config|TSA Hub Airport Config]]
- [[_COMMUNITY_City Aliases Config|City Aliases Config]]
- [[_COMMUNITY_Real Backtest CLOB Price|Real Backtest CLOB Price]]
- [[_COMMUNITY_Flask Web App|Flask Web App]]
- [[_COMMUNITY_Celsius-Fahrenheit Convert|Celsius-Fahrenheit Convert]]
- [[_COMMUNITY_Paper Broker Stop Loss|Paper Broker Stop Loss]]
- [[_COMMUNITY_CLOB Client Init|CLOB Client Init]]

## God Nodes (most connected - your core abstractions)
1. `_conn()` - 53 edges
2. `cmd_scan()` - 26 edges
3. `main()` - 23 edges
4. `cmd_scan` - 23 edges
5. `compute_edge()` - 20 edges
6. `Polymarket Weather Prediction Bot` - 20 edges
7. `get_running_max_c()` - 14 edges
8. `compute_ensemble_stats()` - 14 edges
9. `get_market_prices()` - 14 edges
10. `fetch_historical_actuals()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `compute_ensemble_stats_sim` --semantically_similar_to--> `compute_nowcast_bucket_prob()`  [INFERRED] [semantically similar]
  simulate.py → signals/nowcaster.py
- `get_historical_high()` --conceptually_related_to--> `Query: Explain PnL`  [AMBIGUOUS]
  data/wunderground.py → graphify-out/memory/query_20260523_132645_explain_pnl.md
- `backtest main` --semantically_similar_to--> `real_backtest main`  [INFERRED] [semantically similar]
  backtest.py → real_backtest.py
- `_acquire_scan_lock` --semantically_similar_to--> `acquire_job_lock`  [INFERRED] [semantically similar]
  main.py → ops_state.py
- `clob_balance()` --calls--> `get_clob_balance()`  [EXTRACTED]
  web_dashboard.py → broker/live_broker.py

## Hyperedges (group relationships)
- **Ethereum/On-chain Dependencies** — requirements_eth_account, requirements_py_clob_client [INFERRED 0.85]
- **Signal Generation Pipeline Components** — readme_openmeteo_py, readme_ensemble_py, readme_nowcaster_py, readme_edge_calculator_py, readme_bias_corrector_py, readme_climatology_py [EXTRACTED 1.00]
- **Broker Layer Components** — readme_paper_broker_py, readme_live_broker_py, readme_position_manager_py [EXTRACTED 1.00]
- **Metrics and Reporting Components** — readme_calibration_py, readme_sharpe_py, readme_reporting_py [EXTRACTED 1.00]
- **Polymarket API Data Sources** — readme_polymarket_gamma_api, readme_polymarket_clob_api, readme_polymarket_data_api [EXTRACTED 1.00]
- **Full Scan Pipeline: market fetch → signal → broker → DB** — main_cmd_scan, broker_paper_execute_paper_trade, broker_correlation_filter_allows_trade, signals_neighbor_get_neighbor_penalty, signals_nowcaster_nowcast_confidence, db_open_trade_atomic [INFERRED 0.85]
- **Trade Resolution Pipeline: PM outcome → temp fetch → DB resolve → bias update** — broker_position_resolve_expired_trades, broker_position_query_polymarket_outcome, broker_position_get_actual_high_c, db_resolve_trade, db_upsert_historical_obs [INFERRED 0.85]
- **Metrics Dashboard Data Flow: DB → compute → render** — metrics_pnl_compute_pnl_summary, metrics_calibration_compute_calibration, metrics_sharpe_compute_sharpe, dashboard_render_dashboard, web_dashboard_build_data [INFERRED 0.75]
- **Temperature Market Signal Pipeline: bias correction → ensemble → edge calculation → confidence tiering** — signals_bias_corrector_get_corrected_ensemble, signals_ensemble_compute_ensemble_stats, signals_edge_calculator_compute_edge, signals_confidence_tier_apply_tier_to_signal [INFERRED 0.95]
- **Shared Kelly Sizing Pattern across Temperature, TSA, and Crypto edge calculators** — signals_edge_calculator_compute_edge, signals_tsa_edge_calculator_compute_tsa_edge, signals_crypto_edge_calculator_compute_crypto_edge [INFERRED 0.95]
- **Three parallel Polymarket market fetchers covering temperature, TSA, and crypto market types** — data_polymarket_fetch_temperature_markets, data_polymarket_tsa_fetch_tsa_markets, data_polymarket_crypto_fetch_crypto_markets [INFERRED 0.95]
- **Wunderground Temperature Resolution Pipeline** — data_wunderground_fetch_wu_page, data_wunderground_extract_json_blob, data_wunderground_parse_daily_high_from_blob, data_wunderground_get_historical_high [EXTRACTED 1.00]
- **Wunderground Live Hourly Observation Pipeline** — data_wunderground_fetch_wu_page, data_wunderground_extract_json_blob, data_wunderground_get_live_hourly, data_wunderground_get_running_max_wu [EXTRACTED 1.00]

## Communities (90 total, 42 thin omitted)

### Community 0 - "Terminal Dashboard"
Cohesion: 0.06
Nodes (56): build_history_table, build_positions_table, render_dashboard, get_all_biases_batch, get_all_stations, get_open_trades, get_resolved_trades, compute_calibration() (+48 more)

### Community 1 - "README Docs Index"
Cohesion: 0.07
Nodes (43): signals/bias_corrector.py (Per-city Bias Correction), metrics/calibration.py (Shrinkage Factor), data/climatology.py (Historical Temperature Distribution), config.py (Tunable Parameters), daemon.py (Scheduler), db.py (SQLite Layer), signals/edge_calculator.py (Alpha Engine), signals/ensemble.py (NWP Ensemble Combiner) (+35 more)

### Community 2 - "NOAA Weather Fetching"
Cohesion: 0.07
Nodes (39): fetch_asos_daily_max(), fetch_asos_today_hourly(), fetch_metar(), get_running_max_today(), NOAA / Iowa State Mesonet data fetchers.  Two roles:   1. Iowa State ASOS — hist, Fetch the most recent METAR observation for each station.     Returns dict: {ica, Get the running maximum temperature for today from ASOS hourly obs.     Returns, Fetch hourly ASOS data and compute daily max temperature.     Returns dict: {dat (+31 more)

### Community 3 - "Polymarket Position Manager"
Cohesion: 0.09
Nodes (32): get_actual_high_c(), _get_clob_token(), _query_polymarket_outcome(), Position manager — resolves open trades against actual temperature outcomes.  Re, Query Polymarket Gamma API to see if a market has resolved.     Returns 'yes' |, Look up clob_token_yes for a trade from the markets table., Get actual daily high temperature for a station/date.     Returns (temp_c, sourc, _extract_json_blob() (+24 more)

### Community 4 - "Database Core Layer"
Cohesion: 0.12
Nodes (32): adjust_bankroll(), already_in_market(), _conn(), count_historical_obs(), deactivate_markets_before(), get_active_markets(), get_all_biases(), get_all_climatology() (+24 more)

### Community 5 - "Web Frontend UI"
Cohesion: 0.09
Nodes (20): animCount(), closeModal(), eClass(), finishBtn(), fmtAbs$(), _fmtIso(), hideToast(), load() (+12 more)

### Community 6 - "Monte Carlo Simulation"
Cohesion: 0.12
Nodes (23): bucket_resolved_yes(), compute_ensemble_stats_sim(), compute_metrics(), compute_pnl(), fetch_era5_actuals(), generate_buckets(), kelly_size(), market_implied_prob() (+15 more)

### Community 7 - "Backtesting Engine"
Cohesion: 0.11
Nodes (24): fetch_day_ahead_forecast (backtest.py), generate_buckets (backtest.py), kelly_size (backtest.py), backtest main, CITIES config dict, Fat-tail Student-t distribution rationale (df=4), Trading Thresholds (MIN_EDGE, KELLY_FRACTION, etc.), Bankroll Double-Deduction Bug Fix (+16 more)

### Community 8 - "Climatology Data"
Cohesion: 0.12
Nodes (21): fetch_climatology(), Climatological baseline from Open-Meteo Climate API.  Fetches 30-year historical, Fetch 30-year daily max temperature climatology and compute per-month stats., fetch_all_models(), fetch_forecast_one_model(), fetch_historical_actuals(), fetch_historical_model_forecast(), fetch_past_model_forecasts() (+13 more)

### Community 9 - "TSA Passenger Forecasting"
Cohesion: 0.13
Nodes (21): compute_dow_baselines(), compute_yoy_ratio(), forecast_passengers(), get_holiday_info(), _parse_count(), _parse_tsa_date(), TSA passenger volume data fetcher.  Scrapes the TSA daily passenger counts page, Parse TSA date strings like '3/25/2026' or '2026-03-25' → 'YYYY-MM-DD'. (+13 more)

### Community 10 - "Live Broker Execution"
Cohesion: 0.14
Nodes (20): cancel_order(), execute_live_trade(), _get_client(), get_clob_balance(), get_clob_fills(), _get_no_token_id(), get_open_orders(), get_order_status() (+12 more)

### Community 11 - "Portfolio Resolution"
Cohesion: 0.15
Nodes (20): get_polymarket_positions_value_usd(), Total mark-to-market value of open positions (Data API — same as UI)., Find all open trades whose target_date has passed and resolve them.      Win/los, resolve_expired_trades(), _acquire_scan_lock(), cmd_resolve(), cmd_scan(), Resolve all expired open trades. (+12 more)

### Community 12 - "Operations State"
Cohesion: 0.26
Nodes (18): acquire_job_lock(), _dur_key(), get_datasource_health(), get_duration_p95(), get_last_error(), get_last_success(), get_ops_snapshot(), _iso_now() (+10 more)

### Community 13 - "Backtest Runner"
Cohesion: 0.17
Nodes (16): _c_to_f(), fetch_day_ahead_forecast(), generate_buckets(), kelly_size(), main(), Fetch what a model actually predicted for target_date issued 1 day ahead., 10 consecutive 1-unit buckets centred on the FORECAST mean (not actual)., f_to_c() (+8 more)

### Community 14 - "Paper Trading Broker"
Cohesion: 0.16
Nodes (15): check_stop_losses(), execute_paper_trade(), Paper broker — simulated order execution at real CLOB prices. Money is fake. Pri, Execute a paper trade based on an edge signal.      market: DB-style market dict, Stop-losses are disabled.     Kept as a no-op for compatibility with any older c, get_clob_orderbook(), get_market_prices(), Fetch CLOB order book for a YES token.     Returns dict with 'bids' and 'asks' l (+7 more)

### Community 15 - "Real Historical Backtest"
Cohesion: 0.22
Nodes (13): fetch_clob_price_24h_before(), fetch_day_ahead_forecast(), fetch_era5_for_city_date_range(), fetch_resolved_markets(), main(), Fetch CLOB price-history and find the price closest to 24h before end_dt.     Re, Fetch what a model predicted 1 day ahead for target_date (historical)., Fetch ERA5 actuals for a city over all needed dates at once. (+5 more)

### Community 16 - "Polymarket Market Data"
Cohesion: 0.19
Nodes (13): fetch_temperature_markets(), get_clob_mid(), get_market_mid(), _parse_bucket(), parse_clob_tokens(), parse_question(), Polymarket Gamma API + CLOB API fetchers. Parses temperature bucket markets and, Parse the temperature bucket portion of a question string. (+5 more)

### Community 17 - "CLOB Position Queries"
Cohesion: 0.20
Nodes (12): get_clob_positions(), get_polymarket_closed_positions(), get_proxy_address(), Fetch all current on-chain positions via Polymarket Gamma API.     Returns list, Polymarket proxy / funder wallet (same as UI portfolio address)., Pull actual on-chain positions from Polymarket data API and reconcile with DB., Closed positions with realized PnL — matches Polymarket portfolio history., sync_positions_to_db() (+4 more)

### Community 18 - "Signal Consistency"
Cohesion: 0.23
Nodes (11): _buckets_are_adjacent(), check_cumulative_consistency(), check_partition_consistency(), _hi(), _lo(), Cross-market consistency checker for temperature markets.  For each (city, targe, Check cumulative (≥X or <X) vs range bucket consistency.      For any pair of ra, Return True if bucket b starts exactly where bucket a ends (no gap, no overlap). (+3 more)

### Community 19 - "Forecast Bias Correction"
Cohesion: 0.22
Nodes (10): apply_bias(), _apply_city_bias(), get_corrected_ensemble_at_date(), get_persistence_bias(), Per-station, per-model, per-calendar-month bias corrector.  bias = mean(actual_h, Compute short-term persistence bias: mean(actual - predicted) over last 7 days., Apply stored bias correction to a model forecast.     Blends:       - Seasonal m, Apply per-city additive bias from CITY_FORECAST_BIAS_C (config) if present. (+2 more)

### Community 20 - "Market Price Scraper"
Cohesion: 0.29
Nodes (9): _collect_markets(), _fetch_and_store_one(), CLOB price history scraper.  Fetches hourly price snapshots for all resolved + a, Fetch full hourly CLOB price history for one token and store it.     Returns num, Fetch and store hourly CLOB price history for all resolved + active temp markets, GET with exponential backoff on 429/5xx., Collect token_id + market_id for all temp markets:     - Resolved (closed=true,, _req() (+1 more)

### Community 21 - "Position Query & Sell"
Cohesion: 0.20
Nodes (10): sell_position, get_actual_high_c, _query_polymarket_outcome, Two-Step Resolution Strategy (PM outcome + temp for bias), resolve_expired_trades, get_weather_fallback_trades, resolve_trade, resolve_tsa_prediction (+2 more)

### Community 22 - "Crypto Market Data"
Cohesion: 0.27
Nodes (9): fetch_crypto_markets(), get_crypto_market_prices(), _is_crypto_updown(), _parse_asset(), Polymarket crypto Up/Down market fetcher and parser.  Fetches active hourly "Bit, Get live CLOB prices for a crypto market., Fetch active crypto Up/Down markets from Polymarket Gamma API.      Only returns, cmd_scan_crypto() (+1 more)

### Community 23 - "TSA Market Integration"
Cohesion: 0.24
Nodes (9): fetch_tsa_markets(), get_tsa_market_prices(), _parse_tsa_bucket(), parse_tsa_question(), Polymarket TSA passenger market fetcher and parser.  Fetches active "How many TS, Extract passenger count bucket from a question string.      Handles raw counts a, Fetch active TSA passenger count markets from Polymarket Gamma API.      Uses th, Get live CLOB prices for a TSA market. Same interface as get_market_prices(). (+1 more)

### Community 24 - "Real Backtest Processing"
Cohesion: 0.22
Nodes (9): _crowd_model_price(), process_market(), Run the full signal pipeline for one resolved market.     Returns a result row d, Fallback market price: Gaussian crowd using ensemble mean + MARKET_SHRINK.     U, compute_ensemble_stats(), Dynamic Lead-Time Uncertainty Scaling, King Models Conflict Detection (ECMWF vs GFS), Kish Effective Sample Size Correction (+1 more)

### Community 25 - "Paper Broker Internals"
Cohesion: 0.22
Nodes (9): execute_paper_trade, Order Book Depth Check Design, Correlated NO Bet Discount Design, adjust_bankroll, Atomic Trade Open Design (stake deducted at entry), get_bankroll, get_recent_prices, open_trade_atomic (+1 more)

### Community 26 - "Forecast DB Queries"
Cohesion: 0.28
Nodes (9): get_forecasts_for_date, record_price, record_tsa_prediction, upsert_market, cmd_scan, cmd_scan_crypto, cmd_scan_tsa, Opportunistic Scan Guards Design (+1 more)

### Community 27 - "Event & KV Store"
Cohesion: 0.22
Nodes (9): log_event, set_kv, _acquire_scan_lock, _signal_health_policy, acquire_job_lock, mark_job_end, mark_job_start, release_job_lock (+1 more)

### Community 28 - "Signal Ensemble Weights"
Cohesion: 0.25
Nodes (7): Multi-model ensemble disagreement scorer.  Takes the bias-corrected model predic, get_freshness_weights(), _last_available(), NWP Model Freshness Decay, Model freshness weighting.  NWP models are initialized at fixed UTC cycle times, Return the UTC datetime of the model's most recently available cycle., Return a freshness multiplier in (0, 1] for each known model.      Call once per

### Community 29 - "Live CLOB Trade Execution"
Cohesion: 0.25
Nodes (8): execute_live_trade, get_clob_balance, redeem_positions, sync_positions_to_db, set_bankroll, Capital Recycle After Resolve Design, cmd_resolve, cmd_sync_positions

### Community 30 - "Live Position Retrieval"
Cohesion: 0.25
Nodes (8): get_clob_positions, get_polymarket_closed_positions, get_polymarket_positions_value_usd, get_kv, set_mode, get_ops_snapshot, should_run_daily_reconcile, _build_polymarket_live_dashboard

### Community 31 - "Correlation Risk Filter"
Cohesion: 0.32
Nodes (7): correlation_allows_trade(), get_city_bucket_count(), get_open_exposure_by_region(), Cross-city correlation filter.  Weather systems move — a cold front hitting Lond, Check whether adding a new trade for `city` on `target_date` is allowed.      Tw, Count unique cities with open trades per weather region for a given target date., Count open bucket trades for a specific city that overlap target_date.     If di

### Community 32 - "Deribit Options Data"
Cohesion: 0.32
Nodes (7): get_atm_iv(), get_crypto_signal_inputs(), get_index_price(), Deribit market data — BTC/ETH index price and implied volatility.  Used as the s, Return current Deribit index price for 'btc_usd' or 'eth_usd'., Return annualised implied volatility interpolated near spot for the given     ex, Return everything the edge calculator needs for one crypto asset.      symbol: '

### Community 33 - "Neighbor Temperature Validation"
Cohesion: 0.29
Nodes (7): clear_session_cache(), _fetch_reference_temp(), get_neighbor_penalty(), Neighbor validation — cross-station sanity filter.  For each city that has a NEI, Clear the in-session cache. The cache clears naturally between process runs., Fetch the GFS daily max temperature at the reference coordinate for city.     Re, Returns (size_multiplier, reason_str).      multiplier = 1.0  — no neighbor ref

### Community 34 - "Daemon Job Scheduler"
Cohesion: 0.38
Nodes (6): _build_schedule(), _nowcast_utc_times(), Polymarket Bot Daemon Sleeps until the next relevant event, then fires the appro, Return all nowcast fire times in UTC for a given date., Build a sorted list of (fire_time_utc, command_flag, label) for today + tomorrow, _run()

### Community 35 - "Forecast Pruning & Storage"
Cohesion: 0.29
Nodes (7): insert_forecast, insert_forecast_if_missing, prune_old_forecasts, upsert_climatology, upsert_historical_obs, upsert_station, cmd_backfill

### Community 36 - "Confidence Tier System"
Cohesion: 0.33
Nodes (5): apply_tier_to_signal(), classify_confidence(), Confidence tiering — size your bets by how certain the signal is.  Four tiers, e, Apply confidence tiering to a signal dict in-place.     Scales size_usdc by the, Four-Tier Confidence Tiering Scheme

### Community 37 - "Crypto Edge Calculator"
Cohesion: 0.33
Nodes (6): Black-Scholes N(d2) Risk-Neutral Probability, compute_crypto_edge(), crypto_updown_prob(), Crypto Up/Down market edge calculator.  Signal: N(d2) from Black-Scholes — the r, P(asset > reference at expiry) under Black-Scholes with zero drift.      spot:, Compute edge signal for one crypto Up/Down market.      market:               di

### Community 38 - "Model Config Settings"
Cohesion: 0.33
Nodes (6): HRRR Coverage Bounds (CONUS only), NEIGHBOR_REFS, OPENMETEO_MODELS, _fetch_reference_temp, get_neighbor_penalty, Neighbor Grid Artifact Detection Design

### Community 39 - "Temperature Unit Utils"
Cohesion: 0.50
Nodes (3): c_to_f(), Shared utility functions., Convert Celsius to Fahrenheit.

### Community 40 - "Correlation City Filter"
Cohesion: 0.50
Nodes (4): CITY_REGION map, correlation_allows_trade, get_open_exposure_by_region, Geographic Correlation Filter Region Design

### Community 41 - "Web UI Loading & Refresh"
Cohesion: 0.50
Nodes (4): load, refreshClobBalance, renderHero, runCmd

### Community 43 - "Daemon Schedule Builder"
Cohesion: 0.67
Nodes (3): _build_schedule, MODEL_RUN_EVENTS schedule, daemon run

## Ambiguous Edges - Review These
- `get_historical_high()` → `Query: Explain PnL`  [AMBIGUOUS]
  graphify-out/memory/query_20260523_132645_explain_pnl.md · relation: conceptually_related_to

## Knowledge Gaps
- **76 isolated node(s):** `allow`, `_trades`, `q`, `python-dotenv`, `numpy` (+71 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **42 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `get_historical_high()` and `Query: Explain PnL`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `cmd_scan` connect `Forecast DB Queries` to `Terminal Dashboard`, `NOAA Weather Fetching`, `Forecast Pruning & Storage`, `Model Config Settings`, `Backtesting Engine`, `Correlation City Filter`, `Paper Broker Internals`, `Event & KV Store`, `Live CLOB Trade Execution`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `get_running_max_c()` connect `NOAA Weather Fetching` to `Polymarket Position Manager`, `Forecast DB Queries`, `Portfolio Resolution`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `cmd_scan()` connect `Portfolio Resolution` to `Terminal Dashboard`, `Neighbor Temperature Validation`, `NOAA Weather Fetching`, `Confidence Tier System`, `Climatology Data`, `Live Broker Execution`, `Backtest Runner`, `Paper Trading Broker`, `Polymarket Market Data`, `Forecast Bias Correction`, `Real Backtest Processing`, `Correlation Risk Filter`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `compute_edge()` (e.g. with `compute_tsa_edge()` and `compute_crypto_edge()`) actually correct?**
  _`compute_edge()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `SQLite schema and all database operations. All reads/writes go through this modu`, `Switch between 'paper' and 'live' databases. Call before any DB operations.`, `Return current mode: 'live' or 'paper'.` to the rest of the system?**
  _306 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Terminal Dashboard` be split into smaller, more focused modules?**
  _Cohesion score 0.05706760316066725 - nodes in this community are weakly interconnected._