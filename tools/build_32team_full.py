#!/usr/bin/env python3
"""Build the 32-team gameplay candidate.

    .venv/bin/python tools/build_32team_full.py

Chain (all scripts are also runnable individually):

    build/direct20-names.nes
      -> build_ratings32.py     (bank3 $BC80, 32 x 4)
      -> build_lineups32.py     (fixed $FD80, 32 x 9)
      -> build_round_labels.py  (bank11 $8440/$84A0/$8500)
      -> build_top_row.py       (header/title rows)
      -> build_roster_cache.py  (bank8 cache, real ids, $7F00 repoint)
      -> build/direct31.nes
      -> build_gameplay32.py    (lineup indexing, row guard, launch stack)
      -> build/gameplay32.nes

`direct20-names.nes` is direct20 + the 16-31 rosters + names32:

    python3 tools/build_extra_rosters.py build/direct20.nes \
        data/roster32.json -o build/direct20-extra.nes
    python3 tools/build_names32.py build/direct20-extra.nes \
        -o build/direct20-names.nes
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "build/direct20-names.nes")
OUT = os.path.join(ROOT, "build/direct31.nes")
GAMEPLAY_OUT = os.path.join(ROOT, "build/gameplay32.nes")


def run(script, *args):
    cmd = [sys.executable, os.path.join(ROOT, "tools", script), *args]
    print("+", " ".join(os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd))
    subprocess.run(cmd, check=True)


def main():
    if not os.path.exists(BASE):
        raise SystemExit(
            f"missing {BASE}; build it with:\n"
            "  python3 tools/build_extra_rosters.py build/direct20.nes data/roster32.json "
            "-o build/direct20-extra.nes\n"
            "  python3 tools/build_names32.py build/direct20-extra.nes -o build/direct20-names.nes")
    tmp = os.path.join(ROOT, "build", "_32full")
    os.makedirs(tmp, exist_ok=True)
    s1, s2, s3, s4, s5, s6, s7 = (os.path.join(tmp, f"step{i}.nes") for i in range(1, 8))
    run("build_ratings32.py", BASE, "-o", s1)
    run("build_lineups32.py", s1, "-o", s2)
    run("build_round_labels.py", s2, "-o", s3)
    run("build_top_row.py", s3, "-o", s4)
    run("build_bracket_codes32.py", s4, "-o", s5)
    run("build_bracket_clear.py", s5, "-o", s6)
    run("build_bracket_layout.py", s6, "-o", s7)
    run("build_roster_cache.py", s7, "-o", OUT)
    run("build_gameplay32.py", OUT, "-o", GAMEPLAY_OUT)
    print(f"wrote {GAMEPLAY_OUT}; baseline preserved at {OUT}")


if __name__ == "__main__":
    main()
