#!/usr/bin/env python3
"""Execute visual-table consumers on the MMC1/PPU CPU harness.

    python tools/test_visualtables32.py build/teamnames32.nes --candidate build/visualtables32.nes

The input must reproduce all three defects. Oracles inspect rendered font
tiles, OAM visibility and palette writes made by the original consumers.
The inherited harness flushes display lists through $C53A. It does not
execute NMI timing, emulate a PPU frame or validate hardware/audio behavior.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import build_visualtables32 as builder
from build_visualtables32 import build_rom, change_manifest, off, protect_output
from test_teamnames32 import Bus, Probe, RAM_FILL, SENTINEL, side_pair, snapshot

UNIFORMS = (
    (0x05, 0x20, 0x0F), (0x26, 0x20, 0x38), (0x02, 0x22, 0x38), (0x1B, 0x2B, 0x0F),
    (0x12, 0x20, 0x0F), (0x15, 0x11, 0x38), (0x11, 0x15, 0x38), (0x00, 0x10, 0x38),
    (0x14, 0x12, 0x0F), (0x15, 0x15, 0x0F), (0x15, 0x25, 0x0F), (0x05, 0x26, 0x0F),
    (0x18, 0x28, 0x38), (0x11, 0x31, 0x0F), (0x09, 0x27, 0x38), (0x0A, 0x2B, 0x38),
)
FLAG_ENTRIES = ((0xCB56, 3), (0xCB52, 4))
OAM_FILL = RAM_FILL[0x200:0x300]
PALETTE_CONSUMERS = {
    "pregame": (1, 0xAF14, SENTINEL),
    "ending-a": (5, 0xAD69, 0xAD7F),
    "ending-b": (5, 0xAD88, 0xAD7F),
    "ending-c": (5, 0xADA0, 0xAD7F),
    "ending-d": (5, 0xADBB, 0xAD7F),
    "field": (6, 0xD065, SENTINEL),
}
PALETTE_CALLS = {
    (1, 0xAF16), (1, 0xAF24), (5, 0xAD6B), (5, 0xAD8A),
    (5, 0xADA2), (5, 0xADBD), (15, 0xD06D), (15, 0xD084),
}


class VisualBus(Bus):
    def __init__(self, rom, bank):
        super().__init__(rom, bank)
        self.reads = Counter()
        self.palette_calls = set()
        self.flag_calls = []
        self.cpu = None

    def __getitem__(self, a):
        if not isinstance(a, slice) and a >= 0x8000:
            self.reads[(15 if a >= 0xC000 else self.bank, a)] += 1
            if self.cpu is not None and self.cpu.pc == a:
                if a == 0xC6FE:
                    sp = self.cpu.sp
                    ret = self.mem[0x100 + ((sp + 1) & 255)]
                    ret |= self.mem[0x100 + ((sp + 2) & 255)] << 8
                    self.palette_calls.add((15 if ret >= 0xC000 else self.bank, ret - 2))
                elif a == 0xCB63:
                    self.flag_calls.append((self.cpu.x, self.mem[0x00], self.mem[0x047F]))
        return super().__getitem__(a)


class VisualProbe(Probe):
    def __init__(self, rom, bank):
        super().__init__(rom, bank)
        bus = VisualBus(rom, bank)
        bus.mem = self.cpu.memory.mem
        bus.cpu = self.cpu
        self.cpu.memory = bus


def round_name(played):
    if played < 16:
        return b"1ST ROUND"
    if played < 24:
        return b"2ND ROUND"
    if played < 28:
        return b"QUARTER FINALS"
    if played < 30:
        return b"SEMI FINALS"
    return b"FINALS"


def matchup(rom, played, team=5, side=0, other=9, guard=(1, 0x32), legacy=0):
    p = VisualProbe(rom, 5)
    m = p.m
    m[0x07FA], m[0x07FB] = side_pair(team, side, other)
    m[0x07ED], m[0x07EF] = guard
    m[0x07FC], m[0x0746], m[0x047C] = played, legacy, 2
    for a in (0x074B, 0x074C, 0x07F1, 0x07F2):
        m[a] = 0xFF
    p.run(0x9BFA)
    assert m[0x0746] == legacy
    assert (m[0x07ED], m[0x07EF], m[0x07FC]) == (*guard, played)
    assert not any(a in (0x0746, 0x07ED, 0x07EF, 0x07FC) for a, _ in p.cpu.memory.writes)
    return p


def assert_label(p, played, base):
    text = round_name(played)
    assert p.texts[0] == ("bg", 0xA1, 0xC6, text, 5), (played, p.texts[0])
    for row, font in ((0, 0x8000), (1, 0x8200)):
        want = bytes(base[off(4, font + (c | 0x80))] for c in text)
        got = bytes(p.cpu.memory.vram.get(0x21C6 + 32 * row + i, 0xFF) for i in range(len(text)))
        assert got == want, (played, row, got.hex(), want.hex())


def flag_direct(rom, team, entry=0xCB56, bank=5, slot=0x10, y=0x30):
    p = VisualProbe(rom, bank)
    p.m[0x04], p.m[0x05], p.m[0x047F] = y, 0x40, slot
    p.cpu.x = team
    p.run(entry)
    return p


def assert_flag_reads(p, base):
    want = Counter()
    for team, rows, _ in p.cpu.memory.flag_calls:
        if team < 16:
            want[(4, 0x975A + team)] += 1
            offset = base[off(4, 0x975A + team)]
            want.update((4, a) for a in range(0x976A + offset, 0x976A + offset + 6 * rows))
    got = Counter({key: count for key, count in p.cpu.memory.reads.items()
                   if key[0] == 4 and 0x975A <= key[1] < 0x986A})
    assert got == want, (p.cpu.memory.flag_calls, got, want)


def hidden_footprint(p, slot, rows):
    indexes = {(slot + i) & 255 for i in range(12 * rows)}
    assert all(p.m[0x200 + i] == 0xF0 for i in indexes), (slot, rows)
    return indexes


def palette_direct(rom, team, side=0, bank=5, status=0x24):
    p = VisualProbe(rom, bank)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, 7)
    p.cpu.a, p.cpu.x, p.cpu.y, p.cpu.p = 0xA5, 0x6B, side, status
    p.run(0xC6FE)
    return p


def palette_consumer(rom, name, team, side, other=7):
    bank, entry, stop = PALETTE_CONSUMERS[name]
    p = VisualProbe(rom, bank)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.m[0x04ED], p.m[0x04EE] = side, 1 - side
    p.run(entry, stops=(stop,))
    return p


def palette_oracle(name, pair, side):
    a, b = (UNIFORMS[t % 16] for t in pair)
    if name == "pregame":
        return {0x0196: a[0], 0x019A: a[1], 0x0197: b[0], 0x019E: b[1]}
    if name == "ending-a":
        return {0x019C: a[1], 0x01A0: a[2]}
    if name == "ending-b":
        return {0x01A0: b[1], 0x01A4: b[2]}
    if name == "ending-c":
        return {0x0197: a[1], 0x019B: a[1], 0x01A3: a[2]}
    if name == "ending-d":
        return {0x01A8: a[0], 0x01A7: a[1]}
    if side:
        a, b = b, a
    return {0x01A8: a[0], 0x01A7: a[1], 0x01B0: a[2], 0x01AC: b[0], 0x01AB: b[1]}


def assert_palette_values(p, name, pair, side):
    want = palette_oracle(name, pair, side)
    assert {a: p.m[a] for a in want} == want, (name, pair, side, want)
    reads = {a for bank, a in p.cpu.memory.reads if bank == 15 and 0xFAC0 <= a < 0xFB4E}
    allowed = {0xFAC0 + 3 * (t % 16) + i for t in pair for i in range(3)}
    assert reads and reads <= allowed, (name, pair, reads, allowed)


def test_negative_controls(base):
    rounds = sum(matchup(base, played).texts[0][3] != round_name(played) for played in range(31))
    assert rounds == 15, rounds
    flags = []
    for entry, rows in FLAG_ENTRIES:
        bad = 0
        for team in range(16, 32):
            p = flag_direct(base, team, entry)
            visible = any(p.m[0x210 + 4 * i] < 0xEF for i in range(3 * rows))
            overread = any(bank == 4 and 0x976A <= a < 0x977A
                           for bank, a in p.cpu.memory.reads)
            assert visible and overread, (entry, team)
            bad += 1
        flags.append(bad)
    palettes = 0
    for team in range(16, 32):
        p = palette_consumer(base, "field", team, 0)
        want = palette_oracle("field", (team, 7), 0)
        assert any(p.m[a] != v for a, v in want.items()), team
        assert any(bank == 15 and 0xFAF0 <= a < 0xFB20 for bank, a in p.cpu.memory.reads), team
        palettes += 1
    print(f"negative input: {rounds}/15 later labels wrong; high flags visible/out of bounds {flags}; high palettes wrong/out of bounds {palettes}/16")


def test_rounds(base, rom):
    cases = 0
    for played in range(31):
        for side in range(2):
            for team in range(32):
                p = matchup(rom, played, team, side, (team + 17) % 32)
                assert_label(p, played, base)
                assert_flag_reads(p, base)
                assert p.cpu.memory.bank == 5 and p.cpu.sp == 0xFF
                assert 7 not in p.cpu.memory.history
                cases += 1
    for played in (0, 15, 16, 23, 24, 27, 28, 29, 30, 31, 0xFF):
        for legacy in (0, 7, 14, 15):
            p = matchup(rom, played, 16, 0, 31, guard=(0x80, 0x32), legacy=legacy)
            assert_label(p, played, base)
            assert_flag_reads(p, base)
            cases += 1
    print(f"rounds: {cases} full matchup executions, all 32 teams/both sides/all 31 positions; text and actual two-row font tiles correct; $0746 never written")


def test_round_write_bounds(base, rom):
    label_cells = {0x21C6 + 32 * row + i for row in range(2) for i in range(14)}
    for played in range(31):
        old, new = matchup(base, played, 16, other=31), matchup(rom, played, 16, other=31)
        a, b = old.cpu.memory, new.cpu.memory
        assert set(b.vram) - set(a.vram) <= label_cells, played
        old_writes = {addr for addr, _ in a.writes}
        new_writes = {addr for addr, _ in b.writes}
        allowed = set(range(0x100, 0x200)) | set(range(0x06B5, 0x06C3))
        assert new_writes - old_writes <= allowed, (played, new_writes - old_writes)
    print("round write bounds: new VRAM cells confined to the 14-column label; RAM writes stay within the stock set, dead stack and text buffer")


def test_stock_parity(base, rom):
    cases = 0
    guards = ((0, 0x32), (1, 0x16), (0, 0), (0x12, 0x31), (1, 0x33), (0x80, 0x20))
    for guard in guards:
        for legacy in range(16):
            for played in (0, 16, 24, 28, 30, 0xFF):
                a = matchup(base, played, guard=guard, legacy=legacy)
                b = matchup(rom, played, guard=guard, legacy=legacy)
                assert snapshot(a) == snapshot(b), (guard, legacy, played)
                cases += 1
    for team in range(16):
        for side in range(2):
            for other in range(16):
                if team == other:
                    continue
                a = matchup(base, 0, team, side, other)
                b = matchup(rom, 0, team, side, other)
                assert snapshot(a) == snapshot(b), (team, side, other)
                cases += 1
    print(f"matchup parity: {cases} exact live machine-state comparisons, including all 16 stock label indices and both mode guards")


def test_flags(base, rom):
    cases = 0
    for entry, rows in FLAG_ENTRIES:
        for team in range(32):
            for bank in (2, 3, 4, 5):
                for slot, y in ((0, 0x30), (4, 0x6C), (0x30, 0xE8), (0x98, 0x30), (0xF0, 0xE8)):
                    p = flag_direct(rom, team, entry, bank, slot, y)
                    bus, cpu = p.cpu.memory, p.cpu
                    assert bus.flag_calls == [(team, rows, slot)]
                    assert_flag_reads(p, base)
                    assert bus.history == [bank, 4, bank] and bus.bank == p.m[0x27] == p.m[0x2E] == bank
                    assert cpu.sp == 0xFF
                    if team < 16:
                        assert snapshot(p) == snapshot(flag_direct(base, team, entry, bank, slot, y)), (entry, team, bank, slot, y)
                    else:
                        footprint = hidden_footprint(p, slot, rows)
                        assert all(p.m[0x200 + i] == OAM_FILL[i] for i in range(256) if i not in footprint)
                        writes = [(a, v) for a, v in bus.writes if 0x200 <= a < 0x300]
                        assert len(writes) == 12 * rows and all(v == 0xF0 for _, v in writes)
                        assert (p.m[0], p.m[1], p.m[4], p.m[5], cpu.x) == (0, 0, (y + 8 * rows) & 255, 0x40, (slot + 12 * rows) & 255)
                        low = flag_direct(rom, team - 16, entry, bank, slot, y)
                        assert (cpu.a, cpu.p, cpu.sp) == (low.cpu.a, low.cpu.p, low.cpu.sp)
                        assert not bus.vram and not any(a == 0x4014 for a, _ in bus.writes)
                    cases += 1
    for entry, rows in FLAG_ENTRIES:
        for low_team in range(16):
            p = flag_direct(rom, low_team, entry)
            p.cpu.memory.reads.clear()
            p.cpu.memory.writes.clear()
            p.cpu.memory.flag_calls.clear()
            p.cpu.x = low_team + 16
            p.run(entry)
            hidden_footprint(p, 0x10, rows)
            assert_flag_reads(p, base)
            cases += 1
    print(f"flags: {cases} cases, both entry contracts, exact low parity, 36/48-byte hidden footprints including OAM wrap and low-to-high redraws; high paths read no flag data")


def test_flag_callers(base, rom):
    cases = 0
    entries = {
        "selector": (2, 0xBC2D, SENTINEL), "analysis": (3, 0xB1E2, SENTINEL),
        "ending-a": (5, 0xAAE7, 0xAB02), "ending-b": (5, 0xACDD, 0xACF0),
    }
    for name, (bank, entry, stop) in entries.items():
        for side in ((0, 1) if name == "selector" else (0,)):
            for team in range(32):
                probes = []
                for data in (base, rom):
                    p = VisualProbe(data, bank)
                    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, 7)
                    p.m[0xBB] = 2
                    p.cpu.x = side
                    p.run(entry, stops=(stop,))
                    probes.append(p)
                a, p = probes
                assert p.cpu.memory.flag_calls and p.cpu.memory.bank == bank
                assert_flag_reads(p, base)
                if team < 16:
                    assert snapshot(a) == snapshot(p), (name, side, team)
                else:
                    for actual_team, rows, slot in p.cpu.memory.flag_calls:
                        assert actual_team == team and rows == 3
                        hidden_footprint(p, slot, rows)
                cases += 1
    print(f"flag callers: {cases} selector/analysis/ending cases; both matchup sides covered by the round matrix")


def test_palettes(base, rom):
    direct, consumed, calls = 0, 0, set()
    for team in range(32):
        for side in range(2):
            for bank in (1, 4, 5, 6, 11):
                for status in (0x20, 0x21, 0x64, 0xE7):
                    p = palette_direct(rom, team, side, bank, status)
                    ptr = int.from_bytes(p.m[4:6], "little")
                    assert ptr == 0xFAC0 + 3 * (team % 16) and ptr + 2 < 0xFAF0
                    assert tuple(rom[off(15, ptr):off(15, ptr) + 3]) == UNIFORMS[team % 16]
                    assert (p.cpu.a, p.cpu.x, p.cpu.y, p.cpu.sp, p.cpu.memory.bank) == (0xFA, 0x6B, 0, 0xFF, bank)
                    assert p.cpu.memory.history == [bank]
                    if team < 16:
                        assert snapshot(p) == snapshot(palette_direct(base, team, side, bank, status)), (team, side, bank, status)
                    direct += 1
    for name in PALETTE_CONSUMERS:
        for side in range(2):
            for team in range(32):
                for other in (3, 19, 31):
                    p = palette_consumer(rom, name, team, side, other)
                    pair = side_pair(team, side, other)
                    assert_palette_values(p, name, pair, side)
                    assert 7 not in p.cpu.memory.history
                    calls.update(p.cpu.memory.palette_calls)
                    if team < 16 and other < 16:
                        assert snapshot(p) == snapshot(palette_consumer(base, name, team, side, other)), (name, team, side, other)
                    consumed += 1
    assert calls == PALETTE_CALLS, (calls, PALETTE_CALLS)
    print(f"palettes: {direct} pointer/register/bank cases and {consumed} actual consumer cases; all eight calls covered, expected donor colors and reads bounded to $FAC0-$FAEF; exact low parity")


def rejects(call, *args):
    try:
        call(*args)
    except ValueError:
        return
    raise AssertionError(f"invalid input accepted by {call.__name__}")


def test_builder(base, rom):
    assert len(base) == len(rom) == builder.ROM_SIZE
    assert base[:16] == rom[:16] == builder.HEADER
    assert rom[16 + 16 * builder.BANK:] == base[16 + 16 * builder.BANK:]
    owned = ((5, 0x9C42, 0x9C45), (5, 0xBE00, 0xBE80), (4, 0x9B00, 0x9B40),
             (15, 0xCB63, 0xCB66), (15, 0xC6FE, 0xC713))
    allowed = {i for bank, lo, hi in owned for i in range(off(bank, lo), off(bank, hi))}
    changes = change_manifest(base)
    claimed, changed = set(), {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    for c in changes:
        start = off(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        assert c.after and len(c.before) == len(c.after) and not span & claimed and span <= allowed
        assert base[start:start + len(c.before)] == c.before
        assert rom[start:start + len(c.after)] == c.after
        claimed.update(span)
    assert changed <= claimed
    report = builder.diff_manifest(base, rom)
    reported = {i for r in report["ranges"] for i in r["changed_file_offsets"]}
    assert reported == changed
    for bank, lo, hi in (
        (7, 0x8000, 0xC000), (1, 0xBC80, 0xC000), (4, 0x975A, 0x9B00),
        (4, 0xB700, 0xB780), (5, 0xBC80, 0xBD77), (5, 0x9C45, 0x9CAC),
        (11, 0x8000, 0x8700), (12, 0x8000, 0x9000), (15, 0xFB90, 0xFCC0),
        (15, 0xFCC0, 0xFD40), (15, 0xFD80, 0xFDA0), (15, 0xFEA0, 0xFEC9),
        (15, 0xFF14, 0xFF1C), (15, 0xFFC0, 0x10000), (15, 0xFAC0, 0xFAF0),
        (15, 0xF379, 0xF400),
    ):
        assert base[off(bank, lo):off(bank, hi)] == rom[off(bank, lo):off(bank, hi)], (bank, lo, hi)
    for index in (0, 4, 16, off(5, 0x9C42), off(5, 0xBE00), off(4, 0x9B00),
                  off(15, 0xCB63), off(15, 0xC6FE), off(15, 0xFFF4), len(base) - 1):
        corrupt = bytearray(base)
        corrupt[index] ^= 1
        rejects(build_rom, corrupt)
    rejects(build_rom, base[:-1])
    rejects(build_rom, base + b"\xFF")
    first = changes[0]
    for bad in (changes + (first,), changes[1:],
                (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=0xBFFF),) + changes[1:],
                (replace(first, bank=7),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=b"", after=b""),) + changes[1:],
                (replace(first, before=bytes(len(first.before))),) + changes[1:]):
        with patch.object(builder, "change_manifest", return_value=bad):
            rejects(build_rom, base)
    for bank, addr in ((11, 0x8500), (15, 0xFFF4), (15, 0xFAC0), (15, 0xCB52),
                       (5, 0x9C68), (5, 0x9C78), (5, 0xBE00), (4, 0x9B00), (15, 0xC6FE)):
        corrupt = bytearray(base)
        corrupt[off(bank, addr)] ^= 1
        with patch.object(builder, "BASE_SHA256", hashlib.sha256(corrupt).hexdigest()):
            rejects(build_rom, corrupt)
    print(f"ownership: exact manifest covers {len(changed)} changed bytes in five named ranges; bank7, fixed padding, CHR/art, original palettes/pointer and prior-stage reservations preserved")
    print("builder guards: exact input/header/size, reader/table/blank preimages, named reservations, overlaps and incomplete manifests rejected")


def test_output_guards(source, base, rom):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        original = directory / "input.nes"
        original.write_bytes(base)
        copied = directory / "renamed-teamnames.nes"
        copied.write_bytes(base)
        targets = [original, copied, Path(builder.__file__), Path(__file__),
                   builder.ROOT / "data/teams32.json", builder.ROOT / "data/roster32.json"]
        for label, target in (("rom", original), ("python", Path(builder.__file__)),
                              ("data", builder.ROOT / "data/teams32.json")):
            symbolic, hard = directory / f"{label}-symlink", directory / f"{label}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets.extend((symbolic, hard))
        names = ("direct31.nes", "direct31-pair36.nes", "gameplay32.nes", "cpu32.nes",
                 "teamtables32.nes", "roles32.nes", "results32.nes", "control32.nes",
                 "password32.nes", "teamnames32.nes")
        targets.extend(parent / name for parent in (builder.ROOT / "build", directory) for name in names)
        targets.append(builder.ROOT / "Little League Baseball - Championship Series (USA).nes")
        for target in targets:
            before = target.read_bytes() if target.is_file() else None
            rejects(protect_output, original, target)
            assert (target.read_bytes() if target.is_file() else None) == before
        prior = directory / "prior-copy.nes"
        marker, real_sha = b"prior ROM", hashlib.sha256
        prior.write_bytes(marker)
        for digest in builder.PROTECTED_SHA256:
            def fake_sha(data, _digest=digest):
                if data == marker:
                    return type("Digest", (), {"hexdigest": lambda self: _digest})()
                return real_sha(data)
            with patch.object(builder.hashlib, "sha256", side_effect=fake_sha):
                rejects(protect_output, original, prior)
            assert prior.read_bytes() == marker
        real_copies = 0
        for name in names:
            path = source.resolve().parent / name
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() in builder.PROTECTED_SHA256:
                prior.write_bytes(path.read_bytes())
                rejects(protect_output, original, prior)
                real_copies += 1
        script = Path(builder.__file__).resolve()
        output = directory / "candidate.nes"
        command = [sys.executable, str(script), str(original), "-o"]
        for _ in range(2):
            result = subprocess.run(command + [str(output), "--manifest"], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            assert output.read_bytes() == rom
            assert json.loads(result.stdout) == builder.diff_manifest(base, rom)
        for target in (original, targets[4], script, Path(__file__).resolve(), copied):
            before = target.read_bytes()
            result = subprocess.run(command + [str(target)], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 2 and "output aliases protected" in result.stderr, result
            assert target.read_bytes() == before
        original.write_bytes(b"bad ROM")
        result = subprocess.run(command + [str(output)], cwd=directory, capture_output=True, text=True)
        assert result.returncode == 2 and "expected teamnames32" in result.stderr
        assert output.read_bytes() == rom
    print(f"output/CLI guards: original/source/data/Python, symbolic/hard aliases, {len(builder.PROTECTED_SHA256)} prior hashes and {real_copies} real copies protected; deterministic build and exact JSON manifest from another cwd")


def test_consumer_audit(base):
    references = set()
    flags, rounds = set(), set()
    for bank in range(16):
        origin = 0xC000 if bank == 15 else 0x8000
        data = base[off(bank, origin):off(bank, origin) + builder.BANK]
        for i in range(len(data) - 2):
            if data[i:i + 3] == b"\x20\xFE\xC6":
                references.add((bank, origin + i))
            if data[i] in (0x20, 0x4C) and data[i + 1:i + 3] in (b"\x52\xCB", b"\x56\xCB"):
                flags.add((bank, origin + i, int.from_bytes(data[i + 1:i + 3], "little")))
            if data[i:i + 3] == b"\x20\x42\x9C":
                rounds.add((bank, origin + i))
    text_literals = {(1, 0x964D), (1, 0x9688)}
    duplicate_bank7 = {(7, 0x906D), (7, 0x9084)}
    assert references == PALETTE_CALLS | text_literals | duplicate_bank7, references
    assert flags == {(2, 0xBC41, 0xCB56), (3, 0xB1F2, 0xCB56), (5, 0x9D03, 0xCB56),
                     (5, 0xAAFF, 0xCB56), (5, 0xACED, 0xCB56)}, flags
    assert rounds == {(5, 0x9BFA)}, rounds
    print("consumer audit: eight live palette calls covered; two text-literal matches and two unchanged bank7 duplicates identified; flag consumers cover selector, analysis, matchup and both endings")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned teamnames32 input")
    ap.add_argument("candidate", type=Path, nargs="?")
    ap.add_argument("--candidate", dest="candidate_option", type=Path)
    args = ap.parse_args()
    if args.candidate and args.candidate_option:
        ap.error("specify the candidate once")
    started = time.monotonic()
    base = args.rom.read_bytes()
    rom = build_rom(base)
    candidate = args.candidate_option or args.candidate
    if candidate:
        assert candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    test_negative_controls(base)
    test_builder(base, rom)
    test_output_guards(args.rom, base, rom)
    test_consumer_audit(base)
    test_flags(base, rom)
    test_flag_callers(base, rom)
    test_palettes(base, rom)
    test_stock_parity(base, rom)
    test_rounds(base, rom)
    test_round_write_bounds(base, rom)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"visualtables32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
