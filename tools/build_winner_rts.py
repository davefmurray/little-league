#!/usr/bin/env python3
"""Diagnostic build for the state-only champion soak.

    python3 tools/build_winner_rts.py build/direct19.nes -o build/direct19-rts.nes

The score-winner routine at bank11 $83A0 normally ends with `JMP $8000` to
redraw the bracket.  For a state-only soak we call it 31 times from the
debugger and need it to return, so replace that final jump with `RTS`
(`60 EA EA`).  This build is for the soak harness only; it is not the game
flow.
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK = 11
BASE = 0x8000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="direct19.nes (score-winner + high-team build)")
    ap.add_argument("-o", "--out", default="build/direct19-rts.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    off = HEADER + BANK * PRG + (0x83C5 - BASE)
    old = bytes(rom[off:off + 3])
    if old != bytes([0x4C, 0x00, 0x80]):
        raise SystemExit(
            f"bank{BANK} $83C5: expected 4C 00 80, found {old.hex(' ')}")
    rom[off:off + 3] = bytes([0x60, 0xEA, 0xEA])   # RTS / NOP / NOP
    print("bank11 $83C5: JMP $8000 -> RTS (state-soak build)")
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
