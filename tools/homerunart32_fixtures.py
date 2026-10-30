#!/usr/bin/env python3
"""Played home-run states for tools/test_homerunart32.py, from RESET on the input ROM, with a provenance-checked
local cache.

    .venv/bin/python -B tools/homerunart32_fixtures.py build/analysisart32.nes [--quick] [--refresh] [--cache DIR]

Every played home run starts from RESET on the input ROM with controller input only: START on the title,
Exhibition, WATCH, the two picks in the shared picker, then A on the pre-game and half-inning cards (scenes $0B
and $11) and START on scene $0F; both teams are CPU. A fixture is the whole machine where FIXTURES names it: at
bank 6 $B6F8, where the ball has cleared the fence and the mass scorer has not run, or at $D755, where state 2
begins. A state is saved with its observation logs emptied and its ROM image removed, so restore() loads it into
any ROM: stock and candidate start from one state and every later difference comes from the candidate's bytes.

The cache, build/homerunart32-fixtures/, holds one pickle per state and provenance.json: the input SHA-256, the
SHA-256 of every file that shapes a played state (HARNESS: the CPU model, the menu and picker drivers and this
module), the Python and py65 versions, and per state its game, hook, frame, cycle count, RAM summary and pickle
SHA-256. A state loads only when all of those match and its file hashes to the recorded digest; stale states
are played again from RESET. Unrelated files or malformed ownership records are refused without writes;
use a fresh cache directory in that case. A full regeneration plays four games in parallel and is bounded by the
48,080-frame 8-30 game (about 25 minutes on this machine); --quick needs the first home runs of two games (about
5 minutes). The cache is generated local data, never tracked, and a pickle loads only after its digest matches.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
import json
import multiprocessing
from pathlib import Path
import pickle
import sys

import build_homerunart32 as stage
from build_draw32 import sha256
from build_scoreart32 import write_atomic
from frontend32_test_machine import A, START, SCENE, choose, to_mode_menu
import render_menu32 as R
from test_pick32 import in_picker, move_to

ROOT = stage.ROOT
CACHE = stage.FIXTURES
CACHE_FORMAT = "homerunart32-fixtures/1"
HARNESS = ("tools/render_menu32.py", "tools/frontend32_test_machine.py", "tools/test_pick32.py", "tools/build_pick32.py",
           "tools/build_menuart32.py", "tools/homerunart32_fixtures.py")
STATE, HALVES, RUNS, FLAGS, OVER = 0x047C, 0x048A, 0x048B, 0x048E, 0x04D0
BAT_SIDE, TEAMS, SONG, ACTIVE, HITS, HR_STAT = 0x04ED, 0x04EF, 0x0401, 0x0555, 0x073A, 0x073C
LOGS = ("apu", "ppu_writes", "vram_late", "wram_access", "mapper", "partial", "reads", "zp_writes", "ticks",
        "tick_marks", "queue", "shows", "log")

GAMES = {"29-11": ((29, 11), 25080), "11-29": ((11, 29), 22960), "8-30": ((8, 30), 48080), "18-20": ((18, 20), 37570)}
QUICK_UNTIL = {"29-11": 3760, "11-29": 9230}
# name: (game, hook, frame, kind). The frames are where the policy reaches each hook on the pinned input; a run
# that passes one without its hook is fixture drift and fails loudly.
FIXTURES = {
    "solo 29-11 top 1st": ("29-11", "B6F8", 3749, "home run"),
    "two-run 11-29 bottom 1st": ("11-29", "B6F8", 9165, "home run"),
    "state 2 11-29 bottom 1st": ("11-29", "D755", 9225, "state 2"),
    "touched play 30-8 top 2nd": ("8-30", "B6F8", 12087, "touched play"),
    "solo 8-30 bottom 2nd": ("8-30", "B6F8", 16885, "home run"),
    "touched play 11-29 bottom 3rd": ("11-29", "B6F8", 22955, "touched play"),
    "touched play 29-11 top 3rd": ("29-11", "B6F8", 25071, "touched play"),
    "solo 18-20 bottom 4th": ("18-20", "B6F8", 31741, "home run"),
    "solo 20-18 top 5th": ("18-20", "B6F8", 37564, "home run"),
    "two-run 30-8 top 6th": ("8-30", "B6F8", 48076, "home run"),
}
QUICK_FIXTURES = ("solo 29-11 top 1st", "two-run 11-29 bottom 1st", "state 2 11-29 bottom 1st")


def harness():
    return {name: sha256((ROOT / name).read_bytes()) for name in HARNESS}


def environment():
    return {"python": sys.version.split()[0], "py65": version("py65")}


def snapshot(m):
    """The machine as pickle bytes: observation logs emptied, pads, hooks and the ROM image removed."""
    keep = {name: getattr(m, name) for name in (*LOGS, "vblank_work", "pad", "pad2", "on_pc", "rom", "chr_rom")}
    try:
        for name in LOGS:
            setattr(m, name, [])
        m.vblank_work = {m.frame: keep["vblank_work"][m.frame]} if m.frame in keep["vblank_work"] else {}
        m.pad = m.pad2 = None
        m.on_pc = {}
        m.rom = m.chr_rom = b""
        return pickle.dumps(m)
    finally:
        for name, value in keep.items():
            setattr(m, name, value)


def restore(data, rom):
    """A saved machine running `rom`, with released pads and no hooks."""
    m = pickle.loads(data)
    m.rom = rom
    m.chr_rom = rom[R.HEADER + m.nprg * 0x4000:]
    m.pad = m.pad2 = (lambda frame: 0)
    m.on_pc = {}
    return m


def summary(m, hook):
    r = m.ram
    return {"hook": hook, "frame": m.frame, "cycles": m.mpu.processorCycles, "prg": m.prg, "scene": r[SCENE],
            "state": r[STATE], "half": r[HALVES], "score": [r[RUNS], r[RUNS + 1]], "bat_side": r[BAT_SIDE],
            "teams": [r[TEAMS], r[TEAMS + 1]], "flags": r[FLAGS], "c1": r[0xC1],
            "slots": [r[ACTIVE + x] for x in (9, 10, 11, 12)], "hr": [r[HR_STAT], r[HR_STAT + 1]],
            "hits": [r[HITS], r[HITS + 1]], "song": r[SONG], "over": r[OVER]}


def watch(rom, teams):
    """A Driver from RESET through the mode menu, Exhibition WATCH and both picks."""
    d = to_mode_menu(rom)
    choose(d, 1, sub=2)
    in_picker(d)
    move_to(d, teams[0])
    d.press(A)
    move_to(d, teams[1])
    d.press(A, gap=0)
    return d


def step(d):
    """One step of the policy: A on the cards, START on scene $0F, otherwise one frame."""
    scene = d.m.ram[SCENE]
    if scene in (0x0B, 0x11):
        d.press(A, hold=2, after=1, gap=8)
    elif scene == 0x0F:
        d.press(START, hold=2, after=1, gap=8)
    else:
        d.m.frames(1)


def play(rom, game, until, names):
    """Play `game` from RESET to frame `until`, saving the named fixtures: {name: (pickle, summary)}."""
    teams, _ = GAMES[game]
    wanted = {(FIXTURES[n][1], FIXTURES[n][2]): n for n in names}
    d = watch(rom, teams)
    m, saved = d.m, {}

    def hook(tag, bank):
        def fire(mm):
            name = wanted.get((tag, mm.frame))
            if name and name not in saved and not mm.nmi_depth and (bank is None or mm.prg == bank):
                saved[name] = (snapshot(mm), summary(mm, tag))
        return fire
    m.on_pc[0xB6F8] = hook("B6F8", 6)
    m.on_pc[0xD755] = hook("D755", None)
    while m.frame < until:
        step(d)
    missing = sorted(set(names) - set(saved))
    if missing:
        raise AssertionError(f"fixture drift in game {game}: {', '.join(missing)} not reached at the pinned frames; "
                             "the harness or the input changed")
    return saved


def play_job(rom, game, until, names):
    return game, play(rom, game, until, names)


def load_cache(rom, cache=CACHE):
    """{name: (pickle, summary)} for every cached state whose provenance and digest match."""
    path = cache / "provenance.json"
    if not path.is_file():
        return {}
    try:
        record = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeError):
        return {}
    if (not isinstance(record, dict) or record.get("format") != CACHE_FORMAT or record.get("input_sha256") != sha256(rom)
            or record.get("harness") != harness() or record.get("environment") != environment()):
        return {}
    entries = record.get("states")
    if not isinstance(entries, dict):
        return {}
    found = {}
    for name, entry in entries.items():
        if name not in FIXTURES or not isinstance(entry, dict) or entry.get("file") != cache_name(name):
            continue
        info = entry.get("summary")
        if (not isinstance(info, dict) or info.get("frame") != FIXTURES[name][2]
                or info.get("hook") != FIXTURES[name][1]
                or not all(key in info for key in ("half", "bat_side", "slots", "score"))):
            continue
        file = cache / entry["file"]
        if file.is_file() and not file.is_symlink() and file.stat().st_nlink == 1:
            data = file.read_bytes()
            if sha256(data) == entry.get("sha256"):
                found[name] = (data, info)
    return found


def cache_name(name):
    return f"{name.replace(' ', '_')}.pkl"


def protect_cache(source, cache, inputs=()):
    cache = stage.output_path(cache)
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        raise ValueError(f"fixture cache {cache} is a link or not a directory")
    inputs = [*inputs, stage.REGISTRY, *stage.ASSETS.rglob('*')]
    if cache != stage.FIXTURES:
        stage.refuse_inside(cache, stage.FIXTURES)
        inputs.extend(stage.FIXTURES.rglob('*'))
    planned = {'provenance.json', *(cache_name(name) for name in FIXTURES)}
    for name in sorted(planned):
        target = cache / name
        stage.prior.protect_output(source, target, inputs)
        for directory in (stage.ASSETS, stage.BUILD / 'homerunart32-design', stage.BUILD / 'vendor'):
            stage.refuse_inside(target, directory)
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError(f"fixture output is linked or not a regular file: {target}")
    owned = {'provenance.json'}
    record_path = cache / 'provenance.json'
    if record_path.exists():
        try:
            record = json.loads(record_path.read_text())
        except (ValueError, UnicodeError):
            raise ValueError(f"refusing unrelated or corrupt cache provenance: {record_path}") from None
        if (not isinstance(record, dict) or record.get('format') != CACHE_FORMAT
                or not isinstance(record.get('states'), dict)):
            raise ValueError(f"refusing unrelated or corrupt cache provenance: {record_path}")
        for name, entry in record['states'].items():
            if name not in FIXTURES or not isinstance(entry, dict) or entry.get('file') != cache_name(name):
                raise ValueError(f"invalid fixture ownership in {record_path}")
            owned.add(entry['file'])
    if cache.exists():
        for path in cache.iterdir():
            if path.name not in owned or not path.is_file() or path.is_symlink():
                raise ValueError(f"fixture cache contains an unowned file: {path}")
    return cache


def save_cache(source, rom, states, cache=CACHE, inputs=()):
    cache = protect_cache(source, cache, inputs)
    if Path(source).read_bytes() != rom:
        raise ValueError('fixture input changed during generation')
    if set(states) - set(FIXTURES):
        raise ValueError('unknown fixture name')
    entries = {}
    for name in sorted(states):
        data, info = states[name]
        file = cache / cache_name(name)
        write_atomic(file, data)
        entries[name] = {"file": file.name, "sha256": sha256(data), "summary": info,
                         "game": FIXTURES[name][0], "hook": FIXTURES[name][1], "kind": FIXTURES[name][3]}
    record = {"format": CACHE_FORMAT, "input_sha256": sha256(rom), "harness": harness(), "environment": environment(),
              "policy": "RESET; START; Exhibition WATCH; picks; A on scenes $0B/$11, START on $0F",
              "games": {g: {"teams": list(t), "until": u} for g, (t, u) in GAMES.items()}, "states": entries}
    write_atomic(cache / "provenance.json", (json.dumps(record, indent=1) + "\n").encode())


def states(source, names, workers=4, refresh=False, cache=CACHE, log=print, inputs=()):
    """{name: (pickle, summary)} for `names`, from the cache or played again from RESET; the cache is updated."""
    rom = Path(source).read_bytes()
    if sha256(rom) != stage.BASE_SHA256:
        raise ValueError("fixtures come from the pinned analysisart32 input")
    cache = protect_cache(source, cache, inputs)
    found = {} if refresh else load_cache(rom, cache)
    missing = [n for n in names if n not in found]
    if missing:
        quick = set(missing) <= set(QUICK_FIXTURES)
        plan = {g: (QUICK_UNTIL[g] if quick else GAMES[g][1],
                    [n for n in FIXTURES if FIXTURES[n][0] == g and (n in QUICK_FIXTURES or not quick)])
                for g in sorted({FIXTURES[n][0] for n in missing})}
        log(f"fixtures: playing {', '.join(f'{g} to frame {u}' for g, (u, _) in plan.items())} from RESET "
            f"({'refresh' if refresh else 'not cached'})")
        with ProcessPoolExecutor(max_workers=max(1, min(workers, len(plan))),
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            for _, saved in pool.map(play_job, *zip(*[(rom, g, u, n) for g, (u, n) in plan.items()])):
                found.update(saved)
        save_cache(source, rom, found, cache, inputs)
    return {n: found[n] for n in names}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned analysisart32 input")
    ap.add_argument("--quick", action="store_true", help="only the states --quick tests need")
    ap.add_argument("--refresh", action="store_true", help="play every needed game again even if cached")
    ap.add_argument("--cache", type=Path, default=CACHE, help="cache directory (default %(default)s)")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    names = QUICK_FIXTURES if args.quick else tuple(FIXTURES)
    try:
        found = states(args.rom, names, args.jobs, args.refresh, stage.output_path(args.cache))
    except (OSError, ValueError, AssertionError) as exc:
        ap.exit(2, f"homerunart32_fixtures: {exc}\n")
    for name in names:
        info = found[name][1]
        print(f"{name}: frame {info['frame']} {info['hook']}, half {info['half']}, side {info['bat_side']}, "
              f"slots {info['slots']}, score {info['score']}, pickle {sha256(found[name][0])[:12]}")
    print(f"{len(names)} fixtures in {args.cache}")


if __name__ == "__main__":
    main()
