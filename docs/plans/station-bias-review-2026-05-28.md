# Station Bias Review — 2026-05-28

Revisit in ~2 weeks (around 2026-06-11) once more trades have resolved.

## Context

Analyzed 67 resolved paper trades across 30 cities (2026-05-23 – 2026-05-28).
Portfolio: 43 wins / 67 trades · 63% win rate · net +$147.50.
Almost all trades are NO direction (betting a specific temperature bucket does NOT verify).

---

## Per-City Results (sorted by PnL)

| City | N | Win% | Avg Model P(YES) | Avg Market P(YES) | Total PnL |
|------|---|------|-----------------|-------------------|-----------|
| Los Angeles | 5 | 100% | 0.077 | 0.470 | +71.51 |
| Lucknow | 3 | 100% | 0.238 | 0.525 | +42.22 |
| Paris | 3 | 67% | 0.120 | 0.492 | +22.04 |
| Tel Aviv | 2 | 100% | 0.247 | 0.485 | +21.79 |
| Austin | 3 | 100% | 0.060 | 0.298 | +19.08 |
| Dallas | 2 | 100% | 0.130 | 0.350 | +15.93 |
| Seattle | 2 | 100% | 0.122 | 0.338 | +15.00 |
| Houston | 2 | 100% | 0.078 | 0.345 | +14.28 |
| Sao Paulo | 2 | 100% | 0.118 | 0.335 | +12.34 |
| Mexico City | 1 | 100% | 1.000 | 0.650 | +8.05 |
| Milan | 1 | 100% | 0.263 | 0.465 | +7.99 |
| Chongqing | 1 | 100% | 0.173 | 0.340 | +7.70 |
| Shenzhen | 2 | 100% | 0.266 | 0.353 | +7.30 |
| New York City | 1 | 100% | 0.102 | 0.335 | +6.23 |
| Atlanta | 1 | 100% | 0.115 | 0.295 | +5.40 |
| Madrid | 1 | 100% | 0.213 | 0.350 | +5.08 |
| Seoul | 1 | 100% | 1.000 | 0.840 | +2.86 |
| Munich | 2 | 50% | 0.260 | 0.495 | -0.52 |
| Toronto | 4 | 75% | 0.149 | 0.386 | -0.54 |
| Taipei | 3 | 67% | 0.119 | 0.308 | -3.63 |
| Buenos Aires | 1 | 0% | 0.278 | 0.390 | -6.72 |
| Beijing | 1 | 0% | 0.197 | 0.305 | -8.24 |
| Chengdu | 2 | 50% | 0.184 | 0.388 | -10.07 |
| Hong Kong | 3 | 33% | 0.434 | 0.515 | -13.98 |
| Denver | 1 | 0% | 0.000 | 0.266 | -15.00 |
| Warsaw | 1 | 0% | 0.137 | 0.275 | -15.00 |
| Wuhan | 1 | 0% | 0.000 | 0.280 | -15.00 |
| San Francisco | 3 | 33% | 0.100 | 0.323 | -23.85 |
| Tokyo | 3 | 33% | 0.088 | 0.498 | -23.42 |
| Ankara | 2 | 0% | 0.210 | 0.575 | -30.00 |

---

## Model Bias by Losing City

**Ankara (0/2, -$30):** Model gave P(YES)=0.17–0.25, market gave 0.45–0.70, YES verified both times. NWP ensemble cold-biased for Ankara late May. Market was right both times. → Already added to `CITY_EXCLUDE`.

**Tokyo (1/3, -$23):** Key loss: `0ef39c4d` (May 25, 17.5–18.5°C NO) had model=0.005, market=0.78 — we bet against 78% market consensus and lost. Second loss at 25.5–26.5°C also showed model overconfidence in NO. Japanese coastal temperature distribution has fatter tails than ensemble captures.

**San Francisco (1/3, -$24):** Model gives 6–10% P(YES) for 62–65°F NO bets; market ~32%; temp verified 2/3. Marine layer intrusion in late May verifies more often than GFS/ECMWF predicts. → Already in `CITY_EXCLUDE`.

**Hong Kong (1/3, -$14):** YES trade `5a55f73a` had model=1.0 (certainty), market=0.225, and lost — unbounded bucket returning P=1.0 due to floating-point underflow. Also lost a NO trade where market was at 0.76. → Already in `CITY_EXCLUDE`.

---

## Three Suggested Fixes — and Their Actual Status

### 1. Market-conviction filter: skip NO if model_prob < 0.05 and market_prob > 0.50

**Already implemented.** `NO_ENTRY_MIN_PRICE = 0.35` in config.py means we skip any NO bet where entry is below 35¢ (i.e., market > 65% on YES). The comment says "3/3 losses below this threshold live" — those losses (including the Tokyo one) already drove this tuning. The Tokyo `0ef39c4d` trade (entry=0.22) would be blocked today.

**Action: none.** Don't add a second filter on top of one already doing the job.

### 2. Fix HK unbounded bucket — cap model_prob to [0.01, 0.99]

**HK already excluded.** The immediate problem is handled. However, a real code inconsistency exists:
- `model_prob_for_bucket()` (single-day) caps correctly at `[0.005, 0.995]`
- `weekly_market_prob()` (multi-day, lower-bound buckets) returns `min(1.0, ...)` — can return exactly 1.0 when the ensemble mean is well above the lower bound and `p_all_below` underflows

Fix if ever re-enabling HK or adding new lower-bound markets: change the three `return float(max(0.0, min(1.0, ...)))` lines in `weekly_market_prob()` to `min(0.995, ...)`. One-line change per return, zero meaningful effect on currently active cities.

**Action when ready to revisit HK:** make the 3-line fix in `signals/edge_calculator.py` first, then test before removing HK from `CITY_EXCLUDE`.

### 3. SF positive bias correction for 62–65°F buckets (May–June)

**SF already excluded.** 3 resolved trades is too small a sample to estimate bias magnitude reliably. Need to know: how many degrees cold? Is it the full 62–65°F range or just specific buckets? Is it May-specific?

**Action when revisiting:** Wait until ~15 resolved SF trades are available. Then check the ASOS actuals vs model forecasts for SFO in `historical_obs` to estimate the systematic cold error. Add to `CITY_FORECAST_BIAS_C` in config.py (currently only HK is in there). Only then remove SF from `CITY_EXCLUDE`.

---

## Best-Performing Cities — Worth Leaning Into

**Los Angeles:** 5/5, avg edge 0.373, +$71.51. Market systematically overprices YES on LA temperature buckets. The model is well-calibrated here. Consider increasing Kelly fraction at the city level if that becomes configurable.

**Lucknow:** 3/3, avg edge 0.287, +$42.22. Consistent. Edge is real but market pricing is thinner — watch for edge compression as market gets smarter.

**Austin / Houston / Dallas:** All 100%, edges 0.22–0.27. US heat market in late May appears reliably mispriced on the YES side.

---

## What to Check at Revisit (~2026-06-11)

- [ ] Do SF and Tokyo losses hold up with more data, or were these a bad week?
- [ ] Has the Ankara cold bias persisted (validate against ASOS)? If ASOS shows Ankara was genuinely warm, the NWP bias is structural.
- [ ] Is the LA / Austin / Dallas edge compressing as markets mature?
- [ ] Are Munich and Toronto trending positive or negative with more trades?
- [ ] If SF has 10+ resolved trades by then: estimate bias and consider reopening with `CITY_FORECAST_BIAS_C` correction.
- [ ] Run `python main.py --export-calibration` and check the Brier skill score trend.
