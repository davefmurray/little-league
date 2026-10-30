#!/usr/bin/env python3
"""The HOME RUN celebration as one validated domain model.

The stock home run is states 2 and 3 of scene $05. State 2 ($D755) loads background palette record $0E
(fixed $F8C0) through $C1A4 and draws map $24 through metatile set $15 with $C5C4; state 3 ($D77B) flips
CHR1 between $D793[0] = $04 and $D793[1] = $15 every 8 frames until song $0A ends. So the celebration is two
frames that share one nametable, one attribute table and one palette record: frame a is CHR $04, frame b is
CHR $15. Nothing here changes code; the stage only redraws that data.

Sources (tracked, art/homerunart32/):
  layout.json   homerunart32-layout/1: the pxl scene of each frame, the backdrop and the four background
                palettes, in the order the converter tries them.
  cast.json     homerunart32-cast/1: the approved stockart32 parts the scene stamps, poses derived from an
                approved character on another intro panel with their reviewed mask, and per-frame placements.
                A placement shared by both frames ("ab") shows identical part pixels in a and b: still by
                construction.

Read from the input ROM through the loader's own tables, never asserted: where map $24, the shared maps $2A
(VICTORY) and $33 (split screen), the set $15 planes and record $0E live, and which metatile ids the shared
maps use (protected_ids).

Generated (build/homerunart32/homerunassets.json, homerunassets/1, written by
tools/homerunart32_convert.py, read by tools/build_homerunart32.py): HomerunAssets, validated on its own;
build_homerunart32.check_runtime checks it against the input ROM.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import menu32_convert as menu
from menu32_convert import AssetError
from build_draw32 import read

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art/homerunart32"
LAYOUT_FORMAT = "homerunart32-layout/1"
CAST_FORMAT = "homerunart32-cast/1"
ASSETS_FORMAT = "homerunassets/1"
PART_MANIFEST = "art/stockart32/characters.json"

FIXED = 15
FRAMES = ("a", "b")
FRAME_CHR = {"a": 0x04, "b": 0x15}         # $D793: what state 3 stores in $25 per phase
SET_TABLE, MAP_TABLE = 0xFAF0, 0xFB11      # $C5C4: 3-byte (pointer, bank) entries indexed by the inline byte
HR_SET, HR_MAP = 0x15, 0x24                # state 2: JSR $C5C4 .byte $15,$24,$04,$20
SHARED_MAPS = {"VICTORY": 0x2A, "split screen": 0x33}    # the other set-$15 screens (bank 5 $ACC6, $AC6D)
PALETTE_POINTERS, HR_RECORD = 0xFFF0, 0x0E               # $C1A4 and the record state 2 loads
MAP_IDS, ATTRIBUTE_BYTES, PLANE_STRIDE = 240, 64, 0x100  # 16x15 metatile ids, then attributes; TL/TR/BL/BR
TILE_PAIRS = 256                           # CHR $04 and CHR $15 hold 256 patterns each, one id for both
SCREEN_SIZE = (256, 240)
CHR_SIZE = 0x1000
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
SCENE = re.compile(r"[a-z][a-z0-9_]*")              # pxl scene() names, also the render file names
HEX2 = re.compile(r"[0-9A-F]{2}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def fail(where, message):
    raise AssetError(f"{where}: {message}")


def keys(value, where, allowed, required=None):
    required = allowed if required is None else required
    if not isinstance(value, dict):
        fail(where, "must be an object")
    if not set(required) <= set(value) <= set(allowed):
        fail(where, f"keys must be among {', '.join(sorted(allowed))}; missing {sorted(set(required) - set(value))}, "
                    f"unknown {sorted(set(value) - set(allowed))}")
    return value


def integer(value, where, low, high):
    if not is_int(value) or not low <= value <= high:
        fail(where, f"must be an integer from {low} to {high}")
    return value


def text(value, where):
    if not isinstance(value, str) or not value.strip():
        fail(where, "must be a non-empty string")
    return value


def color(value, where):
    if not isinstance(value, str) or not HEX2.fullmatch(value):
        fail(where, "must be an NES color, two uppercase hex digits")
    try:
        return menu.nes_color(value)
    except AssetError as exc:
        fail(where, str(exc))


def point(value, where, width, height):
    if not isinstance(value, list) or len(value) != 2:
        fail(where, "must be [x, y]")
    return integer(value[0], f"{where} x", 0, width - 1), integer(value[1], f"{where} y", 0, height - 1)


def box(value, where, width, height):
    """[x, y, w, h], positive and wholly inside a width x height space."""
    if not isinstance(value, list) or len(value) != 4:
        fail(where, "must be [x, y, w, h]")
    x, y = integer(value[0], f"{where} x", 0, width - 1), integer(value[1], f"{where} y", 0, height - 1)
    return x, y, integer(value[2], f"{where} w", 1, width - x), integer(value[3], f"{where} h", 1, height - y)



@dataclass(frozen=True)
class Layout:
    scenes: dict              # frame -> pxl scene name
    backdrop: int
    palettes: tuple           # four (color, color, color); the converter takes the first that fits a cell
    sha256: str

    @classmethod
    def parse(cls, data, digest):
        keys(data, "layout", {"format", "about", "scenes", "backdrop", "palettes"})
        if data["format"] != LAYOUT_FORMAT:
            fail("layout", f"expected format {LAYOUT_FORMAT}")
        text(data["about"], "layout about")
        keys(data["scenes"], "layout scenes", set(FRAMES))
        scenes = {f: text(data["scenes"][f], f"layout scenes {f}") for f in FRAMES}
        if not all(SCENE.fullmatch(s) for s in scenes.values()) or len(set(scenes.values())) != len(FRAMES):
            fail("layout scenes", "must be two distinct path-safe pxl scene names")
        backdrop = color(data["backdrop"], "layout backdrop")
        raw = data["palettes"]
        if not isinstance(raw, list) or len(raw) != 4:
            fail("layout palettes", "must list the four background palettes")
        palettes = []
        for i, p in enumerate(raw):
            if not isinstance(p, list) or len(p) != 3:
                fail(f"layout palettes[{i}]", "must hold three NES colors")
            colors = tuple(color(c, f"layout palettes[{i}][{j}]") for j, c in enumerate(p))
            shown = [menu.NES_RGB[c] for c in (backdrop, *colors)]
            if len(set(shown)) != 4:
                fail(f"layout palettes[{i}]", "its colors and the backdrop must show four distinct RGB values")
            palettes.append(colors)
        return cls(scenes, backdrop, tuple(palettes), digest)

    @classmethod
    def load(cls, path=ART / "layout.json"):
        raw = Path(path).read_bytes()
        return cls.parse(json.loads(raw), sha256(raw))

    def record(self):
        """The 16-byte background palette record $0E."""
        return b"".join(bytes((self.backdrop, *p)) for p in self.palettes)



@dataclass(frozen=True)
class Pose:
    """An approved character's rules applied to another intro panel, with that cut's own reviewed mask."""
    id: str
    base: str                 # the approved character whose crop, seeds, specks, colors and target it reuses
    panel: int
    drop: tuple               # replaces the base's drop boxes, crop space
    mask_sha256: str          # the reviewed silhouette (stockart32_parts.mask_sha256)
    png_sha256: str           # the reviewed part PNG


@dataclass(frozen=True)
class Placement:
    part: str
    frames: tuple             # ("a",), ("b",) or ("a", "b"): a shared placement is still by construction
    at: tuple
    area: tuple | None        # None: the whole part
    visible: tuple | None     # None: wherever the stamp lands on screen

    @property
    def still(self):
        return self.frames == FRAMES


@dataclass(frozen=True)
class Cast:
    poses: tuple
    placements: tuple
    sha256: str

    @property
    def parts(self):
        """Every part id the scene stamps, in first-placement order."""
        return tuple(dict.fromkeys(p.part for p in self.placements))

    def in_frame(self, frame):
        return tuple(p for p in self.placements if frame in p.frames)

    @classmethod
    def parse(cls, data, digest, approved):
        """`approved` maps each stockart32 part id to its parsed Character or Crowd."""
        keys(data, "cast", {"format", "about", "approved", "poses", "placements"})
        if data["format"] != CAST_FORMAT:
            fail("cast", f"expected format {CAST_FORMAT}")
        text(data["about"], "cast about")
        if data["approved"] != PART_MANIFEST:
            fail("cast approved", f"must be {PART_MANIFEST}, the reviewed part source")
        for name in ("poses", "placements"):
            if not isinstance(data[name], list):
                fail(f"cast {name}", "must be a list")
        poses, sizes = [], {pid: spec.size for pid, spec in approved.items()}
        for i, entry in enumerate(data["poses"]):
            at = f"cast poses[{i}]"
            keys(entry, at, {"id", "from", "panel", "drop", "drop_why", "mask_sha256", "png_sha256", "why"},
                 {"id", "from", "panel", "mask_sha256", "png_sha256", "why"})
            pid = entry["id"]
            if not isinstance(pid, str) or len(pid) > 32 or not ID.fullmatch(pid):
                fail(f"{at} id", "must be a path-safe lowercase name, at most 32 characters")
            if pid in sizes:
                fail(f"{at} id", f"{pid!r} is already a part")
            base = approved.get(entry["from"]) if isinstance(entry["from"], str) else None
            if base is None or not hasattr(base, "panel"):
                fail(f"{at} from", "must name an approved character")
            panel = integer(entry["panel"], f"{at} panel", 0, 6)
            if panel == base.panel:
                fail(f"{at} panel", f"must differ from {entry['from']}'s own panel {base.panel}")
            w, h = base.size
            if not isinstance(entry.get("drop", []), list):
                fail(f"{at} drop", "must be a list of [x, y, w, h]")
            drop = tuple(box(b, f"{at} drop[{k}]", w, h) for k, b in enumerate(entry.get("drop", [])))
            if drop or "drop_why" in entry:
                text(entry.get("drop_why"), f"{at} drop_why")
            for name in ("mask_sha256", "png_sha256"):
                if not isinstance(entry[name], str) or not HEX64.fullmatch(entry[name]):
                    fail(f"{at} {name}", "must be a lowercase SHA-256")
            text(entry["why"], f"{at} why")
            poses.append(Pose(pid, entry["from"], panel, drop, entry["mask_sha256"], entry["png_sha256"]))
            sizes[pid] = base.size
        placements = []
        for i, entry in enumerate(data["placements"]):
            at = f"cast placements[{i}]"
            keys(entry, at, {"part", "frames", "at", "area", "visible", "why"}, {"part", "frames", "at"})
            if entry["part"] not in sizes:
                fail(f"{at} part", f"names no approved part or pose: {entry['part']!r}")
            if entry["frames"] not in ("a", "b", "ab"):
                fail(f"{at} frames", "must be 'a', 'b' or 'ab'")
            area = box(entry["area"], f"{at} area", *sizes[entry["part"]]) if "area" in entry else None
            visible = box(entry["visible"], f"{at} visible", *SCREEN_SIZE) if "visible" in entry else None
            if visible is not None or "why" in entry:
                text(entry.get("why"), f"{at} why")
            placements.append(Placement(entry["part"], tuple(entry["frames"]), point(entry["at"], f"{at} at",
                                                                                      *SCREEN_SIZE), area, visible))
        cast = cls(tuple(poses), tuple(placements), digest)
        missing = [f for f in FRAMES if not cast.in_frame(f)]
        if missing:
            fail("cast placements", f"frame {missing[0]} stamps nothing")
        unplaced = sorted({p.id for p in poses} - set(cast.parts))
        if unplaced:
            fail("cast placements", f"place every pose; {', '.join(unplaced)} never appear")
        return cast

    @classmethod
    def load(cls, approved, path=ART / "cast.json"):
        raw = Path(path).read_bytes()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssetError(f"cast: not JSON ({exc})") from None
        return cls.parse(data, sha256(raw), approved)



def table_entry(rom, table, arg):
    """(CPU address, PRG bank) the $C5C4 table entry for inline byte `arg` points at."""
    lo, hi, bank = read(rom, FIXED, table + arg, 3)
    return lo | hi << 8, bank


def planes_location(rom, set_arg=HR_SET):
    return table_entry(rom, SET_TABLE, set_arg)


def map_location(rom, map_arg):
    return table_entry(rom, MAP_TABLE, map_arg)


def decode_screen(rom, set_arg, map_arg):
    """What $C5C4 writes for (set, map): (metatile map, attributes, 960 tile ids), read through the ROM's own
    tables. Metatile k is planes[k], [k+$100], [k+$200], [k+$300] at TL, TR, BL, BR."""
    planes_at, planes_bank = planes_location(rom, set_arg)
    map_at, map_bank = map_location(rom, map_arg)
    metamap = read(rom, map_bank, map_at, MAP_IDS)
    attributes = read(rom, map_bank, map_at + MAP_IDS, ATTRIBUTE_BYTES)
    planes = [read(rom, planes_bank, planes_at + PLANE_STRIDE * q, 0x100) for q in range(4)]
    nametable = bytearray(960)
    for i, k in enumerate(metamap):
        row, col = 2 * (i // 16), 2 * (i % 16)
        for q in range(4):
            nametable[32 * (row + (q >> 1)) + col + (q & 1)] = planes[q][k]
    return metamap, attributes, bytes(nametable)


def protected_ids(rom):
    """Metatile ids the shared set-$15 maps (VICTORY, split screen) draw: their planes are never redrawn."""
    ids = set()
    for map_arg in SHARED_MAPS.values():
        at, bank = map_location(rom, map_arg)
        ids |= set(read(rom, bank, at, MAP_IDS))
    return frozenset(ids)


def record_location(rom, record=HR_RECORD):
    """The CPU address of background palette record `record`, as $C1A4 computes it."""
    base = int.from_bytes(read(rom, FIXED, PALETTE_POINTERS + (record >> 6), 2), "little")
    return base + ((record << 4) & 0xFF) + (((record >> 4) & 7) << 8) + 1


def attr_palette(attributes, col, row):
    offset, shift = menu.attr_slot(col, row)
    return (attributes[offset] >> shift) & 3


def picture(chr_bank, nametable, attributes, palette):
    """RGB rows of a background as the PPU shows it with `chr_bank` at $1000 and record `palette`."""
    rows = []
    for y in range(240):
        row = []
        for x in range(256):
            tile = nametable[32 * (y // 8) + x // 8]
            v = menu.decode(chr_bank[16 * tile:16 * tile + 16])[y % 8][x % 8]
            p = attr_palette(attributes, x // 8, y // 8)
            row.append(menu.NES_RGB[palette[4 * p + v] if v else palette[0]])
        rows.append(row)
    return rows



def supported(value):
    try:
        menu.nes_color(f"{value:02X}")
    except (AssetError, TypeError, ValueError):
        return False
    return is_int(value)


@dataclass(frozen=True)
class HomerunAssets:
    layout_sha256: str
    renders: dict             # frame -> SHA-256 of the pinned pxl render it was converted from
    tile_pairs: int           # ids 0..tile_pairs-1 each hold one (frame a, frame b) pattern pair
    chr_a: bytes              # CHR $04
    chr_b: bytes              # CHR $15
    metamap: bytes            # map $24: 240 metatile ids, 16x15 row-major
    attributes: bytes         # its 64 attribute bytes
    planes: dict              # metatile id -> (TL, TR, BL, BR) tile ids, ids ascending
    palette: bytes            # background palette record $0E

    def __post_init__(self):
        if not isinstance(self.layout_sha256, str) or not HEX64.fullmatch(self.layout_sha256):
            raise AssetError("layout_sha256 must be a lowercase SHA-256")
        if (not isinstance(self.renders, dict) or list(self.renders) != list(FRAMES)
                or not all(isinstance(v, str) and HEX64.fullmatch(v) for v in self.renders.values())):
            raise AssetError("renders must give each frame's render SHA-256, a then b")
        for name, size in (("chr_a", CHR_SIZE), ("chr_b", CHR_SIZE), ("metamap", MAP_IDS),
                           ("attributes", ATTRIBUTE_BYTES), ("palette", 16)):
            if not isinstance(getattr(self, name), bytes) or len(getattr(self, name)) != size:
                raise AssetError(f"{name} must be exactly {size} bytes")
        if not is_int(self.tile_pairs) or not 1 <= self.tile_pairs <= TILE_PAIRS:
            raise AssetError(f"tile_pairs must be 1-{TILE_PAIRS}: CHR $04 and $15 hold {TILE_PAIRS} patterns")
        used = 16 * self.tile_pairs
        if any(self.chr_a[used:]) or any(self.chr_b[used:]):
            raise AssetError(f"CHR ids from ${self.tile_pairs:02X} on must stay blank: only {self.tile_pairs} pairs "
                             "are allocated")
        pairs = {(self.chr_a[16 * t:16 * t + 16], self.chr_b[16 * t:16 * t + 16]) for t in range(self.tile_pairs)}
        if len(pairs) != self.tile_pairs:
            raise AssetError("each tile id must hold a distinct (frame a, frame b) pattern pair")
        if len(set(self.palette[::4])) != 1 or not all(supported(c) for c in self.palette):
            raise AssetError("palette must hold supported NES colors sharing one backdrop")
        ids = list(self.planes) if isinstance(self.planes, dict) else None
        if not ids or ids != sorted(ids) or not all(is_int(k) and 0 <= k <= 0xFF for k in ids):
            raise AssetError("planes must map ascending metatile ids $00-$FF to tile quads")
        quads = list(self.planes.values())
        if (not all(isinstance(q, tuple) and len(q) == 4 and all(is_int(t) and 0 <= t < self.tile_pairs for t in q)
                    for q in quads) or len(set(quads)) != len(quads)):
            raise AssetError("each metatile must be one distinct (TL, TR, BL, BR) quad of allocated tile ids")
        if set(self.metamap) != set(ids):
            raise AssetError("the metatile map must use exactly the defined metatile ids")
        if set(self.nametable()) != set(range(self.tile_pairs)):
            raise AssetError("the screen must show every allocated tile pair and no other id")

    def nametable(self):
        nametable = bytearray(960)
        for i, k in enumerate(self.metamap):
            row, col = 2 * (i // 16), 2 * (i % 16)
            for q, tile in enumerate(self.planes[k]):
                nametable[32 * (row + (q >> 1)) + col + (q & 1)] = tile
        return bytes(nametable)

    def chr(self, frame):
        return {"a": self.chr_a, "b": self.chr_b}[frame]

    @property
    def animated_pairs(self):
        return sum(self.chr_a[16 * t:16 * t + 16] != self.chr_b[16 * t:16 * t + 16] for t in range(self.tile_pairs))

    def record(self):
        return {
            "format": ASSETS_FORMAT,
            "layout_sha256": self.layout_sha256,
            "renders": dict(self.renders),
            "tile_pairs": self.tile_pairs,
            "chr_a": self.chr_a.hex(),
            "chr_b": self.chr_b.hex(),
            "metamap": self.metamap.hex(),
            "attributes": self.attributes.hex(),
            "planes": {f"{k:02X}": [f"{t:02X}" for t in q] for k, q in self.planes.items()},
            "palette": self.palette.hex(),
        }

    def dumps(self):
        return json.dumps(self.record(), indent=1) + "\n"

    @classmethod
    def parse(cls, record):
        if not isinstance(record, dict) or list(record) != list(ASSET_KEYS):
            raise AssetError(f"{ASSETS_FORMAT} must hold exactly the keys {', '.join(ASSET_KEYS)}, in that order")
        if record["format"] != ASSETS_FORMAT:
            raise AssetError(f"expected {ASSETS_FORMAT}")
        planes = record["planes"]
        if not isinstance(planes, dict) or not all(isinstance(q, list) and len(q) == 4 for q in planes.values()):
            raise AssetError("planes must map metatile ids to four tile ids")
        return cls(layout_sha256=record["layout_sha256"], renders=record["renders"], tile_pairs=record["tile_pairs"],
                   chr_a=hex_bytes(record, "chr_a"), chr_b=hex_bytes(record, "chr_b"),
                   metamap=hex_bytes(record, "metamap"), attributes=hex_bytes(record, "attributes"),
                   planes={hex_id(k, "planes"): tuple(hex_id(t, f"planes {k}") for t in q) for k, q in planes.items()},
                   palette=hex_bytes(record, "palette"))


ASSET_KEYS = ("format", "layout_sha256", "renders", "tile_pairs", "chr_a", "chr_b", "metamap", "attributes", "planes",
              "palette")


def hex_id(value, where):
    if not isinstance(value, str) or not HEX2.fullmatch(value):
        raise AssetError(f"{where}: {value!r} must be two uppercase hex digits")
    return int(value, 16)


def hex_bytes(record, key):
    value = record[key]
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{2})*", value):
        raise AssetError(f"{key} must be a lowercase hex string")
    return bytes.fromhex(value)
