#!/usr/bin/env bash
# Render GUIDE.md → GUIDE.pdf for the printable / downloadable version
# linked from the README. Re-run whenever GUIDE.md changes.
#
# Requires:
#   - python3 with the `markdown` library    (pip install --user markdown)
#   - chromium                                (sudo pacman -S chromium)
#
# The pipeline is markdown → standalone HTML (with print-friendly CSS
# embedded inline) → PDF via headless Chromium. We avoid pandoc + LaTeX
# because it's a multi-GB toolchain for what is essentially a 6-page
# user-facing document.

set -euo pipefail

cd "$(dirname "$0")"

# Use a venv if one is available, else fall back to system python3 with
# an installed `markdown` package. The path here matches the test venv
# created during development; adjust if you're rebuilding from scratch.
PY="${PY:-python3}"
if [[ -x "/tmp/pyi_test/bin/python" ]]; then
    PY="/tmp/pyi_test/bin/python"
fi

"$PY" - <<'PY'
import markdown
from pathlib import Path

src = Path("GUIDE.md").read_text(encoding="utf-8")
body = markdown.markdown(src, extensions=["extra", "smarty"])

CSS = """
@page {
    size: Letter;
    margin: 0.75in 0.7in;
}
body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #1f2937;
    max-width: 7in;
    margin: 0 auto;
}
h1 {
    font-size: 24pt;
    color: #0e3a35;
    border-bottom: 3px solid #d4af37;
    padding-bottom: 8pt;
    margin: 0 0 18pt;
}
h2 {
    font-size: 15pt;
    color: #0e3a35;
    margin: 20pt 0 6pt;
    padding-bottom: 3pt;
    border-bottom: 1px solid #d1d5db;
    page-break-after: avoid;
}
h3 {
    font-size: 12.5pt;
    color: #374151;
    margin: 14pt 0 4pt;
    page-break-after: avoid;
}
p {
    margin: 0 0 9pt;
    orphans: 3;
    widows: 3;
}
ul, ol {
    margin: 0 0 11pt 22pt;
    padding: 0;
}
li {
    margin-bottom: 4pt;
}
li > p { margin-bottom: 4pt; }
strong {
    color: #1f6d63;
    font-weight: 600;
}
em {
    color: #6a5500;
    font-style: italic;
}
code {
    font-family: "Consolas", "Menlo", "Liberation Mono", monospace;
    font-size: 10pt;
    background: #f4ecd6;
    padding: 1pt 4pt;
    border-radius: 2pt;
    color: #5c3317;
    word-break: break-all;
}
pre {
    background: #f4ecd6;
    border: 1px solid #d1d5db;
    border-radius: 3pt;
    padding: 8pt 10pt;
    overflow-wrap: break-word;
    white-space: pre-wrap;
    page-break-inside: avoid;
}
pre code { background: transparent; padding: 0; }
a {
    color: #1f6d63;
    text-decoration: none;
}
hr {
    border: 0;
    border-top: 1px solid #d1d5db;
    margin: 12pt 0;
}
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

# Headless Chromium → PDF. The flags suppress the default browser
# header/footer (date, URL, page numbers) so the output looks like a
# clean printable document, not a browser screenshot. The file must
# end in .html so Chromium sniffs it as HTML rather than text/plain.
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
