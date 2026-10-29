#!/usr/bin/env python3
"""Convert the pxl mode-menu art into data/modeart32/modeassets.json.

    .venv/bin/python tools/modeart32_convert.py --rom build/title32.nes
    .venv/bin/python tools/modeart32_convert.py --rom build/title32.nes --check [--pxl build/vendor/claude-pxl]
    .venv/bin/python tools/modeart32_convert.py --rom build/title32.nes --pxl build/vendor/claude-pxl
    .venv/bin/python tools/modeart32_convert.py --rom build/title32.nes --preview build/modeart32-preview.png

--pxl renders art/modeart32/mode32.px.js with the pinned pxl checkout named in
art/modeart32/PXL.json (commit and minimum Node version). With --check it only
verifies that the render reproduces every committed PNG in art/modeart32/out
pixel for pixel and that --out already holds this output. Without --check it
refreshes those PNGs first. Without --pxl the committed PNGs are converted as
they are. --check writes nothing.

The art is one 256x240 background, out/scenes/mode.png, shared by the main,
Championship and Exhibition menus. art/modeart32/layout.json places the text:

  backdrop, palettes, sprite_palettes   NES colors; the font draws with color 2
  static_text    [{row, col, text, palette}] drawn once with the background
  menus          {main, championship, exhibition}: items, three {row, col, text}
                 with the stock labels in stock order, and optional per-menu
                 text [{row, col, text, palette}]
  item_palette   palette of every item
  cursor         {dx, dy}: the ball's (x, y) is (8 * col + dx, 8 * row + dy)
                 of its item

On each text row the menus' text spans the union of their columns. The art
must leave that union blank and the row keeps one palette in every menu.
Championship items start where the main items do, because the stock cursor
table serves both from the same entries. tools/menu32_convert.py's Screen and
TileBank, imported unchanged, enforce exact NES colors, one palette per 16x16
attribute cell, blank art under text and the 256-tile budget of CHR bank $06.
Text uses the stock font glyphs at their ASCII ids from the --rom CHR bank $00.

--preview writes the three menus side by side, each with the stock ball
cursor from the --rom CHR bank $1B on its first item: what the PPU shows.
tools/modeart32_assets.py documents the output format, modeassets/1.
"""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image

from build_draw32 import ROOT, locate, refuse_aliases
from build_modeart32 import CURSOR_SHAPE, PROTECTED_SHA256, SPRITE_CHR, protected_paths
from build_title32 import protect_output as protect_prior_output
import menu32_convert as menu
from menu32_convert import AssetError
from modeart32_assets import (
    ASSETS, CURSOR_X_MAX, CURSOR_Y_MAX, LABELS, MENUS, MenuText, ModeAssets, Span, sha256,
)

ART = ROOT / "art/modeart32"
SOURCE = ART / "mode32.px.js"
LAYOUT = ART / "layout.json"
LOCK = ART / "PXL.json"
PNGS = ART / "out"
SCENE = PNGS / "scenes/mode.png"
LAYOUT_FORMAT = "modeart32-layout/1"
LAYOUT_KEYS = {"backdrop", "palettes", "sprite_palettes", "cursor", "menus", "item_palette", "static_text"}


@dataclass(frozen=True)
class Text:
    row: int
    col: int
    text: str
    palette: int


@dataclass(frozen=True)
class ModeArtwork:
    """layout.json, validated: screen colors, each menu's text, static text and the ball's offset."""
    colors: dict           # palettes and sprite_palettes, as menu32_convert.Screen reads them
    backdrop: int
    items: dict            # menu name -> its three stock labels, in stock order
    extra: dict            # menu name -> its optional per-menu text
    static: tuple          # text drawn once with the background
    cursor: tuple          # (dx, dy) from an item's first cell to the ball's (x, y)

    def texts(self, name):
        return self.items[name] + self.extra[name]


def integer(value, where, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise AssetError(f"{where} must be an integer from {low} to {high}")
    return value


def text_entries(entries, where, palette=None):
    """Validated Text records; `palette` fixes the palette of entries that carry none (menu items)."""
    keys = {"row", "col", "text"} | ({"palette"} if palette is None else set())
    if not isinstance(entries, list):
        raise AssetError(f"{where} must be a list")
    found = []
    for i, entry in enumerate(entries):
        label = f"{where}[{i}]"
        if not isinstance(entry, dict) or set(entry) != keys:
            raise AssetError(f"{label} must hold exactly {', '.join(sorted(keys))}")
        text = entry["text"]
        if not isinstance(text, str) or not re.fullmatch(r"[ -~]+", text) or not text.strip():
            raise AssetError(f"{label} text must be printable ASCII")
        row = integer(entry["row"], f"{label} row", 0, 29)
        col = integer(entry["col"], f"{label} col", 0, 31)
        if col + len(text) > 32:
            raise AssetError(f"{label} {text!r} runs off the right edge")
        chosen = palette if palette is not None else integer(entry["palette"], f"{label} palette", 0, 3)
        found.append(Text(row, col, text, chosen))
    return tuple(found)


def palettes(layout, key):
    value = layout[key]
    if (not isinstance(value, list) or len(value) != 4
            or not all(isinstance(p, list) and len(p) == 3 and all(isinstance(c, str) for c in p) for p in value)):
        raise AssetError(f"{key} must be four palettes of three NES color strings")
    return value


def read_layout(path):
    layout = json.loads(Path(path).read_text())
    if not isinstance(layout, dict):
        raise AssetError("the layout must be a JSON object")
    if layout.get("format", LAYOUT_FORMAT) != LAYOUT_FORMAT:
        raise AssetError(f"unknown layout format; expected {LAYOUT_FORMAT}")
    keys = set(layout) - {"format"}
    if keys != LAYOUT_KEYS:
        raise AssetError(f"layout keys must be {', '.join(sorted(LAYOUT_KEYS))} (and optionally format); "
                         f"missing {sorted(LAYOUT_KEYS - keys)}, unknown {sorted(keys - LAYOUT_KEYS)}")
    palettes(layout, "palettes")
    palettes(layout, "sprite_palettes")
    if not isinstance(layout["backdrop"], str):
        raise AssetError("backdrop must be an NES color string")
    cursor = layout["cursor"]
    if not isinstance(cursor, dict) or set(cursor) != {"dx", "dy"}:
        raise AssetError("cursor must hold exactly dx and dy")
    integer(cursor["dx"], "cursor dx", -255, 255)
    integer(cursor["dy"], "cursor dy", -255, 255)
    item_palette = integer(layout["item_palette"], "item_palette", 0, 3)
    menus = layout["menus"]
    if not isinstance(menus, dict) or set(menus) != set(MENUS):
        raise AssetError(f"menus must hold exactly {', '.join(MENUS)}")
    items, extra = {}, {}
    for name in MENUS:
        spec = menus[name]
        if not isinstance(spec, dict) or not {"items"} <= set(spec) <= {"items", "text"}:
            raise AssetError(f"menus.{name} must hold items and optionally text")
        items[name] = tuple(text_entries(spec["items"], f"menus.{name}.items", item_palette))
        if tuple(t.text for t in items[name]) != LABELS[name]:
            raise AssetError(f"menus.{name}.items must be {', '.join(map(repr, LABELS[name]))}, in that order")
        extra[name] = tuple(text_entries(spec.get("text", []), f"menus.{name}.text"))
    if [(t.col, t.row) for t in items["championship"]] != [(t.col, t.row) for t in items["main"]]:
        raise AssetError("championship items must start where the main items start: the stock cursor table "
                         "serves the main menu and Championship from the same entries")
    return ModeArtwork(
        colors={"palettes": layout["palettes"], "sprite_palettes": layout["sprite_palettes"]},
        backdrop=menu.nes_color(layout["backdrop"]),
        items=items,
        extra=extra,
        static=text_entries(layout["static_text"], "static_text"),
        cursor=(cursor["dx"], cursor["dy"]),
    )


def union_spans(art):
    """One span per text row, the union of every menu's text there, and that row's palette."""
    rows = {}
    for name in MENUS:
        for t in art.texts(name):
            low, high, palette = rows.get(t.row, (t.col, t.col + len(t.text), t.palette))
            if palette != t.palette:
                raise AssetError(f"row {t.row}: the menus' text needs one palette, not P{palette} and P{t.palette}")
            rows[t.row] = (min(low, t.col), max(high, t.col + len(t.text)), palette)
    return [(Span(row, low, high - low), palette) for row, (low, high, palette) in sorted(rows.items())]


def cursor_table(art):
    dx, dy = art.cursor
    table = bytearray()
    for item in art.items["main"] + art.items["exhibition"] + art.items["main"]:
        x, y = 8 * item.col + dx, 8 * item.row + dy
        if not (0 <= x <= CURSOR_X_MAX and 0 <= y <= CURSOR_Y_MAX):
            raise AssetError(f"the cursor for {item.text!r} lands at ({x}, {y}), off screen")
        table += bytes((x, y))
    return bytes(table)


def convert(rom, layout_path=LAYOUT, scene=SCENE):
    art = read_layout(layout_path)
    screen = menu.Screen("mode", art.colors, art.backdrop)
    spans = union_spans(art)
    for span, palette in spans:
        screen.reserve(span.col, span.row, span.width, f"menu text row {span.row}", palette)
    for t in art.static:
        screen.reserve(t.col, t.row, len(t.text), f"text {t.text!r}", t.palette)
    glyphs = {menu.BLANK}
    for t in art.static + tuple(t for name in MENUS for t in art.texts(name)):
        glyphs |= menu.text_glyphs(t.text)
    bank = menu.TileBank(menu.font_patterns(rom), glyphs)
    allowed = {art.backdrop} | {color for palette in screen.palettes for color in palette}
    _, _, rows = menu.load_png(Path(scene), sorted(allowed), opaque=True, size=(256, 240))
    screen.convert(rows, bank)
    for t in art.static:
        screen.nametable[t.row][t.col:t.col + len(t.text)] = list(t.text.encode())
    drawn = {}
    for name in MENUS:
        cells = bytearray(screen.nametable_bytes())
        for t in art.texts(name):
            cells[32 * t.row + t.col:32 * t.row + t.col + len(t.text)] = t.text.encode()
        drawn[name] = bytes(cells)
    return ModeAssets(
        tiles_used=len(bank.patterns),
        font_glyphs=tuple(bank.font),
        png_sha256=sha256(Path(scene).read_bytes()),
        chr=bank.chr(),
        nametable=drawn["main"],
        attributes=screen.attributes(),
        palette=screen.palette_rgb(),
        spans=tuple(span for span, _ in spans),
        menus=tuple(MenuText(name, tuple(drawn[name][span.cells] for span, _ in spans)) for name in MENUS),
        cursor=cursor_table(art),
    )


def cursor_sprites(rom, x, y):
    """The four OAM entries (y, tile, attr, x) the stock $9586 writes for a ball at (x, y)."""
    shape = rom[locate(1, CURSOR_SHAPE):locate(1, CURSOR_SHAPE) + 16]
    return [(shape[i] + y, shape[i + 1], shape[i + 2], shape[i + 3] + x) for i in range(0, 16, 4)]


def compose(bg_chr, sprite_chr, screen, palette, oam):
    """One frame as the PPU composes it: background from `bg_chr`, 8x8 sprites from `sprite_chr`."""
    image = menu.render(bg_chr, screen[:960], screen[960:], palette)
    pixels = image.load()
    for y, tile, attr, x in reversed(list(oam)):
        if y >= 0xEF:
            continue
        grid = menu.decode(sprite_chr[16 * tile:16 * tile + 16])
        for yy in range(8):
            for xx in range(8):
                value = grid[7 - yy if attr & 0x80 else yy][7 - xx if attr & 0x40 else xx]
                sx, sy = x + xx, y + 1 + yy
                if value and sx < 256 and sy < 240:
                    pixels[sx, sy] = menu.NES_RGB[palette[16 + 4 * (attr & 3) + value]]
    return image


def frame(assets, rom, name, entry):
    """The screen while `name` shows with the ball on cursor table entry `entry`."""
    sprites = rom[locate("chr", SPRITE_CHR * 0x1000):locate("chr", SPRITE_CHR * 0x1000 + 0x1000)]
    return compose(assets.chr, sprites, assets.screen(name), assets.palette,
                   cursor_sprites(rom, *assets.cursor_origin(entry)))


def preview(assets, rom):
    """Main, Championship and Exhibition side by side, each with the ball on its first item."""
    image = Image.new("RGB", (3 * 256, 240))
    for i, (name, entry) in enumerate((("main", 0), ("championship", 0), ("exhibition", 3))):
        image.paste(frame(assets, rom, name, entry), (256 * i, 0))
    return image


def committed_pngs():
    return sorted(path.relative_to(PNGS) for path in PNGS.rglob("*.png"))


def install_pngs(staging, destination, rom, outputs=()):
    rendered = sorted(path.relative_to(staging) for path in Path(staging).rglob("*.png"))
    targets = [Path(destination) / relative for relative in rendered]
    protected = [rom, SOURCE, LAYOUT, LOCK, ASSETS, *outputs]
    replaceable = [*protected_paths(rom), *targets]
    for target in targets:
        protect_prior_output(rom, target)
        refuse_aliases(target, [*protected,
                               *(path for path in replaceable if Path(path).absolute() != target.absolute())],
                       PROTECTED_SHA256 | {sha256(Path(rom).read_bytes())})
    for relative, target in zip(rendered, targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
            pending = Path(staged.name)
        try:
            shutil.copyfile(Path(staging) / relative, pending)
            os.replace(pending, target)
        finally:
            pending.unlink(missing_ok=True)
    return rendered


def render_pxl(pxl, destination, rom, outputs=()):
    """Render the art with the pinned pxl checkout into `destination`; the relative PNG paths."""
    lock = json.loads(LOCK.read_text())
    if menu.node_version() < tuple(lock["node_min"]):
        raise AssetError(f"pxl needs Node >= {'.'.join(map(str, lock['node_min']))}")
    head = subprocess.run(["git", "-C", str(pxl), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != lock["commit"]:
        raise AssetError(f"pxl checkout is at {head}, not the pinned {lock['commit']}")
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(["node", str(Path(pxl).resolve() / "bin/pxl.js"), "build", str(SOURCE), "--out", temporary,
                        "--no-preview"], check=True, capture_output=True, text=True)
        rendered = install_pngs(temporary, destination, rom, outputs)
    return rendered


def check_pxl(pxl, rom):
    """The pinned render reproduces every committed PNG pixel for pixel."""
    with tempfile.TemporaryDirectory() as temporary:
        rendered = render_pxl(pxl, temporary, rom)
        if rendered != committed_pngs():
            raise AssetError("the pxl render and art/modeart32/out hold different PNG files")
        for relative in rendered:
            ours = Image.open(PNGS / relative).convert("RGBA")
            again = Image.open(Path(temporary) / relative).convert("RGBA")
            if ours.size != again.size or ours.tobytes() != again.tobytes():
                raise AssetError(f"{relative} differs from the pinned pxl render")
    return len(rendered)


def protect_output(rom, output):
    """What the stage builder refuses to overwrite, except the canonical JSON entry itself. A link or
    alias that resolves the canonical path onto another protected file stays refused."""
    rom, output = Path(rom), Path(output)
    protect_prior_output(rom, output)
    protected = [path for path in protected_paths(rom) if path != ASSETS]
    source = sha256(rom.read_bytes()) if rom.is_file() else None
    refuse_aliases(output, protected, PROTECTED_SHA256 | ({source} if source else set()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", type=Path, required=True, help="title32 ROM: CHR $00 font, CHR $1B ball and its shape")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout")
    ap.add_argument("-o", "--out", type=Path, default=ASSETS)
    ap.add_argument("--check", action="store_true", help="write nothing; fail unless everything is current")
    ap.add_argument("--preview", type=Path, help="write an NES-exact preview PNG of the three menus")
    args = ap.parse_args()
    if args.check and args.preview:
        ap.error("--check writes nothing; drop --preview")
    try:
        protect_output(args.rom, args.out)
        if args.preview:
            protect_output(args.rom, args.preview)
            refuse_aliases(args.preview, [ASSETS, args.out], set())
        rom = args.rom.read_bytes()
        checked = 0
        if args.pxl and args.check:
            checked = check_pxl(args.pxl, args.rom)
        elif args.pxl:
            render_pxl(args.pxl, PNGS, args.rom, [args.out] + ([args.preview] if args.preview else []))
        assets = convert(rom)
        text = assets.dumps()
        if args.check:
            if not args.out.is_file() or args.out.read_text() != text:
                raise AssetError(f"{args.out} is stale; rerun without --check")
        else:
            image = preview(assets, rom) if args.preview else None
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text)
            if image:
                image.save(args.preview, format="PNG")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"modeart32_convert: {exc}\n")
    print(f"{'checked' if args.check else 'wrote'} {args.out}: {assets.tiles_used} tiles used, "
          f"{256 - assets.tiles_used} free, {len(assets.spans)} text rows, sha256 {sha256(text.encode())}"
          + (f"; pinned pxl reproduces {checked} PNGs" if checked else ""))


if __name__ == "__main__":
    main()
