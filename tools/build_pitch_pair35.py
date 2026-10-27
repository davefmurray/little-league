#!/usr/bin/env python3
"""Build direct31-pair35: skip zero-length rows at $C741.

The row that wraps on scene 0x13 starts at X=255 with $05=0.  $C790
uses a do-while loop (`DEC $07 / BNE`), so $05=0 runs 256 times and
writes ~1KB, wrapping X to 6.  The bounds caps never saw it because
the row starts at X=255 and the skip path is not on the executed path
in the capped builds.

pair35 replaces $C741-$C743 with `JMP $FBE0`.  The helper:

    FBE0: A5 05       LDA $05
    FBE2: F0 08       BEQ $FBEC      ; nothing to draw, skip row
    FBE4: A6 32       LDX $32
    FBE6: 20 90 C7    JSR $C790
    FBE9: 4C 46 C7    JMP $C746
    FBEC: 60          RTS

Skipping a zero-length row loses no visible text and avoids the
256-iteration loop.

Base: build/direct31-pair23.nes.

Result: skipping the whole row removes the wrap ($0032=0x39) but crashes at PC $81CE (data).  The 3 header bytes are needed; see pair36.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair35.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC741)
    want = bytes.fromhex("A6 32 20")
    got = rom[o:o + 3]
    if got != want:
        raise SystemExit(f"$C741 expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = fixed_off(0xFBE0)
    if rom[ho:ho + 0x10] != b"\xff" * 0x10:
        raise SystemExit("$FBE0 is not FF padding")

    helper = bytes.fromhex(
        "A5 05"        # FBE0 LDA $05
        "F0 08"        # FBE2 BEQ $FBEC
        "A6 32"        # FBE4 LDX $32
        "20 90 C7"     # FBE6 JSR $C790
        "4C 46 C7"     # FBE9 JMP $C746
        "60"           # FBEC RTS
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBE0 zero-row skip: {helper.hex(' ')}")

    rom[o:o + 3] = bytes.fromhex("4C E0 FB")
    print("  fixed $C741 -> JMP $FBE0")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
