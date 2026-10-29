#!/usr/bin/env python3
"""Trace draw-state accesses during a romdev controller probe.

The trace covers scripted frame steps and button presses, excluding loadMedia
startup, state loading and direct CPU calls. It checks the two-byte allocation
and the frozen draw/codec instruction sites. Event PCs alone do not prove which
PRG bank is mapped; the separate mapper tour and CPU guards cover that contract.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

import romdev
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler
from draw32_6502 import DRAW_SEGMENT, CODEC_SEGMENT


def access_sites():
    machine = MPU()
    decoder = Disassembler(machine)
    result = set()
    for origin, code in (DRAW_SEGMENT, CODEC_SEGMENT):
        machine.memory[origin:origin + len(code)] = code
        pc = origin
        while pc < origin + len(code):
            size, _ = decoder.instruction_at(pc)
            if size == 3 and int.from_bytes(bytes(machine.memory[pc + 1:pc + 3]), 'little') in (0x7760, 0x7761):
                result.add(pc)
            pc += size
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('script', type=Path)
    ap.add_argument('arguments', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    original = romdev.call
    allowed = access_sites()
    report = {'range': '7760-777F', 'frames': 0, 'events': [], 'allowed_pcs': [f'{pc:04X}' for pc in sorted(allowed)],
              'limit': 'Scripted frame/input calls only; event PCs do not identify the PRG bank.'}

    def drive(count, button=None, port=0):
        while count:
            frames = min(500, count)
            request = {'on': 'range', 'start': 0x7760, 'end': 0x777F, 'kind': 'both', 'frames': frames, 'limit': 4000}
            if button:
                request['pressDuring'] = [{'frame': 0, 'button': button, 'holdFrames': frames, 'port': port}]
            result = original('watch', request)
            assert not result.get('truncated') and result['total'] == len(result['events']), 'incomplete WRAM trace'
            report['events'].extend(result['events'])
            report['frames'] += frames
            count -= frames
        return result

    def call(name, payload, *positional, **keywords):
        if name == 'loadMedia':
            report['rom_sha256'] = hashlib.sha256(Path(payload['path']).read_bytes()).hexdigest()
        if name == 'frame' and payload.get('op') == 'step':
            return drive(payload.get('count', 1))
        if name == 'input' and payload.get('op') == 'press':
            return drive(payload.get('frames', 4), payload['button'], payload.get('port', 0))
        return original(name, payload, *positional, **keywords)

    romdev.call = call
    sys.argv = [str(args.script), *args.arguments]
    try:
        runpy.run_path(str(args.script), run_name='__main__')
        assert report['events'], 'tour did not exercise the draw seed'
        for event in report['events']:
            pc = int(event['pc'].replace('$', ''), 16)
            address = int(event['address'].replace('$', ''), 16)
            assert pc in allowed and address in (0x7760, 0x7761), event
        report['status'] = 'passed'
        print(f'draw WRAM: {len(report["events"])} accesses at owned sites over {report["frames"]} frames', flush=True)
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
