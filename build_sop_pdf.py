#!/usr/bin/env python3
"""Render SOP.txt to a printable single-page PDF via hand-rolled PostScript.

Run from the repo root:

    python3 build_sop_pdf.py

Output: SOP.pdf, fixed at one US-Letter page in Courier so it prints
identically on any system. No third-party Python deps; only requires
the system ``ps2pdf`` (Ghostscript wrapper).

Tuned for the current SOP.txt (~71 lines × ~71 cols). Edit FONT_SIZE
and LINE_HEIGHT if the SOP grows past the visible area; ps2pdf will
silently emit a 2-page document if it overflows.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

SRC = Path(__file__).parent / "SOP.txt"
OUT = Path(__file__).parent / "SOP.pdf"

# US Letter is 612 × 792 pt. With 0.5" left margin and the text starting
# 22 pt below the top edge, we have ~720 pt of vertical and ~540 pt of
# horizontal space for the body. Courier 8.5pt at 10pt line height fits
# 71+ lines × 100+ cols cleanly on one page.
FONT_SIZE = 8.5
LINE_HEIGHT = 10.0
LEFT_MARGIN = 36     # 0.5"
TOP_MARGIN = 770     # PostScript origin is bottom-left


def _escape(s: str) -> str:
    """Escape PostScript string literal special characters."""
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    ps = [
        "%!PS-Adobe-3.0",
        "%%Pages: 1",
        "%%DocumentMedia: Letter 612 792 0 () ()",
        "%%EndComments",
        "%%Page: 1 1",
        f"/Courier findfont {FONT_SIZE} scalefont setfont",
    ]
    y = TOP_MARGIN
    for line in lines:
        ps.append(f"{LEFT_MARGIN} {y:.2f} moveto ({_escape(line)}) show")
        y -= LINE_HEIGHT
    ps.extend(["showpage", "%%EOF"])
    psdoc = "\n".join(ps).encode()

    subprocess.run(
        ["ps2pdf", "-sPAPERSIZE=letter", "-", str(OUT)],
        input=psdoc,
        check=True,
    )
    print(f"wrote {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
