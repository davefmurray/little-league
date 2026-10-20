#!/usr/bin/env python3
"""P4: replace the bracket's 16 placeholder team codes with the real 32.

    python3 tools/build_bracket_codes32.py build/_32full/step4.nes \
        -o build/_32full/step5.nes

The bracket code table is bank 11 $B000, 32 x 4 bytes (3-char code + space).
Teams 16-31 are "T17".."T32" in the stock/early build; digits do not exist
in the bracket font, so they render as garbage tiles. This writes the real
codes from data/teams32.json (AUS, CUB, DOM, ...).
"""
import argparse
import json

HEADER = 16
PRG = 0x4000
BANK11 = 11
TABLE = 0xB000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--teams", default="data/teams32.json")
    ap.add_argument("-o", "--out", default="build/direct31-codes.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    doc = json.load(open(args.teams))
    teams = doc["teams"]
    if len(teams) != 32:
        raise SystemExit(f"expected 32 teams, got {len(teams)}")

    o = HEADER + BANK11 * PRG + (TABLE - 0x8000)
    for team in teams:
        code = team["code"].upper()
        if not (2 <= len(code) <= 3) or not code.isalpha():
            raise SystemExit(f"team {team['id']}: bad code {code!r}")
        rom[o + team["id"] * 4:o + team["id"] * 4 + 4] = code.ljust(4).encode("ascii")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: bracket codes 0-31 at bank11 ${TABLE:04X}")


if __name__ == "__main__":
    main()
