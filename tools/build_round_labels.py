#!/usr/bin/env python3
"""P4: replace the static bracket title with a live round label.

    python3 tools/build_round_labels.py build/direct20.nes -o build/direct25.nes

The title run at $2068 has 14 text bytes at display-list offset 37 (buffer
$0325).  A new bank11 routine at $8440 selects one of five 14-char strings
from $84A0 by the match index $07FC:

    0-15  "ROUND 1  R32  "
    16-23 "ROUND 2  R16  "
    24-27 "ROUND 3  QF   "
    28-29 "ROUND 4  SF   "
    30-31 "ROUND 5  FINAL"

and copies it to $0325 before the bracket flush.  The draw tail at $8077
becomes JSR $8440 / JSR $83D0 (the WIN-line routine) / NOP.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK = 11
BASE = 0x8000

STRINGS = [
    b"ROUND 1  R32  ",
    b"ROUND 2  R16  ",
    b"ROUND 3  QF   ",
    b"ROUND 4  SF   ",
    b"ROUND 5  FINAL",
    b"CHAMPION      ",
]
assert all(len(s) == 14 for s in STRINGS)

ROUND_OFF = [0] * 16 + [14] * 8 + [28] * 4 + [42] * 2 + [56] + [70]

CODE = bytes([
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0xAA,                   # TAX
    0xBD, 0x00, 0x85,       # LDA $8500,X
    0xA8,                   # TAY
    0xA2, 0x00,             # LDX #$00
    0xB9, 0xA0, 0x84,       # LDA $84A0,Y
    0x9D, 0x25, 0x03,       # STA $0325,X
    0xC8,                   # INY
    0xE8,                   # INX
    0xE0, 0x0E,             # CPX #14
    0xD0, 0xF4,             # BNE $844A
    0x60,                   # RTS
])


def off(addr):
    return HEADER + BANK * PRG + (addr - BASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct20.nes (WIN-line build)")
    ap.add_argument("-o", "--out", default="build/direct25.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())

    o = off(0x8077)
    old = bytes(rom[o:o + 7])
    if old != bytes([0x20, 0xD0, 0x83, 0xEA, 0xEA, 0xEA, 0xEA]):
        raise SystemExit(f"$8077: expected WIN tail, found {old.hex(' ')}")
    rom[o:o + 7] = bytes([0x20, 0x40, 0x84, 0x20, 0xD0, 0x83, 0xEA])

    o = off(0x8440)
    if bytes(rom[o:o + len(CODE)]).count(0xFF) != len(CODE):
        raise SystemExit(f"$8440 is not free: {rom[o:o+16].hex(' ')}")
    rom[o:o + len(CODE)] = CODE

    strings = b"".join(STRINGS)
    o = off(0x84A0)
    rom[o:o + len(strings)] = strings
    o = off(0x8500)
    rom[o:o + 32] = bytes(ROUND_OFF)

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: round label routine $8440, strings $84A0")


if __name__ == "__main__":
    main()
