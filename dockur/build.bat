@echo off
REM dockur/build.bat — run inside the Windows VM to produce BarScanner.exe.
REM
REM Prereqs (one-time):
REM   - The VM has finished its first boot and oem\install.bat has
REM     completed (look for READY.txt on the desktop).
REM   - Z: is mapped to \\host.lan\Data (install.bat does this).
REM
REM From a Command Prompt inside Windows:
REM   Z:\dockur\build.bat
REM
REM Output: dist\BarScanner.exe in the host's scanner/ directory
REM (since Z:\ IS the host's scanner/ via the /data mount).

setlocal
cd /d Z:\

if not exist cac_gui.py (
    echo ERROR: cac_gui.py not found in Z:\
    echo The /data mount in compose.yml must point at the scanner/ dir.
    exit /b 1
)

REM Wipe stale build state so a failure doesn't get masked by an old .exe.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --onefile --windowed --name BarScanner --clean --noconfirm cac_gui.py
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

if not exist dist\BarScanner.exe (
    echo ERROR: pyinstaller reported success but dist\BarScanner.exe is missing.
    exit /b 1
)

echo.
echo Build successful: dist\BarScanner.exe
dir dist\BarScanner.exe
endlocal
