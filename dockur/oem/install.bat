@echo off
REM dockur/oem/install.bat — runs once after Windows finishes installing.
REM
REM dockurr/windows automatically executes any install.bat it finds in
REM the /oem mount during first boot. Use it to provision Python +
REM PyInstaller so subsequent runs of build.bat just do the build.
REM
REM Logs land in C:\install.log and a READY.txt appears on the desktop
REM when everything is done — that's the signal that the VM is ready
REM to accept builds.

setlocal
set LOG=C:\install.log
echo === %DATE% %TIME%  install.bat started === > %LOG%

REM -------------------------------------------------- mount the host share

REM dockurr exposes the host's /data mount inside Windows as
REM \\host.lan\Data. Map it to Z: persistently so build.bat can use a
REM short path. Persistent mappings survive reboots for this user.
echo --- mapping Z: to \\host.lan\Data >> %LOG%
net use Z: \\host.lan\Data /persistent:yes >> %LOG% 2>&1

REM -------------------------------------------------- install Python 3.12

set PYVER=3.12.7
set PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe
set PYEXE=C:\python-installer.exe

echo --- downloading Python %PYVER% >> %LOG%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Invoke-WebRequest '%PYURL%' -OutFile '%PYEXE%'" >> %LOG% 2>&1
if not exist %PYEXE% (
    echo FAILED to download Python installer >> %LOG%
    exit /b 1
)

echo --- installing Python silently >> %LOG%
%PYEXE% /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 >> %LOG% 2>&1
del %PYEXE%

REM Refresh PATH in this session — the installer added it to the
REM machine PATH but our cmd inherits the old one.
set PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%

REM -------------------------------------------------- install PyInstaller

echo --- upgrading pip and installing PyInstaller >> %LOG%
python -m pip install --upgrade pip >> %LOG% 2>&1
python -m pip install pyinstaller >> %LOG% 2>&1

REM -------------------------------------------------- ready signal

echo Build environment ready: > C:\Users\Public\Desktop\READY.txt
echo   Python:      >> C:\Users\Public\Desktop\READY.txt
python --version >> C:\Users\Public\Desktop\READY.txt 2>&1
echo   PyInstaller: >> C:\Users\Public\Desktop\READY.txt
pyinstaller --version >> C:\Users\Public\Desktop\READY.txt 2>&1
echo. >> C:\Users\Public\Desktop\READY.txt
echo Run Z:\dockur\build.bat from a Command Prompt to build BarScanner.exe. >> C:\Users\Public\Desktop\READY.txt

echo === %DATE% %TIME%  install.bat finished === >> %LOG%
endlocal
