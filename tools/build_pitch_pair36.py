#!/usr/bin/env python3
"""Build direct31-pair36: $C790 handles $05=0 without the 256-loop.

The wrapping row starts at X=255 with $05=0.  $C790 writes the 3 header
bytes, then:

    C7AB: A9 00       LDA #$00
    C7AD: 85 04       STA $04
    C7AF: A4 04       LDY $04
    ...
    C7D1: C6 07       DEC $07
    C7D3: D0 DA       BNE $C7AF

With $07=0, `DEC $07` wraps to $FF and the loop runs 256 times.  The
header bytes are needed (they set the PPU address/length), so skipping
the whole row (pair35) crashes the scene.

pair36 replaces $C7AB-$C7AE (`A9 00 85 04`) with `JMP $FBF0; NOP`.
The helper:

    FBF0: A5 05       LDA $05
    FBF2: F0 07       BEQ $FBFB      ; zero chars -> RTS after header
    FBF4: A9 00       LDA #$00
    FBF6: 85 04       STA $04
    FBF8: 4C AF C7    JMP $C7AF
    FBFB: 60          RTS

Base: build/direct31-pair23.nes.

Result: 15/15 and 26/26 passes.  The zero-length guard writes the header and skips the 256-iteration loop; match 14 now passes.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair36.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC7AB)
    want = bytes.fromhex("A9 00 85 04")
    got = rom[o:o + 4]
    if got != want:
        raise SystemExit(f"$C7AB expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = fixed_off(0xFBF0)
    if rom[ho:ho + 0x10] != b"\xff" * 0x10:
        raise SystemExit("$FBF0 is not FF padding")

    helper = bytes.fromhex(
        "A5 05"        # FBF0 LDA $05
        "F0 07"        # FBF2 BEQ $FBFB
        "A9 00"        # FBF4 LDA #$00
        "85 04"        # FBF6 STA $04
        "4C AF C7"     # FBF8 JMP $C7AF
        "60"           # FBFB RTS
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBF0 zero-length guard: {helper.hex(' ')}")

    rom[o:o + 4] = bytes.fromhex("4C F0 FB EA")
    print("  fixed $C7AB -> JMP $FBF0")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
