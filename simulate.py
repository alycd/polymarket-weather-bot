"""
Monte Carlo temperature market simulator.

Injects realistic NWP forecast errors to simulate real-world trading conditions,
without relying on the live DB, API calls to nowcasters, or ERA5-as-forecast
(the "perfect information" trap in backtest.py).

Usage:
    python simulate.py [--seed 42] [--trials 500] [--cities 3]
"""
import argparse
import math
import os
import random
import sys
import time
from datetime import date, timedelta
from typing import Optional

import requests
from scipy.stats import norm

# ── Config import ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
import config_active as cfg

# ── Simulation parameters ──────────────────────────────────────────────────────
N_TRIALS = 500          # Monte Carlo trials per (city, date)
LOOKBACK_DAYS = 30      # ERA5 actuals window
ERA5_LAG = 2            # ERA5 has ~2-day publication lag

# Realistic NWP error parameters (bias + std in °C, day-1 lead time)
# Source: NWP skill assessments (e.g., Haiden et al. 2021, ECMWF tech notes)
MODEL_ERRORS = {
    "gfs":         {"bias": +0.8, "std": 2.2},   # GFS warm bias, day-1 RMSE ~2.2°C
    "ecmwf":       {"bias": -0.3, "std": 1.8},   # ECMWF best overall
    "icon":        {"bias": +0.4, "std": 2.0},
    "gem":         {"bias": -0.5, "std": 2.1},
    "meteofrance": {"bias": +0.2, "std": 2.0},
}

# Model weights (mirrors signals/ensemble.py)
MODEL_WEIGHTS = {
    "ecmwf":       1.8,
    "icon":        1.3,
    "gfs":         1.0,
    "gem":         1.0,
    "meteofrance": 1.0,
}

# Market price model: crowd uses ~GFS-equivalent single forecast
# crowd_prob = P(bucket | GFS-based forecast) using Gaussian with std=2.5
# market_mid = 0.5 + MARKET_SHRINK * (crowd_prob - 0.5)
# MARKET_SHRINK < 1.0 means market is partially informed (not fully efficient)
MARKET_SHRINK = 0.30
CROWD_FORECAST_STD = 2.5   # Market crowd's effective forecast uncertainty

# ── Bucket generation ──────────────────────────────────────────────────────────
BUCKET_WIDTH_C = 1.0    # 1-degree Celsius buckets
N_BUCKETS = 10          # number of buckets centred on ensemble mean


def generate_buckets(ensemble_mean_c: float) -> list[dict]:
    """
    Generate N_BUCKETS 1°C-wide buckets centred around ensemble_mean_c.
    Returns list of dicts with bucket_lo, bucket_hi (°C), bucket_unit='C'.
    Edge buckets at extremes are open-ended.
    """
    centre = math.floor(ensemble_mean_c)
    half = N_BUCKETS // 2
    buckets = []
    for i in range(-half, half):
        lo = centre + i * BUCKET_WIDTH_C
        hi = lo + BUCKET_WIDTH_C
        buckets.append({
            "bucket_lo":   lo,
            "bucket_hi":   hi,
            "bucket_unit": "C",
            "market_type": "daily",
            "target_date": "",   # filled in by caller
        })
    return buckets


# ── Ensemble stats (mirrors signals/ensemble.py) ───────────────────────────────
def compute_ensemble_stats_sim(corrected_forecasts: dict[str, float],
                                base_std: float) -> dict:
    """Weighted ensemble stats without DB dependency."""
    names  = list(corrected_forecasts.keys())
    values = [corrected_forecasts[m] for m in names]
    weights = [MODEL_WEIGHTS.get(m, 1.0) for m in names]

    total_w = sum(weights)
    mean = sum(w * v for w, v in zip(weights, values)) / total_w

    n = len(values)
    if n > 1:
        sum_w2 = sum(w ** 2 for w in weights)
        effective_n = total_w ** 2 / sum_w2
        denom = total_w * (1.0 - 1.0 / effective_n) if effective_n > 1 else total_w
        variance = sum(w * (v - mean) ** 2 for w, v in zip(weights, values)) / denom
        std = math.sqrt(variance)
    else:
        std = 0.0

    effective_std = math.sqrt(std ** 2 + base_std ** 2)

    if std > cfg.ENSEMBLE_STD_MAX:
        score = "chaotic"
    elif std < cfg.ENSEMBLE_STD_MIN:
        score = "agree"
    else:
        score = "sweet_spot"

    tradeable = score != "chaotic"

    return {
        "mean_c":        mean,
        "std_c":         std,
        "effective_std": effective_std,
        "score":         score,
        "tradeable":     tradeable,
    }


# ── Probability helpers ────────────────────────────────────────────────────────
def prob_in_bucket(mean_c: float, std_c: float,
                   lo: Optional[float], hi: Optional[float]) -> float:
    """P(temp in [lo, hi]) under N(mean, std). None = unbounded."""
    lo_v = lo if lo is not None else -math.inf
    hi_v = hi if hi is not None else math.inf
    p = norm.cdf(hi_v, mean_c, std_c) - norm.cdf(lo_v, mean_c, std_c)
    return float(max(0.0, min(1.0, p)))


def market_implied_prob(actual_c: float, bucket: dict,
                        rng: random.Random) -> float:
    """
    Simulate the market-implied probability for a bucket.

    The 'crowd' uses a GFS-like single forecast with realistic error.
    crowd_forecast = actual_c + gauss(gfs_bias, gfs_std)
    crowd_prob = P(bucket | crowd_forecast, std=CROWD_FORECAST_STD)
    market_mid = 0.5 + MARKET_SHRINK * (crowd_prob - 0.5)   # partial info
    """
    gfs_err = cfg_model_errors["gfs"]
    crowd_fc = actual_c + rng.gauss(gfs_err["bias"], gfs_err["std"])
    crowd_prob = prob_in_bucket(crowd_fc, CROWD_FORECAST_STD,
                                bucket["bucket_lo"], bucket["bucket_hi"])
    mid = 0.5 + MARKET_SHRINK * (crowd_prob - 0.5)
    return float(max(0.01, min(0.99, mid)))


def bucket_resolved_yes(actual_c: float, bucket: dict) -> bool:
    """Did the actual temperature fall in this bucket?"""
    lo = bucket["bucket_lo"]
    hi = bucket["bucket_hi"]
    if lo is None and hi is None:
        return True
    if lo is None:
        return actual_c < hi
    if hi is None:
        return actual_c >= lo
    return lo <= actual_c < hi


# ── PnL computation ────────────────────────────────────────────────────────────
def compute_pnl(direction: str, entry_price: float, size_usdc: float,
                resolved_yes: bool) -> float:
    """
    Binary option PnL.
    YES bet: stake size_usdc at entry_price. Win: +size_usdc*(1/entry_price - 1), Lose: -size_usdc
    NO bet: stake size_usdc at (1-entry_price). Win: +size_usdc*(1/(1-entry_price)-1), Lose: -size_usdc
    """
    if direction == "YES":
        if resolved_yes:
            return size_usdc * (1.0 / entry_price - 1.0)
        else:
            return -size_usdc
    else:  # NO
        no_price = 1.0 - entry_price
        if not resolved_yes:
            return size_usdc * (1.0 / no_price - 1.0)
        else:
            return -size_usdc


# ── Kelly sizing ───────────────────────────────────────────────────────────────
def kelly_size(model_prob: float, market_prob: float,
               bankroll: float, kelly_fraction: float,
               max_trade: float) -> tuple[float, float]:
    """Returns (kelly_f, size_usdc)."""
    if model_prob > market_prob:
        entry = market_prob
        p = model_prob
    else:
        entry = 1.0 - market_prob
        p = 1.0 - model_prob

    if entry <= 0.001 or entry >= 0.999:
        return 0.0, 0.0
    b = (1.0 / entry) - 1.0
    if b <= 0:
        return 0.0, 0.0
    q = 1.0 - p
    f_full = max(0.0, (b * p - q) / b)
    f = min(f_full * kelly_fraction, 1.0)
    size = min(f * bankroll, max_trade)
    return f, size


# ── ERA5 fetch ─────────────────────────────────────────────────────────────────
def fetch_era5_actuals(lat: float, lon: float, start_date: str,
                       end_date: str, timezone: str) -> dict[str, float]:
    """Fetch ERA5 daily max temps from Open-Meteo Archive."""
    url = cfg.OPENMETEO_ARCHIVE_URL
    params = {
        "latitude":         lat,
        "longitude":        lon,
        "start_date":       start_date,
        "end_date":         end_date,
        "daily":            "temperature_2m_max",
        "temperature_unit": "celsius",
        "timezone":         timezone,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    times = data.get("daily", {}).get("time", [])
    temps = data.get("daily", {}).get("temperature_2m_max", [])
    result = {}
    for t, v in zip(times, temps):
        if v is not None:
            result[t] = float(v)
    return result


# ── Core simulation for one (city, date, trial) ────────────────────────────────
def simulate_one_trial(actual_c: float, date_str: str,
                       rng: random.Random,
                       base_std: float,
                       min_edge: float,
                       kelly_fraction: float,
                       max_trade: float,
                       bankroll: float) -> list[dict]:
    """
    One Monte Carlo trial for a single day.
    Returns list of signal records (may be empty if no tradeable signals).
    """
    # 1. Inject per-model forecast errors
    raw_forecasts = {}
    for model, err in cfg_model_errors.items():
        noise = rng.gauss(err["bias"], err["std"])
        raw_forecasts[model] = actual_c + noise

    # 2. No DB bias correction available in simulation — use raw forecasts
    #    (in practice the bias corrector would remove systematic bias; here we
    #    simulate corrected forecasts by removing the known model bias, which is
    #    what a well-calibrated corrector would do)
    corrected = {}
    for model, raw in raw_forecasts.items():
        # Subtract known bias (simulating what apply_bias() would do with
        # enough history)
        known_bias = cfg_model_errors[model]["bias"]
        corrected[model] = raw - known_bias  # ≈ actual_c + random_noise

    # 3. Ensemble stats
    ensemble = compute_ensemble_stats_sim(corrected, base_std)
    if not ensemble["tradeable"]:
        return []

    # 4. Generate buckets centred on ensemble mean (NOT on actual)
    buckets = generate_buckets(ensemble["mean_c"])

    signals = []
    for bucket in buckets:
        bucket["target_date"] = date_str

        # 5. Market implied probability
        market_prob = market_implied_prob(actual_c, bucket, rng)

        # 6. Model probability
        model_prob = prob_in_bucket(
            ensemble["mean_c"], ensemble["effective_std"],
            bucket["bucket_lo"], bucket["bucket_hi"]
        )

        # 7. Edge check
        edge = model_prob - market_prob
        if abs(edge) < min_edge:
            continue

        # 8. Kelly sizing
        direction = "YES" if edge > 0 else "NO"
        kf, size_usdc = kelly_size(model_prob, market_prob,
                                   bankroll, kelly_fraction, max_trade)
        if size_usdc < 1.0:
            continue

        # 9. Resolution
        resolved_yes = bucket_resolved_yes(actual_c, bucket)
        entry_price = market_prob if direction == "YES" else (1.0 - market_prob)
        pnl = compute_pnl(direction, entry_price, size_usdc, resolved_yes)

        signals.append({
            "date":        date_str,
            "direction":   direction,
            "model_prob":  round(model_prob, 4),
            "market_prob": round(market_prob, 4),
            "edge":        round(edge, 4),
            "entry_price": round(entry_price, 4),
            "size_usdc":   round(size_usdc, 2),
            "kelly_f":     round(kf, 4),
            "resolved":    resolved_yes,
            "pnl":         round(pnl, 4),
            "ens_mean":    round(ensemble["mean_c"], 2),
            "ens_std":     round(ensemble["std_c"], 2),
            "eff_std":     round(ensemble["effective_std"], 2),
            "actual_c":    round(actual_c, 2),
            "bucket_lo":   bucket["bucket_lo"],
            "bucket_hi":   bucket["bucket_hi"],
        })

    return signals


# ── Metrics computation ────────────────────────────────────────────────────────
def compute_metrics(all_signals: list[dict]) -> dict:
    """Compute aggregate metrics from simulation results."""
    if not all_signals:
        return {
            "n_signals": 0, "win_rate": 0.0, "mean_pnl": 0.0,
            "sharpe": None, "mean_edge": 0.0,
            "edge_hist": {"<0.05": 0, "0.05-0.10": 0, "0.10-0.20": 0, ">0.20": 0},
        }

    n = len(all_signals)
    wins = sum(1 for s in all_signals if s["pnl"] > 0)
    win_rate = wins / n

    pnls = [s["pnl"] for s in all_signals]
    mean_pnl = sum(pnls) / n

    # Sharpe annualized on daily PnL (not per-signal — signals aren't daily)
    from collections import defaultdict
    daily_pnl: dict[str, float] = defaultdict(float)
    for s in all_signals:
        daily_pnl[s["date"]] += s["pnl"]
    day_vals = list(daily_pnl.values())
    if len(day_vals) >= 5:
        day_mean = sum(day_vals) / len(day_vals)
        day_var  = sum((v - day_mean) ** 2 for v in day_vals) / max(len(day_vals) - 1, 1)
        day_std  = day_var ** 0.5 if day_var > 0 else None
        sharpe   = (day_mean / day_std) * math.sqrt(252) if day_std else None
    else:
        sharpe = None

    edges = [abs(s["edge"]) for s in all_signals]
    mean_edge = sum(edges) / len(edges)

    edge_hist = {"<0.05": 0, "0.05-0.10": 0, "0.10-0.20": 0, ">0.20": 0}
    for e in edges:
        if e < 0.05:
            edge_hist["<0.05"] += 1
        elif e < 0.10:
            edge_hist["0.05-0.10"] += 1
        elif e < 0.20:
            edge_hist["0.10-0.20"] += 1
        else:
            edge_hist[">0.20"] += 1

    return {
        "n_signals": n,
        "win_rate":  round(win_rate, 4),
        "mean_pnl":  round(mean_pnl, 4),
        "sharpe":    round(sharpe, 3) if sharpe else None,
        "mean_edge": round(mean_edge, 4),
        "edge_hist": edge_hist,
    }


# ── Main simulation runner ─────────────────────────────────────────────────────
def run_simulation(seed: int, n_trials: int, city_limit: int,
                   base_std: Optional[float] = None,
                   min_edge: Optional[float] = None,
                   kelly_fraction: Optional[float] = None,
                   max_trade: Optional[float] = None,
                   bankroll: float = cfg.STARTING_BANKROLL,
                   verbose: bool = True) -> dict:
    """
    Run full Monte Carlo simulation.

    Returns dict with metrics + per-city breakdowns.
    """
    # Use config values if not overridden
    _base_std      = base_std      if base_std      is not None else cfg.BASE_FORECAST_STD_C
    _min_edge      = min_edge      if min_edge      is not None else cfg.MIN_EDGE
    _kelly_frac    = kelly_fraction if kelly_fraction is not None else cfg.KELLY_FRACTION
    _max_trade     = max_trade     if max_trade     is not None else cfg.MAX_TRADE_USDC

    rng = random.Random(seed)

    # Date window
    today = date.today()
    end_date   = today - timedelta(days=ERA5_LAG)
    start_date = end_date - timedelta(days=LOOKBACK_DAYS - 1)
    start_str  = start_date.isoformat()
    end_str    = end_date.isoformat()

    if verbose:
        print(f"\n{'='*70}")
        print(f"SIMULATION  seed={seed}  trials={n_trials}  BASE_STD={_base_std:.2f}")
        print(f"  MIN_EDGE={_min_edge:.3f}  KELLY={_kelly_frac:.3f}  MAX_TRADE={_max_trade:.1f}")
        print(f"  ERA5 window: {start_str} → {end_str}")
        print(f"{'='*70}")

    cities = list(cfg.CITIES.items())
    if city_limit:
        cities = cities[:city_limit]

    all_signals = []
    city_metrics = {}
    signals_per_city_day = []

    for city_name, city_cfg in cities:
        if verbose:
            print(f"\n  {city_name} ({city_cfg['icao']}) ...", end="", flush=True)

        # Fetch ERA5 actuals
        try:
            actuals = fetch_era5_actuals(
                city_cfg["lat"], city_cfg["lon"],
                start_str, end_str, city_cfg["timezone"]
            )
        except Exception as e:
            if verbose:
                print(f" ERA5 FETCH FAILED: {e}")
            continue

        city_signals = []
        n_dates = 0

        for date_str, actual_c in sorted(actuals.items()):
            n_dates += 1
            day_signals = []

            for _trial in range(n_trials):
                trial_signals = simulate_one_trial(
                    actual_c, date_str, rng,
                    _base_std, _min_edge, _kelly_frac, _max_trade, bankroll
                )
                day_signals.extend(trial_signals)

            # Average signals per trial for this day
            n_sigs_per_trial = len(day_signals) / n_trials
            signals_per_city_day.append(n_sigs_per_trial)
            city_signals.extend(day_signals)

        city_m = compute_metrics(city_signals)
        city_metrics[city_name] = city_m
        all_signals.extend(city_signals)

        if verbose:
            print(f" {city_m['n_signals']:>7} sigs | "
                  f"win={city_m['win_rate']*100:.1f}% | "
                  f"pnl/sig=${city_m['mean_pnl']:.3f} | "
                  f"sharpe={city_m['sharpe']}")

    overall = compute_metrics(all_signals)
    mean_sigs_per_city_day = (
        sum(signals_per_city_day) / len(signals_per_city_day)
        if signals_per_city_day else 0.0
    )

    if verbose:
        print(f"\n{'─'*70}")
        print(f"OVERALL  n_signals={overall['n_signals']:,}")
        print(f"  Win rate:          {overall['win_rate']*100:.2f}%")
        print(f"  Mean PnL/signal:   ${overall['mean_pnl']:.4f}")
        print(f"  Sharpe (ann.):     {overall['sharpe']}")
        print(f"  Mean |edge|:       {overall['mean_edge']:.4f}")
        print(f"  Sigs/city/day:     {mean_sigs_per_city_day:.2f}")
        h = overall["edge_hist"]
        total_h = sum(h.values()) or 1
        print(f"  Edge distribution:")
        print(f"    <0.05:    {h['<0.05']:>6}  ({100*h['<0.05']/total_h:.1f}%)")
        print(f"    0.05-0.10:{h['0.05-0.10']:>6}  ({100*h['0.05-0.10']/total_h:.1f}%)")
        print(f"    0.10-0.20:{h['0.10-0.20']:>6}  ({100*h['0.10-0.20']/total_h:.1f}%)")
        print(f"    >0.20:    {h['>0.20']:>6}  ({100*h['>0.20']/total_h:.1f}%)")
        print(f"{'─'*70}\n")

    return {
        "overall":                 overall,
        "city_metrics":            city_metrics,
        "mean_sigs_per_city_day":  round(mean_sigs_per_city_day, 3),
        "params": {
            "base_std":       _base_std,
            "min_edge":       _min_edge,
            "kelly_fraction": _kelly_frac,
            "max_trade":      _max_trade,
            "seed":           seed,
            "n_trials":       n_trials,
        },
    }


# ── Iteration table ────────────────────────────────────────────────────────────
def print_iteration_table(results: list[dict]):
    print("\n" + "="*100)
    print("ITERATION RESULTS TABLE")
    print("="*100)
    hdr = (f"{'Iter':>4} | {'BASE_STD':>8} | {'MIN_EDGE':>8} | {'KELLY':>6} | "
           f"{'Exp_PnL':>8} | {'Win%':>6} | {'Sharpe':>7} | {'Sigs/c/d':>9} | Notes")
    print(hdr)
    print("-"*100)
    for i, r in enumerate(results, 1):
        p  = r["params"]
        m  = r["overall"]
        cd = r["mean_sigs_per_city_day"]
        sh = f"{m['sharpe']:.3f}" if m['sharpe'] else "  N/A "
        print(f"{i:>4} | {p['base_std']:>8.2f} | {p['min_edge']:>8.3f} | "
              f"{p['kelly_fraction']:>6.3f} | ${m['mean_pnl']:>7.4f} | "
              f"{m['win_rate']*100:>5.1f}% | {sh:>7} | {cd:>9.2f} | "
              f"{r.get('note', '')}")
    print("="*100)


# ── Global reference to model errors (allows overriding for experiments) ───────
cfg_model_errors = MODEL_ERRORS


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monte Carlo temperature market simulator")
    parser.add_argument("--seed",    type=int,   default=42,  help="Random seed")
    parser.add_argument("--trials",  type=int,   default=500, help="Trials per city/date")
    parser.add_argument("--cities",  type=int,   default=0,   help="Limit city count (0=all)")
    parser.add_argument("--iterate", action="store_true",     help="Run full iteration sweep")
    args = parser.parse_args()

    N_TRIALS = args.trials

    if args.iterate:
        # ── Full iterative sweep ───────────────────────────────────────────────
        iteration_results = []

        # Iteration 1: Baseline (current config)
        print("\n[Iter 1] Baseline — current config params")
        r1 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities)
        r1["note"] = "Baseline"
        iteration_results.append(r1)

        # Iteration 2: Increase BASE_FORECAST_STD_C (fix overconfidence)
        print("\n[Iter 2] BASE_STD=2.0 (realistic day-1 NWP error)")
        cfg.BASE_FORECAST_STD_C = 2.0
        r2 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=2.0)
        r2["note"] = "BASE_STD up to 2.0"
        iteration_results.append(r2)

        # Iteration 3: Reduce MIN_EDGE to get more signals
        print("\n[Iter 3] BASE_STD=2.0, MIN_EDGE=0.03")
        r3 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=2.0, min_edge=0.03)
        r3["note"] = "MIN_EDGE=0.03"
        iteration_results.append(r3)

        # Iteration 4: More conservative Kelly
        print("\n[Iter 4] BASE_STD=2.0, MIN_EDGE=0.03, KELLY=0.15")
        r4 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=2.0, min_edge=0.03, kelly_fraction=0.15)
        r4["note"] = "KELLY=0.15"
        iteration_results.append(r4)

        # Iteration 5: Tighten MIN_EDGE back, keep BASE_STD realistic
        print("\n[Iter 5] BASE_STD=2.0, MIN_EDGE=0.08, KELLY=0.20")
        r5 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=2.0, min_edge=0.08, kelly_fraction=0.20)
        r5["note"] = "MIN_EDGE=0.08"
        iteration_results.append(r5)

        # Iteration 6: Try smaller BASE_STD (more edge)
        print("\n[Iter 6] BASE_STD=1.5, MIN_EDGE=0.05, KELLY=0.25")
        r6 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=1.5, min_edge=0.05, kelly_fraction=0.25)
        r6["note"] = "BASE_STD=1.5"
        iteration_results.append(r6)

        # Iteration 7: Very conservative — high edge filter
        print("\n[Iter 7] BASE_STD=2.0, MIN_EDGE=0.12, KELLY=0.25")
        r7 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=2.0, min_edge=0.12, kelly_fraction=0.25)
        r7["note"] = "High edge filter"
        iteration_results.append(r7)

        # Iteration 8: Balanced — moderate everything
        print("\n[Iter 8] BASE_STD=1.8, MIN_EDGE=0.06, KELLY=0.20")
        r8 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=1.8, min_edge=0.06, kelly_fraction=0.20)
        r8["note"] = "Balanced"
        iteration_results.append(r8)

        # Iteration 9: Verify best with seed=123
        best_idx = max(range(len(iteration_results)),
                       key=lambda i: (
                           iteration_results[i]["overall"]["mean_pnl"]
                           if iteration_results[i]["overall"]["win_rate"] > 0.52 else -999
                       ))
        best = iteration_results[best_idx]
        bp = best["params"]
        print(f"\n[Iter 9] Best config (iter {best_idx+1}) verified with seed=123")
        r9 = run_simulation(seed=123, n_trials=N_TRIALS, city_limit=args.cities,
                            base_std=bp["base_std"],
                            min_edge=bp["min_edge"],
                            kelly_fraction=bp["kelly_fraction"])
        r9["note"] = f"Verify iter{best_idx+1} seed=123"
        iteration_results.append(r9)

        # Iteration 10: Final tuned
        print("\n[Iter 10] Fine-tuned best")
        r10 = run_simulation(seed=args.seed, n_trials=N_TRIALS, city_limit=args.cities,
                             base_std=bp["base_std"],
                             min_edge=max(bp["min_edge"] - 0.01, 0.02),
                             kelly_fraction=min(bp["kelly_fraction"] + 0.02, 0.35))
        r10["note"] = "Fine-tuned"
        iteration_results.append(r10)

        print_iteration_table(iteration_results)

        # Save best config recommendation
        final_best_idx = max(range(len(iteration_results)),
                             key=lambda i: (
                                 iteration_results[i]["overall"]["mean_pnl"]
                                 if iteration_results[i]["overall"]["win_rate"] > 0.55
                                 and (iteration_results[i]["overall"]["sharpe"] or 0) > 0.3
                                 else -999
                             ))
        fb = iteration_results[final_best_idx]
        fbp = fb["params"]
        print(f"\nBEST CONFIGURATION (iteration {final_best_idx + 1}):")
        print(f"  BASE_FORECAST_STD_C = {fbp['base_std']}")
        print(f"  MIN_EDGE            = {fbp['min_edge']}")
        print(f"  KELLY_FRACTION      = {fbp['kelly_fraction']}")
        print(f"  Expected PnL/signal = ${fb['overall']['mean_pnl']:.4f}")
        print(f"  Win rate            = {fb['overall']['win_rate']*100:.2f}%")
        print(f"  Sharpe              = {fb['overall']['sharpe']}")
        print(f"  Sigs/city/day       = {fb['mean_sigs_per_city_day']:.2f}")

    else:
        # Single baseline run
        r = run_simulation(seed=args.seed, n_trials=args.trials,
                           city_limit=args.cities)
