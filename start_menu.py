"""One-time admin install / uninstall for CAC Bar Scanner on Windows.

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
    3. Register an entry under
       ``HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\``
       so the app shows up in Settings → Apps → Installed apps, and
       the right-click → Uninstall option on the Start menu entry
       actually works.

All three require admin rights, so the GUI's install dialog
re-launches the same exe with ``--install-for-machine`` via
``ShellExecuteEx`` with the ``runas`` verb — Windows shows a UAC
prompt, and the elevated child performs the install and exits.

Uninstall is the symmetric inverse, triggered by Windows running
``BarScanner.exe --uninstall`` (the UninstallString from the
registry entry). The exe shows a small Tk confirmation dialog
asking whether to also wipe the data folder, then re-elevates and
undoes everything.

Implementation:
    * Shortcuts are written through PowerShell's WScript.Shell COM
      bridge (a few lines) rather than binding IShellLink ourselves.
    * The ACL is set with ``icacls.exe`` using the well-known SID for
      Authenticated Users (``*S-1-5-11``) so the call is robust on
      machines with localized account names.
    * Registry writes use ``winreg`` from the Python stdlib.
    * No third-party Python deps; PowerShell and icacls ship with
      every Windows release since Vista.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from enum import Enum
from pathlib import Path

import settings as settings_mod
import version


APP_NAME = version.APP_NAME
SHORTCUT_FILENAME = f"{APP_NAME}.lnk"

# CLI flags used to re-spawn this exe in elevated contexts.
ELEVATED_INSTALL_FLAG = "--install-for-machine"
UNINSTALL_FLAG = "--uninstall"
PURGE_DATA_FLAG = "--purge-data"

# HKLM key Windows reads for Add/Remove Programs and the Start menu
# right-click → Uninstall action.
UNINSTALL_REGISTRY_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CACBarScanner"
)

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
    """Path to the running BarScanner.exe.

    For a frozen PyInstaller exe that's ``sys.executable``; for a
    source-tree run we fall back to ``argv[0]`` so dev imports stay
    safe even though the install flow isn't offered there."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


# ---------------------------------------------------------------- install state

def is_installed() -> bool:
    """True iff the HKLM uninstall registry entry exists, meaning the
    app has been installed via the elevated install flow at some point.

    Used to decide whether the first-run install dialog should appear
    for the current user — once anyone on the machine installs, the
    dialog disappears for everyone."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REGISTRY_KEY
        ):
            return True
    except OSError:
        return False


def _user_declined_marker() -> Path:
    """Per-user file that, if present, suppresses the install dialog
    for this user only. SETTINGS_DIR is machine-shared so we can't put
    this flag there without also silencing it for everyone else."""
    local = os.environ.get(
        "LOCALAPPDATA", str(Path.home() / "AppData" / "Local")
    )
    return Path(local) / "CACBarScanner" / "install_declined"


def should_prompt_install() -> bool:
    """Whether the first-run install dialog should be shown to this user.

    Suppressed when the machine already has the app installed, when
    the current user has previously declined, or when we're not on a
    frozen Windows build."""
    if sys.platform != "win32":
        return False
    if not getattr(sys, "frozen", False):
        return False
    if is_installed():
        return False
    if _user_declined_marker().exists():
        return False
    return True


def mark_user_declined() -> None:
    """Record that the current user said "Not now" to install."""
    marker = _user_declined_marker()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        # Best-effort; if we can't write the marker the only consequence
        # is the dialog reappears next launch.
        pass


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
    """One-shot install: provision the shared data dir, drop the
    all-users Start menu shortcut, and register an Add/Remove
    Programs entry so Windows knows how to uninstall later. Requires
    admin rights.

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

    return _spawn_elevated(ELEVATED_INSTALL_FLAG)


def uninstall_for_machine(purge_data: bool) -> InstallResult:
    """Inverse of install_for_machine.

    Removes the all-users Start menu shortcut, removes the HKLM
    uninstall registry entry, and (if ``purge_data``) deletes the
    shared data directory. Always requires admin; re-spawns elevated
    if needed."""
    if sys.platform != "win32":
        return InstallResult.UNSUPPORTED

    if is_elevated():
        try:
            _do_machine_uninstall(purge_data)
            return InstallResult.OK
        except Exception:
            return InstallResult.FAILED

    flags = UNINSTALL_FLAG
    if purge_data:
        flags += " " + PURGE_DATA_FLAG
    return _spawn_elevated(flags)


# ---------------------------------------------------------------- the install

def _do_machine_install() -> None:
    """Run the privileged half of the install. Caller must be elevated.

    Steps:
        1. Copy the running exe into %ProgramFiles%\\CAC Bar Scanner\\,
           the canonical Windows install location. The shortcut and the
           registry uninstaller both point at this copy, so the user's
           original download (typically in Downloads) can be safely
           deleted later without breaking the install.
        2. Provision %ProgramData%\\CACBarScanner\\ as the shared data
           directory with an Authenticated Users: Modify ACL.
        3. Drop the all-users Start menu shortcut.
        4. Write the HKLM uninstall registry entry — DisplayName,
           DisplayVersion, Publisher, EstimatedSize, InstallDate,
           DisplayIcon, UninstallString, etc."""
    installed_exe = _install_exe_to_program_files()

    data_dir = settings_mod.SETTINGS_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    _grant_authenticated_users_modify(data_dir)

    _create_shortcut(
        str(installed_exe),
        all_users_start_menu() / SHORTCUT_FILENAME,
    )
    _register_uninstall_entry(installed_exe)


def _install_exe_to_program_files() -> Path:
    """Copy the running exe to its canonical Program Files location.

    Idempotent: if we're already running from the install location
    (re-running install on top of an existing install) the copy is
    skipped."""
    install_dir = version.install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    installed_exe = version.installed_exe()

    source = Path(_exe_path()).resolve()
    if source != installed_exe.resolve():
        shutil.copy2(source, installed_exe)
    return installed_exe


def _do_machine_uninstall(purge_data: bool) -> None:
    """Run the privileged half of the uninstall. Caller must be elevated.

    Best-effort: a failure in any single step shouldn't block the rest,
    otherwise a partial-install state can become unremovable.

    The running exe is the one we're trying to delete (it lives in the
    install folder), so the actual file deletion is deferred to the
    next reboot via MoveFileEx(MOVEFILE_DELAY_UNTIL_REBOOT). That's the
    standard Windows uninstaller pattern (Inno Setup, NSIS, etc. all
    use it for the same reason)."""
    lnk = all_users_start_menu() / SHORTCUT_FILENAME
    if lnk.exists():
        try:
            lnk.unlink()
        except OSError:
            pass

    _remove_uninstall_entry()

    if purge_data:
        try:
            shutil.rmtree(settings_mod.SETTINGS_DIR, ignore_errors=True)
        except OSError:
            pass

    install_dir = version.install_dir()
    if install_dir.exists():
        _schedule_delete_at_reboot(install_dir)


def _schedule_delete_at_reboot(path: Path) -> None:
    """Mark every file under ``path`` (and the directory itself) for
    deletion at next reboot, via MoveFileEx(MOVEFILE_DELAY_UNTIL_REBOOT).

    Walks children deepest-first so empty parent directories can be
    successfully scheduled too (Windows only removes empty dirs this
    way at reboot)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    MOVEFILE_DELAY_UNTIL_REBOOT = 0x4

    MoveFileEx = ctypes.windll.kernel32.MoveFileExW
    MoveFileEx.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    MoveFileEx.restype  = wintypes.BOOL

    def _schedule(p: Path) -> None:
        try:
            MoveFileEx(str(p), None, MOVEFILE_DELAY_UNTIL_REBOOT)
        except Exception:
            pass

    for child in sorted(path.rglob("*"), key=lambda p: -len(p.parts)):
        _schedule(child)
    _schedule(path)


# ---------------------------------------------------------------- registry

def _register_uninstall_entry(installed_exe: Path) -> None:
    """Write the HKLM Uninstall entry that Add/Remove Programs and the
    Start menu's right-click Uninstall both read.

    Includes all the fields a normal Windows installer writes —
    DisplayVersion, EstimatedSize, InstallDate, URLInfoAbout — so the
    app shows up cleanly in Settings → Apps with version, size, and
    install date alongside the publisher and icon."""
    import winreg  # Windows-only stdlib module

    install_dir = str(installed_exe.parent)
    try:
        size_kb = max(1, installed_exe.stat().st_size // 1024)
    except OSError:
        size_kb = 0

    with winreg.CreateKey(
        winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REGISTRY_KEY
    ) as k:
        winreg.SetValueEx(k, "DisplayName",     0, winreg.REG_SZ,    version.APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion",  0, winreg.REG_SZ,    version.APP_VERSION)
        winreg.SetValueEx(k, "Publisher",       0, winreg.REG_SZ,    version.APP_PUBLISHER)
        winreg.SetValueEx(k, "DisplayIcon",     0, winreg.REG_SZ,    f"{installed_exe},0")
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,    f'"{installed_exe}" {UNINSTALL_FLAG}')
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ,    install_dir)
        winreg.SetValueEx(k, "InstallDate",     0, winreg.REG_SZ,    date.today().strftime("%Y%m%d"))
        winreg.SetValueEx(k, "URLInfoAbout",    0, winreg.REG_SZ,    version.APP_URL)
        winreg.SetValueEx(k, "Comments",        0, winreg.REG_SZ,    version.APP_DESCRIPTION)
        winreg.SetValueEx(k, "EstimatedSize",   0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify",        0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair",        0, winreg.REG_DWORD, 1)


def _remove_uninstall_entry() -> None:
    """Delete the HKLM Uninstall entry, if it exists."""
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REGISTRY_KEY)
    except FileNotFoundError:
        pass
    except OSError:
        # Already-gone or permission-denied — best effort.
        pass


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

def _spawn_elevated(params: str) -> InstallResult:
    """ShellExecuteEx(runas) the same exe with ``params``, wait for it,
    and translate its exit code into an InstallResult."""
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
    info.lpParameters = params
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


def handle_uninstall_cli() -> bool:
    """If we were spawned with ``--uninstall``, run the uninstall flow.

    Two-stage entry:
        * If elevated: do the privileged uninstall and exit (this is
          the elevated child re-spawned by ourselves below).
        * Otherwise (this is what Windows' Add/Remove Programs invokes):
          show a small Tk confirmation dialog, then re-spawn elevated
          to do the actual work.

    Returns False if the flag isn't present so callers can proceed to
    the normal startup path."""
    if UNINSTALL_FLAG not in sys.argv:
        return False

    if is_elevated():
        try:
            _do_machine_uninstall(PURGE_DATA_FLAG in sys.argv)
            sys.exit(0)
        except Exception:
            sys.exit(1)

    confirmed, purge = _show_uninstall_dialog()
    if not confirmed:
        sys.exit(0)
    res = uninstall_for_machine(purge)
    sys.exit(0 if res == InstallResult.OK else 1)


def _show_uninstall_dialog() -> tuple[bool, bool]:
    """Small modal Tk dialog. Returns (confirmed, purge_data)."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Uninstall CAC Bar Scanner")
    root.resizable(False, False)

    # Match the window icon to the exe when possible.
    try:
        # Look in PyInstaller's _MEIPASS first, then alongside the exe.
        base = getattr(sys, "_MEIPASS", None) or str(Path(_exe_path()).parent)
        root.iconbitmap(default=str(Path(base) / "icon.ico"))
    except Exception:
        pass

    frame = ttk.Frame(root, padding=24)
    frame.grid()

    ttk.Label(
        frame,
        text="Uninstall CAC Bar Scanner from this PC?",
        font=("TkDefaultFont", 12, "bold"),
    ).grid(row=0, column=0, sticky="w")

    ttk.Label(
        frame,
        text=(
            "This removes the Start menu entry and the\n"
            "Add/Remove Programs listing. BarScanner.exe\n"
            "stays where it is — delete the file yourself if\n"
            "you want it gone."
        ),
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(8, 12))

    purge_var = tk.IntVar(value=0)
    ttk.Checkbutton(
        frame,
        text=(
            "Also delete settings, ban list, and all logs from\n"
            r"C:\ProgramData\CACBarScanner\."
        ),
        variable=purge_var,
    ).grid(row=2, column=0, sticky="w", pady=(0, 16))

    result = {"confirmed": False, "purge": False}

    def on_uninstall() -> None:
        # Capture purge_var's value before destroying the Tk root —
        # IntVar reads after destroy fail with a TclError.
        result["purge"] = bool(purge_var.get())
        result["confirmed"] = True
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    btns = ttk.Frame(frame)
    btns.grid(row=3, column=0, sticky="ew")
    ttk.Button(btns, text="Uninstall", command=on_uninstall).pack(side="left")
    ttk.Button(btns, text="Cancel", command=on_cancel).pack(
        side="left", padx=(8, 0)
    )

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    root.mainloop()

    return result["confirmed"], result["purge"]
