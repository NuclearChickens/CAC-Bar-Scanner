"""One-time admin install for CAC Bar Scanner on Windows.

A single-file PyInstaller exe has no installer step, so the kiosk
needs a one-time bootstrap to:

    1. Provision the shared data directory at
       ``C:\\ProgramData\\CACBarScanner\\`` with an explicit
       Authenticated Users: Modify ACL so every operator on the
       machine can read and write the settings, ban list, and logs.
    2. Drop a Start menu shortcut in the all-users location at
       ``C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\``
       so the app appears for every user when they tap the Windows
       key and start typing "Bar".

Both actions require admin rights, so the GUI's install dialog
re-launches the same exe with ``--install-for-machine`` via
``ShellExecuteEx`` with the ``runas`` verb — Windows shows a UAC
prompt, and the elevated child performs the install and exits.

Implementation:
    * Shortcuts are written through PowerShell's WScript.Shell COM
      bridge (a few lines) rather than binding IShellLink ourselves.
    * The ACL is set with ``icacls.exe`` using the well-known SID for
      Authenticated Users (``*S-1-5-11``) so the call is robust on
      machines with localized account names.
    * No third-party Python deps; PowerShell and icacls ship with
      every Windows release since Vista.
"""
from __future__ import annotations

import os
import subprocess
import sys
from enum import Enum
from pathlib import Path

import settings as settings_mod


APP_NAME = "CAC Bar Scanner"
SHORTCUT_FILENAME = f"{APP_NAME}.lnk"
ELEVATED_INSTALL_FLAG = "--install-for-machine"

# Well-known SID for "Authenticated Users". Using the SID rather than
# the display name keeps the icacls call working on Windows installs
# with a non-English UI.
AUTHENTICATED_USERS_SID = "*S-1-5-11"

# CREATE_NO_WINDOW — suppress the console flash from PowerShell /
# icacls subprocesses when running a windowed PyInstaller build.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class InstallResult(Enum):
    OK = "ok"
    CANCELLED = "cancelled"     # user clicked No on UAC
    FAILED = "failed"
    UNSUPPORTED = "unsupported"  # not running on Windows


# ---------------------------------------------------------------- paths

def all_users_start_menu() -> Path:
    """``%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs``"""
    pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(pd) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def shortcut_exists() -> bool:
    """True if the all-users shortcut already exists."""
    return (all_users_start_menu() / SHORTCUT_FILENAME).exists()


def _exe_path() -> str:
    """Path the shortcut should point at: the running BarScanner.exe.

    For a frozen PyInstaller exe that's ``sys.executable``; for a
    source-tree run we fall back to ``argv[0]`` so dev imports stay
    safe even though the install flow isn't offered there."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


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


def install_for_machine() -> InstallResult:
    """One-shot install: provision the shared data dir + drop the
    all-users Start menu shortcut. Requires admin rights.

    If the current process isn't already elevated, re-spawn the same
    exe with ``--install-for-machine`` via ShellExecuteEx(runas);
    Windows shows a UAC prompt and, if accepted, the elevated child
    does the work and exits. Returns CANCELLED if the user clicks No
    on the UAC prompt."""
    if sys.platform != "win32":
        return InstallResult.UNSUPPORTED

    if is_elevated():
        try:
            _do_machine_install()
            return InstallResult.OK
        except Exception:
            return InstallResult.FAILED

    return _spawn_elevated_helper()


# ---------------------------------------------------------------- the install

def _do_machine_install() -> None:
    """Run the privileged half of the install. Caller must be elevated."""
    data_dir = settings_mod.SETTINGS_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    _grant_authenticated_users_modify(data_dir)
    _create_shortcut(
        _exe_path(), all_users_start_menu() / SHORTCUT_FILENAME
    )


def _grant_authenticated_users_modify(folder: Path) -> None:
    """Grant ``Authenticated Users`` Modify access on ``folder`` with
    object + container inheritance so every file beneath it (existing
    and future) is read/writable by any logged-in user on the PC.

    ``/grant:r`` replaces any existing grant for the principal so
    re-running the install is idempotent. ``/T`` recurses through
    existing children, which matters when an earlier non-admin
    launch already populated the folder."""
    subprocess.run(
        [
            "icacls", str(folder),
            "/grant:r", f"{AUTHENTICATED_USERS_SID}:(OI)(CI)M",
            "/T",
            "/C",  # keep going on per-file errors
            "/Q",  # quiet
        ],
        check=True,
        creationflags=_NO_WINDOW,
    )


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

    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", script,
        ],
        check=True,
        creationflags=_NO_WINDOW,
    )


# ---------------------------------------------------------------- runas helper

def _spawn_elevated_helper() -> InstallResult:
    """ShellExecuteEx(runas) the same exe with --install-for-machine,
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

    shell32  = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
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
    """If we were spawned with ``--install-for-machine``, run the
    privileged install and ``sys.exit`` (0 on success, 1 on failure).

    Returns False if the flag isn't present so callers can do
    ``if handle_elevated_install_cli(): return`` at the top of main()
    and otherwise proceed to bring up the GUI."""
    if ELEVATED_INSTALL_FLAG not in sys.argv:
        return False
    try:
        _do_machine_install()
        sys.exit(0)
    except Exception:
        sys.exit(1)
