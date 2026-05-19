#!/usr/bin/env bash
# Render GUIDE.md → GUIDE.pdf for the printable / downloadable version
# linked from the README. Re-run whenever GUIDE.md changes.
#
# Requires:
#   - python3 with the `markdown` library    (pip install --user markdown)
#   - chromium                                (sudo pacman -S chromium)
#   - noto-fonts-emoji or equivalent          (sudo pacman -S noto-fonts-emoji)
#
# Pipeline: markdown → styled HTML → PDF via headless Chromium. We
# avoid pandoc + LaTeX because it's a multi-GB toolchain for what is a
# six-page user-facing document.

set -euo pipefail

cd "$(dirname "$0")"

# Use a venv if one is available, else fall back to system python3
# with an installed `markdown` package.
PY="${PY:-python3}"
if [[ -x "/tmp/pyi_test/bin/python" ]]; then
    PY="/tmp/pyi_test/bin/python"
fi

"$PY" - <<'PY'
import markdown
from pathlib import Path

src = Path("GUIDE.md").read_text(encoding="utf-8")
body = markdown.markdown(
    src,
    extensions=["extra", "smarty", "sane_lists", "toc"],
)

CSS = """
@page {
    size: Letter;
    margin: 0.7in 0.65in;
}

body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, "Noto Color Emoji", sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1f2937;
    max-width: 7.2in;
    margin: 0 auto;
}

/* ---------- Headings ---------- */

h1 {
    font-size: 27pt;
    color: #0e3a35;
    margin: 0 0 4pt;
    padding: 0 0 8pt;
    border-bottom: 4px solid #d4af37;
    letter-spacing: -0.5pt;
    line-height: 1.15;
}

h1 + p {
    color: #5b6770;
    font-style: italic;
    margin-bottom: 22pt;
}

h2 {
    font-size: 16pt;
    color: #0e3a35;
    margin: 24pt 0 10pt;
    padding: 5pt 0 5pt 14pt;
    border-left: 6px solid #d4af37;
    page-break-after: avoid;
    line-height: 1.2;
}

h3 {
    font-size: 12.5pt;
    color: #1f6d63;
    margin: 16pt 0 5pt;
    page-break-after: avoid;
    font-weight: 700;
}

/* ---------- Paragraphs / inline ---------- */

p { margin: 0 0 9pt; orphans: 3; widows: 3; }
strong { color: #0e3a35; font-weight: 700; }
em { color: #6a5500; font-style: italic; }

/* ---------- Inline code (paths, file names) ---------- */

code {
    font-family: "Consolas", "Menlo", "Liberation Mono", monospace;
    font-size: 9.5pt;
    background: #f4ecd6;
    padding: 1pt 5pt;
    border-radius: 3pt;
    color: #5c3317;
    border: 1px solid #e6d9b3;
    white-space: nowrap;
}

/* ---------- Code blocks ---------- */

pre {
    background: #1f2937;
    color: #f4ecd6;
    border-radius: 5pt;
    padding: 10pt 14pt;
    overflow-wrap: break-word;
    white-space: pre-wrap;
    page-break-inside: avoid;
    font-size: 9.5pt;
    margin: 10pt 0;
}
pre code {
    background: transparent;
    border: 0;
    padding: 0;
    color: inherit;
    white-space: pre-wrap;
    font-size: 9.5pt;
}

/* ---------- Unordered lists ---------- */

ul {
    margin: 0 0 11pt 0;
    padding: 0 0 0 20pt;
    list-style: none;
}
ul > li {
    position: relative;
    margin-bottom: 4pt;
    padding-left: 4pt;
}
ul > li::before {
    content: "";
    position: absolute;
    left: -12pt;
    top: 7pt;
    width: 5pt;
    height: 5pt;
    background: #d4af37;
    border-radius: 50%;
}

/* ---------- Ordered lists rendered as step circles ---------- */

ol {
    list-style: none;
    counter-reset: step;
    margin: 10pt 0 14pt 0;
    padding: 0;
}
ol > li {
    counter-increment: step;
    position: relative;
    padding: 4pt 0 10pt 40pt;
    margin: 0;
    min-height: 28pt;
    page-break-inside: avoid;
}
ol > li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 1pt;
    width: 28pt;
    height: 28pt;
    background: #1f6d63;
    color: #ffffff;
    border-radius: 50%;
    font-weight: 700;
    font-size: 13pt;
    text-align: center;
    line-height: 28pt;
    box-shadow: inset 0 -2px 0 rgba(0, 0, 0, 0.2);
}
ol > li > p:first-child { display: inline; }
ol > li > p { margin-bottom: 4pt; }
ol > li > ul,
ol > li > ol {
    margin-top: 5pt;
    margin-left: 0;
}

/* ---------- Tables ---------- */

table {
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    margin: 10pt 0 14pt;
    font-size: 10pt;
    page-break-inside: avoid;
    border: 1px solid #c9d5d0;
    border-radius: 4pt;
    overflow: hidden;
}
thead th {
    background: #1f6d63;
    color: #ffffff;
    text-align: left;
    padding: 7pt 11pt;
    font-weight: 700;
    font-size: 10pt;
    border-bottom: 1px solid #155148;
}
tbody td {
    border-top: 1px solid #e2eae7;
    padding: 6pt 11pt;
    vertical-align: top;
}
tbody tr:first-child td { border-top: 0; }
tbody tr:nth-child(even) td { background: #f6f9f8; }
tbody td code {
    font-size: 9pt;
    padding: 1pt 4pt;
}

/* ---------- Blockquotes as callout boxes ---------- */

blockquote {
    margin: 11pt 0;
    padding: 9pt 14pt;
    border-left: 5px solid #d4af37;
    background: #fdf7e1;
    border-radius: 0 4pt 4pt 0;
    page-break-inside: avoid;
    color: #4a3d10;
}
blockquote p { margin: 0; color: #4a3d10; }
blockquote p + p { margin-top: 6pt; }
blockquote strong { color: #4a3d10; }

/* ---------- Horizontal rule as a centered divider ---------- */

hr {
    border: 0;
    height: 2px;
    background: linear-gradient(to right,
        transparent 0%,
        #c0a040 30%,
        #c0a040 70%,
        transparent 100%);
    margin: 22pt 0;
}

/* ---------- Links ---------- */

a {
    color: #1f6d63;
    text-decoration: none;
    border-bottom: 1px dotted #1f6d63;
}

/* ---------- Emoji indicators in tables ---------- */

td:first-child { font-weight: 600; }
"""

html = (
    "<!doctype html>\n"
    "<html><head><meta charset=\"utf-8\">"
    "<title>CAC Bar Scanner — User Guide</title>"
    f"<style>{CSS}</style>"
    "</head><body>" + body + "</body></html>\n"
)

Path("_guide_print.html").write_text(html, encoding="utf-8")
PY

# Headless Chromium → PDF. Flags suppress browser-default header/
# footer (date, URL, page numbers) for a clean print output. The
# input must end in .html so Chromium sniffs it as HTML.
chromium \
    --headless=new \
    --no-sandbox \
    --disable-gpu \
    --no-pdf-header-footer \
    --print-to-pdf=GUIDE.pdf \
    "file://$PWD/_guide_print.html" \
    2> >(grep -v -E '^\[.*\] *$|^$' >&2 || true)

rm -f _guide_print.html

echo "Wrote $PWD/GUIDE.pdf"
