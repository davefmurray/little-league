#!/usr/bin/env python3
"""Bootable four-page team-select screen with Left/Right paging.

Lists (length byte + display list) at $FB83, four blocks of 160 bytes.
Palette $FE10, code $FE30, page-pointer table $FF20.

    python3 tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes
"""
import argparse
import json

HEADER = 16
BANK = 0x4000
FIXED = 15
HOOK = 0xCBE6
LIST_BASE = 0xFB83
STRIDE = 144
PALETTE = 0xFDD0
CODE = 0xFDF0
MARKER = 0xFFD0
PTR = 0xFFE0
PAGE = 0x07C0
BUTTONS = 0x07C6
CURSOR = 0x07C1


def bank_file(bank):
    return HEADER + bank * BANK


def run(addr, text):
    return bytes([addr >> 8, addr & 0xFF]) + text.encode("ascii") + b"\xfe"


def page_list(teams, page):
    out = bytearray()
    out += run(0x2022, "TEAM SELECT")
    out += run(0x2039, f"{page + 1} OF 4")
    for i, t in enumerate(teams[page * 8:page * 8 + 8]):
        col = 2 + (i % 4) * 7
        row = 5 if i < 4 else 11
        out += run(0x2000 + row * 32 + col - 1, " " + t["code"])
    first = teams[page * 8]
    out += run(0x22A2, first["name"][:14].ljust(14))
    out += run(0x22C2, f"SKILL 4  REGION {first['region']}".ljust(24)[:24])
    out += run(0x236B, "A SELECT")
    return bytes(out)


def assemble(lines, origin):
    labels, code, branches, fixups = {}, bytearray(), [], []
    for item in lines:
        if isinstance(item, str) and item.endswith(":"):
            labels[item[:-1]] = len(code)
            continue
        op = item[0]
        if op in ("LDA#", "LDX#", "LDY#", "CPX#", "CMP#", "AND#", "ORA#", "SBC#", "ADC#"):
            code.append({"LDA#": 0xA9, "LDX#": 0xA2, "LDY#": 0xA0, "CPX#": 0xE0,
                         "CMP#": 0xC9, "AND#": 0x29, "ORA#": 0x09,
                         "SBC#": 0xE9, "ADC#": 0x69}[op])
            code.append(item[1])
        elif op in ("LDAx", "STAx"):
            addr = item[1]
            code += bytes([0xBD if op == "LDAx" else 0x9D, addr & 0xFF, addr >> 8])
        elif op == "STAy":
            code += bytes([0x99, item[1] & 0xFF, item[1] >> 8])
        elif op == "LDA":
            code += bytes([0xAD, item[1] & 0xFF, item[1] >> 8])
        elif op == "STA":
            code += bytes([0x8D, item[1] & 0xFF, item[1] >> 8])
        elif op == "LDX":
            code += bytes([0xAE, item[1] & 0xFF, item[1] >> 8])
        elif op == "STX":
            code += bytes([0x8E, item[1] & 0xFF, item[1] >> 8])
        elif op == "LDAiY":
            code += bytes([0xB1, item[1]])
        elif op == "ROL":
            code += bytes([0x2E, item[1] & 0xFF, item[1] >> 8])
        elif op == "DECz":
            code += bytes([0xC6, item[1]])
        elif op == "BIT":
            code += bytes([0x2C, item[1] & 0xFF, item[1] >> 8])
        elif op in ("JSR", "JMP"):
            opcode = 0x20 if op == "JSR" else 0x4C
            if isinstance(item[1], str):
                fixups.append((len(code), item[1]))
                code += bytes([opcode, 0x00, 0x00])
            else:
                code += bytes([opcode, item[1] & 0xFF, item[1] >> 8])
        elif op in ("BNE", "BPL", "BCC", "BCS"):
            branches.append((len(code), item[1]))
            code += bytes([{"BNE": 0xD0, "BPL": 0x10, "BCC": 0x90, "BCS": 0xB0}[op], 0x00])
        elif op in ("INX", "INY", "DEX", "DEY", "ASL", "LSR", "TAX", "SEC", "CLC", "SEI", "RTS"):
            code.append({"INX": 0xE8, "INY": 0xC8, "DEX": 0xCA, "DEY": 0x88,
                         "ASL": 0x0A, "LSR": 0x4A, "TAX": 0xAA, "SEC": 0x38,
                         "CLC": 0x18, "SEI": 0x78, "RTS": 0x60}[op])
        else:
            raise SystemExit(f"bad op {op}")
    for pos, label in branches:
        code[pos + 1] = (labels[label] - (pos + 2)) & 0xFF
    for pos, label in fixups:
        addr = origin + labels[label]
        code[pos + 1] = addr & 0xFF
        code[pos + 2] = addr >> 8
    return bytes(code)


def screen_code():
    return assemble([
        ("SEI",),
        "w1:", ("BIT", 0x2002), ("BPL", "w1"),
        "w2:", ("BIT", 0x2002), ("BPL", "w2"),
        ("LDA#", 0x00), ("STA", 0x2000), ("STA", 0x2001),
        ("LDA#", 0x1E), ("JSR", 0xC102),
        ("LDA#", 0x00), ("JSR", 0xC11C),
        ("LDA#", 0x01), ("JSR", 0xC134),
        ("LDA#", 0x3F), ("STA", 0x2006), ("LDA#", 0x00), ("STA", 0x2006),
        ("LDX#", 0x00),
        "pal:", ("LDAx", PALETTE), ("STA", 0x2007), ("INX",), ("CPX#", 0x20), ("BNE", "pal"),
        ("LDA#", 0x20), ("STA", 0x2006), ("LDA#", 0x00), ("STA", 0x2006),
        ("LDX#", 0x00), ("LDY#", 0x04),
        "clr:", ("LDA#", 0x20), ("STA", 0x2007), ("INX",), ("BNE", "clr"),
        ("DEY",), ("BNE", "clr"),
        ("LDA#", 0x23), ("STA", 0x2006), ("LDA#", 0xC0), ("STA", 0x2006),
        ("LDX#", 0x40), ("LDA#", 0x00),
        "attr:", ("STA", 0x2007), ("DEX",), ("BNE", "attr"),
        ("LDA#", 0x00), ("STA", PAGE), ("STA", CURSOR),
        ("JSR", "draw_page"),
        "main:", ("JSR", "read_pad"),
        ("LDA", BUTTONS), ("AND#", 0x08), ("BNE", "up"),
        ("LDA", BUTTONS), ("AND#", 0x04), ("BNE", "down"),
        ("LDA", BUTTONS), ("AND#", 0x02), ("BNE", "left"),
        ("LDA", BUTTONS), ("AND#", 0x01), ("BNE", "right"),
        ("JMP", "main"),
        "up:", ("LDA", CURSOR), ("CMP#", 0x04), ("BCC", "release"),
        ("SEC",), ("SBC#", 0x04), ("STA", CURSOR), ("JSR", "draw_page"), ("JMP", "release"),
        "down:", ("LDA", CURSOR), ("CMP#", 0x04), ("BCS", "release"),
        ("CLC",), ("ADC#", 0x04), ("STA", CURSOR), ("JSR", "draw_page"), ("JMP", "release"),
        "left:", ("LDA", CURSOR), ("AND#", 0x03), ("BNE", "leftmove"),
        ("LDA", PAGE), ("SEC",), ("SBC#", 0x01), ("AND#", 0x03), ("STA", PAGE),
        ("LDA", CURSOR), ("AND#", 0x04), ("ORA#", 0x03), ("STA", CURSOR),
        ("JSR", "draw_page"), ("JMP", "release"),
        "leftmove:", ("LDA", CURSOR), ("SEC",), ("SBC#", 0x01), ("STA", CURSOR),
        ("JSR", "draw_page"), ("JMP", "release"),
        "right:", ("LDA", CURSOR), ("AND#", 0x03), ("CMP#", 0x03), ("BNE", "rightmove"),
        ("LDA", PAGE), ("CLC",), ("ADC#", 0x01), ("AND#", 0x03), ("STA", PAGE),
        ("LDA", CURSOR), ("AND#", 0x04), ("STA", CURSOR),
        ("JSR", "draw_page"), ("JMP", "release"),
        "rightmove:", ("LDA", CURSOR), ("CLC",), ("ADC#", 0x01), ("STA", CURSOR),
        ("JSR", "draw_page"), ("JMP", "release"),
        "release:", ("JSR", "read_pad"), ("LDA", BUTTONS), ("BNE", "release"),
        ("JMP", "main"),
        "draw_page:", ("LDA#", 0x00), ("STA", 0x2001),
        ("LDA", PAGE), ("ASL",), ("TAX",),
        ("LDAx", PTR), ("STA", 0x00), ("LDAx", PTR + 1), ("STA", 0x01),
        ("LDY#", 0x00), ("LDAiY", 0x00), ("STA", 0x32), ("STA", 0x05),
        ("INY",),
        "copy:", ("LDAiY", 0x00), ("STAy", 0x02FF), ("INY",), ("DECz", 0x05), ("BNE", "copy"),
        ("LDX", 0x32), ("STX", 0x06),
        ("LDA", CURSOR), ("ASL",), ("TAX",),
        ("LDAx", MARKER), ("STA", 0x02),
        ("LDAx", MARKER + 1), ("STA", 0x03),
        ("LDX", 0x06),
        ("LDA", 0x03), ("STAx", 0x0300), ("INX",),
        ("LDA", 0x02), ("STAx", 0x0300), ("INX",),
        ("LDA#", 0x2D), ("STAx", 0x0300), ("INX",),
        ("LDA#", 0xFE), ("STAx", 0x0300), ("INX",),
        ("STX", 0x32),
        ("JSR", 0xC53A),
        ("LDA#", 0x00), ("STA", 0x2005), ("STA", 0x2005),
        ("LDA#", 0x1E), ("STA", 0x2001),
        ("RTS",),
        "read_pad:", ("LDA#", 0x01), ("STA", 0x4016), ("LDA#", 0x00), ("STA", 0x4016),
        ("LDX#", 0x08), ("LDA#", 0x00), ("STA", BUTTONS),
        "rd:", ("LDA", 0x4016), ("LSR",), ("ROL", BUTTONS), ("DEX",), ("BNE", "rd"), ("RTS",),
    ], CODE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("teams")
    ap.add_argument("-o", "--out", default="build/select-screen.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    teams = json.load(open(args.teams))["teams"]
    fixed = bank_file(FIXED)
    ptrs = []
    for page in range(4):
        lst = page_list(teams, page)
        block = bytes([len(lst)]) + lst
        if len(block) > STRIDE:
            raise SystemExit(f"page {page} list {len(block)} > {STRIDE}")
        block = block.ljust(STRIDE, b"\xff")
        off = LIST_BASE + page * STRIDE
        rom[fixed + (off - 0xC000):fixed + (off - 0xC000) + STRIDE] = block
        ptrs.append((off & 0xFF, off >> 8))

    code = screen_code()
    if CODE + len(code) > PTR:
        raise SystemExit(f"screen code too large: {len(code)} (ends ${CODE + len(code):04X})")
    rom[fixed + (CODE - 0xC000):fixed + (CODE - 0xC000) + len(code)] = code
    palette = bytes([0x1A, 0x30, 0x27, 0x0F] + [0x0F] * 28)
    rom[fixed + (PALETTE - 0xC000):fixed + (PALETTE - 0xC000) + 32] = palette
    table = bytes(x for pair in ptrs for x in pair)
    rom[fixed + (PTR - 0xC000):fixed + (PTR - 0xC000) + len(table)] = table
    markers = [0x20A1, 0x20A8, 0x20AF, 0x20B6, 0x2161, 0x2168, 0x216F, 0x2176]
    mtable = bytes(x for a in markers for x in (a & 0xFF, a >> 8))
    rom[fixed + (MARKER - 0xC000):fixed + (MARKER - 0xC000) + len(mtable)] = mtable

    hook = fixed + (HOOK - 0xC000)
    rom[hook:hook + 5] = bytes([0x20, CODE & 0xFF, CODE >> 8, 0xEA, 0xEA])
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: code {len(code)} bytes at ${CODE:04X}, lists at ${LIST_BASE:04X}")


if __name__ == "__main__":
    main()
