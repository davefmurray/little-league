#!/usr/bin/env python3
"""Type a v1 password through the game's controller-driven keyboard.

    python3 tools/probe_password_ui.py --rom build/password32.nes --seed 31 --played 15
"""
import argparse
from collections import deque
import hashlib
from pathlib import Path

import password32
import romdev
from soak_bracket import press, rd_cart, rd_sys, step, wait_for


def key_path(rom, start, goal):
    bank = 16 + 0x4000
    pointers = [int.from_bytes(rom[bank + address - 0x8000:bank + address - 0x8000 + 2], "little")
                for address in range(0xA78C, 0xA794, 2)]
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        key, path = queue.popleft()
        if key == goal:
            return path
        for button, pointer in zip(("up", "down", "left", "right"), pointers):
            target = rom[bank + pointer - 0x8000 + key]
            if target != 255 and target not in seen:
                seen.add(target)
                queue.append((target, path + [button]))
    raise AssertionError(f"keyboard key {goal} is unreachable from {start}")


def type_password(rom, text):
    for position, character in enumerate(text):
        target = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".index(character)
        for button in key_path(rom, rd_sys(0xBC)[0], target):
            press(button, 2)
            step(3)
        assert rd_sys(0xBC)[0] == target, (position, character, rd_sys(0xBC).hex())
        press("a", 2)
        step(3)
        assert rd_sys(0x0643 + position)[0] == ord(character), (position, character)
    assert rd_sys(0xBC)[0] == 38


def open_entry(rom_path, menu):
    romdev.call("loadMedia", {"platform": "nes", "path": str(rom_path.resolve())})
    step(120)
    press("start", 3)
    step(20)
    press("a", 3)
    step(20)
    if menu == "list":
        press("down", 3)
        step(20)
    press("a", 3)
    wait_for(lambda: rd_sys(0x047B)[0] == 0x19, 240, 10, "password keyboard")
    step(30)


def list_flow(text, played, shot):
    heap = rd_cart(0x7700, 63)

    def matchup():
        press("a", 3)
        step(30)
        assert rd_sys(0x047B, 2) == bytes((0x13, 8))
        assert rd_sys(0x0643, 26) == password32.display(text)
        press("a", 2)
        wait_for(lambda: rd_sys(0x047B, 2) == bytes((0x13, 3)), 240, 10, "matchup")
        step(20)
        assert sorted(rd_sys(0x04EF, 2)) == sorted(heap[2 * played:2 * played + 2])

    matchup()
    print("actual password display and launched matchup match restored state", flush=True)
    press("b", 3)
    step(60)
    assert rd_sys(0x047B)[0] in (6, 7)
    press("a", 3)
    step(30)
    press("down", 3)
    step(20)
    press("a", 10)
    step(60)
    assert rd_sys(0x27)[0] == 11 and rd_sys(0x07F0)[0] == 1
    assert rd_cart(0x7700, 63) == heap and rd_sys(0x07FC)[0] == played
    romdev.call("frame", {"op": "screenshot", "path": shot})
    print("active LIST OF TEAMS preserves heap and match index", flush=True)
    press("b", 3)
    step(60)
    assert rd_sys(0x047B)[0] in (6, 7)
    press("a", 3)
    step(30)
    press("a", 10)
    step(60)
    assert rd_sys(0x27)[0] == 11 and rd_sys(0x07F0)[0] == 0
    assert rd_sys(0x07FC)[0] == played and rd_cart(0x7700, 63) == heap
    matchup()
    print("B returns to title; CONTINUE preserves the bracket and launches its actual next pair", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--played", type=int, default=15)
    ap.add_argument("--results", type=lambda value: int(value, 0))
    ap.add_argument("--cpu-mask", type=lambda value: int(value, 0))
    ap.add_argument("--menu", choices=("continue", "list"), default="continue")
    ap.add_argument("--session", default="password32-ui")
    ap.add_argument("--invalid", action="store_true")
    ap.add_argument("--list-flow", action="store_true",
                    help="exercise display, active LIST, title return and CONTINUE matchup")
    ap.add_argument("--shot", default="/tmp/password32-restored.png")
    ap.add_argument("--state-path", type=Path,
                    help="save the restored bracket for a subsequent match probe")
    args = ap.parse_args()
    romdev.SESSION = args.session
    rom = args.rom.read_bytes()
    results = args.results if args.results is not None else 0x55555555 & ((1 << args.played) - 1)
    mask = args.cpu_mask if args.cpu_mask is not None else 0xFFFFFFFF ^ (1 << args.seed)
    state = args.seed, args.played, results, mask
    text = password32.encode(*state)
    if args.invalid:
        text = text[:-1] + ("1" if text[-1] != "1" else "A")
    print(f"ROM SHA256 {hashlib.sha256(rom).hexdigest()}", flush=True)
    print(f"controller-only menu={args.menu} seed={args.seed} played={args.played} results={results:08X} mask={mask:08X} invalid={args.invalid}", flush=True)
    open_entry(args.rom, args.menu)
    type_password(rom, text)
    assert rd_sys(0xC2)[0] == 0
    press("a", 1 if args.invalid else 10)
    step(1 if args.invalid else 60)
    if args.invalid:
        assert rd_sys(0x07ED)[0] == 0
        assert rd_sys(0x047B)[0] == 0x19
        assert rd_sys(0xC2)[0] == 1
        print("corrupt password rejected on the original entry screen", flush=True)
        romdev.call("frame", {"op": "screenshot", "path": args.shot})
        press("a", 3)
        step(30)
        assert rd_sys(0xC2)[0] == 0
        for button in key_path(rom, rd_sys(0xBC)[0], 37):
            press(button, 2)
            step(3)
        for _ in range(21):
            press("a", 2)
            step(3)
        assert rd_sys(0xBD)[0] == 0
        type_password(rom, password32.encode(*state))
        press("a", 10)
        step(60)
        assert rd_sys(0x27)[0] == 11 and rd_sys(0x07FC)[0] == args.played
        assert rd_cart(0x7700)[0] == args.seed
        print("error dismissal, keyboard rewind and corrected password restore pass", flush=True)
    else:
        heap = bytes(255 if team is None else team for team in
                     password32.advance(password32.seed_order(args.seed), args.played, results))
        assert rd_cart(0x7700, 63) == heap
        assert rd_sys(0x07FC)[0] == args.played
        actual_mask = rd_sys(0x074B, 2) + rd_sys(0x07F1, 2)
        assert actual_mask == mask.to_bytes(4, "little"), actual_mask.hex()
        assert rd_sys(0x07ED)[0] != 0 and rd_sys(0x07EF)[0] == 0x32
        assert rd_sys(0x27)[0] == 11
        print("restored heap, match index and all 32 ownership bits; held END press did not launch", flush=True)
        romdev.call("state", {"op": "save", "name": "password-restored"})
        if args.state_path:
            romdev.call("state", {"op": "save", "path": str(args.state_path.resolve())})
        if args.played == 31:
            press("a", 3)
            step(60)
            assert rd_sys(0x047B)[0] in (6, 7) and rd_sys(0x07FC)[0] == 31
            print("completed tournament A returns to title without launching match 31", flush=True)
            press("a", 3)
            step(30)
            press("a", 10)
            step(60)
            assert rd_sys(0x27)[0] == 11 and rd_sys(0x07FC)[0] == 31
            press("b", 3)
            step(60)
            assert rd_sys(0x047B)[0] in (6, 7) and rd_sys(0x07FC)[0] == 31
            print("CONTINUE reopens the completed bracket; B returns to title", flush=True)
        elif args.list_flow:
            list_flow(text, args.played, args.shot)
    if not args.invalid and not args.list_flow:
        romdev.call("frame", {"op": "screenshot", "path": args.shot})
    print(f"screenshot {args.shot}", flush=True)


if __name__ == "__main__":
    main()
