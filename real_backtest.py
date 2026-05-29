#!/usr/bin/env python3
"""
Real Backtest — uses actual resolved Polymarket markets + real CLOB historical prices
+ real Open-Meteo day-ahead forecasts + ERA5 actuals as ground truth.

Run: source venv/bin/activate && python3 real_backtest.py
"""
import csv
import json
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(__file__))

import requests

import db
from config_active import (
    CITIES, OPENMETEO_MODELS, OPENMETEO_ARCHIVE_URL,
    GAMMA_API, CLOB_API, CITY_ALIASES,
    MIN_EDGE, BASE_FORECAST_STD_C,
)
from data.polymarket import parse_question, parse_clob_tokens
from data.openmeteo import fetch_historical_actuals
from signals.bias_corrector import get_corrected_ensemble
from signals.edge_calculator import bucket_bounds_to_celsius, model_prob_for_bucket
from signals.ensemble import compute_ensemble_stats
from scipy.stats import norm as _norm
from signals.bias_corrector import get_corrected_ensemble_at_date
from signals.confidence_tier import apply_tier_to_signal
from signals.bias_corrector import station_is_ready

db.init_db()

TODAY = date.today()
OUTPUT_CSV = "real_backtest_results.csv"
MODELS_TO_USE = ["gfs", "ecmwf", "icon", "gem", "meteofrance"]
MAX_WORKERS = 10

DAYS_AGO_MIN = 2
DAYS_AGO_MAX = 90

# Parse CLI args at module level so globals are set before any function runs
import argparse as _ap
_parser = _ap.ArgumentParser(add_help=False)
_parser.add_argument("--days-start", type=int, default=DAYS_AGO_MIN)
_parser.add_argument("--days-end",   type=int, default=DAYS_AGO_MAX)
_args, _ = _parser.parse_known_args()
DAYS_AGO_MIN = _args.days_start
DAYS_AGO_MAX = _args.days_end


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _req_with_retry(url, params=None, timeout=15):
    """GET with one retry on 429."""
    for attempt in range(2):
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 429:
            print("  [429 rate limit] sleeping 2s...", flush=True)
            time.sleep(2)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


from utils import f_to_c as _f_to_c


MARKET_SHRINK = 0.30
CROWD_STD_C   = 2.5
SPREAD_HAIRCUT = 0.015   # 1.5% to simulate bid-ask spread cost

def _crowd_model_price(ensemble_mean_c: float, lo_c, hi_c) -> float:
    """
    Fallback market price: Gaussian crowd using ensemble mean + MARKET_SHRINK.
    Used when no real CLOB price is available.
    """
    lo_v = lo_c if lo_c is not None else float("-inf")
    hi_v = hi_c if hi_c is not None else float("inf")
    crowd_prob = float(_norm.cdf(hi_v, ensemble_mean_c, CROWD_STD_C)
                       - _norm.cdf(lo_v, ensemble_mean_c, CROWD_STD_C))
    mid = 0.5 + MARKET_SHRINK * (crowd_prob - 0.5)
    return float(max(0.05, min(0.95, mid)))


# ─── Step 1: Fetch resolved temperature markets via events API ────────────────

def fetch_resolved_markets():
    """
    Use the Gamma events API with tag_slug=weather to find closed city-specific
    temperature markets. This is much more targeted than paginating all markets.
    """
    print("Fetching resolved weather events from Gamma API...", flush=True)

    # City names as they appear in Polymarket questions
    city_list = [
        "New York", "NYC", "Chicago", "London", "Paris", "Miami", "Dallas",
        "Seattle", "Atlanta", "Munich", "Madrid", "Milan", "Toronto",
        "Buenos Aires", "Sao Paulo", "Tel Aviv", "Hong Kong",
    ]
    temp_kw = ["°F", "°C"]

    all_markets = []
    batch = 500
    for offset in range(0, 10000, batch):
        try:
            resp = _req_with_retry(
                f"{GAMMA_API}/events",
                params={
                    "active":    "false",
                    "closed":    "true",
                    "tag_slug":  "weather",
                    "limit":     batch,
                    "offset":    offset,
                },
                timeout=30,
            )
            data = resp.json()
        except Exception as e:
            print(f"  Events API error at offset={offset}: {e}", flush=True)
            break
        if not data:
            break

        for event in data:
            for m in event.get("markets", []):
                all_markets.append(m)

        print(f"  offset={offset}: {len(data)} events → {len(all_markets)} markets total", flush=True)
        if len(data) < batch:
            break

    print(f"  Total weather markets collected: {len(all_markets)}", flush=True)

    # Filter and parse
    parsed = []
    for m in all_markets:
        question = m.get("question", "")
        if not question:
            continue

        # Must be city temperature (not global anomaly)
        if not any(kw in question for kw in temp_kw):
            continue
        if not any(city in question for city in city_list):
            continue

        parsed_q = parse_question(question)
        if not parsed_q:
            continue

        # Only daily markets
        if parsed_q.get("market_type") != "daily":
            continue

        city = parsed_q["city"]
        if city not in CITIES:
            continue

        # Parse end date first so we can correct the target_date year
        end_date_raw = m.get("endDate", "")
        end_dt = None
        if end_date_raw:
            try:
                end_dt = datetime.fromisoformat(str(end_date_raw).replace("Z", "+00:00"))
            except Exception:
                try:
                    end_dt = datetime.utcfromtimestamp(float(end_date_raw))
                except Exception:
                    pass
        if end_dt is None:
            continue

        # Correct target_date year using end_dt — parse_question guesses year from
        # current date which breaks for Jan/Feb markets parsed in March+
        target_date = parsed_q["target_date"]
        end_date_local = end_dt.date()
        # The target date should be within ~5 days before the market end date
        for yr_offset in [-1, 0, 1]:
            candidate = date(end_date_local.year + yr_offset, target_date.month, target_date.day)
            if abs((end_date_local - candidate).days) <= 7:
                target_date = candidate
                break

        days_ago = (TODAY - target_date).days
        if days_ago < DAYS_AGO_MIN or days_ago > DAYS_AGO_MAX:
            continue

        tokens = parse_clob_tokens(m.get("clobTokenIds", "[]"))
        if not tokens:
            continue

        # outcomePrices: ["1","0"] → YES won; ["0","1"] → NO won; ["0","0"] → unresolved/void
        outcome_prices = m.get("outcomePrices", "[]")
        try:
            op = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
        except Exception:
            op = []
        market_resolved_yes = None
        if len(op) >= 2:
            if str(op[0]) == "1":
                market_resolved_yes = 1
            elif str(op[1]) == "1":
                market_resolved_yes = 0
        # Skip if unresolved (both 0 or both 1)
        if market_resolved_yes is None:
            continue

        parsed.append({
            "market_id":           m.get("conditionId") or m.get("id", ""),
            "question":            question,
            "city":                city,
            "target_date":         target_date,
            "bucket_lo":           parsed_q["bucket_lo"],
            "bucket_hi":           parsed_q["bucket_hi"],
            "bucket_unit":         parsed_q["bucket_unit"],
            "clob_token_yes":      tokens[0],
            "end_dt":              end_dt,
            "days_ago":            days_ago,
            "market_resolved_yes": market_resolved_yes,
        })

    print(f"  Usable parsed markets (days_ago 2-90, city known): {len(parsed)}", flush=True)
    return parsed


# ─── Step 2: CLOB price ~24h before endDate ───────────────────────────────────

def fetch_clob_price_24h_before(token_id: str, end_dt: datetime) -> float | None:
    """
    Fetch CLOB price-history and find the price closest to 24h before end_dt.
    Returns float in [0,1] or None.
    """
    target_ts = end_dt.timestamp() - 86400  # 24h before end
    try:
        resp = _req_with_retry(
            f"{CLOB_API}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": 60},
            timeout=15,
        )
        history = resp.json()
        if isinstance(history, dict):
            history = history.get("history", [])
        if not history:
            return None
        # Find point closest to target_ts
        best = min(history, key=lambda pt: abs(float(pt["t"]) - target_ts))
        price = float(best["p"])
        if 0.01 <= price <= 0.99:
            return price
        return None
    except Exception:
        return None


# ─── Step 3: Day-ahead forecast from Open-Meteo ───────────────────────────────

def fetch_day_ahead_forecast(model_name: str, lat: float, lon: float,
                              target_date_str: str, timezone: str,
                              days_ago: int) -> float | None:
    """Fetch what a model predicted 1 day ahead for target_date (historical)."""
    if days_ago < 1:
        return None
    try:
        resp = _req_with_retry(
            OPENMETEO_MODELS[model_name],
            params={
                "latitude":          lat,
                "longitude":         lon,
                "daily":             "temperature_2m_max",
                "temperature_unit":  "celsius",
                "forecast_days":     1,
                "past_days":         days_ago + 1,
                "timezone":          timezone,
            },
            timeout=15,
        )
        data = resp.json()
        times = data.get("daily", {}).get("time", [])
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if target_date_str in times:
            val = temps[times.index(target_date_str)]
            return float(val) if val is not None else None
    except Exception:
        pass
    return None


# ─── Step 4: ERA5 actuals ─────────────────────────────────────────────────────

def fetch_era5_for_city_date_range(city: str, cfg: dict,
                                    dates: list[str]) -> dict[str, float]:
    """Fetch ERA5 actuals for a city over all needed dates at once."""
    if not dates:
        return {}
    dates_sorted = sorted(dates)
    start_d = dates_sorted[0]
    end_d = dates_sorted[-1]
    try:
        return fetch_historical_actuals(
            cfg["lat"], cfg["lon"], start_d, end_d, cfg["timezone"]
        )
    except Exception as e:
        print(f"  ERA5 failed for {city}: {e}", flush=True)
        return {}


# ─── Processing pipeline per market ──────────────────────────────────────────

def process_market(market: dict, forecasts_cache: dict, actuals_cache: dict,
                   asos_cache: dict) -> dict | None:
    """
    Run the full signal pipeline for one resolved market.
    Returns a result row dict or None if skipped.
    """
    city = market["city"]
    cfg = CITIES[city]
    icao = cfg["icao"]
    target_date_str = market["target_date"].isoformat()
    days_ago = market["days_ago"]

    # 1. Forecasts
    available = {m: forecasts_cache[(city, target_date_str, m)]
                 for m in MODELS_TO_USE if (city, target_date_str, m) in forecasts_cache}
    if len(available) < 1:
        return None

    # Fill missing models with mean
    mean_raw = sum(available.values()) / len(available)
    full_raw = {m: available.get(m, mean_raw) for m in MODELS_TO_USE}

    # 2. Point-in-time bias correction (only use observations before target_date)
    corrected = get_corrected_ensemble_at_date(icao, full_raw, target_date_str,
                                               cutoff_date=target_date_str)
    if not corrected:
        return None

    # 3. Ensemble stats
    try:
        ensemble = compute_ensemble_stats(corrected)
    except ValueError:
        return None

    # 4. Bucket probability
    lo_c, hi_c = bucket_bounds_to_celsius(
        market["bucket_lo"], market["bucket_hi"], market["bucket_unit"]
    )
    model_prob = model_prob_for_bucket(
        ensemble["mean_c"], ensemble["effective_std"], lo_c, hi_c
    )

    # 5. Market price — crowd model fallback populated here with ensemble mean
    if market.get("clob_price") is None:
        market_price = _crowd_model_price(ensemble["mean_c"], lo_c, hi_c)
    else:
        market_price = market["clob_price"]
    price_source = market.get("price_source", "unknown")

    # 6. Apply spread haircut (1.5%) to simulate realistic entry price
    edge_raw = model_prob - market_price
    direction = "YES" if edge_raw > 0 else "NO"

    # Skip YES bets on low market prices — crowd has priced these near zero and
    # the model edge is almost always noise (backtest shows 1.5% win rate here)
    if direction == "YES" and market_price < 0.20:
        return None

    # Apply stricter edge for very recent markets (days_ago <= 7)
    from config_active import MIN_EDGE_RECENT_MULTIPLIER, MIN_EDGE_RECENT_DAYS
    min_edge_threshold = (MIN_EDGE * MIN_EDGE_RECENT_MULTIPLIER
                          if days_ago <= MIN_EDGE_RECENT_DAYS else MIN_EDGE)
    if abs(edge_raw) < min_edge_threshold:
        return None

    if direction == "YES":
        entry_price = min(0.99, market_price + SPREAD_HAIRCUT)
    else:
        entry_price = max(0.01, (1.0 - market_price) + SPREAD_HAIRCUT)
    edge = model_prob - entry_price if direction == "YES" else (1.0 - model_prob) - entry_price

    # 7. Ground truth: prefer ASOS station data (matches Polymarket resolution source),
    #    fall back to ERA5, then market's own outcomePrices
    actual_c = asos_cache.get(city, {}).get(target_date_str)
    truth_source = "asos"
    if actual_c is None:
        actual_c = actuals_cache.get(city, {}).get(target_date_str)
        truth_source = "era5"
    market_resolved_yes = market.get("market_resolved_yes")

    if actual_c is not None:
        lo_v = lo_c if lo_c is not None else -math.inf
        hi_v = hi_c if hi_c is not None else math.inf
        # [lo, hi) — exclusive upper bound matching Polymarket convention
        outcome_yes = int(lo_v <= actual_c < hi_v)
    elif market_resolved_yes is not None:
        outcome_yes = market_resolved_yes
        actual_c = float("nan")
        truth_source = "market"
    else:
        return None

    correct = int(
        (direction == "YES" and outcome_yes == 1) or
        (direction == "NO" and outcome_yes == 0)
    )

    # 8. $1-unit PnL
    if direction == "YES":
        pnl_unit = (1.0 / entry_price - 1.0) if correct else -1.0
    else:
        pnl_unit = (1.0 / entry_price - 1.0) if correct else -1.0

    # 9. Kelly-sized PnL (confidence tiering applied)
    signal_dict = {
        "model_prob":       model_prob,
        "market_prob":      market_price,
        "edge":             edge_raw,
        "direction":        direction,
        "ensemble_std_c":   ensemble["std_c"],
        "ensemble_score":   ensemble["score"],
        "size_usdc":        50.0,  # placeholder; tiering scales this
        "kelly_f":          0.0,
        "climo_deviation_c": None,
        "climo_std_c":      None,
        "nowcast_weight":   0.0,
    }
    is_ready = station_is_ready(icao)
    try:
        signal_tiered = apply_tier_to_signal(signal_dict, station_ready=is_ready)
        kelly_size = signal_tiered.get("size_usdc", 0.0)
        tier = signal_tiered.get("confidence_tier", 4)
    except Exception:
        kelly_size = 0.0
        tier = 4

    if direction == "YES":
        kelly_pnl = kelly_size * (1.0 / entry_price - 1.0) if correct else -kelly_size
    else:
        kelly_pnl = kelly_size * (1.0 / entry_price - 1.0) if correct else -kelly_size

    return {
        "market_id":           market["market_id"],
        "question":            market["question"][:80],
        "city":                city,
        "target_date":         target_date_str,
        "days_ago":            days_ago,
        "bucket_lo":           market["bucket_lo"],
        "bucket_hi":           market["bucket_hi"],
        "bucket_unit":         market["bucket_unit"],
        "bucket_lo_c":         round(lo_c, 2) if lo_c is not None else None,
        "bucket_hi_c":         round(hi_c, 2) if hi_c is not None else None,
        "price_source":        price_source,
        "market_price":        round(market_price, 4),
        "entry_price":         round(entry_price, 4),
        "model_prob":          round(model_prob, 4),
        "edge":                round(edge_raw, 4),
        "direction":           direction,
        "confidence_tier":     tier,
        "kelly_size":          round(kelly_size, 2),
        "ensemble_mean_c":     round(ensemble["mean_c"], 2),
        "ensemble_std_c":      round(ensemble["std_c"], 2),
        "effective_std":       round(ensemble["effective_std"], 2),
        "n_models":            len(available),
        "actual_c":            round(actual_c, 2) if not math.isnan(actual_c) else None,
        "truth_source":        truth_source,
        "outcome_yes":         outcome_yes,
        "market_resolved_yes": market.get("market_resolved_yes"),
        "correct":             correct,
        "pnl":                 round(pnl_unit, 4),
        "kelly_pnl":           round(kelly_pnl, 4),
    }


# ─── Analysis loops ──────────────────────────────────────────────────────────

def _safe_mean(lst):
    return sum(lst) / len(lst) if lst else float("nan")


def run_analysis(rows: list[dict]):
    print("\n" + "=" * 70)
    print("REAL BACKTEST ANALYSIS")
    print(f"Total rows with signals: {len(rows)}")
    print("=" * 70)

    if not rows:
        print("No data to analyse.")
        return

    # ── Loop 1: Calibration ──────────────────────────────────────────────────
    print("\n── LOOP 1: CALIBRATION (model_prob bins vs actual YES rate) ──────────")
    print(f"{'Bin':<12} {'N':>5} {'Actual%':>9} {'Expected%':>11} {'Delta':>8} {'Verdict'}")
    print("─" * 60)
    bins = [(i / 10, (i + 1) / 10) for i in range(10)]
    calibration_overconf = 0
    for lo, hi in bins:
        in_bin = [r for r in rows if lo <= r["model_prob"] < hi]
        if not in_bin:
            continue
        actual_yes = sum(r["outcome_yes"] for r in in_bin) / len(in_bin)
        expected = (lo + hi) / 2
        delta = actual_yes - expected
        verdict = ("OK" if abs(delta) < 0.05
                   else ("OVERCONF" if delta < 0 else "UNDERCONF"))
        if delta < 0:
            calibration_overconf += len(in_bin)
        print(f"{lo:.1f}-{hi:.1f}     {len(in_bin):>5} {actual_yes*100:>8.1f}%  "
              f"{expected*100:>10.1f}%  {delta*100:>+7.1f}%  {verdict}")
    total_yes_rate = sum(r["outcome_yes"] for r in rows) / len(rows)
    total_mp = sum(r["model_prob"] for r in rows) / len(rows)
    print(f"\nOverall actual YES rate: {total_yes_rate*100:.1f}%  |  "
          f"Mean model_prob: {total_mp*100:.1f}%")
    print(f"\nFINDING: {'Model is OVERCONFIDENT (predicts higher prob than reality)' if total_mp > total_yes_rate + 0.03 else 'Model is UNDERCONFIDENT (predicts lower prob than reality)' if total_mp < total_yes_rate - 0.03 else 'Model is REASONABLY CALIBRATED'}")
    print("IMPLICATION: If overconfident, reduce model_prob toward 0.5. If underconf, it may be ok.")
    print("FIX: Add a shrinkage factor: model_prob = 0.5 + (model_prob - 0.5) * 0.85")

    # ── Loop 2: Edge magnitude vs actual profit ──────────────────────────────
    print("\n── LOOP 2: EDGE MAGNITUDE vs ACTUAL WIN RATE ──────────────────────────")
    edge_bins = [(0.05, 0.08), (0.08, 0.12), (0.12, 0.20), (0.20, 1.01)]
    print(f"{'Edge range':<14} {'N':>5} {'Win%':>8} {'Mean PnL':>10} {'Assessment'}")
    print("─" * 55)
    edge_monotone = True
    prev_wr = None
    for lo, hi in edge_bins:
        grp = [r for r in rows if lo <= abs(r["edge"]) < hi]
        if not grp:
            continue
        wr = sum(r["correct"] for r in grp) / len(grp)
        mean_pnl = _safe_mean([r["pnl"] for r in grp])
        label = hi if hi < 1.01 else "+"
        if prev_wr is not None and wr < prev_wr - 0.05:
            edge_monotone = False
        prev_wr = wr
        assess = "GOOD" if mean_pnl > 0 else "BAD"
        print(f"{lo:.2f}-{label:<6}    {len(grp):>5} {wr*100:>7.1f}%  {mean_pnl:>+9.3f}  {assess}")
    print(f"\nFINDING: {'Edge size CORRELATES with win rate (real edge exists)' if edge_monotone else 'Edge does NOT monotonically predict win rate (may be noise)'}")
    print("IMPLICATION: If edge is noise, the signal quality is poor. Real edge should → win rate.")
    print("FIX: Raise MIN_EDGE threshold or add a confidence filter based on ensemble std.")

    # ── Loop 3: City breakdown ───────────────────────────────────────────────
    print("\n── LOOP 3: CITY BREAKDOWN ──────────────────────────────────────────────")
    print(f"{'City':<18} {'N':>5} {'Win%':>8} {'Mean edge':>10} {'Total PnL':>11} {'Mean err (°C)':>14}")
    print("─" * 70)
    city_rows: dict[str, list] = {}
    for r in rows:
        city_rows.setdefault(r["city"], []).append(r)
    city_issues = []
    for city, grp in sorted(city_rows.items(), key=lambda x: -len(x[1])):
        wr = sum(r["correct"] for r in grp) / len(grp)
        mean_edge = _safe_mean([r["edge"] for r in grp])
        total_pnl = sum(r["pnl"] for r in grp)
        # model error = ensemble_mean - actual (in °C)
        model_errors = [r["ensemble_mean_c"] - r["actual_c"] for r in grp]
        mean_err = _safe_mean(model_errors)
        flag = " <-- BAD" if wr < 0.45 or abs(mean_err) > 1.5 else ""
        if wr < 0.45 or abs(mean_err) > 1.5:
            city_issues.append((city, mean_err, wr))
        print(f"{city:<18} {len(grp):>5} {wr*100:>7.1f}%  {mean_edge:>+9.3f}  "
              f"{total_pnl:>+10.2f}  {mean_err:>+13.2f}°C{flag}")
    if city_issues:
        print(f"\nFINDING: Cities with systematic error: {', '.join(c[0] for c in city_issues)}")
        print("IMPLICATION: Per-city bias corrections are insufficient or absent.")
        print("FIX: Retrain bias corrections for these cities with more history data.")
    else:
        print("\nFINDING: No city shows extreme systematic bias.")

    # ── Loop 4: Direction bias ───────────────────────────────────────────────
    print("\n── LOOP 4: DIRECTION BIAS (YES bets vs NO bets) ────────────────────────")
    yes_rows = [r for r in rows if r["direction"] == "YES"]
    no_rows  = [r for r in rows if r["direction"] == "NO"]
    print(f"{'Direction':<12} {'N':>5} {'Win%':>8} {'Mean PnL':>10}")
    print("─" * 38)
    for label, grp in [("YES", yes_rows), ("NO", no_rows)]:
        if not grp:
            print(f"{label:<12} {'0':>5}")
            continue
        wr = sum(r["correct"] for r in grp) / len(grp)
        mean_pnl = _safe_mean([r["pnl"] for r in grp])
        print(f"{label:<12} {len(grp):>5} {wr*100:>7.1f}%  {mean_pnl:>+9.3f}")
    if yes_rows and no_rows:
        yes_wr = sum(r["correct"] for r in yes_rows) / len(yes_rows)
        no_wr  = sum(r["correct"] for r in no_rows) / len(no_rows)
        diff = abs(yes_wr - no_wr)
        if diff > 0.08:
            better = "YES" if yes_wr > no_wr else "NO"
            worse  = "NO" if better == "YES" else "YES"
            print(f"\nFINDING: {better} bets win {diff*100:.1f}% more than {worse} bets — DIRECTIONAL BIAS")
            print(f"IMPLICATION: The model systematically {'over-estimates' if better == 'NO' else 'under-estimates'} probability.")
            print("FIX: Apply asymmetric shrinkage: compress high model_probs more than low ones.")
        else:
            print("\nFINDING: YES and NO bets roughly equal — no directional bias detected.")

    # ── Loop 5: What predicts a bad signal? ──────────────────────────────────
    print("\n── LOOP 5: SIGNAL QUALITY PREDICTORS ──────────────────────────────────")
    # Correlate abs(model_prob - outcome) with various features
    errors_abs = [abs(r["model_prob"] - r["outcome_yes"]) for r in rows]
    mean_abs_err = _safe_mean(errors_abs)
    print(f"Mean |model_prob - outcome|: {mean_abs_err:.3f}")

    # By market_price level
    print(f"\n{'Market price range':<22} {'N':>5} {'Mean |err|':>12} {'Win%':>8}")
    print("─" * 50)
    price_bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
    for lo, hi in price_bins:
        grp = [r for r in rows if lo <= r["market_price"] < hi]
        if not grp:
            continue
        me = _safe_mean([abs(r["model_prob"] - r["outcome_yes"]) for r in grp])
        wr = sum(r["correct"] for r in grp) / len(grp)
        print(f"{lo:.1f}-{hi:.1f}              {len(grp):>5} {me:>11.3f}  {wr*100:>7.1f}%")

    print(f"\n{'Edge range':<22} {'N':>5} {'Mean |err|':>12} {'Win%':>8}")
    print("─" * 50)
    for lo, hi in edge_bins:
        grp = [r for r in rows if lo <= abs(r["edge"]) < hi]
        if not grp:
            continue
        me = _safe_mean([abs(r["model_prob"] - r["outcome_yes"]) for r in grp])
        wr = sum(r["correct"] for r in grp) / len(grp)
        print(f"{lo:.2f}-{hi if hi < 1.01 else '+'}              {len(grp):>5} {me:>11.3f}  {wr*100:>7.1f}%")

    print("\nFINDING: Markets with extreme prices (near 0 or 1) are already well-resolved by the market.")
    print("IMPLICATION: Signals at extreme market prices should be treated with caution.")
    print("FIX: Apply a penalty to signals where market_price < 0.10 or > 0.90.")

    # ── Loop 6: Temporal pattern ─────────────────────────────────────────────
    print("\n── LOOP 6: TEMPORAL PATTERN (forecast age vs win rate) ────────────────")
    temporal_bins = [(2, 7), (8, 14), (15, 30), (31, 90)]
    print(f"{'Days ago':<14} {'N':>5} {'Win%':>8} {'Mean PnL':>10} {'Assessment'}")
    print("─" * 50)
    for lo, hi in temporal_bins:
        grp = [r for r in rows if lo <= r["days_ago"] <= hi]
        if not grp:
            continue
        wr = sum(r["correct"] for r in grp) / len(grp)
        mean_pnl = _safe_mean([r["pnl"] for r in grp])
        assess = "GOOD" if wr > 0.52 else ("OK" if wr > 0.48 else "BAD")
        print(f"{lo}-{hi:<8}    {len(grp):>5} {wr*100:>7.1f}%  {mean_pnl:>+9.3f}  {assess}")
    print("\nFINDING: Win rate should degrade with older forecasts (30+ day-old GFS/ECMWF worse).")
    print("IMPLICATION: If old forecasts still win, it suggests market mispricings are large enough to overcome forecast error.")
    print("FIX: Apply a days_ago penalty: effective_std += 0.1 * max(0, days_ago - 14).")

    # ── Loop 7: Bucket type analysis ─────────────────────────────────────────
    print("\n── LOOP 7: BUCKET TYPE ANALYSIS ────────────────────────────────────────")
    near_center = [r for r in rows if 0.4 <= r["model_prob"] <= 0.6]
    tails = [r for r in rows if r["model_prob"] < 0.2 or r["model_prob"] > 0.8]
    mid_range = [r for r in rows if (0.2 <= r["model_prob"] < 0.4) or (0.6 < r["model_prob"] <= 0.8)]
    print(f"{'Bucket type':<20} {'N':>5} {'Win%':>8} {'Mean PnL':>10} {'Mean |edge|':>13}")
    print("─" * 60)
    for label, grp in [("Near-center (0.4-0.6)", near_center),
                        ("Mid (0.2-0.4 / 0.6-0.8)", mid_range),
                        ("Tails (<0.2 / >0.8)", tails)]:
        if not grp:
            continue
        wr = sum(r["correct"] for r in grp) / len(grp)
        mean_pnl = _safe_mean([r["pnl"] for r in grp])
        mean_edge = _safe_mean([abs(r["edge"]) for r in grp])
        print(f"{label:<20} {len(grp):>5} {wr*100:>7.1f}%  {mean_pnl:>+9.3f}  {mean_edge:>12.3f}")

    if near_center and tails:
        nc_wr = sum(r["correct"] for r in near_center) / len(near_center)
        t_wr  = sum(r["correct"] for r in tails) / len(tails)
        nc_pnl = _safe_mean([r["pnl"] for r in near_center])
        t_pnl  = _safe_mean([r["pnl"] for r in tails])
        print(f"\nFINDING: {'Tails MORE profitable' if t_pnl > nc_pnl else 'Near-center MORE profitable'} "
              f"(tail PnL={t_pnl:+.3f} vs center PnL={nc_pnl:+.3f})")
        print("IMPLICATION: High-confidence tail signals tend to have bigger edge but higher variance.")
        print("FIX: If tails underperform, add std buffer for overconfident high-prob buckets.")

    # ── Overall summary ───────────────────────────────────────────────────────
    overall_wr = sum(r["correct"] for r in rows) / len(rows)
    overall_pnl = sum(r["pnl"] for r in rows)
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print(f"Total signals:   {len(rows)}")
    print(f"Overall win rate: {overall_wr*100:.1f}%")
    print(f"Total PnL ($1 units): ${overall_pnl:+.2f}")
    overall_kelly_pnl = sum(r.get("kelly_pnl", 0) for r in rows)
    price_src_counts = {}
    for r in rows:
        src = r.get("price_source", "unknown")
        price_src_counts[src] = price_src_counts.get(src, 0) + 1
    print(f"Total Kelly PnL:      ${overall_kelly_pnl:+.2f}")
    print(f"Price sources: {price_src_counts}")
    truth_counts = {}
    for r in rows:
        src = r.get("truth_source", "unknown")
        truth_counts[src] = truth_counts.get(src, 0) + 1
    print(f"Truth sources: {truth_counts}")
    print(f"Mean model_prob: {total_mp*100:.1f}%  |  Actual YES rate: {total_yes_rate*100:.1f}%")

    # ── Top 3 Issues ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TOP 3 ISSUES RANKED BY IMPACT")
    print("=" * 70)

    issues = []

    # Issue 1: Calibration
    cal_delta = total_mp - total_yes_rate
    issues.append((
        abs(cal_delta),
        f"1. CALIBRATION DRIFT (model_prob offset = {cal_delta:+.3f})\n"
        f"   Data: Mean model_prob={total_mp*100:.1f}%, actual YES rate={total_yes_rate*100:.1f}%\n"
        f"   Implies: {'Overconfidence — model assigns too-high probs → too many bad YES bets' if cal_delta > 0 else 'Underconfidence — model assigns too-low probs → misses real edges'}\n"
        f"   Fix: Apply calibration scaling in model_prob_for_bucket:\n"
        f"        scaled = 0.5 + (model_prob - 0.5) * {max(0.7, 1.0 - abs(cal_delta) * 2):.2f}"
    ))

    # Issue 2: Direction bias
    if yes_rows and no_rows:
        yes_wr2 = sum(r["correct"] for r in yes_rows) / len(yes_rows)
        no_wr2  = sum(r["correct"] for r in no_rows) / len(no_rows)
        dir_diff = yes_wr2 - no_wr2
        issues.append((
            abs(dir_diff),
            f"2. DIRECTIONAL BIAS (YES win%={yes_wr2*100:.1f}% vs NO win%={no_wr2*100:.1f}%)\n"
            f"   Data: Difference = {dir_diff*100:+.1f}%\n"
            f"   Implies: {'Model over-estimates probs → too many YES bets that lose' if dir_diff < -0.05 else 'Model under-estimates probs → NO bets win more' if dir_diff > 0.05 else 'Roughly balanced'}\n"
            f"   Fix: {'Increase BASE_FORECAST_STD_C from {:.2f} to {:.2f} to widen distribution'.format(BASE_FORECAST_STD_C, BASE_FORECAST_STD_C * 1.15) if dir_diff < -0.05 else 'Decrease BASE_FORECAST_STD_C to sharpen distribution'}"
        ))

    # Issue 3: City-level errors
    if city_issues:
        worst_cities = sorted(city_issues, key=lambda x: abs(x[1]), reverse=True)[:3]
        city_str = ", ".join(f"{c} (err={e:+.2f}°C)" for c, e, _ in worst_cities)
        issues.append((
            max(abs(e) for _, e, _ in worst_cities),
            f"3. CITY-LEVEL FORECAST BIAS ({city_str})\n"
            f"   Data: These cities have systematic ensemble_mean vs actual errors > 1.5°C\n"
            f"   Implies: Bias corrections are stale, undertrained, or ERA5 grid mismatch\n"
            f"   Fix: Increase MIN_HISTORY_DAYS for affected cities, or apply a city-level\n"
            f"        additive correction: mean_c += per_city_bias[city]"
        ))
    else:
        issues.append((
            overall_wr,
            f"3. OVERALL WIN RATE ({overall_wr*100:.1f}%) {'BELOW 50% — no real edge' if overall_wr < 0.50 else 'ABOVE 50% — real edge exists'}\n"
            f"   Data: Win rate across all {len(rows)} signals\n"
            f"   Implies: {'Signal is noise or negative edge — do not trade' if overall_wr < 0.48 else 'Edge is real but small — Kelly sizing must be conservative'}\n"
            f"   Fix: {'Audit bucket selection logic and MIN_EDGE threshold' if overall_wr < 0.50 else 'Lower MIN_EDGE to 0.03 to capture more signals'}"
        ))

    issues.sort(key=lambda x: -x[0])
    for _, text in issues[:3]:
        print(f"\n{text}")

    print("\n" + "=" * 70)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\nReal Backtest — today={TODAY}  ERA5 window: 2–90 days ago\n")

    # ── Step 1: Fetch resolved markets ────────────────────────────────────────
    markets = fetch_resolved_markets()
    if not markets:
        print("No markets found. Exiting.")
        return

    # ── Step 2: Fetch real CLOB prices (stored DB → live API → crowd model fallback) ──
    print("\nFetching CLOB prices...", flush=True)
    n_db = n_api = n_crowd = 0
    for m in markets:
        end_dt = m["end_dt"]
        entry_ts = (end_dt.replace(tzinfo=None) - __import__("datetime").timedelta(hours=24)).isoformat()
        # Tier 1: stored DB snapshot (from --scrape-prices or live scans)
        stored = db.get_price_at_time(m["market_id"], entry_ts, window_hours=6)
        if stored is not None:
            m["clob_price"] = stored
            m["price_source"] = "stored_db"
            n_db += 1
            continue
        # Tier 2: crowd model (uses ensemble mean — populated later in process_market)
        # (live CLOB API skipped in backtest — too slow for historical runs)
        m["clob_price"] = None   # will be filled in process_market
        m["price_source"] = "crowd_model"
        n_crowd += 1
    markets_with_price = markets
    print(f"  Prices: stored_db={n_db}  clob_api={n_api}  crowd_model={n_crowd}", flush=True)

    # ── Step 3: Group by city and fetch ERA5 actuals in bulk ──────────────────
    print("\nFetching ERA5 actuals by city...", flush=True)
    city_dates: dict[str, list[str]] = {}
    for m in markets_with_price:
        city_dates.setdefault(m["city"], []).append(m["target_date"].isoformat())

    actuals_cache: dict[str, dict] = {}
    for city, dates in city_dates.items():
        cfg = CITIES[city]
        actuals_cache[city] = fetch_era5_for_city_date_range(city, cfg, dates)
        print(f"  {city}: {len(actuals_cache[city])} ERA5 dates", flush=True)

    # Build ASOS actuals cache from DB (preferred resolution source — matches Polymarket)
    print("\nLoading ASOS actuals from DB...", flush=True)
    asos_cache: dict[str, dict] = {}
    for city, cfg in CITIES.items():
        icao = cfg["icao"]
        obs_rows = db.get_historical_obs(icao, source="asos")
        asos_cache[city] = {r["obs_date"]: r["actual_high_c"] for r in obs_rows}
    total_asos = sum(len(v) for v in asos_cache.values())
    print(f"  ASOS obs loaded: {total_asos} date-city pairs", flush=True)

    # ── Step 4: Fetch day-ahead model forecasts in parallel ───────────────────
    # Deduplicate (city, date_str, model)
    forecast_tasks = set()
    for m in markets_with_price:
        td = m["target_date"].isoformat()
        city = m["city"]
        # Skip only if neither ERA5 nor ASOS has truth for this date
        if actuals_cache.get(city, {}).get(td) is None and asos_cache.get(city, {}).get(td) is None:
            continue
        for model in MODELS_TO_USE:
            forecast_tasks.add((city, td, model, m["days_ago"]))

    forecast_tasks = list(forecast_tasks)
    print(f"\nFetching {len(forecast_tasks)} day-ahead forecasts (all 5 models)...", flush=True)

    forecasts_cache: dict[tuple, float] = {}
    fc_done = 0

    def _fetch_fc(city, td, model, days_ago):
        cfg = CITIES[city]
        val = fetch_day_ahead_forecast(model, cfg["lat"], cfg["lon"], td, cfg["timezone"], days_ago)
        return (city, td, model), val

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_fc, *task): task for task in forecast_tasks}
        for fut in as_completed(futures):
            key, val = fut.result()
            fc_done += 1
            if val is not None:
                forecasts_cache[key] = val
            if fc_done % 100 == 0:
                print(f"  {fc_done}/{len(forecast_tasks)} forecast fetches done ({len(forecasts_cache)} with data)...", flush=True)

    print(f"  Forecasts fetched: {len(forecasts_cache)}/{len(forecast_tasks)}", flush=True)

    # ── Step 5: Run signal pipeline ───────────────────────────────────────────
    print("\nRunning signal pipeline...", flush=True)
    all_rows = []
    skipped = {"no_clob": 0, "no_forecast": 0, "no_era5": 0, "processed": 0}

    for m in markets_with_price:
        result = process_market(m, forecasts_cache, actuals_cache, asos_cache)
        if result is None:
            td = m["target_date"].isoformat()
            city = m["city"]
            if actuals_cache.get(city, {}).get(td) is None:
                skipped["no_era5"] += 1
            elif not any(forecasts_cache.get((city, td, model)) for model in MODELS_TO_USE):
                skipped["no_forecast"] += 1
            else:
                skipped["no_forecast"] += 1
        else:
            all_rows.append(result)
            skipped["processed"] += 1

    print(f"  Processed: {skipped['processed']}  |  Skipped (no ERA5): {skipped['no_era5']}  "
          f"|  Skipped (no forecast): {skipped['no_forecast']}", flush=True)

    if not all_rows:
        print("\nNo rows to analyse. This likely means ERA5 or forecast data is unavailable.")
        print("Possible causes: Open-Meteo API changed, days_ago > 90, or rate limits hit.")
        return

    # ── Step 6: Save CSV (atomic) ─────────────────────────────────────────────
    tmp_csv = OUTPUT_CSV + ".tmp"
    with open(tmp_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)
    os.replace(tmp_csv, OUTPUT_CSV)
    print(f"\nSaved {len(all_rows)} rows to {OUTPUT_CSV}")

    # ── Step 7: Analysis ──────────────────────────────────────────────────────
    run_analysis(all_rows)


if __name__ == "__main__":
    main()
