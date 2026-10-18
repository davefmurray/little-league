#!/usr/bin/env python3
"""Pack data/teams32.json into bank 9 of the 32-team build.

Layout (bank 9, CPU $8000):
  $8000  32 x 4   code (3 chars + 0)
  $8080  32 x 16  name (14 chars + FF FF)
  $8280  32 x 1   region (0 ASIA, 1 AMERICA, 2 EUROPE, 3 HAWAII, 4 NEW)

    python3 tools/pack_team_table.py build/32x20.nes data/teams32.json -o build/32x20-ui.nes
"""
import argparse
import json

HEADER = 16
BANK = 0x4000
BANK_NO = 9
BASE = 0x8000
REGIONS = {"ASIA": 0, "AMERICA": 1, "EUROPE": 2, "HAWAII": 3, "NEW": 4}


def bank_file(bank):
    return HEADER + bank * BANK


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("teams")
    ap.add_argument("-o", "--out", default="build/32x20-ui.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    if rom[4] < BANK_NO + 1:
        raise SystemExit(f"ROM has {rom[4]} PRG banks; need at least {BANK_NO + 1}")
    doc = json.load(open(args.teams))
    teams = doc["teams"]
    if len(teams) != 32:
        raise SystemExit(f"expected 32 teams, got {len(teams)}")

    base = bank_file(BANK_NO, ) + (BASE - 0x8000)
    codes = bytearray(32 * 4)
    names = bytearray(32 * 16)
    regions = bytearray(32)
    for t in teams:
        i = t["id"]
        code = t["code"].encode("ascii")[:3].ljust(4, b"\x00")
        codes[i * 4:i * 4 + 4] = code
        name = t["name"].encode("ascii")[:14].ljust(14, b" ") + b"\xff\xff"
        names[i * 16:i * 16 + 16] = name
        regions[i] = REGIONS[t["region"]]

    rom[base:base + len(codes)] = codes
    rom[base + 0x80:base + 0x80 + len(names)] = names
    rom[base + 0x280:base + 0x280 + len(regions)] = regions
    open(args.out, "wb").write(rom)

    print(f"wrote {args.out}")
    print(f"  bank {BANK_NO}: codes ${BASE:04X}, names ${BASE + 0x80:04X}, "
          f"regions ${BASE + 0x280:04X}")
    for t in teams[:4] + teams[28:]:
        print(f"  {t['id']:02d} {t['code']} {t['name'][:14]:14s} {t['region']}")


if __name__ == "__main__":
    main()
