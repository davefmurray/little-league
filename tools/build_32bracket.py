#!/usr/bin/env python3
"""Install a 32-team bracket: table, PRG-RAM state, 32-byte seed.

- 31 records x 3 at fixed $FC00
- seed 0..31 at fixed $FD00
- slots $6800 (63), losses $6840 (32)
- init at $9B5F rewritten to copy the seed and zero losses
- advance/display operands repointed

This is still a prototype: the stock team-select/password flow seeds 16 teams,
so entry into the bracket is not wired yet.

    python3 tools/build_32bracket.py ROM -o build/32bracket.nes
    python3 tools/build_32bracket.py ROM --table-only -o build/32bracket-table.nes
"""
import argparse

HEADER = 16
PRG = 0x4000
TABLE = 0xFC00
SEED = 0xFD00
SLOTS = 0x6800
LOSSES = 0x6840
INIT = 0x9B5F
ADVANCE = 0x9B85
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
    ap.add_argument("--state", action="store_true",
                    help="also install the experimental 32-team PRG-RAM state")
    ap.add_argument("-o", "--out", default="build/32bracket.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    data = bytes(b for r in gen32() for b in r)
    assert len(data) == 93
    rom[fixed_off(TABLE):fixed_off(TABLE) + len(data)] = data

    rom[bank5_off(ADVANCE_OPERAND):bank5_off(ADVANCE_OPERAND) + 2] = \
        TABLE.to_bytes(2, "little")
    rom[bank5_off(DISPLAY_OPERAND):bank5_off(DISPLAY_OPERAND) + 2] = \
        (TABLE + 2).to_bytes(2, "little")

    if args.state:
        rom[fixed_off(SEED):fixed_off(SEED) + 32] = bytes(range(32))

        # LDX #0 / LDA seed,X / STA slots,X / LDA #0 / STA losses,X / INX /
        # CPX #32 / BNE loop / JMP advance
        init = bytes([
            0xA2, 0x00,
            0xBD, SEED & 0xFF, SEED >> 8,
            0x9D, SLOTS & 0xFF, SLOTS >> 8,
            0xA9, 0x00,
            0x9D, LOSSES & 0xFF, LOSSES >> 8,
            0xE8,
            0xE0, 0x20,
            0xD0, 0xF0,
            0x4C, ADVANCE & 0xFF, ADVANCE >> 8,
        ])
        rom[bank5_off(INIT):bank5_off(INIT) + len(init)] = init

        for addr in (0x9BA7, 0x9BB3, 0x9C0C):
            rom[bank5_off(addr):bank5_off(addr) + 2] = SLOTS.to_bytes(2, "little")
        rom[bank5_off(0x9BAB):bank5_off(0x9BAB) + 2] = LOSSES.to_bytes(2, "little")
        rom[bank5_off(0x9C12):bank5_off(0x9C12) + 2] = (SLOTS + 1).to_bytes(2, "little")

    open(args.out, "wb").write(rom)
    mode = "table + PRG-RAM state" if args.state else "table only (safe default)"
    print(f"wrote {args.out}: {mode}; seed ${SEED:04X}, slots ${SLOTS:04X}, "
          f"losses ${LOSSES:04X}")


if __name__ == "__main__":
    main()
