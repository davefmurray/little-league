#!/usr/bin/env python3
"""Build a 16-team x 20-player test ROM in place.

Team blocks are laid out in the two free runs of PRG bank 4 so that no existing
table (lineups, flags, names, tile map) has to move:

    teams 0-11  -> $985A + team * $170
    teams 12-15 -> $B6F7 + (team-12) * $170

The roster pointer table at $8400 is rewritten, and the pitcher-trailer lookup
at $B094 is replaced with a JMP to a relocated copy that adds $150 instead of
$100. Five placeholder bench players are appended to each team.

    python3 tools/build_16x20.py ROM data/roster.json -o build/16x20.nes
"""
import argparse
import json
import sys

from llbcs_map import TEAM_BASES

HEADER = 16
BANK = 0x4000
TEAMS = 16
PLAYERS = 20
RECORD = 16
STRIDE = PLAYERS * RECORD + 48  # 0x170
NAME_LEN = 6

POINTER_TABLE = 0x8400  # bank 4
RUNS = [(0x985A, 12), (0xB6F7, 4)]
TRAILER_STUB = 0x8420  # free once rosters move
OLD_TRAILER_ROUTINE = 0xB094


def bank_offset(bank, cpu):
    base = 0xC000 if bank == 7 else 0x8000
    return HEADER + bank * BANK + (cpu - base)


def build(base_path, json_path, out_path):
    rom = bytearray(open(base_path, "rb").read())
    if rom[:4] != b"NES\x1a" or (rom[7] & 0xF0) | (rom[6] >> 4) != 1:
        raise SystemExit("expected an MMC1 iNES ROM")
    if rom[4] < 8:
        raise SystemExit("expected at least 8 PRG banks")
    if rom[6] & 0x04:
        raise SystemExit("trainer ROMs are not supported")

    doc = json.load(open(json_path))
    if len(doc["teams"]) != TEAMS:
        raise SystemExit(f"roster JSON has {len(doc['teams'])} teams, expected {TEAMS}")

    # Verify the destination runs are still $FF (i.e. genuinely free).
    for start, count in RUNS:
        off = bank_offset(4, start)
        span = count * STRIDE
        if any(b != 0xFF for b in rom[off:off + span]):
            raise SystemExit(f"run at ${start:04X} is not free; base ROM differs")

    for team_index, team in enumerate(doc["teams"]):
        # Locate this team's slot in the runs.
        remaining = team_index
        base = None
        for start, count in RUNS:
            if remaining < count:
                base = start + remaining * STRIDE
                break
            remaining -= count
        if base is None:
            raise SystemExit(f"team {team_index} has no slot")

        players = list(team["players"])
        if len(players) > PLAYERS:
            raise SystemExit(f"{team['name']}: {len(players)} players, max {PLAYERS}")
        while len(players) < PLAYERS:
            idx = len(players)
            template = dict(players[-1])
            template["name"] = f"NEW{idx - 14:02d}"
            template["attrs"] = list(template["attrs"])
            template["attrs"][5] = 1  # skill 2 placeholder
            players.append(template)

        off = bank_offset(4, base)
        for p, player in enumerate(players):
            name = player["name"][:NAME_LEN].ljust(NAME_LEN).encode("ascii")
            attrs = bytes(player["attrs"])
            if len(attrs) != 10:
                raise SystemExit(f"{team['name']} player {p}: need 10 attrs")
            chunk = name + attrs
            rom[off + p * RECORD:off + p * RECORD + RECORD] = chunk

        # Trailer: FF row, 8 zero bytes, then the three original pitcher records.
        old_base = TEAM_BASES[team_index]
        old_trailer = bank_offset(4, old_base + 0xF0)
        pitcher_bytes = bytes(rom[old_trailer + 0x18:old_trailer + 0x30])
        trailer = b"\xff" * 16 + b"\x00" * 8 + pitcher_bytes
        assert len(trailer) == 48
        rom[off + PLAYERS * RECORD:off + PLAYERS * RECORD + 48] = trailer

        # Pointer table entry.
        ptr = bank_offset(4, POINTER_TABLE + team_index * 2)
        rom[ptr:ptr + 2] = base.to_bytes(2, "little")

    # Relocated trailer lookup: base + $150 + pitcher_slot.
    new_routine = bytes([
        0xAE, 0xEE, 0x04,        # LDX $04EE
        0xBD, 0xFD, 0x04,        # LDA $04FD,X
        0x0A, 0x0A, 0x0A, 0x0A,  # ASL A x4
        0x20, 0x7C, 0xB0,        # JSR $B07C
        0x18,                    # CLC
        0xA0, 0x0C,              # LDY #$0C
        0xB1, 0x04,              # LDA ($04),Y
        0x7D, 0x00, 0x84,        # ADC $8400,X
        0x69, 0x50,              # ADC #$50
        0x85, 0x04,              # STA $04
        0xBD, 0x01, 0x84,        # LDA $8401,X
        0x69, 0x01,              # ADC #$01
        0x85, 0x05,              # STA $05
        0x60,                    # RTS
    ])
    stub = bank_offset(4, TRAILER_STUB)
    rom[stub:stub + len(new_routine)] = new_routine
    off = bank_offset(4, OLD_TRAILER_ROUTINE)
    rom[off:off + 3] = bytes([0x4C, TRAILER_STUB & 0xFF, TRAILER_STUB >> 8])

    open(out_path, "wb").write(rom)
    print(f"wrote {out_path}")
    print(f"  {TEAMS} teams x {PLAYERS} players, stride 0x{STRIDE:X}")
    for start, count in RUNS:
        print(f"  run ${start:04X}: {count} teams, ends ${start + count * STRIDE:04X}")
    print(f"  pointer table ${POINTER_TABLE:04X}, trailer stub ${TRAILER_STUB:04X}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("roster")
    ap.add_argument("-o", "--out", default="build/16x20.nes")
    args = ap.parse_args()
    build(args.rom, args.roster, args.out)


if __name__ == "__main__":
    main()
