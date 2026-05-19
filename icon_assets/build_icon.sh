#!/usr/bin/env bash
# Re-render icon.svg into a multi-resolution Windows icon (icon.ico) at
# the repo root. PyInstaller picks it up via BarScanner.spec.
#
# Requires: rsvg-convert (librsvg) and ImageMagick. On Arch:
#     sudo pacman -S librsvg imagemagick

set -euo pipefail

cd "$(dirname "$0")"

SIZES=(16 24 32 48 64 128 256)
PNGS=()

for s in "${SIZES[@]}"; do
    rsvg-convert -w "$s" -h "$s" icon.svg -o "_${s}.png"
    PNGS+=("_${s}.png")
done

# magick (ImageMagick 7) is preferred over the legacy `convert` alias.
magick "${PNGS[@]}" ../icon.ico

# Tidy up the intermediate PNGs.
rm -f "${PNGS[@]}"

echo "Wrote $(realpath ../icon.ico)"
