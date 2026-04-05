"""
Operational state helpers for scheduler safety and observability.
"""
from __future__ import annotations

import json
import os
import time
import fcntl
from datetime import datetime, timezone
from statistics import quantiles

import db

_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOCK_DIR = os.path.join(_ROOT, ".locks")
os.makedirs(_LOCK_DIR, exist_ok=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _dur_key(job_type: str) -> str:
    return f"ops:durations:{job_type}"


def _run_key(job_type: str) -> str:
    return f"ops:last_run:{job_type}"


def _lock_path(job_type: str) -> str:
    return os.path.join(_LOCK_DIR, f"{job_type}.lock")


def acquire_job_lock(job_type: str):
    """Return (fd, acquired, owner_pid_or_none)."""
    path = _lock_path(job_type)
    fd = open(path, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.seek(0)
        fd.truncate()
        fd.write(str(os.getpid()))
        fd.flush()
        db.set_kv(f"ops:lock:{job_type}", json.dumps({
            "locked": True,
            "pid": os.getpid(),
            "at": _iso_now(),
        }))
        return fd, True, None
    except BlockingIOError:
        fd.seek(0)
        owner = (fd.read() or "").strip()
        try:
            owner_pid = int(owner)
        except Exception:
            owner_pid = None
        fd.close()
        return None, False, owner_pid


def release_job_lock(job_type: str, fd):
    if not fd:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        fd.close()
    except Exception:
        pass
    db.set_kv(f"ops:lock:{job_type}", json.dumps({
        "locked": False,
        "pid": None,
        "at": _iso_now(),
    }))


def mark_job_start(job_type: str):
    db.set_kv(_run_key(job_type), json.dumps({
        "status": "running",
        "started_at": _iso_now(),
        "last_success_at": get_last_success(job_type),
        "last_error": get_last_error(job_type),
    }))
    return time.time()


def mark_job_end(job_type: str, ok: bool, started_ts: float, error: str | None = None):
    elapsed = max(0.0, time.time() - started_ts)
    _record_duration(job_type, elapsed)
    payload = _safe_json(db.get_kv(_run_key(job_type)), {})
    payload["status"] = "ok" if ok else "error"
    payload["finished_at"] = _iso_now()
    payload["last_duration_s"] = round(elapsed, 3)
    if ok:
        payload["last_success_at"] = payload["finished_at"]
        payload["last_error"] = None
    else:
        payload["last_error"] = str(error or "unknown error")
    db.set_kv(_run_key(job_type), json.dumps(payload))
    if not ok:
        db.log_event("JOB_ERROR", f"{job_type} failed: {payload['last_error']}")


def _record_duration(job_type: str, duration_s: float):
    rows = _safe_json(db.get_kv(_dur_key(job_type)), [])
    rows.append(float(duration_s))
    rows = rows[-120:]
    db.set_kv(_dur_key(job_type), json.dumps(rows))


def get_duration_p95(job_type: str) -> float | None:
    rows = _safe_json(db.get_kv(_dur_key(job_type)), [])
    if len(rows) < 2:
        return rows[0] if rows else None
    try:
        return float(quantiles(rows, n=100, method="inclusive")[94])
    except Exception:
        return float(sorted(rows)[int(0.95 * (len(rows) - 1))])


def get_last_success(job_type: str) -> str | None:
    payload = _safe_json(db.get_kv(_run_key(job_type)), {})
    return payload.get("last_success_at")


def get_last_error(job_type: str) -> str | None:
    payload = _safe_json(db.get_kv(_run_key(job_type)), {})
    return payload.get("last_error")


def update_datasource_health(name: str, ok: bool, detail: str = ""):
    key = f"ops:ds:{name}"
    payload = _safe_json(db.get_kv(key), {
        "fails": 0,
        "oks": 0,
        "state": "ok",
        "updated_at": _iso_now(),
        "last_error": None,
    })
    if ok:
        payload["oks"] = int(payload.get("oks", 0)) + 1
        payload["fails"] = 0
        payload["state"] = "ok"
        payload["last_error"] = None
    else:
        payload["fails"] = int(payload.get("fails", 0)) + 1
        payload["state"] = "offline" if payload["fails"] >= 5 else "degraded"
        payload["last_error"] = detail[:240] if detail else "unknown"
    payload["updated_at"] = _iso_now()
    db.set_kv(key, json.dumps(payload))


def get_datasource_health(name: str) -> dict:
    return _safe_json(db.get_kv(f"ops:ds:{name}"), {
        "state": "ok",
        "fails": 0,
        "oks": 0,
        "updated_at": None,
        "last_error": None,
    })


def should_run_daily_reconcile() -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    return db.get_kv("ops:last_reconcile_day") != today


def mark_daily_reconcile():
    today = datetime.now(timezone.utc).date().isoformat()
    db.set_kv("ops:last_reconcile_day", today)


def get_ops_snapshot() -> dict:
    job_types = ("scan", "exit-scan", "resolve")
    jobs = {}
    for jt in job_types:
        run = _safe_json(db.get_kv(_run_key(jt)), {})
        lock = _safe_json(db.get_kv(f"ops:lock:{jt}"), {"locked": False, "pid": None, "at": None})
        jobs[jt] = {
            "last_success_at": run.get("last_success_at"),
            "last_error": run.get("last_error"),
            "status": run.get("status"),
            "last_duration_s": run.get("last_duration_s"),
            "p95_duration_s": get_duration_p95(jt),
            "lock": lock,
        }
    return {
        "jobs": jobs,
        "datasources": {
            "openmeteo": get_datasource_health("openmeteo"),
            "polymarket": get_datasource_health("polymarket"),
            "wunderground": get_datasource_health("wunderground"),
        },
    }
