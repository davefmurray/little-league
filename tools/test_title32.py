#!/usr/bin/env python3
"""Check the title32 stage: art conversion, builder guards and the title's runtime contract.

    .venv/bin/python tools/test_title32.py build/pick32.nes --candidate build/title32.nes
    .venv/bin/python tools/test_title32.py build/pick32.nes --pxl build/vendor/claude-pxl

Runtime checks boot the built ROM and its pick32 input from RESET on
tools/frontend32_test_machine.Boot: the title as drawn in VRAM, song $04,
START from either controller, the idle attract cutscene, the phase-3 title
redraw and the demo game, each compared with the stock title's own timeline.
The model's sprite-0 and vblank-poll approximations shape those frame
numbers; they are not hardware timing. Pixel and listening acceptance belong
to the root emulator gates.
"""
import argparse
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

import build_title32 as builder
from build_draw32 import locate
import menu32_convert as menu
import password32v2 as P
import title32_convert as convert
from frontend32_test_machine import Boot, check_builder, check_output_guards, rejects, title_tail, to_mode_menu

OUTPUT_SHA256 = "8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c"
TOOLS = Path(__file__).resolve().parent
PHASE = 0x00BA                       # stock attract phase counter: k + 1 once phase k is dispatched
ATTRACT_FRAMES = 1900


def expected_screen(assets):
    return bytes.fromhex(assets["nametable"]) + bytes.fromhex(assets["attributes"])


def test_converter(base, pxl=None):
    first, second = convert.convert(base), convert.convert(base)
    text = convert.dumps(first)
    assert text == convert.dumps(second), "converter output is not deterministic"
    assert text == convert.ASSETS.read_text(), "data/title32/titleassets.json is stale"
    assert first["tiles_used"] <= 256 and first["png_sha256"] == hashlib.sha256(convert.SCENE.read_bytes()).hexdigest()
    reproduced = convert.check_pxl(pxl) if pxl else 0

    def edit(path, spots):
        image = Image.open(path).convert("RGBA")
        for xy, rgba in spots:
            image.putpixel(xy, rgba)
        image.save(path)
    gold, white, green, red = (menu.NES_RGB[c] + (255,) for c in (0x28, 0x30, 0x1A, 0x16))
    layout = json.loads(convert.LAYOUT.read_text())
    text_row = layout["text"][0]
    fonts = menu.font_patterns(base)
    unprintable = next(chr(i) for i in range(0x21, 0x7F) if not any(fonts[i]))
    cases = [
        ("unknown color", lambda d, l: edit(d / "title.png", [((100, 120), (1, 2, 3, 255))])),
        ("partial alpha", lambda d, l: edit(d / "title.png", [((100, 120), white[:3] + (128,))])),
        ("wrong size", lambda d, l: Image.new("RGBA", (256, 224), menu.NES_RGB[0x0C] + (255,)).save(d / "title.png")),
        ("text cell painted", lambda d, l: edit(d / "title.png", [((8 * text_row["col"] + 3, 8 * text_row["row"] + 3),
                                                                   white)])),
        ("attribute conflict", lambda d, l: edit(d / "title.png", [((x, 8), c) for x, c in
                                                                   zip(range(8, 12), (gold, white, green, red))])),
        ("no stock glyph", lambda d, l: l["text"].append({"row": 0, "col": 0, "text": unprintable, "palette": 0})),
        ("unsupported color", lambda d, l: l["palettes"][0].__setitem__(0, "0D")),
    ]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        scene, layout_path = directory / "title.png", directory / "layout.json"
        for label, mutate in cases:
            shutil.copyfile(convert.SCENE, scene)
            copy = json.loads(json.dumps(layout))
            mutate(directory, copy)
            layout_path.write_text(json.dumps(copy))
            try:
                convert.convert(base, layout_path, scene)
            except menu.AssetError:
                continue
            raise AssertionError(f"converter accepted {label}")
        shutil.copyfile(convert.SCENE, scene)
        layout_path.write_text(json.dumps(layout))
        real_init = menu.TileBank.__init__

        def tiny(bank, *args):
            real_init(bank, *args)
            bank.order = bank.order[:40]
        with patch.object(menu.TileBank, "__init__", tiny):
            rejects(convert.convert, base, layout_path, scene)
    print(f"converter: deterministic; committed JSON current ({first['tiles_used']} tiles, "
          f"{len(first['font_glyphs'])} stock glyphs); {len(cases) + 1} bad inputs rejected"
          + (f"; pinned pxl reproduces all {reproduced} committed PNGs" if pxl else "; pxl re-render not run (no --pxl)"))


def test_converter_cli(rom_path):
    script = [sys.executable, str(TOOLS / "title32_convert.py"), "--rom"]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        rom = directory / "pick32.nes"
        rom.write_bytes(Path(rom_path).read_bytes())
        output, preview = directory / "assets.json", directory / "title.png"
        result = subprocess.run(script + [str(rom), "--out", str(output), "--preview", str(preview)], cwd=directory,
                                capture_output=True, text=True)
        assert result.returncode == 0 and output.read_text() == convert.ASSETS.read_text(), result.stderr
        assets = json.loads(output.read_text())
        assert Image.open(preview).tobytes() == convert.preview(assets).tobytes()
        result = subprocess.run(script + [str(rom), "--out", str(output), "--check"], cwd=directory,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        output.write_text(output.read_text().replace('"tiles_used": ', '"tiles_used": 1'))
        result = subprocess.run(script + [str(rom), "--out", str(output), "--check"], cwd=directory,
                                capture_output=True, text=True)
        assert result.returncode == 2 and "stale" in result.stderr, result.stderr
        png, sprite = convert.SCENE, next(convert.PNGS.glob("sprites/*.png"))
        targets = [rom, TOOLS / "verify.sh", png, sprite, convert.SOURCE, convert.LAYOUT, convert.LOCK, builder.ROOT / "data/teams32.json"]
        for i, target in enumerate((rom, png)):
            symbolic, hard = directory / f"alias{i}-symlink", directory / f"alias{i}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets += [symbolic, hard]
        for target in targets:
            before = target.read_bytes()
            for option in (["--out", str(target)], ["--out", str(output), "--preview", str(target)]):
                result = subprocess.run(script + [str(rom)] + option, cwd=directory, capture_output=True, text=True)
                assert result.returncode == 2 and "output aliases protected" in result.stderr, (target, result.stderr)
                assert target.read_bytes() == before, f"{target} changed"
        result = subprocess.run(script + [str(rom), "--preview", str(convert.ASSETS)], cwd=directory,
                                capture_output=True, text=True)
        assert result.returncode == 2 and "output aliases protected" in result.stderr, result.stderr
    print(f"converter CLI: --out and --preview from another directory; --check passes current and fails stale JSON; "
          f"{len(targets)} protected targets refused as --out or --preview (ROM, nested PNGs, source, layout, lock, "
          "data, links), and the assets as --preview")


def test_builder(base, rom, assets):
    changed, guards = check_builder(builder, base, rom, owned_banks={0}, owned_chr={builder.TITLE_CHR})
    stock = base[locate("chr", 0x17000):locate("chr", 0x18000)]
    assert hashlib.sha256(stock).hexdigest() == builder.STOCK_CHR17_SHA256
    assert rom[locate("chr", 0x17000):locate("chr", 0x18000)] == bytes.fromhex(assets["chr"])
    assert builder.labels()["title_draw"] == builder.CODE

    def mutated(change):
        bad = json.loads(json.dumps(assets))
        change(bad)
        return bad
    glyph = assets["font_glyphs"][-1]
    chr_flip = bytearray.fromhex(assets["chr"])
    chr_flip[16 * glyph] ^= 1
    empty = next(i for i in range(256) if i not in assets["font_glyphs"] and not any(chr_flip[16 * i:16 * i + 16]))
    for bad in (mutated(lambda a: a.update(format="titleassets/2")), mutated(lambda a: a.update(chr_bank=0x19)),
                mutated(lambda a: a.update(nametable=a["nametable"][:-2])),
                mutated(lambda a: a.update(palette="40" + a["palette"][2:])),
                mutated(lambda a: a.update(palette=a["palette"][:8] + "0F" + a["palette"][10:])),
                mutated(lambda a: a.update(chr=chr_flip.hex())),
                mutated(lambda a: a.update(tiles_used=a["tiles_used"] + 1)),
                mutated(lambda a: a.update(font_glyphs=a["font_glyphs"][::-1])),
                mutated(lambda a: a.update(nametable=f"{empty:02x}" + a["nametable"][2:]))):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assets.json"
            path.write_text(json.dumps(bad))
            rejects(lambda: builder.check_assets(base, builder.load_assets(path)))
    print(f"builder: {changed} changed bytes inside {len(builder.REGIONS)} whole reservations; banks 1-15, header "
          f"and every CHR bank but $17 identical; {guards} dependency, digest, hook, reservation and pinned stock "
          "CHR $17 guards each reject a one-bit drift; bad manifests and 9 malformed or foreign assets rejected")


def attract(rom):
    """Idle from RESET to the demo: the frame each title-loop attract phase starts, the demo's first frame
    (phase 4 switches to scene $08 in the frame it starts) and each phase's screen 40 frames in."""
    m = Boot(rom, watch=(0x047B, PHASE))
    phases, shots, due, demo = {}, {}, {}, None
    while demo is None or m.frame < demo + 5:
        m.frames(1)
        phase = m.ram[PHASE] - 1
        if m.ram[0x047B] == 1 and 0 <= phase and phase not in phases:
            phases[phase] = m.frame
            due[m.frame + 40] = phase
            m.vram_late.clear()
        if m.frame in due:
            shots[due[m.frame]] = (m.nametable(), m.palette32(), tuple(m.chr), m.chr_bank(1), list(m.vram_late))
        if demo is None and m.ram[0x047B] == 8:
            demo = m.frame
        assert m.frame < 4000, "the attract sequence did not reach the demo"
    return phases, demo, shots


def test_runtime(base, rom, assets):
    screen, palette = expected_screen(assets), bytes.fromhex(assets["palette"])
    m = Boot(rom)
    m.frames(120)
    assert m.nametable() == screen, "the title in VRAM differs from the converted art"
    assert m.chr_bank(1) == builder.TITLE_CHR and m.ctrl & 0x10, "the title background is not CHR $17"
    assert m.chr_rom[0x17000:0x18000] == bytes.fromhex(assets["chr"])
    assert m.palette32() == palette, "the title palette was not uploaded"
    assert m.ram[0x0401] == 0x04, "title song $04 is not playing"
    assert not m.vram_late, f"title VRAM written outside vblank: {m.vram_late[:3]}"
    stock = Boot(base)
    stock.frames(120)
    assert stock.nametable() != screen and stock.chr_bank(1) == builder.TITLE_CHR, "control: stock title unchanged"
    starts = []
    for port in (0, 1):
        d = to_mode_menu(rom, port=port)
        assert d.m.ram[0x0401] == 0x06, "menu song $06 is not playing after START"
        starts.append(d.m.frame)
    (phases, demo, shots), (old_phases, old_demo, old_shots) = attract(rom), attract(base)
    assert sorted(phases) == sorted(old_phases) == [0, 1, 2, 3], (phases, old_phases)
    drift = max([abs(phases[k] - old_phases[k]) for k in phases] + [abs(demo - old_demo)])
    assert drift <= 3, (phases, old_phases, demo, old_demo)
    for k in (0, 1, 2):
        assert shots[k][:4] == old_shots[k][:4], f"attract phase {k} differs from the stock cutscene"
        assert shots[k][3] != builder.TITLE_CHR
    nametable, colors, _, bank, late = shots[3]
    assert nametable == screen and colors == palette and bank == builder.TITLE_CHR, "phase 3 did not redraw the title"
    assert not late, f"the phase-3 redraw wrote VRAM outside vblank: {late[:3]}"
    print(f"runtime: frame 120 shows the converted title from CHR $17 with its palette and song $04 and no late "
          f"VRAM writes (control: the stock title differs); START on controller 1 or 2 reaches the mode menu "
          f"with song $06 (frames {starts[0]}, {starts[1]}); attract phases 0-3 start at frames "
          f"{', '.join(str(phases[k]) for k in sorted(phases))} and demo scene $08 at {demo}, at most {drift} frames from "
          f"the stock title ({', '.join(str(old_phases[k]) for k in sorted(old_phases))}; {old_demo}); "
          "cutscene phases 0-2 show the stock screens and CHR; phase 3 redraws the new title")


def test_title_tail(rom):
    codes = []
    for draw_seed in (0, 0x1234, 0x3FFF):
        for port in (0, 1):
            series = P.Series(team=31, played=24, results=0x555555, cpu_mask=0x5AA55AA5, draw_seed=draw_seed)
            codes.append(title_tail(rom, series, port))
    print(f"title tail: v1 and v2 series survive post-game, the new title draw, START on either controller, mode "
          f"menu and CONTINUE, with displayed codes {', '.join(sorted(set(codes)))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned pick32 input")
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: also re-render and compare the art")
    args = ap.parse_args()
    started = time.monotonic()
    base = args.rom.read_bytes()
    assets = builder.load_assets()
    rom = builder.build_rom(base, assets)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256, "title32 output differs from the pinned art build"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    test_converter(base, args.pxl)
    test_converter_cli(args.rom)
    test_builder(base, rom, assets)
    sources = [TOOLS / "build_title32.py", builder.ASSETS, convert.SCENE, next(convert.PNGS.glob("sprites/*.png")),
               convert.SOURCE, convert.LAYOUT, TOOLS / "title32_convert.py", builder.ROOT / "build/draw32.nes"]
    sources += [TOOLS / "verify.sh", builder.ROOT / "data/title32/titleassets.json",
                builder.ROOT / "art/title32/title32.px.js", builder.ROOT / "art/title32/layout.json",
                builder.ROOT / "art/title32/PXL.json", builder.ROOT / "art/title32/out/scenes/title.png"]
    count = check_output_guards(TOOLS / "build_title32.py", args.rom, rom, builder.diff_manifest(base, rom), sources)
    print(f"output guards: deterministic CLI build and manifest from another directory; {count} protected targets "
          "refused (inputs, renamed copy, sources, assets, nested PNGs, symbolic and hard links); a bad input keeps "
          "the output")
    test_title_tail(rom)
    test_runtime(base, rom, assets)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"title32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
