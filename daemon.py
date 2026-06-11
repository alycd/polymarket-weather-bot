"""
Polymarket Bot Daemon
Sleeps until the next relevant event, then fires the appropriate command.

Events (all times UTC):
  - 05:30  ECMWF 00Z processed → --scan  (new forecasts, enter positions)
  - 10:00  GFS 06Z processed   → --scan  (secondary update)
  - 17:30  ECMWF 12Z processed → --scan  (afternoon forecast update)
  - Every 30m opportunistic scan  → --scan
  - Every 30m risk check          → --exit-scan
  - Per-city nowcast windows (2pm and 3:30pm local → UTC) → --nowcast
  - 01:00  Daily resolve        → --resolve

Run once:
  source venv/bin/activate && python daemon.py
"""

import logging
import time
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("daemon")

# ── Event schedule ────────────────────────────────────────────────────────────

# Fixed UTC times for model runs: (hour, minute, command, label)
MODEL_RUN_EVENTS = [
    (7,  13, "--scan",    "ECMWF 00Z + GFS 00Z scan"),
    (9,  45, "--scan",    "GFS 06Z + ICON 06Z scan"),
    (13, 30, "--scan",    "Europe nowcast window scan"),
    (19, 17, "--scan",    "GFS 12Z + US nowcast scan"),
    (7,  47, "--resolve", "Morning resolve"),
    (19, 55, "--resolve", "Afternoon resolve"),
    # Refresh calibration shrinkage factors daily. Deliberately placed at :15 — a
    # scan-free gap (the 30-min opportunistic + exit scans fire on :00/:30) and after
    # the 07:47 morning resolve has settled overnight trades, so the shrink factor is
    # recomputed on fresh outcomes without contending with a scan.
    (8,  15, "--calibration", "Daily calibration + shrinkage refresh"),
]

# Weekly maintenance events: (weekday, hour, minute, command, label).
# weekday: Monday=0 … Sunday=6 (matches datetime.weekday()).
# Backfill is heavy (all cities × ASOS/ERA5/Open-Meteo) and refreshes bias
# corrections (recompute_bias) for EVERY city — including not-yet-traded re-admitted
# ones, whose corrections otherwise only update when one of their trades resolves.
# Placed Sunday 03:15 UTC: a quiet, scan-free gap far from the fixed
# scans/resolves/nowcasts (worst case it delays one 03:30 opportunistic/exit scan).
WEEKLY_EVENTS = [
    (6, 3, 15, "--backfill", "Weekly backfill (refresh obs + bias corrections)"),
]

# Per-city nowcast windows: fire at 2:00pm and 3:30pm local time
CITY_TIMEZONES = {
    "New York City":  "America/New_York",
    "Chicago":        "America/Chicago",
    "Atlanta":        "America/New_York",
    "Miami":          "America/New_York",
    "Dallas":         "America/Chicago",
    "Seattle":        "America/Los_Angeles",
    "London":         "Europe/London",
    "Paris":          "Europe/Paris",
    "Madrid":         "Europe/Madrid",
    "Munich":         "Europe/Berlin",
    "Milan":          "Europe/Rome",
    "Hong Kong":      "Asia/Hong_Kong",
    "Toronto":        "America/Toronto",
    "Buenos Aires":   "America/Argentina/Buenos_Aires",
    "Sao Paulo":      "America/Sao_Paulo",
    "Tel Aviv":       "Asia/Jerusalem",
}

NOWCAST_LOCAL_HOURS = [14, 0]   # 2:00pm local
NOWCAST_LOCAL_HOURS2 = [15, 30]  # 3:30pm local


def _nowcast_utc_times(date_utc: datetime.date) -> list[tuple[datetime, str]]:
    """Return all nowcast fire times in UTC for a given date."""
    events = []
    seen_utc = set()
    for city, tz_str in CITY_TIMEZONES.items():
        tz = ZoneInfo(tz_str)
        for h, m in [NOWCAST_LOCAL_HOURS, NOWCAST_LOCAL_HOURS2]:
            # Build naive local datetime then localise
            local_naive = datetime(date_utc.year, date_utc.month, date_utc.day, h, m)
            local_dt = local_naive.replace(tzinfo=tz)
            utc_dt = local_dt.astimezone(timezone.utc)
            key = utc_dt.replace(second=0, microsecond=0)
            if key not in seen_utc:
                seen_utc.add(key)
                events.append((key, f"Nowcast {city} {h:02d}:{m:02d} local"))
    return events


def _build_schedule(now: datetime) -> list[tuple[datetime, str, str]]:
    """
    Build a sorted list of (fire_time_utc, command_flag, label) for today + tomorrow.
    Skips any events already in the past.
    """
    events = []
    for day_offset in [0, 1]:
        d = (now + timedelta(days=day_offset)).date()
        # Fixed model run events
        for h, m, flag, label in MODEL_RUN_EVENTS:
            fire = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
            if fire > now:
                events.append((fire, flag, label))
        # Weekly maintenance events (only on the matching weekday)
        for wd, h, m, flag, label in WEEKLY_EVENTS:
            if d.weekday() == wd:
                fire = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
                if fire > now:
                    events.append((fire, flag, label))
        # Nowcast events
        for fire, label in _nowcast_utc_times(d):
            if fire > now:
                events.append((fire, "--nowcast", label))
        # Exit scan every 30 minutes (faster risk management / capital recycling)
        for hour in range(24):
            for minute in (0, 30):
                fire = datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)
                if fire > now:
                    events.append((fire, "--exit-scan",
                                  f"30m exit scan {hour:02d}:{minute:02d} UTC"))

        # Opportunistic scan every 30 minutes so fresh bankroll gets redeployed quickly
        # between major model-run scans.
        for hour in range(24):
            for minute in (0, 30):
                fire = datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)
                if fire > now:
                    events.append((fire, "--scan",
                                  f"30m opportunistic scan {hour:02d}:{minute:02d} UTC"))

        # Hourly live reconcile at :20 past the hour — clear of the :00/:30 scan
        # grid and the 08:15 calibration slot. Finalizes pending fills, cancels
        # stale orders, and alerts on DB↔chain divergence. No-op in paper mode.
        for hour in range(24):
            fire = datetime(d.year, d.month, d.day, hour, 20, tzinfo=timezone.utc)
            if fire > now:
                events.append((fire, "--reconcile",
                              f"Hourly reconcile {hour:02d}:20 UTC"))

    events.sort(key=lambda x: x[0])
    return events


def _run(flag: str, label: str, mode: str = "paper"):
    log.info("▶  %s  (%s)", label, flag)
    extra_args = []
    if flag == "--scan" and label.startswith("30m opportunistic scan"):
        extra_args = ["--opportunistic"]
    result = subprocess.run(
        [sys.executable, "main.py", "--mode", mode, flag, *extra_args],
        capture_output=False,
    )
    if result.returncode != 0:
        log.warning("⚠  %s exited with code %d", flag, result.returncode)
    else:
        log.info("✓  %s done", label)


def run(mode: str = "paper"):
    log.info("Daemon starting in %s mode.", mode)
    import os
    os.makedirs("logs", exist_ok=True)

    while True:
        now = datetime.now(timezone.utc)
        schedule = _build_schedule(now)

        if not schedule:
            log.warning("Empty schedule — sleeping 1h")
            time.sleep(3600)
            continue

        next_fire, next_flag, next_label = schedule[0]
        wait_secs = (next_fire - now).total_seconds()

        log.info("Next: %s at %s UTC (in %.0fm)",
                 next_label,
                 next_fire.strftime("%H:%M"),
                 wait_secs / 60)

        if wait_secs > 0:
            time.sleep(wait_secs)

        # Re-check time after sleep (handles system clock drift / DST)
        now2 = datetime.now(timezone.utc)
        if abs((now2 - next_fire).total_seconds()) < 120:
            _run(next_flag, next_label, mode=mode)
        else:
            log.warning("Clock drift detected, re-evaluating schedule")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["paper", "live"], default="paper")
    args = p.parse_args()
    run(mode=args.mode)
