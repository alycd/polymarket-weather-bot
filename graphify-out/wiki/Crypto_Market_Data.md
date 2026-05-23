# Crypto Market Data

> 10 nodes · cohesion 0.27

## Key Concepts

- **cmd_scan_crypto()** (8 connections) — `main.py`
- **fetch_crypto_markets()** (7 connections) — `data/polymarket_crypto.py`
- **polymarket_crypto.py** (6 connections) — `data/polymarket_crypto.py`
- **get_crypto_market_prices()** (5 connections) — `data/polymarket_crypto.py`
- **_is_crypto_updown()** (2 connections) — `data/polymarket_crypto.py`
- **_parse_asset()** (2 connections) — `data/polymarket_crypto.py`
- **Polymarket crypto Up/Down market fetcher and parser.  Fetches active hourly "Bit** (1 connections) — `data/polymarket_crypto.py`
- **Get live CLOB prices for a crypto market.** (1 connections) — `data/polymarket_crypto.py`
- **Fetch active crypto Up/Down markets from Polymarket Gamma API.      Only returns** (1 connections) — `data/polymarket_crypto.py`
- **Scan for crypto Up/Down market edges and paper-trade any found.      Pipeline:** (1 connections) — `main.py`

## Relationships

- [[Portfolio Resolution]] (3 shared connections)
- [[Paper Trading Broker]] (3 shared connections)
- [[Polymarket Market Data]] (1 shared connections)
- [[Terminal Dashboard]] (1 shared connections)
- [[Deribit Options Data]] (1 shared connections)
- [[Crypto Edge Calculator]] (1 shared connections)

## Source Files

- `data/polymarket_crypto.py`
- `main.py`

## Audit Trail

- EXTRACTED: 33 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*