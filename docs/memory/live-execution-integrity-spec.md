---
name: live-execution-integrity-spec
description: "Live execution integrity IMPLEMENTED 2026-06-11 (fill polling, NO-exit token fix, resolve-only-on-fill, hourly reconcile); live rollout (fund + canary) still pending"
metadata:
  node_type: memory
  type: project
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

Audit on 2026-06-10 found live execution was fire-and-forget: fills assumed (order_id discarded), live NO exits sold `clob_token_yes` — a token not held — silently failing on-chain while the DB resolved with estimated P&L, GTC orders never cancelled, no reconciliation. Full spec: `docs/plans/2026-06-10_live_execution_integrity.md`.

**IMPLEMENTED 2026-06-11** (commit ec95e29, by weather-bot-quant agent, 36/36 mock-harness checks): trades schema carries clob_token_no/order ids/fill statuses; entries re-quote + poll ≤30s + cancel remainder + DB corrected or voided per actual fill; exits sell the held token, resolve only at confirmed fill prices, otherwise `held_to_resolution` (Polymarket auto-redeems at $1/share infinite depth); hourly `--reconcile` daemon job at :20 (janitor/pending-sweep/position cross-check/bankroll drift alert). Paper mode verified bit-for-bit unchanged. Test harness: `scripts/test_live_exec.py`.

**Why:** without it, DB bankroll/positions diverge arbitrarily from the wallet; most of the book is NO bets so the wrong-token bug hit most exits.

**How to apply:** live trading still needs the rollout steps before real sizing: deposit (~$50+; sizing math needs ≥$13 for any trade — 8% MAX_TRADE_FRACTION vs $1 floor), micro-canary at MAX_TRADE_USDC≈$2, then daemon `--mode live`. Account facts: pUSD collateral requires POLYMARKET_SIGNATURE_TYPE=3 (set 06-10; sig 0/1/2 read $0 for a funded account); `migrate_paper_to_live.py` seeds cal_shrinkage_* (without it live runs shrinkage 1.0); migration ran 06-10. Exit-fill accounting: stake pre-deducted at entry, `shares = size_usdc/entry_price`, so correcting those two columns to actual fills keeps all P&L math consistent. See [[exit-liquidity-sizing-phase1]].
