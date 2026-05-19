#!/usr/bin/env python3
"""Render DECODING.md to a self-contained, print-friendly HTML file."""
from pathlib import Path
import markdown

SRC = Path(__file__).parent / "DECODING.md"
OUT = Path(__file__).parent / "DECODING.html"

CSS = """
@page { size: Letter; margin: 0.75in 0.7in; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Charter", "Source Serif Pro", Georgia, serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: #111;
  max-width: 7.1in;
  margin: 0 auto;
  padding: 0.4in 0;
}
h1 {
  font-size: 18pt;
  line-height: 1.2;
  margin: 0 0 0.4em;
  border-bottom: 2px solid #111;
  padding-bottom: 0.25em;
  break-after: avoid;
  page-break-after: avoid;
}
h2 {
  font-size: 13pt;
  margin: 1.4em 0 0.5em;
  break-after: avoid;
  page-break-after: avoid;
  border-bottom: 1px solid #888;
  padding-bottom: 0.15em;
}
h3 {
  font-size: 11pt;
  margin: 1em 0 0.4em;
  break-after: avoid;
  page-break-after: avoid;
}
h2 + p, h3 + p { break-after: avoid; page-break-after: avoid; }
p, ul, ol, blockquote, table { margin: 0.5em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 0.15em 0; }
blockquote {
  border-left: 3px solid #888;
  margin-left: 0;
  padding: 0.2em 0.8em;
  color: #333;
  background: #f6f6f6;
  font-size: 9.8pt;
}
code {
  font-family: "DejaVu Sans Mono", "Menlo", Consolas, monospace;
  font-size: 9.5pt;
  background: #f0f0f0;
  padding: 0.05em 0.3em;
  border-radius: 2px;
}
pre {
  background: #f4f4f4;
  border: 1px solid #ddd;
  border-radius: 3px;
  padding: 0.5em 0.7em;
  font-size: 7.8pt;
  line-height: 1.35;
  white-space: pre;
  overflow: hidden;
  break-inside: avoid;
  page-break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; white-space: pre; }
hr { border: 0; border-top: 1px solid #bbb; margin: 1.2em 0; }
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 9.5pt;
}
thead { display: table-header-group; }
tfoot { display: table-footer-group; }
tr, th, td { break-inside: avoid; page-break-inside: avoid; }
th, td {
  border: 1px solid #999;
  padding: 0.25em 0.45em;
  vertical-align: top;
  text-align: left;
}
th { background: #e8e8e8; font-weight: 600; }
tbody tr:nth-child(even) td { background: #fafafa; }
a { color: #14418f; text-decoration: none; word-break: break-all; }
h2 + hr, hr + h2 { display: none; }
section, h2 { break-inside: avoid; }
@media print {
  body { padding: 0; max-width: none; }
  a { color: #111; }
}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    title = "CAC Barcode Guide"
    OUT.write_text(
        HTML_TEMPLATE.format(title=title, css=CSS, body=body),
        encoding="utf-8",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
