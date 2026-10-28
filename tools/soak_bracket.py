#!/usr/bin/env python3
"""Drive a bracket through matches and validate recorded results.

    python3 tools/soak_bracket.py --rom build/results32.nes --matches 31 \
        --winner live-score --require-complete --check-stack

Requires romdev on localhost:7331. --state resumes the stock team-select
CONTINUE/END prompt; otherwise navigation starts at boot. Speed mode
forces CPU control through RAM writes. Watch mode uses controller input.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, "tools")
import romdev


def rd_sys(addr, n=1):
    r = romdev.call("memory", {"op": "read", "region": "system_ram",
                               "offset": addr, "length": n})
    return bytes.fromhex(r["hex"])


def rd_cart(addr, n=1):
    r = romdev.call("memory", {"op": "read", "region": "nes_cart_ram",
                               "offset": addr - 0x6000, "length": n})
    return bytes.fromhex(r["hex"])


def step(n):
    romdev.call("frame", {"op": "step", "count": n})


def press(button, frames=2):
    romdev.call("input", {"op": "press", "button": button, "frames": frames})


def wait_for(pred, max_frames, chunk=250, label="", on_scene=None):
    done = 0
    while done < max_frames:
        if pred():
            return done
        if on_scene is not None:
            on_scene()
        step(chunk)
        done += chunk
    if pred():
        return done
    raise SystemExit(f"timeout waiting for {label} after {max_frames} frames")


def leave_lineup():
    """Walk the pre-game order screens back to END, then confirm.

    The high-team path ($06E1=1) opens the change-orders editor as a
    multi-page menu and B steps back two states at a time ($BA -= 2).
    The old B -> A alternation re-entered the editor: B backed out one
    page, A selected the highlighted item again.  Press B until the
    scene changes (or six tries), then A confirms END if still on 0F.
    """
    for _ in range(6):
        if rd_sys(0x047B)[0] != 0x0F:
            return
        press("b", 2)
        step(15)
    if rd_sys(0x047B)[0] == 0x0F:
        press("a", 2)
        step(30)


def leave_lineup_top():
    leave_lineup()


def navigate_to_prompt():
    """Boot the stock flow to the team-select CONTINUE/END prompt."""
    step(120)
    press("start", 4)
    step(30)
    press("a", 4)          # Championship Series
    step(60)
    press("down", 4)
    press("down", 4)
    press("a", 4)          # Start New Series
    step(60)
    press("right", 6)      # pick a team
    press("a", 2)          # CONTINUE/END prompt
    step(30)


def enter_game(match, mode):
    for _ in range(120):
        if rd_sys(0x07FC)[0] != match:
            return
        scene, substate = rd_sys(0x047B, 2)
        if scene != 0x13:
            return
        if substate == 6 and mode == "watch" and rd_sys(0x047E)[0] == 0:
            press("down", 2)
        elif substate in (3, 6, 8):
            press("a", 2)
        step(10)
    raise SystemExit(f"match {match}: pre-game screen did not advance")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="build/direct17.nes")
    ap.add_argument("--state", default="",
                    help="savestate at CONTINUE/END (CONTINUE selected); "
                         "omit to navigate from boot")
    ap.add_argument("--matches", type=int, default=31)
    ap.add_argument("--shot-every", type=int, default=0)
    ap.add_argument("--session", default="llbcs",
                    help="romdev session owned by this run")
    ap.add_argument("--check-stack", action="store_true",
                    help="require the same stack pointer at every match entry")
    ap.add_argument("--winner", choices=("forced", "score", "live-score"), default="forced",
                    help="forced: first team wins; score: bracket-order scores; "
                         "live-score: score side mapped through the live team IDs")
    ap.add_argument("--require-complete", action="store_true",
                    help="require the stock game-over flag before bracket advancement")
    ap.add_argument("--mode", choices=("speed", "watch"), default="speed",
                    help="speed: SPEED MODE (per-pitch input may be needed); "
                         "watch: WATCH THE GAME with controller-only cutscene/score-screen input")
    args = ap.parse_args()
    romdev.SESSION = args.session
    entry_stack = None

    with open(args.rom, "rb") as source:
        print(f"ROM SHA256 {hashlib.sha256(source.read()).hexdigest()}", flush=True)
    romdev.call("loadMedia", {"platform": "nes",
                              "path": os.path.abspath(args.rom)})
    if args.state:
        romdev.call("state", {"op": "load", "path": args.state})
        print(f"loaded {args.rom}, state {args.state}")
    else:
        navigate_to_prompt()
        print(f"loaded {args.rom}, navigated to CONTINUE/END")

    # CONTINUE -> END, then A enters the bracket and launches match 0.
    press("right", 4)
    press("a", 2)
    step(60)
    press("a", 2)
    step(30)

    for m in range(args.matches):
        idx = rd_sys(0x07FC)[0]
        if idx != m:
            raise SystemExit(f"match {m}: $07FC={idx:02X}, expected {m:02X}")
        pair = rd_cart(0x7700 + 2 * m, 2)
        if pair == b"\xff\xff":
            raise SystemExit(f"match {m}: pair is unset")
        if m > 0:
            press("a", 2)
            step(10)

        wait_for(lambda: rd_sys(0x047B)[0] == 0x13, 120, 10,
                 f"match {m} password")
        if args.check_stack:
            cpu = romdev.call("cpu", {"op": "read"})
            stack = cpu["registers"]["S"]
            if entry_stack is None:
                entry_stack = stack
            if stack != entry_stack:
                raise SystemExit(f"match {m}: stack ${stack:02X}, "
                                 f"expected ${entry_stack:02X}")
            print(f"match {m:02d}: stack ${stack:02X} OK")
        enter_game(m, args.mode)
        if args.mode == "watch":
            if rd_sys(0x07FC)[0] == m:
                step(500)
            if rd_sys(0x07FC)[0] == m:
                press("a", 2)

            def handle_watch_scene():
                scene = rd_sys(0x047B)[0]
                if scene == 0x0F:
                    leave_lineup_top()
                elif scene == 0x0B:
                    press("a", 2)

            wait_for(lambda: rd_sys(0x07FC)[0] == m + 1, 400000, 500,
                     f"match {m} result", on_scene=handle_watch_scene)
        else:
            # The stock field waits for a human pitch on some pairings.
            # Reassert both-COM at the field and advance a waiting cutscene.
            seen = {"cut": False, "com": False}

            def handle_scene():
                scene = rd_sys(0x047B)[0]
                if scene == 0x0F:
                    leave_lineup()
                elif scene == 0x11 and not seen["cut"]:
                    press("a", 2)
                    seen["cut"] = True
                elif scene == 0x03 and not seen["com"]:
                    romdev.call("memory", {"op": "write",
                                           "region": "system_ram",
                                           "offset": 0x04EB, "hex": "8080"})
                    romdev.call("memory", {"op": "write",
                                           "region": "system_ram",
                                           "offset": 0x04E9, "hex": "00"})
                    seen["com"] = True

            wait_for(lambda: rd_sys(0x07FC)[0] == m + 1, 400000, 500,
                     f"match {m} result", on_scene=handle_scene)

        slot = rd_cart(0x7720 + m)[0]
        scores = rd_sys(0x048B, 2)
        if args.require_complete and not rd_sys(0x04D0)[0]:
            raise SystemExit(f"match {m}: bracket advanced before game over, half-inning {rd_sys(0x048A)[0]}")
        if args.winner == "live-score":
            live = rd_sys(0x04EF, 2)
            if sorted(live) != sorted(pair):
                raise SystemExit(f"match {m}: live teams {live.hex()} differ from bracket {pair.hex()}")
            expected = pair[0] if scores[0] == scores[1] else live[int(scores[0] < scores[1])]
            note = f"live {live[0]:02X}/{live[1]:02X}, score {scores[0]}-{scores[1]}, game-over {rd_sys(0x04D0)[0]}"
        elif args.winner == "score":
            expected = pair[0] if scores[0] >= scores[1] else pair[1]
            note = f"score {scores[0]}-{scores[1]}"
        else:
            expected = pair[0]
            note = f"forced {pair[0]:02X}"
        ok = slot == expected
        print(f"match {m:02d}: {pair[0]:02X} v {pair[1]:02X} -> "
              f"$77{0x20 + m:02X}={slot:02X} ({note}) "
              f"{'OK' if ok else 'MISMATCH'}  index={rd_sys(0x07FC)[0]:02X}")
        if not ok:
            raise SystemExit(f"match {m}: winner mismatch")
        if args.shot_every and (m + 1) % args.shot_every == 0:
            romdev.call("frame", {"op": "screenshot",
                                  "path": f"/tmp/soak-{m + 1:02d}.png"})

    slots = rd_cart(0x7700, 63)
    print("slots:", slots.hex(" "))
    if args.matches == 31:
        champ = slots[62]
        print(f"champion slot 62 ($773E) = {champ:02X}")
        if champ == 0xFF:
            raise SystemExit("champion slot still empty")
    romdev.call("state", {"op": "save", "name": "soak-final"})
    romdev.call("frame", {"op": "screenshot", "path": "/tmp/soak-final.png"})
    print("saved state soak-final and /tmp/soak-final.png")


if __name__ == "__main__":
    main()
