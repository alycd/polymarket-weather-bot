"""PnL calculations."""
import db


def compute_pnl_summary() -> dict:
    resolved   = db.get_realized_trades()   # won/lost/stop_loss — all realized P&L
    open_trades = db.get_open_trades()
    bankroll   = db.get_bankroll()

    total_pnl = sum(t["pnl"] for t in resolved if t["pnl"] is not None)
    # Categorise by realised P&L sign so stop-loss exits count as losses.
    wins   = [t for t in resolved if (t["pnl"] or 0) > 0]
    losses = [t for t in resolved if (t["pnl"] or 0) < 0]

    deployed = sum(t["size_usdc"] for t in open_trades)
    initial  = 1000.0
    pct_return = total_pnl / initial * 100

    # Stakes are pre-deducted from bankroll at entry (see db.resolve_trade),
    # so bankroll IS spendable cash — subtracting deployed again would
    # double-count the open stakes. Equity = cash + open stakes at cost.
    return {
        "bankroll":   bankroll,
        "initial":    initial,
        "deployed":   deployed,
        "available":  bankroll,
        "equity":     bankroll + deployed,
        "total_pnl":  total_pnl,
        "pct_return": pct_return,
        "n_resolved": len(resolved),
        "n_open":     len(open_trades),
        "n_wins":     len(wins),
        "n_losses":   len(losses),
        "win_rate":   len(wins) / len(resolved) * 100 if resolved else 0.0,
        "avg_win":    sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0.0,
        "avg_loss":   sum(t["pnl"] for t in losses) / len(losses) if losses else 0.0,
    }
