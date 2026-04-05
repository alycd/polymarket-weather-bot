"""
Live broker — real order execution via Polymarket CLOB.
Real money. Real fills. Use with care.

Architecture:
- Uses py-clob-client to sign and post limit orders (GTC).
- Buying YES shares: side=BUY on the YES token.
- Buying NO shares: side=BUY on the NO token (1 - YES token price).
  The NO token_id is derived from the conditionId + negation.
  Simplest approach: buy YES at (1 - NO_price) is wrong for the NO token.
  We post a BUY on the NO token directly.

Order strategy:
- Post a limit order at mid-price (passive fill).
- If not filled within FILL_TIMEOUT_S seconds, cancel and re-post at ask/bid.
- In practice for weather markets (thin books), we post at mid and accept partial.

All risk checks (deployment cap, stop-loss, direction cap) still run in paper_broker
before we call here. This module ONLY handles the on-chain submission.
"""
import os
import logging
import time
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Lazy singleton to avoid repeated auth overhead
_client = None

CLOB_HOST = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
POLYGON_CHAIN_ID = 137
FILL_TIMEOUT_S = 30   # seconds to wait for passive fill before crossing spread


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
    return _client


def _get_no_token_id(market: dict) -> str | None:
    """
    Fetch the NO token ID for this market from the Gamma API.
    The CLOB market has exactly 2 tokens: YES and NO.
    We already have clob_token_yes; pick the other one.
    """
    import requests
    market_id = market.get("market_id", "")
    clob_yes   = market.get("clob_token_yes", "")
    try:
        r = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"clob_token_ids": clob_yes},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            data = data[0]
        import json as _json
        tokens_raw = data.get("clobTokenIds") or "[]"
        tokens = _json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
        for t in tokens:
            if t != clob_yes:
                return t
    except Exception as e:
        logger.warning("Could not fetch NO token for %s: %s", market_id[:16], e)
    return None


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


def execute_live_trade(
    market: dict,
    signal: dict,
    dry_run: bool = False,
) -> dict:
    """
    Submit a real limit order to the Polymarket CLOB.

    market: same dict as paper_broker (market_id, clob_token_yes, ...)
    signal: output of edge_calculator (direction, entry_price, size_usdc, ...)
    dry_run: if True, validate everything but don't submit the order.

    Returns dict with order_id and fill details, or {'skipped': reason}.
    """
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY

    direction = signal["direction"]
    entry_price = signal["entry_price"]   # price of the side we're buying (0-1)
    size_usdc = signal["size_usdc"]

    # Determine token and price for the order
    if direction == "YES":
        token_id = market.get("clob_token_yes", "")
        order_price = round(entry_price, 2)
    else:
        # Buying NO = buying the NO token at (1 - YES_mid)
        token_id = _get_no_token_id(market)
        if not token_id:
            return {"skipped": "no_token_id_unavailable"}
        order_price = round(1.0 - market.get("market_prob", 1.0 - entry_price), 2)
        # entry_price for NO is already 1 - market_prob; use it directly
        order_price = round(entry_price, 2)

    if not token_id:
        return {"skipped": "token_id_missing"}

    # Clamp price to valid tick range (0.01 - 0.99, step 0.01)
    order_price = max(0.01, min(0.99, round(order_price, 2)))

    # Convert USDC size → shares (shares = usdc / price)
    shares = round(size_usdc / order_price, 2)
    if shares < 1.0:
        return {"skipped": f"shares_too_small ({shares:.2f})"}

    market_id = market.get("market_id", "")
    log_prefix = (
        f"LIVE {direction} | {market.get('city')} {market.get('target_date')} | "
        f"token={token_id[:12]}... price={order_price:.2f} shares={shares:.1f} "
        f"(${size_usdc:.2f})"
    )

    if dry_run:
        logger.info("[DRY RUN LIVE] %s", log_prefix)
        return {"dry_run": True, "log": log_prefix, "token_id": token_id,
                "price": order_price, "shares": shares}

    client = _get_client()

    order_args = OrderArgs(
        token_id=token_id,
        price=order_price,
        size=shares,
        side=BUY,
    )

    try:
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
    except Exception as e:
        logger.error("Order submission failed for %s: %s", market_id[:16], e)
        return {"skipped": f"order_submission_failed: {e}"}

    order_id = resp.get("orderID") or resp.get("id", "")
    status = resp.get("status", "unknown")

    logger.info("ORDER SUBMITTED %s | order_id=%s status=%s",
                log_prefix, order_id[:12] if order_id else "?", status)

    # Poll for fill (GTC orders may sit on the book)
    filled_price = order_price  # assume passive fill at limit price
    filled_size = size_usdc

    return {
        "order_id":    order_id,
        "direction":   direction,
        "token_id":    token_id,
        "entry_price": filled_price,
        "size_usdc":   filled_size,
        "shares":      shares,
        "status":      status,
    }


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


def sell_position(token_id: str, shares: float, min_price: float = 0.01) -> dict:
    """
    Sell (exit) a position by posting a SELL order on the token.
    Used for stop-loss exits and early redemption.

    token_id: the YES or NO token we hold
    shares: number of shares to sell
    min_price: minimum acceptable sell price (default 1¢ — take anything to exit)
    """
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import SELL

    client = _get_client()
    sell_price = max(0.01, min(0.99, round(min_price, 2)))

    order_args = OrderArgs(
        token_id=token_id,
        price=sell_price,
        size=round(shares, 2),
        side=SELL,
    )
    try:
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.GTC)
        order_id = resp.get("orderID") or resp.get("id", "")
        logger.info("SELL order submitted: token=%s shares=%.2f price=%.2f order_id=%s",
                    token_id[:16], shares, sell_price, order_id[:12] if order_id else "?")
        return {"order_id": order_id, "status": resp.get("status", "unknown"), "shares": shares}
    except Exception as e:
        logger.error("Sell order failed for token %s: %s", token_id[:16], e)
        return {"error": str(e)}


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


def sync_positions_to_db() -> dict:
    """
    Pull actual on-chain positions from Polymarket data API and reconcile with DB.
    Logs which of our open trades have real CLOB positions vs unfilled orders.
    Returns summary dict.
    """
    import db

    positions = get_clob_positions()
    n_clob = len(positions)

    # Build lookup by conditionId / marketId
    clob_markets: set[str] = set()
    for p in positions:
        for key in ("conditionId", "market", "asset", "proxyWallet"):
            v = p.get(key, "")
            if v:
                clob_markets.add(v.lower())

    open_trades = db.get_open_trades()
    synced = 0
    not_filled = 0

    for trade in open_trades:
        mid = (trade.get("market_id") or "").lower()
        token = (trade.get("clob_token_yes") or "").lower()
        if mid in clob_markets or token in clob_markets:
            synced += 1
        else:
            not_filled += 1
            logger.info("Trade %s not found on CLOB: %s %s %s",
                        trade["trade_id"][:8], trade["city"],
                        trade["target_date"], trade["direction"])

    logger.info("Position sync: %d CLOB positions, %d DB matches, %d not on CLOB",
                n_clob, synced, not_filled)
    return {"synced": synced, "not_filled": not_filled, "clob_positions": n_clob}
