"""
Confidence tiering — size your bets by how certain the signal is.

Four tiers, each applies a multiplier to the base Kelly fraction:

  Tier 1 — Near-certain intraday (1.0×):
    Nowcast weight > 0.8 AND ensemble is sweet_spot or agree.
    You can see the temperature as it's happening.

  Tier 1.5 — Very strong pre-market signal (0.75×):
    Station ready + climo confirms + |edge| >= 0.15 + sweet_spot/agree.
    Reserve for your highest-conviction day-ahead bets.

  Tier 2 — Bias-corrected + climo confirms (0.5×):
    Station is ready AND climo available AND deviation < 2 climo-std.

  Tier 3 — Raw or uncertain (0.25×):
    Station warming_up, OR climo missing, OR extreme deviation.

  Tier 4 — Skip (0.0×):
    Ensemble score is 'chaotic'. All others are eligible to trade.
"""
import logging

logger = logging.getLogger(__name__)

TIER_NAMES = {1: "near_certain", 2: "corrected", 3: "raw", 4: "skip"}


def classify_confidence(
    signal: dict,
    station_ready: bool,
    nowcast_weight: float = 0.0,
) -> tuple[int, float, str]:
    """
    Classify a signal into a confidence tier.

    signal: output of compute_edge() (must be non-None)
    station_ready: whether the station has >= MIN_HISTORY_DAYS of bias data
    nowcast_weight: current nowcast confidence (0–1)

    Returns (tier: int, kelly_multiplier: float, tier_name: str)
    """
    ensemble_score = signal.get("ensemble_score", "")
    has_climo      = signal.get("has_climo", False)
    climo_dev      = signal.get("climo_deviation_c")
    # Use actual stored climo std if available, fall back to conservative proxy
    climo_std      = signal.get("climo_std_c") or 3.0
    edge_abs       = abs(signal.get("edge", 0.0))

    # Tier 4: chaotic models — untradeable regardless
    if ensemble_score == "chaotic":
        logger.debug("Tier 4: ensemble chaotic")
        return 4, 0.0, TIER_NAMES[4]

    # Tier 1: live nowcast is dominant — we can nearly see the final answer
    if nowcast_weight >= 0.8:
        logger.debug("Tier 1: nowcast_weight=%.2f", nowcast_weight)
        return 1, 1.0, TIER_NAMES[1]

    # Tier 1.5: very strong pre-market signal with climo confirmation
    if station_ready and has_climo and climo_dev is not None and edge_abs >= 0.15:
        if abs(climo_dev) <= 2.0 * climo_std:
            logger.debug("Tier 1.5: high-edge=%.3f climo_dev=%.1f", edge_abs, climo_dev)
            return 2, 0.75, "high_edge"   # reuse tier slot 2 with higher multiplier

    # Tier 2: bias-corrected, climo confirms, ensemble not extreme
    if station_ready:
        if has_climo and climo_dev is not None:
            if abs(climo_dev) <= 2.0 * climo_std:
                logger.debug("Tier 2: station_ready, climo_dev=%.1f", climo_dev)
                return 2, 0.5, TIER_NAMES[2]
            else:
                logger.debug("Tier 3: extreme climo deviation %.1f°C (std=%.1f)", climo_dev, climo_std)
                return 3, 0.25, TIER_NAMES[3]
        else:
            # No climo yet — still corrected, just no baseline
            logger.debug("Tier 2: station_ready, no climo")
            return 2, 0.5, TIER_NAMES[2]

    # Tier 3: warming up or missing climo
    logger.debug("Tier 3: station_ready=%s, has_climo=%s", station_ready, has_climo)
    return 3, 0.25, TIER_NAMES[3]


def apply_tier_to_signal(signal: dict, station_ready: bool) -> dict:
    """
    Apply confidence tiering to a signal dict in-place.
    Scales size_usdc by the tier multiplier.
    Returns the modified signal.
    """
    nowcast_weight = signal.get("nowcast_weight", 0.0)
    tier, multiplier, tier_name = classify_confidence(signal, station_ready, nowcast_weight)

    original_size = signal["size_usdc"]
    tiered_size   = round(original_size * multiplier, 2)

    signal["confidence_tier"]  = tier
    signal["tier_name"]        = tier_name
    signal["kelly_multiplier"] = multiplier
    signal["size_usdc"]        = tiered_size

    logger.debug("Tier %d (%s): size $%.2f → $%.2f (×%.2f)",
                 tier, tier_name, original_size, tiered_size, multiplier)
    return signal
