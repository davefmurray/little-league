#!/usr/bin/env python3
"""Build the 32-team gameplay candidate.

    .venv/bin/python tools/build_32team_full.py

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
CPU_OUT = os.path.join(ROOT, "build/cpu32.nes")
TABLES_OUT = os.path.join(ROOT, "build/teamtables32.nes")
ROLES_OUT = os.path.join(ROOT, "build/roles32.nes")
RESULTS_OUT = os.path.join(ROOT, "build/results32.nes")
CONTROL_OUT = os.path.join(ROOT, "build/control32.nes")


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
    run("build_cpu32.py", GAMEPLAY_OUT, "-o", CPU_OUT)
    run("build_teamtables32.py", CPU_OUT, "-o", TABLES_OUT)
    run("build_roles32.py", TABLES_OUT, "-o", ROLES_OUT)
    run("build_results32.py", ROLES_OUT, "-o", RESULTS_OUT)
    run("build_control32.py", RESULTS_OUT, "-o", CONTROL_OUT)
    print(f"wrote {CONTROL_OUT}; baseline preserved at {OUT}")


if __name__ == "__main__":
    main()
