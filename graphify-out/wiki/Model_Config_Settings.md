# Model Config Settings

> 6 nodes · cohesion 0.33

## Key Concepts

- **get_neighbor_penalty** (4 connections) — `signals/neighbor_check.py`
- **OPENMETEO_MODELS** (2 connections) — `config.py`
- **_fetch_reference_temp** (2 connections) — `signals/neighbor_check.py`
- **HRRR Coverage Bounds (CONUS only)** (1 connections) — `config.py`
- **NEIGHBOR_REFS** (1 connections) — `config.py`
- **Neighbor Grid Artifact Detection Design** (1 connections) — `signals/neighbor_check.py`

## Relationships

- [[Forecast DB Queries]] (1 shared connections)

## Source Files

- `config.py`
- `signals/neighbor_check.py`

## Audit Trail

- EXTRACTED: 11 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*