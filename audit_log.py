"""Persistent audit log of settings activity.

Stores one JSON record per event under the shared data directory
(see ``settings.SETTINGS_DIR``) as ``audit.jsonl``:

    {"ts": "...", "action": "unlock", "authorizers": ["1234567890", "..."]}
    {"ts": "...", "action": "change", "authorizers": [...], "change": "max_drinks: 3 → 5"}
    {"ts": "...", "action": "lock", "authorizers": ["1234567890", "..."]}

Append-only. The audit log is the public record of who unlocked the
settings and what they changed; it is never pruned.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator, Sequence

from settings import SETTINGS_DIR as LOG_DIR

LOG_FILE = LOG_DIR / "audit.jsonl"


def _append(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_unlock(
    edipi1: str, edipi2: str, when: datetime | None = None
) -> datetime:
    when = when or datetime.now(timezone.utc)
    _append(
        {
            "ts": when.isoformat(),
            "action": "unlock",
            "authorizers": [edipi1, edipi2],
        }
    )
    return when


def record_lock(
    authorizers: Sequence[str] | None, when: datetime | None = None
) -> datetime:
    when = when or datetime.now(timezone.utc)
    rec: dict = {"ts": when.isoformat(), "action": "lock"}
    if authorizers:
        rec["authorizers"] = list(authorizers)
    _append(rec)
    return when


def record_change(
    authorizers: Sequence[str] | None,
    change: str,
    when: datetime | None = None,
) -> datetime:
    when = when or datetime.now(timezone.utc)
    _append(
        {
            "ts": when.isoformat(),
            "action": "change",
            "authorizers": list(authorizers) if authorizers else None,
            "change": change,
        }
    )
    return when


def record_export(
    dest_filename: str, when: datetime | None = None
) -> datetime:
    """Record a backup export. No authorizers — export is open to anyone
    so the audit entry just notes when and where the data was written."""
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
    authorizers: Sequence[str],
    source_filename: str,
    when: datetime | None = None,
) -> datetime:
    """Record a backup import. Always carries authorizers since import
    requires the same 2-CAC unlock as other settings changes."""
    when = when or datetime.now(timezone.utc)
    _append(
        {
            "ts": when.isoformat(),
            "action": "import",
            "authorizers": list(authorizers),
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
