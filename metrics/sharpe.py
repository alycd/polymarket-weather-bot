"""Annualized Sharpe ratio on daily PnL returns."""
import math
from collections import defaultdict
import db


def compute_sharpe() -> float | None:
    resolved = [t for t in db.get_realized_trades() if t["pnl"] is not None]
    if len(resolved) < 4:
        return None

    daily: dict[str, float] = defaultdict(float)
    for t in resolved:
        day = (t.get("resolved_at") or t["entry_time"])[:10]
        daily[day] += t["pnl"]

    vals = [v for _, v in sorted(daily.items())]
    if len(vals) < 5:
        return None

    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
    std = math.sqrt(variance) if variance > 0 else None
    if not std:
        return None

    # Annualise: scale daily returns by sqrt(252) — standard convention.
    # Using observed trading-day count avoids sqrt(365) overstating Sharpe
    # when trading is sparse.
    return (mean / std) * math.sqrt(252)
