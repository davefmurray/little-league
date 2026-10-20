#!/usr/bin/env python3
"""Render the live NES nametable with the live CHR to a PNG.

    python3 tools/render_ppu.py -o docs/password-screen-live.png --pattern 0x1000

Reads the emulator's PPU regions through the local romdev server:
`nes_nametables` (2 KB), `nes_chr` (8 KB), `nes_palette` (32 bytes).
Useful when a save state doesn't expose the CHR latches.
"""
import argparse
import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import romdev

NES_PALETTE = [
    (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136),
    (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
    (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
    (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0),
]


def png_rgb(width, height, rows):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(v for px in r for v in px) for r in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="/tmp/ppu.png")
    ap.add_argument("--pattern", type=lambda s: int(s, 0), default=0x1000,
                    choices=(0x0000, 0x1000))
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--gray", action="store_true")
    args = ap.parse_args()

    nt = bytes.fromhex(romdev.call("memory", {
        "op": "read", "region": "nes_nametables", "offset": 0,
        "length": 0x800})["hex"])
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        chr_path = f.name
    romdev.call("memory", {"op": "read", "region": "nes_chr",
                           "offset": 0, "length": 0x2000,
                           "outputPath": chr_path})
    chr_data = open(chr_path, "rb").read()
    os.unlink(chr_path)
    pal = bytes.fromhex(romdev.call("memory", {
        "op": "read", "region": "nes_palette", "offset": 0,
        "length": 32})["hex"])

    scale = args.scale
    W, H = 256 * scale, 240 * scale
    img = [[(0, 0, 0)] * W for _ in range(H)]
    for row in range(30):
        for col in range(32):
            tile = nt[row * 32 + col]
            o = args.pattern + tile * 16
            if o + 16 > len(chr_data):
                continue
            lo, hi = chr_data[o:o + 8], chr_data[o + 8:o + 16]
            attr = nt[0x3C0 + (row // 4) * 8 + (col // 4)]
            shift = ((row % 4) // 2) * 4 + ((col % 4) // 2) * 2
            sub = (attr >> shift) & 3
            for y in range(8):
                for x in range(8):
                    bit = 7 - x
                    v = ((lo[y] >> bit) & 1) | (((hi[y] >> bit) & 1) << 1)
                    if args.gray:
                        c = (0, 85, 170, 255)[v]
                    else:
                        idx = pal[sub * 4 + v] & 0x3F
                        c = NES_PALETTE[idx % 16]
                    for dy in range(scale):
                        for dx in range(scale):
                            img[row * 8 * scale + y * scale + dy][
                                col * 8 * scale + x * scale + dx] = c
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    open(args.out, "wb").write(png_rgb(W, H, img))
    print(f"wrote {args.out}: {W}x{H}, pattern ${args.pattern:04X}")


if __name__ == "__main__":
    main()
