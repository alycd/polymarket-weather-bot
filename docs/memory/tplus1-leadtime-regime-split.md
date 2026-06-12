---
name: tplus1-leadtime-regime-split
description: "The book is two regimes by lead time — T+0 carries all profit, T+1 is the noise regime; the best T+1 gate is ensemble_std, NOT an edge floor"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43e3bdfb-03e2-47c8-aa1e-6bd60543ccc7
---

The settled paper book splits cleanly by **lead time** (entry-date vs target-date), and this is the dominant structure in the data (155 settled, 2026-06-09):
- **T+0 (same-day): N=66, 66.7% win, +$163.50, +17.7% ROI** — gets the nowcaster live-ASOS blend (real ground truth).
- **T+1 (day-before): N=89, 59.6% win, −$82.15, −6.7% ROI** — pure forecast-vs-market, the overconfident-noise regime ([[calibration-shrinkage-inert]]).

**A proposed T+1 minimum-|edge| floor of 0.25 was tested and REJECTED as the fix.** On the full raw book it does NOT separate T+1 winners from losers (kept |edge|≥0.25 → −7.0% ROI ≈ dropped → −6.4% ROI); it only removes volume. Its apparent gain on the guarded book is sample-fitting — driven by four −$15 trades in the [0.18,0.25) band — and the T+1 win-rate-vs-|edge| curve is **non-monotonic** (100%→67%→50%→63%→70%): there is no "higher edge = better T+1 trade" signal. Stacked with the shipped `MAX_EDGE_ABS=0.40`, a 0.25 floor squeezes T+1 into the narrow [0.25,0.40] band (26 of 70 T+1 trades survive).

**The better T+1 gate is `ensemble_std`, not edge.** At T+1, tight model agreement (low std) means the specific bucket is likely hit → NO bets fail (T+1 std∈[0,1.0): N=24, 54% win, −13.9% ROI). A **T+1-only `ensemble_std ≥ 1.0` gate** beats the edge floor on every axis: guarded book 125→**101** trades (vs 81 for the floor), PnL $184→**$230** (vs $202), with a clean monotonic ramp (T+1 win% 62.9%→67.4%→72.4% at std 0.8→1.0→1.2). **Must be lead-conditioned**: at T+0 low-std trades are profitable (+10.1% ROI) because the nowcaster carries them — a global std raise would needlessly cut 14 profitable same-day trades.

**Why:** lead time, not edge magnitude, is the regime variable. The nowcaster's live obs is the entire edge at T+0; T+1 has none, so model-agreement (std) is the only usable T+1 reliability signal.

**How to apply:** **SHIPPED to PAPER 2026-06-09** as `T_PLUS_ONE_MIN_STD` (inert 0.0 in config.py; 1.0 in paper_config.py; **also 1.0 in live_config.py since 2026-06-10** — user synced live to paper wholesale, so this forward test is no longer paper-isolated), gated in `signals/edge_calculator.py` right after the global NO `ensemble_std` block. **Critical impl detail:** the gate computes the TRUE unclamped lead `(target_date − today).days` and fires only at `>=1` — do NOT reuse the function's `lead_days` variable, which is `max(1, …)` for horizon scaling and would misclassify same-day (T+0) markets as T+1 and wrongly gate them. Verified: T+0 untouched, T+1/T+2 gated. The ×0.75 T+1 stake trim was DEFERRED (lowers total PnL $230→$221, muddies forward attribution); the edge floor was REJECTED. **Forward review ~2026-06-16** — track as its own forward-test line (orthogonal axis to the b9cebb5 guards but stacked mid-window; attribute carefully). Full decision trail + eval block: docs/plans/2026-06-09_tplus1_leadtime_and_upstream.md.
