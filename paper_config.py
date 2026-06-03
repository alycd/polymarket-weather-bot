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
NO_ENTRY_MAX_PRICE    = 0.75
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
