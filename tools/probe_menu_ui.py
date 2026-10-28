#!/usr/bin/env python3
"""Exercise the grid selector, bracket and stock menu music in romdev.

    .venv/bin/python tools/probe_menu_ui.py --rom build/menuart32.nes --output build/menu-ui

Uses controller input and memory readback, without changing game RAM.
Audio checks measure APU activity; WAVs and screenshots require human inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path

import romdev
from soak_bracket import open_selector, press, rd_cart, rd_sys, step


def capture(out, name, rom):
    assert rd_sys(0x2C, 2) == b"\x01\x01"
    assert rd_sys(0x0401)[0] == 6
    chr_data = bytes.fromhex(romdev.call("memory", {
        "op": "read", "region": "nes_chr", "offset": 0, "length": 8192, "inline": True})["hex"])
    chr_start = 16 + 16 * 0x4000
    assert chr_data[:4096] == rom[chr_start:chr_start + 4096]
    assert chr_data[4096:] == rom[chr_start + 25 * 4096:chr_start + 26 * 4096]
    romdev.call("frame", {"op": "screenshot", "path": str(out / f"{name}.png")})
    before = rd_sys(0x07F3)[0]
    audio = romdev.call("audioDebug", {"op": "inspect", "chip": "nes", "frames": 180, "sampleEvery": 1})
    assert (rd_sys(0x07F3)[0] - before) & 255 == 180
    notes = {event.get("note") for channel in ("pulse1", "pulse2", "triangle")
             for event in audio["timeline"][channel] if event.get("playing")}
    assert len(notes) > 3 and audio["transitions"] > 20, audio
    (out / f"{name}-audio.json").write_text(json.dumps(audio, indent=2) + "\n")
    romdev.call("audioDebug", {"op": "record", "frames": 180, "path": str(out / f"{name}.wav")})
    print(f"{name}: CHR(0,25), song06, 180 menu ticks, {len(notes)} notes, "
          f"{audio['transitions']} APU transitions; PNG/WAV saved", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--session", default="menuart32-ui")
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.read_bytes()
    romdev.SESSION = args.session
    print(f"ROM SHA256 {hashlib.sha256(rom).hexdigest()}", flush=True)
    for team in range(32):
        romdev.call("loadMedia", {"platform": "nes", "path": str(args.rom.resolve())})
        open_selector(team, args.rom)
        assert rd_sys(0x07C0, 2) == bytes((team >> 3, team & 7))
        if team in (0, 31):
            capture(out, f"selector-{team:02d}", rom)
        press("a", 10)
        step(30)
        assert rd_cart(0x7700)[0] == team and rd_sys(0x07FC)[0] == 0
        mask = rd_sys(0x074B, 2) + rd_sys(0x07F1, 2)
        assert int.from_bytes(mask, "little") == 0xFFFFFFFF ^ (1 << team)
        assert rd_sys(0x27)[0] == 11
        print(f"team {team:02X}: grid choice, seed, ownership and held-A handoff pass", flush=True)
    capture(out, "bracket-00", rom)
    romdev.call("state", {"op": "save", "path": str(out / "bracket-00.state")})
    press("a", 2)
    step(30)
    assert rd_sys(0x2C, 2) == b"\x00\x00"
    assert rd_sys(0x047B)[0] == 0x13
    print("bracket launch restores both NMI guards and reaches password display", flush=True)


if __name__ == "__main__":
    main()
