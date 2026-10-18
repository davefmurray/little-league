#!/usr/bin/env python3
"""Isolated flag test: copy 6 tiles and draw one 24x16 flag.

No page list, no cursor, no name/marker. If this renders one flag, the CHR
copy and a single display-list run are correct; the bug is in the eight-run
page logic.

    python3 tools/build_flag_test.py build/flags32.nes -o build/flag-test.nes
"""
import argparse

HEADER = 16
BANK = 0x4000
FIXED = 15
HOOK = 0xCBE6
CODE = 0x8000
TILES = 0xA000
SLOTS = 0xAC00
PAL = 0xAD00


def bf(bank):
    return HEADER + bank * BANK


def assemble(lines, origin):
    labels, code, branches, fix = {}, bytearray(), [], []
    for item in lines:
        if isinstance(item, str) and item.endswith(":"):
            labels[item[:-1]] = len(code)
            continue
        op = item[0]
        if op in ("LDA#", "LDX#", "LDY#", "CPX#", "CPY#", "ADC#"):
            code.append({"LDA#": 0xA9, "LDX#": 0xA2, "LDY#": 0xA0,
                         "CPX#": 0xE0, "CPY#": 0xC0, "ADC#": 0x69}[op])
            code.append(item[1])
        elif op in ("LDAx", "STAx"):
            a = item[1]
            code += bytes([0xBD if op == "LDAx" else 0x9D, a & 0xFF, a >> 8])
        elif op == "LDAy":
            a = item[1]
            code += bytes([0xB9, a & 0xFF, a >> 8])
        elif op == "LDA":
            code += bytes([0xAD, item[1] & 0xFF, item[1] >> 8])
        elif op == "BIT":
            code += bytes([0x2C, item[1] & 0xFF, item[1] >> 8])
        elif op == "STX":
            code += bytes([0x8E, item[1] & 0xFF, item[1] >> 8])
        elif op == "STA":
            code += bytes([0x8D, item[1] & 0xFF, item[1] >> 8])
        elif op == "LDAiY":
            code += bytes([0xB1, item[1]])
        elif op in ("JSR", "JMP"):
            opc = 0x20 if op == "JSR" else 0x4C
            if isinstance(item[1], str):
                fix.append((len(code), item[1]))
                code += bytes([opc, 0, 0])
            else:
                code += bytes([opc, item[1] & 0xFF, item[1] >> 8])
        elif op in ("BNE", "BPL"):
            branches.append((len(code), item[1]))
            code += bytes([0xD0 if op == "BNE" else 0x10, 0])
        elif op in ("INX", "INY", "DEX", "DEY", "ASL", "LSR", "TXA", "SEI", "CLC", "RTS"):
            code.append({"INX": 0xE8, "INY": 0xC8, "DEX": 0xCA, "DEY": 0x88,
                         "ASL": 0x0A, "LSR": 0x4A, "TXA": 0x8A, "SEI": 0x78,
                         "CLC": 0x18, "RTS": 0x60}[op])
        else:
            raise SystemExit(f"bad op {op}")
    for pos, label in branches:
        code[pos + 1] = (labels[label] - (pos + 2)) & 0xFF
    for pos, label in fix:
        a = origin + labels[label]
        code[pos + 1] = a & 0xFF
        code[pos + 2] = a >> 8
    return bytes(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/flag-test.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    code = assemble([
        ("SEI",),
        "w1:", ("BIT", 0x2002), ("BPL", "w1"),
        "w2:", ("BIT", 0x2002), ("BPL", "w2"),
        ("LDA#", 0x00), ("STA", 0x2000), ("STA", 0x2001),
        ("LDA#", 0x1E), ("JSR", 0xC102),
        ("LDA#", 0x00), ("JSR", 0xC11C),
        ("LDA#", 0x01), ("JSR", 0xC134),
        ("LDA#", 0x3F), ("STA", 0x2006), ("LDA#", 0x00), ("STA", 0x2006),
        ("LDX#", 0x00),
        "pal:", ("LDAx", PAL), ("STA", 0x2007), ("INX",), ("CPX#", 0x20), ("BNE", "pal"),
        ("LDA#", 0x20), ("STA", 0x2006), ("LDA#", 0x00), ("STA", 0x2006),
        ("LDX#", 0x00), ("LDY#", 0x04),
        "clr:", ("LDA#", 0x20), ("STA", 0x2007), ("INX",), ("BNE", "clr"), ("DEY",), ("BNE", "clr"),
        ("LDA#", 0x23), ("STA", 0x2006), ("LDA#", 0xC0), ("STA", 0x2006),
        ("LDX#", 0x40), ("LDA#", 0x00),
        "attr:", ("STA", 0x2007), ("DEX",), ("BNE", "attr"),
        # CHR copy: 6 tiles
        ("LDX#", 0x00),
        "copy:", ("LDAx", SLOTS), ("STA", 0x04),
        ("LSR",), ("LSR",), ("LSR",), ("LSR",), ("STA", 0x2006),
        ("LDA", 0x04), ("ASL",), ("ASL",), ("ASL",), ("ASL",), ("STA", 0x2006),
        ("TXA",), ("ASL",), ("ASL",), ("ASL",), ("ASL",), ("STA", 0x00),
        ("LDA#", 0xA0), ("STA", 0x01),
        ("LDY#", 0x00),
        "byte:", ("LDAiY", 0x00), ("STA", 0x2007), ("INY",), ("CPY#", 0x10), ("BNE", "byte"),
        ("INX",), ("CPX#", 0x06), ("BNE", "copy"),
        # one flag run at $2062
        ("LDX#", 0x00),
        ("LDA#", 0x20), ("STAx", 0x0300), ("INX",),
        ("LDA#", 0x62), ("STAx", 0x0300), ("INX",),
        ("LDY#", 0x00),
        "tl:", ("LDAy", SLOTS), ("STAx", 0x0300), ("INX",), ("INY",), ("CPY#", 0x06), ("BNE", "tl"),
        ("LDA#", 0xFE), ("STAx", 0x0300), ("INX",),
        ("STX", 0x32), ("JSR", 0xC53A),
        ("LDA#", 0x00), ("STA", 0x2005), ("STA", 0x2005),
        ("LDA#", 0x1E), ("STA", 0x2001),
        "loop:", ("JMP", "loop"),
    ], CODE)

    b10 = bf(10)
    rom[b10:b10 + len(code)] = code
    rom[b10 + (TILES - 0x8000):b10 + (TILES - 0x8000) + 96] = rom[b10 + (TILES - 0x8000):b10 + (TILES - 0x8000) + 96]
    pal = bytes([0x1A, 0x30, 0x16, 0x12] + [0x0F] * 28)
    rom[b10 + (PAL - 0x8000):b10 + (PAL - 0x8000) + 32] = pal
    fixed = bf(FIXED)
    rom[fixed + (HOOK - 0xC000):fixed + (HOOK - 0xC000) + 5] = bytes([0x20, 0x00, 0xFF, 0xEA, 0xEA])
    rom[fixed + (0xFF00 - 0xC000):fixed + (0xFF00 - 0xC000) + 8] = bytes([0xA9, 0x0A, 0x20, 0x4E, 0xC1, 0x4C, 0x00, 0x80])
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: {len(code)} bytes")


if __name__ == "__main__":
    main()
