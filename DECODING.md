# CAC Barcode Guide for Kids Who Can't Read Good and Who Wanna Learn to Do Other Stuff Good Too

A from-scratch guide to pulling **EDIPI**, **Personnel Category Code**,
and **Branch Code** out of the 18-character barcode on the back of a
U.S. Department of Defense Common Access Card (CAC).

The two source specs:

- **CAC End-Point Implementation Guide v2.1.1** (2 April 2010) —
  high-level reference.
  <https://www.cac.mil/Portals/53/Documents/CAC_End_Point_Implementation_Guide_v2.1.1(2010.4.2).pdf>
- **DoD ID Bar Code Formats — SDK v7.5.0** (September 2012) — contains
  the field layout (§2.1, Table 2), the base-32 algorithm (Appendix
  B.1), and the lookup tables (Tables 25–27 in Appendix C). Section and
  table numbers below refer to this document.
  <https://archive.org/details/DoDIDBarCodeSDKFormatsV750Sep2012>

The CAC carries machine-readable data in three places: the embedded
chip, a PDF417 barcode on the **front** (large, 2D), and a Code 39
barcode on the **back** (small, linear). **This document covers only
the Code 39 barcode on the back.** Your scanner does the Code 39
decoding itself and hands your program an ordinary 18-character ASCII
string; your only job is to interpret it.

---

## 1. The 18-character field layout

From **SDK v7.5.0, §2.1, Table 2 (pp. 11–12)**, the barcode contains
seven fixed-width fields packed into 18 characters with **no separators**:

| Position (1-indexed) | Field                              | Length | What it is                                                                                                                    |
|---------------------:|------------------------------------|-------:|-------------------------------------------------------------------------------------------------------------------------------|
| 1                    | Bar Code Version Code (VC)         | 1      | Always `"1"` for this layout.                                                                                                 |
| 2–7                  | Person Designator Identifier (PDI) | 6      | Base-32-encoded 9-digit ID. Historically the SSN; on modern cards a synthetic card-identifier starting with `999` (see §4).   |
| 8                    | Person Designator Type Code (PDT)  | 1      | Letter saying what kind of ID the PDI is (Table 25).                                                                          |
| 9–15                 | DoD EDI Person Identifier (EDIPI)  | 7      | Base-32-encoded 10-digit DEERS identifier — the durable, unique person ID.                                                    |
| 16                   | Personnel Category Code (PCC)      | 1      | Letter saying what category of person the cardholder is (Table 27).                                                           |
| 17                   | Branch Code (BC)                   | 1      | Letter or digit identifying branch of service (Table 26).                                                                     |
| 18                   | Card Instance Identifier (CI)      | 1      | Random character distinguishing re-issued cards. Ignore for decoding purposes.                                                |

- Positions are 1-indexed in the spec; in 0-indexed Python those become
  `d[0]`, `d[1:7]`, `d[7]`, `d[8:15]`, `d[15]`, `d[16]`, `d[17]`.
- Length is always exactly 18. Anything else is not a CAC Code 39
  barcode (or the scanner is misconfigured).
- All letters are uppercase — normalise with `.upper()` to be safe.

For just EDIPI + PCC + Branch you only need positions 9–15, 16, and 17.

---

## 2. Base-32 encoding (Appendix B.1)

A 10-digit decimal EDIPI would eat 10 characters of an 18-character
budget. The spec instead writes the EDIPI (and PDI) in **base 32**: 10
decimal digits fit in 7 base-32 digits, 9 fit in 6.

### 2.1 The alphabet

```
Value:   0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
Symbol:  0 1 2 3 4 5 6 7 8 9  A  B  C  D  E  F  G  H  I  J  K  L  M  N  O  P  Q  R  S  T  U  V
```

Digits `0`–`9` are themselves; letters `A`–`V` are 10–31. The letters
`W`, `X`, `Y`, `Z` are **not used**.

> SDK v7.5.0, p. 42: "thirty-two symbols represented by the ten decimal
> digits 0 through 9 and the first twenty-two alphabetic characters A
> through V… A represents the 11th symbol… V represents the 32nd."

This is the standard "extended-hex" base-32 alphabet — and exactly the
alphabet Python's built-in `int(s, 32)` already understands.

### 2.2 In one line of Python

```python
edipi = int(barcode[8:15], 32)        # base-32 → integer
edipi_str = f"{edipi:010d}"           # zero-pad to 10 digits
```

The zero-pad matters: without it a short EDIPI like `0123456789` would
print as `123456789`. Same idea for the PDI: pad to 9 digits.

> Per Table 2 footnotes (p. 12): the 9-digit SSN range `000-00-0000` to
> `999-99-9999` maps to base-32 `000000`–`TPLIFV`; the 10-digit EDIPI
> range `1000000000`–`9999999999` maps to base-32 `0TPLIG0`–`9AONOVV`.

If you want the math by hand: for digits `d₁ d₂ … dₙ` (left to right),
`value = d₁·32^(n-1) + d₂·32^(n-2) + … + dₙ·32^0`. The spec's worked
example (p. 42) converts `V62G` to `(31·32³)+(6·32²)+(2·32)+16 = 1,022,032`.

---

## 3. Lookup tables (Appendix C)

### 3.1 Branch (Service) Codes — Table 26, p. 50

Position 17 of the barcode.

| Code | Branch / Service                |
|:----:|---------------------------------|
| A    | USA (Army)                      |
| C    | USCG (Coast Guard)              |
| D    | DoD                             |
| F    | USAF (Air Force)                |
| H    | USPHS (Public Health Service)   |
| M    | USMC (Marine Corps)             |
| N    | USN (Navy)                      |
| O    | NOAA                            |
| 1    | Foreign Army                    |
| 2    | Foreign Navy                    |
| 3    | Foreign Marine Corps            |
| 4    | Foreign Air Force               |
| X    | Other / Not Applicable          |

### 3.2 Personnel Category Codes — Table 27, p. 51

Position 16 of the barcode.

| Code | Category                                                                |
|:----:|-------------------------------------------------------------------------|
| A    | Active duty member                                                      |
| B    | Presidential Appointee                                                  |
| C    | DoD civil service employee                                              |
| D    | 100% disabled American veteran                                          |
| E    | DoD contract employee                                                   |
| F    | Former member (20-yr active-duty, eligible to retire, chose discharge)  |
| G    | National Guard, mobilised or on active duty 31+ days                    |
| H    | Medal of Honor recipient                                                |
| I    | Non-DoD civil service employee                                          |
| J    | Academy student (excludes OCS)                                          |
| K    | Non-appropriated fund (NAF) DoD employee                                |
| L    | Lighthouse service                                                      |
| M    | Non-Government agency personnel (e.g. American Red Cross)               |
| N    | National Guard, not on active duty or active 30 days or less            |
| O    | Non-DoD contract employee                                               |
| Q    | Reserve retiree not yet eligible for retired pay                        |
| R    | Retired Uniformed Service member eligible for retired pay               |
| S    | Reserve, mobilised or on active duty 31+ days                           |
| T    | Foreign military member                                                 |
| U    | Foreign national employee (DoD or non-DoD)                              |
| V    | Reserve, not on active duty or active 30 days or less                   |
| W    | DoD beneficiary (e.g. former or surviving spouse)                       |
| Y    | Retired DoD Civil Service Employee                                      |

Letters not listed (`P`, `X`, `Z`, …) are undefined and should fall
through to "unknown". `P` appears in the older **Member** Category Code
(TAMP) but not in the modern Personnel Category Code.

Table 25 (PDT codes — `S`=SSN, `N`/`P`/`D`/`F`/`T`/`I` for various
non-SSN identifiers) is in the SDK doc but is not needed for the three
fields above.

---

## 4. A note on the PDI (skip if not interested)

Originally the PDI held the cardholder's real nine-digit SSN in base-32.
The DoD has since stopped putting real SSNs on cards; the PDI now
contains a synthetic card-identifier whose leading three digits are
always `999` (an invalid SSN range), with the remaining six digits
giving 10⁶ unique values per person. The PDT field will still typically
be `S` for legacy compatibility.

---

## 5. Worked end-to-end example

The DoD "Appendix C — Sample Barcodes" document gives:

```
1TOQQG0S14PC0MIAA5
```

Splitting by the field widths from §1:

| Positions | Slice     | Decoded                                              |
|:---------:|-----------|------------------------------------------------------|
| 1         | `1`       | Version code (must be `1`).                          |
| 2–7       | `TOQQG0`  | PDI = `999123456` (synthetic; see §4).               |
| 8         | `S`       | PDT = SSN.                                           |
| 9–15      | `14PC0MI` | EDIPI = **`1234567890`**.                            |
| 16        | `A`       | Personnel Category = **Active duty member**.         |
| 17        | `A`       | Branch = **USA (Army)**.                             |
| 18        | `5`       | Card instance (ignore).                              |

Verify in Python: `int("14PC0MI", 32)` → `1234567890`,
`f"{1234567890:010d}"` → `"1234567890"`.

(Beware: in scanned/OCR copies of the spec the digit `0` is often
misread as the letter `O`. A real scanner hands you the correct
characters.)

---

## 6. References

1. **CAC End-Point Implementation Guide v2.1.1**, DMDC, 2 April 2010.
   <https://www.cac.mil/Portals/53/Documents/CAC_End_Point_Implementation_Guide_v2.1.1(2010.4.2).pdf>
2. **DoD ID Bar Code Formats — SDK v7.5.0**, DMDC, September 2012.
   §2.1 / Table 2 (field layout), Appendix B.1 (base-32), Appendix C
   Tables 25–27 (PDT, Branch, PCC).
   <https://archive.org/details/DoDIDBarCodeSDKFormatsV750Sep2012>
3. **Appendix C — Sample Barcodes (CAC)**, DMDC. Source of the worked
   example `1TOQQG0S14PC0MIAA5`.
   <https://archive.org/details/AppedixCSampleBarcodesCommonAccessCardCAC>
4. **ISO/IEC 16388** — the Code 39 standard. Implemented by your
   scanner; you do not need to read it.
5. **`jkusner/CACBarcode`** on GitHub — a Python reference implementation.
   <https://github.com/jkusner/CACBarcode>
