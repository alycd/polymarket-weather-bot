"""
Migrate calibration learnings from paper_trades.db → live_trades.db.

Run this once before switching to live trading, after at least a month of
paper trading has accumulated bias corrections and historical observations.

What gets copied:
  stations          — city configs and station status
  historical_obs    — ASOS + ERA5 observed actuals (ground truth)
  model_forecasts   — historical NWP predictions (needed to recompute bias)
  bias_corrections  — per-city/model/month error corrections
  climatology       — 30-year WMO baselines

Also copied: cal_shrinkage_* keys from kv_store. The shrinkage factor is computed
from resolved trades, which live starts with none of — without seeding it,
get_shrinkage_factor() falls back to 1.0 and live trades WITHOUT the
overconfidence correction paper runs with.

What stays fresh in live:
  trades, daily_pnl, bankroll, scan_log, markets, price_history,
  kv_store (except cal_shrinkage_* keys)
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_DB = os.path.join(DB_DIR, "paper_trades.db")
LIVE_DB  = os.path.join(DB_DIR, "live_trades.db")

TABLES_TO_COPY = [
    "stations",
    "historical_obs",
    "model_forecasts",
    "bias_corrections",
    "climatology",
]

def main():
    if not os.path.exists(PAPER_DB):
        print(f"ERROR: {PAPER_DB} not found")
        return

    # Backup live DB before touching it
    if os.path.exists(LIVE_DB):
        backup = LIVE_DB.replace(".db", f"_pre_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(LIVE_DB, backup)
        print(f"Backed up live DB → {backup}")

    paper = sqlite3.connect(PAPER_DB)
    live  = sqlite3.connect(LIVE_DB)
    live.execute("PRAGMA journal_mode=WAL")

    for table in TABLES_TO_COPY:
        rows_before = live.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        live.execute(f"DELETE FROM {table}")

        rows = paper.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  {table:<20} — empty in paper, skipping")
            continue

        cols = [d[0] for d in paper.execute(f"SELECT * FROM {table} LIMIT 0").description]
        placeholders = ",".join("?" * len(cols))
        live.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", rows)
        live.commit()

        rows_after = live.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<20} — {rows_before} → {rows_after} rows")

    # Seed calibration shrinkage factors. These normally come from resolved
    # trades, which live has none of at migration time — without this, live
    # falls back to shrinkage 1.0 (no overconfidence correction).
    shrink_rows = paper.execute(
        "SELECT key, value, updated_at FROM kv_store WHERE key LIKE 'cal_shrinkage_%'"
    ).fetchall()
    if shrink_rows:
        live.executemany(
            "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
            shrink_rows,
        )
        live.commit()
        for key, value, _ in shrink_rows:
            print(f"  {key:<20} — seeded ({value})")
    else:
        print("  cal_shrinkage_*      — none in paper, skipping")

    paper.close()
    live.close()
    print("\nDone. Run `python main.py --backfill --live` afterwards to freshen any stale forecasts.")

if __name__ == "__main__":
    main()
