# CAC-Bar-Scanner

Tkinter GUI that reads CAC Code 39 barcodes from a USB scanner, decodes them,
and enforces per-user/per-day access policy (hours, daily limits, roster,
banned list). Designed for kiosk-style use on Windows; runs the same on
Linux/macOS from source.

The repo ships both the source and a prebuilt `BarScanner.exe` so you can
double-click it on a Windows machine without installing Python.

## Run the prebuilt binary

Copy `BarScanner.exe` to a Windows machine and double-click. No install
needed; PyInstaller bundles the Python runtime.

## Run from source

Requires Python 3.10+ with Tk available (most distros ship it; on Debian/
Ubuntu install `python3-tk`).

```bash
python3 cac_gui.py
```

There are no third-party deps.

Keys:
- `F11` — toggle fullscreen
- `Esc` — exit fullscreen

## Build the `.exe` yourself

On a Windows machine, install Python 3.12 from
[python.org](https://www.python.org/downloads/) — tick **Add python.exe to
PATH** in the installer. Open a fresh Command Prompt (so it picks up the
new PATH), `cd` into a clone of this repo, then run
`pip install pyinstaller` followed by
`pyinstaller --onefile --windowed --name BarScanner --clean --noconfirm cac_gui.py`.
The finished binary lands at `dist\BarScanner.exe` — copy it anywhere and
double-click. No virtualenv needed; the GUI has no third-party deps, so
PyInstaller is the only pip install required. Tk ships with the standard
python.org installer, so there's nothing extra to add for the GUI itself.

## Source layout

| File             | Role                                                  |
| ---------------- | ----------------------------------------------------- |
| `cac_gui.py`     | Tk application — Notebook with Scanner / Hours / Limits / Roster / Banned tabs |
| `cac_decoder.py` | Parses an 18-char CAC Code 39 barcode into fields     |
| `settings.py`    | Persisted config (hours, limits, roster, banned)      |
| `scan_log.py`    | Per-scan record + count-since-date queries            |
| `audit_log.py`   | Append-only audit trail of admin actions              |
| `reset_log.py`   | Periodic log rollover                                 |
| `backup.py`      | Settings + log backup/restore                         |
| `BarScanner.spec`| PyInstaller spec (single-file, windowed)              |
