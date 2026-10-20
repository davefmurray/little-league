#!/usr/bin/env python3
"""Extend the 16-entry team-name pointer table to 32 teams.

The scene-16 name loader at bank 1 $AF53 does

    AF53 ASL A / TAY
    AF55 LDA $B2D6,Y      ; pointer low
    AF5A LDA $B2D7,Y      ; pointer high
    AF63 LDA ($00),Y / STA $06B5,X ... until $FF

With team >= 16, Y >= 32 reads past the 16-entry table into the name strings,
producing a bogus pointer; the copy loop then runs until it happens to see $FF
(or hangs forever, which is what team 16 did).

This tool builds a 32-entry table + placeholder names in bank 1 free space
($BC80-$BD3F) and repoints the two loads. Teams 16-31 get "TEAM 17".."TEAM 32".

    python3 tools/build_names32.py build/launch-direct.nes -o build/names32.nes
"""
import argparse

HEADER = 16
PRG = 0x4000
BANK1 = 1
OLD_TABLE = 0xB2D6
NEW_TABLE = 0xBC80
NEW_NAMES = 0xBCC0
NAME_LEN = 8
OLD_SHORT = 0x9280
NEW_SHORT = 0xBD40
NEW_SHORT_NAMES = 0xBD80
SHORT_LEN = 12


def off(addr):
    """File offset of a bank-1 address ($8000-$BFFF)."""
    return HEADER + BANK1 * PRG + (addr - 0x8000)


def foff(rom, addr):
    """File offset of a fixed-bank address ($C000-$FFFF)."""
    return HEADER + (rom[4] - 1) * PRG + (addr - 0xC000)


def b7off(addr):
    """File offset of the old bank-7 copy of the fixed bank."""
    return HEADER + 7 * PRG + (addr - 0x8000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/names32.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())

    # 16 original pointers, then 16 placeholders.
    table = bytearray()
    for team in range(16):
        table += bytes(rom[off(OLD_TABLE + 2 * team):off(OLD_TABLE + 2 * team) + 2])
    names = bytearray()
    for team in range(16, 32):
        ptr = NEW_NAMES + (team - 16) * NAME_LEN
        table += bytes([ptr & 0xFF, ptr >> 8])
        text = f"TEAM {team + 1}".encode("ascii")
        names += text[:NAME_LEN - 1].ljust(NAME_LEN - 1, b" ") + b"\xFF"
    assert len(table) == 64 and len(names) == 16 * NAME_LEN

    rom[off(NEW_TABLE):off(NEW_TABLE) + len(table)] = table
    rom[off(NEW_NAMES):off(NEW_NAMES) + len(names)] = names

    # $AF55 B9 D6 B2 -> B9 80 BC ; $AF5A B9 D7 B2 -> B9 81 BC
    rom[off(0xAF56):off(0xAF56) + 2] = bytes([NEW_TABLE & 0xFF, NEW_TABLE >> 8])
    rom[off(0xAF5B):off(0xAF5B) + 2] = bytes([(NEW_TABLE + 1) & 0xFF,
                                              (NEW_TABLE + 1) >> 8])

    # Short-name table: 16 original pointers + 16 placeholders.  Entry format
    # is [pad count] + 10 chars + $FF.
    short = bytearray()
    for team in range(16):
        short += bytes(rom[off(OLD_SHORT + 2 * team):
                          off(OLD_SHORT + 2 * team) + 2])
    short_names = bytearray()
    for team in range(16, 32):
        ptr = NEW_SHORT_NAMES + (team - 16) * SHORT_LEN
        short += bytes([ptr & 0xFF, ptr >> 8])
        text = f"T{team + 1}".encode("ascii")
        short_names += bytes([0]) + text.ljust(10)[:10] + b"\xFF"
    assert len(short) == 64 and len(short_names) == 16 * SHORT_LEN

    rom[off(NEW_SHORT):off(NEW_SHORT) + len(short)] = short
    rom[off(NEW_SHORT_NAMES):off(NEW_SHORT_NAMES) + len(short_names)] = short_names

    # $C965 B9 80 92 -> B9 40 BD ; $C96A B9 81 92 -> B9 41 BD
    # These live in the FIXED bank ($C000), not bank 1.
    rom[foff(rom, 0xC966):foff(rom, 0xC966) + 2] = bytes(
        [NEW_SHORT & 0xFF, NEW_SHORT >> 8])
    rom[foff(rom, 0xC96B):foff(rom, 0xC96B) + 2] = bytes(
        [(NEW_SHORT + 1) & 0xFF, (NEW_SHORT + 1) >> 8])

    # Bank 7 carries a copy of the same loader ($8958); the field HUD reaches
    # it through the bank-7 mapping.  Patch its two operands too.
    rom[b7off(0x8966):b7off(0x8966) + 2] = bytes(
        [NEW_SHORT & 0xFF, NEW_SHORT >> 8])
    rom[b7off(0x896B):b7off(0x896B) + 2] = bytes(
        [(NEW_SHORT + 1) & 0xFF, (NEW_SHORT + 1) >> 8])

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: table ${NEW_TABLE:04X}, names ${NEW_NAMES:04X}")


if __name__ == "__main__":
    main()
