#!/usr/bin/env python3
"""Execute control32 under py65 with real ROM pad readers and serial MMC1 writes.

    .venv/bin/python tools/test_control32.py build/results32.nes --candidate build/control32.nes

Only vblank status and controller pins are supplied. No NMI, PPU or audio is emulated.
"""
import argparse
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

from build_control32 import (
    BASE_SHA256, COMMIT, MASK_BYTES, NEW_SERIES, PROTECTED_NAMES, ROOT, TEAMS,
    build_rom, change_manifest, off, source_selector_bank,
)

RAM = bytes((a * 29 + 0x53) & 255 for a in range(0x800))
PRG_RAM = bytes((a * 7 + 3) & 255 for a in range(0x2000))
A, B, RIGHT, LEFT, UP, DOWN = 0x80, 0x40, 1, 2, 8, 4
OUTPUT_SHA256 = "a1caf9a28e750a777343f2bdbd5c02987a03ccac0f58b6257e62dbee0faf30a8"


class Bus:
    def __init__(self, rom, bank, pads=()):
        self.rom, self.mem = rom, bytearray(0x10000)
        self.mem[0xC000:] = rom[off(15, 0xC000):off(15, 0x10000)]
        self.map(bank)
        self.shift = self.count = self.strobe = self.latch = self.bit = 0
        self.pads, self.samples, self.serial_reads = tuple(pads), [], 0
        self.writes, self.reads, self.mapper_writes = [], [], []

    def map(self, bank):
        self.bank = bank
        self.mem[0x8000:0xC000] = self.rom[off(bank, 0x8000):off(bank, 0xC000)]

    def __getitem__(self, address):
        if isinstance(address, slice):
            return self.mem[address]
        if address == 0x2002:
            return 0x80
        if address == 0x4016:
            self.serial_reads += 1
            if self.strobe:
                return self.latch >> 7
            value = (self.latch >> (7 - self.bit)) & 1 if self.bit < 8 else 1
            self.bit += 1
            return value
        self.reads.append(address)
        return self.mem[address]

    def __setitem__(self, address, value):
        if isinstance(address, slice):
            self.mem[address] = value
            return
        if address >= 0x8000:
            self.mapper_writes.append((address, value))
            if value & 0x80:
                self.shift = self.count = 0
                return
            self.shift |= (value & 1) << self.count
            self.count += 1
            if self.count == 5:
                if address >= 0xE000:
                    self.map(self.shift & 15)
                self.shift = self.count = 0
            return
        if address == 0x4016:
            if self.strobe and not value & 1:
                self.latch = self.pads[min(len(self.samples), len(self.pads) - 1)] if self.pads else 0
                self.samples.append(self.latch)
                self.bit = 0
            self.strobe = value & 1
        self.writes.append((address, value))
        self.mem[address] = value


def machine(rom, bank, pads=()):
    cpu = MPU(memory=Bus(rom, bank, pads))
    cpu.memory.mem[:0x800] = RAM
    cpu.memory.mem[0x6000:0x8000] = PRG_RAM
    cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp = 0xA5, 0x5A, 0x6C, 0x20, 0xFF
    return cpu


def run_to(cpu, stops, limit=400000):
    stops = (stops,) if isinstance(stops, int) else stops
    for _ in range(limit):
        if cpu.pc in stops:
            return cpu.pc
        cpu.step()
    raise AssertionError(f"did not reach {stops}, bank{cpu.memory.bank} PC=${cpu.pc:04X}")


def call(cpu, address):
    stack = cpu.sp
    cpu.stPushWord(0x01FF)
    cpu.pc = address
    run_to(cpu, 0x0200)
    assert cpu.sp == stack, (hex(address), cpu.sp, stack)


def mask32(memory):
    return sum(memory[a] << (8 * i) for i, a in enumerate(MASK_BYTES))


def set_mask(memory, value):
    for i, a in enumerate(MASK_BYTES):
        memory[a] = value >> (8 * i) & 255


def setup_match(rom, pair, mask):
    cpu = machine(rom, 5)
    m = cpu.memory.mem
    m[0x07FA], m[0x07FB] = pair
    set_mask(m, mask)
    cpu.pc = 0x9C0B
    run_to(cpu, 0x9C39)
    return cpu


def humans(cpu):
    m = cpu.memory.mem
    return {m[0x04EF + side] for side in (0, 1) if not m[0x04EB + side] & 0x80}


def test_entry(base, rom):
    for source, scene in ((base, 0x0C), (rom, 0x12)):
        cpu = machine(source, 1)
        call(cpu, 0x9508)
        assert cpu.memory.mem[0x047B] == scene and cpu.memory.mem[0x07ED] == scene
    cpu = machine(rom, 5)
    cpu.pc = 0x98B9
    run_to(cpu, 0x8000)
    assert cpu.memory.bank == 10 and cpu.memory.mem[0x27] == 10
    assert cpu.memory.mem[0x07F7] == cpu.sp == 0xFD
    assert cpu.memory.mem[0x2000] == 0
    for source in (base, rom):
        assert source[off(15, 0xCC79):off(15, 0xCC7B)] == bytes.fromhex("99 58")
        assert source[off(15, 0xFEA0):off(15, 0xFECB)] == b"\xff" * 43
        for bank in range(16):
            start = off(bank, 0xC000 if bank == 15 else 0x8000)
            data = source[start:start + 0x4000]
            assert bytes.fromhex("ad f0 07") not in data
    print("entry: title queues $12, bridge serially maps bank10, legacy scene13 VIEW reader absent")


def test_commits(rom):
    rng = random.Random(7)
    masks = []
    for team in range(32):
        for prior in (0, 0xFFFFFFFF, 0xFFFFFDFF, rng.getrandbits(32)):
            cpu = machine(rom, 10)
            m = cpu.memory.mem
            m[0x07C3] = team
            set_mask(m, prior)
            cpu.pc = COMMIT
            run_to(cpu, 0x8380)
            assert mask32(m) == 0xFFFFFFFF ^ (1 << team), (team, prior)
            assert cpu.memory.bank == 11 and m[0x27] == 11 and m[0x2D] == RAM[0x2D]
            assert {a for a, _ in cpu.memory.writes} <= {
                *MASK_BYTES, 0x00, 0x27, 0x2D, *range(0x100, 0x200),
            }
            assert not cpu.memory.count and cpu.sp == 0xFF
        masks.append(mask32(m))
    print("commit: all32 x four prior masks initialize exactly one human, bounded writes and balanced stack")
    return masks


def selector_run(rom, pads):
    cpu = machine(rom, 10, pads)
    cpu.pc = 0x8000
    run_to(cpu, 0x80C3, 2000000)
    select_poll = len(cpu.memory.samples)
    run_to(cpu, 0x8380, 2000000)
    assert cpu.memory.serial_reads == 8 * len(cpu.memory.samples)
    assert not cpu.memory.samples[-1]
    assert cpu.memory.bank == 11
    assert not any(0x07F3 <= a <= 0x07F9 for a, _ in cpu.memory.writes)
    assert all(cpu.memory.mem[a] == 0xF0 for a in range(0x200, 0x300, 4))
    assert (0x4014, 2) in cpu.memory.writes
    return cpu, select_poll


def test_selector(base, rom, document):
    raw = bytearray(base)
    start = off(10, 0x8000)
    raw[start:start + 0x4000] = source_selector_bank(document)
    pads = [A] * 6 + [0] * 3 + [RIGHT] + [0] * 2 + [A] * 4 + [0]
    old = machine(bytes(raw), 10, pads)
    old.pc = 0x8000
    run_to(old, 0x80C3, 2000000)
    assert old.memory.samples == [A], "unmodified source selector must fail held-A entry"
    cpu, poll = selector_run(rom, pads)
    assert poll == 13 and cpu.memory.mem[0x07C3] == 1
    for team in range(32):
        pads = [A] * 6 + [0] * 3
        directions = ([DOWN] if team & 4 else []) + [RIGHT] * ((team >> 3) * 4 + (team & 3))
        for direction in directions:
            pads += [direction, direction, 0]
        pads += [A] * 4 + [0]
        cpu, _ = selector_run(rom, pads)
        m = cpu.memory.mem
        assert m[0x07C3] == team and mask32(m) == 0xFFFFFFFF ^ (1 << team)
        assert cpu.sp == 0xFF
    for held in (B, UP, DOWN, LEFT, RIGHT, 0x10, 0x20, A | B):
        cpu, poll = selector_run(rom, [held] * 4 + [0, RIGHT, 0, A, A, 0])
        assert poll == 8 and cpu.memory.mem[0x07C3] == 1
    cpu, _ = selector_run(rom, [0, B, B, 0, RIGHT, 0, A, 0])
    assert cpu.memory.mem[0x07C3] == 1, "B keeps the source selector's local clear behavior"
    print("selector: serial pads select all32, held keys ignored, OAM hidden, no debug stores or new B exit")


def test_seed_once(rom):
    for team in range(32):
        cpu = machine(rom, 11)
        m = cpu.memory.mem
        m[0x07C3], m[0x07ED], m[0x07EF], m[0x07F0] = team, 0, 0, 1
        set_mask(m, 0xFFFFFFFF ^ (1 << team))
        cpu.pc = 0x8380
        run_to(cpu, 0x8000)
        leaves = bytes((team,)) + bytes(t for t in range(32) if t != team)
        assert m[0x7700:0x7720] == leaves
        assert m[0x7720:0x773F] == b"\xff" * 31 and m[0x07FC] == 0
        assert (m[0x07ED], m[0x07EF], m[0x07F0]) == (1, 0x32, 0)
        assert mask32(m) == 0xFFFFFFFF ^ (1 << team)
        cpu.memory.map(4)
        cpu.pc = 0xAAFB
        run_to(cpu, 0xAB05)
        assert m[0x07C3] == 0 and m[0x07ED] == 1 and m[0x07EF] == 0x32
        cpu.memory.map(11)
        m[0x7720:0x773F] = bytes(range(31))
        heap = bytes(m[0x7700:0x773F])
        for _ in range(2):
            cpu.memory.writes.clear()
            cpu.pc = 0x8000
            run_to(cpu, 0x8100, 2000000)
            assert m[0x7700:0x773F] == heap
            assert not any(a == 0x07C3 or 0x7700 <= a < 0x773F for a, _ in cpu.memory.writes)
            assert mask32(m) == 0xFFFFFFFF ^ (1 << team)
    print("seed once: all32 reset VIEW, set active marker, seed once; real $AAFB wipe and two full redraws preserve heap")


def test_ownership(base, rom, masks):
    count = 0
    for team, mask in enumerate(masks):
        for pair in itertools.permutations(range(32), 2):
            cpu = setup_match(rom, pair, mask)
            m = cpu.memory.mem
            expected = {team} & set(pair)
            assert humans(cpu) == expected, (team, pair, humans(cpu))
            if expected:
                assert (m[0x04EF], m[0x04EB], m[0x04EC]) == (team, 0, 0x80)
            assert mask32(m) == mask and cpu.sp == 0xFF
            count += 1
    parity = 0
    for low, high in itertools.product((0, 0xFFFF, 0x5555, 0xFDFF), (0xFFFF, 0, 0xA5A5)):
        for pair in itertools.permutations(range(32), 2):
            if high != 0xFFFF and max(pair) >= 16:
                continue
            new = setup_match(rom, pair, low | high << 16)
            old = setup_match(base, pair, low | high << 16)
            assert new.memory.mem[:0x800] == old.memory.mem[:0x800], (pair, low, high)
            assert (new.a, new.x, new.y, new.p, new.sp) == (old.a, old.x, old.y, old.p, old.sp)
            assert new.memory.writes == old.memory.writes
            parity += 1
    for mask in (0, 0xFFFFFFFF, 0x55555555, 0xAAAAAAAA):
        for pair in itertools.permutations(range(32), 2):
            cpu = setup_match(rom, pair, mask)
            assert humans(cpu) == {t for t in pair if not mask & (1 << t)}
            assert mask32(cpu.memory.mem) == mask
    print(f"ownership: {count} setups, {parity} exact low-team/all-CPU-high parity cases, 3968 restored-mask setups")


def test_routing(rom, masks):
    count = 0
    for team, mask in enumerate(masks):
        for other in range(32):
            if other == team:
                continue
            for pair in ((team, other), (other, team)):
                cpu = setup_match(rom, pair, mask)
                m = cpu.memory.mem
                for swap, batting in itertools.product((False, True), (0, 1)):
                    saved = bytes(m[0x04EB:0x04F1])
                    m[0x04E9] = int(swap)
                    if swap:
                        m[0x04EF], m[0x04F0] = m[0x04F0], m[0x04EF]
                        m[0x04EB], m[0x04EC] = m[0x04EC], m[0x04EB]
                    m[0x04ED], m[0x04EE] = batting, batting ^ 1
                    m[0x8F:0x93] = bytes((0x11, 0x22, 0x33, 0x44))
                    call(cpu, 0xC585)
                    for role, side in enumerate((batting, batting ^ 1)):
                        expected = (0x11, 0x33) if m[0x04EF + side] == team else (0, 0)
                        assert (m[0x93 + role], m[0x95 + role]) == expected
                    assert mask32(m) == mask
                    m[0x04EB:0x04F1] = saved
                    count += 1
        cpu = setup_match(rom, (team, team ^ 1), mask)
        m = cpu.memory.mem
        m[0xBE:0xC0] = m[0x04EB:0x04ED]
        m[0x91:0x93] = bytes((UP, UP))
        cpu.x = 0
        cpu.pc = 0x9E17
        run_to(cpu, 0x9E28)
        assert m[0xBE] == 0x80 and mask32(m) == mask
        restored = setup_match(rom, (team, team ^ 1), mask)
        assert restored.memory.mem[0x04EB] == 0
    print(f"routing: {count} real $C585 cases route port1 in both halves and home/away layouts; COM toggle lasts one match")


def bracket_handoff(rom, pads):
    cpu = machine(rom, 11, pads)
    cpu.pc = 0x8100
    run_to(cpu, 0x8360)
    assert cpu.sp == 0xFF and cpu.memory.serial_reads == 8 * len(cpu.memory.samples)
    return cpu


def test_handoff(base, rom):
    pads = [A] * 6 + [0] * 3 + [A] * 5 + [0]
    old = bracket_handoff(base, pads)
    assert len(old.memory.samples) == 10 and old.memory.samples[-1] == A
    new = bracket_handoff(rom, pads)
    assert new.memory.samples == pads and new.memory.mem[0x07C6] == 0
    pads = [A] * 4 + [0] + [B] * 3 + [0] + [A] * 4 + [A | B] * 2 + [B] * 3 + [0]
    new = bracket_handoff(rom, pads)
    assert new.memory.samples == pads, "handoff must wait for every held button to release"
    print("handoff: real $4016 serial regression reproduces results32 exit on poll10 with A down; control32 waits to poll15 release")


def test_results(base, rom):
    for series, done in itertools.product(range(2), range(3)):
        cpu = machine(rom, 4)
        m = cpu.memory.mem
        m[0x04E2], m[0x04D0], m[0x27] = series, done, 4
        cpu.pc = 0xFFC0
        run_to(cpu, 0x83A0 if series and done else 0xB63D)
        assert cpu.memory.bank == (11 if series and done else 4)
        assert not any(0x7700 <= a < 0x773F for a, _ in cpu.memory.writes)
    ongoing = 0
    for series, half, pad, timer, flags in itertools.product(range(2), range(36), (0, A), (0, A), (0, 1, 0x80, 0xFF)):
        machines = (machine(rom, 4), machine(base, 4))
        for cpu in machines:
            m = cpu.memory.mem
            m[0x047B], m[0x04E2], m[0x04D0] = 11, series, 0
            m[0x048A], m[0x0401], m[0x31] = half, timer, pad
            m[0x04EB:0x04EF] = bytes((0x80, 0x80, 0, 1))
            cpu.p = flags
        call(machines[0], 0xFFC0)
        call(machines[1], 0xB63D)
        current, old = machines
        assert current.memory.mem[:0x8000] == old.memory.mem[:0x8000]
        assert current.memory.writes == old.memory.writes
        assert (current.a, current.x, current.y, current.p, current.sp) == (old.a, old.x, old.y, old.p, old.sp)
        ongoing += 1
    winners = 0
    for match, team, swap, scores in itertools.product(range(31), range(32), range(2), ((2, 0), (0, 2), (0, 0), (255, 1), (1, 255))):
        cpu = machine(rom, 11)
        m = cpu.memory.mem
        pair = (team, (team + 17) % 32)
        live = pair[::-1] if swap else pair
        m[0x07FC] = match
        m[0x7700 + 2 * match:0x7702 + 2 * match] = bytes(pair)
        m[0x04EF:0x04F1], m[0x048B:0x048D] = bytes(live), bytes(scores)
        cpu.pc = 0x83A0
        run_to(cpu, 0x8000)
        expected = pair[0] if scores[0] == scores[1] else live[int(scores[0] < scores[1])]
        assert cpu.memory.writes == [(0x7720 + match, expected), (0x07FC, match + 1)]
        winners += 1
    for match in (31, 32, 255):
        cpu = machine(rom, 11)
        cpu.memory.mem[0x07FC] = match
        cpu.pc = 0x83A0
        run_to(cpu, 0x8000)
        assert not cpu.memory.writes
    print(f"results preserved: six gate cases, {ongoing} exact stock continuations, {winners} live-side winner cases")


def test_negative_controls(base, rom):
    for team, pair in ((16, (16, 0)), (31, (0, 31))):
        assert humans(setup_match(base, pair, 0xFFFFFFFF ^ (1 << team))) == set()
        assert humans(setup_match(rom, pair, 0xFFFFFFFF ^ (1 << team))) == {team}
    assert humans(setup_match(base, (9, 10), 0xFFFFFDFF)) == {9}
    cpu = machine(base, 11)
    cpu.memory.mem[0x07C3] = 31
    cpu.pc = 0x8000
    run_to(cpu, 0x801F)
    assert cpu.memory.mem[0x07C3] == cpu.memory.mem[0x7700] == 15
    print("negative controls: results32 forces high teams CPU, inherits stray team9 human, and reseeds to15")


def test_builder(base, rom, document):
    mutable = bytearray(base)
    assert build_rom(mutable, document) == rom and mutable == base
    changes = change_manifest(document)
    allowed = {i for c in changes for i in range(off(c.bank, c.addr), off(c.bank, c.addr) + len(c.after))}
    expected = {off(c.bank, c.addr) + i for c in changes
                for i, (a, b) in enumerate(zip(c.before, c.after)) if a != b}
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert changed == expected and changed <= allowed and len(rom) == len(base)
    for bank, first, last in ((11, 0x8105, 0x8108), (11, 0x81D0, 0x81DA),
                              (11, 0x83A0, 0x83D0), (15, 0xFFC0, 0xFFE7),
                              (11, 0x8600, 0x8680), (11, 0x8680, 0x86E0),
                              (11, 0x86F5, 0x8700), (15, 0xFEA0, 0xFEC4)):
        assert rom[off(bank, first):off(bank, last)] == base[off(bank, first):off(bank, last)]
    assert rom[off(11, NEW_SERIES):off(11, NEW_SERIES) + 21] == bytes.fromhex(
        "a9 32 8d ef 07 a9 01 8d ed 07 a9 00 8d f0 07 20 00 82 4c 00 80")
    invalid = [base[:-1], base + b"\0", rom]
    addresses = {0, 4, 5, 6, 0x50000, off(11, 0x8600), off(11, 0x8680),
                 off(11, 0x8105), off(11, 0x81D0), off(15, 0xCC79), off(15, 0xFEA0)}
    addresses.update(off(c.bank, c.addr) for c in changes)
    for address in addresses:
        damaged = bytearray(base)
        damaged[address] ^= 1
        invalid.append(damaged)
    for damaged in invalid:
        try:
            build_rom(damaged, document)
        except ValueError:
            pass
        else:
            raise AssertionError("builder accepted altered input")
    for field, value in (("id", 32), ("name", ""), ("code", "TOOLONG"), ("name", "\u00e9")):
        damaged = copy.deepcopy(document)
        damaged["teams"][31][field] = value
        try:
            build_rom(base, damaged)
        except ValueError:
            pass
        else:
            raise AssertionError("builder accepted invalid teams")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "results32.nes"
        source.write_bytes(base)
        teams = directory / "teams.json"
        teams.write_text(json.dumps(document))
        protected = [source, teams]
        for name in (*PROTECTED_NAMES, "teamtables32.nes", "roles32.nes"):
            path = directory / name
            path.write_bytes(b"protected baseline")
            protected.append(path)
        aliases = protected[:]
        for i, target in enumerate(protected):
            symlink = directory / f"symlink{i}"
            symlink.symlink_to(target)
            hardlink = directory / f"hardlink{i}"
            os.link(target, hardlink)
            aliases.extend((symlink, hardlink))
        elsewhere = directory / "elsewhere"
        elsewhere.mkdir()
        copied = elsewhere / "input-copy.nes"
        copied.write_bytes(base)
        aliases.extend((copied, directory / "missing" / ".." / "results32.nes",
                        Path(__file__), Path(__file__).with_name("build_control32.py"),
                        Path(__file__).with_name("build_select_screen.py"), TEAMS))
        command = [sys.executable, str(Path(__file__).with_name("build_control32.py")),
                   str(source), "--teams", str(teams), "-o"]
        snapshots = [(path, path.read_bytes()) for path in (*protected, *aliases) if path.is_file()]
        for output in aliases:
            result = subprocess.run(command + [str(output)], capture_output=True, text=True)
            assert result.returncode and "protected input" in result.stderr, result.stderr
            assert all(path.read_bytes() == contents for path, contents in snapshots)
        output = directory / "control32.nes"
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom, result.stderr
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom
        raw = directory / "source-selector.nes"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("build_select_screen.py")),
                                 str(source), str(teams), "-o", str(raw)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert raw.read_bytes()[off(10, 0x8000):off(10, 0xC000)] == source_selector_bank(document)
        source.write_bytes(invalid[-1])
        output.write_bytes(b"existing output")
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode and output.read_bytes() == b"existing output"
        source.write_bytes(base)
        teams.write_text("invalid JSON")
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode and output.read_bytes() == b"existing output"
    outside10 = sum(not off(10, 0x8000) <= i < off(10, 0xC000) for i in changed)
    print(f"builder: exactly {len(changed)} changed bytes, {outside10} outside bank10; source assets match, guards and aliases rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--teams", type=Path, default=TEAMS)
    args = parser.parse_args()
    base = args.rom.read_bytes()
    assert hashlib.sha256(base).hexdigest() == BASE_SHA256
    document = json.loads(args.teams.read_text())
    rom = build_rom(base, document)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from guarded build"
    test_negative_controls(base, rom)
    test_entry(base, rom)
    masks = test_commits(rom)
    test_selector(base, rom, document)
    test_seed_once(rom)
    test_handoff(base, rom)
    test_ownership(base, rom, masks)
    test_routing(rom, masks)
    test_results(base, rom)
    test_builder(base, rom, document)
    digest = hashlib.sha256(rom).hexdigest()
    if args.teams.resolve() == TEAMS.resolve():
        assert digest == OUTPUT_SHA256
    print(f"control32 CPU checks passed: {digest}")


if __name__ == "__main__":
    main()
