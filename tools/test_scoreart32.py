#!/usr/bin/env python3
"""Check the scoreart32 stage: art conversion, the asset boundary, builder guards and the scoreboard at runtime.

    .venv/bin/python tools/test_scoreart32.py build/modeart32.nes --candidate build/scoreart32.nes
    .venv/bin/python tools/test_scoreart32.py build/modeart32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python tools/test_scoreart32.py build/modeart32.nes --quick
    .venv/bin/python tools/test_scoreart32.py build/modeart32.nes --art DIR --assets JSON

Runtime checks run the real scene $0A/$0B code of the modeart32 input and of the built ROM from a
planted game state on tools/scoreart32_machine. Every board the candidate draws must equal, tile
for tile, what the stock rules put at the moved rows (scoreart32_assets.drawn), and the stock ROM
the same rules at its own rows; outside the writer's cells the candidate shows the asset's
background. Team-name sprites, exits, scene writes, sound requests and frame-stamped APU writes,
the cycle budget, the RAM contract and injected NMIs are compared with stock, and negative controls
must fail these same checks. Command-line guards run the real tools from a temporary copy of the
repository, so every hostile alias points at scratch copies. The CPU model counts cycles but its
PPU is approximate: real-core pictures, input, audio and the tournament gates belong to the root
emulator runs. --quick skips the vblank-phase and song variants, the 600-frame final flows, the NMI
sweep and most generated boards.
"""
import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from PIL import Image
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler

import build_scoreart32 as builder
from build_draw32 import locate, padded, read
from frontend32_test_machine import check_builder, check_output_guards, rejects
import menu32_convert as menu
import render_menu32 as R
import scoreart32_assets as model
from scoreart32_assets import GEOMETRY, GLYPHS, STOCK_GEOMETRY, AssetError, ScoreAssets, drawn
import scoreart32_convert as convert
import scoreart32_machine as M
from scoreart32_machine import SAMPLES, Entry, board

ASSETS_SHA256 = "f593b17dcc9a9b5c3c1c81da1be8d2419982f4183f387ae79b4e8b09cdbe0d01"
OUTPUT_SHA256 = "2ae1a7ab2f75aeea4287943ba8153ab0ee0cc188a3d9a67f64bf7398f9e3360a"
# The frozen final art lane's data/scoreassets.json (SHA-256 6ca8f7ff...) holds these exact parts.
ART_LANE_PARTS = {"palette": "df96c40bfcd799b8733df4b6b770a6f056eddf98e61aefadf71217c6cd42a5c7",
                  "chr": "958854c1906be527aac9de00b3cd7ddb5a3933cc5d401674bbd177037e0521c8",
                  "nametable": "b56db13c8d855558138f48cf49ade5ded4568b6aac951ba2eee3d2922b9c0596",
                  "attributes": "50c249653b7e9c4571ac5d6e820506c11a9c1dbcf3685fc6340e6e4b3485bf86"}
TOOLS = Path(__file__).resolve().parent
ROOT = builder.ROOT
TAPS = lambda frame: R.A if frame % 32 < 4 else 0                # noqa: E731
HELD_A = lambda frame: R.A                                       # noqa: E731
HELD_OTHERS = lambda frame: R.A | R.B | R.SELECT | R.START       # noqa: E731
DRAW_CONTRACT = {0x00, 0x01, 0x25, 0x2C, 0x32, 0xAD} | set(range(0x0195, 0x01B6))
SCRATCH = (set(range(0x00, 0x10)) | {0x14, 0x15, 0x16, 0x17, 0x2E, 0x35, 0x36, 0x37, 0x38}
           | set(range(0x0100, 0x0200)) | set(range(0x0340, 0x0400)))
EARLIER = ("direct31", "direct31-pair36", "gameplay32", "cpu32", "teamtables32", "roles32", "results32", "control32",
           "password32", "teamnames32", "visualtables32", "menuart32", "draw32", "pick32", "title32", "modeart32")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patched(data, edits):
    out = bytearray(data)
    for offset, value in edits:
        out[offset:offset + len(value)] = value
    return bytes(out)


def code_offset(instruction):
    code = builder.draw_code()
    assert code.count(instruction) == 1, instruction.hex()
    return locate(builder.BANK, builder.CODE) + code.index(instruction)


def expect_failure(check, *args):
    try:
        check(*args)
    except (AssertionError, R.Halt) as exc:
        return str(exc).splitlines()[0][:110]
    raise AssertionError(f"{getattr(check, '__name__', check)} accepted a broken candidate")

# ---------------------------------------------------------------- the asset boundary


def boundary_cases(record, assets):
    """(label, expected reason, mutation of the JSON record)."""
    nametable = bytes.fromhex(record["nametable"])
    art = sorted(set(nametable) - set(GLYPHS))
    inked = next(t for t in art if any(assets.pattern(t)))
    free = next(t for t in range(256) if t not in GLYPHS and t not in nametable)
    empty = next(t for t in sorted(GLYPHS) if t != model.BLANK and not any(assets.pattern(t)))
    other = next(t for t in art if t != inked)

    def field(key, edit):
        return lambda r: r.update({key: edit(bytearray.fromhex(r[key])).hex()})

    def at(index, value):
        def edit(data):
            data[index] = value
            return data
        return edit

    def tile(t, pattern):
        return field("chr", lambda d: d.__setitem__(slice(16 * t, 16 * t + 16), pattern) or d)

    def cell(col, row, t):
        return field("nametable", at(32 * row + col, t))
    offset, shift = menu.attr_slot(8, 8)
    return [
        ("format", "expected scoreassets/1", lambda r: r.update(format="scoreassets/2")),
        ("CHR bank", "expected scoreassets/1", lambda r: r.update(chr_bank=6)),
        ("CHR bank as a flag", "expected scoreassets/1", lambda r: r.update(chr_bank=True)),
        ("missing key", "exactly the keys", lambda r: r.pop("palette")),
        ("art-lane layout key", "exactly the keys", lambda r: r.update(layout="b")),
        ("short CHR", "chr must be exactly 4096", lambda r: r.update(chr=r["chr"][:-2])),
        ("long CHR", "chr must be exactly 4096", lambda r: r.update(chr=r["chr"] + "00")),
        ("short nametable", "nametable must be exactly 960", lambda r: r.update(nametable=r["nametable"][:-2])),
        ("long nametable", "nametable must be exactly 960", lambda r: r.update(nametable=r["nametable"] + "e8")),
        ("short attributes", "attributes must be exactly 64", lambda r: r.update(attributes=r["attributes"][:-2])),
        ("long attributes", "attributes must be exactly 64", lambda r: r.update(attributes=r["attributes"] + "00")),
        ("short palette", "palette must be exactly 32", lambda r: r.update(palette=r["palette"][:-2])),
        ("long palette", "palette must be exactly 32", lambda r: r.update(palette=r["palette"] + "0c")),
        ("uppercase hex", "lowercase hex", lambda r: r.update(chr=r["chr"].upper())),
        ("odd hex", "lowercase hex", lambda r: r.update(palette=r["palette"] + "0")),
        ("list instead of hex", "lowercase hex", lambda r: r.update(palette=list(bytes.fromhex(r["palette"])))),
        ("tiles_used off by one", "tiles_used", lambda r: r.update(tiles_used=r["tiles_used"] + 1)),
        ("tiles_used as text", "tiles_used", lambda r: r.update(tiles_used=str(r["tiles_used"]))),
        ("sources as a list", "sources must map", lambda r: r.update(sources=list(r["sources"]))),
        ("source missing", "sources must name exactly", lambda r: r["sources"].pop("PXL.json")),
        ("unknown source", "sources must name exactly",
         lambda r: r["sources"].update({"out/sprites/dad.png": "0" * 64})),
        ("art-lane source key", "sources must name exactly",
         lambda r: r["sources"].update({"scenes/score.png": r["sources"].pop("out/scenes/score.png")})),
        ("uppercase digest", "lowercase SHA-256", lambda r: r["sources"].update({"layout.json": "A" * 64})),
        ("short digest", "lowercase SHA-256", lambda r: r["sources"].update({"layout.json": "0" * 63})),
        ("palette color $0D", "supported NES colors", field("palette", at(1, 0x0D))),
        ("palette color $40", "supported NES colors", field("palette", at(1, 0x40))),
        ("two backdrops", "one backdrop", field("palette", at(20, 0x0F))),
        ("repeated palette color", "three distinct colors", field("palette", at(2, assets.palette[1]))),
        ("backdrop inside a palette", "three distinct colors", field("palette", at(3, assets.palette[0]))),
        ("inked header blank", "header blank $E8 must be blank", tile(model.BLANK, b"\xFF" + bytes(15))),
        ("blank big 3", "every big glyph needs ink",
         lambda r: [tile(t, bytes(16))(r) for t in model.big(3)]),
        ("narrow 7 copies narrow 1", "narrow glyphs must differ",
         lambda r: [tile(t, assets.pattern(s))(r) for t, s in zip(model.narrow(7), model.narrow(1))]),
        ("header 3 copies header 8", "header glyphs must differ",
         tile(model.HEADER["3"], assets.pattern(model.HEADER["8"]))),
        ("stray bytes in a free tile", "neither a glyph nor drawn must be zero", tile(free, b"\x01" + bytes(15))),
        ("two art tiles alike", "no other tile or glyph holds", tile(other, assets.pattern(inked))),
        ("art tile copies a glyph", "no other tile or glyph holds", tile(inked, assets.pattern(0x41))),
        ("writer cell inked", "writer cell (8,8) must be blank", cell(8, 8, inked)),
        ("name cell inked", "name sprite cell (2,9) must be blank", cell(2, 9, inked)),
        (f"blank cell as glyph ${empty:02X}", f"must use glyph ${model.BLANK:02X}", cell(0, 29, empty)),
        ("writer palette 1", "must use palette 0",
         field("attributes", lambda d: d.__setitem__(offset, d[offset] | 1 << shift) or d)),
        ("attribute bits below the screen", "below the screen must be zero", field("attributes", at(60, 0x40))),
    ]


def test_assets(base, assets, path):
    text = Path(path).read_text()
    assert ScoreAssets.parse(json.loads(text)).dumps() == text, "the JSON does not round-trip"
    cases = boundary_cases(json.loads(text), assets)
    with tempfile.TemporaryDirectory() as temporary:
        bad = Path(temporary) / "assets.json"
        for label, reason, mutate in cases:
            record = json.loads(text)
            mutate(record)
            bad.write_text(json.dumps(record))
            try:
                builder.build_rom(base, builder.load_assets(bad))
            except AssetError as exc:
                assert reason in str(exc), f"{label}: rejected for another reason: {exc}"
                continue
            raise AssertionError(f"the asset boundary accepted {label}")
    for change in (dict(chr=assets.chr[:-1]), dict(nametable=assets.nametable + b"\xE8"),
                   dict(palette=assets.palette[:31]), dict(sources=assets.sources[1:]), dict(tiles_used=255)):
        rejects(replace, assets, **change)
    print(f"asset boundary: the JSON round-trips; {len(cases)} malformed records (format, keys, sizes, hex, counts, "
          "source pins, palettes, glyph ink and uniqueness, padding, art-tile uniqueness, blank writer and name cells, "
          "the $E8 blank, palette 0 under the writer, bits below the screen) refused at load with their own error "
          "before any ROM byte is built; direct bad fields refused")

# ---------------------------------------------------------------- the converter


def edit_png(path, spots):
    image = Image.open(path).convert("RGBA")
    for xy, rgba in spots:
        image.putpixel(xy, rgba)
    image.save(path)


def rgb(color):
    return menu.NES_RGB[color] + (255,)


def converted(base, art, mutate_layout=None, mutate_art=None):
    with tempfile.TemporaryDirectory() as temporary:
        copy = Path(temporary) / "art"
        shutil.copytree(art, copy)
        if mutate_layout:
            layout = json.loads((copy / "layout.json").read_text())
            mutate_layout(layout)
            (copy / "layout.json").write_text(json.dumps(layout))
        if mutate_art:
            mutate_art(copy)
        return convert.convert(base, copy)


def converter_cases(base, art, assets):
    layout = json.loads((Path(art) / "layout.json").read_text())
    backdrop, p0 = layout["backdrop"], [int(c, 16) for c in layout["palettes"][0]]
    outside = next(int(c, 16) for p in layout["palettes"] for c in p if int(c, 16) not in p0)
    cream = next(c for c in p0 if all(f"{c:02X}" in p for p in layout["palettes"]))
    scene = lambda a: a / convert.SCENE                                     # noqa: E731
    sprite = lambda a, name: a / f"out/sprites/{name}.png"                  # noqa: E731
    reserved = GEOMETRY.writer_cells() | GEOMETRY.name_cells()
    blank_cells = [(i % 32, i // 32) for i, t in enumerate(assets.nametable) if t == model.BLANK
                   and (i % 32, i // 32) not in reserved
                   and (i % 32 // 2, i // 32 // 2) not in GEOMETRY.glyph_attribute_cells()]
    picture = Image.open(Path(art) / convert.SCENE).convert("RGB")
    navy = menu.NES_RGB[int(backdrop, 16)]
    sx, sy = next((x, y) for ax, ay in sorted(GEOMETRY.glyph_attribute_cells())
                  for y in range(16 * ay, 16 * ay + 16) for x in range(16 * ax, 16 * ax + 16)
                  if (x // 8, y // 8) not in reserved and picture.getpixel((x, y)) == navy)
    first_text = layout["text"][0]
    rom_font = menu.font_patterns(base)
    unprintable = next(chr(i) for i in range(0x21, 0x7F) if not any(rom_font[i]))

    def text(entry):
        return lambda lay: lay["text"].append(entry)

    def entry(**change):
        return lambda lay: lay["text"][0].update(change)

    def copy_glyph(name, width, source, target):
        def edit(a):
            image = Image.open(sprite(a, name)).convert("RGBA")
            image.paste(image.crop((width * source, 0, width * source + width, image.size[1])), (width * target, 0))
            image.save(sprite(a, name))
        return edit
    four = [int(c, 16) for p in layout["palettes"] for c in p]
    four = [c for i, c in enumerate(four) if c not in four[:i]][:4]
    x0, y0 = 8 * blank_cells[0][0], 8 * blank_cells[0][1]
    return [
        ("unknown color", "not a palette color", None, lambda a: edit_png(scene(a), [((x0, y0), (1, 2, 3, 255))])),
        ("partial alpha", "transparency", None, lambda a: edit_png(scene(a), [((x0, y0), rgb(cream)[:3] + (128,))])),
        ("wrong scene size", "expected 256x240", None,
         lambda a: Image.new("RGBA", (256, 224), rgb(int(backdrop, 16))).save(scene(a))),
        ("painted writer cell", "the art paints", None, lambda a: edit_png(scene(a), [((67, 67), rgb(cream))])),
        ("painted name cell", "the art paints", None, lambda a: edit_png(scene(a), [((19, 75), rgb(cream))])),
        ("text over art", "art under", lambda lay: lay["text"].append(dict(first_text)), None),
        ("text inks a writer cell", "inks writer or name cell", text({"x": 64, "y": 64, "text": "AB", "font": "menu",
                                                                       "color": f"{cream:02X}"}), None),
        ("text off the screen", "runs off the screen", text({"x": 254, "y": 0, "text": "A", "font": "menu",
                                                               "color": f"{cream:02X}"}), None),
        ("mini letter missing", "mini font has no glyph", entry(text="Z", font="mini"), None),
        ("menu letter missing", "CHR $00 has no glyph", entry(text=unprintable), None),
        ("text color in no palette", "in no background palette", entry(color="30"), None),
        ("unknown font", "font must be one of", entry(font="wide"), None),
        ("text with an advance", "must hold exactly color, font, text, x and y", entry(advance=7), None),
        ("text per layout", "one list", lambda lay: lay.update(text={"b": lay["text"]}), None),
        ("non-ASCII text", "printable ASCII", entry(text="É"), None),
        ("layout format /1", "unknown layout format", lambda lay: lay.update(format="scoreart32-layout/1"), None),
        ("unknown layout key", "layout keys must be", lambda lay: lay.update(header_color="28"), None),
        ("three palettes", "four palettes", lambda lay: lay["palettes"].pop(), None),
        ("backdrop in a palette", "besides the backdrop",
         lambda lay: lay["palettes"][1].__setitem__(0, backdrop), None),
        ("unsupported color", "unsupported NES color", lambda lay: lay["palettes"][2].__setitem__(0, "0D"), None),
        ("attribute conflict", "fit no palette", None,
         lambda a: edit_png(scene(a), [((x0 + i, y0), rgb(c)) for i, c in enumerate(four)])),
        ("palette 0 conflict under the writer", "holds writer cells, so palette 0", None,
         lambda a: edit_png(scene(a), [((sx, sy), rgb(outside))])),
        ("glyph color outside palette 0", "not a palette color", None,
         lambda a: edit_png(sprite(a, "big"), [((0, 0), rgb(outside))])),
        ("narrow sheet size", "expected 88x16", None,
         lambda a: Image.open(sprite(a, "narrow")).crop((0, 0, 80, 16)).save(sprite(a, "narrow"))),
        ("head blank inked", "header blank after 9 must be backdrop", None,
         lambda a: edit_png(sprite(a, "head"), [((84, 3), rgb(p0[1]))])),
        ("missing head sprite", "lacks out/sprites/head.png", None, lambda a: sprite(a, "head").unlink()),
        ("missing pxl pin", "lacks PXL.json", None, lambda a: (a / "PXL.json").unlink()),
        ("narrow 7 copies narrow 1", "narrow glyphs must differ", None, copy_glyph("narrow", 8, 1, 7)),
        ("big 3 erased", "every big glyph needs ink", None,
         lambda a: (lambda image: (image.paste(rgb(int(backdrop, 16)), (48, 0, 64, 16)),
                                   image.save(sprite(a, "big"))))(Image.open(sprite(a, "big")).convert("RGBA"))),
        ("tile budget", "CHR $05 is full", None,
         lambda a: edit_png(scene(a), [((8 * c + i, 8 * r + 2), rgb(cream))
                                       for i, (c, r) in enumerate(blank_cells[:3])])),
    ]


def test_converter(base, art, assets, path, pxl):
    first, second = convert.convert(base, art), convert.convert(base, art)
    text = first.dumps()
    assert text == second.dumps(), "converter output is not deterministic"
    assert text == Path(path).read_text(), f"{path} is stale"
    assert first == assets
    parts = {part: sha256(getattr(first, part)) for part in ART_LANE_PARTS}
    assert parts == ART_LANE_PARTS, f"the conversion differs from the frozen art lane's bytes: {parts}"
    assert first.sources == tuple((name, sha256((Path(art) / name).read_bytes())) for name in model.SOURCES)
    blank = [t for t in sorted(GLYPHS) if not any(first.pattern(t))]
    plain = sum(1 for t in first.nametable if not any(first.pattern(t)))
    assert plain and all(t == model.BLANK for t in first.nametable if not any(first.pattern(t)))
    reproduced = convert.check_pxl(pxl, art) if pxl else 0
    cases = converter_cases(base, art, assets)
    for label, reason, mutate_layout, mutate_art in cases:
        try:
            converted(base, art, mutate_layout, mutate_art)
        except AssetError as exc:
            assert reason in str(exc), f"{label}: rejected for another reason: {exc}"
            continue
        raise AssertionError(f"converter accepted {label}")
    rejects(convert.convert, patched(base, [(16, b"\x00")]), art)
    print(f"converter: deterministic; {Path(path).name} current; palette, CHR, nametable and attributes equal the "
          f"frozen art lane's bytes ({first.tiles_used} tiles, {first.tiles_used - len(GLYPHS)} art, "
          f"{256 - first.tiles_used} free); all {plain} plain cells use ${model.BLANK:02X} although "
          f"{', '.join(f'${t:02X}' for t in blank if t != model.BLANK)} are blank too; {len(cases)} bad layouts, "
          "PNGs and sprites rejected, each for its own reason; another ROM refused"
          + (f"; pinned pxl reproduces all {reproduced} PNGs, twice" if pxl else "; pxl re-render not run (no --pxl)"))

# ---------------------------------------------------------------- command lines in a temporary checkout


@contextmanager
def checkout(base, art, path):
    """A scratch copy of tools, art and data, with the art and asset under test at their conventional paths."""
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        root = scratch / "repo"
        root.mkdir()
        shutil.copytree(TOOLS, root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "art", root / "art", ignore=shutil.ignore_patterns("scoreart32"))
        shutil.copytree(ROOT / "data", root / "data", ignore=shutil.ignore_patterns("scoreart32"))
        shutil.copytree(art, root / "art/scoreart32")
        (root / "data/scoreart32").mkdir()
        shutil.copyfile(path, root / "data/scoreart32/scoreassets.json")
        (root / "build").mkdir()
        (root / "build/modeart32.nes").write_bytes(base)
        (root / "docs").mkdir()
        (root / "docs/notes.md").write_text("docs stay intact\n")
        elsewhere = scratch / "elsewhere"
        elsewhere.mkdir()
        yield root, elsewhere


def snapshot(*roots):
    """Every entry: kind, content digest or link target, inode, mode and modification time."""
    seen = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if "__pycache__" in path.parts:
                continue
            st = path.lstat()
            if path.is_symlink():
                seen[path] = ("link", os.readlink(path), st.st_ino, st.st_mode, st.st_mtime_ns)
            elif path.is_file():
                seen[path] = ("file", sha256(path.read_bytes()), st.st_ino, st.st_mode, st.st_mtime_ns)
            else:
                seen[path] = ("dir",)
    return seen


def run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def refused(result, target=None):
    assert result.returncode == 2 and "output aliases protected" in result.stderr, (target, result.stderr)


def test_converter_cli(base, assets, art, path):
    with checkout(base, art, path) as (root, elsewhere):
        tools, rom = root / "tools", root / "build/modeart32.nes"
        cli = [sys.executable, "-B", str(tools / "scoreart32_convert.py"), "--rom", str(rom)]
        canonical = root / "data/scoreart32/scoreassets.json"
        output, preview = elsewhere / "assets.json", elsewhere / "preview.png"
        result = run(cli + ["--out", str(output), "--preview", str(preview)], elsewhere)
        assert result.returncode == 0 and output.read_text() == canonical.read_text(), result.stderr
        assert Image.open(preview).convert("RGB").tobytes() == convert.preview(assets).tobytes()
        for args in (["--out", str(output), "--check"], ["--check"]):
            result = run(cli + args, elsewhere)
            assert result.returncode == 0 and "checked" in result.stdout, result.stderr
        missing, unwanted = elsewhere / "missing.json", elsewhere / "unwanted.png"
        result = run(cli + ["--out", str(missing), "--check"], elsewhere)
        assert result.returncode == 2 and "stale" in result.stderr and not missing.exists(), result.stderr
        result = run(cli + ["--out", str(output), "--check", "--preview", str(unwanted)], elsewhere)
        assert result.returncode == 2 and not unwanted.exists(), result.stderr
        stale = output.read_text().replace('"tiles_used": ', '"tiles_used": 1')
        output.write_text(stale)
        before = snapshot(root, elsewhere)
        result = run(cli + ["--out", str(output), "--check"], elsewhere)
        assert result.returncode == 2 and "stale" in result.stderr, result.stderr
        assert snapshot(root, elsewhere) == before, "a refused --check changed a file"
        bad = elsewhere / "other-input.nes"
        bad.write_bytes(patched(base, [(0x20, b"\x00")]))
        result = run([sys.executable, "-B", str(tools / "scoreart32_convert.py"), "--rom", str(bad), "--out",
                      str(elsewhere / "never.json")], elsewhere)
        assert result.returncode == 2 and "pinned modeart32" in result.stderr, result.stderr
        assert not (elsewhere / "never.json").exists()

        renamed = elsewhere / "renamed-input.nes"
        renamed.write_bytes(base)
        a = root / "art/scoreart32"
        targets = [rom, renamed, tools / "verify.sh", a / "score32.px.js", a / "layout.json", a / "PXL.json",
                   a / "out/scenes/score.png", a / "out/sprites/head.png", a / "out/sprites/cart.png",
                   tools / "scoreart32_convert.py", tools / "build_scoreart32.py", tools / "scoreart32_assets.py",
                   tools / "scoreart32_machine.py", tools / "test_scoreart32.py", tools / "build_modeart32.py",
                   root / "data/teams32.json", root / "data/modeart32/modeassets.json",
                   root / "data/menu32/menuassets.json", root / "art/modeart32/out/scenes/mode.png",
                   root / "docs/notes.md", a / "out/sprites/missing.png", a / "notes.json"]
        for i, target in enumerate((rom, a / "out/scenes/score.png", root / "data/teams32.json", a / "layout.json")):
            symbolic, hard = elsewhere / f"alias{i}-symlink", elsewhere / f"alias{i}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets += [symbolic, hard]
        before = snapshot(root, elsewhere)
        for target in targets:
            for option in (["--out", str(target)], ["--out", str(output), "--preview", str(target)]):
                refused(run(cli + option, elsewhere), target)
        assert snapshot(root, elsewhere) == before, "a refused output changed a file"
        same = elsewhere / "same.out"
        refused(run(cli + ["--out", str(same), "--preview", str(same)], elsewhere))
        refused(run(cli + ["--out", str(output), "--preview", str(canonical)], elsewhere))
        assert not same.exists() and snapshot(root, elsewhere) == before

        result = run(cli, elsewhere)
        assert result.returncode == 0 and canonical.read_text() == Path(path).read_text(), result.stderr
        link = elsewhere / "assets-link.json"
        link.symlink_to(canonical)
        kept = snapshot(root)
        result = run(cli + ["--out", str(link)], elsewhere)
        assert result.returncode == 0 and not link.is_symlink() and link.read_text() == canonical.read_text()
        assert snapshot(root) == kept, "writing a link to the canonical JSON wrote through it"
        canonical.unlink()
        canonical.symlink_to(root / "data/teams32.json")
        teams = (root / "data/teams32.json").read_bytes()
        refused(run(cli, elsewhere))
        assert (root / "data/teams32.json").read_bytes() == teams
    print(f"converter CLI (temporary checkout): --out and --preview from another directory; --check passes current "
          f"JSON and refuses stale or missing JSON, --check --preview and another ROM, writing nothing; "
          f"{len(targets)} protected targets refused as --out and as --preview with every file, inode, mode and "
          "time unchanged (inputs, a renamed input, verify.sh, tools, art sources and PNGs, data, docs, earlier "
          "art, links, and files not yet created inside the art directory); --out equal to --preview and a "
          "preview over the canonical JSON refused; a link to the canonical JSON is replaced, not written through; "
          "a canonical path resolving onto another data file refused")


def test_builder_cli(base, rom, assets, art, path):
    with checkout(base, art, path) as (root, elsewhere):
        tools = root / "tools"
        a = root / "art/scoreart32"
        sources = [tools / name for name in ("build_scoreart32.py", "scoreart32_convert.py", "scoreart32_assets.py",
                                             "scoreart32_machine.py", "test_scoreart32.py", "verify.sh",
                                             "build_modeart32.py")]
        sources += [root / "data/scoreart32/scoreassets.json", root / "data/modeart32/modeassets.json",
                    root / "data/teams32.json", a / "score32.px.js", a / "layout.json", a / "PXL.json",
                    a / "out/scenes/score.png", a / "out/sprites/big.png", root / "docs/notes.md",
                    root / "art/title32/out/scenes/title.png"]
        count = check_output_guards(tools / "build_scoreart32.py", root / "build/modeart32.nes", rom,
                                    builder.diff_manifest(base, rom, assets), sources)
        cli = [sys.executable, "-B", str(tools / "build_scoreart32.py"), str(root / "build/modeart32.nes")]
        before = snapshot(root, elsewhere)
        refused(run(cli + ["-o", str(a / "out/sprites/new.png")], elsewhere))
        bad = elsewhere / "bad.json"
        record = json.loads(Path(path).read_text())
        record["tiles_used"] += 1
        bad.write_text(json.dumps(record))
        out = elsewhere / "never.nes"
        result = run(cli + ["-o", str(out), "--assets", str(bad)], elsewhere)
        assert result.returncode == 2 and "tiles_used" in result.stderr and not out.exists(), result.stderr
        refused(run(cli + ["-o", str(bad), "--assets", str(bad)], elsewhere))
        assert snapshot(root) == {k: v for k, v in before.items() if k.is_relative_to(root)}
        result = run(cli + ["-o", str(out), "--assets", str(root / "data/scoreart32/scoreassets.json")], elsewhere)
        assert result.returncode == 0 and out.read_bytes() == rom and OUTPUT_SHA256 in result.stdout, result.stderr
    print(f"builder CLI (temporary checkout): deterministic build and manifest from another directory; {count} "
          "protected targets refused (input, renamed copy, tools, assets, art, PNGs, verify.sh, data, docs, "
          "earlier art, symbolic and hard links); a bad input keeps the previous output; an output inside the art "
          "directory, a malformed --assets and an output over --assets refused; --assets builds the pinned ROM")


def test_regeneration(base, assets, art, path, pxl):
    """install_pngs refuses every alias before any copy; with --pxl, the real CLI too."""
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        rom = directory / "modeart32.nes"
        rom.write_bytes(base)
        art_copy = directory / "art"
        shutil.copytree(art, art_copy)
        staging = directory / "rendered"
        shutil.copytree(art_copy / "out", staging)
        target_root = art_copy / "out"
        trap = target_root / "sprites/dad.png"
        early = target_root / "scenes/score.png"
        output, preview = directory / "assets.json", directory / "preview.png"
        output.write_bytes(b"previous JSON")
        preview.write_bytes(b"previous preview")
        data = directory / "protected.json"
        data.write_text("data stays intact")
        protected = (rom, art_copy / "score32.px.js", art_copy / "layout.json", data, output, preview, early)
        cases = 0
        with patch.object(convert, "ASSETS", data):
            for victim in protected:
                for symbolic in (False, True):
                    trap.unlink(missing_ok=True)
                    trap.symlink_to(victim) if symbolic else os.link(victim, trap)
                    before = snapshot(directory)
                    rejects(convert.install_pngs, staging, target_root, rom, art_copy, (output, preview))
                    assert snapshot(directory) == before, f"refusing {victim} changed a file"
                    cases += 1
            trap.unlink()
            for collision in (output, preview):
                outputs = tuple(trap if p == collision else p for p in (output, preview))
                before = snapshot(directory)
                rejects(convert.install_pngs, staging, target_root, rom, art_copy, outputs)
                assert not trap.exists() and snapshot(directory) == before
            neighbor = directory / "unrelated.png"
            neighbor.write_bytes(b"unrelated inode")
            os.link(neighbor, trap)
            installed = convert.install_pngs(staging, target_root, rom, art_copy, (output, preview))
        assert neighbor.read_bytes() == b"unrelated inode" and not trap.samefile(neighbor)
        assert all((target_root / p).read_bytes() == (staging / p).read_bytes() for p in installed)
    line = (f"PNG regeneration: {cases} symbolic and hard aliases of inputs, sources, data, outputs and an earlier "
            "PNG refused before any copy; a missing PNG chosen as the JSON or preview output refused without "
            f"creating it; atomic replacement of all {len(installed)} PNGs leaves an unrelated linked inode intact")
    if pxl:
        line += "; " + regeneration_cli(base, art, path, pxl)
    print(line)


def regeneration_cli(base, art, path, pxl):
    with checkout(base, art, path) as (root, elsewhere):
        a = root / "art/scoreart32"
        rom = root / "build/modeart32.nes"
        cli = [sys.executable, "-B", str(root / "tools/scoreart32_convert.py"), "--rom", str(rom), "--pxl", str(pxl)]
        trap = a / "out/sprites/dad.png"
        dad = trap.read_bytes()
        for symbolic in (False, True):
            trap.unlink()
            trap.symlink_to(rom) if symbolic else os.link(rom, trap)
            before = snapshot(root)
            refused(run(cli, elsewhere))
            assert snapshot(root) == before and rom.read_bytes() == base, "regeneration wrote through an alias"
        trap.unlink()
        trap.write_bytes(dad)
        cart = a / "out/sprites/cart.png"
        cart.unlink()
        for option in ("--out", "--preview"):
            before = snapshot(root, elsewhere)
            args = ["--out", str(cart)] if option == "--out" else ["--out", str(elsewhere / "a.json"), "--preview",
                                                                    str(cart)]
            refused(run(cli + args, elsewhere))
            assert not cart.exists() and snapshot(root, elsewhere) == before, option
        committed = {p: p.read_bytes() for p in (Path(art) / "out").rglob("*.png")}
        result = run(cli + ["--out", str(elsewhere / "regenerated.json")], elsewhere)
        assert result.returncode == 0, result.stderr
        assert {p.relative_to(a / "out"): p.read_bytes() for p in (a / "out").rglob("*.png")} == \
            {p.relative_to(Path(art) / "out"): data for p, data in committed.items()}, "regeneration changed a PNG"
        assert (elsewhere / "regenerated.json").read_text() == Path(path).read_text()
        before = snapshot(root, elsewhere)
        result = run([*cli, "--check"], elsewhere)
        assert result.returncode == 0 and "reproduces" in result.stdout and snapshot(root, elsewhere) == before
        edit_png(cart, [((0, 0), rgb(0x16))])
        extra = a / "out/sprites/extra.png"
        for change, reason in ((lambda: None, "differs from the pinned pxl render"),
                               (lambda: shutil.copyfile(trap, extra), "hold different PNG files")):
            change()
            before = snapshot(root, elsewhere)
            result = run([*cli, "--check"], elsewhere)
            assert result.returncode == 2 and reason in result.stderr and snapshot(root, elsewhere) == before
        lock = json.loads((a / "PXL.json").read_text())
        lock["commit"] = "0" * 40
        (a / "PXL.json").write_text(json.dumps(lock))
        result = run([*cli, "--check"], elsewhere)
        assert result.returncode == 2 and "not the pinned" in result.stderr
    return ("real --pxl CLI in a temporary checkout: hard and symbolic PNG aliases of the ROM refused with nothing "
            "written; a missing PNG as --out or --preview refused; regeneration from another directory reproduces "
            "every PNG and the JSON; --check --pxl writes nothing and refuses an edited PNG, an extra PNG and "
            "another pxl commit")


def test_protected_names(rom_path):
    targets = [ROOT / "Little League Baseball - Championship Series (USA).nes"]
    targets += [ROOT / "build" / f"{stage}.nes" for stage in EARLIER]
    targets += [Path(rom_path).resolve().parent / f"{stage}.nes" for stage in ("title32", "modeart32")]
    for target in targets:
        rejects(builder.protect_output, rom_path, target)
        rejects(convert.protect_output, rom_path, target)
    builder.protect_output(rom_path, ROOT / "build/scoreart32.nes")
    print(f"protected names: the original ROM and {len(targets) - 1} earlier-stage ROM paths are refused as builder "
          "and converter outputs; build/scoreart32.nes stays writable")

# ---------------------------------------------------------------- the builder


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


def test_builder(base, rom, assets):
    changed, guards = check_builder(builder, base, rom, owned_banks={builder.BANK}, owned_chr={model.SCORE_CHR})
    region = {r.name: r for r in builder.REGIONS}
    assert read(rom, 4, builder.HOOK, 20) == bytes.fromhex("20 00 B8 4C D4 B3") + b"\xEA" * 14
    assert read(base, 4, builder.HOOK, 20) == bytes.fromhex(builder.STOCK_DRAW_CALL)
    for name, table in (("header-address", GEOMETRY.header_operand()), ("line-rows", GEOMETRY.line_table()),
                        ("stat-rows", GEOMETRY.stat_table()), ("name-rows", GEOMETRY.name_table())):
        r = region[name]
        assert read(rom, 4, r.start, r.end - r.start) == table, name
    assert read(rom, 4, 0xB41D, 1) == b"\x08" and read(rom, 4, 0xB54A, 16) == bytes.fromhex(
        "21 28 21 48 21 68 21 88 21 EA 22 0A 22 2A 22 4A") and read(rom, 4, 0xB5BE, 4) == bytes.fromhex("47 57 77 87")
    code = builder.draw_code()
    assert len(code) == 78 and read(rom, 4, builder.CODE, 0x80) == code + b"\xFF" * (0x80 - len(code))
    assert read(rom, 4, builder.PALETTE, 32) == assets.palette
    assert read(rom, 4, builder.SCREEN, 0x400) == assets.screen()
    assert read(rom, "chr", 0x5000, 0x1000) == assets.chr
    assert read(rom, 4, builder.PALETTE + 32, builder.SCREEN - builder.PALETTE - 32) == b"\xFF" * 0x60
    writer = range(locate(4, 0xB39D), locate(4, 0xB6F7))
    hooks = {i for name in ("score-draw-call", "header-address", "line-rows", "stat-rows", "name-rows")
             for i in range(locate(4, region[name].start), locate(4, region[name].end))}
    assert {i for i in writer if base[i] != rom[i]} <= hooks, "scene $0A/$0B code changed outside the hook and rows"
    for bank, label in ((14, "bank 14"), (15, "fixed bank")):
        origin = 0xC000 if bank == 15 else 0x8000
        assert read(rom, bank, origin, 0x4000) == read(base, bank, origin, 0x4000), label
    assert read(rom, "chr", 0x18000, 0x1000) == read(base, "chr", 0x18000, 0x1000), "CHR $18"
    assert find_all(base, bytes.fromhex("20 C4 C5 0C 0C 05")) == [(4, 0xB3CD)], "stock CHR $05 descriptors"
    assert not find_all(rom, bytes.fromhex("20 C4 C5 0C 0C 05")), "the stock CHR $05 screen load is still reachable"
    select = [h for p in ("A9 05 85 25", "A9 05 85 23", "A9 05 85 24", "A9 05 85 26")
              for h in find_all(rom, bytes.fromhex(p))]
    before = [h for p in ("A9 05 85 25", "A9 05 85 23", "A9 05 85 24", "A9 05 85 26")
              for h in find_all(base, bytes.fromhex(p))]
    assert sorted(set(select) - set(before)) == [(4, code_offset(bytes.fromhex("A9 05 85 25")) - locate(4, 0x8000)
                                                  + 0x8000)] and set(before) <= set(select), select
    assert not find_all(rom, bytes.fromhex("A9 0E 20 4E C1")), "bank 14 is selected"
    print(f"builder: {changed} changed bytes inside {len(builder.REGIONS)} whole reservations (hook $B3C0-$B3D3, "
          "header, line, statistic and name rows, $B800 code, $B880 palette, $B900 screen, CHR $05); every other "
          f"PRG bank, bank 14, the fixed bank, CHR $18 and the header identical; {guards} dependency, digest and "
          "reservation guards each reject a one-bit drift; bad manifests rejected; the stock CHR $05 load is gone "
          "and the new draw is the only new CHR $05 selection; no bank-14 selection")

# ---------------------------------------------------------------- timing


def test_timing(base, rom, quick):
    leads = (0, 14900) if quick else (0, 997, 14900, 29779)
    entry = SAMPLES["walk-off"]
    for label, data in (("stock", base), ("candidate", rom)):
        for lead in leads:
            got = M.interval(data, entry, lead=lead)
            assert (got["waits"], got["cycles"]) == (2, builder.STOCK_INTERVAL), (label, lead, got)
        quiet = M.interval(data, entry, quiet=True)
        assert quiet["cycles"] == quiet["independent"] == builder.STOCK_INTERVAL, (label, quiet)
    bare = patched(rom, [(locate(4, builder.CODE), padded(builder.draw_code(0), builder.REGIONS[5]))])
    copy = M.interval(bare, entry, quiet=True)
    assert copy["cycles"] == copy["independent"] == builder.COPY_INTERVAL, \
        f"the draw without its busy wait costs {copy['cycles']}; set COPY_INTERVAL to that"
    print(f"timing: stock and candidate both take 2 vblank waits and {builder.STOCK_INTERVAL} CPU cycles from the "
          f"second wait's return to the writer at $B3D4 at vblank phases {', '.join(map(str, leads))} (NMIs "
          "excluded); with NMIs masked an independent opcode-cost sum agrees; the copy alone costs "
          f"{builder.COPY_INTERVAL}, so DELAY {builder.DELAY} pays the difference")


def interval_check(data):
    got = M.interval(data, SAMPLES["walk-off"])
    assert (got["waits"], got["cycles"]) == (2, builder.STOCK_INTERVAL), f"waits/cycles {got['waits']}/{got['cycles']}"

# ---------------------------------------------------------------- boards


def shifted(stock_oam):
    """The stock OAM with every visible label sprite moved to the stage's name rows."""
    want = bytearray(stock_oam)
    for k, first in enumerate(M.LABEL_SLOTS):
        delta = GEOMETRY.name_table()[k] - STOCK_GEOMETRY.name_table()[k]
        for slot in range(first, first + M.LABEL_SPRITES):
            if stock_oam[4 * slot] < 0xEF:
                want[4 * slot] = (stock_oam[4 * slot] + delta) & 0xFF
    return bytes(want)


def board_check(m, stock, entry, assets):
    """The candidate's VRAM is the stock rules at the moved rows over the asset background; the stock VRAM is
    the same rules at the stock rows; the candidate's labels are stock's, moved to the new rows."""
    shown, want = m.nametable(), drawn(entry.board, GEOMETRY)
    bad = [cell for cell, t in want.items() if shown[32 * cell[1] + cell[0]] != t]
    assert not bad, f"writer cells {bad[:4]} differ from the stock rules"
    bad = [(i % 32, i // 32) for i in range(960) if (i % 32, i // 32) not in want and shown[i] != assets.nametable[i]]
    assert not bad, f"background cells {bad[:4]} differ from the asset"
    assert shown[960:] == assets.attributes, "attributes differ from the asset"
    reference = stock.nametable()
    bad = [cell for cell, t in drawn(entry.board, STOCK_GEOMETRY).items() if reference[32 * cell[1] + cell[0]] != t]
    assert not bad, f"stock writer cells {bad[:4]} differ from the stock rules"
    got, wanted = M.oam_buffer(m), shifted(M.oam_buffer(stock))
    if got != wanted:
        first = next(i for i in range(256) if got[i] != wanted[i])
        raise AssertionError(f"name sprites differ from stock's moved labels at OAM byte {first}")


def value_entries(count):
    """Boards that together put every byte in R, H and each statistic, 0-127 in the line score, every marker
    $80-$FF as a side's last line cell, and every team id on both sides."""
    out = []
    for i in range(count):
        plain = [(12 * i + j) % 128 for j in range(12)]
        line = [0] * 14
        line[0:12:2], line[1:12:2] = plain[:6], plain[6:]           # six cells a side, halves 0-11
        line[12], line[13] = 0x80 + i % 128, 0x80 + (i + 64) % 128  # each side's seventh cell ends it
        stats = tuple(((2 * i + 37 * k) % 256, (2 * i + 1 + 37 * k) % 256) for k in range(7))
        out.append(Entry(board(14, line, (2 * i % 256, (2 * i + 1) % 256), stats), teams=(i % 32, (7 * i + 5) % 32)))
    return out


def halves_entries():
    """Every page-table entry 1-41 (the game reaches 36), with two-digit values and an X mid-row on some."""
    out = []
    for halves in range(1, 42):
        line = [(halves * 3 + j * 11) % 128 for j in range(halves)]
        if halves % 5 == 0 and halves > 4:
            line[halves - 3] = 0x80 | (halves % 9)
        out.append(Entry(board(halves, line, (halves, 100 + halves), ((halves + k, 200 - k) for k in range(7))),
                         teams=(halves % 32, 31 - halves % 32)))
    return out


def random_entries(count):
    rng = random.Random(0x5C0E)
    out = []
    for _ in range(count):
        over = rng.choice((0, 0, 1, 2))
        halves = rng.randint(1, 35) if over != 2 else 36
        line = [rng.choice((0, 0, 0, 1, 2, 3, 4, 7, 9, 10, 11, 12, 19, 99)) for _ in range(halves)]
        if over == 1:
            if halves % 2 == 0:
                line.append(0x80)
                halves += 1
            elif rng.random() < 0.6:
                line[-1] |= 0x80
        value = lambda: rng.choice((0, 1, 2, 5, 9, 10, 11, 19, 42, 99, 100, 123, 255))   # noqa: E731
        out.append(Entry(board(halves, line, (value(), value()), [(value(), value()) for _ in range(7)]),
                         teams=(rng.randrange(32), rng.randrange(32)), over=over))
    return out


def test_boards(base, rom, assets, quick):
    sets = {"values": value_entries(16 if quick else 128), "halves": halves_entries(),
            "random": random_entries(40 if quick else 240)}
    teams = set()
    for name, entries in sets.items():
        for i, entry in enumerate(entries):
            try:
                board_check(M.draw(rom, entry), M.draw(base, entry), entry, assets)
            except AssertionError as exc:
                raise AssertionError(f"{name} board {i}: {exc}") from None
            teams |= {(side, team) for side, team in enumerate(entry.teams)}
    values = {v for e in sets["values"] for v in (*e.board.runs, *(x for p in e.board.stats for x in p))}
    line = {v for e in sets["values"] for v in e.board.line[:14]}
    if not quick:
        assert values == set(range(256)) and line == set(range(256)), "the value boards miss a byte"
        assert teams == {(s, t) for s in (0, 1) for t in range(32)}, "a team id is missing on one side"
    counts = ", ".join(f"{len(v)} {k}" for k, v in sets.items())
    print(f"boards: {sum(map(len, sets.values()))} drawn boards ({counts}) "
          f"cover {len(values)} R/H/statistic values, {len(line)} line-score bytes including X and walk-off marks, "
          f"halves 1-41 on all three header pages and {len(teams)} side/team pairs; on the candidate every writer "
          "cell is the stock rules at the moved rows and every other cell and attribute is the asset; on stock the "
          "same rules hold at the stock rows; name sprites are stock's, moved only by the row shift")


def sample_check(m, stock, entry, assets):
    board_check(m, stock, entry, assets)
    got = m.palette32()
    assert got[:16] == assets.palette[:16] and all(got[16 + i] == assets.palette[16 + i] for i in range(16) if i % 4), \
        f"palette {got.hex()}"
    assert (m.chr_bank(1), m.chr_bank(0), m.ctrl & 0x18) == (model.SCORE_CHR, 0x18, 0x10), (m.chr, hex(m.ctrl))
    assert m.chr_rom[model.SCORE_CHR * 0x1000:model.SCORE_CHR * 0x1000 + 0x1000] == assets.chr, "CHR $05"
    assert bytes(m.oam) == M.oam_buffer(m), "OAM was not uploaded"
    assert not m.vram_late, f"VRAM written with rendering on outside vblank: {m.vram_late[:2]}"


def test_samples(base, rom, assets):
    for name, entry in SAMPLES.items():
        try:
            sample_check(M.show(rom, entry), M.show(base, entry), entry, assets)
        except AssertionError as exc:
            raise AssertionError(f"{name}: {exc}") from None
    print(f"samples: {len(SAMPLES)} shown boards ({', '.join(SAMPLES)}) hold the rules' values and the asset "
          "background, attributes, palette and CHR $05 bytes, with BG CHR $05 and sprite CHR $18 mapped, the "
          "moved name sprites uploaded and no late VRAM writes")

# ---------------------------------------------------------------- RAM contract


class Recorder(M.Boot):
    """Records each RAM write: address, PC, PRG bank, SP, whether audio code made it, whether the draw was running."""

    def track(self):
        self.writes, self.in_draw = [], False
        return self

    def step(self):
        if not self.nmi_depth and self.prg == builder.BANK:
            if self.mpu.pc == builder.HOOK:
                self.in_draw = True
            elif self.mpu.pc == M.WRITER:
                self.in_draw = False
        super().step()

    def __setitem__(self, a, v):
        if a < 0x2000 and hasattr(self, "writes"):
            audio = bool(self.nmi_depth) or 0xCF74 <= self.pc <= 0xCFA9 or (self.pc < 0xC000 and self.prg == 0)
            self.writes.append((a & 0x7FF, self.pc, self.prg, self.mpu.sp, audio, self.in_draw))
        super().__setitem__(a, v)


def recorded(data, entry):
    m = M.enter(data, entry)
    m.__class__ = Recorder
    m.track()
    m.run(lambda mm: M.outside_nmi(mm, M.DRAWN), limit=5_000_000)
    return m


def test_ram(base, rom):
    extra, differ, draw_writes = set(), set(), 0
    for name, entry in SAMPLES.items():
        s, c = recorded(base, entry), recorded(rom, entry)
        game = {a for a, _, _, _, audio, _ in s.writes if not audio}
        for a, pc, prg, sp, audio, in_draw in c.writes:
            if in_draw and not audio:
                draw_writes += 1
                assert a in DRAW_CONTRACT or a == 0x100 + sp, f"{name}: the draw wrote ${a:04X} at {prg}:${pc:04X}"
        extra |= {a for a, _, _, _, audio, _ in c.writes if not audio} - game - SCRATCH
        sound = {a for a, *_, audio, _ in s.writes + c.writes if audio}
        differ |= {a for a in range(0x800) if s.ram[a] != c.ram[a]} - SCRATCH - sound - set(range(0x0200, 0x0300))
        assert c.wram == s.wram, f"{name}: WRAM differs"
    assert not extra, f"the candidate writes game RAM stock does not: {sorted(f'${a:04X}' for a in extra)}"
    assert differ == {0x06B4}, f"RAM differs from stock at {sorted(f'${a:04X}' for a in differ)}"
    print(f"RAM: in {len(SAMPLES)} samples the draw's {draw_writes} writes stay inside $00/$01, $25, $2C, $32, $AD, "
          "$0195-$01B5 and stack pushes; through $B3F2 the candidate's game-code writes are a subset of stock's plus "
          "loader scratch; RAM outside scratch, the audio driver's writes and the OAM page equals stock except "
          "$06B4, the last name's Y; WRAM equals stock")

# ---------------------------------------------------------------- flows


def flows(quick):
    final_wait = 600
    live_wait = 360
    since = ((0x8D, R.A), (0x8F, R.A))
    cases = [
        ("live, the jingle ends", SAMPLES["mid 4th"], (None, None), live_wait),
        ("live, A taps, both sides CPU", SAMPLES["two-digit"], (TAPS, None), 80),
        ("live, A held from the board on controller 1, both CPU", SAMPLES["two-digit"], (HELD_A, None), 60),
        ("live, A held on controller 1, batting side human", replace(SAMPLES["two-digit"], cpu=(0x00, 0x80)),
         (HELD_A, None), 60),
        ("live, A held on controller 2, fielding side human", replace(SAMPLES["two-digit"], cpu=(0x80, 0x00)),
         (None, HELD_A), 60),
        ("live, A held since the field plus B SELECT START: the jingle decides",
         replace(SAMPLES["mid 4th"], pokes=since), (HELD_OTHERS, None), live_wait),
        ("Championship final through the results gate", replace(SAMPLES["final, X"], championship=1), (None, None), 80),
        ("quiet final, A taps", replace(SAMPLES["walk-off"], quiet=1), (TAPS, None), 80),
        ("called tie, Championship", replace(SAMPLES["called tie"], championship=1), (None, None), 80),
        ("attract demo past its inning limit", replace(SAMPLES["15th"], attract=1), (None, None), live_wait),
        ("half-zero entry bypasses the board", replace(SAMPLES["mid 4th"], pokes=((M.HALVES, 0),)), (None, None), 30),
    ]
    if not quick:
        cases += [("Exhibition final, A taps after the jingle", SAMPLES["final, X"], (TAPS, None), final_wait),
                  ("called tie, Exhibition, A taps after the jingle", SAMPLES["called tie"], (TAPS, None), final_wait)]
    return cases


def flow_check(base, data, entry, pads, frames, song=0x02, lead=0):
    stock = M.timeline(base, entry, frames, pads, song, lead)
    got = M.timeline(data, entry, frames, pads, song, lead)
    for key in ("scenes", "requests", "frames", "apu"):
        if got[key] != stock[key]:
            first = next((i for i, (x, y) in enumerate(zip(stock[key], got[key])) if x != y),
                         min(len(stock[key]), len(got[key])))
            raise AssertionError(f"{key} differ from stock at entry {first}: "
                                 f"{stock[key][first:first + 2]} vs {got[key][first:first + 2]}")
    return got


def test_flows(base, rom, quick):
    for name, entry, pads, frames in flows(quick):
        try:
            got = flow_check(base, rom, entry, pads, frames)
        except AssertionError as exc:
            raise AssertionError(f"{name}: {exc}") from None
        scenes = " -> ".join(f"${s:02X}@{f}" for f, s in got["scenes"]) or "none"
        bracket = " (bank 11 bracket)" if any(f[1] == 11 for f in got["frames"]) else ""
        print(f"  flow {name}: scene writes {scenes}{bracket}; {frames} frames and {len(got['apu'])} APU writes equal")
    variants = 0
    if not quick:
        for name, entry, pads, frames in flows(True)[1:3] + flows(True)[6:7]:
            for song, lead in ((0x02, 997), (0x02, 14900), (0x02, 29779), (0x00, 0), (0x06, 0)):
                try:
                    flow_check(base, rom, entry, pads, frames, song, lead)
                except AssertionError as exc:
                    raise AssertionError(f"{name}, song ${song:02X}, phase {lead}: {exc}") from None
                variants += 1
    print(f"flows: {len(flows(quick))} exits match stock frame for frame: scene writes, sound requests, per-frame "
          "scene, PRG bank, song and rendering, and every APU write" + (f"; {variants} vblank-phase and song "
                                                                      "variants match too" if variants else ""))

# ---------------------------------------------------------------- NMI injection


def new_instructions(rom):
    memory = bytearray(0x10000)
    memory[0x8000:0xC000] = read(rom, 4, 0x8000, 0x4000)
    disassembler = Disassembler(MPU(memory=memory))
    pcs, pc = [builder.HOOK, builder.HOOK + 3], builder.CODE
    while pc < builder.CODE + len(builder.draw_code()):
        pcs.append(pc)
        pc += disassembler.instruction_at(pc)[0]
    return pcs


def nmi_state(m):
    return m.nametable(), m.palette32(), tuple(m.chr), bytes(m.oam), m.ram[M.SCENE]


def test_nmi(rom):
    entry = SAMPLES["walk-off"]
    reference = nmi_state(M.show(rom, entry, settle=3))
    pcs = new_instructions(rom)
    for pc in pcs:
        m, fired = M.with_nmi(rom, entry, pc)
        assert fired, f"${pc:04X} never ran"
        assert nmi_state(m) == reference, f"an NMI before ${pc:04X} changed the board"
        assert (m.ram[0x2C], m.ram[0x2D], m.ram[0x27]) == (0, 0, 4), f"${pc:04X}: guards or bank left wrong"
    print(f"NMI injection: one NMI before each of the {len(pcs)} hook and draw instructions leaves the same "
          "nametable, palette, CHR, OAM and scene, with $2C and $2D released and bank 4 mapped (CPU model)")

# ---------------------------------------------------------------- negative controls


def test_negative_controls(base, rom, assets):
    code = locate(4, builder.CODE)
    region = builder.REGIONS[5]
    tables = [(locate(4, r.start), read(base, 4, r.start, r.end - r.start)) for r in builder.REGIONS[1:5]]
    entry = SAMPLES["two-digit"]

    def flow(data):
        flow_check(base, data, entry, (TAPS, None), 80)

    def boards(data):
        for e in (entry, SAMPLES["15th"]):
            board_check(M.draw(data, e), M.draw(base, e), e, assets)

    def samples(data):
        sample_check(M.show(data, entry), M.show(base, entry), entry, assets)
    second_wait = builder.draw_code().index(bytes.fromhex("20 60 C2"), 18)
    controls = [
        ("no busy wait", patched(rom, [(code, padded(builder.draw_code(0), region))]), flow),
        ("no busy wait: cycle budget", patched(rom, [(code, padded(builder.draw_code(0), region))]), interval_check),
        ("one vblank wait", patched(rom, [(code + second_wait, b"\xEA" * 3)]), interval_check),
        ("stock rows", patched(rom, tables), boards),
        ("stock name rows", patched(rom, tables[3:]), boards),
        ("no CHR $05 select", patched(rom, [(code_offset(bytes.fromhex("A9 05 85 25")), b"\xEA" * 4)]), samples),
        ("no palette request", patched(rom, [(code_offset(bytes.fromhex("EE B5 01")), b"\xEA" * 3)]), samples),
        ("stock CHR $05", patched(rom, [(locate("chr", 0x5000), read(base, "chr", 0x5000, 0x1000))]), samples),
    ]
    for label, variant, check in controls:
        print(f"  negative control {label}: rejected ({expect_failure(check, variant)})")
    print(f"negative controls: all {len(controls)} detected by the same checks the candidate passes")

# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned modeart32 input")
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--assets", type=Path, default=model.ASSETS, help="scoreassets/1 file (default %(default)s)")
    ap.add_argument("--art", type=Path, default=builder.ART, help="art directory (default %(default)s)")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: also re-render and compare the art")
    ap.add_argument("--quick", action="store_true", help="fewer boards and flows, no phase variants or NMI sweep")
    args = ap.parse_args()
    started = time.monotonic()
    pxl = args.pxl.resolve() if args.pxl else None
    base = args.rom.read_bytes()
    assets = builder.load_assets(args.assets)
    rom = builder.build_rom(base, assets)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    assert sha256(args.assets.read_bytes()) == ASSETS_SHA256, "the asset JSON differs from the pinned final art"
    assert sha256(rom) == OUTPUT_SHA256, "scoreart32 output differs from the pinned final-art build"
    print(f"input {sha256(base)}")
    print(f"assets {ASSETS_SHA256}")
    print(f"candidate {OUTPUT_SHA256}")
    test_assets(base, assets, args.assets)
    test_converter(base, args.art, assets, args.assets, pxl)
    test_converter_cli(base, assets, args.art, args.assets)
    test_builder_cli(base, rom, assets, args.art, args.assets)
    test_regeneration(base, assets, args.art, args.assets, pxl)
    test_protected_names(args.rom)
    with patch.object(builder, "ASSETS", args.assets):
        test_builder(base, rom, assets)
    test_timing(base, rom, args.quick)
    test_samples(base, rom, assets)
    test_boards(base, rom, assets, args.quick)
    test_ram(base, rom)
    test_flows(base, rom, args.quick)
    if not args.quick:
        test_nmi(rom)
    test_negative_controls(base, rom, assets)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"scoreart32 SHA256 {OUTPUT_SHA256}")
    print(f"PASS ({time.monotonic() - started:.1f}s)" + (" quick" if args.quick else ""))


if __name__ == "__main__":
    main()
