#!/usr/bin/env python3
"""Check the homerunart32 stage: its sources and their boundaries, the parts against the ROM, regeneration, the
converter's refusals, the guarded builder and the reader argument, the built ROM's own bytes, and the HOME RUN
celebration at runtime against the analysisart32 input.

    .venv/bin/python -B tools/test_homerunart32.py build/analysisart32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python -B tools/test_homerunart32.py build/analysisart32.nes --quick
    .venv/bin/python -B tools/test_homerunart32.py build/analysisart32.nes --candidate BAD.nes --verify-only

Every section runs and every failure is reported; any failure exits with status 1. Oracles are pinned or derived
from the input, never from the candidate's own tables: the selected ROM's SHA-256 and the two frames' pixel
digests are pinned constants; runs, scores, game-over and debits come from the stock rules applied to the
planted RAM (homerunart32_machine.expected_home_run); part pixels from an independent decode of the intro
panels and stands; screens from an independent decode of the $C5C4 tables. Runtime parity runs stock and
candidate from one saved state, so each difference is the candidate's.

--pxl regenerates the art twice with the pinned renderer and runs the converter command line; without it the
installed build/homerunart32 outputs must match data/homerunart32/digests.json. --quick uses the two fastest
played games, fewer planted cases, teams, vblank phases and contract teams. --candidate names the ROM the
oracles judge (default: the deterministic build, which must also equal it). --verify-only judges only the
candidate's static picture, data-only diff and reader argument; it is the command the suite itself must see
exit 1 on known-bad ROMs.

Fixtures: played home runs are machine states from WATCH games booted from RESET on the input
(tools/homerunart32_fixtures.py). The suite loads them from build/homerunart32-fixtures when that cache's
provenance matches, and plays the games again otherwise (about 5 minutes for --quick, 25 for the full set).

The CPU model counts cycles but approximates the PPU: frames are composed from VRAM, palette RAM and CHR, sprite-0
is manufactured, open bus and fetch timing are not modelled, and audio is APU register writes. Real-core
captures, the mapper census over SPEED, VICTORY and attract, listening, hardware, PAL and a second emulator
belong to root.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

from PIL import Image

import analysisart32_convert as accepted
import analysisart32_machine as earlier
import build_homerunart32 as stage
from build_draw32 import locate, read
from frontend32_test_machine import check_output_guards
import homerunart32_assets as model
from homerunart32_assets import AssetError, Cast, HomerunAssets, Layout
import homerunart32_convert as convert
import homerunart32_fixtures as played
import homerunart32_machine as machine
import homerunart32_readers as readers
import menu32_convert as menu
import stockart32_parts as parts

ROOT = stage.ROOT
STOCK_SHA256 = "1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e"
TARGET_SHA256 = "a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b"
RENDER_PIXELS = {"a": "f6a3a5c1f87d9fe363294e13718b323811b95c80ba846890953dc27fe9def498",
                 "b": "fd3c05812e9cc9836523f79dac4325ecd7696304a6bf5edd555145353b0e824b"}
CHANGED, CLAIMED, REGION_COUNT, TILE_PAIRS, METATILES = 8275, 8972, 464, 223, 115
STILL = {"pair": ((20, 150), 1621), "batter": ((176, 152), 803)}
MOVING = {"cheerleader": (104, 156, 48, 64), "stands crowd": (0, 104, 256, 48), "marquee": (24, 16, 208, 80)}
CHEER_B = ("b88111f1cdd2c16ecfe4db3d2e652451a99d92ea2097f3a544860cc26f291c4b",
           "f7008b62e938fc1b9f1acfaa13a547140d8bf7c45ae49960d54f8c6be0d948ed")
PART_MANIFEST = ROOT / model.PART_MANIFEST
# RAM that may differ from stock at the cutscene exit, with the reason; 240 frames later only the loader buffers
# may (on the scoreboard path, which does not run the loader), and a stale-read watch must see no read of them.
EXIT_SCRATCH = {**dict.fromkeys(range(0x0100, 0x0180), "the $C5C4 loader's map buffer"),
                **dict.fromkeys(range(0x0340, 0x0360), "the $C5C4 loader's row buffer"),
                **dict.fromkeys(range(0x0195, 0x01B5), "palette staging: record $0E and its backdrop mirrors")}
LEADS = (1, 777, 5003, 14011, 22027, 29000)                   # the judge's vblank-phase offsets, in CPU cycles
MASH = [0x80, 0x40, 0x10, 0x20, 0x00]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Failure(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise Failure(message)


def refused(call, reason, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except (ValueError, KeyError) as exc:
        check(reason in str(exc), f"refused for another reason: {exc} (expected {reason!r})")
        return str(exc).splitlines()[0]
    raise Failure(f"{getattr(call, '__name__', call)} accepted a case it must refuse ({reason!r})")


def png_rows(data):
    image = Image.open(io.BytesIO(data)).convert("RGB")
    return [[image.getpixel((x, y)) for x in range(image.width)] for y in range(image.height)]


def rows_digest(rows):
    return sha256(bytes(c for row in rows for pixel in row for c in pixel))


def patched(rom, edits):
    data = bytearray(rom)
    for bank, address, values in edits:
        data[locate(bank, address):locate(bank, address) + len(values)] = values
    return bytes(data)



def word(data):
    return data[0] | data[1] << 8


def decode_panel(rom, k):
    """Intro picture k as (pattern value, NES color or None) rows: bank 5 origins/maps/selectors, CHR $14 and
    sprite palette record $8E at fixed $FA60, read here without tools/stockart32_source.py."""
    tiles_at, selectors_at = word(read(rom, 5, 0xB1F6 + 2 * k, 2)), word(read(rom, 5, 0xB204 + 2 * k, 2))
    record = read(rom, 15, 0xFA60, 16)
    rows = [[None] * 64 for _ in range(64)]
    for i in range(64):
        tile = read(rom, 5, tiles_at + i, 1)[0]
        palette = (read(rom, 5, selectors_at + i // 4, 1)[0] >> 2 * (i % 4)) & 3
        pattern = read(rom, "chr", 0x14 * 0x1000 + 16 * tile, 16)
        for y in range(8):
            for x in range(8):
                v = (pattern[y] >> (7 - x)) & 1 | ((pattern[y + 8] >> (7 - x)) & 1) << 1
                rows[8 * (i // 8) + y][8 * (i % 8) + x] = (v, record[4 * palette + v] if v else None)
    return rows


def neighbours8(x, y):
    return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def outside(blocked, w, h):
    """Pixels 4-connected to the crop border through pixels not in `blocked`."""
    seen = set()
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while stack:
        p = stack.pop()
        if p in seen or p in blocked or not (0 <= p[0] < w and 0 <= p[1] < h):
            continue
        seen.add(p)
        stack += [(p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)]
    return seen


def components8(cells):
    left, found = set(cells), []
    while left:
        stack, part = [left.pop()], set()
        while stack:
            p = stack.pop()
            part.add(p)
            for q in neighbours8(*p):
                if q in left:
                    left.discard(q)
                    stack.append(q)
        found.append(part)
    return found


def verify_character(rom, spec, part):
    """Every opaque part pixel recolors its source pixel or is ink on a source zero; with the plain ink rule
    (no ink_grow, no ink_keep) the ink is exactly the source zeros touching the figure or enclosed by it."""
    src = decode_panel(rom, spec.panel)
    cx, cy, w, h = spec.crop
    figure, ink, zeros, wrong = set(), set(), set(), []
    for y in range(h):
        for x in range(w):
            v, color = src[cy + y][cx + x]
            zeros |= {(x, y)} if not v else set()
            c = part.pixels[y][x]
            if c is None:
                continue
            if v and spec.colors.get(color) != c:
                wrong.append((x, y))
            if not v and c != spec.ink:
                wrong.append((x, y))
            (figure if v else ink).add((x, y))
    check(not wrong, f"{spec.id}: {len(wrong)} pixels are not their source recolored or ink, first {wrong[:3]}")
    check(ink <= zeros, f"{spec.id}: ink sits on an opaque source pixel")
    if not spec.ink_grow and not spec.ink_keep:
        reach = outside(figure, w, h)
        wanted = {p for p in zeros if any(q in figure for q in neighbours8(*p)) or p not in reach}
        check(ink == wanted, f"{spec.id}: ink differs from the source zeros touching or enclosed by the figure in "
                             f"{len(ink ^ wanted)} pixels")
    return len(figure), len(ink), len(zeros - ink)


def verify_crowd(rom, spec, part):
    """Every crowd pixel is its CHR $10 stands pixel in record $15, recolored by its shirt, or ink on a zero."""
    record = read(rom, 15, 0xF930, 16)
    wrong = 0
    for j, row in enumerate(spec.rows):
        for i, (key, shirt) in enumerate(row):
            tiles, palette = spec.metatiles[key]
            for q, tile in enumerate(tiles):
                pattern = read(rom, "chr", 0x10 * 0x1000 + 16 * tile, 16)
                for y in range(8):
                    for x in range(8):
                        v = (pattern[y] >> (7 - x)) & 1 | ((pattern[y + 8] >> (7 - x)) & 1) << 1
                        want = spec.shirts[shirt].get(record[4 * palette + v]) if v else spec.ink
                        wrong += part.pixels[16 * j + 8 * (q >> 1) + y][16 * i + 8 * (q & 1) + x] != want
    check(not wrong, f"{spec.id}: {wrong} pixels differ from the recolored stands block")
    return part.width * part.height



def suite_sources():
    layout, manifest, cast = convert.models(convert.read_sources())
    return layout, manifest, cast, convert.specs(manifest, cast)


def test_boundaries():
    approved = {p.id: p for p in parts.load_manifest(PART_MANIFEST).parts}
    layout0 = json.loads((model.ART / "layout.json").read_text())
    cast0 = json.loads((model.ART / "cast.json").read_text())

    def layout(edit):
        data = json.loads(json.dumps(layout0))
        edit(data)
        return Layout.parse(data, "0" * 64)

    def cast(edit):
        data = json.loads(json.dumps(cast0))
        edit(data)
        return Cast.parse(data, "0" * 64, approved)
    pose = lambda d: d["poses"][0]  # noqa: E731
    cases = [
        (layout, lambda d: d.update(format="homerunart32-layout/0"), "expected format"),
        (layout, lambda d: d["palettes"].pop(), "four background palettes"),
        (layout, lambda d: d["palettes"].__setitem__(0, ["21", "21", "28"]), "four distinct RGB"),
        (layout, lambda d: d.update(backdrop="0D"), "unsupported NES color"),
        (layout, lambda d: d["scenes"].pop("b"), "keys must be among"),
        (layout, lambda d: d["scenes"].update(b="homerun_a"), "two distinct"),
        (cast, lambda d: d.update(approved="art/stockart32/other.json"), "reviewed part source"),
        (cast, lambda d: d["placements"][0].update(part="glovebox"), "names no approved part or pose"),
        (cast, lambda d: d["placements"][0].update(frames="c"), "'a', 'b' or 'ab'"),
        (cast, lambda d: d["placements"][0].update(visible=[250, 150, 64, 50]), "visible w"),
        (cast, lambda d: d["placements"][0].pop("why"), "why"),
        (cast, lambda d: pose(d).update({"from": "crowd-red"}), "must name an approved character"),
        (cast, lambda d: pose(d).update(panel=4), "must differ"),
        (cast, lambda d: pose(d).pop("png_sha256"), "png_sha256"),
        (cast, lambda d: pose(d).update(mask_sha256="B" * 64), "lowercase SHA-256"),
        (cast, lambda d: pose(d).update(drop=[[40, 0, 10, 10]]), "drop[0] w"),
        (cast, lambda d: pose(d).update(id="cheer"), "already a part"),
        (cast, lambda d: d.update(placements=[p for p in d["placements"] if p["part"] != "cheer-b"]),
         "place every pose"),
        (cast, lambda d: [p.update(frames="a") for p in d["placements"]], "frame b stamps nothing"),
    ]
    reasons = [refused(parse, reason, edit) for parse, edit, reason in cases]
    return [f"boundaries: {len(cases)} malformed layouts and casts refused, e.g. {reasons[2]}; {reasons[12]}"]


def test_parts(stock, outputs):
    _, _, cast, rules = suite_sources()
    cut = convert.cut(stock, rules)
    approved = accepted.approved_parts()
    lines = []
    for pid, part in cut.items():
        data = parts.png(part)
        check(data == outputs[f"parts/{pid}.png"], f"{pid}: the installed part differs from a fresh cut")
        if pid == "cheer-b":
            check((parts.mask_sha256(part.pixels), sha256(data)) == CHEER_B, "cheer-b differs from its reviewed digests")
        else:
            check(sha256(data) == approved[f"parts/{pid}.png"], f"{pid} differs from the approved stockart32 part")
    for pid in ("cheer", "cheer-b", "pair", "batter"):
        kept, ink, cleared = verify_character(stock, rules[pid], cut[pid])
        lines.append(f"  {pid}: {kept} figure pixels recolor their source exactly, {ink} ink pixels on source zeros, "
                     f"{cleared} source zeros clear")
    lines.append(f"  crowd-red: {verify_crowd(stock, rules['crowd-red'], cut['crowd-red'])} pixels equal the recolored "
                 "stands block")
    spec = rules["cheer-b"]
    loose = parts.silhouette(stock, replace(spec, drop=()))
    src = decode_panel(stock, spec.panel)
    opaque = {(x, y) for y in range(spec.size[1]) for x in range(spec.size[0])
              if src[spec.crop[1] + y][spec.crop[0] + x][0]}
    kept = {p for p in opaque if cut["cheer-b"].pixels[p[1]][p[0]] is not None}
    removed = {p for p in opaque if loose.pixels[p[1]][p[0]] is not None and p not in kept}
    groups = components8(removed)
    inside = [all(any(bx <= x < bx + bw and by <= y < by + bh for bx, by, bw, bh in spec.drop) for x, y in g)
              for g in groups]
    check(len(groups) == len(spec.drop) and all(inside), f"cheer-b: the drop boxes remove {len(groups)} components, "
                                                          f"inside the boxes: {inside}")
    check(not any(q in kept for p in removed for q in neighbours8(*p)),
          "cheer-b: a dropped pixel touches her kept figure")
    face = [(x, y) for fx, fy, fw, fh in spec.faces for y in range(fy, fy + fh) for x in range(fx, fx + fw)
            if src[spec.crop[1] + y][spec.crop[0] + x][0] and src[spec.crop[1] + y][spec.crop[0] + x][1] != 0x2C
            and cut["cheer-b"].pixels[y][x] is None]
    check(not face, f"cheer-b: {len(face)} opaque non-sky face pixels are lost")
    lines.append(f"  cheer-b drop boxes remove exactly {len(groups)} neighbour figure components "
                 f"({', '.join(str(len(g)) for g in sorted(groups, key=len, reverse=True))} px) wholly inside them, "
                 "none touching her; her face box keeps every opaque non-sky pixel")
    return [f"parts: {', '.join(cut)} cut from the input; approved parts equal data/stockart32/digests.json, cheer-b "
            f"its registered mask {CHEER_B[0][:8]} and PNG {CHEER_B[1][:8]}"] + lines


def test_regeneration(stock, pxl):
    sources = convert.read_sources()
    first = convert.regenerate(stock, pxl, sources)
    second = convert.regenerate(stock, pxl, sources)
    check(first[0] == second[0] and first[2] == second[2], "two pinned regenerations differ")
    outputs, assets, rom, still = first
    check(convert.registry(sources, stock, outputs, rom) == stage.read_registry(),
          "the regenerated art differs from data/homerunart32/digests.json")
    check(sha256(rom) == TARGET_SHA256, f"the regenerated ROM is {sha256(rom)}, not the selected celebration")
    for f in model.FRAMES:
        rows = png_rows(outputs[f"render/scenes/homerun_{f}.png"])
        check(rows_digest(rows) == RENDER_PIXELS[f], f"render {f} differs from the selected frame's pixels")
    return outputs, assets, rom, [f"regeneration: two pinned pxl renders and conversions are identical; outputs and "
                                  f"ROM equal data/homerunart32/digests.json; ROM {TARGET_SHA256[:12]}, both frames' "
                                  "pixels equal the selected design's"]


def installed_outputs():
    out, registry = stage.ASSETS, stage.read_registry()
    found = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    check({k: sha256(v) for k, v in found.items()} == registry["outputs"],
          "build/homerunart32 does not hold exactly the registered outputs")
    return found



def synthetic(frames):
    encoded = {}
    for f, rows in frames.items():
        image = Image.new("RGB", (256, 240))
        image.putdata([pixel for row in rows for pixel in row])
        encoded[f] = accepted.png_bytes(image)
    return encoded


def test_converter_controls(stock, renders):
    layout, _, cast, rules = suite_sources()
    rgb = menu.NES_RGB
    sky, cream, gold, red, green = (rgb[c] for c in (0x21, 0x38, 0x28, 0x16, 0x1A))
    rng = random.Random(32)
    noise = [[rng.choice((sky, cream, gold, rgb[layout.backdrop])) for _ in range(256)] for _ in range(240)]
    flat = [[sky] * 256 for _ in range(240)]
    clash = [row[:] for row in flat]
    clash[3][3], clash[4][4] = red, green
    quads = [row[:] for row in flat]
    for c in range(240):
        for k, (dx, dy) in enumerate(((0, 0), (8, 0))):
            value = (c >> (4 * k)) & 15
            for bit in range(4):
                if value >> bit & 1:
                    quads[16 * (c // 16) + dy + 2 * bit][16 * (c % 16) + dx + 3] = cream
    lines = [refused(convert.convert, "hold 256", stock, layout, synthetic({"a": noise, "b": flat})),
             refused(convert.convert, "no layout palette holds them all", stock, layout,
                     synthetic({"a": clash, "b": flat})),
             refused(convert.convert, "leave 151 ids", stock, layout, synthetic({"a": quads, "b": quads}))]
    cut = convert.cut(stock, rules)
    rows = {f: png_rows(renders[f]) for f in model.FRAMES}
    check(convert.check_placements(cast, cut, rows, "the render"), "the selected renders fail their own placements")
    for part, frame in (("pair", "b"), ("batter", "a"), ("crowd-red", "b"), ("cheer-b", "b")):
        placement = next(p for p in cast.placements if p.part == part and frame in p.frames)
        shown, (dx, dy) = accepted.visible_rect(placement, cut[part])
        x, y = next((x, y) for y in range(shown[1], shown[1] + shown[3]) for x in range(shown[0], shown[0] + shown[2])
                    if cut[part].pixels[y - dy][x - dx] is not None)
        bad = {f: [row[:] for row in rows[f]] for f in model.FRAMES}
        bad[frame][y][x] = gold if bad[frame][y][x] != gold else red
        lines.append(refused(convert.check_placements, f"placement of {part}", cast, cut, bad, f"{part} in {frame}"))
    hop = {f: [row[:] for row in rows[f]] for f in model.FRAMES}
    (x0, y0), _ = STILL["pair"]
    for y in range(y0 - 2, y0 + 48):
        hop["b"][y][x0:x0 + 64] = rows["b"][y + 2][x0:x0 + 64]
    lines.append(refused(convert.check_placements, "placement of pair", cast, cut, hop,
                         "the uncorrected hop (pair 2 px higher in b)"))
    return [f"converter controls: {len(lines)} bad frames refused: " + "; ".join(l[:70] for l in lines)]


def test_assets(stock, assets):
    good = assets.record()
    shared = sorted(model.protected_ids(stock))

    def build(edit):
        record = json.loads(json.dumps(good))
        edit(record)
        return HomerunAssets.parse(record)

    def chr_set(record, name, tile, pattern):
        data = bytearray(bytes.fromhex(record[name]))
        data[16 * tile:16 * tile + 16] = pattern
        record[name] = data.hex()
    first = next(iter(assets.planes))
    unused_quad = next(f"{k:08X}" for k in range(0x10000) if tuple(bytes.fromhex(f"{k:08X}")) not in
                       set(assets.planes.values()) and max(bytes.fromhex(f"{k:08X}")) < assets.tile_pairs)

    def extra_pair(record):
        record["tile_pairs"] += 1
        chr_set(record, "chr_a", record["tile_pairs"] - 1, b"\x55" * 16)
        chr_set(record, "chr_b", record["tile_pairs"] - 1, b"\xAA" * 16)
    cases = [
        (lambda r: r.update(chr_a=r["chr_a"][:-2]), "exactly 4096"),
        (lambda r: r.update(tile_pairs=257), "1-256"),
        (lambda r: chr_set(r, "chr_b", 250, b"\x01" * 16), "must stay blank"),
        (lambda r: [chr_set(r, n, 1, bytes.fromhex(r[n])[:16]) for n in ("chr_a", "chr_b")], "distinct"),
        (lambda r: r.update(palette="0f" + r["palette"][2:]), "one backdrop"),
        (lambda r: r["planes"].update({"FE": [unused_quad[i:i + 2] for i in range(0, 8, 2)]}), "exactly the defined"),
        (lambda r: r["planes"].update({f"{first:02X}": ["00", "00", "00", "FF"]}), "allocated tile ids"),
        (lambda r: r.update(renders={"b": r["renders"]["b"], "a": r["renders"]["a"]}), "a then b"),
        (extra_pair, "every allocated tile pair"),
    ]
    lines = [refused(build, reason, edit) for edit, reason in cases]
    record = json.loads(json.dumps(good))
    taken = f"{shared[1]:02X}"
    record["planes"][taken] = record["planes"].pop(f"{first:02X}")
    record["planes"] = dict(sorted(record["planes"].items()))
    record["metamap"] = bytes(shared[1] if b == first else b for b in bytes.fromhex(record["metamap"])).hex()
    lines.append(refused(stage.build_rom, "belong to the VICTORY or split-screen map", stock,
                         HomerunAssets.parse(record)))
    try:
        HomerunAssets.parse({**good, "extra": 1})
        raise Failure("an asset record with an unknown key was accepted")
    except AssetError as exc:
        lines.append(str(exc)[:60])
    return [f"asset boundary: {len(lines)} bad asset records refused, e.g. {lines[3][:60]}; {lines[-2][:70]}"]



def owned_spans(assets):
    spans = {"CHR $04": range(locate("chr", 0x4000), locate("chr", 0x5000)),
             "CHR $15": range(locate("chr", 0x15000), locate("chr", 0x16000)),
             "map $24": range(locate(1, 0x8DF0), locate(1, 0x8F20)),
             "record $0E": range(locate(15, 0xF8C0), locate(15, 0xF8D0))}
    planes = {locate(1, 0x8400 + 0x100 * q + k) for k in assets.planes for q in range(4)}
    return spans, planes


def test_stage(stock, rom, assets):
    check(stage.build_rom(stock, assets) == rom and sha256(rom) == TARGET_SHA256, "the build is not deterministic")
    manifest = stage.diff_manifest(stock, rom, assets)
    changed = {i for i, (a, b) in enumerate(zip(stock, rom)) if a != b}
    check((manifest["changed_bytes"], manifest["claimed_bytes"], len(manifest["regions"])) == (CHANGED, CLAIMED,
                                                                                               REGION_COUNT),
          f"manifest counts {manifest['changed_bytes']}/{manifest['claimed_bytes']}/{len(manifest['regions'])}")
    check({i for r in manifest["regions"] for i in r["changed_file_offsets"]} == changed, "the manifest is not exact")
    spans, planes = owned_spans(assets)
    check(changed <= set().union(*spans.values()) | planes, "a byte changed outside CHR $04/$15, map $24, the planes "
                                                           "and record $0E")
    check(len(rom) == len(stock) and rom[:16] == stock[:16], "size or header changed")
    for bank in range(16):
        start = locate(bank, 0xC000 if bank == 15 else 0x8000)
        if bank not in (1, 15):
            check(rom[start:start + 0x4000] == stock[start:start + 0x4000], f"PRG bank {bank} changed")
    check(read(rom, 15, 0xC000, 0x38C0) == read(stock, 15, 0xC000, 0x38C0)
          and read(rom, 15, 0xF8D0, 0x730) == read(stock, 15, 0xF8D0, 0x730), "executable fixed-bank bytes changed")
    for bank in range(32):
        if bank not in (0x04, 0x15):
            check(read(rom, "chr", bank * 0x1000, 0x1000) == read(stock, "chr", bank * 0x1000, 0x1000),
                  f"CHR ${bank:02X} changed")
    guards = [(label, bank, address + len(bytes.fromhex(text)) // 2) for label, bank, address, text in stage.DEPENDENCIES]
    guards += [(label, bank, address + size // 2) for label, bank, address, size, _ in stage.DIGESTS]
    guards += [(r.name, r.bank, (r.start + r.end) // 2) for r in stage.REGIONS]
    shared = sorted(model.protected_ids(stock))
    guards += [(f"protected metatile ${k:02X} plane {q}", 1, 0x8400 + 0x100 * q + k) for k in shared[:3] for q in (0, 3)]
    for label, bank, address in guards:
        corrupt = bytearray(stock)
        corrupt[locate(bank, address)] ^= 1
        with patch.object(stage, "BASE_SHA256", sha256(corrupt)):
            try:
                stage.build_rom(bytes(corrupt), assets)
            except ValueError:
                continue
        raise Failure(f"{label}: a one-bit drift at {bank}:${address:04X} was not caught")
    refusals = [refused(stage.build_rom, "size", stock[:-1], assets), refused(stage.build_rom, "size", stock + b"\0",
                                                                               assets),
                refused(stage.build_rom, "does not match pinned", patched(stock, [(15, 0xFFF8, b"\x01")]), assets)]
    changes = stage.change_manifest(stock, assets)
    first = changes[0]
    for bad in (changes + (first,), changes[1:], (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=first.addr + 1),) + changes[1:], (replace(first, bank=9),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=bytes(len(first.before))),) + changes[1:]):
        with patch.object(stage, "change_manifest", return_value=bad):
            try:
                stage.build_rom(stock, assets)
            except ValueError:
                continue
        raise Failure("a malformed change list was applied")
    outside = bytearray(rom)
    outside[locate(2, 0x9000)] ^= 1
    refusals.append(refused(stage.check_output, "outside the homerunart32 regions", stock, bytes(outside), assets))
    victory = bytearray(rom)
    victory[locate(1, 0x8400 + shared[5])] ^= 1
    refusals.append(refused(stage.check_output, "outside", stock, bytes(victory), assets))
    return [f"stage: {CHANGED} bytes change inside {CLAIMED} owned bytes in {REGION_COUNT} regions (CHR $04/$15, map "
            f"$24, {len(assets.planes)} metatile ids' planes, record $0E); no executable byte, other bank, CHR or "
            f"header changes; the manifest is exact; {len(guards)} one-bit input drifts, 7 malformed change lists and "
            f"{len(refusals)} bad inputs or outputs refused, e.g. {refusals[2][:50]}"]


def test_readers(stock, rom):
    for label, data in (("input", stock), ("candidate", rom)):
        failed = [c.name for c in readers.checks(data) if not c.ok]
        check(not failed, f"{label}: {failed}")
    count = len(readers.checks(stock))
    padding = next(a for a in range(0xB000, 0xBFF0) if read(stock, 5, a, 6) == b"\xFF" * 6)
    control = next((b, pc) for b, pc, *_ in readers.sites(stock, lambda op, mode, arg: op == "JSR" and mode == "abs"
                                                         and arg == readers.CONTROL_WRITER) if b != readers.STALE_BANK)
    record_call = next((b, pc) for b, pc, *_ in readers.sites(stock, lambda op, mode, arg: op == "JSR" and mode == "abs"
                                                              and arg == 0xC1A4)
                       if b != readers.STALE_BANK and (b, pc) != (15, 0xD75F) and read(stock, b, pc - 2, 1) == b"\xA9")
    mutations = {
        "an immediate store of scene $1C": ([(4, 0xB6EE, b"\x1C")], "no store writes scene $1B, $1C"),
        "a reviewed store's table holding $1C": ([(5, 0xA90D, b"\x1C")], "immediate or a reviewed value set"),
        "screen 5 in sequence 0": ([(5, 0xA959, b"\x05")], "screen 5 appears only in sequence 5"),
        "preset 6 requested at 5:$AC99": ([(5, 0xAC98, b"\x06")], "preset 6 only at 5:$AC78"),
        "CHR $15 in preset 2": ([(15, 0xFB4D + 12 + 1, b"\x15")], "CHR $15 only in preset 6"),
        "8 KB CHR mode": ([(control[0], control[1] - 1, b"\x0E")], "MMC1 control"),
        "the VICTORY call drawing map $24": ([(5, 0xACCA, b"\x24")], "drawn only with maps"),
        "SPEED's wrapper no longer restores $17": ([(15, 0xF0B6, b"\xEA\xEA\xEA")], "SPEED's play wrapper"),
        "record $0E loaded elsewhere": ([(record_call[0], record_call[1] - 1, b"\x0E")],
                                        "loaded by immediate only at $D75D"),
        "a new scene step in bank 5": ([(5, padding, b"\xEE\x7B\x04")], "the scene steps are"),
        "a new jump into the play exit": ([(5, padding, b"\x4C\x0B\xD8")], "SPEED's play wrapper"),
        "the camera table selecting record $0E": ([(2, 0x97C0, b"\xE4")], "camera table"),
        "scene $1A no longer clearing $10": ([(5, 0xA8B0, b"\xEA\xEA")], "bank 5 $A8A6-$A958"),
    }
    lines = []
    for label, (edits, reason) in mutations.items():
        failed = [c.name for c in readers.checks(patched(stock, [(b, a, v) for b, a, v in edits])) if not c.ok]
        check(any(reason in name for name in failed), f"{label}: {reason!r} did not fail ({failed})")
        lines.append(label)
    corrupt = patched(stock, mutations["screen 5 in sequence 0"][0])
    with patch.object(stage, "BASE_SHA256", sha256(corrupt)), patch.object(stage, "DIGESTS", ()):
        reason = refused(stage.build_rom, "shared-reader argument fails", corrupt, stage_assets())
    return [f"readers: all {count} reader checks pass on the input and the candidate; {len(mutations)} mutated inputs "
            f"each fail their check ({'; '.join(lines[:4])}; ...); the builder refuses one: {reason[:80]}"]


_ASSETS = {}


def stage_assets():
    return _ASSETS["assets"]



def decode_call(rom, set_arg, map_arg):
    """What $C5C4 draws for one call, read here from the $FAF0/$FB11 tables: 960 tile ids and 64 attributes."""
    planes_lo, planes_hi, planes_bank = read(rom, 15, 0xFAF0 + set_arg, 3)
    map_lo, map_hi, map_bank = read(rom, 15, 0xFB11 + map_arg, 3)
    planes_at, map_at = planes_lo | planes_hi << 8, map_lo | map_hi << 8
    ids = read(rom, map_bank, map_at, 240)
    screen = bytearray(960)
    for i, k in enumerate(ids):
        for q in range(4):
            screen[32 * (2 * (i // 16) + q // 2) + 2 * (i % 16) + q % 2] = read(rom, planes_bank, planes_at + 0x100 * q + k,
                                                                               1)[0]
    return bytes(screen) + read(rom, map_bank, map_at + 240, 64)


def frame_rows(rom, frame):
    """RGB rows of a frame from ROM bytes: map $24 through set $15, record $0E, CHR $04 or $15."""
    screen = decode_call(rom, 0x15, 0x24)
    record = read(rom, 15, 0xF8C0, 16)
    bank = read(rom, "chr", (0x04 if frame == "a" else 0x15) * 0x1000, 0x1000)
    rows = []
    for y in range(240):
        row = []
        for x in range(256):
            tile = screen[32 * (y // 8) + x // 8]
            v = (bank[16 * tile + y % 8] >> (7 - x % 8)) & 1 | ((bank[16 * tile + 8 + y % 8] >> (7 - x % 8)) & 1) << 1
            attr = screen[960 + 8 * (y // 32) + x // 32] >> (((y // 16) & 1) * 4 + ((x // 16) & 1) * 2) & 3
            row.append(menu.NES_RGB[record[4 * attr + v] if v else record[0]])
        rows.append(row)
    return rows


def test_static(stock, rom, assets):
    calls = []
    for bank in range(16):
        if bank == readers.STALE_BANK:
            continue
        data = read(stock, bank, 0xC000 if bank == 15 else 0x8000, 0x4000)
        calls += [(bank, i) for i in range(len(data) - 6) if data[i:i + 3] == b"\x20\xC4\xC5"]
    differ, decoded = [], 0
    for bank, i in calls:
        args = read(stock, bank, (0xC000 if bank == 15 else 0x8000) + i + 3, 2)
        try:
            before = decode_call(stock, *args)
        except ValueError:
            continue
        decoded += 1
        if before != decode_call(rom, *args):
            differ.append((bank, (0xC000 if bank == 15 else 0x8000) + i))
    check(differ == [(15, 0xD767)], f"screens drawn differently: {differ}")
    check(decode_call(rom, 0x15, 0x24) == assets.nametable() + assets.attributes, "map $24 decodes differently from "
                                                                                  "the assets")
    check(read(rom, 15, 0xF8C0, 16) == Layout.load().record(), "record $0E differs from layout.json")
    frames = {f: frame_rows(rom, f) for f in model.FRAMES}
    for f in model.FRAMES:
        check(rows_digest(frames[f]) == RENDER_PIXELS[f], f"frame {f} decoded from the ROM differs from the selected "
                                                          "frame")
        check(rows_digest(frame_rows(stock, f)) != RENDER_PIXELS[f], "the input already shows the selected frame")
    _, _, cast, rules = suite_sources()
    cut = convert.cut(stock, rules)
    still = {}
    for pid, ((x0, y0), count) in STILL.items():
        p = next(q for q in cast.placements if q.part == pid)
        check(p.still and p.at == (x0, y0), f"{pid} is not one still placement at {(x0, y0)}")
        shown, (dx, dy) = accepted.visible_rect(p, cut[pid])
        pixels = [(x, y) for y in range(shown[1], shown[1] + shown[3]) for x in range(shown[0], shown[0] + shown[2])
                  if cut[pid].pixels[y - dy][x - dx] is not None]
        same = [p for p in pixels if frames["a"][p[1]][p[0]] == frames["b"][p[1]][p[0]]
                == menu.NES_RGB[cut[pid].pixels[p[1] - dy][p[0] - dx]]]
        check(len(pixels) == len(same) == count, f"{pid}: {len(same)} of {len(pixels)} pixels still, expected {count}")
        still[pid] = count
    moving = {name: sum(frames["a"][y][x] != frames["b"][y][x] for y in range(y0, y0 + h) for x in range(x0, x0 + w))
              for name, (x0, y0, w, h) in MOVING.items()}
    check(all(moving.values()), f"a moving area stands still: {moving}")
    (x0, y0), _ = STILL["pair"]
    hop = [row[:] for row in frames["b"]]
    for y in range(y0 - 2, y0 + 48):
        hop[y][x0:x0 + 64] = frames["b"][y + 2][x0:x0 + 64]
    check(any(hop[y][x] != frames["a"][y][x] for y in range(y0, y0 + 50) for x in range(x0, x0 + 64)),
          "negative control: a 2-pixel hop of the pair was not visible")
    return [f"static: {decoded} live $C5C4 screens decode identically but HR map $24; both frames decoded from the "
            f"ROM's own tables equal the selected frames pixel for pixel (pinned digests); pair {still['pair']} and "
            f"batter {still['batter']} part pixels identical in both frames; " +
            ", ".join(f"{n} {c} px move" for n, c in moving.items())]



def judge_contracts(stock_results, cand_results):
    check(stock_results == cand_results, "a direct-call contract differs from the input")
    counts = {}
    for key, value in cand_results.items():
        kind = key[0]
        counts[kind] = counts.get(kind, 0) + 1
        if kind in ("scoring", "game over"):
            oracle, observed, extra, _ = value
            check(oracle == observed, f"{key}: observed {observed}, the rules give {oracle}")
            check(extra["slots_cleared"] and extra["state"] == 1 and extra["series"],
                  f"{key}: runners not cleared, no state 1 or the series changed: {extra}")
            check(extra["queued"] == sorted([machine.HOME_RUN_SONG] + [machine.RUN_SFX] * oracle["runs"]),
                  f"{key}: queued {extra['queued']}")
            check(extra["over_marks"] == ((True, 0x82) if oracle["over"] else (False, 0)), f"{key}: game-over marks")
        elif kind == "tail":
            side = key[2]
            result = value[0]
            check(result["hr"][side] == 1 and result["hr"][side ^ 1] == 0 and result["hits"][side] == 1
                  and result["batter_hit"] == 1 and result["04AC"] == 3 and result["state"] == 2 and result["series"],
                  f"{key}: {result}")
        elif kind == "suppressed":
            result = value[0]
            check(result["score"] == [7, 8] and result["state"] == 0 and not result["queued"]
                  and result["slots"] == bytes(4), f"{key}: a suppressed home run changed state: {result}")
        elif kind == "exit":
            _, _, _, over, pinch, order = key
            result = value[0]
            want = order if over or pinch else (order + 2 if order + 2 < 0x12 else 0)
            check(result["scene"] == (9 if over else 2) and result["order"] == want and result["series"],
                  f"{key}: {result}, want scene {9 if over else 2} order {want}")
        elif kind == "hud":
            check(value == (list(range(59, -1, -1)) if key[1] else [0]), f"{key}: {value}")
    return counts


CONTRACT_MUTANTS = {
    "pitcher debit removed ($E40A INC -> LDA)": [(15, 0xE40A, b"\xBD")],
    "score credit removed ($E418 INC -> LDA)": [(15, 0xE418, b"\xBD")],
    "runners not cleared ($B76C LDA #$FF -> #$00)": [(6, 0xB76D, b"\x00")],
    "HR stat not counted ($D9E2 INC -> LDA)": [(15, 0xD9E2, b"\xBD")],
    "touched-play guard removed ($B742 BNE -> NOP NOP)": [(6, 0xB742, b"\xEA\xEA")],
    "HUD timer frozen ($E6DB DEC -> LDA)": [(15, 0xE6DB, b"\xAD")],
    "next batter wraps at $14 ($D852 CMP #$12 -> #$14)": [(15, 0xD852, b"\x14")],
}


def test_contracts(results, mutant_results):
    counts = judge_contracts(results["stock"], results["candidate"])
    lines = []
    for label in CONTRACT_MUTANTS:
        try:
            judge_contracts(mutant_results[label], mutant_results[label])
        except Failure as exc:
            lines.append(f"{label}: {str(exc)[:60]}")
            continue
        raise Failure(f"negative control passed: {label}")
    return [f"contracts: {', '.join(f'{n} {k}' for k, n in counts.items())} direct calls on the candidate equal the "
            "input and the independent oracles (runs = 1 + occupied bases, per-run pitcher debits, cleared runners, "
            "song and run SFX, game over at 100/ten-run/walk-off, HR/HIT/batter credit, suppressions, scene 2 vs 9, "
            "next batter +2 wrapping at $12, both HUD-expiry forms, series bytes intact)"] + [
        f"  negative control {line}" for line in lines]



def test_fixture_cache(stock, cache, names):
    """The cache loads only states whose provenance and digest match: a flipped pickle bit, a stale harness
    fingerprint and another input each keep states from loading."""
    with tempfile.TemporaryDirectory(prefix="homerunart32-cache-") as temporary:
        copy = Path(temporary) / "cache"
        shutil.copytree(cache, copy)
        good = played.load_cache(stock, copy)
        check(set(names) <= set(good), f"the cache misses {sorted(set(names) - set(good))}")
        record = json.loads((copy / "provenance.json").read_text())
        victim = copy / record["states"][names[0]]["file"]
        data = bytearray(victim.read_bytes())
        data[len(data) // 2] ^= 1
        victim.write_bytes(bytes(data))
        tampered = played.load_cache(stock, copy)
        check(names[0] not in tampered and len(tampered) == len(good) - 1, "a tampered pickle loaded")
        record["harness"][played.HARNESS[0]] = "0" * 64
        (copy / "provenance.json").write_text(json.dumps(record))
        check(played.load_cache(stock, copy) == {}, "a cache with a stale harness fingerprint loaded")
        check(played.load_cache(patched(stock, [(2, 0x9000, b"\x00")]), cache) == {}, "another input loaded the cache")
    return [f"fixture cache: {len(good)} states load with matching provenance; a flipped pickle bit, a stale harness "
            "fingerprint and another input each refuse states"]


def shown(frames):
    return [f for f in frames if f["scene"] == 5 and f["state"] == 3 and f["shown"]]


def judge_replay(name, stock, cand, oracle):
    """Problems a candidate replay shows against the stock replay from the same state and against the oracle."""
    problems = []
    if stock["marks"] != cand["marks"]:
        problems.append(f"milestones {cand['marks']} vs stock {stock['marks']}")
    diff = [a for a in range(0x800) if stock["exit_ram"][a] != cand["exit_ram"][a] and a not in EXIT_SCRATCH]
    if diff:
        problems.append(f"RAM at the exit differs outside the cutscene scratch at {[hex(a) for a in diff[:6]]}")
    if stock["exit_wram"] != cand["exit_wram"] or stock["end_wram"] != cand["end_wram"]:
        problems.append("WRAM differs")
    end = [a for a in range(0x800) if stock["end_ram"][a] != cand["end_ram"][a] and a not in machine.LOADER_BUFFERS]
    if end:
        problems.append(f"RAM 240 frames after the exit differs at {[hex(a) for a in end[:6]]}")
    if stock["stale"] or cand["stale"]:
        problems.append(f"loader buffers read before rewritten: stock {len(stock['stale'])}, candidate "
                        f"{len(cand['stale'])}")
    for key in ("apu", "queue", "late", "partial", "left"):
        if stock[key] != cand[key]:
            problems.append(f"{key} differs ({len(cand[key]) if isinstance(cand[key], list) else cand[key]} vs stock "
                            f"{len(stock[key]) if isinstance(stock[key], list) else stock[key]})")
    if oracle is not None:
        before, after = cand["before"], cand["exit_ram"]
        side = oracle["side"]
        observed = {"runs": after[machine.RUNS + side] - before[machine.RUNS + side],
                    "score": [after[machine.RUNS], after[machine.RUNS + 1]], "over": bool(after[machine.OVER])}
        if observed != {k: oracle[k] for k in observed}:
            problems.append(f"scored {observed}, the rules give {oracle}")
        if not (after[machine.HR_STAT + side] - before[machine.HR_STAT + side] == 1
                and after[machine.HR_STAT + (side ^ 1)] == before[machine.HR_STAT + (side ^ 1)]
                and after[machine.HITS + side] - before[machine.HITS + side] == 1):
            problems.append("HR or HIT stat not credited to the batting side alone")
        if not all(machine.DEBIT <= a < machine.DEBIT + machine.DEBITS for a in oracle["debits"]):
            problems.append(f"the plant charges runs outside the pitcher table: {oracle['debits']}")
        debits = {a: after[a] - before[a] for a in oracle["debits"]}
        if debits != oracle["debits"]:
            problems.append(f"pitcher debits {debits}, the rules give {oracle['debits']}")
        path = "scene9" if oracle["over"] else "field-init"
        if path not in cand["marks"]:
            problems.append(f"no {path} exit")
    return problems


def judge_frames(stock, cand, assets):
    """Problems in the candidate's cutscene frames: CHR1 flips $04/$15 on stock's 8-frame clock, the PPU holds the
    assets and record $0E, sprite colors equal stock's, sprites stay hidden, and stock's frame count."""
    problems, frames, base = [], shown(cand["frames"]), shown(stock["frames"])
    banks = [f["chr1"] for f in frames]
    if set(banks) != set(model.FRAME_CHR.values()):
        problems.append(f"state 3 shows CHR1 {sorted(set(banks))}, not $04 and $15")
    runs, current = [], None
    for bank in banks:
        if current and current[0] == bank:
            current[1] += 1
        else:
            current = [bank, 1]
            runs.append(current)
    if not runs[1:-1] or any(r[1] != 8 for r in runs[1:-1]):
        problems.append(f"inner flip runs {sorted({r[1] for r in runs[1:-1]})}, not 8 frames")
    screen = sha256(assets.nametable() + assets.attributes)
    if any(f["screen"] != screen for f in frames):
        problems.append("VRAM $2000-$23FF differs from the assets")
    if any(f["background"] != assets.palette.hex() for f in frames):
        problems.append("background palette RAM differs from record $0E")
    if [f["sprites"] for f in frames] != [f["sprites"] for f in base]:
        problems.append("sprite colors differ from stock's")
    if any(f["ctrl"] != 0x10 or not f["oam_hidden"] for f in frames):
        problems.append("PPUCTRL or hidden sprites differ")
    if len(frames) != len(base):
        problems.append(f"{len(frames)} cutscene frames shown, stock {len(base)}")
    return problems


def judge_pictures(rom, stock_rom, cand, stock, renders):
    problems = []
    for bank, frame in ((0x04, "a"), (0x15, "b")):
        if bank not in cand["pictures"]:
            problems.append(f"no CHR1 ${bank:02X} frame shown")
            continue
        if rows_digest(machine.compose(rom, (bank, cand["pictures"][bank]))) != RENDER_PIXELS[frame]:
            problems.append(f"the CPU frame with CHR1 ${bank:02X} differs from the selected frame {frame}")
        if bank in stock["pictures"] and rows_digest(machine.compose(stock_rom, (bank, stock["pictures"][bank]))) == \
                RENDER_PIXELS[frame]:
            problems.append("the input shows the selected frame")
    return problems


def on_base(*slots):
    """Runners planted on base: active, each charged to the starting pitcher (0), as in the played states."""
    return {**{machine.ACTIVE + x: 0 for x in slots}, **{machine.PITCHER + x: 0 for x in slots}}


def planted_cases(states, quick):
    s1, s2 = states["solo 29-11 top 1st"][0], states["two-run 11-29 bottom 1st"][0]
    third = machine.ACTIVE + 12
    cases = {
        "PLANTED three-run (runners on first and second)": (s2, {"ram": {**on_base(10, 11), third: 0xFF}}, 3),
        "PLANTED grand slam, bottom 1st": (s2, {"ram": on_base(10, 11, 12)}, 4),
        "PLANTED grand slam, top 1st": (s1, {"ram": on_base(10, 11, 12)}, 4),
        "PLANTED walk-off, bottom 6th (3-2)": (s2, {"ram": {machine.HALVES: 0x0B, machine.RUNS: 3,
                                                          machine.RUNS + 1: 2}}, 2),
        "PLANTED ten-run rule, bottom 2nd (0-8)": (s2, {"ram": {machine.HALVES: 3, machine.RUNS: 0,
                                                              machine.RUNS + 1: 8}}, 2),
    }
    if not quick:
        cases |= {
            "PLANTED walk-off grand slam, bottom 8th (5-2)": (s2, {"ram": {machine.HALVES: 0x0F, machine.RUNS: 5,
                                                                         machine.RUNS + 1: 2, **on_base(10, 11, 12)}},
                                                               4),
            "PLANTED live v2 championship": (s1, {"series": {"team": 9, "played": 3, "results": 5,
                                                             "cpu_mask": 0xFFFFFDFF, "draw_seed": 0x1234}}, 1),
            "PLANTED buttons mashed on both pads": (s1, {"mash": MASH}, 1),
        }
    cases["PLANTED attract mode, START held on both pads"] = (s1, {"ram": {0xA7: 1}, "mash": [0x10]}, None)
    return cases


def natural_cases(states, quick):
    names = played.QUICK_FIXTURES[:2] if quick else [n for n, f in played.FIXTURES.items() if f[3] == "home run"]
    return {f"played {n}": (states[n][0], {}, None) for n in names}


REPLAY_MUTANTS = {
    "HR stat not counted": ([(15, 0xD9E2, b"\x2C")], "HR or HIT stat"),
    "cutscene cut short ($D77E BMI -> BPL)": ([(15, 0xD77E, b"\x10")], "milestones"),
    "frame b never shown ($D794 = $04)": ([(15, 0xD794, b"\x04")], "not $04 and $15"),
    "record $0E drifted": ([(15, 0xF8C2, b"\x30")], "record $0E"),
    "a tile of map $24 drifted": ([(1, 0x8DF0 + 100, b"\x01")], "VRAM"),
}



def sweep_teams(state, rom, teams):
    return [machine.sweep(state, rom, t) for t in teams]


JOBS = {"natural": machine.natural, "replay": machine.replay, "sweep": sweep_teams, "touched": machine.touched_play,
        "phase": machine.phase_run, "contracts": machine.contracts, "screens": earlier.screens}


def job(name, *args):
    """One independent run, by name; module level so worker processes can import it."""
    return JOBS[name](*args)


class Jobs:
    """Independent runs in worker processes; each result or its exception, by key."""

    def __init__(self, workers):
        self.pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) \
            if workers > 1 else None
        self.pending = {}

    def submit(self, key, *spec):
        self.pending[key] = self.pool.submit(job, *spec) if self.pool else spec

    def result(self, key):
        item = self.pending[key]
        return item.result() if self.pool else job(*item)

    def close(self):
        if self.pool:
            self.pool.shutdown(cancel_futures=True)


def submit_runtime(jobs, stock, rom, states, quick):
    keys = {"natural": ("natural", "stock"), "natural-c": ("natural", "candidate")}
    jobs.submit(keys["natural"], "natural", stock)
    jobs.submit(keys["natural-c"], "natural", rom)
    cases = natural_cases(states, quick) | planted_cases(states, quick)
    for name, (state, plant_spec, _) in cases.items():
        jobs.submit(("replay", name, "stock"), "replay", state, stock, plant_spec)
        jobs.submit(("replay", name, "candidate"), "replay", state, rom, plant_spec)
    two_run = states["two-run 11-29 bottom 1st"][0]
    for label, (edits, _) in REPLAY_MUTANTS.items():
        jobs.submit(("mutant", label), "replay", two_run, rom, {}, tuple(
            (locate(b, a) + i, v) for b, a, values in edits for i, v in enumerate(values)))
    teams = (0, 15, 16, 31) if quick else tuple(range(32))
    sweep_state = states["state 2 11-29 bottom 1st"][0]
    for k in range(0, len(teams), 4):
        jobs.submit(("sweep", k), "sweep", sweep_state, rom, teams[k:k + 4])
    if not quick:
        for name in (n for n, f in played.FIXTURES.items() if f[3] == "touched play"):
            for label, data in (("stock", stock), ("candidate", rom)):
                jobs.submit(("touched", name, label), "touched", states[name][0], data)
    leads = LEADS[::3] if quick else LEADS
    solo = states["solo 29-11 top 1st"][0]
    slam = {"ram": on_base(10, 11, 12)}
    for lead in leads:
        for plant_name, plant_spec in (("natural", {}), ("grand slam", slam)):
            for label, data in (("stock", stock), ("candidate", rom)):
                jobs.submit(("phase", lead, plant_name, label), "phase", solo, data, lead, plant_spec)
    for label, data in (("stock", stock), ("candidate", rom)):
        jobs.submit(("contracts", label), "contracts", data, False)
        jobs.submit(("screens", label), "screens", data)
    for label, edits in CONTRACT_MUTANTS.items():
        jobs.submit(("contract-mutant", label), "contracts", patched(rom, edits), True)
    return cases, teams, leads


def test_natural(jobs, stock, rom, renders):
    a, b = jobs.result(("natural", "stock")), jobs.result(("natural", "candidate"))
    check(a["steps"] == b["steps"] and a["marks"] == b["marks"], "the natural game diverges from the input")
    check({"state2", "exit", "field-init"} <= set(b["marks"]), f"no home run and return in the natural game: {b['marks']}")
    check(a["ram"] == b["ram"] and a["wram"] == b["wram"] and a["apu"] == b["apu"],
          "RAM, WRAM or APU writes differ at the end of the natural game")
    problems = judge_pictures(rom, stock, b, a, renders)
    check(not problems, "; ".join(problems))
    m = b["marks"]
    return [f"natural WATCH 29-11 from RESET, controller input only: {len(b['steps'])} samples of scene, state, half, "
            f"score, CHR banks, song, $25, HR stats and game-over equal the input; cutscene from state 2 at frame "
            f"{m['state2']} to the exit at {m['exit']}, field back at {m['field-init']}; RAM, WRAM and {b['apu'][0]} APU writes "
            "equal 480 frames later; its CPU frames in both CHR phases equal the selected frames (no saved states)"]


def test_replays(jobs, stock, rom, assets, cases, renders):
    lines, judged = [], 0
    for name, (_, _, runs) in cases.items():
        a, b = jobs.result(("replay", name, "stock")), jobs.result(("replay", name, "candidate"))
        oracle = None if "attract" in name else machine.expected_home_run(b["before"])
        if runs is not None:
            check(oracle["runs"] == runs, f"{name}: the plant gives {oracle['runs']} runs, not {runs}")
        problems = judge_replay(name, a, b, oracle)
        if "state3" in b["marks"]:
            problems += judge_frames(a, b, assets) + judge_pictures(rom, stock, b, a, renders)
        check(not problems, f"{name}: {'; '.join(problems)}")
        judged += 1
        summary = (f"{oracle['runs']} run(s) for side {oracle['side']}, {'game over' if oracle['over'] else 'play on'}"
                   if oracle else f"route to scene ${b['left']:02X}")
        lines.append(f"  {name}: {summary}; {len(shown(b['frames']))} frames; exit {b['marks'].get('exit')}")
    base = jobs.result(("replay", "played two-run 11-29 bottom 1st", "stock"))
    for label, (_, reason) in REPLAY_MUTANTS.items():
        mutant = jobs.result(("mutant", label))
        problems = judge_replay(label, base, mutant, machine.expected_home_run(mutant["before"]))
        if "state3" in mutant["marks"]:
            problems += judge_frames(base, mutant, assets)
        check(any(reason in p for p in problems), f"negative control {label} passed: {problems}")
        lines.append(f"  negative control {label}: {next(p for p in problems if reason in p)[:70]}")
    return [f"replays: {judged} home runs from played states on stock and candidate: milestones to the cycle, exit "
            "RAM outside the cutscene scratch, RAM 240 frames later, WRAM, APU writes, sound queue, late PPU writes "
            "and mapper sequences equal; runs, debits, stats and game over match the rules; CHR1 flips $04/$15 "
            "every 8 frames on the assets and record $0E with stock's sprite colors"] + lines


def test_sweeps(jobs, stock, rom, assets, teams, leads, quick):
    lines = []
    exits, sequences = set(), set()
    for k in range(0, len(teams), 4):
        for team, done, frames in jobs.result(("sweep", k)):
            exits.add(done)
            sequences.add(tuple(frames))
    want = {(b, sha256(assets.nametable() + assets.attributes), assets.palette.hex()) for b in model.FRAME_CHR.values()}
    check(len(exits) == 1 and len(sequences) == 1 and set(next(iter(sequences))) == want,
          f"team sweep: {len(exits)} exits, {len(sequences)} sequences")
    lines.append(f"teams {', '.join(map(str, teams)) if quick else '0-31'} planted at the state-2 entry: one exit frame "
                 f"and one frame sequence ({len(next(iter(sequences)))} frames of the assets)")
    if not quick:
        for name in (n for n, f in played.FIXTURES.items() if f[3] == "touched play"):
            a, b = jobs.result(("touched", name, "stock")), jobs.result(("touched", name, "candidate"))
            check(not a["state2"] and not b["state2"] and a["ram"] == b["ram"] and a["wram"] == b["wram"]
                  and a["apu"] == b["apu"] and b["ram"][machine.HR_STAT:machine.HR_STAT + 2]
                  == b["before"][machine.HR_STAT:machine.HR_STAT + 2], f"{name}: a touched ball changed the outcome")
            lines.append(f"{name}: no cutscene, no HR stat; RAM, WRAM and {len(b['apu'])} APU writes equal over 600 "
                         "frames")
    for lead in leads:
        for plant_name in ("natural", "grand slam"):
            a, b = (jobs.result(("phase", lead, plant_name, label)) for label in ("stock", "candidate"))
            check(a == b, f"vblank phase +{lead} {plant_name}: differs from the input in "
                          f"{[k for k in a if a[k] != b[k]]}")
    lines.append(f"vblank phases +{', +'.join(map(str, leads))} cycles, natural and grand slam: milestones, per-frame "
                 "scene/state/$BA/song/CHR1/mask, APU, late writes, mapper sequences, RAM $0400-$07FF and WRAM equal")
    a, b = jobs.result(("screens", "stock")), jobs.result(("screens", "candidate"))
    check(a == b, f"earlier screens differ: {[k for k in a if a[k] != b.get(k)]}")
    lines.append(f"earlier screens: {', '.join(k for k in a if k != 'series intact')} equal the input in VRAM, palette, "
                 "OAM, CHR and PPU state (analysisart32_machine.screens); series intact")
    return ["runtime sweeps:"] + [f"  {line}" for line in lines]



@contextmanager
def checkout(stock_path):
    """A scratch copy of tools, art and data with the input in its build/, a docs stub and earlier evidence."""
    with tempfile.TemporaryDirectory(prefix="homerunart32-test-") as temporary:
        scratch = Path(temporary).resolve()
        repo = scratch / "repo"
        for name in ("tools", "art", "data"):
            shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        (repo / "docs").mkdir()
        (repo / "docs/notes.md").write_text("docs stay intact\n")
        for evidence in ("analysisart32/evidence.json", "homerunart32-design/grounding.md"):
            (repo / "build" / evidence).parent.mkdir(parents=True, exist_ok=True)
            (repo / "build" / evidence).write_text("earlier evidence\n")
        shutil.copyfile(stock_path, repo / "build/analysisart32.nes")
        elsewhere = scratch / "elsewhere"
        elsewhere.mkdir()
        yield repo, elsewhere


def snapshot(*roots):
    seen = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if "__pycache__" in path.parts:
                continue
            st = path.lstat()
            if path.is_symlink():
                seen[path] = ("link", os.readlink(path), st.st_ino, st.st_mtime_ns)
            elif path.is_file():
                seen[path] = ("file", sha256(path.read_bytes()), st.st_ino, st.st_mode, st.st_mtime_ns)
            else:
                seen[path] = ("node", st.st_mode)
    return seen


def run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


def ok(result):
    check(result.returncode == 0, f"exit {result.returncode}: {result.stderr[-600:]}{result.stdout[-300:]}")
    return result


def failed(result, reason, status=2):
    text = result.stderr + result.stdout
    check(result.returncode == status and reason in text,
          f"expected exit {status} mentioning {reason!r}; got {result.returncode}: {text[-400:]}")
    line = next(line for line in reversed(text.strip().splitlines()) if reason in line)
    for scratch in sorted({tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())}, key=len, reverse=True):
        line = line.replace(scratch, "<tmp>")
    return line.split(": ", 1)[-1][:100]


def install(repo, outputs):
    for relative, data in outputs.items():
        target = repo / "build/homerunart32" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_builder_cli(repo, elsewhere, stock, rom, assets):
    tools, rom_path, out = repo / "tools", repo / "build/analysisart32.nes", repo / "build/homerunart32"
    sources = [tools / n for n in ("build_homerunart32.py", "homerunart32_convert.py", "homerunart32_assets.py",
                                   "homerunart32_readers.py", "homerunart32_machine.py", "homerunart32_fixtures.py",
                                   "test_homerunart32.py", "build_analysisart32.py", "verify.sh")]
    sources += [repo / "art/homerunart32/cast.json", repo / "art/homerunart32/homerun32.px.js",
                repo / "data/homerunart32/digests.json", repo / "data/analysisart32/digests.json",
                repo / "docs/notes.md", out / stage.ASSET_JSON, out / "parts/cheer-b.png",
                repo / "build/analysisart32/evidence.json", repo / "build/homerunart32-design/grounding.md"]
    count = check_output_guards(tools / "build_homerunart32.py", rom_path, rom, stage.diff_manifest(stock, rom, assets),
                                sources)
    cli = [sys.executable, "-B", str(tools / "build_homerunart32.py"), str(rom_path)]
    canonical = repo / "build/homerunart32.nes"
    result = ok(run(cli + ["-o", str(canonical)], elsewhere))
    check(canonical.read_bytes() == rom and TARGET_SHA256 in result.stdout, "canonical build")
    for temp_root in dict.fromkeys([tempfile.gettempdir()] + (["/tmp"] if sys.platform == "darwin" else [])):
        with tempfile.TemporaryDirectory(dir=temp_root, prefix="homerunart32-build-") as temporary:
            destination = Path(temporary) / "candidate.nes"
            ok(run(cli + ["-o", str(destination)], elsewhere))
            check(destination.read_bytes() == rom, f"natural temp build failed: {destination}")
    linked = elsewhere / "linked-art"
    linked.symlink_to(repo / "art/homerunart32")
    before = snapshot(repo, elsewhere)
    lines = [failed(run(cli + ["-o", str(linked / "new.nes")], elsewhere), "symbolic link ancestor")]
    check(snapshot(repo, elsewhere) == before, "the builder followed an ancestor link into art")
    copied = elsewhere / "assets"
    shutil.copytree(out, copied)
    record = json.loads((copied / stage.ASSET_JSON).read_text())
    record["palette"] = "0c" + record["palette"][2:4] + "0f" + record["palette"][6:]
    (copied / stage.ASSET_JSON).write_text(json.dumps(record))
    never = elsewhere / "never.nes"
    before = snapshot(repo, elsewhere)
    lines.append(failed(run(cli + ["-o", str(never), "--assets", str(copied)], elsewhere), "digests.json"))
    for place in (out / "inside.nes", repo / "build/analysisart32/x.nes", repo / "build/homerunart32-design/x.nes",
                  repo / "build/homerunart32-fixtures/x.nes", repo / "tools/x.nes"):
        lines.append(failed(run(cli + ["-o", str(place)], elsewhere), "output aliases protected"))
    lines.append(failed(run(cli + ["-o", str(never), "--assets", str(elsewhere / "missing")], elsewhere), "No such"))
    check(not never.exists() and snapshot(repo, elsewhere) == before, "a refused build wrote a file")
    registry = repo / "data/homerunart32/digests.json"
    original = registry.read_bytes()
    edited = json.loads(original)
    edited["rom"] = "0" * 64
    registry.write_text(json.dumps(edited))
    lines.append(failed(run(cli + ["-o", str(never)], elsewhere), "differs from data/homerunart32/digests.json"))
    registry.write_bytes(original)
    check(not never.exists(), "a build against a wrong registry wrote a file")
    canonical.unlink()
    return [f"builder CLI (scratch checkout): the same ROM and manifest from another directory; {count} protected "
            "targets refused (input, renamed copy, tools, verify.sh, art, data, docs, both registries, the asset file, a "
            "part PNG, earlier evidence, symbolic and hard links); natural /tmp and /var temp builds; refused with "
            f"nothing written: {'; '.join(l[:60] for l in lines[:4])}; ..."]


def test_convert_cli(repo, elsewhere, pxl):
    tools, rom_path = repo / "tools", repo / "build/analysisart32.nes"
    cli = [sys.executable, "-B", str(tools / "homerunart32_convert.py"), "--rom", str(rom_path), "--pxl", str(pxl)]
    out, registry_path = repo / "build/homerunart32", repo / "data/homerunart32/digests.json"
    registry = json.loads(registry_path.read_text())
    before = snapshot(repo, elsewhere, pxl)
    check("nothing written" in ok(run(cli + ["--check"], elsewhere)).stdout, "--check output")
    check(snapshot(repo, elsewhere, pxl) == before and not out.exists(), "--check wrote a file")
    ok(run(cli, elsewhere))
    found = {p.relative_to(out).as_posix(): sha256(p.read_bytes()) for p in out.rglob("*") if p.is_file()}
    check(found == registry["outputs"], "regeneration from another directory differs from the registry")
    installed = snapshot(repo)
    ok(run(cli, elsewhere))
    check(snapshot(repo) == installed, "a second run rewrote matching outputs")
    lines = []
    stray = out / "stray.txt"
    stray.write_text("not ours\n")
    lines.append(failed(run(cli, elsewhere), "holds files this run does not write"))
    stray.unlink()
    part = out / "parts/cheer-b.png"
    linked = elsewhere / "linked-part.png"
    os.link(part, linked)
    lines.append(failed(run(cli, elsewhere), "is a link or not a regular file"))
    linked.unlink()
    for place in (repo / "art/homerunart32/out", repo / "data/homerunart32", repo / "docs/out", rom_path,
                  repo / "build/analysisart32", pxl / "out"):
        before = snapshot(repo, elsewhere)
        lines.append(failed(run(cli + ["-o", str(place)], elsewhere), "output aliases protected"))
        check(snapshot(repo, elsewhere) == before, f"a refused run wrote something ({place})")
    layout = repo / "art/homerunart32/homerun32.px.js"
    original = layout.read_bytes()
    layout.write_bytes(original.replace(b"Exact NES colors on the navy", b"Exact NES colours on the navy"))
    check(layout.read_bytes() != original, "the comment edit did not apply")
    before = snapshot(repo, elsewhere)
    lines.append(failed(run(cli + ["--check"], elsewhere), "rerun with --record"))
    lines.append(failed(run(cli, elsewhere), "rerun with --record"))
    check(snapshot(repo, elsewhere) == before, "an unrecorded source change wrote outputs")
    ok(run(cli + ["--record"], elsewhere))
    recorded = json.loads(registry_path.read_text())
    check(recorded["rom"] == registry["rom"] and recorded["outputs"] == {**registry["outputs"],
                                                                         "provenance.json": recorded["outputs"][
                                                                             "provenance.json"]}
          and recorded["sources"]["art/homerunart32/homerun32.px.js"]
          != registry["sources"]["art/homerunart32/homerun32.px.js"],
          "--record changed more than the source and provenance digests of a comment edit")
    layout.write_bytes(original)
    ok(run(cli + ["--record"], elsewhere))
    check(json.loads(registry_path.read_text()) == registry, "re-recording the original sources differs")
    return [f"convert CLI (scratch checkout): --check wrote nothing (repo, elsewhere and the pxl checkout unchanged); "
            "a run installs exactly the registered outputs and a rerun rewrites nothing; a comment edit is refused "
            "until --record, which changes only its source and provenance digests, never the PNGs or ROM; refused "
            f"with nothing written: {'; '.join(l[:50] for l in lines[:5])}; ..."]


def bad_candidates(stock, rom):
    victory = sorted(model.protected_ids(stock))[5]
    return {
        "the unmodified input": (stock, "differs from the selected frame"),
        "frame b with one CHR $15 tile changed": (patched(rom, [("chr", 0x15000 + 16 * 40 + 3, b"\x5A")]),
                                                  "frame b decoded"),
        "frame b never flipped in ($D794 = $04)": (patched(rom, [(15, 0xD794, b"\x04")]), "executable"),
        "the VICTORY planes touched": (patched(rom, [(1, 0x8400 + victory, bytes([read(rom, 1, 0x8400 + victory, 1)[0]
                                                                                  ^ 0xFF]))]), "outside"),
    }


def verify(stock, candidate):
    """Problems in a candidate's static picture, data-only diff and reader argument."""
    problems = []
    try:
        spans, planes = owned_spans(_ASSETS["assets"])
        changed = {i for i, (a, b) in enumerate(zip(stock, candidate)) if a != b}
        if len(candidate) != len(stock) or not changed <= set().union(*spans.values()) | planes:
            problems.append("bytes changed outside the owned data regions (an executable or shared byte)")
        for f in model.FRAMES:
            if rows_digest(frame_rows(candidate, f)) != RENDER_PIXELS[f]:
                problems.append(f"frame {f} decoded from the ROM differs from the selected frame")
        stage.check_output(stock, candidate, _ASSETS["assets"])
        problems += [f"reader check failed: {c.name}" for c in readers.checks(candidate) if not c.ok]
    except (ValueError, IndexError) as exc:
        problems.append(f"unreadable candidate: {exc}")
    return problems


def test_verify(stock, candidate):
    problems = verify(stock, candidate)
    check(not problems, "; ".join(problems))
    return ["verify: the candidate passes the --verify-only oracle (data-only diff, both frames, reader argument)"]


def test_verify_cli(repo, elsewhere, stock, rom):
    cli = [sys.executable, "-B", str(repo / "tools/test_homerunart32.py"), str(repo / "build/analysisart32.nes"),
           "--verify-only"]
    lines = []
    for n, (label, (bad, reason)) in enumerate(bad_candidates(stock, rom).items()):
        path = elsewhere / f"bad-{n}.nes"
        path.write_bytes(bad)
        result = run(cli + ["--candidate", str(path)], elsewhere)
        check(result.returncode == 1 and reason in result.stdout,
              f"{label}: exit {result.returncode}: {result.stdout[-300:]}{result.stderr[-300:]}")
        lines.append(f"{label}: exit 1")
    good = elsewhere / "good.nes"
    good.write_bytes(rom)
    result = run(cli + ["--candidate", str(good)], elsewhere)
    check(result.returncode == 0 and "PASS verify-only" in result.stdout, f"the good ROM failed: {result.stdout[-400:]}")
    return ["test CLI: --verify-only exits 1 for " + "; ".join(lines) + "; and 0 for the selected ROM"]



class Suite:
    def __init__(self):
        self.failures, self.passed = [], 0

    def run(self, name, call, *args):
        started = time.monotonic()
        try:
            result = call(*args)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, (Failure, AssetError, ValueError)):
                detail += "\n" + "".join(traceback.format_exception(exc)[-5:])
            self.failures.append((name, detail))
            print(f"FAIL {name}: {detail}", flush=True)
            return None
        self.passed += 1
        lines = result[-1] if isinstance(result, tuple) else result
        for line in lines or ():
            print(line, flush=True)
        print(f"  ({name}: {time.monotonic() - started:.1f}s)", flush=True)
        return result


def verify_only(args, stock):
    candidate = args.candidate.read_bytes()
    try:
        _ASSETS["assets"] = stage.load_assets(stage.ASSETS, stage.read_registry())
    except (OSError, ValueError) as exc:
        print(f"FAIL verify-only assets: {exc}")
        sys.exit(1)
    problems = verify(stock, candidate)
    for p in problems:
        print(f"FAIL {p}")
    print(f"candidate {sha256(candidate)}: {len(problems)} problems")
    if problems:
        sys.exit(1)
    print("PASS verify-only")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock", type=Path, help="the pinned analysisart32 input ROM")
    ap.add_argument("--candidate", type=Path, help="the built ROM to judge (default: the deterministic build)")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: regenerate and run the converter CLI")
    ap.add_argument("--quick", action="store_true", help="two played games, fewer planted cases, teams and phases")
    ap.add_argument("--verify-only", action="store_true", help="judge only --candidate's static picture and diff")
    ap.add_argument("--refresh-fixtures", action="store_true", help="play the fixture games again even if cached")
    ap.add_argument("--fixtures", type=Path, default=played.CACHE, help="fixture cache directory (default %(default)s)")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1), help="worker processes (default %(default)s)")
    args = ap.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    stock = args.stock.read_bytes()
    if sha256(stock) != STOCK_SHA256:
        print(f"FAIL inputs: {args.stock} is not the pinned analysisart32 input")
        sys.exit(1)
    if args.verify_only:
        if not args.candidate:
            ap.error("--verify-only needs --candidate")
        verify_only(args, stock)
        return
    suite = Suite()
    print(f"inputs: analysisart32 {STOCK_SHA256}" + (f", candidate {args.candidate}" if args.candidate else ""))
    suite.run("boundaries", test_boundaries)
    pxl = args.pxl.resolve() if args.pxl else None
    if pxl:
        built = suite.run("regeneration", test_regeneration, stock, pxl)
        if built is None:
            print("FAIL: without the regenerated art nothing further can be judged")
            sys.exit(1)
        outputs, assets, rom, _ = built
    else:
        outputs = suite.run("installed outputs", lambda: (installed_outputs(), [
            "installed: build/homerunart32 holds exactly the registered outputs (no --pxl: not regenerated)"]))
        if outputs is None:
            print("FAIL: without --pxl the registered outputs must be installed under build/homerunart32")
            sys.exit(1)
        outputs = outputs[0]
        assets = HomerunAssets.parse(json.loads(outputs[stage.ASSET_JSON]))
        rom = stage.build_rom(stock, assets)
    _ASSETS["assets"] = assets
    renders = {f: outputs[f"render/scenes/homerun_{f}.png"] for f in model.FRAMES}
    candidate = args.candidate.read_bytes() if args.candidate else rom

    def same_build():
        check(candidate == rom, f"candidate {sha256(candidate)} differs from the deterministic build {sha256(rom)}")
        check(sha256(rom) == TARGET_SHA256, f"the deterministic build is {sha256(rom)}, not the selected celebration")
        return [f"candidate: {sha256(candidate)} is the deterministic build and the selected celebration"]
    suite.run("candidate", same_build)

    fixture_names = played.QUICK_FIXTURES if args.quick else tuple(played.FIXTURES)
    cache = stage.output_path(args.fixtures)
    states = suite.run("fixtures", lambda: (played.states(args.stock, fixture_names, args.jobs, args.refresh_fixtures, cache,
                                                        inputs=[args.candidate] if args.candidate else []),
                                            [f"fixtures: {len(fixture_names)} played states from {cache} (provenance "
                                             "and digests checked) or played again from RESET"]))
    jobs = Jobs(args.jobs)
    runtime = None
    if states is not None:
        runtime = submit_runtime(jobs, stock, candidate, states[0], args.quick)
        suite.run("fixture cache", test_fixture_cache, stock, cache, list(fixture_names))
    suite.run("parts", test_parts, stock, outputs)
    suite.run("converter controls", test_converter_controls, stock, renders)
    suite.run("asset boundary", test_assets, stock, assets)
    suite.run("stage", test_stage, stock, rom, assets)
    suite.run("readers", test_readers, stock, candidate)
    suite.run("static", test_static, stock, candidate, assets)
    suite.run("verify", test_verify, stock, candidate)
    with checkout(args.stock) as (repo, elsewhere):
        install(repo, outputs)
        suite.run("builder CLI", test_builder_cli, repo, elsewhere, stock, rom, assets)
        suite.run("test CLI", test_verify_cli, repo, elsewhere, stock, rom)
        shutil.rmtree(repo / "build/homerunart32")
        if pxl:
            suite.run("convert CLI", test_convert_cli, repo, elsewhere, pxl)
        else:
            print("convert CLI: skipped (no --pxl)")
    if runtime is not None:
        cases, teams, leads = runtime
        suite.run("contracts", lambda: test_contracts(
            {k: jobs.result(("contracts", k)) for k in ("stock", "candidate")},
            {label: jobs.result(("contract-mutant", label)) for label in CONTRACT_MUTANTS}))
        suite.run("natural game", test_natural, jobs, stock, candidate, renders)
        suite.run("replays", test_replays, jobs, stock, candidate, assets, cases, renders)
        suite.run("sweeps", test_sweeps, jobs, stock, candidate, assets, teams, leads, args.quick)
    jobs.close()
    print("limits: CPU model only. Frames are composed from VRAM, palette RAM and CHR; sprite-0, PPU fetch timing and "
          "open bus are approximations; audio is compared as APU register writes; walk-off, ten-run, grand-slam, "
          "series, mash and attract cases are planted RAM at a played state. CHR $15's second reader is excluded by "
          "the static reader argument (tools/homerunart32_readers.py), not by play. Root's real-core captures, the "
          "mapper census over SPEED, VICTORY and attract, listening, hardware, PAL and a second emulator are separate.")
    print(f"homerunart32 SHA256 {sha256(rom)}")
    if suite.failures:
        print(f"FAIL: {len(suite.failures)} of {suite.passed + len(suite.failures)} sections failed: "
              f"{', '.join(name for name, _ in suite.failures)} ({time.monotonic() - started:.1f}s)")
        sys.exit(1)
    print(f"PASS ({suite.passed} sections, {time.monotonic() - started:.1f}s)" + (" quick" if args.quick else ""))


if __name__ == "__main__":
    main()
