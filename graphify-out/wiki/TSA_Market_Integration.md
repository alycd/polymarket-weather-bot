# TSA Market Integration

> 10 nodes · cohesion 0.24

## Key Concepts

- **fetch_tsa_markets()** (6 connections) — `data/polymarket_tsa.py`
- **polymarket_tsa.py** (6 connections) — `data/polymarket_tsa.py`
- **get_tsa_market_prices()** (4 connections) — `data/polymarket_tsa.py`
- **parse_tsa_question()** (4 connections) — `data/polymarket_tsa.py`
- **_parse_tsa_bucket()** (3 connections) — `data/polymarket_tsa.py`
- **Polymarket TSA passenger market fetcher and parser.  Fetches active "How many TS** (1 connections) — `data/polymarket_tsa.py`
- **Extract passenger count bucket from a question string.      Handles raw counts a** (1 connections) — `data/polymarket_tsa.py`
- **Fetch active TSA passenger count markets from Polymarket Gamma API.      Uses th** (1 connections) — `data/polymarket_tsa.py`
- **Get live CLOB prices for a TSA market. Same interface as get_market_prices().** (1 connections) — `data/polymarket_tsa.py`
- **Parse a Polymarket TSA passenger question.      Handles patterns like:       "Wi** (1 connections) — `data/polymarket_tsa.py`

## Relationships

- [[Paper Trading Broker]] (3 shared connections)
- [[Portfolio Resolution]] (2 shared connections)
- [[Polymarket Market Data]] (1 shared connections)

## Source Files

- `data/polymarket_tsa.py`

## Audit Trail

- EXTRACTED: 27 (96%)
- INFERRED: 1 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*