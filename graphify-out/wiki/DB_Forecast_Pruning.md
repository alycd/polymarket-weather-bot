# DB Forecast Pruning

> 2 nodes · cohesion 1.00

## Key Concepts

- **prune_old_forecasts()** (3 connections) — `db.py`
- **Delete model forecast rows whose target_date is older than N days. Returns count** (1 connections) — `db.py`

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