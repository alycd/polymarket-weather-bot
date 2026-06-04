"""
Paper-trading overrides.
Looser sizing to explore signal quality, and opens excluded cities for data gathering.
"""
from config import *  # noqa: F401, F403

# ── Trading thresholds ────────────────────────────────────────────────────────
MIN_EDGE              = 0.12
MIN_WIN_PROB          = 0.70
MIN_WIN_PROB_YES      = 0.60
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

# ── City exclusions ───────────────────────────────────────────────────────────
# Re-admitted 2026-06-03: Ankara, Beijing, Munich, San Francisco, Seoul, Taipei,
# Tokyo, Warsaw. These were excluded during warmup for a large COLD forecast bias
# (+1.0–2.0°C), not genuine noise. Per-model/month bias corrections are now
# populated; applying the live corrections drops their forecast RMSE to 0.5–1.25°C
# (≤ the tradeable-city average of 1.20°C) with near-zero residual bias. Validated
# against real ASOS/WU obs at lead 0–1. See bias-correction memory + S2 backtest.
# Still excluded: Buenos Aires (genuinely noisy, corrected RMSE 2.14); Hong Kong,
# Chengdu, Wuhan (too few real-obs points to validate re-admission yet); Chongqing
# (borderline, corrected RMSE 1.37).
CITY_EXCLUDE: set[str] = {"Hong Kong", "Buenos Aires", "Chengdu", "Wuhan", "Chongqing"}
