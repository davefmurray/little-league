#!/usr/bin/env python3
"""Restore a tournament through the keyboard and check its matchup label tiles.

    .venv/bin/python tools/probe_matchup_round.py --rom build/visualtables32.nes --played 30 --label FINALS
"""
import argparse
import hashlib
from pathlib import Path

import password32
import romdev
from probe_password_ui import open_entry, type_password
from soak_bracket import press, rd_cart, rd_sys, step, wait_for
from test_teamnames32 import Probe


def label_tiles(rom, label):
    probe = Probe(rom, 5)
    text = b"\xa1\xc6" + label.encode("ascii").ljust(14) + b"\xff"
    probe.m[0x06B3:0x06B3 + len(text)] = text
    probe.run(0xC713)
    probe.run(0xC53A)
    return probe.cpu.memory.vram


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--played", type=int, choices=range(31), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--seed", type=int, choices=range(32), default=31)
    parser.add_argument("--check-flags", action="store_true")
    parser.add_argument("--session", default="matchup-round")
    parser.add_argument("--output", type=Path, default=Path("/tmp/matchup-round"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rom = args.rom.read_bytes()
    romdev.SESSION = args.session
    mask = 0xFFFFFFFF ^ (1 << args.seed)
    password = password32.encode(args.seed, args.played, 0, mask)
    print(f"ROM SHA256 {hashlib.sha256(rom).hexdigest()}", flush=True)
    print(f"controller-only seed={args.seed} played={args.played} results=0 mask={mask:08X} expected={args.label!r}", flush=True)
    open_entry(args.rom, "continue")
    type_password(rom, password)
    press("a", 10)
    step(60)
    assert rd_sys(0x27)[0] == 11
    assert rd_sys(0x07FC)[0] == args.played
    heap = rd_cart(0x7700, 63)
    press("a", 3)
    step(30)
    assert rd_sys(0x047B, 2) == bytes((0x13, 8))
    press("a", 2)
    wait_for(lambda: rd_sys(0x047B, 2) == bytes((0x13, 3)), 240, 5, "matchup")
    step(15)
    assert rd_sys(0x0746)[0] == 0
    assert rd_sys(0x07FC)[0] == args.played
    live = rd_sys(0x04EF, 2)
    assert sorted(live) == sorted(heap[args.played * 2:args.played * 2 + 2])
    raw = romdev.call("memory", {"op": "read", "region": "nes_nametables", "offset": 0, "length": 2048})
    nametables = bytes.fromhex(raw["hex"])
    stem = args.output / f"match-{args.played:02d}"
    stem.with_suffix(".bin").write_bytes(nametables)
    romdev.call("frame", {"op": "screenshot", "path": str(stem.with_suffix(".png").resolve())})
    if args.check_flags:
        raw_oam = romdev.call("memory", {"op": "read", "region": "nes_oam", "offset": 0, "length": 256})
        oam = bytes.fromhex(raw_oam["hex"])
        stem.with_suffix(".oam.bin").write_bytes(oam)
        for side, team in enumerate(live):
            top = 56 + side * 96
            flag_sprites = [oam[i:i + 4] for i in range(0, 256, 4)
                            if top <= oam[i] < top + 24 and 48 <= oam[i + 3] < 72]
            assert len(flag_sprites) == (9 if team < 16 else 0), (team, flag_sprites)
        print("low-team flags retain nine sprites; high-team flag areas contain no sprites", flush=True)
    for address, tile in label_tiles(rom, args.label).items():
        actual = nametables[(address - 0x2000) % 2048]
        assert actual == tile, (args.label, hex(address), actual, tile)
    print(f"label tiles match {args.label!r}; live={live.hex()} stock counter=0; screenshot {stem.with_suffix('.png')}", flush=True)


if __name__ == "__main__":
    main()
