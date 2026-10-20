#!/usr/bin/env python3
"""Divert the first scene-13 entry to the bracket, then run the stock handler.

    python3 tools/build_scene13_hook.py build/_32full/step8.nes \
        --cursor 16 --match 8 -o build/direct31-scene13hook.nes

The stock team select sets the series/order state; patching the scene-13
handler table entry to $FEA0 lets the bracket appear once.  The bracket A
re-enters scene 13; the stub then maps bank 5 and jumps to the stock
password/matchup handler ($9958) with the stock state intact.
"""
import argparse

HEADER = 16
PRG = 0x4000
TRAMP = 0xFEA0
TABLE_13 = 0xCC79          # $CC53 + 2*$13


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--cursor", type=lambda s: int(s, 0), default=16)
    ap.add_argument("--match", type=lambda s: int(s, 0), default=8)
    ap.add_argument("-o", "--out", default="build/direct31-scene13hook.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    code = bytes([
        0xAD, 0xF0, 0x07,        # LDA $07F0
        0xD0, 0x1C,              # BNE stock
        0xA9, 0x01,              # LDA #1
        0x8D, 0xF0, 0x07,        # STA $07F0
        0xA9, 0xF0,              # LDA #$F0
        0xA2, 0x00,              # LDX #0
        0x9D, 0x00, 0x02,        # STA $0200,X
        0xE8,                    # INX
        0xD0, 0xFA,              # BNE
        0xA9, args.match & 0xFF, # LDA #match
        0x8D, 0xFC, 0x07,        # STA $07FC
        0xA9, 0x0B,              # LDA #11
        0x20, 0x4E, 0xC1,        # JSR $C14E
        0x4C, 0x00, 0x80,        # JMP $8000
        0xA9, 0x05,              # stock: LDA #5
        0x20, 0x4E, 0xC1,        # JSR $C14E
        0x4C, 0x58, 0x99,        # JMP $9958
    ])
    fixed = HEADER + 15 * PRG + (TRAMP - 0xC000)
    if rom[fixed:fixed + len(code)].count(0xFF) != len(code):
        raise SystemExit(f"${TRAMP:04X} is not free")
    rom[fixed:fixed + len(code)] = code

    o = HEADER + 15 * PRG + (TABLE_13 - 0xC000)
    if rom[o:o + 2] != bytes([0x99, 0x58]):
        raise SystemExit(f"scene 13 table: expected $5899, found {rom[o:o+2].hex(' ')}")
    rom[o:o + 2] = bytes([TRAMP & 0xFF, TRAMP >> 8])

    if args.cursor:
        o = HEADER + 11 * PRG + (0x8100 - 0x8000)
        if rom[o:o + 5] != bytes([0xA9, 0x00, 0x8D, 0xC7, 0x07]):
            raise SystemExit(f"$8100: unexpected cursor init {rom[o:o+5].hex(' ')}")
        rom[o + 1] = args.cursor & 0xFF

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: scene13 -> ${TRAMP:04X}, cursor={args.cursor}, match={args.match}")


if __name__ == "__main__":
    main()
