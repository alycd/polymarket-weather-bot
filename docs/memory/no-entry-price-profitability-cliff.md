---
name: no-entry-price-profitability-cliff
description: NO-bet profitability has a sharp cliff at entry price 0.65; capped paper NO_ENTRY_MAX_PRICE at 0.65
metadata: 
  node_type: memory
  type: project
  originSessionId: ea1880cb-a2a4-48cd-9e3c-1b31c60069f2
---

Resolved-trade replay (paper, 118 settled NO trades, entry ≥ 0.35, as of 2026-06-04)
shows NO-bet ROI by entry-price band: 0.35–0.45 +126%, 0.45–0.55 +6%, 0.55–0.60 +35%,
0.60–0.65 +15% — all profitable — then a cliff: 0.65–0.70 (n=37) −8.7%, 0.70–0.75 (n=20)
−5.0%. Win rate is flat across the cliff (67%→69%), so the loss is **payoff asymmetry**,
not forecast quality: NO at 0.70 needs a 70% win rate just to break even, and the model's
documented overconfidence (see [[calibration-shrinkage-inert]]) erodes that margin.

**Why:** the bot historically over-concentrated in the 0.65+ region (~45% of NO trades),
which is a net money-loser despite a decent win rate — wins pay too little to cover the
occasional full-price loss.

**How to apply:** capped paper `NO_ENTRY_MAX_PRICE` 0.75 → 0.65 in paper_config.py
(2026-06-04). Counterfactual: settled-NO ROI 11.5% → 26.4%, +$43 realized P&L, frees ~$756
capital to redeploy into the profitable 0.35–0.65 zone. PROMOTED to live_config.py
2026-06-10 (user synced live config to paper wholesale). NOTE: backtest.py CANNOT
validate entry-price-gate changes — it assumes a fixed 0.50 SIMULATED_MID, so the ceiling
never binds and results are identical; validate gate changes by resolved-trade replay instead.
The single enforcement point is signals/edge_calculator.py (~line 392).
