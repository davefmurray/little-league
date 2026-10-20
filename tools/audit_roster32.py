#!/usr/bin/env python3
"""Audit the 32-team bank-8 roster blocks.

    python3 tools/audit_roster32.py build/32x20-extra.nes

For teams 16-31 check: 20 printable player records, exactly three pitcher
slots (08/10/18), and the 48-byte trailer (FF*16, 00*8, three 8-byte
pitcher records).
"""
import argparse

HEADER = 16
BANK = 0x4000
BANK8 = 8
PLAYERS = 20
RECORD = 16
STRIDE = PLAYERS * RECORD + 48


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    args = ap.parse_args()
    rom = open(args.rom, "rb").read()
    if rom[4] != 16:
        raise SystemExit(f"expected 16 PRG banks, found {rom[4]}")

    for tid in range(16, 32):
        off = HEADER + BANK8 * BANK + tid * STRIDE
        block = rom[off:off + STRIDE]
        if len(block) != STRIDE:
            raise SystemExit(f"team {tid}: truncated block")
        slots = []
        names = []
        for p in range(PLAYERS):
            rec = block[p * RECORD:(p + 1) * RECORD]
            name = rec[:6]
            if not all(0x20 <= b < 0x7F for b in name):
                raise SystemExit(f"team {tid} player {p}: non-printable name {name!r}")
            names.append(name.decode("ascii").strip())
            if rec[12] in (8, 16, 24):
                slots.append(rec[12])
        if sorted(slots) != [8, 16, 24]:
            raise SystemExit(f"team {tid}: pitcher slots {slots}, expected 8/16/24")
        trailer = block[PLAYERS * RECORD:]
        if trailer[:16] != b"\xff" * 16 or trailer[16:24] != b"\x00" * 8:
            raise SystemExit(f"team {tid}: bad trailer header")
        for k in range(3):
            rec = trailer[24 + k * 8:24 + (k + 1) * 8]
            if len(rec) != 8:
                raise SystemExit(f"team {tid}: short pitcher record {k}")
        print(f"team {tid:02d}: 20 players, pitchers 08/10/18, "
              f"first={names[0]:<6} last={names[-1]:<6}")

    print("audit OK: 16 x (20 players + 3 pitcher records)")


if __name__ == "__main__":
    main()
