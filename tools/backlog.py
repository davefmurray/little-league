#!/usr/bin/env python3
"""Backlog queue for the 32-team ROM loop.

Single source of truth: docs/backlog.json
Contract: docs/AUTOLOOP.md

Usage:
  python3 tools/backlog.py list
  python3 tools/backlog.py pick            # prints the next READY task JSON
  python3 tools/backlog.py start <id>     # active + attempts++
  python3 tools/backlog.py done <id> --evidence "..." --commit <sha> [--next "..."]
  python3 tools/backlog.py block <id> --reason "..."
  python3 tools/backlog.py add --id ... --title ... --priority P0 --next ... --verify ...
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "docs" / "backlog.json"
PRI = {"P0": 0, "P1": 1, "P2": 2}
OPEN = ("queued", "active")


def load():
    return json.loads(PATH.read_text())


def save(data):
    PATH.write_text(json.dumps(data, indent=2) + "\n")


def find(data, tid):
    for t in data["tasks"]:
        if t["id"] == tid:
            return t
    raise SystemExit(f"unknown task {tid}")


def done(data, tid):
    try:
        return find(data, tid)["status"] == "done"
    except SystemExit:
        return False


def ready(data, t):
    return t["status"] in OPEN and all(done(data, d) for d in t.get("depends_on", []))


def cmd_list(_):
    data = load()
    for t in sorted(data["tasks"], key=lambda x: (PRI.get(x["priority"], 9), x["id"])):
        mark = "*" if t["status"] == "active" else " "
        print(f'{mark}{t["status"]:8} {t["priority"]} {t["id"]:22} {t["title"]}')
    n = sum(1 for t in data["tasks"] if t["status"] == "done")
    print(f'\n{n}/{len(data["tasks"])} done')


def cmd_pick(_):
    data = load()
    cands = [t for t in data["tasks"] if ready(data, t)]
    if not cands:
        print("NO READY TASKS")
        return 2
    t = sorted(cands, key=lambda x: (PRI.get(x["priority"], 9),
                                     x["status"] != "active",
                                     x.get("attempts", 0), x["id"]))[0]
    print(json.dumps(t, indent=2))
    if t.get("attempts", 0) >= 3:
        print("\nWARNING: 3+ attempts on this task. New hypothesis or block it.", file=sys.stderr)
    return 0


def cmd_start(a):
    data = load()
    t = find(data, a.id)
    t["status"] = "active"
    t["attempts"] = t.get("attempts", 0) + 1
    save(data)
    print(json.dumps(t, indent=2))


def cmd_done(a):
    data = load()
    t = find(data, a.id)
    t["status"] = "done"
    t["evidence"] = a.evidence
    t["last_commit"] = a.commit
    if a.next:
        t["next"] = a.next
    save(data)
    print(f"done {a.id}")


def cmd_block(a):
    data = load()
    t = find(data, a.id)
    t["status"] = "blocked"
    t["blocked_reason"] = a.reason
    save(data)
    print(f"blocked {a.id}: {a.reason}")


def cmd_add(a):
    data = load()
    if any(t["id"] == a.id for t in data["tasks"]):
        raise SystemExit(f"duplicate id {a.id}")
    data["tasks"].append({
        "id": a.id, "title": a.title, "priority": a.priority, "status": "queued",
        "depends_on": [d for d in a.depends_on.split(",") if d] if a.depends_on else [],
        "next": a.next, "verify": a.verify, "attempts": 0, "evidence": "", "last_commit": "",
    })
    save(data)
    print(f"added {a.id}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("list").set_defaults(fn=cmd_list)
    s.add_parser("pick").set_defaults(fn=cmd_pick)
    for name, fn in (("start", cmd_start), ("done", cmd_done), ("block", cmd_block)):
        q = s.add_parser(name)
        q.add_argument("id")
        q.set_defaults(fn=fn)
        if name == "done":
            q.add_argument("--evidence", default="")
            q.add_argument("--commit", default="")
            q.add_argument("--next", default="")
        if name == "block":
            q.add_argument("--reason", required=True)
    q = s.add_parser("add")
    for f in ("id", "title", "priority", "next", "verify"):
        q.add_argument(f"--{f}", required=True)
    q.add_argument("--depends-on", default="")
    q.set_defaults(fn=cmd_add)
    a = p.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
