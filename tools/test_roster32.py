#!/usr/bin/env python3
"""Self-contained round-trip test for tools/roster32.py (no base ROM needed)."""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roster32 import (BANK8, BANK9_NAMES, BANK, STRIDE, PLAYERS, RECORD,
                      NAME_LEN, RATINGS32, NAMES32, apply_rom, extract)
from roster32 import off
from roster import Rom, show32
from rominfo import header as rom_header, team_layout


def build_fixture(path):
    data = bytearray(16 + 16 * BANK)
    data[:4] = b"NES\x1a"
    data[4] = 16
    data[5] = 0
    # Low-team names/ratings.
    for t in range(16):
        o = 16 + 1 * BANK + (0x9180 + t * 16 - 0x8000)
        data[o:o + 16] = f"TEAM {t}".ljust(14).encode("ascii") + b"\xff\xff"
        o = 16 + 3 * BANK + (0xB224 + t * 4 - 0x8000)
        data[o:o + 4] = bytes([1, 1, 1, 1])
    # High-team names/ratings.
    for t in range(16, 32):
        o = 16 + 1 * BANK + (NAMES32 + (t - 16) * 8 - 0x8000)
        data[o:o + 8] = f"TEAM {t}".ljust(7).encode("ascii") + b"\xff"
        o = 16 + 3 * BANK + (RATINGS32 + t * 4 - 0x8000)
        data[o:o + 4] = bytes([2, 2, 2, 2])
    # All 32 bank8 roster blocks + trailers.
    for t in range(32):
        base = BANK8 + t * STRIDE
        for p in range(PLAYERS):
            rec = base + p * RECORD
            data[rec:rec + NAME_LEN] = f"P{t:02d}{p:02d}".ljust(6).encode("ascii")
            slot = {0: 8, 1: 16, 2: 24}.get(p, 0)
            data[rec + NAME_LEN:rec + 16] = bytes([p % 5] * 6 + [slot] + [0] * 3)
        data[base + PLAYERS * RECORD:base + PLAYERS * RECORD + 16] = b"\xff" * 16
        data[base + PLAYERS * RECORD + 16:base + PLAYERS * RECORD + 24] = b"\x00" * 8
    open(path, "wb").write(data)
    return data


def main():
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "fixture.nes")
        original = build_fixture(src)
        doc = extract(src)
        assert doc["layout"] == "bank8-32"
        assert len(doc["teams"]) == 32
        assert all(len(t["players"]) == 20 for t in doc["teams"])

        out = os.path.join(td, "out.nes")
        apply_rom(src, doc, out)
        assert open(out, "rb").read() == original, "round-trip is not byte-identical"

        doc["teams"][16]["players"][0]["name"] = "TESTER"
        doc["teams"][16]["players"][0]["attrs"][3] = 7   # byte 9  -> power
        doc["teams"][16]["players"][0]["attrs"][4] = 6   # byte 10 -> speed
        doc["teams"][16]["players"][0]["attrs"][5] = 4   # byte 11 -> skill index (shown +1)
        apply_rom(src, doc, out)
        back = extract(out)
        p0 = back["teams"][16]["players"][0]
        assert p0["name"] == "TESTER"
        assert (p0["attrs"][3], p0["attrs"][4], p0["attrs"][5]) == (7, 6, 4)
        assert p0["attrs"][5] + 1 == 5

        # Every team has 20 players and exactly the three pitcher slots.
        for team in back["teams"]:
            assert len(team["players"]) == 20
            slots = [pl["attrs"][6] for pl in team["players"]
                     if pl["attrs"][6] in (8, 16, 24)]
            assert sorted(slots) == [8, 16, 24], (team["id"], slots)

        # roster.py show32 must also recognize the fixture.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show32(Rom(src))
        lines = buf.getvalue().splitlines()
        assert len(lines) == 33, f"expected header + 32 teams, got {len(lines)}"
        assert "TEAM 16" in buf.getvalue()
        assert "P1600" in buf.getvalue()

        # rominfo.py must detect the same layout.
        raw = open(src, "rb").read()
        assert "32-team bank8" in team_layout(raw, rom_header(raw))
        print("test_roster32: fixture round-trip + edit + attribute/bench + "
              "show32 + rominfo OK")


if __name__ == "__main__":
    main()
