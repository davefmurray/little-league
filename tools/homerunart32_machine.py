#!/usr/bin/env python3
"""CPU-model runs for tools/test_homerunart32.py: saved home-run states (tools/homerunart32_fixtures.py) replayed
on any ROM, a played WATCH game from RESET, and direct calls of the stock scoring, statistics and exit routines.

Each run returns plain data the suite judges: milestones with their frame and cycle count, per-frame scene and
picture state, RAM and WRAM, APU writes, the sound queue, late PPU writes and partial mapper loads. Oracles for
scoring come from expected_home_run(), the stock rules applied to the planted RAM, never from a ROM.

The CPU model counts cycles but approximates the PPU: frames are composed from VRAM, palette RAM and CHR at the
end of a frame, sprite-0 is manufactured from the beam position, open bus and fetch timing are not modelled, and
audio is compared as APU register writes.
"""
from collections import Counter

from build_draw32 import sha256
from frontend32_test_machine import SCENE, Bus, call, cpu, plant, series_state
import homerunart32_assets as model
from homerunart32_fixtures import (ACTIVE, BAT_SIDE, FLAGS, HALVES, HITS, HR_STAT, OVER, RUNS, SONG, STATE, TEAMS,
                                   restore, step, watch)
import password32v2
import render_menu32 as R
from test_pick32 import LIVE

ENDING, FIELD_SIDE, CLOCK = 0x0498, 0x04EE, 0xBA
PITCHER, DEBIT, DEBITS = 0x0563, 0x0793, 32           # slot X: responsible pitcher; runs charged per pitcher, side
SLOTS = (0x0C, 0x0B, 0x0A, 0x09)                     # the mass scorer's walk: runners on third..first, batter
BATTER_HITS, ORDER = 0x0757, 0x0513
HOME_RUN_SONG, RUN_SFX = 0x0A, 0x2C
# The $C5C4 loader's map buffer and bottom-row buffer: every screen load rewrites them before reading them.
LOADER_BUFFERS = frozenset(range(0x0100, 0x0180)) | frozenset(range(0x0340, 0x0360))
MILESTONES = ((0xD9DF, "state1-done"), (0xD755, "state2"), (0xD77B, "state3"), (0xD790, "exit"),
              (0xD872, "scene9"), (0xCFAA, "field-init"))


def scorers(ram):
    """Slots the mass scorer credits, in its order: $0555,X below 5 for X = $0C down to $09."""
    return [x for x in SLOTS if ram[ACTIVE + x] < 5]


def expected_home_run(ram):
    """What the stock rules give a home run from this RAM, independent of any ROM: one run per credited slot to
    the batting side, one debit per run to the slot's responsible pitcher, and after each run the game ends at
    100 runs or, in a bottom half, at a home lead of 10 or more before half $0B (ten-run rule) or any home
    lead from half $0B on (walk-off)."""
    side, half = ram[BAT_SIDE], ram[HALVES]
    score, over = [ram[RUNS], ram[RUNS + 1]], bool(ram[OVER])
    debits = Counter()
    for x in scorers(ram):
        score[side] += 1
        debits[(DEBIT + ((ram[PITCHER + x] << 1 & 0xFF) | ram[FIELD_SIDE])) & 0x7FF] += 1   # ASL, ORA, INC $0793,X
        if score[side] >= 100:
            over = True
        elif half & 1 and half >= 0x0B:
            over |= score[1] > score[0]
        elif half & 1:
            over |= score[1] - score[0] >= 10
    return {"side": side, "runs": len(scorers(ram)), "score": score, "over": over, "debits": dict(debits)}


def apply_plant(m, plant_spec):
    for address, value in plant_spec.get("ram", {}).items():
        m.ram[int(address)] = value
    if plant_spec.get("series"):
        plant(m, password32v2.Series(**plant_spec["series"]))
        m.ram[0x04E2] = 1
    if plant_spec.get("mash"):
        mash = plant_spec["mash"]
        m.pad = lambda frame: mash[frame % len(mash)]
        m.pad2 = lambda frame: mash[(frame + 1) % len(mash)]


def patched(rom, patch):
    data = bytearray(rom)
    for offset, value in patch:
        data[offset] = value
    return bytes(data)


def sample(m):
    """One frame as the picture and the scene machine see it. Sprite colors leave out entry 0 of each sprite
    palette, which mirrors the background backdrop ($3F10/$14/$18/$1C)."""
    nametable, palette = m.nametable(), m.palette32()
    return {"frame": m.frame, "scene": m.ram[SCENE], "state": m.ram[STATE], "chr1": m.chr[1], "ctrl": m.ctrl & 0x18,
            "shown": bool(m.mask & 0x18), "screen": sha256(nametable), "background": palette[:16].hex(),
            "sprites": bytes(palette[16 + 4 * p + k] for p in range(4) for k in (1, 2, 3)).hex(),
            "oam_hidden": all(y >= 0xEF for y in m.oam[::4])}


def watch_loader_buffers(m):
    """Record reads of loader-buffer bytes not yet rewritten; returns (the plain class, the reads)."""
    plain, written, stale = type(m), set(), []

    class Watched(plain):
        def __getitem__(self, a):
            if isinstance(a, int) and a < 0x2000 and (a & 0x7FF) in LOADER_BUFFERS and (a & 0x7FF) not in written:
                stale.append((self.frame, a & 0x7FF, self.pc))
            return plain.__getitem__(self, a)

        def __setitem__(self, a, v):
            if a < 0x2000 and (a & 0x7FF) in LOADER_BUFFERS:
                written.add(a & 0x7FF)
            plain.__setitem__(self, a, v)
    m.__class__ = Watched
    return plain, stale


def replay(state, rom, plant_spec=None, patch=(), after=240):
    """From a saved $B6F8 state: every frame until state 3 exits at $D790, then `after` more frames."""
    rom = patched(rom, patch)
    m = restore(state, rom)
    apply_plant(m, plant_spec or {})
    before = bytes(m.ram)
    marks, frames, pictures = {}, [], {}

    def mark(tag):
        def fire(mm):
            if not mm.nmi_depth and tag not in marks:
                marks[tag] = (mm.frame, mm.mpu.processorCycles)
        return fire
    for pc, tag in MILESTONES:
        m.on_pc[pc] = mark(tag)
    limit = m.frame + 3000
    while "exit" not in marks and m.ram[SCENE] == 5:
        m.frames(1)
        frames.append(sample(m))
        if m.ram[SCENE] == 5 and m.ram[STATE] == 3 and m.mask & 0x18 and m.chr[1] not in pictures:
            pictures[m.chr[1]] = (m.frame, m.nametable(), m.palette32())
        if m.frame > limit:
            raise AssertionError("the cutscene never exited")
    exit_ram, exit_wram = bytes(m.ram), bytes(m.wram)
    plain, stale = watch_loader_buffers(m)
    for _ in range(after):
        m.frames(1)
        frames.append(sample(m))
    m.__class__ = plain
    return {"marks": marks, "frames": frames, "pictures": pictures, "before": before, "left": m.ram[SCENE],
            "exit_ram": exit_ram,
            "exit_wram": exit_wram, "end_ram": bytes(m.ram), "end_wram": bytes(m.wram), "apu": list(m.apu),
            "queue": list(m.queue), "stale": stale, "late": len(m.vram_late), "partial": list(m.partial)}


def sweep(state, rom, team):
    """States 2-3 only from a saved $D755 state with both team ids planted: per shown frame the CHR1 bank, screen
    and background palette, to the $D790 exit (the field re-initializer after it reads roster caches a mid-game
    team swap does not rebuild, so it is outside this check)."""
    m = restore(state, rom)
    m.ram[TEAMS], m.ram[TEAMS + 1] = team, 31 - team
    done = []
    m.on_pc[0xD790] = lambda mm: (not mm.nmi_depth and not done and done.append(mm.frame))
    shown = []
    start = m.frame
    while not done:
        m.frames(1)
        if m.ram[SCENE] == 5 and m.ram[STATE] == 3 and m.mask & 0x18:
            shown.append((m.chr[1], sha256(m.nametable()), m.palette32()[:16].hex()))
        if m.frame - start > 3000:
            raise AssertionError("the cutscene never exited")
    return team, done[0], shown


def touched_play(state, rom, frames=600):
    """A saved over-the-fence state that is not a home run: `frames` frames, and whether state 2 began."""
    m = restore(state, rom)
    before = bytes(m.ram)
    entered = []
    m.on_pc[0xD755] = lambda mm: (not mm.nmi_depth and entered.append(mm.frame))
    m.frames(frames)
    return {"state2": entered, "before": before, "ram": bytes(m.ram), "wram": bytes(m.wram), "apu": list(m.apu)}


def natural(rom, teams=(29, 11), after=480):
    """A WATCH game from RESET under the fixture policy, one sample per policy step, until `after` frames past the
    first home run's return to the field; with pictures of the first shown frame of each CHR1 bank."""
    d = watch(rom, teams)
    m = d.m
    marks, steps, pictures = {}, [], {}

    def mark(tag):
        def fire(mm):
            if not mm.nmi_depth and tag not in marks and (tag == "state2" or "state2" in marks):
                marks[tag] = mm.frame
        return fire
    m.on_pc[0xD755] = mark("state2")
    m.on_pc[0xD790] = mark("exit")
    m.on_pc[0xCFAA] = mark("field-init")
    while "field-init" not in marks or m.frame < marks["field-init"] + after:
        step(d)
        r = m.ram
        steps.append((m.frame, r[SCENE], r[STATE], r[HALVES], r[RUNS], r[RUNS + 1], tuple(m.chr), r[SONG], r[0x25],
                      r[HR_STAT], r[HR_STAT + 1], r[OVER]))
        if r[SCENE] == 5 and r[STATE] == 3 and m.mask & 0x18 and m.chr[1] not in pictures:
            pictures[m.chr[1]] = (m.frame, m.nametable(), m.palette32())
        if m.frame > 12000:
            raise AssertionError("no home run and return to the field by frame 12000")
    return {"marks": marks, "steps": steps, "pictures": pictures, "ram": bytes(m.ram), "wram": bytes(m.wram),
            "apu": (len(m.apu), sha256(repr(m.apu).encode()))}


def compose(rom, picture):
    """RGB rows of a captured frame: (frame, VRAM $2000-$23FF, palette RAM) with its CHR1 bank, sprites hidden."""
    bank, (_, nametable, palette) = picture
    chr_data = rom[R.HEADER + rom[4] * 0x4000 + bank * 0x1000:][:0x1000]
    return model.picture(chr_data, nametable[:960], nametable[960:], palette[:16])



def bus_case(rom, team, side):
    """A flat bus on bank 6 with zeroed RAM, the teams and sides set and a live v2 series planted."""
    bus = Bus(rom, 6)
    m = bus.mem
    m[:0x800] = bytes(0x800)
    m[TEAMS], m[TEAMS + 1] = team, 31 - team
    m[BAT_SIDE], m[FIELD_SIDE] = side, side ^ 1
    plant(bus, LIVE)
    return bus, cpu(bus)


def scoring(rom, team, side, mask, half=0, score=(10, 20)):
    """Bank 6 $B73E for a ball over the fence with the batter and the runners `mask` (bit 0 first base) active:
    (oracle, observed) with the oracle from expected_home_run on the planted RAM."""
    bus, mpu = bus_case(rom, team, side)
    m = bus.mem
    m[0x04EB:0x04ED] = b"\x80\x00"
    m[HALVES] = half
    m[RUNS:RUNS + 2] = bytes(score)
    m[SCENE], m[STATE] = 5, 0
    m[0x0478] = m[0x0479] = 0
    m[0x0470:0x0478] = b"\xFF" * 8
    m[ACTIVE:ACTIVE + 14] = b"\xFF" * 14
    for i in range(4):
        m[ACTIVE + 9 + i] = 0 if i == 0 or mask & (1 << (i - 1)) else 0xFF
        m[PITCHER + 9 + i] = i
    oracle = expected_home_run(m)
    series = series_state(bus)
    call(mpu, 0xB73E)
    observed = {"side": side, "runs": m[RUNS + side] - score[side], "score": [m[RUNS], m[RUNS + 1]],
                "over": bool(m[OVER]), "debits": {a: m[a] for a in range(DEBIT, DEBIT + DEBITS) if m[a]}}
    extra = {"slots_cleared": m[ACTIVE + 9:ACTIVE + 13] == b"\xFF" * 4, "state": m[STATE],
             "over_marks": (bool(m[FLAGS] & 0x80), m[ENDING]), "series": series_state(bus) == series,
             "queued": sorted(v for v in m[0x0470:0x0478] if v != 0xFF)}
    return oracle, observed, extra, bytes(m[:0x800]), bytes(m[0x6000:0x8000])


def tail(rom, team, side):
    """Fixed $D9DF, state 1's timer-done path: the HR stat, the HIT stat and the batter's hit, then state 2."""
    bus, mpu = bus_case(rom, team, side)
    m = bus.mem
    m[0x0515], m[STATE] = 2, 1
    series = series_state(bus)
    call(mpu, 0xD9DF)
    return ({"hr": [m[HR_STAT], m[HR_STAT + 1]], "hits": [m[HITS], m[HITS + 1]], "batter_hit": m[BATTER_HITS + 4 + side],
             "04AC": m[0x04AC], "state": m[STATE], "series": series_state(bus) == series}, bytes(m[:0x800]))


def suppressed(rom, team, side, guard):
    """Bank 6 $B73E with one of its guards set ($C1 bit 2: the ball touched the ground, a wall or a fielder;
    $048E bit 5: the same, latched): no run, no state change and nothing queued."""
    bus, mpu = bus_case(rom, team, side)
    m = bus.mem
    m[RUNS:RUNS + 2] = bytes((7, 8))
    m[ACTIVE:ACTIVE + 14] = b"\xFF" * 14
    m[ACTIVE + 9:ACTIVE + 13] = bytes(4)
    m[0x0470:0x0478] = b"\xFF" * 8
    m[0x0478] = m[0x0479] = 0
    m[SCENE], m[STATE] = 5, 0
    m[0xC1], m[FLAGS] = guard
    call(mpu, 0xB73E)
    return ({"score": [m[RUNS], m[RUNS + 1]], "state": m[STATE], "queued": m[0x0470:0x0478] != b"\xFF" * 8,
             "slots": bytes(m[ACTIVE + 9:ACTIVE + 13])}, bytes(m[:0x800]))


def exit_case(rom, team, side, over, pinch, order=0):
    """Fixed $D7F8, the shared play exit after the cutscene: scene $09 when the game is over, else the field
    re-initializer (scene $02); the batting order $0513,side advances by 2, wrapping to 0 at $12, unless the game
    is over or $054D is set."""
    bus, mpu = bus_case(rom, team, side)
    m = bus.mem
    m[ACTIVE:ACTIVE + 14] = b"\xFF" * 14
    m[0x048D] = 1
    m[OVER], m[0x054D], m[ORDER + side] = over, pinch, order
    m[SCENE], m[STATE] = 5, 3
    series = series_state(bus)
    call(mpu, 0xD7F8)
    return ({"scene": m[SCENE], "order": m[ORDER + side], "series": series_state(bus) == series},
            bytes(m[:0x800]), bytes(m[0x6000:0x8000]))


def hud_expiry(rom, inside):
    """Fixed $E6D6, state 1's field-overlay timer: 60 updates while the play is inside the camera window ($E680
    clears carry), immediate expiry outside it. The timer values after each call until it reaches 0."""
    bus = Bus(rom, 2)
    mpu, m = cpu(bus), bus.mem
    m[:0x800] = bytes(0x800)
    m[0x0499], m[0xD1], m[0xD3], m[0x04BC], m[0x04BA] = 60, 0, 0, 0x10 if inside else 0, 0x80
    values = []
    for _ in range(60):
        call(mpu, 0xE6D6)
        values.append(m[0x0499])
        if not m[0x0499]:
            break
    return values


PHASE_MILESTONES = ((0xD9DF, "state1-done"), (0xD755, "state2"), (0xD767, "draw"), (0xD770, "drawn"),
                    (0xD77B, "state3"), (0xD790, "exit"), (0xD7F8, "play exit"), (0xCFAA, "field-init"),
                    (0xD17A, "scene3"), (0xD872, "scene9"))


def phase_run(state, rom, lead, plant_spec=None, after=60):
    """From a saved $B6F8 state with the next vblank `lead` cycles later: milestones, per-frame scene, state, $BA,
    song, CHR1 and mask, APU writes, late PPU writes, partial mapper loads, RAM $0400-$07FF and WRAM."""
    m = restore(state, rom)
    m.next_vblank += lead
    apply_plant(m, plant_spec or {})
    marks, seq = {}, []

    def mark(tag):
        def fire(mm):
            if not mm.nmi_depth and tag not in marks:
                marks[tag] = (mm.frame, mm.mpu.processorCycles)
        return fire
    for pc, tag in PHASE_MILESTONES:
        m.on_pc[pc] = mark(tag)
    limit = m.frame + 3000
    while "exit" not in marks:
        m.frames(1)
        seq.append((m.ram[SCENE], m.ram[STATE], m.ram[CLOCK], m.ram[SONG], m.chr[1], m.mask))
        if m.frame > limit:
            raise AssertionError("the cutscene never exited")
    for _ in range(after):
        m.frames(1)
        seq.append((m.ram[SCENE], m.ram[STATE], m.ram[CLOCK], m.ram[SONG], m.chr[1], m.mask))
    return {"marks": marks, "seq": seq, "apu": list(m.apu), "late": len(m.vram_late), "partial": list(m.partial),
            "ram": bytes(m.ram[0x0400:0x0800]), "wram": bytes(m.wram)}


GAME_OVER_CASES = (   # (half, away, home): top and bottom halves around the ten-run, walk-off and 100-run edges
    (0, 3, 2), (1, 0, 6), (1, 0, 7), (3, 1, 8), (3, 9, 0), (9, 0, 9), (10, 5, 2), (11, 3, 2), (11, 5, 2),
    (11, 6, 2), (15, 5, 2), (17, 4, 4), (1, 0, 96), (0, 97, 0))


def contracts(rom, quick=False):
    """Every direct-call case on `rom`: {(kind, case): (oracle, observed, raw)} for the suite to judge."""
    out = {}
    teams = range(0, 32, 5) if quick else range(32)
    for team in teams:
        for side in (0, 1):
            for mask in range(8):
                oracle, observed, extra, ram, wram = scoring(rom, team, side, mask)
                out[("scoring", team, side, mask)] = (oracle, observed, extra, sha256(ram + wram))
            out[("tail", team, side)] = tail(rom, team, side)
            for guard in ((4, 0), (0, 0x20)):
                out[("suppressed", team, side, guard)] = suppressed(rom, team, side, guard)
            for over in (0, 1, 2):
                for pinch in (0, 1):
                    order = 0x10 if team & 1 else 0
                    result, ram, wram = exit_case(rom, team, side, over, pinch, order)
                    out[("exit", team, side, over, pinch, order)] = (result, sha256(ram + wram))
    for inside in (True, False):
        out[("hud", inside)] = hud_expiry(rom, inside)
    for half, away, home in GAME_OVER_CASES:
        for mask in range(8):
            oracle, observed, extra, ram, wram = scoring(rom, 7, half & 1, mask, half, (away, home))
            out[("game over", half, away, home, mask)] = (oracle, observed, extra, sha256(ram + wram))
    return out
