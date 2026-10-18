#!/usr/bin/env python3
"""Trace MMC1 reset path with a 6502 disassembler (py65).

Maps PRG banks into a 64K image (bank 7 fixed at $C000), walks control flow
from the reset vector, and logs writes into the $8000-$FFFF MMC1 register space.

Usage: .venv/bin/python tools/trace.py ROM.nes [max_instr]
"""
import sys, re
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler

ROM = sys.argv[1]
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 400

rom = open(ROM, "rb").read()
prg_off = 16
prg = rom[prg_off:prg_off + rom[4] * 16384]
nbanks = rom[4]

mem = bytearray(0x10000)
# reset state: last bank fixed at $C000, bank 0 at $8000
mem[0x8000:0xC000] = prg[0:0x4000]
mem[0xC000:0x10000] = prg[(nbanks - 1) * 0x4000:]

mpu = MPU()
mpu.memory = mem          # bytearray supports indexing/slicing
d = Disassembler(mpu)

reset = mem[0xFFFC] | (mem[0xFFFD] << 8)
nmi = mem[0xFFFA] | (mem[0xFFFB] << 8)
irq = mem[0xFFFE] | (mem[0xFFFF] << 8)
print(f"vectors: NMI ${nmi:04X}  RESET ${reset:04X}  IRQ/BRK ${irq:04X}")
print(f"reset at PRG bank {nbanks-1}\n")

writes = []
seen = set()
queue = [("RESET", reset)]
count = 0
while queue and count < LIMIT:
    tag, pc = queue.pop(0)
    print(f"\n--- {tag} @ ${pc:04X} ---")
    steps = 0
    while count < LIMIT and steps < 120:
        if pc in seen:
            print(f"  ${pc:04X}: (already traced)")
            break
        seen.add(pc)
        n, text = d.instruction_at(pc)
        raw = mem[pc:pc + n]
        print(f"  ${pc:04X}: {raw.hex(' '):<9} {text}")
        count += 1
        steps += 1
        # MMC1 register writes are stores to $8000-$FFFF
        m = re.match(r"ST[AXY] .*\$([89a-fA-F][0-9a-fA-F]{3})", text)
        if m:
            writes.append((pc, text))
        # control flow
        op = text.split()[0]
        if op in ("RTS", "RTI"):
            break
        if op == "JMP":
            tgt = int(re.search(r"\$([0-9a-fA-F]{4})", text).group(1), 16)
            pc = tgt
            continue
        if op == "JSR":
            tgt = int(re.search(r"\$([0-9a-fA-F]{4})", text).group(1), 16)
            queue.append((f"JSR from ${pc:04X}", tgt))
            pc += n
            continue
        if op.startswith("B") and re.search(r"\$([0-9a-fA-F]{4})", text):
            if op not in ("BIT", "BRK"):
                tgt = int(re.search(r"\$([0-9a-fA-F]{4})", text).group(1), 16)
                queue.append((f"{op} from ${pc:04X}", tgt))
            pc += n
            continue
        pc += n

print("\n=== writes to $8000-$FFFF (possible MMC1 serial writes) ===")
for pc, t in writes:
    print(f"  ${pc:04X}: {t}")
