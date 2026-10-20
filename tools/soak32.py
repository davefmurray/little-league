#!/usr/bin/env python3
"""Run a short 32-team soak and write a JSON report.

    python3 tools/soak32.py --rom build/direct31.nes --matches 4 \
        --mode watch -o build/soak32.json

Wraps tools/soak_bracket.py (which drives the bracket, password, matchup,
and field) and records the exit code, wall time, and output tail. With
--password (default), also runs tools/password32.py test and records it.
"""
import argparse
import json
import os
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="build/direct31.nes")
    ap.add_argument("--matches", type=int, default=4)
    ap.add_argument("--mode", choices=("speed", "watch"), default="speed")
    ap.add_argument("--winner", choices=("forced", "score"), default="score")
    ap.add_argument("--state", default="")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--password", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("-o", "--out", default="build/soak32.json")
    args = ap.parse_args()

    cmd = [sys.executable, "tools/soak_bracket.py", "--rom", args.rom,
           "--matches", str(args.matches), "--mode", args.mode,
           "--winner", args.winner]
    if args.state:
        cmd += ["--state", args.state]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=args.timeout)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = f"timeout after {args.timeout}s"
    secs = round(time.time() - t0, 1)

    password = None
    if args.password:
        p = subprocess.run([sys.executable, "tools/password32.py", "test"],
                           capture_output=True, text=True)
        password = {"returncode": p.returncode,
                    "output": (p.stdout + p.stderr).strip()}

    report = {
        "rom": args.rom,
        "matches": args.matches,
        "mode": args.mode,
        "winner": args.winner,
        "seconds": secs,
        "returncode": rc,
        "stdout_tail": out[-1500:],
        "stderr_tail": err[-1500:],
        "password": password,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    open(args.out, "w").write(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in
                      ("rom", "matches", "mode", "winner", "seconds",
                       "returncode")}))
    if rc != 0:
        print(out[-800:])
        print(err[-800:])
        sys.exit(rc)


if __name__ == "__main__":
    main()
