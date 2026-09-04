"""Regenerate the screenshots used by GUIDE.md / GUIDE.pdf.

Drives the real GUI under a virtual X display (see
build_guide_images.sh) and grabs one PNG per screen state the manual
refers to. Nothing here touches the real data folder: HOME is pointed
at a throwaway directory by the wrapper script so the app's
``~/.cac_scanner`` lands there, and the verdict sounds are muted.

Usage (normally via build_guide_images.sh):

    DISPLAY=:99 HOME=/tmp/somewhere python3 guide_images/capture.py OUT_DIR
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path, PureWindowsPath

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

import audit_log  # noqa: E402
import cac_gui  # noqa: E402
import daily_log  # noqa: E402
import reset_log  # noqa: E402
import settings as settings_mod  # noqa: E402
import sound  # noqa: E402
import start_menu  # noqa: E402

# Never touch the real audio device from the capture run.
sound._resolved = True
sound._posix_cmd = None

DISPLAY = os.environ["DISPLAY"]


def edipi_barcode(edipi: int, cat: str = "A", branch: str = "A") -> str:
    """Build a syntactically valid 18-char barcode for a given EDIPI."""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
    n, out = edipi, ""
    while n:
        out = digits[n % 32] + out
        n //= 32
    return "1XZ4PQ7B" + out.rjust(7, "0") + cat + branch + "K"


def settle(app, ms=250):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def grab(app, name: str, extra_settle=300):
    settle(app, extra_settle)
    img = ImageGrab.grab(xdisplay=DISPLAY)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    if (w, h) != img.size:
        img = img.crop((max(0, x - 1), max(0, y - 1), x + w + 1, y + h + 1))
    img.save(OUT / f"{name}.png")
    print("saved", name, img.size)


def center_toplevel(app, dlg):
    app.update_idletasks()
    dlg.update_idletasks()
    x = app.winfo_rootx() + (app.winfo_width() - dlg.winfo_width()) // 2
    y = app.winfo_rooty() + (app.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def find_toplevel(app):
    import tkinter as tk
    for child in app.winfo_children():
        if isinstance(child, tk.Toplevel):
            return child
    return None


def unlock(app):
    """Same effect as typing the correct admin password."""
    app._settings_unlocked = True
    app._pre_edit_settings = app.settings
    audit_log.record_unlock()
    app._apply_lock_state()
    app._schedule_auto_lock()


def capture_main_app() -> None:
    # Bar open right now, so the session line shows a realistic window.
    settings_mod.save(
        settings_mod.Settings(open_time="09:00", close_time="02:00", max_drinks=3)
    )
    app = cac_gui.App()
    settle(app, 800)

    # Scanner tab -------------------------------------------------------
    grab(app, "scanner-ready")

    app._open_install_dialog()
    dlg = find_toplevel(app)
    center_toplevel(app, dlg)
    grab(app, "install-dialog", extra_settle=800)
    dlg.destroy()
    settle(app, 300)

    code = edipi_barcode(1234567890)
    app._process(code)
    app._process(code)
    app._refresh_session_label()
    grab(app, "scanner-allowed")

    app._process(code)
    app._process(code)
    app._refresh_session_label()
    grab(app, "scanner-denied")

    app._process("ABC")
    grab(app, "scanner-invalid")
    app._clear()

    # Locked Hours tab + unlock dialog -----------------------------------
    app.notebook.select(1)
    grab(app, "hours-locked")

    app._open_unlock_dialog()
    dlg = find_toplevel(app)
    center_toplevel(app, dlg)
    import tkinter.ttk as ttk
    for child in dlg.winfo_children():
        if isinstance(child, ttk.Entry):
            child.insert(0, "secret")
    grab(app, "unlock-dialog")
    dlg.destroy()
    unlock(app)

    # Hours ---------------------------------------------------------------
    grab(app, "hours-operating")
    app.tracking_mode_var.set(settings_mod.TRACKING_ROLLING)
    app._on_tracking_mode_changed()
    grab(app, "hours-rolling")
    app.tracking_mode_var.set(settings_mod.TRACKING_HOURS)
    app._on_tracking_mode_changed()

    # Limits / Roster -----------------------------------------------------
    app.notebook.select(2)
    grab(app, "limits")
    app.notebook.select(3)
    grab(app, "roster")

    # Banned --------------------------------------------------------------
    app.notebook.select(4)
    for edipi, expires in (("1098765432", ""), ("1122334455", "20261231")):
        app.ban_edipi_var.set(edipi)
        app.ban_expires_var.set(expires)
        app._add_ban()
    app.ban_edipi_var.set("1234567890")
    app.ban_expires_var.set("")
    grab(app, "banned")
    app.ban_edipi_var.set("")

    # Reset ---------------------------------------------------------------
    app.notebook.select(5)
    reset_log.record_reset()
    app._refresh_reset_log()
    grab(app, "reset")

    # Lock (writes the CHANGE lines the Logs shot shows) ------------------
    app.max_var.set(4)
    app._lock_settings()

    app.destroy()


def capture_backup_and_logs_tabs() -> None:
    """The Backup and Logs tabs as the Windows exe shows them: Windows
    data paths and the PC-install box, which the app hides on
    non-Windows runs. No scans happen in this pass, so the Windows-style
    daily-log path is never written to."""
    real_dir = settings_mod.SETTINGS_DIR
    real_daily = daily_log.DAILY_DIR
    real_platform = sys.platform
    settings_mod.SETTINGS_DIR = PureWindowsPath(r"C:\ProgramData\CACBarScanner")
    daily_log.DAILY_DIR = PureWindowsPath(r"C:\ProgramData\CACBarScanner\daily_logs")
    start_menu.all_users_start_menu = lambda: PureWindowsPath(
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
    )
    start_menu.is_installed = lambda: True
    start_menu.shortcut_exists = lambda: True
    sys.platform = "win32"
    sys.frozen = True
    try:
        app = cac_gui.App()
    finally:
        sys.platform = real_platform
        del sys.frozen
        settings_mod.SETTINGS_DIR = real_dir
        daily_log.DAILY_DIR = real_daily
    settle(app, 800)
    app.notebook.select(6)
    app._refresh_logs()
    grab(app, "logs", extra_settle=400)
    app.notebook.select(7)
    grab(app, "backup", extra_settle=400)
    app.destroy()


def capture_uninstall_dialog() -> None:
    """The uninstall confirmation runs its own Tk root + mainloop; swap
    the mainloop for a short update loop that grabs the window."""
    import tkinter as tk

    def fake_mainloop(self, n=0):
        end = time.time() + 1.2
        while time.time() < end:
            self.update()
            time.sleep(0.02)
        img = ImageGrab.grab(xdisplay=DISPLAY)
        x, y = self.winfo_rootx(), self.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        img = img.crop((x - 12, y - 36, x + w + 12, y + h + 12)).convert("RGB")
        # Whiten the bare root-window background around the frame.
        ImageDraw.floodfill(img, (0, 0), (255, 255, 255), thresh=30)
        ImageDraw.floodfill(img, (img.width - 1, img.height - 1), (255, 255, 255), thresh=30)
        img.save(OUT / "uninstall-dialog.png")
        print("saved uninstall-dialog", img.size)
        self.destroy()

    tk.Tk.mainloop = fake_mainloop
    start_menu._show_uninstall_dialog()


def main() -> None:
    capture_main_app()
    capture_backup_and_logs_tabs()
    capture_uninstall_dialog()


if __name__ == "__main__":
    main()
