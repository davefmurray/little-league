#!/usr/bin/env python3
"""Hook the team-select scene (0D) to the bank-11 bracket screen.

    python3 tools/build_bracket_entry.py build/direct31.nes -o build/direct31-bracket.nes

Stock scene-0D handler is bank2 `$B9C0`. Replace it with `JMP $FF20`; the
fixed trampoline maps bank 11 and jumps to the bracket draw at `$8000`.
The bracket's A handoff returns to the scene dispatcher with `$07FF=$B0`,
which the launch bridge consumes.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK2 = 2
SCENE0D = 0xB9C0
STOCK = bytes([0x20, 0xB7, 0xB9])          # JSR $B9B7
TRAMP = 0xFEA0
OAM_CLEAR = bytes([
    0xA9, 0xF0,              # LDA #$F0
    0xA2, 0x00,              # LDX #$00
    0x9D, 0x00, 0x02,        # STA $0200,X
    0xE8,                    # INX
    0xD0, 0xFA,              # BNE loop
])
BANK_JUMP = bytes([0xA9, 0x0B, 0x20, 0x4E, 0xC1, 0x4C, 0x00, 0x80])
CODE = OAM_CLEAR + BANK_JUMP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--after-select", action="store_true",
                    help="run the stock team-select first (JSR $B9B7), then "
                         "jump to the bracket; preserves the stock state")
    ap.add_argument("--cursor", type=lambda s: int(s, 0), default=0,
                    help="initial bracket cursor slot (16 = AUS/CUB)")
    ap.add_argument("--match", type=lambda s: int(s, 0), default=None,
                    help="initial $07FC match index (default cursor >> 1)")
    ap.add_argument("-o", "--out", default="build/direct31-bracket.nes")
    args = ap.parse_args()
    rom = bytearray(open(args.rom, "rb").read())
    o = HEADER + BANK2 * PRG + (SCENE0D - 0x8000)
    if bytes(rom[o:o + 3]) not in (STOCK, bytes([0x4C, 0xA0, 0xFE])):
        raise SystemExit(f"$B9C0: expected stock hook or existing jump, found {rom[o:o+3].hex(' ')}")
    if args.after_select:
        rom[o:o + 6] = bytes([0x20, 0xB7, 0xB9, 0x4C, 0xA0, 0xFE])
    else:
        rom[o:o + 3] = bytes([0x4C, 0xA0, 0xFE])

    match = args.match if args.match is not None else (args.cursor >> 1)
    code = OAM_CLEAR + bytes([0xA9, match & 0xFF, 0x8D, 0xFC, 0x07]) + BANK_JUMP
    fixed = HEADER + 15 * PRG + (TRAMP - 0xC000)
    if rom[fixed:fixed + len(code)].count(0xFF) != len(code):
        raise SystemExit(f"${TRAMP:04X} is not free")
    rom[fixed:fixed + len(code)] = code

    if args.cursor:
        o = HEADER + 11 * PRG + (0x8100 - 0x8000)
        if bytes(rom[o:o + 5]) != bytes([0xA9, 0x00, 0x8D, 0xC7, 0x07]):
            raise SystemExit(f"$8100: unexpected cursor init {rom[o:o+5].hex(' ')}")
        rom[o + 1] = args.cursor & 0xFF
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: scene 0D -> $FEA0 -> bank11 $8000, "
          f"cursor={args.cursor}, match={match}")


if __name__ == "__main__":
    main()
