"""
Paper broker — simulated order execution at real CLOB prices.
Money is fake. Prices are real.
"""
import uuid
import logging
from datetime import datetime
from config_active import CITIES, MAX_DEPLOYED_FRACTION
import db
from data.polymarket import get_market_prices
from telegram import send_trade_event

logger = logging.getLogger(__name__)


def execute_paper_trade(
    market: dict,
    signal: dict,
    dry_run: bool = False,
    open_trades: list[dict] | None = None,
) -> dict:
    """
    Execute a paper trade based on an edge signal.

    market: DB-style market dict with market_id, city, icao, target_date,
            bucket_lo, bucket_hi, bucket_unit, clob_token_yes, question
    signal: output of edge_calculator.compute_edge()
    dry_run: if True, log but don't write to DB

    Returns dict with trade details or {'skipped': reason}.
    """
    market_id = market.get("market_id") or market.get("conditionId", "")

    # Guard: don't enter the same market twice
    if db.already_in_market(market_id):
        return {"skipped": "already_positioned"}

    # Order book depth check: skip if the market is too thin to fill realistically.
    # We sum the top-5 bid and ask levels.  Size field is in shares; multiply by
    # price to get approximate USDC value.  This rejects phantom quotes that look
    # liquid on mid but have nothing behind them.
    MIN_BOOK_DEPTH_USDC = 150.0
    exit_depth = None   # exit-side depth near best ($) — measure-only, persisted on the trade
    if market.get("market_type", "temperature") not in ("tsa", "crypto"):
        try:
            from data.polymarket import get_clob_orderbook, exit_depth_usdc
            from config_active import EXIT_DEPTH_WINDOW
            book      = get_clob_orderbook(market.get("clob_token_yes", ""))
            bid_depth = sum(
                float(b.get("size", 0)) * float(b.get("price", 0))
                for b in (book.get("bids") or [])[:5]
            )
            ask_depth = sum(
                float(a.get("size", 0)) * float(a.get("price", 0))
                for a in (book.get("asks") or [])[:5]
            )
            total_depth = bid_depth + ask_depth
            if total_depth < MIN_BOOK_DEPTH_USDC:
                logger.info(
                    "Book depth $%.0f too thin (< $%.0f) — skipping %s",
                    total_depth, MIN_BOOK_DEPTH_USDC, market_id[:16],
                )
                return {"skipped": f"book_depth_too_thin (${total_depth:.0f})"}
            # Phase-1 exit-liquidity measurement (no gating yet — see
            # docs/plans/2026-06-12_exit_liquidity_sizing.md): how many dollars
            # rest on the side our exit would sell into, near the best price.
            exit_depth = exit_depth_usdc(book, signal["direction"], EXIT_DEPTH_WINDOW)
            if exit_depth is not None:
                pct = signal["size_usdc"] / exit_depth * 100 if exit_depth > 0 else float("inf")
                logger.info("exit-depth: $%.0f within %.2f of best (size $%.2f → %.0f%% of exit depth) %s",
                            exit_depth, EXIT_DEPTH_WINDOW, signal["size_usdc"], pct, market_id[:16])
            else:
                logger.info("exit-depth: no resting exit-side liquidity for %s", market_id[:16])
        except Exception as _bd_err:
            logger.debug("Book depth check failed for %s: %s — proceeding",
                         market_id[:16], _bd_err)

    # Timing filter: skip if price is converging toward our fair value
    # Use rolling average of last 3 edge snapshots to reduce noise.
    # TSA markets have no intraday price convergence signal — skip this filter for them.
    if signal.get("nowcast_weight", 0.0) < 0.5 and market.get("market_type") not in ("tsa", "crypto"):
        from datetime import datetime, timedelta
        recent = db.get_recent_prices(market_id, limit=8)
        cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        recent_2h = [r for r in recent[1:] if r.get("scanned_at", "") >= cutoff
                     and r.get("edge") is not None]
        curr_edge = signal["edge"]
        if len(recent_2h) >= 2 and curr_edge is not None:
            avg_prev = sum(abs(r["edge"]) for r in recent_2h) / len(recent_2h)
            if avg_prev > 0 and abs(curr_edge) < avg_prev * 0.70:
                logger.info(
                    "Timing: edge shrinking avg=%.3f → %.3f over last 2h for %s — waiting",
                    avg_prev, abs(curr_edge), market_id[:16]
                )
                return {"skipped": "price_converging"}

    bankroll = db.get_bankroll()
    size = signal["size_usdc"]
    # Hard dollar cap — prevents over-sizing when bankroll grows large
    from config_active import MAX_TRADE_USDC
    if size > MAX_TRADE_USDC:
        size = MAX_TRADE_USDC
    if size < 0.50:
        return {"skipped": f"size_too_small (${size:.2f} after tiering)"}
    if size <= 0:
        return {"skipped": "zero_size (T4 or Kelly too small)"}
    if size > bankroll:
        return {"skipped": f"insufficient_bankroll ({bankroll:.2f} < {size:.2f})"}
    if bankroll - size < 0:
        return {"skipped": "would_go_negative"}

    # Global deployment cap: prevent over-concentration across many simultaneous positions
    if open_trades is None:
        open_trades = db.get_open_trades()

    # Correlated bucket discount: multiple NO bets on the same city+date are mutually
    # exclusive (at most one bucket can be the actual temperature, so at most one NO
    # can lose). Count full size for the largest position; discount others by 80%.
    NO_CORR_DISCOUNT = 0.20   # correlated NO positions count at 20% of face value
    from collections import defaultdict
    no_groups: dict[tuple, list[float]] = defaultdict(list)
    for t in open_trades:
        if t.get("direction") == "NO":
            no_groups[(t["city"], str(t["target_date"]))].append(t["size_usdc"])

    discounted_deployed = 0.0
    for t in open_trades:
        key = (t["city"], str(t["target_date"]))
        if t.get("direction") == "NO" and len(no_groups.get(key, [])) > 1:
            sizes = sorted(no_groups[key], reverse=True)
            # Max position counts fully; rest are discounted
            # Largest position counts full; all others discounted.
            # Track by trade_id to handle ties correctly.
            max_size = sizes[0]
            already_counted_full = any(
                ot["size_usdc"] == max_size and ot.get("direction") == "NO"
                and (ot["city"], str(ot["target_date"])) == key
                and ot["trade_id"] < t["trade_id"]  # deterministic tiebreak by id
                for ot in open_trades
            )
            if t["size_usdc"] == max_size and not already_counted_full:
                discounted_deployed += t["size_usdc"]
            else:
                discounted_deployed += t["size_usdc"] * NO_CORR_DISCOUNT
        else:
            discounted_deployed += t["size_usdc"]

    # Also discount the new trade if it's a correlated NO
    new_city, new_td = market.get("city", ""), str(market.get("target_date", ""))
    new_direction = signal["direction"]
    existing_nos_same_group = len(no_groups.get((new_city, new_td), []))
    if new_direction == "NO" and existing_nos_same_group > 0:
        new_size_effective = size * NO_CORR_DISCOUNT
    else:
        new_size_effective = size

    total_deployed = sum(t["size_usdc"] for t in open_trades)
    portfolio_value = bankroll + total_deployed
    if portfolio_value > 0 and (discounted_deployed + new_size_effective) / portfolio_value > MAX_DEPLOYED_FRACTION:
        logger.info(
            "Deployment cap: deployed=%.2f + new=%.2f exceeds %.0f%% of portfolio=%.2f",
            total_deployed, size, MAX_DEPLOYED_FRACTION * 100, portfolio_value,
        )
        return {"skipped": "max_deployment_cap_reached"}

    # Get the freshest CLOB price at execution
    try:
        prices   = get_market_prices(market)
        live_mid = prices.get("mid")
    except Exception as e:
        logger.warning("Could not get live CLOB mid at execution: %s", e)
        live_mid = None

    entry_price = signal["entry_price"]
    if live_mid is not None:
        # Recalculate edge with live price
        if signal["direction"] == "YES":
            live_entry = live_mid
        else:
            live_entry = 1.0 - live_mid
        
        slippage = abs(live_entry - entry_price)
        
        # New "Take-the-Edge" logic: 
        # We only skip if the live price is worse AND it kills the edge.
        # If the price moved in our favor (slippage < 0 effectively), we definitely take it.
        direction = signal["direction"]
        model_prob = signal["model_prob"]
        live_effective_edge = (
            (model_prob - live_entry) if direction == "YES"
            else ((1.0 - model_prob) - live_entry)
        )
        
        exec_min_edge = signal.get("adaptive_min_edge") or __import__("config").MIN_EDGE
        if live_effective_edge < exec_min_edge:
            logger.info(
                "SIM slippage %.3f killed edge (live_edge %.3f < threshold %.3f) — skipping %s",
                slippage, live_effective_edge, exec_min_edge, market_id[:16],
            )
            return {"skipped": f"edge_vanished (slip={slippage:.3f})"}
        
        # If slippage is massive (> 0.10), even with edge, something might be wrong (halt/crash)
        if slippage > 0.10:
            logger.warning("SIM extreme slippage %.3f on %s — skipping for safety", slippage, market_id[:16])
            return {"skipped": "extreme_slippage_safety"}

        if slippage > 0.001:
            logger.info("SIM slippage %.3f accepted — live edge %.3f still profitable",
                        slippage, live_effective_edge)
        
        entry_price = live_entry

    trade_id = str(uuid.uuid4())
    city = market.get("city", "")
    icao = market.get("icao", CITIES.get(city, {}).get("icao", ""))

    log_msg = (
        f"SIM-TRADE {signal['direction']} | {city} {market.get('target_date')} | "
        f"bucket=[{market.get('bucket_lo')}, {market.get('bucket_hi')}] "
        f"{market.get('bucket_unit')} | "
        f"entry={entry_price:.4f} model={signal['model_prob']:.3f} "
        f"market={signal['market_prob']:.3f} edge={signal['edge']:+.3f} | "
        f"${size:.2f} Kelly={signal['kelly_f']:.4f}"
    )

    if dry_run:
        logger.info("[DRY RUN] %s", log_msg)
        return {"dry_run": True, "trade_id": "dry-" + trade_id[:8], "log": log_msg}

    # Deduct bankroll and insert trade record atomically.
    # A crash between these two operations would lose the stake without a trade record.
    # Wrapping in a single SQLite transaction guarantees either both commit or neither does.
    db.open_trade_atomic(
        trade_id=trade_id,
        market_id=market_id,
        city=city,
        icao=icao,
        target_date=str(market.get("target_date", "")),
        bucket_lo=market.get("bucket_lo"),
        bucket_hi=market.get("bucket_hi"),
        bucket_unit=market.get("bucket_unit", "C"),
        direction=signal["direction"],
        entry_price=entry_price,
        model_prob=signal["model_prob"],
        market_prob=signal["market_prob"],
        edge=signal["edge"],
        ensemble_std=signal.get("ensemble_std_c", 0.0),
        size_usdc=size,
        kelly_f=signal["kelly_f"],
        target_date_end=str(market.get("target_date_end", "") or ""),
        market_type=market.get("market_type", "temperature"),
        hub_weather_flag=signal.get("hub_weather_flag"),
        clob_token_yes=market.get("clob_token_yes", ""),
        exit_depth_usdc=exit_depth,
    )

    db.log_event("TRADE_OPENED", log_msg, city=city, icao=icao, data=signal)
    logger.info("%s", log_msg)
    send_trade_event(
        "PAPER-TRADE",
        direction=signal["direction"],
        city=city,
        target_date=market.get("target_date"),
        entry_price=entry_price,
        bucket_lo=market.get("bucket_lo"),
        bucket_hi=market.get("bucket_hi"),
        bucket_unit=market.get("bucket_unit", "C"),
        edge=signal["edge"],
        stake=size,
    )

    return {
        "trade_id":    trade_id,
        "direction":   signal["direction"],
        "entry_price": entry_price,
        "size_usdc":   size,
        "edge":        signal["edge"],
        "model_prob":  signal["model_prob"],
        "market_prob": signal["market_prob"],
        "bankroll_after": db.get_bankroll(),
    }


def check_stop_losses(dry_run: bool = False) -> list[dict]:
    """
    Stop-losses are disabled.
    Kept as a no-op for compatibility with any older callers.
    """
    return []
