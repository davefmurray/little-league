#!/usr/bin/env python3
"""Compare two builds frame-for-frame in a running romdev server.

    python3 tools/verify_regression.py stock.nes build/32bracket.nes
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:7331"


def call(tool, session, payload):
    req = urllib.request.Request(
        f"{BASE}/tool/{tool}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-romdev-session": session},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def run(rom, session, frames=180):
    call("loadMedia", session, {"platform": "nes", "path": rom})
    call("frame", session, {"op": "step", "frames": frames})
    shot = f"/tmp/reg-{session}.png"
    call("frame", session, {"op": "screenshot", "path": shot})
    ram = call("memory", session,
               {"op": "read", "region": "system_ram", "offset": 0, "length": 2048})
    return open(shot, "rb").read(), bytes.fromhex(ram["hex"])


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_regression.py A.nes B.nes")
    a_img, a_ram = run(sys.argv[1], "reg-a")
    b_img, b_ram = run(sys.argv[2], "reg-b")
    diffs = [i for i in range(len(a_ram)) if a_ram[i] != b_ram[i]]
    print(f"screenshots {'MATCH' if a_img == b_img else 'DIFFER'}")
    print(f"system_ram differs in {len(diffs)} bytes")
    print("first diffs:", [f"${i:04X}" for i in diffs[:20]])
    if a_img != b_img or diffs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
