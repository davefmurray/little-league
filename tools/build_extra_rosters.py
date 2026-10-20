#!/usr/bin/env python3
"""Write the generated teams 16-31 into bank 8 of a 32-team build.

    python3 tools/build_extra_rosters.py build/32x20.nes data/roster32.json \
        -o build/32x20-extra.nes

`build_32x20.py` clones team 15 for teams 16-31.  This overwrites those
blocks with the 20 generated players and a 48-byte trailer (three pitcher
records) per team. The bank-8 pointer table already points at these blocks.
"""
import argparse
import json
import random

HEADER = 16
BANK = 0x4000
PLAYERS = 20
RECORD = 16
STRIDE = PLAYERS * RECORD + 48


def block_for(team, rng):
    if len(team["players"]) != PLAYERS:
        raise SystemExit(f"{team['name']}: {len(team['players'])} players, expected {PLAYERS}")
    out = bytearray()
    for p in team["players"]:
        name = p["name"].upper()[:6].ljust(6).encode("ascii")
        attrs = bytes(p["attrs"])
        if len(attrs) != 10:
            raise SystemExit(f"{team['name']}/{p['name']}: need 10 attrs")
        out += name + attrs
    # Trailer: FF row, 8 zeros, three 8-byte pitcher records.
    trailer = bytearray(b"\xff" * 16 + b"\x00" * 8)
    for slot in range(3):
        skill = team["players"][slot]["attrs"][5]
        trailer += bytes([
            rng.choice([0, 1, 2, 128, 129, 130]),
            rng.randint(0x31, 0xFF),
            rng.randint(0x18, 0xFD),
            rng.randint(0x00, 0x0F),
            0, 0,
            skill,
            rng.choice([0, 2]),
        ])
    out += trailer
    assert len(out) == STRIDE, len(out)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="build/32x20.nes from build_32x20.py")
    ap.add_argument("roster", help="data/roster32.json")
    ap.add_argument("-o", "--out", default="build/32x20-extra.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    doc = json.load(open(args.roster))
    if len(doc["teams"]) != 32:
        raise SystemExit(f"roster has {len(doc['teams'])} teams, expected 32")
    if rom[4] != 16:
        raise SystemExit(f"expected 16 PRG banks, found {rom[4]}")

    for tid in range(16, 32):
        block = block_for(doc["teams"][tid], random.Random(0xB8B80000 + tid))
        off = HEADER + 8 * BANK + tid * STRIDE
        rom[off:off + STRIDE] = block
        print(f"team {tid:02d} {doc['teams'][tid]['name']:<14} "
              f"${0x8000 + tid * STRIDE:04X}")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: teams 16-31 rosters")


if __name__ == "__main__":
    main()
