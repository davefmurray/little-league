#!/usr/bin/env python3
"""Build direct31-pair31: bounds-check the $C790 row writer.

$C790 writes a row as 3 header bytes plus 4-5 bytes per character
($05 chars), with no bounds check.  The 262-byte scene-0x13 list makes
X wrap; the caller then stores $32=6 and the flush loops.

pair31 replaces the first four bytes of $C790 (`A5 01 09 40`) with
`JMP $FBC0; NOP`.  The helper computes 5*$05 and, if
X + 5*$05 >= $F0, returns without writing the row.  Otherwise it does
the original `LDA $01 / ORA #$40 / STA $0300,X` and jumps to $C797.
The list is truncated at a safe end pointer instead of wrapping.

Base: build/direct31-pair23.nes.

Result: match 14 still $0032=6.  The helper is entered (X=0, $05=9) but the $FBE7 skip path never hits; the wrapping row does not come through this entry check.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair31.nes"
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
    if rom[ho:ho + 0x40] != b"\xff" * 0x40:
        raise SystemExit("$FBC0 is not FF padding")

    helper = bytes.fromhex(
        "A5 05"        # FBC0 LDA $05
        "0A"           # FBC2 ASL A
        "0A"           # FBC3 ASL A            ; 4N
        "8D F5 07"     # FBC4 STA $07F5
        "A5 05"        # FBC7 LDA $05
        "18"           # FBC9 CLC
        "6D F5 07"     # FBCA ADC $07F5        ; 5N
        "B0 18"        # FBCD BCS skip          ; 5N overflow
        "8D F5 07"     # FBCF STA $07F5
        "8A"           # FBD2 TXA
        "18"           # FBD3 CLC
        "6D F5 07"     # FBD4 ADC $07F5        ; X + 5N
        "B0 0E"        # FBD7 BCS skip
        "C9 F0"        # FBD9 CMP #$F0
        "B0 0A"        # FBDB BCS skip
        "A5 01"        # FBDD LDA $01
        "09 40"        # FBDF ORA #$40
        "9D 00 03"     # FBE1 STA $0300,X
        "4C 97 C7"     # FBE4 JMP $C797
        "60"           # FBE7 RTS
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
