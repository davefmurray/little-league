#!/usr/bin/env python3
"""Convert the pxl menu art into data/menu32/menuassets.json.

    .venv/bin/python tools/menu32_convert.py --rom build/visualtables32.nes
    .venv/bin/python tools/menu32_convert.py --rom build/visualtables32.nes \
        --pxl build/vendor/claude-pxl --previews build/menu32-previews

--pxl first re-renders art/menu32/menu32.px.js with the pinned pxl checkout
(Node >= 22.18) and refreshes the committed PNGs in art/menu32/out. Without it
the committed PNGs are converted as they are.

The converter enforces what pxl cannot: exact NES colors, opaque or fully clear
pixels, one palette per 16x16 attribute cell, blank art under text and runtime
regions, and at most 256 tiles in CHR bank $19. Stock font glyphs keep their
ASCII tile ids and are referenced, not copied: the stage copies them from CHR
bank $00 at build time. The module also holds the screen oracle the tests and
renderer use: the nametable, attributes and sprites a correct runtime draws.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image
from build_visualtables32 import protect_output as protect_prior_output

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art/menu32"
SOURCE = ART / "menu32.px.js"
LAYOUT = ART / "layout.json"
PNGS = ART / "out"
LOCK = ART / "PXL.json"
TEAMS = ROOT / "data/teams32.json"
ASSETS = ROOT / "data/menu32/menuassets.json"

FORMAT = "menuassets/1"
CHR_BANK = 0x19
FONT_BANK = 0x00
HEADER = 16
CHR_START = HEADER + 16 * 0x4000
BLANK = 0x20
NAME_WIDTH = 14
REGION_WIDTH = 7

# FCEUX's default palette in its native 6-bit form. The project emulator shows each
# channel as (v << 2) | (v >> 4); the converter and previews use exactly that.
FCEUX_6BIT = (
    (29, 29, 29), (9, 6, 35), (0, 0, 42), (17, 0, 39), (35, 0, 29), (42, 0, 4), (41, 0, 0), (31, 2, 0),
    (16, 11, 0), (0, 17, 0), (0, 20, 0), (0, 15, 5), (6, 15, 23), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (47, 47, 47), (0, 28, 59), (8, 14, 59), (32, 0, 60), (47, 0, 47), (57, 0, 22), (54, 10, 0), (50, 19, 3),
    (34, 28, 0), (0, 37, 0), (0, 42, 0), (0, 36, 14), (0, 32, 34), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (63, 63, 63), (15, 47, 63), (23, 37, 63), (51, 34, 63), (61, 30, 63), (63, 29, 45), (63, 29, 24), (63, 38, 14),
    (60, 47, 15), (32, 52, 4), (19, 55, 18), (22, 62, 38), (0, 58, 54), (30, 30, 30), (0, 0, 0), (0, 0, 0),
    (63, 63, 63), (42, 57, 63), (49, 53, 63), (53, 50, 63), (63, 49, 63), (63, 49, 54), (63, 47, 44), (63, 54, 42),
    (63, 57, 40), (56, 63, 40), (42, 60, 47), (44, 63, 51), (39, 63, 60), (49, 49, 49), (0, 0, 0), (0, 0, 0),
)
NES_RGB = tuple(tuple((v << 2) | (v >> 4) for v in rgb) for rgb in FCEUX_6BIT)
PALETTE_TABLE = "fceux-default-6bit, channel (v<<2)|(v>>4)"


class AssetError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def nes_color(text):
    value = int(text, 16)
    if not 0 <= value < 0x40 or value in (0x0D, 0x0E) or (value & 0x0F) in (0x0E,):
        raise AssetError(f"unsupported NES color ${value:02X}")
    return value



def load_png(path, allowed, opaque, size):
    """Rows of NES color indices; None marks a fully clear pixel (sprites only)."""
    image = Image.open(path).convert("RGBA")
    if image.size != size:
        raise AssetError(f"{path.name}: {image.size[0]}x{image.size[1]}, expected {size[0]}x{size[1]}")
    by_rgb = {NES_RGB[c]: c for c in allowed}
    if len(by_rgb) != len(set(allowed)):
        raise AssetError("palette colors must have distinct RGB values")
    width, height = image.size
    pixels = image.load()
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0 and not opaque:
                row.append(None)
                continue
            if a != 255:
                raise AssetError(f"{path.name} ({x},{y}): partial or unexpected transparency")
            color = by_rgb.get((r, g, b))
            if color is None:
                raise AssetError(f"{path.name} ({x},{y}): #{r:02X}{g:02X}{b:02X} is not a palette color")
            row.append(color)
        rows.append(row)
    return width, height, rows


def tile_pixels(rows, tx, ty):
    return [rows[ty * 8 + y][tx * 8:tx * 8 + 8] for y in range(8)]


def encode(values):
    """An 8x8 grid of 2-bit values as 16 planar NES bytes."""
    lo = bytes(sum(((values[y][x] & 1) << (7 - x)) for x in range(8)) for y in range(8))
    hi = bytes(sum(((values[y][x] >> 1) << (7 - x)) for x in range(8)) for y in range(8))
    return lo + hi


def decode(pattern):
    return [[((pattern[y] >> (7 - x)) & 1) | (((pattern[y + 8] >> (7 - x)) & 1) << 1)
             for x in range(8)] for y in range(8)]


def to_values(pixels, palette, backdrop, where):
    lookup = {None: 0, backdrop: 0}
    for i, color in enumerate(palette):
        lookup.setdefault(color, i + 1)
    try:
        return [[lookup[c] for c in row] for row in pixels]
    except KeyError as missing:
        raise AssetError(f"{where}: color ${missing.args[0]:02X} is outside palette "
                         f"{' '.join(f'${c:02X}' for c in palette)}") from None



class TileBank:
    """256 tiles. Font glyphs sit at their ASCII ids; everything else dedups by pattern."""

    def __init__(self, font_patterns, glyphs):
        if font_patterns.get(BLANK) != bytes(16):
            raise AssetError("CHR $00 tile $20 is no longer blank")
        self.patterns, self.sources = {}, {}
        self.font = sorted(glyphs)
        for index in self.font:
            if index != BLANK and not any(font_patterns[index]):
                raise AssetError(f"stock font has no glyph for {chr(index)!r}")
            self.patterns[index] = font_patterns[index]
            self.sources[index] = f"font:{chr(index)}"
        self.lookup = {}
        self.order = [i for i in range(256) if i not in self.patterns]

    def intern(self, pattern, source):
        if pattern == bytes(16):
            return BLANK
        if pattern in self.lookup:
            return self.lookup[pattern]
        if not self.order:
            raise AssetError(f"CHR bank ${CHR_BANK:02X} is full at {source}")
        index = self.order.pop(0)
        self.patterns[index], self.sources[index] = pattern, source
        self.lookup[pattern] = index
        return index

    def chr(self):
        return b"".join(self.patterns.get(i, bytes(16)) for i in range(256))



def slot_cells(tree):
    """Heap slot -> (col, row) of its two-tile plate. Match m plays slots 2m and 2m+1."""
    row0, left, right = tree["row0"], tree["left"], tree["right"]
    cells = {}
    for s in range(32):
        side, k = s >> 4, s & 15
        cells[s] = ((right if side else left)[0], row0 + k)
    for i in range(16):
        side, j = i >> 3, i & 7
        cells[32 + i] = ((right if side else left)[1], row0 + 1 + 4 * (j >> 1) + (j & 1))
    for i in range(8):
        side, j = i >> 2, i & 3
        cells[48 + i] = ((right if side else left)[2], row0 + 3 + 8 * (j >> 1) + (j & 1))
    for i in range(4):
        side, j = i >> 1, i & 1
        cells[56 + i] = ((right if side else left)[3], row0 + 7 + j)
    cells[60], cells[61] = tuple(tree["final"][0]), tuple(tree["final"][1])
    cells[62] = tuple(tree["champion"])
    return cells


def slot_palette(choices, slot):
    """First-round pairs alternate plate shades so neighbouring matches stay apart."""
    return choices["alternate"] if slot < 32 and (slot >> 1) & 1 else choices["normal"]


def nt_addr(col, row):
    return 0x2000 + row * 32 + col


def attr_slot(col, row):
    """(byte offset in the 64-byte table, bit shift) of the cell holding tile (col, row)."""
    return (row // 4) * 8 + col // 4, ((row & 2) << 1) | (col & 2)


def round_label(rounds, played):
    label = rounds[0][1]
    for start, text in rounds:
        if played >= start:
            label = text
    return label


def text_glyphs(text):
    return {ord(ch) for ch in text}



class Screen:
    def __init__(self, name, spec, backdrop):
        self.name, self.spec, self.backdrop = name, spec, backdrop
        self.palettes = [[nes_color(c) for c in p] for p in spec["palettes"]]
        self.sprite_palettes = [[nes_color(c) for c in p] for p in spec["sprite_palettes"]]
        self.nametable = [[BLANK] * 32 for _ in range(30)]
        self.reserved = {}            # (col,row) -> label: text or runtime cells, blank in the art
        self.forced = {}              # attribute cell -> static palette
        self.alternates = {}          # attribute cell -> palettes the runtime may switch to
        self.cell_palette = {}

    def force(self, cell, palette, alternates=()):
        if self.forced.setdefault(cell, palette) != palette:
            raise AssetError(f"{self.name} attribute cell {cell}: conflicting palettes")
        if alternates:
            self.alternates.setdefault(cell, set()).update(alternates)

    def reserve(self, col, row, width, label, palette, alternates=()):
        if not (0 <= col and col + width <= 32 and 0 <= row < 30):
            raise AssetError(f"{self.name} {label}: outside the screen")
        for x in range(col, col + width):
            if (x, row) in self.reserved:
                raise AssetError(f"{self.name} {label}: overlaps {self.reserved[(x, row)]}")
            self.reserved[(x, row)] = label
            self.force((x // 2, row // 2), palette, alternates)

    def palette_rgb(self):
        return bytes([self.backdrop] + self.palettes[0] + [self.backdrop] + self.palettes[1]
                     + [self.backdrop] + self.palettes[2] + [self.backdrop] + self.palettes[3]
                     + [self.backdrop] + self.sprite_palettes[0] + [self.backdrop] + self.sprite_palettes[1]
                     + [self.backdrop] + self.sprite_palettes[2] + [self.backdrop] + self.sprite_palettes[3])

    def convert(self, rows, bank):
        errors = []
        for ay in range(15):
            for ax in range(16):
                colors, tiles = set(), [(x, y) for y in (2 * ay, 2 * ay + 1) for x in (2 * ax, 2 * ax + 1)]
                for x, y in tiles:
                    pixels = tile_pixels(rows, x, y)
                    used = {c for row in pixels for c in row if c != self.backdrop}
                    if (x, y) in self.reserved:
                        if used:
                            errors.append(f"{self.name} tile ({x},{y}) is reserved for "
                                          f"{self.reserved[(x, y)]} but the art paints it")
                        continue
                    colors |= used
                if (ax, ay) in self.forced:
                    choice = self.forced[(ax, ay)]
                    if not colors <= set(self.palettes[choice]):
                        errors.append(f"{self.name} cell ({ax},{ay}): art colors "
                                      f"{sorted(f'${c:02X}' for c in colors)} not in forced P{choice}")
                else:
                    fits = [i for i, p in enumerate(self.palettes) if colors <= set(p)]
                    if not fits:
                        errors.append(f"{self.name} cell ({ax},{ay}): colors "
                                      f"{sorted(f'${c:02X}' for c in colors)} fit no palette")
                        continue
                    choice = fits[0]
                self.cell_palette[(ax, ay)] = choice
                for other in self.alternates.get((ax, ay), ()):
                    for color in colors:
                        if self.palettes[choice].index(color) != (self.palettes[other].index(color)
                                                                  if color in self.palettes[other] else -1):
                            errors.append(f"{self.name} cell ({ax},{ay}): ${color:02X} changes when the "
                                          f"runtime switches P{choice} to P{other}")
                    if self.palettes[choice][1] != self.palettes[other][1] and any(
                            self.nametable[y][x] != BLANK and (x, y) in self.reserved for x, y in tiles):
                        errors.append(f"{self.name} cell ({ax},{ay}): text color changes with P{other}")
        if errors:
            raise AssetError("\n".join(errors))
        for y in range(30):
            for x in range(32):
                if (x, y) in self.reserved:
                    continue
                values = to_values(tile_pixels(rows, x, y),
                                   self.palettes[self.cell_palette[(x // 2, y // 2)]],
                                   self.backdrop, f"{self.name} tile ({x},{y})")
                self.nametable[y][x] = bank.intern(encode(values), f"{self.name}:{x},{y}")

    def attributes(self, overrides=None):
        cells = dict(self.cell_palette)
        cells.update(overrides or {})
        table = bytearray(64)
        for (ax, ay), p in cells.items():
            offset, shift = attr_slot(2 * ax, 2 * ay)
            table[offset] |= p << shift
        return bytes(table)

    def nametable_bytes(self):
        return bytes(t for row in self.nametable for t in row)


def font_patterns(rom):
    base = CHR_START + FONT_BANK * 0x1000
    return {i: bytes(rom[base + 16 * i:base + 16 * i + 16]) for i in range(256)}


def team_records(teams_path=TEAMS):
    teams = json.loads(Path(teams_path).read_text())["teams"]
    if [t["id"] for t in teams] != list(range(32)):
        raise AssetError("teams32.json must list ids 0-31 in order")
    for t in teams:
        if len(t["name"]) > NAME_WIDTH or len(t["region"]) > REGION_WIDTH or not 2 <= len(t["code"]) <= 3:
            raise AssetError(f"team {t['id']}: name, region or code does not fit")
        if not re.fullmatch(r"[A-Z ]+", t["name"] + t["region"] + t["code"]):
            raise AssetError(f"team {t['id']}: only A-Z and space are drawable")
    return teams


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def sprite_path(name):
    return PNGS / "sprites" / f"{name}.png"


def scene_path(name):
    return PNGS / "scenes" / f"{name}.png"


def used_pngs():
    names = [f"chip_{i}" for i in range(32)] + ["chip_empty"] + [f"flag_{i}" for i in range(32)] + ["cursor_corner"]
    return [scene_path("selector"), scene_path("bracket")] + [sprite_path(n) for n in names]


def convert(rom, layout_path=LAYOUT, teams_path=TEAMS):
    layout = json.loads(Path(layout_path).read_text())
    if layout.get("format") != "menu32-layout/1":
        raise AssetError("unknown layout format")
    backdrop = nes_color(layout["backdrop"])
    teams = team_records(teams_path)
    sel = Screen("selector", layout["screens"]["selector"], backdrop)
    brk = Screen("bracket", layout["screens"]["bracket"], backdrop)
    rounds = layout["screens"]["bracket"]["rounds"]
    if [r[0] for r in rounds] != sorted(r[0] for r in rounds) or rounds[0][0] != 0:
        raise AssetError("round starts must ascend from 0")

    glyphs = {BLANK} | text_glyphs("MATCH 0123456789VS")
    for t in teams:
        glyphs |= text_glyphs(t["name"] + t["region"])
    for _, label in rounds:
        glyphs |= text_glyphs(label)
    for screen in (sel, brk):
        for entry in screen.spec["text"]:
            glyphs |= text_glyphs(entry["text"])
    bank = TileBank(font_patterns(rom), glyphs)

    allowed = {backdrop}
    for screen in (sel, brk):
        for p in screen.palettes + screen.sprite_palettes:
            allowed |= set(p)

    # Chips and flags first, so their ids do not move when scene art changes.
    chip_palette = brk.palettes[brk.spec["slot_palettes"]["normal"]]
    if any(brk.palettes[p][1:] != chip_palette[1:] for p in brk.spec["slot_palettes"].values()):
        raise AssetError("slot palettes may differ only in the plate color")
    chips = []
    for i in list(range(32)) + ["empty"]:
        _, _, rows = load_png(sprite_path(f"chip_{i}"), allowed, opaque=False, size=(16, 8))
        chips.append([bank.intern(encode(to_values(tile_pixels(rows, x, 0), chip_palette, backdrop,
                                                       f"chip_{i}")), f"chip:{i}:{x}") for x in (0, 1)])
    flag_choices = sel.spec["flag_palettes"]
    flags, flag_palettes = [], []
    for i in range(32):
        _, _, rows = load_png(sprite_path(f"flag_{i}"), allowed, opaque=True, size=(16, 8))
        used = {c for row in rows for c in row} - {backdrop}
        fits = [p for p in flag_choices if used <= set(sel.palettes[p])]
        if not fits:
            raise AssetError(f"flag_{i}: colors fit no flag palette")
        flag_palettes.append(fits[0])
        flags.append([bank.intern(encode(to_values(tile_pixels(rows, x, 0), sel.palettes[fits[0]],
                                                       backdrop, f"flag_{i}")), f"flag:{i}:{x}") for x in (0, 1)])
    _, _, rows = load_png(sprite_path("cursor_corner"), allowed, opaque=False, size=(8, 8))
    cursor = bank.intern(encode(to_values(tile_pixels(rows, 0, 0), sel.sprite_palettes[0], backdrop,
                                          "cursor_corner")), "sprite:cursor_corner")

    regions = {}
    for screen in (sel, brk):
        for entry in screen.spec["text"]:
            screen.reserve(entry["col"], entry["row"], len(entry["text"]), f"text {entry['text']!r}",
                           entry["palette"])
            for i, ch in enumerate(entry["text"]):
                screen.nametable[entry["row"]][entry["col"] + i] = ord(ch)
        for region in screen.spec["regions"]:
            if region["palette"] == "flag":
                palette, alternates = flag_choices[0], flag_choices
            else:
                palette, alternates = region["palette"], ()
            screen.reserve(region["col"], region["row"], region["width"], region["name"], palette, alternates)
            regions.setdefault(screen.name, {})[region["name"]] = {
                "nt": nt_addr(region["col"], region["row"]), "width": region["width"],
                "palette": region["palette"]}

    tree = layout["screens"]["bracket"]["tree"]
    cells = slot_cells(tree)
    highlight = brk.spec["slot_palettes"]["highlight"]
    for s, (col, row) in sorted(cells.items()):
        resting = slot_palette(brk.spec["slot_palettes"], s)
        brk.reserve(col, row, 2, f"slot {s}", resting, (resting, highlight))

    card = sel.spec["cards"]
    for t in range(32):
        col = card["col"] + card["col_pitch"] * (t & 7)
        row = card["flag_row"] + card["row_pitch"] * (t >> 3)
        for x in (col, col + 1):
            sel.force((x // 2, row // 2), flag_palettes[t])

    _, _, sel_rows = load_png(scene_path("selector"), allowed, opaque=True, size=(256, 240))
    _, _, brk_rows = load_png(scene_path("bracket"), allowed, opaque=True, size=(256, 240))
    sel.convert(sel_rows, bank)
    brk.convert(brk_rows, bank)

    # The grid in the selector art must be exactly the runtime flag and chip tiles.
    for t in range(32):
        col = card["col"] + card["col_pitch"] * (t & 7)
        row = card["flag_row"] + card["row_pitch"] * (t >> 3)
        if sel.nametable[row][col:col + 2] != flags[t] or sel.nametable[row + 1][col:col + 2] != chips[t]:
            raise AssetError(f"selector card {t} differs from flag_{t}/chip_{t}")
        for x in (col, col + 1):
            if sel.cell_palette[(x // 2, row // 2)] != flag_palettes[t]:
                raise AssetError(f"selector card {t}: flag cell uses the wrong palette")

    flag_region = sel.spec["regions"][0]
    if flag_region["name"] != "info_flag" or flag_region["col"] % 2 or flag_region["width"] != 2:
        raise AssetError("info_flag must be the first selector region and fill one attribute cell")
    offset, shift = attr_slot(flag_region["col"], flag_region["row"])
    static = sel.attributes()[offset] & ~(3 << shift)
    regions["selector"]["info_flag"]["attr"] = {
        "offset": offset, "values": [static | (p << shift) for p in flag_palettes]}

    static_attr = brk.attributes()
    highlights = []
    for m in range(32):
        slots = (62,) if m == 31 else (2 * m, 2 * m + 1)
        over = {}
        for s in slots:
            col, row = cells[s]
            for x in (col, col + 1):
                over[(x // 2, row // 2)] = highlight
        lit = brk.attributes(over)
        highlights.append([[i, lit[i]] for i in range(64) if lit[i] != static_attr[i]])

    patterns = bank.chr()
    if patterns[16 * BLANK:16 * BLANK + 16] != bytes(16):
        raise AssetError("blank tile was overwritten")
    tiles = []
    for index in sorted(bank.sources):
        entry = {"index": index, "source": bank.sources[index]}
        if index in bank.font:
            entry["font"] = index
        else:
            entry["pattern"] = bank.patterns[index].hex()
        tiles.append(entry)

    meta = {
        "format": FORMAT,
        "chr_bank": CHR_BANK,
        "font_bank": FONT_BANK,
        "font_glyphs": bank.font,
        "font_sha256": sha256(b"".join(bank.patterns[i] for i in bank.font)),
        "palette_table": PALETTE_TABLE,
        "pxl": json.loads(LOCK.read_text()) if LOCK.exists() else None,
        "sources": {relative(p): sha256(p.read_bytes())
                    for p in [SOURCE, Path(layout_path), Path(teams_path), Path(__file__)] + used_pngs()},
        "tiles_used": len(bank.sources),
        "tiles_free": len(bank.order),
    }
    return {
        "format": FORMAT,
        "meta": meta,
        "tiles": tiles,
        "teams": [{"id": t["id"], "code": t["code"], "name": t["name"].ljust(NAME_WIDTH),
                   "region": t["region"].rjust(REGION_WIDTH), "chip": chips[t["id"]],
                   "flag": flags[t["id"]], "flag_palette": flag_palettes[t["id"]]} for t in teams],
        "empty_chip": chips[32],
        "cursor_tile": cursor,
        "screens": {
            screen.name: {"nametable": screen.nametable_bytes().hex(), "attributes": screen.attributes().hex(),
                          "palette": screen.palette_rgb().hex(), "regions": regions.get(screen.name, {})}
            for screen in (sel, brk)},
        "selector": {"cards": [[card["col"] + card["col_pitch"] * (t & 7),
                                card["flag_row"] + card["row_pitch"] * (t >> 3)] for t in range(32)]},
        "bracket": {"slots": [nt_addr(*cells[s]) for s in range(63)], "highlights": highlights,
                    "rounds": rounds},
    }


def dumps(assets):
    return json.dumps(assets, indent=1, sort_keys=True) + "\n"



def chr_bytes(assets, rom):
    fonts = font_patterns(rom)
    data = bytearray(4096)
    for tile in assets["tiles"]:
        pattern = fonts[tile["font"]] if "font" in tile else bytes.fromhex(tile["pattern"])
        data[16 * tile["index"]:16 * tile["index"] + 16] = pattern
    return bytes(data)


def put(nt, addr, values):
    start = addr - 0x2000
    nt[start:start + len(values)] = bytes(values)


def text_bytes(text, width):
    return text.ljust(width)[:width].encode("ascii")


def selector_screen(assets, team):
    """Nametable and attributes after the selector shows `team`."""
    screen = assets["screens"]["selector"]
    nt = bytearray.fromhex(screen["nametable"])
    attrs = bytearray.fromhex(screen["attributes"])
    regions, record = screen["regions"], assets["teams"][team]
    put(nt, regions["info_flag"]["nt"], record["flag"])
    put(nt, regions["info_name"]["nt"], text_bytes(record["name"], NAME_WIDTH))
    put(nt, regions["info_region"]["nt"], text_bytes(record["region"], REGION_WIDTH))
    flag_attr = regions["info_flag"]["attr"]
    attrs[flag_attr["offset"]] = flag_attr["values"][team]
    return bytes(nt), bytes(attrs)


def cursor_sprites(assets, team, phase=0):
    """Four OAM entries (y, tile, attr, x) around card `team`; phase 1 pulls them in a pixel."""
    col, row = assets["selector"]["cards"][team]
    x0, y0 = col * 8, row * 8
    d = 3 - phase
    tile = assets["cursor_tile"]
    spots = ((x0 - d, y0 - d, 0x00), (x0 + 16 + d - 8, y0 - d, 0x40),
             (x0 - d, y0 + 15 + d - 8, 0x80), (x0 + 16 + d - 8, y0 + 15 + d - 8, 0xC0))
    return [((y - 1) & 0xFF, tile, attr, x & 0xFF) for x, y, attr in spots]


def team_ok(team):
    return 0 <= team < 32


def bracket_screen(assets, heap, played):
    """Nametable and attributes after the bracket draws `heap` (63 bytes) with $07FC=played."""
    screen, tree = assets["screens"]["bracket"], assets["bracket"]
    nt = bytearray.fromhex(screen["nametable"])
    attrs = bytearray.fromhex(screen["attributes"])
    m = min(played, 31)
    teams, empty = assets["teams"], assets["empty_chip"]
    for s in range(63):
        decided = s < 32 + m and team_ok(heap[s])
        put(nt, tree["slots"][s], teams[heap[s]]["chip"] if decided else empty)
    for offset, value in tree["highlights"][m]:
        attrs[offset] = value
    regions = screen["regions"]
    label = round_label(tree["rounds"], m)
    put(nt, regions["round"]["nt"], text_bytes(label, regions["round"]["width"]))
    if m < 31:
        pair = [heap[2 * m], heap[2 * m + 1]]
        put(nt, regions["match"]["nt"], text_bytes(f"MATCH {m + 1:02d}", 8))
        put(nt, regions["vs"]["nt"], b"VS")
    else:
        pair = [heap[62], None]
        put(nt, regions["match"]["nt"], text_bytes("", 8))
        put(nt, regions["vs"]["nt"], b"  ")
    for key, team in zip("ab", pair):
        if team is not None and team_ok(team):
            put(nt, regions[f"chip_{key}"]["nt"], teams[team]["chip"])
            put(nt, regions[f"name_{key}"]["nt"], text_bytes(teams[team]["name"], NAME_WIDTH))
        else:
            put(nt, regions[f"chip_{key}"]["nt"], [BLANK, BLANK] if team is None else empty)
            put(nt, regions[f"name_{key}"]["nt"], text_bytes("", NAME_WIDTH))
    return bytes(nt), bytes(attrs)


def render(chr_data, nametable, attributes, palette, oam=(), scale=1):
    """An RGB image of one 256x240 frame, the way the PPU composes it (8x8 sprites)."""
    image = Image.new("RGB", (256, 240))
    px = image.load()
    tiles = {}

    def values(index):
        if index not in tiles:
            tiles[index] = decode(chr_data[16 * index:16 * index + 16])
        return tiles[index]

    for ty in range(30):
        for tx in range(32):
            offset, shift = attr_slot(tx, ty)
            sub = (attributes[offset] >> shift) & 3
            grid = values(nametable[ty * 32 + tx])
            for y in range(8):
                for x in range(8):
                    v = grid[y][x]
                    px[tx * 8 + x, ty * 8 + y] = NES_RGB[palette[4 * sub + v] if v else palette[0]]
    for y, tile, attr, x in reversed(list(oam)):
        if y >= 0xEF:
            continue
        grid = values(tile)
        for yy in range(8):
            for xx in range(8):
                v = grid[7 - yy if attr & 0x80 else yy][7 - xx if attr & 0x40 else xx]
                sx, sy = x + xx, y + 1 + yy
                if v and sx < 256 and sy < 240:
                    px[sx, sy] = NES_RGB[palette[16 + 4 * (attr & 3) + v]]
    if scale != 1:
        image = image.resize((256 * scale, 240 * scale), Image.NEAREST)
    return image


def sample_heap(selected=31, played=31, seed=0x5A):
    """A new series seeded like bank 11 $8200, then `played` matches with stable pseudo-random winners."""
    heap = [selected] + [t for t in range(32) if t != selected] + [0xFF] * 31
    state = seed
    for m in range(played):
        state = (state * 109 + 89) & 0xFF
        heap[32 + m] = heap[2 * m + (state >> 7)]
    return heap


def write_previews(assets, rom, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = chr_bytes(assets, rom)
    sel_pal = bytes.fromhex(assets["screens"]["selector"]["palette"])
    brk_pal = bytes.fromhex(assets["screens"]["bracket"]["palette"])
    written = []
    for team in (0, 31):
        nt, attrs = selector_screen(assets, team)
        name = out / f"selector-{team:02d}.png"
        render(data, nt, attrs, sel_pal, cursor_sprites(assets, team)).save(name)
        written.append(name)
    for played in (0, 15, 16, 23, 24, 28, 30, 31):
        nt, attrs = bracket_screen(assets, sample_heap(played=played), played)
        name = out / f"bracket-{played:02d}.png"
        render(data, nt, attrs, brk_pal).save(name)
        written.append(name)
    return written



def node_version():
    out = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True).stdout
    return tuple(int(v) for v in re.findall(r"\d+", out)[:3])


def render_pxl(pxl, destination):
    """Render the art with a pinned pxl checkout and copy the PNGs the converter reads."""
    lock = json.loads(LOCK.read_text())
    if node_version() < tuple(lock["node_min"]):
        raise AssetError(f"pxl needs Node >= {'.'.join(map(str, lock['node_min']))}")
    head = subprocess.run(["git", "-C", str(pxl), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != lock["commit"]:
        raise AssetError(f"pxl checkout is at {head}, not the pinned {lock['commit']}")
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(["node", str(Path(pxl) / "bin/pxl.js"), "build", str(SOURCE), "--out", temporary,
                        "--no-preview"], check=True, capture_output=True, text=True)
        for path in used_pngs():
            relative = path.relative_to(PNGS)
            target = Path(destination) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(temporary) / relative, target)


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    protected = [source, *ART.rglob("*"),
                 *(path for path in (ROOT / "data").rglob("*") if path != ASSETS)]
    for path in protected:
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise AssetError(f"output aliases protected input {path}")
    if output.is_file() and sha256(output.read_bytes()) == sha256(source.read_bytes()):
        raise AssetError("output aliases protected input ROM artifact")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", type=Path, required=True, help="pinned visualtables32 ROM (font source)")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout; re-render the art first")
    ap.add_argument("-o", "--out", type=Path, default=ASSETS)
    ap.add_argument("--previews", type=Path, help="write NES-exact preview PNGs here")
    ap.add_argument("--check", action="store_true", help="fail unless --out already holds this output")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        rom = args.rom.read_bytes()
        if args.pxl:
            render_pxl(args.pxl, PNGS)
        assets = convert(rom)
        text = dumps(assets)
        if args.check:
            if not args.out.is_file() or args.out.read_text() != text:
                raise AssetError(f"{args.out} is stale; rerun without --check")
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text)
        if args.previews:
            for path in write_previews(assets, rom, args.previews):
                print(f"preview {path}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"menu32_convert: {exc}\n")
    meta = assets["meta"]
    print(f"{'checked' if args.check else 'wrote'} {args.out}: {meta['tiles_used']} tiles used, "
          f"{meta['tiles_free']} free, sha256 {sha256(text.encode())}")


if __name__ == "__main__":
    main()
