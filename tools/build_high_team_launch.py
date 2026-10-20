#!/usr/bin/env python3
"""P1 diagnostic: map bracket ids >= $10 to $00-$0F for the stock launch.

    python3 tools/build_high_team_launch.py build/direct18.nes -o build/direct19.nes

Teams 16-31 still have placeholder roster/name data, and the stock game
dies at scene $10 on the first high-team pairing (match 8).  The P1 state
machine does not need those teams' content: keep the real ids in $7700,
but mask the two ids handed to the stock game:

    $07FA = $7700[2m] & $0F
    $07FB = $7700[2m+1] & $0F

The winning side is preserved, so the score-winner routine at $83A0 still
reads the real pair from $7700 and writes the real team id to $7720+m.
This is a diagnostic P1 build, not the content-correct shipping path.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK11 = 11
FIXED = 15

PAIR_OLD = bytes([
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0x0A,                   # ASL A
    0xAA,                   # TAX
    0xBD, 0x00, 0x77,       # LDA $7700,X
    0x8D, 0xFA, 0x07,       # STA $07FA
    0xBD, 0x01, 0x77,       # LDA $7701,X
    0x8D, 0xFB, 0x07,       # STA $07FB
    0x4C, 0x00, 0x83,       # JMP $8300
])

PAIR_NEW = bytes([
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0x0A,                   # ASL A
    0xAA,                   # TAX
    0xBD, 0x00, 0x77,       # LDA $7700,X
    0x29, 0x0F,             # AND #$0F
    0x8D, 0xFA, 0x07,       # STA $07FA
    0xBD, 0x01, 0x77,       # LDA $7701,X
    0x29, 0x0F,             # AND #$0F
    0x8D, 0xFB, 0x07,       # STA $07FB
    0x4C, 0x00, 0x83,       # JMP $8300
])


def bank_off(bank, addr):
    base = 0xC000 if bank == FIXED else 0x8000
    return HEADER + bank * PRG + (addr - base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct18.nes (score-winner build)")
    ap.add_argument("-o", "--out", default="build/direct19.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    off = bank_off(BANK11, 0x8360)
    old = bytes(rom[off:off + len(PAIR_OLD)])
    if old != PAIR_OLD:
        raise SystemExit(
            f"bank11 $8360: expected score-winner pairing, found {old.hex(' ')}")
    rom[off:off + len(PAIR_NEW)] = PAIR_NEW
    print(f"bank11 $8360: launch pair masked with AND #$0F "
          f"({len(PAIR_NEW)} bytes)")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
