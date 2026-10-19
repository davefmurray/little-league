#!/usr/bin/env python3
"""Decode the tournament bracket table and generate a 32-team layout.

US table: bank 5, $8941, 15 records x 3 bytes (slotA, slotB, destSlot).
RAM: $0650 slots, $0670 loss counts, $0746 round.

    python3 tools/bracket.py ROM
    python3 tools/bracket.py ROM --gen32
"""
import argparse

HEADER = 16
PRG = 0x4000
TABLE_BANK = 5
TABLE = 0x8941
RECORDS = 15


def file_off(addr, bank=TABLE_BANK):
    return HEADER + bank * PRG + (addr - 0x8000)


def read_table(rom, addr=TABLE, records=RECORDS):
    o = file_off(addr)
    raw = rom[o:o + records * 3]
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


def rounds(records):
    out, i, size = [], 0, 8
    while i < len(records) and size >= 1:
        out.append(records[i:i + size])
        i += size
        size //= 2
    return out


def show(records):
    for r, matches in enumerate(rounds(records)):
        print(f"round {r} ({len(matches)} matches)")
        for a, b, dest in matches:
            print(f"  slot {a:2d} vs {b:2d}  ->  {dest:2d}")


def gen32():
    recs = []
    # round 0: 16 matches, leaves 0-31 -> slots 32-47
    for i in range(16):
        recs.append((i * 2, i * 2 + 1, 32 + i))
    # round 1: 8 matches, 32-47 -> 48-55
    for i in range(8):
        recs.append((32 + i * 2, 32 + i * 2 + 1, 48 + i))
    # round 2: 4 matches, 48-55 -> 56-59
    for i in range(4):
        recs.append((48 + i * 2, 48 + i * 2 + 1, 56 + i))
    # round 3: 2 matches, 56-59 -> 60-61
    for i in range(2):
        recs.append((56 + i * 2, 56 + i * 2 + 1, 60 + i))
    # final: 60 vs 61 -> 62
    recs.append((60, 61, 62))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", nargs="?")
    ap.add_argument("--gen32", action="store_true")
    ap.add_argument("--hex", action="store_true")
    args = ap.parse_args()

    if args.gen32:
        recs = gen32()
        print(f"{len(recs)} records, {len(recs) * 3} bytes")
        if args.hex:
            print(bytes(b for r in recs for b in r).hex(" "))
        else:
            show(recs)
        return

    if not args.rom:
        ap.error("ROM required")
    rom = open(args.rom, "rb").read()
    recs = read_table(rom)
    print(f"{len(recs)} records at ${TABLE:04X}")
    show(recs)


if __name__ == "__main__":
    main()
