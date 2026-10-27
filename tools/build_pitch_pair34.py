#!/usr/bin/env python3
"""Build direct31-pair34: diagnostic - save the row start X.

At $C741 the row renderer does:

    C741: A6 32       LDX $32
    C743: 20 90 C7    JSR $C790
    C746: ...

pair34 replaces $C741-$C743 with `JMP $FBD0`.  The helper saves the
row start ($32) to $07F6, reloads X, performs the first $C790 call
itself (the original JSR opcode was overwritten by the JMP), and
continues at $C746:

    FBD0: A5 32       LDA $32
    FBD2: 85 F6       STA $07F6
    FBD4: A6 32       LDX $32
    FBD6: 20 90 C7    JSR $C790
    FBD9: 4C 46 C7    JMP $C746

Then a breakpoint at $C75A (the wrap store) reads $07F6: 0 means the
two $C790 calls produced the wrap; 6 means it was already set upstream.

Diagnostic only (adds a store to debug scratch $07F6).
Base: build/direct31-pair23.nes.

Result: at the $0032=6 write the row started at X=255 with $05=0.  $C790 is a do-while, so the zero-length row runs 256 times and wraps X.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair34.nes"
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

    ho = fixed_off(0xFBD0)
    if rom[ho:ho + 0x10] != b"\xff" * 0x10:
        raise SystemExit("$FBD0 is not FF padding")

    helper = bytes.fromhex(
        "A5 32"        # FBD0 LDA $32
        "85 F6"        # FBD2 STA $07F6
        "A6 32"        # FBD4 LDX $32
        "20 90 C7"     # FBD6 JSR $C790
        "4C 46 C7"     # FBD9 JMP $C746
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBD0 row-start probe: {helper.hex(' ')}")

    rom[o:o + 3] = bytes.fromhex("4C D0 FB")
    print("  fixed $C741 -> JMP $FBD0")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
