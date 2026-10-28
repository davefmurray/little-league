#!/usr/bin/env python3
"""Execute all nine live text readers and verify the guarded display-name stage.

    .venv/bin/python tools/test_teamnames32.py build/password32.nes --candidate build/teamnames32.nes

The offline py65 bus models serial MMC1 PRG banking, PPU writes and OAM DMA.
Text is captured at the real background and sprite sinks. NMI timing is not
emulated; the display-list wait flushes through the real $C53A routine.
"""
import argparse
from copy import deepcopy
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

from py65.devices.mpu6502 import MPU

import build_teamnames32 as builder
from build_teamnames32 import (
    BANK, HIGH_CODES, HIGH_FULL, LONG_PTR, SHORT_PTR, SHORT_REGIONS,
    build_rom, change_manifest, load_teams, off, protect_output,
)

OUTPUT_SHA256 = "5998632da930ec063ea3029320a2b5d901043baa662add8adb8d14b809633f5c"

SENTINEL = 0x0200          # RTS target pushed as $01FF
RAM_FILL = bytes((a * 29 + 0x53) & 255 for a in range(0x800))
PRG_FILL = bytes((a * 7 + 3) & 255 for a in range(0x2000))


class Bus:
    def __init__(self, rom, bank):
        self.rom = rom
        self.mem = bytearray(0x10000)
        self.mem[0xC000:] = rom[off(15, 0xC000):off(15, 0xC000) + BANK]
        self.map(bank)
        self.shift = self.count = 0
        self.ppu_latch = 0
        self.ppu_addr = 0
        self.ppu_ctrl = 0
        self.vram = {}
        self.oam = bytearray(256)
        self.writes = []
        self.bank_reads = {}
        self.track_reads = False

    def map(self, bank):
        self.bank = bank
        self.history = getattr(self, "history", []) + [bank]
        self.mem[0x8000:0xC000] = self.rom[off(bank, 0x8000):off(bank, 0x8000) + BANK]

    def __getitem__(self, a):
        if isinstance(a, slice):
            return self.mem[a]
        if a == 0x2002:
            self.ppu_latch = 0
            return 0x80
        if self.track_reads and 0x8000 <= a < 0xC000:
            key = (self.bank, a)
            self.bank_reads[key] = self.bank_reads.get(key, 0) + 1
        return self.mem[a]

    def __setitem__(self, a, v):
        if isinstance(a, slice):
            self.mem[a] = v
            return
        if a >= 0x8000:
            if v & 0x80:
                self.shift = self.count = 0
                return
            self.shift |= (v & 1) << self.count
            self.count += 1
            if self.count == 5:
                if a >= 0xE000:
                    self.map(self.shift & 15)
                self.shift = self.count = 0
            return
        if a == 0x2000:
            self.ppu_ctrl = v
        elif a == 0x2006:
            if self.ppu_latch == 0:
                self.ppu_addr = (v << 8) | (self.ppu_addr & 0xFF)
            else:
                self.ppu_addr = (self.ppu_addr & 0xFF00) | v
            self.ppu_latch ^= 1
        elif a == 0x2007:
            self.vram[self.ppu_addr & 0x3FFF] = v
            self.ppu_addr = (self.ppu_addr + (32 if self.ppu_ctrl & 4 else 1)) & 0x3FFF
        elif a == 0x4014:
            self.oam[:] = self.mem[v << 8:(v << 8) + 256]
        self.writes.append((a, v))
        self.mem[a] = v


class Probe:
    def __init__(self, rom, bank, ram=None, track_reads=False):
        self.cpu = MPU(memory=Bus(rom, bank))
        self.cpu.memory.track_reads = track_reads
        m = self.cpu.memory.mem
        m[:0x800] = RAM_FILL if ram is None else ram
        m[0x6000:0x8000] = PRG_FILL
        m[0x27] = bank
        m[0x32] = 0                  # empty display list, as $C5C4 leaves it
        m[0x0300:0x0400] = bytes(256)
        self.cpu.a, self.cpu.x, self.cpu.y, self.cpu.p, self.cpu.sp = 0, 0, 0, 0x24, 0xFF
        self.texts = []
        self.nmi_flushes = 0

    @property
    def m(self):
        return self.cpu.memory.mem

    def _capture(self):
        m, pc = self.m, self.cpu.pc
        if pc == 0xC713:
            text = bytearray()
            for i in range(64):
                c = m[0x06B5 + i]
                if c >= 0xFE:
                    break
                text.append(c)
            self.texts.append(("bg", m[0x06B3], m[0x06B4], bytes(text), self.cpu.memory.bank))
        elif pc == 0xC892:
            text = bytearray()
            for i in range(64):
                c = m[0x06B6 + i]
                if c >= 0xFE:
                    break
                text.append(c)
            self.texts.append(("spr", m[0x06B3], m[0x06B4], bytes(text), m[0x06B5]))

    def run(self, entry, stops=(SENTINEL,), limit=300000, push_sentinel=True):
        cpu = self.cpu
        if push_sentinel:
            cpu.stPushWord(SENTINEL - 1)
        cpu.pc = entry
        stops = set(stops)
        for _ in range(limit):
            if cpu.pc in stops:
                return cpu.pc
            assert cpu.pc >= 0x8000, f"execution outside PRG ROM: ${cpu.pc:04X}"
            if cpu.pc in (0xC713, 0xC892):
                self._capture()
            if cpu.pc == 0xC26F and self.m[0x32]:
                cpu.stPushWord(0xC26F - 1)      # NMI stand-in: the NMI flushes via JSR $C53A
                cpu.pc = 0xC53A
                self.nmi_flushes += 1
                continue
            cpu.step()
        raise AssertionError(f"no stop: bank{cpu.memory.bank} PC=${cpu.pc:04X}")


def side_pair(team, side, other):
    return (team, other) if side == 0 else (other, team)


def matchup(rom, team, side=0, other=0, match_index=0, track_reads=False):
    p = Probe(rom, 5, track_reads=track_reads)
    m = p.m
    a, b = side_pair(team, side, other)
    m[0x07FA], m[0x07FB] = a, b
    m[0x0746] = match_index
    m[0x047C] = 2
    for addr in (0x074B, 0x074C, 0x07F1, 0x07F2):
        m[addr] = 0xFF
    p.run(0x9BFA, stops=(0x0200,))
    return p


def pregame(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 1, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.run(0xAF36)
    return p


def order(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 1, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.m[0xBD] = side
    p.run(0x99D2, stops=(0x99E4,), push_sentinel=False)
    return p


def field_hud(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 4, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.m[0x32] = 0
    p.run(0xB112, stops=(0xB12C,), push_sentinel=False)
    return p


def box_score(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 4, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.run(0xB597)
    return p


def team_select(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 2, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.cpu.x = side
    p.run(0xBC0B)
    return p


def power_analysis(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 3, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.run(0xB1D2)
    return p


def ending_short(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 5, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.run(0xAC85, stops=(0xAC95,), push_sentinel=False)
    return p


def ending_full(rom, team, side=0, other=0, track_reads=False):
    p = Probe(rom, 5, track_reads=track_reads)
    p.m[0x04EF], p.m[0x04F0] = side_pair(team, side, other)
    p.run(0xACCD, stops=(0xACDD,), push_sentinel=False)
    return p


READERS = {
    "matchup": matchup,
    "pregame": pregame,
    "order": order,
    "field_hud": field_hud,
    "box_score": box_score,
    "team_select": team_select,
    "power_analysis": power_analysis,
    "ending_short": ending_short,
    "ending_full": ending_full,
}


PICK = {
    "matchup": lambda side: 1 + side,      # [0] is the round label
    "pregame": lambda side: side,
    "order": lambda side: 0,
    "field_hud": lambda side: side,
    "box_score": lambda side: side,
    "team_select": lambda side: 0,
    "power_analysis": lambda side: 0,
    "ending_short": lambda side: 0,
    "ending_full": lambda side: 0,
}
SIDED = {"matchup", "pregame", "order", "field_hud", "box_score", "team_select"}
POS = {  # PPU header bytes ($06B3 high without flags, $06B4) per reader and side
    "matchup": [(0x21, 0x0A), (0x22, 0x8A)], "pregame": [(0x20, 0x41), (0x20, 0x52)],
    "order": [(0x20, 0x42)] * 2, "field_hud": [(0x21, 0x21), (0x21, 0x41)],
    "box_score": [(0x10, 0x4F), (0x10, 0x5F)], "team_select": [(0x20, 0x4A), (0x20, 0xCA)],
    "power_analysis": [(0x20, 0x68)] * 2, "ending_short": [(0x20, 0x42)] * 2,
    "ending_full": [(0x20, 0x48)] * 2,
}


def full_text(team, teams):
    name = teams[team]["name"].ljust(14)
    return (name + "    ", 0x80) if len(teams[team]["name"]) >= 12 else (name, 0x00)


def short_text(team, teams):
    n = teams[team]["name"]
    pad = (14 - len(n)) // 2
    return " " * pad + n + " " * (14 - pad - len(n))


def oracle(reader, team, side, teams):
    """Expected (flag bits of $06B3, text) for a high team."""
    hi, lo = POS[reader][side]
    if reader in ("matchup", "team_select", "power_analysis", "ending_full"):
        text, flag = full_text(team, teams)
        return ("bg", hi | flag, lo, text.encode())
    if reader == "pregame":
        return ("bg", hi | 0x80, lo, teams[team]["name"].ljust(14).encode())
    if reader in ("order", "ending_short"):
        return ("bg", hi, lo, short_text(team, teams).encode())
    if reader == "field_hud":
        return ("bg", hi | 0x40, lo, teams[team]["code"].ljust(5).encode())
    if reader == "box_score":
        return ("spr", hi, lo, teams[team]["code"].ljust(5).encode())
    raise KeyError(reader)


def snapshot(p):
    cpu, bus = p.cpu, p.cpu.memory
    ram = bytearray(bus.mem[:0x800])
    ram[0x100:0x100 + cpu.sp + 1] = bytes(cpu.sp + 1)        # dead stack below SP
    return (bytes(ram), bytes(bus.mem[0x6000:0x8000]), cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp,
            tuple(sorted(bus.vram.items())), bytes(bus.oam), bus.bank, tuple(p.texts),
            tuple((a, v) for a, v in bus.writes if a >= 0x2000))


def run(rom, reader, team, side, other, track_reads=False):
    return READERS[reader](rom, team, side=side, other=other, track_reads=track_reads)


def test_readers(base, rom, teams):
    cases = 0
    for reader in READERS:
        for side in ((0, 1) if reader in SIDED else (0,)):
            for team in range(32):
                opponents = {(team + 1) % 32, (team + 17) % 32,
                             0 if team else 1, 31 if team != 31 else 30}
                for other in sorted(opponents):
                    got = run(rom, reader, team, side, other).texts[PICK[reader](side)]
                    case = (reader, team, side, other)
                    if team >= 16:
                        assert got[:4] == oracle(reader, team, side, teams), (case, got)
                    else:
                        want = run(base, reader, team, side, other).texts[PICK[reader](side)]
                        assert got == want, (case, got, want)
                    cases += 1
    assert cases == 1845
    print(f"oracle: {cases} reader/team/side/opponent cases, 0 failures")


def test_low_parity(base, rom):
    cases = 0
    for reader in READERS:
        for side in ((0, 1) if reader in SIDED else (0,)):
            for team in range(16):
                for other in range(16):
                    if other == team:
                        continue
                    assert snapshot(run(base, reader, team, side, other)) == snapshot(
                        run(rom, reader, team, side, other)), (reader, team, side, other)
                    cases += 1
    assert cases == 3600
    print(f"parity: {cases} low-team cases compared on full machine state")


def test_write_bounds(rom):
    for reader in READERS:
        for side in ((0, 1) if reader in SIDED else (0,)):
            low_writes = set()
            for team in range(16):
                p = run(rom, reader, team, side, (team + 1) % 16)
                low_writes.update(a for a, _ in p.cpu.memory.writes)
            for team in range(16, 32):
                p = run(rom, reader, team, side, 0)
                extra = {a for a, _ in p.cpu.memory.writes} - low_writes
                extra = {a for a in extra if not 0x100 <= a <= 0x1FF}
                assert not extra, (reader, team, side, sorted(extra))
    print("writes: high-team RAM and I/O writes are within the low-team write set")


def test_read_banks(rom):
    data = [("full", HIGH_FULL, HIGH_FULL + 256), ("codes", HIGH_CODES, HIGH_CODES + 128),
            ("longptr", LONG_PTR, LONG_PTR + 64), ("shortptr", SHORT_PTR, SHORT_PTR + 64),
            ("short", 0xBEB0, 0xBF00), ("short", 0xBF20, 0xC000),
            ("stockfull", 0x9180, 0x9280), ("stockshort", 0x9280, 0x936E),
            ("stockcodes", 0x936E, 0x93EE), ("stocklong", 0xB2D6, 0xB37D)]
    expected = {
        "matchup": {"full"}, "pregame": {"longptr", "full"},
        "order": {"shortptr", "short"}, "field_hud": {"codes"},
        "box_score": {"codes"}, "team_select": {"full"},
        "power_analysis": {"full"}, "ending_short": {"shortptr", "short"},
        "ending_full": {"full"},
    }
    stock = {"stockfull", "stockcodes", "stocklong", "stockshort"}
    for reader in READERS:
        for side in ((0, 1) if reader in SIDED else (0,)):
            for team in range(16, 32):
                bus = run(rom, reader, team, side, 0, track_reads=True).cpu.memory
                assert 7 not in bus.history, (reader, team, side, "bank7 mapped")
                tags = {tag for bank, addr in bus.bank_reads for tag, lo, hi in data
                        if bank == 1 and lo <= addr < hi}
                assert tags - stock == expected[reader], (reader, team, side, tags)
                if team == 31 and side == 0:
                    spans = sorted(addr for bank, addr in bus.bank_reads
                                   if bank == 1 and any(lo <= addr < hi for _, lo, hi in data))
                    print(f"readbank {reader}: bank1 ${spans[0]:04X}-${spans[-1]:04X} {sorted(tags)}")


def test_negative_controls(base, teams):
    negative = {}
    for reader in READERS:
        bad = sum(run(base, reader, team, 0, 0).texts[PICK[reader](0)][:4]
                  != oracle(reader, team, 0, teams) for team in range(16, 32))
        negative[reader] = bad
    assert all(value == 16 for value in negative.values()), negative
    print(f"negative: base ROM high-team oracle failures per reader: {negative}")


def rejects(call, *args):
    try:
        call(*args)
    except ValueError:
        return
    raise AssertionError(f"invalid input accepted by {call.__name__}")


def test_builder(base, rom, teams):
    assert hashlib.sha256(base).hexdigest() == builder.BASE_SHA256
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256
    assert len(rom) == len(base) == builder.ROM_SIZE
    assert rom[:16] == base[:16] == builder.HEADER
    assert rom[16 + 16 * BANK:] == base[16 + 16 * BANK:]
    owned = (
        (1, 0xBC80, 0xBE40), (1, 0xBE70, 0xBF00), (1, 0xBF20, 0xC000),
        (15, 0xC966, 0xC968), (15, 0xC96B, 0xC96D), (15, 0xC9AA, 0xC9AC),
        (15, 0xCA27, 0xCA2B), (15, 0xCA2D, 0xCA2F), (15, 0xCA31, 0xCA33),
        (15, 0xFD20, 0xFD40), (4, 0x9A00, 0x9A1A),
        (4, 0xB11A, 0xB11F), (4, 0xB127, 0xB12C), (4, 0xB5B5, 0xB5BA),
    )
    allowed = {index for bank, start, end in owned for index in range(off(bank, start), off(bank, end))}
    manifest = change_manifest(base, teams)
    claimed = set()
    for change in manifest:
        start = off(change.bank, change.addr)
        span = set(range(start, start + len(change.after)))
        assert len(change.before) == len(change.after) and change.after
        assert not claimed & span and span <= allowed, change
        assert base[start:start + len(change.before)] == change.before
        assert rom[start:start + len(change.after)] == change.after
        claimed.update(span)
    changed = {i for i, (old, new) in enumerate(zip(base, rom)) if old != new}
    assert changed <= claimed and len(changed) == 700
    for bank, start, end in ((1, 0xBE40, 0xBE70), (1, 0xBF00, 0xBF20),
                             (1, 0x9180, 0x93EE), (15, 0xC998, 0xC9A8)):
        assert rom[off(bank, start):off(bank, end)] == base[off(bank, start):off(bank, end)]
    for new, old in ((LONG_PTR, 0xB2D6), (SHORT_PTR, 0x9280)):
        assert rom[off(1, new):off(1, new) + 32] == base[off(1, old):off(1, old) + 32]
    assert rom[off(15, 0xFD20):off(15, 0xFD30)] == base[off(15, 0xC998):off(15, 0xC9A8)]
    for offset in (0, 4, 16, off(1, 0xBC80), off(1, 0xBE70), off(1, 0xBE40),
                   off(1, 0xBF00), off(4, 0x9A00), off(15, 0xC966), off(15, 0xFD20), len(base) - 1):
        corrupt = bytearray(base)
        corrupt[offset] ^= 1
        rejects(build_rom, corrupt)
    rejects(build_rom, base[:-1])
    rejects(build_rom, base + b"\xff")
    first = manifest[0]
    invalid = (
        (first, first),
        (replace(first, after=first.after[:-1]),),
        (replace(first, before=b"", after=b""),),
        (replace(first, addr=0xBFFF),),
        (replace(first, bank=16),),
        (replace(first, before=bytes(len(first.before))),),
    )
    for changes in invalid:
        with patch.object(builder, "change_manifest", return_value=changes):
            rejects(build_rom, base)
    print("ownership: exactly 700 changed bytes within manifest; header, CHR, low names/flags, CONTINUE and bias preserved")
    print("input guards: pinned hash, size/header and manifest overlap, length, bank bounds and preimages enforced")


def test_metadata(base, teams):
    invalid = []
    for field, values in (
        ("name", ("", "A" * 15, " A", "A ", "A  B", "a", "É", "A\tB", "A\xff", None, 12)),
        ("code", ("", "A", "ABCD", "ab", "Ab", "A1", "A ", "ÉA", "ΔΑ", "ＡＢ", None, 12)),
    ):
        for value in values:
            bad = deepcopy(teams)
            bad[16][field] = value
            invalid.append(bad)
    for field in ("name", "code", "id"):
        bad = deepcopy(teams)
        del bad[16][field]
        invalid.append(bad)
    for value in (True, "16", 15, 32):
        bad = deepcopy(teams)
        bad[16]["id"] = value
        invalid.append(bad)
    rejects(builder.validate_teams, None)
    invalid.extend(({}, [], teams[:-1], teams + [teams[-1]], teams[::-1]))
    bad = deepcopy(teams)
    bad[16] = None
    invalid.append(bad)
    bad = deepcopy(teams)
    bad[0]["name"] = "OTHER"
    invalid.append(bad)
    for bad in invalid:
        rejects(build_rom, base, bad)
    cases = 0
    for length in (1, 11, 12, 13, 14):
        for code in ("AB", "XYZ"):
            custom = deepcopy(teams)
            for team in custom[16:]:
                team["name"], team["code"] = "A" * length, code
            candidate = build_rom(base, custom)
            assert len(candidate) == len(base)
            assert candidate[:16] == base[:16] and candidate[16 + 16 * BANK:] == base[16 + 16 * BANK:]
            for reader in READERS:
                for side in ((0, 1) if reader in SIDED else (0,)):
                    for team in range(16, 32):
                        got = run(candidate, reader, team, side, 0).texts[PICK[reader](side)][:4]
                        assert got == oracle(reader, team, side, custom), (length, code, reader, team, side, got)
                        cases += 1
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "teams.json"
        path.write_text(json.dumps({"teams": teams}))
        assert load_teams(path) == teams
        for data in ([], {}, {"teams": None}, {"teams": teams[:-1]}):
            path.write_text(json.dumps(data))
            rejects(load_teams, path)
    print(f"metadata: {len(invalid)} invalid records rejected; {cases} CPU cases at name lengths 1/11/12/13/14 and code lengths 2/3")


def test_output_guards(source, base):
    hashes = {
        "58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e",
        "338c1cc9bf80f6b77f441b472e91fd7536223d0b1b129fc8b7307ccb6f006327",
        "deff2f62ab1dff112726846d12aed08b3d6e7fdbb39b7e5ae1d8fbca4b0a1b89",
        "3ce7b8d849d46b7b0e4582750221237875f1db86a3388039b75a6d017aa76317",
        "d043ecdfc46c4d50c509db30f757425759a556dec3258be462fa9b3d81091ec1",
        "bf86fffd907718f72478733be63c5e3938446488205dbcee0a33b1138c28ea4c",
        "775595bef3506de25f704fe0530f6833d8ce0541155110920e739f19425cd006",
        "ddb83443653af408926d98843709e7831fed8fabd40f5e762db655c9a868431b",
        "9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b",
        "a1caf9a28e750a777343f2bdbd5c02987a03ccac0f58b6257e62dbee0faf30a8",
        "978abc4227eac24d0c779ea3fbbdfdc42c89ca0a1fcce350cff6db44501da34a",
    }
    assert builder.PROTECTED_SHA256 == hashes
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        original = directory / "input.nes"
        original.write_bytes(base)
        copied = directory / "renamed-password.nes"
        copied.write_bytes(base)
        targets = [original, copied, Path(builder.__file__), Path(__file__),
                   Path(__file__).with_name("password32_6502.py"), builder.TEAMS]
        for label, target in (("rom", original), ("python", Path(builder.__file__)),
                              ("metadata", builder.TEAMS)):
            symbolic, hard = directory / f"{label}-symlink", directory / f"{label}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets.extend((symbolic, hard))
        names = ("direct31.nes", "direct31-pair36.nes", "gameplay32.nes", "cpu32.nes",
                 "teamtables32.nes", "roles32.nes", "results32.nes", "control32.nes", "password32.nes")
        targets.extend(parent / name for parent in (builder.ROOT / "build", directory) for name in names)
        targets.append(builder.ROOT / "Little League Baseball - Championship Series (USA).nes")
        for target in targets:
            before = target.read_bytes() if target.exists() else None
            rejects(protect_output, original, target)
            assert (target.read_bytes() if target.exists() else None) == before
        marker = b"renamed prior-stage ROM"
        prior_copy = directory / "prior-copy.nes"
        prior_copy.write_bytes(marker)
        real_sha = hashlib.sha256
        for digest in hashes:
            def fake_sha(data, _digest=digest):
                if data == marker:
                    return type("Digest", (), {"hexdigest": lambda self: _digest})()
                return real_sha(data)
            with patch.object(builder.hashlib, "sha256", side_effect=fake_sha):
                rejects(protect_output, original, prior_copy)
            assert prior_copy.read_bytes() == marker
        real_copies = 1
        for name in names:
            prior = source.resolve().parent / name
            if prior.is_file() and hashlib.sha256(prior.read_bytes()).hexdigest() in hashes:
                prior_copy.write_bytes(prior.read_bytes())
                rejects(protect_output, original, prior_copy)
                real_copies += 1
        protect_output(original, directory / "new-output.nes")
        assert not (directory / "new-output.nes").exists()
    print(f"output guards: input, original ROM, metadata, Python, symbolic/hard aliases, 11 pinned hashes and {real_copies} real ROM copies protected")


def test_cli(base, rom):
    script = Path(builder.__file__).resolve()
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source, output = directory / "input.nes", directory / "output.nes"
        source.write_bytes(base)
        command = [sys.executable, str(script), str(source), "-o"]
        def invoke(target):
            return subprocess.run(command + [str(target)], cwd=directory, capture_output=True, text=True)
        for _ in range(2):
            result = invoke(output)
            assert result.returncode == 0, result.stderr
            assert OUTPUT_SHA256 in result.stdout and "700 bytes changed" in result.stdout
            assert output.read_bytes() == rom
        alias = directory / "alias.nes"
        alias.symlink_to(source)
        for target in (source, alias, script, Path(__file__).resolve(), builder.TEAMS):
            before = target.read_bytes()
            result = invoke(target)
            assert result.returncode == 2 and "output aliases protected" in result.stderr, result
            assert target.read_bytes() == before
        source.write_bytes(b"bad ROM")
        result = invoke(output)
        assert result.returncode == 2 and "expected password32" in result.stderr
        assert output.read_bytes() == rom
    print("CLI: source-relative metadata, deterministic rebuilds and rejected writes verified from another working directory")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path, help="pinned password32.nes")
    ap.add_argument("candidate", type=Path, nargs="?")
    ap.add_argument("--candidate", dest="candidate_option", type=Path)
    args = ap.parse_args()
    if args.candidate and args.candidate_option:
        ap.error("specify the candidate once")
    started = time.monotonic()
    base = args.rom.read_bytes()
    teams = load_teams()
    rom = build_rom(base)
    candidate = args.candidate_option or args.candidate
    if candidate:
        assert candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    print(f"base {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    for bad_entry in (0xAC84, 0xACCC):
        try:
            Probe(rom, 5).run(bad_entry, push_sentinel=False)
        except AssertionError as exc:
            assert "execution outside PRG ROM" in str(exc), exc
        else:
            raise AssertionError("operand-byte entry was accepted")
    print("execution guard: both misaligned ending probes fail before entering PPU mirror space")
    test_builder(base, rom, teams)
    test_metadata(base, teams)
    test_output_guards(args.rom, base)
    test_cli(base, rom)
    test_readers(base, rom, teams)
    test_low_parity(base, rom)
    test_write_bounds(rom)
    test_read_banks(rom)
    test_negative_controls(base, teams)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"teamnames32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
