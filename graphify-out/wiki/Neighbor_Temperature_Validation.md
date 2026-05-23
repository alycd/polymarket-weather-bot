# Neighbor Temperature Validation

> 8 nodes · cohesion 0.29

## Key Concepts

- **get_neighbor_penalty()** (5 connections) — `signals/neighbor_check.py`
- **clear_session_cache()** (4 connections) — `signals/neighbor_check.py`
- **neighbor_check.py** (4 connections) — `signals/neighbor_check.py`
- **_fetch_reference_temp()** (3 connections) — `signals/neighbor_check.py`
- **Neighbor validation — cross-station sanity filter.  For each city that has a NEI** (1 connections) — `signals/neighbor_check.py`
- **Clear the in-session cache. The cache clears naturally between process runs.** (1 connections) — `signals/neighbor_check.py`
- **Fetch the GFS daily max temperature at the reference coordinate for city.     Re** (1 connections) — `signals/neighbor_check.py`
- **Returns (size_multiplier, reason_str).      multiplier = 1.0  — no neighbor ref** (1 connections) — `signals/neighbor_check.py`

## Relationships

- [[Portfolio Resolution]] (4 shared connections)

## Source Files

- `signals/neighbor_check.py`

## Audit Trail

- EXTRACTED: 20 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*