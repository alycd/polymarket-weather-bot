"""
Live-trading overrides.
Import everything from shared config, then tighten the risk params for real money.

Synced to paper_config.py on 2026-06-10 (user decision) — includes the forward-test
guards that were previously paper-only. Full empirical rationale for each value
lives in paper_config.py; keep the two files in sync deliberately, not by import,
so future paper-only experiments don't leak into live automatically.
"""
from config import *  # noqa: F401, F403

# ── Trading thresholds ────────────────────────────────────────────────────────
MIN_EDGE              = 0.12
MIN_WIN_PROB          = 0.70
MIN_WIN_PROB_YES      = 0.60
# Favorable-payoff relaxation below 0.45 entry (see paper_config.py, 2026-06-09).
LOW_PRICE_WINPROB_THRESHOLD = 0.45
LOW_PRICE_WINPROB_MARGIN    = 0.12
MIN_WIN_PROB_FLOOR          = 0.50
NO_ENTRY_MIN_PRICE    = 0.35
# 0.65 cap: NO entries above 0.65 lose on payoff asymmetry (replay-validated,
# see paper_config.py, 2026-06-04).
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

# ── Accuracy guards (see paper_config.py, 2026-06-09) ─────────────────────────
MAX_EDGE_ABS               = 0.40   # |edge|>0.40 is adverse-selection noise — skip
HIGH_CONVICTION_KELLY_MULT = 1.0    # neutralize the 2× boost (was amplifying noise)
ENABLE_YES_BETS            = False  # YES model anti-predictive — paused

# ── T+1 lead-conditioned ensemble-std gate (see paper_config.py, 2026-06-09) ──
T_PLUS_ONE_MIN_STD         = 1.0    # T+1 NO bets require ensemble_std >= 1.0°C

# ── City exclusions ───────────────────────────────────────────────────────────
# Matches paper (2026-06-09 revert): Tokyo/Ankara/SF/Seoul/Munich re-excluded after
# failed forward test; Beijing/Taipei/Warsaw kept tradeable. Long-standing: Buenos
# Aires, Hong Kong, Chengdu, Wuhan, Chongqing. Full history in paper_config.py.
CITY_EXCLUDE: set[str] = {"Hong Kong", "Buenos Aires", "Chengdu", "Wuhan", "Chongqing",
                          "Tokyo", "Ankara", "San Francisco", "Seoul", "Munich"}
