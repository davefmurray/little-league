#!/usr/bin/env python3
"""Bound the matchup label, flag and uniform-palette readers on teamnames32.

    python tools/build_visualtables32.py build/teamnames32.nes -o build/visualtables32.nes

The mapping temporarily stores the donor in $05 before producing $04/$05.
Its intermediate write trace differs; the low-team final contract is exact.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from build_bank11 import assemble
from build_teamnames32 import (
    BANK, HEADER, PROTECTED_SHA256 as PRIOR_SHA256, ROM_SIZE, ROOT, off,
    protect_output as protect_prior_output,
)

BASE_SHA256 = "5998632da930ec063ea3029320a2b5d901043baa662add8adb8d14b809633f5c"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
ROUND_BLOCK = 0xBE00
FLAG_HELPER = 0x9B00
PALETTE_POINTER = 0xFFF4
PALETTES = 0xFAC0
PALETTE_BYTES = bytes.fromhex(
    "05 20 0F 26 20 38 02 22 38 1B 2B 0F 12 20 0F 15 11 38 "
    "11 15 38 00 10 38 14 12 0F 15 15 0F 15 25 0F 05 26 0F "
    "18 28 38 11 31 0F 09 27 38 0A 2B 38"
)
STAGE_STARTS = (0, 16, 24, 28, 30)
STOCK_LABELS = (
    ("1ST ROUND", 0x9C56, 0x9C78),
    ("QUARTER FINALS", 0x9C5C, 0x9C84),
    ("SEMI FINALS", 0x9C62, 0x9C95),
    ("FINALS", 0x9C50, 0x9CA3),
)


@dataclass(frozen=True)
class Region:
    name: str
    bank: int
    start: int
    end: int


REGIONS = (
    Region("round-entry", 5, 0x9C42, 0x9C45),
    Region("round-block", 5, ROUND_BLOCK, 0xBE80),
    Region("flag-entry", 15, 0xCB63, 0xCB66),
    Region("flag-helper", 4, FLAG_HELPER, 0x9B40),
    Region("palette-mapping", 15, 0xC6FE, 0xC713),
)


@dataclass(frozen=True)
class Change:
    name: str
    bank: int
    addr: int
    before: bytes
    after: bytes


def word(addr):
    return addr.to_bytes(2, "little")


def read(rom, bank, addr, size):
    start = off(bank, addr)
    return rom[start:start + size]


def round_block():
    record = b"\xC6\xA1" + b"2ND ROUND\xFF"
    second = ROUND_BLOCK + len(record)
    stub = b"\x20\x40\xC8" + word(ROUND_BLOCK) + b"\x60"
    entry = second + len(stub)
    code, _ = assemble([
        "PHP", "PHA", "LDA $07ED", "BEQ stock",
        "LDA $07EF", "CMP #$32", "BNE stock", "PLA", "PLP",
        "LDA $07FC", "CMP #$10", "BCC first",
        "CMP #$18", f"BCC ${second:04X}",
        "CMP #$1C", "BCC quarter", "CMP #$1E", "BCC semi", "JMP $9C50",
        "first:", "JMP $9C56", "quarter:", "JMP $9C5C", "semi:", "JMP $9C62",
        "stock:", "PLA", "PLP", "LDX $0746", "JMP $9C45",
    ], entry)
    return record + stub + code, entry


def flag_helper():
    # $00 is 3 at $CB56 and 4 at $CB52. Hide the complete old footprint.
    return assemble([
        "CPX #$10", "BCS omit", "LDY $975A,X", "JMP $CB66",
        "omit:", "LDX $047F",
        "row:", "LDY #$0C", "LDA #$F0",
        "fill:", "STA $0200,X", "INX", "DEY", "BNE fill",
        "LDA $04", "CLC", "ADC #$08", "STA $04", "DEC $00", "BNE row",
        "STY $01", "JMP $CB9D",
    ], FLAG_HELPER)[0]


def palette_mapping():
    # The guarded $FFF4 pointer is $FAC0. Its 16 records end at $FAEF.
    return assemble([
        "LDA $04EF,Y", "AND #$0F", "STA $05", "ASL A", "ADC $05",
        "ADC #$C0", "STA $04", "LDY #$00", "LDA #$FA", "STA $05", "RTS",
    ], 0xC6FE)[0]


def change_manifest(base):
    checks = [
        (15, PALETTE_POINTER, word(PALETTES)),
        (15, PALETTES, PALETTE_BYTES),
        (15, 0xCB52, bytes.fromhex("A9 04 D0 02 A9 03 85 00 A5 27 85 2E A9 04 20 4E C1")),
        (15, 0xCB66, bytes.fromhex("AE 7F 04 A9 03 85 01")),
        (15, 0xCB9D, bytes.fromhex("A5 2E 4C 4E C1")),
        (5, 0x9C45, bytes.fromhex("BC 68 9C F0 0C 88 F0 0F 88 F0 12")),
        (5, 0x9C68, bytes([0] * 8 + [1] * 4 + [2] * 2 + [3] * 2)),
        (11, 0x8500, bytes([0] * 16 + [14] * 8 + [28] * 4 + [42] * 2 + [56])),
    ]
    for text, stub, record in STOCK_LABELS:
        checks.extend((
            (5, stub, b"\x20\x40\xC8" + word(record) + b"\x60"),
            (5, record, b"\xC6\xA1" + text.encode("ascii") + b"\xFF"),
        ))
    for bank, addr, expected in checks:
        if read(base, bank, addr, len(expected)) != expected:
            raise ValueError(f"bank{bank} ${addr:04X}: unexpected reader or table bytes")

    block, entry = round_block()
    flags, palettes = flag_helper(), palette_mapping()
    return (
        Change("round-entry", 5, 0x9C42, bytes.fromhex("AE 46 07"), b"\x4C" + word(entry)),
        Change("round-block", 5, ROUND_BLOCK, b"\xFF" * len(block), block),
        Change("flag-entry", 15, 0xCB63, bytes.fromhex("BC 5A 97"), b"\x4C" + word(FLAG_HELPER)),
        Change("flag-helper", 4, FLAG_HELPER, b"\xFF" * len(flags), flags),
        Change("palette-mapping", 15, 0xC6FE,
               bytes.fromhex("B9 EF 04 0A 79 EF 04 6D F4 FF 85 04 A9 00 A8 6D F5 FF 85 05 60"),
               palettes),
    )


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected teamnames32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned teamnames32")
    regions = {r.name: r for r in REGIONS}
    rom, claimed, names = bytearray(base), set(), set()
    for c in change_manifest(base):
        region = regions.get(c.name)
        if (region is None or c.name in names or c.bank != region.bank
                or not c.after or len(c.before) != len(c.after)
                or not region.start <= c.addr < c.addr + len(c.after) <= region.end):
            raise ValueError(f"{c.name}: overlapping, invalid or unowned change")
        start = off(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        if claimed & span:
            raise ValueError(f"{c.name}: overlapping change")
        if base[start:start + len(c.before)] != c.before:
            raise ValueError(f"bank{c.bank} ${c.addr:04X}: unexpected input bytes")
        claimed.update(span)
        names.add(c.name)
        rom[start:start + len(c.after)] = c.after
    if names != set(regions):
        raise ValueError("incomplete visual-table manifest")
    return bytes(rom)


def diff_manifest(base, rom):
    return {
        "input_sha256": hashlib.sha256(base).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "ranges": [
            {"name": c.name, "bank": c.bank, "address": c.addr,
             "file_offset": off(c.bank, c.addr), "before": c.before.hex(), "after": c.after.hex(),
             "changed_file_offsets": [off(c.bank, c.addr) + i for i, (a, b)
                                      in enumerate(zip(c.before, c.after)) if a != b]}
            for c in change_manifest(base)
        ],
    }


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    protected = [ROOT / "build/teamnames32.nes", source.resolve().parent / "teamnames32.nes"]
    protected.extend((ROOT / "data").glob("*"))
    for path in protected:
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise ValueError(f"output aliases protected input {path}")
    if output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() in PROTECTED_SHA256:
        raise ValueError("output aliases protected input ROM artifact")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        base = args.rom.read_bytes()
        rom = build_rom(base)
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
