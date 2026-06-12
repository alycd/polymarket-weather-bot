# WU vs ASOS Divergence — Settlement Risk Note

**Date:** 2026-06-12
**Status:** FINDING — partially CORRECTED same day (see Update below). Candidate
analysis item if boundary-trade losses cluster.

## UPDATE (2026-06-12 evening): much of the "divergence" was our read artifact

User caught the dashboard showing "Official WU max 87°" while the live WU page
for KDEN showed High **90°**. Root cause: **WU's page High is the CONTINUOUS
sensor max** (v3 `temperatureMaxSince7Am` = 90), while our backend read maxed
the **hourly observation table** (87) — the 90° spike happened between hourly
prints and never appears in that table. Fixed intraday via
`get_today_max_native` (max of the continuous field and the hourly max).

This reframes the audit rows below: WU likely did NOT diverge from ASOS as much
as our hourly-table reads implied — e.g. Denver 05-28 "WU final print 75" was
the hourly-table max; the page High was plausibly 76 (continuous), matching
both ASOS (76.0) and Polymarket's settlement. **The real divergence is
hourly-table vs continuous-max, and our resolution fetch
(`get_historical_high_native`) reads the hourly table — it may understate
completed-day highs.** Empirical test queued for 2026-06-13: check the KDEN
page for 06-12 after the day completes — if High persists at 90 while the
hourly table maxes ≤88, fix the resolution fetch to use the page-summary value
(native unit). Tracked in FOLLOWUPS.md. Mitigation meanwhile: resolution step 1
is Polymarket's own `winner` field; the weather fallback rarely fires.

## Finding

Weather Underground's daily high — Polymarket's resolution source — does **not**
always converge to the ASOS/METAR daily max, even by end of day. In the
2026-06-12 resolution audit (see `analysis/wu_audit.py`,
`docs/plans/2026-06-10_live_execution_integrity.md` lineage), 3 of 20
PM-settled trades ended with WU's final print ≥1°C away from ASOS,
unreconciled:

| Trade | ASOS final | WU final print |
|---|---|---|
| Chicago 2026-05-28 | 22.78°C (~73°F) | 71°F (WU lower) |
| Toronto 2026-05-25 | 22.0°C | 23°C (WU higher) |
| Denver 2026-05-28 | 24.44°C (76.0°F) | 75°F (revised post-hoc; PM settled per the pre-revision read) |

## Mechanism

- **WU's daily high is the max of the hourly observation list its page shows**
  (routine hourly METARs via api.weather.com).
- **ASOS/IEM daily max** incorporates finer-grained and special observations
  (SPECIs, sub-hourly data), so it catches temperature spikes *between* hourly
  prints that WU never displays. The spike physically happened at the sensor;
  it just doesn't make WU's scoreboard.
- WU also **revises prints after the fact** (Denver above), and Polymarket
  settles on what the page said at resolution time — so even WU-today is not a
  perfect record of WU-at-settlement. Polymarket's own `winner` field remains
  the highest truth (audit: 20/20 of our PM-settled outcomes matched it).

## Implications

1. **Intraday monitoring** (dashboard outlook): "ASOS above WU" is ambiguous —
   usually ingest lag that closes within the hour, sometimes a spike that never
   prints. The outlook wording reflects this; the day-max verdict deliberately
   uses the higher reading (risk view), while settlement expectation should be
   anchored on WU's print.

2. **Nowcaster vs settlement (the open risk):** the T+0 nowcaster blends
   METAR/ASOS live obs as ground truth, but settlement happens on WU's hourly
   prints. On a boundary trade — e.g. NO on 90–91°F where ASOS spikes to 91.4°
   between hourly obs — the model can believe the bucket was escaped while WU
   prints 91 and the market settles it as hit. The boundary-proximity size
   penalty (config: halve size within 40% of bucket width) already limits
   exposure to these setups, but the *probability* model itself doesn't know
   about the print gap.

## Trigger for future work

If calibration analysis ever shows a cluster of boundary trades that "should
have won per ASOS but lost per settlement" (or vice versa), this gap is the
first suspect. The analysis would be: for resolved boundary trades (actual
within ~0.5°C of a bucket edge), compare the ASOS max vs the WU print vs the
settled outcome, and if the print gap is systematically costing money, consider
feeding the nowcaster WU's hourly prints (the api.weather.com backend used by
`data/wunderground.get_historical_high_native` serves them) instead of — or
shrunk toward — the raw METAR feed for same-day bucket probability.
