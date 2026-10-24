#!/usr/bin/env python3
"""Build direct31-pair28: cap the FIXED-bank text builder.

The text builder that actually runs is in the fixed bank:

    C1E5: ... text append macro ...
    C202: STX $32
    C204: DEC $AC
    C206: TYA
    ...
    C21D: LDA #$FF
    C21F: STA $0300,X
    C222: INX
    C223: STX $32
    C225: RTS

pair26/pair27 patched the bank7 mirror at $8202/$8223, which is not
the executed copy, so match 14 still wrapped.

pair28 replaces both fixed-bank stores:

    C202: JMP $FB90 ; NOP      (helper stores X, caps wrap to $FF,
                                does the original DEC $AC, JMP $C206)
    C223: JMP $FBA0            (helper stores X, caps wrap to $FF, RTS)

Base: build/direct31-pair23.nes.

Result: match 14 still wraps at $0032=6.  The fixed $C1E5 builder is
not the writer for this screen; the actual store is $C75A (see
pair29/pair30).
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair23.nes"
DST = ROOT / "build" / "direct31-pair28.nes"
HEADER = 16
BANK = 0x4000


def fixed_off(addr):
    return HEADER + 15 * BANK + (addr - 0xC000)


def main():
    rom = bytearray(SRC.read_bytes())
    print(f"base {SRC.name} {hashlib.sha256(rom).hexdigest()}")

    seg_o = fixed_off(0xC202)
    seg_want = bytes.fromhex("86 32 C6 AC")
    if rom[seg_o:seg_o + 4] != seg_want:
        raise SystemExit(f"$C202 expected {seg_want.hex(' ')}, got {rom[seg_o:seg_o+4].hex(' ')}")
    term_o = fixed_off(0xC223)
    term_want = bytes.fromhex("86 32 60")
    if rom[term_o:term_o + 3] != term_want:
        raise SystemExit(f"$C223 expected {term_want.hex(' ')}, got {rom[term_o:term_o+3].hex(' ')}")

    h1_o = fixed_off(0xFB90)
    if rom[h1_o:h1_o + 0x30] != b"\xff" * 0x30:
        raise SystemExit("$FB90 is not FF padding")

    h1 = bytes.fromhex(
        "86 32"        # FB90 STX $32
        "8A"           # FB92 TXA
        "D0 02"        # FB93 BNE $FB97
        "A9 FF"        # FB95 LDA #$FF
        "85 32"        # FB97 STA $32
        "C6 AC"        # FB99 DEC $AC
        "4C 06 C2"     # FB9B JMP $C206
    )
    rom[h1_o:h1_o + len(h1)] = h1
    print(f"  fixed $FB90 segment cap: {h1.hex(' ')}")

    h2 = bytes.fromhex(
        "86 32"        # FBA0 STX $32
        "8A"           # FBA2 TXA
        "D0 02"        # FBA3 BNE $FBA7
        "A9 FF"        # FBA5 LDA #$FF
        "85 32"        # FBA7 STA $32
        "60"           # FBA9 RTS
    )
    rom[h1_o + 0x10:h1_o + 0x10 + len(h2)] = h2
    print(f"  fixed $FBA0 terminator cap: {h2.hex(' ')}")

    rom[seg_o:seg_o + 4] = bytes.fromhex("4C 90 FB EA")
    rom[term_o:term_o + 3] = bytes.fromhex("4C A0 FB")
    print("  $C202 -> JMP $FB90 ; NOP")
    print("  $C223 -> JMP $FBA0")

    DST.write_bytes(rom)
    print(f"wrote {DST.relative_to(ROOT)} {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
