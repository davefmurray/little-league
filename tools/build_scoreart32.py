#!/usr/bin/env python3
"""Draw the converted pxl scoreboard art on the pinned modeart32 ROM.

    .venv/bin/python tools/build_scoreart32.py build/modeart32.nes -o build/scoreart32.nes
    .venv/bin/python tools/build_scoreart32.py build/modeart32.nes -o build/scoreart32.nes --manifest
    .venv/bin/python tools/build_scoreart32.py build/modeart32.nes -o OUT --assets data/scoreart32/scoreassets.json

Only the scoreboard's background and rows change. Scene $0A (bank 4 $B39D) and scene $0B ($FFC0,
then $B63D) keep their stock code: the half-zero bypass, the name, inning header, line score,
R H E and statistics writer, the jingle, every exit and the championship results gate. Bank 4
$B3C0-$B3D3 held the two palette loads ($C1A4 #$17 and #$90), the blank ($C260) and the metatile
screen load (JSR $C5C4 .byte $0C,$0C,$05,$20). It becomes JSR $B800, JMP $B3D4 and NOPs; the
stock writer continues at $B3D4. In bank 4 padding:

  $B800  the draw: hold $2C (the NMI's short path), stage the $B880 palette at $0195-$01B4 and
         request it ($01B5), blank through $C260, drop a stale display list ($32), wait again
         through $C260 as $C5C4 did, copy $B900-$BCFF to $2000-$23FF, busy-wait DELAY cycles,
         select BG CHR $05 through $25, release $2C, return
  $B880  the 32-byte palette
  $B900  the 960-byte nametable and 64 attributes

Both stock vblank waits stay. The busy wait makes the CPU cycles from the second wait's return
to $B3D4 equal the 41,436 the stock metatile decode spent (NMIs excluded), so the writer starts
on stock's frame and the jingle, the A-press window, every scene change and every APU write keep
theirs. The count holds for this placement: the draw sits inside page $B8, the palette loop reads
$B880-$B89F and the copy reads whole pages, so no branch or indexed read crosses a page. Moving
or editing the draw needs a new measurement; tools/test_scoreart32.py fails until DELAY matches.

Four writer tables move rows and no column moves (scoreart32_assets.GEOMETRY):
  $B41D        header address low byte    $2128 -> $2108, row 9 -> 8
  $B54A-$B551  line-score rows            10/12 -> 9/11, R H E with them
  $B552-$B559  statistic rows             18/20 -> 15/17
  $B5BE-$B5C1  name sprite Y              level with their value rows
CHR $05, the stock scoreboard background, is replaced whole; its 78 glyph tiles keep their stock
ids. Static scans find one literal selector, the replaced $B3CD load, and one latent table entry,
fixed $FB53 preset 1, which no literal preset call passes; the guards pin both and the known
table-driven selectors. Bank 14, the fixed bank and every other PRG and CHR bank, CHR $18 (the
shared name font) included, stay byte-identical.

At runtime the draw writes $00/$01, $25, $32, $0195-$01B5, $2C (balanced) and, through $C260,
$AD: a subset of what the replaced calls wrote. The stage allocates no RAM and never touches
WRAM, the bracket, series or ownership state.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile

from build_bank11 import assemble
from build_draw32 import (
    ROOT, Region, apply_changes, check_guards, claim, locate, manifest_ranges, padded, refuse_aliases, sha256,
)
from build_modeart32 import (
    PROTECTED_SHA256 as PRIOR_SHA256, protect_output as protect_prior_output, protected_paths as prior_paths,
)
from build_teamnames32 import HEADER, ROM_SIZE
from modeart32_assets import ASSETS as MODE_ASSETS
from scoreart32_assets import GEOMETRY, SCORE_CHR, STOCK_GEOMETRY, ScoreAssets
import scoreart32_assets

BASE_SHA256 = "7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
ASSETS = scoreart32_assets.ASSETS
ART = ROOT / "art/scoreart32"
BANK = 4
HOOK, CONTINUE = 0xB3C0, 0xB3D4
CODE, PALETTE, SCREEN = 0xB800, 0xB880, 0xB900
NOP = 0xEA
STOCK_INTERVAL = 41436       # stock cycles from the second wait's return to $B3D4, NMIs excluded
COPY_INTERVAL = 14424        # the draw's cycles over the same span without the busy wait
DELAY = STOCK_INTERVAL - COPY_INTERVAL
STOCK_CHR05_SHA256 = "a1fb1cb08251314148c8b4aa9c0969da7cd6e6c8d3a3dcf52ac7873d66317ffb"

REGIONS = (
    Region("score-draw-call", BANK, HOOK, CONTINUE),
    Region("header-address", BANK, 0xB41D, 0xB41E),
    Region("line-rows", BANK, 0xB54A, 0xB552),
    Region("stat-rows", BANK, 0xB552, 0xB55A),
    Region("name-rows", BANK, 0xB5BE, 0xB5C2),
    Region("score-code", BANK, CODE, CODE + 0x80),
    Region("score-palette", BANK, PALETTE, PALETTE + 0x20),
    Region("score-screen", BANK, SCREEN, SCREEN + 0x400),
    Region("score-chr", "chr", SCORE_CHR * 0x1000, SCORE_CHR * 0x1000 + 0x1000),
)
STOCK_DRAW_CALL = "A9 17 20 A4 C1 A9 90 20 A4 C1 20 60 C2 20 C4 C5 0C 0C 05 20"

DEPENDENCIES = (
    ("scene $0A entry to the OAM hide $B39D", BANK, 0xB39D, "AE 02 04 E8 D0 FA AD 8A 04 D0 0D A9 00 8D 43 05 A9 01"
     " 20 49 C2 4C 99 B6 E6 2C 20 9F CA 8D 90 01 20 99 C1"),
    ("scene $0A writer calls $B3D4", BANK, CONTINUE, "20 97 B5 A9 00 85 B9 8D 7A 04 20 0E B4 20 82 B4 E6 B9 E6 B8"
     " 20 82 B4 A9 18 85 23 20 C6 B5 C6 2C EE 7B 04"),
    ("header address immediates $B417", BANK, 0xB417, "A9 21 8D 06 20 A9 28 8D 06 20"),
    ("R H E column offset $B516", BANK, 0xB516, "18 A5 04 69 10 48"),
    ("name sprite X $B5A4", BANK, 0xB5A4, "A9 10 8D B3 06"),
    ("name OAM slots $B5BA", BANK, 0xB5BA, "01 0D 19 25"),
    ("name sides $B5C2", BANK, 0xB5C2, "00 01 00 01"),
    ("blank and flush wait $C260", 15, 0xC260, "48 2C 02 20 10 FB A9 40 8D 01 20 85 AD 68 60 A5 32 D0 FC 60"),
    ("NMI short path while $2C is held $CD8A", 15, 0xCD8A, "A5 2C 8D E6 04 D0 50"),
    ("NMI CHR apply $CE45", 15, 0xCE45, "A5 2D D0 14 A5 23 20 1C C1 A5 25 4C 34 C1"),
    ("NMI palette upload $CE5E", 15, 0xCE5E, "AD B5 01 F0 FA A2 00 8E B5 01 AD 95 01 8D A5 01"),
    ("scene $0B results gate $FFC0", 15, 0xFFC0, "AD E2 04 F0 0D AD D0 04 F0 08 A9 0B 20 4E C1 4C A0 83 4C 3D B6"),
    ("latent CHR $05 preset 1 $FB53", 15, 0xFB53, "06 18 05 05 18 70"),
    ("CHR preset 7 call bank 1 $AF09", 1, 0xAF09, "A9 07 20 C1 C6"),
    ("CHR preset 0 call bank 2 $B994", 2, 0xB994, "A9 00 20 C1 C6"),
    ("CHR preset 2 call bank 3 $AF9B", 3, 0xAF9B, "A9 02 4C C1 C6"),
    ("CHR preset 6 call bank 5 $AC76", 5, 0xAC76, "A9 06 20 C1 C6"),
    ("CHR preset 4 call bank 5 $AC97", 5, 0xAC97, "A9 04 20 C1 C6"),
    ("CHR preset 8 call bank 5 $ACF2", 5, 0xACF2, "A9 08 20 C1 C6"),
)
DIGESTS = (
    ("bank 4 scoreboard program and tables $B39D-$B6F6", BANK, 0xB39D, 0xB6F7 - 0xB39D,
     "56438a02966e68c12d75a45490848f64ff84471beec7397797def4fe81c1bc34"),
    ("bank 4 name font tables $8000-$83FF", BANK, 0x8000, 0x400,
     "26bd3455657fe1777bcc0aaa2955b38bd3fa27ce3e1ba51b05d8db6a6ed4167e"),
    ("bank 4 team-name writers $9A00-$9A19", BANK, 0x9A00, 0x1A,
     "5d6d220caf2344daa8ac21d8eaa31c435e0c9729acece85de273caa0d9dd36de"),
    ("fixed bank $C000-$FFFF", 15, 0xC000, 0x4000,
     "c38587dc7ee5601a742bf1da30453fc06b303946a39d4d6d398128ac4c5aabb9"),
    ("CHR $18 name font", "chr", 0x18000, 0x1000,
     "8a058223e5f2c3ab5579395148463c000a5ac93d4eed6f014ba1507dbf56e769"),
    ("bank 2 animation CHR selectors $97C0-$98BF", 2, 0x97C0, 0x100,
     "459af1a7f4f0860d5176df4726695b3b2e96f4d8101498237d9c45cf8aa864e9"),
    ("bank 3 CHR selectors $AF48-$AF4A", 3, 0xAF48, 3,
     "c59d2f37216f914dcdd7e15077a877af19c345f951e3725f1e24cb0eb8a78cd2"),
    ("bank 6 CHR selectors $9037-$903C", 6, 0x9037, 6,
     "fe3e95981ffdf153cc4cd27cfd0c993087f72cfaf8d1e101b236f2ebbfebf0c9"),
)


def delay_lines(cycles):
    """A busy wait of exactly `cycles` CPU cycles, for code whose branches stay inside one page:
    LDY #outer, LDX #inner, DEX/BNE and DEY/BNE spend 2 + outer * (5 * inner + 6) - 1, the closest
    pair from below wins, and NOPs (2) with at most one BIT $00 (3) pay the rest."""
    if cycles == 0:
        return []
    best = None
    for outer in range(1, 256):
        for inner in range(1, 256):
            rest = cycles - (2 + outer * (5 * inner + 6) - 1)
            if rest >= 0 and rest != 1 and (best is None or rest < best[2]):
                best = (outer, inner, rest)
    if best is None:
        raise ValueError(f"no busy wait spends exactly {cycles} cycles")
    outer, inner, rest = best
    tail = ["NOP"] * (rest // 2) if rest % 2 == 0 else ["NOP"] * ((rest - 3) // 2) + ["BIT $00"]
    return [f"LDY #${outer:02X}", "delay:", f"LDX #${inner:02X}", "delay_inner:", "DEX", "BNE delay_inner", "DEY",
            "BNE delay", *tail]


def draw_asm(delay=DELAY):
    return [
        "INC $2C",
        "LDX #$1F",
        "palette:",
        f"LDA ${PALETTE:04X},X", "STA $0195,X", "DEX", "BPL palette",
        "INC $01B5",
        "JSR $C260",
        "LDA #$00", "STA $32",
        "JSR $C260",
        "LDA #$20", "STA $2006", "LDA #$00", "STA $2006",
        "STA $00", f"LDA #${SCREEN >> 8:02X}", "STA $01",
        "LDX #$04", "LDY #$00",
        "copy:",
        "LDA ($00),Y", "STA $2007", "INY", "BNE copy",
        "INC $01", "DEX", "BNE copy",
        *delay_lines(delay),
        f"LDA #${SCORE_CHR:02X}", "STA $25",
        "DEC $2C",
        "RTS",
    ]


def draw_code(delay=DELAY):
    code, _ = assemble(draw_asm(delay), CODE)
    if (CODE + len(code) - 1) >> 8 != CODE >> 8 or PALETTE & 0xFF > 0xE0 or SCREEN & 0xFF:
        raise ValueError("the draw must stay in one page and read its palette and screen without page crossings")
    return code


def hook_code(region):
    code, _ = assemble([f"JSR ${CODE:04X}", f"JMP ${CONTINUE:04X}"], HOOK)
    return code + bytes((NOP,)) * (region.end - region.start - len(code))


def load_assets(path=None):
    return ScoreAssets.load(path or ASSETS)


def change_manifest(base, assets=None):
    check_guards(base, DEPENDENCIES, DIGESTS)
    assets = assets or load_assets()
    region = {r.name: r for r in REGIONS}
    return (
        claim(base, region["score-draw-call"], hook_code(region["score-draw-call"]), bytes.fromhex(STOCK_DRAW_CALL)),
        claim(base, region["header-address"], GEOMETRY.header_operand(), STOCK_GEOMETRY.header_operand()),
        claim(base, region["line-rows"], GEOMETRY.line_table(), STOCK_GEOMETRY.line_table()),
        claim(base, region["stat-rows"], GEOMETRY.stat_table(), STOCK_GEOMETRY.stat_table()),
        claim(base, region["name-rows"], GEOMETRY.name_table(), STOCK_GEOMETRY.name_table()),
        claim(base, region["score-code"], padded(draw_code(), region["score-code"])),
        claim(base, region["score-palette"], assets.palette),
        claim(base, region["score-screen"], assets.screen()),
        claim(base, region["score-chr"], assets.chr, STOCK_CHR05_SHA256),
    )


def check_output(base, rom):
    """Whole-ROM postconditions: same size, and no byte changed outside the scoreart32 regions."""
    if len(rom) != len(base):
        raise ValueError("the built ROM changed size")
    owned = set()
    for r in REGIONS:
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end - 1) + 1))
    if any(a != b and i not in owned for i, (a, b) in enumerate(zip(base, rom))):
        raise ValueError("a byte changed outside the scoreart32 regions")


def build_rom(base, assets=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected modeart32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned modeart32")
    rom = apply_changes(base, change_manifest(base, assets), REGIONS)
    check_output(base, rom)
    return rom


def diff_manifest(base, rom, assets=None):
    assets = assets or load_assets()
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "assets_sha256": sha256(assets.dumps().encode()),
            "ranges": manifest_ranges(change_manifest(base, assets))}


def protected_paths(source, art=ART):
    """Files no scoreart32 tool may overwrite: the inputs and every earlier one, all tools, art, data and
    docs, recursively, and the art directory in use."""
    source = Path(source)
    return [ROOT / "build/modeart32.nes", source.resolve().parent / "modeart32.nes", MODE_ASSETS,
            *prior_paths(source), *(ROOT / "tools").rglob("*"), *(ROOT / "docs").rglob("*"), *Path(art).rglob("*")]


def is_inside(output, directory):
    """Compare existing directory identities; reserve missing roots across case/Unicode spellings."""
    import unicodedata

    output, directory = Path(output), Path(directory)
    places = {Path(os.path.abspath(output)), output.resolve()}
    roots = {Path(os.path.abspath(directory)), directory.resolve()}
    if any(place == root or root in place.parents for place in places for root in roots):
        return True
    for root in roots:
        if root.exists():
            for place in places:
                if any(parent.exists() and parent.samefile(root) for parent in (place, *place.parents)):
                    return True
        else:
            reserved = tuple(unicodedata.normalize('NFC', p).casefold() for p in root.parts)
            for place in places:
                parts = tuple(unicodedata.normalize('NFC', p).casefold() for p in place.parts)
                if parts[:len(reserved)] == reserved:
                    return True
    return False


def refuse_inside(output, directory):
    """No output may land in a protected directory, including through filesystem aliases."""
    if is_inside(output, directory):
        raise ValueError(f"output aliases protected input art directory {directory}")


def protect_output(source, output, assets=None):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    refuse_aliases(output, [assets or ASSETS, *protected_paths(source)], PROTECTED_SHA256)
    refuse_inside(output, ART)


def write_atomic(path, data):
    """Replace `path` through a sibling temporary file: no reader sees a partial file, and a hard or
    symbolic link at `path` is replaced instead of written through."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.is_file() and not path.is_symlink() else 0o644
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as staged:
        pending = Path(staged.name)
        staged.write(data)
    try:
        os.chmod(pending, mode)
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned modeart32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--assets", type=Path, default=ASSETS, help="scoreassets/1 file (default %(default)s)")
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out, args.assets)
        base = args.rom.read_bytes()
        assets = load_assets(args.assets)
        rom = build_rom(base, assets)
        write_atomic(args.out, rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom, assets), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
