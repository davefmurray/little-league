#!/usr/bin/env python3
"""P1: choose the bracket winner from the real live scores.

    python3 tools/build_score_winner.py build/direct17.nes -o build/direct18.nes

Replaces the forced first-team winner at bank 11 $83A0 with:

    A = $7700[2m], B = $7700[2m+1]
    winner = A if $048B >= $048C else B
    $7720[m] = winner
    INC $07FC
    JMP $8000

$048B/$048C are the two live scores (bank7 $A418 does `INC $048B,X`;
bank4 $B133/$B141 reads them for the HUD).  $773F is scratch: it is the
unused byte between the 63-slot array ($7700-$773E) and the win-count
area ($7740+), so no zero-page state is touched.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK11 = 11
FIXED = 15

FORCED = bytes([
    0xAE, 0xFC, 0x07,       # LDX $07FC
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0x0A,                   # ASL A
    0xA8,                   # TAY
    0xB9, 0x00, 0x77,       # LDA $7700,Y
    0x9D, 0x20, 0x77,       # STA $7720,X
    0xEE, 0xFC, 0x07,       # INC $07FC
    0x4C, 0x00, 0x80,       # JMP $8000
])

SCORE_WINNER = bytes([
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0x0A,                   # ASL A
    0xA8,                   # TAY                ; Y = 2m
    0xB9, 0x00, 0x77,       # LDA $7700,Y        ; team A
    0x8D, 0x3F, 0x77,       # STA $773F          ; scratch
    0xAD, 0x8B, 0x04,       # LDA $048B          ; A's score
    0xCD, 0x8C, 0x04,       # CMP $048C          ; B's score
    0x90, 0x06,             # BCC use_b          ; A < B -> team B
    0xAD, 0x3F, 0x77,       # LDA $773F          ; team A
    0x4C, 0xBC, 0x83,       # JMP store
    0xB9, 0x01, 0x77,       # use_b: LDA $7701,Y ; team B
    0xAE, 0xFC, 0x07,       # store: LDX $07FC
    0x9D, 0x20, 0x77,       # STA $7720,X
    0xEE, 0xFC, 0x07,       # INC $07FC
    0x4C, 0x00, 0x80,       # JMP $8000
])


def bank_off(bank, addr):
    base = 0xC000 if bank == FIXED else 0x8000
    return HEADER + bank * PRG + (addr - base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct17.nes (forced-winner build)")
    ap.add_argument("-o", "--out", default="build/direct18.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    off = bank_off(BANK11, 0x83A0)
    old = bytes(rom[off:off + len(FORCED)])
    if old != FORCED:
        raise SystemExit(
            f"bank11 $83A0: expected forced-winner bytes, found {old.hex(' ')}")
    rom[off:off + len(SCORE_WINNER)] = SCORE_WINNER
    print(f"bank11 $83A0: forced winner -> score-based winner "
          f"({len(SCORE_WINNER)} bytes)")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
