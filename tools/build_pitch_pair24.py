#!/usr/bin/env python3
"""Build direct31-pair24: reset the display list at scene-0F entry.

pair22 (capture/restore) still stalls in the high-team order editor.
At the stall the CPU is looping in the fixed-bank display-list flush
($C545): $0032 is stale (6) while $0300 holds the previous 32-team
list, so the flush never reaches the end pointer and the menu starves.

pair24 replaces bank1 $96ED `LDA $0522` with `JSR $FB90`; the helper
zeroes $0032, then does the original load and returns.  The normal
order-menu path is kept (no $9C42 forced exit).

Base: build/direct31-pair22.nes.

Result: still stalls at match 5.  $0032 is reset to 0, but the list
itself is 373 bytes ($0033=0x175), so the builder wraps again.
Zeroing at scene entry is not enough; the list must be paginated or
trimmed.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair22.nes"
DST = ROOT / "build" / "direct31-pair24.nes"
HEADER = 16
BANK = 0x4000


def off(addr, bank):
    return HEADER + bank * BANK + (addr - 0x8000)


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = off(0x96ED, 1)
    want = bytes.fromhex("AD 22 05")
    got = rom[o:o + 3]
    if got != want:
        raise SystemExit(f"$96ED expected {want.hex(' ')}, got {got.hex(' ')}")

    helper = bytes.fromhex(
        "A9 00"      # FB90 LDA #$00
        "85 32"      # FB92 STA $32
        "AD 22 05"   # FB94 LDA $0522
        "60"         # FB97 RTS
    )
    ho = fixed_off(0xFB90)
    if rom[ho:ho + 16] != b"\xff" * 16:
        raise SystemExit("$FB90 is not FF padding")
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FB90 helper: {helper.hex(' ')}")

    patch = bytes.fromhex("20 90 FB")  # JSR $FB90
    rom[o:o + 3] = patch
    print(f"  bank1 $96ED reset call: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
