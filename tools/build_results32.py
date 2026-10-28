#!/usr/bin/env python3
"""Advance the bracket only for completed games and credit the live winning team.

    .venv/bin/python tools/build_results32.py build/roles32.nes -o build/results32.nes
"""
import argparse
import hashlib
from pathlib import Path

from build_bank11 import assemble
from build_score_winner import SCORE_WINNER
from build_roles32 import BASE_SHA256 as TEAMTABLES_SHA256
from build_teamtables32 import HEADER, PROTECTED_NAMES, PROTECTED_SHA256, ROM_SIZE, ROOT, off

BASE_SHA256 = "ddb83443653af408926d98843709e7831fed8fabd40f5e762db655c9a868431b"
GATE_ADDRESS = 0xFFC0
WINNER_ADDRESS = 0x83A0
GATE_SIZE = 39
WINNER_SIZE = 48
OLD_GATE = bytes.fromhex(
    "ea ea ea ea ea ea a2 ff 8e ff 9f a9 0b 8d 00 e0 4a 8d 00 e0 "
    "4a 8d 00 e0 4a 8d 00 e0 4a 8d 00 e0 a9 0b 85 27 4c a0 83")
INPUT_ASM = ["JSR $810B", "LDA $07C6", "STA $07C8", "RTS"]
GATE_ASM = [
    "LDA $04E2", "BEQ ongoing", "LDA $04D0", "BEQ ongoing", "LDA #$0B", "JSR $C14E", "JMP $83A0",
    "ongoing:", "JMP $B63D",
]
WINNER_ASM = [
    "LDX $07FC", "CPX #$1F", "BCS done",
    "LDA $048B", "CMP $048C", "BEQ tie", "BCC away",
    "LDA $04EF", "JMP store", "away:", "LDA $04F0", "JMP store",
    "tie:", "TXA", "ASL A", "TAY", "LDA $7700,Y",
    "store:", "STA $7720,X", "INC $07FC", "done:", "JMP $8000",
]


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected roles32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned roles32")
    rom = bytearray(base)
    for bank, address, expected, lines, size in (
        (15, GATE_ADDRESS, OLD_GATE, GATE_ASM, GATE_SIZE),
        (11, 0x8105, bytes.fromhex("8d c8 07"), ["JSR $81D0"], 3),
        (11, 0x81D0, b"\xff" * 10, INPUT_ASM, 10),
        (11, WINNER_ADDRESS, SCORE_WINNER.ljust(WINNER_SIZE, b"\xff"), WINNER_ASM, WINNER_SIZE),
    ):
        start = off(bank, address)
        if len(expected) != size or base[start:start + size] != expected:
            raise ValueError(f"bank{bank} ${address:04X}: unexpected bracket code")
        code, _ = assemble(lines, address)
        if len(code) > size:
            raise ValueError(f"bank{bank} ${address:04X}: code exceeds reservation")
        rom[start:start + size] = code.ljust(size, b"\xea")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    protected = [args.rom, Path(__file__), Path(__file__).with_name("test_results32.py")]
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in (*PROTECTED_NAMES, "teamtables32.nes", "roles32.nes"))
    try:
        for path in protected:
            if (args.out.resolve() == path.resolve()
                    or (args.out.exists() and path.exists() and args.out.samefile(path))):
                ap.error(f"output aliases protected input {path}")
        if (args.out.is_file()
                and hashlib.sha256(args.out.read_bytes()).hexdigest() in PROTECTED_SHA256 | {BASE_SHA256, TEAMTABLES_SHA256}):
            ap.error("output aliases protected input ROM artifact")
        rom = build_rom(args.rom.read_bytes())
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
