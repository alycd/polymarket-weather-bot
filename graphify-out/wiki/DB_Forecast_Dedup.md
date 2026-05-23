# DB Forecast Dedup

> 2 nodes · cohesion 1.00

## Key Concepts

- **insert_forecast_if_missing()** (3 connections) — `db.py`
- **Insert a historical forecast only if no row yet exists for (icao, target_date, m** (1 connections) — `db.py`

## Relationships

- [[Database Core Layer]] (2 shared connections)

## Source Files

- `db.py`

## Audit Trail

- EXTRACTED: 4 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*