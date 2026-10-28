#!/usr/bin/env python3
"""Build the 32-team selector, seed-once entry and shared CPU ownership mask.

    .venv/bin/python tools/build_control32.py build/results32.nes -o build/control32.nes
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_bank11 import assemble
import build_select_screen as selector
from build_teamtables32 import (
    Change, HEADER, PROTECTED_NAMES, PROTECTED_SHA256, ROM_SIZE, ROOT, off,
)

BASE_SHA256 = "9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b"
TEAMS = ROOT / "data/teams32.json"
MASK_BYTES = (0x074B, 0x074C, 0x07F1, 0x07F2)
NEW_SERIES = 0x86E0
RELEASE = 0x8540
ENTRY = 0x9600
COMMIT = 0x9620
BITS = bytes((1, 2, 4, 8, 16, 32, 64, 128))
ENTRY_ASM = [
    "JSR $C199", "LDA #$00", "STA $2003", "LDA #$02", "STA $4014",
    "JSR $8181", "held:", "JSR $8353", "LDA $07C6", "BNE held", "RTS",
]
COMMIT_ASM = [
    "LDA #$FF", "STA $074B", "STA $074C", "STA $07F1", "STA $07F2",
    "LDA $07C3", "AND #$07", "TAX", "LDA BITS_ADDR,X", "EOR #$FF", "STA $00",
    "LDA $07C3", "LSR A", "LSR A", "LSR A", "TAX", "LDA $00",
    "CPX #$02", "BCS high", "AND $074B,X", "STA $074B,X", "JMP $FF14",
    "high:", "AND $07EF,X", "STA $07EF,X", "JMP $FF14",
]
HIGHOWN_ASM = [
    "LDA $9CC0,Y", "CPY #$18", "BCS second", "AND $07F1", "BCC test",
    "second:", "AND $07F2", "test:", "BEQ store", "LDA #$80",
    "store:", "SEC", "JMP $9CCC",
]
NEW_SERIES_ASM = [
    "LDA #$32", "STA $07EF", "LDA #$01", "STA $07ED",
    "LDA #$00", "STA $07F0", "JSR $8200", "JMP $8000",
]
RELEASE_ASM = ["held:", "JSR $810B", "LDA $07C6", "BNE held", "JMP $8360"]
TRAMPOLINE_ASM = ["LDA #$0B", "JSR $C14E", "JMP $8380"]


def replace(data, start, before, after):
    if len(before) != len(after) or data[start:start + len(before)] != before:
        raise ValueError(f"unexpected bytes or reservation at offset ${start:05X}")
    data[start:start + len(after)] = after


def source_selector_bank(document):
    if not isinstance(document, dict):
        raise ValueError("expected selector team document")
    teams = document.get("teams")
    if (not isinstance(teams, list) or len(teams) != 32
            or any(not isinstance(team, dict) or type(team.get("id")) is not int
                   or team["id"] != i for i, team in enumerate(teams))):
        raise ValueError("expected 32 teams ordered by id")
    for team in teams:
        for key in ("name", "code"):
            value = team.get(key)
            if (not isinstance(value, str) or not value
                    or any(not 0x20 <= ord(c) <= 0x7E for c in value)
                    or (key == "code" and len(value) > 3)):
                raise ValueError(f"invalid selector {key} for team {team['id']}")
    bank = bytearray(b"\xff" * 0x4000)

    def put(address, data):
        replace(bank, address - 0x8000, b"\xff" * len(data), data)

    code = selector.screen_code()
    if selector.CODE + len(code) > selector.LIST_BASE:
        raise ValueError("selector code overlaps its lists")
    put(selector.CODE, code)
    pointers = bytearray()
    for page in range(4):
        listing = selector.page_list(teams, page)
        if len(listing) + 1 > selector.STRIDE:
            raise ValueError("selector page exceeds its reservation")
        address = selector.LIST_BASE + page * selector.STRIDE
        put(address, (bytes((len(listing),)) + listing).ljust(selector.STRIDE, b"\xff"))
        pointers += bytes((address & 255, address >> 8))
    put(selector.PTR, pointers)
    put(selector.PALETTE, bytes((0x1A, 0x30, 0x27, 0x0F)) + b"\x0f" * 28)
    markers = (0x20A1, 0x20A8, 0x20AF, 0x20B6, 0x2161, 0x2168, 0x216F, 0x2176)
    put(selector.MARKER, b"".join(a.to_bytes(2, "little") for a in markers))
    for team in teams:
        put(selector.NAMES + team["id"] * 16,
            team["name"].encode("ascii")[:14].ljust(14, b" ") + b"\xff\xff")
    flag_addresses = (0x2062, 0x2069, 0x2070, 0x2077, 0x2122, 0x2129, 0x2130, 0x2137)
    put(selector.FLAGADDR, b"".join(a.to_bytes(2, "little") for a in flag_addresses))
    return bytes(bank)


def selector_bank(document):
    bank = bytearray(source_selector_bank(document))
    entry, _ = assemble(ENTRY_ASM, ENTRY)
    sized, _ = assemble([s.replace("BITS_ADDR", "$9600") for s in COMMIT_ASM], COMMIT)
    bits_address = COMMIT + len(sized)
    commit, _ = assemble([s.replace("BITS_ADDR", f"${bits_address:04X}") for s in COMMIT_ASM], COMMIT)
    if len(entry) != 25 or len(commit) != 58 or len(sized) != len(commit):
        raise ValueError("selector helpers exceed their exact reservations")
    for address, store in ((0x826F, "8e f3 07"), (0x82A3, "8e f4 07"),
                           (0x82E0, "8e f5 07"), (0x82E6, "8d f7 07"), (0x82EC, "8e f6 07")):
        replace(bank, address - 0x8000, bytes.fromhex(store), b"\xea" * 3)
    replace(bank, 0x73, bytes.fromhex("20 81 81"), bytes.fromhex("20 00 96"))
    replace(bank, 0xDE, bytes.fromhex("68 68 a9 12 8d 7b 04 4c 09 cc"),
            bytes.fromhex("4c 20 96") + b"\xea" * 7)
    replace(bank, ENTRY - 0x8000, b"\xff" * len(entry), entry)
    replace(bank, COMMIT - 0x8000, b"\xff" * (len(commit) + len(BITS)), commit + BITS)
    return bytes(bank)


def change_manifest(document):
    changes = [
        Change(1, 0x9509, b"\x0c", b"\x12"),
        Change(15, 0xFF3B, b"\x0b", b"\x0a"),
        Change(15, 0xFF50, b"\x0b", b"\x0a"),
        Change(15, 0xFF54, bytes.fromhex("80 83"), bytes.fromhex("00 80")),
        Change(5, 0xBD47, bytes.fromhex("a9 80 4c cc 9c"), bytes.fromhex("4c 60 bd ea ea")),
        Change(10, 0x8000, b"\xff" * 0x4000, selector_bank(document)),
        Change(11, 0x8000, bytes.fromhex("a9 0f 8d c3 07"), b"\xea" * 5),
        Change(11, 0x801C, bytes.fromhex("20 00 82"), b"\xea" * 3),
        Change(11, 0x8391, bytes.fromhex("4c 00 80"), bytes.fromhex("4c e0 86")),
        Change(11, 0x8176, bytes.fromhex("4c 60 83"), bytes.fromhex("4c 40 85")),
    ]
    for bank, address, lines, size in (
        (15, 0xFF14, TRAMPOLINE_ASM, 8), (5, 0xBD60, HIGHOWN_ASM, 23),
        (11, NEW_SERIES, NEW_SERIES_ASM, 21), (11, RELEASE, RELEASE_ASM, 11),
    ):
        code, _ = assemble(lines, address)
        if len(code) != size:
            raise ValueError(f"bank{bank} ${address:04X}: helper exceeds exact reservation")
        changes.append(Change(bank, address, b"\xff" * size, code))
    occupied = set()
    for change in changes:
        start = off(change.bank, change.addr)
        end = start + len(change.before)
        if (not change.before or len(change.before) != len(change.after)
                or end > off(change.bank, 0x10000 if change.bank == 15 else 0xC000)
                or occupied.intersection(range(start, end))):
            raise ValueError("overlapping or invalid control32 manifest")
        occupied.update(range(start, end))
    return tuple(changes)


def build_rom(base, document=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected results32 ROM size and iNES header")
    document = json.loads(TEAMS.read_text()) if document is None else document
    changes = change_manifest(document)
    checks = [
        (11, 0x8600, b"\xff" * 0x80), (11, 0x8680, b"\xff" * 0x60),
        (15, 0xCC79, bytes.fromhex("99 58")), (15, 0xFEA0, b"\xff" * 43),
        (11, 0x8105, bytes.fromhex("20 d0 81")),
        (11, 0x81D0, bytes.fromhex("20 0b 81 ad c6 07 8d c8 07 60")),
    ]
    checks.extend((c.bank, c.addr, c.before) for c in changes)
    for bank, address, expected in checks:
        start = off(bank, address)
        if base[start:start + len(expected)] != expected:
            raise ValueError(f"bank{bank} ${address:04X}: unexpected bytes or reservation")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned results32")
    rom = bytearray(base)
    for change in changes:
        replace(rom, off(change.bank, change.addr), change.before, change.after)
    return bytes(rom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="pinned results32.nes")
    parser.add_argument("--teams", type=Path, default=TEAMS)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args()
    protected = [args.rom, args.teams, TEAMS, *Path(__file__).parent.glob("*.py")]
    names = (*PROTECTED_NAMES, "teamtables32.nes", "roles32.nes", "results32.nes")
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in names)
    hashes = PROTECTED_SHA256 | {
        BASE_SHA256, "775595bef3506de25f704fe0530f6833d8ce0541155110920e739f19425cd006",
        "ddb83443653af408926d98843709e7831fed8fabd40f5e762db655c9a868431b",
    }
    try:
        for path in protected:
            if (args.out.resolve() == path.resolve()
                    or (args.out.exists() and path.exists() and args.out.samefile(path))):
                parser.error(f"output aliases protected input {path}")
        if args.out.is_file() and hashlib.sha256(args.out.read_bytes()).hexdigest() in hashes:
            parser.error("output aliases protected input ROM artifact")
        rom = build_rom(args.rom.read_bytes(), json.loads(args.teams.read_text()))
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
