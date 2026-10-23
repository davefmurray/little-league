#!/usr/bin/env python3
"""Build direct31-pair27: cap $0032 on the segment path too.

pair26 capped the terminator at $8223 but match 14 still wrapped at
$0032=6, so the wrap happens at the earlier `STX $32` in the text
builder:

    8202: STX $32
    8204: DEC $AC
    8206: TYA
    ...

pair27 replaces $8202-$8205 (`86 32 C6 AC`) with `JMP $BF50; NOP`.
The helper stores X, caps a wrapped X to $FF, performs the original
DEC $AC, and jumps back to $8206.

Base: build/direct31-pair26.nes.

Result: match 14 still wraps at $0032=6.  The scene-0x13 builder uses
another STX $32 site; a write breakpoint on $0032 during the stall
never fires, so the list is already built when the flush blocks.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair26.nes"
DST = ROOT / "build" / "direct31-pair27.nes"
HEADER = 16
BANK = 0x4000


def off(addr, bank):
    return HEADER + bank * BANK + (addr - 0x8000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = off(0x8202, 7)
    want = bytes.fromhex("86 32 C6 AC")
    got = rom[o:o + 4]
    if got != want:
        raise SystemExit(f"$8202 expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = off(0xBF50, 7)
    if rom[ho:ho + 16] != b"\xff" * 16:
        raise SystemExit("$BF50 is not FF padding")

    helper = bytes.fromhex(
        "86 32"        # BF50 STX $32
        "8A"           # BF52 TXA
        "D0 02"        # BF53 BNE $BF57
        "A9 FF"        # BF55 LDA #$FF
        "85 32"        # BF57 STA $32
        "C6 AC"        # BF59 DEC $AC
        "4C 06 82"     # BF5B JMP $8206
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  bank7 $BF50 segment cap: {helper.hex(' ')}")

    patch = bytes.fromhex("4C 50 BF EA")  # JMP $BF50; NOP
    rom[o:o + 4] = patch
    print(f"  bank7 $8202 -> JMP $BF50: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
