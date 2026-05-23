# Signal Ensemble Weights

> 9 nodes · cohesion 0.25

## Key Concepts

- **get_freshness_weights()** (6 connections) — `signals/model_freshness.py`
- **ensemble.py** (3 connections) — `signals/ensemble.py`
- **_last_available()** (3 connections) — `signals/model_freshness.py`
- **model_freshness.py** (3 connections) — `signals/model_freshness.py`
- **NWP Model Freshness Decay** (2 connections) — `signals/model_freshness.py`
- **Multi-model ensemble disagreement scorer.  Takes the bias-corrected model predic** (1 connections) — `signals/ensemble.py`
- **Model freshness weighting.  NWP models are initialized at fixed UTC cycle times** (1 connections) — `signals/model_freshness.py`
- **Return the UTC datetime of the model's most recently available cycle.** (1 connections) — `signals/model_freshness.py`
- **Return a freshness multiplier in (0, 1] for each known model.      Call once per** (1 connections) — `signals/model_freshness.py`

## Relationships

- [[Real Backtest Processing]] (2 shared connections)
- [[Polymarket Position Manager]] (1 shared connections)

## Source Files

- `signals/ensemble.py`
- `signals/model_freshness.py`

## Audit Trail

- EXTRACTED: 20 (95%)
- INFERRED: 1 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*