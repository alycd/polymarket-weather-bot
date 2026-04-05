"""
Deribit market data — BTC/ETH index price and implied volatility.

Used as the signal source for crypto Up/Down edge calculation.
All data is public, no API key required.
"""
import logging
import math
import requests

logger = logging.getLogger(__name__)

DERIBIT_API = "https://www.deribit.com/api/v2/public"
TIMEOUT = 10


def get_index_price(symbol: str) -> float | None:
    """
    Return current Deribit index price for 'btc_usd' or 'eth_usd'.
    """
    try:
        resp = requests.get(
            f"{DERIBIT_API}/get_index_price",
            params={"index_name": symbol},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return float(resp.json()["result"]["index_price"])
    except Exception as e:
        logger.error("Deribit index price failed (%s): %s", symbol, e)
        return None


def get_atm_iv(currency: str, expiry_label: str, spot: float) -> float | None:
    """
    Return annualised implied volatility interpolated near spot for the given
    expiry label (e.g. '27MAR26').

    Fetches the two strikes closest to spot and linearly interpolates IV.
    Falls back to a wider search if the nearest strike has no market.
    """
    try:
        instr = requests.get(
            f"{DERIBIT_API}/get_instruments",
            params={"currency": currency, "kind": "option", "expired": "false"},
            timeout=TIMEOUT,
        ).json()["result"]
    except Exception as e:
        logger.error("Deribit instruments failed: %s", e)
        return None

    calls = [
        o for o in instr
        if expiry_label in o["instrument_name"] and o["instrument_name"].endswith("-C")
    ]
    if not calls:
        logger.warning("No calls found for %s %s", currency, expiry_label)
        return None

    calls.sort(key=lambda o: abs(o["strike"] - spot))

    # Try the two nearest strikes and interpolate
    ivs = []
    for o in calls[:4]:
        try:
            tick = requests.get(
                f"{DERIBIT_API}/ticker",
                params={"instrument_name": o["instrument_name"]},
                timeout=TIMEOUT,
            ).json()["result"]
            iv = tick.get("mark_iv")
            if iv and iv > 0:
                ivs.append((o["strike"], iv / 100.0))  # convert % → decimal
        except Exception:
            continue
        if len(ivs) >= 2:
            break

    if not ivs:
        return None
    if len(ivs) == 1:
        return ivs[0][1]

    # Linear interpolation between the two closest strikes
    (k1, v1), (k2, v2) = ivs[0], ivs[1]
    if k1 == k2:
        return v1
    w = max(0.0, min(1.0, (spot - k1) / (k2 - k1)))
    return v1 * (1 - w) + v2 * w


def get_crypto_signal_inputs(symbol: str) -> dict | None:
    """
    Return everything the edge calculator needs for one crypto asset.

    symbol: 'BTC' or 'ETH'

    Returns:
        {
            "spot":          float,   # current index price
            "iv_annual":     float,   # ATM implied vol (annualised, decimal)
            "expiry_label":  str,     # Deribit expiry used (e.g. '27MAR26')
        }
    or None on failure.
    """
    index_name = f"{symbol.lower()}_usd"
    spot = get_index_price(index_name)
    if spot is None:
        return None

    # Find today's expiry label from available instruments
    try:
        instr = requests.get(
            f"{DERIBIT_API}/get_instruments",
            params={"currency": symbol, "kind": "option", "expired": "false"},
            timeout=TIMEOUT,
        ).json()["result"]
        expirations = sorted(set(o["expiration_timestamp"] for o in instr))
    except Exception as e:
        logger.error("Could not fetch instruments for %s: %s", symbol, e)
        return None

    if not expirations:
        return None

    # Use the nearest upcoming expiry
    from datetime import datetime, timezone
    nearest_ts = expirations[0]
    nearest_dt = datetime.fromtimestamp(nearest_ts / 1000, tz=timezone.utc)
    expiry_label = nearest_dt.strftime("%d%b%y").upper()  # e.g. '27MAR26'

    iv = get_atm_iv(symbol, expiry_label, spot)
    if iv is None:
        # Fallback: use next expiry
        if len(expirations) > 1:
            next_dt = datetime.fromtimestamp(expirations[1] / 1000, tz=timezone.utc)
            expiry_label = next_dt.strftime("%d%b%y").upper()
            iv = get_atm_iv(symbol, expiry_label, spot)

    if iv is None:
        logger.warning("Could not get IV for %s — using fallback 0.60", symbol)
        iv = 0.60

    logger.debug("%s spot=%.2f iv=%.1f%% expiry=%s", symbol, spot, iv * 100, expiry_label)
    return {
        "spot":         spot,
        "iv_annual":    iv,
        "expiry_label": expiry_label,
    }
