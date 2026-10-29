#!/usr/bin/env python3
"""Check the pick32 stage: builder guards and controller-driven flows through the shared picker.

    .venv/bin/python tools/test_pick32.py build/draw32.nes --candidate build/pick32.nes
    .venv/bin/python tools/test_pick32.py build/draw32.nes --quick

Flows boot the built ROM from RESET on tools/frontend32_test_machine.Boot and
press real controller buttons through the stock title, mode menu and
submenus, the picker, the stock commit, draw, roster cache and pre-game
scenes, and the bank-3 ratings screen. Picker routines are also called
directly on the flat bus. A variant without the bank-1 patch and the stock
world-map picker of the draw32 input are the negative controls. --quick skips
the stock-versus-new exit parity run (about six minutes).
"""
import argparse
from dataclasses import replace
import hashlib
from pathlib import Path
import time

import build_menuart32
import build_pick32 as builder
from build_draw32 import locate
import draw32
import draw32_6502
import password32v2 as P
from frontend32_test_machine import (A, B, DOWN, LEFT, RIGHT, SCENE, Boot, Bus, call, check_builder,
                                     check_output_guards, choose, cpu, plant, rejects, run_to, series_state,
                                     title_tail, to_mode_menu)

OUTPUT_SHA256 = "8fb36a7b6f3fea03ec9b4bc76dce24141e7dc6522a0675a64b5d7b9135ac8cfa"
TOOLS = Path(__file__).resolve().parent
LABELS = builder.labels()
PICKER = range(builder.ORIGIN, builder.TEXTS)
OWNERSHIP = (0xBD, 0x04EB, 0x04EC, 0x04E9, 0x04ED, 0x04EE, builder.MODE)
WATCH = (SCENE, 0x07ED, 0x04E2) + OWNERSHIP
LIVE = P.Series(team=9, played=3, results=0b101, cpu_mask=0xFFFFFDFF, draw_seed=0x1234)
FLAGS = ((0x00, 0x80), (0x00, 0x00), (0x80, 0x80))          # $96A3 by $BD: 1P, 2P, WATCH
PICK_PORTS = ((0, None), (0, 1), (None, None))              # controller owning pick 0 and pick 1


def variant(base, name):
    """The stage built with one change left at its old bytes: a negative control."""
    changes = tuple(replace(c, after=c.before) if c.name == name else c for c in builder.change_manifest(base))
    return builder.apply_changes(base, changes, builder.REGIONS)


def header(m):
    start = builder.HEADER_PPU - 0x2000
    return m.nametable()[start:start + 16].decode("ascii")


def cursor(m):
    return m.ram[build_menuart32.ROW] << 3 | m.ram[build_menuart32.COL]


def in_picker(d, limit=600):
    m, start = d.m, d.m.frame
    m.run(lambda mm: (mm.prg == 10 and mm.mpu.pc == LABELS["pk_loop"] and mm.ram[build_menuart32.MENU_MASK] == 0x1E)
          or mm.frame - start > limit, limit=200_000_000)
    assert m.prg == 10 and m.mpu.pc == LABELS["pk_loop"], f"picker not running (scene {m.ram[SCENE]:02X})"
    d.wait(4)


def move_to(d, team, port=0):
    m = d.m
    for _ in range(max(0, (team & 7) - m.ram[build_menuart32.COL])):
        d.press(RIGHT, port=port)
    for _ in range(max(0, m.ram[build_menuart32.COL] - (team & 7))):
        d.press(LEFT, port=port)
    for _ in range(((team >> 3) - m.ram[build_menuart32.ROW]) % 4):
        d.press(DOWN, port=port)
    assert cursor(m) == team, f"cursor at {cursor(m)}, wanted {team}"


def picker_writes(m, addresses):
    return [entry for entry in m.log if entry[1] in addresses and entry[5] == 10 and entry[4] in PICKER]


def roster_cache(rom, team):
    """What $FC00 caches for `team`: 240 roster bytes with only the first three players flagged as
    pitchers, then the 48-byte trailer from roster offset $140."""
    source = rom[locate(15, 0xFCA0 + team)] << 8 | rom[locate(15, 0xFC80 + team)]
    assert source == 0x8000 + 0x170 * team, "bank-8 roster pointer table moved"
    start = locate(8, source)
    data = bytearray(rom[start:start + 0xF0])
    for player in range(15):
        flag = 8 + 16 * player
        data[flag] = (data[flag] & 0x7F) | (0x80 if player < 3 else 0)
    return bytes(data) + rom[start + 0x140:start + 0x170]


def check_launch(rom, picks, snapshot):
    """Roster caches and pointers exactly as $FC00 left them, for high and low teams."""
    cache, pointers = snapshot
    for side, team in enumerate(picks):
        home = 0x7800 + 0x200 * side
        pointer = pointers[2 * team] | pointers[2 * team + 1] << 8
        if team >= 16:
            assert cache[0x200 * side:0x200 * side + 0x120] == roster_cache(rom, team), f"team {team} cache"
            assert pointer == home, f"team {team} roster pointer ${pointer:04X}"
        else:
            stock = rom[locate(15, 0xFD40 + 2 * team)] | rom[locate(15, 0xFD41 + 2 * team)] << 8
            assert pointer == stock, f"team {team} kept the cache pointer instead of its stock roster"


def check_routing(rom, sub, flags):
    """$C585 routes each team's buttons from its owner's controller through both sides and the swap."""
    owners = PICK_PORTS[sub]
    pads = {0: (0x11, 0x33), 1: (0x22, 0x44)}
    for swap in (0, 1):
        for batting in (0, 1):
            bus = Bus(rom, 1)
            bus.mem[0x04EB], bus.mem[0x04EC] = flags[::-1] if swap else flags
            bus.mem[0x04E9], bus.mem[0x04ED], bus.mem[0x04EE] = swap, batting, batting ^ 1
            bus.poke(0x8F, bytes((0x11, 0x22, 0x33, 0x44)))
            call(cpu(bus), 0xC585)
            for role, side in enumerate((batting, batting ^ 1)):
                owner = owners[side ^ swap]
                expected = (0, 0) if owner is None else pads[owner]
                assert (bus.mem[0x93 + role], bus.mem[0x95 + role]) == expected, (sub, swap, batting, role)


def test_builder(base, rom):
    changed, guards = check_builder(builder, base, rom, owned_banks={1, 2, 10})
    generated = build_menuart32.labels()["selector"]
    assert all(generated[name] == addr for name, addr in builder.RUNTIME.items()), "a reused helper moved"
    assets = build_menuart32.load_assets()
    assert (builder.X0, builder.Y0) == tuple(8 * v for v in assets["selector"]["cards"][0])
    assert builder.CURSOR_TILE == assets["cursor_tile"]
    menu_glyphs = set(assets["meta"]["font_glyphs"])
    missing = next(chr(i) for i in range(0x21, 0x60) if i not in menu_glyphs)
    assert {ord(c) for c in "".join(builder.HEADERS)} <= menu_glyphs
    bad = ("CHOOSE YOUR TEA" + missing,) + builder.HEADERS[1:]
    original = builder.HEADERS
    try:
        builder.HEADERS = bad
        rejects(builder.change_manifest, base)
    finally:
        builder.HEADERS = original
    print(f"builder: {changed} changed bytes inside {len(builder.REGIONS)} whole reservations; banks 0, 3-9 and "
          f"11-15, header and CHR identical; {guards} dependency, digest, hook and reservation guards each reject a "
          f"one-bit drift; bad manifests rejected; reused helpers, card origin and cursor tile equal menuart32's "
          f"generated labels and assets; a header needing glyph {missing!r} is rejected")


def test_units(rom):
    for team in range(32):
        bus = Bus(rom, 10)
        bus.mem[builder.MODE], bus.mem[builder.SIDE], bus.mem[builder.PICK0] = builder.EXHIBITION, 1, team
        bus.mem[build_menuart32.ROW], bus.mem[build_menuart32.COL] = team >> 3, team & 7
        bus.poke(0x7700, bytes(range(0x80)))
        before = bus.peek(0x0400, 0x400), bus.peek(0x7700, 0x80)
        mpu = cpu(bus)
        mpu.sp = 0xFD
        run_to(mpu, LABELS["pk_a"], LABELS["pk_sprites"])
        assert bus.mem[builder.SIDE] == 1 and bus.mem[builder.PICK0] == team, "a duplicate pick advanced"
        assert (bus.peek(0x0400, 0x400), bus.peek(0x7700, 0x80)) == before, "a refused pick wrote game state"
    for port in (0, 1):
        bus = Bus(rom, 10, pads=(0x81, 0x48))
        bus.mem[builder.PORT], bus.mem[build_menuart32.HELD] = port, 0
        mpu = cpu(bus)
        call(mpu, LABELS["pk_pad"])
        assert bus.mem[build_menuart32.PAD] == (0x81, 0x48)[port], "wrong controller read"
        assert bus.port_reads == ([8, 0] if port == 0 else [0, 8]), bus.port_reads
        for pads, label, new in (((0x80, 0x80), "pk_latch", 0), ((0, 0), "pk_pad", 0), ((0x80, 0x80), "pk_pad", 0x80)):
            bus.pads = list(pads)
            call(mpu, LABELS[label])
            assert bus.mem[build_menuart32.NEW] == new, f"port {port} {label}: held A acted"
    shown = 0
    for mode, submode, side, index in ([(0, 0, 0, 0), (2, 0, 0, 1)]
                                       + [(1, sub, side, 2 + 2 * sub + side) for sub in range(3) for side in (0, 1)]):
        bus = Bus(rom, 10)
        bus.mem[builder.MODE], bus.mem[builder.SUBMODE], bus.mem[builder.SIDE], bus.mem[0x32] = mode, submode, side, 0
        call(cpu(bus), LABELS["pk_header"])
        expected = bytes((builder.HEADER_PPU >> 8, builder.HEADER_PPU & 0xFF, 16)) + builder.HEADERS[index].encode()
        assert bus.peek(0x0300, 19) == expected and bus.mem[0x32] == 19, (mode, submode, side)
        shown += 1
    print(f"picker units: a second pick equal to the first is refused for all 32 teams with no game-state write; "
          f"controller 1 and 2 reads and the held-button latch on both ports; {shown} mode headers queued at "
          f"${builder.HEADER_PPU:04X}")


def flow_championship(rom):
    d = to_mode_menu(rom, WATCH)
    m = d.m
    start = len(m.log)
    choose(d, 0, sub=2)
    in_picker(d)
    assert header(m) == builder.HEADERS[0]
    move_to(d, 20)
    captured = []
    m.on_pc[draw32_6502.DRAW_LABELS["new_series_draw"]] = \
        lambda mm: mm.prg == 11 and captured.append((mm.ram[0x33], mm.ram[0x07F3]))
    d.press(A, gap=0)
    m.run(lambda mm: bool(captured), limit=50_000_000)
    d.wait(60)
    f33, menu = captured[0]
    seed = int.from_bytes(m.peek(0x7760, 2), "little")
    assert seed == draw32.capture(f33, menu)
    assert list(m.peek(0x7700, 32)) == draw32.draw_order(20, seed), "heap differs from the host draw"
    mask = int.from_bytes(bytes(m.ram[a] for a in (0x074B, 0x074C, 0x07F1, 0x07F2)), "little")
    assert mask == 0xFFFFFFFF ^ (1 << 20) and m.ram[0x07ED] == 1 and m.ram[0x07EF] == 0x32
    marks = [e for e in m.log[start:] if e[1] == 0x07ED]
    assert marks and marks[0][3] == 1 and marks[0][5] == 11 and marks[0][4] == 0x86E7, "series marked before commit"
    draw = range(draw32_6502.DRAW_ORIGIN, 0x8300)
    seed_access = [entry for entry in m.wram_access if entry[1] in (0x7760, 0x7761)]
    assert sum(kind == "W" for kind, *_ in seed_access) in (2, 3), "the seed was not written once at commit"
    assert all(pc in draw and c0 < 0x10 and c1 < 0x10 for _, _, c0, c1, pc in seed_access), \
        "a draw-seed access ran outside the bank-11 draw or with a CHR bank above $0F mapped"
    return (f"championship: team 20 committed through $9620; draw seed {seed:04X} from $33={f33:02X} "
            f"$07F3={menu:02X}; heap equals the host draw (first opponent {m.peek(0x7701)[0]}); only team 20 human; "
            "$07ED first set by the commit at bank 11 $86E7; every $7760/$7761 access comes from the bank-11 draw "
            "with CHR latches below $10")


def cancel_flow(rom, live=None):
    """START NEW SERIES, move to team 31, B, then CONTINUE; the series state at each step."""
    d = to_mode_menu(rom, WATCH)
    m = d.m
    if live is not None:
        plant(m, live)
    run = dict(before=series_state(m))
    mark = len(m.wram_access)
    choose(d, 0, sub=2)
    in_picker(d)
    run["entered"] = series_state(m)
    move_to(d, 31)
    d.press(B)
    d.wait_scene(7)
    d.wait(20)
    run["cancelled"] = series_state(m)
    d.press(A)
    d.wait(30)
    d.press(A, gap=0)
    if live is not None:
        m.run(lambda mm: mm.prg == 11 and 0x9000 <= mm.mpu.pc < 0x9E00, limit=50_000_000)
    else:
        d.wait(90)
    run.update(final=series_state(m), scene=m.ram[SCENE], sub=m.ram[0x047C], prg=m.prg,
               seed_writes=[a for kind, a, *_ in m.wram_access[mark:] if kind == "W" and a in (0x7760, 0x7761)])
    return run


def flow_cancel(base, rom):
    run = cancel_flow(rom)
    marker = run["before"][2]
    assert run["entered"][2] == run["cancelled"][2] == marker == b"\x00", "START NEW SERIES or B set $07ED"
    assert run["prg"] != 11 and run["scene"] == 0x19, f"CONTINUE without a series reached {run['scene']:02X}"
    lines = [f"cancel: fresh boot START NEW SERIES then B keeps $07ED=00; CONTINUE opens password entry "
             f"(scene {run['scene']:02X})"]
    run = cancel_flow(variant(base, "new-series-marker"))
    assert run["entered"][2] == b"\x12" and run["scene"] == 0x13, "control: the stale marker went unnoticed"
    lines.append(f"control without the bank-1 patch: START NEW SERIES sets $07ED=12 and after B, CONTINUE "
                 f"enters scene {run['scene']:02X}/{run['sub']:02X} in bank {run['prg']}")
    for draw_seed in (0, 0x1234, draw32.SEED_MAX):
        run = cancel_flow(rom, replace(LIVE, draw_seed=draw_seed))
        assert run["before"] == run["entered"] == run["cancelled"] == run["final"], f"seed {draw_seed:04X} changed"
        assert run["prg"] == 11 and not run["seed_writes"], "CONTINUE missed the bracket, or the seed was written"
    lines.append("active series with draw seeds 0, $1234 and $3FFF: START NEW SERIES, move to team 31, B, then "
                 "CONTINUE reaches the bank-11 bracket with heap, seed, markers and masks unchanged and zero "
                 "$7760/$7761 writes")
    return "\n".join(lines)


def flow_exhibition(rom, sub, picks, ports=(0, 0), active=False):
    d = to_mode_menu(rom, WATCH)
    m = d.m
    if active:
        plant(m, LIVE)
        m.ram[0x04E2] = 1
    before = series_state(m)
    launches = []
    m.on_pc[0xFF90] = lambda mm: mm.prg == 8 and launches.append((mm.peek(0x7800, 0x400), mm.peek(0x7F00, 0x40)))
    choose(d, 1, sub=sub)
    in_picker(d)
    assert header(m) == builder.HEADERS[2 + 2 * sub], header(m)
    m.vram_late.clear()
    m.vblank_work.clear()
    move_to(d, picks[0], port=ports[0])
    d.press(A, port=ports[0])
    assert m.ram[builder.SIDE] == 1 and m.ram[builder.PICK0] == picks[0]
    assert header(m) == builder.HEADERS[3 + 2 * sub], header(m)
    extra = ""
    if ports[1] == 1:
        spot = cursor(m)
        for button in (RIGHT, DOWN, A, B):
            d.press(button, port=0)
        assert cursor(m) == spot and m.ram[builder.SIDE] == 1 and m.prg == 10, "controller 1 drove side 2"
        d.press(RIGHT, port=1)
        assert cursor(m) != spot, "controller 2 did not drive side 2"
        extra = "; controller 1 cannot steer, pick or go back on side 2; controller 2 can"
    assert not m.vram_late, f"picker wrote VRAM outside vblank: {m.vram_late[:3]}"
    busiest = max(m.vblank_work.values() or [0])
    move_to(d, picks[1], port=ports[1])
    d.press(A, port=ports[1], gap=0)
    d.wait_scene(0x11, limit=900)
    d.wait(120)
    flags = (m.ram[0x04EB], m.ram[0x04EC])
    assert (m.ram[0x04EF], m.ram[0x04F0]) == tuple(picks), (m.ram[0x04EF], m.ram[0x04F0])
    assert flags == FLAGS[sub] and m.ram[0x04E2] == 0, (flags, m.ram[0x04E2])
    assert len(launches) == 1, "the roster cache ran other than once"
    check_launch(rom, picks, launches[0])
    check_routing(rom, sub, flags)
    assert not picker_writes(m, OWNERSHIP + (0x07ED,)), "the picker wrote mode, ownership or series bytes"
    if active:
        assert series_state(m) == before, "exhibition changed the active championship"
    return (f"exhibition {('1P', '2P', 'WATCH')[sub]}: picks {picks} on controllers {ports}; $04EB/$04EC "
            f"{flags[0]:02X}/{flags[1]:02X}; $04E2=0" + ("" if not active else " over a stale 1, series intact")
            + f"; exact roster caches and pointers; $C585 routes both sides through swaps{extra}; picker never "
            f"writes $06E0, $BD or ownership; scene $11 reached; busiest vblank {busiest:.0f} of 2273 cycles")


def flow_rules(rom):
    d = to_mode_menu(rom, WATCH)
    m = d.m
    choose(d, 1, sub=0)
    in_picker(d)
    move_to(d, 12)
    d.press(A)
    d.press(A)
    d.wait(20)
    assert m.ram[builder.SIDE] == 1 and m.prg == 10, "the same team was accepted twice"
    d.press(B)
    assert m.ram[builder.SIDE] == 0 and cursor(m) == 12 and header(m) == builder.HEADERS[2]
    d.press(B)
    d.wait_scene(7)
    return ("exhibition rules: the same team is refused as the second pick; B while choosing the second team returns "
            "to the first with the cursor on it; B again reaches the mode menu")


def flow_analysis(rom):
    d = to_mode_menu(rom, WATCH)
    m = d.m
    plant(m, LIVE)
    before = series_state(m)
    choose(d, 2)
    in_picker(d)
    assert header(m) == builder.HEADERS[1]
    for team in (27, 31):
        move_to(d, team)
        d.press(A, gap=0)
        d.wait_scene(0x15)
        d.wait(60)
        assert m.ram[0x04EF] == team
        d.press(B)
        in_picker(d)
        assert cursor(m) == team, "ratings B did not reopen the picker on the viewed team"
    d.press(B)
    d.wait_scene(7)
    assert series_state(m) == before, "analysis changed the active championship"
    return ("analysis: 27 and 31 viewed; ratings B reopens the picker on the viewed team; B reaches the mode menu; "
            "active series intact")


class Taint(Boot):
    def arm(self, addresses):
        self.taint, self.leaks = set(addresses), {}

    def __getitem__(self, a):
        if isinstance(a, int) and a < 0x2000 and (a & 0x7FF) in getattr(self, "taint", ()):
            self.leaks.setdefault(a & 0x7FF, (self.pc, self.prg, self.ram[SCENE]))
        return super().__getitem__(a)

    def __setitem__(self, a, v):
        if a < 0x2000 and getattr(self, "taint", None):
            self.taint.discard(a & 0x7FF)
        super().__setitem__(a, v)


def parity_run(rom, new):
    d = to_mode_menu(rom)
    d.m.__class__ = Taint
    choose(d, 1, sub=0)
    if new:
        in_picker(d)
        move_to(d, 5)
        d.press(A)
        move_to(d, 1)
        d.press(A, gap=0)
    else:
        d.wait_scene(0x0D)
        d.wait(40)
        d.press(A)
        d.wait(30)
        d.press(RIGHT)
        d.press(A, gap=0)
    d.wait_scene(0x10, limit=600)
    return d


def flow_parity(base, rom):
    """The stock world-map picker and the new one, same 1P match (5, 1): nothing else leaks into the game."""
    old, new = parity_run(base, False), parity_run(rom, True)
    ignore = set(range(0x0100, 0x0400))
    diff = [a for a in range(0x800) if a not in ignore and old.m.ram[a] != new.m.ram[a]]
    for d in (old, new):
        assert (d.m.ram[0x04EF], d.m.ram[0x04F0], d.m.ram[0x04EB], d.m.ram[0x04EC]) == (5, 1, 0, 0x80)
        d.m.arm(diff)
    for d in (old, new):
        seen = []
        for _ in range(60):
            d.press(A, gap=40)
            if d.m.ram[SCENE] not in seen:
                seen.append(d.m.ram[SCENE])
            if d.m.ram[SCENE] in (2, 3, 4, 5) and len(seen) > 2:
                break
        d.wait(300)
        assert seen[:2] == [0x11, 0x0F], seen
    audio = set(range(0x0400, 0x0470)) | {0x00FB}
    allowed = audio | {0x0033, 0x047D, 0x049D, 0x049E, 0x07FD, 0x07FE}
    leaks = set(new.m.leaks)
    assert leaks <= allowed, sorted(f"${a:04X}" for a in leaks - allowed)
    assert not leaks & set(range(0xB8, 0xBD)), "the stock picker's zero page leaked"
    return (f"exit parity: {len(diff)} RAM bytes differ at scene $10; through scenes $11 and $0F the only ones read "
            f"before rewritten are audio state, $33, $047D, $049D/$049E and the cache inputs $07FD/$07FE "
            f"({len(leaks)} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned draw32 input")
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--quick", action="store_true", help="skip the stock-versus-new exit parity run")
    args = ap.parse_args()
    started = time.monotonic()
    base = args.rom.read_bytes()
    rom = builder.build_rom(base)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256, "pick32 output differs from the CPU-tested prototype"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    test_builder(base, rom)
    sources = [TOOLS / "build_pick32.py", builder.ROOT / "data/menu32/menuassets.json",
               builder.ROOT / "art/menu32/out/sprites/flag_0.png", TOOLS / "test_pick32.py",
               TOOLS / "build_draw32.py", builder.ROOT / "build/menuart32.nes"]
    sources += [TOOLS / "verify.sh", builder.ROOT / "data/title32/titleassets.json",
                builder.ROOT / "art/title32/title32.px.js", builder.ROOT / "art/title32/layout.json",
                builder.ROOT / "art/title32/PXL.json", builder.ROOT / "art/title32/out/scenes/title.png"]
    count = check_output_guards(TOOLS / "build_pick32.py", args.rom, rom, builder.diff_manifest(base, rom), sources)
    print(f"output guards: deterministic CLI build and manifest from another directory; {count} protected targets "
          "refused (inputs, renamed copy, sources, nested PNG, symbolic and hard links); a bad input keeps the output")
    test_units(rom)
    codes = [title_tail(rom, replace(LIVE, draw_seed=s), port) for s in (0, 0x1234) for port in (0, 1)]
    print(f"title tail: v1 and v2 series survive post-game, title, START on either controller, mode menu and "
          f"CONTINUE ({', '.join(sorted(set(codes)))})")
    flows = (lambda: flow_championship(rom), lambda: flow_cancel(base, rom),
             lambda: flow_exhibition(rom, 0, (20, 31)), lambda: flow_exhibition(rom, 0, (16, 3), active=True),
             lambda: flow_exhibition(rom, 1, (3, 22), ports=(0, 1)), lambda: flow_exhibition(rom, 2, (30, 29)),
             lambda: flow_exhibition(rom, 1, (31, 0), ports=(0, 1)), lambda: flow_rules(rom),
             lambda: flow_analysis(rom))
    for flow in flows:
        print(flow(), flush=True)
    if not args.quick:
        print(flow_parity(base, rom))
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"pick32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
