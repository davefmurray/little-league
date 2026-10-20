#!/usr/bin/env python3
"""P1 redraw: add a visible "WIN <code>" line to the bracket.

    python3 tools/build_winner_display.py build/direct19.nes -o build/direct20.nes

The static display list at bank11 $B200 ends at 245 bytes ($F5).  Append a
run at row 21, column 1:

    $22A1 "WIN" + three code tiles + $FE     (9 bytes; list = 254/$FE)

The bracket draw loop at $8048 already fills the 32 team-code runs.  Replace
its `LDA #$F5 / STA $32 / JSR $C53A` tail with a call to a new bank11
routine at $83D0 that:

  - reads the last completed match's winner: $7720[$07FC-1]
  - looks up its 3 code tiles in $B000 (4 bytes/team)
  - writes them to the appended run at $03FA..$03FC
  - shows spaces when $07FC == 0
  - sets $32=$FE (254), flushes at $C53A, returns

Also patch the list-copy loop ($8044 CPX #$F5 -> #$FE).
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK = 11
BASE = 0x8000

WIN_RUN = bytes([
    0x22, 0xA1,             # nametable $22A1 (row 21, col 1)
    0x57, 0x49, 0x4E,       # "WIN"
    0x20, 0x20, 0x20,       # placeholder code tiles
    0xFE,                   # end of run
])

WINNER = bytes([
    0xAD, 0xFC, 0x07,       # LDA $07FC
    0xF0, 0x1F,             # BEQ $83F4 (no winner yet)
    0x38,                   # SEC
    0xE9, 0x01,             # SBC #$01
    0xAA,                   # TAX
    0xBD, 0x20, 0x77,       # LDA $7720,X
    0x0A,                   # ASL A
    0x0A,                   # ASL A
    0xA8,                   # TAY
    0xB9, 0x00, 0xB0,       # LDA $B000,Y
    0x8D, 0xFA, 0x03,       # STA $03FA
    0xB9, 0x01, 0xB0,       # LDA $B001,Y
    0x8D, 0xFB, 0x03,       # STA $03FB
    0xB9, 0x02, 0xB0,       # LDA $B002,Y
    0x8D, 0xFC, 0x03,       # STA $03FC
    0x4C, 0xFF, 0x83,       # JMP $83FF (flush)
    0xA9, 0x20,             # $83F4: LDA #$20
    0x8D, 0xFA, 0x03,       # STA $03FA
    0x8D, 0xFB, 0x03,       # STA $03FB
    0x8D, 0xFC, 0x03,       # STA $03FC
    0xA9, 0xFE,             # $83FF: LDA #$FE
    0x85, 0x32,             # STA $32
    0x20, 0x3A, 0xC5,       # JSR $C53A
    0x60,                   # RTS
])


def off(addr):
    return HEADER + BANK * PRG + (addr - BASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct19.nes (score-winner + high-team build)")
    ap.add_argument("-o", "--out", default="build/direct20.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())

    # List copy loop: copy 254 bytes instead of 245.
    o = off(0x8044)
    if bytes(rom[o:o + 2]) != bytes([0xE0, 0xF5]):
        raise SystemExit(f"$8044: expected E0 F5, found {rom[o:o+2].hex(' ')}")
    rom[o:o + 2] = bytes([0xE0, 0xFE])

    # Replace the old length/flush tail with a call to the new routine.
    o = off(0x8077)
    old = bytes([0xA9, 0xF5, 0x85, 0x32, 0x20, 0x3A, 0xC5])
    if bytes(rom[o:o + len(old)]) != old:
        raise SystemExit(f"$8077: expected {old.hex(' ')}, "
                         f"found {rom[o:o+len(old)].hex(' ')}")
    rom[o:o + len(old)] = bytes([0x20, 0xD0, 0x83, 0xEA, 0xEA, 0xEA, 0xEA])

    # New routine.
    o = off(0x83D0)
    if rom[o:o + len(WINNER)].count(0xFF) != len(WINNER):
        raise SystemExit(f"$83D0 is not free: {rom[o:o+16].hex(' ')}")
    rom[o:o + len(WINNER)] = WINNER

    # Append the display-list run at offset 245.
    o = off(0xB200) + 245
    if bytes(rom[o:o + len(WIN_RUN)]).count(0xFF) != len(WIN_RUN):
        raise SystemExit(f"$B200+245 is not free: {rom[o:o+16].hex(' ')}")
    rom[o:o + len(WIN_RUN)] = WIN_RUN

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: WIN line at $22A1, "
          f"list 254, winner routine $83D0")


if __name__ == "__main__":
    main()
