#!/usr/bin/env python3
"""Convert the pxl scoreboard art into data/scoreart32/scoreassets.json.

    .venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes
    .venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --check [--pxl build/vendor/claude-pxl]
    .venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --preview build/scoreart32-preview.png
    .venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --art DIR -o JSON

--art names the art directory (default art/scoreart32) and -o the asset file (default
data/scoreart32/scoreassets.json). --rom must be the pinned modeart32 input, whose CHR $00 font
letters the layout's menu-font text. --pxl renders the art's score32.px.js with the pinned pxl
checkout its PXL.json names (commit and minimum Node). With --check it renders twice, requires
both renders to match byte for byte and to reproduce every PNG under the art's out/ pixel for
pixel, and requires -o to hold this output already; --check writes nothing. Without --check, --pxl
replaces those PNGs before converting, each through a sibling temporary file, and only after
every destination passes the output guards. Without --pxl the PNGs are converted as they are.

The art directory holds:
  score32.px.js, PXL.json     pxl source and renderer pin
  layout.json                 colors and lettering, below
  out/scenes/score.png        the 256x240 background
  out/sprites/big.png         176x16: the 16x16 value glyphs 0-9 and X, left to right
  out/sprites/narrow.png      88x16: the 8x16 narrow glyphs 0-9 and X
  out/sprites/head.png        88x8: the inning header digits 0-9, then the header blank
  out/sprites/sep.png         8x8: the statistic separator

layout.json, format scoreart32-layout/2:
  backdrop          the shared backdrop color
  palettes          four background palettes of three colors; palette 0 draws every glyph
  sprite_palettes   four sprite palettes; the team names use palette 0 with the stock CHR $18 font
  text              [{x, y, text, font, color}] stamped at pixel (x, y) over backdrop pixels only:
                    font "menu" is the CHR $00 font, a letter every 8 pixels; "mini" the 3x5 MINI
                    capitals below, a letter every 4 pixels

The converter enforces what pxl cannot: exact NES colors, one palette per 16x16 attribute cell,
palette 0 wherever the stock writer draws, blank art and text under the writer and the team-name
sprites (tools/scoreart32_assets.GEOMETRY), glyph sprites in palette 0, a blank header blank, and
the 256-tile budget of CHR $05, 78 of whose tiles are the glyphs at their stock ids. Plain backdrop
takes the header blank $E8, never a digit quarter that happens to be empty; another background tile
equal to a glyph takes that glyph's lowest id; the rest take the lowest free ids in nametable order.
--preview writes the bare background beside a sample board the stock rules draw, without name
sprites. tools/scoreart32_assets.py documents the output, scoreassets/1.
"""
import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image

from build_draw32 import refuse_aliases
from build_scoreart32 import (
    ART, BASE_SHA256, PROTECTED_SHA256, protected_paths, refuse_inside, write_atomic,
)
from build_title32 import protect_output as protect_earlier_output
import menu32_convert as menu
from menu32_convert import AssetError
from scoreart32_assets import (
    ASSETS, BLANK, GEOMETRY, GLYPH_PALETTE, GLYPHS, HEAD_ORDER, HEADER, SEPARATOR, SOURCES, Board, ScoreAssets,
    big, drawn, narrow,
)

LAYOUT_FORMAT = "scoreart32-layout/2"
LAYOUT_KEYS = {"format", "backdrop", "palettes", "sprite_palettes", "text"}
TEXT_KEYS = {"x", "y", "text", "font", "color"}
SCENE = "out/scenes/score.png"
GLYPH_SHEETS = {"big": (176, 16), "narrow": (88, 16), "head": (88, 8), "sep": (8, 8)}
PITCH = {"menu": 8, "mini": 4}
MINI = {
    "A": [".X.", "X.X", "XXX", "X.X", "X.X"], "B": ["XX.", "X.X", "XX.", "X.X", "XX."],
    "C": [".XX", "X..", "X..", "X..", ".XX"], "D": ["XX.", "X.X", "X.X", "X.X", "XX."],
    "E": ["XXX", "X..", "XX.", "X..", "XXX"], "H": ["X.X", "X.X", "XXX", "X.X", "X.X"],
    "I": ["XXX", ".X.", ".X.", ".X.", "XXX"], "K": ["X.X", "X.X", "XX.", "X.X", "X.X"],
    "P": ["XX.", "X.X", "XX.", "X..", "X.."], "R": ["XX.", "X.X", "XX.", "X.X", "X.X"],
    "S": [".XX", "X..", ".X.", "..X", "XX."], "T": ["XXX", ".X.", ".X.", ".X.", ".X."],
}
PREVIEW_BOARD = Board(halves=12, line=bytes((0, 1, 2, 0, 0, 0, 1, 1, 12, 0, 3, 0x82)) + bytes(30), runs=(16, 6),
                      stats=((31, 28), (12, 8), (1, 0), (4, 6), (2, 3), (1, 0), (0, 1)))


@dataclass(frozen=True)
class Text:
    x: int
    y: int
    text: str
    font: str
    color: int


@dataclass(frozen=True)
class Layout:
    """layout.json, validated."""
    backdrop: int
    palettes: tuple           # four BG palettes of three NES colors
    sprite_palettes: tuple
    text: tuple


def integer(value, where, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise AssetError(f"{where} must be an integer from {low} to {high}")
    return value


def color(value, where):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{2}", value):
        raise AssetError(f"{where} must be a two-digit NES color string")
    return menu.nes_color(value)


def palette_set(layout, key, backdrop):
    value = layout[key]
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(p, list) and len(p) == 3 for p in value):
        raise AssetError(f"{key} must be four palettes of three NES color strings")
    palettes = tuple(tuple(color(c, f"{key}[{i}]") for c in p) for i, p in enumerate(value))
    for i, p in enumerate(palettes):
        if len(set(p)) != 3 or backdrop in p:
            raise AssetError(f"{key}[{i}] must hold three distinct colors besides the backdrop")
    return palettes


def read_layout(path):
    layout = json.loads(Path(path).read_text())
    if not isinstance(layout, dict):
        raise AssetError("the layout must be a JSON object")
    if layout.get("format") != LAYOUT_FORMAT:
        raise AssetError(f"unknown layout format; expected {LAYOUT_FORMAT}")
    if set(layout) != LAYOUT_KEYS:
        raise AssetError(f"layout keys must be {', '.join(sorted(LAYOUT_KEYS))}; missing "
                         f"{sorted(LAYOUT_KEYS - set(layout))}, unknown {sorted(set(layout) - LAYOUT_KEYS)}")
    backdrop = color(layout["backdrop"], "backdrop")
    palettes = palette_set(layout, "palettes", backdrop)
    sprite_palettes = palette_set(layout, "sprite_palettes", backdrop)
    if not isinstance(layout["text"], list):
        raise AssetError("text must be one list of {x, y, text, font, color}")
    colors = {c for p in palettes for c in p}
    text = []
    for i, entry in enumerate(layout["text"]):
        where = f"text[{i}]"
        if not isinstance(entry, dict) or set(entry) != TEXT_KEYS:
            raise AssetError(f"{where} must hold exactly color, font, text, x and y")
        words = entry["text"]
        if not isinstance(words, str) or not re.fullmatch(r"[ -~]+", words) or not words.strip():
            raise AssetError(f"{where} text must be printable ASCII")
        if not isinstance(entry["font"], str) or entry["font"] not in PITCH:
            raise AssetError(f"{where} font must be one of {', '.join(PITCH)}")
        ink = color(entry["color"], f"{where} color")
        if ink not in colors:
            raise AssetError(f"{where} color ${ink:02X} is in no background palette")
        text.append(Text(integer(entry["x"], f"{where} x", 0, 255), integer(entry["y"], f"{where} y", 0, 239),
                         entry["text"], entry["font"], ink))
    return Layout(backdrop, palettes, sprite_palettes, tuple(text))


def letter(font, rom_font, ch, where):
    """Ink flags of one letter, row by row."""
    if font == "menu":
        glyph = rom_font[ord(ch)]
        if ch != " " and not any(glyph):
            raise AssetError(f"{where}: CHR $00 has no glyph for {ch!r}")
        return [[1 if v else 0 for v in line] for line in menu.decode(glyph)]
    if ch == " ":
        return []
    if ch not in MINI:
        raise AssetError(f"{where}: the mini font has no glyph for {ch!r}")
    return [[1 if c == "X" else 0 for c in line] for line in MINI[ch]]


def blank(rows, col, row, backdrop):
    return all(c == backdrop for line in menu.tile_pixels(rows, col, row) for c in line)


def stamp(rows, rom_font, text, backdrop, reserved):
    """Ink `text` onto backdrop pixels outside the writer and name cells."""
    where = f"text {text.text!r}"
    x = text.x
    for ch in text.text:
        for j, line in enumerate(letter(text.font, rom_font, ch, where)):
            for i, on in enumerate(line):
                px, py = x + i, text.y + j
                if not on:
                    continue
                if not (0 <= px < 256 and 0 <= py < 240):
                    raise AssetError(f"{where} runs off the screen at ({px},{py})")
                if (px // 8, py // 8) in reserved:
                    raise AssetError(f"{where} inks writer or name cell ({px // 8},{py // 8})")
                if rows[py][px] != backdrop:
                    raise AssetError(f"{where}: art under ({px},{py})")
                rows[py][px] = text.color
        x += PITCH[text.font]


def cell_palettes(rows, layout):
    """Attribute cell -> palette: palette 0 where the writer draws, else the first that holds its colors."""
    forced = GEOMETRY.glyph_attribute_cells()
    chosen, errors = {}, []
    for ay in range(15):
        for ax in range(16):
            colors = {c for y in range(16 * ay, 16 * ay + 16) for c in rows[y][16 * ax:16 * ax + 16]}
            colors.discard(layout.backdrop)
            choices = [GLYPH_PALETTE] if (ax, ay) in forced else range(4)
            fits = [i for i in choices if colors <= set(layout.palettes[i])]
            names = " ".join(f"${c:02X}" for c in sorted(colors))
            if fits:
                chosen[(ax, ay)] = fits[0]
            elif (ax, ay) in forced:
                errors.append(f"cell ({ax},{ay}) holds writer cells, so palette 0, but its colors {names} "
                              "are not all there")
            else:
                errors.append(f"cell ({ax},{ay}) colors {names} fit no palette")
    if errors:
        raise AssetError("; ".join(errors[:8]) + (f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""))
    return chosen


def glyph_patterns(art, layout):
    """Glyph tile id -> pattern, from the four glyph sheets drawn in palette 0."""
    p0 = layout.palettes[GLYPH_PALETTE]
    sheets = {}
    for name, size in GLYPH_SHEETS.items():
        _, _, sheets[name] = menu.load_png(art / f"out/sprites/{name}.png", sorted({layout.backdrop, *p0}),
                                           opaque=True, size=size)
    if any(c != layout.backdrop for line in sheets["head"] for c in line[80:88]):
        raise AssetError("head: the header blank after 9 must be backdrop, like the board it fills")

    def tile(name, x, y, where):
        pixels = [line[x:x + 8] for line in sheets[name][y:y + 8]]
        return menu.encode(menu.to_values(pixels, p0, layout.backdrop, where))
    out = {SEPARATOR: tile("sep", 0, 0, "separator")}
    for v in range(11):
        for q, t in enumerate(big(v)):
            out[t] = tile("big", 16 * v + 8 * (q & 1), 8 * (q >> 1), f"big glyph {v}")
        for h, t in enumerate(narrow(v)):
            out[t] = tile("narrow", 8 * v, 8 * h, f"narrow glyph {v}")
    for i, ch in enumerate(HEAD_ORDER):
        out[HEADER[ch]] = tile("head", 8 * i, 0, f"header glyph {ch!r}")
    assert set(out) == set(GLYPHS)
    return out


def check_rom(rom):
    if menu.sha256(rom) != BASE_SHA256:
        raise AssetError("--rom must be the pinned modeart32 input, the font the art is lettered in")


def convert(rom, art=ART):
    """The ScoreAssets of the art directory `art`, its menu text in the CHR $00 font of `rom`."""
    art = Path(art)
    check_rom(rom)
    missing = [name for name in SOURCES if not (art / name).is_file()]
    if missing:
        raise AssetError(f"the art directory {art} lacks {', '.join(missing)}")
    layout = read_layout(art / "layout.json")
    allowed = sorted({layout.backdrop} | {c for p in layout.palettes for c in p})
    _, _, rows = menu.load_png(art / SCENE, allowed, opaque=True, size=(256, 240))
    reserved = GEOMETRY.writer_cells() | GEOMETRY.name_cells()
    painted = [cell for cell in sorted(reserved) if not blank(rows, *cell, layout.backdrop)]
    if painted:
        raise AssetError(f"the art paints {len(painted)} writer or name cells, first ({painted[0][0]},{painted[0][1]})")
    rom_font = menu.font_patterns(rom)
    for text in layout.text:
        stamp(rows, rom_font, text, layout.backdrop, reserved)
    chosen = cell_palettes(rows, layout)
    glyphs = glyph_patterns(art, layout)
    lookup = {}
    for t in sorted(glyphs, key=lambda t: (t != BLANK, t)):
        lookup.setdefault(glyphs[t], t)
    cells = [menu.encode(menu.to_values(menu.tile_pixels(rows, tx, ty), layout.palettes[chosen[(tx // 2, ty // 2)]],
                                        layout.backdrop, f"tile ({tx},{ty})")) for ty in range(30) for tx in range(32)]
    new = list(dict.fromkeys(p for p in cells if p not in lookup))
    free = [t for t in range(256) if t not in glyphs]
    if len(new) > len(free):
        raise AssetError(f"CHR $05 is full: the art needs {len(new)} tiles beside the {len(glyphs)} glyphs, "
                         f"{len(free)} are free")
    patterns = dict(glyphs)
    for t, pattern in zip(free, new):
        patterns[t] = pattern
        lookup[pattern] = t
    attributes = bytearray(64)
    for (ax, ay), p in chosen.items():
        offset, shift = menu.attr_slot(2 * ax, 2 * ay)
        attributes[offset] |= p << shift
    return ScoreAssets(
        tiles_used=len(patterns),
        sources=tuple((name, menu.sha256((art / name).read_bytes())) for name in SOURCES),
        chr=b"".join(patterns.get(t, bytes(16)) for t in range(256)),
        nametable=bytes(lookup[p] for p in cells),
        attributes=bytes(attributes),
        palette=bytes(c for p in layout.palettes + layout.sprite_palettes for c in (layout.backdrop, *p)),
    )


def preview(assets):
    """The bare background beside the background with PREVIEW_BOARD drawn by the stock rules."""
    board = bytearray(assets.nametable)
    for (col, row), tile in drawn(PREVIEW_BOARD).items():
        board[32 * row + col] = tile
    image = Image.new("RGB", (512, 240))
    for i, nametable in enumerate((assets.nametable, bytes(board))):
        image.paste(menu.render(assets.chr, nametable, assets.attributes, assets.palette), (256 * i, 0))
    return image

# ---------------------------------------------------------------- pxl


def read_lock(art):
    lock = json.loads((Path(art) / "PXL.json").read_text())
    if (not isinstance(lock, dict) or not isinstance(lock.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]) or not isinstance(lock.get("node_min"), list)
            or len(lock["node_min"]) != 3 or not all(isinstance(v, int) for v in lock["node_min"])):
        raise AssetError("PXL.json must pin a 40-digit pxl commit and node_min [major, minor, patch]")
    return lock


def render(pxl, art, destination):
    """Render the art's score32.px.js with the pinned pxl checkout into `destination`; the PNG paths."""
    art = Path(art)
    lock = read_lock(art)
    if menu.node_version() < tuple(lock["node_min"]):
        raise AssetError(f"pxl needs Node >= {'.'.join(map(str, lock['node_min']))}")
    head = subprocess.run(["git", "-C", str(pxl), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != lock["commit"]:
        raise AssetError(f"pxl checkout is at {head}, not the pinned {lock['commit']}")
    subprocess.run(["node", str(Path(pxl).resolve() / "bin/pxl.js"), "build", str((art / "score32.px.js").resolve()),
                    "--out", str(destination), "--no-preview"], check=True, capture_output=True, text=True)
    return sorted(path.relative_to(destination) for path in Path(destination).rglob("*.png"))


def install_pngs(staging, destination, rom, art=ART, outputs=()):
    """Replace the PNGs under `destination` with those under `staging`, only after every destination passes:
    no input, source, asset or explicit output, however linked, and no other protected file may be one, but
    a destination may replace the art file at its own path. Each copy lands through a sibling temporary
    file, so a linked inode is never written."""
    art = Path(art)
    rendered = sorted(path.relative_to(staging) for path in Path(staging).rglob("*.png"))
    targets = [Path(destination) / relative for relative in rendered]
    protected = [rom, art / "score32.px.js", art / "layout.json", art / "PXL.json", ASSETS, *outputs]
    replaceable = [*protected_paths(rom, art), *targets]
    for target in targets:
        protect_earlier_output(rom, target)
        refuse_aliases(target, [*protected,
                               *(path for path in replaceable if Path(path).absolute() != target.absolute())],
                       PROTECTED_SHA256 | {menu.sha256(Path(rom).read_bytes())})
    for relative, target in zip(rendered, targets):
        write_atomic(target, (Path(staging) / relative).read_bytes())
    return rendered


def regenerate(pxl, rom, art=ART, outputs=()):
    """Render with pinned pxl and install the PNGs into the art's out/."""
    with tempfile.TemporaryDirectory() as temporary:
        render(pxl, art, temporary)
        return install_pngs(temporary, Path(art) / "out", rom, art, outputs)


def check_pxl(pxl, art=ART):
    """Two pinned renders match each other byte for byte and every PNG under the art's out/ pixel for pixel."""
    art = Path(art)
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        rendered = render(pxl, art, first)
        if render(pxl, art, second) != rendered or any(
                (Path(first) / p).read_bytes() != (Path(second) / p).read_bytes() for p in rendered):
            raise AssetError("two pxl renders of the same source differ")
        committed = sorted(path.relative_to(art / "out") for path in (art / "out").rglob("*.png"))
        if rendered != committed:
            raise AssetError(f"the pxl render and {art / 'out'} hold different PNG files")
        for relative in rendered:
            ours = Image.open(art / "out" / relative).convert("RGBA")
            again = Image.open(Path(first) / relative).convert("RGBA")
            if ours.size != again.size or ours.tobytes() != again.tobytes():
                raise AssetError(f"{relative} differs from the pinned pxl render")
    return len(rendered)

# ---------------------------------------------------------------- outputs


def protect_output(rom, output, art=ART):
    """What the stage builder refuses to overwrite, except the canonical JSON entry itself, plus anything inside
    the art directory. A link or alias resolving the canonical path onto another protected file stays refused."""
    rom, output = Path(rom), Path(output)
    protect_earlier_output(rom, output)
    protected = [path for path in protected_paths(rom, art) if path != ASSETS]
    source = menu.sha256(rom.read_bytes()) if rom.is_file() else None
    refuse_aliases(output, protected, PROTECTED_SHA256 | ({source} if source else set()))
    refuse_inside(output, art)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", type=Path, required=True, help="pinned modeart32 ROM: the CHR $00 font")
    ap.add_argument("--art", type=Path, default=ART, help="art directory (default %(default)s)")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout")
    ap.add_argument("-o", "--out", type=Path, default=ASSETS)
    ap.add_argument("--check", action="store_true", help="write nothing; fail unless everything is current")
    ap.add_argument("--preview", type=Path, help="write a preview PNG of the background and a sample board")
    args = ap.parse_args()
    if args.check and args.preview:
        ap.error("--check writes nothing; drop --preview")
    try:
        protect_output(args.rom, args.out, args.art)
        if args.preview:
            protect_output(args.rom, args.preview, args.art)
            refuse_aliases(args.preview, [ASSETS, args.out], set())
        rom = args.rom.read_bytes()
        check_rom(rom)
        checked = 0
        if args.pxl and args.check:
            checked = check_pxl(args.pxl, args.art)
        elif args.pxl:
            regenerate(args.pxl, args.rom, args.art, [args.out] + ([args.preview] if args.preview else []))
        assets = convert(rom, args.art)
        text = assets.dumps()
        if args.check:
            if not args.out.is_file() or args.out.read_text() != text:
                raise AssetError(f"{args.out} is stale; rerun without --check")
        else:
            image = preview(assets) if args.preview else None
            write_atomic(args.out, text.encode())
            if image:
                encoded = io.BytesIO()
                image.save(encoded, format="PNG")
                write_atomic(args.preview, encoded.getvalue())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"scoreart32_convert: {exc}\n")
    print(f"{'checked' if args.check else 'wrote'} {args.out}: {assets.tiles_used} tiles used "
          f"({assets.tiles_used - len(GLYPHS)} art, {len(GLYPHS)} glyphs), {256 - assets.tiles_used} free, "
          f"sha256 {menu.sha256(text.encode())}" + (f"; pinned pxl reproduces {checked} PNGs twice" if checked else ""))


if __name__ == "__main__":
    main()
