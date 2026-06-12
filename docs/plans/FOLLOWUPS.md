# Follow-ups Tracker

Living list of dated reviews, forward tests, and blocked rollout steps.
**Maintenance protocol:** when asked "what do we need to follow up on", read this
file, compare due dates to today, and report overdue/upcoming items. When an
item is acted on, move it to the Done section with the outcome and a commit/doc
reference — don't delete it. Add new forward tests and canary steps here when
they ship.

_Last updated: 2026-06-12_

## Open items

| Due | Item | Action when due | Source |
|---|---|---|---|
| **2026-06-16** | T+1 `ensemble_std ≥ 1.0` gate forward review (shipped paper 06-09, in LIVE config since 06-10 sync) | Evaluate T+1 trades since 06-09: gate-on book vs counterfactual; keep or rollback (`T_PLUS_ONE_MIN_STD = 0.0`). Track as its own line, separate from the 06-09 guards. | `2026-06-09_tplus1_leadtime_and_upstream.md` |
| **2026-06-23** | Accuracy-guards forward review: `MAX_EDGE_ABS=0.40`, YES pause (`ENABLE_YES_BETS=False`), high-conviction Kelly boost neutralized (shipped 06-09; in live since 06-10) | Check forward win-rate/ROI of would-have-been-blocked trades; decide keep/adjust each guard independently | `2026-06-09_forward_tests.md` |
| **2026-06-23** | Low-price win-prob relaxation review (`LOW_PRICE_WINPROB_THRESHOLD=0.45`, shipped 06-09) | Did the new sub-0.45-entry NO volume hold ≥ break-even? Rollback: `THRESHOLD = 0.0` | `2026-06-09_forward_tests.md` |
| **2026-06-26** | Exit-liquidity phase 2 (phase-1 `exit_depth_usdc` logging live since 06-12) | Analyze logged distribution (~50 entries): tune size cap (proposed ≤0.5× exit depth) + hard floor (proposed $30); decide whether the fixed 5¢ window must scale with spread on thin internationals; ship to paper with inert live defaults | `2026-06-12_exit_liquidity_sizing.md` |
| *blocked: deposit* | Live micro-canary (execution-integrity code shipped 06-11, never exercised with real money) | After depositing ~$50–100: set `MAX_TRADE_USDC≈2` in live, run 2–3 real entries + force one exit, verify positions/orders vs Polymarket UI, confirm `--reconcile` reports zero mismatches, restore `MAX_TRADE_USDC=15`, then `daemon --mode live` | `2026-06-10_live_execution_integrity.md` §5–6 |
| *canary + 2 weeks* | `held_to_resolution` outcome watch | Compare held-to-resolution exits vs what the old early-discount-sell path would have credited; confirm the policy is P&L-positive | `2026-06-10_live_execution_integrity.md` §6 risks |
| *trigger-based* | WU/ASOS boundary-trade analysis | IF boundary trades (actual within ~0.5°C of bucket edge) cluster as "won per ASOS, lost per settlement": compare ASOS max vs WU print vs settled outcome; candidate fix = feed nowcaster WU hourly prints | `2026-06-12_wu_asos_divergence.md` |
| *watch* | Warsaw on city watch-list (re-admitted; 50% win, breakeven, n=2 as of 06-09) | Re-exclude if <55% over ≥5 trades (same rule that caught Tokyo) | city-exclusion history in `paper_config.py` |
| *minor* | Consolidate the legacy 5%-drift daily reconciliation (scan-start) with the hourly `--reconcile` job | Merge or remove the old check so there's one reconciliation path | noted in 06-11 implementation report |
| *optional* | Dashboard: auto-refresh open-position outlooks every ~5 min (currently only refresh on user interaction) | Implement if wanted during canary monitoring | offered 06-12, not yet requested |

## Done

| Date | Item | Outcome |
|---|---|---|
| 2026-06-12 | WU-first resolution + integer-print semantics audit | Books clean (20/20 match PM settlements); fallback semantics fixed; 3 `actual_high_c` refreshed. Commit `806781b`. |
| 2026-06-12 | Exit-liquidity phase 1 (measure-only) | Shipped, commit `6766d51`; data clock started. |
| 2026-06-11 | Live execution integrity (WI-1..WI-6) | Implemented + 36/36 harness checks, commit `ec95e29`; rollout pending canary (see open items). |
| 2026-06-10 | Live config synced to paper; sig_type=3; paper→live calibration migration + shrinkage seeding | Commits `fb08687`, `ba7ccdd`, migration run by user 06-10. |
