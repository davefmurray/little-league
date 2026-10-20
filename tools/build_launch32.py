#!/usr/bin/env python3
"""Build the launch-bridge 32-team field-test ROM.

    python3 tools/build_launch32.py build/launch-prod.nes \
        data/roster32.json -o build/launch32-high.nes

`launch-prod.nes` is the 16-bank base with the real launch bridge
(scene-18 `$98B9` -> `$FF20`, `$FF60`).  This tool applies the 32-team
data (teams 16-31 rosters, names, ratings, lineups) and then the launch
patches that make the bracket pick the selected pair:

  bank5  $9BFD  JSR $9B5F  -> JSR $FF60   (direct teams)
  bank5  $98C8  07        -> 02           (skip password, matchup)
  bank11 $8100  cursor 0  -> 16           (AUS/CUB start)
  fixed  $FF60  copy loop + selected pair $04EF/$04F0 -> $0650/$0651

The cosmetic round-label/top-row/codes/clear/layout steps are not applied:
the launch-prod bracket draw differs at `$8077` (WIN-tail mismatch).

Verified in romdev: the flow reaches scene 03 with the field rendered,
`$0489=0`, Top 1st, 0-0 (`docs/high-team-field.png`).
"""
import argparse
import os
import subprocess
import sys
import tempfile

HEADER = 16
PRG = 0x4000
BANK5 = 5
BANK11 = 11
FIXED = 15


def bank_off(bank, addr, base):
    return HEADER + bank * PRG + (addr - base)


def run_tool(name, *args):
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), name), *args]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="launch-prod.nes (bridge base)")
    ap.add_argument("roster_json", nargs="?", default="data/roster32.json")
    ap.add_argument("-o", "--out", default="build/launch32-high.nes")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="launch32-")
    s1 = os.path.join(tmp, "step1.nes")
    s2 = os.path.join(tmp, "step2.nes")
    s3 = os.path.join(tmp, "step3.nes")
    s4 = os.path.join(tmp, "step4.nes")

    run_tool("build_extra_rosters.py", args.rom, args.roster_json, "-o", s1)
    run_tool("build_names32.py", s1, "-o", s2)
    run_tool("build_ratings32.py", s2, "-o", s3)
    run_tool("build_lineups32.py", s3, "-o", s4)

    rom = bytearray(open(s4, "rb").read())
    if rom[4] <= FIXED:
        raise SystemExit(f"{s4}: {rom[4]} PRG banks, need 16")

    o = bank_off(BANK5, 0x9BFD, 0x8000)
    old = bytes(rom[o:o + 3])
    if old != bytes([0x20, 0x5F, 0x9B]):
        raise SystemExit(f"bank5 $9BFD: expected JSR $9B5F, found {old.hex(' ')}")
    rom[o:o + 3] = bytes([0x20, 0x60, 0xFF])

    o = bank_off(BANK5, 0x98C8, 0x8000)
    rom[o] = 0x02

    o = bank_off(BANK11, 0x8100, 0x8000)
    old = bytes(rom[o:o + 2])
    if old != bytes([0xA9, 0x00]):
        raise SystemExit(f"bank11 $8100: expected LDA #0, found {old.hex(' ')}")
    rom[o + 1] = 0x10

    o = bank_off(FIXED, 0xFF60, 0xC000)
    old = bytes(rom[o:o + 33])
    if old[:5] != bytes([0xA9, 0xFF, 0x8D, 0x4F, 0x06]):
        raise SystemExit(f"fixed $FF60: unexpected setup {old[:8].hex(' ')}")
    if old[21:25] != bytes([0xA2, 0x00, 0xA0, 0x00]):
        raise SystemExit(f"fixed $FF60: pack start moved: {old[21:25].hex(' ')}")
    pair = bytes([
        0xAD, 0xEF, 0x04,        # LDA $04EF
        0x8D, 0x50, 0x06,        # STA $0650
        0xAD, 0xF0, 0x04,        # LDA $04F0
        0x8D, 0x51, 0x06,        # STA $0651
    ])
    rom[o:o + 45] = old[:21] + pair + old[21:]

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: 32-team data + launch bridge + selected pair")


if __name__ == "__main__":
    main()
