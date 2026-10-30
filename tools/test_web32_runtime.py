#!/usr/bin/env python3
"""Run Preview 8's CPU readers on a ROM exported by the web editor.

    ROSTER_ROM32=build/homerunart32.nes .venv/bin/python -B tools/test_web32_runtime.py

tools/web32_export.mjs changes every editable field through web/rom.js: names,
batting, pitching, speed and skill for all 480 active players, plus all 128
live team ratings. This test checks that no other bit changed, then runs the
existing py65 roster-cache and role checks on both cache sides of all 32 teams
and executes both Power Analysis rating readers. It needs Node and py65, and
it reports SKIPPED without the source ROM.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

from test_cpu32 import Memory, call
from test_roles32 import test_cache, test_menu

TOOLS = Path(__file__).resolve().parent
SOURCE_SHA256 = "a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b"


def off(bank, cpu):
    return 16 + bank * 0x4000 + cpu - (0xC000 if bank == 15 else 0x8000)


def record(team, player):
    base = off(4, 0x8420 + 0x120 * team) if team < 16 else off(8, 0x8000 + 0x170 * team)
    return base + 16 * player


def check_export(source, edited):
    assert len(edited) == len(source)
    mask = bytearray(len(source))
    for team in range(32):
        for player in range(15):
            start = record(team, player)
            mask[start:start + 6] = b"\xff" * 6
            mask[start + 9], mask[start + 10], mask[start + 11] = 0xFF, 0x0F, 0xFF
        mask[off(3, 0xBC80 + 4 * team):off(3, 0xBC84 + 4 * team)] = b"\xff" * 4
    stray = [i for i, (a, b, m) in enumerate(zip(source, edited, mask)) if (a ^ b) & ~m & 0xFF]
    assert not stray, f"bits outside the editable fields changed at {[hex(i) for i in stray[:8]]}"
    for team in range(32):
        for player in range(15):
            start = record(team, player)
            skill = source[start + 11]
            assert edited[start:start + 6] == f"E{team:02d}P{player:02d}".encode()
            assert edited[start + 9] == source[start + 9] ^ 0xFF
            assert edited[start + 10] == source[start + 10] ^ 0x0F
            assert edited[start + 11] == (0 if skill == 7 else (skill + 1) % 5)
        ratings = off(3, 0xBC80 + 4 * team)
        assert list(edited[ratings:ratings + 4]) == [v % 4 + 1 for v in source[ratings:ratings + 4]]
    print("export: 480 active players and 128 live ratings changed; every other bit matches the source")


def check_high_cache(rom):
    for team in range(16, 32):
        memory = Memory()
        memory[0x8000:0xC000] = rom[off(8, 0x8000):off(8, 0xC000)]
        memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
        memory[2:4] = [0x00, 0x78]
        cpu = MPU(memory=memory)
        cpu.x = team
        call(cpu, 0xFC4A)
        for player in range(15):
            assert bytes(memory[0x7800 + 16 * player:0x7806 + 16 * player]) == f"E{team:02d}P{player:02d}".encode()
        stored = record(team, 0)
        assert bytes(memory[0x78F0:0x7920]) == rom[stored + 0x140:stored + 0x170], "trailer follows player 15"
    print("cache: edited names reach $7800 for teams 16-31; stored players 16-20 are skipped")


def check_ratings(rom):
    memory = Memory()
    memory[0x8000:0xC000] = rom[off(3, 0x8000):off(3, 0xC000)]
    cpu = MPU(memory=memory)
    assert memory[0xBD46:0xBD4B] == [0xB9, 0x80, 0xBC, 0xA8, 0xB9]
    digits = memory[0xBD4B] | memory[0xBD4C] << 8
    for team in range(32):
        expected = rom[off(3, 0xBC80 + 4 * team):off(3, 0xBC84 + 4 * team)]
        for rating in range(4):
            cpu.y = team * 4 + rating
            cpu.pc = 0xAFE2
            cpu.step()
            assert cpu.a == expected[rating], (team, rating)
        memory[0x04EF] = team
        memory.writes.clear()
        call(cpu, 0xBD30)
        writes = [value for address, value in memory.writes if address == 0x2007]
        assert writes == [memory[digits + value] for value in expected], (team, writes)
    print("ratings: all 128 $AFE2 reads and all 32 $BD30 numeral calls see the live table")


def main():
    path = os.environ.get("ROSTER_ROM32") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not path:
        print("SKIPPED: set ROSTER_ROM32 to the Preview 8 ROM (build/homerunart32.nes) to run this check")
        return
    source = Path(path).read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA256, f"{path} is not the accepted Preview 8 ROM"
    with tempfile.TemporaryDirectory() as scratch:
        output = Path(scratch) / "web-export.nes"
        subprocess.run(["node", str(TOOLS / "web32_export.mjs"), path, str(output)], check=True)
        edited = output.read_bytes()
    check_export(source, edited)
    for label, rom in (("original", source), ("web export", edited)):
        print(f"{label}:")
        test_cache(rom)
        test_menu(rom)
        check_ratings(rom)
    check_high_cache(edited)
    assert Path(path).read_bytes() == source, "the source ROM changed"
    print("source ROM unchanged; the edited export was written only to a temporary directory")


if __name__ == "__main__":
    main()
