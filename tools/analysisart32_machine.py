#!/usr/bin/env python3
"""CPU-model helpers for the analysisart32 stage: finished-card reconstruction for previews, and the
controller-driven runs its tests compare between the stockart32 input and a candidate.

card_frame runs the built card's own code for one team on frontend32_test_machine.Boot without the frame
loop: the prologue's sprite palette record, the hop pad and card() (each $04E6 wait released as the NMI's
short path would), numerals() and balls() at the team's final ratings. compose draws a frame with the
stock split: CHR $18 above the split row, CHR $06 below, sprites from CHR $1B.

Recorder is Boot with per-frame records (scene, loop state, $BC-$BF, the OAM page), the init's
$AF80/$AF94 marks, frame- and cycle-stamped mapper loads, a nametable snapshot when scene $15 starts,
and an optional extra NMI at one chosen instruction boundary. The run functions below take ROM bytes and
plain arguments and return plain data, so the test can run them in worker processes.

This is a CPU timing model, not a cycle-exact PPU: sprite-0 hit is manufactured from the beam position
and OAM, PPU fetches and open bus are not modelled, and pictures are composed from VRAM. It cannot prove
real-core split seams, transition frames or audio output.
"""
import copy
import hashlib

from PIL import Image

import analysisart32_assets as model
import build_analysisart32 as stage
from build_draw32 import read
from frontend32_test_machine import A, B, DOWN, SCENE, Boot, Driver, choose, plant, series_state, to_mode_menu
import menu32_convert as menu
import render_menu32 as R
import test_pick32 as pick

SPRITE_PALETTE_RECORD = 0x8A      # the scene $14 prologue's $C1A4 argument
PALETTE_LOADER = 0xC1A4
INIT, LOOP, RELEASE = 0xAF58, 0xAFA0, 0xAF94
REST, LEAVE = 100, 120            # frames after the A press: record the rest state, then press the exit key
KEYS = {"A": A, "B": B}
GUARDS = (0x2C, 0x2D, 0xAC, 0x32)



def wait_pcs(assets):
    """The two `LDA $04E6` instructions card() spins on, in bank 13."""
    _, labels = stage.far_code(assets)
    return labels["wait1"], labels["wait2"]


def card_frame(rom, team, assets, values=None):
    """(nametable 1 KB, palette 32, OAM 256) of team's finished card, from the built ROM's own routines; the
    assets only locate numerals(), balls() and the waits."""
    _, labels, _ = stage.home_code(assets)
    m = Boot(rom)
    m.mpu.sp = 0xEF
    m.map_bank(stage.HOME)
    m.ram[0x2C], m.ram[0x2D], m.ram[0x32], m.ram[0xAC], m.ram[0xAD] = 1, 0, 0, 0, 0x40
    m.ram[0x04EF] = team
    m.ram[0x0200:0x0300] = b"\xF0" * 256
    m.call(PALETTE_LOADER, a=SPRITE_PALETTE_RECORD)
    for pc in wait_pcs(assets):
        m.on_pc[pc] = lambda mm: mm.ram.__setitem__(0x04E6, mm.ram[0x2C]) if mm.prg == stage.FAR else None
    m.call(stage.PAD, a=0)
    if (m.prg, m.ram[0x27]) != (stage.HOME, stage.HOME):
        raise AssertionError(f"the hop pad returned in bank {m.prg}/{m.ram[0x27]}")
    m.call(labels["numerals"])
    m.ram[0xBC:0xC0] = bytes(values) if values is not None else read(rom, stage.HOME, model.RATINGS + 4 * team, 4)
    m.call(labels["balls"])
    palette = bytearray(m.ram[0x0195:0x01B5])
    for i in (16, 20, 24, 28):
        palette[i] = palette[0]
    return m.nametable(), bytes(palette), bytes(m.ram[0x0200:0x0300])


def compose(rom, nametable, palette, oam, split_row=model.SPLIT_ROW, top=model.TITLE_CHR, bottom=model.MODE_CHR,
            sprites=model.SPRITE_CHR):
    """A 256x240 RGB frame: background from `top` above the split row and `bottom` below, then 8x8 sprites
    in OAM order, a behind-background sprite hidden by opaque background."""
    banks = {b: read(rom, "chr", b * 0x1000, 0x1000) for b in {top, bottom, sprites}}
    cache = {}

    def grid(bank, tile):
        if (bank, tile) not in cache:
            cache[(bank, tile)] = menu.decode(banks[bank][16 * tile:16 * tile + 16])
        return cache[(bank, tile)]

    pixels, opaque = [], []
    for y in range(240):
        bank = top if y // 8 < split_row else bottom
        row, ink = [], []
        for x in range(256):
            v = grid(bank, nametable[32 * (y // 8) + x // 8])[y % 8][x % 8]
            p = model.attr_palette(nametable[960:], x // 8, y // 8)
            row.append(menu.NES_RGB[palette[4 * p + v] if v else palette[0]])
            ink.append(bool(v))
        pixels.append(row)
        opaque.append(ink)
    claimed = set()
    for s in range(64):
        y0, tile, attr, x0 = oam[4 * s:4 * s + 4]
        if y0 >= 0xEF:
            continue
        g = grid(sprites, tile)
        for dy in range(8):
            for dx in range(8):
                x, y = x0 + dx, y0 + 1 + dy
                v = g[7 - dy if attr & 0x80 else dy][7 - dx if attr & 0x40 else dx]
                if not v or x >= 256 or y >= 240 or (x, y) in claimed:
                    continue
                claimed.add((x, y))
                if attr & 0x20 and opaque[y][x]:
                    continue
                pixels[y][x] = menu.NES_RGB[palette[16 + 4 * (attr & 3) + v]]
    image = Image.new("RGB", (256, 240))
    image.putdata([p for row in pixels for p in row])
    return image



class Recorder(Boot):
    rec = None                 # per-visit records while armed
    inject = None              # predicate(machine, bank, pc): fire one extra NMI before that instruction
    fired = None

    def arm(self, press):
        self.rec = {"press": press, "frames": {}, "marks": {}, "maps": [], "entry_nametable": None,
                    "timeline": []}

    def bank_of(self, pc):
        return 15 if pc >= 0xC000 else self.prg_bank(pc) if pc >= 0x8000 else -1

    def step(self):
        rec, pc = self.rec, self.mpu.pc
        if self.inject is not None and not self.nmi_depth:
            bank = self.bank_of(pc)
            if self.inject(self, bank, pc):
                self.fired = {"pc": f"{pc:04X}", "exec_bank": bank, "physical": self.prg, "logical": self.ram[0x27],
                              "serial_count": self.count, "guard_2C": self.ram[0x2C], "guard_2D": self.ram[0x2D]}
                self.pending_nmi = True
                self.inject = None
        if rec is not None and not self.nmi_depth:
            if self.prg == stage.HOME and pc in (stage.HOOK, RELEASE) and pc not in rec["marks"]:
                rec["marks"][pc] = (self.frame, self.mpu.processorCycles)
            if pc == 0xCC14 and self.ram[SCENE] == 0x15:
                rec["timeline"].append((self.frame - rec["press"], self.ram[0xB8], bytes(self.ram[0xBC:0xC0])))
            if rec["entry_nametable"] is None and self.ram[SCENE] == 0x15:
                rec["entry_nametable"] = (self.frame - rec["press"], self.nametable())
        super().step()
        if rec is not None:
            offset = self.frame - rec["press"]
            if offset not in rec["frames"]:
                rec["frames"][offset] = (self.ram[SCENE], self.ram[0xB8], bytes(self.ram[0xBC:0xC0]),
                                         bytes(self.ram[0x0200:0x0300]))

    def __setitem__(self, a, v):
        before = len(self.mapper)
        super().__setitem__(a, v)
        if self.rec is not None and len(self.mapper) > before:
            offset = self.write_cycle() - self.vblank_start if self.vblank_start is not None else None
            self.rec["maps"].append((self.frame - self.rec["press"], offset, *self.mapper[-1]))


def ppu_state(m):
    """What a screen shows and maps: VRAM, palette, OAM, CHR banks, PPU control bits, shadows and split mode."""
    return {"nametable": m.nametable(), "palette": m.palette32(), "oam": bytes(m.oam), "chr": tuple(m.chr),
            "control": m.control, "ctrl": m.ctrl & 0x38, "mask": m.mask & 0x18, "shadows": bytes(m.ram[0x23:0x27]),
            "split": m.ram[0x047A], "scene": m.ram[SCENE]}


def rest_state(m):
    return {**ppu_state(m), "values": bytes(m.ram[0xBC:0xC0]), "state": m.ram[0xB8], "team": m.ram[0x04EF],
            "palette_buffer": bytes(m.ram[0x0195:0x01B5])}


def recorder(d):
    m = d.m
    m.__class__ = Recorder
    return m


def tour(rom, teams, keys):
    """Mode menu -> Power Analysis -> the shared picker; for each team: A, rest, exit key (A or B), back in the
    picker. Then B to the mode menu. An active v2 series is planted first."""
    d = to_mode_menu(rom, pick.WATCH)
    m = recorder(d)
    plant(m, pick.LIVE)
    before = series_state(m)
    choose(d, 2)
    pick.in_picker(d)
    out = {"picker_before": ppu_state(m), "visits": []}
    for team, key in zip(teams, keys):
        pick.move_to(d, team)
        press = m.frame + 3
        apu, queue, late, partial = len(m.apu), len(m.queue), len(m.vram_late), len(m.partial)
        m.arm(press)
        d.press(A, gap=0)
        d.wait(press + REST - m.frame)
        rest = rest_state(m)
        maps = len(m.rec["maps"])
        d.wait(4)
        rest_maps = m.rec["maps"][maps:]
        d.wait(press + LEAVE - 3 - m.frame)
        d.press(KEYS[key], gap=0)
        pick.in_picker(d)
        rec = m.rec
        m.rec = None
        out["visits"].append({
            "team": team, "key": key, "rest": rest, "rest_maps": rest_maps, "frames": rec["frames"],
            "marks": {f"{pc:04X}": mark for pc, mark in rec["marks"].items()}, "timeline": rec["timeline"],
            "entry_nametable": rec["entry_nametable"], "maps": rec["maps"],
            "apu": [(f - press, a, v) for f, a, v in m.apu[apu:]], "queue": [(f - press, v) for f, v in m.queue[queue:]],
            "late_ppu": len(m.vram_late) - late, "partial": m.partial[partial:], "cursor": pick.cursor(m),
            "series_ok": series_state(m) == before, "picker_after": ppu_state(m), "ram_after": bytes(m.ram),
            "wram_after": hashlib.sha256(bytes(m.wram)).hexdigest()})
    d.press(B)
    d.wait_scene(7)
    d.wait(20)
    out["mode_after"] = ppu_state(m)
    out["series_ok"] = series_state(m) == before
    return out



def entry_fixture(rom, team=0):
    """A Driver stopped at scene $14's first instruction ($AF58, bank 3) with an active series planted."""
    d = to_mode_menu(rom, pick.WATCH)
    recorder(d)
    plant(d.m, pick.LIVE)
    choose(d, 2)
    pick.in_picker(d)
    pick.move_to(d, team)
    d.press(A, gap=0)
    d.m.run(lambda mm: mm.prg == stage.HOME and mm.mpu.pc == INIT and not mm.nmi_depth, limit=50_000_000)
    return d


def from_fixture(fixture, rom, team, lead=0):
    """A copy of `fixture` running `rom` for `team`, its next vblank `lead` cycles later."""
    d = copy.deepcopy(fixture)
    m = d.m
    m.pad = lambda frame: d.held[0].get(frame, 0)
    m.pad2 = lambda frame: d.held[1].get(frame, 0)
    m.rom, m.chr_rom = rom, rom[R.HEADER + 16 * 0x4000:]
    m.ram[0x04EF] = team
    m.next_vblank += lead
    return d


def settle(d, frames=80):
    """Run into scene $15, `frames` more frames, then to the start of the next scene-$15 handler."""
    m = d.m
    d.wait_scene(0x15)
    d.wait(frames)
    m.run(lambda mm: mm.prg == stage.HOME and mm.mpu.pc == LOOP and not mm.nmi_depth, limit=50_000_000)
    return {"screen": (m.nametable(), m.palette32(), bytes(m.oam), bytes(m.ram[0x23:0x27]), m.ram[0x047A],
                       m.ram[0xB8], bytes(m.ram[0xBC:0xC0]), m.ram[SCENE]),
            "sp": m.mpu.sp, "physical": m.prg, "logical": m.ram[0x27], "serial": (m.shift, m.count),
            "control": m.control, "chr": tuple(m.chr), "guards": tuple(m.ram[a] for a in GUARDS),
            "series": series_state(m)}


def timing_case(fixture, rom, team, lead, key, held):
    """One phase fixture: optionally A held from scene $14's entry for 95 frames, the scene's frames, the exit
    key on a settled frame, the return to the picker."""
    d = from_fixture(fixture, rom, team, lead)
    m = d.m
    before = series_state(m)
    f0, apu, late, partial = m.frame, len(m.apu), len(m.vram_late), len(m.partial)
    m.arm(f0)
    if held:
        d.held[0].update({f: A for f in range(f0, f0 + 95)})
    d.wait_scene(0x15)
    f15 = m.frame
    d.wait(100)
    held_ok = m.ram[SCENE] == 0x15
    settled = settle(d, 0)
    d.press(KEYS[key])
    pick.in_picker(d)
    rec = m.rec
    m.rec = None
    return {"team": team, "lead": lead, "key": key, "held": held, "held_stays": held_ok, "scene15": f15 - f0,
            "marks": {f"{pc:04X}": (f - f0) for pc, (f, _) in rec["marks"].items()},
            "timeline": [(f + rec["press"] - f15, s, v) for f, s, v in rec["timeline"]],
            "apu": [(f - f0, a, v) for f, a, v in m.apu[apu:]], "settled": settled,
            "split_commits": [(f, off, pc, reg, v) for f, off, pc, reg, v in rec["maps"] if reg == 2],
            "late_ppu": len(m.vram_late) - late, "partial": m.partial[partial:], "cursor": pick.cursor(m),
            "series_ok": series_state(m) == before}


def timing_cases(base, rom, cases):
    fixture = entry_fixture(base)
    return [timing_case(fixture, rom, *case) for case in cases]



class Switch:
    """The instruction at `pc` of the stock PRG writer $C14C-$C167 during its `nth` switch from bank `old` to
    `new`: $C14E before $27 is stored, $C150 with $27 already the new bank and the guard $2D clear, $C152-$C162
    with 0-4 of the five serial bits written, $C165 switched with $2D still set."""

    def __init__(self, pc, old, new, nth=1):
        self.pc, self.old, self.new, self.nth, self.seen, self.armed = pc, old, new, nth, 0, False

    def __call__(self, m, bank, at):
        if bank == 15 and at == 0xC14E and m.prg == self.old and m.mpu.a == self.new:
            self.seen += 1
            self.armed = self.seen == self.nth
        if self.armed and bank == 15 and at == self.pc:
            self.armed = False
            return True
        return False


class At:
    def __init__(self, exec_bank, pc):
        self.exec_bank, self.pc = exec_bank, pc

    def __call__(self, m, bank, at):
        return bank == self.exec_bank and at == self.pc


class Window:
    """The k-th instruction executed between bank 3 `start` and `stop`, NMIs excluded; k = 0 only counts."""

    def __init__(self, start, stop, k=0):
        self.start, self.stop, self.k, self.inside, self.count = start, stop, k, False, 0

    def __call__(self, m, bank, at):
        if bank == stage.HOME and at == self.start:
            self.inside = True
        if bank == stage.HOME and at == self.stop:
            self.inside = False
        if not self.inside:
            return False
        self.count += 1
        return self.count == self.k


def window_length(fixture, rom, team, start, stop):
    d = from_fixture(fixture, rom, team)
    window = Window(start, stop)
    d.m.inject = window
    settle(d)
    return window.count


def injected(fixture, rom, team, site):
    """The settled state after one extra NMI at `site`, and where it fired."""
    d = from_fixture(fixture, rom, team)
    d.m.inject = site
    state = settle(d)
    return state, d.m.fired


def injection_runs(base, rom, team, named, windows):
    """Settled states: the uninjected reference, one extra NMI at each named site ("switch" or "at" with its
    arguments), and one at each sampled fraction of each (name, start, stop, fractions) window."""
    fixture = entry_fixture(base)
    reference = settle(from_fixture(fixture, rom, team))
    results = []
    for name, (kind, args) in named:
        state, fired = injected(fixture, rom, team, {"switch": Switch, "at": At}[kind](*args))
        results.append((name, state, fired))
    for name, start, stop, fractions in windows:
        length = window_length(fixture, rom, team, start, stop)
        for k in sorted({max(1, min(length, round(f * length))) for f in fractions}):
            state, fired = injected(fixture, rom, team, Window(start, stop, k))
            results.append((f"{name} instruction {k} of {length}", state, fired))
    return reference, results



def screens(rom, team=31):
    """Title, mode menu, both submenus and the picker; then a Power Analysis visit and, after it, the picker,
    the mode menu and the screens three more menu paths reach, each with its VRAM, CHR, palette and OAM."""
    out = {}
    d = Driver(rom)
    d.wait_scene(1)
    d.wait(30)
    out["title"] = ppu_state(d.m)
    d = to_mode_menu(rom, pick.WATCH)
    plant(d.m, pick.LIVE)
    before = series_state(d.m)
    d.wait(30)
    out["mode menu"] = ppu_state(d.m)
    d.press(A)
    d.wait(40)
    out["Championship submenu"] = ppu_state(d.m)
    d.press(B)
    d.wait(40)
    d.press(DOWN)
    d.press(A)
    d.wait(40)
    out["Exhibition submenu"] = ppu_state(d.m)
    d.press(B)
    d.wait(40)
    choose(d, 2)
    pick.in_picker(d)
    d.wait(20)
    out["picker"] = ppu_state(d.m)
    pick.move_to(d, team)
    d.press(A, gap=0)
    d.wait_scene(0x15)
    d.wait(100)
    d.press(B)
    pick.in_picker(d)
    d.wait(20)
    out["picker after analysis"] = ppu_state(d.m)
    d.press(B)
    d.wait_scene(7)
    d.wait(30)
    out["mode menu after analysis"] = ppu_state(d.m)
    for name, buttons in (("A after analysis", (A,)), ("then B, DOWN, A after analysis", (B, DOWN, A)),
                          ("then B, DOWN, A again after analysis", (B, DOWN, A))):
        for button in buttons:
            d.press(button)
            d.wait(20)
        d.wait(30)
        out[name] = ppu_state(d.m)
    out["series intact"] = series_state(d.m) == before
    return out
