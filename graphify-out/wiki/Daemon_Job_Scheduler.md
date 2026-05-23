# Daemon Job Scheduler

> 7 nodes · cohesion 0.38

## Key Concepts

- **daemon.py** (4 connections) — `daemon.py`
- **_build_schedule()** (4 connections) — `daemon.py`
- **_nowcast_utc_times()** (3 connections) — `daemon.py`
- **_run()** (2 connections) — `daemon.py`
- **Polymarket Bot Daemon Sleeps until the next relevant event, then fires the appro** (1 connections) — `daemon.py`
- **Return all nowcast fire times in UTC for a given date.** (1 connections) — `daemon.py`
- **Build a sorted list of (fire_time_utc, command_flag, label) for today + tomorrow** (1 connections) — `daemon.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `daemon.py`

## Audit Trail

- EXTRACTED: 16 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*