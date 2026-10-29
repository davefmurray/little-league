#!/usr/bin/env python3
"""Stock Little League character graphics, decoded from ROM bytes the way the game composes them.

The intro pictures are sprites. Bank 5 $AEE6 writes all 64 OAM entries of one 64x64 picture as an
8x8 grid from its origin ($B1E8): tile ids in CHR $14 from a 64-byte map ($B1F6 pointers), two-bit
palettes packed four to a byte, low bits first ($B204 pointers), and attribute $20 | palette, so every
sprite sits behind the background and none is flipped. Sprite palette record $8E (fixed $FA60, entry 4
of $ADD2, loaded by $C1A4) colors them. Pixel value 0 is transparent: the black outlines and dark hair
are the intro's $0F backdrop showing through, so a mask must keep the source zeros a figure owns.

The stands crowd is background: 2x2 metatiles of CHR $10 colored by background palette record $15
(fixed $F930). Every tile id and color is a ROM byte; the order of the metatiles comes from the
crowd-lineup screenshot, and the manifest records it as observed, not as a ROM table.

PINS holds the SHA-256 of every byte range read here, in build_draw32.check_guards' digest form, at
the project's 16-bank addresses. The same bytes hold in the 8-bank stock ROM's own layout and in every
stage from direct31 through scoreart32, so the stage extracts from its own accepted scoreart32 input.
"""
from dataclasses import dataclass

from build_draw32 import check_guards, locate, read, sha256
from build_teamnames32 import HEADER, ROM_SIZE
import menu32_convert as menu

INTRO_BANK, FIXED_BANK = 5, 15
INTRO_CHR, STANDS_CHR = 0x14, 0x10
ORIGINS, MAPS, SELECTORS = 0xB1E8, 0xB1F6, 0xB204
INTRO_PALETTE = 0xFA60        # sprite palette record $8E
STANDS_PALETTE = 0xF930       # background palette record $15
INTRO_BACKDROP = 0x0F
PRIORITY = 0x20               # the attribute bit $AEE6 ORs into every intro sprite
PANELS = ("glove", "batter", "celebrate-a", "celebrate-b", "cheer-a", "cheer-b", "pair")
PANEL_SIZE = 64

PINS = (
    ("intro script, origins, map and selector pointers $B1B7-$B211", INTRO_BANK, 0xB1B7, 0x5B,
     "6124b68ced644bca4128461dac98ebbebb09a9e1929253396c6df0355b8fc10d"),
    ("intro tile maps $B212-$B3D1", INTRO_BANK, 0xB212, 0x1C0,
     "e9725e5aa1200f0ba2b8bd71eee3b1c7533ec126aede1a59b1ba0199d4c99fee"),
    ("intro sprite palette selectors $B3D2-$B441", INTRO_BANK, 0xB3D2, 0x70,
     "4ee8b9c27c92ec2c4b969c30415b59c7a618701bbe13e4c3a17ff3f54c0fe782"),
    ("intro OAM writer $AEE6-$AF68", INTRO_BANK, 0xAEE6, 0x83,
     "7954a0ac7a6d08542dd0a76189077311c81388e72f4c09150698bef1858803c8"),
    ("intro CHR selects $AD34-$AD3B", INTRO_BANK, 0xAD34, 8,
     "e10b83263f0edd2d706d4a372c3f1667b3a8e99f126b5dc7ab45cdab72d4e873"),
    ("intro palette records by sub-scene $ADD2-$ADDD", INTRO_BANK, 0xADD2, 12,
     "6ad8411f4178b8bb93df8a28323b9b9c9823c227eff2bff80c5f509751e12ff0"),
    ("sprite palette record $8E, fixed $FA60-$FA6F", FIXED_BANK, INTRO_PALETTE, 16,
     "99d90b3940c518e0bd7a2fd28d81d7eff3a69aca0f3364c3c8e0ba72a3bd1c61"),
    ("stands palette record $15, fixed $F930-$F93F", FIXED_BANK, STANDS_PALETTE, 16,
     "1a800560229f6a56568e17de50cdb2f423f870b7b0f2e9ddf17f084ed6612f63"),
    ("CHR $14 intro sprites", "chr", INTRO_CHR * 0x1000, 0x1000,
     "2dea85c47810d1ccb6c686e1a29dd9828765386b692faafb341e3cee40179f8e"),
    ("CHR $10 stands crowd", "chr", STANDS_CHR * 0x1000, 0x1000,
     "e7075fe93e716a01b2ca9a19c048b2965820493813d12aada74d264b88dc58e8"),
)


def check_pins(rom):
    """Raise unless `rom` is a full-size image whose every pinned source range holds the stock bytes."""
    if len(rom) != ROM_SIZE or rom[:len(HEADER)] != HEADER:
        raise ValueError("expected the project's iNES header and ROM size")
    check_guards(rom, (), PINS)


@dataclass(frozen=True)
class Pixel:
    """A source pixel as the stock PPU shows it."""
    value: int                # 2-bit pattern value; 0 is transparent (sprites) or backdrop (background)
    color: int                # NES color shown; a transparent intro pixel shows the $0F backdrop


@dataclass(frozen=True)
class Composition:
    """A decoded stock picture and the provenance of each of its 8x8 cells."""
    pixels: tuple             # rows of Pixel
    cells: dict               # (col, row) -> JSON-ready source record


def where(bank, address, size=1):
    return {"bank": bank, "address": f"${address:04X}", "size": size}


def tile_record(chr_bank, tile, rom):
    start = chr_bank * 0x1000 + 16 * tile
    return {"chr_bank": chr_bank, "tile": tile, "chr_offset": locate("chr", start),
            "tile_sha256": sha256(read(rom, "chr", start, 16))}


def record_colors(rom, address, palette):
    """The three colors of palette `palette` in the 16-byte palette record at fixed `address`."""
    return tuple(read(rom, FIXED_BANK, address + 4 * palette + 1, 3))


def intro_panel(rom, k):
    """Intro picture k exactly as $AEE6 writes its OAM, over the intro's $0F backdrop."""
    if not 0 <= k < len(PANELS):
        raise ValueError(f"intro panel {k} does not exist")
    pointer = lambda table: int.from_bytes(read(rom, INTRO_BANK, table + 2 * k, 2), "little")  # noqa: E731
    tiles, selectors = pointer(MAPS), pointer(SELECTORS)
    x0, y0 = read(rom, INTRO_BANK, ORIGINS + 2 * k, 2)
    pixels = [[None] * PANEL_SIZE for _ in range(PANEL_SIZE)]
    cells = {}
    for i in range(64):
        col, row = i % 8, i // 8
        tile = read(rom, INTRO_BANK, tiles + i, 1)[0]
        palette = (read(rom, INTRO_BANK, selectors + i // 4, 1)[0] >> 2 * (i % 4)) & 3
        colors = record_colors(rom, INTRO_PALETTE, palette)
        values = menu.decode(read(rom, "chr", INTRO_CHR * 0x1000 + 16 * tile, 16))
        for y in range(8):
            for x in range(8):
                v = values[y][x]
                pixels[8 * row + y][8 * col + x] = Pixel(v, colors[v - 1] if v else INTRO_BACKDROP)
        cells[(col, row)] = {
            **tile_record(INTRO_CHR, tile, rom),
            "tile_from": where(INTRO_BANK, tiles + i),
            "palette": palette,
            "palette_from": {**where(INTRO_BANK, selectors + i // 4), "shift": 2 * (i % 4)},
            "colors_from": where(FIXED_BANK, INTRO_PALETTE + 4 * palette + 1, 3),
            "oam": {"x": x0 + 8 * col, "y": y0 + 8 * row, "attribute": PRIORITY | palette,
                    "hflip": False, "vflip": False, "behind_background": True},
        }
    source = {"kind": "intro-panel", "panel": k, "name": PANELS[k], "tile_map": where(INTRO_BANK, tiles, 64),
              "selectors": where(INTRO_BANK, selectors, 16), "origin": [x0, y0],
              "writer": where(INTRO_BANK, 0xAEE6, 0x83)}
    return source, Composition(tuple(map(tuple, pixels)), cells)


def stands_block(rom, metatiles, rows):
    """Metatile rows of CHR $10 in palette record $15, as the background shows them.

    `metatiles` maps a key to ((top-left, top-right, bottom-left, bottom-right), palette); `rows` holds keys.
    """
    backdrop = read(rom, FIXED_BANK, STANDS_PALETTE, 1)[0]
    height, width = 16 * len(rows), 16 * len(rows[0])
    pixels = [[None] * width for _ in range(height)]
    cells = {}
    for j, row in enumerate(rows):
        for i, key in enumerate(row):
            tiles, palette = metatiles[key]
            colors = record_colors(rom, STANDS_PALETTE, palette)
            for q, tile in enumerate(tiles):
                col, cell_row = 2 * i + (q & 1), 2 * j + (q >> 1)
                values = menu.decode(read(rom, "chr", STANDS_CHR * 0x1000 + 16 * tile, 16))
                for y in range(8):
                    for x in range(8):
                        v = values[y][x]
                        pixels[8 * cell_row + y][8 * col + x] = Pixel(v, colors[v - 1] if v else backdrop)
                cells[(col, cell_row)] = {**tile_record(STANDS_CHR, tile, rom), "metatile": key, "quadrant": q,
                                          "palette": palette,
                                          "colors_from": where(FIXED_BANK, STANDS_PALETTE + 4 * palette + 1, 3)}
    return Composition(tuple(map(tuple, pixels)), cells)
