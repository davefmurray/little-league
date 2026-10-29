#!/usr/bin/env python3
"""Check the draw32 stage: host draw and codec, the assembled ROM, and its CPU behaviour.

    .venv/bin/python tools/test_draw32.py build/menuart32.nes --candidate build/draw32.nes

CPU checks execute the built ROM's real bank-11, bank-12 and fixed-bank
bytes on the flat py65 bus of tools/frontend32_test_machine.py: the draw for
every seed and capture pair, the v1/v2 decoder and encoder, the password
bridges, the real restore and the stock post-game, title and menu path. The
frozen menuart32 ROM is the negative control for v2 acceptance, and
single-hook variants built by the real builder are the controls for the
restore, encoder and decoder hooks.
"""
import argparse
from dataclasses import replace
import hashlib
import itertools
from pathlib import Path
import random
import subprocess
import sys
import time

import build_draw32 as builder
import draw32
import draw32_6502 as D
import password32
import password32_6502
import password32v2 as P
from frontend32_test_machine import (Bus, call, check_builder, check_output_guards, cpu, plant, rejects,
                                     run_to, series_state, title_tail)

OUTPUT_SHA256 = "b263bd4906b70d2fa0ba807e83296f721787b346df33dc3fc0d69dc7da7d4541"
TOOLS = Path(__file__).resolve().parent
S = P.Series

GOLDEN_DRAWS = {
    (0, 0): "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    (31, 0): "1f000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e",
    (0, 1): "0011120c1d1c1a151e0819160a1004010d17050f0e0b1b06090718021314031f",
    (20, 0x1FEB): "141610030b1c1205021819150f0811170a071a060e0d1e001f1d0913041b0c01",
    (31, 0x1234): "1f161808090a060c11070d1b0110151d020e0317121c19141a0f0b00131e0405",
    (5, 0x3FFF): "05121b1503181613060e0119110809170a1c0d02041d1f0b10141e1a070f0c00",
}
GOLDEN_CODES = (
    (S(team=0, played=0, results=0, cpu_mask=0, draw_seed=0), "74VMS3YCSUHL6HHRB44XUY"),
    (S(team=31, played=31, results=0x7FFFFFFF, cpu_mask=0xFFFFFFFF, draw_seed=0), "7D983S5G32B8XBB4H2D6JJ"),
    (S(team=0, played=0, results=0, cpu_mask=0, draw_seed=1), "44VMS3YCSUHL6HHRB4N0DK"),
    (S(team=31, played=24, results=0x555555, cpu_mask=0x5AA55AA5, draw_seed=0x1234), "4995FEC5ESTVP6KM5YCNYM"),
    (S(team=31, played=31, results=0x7FFFFFFF, cpu_mask=0xFFFFFFFF, draw_seed=0x3FFF), "4T0F3S5G32B8XBB4HRPMS3"),
    (S(team=20, played=3, results=0b101, cpu_mask=0xFFEFFFFF, draw_seed=0x1FEB), "4TWLT8YCSUT8XBW4HPGTJJ"),
)


def states(count, seed=0x32F2):
    rng = random.Random(seed)
    out = [series for series, _ in GOLDEN_CODES]
    out.append(S(team=15, played=0, results=0, cpu_mask=0xFFFFFFDF, draw_seed=0x2A5B))
    out.append(S(team=7, played=16, results=0xAAAA, cpu_mask=0xFFFFFF7F, draw_seed=0x0100))
    for _ in range(count):
        played = rng.randrange(32)
        out.append(S(team=rng.randrange(32), played=played, results=rng.getrandbits(played),
                     cpu_mask=rng.getrandbits(32), draw_seed=rng.choice((0, rng.randrange(1, draw32.SEED_MAX + 1)))))
    return out


def host_rejects(text):
    try:
        P.decode(text)
    except ValueError:
        return True
    return False


def invalid_forms():
    """Codes whose CRC is correct but whose payload no release may accept."""
    forms = []
    for draw_seed in (0, 0x1234):
        good = P.to_bytes(S(team=31, played=0, results=0, cpu_mask=0x7FFFFFFF, draw_seed=draw_seed))[:12]
        flips = [(0, 1), (0, 2), (0, 4), (6, 0x80), (3, 1)] + ([(1, 0x20), (2, 0x20), (11, 1)] if not draw_seed else [])
        for index, bit in flips:
            body = bytearray(good)
            body[index] |= bit
            forms.append((f"seed {draw_seed:04X} byte {index} bit {bit:02X}", P.frame(body)))
        for version in (0, 3, 4, 5, 6, 7) + ((1,) if draw_seed else ()):
            body = bytearray(good)
            body[0] = version << 3
            forms.append((f"seed {draw_seed:04X} version {version}", P.frame(body)))
    body = bytearray(P.to_bytes(S(team=31, played=0, results=0, cpu_mask=0x7FFFFFFF, draw_seed=0))[:12])
    body[0] = P.V2_VERSION
    forms.append(("v2 with draw seed 0", P.frame(body)))
    return forms


def test_host_draw():
    state, period = 1, 0
    while True:
        state = draw32.xorshift16(state)
        period += 1
        assert state, "xorshift16 reached zero"
        if state == 1:
            break
    assert period == 0xFFFF, period
    for team in range(32):
        assert draw32.draw_order(team, 0) == password32.seed_order(team), "seed 0 is not the stock seeder order"
    for (team, draw_seed), golden in GOLDEN_DRAWS.items():
        assert bytes(draw32.draw_order(team, draw_seed)).hex() == golden, (team, draw_seed)

    def distinct(draw):
        return len({tuple(draw(seed)) for seed in range(1, draw32.SEED_MAX + 1)})
    for team in (0, 31):
        for seed in range(1, draw32.SEED_MAX + 1):
            order = draw32.draw_order(team, seed)
            assert order[0] == team and sorted(order) == list(range(32)), (team, seed)
        assert distinct(lambda seed: draw32.draw_order(team, seed)) == draw32.SEED_MAX, "two seeds share a draw"
    collapsed = distinct(lambda seed: draw32.draw_order(0, seed & 0xFF or 1))
    assert collapsed < draw32.SEED_MAX, "control: the distinctness check missed collapsed seeds"
    hits = {}
    for f33, menu in itertools.product(range(256), repeat=2):
        seed = draw32.capture(f33, menu)
        assert 1 <= seed <= draw32.SEED_MAX
        hits[seed] = hits.get(seed, 0) + 1
    assert len(hits) == draw32.SEED_MAX, "a draw seed is unreachable from the timing bytes"
    first = [0] * 32
    for seed in range(1, draw32.SEED_MAX + 1):
        first[draw32.draw_order(0, seed)[1]] += 1
    for bad in ((32, 0), (0, draw32.SEED_MAX + 1), (-1, 0), (0, True), (0, 1.0)):
        rejects(draw32.draw_order, *bad)
    rejects(draw32.capture, 256, 0)
    print(f"host draw: xorshift16 period {period}; seed 0 equals the stock seeder for all 32 teams; "
          f"{len(GOLDEN_DRAWS)} golden draws; {draw32.SEED_MAX} distinct draws for teams 0 and 31 (control: "
          f"8-bit seeds give {collapsed}); all 65536 timing pairs reach every seed {min(hits.values())}-"
          f"{max(hits.values())} times; first opponent counts {min(first[1:])}-{max(first[1:])} over the family")


def test_host_codec():
    all_states = states(400)
    v1_count = v2_count = 0
    for series in all_states:
        text = P.encode(series)
        assert P.decode(text) == series, series
        if series.draw_seed == 0:
            fields = (series.team, series.played, series.results, series.cpu_mask)
            assert text == password32.encode(*fields) and P.display(text) == password32.display(text)
            assert P.to_bytes(series) == password32.to_bytes(*fields)
            v1_count += 1
        else:
            rejects(password32.decode, text)
            v2_count += 1
    for series, code in GOLDEN_CODES:
        assert P.encode(series) == code and P.decode(code) == series, code
        assert P.decode(code.lower()) == series and P.decode(code[:11] + " " + code[11:]) == series
        aliased = code.replace("1", "I").replace("0", "O").replace("9", "Q").replace("2", "Z")
        assert P.decode(aliased) == series, "stock aliases rejected"
    forms = invalid_forms()
    for label, text in forms:
        assert host_rejects(text), f"host accepted {label}"
    substitutions = 0
    for series in [s for s in all_states if not s.draw_seed][:6] + [s for s in all_states if s.draw_seed][:6]:
        text = P.encode(series)
        for index, symbol in itertools.product(range(22), password32.ALPHABET):
            if symbol != text[index]:
                assert host_rejects(text[:index] + symbol + text[index + 1:])
                substitutions += 1
    for bad in (dict(team=32), dict(played=32), dict(results=2), dict(cpu_mask=1 << 32), dict(draw_seed=0x4000),
                dict(draw_seed=-1), dict(team=True), dict(team=1.0)):
        fields = dict(team=0, played=1, results=0, cpu_mask=0, draw_seed=1) | bad
        rejects(lambda: S(**fields))
    rejects(P.frame, bytes(11))
    for text in (None, 22, "", "1" * 21, "1" * 23, "!" * 22, "é" * 22):
        assert host_rejects(text), text
    print(f"host codec: {len(all_states)} states round trip ({v1_count} v1 byte-identical to password32, {v2_count} "
          f"v2 rejected by password32); {len(GOLDEN_CODES)} golden codes with case, space and alias input; "
          f"{len(forms)} correct-CRC invalid forms and {substitutions} one-symbol substitutions rejected")


def test_cli():
    def run(*args):
        return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=TOOLS.parent)
    series, code = GOLDEN_CODES[3]
    result = run(TOOLS / "password32v2.py", "encode", "--team", "31", "--played", "24", "--results", "0x555555",
                 "--cpu-mask", "0x5AA55AA5", "--draw-seed", "0x1234")
    assert result.returncode == 0 and result.stdout.strip() == code, result.stderr
    result = run(TOOLS / "password32v2.py", "decode", code)
    assert result.returncode == 0 and "team=31 " in result.stdout and "draw_seed=0x1234 (v2)" in result.stdout
    result = run(TOOLS / "password32v2.py", "encode", "--team", "3")
    assert result.returncode == 2 and "--draw-seed" in result.stderr, "draw seed must be explicit"
    result = run(TOOLS / "password32v2.py", "encode", "--team", "3", "--draw-seed", "0x4000")
    assert result.returncode == 2 and "draw_seed" in result.stderr
    result = run(TOOLS / "password32v2.py", "decode", invalid_forms()[0][1])
    assert result.returncode == 2
    result = run(TOOLS / "password32.py", "encode", "--seed", "3")
    assert result.returncode == 0 and result.stdout.strip() == password32.encode(3, 0, 0, 0xFFFFFFFF)
    result = run(TOOLS / "password32v2.py", "encode", "--team", "3", "--draw-seed", "0")
    assert result.returncode == 0 and result.stdout.strip() == password32.encode(3, 0, 0, 0xFFFFFFFF)
    result = run(TOOLS / "draw32.py", "--team", "20", "--draw-seed", "0x1FEB")
    assert result.returncode == 0 and result.stdout.startswith("order: " + " ".join(
        f"{t:02X}" for t in draw32.draw_order(20, 0x1FEB)))
    print("CLI: password32v2 encode/decode take explicit --team and --draw-seed; password32 --seed still means "
          "the selected team; draw32 prints the order")


def test_builder(base, rom):
    changed, guards = check_builder(builder, base, rom, owned_banks={11, 12})
    labels = password32_6502.BANK12_LABELS
    assert (D.DEC_FAIL, D.CRC16) == (labels["dec_fail"], labels["crc16"]), "v1 codec labels moved"
    v1_code = dict(password32_6502.BANK12_SEGMENTS)[0x8000]
    gate = 0x8058 - 0x8000
    assert v1_code[gate:gate + 7] == bytes.fromhex("AD 27 06 C9 08 D0") + bytes([D.DEC_FAIL - (0x805D + 2)]), \
        "the version check moved"
    assert D.GATE_RESUME == 0x8058 + 7
    assert v1_code[0x8113 - 0x8000:0x8116 - 0x8000] == b"\x20" + D.CRC16.to_bytes(2, "little"), \
        "the encoder's crc16 call moved"
    restore = dict(password32_6502.BANK11_SEGMENTS)[0x8600]
    assert restore[6:9] == b"\x20" + D.STOCK_SEEDER.to_bytes(2, "little"), "the restore's seeder call moved"
    print(f"builder: {changed} changed bytes inside {len(builder.REGIONS)} whole reservations; banks 0-10 and "
          f"13-15, header and CHR identical; {guards} dependency, digest, hook and reservation guards each reject a "
          "one-bit drift; bad manifests rejected; v1 codec labels match password32_6502")


def test_ram_audit(base, rom):
    """The stage adds absolute $7760-$777F operands only inside its own code.

    A byte scan cannot tell code from data. The base ROM's matches are all in
    bank 0 runs that hold illegal opcodes around them, so they are table data;
    root's real-core traces separately saw no base access to $7760-$777F."""
    absolute = {0x0D, 0x0E, 0x0C, 0x1D, 0x1E, 0x19, 0x2C, 0x2D, 0x2E, 0x3D, 0x3E, 0x39, 0x4D, 0x4E, 0x5D, 0x5E,
                0x59, 0x6D, 0x6E, 0x7D, 0x7E, 0x79, 0x8C, 0x8D, 0x8E, 0x9D, 0x99, 0xAC, 0xAD, 0xAE, 0xBC, 0xBD,
                0xBE, 0xB9, 0xCC, 0xCD, 0xCE, 0xDD, 0xDE, 0xD9, 0xEC, 0xED, 0xEE, 0xFD, 0xFE, 0xF9}

    def users(data):
        found = set()
        for bank in range(16):
            origin = 0xC000 if bank == 15 else 0x8000
            start = builder.locate(bank, origin)
            block = data[start:start + 0x4000]
            for i in range(len(block) - 2):
                if block[i] in absolute and 0x7760 <= int.from_bytes(block[i + 1:i + 3], "little") <= 0x777F:
                    found.add((bank, origin + i))
        return found
    before, after = users(base), users(rom)
    owned = [r for r in builder.REGIONS if r.name in ("draw-code", "codec-code")]
    added = after - before
    assert before <= after and {bank for bank, _ in before} == {0}, sorted(before)
    assert added and all(any(r.bank == bank and r.start <= addr < r.end for r in owned) for bank, addr in added)
    print(f"RAM audit: {len(added)} new $7760/$7761 operands, all inside the bank-11 draw and bank-12 codec code; "
          f"the {len(before)} base matches are bank-0 table bytes")


def test_cpu_draw(rom):
    bus = Bus(rom, 11)
    mpu = cpu(bus)
    labels = D.DRAW_LABELS
    for state in range(1, 0x10000):
        bus.mem[0], bus.mem[1] = state & 0xFF, state >> 8
        call(mpu, labels["dr_rng"])
        assert bus.mem[0] | bus.mem[1] << 8 == draw32.xorshift16(state), state
    cycles = []
    cases = [(seed & 31, seed) for seed in range(1, draw32.SEED_MAX + 1)] + [(team, 0) for team in range(32)]
    bus.writes.clear()
    for team, seed in cases:
        bus.poke(0x7700, b"\xA5" * 0x40)
        bus.mem[0x07C3] = team
        bus.poke(D.SEED_LO, seed.to_bytes(2, "little"))
        cycles.append(call(mpu, labels["draw32"]))
        assert list(bus.peek(0x7700, 32)) == draw32.draw_order(team, seed), (team, seed)
        assert bus.peek(0x7720, 0x20) == b"\xA5" * 0x20, "the draw touched winner slots"
    allowed = set(range(0x7700, 0x7720)) | set(range(0x00, 0x09)) | set(range(0x0100, 0x0200))
    assert bus.writes <= allowed, sorted(f"{a:04X}" for a in bus.writes - allowed)
    assert 0x34 not in bus.writes and D.SEED_LO not in bus.writes and D.SEED_HI not in bus.writes
    assert max(cycles) < 14_890, "the draw takes more than half a frame"
    for f33, menu in itertools.product(range(256), repeat=2):
        bus.mem[0x33], bus.mem[0x07F3] = f33, menu
        run_to(mpu, labels["new_series_draw"], labels["draw32"], limit=40)
        assert bus.mem[D.SEED_LO] | bus.mem[D.SEED_HI] << 8 == draw32.capture(f33, menu), (f33, menu)
    for team, seed in ((31, 1), (5, 0x2A5B), (0, draw32.SEED_MAX), (17, 0)):
        bus.poke(D.DECODED_LO, seed.to_bytes(2, "little"))
        bus.mem[0x07C3] = team
        call(mpu, labels["restore_draw"])
        assert list(bus.peek(0x7700, 32)) == draw32.draw_order(team, seed)
        assert bus.peek(D.SEED_LO, 2) == seed.to_bytes(2, "little")
    print(f"6502 draw: dr_rng equals xorshift16 for all 65535 states; {len(cases)} draws (every seed, every team at "
          f"seed 0) equal the host; {min(cycles)}-{max(cycles)} cycles, mean {sum(cycles) / len(cycles):.0f}; writes "
          "only $7700-$771F, $00-$08 and stack, never $34 or the seed; capture equals the host for all 65536 "
          "timing pairs; restore_draw copies the decoded seed and draws")


def cpu_decode(rom, text):
    bus = Bus(rom, 12)
    bus.poke(0x0643, text.encode())
    mpu = cpu(bus)
    call(mpu, 0x8000)
    if mpu.p & 1:
        return None
    p = bus.peek(0x0627, 14)
    return (p[1], p[2], int.from_bytes(p[3:7], "little"), int.from_bytes(p[7:11], "little"), p[12] | p[13] << 8)


def fields(series):
    return (series.team, series.played, series.results, series.cpu_mask, series.draw_seed)


def restore_cycle(rom, text, poison=b"\xA5"):
    """Decode through the stock bridge, run the real restore to the bracket, then encode for display."""
    bus = Bus(rom, 1)
    bus.poke(0x7700, poison * 0x80)
    bus.poke(0x0643, text.encode())
    mpu = cpu(bus)
    run_to(mpu, 0xFCC0, 0x8000, bank=11)
    restored = bus.peek(0x7700, 0x3F), bus.peek(D.SEED_LO, 2), sorted(a for a in bus.writes if a >= 0x6000)
    bus.map(5)
    mpu.sp = 0xFF
    call(mpu, 0xFCE2)
    return bus, restored


def variant(base, name):
    """The stage built with one hook left at its old bytes: a negative control."""
    changes = tuple(replace(c, after=c.before) if c.name == name else c for c in builder.change_manifest(base))
    return builder.apply_changes(base, changes, builder.REGIONS)


def test_cpu_codec(base, rom):
    all_states = states(400)
    v2 = 0
    for series in all_states:
        text = P.encode(series)
        assert cpu_decode(rom, text) == fields(series), (series, text)
        old = cpu_decode(base, text)
        if series.draw_seed:
            v2 += 1
            assert old is None, f"menuart32 accepted v2 {text}"
        else:
            assert old is not None and old[:4] == fields(series)[:4]
    live = S(team=9, played=3, results=0b101, cpu_mask=0xFDFFFFFF, draw_seed=0x1234)
    forms = invalid_forms()
    for label, text in forms:
        bus = Bus(rom, 12)
        plant(bus, live)
        bus.poke(0x7762, bytes(range(0x1E)))
        before = series_state(bus), bus.peek(0x7700, 0x80)
        bus.poke(0x0643, text.encode())
        mpu = cpu(bus)
        call(mpu, 0x8000)
        assert mpu.p & 1 and (series_state(bus), bus.peek(0x7700, 0x80)) == before, f"CPU accepted {label}"
        bridge = Bus(rom, 1)
        plant(bridge, live)
        kept = series_state(bridge)
        bridge.poke(0x0643, text.encode())
        call(cpu(bridge), 0xFCC0)
        after = series_state(bridge)
        assert bridge.bank == 1 and after[2] == b"\x00", "a failed entry kept the stock $07ED marker"
        assert after[:2] + after[3:] == kept[:2] + kept[3:], "a failed entry changed the heap, seed or masks"
        assert not {a for a in bridge.writes if a >= 0x6000}, "a failed entry wrote PRG RAM"
    substitutions = 0
    for series in [s for s in all_states if not s.draw_seed][:6] + [s for s in all_states if s.draw_seed][:6]:
        text = P.encode(series)
        for index, symbol in itertools.product(range(22), password32.ALPHABET):
            if symbol != text[index]:
                assert cpu_decode(rom, text[:index] + symbol + text[index + 1:]) is None
                substitutions += 1
    for series in all_states:
        bus = Bus(rom, 12)
        plant(bus, series)
        bus.writes.clear()
        call(cpu(bus), 0x8003)
        assert bus.peek(0x0643, 26) == P.display(P.encode(series)), series
        assert not {a for a in bus.writes if a >= 0x6000}, "the encoder wrote PRG RAM"
    cycles = 0
    for series in all_states[:120]:
        text = P.encode(series)
        bus, (heap, seed, wram) = restore_cycle(rom, text)
        assert heap == series_image_heap(series) and seed == series.draw_seed.to_bytes(2, "little"), series
        assert (bus.mem[0x07FC], bus.mem[0x07C3], bus.mem[0x07ED], bus.mem[0x07EF], bus.mem[0x07F0]) \
            == (series.played, series.team, 1, 0x32, 0)
        assert set(wram) <= set(range(0x7700, 0x773F)) | {D.SEED_LO, D.SEED_HI}, "restore wrote outside heap and seed"
        assert bus.peek(0x0643, 26) == P.display(text) and bus.bank == 5, "re-encoded code differs from the typed one"
        cycles += 1
    sample = S(team=5, played=7, results=0b1010101, cpu_mask=0xFFFFFFDF, draw_seed=0x1ABC)
    text = P.encode(sample)
    controls = []
    for name in ("restore-call", "encode-call"):
        bus, (heap, seed, _) = restore_cycle(variant(base, name), text)
        heap_ok = heap == series_image_heap(sample) and seed == sample.draw_seed.to_bytes(2, "little")
        code_ok = bus.peek(0x0643, 26) == P.display(text)
        assert not (heap_ok and code_ok), f"control: {name} left at stock still round-trips"
        controls.append(f"{name} {'heap ok' if heap_ok else 'heap WRONG'}/{'code ok' if code_ok else 'code WRONG'}")
    assert cpu_decode(variant(base, "decode-gate"), text) is None, "control: v2 accepted without the gate"
    print(f"CPU codec: {len(all_states)} codes ({v2} v2) decode like the host; menuart32 rejects all {v2} v2 codes "
          f"and keeps every v1 code; {len(forms)} correct-CRC invalid forms rejected with heap, seed, markers and "
          f"masks unchanged (the stock bridge then clears only $07ED); {substitutions} substitutions rejected; "
          f"{len(all_states)} display buffers equal the host with no PRG RAM writes; {cycles} bridge decode -> "
          f"restore -> encode cycles reproduce heap, markers, seed and the typed code, writing only heap and seed. "
          f"Controls: {'; '.join(controls)}; no gate rejects v2")


def series_image_heap(series):
    return bytes(0xFF if t is None else t for t in P.heap(series))


def test_title_tail(rom):
    codes = []
    for draw_seed in (0, 0x1234, draw32.SEED_MAX):
        for port in (0, 1):
            series = S(team=31, played=24, results=0x555555, cpu_mask=0x5AA55AA5, draw_seed=draw_seed)
            codes.append(title_tail(rom, series, port))
    bus = Bus(rom, 0)
    plant(bus, GOLDEN_CODES[3][0])
    call(cpu(bus), 0xCD5C)
    assert bus.mem[0x07ED] == 0, "control: the reset routine kept the series marker"
    print(f"title tail: v1 and v2 series (draw seeds 0, $1234, $3FFF) survive the real post-game $B63D, title "
          f"init, START on either controller, mode-menu init and CONTINUE into bank 11 with heap, seed, markers "
          f"and masks unchanged; the displayed codes are {', '.join(sorted(set(codes)))}; RESET's $CD20/$CD5C "
          "never ran. Control: a direct $CD5C call clears $07ED")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned menuart32 input")
    ap.add_argument("--candidate", type=Path)
    args = ap.parse_args()
    started = time.monotonic()
    base = args.rom.read_bytes()
    rom = builder.build_rom(base)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256, "draw32 output differs from the CPU-tested prototype"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    test_host_draw()
    test_host_codec()
    test_cli()
    test_builder(base, rom)
    sources = [TOOLS / "build_draw32.py", TOOLS / "password32v2.py", builder.ROOT / "art/menu32/out/scenes/selector.png",
               TOOLS / "draw32_6502.py", TOOLS / "test_draw32.py", builder.ROOT / "data/teams32.json"]
    sources += [TOOLS / "verify.sh", builder.ROOT / "data/title32/titleassets.json",
                builder.ROOT / "art/title32/title32.px.js", builder.ROOT / "art/title32/layout.json",
                builder.ROOT / "art/title32/PXL.json", builder.ROOT / "art/title32/out/scenes/title.png"]
    count = check_output_guards(TOOLS / "build_draw32.py", args.rom, rom, builder.diff_manifest(base, rom), sources)
    print(f"output guards: deterministic CLI build and manifest from another directory; {count} protected targets "
          "refused (inputs, renamed copy, sources, nested PNG, symbolic and hard links); a bad input keeps the output")
    test_ram_audit(base, rom)
    test_cpu_draw(rom)
    test_cpu_codec(base, rom)
    test_title_tail(rom)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"draw32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
