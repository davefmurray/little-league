#!/usr/bin/env python3
"""Redraw the HOME RUN celebration on the pinned analysisart32 ROM. Data only: no executable byte changes.

    .venv/bin/python -B tools/build_homerunart32.py build/analysisart32.nes -o build/homerunart32.nes
    .venv/bin/python -B tools/build_homerunart32.py build/analysisart32.nes -o OUT [--assets DIR] [--manifest]

--assets names the directory tools/homerunart32_convert.py fills (default build/homerunart32). Its
homerunassets.json must carry the digest data/homerunart32/digests.json records, and so must the built
ROM, before anything is written. --manifest prints the exact before/after manifest, computed from the two
ROM images.

The stock scene $05 keeps its whole state machine: state 1's 60-frame field overlay and the HR/HIT stats,
state 2 ($D755) loading palette record $0E and the $C5C4 screen (metatile set $15, map $24, CHR1 $04),
state 3 ($D77B) flipping CHR1 between $D793 = $04, $15 every 8 frames until song $0A ends, and the shared
$D7F8 exit. The stage rewrites only what that cutscene alone reads:

  CHR $04            frame a patterns   read through $D76C (the loader's CHR1 byte) and $D793[0]
  CHR $15            frame b patterns   read through $D793[1]; its one other selector, CHR preset 6 ($FB71,
                                        CHR0 $15), is applied only by bank 5 $AC78 after the split screen,
                                        which only scene $1C reaches. SPEED temporarily decrements its scene
                                        through $1C, then restores it before dispatch; the reader checks
                                        pin this path. A real-core census complements the static argument.
  bank 1 $8DF0-$8F1F map $24 and its attributes, read only through $FB35 by $D767
  bank 1 planes      $8400/$8500/$8600/$8700 + id for each metatile id the new map uses; every id the
                     VICTORY (map $2A) and split-screen (map $33) maps use keeps its stock planes
  fixed $F8C0-$F8CF  background palette record $0E, loaded only by $D75D; sprite palettes stay the field's

Every reader, table entry and shared map those claims rely on is pinned, tools/homerunart32_readers.py
re-derives the reader argument from the input's code, and a one-bit drift in any of them, a protected metatile
id or the input is refused.
"""
import argparse
import json
from pathlib import Path

from build_draw32 import ROOT, Region, apply_changes, check_guards, claim, locate, read, refuse_aliases, sha256
from build_scoreart32 import refuse_inside, write_atomic
import build_analysisart32 as prior
from build_teamnames32 import HEADER, ROM_SIZE
import homerunart32_assets as model
from homerunart32_assets import AssetError, HomerunAssets
import homerunart32_readers as readers

BASE_SHA256 = "1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e"
PROTECTED_SHA256 = prior.PROTECTED_SHA256 | {BASE_SHA256}
BUILD = ROOT / "build"
ASSETS = BUILD / "homerunart32"
OUTPUT = BUILD / "homerunart32.nes"
FIXTURES = BUILD / "homerunart32-fixtures"
REGISTRY = ROOT / "data/homerunart32/digests.json"
REGISTRY_FORMAT = "homerunart32-digests/1"
ASSET_JSON = "homerunassets.json"
EVIDENCE = (BUILD / "analysisart32", BUILD / "homerunart32-design", FIXTURES, BUILD / "vendor")

FIXED = model.FIXED
PLANES, MAP, RECORD = 0x8400, 0x8DF0, 0xF8C0
DATA_BANK = 1
REGIONS = (
    Region("chr04-frame-a", "chr", model.FRAME_CHR["a"] * model.CHR_SIZE, (model.FRAME_CHR["a"] + 1) * model.CHR_SIZE),
    Region("chr15-frame-b", "chr", model.FRAME_CHR["b"] * model.CHR_SIZE, (model.FRAME_CHR["b"] + 1) * model.CHR_SIZE),
    Region("map24", DATA_BANK, MAP, MAP + model.MAP_IDS + model.ATTRIBUTE_BYTES),
    Region("palette0e", FIXED, RECORD, RECORD + 16),
)
STOCK = {
    "chr04-frame-a": "482f48f61dc30bb24e6a8a9ee02ea3914598da24ba94aba55a5b0ccf794c123b",
    "chr15-frame-b": "a0f7f50c97d9c5231df6552c498ab9d458fe51bd98f08faa0f66cc80ffab90c2",
    "map24": "256ff0538e29489a8dd1e223c3f503e48fbd44e5f4bea531b53cc8d739c2c4ab",
    "palette0e": "0F 30 27 36 0F 21 27 36 0F 26 27 36 0F 30 05 36",
}
DEPENDENCIES = (
    ("scene $05 state table $D74A-$D754", FIXED, 0xD74A, "20 32 C2 95 D7 D6 D9 55 D7 7B D7"),
    ("scene $05 state 2 $D755-$D77A: record $0E, the $C5C4 screen $15/$24/CHR1 $04, wait for song $0A", FIXED, 0xD755,
     "20 9F CA 85 BA 20 99 C1 A9 0E 20 A4 C1 E6 2C 20 60 C2 20 C4 C5 15 24 04 20 C6 2C EE 7C 04 AD 01 04 C9 0A D0 F9"
     " 60"),
    ("scene $05 state 3 $D77B-$D794: CHR1 from $D793 every 8 frames until the song ends", FIXED, 0xD77B,
     "AD 01 04 30 10 E6 BA A5 BA 29 08 4A 4A 4A A8 B9 93 D7 85 25 60 4C F8 D7 04 15"),
    ("palette loader $C1A4-$C1E4", FIXED, 0xC1A4, "E6 2C 85 04 A9 00 06 04 2A 06 04 2A 85 00 06 04 2A 06 04 2A 48 29 07"
     " 85 05 EE B5 01 A6 00 BD F0 FF 65 04 85 04 BD F1 FF 65 05 85 05 68 0A 29 10 09 0F AA A0 10 B1 04 9D 95 01 CA 88"
     " D0 F7 C6 2C 60"),
    ("palette pointers $FFF0", FIXED, 0xFFF0, "DF F7"),
    ("metatile set $15 entry $FB05: bank 1 $8400", FIXED, model.SET_TABLE + model.HR_SET, "00 84 01"),
    ("map $24 entry $FB35: bank 1 $8DF0", FIXED, model.MAP_TABLE + model.HR_MAP, "F0 8D 01"),
    ("VICTORY map $2A entry $FB3B: bank 5 $916E", FIXED, model.MAP_TABLE + model.SHARED_MAPS["VICTORY"], "6E 91 05"),
    ("split-screen map $33 entry $FB44: bank 5 $94FE", FIXED, model.MAP_TABLE + model.SHARED_MAPS["split screen"],
     "FE 94 05"),
    ("NMI CHR apply $CE45-$CE52", FIXED, 0xCE45, "A5 2D D0 14 A5 23 20 1C C1 A5 25 4C 34 C1"),
    ("CHR preset 6 record $FB71: CHR0 $15, the only other CHR $15 selector", FIXED, 0xFB71, "06 15 12 12 12 68"),
    ("bank 5 split screen $AC6D: set $15, map $33, then CHR preset 6", 5, 0xAC6D,
     "20 C4 C5 15 33 12 20 E6 B8 A9 06 20 C1 C6"),
    ("bank 5 VICTORY screen $ACC6: set $15, map $2A", 5, 0xACC6, "20 C4 C5 15 2A 13 20"),
)
DIGESTS = (
    ("screen loader $C5C4-$C6C0", FIXED, 0xC5C4, 0xFD, "8e6e9e3375da6056034af7e4d2617a5392b17102614d9927f52b749627f0bcc0"),
    ("fixed bank $C000-$F8BF: scoring, statistics, exits, NMI, sound and loaders", FIXED, 0xC000, RECORD - 0xC000,
     "1ae93170f4bc614d38d078b74678e31f5353ceac768c1505a2f40179f2386766"),
    ("fixed bank $F8D0-$FFFF: the other palette records and the $C5C4 tables", FIXED, RECORD + 16,
     0x10000 - RECORD - 16, "80089b4338fca0cafd129852ed1093fd1613e1107ef98ec62f762ac3f9608984"),
    ("bank 1 $8000-$83FF", DATA_BANK, 0x8000, PLANES - 0x8000,
     "046628c29c4f6c5bf44c6bc32a0890699e724b5445dc5649bc2ff3dbd83554cc"),
    ("metatile set $15 planes $8400-$87FF", DATA_BANK, PLANES, 4 * model.PLANE_STRIDE,
     "f96819df9c6c9248e77f0a02009085dbac93c0766daa649a49ead1f1cb2b4b79"),
    ("bank 1 $8800-$8DEF", DATA_BANK, PLANES + 4 * model.PLANE_STRIDE, MAP - PLANES - 4 * model.PLANE_STRIDE,
     "8d8fbd99d1890680f4a56210ea663bf03869c19f531835a5d34f6918c80c3203"),
    ("bank 1 $8F20-$BFFF", DATA_BANK, MAP + 0x130, 0xC000 - MAP - 0x130,
     "3e2b1af7bd6554e0f2fad3f9fa161c33bf7e21b7430adb07f542a91a4c738e5d"),
    ("bank 5: the VICTORY and split-screen maps and the cutscene player that draws them", 5, 0x8000, 0x4000,
     "71da16ea5e91577b8a467e789da97385b467843571a95e8bab90a3553f67e402"),
    ("bank 6: ball in play, the fence test, the mass scorer $B73E and the play exit", 6, 0x8000, 0x4000,
     "b9b5263b7b7b8a0302fb1b19946cc4a0a9372318e5b1595f1114c83e9c8a2e43"),
)


def plane_regions(assets):
    """One single-byte region per plane byte of every metatile id the new map defines."""
    return tuple(Region(f"planes ${PLANES + model.PLANE_STRIDE * q + k:04X}", DATA_BANK,
                        PLANES + model.PLANE_STRIDE * q + k, PLANES + model.PLANE_STRIDE * q + k + 1)
                 for k in assets.planes for q in range(4))


def regions(assets):
    return REGIONS + plane_regions(assets)


def check_runtime(base, assets):
    """The assets fit what the stock loader and the shared screens read from the input."""
    if model.planes_location(base) != (PLANES, DATA_BANK) or model.map_location(base, model.HR_MAP) != (MAP, DATA_BANK):
        raise AssetError("metatile set $15 or map $24 is not where the stage claims it")
    if model.record_location(base) != RECORD:
        raise AssetError(f"palette record $0E is not at ${RECORD:04X}")
    shared = model.protected_ids(base)
    taken = sorted(set(assets.planes) & shared)
    if taken:
        raise AssetError(f"metatile ids {' '.join(f'${k:02X}' for k in taken)} belong to the VICTORY or split-screen "
                         "map and keep their stock planes")
    if len(assets.planes) > 0x100 - len(shared):
        raise AssetError(f"{len(assets.planes)} metatiles exceed the {0x100 - len(shared)} free ids")


def check_readers(base):
    """The CHR $15, set $15, map $24 and record $0E reader argument (tools/homerunart32_readers.py) holds."""
    failed = [c for c in readers.checks(base) if not c.ok]
    if failed:
        raise ValueError(f"the shared-reader argument fails: {failed[0].name} ({failed[0].detail})"
                         + (f" and {len(failed) - 1} more" if len(failed) > 1 else ""))


def change_manifest(base, assets):
    check_guards(base, DEPENDENCIES, DIGESTS)
    check_readers(base)
    check_runtime(base, assets)
    region = {r.name: r for r in REGIONS}
    changes = [
        claim(base, region["chr04-frame-a"], assets.chr_a, STOCK["chr04-frame-a"]),
        claim(base, region["chr15-frame-b"], assets.chr_b, STOCK["chr15-frame-b"]),
        claim(base, region["map24"], assets.metamap + assets.attributes, STOCK["map24"]),
        claim(base, region["palette0e"], assets.palette, bytes.fromhex(STOCK["palette0e"])),
    ]
    for r in plane_regions(assets):
        q, k = (r.start - PLANES) // model.PLANE_STRIDE, (r.start - PLANES) % model.PLANE_STRIDE
        changes.append(claim(base, r, bytes([assets.planes[k][q]]), read(base, DATA_BANK, r.start, 1)))
    return tuple(changes)


def owned_offsets(assets):
    owned = set()
    for r in regions(assets):
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end - 1) + 1))
    return owned


def check_output(base, rom, assets):
    """Whole-ROM postconditions: size and header, no byte outside the owned regions, the shared screens and the
    protected planes intact, and the loader's own decode showing the assets."""
    if len(rom) != len(base) or rom[:len(HEADER)] != base[:len(HEADER)]:
        raise ValueError("the built ROM changed size or header")
    owned = owned_offsets(assets)
    if any(a != b and i not in owned for i, (a, b) in enumerate(zip(base, rom))):
        raise ValueError("a byte changed outside the homerunart32 regions")
    for k in model.protected_ids(base):
        for q in range(4):
            if read(rom, DATA_BANK, PLANES + model.PLANE_STRIDE * q + k, 1) != read(base, DATA_BANK,
                                                                                   PLANES + model.PLANE_STRIDE * q + k, 1):
                raise ValueError(f"protected metatile ${k:02X} changed")
    for name, map_arg in model.SHARED_MAPS.items():
        if model.decode_screen(rom, model.HR_SET, map_arg) != model.decode_screen(base, model.HR_SET, map_arg):
            raise ValueError(f"the {name} screen decodes differently")
    metamap, attributes, nametable = model.decode_screen(rom, model.HR_SET, model.HR_MAP)
    if (metamap, attributes, nametable) != (assets.metamap, assets.attributes, assets.nametable()):
        raise ValueError("the loader's decode of map $24 differs from the assets")
    if read(rom, FIXED, model.record_location(rom), 16) != assets.palette:
        raise ValueError("palette record $0E differs from the assets")


def build_rom(base, assets):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected analysisart32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned analysisart32")
    rom = apply_changes(base, change_manifest(base, assets), regions(assets))
    check_output(base, rom, assets)
    return rom


def diff_manifest(base, rom, assets):
    """The exact before/after manifest, read from the two ROM images over the owned regions; every changed byte
    must fall inside one of them."""
    owned, ranges = owned_offsets(assets), []
    changed = [i for i, (a, b) in enumerate(zip(base, rom)) if a != b]
    if len(rom) != len(base) or not set(changed) <= owned:
        raise ValueError("the ROM changed outside the homerunart32 regions")
    for r in regions(assets):
        start, size = locate(r.bank, r.start), r.end - r.start
        before, after = base[start:start + size], rom[start:start + size]
        ranges.append({"name": r.name, "bank": r.bank, "start": f"${r.start:04X}", "end": f"${r.end - 1:04X}",
                       "file_offset": start, "size": size, "before_sha256": sha256(before),
                       "after_sha256": sha256(after), "before": before.hex(), "after": after.hex(),
                       "changed_file_offsets": [start + i for i in range(size) if before[i] != after[i]]})
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom), "assets_sha256": sha256(assets.dumps().encode()),
            "size": len(rom), "header": rom[:len(HEADER)].hex(), "changed_bytes": len(changed),
            "claimed_bytes": len(owned), "tile_pairs": assets.tile_pairs, "animated_pairs": assets.animated_pairs,
            "metatiles": len(assets.planes), "regions": ranges}



def read_registry(path=REGISTRY):
    registry = json.loads(Path(path).read_text())
    if (not isinstance(registry, dict) or registry.get("format") != REGISTRY_FORMAT
            or not isinstance(registry.get("outputs"), dict) or not isinstance(registry.get("rom"), str)):
        raise ValueError(f"{path} is not a {REGISTRY_FORMAT} registry")
    return registry


def load_assets(directory, registry):
    """The asset file tools/homerunart32_convert.py wrote, matching its registered digest."""
    data = (Path(directory) / ASSET_JSON).read_bytes()
    if sha256(data) != registry["outputs"].get(ASSET_JSON):
        raise ValueError(f"{Path(directory) / ASSET_JSON} differs from data/homerunart32/digests.json; regenerate "
                         "it with tools/homerunart32_convert.py")
    return HomerunAssets.parse(json.loads(data))


def protected_paths(source, inputs=()):
    """Files no homerunart32 tool may overwrite: its inputs, the registry and sources, every earlier stage's ROMs,
    assets and art, every file under art and data, and under build/ the analysisart32 outputs, root's design
    evidence and the CPU fixture cache, also through links."""
    source = Path(source)
    return [ROOT / "build/analysisart32.nes", source.resolve().parent / "analysisart32.nes", source.resolve(), REGISTRY,
            *inputs, *prior.protected_paths(source), *(ROOT / "art").rglob("*"), *(ROOT / "data").rglob("*"),
            *(path for directory in EVIDENCE[:3] for path in directory.rglob("*"))]


output_path = prior.output_path


def protect_output(source, output, inputs=()):
    """Refuse an output that aliases anything an earlier stage or this one protects: tracked files (outside
    build/), inputs, registries, earlier ROMs by path, link or content, and generated evidence."""
    source, output = Path(source), output_path(output)
    prior.protect_output(source, output, inputs)
    refuse_aliases(output, protected_paths(source, inputs), PROTECTED_SHA256)
    for directory in EVIDENCE:
        refuse_inside(output, directory)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned analysisart32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--assets", type=Path, default=ASSETS, help="homerunart32_convert.py output (default %(default)s)")
    ap.add_argument("--manifest", action="store_true", help="print the exact before/after manifest as JSON")
    args = ap.parse_args()
    try:
        args.out = output_path(args.out)
        inputs = [args.assets / ASSET_JSON, REGISTRY, *sorted(Path(args.assets).rglob("*")), *sorted(ASSETS.rglob("*"))]
        protect_output(args.rom, args.out, inputs)
        refuse_inside(args.out, args.assets)
        registry = read_registry()
        assets = load_assets(args.assets, registry)
        base = args.rom.read_bytes()
        rom = build_rom(base, assets)
        if sha256(rom) != registry["rom"]:
            raise ValueError(f"the built ROM {sha256(rom)} differs from data/homerunart32/digests.json")
        write_atomic(args.out, rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom, assets), indent=1))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed in {len(regions(assets))} regions); matches "
              "data/homerunart32/digests.json")


if __name__ == "__main__":
    main()
