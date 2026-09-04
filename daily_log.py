"""One CSV per calendar day with every scan — allowed, denied, and
invalid — kept permanently for the operator's records.

Layout under the shared data directory (see ``settings.SETTINGS_DIR``)::

    daily_logs/
        2026/
            09/
                2026-09-04.csv
                2026-09-05.csv

Each row records the local time, the card's EDIPI / category / branch,
the verdict, the detail shown on the banner, the drink count the
banner showed, and a running "scans today for this card" number that
counts every scan of that EDIPI that day, denied ones included.

The files are meant to be looked at, not edited: after every append
the file is flipped back to read-only (the Windows read-only attribute
/ POSIX 0444), so Excel or Notepad can open it but can't save over
it. The attribute is cleared just long enough to append the next row.

Unlike ``scans.jsonl`` — which is pruned to the current counting window
for data minimisation — these files are never pruned by the app. They
are the one place the app keeps a lasting per-scan record.
"""
from __future__ import annotations

import csv
import os
import stat
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from settings import SETTINGS_DIR

DAILY_DIR = SETTINGS_DIR / "daily_logs"

COLUMNS = (
    "Time",
    "EDIPI",
    "Category",
    "Branch",
    "Verdict",
    "Detail",
    "Drinks",
    "Scans today (this card)",
)

VERDICT_ALLOWED = "ALLOWED"
VERDICT_DENIED = "DENIED"
VERDICT_INVALID = "INVALID"

_READ_ONLY = stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH
_WRITABLE = _READ_ONLY | stat.S_IWRITE

# Per-EDIPI scan tally for the day currently being written, rebuilt
# from the file on first use and whenever the calendar day changes.
_tally_day: date | None = None
_tally: dict[str, int] = {}


def file_for(day: date) -> Path:
    """``daily_logs/YYYY/MM/YYYY-MM-DD.csv`` for ``day``."""
    return DAILY_DIR / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.csv"


def today_file() -> Path:
    return file_for(date.today())


def _set_read_only(path: Path, read_only: bool) -> None:
    try:
        os.chmod(path, _READ_ONLY if read_only else _WRITABLE)
    except OSError:
        # Best effort — a filesystem that ignores the mode (some network
        # shares) still gets the log, just not the read-only flag.
        pass


def _load_tally(day: date) -> None:
    """Rebuild the per-card tally for ``day`` from its file, if any."""
    global _tally_day, _tally
    _tally = {}
    _tally_day = day
    path = file_for(day)
    if not path.exists():
        return
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                edipi = (row.get("EDIPI") or "").strip()
                if edipi:
                    _tally[edipi] = _tally.get(edipi, 0) + 1
    except (OSError, csv.Error):
        # A damaged file shouldn't stop today's logging; the tally just
        # restarts from zero for this run.
        pass


def record(
    verdict: str,
    edipi: str,
    category: str,
    branch: str,
    detail: str,
    drinks: str,
    when: datetime | None = None,
) -> int | None:
    """Append one row to today's file and return the card's running
    scan number for the day (None for rows without an EDIPI).

    Raises ``OSError`` if the row could not be written; callers decide
    how loudly to report that — a scan must never fail because the
    daily log did."""
    when = when or datetime.now().astimezone()
    day = when.date()
    if _tally_day != day:
        _load_tally(day)

    scan_no: int | None = None
    if edipi:
        scan_no = _tally.get(edipi, 0) + 1

    path = file_for(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    if not is_new:
        _set_read_only(path, False)
    try:
        # utf-8-sig: the BOM makes Excel open the file as UTF-8 instead of
        # guessing a legacy code page.
        with path.open("a", encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(COLUMNS)
            writer.writerow(
                [
                    f"{when:%Y-%m-%d %H:%M:%S}",
                    edipi,
                    category,
                    branch,
                    verdict,
                    detail,
                    drinks,
                    "" if scan_no is None else scan_no,
                ]
            )
            f.flush()
            os.fsync(f.fileno())
    finally:
        _set_read_only(path, True)

    if edipi:
        _tally[edipi] = scan_no  # type: ignore[assignment]
    return scan_no


def open_folder(path: Path | None = None) -> None:
    """Open ``path`` (default: the daily-logs root) in the system file
    browser. Creates the folder first so the button works on a fresh
    install before any scan has been logged."""
    target = path or DAILY_DIR
    if target.suffix == "":
        target.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
