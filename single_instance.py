"""Make sure only one copy of the app runs per PC.

Why this matters: ``scan_log`` keeps the scan file mirrored in memory
and rewrites the file from that mirror when it prunes. Two running
copies would each hold their own mirror, and whichever pruned last
would silently drop the other's scans. The daily-log tally and the
drinks-served counter would drift the same way. So a second launch
must not start a second app — it should just surface the one that's
already open.

Windows: a named mutex in the ``Global\\`` namespace, so it covers every
logged-in Windows account on the PC (they all share the same data
folder). If the mutex already exists the caller brings the existing
window to the front via ``FindWindowW`` / ``SetForegroundWindow``.

Linux / macOS (source-tree runs): an ``flock``-ed lock file in the
data directory. There's no portable way to focus the other window, so
the fallback is a short message.

The handle / file descriptor is held in a module global for the life
of the process; the OS releases it on exit, including on a crash.
"""
from __future__ import annotations

import sys
from pathlib import Path

import version
from settings import SETTINGS_DIR

# Mutex name: Global\\ makes it PC-wide rather than per-login-session.
MUTEX_NAME = f"Global\\{version.APP_USER_MODEL_ID}.SingleInstance"
LOCK_FILE = SETTINGS_DIR / "instance.lock"

_ERROR_ALREADY_EXISTS = 183
_ERROR_ACCESS_DENIED = 5
_SW_RESTORE = 9

_mutex_handle = None
_lock_fd = None


def acquire() -> bool:
    """Claim the single-instance lock. True if this process is now the
    only instance; False if another copy already holds it."""
    if sys.platform == "win32":
        return _acquire_windows()
    return _acquire_posix()


def _acquire_windows() -> bool:
    global _mutex_handle
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()
    if not handle:
        # ERROR_ACCESS_DENIED means the mutex exists but was created by a
        # different account whose ACL we can't open — still "already
        # running". Anything else is unexpected; don't block startup.
        return err != _ERROR_ACCESS_DENIED
    if err == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def _acquire_posix() -> bool:
    global _lock_fd
    import fcntl
    import os

    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        # Can't create the lock file — better to run than to refuse.
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _lock_fd = fd
    return True


def bring_existing_to_front(window_title: str) -> bool:
    """Try to surface the running copy's main window. Returns True if a
    window was found and asked to come forward."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)

    hwnd = user32.FindWindowW(None, window_title)
    if not hwnd:
        # Running under another Windows account (different desktop), or
        # still starting up — nothing we can focus from here.
        return False
    user32.ShowWindow(hwnd, _SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def show_already_running_message() -> None:
    """Modal notice for the case where the other copy can't be focused —
    typically because it's open under a different Windows account."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            f"{version.APP_NAME} is already running",
            (
                f"{version.APP_NAME} is already open on this PC, possibly "
                "under another Windows account.\n\n"
                "Only one copy can run at a time so that drink counts stay "
                "correct. Switch to the window that is already open, or close "
                "it there and try again."
            ),
        )
        root.destroy()
    except Exception:
        pass
