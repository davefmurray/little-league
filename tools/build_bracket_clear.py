#!/usr/bin/env python3
"""P1: clear the nametable before the bracket draw.

    python3 tools/build_bracket_clear.py build/direct31.nes -o build/direct31-clear.nes

The bracket draw at bank11 $8000 turns the PPU off and writes its display
list, but never clears the nametable. After a game, the box-score rows remain
in the gaps between the bracket runs. This replaces the draw's
`LDA #$1E / JSR $C102` with a fixed-bank helper that does the same MMC1
control write and then fills the 1 KB nametable with tile $00.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK11 = 11
FIXED = 15
DRAW = 0x800D
HELPER = 0xFED0
ORIG = bytes([0xA9, 0x1E, 0x20, 0x02, 0xC1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/direct31-clear.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    o = HEADER + BANK11 * PRG + (DRAW - 0x8000)
    if bytes(rom[o:o + len(ORIG)]) != ORIG:
        raise SystemExit(f"$800D: expected {ORIG.hex(' ')}, found {rom[o:o+5].hex(' ')}")
    rom[o:o + 5] = bytes([0x20, HELPER & 0xFF, HELPER >> 8, 0xEA, 0xEA])

    helper = bytes([
        0xA9, 0x1E,             # LDA #$1E
        0x20, 0x02, 0xC1,       # JSR $C102
        0xA9, 0x20,             # LDA #$20
        0x8D, 0x06, 0x20,       # STA $2006
        0xA9, 0x00,             # LDA #$00
        0x8D, 0x06, 0x20,       # STA $2006
        0xA2, 0x04,             # LDX #$04
        0xA9, 0x00,             # LDA #$00 (blank tile)
        0xA0, 0x00,             # LDY #$00
        0x8D, 0x07, 0x20,       # STA $2007
        0xC8,                   # INY
        0xD0, 0xFA,             # BNE $FEE5
        0xCA,                   # DEX
        0xD0, 0xF5,             # BNE $FEDF
        0x60,                   # RTS
    ])
    o = HEADER + FIXED * PRG + (HELPER - 0xC000)
    if bytes(rom[o:o + len(helper)]).count(0xFF) != len(helper):
        raise SystemExit(f"${HELPER:04X} is not free")
    rom[o:o + len(helper)] = helper
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: bracket nametable clear at ${HELPER:04X}")


if __name__ == "__main__":
    main()
