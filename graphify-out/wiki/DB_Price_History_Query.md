# DB Price History Query

> 2 nodes · cohesion 1.00

## Key Concepts

- **get_price_at_time()** (3 connections) — `db.py`
- **Return the mid_price closest to target_ts within ±window_hours, or None.** (1 connections) — `db.py`

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