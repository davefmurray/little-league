#!/usr/bin/env python3
"""Draw the Power Analysis card on the pinned stockart32 ROM.

    .venv/bin/python -B tools/build_analysisart32.py build/stockart32.nes -o build/analysisart32.nes
    .venv/bin/python -B tools/build_analysisart32.py build/stockart32.nes -o OUT [--assets DIR] [--manifest]

--assets names the directory tools/analysisart32_convert.py fills (default build/analysisart32). Its
analysisassets.json must carry the digest data/analysisart32/digests.json records, and so must the
built ROM, before anything is written. --manifest prints the exact before/after manifest, computed
from the two ROM images.

Scenes $14 (init) and $15 (loop) keep their stock state machine, timers, A/B test, confirm SFX $35
and return to scene $0C, which reopens the shared picker on the same team. The init's stock prologue
($AF58-$AF7F: hide OAM, scroll 0, $B8/$047A/$BA-$BF := 0, sprite palette #$8A, hold $2C, blank) and
tail ($AF92: release $2C, scene $15, $C0 := $10) stay. Between them:

  bank 3  $AF80  LDA #0, JSR $BD20 (hop pad), JSR numerals, JMP $AF92; the old metatile map, label,
                 flag and name calls become NOPs
          $AF9B  RTS: card() already applied CHR preset 2
          $AFB9  state 1 jumps to balls() instead of the stock radar $AFF8
          $BD20  hop pad, byte-identical in bank 13: switch to 13 through $C14E, card(), back to 3
          $BD30  numerals(): four digits from the ratings record $BC80 + 4 * team; balls(): one ball
                 sprite (OAM slots 17-32) per point of the stepper's $BC-$BF; their tables
  bank 13 $A000  the 1 KB nametable and attributes
          $A400  palette, ball colors, flag x and name column per team, card():
                 $32 := 0, copy the screen, stage the palette, wait for the NMI's $04E6 store, the stock
                 flag writer $CB56 and name writer $C9A8 at the centered column, CHR preset 2,
                 $26 := $06 (CHR $06 below the stock sprite-0 split), wait for the next NMI
  CHR $06 $BA-$FF  new patterns; $00-$B9, the stockart32 mode screen, stay byte-identical

The two NMI waits clear $04E6 and spin until the NMI's short path (fixed $CD8A, taken while the init
holds $2C) stores $2C there, so the card releases on stock's frame and leaves $04E6 = 1 as stock does.
Every bank change goes through $C14E, keeping $27/$2D coherent for the NMI's audio tick. The fixed
bank, CHR $00/$18/$1B, the ratings and every other byte stay identical; the guards pin what the card
reads and calls.
"""
import argparse
import json
import os
from pathlib import Path
import sys

from build_bank11 import assemble
from build_draw32 import ROOT, Region, apply_changes, check_guards, claim, locate, read, refuse_aliases, sha256
from build_scoreart32 import refuse_inside, write_atomic
import build_stockart32 as prior
from build_teamnames32 import HEADER, ROM_SIZE
import analysisart32_assets as model
from analysisart32_assets import AnalysisAssets, AssetError

BASE_SHA256 = "a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55"   # accepted stockart32
PROTECTED_SHA256 = prior.PROTECTED_SHA256 | {BASE_SHA256}
BUILD = ROOT / "build"
ASSETS = BUILD / "analysisart32"
OUTPUT = BUILD / "analysisart32.nes"
REGISTRY = ROOT / "data/analysisart32/digests.json"
REGISTRY_FORMAT = "analysisart32-digests/1"
ASSET_JSON = "analysisassets.json"
EVIDENCE = (BUILD / "stockart32", BUILD / "analysisart32-design", BUILD / "vendor")

HOME, FAR = model.HOME_BANK, model.FAR_BANK
PAD, HOME_CODE, HOME_END = 0xBD20, 0xBD30, 0xBDB8
SCREEN, FAR_DATA, FAR_END = 0xA000, 0xA400, 0xA500
BALL_COLORS, FLAG_X, NAME_COL, FAR_CODE = 0xA410, 0xA420, 0xA440, 0xA460
HOOK, TAIL, STATE1, STOCK_TAIL = 0xAF80, 0xAF9B, 0xAFB9, 0xAF92
FIRST_BALL_SLOT = 17                  # the stock radar's first slot; sprite 0 is slot 0, the flag 1-9
CHR06 = model.MODE_CHR * 0x1000
NEW_CHR = Region("chr06-new", "chr", CHR06 + 16 * model.FIRST_FREE, CHR06 + 0x1000)

REGIONS = (
    Region("init-hook", HOME, HOOK, STOCK_TAIL),
    Region("init-tail", HOME, TAIL, 0xAFA0),
    Region("state1-draw", HOME, STATE1, 0xAFBC),
    Region("home-pad", HOME, PAD, HOME_CODE),
    Region("home-code", HOME, HOME_CODE, HOME_END),
    Region("far-screen", FAR, SCREEN, FAR_DATA),
    Region("far-code", FAR, FAR_DATA, FAR_END),
    Region("far-pad", FAR, PAD, PAD + 0x10),
    NEW_CHR,
)
STOCK = {
    "init-hook": "20 C4 C5 03 18 18 20 20 40 C8 FB B1 20 E2 B1 20 D2 B1",
    "init-tail": "A9 02 4C C1 C6",
    "state1-draw": "4C F8 AF",
}
DEPENDENCIES = (
    ("scene $14 prologue $AF58-$AF7F", HOME, 0xAF58, "20 99 C1 20 9F CA 85 B8 8D 7A 04 85 B8 85 BA 85 BB 85 BC 85 BD"
     " 85 BE 85 BF A9 8A 20 A4 C1 A9 12 20 A4 C1 E6 2C 20 60 C2"),
    ("scene $14 tail $AF92-$AF9A", HOME, STOCK_TAIL, "C6 2C EE 7B 04 A9 10 85 C0"),
    ("scene $15 loop $AFA0-$AFB8", HOME, 0xAFA0, "A5 B8 20 32 C2 AB AF B6 AF BC AF C6 C0 D0 06 A9 08 85 C0 E6 B8 60"
     " 20 CC AF"),
    ("A/B exit $AFBC", HOME, 0xAFBC, "A5 91 29 C0 F0 F3 A9 0C 8D 7B 04 A9 35 4C 49 C2"),
    ("stepper $AFCC", HOME, 0xAFCC, "C6 C0 D0 27 A9 08 85 C0 AD EF 04 0A 0A 09 03 A8 A2 03 A9 00 85 00 B9 80 BC D5 BC"
     " F0 04 E6 00 F6 BC 88 CA 10 F1 A5 00 D0 02 E6 B8 60"),
    ("stock name call $B1D2", HOME, 0xB1D2, "A9 20 8D B3 06 A9 68 8D B4 06 AD EF 04 4C A8 C9"),
    ("stock flag call $B1E2", HOME, 0xB1E2, "A9 04 8D 7F 04 A9 15 85 04 A9 20 85 05 AE EF 04 20 56 CB A9 14 8D 7F 04"
     " 60"),
    ("PRG writer $C14C", 15, 0xC14C, "A5 27 85 27 E6 2D 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF C6"
     " 2D 60"),
    ("CHR preset $C6C1", 15, 0xC6C1, "0A 8D 00 02 0A 6D 00 02 AA BD 4E FB 30 07 85 23 BD 4F FB 85 24 BD 50 FB 30 07"
     " 85 25 BD 51 FB 85 26 BD 52 FB 8D 00 02 A9 FE 8D 01 02 A9 20 8D 02 02 A9 F8 8D 03 02 BD 4D FB 8D 7A 04 60"),
    ("CHR preset 2 record $FB59", 15, 0xFB59, "06 1B 1B 18 18 40"),
    ("NMI short path stores $2C in $04E6 $CD8A", 15, 0xCD8A, "A5 2C 8D E6 04 D0 50"),
    ("main loop consumes $04E6 $CC14", 15, 0xCC14, "AD E6 04 F0 0C E6 2C 20 BD CE A9 00 8D E6 04 C6 2C"),
    ("NMI sprite-0 split $CDF5", 15, 0xCDF5, "A5 2D D0 64 2C 02 20 70 FB 2C 02 20 30 02 50 F9 AD 7A 04 29 01 F0 21"),
    ("NMI split CHR1 reload $CE39", 15, 0xCE39, "AD 7A 04 29 02 F0 1D A5 26 4C 34 C1"),
    ("name font flags $FD20", 15, model.FONT_FLAGS, "00 00 80 80 00 00 00 00 00 00 00 00 00 00 00 00 20 20 A0 20 20 20"
     " 20 A0 20 20 20 20 20 20 20 A0"),
    ("stock flag writer $CB56", 15, model.FLAG_WRITER, "A9 03 85 00 A5 27 85 2E A9 04 20 4E C1 4C 00 9B"),
    ("flag writer: teams $10-$1F hide their slots, bank 4 $9B00", model.FLAG_BANK, 0x9B00, "E0 10 B0 06 BC 5A 97 4C 66"
     " CB"),
    ("NMI vector", 15, 0xFFFA, "85 CD"),
)
DIGESTS = (
    ("fixed bank $C000-$FFFF", 15, 0xC000, 0x4000, "c38587dc7ee5601a742bf1da30453fc06b303946a39d4d6d398128ac4c5aabb9"),
    ("CHR $00 font", "chr", 0x0000, 0x1000, "771012bc129730fbef4c9bd840bf68f91329d625bfde1f75c0a5940400d2ea32"),
    ("CHR $18 name font", "chr", 0x18000, 0x1000, "8a058223e5f2c3ab5579395148463c000a5ac93d4eed6f014ba1507dbf56e769"),
    ("CHR $1B sprites, flags and ball", "chr", 0x1B000, 0x1000,
     "330afeaa1a18c62cbb0fe1bd39101da67efac96812a43109449737dc1301b5bb"),
    ("CHR $06 $00-$B9 stockart32 mode tiles", "chr", CHR06, 16 * model.FIRST_FREE,
     "74377907abad07a7fe53ee2740b200c135f177d49bb8d2993ede674cf61af73f"),
    ("bank 13 $8000-$9FFF modeart32 and stockart32 mode screen, pad, code and run lists", FAR, 0x8000, 0x2000,
     "80caac1ce8f2d71327ecbd02b83fc62eb772ffab6f66e279313710fa6a470ae1"),
    ("bank 13 $A500-$BD1F", FAR, FAR_END, PAD - FAR_END, "2cd95b9ebb221ae57aa4f429222e176a8b25ae0f8864c8ad4b661eab684353fc"),
    ("bank 13 $BD30-$BFFF", FAR, PAD + 0x10, 0xC000 - PAD - 0x10, "c7cb2daf2491b13bc4e1340b99b7750d6e75e766e2639c4737880e0186cc295a"),
    ("bank 3 $8000-$AF7F up to the scene $14 prologue's end", HOME, 0x8000, HOOK - 0x8000, "1027beea6340b8aea6162ca499bbf156174295ca66e1a7ba3629b9975055bd10"),
    ("bank 3 $AF92-$AF9A scene $14 tail", HOME, STOCK_TAIL, TAIL - STOCK_TAIL, "4d271f1883332eae21c444783b9d30a02ffae8e1cc4833700d3a966d58408ff6"),
    ("bank 3 $AFA0-$AFB8 scene $15 loop", HOME, 0xAFA0, STATE1 - 0xAFA0, "03807ce1df3b57550e00bbb2596d22475991f6cf0c59161ed0661d7fd07e5793"),
    ("bank 3 $AFBC-$BD1F exit, stepper, stock chart, labels, ratings and batting bias", HOME, 0xAFBC, PAD - 0xAFBC,
     "8e3514d2f956d636359c5de5bd68d5aa176e58aa590e30623d8d76a0fc44e19c"),
    ("bank 3 $BDB8-$BFFF", HOME, HOME_END, 0xC000 - HOME_END, "4df8f8601e1388630f7d2aa31218823a7d8aedc7d349c319bb15f3378a5f2d7e"),
    ("bank 1 team name records $9180-$927F", 1, 0x9180, 0x100, "d3128a095bfce53661a98f01cfd4226d92dc60ea0a416f9e43873f192fd75aa5"),
    ("bank 1 team name records $BCC0-$BDBF", 1, 0xBCC0, 0x100, "5baef784eeb778e021d617514a5766e249b9e00ebb9bc51da0fbf9b85d4be5a6"),
    ("bank 4 name font tables $8000-$83FF", model.FLAG_BANK, 0x8000, 0x400,
     "26bd3455657fe1777bcc0aaa2955b38bd3fa27ce3e1ba51b05d8db6a6ed4167e"),
    ("bank 4 flag pointers and sprites $975A-$9889", model.FLAG_BANK, 0x975A, 0x130, "6a079f153b780ac5947e58234e7b249fa1b2eed269cef210bad4cc73403fba62"),
    ("bank 4 flag writer $9B00-$9B27", model.FLAG_BANK, 0x9B00, 0x28, "216986224f61ee509a75e3f2b718251ffc32be04cd1e2a3e838844b21e23d1e1"),
)
FLAG_POINTERS, FLAG_SPRITES, FLAGS = 0x975A, 0x976A, 16



def hop_pad():
    """PHA, switch to bank 13, PLA, card(), switch to bank 3, RTS: identical bytes in both banks, so each
    $C14E call returns into the same instruction stream."""
    code, _ = assemble(["PHA", f"LDA #${FAR:02X}", "JSR $C14E", "PLA", f"JSR ${FAR_CODE:04X}",
                        f"LDA #${HOME:02X}", "JSR $C14E", "RTS"], PAD)
    if len(code) != 16 or code[6] != 0x68 or code[15] != 0x60:
        raise ValueError("the hop pad must resume at $BD26 in bank 13 and at $BD2F in bank 3")
    return code


def wait_nmi(n):
    """Clear $04E6 and spin until the NMI's short path stores the held $2C there."""
    return ["LDA #$00", "STA $04E6", f"wait{n}:", "LDA $04E6", f"BEQ wait{n}"]


def far_code(assets):
    """Bank 13 $A460, request 0: the static card. The caller holds $2C; rendering is off."""
    asm = [
        "LDA #$00", "STA $32",
        "LDA #$20", "STA $2006", "LDA #$00", "STA $2006",
        "STA $00", f"LDA #${SCREEN >> 8:02X}", "STA $01",
        "LDX #$04", "LDY #$00",
        "copy:",
        "LDA ($00),Y", "STA $2007", "INY", "BNE copy",
        "INC $01", "DEX", "BNE copy",
        "LDX #$0F",
        "pal:",
        f"LDA ${FAR_DATA:04X},X", "STA $0195,X", "DEX", "BPL pal",
    ]
    slot = 0x0195 + 16 + 4 * assets.ball_palette + 1
    for i in range(3):
        asm += [f"LDA ${BALL_COLORS + i:04X}", f"STA ${slot + i:04X}"]
    asm += ["INC $01B5", *wait_nmi(1),
            "LDA #$04", "STA $047F",
            f"LDA #${assets.flag_y:02X}", "STA $04",
            "LDX $04EF", f"LDA ${FLAG_X:04X},X", "STA $05",
            f"JSR ${model.FLAG_WRITER:04X}",
            "LDA #$14", "STA $047F",
            "LDA #$20", "STA $06B3",
            "LDX $04EF", f"LDA ${NAME_COL:04X},X", "STA $06B4",
            "LDA $04EF", f"JSR ${model.NAME_WRITER:04X}",
            "LDA #$02", "JSR $C6C1",
            f"LDA #${model.MODE_CHR:02X}", "STA $26",
            *wait_nmi(2), "RTS"]
    code, labels = assemble(asm, FAR_CODE)
    if FAR_CODE + len(code) > FAR_END:
        raise ValueError(f"card() is {len(code)} bytes; it must end by ${FAR_END - 1:04X}")
    return code, labels


def home_code(assets):
    """Bank 3 $BD30: numerals() and balls(), then their tables: digit addresses, digit tiles, ball rows and
    columns. Every table is generated from the assets' one stats-by-sockets geometry."""
    asm = [
        "numerals:",
        "LDA $04EF", "ASL A", "ASL A", "TAY",
        "LDX #$00",
        "n_loop:",
        "LDA num_hi,X", "STA $2006", "LDA num_lo,X", "STA $2006",
        f"STY $00", f"LDA ${model.RATINGS:04X},Y", "TAY", "LDA digit,Y", "STA $2007", "LDY $00",
        "INY", "INX", "CPX #$04", "BNE n_loop",
        "RTS",
        "balls:",
        f"LDX #${4 * FIRST_BALL_SLOT:02X}", "LDY #$03",
        "b_row:",
        "LDA #$00", "STA $00",
        "b_pip:",
        "LDA $00", "CMP $00BC,Y",
        "LDA #$F0", "BCS b_put", "LDA pip_y,Y",
        "b_put:",
        "STA $0200,X",
        f"LDA #${assets.ball_tile:02X}", "STA $0201,X",
        f"LDA #${assets.ball_palette:02X}", "STA $0202,X",
        "STY $01", "LDY $00", "LDA pip_x,Y", "LDY $01", "STA $0203,X",
        "INX", "INX", "INX", "INX",
        "INC $00", "LDA $00", "CMP #$04", "BNE b_pip",
        "DEY", "BPL b_row",
        "RTS",
    ]
    addresses = [0x2000 + model.COLUMNS * s.row + s.digit_col for s in assets.stats]
    tables = (bytes(a >> 8 for a in addresses) + bytes(a & 0xFF for a in addresses)
              + bytes((model.BLANK, *assets.digits)) + bytes(8 * s.row - 1 for s in assets.stats)
              + bytes(8 * c for c in assets.socket_cols))
    names = {"num_hi": 0, "num_lo": 4, "digit": 8, "pip_y": 13, "pip_x": 17}

    def at(origin):
        lines = []
        for line in asm:
            for name, offset in names.items():
                line = line.replace(name, f"${origin + offset:04X}") if not line.endswith(":") else line
            lines.append(line)
        return assemble(lines, HOME_CODE)
    code, _ = at(HOME_CODE + 0x60)
    code, labels = at(HOME_CODE + len(code))
    block = code + tables
    if HOME_CODE + len(block) > HOME_END:
        raise ValueError(f"the bank-3 block is {len(block)} bytes; $BD30-$BDB7 holds {HOME_END - HOME_CODE}")
    tables_at = {name: HOME_CODE + len(code) + offset for name, offset in names.items()}
    return block, labels, tables_at


def hook_code(numerals):
    code, _ = assemble(["LDA #$00", f"JSR ${PAD:04X}", f"JSR ${numerals:04X}", f"JMP ${STOCK_TAIL:04X}"], HOOK)
    return code + b"\xEA" * (STOCK_TAIL - HOOK - len(code))



def check_runtime(base, assets):
    """The assets keep every value the stock writers, fonts, sprites and split depend on."""
    ratings = model.AnalysisRatings.from_rom(base)
    if tuple(s.stat for s in assets.stats) != ratings.meaning:
        raise AssetError(f"the stats must follow the derived stored order {', '.join(ratings.meaning)}")
    if any(read(base, NEW_CHR.bank, NEW_CHR.start, NEW_CHR.end - NEW_CHR.start)):
        raise AssetError(f"CHR $06 ${model.FIRST_FREE:02X}-$FF is not blank in the input")
    mode = model.mode_screen_ids(base)
    if not mode <= set(range(model.FIRST_FREE)):
        raise AssetError(f"the mode screen shows CHR $06 ids {sorted(mode - set(range(model.FIRST_FREE)))} the card "
                         "would claim")
    chr06 = bytearray(read(base, "chr", CHR06, 0x1000))
    stock06 = {bytes(chr06[16 * t:16 * t + 16]) for t in range(model.FIRST_FREE)}
    split = set(assets.split_ids)
    for tile, pattern in assets.new_tiles.items():
        if pattern in stock06 and tile not in split:
            raise AssetError(f"new tile ${tile:02X} repeats a stockart32 mode pattern; reuse its id")
        chr06[16 * tile:16 * tile + 16] = pattern
    chr00 = read(base, "chr", 0, 0x1000)
    chr18 = read(base, "chr", model.TITLE_CHR * 0x1000, 0x1000)
    lettered = ({ch for s in assets.stats for ch in s.stat} | {ch for _, _, words in assets.text for ch in words}
                | {str(v) for v in model.SCALE} | set(assets.glyphs))
    for ch in sorted(lettered - {" "}):
        source = chr00[16 * ord(ch):16 * ord(ch) + 16]
        tile = model.glyph_id(ch, assets.glyphs)
        if not any(source) or bytes(chr06[16 * tile:16 * tile + 16]) != model.ink2(source):
            raise AssetError(f"CHR $06 ${tile:02X} must show the CHR $00 glyph {ch!r} in the mode font's ink")
    for tile in split:
        if bytes(chr06[16 * tile:16 * tile + 16]) != chr18[16 * tile:16 * tile + 16]:
            raise AssetError(f"split id ${tile:02X} differs between CHR $06 and CHR $18: the swap line would show")
    outline = model.ball_outline(base, assets.ball_tile)
    socket = model.menu.decode(assets.new_tiles[assets.socket_tile])
    if {(x, y) for y in range(8) for x in range(8) if socket[y][x]} != outline:
        raise AssetError(f"socket tile ${assets.socket_tile:02X} must be the outline of ball sprite "
                         f"${assets.ball_tile:02X}")
    selectors = read(base, model.FLAG_BANK, FLAG_POINTERS, FLAGS)
    flag_palettes = {read(base, model.FLAG_BANK, FLAG_SPRITES + p + 2 * k + 1, 1)[0] & 3
                     for p in selectors for k in range(9)}
    if assets.ball_palette in flag_palettes:
        raise AssetError(f"sprite palette {assets.ball_palette} colors a flag; the ball needs an unshared palette")
    check_sprite0(base, assets, chr18, bytes(chr06))


def check_sprite0(base, assets, chr18, chr06):
    """Stock sprite 0 (preset 2: Y from $FB59, tile $FE, priority, x $F8) must hit opaque background only on
    the split row, left of x 255, where both CHR banks hold the same patterns."""
    y0 = read(base, 15, 0xFB5E, 1)[0]
    tile, x0 = 0xFE, 0xF8
    sprite = model.menu.decode(read(base, "chr", model.SPRITE_CHR * 0x1000 + 16 * tile, 16))
    hits = []
    for dy in range(8):
        for dx in range(8):
            x, y = x0 + dx, y0 + 1 + dy
            if not sprite[dy][dx] or x >= 255 or y >= 240:
                continue
            t = assets.nametable[model.COLUMNS * (y // 8) + x // 8]
            bank = chr18 if y // 8 < assets.split_row else chr06
            if model.menu.decode(bank[16 * t:16 * t + 16])[y % 8][x % 8]:
                hits.append((x, y))
    if not hits or min(y for _, y in hits) // 8 != assets.split_row:
        raise AssetError(f"stock sprite 0 must first hit opaque background on split row {assets.split_row}")


def title_tables(base):
    titles = model.title_placements(base)
    return bytes(0x60 + t.col for t in titles), bytes(t.flag_x for t in titles)


def change_manifest(base, assets):
    check_guards(base, DEPENDENCIES, DIGESTS)
    check_runtime(base, assets)
    region = {r.name: r for r in REGIONS}
    home, labels, _ = home_code(assets)
    name_col, flag_x = title_tables(base)
    far = bytearray(b"\xFF" * (FAR_END - FAR_DATA))
    far[0:16] = assets.palette
    far[BALL_COLORS - FAR_DATA:BALL_COLORS - FAR_DATA + 3] = bytes(assets.ball_colors)
    far[FLAG_X - FAR_DATA:FLAG_X - FAR_DATA + 32] = flag_x
    far[NAME_COL - FAR_DATA:NAME_COL - FAR_DATA + 32] = name_col
    code, _ = far_code(assets)
    far[FAR_CODE - FAR_DATA:FAR_CODE - FAR_DATA + len(code)] = code
    chr_new = bytearray(NEW_CHR.end - NEW_CHR.start)
    for tile, pattern in assets.new_tiles.items():
        chr_new[16 * (tile - model.FIRST_FREE):16 * (tile - model.FIRST_FREE) + 16] = pattern
    state1, _ = assemble([f"JMP ${labels['balls']:04X}"], STATE1)
    return (
        claim(base, region["init-hook"], hook_code(labels["numerals"]), bytes.fromhex(STOCK["init-hook"])),
        claim(base, region["init-tail"], b"\x60" + b"\xEA" * 4, bytes.fromhex(STOCK["init-tail"])),
        claim(base, region["state1-draw"], state1, bytes.fromhex(STOCK["state1-draw"])),
        claim(base, region["home-pad"], hop_pad()),
        claim(base, region["home-code"], home + b"\xFF" * (HOME_END - HOME_CODE - len(home))),
        claim(base, region["far-screen"], assets.nametable + assets.attributes),
        claim(base, region["far-code"], bytes(far)),
        claim(base, region["far-pad"], hop_pad()),
        claim(base, region["chr06-new"], bytes(chr_new), bytes(len(chr_new))),
    )


def owned_offsets():
    owned = set()
    for r in REGIONS:
        owned |= set(range(locate(r.bank, r.start), locate(r.bank, r.end - 1) + 1))
    return owned


def check_output(base, rom):
    """Whole-ROM postconditions: size and header, no byte outside the nine regions, identical pads, the
    stockart32 mode tiles intact."""
    if len(rom) != len(base) or rom[:len(HEADER)] != base[:len(HEADER)]:
        raise ValueError("the built ROM changed size or header")
    owned = owned_offsets()
    if any(a != b and i not in owned for i, (a, b) in enumerate(zip(base, rom))):
        raise ValueError("a byte changed outside the analysisart32 regions")
    if read(rom, HOME, PAD, 16) != read(rom, FAR, PAD, 16):
        raise ValueError("the bank 3 and bank 13 hop pads differ")
    if read(rom, "chr", CHR06, 16 * model.FIRST_FREE) != read(base, "chr", CHR06, 16 * model.FIRST_FREE):
        raise ValueError("the stockart32 mode tiles CHR $06 $00-$B9 changed")


def build_rom(base, assets):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected stockart32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned stockart32")
    rom = apply_changes(base, change_manifest(base, assets), REGIONS)
    check_output(base, rom)
    return rom


def diff_manifest(base, rom, assets):
    """The exact before/after manifest, read from the two ROM images over the nine regions; every changed
    byte must fall inside one of them."""
    owned, ranges = owned_offsets(), []
    changed = [i for i, (a, b) in enumerate(zip(base, rom)) if a != b]
    if len(rom) != len(base) or not set(changed) <= owned:
        raise ValueError("the ROM changed outside the analysisart32 regions")
    for r in REGIONS:
        start, size = locate(r.bank, r.start), r.end - r.start
        before, after = base[start:start + size], rom[start:start + size]
        ranges.append({"name": r.name, "bank": r.bank, "start": f"${r.start:04X}", "end": f"${r.end - 1:04X}",
                       "file_offset": start, "size": size, "before_sha256": sha256(before),
                       "after_sha256": sha256(after), "before": before.hex(), "after": after.hex(),
                       "changed_file_offsets": [start + i for i in range(size) if before[i] != after[i]]})
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom), "assets_sha256": sha256(assets.dumps().encode()),
            "size": len(rom), "header": rom[:len(HEADER)].hex(), "changed_bytes": len(changed),
            "claimed_bytes": len(owned), "new_chr06_tiles": [f"{t:02X}" for t in assets.new_tiles],
            "free_chr06_tiles": assets.free_after, "regions": ranges}



def read_registry(path=REGISTRY):
    registry = json.loads(Path(path).read_text())
    if (not isinstance(registry, dict) or registry.get("format") != REGISTRY_FORMAT
            or not isinstance(registry.get("outputs"), dict) or not isinstance(registry.get("rom"), str)):
        raise ValueError(f"{path} is not a {REGISTRY_FORMAT} registry")
    return registry


def load_assets(directory, registry):
    """The asset file tools/analysisart32_convert.py wrote, matching its registered digest."""
    data = (Path(directory) / ASSET_JSON).read_bytes()
    if sha256(data) != registry["outputs"].get(ASSET_JSON):
        raise ValueError(f"{Path(directory) / ASSET_JSON} differs from data/analysisart32/digests.json; regenerate "
                         "it with tools/analysisart32_convert.py")
    return AnalysisAssets.parse(json.loads(data))


def protected_paths(source, inputs=()):
    """Files no analysisart32 tool may overwrite: its inputs, the registry and sources, every earlier stage's
    ROMs, assets and art, every file under tools, docs, art and data, and the stockart32 outputs and root's
    design evidence under build/, also through links."""
    source = Path(source)
    return [ROOT / "build/stockart32.nes", source.resolve().parent / "stockart32.nes", source.resolve(), REGISTRY,
            *inputs, *prior.protected_paths(source), *(ROOT / "art").rglob("*"), *(ROOT / "data").rglob("*"),
            *(path for directory in EVIDENCE[:2] for path in directory.rglob("*"))]


def output_path(output):
    path = Path(os.path.abspath(output))
    if sys.platform == "darwin":
        for alias, real in ((Path('/tmp'), Path('/private/tmp')), (Path('/var'), Path('/private/var'))):
            if (path == alias or alias in path.parents) and alias.is_symlink() and alias.resolve() == real:
                path = real / path.relative_to(alias)
                break
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError(f"output passes through symbolic link ancestor {parent}; use the real path {path.resolve()}")
    return path


def protect_output(source, output, inputs=()):
    source, output = Path(source), output_path(output)
    prior.protect_output(source, output, inputs)
    refuse_aliases(output, protected_paths(source, inputs), PROTECTED_SHA256)
    for directory in EVIDENCE:
        refuse_inside(output, directory)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned stockart32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--assets", type=Path, default=ASSETS, help="analysisart32_convert.py output (default %(default)s)")
    ap.add_argument("--manifest", action="store_true", help="print the exact before/after manifest as JSON")
    args = ap.parse_args()
    try:
        args.out = output_path(args.out)
        inputs = [args.assets / ASSET_JSON, REGISTRY]
        protect_output(args.rom, args.out, inputs)
        refuse_inside(args.out, args.assets)
        registry = read_registry()
        assets = load_assets(args.assets, registry)
        base = args.rom.read_bytes()
        rom = build_rom(base, assets)
        if sha256(rom) != registry["rom"]:
            raise ValueError(f"the built ROM {sha256(rom)} differs from data/analysisart32/digests.json")
        write_atomic(args.out, rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom, assets), indent=1))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed in {len(REGIONS)} regions); matches "
              "data/analysisart32/digests.json")


if __name__ == "__main__":
    main()
