# Validation: live-nowcast model_prob in exit-scan edge-reversal (T+0)

Date: 2026-06-14 · PAPER-ONLY analysis, no code/config changed · Author: quant agent

## Proposal under test
`cmd_exit_scan()` (main.py ~L1494) reads stale **entry-time** `model_prob` for its
EDGE-REVERSAL rule. Proposed: for T+0 (target_date==today) open positions, recompute
`model_prob` LIVE via the nowcaster and feed that into edge-reversal so the bot can cut a
same-day position whose obs turned against it. T+1 untouched (no live obs).

## Baseline (settled paper book, 182 resolved)
- T+0: N=88, 67.0% win, **+$237.95**, +19.3% ROI — the entire profit engine; 86/88 are NO bets.
- T+1: N=94, **−$40.79**.
- Actual early exits ever taken: **6** `stop_loss` trades (all small losses, exit<entry); the
  other 176 held to resolution. Edge-reversal essentially never fires in production today.

## CRITICAL DATA LIMITATION (the verdict turns on this)
A faithful replay of the *exact* rule is **impossible** from stored data:
1. `historical_obs` stores **one row per station-day** = the FINAL archived daily high. There is
   **no stored intraday running-max path**. The nowcaster's dominant input (running_max from live
   ASOS/METAR) was never persisted, so the live model_prob at each intraday timestamp cannot be
   reconstructed faithfully.
2. `price_history.model_prob` (the live, nowcast-blended scan-time prob) is populated in only
   **251 / 33,999 rows**, all from ≈2026-06-12+. Only **15 / 88** T+0 trades have any intraday
   live model_prob logged. Faithful replay set is too small and too recent.
3. Intraday MARKET price coverage is fine: **84/88 (95%)** T+0 trades have ≥1 post-entry
   `price_history` mid, median ~12 points. So the market half is reconstructable; the model half is not.

Reconstruction used: back out ensemble_mean from stored model_prob+std (Student-t df=4), set
running_max = actual daily high (the strongest the obs signal ever gets → **upper bound** on how
often the live rule fires), replicate `compute_nowcast_bucket_prob`, and compare against real
intraday mids. This OVER-states firing, so true effect ≤ reported.

## Mechanism finding (why the proposal misfires)
For a **NO** trade the existing rule fires when `current_mid(YES) < model_prob(YES) − 0.10`, i.e.
when the market YES mid drops well **below** the model's YES prob. At NO entry `mid > model_prob`
(positive edge), so this condition triggers as the **market moves IN OUR FAVOR** (NO appreciates).
**Edge-reversal on a NO is a profit-taking / edge-exhausted exit, not a stop-loss.** It fires on
winners. Swapping in a live model_prob does NOT change the formula or threshold; when the nowcast
*confirms* the NO (running_max overshoots → live_mp→0) the threshold drops and the rule fires
LESS, and it only fires more when live_mp is HIGH while the market mid is LOW.

## Results
Net-new exits the proposed rule adds beyond the existing rule (lowest-mid replay, upper bound):

| threshold | net-new exits | of which WINNERS (false-pos) | losers cut | net P&L delta vs hold |
|-----------|---------------|------------------------------|------------|-----------------------|
| 0.10 | 4 | 4 | 0 | **−$6.13** |
| 0.15 | 15 | 15 | 0 | **−$13.40** |
| 0.20 | 18 | 18 | 0 | **−$10.87** |
| 0.25 | 10 | 10 | 0 | **−$9.15** |

- **100% of net-new exits are on WINNING positions. Zero losers cut at any threshold.**
- Net P&L delta is **negative at every threshold** (−$6 to −$13).
- Firing count is **non-monotonic** in threshold (4→15→18→10) — the sample-fit instability
  pattern already rejected for the T+1 edge floor ([[tplus1-leadtime-regime-split]]).

## Spike vulnerability (irreducible blind spot)
For won T+0 NO trades whose high landed below the bucket (32 of 58 wins), the actual high landed a
**median 0.6°C** below `bucket_lo`; **24 of 32 within 1.5°C**. The nowcaster's running_max is
monotone and its +1°C hard-zero margin guards only the upper bucket boundary, not the lower one. A
transient ~1°C ASOS spike would push running_max into the bucket, spike live_mp(YES) up, and could
fire a premature NO exit on a position that ultimately won. `historical_obs` stores only the final
high, so the count of such transient spikes is **unobservable** — exactly the user's fear, and the
data cannot bound it down.

## VERDICT: REJECT auto live-model exit. Prefer the manual exit button.
- Replay (upper bound) shows the change only crystallizes winners early and is net-negative; it
  never cut a loser. The bot's hold-to-resolution design is already correct for this book.
- The model is overconfident on its selected bets ([[calibration-shrinkage-inert]]); a live-model
  trigger is exactly the over-eager signal that memory warns against.
- The spike-driven false-positive risk is real (tight 0.6°C median cushion) and **cannot be proven
  safe from stored data** — this directly supports the user's risk-averse instinct.
- A **manual exit button** (human-initiated force-close) sidesteps model noise, adds zero automated
  premature-exit risk, and is the better near-term move. If auto-exit is ever revisited it must be a
  forward paper test (the historical book can't validate it), AND would need intraday running-max
  logging added first.

## Rollback
N/A — no code/config changed.

## Re-litigation guard
Do NOT re-run this as a backtest: the model half of the counterfactual is unreconstructable
(no intraday running-max persisted). Any future test must (1) first persist intraday running_max,
then (2) run forward in paper. The mechanism point stands regardless of data: NO edge-reversal is a
profit-taker, not a stop-loss.
