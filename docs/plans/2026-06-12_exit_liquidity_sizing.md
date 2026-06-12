# Exit-Liquidity-Aware Entry Sizing — Spec

**Date:** 2026-06-12
**Status:** Phase 1 IMPLEMENTED 2026-06-12 (measure-only; `trades.exit_depth_usdc`,
`EXIT_DEPTH_WINDOW=0.05`, shared `data/polymarket.exit_side_levels` also now backs
the closing-soon gate). Phase 2 NOT implemented — tune from phase-1 data after
~2 weeks / ~50 entries.
**Scope:** entry-side risk check. Phase 1 is measure-only (zero behavior change);
phase 2 trims size and is a trading-behavior change → paper forward test first,
per project discipline.

## Context

External review of thin-market exit mechanics ("size to the exit, not the
entry") cross-checked against the codebase. Most of it is already covered by
the 2026-06-10 live-execution-integrity work:

- Hold-to-resolution backstop for unfillable exits (`exit_fill_status='held_to_resolution'`);
  redemption has infinite depth — early exits are the only liquidity problem.
- GTC limit exits with poll/cancel (never market sells); edge-reversed exits
  repost once, deeper.
- CLOSING-SOON exits gated on bid-within-10¢-of-fair AND depth ≥ position shares
  (`_closing_soon_liquidity_ok`, main.py).

## The gap

The entry depth gate (`paper_broker.py:38-64`, `MIN_BOOK_DEPTH_USDC = 150`) is
the only "check the book before entering" control, and it measures the wrong
thing:

1. **Wrong side.** It sums bid + ask depth combined. A book with $140 ask / $10
   bid passes — and a YES position bought there has no exit bid. The exit side
   for a YES bet is the YES bid stack; for a NO bet it is the NO bid stack
   (= 1 − YES asks, the same transform `_closing_soon_liquidity_ok` uses).
2. **No price window.** Top-5 levels at any price count; $100 bid at 0.30 under
   a 0.60 fair "counts" as depth but is a catastrophic exit.
3. **Pass/fail, not size-aware.** $150 of depth admits a $15 trade and would
   admit a $150 trade identically. The advice's core point: max position is
   bounded by the book, not by Kelly.

Materiality today: trades are capped at $15 vs a $150 combined gate, so
position ≈ ≤10% of visible depth — mostly fine. The asymmetric-book case (1)
is the live risk at current size; (2)+(3) become live risks if MAX_TRADE_USDC
grows.

## Constraint: not backtestable

We do not store historical order-book snapshots, so no replay can say how often
an exit-depth cap would have bound or what it would have saved. Validation must
be forward, which dictates the two-phase design.

## Design

### Phase 1 — measure only (ship immediately, both modes)

At entry (in `execute_paper_trade`, where the book is already fetched), compute
and persist:

```
exit_depth_usdc = Σ (price × size) over EXIT-side levels with
                  price ≥ (exit_side_best − EXIT_DEPTH_WINDOW)
```

- Exit side per direction as in `_closing_soon_liquidity_ok` (YES → YES bids;
  NO → 1 − YES asks). Reuse/extract that level transform into a shared helper
  (e.g. `data/polymarket.exit_side_levels(book, direction)`) so the two call
  sites cannot drift.
- New trades column `exit_depth_usdc REAL` (guarded ALTER TABLE, same pattern
  as the 06-10 migration). NULL for legacy rows.
- New config: `EXIT_DEPTH_WINDOW = 0.05` (5¢ window, per the review's
  rule of thumb).
- Zero behavior change: nothing reads the value yet. Log line per entry:
  `exit-depth: $X within 5¢ (size $Y → Z% of exit depth)`.

### Phase 2 — act (paper first, promote like other gates)

After ~2 weeks of phase-1 data (or ~50 entries), pick thresholds from the
observed distribution and activate in `paper_config.py`:

1. **Size cap:** `size_usdc ≤ EXIT_DEPTH_FRACTION × exit_depth_usdc`
   (proposed default 0.50 — never be more than half the near-fair exit depth).
   Trim, don't skip, mirroring the city-date-cap trim behavior.
2. **Hard floor:** skip entirely if `exit_depth_usdc < EXIT_DEPTH_MIN_USDC`
   (proposed $30 — an exit book thinner than 2× one trade is a no-trade).
   This replaces the asymmetric-book blind spot of the combined gate; keep the
   existing $150 combined gate as-is (it also guards entry fill quality).
3. Inert defaults in `config.py` (`EXIT_DEPTH_FRACTION = 1e9`,
   `EXIT_DEPTH_MIN_USDC = 0`) so live is untouched until promoted — same
   pattern as T_PLUS_ONE_MIN_STD.

Forward-test read-out: compare trimmed/skipped entries' counterfactual outcomes
(we keep logging the would-have-been size) against the realized book, exactly
like the other 06-09 forward-test lines. Note: since live config was synced to
paper on 06-10, decide at promotion time whether this follows automatically or
stays paper-only longer.

### Out of scope

- Ladder/scale-out exits and post-inside-spread passive exit pricing: not worth
  complexity at ≤$15 trades; revisit if MAX_TRADE_USDC exceeds ~$50.
- TSA/crypto markets (already exempt from the depth gate).

## Open questions

1. Should the 5¢ window scale with spread (thin internationals run 8–15¢
   spreads where a fixed 5¢ window may find zero depth and veto everything)?
   Phase-1 data answers this — if median exit_depth within 5¢ is ~$0 on markets
   we profitably trade, widen to `max(0.05, 1.0 × spread)`.
2. Should exit_depth also gate the boundary-proximity / high-conviction size
   boosts? Simpler to let the cap apply last, after all multipliers.
