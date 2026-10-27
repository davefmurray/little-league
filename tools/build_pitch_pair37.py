#!/usr/bin/env python3
"""Build direct31-pair37: drop the forced menu exit + fix $05=0 rows.

pair36 = pair23 (forced menu exit) + the $C790 zero-length guard and
passes 15/15.  pair37 is the clean variant:

  * base build/direct31-pair22.nes (capture/restore, NO $9C42 forced
    order-menu exit)
  * fixed $C7AB -> JMP $FBF0; the helper writes the 3 row header bytes
    and returns when $05=0, avoiding the 256-iteration loop.

If this passes 26 matches, `displaylist-256` is satisfied without the
$9C42 workaround.

Result: still stalls at match 5.  The 373-byte second-team list is a separate issue (order-menu-high/list-dispatch); keep the $9C42 forced exit for now.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair22.nes"
DST = ROOT / "build" / "direct31-pair37.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    # sanity: this base must NOT have the $9C42 forced exit
    o9c42 = 16 + 1 * BANK + (0x9C42 - 0x8000)
    if rom[o9c42:o9c42 + 5] != bytes.fromhex("AD E1 06 F0 05"):
        raise SystemExit("base $9C42 is not the original menu branch")

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
