#!/usr/bin/env python3
"""The Power Analysis card as one validated domain model.

Sources (tracked, art/analysisart32/):
  layout.json       analysisart32-layout/1: palettes, the CHR $18 title band, the split strip, one row
                    per stat (label, four ball sockets, digit), static text, the ball sprite, the flag
                    row and the init pacing. The geometry contract: one stats row by socket column
                    grid drives the converter's socket check and the bank-3 ball and digit tables.
  placements.json   analysisart32-placements/1: where card32.px.js stamps the approved stockart32 parts
                    and which of their pixels stay visible.

Read from the pinned input ROM, never asserted:
  AnalysisRatings   32 x 4 ratings at bank 3 $BC80 through the reader $AFE2, each 1..4, and the meaning
                    of each stored index, derived from the stock chart's direction tables $B1CA/$B1CE
                    and the stock label list $B1FB.
  title_placements  per team what the stock name writer $C9A8 prints (font, cells, ink extent), whether
                    the stock flag writer $CB56 draws a flag, and the centered column and flag x.
  mode_screen_ids   every CHR $06 id the stockart32 mode menu shows: nametable and all run lists.

Generated (build/analysisart32/analysisassets.json, analysisassets/1, written by
tools/analysisart32_convert.py and read by tools/build_analysisart32.py): the converted screen and
the geometry it was converted with. Building an AnalysisAssets validates every field on its own;
build_analysisart32.check_runtime then checks it against the input ROM's fonts and sprites.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import menu32_convert as menu
from menu32_convert import AssetError
import render_menu32 as R
from build_draw32 import read

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art/analysisart32"
LAYOUT_FORMAT = "analysisart32-layout/1"
PLACEMENTS_FORMAT = "analysisart32-placements/1"
ASSETS_FORMAT = "analysisassets/1"
PART_MANIFEST = "art/stockart32/characters.json"

HOME_BANK, FAR_BANK, FLAG_BANK, MODE_BANK = 3, 13, 4, 13
MODE_CHR, TITLE_CHR, FONT_CHR, SPRITE_CHR = 0x06, 0x18, 0x00, 0x1B
FIRST_FREE = 0xBA                  # the stockart32 mode screen owns CHR $06 $00-$B9
BLANK = 0x20
ROWS, COLUMNS = 30, 32
SPLIT_ROW = 8                      # holds stock sprite 0's hit line 65
NAME_ROWS = (2, 3, 4, 5)           # the stock writer prints rows 3-5 with padding and wrap; row 2 stays blank
RAIL_ROWS = (1, 6)
PACE_NMIS = 2
SCREEN_SIZE = (256, 240)

RATINGS, READER = 0xBC80, 0xAFE2   # 32 x 4 bytes; $AFE2 LDA $BC80,Y
DX_TABLE, DY_TABLE = 0xB1CA, 0xB1CE
CENTER = (0x80, 0x8F)              # stock chart center: $B10B LDA #$80, $B0FA LDA #$8F
LABEL_LIST = 0xB1FB
STATS = ("BATTING", "RUNNING", "PITCHING", "DEFENSE")
TEAMS, SCALE = 32, range(1, 5)
NAME_WRITER, FLAG_WRITER = 0xC9A8, 0xCB56
FONT_FLAGS = 0xFD20                # per team: bit 7 the narrow font
MODE_SCREEN, MODE_LISTS, MENUS = 0x9000, 0x9500, 3
SOLID3 = b"\xFF" * 16
RESERVE_KINDS = {"solid3": SOLID3}
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
HEX2 = re.compile(r"[0-9A-F]{2}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TEXT = re.compile(r"[A-Z0-9 ]+")


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


def tile_id(value, where):
    if not isinstance(value, str) or not HEX2.fullmatch(value):
        fail(where, "must be a tile id, two uppercase hex digits")
    return int(value, 16)


def int_list(value, where, low, high, length=None):
    if not isinstance(value, list) or not value or (length is not None and len(value) != length):
        fail(where, f"must be a list of {length or 'one or more'} integers")
    found = [integer(v, f"{where}[{i}]", low, high) for i, v in enumerate(value)]
    if len(set(found)) != len(found):
        fail(where, "names a value twice")
    return tuple(found)


def box(value, where, width, height):
    if not isinstance(value, list) or len(value) != 4:
        fail(where, "must be [x, y, w, h]")
    x, y = integer(value[0], f"{where} x", 0, width - 1), integer(value[1], f"{where} y", 0, height - 1)
    return x, y, integer(value[2], f"{where} w", 1, width - x), integer(value[3], f"{where} h", 1, height - y)


def glyph_id(char, glyphs):
    """The CHR $06 id that shows `char`: an extracted copy, the blank, or the mode font at its ASCII id."""
    if char == " ":
        return BLANK
    return glyphs[char] if char in glyphs else ord(char)



@dataclass(frozen=True)
class StatRow:
    stat: str
    row: int
    label_col: int
    digit_col: int


@dataclass(frozen=True)
class Layout:
    scene: str
    backdrop: int
    palettes: tuple           # four background palettes of three NES colors
    title_palette: int
    split_row: int
    name_rows: tuple
    rail_rows: tuple
    split_ids: tuple
    reserve: dict             # CHR $06 id -> pattern
    attr_hints: dict          # (even row, even col) -> palette
    glyphs: tuple             # characters copied from CHR $00 into new ids, in allocation order
    stats: tuple              # StatRow per stored index
    socket_cols: tuple
    socket_color: int
    text: tuple               # (row, col, text) static lettering
    ball_tile: int
    ball_palette: int
    ball_colors: tuple
    flag_y: int
    pace_nmis: int
    sha256: str

    def socket_cells(self):
        return tuple((s.row, col) for s in self.stats for col in self.socket_cols)

    def label_cells(self):
        return {(s.row, s.label_col + i): ch for s in self.stats for i, ch in enumerate(s.stat)}

    def static_cells(self):
        return {(row, col + i): ch for row, col, words in self.text for i, ch in enumerate(words)}

    def digit_cells(self):
        return {(s.row, s.digit_col): i for i, s in enumerate(self.stats)}

    @classmethod
    def parse(cls, data, digest):
        keys(data, "layout", {"format", "about", "scene", "backdrop", "palettes", "title", "reserve", "attr_hints",
                              "glyphs", "stats", "sockets", "text", "ball", "flag", "pace_nmis"})
        if data["format"] != LAYOUT_FORMAT:
            fail("layout", f"expected format {LAYOUT_FORMAT}")
        text(data["about"], "layout about")
        if not isinstance(data["scene"], str) or not ID.fullmatch(data["scene"]):
            fail("layout scene", "must be a path-safe lowercase name")
        backdrop = color(data["backdrop"], "layout backdrop")
        if not isinstance(data["palettes"], list) or len(data["palettes"]) != 4:
            fail("layout palettes", "must be four background palettes")
        palettes = []
        for i, p in enumerate(data["palettes"]):
            if not isinstance(p, list) or len(p) != 3:
                fail(f"layout palettes[{i}]", "must hold three NES colors")
            palettes.append(tuple(color(c, f"layout palettes[{i}][{j}]") for j, c in enumerate(p)))
        title = keys(data["title"], "layout title", {"palette", "split_row", "name_rows", "rail_rows", "split_ids"})
        title_palette = integer(title["palette"], "layout title palette", 0, 3)
        split = integer(title["split_row"], "layout title split_row", 0, ROWS - 1)
        if split != SPLIT_ROW:
            fail("layout title split_row", f"must be {SPLIT_ROW}: stock sprite 0 hits line 65 there, and moving it "
                                           "changes the NMI's busy wait")
        name_rows = int_list(title["name_rows"], "layout title name_rows", 0, split - 1)
        if name_rows != NAME_ROWS:
            fail("layout title name_rows", f"must be {list(NAME_ROWS)}: the stock writer's padded, wrapped rows")
        rail_rows = int_list(title["rail_rows"], "layout title rail_rows", 0, split - 1)
        if set(rail_rows) & set(name_rows) or rail_rows != RAIL_ROWS:
            fail("layout title rail_rows", f"must be {list(RAIL_ROWS)}, outside the name writer's rows")
        if not isinstance(title["split_ids"], list) or not title["split_ids"]:
            fail("layout title split_ids", "must list the ids the split row may use")
        split_ids = tuple(tile_id(v, f"layout title split_ids[{i}]") for i, v in enumerate(title["split_ids"]))
        if len(set(split_ids)) != len(split_ids) or BLANK not in split_ids:
            fail("layout title split_ids", "must be distinct and include the blank $20")
        if not isinstance(data["reserve"], dict):
            fail("layout reserve", "must map CHR $06 ids to pattern kinds")
        reserve = {}
        for key, kind in data["reserve"].items():
            rid = tile_id(key, f"layout reserve {key!r}")
            if not FIRST_FREE <= rid <= 0xFF:
                fail(f"layout reserve {key}", f"must be a free CHR $06 id ${FIRST_FREE:02X}-$FF")
            if kind not in RESERVE_KINDS:
                fail(f"layout reserve {key}", f"kind must be one of {', '.join(RESERVE_KINDS)}")
            if rid not in split_ids:
                fail(f"layout reserve {key}", "a reserved pattern exists for the split strip; list it in split_ids")
            reserve[rid] = RESERVE_KINDS[kind]
        if not isinstance(data["attr_hints"], list):
            fail("layout attr_hints", "must be a list")
        hints = {}
        for i, hint in enumerate(data["attr_hints"]):
            at = f"layout attr_hints[{i}]"
            keys(hint, at, {"row", "col", "palette"}, {"row", "palette"})
            row = integer(hint["row"], f"{at} row", 0, ROWS - 1)
            cols = [integer(hint["col"], f"{at} col", 0, COLUMNS - 1)] if "col" in hint else range(0, COLUMNS, 2)
            for col in cols:
                hints[(row & ~1, col & ~1)] = integer(hint["palette"], f"{at} palette", 0, 3)
        glyphs = data["glyphs"]
        if (not isinstance(glyphs, list) or not all(isinstance(g, str) and len(g) == 1 and TEXT.fullmatch(g)
                                                    and g != " " for g in glyphs) or len(set(glyphs)) != len(glyphs)):
            fail("layout glyphs", "must be distinct single uppercase letters or digits")
        if not isinstance(data["stats"], list) or len(data["stats"]) != len(STATS):
            fail("layout stats", f"must hold exactly one row per stat: {', '.join(STATS)}")
        stats = []
        for i, entry in enumerate(data["stats"]):
            at = f"layout stats[{i}]"
            keys(entry, at, {"stat", "row", "label_col", "digit_col"})
            if entry["stat"] not in STATS:
                fail(f"{at} stat", f"must be one of {', '.join(STATS)}")
            name = entry["stat"]
            row = integer(entry["row"], f"{at} row", split + 1, ROWS - 1)
            label = integer(entry["label_col"], f"{at} label_col", 0, COLUMNS - len(name))
            stats.append(StatRow(name, row, label, integer(entry["digit_col"], f"{at} digit_col", 0, COLUMNS - 1)))
        names = [s.stat for s in stats]
        if len(set(names)) != len(names):
            fail("layout stats", "names a stat twice")
        if tuple(names) != STATS:
            fail("layout stats", f"must list the stats in stored order {', '.join(STATS)}: entry i draws stored "
                                 "index i")
        if len({s.row for s in stats}) != len(stats):
            fail("layout stats", "two stats share a row")
        sockets = keys(data["sockets"], "layout sockets", {"cols", "color"})
        cols = int_list(sockets["cols"], "layout sockets cols", 0, COLUMNS - 1, length=max(SCALE))
        if list(cols) != sorted(cols):
            fail("layout sockets cols", "must run left to right: a rating fills the first sockets")
        if not isinstance(data["text"], list):
            fail("layout text", "must be a list")
        static = []
        for i, entry in enumerate(data["text"]):
            at = f"layout text[{i}]"
            keys(entry, at, {"row", "col", "text"})
            words = entry["text"]
            if not isinstance(words, str) or not TEXT.fullmatch(words) or not words.strip():
                fail(f"{at} text", "must be uppercase letters, digits and spaces")
            row = integer(entry["row"], f"{at} row", split + 1, ROWS - 1)
            static.append((row, integer(entry["col"], f"{at} col", 0, COLUMNS - len(words)), words))
        ball = keys(data["ball"], "layout ball", {"tile", "sprite_palette", "colors"})
        ball_palette = integer(ball["sprite_palette"], "layout ball sprite_palette", 1, 3)
        if not isinstance(ball["colors"], list) or len(ball["colors"]) != 3:
            fail("layout ball colors", "must hold three NES colors")
        flag = keys(data["flag"], "layout flag", {"y"})
        flag_y = integer(flag["y"], "layout flag y", 0, 8 * split - 24)
        pace = integer(data["pace_nmis"], "layout pace_nmis", 0, 8)
        if pace != PACE_NMIS:
            fail("layout pace_nmis", f"must be {PACE_NMIS}: the card releases on stock's frame only with both waits")
        layout = cls(scene=data["scene"], backdrop=backdrop, palettes=tuple(palettes), title_palette=title_palette,
                     split_row=split, name_rows=name_rows, rail_rows=rail_rows, split_ids=split_ids, reserve=reserve,
                     attr_hints=hints, glyphs=tuple(glyphs), stats=tuple(stats), socket_cols=cols,
                     socket_color=color(sockets["color"], "layout sockets color"), text=tuple(static),
                     ball_tile=tile_id(ball["tile"], "layout ball tile"), ball_palette=ball_palette,
                     ball_colors=tuple(color(c, f"layout ball colors[{i}]") for i, c in enumerate(ball["colors"])),
                     flag_y=flag_y, pace_nmis=pace, sha256=digest)
        check_cells(layout.label_cells(), layout.static_cells(), layout.digit_cells(), layout.socket_cells())
        return layout

    @classmethod
    def load(cls, path=ART / "layout.json"):
        raw = Path(path).read_bytes()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssetError(f"layout: not JSON ({exc})") from None
        return cls.parse(data, sha256(raw))


def check_cells(labels, static, digits, sockets):
    """Labels, static text, digits and sockets each own their cells: no cell twice, none off the screen."""
    owners = {}
    for kind, cells in (("label", labels), ("text", static), ("digit", digits), ("socket", sockets)):
        for row, col in cells:
            if not (0 <= row < ROWS and 0 <= col < COLUMNS):
                fail("layout", f"{kind} cell row {row} col {col} is off the screen")
            if (row, col) in owners:
                fail("layout", f"{kind} cell row {row} col {col} overlaps a {owners[(row, col)]} cell")
            owners[(row, col)] = kind



@dataclass(frozen=True)
class Placement:
    part: str
    at: tuple
    area: tuple | None        # None: the whole part
    visible: tuple | None     # None: wherever the stamp lands on screen


def parse_placements(data, part_sizes):
    """Placements of the approved parts; `part_sizes` maps each stockart32 part id to (w, h)."""
    keys(data, "placements", {"format", "about", "manifest", "placements"})
    if data["format"] != PLACEMENTS_FORMAT:
        fail("placements", f"expected format {PLACEMENTS_FORMAT}")
    text(data["about"], "placements about")
    if data["manifest"] != PART_MANIFEST:
        fail("placements manifest", f"must be {PART_MANIFEST}, the reviewed part source")
    if not isinstance(data["placements"], list) or not data["placements"]:
        fail("placements", "must be a non-empty list")
    found = []
    for i, entry in enumerate(data["placements"]):
        at = f"placements[{i}]"
        keys(entry, at, {"part", "at", "area", "visible", "why"}, {"part", "at"})
        if entry["part"] not in part_sizes:
            fail(f"{at} part", f"names no stockart32 part: {entry['part']!r}")
        if not isinstance(entry["at"], list) or len(entry["at"]) != 2:
            fail(f"{at} at", "must be [x, y]")
        x = integer(entry["at"][0], f"{at} at x", 0, SCREEN_SIZE[0] - 1)
        y = integer(entry["at"][1], f"{at} at y", 0, SCREEN_SIZE[1] - 1)
        area = box(entry["area"], f"{at} area", *part_sizes[entry["part"]]) if "area" in entry else None
        visible = box(entry["visible"], f"{at} visible", *SCREEN_SIZE) if "visible" in entry else None
        if visible is not None or "why" in entry:
            text(entry.get("why"), f"{at} why")
        found.append(Placement(entry["part"], (x, y), area, visible))
    return tuple(found)



def s8(value):
    return value - 256 if value >= 128 else value


def stock_labels(rom):
    """The stock chart's label list $B1FB: (text, column, row) of each run, as $C840 prints them."""
    labels, p = [], LABEL_LIST
    while True:
        low, high = read(rom, HOME_BANK, p, 2)
        p += 2
        words = bytearray()
        while read(rom, HOME_BANK, p, 1)[0] < 0xFE:
            words += read(rom, HOME_BANK, p, 1)
            p += 1
        end = read(rom, HOME_BANK, p, 1)[0]
        p += 1
        address = (high & 0x3F) << 8 | low
        labels.append((words.decode("ascii"), (address - 0x2000) % COLUMNS, (address - 0x2000) // COLUMNS))
        if end == 0xFF or len(labels) > 8:
            return labels


@dataclass(frozen=True)
class AnalysisRatings:
    values: tuple             # values[team] = four ratings in stored order
    meaning: tuple            # meaning[i] = the stat stored index i rates

    @classmethod
    def from_rom(cls, rom):
        if read(rom, HOME_BANK, READER, 3) != bytes((0xB9, RATINGS & 0xFF, RATINGS >> 8)):
            raise AssetError("ratings reader $AFE2 no longer reads $BC80,Y")
        raw = read(rom, HOME_BANK, RATINGS, 4 * TEAMS)
        values = tuple(tuple(raw[4 * t:4 * t + 4]) for t in range(TEAMS))
        for team, four in enumerate(values):
            if any(v not in SCALE for v in four):
                raise AssetError(f"team {team} ratings {list(four)} leave 1..4: the digit table has entries 1-4 only")
        labels = stock_labels(rom)
        dx, dy = read(rom, HOME_BANK, DX_TABLE, 4), read(rom, HOME_BANK, DY_TABLE, 4)
        cx, cy = CENTER[0] / 8, CENTER[1] / 8
        meaning = []
        for i in range(4):
            vx, vy = s8(dx[i]), s8(dy[i])
            best = max(labels, key=lambda label: (label[1] + len(label[0]) / 2 - cx) * vx + (label[2] + 1 - cy) * vy)
            meaning.append(best[0])
        if tuple(meaning) != STATS:
            raise AssetError(f"the stock chart's directions and labels give stored order {meaning}, not {list(STATS)}")
        return cls(values, tuple(meaning))



@dataclass(frozen=True)
class TitlePlacement:
    team: int
    text: str
    font: str                 # "wide" (2x2 tiles per letter) or "narrow" (1x2)
    cells: tuple              # (nametable index, CHR $18 tile) the writer stores when started at row 3, col 0
    ink: tuple                # leftmost and rightmost inked pixel column of rows 3-4, writer at col 0
    flag: bool                # whether the stock flag writer draws this team's flag
    col: int                  # the centered start column on row 3
    flag_x: int               # the flag's left x, 0 for flagless teams


def run_name_writer(rom, team, address, bank=HOME_BANK):
    """Execute the stock writer $C9A8 for `team` at nametable `address`, rendering off: (machine, cells, text)."""
    m = R.Machine(rom)
    m.mpu.sp = 0xEF
    m.map_bank(bank)
    sentinel = 0xEE
    m.vram[0:0x400] = bytes((sentinel,)) * 0x400
    m.ram[0x04EF] = team
    m.ram[0x2C], m.ram[0x32], m.ram[0xAC], m.ram[0xAD] = 1, 0, 0, 0x40
    m.ram[0x06B3], m.ram[0x06B4] = address >> 8, address & 0xFF
    m.call(NAME_WRITER, a=team)
    nametable = m.nametable()
    cells = tuple((i, nametable[i]) for i in range(ROWS * COLUMNS) if nametable[i] != sentinel)
    record = bytes(m.ram[0x06B5:0x06B5 + 32])
    words = record.split(b"\xFF")[0].split(b"\xFE")[0].decode("ascii", "replace").rstrip()
    return m, cells, words


def run_flag_writer(rom, team, x, y, slot=4, bank=HOME_BANK):
    """Execute the stock flag writer $CB56 for `team` with its left x and OAM Y: OAM slots 1-9 as written."""
    m = R.Machine(rom)
    m.mpu.sp = 0xEF
    m.map_bank(bank)
    m.ram[0x0200:0x0300] = b"\xF0" * 256
    m.ram[0x047F], m.ram[0x04], m.ram[0x05] = slot, y, x
    m.mpu.x = team
    m.call(FLAG_WRITER)
    if (m.prg, m.ram[0x27]) != (bank, bank):
        raise AssetError(f"the stock flag writer left bank {m.prg}/{m.ram[0x27]}, not {bank}")
    return bytes(m.ram[0x0200 + slot:0x0200 + slot + 36])


def title_placements(rom, row=3):
    """Per team: the stock writer's cells and ink, the stock flag, and the column that centers both on x 127.5."""
    chr18 = read(rom, "chr", TITLE_CHR * 0x1000, 0x1000)
    found = []
    for team in range(TEAMS):
        _, cells, words = run_name_writer(rom, team, 0x2000 + COLUMNS * row)
        xs = []
        for index, tile in cells:
            if index // COLUMNS not in (row, row + 1) or tile == BLANK:
                continue
            grid = menu.decode(chr18[16 * tile:16 * tile + 16])
            col = index % COLUMNS
            xs += [8 * col + x for x in range(8) if any(grid[y][x] for y in range(8))]
        if not xs:
            raise AssetError(f"team {team}: the stock writer printed no ink")
        left, right = min(xs), max(xs)
        flag = any(b < 0xEF for b in run_flag_writer(rom, team, 0, 0)[0::4])
        font = "narrow" if read(rom, 15, FONT_FLAGS + team, 1)[0] & 0x80 else "wide"
        col = round((127.5 - (right - 32) / 2) / 8) if flag else round((127.5 - (left + right) / 2) / 8)
        first_row = [i % COLUMNS for i, _ in cells if i // COLUMNS == row]
        if font == "narrow" and col + max(first_row) - min(first_row) + 1 > COLUMNS:
            raise AssetError(f"team {team}: the narrow name would wrap off row {row}")
        if not 0 <= col <= COLUMNS - 1 or (flag and 8 * col < 32):
            raise AssetError(f"team {team}: centered column {col} leaves no room for the name and flag")
        if any((i + col) // COLUMNS not in NAME_ROWS for i, _ in cells):
            raise AssetError(f"team {team}: the name written from column {col} leaves rows {list(NAME_ROWS)}")
        found.append(TitlePlacement(team, words, font, cells, (left, right), flag, col,
                                    (8 * col - 32) & 0xFF if flag else 0))
    return tuple(found)


def mode_screen_ids(rom):
    """Every CHR $06 id the stockart32 mode menu can show: its nametable and the tiles of all three run lists."""
    used = set(read(rom, MODE_BANK, MODE_SCREEN, ROWS * COLUMNS))
    pointers = read(rom, MODE_BANK, MODE_LISTS, 2 * MENUS)
    for k in range(MENUS):
        p = pointers[k] | pointers[MENUS + k] << 8
        for _ in range(ROWS):
            high = read(rom, MODE_BANK, p + 1, 1)[0]
            if high & 0xC0 != 0x40:
                raise AssetError(f"mode run list {k} at ${p:04X} is not a raw nametable run")
            p += 2
            while (b := read(rom, MODE_BANK, p, 1)[0]) < 0xFE:
                used.add(b)
                p += 1
            p += 1
            if b == 0xFF:
                break
        else:
            raise AssetError(f"mode run list {k} has no end")
    return used



ASSET_KEYS = ("format", "scene", "layout_sha256", "png_sha256", "split_row", "title_palette", "name_rows", "rail_rows",
              "split_ids", "nametable", "attributes", "palette", "new_tiles", "glyphs", "digits", "stats", "text",
              "socket_cols", "socket_tile", "ball", "flag_y", "pace_nmis")
SIZES = {"nametable": ROWS * COLUMNS, "attributes": 64, "palette": 16}


def attr_palette(attributes, col, row):
    offset, shift = menu.attr_slot(col, row)
    return (attributes[offset] >> shift) & 3


@dataclass(frozen=True)
class AnalysisAssets:
    scene: str
    layout_sha256: str
    png_sha256: str
    split_row: int
    title_palette: int
    name_rows: tuple
    rail_rows: tuple
    split_ids: tuple
    nametable: bytes          # 960 ids: CHR $18 above the split, CHR $06 below
    attributes: bytes
    palette: bytes            # the four background palettes, one backdrop
    new_tiles: dict           # CHR $06 id ($BA-$FF) -> 16-byte pattern, ids ascending
    glyphs: dict              # character -> new CHR $06 id holding its CHR $00 glyph
    digits: tuple             # CHR $06 id showing rating 1, 2, 3, 4
    stats: tuple              # StatRow per stored index
    text: tuple               # (row, col, text) static lettering
    socket_cols: tuple
    socket_tile: int
    ball_tile: int
    ball_palette: int
    ball_colors: tuple
    flag_y: int
    pace_nmis: int

    def __post_init__(self):
        for name in ("layout_sha256", "png_sha256"):
            if not isinstance(getattr(self, name), str) or not HEX64.fullmatch(getattr(self, name)):
                raise AssetError(f"{name} must be a lowercase SHA-256")
        if not isinstance(self.scene, str) or not ID.fullmatch(self.scene):
            raise AssetError("scene must be a path-safe lowercase name")
        for key, size in SIZES.items():
            if not isinstance(getattr(self, key), bytes) or len(getattr(self, key)) != size:
                raise AssetError(f"{key} must be exactly {size} bytes")
        if (self.split_row, self.name_rows, self.rail_rows, self.pace_nmis) != (SPLIT_ROW, NAME_ROWS, RAIL_ROWS,
                                                                                PACE_NMIS):
            raise AssetError(f"the card contract is split row {SPLIT_ROW}, name rows {list(NAME_ROWS)}, rails "
                             f"{list(RAIL_ROWS)} and {PACE_NMIS} paced NMIs")
        if not is_int(self.title_palette) or not 0 <= self.title_palette <= 3:
            raise AssetError("title_palette must be 0-3")
        if (not isinstance(self.split_ids, tuple) or BLANK not in self.split_ids
                or not all(is_int(t) and 0 <= t <= 0xFF for t in self.split_ids)):
            raise AssetError("split_ids must be tile ids including the blank $20")
        backdrops = set(self.palette[::4])
        if len(backdrops) != 1 or not all(supported(c) for c in self.palette):
            raise AssetError("palette must hold supported NES colors sharing one backdrop")
        ids = list(self.new_tiles)
        if (not isinstance(self.new_tiles, dict) or ids != sorted(ids)
                or not all(is_int(t) and FIRST_FREE <= t <= 0xFF for t in ids)):
            raise AssetError(f"new tile ids must ascend inside the free CHR $06 range ${FIRST_FREE:02X}-$FF")
        patterns = list(self.new_tiles.values())
        if not all(isinstance(p, bytes) and len(p) == 16 and any(p) for p in patterns) or len(set(patterns)) != len(
                patterns):
            raise AssetError("each new tile must be one distinct, non-blank 16-byte pattern")
        if (not isinstance(self.glyphs, dict) or not all(isinstance(c, str) and len(c) == 1 and TEXT.fullmatch(c)
                                                         and c != " " for c in self.glyphs)
                or not all(g in self.new_tiles for g in self.glyphs.values())
                or len(set(self.glyphs.values())) != len(self.glyphs)):
            raise AssetError("glyphs must map single characters to distinct new tile ids")
        if (not isinstance(self.digits, tuple) or len(self.digits) != max(SCALE)
                or not all(is_int(d) and (d in self.new_tiles or 0 <= d < FIRST_FREE) for d in self.digits)
                or any(glyph_id(str(v), self.glyphs) != d for v, d in zip(SCALE, self.digits))):
            raise AssetError("digits must be the glyph ids of 1, 2, 3 and 4")
        stats = self.stats
        if (not isinstance(stats, tuple) or tuple(getattr(s, "stat", None) for s in stats) != STATS
                or not all(isinstance(s, StatRow) for s in stats)):
            raise AssetError(f"stats must be one StatRow per stat in stored order {', '.join(STATS)}")
        for s in stats:
            if (not all(is_int(v) for v in (s.row, s.label_col, s.digit_col)) or not SPLIT_ROW < s.row < ROWS
                    or not 0 <= s.label_col <= COLUMNS - len(s.stat) or not 0 <= s.digit_col < COLUMNS):
                raise AssetError(f"{s.stat} row {s.row} cells must lie below the split, on the screen")
        cols = self.socket_cols
        if (not isinstance(cols, tuple) or len(cols) != max(SCALE) or list(cols) != sorted(set(cols))
                or not all(is_int(c) and 0 <= c < COLUMNS for c in cols)):
            raise AssetError("socket_cols must be four ascending on-screen columns")
        labels = {(s.row, s.label_col + i): ch for s in stats for i, ch in enumerate(s.stat)}
        if not isinstance(self.text, tuple) or not all(
                isinstance(t, tuple) and len(t) == 3 and is_int(t[0]) and is_int(t[1]) and isinstance(t[2], str)
                and TEXT.fullmatch(t[2]) and t[2].strip() and SPLIT_ROW < t[0] < ROWS
                and 0 <= t[1] <= COLUMNS - len(t[2]) for t in self.text):
            raise AssetError("text must be (row, col, uppercase text) entries below the split, on the screen")
        static = {(row, col + i): ch for row, col, words in self.text for i, ch in enumerate(words)}
        digit_cells = {(s.row, s.digit_col) for s in stats}
        sockets = {(s.row, c) for s in stats for c in cols}
        check_cells(labels, static, digit_cells, sockets)
        nt = self.nametable
        if self.socket_tile not in self.new_tiles:
            raise AssetError("socket_tile must be a new tile")
        placed = {(i // COLUMNS, i % COLUMNS) for i, t in enumerate(nt) if t == self.socket_tile}
        if placed != sockets:
            raise AssetError(f"the nametable must hold the socket tile exactly at the {len(sockets)} socket cells, "
                             f"not at {len(placed)} cells")
        for (row, col), ch in (labels | static).items():
            if nt[COLUMNS * row + col] != glyph_id(ch, self.glyphs):
                raise AssetError(f"lettered cell row {row} col {col} must show {ch!r}")
        if any(nt[COLUMNS * row + col] != BLANK for row, col in digit_cells):
            raise AssetError("digit cells must stay blank: numerals() writes them at runtime")
        if any(nt[COLUMNS * row + col] != BLANK for row in self.name_rows for col in range(COLUMNS)):
            raise AssetError("name rows must stay blank: the stock writer prints there")
        if not set(nt[COLUMNS * SPLIT_ROW:COLUMNS * (SPLIT_ROW + 1)]) <= set(self.split_ids):
            raise AssetError("the split row may use only split_ids")
        lower = set(nt[COLUMNS * (SPLIT_ROW + 1):])
        undefined = sorted(t for t in lower if t >= FIRST_FREE and t not in self.new_tiles)
        if undefined:
            raise AssetError(f"the lower screen uses undefined CHR $06 ids {' '.join(f'${t:02X}' for t in undefined)}")
        if any(attr_palette(self.attributes, col, row) != self.title_palette
               for row in range(SPLIT_ROW) for col in range(COLUMNS)):
            raise AssetError("every title-band cell must use the title palette")
        if (not is_int(self.ball_tile) or not 0 <= self.ball_tile <= 0xFF or not is_int(self.ball_palette)
                or not 1 <= self.ball_palette <= 3 or not isinstance(self.ball_colors, tuple)
                or len(self.ball_colors) != 3 or not all(supported(c) for c in self.ball_colors)):
            raise AssetError("ball must be a sprite tile, sprite palette 1-3 and three supported colors")
        if not is_int(self.flag_y) or not 0 <= self.flag_y <= 8 * SPLIT_ROW - 24:
            raise AssetError("flag_y must keep the 3x3 flag above the split")

    @property
    def free_after(self):
        return 0x100 - FIRST_FREE - len(self.new_tiles)

    def record(self):
        return {
            "format": ASSETS_FORMAT,
            "scene": self.scene,
            "layout_sha256": self.layout_sha256,
            "png_sha256": self.png_sha256,
            "split_row": self.split_row,
            "title_palette": self.title_palette,
            "name_rows": list(self.name_rows),
            "rail_rows": list(self.rail_rows),
            "split_ids": [f"{t:02X}" for t in self.split_ids],
            "nametable": self.nametable.hex(),
            "attributes": self.attributes.hex(),
            "palette": self.palette.hex(),
            "new_tiles": {f"{t:02X}": p.hex() for t, p in self.new_tiles.items()},
            "glyphs": {c: f"{t:02X}" for c, t in self.glyphs.items()},
            "digits": [f"{t:02X}" for t in self.digits],
            "stats": [{"stat": s.stat, "row": s.row, "label_col": s.label_col, "digit_col": s.digit_col}
                      for s in self.stats],
            "text": [{"row": row, "col": col, "text": words} for row, col, words in self.text],
            "socket_cols": list(self.socket_cols),
            "socket_tile": f"{self.socket_tile:02X}",
            "ball": {"tile": f"{self.ball_tile:02X}", "sprite_palette": self.ball_palette,
                     "colors": [f"{c:02X}" for c in self.ball_colors]},
            "flag_y": self.flag_y,
            "pace_nmis": self.pace_nmis,
        }

    def dumps(self):
        return json.dumps(self.record(), indent=1) + "\n"

    @classmethod
    def parse(cls, record):
        if not isinstance(record, dict) or list(record) != list(ASSET_KEYS):
            raise AssetError(f"{ASSETS_FORMAT} must hold exactly the keys {', '.join(ASSET_KEYS)}, in that order")
        if record["format"] != ASSETS_FORMAT:
            raise AssetError(f"expected {ASSETS_FORMAT}")
        ball = record["ball"]
        if not isinstance(ball, dict) or set(ball) != {"tile", "sprite_palette", "colors"}:
            raise AssetError("ball must hold tile, sprite_palette and colors")
        stats = record["stats"]
        if not isinstance(stats, list) or not all(isinstance(s, dict) and set(s) == {"stat", "row", "label_col",
                                                                                      "digit_col"} for s in stats):
            raise AssetError("stats must be a list of {stat, row, label_col, digit_col}")
        tiles = record["new_tiles"]
        if not isinstance(tiles, dict) or not isinstance(record["glyphs"], dict):
            raise AssetError("new_tiles and glyphs must be objects")
        if not isinstance(record["text"], list) or not all(isinstance(t, dict) and set(t) == {"row", "col", "text"}
                                                            for t in record["text"]):
            raise AssetError("text must be a list of {row, col, text}")
        for name in ("name_rows", "rail_rows", "socket_cols", "split_ids", "digits"):
            if not isinstance(record[name], list):
                raise AssetError(f"{name} must be a list")
        return cls(
            scene=record["scene"], layout_sha256=record["layout_sha256"], png_sha256=record["png_sha256"],
            split_row=record["split_row"], title_palette=record["title_palette"],
            name_rows=tuple(record["name_rows"]), rail_rows=tuple(record["rail_rows"]),
            split_ids=tuple(hex_id(t, "split_ids") for t in record["split_ids"]),
            nametable=hex_bytes(record, "nametable"), attributes=hex_bytes(record, "attributes"),
            palette=hex_bytes(record, "palette"),
            new_tiles={hex_id(t, "new_tiles"): hex_bytes(tiles, t, 16) for t in tiles},
            glyphs={c: hex_id(t, "glyphs") for c, t in record["glyphs"].items()},
            digits=tuple(hex_id(t, "digits") for t in record["digits"]),
            stats=tuple(StatRow(s["stat"], s["row"], s["label_col"], s["digit_col"]) for s in stats),
            text=tuple((t["row"], t["col"], t["text"]) for t in record["text"]),
            socket_cols=tuple(record["socket_cols"]), socket_tile=hex_id(record["socket_tile"], "socket_tile"),
            ball_tile=hex_id(ball["tile"], "ball tile"), ball_palette=ball["sprite_palette"],
            ball_colors=tuple(hex_id(c, "ball colors") for c in ball["colors"]) if isinstance(ball["colors"], list)
            else ball["colors"],
            flag_y=record["flag_y"], pace_nmis=record["pace_nmis"])

    @classmethod
    def load(cls, path):
        return cls.parse(json.loads(Path(path).read_text()))


def supported(value):
    try:
        menu.nes_color(f"{value:02X}")
    except (AssetError, TypeError, ValueError):
        return False
    return is_int(value)


def hex_id(value, where):
    if not isinstance(value, str) or not HEX2.fullmatch(value):
        raise AssetError(f"{where}: {value!r} must be two uppercase hex digits")
    return int(value, 16)


def hex_bytes(record, key, size=None):
    value = record[key]
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{2})*", value):
        raise AssetError(f"{key} must be a lowercase hex string")
    data = bytes.fromhex(value)
    if size is not None and len(data) != size:
        raise AssetError(f"{key} must be exactly {size} bytes")
    return data


def chr_tile(rom, bank, tile):
    return read(rom, "chr", bank * 0x1000 + 16 * tile, 16)


def ink2(pattern):
    """A CHR $00 glyph with its ink at value 2, the mode font's ink."""
    grid = menu.decode(pattern)
    if len({v for row in grid for v in row if v}) != 1:
        raise AssetError("a glyph must use one ink value")
    return menu.encode([[2 if v else 0 for v in row] for row in grid])


def ball_outline(rom, tile):
    """The 8x8 mask of the ball sprite's edge: opaque pixels with a clear or off-tile 4-neighbour."""
    grid = menu.decode(chr_tile(rom, SPRITE_CHR, tile))
    opaque = {(x, y) for y in range(8) for x in range(8) if grid[y][x]}
    return frozenset((x, y) for x, y in opaque
                     if any((x + dx, y + dy) not in opaque for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
