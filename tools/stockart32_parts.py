#!/usr/bin/env python3
"""The stock-character manifest (art/stockart32/characters.json) and the parts it cuts from the ROM.

Format stockchars/1 holds references into ROM bytes, never pixels:

  characters[]  id            path-safe part name, unique among all parts
                source        {kind: "intro-panel", panel: 0-6}
                crop          [x, y, w, h] in the 64x64 panel, on its 8-pixel grid: one source tile per part cell
                seeds[]       {at, through, box?, why}: 4-connected floods of scenery from `at` through the listed
                              source colors, inside `box` (crop space) when given
                specks[]      {box, colors, size, why}: opaque components of at most `size` pixels lying wholly in
                              `box`, all in the listed colors (fence and bleacher dither)
                drop[]        [x, y, w, h] boxes of scenery (a neighbor cut by the crop), with drop_why
                scenery_colors  source colors that are scenery wherever they appear
                ink_grow      ink floods on through transparent pixels touching no scenery (dark hair)
                ink_keep[]    reviewed source-zero pixels the silhouette keeps, [x, y] in crop space, with ink_keep_why
                faces[]       [x, y, w, h] boxes the review checks: opaque non-sky source pixels there must survive
                ink           color of the kept source zeros (outline, hair); the target screen's backdrop
                colors        {source color: target color}; a figure color without a target is an error
                target        {screen: "score" | "mode", palette: 0-3}, the background palette the part must fit
                mask_sha256   the reviewed silhouette, hashed from the cut pixels
                reference     {capture, sha256, crop}: the screenshot the source decode was matched against,
                              evidence only; regeneration never reads it
  crowds[]      id, ink, target {screen, palettes: {shirt: palette}}, reference, arrangement_why
                source        {kind: "stands-block", metatiles: {key: {tiles: [4 CHR $10 ids], palette}}, rows}
                              rows hold cells "<metatile key><shirt>"; the arrangement is screenshot-observed
                shirts        {shirt: {source color: target color}}
  placements[]  {part, screen, at: [x, y], area?: [x, y, w, h] of the part, visible?: [x, y, w, h] of the
                screen, why?}: where the pxl source stamps a part and which of its pixels stay visible

Colors are two uppercase hex digits. Every box and point lies inside its crop, part or screen. A part's
pixels come only from these rules: changing a part means changing its crop, seeds, boxes, points or colors.

A part pixel is scenery (clear) by the seed, speck, drop and scenery-color rules; every other opaque
pixel is figure, recolored through `colors`. A transparent source pixel 8-adjacent to the figure, or
enclosed by it, is ink; with ink_grow, ink also floods through transparent pixels that touch no scenery.
ink_keep adds reviewed source zeros that the automatic rules miss. Other pixels are clear. These rules
cannot tell hair from transparent fence dither on their own; mask_sha256 freezes the reviewed result.
"""
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image

import menu32_convert as menu
import stockart32_source as source

FORMAT = "stockchars/1"
SCREENS = {"score": (256, 240), "mode": (256, 240)}
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
COLOR = re.compile(r"[0-9A-F]{2}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TOP_KEYS = {"format", "about", "characters", "crowds", "placements"}
CHARACTER_KEYS = {"id", "source", "crop", "seeds", "specks", "drop", "drop_why", "scenery_colors", "ink_grow",
                  "ink_keep", "ink_keep_why", "faces", "ink", "colors", "recolor_why", "target", "mask_sha256",
                  "reference"}
CHARACTER_REQUIRED = {"id", "source", "crop", "faces", "ink", "colors", "target", "mask_sha256"}
CROWD_KEYS = {"id", "source", "shirts", "ink", "target", "reference", "arrangement_why"}
PLACEMENT_KEYS = {"part", "screen", "at", "area", "visible", "why"}


class ManifestError(ValueError):
    pass



@dataclass(frozen=True)
class Seed:
    at: tuple
    through: frozenset
    box: tuple


@dataclass(frozen=True)
class Specks:
    box: tuple
    colors: frozenset
    size: int


@dataclass(frozen=True)
class Character:
    id: str
    panel: int
    crop: tuple
    seeds: tuple
    specks: tuple
    drop: tuple
    scenery_colors: frozenset
    ink_grow: bool
    ink_keep: tuple
    faces: tuple
    ink: int
    colors: dict
    screen: str
    palette: int
    mask_sha256: str

    @property
    def size(self):
        return self.crop[2:]


@dataclass(frozen=True)
class Crowd:
    id: str
    metatiles: dict           # key -> ((tl, tr, bl, br), stands palette)
    rows: tuple               # rows of (metatile key, shirt)
    shirts: dict              # shirt -> {source color: target color}
    ink: int
    screen: str
    palettes: dict            # shirt -> target background palette

    @property
    def size(self):
        return 16 * len(self.rows[0]), 16 * len(self.rows)


@dataclass(frozen=True)
class Placement:
    part: str
    screen: str
    at: tuple
    area: tuple | None        # None: the whole part
    visible: tuple | None     # None: wherever the stamp lands on screen


@dataclass(frozen=True)
class Manifest:
    characters: tuple
    crowds: tuple
    placements: tuple
    sha256: str

    @property
    def parts(self):
        return self.characters + self.crowds


def fail(where, message):
    raise ManifestError(f"{where}: {message}")


def keys(value, where, allowed, required):
    if not isinstance(value, dict):
        fail(where, "must be an object")
    if not required <= set(value) <= allowed:
        fail(where, f"keys must be among {', '.join(sorted(allowed))}; missing {sorted(required - set(value))}, "
                    f"unknown {sorted(set(value) - allowed)}")
    return value


def integer(value, where, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        fail(where, f"must be an integer from {low} to {high}")
    return value


def text(value, where):
    if not isinstance(value, str) or not value.strip():
        fail(where, "must be a non-empty string")
    return value


def color(value, where):
    if not isinstance(value, str) or not COLOR.fullmatch(value):
        fail(where, "must be an NES color, two uppercase hex digits")
    try:
        return menu.nes_color(value)
    except menu.AssetError as exc:
        fail(where, str(exc))


def colors(value, where):
    if not isinstance(value, list) or not value:
        fail(where, "must be a non-empty list of NES colors")
    found = [color(c, f"{where}[{i}]") for i, c in enumerate(value)]
    if len(set(found)) != len(found):
        fail(where, "lists a color twice")
    return frozenset(found)


def recolor(value, where):
    if not isinstance(value, dict) or not value:
        fail(where, "must map source colors to target colors")
    return {color(k, f"{where} key {k!r}"): color(v, f"{where}[{k!r}]") for k, v in value.items()}


def point(value, where, width, height):
    if not isinstance(value, list) or len(value) != 2:
        fail(where, "must be [x, y]")
    return integer(value[0], f"{where} x", 0, width - 1), integer(value[1], f"{where} y", 0, height - 1)


def box(value, where, width, height):
    """[x, y, w, h], positive and wholly inside a width x height space."""
    if not isinstance(value, list) or len(value) != 4:
        fail(where, "must be [x, y, w, h]")
    x, y = integer(value[0], f"{where} x", 0, width - 1), integer(value[1], f"{where} y", 0, height - 1)
    w, h = integer(value[2], f"{where} w", 1, width - x), integer(value[3], f"{where} h", 1, height - y)
    return x, y, w, h


def boxes(value, where, width, height, required=False):
    if not isinstance(value, list) or (required and not value):
        fail(where, "must be a " + ("non-empty " if required else "") + "list of [x, y, w, h]")
    return tuple(box(b, f"{where}[{i}]", width, height) for i, b in enumerate(value))


def target(value, where):
    keys(value, where, {"screen", "palette", "palettes"}, {"screen"})
    text(value["screen"], f"{where} screen")
    if value["screen"] not in SCREENS:
        fail(f"{where} screen", f"must be one of {', '.join(SCREENS)}")
    return value["screen"]


def reference(value, where):
    keys(value, where, {"capture", "sha256", "crop", "matched"}, {"capture", "sha256", "crop"})
    text(value["capture"], f"{where} capture")
    if not isinstance(value["sha256"], str) or not HEX64.fullmatch(value["sha256"]):
        fail(f"{where} sha256", "must be a lowercase SHA-256")
    box(value["crop"], f"{where} crop", *SCREENS["score"])


def character(entry, where):
    keys(entry, where, CHARACTER_KEYS, CHARACTER_REQUIRED)
    src = keys(entry["source"], f"{where} source", {"kind", "panel"}, {"kind", "panel"})
    if src["kind"] != "intro-panel":
        fail(f"{where} source kind", "must be intro-panel")
    panel = integer(src["panel"], f"{where} source panel", 0, len(source.PANELS) - 1)
    crop = box(entry["crop"], f"{where} crop", source.PANEL_SIZE, source.PANEL_SIZE)
    if any(v % 8 for v in crop):
        fail(f"{where} crop", "must stay on the source's 8-pixel tile grid")
    w, h = crop[2:]
    for name in ("seeds", "specks", "ink_keep"):
        if not isinstance(entry.get(name, []), list):
            fail(f"{where} {name}", "must be a list")
    seeds = []
    for i, seed in enumerate(entry.get("seeds", [])):
        at = f"{where} seeds[{i}]"
        keys(seed, at, {"at", "through", "box", "why"}, {"at", "through", "why"})
        start = point(seed["at"], f"{at} at", w, h)
        area = box(seed["box"], f"{at} box", w, h) if "box" in seed else (0, 0, w, h)
        if not (area[0] <= start[0] < area[0] + area[2] and area[1] <= start[1] < area[1] + area[3]):
            fail(f"{at} at", "must lie inside the seed's box")
        text(seed["why"], f"{at} why")
        seeds.append(Seed(start, colors(seed["through"], f"{at} through"), area))
    specks = []
    for i, rule in enumerate(entry.get("specks", [])):
        at = f"{where} specks[{i}]"
        keys(rule, at, {"box", "colors", "size", "why"}, {"box", "colors", "size", "why"})
        text(rule["why"], f"{at} why")
        specks.append(Specks(box(rule["box"], f"{at} box", w, h), colors(rule["colors"], f"{at} colors"),
                             integer(rule["size"], f"{at} size", 1, w * h)))
    drop = boxes(entry.get("drop", []), f"{where} drop", w, h)
    if drop or "drop_why" in entry:
        text(entry.get("drop_why"), f"{where} drop_why")
    keep = [point(p, f"{where} ink_keep[{i}]", w, h) for i, p in enumerate(entry.get("ink_keep", []))]
    if len(set(keep)) != len(keep):
        fail(f"{where} ink_keep", "names a pixel twice")
    if keep or "ink_keep_why" in entry:
        text(entry.get("ink_keep_why"), f"{where} ink_keep_why")
    if "recolor_why" in entry:
        text(entry["recolor_why"], f"{where} recolor_why")
    if not isinstance(entry.get("ink_grow", False), bool):
        fail(f"{where} ink_grow", "must be true or false")
    if not isinstance(entry["mask_sha256"], str) or not HEX64.fullmatch(entry["mask_sha256"]):
        fail(f"{where} mask_sha256", "must be a lowercase SHA-256")
    if "reference" in entry:
        reference(entry["reference"], f"{where} reference")
    screen = target(entry["target"], f"{where} target")
    if "palettes" in entry["target"] or "palette" not in entry["target"]:
        fail(f"{where} target", "a character fits one palette: {screen, palette}")
    return Character(
        id=entry["id"], panel=panel, crop=crop, seeds=tuple(seeds), specks=tuple(specks), drop=drop,
        scenery_colors=colors(entry["scenery_colors"], f"{where} scenery_colors") if "scenery_colors" in entry
        else frozenset(),
        ink_grow=entry.get("ink_grow", False), ink_keep=tuple(keep),
        faces=boxes(entry["faces"], f"{where} faces", w, h, required=True), ink=color(entry["ink"], f"{where} ink"),
        colors=recolor(entry["colors"], f"{where} colors"), screen=screen,
        palette=integer(entry["target"]["palette"], f"{where} target palette", 0, 3),
        mask_sha256=entry["mask_sha256"])


def crowd(entry, where):
    keys(entry, where, CROWD_KEYS, {"id", "source", "shirts", "ink", "target", "arrangement_why"})
    src = keys(entry["source"], f"{where} source", {"kind", "metatiles", "rows"}, {"kind", "metatiles", "rows"})
    if src["kind"] != "stands-block":
        fail(f"{where} source kind", "must be stands-block")
    text(entry["arrangement_why"], f"{where} arrangement_why")
    if "reference" in entry:
        reference(entry["reference"], f"{where} reference")
    if not isinstance(src["metatiles"], dict) or not src["metatiles"]:
        fail(f"{where} metatiles", "must map one-letter keys to metatiles")
    metatiles = {}
    for key, meta in src["metatiles"].items():
        at = f"{where} metatiles[{key!r}]"
        if not re.fullmatch(r"[A-Z]", key):
            fail(at, "keys are single uppercase letters")
        keys(meta, at, {"tiles", "palette"}, {"tiles", "palette"})
        tiles = meta["tiles"]
        if not isinstance(tiles, list) or len(tiles) != 4 or not all(isinstance(t, str) and COLOR.fullmatch(t)
                                                                     for t in tiles):
            fail(f"{at} tiles", "must be four CHR $10 tile ids, two uppercase hex digits each")
        metatiles[key] = (tuple(int(t, 16) for t in tiles), integer(meta["palette"], f"{at} palette", 0, 3))
    if not isinstance(entry["shirts"], dict) or not entry["shirts"]:
        fail(f"{where} shirts", "must map shirt names to recolors")
    shirts = {}
    for name, mapping in entry["shirts"].items():
        if not re.fullmatch(r"[a-z]", name):
            fail(f"{where} shirts", "names are single lowercase letters")
        shirts[name] = recolor(mapping, f"{where} shirts[{name!r}]")
    rows = src["rows"]
    if (not isinstance(rows, list) or not rows or not all(isinstance(r, list) and r for r in rows)
            or len({len(r) for r in rows}) != 1):
        fail(f"{where} rows", "must be equal-length non-empty rows of metatile cells")
    cells = []
    for j, row in enumerate(rows):
        line = []
        for i, cell in enumerate(row):
            if not isinstance(cell, str) or len(cell) != 2 or cell[0] not in metatiles or cell[1] not in shirts:
                fail(f"{where} rows[{j}][{i}]", "must be a metatile key and a shirt name, as 'Br'")
            line.append((cell[0], cell[1]))
        cells.append(tuple(line))
    if 16 * len(rows) > 240 or 16 * len(rows[0]) > 256:
        fail(f"{where} rows", "the block must fit on one screen")
    screen = target(entry["target"], f"{where} target")
    palettes = entry["target"].get("palettes")
    if "palette" in entry["target"] or not isinstance(palettes, dict) or set(palettes) != set(shirts):
        fail(f"{where} target", "a crowd names one palette per shirt: {screen, palettes: {shirt: palette}}")
    return Crowd(id=entry["id"], metatiles=metatiles, rows=tuple(cells), shirts=shirts,
                 ink=color(entry["ink"], f"{where} ink"), screen=screen,
                 palettes={k: integer(v, f"{where} target palettes[{k!r}]", 0, 3) for k, v in palettes.items()})


def placement(entry, where, sizes, screens):
    keys(entry, where, PLACEMENT_KEYS, {"part", "screen", "at"})
    text(entry["part"], f"{where} part")
    if entry["part"] not in sizes:
        fail(f"{where} part", f"names no part: {entry['part']!r}")
    if entry["screen"] != screens[entry["part"]]:
        fail(f"{where} screen", f"{entry['part']} targets the {screens[entry['part']]} screen")
    width, height = SCREENS[entry["screen"]]
    at = point(entry["at"], f"{where} at", width, height)
    area = box(entry["area"], f"{where} area", *sizes[entry["part"]]) if "area" in entry else None
    visible = box(entry["visible"], f"{where} visible", width, height) if "visible" in entry else None
    if "why" in entry:
        text(entry["why"], f"{where} why")
    return Placement(entry["part"], entry["screen"], at, area, visible)


def parse_manifest(data, digest):
    keys(data, "manifest", TOP_KEYS, TOP_KEYS)
    if data["format"] != FORMAT:
        fail("manifest", f"expected format {FORMAT}")
    text(data["about"], "manifest about")
    for name in ("characters", "crowds", "placements"):
        if not isinstance(data[name], list) or not data[name]:
            fail(f"manifest {name}", "must be a non-empty list")
    ids = []
    for kind in ("characters", "crowds"):
        for i, entry in enumerate(data[kind]):
            name = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(name, str) or len(name) > 32 or not ID.fullmatch(name):
                fail(f"{kind}[{i}] id", "must be a path-safe lowercase name like 'crowd-red', at most 32 characters")
            ids.append(name)
    if len(set(ids)) != len(ids):
        fail("manifest", "part ids must be unique")
    characters = tuple(character(e, f"character {e['id']}") for e in data["characters"])
    crowds = tuple(crowd(e, f"crowd {e['id']}") for e in data["crowds"])
    sizes = {p.id: p.size for p in characters + crowds}
    screens = {p.id: p.screen for p in characters + crowds}
    placements = tuple(placement(e, f"placements[{i}]", sizes, screens) for i, e in enumerate(data["placements"]))
    unplaced = sorted(set(ids) - {p.part for p in placements})
    if unplaced:
        fail("manifest placements", f"place every part; {', '.join(unplaced)} never appear")
    return Manifest(characters, crowds, placements, digest)


def load_manifest(path):
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest: not JSON ({exc})") from None
    return parse_manifest(data, hashlib.sha256(raw).hexdigest())


def check_targets(manifest, screens):
    """Every target color of every part sits in its target palette; ink is the screen's backdrop.

    `screens` maps a screen name to (backdrop, four palettes of three NES colors)."""
    for part in manifest.parts:
        backdrop, palettes = screens[part.screen]
        if part.ink != backdrop:
            fail(f"part {part.id}", f"ink ${part.ink:02X} must be the {part.screen} backdrop ${backdrop:02X}")
        wanted = ([(part.palette, set(part.colors.values()))] if isinstance(part, Character)
                  else [(part.palettes[s], set(m.values())) for s, m in part.shirts.items()])
        for index, targets in wanted:
            stray = sorted(targets - set(palettes[index]) - {backdrop})
            if stray:
                fail(f"part {part.id}", f"targets {' '.join(f'${c:02X}' for c in stray)} are not in {part.screen} "
                                        f"palette {index}")



@dataclass(frozen=True)
class Part:
    id: str
    pixels: tuple             # rows of target NES colors, None where clear
    source: dict              # the source composition's record and the crop
    cells: dict               # (col, row) -> the source record of that part cell, with pixel counts

    @property
    def width(self):
        return len(self.pixels[0])

    @property
    def height(self):
        return len(self.pixels)


def mask_sha256(pixels):
    """SHA-256 of the silhouette: per 8x8 cell in row-major order, eight row bytes, bit 7 the left pixel."""
    data = bytes(sum((pixels[y + j][x + i] is not None) << (7 - i) for i in range(8))
                 for y in range(0, len(pixels), 8) for x in range(0, len(pixels[0]), 8) for j in range(8))
    return hashlib.sha256(data).hexdigest()


def flood(start, passable, w, h):
    seen, stack = set(), [start]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h) or not passable(x, y):
            continue
        seen.add((x, y))
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return seen


def components(cells, w, h):
    left, out = set(cells), []
    while left:
        part = flood(next(iter(left)), lambda x, y: (x, y) in left, w, h)
        left -= part
        out.append(part)
    return out


def touches(x, y, cells):
    return any((x + dx, y + dy) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def silhouette(rom, spec):
    """The part one character entry describes, before its silhouette is compared with the review."""
    record, composition = source.intro_panel(rom, spec.panel)
    cx, cy, w, h = spec.crop
    src = [row[cx:cx + w] for row in composition.pixels[cy:cy + h]]
    opaque = {(x, y) for y in range(h) for x in range(w) if src[y][x].value}
    scenery = set()
    for seed in spec.seeds:
        x, y = seed.at
        bx, by, bw, bh = seed.box
        if (x, y) not in opaque or src[y][x].color not in seed.through:
            fail(f"part {spec.id}", f"seed {list(seed.at)} is not an opaque "
                                    f"{'/'.join(f'${c:02X}' for c in sorted(seed.through))} pixel")
        scenery |= flood((x, y), lambda X, Y: (X, Y) in opaque and src[Y][X].color in seed.through
                         and bx <= X < bx + bw and by <= Y < by + bh, w, h)
    for rule in spec.specks:
        x0, y0, bw, bh = rule.box
        for comp in components(opaque - scenery, w, h):
            if len(comp) <= rule.size and all(src[y][x].color in rule.colors and x0 <= x < x0 + bw
                                              and y0 <= y < y0 + bh for x, y in comp):
                scenery |= comp
    for x0, y0, bw, bh in spec.drop:
        scenery |= {(x, y) for x, y in opaque if x0 <= x < x0 + bw and y0 <= y < y0 + bh}
    scenery |= {(x, y) for x, y in opaque if src[y][x].color in spec.scenery_colors}
    figure = opaque - scenery
    missing = sorted({src[y][x].color for x, y in figure} - set(spec.colors))
    if missing:
        fail(f"part {spec.id}", f"figure colors {' '.join(f'${c:02X}' for c in missing)} have no target")
    outside = set()
    for x in range(w):
        for y in (0, h - 1):
            if (x, y) not in figure:
                outside |= flood((x, y), lambda X, Y: (X, Y) not in figure, w, h)
    for y in range(h):
        for x in (0, w - 1):
            if (x, y) not in figure and (x, y) not in outside:
                outside |= flood((x, y), lambda X, Y: (X, Y) not in figure, w, h)
    clear = {(x, y) for y in range(h) for x in range(w) if not src[y][x].value}
    ink = {p for p in clear if touches(*p, figure) or p not in outside}
    if spec.ink_grow:
        dark = {p for p in clear if not touches(*p, scenery)}
        for p in list(ink):
            if p in dark:
                ink |= flood(p, lambda X, Y: (X, Y) in dark, w, h)
    for x, y in spec.ink_keep:
        if src[y][x].value:
            fail(f"part {spec.id}", f"ink_keep [{x}, {y}] must name a transparent source pixel")
        ink.add((x, y))
    pixels = tuple(tuple(spec.colors[src[y][x].color] if (x, y) in figure else spec.ink if (x, y) in ink else None
                         for x in range(w)) for y in range(h))
    cells = {}
    for row in range(h // 8):
        for col in range(w // 8):
            box_pixels = [(8 * col + i, 8 * row + j) for j in range(8) for i in range(8)]
            cells[(col, row)] = {**composition.cells[(cx // 8 + col, cy // 8 + row)],
                                 "kept": sum(p in figure for p in box_pixels), "ink": sum(p in ink for p in box_pixels),
                                 "opaque": sum(p in opaque for p in box_pixels)}
    return Part(spec.id, pixels, {**record, "crop": list(spec.crop)}, cells)


def cut_character(rom, spec):
    """The part one character entry describes; its silhouette must equal the reviewed mask_sha256."""
    part = silhouette(rom, spec)
    if mask_sha256(part.pixels) != spec.mask_sha256:
        fail(f"part {spec.id}", "the cut silhouette differs from the reviewed mask_sha256")
    return part


def cut_crowd(rom, spec):
    """A crowd block: its metatile rows, each metatile recolored by its shirt; source zeros become ink."""
    composition = source.stands_block(rom, spec.metatiles, [[key for key, _ in row] for row in spec.rows])
    pixels = []
    for y, line in enumerate(composition.pixels):
        out = []
        for x, pixel in enumerate(line):
            if not pixel.value:
                out.append(spec.ink)
                continue
            shirt = spec.shirts[spec.rows[y // 16][x // 16][1]]
            if pixel.color not in shirt:
                fail(f"part {spec.id}", f"shirt {spec.rows[y // 16][x // 16][1]!r} has no target for ${pixel.color:02X}")
            out.append(shirt[pixel.color])
        pixels.append(tuple(out))
    cells = {(col, row): {**record, "shirt": spec.rows[row // 2][col // 2][1]}
             for (col, row), record in composition.cells.items()}
    return Part(spec.id, tuple(pixels), {"kind": "stands-block", "arrangement": "screenshot-observed",
                                         "rows": ["".join(f"{k}{s}" for k, s in row) for row in spec.rows]}, cells)


def cut_parts(rom, manifest):
    """Every part the manifest describes, by id. The ROM's source ranges must hold their pinned bytes."""
    source.check_pins(rom)
    parts = {c.id: cut_character(rom, c) for c in manifest.characters}
    parts |= {c.id: cut_crowd(rom, c) for c in manifest.crowds}
    return parts


def png(part):
    """The part as a pxl-ready PNG: exact NES colors, alpha 0 where clear."""
    image = Image.new("RGBA", (part.width, part.height), (0, 0, 0, 0))
    for y, row in enumerate(part.pixels):
        for x, c in enumerate(row):
            if c is not None:
                image.putpixel((x, y), (*menu.NES_RGB[c], 255))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return encoded.getvalue()
