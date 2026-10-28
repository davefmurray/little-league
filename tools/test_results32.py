#!/usr/bin/env python3
"""Execute bracket completion, live-side winner and stock continuation checks.

    .venv/bin/python tools/test_results32.py build/roles32.nes --candidate build/results32.nes
"""
import argparse
import copy
import hashlib
import itertools
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from build_results32 import BASE_SHA256, build_rom, off
from test_gameplay32 import Memory, machine, run, call

OUTPUT_SHA256 = "9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b"


def test_ongoing(rom, base):
    for series, half, pad, timer, flags in itertools.product(range(2), range(36), (0, 0x80), (0, 0x80), (0, 1, 0x80, 0xFF)):
        current = machine(rom)
        memory = current.memory
        memory[0x047B] = 11
        memory[0x04E2] = series
        memory[0x048A] = half
        memory[0x0401] = timer
        memory[0x31] = pad
        memory[0x04EB:0x04EF] = [0x80, 0x80, 0, 1]
        memory[0x7700:0x7740] = [0xA5] * 64
        current.p = flags
        original = copy.deepcopy(current)
        original.memory[0xC000:0x10000] = base[off(15, 0xC000):off(15, 0x10000)]
        current.memory.writes.clear()
        original.memory.writes.clear()
        call(current, 0xFFC0)
        call(original, 0xB63D)
        assert current.memory[:0x8000] == original.memory[:0x8000], (half, pad, timer, flags)
        assert current.memory.writes == original.memory.writes
        assert (current.a, current.x, current.y, current.p, current.sp) == (original.a, original.x, original.y, original.p, original.sp)
        assert current.memory[0x07FC] == 0 and current.memory[0x7700:0x7740] == [0xA5] * 64
    print('ongoing games: 1152 cases match the stock box-score handler exactly')


def test_gate(rom):
    for series, flag in itertools.product(range(2), range(3)):
        cpu = machine(rom)
        cpu.memory[0x04E2] = series
        cpu.memory[0x04D0] = flag
        cpu.memory[0x27] = 4
        cpu.memory.writes.clear()
        cpu.pc = 0xFFC0
        run(cpu, 0x83A0 if series and flag else 0xB63D)
        assert cpu.memory[0x27] == (11 if series and flag else 4)
        assert cpu.memory[0x07FC] == 0
        assert not any(0x7700 <= addr < 0x7740 for addr, _ in cpu.memory.writes)
    print('completion gate: exhibitions and unfinished games retain bank4; completed championship games select bank11')


def result(rom, match, pair, live, scores):
    cpu = machine(rom, 11)
    cpu.memory[0x07FC] = match
    cpu.memory[0x7700:0x7740] = [0xFF] * 64
    if match < 31:
        cpu.memory[0x7700 + 2 * match:0x7702 + 2 * match] = pair
    cpu.memory[0x04EF:0x04F1] = live
    cpu.memory[0x048B:0x048D] = scores
    cpu.memory.writes.clear()
    cpu.pc = 0x83A0
    run(cpu, 0x8000)
    return cpu


def test_winners(rom):
    cases = 0
    for match, team, swap, scores in itertools.product(range(31), range(32), range(2), ((2, 0), (0, 2), (0, 0), (255, 1), (1, 255))):
        pair = [team, (team + 17) % 32]
        live = pair[::-1] if swap else pair
        cpu = result(rom, match, pair, live, scores)
        expected = pair[0] if scores[0] == scores[1] else live[int(scores[0] < scores[1])]
        assert cpu.memory[0x7720 + match] == expected, (match, pair, live, scores)
        assert cpu.memory.writes == [(0x7720 + match, expected), (0x07FC, match + 1)]
        cases += 1
    for match in (31, 32, 255):
        cpu = result(rom, match, [0, 1], [0, 1], [2, 0])
        assert not cpu.memory.writes and cpu.memory[0x07FC] == match
    print(f'winners: {cases} cases cover all teams, match positions, side swaps and ties; completed brackets stay unchanged')


class ControllerMemory(Memory):
    def __init__(self, contents):
        super().__init__()
        self[:] = contents
        self.reads = 0

    def __getitem__(self, address):
        if address == 0x4016:
            poll, bit = divmod(self.reads, 8)
            buttons = (0x80, 0x80, 0, 0x80)[min(poll, 3)]
            self.reads += 1
            return (buttons >> (7 - bit)) & 1
        return super().__getitem__(address)


def input_polls(rom):
    cpu = machine(rom, 11)
    cpu.memory = ControllerMemory(cpu.memory)
    cpu.pc = 0x8100
    run(cpu, 0x8360)
    assert cpu.sp == 0xFF
    return cpu.memory.reads // 8


def test_input(rom, base):
    assert input_polls(base) == 1
    assert input_polls(rom) == 4
    print('held-A negative control launches immediately; fixed bracket waits for release and a new press')


def test_aliases(base, rom):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "roles32.nes"
        source.write_bytes(base)
        symlink = directory / "symlink.nes"
        symlink.symlink_to(source)
        hardlink = directory / "hardlink.nes"
        os.link(source, hardlink)
        copied = directory / "copy.nes"
        copied.write_bytes(base)
        command = [sys.executable, str(Path(__file__).with_name("build_results32.py")), str(source), "-o"]
        for output in (source, symlink, hardlink, copied):
            result = subprocess.run(command + [str(output)], capture_output=True, text=True)
            assert result.returncode and "protected input" in result.stderr
            assert source.read_bytes() == base
        output = directory / "results32.nes"
        result = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert result.returncode == 0 and output.read_bytes() == rom, result.stderr
    print('CLI: input aliases rejected and output matches guarded build')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    base = args.rom.read_bytes()
    assert hashlib.sha256(base).hexdigest() == BASE_SHA256
    rom = build_rom(base)
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256
    if args.candidate:
        assert args.candidate.read_bytes() == rom
    old = result(base, 0, [15, 0], [0, 15], [2, 0])
    assert old.memory[0x7720] == 15
    print('old winner negative control: swapped live sides incorrectly credit team15 instead of team0')
    old = machine(base)
    old.memory[0x04D0] = 0
    old.pc = 0xFFC0
    run(old, 0x83A0)
    print('old gate negative control: unfinished game reaches winner entry')
    test_gate(rom)
    test_ongoing(rom, base)
    test_winners(rom)
    test_input(rom, base)
    allowed = set(range(off(15, 0xFFC0), off(15, 0xFFE7))) | set(range(off(11, 0x83A0), off(11, 0x83D0)))
    allowed |= set(range(off(11, 0x8105), off(11, 0x8108))) | set(range(off(11, 0x81D0), off(11, 0x81DA)))
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert len(base) == len(rom) and len(changed) == 98 and changed <= allowed
    mutable = bytearray(base)
    assert build_rom(mutable) == rom and mutable == base
    for address in (0, off(15, 0xFFC0), off(11, 0x83A0), 0x50000):
        damaged = bytearray(base)
        damaged[address] ^= 1
        try:
            build_rom(damaged)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted altered input")
    print(f'builder: {len(changed)} changed bytes within existing result routines')
    test_aliases(base, rom)
    print(f'results32 passed: {OUTPUT_SHA256}')


if __name__ == '__main__':
    main()
