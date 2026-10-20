#!/usr/bin/env python3
"""P3: 32-entry team ratings table (POWER ANALYSIS bars).

    python3 tools/build_ratings32.py build/direct26.nes -o build/direct27.nes

The stock table is 16 x 4 bytes at bank3 $B224; the only reader is
bank3 $AFE3 `LDA $B224,Y`. Build a 32 x 4 table at bank3 $BC80 (a free
$BC61..$BDB7 run), copy the original 16 entries, append the 16 generated
teams' ratings from data/roster32.json, and repoint the reader.
"""
import argparse
import json

HEADER = 16
PRG = 0x4000
BANK = 3
BASE = 0x8000
OLD = 0xB224
NEW = 0xBC80
READER = 0xAFE2


def off(addr):
    return HEADER + BANK * PRG + (addr - BASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct26.nes")
    ap.add_argument("--roster", default="data/roster32.json")
    ap.add_argument("-o", "--out", default="build/direct27.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    doc = json.load(open(args.roster))
    if len(doc["teams"]) != 32:
        raise SystemExit(f"roster has {len(doc['teams'])} teams, expected 32")

    o = off(OLD)
    table = bytearray(rom[o:o + 64])
    for t in range(16, 32):
        ratings = doc["teams"][t]["ratings"]
        if len(ratings) != 4 or any(not 1 <= v <= 4 for v in ratings):
            raise SystemExit(f"team {t}: bad ratings {ratings}")
        table += bytes(ratings)

    o = off(NEW)
    if bytes(rom[o:o + len(table)]).count(0xFF) != len(table):
        raise SystemExit(f"bank3 ${NEW:04X} is not free")
    rom[o:o + len(table)] = table

    o = off(READER)
    if bytes(rom[o:o + 3]) != bytes([0xB9, 0x24, 0xB2]):
        raise SystemExit(f"bank3 ${READER:04X}: expected B9 24 B2, "
                         f"found {rom[o:o+3].hex(' ')}")
    rom[o:o + 3] = bytes([0xB9, NEW & 0xFF, NEW >> 8])

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: ratings table ${NEW:04X}, reader -> ${NEW:04X}")


if __name__ == "__main__":
    main()
