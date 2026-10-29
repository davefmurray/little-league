#!/usr/bin/env python3
"""Convert the pxl title art into data/title32/titleassets.json.

    .venv/bin/python tools/title32_convert.py --rom build/pick32.nes
    .venv/bin/python tools/title32_convert.py --rom build/pick32.nes --check --pxl build/vendor/claude-pxl
    .venv/bin/python tools/title32_convert.py --rom build/pick32.nes --pxl build/vendor/claude-pxl

--pxl renders art/title32/title32.px.js with the pinned pxl checkout named in
art/title32/PXL.json (commit and minimum Node version). With --check it only
verifies that the render reproduces every committed PNG in art/title32/out
pixel for pixel and that --out already holds this output; without --check it
refreshes those PNGs first. Without --pxl the committed PNGs are converted as
they are.

The title is one 256x240 screen whose tiles fill CHR bank $17, which only the
stock title maps. tools/menu32_convert.py's Screen and TileBank, imported
unchanged, enforce exact NES colors, one palette per 16x16 attribute cell,
blank art under the layout's text and the 256-tile budget. Text cells use
the stock font glyphs at their ASCII ids from the --rom CHR bank $00;
tools/build_title32.py checks them against the ROM it builds.

Output, format titleassets/1, in this key order: chr_bank, tiles_used,
font_glyphs, png_sha256 of out/scenes/title.png, then hex strings of the
4 KB CHR bank, the 960-byte nametable, the 64 attribute bytes and the
32-byte palette.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image

from build_draw32 import ROOT, refuse_aliases
from build_menuart32 import protect_output as protect_rom
from build_title32 import ART, ASSETS, FORMAT, PROTECTED_SHA256, TITLE_CHR
import menu32_convert as menu

SOURCE = ART / "title32.px.js"
LAYOUT = ART / "layout.json"
LOCK = ART / "PXL.json"
PNGS = ART / "out"
SCENE = PNGS / "scenes/title.png"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def convert(rom, layout_path=LAYOUT, scene=SCENE):
    layout = json.loads(Path(layout_path).read_text())
    backdrop = menu.nes_color(layout["backdrop"])
    screen = menu.Screen("title", layout, backdrop)
    glyphs = {menu.BLANK}
    for entry in layout["text"]:
        glyphs |= menu.text_glyphs(entry["text"])
        screen.reserve(entry["col"], entry["row"], len(entry["text"]), f"text {entry['text']!r}", entry["palette"])
    bank = menu.TileBank(menu.font_patterns(rom), glyphs)
    allowed = {backdrop} | {color for palette in screen.palettes for color in palette}
    _, _, rows = menu.load_png(Path(scene), sorted(allowed), opaque=True, size=(256, 240))
    screen.convert(rows, bank)
    for entry in layout["text"]:
        for i, char in enumerate(entry["text"]):
            screen.nametable[entry["row"]][entry["col"] + i] = ord(char)
    return {
        "format": FORMAT,
        "chr_bank": TITLE_CHR,
        "tiles_used": len(bank.patterns),
        "font_glyphs": bank.font,
        "png_sha256": sha256(Path(scene).read_bytes()),
        "chr": bank.chr().hex(),
        "nametable": screen.nametable_bytes().hex(),
        "attributes": screen.attributes().hex(),
        "palette": screen.palette_rgb().hex(),
    }


def dumps(assets):
    return json.dumps(assets, indent=1) + "\n"


def committed_pngs():
    return sorted(path.relative_to(PNGS) for path in PNGS.rglob("*.png"))


def render_pxl(pxl, destination):
    """Render the art with the pinned pxl checkout into `destination`; the relative PNG paths."""
    lock = json.loads(LOCK.read_text())
    if menu.node_version() < tuple(lock["node_min"]):
        raise menu.AssetError(f"pxl needs Node >= {'.'.join(map(str, lock['node_min']))}")
    head = subprocess.run(["git", "-C", str(pxl), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != lock["commit"]:
        raise menu.AssetError(f"pxl checkout is at {head}, not the pinned {lock['commit']}")
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(["node", str(Path(pxl) / "bin/pxl.js"), "build", str(SOURCE), "--out", temporary,
                        "--no-preview"], check=True, capture_output=True, text=True)
        rendered = sorted(path.relative_to(temporary) for path in Path(temporary).rglob("*.png"))
        for relative in rendered:
            target = Path(destination) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(temporary) / relative, target)
    return rendered


def check_pxl(pxl):
    """The pinned render reproduces every committed PNG pixel for pixel."""
    with tempfile.TemporaryDirectory() as temporary:
        rendered = render_pxl(pxl, temporary)
        if rendered != committed_pngs():
            raise menu.AssetError("the pxl render and art/title32/out hold different PNG files")
        for relative in rendered:
            ours = Image.open(PNGS / relative).convert("RGBA")
            again = Image.open(Path(temporary) / relative).convert("RGBA")
            if ours.size != again.size or ours.tobytes() != again.tobytes():
                raise menu.AssetError(f"{relative} differs from the pinned pxl render")
    return len(rendered)


def preview(assets):
    return menu.render(bytes.fromhex(assets["chr"]), bytes.fromhex(assets["nametable"]),
                       bytes.fromhex(assets["attributes"]), bytes.fromhex(assets["palette"]))


def protect_output(rom, output):
    rom, output = Path(rom), Path(output)
    protect_rom(rom, output)
    protected = [rom, ROOT / "tools/verify.sh", *ART.rglob("*"), *(path for path in (ROOT / "data").rglob("*") if path != ASSETS)]
    source = sha256(rom.read_bytes()) if rom.is_file() else None
    refuse_aliases(output, protected, PROTECTED_SHA256 | ({source} if source else set()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", type=Path, required=True, help="ROM whose CHR $00 font the title text uses")
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout")
    ap.add_argument("-o", "--out", type=Path, default=ASSETS)
    ap.add_argument("--check", action="store_true", help="change nothing; fail unless everything is current")
    ap.add_argument("--preview", type=Path, help="write an NES-exact preview PNG of the converted title")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        if args.preview:
            protect_output(args.rom, args.preview)
            refuse_aliases(args.preview, [ASSETS, args.out], set())
        rom = args.rom.read_bytes()
        checked = 0
        if args.pxl and args.check:
            checked = check_pxl(args.pxl)
        elif args.pxl:
            render_pxl(args.pxl, PNGS)
        assets = convert(rom)
        text = dumps(assets)
        if args.check:
            if not args.out.is_file() or args.out.read_text() != text:
                raise menu.AssetError(f"{args.out} is stale; rerun without --check")
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text)
        if args.preview:
            preview(assets).save(args.preview)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        ap.exit(2, f"title32_convert: {exc}\n")
    print(f"{'checked' if args.check else 'wrote'} {args.out}: {assets['tiles_used']} tiles used, "
          f"{256 - assets['tiles_used']} free, sha256 {sha256(text.encode())}"
          + (f"; pinned pxl reproduces {checked} PNGs" if checked else ""))


if __name__ == "__main__":
    main()
