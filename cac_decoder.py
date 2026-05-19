"""CAC Code 39 barcode decoder.

Public API:
    decode(raw: str) -> Decoded
    InvalidBarcode  -- raised for malformed input

The layout, alphabet, and lookup tables come from DoD ID Bar Code
Formats SDK v7.5.0 (Sept 2012); see DECODING.md for full provenance.
"""
from __future__ import annotations

from dataclasses import dataclass

BARCODE_LEN = 18

CATEGORIES = {
    "A": "Active duty member",
    "B": "Presidential Appointee",
    "C": "DoD civil service employee",
    "D": "100% disabled American veteran",
    "E": "DoD contract employee",
    "F": "Former member",
    "G": "National Guard (active 31+ days)",
    "H": "Medal of Honor recipient",
    "I": "Non-DoD civil service employee",
    "J": "Academy student",
    "K": "Non-appropriated fund (NAF) DoD employee",
    "L": "Lighthouse service",
    "M": "Non-Government agency personnel",
    "N": "National Guard (not active or <31 days)",
    "O": "Non-DoD contract employee",
    "Q": "Reserve retiree, not yet eligible for retired pay",
    "R": "Retired Uniformed Service member, eligible for retired pay",
    "S": "Reserve (active 31+ days)",
    "T": "Foreign military member",
    "U": "Foreign national employee",
    "V": "Reserve (not active or <31 days)",
    "W": "DoD beneficiary",
    "Y": "Retired DoD Civil Service Employee",
}

BRANCHES = {
    "A": "USA (Army)",
    "C": "USCG (Coast Guard)",
    "D": "DoD",
    "F": "USAF (Air Force)",
    "H": "USPHS (Public Health Service)",
    "M": "USMC (Marine Corps)",
    "N": "USN (Navy)",
    "O": "NOAA",
    "1": "Foreign Army",
    "2": "Foreign Navy",
    "3": "Foreign Marine Corps",
    "4": "Foreign Air Force",
    "X": "Other / Not Applicable",
}


class InvalidBarcode(ValueError):
    """Raised when input is not a valid 18-character CAC Code 39 barcode."""


@dataclass(frozen=True)
class Decoded:
    raw: str
    edipi: str
    category_code: str
    category: str
    branch_code: str
    branch: str


def decode(raw: str) -> Decoded:
    s = (raw or "").strip().upper()
    if len(s) != BARCODE_LEN:
        raise InvalidBarcode(f"expected {BARCODE_LEN} characters, got {len(s)}")
    try:
        edipi_int = int(s[8:15], 32)
    except ValueError:
        raise InvalidBarcode(f"EDIPI slice {s[8:15]!r} is not valid base-32") from None
    cat_code = s[15]
    br_code = s[16]
    return Decoded(
        raw=s,
        edipi=f"{edipi_int:010d}",
        category_code=cat_code,
        category=CATEGORIES.get(cat_code, "Unknown"),
        branch_code=br_code,
        branch=BRANCHES.get(br_code, "Unknown"),
    )
