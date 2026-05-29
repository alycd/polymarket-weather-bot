#!/usr/bin/env python3
"""
Calibrate BASE_FORECAST_STD_C from real day-ahead forecast errors.

Uses Open-Meteo's past_days parameter to fetch what GFS and ECMWF
actually predicted 1 day ahead for each city over the last 30 days,
then computes RMS error against ERA5 actuals.

Run: python3 scripts/calibrate_forecast_std.py
"""
import sys
import re
import math
import logging
import requests
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, ".")
from config_active import CITIES, OPENMETEO_MODELS
from data.openmeteo import fetch_historical_actuals

logging.basicConfig(level=logging.WARNING)

LOOKBACK_DAYS   = 30
MODELS_TO_USE   = ["gfs", "ecmwf"]
MAX_WORKERS     = 20


def fetch_day_ahead_forecast(model_name: str, lat: float, lon: float,
                              target_date_str: str, timezone: str) -> float | None:
    target    = date.fromisoformat(target_date_str)
    days_ago  = (date.today() - target).days
    if days_ago < 1:
        return None
    model_url = OPENMETEO_MODELS[model_name]
    try:
        resp = requests.get(model_url, params={
            "latitude":         lat,
            "longitude":        lon,
            "daily":            "temperature_2m_max",
            "temperature_unit": "celsius",
            "forecast_days":    1,
            "past_days":        days_ago + 1,
            "timezone":         timezone,
        }, timeout=12)
        resp.raise_for_status()
        data  = resp.json()
        times = data.get("daily", {}).get("time", [])
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if target_date_str in times:
            val = temps[times.index(target_date_str)]
            return float(val) if val is not None else None
    except Exception:
        pass
    return None


def main():
    today      = date.today()
    start_date = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end_date   = (today - timedelta(days=1)).isoformat()

    print(f"\nCalibrating BASE_FORECAST_STD_C — last {LOOKBACK_DAYS} days, "
          f"models: {MODELS_TO_USE}\n")

    # Build all (city, date, model) fetch tasks
    tasks = []
    actuals_cache: dict[str, dict] = {}

    print("Fetching ERA5 actuals for all cities...")
    for city, cfg in CITIES.items():
        try:
            actuals = fetch_historical_actuals(
                cfg["lat"], cfg["lon"], start_date, end_date, cfg["timezone"]
            )
            actuals_cache[city] = actuals
            for days_back in range(2, LOOKBACK_DAYS + 1):
                td = (today - timedelta(days=days_back)).isoformat()
                if td in actuals:
                    for m in MODELS_TO_USE:
                        tasks.append((city, td, m, cfg))
        except Exception as e:
            print(f"  ERA5 failed for {city}: {e}")

    print(f"Fetching {len(tasks)} day-ahead forecasts in parallel...")

    results: dict[tuple, float] = {}   # (city, date, model) -> predicted_c
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetch_day_ahead_forecast,
                        model, cfg["lat"], cfg["lon"], td, cfg["timezone"]): (city, td, model)
            for (city, td, model, cfg) in tasks
        }
        done = 0
        for fut in as_completed(futures):
            key = futures[fut]
            val = fut.result()
            if val is not None:
                results[key] = val
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(tasks)} fetched...", flush=True)

    # Compute errors per city
    all_errors: list[float] = []
    print(f"\n{'City':<16} {'N':>5} {'RMS':>8} {'Mean':>8} {'Max':>8}")
    print("─" * 50)

    for city, cfg in CITIES.items():
        actuals = actuals_cache.get(city, {})
        errors  = []
        for days_back in range(2, LOOKBACK_DAYS + 1):
            td     = (today - timedelta(days=days_back)).isoformat()
            actual = actuals.get(td)
            if actual is None:
                continue
            preds  = [results[(city, td, m)] for m in MODELS_TO_USE
                      if (city, td, m) in results]
            if preds:
                mean_pred = sum(preds) / len(preds)
                errors.append(abs(mean_pred - actual))

        if errors:
            rms  = math.sqrt(sum(e**2 for e in errors) / len(errors))
            mean = sum(errors) / len(errors)
            mx   = max(errors)
            all_errors.extend(errors)
            print(f"{city:<16} {len(errors):>5} {rms:>7.2f}°C {mean:>7.2f}°C {mx:>7.2f}°C")
        else:
            print(f"{city:<16}   no data")

    if not all_errors:
        print("\nNo data — cannot calibrate.")
        return

    global_rms = math.sqrt(sum(e**2 for e in all_errors) / len(all_errors))
    print("─" * 50)
    print(f"{'GLOBAL':<16} {len(all_errors):>5} {global_rms:>7.2f}°C")

    with open("config.py") as f:
        config_text = f.read()
    current_match = re.search(r"BASE_FORECAST_STD_C\s*=\s*([\d.]+)", config_text)
    current_val   = float(current_match.group(1)) if current_match else 1.5

    recommended   = round(global_rms * 1.1, 2)
    print(f"\nCurrent  BASE_FORECAST_STD_C = {current_val}°C")
    print(f"Measured RMS forecast error   = {global_rms:.2f}°C")
    print(f"Recommended (RMS × 1.1)       = {recommended}°C")

    if abs(recommended - current_val) < 0.1:
        print("\nAlready well-calibrated. No update needed.")
        return

    answer = input(f"\nUpdate config.py {current_val} → {recommended}? [y/N] ").strip().lower()
    if answer == "y":
        new_text = re.sub(
            r"(BASE_FORECAST_STD_C\s*=\s*)[\d.]+",
            f"\\g<1>{recommended}",
            config_text,
        )
        with open("config.py", "w") as f:
            f.write(new_text)
        print(f"Updated: BASE_FORECAST_STD_C = {recommended}°C")
    else:
        print("No changes made.")


if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
