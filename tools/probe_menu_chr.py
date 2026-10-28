#!/usr/bin/env python3
"""Trace MMC1 writes while running an existing controller probe.

    python tools/probe_menu_chr.py --report build/chr.json tools/probe_password_ui.py --rom build/visualtables32.nes --played 31
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import sys

import romdev


class MapperTrace:
    def __init__(self, call):
        self.call = call
        self.shift = self.bits = self.frames = self.writes = 0
        self.banks = (Counter(), Counter())
        self.sources = Counter()
        self.requests = (Counter(), Counter())
        self.misaligned = []

    def step(self, frames, button=None, port=0):
        remaining = frames
        while remaining:
            count = min(40, remaining)
            self.call("state", dict(op="save", name="mapper-window"))
            while True:
                args = dict(on="range", start=0x8000, end=0xFFFF,
                            kind="write", frames=count, limit=4000)
                if button is not None:
                    args["pressDuring"] = [dict(button=button, port=port,
                                               frame=0, holdFrames=count)]
                result = self.call("watch", args)
                if not result.get("truncated") and result["total"] == len(result["events"]):
                    break
                assert count > 1, "mapper log truncated within one frame"
                self.call("state", dict(op="load", name="mapper-window", render=False,
                                        probeLiveness=False))
                count = max(1, count // 2)
            assert result["total"] == len(result["events"]), "mapper log incomplete"
            for index, event in enumerate(result["events"]):
                address = int(event["address"].replace("$", ""), 16)
                value = int(event["value"], 16)
                if event["pc"] in ("$C11E", "$C136"):
                    self.requests[event["pc"] == "$C136"][value & 31] += 1
                    if self.bits and len(self.misaligned) < 4:
                        self.misaligned.append(dict(frame=self.frames, bits=self.bits,
                            events=result["events"][max(0, index - 8):index + 7]))
                self.writes += 1
                if value & 0x80:
                    self.shift = self.bits = 0
                    continue
                self.shift |= (value & 1) << self.bits
                self.bits += 1
                if self.bits == 5:
                    register = (address >> 13) & 3
                    if register in (1, 2):
                        self.banks[register - 1][self.shift] += 1
                        self.sources[f"{event['pc']}:CHR{register - 1}:{self.shift:02X}"] += 1
                    self.shift = self.bits = 0
            self.frames += count
            remaining -= count
        return result

    def dispatch(self, name, payload, *args, **kwargs):
        if name == "loadMedia":
            self.shift = self.bits = 0
        if name == "frame" and payload.get("op") == "step":
            return self.step(payload.get("count", 1))
        if name == "input" and payload.get("op") == "press":
            return self.step(payload.get("frames", 4), payload["button"], payload.get("port", 0))
        return self.call(name, payload, *args, **kwargs)

    def report(self):
        return dict(frames=self.frames, mapper_writes=self.writes,
                    chr0={f"{k:02X}": v for k, v in sorted(self.banks[0].items())},
                    chr1={f"{k:02X}": v for k, v in sorted(self.banks[1].items())},
                    sources=dict(sorted(self.sources.items())),
                    requests=[{f"{k:02X}": v for k, v in sorted(c.items())} for c in self.requests],
                    misaligned=self.misaligned,
                    limit="Only this scripted tour is covered; loadMedia startup and direct CPU calls are not traced.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--forbid-menu-bank", action="store_true")
    parser.add_argument("script", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    trace = MapperTrace(romdev.call)
    romdev.call = trace.dispatch
    sys.argv = [str(args.script), *args.arguments]
    try:
        runpy.run_path(str(args.script), run_name="__main__")
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(trace.report(), indent=2) + "\n")
        print(f"MMC1 trace: {trace.frames} frames, {trace.writes} writes; {args.report}")
    if args.forbid_menu_bank:
        assert not trace.misaligned, "mapper reconstruction lost serial alignment"
        assert all(not counter[0x19] for counter in trace.banks), "stock flow selected CHR $19"


if __name__ == "__main__":
    main()
