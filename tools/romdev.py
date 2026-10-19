#!/usr/bin/env python3
"""Tiny stdlib-only romdev REST client, so probes are one short command.

romdev runs at http://127.0.0.1:7331 (start it with
`npm_config_cache="$PWD/.npm-cache" npx -y romdevtools &`).

Usage:
  python3 tools/romdev.py load build/bracket-input.nes
  python3 tools/romdev.py step 120
  python3 tools/romdev.py press start 4
  python3 tools/romdev.py press a 4
  python3 tools/romdev.py shot /tmp/shot.png
  python3 tools/romdev.py ram 0x047b 16          # system_ram
  python3 tools/romdev.py read 0x6000 64          # nes_cart_ram
  python3 tools/romdev.py bp 0x8162               # stop on PC
  python3 tools/romdev.py trace 60 0x8100         # executed instructions
  python3 tools/romdev.py call 0x8200 '{"maxInstructions":1000}'
  python3 tools/romdev.py save before-a
  python3 tools/romdev.py loadstate before-a
  python3 tools/romdev.py tool breakpoint '{"on":"read","address":16406,"maxFrames":120}'

Every command takes an optional trailing --session NAME (default llbcs).
The generic `tool` command is the escape hatch for anything not wrapped.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ROMDEV_URL", "http://127.0.0.1:7331")
SESSION = "llbcs"


def call(name, payload, timeout=120):
    req = urllib.request.Request(
        f"{BASE}/tool/{name}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json",
                 "x-romdev-session": SESSION},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"{name} HTTP {e.code}: {body}")


def num(s):
    return int(s, 0)


def out(obj, limit=None):
    text = json.dumps(obj, indent=1)
    if limit and len(text) > limit:
        text = text[:limit] + "\n... (truncated)"
    print(text)


def main(argv):
    global SESSION
    if not argv:
        raise SystemExit(__doc__)
    if "--session" in argv:
        i = argv.index("--session")
        SESSION = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    cmd, rest = argv[0], argv[1:]

    if cmd == "tool":
        payload = json.loads(rest[1]) if len(rest) > 1 else {}
        out(call(rest[0], payload))
    elif cmd == "load":
        out(call("loadMedia", {"platform": "nes", "path": os.path.abspath(rest[0])}))
    elif cmd == "step":
        out(call("frame", {"op": "step", "count": num(rest[0]) if rest else 1}))
    elif cmd == "press":
        out(call("input", {"op": "press", "button": rest[0],
                           "frames": num(rest[1]) if len(rest) > 1 else 4}))
    elif cmd == "shot":
        out(call("frame", {"op": "screenshot", "path": rest[0]}))
    elif cmd == "ram":
        out(call("memory", {"op": "read", "region": "system_ram",
                            "offset": num(rest[0]),
                            "length": num(rest[1]) if len(rest) > 1 else 1}))
    elif cmd == "read":
        out(call("memory", {"op": "read", "region": "nes_cart_ram",
                            "offset": num(rest[0]),
                            "length": num(rest[1]) if len(rest) > 1 else 1}))
    elif cmd == "write":
        out(call("memory", {"op": "write", "region": "system_ram",
                            "offset": num(rest[0]), "bytes": rest[1]}))
    elif cmd == "bp":
        payload = {"on": "pc", "address": num(rest[0]),
                   "maxFrames": num(rest[1]) if len(rest) > 1 else 600}
        out(call("breakpoint", payload))
    elif cmd == "trace":
        payload = {"op": "traceInstructions", "count": num(rest[0]),
                   "maxEntries": num(rest[2]) if len(rest) > 2 else 400}
        if len(rest) > 1:
            payload["fromPc"] = num(rest[1])
        out(call("frame", payload))
    elif cmd == "call":
        payload = {"op": "call", "pc": num(rest[0])}
        if len(rest) > 1:
            payload.update(json.loads(rest[1]))
        out(call("cpu", payload))
    elif cmd == "save":
        out(call("state", {"op": "save", "name": rest[0]}))
    elif cmd == "loadstate":
        out(call("state", {"op": "load", "name": rest[0]}))
    elif cmd == "regs":
        out(call("memory", {"op": "read", "region": "nes_cpu_regs"}))
    elif cmd == "pc":
        d = call("cpu", {"op": "read"})
        bank = call("memory", {"op": "read", "region": "system_ram",
                               "offset": 0x27, "length": 1}).get("hex")
        print(f"PC=${d['pc']:04X} S=${d['registers']['S']:02X} "
              f"A=${d['registers']['A']:02X} X=${d['registers']['X']:02X} "
              f"Y=${d['registers']['Y']:02X} $27=${bank} "
              f"jammed={d['flags']['jammed']}")
    elif cmd == "health":
        with urllib.request.urlopen(f"{BASE}/healthz", timeout=5) as r:
            print(r.read().decode())
    else:
        raise SystemExit(f"unknown command {cmd}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
