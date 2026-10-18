#!/usr/bin/env python3
"""Copy-on-select proof using PRG RAM.

PRG ROM cannot be written at runtime, so the cache lives in the cart's 8 KiB PRG
RAM at $6000. The 16-entry roster pointer table is mirrored to $7000 and every
real table read is repointed there.

Boot routine (fixed bank):
  - copy $8400..$841F -> $7000..$701F
  - switch to bank 8 and copy two team blocks -> $6000 / $6170
  - point RAM table entries 5 and 6 at those blocks
  - restore bank 0 and the skipped PPU-off write

Team 5 (New York) and 6 (California) get names ZZA01.. / ZZB01.. in bank 8 so a
lineup screen proves the cache is being used.

    python3 tools/build_copy_on_select.py BASE data/roster.json -o build/copy-on-select.nes
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
FIXED_OLD = 7
FIXED_NEW = TARGET_BANKS - 1

BASE_HOOK = 0xCBE6
ROUTINE = 0xFB90
RAM_TABLE = 0x7000
ROM_TABLE = 0x8400
CACHE_A = 0x6000
CACHE_B = 0x6170
SOURCE_A = 0x8000
SOURCE_B = 0x8170

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


def team_block(rom, team, names):
    table = bank_file(4) + (ROM_TABLE - 0x8000)
    ptr = rom[table + team * 2] | (rom[table + team * 2 + 1] << 8)
    off = bank_file(4) + (ptr - 0x8000)
    block = bytearray(rom[off:off + STRIDE])
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
        if op in ("LDA#", "LDX#", "CPX#"):
            code.append({"LDA#": 0xA9, "LDX#": 0xA2, "CPX#": 0xE0}[op])
            code.append(item[1])
        elif op in ("LDAx", "STAx"):
            addr = item[1]
            code += bytes([0xBD if op == "LDAx" else 0x9D, addr & 0xFF, addr >> 8])
        elif op == "STA":
            code += bytes([0x8D, item[1] & 0xFF, item[1] >> 8])
        elif op == "JSR":
            code += bytes([0x20, item[1] & 0xFF, item[1] >> 8])
        elif op == "BNE":
            branches.append((len(code), item[1]))
            code += bytes([0xD0, 0x00])
        elif op == "INX":
            code.append(0xE8)
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
        ("LDX#", 0x00),
        "a1:", ("LDAx", SOURCE_A), ("STAx", CACHE_A), ("INX",), ("BNE", "a1"),
        ("LDX#", 0x00),
        "a2:", ("LDAx", SOURCE_A + 0x100), ("STAx", CACHE_A + 0x100), ("INX",), ("CPX#", 0x70), ("BNE", "a2"),
        ("LDX#", 0x00),
        "b1:", ("LDAx", SOURCE_B), ("STAx", CACHE_B), ("INX",), ("BNE", "b1"),
        ("LDX#", 0x00),
        "b2:", ("LDAx", SOURCE_B + 0x100), ("STAx", CACHE_B + 0x100), ("INX",), ("CPX#", 0x70), ("BNE", "b2"),
        ("LDA#", CACHE_A & 0xFF), ("STA", RAM_TABLE + 10),
        ("LDA#", CACHE_A >> 8), ("STA", RAM_TABLE + 11),
        ("LDA#", CACHE_B & 0xFF), ("STA", RAM_TABLE + 12),
        ("LDA#", CACHE_B >> 8), ("STA", RAM_TABLE + 13),
        ("LDA#", 0x00), ("STA", 0x2001),
        ("LDA#", 0x00), ("JSR", 0xC14E),
        ("RTS",),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("roster")
    ap.add_argument("-o", "--out", default="build/copy-on-select.nes")
    args = ap.parse_args()

    subprocess.run([sys.executable, "tools/build_16x20.py", args.rom, args.roster,
                    "-o", "build/16x20.nes"], check=True)
    base = bytearray(open("build/16x20.nes", "rb").read())
    out = expand16(base)

    def names(p):
        return [f"{p}{i:02d}" for i in range(1, PLAYERS + 1)]

    out[bank_file(8):bank_file(8) + STRIDE] = team_block(base, 5, names("ZZA"))
    out[bank_file(8) + STRIDE:bank_file(8) + 2 * STRIDE] = team_block(base, 6, names("ZZB"))

    for bank, addrs in READS.items():
        for addr in addrs:
            base = 0xC000 if bank in (7, 15) else 0x8000
            off = bank_file(bank) + (addr - base)
            if off + 2 >= len(out) or out[off + 2] != 0x84:
                raise SystemExit(f"expected $84 operand at bank {bank} ${addr:04X}")
            out[off + 2] = 0x70

    code = routine()
    fixed = bank_file(FIXED_NEW)
    out[fixed + (ROUTINE - 0xC000):fixed + (ROUTINE - 0xC000) + len(code)] = code

    hook = fixed + (BASE_HOOK - 0xC000)
    if bytes(out[hook:hook + 5]) != b"\xa9\x00\x8d\x01\x20":
        raise SystemExit("unexpected hook bytes")
    out[hook:hook + 5] = bytes([0x20, ROUTINE & 0xFF, ROUTINE >> 8, 0xEA, 0xEA])

    open(args.out, "wb").write(out)
    print(f"wrote {args.out}")
    print(f"  routine ${ROUTINE:04X} ({len(code)} bytes), table RAM ${RAM_TABLE:04X}")
    print(f"  cache ${CACHE_A:04X}/${CACHE_B:04X}, reads patched: "
          f"{sum(len(v) for v in READS.values())}")


if __name__ == "__main__":
    main()
