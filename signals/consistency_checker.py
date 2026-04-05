"""
Cross-market consistency checker for temperature markets.

For each (city, target_date) with multiple active bucket markets, checks
whether the CLOB prices are internally consistent.

Two checks:

  1. Partition sum check:
     If the buckets tile the temperature axis without gaps or overlaps,
     their YES probabilities should sum to ~1.0.
     Sum > 1.0 + THRESHOLD → something is overpriced → bet NO on the most overpriced
     Sum < 1.0 - THRESHOLD → something is underpriced → bet YES on the most underpriced

  2. Cumulative vs range check:
     If P(high ≥ X) and P(high in [X, Y)) and P(high ≥ Y) are all live:
     P(≥ X) ≈ P([X,Y)) + P(≥ Y)
     If the cumulative price deviates by > THRESHOLD from the component sum,
     one of them is mispriced.

Returns a list of arb signals, each with:
  market_id, direction (YES|NO), type (partition|cumulative),
  implied_fair, market_prob, implied_edge, message
"""
import logging
import math
from itertools import combinations

logger = logging.getLogger(__name__)

# Min mismatch (after accounting for typical spread) before flagging
CONSISTENCY_THRESHOLD = 0.06   # 6 percentage points

# Only check groups with at least this many buckets
MIN_BUCKETS_PER_GROUP = 2


def _lo(m) -> float:
    v = m.get("bucket_lo")
    return float("-inf") if v is None else float(v)


def _hi(m) -> float:
    v = m.get("bucket_hi")
    return float("inf") if v is None else float(v)


def _buckets_are_adjacent(a: dict, b: dict) -> bool:
    """Return True if bucket b starts exactly where bucket a ends (no gap, no overlap)."""
    return math.isclose(_hi(a), _lo(b), abs_tol=0.01)


def _sort_key(m):
    """Sort by lower bound, putting -inf first."""
    lo = m.get("bucket_lo")
    return float("-inf") if lo is None else float(lo)


def check_partition_consistency(
    markets_for_group: list[dict],
    prices: dict[str, float],    # market_id → YES mid-price
) -> list[dict]:
    """
    Find ordered bucket chains that tile the axis and check their sum.

    markets_for_group: all parsed markets for one (city, target_date)
    prices:            live mid-price per market_id
    """
    signals = []

    # Sort by lower bound
    ms = sorted(markets_for_group, key=_sort_key)

    # Find maximal contiguous chains where adjacent buckets tile perfectly
    def build_chains(markets):
        """Return list of chains (each chain is an ordered list of markets)."""
        used = set()
        chains = []
        for i, start in enumerate(markets):
            if i in used:
                continue
            chain = [start]
            used.add(i)
            cur = start
            for j, nxt in enumerate(markets):
                if j in used:
                    continue
                if _buckets_are_adjacent(cur, nxt):
                    chain.append(nxt)
                    used.add(j)
                    cur = nxt
            if len(chain) >= MIN_BUCKETS_PER_GROUP:
                chains.append(chain)
        return chains

    chains = build_chains(ms)

    for chain in chains:
        mid_prices = [prices.get(m["market_id"]) for m in chain]
        if any(p is None for p in mid_prices):
            continue  # missing price — can't check

        total = sum(mid_prices)
        n = len(chain)

        if abs(total - 1.0) < CONSISTENCY_THRESHOLD:
            continue  # consistent — no arb

        # Find most mispriced bucket relative to implied fair value
        # Implied fair = each bucket's share if total were normalised to 1.0
        implied_fairs = [p / total for p in mid_prices]

        for market, p_market, p_fair in zip(chain, mid_prices, implied_fairs):
            implied_edge = p_fair - p_market  # + means underpriced (buy YES)
            if abs(implied_edge) < CONSISTENCY_THRESHOLD:
                continue

            direction = "YES" if implied_edge > 0 else "NO"
            msg = (
                f"Partition sum={total:.3f} (expected 1.0) | "
                f"{market.get('question', market['market_id'][:30])} | "
                f"market={p_market:.3f} fair≈{p_fair:.3f} edge={implied_edge:+.3f}"
            )
            signals.append({
                "market_id":    market["market_id"],
                "direction":    direction,
                "type":         "partition",
                "implied_fair": round(p_fair, 4),
                "market_prob":  round(p_market, 4),
                "implied_edge": round(implied_edge, 4),
                "chain_sum":    round(total, 4),
                "n_buckets":    n,
                "message":      msg,
            })
            logger.info("Consistency arb [partition]: %s", msg)

    return signals


def check_cumulative_consistency(
    markets_for_group: list[dict],
    prices: dict[str, float],
) -> list[dict]:
    """
    Check cumulative (≥X or <X) vs range bucket consistency.

    For any pair of range buckets [A,B) and [B,C) and cumulative ≥A:
      P(≥A) should ≈ P([A,B)) + P([B,C)) + P(≥C)
    """
    signals = []

    # Separate cumulative and range markets
    cumulative = [m for m in markets_for_group
                  if m.get("bucket_lo") is None or m.get("bucket_hi") is None]
    ranged = [m for m in markets_for_group
              if m.get("bucket_lo") is not None and m.get("bucket_hi") is not None]

    if not cumulative or not ranged:
        return signals

    for cum_m in cumulative:
        cum_price = prices.get(cum_m["market_id"])
        if cum_price is None:
            continue

        cum_lo = _lo(cum_m)  # for ≥X markets
        cum_hi = _hi(cum_m)  # for <X markets

        # Find range buckets that live inside the cumulative range
        if cum_m.get("bucket_hi") is None:
            # ≥ X market: look for [X, Y) + [Y, Z) + ... + ≥Z
            sub = [r for r in ranged
                   if _lo(r) >= cum_lo - 0.01
                   and _hi(r) < float("inf")]
        else:
            # < X market: look for [A, B) + ... + [W, X)
            sub = [r for r in ranged
                   if _hi(r) <= cum_hi + 0.01
                   and _lo(r) > float("-inf")]

        if len(sub) < 2:
            continue

        sub_prices = [prices.get(m["market_id"]) for m in sub]
        if any(p is None for p in sub_prices):
            continue

        # Find the "tail" cumulative market (≥ max of sub buckets, or ≤ min)
        if cum_m.get("bucket_hi") is None:
            max_sub_hi = max(_hi(m) for m in sub)
            tail = [m for m in cumulative
                    if m["market_id"] != cum_m["market_id"]
                    and m.get("bucket_lo") is not None
                    and math.isclose(float(m["bucket_lo"]), max_sub_hi, abs_tol=0.01)]
            tail_price = prices.get(tail[0]["market_id"]) if tail else 0.0
            if tail_price is None:
                tail_price = 0.0
        else:
            min_sub_lo = min(_lo(m) for m in sub)
            tail = [m for m in cumulative
                    if m["market_id"] != cum_m["market_id"]
                    and m.get("bucket_hi") is not None
                    and math.isclose(float(m["bucket_hi"]), min_sub_lo, abs_tol=0.01)]
            tail_price = prices.get(tail[0]["market_id"]) if tail else 0.0
            if tail_price is None:
                tail_price = 0.0

        implied_cum = sum(sub_prices) + tail_price
        gap = implied_cum - cum_price   # + means cum underpriced; - means cum overpriced

        if abs(gap) < CONSISTENCY_THRESHOLD:
            continue

        direction = "YES" if gap > 0 else "NO"
        msg = (
            f"Cumulative mismatch: {cum_m.get('question','?')[:40]} "
            f"priced {cum_price:.3f} but components sum to {implied_cum:.3f} "
            f"(gap={gap:+.3f})"
        )
        signals.append({
            "market_id":    cum_m["market_id"],
            "direction":    direction,
            "type":         "cumulative",
            "implied_fair": round(implied_cum, 4),
            "market_prob":  round(cum_price, 4),
            "implied_edge": round(gap, 4),
            "message":      msg,
        })
        logger.info("Consistency arb [cumulative]: %s", msg)

    return signals


def find_consistency_signals(
    markets: list[dict],
    prices: dict[str, float],
    unit: str | None = None,
) -> list[dict]:
    """
    Main entry point.

    markets: list of parsed market dicts (same city, filtered to temperature).
             Each must have: market_id, city, target_date, bucket_lo, bucket_hi,
             bucket_unit, question.
    prices:  {market_id: YES mid-price}
    unit:    if provided, only check markets with this bucket_unit ('F' or 'C')

    Returns list of arb signal dicts sorted by |implied_edge| descending.
    """
    all_signals = []

    # Group by (city, target_date, bucket_unit)
    groups: dict[tuple, list[dict]] = {}
    for m in markets:
        if unit and m.get("bucket_unit") != unit:
            continue
        key = (m.get("city", ""), str(m.get("target_date", "")), m.get("bucket_unit", ""))
        groups.setdefault(key, []).append(m)

    for (city, tdate, bunit), group in groups.items():
        if len(group) < MIN_BUCKETS_PER_GROUP:
            continue
        group_prices = {m["market_id"]: prices.get(m["market_id"])
                        for m in group if prices.get(m["market_id"]) is not None}
        if len(group_prices) < MIN_BUCKETS_PER_GROUP:
            continue

        all_signals.extend(check_partition_consistency(group, group_prices))
        all_signals.extend(check_cumulative_consistency(group, group_prices))

    # Deduplicate by market_id (keep highest implied_edge for each)
    seen: dict[str, dict] = {}
    for s in all_signals:
        mid = s["market_id"]
        if mid not in seen or abs(s["implied_edge"]) > abs(seen[mid]["implied_edge"]):
            seen[mid] = s

    return sorted(seen.values(), key=lambda x: abs(x["implied_edge"]), reverse=True)
