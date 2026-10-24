#!/usr/bin/env python3
"""Build direct31-pair29: cap $0032 at the $C75A row renderer.

A conditional write breakpoint (value 6) from the match-14 pre-input
state stops at:

    C75A: STX $32       ; X = 6 after $C790 wrapped
    C75C: LDA $AD
    C75E: AND #$1E
    C760: BNE $C765
    C762: JSR $C53A     ; flush loops because X > $32

caller $CA1F.  This is the builder that actually wraps on the
scene-0x13 password list; the $C1E5 text builder is a different path.

pair29 replaces $C75A-$C75D (`86 32 A5 AD`) with `JMP $FBB0; NOP`.
The helper stores X, caps a wrapped X to $FF (so the flush can
terminate), and jumps back to the original `LDA $AD` at $C75C.

Base: build/direct31-pair28.nes.

Result: match 5 now stalls.  Capping every $C75A wrap truncates the
order/list screen too.  pair30 tries a scene-0x13-only cap.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair28.nes"
DST = ROOT / "build" / "direct31-pair29.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC75A)
    want = bytes.fromhex("86 32 A5 AD")
    got = rom[o:o + 4]
    if got != want:
        raise SystemExit(f"$C75A expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = fixed_off(0xFBB0)
    if rom[ho:ho + 0x10] != b"\xff" * 0x10:
        raise SystemExit("$FBB0 is not FF padding")

    helper = bytes.fromhex(
        "86 32"        # FBB0 STX $32
        "8A"           # FBB2 TXA
        "D0 02"        # FBB3 BNE $FBB7
        "A9 FF"        # FBB5 LDA #$FF
        "85 32"        # FBB7 STA $32
        "4C 5C C7"     # FBB9 JMP $C75C
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBB0 cap: {helper.hex(' ')}")

    patch = bytes.fromhex("4C B0 FB EA")  # JMP $FBB0; NOP
    rom[o:o + 4] = patch
    print(f"  fixed $C75A -> JMP $FBB0: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
