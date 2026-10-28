#!/usr/bin/env python3
"""Capture team-label screens using controller input only.

    python3 tools/probe_team_names.py --rom build/password32.nes --team 31

Screenshots require visual inspection. The optional HUD check verifies
all five label tiles; other checks cover navigation and ownership.
"""
import argparse
import hashlib
import json
from pathlib import Path

import romdev
from soak_bracket import leave_lineup, navigate_selector, press, rd_sys, step


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--team", type=int, choices=range(32), default=31)
    ap.add_argument("--session", default="team-names-ui")
    ap.add_argument("--bracket-state", type=Path, help="resume a bracket with --team as its human team")
    ap.add_argument("--output", type=Path, default=Path("/tmp/team-names-ui"))
    ap.add_argument("--check-hud", action="store_true",
                    help="require canonical codes and padding in both high-team field HUD labels")
    args = ap.parse_args()
    if args.check_hud and args.team < 16:
        ap.error("--check-hud applies to high teams; stock low-team labels are preserved")
    args.output.mkdir(parents=True, exist_ok=True)
    romdev.SESSION = args.session
    print(f"ROM SHA256 {hashlib.sha256(args.rom.read_bytes()).hexdigest()}", flush=True)
    print(f"controller-only human team {args.team:02X}, bracket_state={args.bracket_state}", flush=True)
    romdev.call("loadMedia", {"platform": "nes", "path": str(args.rom.resolve())})
    if args.bracket_state:
        romdev.call("state", {"op": "load", "path": str(args.bracket_state.resolve())})
    else:
        navigate_selector(args.team)
    press("a", 2)
    step(30)
    captured = set()
    for _ in range(600):
        scene, substate = rd_sys(0x047B, 2)
        label = None
        if scene == 0x13 and substate == 3:
            label = "matchup"
        elif scene == 0x11 and substate == 1:
            label = "cutscene"
        elif scene == 0x0F:
            label = "order"
        elif scene == 0x03:
            label = "field"
        if label is not None and label not in captured:
            step(15)
            path = args.output / f"{args.team:02x}-{label}.png"
            romdev.call("frame", {"op": "screenshot", "path": str(path.resolve())})
            for region, length in (("nes_nametables", 2048), ("nes_oam", 256)):
                data = romdev.call("memory", {"op": "read", "region": region,
                                             "offset": 0, "length": length})
                path.with_suffix(f".{region}.bin").write_bytes(bytes.fromhex(data["hex"]))
            captured.add(label)
            print(f"{label}: scene {scene:02X}/{substate:02X}; screenshot {path}", flush=True)
        if scene == 0x03:
            live = rd_sys(0x04EF, 2)
            ownership = rd_sys(0x04EB, 2)
            human_side = live.index(args.team)
            assert ownership[human_side] == 0
            assert ownership[human_side ^ 1] == 0x80
            print(f"live teams {live.hex()}, ownership {ownership.hex()}, human side {human_side}", flush=True)
            assert {"matchup", "order", "field"} <= captured
            if args.check_hud:
                metadata = Path(__file__).resolve().parent.parent / "data" / "teams32.json"
                teams = json.loads(metadata.read_text())["teams"]
                for side, team_id in enumerate(live):
                    if team_id < 16:
                        continue
                    expected = next(team["code"] for team in teams if team["id"] == team_id)
                    tiles = romdev.call("memory", {"op": "read", "region": "nes_nametables",
                                                   "offset": (9 + side) * 32 + 1, "length": 5})
                    actual = bytes.fromhex(tiles["hex"])
                    assert actual == expected.encode("ascii").ljust(5), (actual, expected)
                    print(f"field HUD side {side} has canonical label {expected!r} padded to five tiles", flush=True)
            print("field reached with selected team human; inspect captured labels", flush=True)
            return
        if scene == 0x13 and substate in (3, 6, 8):
            press("a", 2)
        elif scene == 0x11:
            step(30)
            press("a", 2)
        elif scene == 0x0F:
            leave_lineup()
        step(5)
    raise SystemExit("field was not reached")


if __name__ == "__main__":
    main()
