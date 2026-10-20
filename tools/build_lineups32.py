#!/usr/bin/env python3
"""P3: 32-entry lineup table.

    python3 tools/build_lineups32.py build/direct27.nes -o build/direct28.nes

The stock lineup table is 16 x 9 bytes at bank4 $96CA; the only reader is
bank4 $AD4E `LDA $96CA,Y` with Y = team*9. Build a 32 x 9 table in the
fixed bank at $FD80 (always mapped), copy the original 16 entries, append a
default 9-batter order for teams 16-31, and repoint the reader.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK4 = 4
FIXED = 15
OLD = 0x96CA
NEW = 0xFD80
READER = 0xAD4E
DEFAULT = bytes([0x08, 0x16, 0x29, 0x31, 0x42, 0x57, 0x65, 0x73, 0x84])


def off(bank, addr):
    base = 0xC000 if bank == FIXED else 0x8000
    return HEADER + bank * PRG + (addr - base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct27.nes")
    ap.add_argument("-o", "--out", default="build/direct28.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    o = off(BANK4, OLD)
    table = bytearray(rom[o:o + 16 * 9])
    for t in range(16, 32):
        table += DEFAULT

    o = off(FIXED, NEW)
    if bytes(rom[o:o + len(table)]).count(0xFF) != len(table):
        raise SystemExit(f"fixed ${NEW:04X} is not free")
    rom[o:o + len(table)] = table

    o = off(BANK4, READER)
    if bytes(rom[o:o + 3]) != bytes([0xB9, 0xCA, 0x96]):
        raise SystemExit(f"bank4 ${READER:04X}: expected B9 CA 96, "
                         f"found {rom[o:o+3].hex(' ')}")
    rom[o:o + 3] = bytes([0xB9, NEW & 0xFF, NEW >> 8])

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: lineups ${NEW:04X} (32 x 9), reader -> ${NEW:04X}")


if __name__ == "__main__":
    main()
