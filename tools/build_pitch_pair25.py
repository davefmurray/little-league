#!/usr/bin/env python3
"""Build direct31-pair25: stop the display-list flush at/past $0032.

The fixed-bank flush at $C53A does:

    LDX #$00
    CPX $32
    BNE $C545      ; only stops when X == $32

When a screen builds more than 256 bytes the builder wraps X, sets $32
to the small wrapped value, and the flush loops forever (X > $32 but
never equal).  pair25 changes the `BNE` at $C53E to `BCS`, so a wrapped
list is truncated at the first run boundary instead of hanging:

    CPX $32
    BCS $C540      ; stop when X >= $32

Normal lists (X reaches $32 exactly) are unchanged.

Base: build/direct31-pair23.nes (forced menu exit).  A clean base
without $9C42 can be built later if the menu exits naturally.

Result: breaks boot (`match 0: $07FC=FF`).  Normal lists can have
X > $32 mid-build, so `BCS` stops them early and the boot screens never
finish.  Do not repeat this one-byte change; cap/paginate in the builder
or split the flush instead.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair25.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC53A)
    want = bytes.fromhex("A2 00 E4 32 D0 05 A9 00 85 32 60")
    got = rom[o:o + len(want)]
    if got != want:
        raise SystemExit(f"$C53A expected {want.hex(' ')}, got {got.hex(' ')}")

    rom[o + 4] = 0xB0  # BNE -> BCS
    print(f"  fixed $C53E BNE -> BCS (stop when X >= $32)")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
