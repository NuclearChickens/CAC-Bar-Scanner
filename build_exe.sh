#!/usr/bin/env bash
# build_exe.sh — produce dist/BarScanner.exe via Wine in Docker.
#
# Usage:
#     ./build_exe.sh
#
# Output:
#     dist/BarScanner.exe — single-file Windows binary, copy to a
#     Windows machine and double-click to run.
#
# First run pulls the image (~2 GB) and takes a few minutes. Subsequent
# runs reuse the cached image and finish in under a minute.
#
# Override the image with: IMAGE=cdrx/pyinstaller-windows ./build_exe.sh

set -euo pipefail

IMAGE="${IMAGE:-batonogov/pyinstaller-windows:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

# Wipe previous PyInstaller output so a stale .exe from a failed build
# can't masquerade as the new one.
rm -rf build dist

# Run PyInstaller inside the Wine container.
#   --onefile     — single self-contained .exe (no folder of DLLs)
#   --windowed    — no console window (this is a tk GUI app)
#   --name        — output filename
#   --clean       — discard cached PyInstaller state
#   --noconfirm   — overwrite dist/ without prompting
#
# All sibling .py modules (backup, settings, audit_log, scan_log,
# reset_log, cac_decoder, cac_code39) are picked up automatically as
# imports of cac_gui.py — no need to list them.
docker run --rm \
    -v "$SCRIPT_DIR:/src/" \
    "$IMAGE" \
    "pyinstaller --onefile --windowed --name BarScanner --clean --noconfirm cac_gui.py"

# PyInstaller runs as root in the container, so dist/ and build/ end
# up root-owned on the host. Chown them back via a tiny throwaway
# alpine container so we don't need sudo on the host.
docker run --rm \
    -v "$SCRIPT_DIR:/src" \
    --entrypoint sh \
    alpine:latest \
    -c "chown -R $(id -u):$(id -g) /src/dist /src/build 2>/dev/null || true"

if [[ ! -f "$SCRIPT_DIR/dist/BarScanner.exe" ]]; then
    echo >&2
    echo "ERROR: build did not produce dist/BarScanner.exe" >&2
    echo "Check the PyInstaller output above for the actual failure." >&2
    exit 1
fi

echo
echo "Build successful:"
ls -lh "$SCRIPT_DIR/dist/BarScanner.exe"
