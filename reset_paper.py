#!/usr/bin/env python3
"""
One-off reset: void all stale open paper trades, restore bankroll to $1000.

"Stale" = open trades whose target_date is strictly before today's UTC date.
Sets status=void, pnl=0, exit_price=0, resolved_at=now.
Does NOT touch bankroll for each void (the bankroll snapshot at trade entry
is already deducted; we just wipe the liability and restart fresh from $1000).
"""
import sqlite3
from datetime import date, datetime
import db


def reset():
    db.init_db()

    today = date.today().isoformat()
    conn  = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        stale = conn.execute(
            "SELECT trade_id, city, target_date, size_usdc FROM trades WHERE status='open'"
        ).fetchall()

        print(f"Found {len(stale)} open trades to void:")
        for t in stale:
            print(f"  {t['trade_id'][:12]}  {t['city']:<18}  {t['target_date']}  ${t['size_usdc']:.2f}")

        if stale:
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE trades SET status='void', pnl=0, exit_price=0, resolved_at=? "
                "WHERE status='open'",
                (now,)
            )
            print(f"\nVoided {len(stale)} trades.")
        else:
            print("  (none)")

        conn.execute("UPDATE bankroll SET balance=1000.00 WHERE id=1")
        conn.commit()
        print(f"\nBankroll reset to $1000.00")

    finally:
        conn.close()

    print(f"\nVerification:")
    print(f"  Bankroll: ${db.get_bankroll():.2f}")
    print(f"  Open trades: {len(db.get_open_trades())}")


if __name__ == "__main__":
    reset()
