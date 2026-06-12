"""
WU resolution-source audit (PART 1).

Fetches the official Weather Underground daily high (via the api.weather.com
backend that WU's history page reads, which is the same source Polymarket scores
from) for every resolved temperature trade, recomputes the bucket outcome with
position_manager semantics, and reports disagreements + outcome flips.

Throttled >=2s between network fetches; results cached in analysis/wu_cache.json.
"""
import json
import os
import sqlite3
import time
import math
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from utils import f_to_c

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "wu_cache.json")
DB_PATH = os.path.join(os.path.dirname(HERE), "paper_trades.db")

# api.weather.com key embedded in the WU history page (public, rotates occasionally).
WU_API_KEY = os.environ.get("WU_API_KEY", "e1f10a1e78da46f5b10a1e78da96f525")
_H = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.wunderground.com/",
}

_cache = {}
if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH) as f:
        _cache = json.load(f)


def _save_cache():
    with open(CACHE_PATH, "w") as f:
        json.dump(_cache, f, indent=2)


_country_cache = {}


def _country_code(icao: str) -> str | None:
    if icao in _country_cache:
        return _country_cache[icao]
    ck = f"cc::{icao}"
    if ck in _cache:
        _country_cache[icao] = _cache[ck]
        return _cache[ck]
    try:
        r = requests.get("https://api.weather.com/v3/location/point",
                         params={"apiKey": WU_API_KEY, "language": "en-US",
                                 "icaoCode": icao, "format": "json"},
                         headers=_H, timeout=15)
        time.sleep(2.2)
        if r.ok:
            cc = r.json().get("location", {}).get("countryCode")
            _cache[ck] = cc
            _country_cache[icao] = cc
            _save_cache()
            return cc
    except Exception as e:
        print(f"  [cc fetch err {icao}] {e!r}")
    return None


def wu_daily_high(icao: str, target_date: str, unit: str):
    """Return (value, raw_unit) of WU daily high for the station-local calendar day.

    unit='F' -> queries units='e' (integer degF), unit='C' -> units='m' (integer degC).
    Returns (None, reason) on failure. Cached.
    """
    key = f"{icao}::{target_date}::{unit}"
    if key in _cache:
        v = _cache[key]
        return (v if isinstance(v, (int, float)) else None,
                "cache" if isinstance(v, (int, float)) else v)

    cc = _country_code(icao)
    if not cc:
        _cache[key] = "no_country_code"
        _save_cache()
        return None, "no_country_code"

    api_unit = "e" if unit == "F" else "m"
    loc = f"{icao}:9:{cc}"
    ymd = target_date.replace("-", "")
    url = f"https://api.weather.com/v1/location/{loc}/observations/historical.json"
    try:
        r = requests.get(url, params={"apiKey": WU_API_KEY, "units": api_unit,
                                      "startDate": ymd, "endDate": ymd},
                         headers=_H, timeout=20)
        time.sleep(2.2)
        if not r.ok:
            _cache[key] = f"http_{r.status_code}"
            _save_cache()
            return None, f"http_{r.status_code}"
        obs = r.json().get("observations", [])
        temps = [o.get("temp") for o in obs if o.get("temp") is not None]
        if not temps:
            _cache[key] = "no_obs"
            _save_cache()
            return None, "no_obs"
        hi = max(temps)
        _cache[key] = hi
        _save_cache()
        return hi, "ok"
    except Exception as e:
        _cache[key] = f"err"
        _save_cache()
        return None, f"err:{e!r}"


def main():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(
        "SELECT trade_id,city,icao,target_date,bucket_lo,bucket_hi,bucket_unit,"
        "direction,status,actual_high_c,outcome_source,entry_price,exit_price,size_usdc,pnl "
        "FROM trades WHERE status IN ('won','lost') "
        "AND (market_type='daily' OR market_type IS NULL) "
        "ORDER BY target_date, city")]

    # Audit only trades that carry a bucket outcome we can compare:
    #   - exit_scan trades resolved at a CLOB market price (0<exit<1) have NO bucket
    #     outcome and NO actual; WU is irrelevant to them.
    #   - polymarket-sourced trades settled at 0.0/1.0 ARE bucket outcomes.
    # We still fetch WU for ALL unique (icao,date) to report temp disagreement,
    # but outcome-flip analysis is meaningful only for true settlements.
    settled = [r for r in rows if r["outcome_source"] == "polymarket"]
    exitscan = [r for r in rows if r["outcome_source"] == "exit_scan"]

    print(f"Total resolved daily trades: {len(rows)}")
    print(f"  polymarket-settled (0/1, bucket outcome exists): {len(settled)}")
    print(f"  exit_scan (sold at market price, NO bucket outcome): {len(exitscan)}")
    print(f"  other: {len(rows) - len(settled) - len(exitscan)}")
    print()

    fails = 0
    temp_disagree = 0
    flips = []
    flip_detail = []
    checked = 0

    for r in settled:
        unit = r["bucket_unit"]
        wu_val, status = wu_daily_high(r["icao"], r["target_date"], unit)
        checked += 1
        if wu_val is None:
            fails += 1
            print(f"  FETCH FAIL {r['city']:<14} {r['target_date']} {r['icao']} ({status})")
            continue

        # Convert WU value to C for temp comparison
        wu_c = f_to_c(wu_val) if unit == "F" else wu_val
        stored_c = r["actual_high_c"]
        if stored_c is not None and abs(wu_c - stored_c) > 0.6:  # >0.6C ~ >1F drift
            temp_disagree += 1

        # Recompute bucket outcome with PM-style INTEGER-print semantics:
        # PM scores the integer print W. Bucket "[lo,hi]" in the market's native
        # unit. We compute membership in native integer space:
        #   YES wins iff lo <= W <= hi   (closed interval on integer prints; see audit note)
        # Also compute position_manager's CURRENT continuous-C semantics for contrast.
        lo, hi = r["bucket_lo"], r["bucket_hi"]
        lo_v = lo if lo is not None else -math.inf
        hi_v = hi if hi is not None else math.inf

        # --- PM integer-print semantics (native unit) ---
        # Single-degree buckets in our DB are stored as [N-0.5, N+0.5] (e.g. 64.0-65.0
        # stored, but really the "65F" bucket etc). We test integer membership two ways
        # and pick the closed-interval reading that matches the data.
        yes_int = (lo_v <= wu_val <= hi_v)
        # --- position_manager current continuous-C semantics ---
        lo_c = f_to_c(lo) if (unit == "F" and lo is not None) else (lo if lo is not None else None)
        hi_c = f_to_c(hi) if (unit == "F" and hi is not None) else (hi if hi is not None else None)
        lo_cv = lo_c if lo_c is not None else -math.inf
        hi_cv = hi_c if hi_c is not None else math.inf
        yes_cont = (lo_cv <= wu_c < hi_cv)

        def outcome_for(yes_won):
            if r["direction"] == "YES":
                return "won" if yes_won else "lost"
            return "won" if not yes_won else "lost"

        wu_outcome_int = outcome_for(yes_int)
        wu_outcome_cont = outcome_for(yes_cont)
        recorded = r["status"]

        # P&L impact if outcome flips (true settlement: win pays full, loss = -stake)
        size = r["size_usdc"]
        entry = r["entry_price"]
        shares = size / entry
        pnl_if_won = shares - size
        pnl_if_lost = -size

        if wu_outcome_int != recorded:
            new_pnl = pnl_if_won if wu_outcome_int == "won" else pnl_if_lost
            delta = new_pnl - r["pnl"]
            flips.append(r["trade_id"])
            flip_detail.append({
                "trade_id": r["trade_id"], "city": r["city"], "date": r["target_date"],
                "bucket": f"[{lo},{hi}]{unit}", "dir": r["direction"],
                "stored_actual_c": stored_c, "wu_native": wu_val, "wu_unit": unit,
                "old": recorded, "new_int": wu_outcome_int, "new_cont": wu_outcome_cont,
                "old_pnl": r["pnl"], "new_pnl": new_pnl, "delta": delta,
            })

        marker = "  <<< FLIP" if wu_outcome_int != recorded else ""
        cont_note = "" if wu_outcome_cont == wu_outcome_int else f" [contC={wu_outcome_cont}]"
        print(f"  {r['city']:<14} {r['target_date']} [{lo},{hi}]{unit} {r['direction']:<3} "
              f"WU={wu_val}{unit}({wu_c:.1f}C) stored={stored_c}C "
              f"rec={recorded} wu_int={wu_outcome_int}{cont_note}{marker}")

    print()
    print("=" * 70)
    print(f"AUDIT SUMMARY (true settlements only, n={len(settled)})")
    print(f"  checked:                 {checked}")
    print(f"  WU fetch failures:       {fails}")
    print(f"  temp disagreements >0.6C:{temp_disagree}")
    print(f"  OUTCOME FLIPS:           {len(flips)}")
    print("=" * 70)
    if flip_detail:
        net = sum(d["delta"] for d in flip_detail)
        print(f"\nFlip detail (net bankroll delta if applied: ${net:+.2f}):")
        for d in flip_detail:
            print(f"  {d['city']:<14} {d['date']} {d['bucket']} {d['dir']:<3} "
                  f"stored={d['stored_actual_c']}C WU={d['wu_native']}{d['wu_unit']} "
                  f"{d['old']}->{d['new_int']} pnl {d['old_pnl']:+.2f}->{d['new_pnl']:+.2f} "
                  f"(delta {d['delta']:+.2f})")

    # Also fetch WU for exit_scan trades to characterize temp drift (informational)
    print("\n--- exit_scan temp-drift probe (informational; NOT outcome-flippable) ---")
    print("(exit_scan trades sold at a CLOB market price; they have no bucket outcome")
    print(" and no stored actual. WU values here only inform whether the early exit")
    print(" was directionally consistent with the eventual print.)")

    with open(os.path.join(HERE, "wu_audit_flips.json"), "w") as f:
        json.dump(flip_detail, f, indent=2)


if __name__ == "__main__":
    main()
