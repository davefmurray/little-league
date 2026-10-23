#!/usr/bin/env python3
"""Build direct31-pair26: cap $0032 when the text builder wraps.

Bank7 $821D-$8225 terminates a text string:

    821D: LDA #$FF
    821F: STA $0300,X
    8222: INX
    8223: STX $32
    8225: RTS

If the list already passed $FF, INX wraps X to 0 and $0032 becomes a
small value; the fixed flush then loops.  pair26 replaces $8223 with
`JMP $BF40`; the helper stores X, and if X wrapped to 0 it stores $FF
instead, so the flush stops at the end of the buffer.

This truncates an overlong screen at 255 bytes but keeps the game
alive.  It does not replace proper pagination.

Base: build/direct31-pair23.nes.

Result: match 14 still wraps at $0032=6, so the wrap is not only at
the terminator.  pair27 probes the earlier segment path.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair26.nes"
HEADER = 16
BANK = 0x4000


def off(addr, bank):
    return HEADER + bank * BANK + (addr - 0x8000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = off(0x8223, 7)
    want = bytes.fromhex("86 32 60")
    got = rom[o:o + 3]
    if got != want:
        raise SystemExit(f"$8223 expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = off(0xBF40, 7)
    if rom[ho:ho + 16] != b"\xff" * 16:
        raise SystemExit("$BF40 is not FF padding")

    helper = bytes.fromhex(
        "86 32"      # BF40 STX $32
        "8A"         # BF42 TXA
        "D0 02"      # BF43 BNE $BF47
        "A9 FF"      # BF45 LDA #$FF
        "85 32"      # BF47 STA $32
        "60"         # BF49 RTS
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed bank7 $BF40 cap helper: {helper.hex(' ')}")

    patch = bytes.fromhex("4C 40 BF")  # JMP $BF40
    rom[o:o + 3] = patch
    print(f"  bank7 $8223 terminator -> JMP $BF40: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
