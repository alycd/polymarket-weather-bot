# Market Price Scraper

> 10 nodes · cohesion 0.29

## Key Concepts

- **price_scraper.py** (7 connections) — `data/price_scraper.py`
- **_collect_markets()** (6 connections) — `data/price_scraper.py`
- **scrape_and_store_all_prices()** (6 connections) — `data/price_scraper.py`
- **_fetch_and_store_one()** (4 connections) — `data/price_scraper.py`
- **_req()** (4 connections) — `data/price_scraper.py`
- **CLOB price history scraper.  Fetches hourly price snapshots for all resolved + a** (1 connections) — `data/price_scraper.py`
- **Fetch full hourly CLOB price history for one token and store it.     Returns num** (1 connections) — `data/price_scraper.py`
- **Fetch and store hourly CLOB price history for all resolved + active temp markets** (1 connections) — `data/price_scraper.py`
- **GET with exponential backoff on 429/5xx.** (1 connections) — `data/price_scraper.py`
- **Collect token_id + market_id for all temp markets:     - Resolved (closed=true,** (1 connections) — `data/price_scraper.py`

## Relationships

- [[Polymarket Market Data]] (4 shared connections)
- [[Portfolio Resolution]] (1 shared connections)
- [[Terminal Dashboard]] (1 shared connections)

## Source Files

- `data/price_scraper.py`

## Audit Trail

- EXTRACTED: 32 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*