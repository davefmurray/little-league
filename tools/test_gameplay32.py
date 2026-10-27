#!/usr/bin/env python3
"""Execute the gameplay repairs in py65 using the pinned direct31 input.

    .venv/bin/python tools/test_gameplay32.py build/direct31.nes
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

from build_gameplay32 import build_rom


class Memory(list):
    def __init__(self):
        super().__init__([0] * 0x10000)
        self.writes = []

    def __setitem__(self, addr, value):
        super().__setitem__(addr, value)
        if isinstance(addr, int):
            self.writes.append((addr, value))


def machine(rom, bank=4):
    memory = Memory()
    memory[0x8000:0xC000] = rom[16 + bank * 0x4000:16 + (bank + 1) * 0x4000]
    memory[0xC000:0x10000] = rom[0x3C010:0x40010]
    return MPU(memory=memory)


def run(cpu, stop, limit=5000):
    trace = []
    for _ in range(limit):
        if cpu.pc == stop:
            return trace
        trace.append(cpu.pc)
        cpu.step()
    raise AssertionError(f"did not reach ${stop:04X}, PC=${cpu.pc:04X}, SP=${cpu.sp:02X}")


def call(cpu, entry):
    before = cpu.sp
    cpu.stPushWord(0x01FF)
    cpu.pc = entry
    trace = run(cpu, 0x0200)
    assert cpu.sp == before, (hex(entry), cpu.sp, before)
    return trace


def test_lineups(rom):
    table = rom[0x3FD90:0x3FD90 + 32 * 9]
    for team in range(32):
        row = table[team * 9:(team + 1) * 9]
        assert sorted(value & 15 for value in row) == list(range(1, 10)), team
        assert len({value >> 4 for value in row}) == 9, team
    varied = bytes((((team + slot * 5) % 16) << 4) | ((slot * 2 + team) % 9 + 1)
                   for team in range(32) for slot in range(9))
    for rows in (table, varied):
        for team in range(32):
            for side in (0, 1):
                cpu = machine(rom)
                memory = cpu.memory
                memory[0xFD80:0xFEA0] = rows
                memory[0x06D0:0x0710] = [(addr * 13 + side) & 0xFF
                                       for addr in range(0x06D0, 0x0710)]
                for selected in (team, (team + 13) % 32):
                    memory[0x04EF + side] = selected
                    memory[0x09] = 0xA5
                    cpu.x = side
                    cpu.p = (cpu.p & ~1) | (team & 1)
                    before = memory[0x06D0:0x0710]
                    expected = before[:]
                    expected[0x12 + side:0x24:2] = rows[selected * 9:selected * 9 + 9]
                    memory.writes.clear()
                    call(cpu, 0xAD42)
                    assert memory[0x06D0:0x0710] == expected, (selected, side)
                    writes = [(addr, value) for addr, value in memory.writes
                              if 0x06D0 <= addr < 0x0710]
                    assert writes == [(0x06E2 + side + 2 * slot, rows[selected * 9 + slot])
                                      for slot in range(9)], (selected, side, writes)
                    assert memory[0x09] == side, (selected, side, memory[0x09])
                    assert cpu.x == 0x12 + side
                    cpu.x = side
                    call(cpu, 0xB0BE)
                    assert cpu.x < 0x12 + side
                    assert memory[0x06E2 + cpu.x] & 15 == 1
    print("lineups: 32 teams x 2 sides x stock/varied rows, repeated copies, scores and $09 OK")


def test_pitcher(rom):
    for side in (0, 1):
        cpu = machine(rom)
        memory = cpu.memory
        team = 31 if side else 0
        roster = 0x6000 + side * 0x200
        memory[0x04EE] = side
        memory[0x04EF + side] = team
        memory[0x7F00 + team * 2:0x7F02 + team * 2] = [roster & 0xFF, roster >> 8]
        memory[0x0749 + side] = 3
        memory[0xE8] = 0xA5
        memory[0x06E2:0x0700] = [0xCC] * 30
        for start in (0x0689, 0x058D, 0x059B, 0x05A9, 0x05B7):
            memory[start:start + 9] = [0xCC] * 9
        expected = {start: [0xCC] * 9 for start in (0x0689, 0x058D, 0x059B, 0x05A9, 0x05B7)}
        for slot in range(9):
            player = (slot * 5 + side) % 16
            position = (slot * 2 + side) % 9
            memory[0x06E2 + slot * 2 + side] = (player << 4) | (position + 1)
            attr = ((player % 4) << 6) | ((player * 3) % 16)
            memory[roster + player * 16 + 10] = attr
            skill = min((attr & 15) + 3, 15)
            field = (((skill << 3) & 0x60) | ((attr >> 3) & 0x18)) or 8
            stance = 2 if position == 2 else 6
            for start, value in ((0x0689, skill), (0x058D, field), (0x059B, field),
                                 (0x05A9, stance), (0x05B7, stance | field)):
                expected[start][position] = value
        before = memory[0x06E2:0x0700]
        trace = call(cpu, 0xAD5C)
        assert trace.count(0xAD63) == 9, trace
        assert memory[0xE8] == 0xA5
        assert memory[0x06E2:0x0700] == before
        for start, values in expected.items():
            assert memory[start:start + 9] == values, (side, hex(start))
    print("pitcher: stock $AD5C reaches $AD63 nine times, attributes, $E8 and return stack OK")


def test_rows(rom):
    for length in (0, 1, 4):
        for mode in (0, 1):
            for cursor in (0, 0x20, 0xFF):
                cpu = machine(rom)
                memory = cpu.memory
                memory[0:8] = [0x34, 0x21, 0, 0x60, 0x73, length, mode, 0xA5]
                memory[0x0300:0x0500] = [0xCC] * 0x200
                memory[0x6000:0x6100] = [(value * 5 + 17) & 0xFF for value in range(256)]
                memory[0x6100:0x6200] = [(value * 7 + 83) & 0xFF for value in range(256)]
                glyphs = [0x02, 0x11, 0x3D, 0x61]
                memory[0x06B5:0x06B9] = glyphs
                data = [0x61, 0x34, length * (1 if mode else 2)] if length else []
                for glyph in glyphs[:length]:
                    index = glyph | (0x80 if mode else 0)
                    data.append(memory[0x6000 + index])
                    if not mode:
                        data.append(memory[0x6100 + index])
                expected = memory[0x0300:0x0500]
                writes = [(0x0300 + ((cursor + i) & 0xFF), value)
                          for i, value in enumerate(data)]
                for addr, value in writes:
                    expected[addr - 0x0300] = value
                cpu.x = cursor
                memory.writes.clear()
                call(cpu, 0xC790)
                assert memory[0x0300:0x0500] == expected, (length, mode, cursor)
                assert [(addr, value) for addr, value in memory.writes
                        if 0x0300 <= addr < 0x0500] == writes
                assert cpu.x == (cursor + len(data)) & 0xFF
                assert memory[0x04] == (length if length else 0x73)
                assert memory[0x07] == (0 if length else 0xA5)
                if cursor == 0:
                    memory[0x32] = cpu.x
                    memory.writes.clear()
                    call(cpu, 0xC53A)
                    assert [value for addr, value in memory.writes if addr == 0x2007] == data[3:]
                    assert memory[0x32] == 0
    print("rows: empty text emits no row or PPU writes; populated producer/consumer output OK")


def test_launch(rom):
    for sp in (0xFF, 0xFD, 0xCB, 0xB1, 0x80, 1, 0):
        cpu = machine(rom)
        cpu.sp = sp
        for _ in range(31):
            cpu.stPushWord(0x1234)
            cpu.x = 0
            cpu.pc = 0xFF90
            trace = run(cpu, 0xCC09)
            assert 0xFFB3 in trace
            assert cpu.sp == 0xFF, (sp, cpu.sp)
            assert cpu.x == 0xFF
            assert cpu.memory[0x27] == 5 and cpu.memory[0x2000] == 0x80
            cpu.memory[0x047D] = 1
            cpu.step()
            cpu.step()
            assert cpu.pc == 0xCC09 and cpu.sp == 0xFF
    print("launch: $FF90 resets SP to FF for seven starting stacks across 31 launches OK")


def test_builder(base, rom):
    assert isinstance(rom, bytes)
    assert hashlib.sha256(rom).hexdigest() == "deff2f62ab1dff112726846d12aed08b3d6e7fdbb39b7e5ae1d8fbca4b0a1b89"
    assert build_rom(base) == rom
    mutable = bytearray(base)
    assert build_rom(mutable) == rom and mutable == base
    allowed = ((0x12D52, 0x12D55), (0x13F50, 0x13F8A),
               (0x3C7A0, 0x3C7A4), (0x3FC00, 0x3FC0C), (0x3FFC3, 0x3FFC7))
    assert len(rom) == len(base)
    changed = {i for i, (old, new) in enumerate(zip(base, rom)) if old != new}
    assert changed == {i for start, end in allowed for i in range(start, end)}
    invalid = [base[:-1], base + b"\0", rom]
    for addr in (0, 4, 5, 6, 0x50000, *(start for start, _ in allowed)):
        damaged = bytearray(base)
        damaged[addr] ^= 1
        invalid.append(bytes(damaged))
    for damaged in invalid:
        try:
            build_rom(damaged)
        except ValueError:
            pass
        else:
            raise AssertionError("builder accepted a mismatched input")

    script = Path(__file__).with_name("build_gameplay32.py")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "direct31.nes"
        source.write_bytes(base)
        pair36 = directory / "direct31-pair36.nes"
        pair36.write_bytes(b"protected pair36")
        aliases = [source, pair36, directory / "missing" / ".." / "direct31.nes"]
        elsewhere = directory / "elsewhere"
        elsewhere.mkdir()
        pinned_copy = elsewhere / "pinned-copy.nes"
        pinned_copy.write_bytes(base)
        aliases.append(pinned_copy)
        for target in (source, pair36):
            symlink = directory / (target.stem + "-symlink.nes")
            symlink.symlink_to(target)
            hardlink = directory / (target.stem + "-hardlink.nes")
            os.link(target, hardlink)
            aliases.extend((symlink, hardlink))
        for output in aliases:
            result = subprocess.run([sys.executable, str(script), str(source), "-o", str(output)],
                                    capture_output=True, text=True)
            assert result.returncode != 0 and "protected input" in result.stderr, result
            assert source.read_bytes() == base and pair36.read_bytes() == b"protected pair36"
        output = directory / "gameplay32.nes"
        result = subprocess.run([sys.executable, str(script), str(source), "-o", str(output)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert output.read_bytes() == rom
        source.write_bytes(invalid[-1])
        output.write_bytes(b"existing output")
        result = subprocess.run([sys.executable, str(script), str(source), "-o", str(output)],
                                capture_output=True, text=True)
        assert result.returncode != 0 and output.read_bytes() == b"existing output"
    print("builder: exact five changed ranges, deterministic output, bad inputs and path aliases rejected OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned direct31.nes")
    ap.add_argument("--expected", type=Path, help="independent experimental control ROM")
    args = ap.parse_args()
    base = args.rom.read_bytes()
    rom = build_rom(base)
    test_lineups(rom)
    test_pitcher(rom)
    test_rows(rom)
    test_launch(rom)
    test_builder(base, rom)
    if args.expected:
        assert rom == args.expected.read_bytes(), "output differs from the experimental control ROM"
        print("experimental ROM: byte-identical OK")
    print(f"test_gameplay32: OK {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
