# Forward Tests — Accuracy Guards (S3) + Low-Price Payoff Test

**Date:** 2026-06-09
**Scope:** paper config only (live verified inert on every knob)
**Status:** ✅ Shipped to paper, running on the daemon (picked up per-scan). Evaluate in one week.
**Revisit:** **~2026-06-16** — run the [evaluation block](#evaluation-run-this-on-2026-06-16) and apply the decisions.

---

## TL;DR

A health check on 2026-06-09 (154 settled trades) found the model **badly overconfident** (stated 86% vs actual **63%** win — roughly double the +12pt gap at S1 time), with the losses concentrated in identifiable pockets rather than diffuse. We shipped five targeted, paper-only changes and **rejected** one (lowering the shrinkage floor) because the replay showed it cuts PnL with no win-rate gain. This doc defines how to judge each in a week.

Backfill (bias corrections fresh, weekly Sunday run firing) and resolution (settling through current day) are both healthy — not under test.

---

## Baseline snapshot (as of 2026-06-09, pre-change regime)

Compare the week-later numbers against these.

| Metric | Value |
|---|---|
| Settled trades | 154 |
| Overall win rate | 63.0% |
| Overall ROI | +4.5% |
| Overall P&L | +$96 |
| Calibration gap (stated − actual) | **+23pt** (86.1% → 63.0%) |
| "97% confident" bucket actual win | 57.8% |
| `cal_shrinkage_temperature` | 0.75 (pinned at floor) |

By NO entry-price band: 0.35–0.45 → 1.41 win/loss, +49% ROI · 0.55–0.65 → 0.70, +17% (the breadwinner, +$124) · 0.65+ → 0.45, −6% (mostly pre-cap).
By |edge|: 0.25–0.40 → 65% win, **+12% ROI** (sweet spot) · **0.40+ → 38% win, −17.5% ROI** (noise).
By direction: NO 64% actual · **YES 43% actual** (96% stated).
Re-admitted cities (S2): Tokyo 40%/n5, Ankara 0%/n2, SF 25%/n4, Seoul 25%/n4, Munich 33%/n3 → **−$154 combined**; Beijing/Taipei/Warsaw kept.

---

## The changes under test

All knobs have inert defaults in `config.py`; `paper_config.py` activates them. Logic in `signals/edge_calculator.py`.

| # | Change | Knob (paper value) | Rollback |
|---|---|---|---|
| **T1** | Low-price win-prob relaxation (NO, entry <0.45) — source favorable-payoff volume | `LOW_PRICE_WINPROB_THRESHOLD=0.45` | set to `0.0` |
| **T2** | Upper edge cap — skip adverse-selection noise | `MAX_EDGE_ABS=0.40` | set to `1.0` |
| **T3** | Neutralize 2× high-conviction Kelly boost | `HIGH_CONVICTION_KELLY_MULT=1.0` | set to `2.0` |
| **T4** | Pause YES bets | `ENABLE_YES_BETS=False` | set to `True` |
| **T5** | Re-exclude 5 failed re-admit cities | `CITY_EXCLUDE += {Tokyo,Ankara,SF,Seoul,Munich}` | remove them |
| ~~T6~~ | ~~Lower shrinkage floor~~ | **REJECTED** — replay cut PnL +$83→−$97, no win-rate gain | n/a |

---

## Hypotheses & pass/fail criteria

Evaluate only on trades **entered on/after 2026-06-09** (the new regime). Thin samples are expected after one week — treat <5 trades as "inconclusive, keep running," not pass.

### T1 — Low-price relaxation (the real forward test)
- **Hypothesis:** relaxing the NO win-prob floor below 0.45 sources favorable-payoff trades (win/loss >1) that hold at or above break-even (≈ entry price, ~0.35–0.45).
- **Metric:** count, win%, ROI of NO trades with `entry_price < 0.45` entered since 2026-06-09.
- **PASS:** ≥5 such trades, win rate ≥ ~50% (comfortably above the ~40% break-even) **and** positive P&L.
- **FAIL → rollback (`THRESHOLD=0.0`):** win rate below break-even or negative P&L over ≥5 trades.
- **Inconclusive:** if it generated ~0 sub-0.45 trades, the market isn't offering these mispricings — note it; consider whether to keep waiting or drop the test.

### T2 — Edge cap
- **Hypothesis:** skipping |edge|>0.40 removes noise without losing real edge.
- **Metric:** confirm **zero** new trades with `|edge| > 0.40`; overall ROI not degraded.
- **PASS:** gate fired (0 high-edge trades) and book ROI ≥ baseline.
- This is low-risk; mainly confirm it's working.

### T3 — Conviction boost removed
- **Metric:** stakes on edge-0.30–0.40 trades should sit at normal Kelly (no 2× outliers); max single stake ≤ the `MAX_TRADE_USDC`/Kelly cap, not double it.
- **PASS:** no boosted (2×) stakes; per-trade loss variance down.

### T4 — YES pause
- **Metric:** **zero** YES trades entered since 2026-06-09.
- **PASS:** 0 YES trades. (Re-enable later only with a fixed YES probability model.)

### T5 — City re-exclusion
- **Metric:** zero new trades in Tokyo/Ankara/SF/Seoul/Munich; kept cities (Beijing/Taipei/**Warsaw**) at ≥ break-even.
- **PASS:** 0 trades in the excluded 5. **Watch Warsaw** (was 50%/n2): if <55% over ≥5, exclude it too.

### Headline — did calibration & the book improve?
- **Metric:** stated vs actual win rate on trades **resolved** since 2026-06-09; overall win%, ROI, P&L, and **trade volume**.
- **Watch volume:** T2/T4/T5 all *cut* volume; T1 adds some back. Confirm net volume didn't crater (if it did, the book is starving — revisit the low-price threshold or the city list).
- **Watch the shrink factor:** has the daily `--calibration` job moved `cal_shrinkage_temperature` off 0.75, or is it still pinned (still overconfident)?

---

## Evaluation (run this on 2026-06-16)

```bash
cd /home/ubuntu/polymarket-weather-bot && python3 - <<'EOF'
import sqlite3
c=sqlite3.connect('paper_trades.db'); c.row_factory=sqlite3.Row
SINCE='2026-06-09'
def q(sql,*a): return [dict(r) for r in c.execute(sql,a)]

print("== NEW-REGIME BOOK (entered >= %s) =="%SINCE)
for r in q("""SELECT COUNT(*) n, SUM(pnl>0) wins, ROUND(100.0*SUM(pnl>0)/COUNT(*),1) win_pct,
  ROUND(SUM(pnl),2) pnl, ROUND(100.0*SUM(pnl)/NULLIF(SUM(size_usdc),0),1) roi
  FROM trades WHERE date(entry_time)>=? AND pnl IS NOT NULL AND status NOT IN('open','pending')""",SINCE):
    print(" ",r)

print("\n== T1 low-price NO (entry<0.45) ==")
for r in q("""SELECT COUNT(*) n, ROUND(100.0*SUM(pnl>0)/COUNT(*),0) win_pct, ROUND(AVG(entry_price),3) avg_entry,
  ROUND(SUM(pnl),2) pnl FROM trades WHERE date(entry_time)>=? AND direction='NO' AND entry_price<0.45
  AND pnl IS NOT NULL AND status NOT IN('open','pending')""",SINCE): print(" ",r)

print("\n== T2 edge cap (should be 0) / T4 YES (should be 0) ==")
print("  |edge|>0.40 new:", q("SELECT COUNT(*) n FROM trades WHERE date(entry_time)>=? AND ABS(edge)>0.40",SINCE)[0]['n'])
print("  YES new:        ", q("SELECT COUNT(*) n FROM trades WHERE date(entry_time)>=? AND direction='YES'",SINCE)[0]['n'])

print("\n== T5 excluded cities (should be 0) + kept-city perf ==")
for r in q("""SELECT city, COUNT(*) n, ROUND(100.0*SUM(pnl>0)/COUNT(*),0) win_pct, ROUND(SUM(pnl),2) pnl
  FROM trades WHERE date(entry_time)>=? AND city IN
  ('Tokyo','Ankara','San Francisco','Seoul','Munich','Beijing','Taipei','Warsaw')
  GROUP BY city ORDER BY city""",SINCE): print(" ",r)

print("\n== CALIBRATION (resolved >= %s): stated vs actual =="%SINCE)
rows=q("""SELECT direction,model_prob,(pnl>0) won FROM trades WHERE date(resolved_at)>=?
  AND pnl IS NOT NULL AND model_prob IS NOT NULL""",SINCE)
if rows:
    pw=lambda r:r['model_prob'] if r['direction']=='YES' else 1-r['model_prob']
    n=len(rows); st=sum(pw(r) for r in rows)/n; ac=sum(r['won'] for r in rows)/n
    print(f"  N={n} stated={100*st:.0f}% actual={100*ac:.0f}% gap={100*(st-ac):+.0f} (baseline gap +23)")
else: print("  (none resolved yet)")

print("\n== shrink factor (was 0.75 pinned) ==")
print(" ", q("SELECT value,updated_at FROM kv_store WHERE key='cal_shrinkage_temperature'"))
EOF
```

---

## Next deeper test to queue (not yet shipped)

The through-line of the health check: **the model's confident disagreements with the market are mostly noise** — post-hoc shrinkage can't fix that, and the guards above only trim the symptoms. The root cause is that the forecast→bucket-probability distribution is **too sharp** on selected bets.

**Proposed S4 (after this week's results):** widen the bucket-probability distribution at the source.
1. **Offline first (no risk):** recompute bucket Brier score against resolved actuals at several inflations of `effective_std` / `BASE_FORECAST_STD_C` (e.g. ×1.0, ×1.15, ×1.30) to find where calibration is best. This *is* backtestable (unlike the gate changes) because it only rescales probabilities on known outcomes.
2. **Then forward-test** the winning inflation in paper (paper-only knob, inert in live), watching the 90–100% stated bucket's actual win rate climb toward parity.

This is the highest-leverage remaining accuracy lever; the shrinkage/gate work has hit diminishing returns.

---

## Rollback (all paper-only)

Each knob reverts independently to its inert value (see the table). Full revert: in `paper_config.py` set `LOW_PRICE_WINPROB_THRESHOLD=0.0`, `MAX_EDGE_ABS=1.0`, `HIGH_CONVICTION_KELLY_MULT=2.0`, `ENABLE_YES_BETS=True`, and remove the 5 re-excluded cities from `CITY_EXCLUDE`. Live is unaffected throughout.

## Files changed (this session)
- `config.py` — inert defaults: `LOW_PRICE_WINPROB_THRESHOLD/MARGIN/MIN_WIN_PROB_FLOOR`, `MAX_EDGE_ABS`, `ENABLE_YES_BETS`.
- `paper_config.py` — activated all guards + re-excluded 5 cities (with rationale comments).
- `signals/edge_calculator.py` — low-price win-prob relaxation (NO-only), YES pause, upper edge cap.
- Related memories: `calibration-shrinkage-inert`, `excluded-cities-are-bias-driven`, `payoff-asymmetry-levers-exhausted`.
