"""Backup / restore for the entire ``~/.cac_scanner/`` data directory.

Exports produce a single .zip containing ``settings.json`` and the three
log files (``scans.jsonl``, ``audit.jsonl``, ``resets.jsonl``), plus a
``backup_manifest.json`` with format version and timestamp.

Imports validate the zip thoroughly (every JSON line parses, settings
round-trip through ``settings.from_dict``) before touching live data,
then atomically swap files into place so a failure mid-import leaves
the local install untouched.

The IMPORT event is appended to the imported ``audit.jsonl`` *before*
the file is written locally — that way the imported machine's history
is preserved AND the import action itself appears in the new log.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import settings as settings_mod
from settings import SETTINGS_DIR, Settings

BACKUP_FILES: tuple[str, ...] = (
    "settings.json",
    "scans.jsonl",
    "audit.jsonl",
    "resets.jsonl",
)
MANIFEST_NAME = "backup_manifest.json"
FORMAT_VERSION = 1


class BackupError(Exception):
    """Raised when a backup zip is missing required content or is corrupt."""


# ---------------------------------------------------------------- export


def export_backup(dest: Path) -> None:
    """Write a zip of all files in ``SETTINGS_DIR`` plus a manifest to
    ``dest``. Missing log files are simply omitted; ``settings.json`` is
    always included (defaults are written if no file exists yet).

    The zip is staged in a sibling temp file and atomically renamed so a
    crash mid-write doesn't leave a half-finished .zip at ``dest``."""
    dest = Path(dest)
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }

    fd, tmppath_str = tempfile.mkstemp(suffix=".zip", dir=str(dest.parent))
    os.close(fd)
    tmppath = Path(tmppath_str)
    try:
        with zipfile.ZipFile(tmppath, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in BACKUP_FILES:
                src = SETTINGS_DIR / name
                if src.exists():
                    zf.write(src, arcname=name)
                    manifest["files"].append(name)
                elif name == "settings.json":
                    payload = json.dumps(
                        dataclasses.asdict(settings_mod.load()), indent=2
                    )
                    zf.writestr(name, payload)
                    manifest["files"].append(name)
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        os.replace(tmppath, dest)
    except Exception:
        try:
            tmppath.unlink()
        except FileNotFoundError:
            pass
        raise


# ---------------------------------------------------------------- import


def import_backup(src: Path) -> Settings:
    """Replace local files from a backup zip. Returns the new Settings
    so the caller can refresh in-memory state.

    Validation order: zip parseable → no path traversal → settings.json
    present and valid JSON → settings.from_dict succeeds → every line in
    each .jsonl parses. Any failure raises BackupError before any local
    file is touched."""
    src = Path(src)
    if not src.exists():
        raise BackupError(f"Backup file not found: {src}")
    if not zipfile.is_zipfile(src):
        raise BackupError(f"Not a valid zip file: {src}")

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        try:
            with zipfile.ZipFile(src) as zf:
                # Reject zips with subdirs, absolute paths, or .. traversal
                for name in zf.namelist():
                    if name != Path(name).name or name.startswith((".", "/")):
                        raise BackupError(
                            f"Backup contains unexpected path: {name!r}"
                        )
                zf.extractall(tmpdir)
        except zipfile.BadZipFile as e:
            raise BackupError(f"Corrupt zip: {e}") from None

        settings_path = tmpdir / "settings.json"
        if not settings_path.exists():
            raise BackupError("Backup is missing settings.json")
        try:
            settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise BackupError(f"settings.json is not valid JSON: {e}") from None
        try:
            new_settings = settings_mod.from_dict(settings_data)
        except (TypeError, ValueError) as e:
            raise BackupError(f"settings.json failed validation: {e}") from None

        for name in ("scans.jsonl", "audit.jsonl", "resets.jsonl"):
            p = tmpdir / name
            if not p.exists():
                continue
            try:
                with p.open(encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            json.loads(line)
                        except json.JSONDecodeError as e:
                            raise BackupError(
                                f"{name} line {lineno} is not valid JSON: {e}"
                            ) from None
            except OSError as e:
                raise BackupError(f"Cannot read {name}: {e}") from None

        # Append the IMPORT record to the imported audit.jsonl so the
        # action survives in the new on-disk log. Must happen before the
        # swap below so the IMPORT line lands in the file we then promote.
        audit_src = tmpdir / "audit.jsonl"
        import_record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "import",
            "source": src.name,
        }
        with audit_src.open("a", encoding="utf-8") as f:
            f.write(json.dumps(import_record, ensure_ascii=False) + "\n")

        # All validated — swap files into place. Stage each via a
        # ``*.import.tmp`` sibling and ``os.replace`` so each individual
        # promotion is atomic; SETTINGS_DIR may be on a different
        # filesystem from the system tempdir so we can't move directly.
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        for name in BACKUP_FILES:
            src_file = tmpdir / name
            final = SETTINGS_DIR / name
            if src_file.exists():
                staging = SETTINGS_DIR / (name + ".import.tmp")
                shutil.copy2(src_file, staging)
                os.replace(staging, final)

        return new_settings
