#!/usr/bin/env python3
"""P1: fix the bracket header/title leftovers.

    python3 tools/build_bracket_layout.py build/direct31.nes -o build/direct31-layout.nes

Two visual artefacts remain after the codes/clear fixes:

1. the 32-char header run wraps its last 8 chars onto row 4; the wrapped
   text starts with a stray "F" (the old "SF" tail) at `$B21A`;
2. the static title run is 15 chars ("32 TEAM BRACKET") but the live round
   label copies only 14, leaving a trailing "T" at `$0333`.

This patches the header byte to a space and appends
`LDA #$20 / STA $0333` before the round-label RTS.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK11 = 11
HEADER_F = 0xB21A
ROUND_RTS = 0x8456
ROUND_BYTES = bytes([0xAD, 0xFC, 0x07, 0xAA, 0xBD, 0x00, 0x85, 0xA8,
                     0xA2, 0x00, 0xB9, 0xA0, 0x84, 0x9D, 0x25, 0x03,
                     0xC8, 0xE8, 0xE0, 0x0E, 0xD0, 0xF4, 0x60])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/direct31-layout.nes")
    args = ap.parse_args()
    rom = bytearray(open(args.rom, "rb").read())
    base = HEADER + BANK11 * PRG

    o = base + (HEADER_F - 0x8000)
    if rom[o] != 0x46:
        raise SystemExit(f"$B21A: expected 'F' (46), found {rom[o]:02x}")
    rom[o] = 0x20

    o = base + (0x8440 - 0x8000)
    if bytes(rom[o:o + len(ROUND_BYTES)]) != ROUND_BYTES:
        raise SystemExit(f"$8440: round-label routine differs: {rom[o:o+24].hex(' ')}")
    tail = base + (ROUND_RTS - 0x8000)
    rom[tail:tail + 6] = bytes([0xA9, 0x20, 0x8D, 0x33, 0x03, 0x60])

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: header space at $B21A, title tail space at $0333")


if __name__ == "__main__":
    main()
