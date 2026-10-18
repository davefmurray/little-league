#!/usr/bin/env python3
"""Build a bootable static team-select screen (page 1) for the 32-team ROM.

Replaces the MMC1-init hook with a screen routine at $FD20:
  - PPU warm-up, control $1E, CHR0=0/CHR1=1
  - palette + nametable clear
  - copies a prebuilt display list from $FC00 to $0300 and flushes it via $C53A
  - enables rendering and loops

    python3 tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes
"""
import argparse
import json

HEADER = 16
BANK = 0x4000
FIXED = 15
HOOK = 0xCBE6
LIST = 0xFC00
PALETTE = 0xFD00
CODE = 0xFD20


def bank_file(bank):
    return HEADER + bank * BANK


def run(addr, text):
    return bytes([addr >> 8, addr & 0xFF]) + text.encode("ascii") + b"\xfe"


def build_list(teams):
    out = bytearray()
    out += run(0x2022, "TEAM SELECT")
    out += run(0x2039, "1 OF 4")
    for i, t in enumerate(teams[:8]):
        col = 2 + (i % 4) * 7
        row = 5 if i < 4 else 11
        out += run(0x2000 + row * 32 + col, t["code"])
    out += run(0x22A2, "NEW YORK")
    out += run(0x22B4, "12-4")
    out += run(0x22C2, "SKILL 4  REGION AMERICA")
    out += run(0x2362, "PREV")
    out += run(0x236B, "A SELECT")
    out += run(0x2379, "NEXT")
    return bytes(out)


def assemble(lines):
    labels, code, branches = {}, bytearray(), []
    for item in lines:
        if isinstance(item, str) and item.endswith(":"):
            labels[item[:-1]] = len(code)
            continue
        op = item[0]
        if op in ("LDA#", "LDX#", "LDY#", "CPX#"):
            code.append({"LDA#": 0xA9, "LDX#": 0xA2, "LDY#": 0xA0, "CPX#": 0xE0}[op])
            code.append(item[1])
        elif op in ("LDAx", "STAx"):
            addr = item[1]
            code += bytes([0xBD if op == "LDAx" else 0x9D, addr & 0xFF, addr >> 8])
        elif op == "STA":
            code += bytes([0x8D, item[1] & 0xFF, item[1] >> 8])
        elif op == "BIT":
            code += bytes([0x2C, item[1] & 0xFF, item[1] >> 8])
        elif op == "JSR":
            code += bytes([0x20, item[1] & 0xFF, item[1] >> 8])
        elif op == "JMP":
            code += bytes([0x4C, item[1] & 0xFF, item[1] >> 8])
        elif op in ("BNE", "BPL"):
            branches.append((len(code), item[1], 0xD0 if op == "BNE" else 0x10))
            code += bytes([0xD0 if op == "BNE" else 0x10, 0x00])
        elif op == "INX":
            code.append(0xE8)
        elif op == "DEX":
            code.append(0xCA)
        elif op == "DEY":
            code.append(0x88)
        elif op == "SEI":
            code.append(0x78)
        elif op == "RTS":
            code.append(0x60)
        else:
            raise SystemExit(f"bad op {op}")
    for pos, label, opcode in branches:
        code[pos + 1] = (labels[label] - (pos + 2)) & 0xFF
    return bytes(code)


def screen_code(length):
    return assemble([
        ("SEI",),
        "wait1:", ("BIT", 0x2002), ("BPL", "wait1"),
        "wait2:", ("BIT", 0x2002), ("BPL", "wait2"),
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
        ("LDX#", 0x00),
        "copy:", ("LDAx", LIST), ("STAx", 0x0300), ("INX",), ("CPX#", length), ("BNE", "copy"),
        ("LDA#", length), ("STA", 0x32),
        ("JSR", 0xC53A),
        ("LDA#", 0x00), ("STA", 0x2005), ("STA", 0x2005),
        ("LDA#", 0x00), ("STA", 0x2000),
        ("LDA#", 0x1E), ("STA", 0x2001),
        "loop:", ("JMP", CODE),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("teams")
    ap.add_argument("-o", "--out", default="build/select-screen.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    teams = json.load(open(args.teams))["teams"]
    lst = build_list(teams)
    if len(lst) >= 0x100:
        raise SystemExit(f"display list too long: {len(lst)}")
    palette = bytes([0x1A, 0x30, 0x27, 0x0F] + [0x0F] * 28)
    code = bytearray(screen_code(len(lst)))
    loop_addr = CODE + len(code) - 3
    code[-2] = loop_addr & 0xFF
    code[-1] = loop_addr >> 8
    fixed = bank_file(FIXED)
    rom[fixed + (LIST - 0xC000):fixed + (LIST - 0xC000) + len(lst)] = lst
    rom[fixed + (PALETTE - 0xC000):fixed + (PALETTE - 0xC000) + 32] = palette
    rom[fixed + (CODE - 0xC000):fixed + (CODE - 0xC000) + len(code)] = code

    hook = fixed + (HOOK - 0xC000)
    rom[hook:hook + 5] = bytes([0x20, CODE & 0xFF, CODE >> 8, 0xEA, 0xEA])
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}")
    print(f"  list {len(lst)} bytes at ${LIST:04X}, code {len(code)} bytes at ${CODE:04X}")


if __name__ == "__main__":
    main()
