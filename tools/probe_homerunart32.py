#!/usr/bin/env python3
"""Replay a played multi-run homer and planted grand slams on the real NTSC core.

Accepts the pinned input or selected output for paired runs. Grand slams and the
walk-off use RAM plants at a controller-reached fence event, not played outcomes.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import build_homerunart32 as stage
from build_scoreart32 import write_atomic
from homerunart32_convert import protect_outputs, rom_frames
from homerunart32_machine import DEBIT, DEBITS, expected_home_run
from probe_frontend32 import exhibition, press
from probe_menu_chr import MapperTrace
from soak_bracket import rd_sys, step, leave_lineup
import romdev

CAPTURES = (80, 88, 96, 528, 536, 544, 600, 720)
CASES = tuple(f'natural-{i}' for i in range(8)) + ('planted-grand-slam', 'planted-walkoff-grand-slam')


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def check_animation(seen, count):
    check(count >= 4 and seen == {'a', 'b'}, 'need four exact captures covering both animation frames')


def output_names():
    return (['fence.state', 'summary.json', 'home-run.wav', 'audio.json',
             'exhibition-2-second-pick.png', 'exhibition-2-pre-game.png']
            + [f'{case}{suffix}' for case in CASES for suffix in ('.json', '-mapper.json')]
            + [f'{case}-{frame:03}.png' for case in CASES for frame in CAPTURES])


class Outputs:
    def __init__(self, source, directory, assets=stage.ASSETS):
        self.source = source
        self.directory = stage.output_path(directory)
        self.names = output_names()
        self.inputs = [stage.REGISTRY, *assets.rglob('*')]
        protect_outputs(source, self.directory, self.names, self.inputs, stage.ROOT / 'build/vendor')
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        if name not in self.names:
            raise ValueError(f'unplanned probe output: {name}')
        target = self.directory / name
        stage.protect_output(self.source, target, self.inputs)
        for parent in (target, *target.parents):
            if parent.is_symlink():
                raise ValueError(f'linked probe output: {parent}')
        if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
            raise ValueError(f'probe output is not an unlinked regular file: {target}')
        return target

    def json(self, name, value):
        write_atomic(self.path(name), (json.dumps(value, indent=2) + '\n').encode())

    def dispatch(self, call, name, payload, **kwargs):
        if name in ('frame', 'state', 'audioDebug') and 'path' in payload:
            path = Path(payload['path'])
            if path.absolute() != self.directory / path.name:
                raise ValueError(f'unplanned emulator output: {path}')
            self.path(path.name)
        return call(name, payload, **kwargs)


def find_event():
    for _ in range(120):
        scene = rd_sys(0x047B)[0]
        if scene == 0x0F:
            leave_lineup()
        elif scene in (0x0B, 0x11):
            press('a', gap=30)
        romdev.call('breakpoint', dict(on='pc', address=0xB6F8, maxFrames=2000))
        cpu, ram = romdev.call('cpu', dict(op='read')), rd_sys(0, 0x800)
        if cpu['pc'] == 0xB6F8 and ram[0x27] == 6 and ram[0x047B] == 5:
            if not (ram[0xC1] & 4 or ram[0x048E] & 0x20):
                return ram
            step(1)
    raise RuntimeError('no qualifying fence event in bounded natural tour')


def plant_runners(walkoff=False):
    plants = [(0x055F, [0, 0, 0]), (0x056D, [0, 0, 0])]
    if walkoff:
        plants += [(0x048A, [0x0B, 3, 2]), (0x04ED, [1, 0])]
    for address, values in plants:
        romdev.call('memory', dict(op='write', region='system_ram', offset=address, hex=bytes(values).hex()))


def capture(label, ram, outputs, digest, pictures):
    oracle = expected_home_run(ram)
    check(1 <= oracle['runs'] <= 4, 'invalid scorer count')
    check(all(DEBIT <= address < DEBIT + DEBITS for address in oracle['debits']), 'invalid pitcher plant')
    trace = MapperTrace(romdev.call, True, 0x15, 14)
    frames, debit_checked, pixel_checks = [], False, 0
    seen = set()
    with patch.object(romdev, 'call', trace.dispatch):
        for frame in range(740):
            live = rd_sys(0, 0x800)
            frames.append(dict(frame=frame, scene=list(live[0x047B:0x047D]),
                               scores=list(live[0x048B:0x048D]), song=live[0x0401], chr=live[0x25],
                               game_over=live[0x04D0], hr=list(live[0x073C:0x073E])))
            if live[0x047B:0x047D] == bytes((5, 3)) and not debit_checked:
                for address in range(DEBIT, DEBIT + DEBITS):
                    check(live[address] == (ram[address] + oracle['debits'].get(address, 0)) & 255,
                          f'pitcher debit differs at ${address:04X}')
                debit_checked = True
            if frame in CAPTURES:
                target = outputs.path(f'{label}-{frame:03}.png')
                romdev.call('frame', dict(op='screenshot', path=str(target)))
                if live[0x047B:0x047D] == bytes((5, 3)) and live[0xAD] == 0x1E:
                    with Image.open(target) as image:
                        actual = image.convert('RGB').tobytes()
                        matches = [name for name, picture in pictures.items() if actual == picture]
                        check(image.size == (256, 224) and len(matches) == 1, 'cutscene pixels differ')
                        seen.add(matches[0])
                    pixel_checks += 1
            step(1)
    end = rd_sys(0, 0x800)
    check(debit_checked, 'pitcher debits were not checked')
    check_animation(seen, pixel_checks)
    check(list(end[0x048B:0x048D]) == oracle['score'], 'scores differ')
    check(bool(end[0x04D0]) == oracle['over'], 'game-over flag differs')
    check(end[0x047B] in (3, 5, 9, 10, 11), 'unexpected return scene')
    report = trace.report()
    check(not report['misaligned'] and not trace.banks[0][0x15], 'invalid mapper writes')
    report.update(rom_sha256=digest, case=label, limit='740 frames from fence; setup and audio replay are untraced.')
    outputs.json(f'{label}-mapper.json', report)
    record = dict(label=label, expected_runs=oracle['runs'], score_before=list(ram[0x048B:0x048D]),
                  score_after=list(end[0x048B:0x048D]), game_over=end[0x04D0], end_scene=end[0x047B],
                  pitcher_debits=oracle['debits'], pixel_checks=pixel_checks, frames_seen=sorted(seen), frames=frames)
    outputs.json(f'{label}.json', record)
    print(f"{label}: PASS {oracle['runs']} runs; scores, pitcher debits, pixels and return", flush=True)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--session', default='homerunart32-events')
    args = ap.parse_args()
    rom = args.rom.read_bytes()
    digest = stage.sha256(rom)
    if digest not in (stage.BASE_SHA256, stage.read_registry()['rom']):
        ap.error('expected pinned analysisart32 or registered homerunart32 ROM')
    outputs = Outputs(args.rom, args.output)
    pictures = {name: bytes(channel for row in rows[8:232] for pixel in row for channel in pixel)
                for name, rows in rom_frames(rom).items()}
    romdev.SESSION = args.session
    raw_call = romdev.call
    results = []
    with patch.object(romdev, 'call', lambda name, payload, **kw: outputs.dispatch(raw_call, name, payload, **kw)):
        exhibition(args.rom, outputs.directory, 2, (11, 29), None, False, False)
        for event in range(8):
            ram = find_event()
            if event == 0:
                romdev.call('state', dict(op='save', name='hr-fence'))
                romdev.call('state', dict(op='export', fromSlot='hr-fence', path=str(outputs.path('fence.state'))))
            results.append(capture(f'natural-{event}', ram, outputs, digest, pictures))
            if results[-1]['expected_runs'] >= 2:
                break
        check(any(result['expected_runs'] >= 2 for result in results), 'no natural multi-run homer')
        for walkoff in (False, True):
            romdev.call('state', dict(op='load', name='hr-fence', render=False, probeLiveness=False))
            plant_runners(walkoff)
            label = 'planted-walkoff-grand-slam' if walkoff else 'planted-grand-slam'
            results.append(capture(label, rd_sys(0, 0x800), outputs, digest, pictures))
            if walkoff:
                check(results[-1]['game_over'] == 1 and results[-1]['end_scene'] == 11, 'walk-off did not reach scoreboard')
        romdev.call('state', dict(op='load', name='hr-fence', render=False, probeLiveness=False))
        audio = romdev.call('audioDebug', dict(op='record', frames=600, path=str(outputs.path('home-run.wav'))))
        outputs.json('audio.json', audio)
    outputs.json('summary.json', dict(rom_sha256=digest,
                 cases=[{k: v for k, v in result.items() if k != 'frames'} for result in results],
                 audio_sha256=stage.sha256(outputs.path('home-run.wav').read_bytes()),
                 limits='NTSC emulator, no hardware/PAL claim. Grand slams and walk-off are planted.'))
    print('PASS home-run real-core tour', flush=True)


if __name__ == '__main__':
    main()
