"""
Live-trading overrides.
Import everything from shared config, then tighten the risk params for real money.
"""
from config import *  # noqa: F401, F403

# ── Position sizing (tighter for real USDC) ───────────────────────────────────
KELLY_FRACTION        = 0.10   # fractional Kelly — conservative for live
MAX_TRADE_USDC        = 15.0   # hard per-trade cap
MAX_TRADE_FRACTION    = 0.08   # max single trade as % of bankroll
MAX_DEPLOYED_FRACTION = 0.40   # max % portfolio in open positions
MAX_CITY_DATE_FRACTION = 0.15  # max % deployed per city+date

# ── Signal quality (stricter edge required) ───────────────────────────────────
MIN_EDGE              = 0.12

# ── City exclusions (structural model failures or code-level issues) ──────────
CITY_EXCLUDE: set[str] = {
    "Hong Kong",     # weekly_market_prob returns P=1.0 on unbounded bucket (code bug)
    "Chengdu",       # insufficient resolved data, mixed results
    "Wuhan",         # single catastrophic miss, insufficient data
    "Ankara",        # structural NWP cold bias confirmed across 2 trades
    "San Francisco", # marine-layer cold bias, revisit at ~15 resolved trades
}
