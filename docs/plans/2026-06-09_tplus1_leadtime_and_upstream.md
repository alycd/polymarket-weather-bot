# T+1 Lead-Time Leak — Floor vs. Std-Gate, Sizing, and the Upstream-Widening Result

**Date:** 2026-06-09 (session 2; **P1 SHIPPED to PAPER in session 3, same day** — see "SHIPPED" section at top).
**Scope:** Analysis + proposals. P1 (lead-conditioned T+1 std gate) is now **SHIPPED to paper**; P2 (stake trim) and P3 (edge floor) remain unshipped (P2 deferred, P3 rejected).
**Companion doc:** `2026-06-09_forward_tests.md` (the already-shipped S3 guards — MAX_EDGE_ABS=0.40, YES pause, 5-city re-exclusion, low-price relaxation — still under forward test, review ~2026-06-16).

---

## ✅ SHIPPED 2026-06-09 (session 3) — P1: lead-conditioned T+1 ensemble-std gate `T_PLUS_ONE_MIN_STD=1.0`

**Status: QUEUED → SHIPPED to PAPER (live inert).** This is its own forward-test line for the 2026-06-16 review.

### Decision
Shipped **the std≥1.0 T+1 gate ALONE** (P1). At true lead (target_date − today) ≥ 1, a NO bet is skipped if `ensemble_std < 1.0`. T+0 (same-day) is explicitly untouched. Knob is inert in live (0.0) and active in paper (1.0).

### What changed
- `config.py`: added inert default `T_PLUS_ONE_MIN_STD = 0.0` (0.0 ⇒ gate never fires ⇒ live unaffected).
- `paper_config.py`: `T_PLUS_ONE_MIN_STD = 1.0` (active).
- `signals/edge_calculator.py`: imported `T_PLUS_ONE_MIN_STD`; added a lead-conditioned gate right after the existing global `NO_MIN_ENSEMBLE_STD` block in the NO branch. **Uses the TRUE unclamped lead** `(target_date − today).days`, not the `lead_days` variable defined upstream (that one is `max(1, …)` for horizon scaling and would misread T+0 as T+1). Gate fires only when `true_lead ≥ 1`.

### Verification (run this session)
- `LIVE T_PLUS_ONE_MIN_STD = 0.0` (inert) / `PAPER T_PLUS_ONE_MIN_STD = 1.0` (active). Confirmed via `config_active`.
- `python main.py --scan --dry-run` (PAPER): EXIT 0, pipeline clean (only a transient NOAA 429 auto-retry, unrelated).
- Direct `compute_edge` unit checks at std≈0.89 (between the global 0.80 floor and the 1.0 T+1 floor, to isolate the new gate):
  - **T+0** → new gate does NOT fire (trade advances past it; later skipped by an unrelated edge threshold). T+0 untouched. ✅
  - **T+1** → new gate fires: "Skipping T+1 NO bet (lead=1): ensemble_std=0.89 < T_PLUS_ONE_MIN_STD=1.00". ✅
  - **T+2** → gate fires (lead≥1 regime). ✅

### Replay evidence (settled guarded book, 156 settled as of this session)
Lead defined as `target_date − date(entry_time)`, matching runtime semantics.

| Book | N | win% | PnL | ROI | $/trade |
|---|---|---|---|---|---|
| Guarded baseline (no std gate) | 125 | 67.2% | +$184.35 | 10.8% | $1.47 |
| **+ T+1 std≥1.0 (SHIPPED)** | **101** | **70.3%** | **+$230.51** | **16.8%** | **$2.28** |
| + T+1 std≥1.2 (for reference) | 84 | 72.6% | +$236.02 | 20.9% | $2.81 |

T+1 cohort win-rate ramp is **monotonic**: std≥0.8 → 62.9% (N=70), std≥1.0 → 67.4% (N=46), std≥1.2 → 72.4% (N=29). (Contrast the rejected edge floor, whose win/edge curve is non-monotonic.)

### What was rejected / deferred (for the 06-16 reviewer)
- **P3 — T+1 |edge|≥0.25 floor: REJECTED.** Sample-fitting and non-monotonic (T+1 win% vs |edge| = 100→67→50→63→70%). On the raw book, kept trades (−7.0% ROI) are no better than dropped (−6.4%) — pure volume removal. Worse, stacking it on the existing `MAX_EDGE_ABS=0.40` squeezes T+1 into [0.25,0.40] and discards 44 trades that were 61% winners. Dominated by P1 on both volume (101 vs 81) and PnL ($230 vs $202).
- **P2 — T+1 stake trim ×0.75: DEFERRED, not shipped.** It LOWERS total PnL ($230→$221, though ROI rises to 18.2% on less deployed capital) and would muddy the forward attribution of the gate. The user explicitly chose the gate alone. Revisit after 06-16 only if T+1 is still weak.

### User guidance captured
- Do **NOT** over-restrict / starve the book. P1 keeps 101 trades (vs 81 for the edge floor) — chosen partly for this. Watch weekly T+1 volume stays > 0.
- The user is wary of **stacking gates** on top of the 5 guards already under forward test from commit b9cebb5 (MAX_EDGE_ABS, YES pause, 5-city exclusion, low-price relaxation, conviction-Kelly neutralization).

### Reviewer caveat (IMPORTANT for 06-16 attribution)
This gate acts on a **different axis** — forecast spread (`ensemble_std`) — than the b9cebb5 guards (edge cap / YES pause / entry price / city). So it is largely orthogonal to them. **But it was still stacked mid-window** (shipped 2026-06-09, same day the b9cebb5 window is being measured). Therefore the 06-16 read must **attribute carefully**: treat this gate as its OWN forward-test line with its own baseline snapshot (below), and do not credit/blame the b9cebb5 guards for the T+1 std-gate's effect or vice-versa.

### Baseline snapshot for the 06-16 forward read (frozen 2026-06-09)
- Pre-gate guarded baseline: **N=125, 67.2% win, +$184.35, 10.8% ROI** (whole guarded book) / T+1 sub-cohort: **N=70, 62.9% win, −$10.37, −1.1% ROI**.
- Activation date: **2026-06-09**. Only trades with `date(entry_time) ≥ 2026-06-09` count toward the forward read.

### Pass/fail criteria (judge ~2026-06-16)
- **PASS** if, over forward trades entered ≥ 2026-06-09: (a) T+1 NO trades that survived the gate (std≥1.0) hold ≥ break-even win rate over **≥5 new T+1 trades**, AND (b) book ROI ≥ the 10.8% baseline, AND (c) T+1 volume not crushed (>0 T+1 trades/week), AND (d) zero std<1.0 T+1 trades slipped through.
- **INCONCLUSIVE** if < 5–10 new T+1 trades in the window (thin sample — extend, don't judge).
- **FAIL** → rollback.

### Rollback (one line)
Set `T_PLUS_ONE_MIN_STD = 0.0` in `paper_config.py`.

### Evaluation block (run ~2026-06-16)
```bash
cd /home/ubuntu/polymarket-weather-bot && python3 - <<'PYEOF'
import sqlite3
from datetime import date
c=sqlite3.connect('paper_trades.db'); c.row_factory=sqlite3.Row
ACTIVATION='2026-06-09'   # gate shipped this date
rows=[dict(r) for r in c.execute("""SELECT city,direction,edge,ensemble_std,size_usdc,pnl,entry_time,target_date
  FROM trades WHERE date(entry_time)>=? AND pnl IS NOT NULL AND status NOT IN('open','pending')""",(ACTIVATION,))]
def lead(r):
    ey,em,ed=map(int,r['entry_time'][:10].split('-')); ty,tm,td=map(int,r['target_date'].split('-'))
    return (date(ty,tm,td)-date(ey,em,ed)).days
def summ(lbl,rs):
    if not rs: print(f"{lbl}: N=0"); return
    n=len(rs); w=sum(r['pnl']>0 for r in rs); p=sum(r['pnl'] for r in rs); s=sum(r['size_usdc'] for r in rs) or 1
    print(f"{lbl}: N={n} win%={100*w/n:.1f} PnL=${p:.2f} ROI={100*p/s:.1f}%")
summ("ALL since activation", rows)
t1=[r for r in rows if lead(r)>=1]
summ("T+1 since activation", t1)
summ("  T+1 std>=1.0 (kept by gate)", [r for r in t1 if (r['ensemble_std'] or 0)>=1.0])
print("  T+1 NO std<1.0 that SLIPPED THROUGH (should be 0):",
      sum(1 for r in t1 if r['direction']=='NO' and (r['ensemble_std'] or 0)<1.0))
summ("T+0 since activation (should be unaffected)", [r for r in rows if lead(r)<=0])
print("\nPASS if: >=5 new T+1 trades, T+1 kept-cohort >= break-even win%, book ROI >= 10.8%, 0 slip-throughs. <5-10 T+1 = inconclusive.")
PYEOF
```

---

## TL;DR

The whole settled book is two regimes split by lead time: **T+0 carries all the profit** (nowcaster live-ASOS blend = ground truth), **T+1 is the overconfident-noise regime**. The user asked to evaluate a **T+1 minimum-edge floor of 0.25**.

**Verdict on the proposal: it "works" only by removing volume, and it is the WORST of the candidates I tested.** On the full raw book the floor does NOT separate T+1 winners from losers (kept −7.0% ROI ≈ dropped −6.4% ROI). Its apparent gain on the guarded book is **sample-fitting** — it hinges on the [0.18,0.25) edge band happening to hold four −$15 max-loss trades, and the T+1 win-rate-vs-edge curve is **non-monotonic** (100%→67%→50%→63%→70%), i.e. there is no real "higher edge = better T+1 trade" signal.

**A far better, mechanistically-grounded T+1 gate exists: `ensemble_std ≥ 1.0` (NO bets, T+1 only).** It keeps 20 MORE trades than the edge floor, makes ~$28 MORE PnL, has a clean monotonic win-rate/ROI ramp, reuses the existing `NO_MIN_ENSEMBLE_STD` mechanism, and addresses the documented mechanism (tight model agreement at T+1 → specific bucket likely hit → NO loses, with no nowcaster to override).

**Upstream widening (`BASE_FORECAST_STD_C` / `effective_std`) is REJECTED** — the offline Brier sweep over 783 real NOAA forecast-days shows Brier is *minimized at no inflation* and the model is if anything *under*-confident on its central forecast. The "86% stated / 62% actual" overconfidence is a pure **bet-selection artifact**, not a distribution-sharpness problem; widening can't touch it and would hurt the profitable T+0 cohort.

---

## Baseline (this session, 155 settled paper trades)

P&L totals differ slightly from the 06-09 forward-test doc (+$81 raw / +$184 guarded vs +$96 there) — a few trades have resolved since. The lead split is identical.

| Cohort | N | win% | PnL | ROI | $/trade |
|---|---|---|---|---|---|
| ALL (raw, 155) | 155 | 62.6% | +$81.35 | +3.8% | +$0.52 |
| **T+0 (same-day)** | 66 | 66.7% | **+$163.50** | **+17.7%** | +$2.48 |
| **T+1 (day-before)** | 89 | 59.6% | **−$82.15** | **−6.7%** | −$0.92 |
| Shipped-guards book (≤0.40 edge, NO-only, 5 cities excl.) | 125 | 67.2% | +$184.35 | +10.8% | +$1.47 |
| — of which T+1 | 70 | 62.9% | −$10.37 | −1.1% | −$0.15 |

Mechanism: T+0 gets the nowcaster live-ASOS blend (real ground truth); T+1 is pure forecast-vs-market in the regime where the model's confident disagreements are mostly noise.

---

## TASK A — the user's question: T+1 min-edge floor 0.25, WIN/LOSS counts

### View 1 — full raw book (155), ONLY the T+1 |edge|≥0.25 floor (no other guards)

| | N | **WINS** | **LOSSES** | win% | PnL | ROI | $/trade |
|---|---|---|---|---|---|---|---|
| Baseline (all 155) | 155 | 97 | 58 | 62.6% | +$81.35 | +3.8% | +$0.52 |
| **With T+1 floor 0.25** | **105** | **67** | **38** | 63.8% | +$123.20 | +8.2% | +$1.17 |
| → DROPPED (T+1, \|edge\|<0.25) | 50 | 30 | 20 | 60.0% | −$41.85 | −6.4% | −$0.84 |

### View 2 — same rule, split by lead

| | N | WINS | LOSSES | win% | PnL | ROI |
|---|---|---|---|---|---|---|
| T+0 (unaffected) | 66 | 44 | 22 | 66.7% | +$163.50 | +17.7% |
| **T+1 KEPT (\|edge\|≥0.25)** | 39 | 23 | 16 | 59.0% | **−$40.30** | **−7.0%** |
| T+1 baseline (all) | 89 | 53 | 36 | 59.6% | −$82.15 | −6.7% |
| T+1 DROPPED (\|edge\|<0.25) | 50 | 30 | 20 | 60.0% | −$41.85 | −6.4% |

**Key:** on the raw book the kept T+1 trades (−7.0% ROI) are NO better than the dropped ones (−6.4%). The floor does not select good trades — it just halves the book. The "+$41.85" is purely removed-volume, not captured edge.

### View 3 — realistic current-regime book (already-shipped guards + the floor)

| Book | N | WINS | LOSSES | win% | PnL | ROI | $/trade |
|---|---|---|---|---|---|---|---|
| Shipped guards (no floor) | 125 | 84 | 41 | 67.2% | +$184.35 | +10.8% | +$1.47 |
| **+ T+1 floor 0.25** | **81** | **57** | **24** | 70.4% | +$202.06 | +17.8% | +$2.49 |

So under the realistic stack, the floor would have the book trade **81 trades (57 W / 24 L)**. It does lift ROI — but only by cutting 44 trades, and (Task B) less efficiently than the alternatives.

---

## TASK B — stacking with MAX_EDGE_ABS=0.40, and the better floor

With MAX_EDGE_ABS=0.40 already active, T+1 trades only survive in **|edge| ∈ [0.25, 0.40]** once a 0.25 floor is added. Of the 70 T+1 trades in the guarded book, only **26** fall in that band — the floor squeezes out 44 (63%). The book is not *starved* (81 total is still viable), but the floor is **inefficient**: the dropped 44 are 61% winners, and the per-edge-band T+1 PnL is non-monotonic noise (the −$15 cluster in [0.18,0.25) drives the whole "gain").

**Candidate T+1 gates compared (effect on the whole guarded book; T+0 always untouched):**

| Gate on T+1 cohort | Book N | win% | PnL | ROI | $/trade | Comment |
|---|---|---|---|---|---|---|
| none (baseline) | 125 | 67.2% | $184.35 | 10.8% | $1.47 | — |
| \|edge\| ≥ 0.20 | 91 | 68.1% | $184.79 | 14.6% | $2.03 | no PnL gain |
| **\|edge\| ≥ 0.25 (the proposal)** | 81 | 70.4% | $202.06 | 17.8% | $2.49 | most-gating, lower PnL |
| \|edge\| ≥ 0.30 | 67 | 71.6% | $211.85 | 22.7% | $3.16 | starts to starve |
| **std ≥ 1.0 (RECOMMENDED)** | **101** | 70.3% | **$230.51** | 16.8% | $2.28 | +20 trades & +$28 vs proposal |
| std ≥ 1.2 | ~84 | 72.4%* | higher* | ~19%* | — | *T+1-cohort figures; tighter |
| std ≥ 1.0 & entry ≤ 0.70 | 92 | 69.6% | $224.44 | 18.0% | $2.44 | best ROI of the gate-only set |

\* std≥1.2 figures are for the T+1 cohort in isolation (N=29, 72.4% win, +11.1% ROI).

**Recommendation: do NOT use the |edge| floor. Use a lead-conditioned ensemble-std gate at 1.0** (`std ≥ 1.0` for T+1 NO bets), optionally paired with an entry-price tightening for T+1. Rationale:
- **More volume, more money:** 101 trades / +$230.51 vs 81 / +$202.06. Directly serves the "don't over-gate" constraint.
- **Monotonic & mechanistic:** T+1 win% climbs cleanly 62.9% (all) → 67.4% (≥1.0) → 72.4% (≥1.2); ROI −1.1% → +5.8% → +11.1%. The edge curve does not.
- **Lead-conditioned is essential — do NOT just raise the global gate.** At T+0, low-std trades are *profitable* (std∈[0.0,1.0): N=14, 64% win, +10.1% ROI) because the nowcaster carries them. A global raise to 1.0 would needlessly cut 14 profitable same-day trades (+$17.66). So the knob must apply to T+1 only.
- **Reuses an existing, understood mechanism** (`NO_MIN_ENSEMBLE_STD`, currently 0.8) — low implementation risk.

If a single number is wanted: **std ≥ 1.0 for T+1**. If maximizing risk-adjusted return over raw volume, **std ≥ 1.0 & entry ≤ 0.70 for T+1** (18.0% ROI, 92 trades).

---

## TASK D — further optimizations

### D-a — Upstream widening of the forecast→bucket distribution: **REJECTED (negative result).**

The prior session flagged widening `effective_std` / `BASE_FORECAST_STD_C` as the "highest-leverage remaining lever," to be validated via an offline Brier sweep against resolved NOAA actuals. Built that harness — and it does NOT support widening.

- Data: joined `model_forecasts` (lead 0 & 1) to `historical_obs` actuals → **783 forecast-days** with real outcomes (452 lead-0, 331 lead-1), vs only 19 actuals in the trades table. Replicated the real ensemble exactly (weighted mean, Kish-corrected spread, `dynamic_base_std = max(1.1, BASE−(2−lead)·0.25)`, Student-t df=4) and swept an inflation factor k on `effective_std`.
- **Full-distribution Brier is minimized at k=1.00** and rises monotonically with inflation (lead-0: 0.04680 → 0.05150 at k=2.0; lead-1 similar). Widening makes calibration *worse*.
- **Modal-bucket calibration shows UNDER-confidence, not over-:** stated P(temp in modal bucket) = 19.3% (lead-0) / 16.9% (lead-1), actual hit rate = 33.4% / 27.8%. The temperature lands in the model's central bucket *more* often than stated. Inflating std widens this gap.
- **Conclusion:** the model is well-calibrated (mildly under-confident) on the *population* of forecasts. The documented "86% stated / 62% actual win" is a **bet-selection artifact** — the bot bets NO on buckets it assigns low probability, and on exactly the buckets where it most disagrees with the market, the market is right. A global distribution change cannot fix a selection problem, and would degrade the profitable T+0 book. (The trades table also lacks `ensemble_mean`, so the selected-bucket inflation can't even be reconstructed offline — the forecast-day harness is the valid test, and it says no.)
- This refines `calibration-shrinkage-inert` and closes the S4 idea proposed in the companion doc. **Do not widen.**

### D-b — Sizing reallocation toward T+0: limited headroom, but a T+1 stake trim is a mild win.

P&L is exactly linear in stake, so this is cleanly replayable (cap each stake at the $15 max-loss rule).

- **T+0 boost is mostly inert:** 44/55 T+0 trades already sit at the $15 cap (avg size $13.81). A T+0 multiplier barely moves PnL (×2.0 → +$5 only).
- **T+1 stake ×0.5 (keep all volume, just de-risk):** book PnL $184.35 → $189.53, **ROI 10.8% → 15.4%**, frees ~$475 of capital. This is a genuine "reallocate, don't cut" lever — all 125 trades retained, lower variance on the losing cohort.
- Best risk-adjusted single package: **std≥1.0 T+1 gate + T+1 stake ×0.75** → N=101, 70.3% win, +$221.56, **ROI 18.2%** (deploys only $1,220).

### D-c — Volume-sourcing: nothing new validated this session.

The structurally-correct way to add favorable-payoff (<0.50) volume is the low-price win-prob relaxation already shipped (T1, under forward test). The T+0 cohort is the profit engine but is supply-constrained by how many same-day mispricings the market offers — not gateable into existence. No replayable volume-add found; revisit after the 06-16 forward results.

---

## QUEUED proposals (NOT shipped — await user approval)

> **UPDATE 2026-06-09 (session 3): P1 SHIPPED to paper — see the "SHIPPED" section at the top of this doc.** The knob was named `T_PLUS_ONE_MIN_STD` as actually implemented (the `T_PLUS_ONE_MIN_ENSEMBLE_STD` name below was the draft proposal name). The implementation computes the TRUE unclamped lead `(target_date − today)` rather than reusing the `max(1,…)` `lead_days`. P2 deferred, P3 rejected.

### P1 (RECOMMENDED — now SHIPPED) — Lead-conditioned T+1 ensemble-std gate
- **Hypothesis:** at T+1 (no nowcaster ground truth), tight model agreement (low `ensemble_std`) means the specific bucket is likely hit → NO bets fail. Gating T+1 NO bets at std ≥ 1.0 removes the −13.9%-ROI low-std cohort while keeping more volume than any edge floor.
- **Implementation (inert-in-live pattern):**
  - `config.py`: add `T_PLUS_ONE_MIN_ENSEMBLE_STD = 0.0` (inert default → live inherits, no behavior change). Verify: `python -c "import sys; sys.argv.append('--live'); import config_active as c; print(c.T_PLUS_ONE_MIN_ENSEMBLE_STD)"` → `0.0`.
  - `paper_config.py`: `T_PLUS_ONE_MIN_ENSEMBLE_STD = 1.0`.
  - `signals/edge_calculator.py`: in the existing NO ensemble-std gate block (~line 405, where `NO_MIN_ENSEMBLE_STD` is checked), add: if `lead_days >= 1` and `ensemble.std_c < T_PLUS_ONE_MIN_ENSEMBLE_STD`, skip. (Lead-conditioned — T+0 untouched.)
- **Replay (settled book, guarded):** N 125→101, win% 67.2→70.3, PnL $184.35→$230.51, ROI 10.8%→16.8%.
- **Pass/fail (forward, trades entered ≥ activation date):** PASS if T+1 NO trades with std≥1.0 hold ≥ break-even win rate over ≥5 trades AND book ROI ≥ baseline AND T+1 volume not crushed (>0 T+1 trades/week). FAIL → rollback.
- **Rollback:** set `T_PLUS_ONE_MIN_ENSEMBLE_STD = 0.0` in paper_config.py.
- **Stacking note:** independent of MAX_EDGE_ABS (acts on std, not edge), so no narrow-band squeeze. Stacks additively with the shipped guards; verify combined T+1 weekly volume stays >0.

### P2 (OPTIONAL, pairs with P1) — T+1 stake reduction
- **Hypothesis:** halving/0.75×-ing T+1 stakes de-risks the weaker cohort without cutting any trades; lifts ROI, frees capital for T+0.
- **Implementation:** `config.py` add `T_PLUS_ONE_SIZE_MULT = 1.0` (inert); `paper_config.py` = 0.75; apply in the Kelly-sizing block of `edge_calculator.py` when `lead_days >= 1` (after the $15 cap).
- **Replay:** ×0.75 with P1 → ROI 18.2%, PnL $221.56, all-volume-retained variant ×0.5 alone → ROI 15.4%.
- **Rollback:** `T_PLUS_ONE_SIZE_MULT = 1.0`.

### P3 — The |edge|≥0.25 T+1 floor (the original proposal): **NOT recommended.** Dominated by P1 on volume and PnL; gain is sample-fitting on a non-monotonic edge curve. Recorded for completeness; do not ship.

---

## Evaluation block (run when P1/P2 are shipped + a week elapses)

```bash
cd /home/ubuntu/polymarket-weather-bot && python3 - <<'EOF'
import sqlite3
from datetime import date
c=sqlite3.connect('paper_trades.db'); c.row_factory=sqlite3.Row
SINCE='REPLACE_WITH_ACTIVATION_DATE'
rows=[dict(r) for r in c.execute("""SELECT city,direction,edge,ensemble_std,size_usdc,pnl,entry_time,target_date
  FROM trades WHERE date(entry_time)>=? AND pnl IS NOT NULL AND status NOT IN('open','pending')""",(SINCE,))]
def lead(r):
    ey,em,ed=map(int,r['entry_time'][:10].split('-')); ty,tm,td=map(int,r['target_date'].split('-'))
    return (date(ty,tm,td)-date(ey,em,ed)).days
def summ(lbl,rs):
    if not rs: print(f"{lbl}: N=0"); return
    n=len(rs); w=sum(r['pnl']>0 for r in rs); p=sum(r['pnl'] for r in rs); s=sum(r['size_usdc'] for r in rs)
    print(f"{lbl}: N={n} win%={100*w/n:.1f} PnL=${p:.2f} ROI={100*p/s:.1f}%")
t1=[r for r in rows if lead(r)>=1]
summ("T+1 since activation", t1)
summ("  T+1 std>=1.0 (kept)", [r for r in t1 if r['ensemble_std'] and r['ensemble_std']>=1.0])
print("  T+1 std<1.0 trades that SLIPPED THROUGH (should be ~0):",
      sum(1 for r in t1 if r['ensemble_std'] and r['ensemble_std']<1.0))
summ("T+0 since activation (should be unaffected)", [r for r in rows if lead(r)<=0])
EOF
```

---

## Files (analysis only — no code changed this session)
- Analysis here; proposals queued. `config.py` / `paper_config.py` / `signals/edge_calculator.py` **untouched**.
- Memories: refined `calibration-shrinkage-inert` (upstream-widening rejected); new `tplus1-leadtime-regime-split` (lead split + std-gate beats edge-floor).
