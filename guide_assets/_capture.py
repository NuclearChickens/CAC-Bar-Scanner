"""Drive cac_gui.App through each tab and capture screenshots with grim.

Side-tracks every persistent file location to a temp directory so the
user's real ~/.cac_scanner data is left alone.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Redirect every persistent file BEFORE importing the app modules so the
# module-level path constants pick up the temp dir.
TMP = Path(tempfile.mkdtemp(prefix="cac_guide_"))
os.environ["HOME"] = str(TMP)            # kept for any home-relative lookups
print(f"sandbox: {TMP}")

import settings as settings_mod  # noqa: E402
import scan_log                  # noqa: E402
import audit_log                 # noqa: E402
import reset_log                 # noqa: E402

for mod in (settings_mod, scan_log, audit_log, reset_log):
    mod.LOG_DIR = TMP if mod is not settings_mod else TMP
settings_mod.SETTINGS_DIR = TMP
settings_mod.SETTINGS_FILE = TMP / "settings.json"
scan_log.LOG_FILE = TMP / "scans.jsonl"
audit_log.LOG_FILE = TMP / "audit.jsonl"
reset_log.LOG_FILE = TMP / "resets.jsonl"

import cac_gui  # noqa: E402

OUT = Path(__file__).resolve().parent
OUT.mkdir(exist_ok=True)


# Pre-seed settings + a handful of audit/reset/scan entries so the
# settings-driven tabs (Hours, Limits, Banned, Reset, Logs) have
# realistic content for the screenshots.
def seed():
    s = settings_mod.Settings(
        open_time="16:00",
        close_time="23:30",
        max_drinks=3,
        allowed_categories=("A", "C", "E", "G", "R", "S"),
        allowed_branches=("A", "F", "M", "N", "C", "D"),
        bans=(
            settings_mod.Ban(edipi="9876543210", expires=None),
            settings_mod.Ban(edipi="5551112222", expires="2026-12-31"),
        ),
        tracking_mode=settings_mod.TRACKING_HOURS,
        rolling_hours=24,
    )
    settings_mod.save(s)
    audit_log.record_unlock("1112223333", "4445556666")
    audit_log.record_change(
        ("1112223333", "4445556666"), "max_drinks: 2 → 3"
    )
    audit_log.record_change(
        ("1112223333", "4445556666"),
        "ban added: 9876543210 (permanent)",
    )
    audit_log.record_lock(("1112223333", "4445556666"))
    reset_log.record_reset("1112223333", "4445556666")


class GuideApp(cac_gui.App):
    """The app's natural mode is fullscreen, and the Decoded section
    needs the full 1080-px height to lay out cleanly. Keep fullscreen."""


def hypr_active_window() -> dict:
    return json.loads(
        subprocess.check_output(["hyprctl", "activewindow", "-j"], text=True)
    )


def hypr_window_by_address(addr: str) -> dict | None:
    clients = json.loads(
        subprocess.check_output(["hyprctl", "clients", "-j"], text=True)
    )
    for c in clients:
        if c.get("address") == addr:
            return c
    return None


WINDOW_ADDR = ""


def shoot(root, dest: Path) -> None:
    root.update_idletasks()
    root.update()
    if WINDOW_ADDR:
        subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", f"address:{WINDOW_ADDR}"],
            check=False,
        )
    root.lift()
    root.focus_force()
    root.update_idletasks()
    root.update()
    time.sleep(0.5)
    # Capture the entire eDP-1 monitor — the app is fullscreen, so this
    # gives us a clean 1920x1080 image with no other windows visible.
    subprocess.run(["grim", "-o", "eDP-1", str(dest)], check=True)
    print(f"  -> {dest.name}")


def main():
    seed()
    global WINDOW_ADDR
    app = GuideApp()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)
    try:
        win = hypr_active_window()
        WINDOW_ADDR = win.get("address", "")
        print(f"window addr: {WINDOW_ADDR}  fullscreen={win.get('fullscreen')}")
        if WINDOW_ADDR:
            # Force fullscreen mode 0 (true fullscreen, covers everything)
            # so the captured image has no other windows or panels.
            subprocess.run(
                ["hyprctl", "dispatch", "fullscreenstate",
                 f"2 1,address:{WINDOW_ADDR}"],
                check=False,
            )
            time.sleep(0.5)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"hypr setup failed: {e}")

    def go():
        # ---------- 01 Scanner — idle
        app.notebook.select(0)
        app._reset_banner()
        for var in app._values.values():
            var.set(app.PLACEHOLDER)
        app.input_var.set("")
        app.update()
        shoot(app, OUT / "01_scanner_idle.png")

        # ---------- 02 Scanner — ALLOWED
        app._values["edipi"].set("1234567890")
        app._values["category"].set("A — Active duty member")
        app._values["branch"].set("F — USAF (Air Force)")
        app._values["count"].set(f"1 / {app.settings.max_drinks}")
        app._set_banner(
            cac_gui.GREEN,
            "ALLOWED — 1st drink",
            "Active duty member  •  USAF (Air Force)",
        )
        shoot(app, OUT / "02_scanner_allowed.png")

        # ---------- 03 Scanner — DENIED (limit reached)
        app._values["count"].set(f"3 / {app.settings.max_drinks}")
        app._set_banner(
            cac_gui.RED,
            "DENIED",
            "You've had 3 drinks today (limit 3)",
        )
        shoot(app, OUT / "03_scanner_denied.png")

        # ---------- 04 Hours tab (locked banner is the headline here)
        app._reset_banner()
        for var in app._values.values():
            var.set(app.PLACEHOLDER)
        app.notebook.select(1)
        shoot(app, OUT / "04_hours_locked.png")

        # Now unlock everything so the form-field tabs show their content.
        app._settings_unlocked = True
        app._unlock_authorizers = ("1112223333", "4445556666")
        app._pre_edit_settings = app.settings
        app._apply_lock_state()

        app.notebook.select(1)
        shoot(app, OUT / "05_hours_unlocked.png")

        app.notebook.select(2)
        shoot(app, OUT / "06_limits.png")

        app.notebook.select(3)
        shoot(app, OUT / "07_roster.png")

        app.notebook.select(4)
        shoot(app, OUT / "08_banned.png")

        app.notebook.select(5)
        shoot(app, OUT / "09_reset.png")

        app.notebook.select(6)
        shoot(app, OUT / "10_logs.png")

        app.after(120, app.destroy)

    app.after(800, go)
    app.mainloop()


if __name__ == "__main__":
    main()
