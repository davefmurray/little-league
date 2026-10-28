#!/usr/bin/env python3
"""Execute the CPU pitching-table repair and its old-ROM negative controls.

    .venv/bin/python tools/test_cpu32.py build/gameplay32.nes --candidate build/cpu32.nes
"""
import argparse
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from functools import lru_cache

from py65.devices.mpu6502 import MPU

from build_cpu32 import BASE_SHA256, MANAGERS, RELIEVERS, ROOT, build_rom, off

STYLES = [1, 2, 1, 0, 2, 0, 1, 1, 1, 2, 2, 1, 1, 2, 2, 2] + [1] * 16
PAIRS = [(9, 7), (9, 10), (13, 14), (9, 10), (9, 14)] + [(9, 10)] * 11 + [(1, 2)] * 16
POINTERS = [0xA372, 0xA382, 0xA392, 0xA3A2]


class Memory(list):
    def __init__(self):
        super().__init__([0] * 0x10000)
        self.writes = []

    def __setitem__(self, addr, value):
        super().__setitem__(addr, value)
        if isinstance(addr, int):
            self.writes.append((addr, value))


@lru_cache(maxsize=128)
def runtime_flags(rom, team):
    if team < 16:
        pointer = int.from_bytes(rom[off(15, 0xFD40 + team * 2):off(15, 0xFD42 + team * 2)], "little")
        start = off(4, pointer)
        return tuple(rom[start + player * 16 + 8] for player in range(15))
    memory = Memory()
    memory[0x8000:0xC000] = rom[off(8, 0x8000):off(8, 0xC000)]
    memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
    memory[2:4] = [0, 0x78]
    cpu = MPU(memory=memory)
    cpu.x = team
    call(cpu, 0xFC4A)
    return tuple(memory[0x7808 + player * 16] for player in range(15))


def context(rom, roster, team, side, count=0):
    memory = Memory()
    memory[0x8000:0xC000] = rom[off(5, 0x8000):off(5, 0xC000)]
    memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
    memory[0x06D0:0x071A] = [(addr * 13 + side) & 255 for addr in range(0x06D0, 0x071A)]
    opponent = (team + 13) % (16 if team < 16 else 32)
    for selected_side, selected_team in ((side, team), (side ^ 1, opponent)):
        memory[0x04EF + selected_side] = selected_team
        start = off(15, 0xFD80 + selected_team * 9)
        lineup = rom[start:start + 9]
        memory[0x06E2 + selected_side:0x06F4:2] = lineup
        memory[0x04FD + selected_side] = next(value >> 4 for value in lineup if value & 15 == 1)
        for player in range(15):
            memory[0x071A + player * 2 + selected_side] = (
                runtime_flags(rom, selected_team)[player])
    memory[0x04EE] = side
    memory[0x04ED] = side ^ 1
    memory[0x04EB + side] = 0x80
    memory[0x048A] = side ^ 1
    memory[0x048B:0x048D] = [0, 0]
    memory[0x0522:0x0527] = [0, 0xCC, 0xCC, 0xCC, 0xCC]
    memory[0x0528] = 0x20
    memory[0x052D + side] = count
    memory[0x052D + (side ^ 1)] = 3
    pitcher = memory[0x04FD + side]
    memory[0x0775 + pitcher * 2 + side] = 0x7C
    memory[0x0793 + pitcher * 2 + side] = 0x20
    memory[0x04FB + side] = 0
    memory[0x04FF + side] = 0x80
    memory.writes.clear()
    return MPU(memory=memory)


def run(cpu, stop=0x0200):
    trace = []
    for _ in range(3000):
        if cpu.pc == stop:
            return trace
        trace.append(cpu.pc)
        cpu.step()
    raise AssertionError(f"CPU did not reach ${stop:04X}, PC=${cpu.pc:04X}, SP=${cpu.sp:02X}")


def call(cpu, entry=0xA3F6):
    before = cpu.sp
    cpu.stPushWord(0x01FF)
    cpu.pc = entry
    trace = run(cpu)
    assert cpu.sp == before, (hex(entry), cpu.sp, before)
    return trace


def test_managers(rom, base, roster):
    for team, side, count, winning in itertools.product(range(32), range(2), range(2), range(2)):
        cpu = context(rom, roster, team, side, count)
        memory = cpu.memory
        memory[0x048B + side] = 4 if winning else 0
        memory[0x048B + (side ^ 1)] = 0 if winning else 4
        cpu.stPushWord(0x01FF)
        cpu.pc = 0xA3F6
        run(cpu, 0xA410)
        assert cpu.a == STYLES[team], (team, side, "manager style", cpu.a)
        run(cpu, 0xA41C)
        pointer = memory[2] | memory[3] << 8
        assert pointer in POINTERS and pointer == POINTERS[STYLES[team]], (team, side, hex(pointer))
        run(cpu, 0xA44E)
        offset = count * 2 + (0 if winning else 8)
        start = off(5, pointer + offset)
        assert memory[0x10:0x12] == list(base[start:start + 2]), (team, side, offset)
        run(cpu)
        assert cpu.sp == 0xFF
    print("managers: 32 teams x 2 sides x 2 relief counts x leading/trailing, valid pointers and thresholds OK")


def test_reliever_reads(rom, roster):
    for team, side, count in itertools.product(range(32), range(2), range(2)):
        cpu = context(rom, roster, team, side, count)
        cpu.pc = 0xA48D
        run(cpu, 0xA4AD)
        selected = cpu.memory[0x0525]
        assert 0 <= selected < 15, (team, side, count, "invalid player", selected)
        assert selected == cpu.memory[0x0526] == PAIRS[team][count], (team, side, count, selected)
    print("relievers: 32 teams x 2 sides x 2 selections, player IDs 0..14 and stock choices OK")


def test_threshold_boundaries(rom, base, roster):
    for team, side, count, winning in itertools.product(range(32), range(2), range(2), range(2)):
        offset = count * 2 + (0 if winning else 8)
        start = off(5, POINTERS[STYLES[team]] + offset)
        runs_limit, work_limit = base[start:start + 2]
        for work_ok, runs_ok, exhausted, occupied in itertools.product(range(2), repeat=4):
            cpu = context(rom, roster, team, side, count)
            memory = cpu.memory
            pitcher = memory[0x04FD + side]
            index = pitcher * 2 + side
            memory[0x071A + index] |= 0x80
            memory[0x048B + side] = 4 if winning else 0
            memory[0x048B + (side ^ 1)] = 0 if winning else 4
            memory[0x0775 + index] = (work_limit - 1 + work_ok - exhausted) * 4
            memory[0x0793 + index] = runs_limit - 1 + runs_ok - occupied
            memory[0x04FB + side] = 0 if exhausted else 1
            memory[0x04FF + side] = 0x80
            memory[0x04B7] = 0x0C if occupied else 0
            before = memory[0x06D0:0x071A]
            trace = call(cpu)
            queued = bool(memory[0x0522])
            assert queued == bool(work_ok and runs_ok), (team, side, count, winning,
                                                        work_ok, runs_ok, exhausted, occupied)
            assert (0xA4A4 in trace) == queued
            assert memory[0x06D0:0x071A] == before
    print("threshold decisions: all teams/sides, exact boundaries, stamina increment and occupied-base increment OK")


def queue_case(rom, roster, team, side, count, used):
    cpu = context(rom, roster, team, side, count)
    memory = cpu.memory
    for player, status in zip(PAIRS[team], used):
        index = 0x071A + player * 2 + side
        memory[index] = (memory[index] & 0xFC) | status
    before = memory[0x06D0:0x071A]
    flags = memory[0x071A:0x0738]
    memory.writes.clear()
    trace = call(cpu)
    assert memory[0x06D0:0x071A] == before, (team, side, "lineup or score write")
    selected_slot = next((slot for slot in range(count, 2) if not used[slot]), None)
    if selected_slot is None:
        assert memory[0x0522] == 0 and memory[0x0528] == 0x20, (team, side, count, used)
        assert memory[0x052D + side] == max(count, 2)
        assert memory[0x071A:0x0738] == flags
    else:
        selected = PAIRS[team][selected_slot]
        assert 0 <= memory[0x0525] < 15, (team, side, count, used, memory[0x0525])
        assert 0 <= memory[0x0526] < 15 and memory[0x0526] == selected
        assert memory[0x0524] == memory[0x04FD + side]
        active = {value >> 4 for value in before[0x12 + side:0x24:2]}
        mode = memory[0x0523]
        assert mode in (2, 3, 0x83), (team, side, count, used, mode)
        if mode == 0x83:
            assert selected not in active and memory[0x0525] in active
            flags[memory[0x0525] * 2 + side] &= 0xFB
        else:
            assert memory[0x0525] == selected
            assert mode == (3 if selected in active else 2)
        assert memory[0x0522] == 1 and memory[0x0528] == 0x24
        assert memory[0x052D + side] == selected_slot + 1
        flags[memory[0x04FD + side] * 2 + side] &= 0xFB
        assert memory[0x071A:0x0738] == flags
        assert 0xA6D5 in trace and 0xA563 in trace
        if team >= 16:
            assert mode == 3 and selected in active
            assert roster["teams"][team]["players"][selected]["attrs"][6] in (16, 24)
    assert memory[0x052D + (side ^ 1)] == 3
    return cpu, trace


def test_queues(rom, base, roster):
    for team, side, count in itertools.product(range(32), range(2), range(4)):
        for used in itertools.product(range(4), repeat=2):
            cpu, trace = queue_case(rom, roster, team, side, count, used)
            if team < 16:
                old, old_trace = queue_case(base, roster, team, side, count, used)
                assert cpu.memory[:0x800] == old.memory[:0x800], (team, side, count, used)
                assert cpu.memory.writes == old.memory.writes
                assert (cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp) == (old.a, old.x, old.y, old.p, old.sp)
                assert trace == old_trace
    print("queues: 32 teams x 2 sides x counts 0..3 x all 16 used-status pairs, bounded returns and valid queues OK")
    print("stock parity: teams 0..15 have identical RAM, registers, writes and instruction traces on every queue case")


def test_early_returns(rom, roster):
    for team, side in itertools.product(range(32), range(2)):
        for guard in ("already queued", "human"):
            cpu = context(rom, roster, team, side)
            cpu.memory[0x0528 if guard == "already queued" else 0x04EB + side] = (
                4 if guard == "already queued" else 0)
            before = cpu.memory[0x0400:0x0800]
            trace = call(cpu)
            assert cpu.memory[0x0400:0x0800] == before
            assert 0xA40D not in trace
    print("entry guards: already-queued and human-controlled teams return without substitutions OK")


def test_fresh_pitchers(rom, roster):
    for team, side in itertools.product(range(32), range(2)):
        pitchers = range(3) if team >= 16 else [context(rom, roster, team, side).memory[0x04FD + side]]
        for player in pitchers:
            cpu = context(rom, roster, team, side)
            memory = cpu.memory
            memory[0x04FD + side] = player
            memory[0x0775 + player * 2 + side] = 0
            memory[0x0793 + player * 2 + side] = 0
            memory[0x04FB + side] = 1
            memory[0x04FF + side] = 0
            trace = call(cpu)
            assert 0xA461 in trace, (team, side, player, "skipped fatigue checks")
            assert memory[0x0522] == 0, (team, side, player, "fresh pitcher relieved")
    print("fresh pitchers: all starters and high-team P1/P2/P3 retain fatigue checks and are not immediately relieved OK")


def test_active_pitcher_swaps(rom, roster):
    for team, side, count in itertools.product(range(16, 32), range(2), range(2)):
        cpu, _ = queue_case(rom, roster, team, side, count, (0, 0))
        memory = cpu.memory
        current, selected = memory[0x0524:0x0526]
        memory[0x8000:0xC000] = rom[off(4, 0x8000):off(4, 0xC000)]
        memory[0x0490:0x0492] = [current, selected]
        memory[0x048F] = 0
        before = memory[0x06D0:0x071A]
        expected = before[:]
        current_slot = next(slot for slot in range(9)
                            if before[0x12 + side + slot * 2] >> 4 == current)
        selected_slot = next(slot for slot in range(9)
                             if before[0x12 + side + slot * 2] >> 4 == selected)
        first = 0x12 + side + current_slot * 2
        second = 0x12 + side + selected_slot * 2
        expected[first] = (before[first] & 0xF0) | (before[second] & 15)
        expected[second] = (before[second] & 0xF0) | (before[first] & 15)
        memory.writes.clear()
        trace = call(cpu, 0xABF4)
        assert 0xAC0A in trace and 0xAC1C in trace
        assert memory[0x06D0:0x071A] == expected, (team, side, count)
        assert len([(addr, value) for addr, value in memory.writes
                    if 0x06D0 <= addr < 0x071A]) == 2
        assert memory[0x06E2 + side + selected_slot * 2] == (selected << 4) | 1
    print("active relief specialists: stock $ABF4 swaps players 1/2 into pitching on both sides using only 18 lineup bytes OK")


def test_negative_controls(base, roster):
    checks = [
        ("manager styles/pointers", lambda: test_managers(base, base, roster)),
        ("relief-player IDs", lambda: test_reliever_reads(base, roster)),
        ("full CPU substitution queue", lambda: queue_case(base, roster, 16, 0, 0, (0, 0))),
    ]
    for name, check in checks:
        try:
            check()
        except AssertionError as exc:
            print(f"old-ROM negative control rejected {name}: {exc}")
        else:
            raise AssertionError(f"old-ROM negative control unexpectedly passed {name}")


def test_runtime_cache(rom):
    for team, side in itertools.product(list(range(16, 32)) + list(range(16)), range(2)):
        memory = Memory()
        memory[0x8000:0xC000] = rom[off(8, 0x8000):off(8, 0xC000)]
        memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
        destination = 0x7800 + side * 0x200
        source = off(8, 0x8000 + team * 0x170)
        expected = bytearray(rom[source:source + 0xF0] + rom[source + 0x140:source + 0x170])
        for player in range(3):
            expected[player * 16 + 8] |= 0x80
        memory[destination - 16:destination + 0x200] = [0xCA] * 0x210
        memory[2:4] = [destination & 255, destination >> 8]
        cpu = MPU(memory=memory)
        cpu.x = team
        memory.writes.clear()
        call(cpu, 0xFC4A)
        assert bytes(memory[destination:destination + 0x120]) == expected, (team, side)
        expected_writes = list(enumerate(rom[source:source + 0xF0], destination))
        expected_writes += [(destination + player * 16 + 8, expected[player * 16 + 8]) for player in range(3)]
        expected_writes += list(enumerate(expected[0xF0:], destination + 0xF0))
        assert [(addr, value) for addr, value in memory.writes if 0x6000 <= addr < 0x8000] == expected_writes
        assert memory[destination - 16:destination] == [0xCA] * 16
        assert memory[destination + 0x120:destination + 0x200] == [0xCA] * 0xE0
        assert cpu.x == team
        memory[0x7F00 + team * 2:0x7F02 + team * 2] = [destination & 255, destination >> 8]
        call(cpu, 0xFF00)
        base = memory[0x7F00 + team * 2] | memory[0x7F01 + team * 2] << 8
        if team < 16:
            original = off(15, 0xFD40 + team * 2)
            assert base == int.from_bytes(rom[original:original + 2], 'little')
            runtime = rom[off(4, base):off(4, base) + 0x120]
        else:
            assert base == destination
            runtime = expected
        memory[0x8000:0xC000] = rom[off(4, 0x8000):off(4, 0xC000)]
        memory[0x04EF + side] = team
        memory[0x04EE] = side
        memory[0x0749 + side] = 0
        cpu.x = side
        call(cpu, 0xAB22)
        for player in range(15):
            selector = runtime[player * 16 + 12]
            stamina = runtime[0x100 + selector + 1] & 15
            assert memory[0x071A + player * 2 + side] == runtime[player * 16 + 8]
            assert memory[0x07B1 + player * 2 + side] == memory[0xAD2B + stamina]
            assert memory[0x07CF + player * 2 + side] == 0
            if not selector:
                continue
            memory[0x04FD + side] = player
            call(cpu, 0xB094)
            pointer = memory[4] | memory[5] << 8
            assert pointer == base + 0x100 + selector, (team, side, player)
            assert bytes(memory[pointer:pointer + 8]) == runtime[0x100 + selector:0x108 + selector]
        cpu.x = side
        call(cpu, 0xAD42)
        memory[1] = side
        cpu.x = side
        call(cpu, 0xABB8)
        lineup = rom[off(15, 0xFD80 + team * 9):off(15, 0xFD80 + team * 9) + 9]
        starter = 0 if team >= 16 else next(value >> 4 for value in lineup if value & 15 == 1)
        assert memory[0x04FD + side] == starter, (team, side, "starting pitcher", memory[0x04FD + side])
        selector = runtime[starter * 16 + 12]
        if team >= 16:
            assert selector == 8, (team, "P1 selector", selector)
        record = runtime[0x100 + selector:0x108 + selector]
        assert memory[0x04FB + side] == memory[0xAD2B + (record[1] & 15)]
        assert memory[0x04FF + side] == 0
        assert memory[0x0534 + side] == record[6]
        assert memory[0x0536 + side] == record[7]
    print("runtime cache: all32 x both sides, bounded 15-player/trailer copy, low pointers, flags, stamina, pitcher records and actual starter initialization OK")


def test_builder(base, rom, roster):
    assert build_rom(base, roster) == rom
    assert hashlib.sha256(rom).hexdigest() == "338c1cc9bf80f6b77f441b472e91fd7536223d0b1b129fc8b7307ccb6f006327"
    mutable = bytearray(base)
    assert build_rom(mutable, roster) == rom and mutable == base
    expected = {off(5, addr) for addr in (0xA40E, 0xA40F, 0xA4A5, 0xA4A6)}
    expected.update(range(off(5, MANAGERS), off(5, RELIEVERS + 64)))
    expected.update(range(off(15, 0xFB90), off(15, 0xFBE3)))
    expected.update(range(off(15, 0xFC4A), off(15, 0xFC4D)))
    expected.update(off(15, 0xFD80 + team * 9 + row)
                    for team in range(16, 32) for row in (0, 3))
    assert len(rom) == len(base)
    assert {i for i, (old, new) in enumerate(zip(base, rom)) if old != new} == expected
    assert rom[off(5, MANAGERS):off(5, MANAGERS + 16)] == base[off(5, 0xA35A):off(5, 0xA36A)]
    assert rom[off(5, RELIEVERS):off(5, RELIEVERS + 32)] == base[off(5, 0xA3C2):off(5, 0xA3E2)]
    assert rom[off(5, 0xBC5F):off(5, 0xBC6F)] == base[off(5, 0xBC5F):off(5, 0xBC6F)]
    invalid = [base[:-1], base + b"\0", rom]
    for addr in (0, 4, 5, 6, off(5, 0xA40D), off(5, 0xA4A4), off(5, 0xA35A),
                 off(5, 0xA3C2), off(5, 0xBC61), off(5, 0xBFFF), 0x50000):
        damaged = bytearray(base)
        damaged[addr] ^= 1
        invalid.append(damaged)
    for damaged in invalid:
        try:
            build_rom(damaged, roster)
        except ValueError:
            pass
        else:
            raise AssertionError("builder accepted a mismatched ROM")
    for mutation in ("team order", "missing player", "roster attributes", "roster name"):
        damaged = copy.deepcopy(roster)
        if mutation == "team order":
            damaged["teams"].reverse()
        elif mutation == "missing player":
            damaged["teams"][16]["players"].pop()
        elif mutation == "roster attributes":
            damaged["teams"][16]["players"][9]["attrs"][6] = 16
        else:
            damaged["teams"][16]["players"][9]["name"] = "WRONG"
        try:
            build_rom(base, damaged)
        except ValueError:
            pass
        else:
            raise AssertionError(f"builder accepted {mutation}")
    script = Path(__file__).with_name("build_cpu32.py")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "gameplay32.nes"
        source.write_bytes(base)
        roster_path = directory / "roster.json"
        roster_path.write_text(json.dumps(roster))
        protected = [source, roster_path]
        for name in ("direct31.nes", "direct31-pair36.nes"):
            path = directory / name
            path.write_bytes(b"protected baseline")
            protected.append(path)
        aliases = protected[:]
        for target in protected:
            symlink = directory / (target.stem + "-symlink")
            symlink.symlink_to(target)
            hardlink = directory / (target.stem + "-hardlink")
            os.link(target, hardlink)
            aliases.extend((symlink, hardlink))
        elsewhere = directory / "elsewhere"
        elsewhere.mkdir()
        copied = elsewhere / "input-copy.nes"
        copied.write_bytes(base)
        aliases.extend((copied, directory / "missing" / ".." / "gameplay32.nes"))
        command = [sys.executable, str(script), str(source), "--roster", str(roster_path), "-o"]
        snapshots = [(path, path.read_bytes()) for path in protected]
        for output in aliases:
            result = subprocess.run(command + [str(output)], capture_output=True, text=True)
            assert result.returncode != 0 and "protected input" in result.stderr, result
            assert all(path.read_bytes() == contents for path, contents in snapshots)
        output = directory / "cpu32.nes"
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom, result.stderr
        source.write_bytes(invalid[-1])
        output.write_bytes(b"existing output")
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode != 0 and output.read_bytes() == b"existing output"
    print("builder: exactly 218 changed bytes, stock tables and old batting-bias reads preserved, mismatches and input aliases rejected OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned gameplay32.nes")
    ap.add_argument("--candidate", type=Path, help="verify and execute this built repair ROM")
    ap.add_argument("--roster", type=Path, default=ROOT / "data/roster32.json")
    args = ap.parse_args()
    base = args.rom.read_bytes()
    assert hashlib.sha256(base).hexdigest() == BASE_SHA256
    roster = json.loads(args.roster.read_text())
    built = build_rom(base, roster)
    rom = args.candidate.read_bytes() if args.candidate else built
    assert rom == built, "candidate differs from the guarded build"
    test_negative_controls(base, roster)
    test_managers(rom, base, roster)
    test_reliever_reads(rom, roster)
    test_threshold_boundaries(rom, base, roster)
    test_queues(rom, base, roster)
    test_early_returns(rom, roster)
    test_fresh_pitchers(rom, roster)
    random_flags = bytearray(rom)
    for address in range(off(15, 0xFB90), off(15, 0xFBE3) - 1):
        if rom[address:address + 2] == bytes.fromhex("09 80"):
            random_flags[address + 1] = 0
    try:
        test_fresh_pitchers(bytes(random_flags), roster)
    except AssertionError as exc:
        print(f"random-roster-flags negative control rejected fresh pitcher: {exc}")
    else:
        raise AssertionError("random pitcher flags unexpectedly pass fatigue checks")
    test_active_pitcher_swaps(rom, roster)
    try:
        test_runtime_cache(base)
    except AssertionError as exc:
        print(f"old-ROM negative control rejected runtime cache: {exc}")
    else:
        raise AssertionError("old runtime cache unexpectedly passed")
    test_runtime_cache(rom)
    cache_only = bytearray(rom)
    start = off(15, 0xFD80 + 16 * 9)
    cache_only[start:start + 16 * 9] = base[start:start + 16 * 9]
    try:
        test_runtime_cache(cache_only)
    except AssertionError as exc:
        print(f"cache-only negative control rejected starter lineup: {exc}")
    else:
        raise AssertionError("cache-only repair unexpectedly starts P1")
    test_builder(base, rom, roster)
    print(f"test_cpu32: OK {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
