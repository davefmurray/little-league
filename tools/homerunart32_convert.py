#!/usr/bin/env python3
"""Regenerate or check the HOME RUN celebration art: the parts art/homerunart32/cast.json stamps, cut from the
ROM, the two pinned pxl frames of art/homerunart32/homerun32.px.js, their conversion to the stock cutscene's
own data and, in memory, the ROM tools/build_homerunart32.py builds from them.

    .venv/bin/python -B tools/homerunart32_convert.py --rom build/analysisart32.nes --pxl build/vendor/claude-pxl [--out DIR]
    .venv/bin/python -B tools/homerunart32_convert.py --rom ... --pxl ... --check
    .venv/bin/python -B tools/homerunart32_convert.py --rom ... --pxl ... --record

--rom is the pinned analysisart32 ROM: the stage input and the source of every stock byte. --pxl is the
checkout of the commit art/homerunart32/PXL.json pins; it is only read.

Everything is generated in scratch storage first: the parts, cut by tools/stockart32_parts.py with their
reviewed masks (approved parts must equal the digests data/stockart32/digests.json records; a pose reuses an
approved character's rules on another intro panel and must equal its own reviewed mask and PNG); two pinned pxl
renders, byte for byte equal; the conversion and its round trip; every placement's visible part pixels in
each frame it lists, first in the render and then in the built ROM's own bytes, so a placement shared by
both frames is still in both; the previews and provenance. Every output and the ROM must then match
data/homerunart32/digests.json. Only after the whole planned batch passes the output guards is each file
installed under --out (default build/homerunart32) through a sibling temporary file. --check stops before
installing and writes nothing. --record also rewrites data/homerunart32/digests.json, the only tracked file
this tool writes, after every check passed.

The conversion fills exactly the formats the stock cutscene reads:
  per 16x16 cell  the first layout palette holding every non-backdrop color the cell shows in either frame;
                  one attribute table serves both frames
  per 8x8 cell    the (frame a, frame b) pattern pair takes one tile id: CHR $04 holds a, CHR $15 holds b;
                  the 257th distinct pair is refused
  per 16x16 cell  the (TL, TR, BL, BR) quad takes one metatile id, in ascending order from the ids the
                  VICTORY and split-screen maps do not use
  palette         record $0E: the backdrop and the four layout palettes

Under --out:
  parts/<id>.png               the parts the scene stamps, exact NES colors, alpha 0 where clear
  render/scenes/<scene>.png    the two pinned pxl renders the conversion reads
  homerunassets.json           homerunassets/1, which tools/build_homerunart32.py reads
  preview.png                  frames a and b side by side, decoded from the built ROM's own bytes
  provenance.json              per part cell its ROM source; per placement and frame the screen tiles it
                               reaches; the still pixel counts, the budgets and the CHR $15 caveat
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

import analysisart32_convert as accepted
import build_homerunart32 as stage
from build_draw32 import read, refuse_aliases, sha256
from build_scoreart32 import refuse_inside, write_atomic
from build_title32 import protect_output as protect_earlier_output
import homerunart32_assets as model
from homerunart32_assets import AssetError, Cast, HomerunAssets, Layout
import menu32_convert as menu
from scoreart32_convert import read_lock
import stockart32_convert as stock_convert
import stockart32_parts as parts
import stockart32_source as source

ROOT = stage.ROOT
ART = model.ART
SOURCES = ("PXL.json", "homerun32.px.js", "layout.json", "cast.json")
PART_MANIFEST = ROOT / model.PART_MANIFEST
APPROVED = accepted.APPROVED
SCENE_SOURCE = "homerun32.px.js"
FIXED_OUTPUTS = (stage.ASSET_JSON, "preview.png", "provenance.json")
CAVEAT = ("CHR $15 has one other selector: CHR preset 6 ($FB71, CHR0 $15), applied only after the bank-5 split "
          "screen, which only scene $1C reaches. No store writes $1C; SPEED's play exit decrements its own $1D through "
          "$1C and $1B and restores $17 before the dispatcher reads the scene. tools/homerunart32_readers.py checks "
          "that argument statically; root's real-core census must confirm CHR $15 appears only in home-run windows.")


def read_sources(art=ART, part_manifest=PART_MANIFEST):
    found = {f"art/homerunart32/{name}": (Path(art) / name).read_bytes() for name in SOURCES}
    found[model.PART_MANIFEST] = Path(part_manifest).read_bytes()
    return found


def models(sources):
    """The layout, the approved part manifest and the cast, each validated before any pixel is touched."""
    layout = Layout.parse(json.loads(sources["art/homerunart32/layout.json"]),
                          sha256(sources["art/homerunart32/layout.json"]))
    manifest = parts.parse_manifest(json.loads(sources[model.PART_MANIFEST]), sha256(sources[model.PART_MANIFEST]))
    try:
        record = json.loads(sources["art/homerunart32/cast.json"])
    except json.JSONDecodeError as exc:
        raise AssetError(f"cast: not JSON ({exc})") from None
    cast = Cast.parse(record, sha256(sources["art/homerunart32/cast.json"]), {p.id: p for p in manifest.parts})
    return layout, manifest, cast


def specs(manifest, cast):
    """The cut rules of every part the cast stamps: approved entries as reviewed, poses as their base's rules on
    their own panel, with their own drop boxes and reviewed mask."""
    approved = {p.id: p for p in manifest.parts}
    found = {}
    for pid in cast.parts:
        pose = next((p for p in cast.poses if p.id == pid), None)
        found[pid] = approved[pid] if pose is None else replace(
            approved[pose.base], id=pose.id, panel=pose.panel, drop=pose.drop, mask_sha256=pose.mask_sha256)
    return found


def cut(base, rules):
    """{part id: Part}. The input's source ranges must hold their pinned bytes; every character must equal its
    reviewed mask."""
    source.check_pins(base)
    return {pid: parts.cut_character(base, spec) if isinstance(spec, parts.Character) else parts.cut_crowd(base, spec)
            for pid, spec in rules.items()}


def planned_outputs(layout, cast):
    """Every file one run writes, named before anything is rendered."""
    return sorted({*FIXED_OUTPUTS, *(f"render/scenes/{layout.scenes[f]}.png" for f in model.FRAMES),
                   *(f"parts/{pid}.png" for pid in cast.parts)})



def convert(base, layout, renders):
    """The two renders (frame -> PNG bytes) as HomerunAssets, and the RGB rows of each frame."""
    rows = {f: accepted.scene_rgb(renders[f]) for f in model.FRAMES}
    rgb = menu.NES_RGB
    backdrop = rgb[layout.backdrop]
    palettes = [tuple(rgb[c] for c in p) for p in layout.palettes]
    attributes, cell = bytearray(model.ATTRIBUTE_BYTES), {}
    for my in range(15):
        for mx in range(16):
            used = {rows[f][y][x] for f in model.FRAMES for y in range(16 * my, 16 * my + 16)
                    for x in range(16 * mx, 16 * mx + 16)} - {backdrop}
            choice = next((p for p, pal in enumerate(palettes) if used <= set(pal)), None)
            if choice is None:
                found = " ".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in sorted(used))
                raise AssetError(f"16x16 cell col {mx} row {my} shows {found} across both frames: no layout palette "
                                 "holds them all")
            cell[(mx, my)] = choice
            offset, shift = menu.attr_slot(2 * mx, 2 * my)
            attributes[offset] |= choice << shift
    pairs, chr_a, chr_b = {}, bytearray(model.CHR_SIZE), bytearray(model.CHR_SIZE)
    nametable = bytearray(960)
    for ty in range(30):
        for tx in range(32):
            lookup = {backdrop: 0}
            for i, c in enumerate(palettes[cell[(tx >> 1, ty >> 1)]]):
                lookup.setdefault(c, i + 1)
            key = tuple(menu.encode([[lookup[rows[f][8 * ty + j][8 * tx + i]] for i in range(8)] for j in range(8)])
                        for f in model.FRAMES)
            if key not in pairs:
                if len(pairs) == model.TILE_PAIRS:
                    raise AssetError(f"tile col {tx} row {ty} needs pattern pair {len(pairs) + 1}: CHR $04 and $15 "
                                     f"hold {model.TILE_PAIRS}")
                t = pairs[key] = len(pairs)
                chr_a[16 * t:16 * t + 16], chr_b[16 * t:16 * t + 16] = key
            nametable[32 * ty + tx] = pairs[key]
    shared = model.protected_ids(base)
    free = [k for k in range(0x100) if k not in shared]
    quads, metamap, planes = {}, bytearray(model.MAP_IDS), {}
    for my in range(15):
        for mx in range(16):
            top, bottom = 64 * my + 2 * mx, 64 * my + 32 + 2 * mx
            quad = (nametable[top], nametable[top + 1], nametable[bottom], nametable[bottom + 1])
            if quad not in quads:
                if len(quads) == len(free):
                    raise AssetError(f"metatile col {mx} row {my} needs metatile {len(quads) + 1}: the VICTORY and "
                                     f"split-screen maps leave {len(free)} ids")
                quads[quad] = free[len(quads)]
                planes[quads[quad]] = quad
            metamap[16 * my + mx] = quads[quad]
    assets = HomerunAssets(layout_sha256=layout.sha256, renders={f: sha256(renders[f]) for f in model.FRAMES},
                           tile_pairs=len(pairs), chr_a=bytes(chr_a), chr_b=bytes(chr_b), metamap=bytes(metamap),
                           attributes=bytes(attributes), planes=dict(sorted(planes.items())), palette=layout.record())
    for f in model.FRAMES:
        decoded = model.picture(assets.chr(f), assets.nametable(), assets.attributes, assets.palette)
        bad = sum(a != b for ra, rb in zip(decoded, rows[f]) for a, b in zip(ra, rb))
        if bad:
            raise AssetError(f"frame {f}: the asset bytes decode differently from the render in {bad} pixels")
    return assets, rows


def rom_frames(rom):
    """RGB rows of both frames as the built ROM's own bytes show them: the loader's decode of map $24 through set
    $15, record $0E and CHR $04 or $15."""
    _, attributes, nametable = model.decode_screen(rom, model.HR_SET, model.HR_MAP)
    palette = read(rom, model.FIXED, model.record_location(rom), 16)
    return {f: model.picture(read(rom, "chr", model.FRAME_CHR[f] * model.CHR_SIZE, model.CHR_SIZE), nametable,
                             attributes, palette) for f in model.FRAMES}


def check_placements(cast, cut_parts, screens, label):
    """Every visible part pixel of every placement shows its color in each frame it lists; {placement index:
    pixels checked per frame}. A still placement passes in both frames, so its pixels match between them."""
    painted = {}
    for i, p in enumerate(cast.placements):
        counts = {f: accepted.check_placement(p, cut_parts[p.part], screens[f], f"frame {f} of {label}") for f in p.frames}
        if len(set(counts.values())) != 1:
            raise AssetError(f"placement of {p.part} at {list(p.at)}: frames show different pixel counts {counts}")
        painted[i] = counts[p.frames[0]]
    return painted


def still_pixels(cast, painted):
    """Per still part, the visible pixels its shared placements hold identical in both frames."""
    found = {}
    for i, p in enumerate(cast.placements):
        if p.still:
            found[p.part] = found.get(p.part, 0) + painted[i]
    return found


def preview(frames):
    sheet = Image.new("RGB", (2 * 256 + 8, 240), (32, 32, 32))
    for k, f in enumerate(model.FRAMES):
        sheet.paste(accepted.rows_image(frames[f]), (k * (256 + 8), 0))
    return accepted.png_bytes(sheet)



def placement_tiles(placement, part, rom, frame):
    """The screen tiles a placement reaches in `frame`, with the built ROM's tile pair, metatile and palette."""
    shown, (dx, dy) = accepted.visible_rect(placement, part)
    metamap, attributes, nametable = model.decode_screen(rom, model.HR_SET, model.HR_MAP)
    bank = read(rom, "chr", model.FRAME_CHR[frame] * model.CHR_SIZE, model.CHR_SIZE)
    tiles = []
    for ty in range(shown[1] // 8, (shown[1] + shown[3] - 1) // 8 + 1):
        for tx in range(shown[0] // 8, (shown[0] + shown[2] - 1) // 8 + 1):
            rect = stock_convert.intersect((8 * tx, 8 * ty, 8, 8), shown)
            count = sum(part.pixels[y - dy][x - dx] is not None for y in range(rect[1], rect[1] + rect[3])
                        for x in range(rect[0], rect[0] + rect[2]))
            if count:
                tile = nametable[32 * ty + tx]
                tiles.append({"tile": [tx, ty], "pair": tile, "metatile": metamap[16 * (ty // 2) + tx // 2],
                              "pattern_sha256": sha256(bank[16 * tile:16 * tile + 16]),
                              "palette": model.attr_palette(attributes, tx, ty), "pixels": count})
    return tiles


def provenance(base, sources, cast, cut_parts, assets, rom, painted, still):
    poses = {p.id: p for p in cast.poses}
    used_palettes = sorted({model.attr_palette(assets.attributes, 2 * mx, 2 * my) for my in range(15) for mx in range(16)})
    return {
        "format": "homerunart32-provenance/1",
        "base_sha256": sha256(base),
        "rom_sha256": sha256(rom),
        "sources": {name: sha256(data) for name, data in sorted(sources.items())},
        "part_pins": [{"label": label, "bank": bank, "address": f"${address:04X}", "size": size, "sha256": digest}
                      for label, bank, address, size, digest in source.PINS],
        "parts": [{"id": pid, "size": [part.width, part.height], "png_sha256": sha256(parts.png(part)),
                   "mask_sha256": parts.mask_sha256(part.pixels),
                   "rules": ({"pose_of": poses[pid].base, "panel": poses[pid].panel,
                              "drop": [list(b) for b in poses[pid].drop]} if pid in poses
                             else {"approved": model.PART_MANIFEST}),
                   "source": part.source,
                   "cells": [{"cell": [col, row], **record}
                             for (col, row), record in sorted(part.cells.items(), key=lambda c: (c[0][1], c[0][0]))]}
                  for pid, part in cut_parts.items()],
        "placements": [{"part": p.part, "frames": "".join(p.frames), "still": p.still, "at": list(p.at),
                        "area": list(p.area) if p.area else None,
                        "shown": list(accepted.visible_rect(p, cut_parts[p.part])[0]), "pixels": painted[i],
                        "tiles": {f: placement_tiles(p, cut_parts[p.part], rom, f) for f in p.frames}}
                       for i, p in enumerate(cast.placements)],
        "still": still,
        "budget": {"tile_pairs": assets.tile_pairs, "tile_pairs_max": model.TILE_PAIRS,
                   "animated_pairs": assets.animated_pairs, "metatiles": len(assets.planes),
                   "free_metatile_ids": 0x100 - len(model.protected_ids(base)),
                   "protected_metatile_ids": len(model.protected_ids(base)), "palettes_used": used_palettes},
        "frames": {f: {"chr1": f"${model.FRAME_CHR[f]:02X}", "render_sha256": assets.renders[f]} for f in model.FRAMES},
        "caveat": CAVEAT,
        "previews": {"preview.png": "frames a and b decoded from the built ROM's own bytes; not an emulator capture"},
    }


def render_scene(pxl, sources, pngs):
    """Two pinned pxl renders of homerun32.px.js staged with the parts, in scratch: {relative path: bytes}."""
    with tempfile.TemporaryDirectory(prefix="homerunart32-") as temporary:
        directory = Path(temporary) / "homerun"
        (directory / "parts").mkdir(parents=True)
        for name in SOURCES:
            (directory / name).write_bytes(sources[f"art/homerunart32/{name}"])
        for pid, data in pngs.items():
            (directory / "parts" / f"{pid}.png").write_bytes(data)
        stock_convert.check_renderer(pxl, read_lock(directory))
        return stock_convert.render(pxl, directory, SCENE_SOURCE)


def regenerate(base, pxl, sources):
    """Every output under --out as {relative path: bytes}, the assets and the ROM, all built in scratch."""
    if sha256(base) != stage.BASE_SHA256:
        raise AssetError("--rom must be the pinned analysisart32 input")
    layout, manifest, cast = models(sources)
    rules = specs(manifest, cast)
    cut_parts = cut(base, rules)
    pngs = {pid: parts.png(part) for pid, part in cut_parts.items()}
    approved, poses = accepted.approved_parts(), {p.id: p for p in cast.poses}
    for pid, data in pngs.items():
        if pid in poses and sha256(data) != poses[pid].png_sha256:
            raise AssetError(f"pose {pid} differs from its reviewed png_sha256 in art/homerunart32/cast.json")
        if pid not in poses and sha256(data) != approved.get(f"parts/{pid}.png"):
            raise AssetError(f"part {pid} differs from the approved stockart32 part in data/stockart32/digests.json")
    renders = render_scene(pxl, sources, pngs)
    scenes = {f: f"scenes/{layout.scenes[f]}.png" for f in model.FRAMES}
    if set(renders) != set(scenes.values()):
        raise AssetError(f"pxl rendered {sorted(renders)}; expected only {sorted(scenes.values())}")
    assets, rows = convert(base, layout, {f: renders[scenes[f]] for f in model.FRAMES})
    painted = check_placements(cast, cut_parts, rows, "the render")
    rom = stage.build_rom(base, assets)
    frames = rom_frames(rom)
    if frames != rows:
        raise AssetError("the built ROM's own bytes decode differently from the renders")
    check_placements(cast, cut_parts, frames, "the built ROM's screen bytes")
    still = still_pixels(cast, painted)
    outputs = {f"parts/{pid}.png": data for pid, data in pngs.items()}
    outputs |= {f"render/{scenes[f]}": renders[scenes[f]] for f in model.FRAMES}
    outputs |= {stage.ASSET_JSON: assets.dumps().encode(), "preview.png": preview(frames),
                "provenance.json": (json.dumps(provenance(base, sources, cast, cut_parts, assets, rom, painted, still),
                                               indent=1) + "\n").encode()}
    planned = planned_outputs(layout, cast)
    if sorted(outputs) != planned:
        raise AssetError(f"the run produced {sorted(outputs)}, not the planned {planned}")
    return outputs, assets, rom, still


def registry(sources, base, outputs, rom):
    return {"format": stage.REGISTRY_FORMAT,
            "sources": {name: sha256(data) for name, data in sorted(sources.items())},
            "roms": {"base": sha256(base)},
            "pins": {label: digest for label, *_, digest in (*source.PINS, *stage.DIGESTS)},
            "outputs": {path: sha256(data) for path, data in sorted(outputs.items())},
            "rom": sha256(rom)}



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
        for place in accepted.walk_down(out, target):
            if place.is_symlink():
                raise ValueError(f"output aliases protected location through the linked directory {place}")
            if place.exists() and not place.is_dir():
                raise ValueError(f"output aliases protected location: {place} is not a directory")
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError(f"output aliases protected file: {target} is a link or not a regular file")
    resolved = [str(t.resolve()).casefold() for t in targets]
    if len(set(resolved)) != len(resolved):
        raise ValueError("output aliases protected output: two outputs resolve to one file")
    if out.exists():
        wanted = {str(Path(t).relative_to(out)) for t in targets}
        wanted |= {str(p.relative_to(out)) for t in targets for p in accepted.walk_down(out, t)[1:]}
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
    ap.add_argument("--rom", type=Path, required=True, help="pinned analysisart32 ROM: stage input and stock sources")
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
        layout, _, cast = models(sources)
        planned = planned_outputs(layout, cast)
        inputs = [stage.OUTPUT, stage.REGISTRY, *(ART / name for name in SOURCES), PART_MANIFEST, APPROVED]
        if not args.check:
            protect_outputs(args.rom, out, planned, inputs, pxl)
            if args.record:
                protect_registry(args.rom, inputs)
        base = args.rom.read_bytes()
        outputs, assets, rom, still = regenerate(base, pxl, sources)
        current = registry(sources, base, outputs, rom)
        if not args.record:
            if not stage.REGISTRY.is_file():
                raise AssetError(f"{stage.REGISTRY} is missing; rerun with --record to create it")
            changed = accepted.differences(stage.read_registry(), current)
            if changed:
                raise AssetError(f"the regenerated art differs from data/homerunart32/digests.json in "
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
        ap.exit(2, f"homerunart32_convert: {exc}\n")
    changed = sum(a != b for a, b in zip(base, rom))
    if args.check:
        print(f"checked: all {len(outputs)} outputs and the ROM match data/homerunart32/digests.json; nothing written")
    else:
        print(f"wrote {out}: {len(outputs)} outputs {'recorded in' if args.record else 'matching'} "
              "data/homerunart32/digests.json")
    print(f"  {assets.tile_pairs}/{model.TILE_PAIRS} tile pairs ({assets.animated_pairs} animated), "
          f"{len(assets.planes)} metatiles; still: " + ", ".join(f"{pid} {n} px" for pid, n in still.items()))
    print(f"  homerunart32 ROM {sha256(rom)} from analysisart32 {sha256(base)}: {changed} bytes changed")


if __name__ == "__main__":
    main()
