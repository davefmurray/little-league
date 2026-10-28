#!/usr/bin/env python3
"""Replace the 32-team selector and bracket presentation on the pinned visualtables32 ROM.

    .venv/bin/python tools/build_menuart32.py build/visualtables32.nes -o build/menuart32.nes
    .venv/bin/python tools/build_menuart32.py build/visualtables32.nes -o build/menuart32.nes --manifest

Two 3-byte hooks jump from the old draw entries (bank 10 and bank 11 $8000) to
new screens in free space of the same banks. Every input, commit, seed,
launch, result, password and view-exit routine stays byte-identical; the new
screens leave through the same stock entry points the old ones used.

While a menu runs, the stock NMI is a pure vblank clock: $2C=1 sends it down its
short path and $2D=1 makes it skip its audio tick. Each menu frame waits for
that clock, writes queued VRAM inside vblank, DMAs OAM, restores scroll and mask,
then calls the stock tick past its guard ($CF7B) once. Song $06, the stock menu
song, is only queued when it is not already playing.

Art lives in CHR bank $19, mapped through CHR1 only. Font tiles keep their ASCII
ids and are copied from CHR bank $00 here, so no stock glyph is committed.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from build_bank11 import assemble
from build_teamnames32 import HEADER, ROM_SIZE, ROOT, off
from build_visualtables32 import PROTECTED_SHA256 as PRIOR_SHA256, protect_output as protect_prior_output
import menu32_convert as convert

BASE_SHA256 = "cf4f1126a4afde0cd04bd13f06ebbea2867029cba78cedb3944ee7b15d582780"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
ASSETS = ROOT / "data/menu32/menuassets.json"
TEAMS = ROOT / "data/teams32.json"
CHR_START = convert.CHR_START
MENU_CHR = convert.CHR_BANK
CHR19_SHA256 = "12683d05317b4e4682f69071552ee951e541a8f75516c7aad5a23fdb033b960c"

# RAM the menus own while they run. $07F3/$07F4 are former debug bytes nothing reads.
MENU_FRAME, MENU_MASK = 0x07F3, 0x07F4
ROW, COL, CHOICE = 0x07C0, 0x07C1, 0x07C3          # stock meanings: row (page), column, team
PAD, CURSOR, HELD, NEW = 0x07C6, 0x07C7, 0x07C8, 0x07C9
BUF, BUF_SIZE, CACHE = 0x0300, 0x80, 0x0380        # VRAM runs; bracket heap cache
SONG = 0x06
SFX_MOVE, SFX_CONFIRM = 0x36, 0x35
CTRL = 0x98                                         # NMI on, BG and sprites from $1000
MASK = 0x1E

SEL_BANK, BRK_BANK = 10, 11
SEL_CODE, SEL_DATA, SEL_MAP = 0xA000, 0xA400, 0xB000
BRK_CODE, BRK_DATA, BRK_MAP = 0x9000, 0x9400, 0xA000


@dataclass(frozen=True)
class Region:
    name: str
    bank: object          # PRG bank number, or "chr"
    start: int
    end: int


REGIONS = (
    Region("selector-entry", SEL_BANK, 0x8000, 0x8003),
    Region("selector-code", SEL_BANK, SEL_CODE, SEL_CODE + 0x400),
    Region("selector-data", SEL_BANK, SEL_DATA, SEL_DATA + 0x700),
    Region("selector-map", SEL_BANK, SEL_MAP, SEL_MAP + 0x400),
    Region("bracket-entry", BRK_BANK, 0x8000, 0x8003),
    Region("bracket-code", BRK_BANK, BRK_CODE, BRK_CODE + 0x400),
    Region("bracket-data", BRK_BANK, BRK_DATA, BRK_DATA + 0xA00),
    Region("bracket-map", BRK_BANK, BRK_MAP, BRK_MAP + 0x400),
    Region("menu-chr", "chr", MENU_CHR * 0x1000, MENU_CHR * 0x1000 + 0x1000),
)


@dataclass(frozen=True)
class Change:
    name: str
    bank: object
    addr: int
    before: bytes
    after: bytes


def locate(bank, addr):
    return CHR_START + addr if bank == "chr" else off(bank, addr)


def read(rom, bank, addr, size):
    start = locate(bank, addr)
    return bytes(rom[start:start + size])


def word(addr):
    return addr.to_bytes(2, "little")


# Unchanged stock code the new screens call, enter from or leave through. Each must
# still hold these exact bytes; a drifted base fails the build instead of the game.
DEPENDENCIES = (
    ("MMC1 control/CHR/PRG writers", 15, 0xC100, "A5 22 85 22 E6 2D 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F C6 2D 60"
     " E6 2D 8D FF BF 4A 8D FF BF 4A 8D FF BF 4A 8D FF BF 4A 8D FF BF C6 2D 60"
     " E6 2D 8D FF DF 4A 8D FF DF 4A 8D FF DF 4A 8D FF DF 4A 8D FF DF C6 2D 60"
     " A5 27 85 27 E6 2D 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF C6 2D 60"),
    ("OAM hide $C199", 15, 0xC199, "A9 F0 A2 00 9D 00 02 CA D0 FA 60"),
    ("sound queue $C249", 15, 0xC249, "AE EA 04 D0 11 E6 2D AE 79 04 9D 70 04 E8 8A 29 07 8D 79 04 C6 2D 60"),
    ("NMI $CD85", 15, 0xCD85, "48 98 48 8A 48 A5 2C 8D E6 04 D0 50"),
    ("NMI short path $CDE1", 15, 0xCDE1, "20 74 CF A5 AD 29 1E F0 05 A9 00 8D 7D 04 68 AA 68 A8 68 40"),
    ("audio tick $CF74", 15, 0xCF74, "A5 2D 8D E4 04 D0 2E E6 2D A9 00 20 50 C1 AE 78 04 BD 70 04 C9 FF F0 15"
     " 8D 00 04 20 48 80 AE 78 04 A9 FF 9D 70 04 E8 8A 29 07 8D 78 04 20 6C 81 20 4C C1 C6 2D 60"),
    ("NMI vector", 15, 0xFFFA, "85 CD"),
    ("selector bridge $FF20", 15, 0xFF20, "BA 8E F7 07 BD 01 01 8D F8 07 BD 02 01 8D F9 07 A9 00 8D 00 20"
     " A2 FF 8E FF 9F A9 0A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 A9 0A 85 27 4C 00 80"),
    ("commit bridge $FF14", 15, 0xFF14, "A9 0B 20 4E C1 4C 80 83"),
    ("exit $FF90", 15, 0xFF90, "A2 FF 8E FF 9F A9 05 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0"
     " A9 05 85 27 A9 80 8D 00 20 9A 4C 09 CC"),
    ("LIST/CONTINUE $FEA0", 15, 0xFEA0, "AD EF 07 C9 32 D0 17 AD ED 07 F0 12 A9 01 8D F0 07 A9 00 8D 00 20"
     " A9 0B 20 4E C1 4C 00 80"),
    ("result hook $FFC0", 15, 0xFFC0, "AD E2 04 F0 0D AD D0 04 F0 08 A9 0B 20 4E C1 4C A0 83"),
    ("password bridge $FCD5", 15, 0xFCD5, "A9 00 8D 00 20 A9 0B 20 4E C1 4C 00 86"),
    ("selector commit $9620", SEL_BANK, 0x9620, "A9 FF 8D 4B 07 8D 4C 07 8D F1 07 8D F2 07 AD C3 07 29 07 AA BD 5A 96"
     " 49 FF 85 00 AD C3 07 4A 4A 4A AA A5 00 E0 02 B0 09 3D 4B 07 9D 4B 07 4C 14 FF 3D EF 07 9D EF 07 4C 14 FF"
     " 01 02 04 08 10 20 40 80"),
    ("new series $8380", BRK_BANK, 0x8380, "A9 00 8D FC 07 A9 FF A2 20 9D 00 77 E8 E0 3F D0 F8 4C E0 86"),
    ("advance $83A0", BRK_BANK, 0x83A0, "AE FC 07 E0 1F B0 22 AD 8B 04 CD 8C 04 F0 0E 90 06 AD EF 04 4C C3 83"
     " AD F0 04 4C C3 83 8A 0A A8 B9 00 77 9D 20 77 EE FC 07 4C 00 80"),
    ("seed $8200", BRK_BANK, 0x8200, "AD C3 07 8D 00 77 A2 01 8A 38 E9 01 CD 00 77 90 03 18 69 01 9D 00 77 E8"
     " E0 20 D0 EC 60"),
    ("launch $8162", BRK_BANK, 0x8162, "AD C7 07 8D EF 04 49 01 8D F0 04 A9 B0 8D FF 07 A5 33 85 34 4C 40 85"),
    ("release $8540", BRK_BANK, 0x8540, "20 0B 81 AD C6 07 D0 F8 4C 60 83"),
    ("pad $810B", BRK_BANK, 0x810B, "A9 01 8D 16 40 A9 00 8D 16 40 A2 08 A9 00 8D C6 07 AD 16 40 4A 2E C6 07"
     " CA D0 F6 60"),
    ("match teams $8360", BRK_BANK, 0x8360, "AD FC 07 0A AA BD 00 77 8D FA 07 BD 01 77 8D FB 07 4C 00 83"),
    ("scene $8300", BRK_BANK, 0x8300, "A9 13 8D 7B 04 A9 00 8D 7D 04 8D 46 07 85 BE A9 07 8D 7C 04 A9 01 8D ED 07"
     " 4C 70 84"),
    ("roster bridge $8470", BRK_BANK, 0x8470, "A2 FF 8E FF 9F AD FC 07 0A A8 B9 00 77 8D FD 07 B9 01 77 8D FE 07"
     " 4C 00 FC"),
    ("restore $8600", BRK_BANK, 0x8600, "AD 28 06 8D C3 07 20 00 82 A9 FF A2 1E 9D 20 77 CA 10 FA AD 29 06 8D FC 07"),
    ("restore tail $8644", BRK_BANK, 0x8644, "AD 2E 06 8D 4B 07 AD 2F 06 8D 4C 07 AD 30 06 8D F1 07 AD 31 06 8D F2 07"
     " A9 01 8D ED 07 A9 32 8D EF 07 A9 00 8D F0 07 20 99 C1 4C 00 80"),
    ("view decision $8680", BRK_BANK, 0x8680, "AD FC 07 C9 1F 90 05 A9 01 8D F0 07 AD F0 07 D0 03 4C 00 81"),
    ("view exit $86C7", BRK_BANK, 0x86C7, "A9 06 8D 7B 04 A9 00 8D 7D 04 8D F0 07 4C 90 FF"),
    ("seed entry $86E0", BRK_BANK, 0x86E0, "A9 32 8D EF 07 A9 01 8D ED 07 A9 00 8D F0 07 20 00 82 4C 00 80"),
)


def check_dependencies(base):
    for label, bank, addr, text in DEPENDENCIES:
        expected = bytes.fromhex(text)
        if read(base, bank, addr, len(expected)) != expected:
            raise ValueError(f"{label}: unexpected stock bytes")



def runtime(palette, page):
    """The menu-mode routines. `palette` and `page` are this bank's palette and map address."""
    return [
        # MenuBegin: guards, then a blank and the vblank clock both inside one vblank, then
        # explicit MMC1 control before any bank switch, CHR (0,1), and the menu song unless
        # it already plays. Safe to call twice in a row.
        "menu_begin:",
        "LDA #$01", "STA $2C", "STA $2D",
        "LDA #$1E", "STA $AD",
        "LDA #$00", "STA $32", f"STA ${MENU_MASK:04X}",
        # Any NMI now takes the short path, which never reads $2002, so the flag is ours.
        "BIT $2002",
        "mb_wait:",
        "BIT $2002", "BPL mb_wait",
        "LDA #$00", "STA $2001",
        "LDA #$80", "STA $2000",
        "LDA #$1E", "JSR $C102",
        "LDA #$00", "JSR $C11C",
        "LDA #$01", "JSR $C134",
        "JSR $C199",
        f"LDA #${SONG:02X}", "CMP $0401", "BEQ mb_playing", "JSR $C249",
        "mb_playing:",
        "RTS",

        "vblank_wait:",
        "LDA #$01", "STA $047D",
        "vw_loop:",
        "LDA $047D", "BNE vw_loop",
        "RTS",

        # MenuFrame: all PPU work first, inside vblank; then one audio tick.
        "menu_frame:",
        "JSR vblank_wait",
        "LDA $32", "BEQ mf_flushed", "JSR flush",
        "mf_flushed:",
        "LDA #$00", "STA $2003", "LDA #$02", "STA $4014",
        f"LDA #${CTRL:02X}", "STA $2000",
        "LDA #$00", "STA $2005", "STA $2005",
        f"LDA ${MENU_MASK:04X}", "STA $2001",
        "JSR $CF7B",
        f"INC ${MENU_FRAME:04X}",
        "RTS",

        # MenuEnd: blank at vblank, then the state the old screens left for the stock exits.
        "menu_end:",
        "LDA #$00", f"STA ${MENU_MASK:04X}",
        "JSR menu_frame",
        "LDA #$00", "STA $2000", "STA $2C", "STA $2D", "STA $04E4", "STA $04E6", "STA $32",
        "LDA #$1E", "STA $AD",
        "JSR $C199",
        "LDA #$00", "STA $2003", "LDA #$02", "STA $4014",
        "LDA #$01", "JMP $C134",

        # VRAM runs in $0300: [address hi, lo, count, bytes...] up to length $32.
        "flush:",
        "LDX #$00",
        "fl_run:",
        f"LDA ${BUF:04X},X", "STA $2006",
        f"LDA ${BUF + 1:04X},X", "STA $2006",
        f"LDY ${BUF + 2:04X},X",
        "INX", "INX", "INX",
        "fl_byte:",
        f"LDA ${BUF:04X},X", "STA $2007",
        "INX", "DEY", "BNE fl_byte",
        "CPX $32", "BCC fl_run",
        "LDA #$00", "STA $32",
        "RTS",

        "read_pad:",
        "LDA #$01", "STA $4016", "LDA #$00", "STA $4016",
        "LDX #$08",
        "rp_bit:",
        "LDA $4016", "LSR A", f"ROL ${PAD:04X}", "DEX", "BNE rp_bit",
        f"LDA ${HELD:04X}", "EOR #$FF", f"AND ${PAD:04X}", f"STA ${NEW:04X}",
        f"LDA ${PAD:04X}", f"STA ${HELD:04X}",
        "RTS",

        # q_head: append a run header for $02 bytes at PPU $00/$01; X = first data index.
        "q_head:",
        "LDX $32",
        "LDA $00", f"STA ${BUF:04X},X",
        "LDA $01", f"STA ${BUF + 1:04X},X",
        "LDA $02", f"STA ${BUF + 2:04X},X",
        "TXA", "CLC", "ADC #$03", "TAX",
        "CLC", "ADC $02", "STA $32",
        "RTS",

        # t_ptr: ($03) = ($05) + (A << X).
        "t_ptr:",
        "STA $03", "LDA #$00", "STA $04",
        "CPX #$00", "BEQ tp_add",
        "tp_shift:",
        "ASL $03", "ROL $04", "DEX", "BNE tp_shift",
        "tp_add:",
        "CLC", "LDA $03", "ADC $05", "STA $03",
        "LDA $04", "ADC $06", "STA $04",
        "RTS",

        "q_copy:",
        "JSR q_head",
        "LDY #$00",
        "qc_loop:",
        "LDA ($03),Y", f"STA ${BUF:04X},X", "INX", "INY", "CPY $02", "BNE qc_loop",
        "RTS",

        # q_items: ($0D) holds $0F records [ppu hi, lo, count, table lo, hi, shift, which];
        # each copies count bytes from table + (index << shift), index = ($0A + which).
        "q_items:",
        "LDY #$00",
        "qi_next:",
        "LDA ($0D),Y", "STA $00", "INY",
        "LDA ($0D),Y", "STA $01", "INY",
        "LDA ($0D),Y", "STA $02", "INY",
        "LDA ($0D),Y", "STA $05", "INY",
        "LDA ($0D),Y", "STA $06", "INY",
        "LDA ($0D),Y", "TAX", "INY",
        "LDA ($0D),Y", "INY",
        "STY $09",
        "TAY", "LDA $000A,Y",
        "JSR t_ptr",
        "JSR q_copy",
        "LDY $09",
        "DEC $0F", "BNE qi_next",
        "RTS",

        # load_screen: palette, then the 1 KB map one page per frame (rendering is off).
        "load_screen:",
        "LDA #$3F", "STA $2006", "LDA #$00", "STA $2006",
        "LDX #$00",
        "ls_pal:",
        f"LDA ${palette:04X},X", "STA $2007", "INX", "CPX #$20", "BNE ls_pal",
        f"LDA #${page & 0xFF:02X}", "STA $00", f"LDA #${page >> 8:02X}", "STA $01",
        "LDA #$20", "STA $02",
        "ls_page:",
        "JSR menu_frame",
        "LDA $02", "STA $2006", "LDA #$00", "STA $2006",
        "LDY #$00",
        "ls_byte:",
        "LDA ($00),Y", "STA $2007", "INY", "BNE ls_byte",
        "INC $01", "INC $02",
        "LDA $02", "CMP #$24", "BNE ls_page",
        "RTS",
    ]



class Blob:
    """Fixed-address data inside one claimed region."""

    def __init__(self, start, size):
        self.start, self.data = start, bytearray(b"\xFF" * size)
        self.labels = {}

    def put(self, label, addr, data, align=1):
        if addr % align or not self.start <= addr <= addr + len(data) <= self.start + len(self.data):
            raise ValueError(f"{label}: outside its region or misaligned")
        if any(b != 0xFF for b in self.data[addr - self.start:addr - self.start + len(data)]):
            raise ValueError(f"{label}: overlaps other data")
        self.data[addr - self.start:addr - self.start + len(data)] = data
        self.labels[label] = addr
        return addr


def item(ppu, count, table, shift, which=0):
    return bytes([ppu >> 8, ppu & 0xFF, count, table & 0xFF, table >> 8, shift, which])


def text16(text, width=16, fill=b" "):
    data = text.encode("ascii")
    return data + fill * (width - len(data))


def load_assets(path=ASSETS):
    assets = json.loads(Path(path).read_text())
    if assets.get("format") != convert.FORMAT or assets["meta"]["chr_bank"] != MENU_CHR:
        raise ValueError("unexpected MenuAssets format")
    return assets


def check_assets(base, assets, teams_path=TEAMS):
    """The art and team data must agree with the ROM they patch."""
    meta = assets["meta"]
    fonts = convert.font_patterns(base)
    glyphs = meta["font_glyphs"]
    if hashlib.sha256(b"".join(fonts[g] for g in glyphs)).hexdigest() != meta["font_sha256"]:
        raise ValueError("CHR $00 font glyphs differ from the ones the art was converted against")
    if fonts[convert.BLANK] != bytes(16):
        raise ValueError("CHR $00 tile $20 is not blank")
    indices = [t["index"] for t in assets["tiles"]]
    if len(indices) != len(set(indices)) or not all(0 <= i < 256 for i in indices):
        raise ValueError("tile indices must be unique bytes")
    for tile in assets["tiles"]:
        if ("font" in tile) == ("pattern" in tile) or tile.get("font", tile["index"]) != tile["index"]:
            raise ValueError(f"tile {tile['index']}: font tiles keep their ASCII id; art tiles carry a pattern")
        if "pattern" in tile and len(bytes.fromhex(tile["pattern"])) != 16:
            raise ValueError(f"tile {tile['index']}: pattern must be 16 bytes")
    if sorted(t["index"] for t in assets["tiles"] if "font" in t) != sorted(glyphs):
        raise ValueError("font tile list differs from the converted glyph list")
    teams = convert.team_records(teams_path)
    for t, record in zip(teams, assets["teams"]):
        name = read(base, SEL_BANK, 0x9400 + 16 * t["id"], 16)
        code = read(base, BRK_BANK, 0xB000 + 4 * t["id"], 4)
        if name != t["name"].ljust(14).encode() + b"\xFF\xFF" or code != t["code"].ljust(4).encode():
            raise ValueError(f"team {t['id']}: teams32.json disagrees with the ROM's name or code table")
        if (record["code"], record["name"].rstrip(), record["region"].strip()) != (t["code"], t["name"], t["region"]):
            raise ValueError(f"team {t['id']}: MenuAssets is stale against teams32.json")
    screens = assets["screens"]
    for name in ("selector", "bracket"):
        if len(bytes.fromhex(screens[name]["nametable"])) != 960 or len(bytes.fromhex(screens[name]["attributes"])) != 64:
            raise ValueError(f"{name}: map must be 960 tiles and 64 attribute bytes")
        if len(bytes.fromhex(screens[name]["palette"])) != 32:
            raise ValueError(f"{name}: palette must be 32 bytes")
    if len(assets["bracket"]["slots"]) != 63 or len(assets["bracket"]["highlights"]) != 32:
        raise ValueError("bracket needs 63 slots and 32 highlight states")
    if any(len(h) > 4 for h in assets["bracket"]["highlights"]):
        raise ValueError("a highlight may touch at most four attribute bytes")


def screen_map(assets, name):
    screen = assets["screens"][name]
    return bytes.fromhex(screen["nametable"]) + bytes.fromhex(screen["attributes"])


def menu_chr(base, assets):
    fonts = convert.font_patterns(base)
    data = bytearray(0x1000)
    for tile in assets["tiles"]:
        pattern = fonts[tile["font"]] if "font" in tile else bytes.fromhex(tile["pattern"])
        data[16 * tile["index"]:16 * tile["index"] + 16] = pattern
    return bytes(data)



def selector_data(assets):
    blob = Blob(SEL_DATA, 0x700)
    screen = assets["screens"]["selector"]
    regions = screen["regions"]
    teams = assets["teams"]
    palette = blob.put("palette", 0xA400, bytes.fromhex(screen["palette"]))
    flags = blob.put("flags", 0xA420, b"".join(bytes(t["flag"]) for t in teams))
    attrs = blob.put("attrs", 0xA460, bytes(regions["info_flag"]["attr"]["values"]))
    names = blob.put("names", 0xA800, b"".join(text16(t["name"]) for t in teams), align=0x100)
    places = blob.put("regions", 0xAA00, b"".join(text16(t["region"], 8) for t in teams), align=0x100)
    attr_ppu = 0x23C0 + regions["info_flag"]["attr"]["offset"]
    items = blob.put("items", 0xA480, b"".join((
        item(regions["info_flag"]["nt"], 2, flags, 1),
        item(attr_ppu, 1, attrs, 0),
        item(regions["info_name"]["nt"], 14, names, 4),
        item(regions["info_region"]["nt"], 7, places, 3),
    )))
    return blob, palette, items


def selector_code(assets, items):
    cards = assets["selector"]["cards"]
    x0, y0 = cards[0][0] * 8, cards[0][1] * 8
    for t, (col, row) in enumerate(cards):
        if (col * 8, row * 8) != (x0 + 32 * (t & 7), y0 + 32 * (t >> 3)):
            raise ValueError("selector cards must sit on a 32-pixel grid")
    cursor = assets["cursor_tile"]
    return [
        "sel_entry:",
        "SEI",
        "JSR menu_begin",
        f"LDA #${MENU_CHR:02X}", "JSR $C134",
        "JSR load_screen",
        "LDA #$00", f"STA ${ROW:04X}", f"STA ${COL:04X}",
        "LDA #$FF", f"STA ${CHOICE:04X}",
        "JSR sel_info", "JSR flush",
        "JSR sel_cursor",
        "JSR read_pad",
        f"LDA #${MASK:02X}", f"STA ${MENU_MASK:04X}",
        # The panel runs and the cursor sprites queued in one pass land in the same vblank.
        "sel_loop:",
        "JSR menu_frame",
        "JSR read_pad",
        f"LDA ${NEW:04X}", "BMI sel_commit",
        "AND #$0F", "BEQ sel_idle",
        "JSR sel_move",
        "sel_idle:",
        "JSR sel_cursor",
        "JMP sel_loop",
        "sel_commit:",
        "JSR sel_team", f"STA ${CHOICE:04X}",
        f"LDA #${SFX_CONFIRM:02X}", "JSR $C249",
        "sel_release:",
        "JSR menu_frame", "JSR read_pad",
        f"LDA ${PAD:04X}", "BNE sel_release",
        "JSR menu_end",
        "JMP $9620",

        # Right/Left step through team ids with wrap; Up/Down change rows with wrap.
        "sel_move:",
        "LSR A", "BCS sm_right",
        "LSR A", "BCS sm_left",
        "LSR A", "BCS sm_down",
        f"DEC ${ROW:04X}", "JMP sm_wrap",
        "sm_down:",
        f"INC ${ROW:04X}", "JMP sm_wrap",
        "sm_left:",
        f"DEC ${COL:04X}", "BPL sm_wrap",
        "LDA #$07", f"STA ${COL:04X}", f"DEC ${ROW:04X}", "JMP sm_wrap",
        "sm_right:",
        f"INC ${COL:04X}", f"LDA ${COL:04X}", "CMP #$08", "BCC sm_wrap",
        "LDA #$00", f"STA ${COL:04X}", f"INC ${ROW:04X}",
        "sm_wrap:",
        f"LDA ${ROW:04X}", "AND #$03", f"STA ${ROW:04X}",
        f"LDA #${SFX_MOVE:02X}", "JSR $C249",
        "JMP sel_info",

        "sel_team:",
        f"LDA ${ROW:04X}", "ASL A", "ASL A", "ASL A", f"ORA ${COL:04X}",
        "RTS",

        "sel_info:",
        "JSR sel_team", "STA $0A",
        f"LDA #${items & 0xFF:02X}", "STA $0D", f"LDA #${items >> 8:02X}", "STA $0E",
        "LDA #$04", "STA $0F",
        "JMP q_items",

        # Four corner sprites around the card; every 16 frames they close in a pixel.
        "sel_cursor:",
        f"LDA ${MENU_FRAME:04X}", "AND #$10", "BEQ sc_phase",
        "LDA #$01",
        "sc_phase:",
        "STA $05",
        "LDA #$03", "SEC", "SBC $05", "STA $05",
        f"LDA ${COL:04X}", "ASL A", "ASL A", "ASL A", "ASL A", "ASL A", "CLC", f"ADC #${x0:02X}", "STA $06",
        f"LDA ${ROW:04X}", "ASL A", "ASL A", "ASL A", "ASL A", "ASL A", "CLC", f"ADC #${y0:02X}", "STA $07",
        "LDA $06", "SEC", "SBC $05", "STA $0203", "STA $020B",
        "LDA $06", "CLC", "ADC #$08", "CLC", "ADC $05", "STA $0207", "STA $020F",
        "LDA $07", "SEC", "SBC $05", "SEC", "SBC #$01", "STA $0200", "STA $0204",
        "LDA $07", "CLC", "ADC #$06", "CLC", "ADC $05", "STA $0208", "STA $020C",
        f"LDA #${cursor:02X}", "STA $0201", "STA $0205", "STA $0209", "STA $020D",
        "LDA #$00", "STA $0202", "LDA #$40", "STA $0206",
        "LDA #$80", "STA $020A", "LDA #$C0", "STA $020E",
        "RTS",
    ]



def bracket_data(assets):
    blob = Blob(BRK_DATA, 0xA00)
    screen, tree = assets["screens"]["bracket"], assets["bracket"]
    regions, teams = screen["regions"], assets["teams"]
    palette = blob.put("palette", 0x9400, bytes.fromhex(screen["palette"]))
    slot_hi = blob.put("slot_hi", 0x9420, bytes(a >> 8 for a in tree["slots"]))
    slot_lo = blob.put("slot_lo", 0x9460, bytes(a & 0xFF for a in tree["slots"]))
    chips = blob.put("chips", 0x94A0, b"".join(bytes(t["chip"]) for t in teams)
                     + bytes(assets["empty_chip"]) + bytes([convert.BLANK] * 2))
    count = bytearray(32)
    offsets, lit, dim = bytearray(128), bytearray(128), bytearray(128)
    static = bytes.fromhex(screen["attributes"])
    for m, changes in enumerate(tree["highlights"]):
        count[m] = len(changes)
        for k, (offset, value) in enumerate(changes):
            offsets[4 * m + k], lit[4 * m + k], dim[4 * m + k] = 0xC0 | offset, value, static[offset]
    hl_count = blob.put("hl_count", 0x9500, bytes(count))
    hl_off = blob.put("hl_off", 0x9520, bytes(offsets))
    hl_val = blob.put("hl_val", 0x9600, bytes(lit + dim), align=0x100)
    rounds = blob.put("rounds", 0x9700, b"".join(
        text16(convert.round_label(tree["rounds"], m)) for m in range(32)), align=0x100)
    matches = blob.put("matches", 0x9900, b"".join(
        text16(f"MATCH {m + 1:02d}" if m < 31 else "", 8) for m in range(32)), align=0x100)
    versus = blob.put("versus", 0x9A00, b"".join(b"VS" if m < 31 else b"  " for m in range(32)))
    names = blob.put("names", 0x9B00, b"".join(text16(t["name"]) for t in teams) + text16("") * 2,
                     align=0x100)
    panel = blob.put("panel", 0x95A0, b"".join((
        item(regions["round"]["nt"], 14, rounds, 4),
        item(regions["match"]["nt"], 8, matches, 3),
        item(regions["vs"]["nt"], 2, versus, 1),
        item(regions["chip_a"]["nt"], 2, chips, 1, 1),
        item(regions["name_a"]["nt"], 14, names, 4, 1),
        item(regions["chip_b"]["nt"], 2, chips, 1, 2),
        item(regions["name_b"]["nt"], 14, names, 4, 2),
    )))
    return blob, dict(palette=palette, slot_hi=slot_hi, slot_lo=slot_lo, chips=chips,
                      hl_count=hl_count, hl_off=hl_off, hl_val=hl_val, panel=panel)


def bracket_code(d):
    return [
        "brk_entry:",
        "JSR menu_begin",
        # The heap is read once, while both CHR latches are below $10. Slot 63 is never read.
        "LDX #$00",
        "bc_copy:",
        "LDA $7700,X", f"STA ${CACHE:04X},X", "INX", "CPX #$3F", "BNE bc_copy",
        f"LDA #${MENU_CHR:02X}", "JSR $C134",
        "JSR load_screen",
        "JSR brk_state",
        "JSR brk_slots",
        "LDA #$00", "STA $08", "JSR brk_attr",
        "JSR brk_panel",
        "JSR flush",
        # The stock $8680 decision, including its $07F0 write.
        "LDA $07FC", "CMP #$1F", "BCC bm_keep", "LDA #$01", "STA $07F0",
        "bm_keep:",
        "JSR read_pad",
        f"LDA #${MASK:02X}", f"STA ${MENU_MASK:04X}",
        "LDA $07F0", "BNE bv_loop",
        "LDA #$00", f"STA ${CURSOR:04X}",
        "bi_loop:",
        "JSR menu_frame", "JSR brk_blink", "JSR read_pad",
        f"LDA ${NEW:04X}", "BPL bi_loop",
        "JSR brk_confirm",
        "JMP $8162",
        "bv_loop:",
        "JSR menu_frame", "JSR brk_blink", "JSR read_pad",
        f"LDA ${NEW:04X}", "AND #$C0", "BEQ bv_loop",
        "JSR brk_confirm",
        "JMP $86C7",

        "brk_confirm:",
        f"LDA #${SFX_CONFIRM:02X}", "JSR $C249",
        "bcf_wait:",
        "JSR menu_frame", "JSR read_pad",
        f"LDA ${PAD:04X}", "BNE bcf_wait",
        "JMP menu_end",

        # $0A = shown match (0-31), $0B/$0C = its teams; 32 = unknown team, 33 = none.
        "brk_m:",
        "LDA $07FC", "CMP #$1F", "BCC bmc_ok", "LDA #$1F",
        "bmc_ok:",
        "STA $0A",
        "RTS",
        "brk_state:",
        "JSR brk_m",
        "CMP #$1F", "BEQ bs_champ",
        "ASL A", "TAX",
        f"LDA ${CACHE:04X},X", "JSR bs_valid", "STA $0B",
        f"LDA ${CACHE + 1:04X},X", "JSR bs_valid", "STA $0C",
        "RTS",
        "bs_champ:",
        f"LDA ${CACHE + 62:04X}", "JSR bs_valid", "STA $0B",
        "LDA #$21", "STA $0C",
        "RTS",
        "bs_valid:",
        "CMP #$20", "BCC bsv_ok", "LDA #$20",
        "bsv_ok:",
        "RTS",

        # Every slot below 32+m holds a played or seeded team; later slots are undecided.
        "brk_slots:",
        "LDA $0A", "CLC", "ADC #$20", "STA $09",
        "LDX #$00",
        "bsl_next:",
        f"LDA ${d['slot_hi']:04X},X", "STA $2006",
        f"LDA ${d['slot_lo']:04X},X", "STA $2006",
        "LDY #$40",
        "CPX $09", "BCS bsl_put",
        f"LDA ${CACHE:04X},X", "CMP #$20", "BCS bsl_put",
        "ASL A", "TAY",
        "bsl_put:",
        f"LDA ${d['chips']:04X},Y", "STA $2007",
        f"LDA ${d['chips'] + 1:04X},Y", "STA $2007",
        "INX", "CPX #$3F", "BNE bsl_next",
        "RTS",

        # The shown match's plates turn gold for 24 frames in every 32.
        "brk_blink:",
        f"LDA ${MENU_FRAME:04X}", "AND #$1F", "BEQ bb_lit",
        "CMP #$18", "BNE bb_none",
        "LDA #$80", "BNE bb_go",
        "bb_lit:",
        "LDA #$00",
        "bb_go:",
        "STA $08",
        "JSR brk_m",
        # brk_attr: queue match $0A's attribute bytes, lit ($08=0) or resting ($08=$80).
        "brk_attr:",
        "LDY $0A",
        f"LDA ${d['hl_count']:04X},Y", "BEQ bb_none",
        "STA $07",
        "TYA", "ASL A", "ASL A", "STA $09",
        "ba_next:",
        "LDA #$23", "STA $00",
        "LDX $09", f"LDA ${d['hl_off']:04X},X", "STA $01",
        "LDA #$01", "STA $02",
        "JSR q_head",
        "STX $06",
        "LDA $09", "CLC", "ADC $08", "TAY",
        f"LDA ${d['hl_val']:04X},Y",
        "LDX $06", f"STA ${BUF:04X},X",
        "INC $09",
        "DEC $07", "BNE ba_next",
        "bb_none:",
        "RTS",

        "brk_panel:",
        f"LDA #${d['panel'] & 0xFF:02X}", "STA $0D", f"LDA #${d['panel'] >> 8:02X}", "STA $0E",
        "LDA #$07", "STA $0F",
        "JMP q_items",
    ]


def assemble_bank(lines, origin, limit=0x400):
    code, labels = assemble(lines, origin)
    if len(code) > limit:
        raise ValueError(f"code at ${origin:04X} is {len(code)} bytes; region holds {limit}")
    return code, labels


def queued(records):
    """VRAM buffer bytes a run of 7-byte item records queues: a 3-byte header plus its count each."""
    return sum(3 + records[i + 2] for i in range(0, len(records), 7))


def change_manifest(base, assets=None):
    assets = assets or load_assets()
    check_dependencies(base)
    check_assets(base, assets)
    if hashlib.sha256(read(base, "chr", MENU_CHR * 0x1000, 0x1000)).hexdigest() != CHR19_SHA256:
        raise ValueError(f"CHR bank ${MENU_CHR:02X} is not the reclaimed stock copy")

    sel_blob, sel_palette, sel_items = selector_data(assets)
    sel_code, sel_labels = assemble_bank(runtime(sel_palette, SEL_MAP) + selector_code(assets, sel_items), SEL_CODE)
    brk_blob, brk = bracket_data(assets)
    brk_code, brk_labels = assemble_bank(runtime(brk["palette"], BRK_MAP) + bracket_code(brk), BRK_CODE)
    # One selector move queues the info panel; the bracket queues its highlight and panel once.
    sel_queue = queued(bytes(sel_blob.data[sel_items - SEL_DATA:][:4 * 7]))
    brk_queue = 4 * 4 + queued(bytes(brk_blob.data[brk["panel"] - BRK_DATA:][:7 * 7]))
    if BUF + BUF_SIZE > CACHE or max(sel_queue, brk_queue) > BUF_SIZE:
        raise ValueError("queued VRAM runs exceed the $0300 buffer")

    def padded(code, size):
        return code + b"\xFF" * (size - len(code))

    changes = (
        (SEL_BANK, 0x8000, "selector-entry", b"\x4C" + word(sel_labels["sel_entry"])),
        (SEL_BANK, SEL_CODE, "selector-code", padded(sel_code, 0x400)),
        (SEL_BANK, SEL_DATA, "selector-data", bytes(sel_blob.data)),
        (SEL_BANK, SEL_MAP, "selector-map", screen_map(assets, "selector")),
        (BRK_BANK, 0x8000, "bracket-entry", b"\x4C" + word(brk_labels["brk_entry"])),
        (BRK_BANK, BRK_CODE, "bracket-code", padded(brk_code, 0x400)),
        (BRK_BANK, BRK_DATA, "bracket-data", bytes(brk_blob.data)),
        (BRK_BANK, BRK_MAP, "bracket-map", screen_map(assets, "bracket")),
        ("chr", MENU_CHR * 0x1000, "menu-chr", menu_chr(base, assets)),
    )
    hooks = {"selector-entry": bytes.fromhex("78 2C 02"), "bracket-entry": bytes.fromhex("EA EA EA")}
    out = []
    for bank, addr, name, after in changes:
        before = read(base, bank, addr, len(after))
        if name in hooks and before != hooks[name]:
            raise ValueError(f"{name}: unexpected hook bytes")
        if name not in hooks and name != "menu-chr" and before != b"\xFF" * len(after):
            raise ValueError(f"{name}: reservation is not free space")
        out.append(Change(name, bank, addr, before, after))
    return tuple(out)


def labels(assets=None):
    """Assembled label addresses of both banks (tests and probes use them)."""
    assets = assets or load_assets()
    _, sel_palette, sel_items = selector_data(assets)
    _, sel = assemble(runtime(sel_palette, SEL_MAP) + selector_code(assets, sel_items), SEL_CODE)
    _, brk = bracket_data(assets)
    _, brk_labels = assemble(runtime(brk["palette"], BRK_MAP) + bracket_code(brk), BRK_CODE)
    return {"selector": sel, "bracket": brk_labels}


def build_rom(base, assets=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected visualtables32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned visualtables32")
    regions = {r.name: r for r in REGIONS}
    rom, claimed, names = bytearray(base), set(), set()
    for c in change_manifest(base, assets):
        region = regions.get(c.name)
        if (region is None or c.name in names or c.bank != region.bank
                or not c.after or len(c.before) != len(c.after)
                or not region.start <= c.addr < c.addr + len(c.after) <= region.end):
            raise ValueError(f"{c.name}: overlapping, invalid or unowned change")
        start = locate(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        if claimed & span:
            raise ValueError(f"{c.name}: overlapping change")
        if base[start:start + len(c.before)] != c.before:
            raise ValueError(f"{c.name}: unexpected input bytes")
        claimed.update(span)
        names.add(c.name)
        rom[start:start + len(c.after)] = c.after
    if names != set(regions):
        raise ValueError("incomplete menuart32 manifest")
    return bytes(rom)


def diff_manifest(base, rom, assets=None):
    return {
        "input_sha256": hashlib.sha256(base).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "assets_sha256": hashlib.sha256(convert.dumps(assets or load_assets()).encode()).hexdigest(),
        "ranges": [
            {"name": c.name, "bank": c.bank, "address": c.addr, "file_offset": locate(c.bank, c.addr),
             "size": len(c.after),
             "before_sha256": hashlib.sha256(c.before).hexdigest(),
             "after_sha256": hashlib.sha256(c.after).hexdigest(),
             "changed_file_offsets": [locate(c.bank, c.addr) + i for i, (a, b)
                                      in enumerate(zip(c.before, c.after)) if a != b]}
            for c in change_manifest(base, assets)
        ],
    }


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    protected = [ROOT / "build/visualtables32.nes", source.resolve().parent / "visualtables32.nes",
                 source.resolve(), ASSETS, TEAMS]
    protected.extend((ROOT / "data").glob("*"))
    protected.extend((ROOT / "art/menu32").rglob("*"))
    for path in protected:
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise ValueError(f"output aliases protected input {path}")
    if output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() in PROTECTED_SHA256:
        raise ValueError("output aliases protected input ROM artifact")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path)
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
        print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
