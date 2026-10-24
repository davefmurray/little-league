#!/usr/bin/env python3
"""Build direct31-pair30: conditional $C75A cap (scene $13 only).

pair29 capped every $C75A wrap and broke match 5.  pair30 caps only
when $047B == $13 (the password/menu scene) and the new X is < $10
(the wrapped 262-byte list ends at X=6).  Other scenes keep the
original behavior.

Base: build/direct31-pair28.nes.

Result: match 5 still stalls.  Short scene-0x13 lists can also end at
X < $10, so the threshold is not a wrap test.  The next step is a cap
inside the $C790 row writer (before X crosses $FF) or pagination.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair28.nes"
DST = ROOT / "build" / "direct31-pair30.nes"
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
        "A5 7B"        # FBB2 LDA $047B
        "C9 13"        # FBB4 CMP #$13
        "D0 09"        # FBB6 BNE $FBC1
        "8A"           # FBB8 TXA
        "C9 10"        # FBB9 CMP #$10
        "B0 04"        # FBBB BCS $FBC1
        "A9 FF"        # FBBD LDA #$FF
        "85 32"        # FBBF STA $32
        "4C 5C C7"     # FBC1 JMP $C75C
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBB0 conditional cap: {helper.hex(' ')}")

    patch = bytes.fromhex("4C B0 FB EA")  # JMP $FBB0; NOP
    rom[o:o + 4] = patch
    print(f"  fixed $C75A -> JMP $FBB0: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
