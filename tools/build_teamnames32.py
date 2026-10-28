#!/usr/bin/env python3
"""Repair all nine high-team display-name readers on the pinned password32 ROM.

    .venv/bin/python tools/build_teamnames32.py build/password32.nes -o build/teamnames32.nes
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from build_bank11 import assemble
from build_passwordrom32 import (
    BASE_SHA256 as CONTROL_SHA256, RESULTS_SHA256, ROLES_SHA256, TABLES_SHA256,
    protect_output as protect_prior_output,
)
from build_teamtables32 import PROTECTED_SHA256 as PRIOR_SHA256

ROOT = Path(__file__).resolve().parent.parent
HEADER = bytes.fromhex("4E45531A101010000000000000000000")
BANK = 0x4000
ROM_SIZE = len(HEADER) + 16 * BANK + 16 * 0x2000
BASE_SHA256 = "978abc4227eac24d0c779ea3fbbdfdc42c89ca0a1fcce350cff6db44501da34a"
PROTECTED_SHA256 = PRIOR_SHA256 | {
    BASE_SHA256, CONTROL_SHA256, RESULTS_SHA256, ROLES_SHA256, TABLES_SHA256,
}
TEAMS = ROOT / "data/teams32.json"

LONG_PTR = 0xBC80          # bank1, 32 x word, read by bank1 $AF55/$AF5A (operands unchanged)
HIGH_FULL = 0xBCC0         # bank1, 16 x 16: descriptor slot 3
HIGH_CODES = 0xBDC0        # bank1, 16 x 8: descriptor slot 2
SHORT_PTR = 0xBE70         # bank1, 32 x word, read by fixed $C965/$C96A
SHORT_REGIONS = ((0xBF20, 0xC000), (0xBEB0, 0xBF00))
LEGACY = (0xBC80, 0xBE40)  # legacy build_names32 block replaced here
FLAGS32 = 0xFD20           # fixed, 32 bytes, read by fixed $C9A9 ORA abs,Y
HUD_HOOK = 0x9A00
STOCK_FLAGS = bytes.fromhex("00 00 80 80 00 00 00 00 00 00 00 00 00 00 00 00")
NAME_COLUMNS = 14
CODE_COLUMNS = 5
NARROW_FROM = 12


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


def load_teams(path=TEAMS):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or "teams" not in data:
        raise ValueError("team metadata must contain a teams list")
    return validate_teams(data["teams"])


def validate_teams(teams):
    if (not isinstance(teams, (list, tuple)) or len(teams) != 32
            or any(not isinstance(t, dict) or type(t.get("id")) is not int
                   or t["id"] != i for i, t in enumerate(teams))):
        raise ValueError("team metadata must list ids 0..31 in order")
    for t in teams:
        name, code = t.get("name"), t.get("code")
        if (not isinstance(name, str) or not 1 <= len(name) <= NAME_COLUMNS
                or set(name) - set("ABCDEFGHIJKLMNOPQRSTUVWXYZ ")):
            raise ValueError(f"team {t['id']}: name {name!r} must be 1-14 of A-Z and space")
        if name != name.strip() or "  " in name:
            raise ValueError(f"team {t['id']}: name {name!r} has edge or double spaces")
        if (not isinstance(code, str) or not 2 <= len(code) <= 3
                or set(code) - set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
            raise ValueError(f"team {t['id']}: code {code!r} must be 2-3 of A-Z")
    return teams


def full_record(name):
    return name.encode("ascii").ljust(NAME_COLUMNS) + b"\xff\xff"


def code_record(code):
    return code.encode("ascii").ljust(CODE_COLUMNS) + b"\xff\xff\xff"


def short_entry(name):
    pad = (NAME_COLUMNS - len(name)) // 2
    return bytes([pad]) + name.encode("ascii") + b" " * (NAME_COLUMNS - pad - len(name)) + b"\xff"


def narrow_flag(name):
    return 0x80 if len(name) >= NARROW_FROM else 0x00


def word(addr):
    return bytes((addr & 255, addr >> 8))


def legacy_block(base):
    """The exact block tools/build_names32.py wrote, rebuilt from the input's stock tables."""
    def stock_ptrs(table):
        return b"".join(base[off(1, table + 2 * t):off(1, table + 2 * t) + 2] for t in range(16))
    long_ptr = stock_ptrs(0xB2D6) + b"".join(word(0xBCC0 + 8 * i) for i in range(16))
    long_txt = b"".join(f"TEAM {t + 1}".encode()[:7].ljust(7) + b"\xff" for t in range(16, 32))
    short_ptr = stock_ptrs(0x9280) + b"".join(word(0xBD80 + 12 * i) for i in range(16))
    short_txt = b"".join(b"\x00" + f"T{t + 1}".encode().ljust(10)[:10] + b"\xff" for t in range(16, 32))
    return long_ptr + long_txt + short_ptr + short_txt


def hook_code():
    # XOR $30 selects descriptor 2 instead of 1 without changing the font flags.
    lines = [
        "hud:", "CMP #$10", "AND #$0F", "ORA #$50", "BCC hud_low", "EOR #$30",
        "hud_low:", "JMP $C9AC",
        "box:", "CMP #$10", "AND #$0F", "ORA #$90", "BCC box_low", "EOR #$30",
        "box_low:", "JMP $CA33",
    ]
    return assemble(lines, HUD_HOOK)


def change_manifest(base, teams):
    high = teams[16:]
    def stock_ptrs(table):
        start = off(1, table)
        return base[start:start + 32]

    if any(base[off(1, 0x9180 + 16 * i):off(1, 0x9180 + 16 * i) + 16] != full_record(teams[i]["name"])
           for i in range(16)):
        raise ValueError("teams32.json low names differ from the stock full-name table")
    if bytes(narrow_flag(t["name"]) for t in teams[:16]) != STOCK_FLAGS:
        raise ValueError("narrow rule does not reproduce the stock $C998 flags")

    shorts, placed, cursor = {}, [], {r: r[0] for r in SHORT_REGIONS}
    for t in high:
        entry = short_entry(t["name"])
        for region in SHORT_REGIONS:
            if cursor[region] + len(entry) <= region[1]:
                shorts[t["id"]] = cursor[region]
                placed.append((cursor[region], entry))
                cursor[region] += len(entry)
                break
        else:
            raise ValueError("short names exceed bank1 capacity")

    long_ptr = stock_ptrs(0xB2D6) + b"".join(word(HIGH_FULL + 16 * i) for i in range(16))
    full = b"".join(full_record(t["name"]) for t in high)
    codes = b"".join(code_record(t["code"]) for t in high)
    block = long_ptr + full + codes
    if len(block) != LEGACY[1] - LEGACY[0]:
        raise ValueError("full-name and code tables exceed their reservation")
    short_ptr = stock_ptrs(0x9280) + b"".join(word(shorts[t]) for t in range(16, 32))
    flags = STOCK_FLAGS + bytes(0x20 | narrow_flag(t["name"]) for t in high)
    hooks, labels = hook_code()

    changes = [
        Change(1, LEGACY[0], legacy_block(base), block),
        Change(1, SHORT_PTR, b"\xff" * 64, short_ptr),
        Change(15, 0xC966, word(0xBD40), word(SHORT_PTR)),
        Change(15, 0xC96B, word(0xBD41), word(SHORT_PTR + 1)),
        Change(15, 0xC9AA, word(0xC998), word(FLAGS32)),
        Change(15, 0xCA27, bytes.fromhex("80 92 80 92"), word(HIGH_CODES) + word(HIGH_FULL)),
        Change(15, 0xCA2D, bytes.fromhex("04 04"), bytes.fromhex("08 10")),
        Change(15, 0xCA31, bytes.fromhex("01 01"), bytes.fromhex("02 03")),
        Change(15, FLAGS32, b"\xff" * 32, flags),
        Change(4, HUD_HOOK, b"\xff" * len(hooks), hooks),
        Change(4, 0xB11A, bytes.fromhex("09 50 20 ac c9"), b"\x20" + word(labels["hud"]) + b"\xea\xea"),
        Change(4, 0xB127, bytes.fromhex("09 50 20 ac c9"), b"\x20" + word(labels["hud"]) + b"\xea\xea"),
        Change(4, 0xB5B5, bytes.fromhex("09 90 4c 33 ca"), b"\x4c" + word(labels["box"]) + b"\xea\xea"),
    ]
    changes += [Change(1, addr, b"\xff" * len(entry), entry) for addr, entry in placed]
    return tuple(changes)


def build_rom(base, teams=None):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected password32 ROM size and iNES header")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned password32")
    teams = load_teams() if teams is None else validate_teams(teams)
    rom, claimed = bytearray(base), set()
    for c in change_manifest(base, teams):
        start = off(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        bank_end = off(c.bank, 0x10000 if c.bank == 15 else 0xC000)
        if (not c.after or len(c.before) != len(c.after) or claimed & span
                or start + len(c.after) > bank_end):
            raise ValueError(f"bank{c.bank} ${c.addr:04X}: overlapping or invalid change")
        if base[start:start + len(c.before)] != c.before:
            raise ValueError(f"bank{c.bank} ${c.addr:04X}: unexpected input bytes")
        claimed |= span
        rom[start:start + len(c.after)] = c.after
    return bytes(rom)


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    protected = [TEAMS, ROOT / "Little League Baseball - Championship Series (USA).nes"]
    protected.extend(directory / "password32.nes"
                     for directory in (ROOT / "build", source.resolve().parent))
    for path in protected:
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise ValueError(f"output aliases protected input {path}")
    if output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() in PROTECTED_SHA256:
        raise ValueError("output aliases protected input ROM artifact")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        base = args.rom.read_bytes()
        rom = build_rom(base)
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    diff = sum(a != b for a, b in zip(rom, base))
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
