"""
Live-trading overrides.
Import everything from shared config, then tighten the risk params for real money.
"""
from config import *  # noqa: F401, F403

# ── Trading thresholds ────────────────────────────────────────────────────────
MIN_EDGE              = 0.12
MIN_WIN_PROB          = 0.70
MIN_WIN_PROB_YES      = 0.52
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
CITY_EXCLUDE: set[str] = {"Hong Kong", "Buenos Aires", "Warsaw", "Chengdu", "Wuhan", "Ankara", "San Francisco"}
