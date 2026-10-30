#!/usr/bin/env python3
"""Check the Power Analysis card on romdev through controller input.

Compares real screenshots with a composition of ROM graphics and live PPU memory,
including the split strip during entry and count-up. This is emulator evidence,
not physical-hardware or PAL validation. Audio inspection advances untraced frames.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops

import analysisart32_machine as machine
import build_analysisart32 as stage
from analysisart32_assets import AnalysisRatings
from analysisart32_convert import protect_outputs
from build_draw32 import read
from build_scoreart32 import write_atomic
from modeart32_assets import ModeAssets
from probe_frontend32 import boot_mode, canonical_series, press, select, wait_picker
from probe_modeart32 import memory
from soak_bracket import rd_sys, step
import romdev

PHASE_TEAMS = (0, 13, 31)
PHASE_FRAMES = 80
CAPTURE_PHASES = (0, 1, 8, 16, 24, 32, 40, 56, 72)
PASSWORD = '4995FEC5ESTVP6KM5YCNYM'


def output_names():
    return ([f'team-{team:02d}.png' for team in range(32)]
            + [f'phase-{team:02d}-{frame:02d}.png' for team in PHASE_TEAMS for frame in CAPTURE_PHASES]
            + ['return-mode.png', 'resume-bracket.png', 'resume.state', 'audio.json', 'audio.wav',
               'split-writes.json', 'report.json'])


class Outputs:
    def __init__(self, source, assets, output):
        self.source, self.assets = source, assets
        self.directory = stage.output_path(output)
        self.inputs = [stage.REGISTRY, *assets.rglob('*')]
        self.names = output_names()
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

    def screenshot(self, name):
        target = self.path(name)
        romdev.call('frame', dict(op='screenshot', path=str(target)))
        return target

    def json(self, name, value):
        write_atomic(self.path(name), (json.dumps(value, indent=2) + '\n').encode())


def visible(oam):
    return [tuple(oam[i:i+4]) for i in range(0, 256, 4) if oam[i] < 0xEF]


def card(rom, assets, team, outputs, name, settled=False):
    ram = memory('system_ram', 0, 2048)
    assert ram[0x047B] == 0x15 and ram[0x04EF] == team, name
    assert ram[0xAD] == 0x1E and ram[0x23:0x27] == bytes((0x1B, 0x1B, 0x18, 6)), name
    nt = memory('nes_nametables', 0, 1024)
    palette = memory('nes_palette', 0, 32)
    oam = memory('nes_oam', 0, 256)
    expected_nt, expected_pal, expected_oam = machine.card_frame(rom, team, assets)
    assert nt == expected_nt, f'{name}: name, digits or background differ'
    assert all(palette[i] == expected_pal[i] for i in range(32) if i % 4), f'{name}: palette'
    assert palette[0] == expected_pal[0], f'{name}: backdrop'
    assert oam[:4] == bytes((0x40, 0xFE, 0x20, 0xF8)), f'{name}: split marker'
    if settled:
        assert visible(oam) == visible(expected_oam), f'{name}: rating balls or flags'
        assert tuple(ram[0xBC:0xC0]) == AnalysisRatings.from_rom(rom).values[team], name
        assert ram[0xB8] == 2, f'{name}: animation incomplete'
    for sprite in visible(oam)[1:]:
        y, tile, attr, x = sprite
        if tile == assets.ball_tile and attr & 3 == assets.ball_palette:
            assert x in (128, 144, 160, 176) and y + 1 in (88, 104, 120, 136), name
    path = outputs.screenshot(name)
    actual = Image.open(path).convert('RGB')
    expected = machine.compose(rom, nt, palette, oam).crop((0, 8, 256, 232))
    assert actual.size == expected.size, (name, actual.size)
    difference = ImageChops.difference(actual, expected)
    assert difference.getbbox() is None, f'{name}: visible pixels differ at {difference.getbbox()}'
    return dict(image=name, counters=list(ram[0xBC:0xC0]), state=ram[0xB8],
                visible_sprites=len(visible(oam)), pixels='exact', split_lines='64..72 exact')


def split_trace(outputs):
    trace = romdev.call('watch', dict(on='range', start=0xA000, end=0xDFFF,
                                     kind='write', frames=12, limit=1000))
    assert not trace['truncated'] and trace['total'] == len(trace['events'])
    shift = count = 0
    banks = []
    for event in trace['events']:
        address, value = int(event['address'].lstrip('$'), 16), int(event['value'], 16)
        assert not value & 0x80, 'unexpected MMC1 reset in stable card'
        shift |= (value & 1) << count
        count += 1
        if count == 5:
            if address >= 0xC000:
                banks.append(shift)
            else:
                assert shift == 0x1B
            shift = count = 0
    assert count == 0 and banks == [0x18, 6] * 12, banks
    outputs.json('split-writes.json', dict(trace=trace, chr1_commits=banks,
                 limit='Write order is observed; this watch API supplies no scanline timestamps.'))
    return banks


def return_mode(rom, outputs):
    press('b', gap=60)
    ram = memory('system_ram', 0, 2048)
    assert ram[0x047B] == 7 and ram[0x2C:0x2E] == b'\0\0'
    assets = ModeAssets.load(stage.ROOT / 'build/stockart32/modeassets.json')
    assert memory('nes_nametables', 0, 1024) == assets.screen('main')
    assert memory('nes_chr', 4096, 4096) == read(rom, 'chr', 0x6000, 4096)
    palette = memory('nes_palette', 0, 32)
    assert all(palette[i] == assets.palette[i] for i in range(32) if i % 4)
    assert palette[0] == assets.palette[0] and ram[0x0401] == 6
    outputs.screenshot('return-mode.png')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--assets', type=Path, default=stage.ASSETS)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--session', default='analysisart32-ui')
    ap.add_argument('--bracket-state', default='analysisart32-after-analysis')
    args = ap.parse_args()
    registry = stage.read_registry()
    rom = args.rom.read_bytes()
    if stage.sha256(rom) != registry['rom']:
        ap.error('ROM differs from registered analysisart32')
    assets = stage.load_assets(args.assets, registry)
    outputs = Outputs(args.rom, args.assets, args.output)
    romdev.SESSION = args.session
    report = dict(rom_sha256=stage.sha256(rom), phases=[], teams=[], password=PASSWORD)
    boot_mode(args.rom, 2, PASSWORD)
    wait_picker()
    series = canonical_series()
    print(f'ROM SHA256 {report["rom_sha256"]}; controller-only all32 and phase tour', flush=True)
    for team in range(32):
        select(team)
        press('a', frames=1, gap=1)
        if team in PHASE_TEAMS:
            visible_frame = 0
            for frame in range(PHASE_FRAMES):
                ram = memory('system_ram', 0, 2048)
                if ram[0x047B] == 0x15 and ram[0xAD] == 0x1E:
                    if visible_frame in CAPTURE_PHASES:
                        report['phases'].append(card(rom, assets, team, outputs, f'phase-{team:02d}-{visible_frame:02d}.png'))
                    visible_frame += 1
                step(1)
            assert visible_frame > max(CAPTURE_PHASES), f'team {team}: missing visible phases'
        else:
            step(100)
        report['teams'].append(card(rom, assets, team, outputs, f'team-{team:02d}.png', settled=True))
        assert canonical_series() == series
        if team == 31:
            report['chr1_commits'] = split_trace(outputs)
            audio = romdev.call('audioDebug', dict(op='inspect', chip='nes', frames=180, sampleEvery=1))
            assert audio['transitions'] > 20 and rd_sys(0x0401)[0] == 6
            outputs.json('audio.json', audio)
            report['audio_transitions'] = audio['transitions']
            report['audio_recording'] = romdev.call('audioDebug', dict(op='record', frames=180,
                                            path=str(outputs.path('audio.wav'))))
        press('a' if team % 2 else 'b', gap=30)
        wait_picker()
        assert rd_sys(0x07C0, 2) == bytes((team >> 3, team & 7))
        assert canonical_series() == series
        print(f'team {team:02d}: exact card pixels, names, ratings, flags, palette; return and series pass', flush=True)
    return_mode(rom, outputs)
    assert canonical_series() == series
    press('a', gap=60)
    press('a', gap=60)
    assert rd_sys(0x27)[0] == 11 and canonical_series() == series
    outputs.screenshot('resume-bracket.png')
    romdev.call('state', dict(op='save', name=args.bracket_state))
    state_path = outputs.path('resume.state')
    romdev.call('state', dict(op='export', fromSlot=args.bracket_state, path=str(state_path)))
    report['resume_state'] = args.bracket_state
    report['resume_path'] = str(state_path)
    assert len(report['phases']) == len(PHASE_TEAMS) * len(CAPTURE_PHASES)
    report['series'] = series
    report['limits'] = 'Real-core NTSC captures, no hardware/PAL claim. Audio is APU activity; split watch has no scanline times.'
    outputs.json('report.json', report)
    print(f'{len(report["phases"])} animation/entry/rest frames exact; 32 teams pass; resume state {args.bracket_state}', flush=True)


if __name__ == '__main__':
    main()
