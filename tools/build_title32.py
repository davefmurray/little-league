#!/usr/bin/env python3
"""Draw the converted pxl title screen on the pinned pick32 ROM.

    .venv/bin/python tools/build_title32.py build/pick32.nes -o build/title32.nes
    .venv/bin/python tools/build_title32.py build/pick32.nes -o build/title32.nes --manifest

Only the title's drawing changes. The stock title draw at bank 0 $AC5A, which
scene 0 and attract phase 3 both call, jumps to a replacement in bank 0
padding that keeps the stock routine's contract: $2C held around the VRAM
writes so the NMI takes its short path, $C260 blanks, a 1 KB nametable at
$2000, CHR $17 through $25 and CHR $12 through $23, sprites hidden ($C199),
the 32-byte palette through the $0195 buffer and its $01B5 request, $28-$2B
zeroed ($CA9F) and the attract timers restarted with A = 0 ($ADF9). The
scene-1 loop, START from either controller, song $04, the attract cutscene
and the demo game stay stock.

The art is data/title32/titleassets.json from tools/title32_convert.py. Its
tiles replace CHR bank $17, which only the stock title maps; the stock bank's
digest is pinned here, and the art's font glyphs must equal this ROM's CHR
bank $00.
"""
import argparse
import json
from pathlib import Path

from build_bank11 import assemble
from build_draw32 import (
    ROOT, Region, apply_changes, check_guards, claim, manifest_ranges, padded, refuse_aliases, sha256, word,
)
from build_pick32 import PROTECTED_SHA256 as PRIOR_SHA256, protect_output as protect_prior_output
from build_teamnames32 import HEADER, ROM_SIZE
import menu32_convert as menu

BASE_SHA256 = "8fb36a7b6f3fea03ec9b4bc76dce24141e7dc6522a0675a64b5d7b9135ac8cfa"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
ART = ROOT / "art/title32"
ASSETS = ROOT / "data/title32/titleassets.json"
FORMAT = "titleassets/1"
TITLE_CHR = 0x17
STOCK_CHR17_SHA256 = "5199e828f5bf67c09e4bb52539450ec6a6284299388aa1e4abc5cd0cfbf605fa"
CODE, MAP_TOP, MAP_BOTTOM, PALETTE = 0xA980, 0xAA00, 0xBD20, 0xBF40
TOP_BYTES = 15 * 32                      # nametable rows 0-14; rows 15-29 and the attributes follow at MAP_BOTTOM

REGIONS = (
    Region("title-hook", 0, 0xAC5A, 0xAC5D),
    Region("title-code", 0, CODE, MAP_TOP),
    Region("title-map-top", 0, MAP_TOP, MAP_TOP + TOP_BYTES),
    Region("title-map-bottom", 0, MAP_BOTTOM, MAP_BOTTOM + 0x400 - TOP_BYTES),
    Region("title-palette", 0, PALETTE, PALETTE + 0x20),
    Region("title-chr", "chr", TITLE_CHR * 0x1000, TITLE_CHR * 0x1000 + 0x1000),
)

DEPENDENCIES = (
    ("stock title draw $AC5A", 0, 0xAC5A, "E6 2C 20 60 C2 20 C4 C5 18 15 17 20 A9 12 85 23 20 34 AE A9 93 20 A4 C1"
     " A9 07 20 A4 C1 20 9F CA 20 F9 AD C6 2C 60"),
    ("title init $AC00", 0, 0xAC00, "20 6F C2 8D 90 01 85 B8 85 BE 85 BD 85 BA 85 BB 8D 7A 04 85 C0 20 5A AC EE 7B"
     " 04 A9 04 20 49 C2 60"),
    ("attract phase table $AC4A", 0, 0xAC4A, "80 AC AA AC C7 AC 5A AC F2 AC"),
    ("attract timers $ADF9", 0, 0xADF9, "8D 9D 04 8D 9E 04 60"),
    ("blank $C260", 15, 0xC260, "48 2C 02 20 10 FB A9 40 8D 01 20 85 AD 68 60"),
    ("OAM hide $C199", 15, 0xC199, "A9 F0 A2 00 9D 00 02 CA D0 FA 60"),
    ("scroll clear $CA9F", 15, 0xCA9F, "A9 00 85 28 85 29 85 2A 85 2B 60"),
    ("NMI vector", 15, 0xFFFA, "85 CD"),
)
DIGESTS = (
    ("title, START and attract program $AC00-$AE5F", 0, 0xAC00, 0x260,
     "b8a9cf35ff9ddbae5883e9584945a39a8e1fb430eb18724fafb32d8851010353"),
    ("NMI $CD85-$CE5F", 15, 0xCD85, 0xDB, "fce7c3b6ffade1d18f1c3ff2177ce72bebce785cc9e6f3463ed029dcc2e0b464"),
)


def asm():
    return [
        "title_draw:",
        "INC $2C",
        "JSR $C260",
        "LDA #$20", "STA $2006", "LDA #$00", "STA $2006",
        f"LDA #${MAP_TOP & 0xFF:02X}", "STA $00", f"LDA #${MAP_TOP >> 8:02X}", "STA $01",
        f"LDA #${TOP_BYTES & 0xFF:02X}", "STA $02", f"LDA #${TOP_BYTES >> 8:02X}", "STA $03",
        "JSR td_copy",
        f"LDA #${MAP_BOTTOM & 0xFF:02X}", "STA $00", f"LDA #${MAP_BOTTOM >> 8:02X}", "STA $01",
        f"LDA #${(0x400 - TOP_BYTES) & 0xFF:02X}", "STA $02", f"LDA #${(0x400 - TOP_BYTES) >> 8:02X}", "STA $03",
        "JSR td_copy",
        f"LDA #${TITLE_CHR:02X}", "STA $25",
        "LDA #$12", "STA $23",
        "JSR $C199",
        "LDX #$1F",
        "td_pal:",
        f"LDA ${PALETTE:04X},X", "STA $0195,X", "DEX", "BPL td_pal",
        "INC $01B5",
        "JSR $CA9F",
        "JSR $ADF9",
        "DEC $2C",
        "RTS",
        # Copy the 16-bit count at $02/$03 from ($00) to $2007.
        "td_copy:",
        "LDY #$00",
        "tc_loop:",
        "LDA ($00),Y", "STA $2007",
        "INY", "BNE tc_count", "INC $01",
        "tc_count:",
        "LDA $02", "BNE tc_low", "DEC $03",
        "tc_low:",
        "DEC $02",
        "LDA $02", "ORA $03", "BNE tc_loop",
        "RTS",
    ]


def load_assets(path=ASSETS):
    assets = json.loads(Path(path).read_text())
    if assets.get("format") != FORMAT or assets.get("chr_bank") != TITLE_CHR:
        raise ValueError(f"expected {FORMAT} art for CHR ${TITLE_CHR:02X}")
    return assets


def check_assets(base, assets):
    """The converted art must be one whole screen whose text glyphs are this ROM's stock font."""
    sizes = {"chr": 0x1000, "nametable": 960, "attributes": 64, "palette": 32}
    data = {key: bytes.fromhex(assets[key]) for key in sizes}
    for key, size in sizes.items():
        if len(data[key]) != size:
            raise ValueError(f"title {key} must be {size} bytes")
    if any(color >= 0x40 for color in data["palette"]) or len(set(data["palette"][::4])) != 1:
        raise ValueError("title palette must be NES colors sharing one backdrop")
    glyphs = assets["font_glyphs"]
    if glyphs != sorted(set(glyphs)) or menu.BLANK not in glyphs or not all(0 <= g < 256 for g in glyphs):
        raise ValueError("font glyph list must be sorted unique tile ids including the blank")
    fonts = menu.font_patterns(base)
    for glyph in glyphs:
        if data["chr"][16 * glyph:16 * glyph + 16] != fonts[glyph]:
            raise ValueError(f"title tile ${glyph:02X} is not this ROM's CHR $00 glyph")
    defined = set(glyphs) | {i for i in range(256) if any(data["chr"][16 * i:16 * i + 16])}
    if assets["tiles_used"] != len(defined) or not set(data["nametable"]) <= defined:
        raise ValueError("title nametable or tile count disagrees with its CHR bank")
    return data


def labels():
    return assemble(asm(), CODE)[1]


def change_manifest(base, assets=None):
    check_guards(base, DEPENDENCIES, DIGESTS)
    data = check_assets(base, assets or load_assets())
    code, title = assemble(asm(), CODE)
    region = {r.name: r for r in REGIONS}
    screen = data["nametable"] + data["attributes"]
    return (
        claim(base, region["title-hook"], b"\x4C" + word(title["title_draw"]), bytes.fromhex("E6 2C 20")),
        claim(base, region["title-code"], padded(code, region["title-code"])),
        claim(base, region["title-map-top"], screen[:TOP_BYTES]),
        claim(base, region["title-map-bottom"], screen[TOP_BYTES:]),
        claim(base, region["title-palette"], data["palette"]),
        claim(base, region["title-chr"], data["chr"], STOCK_CHR17_SHA256),
    )


def build_rom(base, assets=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected pick32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned pick32")
    return apply_changes(base, change_manifest(base, assets), REGIONS)


def diff_manifest(base, rom, assets=None):
    assets = assets or load_assets()
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "assets_sha256": sha256(json.dumps(assets, indent=1).encode() + b"\n"),
            "ranges": manifest_ranges(change_manifest(base, assets))}


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    refuse_aliases(output, [ROOT / "build/pick32.nes", source.resolve().parent / "pick32.nes", source.resolve(),
                            ASSETS, *ART.rglob("*"), *(ROOT / "data/title32").rglob("*")], PROTECTED_SHA256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned pick32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        base = args.rom.read_bytes()
        rom = build_rom(base)
        args.out.write_bytes(rom)
    except (OSError, ValueError, KeyError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
