#!/usr/bin/env bash
# Regenerate guide_images/*.png — the screenshots embedded in GUIDE.md
# and GUIDE.pdf — by running the real GUI under a virtual X display.
# Re-run after any visible UI change, then ./build_guide_pdf.sh.
#
# Requires:
#   - Xvfb                      (Arch: xorg-server-xvfb; or via nix, below)
#   - openbox (optional)        gives the dialogs a title bar
#   - python3 with Pillow       (pacman -S python-pillow)
#   - ImageMagick `magick`      (pacman -S imagemagick) for downscaling
#
# If Xvfb / openbox aren't on PATH but `nix` is, they're fetched into
# the user's nix store (no root needed).

set -euo pipefail
cd "$(dirname "$0")"

find_tool() {
    local name="$1" attr="$2"
    if command -v "$name" >/dev/null 2>&1; then
        command -v "$name"
    elif command -v nix >/dev/null 2>&1; then
        echo "$(nix build "nixpkgs#$attr" --no-link --print-out-paths)/bin/$name"
    fi
}

XVFB="$(find_tool Xvfb xorg.xvfb)"
OPENBOX="$(find_tool openbox openbox || true)"
[[ -n "$XVFB" ]] || { echo "Xvfb not found (install xorg-server-xvfb or nix)" >&2; exit 1; }

DISPLAY_NUM=":99"
WORK="$(mktemp -d)"
trap 'kill ${OB_PID:-} ${XVFB_PID:-} 2>/dev/null || true; rm -rf "$WORK"' EXIT

"$XVFB" "$DISPLAY_NUM" -screen 0 1920x1080x24 -dpi 96 -nolisten tcp >/dev/null 2>&1 &
XVFB_PID=$!
sleep 1.5
if [[ -n "$OPENBOX" ]]; then
    DISPLAY="$DISPLAY_NUM" "$OPENBOX" >/dev/null 2>&1 &
    OB_PID=$!
    sleep 1
fi

# HOME is redirected so the app's ~/.cac_scanner data lands in $WORK,
# never in the real data folder. Tk prints a few harmless "invalid
# command name" lines when the window is torn down; filter them.
mkdir -p "$WORK/home" "$WORK/shots"
HOME="$WORK/home" DISPLAY="$DISPLAY_NUM" python3 guide_images/capture.py "$WORK/shots" \
    2> >(grep -v -E 'invalid command name|while executing|<lambda>|"after" script' >&2 || true)

# Downscale the full-screen grabs for the repo; keep the dialog crop as is.
for f in "$WORK"/shots/*.png; do
    n="$(basename "$f")"
    if [[ "$n" == "uninstall-dialog.png" ]]; then
        magick "$f" -strip "guide_images/$n"
    else
        magick "$f" -resize 1600x -strip -define png:compression-level=9 "guide_images/$n"
    fi
done

echo "Wrote $(ls guide_images/*.png | wc -l) screenshots to $PWD/guide_images/"
