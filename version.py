"""App metadata: version, publisher, AppUserModelID, install location.

Single source of truth referenced by:
    * BarScanner.spec (PyInstaller version_info — drives right-click
      Properties → Details on the exe)
    * start_menu (Add/Remove Programs registry entry and the
      Program Files install location)
    * cac_gui (the AppUserModelID set at process startup so Windows
      groups the running app's windows correctly in the taskbar)

Bump APP_VERSION here and rebuild — both the on-disk exe and the
Add/Remove Programs entry pick the new value up automatically.
"""
from __future__ import annotations

import os
from pathlib import Path


APP_NAME        = "CAC Bar Scanner"
APP_VERSION     = "1.0.0"
APP_PUBLISHER   = "Jeremy Evans"
APP_DESCRIPTION = "CAC barcode access control for bars / kiosks"
APP_COPYRIGHT   = "Copyright (c) 2026 Jeremy Evans"
APP_URL         = "https://github.com/NuclearChickens/CAC-Bar-Scanner"

# AppUserModelID — what Windows uses to group taskbar entries and
# route toasts/jumplists. Format is <Company>.<Product>; no spaces.
APP_USER_MODEL_ID = "JeremyEvans.CACBarScanner"

# Internal name (file basename without extension). Must match the
# `name=` value in BarScanner.spec.
EXECUTABLE_BASENAME = "BarScanner"


def install_dir() -> Path:
    """Canonical machine-wide install location: %ProgramFiles%\\CAC Bar Scanner\\."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    return Path(pf) / APP_NAME


def installed_exe() -> Path:
    return install_dir() / f"{EXECUTABLE_BASENAME}.exe"
