#!/usr/bin/env python3
"""First-round draw for a 32-team series.

    .venv/bin/python tools/draw32.py --team 20 --draw-seed 0x1FEB

A series draw is the pair (selected team, 14-bit draw seed). The selected
team always holds slot 0, so it plays match 1. Draw seed 0 is the legacy
order the stock bank-11 $8200 seeder builds: the selected team, then every
other team ascending. Every format-v1 password implies it.

A nonzero draw seed shuffles slots 1..31 with Fisher-Yates. The xorshift16
(7,9,8) state starts at draw_seed XOR $9E37, which is never zero because the
seed's top two bits are clear, and advances twice. Then slot i, from 31 down
to 2, takes the next state s and swaps with slot 1 + ((s * i) >> 16). One
state per slot keeps two seeds from realigning onto one stream, so the 16,383
nonzero seeds give 16,383 distinct draws for each selected team. That is a
finite family of draws chosen by menu timing, not a uniform sample of all 31!
orders.

A new series captures ((frame counter << 6) XOR menu frame) AND $3FFF from
the NMI frame counter $33, frozen while menus run, and the menu frame
counter $07F3, with 0 mapped to 1.
"""
import argparse

TEAMS = 32
SEED_BITS = 14
SEED_MAX = (1 << SEED_BITS) - 1
STATE_XOR = 0x9E37
WARMUP = 2


def _integer(name, value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")


def xorshift16(state):
    state ^= (state << 7) & 0xFFFF
    state ^= state >> 9
    return state ^ ((state << 8) & 0xFFFF)


def draw_order(team, draw_seed):
    """The 32 first-round slots for the selected team and draw seed."""
    _integer("team", team, TEAMS - 1)
    _integer("draw_seed", draw_seed, SEED_MAX)
    order = [team] + [other for other in range(TEAMS) if other != team]
    if draw_seed == 0:
        return order
    state = draw_seed ^ STATE_XOR
    for _ in range(WARMUP):
        state = xorshift16(state)
    for slot in range(TEAMS - 1, 1, -1):
        state = xorshift16(state)
        other = 1 + ((state * slot) >> 16)
        order[slot], order[other] = order[other], order[slot]
    return order


def capture(frame_counter, menu_frame):
    """The draw seed a new series takes from the two timing bytes."""
    _integer("frame_counter", frame_counter, 0xFF)
    _integer("menu_frame", menu_frame, 0xFF)
    return ((frame_counter << 6) ^ menu_frame) & SEED_MAX or 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    integer = lambda value: int(value, 0)
    parser.add_argument("--team", type=integer, required=True, help="selected team id, 0..31; it keeps slot 0")
    parser.add_argument("--draw-seed", type=integer, required=True, help="0 = legacy ascending draw, else 1..16383")
    args = parser.parse_args()
    try:
        order = draw_order(args.team, args.draw_seed)
    except ValueError as error:
        parser.error(str(error))
    print("order:", " ".join(f"{team:02X}" for team in order))
    print("round 1:", " ".join(f"{order[2 * m]:02X}-{order[2 * m + 1]:02X}" for m in range(TEAMS // 2)))


if __name__ == "__main__":
    main()
