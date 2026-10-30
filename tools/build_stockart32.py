#!/usr/bin/env python3
"""Draw the stock-character mode menu and scoreboard on the pinned scoreart32 ROM.

    .venv/bin/python -B tools/build_stockart32.py build/scoreart32.nes -o build/stockart32.nes
    .venv/bin/python -B tools/build_stockart32.py build/scoreart32.nes --assets DIR -o OUT --manifest

--assets names the directory tools/stockart32_convert.py fills (default build/stockart32). Its
modeassets.json and scoreassets.json must carry the digests data/stockart32/digests.json records, and
so must the built ROM, before anything is written.

The stage replaces data the modeart32 and scoreart32 stages own and keeps all of their code:

  bank 13 $9000-$93FF  mode nametable and attributes   bank 4 $B880-$B89F  scoreboard palette
  bank 13 $9400-$941F  mode palette                    bank 4 $B900-$BCFF  scoreboard nametable and attributes
  CHR $06              mode background tiles           CHR $05             scoreboard tiles and glyphs

Each region names the SHA-256 of the accepted bytes it replaces. The draw code, the scoreboard's
41,436-cycle timing pad, the menu run lists and cursor table, the writer row tables, the fixed bank
and the shared fonts are pinned by digest. The mode art must reproduce the accepted run lists, cursor
table and text cells with the CHR $00 font glyphs, and the scoreboard art all 78 glyph tiles. In the
palettes only the background skin slots change: byte 11 of both and byte 15 of the mode palette become
$36; palette 0, which draws the text and glyphs, and both sprite halves stay as they are. The stock
writers, text engine, cursor and timing therefore read the same values, and the 1 KB screen copies
cost the same cycles whatever they hold.
"""
import argparse
import json
import os
from pathlib import Path

from build_draw32 import (
    ROOT, Region, apply_changes, check_guards, claim, locate, manifest_ranges, read, refuse_aliases, sha256,
)
from build_modeart32 import check_font, far_block
import build_scoreart32 as score_stage
from build_teamnames32 import HEADER, ROM_SIZE
import menu32_convert as menu
from modeart32_assets import ModeAssets
from scoreart32_assets import GLYPHS, ScoreAssets

BASE_SHA256 = "2ae1a7ab2f75aeea4287943ba8153ab0ee0cc188a3d9a67f64bf7398f9e3360a"   # accepted scoreart32
PROTECTED_SHA256 = score_stage.PROTECTED_SHA256 | {BASE_SHA256}
BUILD = ROOT / "build"
ASSETS = BUILD / "stockart32"
OUTPUT = BUILD / "stockart32.nes"
REGISTRY = ROOT / "data/stockart32/digests.json"
REGISTRY_FORMAT = "stockart32-digests/1"
MODE_JSON, SCORE_JSON = "modeassets.json", "scoreassets.json"
MODE_BANK, SCORE_BANK, CURSOR_BANK = 13, 4, 1
CURSOR_TABLE = 0x95E4

REGIONS = (
    Region("mode-screen", MODE_BANK, 0x9000, 0x9400),
    Region("mode-palette", MODE_BANK, 0x9400, 0x9420),
    Region("mode-chr", "chr", 0x6000, 0x7000),
    Region("score-palette", SCORE_BANK, 0xB880, 0xB8A0),
    Region("score-screen", SCORE_BANK, 0xB900, 0xBD00),
    Region("score-chr", "chr", 0x5000, 0x6000),
)
ACCEPTED = {
    "mode-screen": "84ac81711d13f23893fab99fc6b2e9b8485e3cee6011d2b081e806bf13bce685",
    "mode-palette": "7f0d9f28ed9ea738dbb68f1a201b300195dd15a1c00aa49fddd11579194808fe",
    "mode-chr": "4fffe7f6a23b4def6ebef27f9da8c9b41cfcaa54a7ef275bbb1e3af8943d0913",
    "score-palette": "df96c40bfcd799b8733df4b6b770a6f056eddf98e61aefadf71217c6cd42a5c7",
    "score-screen": "0b374bf21c47b32d384c877f624e33a814f0be17ffa40ea039987abb80f21989",
    "score-chr": "958854c1906be527aac9de00b3cd7ddb5a3933cc5d401674bbd177037e0521c8",
}
PALETTE_EDITS = {"mode-palette": {11: 0x36, 15: 0x36}, "score-palette": {11: 0x36}}
DIGESTS = (
    ("bank 13 hop pad, draw, request code and run lists $9420-$9FFF", MODE_BANK, 0x9420, 0xBE0,
     "f814ec4e9165aa5061068972d7d9839a6dec6d76ebe29d8f94202fd95278f1ab"),
    ("bank 1 mode program, draw stub and cursor table $9400-$96A8", CURSOR_BANK, 0x9400, 0x2A9,
     "53fa6c72fdd8ac144ee5df7f4af53f361af8f1700bb92881b743b03f8bec833f"),
    ("bank 4 scoreboard draw and timing pad $B800-$B87F", SCORE_BANK, 0xB800, 0x80,
     "215d75214c657a2d504415127e45ef79ce0d8d027ec569ebad487a0c2c8c3f2b"),
    ("bank 4 scoreboard program and row tables $B39D-$B6F6", SCORE_BANK, 0xB39D, 0x35A,
     "e4084f88a6bce8aa668b60b2df355ba065caa93160fa4af24843268094810600"),
    ("fixed bank $C000-$FFFF", 15, 0xC000, 0x4000, "c38587dc7ee5601a742bf1da30453fc06b303946a39d4d6d398128ac4c5aabb9"),
    ("CHR $00 font", "chr", 0x0000, 0x1000, "771012bc129730fbef4c9bd840bf68f91329d625bfde1f75c0a5940400d2ea32"),
    ("CHR $18 name font", "chr", 0x18000, 0x1000, "8a058223e5f2c3ab5579395148463c000a5ac93d4eed6f014ba1507dbf56e769"),
    ("CHR $1B sprites and ball", "chr", 0x1B000, 0x1000,
     "330afeaa1a18c62cbb0fe1bd39101da67efac96812a43109449737dc1301b5bb"),
)


def text_cells(nametable, glyphs):
    """Cell -> font glyph for every lettered cell; art never takes a font id other than the blank."""
    return {i: t for i, t in enumerate(nametable) if t in glyphs and t != menu.BLANK}


def check_runtime(base, mode, score):
    """The new art keeps every value the stock text engine, cursor and score writer depend on."""
    if far_block(mode)[0x420:] != read(base, MODE_BANK, 0x9420, 0xBE0):
        raise ValueError("the mode art must reproduce the accepted run lists and bank-13 code exactly")
    if mode.cursor != read(base, CURSOR_BANK, CURSOR_TABLE, 18):
        raise ValueError("the mode art must keep the accepted cursor table")
    check_font(base, mode)
    accepted = read(base, MODE_BANK, 0x9000, 960)
    if text_cells(mode.nametable, mode.font_glyphs) != text_cells(accepted, mode.font_glyphs):
        raise ValueError("the mode art must letter exactly the accepted text cells")
    stock = read(base, "chr", 0x5000, 0x1000)
    moved = [t for t in GLYPHS if score.chr[16 * t:16 * t + 16] != stock[16 * t:16 * t + 16]]
    if moved:
        raise ValueError(f"scoreboard glyph tiles changed: {' '.join(f'${t:02X}' for t in moved[:8])}")
    region = {r.name: r for r in REGIONS}
    for name, palette in (("mode-palette", mode.palette), ("score-palette", score.palette)):
        r = region[name]
        expected = bytearray(read(base, r.bank, r.start, 32))
        for index, value in PALETTE_EDITS[name].items():
            expected[index] = value
        wrong = [i for i in range(32) if palette[i] != expected[i]]
        if wrong:
            raise ValueError(f"{name} bytes {', '.join(map(str, wrong))} differ: only the background skin slots "
                             f"{', '.join(map(str, PALETTE_EDITS[name]))} become $36; palette 0 and the sprite "
                             "palettes stay stock")


def change_manifest(base, mode, score):
    check_guards(base, (), DIGESTS)
    check_runtime(base, mode, score)
    region = {r.name: r for r in REGIONS}
    data = {"mode-screen": mode.nametable + mode.attributes, "mode-palette": mode.palette, "mode-chr": mode.chr,
            "score-palette": score.palette, "score-screen": score.screen(), "score-chr": score.chr}
    return tuple(claim(base, region[r.name], data[r.name], ACCEPTED[r.name]) for r in REGIONS)


def check_output(base, rom):
    """Whole-ROM postconditions: same size, and no byte changed outside the stockart32 regions."""
    if len(rom) != len(base):
        raise ValueError("the built ROM changed size")
    owned = set()
    for r in REGIONS:
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end - 1) + 1))
    if any(a != b and i not in owned for i, (a, b) in enumerate(zip(base, rom))):
        raise ValueError("a byte changed outside the stockart32 regions")


def build_rom(base, mode, score):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected scoreart32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned scoreart32")
    rom = apply_changes(base, change_manifest(base, mode, score), REGIONS)
    check_output(base, rom)
    return rom


def diff_manifest(base, rom, mode, score):
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "mode_assets_sha256": sha256(mode.dumps().encode()), "score_assets_sha256": sha256(score.dumps().encode()),
            "ranges": manifest_ranges(change_manifest(base, mode, score))}



def read_registry(path=REGISTRY):
    registry = json.loads(Path(path).read_text())
    if (not isinstance(registry, dict) or registry.get("format") != REGISTRY_FORMAT
            or not isinstance(registry.get("outputs"), dict) or not isinstance(registry.get("rom"), str)):
        raise ValueError(f"{path} is not a {REGISTRY_FORMAT} registry")
    return registry


def load_assets(directory, registry):
    """The two asset files tools/stockart32_convert.py wrote, each matching its registered digest."""
    loaded = []
    for name, kind in ((MODE_JSON, ModeAssets), (SCORE_JSON, ScoreAssets)):
        data = (Path(directory) / name).read_bytes()
        if sha256(data) != registry["outputs"].get(name):
            raise ValueError(f"{Path(directory) / name} differs from data/stockart32/digests.json; regenerate it "
                             "with tools/stockart32_convert.py")
        loaded.append(kind.parse(json.loads(data)))
    return tuple(loaded)


def protected_paths(source, inputs=()):
    """Files no stockart32 tool may overwrite: its inputs, every earlier stage's ROMs, assets and art, and
    every file under tools, docs, art and data."""
    source = Path(source)
    return [ROOT / "build/scoreart32.nes", source.resolve().parent / "scoreart32.nes", source.resolve(), *inputs,
            *score_stage.protected_paths(source), *(ROOT / "art").rglob("*"), *(ROOT / "data").rglob("*")]


def refuse_tracked(output):
    """Inside the repository a generated file belongs under build/, even one that does not exist yet."""
    if score_stage.is_inside(output, ROOT) and not score_stage.is_inside(output, BUILD):
        raise ValueError(f"output aliases protected repository path {output}; generated files belong under {BUILD}")


def protect_output(source, output, inputs=()):
    source, output = Path(source), Path(output)
    score_stage.protect_output(source, output)
    refuse_aliases(output, protected_paths(source, inputs), PROTECTED_SHA256)
    refuse_tracked(output)
    score_stage.refuse_inside(output, BUILD / "vendor")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned scoreart32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--assets", type=Path, default=ASSETS, help="stockart32_convert.py output (default %(default)s)")
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        inputs = [args.assets / MODE_JSON, args.assets / SCORE_JSON, REGISTRY]
        protect_output(args.rom, args.out, inputs)
        score_stage.refuse_inside(args.out, args.assets)
        registry = read_registry()
        mode, score = load_assets(args.assets, registry)
        base = args.rom.read_bytes()
        rom = build_rom(base, mode, score)
        if sha256(rom) != registry["rom"]:
            raise ValueError(f"the built ROM {sha256(rom)} differs from data/stockart32/digests.json")
        score_stage.write_atomic(args.out, rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom, mode, score), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed); matches data/stockart32/digests.json")


if __name__ == "__main__":
    main()
