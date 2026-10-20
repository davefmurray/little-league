#!/usr/bin/env python3
"""M1: scene dispatcher on $07C3.

Keeps the selector hook at $CBE6. $FF00 now branches:
  $07C3 == $FF -> bank 10 selector
  otherwise    -> bank 11 (stub writes $A5 to $07FF)

    python3 tools/build_dispatcher.py build/select-screen.nes -o build/dispatcher.nes
    python3 tools/build_dispatcher.py build/select-screen.nes --selected 5 -o build/dispatcher-test.nes
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK11 = 0x8000
STUB = bytes([0xA9, 0xA5, 0x8D, 0xFF, 0x07, 0x4C, 0x00, 0x80])
DISPATCH = bytes([
    0x8D, 0x00, 0x20,        # STA $2000 (the instruction the hook replaced)
    0xAD, 0xC3, 0x07,        # LDA $07C3
    0xC9, 0xFF,              # CMP #$FF
    0xF0, 0x08,              # BEQ selector
    0xA9, 0x0B,              # LDA #11
    0x20, 0x4E, 0xC1,        # JSR $C14E
    0x4C, 0x00, 0x80,        # JMP $8000
    0xA9, 0x0A,              # selector:
    0x20, 0x4E, 0xC1,
    0x4C, 0x00, 0x80,
])


def bank_off(bank):
    return HEADER + bank * PRG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--selected", type=lambda s: int(s, 0))
    ap.add_argument("--force", type=lambda s: int(s, 0),
                    help="test only: use this team id instead of reading $07C3")
    ap.add_argument("--roster-cache", action="store_true",
                    help="call the $FB90 32-team roster cache at reset before "
                         "dispatching; build_32x20.py repointed reads to "
                         "$7F00, so it must run or those reads return zeros")
    ap.add_argument("-o", "--out", default="build/dispatcher.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    nb = rom[4]
    fixed = bank_off(nb - 1) + (0xFF00 - 0xC000)
    dispatch = DISPATCH
    if args.roster_cache:
        dispatch = bytes([0x20, 0x90, 0xFB,   # JSR $FB90
                       0xA9, 0x80]) + DISPATCH   # A=$80 for STA $2000
    rom[fixed:fixed + len(dispatch)] = dispatch
    # Restore stock at $CBE6 (LDA #$00) and hook after reset init at $CC06
    base = bank_off(nb - 1)
    rom[base + (0xCBE6 - 0xC000):base + (0xCBE6 - 0xC000) + 5] = bytes([0xA9, 0x00, 0x8D, 0x01, 0x20])
    rom[base + (0xCC06 - 0xC000):base + (0xCC06 - 0xC000) + 3] = bytes([0x20, 0x00, 0xFF])
    if args.force is not None:
        rom[fixed + len(dispatch) - len(DISPATCH) + 3:
            fixed + len(dispatch) - len(DISPATCH) + 6] = bytes(
                [0xA9, args.force, 0xEA])

    stub = bank_off(11) + (BANK11 - 0x8000)
    rom[stub:stub + len(STUB)] = STUB

    if args.selected is not None:
        pat = bytes([0xA9, 0xFF, 0x8D, 0xC3, 0x07])
        off = bank_off(10) + (0x8000 - 0x8000)
        b10 = rom[bank_off(10):bank_off(11)]
        i = b10.find(pat)
        if i < 0:
            raise SystemExit("selector init pattern not found")
        rom[bank_off(10) + i + 1] = args.selected

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: dispatch on $07C3, bank11 stub, selected={args.selected}")


if __name__ == "__main__":
    main()
