#!/usr/bin/env python3
"""State-only 31-match soak: call the real ROM winner routine 31 times.

    python3 tools/state_soak.py --rom build/direct19-rts.nes

Uses tools/build_winner_rts.py: the bank11 $83A0 routine ends with RTS
instead of JMP $8000, so the debugger can call it and return.  Each call
gets a controlled 1-0 score, reads the real pair from $7700 (2m/2m+1),
writes the real winner to $7720+m, and increments $07FC.

This is the documented fallback for champion math when the stock game flow
cannot be forced through the match-5 field.  The in-context game proofs for
matches 0/1/8/16 remain the real-flow evidence.
"""
import argparse
import os
import sys

sys.path.insert(0, "tools")
import romdev
import soak_bracket as s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="build/direct19-rts.nes")
    args = ap.parse_args()

    romdev.call("loadMedia", {"platform": "nes",
                              "path": os.path.abspath(args.rom)})
    s.navigate_to_prompt()
    s.press("right", 4)
    s.press("a", 1)                 # enter the bracket without launching A
    s.step(60)
    if s.rd_sys(0x07FC)[0] != 0:
        raise SystemExit(f"bracket index is {s.rd_sys(0x07FC)[0]:02X}, expected 0")
    print(f"bracket ready, pair {s.rd_cart(0x7700, 2).hex(' ')}")

    for m in range(31):
        pair = s.rd_cart(0x7700 + 2 * m, 2)
        if pair == b"\xff\xff":
            raise SystemExit(f"match {m}: pair unset")
        # Team A wins 1-0; the winner routine chooses A when $048B >= $048C.
        romdev.call("memory", {"op": "write", "region": "system_ram",
                               "offset": 0x048B, "hex": "0100"})
        r = romdev.call("cpu", {"op": "call", "pc": 0x83A0,
                                "maxInstructions": 2000})
        if not r.get("returned"):
            raise SystemExit(f"match {m}: winner call did not return")
        slot = s.rd_cart(0x7720 + m)[0]
        index = s.rd_sys(0x07FC)[0]
        ok = slot == pair[0] and index == m + 1
        print(f"match {m:02d}: {pair[0]:02X} v {pair[1]:02X} -> "
              f"$77{0x20 + m:02X}={slot:02X} index={index:02X} "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            raise SystemExit(f"match {m}: expected {pair[0]:02X}, "
                             f"index {m + 1:02X}")

    slots = s.rd_cart(0x7700, 63)
    print("slots:", slots.hex(" "))
    champ = slots[62]
    print(f"champion slot 62 ($773E) = {champ:02X}")
    if champ != 0x0F:
        raise SystemExit(f"champion {champ:02X}, expected 0F")
    print("STATE-ONLY SOAK GREEN")


if __name__ == "__main__":
    main()
