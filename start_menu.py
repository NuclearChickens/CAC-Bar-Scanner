"""Create a Windows Start menu shortcut to BarScanner.exe.

PyInstaller --onefile exes don't go through an installer, so the user
has no Start menu entry until they manually pin one. On first launch
the GUI offers two install scopes:

    * current_user — writes a .lnk to %APPDATA%\\...\\Start Menu\\Programs.
      No admin rights required.
    * all_users   — writes a .lnk to %PROGRAMDATA%\\...\\Start Menu\\Programs.
      Requires admin. If the running process isn't elevated we re-launch
      the same exe with ``--install-system-shortcut`` via ShellExecuteEx
      with the ``runas`` verb, which fires a UAC prompt; the elevated
      child writes the shortcut and exits.

Implementation note: the .lnk file is created via PowerShell's
WScript.Shell COM bridge (one liner) instead of binding the IShellLink
COM interface ourselves through ctypes. PowerShell ships with every
Windows release since Vista, so no third-party deps and no fragile
80-line COM dance.
"""
from __future__ import annotations

import os
import subprocess
import sys
from enum import Enum
from pathlib import Path


APP_NAME = "CAC Bar Scanner"
SHORTCUT_FILENAME = f"{APP_NAME}.lnk"
ELEVATED_INSTALL_FLAG = "--install-system-shortcut"


class InstallResult(Enum):
    OK = "ok"
    CANCELLED = "cancelled"   # user clicked No on the UAC prompt
    FAILED = "failed"
    UNSUPPORTED = "unsupported"  # not running on Windows


# ---------------------------------------------------------------- paths

def current_user_start_menu() -> Path:
    """``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs``"""
    appdata = os.environ.get("APPDATA") or str(
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Roaming"
    )
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def all_users_start_menu() -> Path:
    """``%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs``"""
    pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(pd) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def shortcut_exists() -> bool:
    """True if either a per-user or all-users shortcut already exists."""
    return (
        (current_user_start_menu() / SHORTCUT_FILENAME).exists()
        or (all_users_start_menu() / SHORTCUT_FILENAME).exists()
    )


def _exe_path() -> str:
    """Path the shortcut should point at: the running BarScanner.exe.

    For a frozen PyInstaller exe that's ``sys.executable``; for a
    source-tree run we fall back to ``argv[0]`` (shortcut install is
    only offered for frozen builds, but the fallback keeps imports
    safe in dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


# ---------------------------------------------------------------- writers

def _create_shortcut(target: str, lnk_path: Path) -> None:
    """Drop a .lnk file at ``lnk_path`` pointing at ``target``.

    Uses PowerShell + WScript.Shell COM. Single-quoted PowerShell
    strings don't interpret backslashes, so the only character that
    needs escaping is the single quote itself (doubled to ``''``)."""
    target_dir = str(Path(target).parent)

    def esc(s: str) -> str:
        return s.replace("'", "''")

    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{esc(str(lnk_path))}'); "
        f"$s.TargetPath = '{esc(target)}'; "
        f"$s.WorkingDirectory = '{esc(target_dir)}'; "
        f"$s.IconLocation = '{esc(target)},0'; "
        f"$s.Description = '{esc(APP_NAME)}'; "
        "$s.Save();"
    )

    lnk_path.parent.mkdir(parents=True, exist_ok=True)

    creationflags = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW — suppress the PowerShell console flash for
        # users running a windowed (no-console) PyInstaller build.
        creationflags = 0x08000000

    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", script,
        ],
        check=True,
        creationflags=creationflags,
    )


# ---------------------------------------------------------------- elevation

def is_elevated() -> bool:
    """Whether the current process has admin rights."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def install_current_user() -> InstallResult:
    """Write the .lnk into the current user's Start menu. No UAC."""
    if sys.platform != "win32":
        return InstallResult.UNSUPPORTED
    try:
        _create_shortcut(
            _exe_path(), current_user_start_menu() / SHORTCUT_FILENAME
        )
        return InstallResult.OK
    except Exception:
        return InstallResult.FAILED


def install_all_users() -> InstallResult:
    """Write the .lnk into the all-users Start menu.

    Requires admin. If the current process isn't elevated, re-spawn
    ourselves with --install-system-shortcut via ShellExecuteEx(runas);
    Windows shows a UAC prompt and, if accepted, the elevated child
    drops the shortcut and exits. Returns CANCELLED if the user clicks
    No on the UAC prompt."""
    if sys.platform != "win32":
        return InstallResult.UNSUPPORTED

    if is_elevated():
        try:
            _create_shortcut(
                _exe_path(), all_users_start_menu() / SHORTCUT_FILENAME
            )
            return InstallResult.OK
        except Exception:
            return InstallResult.FAILED

    return _spawn_elevated_helper()


def _spawn_elevated_helper() -> InstallResult:
    """ShellExecuteEx(runas) the same exe with --install-system-shortcut,
    wait for it, and translate its exit code into an InstallResult."""
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE     = 0x00008000
    SW_HIDE                 = 0
    ERROR_CANCELLED         = 1223
    INFINITE                = 0xFFFFFFFF

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize",         wintypes.DWORD),
            ("fMask",          wintypes.ULONG),
            ("hwnd",           wintypes.HWND),
            ("lpVerb",         wintypes.LPCWSTR),
            ("lpFile",         wintypes.LPCWSTR),
            ("lpParameters",   wintypes.LPCWSTR),
            ("lpDirectory",    wintypes.LPCWSTR),
            ("nShow",          ctypes.c_int),
            ("hInstApp",       wintypes.HINSTANCE),
            ("lpIDList",       wintypes.LPVOID),
            ("lpClass",        wintypes.LPCWSTR),
            ("hkeyClass",      wintypes.HKEY),
            ("dwHotKey",       wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess",       wintypes.HANDLE),
        ]

    info = SHELLEXECUTEINFOW()
    info.cbSize       = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask        = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb       = "runas"
    info.lpFile       = _exe_path()
    info.lpParameters = ELEVATED_INSTALL_FLAG
    info.nShow        = SW_HIDE

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        # GetLastError == ERROR_CANCELLED when the user clicked No on UAC.
        if ctypes.get_last_error() == ERROR_CANCELLED:
            return InstallResult.CANCELLED
        return InstallResult.FAILED

    if not info.hProcess:
        return InstallResult.FAILED

    try:
        kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
    finally:
        kernel32.CloseHandle(info.hProcess)

    return InstallResult.OK if exit_code.value == 0 else InstallResult.FAILED


def handle_elevated_install_cli() -> bool:
    """If we were spawned with ``--install-system-shortcut``, do the
    all-users install and ``sys.exit`` with 0 on success, 1 on failure.

    Returns False (and does nothing) if the flag isn't present, so
    callers can ``if handle_elevated_install_cli(): return`` at the top
    of main() and otherwise proceed normally."""
    if ELEVATED_INSTALL_FLAG not in sys.argv:
        return False
    try:
        _create_shortcut(_exe_path(), all_users_start_menu() / SHORTCUT_FILENAME)
        sys.exit(0)
    except Exception:
        sys.exit(1)
