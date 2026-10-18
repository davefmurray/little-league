#!/usr/bin/env python3
"""Generate 32 flags at 24x16 (3x2 tiles) and pack them into bank 10.

Layout in bank 10:
  $A000  32 flags x 6 tiles x 16 bytes = 3,072 bytes
  $AC00  48 destination tile slots in CHR bank 0 (empty tiles)
  $AC40  four sprite/background palettes (16 bytes)

    python3 tools/build_flags32.py build/32x20-ui.nes data/teams32.json -o build/flags32.nes
"""
import argparse
import json

HEADER = 16
PRG_BANK = 0x4000
TILE = 16
BANK = 10
TILES_AT = 0xA000
SLOTS_AT = 0xAC00
PAL_AT = 0xAC40

COLORS = [(12, 36, 28), (244, 232, 210), (188, 32, 48), (40, 70, 160)]


def design(i, w=24, h=16):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), COLORS[1])
    d = ImageDraw.Draw(img)
    kind = i % 6
    if kind == 0:
        d.ellipse([7, 3, 16, 12], fill=COLORS[2])
    elif kind == 1:
        for y in range(0, h, 5):
            d.rectangle([0, y, w, y + 2], fill=COLORS[2])
        d.rectangle([0, 0, 9, 7], fill=COLORS[3])
    elif kind == 2:
        d.rectangle([8, 0, 15, h], fill=COLORS[3])
    elif kind == 3:
        d.rectangle([0, 0, w, 7], fill=COLORS[2])
        d.rectangle([0, 8, w, 15], fill=COLORS[3])
    elif kind == 4:
        d.rectangle([0, 0, 7, h], fill=COLORS[2])
        d.rectangle([16, 0, 23, h], fill=COLORS[2])
        d.rectangle([9, 4, 14, 11], fill=COLORS[3])
    else:
        d.ellipse([5, 2, 18, 13], outline=COLORS[2], width=2)
        d.rectangle([10, 6, 13, 9], fill=COLORS[3])
    return img


def tiles_of(img):
    out = []
    for ty in range(2):
        for tx in range(3):
            rows = []
            for y in range(8):
                p0 = p1 = 0
                for x in range(8):
                    px = img.getpixel((tx * 8 + x, ty * 8 + y))
                    v = 0
                    if px == COLORS[1]:
                        v = 1
                    elif px == COLORS[2]:
                        v = 2
                    elif px == COLORS[3]:
                        v = 3
                    p0 |= (v & 1) << (7 - x)
                    p1 |= ((v >> 1) & 1) << (7 - x)
                rows.append((p0, p1))
            out.append(bytes([r[0] for r in rows] + [r[1] for r in rows]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("teams")
    ap.add_argument("-o", "--out", default="build/flags32.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    teams = json.load(open(args.teams))["teams"]
    b10 = HEADER + BANK * PRG_BANK

    # 48 empty CHR bank-0 slots
    chr_base = HEADER + rom[4] * PRG_BANK
    empty = [t for t in range(256)
             if not (0x20 <= t <= 0x5F)
             and rom[chr_base + t * TILE:chr_base + t * TILE + TILE] == b"\x00" * TILE]
    if len(empty) < 48:
        raise SystemExit(f"only {len(empty)} empty tiles")
    slots = empty[:48]

    data = bytearray()
    for i in range(32):
        for t in tiles_of(design(i)):
            data += t
    rom[b10 + (TILES_AT - 0x8000):b10 + (TILES_AT - 0x8000) + len(data)] = data
    rom[b10 + (SLOTS_AT - 0x8000):b10 + (SLOTS_AT - 0x8000) + 48] = bytes(slots)
    pal = bytes([0x0F, 0x30, 0x16, 0x12,  0x0F, 0x30, 0x1A, 0x28,
                 0x0F, 0x30, 0x12, 0x28,  0x0F, 0x30, 0x16, 0x1A])
    rom[b10 + (PAL_AT - 0x8000):b10 + (PAL_AT - 0x8000) + 16] = pal
    open(args.out, "wb").write(rom)
    print(f"packed 32 flags into bank 10 ${TILES_AT:04X}; {len(slots)} CHR slots")


if __name__ == "__main__":
    main()
