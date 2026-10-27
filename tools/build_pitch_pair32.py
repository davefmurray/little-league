#!/usr/bin/env python3
"""Build direct31-pair32: $C790 bounds check without RAM scratch.

pair31 used $07F5 for 5*$05; the helper never took the skip path, so
the scratch may be clobbered by NMI.  pair32 computes X+5N in A with
five `ADC $05` (N <= $33), no memory scratch:

    LDA $05 / CMP #$34 / BCS skip
    TXA / CLC / ADC $05 x5
    BCS skip / CMP #$F0 / BCS skip
    LDA $01 / ORA #$40 / STA $0300,X / JMP $C797
    skip: RTS

Base: build/direct31-pair31.nes (already has $C790 -> JMP $FBC0).

Result: match 14 still $0032=6.  The no-scratch check behaves the same; the wrap bypasses the $C790 entry.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair31.nes"
DST = ROOT / "build" / "direct31-pair32.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    o = fixed_off(0xC790)
    want = bytes.fromhex("4C C0 FB EA")
    got = rom[o:o + 4]
    if got != want:
        raise SystemExit(f"$C790 expected {want.hex(' ')}, got {got.hex(' ')}")

    ho = fixed_off(0xFBC0)
    helper = bytes.fromhex(
        "A5 05"        # FBC0 LDA $05
        "C9 34"        # FBC2 CMP #$34          ; N >= 52 cannot fit
        "B0 1C"        # FBC4 BCS $FBE2
        "8A"           # FBC6 TXA
        "18"           # FBC7 CLC
        "65 05"        # FBC8 ADC $05
        "65 05"        # FBCA ADC $05
        "65 05"        # FBCC ADC $05
        "65 05"        # FBCE ADC $05
        "65 05"        # FBD0 ADC $05          ; X + 5N
        "B0 0E"        # FBD2 BCS $FBE2
        "C9 F0"        # FBD4 CMP #$F0
        "B0 0A"        # FBD6 BCS $FBE2
        "A5 01"        # FBD8 LDA $01
        "09 40"        # FBDA ORA #$40
        "9D 00 03"     # FBDC STA $0300,X
        "4C 97 C7"     # FBDF JMP $C797
        "60"           # FBE2 RTS
    )
    if rom[ho:ho + 0x30] == b"\x00" * 0x30:
        raise SystemExit("$FBC0 looks unwritten")
    rom[ho:ho + len(helper)] = helper
    print(f"  fixed $FBC0 no-scratch bounds: {helper.hex(' ')}")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
