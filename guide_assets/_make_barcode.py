"""Generate a Code 39 SVG barcode for the guide."""
from pathlib import Path

# Code 39 encoding table: each entry is the 9-element bar/space pattern,
# where 0 = narrow and 1 = wide. Pattern is b-s-b-s-b-s-b-s-b
# (5 bars, 4 spaces). Each character is followed by a narrow inter-char gap.
PATTERNS = {
    "0": "000110100", "1": "100100001", "2": "001100001",
    "3": "101100000", "4": "000110001", "5": "100110000",
    "6": "001110000", "7": "000100101", "8": "100100100",
    "9": "001100100", "A": "100001001", "B": "001001001",
    "C": "101001000", "D": "000011001", "E": "100011000",
    "F": "001011000", "G": "000001101", "H": "100001100",
    "I": "001001100", "J": "000011100", "K": "100000011",
    "L": "001000011", "M": "101000010", "N": "000010011",
    "O": "100010010", "P": "001010010", "Q": "000000111",
    "R": "100000110", "S": "001000110", "T": "000010110",
    "U": "110000001", "V": "011000001", "W": "111000000",
    "X": "010010001", "Y": "110010000", "Z": "011010000",
    "-": "010000101", ".": "110000100", " ": "011000100",
    "$": "010101000", "/": "010100010", "+": "010001010",
    "%": "000101010", "*": "010010100",
}

NARROW = 2.0   # px per narrow element
WIDE = NARROW * 2.5
GAP = NARROW   # inter-char gap
HEIGHT = 110
QUIET = 12 * NARROW  # quiet zone
TEXT_HEIGHT = 28


def char_width(pat: str) -> float:
    return sum(WIDE if b == "1" else NARROW for b in pat)


def render(text: str) -> str:
    full = f"*{text}*"
    bar_w = sum(char_width(PATTERNS[c]) for c in full) + (len(full) - 1) * GAP
    total_w = QUIET * 2 + bar_w
    total_h = HEIGHT + TEXT_HEIGHT + 8

    bars: list[str] = []
    x = QUIET
    for i, ch in enumerate(full):
        pat = PATTERNS[ch]
        is_bar = True
        for elem in pat:
            w = WIDE if elem == "1" else NARROW
            if is_bar:
                bars.append(
                    f'<rect x="{x:.2f}" y="0" width="{w:.2f}" '
                    f'height="{HEIGHT}" fill="#000" />'
                )
            x += w
            is_bar = not is_bar
        if i < len(full) - 1:
            x += GAP

    bars_xml = "\n  ".join(bars)
    label = text  # human-readable, no asterisks
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {total_h}" preserveAspectRatio="xMidYMid meet">
  <rect x="0" y="0" width="{total_w:.0f}" height="{total_h}" fill="#fff"/>
  {bars_xml}
  <text x="{total_w/2:.0f}" y="{HEIGHT + TEXT_HEIGHT - 2}" text-anchor="middle"
        font-family="ui-monospace, Menlo, Consolas, monospace" font-size="22"
        letter-spacing="2" fill="#000">{label}</text>
</svg>'''


def main():
    out = Path(__file__).resolve().parent
    # 18-char demo CAC barcode (representative: 8 reserved chars, 7-char
    # base-32 EDIPI block, category, branch).
    # Base-32 of EDIPI 1234567890 = "14PC0MI"; category A (Active duty),
    # branch F (USAF). 8 reserved + 7 EDIPI + cat + branch + checksum = 18.
    demo = "ABCDEFGH" + "14PC0MI" + "A" + "F" + "0"
    assert len(demo) == 18, len(demo)
    svg = render(demo)
    (out / "barcode.svg").write_text(svg, encoding="utf-8")
    print(f"wrote {out / 'barcode.svg'}  ({len(svg)} bytes, encoding {demo!r})")


if __name__ == "__main__":
    main()
