# Polymarket Market Data

> 14 nodes · cohesion 0.19

## Key Concepts

- **polymarket.py** (9 connections) — `data/polymarket.py`
- **fetch_temperature_markets()** (8 connections) — `data/polymarket.py`
- **parse_question()** (8 connections) — `data/polymarket.py`
- **parse_clob_tokens()** (7 connections) — `data/polymarket.py`
- **get_clob_mid()** (4 connections) — `data/polymarket.py`
- **get_market_mid()** (3 connections) — `data/polymarket.py`
- **_parse_bucket()** (3 connections) — `data/polymarket.py`
- **Polymarket Gamma API + CLOB API fetchers. Parses temperature bucket markets and** (1 connections) — `data/polymarket.py`
- **Parse the temperature bucket portion of a question string.** (1 connections) — `data/polymarket.py`
- **Parse clobTokenIds which may arrive as a JSON string or a list.** (1 connections) — `data/polymarket.py`
- **Fetch all active temperature/weather markets from Polymarket.     Returns list o** (1 connections) — `data/polymarket.py`
- **Parse a Polymarket temperature market question.      Handles both daily and week** (1 connections) — `data/polymarket.py`
- **Fetch live CLOB midpoint for a YES token.     Returns float in [0, 1].     Raise** (1 connections) — `data/polymarket.py`
- **Get the best available mid price for a market, trying CLOB first then     fallin** (1 connections) — `data/polymarket.py`

## Relationships

- [[Real Historical Backtest]] (4 shared connections)
- [[Market Price Scraper]] (4 shared connections)
- [[Paper Trading Broker]] (3 shared connections)
- [[Portfolio Resolution]] (2 shared connections)
- [[Crypto Market Data]] (1 shared connections)
- [[TSA Market Integration]] (1 shared connections)

## Source Files

- `data/polymarket.py`

## Audit Trail

- EXTRACTED: 47 (96%)
- INFERRED: 2 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*