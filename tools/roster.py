#!/usr/bin/env python3
"""Roster/team data extractor and patcher for Little League Baseball: Championship Series.

Data locations (CPU addresses in the bank where the game maps them):

  team long names    bank 1  $9180   16 teams x 16 bytes, ASCII, space padded
  team short names   bank 1  $9290   pointer table -> [attr][text][FF]
  team ratings       bank 3  $B224   16 teams x 4 bytes (1-4), power analysis bars
  player records     bank 4  $8420   16 teams x 15 players x 16 bytes
                                     [0:6] name ASCII, [6:16] attributes

Usage:
  python3 tools/roster.py show    ROM
  python3 tools/roster.py extract ROM -o data/roster.json
  python3 tools/roster.py apply   ROM data/roster.json -o build/hack.nes

Requires no third-party modules.
"""
import argparse
import json
import sys

from llbcs_map import (TEAM_BASES, COLOR_PRIMARY, COLOR_SECONDARY,
                       LINEUPS, TRAILER, PITCHERS_AT)

HEADER = 16
BANK = 16384
TEAMS = 16
PLAYERS = 15
RECORD = 16
NAME_LEN = 6

ROM_BASE = {
    1: 0x8000,
    3: 0x8000,
    4: 0x8000,
    7: 0xC000,
}

ADDR = {
    "team_names": (1, 0x9180, 16),
    "short_ptrs": (1, 0x9290, 2),
    "ratings": (3, 0xB224, 4),
    "roster": (4, 0x8420, RECORD),
}

RATING_LABELS = ["BATTING", "RUNNING", "PITCHING", "DEFENSE"]


def off(bank, cpu):
    """File offset for a CPU address inside a switchable PRG bank."""
    base = ROM_BASE[bank]
    if not (base <= cpu < base + BANK):
        raise ValueError(f"${cpu:04X} is outside bank {bank}")
    return HEADER + bank * BANK + (cpu - base)


class Rom:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = bytearray(f.read())
        if self.data[:4] != b"NES\x1a":
            raise SystemExit(f"{path}: not an iNES file")
        if self.data[4] < 8:
            raise SystemExit(f"{path}: expected >= 8 PRG banks")

    def get(self, bank, cpu, n):
        o = off(bank, cpu)
        return bytes(self.data[o:o + n])

    def put(self, bank, cpu, blob):
        o = off(bank, cpu)
        self.data[o:o + len(blob)] = blob

    # --- team names -----------------------------------------------------
    def team_names(self):
        names = []
        for t in range(TEAMS):
            raw = self.get(1, 0x9180 + t * 16, 14)
            names.append(raw.decode("ascii", "replace").rstrip())
        return names

    def set_team_name(self, t, name):
        if len(name) > 14:
            raise ValueError(f"team name {name!r} > 14 chars")
        if not all(32 <= ord(c) < 127 for c in name):
            raise ValueError(f"team name {name!r} must be printable ASCII")
        self.put(1, 0x9180 + t * 16, name.ljust(14).encode("ascii") + b"\xff\xff")

    # --- short names ----------------------------------------------------
    # Teams 0-7 live in a sequential table at $92A0; teams 8-15 are reached
    # through an 8-entry pointer table at $9290.  Each entry is
    # [attr byte][text][0xFF], text space padded.
    def _short_entry(self, addr):
        attr = self.get(1, addr, 1)[0]
        addr += 1
        raw = bytearray()
        while True:
            b = self.get(1, addr, 1)[0]
            if b == 0xFF:
                break
            raw.append(b)
            addr += 1
            if len(raw) > 24:
                raise SystemExit(f"unterminated short name at ${addr:04X}")
        return {"attr": attr, "name": raw.decode("ascii", "replace"),
                "width": len(raw), "text_addr": addr - len(raw)}

    def short_names(self):
        out = []
        for t in range(TEAMS):
            table = 0x9280 if t < 8 else 0x9290
            idx = t if t < 8 else t - 8
            ptr = int.from_bytes(self.get(1, table + idx * 2, 2), "little")
            out.append(self._short_entry(ptr))
        return out

    def set_short_name(self, t, name):
        cur = self.short_names()[t]
        width = cur["width"]
        if len(name) > width:
            raise ValueError(
                f"short name {name!r} does not fit ({len(name)} > {width} bytes); "
                f"current is {cur['name']!r}")
        if not all(32 <= ord(c) < 127 for c in name):
            raise ValueError(f"short name {name!r} must be printable ASCII")
        self.put(1, cur["text_addr"], name.ljust(width).encode("ascii"))

    # --- team ratings ---------------------------------------------------
    def ratings(self):
        return [list(self.get(3, 0xB224 + t * 4, 4)) for t in range(TEAMS)]

    def set_ratings(self, t, values):
        if len(values) != 4:
            raise ValueError("ratings need exactly 4 values")
        if not all(isinstance(v, int) and 1 <= v <= 4 for v in values):
            raise ValueError(f"ratings must be 1..4, got {values}")
        self.put(3, 0xB224 + t * 4, bytes(values))

    # --- colours / lineup -----------------------------------------------
    def colors(self, t):
        return {
            "primary": self.get(7, COLOR_PRIMARY + t, 1)[0],
            "secondary": self.get(7, COLOR_SECONDARY + t, 1)[0],
        }

    def set_colors(self, t, primary, secondary):
        self.put(7, COLOR_PRIMARY + t, bytes([primary]))
        self.put(7, COLOR_SECONDARY + t, bytes([secondary]))

    def lineup(self, t):
        raw = self.get(4, LINEUPS + t * 9, 9)
        return [{"order": b >> 4, "position": b & 0x0F} for b in raw]

    def set_lineup(self, t, entries):
        if len(entries) != 9:
            raise ValueError("lineup needs 9 entries")
        out = bytearray()
        for e in entries:
            order = e["order"] if isinstance(e, dict) else e[0]
            pos = e["position"] if isinstance(e, dict) else e[1]
            if not (0 <= order <= 8 and 1 <= pos <= 9):
                raise ValueError(f"bad lineup entry {order},{pos}")
            out.append((order << 4) | pos)
        self.put(4, LINEUPS + t * 9, bytes(out))

    # --- pitchers -------------------------------------------------------
    def pitchers(self, t):
        base = TEAM_BASES[t] + TRAILER + PITCHERS_AT
        raw = self.get(4, base, 24)
        return [list(raw[i * 8:(i + 1) * 8]) for i in range(3)]

    def set_pitchers(self, t, records):
        if len(records) != 3 or any(len(r) != 8 for r in records):
            raise ValueError("need 3 pitcher records of 8 bytes")
        base = TEAM_BASES[t] + TRAILER + PITCHERS_AT
        self.put(4, base, bytes(b for r in records for b in r))

    # --- players --------------------------------------------------------
    def players(self, t):
        out = []
        base = TEAM_BASES[t]
        for p in range(PLAYERS):
            rec = self.get(4, base + p * RECORD, RECORD)
            name = rec[:NAME_LEN].decode("ascii", "replace")
            out.append({"name": name.rstrip(), "padded": name,
                        "attrs": list(rec[NAME_LEN:])})
        return out

    def set_player(self, t, p, name, attrs):
        if len(name) > NAME_LEN:
            raise ValueError(f"player name {name!r} > {NAME_LEN} chars")
        if not all(32 <= ord(c) < 127 for c in name):
            raise ValueError(f"player name {name!r} must be printable ASCII")
        if len(attrs) != RECORD - NAME_LEN:
            raise ValueError(f"attrs must be {RECORD - NAME_LEN} bytes")
        if not all(isinstance(a, int) and 0 <= a <= 255 for a in attrs):
            raise ValueError("attrs must be bytes 0..255")
        base = TEAM_BASES[t] + p * RECORD
        self.put(4, base, name.ljust(NAME_LEN).encode("ascii") + bytes(attrs))


def extract(rom):
    shorts = rom.short_names()
    return {
        "rom": rom.path,
        "teams": [
            {
                "id": t,
                "name": rom.team_names()[t],
                "short_name": shorts[t]["name"].rstrip(),
                "short_width": shorts[t]["width"],
                "short_attr": shorts[t]["attr"],
                "ratings": rom.ratings()[t],
                "colors": rom.colors(t),
                "lineup": rom.lineup(t),
                "pitchers": rom.pitchers(t),
                "players": rom.players(t),
            }
            for t in range(TEAMS)
        ],
    }


def apply(rom, doc):
    teams = doc["teams"]
    if len(teams) != TEAMS:
        raise SystemExit(f"expected {TEAMS} teams, found {len(teams)}")
    for t, team in enumerate(teams):
        if team.get("name") is not None:
            rom.set_team_name(t, team["name"])
        if team.get("short_name"):
            rom.set_short_name(t, team["short_name"])
        if team.get("ratings") is not None:
            rom.set_ratings(t, team["ratings"])
        if team.get("colors"):
            rom.set_colors(t, team["colors"]["primary"], team["colors"]["secondary"])
        if team.get("lineup"):
            rom.set_lineup(t, team["lineup"])
        if team.get("pitchers"):
            rom.set_pitchers(t, team["pitchers"])
        players = team.get("players", [])
        if len(players) != PLAYERS:
            raise SystemExit(f"team {t}: expected {PLAYERS} players, found {len(players)}")
        for p, player in enumerate(players):
            rom.set_player(t, p, player["name"], player["attrs"])


def show(rom):
    names = rom.team_names()
    ratings = rom.ratings()
    print(f"{'#':>2} {'TEAM':<16} {'BAT RUN PIT DEF':<15} roster")
    for t in range(TEAMS):
        ps = rom.players(t)
        line = " ".join(f"{p['name']:<6}" for p in ps)
        r = ratings[t]
        c = rom.colors(t)
        lu = "".join(f"{e['order']}{e['position']}" for e in rom.lineup(t))
        print(f"{t:2d} {names[t]:<16} {r[0]:3d} {r[1]:3d} {r[2]:3d} {r[3]:3d} "
              f"c {c['primary']:02X}/{c['secondary']:02X}  lu {lu}  {line}")


def patch(rom, team, slot, name, skill, attrs):
    players = rom.players(team)
    if not 0 <= slot < PLAYERS:
        raise SystemExit(f"slot must be 0..{PLAYERS - 1}")
    cur = players[slot]
    new_name = name if name is not None else cur["name"]
    new_attrs = list(cur["attrs"])
    if attrs is not None:
        raw = bytes.fromhex(attrs.replace(" ", ""))
        if len(raw) != RECORD - NAME_LEN:
            raise SystemExit(f"--attrs needs {RECORD - NAME_LEN} hex bytes")
        new_attrs = list(raw)
    if skill is not None:
        if not 1 <= skill <= 5:
            raise SystemExit("--skill must be 1..5")
        new_attrs[5] = skill - 1          # b11 = SKILL index, displayed +1
    rom.set_player(team, slot, new_name, new_attrs)
    print(f"team {team} slot {slot}: {cur['name']!r} -> {new_name!r}, "
          f"skill {new_attrs[5] + 1}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show")
    s.add_argument("rom")

    e = sub.add_parser("extract")
    e.add_argument("rom")
    e.add_argument("-o", "--out", default="roster.json")

    p2 = sub.add_parser("patch")
    p2.add_argument("rom")
    p2.add_argument("--team", type=int, required=True)
    p2.add_argument("--slot", type=int, required=True)
    p2.add_argument("--name")
    p2.add_argument("--skill", type=int, choices=range(1, 6))
    p2.add_argument("--attrs", help="10 raw attribute bytes as hex")
    p2.add_argument("-o", "--out", required=True)

    a = sub.add_parser("apply")
    a.add_argument("rom")
    a.add_argument("json")
    a.add_argument("-o", "--out", required=True)

    args = ap.parse_args()
    rom = Rom(args.rom)

    if args.cmd == "show":
        show(rom)
    elif args.cmd == "extract":
        doc = extract(rom)
        with open(args.out, "w") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        print(f"wrote {args.out}: {TEAMS} teams x {PLAYERS} players")
    elif args.cmd == "patch":
        patch(rom, args.team, args.slot, args.name, args.skill, args.attrs)
        with open(args.out, "wb") as f:
            f.write(rom.data)
        print(f"wrote {args.out}")
    else:
        with open(args.json) as f:
            doc = json.load(f)
        apply(rom, doc)
        with open(args.out, "wb") as f:
            f.write(rom.data)
        print(f"wrote {args.out} ({len(rom.data)} bytes)")


if __name__ == "__main__":
    main()
