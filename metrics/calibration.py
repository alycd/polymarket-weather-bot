"""
Calibration metrics — was our model closer to reality than the market?

Computes:
  - Mean Absolute Error (MAE) for model and market
  - Brier Score: mean((prob - outcome)²) — lower is better
  - Brier Skill Score: 1 - (model_brier / market_brier) — positive = outperforming market
  - Per-city breakdown
  - Calibration curve: bucketed predicted-vs-actual win rate (overconfidence / underconfidence)
  - Per-market-type breakdown (temperature / TSA / crypto)
  - Shrinkage factor recommendation

Also supports exporting a full calibration CSV for public tracking.
CSV uses atomic writes (write to .tmp, rename) + fcntl.flock for safety.
"""
import csv
import fcntl
import logging
import os
import db

logger = logging.getLogger(__name__)


def compute_calibration(since: str | None = None) -> dict:
    resolved = db.get_resolved_trades()
    if since:
        resolved = [t for t in resolved if (t.get("resolved_at") or "") >= since]
    if not resolved:
        return {
            "n": 0,
            "model_closer_count": 0,
            "accuracy": 0.0,
            "mean_model_error": 0.0,
            "mean_market_error": 0.0,
            "model_brier": 0.0,
            "market_brier": 0.0,
            "brier_skill_score": 0.0,
            "by_city": {},
        }

    n_closer = 0
    model_errors, market_errors = [], []
    model_brier_vals, market_brier_vals = [], []
    by_city: dict[str, dict] = {}

    for t in resolved:
        outcome_val = 1.0 if t["status"] == "won" else 0.0
        model_err   = abs(t["model_prob"] - outcome_val)
        market_err  = abs(t["market_prob"] - outcome_val)
        model_errors.append(model_err)
        market_errors.append(market_err)
        model_brier_vals.append((t["model_prob"] - outcome_val) ** 2)
        market_brier_vals.append((t["market_prob"] - outcome_val) ** 2)
        if model_err < market_err:
            n_closer += 1

        city = t["city"]
        if city not in by_city:
            by_city[city] = {"n": 0, "closer": 0, "model_brier_sum": 0.0, "market_brier_sum": 0.0}
        by_city[city]["n"] += 1
        by_city[city]["model_brier_sum"]  += (t["model_prob"] - outcome_val) ** 2
        by_city[city]["market_brier_sum"] += (t["market_prob"] - outcome_val) ** 2
        if model_err < market_err:
            by_city[city]["closer"] += 1

    n = len(resolved)
    model_brier  = sum(model_brier_vals)  / n
    market_brier = sum(market_brier_vals) / n
    bss = (1.0 - model_brier / market_brier) if market_brier > 0 else 0.0

    # Per-city Brier scores
    for city, d in by_city.items():
        cn = d["n"]
        d["model_brier"]  = round(d["model_brier_sum"]  / cn, 4)
        d["market_brier"] = round(d["market_brier_sum"] / cn, 4)
        d["brier_skill"]  = round(
            1.0 - d["model_brier"] / d["market_brier"] if d["market_brier"] > 0 else 0.0, 4
        )

    return {
        "n":                  n,
        "model_closer_count": n_closer,
        "accuracy":           round(n_closer / n * 100, 1) if n else 0.0,
        "mean_model_error":   round(sum(model_errors)  / n, 4),
        "mean_market_error":  round(sum(market_errors) / n, 4),
        "model_brier":        round(model_brier,  4),
        "market_brier":       round(market_brier, 4),
        "brier_skill_score":  round(bss, 4),
        "by_city":            by_city,
    }


def export_calibration_csv(filepath: str) -> int:
    """
    Export all resolved trades as a calibration CSV.

    Columns: trade_id, date, city, bucket_lo, bucket_hi, bucket_unit,
             direction, model_prob, market_prob, outcome,
             model_error, market_error, model_brier, market_brier

    Uses atomic write (write to .tmp then rename) so concurrent readers
    never see a partial file.
    Returns number of rows written.
    """
    resolved = db.get_resolved_trades()
    if not resolved:
        logger.info("No resolved trades to export")
        return 0

    tmp_path = filepath + ".tmp"
    rows_written = 0

    try:
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            # Acquire exclusive lock for the duration of the write
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                writer = csv.writer(f)
                writer.writerow([
                    "trade_id", "date", "city",
                    "bucket_lo", "bucket_hi", "bucket_unit", "direction",
                    "model_prob", "market_prob", "outcome",
                    "model_error", "market_error",
                    "model_brier", "market_brier",
                    "entry_price", "pnl",
                ])
                for t in resolved:
                    outcome_val = 1.0 if t["status"] == "won" else 0.0
                    model_err   = abs(t["model_prob"] - outcome_val)
                    market_err  = abs(t["market_prob"] - outcome_val)
                    writer.writerow([
                        t["trade_id"][:12],
                        t["target_date"],
                        t["city"],
                        t.get("bucket_lo", ""),
                        t.get("bucket_hi", ""),
                        t.get("bucket_unit", "C"),
                        t["direction"],
                        round(t["model_prob"], 4),
                        round(t["market_prob"], 4),
                        int(outcome_val),
                        round(model_err, 4),
                        round(market_err, 4),
                        round((t["model_prob"] - outcome_val) ** 2, 4),
                        round((t["market_prob"] - outcome_val) ** 2, 4),
                        round(t["entry_price"], 4),
                        round(t["pnl"] or 0, 2),
                    ])
                    rows_written += 1
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        # Atomic rename — readers always see a complete file
        os.replace(tmp_path, filepath)
        logger.info("Exported %d calibration rows to %s", rows_written, filepath)

    except Exception as e:
        # Clean up tmp file if something went wrong
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise e

    return rows_written


# ── Calibration curve ─────────────────────────────────────────────────────────

# Probability buckets for the calibration curve.
# All trades are mapped to P(our_bet_wins) before bucketing.
_CURVE_BUCKETS = [
    (0.50, 0.55),
    (0.55, 0.60),
    (0.60, 0.65),
    (0.65, 0.70),
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, 0.90),
    (0.90, 1.00),
]


def _p_win(trade: dict) -> float:
    """Normalise model_prob to P(our bet wins) regardless of YES/NO direction."""
    p = trade["model_prob"]
    return p if trade["direction"] == "YES" else (1.0 - p)


def compute_calibration_curve(trades: list[dict] | None = None) -> dict:
    """
    Build a calibration curve from resolved trades.

    For each probability bucket [lo, hi):
      - predicted:  midpoint of the bucket (what we claimed)
      - actual:     fraction of trades in this bucket that actually won
      - bias:       actual - predicted  (+ = underconfident, - = overconfident)
      - n:          number of resolved trades in this bucket

    Also returns:
      - overall_bias:      mean bias across buckets with >= MIN_N trades
      - shrinkage_factor:  recommended multiplier to apply to (model_prob - 0.5)
                           = actual_spread / predicted_spread, capped [0.5, 1.0]
      - by_market_type:    same curve broken down by temperature / tsa / crypto
    """
    MIN_N = 5  # minimum trades per bucket to include in output

    if trades is None:
        trades = db.get_resolved_trades()

    resolved = [t for t in trades if t["status"] in ("won", "lost")]
    if not resolved:
        return {"buckets": [], "overall_bias": None, "shrinkage_factor": None,
                "by_market_type": {}, "n_total": 0}

    def _build_curve(trade_list):
        buckets = []
        for lo, hi in _CURVE_BUCKETS:
            mid = (lo + hi) / 2
            subset = [t for t in trade_list if lo <= _p_win(t) < hi]
            if len(subset) < MIN_N:
                continue
            actual_rate = sum(1 for t in subset if t["status"] == "won") / len(subset)
            bias = actual_rate - mid
            buckets.append({
                "range":     f"{lo:.0%}–{hi:.0%}",
                "lo":        lo,
                "hi":        hi,
                "predicted": round(mid, 4),
                "actual":    round(actual_rate, 4),
                "bias":      round(bias, 4),
                "n":         len(subset),
            })
        return buckets

    all_buckets = _build_curve(resolved)

    # Overall bias: weighted mean across all buckets
    if all_buckets:
        total_n = sum(b["n"] for b in all_buckets)
        overall_bias = sum(b["bias"] * b["n"] for b in all_buckets) / total_n
    else:
        overall_bias = None

    # Shrinkage factor: ratio of actual spread to predicted spread.
    # Predicted spread = mean(|p_win - 0.5|), actual spread = mean(|outcome - 0.5|)
    # A value < 1.0 means the model is overconfident.
    pred_spreads  = [abs(_p_win(t) - 0.5) for t in resolved]
    actual_vals   = [1.0 if t["status"] == "won" else 0.0 for t in resolved]
    # Use simple linear regression slope: cov(p_win, outcome) / var(p_win)
    n = len(resolved)
    p_wins = [_p_win(t) for t in resolved]
    mean_p = sum(p_wins) / n
    mean_a = sum(actual_vals) / n
    cov = sum((p - mean_p) * (a - mean_a) for p, a in zip(p_wins, actual_vals)) / n
    var = sum((p - mean_p) ** 2 for p in p_wins) / n
    if var > 1e-9:
        slope = cov / var
        # slope ≈ 1.0 → perfectly calibrated; < 1.0 → overconfident; > 1.0 → underconfident
        # Floor at 0.75: the raw slope can drop to ~0.5 on overconfident small samples,
        # but the MIN_WIN_PROB entry gate already removes the most overconfident bets, so
        # a 0.5 shrink double-penalises and starves trade volume. Empirically shrink≈0.75
        # jointly maximises realised PnL and win-rate in trade replay while still
        # correcting the documented overconfidence; it relaxes toward 1.0 as calibration
        # improves. See SHRINKAGE_FLOOR.
        shrinkage_factor = round(max(SHRINKAGE_FLOOR, min(1.50, slope)), 3)
    else:
        shrinkage_factor = None

    # Per market type
    market_types = {t.get("market_type", "temperature") for t in resolved}
    by_market_type = {}
    for mt in sorted(market_types):
        subset = [t for t in resolved if t.get("market_type", "temperature") == mt]
        by_market_type[mt] = {
            "n":       len(subset),
            "buckets": _build_curve(subset),
        }
        if by_market_type[mt]["buckets"]:
            mt_n = sum(b["n"] for b in by_market_type[mt]["buckets"])
            by_market_type[mt]["overall_bias"] = round(
                sum(b["bias"] * b["n"] for b in by_market_type[mt]["buckets"]) / mt_n, 4
            )
        else:
            by_market_type[mt]["overall_bias"] = None

    return {
        "buckets":          all_buckets,
        "overall_bias":     round(overall_bias, 4) if overall_bias is not None else None,
        "shrinkage_factor": shrinkage_factor,
        "by_market_type":   by_market_type,
        "n_total":          len(resolved),
    }


# ── Shrinkage factor storage / retrieval ──────────────────────────────────────

MIN_TRADES_FOR_SHRINKAGE = 15  # need at least this many to trust the correction

# Gentlest shrink we will apply. The calibration slope can fall to ~0.5 on
# overconfident samples, but the MIN_WIN_PROB entry gate already filters the most
# overconfident bets, so a harder shrink double-penalises and starves volume.
# 0.75 jointly maximises realised PnL and win-rate in resolved-trade replay.
SHRINKAGE_FLOOR = 0.75

# Weather/temperature markets are recorded with market_type 'daily' or 'weekly',
# but edge_calculator reads the calibration factor via get_shrinkage_factor("temperature").
# Group those raw types under the 'temperature' family so the factor is both
# computed and found. tsa/crypto stay separate.
SHRINKAGE_FAMILIES = {
    "temperature": ("temperature", "daily", "weekly"),
    "tsa":         ("tsa",),
    "crypto":      ("crypto",),
}


def update_shrinkage_factors() -> dict:
    """
    Recompute calibration curves per market type, compute shrinkage factors,
    and persist them in kv_store.  Called at end of --calibration.

    Returns dict: {market_type: shrinkage_factor}
    """
    import db as _db
    all_trades = _db.get_resolved_trades()
    stored = {}

    for family, raw_types in SHRINKAGE_FAMILIES.items():
        subset = [t for t in all_trades
                  if t.get("market_type", "daily") in raw_types]
        if len(subset) < MIN_TRADES_FOR_SHRINKAGE:
            logger.debug("Shrinkage for %s: only %d trades — skipping", family, len(subset))
            continue
        curve = compute_calibration_curve(subset)
        sf = curve.get("shrinkage_factor")
        if sf is not None:
            _db.set_kv(f"cal_shrinkage_{family}", str(sf))
            stored[family] = sf
            logger.info("Shrinkage factor stored: %s = %.3f (n=%d)", family, sf, len(subset))

    return stored


def get_shrinkage_factor(market_type: str = "temperature") -> float:
    """
    Return the stored shrinkage factor for a market type.
    Falls back to 1.0 (no correction) if not yet computed or too few trades.
    """
    import db as _db
    val = _db.get_kv(f"cal_shrinkage_{market_type}")
    if val is not None:
        try:
            sf = float(val)
            # Sanity bounds: don't apply extreme corrections
            return max(SHRINKAGE_FLOOR, min(1.50, sf))
        except ValueError:
            pass
    return 1.0
