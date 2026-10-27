#!/usr/bin/env python3
"""Build direct31-pair33: cap both fixed-bank writers.

pair28 capped the fixed text builder ($C202/$C223) but the scene-0x13
list still wrapped; pair32 capped the $C790 row writer but the wrap
persisted.  The list uses both paths, so pair33 combines them:

  * $C202/$C223 caps from pair28
  * $C790 bounds check from pair32 ($FBC0 helper)

Base: build/direct31-pair28.nes.

Result: match 14 still $0032=6.  Capping both the $C1E5 builder and the $C790 row writer is still not enough.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair28.nes"
DST = ROOT / "build" / "direct31-pair33.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC790)
    want = bytes.fromhex("A5 01 09 40")
    got = rom[o:o + 4]
    if got != want:
        raise SystemExit(f"$C790 expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = fixed_off(0xFBC0)
    if rom[ho:ho + 0x30] != b"\xff" * 0x30:
        raise SystemExit("$FBC0 is not FF padding")

    helper = bytes.fromhex(
        "A5 05"        # FBC0 LDA $05
        "C9 34"        # FBC2 CMP #$34
        "B0 1C"        # FBC4 BCS $FBE2
        "8A"           # FBC6 TXA
        "18"           # FBC7 CLC
        "65 05"        # FBC8 ADC $05
        "65 05"        # FBCA ADC $05
        "65 05"        # FBCC ADC $05
        "65 05"        # FBCE ADC $05
        "65 05"        # FBD0 ADC $05
        "B0 0E"        # FBD2 BCS $FBE2
        "C9 F0"        # FBD4 CMP #$F0
        "B0 0A"        # FBD6 BCS $FBE2
        "A5 01"        # FBD8 LDA $01
        "09 40"        # FBDA ORA #$40
        "9D 00 03"     # FBDC STA $0300,X
        "4C 97 C7"     # FBDF JMP $C797
        "60"           # FBE2 RTS
    )
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBC0 bounds helper: {helper.hex(' ')}")

    patch = bytes.fromhex("4C C0 FB EA")  # JMP $FBC0; NOP
    rom[o:o + 4] = patch
    print(f"  fixed $C790 -> JMP $FBC0: {patch.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
