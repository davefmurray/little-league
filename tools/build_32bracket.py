#!/usr/bin/env python3
"""Install a 32-team bracket, or a stock-compatible 16-team table.

Default (stock-safe):
  15-record 16-team table at fixed-bank $FC00
  $9BA4 (source A)     -> $FC00
  $9BB0 (destination)  -> $FC02
  $9C09 (display A)    -> $FC00

--state (experimental 32-team):
  31-record table at $FC00, seed 0..31 at $FD00
  slots $7700 (63), losses $7740 (32)  [clear of the $6000-$76FF cache]
  init at $9B5F rewritten to copy the seed and zero losses

    python3 tools/build_32bracket.py ROM -o build/32bracket.nes
    python3 tools/build_32bracket.py ROM --state -o build/32bracket-state.nes
"""
import argparse

HEADER = 16
PRG = 0x4000
TABLE = 0xFC00
SEED = 0xFD00
SLOTS = 0x7700
LOSSES = 0x7740
INIT = 0x9B5F
ADVANCE = 0x9B85

SRC_A = 0x9BA4
DEST = 0x9BB0
LOAD_A = 0x9BA7
STORE_A = 0x9BB3
INC_LOSS = 0x9BAB
DISP_A = 0x9C09
DISP_LOAD_A = 0x9C0C
DISP_LOAD_B = 0x9C12


def gen16():
    recs = []
    for i in range(8):
        recs.append((i * 2, i * 2 + 1, 16 + i))
    for i in range(4):
        recs.append((16 + i * 2, 16 + i * 2 + 1, 24 + i))
    for i in range(2):
        recs.append((24 + i * 2, 24 + i * 2 + 1, 28 + i))
    recs.append((28, 29, 30))
    return recs


def gen32():
    recs = []
    for i in range(16):
        recs.append((i * 2, i * 2 + 1, 32 + i))
    for i in range(8):
        recs.append((32 + i * 2, 32 + i * 2 + 1, 48 + i))
    for i in range(4):
        recs.append((48 + i * 2, 48 + i * 2 + 1, 56 + i))
    for i in range(2):
        recs.append((56 + i * 2, 56 + i * 2 + 1, 60 + i))
    recs.append((60, 61, 62))
    return recs


def bank5_off(addr):
    return HEADER + 5 * PRG + (addr - 0x8000)


def fixed_off(addr, nb):
    return HEADER + (nb - 1) * PRG + (addr - 0xC000)


def patch16(rom, addr, value):
    rom[bank5_off(addr):bank5_off(addr) + 2] = value.to_bytes(2, "little")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--state", action="store_true",
                    help="install the experimental 32-team PRG-RAM state")
    ap.add_argument("--keep-seed", action="store_true",
                    help="with --state, do not overwrite $7700 from $FD00; "
                         "use the seed the bracket screen already wrote")
    ap.add_argument("-o", "--out", default="build/32bracket.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    nb = rom[4]
    recs = gen32() if args.state else gen16()
    data = bytes(b for r in recs for b in r)

    rom[fixed_off(TABLE, nb):fixed_off(TABLE, nb) + len(data)] = data
    patch16(rom, SRC_A, TABLE)
    patch16(rom, DEST, TABLE + 2)
    patch16(rom, DISP_A, TABLE)

    if args.state:
        rom[fixed_off(SEED, nb):fixed_off(SEED, nb) + 32] = bytes(range(32))
        init = bytes([
            0xA2, 0x00,
            0xBD, SEED & 0xFF, SEED >> 8,
            0x9D, SLOTS & 0xFF, SLOTS >> 8,
            0xA9, 0x00,
            0x9D, LOSSES & 0xFF, LOSSES >> 8,
            0xE8,
            0xE0, 0x20,
            0xD0, 0xF0,
            0x4C, ADVANCE & 0xFF, ADVANCE >> 8,
        ])
        if args.keep_seed:
            # BD 00 FD -> BD 00 77: the copy becomes a self-copy, so the
            # bracket screen's human-first $7700 seed survives.
            init = bytearray(init)
            init[3] = SLOTS & 0xFF
            init[4] = SLOTS >> 8
        rom[bank5_off(INIT):bank5_off(INIT) + len(init)] = init

        patch16(rom, LOAD_A, SLOTS)
        patch16(rom, INC_LOSS, LOSSES)
        patch16(rom, STORE_A, SLOTS)
        patch16(rom, DISP_LOAD_A, SLOTS)
        patch16(rom, DISP_LOAD_B, SLOTS + 1)

    open(args.out, "wb").write(rom)
    mode = "32-team state" if args.state else "stock 16-team (safe)"
    print(f"wrote {args.out}: {mode}; fixed bank {nb - 1}; table ${TABLE:04X}")


if __name__ == "__main__":
    main()
