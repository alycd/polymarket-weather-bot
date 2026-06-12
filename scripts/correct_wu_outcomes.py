"""
correct_wu_outcomes.py  (PART 3 — REPORT-FIRST, do NOT run without approval)

What the WU audit (analysis/wu_audit.py) actually found
-------------------------------------------------------
Of 165 resolved daily trades in paper_trades.db:
  * 145 are `exit_scan` — sold at the live CLOB market price (0 < exit_price < 1)
    BEFORE official settlement. They carry NO bucket outcome and NO stored
    actual_high_c. The WU-vs-ASOS resolution-source question is MOOT for them:
    no weather source resolved them, and re-resolving would overwrite a realised
    market exit with a hypothetical settlement. They are OUT OF SCOPE.
  * 20 are `polymarket` — settled at exactly 0.0 / 1.0 from Polymarket's own
    `winner` field (ground truth for the money). These are the only trades with a
    bucket outcome.

Outcome flips: applying WU integer-print semantics flags exactly ONE candidate,
Denver 2026-05-28 (WU=75°F in a "74-75°F" market → integer-closed semantics say
YES won → NO lost; our DB says NO won). BUT a live Polymarket CLOB query confirms
that market settled YES=loser / NO=winner — i.e. OUR DB IS CORRECT and Polymarket
itself did NOT score 75°F as inside the 74-75 bucket that day. So this is a genuine
WU-vs-PM data divergence on one boundary day, NOT a bug in our records. Flipping it
would make our book DISAGREE with the real settlement.

==> Conclusion: there are ZERO outcome corrections to apply. PM `winner` already gave
    us the right answers. This script therefore defaults to NOT changing any outcome.

What this script CAN safely do (opt-in, --apply-temp only)
----------------------------------------------------------
The stored actual_high_c on 2-3 of the 20 PM-settled trades drifts up to ~1.1°C from
WU's print (it was fetched from ASOS/ERA5 at resolution time, not WU). actual_high_c
feeds the bias corrector. Refreshing it to the WU native print makes the bias-correction
data consistent with Polymarket's resolution source. This touches ONLY actual_high_c
(via db.update_trade_outcome_source-adjacent UPDATE) — it does NOT change status,
exit_price, pnl, or bankroll.

Modes
-----
  (default)        DRY RUN. Print exactly what WOULD change. No writes.
  --apply-temp     Refresh actual_high_c to the WU native value for PM-settled temp
                   trades where it drifts >THRESH_C. Does NOT touch outcome/bankroll.
  --verify-pm      Re-query live Polymarket for each PM-settled trade and report (do
                   not auto-flip) any outcome that PM now reports differently. If any
                   appear, surface them for human review — do not write.

db.update_trade_outcome (db.py:703) IS correct for genuine flips (it reverses the old
bankroll delta and applies the new one, recomputing pnl) — but per the audit there are
no flips to apply, so this script does not call it by default.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from utils import f_to_c
from broker.position_manager import get_actual_high_native, _query_polymarket_outcome, _get_clob_token

THRESH_C = 0.6  # only refresh actual_high_c when WU disagrees by more than this


def _settled_pm_trades():
    return [t for t in db.get_resolved_trades()
            if t.get("outcome_source") == "polymarket"
            and (t.get("market_type") in ("daily", None))]


def verify_pm(trades):
    print("\n=== --verify-pm: re-query live Polymarket winner per settled trade ===")
    disagreements = []
    for t in trades:
        tok = _get_clob_token(t)
        winner = _query_polymarket_outcome(tok, t.get("market_id", ""))
        time.sleep(1.0)
        if winner is None:
            print(f"  {t['city']:<14} {t['target_date']}  PM no longer queryable (aged out) — keep recorded {t['status']}")
            continue
        yes_won = (winner == "yes")
        pm_outcome = ("won" if yes_won else "lost") if t["direction"] == "YES" else ("won" if not yes_won else "lost")
        ok = (pm_outcome == t["status"])
        marker = "" if ok else "  <<< PM DISAGREES — REVIEW"
        print(f"  {t['city']:<14} {t['target_date']} dir={t['direction']} recorded={t['status']} PM={pm_outcome}{marker}")
        if not ok:
            disagreements.append((t, pm_outcome))
    if disagreements:
        print(f"\n  {len(disagreements)} trade(s) where live PM disagrees with our DB — surfaced for HUMAN review.")
        print("  This script will NOT auto-apply these. Decide per-trade.")
    else:
        print("\n  All settled outcomes agree with live Polymarket. No outcome corrections.")
    return disagreements


def refresh_temps(trades, apply: bool):
    print(f"\n=== {'--apply-temp (WRITING)' if apply else 'temp-refresh DRY RUN'}: "
          f"actual_high_c vs WU (threshold {THRESH_C}°C) ===")
    changes = []
    for t in trades:
        unit = t["bucket_unit"]
        try:
            wu_native, src = get_actual_high_native(t["icao"], t["target_date"], t["city"], unit)
            time.sleep(2.2)
        except Exception as e:
            print(f"  {t['city']:<14} {t['target_date']}  WU fetch failed ({e}) — skip")
            continue
        if src != "wunderground":
            print(f"  {t['city']:<14} {t['target_date']}  WU unavailable (src={src}) — skip temp refresh")
            continue
        wu_c = f_to_c(wu_native) if str(unit).upper().startswith("F") else wu_native
        stored = t.get("actual_high_c")
        if stored is None:
            drift = None
        else:
            drift = abs(wu_c - stored)
        if stored is None or (drift is not None and drift > THRESH_C):
            changes.append((t, wu_c, stored, drift))
            print(f"  {t['city']:<14} {t['target_date']} stored={stored}°C -> WU {wu_native}{unit}={wu_c:.2f}°C "
                  f"(drift={'n/a' if drift is None else f'{drift:.2f}'}°C)"
                  + ("  [WOULD UPDATE]" if not apply else "  [UPDATING]"))
            if apply:
                with db._conn() as conn:
                    conn.execute("UPDATE trades SET actual_high_c=? WHERE trade_id=?",
                                 (round(wu_c, 2), t["trade_id"]))
                # also store WU obs for bias correction
                db.upsert_historical_obs(t["icao"], t["target_date"], round(wu_c, 2), "wunderground")
    if not changes:
        print("  No actual_high_c values drift beyond threshold. Nothing to refresh.")
    else:
        print(f"\n  {len(changes)} actual_high_c value(s) "
              f"{'updated' if apply else 'WOULD be updated'}. Outcome/pnl/bankroll untouched.")
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-temp", action="store_true",
                    help="WRITE: refresh drifted actual_high_c to WU native (no outcome/bankroll change)")
    ap.add_argument("--verify-pm", action="store_true",
                    help="re-query live Polymarket and report (not apply) any outcome disagreement")
    args = ap.parse_args()

    trades = _settled_pm_trades()
    print(f"PM-settled daily trades to consider: {len(trades)}")
    print("NOTE: exit_scan trades (145) are NOT touched — they have no bucket outcome.")
    print("NOTE: per audit, there are ZERO outcome flips to apply (PM winner is ground truth).")

    if args.verify_pm:
        verify_pm(trades)

    refresh_temps(trades, apply=args.apply_temp)

    if not args.apply_temp:
        print("\n(DRY RUN — no writes. Re-run with --apply-temp to refresh actual_high_c,")
        print(" and/or --verify-pm to re-check outcomes against live Polymarket.)")


if __name__ == "__main__":
    main()
