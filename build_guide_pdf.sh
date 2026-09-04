#!/usr/bin/env bash
# Render GUIDE.md → GUIDE.pdf for the printable / downloadable version
# linked from the README. Re-run whenever GUIDE.md or guide_images/
# changes.
#
# Requires:
#   - python3 with the `markdown` library    (pip install --user markdown)
#   - chromium                                (sudo pacman -S chromium)
#   - noto-fonts-emoji or equivalent          (sudo pacman -S noto-fonts-emoji)
#
# Pipeline: markdown → styled HTML → PDF via headless Chromium. We
# avoid pandoc + LaTeX because it's a multi-GB toolchain for what is a
# user-facing document.
#
# GUIDE.md uses GitHub's alert syntax (`> [!TIP]`, `> [!WARNING]`,
# `> [!NOTE]`, `> [!IMPORTANT]`) so callouts render natively on
# github.com; the Python step below rewrites those blockquotes into
# styled callout boxes for the PDF. Screenshots are wrapped in
# <figure> with the alt text as the caption.

set -euo pipefail

cd "$(dirname "$0")"

PY="${PY:-python3}"

"$PY" - <<'PY'
import html
import re
from pathlib import Path

import markdown

src = Path("GUIDE.md").read_text(encoding="utf-8")
body = markdown.markdown(
    src,
    extensions=["extra", "smarty", "sane_lists", "toc"],
)

# ---- GitHub alerts → callout boxes -------------------------------------
ALERT_TITLES = {
    "TIP": "Tip",
    "NOTE": "Note",
    "IMPORTANT": "Important",
    "WARNING": "Warning",
    "CAUTION": "Caution",
}
KINDS = "TIP|NOTE|IMPORTANT|WARNING|CAUTION"
def _alert(m: re.Match) -> str:
    kind = m.group(1)
    return (
        f'<blockquote class="alert alert-{kind.lower()}">'
        f'<p class="alert-title">{ALERT_TITLES[kind]}</p><p>'
    )
# Python-Markdown merges consecutive blockquotes into one; a marker that
# is not the first paragraph of its blockquote therefore starts a new box.
body = re.sub(
    rf"(?<!<blockquote>)\n<p>\[!({KINDS})\]\s*",
    lambda m: "</blockquote>\n" + _alert(m),
    body,
)
body = re.sub(rf"<blockquote>\s*<p>\[!({KINDS})\]\s*", _alert, body)

# ---- Screenshots → figures with captions -------------------------------
def _figure(m: re.Match) -> str:
    attrs = m.group(1)
    alt = re.search(r'alt="([^"]*)"', attrs)
    cap = html.escape(html.unescape(alt.group(1))) if alt else ""
    return f"<figure><img{attrs}><figcaption>{cap}</figcaption></figure>"
body = re.sub(r"<p><img([^>]*)>\s*</p>", _figure, body)

CSS = """
@page {
    size: Letter;
    margin: 0.8in 0.7in 0.85in;
    @bottom-left {
        content: "CAC Bar Scanner \\2014 User Manual";
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 8.5pt;
        color: #7a8790;
    }
    @bottom-right {
        content: "Page " counter(page);
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 8.5pt;
        color: #7a8790;
    }
}
@page :first {
    @bottom-left { content: none; }
    @bottom-right { content: none; }
}

:root {
    --ink: #1f2937;
    --muted: #5b6770;
    --teal: #1f6d63;
    --teal-dark: #0e3a35;
    --gold: #d4af37;
    --gold-dark: #7a5d10;
    --line: #c9d5d0;
    --row: #f4f8f6;
}

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, "Noto Color Emoji", sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: var(--ink);
    margin: 0 auto;
}

/* ---------- Cover block (h1 + intro + link box) ---------- */

h1 {
    font-size: 30pt;
    color: var(--teal-dark);
    margin: 0.35in 0 6pt;
    padding: 0 0 10pt;
    border-bottom: 5px solid var(--gold);
    letter-spacing: -0.5pt;
    line-height: 1.12;
}
h1 + p {
    color: var(--muted);
    font-size: 12pt;
    margin: 10pt 0 18pt;
}

/* ---------- Headings ---------- */

h2 {
    font-size: 18pt;
    color: var(--teal-dark);
    margin: 0 0 12pt;
    padding: 8pt 0 8pt 16pt;
    border-left: 7px solid var(--gold);
    background: linear-gradient(to right, #f3f7f5, transparent 70%);
    break-after: avoid;
    line-height: 1.2;
}
h2 { margin-top: 30pt; }
/* The quick reference card is meant to be printed on its own. */
#17-quick-reference-card { break-before: page; margin-top: 0; }

h3 {
    font-size: 13pt;
    color: var(--teal);
    margin: 18pt 0 6pt;
    break-after: avoid;
    font-weight: 700;
}
h3 + h4 { margin-top: 6pt; }
h4 {
    font-size: 11pt;
    color: var(--teal-dark);
    margin: 12pt 0 4pt;
    break-after: avoid;
}

/* ---------- Paragraphs / inline ---------- */

p { margin: 0 0 9pt; orphans: 3; widows: 3; }
strong { color: var(--teal-dark); font-weight: 700; }
em { color: #6a5500; font-style: italic; }

a {
    color: var(--teal);
    text-decoration: none;
    border-bottom: 1px dotted var(--teal);
}

code {
    font-family: "Consolas", "Menlo", "Liberation Mono", monospace;
    font-size: 9.3pt;
    background: #f4ecd6;
    padding: 1pt 5pt;
    border-radius: 3pt;
    color: #5c3317;
    border: 1px solid #e6d9b3;
    white-space: nowrap;
}

pre {
    background: #1f2937;
    color: #f4ecd6;
    border-radius: 5pt;
    padding: 10pt 14pt;
    overflow-wrap: break-word;
    white-space: pre-wrap;
    break-inside: avoid;
    font-size: 9.5pt;
    margin: 6pt 0 10pt;
}
pre code {
    background: transparent;
    border: 0;
    padding: 0;
    color: inherit;
    white-space: pre-wrap;
    font-size: 9.5pt;
}

/* ---------- Contents list ---------- */

#contents + ol {
    list-style: none;
    counter-reset: toc;
    margin: 0 0 12pt;
    padding: 0;
    columns: 2;
    column-gap: 28pt;
}
#contents + ol > li {
    counter-increment: toc;
    padding: 3pt 0 3pt 26pt;
    min-height: 0;
    border-bottom: 1px dotted var(--line);
    break-inside: avoid;
}
#contents + ol > li::before {
    content: counter(toc);
    position: absolute;
    left: 0;
    top: 3pt;
    width: auto;
    height: auto;
    background: none;
    box-shadow: none;
    border-radius: 0;
    color: var(--gold-dark);
    font-weight: 700;
    font-size: 10.5pt;
    line-height: inherit;
    text-align: right;
    min-width: 18pt;
}
#contents + ol > li a { border-bottom: 0; font-weight: 600; }

/* ---------- Unordered lists ---------- */

ul {
    margin: 0 0 10pt 0;
    padding: 0 0 0 18pt;
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
    background: var(--gold);
    border-radius: 50%;
}
li > ul { margin-top: 4pt; }

/* ---------- Ordered lists as numbered steps ---------- */

ol {
    list-style: none;
    counter-reset: step;
    margin: 6pt 0 12pt 0;
    padding: 0;
}
ol > li {
    counter-increment: step;
    position: relative;
    padding: 3pt 0 8pt 36pt;
    margin: 0;
    min-height: 24pt;
    break-inside: avoid;
}
ol > li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 2pt;
    width: 24pt;
    height: 24pt;
    background: var(--teal);
    color: #ffffff;
    border-radius: 50%;
    font-weight: 700;
    font-size: 12pt;
    text-align: center;
    line-height: 24pt;
    box-shadow: inset 0 -2px 0 rgba(0, 0, 0, 0.2);
}
ol > li > p:first-child { display: inline; }
ol > li > p { margin-bottom: 4pt; }
ol > li > ul,
ol > li > ol { margin-top: 5pt; margin-left: 0; }
ol > li > pre { margin-top: 6pt; }

/* ---------- Tables ---------- */

table {
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    margin: 8pt 0 14pt;
    font-size: 9.6pt;
    line-height: 1.4;
    border: 1px solid var(--line);
    border-radius: 4pt;
    overflow: hidden;
}
thead th {
    background: var(--teal);
    color: #ffffff;
    text-align: left;
    padding: 6pt 9pt;
    font-weight: 700;
    border-bottom: 1px solid #155148;
}
tbody td {
    border-top: 1px solid #e2eae7;
    padding: 5pt 9pt;
    vertical-align: top;
}
tbody tr { break-inside: avoid; }
tbody tr:first-child td { border-top: 0; }
tbody tr:nth-child(even) td { background: var(--row); }
tbody td code { font-size: 8.8pt; padding: 1pt 4pt; white-space: normal; }
td:first-child { font-weight: 600; }

/* ---------- Callout boxes ---------- */

blockquote {
    margin: 10pt 0 12pt;
    padding: 9pt 14pt;
    border-left: 5px solid var(--gold);
    background: #fdf7e1;
    border-radius: 0 4pt 4pt 0;
    break-inside: avoid;
    color: #4a3d10;
}
blockquote p { margin: 0; color: inherit; }
blockquote p + p { margin-top: 6pt; }
blockquote strong { color: inherit; }
blockquote a { color: inherit; border-bottom-color: currentColor; }

.alert-title {
    font-weight: 700;
    font-size: 9pt;
    letter-spacing: 0.8pt;
    text-transform: uppercase;
    margin-bottom: 3pt !important;
}
.alert-tip       { border-left-color: #1f6d63; background: #e9f4f1; color: #123f38; }
.alert-note      { border-left-color: #3b6fb6; background: #eaf1fb; color: #1d3a66; }
.alert-important { border-left-color: #7c4dbd; background: #f1ebfa; color: #3f2566; }
.alert-warning   { border-left-color: #c47d12; background: #fdf1dc; color: #5a3a06; }
.alert-caution   { border-left-color: #c0392b; background: #fbe9e7; color: #6b1d15; }

/* ---------- Figures (screenshots) ---------- */

figure {
    margin: 8pt 0 14pt;
    break-inside: avoid;
    text-align: center;
}
figure img {
    max-width: 100%;
    height: auto;
    border: 1px solid #b9c6c1;
    border-radius: 4pt;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}
figure img[src*="uninstall-dialog"] { max-width: 3.6in; }
figcaption {
    font-size: 9pt;
    color: var(--muted);
    font-style: italic;
    margin-top: 5pt;
}

/* ---------- Horizontal rule ---------- */

hr { display: none; }
"""

html_doc = (
    "<!doctype html>\n"
    "<html><head><meta charset=\"utf-8\">"
    "<title>CAC Bar Scanner — User Manual</title>"
    f"<style>{CSS}</style>"
    "</head><body>" + body + "</body></html>\n"
)

Path("_guide_print.html").write_text(html_doc, encoding="utf-8")
PY

# Headless Chromium → PDF. --no-pdf-header-footer drops Chromium's own
# date/URL header so the @page margin boxes in the CSS supply the
# running footer instead. The input must end in .html so Chromium
# sniffs it as HTML; screenshots are referenced relative to it.
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
