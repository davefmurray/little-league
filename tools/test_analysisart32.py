#!/usr/bin/env python3
"""Check the analysisart32 stage: the layout, placement and asset boundaries, the derived ratings, the approved
parts, regeneration, the converter's refusals, the guarded builder, the built ROM's own bytes and the
Power Analysis card at runtime against the stockart32 input.

    .venv/bin/python -B tools/test_analysisart32.py build/stockart32.nes --candidate build/analysisart32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python -B tools/test_analysisart32.py build/stockart32.nes --candidate build/analysisart32.nes --quick
    .venv/bin/python -B tools/test_analysisart32.py build/stockart32.nes --candidate BAD.nes --verify-only --teams 31

Every section runs and every failure is reported; any failure exits with status 1. Oracles never come from the
candidate's own tables: ratings and their meaning are read from the input ROM's table, chart directions and
label list; names and flags from the stock writers executed on the input ROM; digits and letters from the
CHR $00 font; sockets from the decoded background, matched against the outline of the input ROM's ball
sprite; the art from the pinned pxl render. Runtime runs boot both ROMs from RESET on the repository's CPU
model with the same controller script; independent runs go to worker processes (--jobs).

--candidate names the ROM the runtime oracles judge (default: the deterministic build); it must also equal the
deterministic build. --pxl regenerates the art twice with the pinned renderer and runs the converter command
line; without it the installed build/analysisart32 outputs must match data/analysisart32/digests.json.
--verify-only judges just the candidate (static and runtime oracles, stock parity) on --teams. --quick tours
seven teams and samples fewer NMI sites, timing fixtures and scoreboard flows.

The CPU model counts cycles but approximates the PPU: sprite-0 hit is manufactured from beam position and
OAM, PPU fetch timing and open bus are not modelled, frames are composed from VRAM, and audio is compared as
APU register writes. It does not prove real-core split seams, transition pictures, mapper timing or sound;
those, the 224-line capture review and the tournament gates belong to the root.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import io
import json
import multiprocessing
import os
import random
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

from PIL import Image

import analysisart32_assets as model
from analysisart32_assets import AnalysisAssets, AssetError, Layout
import analysisart32_convert as convert
import analysisart32_machine as machine
import build_analysisart32 as stage
from build_draw32 import locate
from frontend32_test_machine import check_output_guards
import menu32_convert as menu
import render_menu32 as R
import stockart32_parts as parts

ROOT = stage.ROOT
STOCK_SHA256 = "a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55"
TARGET_SHA256 = "1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e"
RENDER_SHA256 = "3dc8c52ddcad12bdbe180d438c311359ae8689776f8e604cea3c089559943568"
# The judged reservation (inclusive ends) and the bytes each region changes in the selected card.
REGIONS = (("init-hook", 3, 0xAF80, 0xAF91), ("init-tail", 3, 0xAF9B, 0xAF9F), ("state1-draw", 3, 0xAFB9, 0xAFBB),
           ("home-pad", 3, 0xBD20, 0xBD2F), ("home-code", 3, 0xBD30, 0xBDB7), ("far-screen", 13, 0xA000, 0xA3FF),
           ("far-code", 13, 0xA400, 0xA4FF), ("far-pad", 13, 0xBD20, 0xBD2F), ("chr06-new", "chr", 0x6BA0, 0x6FFF))
REGION_CHANGES = {"init-hook": 18, "init-tail": 5, "state1-draw": 2, "home-pad": 16, "home-code": 123,
                  "far-screen": 1008, "far-code": 227, "far-pad": 16, "chr06-new": 109}
CLAIMED, CHANGED = 2594, 1524
NEW_TILES = (0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xC1, 0xC2, 0xC3, 0xE0)
TITLE_TEMPLATE = (0xE0, 0xE9, 0x20, 0x20, 0x20, 0x20, 0xE9, 0xE0)      # rows 0-7 outside the name writer's cells
HINT = "BACK"
SPRITE0 = bytes.fromhex("40 FE 20 F8")
SHADOWS, SPLIT = bytes.fromhex("1B 1B 18 06"), 0x06
STAT_LABELS = {"BATTING": 0x214D, "RUNNING": 0x2243, "PITCHING": 0x232C, "DEFENSE": 0x2257}
CHART_DIRECTIONS = bytes.fromhex("00 F8 00 08 F8 00 08 00")           # dx then dy per stored index: up left down right
FULL_TEAMS = tuple(range(32))
QUICK_TEAMS = (0, 2, 5, 13, 18, 27, 31)       # wide and narrow fonts, flag and none, 1-4 in every stat
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CROP = (8, 232)                               # the root's 224-line emulator captures
# RAM that may differ from stock after the card returns to the picker, with the reason; everything else and
# all of WRAM must equal stock.
LEAVE_SCRATCH = {
    **dict.fromkeys(range(0x14, 0x18), "stock $C5C4 metatile map scratch"),
    0x26: "CHR1 shadow below the split: $06 after the card, $18 after stock; read only by the NMI split behind "
          "$047A bit 1, which only $C6C1 sets, always together with $26",
    0x2E: "the stock flag writer's saved bank: the card calls it from bank 13",
    0x38: "stock $C5C4 scratch",
    0xAA: "stock $C840 label list pointer", 0xAB: "stock $C840 label list pointer",
    0xBA: "stock radar state", 0xBB: "stock radar state",
    **dict.fromkeys(range(0x0100, 0x0180), "stock $C5C4 decode buffer on the stack page"),
    **dict.fromkeys(range(0x0195, 0x01B5), "palette buffer: the card's palette until the next palette load"),
    **dict.fromkeys(range(0x01E0, 0x01F0), "dead stack below the deepest frame (the hop pad's JSR)"),
    **dict.fromkeys(range(0x0340, 0x0360), "stock $C840 label run buffer"),
    0x047F: "the stock radar's OAM index",
    0x06B4: "the name writer's address low byte: the centered column",
}


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
    raise Failure(f"accepted; expected a refusal mentioning {reason!r}")



def planar(pattern):
    lo, hi = pattern[:8], pattern[8:16]
    return [[(lo[y] >> (7 - x) & 1) | (hi[y] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def chr_bank(rom, bank):
    start = 16 + 16 * 0x4000 + bank * 0x1000
    return rom[start:start + 0x1000]


def prg(rom, bank, address, size=1):
    start = 16 + bank * 0x4000 + address - (0xC000 if bank == 15 else 0x8000)
    return rom[start:start + size]


def cell_palette(attributes, col, row):
    return attributes[8 * (row // 4) + col // 4] >> (4 * (row // 2 % 2) + 2 * (col // 2 % 2)) & 3


def shape(pattern):
    return tuple(tuple(bool(v) for v in row) for row in planar(pattern))


def background(rom, nametable, palette, top, bottom, switch=72):
    """RGB rows of a background: CHR bank `top` on the lines above `switch`, `bottom` from it on."""
    banks = {top: chr_bank(rom, top), bottom: chr_bank(rom, bottom)}
    grids, rows = {}, []
    for y in range(240):
        bank = top if y < switch else bottom
        row = []
        for x in range(256):
            tile = nametable[32 * (y // 8) + x // 8]
            if (bank, tile) not in grids:
                grids[(bank, tile)] = planar(banks[bank][16 * tile:16 * tile + 16])
            v = grids[(bank, tile)][y % 8][x % 8]
            row.append(menu.NES_RGB[palette[4 * cell_palette(nametable[960:], x // 8, y // 8) + v] if v else palette[0]])
        rows.append(row)
    return rows


def png_rows(data):
    image = Image.open(io.BytesIO(data)).convert("RGB")
    px = image.load()
    return [[px[x, y] for x in range(image.width)] for y in range(image.height)]


def glyph_shapes(stock):
    font = chr_bank(stock, 0)
    return {shape(font[16 * ord(ch):16 * ord(ch) + 16]): ch for ch in GLYPHS}


def ball_outline(stock, tile):
    """The ball sprite's edge pixels and the interior they enclose, from the input ROM's CHR $1B."""
    grid = planar(chr_bank(stock, 0x1B)[16 * tile:16 * tile + 16])
    inside = {(x, y) for y in range(8) for x in range(8) if grid[y][x]}
    edge = {(x, y) for x, y in inside if any((x + dx, y + dy) not in inside for dx, dy in ((1, 0), (-1, 0), (0, 1),
                                                                                         (0, -1)))}
    return edge, inside - edge


def find_rings(rows, edge, interior, backdrop):
    """Every 8x8 window below the split, at any pixel offset, holding the ball outline in one color over an
    empty interior: an empty ball socket."""
    probe = min(edge)
    found = []
    for y0 in range(8 * (model.SPLIT_ROW + 1), 233):
        for x0 in range(249):
            first = rows[y0 + probe[1]][x0 + probe[0]]
            if first == backdrop:
                continue
            if all(rows[y0 + y][x0 + x] == first for x, y in edge) and all(
                    rows[y0 + y][x0 + x] == backdrop for x, y in interior):
                found.append((x0, y0))
    return found



def stock_meaning(stock):
    """Stored index -> stat, from the chart's direction tables and the label list's positions, independently."""
    check(prg(stock, 3, 0xB1CA, 8) == CHART_DIRECTIONS, "the stock chart's direction tables moved")
    labels, p = {}, 0xB1FB
    while True:
        low, high = prg(stock, 3, p, 2)
        p += 2
        letters = bytearray()
        while prg(stock, 3, p)[0] < 0xFE:
            letters += prg(stock, 3, p)
            p += 1
        labels[letters.decode()] = (high & 0x3F) << 8 | low
        p += 1
        if prg(stock, 3, p - 1)[0] == 0xFF:
            break
    check(labels == STAT_LABELS, f"stock labels {labels}")
    center_col, center_row = 0x80 // 8, 0x8F // 8
    meaning = []
    for i in range(4):
        dx, dy = (b - 256 if b > 127 else b for b in (CHART_DIRECTIONS[i], CHART_DIRECTIONS[4 + i]))

        def toward(item, dx=dx, dy=dy):
            col, row = (item[1] - 0x2000) % 32, (item[1] - 0x2000) // 32
            return (col + len(item[0]) / 2 - center_col) * dx + (row + 1 - center_row) * dy
        meaning.append(max(labels.items(), key=toward)[0])
    return tuple(meaning)


def stock_ratings(stock):
    table = prg(stock, 3, 0xBC80, 128)
    return [tuple(table[4 * t:4 * t + 4]) for t in range(32)]


def stock_writer(stock, team, address):
    """{nametable index: CHR $18 tile} the stock name writer stores for `team` at `address`, rendering off."""
    m = R.Machine(stock)
    m.mpu.sp = 0xEF
    m.map_bank(3)
    m.vram[0:0x400] = b"\xEE" * 0x400
    m.ram[0x2C], m.ram[0x32], m.ram[0xAC], m.ram[0xAD], m.ram[0x04EF] = 1, 0, 0, 0x40, team
    m.ram[0x06B3], m.ram[0x06B4] = address >> 8, address & 0xFF
    m.call(0xC9A8, a=team)
    nametable = m.nametable()
    return {i: t for i, t in enumerate(nametable[:960]) if t != 0xEE}


def stock_flag(stock, team, x, y):
    """OAM slots 1-9 as the stock flag writer stores them for `team` at (x, y)."""
    m = R.Machine(stock)
    m.mpu.sp = 0xEF
    m.map_bank(3)
    m.ram[0x0200:0x0300] = b"\xF0" * 256
    m.ram[0x047F], m.ram[0x04], m.ram[0x05] = 4, y, x
    m.mpu.x = team
    m.call(0xCB56)
    return bytes(m.ram[0x0204:0x0228])



class Context:
    """What the candidate oracle needs from independent sources, computed once."""

    def __init__(self, stock, render_png):
        check(sha256(render_png) == RENDER_SHA256, "the render is not the pinned scene")
        self.stock = stock
        self.render = png_rows(render_png)
        self.glyphs = glyph_shapes(stock)
        self.meaning = stock_meaning(stock)
        self.ratings = stock_ratings(stock)
        self.chr18 = chr_bank(stock, 0x18)
        self.writer = {}

    def writer_at(self, team, col):
        if (team, col) not in self.writer:
            self.writer[(team, col)] = stock_writer(self.stock, team, 0x2060 + col)
        return self.writer[(team, col)]


def read_letters(rows, render, nametable, chr_bottom, glyphs, backdrop):
    """Cells below the split where the candidate differs from the pinned render: each must be a CHR $00 glyph on
    a blank render cell. ({(row, col): char}, problems)."""
    letters, problems = {}, []
    for row in range(model.SPLIT_ROW + 1, 30):
        for col in range(32):
            if all(rows[8 * row + y][8 * col:8 * col + 8] == render[8 * row + y][8 * col:8 * col + 8] for y in range(8)):
                continue
            blank = all(render[8 * row + y][8 * col + x] == backdrop for y in range(8) for x in range(8))
            tile = nametable[32 * row + col]
            ch = glyphs.get(shape(chr_bottom[16 * tile:16 * tile + 16]))
            if not blank or ch is None:
                problems.append(f"cell row {row} col {col} differs from the pinned render and is no CHR $00 glyph")
            else:
                letters[(row, col)] = ch
    return letters, problems


def words(letters):
    found, run = [], None
    for (row, col) in sorted(letters):
        if run and run[0] == row and run[1] + len(run[2]) == col:
            run = (row, run[1], run[2] + letters[(row, col)])
        else:
            if run:
                found.append(run)
            run = (row, col, letters[(row, col)])
    if run:
        found.append(run)
    return found


def balls_on(oam, ball, rings, rows_of):
    """{stat index: socket indexes holding a ball}, balls on no socket, and the visible ball count."""
    sprites = [(oam[4 * s + 3], oam[4 * s] + 1) for s in range(64) if oam[4 * s] < 0xEF and oam[4 * s + 1] == ball]
    boxes = set(sprites)
    per = {i: [k for k, ring in enumerate(ring_list) if ring in boxes] for i, ring_list in rows_of.items()}
    return per, sorted(b for b in boxes if b not in rings), len(sprites)


def judge_card(ctx, rom, rest, team, cache):
    """The rest frame of one visit; a list of problems."""
    tag, problems = f"team {team:2d}", []
    nt, oam, palette = rest["nametable"], rest["oam"], rest["palette"]
    want = ctx.ratings[team]
    if rest["shadows"] != SHADOWS or rest["split"] != SPLIT or oam[:4] != SPRITE0:
        problems.append(f"{tag}: CHR shadows {rest['shadows'].hex()}, split mode {rest['split']:02X}, sprite 0 "
                        f"{oam[:4].hex()}; the card keeps stock sprite 0 and only moves $26 to CHR $06")
    rows = background(rom, nt, palette, rest["shadows"][2], rest["shadows"][3])
    backdrop = menu.NES_RGB[palette[0]]
    letters, text = read_letters(rows, ctx.render, nt, chr_bank(rom, rest["shadows"][3]), ctx.glyphs, backdrop)
    problems += [f"{tag}: {p}" for p in text[:3]]
    found = words(letters)
    labels = {w: (row, col) for row, col, w in found if w in STAT_LABELS}
    if sorted(labels) != sorted(STAT_LABELS) or sum(w in STAT_LABELS for _, _, w in found) != 4:
        return problems + [f"{tag}: the labels {found[:6]} do not show each stock label once"]
    hint = [(row, col) for row, col, w in found if w == HINT]
    if len(hint) != 1 or not (CROP[0] + 8 <= 8 * hint[0][0] and 8 * hint[0][0] + 8 <= CROP[1] - 8):
        problems.append(f"{tag}: the {HINT!r} hint is not shown once inside the 224-line crop's margins: {found}")
    if not all(CROP[0] <= 8 * row and 8 * row + 8 <= CROP[1] for row, _ in letters):
        problems.append(f"{tag}: a letter or digit leaves the 224-line crop")
    if not all(CROP[0] <= oam[4 * s] + 1 and oam[4 * s] + 9 <= CROP[1] for s in range(1, 64) if oam[4 * s] < 0xEF):
        problems.append(f"{tag}: a flag or ball sprite leaves the 224-line crop")
    if "rings" not in cache:
        ball_tiles = {oam[4 * s + 1] for s in range(10, 64) if oam[4 * s] < 0xEF}
        if len(ball_tiles) != 1:
            return problems + [f"{tag}: rest sprites outside the flag use tiles {sorted(ball_tiles)}"]
        cache["ball"] = ball_tiles.pop()
        cache["rings"] = find_rings(rows, *ball_outline(ctx.stock, cache["ball"]), backdrop)
    rings = cache["rings"]
    rows_of = {i: sorted(r for r in rings if r[1] == 8 * labels[stat][0]) for i, stat in enumerate(ctx.meaning)}
    if len(rings) != 16 or any(len(v) != 4 for v in rows_of.values()):
        return problems + [f"{tag}: {len(rings)} sockets in the decoded background; 4 must sit on each label row"]
    cache["rows_of"] = rows_of
    per, stray, count = balls_on(oam, cache["ball"], set(rings), rows_of)
    if stray:
        problems.append(f"{tag}: ball sprites at {stray[:4]} sit on no socket")
    for i, stat in enumerate(ctx.meaning):
        if per[i] != list(range(want[i])):
            problems.append(f"{tag}: {stat} shows balls on sockets {per[i]}, rating {want[i]} fills the first {want[i]}")
        cache.setdefault("covered", set()).update((i, k) for k in per[i])
        row = labels[stat][0]
        digits = [(col, ch) for (r, col), ch in letters.items() if r == row and ch.isdigit()]
        right_of = max(x for x, _ in rows_of[i]) + 8
        if [ch for col, ch in digits if 8 * col >= right_of] != [str(want[i])] or len(digits) != 1:
            problems.append(f"{tag}: {stat} digits {digits}, expected {want[i]} right of its sockets")
    if count != sum(want):
        problems.append(f"{tag}: {count} ball sprites for ratings {want}")
    matches = [(col, ctx.writer_at(team, col)) for col in range(32)]
    matches = [(col, cells) for col, cells in matches if all(nt[i] == t for i, t in cells.items())]
    if len(matches) != 1:
        return problems + [f"{tag}: the stock writer's output matches the title band at {len(matches)} columns"]
    col, cells = matches[0]
    template = [i for i in range(256) if i not in cells and nt[i] != TITLE_TEMPLATE[i // 32]]
    if template:
        problems.append(f"{tag}: title cells {template[:6]} outside the writer's differ from the accepted template")
    if any(i // 32 not in model.NAME_ROWS for i in cells):
        problems.append(f"{tag}: the name writer reaches rows {sorted({i // 32 for i in cells})}")
    xs = [8 * (i % 32) + x for i, t in cells.items() if i // 32 in (3, 4) and t != 0x20
          for x in range(8) if any(planar(ctx.chr18[16 * t:16 * t + 16])[y][x] for y in range(8))]
    flag = [s for s in range(1, 10) if oam[4 * s] < 0xEF]
    if any(b < 0xEF for b in stock_flag(ctx.stock, team, 0x20, 0x15)[0::4]):
        x, y = oam[7], oam[4]
        if oam[4:40] != stock_flag(ctx.stock, team, x, y) or len(flag) != 9:
            problems.append(f"{tag}: OAM slots 1-9 are not the stock flag writer's nine sprites at ({x},{y})")
        if x + 24 > min(xs):
            problems.append(f"{tag}: the flag overlaps the name")
        left = x
    else:
        if flag:
            problems.append(f"{tag}: a flagless team shows {len(flag)} flag sprites")
        left = min(xs)
    center = (left + max(xs)) / 2
    if abs(center - 127.5) > 4:
        problems.append(f"{tag}: the name and flag center at x {center}, not within 4 px of 127.5")
    return problems


def judge_visit(ctx, rom, visit, cache):
    team, problems = visit["team"], []
    tag = f"team {team:2d}"
    problems += judge_card(ctx, rom, visit["rest"], team, cache)
    chr1 = [v for _, _, _, register, v in visit["rest_maps"] if register == 2]
    if chr1[:4] != [0x18, 0x06, 0x18, 0x06]:
        problems.append(f"{tag}: CHR1 loads at rest {[f'{v:02X}' for v in chr1[:6]]}, expected $18 then $06 each frame")
    lines = [(off - R.VBLANK) / (341 / 3) for _, off, _, register, v in visit["rest_maps"] if register == 2 and v == 6]
    if not lines or not all(8 * model.SPLIT_ROW <= line < 8 * model.SPLIT_ROW + 8 for line in lines):
        problems.append(f"{tag}: the CHR1 $06 load lands on model lines {[round(c, 2) for c in lines[:3]]}, not "
                        "inside the split row")
    if "rows_of" in cache:
        for offset, (scene, state, values, page) in sorted(visit["frames"].items()):
            if scene not in (0x14, 0x15):
                continue
            per, stray, count = balls_on(page, cache["ball"], set(cache["rings"]), cache["rows_of"])
            if stray or any(per[i] != list(range(values[i])) for i in range(4)) or count != sum(values):
                problems.append(f"{tag}: frame A+{offset} state {state} shows balls {per} for $BC-$BF {list(values)}")
                break
    entry = visit["entry_nametable"]
    if entry is None or entry[1][:960] != visit["rest"]["nametable"][:960]:
        problems.append(f"{tag}: scene $15 starts before the card's name and digits are drawn")
    if visit["late_ppu"]:
        problems.append(f"{tag}: {visit['late_ppu']} PPU writes landed with rendering on outside vblank")
    return problems


def judge_parity(visit, stock_visit):
    """The candidate's visit against stock's on the same script: frames, timing, sound, return and state."""
    tag, problems = f"team {visit['team']:2d}", []

    def frames(v):
        return [(o, f[0], f[1], f[2]) for o, f in sorted(v["frames"].items())]
    if frames(visit) != frames(stock_visit):
        first = next((a for a, b in zip(frames(visit), frames(stock_visit)) if a != b), None)
        problems.append(f"{tag}: per-frame scene, state and $BC-$BF differ from stock, first {first}")
    if visit["timeline"] != stock_visit["timeline"]:
        problems.append(f"{tag}: the scene-$15 handler timeline differs from stock")
    release = [v["marks"]["AF94"][0] - v["marks"]["AF80"][0] for v in (visit, stock_visit)]
    if release[0] != release[1]:
        problems.append(f"{tag}: the init releases {release[0]} frames after its vblank, stock {release[1]}")
    if visit["apu"] != stock_visit["apu"]:
        problems.append(f"{tag}: APU writes differ from stock ({len(visit['apu'])} vs {len(stock_visit['apu'])})")
    if visit["queue"] != stock_visit["queue"] or not any(v == 0x35 for _, v in visit["queue"]):
        problems.append(f"{tag}: sound requests {visit['queue']} vs stock {stock_visit['queue']}")
    if visit["cursor"] != visit["team"] or not visit["series_ok"]:
        problems.append(f"{tag}: the exit returned to team {visit['cursor']} (series intact {visit['series_ok']})")
    before, after = stock_visit["picker_after"], visit["picker_after"]
    differing = sorted(k for k in before if before[k] != after[k])
    if differing != ["shadows"] or after["shadows"][:3] != before["shadows"][:3] or after["shadows"][3] != 0x06:
        problems.append(f"{tag}: the picker after the card differs from stock in {differing}")
    leaked = [a for a in range(0x800) if visit["ram_after"][a] != stock_visit["ram_after"][a] and a not in LEAVE_SCRATCH]
    if leaked or visit["wram_after"] != stock_visit["wram_after"]:
        problems.append(f"{tag}: after the return RAM {[f'${a:04X}' for a in leaked[:6]]} or WRAM differ from stock")
    return problems


def judge_tours(ctx, rom, tours, stock_tours, coverage=True):
    problems, cache = [], {}
    for tour, stock_tour in zip(tours, stock_tours):
        for visit, stock_visit in zip(tour["visits"], stock_tour["visits"]):
            problems += judge_visit(ctx, rom, visit, cache)
            problems += judge_parity(visit, stock_visit)
        differing = sorted(k for k in tour["mode_after"] if tour["mode_after"][k] != stock_tour["mode_after"][k])
        if differing not in ([], ["shadows"]):
            problems.append(f"the mode menu after the tour differs from stock in {differing}")
        if not tour["series_ok"] or tour["picker_before"] != stock_tour["picker_before"]:
            problems.append("the tour's series or the picker before the card differ from stock")
    covered = cache.get("covered", set())
    if coverage and covered != {(i, k) for i in range(4) for k in range(4)}:
        problems.append(f"only {len(covered)} of 16 sockets held a ball on this tour")
    return problems



def earlier_mode(stock, rom):
    import test_modeart32 as mode_suite
    for name, steps in mode_suite.FLOWS.items():
        ours, theirs = mode_suite.scene_run(rom, steps)[0], mode_suite.scene_run(stock, steps)[0]
        check(ours == theirs, f"mode menu {name}: stockart32 {theirs} vs candidate {ours}")
    mode_suite.test_audio(stock, rom)
    return [f"earlier mode suite: all {len(mode_suite.FLOWS)} mode-menu exits give stockart32's scenes, mode and "
            "ownership bytes and sound requests; idle APU writes and press sounds equal stockart32 (test_modeart32's "
            "own scene_run and test_audio)"]


def earlier_pick(rom):
    import test_pick32 as pick_suite
    return [f"earlier pick suite: {pick_suite.flow_analysis(rom)} (test_pick32.flow_analysis)"]


def earlier_score(stock, rom, quick, part=0, parts_=1):
    import test_scoreart32 as score_suite
    flows = (score_suite.flows(True)[:6] if quick else score_suite.flows(False))[part::parts_]
    for name, entry, pads, frames in flows:
        try:
            score_suite.flow_check(stock, rom, entry, pads, frames)
        except AssertionError as exc:
            raise Failure(f"scoreboard {name}: {exc}") from None
    return len(flows)


JOBS = {"tour": machine.tour, "timing_cases": machine.timing_cases, "injection_runs": machine.injection_runs,
        "screens": machine.screens, "earlier_mode": earlier_mode, "earlier_pick": earlier_pick,
        "earlier_score": earlier_score}


def job(name, *args):
    """One independent run, by name; module level so worker processes can import it."""
    return JOBS[name](*args)


class Jobs:
    """Independent runs, in worker processes when workers > 1; each result or its exception, by key."""

    def __init__(self, workers):
        self.pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) \
            if workers > 1 else None
        self.pending = {}

    def submit(self, key, *spec):
        self.pending[key] = self.pool.submit(job, *spec) if self.pool else spec

    def result(self, key):
        item = self.pending[key]
        if self.pool:
            return item.result()
        return job(*item)

    def close(self):
        if self.pool:
            self.pool.shutdown(cancel_futures=True)


def chunks(teams, size):
    return [teams[i:i + size] for i in range(0, len(teams), size)]


def keys_for(teams):
    return ["B" if i % 2 == 0 else "A" for i in range(len(teams))]


def submit_tours(jobs, prefix, rom, teams, size):
    keys = []
    for k, chunk in enumerate(chunks(list(teams), size)):
        jobs.submit((prefix, k), "tour", rom, chunk, keys_for(chunk))
        keys.append((prefix, k))
    return keys



def layout_cases():
    def stat(i, **values):
        return lambda d: d["stats"][i].update(values)
    return [
        ("format", "expected format", lambda d: d.update(format="analysisart32-layout/2")),
        ("unknown key", "keys must be among", lambda d: d.update(notes="")),
        ("missing ball", "keys must be among", lambda d: d.pop("ball")),
        ("scene with a capital", "path-safe", lambda d: d.update(scene="Card")),
        ("backdrop $0D", "unsupported NES color", lambda d: d.update(backdrop="0D")),
        ("three palettes", "four background palettes", lambda d: d["palettes"].pop()),
        ("a two-color palette", "three NES colors", lambda d: d["palettes"][0].pop()),
        ("split row 9", "must be 8", lambda d: d["title"].update(split_row=9)),
        ("split row 7", "must be 8", lambda d: d["title"].update(split_row=7)),
        ("name rows 3-5 only", "padded, wrapped rows", lambda d: d["title"].update(name_rows=[3, 4, 5])),
        ("a rail on a name row", "outside the name writer", lambda d: d["title"].update(rail_rows=[1, 5])),
        ("split ids without the blank", "include the blank", lambda d: d["title"].update(split_ids=["E0"])),
        ("reserve id $B9", "free CHR $06 id", lambda d: d.update(reserve={"B9": "solid3"})),
        ("reserve kind", "kind must be one of", lambda d: d.update(reserve={"E0": "solid1"})),
        ("reserve outside the split ids", "list it in split_ids", lambda d: d.update(reserve={"E1": "solid3"})),
        ("attribute hint palette 4", "from 0 to 3", lambda d: d["attr_hints"][0].update(palette=4)),
        ("a lowercase glyph", "single uppercase", lambda d: d.update(glyphs=["3", "4", "k"])),
        ("a glyph twice", "single uppercase", lambda d: d.update(glyphs=["3", "3", "K"])),
        ("three stats", "one row per stat", lambda d: d["stats"].pop()),
        ("an unknown stat", "must be one of", stat(0, stat="SPEED")),
        ("a stat twice", "names a stat twice", stat(1, stat="BATTING")),
        ("reordered meaning", "stored order", lambda d: d["stats"].insert(0, d["stats"].pop(1))),
        ("two stats on one row", "share a row", stat(1, row=11)),
        ("a stat on the split row", "from 9 to 29", stat(0, row=8)),
        ("a label off the screen", "from 0 to 24", stat(2, label_col=25)),
        ("a digit off the screen", "from 0 to 31", stat(0, digit_col=32)),
        ("five sockets", "list of 4", lambda d: d["sockets"].update(cols=[14, 16, 18, 20, 22])),
        ("sockets right to left", "left to right", lambda d: d["sockets"].update(cols=[22, 20, 18, 16])),
        ("a socket twice", "names a value twice", lambda d: d["sockets"].update(cols=[16, 16, 20, 22])),
        ("a socket on the digit", "overlaps", lambda d: d["sockets"].update(cols=[16, 18, 20, 25])),
        ("a label over the sockets", "overlaps", stat(2, label_col=10)),
        ("text over a label", "overlaps", lambda d: d["text"].append({"row": 11, "col": 8, "text": "X"})),
        ("text above the split", "from 9 to 29", lambda d: d["text"][0].update(row=5)),
        ("lowercase text", "uppercase letters", lambda d: d["text"][0].update(text="Back")),
        ("ball palette 0", "from 1 to 3", lambda d: d["ball"].update(sprite_palette=0)),
        ("ball palette 4", "from 1 to 3", lambda d: d["ball"].update(sprite_palette=4)),
        ("ball color $0E", "unsupported NES color", lambda d: d["ball"].update(colors=["0F", "16", "0E"])),
        ("flag below the title band", "from 0 to 40", lambda d: d["flag"].update(y=60)),
        ("one paced NMI", "must be 2", lambda d: d.update(pace_nmis=1)),
        ("no pacing", "must be 2", lambda d: d.update(pace_nmis=0)),
    ]


def test_layout_boundary():
    path = model.ART / "layout.json"
    data = json.loads(path.read_text())
    Layout.parse(copy.deepcopy(data), "0" * 64)
    cases = layout_cases()
    for label, reason, mutate in cases:
        bad = copy.deepcopy(data)
        mutate(bad)
        try:
            Layout.parse(bad, "0" * 64)
        except AssetError as exc:
            check(reason in str(exc), f"layout {label}: refused for another reason: {exc}")
            continue
        raise Failure(f"the layout boundary accepted {label}")
    with tempfile.TemporaryDirectory() as temporary:
        broken = Path(temporary) / "layout.json"
        broken.write_text(path.read_text()[:-10])
        refused(Layout.load, "not JSON", broken)
    return [f"layout: analysisart32-layout/1 parses; {len(cases)} malformed layouts (keys, colors, palettes, split row "
            "other than 8, name and rail rows, split and reserve ids, hints, glyphs, missing, unknown, duplicate and "
            "reordered stats, rows on the split, cells off the screen, socket count, order and repeats, text, label, "
            "digit and socket overlaps, ball palette 0 or 4, flag row, pacing) and broken JSON are refused"]


def test_placements_boundary(manifest):
    data = json.loads((model.ART / "placements.json").read_text())
    sizes = {p.id: p.size for p in manifest.parts}
    model.parse_placements(copy.deepcopy(data), sizes)
    cases = [
        ("format", "expected format", lambda d: d.update(format="analysisart32-placements/2")),
        ("another manifest", "the reviewed part source", lambda d: d.update(manifest="art/x.json")),
        ("no placements", "non-empty list", lambda d: d.update(placements=[])),
        ("an unknown part", "names no stockart32 part", lambda d: d["placements"][0].update(part="umpire")),
        ("a stamp off the screen", "from 0 to 255", lambda d: d["placements"][0].update(at=[256, 0])),
        ("an area past the part", "from 1 to", lambda d: d["placements"][0].update(area=[60, 0, 32, 32])),
        ("visible past the screen", "from 1 to", lambda d: d["placements"][0].update(visible=[0, 97, 32, 150])),
        ("visible without a reason", "why", lambda d: d["placements"][0].pop("why")),
        ("an unknown key", "keys must be among", lambda d: d["placements"][7].update(flip=True)),
    ]
    for label, reason, mutate in cases:
        bad = copy.deepcopy(data)
        mutate(bad)
        try:
            model.parse_placements(bad, sizes)
        except AssetError as exc:
            check(reason in str(exc), f"placements {label}: refused for another reason: {exc}")
            continue
        raise Failure(f"the placement boundary accepted {label}")
    return [f"placements: {len(data['placements'])} stamps parse; {len(cases)} malformed placement records are refused"]


def test_ratings(stock):
    meaning = stock_meaning(stock)
    check(meaning == model.STATS, f"independent stored order {meaning}")
    ratings = model.AnalysisRatings.from_rom(stock)
    check(ratings.meaning == meaning and list(ratings.values) == stock_ratings(stock), "the model's ratings differ")
    check(all(1 <= v <= 4 for r in ratings.values for v in r), "a rating leaves 1..4")
    check(ratings.values[31] == (3, 3, 4, 2) and ratings.values[13] == (1, 1, 1, 1), "teams 31 and 13 moved")
    for value in (0, 5):
        bad = bytearray(stock)
        bad[locate(3, 0xBC80 + 4 * 7 + 2)] = value
        refused(model.AnalysisRatings.from_rom, "leave 1..4", bytes(bad))
    swapped = bytearray(stock)
    swapped[locate(3, 0xB1CA):locate(3, 0xB1CA) + 8] = bytes.fromhex("F8 00 08 00 00 F8 00 08")
    refused(model.AnalysisRatings.from_rom, "stored order", bytes(swapped))
    reader = bytearray(stock)
    reader[locate(3, 0xAFE3)] ^= 0x40
    refused(model.AnalysisRatings.from_rom, "reader $AFE2", bytes(reader))
    return [f"ratings: stored order {', '.join(meaning)} derived independently from the chart directions $B1CA/$B1CE "
            "and the label list $B1FB (BATTING $214D, RUNNING $2243, PITCHING $232C, DEFENSE $2257) agrees with the "
            "model; all 128 values are 1..4, team 31 3,3,4,2, team 13 1,1,1,1; ratings 0 and 5, swapped directions and "
            "a moved reader are refused"]


def test_parts(stock, manifest, placements, rom):
    """The approved parts, their reviewed masks, and every visible part pixel in the built ROM's own bytes."""
    approved = json.loads((ROOT / "data/stockart32/digests.json").read_text())["outputs"]
    cut = parts.cut_parts(stock, manifest)
    used = sorted({p.part for p in placements})
    check(used == ["cheer", "crowd-red", "pair"], f"placed parts {used}")
    for pid in used:
        check(sha256(parts.png(cut[pid])) == approved[f"parts/{pid}.png"], f"{pid} differs from the approved part")
        spec = next((c for c in manifest.characters if c.id == pid), None)
        if spec is not None:
            check(parts.mask_sha256(cut[pid].pixels) == spec.mask_sha256, f"{pid} mask differs from its review")
    rows = background(rom, prg(rom, 13, 0xA000, 0x400), prg(rom, 13, 0xA400, 16), 0x18, 0x06)
    totals, faces = {}, 0
    for p in placements:
        part = cut[p.part]
        ax, ay, aw, ah = p.area or (0, 0, part.width, part.height)
        vx, vy, vw, vh = p.visible or (p.at[0], p.at[1], aw, ah)
        shown = hidden = 0
        for y in range(ah):
            for x in range(aw):
                c = part.pixels[ay + y][ax + x]
                sx, sy = p.at[0] + x, p.at[1] + y
                if c is None or not (sx < 256 and sy < 240):
                    continue
                if vx <= sx < vx + vw and vy <= sy < vy + vh:
                    check(rows[sy][sx] == menu.NES_RGB[c], f"{p.part} pixel ({sx},{sy}) is not its color in the ROM")
                    shown += 1
                elif rows[sy][sx] != menu.NES_RGB[c]:
                    hidden += 1
        totals[p.part] = totals.get(p.part, 0) + shown
        spec = next((c for c in manifest.characters if c.id == p.part), None)
        if spec is not None:
            for fx, fy, fw, fh in spec.faces:
                check(vx <= p.at[0] + fx and p.at[0] + fx + fw <= vx + vw and vy <= p.at[1] + fy
                      and p.at[1] + fy + fh <= vy + vh, f"a reviewed {p.part} face box is occluded")
                faces += 1
        if p.part == "pair":
            check(hidden > 0, "the counter and ledge occlusion of the pair hides nothing")
    return [f"parts: cheer, crowd-red and pair regenerate from art/stockart32/characters.json equal to the approved "
            "data/stockart32/digests.json PNGs, with their reviewed masks; every visible part pixel shows its color in "
            f"the built ROM's own screen, CHR and palette bytes ({', '.join(f'{k} {v}' for k, v in totals.items())}); "
            f"the counter and ledge really occlude the pair, and all {faces} reviewed face boxes stay visible"]


def test_regeneration(stock, pxl):
    sources = convert.read_sources()
    first = convert.regenerate(stock, pxl, sources)
    second = convert.regenerate(stock, pxl, sources)
    check(first[0] == second[0] and first[2] == second[2], "regeneration is not deterministic")
    outputs, assets, rom, _ = first
    recorded = stage.read_registry()
    check(convert.registry(sources, stock, outputs, rom) == recorded, "data/analysisart32/digests.json is stale")
    check(set(recorded["sources"]) == {f"art/analysisart32/{n}" for n in convert.SOURCES} | {model.PART_MANIFEST},
          "registry sources")
    check(sha256(rom) == TARGET_SHA256 == recorded["rom"], f"the ROM is {sha256(rom)}, not the selected card")
    check(sha256(outputs["render/scenes/card.png"]) == RENDER_SHA256, "the pinned render is not the frozen scene")
    text = (ROOT / "data/analysisart32/digests.json").read_text()
    check(json.dumps(json.loads(text), indent=1) + "\n" == text and str(ROOT) not in text
          and tempfile.gettempdir() not in text and list(recorded["outputs"]) == sorted(recorded["outputs"]),
          "the registry is not sorted, canonical and path-free")
    return outputs, assets, rom, [
        f"regeneration: two in-process runs (four pinned pxl renders) agree on all {len(outputs)} outputs and the ROM; "
        f"the registry is current, canonical and path-free; the render is the frozen scene {RENDER_SHA256[:12]}; the "
        f"ROM is the selected card {TARGET_SHA256}"]


def part_colors(data):
    """Rows of RGB triples of a part PNG, None where clear."""
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    px = image.load()
    return [[px[x, y][:3] if px[x, y][3] else None for x in range(image.width)] for y in range(image.height)]


def test_provenance(rom, outputs, assets):
    """provenance.json against the built ROM's own bytes: every part cell's source tile, map byte, selector bits,
    colors and sprite attribute; every placement tile's id, pattern, palette and decoded part pixels; the socket,
    digit and title tables."""
    record = json.loads(outputs["provenance.json"])
    check(record["base_sha256"] == STOCK_SHA256 and record["rom_sha256"] == sha256(rom), "provenance ROM digests")
    check(record["sources"] == {name: sha256(data) for name, data in sorted(convert.read_sources().items())},
          "provenance sources")
    cells = 0
    for part in record["parts"]:
        check(sha256(outputs[f"parts/{part['id']}.png"]) == part["png_sha256"], f"{part['id']} PNG digest")
        for cell in part["cells"]:
            start = cell["chr_offset"]
            check(start == 16 + 16 * 0x4000 + cell["chr_bank"] * 0x1000 + 16 * cell["tile"]
                  and sha256(rom[start:start + 16]) == cell["tile_sha256"], f"{part['id']} cell {cell['cell']} tile")
            colors = cell["colors_from"]
            if part["source"]["kind"] == "intro-panel":
                tile_from, palette_from = cell["tile_from"], cell["palette_from"]
                check(prg(rom, 5, int(tile_from["address"][1:], 16))[0] == cell["tile"]
                      and prg(rom, 5, int(palette_from["address"][1:], 16))[0] >> palette_from["shift"] & 3
                      == cell["palette"], f"{part['id']} cell {cell['cell']} map or selector byte")
                check(colors["bank"] == 15 and int(colors["address"][1:], 16) == 0xFA61 + 4 * cell["palette"]
                      and cell["oam"]["attribute"] == 0x20 | cell["palette"] and not cell["oam"]["hflip"]
                      and not cell["oam"]["vflip"], f"{part['id']} cell {cell['cell']} colors or attribute")
            else:
                check(colors["bank"] == 15 and int(colors["address"][1:], 16) == 0xF931 + 4 * cell["palette"],
                      f"{part['id']} cell {cell['cell']} stands colors")
            cells += 1
    screen, palette, chr06 = prg(rom, 13, 0xA000, 0x400), prg(rom, 13, 0xA400, 16), chr_bank(rom, 6)
    tiles = pixels = 0
    for placement in record["placements"]:
        part = part_colors(outputs[f"parts/{placement['part']}.png"])
        ax, ay = (placement["area"] or [0, 0])[:2]
        dx, dy = placement["at"][0] - ax, placement["at"][1] - ay
        for tile in placement["tiles"]:
            tx, ty = tile["tile"]
            t = screen[32 * ty + tx]
            check(t == tile["chr_tile"] and cell_palette(screen[960:], tx, ty) == tile["palette"]
                  and sha256(chr06[16 * t:16 * t + 16]) == tile["pattern_sha256"], f"placement tile {tx},{ty}")
            grid = planar(chr06[16 * t:16 * t + 16])
            px, py, w, h = tile["part_rect"]
            count = 0
            for j in range(h):
                for i in range(w):
                    c = part[py + j][px + i]
                    if c is None:
                        continue
                    sx, sy = dx + px + i, dy + py + j
                    check((sx // 8, sy // 8) == (tx, ty), f"placement rect leaves tile {tx},{ty}")
                    v = grid[sy % 8][sx % 8]
                    check(menu.NES_RGB[palette[4 * tile["palette"] + v] if v else palette[0]] == c,
                          f"{placement['part']} pixel ({sx},{sy}) does not decode from ROM tile ${t:02X}")
                    count += 1
            check(count == tile["pixels"], f"placement tile {tx},{ty} pixel count")
            tiles += 1
            pixels += count
    _, _, tables = stage.home_code(assets)
    sockets = record["sockets"]
    check(sockets["ball_y"] == list(prg(rom, 3, tables["pip_y"], 4)) == [8 * r - 1 for r in sockets["rows"]]
          and sockets["ball_x"] == list(prg(rom, 3, tables["pip_x"], 4)) == [8 * c for c in sockets["cols"]]
          and all(screen[32 * r + c] == int(sockets["tile"], 16) for r in sockets["rows"] for c in sockets["cols"]),
          "provenance sockets disagree with the ROM's ball tables or screen")
    addresses = [b << 8 | a for b, a in zip(prg(rom, 3, tables["num_hi"], 4), prg(rom, 3, tables["num_lo"], 4))]
    check([int(d["address"][1:], 16) for d in record["digits"]] == addresses, "provenance digit addresses")
    check([0x60 + t["col"] for t in record["titles"]] == list(prg(rom, 13, 0xA440, 32))
          and [t["flag_x"] for t in record["titles"]] == list(prg(rom, 13, 0xA420, 32)), "provenance title columns")
    return [f"provenance: {cells} part cells name the CHR tile, offset and digest, the map byte, the selector byte and "
            "bit shift, the palette record and an unflipped priority attribute that the ROM holds; "
            f"{tiles} destination tiles of {len(record['placements'])} placements name the ROM's tile id, pattern digest "
            f"and palette, and their {pixels} part pixels decode from those ROM tiles to the part's colors; the socket, "
            "digit and title records equal the ROM's tables"]


def installed_outputs():
    """The installed converter outputs, which must be exactly the registered ones; None when absent."""
    if not stage.ASSETS.exists():
        return None
    registry = stage.read_registry()
    found = {p.relative_to(stage.ASSETS).as_posix(): p.read_bytes() for p in stage.ASSETS.rglob("*") if p.is_file()}
    check({k: sha256(v) for k, v in found.items()} == registry["outputs"],
          f"{stage.ASSETS} does not hold exactly the registered outputs; rerun tools/analysisart32_convert.py")
    return found


def test_converter_controls(stock, render_png):
    """Art and layout errors the converter must refuse, on the pinned render and the tracked layout."""
    sources = convert.read_sources()
    layout, manifest, placements = convert.models(sources)
    cut = parts.cut_parts(stock, manifest)
    outline = model.ball_outline(stock, 0x61)

    def edited(spots):
        image = Image.open(io.BytesIO(render_png)).convert("RGBA")
        for (x, y), c in spots:
            image.putpixel((x, y), menu.NES_RGB[c] + (255,))
        encoded = io.BytesIO()
        image.save(encoded, format="PNG")
        return encoded.getvalue()

    def relaid(mutate):
        data = json.loads(sources["art/analysisart32/layout.json"])
        mutate(data)
        return Layout.parse(data, "0" * 64)

    def socket_at(col, row, draw=True):
        return [((8 * col + x, 8 * row + y), 0x28 if draw and (x, y) in outline else 0x0C) for y in range(8)
                for x in range(8)]
    shifted = [spot for row in (11, 13, 15, 17) for col in (16, 18, 20, 22)
               for spot in socket_at(col, row, False) + socket_at(col + 1, row)]
    rng, noise = random.Random(7), []
    for rows_, cols_, count, color in ((range(20, 25), range(23, 28), 5, 0x0C), (range(9, 12), range(0, 4), 5, 0x0C),
                                       (range(25, 28), range(0, 6), 5, 0x0C), (range(12, 25), range(4, 6), 4, 0x0C)):
        for ty in rows_:
            for tx in cols_:
                noise += [((8 * tx + rng.randrange(8), 8 * ty + rng.randrange(8)), color) for _ in range(count)]
    blank_q = bytearray(stock)
    blank_q[locate("chr", 16 * ord("Q")):locate("chr", 16 * ord("Q")) + 16] = bytes(16)

    def cols(values):
        return lambda d: d["sockets"].update(cols=values)

    def rows(values):
        return lambda d: [entry.update(row=r) for entry, r in zip(d["stats"], values)]
    cases = [
        ("a title cell that is no CHR $18 pattern", "not in CHR $18", stock, layout, edited([((100, 60), 0x28)])),
        ("a cream pixel on the split row", "identical in CHR $18 and CHR $06", stock, layout, edited([((100, 66), 0x38)])),
        ("ink in a label cell", "must be blank in the art", stock, layout, edited([((51, 91), 0x38)])),
        ("ink in a digit cell", "must be blank in the art", stock, layout, edited([((8 * 25 + 3, 8 * 11 + 3), 0x38)])),
        ("ink on a name row", "name rows must be blank", stock, layout, edited([((120, 30), 0x38)])),
        ("red in a sky and gold cell", "fits no allowed palette", stock, layout, edited([((4, 84), 0x16)])),
        ("a tile budget overflow", "CHR $06 is full", stock, layout, edited(noise)),
        ("a missing socket", "no empty ball socket", stock, layout, edited(socket_at(16, 11, False))),
        ("an extra socket", "socket tile exactly", stock, layout, edited(socket_at(24, 11))),
        ("every socket drawn 8 px right", "no empty ball socket", stock, layout, edited(shifted)),
        ("socket columns +1 in the layout only", "no empty ball socket", stock, relaid(cols([17, 19, 21, 23])),
         render_png),
        ("stat rows one lower in the layout only", "must be blank in the art", stock, relaid(rows([12, 14, 16, 18])),
         render_png),
        ("a glyph CHR $00 leaves blank", "is blank, not a glyph", bytes(blank_q),
         relaid(lambda d: d.update(glyphs=["3", "4", "K", "Q"])), render_png),
        ("a glyph the mode font already has", "already CHR $06", stock,
         relaid(lambda d: d.update(glyphs=["3", "4", "K", "1"])), render_png),
        ("a letter neither font has", "no stock glyph for 'K'", stock, relaid(lambda d: d.update(glyphs=["3", "4"])),
         render_png),
    ]
    lines = []
    for label, reason, base, lay, png in cases:
        lines.append(f"{label}: {refused(convert.convert, reason, base, lay, png)[:90]}")
    pixels = convert.scene_rgb(render_png)
    painted = [convert.check_placement(p, cut[p.part], pixels, "the render") for p in placements]
    pair = next(p for p in placements if p.part == "pair")
    check(not any(any(c is not None for c in row) for row in cut["pair"].pixels[:4]),
          "the pair's top rows, under the card ledge, are no longer clear")
    for label, moved in (("the pair stamped 1 px right", replace(pair, at=(57, 156))),
                         ("the pair's counter rows counted visible", replace(pair, visible=(56, 160, 64, 44))),
                         ("the whole pair counted visible", replace(pair, visible=None))):
        reason = refused(convert.check_placement, "differ in the render", moved, cut["pair"], pixels, "the render")
        lines.append(f"{label}: {reason[:70]}")
    return [f"converter controls (pinned render, tracked layout; {sum(painted)} visible part pixels traced in the "
            "render):"] + [f"  refused {line}" for line in lines]


def test_asset_controls(stock, assets):
    """Malformed assets refused by the model, and self-consistent ones the builder refuses against the ROM."""
    record = assets.record()
    nt = assets.nametable

    def rec(**changes):
        bad = copy.deepcopy(record)
        for key, value in changes.items():
            bad[key] = value(bad) if callable(value) else value
        return bad

    def nt_edit(index, tile):
        table = bytearray(nt)
        table[index] = tile
        return table.hex()
    cases = [
        ("an extra key", "exactly the keys", {**record, "extra": 1}),
        ("a short nametable", "960 bytes", rec(nametable=nt[:-1].hex())),
        ("63 attribute bytes", "64 bytes", rec(attributes=assets.attributes[:-1].hex())),
        ("two backdrops", "one backdrop", rec(palette=(assets.palette[:4] + b"\x0F" + assets.palette[5:]).hex())),
        ("color $0D", "supported NES colors", rec(palette=(assets.palette[:1] + b"\x0D" + assets.palette[2:]).hex())),
        ("new tile id $B9", "free CHR $06 range", rec(new_tiles=lambda b: {"B9": b["new_tiles"]["BA"], **b["new_tiles"]})),
        ("a blank new tile", "non-blank", rec(new_tiles=lambda b: {**b["new_tiles"], "F0": "00" * 16})),
        ("a repeated pattern", "distinct", rec(new_tiles=lambda b: {**b["new_tiles"], "F0": b["new_tiles"]["BA"]})),
        ("a glyph outside the new tiles", "distinct new tile ids", rec(glyphs=lambda b: {**b["glyphs"], "K": "4B"})),
        ("digit 3 at the art id $33", "glyph ids of 1, 2, 3 and 4", rec(digits=["31", "32", "33", "BB"])),
        ("reordered stats", "stored order", rec(stats=lambda b: [b["stats"][1], b["stats"][0], *b["stats"][2:]])),
        ("a stat on the split row", "below the split", rec(stats=lambda b: [{**b["stats"][0], "row": 8}, *b["stats"][1:]])),
        ("three socket columns", "four ascending", rec(socket_cols=[16, 18, 20])),
        ("socket columns +1, nametable unchanged", "exactly at the 16 socket cells", rec(socket_cols=[17, 19, 21, 23])),
        ("a socket tile elsewhere", "exactly at the 16 socket cells", rec(nametable=nt_edit(32 * 12 + 16,
                                                                                            assets.socket_tile))),
        ("a wrong label glyph", "must show 'B'", rec(nametable=nt_edit(32 * 11 + 6, 0x41))),
        ("a drawn digit cell", "digit cells must stay blank", rec(nametable=nt_edit(32 * 11 + 25, 0x31))),
        ("ink on a name row", "name rows must stay blank", rec(nametable=nt_edit(32 * 3 + 5, 0xE0))),
        ("an unlisted split id", "only split_ids", rec(nametable=nt_edit(32 * 8 + 3, 0xE9))),
        ("an undefined new id", "undefined CHR $06 ids", rec(nametable=nt_edit(32 * 20 + 2, 0xF7))),
        ("a title cell off the title palette", "title palette", rec(attributes=(b"\x00" + assets.attributes[1:]).hex())),
        ("ball palette 0", "sprite palette 1-3", rec(ball=lambda b: {**b["ball"], "sprite_palette": 0})),
        ("a flag below the title band", "above the split", rec(flag_y=48)),
        ("one paced NMI", "paced NMIs", rec(pace_nmis=1)),
        ("text over a label", "overlaps", rec(text=[{"row": 11, "col": 7, "text": "X"}])),
    ]
    check(AnalysisAssets.parse(json.loads(assets.dumps())) == assets, "the assets do not round-trip")
    for label, reason, bad in cases:
        try:
            AnalysisAssets.parse(bad)
        except AssetError as exc:
            check(reason in str(exc), f"assets {label}: refused for another reason: {exc}")
            continue
        raise Failure(f"the asset boundary accepted {label}")
    tiles = dict(assets.new_tiles)

    def flipped(tile, i, bit=1):
        return {**tiles, tile: tiles[tile][:i] + bytes((tiles[tile][i] ^ bit,)) + tiles[tile][i + 1:]}
    runtime = [
        ("a glyph bit flipped", "CHR $00 glyph", replace(assets, new_tiles=flipped(0xBA, 3))),
        ("an inked pixel inside the socket", "outline of ball sprite",
         replace(assets, new_tiles=flipped(assets.socket_tile, 2, 0x02))),
        ("a split pattern bit flipped", "differs between CHR $06 and CHR $18", replace(assets, new_tiles=flipped(0xE0, 0))),
        ("the ball on flag palette 2", "colors a flag", replace(assets, ball_palette=2)),
        ("a new tile repeating a mode pattern", "repeats a stockart32 mode pattern",
         replace(assets, new_tiles={**tiles, 0xBD: chr_bank(stock, 6)[16 * 0x50:16 * 0x51]})),
        ("another ball sprite", "outline of ball sprite", replace(assets, ball_tile=0xFE)),
    ]
    for label, reason, bad in runtime:
        refused(stage.build_rom, reason, stock, bad)
    return [f"assets: analysisassets/1 round-trips; {len(cases)} malformed records (keys, sizes, palettes, low, blank or "
            "repeated new tiles, glyph and digit ids, stat order and rows, socket count, columns and cells, label, "
            "digit, name-row, split-row and undefined ids, title palette, ball palette, flag row, pacing, text "
            f"overlap) are refused by the model; {len(runtime)} self-consistent assets the input ROM contradicts (glyph, "
            "socket and split patterns, the ball on a flag palette, a repeated mode pattern, another ball sprite) are "
            "refused by the builder"]


def test_stage(stock, rom, assets):
    check(stage.build_rom(stock, assets) == rom == stage.build_rom(stock, assets), "build_rom is not pure")
    check(tuple((r.name, r.bank, r.start, r.end - 1) for r in stage.REGIONS) == REGIONS,
          "the builder's regions are not the judged reservation")
    owned = set()
    for name, bank, start, end in REGIONS:
        owned |= set(range(locate(bank, start), locate(bank, end) + 1))
    changed = {i for i, (a, b) in enumerate(zip(stock, rom)) if a != b}
    check(len(rom) == len(stock) and rom[:16] == stock[:16], "size or header changed")
    check(len(owned) == CLAIMED and changed <= owned and len(changed) == CHANGED,
          f"{len(changed)} bytes changed, {len(changed - owned)} outside {len(owned)} claimed")
    counts = {name: sum(1 for i in changed if locate(bank, start) <= i <= locate(bank, end))
              for name, bank, start, end in REGIONS}
    check(counts == REGION_CHANGES, f"per-region changes {counts}")
    for bank in range(16):
        if bank not in (3, 13):
            origin = 0xC000 if bank == 15 else 0x8000
            check(prg(rom, bank, origin, 0x4000) == prg(stock, bank, origin, 0x4000), f"PRG bank {bank} changed")
    for bank in range(32):
        if bank != 6:
            check(chr_bank(rom, bank) == chr_bank(stock, bank), f"CHR ${bank:02X} changed")
    new = [t for t in range(256) if chr_bank(rom, 6)[16 * t:16 * t + 16] != chr_bank(stock, 6)[16 * t:16 * t + 16]]
    check(tuple(new) == NEW_TILES and chr_bank(rom, 6)[:16 * 0xBA] == chr_bank(stock, 6)[:16 * 0xBA],
          f"new CHR $06 tiles {[f'{t:02X}' for t in new]}")
    check(not any(any(chr_bank(rom, 6)[16 * t:16 * t + 16]) for t in range(0xBA, 0x100) if t not in NEW_TILES),
          "an unused CHR $06 pattern is not blank")
    check(prg(rom, 3, 0xBC80, 0xA0) == prg(stock, 3, 0xBC80, 0xA0), "ratings or batting bias changed")
    check(prg(rom, 13, 0x8000, 0x2000) == prg(stock, 13, 0x8000, 0x2000), "bank 13 $8000-$9FFF changed")
    check(prg(rom, 3, 0xBD20, 16) == prg(rom, 13, 0xBD20, 16), "the hop pads differ")
    report = stage.diff_manifest(stock, rom, assets)
    check(report["changed_bytes"] == CHANGED and report["claimed_bytes"] == CLAIMED
          and {r["name"]: len(r["changed_file_offsets"]) for r in report["regions"]} == REGION_CHANGES
          and {i for r in report["regions"] for i in r["changed_file_offsets"]} == changed
          and all(bytes.fromhex(r["before"]) == stock[r["file_offset"]:r["file_offset"] + r["size"]]
                  and bytes.fromhex(r["after"]) == rom[r["file_offset"]:r["file_offset"] + r["size"]]
                  for r in report["regions"]), "the before/after manifest is not exact")
    guards = [(label, bank, addr + len(bytes.fromhex(text)) // 2) for label, bank, addr, text in stage.DEPENDENCIES]
    guards += [(label, bank, addr + size // 2) for label, bank, addr, size, _ in stage.DIGESTS]
    guards += [(r.name, r.bank, (r.start + r.end) // 2) for r in stage.REGIONS]
    guards += [("NMI short path store $CD8C", 15, 0xCD8C), ("consumer clear $CC20", 15, 0xCC20),
               ("PRG writer $C14E", 15, 0xC14E), ("ratings reader $AFE3", 3, 0xAFE3),
               ("CHR $18 first byte", "chr", 0x18000), ("flag pointer $975A", 4, 0x975A),
               ("flag attribute $976B", 4, 0x976B), ("ball tile", "chr", 0x1B000 + 16 * 0x61 + 3),
               ("mode tile $B9", "chr", 0x6000 + 16 * 0xB9 + 5), ("bank 13 pad", 13, 0xBD25),
               ("bank 3 free run", 3, 0xBD50), ("bank 13 card region", 13, 0xA123), ("CHR $06 new region", "chr", 0x6C00),
               ("a rating", 3, 0xBC80 + 4 * 9 + 1)]
    for label, bank, address in guards:
        drifted = bytearray(stock)
        drifted[locate(bank, address)] ^= 1
        with patch.object(stage, "BASE_SHA256", sha256(drifted)):
            try:
                stage.build_rom(bytes(drifted), assets)
            except (ValueError, KeyError):
                continue
        raise Failure(f"{label}: a one-bit drift at {address:04X} was not refused")
    no_pin = tuple(d for d in stage.DIGESTS if "ratings" not in d[0])
    for value in (0, 5):
        bad = bytearray(stock)
        bad[locate(3, 0xBC80 + 4 * 3)] = value
        with patch.object(stage, "BASE_SHA256", sha256(bad)), patch.object(stage, "DIGESTS", no_pin):
            refused(stage.build_rom, "leave 1..4", bytes(bad), assets)
    other = bytearray(stock)
    other[locate(9, 0x8000)] ^= 1
    refused(stage.build_rom, "does not match pinned stockart32", bytes(other), assets)
    refused(stage.build_rom, "ROM size and iNES header", stock[:-1], assets)
    refused(stage.build_rom, "ROM size and iNES header", stock + b"\xFF", assets)
    changes = stage.change_manifest(stock, assets)
    first = changes[0]
    tampered = (changes + (first,), changes[1:], (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=first.addr + 1),) + changes[1:], (replace(first, bank=9),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=bytes(len(first.before))),) + changes[1:])
    for bad in tampered:
        with patch.object(stage, "change_manifest", return_value=bad):
            try:
                stage.build_rom(stock, assets)
            except ValueError:
                continue
        raise Failure("a tampered change manifest was accepted")
    pads = tuple(replace(c, after=c.after[:-1] + b"\x00") if c.name == "far-pad" else c for c in changes)
    with patch.object(stage, "change_manifest", return_value=pads):
        refused(stage.build_rom, "hop pads differ", stock, assets)
    with patch.object(stage, "FAR_END", stage.FAR_CODE + 0x60):
        refused(stage.build_rom, "card() is", stock, assets)
    with patch.object(stage, "HOME_END", stage.HOME_CODE + 0x60):
        refused(stage.build_rom, "the bank-3 block is", stock, assets)
    return [f"stage: build_rom is pure and gives the candidate; the nine regions are the judged reservation ({CLAIMED} "
            f"bytes claimed); exactly {CHANGED} bytes change ({', '.join(f'{k} {v}' for k, v in REGION_CHANGES.items())});"
            " header, size, every other PRG and CHR bank, CHR $06 $00-$B9, the ratings and batting bias and bank 13 "
            f"$8000-$9FFF are unchanged; new CHR $06 tiles {' '.join(f'${t:02X}' for t in NEW_TILES)} leave 59 blank; "
            f"the before/after manifest is exact; {len(guards)} one-bit drifts (every dependency, digest and region, the "
            "NMI latch store and consumer, $C14E, the reader, a flag pointer and attribute, the ball tile, a mode tile, "
            "the pads, a rating), ratings 0 and 5 without the ratings pin, another ROM, wrong sizes, "
            f"{len(tampered)} tampered change manifests, unequal pads and card or bank-3 code overflowing its region are "
            "refused"]


def test_static(ctx, rom):
    """Split, flag, title-band, mode-ownership and leave-state invariants read from ROM bytes."""
    nt = prg(rom, 13, 0xA000, 0x400)
    chr18, chr06, chr1b = chr_bank(rom, 0x18), chr_bank(rom, 6), chr_bank(rom, 0x1B)
    check(prg(rom, 15, 0xC6E8, 15) == bytes.fromhex("A9 FE 8D 01 02 A9 20 8D 02 02 A9 F8 8D 03 02"),
          "$C6C1 no longer places sprite 0 as tile $FE, priority, x $F8")
    check(prg(rom, 15, 0xFB59, 6) == bytes.fromhex("06 1B 1B 18 18 40"), "CHR preset 2 record")
    y0 = prg(rom, 15, 0xFB59, 6)[5]
    sprite = planar(chr1b[16 * 0xFE:16 * 0xFF])
    hits = []
    for dy in range(8):
        for dx in range(8):
            x, y = 0xF8 + dx, y0 + 1 + dy
            tile = nt[32 * (y // 8) + x // 8]
            if sprite[dy][dx] and x < 255 and planar(chr18[16 * tile:16 * tile + 16])[y % 8][x % 8]:
                hits.append((x, y))
    check(hits and min(y for _, y in hits) // 8 == model.SPLIT_ROW, f"sprite 0 hits {hits}")
    row8 = set(nt[32 * 8:32 * 9])
    check(all(chr18[16 * t:16 * t + 16] == chr06[16 * t:16 * t + 16] for t in row8), "split row patterns differ")
    check(all(nt[32 * r + c] == TITLE_TEMPLATE[r] for r in range(8) for c in range(32)),
          "the uploaded title band is not the accepted template")
    palette = prg(rom, 13, 0xA400, 16)
    for r in range(8):
        tile = TITLE_TEMPLATE[r]
        grid = planar(chr18[16 * tile:16 * tile + 16])
        want = [[menu.NES_RGB[palette[12 + v] if v else palette[0]] for v in line] for line in grid]
        for c in range(32):
            check(cell_palette(nt[960:], c, r) == 3, f"title cell row {r} col {c} is not on palette 3")
            check([ctx.render[8 * r + y][8 * c:8 * c + 8] for y in range(8)] == want,
                  f"the pinned render's title cell row {r} col {c} is not CHR $18 ${tile:02X}")
    selectors = prg(rom, 4, 0x975A, 16)
    palettes = sorted({prg(rom, 4, 0x976B + p + 2 * k)[0] & 3 for p in selectors for k in range(9)})
    check(palettes == [0, 2, 3], f"flag sprite palettes {palettes}")
    check(any(chr1b[16 * 0x61:16 * 0x62]), "the ball tile is blank")
    lines = [f"split: stock sprite 0 {SPRITE0.hex(' ').upper()} first hits opaque CHR $18 at {hits[:2]} (x < 255) on "
             f"row 8, whose ids {' '.join(f'${t:02X}' for t in sorted(row8))} are identical in CHR $18 and CHR $06; the "
             f"16 flags use sprite palettes {palettes}, so the ball's palette 1 is unshared",
             "title band: the uploaded rows 0-7 are the accepted template (sky $E0, rails $E9 on rows 1 and 6, blank "
             "name rows, palette 3), and the pinned render's rows 0-63 decode to exactly those CHR $18 patterns"]
    used = model.mode_screen_ids(rom)
    check(used == set(range(0xBA)), f"the mode screen shows ids up to ${max(used):02X}")
    mode_json = ROOT / "build/stockart32/modeassets.json"
    if mode_json.is_file():
        from modeart32_assets import ModeAssets
        approved = json.loads((ROOT / "data/stockart32/digests.json").read_text())["outputs"]["modeassets.json"]
        check(sha256(mode_json.read_bytes()) == approved, "build/stockart32/modeassets.json is not the approved asset")
        mode = ModeAssets.load(mode_json)
        union = set(mode.nametable) | set(mode.font_glyphs) | {t for m in mode.menus for run in m.tiles for t in run}
        check(union == used and prg(rom, 13, 0x9000, 0x400) == mode.nametable + mode.attributes,
              "the approved mode asset disagrees with the ROM's mode screen")
        lines.append("mode screen: its nametable, font glyphs and all three menus' run lists use exactly CHR $06 "
                     "$00-$B9, read from the ROM and from the approved build/stockart32/modeassets.json alike")
    else:
        lines.append("mode screen: its nametable and all three run lists, read from the ROM, use exactly CHR $06 "
                     "$00-$B9 (approved build/stockart32/modeassets.json not installed: cross-check skipped)")
    for preset in range(9):
        record = prg(rom, 15, 0xFB4D + 6 * preset, 6)
        check(not record[0] & 2 or not record[3] & 0x80, f"CHR preset {preset} reloads CHR1 without setting $26")
    check(prg(rom, 15, 0xCE39, 12) == bytes.fromhex("AD 7A 04 29 02 F0 1D A5 26 4C 34 C1"), "the NMI CHR1 reload moved")
    lines.append("leave state: the card leaves $26 = $06; the NMI reads $26 only at $CE40 behind $047A bit 1, and every "
                 "CHR preset 0-8 that sets the bit also rewrites $26 (source bytes pinned here; other readers/setters "
                 "were audited separately, not scanned by this test)")
    return lines


def test_runtime(ctx, rom, tours, stock_tours):
    problems = judge_tours(ctx, rom, tours, stock_tours)
    check(not problems, "; ".join(problems[:8]) + (f" (+{len(problems) - 8} more)" if len(problems) > 8 else ""))
    visits = [v for t in tours for v in t["visits"]]
    releases = sorted({v["marks"]["AF94"][0] - v["marks"]["AF80"][0] for v in visits})
    return [f"tours: {len(visits)} controller-driven visits from RESET ({len(tours)} tours, exits alternating A and B) "
            "match stockart32 frame for frame: per-frame scene, state and $BC-$BF, the handler timeline, release "
            f"{releases} frames after the prologue's vblank, every APU write, the $35 confirm, the return to the same "
            "picker cell, the active v2 series heap, seed, markers and mask, the picker and mode menu after the card "
            "(but $26), and RAM and WRAM after the return outside the reviewed scratch list",
            f"cards: on every visit the four stock labels and {HINT!r} are CHR $00 glyphs on blank render cells inside "
            "the 224-line crop; the rest of rows 9-29 equals the pinned render pixel for pixel; each label row holds 4 "
            "sockets found in the decoded background; the rating's balls fill its first sockets and its digit shows the "
            "rating; every count-up frame shows exactly $BC-$BF balls; all 16 sockets hold a ball on some visit; the "
            "title band is the stock writer's cells inside its writes and the accepted template outside; the flag is "
            "the stock writer's nine sprites; name and flag center within 4 px; shadows 1B 1B 18 06, split mode $06, "
            "sprite 0 40 FE 20 F8; CHR1 loads $18 then $06 each frame, inside the split row"]


def test_timing(timing, stock_timing):
    problems = []
    for case, stock_case in zip(timing, stock_timing):
        tag = f"team {case['team']} lead {case['lead']} {'A held, ' if case['held'] else ''}exit {case['key']}"
        for key in ("scene15", "timeline", "apu"):
            if case[key] != stock_case[key]:
                problems.append(f"{tag}: {key} differs from stock")
        release = [c["marks"]["AF94"] - c["marks"]["AF80"] for c in (case, stock_case)]
        if release[0] != release[1]:
            problems.append(f"{tag}: release {release[0]} frames, stock {release[1]}")
        s = case["settled"]
        if (not case["held_stays"] or s["guards"] != (0, 0, 0, 0) or (s["physical"], s["logical"]) != (3, 3)
                or s["sp"] != 0xFD or s["serial"][1]):
            problems.append(f"{tag}: held A {case['held_stays']}, settled guards {s['guards']}, bank {s['physical']}/"
                            f"{s['logical']}, SP {s['sp']:02X}, serial {s['serial']}")
        if case["cursor"] != case["team"] or not case["series_ok"] or case["late_ppu"]:
            problems.append(f"{tag}: return {case['cursor']}, series {case['series_ok']}, late writes {case['late_ppu']}")
    check(not problems, "; ".join(problems[:6]))
    lines = [(off - R.VBLANK) / (341 / 3) for case in timing for _, off, _, _, v in case["split_commits"] if v == 6]
    return [f"timing: {len(timing)} RESET-ancestry fixtures (team 31 at vblank leads "
            f"{sorted({c['lead'] for c in timing if c['team'] == 31})} cycles with A held from entry, other teams at "
            "lead 0) match stockart32's scene-$15 frame, release frame, handler timeline and every frame-stamped APU "
            "write through the return; held A never exits early; $2C $2D $AC $32 clear, PRG 3 physical and logical, "
            f"MMC1 serial count 0 and SP $FD before the exit; {len(lines)} CHR1 $06 loads land on model lines "
            f"{min(lines):.2f}-{max(lines):.2f}"]


def test_injection(results):
    lines, total = [], 0
    for team, (reference, runs) in results:
        check(reference["guards"] == (0, 0, 0, 0) and (reference["physical"], reference["logical"]) == (3, 3)
              and reference["serial"][1] == 0 and reference["sp"] == 0xFD, f"team {team} reference {reference}")
        bad = [f"{name}: never reached" if fired is None else
               f"{name}: {sorted(k for k in state if state[k] != reference[k])} differ"
               for name, state, fired in runs if fired is None or state != reference]
        check(not bad, f"team {team}: " + "; ".join(bad[:6]))
        sites = {(f["exec_bank"], f["pc"]) for _, _, f in runs}
        early = sum(1 for _, _, f in runs if f["physical"] != f["logical"])
        partial = sum(1 for _, _, f in runs if f["serial_count"])
        total += len(runs)
        lines.append(f"  team {team}: {len(runs)} NMIs at {len(sites)} sites, {early} with logical $27 ahead of the "
                     f"physical bank, {partial} mid-serial")
    return [f"NMI injection: {total} extra NMIs (the hop pads, card entry, numerals and balls, every bank switch's $27 "
            "store, guard and serial bits, sampled init and ball instructions) each settle to the uninjected screen, "
            "SP, physical and logical PRG, MMC1 shift and count, control and CHR, guards $2C $2D $AC $32 and the "
            "active series (final-state robustness, not transient-frame or audio parity)"] + lines


def test_screens(stock_screens, screens):
    differing = {name: sorted(k for k in stock_screens[name] if stock_screens[name][k] != screens[name][k])
                 for name in stock_screens if name != "series intact"}
    after = {n: d for n, d in differing.items() if "after" in n}
    before = {n: d for n, d in differing.items() if "after" not in n}
    check(all(not d for d in before.values()) and all(d in ([], ["shadows"]) for d in after.values())
          and screens["series intact"] and stock_screens["series intact"], f"protected screens differ: {differing}")
    return [f"protected screens: {', '.join(before)} equal stockart32 in VRAM, palette, OAM, CHR, PPU control, shadows "
            f"and split mode; after a card visit, {', '.join(after)} equal it but for the $26 shadow; series intact"]



@contextmanager
def checkout(stock_path):
    """A scratch copy of tools, art and data with the input ROM in its build/, a docs stub and earlier evidence."""
    with tempfile.TemporaryDirectory(prefix="analysisart32-test-") as temporary:
        scratch = Path(temporary).resolve()
        repo = scratch / "repo"
        for name in ("tools", "art", "data"):
            shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        (repo / "docs").mkdir()
        (repo / "docs/notes.md").write_text("docs stay intact\n")
        (repo / "build/stockart32").mkdir(parents=True)
        (repo / "build/stockart32/evidence.json").write_text("earlier stage output\n")
        (repo / "build/analysisart32-design").mkdir()
        (repo / "build/analysisart32-design/grounding.md").write_text("root evidence\n")
        shutil.copyfile(stock_path, repo / "build/stockart32.nes")
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
    return line.split(": ", 1)[-1][:110]


def outputs_match(out, registry):
    found = {p.relative_to(out).as_posix(): sha256(p.read_bytes()) for p in out.rglob("*") if p.is_file()}
    return found == registry["outputs"]


def install(repo, outputs):
    for relative, data in outputs.items():
        target = repo / "build/analysisart32" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_convert_cli(repo, elsewhere, pxl):
    tools, rom_path = repo / "tools", repo / "build/stockart32.nes"
    original_rom = rom_path.read_bytes()
    cli = [sys.executable, "-B", str(tools / "analysisart32_convert.py"), "--rom", str(rom_path), "--pxl", str(pxl)]
    out, registry_path = repo / "build/analysisart32", repo / "data/analysisart32/digests.json"
    registry = json.loads(registry_path.read_text())
    before = snapshot(repo, elsewhere)
    check("nothing written" in ok(run(cli + ["--check"], elsewhere)).stdout, "--check output")
    check(snapshot(repo, elsewhere) == before and not out.exists(), "--check wrote a file")
    ok(run(cli, elsewhere))
    check(outputs_match(out, registry), "regeneration from another directory differs from the registry")
    installed = snapshot(repo)
    ok(run(cli, elsewhere))
    check(snapshot(repo) == installed, "a repeated regeneration rewrote a file")
    ok(run(cli + ["--check"], elsewhere))
    check(snapshot(repo) == installed, "--check after installing wrote a file")
    for temp_root in dict.fromkeys([tempfile.gettempdir()] + (["/tmp"] if sys.platform == "darwin" else [])):
        with tempfile.TemporaryDirectory(dir=temp_root, prefix="analysisart32-output-") as temporary:
            destination = Path(temporary) / "new-output"
            ok(run(cli + ["--out", str(destination)], elsewhere))
            check(outputs_match(destination, registry), f"natural temp output failed: {destination}")

    fake = elsewhere / "fake-pxl"
    fake.mkdir()
    (elsewhere / "plain-file").write_text("a file")
    safe = elsewhere / "real-out"
    safe.mkdir()
    (safe / "existing").mkdir()
    (elsewhere / "linked-out").symlink_to(safe)
    (elsewhere / "linked-art").symlink_to(repo / "art/analysisart32")
    stray = elsewhere / "stray"
    stray.mkdir()
    (stray / "notes.txt").write_text("not ours")

    def staged(label, build):
        directory = elsewhere / label
        directory.mkdir()
        build(directory)
        return directory

    def part_link(d):
        (d / "parts").mkdir()
        (d / "parts/pair.png").symlink_to(registry_path)
    hostile = [
        ("--out in tracked art", repo / "art/analysisart32/generated", "output aliases protected"),
        ("--out in data", repo / "data/analysisart32/generated", "output aliases protected"),
        ("--out as the registry's directory", repo / "data/analysisart32", "output aliases protected"),
        ("--out in tools", repo / "tools/generated", "output aliases protected"),
        ("--out as docs", repo / "docs", "output aliases protected"),
        ("--out as the repository", repo, "output aliases protected"),
        ("--out inside an earlier stage's outputs", repo / "build/stockart32/analysis", "output aliases protected"),
        ("--out inside root's design evidence", repo / "build/analysisart32-design/out", "output aliases protected"),
        ("--out linked into tracked art", elsewhere / "linked-art", "output aliases protected"),
        ("--out under a link into tracked art", elsewhere / "linked-art/generated", "symbolic link ancestor"),
        ("--out as a linked directory", elsewhere / "linked-out", "output aliases protected"),
        ("--out missing beneath a linked ancestor", elsewhere / "linked-out/new-output", "symbolic link ancestor"),
        ("--out existing beneath a linked ancestor", elsewhere / "linked-out/existing", "symbolic link ancestor"),
        ("--out holding another file", stray, "does not write"),
        ("--out as a file", elsewhere / "plain-file", "not a directory"),
        ("--out as build/", repo / "build", "does not write"),
        ("a linked parts directory", staged("linked-parts", lambda d: (d / "parts").symlink_to(safe)),
         "symbolic link ancestor"),
        ("a planned render under a linked directory", staged("linked-render", lambda d: (d / "render").symlink_to(safe)),
         "symbolic link ancestor"),
        ("a planned render directory that is a file", staged("render-file", lambda d: (d / "render").write_text("x")),
         "not a directory"),
        ("the asset JSON as a symlink to the input ROM",
         staged("asset-symlink", lambda d: (d / stage.ASSET_JSON).symlink_to(rom_path)), "output aliases protected"),
        ("the asset JSON as a hardlink to the input ROM",
         staged("asset-hardlink", lambda d: os.link(rom_path, d / stage.ASSET_JSON)), "output aliases protected"),
        ("provenance as a hardlink to placements.json", staged("provenance-hardlink", lambda d: os.link(
            repo / "art/analysisart32/placements.json", d / "provenance.json")), "output aliases protected"),
        ("a part as a symlink to the registry", staged("part-symlink", part_link), "output aliases protected"),
        ("the preview as a directory", staged("preview-dir", lambda d: (d / "preview.png").mkdir()),
         "output aliases protected"),
        ("provenance as a FIFO", staged("fifo", lambda d: os.mkfifo(d / "provenance.json")), "output aliases protected"),
        ("a planned PNG name in another case", staged("casefold", lambda d: (d / "PREVIEW.png").write_bytes(b"x")),
         "folds onto a planned name"),
        ("a parts directory in another case", staged("casefold-parts", lambda d: (d / "Parts").mkdir()),
         "folds onto a planned name"),
        ("--out inside the pxl checkout", fake / "out", "output aliases protected"),
    ]
    lines = []
    for label, target, reason in hostile:
        extra = ["--out", str(target)] + (["--pxl", str(fake)] if "pxl checkout" in label else [])
        before = snapshot(repo, elsewhere)
        lines.append(f"{label}: {failed(run(cli + extra, elsewhere), reason)}")
        check(snapshot(repo, elsewhere) == before, f"{label}: a refused run changed a file")
    lines.append("--check with --record: " + failed(run(cli + ["--check", "--record"], elsewhere), "drop --record"))
    for link in ("symlink", "hardlink"):
        original = registry_path.read_bytes()
        registry_path.unlink()
        moved = elsewhere / "registry-target.json"
        moved.write_bytes(original)
        registry_path.symlink_to(moved) if link == "symlink" else os.link(moved, registry_path)
        before = snapshot(repo, elsewhere)
        lines.append(f"a {link}ed registry under --record: " + failed(run(cli + ["--record"], elsewhere),
                                                                      "output aliases protected"))
        check(snapshot(repo, elsewhere) == before, "a refused --record changed a file")
        registry_path.unlink()
        moved.unlink()
        registry_path.write_bytes(original)

    def attempt(label, path, change, reason, *extra):
        original = path.read_bytes()
        path.write_bytes(change(original))
        before = snapshot(repo, elsewhere)
        line = failed(run(cli + list(extra), elsewhere), reason)
        check(snapshot(repo, elsewhere) == before, f"{label}: a failed run changed a file")
        path.write_bytes(original)
        lines.append(f"{label}: {line}")
    layout_path, source_path = repo / "art/analysisart32/layout.json", repo / "art/analysisart32/card32.px.js"
    attempt("socket columns +1 in the layout", layout_path,
            lambda d: d.replace(b'"cols": [16, 18, 20, 22]', b'"cols": [17, 19, 21, 23]'), "no empty ball socket")
    attempt("the pair moved in placements.json", repo / "art/analysisart32/placements.json",
            lambda d: d.replace(b'"at": [56, 156]', b'"at": [57, 156]'), "differ in the render")
    attempt("broken pxl source", source_path, lambda d: d + b"\nthis is not javascript (\n", "pxl could not build")
    attempt("an unsupported layout color", layout_path, lambda d: d.replace(b'"16", "38", "36"', b'"16", "38", "0D"'),
            "unsupported NES color")
    attempt("another pxl commit", repo / "art/analysisart32/PXL.json",
            lambda d: d.replace(b"3bc816cb15a14592e0dc062ee98013637d399457", b"0" * 40), "not the pinned")
    windows = b'c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "c")'
    gold = b'c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "y")'
    check(source_path.read_bytes().count(windows) == 1, "the light-tower window line moved")
    attempt("an art edit without --record", source_path, lambda d: d.replace(windows, gold),
            "differs from data/analysisart32/digests.json")
    attempt("an art edit under --check", source_path, lambda d: d.replace(windows, gold),
            "differs from data/analysisart32/digests.json", "--check")
    attempt("an unapproved pair part", repo / "data/stockart32/digests.json",
            lambda d: d.replace(b"a8c73eb5b6ed4a09f506a5a4eccba9c3a62b6744936a3d5349dc917b4587ec2f", b"0" * 64),
            "differs from the approved stockart32 part")

    def without_pair_ink(data):
        record = json.loads(data)
        entry = next(c for c in record["characters"] if c["id"] == "pair")
        entry.pop("ink_keep")
        entry.pop("ink_keep_why")
        return json.dumps(record).encode()
    attempt("the pair without its reviewed ink", repo / "art/stockart32/characters.json", without_pair_ink,
            "reviewed mask_sha256")
    drifted = elsewhere / "drifted.nes"
    data = bytearray(original_rom)
    data[locate("chr", 0x14000 + 0x123)] ^= 1
    drifted.write_bytes(data)
    lines.append("a drifted CHR $14 input: " + failed(run(cli[:4] + [str(drifted)] + cli[5:], elsewhere),
                                                      "--rom must be the pinned stockart32"))
    original_registry = registry_path.read_bytes()
    source_path.write_bytes(source_path.read_bytes().replace(windows, gold))
    ok(run(cli + ["--record"], elsewhere))
    edited = json.loads(registry_path.read_text())
    check(edited["rom"] != TARGET_SHA256 and outputs_match(out, edited), "--record did not accept the art edit")
    builder = [sys.executable, "-B", str(tools / "build_analysisart32.py"), str(rom_path)]
    ok(run(builder + ["-o", str(elsewhere / "edited.nes")], elsewhere))
    check(sha256((elsewhere / "edited.nes").read_bytes()) == edited["rom"], "the builder did not follow the record")
    source_path.write_bytes(source_path.read_bytes().replace(gold, windows))
    ok(run(cli + ["--record"], elsewhere))
    check(registry_path.read_bytes() == original_registry and outputs_match(out, registry),
          "recording the restored art did not give back the tracked registry")
    check(rom_path.read_bytes() == original_rom, "the input ROM changed")
    return [f"convert CLI (scratch checkout): --check regenerates and writes nothing; a run from another directory "
            "installs exactly the registered outputs and a repeat rewrites nothing; "
            f"{len(hostile) + 1} hostile outputs and both linked registries are refused before any write with every "
            "file unchanged; failing sources, pins, parts, masks and inputs are refused unchanged; --record accepts "
            "an art edit, the builder follows it, and recording the restored art gives back the tracked registry"] + \
        [f"  refused {line}" for line in lines]


def test_builder_cli(repo, elsewhere, stock, rom, assets):
    tools, rom_path, out = repo / "tools", repo / "build/stockart32.nes", repo / "build/analysisart32"
    sources = [tools / n for n in ("build_analysisart32.py", "analysisart32_convert.py", "analysisart32_assets.py",
                                   "test_analysisart32.py", "build_stockart32.py")]
    sources += [repo / "art/analysisart32/layout.json", repo / "art/analysisart32/card32.px.js",
                repo / "data/analysisart32/digests.json", repo / "data/stockart32/digests.json", repo / "docs/notes.md",
                out / stage.ASSET_JSON, repo / "build/stockart32/evidence.json"]
    count = check_output_guards(tools / "build_analysisart32.py", rom_path, rom, stage.diff_manifest(stock, rom, assets),
                                sources)
    cli = [sys.executable, "-B", str(tools / "build_analysisart32.py"), str(rom_path)]
    canonical = repo / "build/analysisart32.nes"
    result = ok(run(cli + ["-o", str(canonical)], elsewhere))
    check(canonical.read_bytes() == rom and TARGET_SHA256 in result.stdout, "canonical build")
    for temp_root in dict.fromkeys([tempfile.gettempdir()] + (["/tmp"] if sys.platform == "darwin" else [])):
        with tempfile.TemporaryDirectory(dir=temp_root, prefix="analysisart32-build-") as temporary:
            destination = Path(temporary) / "candidate.nes"
            ok(run(cli + ["-o", str(destination)], elsewhere))
            check(destination.read_bytes() == rom, f"natural temp build failed: {destination}")
    linked_art = elsewhere / "builder-linked-art"
    linked_art.symlink_to(repo / "art/analysisart32")
    before = snapshot(repo, elsewhere)
    failed(run(cli + ["-o", str(linked_art / "new.nes")], elsewhere), "symbolic link ancestor")
    check(snapshot(repo, elsewhere) == before, "builder followed an ancestor link into art")
    copied = elsewhere / "assets"
    shutil.copytree(out, copied)
    record = json.loads((copied / stage.ASSET_JSON).read_text())
    record["flag_y"] += 1
    (copied / stage.ASSET_JSON).write_text(json.dumps(record))
    never = elsewhere / "never.nes"
    before = snapshot(repo, elsewhere)
    lines = [failed(run(cli + ["-o", str(never), "--assets", str(copied)], elsewhere), "digests.json")]
    lines.append(failed(run(cli + ["-o", str(out / "inside.nes")], elsewhere), "output aliases protected"))
    lines.append(failed(run(cli + ["-o", str(repo / "build/stockart32/x.nes")], elsewhere), "output aliases protected"))
    lines.append(failed(run(cli + ["-o", str(repo / "build/analysisart32-design/x.nes")], elsewhere),
                        "output aliases protected"))
    lines.append(failed(run(cli + ["-o", str(never), "--assets", str(elsewhere / "missing")], elsewhere), "No such"))
    check(not never.exists() and snapshot(repo, elsewhere) == before, "a refused build wrote a file")
    registry = repo / "data/analysisart32/digests.json"
    original = registry.read_bytes()
    edited = json.loads(original)
    edited["rom"] = "0" * 64
    registry.write_text(json.dumps(edited))
    lines.append(failed(run(cli + ["-o", str(never)], elsewhere), "differs from data/analysisart32/digests.json"))
    registry.write_bytes(original)
    check(not never.exists(), "a build against a wrong registry wrote a file")
    canonical.unlink()
    return [f"builder CLI (scratch checkout): the same ROM and manifest from another directory; {count} protected "
            "targets refused (input, renamed copy, tools, art, data, docs, both registries, the asset file, earlier "
            "evidence, symbolic and hard links); a bad input keeps the previous output; the canonical build is the "
            f"selected card; refused with nothing written: {'; '.join(lines)}"]


def bad_candidates(stock, rom, assets):
    """Known-bad ROMs: (bytes, teams, a phrase the oracle must report). Each patches the selected card's own
    bytes, so everything else stays as built."""
    _, _, tables = stage.home_code(assets)
    code, _ = stage.far_code(assets)
    far = locate(13, stage.FAR_CODE)

    def patched(edits):
        data = bytearray(rom)
        for offset, values in edits:
            data[offset:offset + len(values)] = values
        return bytes(data)
    x_at, y_at, num_lo = (locate(3, tables[k]) for k in ("pip_x", "pip_y", "num_lo"))
    with patch.object(AnalysisAssets, "__post_init__", lambda self: None):
        shifted_assets = replace(assets, socket_cols=tuple(c + 1 for c in assets.socket_cols))
    shifted_block, _, _ = stage.home_code(shifted_assets)
    shifted = patched([(locate(3, stage.HOME_CODE), shifted_block)])
    check(shifted[x_at:x_at + 4] == bytes(8 * c + 8 for c in assets.socket_cols), "the shifted tables")
    clears = [i for i in range(len(code) - 4) if code[i:i + 5] == bytes.fromhex("A9 00 8D E6 04")]
    check(len(clears) == 2, "card() must clear $04E6 twice")
    return {
        "$26 left at $18": (patched([(far + code.index(bytes.fromhex("A9 06 85 26")) + 1, b"\x18")]), (31,),
                            "CHR shadows"),
        "ball columns +8 px, tables generated from the shifted layout": (shifted, (5, 31), "sit on no socket"),
        "ball rows reversed": (patched([(y_at, bytes(reversed(rom[y_at:y_at + 4])))]), (31,), "shows balls on sockets"),
        "digit addresses permuted": (patched([(num_lo, bytes(rom[num_lo + i] for i in (1, 0, 3, 2)))]), (31,),
                                     "digits"),
        "every name at the stock column $2068": (patched([(locate(13, stage.NAME_COL), b"\x68" * 32)]), (0,), "center"),
        "no pacing: the $04E6 clears removed": (patched([(far + i, b"\xEA" * 5) for i in clears]), (31,), "releases"),
        "the unmodified input ROM": (stock, (0,), "CHR shadows"),
    }


def submit_bad(jobs, stock, rom, assets):
    cases = bad_candidates(stock, rom, assets)
    team_sets = sorted({teams for _, teams, _ in cases.values()})
    for teams in team_sets:
        jobs.submit(("bad-stock", teams), "tour", stock, list(teams), keys_for(list(teams)))
    for label, (bad, teams, _) in cases.items():
        jobs.submit(("bad", label), "tour", bad, list(teams), keys_for(list(teams)))
    return cases


def test_bad_candidates(ctx, jobs, cases):
    lines = []
    for label, (bad, teams, reason) in cases.items():
        problems = judge_tours(ctx, bad, [jobs.result(("bad", label))], [jobs.result(("bad-stock", teams))],
                               coverage=False)
        try:
            test_static(ctx, bad)
        except Failure as exc:
            problems.append(f"static: {exc}")
        check(any(reason in p for p in problems), f"{label}: the oracle did not report {reason!r}: {problems[:3]}")
        lines.append(f"  {label}: {len(problems)} problems, e.g. {next(p for p in problems if reason in p)[:96]}")
    return ["negative candidates (the same oracle, in process): every known-bad ROM fails it"] + lines


def test_verify_cli(repo, elsewhere, stock, rom, assets, render_png, quick=False):
    """The test command itself exits 1 for known-bad candidates and 0 for the selected card."""
    render = elsewhere / "render.png"
    render.write_bytes(render_png)
    cli = [sys.executable, "-B", str(repo / "tools/test_analysisart32.py"), str(repo / "build/stockart32.nes"),
           "--verify-only", "--jobs", "1", "--render", str(render)]
    cases = bad_candidates(stock, rom, assets)
    lines = []
    labels = ("$26 left at $18", "ball columns +8 px, tables generated from the shifted layout", "ball rows reversed")
    for n, label in enumerate(labels[:1] if quick else labels):
        bad, teams, reason = cases[label]
        path = elsewhere / f"bad-{n}.nes"
        path.write_bytes(bad)
        result = run(cli + ["--candidate", str(path), "--teams", ",".join(map(str, teams))], elsewhere)
        check(result.returncode == 1 and reason in result.stdout,
              f"{label}: exit {result.returncode}: {result.stdout[-300:]}{result.stderr[-300:]}")
        lines.append(f"{label}: exit 1 ({next(l for l in result.stdout.splitlines() if reason in l).strip()[:80]})")
    good = elsewhere / "good.nes"
    good.write_bytes(rom)
    result = run(cli + ["--candidate", str(good), "--teams", "31"], elsewhere)
    check(result.returncode == 0 and "PASS verify-only" in result.stdout, f"the good card failed: {result.stdout[-400:]}")
    return ["test CLI: tools/test_analysisart32.py --verify-only exits 1 for " + "; ".join(lines) +
            "; and exits 0 for the selected card"]



class Suite:
    def __init__(self):
        self.failures, self.passed = [], 0

    def run(self, name, call, *args):
        started = time.monotonic()
        try:
            result = call(*args)
        except Exception as exc:  # every failure is reported; the run then exits 1
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
    render_png = (args.render or stage.ASSETS / "render/scenes/card.png").read_bytes()
    teams = [int(t) for t in args.teams.split(",")] if args.teams else list(QUICK_TEAMS)
    ctx = Context(stock, render_png)
    jobs = Jobs(args.jobs)
    for key, rom in (("stock", stock), ("candidate", candidate)):
        jobs.submit(key, "tour", rom, teams, keys_for(teams))
    problems = []
    try:
        test_static(ctx, candidate)
    except Failure as exc:
        problems.append(f"static: {exc}")
    problems += judge_tours(ctx, candidate, [jobs.result("candidate")], [jobs.result("stock")], coverage=False)
    jobs.close()
    for p in problems:
        print(f"FAIL {p}")
    print(f"candidate {sha256(candidate)}: {len(problems)} problems on teams {teams}")
    if problems:
        sys.exit(1)
    print("PASS verify-only")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock", type=Path, help="the pinned stockart32 input ROM")
    ap.add_argument("--candidate", type=Path, help="the built ROM to judge (default: the deterministic build)")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: regenerate and run the converter CLI")
    ap.add_argument("--quick", action="store_true", help="seven teams, fewer NMI sites, fixtures and scoreboard flows")
    ap.add_argument("--verify-only", action="store_true", help="judge only --candidate on --teams")
    ap.add_argument("--teams", help="comma-separated teams for --verify-only (default: the quick teams)")
    ap.add_argument("--render", type=Path, help="the pinned render PNG for --verify-only (default: the installed one)")
    ap.add_argument("--jobs", type=int, default=min(6, os.cpu_count() or 1), help="worker processes (default %(default)s)")
    args = ap.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    stock = args.stock.read_bytes()
    if sha256(stock) != STOCK_SHA256:
        print(f"FAIL inputs: {args.stock} is not the pinned stockart32 input")
        sys.exit(1)
    if args.verify_only:
        if not args.candidate:
            ap.error("--verify-only needs --candidate")
        verify_only(args, stock)
        return
    suite = Suite()
    print(f"inputs: stockart32 {STOCK_SHA256}" + (f", candidate {args.candidate}" if args.candidate else ""))
    manifest = parts.load_manifest(convert.PART_MANIFEST)
    _, _, placements = convert.models(convert.read_sources())
    suite.run("layout boundary", test_layout_boundary)
    suite.run("placement boundary", test_placements_boundary, manifest)
    suite.run("ratings", test_ratings, stock)
    pxl = args.pxl.resolve() if args.pxl else None
    if pxl:
        built = suite.run("regeneration", test_regeneration, stock, pxl)
        if built is None:
            print("FAIL: without the regenerated art nothing further can be judged")
            sys.exit(1)
        outputs, assets, rom, _ = built
        suite.run("installed outputs", lambda: [
            "installed: build/analysisart32 holds exactly the registered outputs" if installed_outputs() is not None
            else "installed: build/analysisart32 absent (not checked)"])
    else:
        outputs = suite.run("installed outputs", lambda: (installed_outputs(), [
            "installed: build/analysisart32 holds exactly the registered outputs (no --pxl: not regenerated)"]))
        if outputs is None or outputs[0] is None:
            print("FAIL: without --pxl the registered outputs must be installed under build/analysisart32")
            sys.exit(1)
        outputs = outputs[0]
        assets = AnalysisAssets.parse(json.loads(outputs[stage.ASSET_JSON]))
        rom = stage.build_rom(stock, assets)
    render_png = outputs["render/scenes/card.png"]
    candidate = args.candidate.read_bytes() if args.candidate else rom

    def same_build():
        check(candidate == rom, f"candidate {sha256(candidate)} differs from the deterministic build {sha256(rom)}")
        check(sha256(rom) == TARGET_SHA256, f"the deterministic build is {sha256(rom)}, not the selected card")
        return [f"candidate: {sha256(candidate)} is the deterministic build and the selected card"]
    suite.run("candidate", same_build)

    jobs = Jobs(args.jobs)
    teams = list(QUICK_TEAMS if args.quick else FULL_TEAMS)
    size = len(teams) if args.quick else 8
    tour_keys = {name: submit_tours(jobs, name, r, teams, size) for name, r in (("stock", stock), ("card", candidate))}
    timing = ([(31, lead, "A" if i % 2 else "B", True) for i, lead in enumerate((0, 1, 3700, 7400, 14800, 22200, 29000))]
              + [(t, 0, "A" if t % 2 else "B", False) for t in (0, 5, 13, 18, 27)])
    if args.quick:
        timing = [timing[1], timing[4], timing[8], timing[10]]     # A and B exits, held and released, two leads
    for name, r in (("stock", stock), ("card", candidate)):
        for k, part in enumerate(chunks(timing, 4)):
            jobs.submit(("timing", name, k), "timing_cases", stock, r, part)
    switches = [(3, 13, 1), (13, 4, 1), (4, 13, 1), (13, 1, 1), (1, 13, 1), (13, 4, 2), (4, 13, 2), (13, 3, 1)]
    positions = (0xC14E, 0xC150, 0xC152, 0xC156, 0xC15A, 0xC15E, 0xC162, 0xC165)
    _, home_labels, home_tables = stage.home_code(assets)
    fixed = [("home pad", ("at", (3, stage.PAD))), ("far pad resume", ("at", (13, stage.PAD + 6))),
             ("card entry", ("at", (13, stage.FAR_CODE))), ("home pad RTS", ("at", (3, stage.PAD + 15))),
             ("numerals", ("at", (3, home_labels["numerals"]))), ("balls", ("at", (3, home_labels["balls"] + 0x17)))]
    injection = {}
    for team, chosen, fractions in ((0, switches, (40, 20)), (31, switches[:1] + switches[-1:], (20, 10))):
        if args.quick and team == 0:
            continue
        if args.quick:
            fractions = (8, 4)
        named = fixed + [(f"switch {old}->{new} #{nth} at ${pc:04X}", ("switch", (pc, old, new, nth)))
                         for old, new, nth in chosen for pc in positions]
        windows = [("init", stage.HOOK, stage.STOCK_TAIL, tuple((k + 0.5) / fractions[0] for k in range(fractions[0]))),
                   ("balls", home_labels["balls"], home_tables["num_hi"] - 1,
                    tuple((k + 0.5) / fractions[1] for k in range(fractions[1])))]
        parts_n = 3 if not args.quick else 2
        injection[team] = [("injection", team, k) for k in range(parts_n)]
        for k in range(parts_n):
            jobs.submit(("injection", team, k), "injection_runs", stock, candidate, team, named[k::parts_n],
                        [(n, a, b, f[k::parts_n]) for n, a, b, f in windows])
    for name, r in (("stock", stock), ("card", candidate)):
        jobs.submit(("screens", name), "screens", r)
    jobs.submit("earlier_mode", "earlier_mode", stock, candidate)
    jobs.submit("earlier_pick", "earlier_pick", candidate)
    for k in range(2):
        jobs.submit(("earlier_score", k), "earlier_score", stock, candidate, args.quick, k, 2)
    bad = submit_bad(jobs, stock, rom, assets)

    ctx = Context(stock, render_png)
    suite.run("parts and placements", test_parts, stock, manifest, placements, rom)
    suite.run("provenance", test_provenance, rom, outputs, assets)
    suite.run("converter controls", test_converter_controls, stock, render_png)
    suite.run("asset boundary", test_asset_controls, stock, assets)
    suite.run("stage", test_stage, stock, rom, assets)
    suite.run("static", test_static, ctx, candidate)
    with checkout(args.stock) as (repo, elsewhere):
        install(repo, outputs)
        suite.run("builder CLI", test_builder_cli, repo, elsewhere, stock, rom, assets)
        suite.run("test CLI", test_verify_cli, repo, elsewhere, stock, rom, assets, render_png, args.quick)
        shutil.rmtree(repo / "build/analysisart32")
        if pxl:
            suite.run("convert CLI", test_convert_cli, repo, elsewhere, pxl)
        else:
            print("convert CLI: skipped (no --pxl)")
    suite.run("negative candidates", test_bad_candidates, ctx, jobs, bad)
    suite.run("runtime", lambda: test_runtime(ctx, candidate, [jobs.result(k) for k in tour_keys["card"]],
                                              [jobs.result(k) for k in tour_keys["stock"]]))

    def timing_results(name):
        return [case for k in range(len(chunks(timing, 4))) for case in jobs.result(("timing", name, k))]
    suite.run("timing", lambda: test_timing(timing_results("card"), timing_results("stock")))

    def injection_results():
        found = []
        for team, keys in injection.items():
            parts_ = [jobs.result(key) for key in keys]
            check(all(p[0] == parts_[0][0] for p in parts_), f"team {team}: the injection jobs' references differ")
            found.append((team, (parts_[0][0], [run for p in parts_ for run in p[1]])))
        return found
    suite.run("NMI injection", lambda: test_injection(injection_results()))
    suite.run("protected screens", lambda: test_screens(jobs.result(("screens", "stock")), jobs.result(("screens", "card"))))
    suite.run("earlier mode", lambda: jobs.result("earlier_mode"))
    suite.run("earlier pick", lambda: jobs.result("earlier_pick"))
    suite.run("earlier score", lambda: [
        f"earlier score suite: {jobs.result(('earlier_score', 0)) + jobs.result(('earlier_score', 1))} scoreboard exits "
        "match stockart32 frame for frame (scene writes, sound requests, per-frame scene, bank, song, rendering and "
        "every APU write; test_scoreart32.flow_check)"])
    jobs.close()
    print("limits: CPU model only. Sprite-0 hit is manufactured from the beam position and OAM; PPU fetch timing, open "
          "bus, real MMC1 write timing and the analog picture are not modelled; audio is compared as APU register "
          "writes. Root's real-core phase, split-seam, mapper-census and audio probes, the 224-line capture review and "
          "the stock-six and 31-game tournament gates are separate from this CPU suite.")
    print(f"analysisart32 SHA256 {sha256(rom)}")
    if suite.failures:
        print(f"FAIL: {len(suite.failures)} of {suite.passed + len(suite.failures)} sections failed: "
              f"{', '.join(name for name, _ in suite.failures)} ({time.monotonic() - started:.1f}s)")
        sys.exit(1)
    print(f"PASS ({suite.passed} sections, {time.monotonic() - started:.1f}s)" + (" quick" if args.quick else ""))


if __name__ == "__main__":
    main()
