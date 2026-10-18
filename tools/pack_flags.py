#!/usr/bin/env python3
"""Prototype: pack 24x24 flags into CHR bank 0's empty tiles.

Bank 0 has 71 empty tiles (16 x $00 bytes). A flag is 3x3 = 9 tiles, so this
prototype packs **7 flags = 63 tiles**. Eight flags would need 72, one more than
the empty-tile budget; that constraint is deliberate and documented.

    python3 tools/pack_flags.py ROM -o build/flags-chr.nes
"""
import argparse
import json

from PIL import Image, ImageDraw

HEADER = 16
PRG_BANK = 0x4000
TILE = 16

# 4-colour prototype palette: 0 bg, 1 white, 2 red, 3 blue
COLORS = [(12, 36, 28), (244, 232, 210), (188, 32, 48), (40, 70, 160)]


def flag_images():
    W = H = 24
    specs = [
        ("JPN", (244, 232, 210), (188, 32, 48)),
        ("USA", (188, 32, 48), (244, 232, 210)),
        ("PEN", (40, 70, 160), (244, 232, 210)),
        ("TPE", (30, 120, 70), (244, 232, 210)),
        ("KOR", (244, 232, 210), (188, 32, 48)),
        ("NY", (40, 70, 160), (244, 232, 210)),
        ("CAL", (224, 166, 60), (40, 70, 160)),
    ]
    out = []
    for name, a, b in specs:
        img = Image.new("RGB", (W, H), a)
        d = ImageDraw.Draw(img)
        if name == "JPN":
            d.ellipse([7, 7, 16, 16], fill=b)
        elif name == "USA":
            for y in range(0, H, 6):
                d.rectangle([0, y, W, y + 2], fill=b)
            d.rectangle([0, 0, 10, 10], fill=(40, 70, 160))
        elif name == "PEN":
            d.rectangle([8, 0, 15, H], fill=b)
        elif name == "TPE":
            d.ellipse([6, 6, 17, 17], fill=b)
        elif name == "KOR":
            d.ellipse([8, 8, 15, 15], fill=(40, 70, 160))
        elif name == "NY":
            d.rectangle([0, 0, 7, H], fill=b)
            d.rectangle([16, 0, 23, H], fill=b)
        elif name == "CAL":
            d.rectangle([0, 16, W, 23], fill=b)
        out.append((name, img))
    return out


def to_tiles(img):
    tiles = []
    for ty in range(3):
        for tx in range(3):
            rows = []
            for y in range(8):
                p0 = p1 = 0
                for x in range(8):
                    r, g, b = img.getpixel((tx * 8 + x, ty * 8 + y))
                    if (r, g, b) == COLORS[1]:
                        v = 1
                    elif (r, g, b) == COLORS[2]:
                        v = 2
                    elif (r, g, b) == COLORS[3]:
                        v = 3
                    else:
                        v = 0
                    if v & 1:
                        p0 |= 1 << (7 - x)
                    if v & 2:
                        p1 |= 1 << (7 - x)
                rows.append((p0, p1))
            tiles.append(bytes([r[0] for r in rows] + [r[1] for r in rows]))
    return tiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/flags-chr.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    chr_base = HEADER + rom[4] * PRG_BANK
    bank0 = chr_base
    empty = [t for t in range(256) if rom[bank0 + t * 16:bank0 + t * 16 + 16] == b"\x00" * 16]
    print(f"empty tiles in CHR bank 0: {len(empty)}")
    if len(empty) < 63:
        raise SystemExit("not enough empty tiles for 7 flags")

    mapping = {}
    slot = 0
    for name, img in flag_images():
        tiles = to_tiles(img)
        for t in tiles:
            rom[bank0 + empty[slot] * 16:bank0 + empty[slot] * 16 + 16] = t
            slot += 1
        mapping[name] = {"tile_base": empty[slot - 9], "tiles": empty[slot - 9:slot]}

    open(args.out, "wb").write(rom)
    with open("build/flags-chr.json", "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"packed 7 flags / {slot} tiles into {args.out}")
    for name, m in mapping.items():
        print(f"  {name}: base tile ${m['tile_base']:02X}")


if __name__ == "__main__":
    main()
