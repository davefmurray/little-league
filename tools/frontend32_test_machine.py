"""Shared CPU harness and stage checks for the draw32, pick32 and title32 suites.

Boot runs a ROM from RESET on tools/render_menu32.Machine, imported unchanged,
with three additions the stock front end needs:
  * controller 2 at $4017, strobed together with controller 1;
  * an approximate sprite-0 hit, set once the beam passes OAM[0]'s row with
    background and sprites on, because the stock title and attract wait for it;
  * a BIT $2002 poll may read a new vblank flag before the NMI is taken, as
    on hardware when the flag lands in the poll's last read cycle. Without it
    the stock attract sequencer stalls in this model.
It is a CPU timing model, not a cycle-exact PPU. Boot assumptions: MMC1
control $0C (PRG mode 3, last bank fixed) with PRG bank 0 at power-on, SP $FD,
and render_menu32's RAM and PRG RAM fill patterns, so nothing relies on
cleared memory.

Bus is a flat 64 KB bus for calling routines directly: fixed bank 15 at
$C000, a switchable bank at $8000 that MMC1 serial writes to $E000-$FFFF
switch, a vblank flag that always reads set, both controller ports and a log
of written addresses. It runs no NMI, so it cannot run the menu frame loop.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from py65.devices.mpu6502 import MPU

import password32v2
import render_menu32 as R
from build_draw32 import locate

A, B, START, DOWN, LEFT, RIGHT = R.A, R.B, R.START, R.DOWN, R.LEFT, R.RIGHT
SCENE = 0x047B
SERIES_RAM = (0x07ED, 0x07EF, 0x07FC, 0x07F0, 0x074B, 0x074C, 0x07F1, 0x07F2)
HEAP, SEED = 0x7700, 0x7760


def rejects(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except (ValueError, KeyError):
        return
    raise AssertionError(f"{getattr(call, '__name__', call)} accepted bad input")


class Boot(R.Machine):
    """Machine from RESET with controller 2, sprite 0, a logged RAM watch list and PC hooks."""

    def __init__(self, rom, pads=(None, None), watch=(SCENE,)):
        super().__init__(rom, pads[0])
        self.pad2 = pads[1] or (lambda frame: 0)
        self.pad2_bits = 0
        self.watch = set(watch)
        self.log = []                  # (frame, address, old, new, pc, prg) for watched RAM
        self.on_pc = {}                # pc -> callback(machine), run before that instruction
        self.control, self.prg = 0x0C, 0
        self.mpu.pc = self[0xFFFC] | self[0xFFFD] << 8
        self.mpu.sp = 0xFD

    def peek(self, addr, size=1):
        if 0x6000 <= addr < 0x8000:
            return bytes(self.wram[addr - 0x6000:addr - 0x6000 + size])
        return bytes(self.ram[addr & 0x7FF:(addr & 0x7FF) + size])

    def poke(self, addr, data):
        if 0x6000 <= addr < 0x8000:
            self.wram[addr - 0x6000:addr - 0x6000 + len(data)] = data
        else:
            self.ram[addr & 0x7FF:(addr & 0x7FF) + len(data)] = data

    def __getitem__(self, a):
        if a == 0x4017:
            if self.strobe:
                self.pad2_bits = self.pad2(self.frame)
                return 0x40 | (self.pad2_bits >> 7)
            bit = (self.pad2_bits >> 7) & 1
            self.pad2_bits = ((self.pad2_bits << 1) | 1) & 0xFF
            return 0x40 | bit
        return super().__getitem__(a)

    def __setitem__(self, a, v):
        if a < 0x2000 and (a & 0x7FF) in self.watch and self.ram[a & 0x7FF] != (v & 0xFF):
            self.log.append((self.frame, a & 0x7FF, self.ram[a & 0x7FF], v & 0xFF, self.pc, self.prg))
        if a == 0x4016 and v & 1:
            self.pad2_bits = self.pad2(self.frame)
        super().__setitem__(a, v)

    def rom_byte(self, a):
        """An opcode byte as the CPU would fetch it, without bus side effects."""
        a &= 0xFFFF
        if a < 0x2000:
            return self.ram[a & 0x7FF]
        if a < 0x8000:
            return 0
        return self.rom[R.HEADER + self.prg_bank(a) * 0x4000 + (a & 0x3FFF)]

    def ppu_read(self, reg):
        value = super().ppu_read(reg)
        if reg == 0x2002 and self.sprite0_hit():
            value |= 0x40
        return value

    def sprite0_hit(self):
        if self.vblank_start is None or (self.mask & 0x18) != 0x18:
            return False
        y, x = self.oam[0], self.oam[3]
        if y >= 0xEF:
            return False
        dt = self.write_cycle() - self.vblank_start
        return R.VBLANK + (y + 1) * 113.667 + x / 3 <= dt < R.FRAME

    def step(self):
        hook = self.on_pc.get(self.mpu.pc)
        if hook:
            hook(self)
        pc = self.mpu.pc
        if (self.pending_nmi and self.rom_byte(pc) == 0x2C and self.rom_byte(pc + 1) == 0x02
                and self.rom_byte(pc + 2) == 0x20):
            self.pending_nmi = False
            super().step()
            self.pending_nmi = True
            return
        super().step()


class Driver:
    """Live controller input for a booted machine, relative to its current frame."""

    def __init__(self, rom, watch=(SCENE,)):
        self.held = ({}, {})
        self.m = Boot(rom, (lambda f: self.held[0].get(f, 0), lambda f: self.held[1].get(f, 0)), watch)

    def press(self, buttons, port=0, hold=2, after=3, gap=6):
        table = self.held[port]
        for f in range(self.m.frame + after, self.m.frame + after + hold):
            table[f] = table.get(f, 0) | buttons
        self.m.frames(after + hold + gap)

    def wait(self, frames):
        self.m.frames(frames)

    def wait_scene(self, scene, limit=3000):
        m, start = self.m, self.m.frame
        m.run(lambda mm: mm.ram[SCENE] == scene or mm.frame - start > limit, limit=200_000_000)
        if m.ram[SCENE] != scene:
            raise AssertionError(f"scene {scene:02X} not reached; at {m.ram[SCENE]:02X}")


def to_mode_menu(rom, watch=(SCENE,), port=0):
    d = Driver(rom, watch)
    d.wait_scene(1)
    d.wait(30)
    d.press(START, port=port)
    d.wait_scene(7)
    d.wait(20)
    return d


def choose(d, mode, sub=None):
    """Mode menu: 0 Championship, 1 Exhibition, 2 Power Analysis; then a submenu row."""
    for _ in range(mode):
        d.press(DOWN)
    d.press(A)
    d.wait(30)
    if sub is not None:
        for _ in range(sub):
            d.press(DOWN)
        d.press(A)


class Bus:
    """Flat CPU bus for direct routine calls; see the module docstring."""

    def __init__(self, rom, bank, pads=(0, 0)):
        self.rom = rom
        self.mem = bytearray(0x10000)
        self.mem[0xC000:] = rom[locate(15, 0xC000):locate(15, 0xC000) + 0x4000]
        self.map(bank)
        self.pads, self.streams, self.port_reads = list(pads), [0, 0], [0, 0]
        self.serial = self.count = 0
        self.writes = set()

    def map(self, bank):
        self.bank = bank
        self.mem[0x27] = bank
        self.mem[0x8000:0xC000] = self.rom[locate(bank, 0x8000):locate(bank, 0x8000) + 0x4000]

    def __len__(self):
        return 0x10000

    def __getitem__(self, a):
        if isinstance(a, slice):
            return self.mem[a]
        if a == 0x2002:
            return 0x80
        if a in (0x4016, 0x4017):
            port = a - 0x4016
            self.port_reads[port] += 1
            bit = (self.streams[port] >> 7) & 1
            self.streams[port] = (self.streams[port] << 1) & 0xFF
            return 0x40 | bit
        return self.mem[a]

    def __setitem__(self, a, v):
        if isinstance(a, slice):
            self.mem[a] = v
            return
        v &= 0xFF
        if a >= 0x8000:
            if v & 0x80:
                self.serial = self.count = 0
                return
            self.serial |= (v & 1) << self.count
            self.count += 1
            if self.count == 5:
                if a >= 0xE000:
                    self.map(self.serial & 0x0F)
                self.serial = self.count = 0
            return
        if a == 0x4016 and v & 1:
            self.streams = list(self.pads)
        self.writes.add(a)
        self.mem[a] = v

    def peek(self, addr, size=1):
        return bytes(self.mem[addr:addr + size])

    def poke(self, addr, data):
        self.mem[addr:addr + len(data)] = data


def cpu(bus, sp=0xFF):
    mpu = MPU(memory=bus)
    mpu.sp = sp
    return mpu


def call(mpu, entry, limit=2_000_000, seen=None):
    """Run `entry` as a subroutine until it returns; the cycles it took."""
    ret = (R.STOP - 1) & 0xFFFF
    sp = mpu.sp
    mpu.memory[0x100 + mpu.sp] = ret >> 8
    mpu.memory[0x100 + ((mpu.sp - 1) & 0xFF)] = ret & 0xFF
    mpu.sp = (mpu.sp - 2) & 0xFF
    mpu.pc = entry
    start = mpu.processorCycles
    for _ in range(limit):
        if mpu.pc == R.STOP:
            assert mpu.sp == sp, f"${entry:04X} returned with an unbalanced stack"
            return mpu.processorCycles - start
        if seen is not None:
            seen.add((mpu.memory.bank if mpu.pc < 0xC000 else 15, mpu.pc))
        mpu.step()
    raise AssertionError(f"${entry:04X} did not return")


def run_to(mpu, entry, stop, bank=None, limit=2_000_000, seen=None):
    mpu.pc = entry
    for _ in range(limit):
        if mpu.pc == stop and (bank is None or mpu.memory.bank == bank):
            return
        if seen is not None:
            seen.add((mpu.memory.bank if mpu.pc < 0xC000 else 15, mpu.pc))
        mpu.step()
    raise AssertionError(f"${entry:04X} did not reach ${stop:04X}")


def series_image(series):
    """CPU address -> bytes of a live championship holding `series`."""
    mask = series.cpu_mask.to_bytes(4, "little")
    return {HEAP: bytes(0xFF if t is None else t for t in password32v2.heap(series)),
            SEED: series.draw_seed.to_bytes(2, "little"),
            0x07ED: b"\x01", 0x07EF: b"\x32", 0x07FC: bytes([series.played]), 0x07F0: b"\x00",
            0x074B: mask[:2], 0x07F1: mask[2:]}


def plant(memory, series):
    for addr, data in series_image(series).items():
        memory.poke(addr, data)


def series_state(memory):
    """The canonical series: heap, draw seed, markers, played, view flag and ownership mask."""
    return (memory.peek(HEAP, 0x3F), memory.peek(SEED, 2)) + tuple(memory.peek(a) for a in SERIES_RAM)


def title_tail(rom, series, port=0):
    """Plant `series`, then run the real post-game, title, START, mode-menu, password and CONTINUE code.

    The post-game routine $B63D runs with an exhibition finished ($04D0=1,
    $04E2=0), the result jingle over ($0401=$FF) and A newly pressed ($31).
    Each later step starts where the stock scene handler would. RESET's
    $CD20/$CD5C, which end a series, must never run on this path."""
    bus = Bus(rom, 4)
    mpu = cpu(bus)
    plant(bus, series)
    for addr, value in ((0x31, 0x80), (0x04D0, 1), (0x0401, 0xFF), (0x04E2, 0), (0xA7, 0), (0x07EE, 0)):
        bus.mem[addr] = value
    before, seen = series_state(bus), set()
    call(mpu, 0xB63D, seen=seen)
    assert bus.mem[SCENE] == 0 and series_state(bus) == before, "post-game did not return to the title intact"
    bus.map(0)
    bus.mem[0x32] = 0
    bus.mem[0x0470:0x0478] = b"\xFF" * 8
    call(mpu, 0xAC00, seen=seen)
    assert bus.mem[SCENE] == 1 and series_state(bus) == before, "title init changed the series"
    bus.mem[0x91], bus.mem[0x92] = (0x10, 0) if port == 0 else (0, 0x10)
    call(mpu, 0xACE9, seen=seen)
    assert bus.mem[SCENE] == 6, f"START on controller {port + 1} did not leave the title"
    bus.map(1)
    call(mpu, 0x9400, seen=seen)
    assert bus.mem[SCENE] == 7 and series_state(bus) == before, "mode menu init changed the series"
    bus.map(5)
    call(mpu, 0xFCE2, seen=seen)
    code = password32v2.encode(series)
    assert bus.peek(0x0643, 26) == password32v2.display(code) and bus.bank == 5, "password display differs"
    bus.map(1)
    mpu.sp = 0xFF
    run_to(mpu, 0x94F8, 0x8000, bank=11, seen=seen)
    assert bus.mem[0x07F0] == 0 and series_state(bus) == before, "CONTINUE changed the series"
    assert not {(15, 0xCD20), (15, 0xCD5C)} & seen, "the reset path ran"
    return code


def protected_targets(directory, rom_path, sources):
    """Output paths a stage CLI must refuse: the input, a renamed copy, sources, and links to them."""
    original = directory / rom_path.name
    original.write_bytes(rom_path.read_bytes())
    copy = directory / "renamed-input.nes"
    copy.write_bytes(rom_path.read_bytes())
    targets = [original, copy, *sources]
    for i, target in enumerate([original, *sources]):
        symbolic, hard = directory / f"alias{i}-symlink", directory / f"alias{i}-hardlink"
        symbolic.symlink_to(Path(target).resolve())
        os.link(target, hard)
        targets.extend((symbolic, hard))
    return original, targets


def check_output_guards(script, rom_path, rom, manifest, sources):
    """The stage CLI builds deterministically from another directory and refuses every protected target."""
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        original, targets = protected_targets(directory, rom_path, sources)
        command = [sys.executable, str(Path(script).resolve()), str(original), "-o"]
        output = directory / "out" / "stage.nes"
        output.parent.mkdir()
        for _ in range(2):
            result = subprocess.run(command + [str(output), "--manifest"], cwd=directory, capture_output=True,
                                    text=True)
            assert result.returncode == 0, result.stderr
            assert output.read_bytes() == rom, "CLI output differs from the deterministic build"
            assert json.loads(result.stdout) == manifest, "CLI manifest differs"
        for target in targets:
            before = Path(target).read_bytes()
            result = subprocess.run(command + [str(target)], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 2 and "output aliases protected" in result.stderr, (target, result.stderr)
            assert Path(target).read_bytes() == before, f"{target} changed"
        original.write_bytes(b"bad ROM")
        result = subprocess.run(command + [str(output)], cwd=directory, capture_output=True, text=True)
        assert result.returncode == 2 and "expected" in result.stderr, result.stderr
        assert output.read_bytes() == rom, "a rejected build replaced the output"
    return len(targets)


def check_builder(builder, base, rom, owned_banks, owned_chr=()):
    """Whole-region changes, an exact changed-byte manifest, and every input guard rejecting a one-bit drift."""
    changes = builder.change_manifest(base)
    regions = {r.name: r for r in builder.REGIONS}
    assert [c.name for c in changes] == list(regions), "changes and regions differ"
    claimed = set()
    for c in changes:
        region = regions[c.name]
        start = locate(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        assert (c.bank, c.addr, c.addr + len(c.after)) == (region.bank, region.start, region.end), c.name
        assert not span & claimed and base[start:start + len(c.before)] == c.before, c.name
        assert rom[start:start + len(c.after)] == c.after, c.name
        claimed |= span
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert len(base) == len(rom) and changed <= claimed, "a byte changed outside the claimed regions"
    report = builder.diff_manifest(base, rom)
    assert {i for r in report["ranges"] for i in r["changed_file_offsets"]} == changed, "manifest is not exact"
    assert report["input_sha256"] == builder.BASE_SHA256 and report["output_sha256"] == hashlib.sha256(rom).hexdigest()
    assert rom[:16] == base[:16], "header changed"
    for bank in range(16):
        if bank not in owned_banks:
            start = locate(bank, 0xC000 if bank == 15 else 0x8000)
            assert rom[start:start + 0x4000] == base[start:start + 0x4000], f"PRG bank {bank} changed"
    for bank in range(32):
        if bank not in owned_chr:
            start = locate("chr", bank * 0x1000)
            assert rom[start:start + 0x1000] == base[start:start + 0x1000], f"CHR ${bank:02X} changed"

    for index in (0, 4, 16, len(base) // 2, len(base) - 1):
        corrupt = bytearray(base)
        corrupt[index] ^= 1
        rejects(builder.build_rom, bytes(corrupt))
    rejects(builder.build_rom, base[:-1])
    rejects(builder.build_rom, base + b"\xFF")
    guards = [(label, bank, addr + len(bytes.fromhex(text)) // 2) for label, bank, addr, text in builder.DEPENDENCIES]
    guards += [(label, bank, addr + size // 2) for label, bank, addr, size, _ in builder.DIGESTS]
    guards += [(r.name, r.bank, (r.start + r.end) // 2) for r in builder.REGIONS]
    for label, bank, addr in guards:
        corrupt = bytearray(base)
        corrupt[locate(bank, addr)] ^= 1
        with patch.object(builder, "BASE_SHA256", hashlib.sha256(corrupt).hexdigest()):
            try:
                builder.build_rom(bytes(corrupt))
            except ValueError:
                continue
        raise AssertionError(f"{label}: a one-bit drift at ${addr:04X} was not caught")
    first = changes[0]
    for bad in (changes + (first,), changes[1:], (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=first.addr + 1),) + changes[1:], (replace(first, bank=9),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=b"", after=b""),) + changes[1:],
                (replace(first, before=bytes(len(first.before))),) + changes[1:]):
        with patch.object(builder, "change_manifest", return_value=bad):
            rejects(builder.build_rom, base)
    return len(changed), len(guards)
