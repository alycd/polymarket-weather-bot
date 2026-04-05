"""PnL calculations."""
import db


def compute_pnl_summary() -> dict:
    resolved   = db.get_resolved_trades()
    open_trades = db.get_open_trades()
    bankroll   = db.get_bankroll()

    total_pnl = sum(t["pnl"] for t in resolved if t["pnl"] is not None)
    wins   = [t for t in resolved if t["status"] == "won"]
    losses = [t for t in resolved if t["status"] == "lost"]

    deployed = sum(t["size_usdc"] for t in open_trades)
    initial  = 1000.0
    pct_return = total_pnl / initial * 100

    return {
        "bankroll":   bankroll,
        "deployed":   deployed,
        "available":  max(0.0, bankroll - deployed),
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
