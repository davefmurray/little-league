#!/usr/bin/env python3
"""M4: static 32-team bracket screen in bank 11.

    python3 tools/build_bracket_screen.py build/dispatcher-test.nes -o build/bracket-screen.nes
"""
import argparse
import json

HEADER = 16
PRG = 0x4000
CODES = 0xB000
PALETTE = 0xB100
LIST = 0xB200


def run(addr, text):
    return bytes([addr >> 8, addr & 0xFF]) + text.encode("ascii") + b"\xFE"


def build_list(teams):
    out = bytearray()
    labels = "R32   R16   QF    SF    F".ljust(32)[:32]
    out += run(0x2048, labels)
    out += run(0x2068, "32 TEAM BRACKET")
    for i, t in enumerate(teams):
        col = i % 4
        row = 5 + (i // 4) * 2
        out += run(0x2000 + row * 32 + 1 + col * 8, t["code"])
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--loop-to", type=lambda s: int(s, 0))
    ap.add_argument("-o", "--out", default="build/bracket-screen.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    teams = json.load(open("data/teams32.json"))["teams"]
    listing = build_list(teams)
    if len(listing) > 250:
        raise SystemExit(f"display list too long: {len(listing)}")

    code = bytes([
        0xA9, 0x00, 0x8D, 0x00, 0x20,
        0x8D, 0x01, 0x20,
        0xA9, 0x1E, 0x20, 0x02, 0xC1,
        0xA9, 0x00, 0x20, 0x1C, 0xC1,
        0xA9, 0x01, 0x20, 0x34, 0xC1,
        0xA9, 0x3F, 0x8D, 0x06, 0x20,
        0xA9, 0x00, 0x8D, 0x06, 0x20,
        0xA2, 0x00,
        0xBD, PALETTE & 0xFF, PALETTE >> 8,
        0x8D, 0x07, 0x20,
        0xE8, 0xE0, 0x20, 0xD0, 0xF5,
        0xA2, 0x00,
        0xBD, LIST & 0xFF, LIST >> 8,
        0x9D, 0x00, 0x03,
        0xE8, 0xE0, len(listing), 0xD0, 0xF5,
        0xA9, 0x00, 0x8D, 0x40, 0xC0,
        0xA9, len(listing), 0x85, 0x32,
        0x20, 0x3A, 0xC5,
        0xA9, 0x00, 0x8D, 0x05, 0x20, 0x8D, 0x05, 0x20,
        0xA9, 0x1E, 0x8D, 0x01, 0x20,
        0x4C, 0x00, 0x80,
    ])
    code = bytearray(code)
    loop = args.loop_to if args.loop_to is not None else 0x8000 + len(code) - 3
    code[-3:] = bytes([0x4C, loop & 0xFF, loop >> 8])
    code = bytes(code)

    off = HEADER + 11 * PRG
    rom[off:off + len(code)] = code
    codes = b"".join(t["code"].ljust(4).encode("ascii") for t in teams)
    rom[off + (CODES - 0x8000):off + (CODES - 0x8000) + len(codes)] = codes[:128]
    pal = bytes([0x0F, 0x30, 0x16, 0x12] + [0] * 12 +
                [0x0F, 0x30, 0x16, 0x12] + [0] * 12)
    rom[off + (PALETTE - 0x8000):off + (PALETTE - 0x8000) + 32] = pal
    rom[off + (LIST - 0x8000):off + (LIST - 0x8000) + len(listing)] = listing

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: bank11 screen, list {len(listing)} bytes")


if __name__ == "__main__":
    main()
