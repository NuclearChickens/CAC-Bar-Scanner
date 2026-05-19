"""Persistent audit log of settings activity.

Stores one JSON record per event under the shared data directory
(see ``settings.SETTINGS_DIR``) as ``audit.jsonl``:

    {"ts": "...", "action": "unlock"}
    {"ts": "...", "action": "change", "change": "max_drinks: 3 → 5"}
    {"ts": "...", "action": "lock"}

Append-only. The audit log is the public record of who unlocked the
settings and what they changed; it is never pruned.

Legacy entries written before password auth replaced two-CAC integrity
also carry an ``authorizers`` list of EDIPIs; the reader preserves
those fields untouched so historical records still display correctly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator

from settings import SETTINGS_DIR as LOG_DIR

LOG_FILE = LOG_DIR / "audit.jsonl"


def _append(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_unlock(when: datetime | None = None) -> datetime:
    when = when or datetime.now(timezone.utc)
    _append({"ts": when.isoformat(), "action": "unlock"})
    return when


def record_lock(when: datetime | None = None) -> datetime:
    when = when or datetime.now(timezone.utc)
    _append({"ts": when.isoformat(), "action": "lock"})
    return when


def record_change(change: str, when: datetime | None = None) -> datetime:
    when = when or datetime.now(timezone.utc)
    _append(
        {"ts": when.isoformat(), "action": "change", "change": change}
    )
    return when


def record_export(
    dest_filename: str, when: datetime | None = None
) -> datetime:
    """Record a backup export. Export is open to anyone, so the entry
    just notes when and where the data was written."""
    when = when or datetime.now(timezone.utc)
    _append(
        {
            "ts": when.isoformat(),
            "action": "export",
            "dest": dest_filename,
        }
    )
    return when


def record_import(
    source_filename: str,
    when: datetime | None = None,
) -> datetime:
    """Record a backup import. Gated by the same unlock as other settings
    changes, but the password itself isn't logged."""
    when = when or datetime.now(timezone.utc)
    _append(
        {
            "ts": when.isoformat(),
            "action": "import",
            "source": source_filename,
        }
    )
    return when


def iter_records() -> Iterator[dict]:
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def list_records() -> list[dict]:
    items = list(iter_records())
    items.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return items
