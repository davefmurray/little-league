#!/usr/bin/env python3
"""Align runtime pitcher flags with declared pitcher records.

    .venv/bin/python tools/build_roles32.py build/teamtables32.nes -o build/roles32.nes
"""
import argparse
import hashlib
from pathlib import Path

from build_bank11 import assemble
from build_cpu32 import (CACHE_ASM, FLAG_OFFSET, PLAYER_BYTES, RUNTIME_PLAYER_BYTES,
                         SPECIALISTS, STORED_PLAYER_BYTES, TRAILER_BYTES)
from build_teamtables32 import HEADER, PROTECTED_NAMES, PROTECTED_SHA256, ROM_SIZE, ROOT, off

BASE_SHA256 = "775595bef3506de25f704fe0530f6833d8ce0541155110920e739f19425cd006"
CACHE_ADDRESS = 0xFB90
CACHE_RESERVATION = 83
FLAGS_ASM = [
    "LDA $FC80,X", "STA $00", "LDA $FCA0,X", "STA $01", "LDY #$00",
    "players:", "LDA ($00),Y", "STA ($02),Y", "INY",
    f"CPY #${RUNTIME_PLAYER_BYTES:02X}", "BNE players",
    f"LDY #${FLAG_OFFSET:02X}",
    "flags:", "LDA ($02),Y", "AND #$7F",
    f"CPY #${len(SPECIALISTS) * PLAYER_BYTES + FLAG_OFFSET:02X}", "BCS store_flag",
    "ORA #$80",
    "store_flag:", "STA ($02),Y", "TYA", "CLC", f"ADC #${PLAYER_BYTES:02X}", "TAY",
    f"CPY #${RUNTIME_PLAYER_BYTES + FLAG_OFFSET:02X}", "BNE flags",
    "CLC", "LDA $00", f"ADC #${STORED_PLAYER_BYTES & 255:02X}", "STA $00",
    "LDA $01", f"ADC #${STORED_PLAYER_BYTES >> 8:02X}", "STA $01",
    "CLC", "LDA $02", f"ADC #${RUNTIME_PLAYER_BYTES:02X}", "STA $02",
    "LDA $03", "ADC #$00", "STA $03", "LDY #$00",
    "trailer:", "LDA ($00),Y", "STA ($02),Y", "INY",
    f"CPY #${TRAILER_BYTES:02X}", "BNE trailer", "RTS",
]


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected teamtables32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned teamtables32")
    for team in range(16, 32):
        start = off(8, 0x8000 + team * 0x170)
        selectors = [base[start + player * PLAYER_BYTES + 12] for player in range(15)]
        if selectors != [8, 16, 24] + [0] * 12:
            raise ValueError(f"team {team}: unexpected pitcher record assignments")
    expected, _ = assemble(CACHE_ASM, CACHE_ADDRESS)
    replacement, _ = assemble(FLAGS_ASM, CACHE_ADDRESS)
    start = off(15, CACHE_ADDRESS)
    if len(expected) != CACHE_RESERVATION or base[start:start + CACHE_RESERVATION] != expected:
        raise ValueError("runtime cache reservation differs from cpu32")
    if len(replacement) != 82:
        raise ValueError("role-normalizing cache helper must remain 82 bytes")
    rom = bytearray(base)
    rom[start:start + CACHE_RESERVATION] = replacement.ljust(CACHE_RESERVATION, b"\xff")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    protected = [args.rom, Path(__file__), Path(__file__).with_name("test_roles32.py")]
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in (*PROTECTED_NAMES, "teamtables32.nes"))
    try:
        for path in protected:
            if (args.out.resolve() == path.resolve()
                    or (args.out.exists() and path.exists() and args.out.samefile(path))):
                ap.error(f"output aliases protected input {path}")
        if (args.out.is_file()
                and hashlib.sha256(args.out.read_bytes()).hexdigest() in PROTECTED_SHA256 | {BASE_SHA256}):
            ap.error("output aliases protected input ROM artifact")
        rom = build_rom(args.rom.read_bytes())
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
