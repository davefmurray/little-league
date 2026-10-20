#!/usr/bin/env python3
"""P4: move the bracket header/title down one row so they are not clipped.

    python3 tools/build_top_row.py build/direct25.nes -o build/direct26.nes

The display list starts with:
    offset 0:  $2048  "R32 R16 QF SF ..."   (row 2)
    offset 35: $2068  "ROUND 1  R32 ..."    (row 3)

The NES/romdev view crops the top 8 pixels, so row 2 is partly cut. Move
both runs to rows 3/4 ($2068/$2088); the team grid starts at row 5, so
nothing overlaps.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK = 11
BASE = 0x8000


def off(addr):
    return HEADER + BANK * PRG + (addr - BASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct25.nes (round-label build)")
    ap.add_argument("-o", "--out", default="build/direct26.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    o = off(0xB200)
    if bytes(rom[o:o + 3]) != bytes([0x20, 0x48, 0x52]):
        raise SystemExit(f"header run: expected 20 48 52, found {rom[o:o+3].hex(' ')}")
    rom[o + 1] = 0x68                      # $2048 -> $2068

    o = off(0xB200 + 35)
    if bytes(rom[o:o + 3]) != bytes([0x20, 0x68, 0x33]):
        raise SystemExit(f"title run: expected 20 68 33, found {rom[o:o+3].hex(' ')}")
    rom[o + 1] = 0x88                      # $2068 -> $2088

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: header -> $2068, title -> $2088")


if __name__ == "__main__":
    main()
