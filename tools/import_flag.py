#!/usr/bin/env python3
"""Import a 24x24 PNG as one team's flag.

Writes 3x3 tiles into CHR bank $1B at the tile indices referenced by the
team's record at $976A, and rewrites those (tile, attr) pairs with flips
cleared. Palette bits are preserved.

    python3 tools/import_flag.py ROM --team 0 --png flag.png -o build/flag.nes
"""
import argparse

from PIL import Image

HEADER = 16
PRG = 0x4000
TABLE = 0x975A
RECORDS = 0x976A
CHR_BANK = 0x1B
DEFAULT_COLORS = [(0, 0, 0), (244, 232, 210), (188, 32, 48), (40, 70, 160)]


def file_off(addr):
    return HEADER + 4 * PRG + (addr - 0x8000)


def chr_off(tile):
    return HEADER + 8 * PRG + CHR_BANK * 0x1000 + tile * 16


def encode_tile(img, tx, ty, colors):
    rows0, rows1 = [], []
    for y in range(8):
        p0 = p1 = 0
        for x in range(8):
            px = img.getpixel((tx * 8 + x, ty * 8 + y))[:3]
            best, dist = 0, 1 << 30
            for i, c in enumerate(colors):
                d = sum((px[k] - c[k]) ** 2 for k in range(3))
                if d < dist:
                    best, dist = i, d
            p0 |= (best & 1) << (7 - x)
            p1 |= ((best >> 1) & 1) << (7 - x)
        rows0.append(p0)
        rows1.append(p1)
    return bytes(rows0 + rows1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--team", type=int, required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("-o", "--out", default="build/flag-import.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    img = Image.open(args.png).convert("RGB").resize((24, 24), Image.NEAREST)

    off = file_off(TABLE)
    record = rom[off + args.team]
    base = file_off(RECORDS) + record

    for s in range(9):
        tile = rom[base + s * 2]
        attr = rom[base + s * 2 + 1]
        tx, ty = s % 3, s // 3
        data = encode_tile(img, tx, ty, DEFAULT_COLORS)
        rom[chr_off(tile):chr_off(tile) + 16] = data
        rom[base + s * 2 + 1] = attr & 0x03  # keep palette, clear flips

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: team {args.team} flag -> record ${record:02X}, 9 tiles")


if __name__ == "__main__":
    main()
