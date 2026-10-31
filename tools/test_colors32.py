#!/usr/bin/env python3
"""CPU checks for Roster Lab team colors, run on ROMs the web editor exported.

    .venv/bin/python -B tools/test_colors32.py
    ROSTER_ROM32=build/homerunart32.nes \\
    ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \\
        .venv/bin/python -B tools/test_colors32.py

Every image comes from tools/web_colors_export.mjs, which calls web/rom.js
exactly as Roster Lab does. Nothing here patches a ROM by hand.

Always: a synthetic Preview 8 image is exported with a color edit, and the
palette routine that export wrote at $C6FE is run for every team id, both
sides, five banks and four status values.

With the ROMs (the color review's C1-C5): call-site census, every consumer's
palette destinations and bounded reads, the direct routine contract,
machine-state parity between the original and an upgraded copy whose teams
wear their old records, and the padding, RNG, simulation-reader and $C1A4
bounds around the reserved table. Without them it prints SKIPPED for that
part. It is a bounded CPU model: no NMI timing, PPU frame or emulator run.
Outputs go to a temporary directory; the source ROMs must stay unchanged.
"""
from collections import Counter
import hashlib
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from py65.devices.mpu6502 import MPU

TOOLS = Path(__file__).resolve().parent
HEADER, BANK = 16, 0x4000
SENT = 0x0200                       # RTS target pushed as $01FF
RAM_FILL = bytes((a * 29 + 0x53) & 255 for a in range(0x800))
P8_SHA = "a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b"
STOCK_SHA = "58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e"
SEEDED_SHA = "dbb5c3da49b1463290da4a77f42e0c34ce20487fdbd05cc1cd268455068dea6f"
VENEZUELA_SHA = "f861d9674507165d371676e431e05351b36045fedd5546fadd2fed8cb17521b2"
ROUTINE_SHARED = bytes.fromhex("b9ef04290f85050a650569c08504a000a9fa850560")
ROUTINE_OWN = bytes.fromhex("b9ef04291f85050a650569808504a000a9f3850560")
VENEZUELA = (0x16, 0x30, 0x38)

CONSUMERS = {
    "pregame": (1, 0xAF14, SENT),
    "ending-0": (5, 0xAD69, 0xAD7F),
    "ending-1": (5, 0xAD88, 0xAD7F),
    "ending-2": (5, 0xADA0, 0xAD7F),
    "ending-3": (5, 0xADBB, 0xAD7F),
    "field": (6, 0xD065, SENT),
}
COLOR_REGIONS = (range(0xFAC0, 0xFAF0), range(0xF379, 0xF400))
ALIAS_IDS = {0x2E, 0x2F, 0x30, 0x94, 0x95, 0x96}


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def fixed_bank(rom):
    return rom[4] - 1


def off(rom, bank, cpu):
    base = 0xC000 if bank == fixed_bank(rom) else 0x8000
    assert base <= cpu < base + BANK, (bank, hex(cpu))
    return HEADER + bank * BANK + cpu - base


def fixed(rom, cpu, n=1):
    o = off(rom, fixed_bank(rom), cpu)
    return bytes(rom[o:o + n])


class Bus:
    """A flat bus: RAM, a switchable bank at $8000 (MMC1 serial writes switch it), the fixed bank at $C000.

    Records ROM data reads by (bank, address), PPU writes through $2006/$2007, every RAM write and each
    caller of $C6FE.
    """

    def __init__(self, rom, bank):
        self.rom = rom
        self.fixed = fixed_bank(rom)
        self.mem = bytearray(0x10000)
        self.mem[:0x800] = RAM_FILL
        self.mem[0xC000:] = rom[off(rom, self.fixed, 0xC000):off(rom, self.fixed, 0xC000) + BANK]
        self.reads, self.writes, self.vram, self.calls = Counter(), [], {}, set()
        self.history, self.shift, self.count, self.latch, self.ppu = [], 0, 0, 0, 0
        self.cpu = None
        self.map(bank)

    def map(self, bank):
        self.bank = bank
        self.history.append(bank)
        self.mem[0x8000:0xC000] = self.rom[off(self.rom, bank, 0x8000):off(self.rom, bank, 0x8000) + BANK]

    def __getitem__(self, a):
        if a == 0x2002:
            self.latch = 0
            return 0x80
        if a >= 0x8000:
            self.reads[(self.fixed if a >= 0xC000 else self.bank, a)] += 1
            if a == 0xC6FE and self.cpu is not None and self.cpu.pc == a:
                sp = self.cpu.sp
                ret = self.mem[0x100 + ((sp + 1) & 255)] | self.mem[0x100 + ((sp + 2) & 255)] << 8
                self.calls.add((self.fixed if ret >= 0xC000 else self.bank, ret - 2))
        return self.mem[a]

    def __setitem__(self, a, v):
        if a >= 0x8000:
            if v & 0x80:
                self.shift = self.count = 0
                return
            self.shift |= (v & 1) << self.count
            self.count += 1
            if self.count == 5:
                if a >= 0xE000:
                    self.map(self.shift & (self.rom[4] - 1))
                self.shift = self.count = 0
            return
        if a == 0x2006:
            self.ppu = (v << 8 | self.ppu & 0xFF) if not self.latch else (self.ppu & 0xFF00 | v)
            self.latch ^= 1
        elif a == 0x2007:
            self.vram[self.ppu & 0x3FFF] = v
            self.ppu += 1
        self.writes.append((a, v))
        self.mem[a] = v


def run(rom, bank, entry, stop=SENT, a=0xA5, x=0x6B, y=0, p=0x24, setup=None, limit=200_000):
    bus = Bus(rom, bank)
    cpu = MPU(memory=bus)
    bus.cpu = cpu
    cpu.sp, cpu.a, cpu.x, cpu.y, cpu.p = 0xFF, a, x, y, p
    if setup:
        setup(bus.mem)
    cpu.stPushWord(SENT - 1)
    bus.writes.clear()
    cpu.pc = entry
    cpu.processorCycles = 0
    for _ in range(limit):
        if cpu.pc == stop:
            return bus, cpu
        assert cpu.pc >= 0x8000, f"ran into RAM at ${cpu.pc:04X} from ${entry:04X}"
        cpu.step()
    raise AssertionError(f"${entry:04X} did not reach ${stop:04X}")


def upload(bus, cpu):
    """Run the game's own palette upload ($CE5E) after a consumer; PPU $3F00-$3F1F."""
    bus.mem[0x01B5] = 1
    bus.vram.clear()
    cpu.sp = 0xFF
    cpu.stPushWord(SENT - 1)
    cpu.pc = 0xCE5E
    for _ in range(4000):
        if cpu.pc == SENT:
            return [bus.vram.get(0x3F00 + i) for i in range(32)]
        cpu.step()
    raise AssertionError("$CE5E did not return")


def export(source, output, case, synthetic=False):
    command = ["node", str(TOOLS / "web_colors_export.mjs")] + (["--synthetic"] if synthetic else []) + [str(source), str(output), case]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return Path(output).read_bytes()


# --- the direct routine contract ------------------------------------------------------------------------------

def direct(rom, team, side, bank, status):
    def setup(m):
        m[0x04EF + side], m[0x04EF + (1 - side)] = team, 7
    return run(rom, bank, 0xC6FE, y=side, p=status, setup=setup)


def check_direct(rom, table, count, cycles, a_exit, label, base=None):
    """Teams 0-31 x sides x banks x status values, then every id 32-255: pointer, cycles, registers, writes, bank."""
    cases = 0
    matrix = itertools.product(range(32), (0, 1), (1, 4, 5, 6, 11), (0x20, 0x21, 0x64, 0xE7))
    for team, side, bank, status in itertools.chain(matrix, itertools.product(range(32, 256), (0, 1), (5,), (0x24,))):
        bus, cpu = direct(rom, team, side, bank, status)
        pointer = bus.mem[4] | bus.mem[5] << 8
        assert pointer == table(team % count), (label, team, hex(pointer))
        assert cpu.processorCycles == cycles, (label, team, cpu.processorCycles)
        assert (cpu.a, cpu.x, cpu.y, cpu.sp) == (a_exit, 0x6B, 0, 0xFF), (label, team, cpu.a, cpu.x, cpu.y)
        assert {w for w, _ in bus.writes} <= {0x04, 0x05}, (label, team, bus.writes)
        assert bus.history == [bank], (label, bus.history)
        if base is not None:
            ref_bus, ref = direct(base, team, side, bank, status)
            assert (ref.p, ref.processorCycles, ref.x, ref.y) == (cpu.p, cpu.processorCycles, cpu.x, cpu.y), (label, team, status)
        cases += 1
    return cases


def check_synthetic():
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch) / "synthetic-preview8.nes"
        subprocess.run(["node", str(TOOLS / "web_colors_export.mjs"), "--fixture", "preview8", str(base)], check=True, stdout=subprocess.DEVNULL)
        source = base.read_bytes()
        rom = export(base, Path(scratch) / "synthetic-venezuela.nes", "venezuela", synthetic=True)
        assert base.read_bytes() == source, "the synthetic source changed"
    assert fixed(source, 0xC6FE, 21) == ROUTINE_SHARED and fixed(rom, 0xC6FE, 21) == ROUTINE_OWN
    changed = [i for i in range(len(rom)) if rom[i] != source[i]]
    assert changed == [off(rom, 15, a) for a in (0xC702, 0xC709, 0xC70F)] + list(range(off(rom, 15, 0xF380), off(rom, 15, 0xF3E0))), changed
    for t in range(32):
        want = VENEZUELA if t == 19 else fixed(source, 0xFAC0 + 3 * (t & 15), 3)
        assert fixed(rom, 0xF380 + 3 * t, 3) == bytes(want), t
    cases = check_direct(rom, lambda t: 0xF380 + 3 * t, 32, 32, 0xF3, "synthetic export", base=source)
    check_direct(source, lambda t: 0xFAC0 + 3 * t, 16, 32, 0xFA, "synthetic as built")
    print(f"synthetic: the editor's export changed only the 3 routine constants and the 96-byte table; "
          f"{cases} direct calls: 32 cycles, pointer $F380 + 3(t & 31), A=$F3 X kept Y=0, flags as built, writes only $04/$05")


# --- the full matrix on the real ROMs ---------------------------------------------------------------------------

def oracle(name, pair, bat, rec):
    """Palette-buffer destinations from the color review: the batting team is $04EF + $04ED."""
    a, b = rec(pair[0]), rec(pair[1])
    if name == "pregame":
        return {0x0196: a[0], 0x019A: a[1], 0x0197: b[0], 0x019E: b[1]}
    if name == "ending-0":
        return {0x019C: a[1], 0x01A0: a[2]}
    if name == "ending-1":
        return {0x01A0: b[1], 0x01A4: b[2]}
    if name == "ending-2":
        return {0x0197: a[1], 0x019B: a[1], 0x01A3: a[2]}
    if name == "ending-3":
        return {0x01A8: a[0], 0x01A7: a[1]}
    batting, fielding = (a, b) if bat == 0 else (b, a)
    return {0x01A8: batting[0], 0x01A7: batting[1], 0x01B0: batting[2], 0x01AC: fielding[0], 0x01AB: fielding[1]}


def consume(rom, name, pair, bat):
    bank, entry, stop = CONSUMERS[name]

    def setup(m):
        m[0x04EF], m[0x04F0] = pair
        m[0x04ED], m[0x04EE] = bat, 1 - bat
    return run(rom, bank, entry, stop=stop, setup=setup)


def check_consumers(label, rom, count, at):
    """C1/C2: every consumer, team, batting side and opponent: values, bounded reads and the upload."""
    rec = lambda t: fixed(rom, at(t), 3)
    calls, cases = set(), 0
    opponents = sorted({0, 1, count // 2 - 1, count // 2, count - 1})
    for name, t, bat, other in itertools.product(CONSUMERS, range(count), (0, 1), opponents):
        if other == t:
            continue
        for pair in ((t, other), (other, t)):
            bus, cpu = consume(rom, name, pair, bat)
            want = oracle(name, pair, bat, rec)
            assert {k: bus.mem[k] for k in want} == want, (label, name, pair, bat)
            reads = {a for (b, a) in bus.reads if b == fixed_bank(rom) and any(a in r for r in COLOR_REGIONS)}
            allowed = {at(x) + i for x in pair for i in range(3)}
            assert reads and reads <= allowed, (label, name, pair, sorted(map(hex, reads - allowed)))
            ram = bus.mem[0x0195:0x01B5]
            # The upload copies the buffer, putting the backdrop in each sprite palette's mirrored entry 0.
            expected = [ram[0] if i in (0x10, 0x14, 0x18, 0x1C) else ram[i] for i in range(32)]
            assert upload(bus, cpu) == expected, (label, name, pair, "the $CE5E upload carries the buffer")
            calls |= bus.calls
            cases += 1
    return calls, cases


def check_parity(base, rom):
    """C4: the upgraded copy whose teams wear their old records against the original, at every consumer exit."""
    cases = 0
    for name, t, bat, other in itertools.product(CONSUMERS, range(32), (0, 1), (0, 16, 31)):
        if other == t:
            continue
        pair = (t, other)
        a_bus, a = consume(base, name, pair, bat)
        b_bus, b = consume(rom, name, pair, bat)
        assert (a.a, a.x, a.y, a.sp, a.p, a.processorCycles) == (b.a, b.x, b.y, b.sp, b.p, b.processorCycles), (name, pair, bat)
        live = [i for i in range(0x800) if not 0x100 <= i <= 0x100 + a.sp]
        assert [i for i in live if a_bus.mem[i] != b_bus.mem[i]] in ([], [4], [5], [4, 5]), (name, pair, bat)
        assert a_bus.history == b_bus.history
        assert upload(a_bus, a) == upload(b_bus, b), (name, pair, bat)
        cases += 1
    return cases


def check_census(rom, expected):
    """C1: JSR $C6FE byte matches; no JSR or JMP into the routine's body outside known text."""
    jsr, body = set(), set()
    for bank in range(rom[4]):
        base = 0xC000 if bank == fixed_bank(rom) else 0x8000
        data = rom[off(rom, bank, base):off(rom, bank, base) + BANK]
        for i in range(len(data) - 2):
            target = data[i + 1] | data[i + 2] << 8
            if data[i] == 0x20 and target == 0xC6FE:
                jsr.add((bank, base + i))
            if data[i] in (0x20, 0x4C) and 0xC6FF <= target <= 0xC712:
                body.add((bank, base + i))
    assert jsr == expected, sorted(jsr ^ expected)
    assert body <= {(1, 0x9635)}, body
    return len(jsr)


def check_bounds(base, rom):
    """C5: the reserved table sits in padding no reader reaches; aliasing $C1A4 ids are never passed."""
    assert fixed(base, 0xF379, 0x87) == b"\xff" * 0x87, "the padding is $FF as built"
    assert fixed(rom, 0xF379, 7) == b"\xff" * 7 and fixed(rom, 0xF3E0, 0x20) == b"\xff" * 0x20, "padding outside the table stays free"
    assert max(fixed(base, 0xC4FA, 64)) <= 7
    rng = set()
    for state in range(256):
        rng.add(run(base, 6, 0xC46F, setup=lambda m, s=state: m.__setitem__(0x34, s))[1].a)
    assert rng <= set(range(8)), rng
    clamps = set()
    for low, high in itertools.product(range(256), range(0, 256, 4)):
        def setup(m, low=low, high=high):
            m[0x0516], m[0x0517] = low, high
        clamps.add(run(base, 6, 0xF166, setup=setup)[0].mem[0x01])
    assert clamps <= {8 * v for v in range(16)}, clamps
    assert fixed(base, 0xF19C, 6) == bytes.fromhex("c90f9002a90f") and max(fixed(base, 0xF1BF, 64)) <= 15
    seen = {}
    for entry, stop, cell, table in ((0xEF45, 0xEF51, 0x01, 0xF2C9), (0xEF56, 0xEF62, 0x00, 0xF309)):
        reads = set()
        for clamp, state in itertools.product(range(16), range(64)):
            def setup(m, clamp=clamp, state=state, cell=cell):
                m[cell], m[0x34] = 8 * clamp, state
            bus, _ = run(base, 6, entry, stop=stop, setup=setup)
            reads |= {a for (b, a) in bus.reads if b == fixed_bank(base) and table <= a < 0xF400}
        seen[table] = max(reads)
    reads = set()
    for group, first, second in itertools.product((0, 0x10, 0x20), range(8), range(8)):
        def setup(m, group=group):
            m[0x02] = group
        bus, _ = run(base, 6, 0xEF8D, stop=0xEF91, a=(second << 1 | first & 1) | group, setup=setup)
        reads |= {a for (b, a) in bus.reads if b == fixed_bank(base) and 0xF349 <= a < 0xF400}
    seen[0xF349] = max(reads)
    assert fixed(base, 0xEED3, 16) == bytes.fromhex("206fc48502 20aef2 2908 0502 aa bcb9f2".replace(" ", ""))
    seen[0xF2B9] = 0xF2B9 + (0x08 | 0x07)
    assert seen == {0xF2C9: 0xF308, 0xF309: 0xF348, 0xF349: 0xF378, 0xF2B9: 0xF2C8}, {hex(k): hex(v) for k, v in seen.items()}
    aliases = {}
    for label, image in (("as built", base), ("upgraded", rom)):
        hits = set()
        for palette_id in range(256):
            bus, _ = run(image, 5, 0xC1A4, a=palette_id)
            reads = {a for (b, a) in bus.reads if b == fixed_bank(image) and not 0xC1A4 <= a < 0xC1E5 and a < 0xFFF0}
            assert not reads & set(range(0xF379, 0xF400)), (label, hex(palette_id))
            if reads & set(range(0xFAC0, 0xFAF0)):
                hits.add(palette_id)
        aliases[label] = hits
    assert aliases == {"as built": ALIAS_IDS, "upgraded": ALIAS_IDS}, aliases
    passed = set()
    for bank in range(base[4]):
        origin = 0xC000 if bank == fixed_bank(base) else 0x8000
        data = base[off(base, bank, origin):off(base, bank, origin) + BANK]
        passed |= {data[i - 1] for i in range(2, len(data) - 2) if data[i:i + 3] == b"\x20\xa4\xc1" and data[i - 2] == 0xA9}
    tables = set(base[off(base, 5, 0xADD2):off(base, 5, 0xADD2) + 12])
    assert not (passed | tables) & ALIAS_IDS, sorted(map(hex, (passed | tables) & ALIAS_IDS))
    return len(passed)


def check_real(p8_path, stock_path):
    p8, stock = Path(p8_path).read_bytes(), Path(stock_path).read_bytes()
    assert sha(p8) == P8_SHA, f"{p8_path} is not the accepted Preview 8 ROM"
    assert sha(stock) == STOCK_SHA, f"{stock_path} is not the accepted 16-team ROM"
    with tempfile.TemporaryDirectory() as scratch:
        out = {case: export(p8_path, Path(scratch) / f"{case}.nes", case) for case in ("venezuela", "seeded", "distinct")}
        out["stock-distinct"] = export(stock_path, Path(scratch) / "stock-distinct.nes", "distinct")
    assert sha(out["venezuela"]) == VENEZUELA_SHA and sha(out["seeded"]) == SEEDED_SHA
    for t in range(32):
        assert fixed(out["distinct"], 0xF380 + 3 * t, 3) == bytes([(2 * t + 1) & 63, (2 * t) & 63, (t + 32) & 63])
    for t in range(16):
        assert fixed(out["stock-distinct"], 0xFAC0 + 3 * t, 3) == bytes([2 * t + 1, 2 * t, t + 32])

    p8_calls = {(1, 0x964D), (1, 0x9688), (1, 0xAF16), (1, 0xAF24), (5, 0xAD6B), (5, 0xAD8A), (5, 0xADA2), (5, 0xADBD),
                (7, 0x906D), (7, 0x9084), (15, 0xD06D), (15, 0xD084)}
    stock_calls = {(1, 0x964D), (1, 0x9688), (1, 0xAF16), (1, 0xAF24), (5, 0xAD6B), (5, 0xAD8A), (5, 0xADA2), (5, 0xADBD),
                   (7, 0xD06D), (7, 0xD084)}
    matches = [check_census(img, p8_calls) for img in (p8, out["seeded"], out["distinct"])] + \
        [check_census(img, stock_calls) for img in (stock, out["stock-distinct"])]
    print(f"C1 census: {matches[0]} JSR $C6FE byte matches on Preview 8 and its exports, {matches[3]} on the 16-team ROM;"
          " the only JSR into the routine body is bank-1 menu text")

    live = {"p8": {(1, 0xAF16), (1, 0xAF24), (5, 0xAD6B), (5, 0xAD8A), (5, 0xADA2), (5, 0xADBD), (15, 0xD06D), (15, 0xD084)}}
    live["stock"] = {(b if b != 15 else 7, a) for b, a in live["p8"]}
    total = 0
    for label, image, count, at, callers in (
            ("as built", p8, 32, lambda t: 0xFAC0 + 3 * (t & 15), live["p8"]),
            ("seeded", out["seeded"], 32, lambda t: 0xF380 + 3 * t, live["p8"]),
            ("distinct", out["distinct"], 32, lambda t: 0xF380 + 3 * t, live["p8"]),
            ("16-team", stock, 16, lambda t: 0xFAC0 + 3 * t, live["stock"]),
            ("16-team distinct", out["stock-distinct"], 16, lambda t: 0xFAC0 + 3 * t, live["stock"])):
        calls, cases = check_consumers(label, image, count, at)
        assert calls == callers, (label, sorted(calls ^ callers))
        total += cases
    print(f"C2 consumers: {total} runs over 5 images; all 8 live callers reached on each; values match the review's "
          "destination table (batting side $04ED owns field slot 2); reads stay in the two teams' records; $CE5E uploads carry the buffer")

    direct_cases = check_direct(out["seeded"], lambda t: 0xF380 + 3 * t, 32, 32, 0xF3, "seeded", base=p8)
    direct_cases += check_direct(out["distinct"], lambda t: 0xF380 + 3 * t, 32, 32, 0xF3, "distinct", base=p8)
    direct_cases += check_direct(p8, lambda t: 0xFAC0 + 3 * t, 16, 32, 0xFA, "as built")
    for team in range(16):
        bus, cpu = direct(stock, team, 0, 4, 0x24)
        assert (bus.mem[4] | bus.mem[5] << 8) == 0xFAC0 + 3 * team and cpu.processorCycles == 34
    print(f"C3 direct: {direct_cases} calls; upgraded 32 cycles, pointer $F380 + 3(t & 31) for every id 0-255, "
          "A=$F3 X kept Y=0, flags equal the original's, writes only $04/$05, bank unchanged; original $FAC0 + 3(t & 15); 16-team 34 cycles")

    print(f"C4 parity: {check_parity(p8, out['seeded'])} consumer exits; registers, flags and cycles identical to the original, "
          "RAM differs only at $04/$05, same uploads and banks")

    immediates = check_bounds(p8, out["seeded"])
    print(f"C5 bounds: $F379-$F3FF is $FF as built and only $F380-$F3DF changes; RNG $C46F gives 0-7 for every state; "
          f"readers end at $F2C8/$F308/$F348/$F378; ids $2E-$30 and $94-$96 alias $FAC0 and none reads $F379-$F3FF; "
          f"none of the {immediates} distinct immediate ids or the bank-5 id tables aliases")
    assert Path(p8_path).read_bytes() == p8 and Path(stock_path).read_bytes() == stock, "a source ROM changed"
    print("source ROMs unchanged; exports were written only to a temporary directory")


def main():
    check_synthetic()
    p8_path, stock_path = os.environ.get("ROSTER_ROM32"), os.environ.get("ROSTER_ROM16")
    if not (p8_path and stock_path):
        print("SKIPPED real-ROM matrix: set ROSTER_ROM32 and ROSTER_ROM16 to the accepted ROMs")
        return
    check_real(p8_path, stock_path)


if __name__ == "__main__":
    main()
