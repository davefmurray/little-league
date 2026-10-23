#!/usr/bin/env python3
"""Build direct31-pair23: pair22 + high-team order-menu exit.

Experiment for the match-5 stall.  At bank1 $9C42 the menu does:

    LDA $06E1        ; 1 = series active / high-team path
    BEQ $9C4C        ; flag clear -> scene 02 (leave order screen)
    LDA #$07
    STA $BE          ; flag set -> select item 7, stay in the menu
    RTS

The high-team path therefore never leaves via B; it walks into the
second team's order draw.  pair23 forces the flag-clear branch:

    JMP $9C4C        ; always leave the order screen
    NOP
    NOP

Base: build/direct31-pair22.nes.  This is the match-5 fix used by the
10-match soak; order-menu-high tracks removing it once the second-team
order draw no longer overflows.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair22.nes"
DST = ROOT / "build" / "direct31-pair23.nes"
HEADER = 16
BANK = 0x4000


def off(addr, bank):
    return HEADER + bank * BANK + (addr - 0x8000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")
    o = off(0x9C42, 1)
    want = bytes.fromhex("AD E1 06 F0 05")
    got = rom[o:o + len(want)]
    if got != want:
        raise SystemExit(f"$9C42 expected {want.hex(' ')}, got {got.hex(' ')}")
    patch = bytes.fromhex("4C 4C 9C EA EA")
    rom[o:o + len(patch)] = patch
    print(f"  bank1 $9C42 menu exit: {patch.hex(' ')}")
    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
