#!/usr/bin/env python3
"""Extend team-indexed bonus, batting-bias and CPU ownership tables.

    .venv/bin/python tools/build_teamtables32.py build/cpu32.nes -o build/teamtables32.nes

High teams receive neutral bonuses and batting bias, and CPU ownership.
The persistent ownership mask remains 16 bits.
"""
import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path

from build_bank11 import assemble

ROOT = Path(__file__).resolve().parent.parent
HEADER = bytes.fromhex("4E45531A101010000000000000000000")
BANK = 0x4000
ROM_SIZE = len(HEADER) + 16 * BANK + 16 * 0x2000
BASE_SHA256 = "338c1cc9bf80f6b77f441b472e91fd7536223d0b1b129fc8b7307ccb6f006327"
PROTECTED_SHA256 = {
    "58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e",
    BASE_SHA256,
    "deff2f62ab1dff112726846d12aed08b3d6e7fdbb39b7e5ae1d8fbca4b0a1b89",
    "3ce7b8d849d46b7b0e4582750221237875f1db86a3388039b75a6d017aa76317",
    "d043ecdfc46c4d50c509db30f757425759a556dec3258be462fa9b3d81091ec1",
    "bf86fffd907718f72478733be63c5e3938446488205dbcee0a33b1138c28ea4c",
}
PROTECTED_NAMES = ("direct31.nes", "direct31-pair36.nes", "gameplay32.nes", "cpu32.nes")
BONUSES = bytes.fromhex(
    "00 00 11 21 00 00 11 21 00 11 11 22 00 00 11 21 "
    "00 11 11 22 00 00 00 11 00 00 11 21 33 00 11 21 "
    "00 00 01 13 00 11 12 12 00 11 22 42 00 01 02 13 "
    "00 00 00 11 00 11 22 44 00 11 21 33 00 00 11 22")
TIERS = bytes.fromhex("00 00 00 00 00 00 00 00 01 01 01 01 02 02 03 03")
BIAS = bytes.fromhex("02 FF FF 00 FF FE FE FE FE FE FF FE FF FF FE 00")
BATTING_TABLES = ((0, 0xBD00), (1, 0xBF00), (3, 0xBD00), (5, 0xBD00))
READER_ASM = [
    "LDY $04EF,X", "CPY #$10", "BCC low", "LDA #$80", "JMP $9CCC",
    "low:", "JMP $9CB5",
]
WRITER_ASM = [
    "LDY $04EF,X", "CPY #$10", "BCC low", "RTS", "low:", "JMP $9F49",
]


def off(bank, addr):
    origin = 0xC000 if bank == 15 else 0x8000
    if not 0 <= bank < 16 or not origin <= addr <= origin + BANK:
        raise ValueError("address outside PRG bank")
    return len(HEADER) + bank * BANK + addr - origin


@dataclass(frozen=True)
class Change:
    bank: int
    addr: int
    before: bytes
    after: bytes


def change_manifest():
    reader, _ = assemble(READER_ASM, 0xBD40)
    writer, _ = assemble(WRITER_ASM, 0xBD50)
    if len(reader) != 15 or len(writer) != 11:
        raise ValueError("ownership helpers exceed their exact reservations")
    changes = [
        Change(4, 0xAA99, bytes.fromhex("B9 BB AA"), bytes.fromhex("B9 00 B7")),
        Change(4, 0xB700, b"\xff" * 128, BONUSES + bytes(64)),
        Change(5, 0x9CB2, bytes.fromhex("BC EF 04"), bytes.fromhex("4C 40 BD")),
        Change(5, 0x9F46, bytes.fromhex("BC EF 04"), bytes.fromhex("4C 50 BD")),
        Change(5, 0xBD40, b"\xff" * 15, reader),
        Change(5, 0xBD50, b"\xff" * 11, writer),
    ]
    for bank, addr in BATTING_TABLES:
        changes.extend((
            Change(bank, 0xBB90, bytes.fromhex("79 4F BC"),
                   bytes((0x79, addr & 255, addr >> 8))),
            Change(bank, addr, b"\xff" * 32, BIAS + bytes(16)),
        ))
    occupied = set()
    for change in changes:
        start = off(change.bank, change.addr)
        end = start + len(change.before)
        if (len(change.before) != len(change.after) or not change.before
                or end > off(change.bank, 0x10000 if change.bank == 15 else 0xC000)
                or occupied.intersection(range(start, end))):
            raise ValueError("overlapping or invalid change manifest")
        occupied.update(range(start, end))
    return tuple(changes)


def build_rom(base):
    if len(base) != ROM_SIZE:
        raise ValueError(f"expected {ROM_SIZE} bytes, got {len(base)}")
    if base[:len(HEADER)] != HEADER:
        raise ValueError("expected CPU32 iNES header with 16 PRG and 16 CHR banks")
    checks = [(4, 0xAAAB, TIERS), (4, 0xAABB, BONUSES),
              (5, 0x9CD0, bytes((1, 2, 4, 8, 16, 32, 64, 128)) * 2)]
    checks.extend((bank, 0xBC4F, BIAS) for bank, _ in BATTING_TABLES)
    changes = change_manifest()
    checks.extend((change.bank, change.addr, change.before) for change in changes)
    for bank, addr, expected in checks:
        start = off(bank, addr)
        if base[start:start + len(expected)] != expected:
            raise ValueError(f"bank {bank} ${addr:04X}: expected bytes or reservation differ")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned cpu32")
    rom = bytearray(base)
    for change in changes:
        start = off(change.bank, change.addr)
        rom[start:start + len(change.after)] = change.after
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned cpu32.nes")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    protected = [args.rom, Path(__file__), Path(__file__).with_name("test_teamtables32.py")]
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in PROTECTED_NAMES)
    try:
        for path in protected:
            if (args.out.resolve() == path.resolve()
                    or (args.out.exists() and path.exists() and args.out.samefile(path))):
                ap.error(f"output aliases protected input {path}")
        if (args.out.is_file()
                and hashlib.sha256(args.out.read_bytes()).hexdigest() in PROTECTED_SHA256):
            ap.error("output aliases protected input ROM artifact")
        rom = build_rom(args.rom.read_bytes())
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
