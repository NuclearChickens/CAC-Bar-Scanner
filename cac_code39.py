#!/usr/bin/env python3
"""CLI: decode one CAC Code 39 barcode passed as argv, stdin, or prompt."""
import sys

from cac_decoder import InvalidBarcode, decode


def _read_input() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return input("Barcode: ")


def main() -> int:
    try:
        r = decode(_read_input())
    except InvalidBarcode as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"EDIPI:    {r.edipi}")
    print(f"Category: {r.category_code} ({r.category})")
    print(f"Branch:   {r.branch_code} ({r.branch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
