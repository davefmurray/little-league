#!/usr/bin/env python3
"""Execute team-table repairs, stock parity, guards, and old-ROM failures in py65.

    .venv/bin/python tools/test_teamtables32.py build/cpu32.nes --candidate build/teamtables32.nes
"""
import argparse
import hashlib
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

from build_teamtables32 import BASE_SHA256, PROTECTED_NAMES, build_rom, change_manifest, off

OUTPUT_SHA256 = "775595bef3506de25f704fe0530f6833d8ce0541155110920e739f19425cd006"
STOCK_BONUSES = bytes.fromhex(
    "00 00 11 21 00 00 11 21 00 11 11 22 00 00 11 21 "
    "00 11 11 22 00 00 00 11 00 00 11 21 33 00 11 21 "
    "00 00 01 13 00 11 12 12 00 11 22 42 00 01 02 13 "
    "00 00 00 11 00 11 22 44 00 11 21 33 00 00 11 22")
STOCK_BIAS = (2, -1, -1, 0, -1, -2, -2, -2, -2, -2, -1, -2, -1, -1, -2, 0)
TIERS = (0,) * 8 + (1,) * 4 + (2, 2, 3, 3)
BATTING = ((0, 0xBD00), (1, 0xBF00), (3, 0xBD00), (5, 0xBD00))
MASKS = (0, 0xFFFF, 0x5555, 0xAAAA) + tuple(1 << bit for bit in range(16))
RAM = bytes((addr * 29 + 0x53) & 255 for addr in range(0x800))


class Memory(list):
    def __init__(self):
        super().__init__([0] * 0x10000)
        self.writes = []
        self.reads = []

    def __getitem__(self, addr):
        if isinstance(addr, int) and addr >= 0x8000:
            self.reads.append(addr)
        return super().__getitem__(addr)

    def __setitem__(self, addr, value):
        super().__setitem__(addr, value)
        if isinstance(addr, int):
            self.writes.append((addr, value))


def machine(rom, bank):
    memory = Memory()
    memory[0x8000:0xC000] = rom[off(bank, 0x8000):off(bank, 0xC000)]
    memory[0xC000:0x10000] = rom[off(15, 0xC000):off(15, 0x10000)]
    return MPU(memory=memory)


def reset(cpu):
    cpu.memory[:0x800] = RAM
    cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp = 0xA5, 0x5A, 0x6C, 0x61, 0xFF
    cpu.memory.writes.clear()
    cpu.memory.reads.clear()


def run(cpu, stop=0x0200):
    trace = []
    for _ in range(1500):
        if cpu.pc == stop:
            return trace
        trace.append(cpu.pc)
        cpu.step()
    raise AssertionError(f"did not reach ${stop:04X}, PC=${cpu.pc:04X}, SP=${cpu.sp:02X}")


def call(cpu, entry):
    before = cpu.sp
    cpu.stPushWord(0x01FF)
    cpu.pc = entry
    trace = run(cpu)
    assert cpu.sp == before, (hex(entry), cpu.sp, before)
    return trace


def parity(cpu, old, case):
    assert cpu.memory[:0x800] == old.memory[:0x800], (case, "RAM/stack parity")
    assert (cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp) == (old.a, old.x, old.y, old.p, old.sp), (
        case, "register/flag/stack parity")
    assert cpu.memory.writes == old.memory.writes, (case, "write parity")


def ownership(team, mask):
    return 0x80 if team >= 16 or mask & (1 << team) else 0


def bonus_case(cpu, team, side, counter):
    reset(cpu)
    other = (team + 7) % (16 if team < 16 else 32)
    cpu.memory[0x04EF:0x04F1] = [team if side == 0 else other, team if side == 1 else other]
    cpu.memory[0x0746] = counter
    cpu.memory[0x074B:0x0757] = [0xA5] * 12
    cpu.memory.writes.clear()
    call(cpu, 0xAA83)
    for selected in range(2):
        selected_team = cpu.memory[0x04EF + selected]
        packed = STOCK_BONUSES[selected_team * 4 + TIERS[counter]] if selected_team < 16 else 0
        assert cpu.memory[0x0747 + selected] == packed >> 4, (team, side, counter, "upper bonus")
        assert cpu.memory[0x0749 + selected] == packed & 15, (team, side, counter, "lower bonus")
    assert cpu.memory[0x0746] == counter
    assert cpu.memory[0x074B:0x0757] == [0xA5] * 12
    assert {addr for addr, _ in cpu.memory.writes if addr >= 0x200} == set(range(0x0747, 0x074B))


def test_bonuses(rom, base):
    cpu, old = machine(rom, 4), machine(base, 4)
    for team, side, counter in itertools.product(range(32), range(2), range(16)):
        bonus_case(cpu, team, side, counter)
        reads = [addr for addr in cpu.memory.reads if 0xB700 <= addr < 0xB800]
        teams = cpu.memory[0x04EF:0x04F1]
        assert reads == [0xB700 + selected * 4 + TIERS[counter] for selected in teams]
        assert not any(0xAABB <= addr < 0xAAFB for addr in cpu.memory.reads)
        if max(teams) < 16:
            bonus_case(old, team, side, counter)
            parity(cpu, old, (team, side, counter))
        for selected, entry in itertools.product(range(2), (0xADBC, 0xADC7)):
            boost = cpu.memory[(0x0749 if entry == 0xADBC else 0x0747) + selected]
            for value in range(16):
                cpu.a, cpu.x = value, selected
                cpu.p = 0x20 | (value & 1)
                call(cpu, entry)
                assert cpu.a == min(value + boost, 15), (team, side, counter, entry, value)
                assert cpu.x == selected
                if max(teams) < 16:
                    old.a, old.x, old.p = value, selected, 0x20 | (value & 1)
                    call(old, entry)
                    parity(cpu, old, (team, side, counter, entry, value))
    print("bonuses: 32 teams x 2 sides x 16 counters; both saturating helpers at every input 0..15; low-team RAM/register/flag/stack parity; bounded reads OK")


def batting_case(cpu, team, side, seed, speeds, runners, outs=0, strikes=0, balls=0, forced_rng=None):
    reset(cpu)
    memory = cpu.memory
    memory[0x04ED] = side
    memory[0x04EF:0x04F1] = [31 if side else team, team if side else 31]
    memory[0x0489], memory[0x0487], memory[0x0488] = outs, strikes, balls
    memory[0x04B7] = runners
    memory[0x0531:0x0533] = speeds
    memory[0x0547] = 0xA5
    memory[0x34] = seed
    original_rng = rng = memory[0xC4FA + ((seed + 1) & 63)]
    second = memory[0xC4FA + ((seed + 2) & 63)]
    if forced_rng is not None:
        memory[0xC4FA + ((seed + 1) & 63)] = forced_rng
        rng = forced_rng
    memory.writes.clear()
    memory.reads.clear()
    trace = call(cpu, 0xBB47)
    active = runners & 14
    early = outs >= 2 or strikes >= 2 or active == 0
    threshold = ((speeds[0] + speeds[1]) & 255) >> 1
    if active & 8 and not early:
        penalty = memory[0xBC03 + strikes * 4 + balls]
        threshold = (threshold - penalty) & 255
        if threshold & 0x80:
            threshold = 0
    bias = STOCK_BIAS[team] if team < 16 else 0
    adjusted = (rng + bias) & 255
    success = not adjusted & 0x80 and adjusted >= threshold
    result = 0 if early else (3 if active & 8 else 2) if success else int(active == 4 and second < 4)
    assert memory[0x0547] == result, (
        team, side, seed, speeds, runners, outs, strikes, balls, rng, threshold, adjusted, memory[0x0547], result)
    assert (0xBB90 in trace) == (not early)
    assert memory[0x34] == (seed if early else (seed + 1 + int(not success and active == 4)) & 255)
    allowed = {0x0547}
    if outs < 2 and strikes < 2:
        allowed.add(0)
    if not early:
        allowed.update((1, 0x34))
    assert all(addr in allowed or 0x100 <= addr < 0x200 for addr, _ in memory.writes), (
        team, side, seed, speeds, runners, outs, strikes, memory.writes)
    if forced_rng is not None:
        memory[0xC4FA + ((seed + 1) & 63)] = original_rng
    return trace


RNG = (7, 1, 6, 2, 7, 5, 3, 6, 4, 5, 3, 0, 0, 2, 4, 6,
       3, 6, 1, 1, 7, 4, 3, 5, 4, 6, 2, 4, 5, 1, 0, 0,
       0, 3, 7, 7, 2, 0, 3, 5, 4, 1, 3, 4, 1, 6, 2, 0,
       6, 6, 2, 1, 0, 2, 7, 5, 2, 4, 7, 3, 5, 1, 5, 0)


def test_batting(rom, base):
    count = 0
    for bank, table in BATTING:
        cpu, old = machine(rom, bank), machine(base, bank)
        assert tuple(cpu.memory[0xC4FA:0xC53A]) == RNG
        cases = itertools.chain(
            ((seed, (threshold, threshold), runners, 0, 0, 0, None)
             for seed, threshold, runners in itertools.product(range(64), range(9), (4, 8))),
            ((seed, speeds, runners, 0, strikes, balls, None)
             for seed, speeds, runners, strikes, balls in itertools.product(
                 (0, 10, 0xFF), ((1, 2), (15, 15), (127, 127), (128, 128), (255, 255)),
                 (2, 6, 10, 12, 14), range(2), range(4))),
            ((0, (2, 2), runners, 0, 0, 0, rng)
             for runners, rng in itertools.product((4, 8), (0, 1, 2, 0x7E, 0x7F, 0x80, 0xFE, 0xFF))),
            ((0xFF, (15, 15), runners, outs, strikes, 3, None)
             for runners, outs, strikes in itertools.product((0, 1, 2, 4, 8, 14), (0, 2, 255), (0, 2, 255))
             if outs >= 2 or strikes >= 2 or not runners & 14),
        )
        cases = tuple(cases)
        for team, side in itertools.product(range(32), range(2)):
            for seed, speeds, runners, outs, strikes, balls, forced in cases:
                case = (team, side, seed, speeds, runners, outs, strikes, balls, forced)
                trace = batting_case(cpu, *case)
                reads = [addr for addr in cpu.memory.reads if table <= addr < table + 256]
                assert reads == ([table + team] if 0xBB90 in trace else []), (bank, case, reads)
                assert not any(0xBC4F <= addr < 0xBC6F for addr in cpu.memory.reads), (bank, case)
                if team < 16:
                    batting_case(old, *case)
                    parity(cpu, old, (bank, case))
                count += 1
    print(f"batting: {count} cases across banks 0/1/3/5, all32/both sides, every RNG seed and threshold 0..8, signed edges, situational branches, early returns, low parity and bounded reads OK")


def ownership_case(cpu, team, side, mask, entry, flag=0x80):
    reset(cpu)
    memory = cpu.memory
    memory[0x04EF:0x04F1] = [31 if side else team, team if side else 31]
    memory[0x04EB:0x04ED] = [0x27, 0x35]
    memory[0x074B:0x074D] = [mask & 255, mask >> 8]
    if entry == 0x9F41:
        memory[0x04EB + side] = flag
    cpu.x = side
    cpu.p = (0x20, 0x61, 0xA2, 0xE1)[mask % 4]
    before = memory[:0x800]
    memory.writes.clear()
    memory.reads.clear()
    call(cpu, entry)
    expected = before[:]
    allowed = set()
    if entry == 0x9CB2:
        expected[0x04EB + side] = ownership(team, mask)
        allowed.add(0x04EB + side)
    elif flag & 0x80 and team < 16:
        updated = mask | (1 << team)
        expected[0x074B:0x074D] = [updated & 255, updated >> 8]
        allowed.add(0x074B + (team >= 8))
    if team < 16 and (entry == 0x9CB2 or flag & 0x80):
        expected[0] = 1 << (team & 7)
        allowed.add(0)
    assert memory[:0x100] == expected[:0x100] and memory[0x200:0x800] == expected[0x200:0x800], (
        team, side, mask, hex(entry), flag, "ownership state")
    assert all(addr in allowed or 0x100 <= addr < 0x200 for addr, _ in memory.writes), (
        team, side, mask, hex(entry), "unrelated write")
    if team >= 16:
        assert not any(0x9CD0 <= addr < 0x9D00 for addr in memory.reads), (team, "ownership alias read")
        assert not any(addr in (0x074B, 0x074C) for addr, _ in memory.writes)


def test_ownership(rom, base):
    cpu, old = machine(rom, 5), machine(base, 5)
    for team, side, mask in itertools.product(range(32), range(2), MASKS):
        for entry, flag in ((0x9CB2, 0x80), (0x9F41, 0), (0x9F41, 0x7F), (0x9F41, 0x80), (0x9F41, 0xFF)):
            ownership_case(cpu, team, side, mask, entry, flag)
            if team < 16:
                ownership_case(old, team, side, mask, entry, flag)
                parity(cpu, old, (team, side, mask, hex(entry), flag))
    print("ownership: all32/both sides x clear/set/alternating/16 single-bit masks; reader and human/CPU writer; exact low RAM/register/flag/stack/write parity; no high-team mask writes OK")


def routing_case(cpu, teams, mask, batting_side, inverted):
    reset(cpu)
    memory = cpu.memory
    memory[0x04EF:0x04F1] = teams
    memory[0x074B:0x074D] = [mask & 255, mask >> 8]
    memory[0x04ED:0x04EF] = [batting_side, batting_side ^ 1]
    memory[0x04E9] = inverted
    memory[0x8F:0x93] = [0x12, 0x34, 0x56, 0x78]
    memory[0x2C], memory[0x047C] = 3, 9
    call(cpu, 0x9CAC)
    flags = [ownership(team, mask) for team in teams]
    assert memory[0x04EB:0x04ED] == flags
    swap = flags[0] & 0x80 and not flags[1] & 0x80
    cpu.pc = 0x9C1A
    trace = run(cpu, 0x9C39)
    expected_teams = list(reversed(teams)) if swap else list(teams)
    expected_flags = list(reversed(flags)) if swap else flags
    assert memory[0x04EF:0x04F1] == expected_teams
    assert memory[0x04EB:0x04ED] == expected_flags
    assert (0x9C24 in trace) == bool(swap)
    assert cpu.sp == 0xFF
    memory.writes.clear()
    call(cpu, 0xC585)
    for output, side in enumerate((batting_side, batting_side ^ 1)):
        controller = side ^ int(bool(inverted))
        expected = [0, 0] if expected_flags[side] & 0x80 else [memory[0x8F + controller], memory[0x91 + controller]]
        assert [memory[0x93 + output], memory[0x95 + output]] == expected, (
            teams, mask, batting_side, inverted, output, expected_flags)
    assert all(addr in (0x93, 0x94, 0x95, 0x96) or 0x100 <= addr < 0x200
               for addr, _ in memory.writes)


def test_routing(rom, base):
    cpu, old = machine(rom, 5), machine(base, 5)
    for team, other, mask, side, inverted in itertools.product(range(32), range(32), MASKS, range(2), range(2)):
        routing_case(cpu, (team, other), mask, side, inverted)
        if team < 16 and other < 16:
            routing_case(old, (team, other), mask, side, inverted)
            parity(cpu, old, (team, other, mask, side, inverted))
    for counter, original in itertools.product(range(16), (0, 0x5555, 0xFFFF)):
        reset(cpu)
        memory = cpu.memory
        memory[0x0746] = counter
        memory[0x0755:0x0757] = [original & 255, original >> 8]
        memory[0x04EF] = 31
        memory[0x0650 + counter * 2] = 0
        cpu.pc = 0x9F84
        run(cpu, 0x9FB5)
        assert memory[0x0755] | memory[0x0756] << 8 == original | (1 << counter)
        assert memory[0x0746] == counter
    print("routing: all 1024 team pairs x 20 masks x both batting sides x controller inversion; $9CAC ownership, $9C1A swap block through $9C39, $C585 CPU filtering, low parity; stock result mask execution OK")


def test_negative_controls(base):
    controls = [("high bonus", lambda: bonus_case(machine(base, 4), 16, 0, 0)),
                ("high ownership read", lambda: ownership_case(machine(base, 5), 16, 0, 0, 0x9CB2)),
                ("high ownership write", lambda: ownership_case(machine(base, 5), 16, 0, 0, 0x9F41))]
    for bank, _ in BATTING:
        controls.append((f"bank {bank} high batting bias",
                         lambda bank=bank: batting_case(machine(base, bank), 16, 0, 10, (0, 0), 2)))
    for name, check in controls:
        try:
            check()
        except AssertionError as exc:
            print(f"unpatched negative control rejected {name}: {exc}")
        else:
            raise AssertionError(f"unpatched negative control passed {name}")


def rejected(base, phrase=None):
    try:
        build_rom(base)
    except ValueError as exc:
        assert phrase is None or phrase in str(exc), str(exc)
    else:
        raise AssertionError("builder accepted mismatched input")


def test_builder(base, rom):
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256
    assert build_rom(base) == rom
    mutable = bytearray(base)
    assert build_rom(mutable) == rom and mutable == base
    ranges = [(4, 0xAA9A, 2), (4, 0xB700, 128), (5, 0x9CB2, 3), (5, 0x9F46, 3),
              (5, 0xBD40, 15), (5, 0xBD50, 11)]
    ranges.extend((bank, 0xBB91, 2) for bank, _ in BATTING)
    changed = {index for index, (before, after) in enumerate(zip(base, rom)) if before != after}
    expected = {off(bank, addr) + index for bank, addr, length in ranges for index in range(length)}
    expected.update(off(bank, addr) + index for bank, addr in BATTING for index in range(32)
                    if index >= 16 or STOCK_BIAS[index] != -1)
    assert len(rom) == len(base) and changed == expected and len(changed) == 274
    for change in change_manifest():
        start = off(change.bank, change.addr)
        assert base[start:start + len(change.before)] == change.before
        assert rom[start:start + len(change.after)] == change.after
        for index in (start, start + len(change.before) - 1):
            damaged = bytearray(base)
            damaged[index] ^= 1
            rejected(damaged, "expected bytes or reservation")
    for bank, addr, length in ((4, 0xAAAB, 80), (5, 0x9CD0, 16),
                               *((bank, 0xBC4F, 16) for bank, _ in BATTING)):
        start = off(bank, addr)
        assert rom[start:start + length] == base[start:start + length]
        damaged = bytearray(base)
        damaged[start] ^= 1
        rejected(damaged, "expected bytes or reservation")
    start = off(5, 0xBC80)
    assert rom[start:start + 0x60] == base[start:start + 0x60], "parent CPU tables changed"
    for damaged in (base[:-1], base + b"\0", rom):
        rejected(damaged)
    for index in (0, 4, 5, 6, 15, 0x50000, off(5, 0xBD4F), off(5, 0xBD5B), off(4, 0xB780)):
        damaged = bytearray(base)
        damaged[index] ^= 1
        rejected(damaged, "header" if index < 16 else "SHA-256")
    script = Path(__file__).with_name("build_teamtables32.py")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "cpu32.nes"
        source.write_bytes(base)
        protected = [source]
        for name in PROTECTED_NAMES:
            path = directory / name
            if path != source:
                path.write_bytes(b"protected baseline")
                protected.append(path)
        protected.append(directory / "absent" / ".." / "gameplay32.nes")
        aliases = protected[:]
        for path in protected[:-1]:
            symlink = directory / (path.stem + "-symlink")
            symlink.symlink_to(path)
            hardlink = directory / (path.stem + "-hardlink")
            os.link(path, hardlink)
            aliases.extend((symlink, hardlink))
        elsewhere = directory / "elsewhere"
        elsewhere.mkdir()
        copied = elsewhere / "copy.nes"
        copied.write_bytes(base)
        aliases.append(copied)
        snapshots = [(path, path.read_bytes()) for path in protected[:-1]]
        command = [sys.executable, str(script), str(source), "-o"]
        for output in aliases:
            result = subprocess.run(command + [str(output)], capture_output=True, text=True)
            assert result.returncode != 0 and "protected input" in result.stderr, result.stderr
            assert all(path.read_bytes() == before for path, before in snapshots)
        output = directory / "teamtables32.nes"
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom, result.stderr
        source.write_bytes(base[:-1])
        output.write_bytes(b"existing output")
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode != 0 and output.read_bytes() == b"existing output"
    print("builder: exact 274-byte change set, original tables/results preserved, immutable input, header/hash/expected-byte/reservation/alias guards and CLI output OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned cpu32.nes")
    ap.add_argument("--candidate", type=Path, help="execute an independently written teamtables32 ROM")
    args = ap.parse_args()
    base = args.rom.read_bytes()
    assert hashlib.sha256(base).hexdigest() == BASE_SHA256
    built = build_rom(base)
    rom = args.candidate.read_bytes() if args.candidate else built
    assert rom == built, "candidate differs from the guarded build"
    test_negative_controls(base)
    test_builder(base, rom)
    test_bonuses(rom, base)
    test_batting(rom, base)
    test_ownership(rom, base)
    test_routing(rom, base)
    print(f"teamtables32 passed: {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
