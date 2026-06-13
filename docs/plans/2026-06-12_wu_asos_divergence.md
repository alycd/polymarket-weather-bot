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

### RESOLVED 2026-06-13: the page uses the observation max; my "fix" overshoot

The 06-13 test settled it: the Denver 06-12 **history-page High reads 87.8°F**,
not 90. Yesterday's "90" was WU's **live current-conditions widget**
(`temperatureMaxSince7Am`) — a separate, more aggressive number that does NOT
drive the history-page High Polymarket resolves on. Toronto 06-13 is the clean
confirmation: page High 29°C, but `temperatureMaxSince7Am` = 86°F = 30.00°C →
our 06-12 dashboard helper showed 30 and flipped a real HIT into a reassuring
MISS on an open NO position.

Corrected: `get_today_max_native` now delegates to `get_historical_high_native`
(the observation-derived fetch the resolution path already uses), so the
dashboard "Official WU max" always equals what the bot resolves on. **No
resolution-path change was ever needed — `get_historical_high_native` was
correct throughout.** The audit's "3/20 divergence" rows were measurement noise
from the brief window I trusted the continuous field, not real WU-vs-ASOS gaps.

Net residual finding: WU's history-page High = max of the hourly observation
table (the °F integer print). ASOS/IEM can still occasionally exceed it via
special obs, but that's rarer than the 3/20 figure suggested. The
nowcaster-vs-settlement boundary risk below still stands as a watch item.

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
