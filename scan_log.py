"""Persistent per-EDIPI scan log shared across runs.

Stores one JSON record per scan under the shared data directory
(see ``settings.SETTINGS_DIR``) as ``scans.jsonl``:

    {"edipi": "1234567890", "ts": "2026-05-13T14:22:08.123456+00:00"}

Append-only; old records are kept indefinitely. Counts are computed by
reading the file and filtering by EDIPI and a time window.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from settings import SETTINGS_DIR as LOG_DIR

LOG_FILE = LOG_DIR / "scans.jsonl"


def record_scan(edipi: str, when: datetime | None = None) -> datetime:
    """Append a scan event to the log. Returns the timestamp recorded."""
    when = when or datetime.now(timezone.utc)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"edipi": edipi, "ts": when.isoformat()}) + "\n")
    return when


def _iter_records() -> Iterable[tuple[str, datetime]]:
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                yield rec["edipi"], datetime.fromisoformat(rec["ts"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue


def count_recent(
    edipi: str,
    within: timedelta = timedelta(days=1),
    now: datetime | None = None,
) -> int:
    """Count scans for ``edipi`` in the rolling ``within`` window ending now."""
    now = now or datetime.now(timezone.utc)
    return count_since(edipi, now - within, now)


def count_since(
    edipi: str,
    since: datetime,
    now: datetime | None = None,
) -> int:
    """Count scans for ``edipi`` between ``since`` and ``now`` (inclusive).

    Both ``since`` and ``now`` must be timezone-aware; comparison is done
    across timezones correctly. Useful for fixed-window counts like
    "drinks since the bar opened tonight at 20:00 local time"."""
    now = now or datetime.now(timezone.utc)
    return sum(1 for e, ts in _iter_records() if e == edipi and since <= ts <= now)


def prune_before(cutoff: datetime) -> int:
    """Drop records with ts < cutoff. Returns the number removed.

    Writes atomically via a sibling temp file + rename so a crash partway
    through cannot corrupt the log. Data minimization: callers pass the
    start of the current operating-hours window, or ``now`` when closed,
    to limit retention to the minimum needed for counting."""
    if not LOG_FILE.exists():
        return 0
    kept: list[str] = []
    removed = 0
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
                ts = datetime.fromisoformat(rec["ts"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if ts >= cutoff:
                kept.append(stripped)
            else:
                removed += 1
    if removed == 0:
        return 0
    tmp = LOG_FILE.parent / (LOG_FILE.name + ".tmp")
    body = "\n".join(kept) + ("\n" if kept else "")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(LOG_FILE)
    return removed
