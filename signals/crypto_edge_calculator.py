"""
Crypto Up/Down market edge calculator.

Signal: N(d2) from Black-Scholes — the risk-neutral probability that the
asset closes above the reference price by the resolution time.

Reference price = Deribit index price at the time of first scan for this
market (stored in DB). On subsequent scans the stored reference is reused
so the bet stays consistent.

Kelly sizing identical to temperature and TSA markets.
"""
import logging
import math
from datetime import datetime, timezone

from scipy.stats import norm

from config import (MIN_EDGE, KELLY_FRACTION, MAX_TRADE_FRACTION,
                    MIN_EDGE_RECENT_MULTIPLIER, MIN_EDGE_RECENT_DAYS,
                    HIGH_CONVICTION_EDGE, HIGH_CONVICTION_KELLY_MULT)

logger = logging.getLogger(__name__)


# ── Core probability model ─────────────────────────────────────────────────────

def crypto_updown_prob(
    spot: float,
    reference: float,
    hours_remaining: float,
    iv_annual: float,
) -> float:
    """
    P(asset > reference at expiry) under Black-Scholes with zero drift.

    spot:           current index price
    reference:      price the asset must beat to resolve YES
    hours_remaining: time until market resolves (fractional hours)
    iv_annual:      annualised implied vol (decimal, e.g. 0.55 for 55%)
    """
    T = max(hours_remaining, 1 / 3600) / 8760  # hours → years, floor at 1 second
    d1 = (math.log(spot / reference) + 0.5 * iv_annual ** 2 * T) / (iv_annual * math.sqrt(T))
    d2 = d1 - iv_annual * math.sqrt(T)
    return float(norm.cdf(d2))


# ── Main signal computation ────────────────────────────────────────────────────

def compute_crypto_edge(
    market: dict,
    market_implied_prob: float,
    spot: float,
    reference_price: float,
    iv_annual: float,
    bid: float | None = None,
    ask: float | None = None,
) -> dict | None:
    """
    Compute edge signal for one crypto Up/Down market.

    market:               dict with end_time, asset, market_id
    market_implied_prob:  CLOB mid for YES
    spot:                 current Deribit index price
    reference_price:      price at window open (what YES must beat)
    iv_annual:            Deribit ATM IV (annualised, decimal)
    bid/ask:              CLOB bid/ask for accurate entry price

    Returns signal dict or None if should be skipped.
    """
    import db

    end_time = market.get("end_time", "")
    asset    = market.get("asset", "")

    # Hours remaining
    try:
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        hours_remaining = max(0.0, (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600)
    except (ValueError, TypeError):
        logger.warning("Crypto: bad end_time %s", end_time)
        return None

    if hours_remaining < 1 / 60:  # less than 1 minute — skip, too late to enter
        return None

    # ── 1. Model probability ──────────────────────────────────────────────────
    model_prob = crypto_updown_prob(spot, reference_price, hours_remaining, iv_annual)

    # ── 2. Edge ──────────────────────────────────────────────────────────────
    edge      = model_prob - market_implied_prob
    direction = "YES" if model_prob > market_implied_prob else "NO"

    if direction == "YES":
        actual_entry = ask if ask is not None else market_implied_prob
    else:
        actual_entry = (1.0 - bid) if bid is not None else (1.0 - market_implied_prob)

    if direction == "YES":
        effective_edge = model_prob - actual_entry
    else:
        effective_edge = (1.0 - model_prob) - actual_entry

    # ── 3. Skip extreme-priced markets (unrealisable fills) ──────────────────
    if direction == "YES" and market_implied_prob < 0.05:
        return None
    if direction == "NO" and market_implied_prob > 0.95:
        return None
    if direction == "NO" and actual_entry < 0.05:
        return None

    # ── 4. Only enter when signal is sufficiently far from 50/50 ─────────────
    # A model_prob near 0.50 means we have no real edge — the market is still live.
    # Require the model to have moved at least 15 percentage points from 50%.
    if abs(model_prob - 0.50) < 0.15:
        logger.debug("Crypto: model_prob %.3f too close to 0.50 — no entry signal yet", model_prob)
        return None

    # ── 5. Lead-time aware min edge ───────────────────────────────────────────
    if hours_remaining <= MIN_EDGE_RECENT_DAYS * 24:
        adaptive_min_edge = MIN_EDGE * MIN_EDGE_RECENT_MULTIPLIER
    else:
        adaptive_min_edge = MIN_EDGE

    if abs(effective_edge) < adaptive_min_edge:
        logger.debug("Crypto: effective_edge %.3f below threshold — skip", effective_edge)
        return None

    # ── 6. Kelly sizing ───────────────────────────────────────────────────────
    bankroll = db.get_bankroll()
    p_win = model_prob if direction == "YES" else (1.0 - model_prob)

    if actual_entry <= 0.001 or actual_entry >= 0.999:
        return None
    b_odds = (1.0 / actual_entry) - 1.0
    if b_odds <= 0:
        return None

    kf = max(0.0, (b_odds * p_win - (1.0 - p_win)) / b_odds)
    kelly_mult = HIGH_CONVICTION_KELLY_MULT if abs(effective_edge) >= HIGH_CONVICTION_EDGE else 1.0
    kf = min(kf * KELLY_FRACTION * kelly_mult, 1.0)
    size_usdc = min(kf * bankroll, MAX_TRADE_FRACTION * bankroll)
    if size_usdc < 1.0:
        return None

    return {
        "direction":        direction,
        "entry_price":      actual_entry,
        "model_prob":       round(model_prob, 4),
        "market_prob":      round(market_implied_prob, 4),
        "edge":             round(edge, 4),
        "effective_edge":   round(effective_edge, 4),
        "size_usdc":        round(size_usdc, 2),
        "kelly_f":          round(kf, 4),
        "lead_days":        round(hours_remaining / 24, 4),
        # Crypto-specific
        "crypto_asset":     asset,
        "crypto_spot":      round(spot, 2),
        "crypto_reference": round(reference_price, 2),
        "crypto_iv":        round(iv_annual, 4),
        "crypto_hours_rem": round(hours_remaining, 3),
        # Broker compatibility sentinels
        "ensemble_std_c":   0.0,
        "nowcast_weight":   0.0,
        "confidence_tier":  2,
        "hub_weather_flag": None,
    }
