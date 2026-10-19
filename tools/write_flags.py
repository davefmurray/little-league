#!/usr/bin/env python3
"""Write the team flag table (bank 4).

Flags: offset table at $975A (16 bytes), records at $976A (12 x tile,attr).
This tool swaps or repoints records. Tile import is a separate step.

    python3 tools/write_flags.py ROM --swap 0 4 -o build/flags-swap.nes
    python3 tools/write_flags.py ROM --set 0 0x48 -o build/flags-usa.nes
    python3 tools/write_flags.py ROM --list
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK = 4
TABLE = 0x975A
RECORDS = 0x976A
RECORD_BYTES = 0x180


def file_off(addr):
    return HEADER + BANK * PRG + (addr - 0x8000)


def load(rom):
    o = file_off(TABLE)
    return bytearray(rom[o:o + 16])


def save(rom, table):
    rom[file_off(TABLE):file_off(TABLE) + 16] = table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--swap", nargs=2, type=int, metavar=("A", "B"))
    ap.add_argument("--set", nargs=2, type=lambda s: int(s, 0), metavar=("TEAM", "OFFSET"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-o", "--out", default="build/flags-written.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    table = load(rom)

    if args.list:
        print(" ".join(f"{t:02d}:{v:02X}" for t, v in enumerate(table)))
        return

    if args.swap:
        a, b = args.swap
        table[a], table[b] = table[b], table[a]

    if args.set:
        team, value = args.set
        if not (0 <= value < RECORD_BYTES and value % 2 == 0):
            raise SystemExit("offset must be even and < 0x180")
        table[team] = value

    save(rom, table)
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: " + " ".join(f"{t:02d}:{v:02X}" for t, v in enumerate(table)))


if __name__ == "__main__":
    main()
