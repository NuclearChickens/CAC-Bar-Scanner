"""Persistent audit log of drinks-reset events.

Stores one JSON record per reset in ``~/.cac_scanner/resets.jsonl``:

    {"ts": "2026-05-13T14:22:08.123456+00:00",
     "edipi1": "1234567890",
     "edipi2": "0987654321"}

Append-only. The reset log is the public audit trail and is never
pruned — entries must remain visible after the underlying scan data
has aged out of the scan log.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

LOG_DIR = Path.home() / ".cac_scanner"
LOG_FILE = LOG_DIR / "resets.jsonl"


def record_reset(
    edipi1: str,
    edipi2: str,
    when: datetime | None = None,
) -> datetime:
    """Append a reset event. Returns the timestamp recorded (UTC-aware)."""
    when = when or datetime.now(timezone.utc)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps({"ts": when.isoformat(), "edipi1": edipi1, "edipi2": edipi2})
            + "\n"
        )
    return when


def _iter_records() -> Iterable[tuple[datetime, str, str]]:
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                yield (
                    datetime.fromisoformat(rec["ts"]),
                    str(rec["edipi1"]),
                    str(rec["edipi2"]),
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                continue


def latest_reset() -> datetime | None:
    """Return the most recent reset timestamp, or None if there are none."""
    latest: datetime | None = None
    for ts, _e1, _e2 in _iter_records():
        if latest is None or ts > latest:
            latest = ts
    return latest


def list_resets() -> list[tuple[datetime, str, str]]:
    """Return all resets newest-first."""
    items = list(_iter_records())
    items.sort(key=lambda r: r[0], reverse=True)
    return items
