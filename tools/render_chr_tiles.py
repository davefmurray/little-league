#!/usr/bin/env python3
"""Render 8x8 CHR tiles from a 4 KiB CHR bank to a PNG grid.

    python3 tools/render_chr_tiles.py build/direct31.nes --bank 0x1B \
        --tiles 35,37,48,4a,4b,4d,4f,51,53,55,65,67,68,6a,6c,6e \
        -o /tmp/alphabet.png

Pure Python (zlib + struct); no PIL. The grid is row-major, 4 columns.
"""
import argparse
import struct
import zlib

HEADER = 16


def png_gray(width, height, rows):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--bank", type=lambda s: int(s, 0), required=True,
                    help="4 KiB CHR bank index")
    ap.add_argument("--tiles", required=True, help="comma-separated tile indices")
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("-o", "--out", default="chr-tiles.png")
    args = ap.parse_args()

    rom = open(args.rom, "rb").read()
    prg = rom[4]
    chr_base = HEADER + prg * 0x4000
    base = chr_base + args.bank * 0x1000
    if base + 0x1000 > len(rom):
        raise SystemExit(f"CHR bank {args.bank} is outside the ROM")

    tiles = [int(t, 16) for t in args.tiles.split(",")]
    scale, gap, cols = args.scale, 4, 4
    cell = 8 * scale
    rows = (len(tiles) + cols - 1) // cols
    w = cols * (cell + gap) + gap
    h = rows * (cell + gap) + gap
    img = [[255] * w for _ in range(h)]

    for i, tile in enumerate(tiles):
        o = base + (tile & 0xFF) * 16
        lo, hi = rom[o:o + 8], rom[o + 8:o + 16]
        r, c = divmod(i, cols)
        x0 = gap + c * (cell + gap)
        y0 = gap + r * (cell + gap)
        for y in range(8):
            for x in range(8):
                bit = 7 - x
                v = ((lo[y] >> bit) & 1) | (((hi[y] >> bit) & 1) << 1)
                if v:
                    for dy in range(scale):
                        for dx in range(scale):
                            img[y0 + y * scale + dy][x0 + x * scale + dx] = 0

    open(args.out, "wb").write(png_gray(w, h, img))
    print(f"wrote {args.out}: {w}x{h}, bank {args.bank}, {len(tiles)} tiles")


if __name__ == "__main__":
    main()
