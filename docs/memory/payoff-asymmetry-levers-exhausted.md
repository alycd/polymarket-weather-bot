---
name: payoff-asymmetry-levers-exhausted
description: Price-scaled edge and payoff-aware sizing both fail to beat the flat baseline on settled paper trades; 0.65 cap already captured the win
metadata: 
  node_type: memory
  type: project
  originSessionId: c5175f05-fe64-41ba-8b07-632b16447e1f
---

On 2026-06-08 investigated the payoff-asymmetry concern (binary markets: at entry price p>0.5 you risk more than you can win, since win pays stake·(1−p)/p but a loss costs the full stake; break-even win rate = p). Built a counterfactual replay over all 154 settled paper trades (P&L is exactly linear in stake, so stake reallocation is replayable).

Findings:
- **Price-scaled MIN_EDGE (raise the bar as price rises): does NOT help.** Every (pivot, k) config *reduced* total P&L vs the flat-0.12 baseline (+$96.35, 4.5% ROI). It only removes net-positive volume — the profitable 0.55–0.65 band gets cut, while the genuinely-bad 0.65+ zone was already removed by [[no-entry-price-profitability-cliff]] (its −$62 was all pre-cap; post-cap 0.65+ is gone).
- **Payoff-aware sizing: no robust win.** Naive size∝(1−p)/p → −$28 (over-concentrates the small cheap band). Best variant +$105 (+9%) but needed a $21 max stake, breaking the $15 max-loss rule. Every variant respecting the $15 cap ≈ baseline.
- Realized win/loss ratio by NO band: 0.35–0.45 → 1.41 (+49% ROI), 0.55–0.65 → 0.70 (+17%, carried by 70% win rate), 0.65+ → 0.45 (−6%). avg |edge| also *falls* with price (0.45 → 0.21).
- The two money-losing pockets (YES book −$48/43% win; NO 0.45–0.55 −$24/44% win) are **win-rate/calibration** problems, not payoff problems — addressed by S1 shrinkage, not sizing.

**Why:** the payoff-asymmetry lever is already spent (the 0.65 cap did it); the remaining book is thin-but-positive and dominated by the unfavorable-payoff 0.55–0.65 zone whose high win rate carries it. You can't gate or reallocate your way to better risk/reward from existing trades — every knob trims profitable volume.

**How to apply:** don't add price-scaled edge or payoff-tilt sizing. The only structurally-correct improvement is sourcing MORE sub-0.50 (favorable-payoff) bets by *relaxing* the gate below ~0.45 — but that adds trades the replay can't see, so it must be **forward paper-tested**, not backtested. Replay harness pattern: keep trade if abs(edge) ≥ threshold(p); new_pnl = old_pnl × (new_size/old_size).

**UPDATE 2026-06-09 — forward test now LIVE in paper.** Key finding while implementing: at low entry prices the binding gate is `MIN_WIN_PROB` (0.70 NO / 0.60 YES), NOT `MIN_EDGE` — because `p_win = actual_entry + effective_edge`, so a flat 0.70 floor forces edge ≥ 0.30 at entry 0.40. Relaxing MIN_EDGE there would be inert. So the implemented lever relaxes the *win-prob floor* below 0.45 toward `max(0.50, entry + 0.12)`, making MIN_EDGE the binding gate. Config: `LOW_PRICE_WINPROB_THRESHOLD/MARGIN/MIN_WIN_PROB_FLOOR` (inert 0.0 default in config.py → live unaffected; activated 0.45/0.12/0.50 in paper_config.py). Wired into the win-prob gate in signals/edge_calculator.py. **Review ~2026-06-23**: check whether sub-0.45 trades hold ≥ break-even win rate; rollback = set THRESHOLD back to 0.0.
