#!/usr/bin/env python3
"""Regenerate or check the stockart32 art: stock characters cut from the ROM, staged beside copies of
the pxl sources, rendered with the pinned pxl and converted by the unchanged scoreart32 and modeart32
converters.

    .venv/bin/python -B tools/stockart32_convert.py --rom build/scoreart32.nes --font-rom build/modeart32.nes \\
        --pxl build/vendor/claude-pxl [--out DIR]
    .venv/bin/python -B tools/stockart32_convert.py --rom ... --font-rom ... --pxl ... --check
    .venv/bin/python -B tools/stockart32_convert.py --rom ... --font-rom ... --pxl ... --record

--rom is the accepted scoreart32 ROM: the source of every stock character byte and the stage input.
--font-rom is the pinned modeart32 ROM, whose CHR $00 font both converters letter text in and whose
CHR $1B ball the mode preview draws. --pxl is the checkout of the commit art/stockart32/PXL.json pins.

Everything is generated in scratch storage first: the parts art/stockart32/characters.json describes,
the pinned pxl render of art/stockart32/score and art/stockart32/mode staged with those parts (twice,
byte for byte), the scoreassets/1 and modeassets/1 assets, the converters' previews, provenance.json
and, in memory only, the ROM tools/build_stockart32.py builds from them. Every placed part pixel must
show in that ROM's own screen bytes, and every output and the ROM must match its digest in
data/stockart32/digests.json. Only then, after every destination passes the output guards, is each
output installed under --out (default build/stockart32) through a sibling temporary file. --check
stops before installing and writes nothing. --record installs outputs whose digests changed and then
rewrites data/stockart32/digests.json, the only tracked file this tool writes.

Under --out:
  parts/<id>.png             each part in exact NES colors, alpha 0 where clear
  score/out/, mode/out/      the pinned pxl renders the converters read
  scoreassets.json, modeassets.json   the converters' output, which tools/build_stockart32.py reads
  score-preview.png, mode-preview.png the converters' previews, decoded from asset bytes, not ROM frames
  provenance.json            per part cell: source tile, CHR offset and digest, the map byte and the
                             selector byte and bit shift, palette source, flips and priority; per
                             placement: each screen tile it reaches, the part rectangles drawn there and
                             the ROM's tile id, pattern digest and palette
"""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

import build_stockart32 as stage
from build_draw32 import read, refuse_aliases, sha256
from build_scoreart32 import refuse_inside, write_atomic
from build_title32 import protect_output as protect_earlier_output
import menu32_convert as menu
from menu32_convert import AssetError
import modeart32_convert as mode_convert
import scoreart32_convert as score_convert
import stockart32_parts as parts
import stockart32_source as source

ROOT = stage.ROOT
ART = ROOT / "art/stockart32"
SOURCES = ("PXL.json", "characters.json", "mode/layout.json", "mode/mode32.px.js", "score/layout.json",
           "score/score32.px.js")
SCENES = {"score": "score32.px.js", "mode": "mode32.px.js"}
# screen -> (PRG bank, nametable and attributes, palette, CHR offset) of its art in the built ROM
SCREEN_BYTES = {"score": (stage.SCORE_BANK, 0xB900, 0xB880, 0x5000), "mode": (stage.MODE_BANK, 0x9000, 0x9400, 0x6000)}
FIXED_OUTPUTS = (stage.MODE_JSON, stage.SCORE_JSON, "score-preview.png", "mode-preview.png", "provenance.json")


def png_bytes(image):
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return encoded.getvalue()


def read_sources(art):
    return {name: (Path(art) / name).read_bytes() for name in SOURCES}


def check_roms(base, font):
    if sha256(base) != stage.BASE_SHA256:
        raise AssetError("--rom must be the pinned scoreart32 input")
    if sha256(font) != score_convert.BASE_SHA256:
        raise AssetError("--font-rom must be the pinned modeart32 input, the font the converters letter text in")
    source.check_pins(base)


def screen_palettes(scratch):
    """screen -> (backdrop, four background palettes), from the staged layouts through their own readers."""
    score = score_convert.read_layout(scratch / "score/layout.json")
    mode = mode_convert.read_layout(scratch / "mode/layout.json")
    return {"score": (score.backdrop, score.palettes),
            "mode": (mode.backdrop, tuple(tuple(menu.nes_color(c) for c in p) for p in mode.colors["palettes"]))}


def stage_screen(scratch, sources, screen, manifest, pngs):
    """A convertible art directory: copies of the screen's sources and pin, and the parts it places."""
    directory = scratch / screen
    (directory / "parts").mkdir(parents=True)
    for name in ("layout.json", SCENES[screen]):
        (directory / name).write_bytes(sources[f"{screen}/{name}"])
    (directory / "PXL.json").write_bytes(sources["PXL.json"])
    for part in sorted({p.part for p in manifest.placements if p.screen == screen}):
        (directory / "parts" / f"{part}.png").write_bytes(pngs[part])
    return directory


def check_renderer(pxl, lock):
    if menu.node_version() < tuple(lock["node_min"]):
        raise AssetError(f"pxl needs Node >= {'.'.join(map(str, lock['node_min']))}")
    head = subprocess.run(["git", "-C", str(pxl), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != lock["commit"]:
        raise AssetError(f"pxl checkout is at {head}, not the pinned {lock['commit']}")


def render(pxl, directory, scene):
    """Render `scene` with pinned pxl twice, each time into a fresh directory; {relative path: bytes}."""
    renders = []
    for k in range(2):
        out = directory.parent / f"render-{directory.name}-{k}"
        result = subprocess.run(["node", str(Path(pxl).resolve() / "bin/pxl.js"), "build", str(directory / scene),
                                 "--out", str(out), "--no-preview"], cwd=directory, capture_output=True, text=True)
        if result.returncode:
            raise AssetError(f"pxl could not build {directory.name}/{scene}: {result.stderr.strip()[-300:]}")
        files = sorted(p for p in out.rglob("*") if p.is_file())
        if not files or any(p.suffix != ".png" for p in files):
            raise AssetError(f"pxl wrote {[str(p.relative_to(out)) for p in files]} for {scene}; expected PNGs only")
        renders.append({p.relative_to(out).as_posix(): p.read_bytes() for p in files})
    if renders[0] != renders[1]:
        raise AssetError(f"two pinned pxl renders of {scene} differ")
    for relative, data in renders[0].items():
        target = directory / "out" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return renders[0]



def rom_screen(rom, screen):
    bank, screen_at, palette_at, chr_at = SCREEN_BYTES[screen]
    data, chr_data = read(rom, bank, screen_at, 0x400), read(rom, "chr", chr_at, 0x1000)
    image = menu.render(chr_data, data[:960], data[960:], read(rom, bank, palette_at, 32))
    return image.load(), data, chr_data


def intersect(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x, y, right - x, bottom - y) if right > x and bottom > y else None


def visible_rect(placement, part):
    """The screen pixels a placement still shows, and the screen-minus-part offset."""
    ax, ay, aw, ah = placement.area or (0, 0, part.width, part.height)
    x0, y0 = placement.at
    shown = intersect(placement.visible or (x0, y0, aw, ah), intersect((x0, y0, aw, ah), (0, 0, 256, 240)))
    return shown, (x0 - ax, y0 - ay)


def place(placement, part, view):
    """Check every visible part pixel against the ROM's screen; map each screen tile it reaches."""
    pixels, data, chr_data = view
    shown, (dx, dy) = visible_rect(placement, part)
    where = f"placement of {placement.part} at {list(placement.at)} on {placement.screen}"
    if shown is None:
        raise AssetError(f"{where} shows nothing")
    painted = 0
    wrong = []
    for sy in range(shown[1], shown[1] + shown[3]):
        for sx in range(shown[0], shown[0] + shown[2]):
            color = part.pixels[sy - dy][sx - dx]
            if color is not None:
                painted += 1
                if pixels[sx, sy] != menu.NES_RGB[color]:
                    wrong.append((sx, sy))
    if wrong:
        raise AssetError(f"{where}: {len(wrong)} of {painted} visible part pixels differ in the ROM's screen bytes, "
                         f"first at {wrong[0]}")
    tiles = {}
    for (col, row) in sorted(part.cells, key=lambda c: (c[1], c[0])):
        cell = intersect((8 * col + dx, 8 * row + dy, 8, 8), shown)
        if cell is None:
            continue
        for ty in range(cell[1] // 8, (cell[1] + cell[3] - 1) // 8 + 1):
            for tx in range(cell[0] // 8, (cell[0] + cell[2] - 1) // 8 + 1):
                x, y, w, h = intersect(cell, (8 * tx, 8 * ty, 8, 8))
                count = sum(part.pixels[py - dy][px - dx] is not None for py in range(y, y + h) for px in range(x, x + w))
                if count:
                    tiles.setdefault((tx, ty), []).append({"cell": [col, row], "part_rect": [x - dx, y - dy, w, h],
                                                           "tile_rect": [x - 8 * tx, y - 8 * ty, w, h],
                                                           "pixels": count})
    records = []
    for (tx, ty), drawn in sorted(tiles.items(), key=lambda item: (item[0][1], item[0][0])):
        tile = data[32 * ty + tx]
        offset, shift = menu.attr_slot(tx, ty)
        records.append({"tile": [tx, ty], "chr_tile": tile, "pattern_sha256": sha256(chr_data[16 * tile:16 * tile + 16]),
                        "palette": (data[960 + offset] >> shift) & 3, "from": drawn})
    return {"part": placement.part, "screen": placement.screen, "at": list(placement.at),
            "area": list(placement.area) if placement.area else None, "shown": list(shown), "pixels": painted,
            "tiles": records}


def provenance(base, manifest, cut, rom):
    views = {screen: rom_screen(rom, screen) for screen in SCREEN_BYTES}
    return {
        "format": "stockart32-provenance/1",
        "base_sha256": sha256(base),
        "manifest_sha256": manifest.sha256,
        "pins": [{"label": label, "bank": bank, "address": f"${address:04X}", "size": size, "sha256": digest}
                 for label, bank, address, size, digest in source.PINS],
        "parts": [{"id": part.id, "size": [part.width, part.height], "source": part.source,
                   "mask_sha256": parts.mask_sha256(part.pixels),
                   "cells": [{"cell": [col, row], **record,
                              "painted": sum(part.pixels[8 * row + j][8 * col + i] is not None
                                             for j in range(8) for i in range(8))}
                             for (col, row), record in sorted(part.cells.items(), key=lambda c: (c[0][1], c[0][0]))]}
                  for part in cut.values()],
        "placements": [place(p, cut[p.part], views[p.screen]) for p in manifest.placements],
    }



def regenerate(base, font, pxl, sources):
    """Every output under --out as {relative path: bytes}, the two assets and the ROM, all built in scratch."""
    check_roms(base, font)
    manifest = parts.parse_manifest(json.loads(sources["characters.json"]), sha256(sources["characters.json"]))
    cut = parts.cut_parts(base, manifest)
    pngs = {pid: parts.png(part) for pid, part in cut.items()}
    renders = {}
    with tempfile.TemporaryDirectory(prefix="stockart32-") as temporary:
        scratch = Path(temporary)
        staged = {screen: stage_screen(scratch, sources, screen, manifest, pngs) for screen in SCENES}
        parts.check_targets(manifest, screen_palettes(scratch))
        check_renderer(pxl, score_convert.read_lock(staged["score"]))
        for screen, directory in staged.items():
            renders[screen] = render(pxl, directory, SCENES[screen])
        score = score_convert.convert(font, staged["score"])
        mode = mode_convert.convert(font, staged["mode"] / "layout.json", staged["mode"] / "out/scenes/mode.png")
    rom = stage.build_rom(base, mode, score)
    outputs = {f"parts/{pid}.png": data for pid, data in pngs.items()}
    outputs |= {f"{screen}/out/{relative}": data for screen, files in renders.items() for relative, data in files.items()}
    outputs |= {stage.SCORE_JSON: score.dumps().encode(), stage.MODE_JSON: mode.dumps().encode(),
                "score-preview.png": png_bytes(score_convert.preview(score)),
                "mode-preview.png": png_bytes(mode_convert.preview(mode, font)),
                "provenance.json": (json.dumps(provenance(base, manifest, cut, rom), indent=1) + "\n").encode()}
    return outputs, mode, score, rom


def registry(sources, base, font, outputs, rom):
    return {"format": stage.REGISTRY_FORMAT,
            "sources": {f"art/stockart32/{name}": sha256(data) for name, data in sources.items()},
            "roms": {"base": sha256(base), "font": sha256(font)},
            "pins": {label: digest for label, *_, digest in source.PINS},
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


def protect_outputs(rom, out, planned, inputs, pxl, renders=()):
    """Refuse the whole batch before any file is written: protected inputs and tracked files (also through links
    and before they exist), the pxl checkout, links inside --out, two outputs on one file, and files in --out
    this run would not write. Before rendering, whatever lies under the `renders` directories counts as planned."""
    out = Path(os.path.abspath(out))
    targets = [out / relative for relative in planned]
    for target in targets:
        stage.protect_output(rom, target, inputs)
        refuse_inside(target, pxl)
        for place in walk_down(out, target):
            if place.is_symlink():
                raise ValueError(f"output aliases protected location through the linked directory {place}")
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError(f"output aliases protected file: {target} is a link or not a regular file")
    resolved = [os.path.normcase(str(t.resolve())).casefold() for t in targets]
    if len(set(resolved)) != len(resolved):
        raise ValueError("output aliases protected output: two outputs resolve to one file")
    if out.exists() and not out.is_dir():
        raise ValueError(f"{out} is not a directory")
    if out.exists():
        wanted = set(targets) | {place for target in targets for place in walk_down(out, target)}
        found = list(out.rglob("*"))
        linked = [p for p in found if p.is_symlink()]
        if linked:
            raise ValueError(f"output aliases protected location through the link {linked[0]}")
        stray = sorted(str(p.relative_to(out)) for p in found
                       if p not in wanted and p.relative_to(out).parts[0] not in renders)
        if stray:
            raise ValueError(f"{out} holds files this run does not write: {', '.join(stray[:5])}")


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
    ap.add_argument("--rom", type=Path, required=True, help="pinned scoreart32 ROM: stock characters, stage input")
    ap.add_argument("--font-rom", type=Path, required=True, help="pinned modeart32 ROM: CHR $00 font, CHR $1B ball")
    ap.add_argument("--pxl", type=Path, required=True, help="pinned claude-pxl checkout")
    ap.add_argument("-o", "--out", type=Path, default=stage.ASSETS, help="output directory (default %(default)s)")
    ap.add_argument("--check", action="store_true", help="write nothing; fail unless every digest is current")
    ap.add_argument("--record", action="store_true", help="accept new digests: install and rewrite the registry")
    args = ap.parse_args()
    if args.check and args.record:
        ap.error("--check writes nothing; drop --record")
    out = Path(os.path.abspath(args.out))
    try:
        pxl = args.pxl.resolve()
        inputs = [args.font_rom, stage.OUTPUT, *(ART / name for name in SOURCES)]
        manifest = parts.load_manifest(ART / "characters.json")
        known = [*FIXED_OUTPUTS, *(f"parts/{p.id}.png" for p in manifest.parts)]
        if not args.check:
            protect_outputs(args.rom, out, known, inputs, pxl, renders=tuple(SCENES))
            if args.record:
                protect_registry(args.rom, inputs)
        sources = read_sources(ART)
        base, font = args.rom.read_bytes(), args.font_rom.read_bytes()
        outputs, mode, score, rom = regenerate(base, font, pxl, sources)
        current = registry(sources, base, font, outputs, rom)
        if not args.record:
            if not stage.REGISTRY.is_file():
                raise AssetError(f"{stage.REGISTRY} is missing; rerun with --record to create it")
            changed = differences(stage.read_registry(), current)
            if changed:
                raise AssetError(f"the regenerated art differs from data/stockart32/digests.json in "
                                 f"{', '.join(changed[:6])}{' and more' if len(changed) > 6 else ''}; "
                                 "rerun with --record to accept it")
        if not args.check:
            protect_outputs(args.rom, out, outputs, inputs, pxl)
            for relative, data in sorted(outputs.items()):
                target = out / relative
                if not target.is_file() or target.read_bytes() != data:
                    write_atomic(target, data)
            if args.record:
                protect_registry(args.rom, inputs)
                write_atomic(stage.REGISTRY, (json.dumps(current, indent=1) + "\n").encode())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"stockart32_convert: {exc}\n")
    changed = sum(a != b for a, b in zip(base, rom))
    if args.check:
        print(f"checked: all {len(outputs)} outputs and the ROM match data/stockart32/digests.json; nothing written")
    else:
        print(f"wrote {out}: {len(outputs)} outputs {'recorded in' if args.record else 'matching'} "
              "data/stockart32/digests.json")
    print(f"  parts: {', '.join(f'{p.id} {p.size[0]}x{p.size[1]}' for p in manifest.parts)}")
    print(f"  score: {score.tiles_used} tiles (78 glyphs, {score.tiles_used - 78} art, {256 - score.tiles_used} free); "
          f"mode: {mode.tiles_used} tiles ({len(mode.font_glyphs)} font, {mode.tiles_used - len(mode.font_glyphs)} art, "
          f"{256 - mode.tiles_used} free)")
    print(f"  stockart32 ROM {sha256(rom)} from scoreart32 {sha256(base)}: {changed} bytes changed")


if __name__ == "__main__":
    main()
