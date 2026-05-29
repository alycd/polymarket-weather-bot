"""
Paper-trading overrides.
Looser sizing to explore signal quality, and opens excluded cities for data gathering.
"""
from config import *  # noqa: F401, F403

# ── Position sizing (more aggressive — no real money at risk) ─────────────────
KELLY_FRACTION        = 0.25   # original paper fraction
MAX_TRADE_USDC        = 50.0   # higher cap to see full Kelly sizing
MAX_TRADE_FRACTION    = 0.08   # same as live
MAX_DEPLOYED_FRACTION = 0.60   # allow more deployment to gather data faster
MAX_CITY_DATE_FRACTION = 0.25  # wider city+date exposure

# ── Signal quality (thinner edges acceptable for discovery) ───────────────────
MIN_EDGE              = 0.10

# ── City exclusions (narrower — paper can tolerate model risk for data) ───────
CITY_EXCLUDE: set[str] = {
    "Hong Kong",     # weekly_market_prob returns P=1.0 on unbounded bucket (code bug — fix before re-enabling)
    "Ankara",        # structural NWP cold bias confirmed; keep out until bias corrector is retrained
    "Wuhan",         # single catastrophic miss; need more data before trusting model here
    # SF and Chengdu open in paper to gather calibration data
}
