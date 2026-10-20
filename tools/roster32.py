#!/usr/bin/env python3
"""Extract/apply the 32-team bank-8 roster layout.

    python3 tools/roster32.py extract build/32x20-extra.nes -o /tmp/r32.json
    python3 tools/roster32.py apply   build/32x20-extra.nes /tmp/r32.json -o /tmp/r32.nes

Layout (same as the web editor's bank8-32 mode):

  players   bank8 $8000 + team*$170, 20 x 16 bytes (6 name + 10 attrs)
  names     bank1 $9180 (0-15), bank9 $8080 (16-31), fallback bank1 $BCC0
  ratings   bank3 $B224 (0-15), bank3 $BC80 (16-31, when valid)
  lineups   fixed $FD80 (16-31, when valid) -- read-only in the JSON
"""
import argparse
import json
import os

HEADER = 16
BANK = 0x4000
BANK8 = HEADER + 8 * BANK
BANK9_NAMES = HEADER + 9 * BANK + 0x80
FIXED_LINEUPS = HEADER + 15 * BANK + (0xFD80 - 0xC000)
RATINGS32 = 0xBC80
NAMES32 = 0xBCC0
STRIDE = 0x170
PLAYERS = 20
RECORD = 16
NAME_LEN = 6


def off(bank, cpu):
    base = 0xC000 if bank == 15 else 0x8000
    return HEADER + bank * BANK + (cpu - base)


def printable(raw):
    return len(raw) > 0 and all(0x20 <= b < 0x7F for b in raw)


def is_32team(data):
    o = BANK8 + 16 * STRIDE
    return len(data) >= o + 6 and printable(data[o:o + 6])


def read_name(data, t):
    if t < 16:
        return data[off(1, 0x9180 + t * 16):off(1, 0x9180 + t * 16) + 14].decode(
            "ascii", "replace").rstrip()
    raw = data[BANK9_NAMES + t * 16:BANK9_NAMES + t * 16 + 14]
    if printable(raw):
        return raw.decode("ascii", "replace").rstrip()
    raw = data[off(1, NAMES32 + (t - 16) * 8):off(1, NAMES32 + (t - 16) * 8) + 7]
    if printable(raw):
        return raw.decode("ascii", "replace").rstrip()
    return f"TEAM {t + 1}"


def read_ratings(data, t):
    if t < 16:
        o = off(3, 0xB224 + t * 4)
        return list(data[o:o + 4])
    o = off(3, RATINGS32 + t * 4)
    r = list(data[o:o + 4])
    return r if all(1 <= v <= 4 for v in r) else [2, 2, 2, 2]


def read_lineup(data, t):
    o = FIXED_LINEUPS + t * 9
    raw = data[o:o + 9]
    if len(raw) == 9 and all(1 <= (b & 0x0F) <= 9 and (b >> 4) <= 8 for b in raw):
        return [{"order": b >> 4, "position": b & 0x0F} for b in raw]
    return []


def extract(path):
    data = open(path, "rb").read()
    if len(data) < HEADER + 16 * BANK or data[:4] != b"NES\x1a":
        raise SystemExit(f"{path}: not an iNES file")
    if not is_32team(data):
        raise SystemExit(f"{path}: no bank8 team-16 block (not a 32-team build)")
    teams = []
    for t in range(32):
        base = BANK8 + t * STRIDE
        players = []
        for p in range(PLAYERS):
            rec = data[base + p * RECORD:base + p * RECORD + RECORD]
            players.append({
                "name": rec[:NAME_LEN].decode("ascii", "replace").rstrip(),
                "attrs": list(rec[NAME_LEN:16]),
            })
        teams.append({
            "id": t,
            "name": read_name(data, t),
            "ratings": read_ratings(data, t),
            "lineup": read_lineup(data, t) if t >= 16 else [],
            "players": players,
        })
    return {"version": 1, "layout": "bank8-32", "teams": teams}


def apply_rom(path, doc, out_path):
    data = bytearray(open(path, "rb").read())
    if not is_32team(data):
        raise SystemExit(f"{path}: no bank8 team-16 block")
    teams = doc.get("teams", [])
    if len(teams) != 32:
        raise SystemExit(f"expected 32 teams, got {len(teams)}")
    fresh = open(path, "rb").read()
    have_bank9 = printable(fresh[BANK9_NAMES:BANK9_NAMES + 6])
    have_ratings32 = all(1 <= b <= 4 for b in fresh[off(3, RATINGS32):off(3, RATINGS32) + 128])

    for t, team in enumerate(teams):
        if t < 16:
            o = off(1, 0x9180 + t * 16)
            name = team["name"][:14].ljust(14).encode("ascii") + b"\xff\xff"
            data[o:o + 16] = name
        elif have_bank9:
            o = BANK9_NAMES + t * 16
            data[o:o + 16] = team["name"][:14].ljust(14).encode("ascii") + b"\xff\xff"
        else:
            o = off(1, NAMES32 + (t - 16) * 8)
            # Only overwrite an existing names32 entry; an all-FF table is
            # left untouched so the extract/apply round-trip is byte-exact.
            if printable(fresh[o:o + 7]):
                data[o:o + 8] = team["name"][:7].ljust(7).encode("ascii") + b"\xff"

        if t < 16 or have_ratings32:
            o = off(3, (0xB224 if t < 16 else RATINGS32) + t * 4)
            data[o:o + 4] = bytes(team["ratings"])

        base = BANK8 + t * STRIDE
        players = team["players"]
        if len(players) != PLAYERS:
            raise SystemExit(f"team {t}: expected {PLAYERS} players, got {len(players)}")
        for p, player in enumerate(players):
            rec = base + p * RECORD
            data[rec:rec + NAME_LEN] = player["name"][:6].ljust(6).encode("ascii")
            attrs = player["attrs"]
            if len(attrs) != 10 or not all(isinstance(v, int) and 0 <= v <= 255 for v in attrs):
                raise SystemExit(f"team {t} player {p}: attrs must be 10 bytes")
            data[rec + NAME_LEN:rec + 16] = bytes(attrs)

    open(out_path, "wb").write(data)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("rom")
    e.add_argument("-o", "--out", default="roster32.json")
    a = sub.add_parser("apply")
    a.add_argument("rom")
    a.add_argument("json")
    a.add_argument("-o", "--out", default="build/roster32-applied.nes")
    args = ap.parse_args()

    if args.cmd == "extract":
        doc = extract(args.rom)
        with open(args.out, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
        print(f"wrote {args.out}: 32 teams x 20 players")
    else:
        apply_rom(args.rom, json.load(open(args.json)), args.out)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
