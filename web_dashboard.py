#!/usr/bin/env python3
"""Web dashboard — run: python web_dashboard.py"""
import logging
import os
import subprocess
import time
import threading
import traceback
import uuid
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, render_template
import requests as _req
import db
from metrics.pnl import compute_pnl_summary
from metrics.calibration import compute_calibration
from metrics.sharpe import compute_sharpe

logger = logging.getLogger(__name__)
app = Flask(__name__)

# ── HTTP Basic Auth ────────────────────────────────────────────────────────────
# Set DASHBOARD_USER / DASHBOARD_PASSWORD in .env to require login on every
# route (pages and /api/*). With no password set, the dashboard stays open and
# logs a warning at startup — don't run it that way on a public interface.
import secrets

_AUTH_USER = os.getenv("DASHBOARD_USER", "admin").strip()
_AUTH_PASS = os.getenv("DASHBOARD_PASSWORD", "").strip()


@app.before_request
def _require_auth():
    if not _AUTH_PASS:
        return None
    auth = request.authorization
    if (auth and auth.type == "basic"
            and secrets.compare_digest(auth.username or "", _AUTH_USER)
            and secrets.compare_digest(auth.password or "", _AUTH_PASS)):
        return None
    return (
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Polymarket Bot Dashboard"'},
    )


# ── Response cache ─────────────────────────────────────────────────────────────
_api_cache: dict = {}
_api_lock = threading.Lock()
CACHE_TTL = 20

_slug_cache: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_BOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Empty calibration payload for live Polymarket-only view (bot metrics stay in paper)
_CAL_PLACEHOLDER = {
    "accuracy": 0.0,
    "mean_model_error": 0.0,
    "mean_market_error": 0.0,
    "model_closer_count": 0,
    "n": 0,
}


def _run_job(job_id: str, cmd_flag: str, mode: str = "paper", timeout: int = 600):
    try:
        result = subprocess.run(
            ["python3", "main.py", "--mode", mode, cmd_flag],
            capture_output=True, text=True, timeout=timeout,
            cwd=_BOT_DIR,
        )
        output = (result.stdout + result.stderr).strip()
        _jobs[job_id] = {
            "status": "done" if result.returncode == 0 else "error",
            "output": output[-4000:],
        }
        # Cache keys are "<mode>:<days|all>" — drop every window for this mode
        for k in [k for k in _api_cache if k.split(":")[0] == mode]:
            _api_cache.pop(k, None)
    except subprocess.TimeoutExpired:
        mins = timeout // 60
        _jobs[job_id] = {"status": "error", "output": f"Timed out after {mins} minutes."}
    except Exception as e:
        _jobs[job_id] = {"status": "error", "output": str(e)}


_CMD_TIMEOUT = {"backfill": 3600}

@app.route("/api/run/<cmd>", methods=["POST"])
def run_cmd(cmd):
    allowed = {"scan": "--scan", "resolve": "--resolve", "monitor": "--monitor", "backfill": "--backfill"}
    if cmd not in allowed:
        return jsonify({"error": "unknown command"}), 400
    mode = request.args.get("mode", "paper")
    running_ids = [jid for jid, j in _jobs.items() if j.get("status") == "running" and j.get("cmd") == cmd]
    if running_ids:
        return jsonify({"error": f"{cmd} already running", "job_id": running_ids[0]}), 409
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "running", "output": "", "cmd": cmd}
    timeout = _CMD_TIMEOUT.get(cmd, 600)
    t = threading.Thread(target=_run_job, args=(job_id, allowed[cmd], mode, timeout), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/run/status/<job_id>")
def job_status(job_id):
    return jsonify(_jobs.get(job_id, {"status": "unknown", "output": ""}))


def _get_market_meta(clob_token: str, market_id: str = "") -> dict:
    cache_key = clob_token or market_id
    if cache_key in _slug_cache:
        return _slug_cache[cache_key]
    result = {"slug": "", "event_slug": "", "market_slug": ""}
    # 1. Gamma (works while market is active/indexed)
    if clob_token:
        try:
            r = _req.get("https://gamma-api.polymarket.com/markets",
                         params={"clob_token_ids": clob_token}, timeout=6)
            data = r.json()
            if data:
                m = data[0]
                slug = m.get("slug", "")
                events = m.get("events", [])
                event_slug = events[0].get("slug", "") if events else ""
                result = {"slug": slug, "event_slug": event_slug, "market_slug": slug}
                _slug_cache[cache_key] = result
                return result
        except Exception:
            pass
    # 2. CLOB fallback (works for closed/archived markets)
    if market_id:
        try:
            r = _req.get(f"https://clob.polymarket.com/markets/{market_id}", timeout=6)
            if r.ok:
                data = r.json()
                market_slug = data.get("market_slug", "")
                result = {"slug": market_slug, "event_slug": "", "market_slug": market_slug}
                _slug_cache[cache_key] = result
                return result
        except Exception:
            pass
    return result


def _enrich_trades(trades, db_path: str):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    enriched = []
    try:
        for t in trades:
            row = dict(t)
            if row.get("pm_row"):
                enriched.append(row)
                continue
            m = None
            if t.get("market_id"):
                cur = conn.execute(
                    "SELECT market_id, question, clob_token_yes FROM markets "
                    "WHERE market_id=? LIMIT 1",
                    (t["market_id"],)
                )
                m = cur.fetchone()
            if not m:
                cur = conn.execute(
                    "SELECT market_id, question, clob_token_yes FROM markets "
                    "WHERE city=? AND target_date=? AND bucket_lo IS ? AND bucket_hi IS ? AND bucket_unit=? LIMIT 1",
                    (t["city"], str(t["target_date"]), t["bucket_lo"], t["bucket_hi"], t["bucket_unit"])
                )
                m = cur.fetchone()
            if m:
                row["market_id"] = m["market_id"]
                row["question"] = m["question"]
                row["clob_token_yes"] = m["clob_token_yes"]
            else:
                row.setdefault("market_id", t.get("market_id", ""))
                row.setdefault("question", "")
                row.setdefault("clob_token_yes", "")
            enriched.append(row)
    finally:
        conn.close()
    return enriched


def _build_polymarket_live_dashboard(db_path: str, days: int | None = None) -> dict:
    """
    Entire live view from Polymarket public Data API + CLOB cash (same as UI).

    days: only count positions CLOSED within the last N days toward realized
    stats/history. Cash and open positions are current state — unfiltered.
    """
    from broker.live_broker import (
        get_clob_balance,
        get_clob_positions,
        get_polymarket_closed_positions,
        get_polymarket_positions_value_usd,
        get_proxy_address,
    )

    proxy = get_proxy_address()
    if not proxy:
        raise RuntimeError("POLYMARKET_PROXY_ADDRESS not set in environment (.env)")

    cash = float(get_clob_balance() or 0.0)
    raw_open = get_clob_positions()
    raw_closed = get_polymarket_closed_positions(limit=500)

    if days:
        cutoff_epoch = time.time() - days * 86400
        def _closed_at(p):
            return int(p.get("timestamp") or 0) or int(p.get("closedAt") or 0)
        # Rows the API doesn't date are dropped under a filter — we can't
        # claim they're in the window.
        raw_closed = [p for p in raw_closed if _closed_at(p) >= cutoff_epoch]

    pos_value_api = get_polymarket_positions_value_usd()
    positions_sum = sum(float(p.get("currentValue") or 0) for p in raw_open)
    positions_value = pos_value_api if pos_value_api is not None else positions_sum

    unrealized = sum(float(p.get("cashPnl") or 0) for p in raw_open)
    realized = sum(float(p.get("realizedPnl") or 0) for p in raw_closed)
    total_pnl = unrealized + realized

    portfolio_value = cash + positions_value
    cost_basis = max(0.01, portfolio_value - total_pnl)
    pct_return = (total_pnl / cost_basis) * 100.0

    realized_list = [float(p.get("realizedPnl") or 0) for p in raw_closed]
    wins_list = [x for x in realized_list if x > 0]
    losses_list = [x for x in realized_list if x < 0]
    n_resolved = len(raw_closed)
    n_wins = len(wins_list)
    n_losses = len(losses_list)

    rows_open = []
    for i, p in enumerate(raw_open):
        tid = f"pm-open-{p.get('conditionId', '')[:20]}-{i}"
        rows_open.append({
            "trade_id": tid,
            "market_id": p.get("conditionId", ""),
            "city": (p.get("title") or "Market")[:100],
            "target_date": str(p.get("endDate") or "")[:16],
            "bucket_lo": None,
            "bucket_hi": None,
            "bucket_unit": "PM",
            "direction": p.get("outcome", "—"),
            "entry_price": float(p.get("avgPrice") or 0),
            "size_usdc": float(p.get("currentValue") or 0),
            "model_prob": float(p.get("curPrice") or 0),
            "market_prob": float(p.get("curPrice") or 0),
            "edge": float(p.get("cashPnl") or 0),
            "question": p.get("title", ""),
            "clob_token_yes": str(p.get("asset") or ""),
            "pm_row": True,
            "pm_initial": float(p.get("initialValue") or 0),
        })

    closed_sorted = sorted(
        raw_closed,
        key=lambda x: (
            int(x.get("timestamp") or 0)
            or int(x.get("closedAt") or 0)
            or str(x.get("endDate") or "")
        ),
        reverse=True,
    )
    rows_closed = []
    for i, p in enumerate(closed_sorted):
        rp = float(p.get("realizedPnl") or 0)
        tid = f"pm-closed-{p.get('conditionId', '')[:20]}-{i}"
        rows_closed.append({
            "trade_id": tid,
            "city": (p.get("title") or "Market")[:100],
            "target_date": str(p.get("endDate") or "")[:16],
            "bucket_lo": None,
            "bucket_hi": None,
            "bucket_unit": "PM",
            "direction": p.get("outcome", "—"),
            "entry_price": float(p.get("avgPrice") or 0),
            "size_usdc": float(p.get("totalBought") or 0),
            "model_prob": 0.0,
            "market_prob": 0.0,
            "edge": 0.0,
            "pnl": rp,
            "status": "won" if rp >= 0 else "lost",
            "actual_high_c": None,
            "question": p.get("title", ""),
            "clob_token_yes": str(p.get("asset") or ""),
            "pm_row": True,
        })

    pnl = {
        "bankroll": cash,
        "cash": cash,
        "deployed": positions_value,
        "positions_value": positions_value,
        "portfolio_value": portfolio_value,
        "available": cash,
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "total_pnl": total_pnl,
        "pct_return": pct_return,
        "n_resolved": n_resolved,
        "n_open": len(raw_open),
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": (n_wins / n_resolved * 100.0) if n_resolved else 0.0,
        "avg_win": sum(wins_list) / len(wins_list) if wins_list else 0.0,
        "avg_loss": sum(losses_list) / len(losses_list) if losses_list else 0.0,
    }

    db.set_mode("live")
    all_biases = db.get_all_biases_batch()
    stations_raw = db.get_all_stations()
    stations = []
    for s in sorted(stations_raw, key=lambda x: x["city"]):
        biases = all_biases.get(s["icao"], [])
        n_b = len(biases)
        avg_b = sum(abs(b["bias_c"]) for b in biases) / n_b if biases else None
        stations.append({
            "city": s["city"],
            "icao": s["icao"],
            "status": s["status"],
            "history_days": s["history_days"],
            "avg_bias": avg_b,
        })

    from ops_state import get_ops_snapshot
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": "live",
        "db_file": os.path.basename(db_path),
        "live_pm_ui": True,
        "data_source": "polymarket",
        "range_days": days,
        "open_count": len(rows_open),
        "history_count": len(rows_closed),
        "pnl": pnl,
        "cal": _CAL_PLACEHOLDER,
        "sharpe": None,
        "positions": rows_open,
        "history": rows_closed,
        "stations": stations,
        "ops": get_ops_snapshot(),
        "pnl_history": _pnl_history_with_realized(_since_iso(days)),
    }


def _pnl_history_with_realized(since: str | None = None) -> list[dict]:
    """daily_pnl rows annotated with cumulative realized P&L from resolved trades.

    The chart previously plotted ending_bankroll minus the first row's
    starting_bankroll as "Cum PnL" — but bankroll is cash, which swings with
    stake deployment, and the first snapshot was taken mid-deployment, so the
    line overstated profit. cum_realized is the true profit curve.

    since: full ISO timestamp — drop day-rows before its date and restart the
    cumulative sum at the window start (timestamp-exact, so sub-day windows
    agree with the timestamp-filtered summary numbers).
    """
    rows = db.get_daily_pnl()
    daily = db.get_daily_realized_pnl(since=since)
    if since:
        rows = [r for r in rows if r["pnl_date"] >= since[:10]]
    dates = sorted(daily)
    cum, i = 0.0, 0
    for row in rows:
        while i < len(dates) and dates[i] <= row["pnl_date"]:
            cum += daily[dates[i]]
            i += 1
        row["cum_realized"] = round(cum, 2)
    return rows


def _since_iso(days: int | None) -> str | None:
    """UTC ISO cutoff for an N-day window, or None for no filter."""
    if not days:
        return None
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _build_data(mode: str, days: int | None = None) -> dict:
    db.set_mode(mode)
    current_path = db.DB_PATH

    if mode == "live":
        return _build_polymarket_live_dashboard(current_path, days=days)

    since = _since_iso(days)
    pnl = compute_pnl_summary(since=since)
    cal = compute_calibration(since=since)
    sharpe = compute_sharpe(since=since)
    open_trades_raw = db.get_open_trades()
    all_trades = db.get_all_trades()
    history_raw = [t for t in all_trades if t["status"] in ("won", "lost", "stop_loss")]
    if since:
        history_raw = [t for t in history_raw if (t.get("resolved_at") or "") >= since]
    trades = _enrich_trades(open_trades_raw, current_path)
    history = _enrich_trades(history_raw, current_path)
    # Most-recently-CLOSED first. get_all_trades() orders by entry_time, but the
    # history tab wants resolution order (resolved_at); fall back to entry_time
    # for any row missing a close timestamp (ISO strings sort lexicographically).
    history.sort(key=lambda t: (t.get("resolved_at") or t.get("entry_time") or ""), reverse=True)

    live_prices = db.get_latest_prices_for_markets([t["market_id"] for t in trades if t.get("market_id")])
    for t in trades:
        info = live_prices.get(t.get("market_id", ""))
        if info:
            yes_mid, scanned_at = info
            cur = yes_mid if t["direction"] == "YES" else (1.0 - yes_mid)
            shares = t["size_usdc"] / t["entry_price"] if t["entry_price"] else 0
            t["current_price"] = round(cur, 4)
            t["unreal_pnl"] = round(shares * cur - t["size_usdc"], 2)
            t["price_age"] = scanned_at
        else:
            t["current_price"] = None
            t["unreal_pnl"] = None
            t["price_age"] = None

    # Mark-to-market summary from the per-row figures above. Trades with no
    # recent price are carried at cost (unrealized 0) rather than excluded.
    priced = [t for t in trades if t.get("unreal_pnl") is not None]
    pnl["unrealized_pnl"] = round(sum(t["unreal_pnl"] for t in priced), 2)
    pnl["unpriced_open"] = len(trades) - len(priced)

    all_biases = db.get_all_biases_batch()
    stations_raw = db.get_all_stations()
    stations = []
    for s in sorted(stations_raw, key=lambda x: x["city"]):
        biases = all_biases.get(s["icao"], [])
        n_b = len(biases)
        avg_b = sum(abs(b["bias_c"]) for b in biases) / n_b if biases else None
        stations.append({
            "city": s["city"],
            "icao": s["icao"],
            "status": s["status"],
            "history_days": s["history_days"],
            "avg_bias": avg_b,
        })

    from ops_state import get_ops_snapshot
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": mode,
        "db_file": os.path.basename(current_path),
        "live_pm_ui": False,
        "range_days": days,
        "open_count": len(open_trades_raw),
        "history_count": len(history_raw),
        "pnl": pnl,
        "cal": cal,
        "sharpe": sharpe,
        "positions": trades,
        "history": history,
        "stations": stations,
        "ops": get_ops_snapshot(),
        "pnl_history": _pnl_history_with_realized(since),
    }


@app.route("/api/data")
def api_data():
    mode = request.args.get("mode", "paper")
    try:
        days = int(request.args.get("days", "") or 0) or None
    except ValueError:
        days = None
    cache_key = f"{mode}:{days or 'all'}"
    now = time.time()
    force = request.args.get("force", "") == "1"

    if not force:
        cached = _api_cache.get(cache_key)
        if cached and (now - cached["ts"]) < CACHE_TTL:
            return jsonify(cached["data"])

    with _api_lock:
        if not force:
            cached = _api_cache.get(cache_key)
            if cached and (now - cached["ts"]) < CACHE_TTL:
                return jsonify(cached["data"])

        try:
            data = _build_data(mode, days=days)
            _api_cache[cache_key] = {"ts": now, "data": data}
            return jsonify(data)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("api_data(%s) error: %s\n%s", cache_key, e, tb)
            stale = _api_cache.get(cache_key)
            if stale:
                d = dict(stale["data"])
                d["stale"] = True
                d["stale_error"] = str(e)
                return jsonify(d)
            return jsonify({"error": str(e), "traceback": tb}), 500


# ── Position outlook ───────────────────────────────────────────────────────────
# Automates the manual loop: open position → check hourly forecast → does the
# day's max hit the bucket, and which hour gets closest?
_outlook_cache: dict[str, dict] = {}
_OUTLOOK_TTL = 900  # hourly forecasts update slowly; 15 min is plenty
_obs_cache: dict[str, dict] = {}
_OBS_TTL = 300      # live obs move faster, but ASOS rate-limits aggressive polling


def _c_to_unit(c: float, unit: str) -> float:
    return c * 9 / 5 + 32 if unit == "F" else c


def _bucket_distance(temp: float, lo, hi) -> float:
    """Signed distance from temp to the bucket [lo, hi]. 0 = inside.
    Negative = below lo (need warmer), positive = above hi (overshot)."""
    if lo is not None and temp < lo:
        return temp - lo
    if hi is not None and temp > hi:
        return temp - hi
    return 0.0


@app.route("/api/outlook/<trade_id>")
def position_outlook(trade_id):
    try:
        db.set_mode(request.args.get("mode", "paper"))
        trade = db.get_trade(trade_id)
        if not trade:
            return jsonify({"error": "trade not found"}), 404
        # Temperature markets are typed 'daily' (legacy) or 'temperature';
        # only TSA/crypto have no hourly-temp outlook.
        if (trade.get("market_type") or "") in ("tsa", "crypto"):
            return jsonify({"error": "outlook only for temperature markets"}), 400

        from config_active import CITIES
        cfg = CITIES.get(trade["city"])
        if not cfg:
            return jsonify({"error": f"no city config for {trade['city']}"}), 400

        target_date = str(trade["target_date"])
        unit = trade.get("bucket_unit") or ("F" if cfg.get("uses_fahrenheit") else "C")
        cache_key = f"{trade['city']}:{target_date}:{unit}"
        now = time.time()
        cached = _outlook_cache.get(cache_key)
        if cached and now - cached["ts"] < _OUTLOOK_TTL:
            body = dict(cached["data"])
        else:
            # Prefer the WU/TWC forecast — it's what readers of the resolution
            # page see, so the projected high matches theirs. Fall back to
            # Open-Meteo when TWC is unavailable (or for far-out dates).
            hourly, fc_source = None, None
            try:
                from data.wunderground import get_hourly_forecast_native
                hourly = get_hourly_forecast_native(cfg["icao"], target_date, unit)
                hourly = [{"time": h["time"], "temp": round(h["temp"], 1)} for h in hourly]
                fc_source = "WU"
            except Exception as e:
                logger.info("TWC forecast unavailable for %s (%s) — using Open-Meteo",
                            trade["city"], e)
            if not hourly:
                from data.openmeteo import fetch_hourly_temps
                hourly_raw = fetch_hourly_temps(cfg["lat"], cfg["lon"], target_date,
                                                cfg["timezone"])
                if not hourly_raw:
                    return jsonify({"error": "no hourly forecast available"}), 502
                hourly = [{"time": h["time"][11:16], "temp": round(_c_to_unit(h["temp_c"], unit), 1)}
                          for h in hourly_raw]
                fc_source = "Open-Meteo"
            peak = max(hourly, key=lambda h: h["temp"])
            body = {"hourly": hourly, "peak": peak, "unit": unit, "fc_source": fc_source}
            _outlook_cache[cache_key] = {"ts": now, "data": body}

        lo, hi = trade.get("bucket_lo"), trade.get("bucket_hi")
        peak = body["peak"]
        hourly = body["hourly"]

        # Live observed running max (only meaningful for today, local time).
        # Cached separately: obs move faster than forecasts, but ASOS 429s
        # aggressive polling. fresh=1 (modal click) bypasses the cache so the
        # WU number is read at that moment.
        obs = None
        fresh = request.args.get("fresh", "") == "1"
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(cfg["timezone"])
            today_local = datetime.now(tz).date().isoformat()
            if target_date == today_local:
                oc = _obs_cache.get(trade["city"])
                if oc and now - oc["ts"] < _OBS_TTL and not fresh:
                    obs_c = oc["data"]
                else:
                    from signals.nowcaster import get_running_max_c
                    max_c, rate = get_running_max_c(trade["city"])
                    # WU is what Polymarket resolves from. The page's intraday
                    # High is the CONTINUOUS sensor max (since-7am field), not
                    # the hourly obs table — get_today_max_native combines both.
                    # Page-scrape fallback for when the backend misbehaves.
                    wu_native = None
                    try:
                        from data.wunderground import get_today_max_native
                        wu_native = get_today_max_native(cfg["icao"], today_local, unit)
                    except Exception as wu_err:
                        logger.debug("WU backend obs failed for %s: %s", cfg["icao"], wu_err)
                    if wu_native is None:
                        try:
                            from data.wunderground import get_running_max_wu
                            wu_c = get_running_max_wu(cfg["icao"])
                            if wu_c is not None:
                                wu_native = _c_to_unit(wu_c, unit)
                        except Exception:
                            pass
                    obs_c = ({"max_c": max_c, "rate": rate, "wu_native": wu_native,
                              "asof": datetime.now(tz).strftime("%H:%M")}
                             if (max_c is not None or wu_native is not None) else None)
                    _obs_cache[trade["city"]] = {"ts": now, "data": obs_c}
                if obs_c:
                    obs = {"asof": obs_c.get("asof")}
                    if obs_c.get("max_c") is not None:
                        obs["max"] = round(_c_to_unit(obs_c["max_c"], unit), 1)
                        obs["rate_c_per_h"] = (round(obs_c["rate"], 2)
                                               if obs_c.get("rate") is not None else None)
                    if obs_c.get("wu_native") is not None:
                        obs["wu_max"] = round(obs_c["wu_native"], 1)
                    if obs.get("max") is not None and obs.get("wu_max") is not None:
                        obs["disagree"] = abs(obs["max"] - obs["wu_max"]) >= 1.0
        except Exception as e:
            logger.debug("outlook obs fetch failed for %s: %s", trade["city"], e)

        # Verdict on the best estimate of the day's max: forecast peak, or an
        # observed running max if reality has already outrun the forecast.
        # WU's number counts double here — it's the resolution source.
        day_max = peak["temp"]
        max_source = "forecast"
        if obs and obs.get("max") is not None and obs["max"] > day_max:
            day_max = obs["max"]
            max_source = "observed"
        if obs and obs.get("wu_max") is not None and obs["wu_max"] > day_max:
            day_max = obs["wu_max"]
            max_source = "observed_wu"
        peak_dist = _bucket_distance(day_max, lo, hi)
        verdict = "HIT" if peak_dist == 0 else ("MISS_BELOW" if peak_dist < 0 else "MISS_ABOVE")
        direction = trade.get("direction", "NO")
        favorable = (verdict == "HIT") == (direction == "YES")

        # Closest approach: the hour whose temp is nearest the bucket — the
        # time of day worth monitoring. On a HIT, this is the first hour inside.
        closest = min(hourly, key=lambda h: abs(_bucket_distance(h["temp"], lo, hi)))

        return jsonify({
            "city": trade["city"],
            "target_date": target_date,
            "direction": direction,
            "bucket": {"lo": lo, "hi": hi, "unit": body["unit"]},
            "peak": peak,
            "fc_source": body.get("fc_source", "Open-Meteo"),
            "day_max": round(day_max, 1),
            "max_source": max_source,
            "verdict": verdict,
            "favorable": favorable,
            "peak_margin": round(peak_dist, 1),
            "closest": {**closest,
                        "dist": round(_bucket_distance(closest["temp"], lo, hi), 1)},
            "obs": obs,
            "hourly": hourly,
        })
    except Exception as e:
        logger.error("outlook(%s) error: %s", trade_id[:8], e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/pnl-history")
def pnl_history():
    try:
        db.set_mode(request.args.get("mode", "paper"))
        try:
            days = int(request.args.get("days", "") or 0) or None
        except ValueError:
            days = None
        return jsonify(_pnl_history_with_realized(_since_iso(days)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/price-history")
def price_history():
    token = request.args.get("token", "")
    if not token:
        return jsonify({"error": "no token"}), 400
    try:
        r = _req.get("https://clob.polymarket.com/prices-history",
                     params={"market": token, "interval": "max", "fidelity": 60}, timeout=8)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/market-meta")
def market_meta():
    token = request.args.get("token", "")
    market_id = request.args.get("market_id", "")
    if not token and not market_id:
        return jsonify({}), 400
    return jsonify(_get_market_meta(token, market_id))


@app.route("/api/clob-balance")
def clob_balance():
    try:
        from broker.live_broker import get_clob_balance
        bal = get_clob_balance()
        return jsonify({"balance": bal})
    except Exception as e:
        return jsonify({"balance": None, "error": str(e)})


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    db.init_db()
    print("\n  Dashboard → http://localhost:5050\n")
    if _AUTH_PASS:
        print(f"  Auth: HTTP Basic enabled (user: {_AUTH_USER})\n")
    else:
        print("  ⚠ WARNING: no DASHBOARD_PASSWORD set in .env — dashboard is "
              "OPEN to anyone who can reach this host on port 5050.\n")
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
