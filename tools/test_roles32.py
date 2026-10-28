#!/usr/bin/env python3
"""Execute runtime role classification and preserve CPU substitution decisions."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

from build_roles32 import BASE_SHA256, ROOT, build_rom, off
from test_cpu32 import Memory, call, context, runtime_flags, test_fresh_pitchers

OUTPUT_SHA256 = "ddb83443653af408926d98843709e7831fed8fabd40f5e762db655c9a868431b"


def test_cache(rom):
    for team, side in itertools.product(range(32), range(2)):
        memory = Memory()
        memory[0x8000:0xC000] = rom[off(8, 0x8000):off(8, 0xC000)]
        memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
        destination = 0x7800 + side * 0x200
        memory[destination - 16:destination + 0x200] = [0xCA] * 0x210
        memory[2:4] = [destination & 255, destination >> 8]
        cpu = MPU(memory=memory)
        cpu.x = team
        memory.writes.clear()
        call(cpu, 0xFC4A)
        source = off(8, 0x8000 + team * 0x170)
        expected = bytearray(rom[source:source + 0xF0] + rom[source + 0x140:source + 0x170])
        writes = list(enumerate(expected[:0xF0], destination))
        for player in range(15):
            index = player * 16 + 8
            is_pitcher = bool(expected[player * 16 + 12]) if team >= 16 else player < 3
            expected[index] = (expected[index] & 0x7F) | (0x80 if is_pitcher else 0)
            writes.append((destination + index, expected[index]))
        writes += list(enumerate(expected[0xF0:], destination + 0xF0))
        assert bytes(memory[destination:destination + 0x120]) == expected, (team, side)
        assert [(a, v) for a, v in memory.writes if 0x6000 <= a < 0x8000] == writes
        assert len(writes) == 303 and len({a for a, v in writes}) == 288
        assert memory[destination - 16:destination] == [0xCA] * 16
        assert memory[destination + 0x120:destination + 0x200] == [0xCA] * 0xE0
        assert cpu.x == team
        memory[0x7F00 + team * 2:0x7F02 + team * 2] = [destination & 255, destination >> 8]
        call(cpu, 0xFF00)
        pointer = memory[0x7F00 + team * 2] | memory[0x7F01 + team * 2] << 8
        if team < 16:
            original = off(15, 0xFD40 + team * 2)
            assert pointer == int.from_bytes(rom[original:original + 2], "little")
            runtime = rom[off(4, pointer):off(4, pointer) + 0x120]
        else:
            assert pointer == destination
            runtime = expected
        memory[0x8000:0xC000] = rom[off(4, 0x8000):off(4, 0xC000)]
        memory[0x04EF + side] = team
        memory[0x0749 + side] = 0
        cpu.x = side
        call(cpu, 0xAB22)
        for player in range(15):
            assert memory[0x071A + player * 2 + side] == runtime[player * 16 + 8]
            selector = runtime[player * 16 + 12]
            stamina = runtime[0x101 + selector] & 15
            assert memory[0x07B1 + player * 2 + side] == memory[0xAD2B + stamina]
            assert memory[0x07CF + player * 2 + side] == 0
    print("cache: all32/both slots, 303 writes to 288 addresses, canaries, low pointers and AB22 state OK")


def test_menu(rom):
    for team in range(16, 32):
        flags = runtime_flags(rom, team)
        for side, player in itertools.product(range(2), range(15)):
            memory = Memory()
            memory[0x8000:0xC000] = rom[off(1, 0x8000):off(1, 0xC000)]
            memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
            memory[0xC4], memory[0xB1], memory[0xBD] = 0, 0, side
            memory[0x06E2 + side] = player << 4 | 8
            memory[0x071A + player * 2 + side] = flags[player]
            cpu = MPU(memory=memory)
            call(cpu, 0xA10C)
            selector = rom[off(8, 0x8000 + team * 0x170 + player * 16 + 12)]
            expected = 0 if selector else 2
            assert memory[0xB4] == expected, (team, side, player, memory[0xB4])
            memory[0xC0] = player
            cpu.pc = 0xA1CD
            for _ in range(20):
                if cpu.pc == 0xA1E0:
                    break
                cpu.step()
            assert cpu.pc == 0xA1E0 and memory[0xB6] == expected
    print("menu: all480 high-team player/side cases classify declared pitchers through bank1 A125 and A1D3 OK")


def test_substitutions(rom, base, roster):
    queued = 0
    for team, side, row, entry, used in itertools.product(
            range(32), range(2), range(9), (0xA576, 0xA630), (0, 3)):
        machines = []
        for artifact in (base, rom):
            cpu = context(artifact, roster, team, side)
            memory = cpu.memory
            memory[0x04ED], memory[0x04EE] = side, side ^ 1
            memory[0x048A] = 6
            memory[0x048B:0x048D] = [0, 0]
            memory[0x0515], memory[0x04B7] = row, 2
            memory[0x055E:0x0562] = [0xFF] * 4
            memory[0x055F], memory[0x06AF] = 0, row * 2
            for player in range(9, 15):
                memory[0x071A + player * 2 + side] |= used
            memory.writes.clear()
            call(cpu, entry)
            machines.append(cpu)
        old, current = machines
        assert (old.a, old.x, old.y, old.p, old.sp) == (
            current.a, current.x, current.y, current.p, current.sp)
        assert old.memory.writes == current.memory.writes, (team, side, row, entry, used)
        old_ram, new_ram = list(old.memory[:0x800]), list(current.memory[:0x800])
        if team >= 16:
            for address in range(0x071A, 0x0738):
                old_ram[address] &= 0x7F
                new_ram[address] &= 0x7F
        assert old_ram == new_ram, (team, side, row, entry, used)
        if current.memory[0x0522]:
            assert 9 <= current.memory[0x0525] < 15 and not used
            queued += 1
    assert queued > 0
    print(f"pinch run/hit: 2304 cases preserve decisions, exact writes/registers and low RAM; {queued} valid bench queues OK")


def test_builder(base, rom):
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256
    mutable = bytearray(base)
    assert build_rom(mutable) == rom and mutable == base
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert len(base) == len(rom) and len(changed) == 58
    assert changed <= set(range(off(15, 0xFB90), off(15, 0xFBE3)))
    for address in (0, 4, off(8, 0x970C), off(15, 0xFB90), off(15, 0xFBE2), 0x50000):
        damaged = bytearray(base)
        damaged[address] ^= 1
        try:
            build_rom(damaged)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted altered input")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "teamtables32.nes"
        source.write_bytes(base)
        symlink = directory / "symlink.nes"
        symlink.symlink_to(source)
        hardlink = directory / "hardlink.nes"
        os.link(source, hardlink)
        copied = directory / "copy.nes"
        copied.write_bytes(base)
        script = Path(__file__).with_name("build_roles32.py")
        command = [sys.executable, str(script), str(source), "-o"]
        for output in (source, symlink, hardlink, copied):
            result = subprocess.run(command + [str(output)], capture_output=True, text=True)
            assert result.returncode != 0 and "protected input" in result.stderr
            assert source.read_bytes() == base
        output = directory / "roles32.nes"
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom, result.stderr
    print("builder: pinned output, only58 helper bytes changed, immutable input and alias guards OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("--candidate", type=Path)
    args = ap.parse_args()
    base = args.rom.read_bytes()
    assert hashlib.sha256(base).hexdigest() == BASE_SHA256
    rom = build_rom(base)
    if args.candidate:
        assert args.candidate.read_bytes() == rom
    try:
        test_menu(base)
    except AssertionError as exc:
        print(f"old flag negative control rejected menu classification: {exc}")
    else:
        raise AssertionError("old flags unexpectedly classify all players correctly")
    test_cache(rom)
    test_menu(rom)
    roster = json.loads((ROOT / "data/roster32.json").read_text())
    test_fresh_pitchers(rom, roster)
    test_substitutions(rom, base, roster)
    test_builder(base, rom)
    print(f"roles32 passed: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
