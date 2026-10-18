#!/usr/bin/env python3
"""32-team bank-8 build with a 16-team PRG-RAM cache.

Bank 8 holds all 32 rosters (20 players each). At boot the fixed-bank routine:
  - mirrors the pointer table to PRG RAM $7F00
  - copies teams 0-15 (0x1700 bytes) from bank 8 into $6000
  - writes their RAM table entries ($6000 + team*0x170)
  - restores bank 0 and the skipped PPU-off write

The 16-team UI is unchanged; teams 16-31 are staged for the UI/bracket work.

    python3 tools/build_32x20.py BASE data/roster.json -o build/32x20.nes
"""
import argparse
import subprocess
import sys

HEADER = 16
BANK = 0x4000
TARGET_BANKS = 16
PLAYERS = 20
RECORD = 16
STRIDE = PLAYERS * RECORD + 48
TEAMS = 32
UI_TEAMS = 16
FIXED_OLD = 7
FIXED_NEW = TARGET_BANKS - 1

BASE_HOOK = 0xCBE6
ROUTINE = 0xFB90
RAM_TABLE = 0x7F00
ROM_TABLE = 0x8400
RAM_CACHE = 0x6000
BANK8 = 0x8000

READS = {
    4: [0xB085, 0xB08C, 0xB0A6, 0xB0AB, 0xAB2C, 0xAB33, 0x8432, 0x8439],
    15: [0xCB2C, 0xCB36],
}


def bank_file(bank):
    return HEADER + bank * BANK


def expand16(rom):
    prg = rom[HEADER:HEADER + rom[4] * BANK]
    chr_ = rom[HEADER + rom[4] * BANK:]
    out = bytearray(b"\xff" * (TARGET_BANKS * BANK))
    out[:len(prg)] = prg
    out[(TARGET_BANKS - 1) * BANK:] = prg[FIXED_OLD * BANK:(FIXED_OLD + 1) * BANK]
    header = bytearray(rom[:HEADER])
    header[4] = TARGET_BANKS
    return bytearray(header) + out + bytearray(chr_)


def pointer(rom, team):
    off = bank_file(4) + (ROM_TABLE - 0x8000) + team * 2
    return rom[off] | (rom[off + 1] << 8)


def team_block(rom, team, names=None):
    off = bank_file(4) + (pointer(rom, team) - 0x8000)
    block = bytearray(rom[off:off + STRIDE])
    if names:
        for p in range(PLAYERS):
            block[p * RECORD:p * RECORD + 6] = names[p].ljust(6).encode("ascii")
    return block


def assemble(lines):
    labels, code, branches = {}, bytearray(), []
    for item in lines:
        if isinstance(item, str) and item.endswith(":"):
            labels[item[:-1]] = len(code)
            continue
        op = item[0]
        if op in ("LDA#", "LDX#", "CPX#", "LDY#", "ADDC"):
            code.append({"LDA#": 0xA9, "LDX#": 0xA2, "CPX#": 0xE0,
                         "LDY#": 0xA0, "ADDC": 0x69}[op])
            code.append(item[1])
        elif op in ("LDAx", "STAx"):
            addr = item[1]
            code += bytes([0xBD if op == "LDAx" else 0x9D, addr & 0xFF, addr >> 8])
        elif op in ("LDAz", "STAz", "INCz"):
            code += bytes([{"LDAz": 0xA5, "STAz": 0x85, "INCz": 0xE6}[op], item[1]])
        elif op in ("LDAiY", "STAiY"):
            code += bytes([0xB1 if op == "LDAiY" else 0x91, item[1]])
        elif op == "STA":
            code += bytes([0x8D, item[1] & 0xFF, item[1] >> 8])
        elif op == "JSR":
            code += bytes([0x20, item[1] & 0xFF, item[1] >> 8])
        elif op == "BNE":
            branches.append((len(code), item[1]))
            code += bytes([0xD0, 0x00])
        elif op in ("INX", "INY", "DEX", "CLC"):
            code.append({"INX": 0xE8, "INY": 0xC8, "DEX": 0xCA, "CLC": 0x18}[op])
        elif op == "RTS":
            code.append(0x60)
        else:
            raise SystemExit(f"bad op {op}")
    for pos, label in branches:
        code[pos + 1] = (labels[label] - (pos + 2)) & 0xFF
    return bytes(code)


def routine():
    return assemble([
        ("LDA#", 0x04), ("JSR", 0xC14E),
        ("LDX#", 0x00),
        "t:", ("LDAx", ROM_TABLE), ("STAx", RAM_TABLE), ("INX",), ("CPX#", 0x20), ("BNE", "t"),
        ("LDA#", 0x08), ("JSR", 0xC14E),
        ("LDA#", 0x00), ("STAz", 0x00), ("LDA#", BANK8 >> 8), ("STAz", 0x01),
        ("LDA#", 0x00), ("STAz", 0x02), ("LDA#", RAM_CACHE >> 8), ("STAz", 0x03),
        ("LDX#", 0x17),
        "page:", ("LDY#", 0x00),
        "byte:", ("LDAiY", 0x00), ("STAiY", 0x02), ("INY",), ("BNE", "byte"),
        ("INCz", 0x01), ("INCz", 0x03), ("DEX",), ("BNE", "page"),
        ("LDX#", 0x00),
        ("LDA#", RAM_CACHE & 0xFF), ("STAz", 0x04),
        ("LDA#", RAM_CACHE >> 8), ("STAz", 0x05),
        "ent:", ("LDAz", 0x04), ("STAx", RAM_TABLE),
        ("LDAz", 0x05), ("STAx", RAM_TABLE + 1),
        ("CLC",), ("LDAz", 0x04), ("ADDC", STRIDE & 0xFF), ("STAz", 0x04),
        ("LDAz", 0x05), ("ADDC", STRIDE >> 8), ("STAz", 0x05),
        ("INX",), ("INX",), ("CPX#", UI_TEAMS * 2), ("BNE", "ent"),
        ("LDA#", 0x00), ("STA", 0x2001),
        ("LDA#", 0x00), ("JSR", 0xC14E),
        ("RTS",),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("roster")
    ap.add_argument("-o", "--out", default="build/32x20.nes")
    args = ap.parse_args()

    subprocess.run([sys.executable, "tools/build_16x20.py", args.rom, args.roster,
                    "-o", "build/16x20.nes"], check=True)
    base = bytearray(open("build/16x20.nes", "rb").read())
    out = expand16(base)

    for t in range(TEAMS):
        if t < UI_TEAMS:
            block = team_block(base, t)
        else:
            block = team_block(base, UI_TEAMS - 1,
                               [f"B{t:02d}{p:02d}" for p in range(1, PLAYERS + 1)])
        off = bank_file(8) + t * STRIDE
        out[off:off + STRIDE] = block

    for bank, addrs in READS.items():
        for addr in addrs:
            b = 0xC000 if bank in (7, 15) else 0x8000
            off = bank_file(bank) + (addr - b)
            if out[off + 2] != 0x84:
                raise SystemExit(f"expected $84 operand at bank {bank} ${addr:04X}")
            out[off + 2] = RAM_TABLE >> 8

    code = routine()
    fixed = bank_file(FIXED_NEW)
    out[fixed + (ROUTINE - 0xC000):fixed + (ROUTINE - 0xC000) + len(code)] = code
    hook = fixed + (BASE_HOOK - 0xC000)
    if bytes(out[hook:hook + 5]) != b"\xa9\x00\x8d\x01\x20":
        raise SystemExit("unexpected hook bytes")
    out[hook:hook + 5] = bytes([0x20, ROUTINE & 0xFF, ROUTINE >> 8, 0xEA, 0xEA])

    open(args.out, "wb").write(out)
    print(f"wrote {args.out}")
    print(f"  32 teams in bank 8, {UI_TEAMS} cached at ${RAM_CACHE:04X}")
    print(f"  table ${RAM_TABLE:04X}, routine ${ROUTINE:04X} ({len(code)} bytes)")


if __name__ == "__main__":
    main()
