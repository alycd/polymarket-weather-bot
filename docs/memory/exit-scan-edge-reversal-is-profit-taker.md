---
name: exit-scan-edge-reversal-is-profit-taker
description: "Exit-scan EDGE-REVERSAL on a NO is a profit-taker not a stop-loss; live-nowcast model_prob in it was validated and REJECTED (only cuts winners, net-negative, spike risk unprovable)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

The exit-scan EDGE-REVERSAL rule (`cmd_exit_scan`, main.py ~L1494) on a **NO** position fires when
`current_mid(YES) < model_prob(YES) − EDGE_REVERSAL_MIN(0.10)`. Since at NO entry `mid > model_prob`
(positive edge), this triggers when the market YES mid **drops** = the NO appreciates = the market
moved IN OUR FAVOR. **So NO edge-reversal is a profit-taking / edge-exhausted exit, NOT a stop-loss.**
In production it almost never fires anyway: of 182 settled paper trades only 6 are `stop_loss`
(all small losses); 176 held to resolution by design.

**Proposal REJECTED 2026-06-14 (paper-only validation, no code changed):** swap the stale entry
`model_prob` for a LIVE nowcast model_prob (T+0 only) in edge-reversal. Upper-bound replay
(running_max set to actual daily high, ensemble_mean backed out of stored model_prob+std, t df=4,
vs real intraday `price_history` mids):
- net-new exits over the existing rule: 4/15/18/10 at threshold 0.10/0.15/0.20/0.25 — **non-monotonic** (sample-fit, same pattern as the rejected T+1 edge floor in [[tplus1-leadtime-regime-split]]).
- **100% of net-new exits land on WINNERS; ZERO losers cut** at any threshold.
- net P&L delta vs hold-to-resolution is **negative at every threshold** (−$6 to −$13).
Swapping in live model_prob doesn't change the formula/threshold; when the nowcast *confirms* the
NO (running_max overshoots → hard-zero → live_mp→0) it fires LESS, and fires more only when live_mp
is HIGH vs a LOW market mid (the profit-taker condition).

**Why it can't even be validated cleanly:** the nowcaster's dominant input is the intraday
running-max from live ASOS/METAR, but `historical_obs` stores only ONE row per station-day (the
final archived high) — **no intraday running-max path is persisted**. `price_history.model_prob`
(live scan-time blended prob) is populated in only 251/33,999 rows, all ≈2026-06-12+, covering just
15/88 T+0 trades. The model half of the counterfactual is **unreconstructable**; only the market
half (84/88 T+0 trades have intraday mids) is.

**Spike risk is real and UNPROVABLE-safe:** won T+0 NO trades whose high undershot the bucket
landed a **median 0.6°C** below `bucket_lo` (24/32 within 1.5°C). running_max is monotone and the
+1°C hard-zero margin guards only the upper boundary — a transient ~1°C spike could push running_max
into the bucket, spike live_mp(YES), and fire a premature exit on an eventual winner. The final-high
archive hides such transient spikes, so the false-positive count can't be bounded down. Supports the
user's risk-averse instinct.

**How to apply:** prefer a MANUAL exit button (human force-close) over auto live-model exit — zero
automated premature-exit risk. Don't re-backtest this; any revisit needs intraday running-max
logged first, then a forward paper test. Combine with the overconfidence warning in
[[calibration-shrinkage-inert]] (a live-model trigger is exactly the over-eager signal to avoid).
Full analysis: docs/plans/2026-06-14_live_model_exit_reversal_validation.md.
