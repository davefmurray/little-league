#!/usr/bin/env python3
"""Repair CPU pitching tables and the runtime roster view.

    .venv/bin/python tools/build_cpu32.py build/gameplay32.nes -o build/cpu32.nes

"""
import argparse
import hashlib
import json
from pathlib import Path

from build_bank11 import assemble

ROOT = Path(__file__).resolve().parent.parent
HEADER = bytes.fromhex("4E45531A101010000000000000000000")
BANK = 0x4000
ROM_SIZE = len(HEADER) + 16 * BANK + 16 * 0x2000
BASE_SHA256 = "deff2f62ab1dff112726846d12aed08b3d6e7fdbb39b7e5ae1d8fbca4b0a1b89"
PROTECTED_SHA256 = {
    BASE_SHA256,
    "3ce7b8d849d46b7b0e4582750221237875f1db86a3388039b75a6d017aa76317",
    "d043ecdfc46c4d50c509db30f757425759a556dec3258be462fa9b3d81091ec1",
    "bf86fffd907718f72478733be63c5e3938446488205dbcee0a33b1138c28ea4c",
}
MANAGERS = 0xBC80
RELIEVERS = MANAGERS + 32
HIGH_TEAM_MANAGER_STYLE = 1
SPECIALISTS = (0, 1, 2)
RUNTIME_PLAYERS = 15
STORED_PLAYERS = 20
PLAYER_BYTES = 16
TRAILER_BYTES = 48
FLAG_OFFSET = 8
RUNTIME_PLAYER_BYTES = RUNTIME_PLAYERS * PLAYER_BYTES
STORED_PLAYER_BYTES = STORED_PLAYERS * PLAYER_BYTES
ORIGINAL_HIGH_LINEUP = bytes.fromhex("08 16 29 31 42 57 65 73 84")
STARTER_HIGH_LINEUP = bytes.fromhex("01 16 29 38 42 57 65 73 84")
STOCK_MANAGERS = bytes.fromhex("01 02 01 00 02 00 01 01 01 02 02 01 01 02 02 02")
STOCK_RELIEVERS = bytes.fromhex(
    "09 07 09 0A 0D 0E 09 0A 09 0E 09 0A 09 0A 09 0A "
    "09 0A 09 0A 09 0A 09 0A 09 0A 09 0A 09 0A 09 0A")


CACHE_ASM = [
    "LDA $FC80,X", "STA $00", "LDA $FCA0,X", "STA $01", "LDY #$00",
    "players:", "LDA ($00),Y", "STA ($02),Y", "INY",
    f"CPY #${RUNTIME_PLAYER_BYTES:02X}", "BNE players",
] + [
    instruction for player in SPECIALISTS
    for instruction in (f"LDY #${player * PLAYER_BYTES + FLAG_OFFSET:02X}",
                        "LDA ($02),Y", "ORA #$80", "STA ($02),Y")
] + [
    "CLC", "LDA $00", f"ADC #${STORED_PLAYER_BYTES & 255:02X}", "STA $00",
    "LDA $01", f"ADC #${STORED_PLAYER_BYTES >> 8:02X}", "STA $01",
    "CLC", "LDA $02", f"ADC #${RUNTIME_PLAYER_BYTES:02X}", "STA $02",
    "LDA $03", "ADC #$00", "STA $03",
    "LDY #$00",
    "trailer:", "LDA ($00),Y", "STA ($02),Y", "INY",
    f"CPY #${TRAILER_BYTES:02X}", "BNE trailer", "RTS",
]


def off(bank, addr):
    return len(HEADER) + bank * BANK + addr - (0xC000 if bank == 15 else 0x8000)


def pitching_tables(base, roster):
    teams = roster.get("teams", [])
    if len(teams) != 32 or [team.get("id") for team in teams] != list(range(32)):
        raise ValueError("roster must contain teams 0..31 in order")
    managers = STOCK_MANAGERS + bytes([HIGH_TEAM_MANAGER_STYLE] * 16)
    relievers = bytearray(STOCK_RELIEVERS)
    for team in range(16, 32):
        players = teams[team].get("players", [])
        if len(players) != 20:
            raise ValueError(f"team {team}: expected 20 roster players")
        for player, record in enumerate(players):
            attrs = record.get("attrs", [])
            name = record.get("name", "")
            if (len(attrs) != 10 or not isinstance(name, str)
                    or not all(type(value) is int and 0 <= value <= 255 for value in attrs)):
                raise ValueError(f"team {team} player {player}: invalid roster record")
            expected = name.upper()[:6].ljust(6).encode("ascii") + bytes(attrs)
            start = off(8, 0x8000 + team * 0x170 + player * 16)
            if base[start:start + 16] != expected:
                raise ValueError(f"team {team} player {player}: roster differs from ROM")
            if attrs[6] not in (0, 8, 16, 24):
                raise ValueError(f"team {team} player {player}: invalid pitcher selector")
        start = off(15, 0xFD80 + team * 9)
        lineup = base[start:start + 9]
        active = {value >> 4 for value in lineup}
        if (len(active) != 9 or any(player >= 15 for player in active)
                or {value & 15 for value in lineup} != set(range(1, 10))):
            raise ValueError(f"team {team}: invalid nine-player lineup")
        pitcher = next(value >> 4 for value in lineup if value & 15 == 1)
        pair = [player for player in range(RUNTIME_PLAYERS)
                if players[player]["attrs"][6] in (16, 24) and player != pitcher]
        if pair != [1, 2]:
            raise ValueError(f"team {team}: expected relief specialists 1 and 2")
        relievers.extend(pair)
    return managers, bytes(relievers)


def build_rom(base, roster):
    if len(base) != ROM_SIZE:
        raise ValueError(f"expected {ROM_SIZE} bytes, got {len(base)}")
    if base[:len(HEADER)] != HEADER:
        raise ValueError("expected gameplay32 iNES header, 16 PRG banks and 16 CHR banks")
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned gameplay32")
    for addr, expected in ((0xA35A, STOCK_MANAGERS), (0xA3C2, STOCK_RELIEVERS),
                           (MANAGERS, b"\xff" * (0xC000 - MANAGERS))):
        start = off(5, addr)
        if base[start:start + len(expected)] != expected:
            raise ValueError(f"bank 5 ${addr:04X}: unexpected table or occupied padding")
    rom = bytearray(base)
    for team in range(16, 32):
        start = off(15, 0xFD80 + team * 9)
        if base[start:start + 9] != ORIGINAL_HIGH_LINEUP:
            raise ValueError(f"team {team}: unexpected starter lineup")
        rom[start:start + 9] = STARTER_HIGH_LINEUP
    managers, relievers = pitching_tables(rom, roster)
    for team in range(16, 32):
        players = roster["teams"][team]["players"]
        if [players[player]["attrs"][6] for player in range(3)] != [8, 16, 24]:
            raise ValueError(f"team {team}: players 0/1/2 must select P1/P2/P3")
    if len(managers) != 32 or len(relievers) != 64:
        raise ValueError("pitching tables must have 32 styles and 32 player pairs")
    changes = [
        (0xA40D, bytes.fromhex("B9 5A A3"), bytes([0xB9, MANAGERS & 255, MANAGERS >> 8])),
        (0xA4A4, bytes.fromhex("B9 C2 A3"), bytes([0xB9, RELIEVERS & 255, RELIEVERS >> 8])),
        (MANAGERS, b"\xff" * 32, managers),
        (RELIEVERS, b"\xff" * 64, relievers),
    ]
    for addr, expected, replacement in changes:
        start = off(5, addr)
        if base[start:start + len(expected)] != expected or len(expected) != len(replacement):
            raise ValueError(f"bank 5 ${addr:04X}: reader or reservation differs")
    for addr, expected, replacement in changes:
        start = off(5, addr)
        rom[start:start + len(expected)] = replacement
    cache, _ = assemble(CACHE_ASM, 0xFB90)
    if len(cache) != 83:
        raise ValueError("runtime cache helper does not fit its reservation")
    for addr, expected, replacement in (
        (0xFC4A, bytes.fromhex("BD 80 FC"), bytes.fromhex("4C 90 FB")),
        (0xFB90, b"\xff" * 83, cache),
    ):
        start = off(15, addr)
        if base[start:start + len(expected)] != expected:
            raise ValueError(f"fixed ${addr:04X}: cache entry or reservation differs")
        rom[start:start + len(expected)] = replacement
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned gameplay32.nes")
    ap.add_argument("--roster", type=Path, default=ROOT / "data/roster32.json")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    protected = [args.rom, args.roster]
    for directory in (ROOT / "build", args.rom.resolve().parent):
        protected.extend(directory / name for name in
                         ("direct31.nes", "direct31-pair36.nes", "gameplay32.nes"))
    for path in protected:
        if (args.out.resolve() == path.resolve()
                or (args.out.exists() and path.exists() and args.out.samefile(path))):
            ap.error(f"output aliases protected input {path}")
    if (args.out.is_file()
            and hashlib.sha256(args.out.read_bytes()).hexdigest() in PROTECTED_SHA256):
        ap.error("output aliases protected input ROM artifact")
    try:
        rom = build_rom(args.rom.read_bytes(), json.loads(args.roster.read_text()))
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    args.out.write_bytes(rom)
    print(f"wrote {args.out}: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
