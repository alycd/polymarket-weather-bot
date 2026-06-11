"""
Live broker — real order execution via Polymarket CLOB.
Real money. Real fills. Use with care.

Architecture:
- Uses py-clob-client to sign and post limit orders (GTC).
- Buying YES shares: side=BUY on the YES token.
- Buying NO shares: side=BUY on the NO token (a distinct asset_id from YES).
  The NO token_id is fetched from the CLOB GET /markets/{condition_id} endpoint
  (Gamma sometimes omits the sibling token). We post a BUY directly on it.

Order strategy (taker — we are NOT a market maker):
- Re-quote the book at submission time and abort if the ask slipped past the
  scan-time edge by more than LIVE_MAX_REQUOTE_SLIP — the edge was computed
  against a price that no longer exists (F10).
- Round the limit to the market's tick size: BUY rounds UP to the next tick
  at/above the ask (taker intent), SELL rounds DOWN (F11).
- Post GTC at the re-quoted ask, then POLL get_order_status every
  LIVE_FILL_POLL_S up to LIVE_FILL_TIMEOUT_S. Terminal when size_matched == size
  or status is matched/filled (F2).
- Filled  → compute the actual average fill price from get_clob_fills.
- Partial → cancel the remainder; record only the filled fraction (F8).
- Unfilled→ cancel; the trade is voided upstream (no on-chain position).
- Cancel race (filled while cancelling) → re-check; pending if still ambiguous,
  the reconciler owns it (--reconcile, WI-5). We never assume a fill (F2/F5).

All risk checks (deployment cap, direction cap, book depth) still run in
paper_broker before we get here. This module ONLY handles on-chain submission
and fill verification.
"""
import os
import logging
import time
from dotenv import load_dotenv
from telegram import send_trade_event, send_telegram_notification

load_dotenv()

logger = logging.getLogger(__name__)

# Lazy singleton to avoid repeated auth overhead
_client = None

CLOB_HOST = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
POLYGON_CHAIN_ID = 137

# Live execution tunables (read from the active config; inert in paper mode).
# Imported lazily inside functions so importing this module never pulls config.
def _live_cfg():
    import config_active as c
    return c


def get_proxy_address() -> str:
    """Polymarket proxy / funder wallet (same as UI portfolio address)."""
    return os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()


def get_polymarket_closed_positions(limit: int = 500) -> list[dict]:
    """Closed positions with realized PnL — matches Polymarket portfolio history."""
    proxy = get_proxy_address()
    if not proxy:
        return []
    import requests

    try:
        r = requests.get(
            f"{DATA_API}/closed-positions",
            params={"user": proxy, "limit": min(limit, 500)},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Could not fetch closed positions: %s", e)
        return []


def get_polymarket_positions_value_usd() -> float | None:
    """Total mark-to-market value of open positions (Data API — same as UI)."""
    proxy = get_proxy_address()
    if not proxy:
        return None
    import requests

    try:
        r = requests.get(f"{DATA_API}/value", params={"user": proxy}, timeout=12)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return float(data[0].get("value", 0) or 0)
    except Exception as e:
        logger.warning("Could not fetch /value: %s", e)
    return None


def _get_client():
    global _client
    if _client is not None:
        return _client

    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
    api_secret = os.getenv("POLYMARKET_API_SECRET", "").strip()
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

    proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
    sig_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))

    if not private_key:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set in .env")
    if not api_key:
        raise RuntimeError("POLYMARKET_API_KEY not set in .env — run scripts/gen_clob_creds.py")

    creds = ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    )
    _client = ClobClient(
        host=CLOB_HOST,
        chain_id=POLYGON_CHAIN_ID,
        key=private_key,
        creds=creds,
        signature_type=sig_type,
        funder=proxy_address if proxy_address else None,
    )
    logger.info("CLOB client initialized — address: %s", _client.get_address())

    # Sync balance allowance so the CLOB recognises current wallet state.
    # Required for pUSD markets (signature_type=3); harmless for USDC (type=0).
    _sync_balance_allowance(_client, sig_type)

    return _client


def _sync_balance_allowance(client, sig_type: int) -> None:
    """Call /balance-allowance/update to sync on-chain balance with the CLOB."""
    import requests as _r
    from py_clob_client.clob_types import RequestArgs
    from py_clob_client.headers.headers import create_level_2_headers
    try:
        path = "/balance-allowance/update"
        req_args = RequestArgs(method="GET", request_path=path)
        headers = create_level_2_headers(client.signer, client.creds, req_args)
        resp = _r.get(
            f"{CLOB_HOST}{path}?asset_type=COLLATERAL&signature_type={sig_type}",
            headers=headers,
            timeout=10,
        )
        if resp.ok:
            logger.info("Balance allowance synced (sig_type=%d)", sig_type)
        else:
            logger.warning("Balance allowance sync returned %d: %s", resp.status_code, resp.text[:120])
    except Exception as e:
        logger.warning("Balance allowance sync failed: %s", e)


def _get_clob_market(market_id: str) -> dict:
    """Fetch the CLOB GET /markets/{condition_id} response (tokens + tick size).

    Gamma has a known bug where it sometimes omits the sibling (NO) token when
    queried by YES token ID, causing Missing Instrument errors. The CLOB endpoint
    returns both tokens explicitly by outcome label plus the market's
    minimum_tick_size, so we use it for both the NO-token and tick lookups.
    Returns {} on failure.
    """
    import requests
    if not market_id:
        return {}
    try:
        r = requests.get(f"{CLOB_HOST}/markets/{market_id}", timeout=8)
        r.raise_for_status()
        return r.json() or {}
    except Exception as e:
        logger.warning("Could not fetch CLOB market %s: %s", market_id[:16], e)
        return {}


def _get_no_token_id(market: dict, clob_market: dict | None = None) -> str | None:
    """Return the NO token ID for a market (via the CLOB market response)."""
    market_id = market.get("market_id", "")
    clob_yes   = market.get("clob_token_yes", "")
    if not market_id:
        logger.warning("Cannot fetch NO token: market_id missing for %s", clob_yes[:16])
        return None
    data = clob_market if clob_market is not None else _get_clob_market(market_id)
    for token in data.get("tokens", []):
        if token.get("outcome", "").lower() == "no":
            return str(token["token_id"])
    return None


def _get_tick_size(clob_market: dict, default: float = 0.01) -> float:
    """Extract the market's minimum tick size; fall back to 0.01."""
    for key in ("minimum_tick_size", "min_tick_size", "tick_size"):
        v = clob_market.get(key)
        if v:
            try:
                tick = float(v)
                if tick > 0:
                    return tick
            except (TypeError, ValueError):
                pass
    return default


def _round_to_tick(price: float, tick: float, direction: str) -> float:
    """Round a limit price to the tick grid.

    direction='up'   → ceil to the next tick at/above price (taker BUY intent).
    direction='down' → floor to the next tick at/below price (SELL intent).
    Always clamped to the valid (tick, 1-tick) range.
    """
    import math
    if tick <= 0:
        tick = 0.01
    steps = price / tick
    if direction == "up":
        snapped = math.ceil(round(steps, 9)) * tick
    else:
        snapped = math.floor(round(steps, 9)) * tick
    snapped = max(tick, min(1.0 - tick, snapped))
    # tidy float noise to the tick's decimal precision
    decimals = max(0, -int(round(math.log10(tick))))
    return round(snapped, decimals + 2)


def get_clob_balance() -> float:
    """Return current USDC balance in the CLOB wallet (6-decimal raw → dollars)."""
    import requests
    from py_clob_client.clob_types import RequestArgs
    from py_clob_client.headers.headers import create_level_2_headers

    client = _get_client()
    sig_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    try:
        path = "/balance-allowance"
        req_args = RequestArgs(method="GET", request_path=path)
        headers = create_level_2_headers(client.signer, client.creds, req_args)
        r = requests.get(
            f"{CLOB_HOST}{path}?asset_type=COLLATERAL&signature_type={sig_type}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        raw = int(r.json().get("balance", 0))
        return raw / 1_000_000  # USDC has 6 decimals
    except Exception as e:
        logger.warning("Could not fetch CLOB balance: %s", e)
        return 0.0


# ── Fill-verification primitives ───────────────────────────────────────────────

def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _order_match_state(order_obj: dict) -> tuple[float, float, str]:
    """Return (size_matched, original_size, status) from a CLOB order dict,
    reading defensively across field-name variants."""
    sm = order_obj.get("size_matched", order_obj.get("sizeMatched",
          order_obj.get("matched_amount", 0)))
    orig = order_obj.get("original_size", order_obj.get("originalSize",
            order_obj.get("size", order_obj.get("makerAmount", 0))))
    status = str(order_obj.get("status", "")).lower()
    return _f(sm), _f(orig), status


def _avg_fill_price(order_id: str, token_id: str, fallback_price: float) -> tuple[float, float]:
    """Average fill price + total filled shares for an order, from get_clob_fills.

    Fills can execute across several book levels, so the realized average differs
    from the limit. The fills API can lag the order status by a few seconds
    (edge case, spec §4): retry x3 with 2s backoff. If still empty, fall back to
    the limit price (conservative for a taker BUY: realized <= limit) and let the
    reconciler refine it later. Returns (avg_price, filled_shares).
    """
    for attempt in range(3):
        fills = get_clob_fills()
        matched = []
        for fexec in fills:
            oid = (fexec.get("order_id") or fexec.get("orderID")
                   or fexec.get("taker_order_id") or "")
            asset = str(fexec.get("asset_id") or fexec.get("asset")
                        or fexec.get("token_id") or "")
            if (order_id and oid == order_id) or (not oid and asset == token_id):
                px = _f(fexec.get("price"))
                sz = _f(fexec.get("size") or fexec.get("size_matched")
                        or fexec.get("matched_amount"))
                if px > 0 and sz > 0:
                    matched.append((px, sz))
        if matched:
            total_sz = sum(sz for _, sz in matched)
            avg = sum(px * sz for px, sz in matched) / total_sz if total_sz else fallback_price
            return round(avg, 6), round(total_sz, 4)
        if attempt < 2:
            time.sleep(2)
    logger.warning("get_clob_fills lag: no fills for order %s — using limit price %.3f",
                   order_id[:12] if order_id else "?", fallback_price)
    return fallback_price, 0.0


def _post_and_poll(order_args, timeout_s: float, on_posted=None) -> dict:
    """Sign+post a GTC order, then poll until terminal or timeout.

    on_posted(order_id): optional callback invoked immediately after a successful
    post, BEFORE polling — used by entries to persist entry_order_id +
    entry_fill_status='pending' so a daemon killed mid-poll leaves a recoverable
    row (spec §4 bullet 1).

    Returns one of:
      {fill_status:'filled',  order_id, size_matched, original_size}
      {fill_status:'partial', order_id, size_matched, original_size}  (remainder cancelled)
      {fill_status:'unfilled',order_id}                               (cancelled)
      {fill_status:'pending', order_id}                               (ambiguous; reconciler owns)
      {error: str}                                                    (submission failed)

    Average fill price is NOT computed here (caller fetches it via _avg_fill_price
    so the same helper serves both entries and exits).
    """
    from py_clob_client.clob_types import OrderType
    cfg = _live_cfg()
    client = _get_client()

    try:
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.GTC)
    except Exception as e:
        return {"error": f"order_submission_failed: {e}"}

    order_id = resp.get("orderID") or resp.get("id", "")
    if on_posted is not None and order_id:
        try:
            on_posted(order_id)
        except Exception as e:
            logger.warning("on_posted callback failed for %s: %s",
                           order_id[:12] if order_id else "?", e)
    post_status = str(resp.get("status", "")).lower()
    requested = _f(getattr(order_args, "size", 0))

    # Immediate full match on submission (taker crossed the spread)?
    if post_status in ("matched", "filled"):
        return {"fill_status": "filled", "order_id": order_id,
                "size_matched": requested, "original_size": requested}

    deadline = time.time() + timeout_s
    last_matched, last_orig = 0.0, requested
    while time.time() < deadline:
        time.sleep(cfg.LIVE_FILL_POLL_S)
        obj = get_order_status(order_id)
        if not obj:
            continue
        matched, orig, status = _order_match_state(obj)
        last_matched, last_orig = matched, (orig or requested)
        if status in ("matched", "filled") or (last_orig and matched >= last_orig - 1e-6):
            return {"fill_status": "filled", "order_id": order_id,
                    "size_matched": matched or last_orig, "original_size": last_orig}
        if status in ("cancelled", "canceled"):
            # Cancelled out from under us; treat any matched portion as partial.
            if matched > 0:
                return {"fill_status": "partial", "order_id": order_id,
                        "size_matched": matched, "original_size": last_orig}
            return {"fill_status": "unfilled", "order_id": order_id}

    # Timed out — cancel the remainder.
    cancelled = cancel_order(order_id)
    obj = get_order_status(order_id)
    matched, orig, status = _order_match_state(obj) if obj else (last_matched, last_orig, "")
    last_orig = orig or last_orig or requested

    if status in ("matched", "filled") or (last_orig and matched >= last_orig - 1e-6):
        # Cancel raced a fill — it actually filled. (spec §4: re-check after cancel)
        return {"fill_status": "filled", "order_id": order_id,
                "size_matched": matched or last_orig, "original_size": last_orig}
    if matched > 0:
        return {"fill_status": "partial", "order_id": order_id,
                "size_matched": matched, "original_size": last_orig}
    if cancelled or status in ("cancelled", "canceled"):
        return {"fill_status": "unfilled", "order_id": order_id}
    # Cancel API errored and status is unknown — hand off to the reconciler.
    return {"fill_status": "pending", "order_id": order_id}


def execute_live_trade(
    market: dict,
    signal: dict,
    dry_run: bool = False,
    trade_id: str | None = None,
) -> dict:
    """
    Submit a real limit order to the Polymarket CLOB and verify the fill.

    market: same dict as paper_broker (market_id, clob_token_yes, ...)
    signal: output of edge_calculator (direction, entry_price, size_usdc, ...)
    dry_run: if True, validate everything (incl. requote/tick logging) but post nothing.
    trade_id: the paper-path DB row id; if given, entry_order_id + 'pending' are
              persisted the instant the order is posted (before polling).

    Returns a dict the caller maps to a DB correction:
      {fill_status:'filled',   order_id, token_id, clob_token_no, avg_fill_price,
       filled_shares}
      {fill_status:'partial',  ... filled_shares, avg_fill_price}
      {fill_status:'unfilled'} / {fill_status:'pending', order_id} / {skipped: reason}
    """
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.order_builder.constants import BUY

    cfg = _live_cfg()
    direction = signal["direction"]
    entry_price = signal["entry_price"]   # scan-time price of the side we're buying (0-1)
    size_usdc = signal["size_usdc"]
    market_id = market.get("market_id", "")

    # Resolve the token we're buying + the NO token id + tick size in one fetch.
    clob_market = _get_clob_market(market_id) if market_id else {}
    no_token_id = _get_no_token_id(market, clob_market) if market_id else None
    tick = _get_tick_size(clob_market)

    if direction == "YES":
        token_id = market.get("clob_token_yes", "")
    else:
        token_id = no_token_id
        if not token_id:
            return {"skipped": "no_token_id_unavailable"}
    if not token_id:
        return {"skipped": "token_id_missing"}

    # ── Re-quote at submission time (F10) ──────────────────────────────────────
    # Fetch the current ask for the token we're buying and abort if it slipped
    # past the scan-time entry by more than LIVE_MAX_REQUOTE_SLIP. The scan-time
    # entry_price IS the ask for the side we buy (YES ask / NO ask = 1 - YES bid),
    # so we compare like-for-like.
    requote_ask = _current_ask(token_id, market.get("clob_token_yes", ""), direction)
    if requote_ask is not None:
        slip = requote_ask - entry_price
        if slip > cfg.LIVE_MAX_REQUOTE_SLIP:
            logger.info("Requote slip abort %s: scan=%.3f now=%.3f (+%.3f > %.3f)",
                        market_id[:12], entry_price, requote_ask, slip, cfg.LIVE_MAX_REQUOTE_SLIP)
            return {"skipped": "requote_slip"}
        order_price = requote_ask
    else:
        # No live book — fall back to the scan-time entry price.
        order_price = entry_price

    # ── Tick-aware rounding (F11): round BUY limit UP to the next tick ──────────
    order_price = _round_to_tick(order_price, tick, "up")

    # Convert USDC size → shares (shares = usdc / price)
    shares = round(size_usdc / order_price, 2)
    if shares < 1.0:
        return {"skipped": f"shares_too_small ({shares:.2f})"}

    log_prefix = (
        f"LIVE {direction} | {market.get('city')} {market.get('target_date')} | "
        f"token={token_id[:12]}... price={order_price:.3f} shares={shares:.1f} "
        f"(${size_usdc:.2f}) tick={tick}"
    )

    if dry_run:
        logger.info("[DRY RUN LIVE] %s | requote_ask=%s", log_prefix,
                    f"{requote_ask:.3f}" if requote_ask is not None else "n/a")
        return {"dry_run": True, "log": log_prefix, "token_id": token_id,
                "clob_token_no": no_token_id or "", "price": order_price, "shares": shares}

    # ── Post + poll for fill (F2). Persist the order id + 'pending' the instant
    #    the order is posted so a daemon killed mid-poll leaves a recoverable row.
    order_args = OrderArgs(token_id=token_id, price=order_price, size=shares, side=BUY)

    def _on_posted(oid: str):
        if trade_id:
            import db
            db.update_trade_execution(trade_id, entry_order_id=oid,
                                      entry_fill_status="pending",
                                      clob_token_no=no_token_id or "")

    poll = _post_and_poll(order_args, cfg.LIVE_FILL_TIMEOUT_S, on_posted=_on_posted)

    if "error" in poll:
        logger.error("Order submission failed for %s: %s", market_id[:16], poll["error"])
        return {"skipped": poll["error"]}

    order_id = poll["order_id"]
    fill_status = poll["fill_status"]
    logger.info("ORDER %s %s | order_id=%s",
                fill_status.upper(), log_prefix, order_id[:12] if order_id else "?")

    if fill_status == "unfilled":
        send_trade_event(
            "LIVE-UNFILLED",
            direction=direction, city=market.get("city"),
            target_date=market.get("target_date"),
            entry_price=order_price,
            bucket_lo=market.get("bucket_lo"), bucket_hi=market.get("bucket_hi"),
            bucket_unit=market.get("bucket_unit", "C"),
            edge=signal["edge"], stake=size_usdc,
        )
        return {"fill_status": "unfilled", "order_id": order_id,
                "token_id": token_id, "clob_token_no": no_token_id or ""}

    if fill_status == "pending":
        return {"fill_status": "pending", "order_id": order_id,
                "token_id": token_id, "clob_token_no": no_token_id or ""}

    # filled or partial — get the realized average fill price + shares
    avg_price, filled_from_fills = _avg_fill_price(order_id, token_id, order_price)
    if fill_status == "partial":
        filled_shares = poll.get("size_matched") or filled_from_fills or 0.0
    else:
        filled_shares = filled_from_fills or poll.get("size_matched") or shares

    send_trade_event(
        "LIVE-TRADE",
        direction=direction,
        city=market.get("city"),
        target_date=market.get("target_date"),
        entry_price=avg_price,
        bucket_lo=market.get("bucket_lo"),
        bucket_hi=market.get("bucket_hi"),
        bucket_unit=market.get("bucket_unit", "C"),
        edge=signal["edge"],
        stake=round(filled_shares * avg_price, 2),
    )

    return {
        "fill_status":    fill_status,        # 'filled' | 'partial'
        "order_id":       order_id,
        "direction":      direction,
        "token_id":       token_id,
        "clob_token_no":  no_token_id or "",
        "avg_fill_price": avg_price,
        "filled_shares":  filled_shares,
    }


def _current_ask(token_id: str, yes_token_id: str, direction: str) -> float | None:
    """Best ask (cost to buy one share) for the side we're entering.

    For YES we need the YES token's ask; for NO we need the NO token's ask, which
    equals 1 - (YES token best bid). We always fetch the YES book (the one our
    data layer exposes) and derive accordingly. Returns None if the book is empty.
    """
    from data.polymarket import get_clob_orderbook
    try:
        if direction == "YES":
            book = get_clob_orderbook(token_id)
            asks = book.get("asks", [])
            if asks:
                return min(float(a["price"]) for a in asks)
        else:
            book = get_clob_orderbook(yes_token_id or token_id)
            bids = book.get("bids", [])
            if bids:
                return round(1.0 - max(float(b["price"]) for b in bids), 6)
    except Exception as e:
        logger.warning("Requote book fetch failed for %s: %s",
                       (token_id or "?")[:16], e)
    return None


def cancel_order(order_id: str) -> bool:
    """Cancel an open limit order by ID. Returns True on success."""
    client = _get_client()
    try:
        client.cancel(order_id=order_id)
        logger.info("Cancelled order %s", order_id[:16])
        return True
    except Exception as e:
        logger.warning("Failed to cancel order %s: %s", order_id[:16], e)
        return False


def get_open_orders() -> list[dict]:
    """Return all open (unfilled) orders on the CLOB."""
    client = _get_client()
    try:
        resp = client.get_orders()
        return resp if isinstance(resp, list) else []
    except Exception as e:
        logger.warning("Could not fetch open orders: %s", e)
        return []


def get_clob_positions() -> list[dict]:
    """
    Fetch all current on-chain positions via Polymarket Gamma API.
    Returns list of {conditionId, asset, size, avgPrice, currentPrice, value}.
    """
    import requests

    proxy = get_proxy_address()
    if not proxy:
        logger.warning("POLYMARKET_PROXY_ADDRESS not set — cannot fetch positions")
        return []
    try:
        r = requests.get(
            f"{DATA_API}/positions",
            params={"user": proxy, "sizeThreshold": 0.01},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Could not fetch positions from data-api: %s", e)
        return []


def get_clob_fills() -> list[dict]:
    """Return all confirmed fills from the CLOB (entire wallet history)."""
    from py_clob_client.clob_types import TradeParams
    client = _get_client()
    proxy = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
    try:
        trades = client.get_trades(TradeParams(maker_address=proxy))
        return trades if isinstance(trades, list) else []
    except Exception as e:
        logger.warning("Could not fetch CLOB fills: %s", e)
        return []


def get_order_status(order_id: str) -> dict:
    """Check if a submitted order has been filled, partially filled, or is still open."""
    client = _get_client()
    try:
        resp = client.get_order(order_id)
        return resp if isinstance(resp, dict) else {}
    except Exception as e:
        logger.warning("Could not get order status for %s: %s", order_id[:16], e)
        return {}


def sell_position(token_id: str, shares: float, min_price: float = 0.01,
                  tick: float = 0.01, timeout_s: float | None = None) -> dict:
    """
    Sell (exit) a position by posting a SELL order on the token WE HOLD, then
    verify the fill (WI-3/WI-4). Used for early exits.

    token_id: the NO token for NO positions, YES token for YES positions — the
              caller (exit-scan) selects this correctly so we never try to sell a
              token we don't hold (F1).
    shares:   number of shares to sell (caller floors to <= held shares; F7).
    min_price: limit price; rounded DOWN to the tick (SELL intent; F11).
    timeout_s: poll window (defaults to LIVE_EXIT_FILL_TIMEOUT_S).

    Returns:
      {fill_status:'filled'|'partial', order_id, avg_fill_price, filled_shares}
      {fill_status:'unfilled'|'pending', order_id}
      {error: str}
    """
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.order_builder.constants import SELL

    cfg = _live_cfg()
    if timeout_s is None:
        timeout_s = cfg.LIVE_EXIT_FILL_TIMEOUT_S

    sell_price = _round_to_tick(min_price, tick, "down")
    sell_shares = round(shares, 2)
    order_args = OrderArgs(token_id=token_id, price=sell_price, size=sell_shares, side=SELL)

    logger.info("SELL submit: token=%s shares=%.2f price=%.3f tick=%s",
                token_id[:16], sell_shares, sell_price, tick)
    poll = _post_and_poll(order_args, timeout_s)
    if "error" in poll:
        logger.error("Sell order failed for token %s: %s", token_id[:16], poll["error"])
        return {"error": poll["error"]}

    order_id = poll["order_id"]
    fill_status = poll["fill_status"]
    if fill_status in ("unfilled", "pending"):
        return {"fill_status": fill_status, "order_id": order_id}

    avg_price, filled_from_fills = _avg_fill_price(order_id, token_id, sell_price)
    if fill_status == "partial":
        filled_shares = poll.get("size_matched") or filled_from_fills or 0.0
    else:
        filled_shares = filled_from_fills or poll.get("size_matched") or sell_shares
    return {"fill_status": fill_status, "order_id": order_id,
            "avg_fill_price": avg_price, "filled_shares": filled_shares}


def redeem_positions() -> dict:
    """
    Check for resolved winning positions and report claimable USDC.

    On Polymarket, resolved positions are redeemed automatically by the
    protocol when the market settles — the USDC appears in the wallet
    without any on-chain action needed. This function checks if any
    positions changed from open to resolved since last check.

    Returns {redeemed: count, usdc_claimed: float}.
    """
    import requests

    proxy = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
    balance_after = get_clob_balance()

    try:
        # Check for redeemable positions via data API
        r = requests.get(
            f"{DATA_API}/positions",
            params={"user": proxy, "sizeThreshold": 0.01, "redeemable": "true"},
            timeout=12,
        )
        redeemable = r.json() if r.ok else []
        if not isinstance(redeemable, list):
            redeemable = []

        n = len(redeemable)
        if n > 0:
            total_value = sum(float(p.get("currentValue", 0)) for p in redeemable)
            logger.info("Found %d redeemable positions worth $%.2f", n, total_value)
            return {"redeemed": n, "usdc_claimed": total_value}

        return {"redeemed": 0, "usdc_claimed": 0.0}
    except Exception as e:
        logger.warning("Redeem check failed: %s", e)
        return {"redeemed": 0, "usdc_claimed": 0.0, "error": str(e)}


def _position_token_map(positions: list[dict]) -> dict[str, float]:
    """Map on-chain token-id → held share count, from the data-api positions list.

    Matching on token id (asset) — NOT conditionId — because a YES and a NO
    position in the same market share a conditionId and would false-match (F-edge,
    spec §4 / WI-5 step 3).
    """
    by_token: dict[str, float] = {}
    for p in positions:
        token = str(p.get("asset") or p.get("token_id") or "")
        if not token:
            continue
        size = _f(p.get("size") or p.get("shares") or p.get("totalBought"))
        by_token[token] = by_token.get(token, 0.0) + size
    return by_token


def _trade_token(trade: dict) -> str:
    """The token id this trade should hold on-chain: NO token for NO, else YES."""
    if trade.get("direction") == "NO":
        return trade.get("clob_token_no") or ""
    return trade.get("clob_token_yes") or ""


def sync_positions_to_db(alert: bool = False) -> dict:
    """
    Pull actual on-chain positions and cross-check against confirmed-fill DB trades.

    Matches on token id + share count (within 5% tolerance). Reports:
      - filled DB trades with no matching CLOB position  → mismatch (alert)
      - CLOB positions with no DB trade                  → orphan  (alert: manual trades)
    Does NOT auto-void — could be data-api lag (WI-5 step 3). With alert=True,
    sends a telegram RECONCILE-MISMATCH and flags the trade's notes on the SECOND
    consecutive miss.
    Returns summary dict.
    """
    import db

    positions = get_clob_positions()
    n_clob = len(positions)
    by_token = _position_token_map(positions)

    # Only cross-check trades we believe are actually filled on-chain.
    open_trades = db.get_open_live_trades_with_fills()
    matched = 0
    mismatches: list[dict] = []

    for trade in open_trades:
        token = _trade_token(trade)
        held = trade.get("entry_filled_shares")
        if held is None:
            ep = trade.get("entry_price") or 0
            held = (trade.get("size_usdc") or 0.0) / ep if ep else 0.0
        chain_sz = by_token.get(token, 0.0)
        tol = max(0.05 * held, 1.0)
        if token and abs(chain_sz - held) <= tol:
            matched += 1
        else:
            mismatches.append({"trade": trade, "expected": held, "on_chain": chain_sz})

    # Orphan CLOB positions (token on-chain with no filled DB trade)
    db_tokens = {_trade_token(t) for t in open_trades}
    orphans = [tok for tok, sz in by_token.items() if sz > 0 and tok not in db_tokens]

    for m in mismatches:
        t = m["trade"]
        logger.warning("RECONCILE mismatch: trade %s (%s %s %s) expected %.2f sh, on-chain %.2f sh",
                       t["trade_id"][:8], t["city"], t["target_date"], t["direction"],
                       m["expected"], m["on_chain"])
        if alert:
            prev = (t.get("notes") or "")
            second = "RECONCILE-MISS-1" in prev
            send_telegram_notification(
                "RECONCILE-MISMATCH",
                f"{t['city']} {t['target_date']} {t['direction']}: "
                f"DB expects {m['expected']:.1f} sh, chain has {m['on_chain']:.1f} sh"
                + (" — SECOND consecutive miss, flagged for manual review" if second else ""))
            if second:
                _flag_trade_note(t["trade_id"], "RECONCILE-MISS-2 manual review")
            else:
                _flag_trade_note(t["trade_id"], "RECONCILE-MISS-1")

    if orphans and alert:
        send_telegram_notification(
            "RECONCILE-ORPHAN",
            f"{len(orphans)} on-chain position(s) with no matching DB trade "
            f"(token{'s' if len(orphans)!=1 else ''}: "
            + ", ".join(tok[:10] for tok in orphans[:5]) + ")")

    logger.info("Position sync: %d CLOB positions, %d matched, %d mismatches, %d orphans",
                n_clob, matched, len(mismatches), len(orphans))
    return {"synced": matched, "not_filled": len(mismatches),
            "clob_positions": n_clob, "orphans": len(orphans)}


def _flag_trade_note(trade_id: str, note: str):
    """Append a short note to a trade row (manual-review breadcrumb)."""
    import db
    with db._conn() as conn:
        row = conn.execute("SELECT notes FROM trades WHERE trade_id=?", (trade_id,)).fetchone()
        prev = (row["notes"] if row else "") or ""
        if note in prev:
            return
        conn.execute("UPDATE trades SET notes=? WHERE trade_id=?",
                     ((prev + " | " + note).strip(" |"), trade_id))


def _finalize_poll_result(trade_id: str, poll: dict, token_id: str, limit_price: float):
    """Apply a WI-2 entry outcome (filled/partial/unfilled/pending) to a DB trade.

    Shared by the live entry call site AND the reconciler's pending sweep, so the
    DB correction is written in exactly one place.
    """
    import db
    fill_status = poll.get("fill_status")
    order_id = poll.get("order_id", "")

    if fill_status == "filled":
        avg_price, filled = _avg_fill_price(order_id, token_id, limit_price)
        shares = filled or poll.get("size_matched") or 0.0
        if shares <= 0:
            return
        db.update_trade_execution(
            trade_id, entry_order_id=order_id, entry_fill_status="filled",
            entry_filled_shares=shares, entry_price=avg_price,
            size_usdc=round(shares * avg_price, 2))
    elif fill_status == "partial":
        avg_price, filled = _avg_fill_price(order_id, token_id, limit_price)
        shares = poll.get("size_matched") or filled or 0.0
        if shares <= 0:
            db.void_trade_refund_stake(trade_id, "reconcile: partial reported zero shares")
            return
        db.update_trade_execution(trade_id, entry_order_id=order_id)
        db.trim_trade_partial_fill(trade_id, shares, avg_price)
    elif fill_status == "unfilled":
        db.void_trade_refund_stake(trade_id, "reconcile: order unfilled / cancelled")
    # 'pending' → leave as-is for the next reconcile pass


def reconcile() -> dict:
    """Hourly DB↔chain reconciliation (live only). See spec WI-5.

    1. Stale-order janitor: cancel resting orders older than LIVE_MAX_ORDER_AGE_S
       and finalize their owning trade if still pending.
    2. Pending-trade sweep: finalize any entry_fill_status='pending' rows.
    3. Position cross-check: token-id matching, alert on mismatch/orphan.
    4. Bankroll sanity: alert if DB vs (cash + positions value) drift > threshold.
    No auto-void of positions; alert-only (WI-5 / decision 3).
    """
    import db
    from datetime import datetime, timezone as _tz
    cfg = _live_cfg()
    summary = {"stale_cancelled": 0, "pending_finalized": 0,
               "mismatches": 0, "orphans": 0, "bankroll_drift": 0.0}

    # 1. Stale-order janitor ----------------------------------------------------
    now = datetime.now(_tz.utc)
    open_orders = get_open_orders()
    pending_trades = {t.get("entry_order_id"): t
                      for t in db.get_trades_by_entry_fill_status("pending")
                      if t.get("entry_order_id")}
    for order in open_orders:
        oid = order.get("orderID") or order.get("id") or order.get("order_id") or ""
        created = order.get("created_at") or order.get("createdAt") or order.get("created")
        age_s = _order_age_seconds(created, now)
        if age_s is not None and age_s < cfg.LIVE_MAX_ORDER_AGE_S:
            continue
        # Old (or unknown-age) resting order — cancel and finalize its owner.
        if cancel_order(oid):
            summary["stale_cancelled"] += 1
        if oid in pending_trades:
            poll = _classify_order_now(oid, order)
            t = pending_trades[oid]
            _finalize_poll_result(t["trade_id"], poll, _trade_token(t), t.get("entry_price", 0.0))
            summary["pending_finalized"] += 1

    # 2. Pending-trade sweep (anything still pending, e.g. order no longer open) -
    for t in db.get_trades_by_entry_fill_status("pending"):
        oid = t.get("entry_order_id") or ""
        if not oid:
            db.void_trade_refund_stake(t["trade_id"], "reconcile: pending with no order id")
            summary["pending_finalized"] += 1
            continue
        poll = _classify_order_now(oid, None)
        _finalize_poll_result(t["trade_id"], poll, _trade_token(t), t.get("entry_price", 0.0))
        summary["pending_finalized"] += 1

    # 3. Position cross-check ---------------------------------------------------
    sync = sync_positions_to_db(alert=True)
    summary["mismatches"] = sync.get("not_filled", 0)
    summary["orphans"] = sync.get("orphans", 0)

    # 4. Bankroll sanity --------------------------------------------------------
    try:
        cash = float(get_clob_balance() or 0.0)
        pos_val = float(get_polymarket_positions_value_usd() or 0.0)
        chain_total = cash + pos_val
        db_total = float(db.get_bankroll()) + sum(
            float(t.get("size_usdc") or 0.0) for t in db.get_open_trades())
        drift = db_total - chain_total
        summary["bankroll_drift"] = round(drift, 2)
        if abs(drift) > cfg.LIVE_BANKROLL_DRIFT_ALERT:
            msg = (f"DB total ${db_total:.2f} vs chain ${chain_total:.2f} "
                   f"(cash ${cash:.2f}+pos ${pos_val:.2f}) drift ${drift:+.2f}")
            logger.error("RECONCILE bankroll drift: %s", msg)
            send_telegram_notification("RECONCILE-DRIFT", msg)
    except Exception as e:
        logger.warning("Bankroll sanity check failed: %s", e)

    db.log_event("RECONCILE",
                 f"stale={summary['stale_cancelled']} pending={summary['pending_finalized']} "
                 f"mismatch={summary['mismatches']} orphan={summary['orphans']} "
                 f"drift=${summary['bankroll_drift']:+.2f}")
    logger.info("Reconcile complete: %s", summary)
    return summary


def _order_age_seconds(created_raw, now) -> float | None:
    """Best-effort age of an order in seconds. Returns None if unparseable
    (treated as stale by the caller, since nothing should rest unknown-age)."""
    if created_raw is None:
        return None
    from datetime import datetime, timezone as _tz
    try:
        # Epoch seconds (int/str) or ISO timestamp
        if isinstance(created_raw, (int, float)) or str(created_raw).isdigit():
            ts = datetime.fromtimestamp(int(created_raw), _tz.utc)
        else:
            ts = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz.utc)
        return (now - ts).total_seconds()
    except (ValueError, TypeError, OSError):
        return None


def _classify_order_now(order_id: str, order_obj: dict | None) -> dict:
    """Classify an order's current terminal state for finalization (no polling)."""
    obj = order_obj if order_obj is not None else get_order_status(order_id)
    if not obj:
        # Order not found / no longer open — check fills to decide.
        return {"fill_status": "unfilled", "order_id": order_id}
    matched, orig, status = _order_match_state(obj)
    if status in ("matched", "filled") or (orig and matched >= orig - 1e-6):
        return {"fill_status": "filled", "order_id": order_id,
                "size_matched": matched or orig, "original_size": orig}
    if matched > 0:
        return {"fill_status": "partial", "order_id": order_id,
                "size_matched": matched, "original_size": orig}
    if status in ("cancelled", "canceled"):
        return {"fill_status": "unfilled", "order_id": order_id}
    return {"fill_status": "pending", "order_id": order_id}
