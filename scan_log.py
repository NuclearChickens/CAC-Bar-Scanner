"""Persistent per-EDIPI scan log shared across runs.

Stores one JSON record per scan under the shared data directory
(see ``settings.SETTINGS_DIR``) as ``scans.jsonl``:

    {"edipi": "1234567890", "ts": "2026-05-13T14:22:08.123456+00:00"}

Append-only; old records are kept indefinitely. Counts are computed by
reading the file and filtering by EDIPI and a time window.

An in-memory cache mirrors the on-disk file so per-scan counts stay
O(cache size) instead of O(N) file reads. The file remains the source
of truth across process restarts — the cache lazily loads from disk
on first read, then updates in step with every ``record_scan`` /
``prune_before`` call.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from settings import SETTINGS_DIR as LOG_DIR

LOG_FILE = LOG_DIR / "scans.jsonl"


_records: list[tuple[str, datetime]] = []
_loaded: bool = False


def _ensure_loaded() -> None:
    """Populate ``_records`` from disk on first access. Idempotent."""
    global _loaded
    if _loaded:
        return
    _records.clear()
    if LOG_FILE.exists():
        with LOG_FILE.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    _records.append(
                        (rec["edipi"], datetime.fromisoformat(rec["ts"]))
                    )
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    _loaded = True


def record_scan(edipi: str, when: datetime | None = None) -> datetime:
    """Append a scan event to the log. Returns the timestamp recorded."""
    when = when or datetime.now(timezone.utc)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"edipi": edipi, "ts": when.isoformat()}) + "\n")
    _ensure_loaded()
    _records.append((edipi, when))
    return when


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
    _ensure_loaded()
    return sum(1 for e, ts in _records if e == edipi and since <= ts <= now)


def count_total_since(
    since: datetime,
    now: datetime | None = None,
) -> int:
    """Count every scan across all EDIPIs between ``since`` and ``now``.

    Used for the bar-wide drinks-served counter. Mirrors ``count_since``
    but without the per-EDIPI filter."""
    now = now or datetime.now(timezone.utc)
    _ensure_loaded()
    return sum(1 for _e, ts in _records if since <= ts <= now)


def prune_before(cutoff: datetime) -> int:
    """Drop records with ts < cutoff. Returns the number removed.

    Writes atomically via a sibling temp file + rename so a crash partway
    through cannot corrupt the log. Data minimization: callers pass the
    start of the current operating-hours window, or ``now`` when closed,
    to limit retention to the minimum needed for counting."""
    _ensure_loaded()
    kept = [(e, ts) for e, ts in _records if ts >= cutoff]
    removed = len(_records) - len(kept)
    if removed == 0:
        return 0
    _records[:] = kept
    if not LOG_FILE.exists() and not kept:
        return removed
    tmp = LOG_FILE.parent / (LOG_FILE.name + ".tmp")
    body = "\n".join(
        json.dumps({"edipi": e, "ts": ts.isoformat()}) for e, ts in kept
    ) + ("\n" if kept else "")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(LOG_FILE)
    return removed
