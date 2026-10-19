#!/usr/bin/env python3
"""M3: bank 11 bracket logic (init + advance), table at $A000.

    python3 tools/build_bank11.py build/dispatcher.nes -o build/bank11.nes
"""
import argparse
import re

from py65.assembler import Assembler
from py65.devices.mpu6502 import MPU

HEADER = 16
PRG = 0x4000
CODE = 0x8000
TABLE = 0xA000

ASM = [
    ("init:",),
    ("LDX #$00",),
    ("init_loop:",),
    ("TXA",),
    ("STA $7700,X",),
    ("LDA #$00",),
    ("STA $7740,X",),
    ("INX",),
    ("CPX #$20",),
    ("BNE init_loop",),
    ("RTS",),
    ("seed:",),
    ("LDA $07C3",),
    ("STA $7700",),
    ("STA $02",),
    ("LDX #$01",),
    ("LDA #$00",),
    ("seed_loop:",),
    ("CMP $02",),
    ("BEQ seed_skip",),
    ("STA $7700,X",),
    ("INX",),
    ("seed_skip:",),
    ("CLC",),
    ("ADC #$01",),
    ("CMP #$20",),
    ("BNE seed_loop",),
    ("RTS",),
    ("advance:",),
    ("LDX #$00",),
    ("adv_loop:",),
    ("CPX $0746",),
    ("BEQ adv_done",),
    ("STX $02",),
    ("TXA",),
    ("ASL A",),
    ("STA $00",),
    ("TXA",),
    ("CLC",),
    ("ADC $00",),
    ("TAY",),
    ("LDA $A000,Y",),
    ("TAY",),
    ("LDA $7700,Y",),
    ("STA $01",),
    ("TAX",),
    ("INC $7740,X",),
    ("LDX $02",),
    ("TXA",),
    ("ASL A",),
    ("STA $00",),
    ("TXA",),
    ("CLC",),
    ("ADC $00",),
    ("TAY",),
    ("LDA $A002,Y",),
    ("TAY",),
    ("LDA $01",),
    ("STA $7700,Y",),
    ("LDX $02",),
    ("INX",),
    ("BNE adv_loop",),
    ("adv_done:",),
    ("RTS",),
]


def gen32():
    recs = []
    for i in range(16):
        recs.append((i * 2, i * 2 + 1, 32 + i))
    for i in range(8):
        recs.append((32 + i * 2, 32 + i * 2 + 1, 48 + i))
    for i in range(4):
        recs.append((48 + i * 2, 48 + i * 2 + 1, 56 + i))
    for i in range(2):
        recs.append((56 + i * 2, 56 + i * 2 + 1, 60 + i))
    recs.append((60, 61, 62))
    return recs


BRANCHES = {"BNE", "BEQ", "BCC", "BCS", "BMI", "BPL", "BVC", "BVS"}


def size_of(line):
    mnemonic, _, operand = line.partition(" ")
    if not operand or operand == "A":
        return 1
    if operand.startswith("#"):
        return 2
    if re.fullmatch(r"\$[0-9A-Fa-f]{1,2}", operand):
        return 2
    if mnemonic in BRANCHES:
        return 2
    return 3


def assemble(lines, origin):
    a = Assembler(MPU())
    labels, pc = {}, origin
    for item in lines:
        line = item[0] if isinstance(item, tuple) else item
        if line.endswith(":"):
            labels[line[:-1]] = pc
            continue
        pc += size_of(line)
    code = bytearray()
    for item in lines:
        line = item[0] if isinstance(item, tuple) else item
        if line.endswith(":"):
            continue
        for name, addr in sorted(labels.items(), key=lambda kv: -len(kv[0])):
            line = re.sub(rf"\b{re.escape(name)}\b", f"${addr:04X}", line)
        code += bytes(a.assemble(line, origin + len(code)))
    return bytes(code), labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/bank11.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    code, labels = assemble(ASM, CODE)
    off = HEADER + 11 * PRG
    rom[off:off + len(code)] = code

    data = bytes(b for r in gen32() for b in r)
    rom[off + (TABLE - CODE):off + (TABLE - CODE) + len(data)] = data

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: code {len(code)} bytes at $8000, table $A000 "
          f"(init ${labels['init']:04X}, seed ${labels['seed']:04X}, "
          f"advance ${labels['advance']:04X})")


if __name__ == "__main__":
    main()
