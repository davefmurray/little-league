#!/usr/bin/env python3
"""iNES ROM inspector: header, PRG/CHR bank tables, vectors, strings.

Usage: python3 tools/rominfo.py "Little League Baseball - Championship Series (USA).nes"
"""
import sys, zlib, collections

MAPPERS = {
    0: "NROM", 1: "MMC1 (SxROM)", 2: "UxROM", 3: "CNROM", 4: "MMC3 (TxROM)",
    5: "MMC5", 7: "AxROM", 9: "MMC2 (PxROM)", 10: "MMC4 (FxROM)",
    11: "Color Dreams", 66: "GxROM", 69: "Sunsoft FME-7", 71: "Camerica",
}


def header(rom):
    if rom[:4] != b"NES\x1a":
        raise SystemExit("not an iNES file")
    prg, chr_, f6, f7, f8 = rom[4], rom[5], rom[6], rom[7], rom[8]
    return {
        "prg": prg,
        "chr": chr_,
        "mapper": (f7 & 0xF0) | (f6 >> 4),
        "mirroring": "vertical" if f6 & 1 else "horizontal",
        "battery": bool(f6 & 2),
        "trainer": bool(f6 & 4),
        "four_screen": bool(f6 & 8),
        "nes2": (f7 & 0x0C) == 0x08,
        "submapper": (f8 >> 4) if (f7 & 0x0C) == 0x08 else 0,
        "prg_ram_shifts": f8 & 0x0F,
    }


def bank_table(data, size, label):
    rows = []
    for i in range(0, len(data), size):
        b = data[i:i + size]
        zeros = b.count(0)
        ffs = b.count(0xFF)
        rows.append({
            "idx": i // size,
            "crc": zlib.crc32(b) & 0xFFFFFFFF,
            "zero_pct": 100.0 * zeros / len(b),
            "ff_pct": 100.0 * ffs / len(b),
            "head": b[:8].hex(" "),
        })
    # mark duplicates of an earlier bank
    seen = {}
    for r in rows:
        key = (r["crc"], size)
        if key in seen:
            r["dup"] = seen[key]
        else:
            seen[key] = r["idx"]
    return rows


def team_layout(rom, h):
    """Detect the bank-8 32-team roster layout (team 16 at $9700)."""
    if h["prg"] >= 16:
        o = 16 + 8 * 16384 + 16 * 0x170
        if len(rom) >= o + 6 and all(0x20 <= b < 0x7F for b in rom[o:o + 6]):
            return f"32-team bank8 (team 16 at ${0x8000 + 16 * 0x170:04X}, 20 players)"
    return "stock 16-team"


def main():
    path = sys.argv[1]
    rom = open(path, "rb").read()
    h = header(rom)
    prg_off = 16 + (512 if h["trainer"] else 0)
    prg_len = h["prg"] * 16384
    chr_len = h["chr"] * 8192
    prg = rom[prg_off:prg_off + prg_len]
    chr_ = rom[prg_off + prg_len:prg_off + prg_len + chr_len]

    print(f"file      : {path}")
    print(f"size      : {len(rom)} bytes (header 16 + PRG {prg_len} + CHR {chr_len})")
    print(f"mapper    : {h['mapper']} ({MAPPERS.get(h['mapper'], 'unknown')})")
    print(f"mirroring : {h['mirroring']}   battery: {h['battery']}   "
          f"trainer: {h['trainer']}   four-screen: {h['four_screen']}")
    print(f"PRG       : {prg_len // 1024} KiB = {h['prg']} x 16 KiB")
    print(f"CHR       : {chr_len // 1024} KiB = {h['chr']} x 8 KiB")
    print(f"layout    : {team_layout(rom, h)}")
    print()

    print("PRG banks (16 KiB, CPU $8000/$C000 windows)")
    print("  #   CRC32     %00   %FF  dup  vectors NMI/RESET/IRQ   first bytes")
    for r in bank_table(prg, 16384, "PRG"):
        vec = ""
        if r["idx"] == h["prg"] - 1:           # fixed bank at $C000
            tail = prg[r["idx"] * 16384:]
            nmi, res, irq = (int.from_bytes(tail[0x3FFA:0x4000][i:i + 2], "little")
                             for i in (0, 2, 4))
            vec = f" {nmi:04X}/{res:04X}/{irq:04X}"
        print(f"  {r['idx']:2d}  {r['crc']:08X}  {r['zero_pct']:5.1f} {r['ff_pct']:5.1f}"
              f"  {('=' + str(r['dup'])) if 'dup' in r else '   '}  "
              f"{vec or ' ' * 18}  {r['head']}")
    print()

    print("CHR banks (8 KiB, PPU $0000/$1000 windows)")
    print("  #   CRC32     %00   %FF  dup  first bytes")
    chr_rows = bank_table(chr_, 8192, "CHR")
    for r in chr_rows:
        print(f"  {r['idx']:2d}  {r['crc']:08X}  {r['zero_pct']:5.1f} {r['ff_pct']:5.1f}"
              f"  {('=' + str(r['dup'])) if 'dup' in r else '   '}  {r['head']}")
    uniq = len({r["crc"] for r in chr_rows})
    print(f"\n  unique CHR banks: {uniq} of {len(chr_rows)}")
    print(f"  CHR looks like: {'CHR-RAM (tile data in PRG)' if not chr_rows else 'CHR-ROM'}")
    print()

    # text strings in PRG
    strings, cur = [], bytearray()
    for b in prg:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= 6:
                strings.append(cur.decode())
            cur.clear()
    if len(cur) >= 6:
        strings.append(cur.decode())
    print(f"PRG ASCII strings >= 6 chars: {len(strings)}")
    for s in strings[:40]:
        print("   ", repr(s))

    # quick opcode census (rough code/data signal)
    print("\nPRG byte histogram top 8:")
    for b, n in collections.Counter(prg).most_common(8):
        print(f"   ${b:02X}: {n:6d} ({100.0 * n / len(prg):4.1f}%)")


if __name__ == "__main__":
    main()
