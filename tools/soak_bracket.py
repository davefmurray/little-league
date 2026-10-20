#!/usr/bin/env python3
"""Drive the P1 bracket through N matches with the forced-winner hook.

    python3 tools/soak_bracket.py --rom build/direct17.nes --matches 31

Assumes a romdev server on 127.0.0.1:7331.  With --state, restores a
savestate at the stock team-select CONTINUE/END prompt (CONTINUE
selected); without it, drives the boot -> title -> Championship -> Start
New Series -> team-select path itself.

For each match:
  1. bracket A launches the pair at $7700[2m], $7700[2m+1];
  2. A through password, matchup and SPEED MODE;
  3. wait for the scene-0B hook to write $7720+m and bump $07FC;
  4. verify the slot equals the forced winner (the first team).
"""
import argparse
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
    """Confirm the pre-game order screens (both teams).

    The top-level handler (bank1 $9BAB) treats B as "select END": it sets
    $BE=7, and A confirms.  This is deterministic; the old RIGHT x3 walk
    depended on the hidden $BE selection and often entered a submenu.
    """
    for _ in range(2):
        if rd_sys(0x047B)[0] != 0x0F:
            return
        press("b", 2)
        step(10)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="build/direct17.nes")
    ap.add_argument("--state", default="",
                    help="savestate at CONTINUE/END (CONTINUE selected); "
                         "omit to navigate from boot")
    ap.add_argument("--matches", type=int, default=31)
    ap.add_argument("--shot-every", type=int, default=0)
    ap.add_argument("--winner", choices=("forced", "score"), default="forced",
                    help="forced: first team always wins; score: use $048B/$048C")
    ap.add_argument("--mode", choices=("speed", "watch"), default="speed",
                    help="speed: SPEED MODE (per-pitch input may be needed); "
                         "watch: WATCH THE GAME (one cutscene A, then auto)")
    args = ap.parse_args()

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
    step(15)

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
        press("a", 2)
        step(60)
        press("a", 2)
        step(60)
        if args.mode == "watch":
            press("down", 2)
            step(10)
        press("a", 2)
        if args.mode == "watch":
            # The pre-match cutscene waits for A; after that WATCH runs
            # itself to the box score (the score may be 0-0, a tie -> A).
            step(500)
            press("a", 2)
            wait_for(lambda: rd_sys(0x07FC)[0] == m + 1, 20000, 500,
                     f"match {m} result",
                     on_scene=lambda: (leave_lineup_top()
                                       if rd_sys(0x047B)[0] == 0x0F else None))
        else:
            wait_for(lambda: rd_sys(0x07FC)[0] == m + 1, 30000, 500,
                     f"match {m} result",
                     on_scene=lambda: (leave_lineup()
                                       if rd_sys(0x047B)[0] == 0x0F else None))

        slot = rd_cart(0x7720 + m)[0]
        scores = rd_sys(0x048B, 2)
        if args.winner == "score":
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
