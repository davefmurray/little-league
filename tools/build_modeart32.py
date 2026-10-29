#!/usr/bin/env python3
"""Draw the converted pxl mode-menu art on the pinned title32 ROM.

    .venv/bin/python tools/build_modeart32.py build/title32.nes -o build/modeart32.nes
    .venv/bin/python tools/build_modeart32.py build/title32.nes -o build/modeart32.nes --manifest

Only the mode menu's presentation changes. Scene 6 ($9400) and the scene-7
state machine ($944F) stay stock in bank 1: song $06, selection, wrap, sound
effects, every exit, Exhibition ownership and the cursor routine. Four stock
calls now ask bank 13 for a picture through one entry, LDA #request then
JSR $9432:

  $942A  request 0  scene 6 draws the whole main-menu screen, then JMP $944B
  $9464  request 1  state 5 (B) redraws the main menu's text
  $948F  request 2  state 1 draws the Championship text
  $9484  request 3  state 1 draws the Exhibition text

$9432 is a 16-byte hop pad, byte-identical in banks 1 and 13. Bank 1 runs its
first three instructions; the stock PRG writer $C14E maps bank 13, whose copy
resumes at $9438, calls the request and maps bank 1 again, whose copy resumes
at the final RTS. There is no fixed-bank change. In bank 13 $9000-$9FFF:

  $9000  1 KB main-menu nametable and attributes
  $9400  32-byte palette
  $9432  the hop pad
  $9442  request: 0 holds $2C (the NMI's short path), blanks through $C260,
         drops a stale display list, copies the 1 KB to $2000, selects CHR
         $06 (background) and $1B (sprites) through $25/$23 and queues the
         palette through $0195/$01B5; 1-3 pass that menu's list to the stock
         walker $C863, which draws one raw run per NMI
  $9500  list address table (low x3, high x3), then the three run lists

The art is data/modeart32/modeassets.json from tools/modeart32_convert.py,
checked by tools/modeart32_assets.py before any byte here is built. Its tiles
replace CHR bank $06, the stock mode background, which only this scene maps;
its font glyphs must equal this ROM's CHR $00. The stock cursor table at
$95E4 takes the converted ball positions; the ball sprites stay stock CHR $1B.

The stage writes only stock scratch at runtime: $00/$01, $AA/$AB, $06B3-$06D5,
$0300-$0322, $0195-$01B5, $23, $25, $32, $2C (balanced), and through stock
routines $06, $27, $2D, $2E, $AC and $AD. Bank 13 must be entirely unused in
the input; this stage is its first owner.
"""
import argparse
from itertools import accumulate
import json
from pathlib import Path

from build_bank11 import assemble
from build_draw32 import (
    ROOT, Region, apply_changes, check_guards, claim, locate, manifest_ranges, padded, read, refuse_aliases,
    sha256,
)
from build_teamnames32 import HEADER, ROM_SIZE
from build_title32 import PROTECTED_SHA256 as PRIOR_SHA256, protect_output as protect_prior_output
from modeart32_assets import ASSETS, MENUS, MODE_CHR, AssetError, ModeAssets

BASE_SHA256 = "8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
ART = ROOT / "art/modeart32"
HOME_BANK, FAR_BANK = 1, 13
SPRITE_CHR, FONT_CHR = 0x1B, 0x00
FAR, FAR_END = 0x9000, 0xA000
SCREEN, PALETTE, PAD, CODE, LISTS = 0x9000, 0x9400, 0x9432, 0x9442, 0x9500
DRAW, DRAW_DONE = 0x942A, 0x944B
CURSOR_SHAPE = 0x95D4
DRAW_REQUEST = 0
REQUESTS = {name: i + 1 for i, name in enumerate(MENUS)}
TEXT_CALLS = {"main": 0x9464, "exhibition": 0x9484, "championship": 0x948F}
STOCK_CHR06_SHA256 = "c639380f8fea74e9dfc7232807f11016fb34522e7769018bb199f4a48bf424fc"

REGIONS = (
    Region("mode-draw", HOME_BANK, DRAW, DRAW_DONE),
    Region("main-text-call", HOME_BANK, 0x9464, 0x9469),
    Region("exhibition-text-call", HOME_BANK, 0x9484, 0x9489),
    Region("championship-text-call", HOME_BANK, 0x948F, 0x9494),
    Region("cursor-positions", HOME_BANK, 0x95E4, 0x95F6),
    Region("mode-far", FAR_BANK, FAR, FAR_END),
    Region("mode-chr", "chr", MODE_CHR * 0x1000, MODE_CHR * 0x1000 + 0x1000),
)
STOCK = {
    "mode-draw": "A9 92 20 A4 C1 A9 0D 20 A4 C1 A9 1B 85 23 E6 2C 20 60 C2 20 C4 C5 03 21 06 20 C6 2C 20 40 C8"
                 " F6 95",
    "main-text-call": "20 40 C8 F6 95",
    "exhibition-text-call": "20 40 C8 37 96",
    "championship-text-call": "20 40 C8 62 96",
    "cursor-positions": "20 30 20 50 20 70 50 30 50 50 50 70 20 30 20 50 20 70",
}

DEPENDENCIES = (
    ("mode init $9400", HOME_BANK, 0x9400, "A9 06 CD 01 04 F0 03 20 49 C2 20 99 C1 20 9F CA 85 BA 85 B9 8D 7A 04"
     " 8D 22 05 8D 2D 05 8D 2E 05 8D E0 06 A9 80 85 B8 8D E1 06"),
    ("mode init tail $944B", HOME_BANK, DRAW_DONE, "EE 7B 04 60"),
    ("ball cursor shape $95D4", HOME_BANK, CURSOR_SHAPE, "00 E6 00 00 00 E7 00 08 08 E8 00 00 08 E9 00 08"),
    ("PRG writer $C14C", 15, 0xC14C, "A5 27 85 27 E6 2D 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF"
     " C6 2D 60"),
    ("blank and flush wait $C260", 15, 0xC260, "48 2C 02 20 10 FB A9 40 8D 01 20 85 AD 68 60 A5 32 D0 FC 60"),
    ("OAM hide $C199", 15, 0xC199, "A9 F0 A2 00 9D 00 02 CA D0 FA 60"),
    ("scroll clear $CA9F", 15, 0xCA9F, "A9 00 85 28 85 29 85 2A 85 2B 60"),
    ("NMI vector", 15, 0xFFFA, "85 CD"),
)
DIGESTS = (
    ("mode menu program and data $9400-$96A8", HOME_BANK, 0x9400, 0x2A9,
     "5a455f362daae2ba83a1d4c5b7d8e54ea8e94a66c8800ac3adebd375c0bca2df"),
    ("mapper writers $C102-$C16B", 15, 0xC102, 0x6A,
     "83a625a1bd5a096ceee559f2afce571cd8e824f717d2557e0b7352bb171796e8"),
    ("display list flush $C53A-$C584", 15, 0xC53A, 0x4B,
     "367bab66264259ba9514559fa4ab72849d30b2686e62ba642abfea15ad93f5e4"),
    ("text lists and raw runs $C713-$C891", 15, 0xC713, 0x17F,
     "d0738dbae0ea2f379b2d0c68d981a91395babf20bffcc35a8512c3ff1935b267"),
    ("scene dispatch $CC30-$CCBA", 15, 0xCC30, 0x8B,
     "4f00a2f48c5fbdfb9e898b7a9dd86d009d7ba601a56ced1146ee6dcb5cb92dd6"),
    ("NMI, pads and audio $CD85-$CFA9", 15, 0xCD85, 0x225,
     "935ba5239a2afb1ad1d709194cb675be4fb79d9e88350cf41bcd944d16fd67c2"),
    ("fixed bank $C000-$FFFF", 15, 0xC000, 0x4000, "c38587dc7ee5601a742bf1da30453fc06b303946a39d4d6d398128ac4c5aabb9"),
    ("bank 13, unused", FAR_BANK, 0x8000, 0x4000, "0fbba07a833d4dcfc7024eaf313661a0ba8f80a05c6d29b8801c612e10e60dee"),
    ("CHR $00 font", "chr", 0x0000, 0x1000, "771012bc129730fbef4c9bd840bf68f91329d625bfde1f75c0a5940400d2ea32"),
    ("CHR $17 title", "chr", 0x17000, 0x1000, "e1ef28338eb74c7062d29a33c5cb12498231ea8358b55ac126210b273c4736f9"),
    ("CHR $19 picker", "chr", 0x19000, 0x1000, "e358386bc743abb58b1bec0dfa4421fbd75f8f50b28440f8ca045a26b0407e3b"),
    ("CHR $1B sprites and ball", "chr", 0x1B000, 0x1000,
     "330afeaa1a18c62cbb0fe1bd39101da67efac96812a43109449737dc1301b5bb"),
)


def far_asm():
    return [
        "request:",
        "TAX",
        "BEQ draw",
        f"LDA ${LISTS - 1:04X},X", "STA $AA",
        f"LDA ${LISTS + len(MENUS) - 1:04X},X", "STA $AB",
        "JMP $C863",
        "draw:",
        "INC $2C",
        "JSR $C260",
        "LDA #$00", "STA $32",
        "LDA #$20", "STA $2006", "LDA #$00", "STA $2006",
        "STA $00", f"LDA #${SCREEN >> 8:02X}", "STA $01",
        "LDX #$04", "LDY #$00",
        "copy:",
        "LDA ($00),Y", "STA $2007",
        "INY", "BNE copy",
        "INC $01", "DEX", "BNE copy",
        f"LDA #${MODE_CHR:02X}", "STA $25",
        f"LDA #${SPRITE_CHR:02X}", "STA $23",
        "LDX #$1F",
        "palette:",
        f"LDA ${PALETTE:04X},X", "STA $0195,X", "DEX", "BPL palette",
        "INC $01B5",
        "DEC $2C",
        "RTS",
    ]


def hop_pad():
    """Bank 1 runs PHA..JSR $C14E and the final RTS; bank 13 runs PLA..JSR $C14E."""
    code, _ = assemble(["PHA", f"LDA #${FAR_BANK:02X}", "JSR $C14E", "PLA", f"JSR ${CODE:04X}",
                        f"LDA #${HOME_BANK:02X}", "JSR $C14E", "RTS"], PAD)
    if len(code) != 16 or code[6] != 0x68 or code[15] != 0x60:
        raise ValueError("hop pad must resume at $9438 in bank 13 and $9441 in bank 1")
    return code


def far_block(assets):
    """Bank 13 $9000-$9FFF."""
    code, far = assemble(far_asm(), CODE)
    if far["request"] != CODE or CODE + len(code) > LISTS:
        raise ValueError("bank-13 code must start at the pad's call target and end before the list table")
    lists = [assets.run_list(name) for name in MENUS]
    starts = list(accumulate([LISTS + 2 * len(MENUS)] + [len(data) for data in lists[:-1]]))
    end = starts[-1] + len(lists[-1])
    if end > FAR_END:
        raise AssetError(f"the run lists end at ${end:04X}, past bank 13's reservation")
    block = bytearray(b"\xFF" * (FAR_END - FAR))
    for addr, data in ((SCREEN, assets.nametable + assets.attributes), (PALETTE, assets.palette), (PAD, hop_pad()),
                       (CODE, code), (LISTS, bytes(a & 0xFF for a in starts) + bytes(a >> 8 for a in starts)),
                       *zip(starts, lists)):
        block[addr - FAR:addr - FAR + len(data)] = data
    if len(block) != FAR_END - FAR:
        raise ValueError("bank-13 block overflowed")
    return bytes(block)


def draw_hook(region):
    stub, _ = assemble([f"LDA #${DRAW_REQUEST:02X}", f"JSR ${PAD:04X}", f"JMP ${DRAW_DONE:04X}"], DRAW)
    if DRAW + len(stub) != PAD:
        raise ValueError("the scene-6 stub must end where the hop pad starts")
    return padded(stub + hop_pad(), region)


def text_call(name):
    code, _ = assemble([f"LDA #${REQUESTS[name]:02X}", f"JSR ${PAD:04X}"], TEXT_CALLS[name])
    return code


def load_assets(path=ASSETS):
    return ModeAssets.load(path)


def check_font(base, assets):
    """The art's text tiles are copies of this ROM's CHR $00 glyphs, at their ids."""
    fonts = read(base, "chr", FONT_CHR * 0x1000, 0x1000)
    for glyph in assets.font_glyphs:
        if assets.chr[16 * glyph:16 * glyph + 16] != fonts[16 * glyph:16 * glyph + 16]:
            raise AssetError(f"mode tile ${glyph:02X} is not this ROM's CHR $00 glyph")


def change_manifest(base, assets=None):
    check_guards(base, DEPENDENCIES, DIGESTS)
    assets = assets or load_assets()
    check_font(base, assets)
    region = {r.name: r for r in REGIONS}

    def hook(name):
        return bytes.fromhex(STOCK[name])
    return (
        claim(base, region["mode-draw"], draw_hook(region["mode-draw"]), hook("mode-draw")),
        claim(base, region["main-text-call"], text_call("main"), hook("main-text-call")),
        claim(base, region["exhibition-text-call"], text_call("exhibition"), hook("exhibition-text-call")),
        claim(base, region["championship-text-call"], text_call("championship"), hook("championship-text-call")),
        claim(base, region["cursor-positions"], assets.cursor, hook("cursor-positions")),
        claim(base, region["mode-far"], far_block(assets)),
        claim(base, region["mode-chr"], assets.chr, STOCK_CHR06_SHA256),
    )


def check_output(base, rom):
    """Whole-ROM postconditions: same size, changes only inside the regions, identical hop pads."""
    if len(rom) != len(base):
        raise ValueError("the built ROM changed size")
    owned = set()
    for r in REGIONS:
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end - 1) + 1))
    if any(a != b and i not in owned for i, (a, b) in enumerate(zip(base, rom))):
        raise ValueError("a byte changed outside the mode-art regions")
    pads = [read(rom, bank, PAD, 16) for bank in (HOME_BANK, FAR_BANK)]
    if pads[0] != pads[1] or pads[0] != hop_pad():
        raise ValueError("the bank-1 and bank-13 hop pads differ")


def build_rom(base, assets=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected title32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned title32")
    rom = apply_changes(base, change_manifest(base, assets), REGIONS)
    check_output(base, rom)
    return rom


def diff_manifest(base, rom, assets=None):
    assets = assets or load_assets()
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "assets_sha256": sha256(assets.dumps().encode()),
            "ranges": manifest_ranges(change_manifest(base, assets))}


def protected_paths(source):
    """Files no modeart32 tool may overwrite: inputs, every source, all art and data, recursively."""
    source = Path(source)
    return [ROOT / "build/title32.nes", source.resolve().parent / "title32.nes", source.resolve(),
            ROOT / "tools/verify.sh", *(ROOT / "tools").glob("*.py"), *(ROOT / "art").rglob("*"),
            *(ROOT / "data").rglob("*")]


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    refuse_aliases(output, [ASSETS, *protected_paths(source)], PROTECTED_SHA256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned title32 input")
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
