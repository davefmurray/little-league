#!/usr/bin/env python3
"""Check the stockart32 stage: the manifest and its source pins, every part against an independent decode
of its stock source, regeneration and its output guards, the pure stage boundary, the built ROM's own
pixels, and the mode menu and scoreboard at runtime.

    .venv/bin/python -B tools/test_stockart32.py --pxl build/vendor/claude-pxl
    .venv/bin/python -B tools/test_stockart32.py --pxl build/vendor/claude-pxl --candidate build/stockart32.nes
    .venv/bin/python -B tools/test_stockart32.py --pxl PXL --quick
    .venv/bin/python -B tools/test_stockart32.py --pxl PXL --references build/stock-characters-design/references.json

The inputs are build/scoreart32.nes, build/modeart32.nes and build/title32.nes (--build names another
directory). The runtime checks are the accepted suites' own functions, imported unchanged: the mode menu
runs test_modeart32's checks against stock title32 and the scoreboard test_scoreart32's against
modeart32, with the stockart32 ROM, assets, layout and scene as the candidate. Their pinned modeart32 and
scoreart32 hashes are untouched, so those suites still pass on the accepted stages. A further pass
compares the candidate's exits, sound and timelines with the accepted scoreart32 ROM itself. Command
lines run from a temporary copy of tools, art and data, so hostile aliases point at scratch copies.
--references also matches the ROM decodes against the screenshots the manifest names; regeneration
never needs them. The CPU model counts cycles but approximates the PPU: emulator pictures, input,
audio and the tournament gates belong to the root. --quick shortens the runtime suites.
"""
import argparse
from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from PIL import Image

import build_stockart32 as stage
from build_draw32 import locate, read
from frontend32_test_machine import check_output_guards, rejects
import menu32_convert as menu
from menu32_convert import AssetError
import modeart32_convert as mode_convert
from modeart32_assets import ModeAssets
import scoreart32_convert as score_convert
from scoreart32_assets import GLYPHS, ScoreAssets
import stockart32_convert as convert
import stockart32_parts as parts
import stockart32_source as source
import test_modeart32 as mode_suite
import test_scoreart32 as score_suite

ROOT = stage.ROOT
TOOLS = ROOT / "tools"
INPUTS = {"scoreart32.nes": stage.BASE_SHA256, "modeart32.nes": score_convert.BASE_SHA256,
          "title32.nes": "8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c"}
FROZEN_ROM = "a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55"   # the root-corrected prototype
REGION_CHANGES = {"mode-screen": 628, "mode-palette": 2, "mode-chr": 2383, "score-palette": 1, "score-screen": 306,
                  "score-chr": 1314}
TILES = {"score": 237, "mode": 186}
# Glove, cheer and both crowds are byte-identical to the cross-judged candidate; batter and pair carry the
# root's reviewed source-zero corrections.
PART_PNGS = {"glove": "70257809a4767e66dccb1a499bfc60b15a9b13ca1dcdb541644ddfda204caf70",
             "cheer": "0e8f42700fc1e292f3897cf0e76e606e4a87c0f2267f3c88121f35ca750a3d8d",
             "crowd-red": "1d7237916cc8a009e5268eddf2d9827d51a0ce584c65583c13cfe854c670a327",
             "crowd-mix": "32fbbf2f08e6748341df93fc76cfb339ff0d4535a7e70f2de7216ab5b1fddfa2",
             "batter": "f991ee13d87332bb8963f643a30367ba375d7890901625b8a315b364be8561a4",
             "pair": "a8c73eb5b6ed4a09f506a5a4eccba9c3a62b6744936a3d5349dc917b4587ec2f"}
PLACED = {"batter": 803, "glove": 987, "cheer": 852, "pair": 1323}
SKY = 0x2C
CHR_START = 16 + 16 * 0x4000
SHOT_RGB = tuple(tuple(v << 2 for v in rgb) for rgb in menu.FCEUX_6BIT)   # the reference captures' emulator


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def refused(call, reason, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except ValueError as exc:
        assert reason in str(exc), f"refused for another reason: {exc}"
        return str(exc).splitlines()[0]
    raise AssertionError(f"accepted; expected a refusal mentioning {reason!r}")



def prg_byte(rom, bank, address):
    return rom[16 + bank * 0x4000 + address - (0xC000 if bank == 15 else 0x8000)]


def planar(rom, chr_bank, tile):
    start = CHR_START + chr_bank * 0x1000 + 16 * tile
    lo, hi = rom[start:start + 8], rom[start + 8:start + 16]
    return [[(lo[y] >> (7 - x) & 1) | (hi[y] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def stock_panel(rom, k):
    """(value, color) rows of intro picture k, read straight from file offsets: transparent shows $0F."""
    b = lambda address: prg_byte(rom, 5, address)  # noqa: E731
    tiles, selectors = b(0xB1F6 + 2 * k) | b(0xB1F7 + 2 * k) << 8, b(0xB204 + 2 * k) | b(0xB205 + 2 * k) << 8
    rows = [[None] * 64 for _ in range(64)]
    for i in range(64):
        palette = b(selectors + i // 4) >> 2 * (i % 4) & 3
        colors = [0x0F] + [prg_byte(rom, 15, 0xFA60 + 4 * palette + c) for c in (1, 2, 3)]
        for y, line in enumerate(planar(rom, 0x14, b(tiles + i))):
            for x, v in enumerate(line):
                rows[8 * (i // 8) + y][8 * (i % 8) + x] = (v, colors[v])
    return rows


def stock_block(rom, crowd):
    """(value, color) rows of a stands block in palette record $15, from file offsets."""
    rows = [[None] * crowd.size[0] for _ in range(crowd.size[1])]
    for j, line in enumerate(crowd.rows):
        for i, (key, _) in enumerate(line):
            tiles, palette = crowd.metatiles[key]
            colors = [prg_byte(rom, 15, 0xF930)] + [prg_byte(rom, 15, 0xF930 + 4 * palette + c) for c in (1, 2, 3)]
            for q, tile in enumerate(tiles):
                for y, values in enumerate(planar(rom, 0x10, tile)):
                    for x, v in enumerate(values):
                        rows[16 * j + 8 * (q >> 1) + y][16 * i + 8 * (q & 1) + x] = (v, colors[v])
    return rows


def screen_colors(rom, screen):
    """NES color rows of a stockart32 screen from the ROM's own bytes, decoded without menu32_convert."""
    bank, screen_at, palette_at, chr_at = convert.SCREEN_BYTES[screen]
    data = rom[locate(bank, screen_at):locate(bank, screen_at) + 0x400]
    palette = rom[locate(bank, palette_at):locate(bank, palette_at) + 32]
    tiles = [planar(rom, chr_at // 0x1000, t) for t in range(256)]
    rows = []
    for y in range(240):
        line = []
        for x in range(256):
            v = tiles[data[32 * (y // 8) + x // 8]][y % 8][x % 8]
            p = data[960 + 8 * (y // 32) + x // 32] >> (4 * (y // 16 % 2) + 2 * (x // 16 % 2)) & 3
            line.append(palette[4 * p + v] if v else palette[0])
        rows.append(line)
    return rows


def silhouette_digest(pixels):
    """The reviewed mask digest, recomputed from pixels: per 8x8 cell, row bytes, bit 7 the left pixel."""
    data = bytearray()
    for y in range(0, len(pixels), 8):
        for x in range(0, len(pixels[0]), 8):
            for j in range(8):
                data.append(sum((pixels[y + j][x + i] is not None) << (7 - i) for i in range(8)))
    return sha256(bytes(data))


SCREEN_COLORS = {c for _, palettes in convert.screen_palettes(convert.ART).values() for p in palettes for c in p} | {0x0C}


def png_colors(data):
    """NES color rows of a part PNG, None where clear; parts use only the two screens' colors."""
    by_rgb = {menu.NES_RGB[c]: c for c in SCREEN_COLORS}
    assert len(by_rgb) == len(SCREEN_COLORS)
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    px = image.load()
    return tuple(tuple(by_rgb[px[x, y][:3]] if px[x, y][3] else None for x in range(image.width))
                 for y in range(image.height))


def connected(cells, diagonal):
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)] + ([(1, 1), (1, -1), (-1, 1), (-1, -1)] if diagonal else [])
    left, found = set(cells), []
    while left:
        stack, part = [left.pop()], set()
        while stack:
            x, y = stack.pop()
            part.add((x, y))
            for dx, dy in steps:
                if (x + dx, y + dy) in left:
                    left.remove((x + dx, y + dy))
                    stack.append((x + dx, y + dy))
        found.append(part)
    return found



def manifest_cases(data):
    """(label, reason, mutation of the JSON manifest) that parse_manifest must refuse before any work."""
    def at(name, key, value):
        return lambda d: next(c for c in d["characters"] if c["id"] == name).__setitem__(key, value)
    crowd = lambda d: d["crowds"][0]  # noqa: E731
    return [
        ("format", "expected format", lambda d: d.update(format="stockchars/2")),
        ("unknown top-level key", "keys must be among", lambda d: d.update(notes="")),
        ("missing placements", "keys must be among", lambda d: d.pop("placements")),
        ("empty characters", "must be a non-empty list", lambda d: d.update(characters=[])),
        ("id with a path", "path-safe", at("glove", "id", "../glove")),
        ("id with a capital", "path-safe", at("glove", "id", "Glove")),
        ("id too long", "path-safe", at("glove", "id", "g" * 33)),
        ("duplicate id", "unique", lambda d: crowd(d).update(id="glove")),
        ("misspelled key", "keys must be among", lambda d: char_of(d, "batter").update(ink_kep=[])),
        ("missing mask", "keys must be among", lambda d: char_of(d, "pair").pop("mask_sha256")),
        ("unknown source kind", "must be intro-panel", at("glove", "source", {"kind": "title-panel", "panel": 0})),
        ("panel 7", "panel: must be an integer from 0 to 6", at("glove", "source", {"kind": "intro-panel", "panel": 7})),
        ("panel as a flag", "panel: must be an integer", at("glove", "source", {"kind": "intro-panel", "panel": True})),
        ("crop off the tile grid", "8-pixel tile grid", at("glove", "crop", [4, 0, 40, 64])),
        ("empty crop", "w: must be an integer from 1", at("glove", "crop", [8, 0, 0, 64])),
        ("crop past the panel", "w: must be an integer from 1 to 32", at("glove", "crop", [32, 0, 40, 64])),
        ("negative crop", "x: must be an integer from 0", at("glove", "crop", [-8, 0, 40, 64])),
        ("crop with three numbers", "must be [x, y, w, h]", at("glove", "crop", [8, 0, 40])),
        ("lowercase color", "two uppercase hex digits", at("glove", "ink", "0c")),
        ("color $0D", "unsupported NES color", at("glove", "ink", "0D")),
        ("color $40", "unsupported NES color", at("glove", "ink", "40")),
        ("color as a number", "two uppercase hex digits", at("glove", "ink", 12)),
        ("recolor to $1E", "unsupported NES color", lambda d: char_of(d, "glove")["colors"].update({"20": "1E"})),
        ("seed outside its box", "inside the seed's box",
         lambda d: char_of(d, "pair")["seeds"][3].update(at=[60, 0])),
        ("seed outside the crop", "x: must be an integer from 0 to 39",
         lambda d: char_of(d, "glove")["seeds"][0].update(at=[40, 0])),
        ("seed through nothing", "non-empty list", lambda d: char_of(d, "glove")["seeds"][0].update(through=[])),
        ("seed without a reason", "keys must be among", lambda d: char_of(d, "glove")["seeds"][0].pop("why")),
        ("null seeds", "seeds: must be a list", at("glove", "seeds", None)),
        ("null specks", "specks: must be a list", at("glove", "specks", None)),
        ("null ink_keep", "ink_keep: must be a list", at("batter", "ink_keep", None)),
        ("screen as a list", "screen: must be a non-empty string",
         at("glove", "target", {"screen": [], "palette": 3})),
        ("part as a list", "part: must be a non-empty string", lambda d: d["placements"][0].update(part=[])),
        ("speck box past the crop", "w: must be an integer from 1 to",
         lambda d: char_of(d, "glove")["specks"][0].update(box=[0, 32, 41, 16])),
        ("speck size 0", "size: must be an integer from 1", lambda d: char_of(d, "glove")["specks"][0].update(size=0)),
        ("drop box past the crop", "h: must be an integer from 1 to",
         lambda d: char_of(d, "pair")["drop"].__setitem__(2, [55, 0, 9, 65])),
        ("drop without a reason", "drop_why", lambda d: char_of(d, "pair").pop("drop_why")),
        ("face past the crop", "h: must be an integer from 1 to", at("cheer", "faces", [[22, 15, 15, 50]])),
        ("no faces", "non-empty list", at("cheer", "faces", [])),
        ("ink_keep past the crop", "x: must be an integer from 0 to 55",
         lambda d: char_of(d, "batter")["ink_keep"].append([56, 8])),
        ("ink_keep twice", "names a pixel twice", lambda d: char_of(d, "pair")["ink_keep"].append([17, 23])),
        ("ink_keep without a reason", "ink_keep_why", lambda d: char_of(d, "pair").pop("ink_keep_why")),
        ("ink_grow as text", "true or false", at("batter", "ink_grow", "yes")),
        ("uppercase mask digest", "lowercase SHA-256", lambda d: char_of(d, "pair").update(
            mask_sha256=char_of(d, "pair")["mask_sha256"].upper())),
        ("unknown screen", "must be one of score, mode", at("glove", "target", {"screen": "title", "palette": 3})),
        ("palette 4", "palette: must be an integer from 0 to 3", at("glove", "target", {"screen": "score", "palette": 4})),
        ("character with per-shirt palettes", "fits one palette",
         at("glove", "target", {"screen": "score", "palettes": {"r": 2}})),
        ("reference digest not hex", "lowercase SHA-256",
         lambda d: char_of(d, "glove")["reference"].update(sha256="screenshot")),
        ("unknown crowd kind", "must be stands-block", lambda d: crowd(d)["source"].update(kind="homerun")),
        ("metatile key lowercase", "single uppercase letters",
         lambda d: crowd(d)["source"]["metatiles"].update(a=crowd(d)["source"]["metatiles"]["A"])),
        ("three-tile metatile", "four CHR $10 tile ids",
         lambda d: crowd(d)["source"]["metatiles"]["A"].update(tiles=["40", "41", "42"])),
        ("tile id not hex", "four CHR $10 tile ids",
         lambda d: crowd(d)["source"]["metatiles"]["A"].update(tiles=["40", "41", "42", "4G"])),
        ("stands palette 4", "palette: must be an integer from 0 to 3",
         lambda d: crowd(d)["source"]["metatiles"]["A"].update(palette=4)),
        ("unknown metatile", "metatile key and a shirt", lambda d: crowd(d)["source"]["rows"][0].__setitem__(0, "Dr")),
        ("cell without a shirt", "metatile key and a shirt", lambda d: crowd(d)["source"]["rows"][0].__setitem__(0, "B")),
        ("ragged rows", "equal-length", lambda d: crowd(d)["source"]["rows"][1].pop()),
        ("shirt without a palette", "one palette per shirt",
         lambda d: crowd(d)["target"].update(palettes={})),
        ("crowd without its observed-order note", "keys must be among", lambda d: crowd(d).pop("arrangement_why")),
        ("placement of nothing", "names no part", lambda d: d["placements"][0].update(part="umpire")),
        ("placement on the wrong screen", "targets the score screen", lambda d: d["placements"][0].update(screen="mode")),
        ("placement off the screen", "x: must be an integer from 0 to 255",
         lambda d: d["placements"][0].update(at=[256, 0])),
        ("area past the part", "w: must be an integer from 1 to",
         lambda d: d["placements"][6].update(area=[48, 0, 48, 32])),
        ("visible past the screen", "h: must be an integer from 1 to",
         lambda d: d["placements"][1].update(visible=[196, 160, 40, 81])),
        ("unplaced part", "place every part",
         lambda d: d.update(placements=[p for p in d["placements"] if p["part"] != "cheer"])),
    ]


def char_of(data, name):
    return next(c for c in data["characters"] if c["id"] == name)


def test_manifest(base, manifest):
    path = convert.ART / "characters.json"
    data = json.loads(path.read_text())
    cases = manifest_cases(data)
    for label, reason, mutate in cases:
        bad = copy.deepcopy(data)
        mutate(bad)
        try:
            parts.parse_manifest(bad, "0" * 64)
        except parts.ManifestError as exc:
            assert reason in str(exc), f"{label}: refused for another reason: {exc}"
            continue
        raise AssertionError(f"the manifest boundary accepted {label}")
    with tempfile.TemporaryDirectory() as temporary:
        broken = Path(temporary) / "characters.json"
        broken.write_text(path.read_text()[:-20])
        refused(parts.load_manifest, "not JSON", broken)
    spec = {c.id: c for c in manifest.characters}
    opaque = next((x, y) for y in range(64) for x in range(64) if stock_panel(base, 6)[y][x][0])
    pixel_cases = [
        ("a seed on figure pixels", "is not an opaque", lambda: parts.cut_character(
            base, replace(spec["glove"], seeds=(parts.Seed((20, 30), frozenset({SKY}), (0, 0, 40, 64)),)))),
        ("an ink_keep on an opaque pixel", "must name a transparent source pixel", lambda: parts.cut_character(
            base, replace(spec["pair"], ink_keep=spec["pair"].ink_keep + (opaque,)))),
        ("a figure color without a target", "have no target", lambda: parts.cut_character(
            base, replace(spec["glove"], colors={k: v for k, v in spec["glove"].colors.items() if k != 0x17}))),
        ("the pair without its reviewed ink", "reviewed mask_sha256", lambda: parts.cut_character(
            base, replace(spec["pair"], ink_keep=()))),
        ("the batter without its reviewed head pixels", "reviewed mask_sha256", lambda: parts.cut_character(
            base, replace(spec["batter"], ink_keep=()))),
        ("the wider reviewed hand box", "reviewed mask_sha256", lambda: parts.cut_character(
            base, replace(spec["pair"], drop=spec["pair"].drop[:2] + ((54, 0, 10, 18),)))),
    ]
    palettes = convert.screen_palettes(convert.ART)
    parts.check_targets(manifest, palettes)
    pixel_cases += [
        ("the glove kid in the red palette", "not in score palette 2",
         lambda: parts.check_targets(replace(manifest, characters=(replace(spec["glove"], palette=2),)), palettes)),
        ("black ink on navy", "must be the score backdrop",
         lambda: parts.check_targets(replace(manifest, characters=(replace(spec["batter"], ink=0x0F),)), palettes)),
        ("blue shirts on the scoreboard", "not in score palette 2", lambda: parts.check_targets(replace(
            manifest, characters=(), crowds=(replace(manifest.crowds[1], screen="score", palettes={"r": 2, "b": 2}),)),
            palettes)),
    ]
    for label, reason, call in pixel_cases:
        refused(call, reason)
    crowd = manifest.crowds[1]
    for gold_first in (True, False):
        shirts = dict(crowd.shirts)
        gold = {key: 0x28 for key in next(iter(shirts.values()))}
        shirts = {"x": gold, **shirts} if gold_first else {**shirts, "x": gold}
        altered = replace(crowd, shirts=shirts, palettes={**crowd.palettes, "x": 2})
        refused(parts.check_targets, "not in mode palette 2",
                replace(manifest, characters=(), crowds=(altered,)), palettes)
    print("crowd targets: incompatible shirts sharing a palette are refused in both insertion orders")
    print(f"manifest: stockchars/1 parses into {len(manifest.characters)} characters, {len(manifest.crowds)} crowds "
          f"and {len(manifest.placements)} placements; {len(cases)} malformed manifests (format, keys, path-safe and "
          "unique ids, source kinds and panels, crops on the grid and in bounds, color types and ranges, seeds, "
          "specks, drops, faces, ink points, digests, targets, metatiles, rows, placements, unplaced parts) and "
          f"broken JSON refused before any pixel is cut; {len(pixel_cases)} pixel-level errors refused (seed on "
          "figure pixels, ink_keep on ink, unmapped color, removed reviewed ink, the wider hand box, target "
          "palettes and backdrop ink)")



def test_pins(base, earlier, manifest):
    source.check_pins(base)
    for rom in earlier:
        source.check_pins(rom)
    for label, bank, address, size, _ in source.PINS:
        drifted = bytearray(base)
        drifted[locate(bank, address + size // 2)] ^= 1
        refused(source.check_pins, label, bytes(drifted))
        refused(parts.cut_parts, label, bytes(drifted), manifest)
    refused(source.check_pins, "iNES header", base[:-1])
    refused(source.check_pins, "iNES header", b"NES\x1b" + base[4:])
    print(f"source pins: all {len(source.PINS)} pinned ranges hold on scoreart32 and on modeart32 and title32; a "
          "one-bit drift in each refuses the pins and the part cutter, naming the range; a short ROM and another "
          "header are refused")


def faces_and_seams(spec, part, src):
    cx, cy, w, h = spec.crop
    kept = sky = 0
    for fx, fy, fw, fh in spec.faces:
        for y in range(fy, fy + fh):
            for x in range(fx, fx + fw):
                value, color = src[cy + y][cx + x]
                if not value:
                    continue
                if part.pixels[y][x] is not None:
                    kept += 1
                elif color == SKY:
                    sky += 1
                else:
                    raise AssertionError(f"{spec.id}: face pixel ({x},{y}) ${color:02X} was dropped")
    for y in range(h):
        for x in range(w):
            value, color = src[cy + y][cx + x]
            if not value or part.pixels[y][x] is not None:
                continue
            for X, Y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (0 <= X < w and 0 <= Y < h and part.pixels[Y][X] is not None and src[cy + Y][cx + X][0]
                        and src[cy + Y][cx + X][1] == color):
                    raise AssertionError(f"{spec.id}: dropped ${color:02X} pixel ({x},{y}) touches a kept one")
    return kept, sky


def test_parts(base, manifest, cut):
    for k in range(len(source.PANELS)):
        _, composition = source.intro_panel(base, k)
        assert [[(p.value, p.color) for p in row] for row in composition.pixels] == stock_panel(base, k), k
    lines = []
    for spec in manifest.characters:
        part = cut[spec.id]
        src = stock_panel(base, spec.panel)
        cx, cy, w, h = spec.crop
        figure = ink = 0
        for y in range(h):
            for x in range(w):
                value, color = src[cy + y][cx + x]
                if part.pixels[y][x] is None:
                    continue
                if value:
                    assert part.pixels[y][x] == spec.colors[color], (spec.id, x, y)
                    figure += 1
                else:
                    assert part.pixels[y][x] == spec.ink, (spec.id, x, y)
                    ink += 1
        kept, sky = faces_and_seams(spec, part, src)
        digest = silhouette_digest(part.pixels)
        assert digest == spec.mask_sha256 == parts.mask_sha256(part.pixels), spec.id
        without_ink = tuple(tuple(None if x == spec.ink else x for x in row) for row in part.pixels)
        assert silhouette_digest(without_ink) != spec.mask_sha256, f"{spec.id}: the mask digest ignores ink"
        lines.append(f"{spec.id} {figure} figure + {ink} source-zero ink, faces keep {kept} ({sky} sky dropped)")
    for spec in manifest.crowds:
        part, src = cut[spec.id], stock_block(base, spec)
        for y, row in enumerate(part.pixels):
            for x, color in enumerate(row):
                value, stock = src[y][x]
                assert color == (spec.shirts[spec.rows[y // 16][x // 16][1]][stock] if value else spec.ink)
    pngs = {pid: sha256(parts.png(part)) for pid, part in cut.items()}
    assert pngs == PART_PNGS, f"part pixels changed: {sorted(k for k in pngs if pngs[k] != PART_PNGS[k])}"

    pair, batter, cheer = cut["pair"], cut["batter"], cut["cheer"]
    for x, y in ((17, 23), (53, 26)):
        assert pair.pixels[y][x] == 0x0C, f"pair source-zero detail ({x},{y}) lost"
    assert all(pair.pixels[y][x] is None for y in range(6, 18) for x in range(55, 64)
               if (x, y) not in ((55, 15), (55, 16), (55, 17))), "the detached raised hand is back"
    assert pair.pixels[16][54] == pair.pixels[17][54] == 0x16, "the neighboring red cap lost its edge"
    assert pair.pixels[27][40] == 0x38 and pair.pixels[27][39] is None, "the shoulder or the sky beside it changed"
    spec = {c.id: c for c in manifest.characters}
    wide = parts.silhouette(base, replace(spec["pair"], drop=spec["pair"].drop[:2] + ((54, 0, 10, 18),)))
    assert wide.pixels[16][54] is None and wide.pixels[17][54] is None, "the wider box no longer clips the cap"
    try:
        faces_and_seams(spec["pair"], wide, stock_panel(base, 6))
    except AssertionError as exc:
        seam = str(exc)
    else:
        raise AssertionError("the wider hand box passes the seam check")
    keep = spec["batter"].ink_keep
    assert len(keep) == 115 and all(batter.pixels[y][x] == 0x0C for x, y in keep)
    painted = {(x, y) for y, row in enumerate(cheer.pixels) for x, c in enumerate(row) if c is not None}
    boot = {(x, y) for x, y in painted if 28 <= x <= 33 and 44 <= y <= 48}
    four = next(c for c in connected(painted, False) if boot & c)
    assert len(painted) == 852 and len(boot) == 25 and four == boot, "the cheer's raised boot changed"
    assert len(connected(painted, True)) == 1, "the boot lost its diagonal connection to the leg"
    for line in lines:
        print(f"  part {line}")
    print("parts: every intro panel decodes the same through the source module and straight from file offsets; "
          "every painted pixel is its source pixel through the manifest colors or kept source-zero ink; face "
          "boxes keep every opaque non-sky pixel; no dropped pixel touches a kept one of its color; each mask "
          "digest recomputed from pixels matches the review and changes when the ink goes; crowds are their "
          "stands blocks through the shirt maps; glove, cheer and crowds are byte-identical to the judged "
          "candidate and batter and pair to the root's correction; the pair keeps (17,23), (53,26), the red cap "
          "(54,16)-(54,17) and the shoulder, and loses the detached hand; the wider box [54,0,10,18] clips the "
          f"cap and fails the seam check ({seam[:70]}); the batter keeps all 115 reviewed head pixels; the cheer "
          "keeps its 25-pixel raised boot, diagonally joined to the leg, in one 852-pixel figure")



def test_regeneration(base, font, pxl):
    sources = convert.read_sources(convert.ART)
    first = convert.regenerate(base, font, pxl, sources)
    second = convert.regenerate(base, font, pxl, sources)
    assert first[0] == second[0] and first[3] == second[3], "regeneration is not deterministic"
    outputs, mode, score, rom = first
    recorded = stage.read_registry()
    assert convert.registry(sources, base, font, outputs, rom) == recorded, "data/stockart32/digests.json is stale"
    assert set(recorded["sources"]) == {f"art/stockart32/{name}" for name in convert.SOURCES}
    assert set(recorded["pins"]) == {label for label, *_ in source.PINS}
    assert sha256(rom) == FROZEN_ROM and recorded["rom"] == FROZEN_ROM
    assert (score.tiles_used, mode.tiles_used) == (TILES["score"], TILES["mode"])
    with tempfile.TemporaryDirectory() as temporary:
        art = Path(temporary) / "score"
        for name in ("score32.px.js", "layout.json"):
            (art / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(convert.ART / "score" / name, art / name)
        shutil.copyfile(convert.ART / "PXL.json", art / "PXL.json")
        for relative, data in outputs.items():
            if relative.startswith("score/out/"):
                (art / relative[6:]).parent.mkdir(parents=True, exist_ok=True)
                (art / relative[6:]).write_bytes(data)
        scene = Path(temporary) / "mode.png"
        scene.write_bytes(outputs["mode/out/scenes/mode.png"])
        assert score_convert.convert(font, art).dumps().encode() == outputs[stage.SCORE_JSON]
        assert mode_convert.convert(font, convert.ART / "mode/layout.json", scene).dumps().encode() == \
            outputs[stage.MODE_JSON]
        assert dict(score.sources) == {name: sha256((art / name).read_bytes()) for name in dict(score.sources)}
    print(f"regeneration: two in-process runs agree on all {len(outputs)} outputs and the ROM; every source, ROM, "
          "pin, output and ROM digest equals data/stockart32/digests.json; the ROM is the frozen corrected "
          f"prototype {FROZEN_ROM}; the unchanged converters, run again on the tracked sources and the "
          f"generated renders, give the same asset bytes; score {score.tiles_used} and mode {mode.tiles_used} "
          "tiles; the score asset pins its tracked sources and generated PNGs")
    return outputs, mode, score, rom


def test_provenance(rom, outputs):
    record = json.loads(outputs["provenance.json"])
    cells = 0
    for part in record["parts"]:
        for cell in part["cells"]:
            start = cell["chr_offset"]
            assert start == CHR_START + cell["chr_bank"] * 0x1000 + 16 * cell["tile"]
            assert sha256(rom[start:start + 16]) == cell["tile_sha256"]
            colors = cell["colors_from"]
            address = int(colors["address"][1:], 16)
            if part["source"]["kind"] == "intro-panel":
                tile_from, palette_from = cell["tile_from"], cell["palette_from"]
                assert prg_byte(rom, 5, int(tile_from["address"][1:], 16)) == cell["tile"]
                selector = prg_byte(rom, 5, int(palette_from["address"][1:], 16))
                assert selector >> palette_from["shift"] & 3 == cell["palette"]
                assert address == 0xFA60 + 4 * cell["palette"] + 1 and colors["bank"] == 15
                oam = cell["oam"]
                assert oam["attribute"] == 0x20 | cell["palette"] and not oam["hflip"] and not oam["vflip"]
            else:
                assert address == 0xF930 + 4 * cell["palette"] + 1
            cells += 1
    tiles = 0
    for placement in record["placements"]:
        bank, screen_at, palette_at, chr_at = convert.SCREEN_BYTES[placement["screen"]]
        data = read(rom, bank, screen_at, 0x400)
        palette = read(rom, bank, palette_at, 32)
        pixels = png_colors(outputs[f"parts/{placement['part']}.png"])
        for tile in placement["tiles"]:
            tx, ty = tile["tile"]
            assert data[32 * ty + tx] == tile["chr_tile"]
            chosen = data[960 + 8 * (ty // 4) + tx // 4] >> (4 * (ty // 2 % 2) + 2 * (tx // 2 % 2)) & 3
            assert chosen == tile["palette"]
            pattern = rom[CHR_START + chr_at + 16 * tile["chr_tile"]:CHR_START + chr_at + 16 * tile["chr_tile"] + 16]
            assert sha256(pattern) == tile["pattern_sha256"]
            values = planar(rom, chr_at // 0x1000, tile["chr_tile"])
            for drawn in tile["from"]:
                px, py, w, h = drawn["part_rect"]
                ox, oy = drawn["tile_rect"][:2]
                count = 0
                for j in range(h):
                    for i in range(w):
                        color = pixels[py + j][px + i]
                        if color is not None:
                            v = values[oy + j][ox + i]
                            assert (palette[4 * chosen + v] if v else palette[0]) == color, (placement["part"], tx, ty)
                            count += 1
                assert count == drawn["pixels"]
            tiles += 1
    print(f"provenance: {cells} part cells name their tile, CHR offset and digest, the map byte, the selector byte "
          "and bit shift and the palette record that the ROM holds, with attribute $20 | palette and no flips; "
          f"{tiles} destination tiles of {len(record['placements'])} placements name the ROM's tile id, pattern "
          "digest and attribute palette, and their part rectangles decode from the ROM tile to the part's colors")


def test_readback(rom, manifest, outputs):
    screens = {screen: screen_colors(rom, screen) for screen in convert.SCREEN_BYTES}
    totals = {}
    for placement in manifest.placements:
        pixels = png_colors(outputs[f"parts/{placement.part}.png"])
        ax, ay, aw, ah = placement.area or (0, 0, len(pixels[0]), len(pixels))
        x0, y0 = placement.at
        vx, vy, vw, vh = placement.visible or (x0, y0, aw, ah)
        shown = 0
        for y in range(ah):
            for x in range(aw):
                sx, sy, color = x0 + x, y0 + y, pixels[ay + y][ax + x]
                if color is None or not (vx <= sx < vx + vw and vy <= sy < vy + vh and sx < 256 and sy < 240):
                    continue
                assert screens[placement.screen][sy][sx] == color, (placement.part, sx, sy)
                shown += 1
        totals[placement.part] = totals.get(placement.part, 0) + shown
    assert {k: totals[k] for k in PLACED} == PLACED, totals
    print(f"ROM readback: decoded from the built ROM's own CHR, screen, attribute and palette bytes without the "
          f"converter's renderer, every visible pixel of all {len(manifest.placements)} placements shows its part "
          f"color: {', '.join(f'{k} {v}' for k, v in totals.items())} pixels")


def edit(path, spots):
    image = Image.open(path).convert("RGBA")
    for (x, y), color in spots:
        image.putpixel((x, y), menu.NES_RGB[color] + (255,))
    image.save(path)


def test_converter_controls(base, font, manifest, outputs):
    """The unchanged converters refuse a mixed-palette cell, a tile overflow and the pair with its cyan kept."""
    with tempfile.TemporaryDirectory() as temporary:
        art = Path(temporary) / "score"
        for relative, data in outputs.items():
            if relative.startswith("score/out/"):
                (art / relative[6:]).parent.mkdir(parents=True, exist_ok=True)
                (art / relative[6:]).write_bytes(data)
        for name in ("score/score32.px.js", "score/layout.json", "PXL.json"):
            shutil.copyfile(convert.ART / name, art / Path(name).name)
        scene = art / score_convert.SCENE
        pristine = scene.read_bytes()
        edit(scene, [((16 * ax + 4, 212), color) for ax in range(6, 10) for color in (0x28,)]
             + [((16 * ax + 5, 212), 0x38) for ax in range(6, 10)])
        wall = refused(score_convert.convert, "fit no palette", font, art)
        assert all(f"cell ({ax},13) colors $16 $28 $38 fit no palette" in wall for ax in range(6, 10)), wall
        scene.write_bytes(pristine)
        edit(scene, [((8 * i + i % 8, 232 + i // 8), 0x38) for i in range(22)])
        overflow = refused(score_convert.convert, "CHR $05 is full", font, art)
        assert "needs 181 tiles beside the 78 glyphs, 178 are free" in overflow, overflow
        mode_scene = Path(temporary) / "mode.png"
        mode_scene.write_bytes(outputs["mode/out/scenes/mode.png"])
        edit(mode_scene, [((96 + 4, 212), 0x16), ((96 + 5, 212), 0x28)])
        mode_wall = refused(mode_convert.convert, "fit no palette", font, convert.ART / "mode/layout.json", mode_scene)
        pair = next(c for c in manifest.characters if c.id == "pair")
        cyan = parts.silhouette(base, replace(pair, colors={**pair.colors, SKY: 0x12}))
        mode_scene.write_bytes(outputs["mode/out/scenes/mode.png"])
        edit(mode_scene, [((120 + x, 156 + y), c) for y, row in enumerate(cyan.pixels[:44]) for x, c in enumerate(row)
                          if c is not None])
        four = refused(mode_convert.convert, "fit no palette", font, convert.ART / "mode/layout.json", mode_scene)
        assert "(8,11)" in four and "'$12', '$16', '$36', '$38'" in four, four
    print(f"converter controls (scratch fixtures): red, gold and cream in score cells (6,13)-(9,13) are refused "
          f"({wall[:46]}); 22 extra tiles overflow CHR $05 ({overflow}); gold beside red on the mode wall is "
          f"refused ({mode_wall[:40]}); the pair with its cyan kept as blue is refused ({four[:64]})")


def test_assets(base, mode, score, outputs):
    """The accepted suites' asset-boundary mutations, applied to the stockart32 assets."""
    count = 0
    for name, kind, cases in (
            (stage.SCORE_JSON, ScoreAssets, lambda r: [(a, b, c) for a, b, c in score_suite.boundary_cases(r, score)]),
            (stage.MODE_JSON, ModeAssets, lambda r: mode_suite.boundary_cases(r))):
        text = outputs[name].decode()
        assert kind.parse(json.loads(text)).dumps() == text, f"{name} does not round-trip"
        for label, reason, mutate in cases(json.loads(text)):
            record = json.loads(text)
            mutate(record)
            try:
                assets = kind.parse(record)
                stage.build_rom(base, assets if kind is ModeAssets else mode, assets if kind is ScoreAssets else score)
            except ValueError as exc:
                assert reason in str(exc), f"{name} {label}: refused for another reason: {exc}"
                count += 1
                continue
            raise AssertionError(f"{name}: the boundary accepted {label}")
    print(f"asset boundary: both stockart32 assets round-trip; the accepted suites' {count} malformed-record cases, "
          "applied to these assets, are each refused with their own reason before a ROM byte is built")



def test_stage(base, rom, mode, score):
    assert stage.build_rom(base, mode, score) == rom
    report = stage.diff_manifest(base, rom, mode, score)
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert {i for r in report["ranges"] for i in r["changed_file_offsets"]} == changed and len(changed) == 4634
    assert {r["name"]: len(r["changed_file_offsets"]) for r in report["ranges"]} == REGION_CHANGES
    assert report["input_sha256"] == stage.BASE_SHA256 and report["output_sha256"] == FROZEN_ROM
    assert len(rom) == len(base) and rom[:16] == base[:16], "size or header changed"
    owned = set()
    for r in stage.REGIONS:
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end)))
    assert changed <= owned
    for bank in range(16):
        start = locate(bank, 0xC000 if bank == 15 else 0x8000)
        if bank not in (stage.MODE_BANK, stage.SCORE_BANK):
            assert rom[start:start + 0x4000] == base[start:start + 0x4000], f"PRG bank {bank} changed"
    for bank in range(32):
        if bank not in (5, 6):
            assert read(rom, "chr", bank * 0x1000, 0x1000) == read(base, "chr", bank * 0x1000, 0x1000), f"CHR ${bank:02X}"
    assert all(read(rom, "chr", 0x5000 + 16 * t, 16) == read(base, "chr", 0x5000 + 16 * t, 16) for t in GLYPHS)
    assert all(read(rom, "chr", 0x6000 + 16 * t, 16) == read(base, "chr", 16 * t, 16) for t in mode.font_glyphs)
    assert read(rom, 13, 0x9420, 0xBE0) == read(base, 13, 0x9420, 0xBE0) and read(rom, 1, 0x95E4, 18) == read(base, 1, 0x95E4, 18)
    assert stage.text_cells(read(rom, 13, 0x9000, 960), mode.font_glyphs) == \
        stage.text_cells(read(base, 13, 0x9000, 960), mode.font_glyphs)
    for name, bank, address, edits in (("mode", 13, 0x9400, {11: 0x36, 15: 0x36}), ("score", 4, 0xB880, {11: 0x36})):
        before, after = read(base, bank, address, 32), read(rom, bank, address, 32)
        assert {i for i in range(32) if before[i] != after[i]} <= set(edits) and all(after[i] == v for i, v in edits.items())

    guards = [(label, bank, address + size // 2) for label, bank, address, size, _ in stage.DIGESTS]
    guards += [(r.name, r.bank, (r.start + r.end) // 2) for r in stage.REGIONS]
    for label, bank, address in guards:
        drifted = bytearray(base)
        drifted[locate(bank, address)] ^= 1
        with patch.object(stage, "BASE_SHA256", sha256(drifted)):
            rejects(stage.build_rom, bytes(drifted), mode, score)
    refused(stage.build_rom, "does not match pinned scoreart32", rom, mode, score)
    refused(stage.build_rom, "ROM size and iNES header", base[:-1], mode, score)
    refused(stage.build_rom, "ROM size and iNES header", base + b"\xFF", mode, score)

    stage_refusals = asset_refusals = 0
    for which, assets in (("mode", mode), ("score", score)):
        for index in range(16, 32):
            palette = bytearray(assets.palette)
            palette[index] = 0x21
            try:
                altered = replace(assets, palette=bytes(palette))
            except AssetError as exc:
                assert index % 4 == 0 and "one backdrop" in str(exc), (which, index, exc)
                asset_refusals += 1
                continue
            refused(stage.build_rom, "sprite palettes stay stock", base, altered if which == "mode" else mode,
                    altered if which == "score" else score)
            stage_refusals += 1
    assert (stage_refusals, asset_refusals) == (24, 8)
    palette_cases = [("mode", 1, 0x16), ("mode", 7, 0x2A), ("mode", 11, 0x27), ("mode", 15, 0x17), ("score", 1, 0x16),
                     ("score", 14, 0x16), ("score", 11, 0x27)]
    for which, index, value in palette_cases:
        assets = mode if which == "mode" else score
        palette = bytearray(assets.palette)
        palette[index] = value
        altered = replace(assets, palette=bytes(palette))
        refused(stage.build_rom, "background skin slots", base, altered if which == "mode" else mode,
                altered if which == "score" else score)

    cursor = bytearray(mode.cursor)
    cursor[0] += 8
    cursor[12] += 8
    letter = bytearray(mode.nametable)
    assert letter[32 * 3 + 9] == ord("L")
    letter[32 * 3 + 9] = menu.BLANK
    font = bytearray(mode.chr)
    font[16 * mode.font_glyphs[-1]] ^= 1
    glyph = bytearray(score.chr)
    glyph[16 * 0x40] ^= 0x80
    contracts = [
        ("26 full-width text rows", "run lists", lambda: stage.build_rom(base, mode_suite.oversized(mode, 26), score)),
        ("a moved cursor", "cursor table", lambda: stage.build_rom(base, replace(mode, cursor=bytes(cursor)), score)),
        ("a blanked LITTLE", "text cells", lambda: stage.build_rom(base, replace(mode, nametable=bytes(letter)), score)),
        ("an edited font glyph", "CHR $00 glyph", lambda: stage.build_rom(base, replace(mode, chr=bytes(font)), score)),
        ("an edited score glyph", "glyph tiles changed", lambda: stage.build_rom(base, mode, replace(score, chr=bytes(glyph)))),
    ]
    for label, reason, call in contracts:
        refused(call, reason)
    changes = stage.change_manifest(base, mode, score)
    first = changes[0]
    tampered = (changes + (first,), changes[1:], (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=first.addr + 1),) + changes[1:], (replace(first, bank=9),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=bytes(len(first.before))),) + changes[1:])
    for bad in tampered:
        with patch.object(stage, "change_manifest", return_value=bad):
            rejects(stage.build_rom, base, mode, score)
    print(f"stage: build_rom is pure and reproduces the frozen ROM; the exact manifest lists all 4634 changed bytes "
          f"({', '.join(f'{k} {v}' for k, v in REGION_CHANGES.items())}), all inside the six regions; header, size, "
          "every other PRG bank and CHR bank, the 78 score glyph tiles, the 24 mode font glyphs, the bank-13 code "
          "and run lists, the cursor table and every lettered cell are unchanged; mode bytes 11 and 15 and score "
          f"byte 11 become $36 and nothing else in either palette moves; {len(guards)} digest and region guards "
          "each refuse a one-bit drift; another ROM and wrong sizes are refused; 24 valid sprite-slot mutations "
          "are refused by the stage and 8 backdrop mutations by asset validation; "
          f"{len(palette_cases)} other palette edits, {len(contracts)} contract breaks and {len(tampered)} tampered "
          "change manifests are refused")



@contextmanager
def checkout(builds):
    """A scratch copy of tools, art and data, with the input ROMs in its build/ and a docs stub."""
    with tempfile.TemporaryDirectory(prefix="stockart32-test-") as temporary:
        scratch = Path(temporary)
        repo = scratch / "repo"
        for name in ("tools", "art", "data"):
            shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        (repo / "docs").mkdir()
        (repo / "docs/notes.md").write_text("docs stay intact\n")
        (repo / "build").mkdir()
        for name in ("scoreart32.nes", "modeart32.nes"):
            shutil.copyfile(builds / name, repo / "build" / name)
        elsewhere = scratch / "elsewhere"
        elsewhere.mkdir()
        yield repo, elsewhere


def run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def ok(result):
    assert result.returncode == 0, result.stderr
    return result


def failed(result, reason):
    assert result.returncode == 2 and reason in result.stderr, (reason, result.returncode, result.stderr[-400:])
    line = result.stderr.strip().splitlines()[-1]
    for scratch in sorted({tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())}, key=len, reverse=True):
        line = line.replace(scratch, "<tmp>")
    return line.split(": ", 1)[-1][:130]


def outputs_match(out, registry):
    found = {p.relative_to(out).as_posix(): sha256(p.read_bytes()) for p in out.rglob("*") if p.is_file()}
    return found == registry["outputs"]


def test_convert_cli(repo, elsewhere, pxl):
    tools, rom_path, font_path = repo / "tools", repo / "build/scoreart32.nes", repo / "build/modeart32.nes"
    cli = [sys.executable, "-B", str(tools / "stockart32_convert.py"), "--rom", str(rom_path), "--font-rom",
           str(font_path), "--pxl", str(pxl)]
    out, registry_path = repo / "build/stockart32", repo / "data/stockart32/digests.json"
    registry = json.loads(registry_path.read_text())
    inputs = {p: p.read_bytes() for p in (rom_path, font_path)}
    snapshot = score_suite.snapshot
    before = snapshot(repo, elsewhere)
    assert "nothing written" in ok(run(cli + ["--check"], elsewhere)).stdout
    assert snapshot(repo, elsewhere) == before and not out.exists(), "--check wrote a file"
    ok(run(cli, elsewhere))
    assert outputs_match(out, registry), "regeneration from another directory differs from the registry"
    installed = snapshot(repo)
    ok(run(cli, elsewhere))
    assert snapshot(repo) == installed, "a repeated regeneration rewrote a file"
    ok(run(cli + ["--check"], elsewhere))
    assert snapshot(repo) == installed

    fake = elsewhere / "fake-pxl"
    fake.mkdir()
    stray_out = elsewhere / "stray"
    stray_out.mkdir()
    (stray_out / "notes.txt").write_text("not ours")
    as_file = elsewhere / "plain-file"
    as_file.write_text("a file")
    safe = elsewhere / "real-out"
    safe.mkdir()
    linked_out = elsewhere / "linked-out"
    linked_out.symlink_to(safe)
    linked_art = elsewhere / "linked-art"
    linked_art.symlink_to(repo / "art/stockart32")
    parts_link = elsewhere / "parts-link"
    parts_link.mkdir()
    (parts_link / "parts").symlink_to(safe)
    aliases = {}
    for label, target in (("symlink to the ROM", rom_path), ("hardlink to the ROM", rom_path),
                          ("hardlink to an unrelated file", as_file)):
        directory = elsewhere / label.replace(" ", "-")
        directory.mkdir()
        if label.startswith("symlink"):
            (directory / stage.MODE_JSON).symlink_to(target)
        else:
            os.link(target, directory / stage.MODE_JSON)
        aliases[label] = directory
    cases = [
        ("--out in tracked art", ["--out", str(repo / "art/stockart32/generated")], "output aliases protected"),
        ("--out in data", ["--out", str(repo / "data/stockart32/generated")], "output aliases protected"),
        ("--out in tools", ["--out", str(repo / "tools/generated")], "output aliases protected"),
        ("--out as docs", ["--out", str(repo / "docs")], "output aliases protected"),
        ("--out as the repository", ["--out", str(repo)], "output aliases protected"),
        ("--out linked into tracked art", ["--out", str(linked_art)], "output aliases protected"),
        ("--out as a linked directory", ["--out", str(linked_out)], "output aliases protected"),
        ("a linked parts directory", ["--out", str(parts_link)], "output aliases protected"),
        ("--out inside the pxl checkout", ["--out", str(fake / "out"), "--pxl", str(fake)], "output aliases protected"),
        ("--out holding another file", ["--out", str(stray_out)], "does not write"),
        ("--out as a file", ["--out", str(as_file)], "not a directory"),
        ("--out as build/", ["--out", str(repo / "build")], "does not write"),
        *((f"an asset JSON as a {label}", ["--out", str(directory)], "output aliases protected")
          for label, directory in aliases.items()),
        ("--check with --record", ["--check", "--record"], "drop --record"),
    ]
    before = snapshot(repo, elsewhere)
    lines = []
    for label, args, reason in cases:
        lines.append(f"{label}: {failed(run(cli + args, elsewhere), reason)}")
        assert snapshot(repo, elsewhere) == before, f"{label}: a refused run changed a file"
    for link in ("symlink", "hardlink"):
        original = registry_path.read_bytes()
        registry_path.unlink()
        moved = elsewhere / "registry-target.json"
        moved.write_bytes(original)
        registry_path.symlink_to(moved) if link == "symlink" else os.link(moved, registry_path)
        before = snapshot(repo, elsewhere)
        failed(run(cli + ["--record"], elsewhere), "output aliases protected")
        assert snapshot(repo, elsewhere) == before
        registry_path.unlink()
        moved.unlink()
        registry_path.write_bytes(original)

    def attempt(label, path, change, reason, *extra):
        """Change one source, expect a refusal that writes nothing, then restore it."""
        original = path.read_bytes()
        path.write_bytes(change(original))
        before = snapshot(repo, elsewhere)
        line = failed(run(cli + list(extra), elsewhere), reason)
        assert snapshot(repo, elsewhere) == before, f"{label}: a failed run changed a file"
        path.write_bytes(original)
        lines.append(f"{label}: {line}")
    manifest = repo / "art/stockart32/characters.json"
    score_source = repo / "art/stockart32/score/score32.px.js"

    def without_pair_ink(data):
        record = json.loads(data)
        char_of(record, "pair").pop("ink_keep")
        char_of(record, "pair").pop("ink_keep_why")
        return json.dumps(record).encode()

    def off_grid(data):
        record = json.loads(data)
        char_of(record, "glove")["crop"] = [4, 0, 40, 64]
        return json.dumps(record).encode()
    attempt("the pair without its reviewed ink", manifest, without_pair_ink, "reviewed mask_sha256")
    attempt("a crop off the tile grid", manifest, off_grid, "8-pixel tile grid")
    attempt("broken pxl source", score_source, lambda d: d + b"\nthis is not javascript (\n", "pxl could not build")
    attempt("an unsupported layout color", repo / "art/stockart32/score/layout.json",
            lambda d: d.replace(b'"16", "38", "36"', b'"16", "38", "0D"'), "unsupported NES color")
    attempt("another pxl commit", repo / "art/stockart32/PXL.json",
            lambda d: d.replace(b"3bc816cb15a14592e0dc062ee98013637d399457", b"0" * 40), "not the pinned")
    windows, gold = b'c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "c")', b'c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "y")'
    assert score_source.read_bytes().count(windows) == 1
    attempt("an art edit without --record", score_source, lambda d: d.replace(windows, gold),
            "differs from data/stockart32/digests.json")
    attempt("an art edit under --check", score_source, lambda d: d.replace(windows, gold),
            "differs from data/stockart32/digests.json", "--check")
    drifted = elsewhere / "drifted.nes"
    data = bytearray(inputs[rom_path])
    data[locate("chr", 0x14000 + 0x123)] ^= 1
    drifted.write_bytes(data)
    lines.append("a drifted CHR $14 input: " + failed(run(cli[:4] + [str(drifted)] + cli[5:], elsewhere),
                                                      "--rom must be the pinned scoreart32"))
    lines.append("another font ROM: " + failed(run(cli[:6] + [str(rom_path)] + cli[7:], elsewhere),
                                               "--font-rom must be the pinned modeart32"))

    original_registry = registry_path.read_bytes()
    score_source.write_bytes(score_source.read_bytes().replace(windows, gold))
    ok(run(cli + ["--record"], elsewhere))
    edited = json.loads(registry_path.read_text())
    assert edited["rom"] != FROZEN_ROM and outputs_match(out, edited)
    builder = [sys.executable, "-B", str(tools / "build_stockart32.py"), str(rom_path)]
    ok(run(builder + ["-o", str(elsewhere / "edited.nes")], elsewhere))
    assert sha256((elsewhere / "edited.nes").read_bytes()) == edited["rom"]
    score_source.write_bytes(score_source.read_bytes().replace(gold, windows))
    ok(run(cli + ["--record"], elsewhere))
    assert registry_path.read_bytes() == original_registry and outputs_match(out, registry)
    assert all(p.read_bytes() == data for p, data in inputs.items()), "an input ROM changed"
    for line in lines:
        print(f"  refused {line}")
    print(f"convert CLI (temporary checkout): --check passes and writes nothing; regeneration from another "
          f"directory installs exactly the registered outputs and a repeated run rewrites nothing; {len(cases)} "
          "hostile outputs (tracked art, data, tools, docs, the repository, linked directories, the pxl "
          "checkout, foreign files, a file, links to the ROM or another file) and a linked registry are refused "
          f"before any write; {len(lines) - len(cases)} failing sources, pins, art edits and inputs are refused "
          "with every file unchanged; --record accepts an art edit, the builder follows it, and recording the "
          "restored art gives back the tracked registry byte for byte")


def test_builder_cli(repo, elsewhere, base, rom, mode, score):
    tools, rom_path = repo / "tools", repo / "build/scoreart32.nes"
    out = repo / "build/stockart32"
    sources = [tools / name for name in ("build_stockart32.py", "stockart32_convert.py", "stockart32_parts.py",
                                         "test_stockart32.py", "build_scoreart32.py")]
    sources += [repo / "art/stockart32/characters.json", repo / "art/stockart32/score/score32.px.js",
                repo / "data/stockart32/digests.json", repo / "data/scoreart32/scoreassets.json", repo / "docs/notes.md",
                out / stage.MODE_JSON, out / stage.SCORE_JSON, repo / "build/modeart32.nes"]
    count = check_output_guards(tools / "build_stockart32.py", rom_path, rom, stage.diff_manifest(base, rom, mode, score),
                                sources)
    cli = [sys.executable, "-B", str(tools / "build_stockart32.py"), str(rom_path)]
    canonical = repo / "build/stockart32.nes"
    result = ok(run(cli + ["-o", str(canonical)], elsewhere))
    assert canonical.read_bytes() == rom and FROZEN_ROM in result.stdout
    copied = elsewhere / "assets"
    shutil.copytree(out, copied)
    record = json.loads((copied / stage.SCORE_JSON).read_text())
    record["tiles_used"] += 1
    (copied / stage.SCORE_JSON).write_text(json.dumps(record))
    never = elsewhere / "never.nes"
    before = score_suite.snapshot(repo, elsewhere)
    lines = [failed(run(cli + ["-o", str(never), "--assets", str(copied)], elsewhere), "digests.json")]
    lines.append(failed(run(cli + ["-o", str(out / "inside.nes")], elsewhere), "output aliases protected"))
    lines.append(failed(run(cli + ["-o", str(never), "--assets", str(elsewhere / "missing")], elsewhere), "No such"))
    assert not never.exists() and score_suite.snapshot(repo, elsewhere) == before
    registry = repo / "data/stockart32/digests.json"
    original = registry.read_bytes()
    edited = json.loads(original)
    edited["rom"] = "0" * 64
    registry.write_text(json.dumps(edited))
    lines.append(failed(run(cli + ["-o", str(never)], elsewhere), "differs from data/stockart32/digests.json"))
    registry.write_bytes(original)
    assert not never.exists()
    print(f"builder CLI (temporary checkout): deterministic ROM and manifest from another directory; {count} "
          "protected targets refused (input, renamed copy, tools, art, data, docs, the registry, the asset files it "
          "reads, an earlier ROM, symbolic and hard links); a bad input keeps the previous output; the "
          f"canonical build is the frozen ROM; refused with nothing written: {'; '.join(lines)}")


def test_installed(rom, candidate):
    out = stage.ASSETS
    if out.is_dir():
        assert outputs_match(out, stage.read_registry()), f"{out} is stale; rerun tools/stockart32_convert.py"
        line = f"installed: {out} holds exactly the registered outputs"
    else:
        line = f"installed: {out} absent (not checked)"
    if candidate:
        assert Path(candidate).read_bytes() == rom, "candidate differs from the deterministic build"
        line += f"; {candidate} is the deterministic build"
    print(line)


def test_references(base, manifest, path):
    """The ROM decodes against the screenshots the manifest names, by the captures' own palette."""
    refs = json.loads(Path(path).read_text())
    recorded = json.loads((convert.ART / "characters.json").read_text())
    lines = []
    for spec in manifest.characters + manifest.crowds:
        entry = next(e for e in recorded["characters"] + recorded["crowds"] if e["id"] == spec.id)["reference"]
        shot = Path(refs[entry["capture"]])
        assert sha256(shot.read_bytes()) == entry["sha256"], f"{entry['capture']} is not the recorded capture"
        image = Image.open(shot).convert("RGB")
        px = image.load()
        rows = stock_panel(base, spec.panel) if isinstance(spec, parts.Character) else stock_block(base, spec)
        x0, y0, w, h = entry["crop"]
        diff = sum(px[x0 + x, y0 + y] != SHOT_RGB[rows[y][x][1]] for y in range(h) for x in range(w))
        assert diff == 0, f"{spec.id}: {diff} of {w * h} pixels differ from {entry['capture']}"
        lines.append(f"{spec.id} vs {entry['capture']} {w}x{h}")
    print(f"references: {'; '.join(lines)}: 0 pixels differ in each, every capture's SHA-256 as recorded")



def test_score_runtime(stock, accepted, rom, assets, quick):
    score_suite.test_timing(stock, rom, quick)
    score_suite.test_samples(stock, rom, assets)
    score_suite.test_boards(stock, rom, assets, quick)
    score_suite.test_ram(stock, rom)
    score_suite.test_flows(stock, rom, quick)
    if not quick:
        score_suite.test_nmi(rom)
    score_suite.test_negative_controls(stock, rom, assets)
    for name, entry, pads, frames in score_suite.flows(quick):
        try:
            score_suite.flow_check(accepted, rom, entry, pads, frames)
        except AssertionError as exc:
            raise AssertionError(f"{name} differs from scoreart32: {exc}") from None
    print(f"scoreboard against scoreart32: all {len(score_suite.flows(quick))} exits match the accepted stage frame "
          "for frame (scene writes, sound requests, per-frame scene, bank, song, rendering and every APU write)")


def test_mode_runtime(stock, accepted, rom, assets, layout, scene, quick):
    with patch.object(mode_convert, "LAYOUT", layout), patch.object(mode_convert, "SCENE", scene):
        screens = mode_suite.oracle_screens(rom)
        mode_suite.test_overlays(rom, screens)
        mode_suite.test_art_pixels(rom)
        mode_suite.test_title_tail(rom)
        mode_suite.test_tour(rom, stock, assets, screens)
        mode_suite.test_entries(rom, stock, assets, screens)
        mode_suite.test_exit_parity(stock, rom)
        mode_suite.test_series_reentry(stock, rom, assets, screens)
        mode_suite.test_contract(stock, rom)
        mode_suite.test_audio(stock, rom)
        if not quick:
            mode_suite.test_pick_flows(rom)
            mode_suite.test_nmi(rom)
        mode_suite.test_negative_controls(stock, rom, assets, screens)
        for name, steps in mode_suite.FLOWS.items():
            ours, theirs = mode_suite.scene_run(rom, steps)[0], mode_suite.scene_run(accepted, steps)[0]
            assert ours == theirs, f"{name}: scoreart32 {theirs} vs stockart32 {ours}"
        mode_suite.test_audio(accepted, rom)
    print(f"mode menu against scoreart32: all {len(mode_suite.FLOWS)} exits give the accepted stage's scenes, mode "
          "and ownership bytes and sound requests, and its idle APU writes and press sounds")



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pxl", type=Path, required=True, help="pinned claude-pxl checkout")
    ap.add_argument("--build", type=Path, default=ROOT / "build", help="directory holding the input ROMs")
    ap.add_argument("--candidate", type=Path, help="a built stockart32 ROM to compare with the deterministic build")
    ap.add_argument("--references", type=Path, help="references.json naming the reference screenshots")
    ap.add_argument("--quick", action="store_true", help="shorter runtime suites, no NMI sweeps or picker flows")
    args = ap.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    pxl = args.pxl.resolve()
    roms = {name: (args.build / name).read_bytes() for name in INPUTS}
    for name, digest in INPUTS.items():
        assert sha256(roms[name]) == digest, f"{name} is not the pinned input"
    base, font, title = roms["scoreart32.nes"], roms["modeart32.nes"], roms["title32.nes"]
    print(f"inputs: scoreart32 {INPUTS['scoreart32.nes']}, modeart32 {INPUTS['modeart32.nes']}, "
          f"title32 {INPUTS['title32.nes']}")
    manifest = parts.load_manifest(convert.ART / "characters.json")
    test_manifest(base, manifest)
    test_pins(base, (font, title), manifest)
    cut = parts.cut_parts(base, manifest)
    test_parts(base, manifest, cut)
    outputs, mode, score, rom = test_regeneration(base, font, pxl)
    test_provenance(rom, outputs)
    test_readback(rom, manifest, outputs)
    test_converter_controls(base, font, manifest, outputs)
    test_assets(base, mode, score, outputs)
    test_stage(base, rom, mode, score)
    with checkout(args.build) as (repo, elsewhere):
        test_convert_cli(repo, elsewhere, pxl)
        test_builder_cli(repo, elsewhere, base, rom, mode, score)
    test_installed(rom, args.candidate)
    if args.references:
        test_references(base, manifest, args.references)
    with tempfile.TemporaryDirectory() as temporary:
        scene = Path(temporary) / "mode.png"
        scene.write_bytes(outputs["mode/out/scenes/mode.png"])
        test_score_runtime(font, base, rom, score, args.quick)
        test_mode_runtime(title, base, rom, mode, convert.ART / "mode/layout.json", scene, args.quick)
    assert all((args.build / name).read_bytes() == roms[name] for name in INPUTS), "an input ROM changed"
    print(f"stockart32 SHA256 {sha256(rom)}")
    print(f"PASS ({time.monotonic() - started:.1f}s)" + (" quick" if args.quick else ""))


if __name__ == "__main__":
    main()
