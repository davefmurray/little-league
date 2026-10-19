#!/usr/bin/env python3
"""Install the 32-team bracket table (table/pointer step).

31 records x 3 bytes at fixed-bank $FC00. Repoints the two readers:
  $9BA4 operand (advance)  -> $FC00
  $9C09 operand (display)  -> $FC02

RAM/init changes are NOT included yet: slots still live at $0650 and the seed
is still 16 packed nibbles, so this build boots but does not yet play a
32-team bracket.

    python3 tools/build_32bracket.py ROM -o build/32bracket.nes
"""
import argparse

HEADER = 16
PRG = 0x4000
TABLE = 0xFC00
ADVANCE_OPERAND = 0x9BA4
DISPLAY_OPERAND = 0x9C09


def gen32():
    recs = []
    for i in range(16):
        recs.append((i * 2, i * 2 + 1, 32 + i))
    for i in range(8):
        recs.append((32 + i * 2, 32 + i * 2 + 1, 48 + i))
    for i in range(4):
        recs.append((48 + i * 2, 48 + i * 2 + 1, 56 + i))
    for i in range(2):
        recs.append((56 + i * 2, 56 + i * 2 + 1, 60 + i))
    recs.append((60, 61, 62))
    return recs


def bank5_off(addr):
    return HEADER + 5 * PRG + (addr - 0x8000)


def fixed_off(addr):
    return HEADER + 7 * PRG + (addr - 0xC000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/32bracket.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    recs = gen32()
    data = bytes(b for r in recs for b in r)
    assert len(data) == 93

    rom[fixed_off(TABLE):fixed_off(TABLE) + len(data)] = data

    rom[bank5_off(ADVANCE_OPERAND):bank5_off(ADVANCE_OPERAND) + 2] = \
        TABLE.to_bytes(2, "little")
    rom[bank5_off(DISPLAY_OPERAND):bank5_off(DISPLAY_OPERAND) + 2] = \
        (TABLE + 2).to_bytes(2, "little")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: 31 records at ${TABLE:04X}; "
          f"advance -> ${TABLE:04X}, display -> ${TABLE + 2:04X}")


if __name__ == "__main__":
    main()
