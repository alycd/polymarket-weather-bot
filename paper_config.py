"""
Paper-trading overrides.
Looser sizing to explore signal quality, and opens excluded cities for data gathering.
"""
from config import *  # noqa: F401, F403

# ── Trading thresholds ────────────────────────────────────────────────────────
MIN_EDGE              = 0.12
MIN_WIN_PROB          = 0.70
MIN_WIN_PROB_YES      = 0.60
# Favorable-payoff forward test (2026-06-09, PAPER ONLY — review ~2026-06-23).
# At low entry prices the win/loss ratio is >1, but the flat 0.70/0.60 win-prob
# floor forces edge ≥ 0.25+ there and starves favorable-payoff volume (the
# 0.35–0.45 NO band ran +49% ROI but was gated by win-prob, not edge). Relax the
# floor below 0.45 toward break-even (= entry) + 0.12, never below 0.50. MIN_EDGE
# (0.12) still binds. Can't be backtested (replay can't see rejected trades), so
# this is a forward test: watch whether the new sub-0.45 volume holds ≥ break-even.
# See [[payoff-asymmetry-levers-exhausted]]. Rollback: set THRESHOLD back to 0.0.
LOW_PRICE_WINPROB_THRESHOLD = 0.45
LOW_PRICE_WINPROB_MARGIN    = 0.12
MIN_WIN_PROB_FLOOR          = 0.50
NO_ENTRY_MIN_PRICE    = 0.35
# Lowered 0.75 → 0.65 on 2026-06-04. Resolved-trade replay (118 settled NO trades,
# entry ≥ 0.35) shows a sharp profitability cliff at 0.65: every band from 0.35–0.65
# is profitable (ROI +6% to +126%), while 0.65–0.70 (n=37) and 0.70–0.75 (n=20) both
# LOSE money (−8.7% / −5.0% ROI) despite a 59–70% win rate — pure payoff asymmetry
# (NO at 0.70 needs a 70% win rate just to break even, which the model's documented
# overconfidence erodes). Capping at 0.65 lifts settled-NO ROI 11.5% → 26.4%, adds
# +$43 realized P&L, and frees ~$756 of capital to redeploy into the 0.35–0.65 zone.
# NOTE: backtest.py cannot validate this (it assumes a fixed 0.50 mid, so the ceiling
# never binds); validated by resolved-trade counterfactual replay instead.
NO_ENTRY_MAX_PRICE    = 0.65
NO_MIN_ENSEMBLE_STD   = 0.8
ENSEMBLE_STD_MIN      = 0.5
ENSEMBLE_STD_MAX      = 2.0
MIN_HISTORY_DAYS      = 14
KELLY_FRACTION        = 0.10
MAX_TRADE_FRACTION    = 0.08
MAX_TRADE_USDC        = 15.0
STARTING_BANKROLL     = 1000.0
MAX_DEPLOYED_FRACTION    = 0.40
MAX_CITY_DATE_FRACTION   = 0.15
MIN_MARKET_VOLUME_USDC   = 500.0

# ── Accuracy guards (2026-06-09, PAPER ONLY — review ~2026-06-23) ─────────────
# Resolved-trade analysis of 154 settled trades found the model badly overconfident
# (stated 86% vs actual 63% win) with the worst leaks concentrated, not diffuse:
#   • |edge|>0.40 wins only 38% (−17.5% ROI, −$42 over n=16) — when the model
#     wildly disagrees with the market the market is right (adverse selection).
#     Cap edge at 0.40 so these noise trades are skipped.
#   • The 2× high-conviction Kelly boost (edge≥0.30) was AMPLIFYING that noisy
#     tail — neutralize it to 1.0.
#   • YES bets are 96% stated vs 43% actual (gap +53, n=7, uniformly wrong) — pause
#     them until the YES probability model is fixed.
# NOTE: lowering SHRINKAGE_FLOOR was tested and REJECTED — the replay showed it cuts
# PnL without improving win rate (miscalibration makes stated-confidence gating
# uninformative); the edge cap above targets the same problem directly. See
# [[payoff-asymmetry-levers-exhausted]] + calibration memory.
MAX_EDGE_ABS               = 0.40   # skip trades where |edge| exceeds this
HIGH_CONVICTION_KELLY_MULT = 1.0    # neutralize the 2× boost (was amplifying noise)
ENABLE_YES_BETS            = False  # pause YES entirely (anti-predictive: high conf → loses)

# ── T+1 lead-conditioned ensemble-std gate (2026-06-09, PAPER ONLY — review ~2026-06-16)
# The settled book splits by lead time: T+0 (same-day, nowcaster ground truth) carries
# all profit (+17.7% ROI); T+1 (day-before, pure forecast) is the overconfident-noise
# regime. At T+1, tight model agreement (low std) → specific bucket likely hit → NO bet
# fails (std∈[0,1.0): 54% win, −13.9% ROI). Gate T+1 NO bets at std>=1.0. Replay:
# guarded book 125→101 trades, +$184.35→+$230.51 PnL, 10.8%→16.8% ROI, monotonic
# T+1 win ramp 62.9→67.4→72.4% at std 0.8/1.0/1.2. Lead-conditioned: T+0 untouched
# (low-std same-day NO bets are +10.1% ROI — nowcaster carries them). Acts on forecast
# spread (different axis than the edge-cap/YES/price/city guards above) but stacked
# mid-window — track as its OWN forward-test line. Chose the gate alone (NOT the ×0.75
# T+1 stake trim — it lowers total PnL $230→$221 and muddies the forward read).
# Rollback: set T_PLUS_ONE_MIN_STD = 0.0.
T_PLUS_ONE_MIN_STD         = 1.0    # T+1 NO bets require ensemble_std >= 1.0°C

# ── City exclusions ───────────────────────────────────────────────────────────
# Re-admitted 2026-06-03 on corrected-RMSE evidence (Ankara, Beijing, Munich, San
# Francisco, Seoul, Taipei, Tokyo, Warsaw). PARTIALLY REVERTED 2026-06-09: the S2
# re-admission FAILED forward. Despite good corrected RMSE, the cold-bias cohort
# traded badly (watch-list said re-exclude if <55% over ≥5): Tokyo 40%/n5
# (rule-triggered), Ankara 0%/n2, San Francisco 25%/n4, Seoul 25%/n4, Munich 33%/n3
# — combined −$154 of drag. Re-excluded those 5. KEPT tradeable: Beijing (50%, +$2),
# Taipei (75%, +$3), Warsaw (50%, breakeven n2 — on watch). Corrected RMSE did not
# predict forward trade quality; revisit if calibration improves. See calibration memory.
# Long-standing exclusions: Buenos Aires (noisy, RMSE 2.14); Hong Kong, Chengdu,
# Wuhan (too few real-obs to validate); Chongqing (borderline, RMSE 1.37).
CITY_EXCLUDE: set[str] = {"Hong Kong", "Buenos Aires", "Chengdu", "Wuhan", "Chongqing",
                          "Tokyo", "Ankara", "San Francisco", "Seoul", "Munich"}
