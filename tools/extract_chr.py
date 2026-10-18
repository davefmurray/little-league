#!/usr/bin/env python3
"""Extract every CHR tile from an iNES ROM.

Writes:
  build/assets/chr-bank-XX.png   256 tiles per 4 KiB bank, 16x16 grid
  build/assets/chr-atlas.png     all banks in one contact sheet
  build/assets/chr.json          bank/tile inventory, empty + duplicate counts

    python3 tools/extract_chr.py ROM
"""
import argparse
import hashlib
import json
import os

from PIL import Image, ImageDraw, ImageFont

HEADER = 16
PRG_BANK = 0x4000
CHR_BANK = 0x2000  # 8 KiB
TILE = 16
COLORS = [(12, 36, 28), (244, 232, 210), (224, 166, 60), (122, 60, 44)]


def render_bank(data, bank, scale=2):
    img = Image.new("RGB", (16 * 9 + 1, 16 * 9 + 1), (6, 14, 11))
    d = ImageDraw.Draw(img)
    for t in range(256):
        off = bank * 0x1000 + t * TILE
        chunk = data[off:off + TILE]
        if len(chunk) < TILE:
            break
        x = 1 + (t % 16) * 9
        y = 1 + (t // 16) * 9
        for py in range(8):
            p0, p1 = chunk[py], chunk[py + 8]
            for px in range(8):
                bit = 7 - px
                v = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                d.point((x + px, y + py), fill=COLORS[v])
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/assets")
    args = ap.parse_args()

    rom = open(args.rom, "rb").read()
    prg = rom[4]
    chr_data = rom[HEADER + prg * PRG_BANK:]
    chr_data = chr_data[: (len(chr_data) // CHR_BANK) * CHR_BANK]
    banks = len(chr_data) // 0x1000
    os.makedirs(args.out, exist_ok=True)

    manifest = {"chr_bytes": len(chr_data), "banks_4k": banks, "banks": []}
    seen = {}
    thumbs = []
    for bank in range(banks):
        img = render_bank(chr_data, bank)
        img.save(os.path.join(args.out, f"chr-bank-{bank:02d}.png"))
        thumbs.append((bank, img))
        empty = 0
        dup = 0
        for t in range(256):
            off = bank * 0x1000 + t * TILE
            chunk = chr_data[off:off + TILE]
            if chunk == b"\x00" * TILE:
                empty += 1
                continue
            h = hashlib.sha1(chunk).hexdigest()
            if h in seen:
                dup += 1
            else:
                seen[h] = (bank, t)
        manifest["banks"].append({
            "bank": bank, "empty_tiles": empty, "duplicate_tiles": dup,
            "unique_tiles": 256 - empty - dup,
        })

    cols, cell = 4, 148
    rows = (banks + cols - 1) // cols
    atlas = Image.new("RGB", (cols * cell, rows * cell), (6, 14, 11))
    d = ImageDraw.Draw(atlas)
    font = ImageFont.load_default()
    for i, (bank, img) in enumerate(thumbs):
        x = (i % cols) * cell
        y = (i // cols) * cell
        atlas.paste(img, (x + 2, y + 10))
        d.text((x + 2, y), f"bank {bank:02d}  4K", font=font, fill=(224, 166, 60))
    atlas.save(os.path.join(args.out, "chr-atlas.png"))
    manifest["atlas"] = "chr-atlas.png"

    with open(os.path.join(args.out, "chr.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"{banks} 4K banks, {len(chr_data)} CHR bytes -> {args.out}")
    print(f"atlas: {args.out}/chr-atlas.png")
    for b in manifest["banks"][:4]:
        print(f"  bank {b['bank']:02d}: empty {b['empty_tiles']}, dup {b['duplicate_tiles']}")


if __name__ == "__main__":
    main()
