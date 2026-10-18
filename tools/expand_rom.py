#!/usr/bin/env python3
"""Expand an MMC1 NES ROM's PRG space safely.

MMC1 fixes the **last** 16 KiB PRG bank at $C000. The stock game's fixed bank is
bank 7 (the last of 8). Growing the PRG therefore moves the fixed window to the
new last bank, so the original bank 7 must be copied there or the reset vector
disappears.

This tool keeps banks 0-7 at their original file positions, copies bank 7 to the
new last bank, and fills the new banks with $FF. CHR is unchanged: MMC1 caps CHR
at 128 KiB and this ROM already uses all of it.

    python3 tools/expand_rom.py ROM -o build/expanded.nes --prg-banks 16
    python3 tools/expand_rom.py build/expanded.nes --inspect
"""
import argparse
import sys

HEADER = 16
PRG_BANK = 0x4000
CHR_BANK = 0x2000
MAX_MMC1_PRG_BANKS = 32  # 5-bit PRG register, 16 KiB units = 512 KiB
MAX_MMC1_CHR_BANKS = 16  # 5-bit CHR register, 4 KiB units = 128 KiB


def load(path):
    data = open(path, "rb").read()
    if len(data) < HEADER or data[:4] != b"NES\x1a":
        raise SystemExit(f"{path}: not an iNES ROM")
    prg = data[4]
    chr_ = data[5]
    mapper = (data[7] & 0xF0) | (data[6] >> 4)
    if mapper != 1:
        raise SystemExit(f"{path}: mapper {mapper}, expected 1 (MMC1)")
    need = HEADER + prg * PRG_BANK + chr_ * CHR_BANK
    if len(data) < need:
        raise SystemExit(f"{path}: truncated ({len(data)} < {need})")
    return {
        "path": path,
        "raw": data,
        "header": data[:HEADER],
        "prg": data[HEADER:HEADER + prg * PRG_BANK],
        "chr": data[HEADER + prg * PRG_BANK:HEADER + prg * PRG_BANK + chr_ * CHR_BANK],
        "prg_banks": prg,
        "chr_banks": chr_,
        "mapper": mapper,
    }


def vectors(bank):
    nmi = bank[0x3FFA] | (bank[0x3FFB] << 8)
    reset = bank[0x3FFC] | (bank[0x3FFD] << 8)
    irq = bank[0x3FFE] | (bank[0x3FFF] << 8)
    return nmi, reset, irq


def bank_of(blob, n):
    return blob[n * PRG_BANK:(n + 1) * PRG_BANK]


def expand(rom, target):
    if target <= rom["prg_banks"]:
        raise SystemExit(f"target {target} banks is not larger than {rom['prg_banks']}")
    if target > MAX_MMC1_PRG_BANKS:
        raise SystemExit(f"MMC1 supports at most {MAX_MMC1_PRG_BANKS} PRG banks")
    if rom["chr_banks"] > MAX_MMC1_CHR_BANKS:
        raise SystemExit(f"MMC1 supports at most {MAX_MMC1_CHR_BANKS} CHR banks")

    prg = bytearray(b"\xff" * (target * PRG_BANK))
    prg[:rom["prg_banks"] * PRG_BANK] = rom["prg"]

    fixed = rom["prg_banks"] - 1
    prg[(target - 1) * PRG_BANK:target * PRG_BANK] = bank_of(rom["prg"], fixed)

    header = bytearray(rom["header"])
    header[4] = target
    header[5] = rom["chr_banks"]

    out = bytes(header) + bytes(prg) + rom["chr"]
    return out, target, fixed


def verify(rom, out, target, fixed):
    exp_size = HEADER + target * PRG_BANK + rom["chr_banks"] * CHR_BANK
    if len(out) != exp_size:
        raise SystemExit(f"size mismatch: {len(out)} != {exp_size}")
    if out[4] != target:
        raise SystemExit("header PRG count not written")
    out_prg = out[HEADER:HEADER + target * PRG_BANK]
    if out_prg[:rom["prg_banks"] * PRG_BANK] != rom["prg"]:
        raise SystemExit("original PRG banks changed")
    if bank_of(out_prg, target - 1) != bank_of(rom["prg"], fixed):
        raise SystemExit("fixed bank copy is not identical to the original")
    out_chr = out[HEADER + target * PRG_BANK:]
    if out_chr != rom["chr"]:
        raise SystemExit("CHR changed")
    if vectors(bank_of(out_prg, target - 1)) != vectors(bank_of(rom["prg"], fixed)):
        raise SystemExit("vectors do not match")

    free = list(range(rom["prg_banks"], target - 1))
    print(f"  size        {len(out):,} bytes")
    print(f"  PRG         {target} banks ({target * 16} KiB)")
    print(f"  CHR         {rom['chr_banks']} banks ({rom['chr_banks'] * 8} KiB, unchanged)")
    print(f"  fixed bank  {target - 1} (copy of original bank {fixed})")
    print(f"  vectors     " + "/".join(f"${v:04X}" for v in vectors(bank_of(out_prg, target - 1))))
    print(f"  free banks  {free[0]}-{free[-1]} ({len(free)} banks, {len(free) * 16} KiB)")


def inspect(path):
    rom = load(path)
    prg = rom["prg"]
    print(f"file        {path}")
    print(f"size        {len(rom['raw']):,} bytes")
    print(f"mapper      {rom['mapper']} (MMC1)")
    print(f"PRG         {rom['prg_banks']} banks ({rom['prg_banks'] * 16} KiB)")
    print(f"CHR         {rom['chr_banks']} banks ({rom['chr_banks'] * 8} KiB)")
    nmi, reset, irq = vectors(bank_of(prg, rom["prg_banks"] - 1))
    print(f"fixed bank  {rom['prg_banks'] - 1}")
    print(f"vectors     NMI ${nmi:04X}  RESET ${reset:04X}  IRQ ${irq:04X}")
    if rom["prg_banks"] < MAX_MMC1_PRG_BANKS:
        print(f"PRG room    {MAX_MMC1_PRG_BANKS - rom['prg_banks']} more banks "
              f"({(MAX_MMC1_PRG_BANKS - rom['prg_banks']) * 16} KiB) within MMC1")
    else:
        print("PRG room    none (MMC1 maximum)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", help="write expanded ROM here")
    ap.add_argument("--prg-banks", type=int, default=16,
                    help="target PRG banks (default 16 = 256 KiB)")
    ap.add_argument("--inspect", action="store_true", help="report layout and exit")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.rom)
        return

    if not args.out:
        ap.error("-o/--out is required unless --inspect is used")

    rom = load(args.rom)
    out, target, fixed = expand(rom, args.prg_banks)
    print(f"expanding {args.rom} -> {args.out}")
    verify(rom, out, target, fixed)
    open(args.out, "wb").write(out)
    print(f"  wrote       {args.out}")


if __name__ == "__main__":
    main()
