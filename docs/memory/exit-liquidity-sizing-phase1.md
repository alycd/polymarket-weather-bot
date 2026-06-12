---
name: exit-liquidity-sizing-phase1
description: exit_depth_usdc measured (not acted on) at every entry since 2026-06-12; phase-2 size cap/floor to be tuned from logged distribution ~2026-06-26
metadata: 
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

Phase 1 of docs/plans/2026-06-12_exit_liquidity_sizing.md shipped 2026-06-12 (commit 6766d51): every temperature entry records `trades.exit_depth_usdc` — exit-side book depth ($) within EXIT_DEPTH_WINDOW (0.05) of exit-side best. Measure-only; nothing gates on it. NULL for legacy/tsa/crypto rows. Shared transform `data/polymarket.exit_side_levels()` backs both this and the closing-soon exit gate.

**Why:** the $150 entry depth gate counts bid+ask combined — an asymmetric book passes with no exit-side liquidity. Can't backtest (no historical book snapshots), so thresholds must come from forward-logged data.

**How to apply:** after ~2 weeks / ~50 entries (≈2026-06-26), analyze the exit_depth_usdc distribution and decide phase 2: size cap (proposed ≤0.50× exit depth, trim not skip) + hard floor (proposed skip < $30), paper first with inert config.py defaults like [[tplus1-leadtime-regime-split]]. Key open question the data answers: does a fixed 5¢ window find ~zero depth on profitably-traded thin internationals (10¢+ spreads)? If so, widen to max(0.05, 1×spread) before gating. See also [[live-execution-integrity-spec]].
