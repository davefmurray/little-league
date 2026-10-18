#!/usr/bin/env python3
"""Extract the 16 team flag/label blocks from their per-team 4 KiB CHR banks.

Team -> CHR bank comes from the 6-byte table at $FB4E; the 24-byte sprite
record (12 x tile,attr) comes from the offset table at $975A into $976A.

    python3 tools/extract_flags.py ROM
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

HEADER = 16
PRG_BANK = 0x4000
PALETTES = [
    [None, (244, 232, 210), (188, 32, 48), (12, 36, 28)],
    [None, (224, 166, 60), (40, 70, 160), (12, 36, 28)],
    [None, (30, 120, 70), (244, 232, 210), (12, 36, 28)],
    [None, (200, 90, 30), (90, 40, 120), (12, 36, 28)],
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/assets/flags")
    args = ap.parse_args()

    rom = open(args.rom, "rb").read()
    prg = rom[4]
    prg_data = rom[HEADER:HEADER + prg * PRG_BANK]
    chr_data = rom[HEADER + prg * PRG_BANK:]
    fixed = prg_data[(prg - 1) * PRG_BANK:]

    def fb(addr):
        return fixed[addr - 0xC000]

    ids = [fb(0x975A + i) for i in range(16)]
    banks = [[fb(0xFB4E + t * 6 + i) for i in range(4)] for t in range(16)]
    tab = [fb(0x976A + i) for i in range(0x180)]
    teams = json.load(open("data/teams32.json"))["teams"]
    os.makedirs(args.out, exist_ok=True)

    tiles = []
    for team in range(16):
        bank = 0x1B
        if bank >= 0xFF:
            continue
        o = ids[team]
        img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
        px = img.load()
        for s in range(9):
            tile, attr = tab[o + s * 2], tab[o + s * 2 + 1]
            pal = PALETTES[attr & 3]
            hflip = bool(attr & 0x40)
            vflip = bool(attr & 0x80)
            off = bank * 0x1000 + tile * 16
            if off + 16 > len(chr_data):
                continue
            cx, cy = (s % 3) * 8, (s // 3) * 8
            for y in range(8):
                p0, p1 = chr_data[off + y], chr_data[off + 8 + y]
                for x in range(8):
                    bit = 7 - x
                    v = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                    if v:
                        px[cx + (7 - x if hflip else x), cy + (7 - y if vflip else y)] = pal[v]
        big = img.resize((96, 96), Image.NEAREST)
        name = teams[team]["name"].split()[0].lower()
        big.save(os.path.join(args.out, f"{team:02d}-{name}.png"))
        small = img.resize((16, 16), Image.LANCZOS)
        small.save(os.path.join(args.out, f"16-{team:02d}-{name}.png"))
        tiles.append((team, teams[team]["name"], big))

    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 112, rows * 150), (10, 20, 16))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, (team, name, img) in enumerate(tiles):
        x, y = (i % cols) * 112, (i // cols) * 150
        sheet.paste(img, (x + 8, y + 18), img)
        d.text((x + 8, y + 4), f"{team:02d} {name}", font=font, fill=(224, 166, 60))
    sheet.save(os.path.join(args.out, "sheet.png"))
    print(f"wrote {len(tiles)} flags to {args.out}, sheet.png")


if __name__ == "__main__":
    main()
