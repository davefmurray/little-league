#!/usr/bin/env python3
"""Apply the gameplay repairs to the pinned direct31 ROM.

    .venv/bin/python tools/build_gameplay32.py build/direct31.nes -o build/gameplay32.nes
"""
import argparse
import hashlib
from pathlib import Path

from build_bank11 import assemble

ROOT = Path(__file__).resolve().parent.parent
HEADER = bytes.fromhex("4E45531A101010000000000000000000")
BANK = 0x4000
ROM_SIZE = len(HEADER) + 16 * BANK + 16 * 0x2000
BASE_SHA256 = "d043ecdfc46c4d50c509db30f757425759a556dec3258be462fa9b3d81091ec1"
PAIR36_SHA256 = "bf86fffd907718f72478733be63c5e3938446488205dbcee0a33b1138c28ea4c"

LINEUP_ASM = [
    "STX $09",
    "LDA $04EF,X",
    "CMP #$1C",
    "BCS high",
    "ASL A",
    "ASL A",
    "ASL A",
    "CLC",
    "ADC $04EF,X",
    "TAY",
    "low_loop:",
    "LDA $FD80,Y",
    "STA $06E2,X",
    "INX",
    "INX",
    "INY",
    "CPX #$12",
    "BCC low_loop",
    "RTS",
    "high:",
    "SBC #$1C",
    "STA $09",
    "ASL A",
    "ASL A",
    "ASL A",
    "CLC",
    "ADC $09",
    "TAY",
    "STX $09",
    "high_loop:",
    "LDA $FE7C,Y",
    "STA $06E2,X",
    "INX",
    "INX",
    "INY",
    "CPX #$12",
    "BCC high_loop",
    "RTS",
]

ROW_ASM = [
    "LDA $05",
    "BEQ done",
    "LDA $01",
    "ORA #$40",
    "JMP $C794",
    "done:",
    "RTS",
]


def off(bank, addr):
    return len(HEADER) + bank * BANK + addr - (0xC000 if bank == 15 else 0x8000)


def build_rom(base: bytes) -> bytes:
    if len(base) != ROM_SIZE:
        raise ValueError(f"expected {ROM_SIZE} bytes, got {len(base)}")
    if base[:len(HEADER)] != HEADER:
        raise ValueError("expected direct31 iNES header, 16 PRG banks and 16 CHR banks")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned direct31")

    lineup, _ = assemble(LINEUP_ASM, 0xBF40)
    row, _ = assemble(ROW_ASM, 0xFBF0)
    if len(lineup) != 58 or len(row) != 12:
        raise ValueError("assembled helpers do not fit their exact reservations")

    changes = [
        (15, 0xC790, bytes.fromhex("A5 01 09 40"), bytes.fromhex("4C F0 FB EA")),
        (15, 0xFBF0, b"\xff" * 12, row),
        (4, 0xAD42, bytes.fromhex("86 09 BD"), bytes.fromhex("4C 40 BF")),
        (4, 0xBF40, b"\xff" * 58, lineup),
        # FF90 loads X=FF and abandons its caller when it jumps to the main loop.
        (15, 0xFFB3, bytes.fromhex("4C 09 CC FF"), bytes.fromhex("9A 4C 09 CC")),
    ]
    for bank, addr, expected, replacement in changes:
        start = off(bank, addr)
        actual = base[start:start + len(expected)]
        if actual != expected:
            raise ValueError(f"bank {bank} ${addr:04X}: expected {expected.hex(' ')}, "
                             f"got {actual.hex(' ')}")
        if len(replacement) != len(expected):
            raise ValueError(f"bank {bank} ${addr:04X}: repair changes ROM layout")

    rom = bytearray(base)
    for bank, addr, expected, replacement in changes:
        start = off(bank, addr)
        rom[start:start + len(expected)] = replacement
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned direct31.nes")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    protected = [args.rom]
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in ("direct31.nes", "direct31-pair36.nes"))
    for path in protected:
        if (args.out.resolve() == path.resolve()
                or (args.out.exists() and path.exists() and args.out.samefile(path))):
            ap.error(f"output aliases protected input {path}")
    if (args.out.is_file()
            and hashlib.sha256(args.out.read_bytes()).hexdigest() in (BASE_SHA256, PAIR36_SHA256)):
        ap.error("output aliases protected input direct31 or pair36 artifact")

    try:
        rom = build_rom(args.rom.read_bytes())
    except ValueError as exc:
        ap.error(str(exc))
    args.out.write_bytes(rom)
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
