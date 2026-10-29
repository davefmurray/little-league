#!/usr/bin/env python3
"""Check the modeart32 stage: art conversion, the asset boundary, builder guards and the mode menu at runtime.

    .venv/bin/python tools/test_modeart32.py build/title32.nes --candidate build/modeart32.nes
    .venv/bin/python tools/test_modeart32.py build/title32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python tools/test_modeart32.py build/title32.nes --quick

Runtime checks boot the built ROM and its title32 input from RESET on
tools/frontend32_test_machine.Boot and press real controller buttons. Each
menu's VRAM, palette, CHR banks, ball sprites and composed frame are compared
with an oracle built from the layout and the ROM's own scene-6 upload, not from
the converter's run lists. Exits, sound requests, idle APU writes and the
scene-7 stack are compared with the stock title32 menu, and pick32's picker
flows run unchanged. Negative controls must fail these same checks. The model
is a CPU timing model with an approximate PPU: vblank budgets and injected NMIs
are model results, not hardware timing. Pixel, listening and mapper acceptance
belong to the root emulator gates. --quick skips the pick32 flows and the NMI
injection sweep.
"""
import argparse
import copy
from dataclasses import replace
import hashlib
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

import build_modeart32 as builder
from build_bank11 import assemble
from build_draw32 import locate, read
import menu32_convert as menu
import modeart32_assets as model
from modeart32_assets import LABELS, MENUS, AssetError, MenuText, ModeAssets, Span
import modeart32_convert as convert
import password32v2 as P
import render_menu32 as R
import test_pick32 as pick
from frontend32_test_machine import (
    A, B, DOWN, SCENE, SERIES_RAM, START, Boot, Driver, check_builder, check_output_guards, choose, plant,
    rejects, series_state, title_tail, to_mode_menu,
)

OUTPUT_SHA256 = "7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9"
TOOLS = Path(__file__).resolve().parent
UP = R.UP
LIVE = P.Series(team=9, played=3, results=0b101, cpu_mask=0xFFFFFDFF, draw_seed=0x1234)
OWN = (0x06E0, 0xBD, 0x04EB, 0x04EC, 0x04E9, 0x04E2, 0x04ED, 0x04EE, 0x07ED)
MODE_BYTES = (0x06E0, 0xBD, 0xB8, 0xB9, 0xBA)
SPRITE_CHR = builder.SPRITE_CHR
NEW_CODE = ((1, 0x942A, 0x944B), (1, 0x9464, 0x9469), (1, 0x9484, 0x9489), (1, 0x948F, 0x9494),
            (13, builder.FAR, builder.FAR_END))
MAPPER = range(0xC102, 0xC16C)
CONTRACT = ({0x00, 0x01, 0x06, 0x23, 0x25, 0x27, 0x2C, 0x2D, 0x2E, 0x32, 0xAA, 0xAB, 0xAC, 0xAD}
            | set(range(0x0195, 0x01B6)) | set(range(0x06B3, 0x06D6)) | set(range(0x0300, 0x0323)))
FLOWS = {
    "Championship CONTINUE": [A, A, "wait"],
    "Championship LIST OF TEAMS": [A, DOWN, A, "wait"],
    "Championship START NEW SERIES": [A, DOWN, DOWN, A, "wait"],
    "Exhibition 1P": [DOWN, A, A, "wait"],
    "Exhibition 2P": [DOWN, A, DOWN, A, "wait"],
    "Exhibition WATCH GAME": [DOWN, A, DOWN, DOWN, A, "wait"],
    "Power Analysis": [DOWN, DOWN, A, "wait"],
    "Power Analysis by wrapping up": [UP, A, "wait"],
    "submenu B, then Power Analysis": [A, B, DOWN, DOWN, A, "wait"],
}


# ---------------------------------------------------------------- oracles

def layout_texts():
    layout = json.loads(convert.LAYOUT.read_text())
    return ({name: [(t["row"], t["col"], t["text"])
                    for t in layout["menus"][name]["items"] + layout["menus"][name].get("text", [])]
             for name in MENUS},
            [(t["row"], t["col"], t["text"]) for t in layout["static_text"]])


def oracle_screens(rom):
    """Each menu's 1 KB nametable and attributes: the ROM's scene-6 upload with that menu's layout text in
    place of every menu's text. Built from the layout alone, not from the converter's spans or runs."""
    upload = read(rom, builder.FAR_BANK, builder.SCREEN, 0x400)
    texts, _ = layout_texts()
    cleared = bytearray(upload)
    for name in MENUS:
        for row, col, text in texts[name]:
            cleared[32 * row + col:32 * row + col + len(text)] = b" " * len(text)
    screens = {}
    for name in MENUS:
        screen = bytearray(cleared)
        for row, col, text in texts[name]:
            screen[32 * row + col:32 * row + col + len(text)] = text.encode()
        screens[name] = bytes(screen)
    assert screens["main"] == upload, "scene 6 does not upload the main menu"
    return screens


def layout_cursor():
    """The nine stock cursor-table entries the layout asks for: main x3, Exhibition x3, main x3."""
    layout = json.loads(convert.LAYOUT.read_text())
    dx, dy = layout["cursor"]["dx"], layout["cursor"]["dy"]
    origins = {name: [(8 * i["col"] + dx, 8 * i["row"] + dy) for i in layout["menus"][name]["items"]]
               for name in MENUS}
    assert origins["championship"] == origins["main"], "Championship items must sit on the main items' origins"
    return origins["main"] + origins["exhibition"] + origins["main"]


def ball(base, entry):
    """The four OAM entries of the stock ball on cursor-table entry `entry`, from the layout."""
    return bytes(b for sprite in convert.cursor_sprites(base, *layout_cursor()[entry]) for b in sprite)


def first_difference(got, want):
    bad = [i for i in range(min(len(got), len(want))) if got[i] != want[i]]
    return f"{len(bad)} bytes differ, first at ${0x2000 + bad[0]:04X}" if bad else f"sizes {len(got)}/{len(want)}"


def machine_frame(m):
    bg, sp = m.chr_bank(1 if m.ctrl & 0x10 else 0), m.chr_bank(1 if m.ctrl & 0x08 else 0)
    oam = [tuple(m.oam[i:i + 4]) for i in range(0, 256, 4)]
    return convert.compose(m.chr_rom[bg * 0x1000:bg * 0x1000 + 0x1000], m.chr_rom[sp * 0x1000:sp * 0x1000 + 0x1000],
                           m.nametable(), m.palette32(), oam), (bg, sp)


def check_view(m, base, assets, screens, name, entry, label):
    """VRAM, palette, CHR banks, the four ball sprites and the composed frame while `name` shows."""
    shown = m.nametable()
    assert shown == screens[name], f"{label}: VRAM is not the {name} menu ({first_difference(shown, screens[name])})"
    assert m.palette32() == assets.palette, f"{label}: palette {m.palette32().hex()}"
    image, banks = machine_frame(m)
    assert banks == (model.MODE_CHR, SPRITE_CHR), f"{label}: background/sprite CHR ${banks[0]:02X}/${banks[1]:02X}"
    assert bytes(m.oam[:16]) == ball(base, entry), \
        f"{label}: ball sprites {bytes(m.oam[:16]).hex()} are not cursor entry {entry}"
    assert all(m.oam[i] >= 0xEF for i in range(16, 256, 4)), f"{label}: a stray sprite is visible"
    assert image.tobytes() == convert.frame(assets, base, name, entry).tobytes(), \
        f"{label}: the composed frame differs from the converter preview"


# ---------------------------------------------------------------- converter

def edit_png(path, spots):
    image = Image.open(path).convert("RGBA")
    for xy, rgba in spots:
        image.putpixel(xy, rgba)
    image.save(path)


def converted(base, mutate_layout=None, mutate_png=None):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        scene, layout_path = directory / "mode.png", directory / "layout.json"
        shutil.copyfile(convert.SCENE, scene)
        layout = json.loads(convert.LAYOUT.read_text())
        if mutate_layout:
            mutate_layout(layout)
        if mutate_png:
            mutate_png(scene)
        layout_path.write_text(json.dumps(layout))
        return convert.convert(base, layout_path, scene)


def free_cell(assets):
    """(menu, row, col) of a span cell that one menu leaves blank on both sides: room for per-menu text
    without new art and without touching that menu's labels."""
    texts, _ = layout_texts()
    for span in assets.spans:
        for name in MENUS:
            covered = {col + i for row, col, text in texts[name] if row == span.row for i in range(len(text))}
            for col in range(span.col, span.col + span.width):
                if not {col - 1, col, col + 1} & covered:
                    return name, span.row, col
    raise AssertionError("no span cell is blank with blank neighbours in any menu")


def plain_cell():
    """Pixel origin of the first 16x16 attribute cell with no text in any menu."""
    texts, static = layout_texts()
    cells = {((col + i) // 2, row // 2) for row, col, text in static + [t for n in MENUS for t in texts[n]]
             for i in range(len(text))}
    ax, ay = next((x, y) for y in range(15) for x in range(16) if (x, y) not in cells)
    return 16 * ax, 16 * ay


def test_converter(base, rom_path, pxl=None):
    first, second = convert.convert(base), convert.convert(base)
    text = first.dumps()
    assert text == second.dumps(), "converter output is not deterministic"
    assert text == model.ASSETS.read_text(), "data/modeart32/modeassets.json is stale"
    assert ModeAssets.load() == first, "the committed JSON does not load back to the converted art"
    assert first.png_sha256 == hashlib.sha256(convert.SCENE.read_bytes()).hexdigest()
    reproduced = convert.check_pxl(pxl, rom_path) if pxl else 0

    layout = json.loads(convert.LAYOUT.read_text())
    span = first.spans[0]
    backdrop = menu.nes_color(layout["backdrop"])
    colors = sorted({menu.nes_color(c) for p in layout["palettes"] for c in p} - {backdrop})
    ink = menu.NES_RGB[colors[0]] + (255,)
    fonts = menu.font_patterns(base)
    unprintable = next(chr(i) for i in range(0x21, 0x7F) if not any(fonts[i]))
    owner, row, col = free_cell(first)
    x0, y0 = plain_cell()
    other = (layout["item_palette"] + 1) % 4

    def item(name, i, **change):
        return lambda lay: lay["menus"][name]["items"][i].update(change)

    def menu_text(name, entry):
        return lambda lay: lay["menus"][name].setdefault("text", []).append(entry)
    main0 = layout["menus"]["main"]["items"][0]
    cases = [
        ("unknown color", "not a palette color", None, lambda s: edit_png(s, [((100, 200), (1, 2, 3, 255))])),
        ("partial alpha", "transparency", None, lambda s: edit_png(s, [((100, 200), ink[:3] + (128,))])),
        ("wrong size", "expected 256x240", None,
         lambda s: Image.new("RGBA", (256, 224), menu.NES_RGB[backdrop] + (255,)).save(s)),
        ("painted text cell", "reserved", None,
         lambda s: edit_png(s, [((8 * (span.col + span.width - 1) + 3, 8 * span.row + 3), ink)])),
        ("no stock glyph", "no glyph", menu_text(owner, {"row": row, "col": col, "text": unprintable,
                                                          "palette": layout["item_palette"]}), None),
        ("non-ASCII text", "printable ASCII", menu_text(owner, {"row": row, "col": col, "text": "\u00c9",
                                                                 "palette": layout["item_palette"]}), None),
        ("unsupported color", "unsupported NES color", lambda lay: lay["palettes"][0].__setitem__(0, "0D"), None),
        ("three palettes", "four palettes", lambda lay: lay["palettes"].pop(), None),
        ("misaligned Championship item", "championship items must start",
         item("championship", 1, col=layout["menus"]["main"]["items"][1]["col"] + 1), None),
        ("row palette conflict", "one palette", menu_text(owner, {"row": row, "col": col, "text": "X",
                                                                   "palette": other}), None),
        ("static text on a menu row", "overlaps", lambda lay: lay["static_text"].append(
            {"row": span.row, "col": span.col, "text": "HI", "palette": layout["item_palette"]}), None),
        ("non-canonical label", "items must be", item("exhibition", 0, text="1P GAME"), None),
        ("labels out of order", "items must be", lambda lay: lay["menus"]["main"]["items"].reverse(), None),
        ("two items", "items must be", lambda lay: lay["menus"]["main"]["items"].pop(), None),
        ("item with its own palette", "must hold exactly", item("main", 0, palette=0), None),
        ("missing menu", "menus must hold", lambda lay: lay["menus"].pop("exhibition"), None),
        ("unknown menu", "menus must hold", lambda lay: lay["menus"].update(options={"items": []}), None),
        ("unknown layout key", "layout keys", lambda lay: lay.update(static_txt=[]), None),
        ("foreign layout format", "layout format", lambda lay: lay.update(format="modeart32-layout/2"), None),
        ("item_palette 4", "item_palette", lambda lay: lay.update(item_palette=4), None),
        ("cursor off screen", "off screen", lambda lay: lay["cursor"].update(dx=255), None),
        ("cursor above the screen", "off screen", lambda lay: lay["cursor"].update(dy=-255), None),
        ("item off the right edge", "right edge", item("main", 0, col=33 - len(main0["text"])), None),
        ("item below the screen", "row must be", item("main", 2, row=30), None),
    ]
    if len(colors) >= 4:
        cases.append(("attribute conflict", "fit no palette", None, lambda s: edit_png(
            s, [((x0 + i, y0), menu.NES_RGB[c] + (255,)) for i, c in enumerate(colors[:4])])))
    for label, reason, mutate_layout, mutate_png in cases:
        try:
            converted(base, mutate_layout, mutate_png)
        except AssetError as exc:
            assert reason in str(exc), f"{label}: rejected for another reason: {exc}"
            continue
        raise AssertionError(f"converter accepted {label}")
    real_init = menu.TileBank.__init__

    def tiny(bank, *args):
        real_init(bank, *args)
        bank.order = bank.order[:first.tiles_used - len(first.font_glyphs) - 1]
    with patch.object(menu.TileBank, "__init__", tiny):
        rejects(converted, base)

    extra = converted(base, menu_text(owner, {"row": row, "col": col, "text": "X", "palette": layout["item_palette"]}))
    assert extra.spans == first.spans
    for name in MENUS:
        want = bytearray(first.screen(name))
        if name == owner:
            want[32 * row + col] = ord("X")
        assert extra.screen(name) == bytes(want), name
    print(f"converter: deterministic; committed JSON current ({first.tiles_used} tiles, {len(first.font_glyphs)} "
          f"stock glyphs, {len(first.spans)} text rows); {len(cases) + 1} bad layouts or PNGs rejected, each for its "
          "own reason" + ("" if len(colors) >= 4 else " (attribute conflict skipped: the palettes hold under four "
                          "colors)") + f"; per-menu text inside a shared row shows only in its menu ({owner})"
          + (f"; pinned pxl reproduces all {reproduced} committed PNGs" if pxl
             else "; pxl re-render not run (no --pxl)"))


def run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def test_converter_cli(rom_path, base, assets):
    script = [sys.executable, str(TOOLS / "modeart32_convert.py"), "--rom"]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        rom = directory / "title32.nes"
        rom.write_bytes(base)
        output, preview = directory / "assets.json", directory / "preview.png"
        result = run(script + [str(rom), "--out", str(output), "--preview", str(preview)], directory)
        assert result.returncode == 0 and output.read_text() == model.ASSETS.read_text(), result.stderr
        assert Image.open(preview).convert("RGB").tobytes() == convert.preview(assets, base).tobytes()
        result = run(script + [str(rom), "--out", str(output), "--check"], directory)
        assert result.returncode == 0 and "checked" in result.stdout, result.stderr
        missing, unwanted = directory / "missing.json", directory / "unwanted.png"
        result = run(script + [str(rom), "--out", str(missing), "--check"], directory)
        assert result.returncode == 2 and "stale" in result.stderr and not missing.exists(), result.stderr
        result = run(script + [str(rom), "--out", str(output), "--check", "--preview", str(unwanted)], directory)
        assert result.returncode == 2 and not unwanted.exists(), result.stderr
        stale = output.read_text().replace('"tiles_used": ', '"tiles_used": 1')
        output.write_text(stale)
        result = run(script + [str(rom), "--out", str(output), "--check"], directory)
        assert result.returncode == 2 and "stale" in result.stderr and output.read_text() == stale, result.stderr

        root = builder.ROOT
        renamed = directory / "renamed-input.nes"
        renamed.write_bytes(base)
        targets = [rom, renamed, TOOLS / "verify.sh", convert.SCENE, convert.LAYOUT, convert.LOCK,
                   TOOLS / "build_modeart32.py",
                   TOOLS / "modeart32_convert.py", TOOLS / "modeart32_assets.py", root / "data/teams32.json",
                   root / "data/title32/titleassets.json", root / "data/menu32/menuassets.json",
                   root / "art/title32/out/scenes/title.png", root / "build/title32.nes"]
        for i, target in enumerate((rom, convert.SCENE, root / "data/teams32.json")):
            symbolic, hard = directory / f"alias{i}-symlink", directory / f"alias{i}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets += [symbolic, hard]
        for target in targets:
            before = target.read_bytes()
            for option in (["--out", str(target)], ["--out", str(output), "--preview", str(target)]):
                result = run(script + [str(rom)] + option, directory)
                assert result.returncode == 2 and "output aliases protected" in result.stderr, (target, result.stderr)
                assert target.read_bytes() == before, f"{target} changed"
        result = run(script + [str(rom), "--preview", str(model.ASSETS)], directory)
        assert result.returncode == 2 and "output aliases protected" in result.stderr, result.stderr

        link = directory / "assets-link.json"
        link.symlink_to(model.ASSETS)
        for allowed in (model.ASSETS, link):
            convert.protect_output(rom_path, allowed)
        rejects(builder.protect_output, rom_path, model.ASSETS)
        trap = directory / "trap.json"
        trap.symlink_to(root / "data/teams32.json")
        with patch.object(convert, "ASSETS", trap):
            rejects(convert.protect_output, rom_path, trap)
    print(f"converter CLI: --out and --preview from another directory; --check passes current JSON, fails stale or "
          f"missing JSON and writes nothing (a --check --preview is refused); {len(targets)} protected targets "
          "refused as --out or --preview and left intact (ROM, renamed ROM, sources, art, data, verify.sh, symbolic "
          "and hard links); only the canonical JSON entry itself, or a link to it, is writable, and a canonical path "
          "resolving onto another data file stays refused")


EARLIER = ("direct31", "direct31-pair36", "gameplay32", "cpu32", "teamtables32", "roles32", "results32", "control32",
           "password32", "teamnames32", "visualtables32", "menuart32", "draw32", "pick32", "title32")


def test_png_regeneration(base, pxl=None):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        rom = directory / 'title32.nes'
        rom.write_bytes(base)
        source, data = directory / 'source.js', directory / 'protected.json'
        source.write_text('source stays intact')
        data.write_text('data stays intact')
        staging = directory / 'rendered'
        shutil.copytree(convert.PNGS, staging)
        target_root = directory / 'out'
        target_root.mkdir()
        early = target_root / 'scenes/mode.png'
        early.parent.mkdir()
        early.write_bytes(b'previous scene')
        trap = target_root / 'sprites/dad.png'
        trap.parent.mkdir()
        output, preview = directory / 'assets.json', directory / 'preview.png'
        output.write_bytes(b'previous JSON')
        preview.write_bytes(b'previous preview')
        cases = 0
        with patch.object(convert, 'SOURCE', source), patch.object(convert, 'ASSETS', data):
            for protected in (rom, source, data, output, preview, early):
                for symbolic in (False, True):
                    trap.unlink(missing_ok=True)
                    if symbolic:
                        trap.symlink_to(protected)
                    else:
                        os.link(protected, trap)
                    before = {p: p.read_bytes() for p in (rom, source, data, output, preview, early)}
                    rejects(convert.install_pngs, staging, target_root, rom, (output, preview))
                    assert all(p.read_bytes() == contents for p, contents in before.items())
                    assert trap.samefile(protected), 'rejection changed an output before preflight finished'
                    cases += 1
        trap.unlink()
        for collision in (output, preview):
            outputs = tuple(trap if path == collision else path for path in (output, preview))
            before = {p: p.read_bytes() for p in (rom, source, data, output, preview, early)}
            rejects(convert.install_pngs, staging, target_root, rom, outputs)
            assert not trap.exists(), 'rejected collision created the missing PNG'
            assert all(p.read_bytes() == contents for p, contents in before.items())
        neighbor = directory / 'unrelated.png'
        neighbor.write_bytes(b'unrelated inode')
        os.link(neighbor, trap)
        converted = convert.install_pngs(staging, target_root, rom, (output, preview))
        assert len(converted) == 12
        assert neighbor.read_bytes() == b'unrelated inode' and not trap.samefile(neighbor)
        assert all((target_root / p).read_bytes() == (staging / p).read_bytes() for p in converted)
        if pxl:
            for symbolic in (False, True):
                trap.unlink()
                if symbolic:
                    trap.symlink_to(rom)
                else:
                    os.link(rom, trap)
                before = early.read_bytes()
                argv = ['modeart32_convert.py', '--rom', str(rom), '--out', str(output), '--pxl', str(pxl)]
                with patch.object(convert, 'PNGS', target_root), patch.object(sys, 'argv', argv):
                    try:
                        convert.main()
                    except SystemExit as exc:
                        assert exc.code == 2
                    else:
                        raise AssertionError('regeneration CLI accepted an input-ROM alias')
                assert rom.read_bytes() == base and early.read_bytes() == before
                assert output.read_bytes() == b'previous JSON'
            trap.unlink()
            for option in ('--out', '--preview'):
                before = {p: p.read_bytes() for p in target_root.rglob('*.png')}
                before.update({p: p.read_bytes() for p in (rom, output, preview)})
                argv = ['modeart32_convert.py', '--rom', str(rom), '--pxl', str(pxl),
                        '--out', str(trap if option == '--out' else output)]
                if option == '--preview':
                    argv += ['--preview', str(trap)]
                with patch.object(convert, 'PNGS', target_root), patch.object(sys, 'argv', argv):
                    try:
                        convert.main()
                    except SystemExit as exc:
                        assert exc.code == 2
                    else:
                        raise AssertionError(f'regeneration CLI accepted missing PNG as {option}')
                assert not trap.exists()
                assert all(p.read_bytes() == contents for p, contents in before.items())
    print(f'PNG regeneration: {cases} symbolic/hard aliases rejected before any persistent copy; atomic '
          'replacement leaves unrelated linked inodes intact; missing PNG collisions rejected for JSON and preview'
          + ('; real --pxl CLI alias and collision regressions pass' if pxl else ''))


def test_protected_names(rom_path):
    """The original ROM and every earlier stage's ROM are refused as outputs of both tools; the stage's own
    output is not."""
    targets = [builder.ROOT / "Little League Baseball - Championship Series (USA).nes"]
    targets += [builder.ROOT / "build" / f"{stage}.nes" for stage in EARLIER]
    targets += [Path(rom_path).resolve().parent / f"{stage}.nes" for stage in ("pick32", "title32")]
    for target in targets:
        rejects(builder.protect_output, rom_path, target)
        rejects(convert.protect_output, rom_path, target)
    builder.protect_output(rom_path, builder.ROOT / "build/modeart32.nes")
    print(f"protected names: the original ROM and {len(targets) - 1} earlier-stage ROM paths are refused as builder "
          "and converter outputs; build/modeart32.nes stays writable")


# ---------------------------------------------------------------- asset boundary and builder

def run_list_edit(name, edit):
    """Mutate one menu's hex run list through `edit(bytearray)`."""
    def mutate(record):
        data = bytearray.fromhex(record["runs"][name])
        edit(data)
        record["runs"][name] = data.hex()
    return mutate


def run_holding(data, text):
    """(start, end) of the run in a $C840 list whose tiles hold `text`; `end` indexes its terminator."""
    pos = 0
    while pos < len(data):
        end = pos + 2
        while data[end] < 0xFE:
            end += 1
        if text in data[pos + 2:end]:
            return pos, end
        pos = end + 1
    raise AssertionError(f"no run holds {text!r}")


def boundary_cases(record):
    """(label, expected reason, mutation) of the committed JSON record. Run edits target the runs holding the
    canonical labels, so the cases mean the same thing for any art."""
    main = bytes.fromhex(record["runs"]["main"])
    k, k_end = run_holding(main, b"POWER ANALYSIS")
    width = k_end - k - 2
    row = ((main[k + 1] & 0x3F) << 8 | main[k]) - 0x2000 >> 5
    label = k + 2 + main[k + 2:k_end].index(b"ANALYSIS")
    crossing = 0x2000 + 32 * row + 33 - width
    lower = 0x2000 + 32 * (row + 1) + (main[k] & 31) if row < 29 else 0x2000 + 32 * (row - 1) + (main[k] & 31)
    exhibition = bytes.fromhex(record["runs"]["exhibition"])
    e, e_end = run_holding(exhibition, b"1P")
    offset = exhibition[e + 2:e_end].index(b"1P")
    moved = ((exhibition[e + 1] & 0x3F) << 8 | exhibition[e]) + offset
    narrow = exhibition[:e] + bytes((moved & 0xFF, 0x40 | moved >> 8)) + b"1P" + exhibition[e_end:]
    nametable = bytes.fromhex(record["nametable"])
    shown = next(32 * s["row"] + c for s in record["spans"] for c in range(s["col"], s["col"] + s["width"])
                 if nametable[32 * s["row"] + c] != 0x20)
    palette = bytes.fromhex(record["palette"])
    other_backdrop = 0x0F if palette[0] != 0x0F else 0x30
    x0 = bytes.fromhex(record["cursor"])[0]
    early = next(end for end in (k_end, run_holding(main, b"CHAMPIONSHIP SERIES")[1]) if end != len(main) - 1)

    def hexbytes(key, edit):
        return lambda r: r.update({key: edit(bytearray.fromhex(r[key])).hex()})

    def at(index, value):
        def edit(data):
            data[index] = value
            return data
        return edit
    unused = next(i for i in range(256) if i not in record["font_glyphs"]
                  and not any(bytes.fromhex(record["chr"])[16 * i:16 * i + 16]))
    return [
        ("format", "expected modeassets/1", lambda r: r.update(format="modeassets/2")),
        ("CHR bank", "expected modeassets/1", lambda r: r.update(chr_bank=0x17)),
        ("missing key", "exactly the keys", lambda r: r.pop("cursor")),
        ("unknown key", "exactly the keys", lambda r: r.update(comment="")),
        ("short CHR", "chr must be exactly 4096", lambda r: r.update(chr=r["chr"][:-2])),
        ("long CHR", "chr must be exactly 4096", lambda r: r.update(chr=r["chr"] + "00")),
        ("short nametable", "nametable must be exactly 960", lambda r: r.update(nametable=r["nametable"][:-2])),
        ("long nametable", "nametable must be exactly 960", lambda r: r.update(nametable=r["nametable"] + "20")),
        ("short attributes", "attributes must be exactly 64", lambda r: r.update(attributes=r["attributes"][:-2])),
        ("long attributes", "attributes must be exactly 64", lambda r: r.update(attributes=r["attributes"] + "00")),
        ("short palette", "palette must be exactly 32", lambda r: r.update(palette=r["palette"][:-2])),
        ("long palette", "palette must be exactly 32", lambda r: r.update(palette=r["palette"] + "0c")),
        ("short cursor", "cursor must be exactly 18", lambda r: r.update(cursor=r["cursor"][:-2])),
        ("long cursor", "cursor must be exactly 18", lambda r: r.update(cursor=r["cursor"] + "28")),
        ("uppercase hex", "lowercase hex", lambda r: r.update(chr=r["chr"].upper())),
        ("spaced hex", "lowercase hex",
         lambda r: r.update(cursor=" ".join(r["cursor"][i:i + 2] for i in range(0, 36, 2)))),
        ("odd hex", "lowercase hex", lambda r: r.update(cursor=r["cursor"] + "0")),
        ("list instead of hex", "lowercase hex", lambda r: r.update(cursor=list(bytes.fromhex(r["cursor"])))),
        ("tiles_used off by one", "tiles_used", lambda r: r.update(tiles_used=r["tiles_used"] + 1)),
        ("tiles_used as text", "tiles_used", lambda r: r.update(tiles_used=str(r["tiles_used"]))),
        ("unsorted glyphs", "font_glyphs", lambda r: r.update(font_glyphs=r["font_glyphs"][::-1])),
        ("glyphs without the blank", "font_glyphs", lambda r: r["font_glyphs"].remove(0x20)),
        ("glyph outside ASCII", "font_glyphs", lambda r: r["font_glyphs"].append(0xC8)),
        ("undefined nametable tile", "undefined", hexbytes("nametable", at(0, unused))),
        ("palette color $40", "supported NES colors", hexbytes("palette", at(1, 0x40))),
        ("palette color $0D", "supported NES colors", hexbytes("palette", at(1, 0x0D))),
        ("two backdrops", "one backdrop", hexbytes("palette", at(20, other_backdrop))),
        ("bad png digest", "png_sha256", lambda r: r.update(png_sha256=r["png_sha256"].upper())),
        ("no spans", "spans", lambda r: r.update(spans=[])),
        ("span 33 wide", "1-32", lambda r: r["spans"][0].update(width=33)),
        ("span crossing a row", "1-32", lambda r: r["spans"][0].update(col=33 - r["spans"][0]["width"])),
        ("span below the screen", "1-32", lambda r: r["spans"][-1].update(row=30)),
        ("span with a flag", "integers", lambda r: r["spans"][0].update(row=True)),
        ("span with an extra key", "row, col, width", lambda r: r["spans"][0].update(palette=1)),
        ("two spans on one row", "one span per row", lambda r: r["spans"].insert(1, dict(r["spans"][0]))),
        ("runs without Exhibition", "runs must hold", lambda r: r["runs"].pop("exhibition")),
        ("33-tile run", "runs hold 1-32",
         run_list_edit("main", lambda d: d.__setitem__(slice(k + 2, k + 2), b" " * (33 - width)))),
        ("run crossing a row", "leaves its nametable row",
         run_list_edit("main", lambda d: d.__setitem__(slice(k, k + 2),
                                                       bytes((crossing & 0xFF, 0x40 | crossing >> 8))))),
        ("wide-font flag", "narrow raw run", run_list_edit("main", lambda d: d.__setitem__(k + 1, d[k + 1] | 0x80))),
        ("raw flag missing", "narrow raw run", run_list_edit("main", lambda d: d.__setitem__(k + 1, d[k + 1] & ~0x40))),
        ("nametable $2400", "narrow raw run", run_list_edit("main", lambda d: d.__setitem__(k + 1, 0x64))),
        ("attribute table address", "leaves its nametable row",
         run_list_edit("main", lambda d: d.__setitem__(slice(k, k + 2), bytes((0xC8, 0x63))))),
        ("terminator inside a run", "", run_list_edit("main", lambda d: d.__setitem__(label + 3, 0xFE))),
        ("list without $FF", "truncated", run_list_edit("main", lambda d: d.__setitem__(len(d) - 1, 0xFE))),
        ("bytes after $FF", "follow the $FF", run_list_edit("main", lambda d: d.extend(b" "))),
        ("$FF before the last run", "follow the $FF", run_list_edit("main", lambda d: d.__setitem__(early, 0xFF))),
        ("run on another row", "declared spans",
         run_list_edit("main", lambda d: d.__setitem__(slice(k, k + 2), bytes((lower & 0xFF, 0x40 | lower >> 8))))),
        ("stale narrow run", "declared spans", lambda r: r["runs"].update(exhibition=narrow.hex())),
        ("run tile not a glyph", "font glyphs", run_list_edit("main", lambda d: d.__setitem__(k + 2, 0x01))),
        ("missing label", "exactly once",
         run_list_edit("main", lambda d: d.__setitem__(slice(label, label + 8), b"ANALYSES"))),
        ("nametable not the main menu", "main menu", hexbytes("nametable", at(shown, 0x20))),
        ("cursor x 241", "cursor entries", hexbytes("cursor", at(0, 241))),
        ("cursor y 224", "cursor entries", hexbytes("cursor", at(1, 224))),
        ("cursor entries 6-8", "repeat the main", hexbytes("cursor", at(12, x0 - 1 if x0 else 1))),
    ]


def oversized(assets, rows):
    """Valid art with `rows` full-width text rows holding the labels: the list space limit."""
    spans = tuple(Span(row, 0, 32) for row in range(rows))
    text = {name: [b" " * 32] * rows for name in MENUS}
    for name in MENUS:
        text[name] = [label.encode().ljust(32) for label in LABELS[name]] + text[name][3:]
    return replace(assets, nametable=b"".join(text["main"]) + b" " * (960 - 32 * rows), spans=spans,
                   menus=tuple(MenuText(name, tuple(text[name])) for name in MENUS))


def test_assets(base, assets):
    record = json.loads(model.ASSETS.read_text())
    assert ModeAssets.parse(record).dumps() == model.ASSETS.read_text(), "the JSON does not round-trip"
    cases = boundary_cases(record)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "assets.json"
        for label, reason, mutate in cases:
            bad = json.loads(json.dumps(record))
            mutate(bad)
            path.write_text(json.dumps(bad))
            try:
                builder.build_rom(base, builder.load_assets(path))
            except AssetError as exc:
                assert reason in str(exc), f"{label}: rejected for another reason: {exc}"
                continue
            raise AssertionError(f"the asset boundary accepted {label}")
    chr_flip = bytearray(assets.chr)
    glyph = assets.font_glyphs[-1]
    chr_flip[16 * glyph] ^= 1
    rejects(builder.build_rom, base, replace(assets, chr=bytes(chr_flip)))
    for change in (dict(chr=assets.chr[:-1]), dict(palette=assets.palette + b"\x0C"), dict(cursor=assets.cursor[:17]),
                   dict(nametable=assets.nametable[:-1]), dict(spans=()), dict(menus=assets.menus[:2])):
        rejects(replace, assets, **change)
    big = builder.build_rom(base, oversized(assets, 26))
    assert len(big) == len(base)
    try:
        builder.build_rom(base, oversized(assets, 27))
    except AssetError as exc:
        assert "past bank 13" in str(exc), exc
    else:
        raise AssertionError("run lists overflowing bank 13 were accepted")
    print(f"asset boundary: the committed JSON round-trips; {len(cases)} malformed records (sizes, hex, keys, glyphs, "
          "palette, spans, run grammar, flags, addresses, terminators, stale runs, labels, cursor) refused at load "
          "with their own error before any ROM byte is built; a glyph differing from CHR $00 and direct short or "
          "long fields are refused; 26 full-width text rows still fit bank 13, 27 are refused")


def find_all(rom, pattern):
    hits = []
    for bank in range(16):
        if bank == 7:            # a stale copy of the stock fixed bank, never mapped
            continue
        origin = 0xC000 if bank == 15 else 0x8000
        data = rom[locate(bank, origin):locate(bank, origin) + 0x4000]
        i = data.find(pattern)
        while i >= 0:
            hits.append((bank, origin + i))
            i = data.find(pattern, i + 1)
    return hits


def pad_trace(rom, request):
    """(bank, pc) of every hop-pad instruction a request executes, rendering off and no NMI."""
    m = Boot(rom)
    m.map_bank(builder.HOME_BANK)
    m.ram[0xAD] = m.ram[0x32] = 0
    trace = []
    for pc in range(builder.PAD, builder.PAD + 16):
        m.on_pc[pc] = lambda mm, pc=pc: trace.append((mm.prg, pc))
    m.call(builder.PAD, a=request)
    return trace, m.prg, m.ram[0x27]


def test_builder(base, rom, assets):
    changed, guards = check_builder(builder, base, rom, owned_banks={1, 13}, owned_chr={model.MODE_CHR})
    stock = read(base, "chr", 0x6000, 0x1000)
    assert hashlib.sha256(stock).hexdigest() == builder.STOCK_CHR06_SHA256
    assert read(rom, "chr", 0x6000, 0x1000) == assets.chr
    code, labels = assemble(builder.far_asm(), builder.CODE)
    pad = builder.hop_pad()
    assert labels["request"] == builder.CODE
    assert pad[7:10] == bytes((0x20, builder.CODE & 0xFF, builder.CODE >> 8)), "the pad does not call the request"
    assert read(rom, 1, builder.PAD, 16) == read(rom, 13, builder.PAD, 16) == pad, "hop pads differ"
    far = read(rom, 13, builder.FAR, 0x1000)
    assert far[:0x400] == assets.nametable + assets.attributes and far[0x400:0x420] == assets.palette
    assert far[builder.CODE - builder.FAR:builder.CODE - builder.FAR + len(code)] == code
    table = far[builder.LISTS - builder.FAR:builder.LISTS - builder.FAR + 6]
    used = set(range(0, 0x420)) | set(range(builder.PAD - builder.FAR, builder.CODE - builder.FAR + len(code)))
    used |= set(range(builder.LISTS - builder.FAR, builder.LISTS - builder.FAR + 6))
    for i, name in enumerate(MENUS):
        start = table[i] | table[3 + i] << 8
        data = assets.run_list(name)
        assert far[start - builder.FAR:start - builder.FAR + len(data)] == data, f"{name} list"
        used |= set(range(start - builder.FAR, start - builder.FAR + len(data)))
    assert all(far[i] == 0xFF for i in range(0x1000) if i not in used), "bank 13 holds stray bytes"
    rest = read(rom, 13, 0x8000, 0x4000)
    assert rest[:0x1000] == b"\xFF" * 0x1000 and rest[0x2000:] == b"\xFF" * 0x2000 and rest[0x1000:0x2000] == far
    stage = {i for r in builder.REGIONS if r.bank == 1 for i in range(locate(1, r.start), locate(1, r.end))}
    program = range(locate(1, 0x9400), locate(1, 0x96A9))
    assert {i for i in program if base[i] != rom[i]} <= stage, "bank 1 $9400-$96A8 changed outside the hooks"
    assert read(rom, 1, 0x95E4, 18) == bytes(v for xy in layout_cursor() for v in xy), "cursor table"
    assert read(rom, 1, builder.DRAW, 8) == bytes.fromhex("A9 00 20 32 94 4C 4B 94")
    for name, addr in builder.TEXT_CALLS.items():
        assert read(rom, 1, addr, 5) == bytes((0xA9, builder.REQUESTS[name], 0x20, 0x32, 0x94)), name
    hop = bytes.fromhex("A9 0D 20 4E C1")
    assert find_all(rom, hop) == [(1, builder.PAD + 1), (13, builder.PAD + 1)] and not find_all(base, hop)
    chr06 = [h for p in ("A9 06 85 25", "A9 06 20 34 C1") for h in find_all(rom, bytes.fromhex(p))]
    old = [h for p in ("A9 06 85 25", "A9 06 20 34 C1") for h in find_all(base, bytes.fromhex(p))]
    select = builder.CODE + code.index(bytes.fromhex("A9 06 85 25"))
    assert sorted(set(chr06) - set(old)) == [(13, select)] and set(old) <= set(chr06), chr06
    expected = [(1, 0x9432), (1, 0x9433), (1, 0x9435), (13, 0x9438), (13, 0x9439), (13, 0x943C), (13, 0x943E),
                (1, 0x9441)]
    for request in range(4):
        trace, prg, shadow = pad_trace(rom, request)
        assert trace == expected and (prg, shadow) == (1, 1), (request, trace, prg, shadow)
    print(f"builder: {changed} changed bytes inside {len(builder.REGIONS)} whole reservations (66 bank-1 bytes, "
          f"bank 13 $9000-$9FFF, CHR $06); every other PRG bank, CHR bank and the header identical; {guards} "
          "dependency, digest and reservation guards (whole fixed bank, bank 13 unused, CHR $00/$06/$17/$19/$1B, "
          "mode program) each reject a one-bit drift; bad manifests rejected; bank-1 and bank-13 pads byte-equal; "
          "requests 0-3 run the pad in bank 1 at $9432-$9435, bank 13 at $9438-$943E and bank 1 at $9441, ending "
          "with PRG and $27 = 1; immediate bank-13 and CHR06 selection patterns occur only in the new code")


# ---------------------------------------------------------------- runtime

def test_overlays(rom, screens):
    """Every source menu to every target menu through the real pad, request and stock walker (rendering off,
    so $C713 flushes each run at once): the target screen exactly, attributes untouched, $06DE-$06E0 intact."""
    pairs = 0
    for source in MENUS:
        for target in MENUS:
            m = Boot(rom)
            m.map_bank(builder.HOME_BANK)
            m.ram[0xAD] = m.ram[0x32] = 0
            for i, value in enumerate(screens[source]):
                m.vram[m.mirror(0x2000 + i)] = value
            m.ram[0x06DE:0x06E1] = bytes((0x91, 0x92, 0x93))
            m.call(builder.PAD, a=builder.REQUESTS[target])
            assert m.nametable() == screens[target], (source, target, first_difference(m.nametable(), screens[target]))
            assert bytes(m.ram[0x06DE:0x06E1]) == bytes((0x91, 0x92, 0x93)) and (m.prg, m.ram[0x27]) == (1, 1)
            pairs += 1
    print(f"overlays: all {pairs} source/target menu pairs through the real pad and stock walker give exactly the "
          "target's layout text; attributes, all other cells and $06DE-$06E0 unchanged")


def test_art_pixels(rom):
    """The ROM's main screen, rendered, reproduces the PNG on every tile outside text cells."""
    png = Image.open(convert.SCENE).convert("RGB")
    upload = read(rom, builder.FAR_BANK, builder.SCREEN, 0x400)
    image = menu.render(read(rom, "chr", 0x6000, 0x1000), upload[:960], upload[960:],
                        read(rom, builder.FAR_BANK, builder.PALETTE, 32))
    texts, static = layout_texts()
    cells = {(col + i, row) for row, col, text in static + [t for name in MENUS for t in texts[name]]
             for i in range(len(text))}
    compared = 0
    for ty in range(30):
        for tx in range(32):
            if (tx, ty) in cells:
                continue
            box = (8 * tx, 8 * ty, 8 * tx + 8, 8 * ty + 8)
            assert image.crop(box).tobytes() == png.crop(box).tobytes(), f"tile ({tx},{ty}) differs from the art"
            compared += 1
    print(f"art: the ROM's CHR $06, upload and palette reproduce mode.png exactly on all {compared} non-text tiles")


def test_title_tail(rom):
    codes = []
    for draw_seed in (0, 0x1234, 0x3FFF):
        for port in (0, 1):
            series = replace(LIVE, draw_seed=draw_seed)
            assert title_tail(rom, series, port) == P.encode(series)
            codes.append(P.encode(series))
    print(f"title tail: v1 and v2 series (seeds 0, $1234, $3FFF) survive post-game, title, START on either "
          f"controller, the new mode-menu draw and CONTINUE; codes {', '.join(sorted(set(codes)))}")


def tour(rom, base, assets, screens):
    """All three menus: every choice, wrap both ways, B back, and the redraw after the picker."""
    d = to_mode_menu(rom)
    m = d.m

    def view(name, entry, label):
        check_view(m, base, assets, screens, name, entry, label)
    view("main", 0, "entry")
    steps = ((1, DOWN), (2, DOWN), (0, DOWN), (2, UP), (1, UP), (0, UP))
    for entry, button in steps:
        d.press(button)
        view("main", entry, f"main choice {entry}")
    d.press(A)
    d.wait(12)
    view("championship", 0, "Championship")
    for entry, button in steps:
        d.press(button)
        view("championship", entry, f"Championship choice {entry}")
    d.press(B)
    d.wait(12)
    view("main", 0, "B from Championship")
    d.press(DOWN)
    d.press(A)
    d.wait(12)
    view("exhibition", 3, "Exhibition")
    for entry, button in steps:
        d.press(button)
        view("exhibition", 3 + entry, f"Exhibition choice {entry}")
    d.press(B)
    d.wait(12)
    view("main", 0, "B from Exhibition")
    d.press(DOWN)
    d.press(DOWN)
    d.press(A)
    pick.in_picker(d)
    d.press(B)
    d.wait_scene(7)
    d.wait(20)
    view("main", 0, "redraw after the picker")
    assert not m.vram_late, f"VRAM or scroll written with rendering on outside vblank: {m.vram_late[:3]}"
    busiest = max(m.vblank_work.values())
    assert busiest < R.VBLANK, busiest
    return busiest


def test_tour(rom, base, assets, screens):
    busiest = tour(rom, base, assets, screens)
    print(f"menus: main, Championship and Exhibition show their layout text, palette, CHR $06/$1B and the four ball "
          f"sprites on all 3 choices, wrapping down and up; B returns to main; the main menu redraws exactly after "
          f"the picker (CHR $19 mapped); every composed frame equals the converter preview; no late VRAM writes; "
          f"busiest modeled vblank {busiest:.1f} of {R.VBLANK:.0f} cycles including OAM DMA (model, not hardware)")


def back_from_picker(d, mode, sub=None):
    choose(d, mode, sub)
    pick.in_picker(d)
    d.press(B)
    d.wait_scene(7)
    d.wait(20)


def test_entries(rom, base, assets, screens):
    routes = 0

    def landed(d, label):
        nonlocal routes
        check_view(d.m, base, assets, screens, "main", 0, label)
        routes += 1
    for port in (0, 1):
        landed(to_mode_menu(rom, port=port), f"START on controller {port + 1}")
    for label, mode, sub in (("START NEW SERIES", 0, 2), ("Exhibition 1P", 1, 0), ("Exhibition 2P", 1, 1),
                             ("Exhibition WATCH", 1, 2), ("Power Analysis", 2, None)):
        d = to_mode_menu(rom)
        back_from_picker(d, mode, sub)
        landed(d, f"picker B from {label}")
    d = to_mode_menu(rom)
    choose(d, 2)
    pick.in_picker(d)
    pick.move_to(d, 27)
    d.press(A, gap=0)
    d.wait_scene(0x15)
    d.wait(60)
    d.press(B)
    pick.in_picker(d)
    d.press(B)
    d.wait_scene(7)
    d.wait(20)
    landed(d, "ratings, then picker B")
    d = to_mode_menu(rom)
    choose(d, 1, sub=1)
    pick.in_picker(d)
    pick.move_to(d, 5)
    d.press(A)
    assert d.m.ram[pick.builder.SIDE] == 1
    d.press(B, port=0)
    assert d.m.ram[pick.builder.SIDE] == 1, "controller 1 went back for player 2"
    d.press(B, port=1)
    assert d.m.ram[pick.builder.SIDE] == 0, "controller 2's B did not return to the first pick"
    d.press(B, port=0)
    d.wait_scene(7)
    d.wait(20)
    landed(d, "2P: controller 2 B, then controller 1 B")
    d = to_mode_menu(rom)
    d.press(A)
    d.wait(12)
    d.press(A)
    d.wait_scene(0x19)
    d.wait(30)
    chr1 = d.m.chr_bank(1)
    d.m.on_pc[0xA475] = lambda mm: mm.prg == 1 and mm.ram.__setitem__(SCENE, 6)   # the $A5BF exit's store
    d.wait_scene(7)
    del d.m.on_pc[0xA475]
    d.wait(20)
    landed(d, f"password entry exit with CHR ${chr1:02X}")
    print(f"entries: {routes} routes land on the exact main menu with its sprites and CHR $06/$1B: START on either "
          "controller; picker B from START NEW SERIES, 1P, 2P, WATCH and Power Analysis; ratings B then picker B; "
          f"2P controller-2 B then controller-1 B; the password screen's scene-6 exit with CHR ${chr1:02X} mapped")


def scene_run(rom, steps, live=None):
    d = Driver(rom, watch=(SCENE,) + OWN)
    d.wait_scene(1)
    d.wait(30)
    if live is not None:
        plant(d.m, live)
    before = series_state(d.m)
    d.press(START)
    d.wait_scene(7)
    d.wait(20)
    for step in steps:
        if step == "wait":
            d.wait(60)
        else:
            d.press(step)
            d.wait(14)
    scenes = [new for (_, addr, _, new, _, _) in d.m.log if addr == SCENE]
    return (scenes, tuple(d.m.ram[a] for a in OWN), [v for _, v in d.m.queue]), before, series_state(d.m), d


def test_exit_parity(base, rom):
    for name, steps in FLOWS.items():
        stock, candidate = scene_run(base, steps)[0], scene_run(rom, steps)[0]
        assert stock == candidate, f"{name}: stock {stock} vs candidate {candidate}"
        assert candidate[2].count(0x06) == 1, f"{name}: song $06 queued {candidate[2].count(0x06)} times"
    print(f"exit parity: all {len(FLOWS)} mode-menu exits (Championship CONTINUE/LIST/NEW, Exhibition 1P/2P/WATCH, "
          "Power Analysis direct and by wrapping, submenu B then Power Analysis) give stock's scene sequence, "
          "mode/ownership bytes $06E0 $BD $04EB $04EC $04E9 $04E2 $04ED $04EE $07ED and every sound request")


def test_series_reentry(base, rom, assets, screens):
    flows = (("Exhibition cancel", [DOWN, A, A, "wait", B, "wait"]),
             ("Power Analysis cancel", [DOWN, DOWN, A, "wait", B, "wait"]),
             ("START NEW SERIES cancel", [A, DOWN, DOWN, A, "wait", B, "wait"]))
    for name, steps in flows:
        stock, _, _, _ = scene_run(base, steps, LIVE)
        candidate, before, after, d = scene_run(rom, steps, LIVE)
        assert stock == candidate, f"{name}: stock {stock} vs candidate {candidate}"
        assert after == before, f"{name}: the series changed"
        assert d.m.ram[SCENE] == 7 and candidate[2].count(0x06) == 1, f"{name}: song restarted or not back"
        check_view(d.m, base, assets, screens, "main", 0, f"{name} re-entry")
    print(f"series: a planted v2 series survives {len(flows)} picker cancels exactly as on stock (scenes, mode bytes, "
          "sound requests); song $06 is never re-queued on re-entry; the main menu redraws exactly")


class Contract(Boot):
    """Boot recording each hop-pad request and every RAM or WRAM write made outside NMIs while one runs."""

    def track(self):
        self.active, self.requests, self.writes = None, [], []
        return self

    def step(self):
        super().step()
        if self.nmi_depth or self.prg != builder.HOME_BANK:
            return
        if self.pc == builder.PAD:
            self.active = (self.mpu.a, self.ram[0x2C])
        elif self.pc == builder.PAD + 15 and self.active is not None:
            self.requests.append((self.active[0], self.prg, self.ram[0x27], self.active[1], self.ram[0x2C]))
            self.active = None

    def __setitem__(self, a, v):
        if getattr(self, "active", None) is not None and not self.nmi_depth and (a < 0x2000 or 0x6000 <= a < 0x8000):
            self.writes.append((a & 0x7FF if a < 0x2000 else a, self.pc, self.prg, self.mpu.sp))
        super().__setitem__(a, v)


def contract_run(rom):
    d = Driver(rom)
    m = d.m
    m.__class__ = Contract
    m.track()
    loop = []
    m.on_pc[0x944F] = lambda mm: mm.prg == 1 and not mm.nmi_depth and loop.append(mm.mpu.sp)
    d.wait_scene(1)
    d.wait(30)
    d.press(START)
    d.wait_scene(7)
    d.wait(20)
    for button in (A, B, DOWN, A, B, DOWN, DOWN):
        d.press(button)
        d.wait(12)
    d.press(A)
    pick.in_picker(d)
    d.press(B)
    d.wait_scene(7)
    d.wait(20)
    return m, set(loop)


def test_contract(base, rom):
    stock, stock_loop = contract_run(base)
    m, loop = contract_run(rom)
    assert not stock.requests and loop == stock_loop, (loop, stock_loop)
    assert [r[0] for r in m.requests] == [0, 2, 1, 3, 1, 0], m.requests
    assert all(r[1:3] == (1, 1) and r[3] == r[4] for r in m.requests), m.requests
    protected = set(SERIES_RAM) | set(MODE_BYTES)
    for addr, pc, prg, sp in m.writes:
        assert addr < 0x2000, f"request wrote WRAM ${addr:04X} at {prg}:${pc:04X}"
        assert addr not in protected, f"request wrote ${addr:04X} at {prg}:${pc:04X}"
        assert addr in CONTRACT or addr == 0x100 + sp, f"request wrote ${addr:04X} at {prg}:${pc:04X}"
    print(f"contract: {len(m.requests)} requests (draw, Championship, main, Exhibition, main, redraw) each return "
          f"in bank 1 with $27 = 1 and $2C balanced; their {len(m.writes)} non-NMI writes stay inside the stock "
          "scratch contract and stack pushes, never series RAM, WRAM, $06E0, $BD or $B8-$BA; the scene-7 loop "
          f"runs at the stock stack pointer ${min(loop):02X}")


def test_audio(base, rom):
    stock, candidate = to_mode_menu(base), to_mode_menu(rom)
    common = max(stock.m.frame, candidate.m.frame)
    for d in (stock, candidate):
        d.wait(common - d.m.frame)
    marks = [len(d.m.apu) for d in (stock, candidate)]
    for d in (stock, candidate):
        d.wait(180)
    idle = [[(f - common, a, v) for f, a, v in d.m.apu[mark:]] for d, mark in zip((stock, candidate), marks)]
    assert idle[0] == idle[1] and idle[0], "idle APU writes differ from stock"
    heard = []
    for d in (stock, candidate):
        ticks, commands = [], []
        d.m.on_pc[0xCF7B] = lambda mm, ticks=ticks: ticks.append(mm.frame)
        for button in (A, DOWN, B, DOWN, A, DOWN, B, UP):
            at = len(d.m.queue)
            d.press(button)
            d.wait(8)
            commands.extend(v for _, v in d.m.queue[at:])
        assert len(ticks) == len(set(ticks)) and ticks == list(range(ticks[0], ticks[-1] + 1)), "audio tick skipped"
        heard.append((commands, len(ticks)))
    assert heard[0][0] == heard[1][0] == [0x35, 0x36, 0x35, 0x36, 0x35, 0x36, 0x35, 0x36], heard
    print(f"audio: {len(idle[0])} APU writes over 180 idle frames equal stock exactly (aligned frames); confirm, move "
          f"and back presses queue stock's $35/$36 requests; one audio tick on each of {heard[1][1]} consecutive "
          "frames through every switch")


def test_pick_flows(rom):
    lines = [pick.flow_exhibition(rom, sub, (31, 27), ports, active=True)
             for sub, ports in ((0, (0, 0)), (1, (0, 1)), (2, (0, 0)))]
    lines += [pick.flow_rules(rom), pick.flow_analysis(rom)]
    for draw_seed in (0, 0x1234, 0x3FFF):
        run_ = pick.cancel_flow(rom, replace(LIVE, draw_seed=draw_seed))
        assert run_["before"] == run_["entered"] == run_["cancelled"] == run_["final"], f"seed {draw_seed:04X}"
        assert run_["prg"] == 11 and not run_["seed_writes"], "CONTINUE missed the bracket, or the seed was written"
    fresh = pick.cancel_flow(rom)
    assert fresh["scene"] == 0x19 and fresh["before"][2] == fresh["cancelled"][2] == b"\x00"
    lines.append("cancel: fresh CONTINUE reaches password entry; v1 and v2 series with draw seeds 0, $1234 and $3FFF "
                 "survive START NEW SERIES, team 31, B and CONTINUE with no seed write")
    for line in lines:
        print(f"pick32 on modeart32: {line}")


# ---------------------------------------------------------------- NMI injection

SWEEPS = (("scene-6 draw", 0x9400, {SCENE: 6}), ("main text", 0x9464, {}),
          ("Championship text", 0x9478, {0x06E0: 0}), ("Exhibition text", 0x9478, {0x06E0: 1}))


def owned(bank, pc):
    return pc in MAPPER or any(bank == b and lo <= pc < hi for b, lo, hi in NEW_CODE)


def template(rom):
    """A machine at the scene-7 handler's entry, outside any NMI, with empty logs."""
    d = to_mode_menu(rom)
    m = d.m
    m.run(lambda mm: mm.mpu.pc == 0x944F and mm.prg == 1 and not mm.nmi_depth and not mm.pending_nmi)
    for log in (m.apu, m.ppu_writes, m.vram_late, m.wram_access, m.mapper, m.partial, m.queue, m.ticks,
                m.tick_marks, m.log, m.shows):
        log.clear()
    m.vblank_work.clear()
    return m


def begin(base_machine, entry, pokes):
    m = copy.deepcopy(base_machine)
    for addr, value in pokes.items():
        m.ram[addr] = value
    ret = (R.STOP - 1) & 0xFFFF
    m.ram[0x100 + m.mpu.sp] = ret >> 8
    m.ram[0x100 + ((m.mpu.sp - 1) & 0xFF)] = ret & 0xFF
    m.mpu.sp = (m.mpu.sp - 2) & 0xFF
    m.mpu.pc = entry
    return m


def inject(m):
    m.pending_nmi = m.vblank = True
    m.vblank_start = m.mpu.processorCycles
    m.next_vblank = m.vblank_start + R.FRAME


def settle(m):
    """Run to the return, then through one more NMI so queued palette and CHR changes land."""
    for _ in range(3_000_000):
        if m.mpu.pc == R.STOP and not m.nmi_depth:
            break
        m.step()
    else:
        raise AssertionError(f"no return; pc ${m.mpu.pc:04X} bank {m.prg}")
    inject(m)
    m.step()
    for _ in range(100_000):
        if m.mpu.pc == R.STOP and not m.nmi_depth:
            break
        m.step()
    else:
        raise AssertionError("the settling NMI did not return")
    return (m.nametable(), m.palette32(), tuple(m.chr), m.prg, m.ram[0x27], bytes(m.ram[0x2C:0x2E]), m.mpu.sp,
            series_state(m), m.ram[SCENE], bytes(m.ram[a] for a in MODE_BYTES), tuple(m.vram_late), m.count)


def sweep(base_machine, entry, pokes):
    """Inject one NMI at the first visit of every new-code or mapper instruction, per guard state."""
    m = begin(base_machine, entry, pokes)
    snapshots = {}
    for _ in range(3_000_000):
        if m.mpu.pc == R.STOP and not m.nmi_depth:
            break
        pc, bank = m.mpu.pc, m.prg
        if not m.nmi_depth and not m.pending_nmi and owned(bank, pc):
            key = (bank if pc < 0xC000 else 15, pc, m.ram[0x2C], m.ram[0x2D])
            snapshots.setdefault(key, copy.deepcopy(m))
        m.step()
    golden = settle(m)
    failures, partial = [], 0
    for key, s in snapshots.items():
        partial += s.count != 0
        inject(s)
        try:
            got = settle(s)
        except (AssertionError, R.Halt) as exc:
            failures.append((key, str(exc)[:80]))
            continue
        if got != golden:
            failures.append((key, [i for i in range(len(got)) if got[i] != golden[i]]))
    return len(snapshots), partial, failures


def test_nmi(rom):
    base_machine = template(rom)
    total = partial = 0
    for label, entry, pokes in SWEEPS:
        cases, cut, failures = sweep(base_machine, entry, pokes)
        assert not failures, f"{label}: {len(failures)} injected NMIs changed the outcome: {failures[:3]}"
        total, partial = total + cases, partial + cut
    print(f"NMI injection: {total} cases, one NMI at the first visit of each new-code and mapper-writer instruction "
          f"per $2C/$2D guard state ({partial} inside an MMC1 serial write) across the scene-6 draw and the main, "
          "Championship and Exhibition text requests; nametable, palette, CHR, PRG and $27, guards, stack, series, "
          "scene and mode bytes settle exactly as without it, with no late VRAM writes and no dangling serial "
          "write (bounded CPU-model probe, not every PPU phase)")


# ---------------------------------------------------------------- negative controls

def patched(rom, edits):
    data = bytearray(rom)
    for offset, value in edits:
        data[offset:offset + len(value)] = value
    return bytes(data)


def far_code_offset(instruction):
    code = assemble(builder.far_asm(), builder.CODE)[0]
    assert code.count(instruction) == 1, instruction.hex()
    return locate(13, builder.CODE) + code.index(instruction)


def narrow_lists(rom):
    """Lists that rewrite only each menu's own text: other menus' text survives a switch."""
    texts, _ = layout_texts()
    lists = []
    for name in MENUS:
        runs = [bytes(((0x2000 + 32 * row + col) & 0xFF, 0x40 | (0x2000 + 32 * row + col) >> 8)) + text.encode()
                for row, col, text in texts[name]]
        lists.append(b"\xFE".join(runs) + b"\xFF")
    starts = [builder.LISTS + 6]
    for data in lists[:-1]:
        starts.append(starts[-1] + len(data))
    edits = [(locate(13, builder.LISTS), bytes(a & 0xFF for a in starts) + bytes(a >> 8 for a in starts))]
    edits += [(locate(13, start), data) for start, data in zip(starts, lists)]
    return patched(rom, edits)


def long_run(rom, tiles):
    """The Championship list's first run widened to `tiles` blanks, the list ending there."""
    table = read(rom, 13, builder.LISTS, 6)
    start = table[1] | table[4] << 8
    head = read(rom, 13, start, 2)
    return patched(rom, [(locate(13, start), head + b" " * tiles + b"\xFF")])


def mode_bytes_after_championship(rom):
    d = to_mode_menu(rom)
    d.m.ram[0x06DE:0x06E0] = bytes((0x5A, 0xA5))
    before = bytes(d.m.ram[0x06DE:0x06E1])
    d.press(A)
    d.wait(12)
    after = bytes(d.m.ram[0x06DE:0x06E1])
    assert after == before, f"Championship text overwrote $06DE-$06E0: {before.hex()} -> {after.hex()}"


def guard_sweep(rom):
    _, _, failures = sweep(template(rom), *SWEEPS[0][1:])
    assert not failures, f"{len(failures)} injected NMIs changed the scene-6 draw"


def test_negative_controls(base, rom, assets, screens):
    def screen_tour(variant):
        tour(variant, base, assets, screens)
    hooks = [(locate(1, a), read(base, 1, a, 5)) for a in builder.TEXT_CALLS.values()]
    chr06 = locate("chr", 0x6000)
    controls = [
        ("stock text call sites", patched(rom, hooks), screen_tour),
        ("stock cursor table", patched(rom, [(locate(1, 0x95E4), read(base, 1, 0x95E4, 18))]), screen_tour),
        ("bank-13 pad one byte off", patched(rom, [(locate(13, builder.PAD + 8), bytes(((builder.CODE + 1) & 0xFF,)))]),
         screen_tour),
        ("stock CHR $06", patched(rom, [(chr06, base[chr06:chr06 + 0x1000])]), screen_tour),
        ("bank 13 left unused", patched(rom, [(locate(13, builder.FAR), b"\xFF" * 0x1000)]), screen_tour),
        ("stale narrow runs", narrow_lists(rom), screen_tour),
        ("draw without selecting CHR $06", patched(rom, [(far_code_offset(bytes.fromhex("A9 06 85 25")),
                                                          b"\xEA" * 4)]), screen_tour),
        ("draw without the $2C guard", patched(rom, [(far_code_offset(bytes.fromhex("E6 2C")), b"\xEA\xEA"),
                                                     (far_code_offset(bytes.fromhex("C6 2C")), b"\xEA\xEA")]),
         guard_sweep),
        ("41 raw tiles", long_run(rom, 41), mode_bytes_after_championship),
        ("43 raw tiles", long_run(rom, 43), mode_bytes_after_championship),
    ]
    mode_bytes_after_championship(rom)
    for label, variant, check in controls:
        try:
            check(variant)
        except (AssertionError, R.Halt) as exc:
            print(f"  negative control {label}: rejected ({str(exc).splitlines()[0][:100]})")
            continue
        raise AssertionError(f"negative control {label} was not detected")
    print(f"negative controls: all {len(controls)} detected; the candidate itself keeps $06DE-$06E0 across the "
          "Championship text")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned title32 input")
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: also re-render and compare the art")
    ap.add_argument("--quick", action="store_true", help="skip the pick32 flows and the NMI injection sweep")
    args = ap.parse_args()
    started = time.monotonic()
    base = args.rom.read_bytes()
    assets = builder.load_assets()
    rom = builder.build_rom(base, assets)
    output = hashlib.sha256(rom).hexdigest()
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    assert output == OUTPUT_SHA256, "modeart32 output differs from the pinned art build"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {output}")
    test_converter(base, args.rom, args.pxl)
    test_converter_cli(args.rom, base, assets)
    test_png_regeneration(base, args.pxl)
    test_protected_names(args.rom)
    test_assets(base, assets)
    test_builder(base, rom, assets)
    sources = [TOOLS / "build_modeart32.py", TOOLS / "modeart32_convert.py", TOOLS / "modeart32_assets.py",
               TOOLS / "test_modeart32.py", model.ASSETS, convert.SCENE, convert.LAYOUT, convert.LOCK,
               TOOLS / "verify.sh", builder.ROOT / "data/title32/titleassets.json",
               builder.ROOT / "art/title32/out/scenes/title.png", builder.ROOT / "data/teams32.json",
               builder.ROOT / "data/menu32/menuassets.json"]
    sources += [convert.SOURCE] if convert.SOURCE.exists() else []
    count = check_output_guards(TOOLS / "build_modeart32.py", args.rom, rom, builder.diff_manifest(base, rom), sources)
    print(f"output guards: deterministic CLI build and manifest from another directory; {count} protected targets "
          "refused (input, renamed copy, tools, assets, layout, PNG, lock, verify.sh, other stages' art and data, "
          "symbolic and hard links); a bad input keeps the previous output")
    screens = oracle_screens(rom)
    test_overlays(rom, screens)
    test_art_pixels(rom)
    test_title_tail(rom)
    test_tour(rom, base, assets, screens)
    test_entries(rom, base, assets, screens)
    test_exit_parity(base, rom)
    test_series_reentry(base, rom, assets, screens)
    test_contract(base, rom)
    test_audio(base, rom)
    if not args.quick:
        test_pick_flows(rom)
        test_nmi(rom)
    test_negative_controls(base, rom, assets, screens)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"modeart32 SHA256 {output}")
    print(f"PASS ({time.monotonic() - started:.1f}s)" + (" quick" if args.quick else ""))


if __name__ == "__main__":
    main()
