#!/usr/bin/env python3
"""The mode-menu art as one immutable value, checked once: data/modeart32/modeassets.json.

tools/modeart32_convert.py writes the file and tools/build_modeart32.py reads it. Building a
ModeAssets, from the converter or from the file, validates every field before any tool uses a
byte of it; nothing downstream checks again.

The three mode menus (main, Championship, Exhibition) share one 256x240 background, palette and
attribute table. They differ only inside the declared spans: one row segment per text row, the
union of all three menus' text on that row. Every menu's run list rewrites every span, so a
switch from any menu to any other leaves exactly the target menu on screen and never touches a
cell outside the spans or an attribute byte.

Format modeassets/1, in this key order:
  format, chr_bank         "modeassets/1", 6
  tiles_used, font_glyphs  CHR tiles defined; the stock CHR $00 glyph ids the text uses
  png_sha256               SHA-256 of the converted art/modeart32/out/scenes/mode.png
  chr                      4096 bytes, CHR bank $06; font glyphs are copies of CHR $00 tiles
  nametable, attributes    960 + 64 bytes: the main menu exactly as scene 6 draws it
  palette                  32 bytes, BG then sprite palettes, one shared backdrop
  spans                    [{row, col, width}], one per text row, rows ascending
  runs                     {main, championship, exhibition}: each menu's stock $C840 list
  cursor                   18 bytes, the stock (x, y) table: main x3, exhibition x3, main x3
Byte fields are lowercase hex. A run list holds one raw run per span, in span order:
address low byte, $40 | address high byte, the span's tiles, then $FE, or $FF after the last.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import menu32_convert as menu
from menu32_convert import AssetError

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "data/modeart32/modeassets.json"
FORMAT = "modeassets/1"
MODE_CHR = 0x06
MENUS = ("main", "championship", "exhibition")
LABELS = {
    "main": ("CHAMPIONSHIP SERIES", "EXHIBITION MODE", "POWER ANALYSIS"),
    "championship": ("CONTINUE PLAY", "LIST OF TEAMS", "START NEW SERIES"),
    "exhibition": ("1P", "2P", "WATCH GAME"),
}
ROWS, COLUMNS = 30, 32
MAX_RUN = 32              # tiles per run; $C863 copies runs to $06B5 unchecked, and 43 reach $06E0
RAW = 0x40                # $C840 run flag: copy bytes as tile ids (bit 7, the wide font, stays clear)
MORE, END = 0xFE, 0xFF    # run terminators: another run follows, or the list ends
CURSOR_X_MAX = 240        # the 16x16 ball stays on screen without wrapping
CURSOR_Y_MAX = 223
SIZES = {"chr": 0x1000, "nametable": 960, "attributes": 64, "palette": 32, "cursor": 18}
KEYS = ("format", "chr_bank", "tiles_used", "font_glyphs", "png_sha256", "chr", "nametable", "attributes",
        "palette", "spans", "runs", "cursor")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def supported_color(value):
    try:
        menu.nes_color(f"{value:02X}")
    except AssetError:
        return False
    return True


@dataclass(frozen=True)
class Span:
    """Cells every menu rewrites on one nametable row."""
    row: int
    col: int
    width: int

    def __post_init__(self):
        if not all(is_int(v) for v in (self.row, self.col, self.width)):
            raise AssetError("span row, col and width must be integers")
        if not (0 <= self.row < ROWS and 0 <= self.col and 1 <= self.width <= MAX_RUN
                and self.col + self.width <= COLUMNS):
            raise AssetError(f"span at row {self.row} col {self.col} width {self.width} must hold 1-{MAX_RUN} "
                             "tiles inside one row of nametable $2000")

    @property
    def address(self):
        return 0x2000 + COLUMNS * self.row + self.col

    @property
    def cells(self):
        start = COLUMNS * self.row + self.col
        return slice(start, start + self.width)


@dataclass(frozen=True)
class MenuText:
    """What one menu shows in each span, in span order."""
    name: str
    tiles: tuple


@dataclass(frozen=True)
class ModeAssets:
    tiles_used: int
    font_glyphs: tuple
    png_sha256: str
    chr: bytes
    nametable: bytes
    attributes: bytes
    palette: bytes
    spans: tuple
    menus: tuple
    cursor: bytes

    def __post_init__(self):
        for key, size in SIZES.items():
            value = getattr(self, key)
            if not isinstance(value, bytes) or len(value) != size:
                raise AssetError(f"{key} must be exactly {size} bytes")
        glyphs = self.font_glyphs
        if (not isinstance(glyphs, tuple) or not all(is_int(g) for g in glyphs) or list(glyphs) != sorted(set(glyphs))
                or menu.BLANK not in glyphs or not all(0x20 <= g < 0x7F for g in glyphs)):
            raise AssetError("font_glyphs must be ascending unique printable ASCII tile ids including the blank $20")
        defined = set(glyphs) | {i for i in range(256) if any(self.chr[16 * i:16 * i + 16])}
        if not is_int(self.tiles_used) or self.tiles_used != len(defined):
            raise AssetError(f"tiles_used must count the {len(defined)} defined CHR tiles")
        if not set(self.nametable) <= defined:
            raise AssetError("the nametable uses a tile the CHR bank leaves undefined")
        if not isinstance(self.png_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.png_sha256):
            raise AssetError("png_sha256 must be a lowercase SHA-256")
        if not all(supported_color(c) for c in self.palette) or len(set(self.palette[::4])) != 1:
            raise AssetError("palette must hold supported NES colors sharing one backdrop")
        spans = check_spans(self.spans)
        if (not isinstance(self.menus, tuple) or not all(isinstance(m, MenuText) for m in self.menus)
                or tuple(m.name for m in self.menus) != MENUS):
            raise AssetError(f"menus must be {', '.join(MENUS)}, in that order")
        for item in self.menus:
            if (not isinstance(item.tiles, tuple) or len(item.tiles) != len(spans)
                    or not all(isinstance(t, bytes) and len(t) == s.width for t, s in zip(item.tiles, spans))):
                raise AssetError(f"{item.name}: one run of exactly the span's width per span")
            if not set(b"".join(item.tiles)) <= set(glyphs):
                raise AssetError(f"{item.name}: run tiles must be font glyphs")
            shown = b" ".join(item.tiles).decode("ascii")
            for label in LABELS[item.name]:
                if len(re.findall(rf"(?<![A-Z0-9]){re.escape(label)}(?![A-Z0-9])", shown)) != 1:
                    raise AssetError(f"{item.name} must show {label!r} exactly once")
        main = self.menus[0]
        if any(self.nametable[s.cells] != t for s, t in zip(spans, main.tiles)):
            raise AssetError("the nametable must be the main menu: its span cells must equal the main runs")
        entries = [self.cursor[i:i + 2] for i in range(0, 18, 2)]
        if any(x > CURSOR_X_MAX or y > CURSOR_Y_MAX for x, y in entries):
            raise AssetError(f"cursor entries must stay within x <= {CURSOR_X_MAX}, y <= {CURSOR_Y_MAX}")
        if entries[6:] != entries[:3]:
            raise AssetError("cursor entries 6-8 must repeat the main entries 0-2, as the stock table does")

    def menu(self, name):
        return self.menus[MENUS.index(name)]

    def screen(self, name):
        """The 1 KB nametable and attributes while `name` is showing."""
        nametable = bytearray(self.nametable)
        for span, tiles in zip(self.spans, self.menu(name).tiles):
            nametable[span.cells] = tiles
        return bytes(nametable) + self.attributes

    def run_list(self, name):
        data = bytearray()
        for i, (span, tiles) in enumerate(zip(self.spans, self.menu(name).tiles)):
            data += bytes((span.address & 0xFF, RAW | span.address >> 8)) + tiles
            data.append(END if i == len(self.spans) - 1 else MORE)
        return bytes(data)

    def cursor_origin(self, entry):
        return self.cursor[2 * entry], self.cursor[2 * entry + 1]

    def record(self):
        return {
            "format": FORMAT,
            "chr_bank": MODE_CHR,
            "tiles_used": self.tiles_used,
            "font_glyphs": list(self.font_glyphs),
            "png_sha256": self.png_sha256,
            "chr": self.chr.hex(),
            "nametable": self.nametable.hex(),
            "attributes": self.attributes.hex(),
            "palette": self.palette.hex(),
            "spans": [{"row": s.row, "col": s.col, "width": s.width} for s in self.spans],
            "runs": {name: self.run_list(name).hex() for name in MENUS},
            "cursor": self.cursor.hex(),
        }

    def dumps(self):
        return json.dumps(self.record(), indent=1) + "\n"

    @classmethod
    def parse(cls, record):
        if not isinstance(record, dict) or set(record) != set(KEYS):
            raise AssetError(f"{FORMAT} must hold exactly the keys {', '.join(KEYS)}")
        if record["format"] != FORMAT or not is_int(record["chr_bank"]) or record["chr_bank"] != MODE_CHR:
            raise AssetError(f"expected {FORMAT} art for CHR ${MODE_CHR:02X}")
        if not isinstance(record["spans"], list) or not all(
                isinstance(s, dict) and set(s) == {"row", "col", "width"} for s in record["spans"]):
            raise AssetError("spans must be a list of {row, col, width}")
        spans = check_spans(tuple(Span(s["row"], s["col"], s["width"]) for s in record["spans"]))
        runs = record["runs"]
        if not isinstance(runs, dict) or set(runs) != set(MENUS):
            raise AssetError(f"runs must hold exactly {', '.join(MENUS)}")
        glyphs = record["font_glyphs"]
        return cls(
            tiles_used=record["tiles_used"],
            font_glyphs=tuple(glyphs) if isinstance(glyphs, list) else glyphs,
            png_sha256=record["png_sha256"],
            chr=hex_field(record, "chr"),
            nametable=hex_field(record, "nametable"),
            attributes=hex_field(record, "attributes"),
            palette=hex_field(record, "palette"),
            spans=spans,
            menus=tuple(MenuText(name, read_runs(name, hex_field(runs, name), spans)) for name in MENUS),
            cursor=hex_field(record, "cursor"),
        )

    @classmethod
    def load(cls, path=ASSETS):
        return cls.parse(json.loads(Path(path).read_text()))


def check_spans(spans):
    if (not isinstance(spans, tuple) or not 1 <= len(spans) <= ROWS or not all(isinstance(s, Span) for s in spans)
            or [s.row for s in spans] != sorted({s.row for s in spans})):
        raise AssetError(f"spans must be 1-{ROWS} rows in ascending order, one span per row")
    return spans


def hex_field(record, key):
    text = record[key]
    if not isinstance(text, str) or not re.fullmatch(r"(?:[0-9a-f]{2})*", text):
        raise AssetError(f"{key} must be a lowercase hex string")
    data = bytes.fromhex(text)
    if key in SIZES and len(data) != SIZES[key]:
        raise AssetError(f"{key} must be exactly {SIZES[key]} bytes, not {len(data)}")
    return data


def read_runs(name, data, spans):
    """One menu's $C840 list -> its tiles per span, rejecting anything the stock walker would misdraw."""
    runs, pos = [], 0
    while True:
        where = f"{name} run {len(runs)}"
        if pos + 3 > len(data):
            raise AssetError(f"{where}: truncated; a run needs an address, a tile and a terminator")
        low, high = data[pos], data[pos + 1]
        if high & 0xC0 != RAW or not 0x20 <= high & 0x3F <= 0x23:
            raise AssetError(f"{where}: flags/address byte ${high:02X} is not a narrow raw run in nametable $2000")
        address = (high & 0x3F) << 8 | low
        end = pos + 2
        while end < len(data) and data[end] < MORE:
            end += 1
        if end == len(data):
            raise AssetError(f"{where}: no $FE or $FF terminator")
        tiles = data[pos + 2:end]
        if not 1 <= len(tiles) <= MAX_RUN:
            raise AssetError(f"{where}: {len(tiles)} tiles; runs hold 1-{MAX_RUN}")
        if address + len(tiles) > 0x2000 + ROWS * COLUMNS or (address & 31) + len(tiles) > COLUMNS:
            raise AssetError(f"{where}: ${address:04X}+{len(tiles)} leaves its nametable row")
        runs.append((address, tiles))
        pos = end + 1
        if data[end] == END:
            break
    if pos != len(data):
        raise AssetError(f"{name}: {len(data) - pos} bytes follow the $FF terminator")
    if [(a, len(t)) for a, t in runs] != [(s.address, s.width) for s in spans]:
        raise AssetError(f"{name}: runs must cover exactly the declared spans, in order")
    return tuple(t for _, t in runs)
