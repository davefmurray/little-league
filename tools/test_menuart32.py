#!/usr/bin/env python3
"""Check the menuart32 stage, its art conversion, and its assembled ROM.

    .venv/bin/python tools/test_menuart32.py build/visualtables32.nes --candidate build/menuart32.nes
    .venv/bin/python tools/test_menuart32.py build/visualtables32.nes --pxl build/vendor/claude-pxl

Runtime checks execute the real ROM bytes on tools/render_menu32.py's CPU/PPU
model: stock entry code, both menus, controller serial reads, the stock NMI,
the stock audio engine, the stock commit, seed, launch and view exits, up to
the main loop at $FF90. The base ROM runs the same scripts as the reference.
The model charges OAM DMA and NMI entry cycles, but it is not a cycle-exact PPU
and cannot judge sound or pixels on a TV; the root emulator gates own those.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from PIL import Image

import build_menuart32 as builder
from build_menuart32 import build_rom, change_manifest, locate, protect_output
import menu32_convert as convert
import render_menu32 as R

# Fifth serial writes of the stock MMC1 routines ($C102/$C11C/$C134/$C14E) and bridges ($FF20, $FF90).
STOCK_MAPPER_LOADS = {0xC116, 0xC12E, 0xC146, 0xC162, 0xFF4C, 0xFFA7}
EXIT = 0xFF90          # both menu exits reach the stock bridge here, before it re-enables the NMI


def rejects(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except (ValueError, KeyError, convert.AssetError):
        return
    raise AssertionError(f"{getattr(call, '__name__', call)} accepted bad input")


def variant(base, mutate):
    """Build a ROM whose generated assembly is edited by `mutate(lines)`; for negative controls."""
    real = {name: getattr(builder, name) for name in ("runtime", "selector_code", "bracket_code")}

    def wrap(name):
        def inner(*args):
            return mutate(name, list(real[name](*args)))
        return inner

    with patch.multiple(builder, **{name: wrap(name) for name in real}), \
            patch.object(builder, "BASE_SHA256", hashlib.sha256(base).hexdigest()):
        return build_rom(base)


def menu_pc(pc):
    """True for a PC inside the new menu code of either bank."""
    return builder.BRK_CODE <= pc < builder.BRK_CODE + 0x400 or builder.SEL_CODE <= pc < builder.SEL_CODE + 0x400



def test_converter(base, pxl=None):
    first, second = convert.convert(base), convert.convert(base)
    text = convert.dumps(first)
    assert text == convert.dumps(second), "converter output is not deterministic"
    assert text == convert.ASSETS.read_text(), "data/menu32/menuassets.json is stale"
    meta = first["meta"]
    assert meta["tiles_used"] + meta["tiles_free"] == 256 and meta["tiles_used"] <= 254
    assert meta["pxl"]["commit"] == "3bc816cb15a14592e0dc062ee98013637d399457"
    assert all(tile["index"] == tile.get("font", tile["index"]) for tile in first["tiles"])
    assert all("pattern" not in tile for tile in first["tiles"] if "font" in tile), "stock glyphs committed"
    codes = [t["code"] for t in first["teams"]]
    assert len(set(map(tuple, (t["chip"] for t in first["teams"])))) == 32, "two teams share a chip"
    assert len(set(map(tuple, (t["flag"] for t in first["teams"])))) == 32, "two teams share a flag"
    assert codes == [t["code"] for t in convert.team_records()]

    committed = convert.PNGS

    def fresh(directory):
        if directory.exists():
            shutil.rmtree(directory)
        shutil.copytree(committed, directory)

    def edit(path, xy, rgba):
        image = Image.open(path).convert("RGBA")
        image.putpixel(xy, rgba)
        image.save(path)

    gold, cream, green, red = (convert.NES_RGB[c] + (255,) for c in (0x28, 0x38, 0x1A, 0x16))
    cases = [
        ("unknown color", lambda d: edit(d / "scenes/selector.png", (100, 120), (1, 2, 3, 255))),
        ("partial alpha", lambda d: edit(d / "sprites/chip_0.png", (3, 3), (255, 231, 162, 128))),
        ("scene transparency", lambda d: edit(d / "scenes/bracket.png", (40, 200), (0, 0, 0, 0))),
        ("attribute conflict", lambda d: [edit(d / "scenes/bracket.png", xy, c) for xy, c in
                                          (((120, 112), gold), ((121, 112), cream), ((122, 112), green),
                                           ((123, 112), red))]),
        ("text cell painted", lambda d: edit(d / "scenes/selector.png", (8 * 8 + 3, 3 * 8 + 3), gold)),
        ("runtime cell painted", lambda d: edit(d / "scenes/bracket.png", (8 + 4, 4 * 8 + 2), (255, 255, 255, 255))),
        ("slot palette switch", lambda d: edit(d / "scenes/bracket.png", (5, 34), cream)),
        ("flag fits no palette", lambda d: [edit(d / "sprites/flag_0.png", xy, c) for xy, c in
                                            (((0, 0), green), ((1, 0), gold), ((2, 0), red))]),
        ("wrong size", lambda d: Image.new("RGBA", (16, 16), (24, 60, 93, 255)).save(d / "sprites/chip_3.png")),
    ]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary) / "out"
        with patch.object(convert, "PNGS", directory):
            fresh(directory)
            copied = convert.convert(base)
            assert {k: v for k, v in copied.items() if k != "meta"} == {k: v for k, v in first.items() if k != "meta"}
            for label, mutate in cases:
                fresh(directory)
                mutate(directory)
                try:
                    convert.convert(base)
                except (convert.AssetError, IndexError) as exc:
                    if isinstance(exc, IndexError):
                        raise AssertionError(f"{label}: crashed instead of a clear error") from exc
                    continue
                raise AssertionError(f"converter accepted {label}")
            fresh(directory)
            real_init = convert.TileBank.__init__

            def tiny(bank, *args):
                real_init(bank, *args)
                bank.order = bank.order[:40]
            with patch.object(convert.TileBank, "__init__", tiny):
                rejects(convert.convert, base)
    rejects(convert.TileBank, {i: bytes(16) for i in range(256)}, {0x41})
    broken = dict(convert.font_patterns(base))
    broken[convert.BLANK] = b"\x01" + bytes(15)
    rejects(convert.TileBank, broken, {convert.BLANK})
    rendered = 0
    if pxl:
        with tempfile.TemporaryDirectory() as temporary:
            convert.render_pxl(pxl, Path(temporary))
            for path in convert.used_pngs():
                ours = Image.open(path).convert("RGBA")
                again = Image.open(Path(temporary) / path.relative_to(convert.PNGS)).convert("RGBA")
                assert ours.size == again.size and ours.tobytes() == again.tobytes(), path
                rendered += 1
    print(f"converter: deterministic, committed JSON current; {meta['tiles_used']} tiles "
          f"({len(meta['font_glyphs'])} referenced stock glyphs, none committed), {meta['tiles_free']} free; "
          f"{len(cases) + 3} bad inputs rejected"
          + (f"; pinned pxl re-render matches {rendered} committed PNGs pixel for pixel" if pxl else
             "; pxl re-render not run (no --pxl)"))



def test_builder(base, rom, assets):
    changes = change_manifest(base, assets)
    regions = {r.name: r for r in builder.REGIONS}
    claimed = set()
    for c in changes:
        region = regions[c.name]
        start = locate(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        assert (c.bank, c.addr, len(c.after)) == (region.bank, region.start, region.end - region.start)
        assert not span & claimed and base[start:start + len(c.before)] == c.before
        assert rom[start:start + len(c.after)] == c.after
        claimed.update(span)
    changed = {i for i, (a, b) in enumerate(zip(base, rom)) if a != b}
    assert len(base) == len(rom) and changed <= claimed
    report = builder.diff_manifest(base, rom)
    assert {i for r in report["ranges"] for i in r["changed_file_offsets"]} == changed
    assert report["input_sha256"] == builder.BASE_SHA256
    assert rom[:16] == base[:16]
    for bank in [b for b in range(16) if b not in (10, 11)]:
        origin = 0xC000 if bank == 15 else 0x8000
        assert rom[locate(bank, origin):locate(bank, origin) + 0x4000] == base[locate(bank, origin):locate(bank, origin) + 0x4000], bank
    for bank in range(32):
        if bank != builder.MENU_CHR:
            start = locate("chr", bank * 0x1000)
            assert rom[start:start + 0x1000] == base[start:start + 0x1000], f"CHR ${bank:02X}"
    assert len(rom) - locate("chr", 0) == 0x20000
    for index in (0, 4, 16, locate(10, 0x8000), locate(11, 0x8001), locate(10, 0xA000),
                  locate(11, 0x9000), locate("chr", 0x19000), locate(15, 0xCF7B), len(base) - 1):
        corrupt = bytearray(base)
        corrupt[index] ^= 1
        rejects(build_rom, bytes(corrupt), assets)
    rejects(build_rom, base[:-1], assets)
    rejects(build_rom, base + b"\xFF", assets)
    guards = [(10, 0x8001), (11, 0x8002), (10, 0xA3FF), (10, 0xAAFF), (10, 0xB3FF), (11, 0x93FF),
              (11, 0x9DFF), (11, 0xA3FF), (15, 0xC102), (15, 0xC13A), (15, 0xC152), (15, 0xC24C),
              (15, 0xC19B), (15, 0xCD8F), (15, 0xCDE6), (15, 0xCF79), (15, 0xCFA7), (15, 0xFFFA),
              (15, 0xFF53), (15, 0xFFB4), (15, 0xFEBB), (15, 0xFFCF), (15, 0xFCDF), (10, 0x9634),
              (11, 0x8162), (11, 0x8548), (11, 0x8384), (11, 0x83C6), (11, 0x8203), (11, 0x8364),
              (11, 0x8312), (11, 0x8486), (11, 0x8613), (11, 0x8665), (11, 0x8685), (11, 0x86D4),
              (11, 0x86F2), (11, 0x8120), ("chr", 0x19000 + 0x800), ("chr", 16 * 0x41 + 3),
              ("chr", 16 * 0x20), (10, 0x9400 + 16 * 5), (11, 0xB000 + 4 * 7)]
    for bank, addr in guards:
        corrupt = bytearray(base)
        corrupt[locate(bank, addr)] ^= 1
        with patch.object(builder, "BASE_SHA256", hashlib.sha256(corrupt).hexdigest()):
            rejects(build_rom, bytes(corrupt), assets)
    first = changes[0]
    for bad in (changes + (first,), changes[1:], (replace(first, name="unowned"),) + changes[1:],
                (replace(first, addr=0x8001),) + changes[1:], (replace(first, bank=9),) + changes[1:],
                (replace(first, after=first.after[:-1]),) + changes[1:],
                (replace(first, before=b"", after=b""),) + changes[1:],
                (replace(first, before=bytes(3)),) + changes[1:]):
        with patch.object(builder, "change_manifest", return_value=bad):
            rejects(build_rom, base, assets)
    stale = json.loads(json.dumps(assets))
    stale["teams"][4]["name"] = "KOREA REP     "
    rejects(builder.check_assets, base, stale)
    for mutate in (lambda a: a["tiles"].append(dict(a["tiles"][-1])),
                   lambda a: a["tiles"][0].update(pattern="00"),
                   lambda a: a["tiles"].__setitem__(0, {"index": 0x41, "font": 0x42, "source": "x"}),
                   lambda a: a["meta"].update(font_sha256="0" * 64),
                   lambda a: a["bracket"]["highlights"][3].extend([[1, 1]] * 4),
                   lambda a: a["screens"]["bracket"].update(palette="00")):
        bad = json.loads(json.dumps(assets))
        mutate(bad)
        rejects(builder.check_assets, base, bad)
    with tempfile.TemporaryDirectory() as temporary:
        teams = Path(temporary) / "teams32.json"
        data = json.loads(builder.TEAMS.read_text())
        data["teams"][9]["name"] = "ESPANA"
        teams.write_text(json.dumps(data))
        rejects(builder.check_assets, base, assets, teams)
    print(f"builder: {len(changed)} changed bytes inside {len(changes)} whole reservations; fixed bank, banks 0-9 "
          f"and 12-15, header and every CHR bank but ${builder.MENU_CHR:02X} identical; {len(guards)} stock "
          "dependency, hook, reservation, CHR $19, font and table guards each reject a one-bit drift; "
          "bad manifests and stale assets rejected")


def test_ram_audit(base, rom):
    """MENU_FRAME/MENU_MASK ($07F3/$07F4) have no stock reader or writer; the new code is their only user."""
    absolute = {0x0D, 0x0E, 0x0C, 0x1D, 0x1E, 0x19, 0x2C, 0x2D, 0x2E, 0x3D, 0x3E, 0x39, 0x4D, 0x4E, 0x5D, 0x5E,
                0x59, 0x6D, 0x6E, 0x7D, 0x7E, 0x79, 0x8C, 0x8D, 0x8E, 0x9D, 0x99, 0xAC, 0xAD, 0xAE, 0xBC, 0xBD,
                0xBE, 0xB9, 0xCC, 0xCD, 0xCE, 0xDD, 0xDE, 0xD9, 0xEC, 0xED, 0xEE, 0xFD, 0xFE, 0xF9}

    def users(rom_bytes, target):
        found = []
        for bank in range(16):
            origin = 0xC000 if bank == 15 else 0x8000
            data = rom_bytes[locate(bank, origin):locate(bank, origin) + 0x4000]
            for i in range(len(data) - 2):
                if data[i] in absolute and data[i + 1:i + 3] == target.to_bytes(2, "little"):
                    found.append((bank, origin + i))
        return found
    for target in (builder.MENU_FRAME, builder.MENU_MASK):
        assert not users(base, target), (hex(target), users(base, target))
        assert {bank for bank, _ in users(rom, target)} <= {10, 11}
    print("RAM audit: no stock instruction addresses $07F3 or $07F4; only the two menu banks do")


def test_output_guards(source, base, rom):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        original = directory / "input.nes"
        original.write_bytes(base)
        copy = directory / "renamed-visual.nes"
        copy.write_bytes(base)
        png = convert.PNGS / "scenes/selector.png"
        flag = convert.PNGS / "sprites/flag_0.png"
        targets = [original, copy, Path(builder.__file__), Path(__file__), builder.ASSETS, builder.TEAMS, png, flag,
                   convert.SOURCE, convert.LAYOUT, builder.ROOT / "build/visualtables32.nes",
                   directory / "visualtables32.nes", builder.ROOT / "Little League Baseball - Championship Series (USA).nes"]
        for label, target in (("rom", original), ("python", Path(builder.__file__)),
                              ("assets", builder.ASSETS), ("png", png)):
            symbolic, hard = directory / f"{label}-symlink", directory / f"{label}-hardlink"
            symbolic.symlink_to(target.resolve())
            os.link(target, hard)
            targets.extend((symbolic, hard))
        for target in targets:
            before = target.read_bytes() if target.is_file() else None
            rejects(protect_output, original, target)
            assert (target.read_bytes() if target.is_file() else None) == before
        script = Path(builder.__file__).resolve()
        output = directory / "menuart32.nes"
        command = [sys.executable, str(script), str(original), "-o"]
        for _ in range(2):
            result = subprocess.run(command + [str(output), "--manifest"], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            assert output.read_bytes() == rom
            assert json.loads(result.stdout) == builder.diff_manifest(base, rom)
        for target in (original, copy, script):
            before = target.read_bytes()
            result = subprocess.run(command + [str(target)], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 2 and "output aliases protected" in result.stderr, result.stderr
            assert target.read_bytes() == before
        converter_command = [sys.executable, str(Path(convert.__file__).resolve()), "--rom", str(original), "--out"]
        for target in (original, copy, directory / "rom-symlink", directory / "rom-hardlink",
                       png, flag, directory / "png-symlink", directory / "png-hardlink", convert.SOURCE, builder.TEAMS):
            before = target.read_bytes()
            result = subprocess.run(converter_command + [str(target)], cwd=directory, capture_output=True, text=True)
            assert result.returncode == 2 and "output aliases protected" in result.stderr, result.stderr
            assert target.read_bytes() == before
        asset_output = directory / "assets.json"
        result = subprocess.run(converter_command + [str(asset_output)], cwd=directory, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert asset_output.read_text() == convert.ASSETS.read_text()
        convert.protect_output(original, convert.ASSETS)
        original.write_bytes(b"bad ROM")
        result = subprocess.run(command + [str(output)], cwd=directory, capture_output=True, text=True)
        assert result.returncode == 2 and "expected visualtables32" in result.stderr
        assert output.read_bytes() == rom
    print("output guards: builder and converter refuse input ROMs, copies, nested PNGs, source and symbolic/hard "
          "aliases; normal ROM/JSON outputs pass; deterministic CLI build and manifest from another cwd")



GAME_RAM = sorted({0x07C0, 0x07C1, 0x07C3, 0x07C7, 0x074B, 0x074C, 0x07F1, 0x07F2, 0x07ED, 0x07EF, 0x07F0,
                   0x07F7, 0x07F8, 0x07F9, 0x07FA, 0x07FB, 0x07FC, 0x07FD, 0x07FE, 0x07FF, 0x04EF, 0x04F0,
                   0x047A, 0x047B, 0x047C, 0x047D, 0x0746, 0xBE, 0x33, 0x34, 0x27, 0x2C, 0x2D, 0x20, 0x22, 0x0401})


def exit_state(m):
    """Everything an exit hands to stock code, minus bytes the menus own or the sound engine moves."""
    return {
        "pc": m.mpu.pc, "sp": m.mpu.sp, "prg": m.prg, "control": m.control, "chr": tuple(m.chr),
        "nmi": bool(m.ctrl & 0x80),
        "ram": {f"${a:04X}": m.ram[a] for a in GAME_RAM},
        "wram": hashlib.sha256(bytes(m.wram)).hexdigest(),
    }


def selection_run(rom, team, old=False, second=R.A):
    steps = (R.old_selector_steps if old else R.selector_steps)(team) + [R.A]
    pad, end = R.press_script(steps, settle=12)

    def buttons(frame):
        if end + 40 <= frame < end + 42:
            return second
        return pad(frame)
    m = R.enter_selector(rom, buttons)
    m.run(R.at(EXIT), limit=20_000_000)
    return m


def test_selection(base, rom):
    started = time.monotonic()
    for team in range(32):
        new = selection_run(rom, team)
        old = selection_run(base, team, old=True)
        assert new.ram[0x07C3] == team
        heap = bytes(new.wram[0x1700:0x1740])
        assert heap[:32] == bytes([team] + [t for t in range(32) if t != team]), team
        assert heap[32:63] == b"\xFF" * 31
        masks = [new.ram[a] for a in (0x074B, 0x074C, 0x07F1, 0x07F2)]
        assert masks == [0xFF ^ (1 << (team & 7)) if i == team >> 3 else 0xFF for i in range(4)], (team, masks)
        a, b = exit_state(new), exit_state(old)
        assert a == b, (team, {k: (a[k], b[k]) for k in a if a[k] != b[k]})
        assert new.mpu.pc == EXIT and new.ram[0x2C] == new.ram[0x2D] == 0 and new.count == 0
        assert not new.vram_late and not new.partial and new.nmi_ticks == 0
    print(f"selection: all 32 teams chosen by serial controller input reach $FF90 through the stock commit, "
          f"seed and launch with the old ROM's exact game RAM, PRG RAM, mapper and stack state "
          f"({time.monotonic() - started:.0f}s)")


def bracket_run(rom, path, heap, played, presses=(), until=None, view=None, control=0x1F, frames=0):
    """Enter by `path`, then press each (frame offset, buttons) after the screen first shows."""
    shown = {}

    def pad(frame):
        if "at" not in shown:
            return presses[0][1] if presses and presses[0][0] < 0 else 0
        for offset, buttons in presses:
            if offset >= 0 and frame == shown["at"] + offset:
                return buttons
        return 0
    m = R.enter_bracket(rom, path, pad, heap, played, control=control, view=view)
    m.run(lambda machine: R.shown(machine) or machine.mpu.pc == until, limit=20_000_000)
    shown["at"] = m.frame
    shown["state"] = (m.nametable(), m.palette32(), m.control, tuple(m.chr), m.ctrl, m.mask, bytes(m.oam))
    if frames:
        m.frames(frames)
        shown["later"] = (m.nametable(), bytes(m.oam))
    if until is not None:
        m.run(R.at(until), limit=20_000_000)
    return m, shown


def expected_bracket(assets, heap, played):
    nt, attrs = convert.bracket_screen(assets, heap, played)
    return nt + attrs


def test_entry_paths(base, rom, assets):
    """All five ways into bank 11 $8000 draw the right bracket and leave like the old ROM."""
    palette = bytes.fromhex(assets["screens"]["bracket"]["palette"])
    checked = []
    for path, played, view in (("result", 6, None), ("result", 30, None), ("password", 17, None),
                               ("list", 12, None), ("list", 31, None), ("continue", 23, None),
                               ("continue", 0, None)):
        heap = R.heap_after(31, played)
        after = played + 1 if path == "result" else played
        expect_heap = bytearray(heap)
        if path == "result":
            expect_heap[32 + played] = heap[2 * played]
        view_mode = path == "list" or after >= 31
        button = R.B if view_mode else R.A
        presses = [(-1, button), (6, button)]
        m, shown = bracket_run(rom, path, heap, played, presses, until=EXIT)
        assert m.frame >= shown["at"] + 6, "the held entry button acted"
        nt, pal, control, chr_banks, ctrl, mask, oam = shown["state"]
        assert nt == expected_bracket(assets, expect_heap, after), (path, played)
        assert pal == palette and control == 0x1E and chr_banks == (0, builder.MENU_CHR)
        assert ctrl == builder.CTRL and mask == builder.MASK and all(y >= 0xEF for y in oam[0::4])
        old, _ = bracket_run(base, path, heap, played, presses, until=EXIT)
        a, b = exit_state(m), exit_state(old)
        assert a == b, (path, played, {k: (a[k], b[k]) for k in a if a[k] != b[k]})
        assert m.mpu.pc == EXIT and m.ram[0x2C] == m.ram[0x2D] == 0 and m.count == 0
        assert m.ram[0x047B] == (6 if view_mode else 0x13), (path, m.ram[0x047B])
        assert not m.vram_late and not m.partial and m.nmi_ticks == 0
        checked.append(f"{path}@{played}")
    heap = R.heap_after(31, 9)
    m, _ = bracket_run(rom, "continue", heap, 9, [(-1, R.A)], frames=40)
    assert R.shown(m), "a held A launched the bracket"
    m, _ = bracket_run(rom, "list", heap, 9, [(-1, R.B)], frames=40)
    assert R.shown(m), "a held B left the view"
    sel = R.enter_selector(rom, lambda f: R.A if f < 30 else 0)
    sel.frames(60)
    assert sel.ram[0x07C3] == 0xFF and sel.prg == 10, "a held A committed a team"
    sel = R.enter_selector(rom, lambda f: R.B if 20 <= f < 24 else 0)
    sel.frames(40)
    assert sel.ram[0x07C3] == 0xFF and sel.prg == 10, "B left the selector"
    print(f"entry paths: {', '.join(checked)} each draw the oracle bracket from the real heap and exit to "
          "$FF90 with the old ROM's state; held entry buttons and their release ignored in both menus")


def poisoned_heap(played, seed):
    heap = list(R.heap_after(seed & 31, played))
    for s in range(32 + played, 64):
        heap[s] = (s * 7 + seed) & 31 if s & 1 else (0x20 + s * 11 + seed) & 0xFF
    return bytes(heap)


def test_heap_bounds(base, rom, assets):
    """Undecided slots never show stale winners, slot 63 is never read and no table read runs past its end."""
    data = builder.bracket_data(assets)[1]
    tables = {"slot_hi": (data["slot_hi"], 63), "slot_lo": (data["slot_lo"], 63), "chips": (data["chips"], 68),
              "hl_count": (data["hl_count"], 32), "hl_off": (data["hl_off"], 128), "hl_val": (data["hl_val"], 256),
              "panel": (data["panel"], 49), "rounds": (0x9700, 512), "matches": (0x9900, 256),
              "versus": (0x9A00, 64), "names": (0x9B00, 544), "palette": (data["palette"], 32),
              "map": (builder.BRK_MAP, 1024)}
    cases = 0
    for played in list(range(32)) + [40, 0xFF]:
        for seed in (3, 22):
            heap = poisoned_heap(min(played, 31), seed)
            if seed == 22 and played < 31:
                heap = heap[:2 * played] + bytes([0x5A]) + heap[2 * played + 1:]
            m = R.enter_bracket(rom, "list", None, heap, played)
            m.trace_reads = (11, 0x9400, 0xA400)
            m.run(R.shown, limit=50_000_000)
            assert m.nametable() == expected_bracket(assets, heap, played), (played, seed)
            reads = {a for a, pc in m.reads if builder.BRK_CODE <= pc < builder.BRK_CODE + 0x400}
            for a in reads:
                assert any(lo <= a < lo + size for lo, size in tables.values()), f"stray read ${a:04X}"
            menu = [(kind, a) for kind, a, c0, c1, pc in m.wram_access if menu_pc(pc)]
            stray = {a for kind, a in menu if kind == "R"} - set(range(0x7700, 0x773F))
            assert not stray, sorted(f"${a:04X}" for a in stray)
            assert all(a != 0x773F for _, a, *_ in m.wram_access), "slot 63 was read"
            assert all(kind == "R" for kind, _ in menu), "the menu wrote PRG RAM"
            assert m.reads, "read tracing saw nothing"
            cases += 1
    unbounded = variant(base, lambda name, lines: [l for l in lines if l != "CPX $09"] if name == "bracket_code" else lines)
    heap = poisoned_heap(9, 3)
    m = R.enter_bracket(unbounded, "list", None, heap, 9)
    m.run(R.shown, limit=50_000_000)
    assert m.nametable() != expected_bracket(assets, heap, 9), "control: stale winners went unnoticed"
    print(f"heap bounds: {cases} poisoned heaps (stale valid winners, out-of-range ids, $07FC up to $FF) "
          "render only slots below 32+min($07FC,31); slot 63 never read; every data read inside its table; "
          "control: dropping the bound shows stale winners")


def stock_ticks(rom, count):
    m = R.stock_machine(rom, None)
    marks = []
    for _ in range(count):
        marks.append(len(m.apu))
        m.ram[0x2D] = 0
        m.call(0xCF74)
    return m.apu, marks


def tick_writes(apu, marks):
    bounds = list(marks) + [len(apu)]
    return [tuple((a, v) for _, a, v in apu[bounds[i]:bounds[i + 1]]) for i in range(len(marks))]


def test_audio(base, rom):
    idle = R.enter_selector(rom, None)
    idle.frames(600)
    ticks = tick_writes(idle.apu, idle.tick_marks)
    reference = tick_writes(*stock_ticks(rom, len(ticks)))
    assert ticks == reference, "menu ticks differ from the stock tick sequence"
    assert idle.nmi_ticks == 0 and not idle.queue and idle.ram[0x0401] == 0x06
    first = idle.ticks[0]
    per_frame = [idle.ticks.count(f) for f in range(first, idle.frame)]
    assert set(per_frame) == {1}, "a menu frame missed or doubled its tick"
    m = selection_run(rom, 13)
    song = [v for _, v in m.queue if v < 0x20]
    sfx = [v for _, v in m.queue if v >= 0x20]
    assert not song, "the menu song was queued again"
    assert sfx == [builder.SFX_MOVE] * len(R.selector_steps(13)) + [builder.SFX_CONFIRM] * 2, sfx
    gaps = [f for f in range(m.ticks[0], m.ticks[-1]) if f not in m.ticks]
    assert len(gaps) <= 2, f"frames without a tick through the menus: {gaps}"
    # After a game the result jingle plays; the bracket starts song 6 exactly once.
    heap = R.heap_after(31, 4)
    jingle = R.stock_machine(rom, None, song=0x10)
    jingle.wram[0x1700:0x1740] = heap
    jingle.ram[0x07FC], jingle.ram[0x07EF], jingle.ram[0x07ED], jingle.ram[0x07F0] = 4, 0x32, 1, 0
    jingle.map_bank(1)
    jingle.mpu.pc = 0xFEB1
    jingle.frames(40)
    assert [v for _, v in jingle.queue] == [0x06] and jingle.ram[0x0401] == 0x06
    old = R.enter_bracket(base, "continue", None, heap, 4)
    old.frames(120)
    assert not old.ticks and not old.nmi_ticks, "old bracket unexpectedly ticks"
    replay = variant(base, lambda name, lines: [
        "NOP" if line in ("BEQ mb_playing",) else line for line in lines] if name == "runtime" else lines)
    restart = R.enter_selector(replay, None)
    restart.frames(30)
    assert [v for _, v in restart.queue] == [0x06], "restart control did not restart"
    double = variant(base, lambda name, lines: _no_guard(lines) if name == "runtime" else lines)
    twice = R.enter_selector(double, None)
    twice.frames(120)
    assert twice.nmi_ticks > 0 and tick_writes(twice.apu, twice.tick_marks) != reference[:len(twice.tick_marks)]
    print(f"audio: 600 idle selector frames tick once each and equal the stock tick's APU writes; song $06 never "
          f"re-queued through moves, commit, handoff, bracket and launch; ${builder.SFX_MOVE:02X}/"
          f"${builder.SFX_CONFIRM:02X} on moves/confirm; {len(gaps)} untimed frame(s) at the handoff; result jingle "
          "replaced once. Controls: old bracket 0 ticks in 120 frames; unguarded queue restarts; $2D=0 double-ticks")


def _no_guard(lines):
    """Leave $2D clear in menu mode, so the NMI ticks audio too."""
    out = list(lines)
    out[out.index("STA $2D", out.index("menu_begin:"))] = "NOP"
    return out


def test_vblank(base, rom):
    """With rendering on, every PPU write lands in vblank, DMA stall and NMI entry included."""
    steps = [R.RIGHT, R.DOWN, R.LEFT, R.UP] * 6
    pad, end = R.press_script(steps, settle=12, hold=1, gap=1)
    m = R.enter_selector(rom, pad)
    m.frames(end + 20)
    worst = max(m.vblank_work.values())
    assert not m.vram_late and worst < R.VBLANK, (worst, m.vram_late[:3])
    heap = R.heap_after(31, 9)
    b, _ = bracket_run(rom, "continue", heap, 9, [], frames=80)
    bracket_worst = max(b.vblank_work.values())
    assert not b.vram_late and bracket_worst < R.VBLANK
    with patch.object(R.Machine, "oam_dma", lambda machine, page: R.Machine.log_ppu(machine, 0x4014, page)):
        free = R.enter_selector(rom, pad)
        free.frames(end + 20)
    uncharged = max(free.vblank_work.values())
    assert worst - uncharged >= 513, "the harness does not charge the OAM DMA stall"
    big = variant(base, lambda name, lines: _overflow(lines) if name == "selector_code" else lines)
    over = R.enter_selector(big, pad)
    over.frames(end + 20)
    assert over.vram_late, "an oversized update was not caught"
    print(f"vblank: worst selector frame ends its PPU work {worst:.0f} cycles after vblank start "
          f"(a full 36-byte panel update, OAM DMA {worst - uncharged:.0f} cycles), bracket {bracket_worst:.0f}, "
          f"budget {R.VBLANK:.0f}; controls: uncharged DMA reads {uncharged:.0f}, a 6x update lands late")


def _overflow(lines):
    """Queue the info panel six times per move: far more VRAM than one vblank holds."""
    i = lines.index("sel_info:")
    loop = ["LDA #$06", "STA $08", "si_more:", "JSR sel_info_once", "DEC $08", "BNE si_more", "RTS",
            "sel_info_once:"]
    return lines[:i + 1] + loop + lines[i + 1:]


def test_prg_ram_rule(base, rom):
    """While menu code runs, PRG RAM is touched only with both CHR latches below $10."""
    runs = [selection_run(rom, 20)]
    for path, played in (("result", 3), ("password", 8), ("list", 31), ("continue", 15)):
        runs.append(bracket_run(rom, path, R.heap_after(31, played), played,
                                [(2, R.B if path == "list" else R.A)], until=EXIT)[0])
    touched = 0
    for m in runs:
        for kind, a, c0, c1, pc in m.wram_access:
            if menu_pc(pc):
                touched += 1
                assert c0 < 0x10 and c1 < 0x10, (kind, hex(a), c0, c1, hex(pc))
        assert not m.partial
        loads = {pc for pc, *_ in m.mapper}
        assert loads <= STOCK_MAPPER_LOADS, sorted(hex(p) for p in loads - STOCK_MAPPER_LOADS)
    early = variant(base, lambda name, lines: _chr_first(lines) if name == "bracket_code" else lines)
    bad = R.enter_bracket(early, "continue", None, R.heap_after(31, 5), 5)
    bad.run(R.shown, limit=50_000_000)
    assert any(c1 >= 0x10 for kind, a, c0, c1, pc in bad.wram_access if menu_pc(pc)), "control missed"
    old = R.enter_bracket(base, "continue", None, R.heap_after(31, 5), 5)
    old.run(R.at(0x8680), limit=50_000_000)
    assert old.count == 1, "the old draw's stray $C040 write was not visible"
    print(f"PRG RAM and mapper: {touched} menu PRG RAM reads all under CHR (0,1); no NMI split a mapper write; "
          "every MMC1 load completes on a stock routine's fifth write; controls: CHR $19 before the heap copy "
          "caught, old bracket leaves MMC1 serial count 1 at $8680")


def _chr_first(lines):
    i = lines.index("brk_entry:")
    return lines[:i + 2] + [f"LDA #${builder.MENU_CHR:02X}", "JSR $C134"] + lines[i + 2:]


def test_zero_page(rom):
    """The stock tick and NMI short path never write $00-$0F, so menu scratch there survives a frame."""
    m = R.enter_selector(rom, lambda f: R.RIGHT if f % 6 == 3 else 0)
    m.watch_zp = lambda machine: machine.prg == 0 or machine.mpu.pc >= 0xC000 and machine.nmi_depth
    m.frames(400)
    assert not m.zp_writes, m.zp_writes[:5]
    print("zero page: 400 frames of ticks and NMIs write nothing in $00-$0F")


def test_selector_sync(rom, assets):
    """On every shown frame the cursor sprites frame the team the info panel names."""
    pad, end = R.press_script([R.RIGHT, R.DOWN, R.LEFT, R.UP, R.LEFT, R.RIGHT], settle=12, hold=1, gap=1)
    m = R.enter_selector(rom, pad)
    names = {convert.text_bytes(t["name"], convert.NAME_WIDTH): t["id"] for t in assets["teams"]}
    start = assets["screens"]["selector"]["regions"]["info_name"]["nt"] - 0x2000
    frames = 0
    while m.frame < end + 8:
        frame = m.frame
        m.run(lambda machine: machine.frame > frame)
        if not R.shown(m):
            continue
        team = names[m.nametable()[start:start + convert.NAME_WIDTH]]
        oam = [tuple(m.oam[i:i + 4]) for i in range(0, 16, 4)]
        assert oam in (convert.cursor_sprites(assets, team, 0), convert.cursor_sprites(assets, team, 1)), frame
        frames += 1
    assert frames > 20
    print(f"selector sync: {frames} frames through six moves show the cursor on the team the panel names")


def test_renders(rom, assets, out):
    out.mkdir(parents=True, exist_ok=True)
    data = convert.chr_bytes(assets, rom)
    pal = {name: bytes.fromhex(assets["screens"][name]["palette"]) for name in ("selector", "bracket")}
    written = []
    for team in (0, 31):
        pad, end = R.press_script(R.selector_steps(team), settle=12)
        m = R.enter_selector(rom, pad)
        m.frames(end + 6)
        nt, attrs = convert.selector_screen(assets, team)
        assert m.nametable() == nt + attrs and m.palette32() == pal["selector"]
        oam = [tuple(m.oam[i:i + 4]) for i in range(0, 16, 4)]
        assert oam in (convert.cursor_sprites(assets, team, 0), convert.cursor_sprites(assets, team, 1)), oam
        assert all(y >= 0xEF for y in m.oam[16::4]), "stray sprites"
        expected = convert.render(data, nt, attrs, pal["selector"], oam)
        assert m.picture().tobytes() == expected.tobytes()
        m.picture().save(out / f"rom-selector-{team:02d}.png")
        written.append(f"selector {team}")
    for played in (0, 15, 16, 23, 24, 28, 30, 31):
        heap = R.heap_after(31, played)
        m = R.enter_bracket(rom, "list" if played == 31 else "continue", None, heap, played)
        m.run(R.shown, limit=50_000_000)
        m.run(lambda machine: (machine.ram[0x07F3] & 0x1F) == 2, limit=50_000_000)
        assert m.nametable() == expected_bracket(assets, heap, played) and m.palette32() == pal["bracket"]
        m.picture().save(out / f"rom-bracket-{played:02d}.png")
        written.append(f"bracket {played}")
    for bank, addr, entry in ((10, builder.SEL_MAP + 0x1A5, "selector"), (11, builder.BRK_MAP + 0x0AF, "bracket")):
        corrupt = bytearray(rom)
        corrupt[locate(bank, addr)] ^= 0x01
        if entry == "selector":
            m = R.enter_selector(bytes(corrupt), None)
            expected = b"".join(convert.selector_screen(assets, 0))
        else:
            heap = R.heap_after(31, 5)
            m = R.enter_bracket(bytes(corrupt), "continue", None, heap, 5)
            expected = expected_bracket(assets, heap, 5)
        m.run(R.shown, limit=50_000_000)
        assert m.nametable() != expected, f"control: a corrupted {entry} map went unnoticed"
    print(f"renders: {len(written)} ROM-executed frames equal the converter oracle; PNGs in {out}; "
          "control: one flipped map byte in either screen is caught")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned visualtables32 input")
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--pxl", type=Path, help="pinned claude-pxl checkout: also re-render the art")
    ap.add_argument("--renders", type=Path, default=Path("build/menu32-rom"))
    ap.add_argument("--quick", action="store_true", help="skip the 32-team old-ROM parity sweep")
    args = ap.parse_args()
    started = time.monotonic()
    base = args.rom.read_bytes()
    assets = builder.load_assets()
    rom = build_rom(base, assets)
    if args.candidate:
        assert args.candidate.read_bytes() == rom, "candidate differs from the deterministic build"
    print(f"input {hashlib.sha256(base).hexdigest()}")
    print(f"candidate {hashlib.sha256(rom).hexdigest()}")
    test_converter(base, args.pxl)
    test_builder(base, rom, assets)
    test_output_guards(args.rom, base, rom)
    test_ram_audit(base, rom)
    test_entry_paths(base, rom, assets)
    test_heap_bounds(base, rom, assets)
    test_audio(base, rom)
    test_vblank(base, rom)
    test_prg_ram_rule(base, rom)
    test_zero_page(rom)
    test_selector_sync(rom, assets)
    test_renders(rom, assets, args.renders)
    if not args.quick:
        test_selection(base, rom)
    assert args.rom.read_bytes() == base, "input ROM changed"
    print(f"menuart32 SHA256 {hashlib.sha256(rom).hexdigest()}")
    print(f"PASS ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
