"""
Backfill daily_pnl from existing resolved trades.

Net bankroll effect per trade = pnl column (won: profit, lost: -stake, void: 0).
We anchor on the current bankroll and reconstruct backwards, then write
forward-ordered daily rows.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db

def backfill(mode: str):
    db.set_mode(mode)
    current_bankroll = db.get_bankroll()
    all_trades = db.get_all_trades()

    resolved = [
        t for t in all_trades
        if t["status"] in ("won", "lost", "stop_loss", "void", "voided")
        and t.get("resolved_at")
        and t.get("pnl") is not None
    ]
    if not resolved:
        print(f"[{mode}] No resolved trades — nothing to backfill.")
        return

    resolved.sort(key=lambda t: t["resolved_at"])

    # reconstruct bankroll at each resolution event, working backwards from now
    # net effect of each trade on bankroll = pnl column value
    # so bankroll_before_trade_N = current - sum(pnl for trades >= N)
    total_pnl = sum(t["pnl"] for t in resolved)
    running = current_bankroll - total_pnl   # bankroll before the earliest trade resolved

    # build per-day buckets in chronological order
    days = {}
    for t in resolved:
        day = t["resolved_at"][:10]
        pnl = t["pnl"]
        if day not in days:
            days[day] = {"start": running, "end": running, "w": 0, "l": 0, "resolved": 0}
        days[day]["end"]      += pnl
        days[day]["resolved"] += 1
        if t["status"] == "won":
            days[day]["w"] += 1
        elif t["status"] in ("lost", "stop_loss"):
            days[day]["l"] += 1
        running += pnl

    # clear existing rows so we start clean
    with db._conn() as conn:
        conn.execute("DELETE FROM daily_pnl")

    for day, s in sorted(days.items()):
        db.upsert_daily_pnl(
            pnl_date=day,
            starting=s["start"],
            ending=s["end"],
            placed=0,
            resolved=s["resolved"],
            wins=s["w"],
            losses=s["l"],
        )
        net = s["end"] - s["start"]
        print(f"[{mode}] {day}  start=${s['start']:.2f}  end=${s['end']:.2f}  net={'+' if net>=0 else ''}{net:.2f}  {s['w']}W/{s['l']}L")

    print(f"[{mode}] Done — {len(days)} days backfilled.")

if __name__ == "__main__":
    modes = sys.argv[1:] or ["paper", "live"]
    for m in modes:
        backfill(m)
