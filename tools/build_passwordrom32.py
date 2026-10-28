#!/usr/bin/env python3
"""Install 32-team passwords, CONTINUE routing and a view-only team list.

    .venv/bin/python tools/build_passwordrom32.py build/control32.nes -o build/password32.nes
"""
import argparse
import hashlib
from pathlib import Path

from build_bank11 import assemble
from build_control32 import BASE_SHA256 as RESULTS_SHA256
from build_results32 import BASE_SHA256 as ROLES_SHA256
from build_roles32 import BASE_SHA256 as TABLES_SHA256
from build_teamtables32 import HEADER, PROTECTED_NAMES, PROTECTED_SHA256, ROM_SIZE, ROOT, off
from password32_6502 import BANK11_SEGMENTS, BANK12_SEGMENTS

BASE_SHA256 = "a1caf9a28e750a777343f2bdbd5c02987a03ccac0f58b6257e62dbee0faf30a8"
DECODE_ADDRESS = 0xFCC0
ENCODE_ADDRESS = 0xFCE2
LIST_ADDRESS = 0xFEA0
VIEW_ADDRESS = 0x8680
CONTINUE_ADDRESS = 0xBE40
DECODE_ASM = [
    "LDA #$0C", "JSR $C14E", "JSR $8000", "BCC valid",
    "LDA #$01", "JSR $C14E", "LDA #$00", "STA $07ED", "RTS",
    "valid:", "LDA #$00", "STA $2000", "LDA #$0B", "JSR $C14E", "JMP $8600",
]
ENCODE_ASM = [
    "LDA $07EF", "CMP #$32", "BNE stock", "LDA $07ED", "BEQ stock",
    "LDA #$0C", "JSR $C14E", "JSR $8003", "LDA #$05", "JMP $C14E",
    "stock:", "JMP $A036",
]
LIST_ASM = [
    "LDA $07EF", "CMP #$32", "BNE stock", "LDA $07ED", "BEQ stock",
    "LDA #$01", "STA $07F0", "draw:", "LDA #$00", "STA $2000",
    "LDA #$0B", "JSR $C14E", "JMP $8000",
    "stock:", "LDA #$13", "STA $047B", "LDA #$00", "STA $047C", "RTS",
]
VIEW_ASM = [
    "LDA $07FC", "CMP #$1F", "BCC mode", "LDA #$01", "STA $07F0",
    "mode:", "LDA $07F0", "BNE view", "JMP $8100",
    "view:", "JSR $C199", "LDA #$00", "STA $2003", "LDA #$02", "STA $4014",
    "JSR $810B", "LDA $07C6", "STA $07C8",
    "poll:", "JSR $810B", "LDA $07C8", "EOR #$FF", "AND $07C6",
    "LDX $07C6", "STX $07C8", "AND #$C0", "BEQ poll",
    "release:", "JSR $810B", "LDA $07C6", "BNE release",
    "LDA #$06", "STA $047B", "LDA #$00", "STA $047D", "STA $07F0", "JMP $FF90",
]


def patches():
    _, list_labels = assemble(LIST_ASM, LIST_ADDRESS)
    continue_asm = [
        "LDA $07ED", "BEQ password", "LDA $07EF", "CMP #$32", "BNE stock",
        "LDA #$00", "STA $07F0", f"JMP ${list_labels['draw']:04X}",
        "stock:", "LDA #$13", "STA $047B", "LDA #$02", "STA $047C", "RTS",
        "password:", "LDA #$18", "STA $047B", "RTS",
    ]
    result = [
        (1, 0x94F8, bytes.fromhex("ad ed 07"), bytes.fromhex("4c 40 be")),
        (1, 0xA584, bytes.fromhex("20 a2 a8"), bytes.fromhex("20 c0 fc")),
        (5, 0x9FF5, bytes.fromhex("20 36 a0"), bytes.fromhex("20 e2 fc")),
        (1, 0x951C, bytes.fromhex("a9 13 8d 7b 04 a9 00 8d 7c 04 60"),
         bytes.fromhex("4c a0 fe") + b"\xea" * 8),
        (11, 0x808B, bytes.fromhex("4c 00 81"), bytes.fromhex("4c 80 86")),
    ]
    for bank, address, lines, capacity in (
        (15, DECODE_ADDRESS, DECODE_ASM, ENCODE_ADDRESS - DECODE_ADDRESS),
        (15, ENCODE_ADDRESS, ENCODE_ASM, 0xFD00 - ENCODE_ADDRESS),
        (15, LIST_ADDRESS, LIST_ASM, 0xFEC9 - LIST_ADDRESS),
        (11, VIEW_ADDRESS, VIEW_ASM, 0x86E0 - VIEW_ADDRESS),
        (1, CONTINUE_ADDRESS, continue_asm, 0x30),
    ):
        code, _ = assemble(lines, address)
        if len(code) > capacity:
            raise ValueError(f"bank{bank} ${address:04X}: helper exceeds reservation")
        result.append((bank, address, b"\xff" * len(code), code))
    for bank, segments in ((11, BANK11_SEGMENTS), (12, BANK12_SEGMENTS)):
        for address, code in segments:
            result.append((bank, address, b"\xff" * len(code), code))
    return tuple(result)


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected control32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned control32")
    rom = bytearray(base)
    claimed = set()
    for bank, address, expected, code in patches():
        start = off(bank, address)
        region = set(range(start, start + len(code)))
        if len(code) != len(expected) or claimed & region:
            raise ValueError("overlapping or unequal patch ranges")
        if base[start:start + len(expected)] != expected:
            raise ValueError(f"bank{bank} ${address:04X}: unexpected bytes")
        claimed.update(region)
        rom[start:start + len(code)] = code
    return bytes(rom)


def protect_output(source, output):
    protected = [source, *Path(__file__).parent.glob("*.py")]
    for directory in (ROOT / "build", source.resolve().parent):
        protected.extend(directory / name for name in (*PROTECTED_NAMES, "teamtables32.nes", "roles32.nes",
                                                       "results32.nes", "control32.nes"))
    for path in protected:
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise ValueError(f"output aliases protected input {path}")
    if (output.is_file()
            and hashlib.sha256(output.read_bytes()).hexdigest() in
            PROTECTED_SHA256 | {BASE_SHA256, RESULTS_SHA256, ROLES_SHA256, TABLES_SHA256}):
        raise ValueError("output aliases protected input ROM artifact")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        rom = build_rom(args.rom.read_bytes())
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
