#!/usr/bin/env python3
"""
Backtest: replay 30 days of real day-ahead signals to validate edge quality.

Methodology
-----------
For each city × each date in the last 30 days:
  1. Fetch what GFS and ECMWF actually predicted 1 day ahead (real archives
     via Open-Meteo past_days parameter — NOT ERA5 reanalysis).
  2. Apply stored bias corrections via get_corrected_ensemble().
  3. Generate 10 realistic 1-unit buckets centred on the FORECAST mean
     (not the actual — we simulate not knowing the answer).
  4. For each bucket call compute_edge() with a simulated mid of 0.50
     (worst-case assumption: market is perfectly priced at 50/50 for all).
  5. Fetch ERA5 actuals as ground truth to evaluate each signal.
  6. Record win/loss and Kelly-sized PnL.

This is a valid out-of-sample test because:
  - The forecasts were made before the actual was known
  - Bias corrections are trained on older data (pre-backtest period)
  - We use a conservative mid=0.50 (real market prices would be sharper)

Run: python3 backtest.py
"""
import csv
import logging
import math
import os
import sys
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(__file__))

import db
from config import CITIES, OPENMETEO_MODELS, MIN_EDGE, MAX_TRADE_USDC, BASE_FORECAST_STD_C, KELLY_FRACTION
from data.openmeteo import fetch_historical_actuals
from signals.bias_corrector import get_corrected_ensemble, station_is_ready
from signals.edge_calculator import bucket_bounds_to_celsius, model_prob_for_bucket
from signals.ensemble import compute_ensemble_stats
import requests

db.init_db()

BACKTEST_DAYS   = 30
SIMULATED_MID   = 0.50
MODELS_TO_USE   = ["gfs", "ecmwf", "icon", "gem", "meteofrance"]
MAX_WORKERS     = 20
OUTPUT_CSV      = "backtest_results.csv"


def _c_to_f(c): return c * 9 / 5 + 32
from utils import f_to_c as _f_to_c


def fetch_day_ahead_forecast(model_name: str, lat: float, lon: float,
                              target_date: str, timezone: str) -> float | None:
    """Fetch what a model actually predicted for target_date issued 1 day ahead."""
    tgt      = date.fromisoformat(target_date)
    days_ago = (date.today() - tgt).days
    if days_ago < 1:
        return None
    try:
        resp = requests.get(OPENMETEO_MODELS[model_name], params={
            "latitude": lat, "longitude": lon,
            "daily": "temperature_2m_max",
            "temperature_unit": "celsius",
            "forecast_days": 1,
            "past_days": days_ago + 1,
            "timezone": timezone,
        }, timeout=12)
        resp.raise_for_status()
        data  = resp.json()
        times = data.get("daily", {}).get("time", [])
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if target_date in times:
            val = temps[times.index(target_date)]
            return float(val) if val is not None else None
    except Exception:
        pass
    return None


def kelly_size(model_prob: float, mid: float, bankroll: float = 1000.0) -> float:
    if model_prob > mid:
        entry, p = mid, model_prob
    else:
        entry, p = 1.0 - mid, 1.0 - model_prob
    if entry <= 0.001 or entry >= 0.999:
        return 0.0
    b = (1.0 / entry) - 1.0
    q = 1.0 - p
    f = max(0.0, (b * p - q) / b)
    return round(min(f * KELLY_FRACTION * bankroll, MAX_TRADE_USDC), 2)


def generate_buckets(forecast_mean_c: float, uses_fahrenheit: bool) -> list[dict]:
    """10 consecutive 1-unit buckets centred on the FORECAST mean (not actual)."""
    if uses_fahrenheit:
        centre_f = round(_c_to_f(forecast_mean_c))
        lo_f = centre_f - 5
        return [{"bucket_lo": float(lo_f + i), "bucket_hi": float(lo_f + i + 1),
                 "bucket_unit": "F"} for i in range(10)]
    else:
        centre_c = round(forecast_mean_c)
        lo_c = centre_c - 5
        return [{"bucket_lo": float(lo_c + i), "bucket_hi": float(lo_c + i + 1),
                 "bucket_unit": "C"} for i in range(10)]


def main():
    today      = date.today()
    start_date = (today - timedelta(days=BACKTEST_DAYS)).isoformat()
    end_date   = (today - timedelta(days=1)).isoformat()

    print(f"\nBacktest — last {BACKTEST_DAYS} days — real GFS+ECMWF day-ahead forecasts\n")
    print("Fetching ERA5 actuals and model forecasts in parallel...")

    # ── Step 1: fetch all ERA5 actuals ────────────────────────────────────────
    actuals_cache: dict[str, dict] = {}
    for city, cfg in CITIES.items():
        try:
            actuals_cache[city] = fetch_historical_actuals(
                cfg["lat"], cfg["lon"], start_date, end_date, cfg["timezone"]
            )
        except Exception as e:
            print(f"  ERA5 failed {city}: {e}")
            actuals_cache[city] = {}

    # ── Step 2: fetch all real day-ahead forecasts in parallel ────────────────
    fetch_tasks = []
    for city, cfg in CITIES.items():
        for days_back in range(2, BACKTEST_DAYS + 1):
            td = (today - timedelta(days=days_back)).isoformat()
            if td not in actuals_cache.get(city, {}):
                continue
            for model in MODELS_TO_USE:
                fetch_tasks.append((city, td, model, cfg))

    forecasts_cache: dict[tuple, float] = {}   # (city, date, model) -> predicted_c
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetch_day_ahead_forecast,
                        model, cfg["lat"], cfg["lon"], td, cfg["timezone"]
                        ): (city, td, model)
            for (city, td, model, cfg) in fetch_tasks
        }
        done = 0
        for fut in as_completed(futures):
            key = futures[fut]
            val = fut.result()
            if val is not None:
                forecasts_cache[key] = val
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(fetch_tasks)} forecast fetches done...", flush=True)

    # ── Step 3: run signal pipeline city × date × bucket ─────────────────────
    all_rows = []
    city_stats: dict[str, dict] = {}
    running_bankroll = 1000.0

    for city, cfg in CITIES.items():
        icao   = cfg["icao"]
        use_f  = cfg["uses_fahrenheit"]
        actuals = actuals_cache.get(city, {})
        stats  = {"n": 0, "correct": 0, "kelly_pnl": 0.0, "no_signal": 0,
                  "no_forecast": 0}

        for days_back in range(2, BACKTEST_DAYS + 1):
            td     = (today - timedelta(days=days_back)).isoformat()
            actual = actuals.get(td)
            if actual is None:
                continue

            # Collect real model predictions for this city/date
            raw = {m: forecasts_cache[(city, td, m)]
                   for m in MODELS_TO_USE if (city, td, m) in forecasts_cache}
            if len(raw) < 1:
                stats["no_forecast"] += 1
                continue

            # Fill missing models with mean of available (conservative)
            mean_raw = sum(raw.values()) / len(raw)
            full_raw = {m: raw.get(m, mean_raw) for m in MODELS_TO_USE}

            # Apply bias corrections
            corrected = get_corrected_ensemble(icao, full_raw, td)
            if not corrected:
                stats["no_forecast"] += 1
                continue

            try:
                ensemble = compute_ensemble_stats(corrected)
            except ValueError:
                continue

            forecast_mean_c = ensemble["mean_c"]
            effective_std   = ensemble["effective_std"]

            # Generate buckets centred on FORECAST mean (not actual)
            buckets = generate_buckets(forecast_mean_c, use_f)

            for bkt in buckets:
                lo_c, hi_c = bucket_bounds_to_celsius(
                    bkt["bucket_lo"], bkt["bucket_hi"], bkt["bucket_unit"]
                )

                model_prob = model_prob_for_bucket(forecast_mean_c, effective_std, lo_c, hi_c)
                edge       = model_prob - SIMULATED_MID

                if abs(edge) < MIN_EDGE:
                    stats["no_signal"] += 1
                    continue

                direction = "YES" if edge > 0 else "NO"

                # Ground truth: did the bucket resolve YES?
                lo_v = lo_c if lo_c is not None else -math.inf
                hi_v = hi_c if hi_c is not None else math.inf
                outcome_yes = int(lo_v <= actual <= hi_v)

                correct = int(
                    (direction == "YES" and outcome_yes == 1) or
                    (direction == "NO"  and outcome_yes == 0)
                )

                size = kelly_size(model_prob, SIMULATED_MID, running_bankroll)
                if direction == "YES":
                    kelly_pnl = size * (1.0 / SIMULATED_MID - 1) if correct else -size
                else:
                    kelly_pnl = size * (1.0 / (1 - SIMULATED_MID) - 1) if correct else -size
                # Update running bankroll (cap minimum at $1 to avoid degenerate sizing)
                running_bankroll = max(1.0, running_bankroll + kelly_pnl)

                stats["n"]         += 1
                stats["correct"]   += correct
                stats["kelly_pnl"] += kelly_pnl

                all_rows.append({
                    "date":          td,
                    "city":          city,
                    "bucket_lo":     bkt["bucket_lo"],
                    "bucket_hi":     bkt["bucket_hi"],
                    "bucket_unit":   bkt["bucket_unit"],
                    "direction":     direction,
                    "model_prob":    round(model_prob, 4),
                    "market_prob":   SIMULATED_MID,
                    "edge":          round(edge, 4),
                    "forecast_mean": round(forecast_mean_c, 2),
                    "actual_c":      round(actual, 2),
                    "outcome_yes":   outcome_yes,
                    "correct":       correct,
                    "kelly_size":    size,
                    "kelly_pnl":     round(kelly_pnl, 2),
                    "n_models":      len(raw),
                })

        city_stats[city] = stats

    # ── Step 4: print summary ─────────────────────────────────────────────────
    print(f"\n{'City':<16} {'N':>5} {'Win%':>7} {'Kelly PnL':>11} {'No sig':>7} {'No fc':>6}")
    print("─" * 58)
    total_n = total_c = 0
    total_pnl = 0.0
    for city, s in sorted(city_stats.items(), key=lambda x: -x[1]["kelly_pnl"]):
        n   = s["n"]
        wr  = s["correct"] / n * 100 if n else 0
        print(f"{city:<16} {n:>5} {wr:>6.1f}%  ${s['kelly_pnl']:>9.2f}"
              f"  {s['no_signal']:>6}  {s['no_forecast']:>5}")
        total_n   += n
        total_c   += s["correct"]
        total_pnl += s["kelly_pnl"]

    print("─" * 58)
    overall_wr = total_c / total_n * 100 if total_n else 0
    print(f"{'TOTAL':<16} {total_n:>5} {overall_wr:>6.1f}%  ${total_pnl:>9.2f}")
    print(f"\nTotal signals: {total_n}  |  Win rate: {overall_wr:.1f}%  |  "
          f"Kelly PnL (vs $1000 bank): ${total_pnl:.2f}")

    if total_n > 0:
        edge_vals = [abs(float(r["edge"])) for r in all_rows]
        print(f"Mean |edge|: {sum(edge_vals)/len(edge_vals):.3f}  |  "
              f"Median: {sorted(edge_vals)[len(edge_vals)//2]:.3f}")

    # ── Step 5: save CSV ──────────────────────────────────────────────────────
    if all_rows:
        with open(OUTPUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nSaved {len(all_rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
