"""
Position manager — resolves open trades against actual temperature outcomes.

Resolution strategy (two independent steps):

  Step 1 — WIN/LOSS (outcome):
    Query Polymarket's Gamma API and use their winner field only.
    If Polymarket has not resolved yet, the trade remains open/pending.

  Step 2 — ACTUAL TEMPERATURE (bias correction only):
    Fetch the real temperature from weather sources regardless of Step 1.
    This value is stored in actual_high_c and feeds back into model bias
    correction — it does NOT affect win/loss when Step 1 succeeds.
    Priority: Wunderground (Polymarket's source) → ASOS → ERA5 archive.

When Polymarket itself can't be queried (paper-mode, market dropped from index),
_weather_fallback_outcome scores the bucket directly from the WU high, matching
Polymarket's bucket semantics: the INTEGER print in the market's NATIVE unit, with
membership CLOSED-CLOSED — YES wins iff bucket_lo <= round(high_native) <= bucket_hi.
(Validated against 18/19 resolved PM settlements, 2026-06; the prior continuous-°C
exclusive-upper comparison mis-scored upper-edge prints like 65°F in a 64-65°F market.)
"""
import logging
import requests as _req
from datetime import date, timedelta
from data.wunderground import get_historical_high, get_historical_high_native, WundergroundError
from data.noaa import fetch_asos_daily_max
from data.openmeteo import fetch_historical_actuals
from config_active import CITIES
import db
from telegram import send_trade_event

logger = logging.getLogger(__name__)

# Cities where Polymarket resolves via ASOS/NOAA directly (not Wunderground)
_ASOS_PRIMARY_CITIES = {"Tel Aviv"}

_GAMMA_API = "https://gamma-api.polymarket.com/markets"
_CLOB_API  = "https://clob.polymarket.com"
_DATA_API  = "https://data-api.polymarket.com"


def _query_polymarket_outcome(clob_token_yes: str, market_id: str = "") -> str | None:
    """
    Determine market outcome from Polymarket APIs. Returns 'yes' | 'no' | None.

    Resolution cascade:
      1. Gamma /markets?clob_token_ids=... — works while Gamma still indexes the market
      2. CLOB  /markets/{condition_id}    — works after Gamma drops the market;
                                            tokens[].winner is authoritative
    """
    # ── 1. Gamma ────────────────────────────────────────────────────────────
    if clob_token_yes:
        try:
            resp = _req.get(_GAMMA_API, params={"clob_token_ids": clob_token_yes}, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            if data:
                m = data[0]
                if m.get("resolved"):
                    winner = (m.get("winner") or "").strip().lower()
                    if winner in ("yes", "no"):
                        logger.info("Gamma resolved: winner=%s", winner)
                        return winner
        except Exception as e:
            logger.warning("Gamma outcome query failed: %s", e)

    # ── 2. CLOB /markets/{condition_id} ─────────────────────────────────────
    if market_id:
        try:
            resp = _req.get(f"{_CLOB_API}/markets/{market_id}", timeout=8)
            if resp.ok:
                tokens = resp.json().get("tokens", [])
                for token in tokens:
                    if token.get("winner") is True:
                        outcome = token.get("outcome", "").lower()
                        if outcome in ("yes", "no"):
                            logger.info("CLOB resolved: winner=%s (condition_id=%s...)",
                                        outcome, market_id[:12])
                            return outcome
        except Exception as e:
            logger.warning("CLOB market query failed for %s: %s", market_id[:16], e)

    return None


def _yes_won_native(high_native: float, bucket_lo, bucket_hi) -> bool:
    """Polymarket bucket membership on the INTEGER print in the market's NATIVE unit.

    PM scores the integer high WU shows and asks e.g. "be 26°C" (single int) or
    "between 74-75°F" (a 2-degree inclusive range). Validated against 18/19 resolved
    PM settlements (2026-06): membership is CLOSED-CLOSED on the rounded native print:
        YES wins iff  bucket_lo <= round(high_native) <= bucket_hi
    Open / unbounded edges (None) extend to ±inf. The old continuous-°C exclusive-upper
    comparison mis-scored upper-edge prints (e.g. 65°F in a 64-65°F market) — see
    data/wunderground.py docstring.
    """
    import math
    w = round(high_native)
    lo = bucket_lo if bucket_lo is not None else -math.inf
    hi = bucket_hi if bucket_hi is not None else math.inf
    return lo <= w <= hi


def _weather_fallback_outcome(icao: str, target_date: str, city: str,
                              bucket_lo, bucket_hi, bucket_unit: str) -> str | None:
    """
    Paper-mode fallback: determine YES/NO from actual temperature when Gamma
    has dropped the market from its index. Mirrors Polymarket's own bucket math
    exactly (integer print in the market's native unit, closed-closed interval).
    Returns 'yes' | 'no' | None (if temp fetch fails).
    """
    from utils import c_to_f
    native_unit = "F" if str(bucket_unit).upper().startswith("F") else "C"
    try:
        # Fetch the actual high in the market's NATIVE unit so the integer print
        # matches what Polymarket scores. get_actual_high_c also stores the °C value
        # for bias correction; we re-derive the native print from its source.
        high_native, src = get_actual_high_native(icao, target_date, city, native_unit)
        yes_won = _yes_won_native(high_native, bucket_lo, bucket_hi)
        logger.info(
            "Weather fallback %s %s: actual=%s°%s (src=%s) bucket=[%s,%s]%s → YES_won=%s",
            city, target_date, round(high_native), native_unit, src,
            bucket_lo if bucket_lo is not None else "-inf",
            bucket_hi if bucket_hi is not None else "+inf",
            bucket_unit, yes_won,
        )
        return "yes" if yes_won else "no"
    except Exception as e:
        logger.warning("Weather fallback failed for %s %s: %s", city, target_date, e)
        return None


def _query_outcome_via_data_api(clob_token_yes: str, market_id: str) -> str | None:
    """
    Fallback resolution via Polymarket Data API — for markets Gamma no longer indexes.
    Only works in live mode (requires a real proxy wallet with actual positions).

    Resolution logic:
      - Losing YES token remains in /positions with currentPrice ≈ 0  → NO won
      - Winning YES token appears in /positions?redeemable=true         → YES won
      - Same conditionId, different token in redeemable                 → NO won

    Returns 'yes' | 'no' | None.
    """
    try:
        from broker.live_broker import get_proxy_address
    except ImportError:
        return None

    proxy = get_proxy_address()
    if not proxy:
        return None

    import requests as _r2

    # Step A: check all current positions — losing tokens linger at price ≈ 0
    try:
        r = _r2.get(
            f"{_DATA_API}/positions",
            params={"user": proxy, "sizeThreshold": 0.001},
            timeout=12,
        )
        if r.ok:
            for p in (r.json() if isinstance(r.json(), list) else []):
                if p.get("asset") == clob_token_yes:
                    price = float(p.get("currentPrice") or 0.5)
                    if price <= 0.01:
                        logger.info("Data API positions: YES price=%.4f → NO won", price)
                        return "no"
                    if price >= 0.99:
                        logger.info("Data API positions: YES price=%.4f → YES won", price)
                        return "yes"
                    return None  # Market still active
    except Exception as e:
        logger.warning("Data API positions check failed: %s", e)

    # Step B: check redeemable positions — winning tokens before auto-redemption
    try:
        r2 = _r2.get(
            f"{_DATA_API}/positions",
            params={"user": proxy, "sizeThreshold": 0.001, "redeemable": "true"},
            timeout=12,
        )
        if r2.ok:
            for p in (r2.json() if isinstance(r2.json(), list) else []):
                if p.get("asset") == clob_token_yes:
                    logger.info("Data API redeemable: YES token present → YES won")
                    return "yes"
                if market_id and p.get("conditionId") == market_id:
                    logger.info("Data API redeemable: NO token present (conditionId match) → NO won")
                    return "no"
    except Exception as e:
        logger.warning("Data API redeemable check failed: %s", e)

    return None


def _get_clob_token(trade: dict) -> str:
    """
    Return the YES CLOB token for a trade.
    Uses trade["clob_token_yes"] when populated (new trades); falls back to
    a markets-table lookup for older trades that pre-date the column.
    """
    token = (trade.get("clob_token_yes") or "").strip()
    if token:
        return token

    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT clob_token_yes FROM markets
        WHERE city=? AND target_date=?
          AND (bucket_lo IS ? OR (bucket_lo IS NULL AND ? IS NULL))
          AND (bucket_hi IS ? OR (bucket_hi IS NULL AND ? IS NULL))
        LIMIT 1
    """, (trade["city"], str(trade["target_date"]),
          trade["bucket_lo"], trade["bucket_lo"],
          trade["bucket_hi"], trade["bucket_hi"])).fetchone()
    conn.close()
    return row["clob_token_yes"] if row else ""


def get_actual_high_c(icao: str, target_date: str, city_name: str) -> tuple[float, str]:
    """
    Get actual daily high temperature for a station/date.
    Returns (temp_c, source_name).
    Raises RuntimeError if all sources fail.

    Priority matches Polymarket's stated resolution source per city:
      - Most cities: Wunderground first (Polymarket's primary source)
      - Tel Aviv: ASOS first (Polymarket uses NOAA/ASOS for LLBG)
      - Hong Kong: falls to ERA5 (HK Observatory not directly fetchable)
    """
    cfg = CITIES.get(city_name, {})

    if city_name in _ASOS_PRIMARY_CITIES:
        # --- ASOS-primary path (Tel Aviv / NOAA) ---
        asos = cfg.get("asos_station", icao)
        try:
            daily_max = fetch_asos_daily_max(asos, target_date, target_date)
            if target_date in daily_max:
                high_c = daily_max[target_date]
                logger.info("Resolution %s %s: %.1f°C (ASOS)", icao, target_date, high_c)
                return high_c, "asos"
        except Exception as e:
            logger.warning("ASOS failed for %s %s: %s — trying WU", icao, target_date, e)

        try:
            high_c = get_historical_high(icao, target_date)
            logger.info("Resolution %s %s: %.1f°C (WU fallback)", icao, target_date, high_c)
            return high_c, "wunderground"
        except WundergroundError as e:
            logger.warning("WU failed for %s %s: %s — trying archive", icao, target_date, e)

    else:
        # --- Wunderground-primary path (all other cities — matches Polymarket) ---
        try:
            high_c = get_historical_high(icao, target_date)
            logger.info("Resolution %s %s: %.1f°C (Wunderground)", icao, target_date, high_c)
            return high_c, "wunderground"
        except WundergroundError as e:
            logger.warning("WU failed for %s %s: %s — trying ASOS", icao, target_date, e)

        asos = cfg.get("asos_station", icao)
        try:
            daily_max = fetch_asos_daily_max(asos, target_date, target_date)
            if target_date in daily_max:
                high_c = daily_max[target_date]
                logger.info("Resolution %s %s: %.1f°C (ASOS fallback)", icao, target_date, high_c)
                return high_c, "asos"
        except Exception as e:
            logger.warning("ASOS failed for %s %s: %s — trying archive", icao, target_date, e)

    # Final fallback: ERA5 archive (Hong Kong and last resort for all cities)
    try:
        tz = cfg.get("timezone", "UTC")
        actuals = fetch_historical_actuals(cfg["lat"], cfg["lon"], target_date, target_date, tz)
        if target_date in actuals:
            high_c = actuals[target_date]
            logger.info("Resolution %s %s: %.1f°C (ERA5 archive)", icao, target_date, high_c)
            return high_c, "openmeteo_archive"
    except Exception as e:
        logger.warning("Archive failed for %s %s: %s", icao, target_date, e)

    raise RuntimeError(
        f"All resolution sources failed for {icao} {target_date}. "
        f"Cannot resolve trade. Skipping."
    )


def get_actual_high_native(icao: str, target_date: str, city_name: str,
                           native_unit: str) -> tuple[float, str]:
    """
    Get the actual daily high in the market's NATIVE unit ('F' or 'C') so the
    integer print matches what Polymarket scores.

    Source priority mirrors get_actual_high_c (WU first for most cities, ASOS first
    for Tel Aviv, ERA5 last). WU returns the native integer print directly; ASOS/ERA5
    return °C, which we convert to the native unit (rounding happens at comparison).
    Raises RuntimeError if all sources fail.
    """
    from utils import c_to_f
    cfg = CITIES.get(city_name, {})
    want_f = str(native_unit).upper().startswith("F")

    def _wu_native():
        return get_historical_high_native(icao, target_date, "F" if want_f else "C"), "wunderground"

    def _asos_native():
        asos = cfg.get("asos_station", icao)
        daily_max = fetch_asos_daily_max(asos, target_date, target_date)
        if target_date in daily_max:
            c = daily_max[target_date]
            return (c_to_f(c) if want_f else c), "asos"
        raise WundergroundError("asos no data")

    def _era5_native():
        tz = cfg.get("timezone", "UTC")
        actuals = fetch_historical_actuals(cfg["lat"], cfg["lon"], target_date, target_date, tz)
        if target_date in actuals:
            c = actuals[target_date]
            return (c_to_f(c) if want_f else c), "openmeteo_archive"
        raise WundergroundError("era5 no data")

    order = ([_asos_native, _wu_native, _era5_native]
             if city_name in _ASOS_PRIMARY_CITIES
             else [_wu_native, _asos_native, _era5_native])

    for fn in order:
        try:
            val, src = fn()
            logger.info("Resolution(native) %s %s: %.2f°%s (%s)",
                        icao, target_date, val, "F" if want_f else "C", src)
            return val, src
        except Exception as e:
            logger.warning("native source failed for %s %s: %s", icao, target_date, e)

    raise RuntimeError(
        f"All native resolution sources failed for {icao} {target_date}."
    )


def resolve_expired_trades(dry_run: bool = False) -> list[dict]:
    """
    Find all open trades whose target_date has passed and resolve them.

    Win/loss is determined by Polymarket's own resolution (ground truth).
    Actual temperature is fetched separately for bias correction purposes only.
    """
    today = date.today().isoformat()

    # ── Re-check previously weather-fallback-resolved trades ─────────────────
    # Polymarket typically settles 1-2 days after the event. Trades that were
    # resolved via weather data earlier may now have an official PM resolution.
    weather_fallback_trades = db.get_weather_fallback_trades()
    for trade in weather_fallback_trades:
        clob_token = _get_clob_token(trade)
        pm_winner = _query_polymarket_outcome(clob_token, trade.get("market_id", ""))
        if pm_winner is None:
            continue
        yes_won = (pm_winner == "yes")
        direction = trade["direction"]
        new_outcome = ("won" if yes_won else "lost") if direction == "YES" else ("won" if not yes_won else "lost")
        logger.info("PM re-check corrected %s: weather_fallback → polymarket (%s → %s)",
                    trade["trade_id"][:8], trade.get("status"), new_outcome)
        if not dry_run:
            db.update_trade_outcome(trade["trade_id"], new_outcome, "polymarket",
                                    actual_high_c=trade.get("actual_high_c"))
        else:
            logger.info("[DRY RUN] Would correct trade %s: %s → %s",
                        trade["trade_id"][:8], trade.get("status"), new_outcome)

    # ── Re-check exit-scan trades settled at entry_price (no-price fallback) ─
    # When the CLOB orderbook is gone near resolution, exit_scan records the trade
    # at entry_price (pnl=0). Once PM settles we can correct to the real 1.0/0.0.
    exit_scan_fallback_trades = db.get_exit_scan_fallback_trades()
    for trade in exit_scan_fallback_trades:
        clob_token = _get_clob_token(trade)
        pm_winner = _query_polymarket_outcome(clob_token, trade.get("market_id", ""))
        if pm_winner is None:
            continue
        yes_won = (pm_winner == "yes")
        direction = trade["direction"]
        new_outcome = ("won" if yes_won else "lost") if direction == "YES" else ("won" if not yes_won else "lost")
        logger.info("PM re-check corrected %s: exit_scan fallback → polymarket (%s → %s)",
                    trade["trade_id"][:8], trade.get("status"), new_outcome)
        if not dry_run:
            db.update_trade_outcome(trade["trade_id"], new_outcome, "polymarket",
                                    actual_high_c=trade.get("actual_high_c"))
        else:
            logger.info("[DRY RUN] Would correct trade %s: %s → %s",
                        trade["trade_id"][:8], trade.get("status"), new_outcome)

    open_trades = db.get_open_trades()
    expired = [t for t in open_trades if str(t["target_date"]) < today]

    if not expired:
        logger.info("No expired trades to resolve.")
        return []

    logger.info("Resolving %d expired trades...", len(expired))
    results = []

    for trade in expired:
        icao        = trade["icao"]
        city        = trade["city"]
        target_date = str(trade["target_date"])
        direction   = trade["direction"]
        bucket_lo   = trade["bucket_lo"]
        bucket_hi   = trade["bucket_hi"]
        bucket_unit = trade["bucket_unit"]
        size        = trade["size_usdc"]

        # ── Step 1: ask Polymarket who won ───────────────────────────────────
        # Resolution cascade (same for both modes):
        #   Gamma → CLOB /markets/{condition_id} → Data API (live) / weather (paper)
        market_id  = trade.get("market_id", "")
        clob_token = _get_clob_token(trade)
        pm_winner  = _query_polymarket_outcome(clob_token, market_id)  # 'yes' | 'no' | None

        outcome_source = "polymarket"
        if pm_winner is not None:
            # Check whether CLOB was the source (Gamma would have returned it directly)
            pass  # outcome_source stays "polymarket" for both Gamma and CLOB paths

        # If Gamma+CLOB both failed, try Data API positions (live) or weather (paper)
        if pm_winner is None and db.get_mode() == "live":
            pm_winner = _query_outcome_via_data_api(clob_token, market_id)
            if pm_winner is not None:
                outcome_source = "data_api"

        if pm_winner is None and db.get_mode() == "paper":
            pm_winner = _weather_fallback_outcome(icao, target_date, city,
                                                  bucket_lo, bucket_hi, bucket_unit)
            if pm_winner is not None:
                outcome_source = "weather_fallback"

        if pm_winner is not None:
            # Ground truth from Polymarket — no temperature math needed for outcome
            yes_won = (pm_winner == "yes")
            if direction == "YES":
                outcome = "won" if yes_won else "lost"
            else:
                outcome = "won" if not yes_won else "lost"
            logger.info("PM resolution %s %s: YES_won=%s → %s %s (src=%s)",
                        city, target_date, yes_won, direction, outcome, outcome_source)
        else:
            # Polymarket has not resolved this market yet.
            # Live-mode policy: never self-resolve from weather fallbacks.
            logger.info("PM not resolved for %s %s trade=%s — holding pending",
                        city, target_date, trade["trade_id"][:8])
            results.append({
                "trade_id": trade["trade_id"],
                "status": "pending_pm",
                "city": city,
                "date": target_date,
            })
            continue

        # ── Step 2: fetch actual temperature for bias correction ─────────────
        # Skip for TSA — there is no temperature to fetch, and TSA trades have no
        # station in the bias correction pipeline.
        actual_c = None
        temp_source = "unavailable"
        if trade.get("market_type", "temperature") not in ("tsa", "crypto"):
            try:
                actual_c, temp_source = get_actual_high_c(icao, target_date, city)
            except RuntimeError as e:
                logger.warning("Could not fetch temp for bias correction %s %s: %s",
                               city, target_date, e)

        exit_price = 1.0 if outcome == "won" else 0.0

        msg = (
            f"RESOLVED {trade['trade_id'][:8]} | {city} {target_date} | "
            f"actual={actual_c:.1f}°C | bucket=[{bucket_lo},{bucket_hi}]{bucket_unit} | "
            f"{direction} → {outcome} | outcome_src={outcome_source} temp_src={temp_source}"
            if actual_c is not None else
            f"RESOLVED {trade['trade_id'][:8]} | {city} {target_date} | "
            f"no_temp | bucket=[{bucket_lo},{bucket_hi}]{bucket_unit} | "
            f"{direction} → {outcome} | outcome_src={outcome_source}"
        )
        logger.info(msg)

        if not dry_run:
            # Store actual temp as historical obs for bias correction.
            # Wunderground obs are especially valuable — they're Polymarket's resolution
            # source and give non-circular ground truth for international stations.
            if actual_c is not None and temp_source in ("wunderground", "asos"):
                db.upsert_historical_obs(icao, target_date, actual_c, temp_source)
                logger.debug("Stored %s obs for %s %s: %.1f°C", temp_source, icao, target_date, actual_c)
                # Immediately recompute bias so next scan uses updated corrections.
                # Wrapped in try/except — bias failure must never block trade resolution.
                try:
                    from signals.bias_corrector import recompute_bias
                    recompute_bias(icao)
                    logger.debug("Bias recomputed for %s after %s obs", icao, temp_source)
                except Exception as _be:
                    logger.warning("Bias recompute failed for %s: %s", icao, _be)

            pnl = db.resolve_trade(trade["trade_id"], actual_c, outcome, exit_price,
                                   outcome_source=outcome_source)
            db.log_event("TRADE_RESOLVED", msg, city=city, icao=icao,
                         data={"actual_c": actual_c, "outcome": outcome,
                               "pnl": pnl, "outcome_source": outcome_source})
            send_trade_event(
                "WIN" if outcome == "won" else "LOSS",
                direction=trade["direction"],
                city=city,
                target_date=target_date,
                entry_price=trade["entry_price"],
                bucket_lo=bucket_lo,
                bucket_hi=bucket_hi,
                bucket_unit=bucket_unit,
                edge=trade["edge"],
                stake=size,
                pnl=pnl,
            )
            # Update TSA calibration record if applicable
            if trade.get("market_type") == "tsa":
                resolved_val = 1.0 if (
                    (outcome == "won" and trade["direction"] == "YES") or
                    (outcome == "lost" and trade["direction"] == "NO")
                ) else 0.0
                db.resolve_tsa_prediction(trade["market_id"], resolved_val)
            results.append({
                "trade_id":      trade["trade_id"],
                "city":          city,
                "date":          target_date,
                "actual_c":      actual_c,
                "outcome":       outcome,
                "outcome_source": outcome_source,
                "pnl":           pnl,
            })
        else:
            logger.info("[DRY RUN] Would resolve: %s", msg)
            results.append({
                "trade_id":      trade["trade_id"],
                "dry_run":       True,
                "outcome":       outcome,
                "outcome_source": outcome_source,
            })

    return results
