# Backtest Runner

> 17 nodes · cohesion 0.17

## Key Concepts

- **backtest.py** (12 connections) — `backtest.py`
- **get_corrected_ensemble()** (10 connections) — `signals/bias_corrector.py`
- **model_prob_for_bucket()** (10 connections) — `signals/edge_calculator.py`
- **main()** (8 connections) — `backtest.py`
- **bucket_bounds_to_celsius()** (8 connections) — `signals/edge_calculator.py`
- **f_to_c()** (7 connections) — `utils.py`
- **generate_buckets()** (4 connections) — `backtest.py`
- **_c_to_f()** (2 connections) — `backtest.py`
- **fetch_day_ahead_forecast()** (2 connections) — `backtest.py`
- **kelly_size()** (2 connections) — `backtest.py`
- **Fetch what a model actually predicted for target_date issued 1 day ahead.** (1 connections) — `backtest.py`
- **10 consecutive 1-unit buckets centred on the FORECAST mean (not actual).** (1 connections) — `backtest.py`
- **Convert Fahrenheit to Celsius.** (1 connections) — `utils.py`
- **Apply bias correction to all model forecasts.     Returns {model_name: corrected** (1 connections) — `signals/bias_corrector.py`
- **Convert bucket bounds to °C. None = unbounded.** (1 connections) — `signals/edge_calculator.py`
- **P(temp in [lo_c, hi_c]) under t(df=FORECAST_T_DF, mean, eff_std).      Student's** (1 connections) — `signals/edge_calculator.py`
- **Student-t Heavy Tails for Extreme Buckets** (1 connections) — `signals/edge_calculator.py`

## Relationships

- [[NOAA Weather Fetching]] (7 shared connections)
- [[Forecast Bias Correction]] (5 shared connections)
- [[Real Backtest Processing]] (4 shared connections)
- [[Real Historical Backtest]] (4 shared connections)
- [[Climatology Data]] (2 shared connections)
- [[Portfolio Resolution]] (2 shared connections)
- [[Temperature Unit Utils]] (1 shared connections)
- [[TSA Passenger Forecasting]] (1 shared connections)

## Source Files

- `backtest.py`
- `signals/bias_corrector.py`
- `signals/edge_calculator.py`
- `utils.py`

## Audit Trail

- EXTRACTED: 70 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*