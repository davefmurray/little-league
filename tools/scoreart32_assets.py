#!/usr/bin/env python3
"""The scoreboard art as one immutable value, checked once: data/scoreart32/scoreassets.json.

tools/scoreart32_convert.py writes the file and tools/build_scoreart32.py reads it. Building a
ScoreAssets, from the converter or from the file, validates every field before any tool uses a
byte of it; nothing downstream checks again.

The stage keeps the stock scoreboard writer in bank 4: $B40E draws the inning header, $B482 a
side's line score and R H E, $B5C6 the team names and statistics. The writer puts every live
value on screen by tile id over the background that scene $0A uploads first, so 78 ids of CHR
bank $05 keep their stock meaning (GLYPHS) and the art owns the other 178. The stage moves the
writer's rows, never its columns (GEOMETRY, against STOCK_GEOMETRY). Board and drawn() state which
tiles the writer puts where, from the stock rules: values mod 100, a big glyph below 10, the X of a
side that did not bat, a walk-off's last digit and narrow X, three inning-header pages, E always 0.

The background leaves blank every cell the writer can touch and every cell under a team-name
sprite, so a cell the writer skips (an unplayed half-inning, the cells after an X) shows nothing.
Each 16x16 attribute cell holding writer cells uses palette 0, the palette the glyphs are drawn in.
The header blank $E8 is blank too, and every blank background cell uses it, never a digit quarter
that happens to be empty; a background tile equal to a glyph uses that glyph's lowest id. Every
other background tile is unique to the art.

Format scoreassets/1, in this key order:
  format, chr_bank         "scoreassets/1", 5
  tiles_used               CHR tiles defined: the 78 glyphs and the art's own tiles
  sources                  {art-relative path: SHA-256} of SOURCES: the pxl source and pin, the
                           layout and the five PNGs the conversion reads
  chr                      4096 bytes, CHR bank $05; a tile that is neither a glyph nor drawn is zero
  nametable, attributes    960 + 64 bytes: the background scene $0A uploads
  palette                  32 bytes, BG then sprite palettes, one shared backdrop
Byte fields are lowercase hex.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

import menu32_convert as menu
from menu32_convert import AssetError

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "data/scoreart32/scoreassets.json"
FORMAT = "scoreassets/1"
SCORE_CHR = 0x05
GLYPH_PALETTE = 0
ROWS, COLUMNS = 30, 32
SIZES = {"chr": 0x1000, "nametable": ROWS * COLUMNS, "attributes": 64, "palette": 32}
KEYS = ("format", "chr_bank", "tiles_used", "sources", "chr", "nametable", "attributes", "palette")
SOURCES = ("PXL.json", "layout.json", "out/scenes/score.png", "out/sprites/big.png", "out/sprites/head.png",
           "out/sprites/narrow.png", "out/sprites/sep.png", "score32.px.js")

# ---------------------------------------------------------------- runtime glyph contract

VALUES = "0123456789X"        # value glyphs; X (10) marks a side that did not bat, or ends a walk-off
X = VALUES.index("X")
SEPARATOR = 0x01              # between two statistics, on both of their rows
BIG, NARROW = 0x40, 0x6C      # big value v: BIG + 4v + (TL, TR, BL, BR); narrow v: NARROW + 2v + (top, bottom)
HEADER = {"8": 0xDD, "9": 0xDE, "0": 0xDF, "1": 0xE1, "2": 0xE2, "3": 0xE3, "4": 0xE4, "5": 0xE5,
          "6": 0xE6, "7": 0xE7, " ": 0xE8}
HEAD_ORDER = "0123456789 "    # left to right in the art's 88x8 head sprite
BLANK = HEADER[" "]


def big(v):
    return tuple(BIG + 4 * v + q for q in range(4))


def narrow(v):
    return NARROW + 2 * v, NARROW + 2 * v + 1


GLYPHS = {SEPARATOR: "separator",
          **{t: f"big {VALUES[v]} {q}" for v in range(11) for q, t in zip(("TL", "TR", "BL", "BR"), big(v))},
          **{t: f"narrow {VALUES[v]} {h}" for v in range(11) for h, t in zip(("top", "bottom"), narrow(v))},
          **{t: f"header {ch!r}" for ch, t in HEADER.items()}}
assert len(GLYPHS) == 78

# ---------------------------------------------------------------- geometry

HEADER_COL, HEADER_WIDTH = 8, 14          # seven two-tile inning headings at columns 8-21
LINE_COL, LINE_WIDTH, RHE_COL = 8, 14, 24  # up to seven line-score cells from column 8; R H E at columns 24-29
STAT_COL, STATS, STAT_PITCH = 10, 7, 3    # AB HIT HR K BB SAC DP at columns 10-29, separators between
NAME_COL, NAME_WIDTH = 2, 5               # team-name sprites from x = 16, five 8-pixel characters


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def nt_address(col, row):
    return 0x2000 + COLUMNS * row + col


@dataclass(frozen=True)
class ScoreGeometry:
    """The writer's rows in nametable tiles. Bank 4's header address operand ($B41D), line and statistic
    row tables ($B54A, $B552) and name-sprite Y table ($B5BE) all follow from these three facts: names sit
    level with their value rows, in label order side 0 line, side 1 line, side 0 stats, side 1 stats."""
    header_row: int
    line_rows: tuple          # top row of each side's two-row line score and R H E, side 0 first
    stat_rows: tuple          # top row of each side's two-row statistics, side 0 first

    def __post_init__(self):
        if (not is_int(self.header_row) or not isinstance(self.line_rows, tuple) or len(self.line_rows) != 2
                or not isinstance(self.stat_rows, tuple) or len(self.stat_rows) != 2
                or not all(is_int(r) for r in self.value_rows)):
            raise ValueError("geometry is a header row and two line and two statistic rows")
        if not 8 <= self.header_row <= 15:
            raise ValueError("the header row must keep the $21 high byte of the stock $2128 address")
        rows = [self.header_row] + [r + d for r in self.value_rows for d in (0, 1)]
        if len(set(rows)) != len(rows) or not all(1 <= r < ROWS for r in rows):
            raise ValueError("the header and the four two-row value bands must not overlap or leave the screen")

    @property
    def value_rows(self):
        return (*self.line_rows, *self.stat_rows)

    def header_operand(self):
        return bytes((nt_address(HEADER_COL, self.header_row) & 0xFF,))

    def line_table(self):
        return self._rows(self.line_rows, LINE_COL)

    def stat_table(self):
        return self._rows(self.stat_rows, STAT_COL)

    def name_table(self):
        return bytes(8 * row - 1 for row in self.value_rows)

    @staticmethod
    def _rows(rows, col):
        return b"".join(nt_address(col, row + d).to_bytes(2, "big") for row in rows for d in (0, 1))

    def writer_cells(self):
        """Every (col, row) the stock writer can draw."""
        cells = {(HEADER_COL + i, self.header_row) for i in range(HEADER_WIDTH)}
        for row in self.line_rows:
            for r in (row, row + 1):
                cells |= {(LINE_COL + i, r) for i in range(LINE_WIDTH)} | {(RHE_COL + i, r) for i in range(6)}
        for row in self.stat_rows:
            for r in (row, row + 1):
                cells |= {(STAT_COL + i, r) for i in range(STAT_PITCH * STATS - 1)}
        return frozenset(cells)

    def name_cells(self):
        return frozenset((NAME_COL + i, row + d) for row in self.value_rows for d in (0, 1) for i in range(NAME_WIDTH))

    def glyph_attribute_cells(self):
        return frozenset((col // 2, row // 2) for col, row in self.writer_cells())


STOCK_GEOMETRY = ScoreGeometry(header_row=9, line_rows=(10, 12), stat_rows=(18, 20))
GEOMETRY = ScoreGeometry(header_row=8, line_rows=(9, 11), stat_rows=(15, 17))

# ---------------------------------------------------------------- what the writer draws

LINE_BYTES = 42               # $06F6-$071F, runs per half-inning
MAX_HALVES = 41               # the last entry of the stock page table $B42E
HEADERS = {0: " 1 2 3 4 5 6 7", 14: " 8 91011121314", 28: "15161718      "}


def page(halves):
    """The first half-inning on the board, from the stock page table $B42E."""
    return 0 if halves <= 14 else 14 if halves <= 28 else 28


@dataclass(frozen=True)
class Board:
    """What the stock writer reads: $048A completed half-innings, the $06F6 runs per half-inning (bit 7
    marks an X), $048B/$048C runs and the $0738 statistics AB HIT HR K BB SAC DP. HIT also fills H."""
    halves: int
    line: bytes
    runs: tuple
    stats: tuple              # seven (side 0, side 1) pairs

    def __post_init__(self):
        values = [*self.runs, *(v for pair in self.stats for v in pair)]
        if (not is_int(self.halves) or not 1 <= self.halves <= MAX_HALVES or not isinstance(self.line, bytes)
                or len(self.line) != LINE_BYTES or len(self.runs) != 2 or len(self.stats) != STATS
                or not all(len(pair) == 2 for pair in self.stats)
                or not all(is_int(v) and 0 <= v <= 0xFF for v in values)):
            raise ValueError("a board is 1-41 halves, 42 line bytes, two runs and seven statistic pairs of bytes")


def big_tiles(v):
    tl, tr, bl, br = big(v)
    return (tl, tr), (bl, br)


def value_tiles(value):
    """Stock $B55A: a big glyph below 10; otherwise the tens and ones digits of value mod 100, narrow."""
    if value < 10:
        return big_tiles(value)
    tens, ones = value // 10 % 10, value % 10
    return (narrow(tens)[0], narrow(ones)[0]), (narrow(tens)[1], narrow(ones)[1])


def marker_tiles(value):
    """A line byte with bit 7 ($B49D): $80 is the big X ($B55E, past the two-digit test), $80+n the last digit
    of n and a narrow X."""
    n = value & 0x7F
    if not n:
        return big_tiles(X)
    digit = n % 10
    return (narrow(digit)[0], narrow(X)[0]), (narrow(digit)[1], narrow(X)[1])


def put(cells, col, row, tiles):
    (tl, tr), (bl, br) = tiles
    cells.update({(col, row): tl, (col + 1, row): tr, (col, row + 1): bl, (col + 1, row + 1): br})


def drawn(board, geometry=GEOMETRY):
    """(col, row) -> tile of every cell the stock writer draws for `board`. A side's line cells stop at
    the last completed half-inning on the board's page, or after its first X."""
    cells = {}
    first = page(board.halves)
    for i, ch in enumerate(HEADERS[first]):
        cells[(HEADER_COL + i, geometry.header_row)] = HEADER[ch]
    for side, row in enumerate(geometry.line_rows):
        col = LINE_COL
        for half in range(first + side, board.halves, 2):
            value = board.line[half]
            put(cells, col, row, marker_tiles(value) if value & 0x80 else value_tiles(value))
            col += 2
            if value & 0x80:
                break
        for k, value in enumerate((board.runs[side], board.stats[1][side], 0)):
            put(cells, RHE_COL + 2 * k, row, value_tiles(value))
    for side, row in enumerate(geometry.stat_rows):
        for k in range(STATS):
            col = STAT_COL + STAT_PITCH * k
            put(cells, col, row, value_tiles(board.stats[k][side]))
            if k < STATS - 1:
                cells[(col + 2, row)] = cells[(col + 2, row + 1)] = SEPARATOR
    return cells

# ---------------------------------------------------------------- the asset


def supported_color(value):
    try:
        menu.nes_color(f"{value:02X}")
    except AssetError:
        return False
    return True


def attribute(attributes, ax, ay):
    offset, shift = menu.attr_slot(2 * ax, 2 * ay)
    return (attributes[offset] >> shift) & 3


@dataclass(frozen=True)
class ScoreAssets:
    tiles_used: int
    sources: tuple            # ((art-relative path, SHA-256), ...) in path order
    chr: bytes
    nametable: bytes
    attributes: bytes
    palette: bytes

    def __post_init__(self):
        for key, size in SIZES.items():
            value = getattr(self, key)
            if not isinstance(value, bytes) or len(value) != size:
                raise AssetError(f"{key} must be exactly {size} bytes")
        self._check_palette()
        self._check_sources()
        self._check_glyphs()
        self._check_tiles()
        self._check_screen()

    def _check_palette(self):
        if not all(supported_color(c) for c in self.palette) or len(set(self.palette[::4])) != 1:
            raise AssetError("palette must hold supported NES colors sharing one backdrop")
        for i in range(8):
            colors = self.palette[4 * i + 1:4 * i + 4]
            if len(set(colors)) != 3 or self.palette[0] in colors:
                raise AssetError(f"palette {i} must hold three distinct colors besides the backdrop")

    def _check_sources(self):
        pairs = self.sources
        if (not isinstance(pairs, tuple) or not all(isinstance(p, tuple) and len(p) == 2
                                                    and all(isinstance(v, str) for v in p) for p in pairs)):
            raise AssetError("sources must map art-relative paths to SHA-256 digests")
        if tuple(path for path, _ in pairs) != SOURCES:
            raise AssetError(f"sources must name exactly {', '.join(SOURCES)}")
        if not all(re.fullmatch(r"[0-9a-f]{64}", digest) for _, digest in pairs):
            raise AssetError("source digests must be lowercase SHA-256")

    def _check_glyphs(self):
        if any(self.pattern(BLANK)):
            raise AssetError("the header blank $E8 must be blank")
        families = {"big": [big(v) for v in range(11)], "narrow": [narrow(v) for v in range(11)],
                    "header": [(HEADER[d],) for d in "0123456789"]}
        for name, glyphs in families.items():
            shapes = [b"".join(self.pattern(t) for t in tiles) for tiles in glyphs]
            if not all(any(shape) for shape in shapes):
                raise AssetError(f"every {name} glyph needs ink")
            if len(set(shapes)) != len(shapes):
                raise AssetError(f"the {name} glyphs must differ from each other")

    def _check_tiles(self):
        art = set(self.nametable) - set(GLYPHS)
        defined = set(GLYPHS) | art
        if any(self.pattern(t) != bytes(16) for t in range(256) if t not in defined):
            raise AssetError("a CHR tile that is neither a glyph nor drawn must be zero")
        if not is_int(self.tiles_used) or self.tiles_used != len(defined):
            raise AssetError(f"tiles_used must count the {len(defined)} glyph and drawn tiles")
        shapes = [self.pattern(t) for t in art]
        if len(set(shapes)) != len(shapes) or set(shapes) & {self.pattern(t) for t in GLYPHS}:
            raise AssetError("each art tile must be a pattern no other tile or glyph holds")
        first = {}
        for t in sorted(GLYPHS, key=lambda t: (t != BLANK, t)):
            first.setdefault(self.pattern(t), t)
        for i, t in enumerate(self.nametable):
            if t in GLYPHS and first[self.pattern(t)] != t:
                raise AssetError(f"background cell ({i % COLUMNS},{i // COLUMNS}) must use glyph "
                                 f"${first[self.pattern(t)]:02X}: blank is $E8, else the lowest id with the pattern")

    def _check_screen(self):
        for col, row in sorted(GEOMETRY.writer_cells() | GEOMETRY.name_cells()):
            if any(self.pattern(self.nametable[COLUMNS * row + col])):
                kind = "writer" if (col, row) in GEOMETRY.writer_cells() else "name sprite"
                raise AssetError(f"{kind} cell ({col},{row}) must be blank in the background")
        for ax, ay in sorted(GEOMETRY.glyph_attribute_cells()):
            if attribute(self.attributes, ax, ay) != GLYPH_PALETTE:
                raise AssetError(f"attribute cell ({ax},{ay}) holds writer cells and must use palette 0")
        if any(b >> 4 for b in self.attributes[56:]):
            raise AssetError("attribute bits below the screen must be zero")

    def pattern(self, tile):
        return self.chr[16 * tile:16 * tile + 16]

    def screen(self):
        """The 1 KB scene $0A uploads to $2000: nametable, then attributes."""
        return self.nametable + self.attributes

    def record(self):
        return {
            "format": FORMAT,
            "chr_bank": SCORE_CHR,
            "tiles_used": self.tiles_used,
            "sources": dict(self.sources),
            "chr": self.chr.hex(),
            "nametable": self.nametable.hex(),
            "attributes": self.attributes.hex(),
            "palette": self.palette.hex(),
        }

    def dumps(self):
        return json.dumps(self.record(), indent=1) + "\n"

    @classmethod
    def parse(cls, record):
        if not isinstance(record, dict) or set(record) != set(KEYS):
            raise AssetError(f"{FORMAT} must hold exactly the keys {', '.join(KEYS)}")
        if record["format"] != FORMAT or not is_int(record["chr_bank"]) or record["chr_bank"] != SCORE_CHR:
            raise AssetError(f"expected {FORMAT} art for CHR ${SCORE_CHR:02X}")
        if not isinstance(record["sources"], dict):
            raise AssetError("sources must map art-relative paths to SHA-256 digests")
        return cls(
            tiles_used=record["tiles_used"],
            sources=tuple(sorted(record["sources"].items())),
            chr=hex_field(record, "chr"),
            nametable=hex_field(record, "nametable"),
            attributes=hex_field(record, "attributes"),
            palette=hex_field(record, "palette"),
        )

    @classmethod
    def load(cls, path=ASSETS):
        return cls.parse(json.loads(Path(path).read_text()))


def hex_field(record, key):
    text = record[key]
    if not isinstance(text, str) or not re.fullmatch(r"(?:[0-9a-f]{2})*", text):
        raise AssetError(f"{key} must be a lowercase hex string")
    data = bytes.fromhex(text)
    if len(data) != SIZES[key]:
        raise AssetError(f"{key} must be exactly {SIZES[key]} bytes, not {len(data)}")
    return data
