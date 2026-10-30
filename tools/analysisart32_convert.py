#!/usr/bin/env python3
"""Regenerate or check the Power Analysis card art: the approved stock parts cut from the ROM, the pinned
pxl render of art/analysisart32/card32.px.js, its conversion to split-screen NES bytes and, in memory,
the ROM tools/build_analysisart32.py builds from them.

    .venv/bin/python -B tools/analysisart32_convert.py --rom build/stockart32.nes --pxl build/vendor/claude-pxl [--out DIR]
    .venv/bin/python -B tools/analysisart32_convert.py --rom ... --pxl ... --check
    .venv/bin/python -B tools/analysisart32_convert.py --rom ... --pxl ... --record

--rom is the pinned stockart32 ROM: the stage input and the source of every stock byte. --pxl is the
checkout of the commit art/analysisart32/PXL.json pins; it is only read.

Everything is generated in scratch storage first: the parts art/analysisart32/placements.json uses, cut
by tools/stockart32_parts.py from art/stockart32/characters.json with its reviewed masks (each must equal
the digest data/stockart32/digests.json approved); two pinned pxl renders, byte for byte equal; the
conversion and its round trip; the socket and placement checks against the render; the ROM; every
visible part pixel and socket traced in that ROM's own bytes; the previews and provenance. Every output
and the ROM must then match data/analysisart32/digests.json. Only after the whole planned batch passes
the output guards is each file installed under --out (default build/analysisart32) through a sibling
temporary file. --check stops before installing and writes nothing. --record also rewrites
data/analysisart32/digests.json, the only tracked file this tool writes, after every check passed.

Rows 0-7 of the screen are CHR $18 (the shared name font): every cell must be an existing CHR $18 pattern
in the title palette and the name rows stay blank. Row 8, the split strip, may only use ids whose pattern
is identical in CHR $18 and CHR $06. Rows 9-29 are CHR $06: the stockart32 mode patterns are reused by
id, anything else takes a free id from $BA-$FF; letters use the mode font at ASCII ids or a CHR $00 glyph
copied into a free id.

Under --out:
  parts/<id>.png          the approved parts the scene stamps, exact NES colors, alpha 0 where clear
  render/scenes/card.png  the pinned pxl render the conversion reads
  analysisassets.json     analysisassets/1, which tools/build_analysisart32.py reads
  preview.png             the converted background decoded from asset bytes (no name, flag, digits or balls)
  teams.png               six finished cards reconstructed from the built ROM: its own card data, stock flag
                          and name writers, numerals() and balls() run on the CPU model, no frame loop
  provenance.json         per part cell its ROM source; per placement the screen tiles it reaches with the
                          ROM's tile id, pattern digest and palette; sockets, digits and title placements
"""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

import analysisart32_assets as model
from analysisart32_assets import AnalysisAssets, AssetError, Layout
import analysisart32_machine as machine
import build_analysisart32 as stage
from build_draw32 import read, refuse_aliases, sha256
from build_scoreart32 import refuse_inside, write_atomic
from build_title32 import protect_output as protect_earlier_output
import menu32_convert as menu
from scoreart32_convert import read_lock
import stockart32_convert as stock_convert
import stockart32_parts as parts
import stockart32_source as source

ROOT = stage.ROOT
ART = model.ART
SOURCES = ("PXL.json", "card32.px.js", "layout.json", "placements.json")
PART_MANIFEST = ROOT / model.PART_MANIFEST
APPROVED = ROOT / "data/stockart32/digests.json"
SCENE_SOURCE = "card32.px.js"
FIXED_OUTPUTS = (stage.ASSET_JSON, "preview.png", "teams.png", "provenance.json")
PREVIEW_TEAMS = (0, 2, 13, 18, 27, 31)     # wide and narrow fonts, with and without flags, low and mixed ratings


def png_bytes(image):
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return encoded.getvalue()


def read_sources(art=ART, part_manifest=PART_MANIFEST):
    found = {f"art/analysisart32/{name}": (Path(art) / name).read_bytes() for name in SOURCES}
    found[model.PART_MANIFEST] = Path(part_manifest).read_bytes()
    return found


def models(sources):
    """The layout, the part manifest and the placements, each validated before any pixel is touched."""
    layout = Layout.parse(json.loads(sources["art/analysisart32/layout.json"]),
                          sha256(sources["art/analysisart32/layout.json"]))
    manifest = parts.parse_manifest(json.loads(sources[model.PART_MANIFEST]), sha256(sources[model.PART_MANIFEST]))
    try:
        record = json.loads(sources["art/analysisart32/placements.json"])
    except json.JSONDecodeError as exc:
        raise AssetError(f"placements: not JSON ({exc})") from None
    placements = model.parse_placements(record, {p.id: p.size for p in manifest.parts})
    return layout, manifest, placements


def planned_outputs(layout, placements):
    """Every file one run writes, named before anything is rendered."""
    return sorted({*FIXED_OUTPUTS, f"render/scenes/{layout.scene}.png",
                   *(f"parts/{p.part}.png" for p in placements)})



def scene_rgb(png):
    """Rows of RGB triples of the 256x240 render; every pixel opaque and an NES color."""
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    if image.size != model.SCREEN_SIZE:
        raise AssetError(f"the render is {image.size[0]}x{image.size[1]}, expected 256x240")
    colors = set(menu.NES_RGB)
    px = image.load()
    rows = []
    for y in range(240):
        row = []
        for x in range(256):
            r, g, b, a = px[x, y]
            if a != 255:
                raise AssetError(f"render ({x},{y}) is not opaque")
            if (r, g, b) not in colors:
                raise AssetError(f"render ({x},{y}) #{r:02X}{g:02X}{b:02X} is not an NES color")
            row.append((r, g, b))
        rows.append(row)
    return rows


def convert(base, layout, png):
    """The render as AnalysisAssets: attributes, palettes, nametable and new CHR $06 tiles. The render's
    sockets must sit exactly at the layout's stats rows by socket columns."""
    pixels = scene_rgb(png)
    chr06 = bytearray(read(base, "chr", model.MODE_CHR * 0x1000, 0x1000))
    chr18 = read(base, "chr", model.TITLE_CHR * 0x1000, 0x1000)
    chr00 = read(base, "chr", model.FONT_CHR * 0x1000, 0x1000)
    if any(chr06[16 * model.FIRST_FREE:]):
        raise AssetError(f"CHR $06 ${model.FIRST_FREE:02X}-$FF is not blank in the input; the free ids are taken")
    rgb = menu.NES_RGB
    backdrop = rgb[layout.backdrop]
    palettes = [[rgb[c] for c in p] for p in layout.palettes]
    split = layout.split_row

    attributes, cell_palette = bytearray(64), {}
    for ay in range(15):
        for ax in range(16):
            colors = {pixels[y][x] for y in range(16 * ay, 16 * ay + 16) for x in range(16 * ax, 16 * ax + 16)}
            colors.discard(backdrop)
            top = 2 * ay
            if top + 1 < split:
                choices = [layout.title_palette]
            else:
                choices = [i for i, p in enumerate(palettes) if colors <= set(p)]
                hint = layout.attr_hints.get((top, 2 * ax))
                if hint is not None:
                    choices = [hint] if hint in choices else []
            if not choices or not colors <= set(palettes[choices[0]]):
                found = " ".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in sorted(colors))
                raise AssetError(f"16x16 cell rows {top}-{top + 1} cols {2 * ax}-{2 * ax + 1}: {found} fits no allowed "
                                 f"palette {choices}")
            p = choices[0]
            for dy in (0, 1):
                for dx in (0, 1):
                    cell_palette[(top + dy, 2 * ax + dx)] = p
                    offset, shift = menu.attr_slot(2 * ax + dx, top + dy)
                    attributes[offset] |= p << shift

    def values(tx, ty):
        lookup = {backdrop: 0}
        for i, c in enumerate(palettes[cell_palette[(ty, tx)]]):
            lookup.setdefault(c, i + 1)
        return [[lookup[pixels[8 * ty + y][8 * tx + x]] for x in range(8)] for y in range(8)]

    free = [i for i in range(model.FIRST_FREE, 0x100) if i not in layout.reserve]
    new_tiles = {}
    for tile, pattern in layout.reserve.items():
        new_tiles[tile] = pattern
        chr06[16 * tile:16 * tile + 16] = pattern
    existing06 = {}
    for i in range(model.FIRST_FREE):
        existing06.setdefault(bytes(chr06[16 * i:16 * i + 16]), i)
    existing18 = {}
    for i in range(0x100):
        existing18.setdefault(chr18[16 * i:16 * i + 16], i)
    existing18[bytes(16)] = model.BLANK

    def allocate(pattern, where):
        if pattern in existing06:
            return existing06[pattern]
        if not free:
            raise AssetError(f"CHR $06 is full at {where}: all {0x100 - model.FIRST_FREE} free ids are used")
        tile = free.pop(0)
        new_tiles[tile] = pattern
        chr06[16 * tile:16 * tile + 16] = pattern
        existing06[pattern] = tile
        return tile

    if {v for row in menu.decode(bytes(chr06[16 * 0x41:16 * 0x41 + 16])) for v in row} != {0, 2}:
        raise AssetError("CHR $06 'A' is not a value-2 glyph; the mode font assumption fails")
    glyphs = {}
    for ch in layout.glyphs:
        pattern = chr00[16 * ord(ch):16 * ord(ch) + 16]
        if not any(pattern):
            raise AssetError(f"glyph {ch!r}: CHR $00 ${ord(ch):02X} is blank, not a glyph")
        before = len(new_tiles)
        glyphs[ch] = allocate(model.ink2(pattern), f"glyph {ch!r}")
        if len(new_tiles) == before:
            raise AssetError(f"glyph {ch!r} is already CHR $06 ${glyphs[ch]:02X}; drop it from the layout glyphs")

    def glyph(ch):
        tile = model.glyph_id(ch, glyphs)
        if ch == " " or ch in glyphs:
            return tile
        stock = bytes(chr06[16 * tile:16 * tile + 16])
        source_glyph = chr00[16 * tile:16 * tile + 16]
        if not any(stock) or not any(source_glyph) or stock != model.ink2(source_glyph):
            raise AssetError(f"CHR $06 has no stock glyph for {ch!r}; add it to the layout glyphs")
        return tile

    lettered = {cell: glyph(ch) for cell, ch in (layout.label_cells() | layout.static_cells()).items()}
    digits = set(layout.digit_cells())
    nametable = bytearray(model.ROWS * model.COLUMNS)
    report = {"title": 0, "reused": 0, "new": 0, "lettered": len(lettered), "digits": len(digits)}
    for ty in range(model.ROWS):
        for tx in range(model.COLUMNS):
            v = values(tx, ty)
            pattern = menu.encode(v)
            where = f"cell row {ty} col {tx}"
            cell = 32 * ty + tx
            if (ty, tx) in lettered or (ty, tx) in digits:
                if any(any(r) for r in v):
                    raise AssetError(f"{where}: a lettered or digit cell must be blank in the art")
                nametable[cell] = lettered.get((ty, tx), model.BLANK)
                continue
            if ty < split:
                if ty in layout.name_rows and any(any(r) for r in v):
                    raise AssetError(f"{where}: name rows must be blank; the stock writer prints there")
                if pattern not in existing18:
                    raise AssetError(f"{where}: the pattern is not in CHR $18; the title band cannot add tiles")
                nametable[cell] = existing18[pattern]
                report["title"] += 1
                continue
            if ty == split:
                tile = model.BLANK if not any(pattern) else next(
                    (i for i in layout.split_ids if bytes(chr06[16 * i:16 * i + 16]) == pattern), None)
                if tile is None or chr18[16 * tile:16 * tile + 16] != pattern:
                    raise AssetError(f"{where}: the split row needs a pattern identical in CHR $18 and CHR $06")
                nametable[cell] = tile
                continue
            if not any(pattern):
                nametable[cell] = model.BLANK
                continue
            before = len(new_tiles)
            nametable[cell] = allocate(pattern, where)
            report["new" if len(new_tiles) > before else "reused"] += 1
    for row in layout.rail_rows:
        rail = set(nametable[32 * row:32 * row + 32])
        if len(rail) != 1 or rail == {model.BLANK}:
            raise AssetError(f"rail row {row} must be one non-blank CHR $18 pattern across the screen")
    for tile in layout.split_ids:
        if bytes(chr06[16 * tile:16 * tile + 16]) != chr18[16 * tile:16 * tile + 16]:
            raise AssetError(f"split id ${tile:02X} differs between CHR $06 and CHR $18")
    socket_tile = check_sockets(base, layout, pixels, nametable)
    palette = b"".join(bytes((layout.backdrop, *p)) for p in layout.palettes)
    assets = AnalysisAssets(
        scene=layout.scene, layout_sha256=layout.sha256, png_sha256=sha256(png), split_row=split,
        title_palette=layout.title_palette, name_rows=layout.name_rows, rail_rows=layout.rail_rows,
        split_ids=layout.split_ids, nametable=bytes(nametable), attributes=bytes(attributes), palette=palette,
        new_tiles={t: new_tiles[t] for t in sorted(new_tiles)}, glyphs=glyphs,
        digits=tuple(glyph(str(v)) for v in model.SCALE), stats=layout.stats, text=layout.text,
        socket_cols=layout.socket_cols, socket_tile=socket_tile, ball_tile=layout.ball_tile,
        ball_palette=layout.ball_palette, ball_colors=layout.ball_colors, flag_y=layout.flag_y,
        pace_nmis=layout.pace_nmis)
    check_roundtrip(base, assets, pixels, lettered, digits)
    return assets, pixels, report


def check_sockets(base, layout, pixels, nametable):
    """Every stats row by socket column cell of the render is an empty socket: the ball sprite's outline in
    the socket color on the backdrop. All of them convert to one tile, which the assets then allow nowhere
    else."""
    outline = model.ball_outline(base, layout.ball_tile)
    ink, ground = menu.NES_RGB[layout.socket_color], menu.NES_RGB[layout.backdrop]
    tiles = set()
    for row, col in layout.socket_cells():
        for y in range(8):
            for x in range(8):
                if pixels[8 * row + y][8 * col + x] != (ink if (x, y) in outline else ground):
                    raise AssetError(f"the render has no empty ball socket at stats row {row}, socket column {col} "
                                     f"(pixel {8 * col + x},{8 * row + y}); card32.px.js and layout.json disagree")
        tiles.add(nametable[32 * row + col])
    if len(tiles) != 1:
        raise AssetError("the sockets convert to different tiles")
    return tiles.pop()


def screen_chr(base, assets):
    """CHR $18 as is and CHR $06 with the new tiles."""
    chr06 = bytearray(read(base, "chr", model.MODE_CHR * 0x1000, 0x1000))
    for tile, pattern in assets.new_tiles.items():
        chr06[16 * tile:16 * tile + 16] = pattern
    return read(base, "chr", model.TITLE_CHR * 0x1000, 0x1000), bytes(chr06)


def decode_background(base, assets):
    """RGB rows of the converted background as the PPU shows it: CHR $18 above the split, CHR $06 below."""
    chr18, chr06 = screen_chr(base, assets)
    rows = []
    for y in range(240):
        bank = chr18 if y // 8 < assets.split_row else chr06
        row = []
        for x in range(256):
            tile = assets.nametable[32 * (y // 8) + x // 8]
            v = menu.decode(bank[16 * tile:16 * tile + 16])[y % 8][x % 8]
            p = model.attr_palette(assets.attributes, x // 8, y // 8)
            row.append(menu.NES_RGB[assets.palette[4 * p + v] if v else assets.palette[0]])
        rows.append(row)
    return rows


def check_roundtrip(base, assets, pixels, lettered, digits):
    """The asset bytes decode to the render everywhere but the lettered and digit cells, which show their
    CHR $00 glyph shape and the blank."""
    decoded = decode_background(base, assets)
    chr00 = read(base, "chr", 0, 0x1000)
    bad = 0
    for y in range(240):
        for x in range(256):
            cell = (y // 8, x // 8)
            if cell not in lettered and cell not in digits and decoded[y][x] != pixels[y][x]:
                bad += 1
    if bad:
        raise AssetError(f"the asset bytes decode differently from the render in {bad} pixels")
    _, chr06 = screen_chr(base, assets)
    for (row, col), tile in lettered.items():
        if tile == model.BLANK:
            continue
        ch = next(c for c, t in assets.glyphs.items() if t == tile) if tile in assets.glyphs.values() else chr(tile)
        shape = menu.decode(chr00[16 * ord(ch):16 * ord(ch) + 16])
        got = menu.decode(chr06[16 * tile:16 * tile + 16])
        if [[bool(v) for v in r] for r in shape] != [[bool(v) for v in r] for r in got]:
            raise AssetError(f"cell row {row} col {col} does not show the CHR $00 glyph {ch!r}")



def visible_rect(placement, part):
    ax, ay, aw, ah = placement.area or (0, 0, part.width, part.height)
    x0, y0 = placement.at
    shown = stock_convert.intersect(placement.visible or (x0, y0, aw, ah),
                                    stock_convert.intersect((x0, y0, aw, ah), (0, 0, 256, 240)))
    return shown, (x0 - ax, y0 - ay)


def check_placement(placement, part, screen, label):
    """Every visible part pixel shows its color on `screen` (RGB rows); the count of pixels checked."""
    shown, (dx, dy) = visible_rect(placement, part)
    where = f"placement of {placement.part} at {list(placement.at)}"
    if shown is None:
        raise AssetError(f"{where} shows nothing")
    painted, wrong = 0, []
    for sy in range(shown[1], shown[1] + shown[3]):
        for sx in range(shown[0], shown[0] + shown[2]):
            c = part.pixels[sy - dy][sx - dx]
            if c is not None:
                painted += 1
                if screen[sy][sx] != menu.NES_RGB[c]:
                    wrong.append((sx, sy))
    if wrong:
        raise AssetError(f"{where}: {len(wrong)} of {painted} visible part pixels differ in {label}, first at "
                         f"{wrong[0]}")
    if not painted:
        raise AssetError(f"{where} shows no part pixel")
    return painted


def placement_record(placement, part, rom, assets):
    """The screen tiles a placement reaches, with the built ROM's tile id, pattern digest and palette."""
    shown, (dx, dy) = visible_rect(placement, part)
    chr06 = read(rom, "chr", model.MODE_CHR * 0x1000, 0x1000)
    screen = read(rom, stage.FAR, stage.SCREEN, 0x400)
    tiles = []
    for ty in range(shown[1] // 8, (shown[1] + shown[3] - 1) // 8 + 1):
        for tx in range(shown[0] // 8, (shown[0] + shown[2] - 1) // 8 + 1):
            rect = stock_convert.intersect((8 * tx, 8 * ty, 8, 8), shown)
            count = sum(part.pixels[y - dy][x - dx] is not None for y in range(rect[1], rect[1] + rect[3])
                        for x in range(rect[0], rect[0] + rect[2]))
            if not count:
                continue
            tile = screen[32 * ty + tx]
            tiles.append({"tile": [tx, ty], "chr_tile": tile, "pattern_sha256": sha256(chr06[16 * tile:16 * tile + 16]),
                          "palette": model.attr_palette(screen[960:], tx, ty),
                          "part_rect": [rect[0] - dx, rect[1] - dy, rect[2], rect[3]], "pixels": count})
    return {"part": placement.part, "at": list(placement.at), "area": list(placement.area) if placement.area else None,
            "shown": list(shown), "tiles": tiles}



def rom_background(rom):
    """RGB rows of the built ROM's card screen, decoded from its own bank-13 and CHR bytes."""
    screen = read(rom, stage.FAR, stage.SCREEN, 0x400)
    palette = read(rom, stage.FAR, stage.FAR_DATA, 16)
    banks = {b: read(rom, "chr", b * 0x1000, 0x1000) for b in (model.TITLE_CHR, model.MODE_CHR)}
    rows = []
    for y in range(240):
        bank = banks[model.TITLE_CHR if y // 8 < model.SPLIT_ROW else model.MODE_CHR]
        row = []
        for x in range(256):
            tile = screen[32 * (y // 8) + x // 8]
            v = menu.decode(bank[16 * tile:16 * tile + 16])[y % 8][x % 8]
            p = model.attr_palette(screen[960:], x // 8, y // 8)
            row.append(menu.NES_RGB[palette[4 * p + v] if v else palette[0]])
        rows.append(row)
    return rows


def rows_image(rows):
    image = Image.new("RGB", (len(rows[0]), len(rows)))
    image.putdata([p for row in rows for p in row])
    return image


def teams_sheet(rom, assets):
    sheet = Image.new("RGB", (3 * 256, 2 * 240))
    for i, team in enumerate(PREVIEW_TEAMS):
        sheet.paste(machine.compose(rom, *machine.card_frame(rom, team, assets)), (256 * (i % 3), 240 * (i // 3)))
    return sheet


def provenance(base, sources, manifest, cut, placements, assets, rom, painted):
    titles = model.title_placements(base)
    _, _, tables = stage.home_code(assets)
    return {
        "format": "analysisart32-provenance/1",
        "base_sha256": sha256(base),
        "rom_sha256": sha256(rom),
        "sources": {name: sha256(data) for name, data in sorted(sources.items())},
        "part_pins": [{"label": label, "bank": bank, "address": f"${address:04X}", "size": size, "sha256": digest}
                      for label, bank, address, size, digest in source.PINS],
        "parts": [{"id": pid, "size": [cut[pid].width, cut[pid].height], "png_sha256": sha256(parts.png(cut[pid])),
                   "mask_sha256": parts.mask_sha256(cut[pid].pixels), "source": cut[pid].source,
                   "cells": [{"cell": [col, row], **record}
                             for (col, row), record in sorted(cut[pid].cells.items(), key=lambda c: (c[0][1], c[0][0]))]}
                  for pid in sorted({p.part for p in placements})],
        "placements": [{**placement_record(p, cut[p.part], rom, assets), "pixels": n}
                       for p, n in zip(placements, painted)],
        "sockets": {"rows": [s.row for s in assets.stats], "cols": list(assets.socket_cols),
                    "tile": f"{assets.socket_tile:02X}", "ball_tile": f"{assets.ball_tile:02X}",
                    "ball_y": list(read(rom, stage.HOME, tables["pip_y"], 4)),
                    "ball_x": list(read(rom, stage.HOME, tables["pip_x"], 4))},
        "digits": [{"stat": s.stat, "address": f"${0x2000 + 32 * s.row + s.digit_col:04X}"} for s in assets.stats],
        "titles": [{"team": t.team, "text": t.text, "font": t.font, "col": t.col, "flag": t.flag, "flag_x": t.flag_x}
                   for t in titles],
        "previews": {"preview.png": "the converted background decoded from asset bytes",
                     "teams.png": f"teams {', '.join(map(str, PREVIEW_TEAMS))} reconstructed on the CPU model from the "
                                  "built ROM's own routines and tables; not an emulator capture"},
    }


def approved_parts():
    registry = json.loads(APPROVED.read_text())
    if registry.get("format") != "stockart32-digests/1" or not isinstance(registry.get("outputs"), dict):
        raise AssetError(f"{APPROVED} is not the stockart32 registry")
    return registry["outputs"]


def render_scene(pxl, sources, pngs):
    """Two pinned pxl renders of card32.px.js staged with the parts, in scratch: {relative path: bytes}."""
    with tempfile.TemporaryDirectory(prefix="analysisart32-") as temporary:
        directory = Path(temporary) / "card"
        (directory / "parts").mkdir(parents=True)
        for name in SOURCES:
            (directory / name).write_bytes(sources[f"art/analysisart32/{name}"])
        for pid, data in pngs.items():
            (directory / "parts" / f"{pid}.png").write_bytes(data)
        stock_convert.check_renderer(pxl, read_lock(directory))
        return stock_convert.render(pxl, directory, SCENE_SOURCE)


def regenerate(base, pxl, sources):
    """Every output under --out as {relative path: bytes}, the assets and the ROM, all built in scratch."""
    if sha256(base) != stage.BASE_SHA256:
        raise AssetError("--rom must be the pinned stockart32 input")
    source.check_pins(base)
    layout, manifest, placements = models(sources)
    cut = parts.cut_parts(base, manifest)
    used = sorted({p.part for p in placements})
    pngs = {pid: parts.png(cut[pid]) for pid in used}
    approved = approved_parts()
    for pid, data in pngs.items():
        if sha256(data) != approved.get(f"parts/{pid}.png"):
            raise AssetError(f"part {pid} differs from the approved stockart32 part in data/stockart32/digests.json")
    renders = render_scene(pxl, sources, pngs)
    scene = f"scenes/{layout.scene}.png"
    if set(renders) != {scene}:
        raise AssetError(f"pxl rendered {sorted(renders)}; expected only {scene}")
    assets, pixels, report = convert(base, layout, renders[scene])
    painted = [check_placement(p, cut[p.part], pixels, "the render") for p in placements]
    rom = stage.build_rom(base, assets)
    screen = rom_background(rom)
    for p in placements:
        check_placement(p, cut[p.part], screen, "the built ROM's screen bytes")
    outputs = {f"parts/{pid}.png": data for pid, data in pngs.items()}
    outputs[f"render/{scene}"] = renders[scene]
    outputs |= {stage.ASSET_JSON: assets.dumps().encode(),
                "preview.png": png_bytes(rows_image(decode_background(base, assets))),
                "teams.png": png_bytes(teams_sheet(rom, assets)),
                "provenance.json": (json.dumps(provenance(base, sources, manifest, cut, placements, assets, rom,
                                                          painted), indent=1) + "\n").encode()}
    planned = planned_outputs(layout, placements)
    if sorted(outputs) != planned:
        raise AssetError(f"the run produced {sorted(outputs)}, not the planned {planned}")
    return outputs, assets, rom, report


def registry(sources, base, outputs, rom):
    return {"format": stage.REGISTRY_FORMAT,
            "sources": {name: sha256(data) for name, data in sorted(sources.items())},
            "roms": {"base": sha256(base)},
            "pins": {label: digest for label, *_, digest in (*source.PINS, *stage.DIGESTS)},
            "outputs": {path: sha256(data) for path, data in sorted(outputs.items())},
            "rom": sha256(rom)}


def differences(recorded, current):
    found = []
    for key in sorted(set(recorded) | set(current)):
        a, b = recorded.get(key), current.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            found += [f"{key} {name}" for name in sorted(set(a) | set(b)) if a.get(name) != b.get(name)]
        elif a != b:
            found.append(key)
    return found



def walk_down(top, target):
    """`top` and every directory between it and `target`, top first."""
    places = [Path(top)]
    for part in Path(target).relative_to(top).parts[:-1]:
        places.append(places[-1] / part)
    return places


def protect_outputs(rom, out, planned, inputs, pxl):
    """Refuse the whole batch before any file is written: protected inputs, tracked files and earlier evidence
    (also through links and before they exist), the pxl checkout, links or non-directories on the way to any
    planned file, links, hard links or non-regular files at one, two planned names on one file or folding to
    one name, and files in --out this run does not write."""
    out = stage.output_path(out)
    if out.is_symlink() or (out.exists() and not out.is_dir()):
        raise ValueError(f"output aliases protected location: {out} is a link or not a directory")
    folded = {}
    for relative in planned:
        key = relative.casefold()
        if key in folded:
            raise ValueError(f"output aliases protected output: {folded[key]} and {relative} fold to one name")
        folded[key] = relative
    targets = [out / relative for relative in planned]
    for target in targets:
        stage.protect_output(rom, target, inputs)
        refuse_inside(target, pxl)
        for place in walk_down(out, target):
            if place.is_symlink():
                raise ValueError(f"output aliases protected location through the linked directory {place}")
            if place.exists() and not place.is_dir():
                raise ValueError(f"output aliases protected location: {place} is not a directory")
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError(f"output aliases protected file: {target} is a link or not a regular file")
    resolved = [os.path.normcase(str(t.resolve())).casefold() for t in targets]
    if len(set(resolved)) != len(resolved):
        raise ValueError("output aliases protected output: two outputs resolve to one file")
    if out.exists():
        wanted = {str(Path(t).relative_to(out)) for t in targets}
        wanted |= {str(p.relative_to(out)) for t in targets for p in walk_down(out, t)[1:]}
        for found in sorted(out.rglob("*")):
            relative = str(found.relative_to(out))
            if found.is_symlink():
                raise ValueError(f"output aliases protected location through the link {found}")
            if relative not in wanted:
                if relative.casefold() in {w.casefold() for w in wanted}:
                    raise ValueError(f"output aliases protected output: {relative} folds onto a planned name")
                raise ValueError(f"{out} holds files this run does not write: {relative}")


def protect_registry(rom, inputs):
    path = stage.REGISTRY
    protect_earlier_output(rom, path)
    for place in (path.parent, path):
        if place.is_symlink():
            raise ValueError(f"output aliases protected file through the link {place}")
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError(f"output aliases protected file: {path} is linked or not a regular file")
    refuse_aliases(path, [p for p in stage.protected_paths(rom, inputs) if Path(p).absolute() != path.absolute()],
                   stage.PROTECTED_SHA256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", type=Path, required=True, help="pinned stockart32 ROM: stage input and stock sources")
    ap.add_argument("--pxl", type=Path, required=True, help="pinned claude-pxl checkout (read only)")
    ap.add_argument("-o", "--out", type=Path, default=stage.ASSETS, help="output directory (default %(default)s)")
    ap.add_argument("--check", action="store_true", help="write nothing; fail unless every digest is current")
    ap.add_argument("--record", action="store_true", help="accept new digests: install and rewrite the registry")
    args = ap.parse_args()
    if args.check and args.record:
        ap.error("--check writes nothing; drop --record")
    try:
        out = stage.output_path(args.out)
        pxl = args.pxl.resolve()
        sources = read_sources()
        layout, _, placements = models(sources)
        planned = planned_outputs(layout, placements)
        inputs = [stage.OUTPUT, stage.REGISTRY, *(ART / name for name in SOURCES), PART_MANIFEST, APPROVED]
        if not args.check:
            protect_outputs(args.rom, out, planned, inputs, pxl)
            if args.record:
                protect_registry(args.rom, inputs)
        base = args.rom.read_bytes()
        outputs, assets, rom, report = regenerate(base, pxl, sources)
        current = registry(sources, base, outputs, rom)
        if not args.record:
            if not stage.REGISTRY.is_file():
                raise AssetError(f"{stage.REGISTRY} is missing; rerun with --record to create it")
            changed = differences(stage.read_registry(), current)
            if changed:
                raise AssetError(f"the regenerated art differs from data/analysisart32/digests.json in "
                                 f"{', '.join(changed[:6])}{' and more' if len(changed) > 6 else ''}; "
                                 "rerun with --record to accept it")
        if not args.check:
            protect_outputs(args.rom, out, planned, inputs, pxl)
            for relative, data in sorted(outputs.items()):
                target = out / relative
                if not target.is_file() or target.read_bytes() != data:
                    write_atomic(target, data)
            if args.record:
                protect_registry(args.rom, inputs)
                write_atomic(stage.REGISTRY, (json.dumps(current, indent=1) + "\n").encode())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"analysisart32_convert: {exc}\n")
    changed = sum(a != b for a, b in zip(base, rom))
    if args.check:
        print(f"checked: all {len(outputs)} outputs and the ROM match data/analysisart32/digests.json; nothing written")
    else:
        print(f"wrote {out}: {len(outputs)} outputs {'recorded in' if args.record else 'matching'} "
              "data/analysisart32/digests.json")
    print(f"  CHR $06: {len(assets.new_tiles)} new tiles ({' '.join(f'${t:02X}' for t in assets.new_tiles)}), "
          f"{assets.free_after} free; {report['reused']} lower cells reuse stockart32 mode patterns, "
          f"{report['title']} title cells use CHR $18")
    print(f"  analysisart32 ROM {sha256(rom)} from stockart32 {sha256(base)}: {changed} bytes changed")


if __name__ == "__main__":
    main()
