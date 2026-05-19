#!/usr/bin/env bash
# dockur/build.sh — host-side trigger for a native Windows build.
#
# Prereqs:
#   - ``docker compose up -d`` has been run from this directory.
#   - The VM has booted past the OEM install (READY.txt exists on the
#     Windows desktop). Check progress at http://localhost:8006.
#   - ``xfreerdp`` installed on the host (sudo pacman -S freerdp).
#
# This script RDPs into the VM as the builder user and runs build.bat.
# Output: ../dist/BarScanner.exe in the parent (scanner/) directory,
# placed there by PyInstaller via the /data mount.

set -euo pipefail

HOST="${HOST:-localhost}"
USER="${USER_OVERRIDE:-builder}"
PASS="${PASS:-builder}"

if ! command -v xfreerdp >/dev/null 2>&1; then
    echo "ERROR: xfreerdp not installed. Run: sudo pacman -S freerdp" >&2
    exit 1
fi

# /cmd: tell xfreerdp to run a single command and exit when it finishes.
# /cert:ignore tolerates the VM's self-signed RDP cert.
xfreerdp \
    /v:"$HOST":3389 \
    /u:"$USER" \
    /p:"$PASS" \
    /cert:ignore \
    /dynamic-resolution \
    /cmd:"cmd /c Z:\\dockur\\build.bat"

# xfreerdp exits 0 even on remote command failure; verify the artifact.
if [[ ! -f "../dist/BarScanner.exe" ]]; then
    echo "ERROR: build did not produce ../dist/BarScanner.exe" >&2
    echo "Check the RDP session output and C:\\install.log for details." >&2
    exit 1
fi

echo
echo "Native Windows build successful:"
ls -lh ../dist/BarScanner.exe
