#!/usr/bin/env python3
"""Serve Championship, Exhibition and Power Analysis from one 32-team picker, on the pinned draw32 ROM.

    .venv/bin/python tools/build_pick32.py build/draw32.nes -o build/pick32.nes
    .venv/bin/python tools/build_pick32.py build/draw32.nes -o build/pick32.nes --manifest

The stock mode menu still performs each mode's setup and stores the mode in
$06E0: Exhibition's ownership flags, submenu $BD and $04E2=0 at bank 1 $9532,
Power Analysis at $9527. menuart32's flag grid then picks for all three. Scene
$12 (START NEW SERIES) and scene $0C (Exhibition, Power Analysis) both enter
bank 10 through $FF20, whose $8000 jump now targets this picker. It reuses
menuart32's runtime and selector helpers in place and leaves only through
stock contracts:

  Championship    A: $07C3 = team, JMP $9620 (commit, draw, bracket).
  Exhibition      A on side 0 locks the first team. A on side 1 takes the
                  second, refusing the first: $04EF/$04F0 and $07FD/$07FE,
                  scene $10, JMP $FC00 (roster cache). 2P side 1 reads
                  controller 2, which then also owns B.
  Power Analysis  A: $04EF = team, scene $14. The ratings' B re-enters scene
                  $0C, which reopens the picker on $04EF.
  B               side 1 returns to side 0; otherwise scene 6 (mode menu).

START NEW SERIES no longer marks $07ED before the pick, so cancelling keeps
an active series intact; the commit at bank 11 $86E7 still marks it. The
picker never writes the heap, masks, markers or draw seed. Its transient RAM
is $07C2 (port), $07C4 (side) and $07C5 (first pick), inside the stock
per-player array $07B1,X that games rewrite, as menuart32's $07C0-$07C9 are.
"""
import argparse
import json
from pathlib import Path

from build_bank11 import assemble
from build_draw32 import (
    PROTECTED_SHA256 as PRIOR_SHA256, ROOT, Region, apply_changes, check_guards, claim, manifest_ranges,
    padded, protect_output as protect_prior_output, read, refuse_aliases, sha256, word,
)
from build_menuart32 import CHOICE, COL, HELD, MENU_CHR, MENU_MASK, NEW, PAD, ROW, SFX_CONFIRM
from build_teamnames32 import HEADER, ROM_SIZE

BASE_SHA256 = "b263bd4906b70d2fa0ba807e83296f721787b346df33dc3fc0d69dc7da7d4541"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}

PICK_BANK, ORIGIN, TEXTS = 10, 0xB400, 0xBB00
PORT, SIDE, PICK0 = 0x07C2, 0x07C4, 0x07C5
MODE, SUBMODE = 0x06E0, 0xBD
CHAMPIONSHIP, EXHIBITION, ANALYSIS = 0, 1, 2
TWO_PLAYER = 1                          # $BD: 0 1P, 1 2P, 2 WATCH
X0, Y0 = 8, 56                          # menuart32 card 0's pixel origin
CURSOR_TILE = 0xA0                      # menuart32's cursor corner tile
HEADER_PPU = 0x2068                     # the selector map's "CHOOSE YOUR TEAM" cells, row 3 column 8
LOCK_PALETTE = (0x0C, 0x21, 0x30, 0x12)  # sprite palette 1, free on the selector, for the locked first pick

# menuart32 bank-10 routines reused in place. tools/test_pick32.py checks them
# against build_menuart32's generated labels.
RUNTIME = dict(menu_begin=0xA000, menu_frame=0xA04B, menu_end=0xA079, flush=0xA0A8, q_head=0xA0F7,
               load_screen=0xA178, sel_move=0xA21B, sel_team=0xA262, sel_info=0xA26C, sel_cursor=0xA280)

# One 16-character header per screen: championship, analysis, then exhibition
# as 2 + 2 * $BD + side (1P, 2P, WATCH; side 0, side 1).
HEADERS = (
    "CHOOSE YOUR TEAM",
    " POWER ANALYSIS ",
    " 1P CHOOSE TEAM ", "CHOOSE OPPONENT ",
    " 1P CHOOSE TEAM ", " 2P CHOOSE TEAM ",
    " CHOOSE TEAM 1  ", " CHOOSE TEAM 2  ",
)

REGIONS = (
    Region("entry-target", PICK_BANK, 0x8001, 0x8003),
    Region("picker-code", PICK_BANK, ORIGIN, TEXTS),
    Region("picker-text", PICK_BANK, TEXTS, TEXTS + 0x100),
    Region("scene-0c-bridge", 2, 0xB969, 0xB96C),
    Region("new-series-marker", 1, 0x950A, 0x950D),
)

DEPENDENCIES = (
    ("bank-10 entry $8000", PICK_BANK, 0x8000, "4C BD A1"),
    ("selector header cells $B068", PICK_BANK, 0xB000 + HEADER_PPU - 0x2000, "CHOOSE YOUR TEAM".encode().hex()),
    ("selector commit $9620", PICK_BANK, 0x9620, "A9 FF 8D 4B 07 8D 4C 07 8D F1 07 8D F2 07 AD C3 07 29 07 AA BD 5A 96"
     " 49 FF 85 00 AD C3 07 4A 4A 4A AA A5 00 E0 02 B0 09 3D 4B 07 9D 4B 07 4C 14 FF 3D EF 07 9D EF 07 4C 14 FF"
     " 01 02 04 08 10 20 40 80"),
    ("mode menu START NEW SERIES $9508", 1, 0x9508, "A9 12 8D ED 07 8D 7B 04 60"),
    ("mode menu Power Analysis $9527", 1, 0x9527, "A9 02 8D E0 06 A9 0C 8D 7B 04 60"),
    ("mode menu Exhibition $9532", 1, 0x9532, "A5 B9 85 BD 0A A8 B9 A3 96 8D EB 04 B9 A4 96 8D EC 04 A9 00 8D E9 04"
     " 85 A7 8D E2 04 8D ED 04 A9 01 8D EE 04 A9 0C 8D 7B 04 60"),
    ("Exhibition ownership $96A3", 1, 0x96A3, "00 80 00 00 80 80"),
    ("old picker scene $0C entry $B969", 2, 0xB969, "20 9F CA"),
    ("ratings exit $AFBC", 3, 0xAFBC, "A5 91 29 C0 F0 F3 A9 0C 8D 7B 04 A9 35 4C 49 C2"),
    ("scene $12 bridge call $98B9", 5, 0x98B9, "20 20 FF"),
    ("scene handlers $CC52", 15, 0xCC52, "00 AC 21 AC AA CF 7A D1 C3 D6 40 D7 00 94 4F 94 23 AA B6 B2 9D B3 C0 FF"
     " 69 B9 C0 B9 A9 96 ED 96 B9 AE 71 AF B9 98 5F 99 58 AF A0 AF 27 EE 43 EE 30 A4 75 A4"),
    ("scene banks $CCAC", 15, 0xCCAC, "00 06 06 01 04 04 02 01 01 05 03 06 01"),
    ("MMC1 writers $C100", 15, 0xC100, "A5 22 85 22 E6 2D 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F 4A 8D FF 9F"
     " C6 2D 60 E6 2D 8D FF BF 4A 8D FF BF 4A 8D FF BF 4A 8D FF BF 4A 8D FF BF C6 2D 60 E6 2D 8D FF DF 4A 8D FF DF"
     " 4A 8D FF DF 4A 8D FF DF 4A 8D FF DF C6 2D 60 A5 27 85 27 E6 2D 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF"
     " 4A 8D FF FF C6 2D 60"),
    ("OAM hide $C199", 15, 0xC199, "A9 F0 A2 00 9D 00 02 CA D0 FA 60"),
    ("sound queue $C249", 15, 0xC249, "AE EA 04 D0 11 E6 2D AE 79 04 9D 70 04 E8 8A 29 07 8D 79 04 C6 2D 60"),
    ("NMI $CD85", 15, 0xCD85, "48 98 48 8A 48 A5 2C 8D E6 04 D0 50"),
    ("NMI short path $CDE1", 15, 0xCDE1, "20 74 CF A5 AD 29 1E F0 05 A9 00 8D 7D 04 68 AA 68 A8 68 40"),
    ("audio tick $CF74", 15, 0xCF74, "A5 2D 8D E4 04 D0 2E E6 2D A9 00 20 50 C1 AE 78 04 BD 70 04 C9 FF F0 15"
     " 8D 00 04 20 48 80 AE 78 04 A9 FF 9D 70 04 E8 8A 29 07 8D 78 04 20 6C 81 20 4C C1 C6 2D 60"),
    ("NMI vector", 15, 0xFFFA, "85 CD"),
    ("roster copy $FB90", 15, 0xFB90, "BD 80 FC 85 00 BD A0 FC 85 01 A0 00 B1 00 91 02 C8 C0 F0 D0 F7 A0 08 B1 02"
     " 29 7F C0 38 B0 02 09 80 91 02 98 18 69 10 A8 C0 F8 D0 EB 18 A5 00 69 40 85 00 A5 01 69 01 85 01 18 A5 02"
     " 69 F0 85 02 A5 03 69 00 85 03 A0 00 B1 00 91 02 C8 C0 30 D0 F7 60"),
    ("roster cache $FC00", 15, 0xFC00, "A9 08 20 4E C1 A9 00 85 02 A9 78 85 03 AE FD 07 20 4A FC AE FD 07 8A 0A A8"
     " A9 00 99 00 7F A9 78 99 01 7F 20 00 FF A9 00 85 02 A9 7A 85 03 AE FE 07 20 4A FC AE FE 07 8A 0A A8 A9 00 99"
     " 00 7F A9 7A 99 01 7F 20 00 FF 4C 90 FF 4C 90 FB"),
    ("roster pointers $FC80", 15, 0xFC80, "00 70 E0 50 C0 30 A0 10 80 F0 60 D0 40 B0 20 90 00 70 E0 50 C0 30 A0 10"
     " 80 F0 60 D0 40 B0 20 90 80 81 82 84 85 87 88 8A 8B 8C 8E 8F 91 92 94 95 97 98 99 9B 9C 9E 9F A1 A2 A3 A5 A6"
     " A8 A9 AB AC"),
    ("stock pointer restore $FF00", 15, 0xFF00, "E0 10 B0 0F 8A 0A AA BD 40 FD 9D 00 7F BD 41 FD 9D 01 7F 60"),
    ("commit bridge $FF14", 15, 0xFF14, "A9 0B 20 4E C1 4C 80 83"),
    ("selector bridge $FF20", 15, 0xFF20, "BA 8E F7 07 BD 01 01 8D F8 07 BD 02 01 8D F9 07 A9 00 8D 00 20 A2 FF 8E"
     " FF 9F A9 0A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 A9 0A 85 27 4C 00 80"),
    ("exit $FF90", 15, 0xFF90, "A2 FF 8E FF 9F A9 05 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0 4A 8D 00 E0"
     " A9 05 85 27 A9 80 8D 00 20 9A 4C 09 CC"),
)
DIGESTS = (
    ("menuart32 selector runtime $A000-$A3FF", PICK_BANK, 0xA000, 0x400,
     "457bb11efc5555302affffaf696c1840a064ffcd38aa52c84de24e464b0ba115"),
    ("menuart32 selector data $A400-$AAFF", PICK_BANK, 0xA400, 0x700,
     "cd13126b34862ef843b6a33826d89a6687fece4c6ce527aaa0d436ecd3489a47"),
    ("menuart32 selector map $B000-$B3FF", PICK_BANK, 0xB000, 0x400,
     "5b27e8b5b1cef8d0a85aeb207915b20c7f9416e0e7a1a83fffeaa577012dcf44"),
)


def check_header_glyphs(base):
    """Every header character must be a stock font glyph at its ASCII id in the menu CHR bank."""
    for char in sorted(set("".join(HEADERS))):
        index = ord(char)
        glyph = read(base, "chr", MENU_CHR * 0x1000 + 16 * index, 16)
        if glyph != read(base, "chr", 16 * index, 16) or (char != " " and not any(glyph)):
            raise ValueError(f"header character {char!r} has no font glyph in CHR ${MENU_CHR:02X}")


def asm():
    r = RUNTIME
    return [
        "pk_entry:",
        "SEI",
        f"JSR ${r['menu_begin']:04X}",
        f"LDA #${MENU_CHR:02X}", "JSR $C134",
        f"JSR ${r['load_screen']:04X}",
        "LDA #$3F", "STA $2006", "LDA #$14", "STA $2006",
        *[line for color in LOCK_PALETTE for line in (f"LDA #${color:02X}", "STA $2007")],
        "LDA #$00", f"STA ${SIDE:04X}", f"STA ${PORT:04X}",
        "LDA #$FF", f"STA ${PICK0:04X}", f"STA ${CHOICE:04X}",
        f"LDA ${MODE:04X}", f"CMP #${ANALYSIS:02X}", "BNE pe_zero",
        "LDA $04EF", "AND #$1F", "JMP pe_set",
        "pe_zero:",
        "LDA #$00",
        "pe_set:",
        "JSR pk_goto",
        "JSR pk_header",
        f"JSR ${r['sel_info']:04X}",
        f"JSR ${r['flush']:04X}",
        "JSR pk_sprites",
        "JSR pk_latch",
        "LDA #$1E", f"STA ${MENU_MASK:04X}",
        "pk_loop:",
        f"JSR ${r['menu_frame']:04X}",
        "JSR pk_pad",
        f"LDA ${NEW:04X}", "BPL pl_nota",
        "JMP pk_a",
        "pl_nota:",
        "ASL A", "BPL pl_move",
        "JMP pk_b",
        "pl_move:",
        f"LDA ${NEW:04X}", "AND #$0F", "BEQ pk_idle",
        f"JSR ${r['sel_move']:04X}",
        "pk_idle:",
        "JSR pk_sprites",
        "JMP pk_loop",

        "pk_a:",
        f"JSR ${r['sel_team']:04X}",
        f"LDX ${MODE:04X}", "BEQ pa_champ",
        f"CPX #${ANALYSIS:02X}", "BEQ pa_analysis",
        f"LDX ${SIDE:04X}", "BNE pa_second",
        f"STA ${PICK0:04X}",
        f"INC ${SIDE:04X}",
        f"LDA ${SUBMODE:02X}", f"CMP #${TWO_PLAYER:02X}", "BNE pa_port",
        f"STA ${PORT:04X}",
        "pa_port:",
        f"LDA #${SFX_CONFIRM:02X}", "JSR $C249",
        "JSR pk_header",
        "JSR pk_latch",
        "JMP pk_idle",
        "pa_second:",
        f"CMP ${PICK0:04X}", "BNE pa_take",
        "JMP pk_idle",
        "pa_take:",
        f"STA ${CHOICE:04X}",
        "JSR pk_confirm",
        f"LDA ${PICK0:04X}", "STA $04EF", "STA $07FD",
        f"LDA ${CHOICE:04X}", "STA $04F0", "STA $07FE",
        "LDA #$00", "STA $047A", "STA $047D",
        "LDA #$10", "STA $047B",
        "JMP $FC00",
        "pa_champ:",
        f"STA ${CHOICE:04X}",
        "JSR pk_confirm",
        "JMP $9620",
        "pa_analysis:",
        "STA $04EF",
        "JSR pk_confirm",
        "LDA #$14",
        "pk_exit:",
        "STA $047B",
        "LDA #$00", "STA $047D",
        "JMP $FF90",

        "pk_b:",
        f"LDA ${MODE:04X}", f"CMP #${EXHIBITION:02X}", "BNE pb_leave",
        f"LDA ${SIDE:04X}", "BEQ pb_leave",
        "LDA #$00", f"STA ${SIDE:04X}", f"STA ${PORT:04X}",
        f"LDA ${PICK0:04X}", "JSR pk_goto",
        "LDA #$FF", f"STA ${PICK0:04X}",
        f"JSR ${r['sel_info']:04X}",
        f"LDA #${SFX_CONFIRM:02X}", "JSR $C249",
        "JSR pk_header",
        "JSR pk_latch",
        "JMP pk_idle",
        "pb_leave:",
        "JSR pk_confirm",
        "LDA #$06",
        "JMP pk_exit",

        # Confirm sound, wait for the active port's release, then menuart32's teardown.
        "pk_confirm:",
        f"LDA #${SFX_CONFIRM:02X}", "JSR $C249",
        "pc_wait:",
        f"JSR ${r['menu_frame']:04X}",
        "JSR pk_pad",
        f"LDA ${PAD:04X}", "BNE pc_wait",
        f"JMP ${r['menu_end']:04X}",

        "pk_goto:",
        "PHA", "AND #$07", f"STA ${COL:04X}",
        "PLA", "LSR A", "LSR A", "LSR A", f"STA ${ROW:04X}",
        "RTS",

        # Serial read of controller 1 or 2 ($4016,X).
        "pk_pad:",
        "LDA #$01", "STA $4016", "LDA #$00", "STA $4016",
        f"LDX ${PORT:04X}",
        "LDY #$08",
        "pp_bit:",
        "LDA $4016,X", "LSR A", f"ROL ${PAD:04X}", "DEY", "BNE pp_bit",
        f"LDA ${HELD:04X}", "EOR #$FF", f"AND ${PAD:04X}", f"STA ${NEW:04X}",
        f"LDA ${PAD:04X}", f"STA ${HELD:04X}",
        "RTS",
        # Buttons already held on a newly active port act only after release.
        "pk_latch:",
        "LDA #$FF", f"STA ${HELD:04X}",
        "JMP pk_pad",

        "pk_header:",
        f"LDA ${MODE:04X}", "BEQ ph_set",
        f"CMP #${ANALYSIS:02X}", "BNE ph_exh",
        "LDA #$01", "BNE ph_set",
        "ph_exh:",
        f"LDA ${SUBMODE:02X}", "ASL A", f"ORA ${SIDE:04X}", "CLC", "ADC #$02",
        "ph_set:",
        "ASL A", "ASL A", "ASL A", "ASL A", "STA $03",
        f"LDA #${HEADER_PPU >> 8:02X}", "STA $00", f"LDA #${HEADER_PPU & 0xFF:02X}", "STA $01",
        "LDA #$10", "STA $02",
        f"JSR ${r['q_head']:04X}",
        "LDY $03", "LDA #$10", "STA $04",
        "ph_copy:",
        f"LDA ${TEXTS:04X},Y", "STA $0300,X", "INX", "INY", "DEC $04", "BNE ph_copy",
        "RTS",

        # menuart32's cursor, plus fixed corners in sprite palette 1 around the locked first pick.
        "pk_sprites:",
        f"JSR ${r['sel_cursor']:04X}",
        f"LDA ${SIDE:04X}", "BEQ ps_hide",
        f"LDA ${PICK0:04X}", "AND #$07", "ASL A", "ASL A", "ASL A", "ASL A", "ASL A", "CLC", f"ADC #${X0:02X}",
        "STA $06",
        f"LDA ${PICK0:04X}", "LSR A", "LSR A", "LSR A", "ASL A", "ASL A", "ASL A", "ASL A", "ASL A", "CLC",
        f"ADC #${Y0:02X}", "STA $07",
        "LDA $06", "SEC", "SBC #$03", "STA $0213", "STA $021B",
        "LDA $06", "CLC", "ADC #$0B", "STA $0217", "STA $021F",
        "LDA $07", "SEC", "SBC #$04", "STA $0210", "STA $0214",
        "LDA $07", "CLC", "ADC #$09", "STA $0218", "STA $021C",
        f"LDA #${CURSOR_TILE:02X}", "STA $0211", "STA $0215", "STA $0219", "STA $021D",
        "LDA #$01", "STA $0212", "LDA #$41", "STA $0216",
        "LDA #$81", "STA $021A", "LDA #$C1", "STA $021E",
        "RTS",
        "ps_hide:",
        "LDA #$F0", "STA $0210", "STA $0214", "STA $0218", "STA $021C",
        "RTS",
    ]


def assemble_picker():
    code, labels = assemble(asm(), ORIGIN)
    texts = b"".join(text.encode("ascii") for text in HEADERS)
    if any(len(text) != 16 for text in HEADERS):
        raise ValueError("headers are 16 characters")
    return code, labels, texts


def labels():
    return assemble_picker()[1]


def change_manifest(base):
    check_guards(base, DEPENDENCIES, DIGESTS)
    check_header_glyphs(base)
    code, picker, texts = assemble_picker()
    region = {r.name: r for r in REGIONS}
    return (
        claim(base, region["entry-target"], word(picker["pk_entry"]), word(0xA1BD)),
        claim(base, region["picker-code"], padded(code, region["picker-code"])),
        claim(base, region["picker-text"], padded(texts, region["picker-text"])),
        claim(base, region["scene-0c-bridge"], bytes.fromhex("20 20 FF"), bytes.fromhex("20 9F CA")),
        claim(base, region["new-series-marker"], bytes.fromhex("EA EA EA"), bytes.fromhex("8D ED 07")),
    )


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected draw32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned draw32")
    return apply_changes(base, change_manifest(base), REGIONS)


def diff_manifest(base, rom):
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "ranges": manifest_ranges(change_manifest(base))}


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    refuse_aliases(output, [ROOT / "build/draw32.nes", source.resolve().parent / "draw32.nes", source.resolve()],
                   PROTECTED_SHA256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned draw32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        base = args.rom.read_bytes()
        rom = build_rom(base)
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
