"""Persistent audit log of drinks-reset events.

Stores one JSON record per reset under the shared data directory
(see ``settings.SETTINGS_DIR``) as ``resets.jsonl``:

    {"ts": "2026-05-13T14:22:08.123456+00:00"}

Append-only. The reset log is the public audit trail and is never
pruned — entries must remain visible after the underlying scan data
has aged out of the scan log.

Legacy entries written before password auth replaced two-CAC integrity
also carry ``edipi1`` / ``edipi2`` fields; the reader returns them as
optional tuple elements so historical records can still be displayed
with the two authorizing EDIPIs.

``latest_reset()`` sits on the per-scan hot path (via
``_effective_since``) so its result is cached in memory and only
invalidated when ``record_reset`` writes a new entry. The full-file
iterator is only walked by the Logs tab.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from settings import SETTINGS_DIR as LOG_DIR

LOG_FILE = LOG_DIR / "resets.jsonl"


_latest_cached: datetime | None = None
_latest_loaded: bool = False


def _ensure_latest_loaded() -> None:
    """Populate ``_latest_cached`` from disk once. Idempotent."""
    global _latest_cached, _latest_loaded
    if _latest_loaded:
        return
    latest: datetime | None = None
    for ts, _e1, _e2 in _iter_records():
        if latest is None or ts > latest:
            latest = ts
    _latest_cached = latest
    _latest_loaded = True


def record_reset(when: datetime | None = None) -> datetime:
    """Append a reset event. Returns the timestamp recorded (UTC-aware)."""
    global _latest_cached, _latest_loaded
    when = when or datetime.now(timezone.utc)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": when.isoformat()}) + "\n")
    _ensure_latest_loaded()
    if _latest_cached is None or when > _latest_cached:
        _latest_cached = when
    return when


def _iter_records() -> Iterable[tuple[datetime, str | None, str | None]]:
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec["ts"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            e1 = rec.get("edipi1")
            e2 = rec.get("edipi2")
            yield (ts, str(e1) if e1 else None, str(e2) if e2 else None)


def latest_reset() -> datetime | None:
    """Return the most recent reset timestamp, or None if there are none."""
    _ensure_latest_loaded()
    return _latest_cached


def list_resets() -> list[tuple[datetime, str | None, str | None]]:
    """Return all resets newest-first. Each entry is
    (timestamp, edipi1_or_None, edipi2_or_None) — the EDIPIs only appear
    in legacy two-CAC records."""
    items = list(_iter_records())
    items.sort(key=lambda r: r[0], reverse=True)
    return items
