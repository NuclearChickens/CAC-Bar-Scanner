# CAC-Bar-Scanner

Tkinter GUI that reads CAC Code 39 barcodes from a USB scanner, decodes them,
and enforces per-user/per-day access policy (hours, daily limits, roster,
banned list). Every scan is also written to a read-only per-day CSV log. Designed for kiosk-style use on Windows; runs the same on
Linux/macOS from source.

The repo ships both the source and a prebuilt `BarScanner.exe` so you can
double-click it on a Windows machine without installing Python.

<p align="center">
  <a href="GUIDE.md">
    <img src="https://img.shields.io/badge/%F0%9F%93%96%20%20READ%20THE%20USER%20GUIDE-1f6d63?style=for-the-badge&labelColor=0e3a35" alt="Read the User Guide" height="60"/>
  </a>
  &nbsp;
  <a href="https://github.com/NuclearChickens/CAC-Bar-Scanner/raw/main/GUIDE.pdf">
    <img src="https://img.shields.io/badge/%F0%9F%93%84%20%20PRINTABLE%20PDF-d4af37?style=for-the-badge&labelColor=7a5d10" alt="Download printable PDF" height="60"/>
  </a>
</p>

## Download

**[⬇ Download BarScanner.exe](https://github.com/NuclearChickens/CAC-Bar-Scanner/raw/main/BarScanner.exe)**
&nbsp;·&nbsp; ~11 MB &nbsp;·&nbsp; Windows 10/11

Double-click the downloaded file. The first time, Windows may show
**"Windows protected your PC"** (the binary isn't code-signed) — click
**More info** → **Run anyway**. On first launch the app offers to install
for the whole PC: click **Install** and approve the UAC prompt, and it
will:

- Copy `BarScanner.exe` to `C:\Program Files\CAC Bar Scanner\`
- Add a Start menu shortcut for every user
- Register itself in **Settings → Apps** so it can be uninstalled cleanly
- Create a shared data folder at `C:\ProgramData\CACBarScanner\` so every
  operator on the PC sees the same configuration and scan history

After install the Downloads copy can be deleted — Start menu / taskbar
launches use the Program Files copy.

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
`pyinstaller --clean --noconfirm BarScanner.spec`.
The finished binary lands at `dist\BarScanner.exe` with the bottle-and-CAC
icon baked in — copy it anywhere and double-click. No virtualenv needed;
the GUI has no third-party deps, so PyInstaller is the only pip install
required. Tk ships with the standard python.org installer, so there's
nothing extra to add for the GUI itself.

### Regenerating the verdict sounds

`sounds/allowed.wav` (bell) and `sounds/denied.wav` (buzzer) are
synthesized by `make_sounds.py` using nothing but `wave` and `math`, so
there's no audio toolchain to install. Edit the parameters at the top of
each function, run `python3 make_sounds.py`, and commit the regenerated
files. On Windows playback uses stdlib `winsound`; on Linux/macOS it
shells out to whichever of `paplay`/`pw-play`/`aplay`/`afplay` exists.
Missing files, missing players, and machines with no sound card all
degrade to a silent scanner rather than an error.

### Regenerating the user manual

`GUIDE.md` is the source. `./build_guide_pdf.sh` renders it to
`GUIDE.pdf` through headless Chromium (needs `python-markdown`,
`chromium`, and an emoji font). The screenshots in `guide_images/` come
from `./build_guide_images.sh`, which runs the real GUI under a virtual
X display and grabs every state the manual shows; re-run it after any
visible UI change, then rebuild the PDF. It needs Xvfb (fetched via
`nix` automatically if not installed), Pillow, and ImageMagick.

### Regenerating the icon

`icon.ico` at the repo root is the multi-resolution icon embedded in
the exe. It's built from `icon_assets/icon.svg` via
`icon_assets/build_icon.sh`, which uses `rsvg-convert` (librsvg) and
ImageMagick. Edit the SVG, re-run the script, commit both, rebuild
the exe.

## Source layout

| File             | Role                                                  |
| ---------------- | ----------------------------------------------------- |
| `cac_gui.py`     | Tk application — Notebook with Scanner / Hours / Limits / Roster / Banned tabs |
| `cac_decoder.py` | Parses an 18-char CAC Code 39 barcode into fields     |
| `settings.py`    | Persisted config (hours, limits, roster, banned)      |
| `scan_log.py`    | Per-scan record + count-since-date queries            |
| `audit_log.py`   | Append-only audit trail of admin actions              |
| `reset_log.py`   | Periodic log rollover                                 |
| `daily_log.py`   | Read-only per-day CSV of every scan (allowed, denied, invalid) in `daily_logs/YYYY/MM/` |
| `sound.py`       | Verdict sounds — bell on ALLOWED, buzzer on DENIED/INVALID |
| `backup.py`      | Settings + log backup/restore                         |
| `start_menu.py`  | Install/uninstall (Program Files copy, ACL, shortcut, registry) |
| `version.py`     | App name/version/AUMID — single source of truth       |
| `BarScanner.spec`| PyInstaller spec (single-file, windowed, icon + version) |
| `icon.ico`       | Multi-res Windows icon embedded in the exe            |
| `icon_assets/`   | SVG icon source, rebuild script, version-info file    |
| `GUIDE.md`       | Full user manual: install, setup, daily use, every tab, troubleshooting |
| `GUIDE.pdf`      | Printable PDF of the same manual                      |
| `guide_images/`  | Screenshots embedded in the manual, plus `capture.py` that regenerates them |
| `build_guide_images.sh` | Regenerates `guide_images/*.png` by driving the GUI under Xvfb |
| `build_guide_pdf.sh` | Regenerates `GUIDE.pdf` from `GUIDE.md` + `guide_images/` |
| `sounds/`        | `allowed.wav` / `denied.wav`, bundled into the exe    |
| `make_sounds.py` | Regenerates `sounds/*.wav` (stdlib synthesis, no deps) |
