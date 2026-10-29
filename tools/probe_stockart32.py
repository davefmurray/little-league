#!/usr/bin/env python3
"""Run the accepted menu or scoreboard emulator tour with generated stock-character assets.

Checks retain the original probes' controller paths, exact VRAM/palette assertions,
and disclosed planted scoreboard cases. No physical-hardware claim is made.
"""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

import build_stockart32 as stage
import probe_modeart32 as mode_probe
import probe_scoreart32 as score_probe
import romdev


def output_names(tour):
    if tour == 'score':
        labels = ['exhibition-2-second-pick', 'exhibition-2-pre-game']
        labels += [f'played-half-{half}' for half in range(1, 42)]
        labels += [f'planted-half-{half}' for half in (14, 15, 28, 29, 36)]
    else:
        labels = []
        for port in (1, 2):
            for menu in ('main', 'championship', 'exhibition'):
                labels += [f'p{port}-{menu}-{choice}' for choice in (0, 1, 2, 'down-wrap', 'up-wrap')]
                if menu != 'main':
                    labels.append(f'p{port}-{menu}-back')
            labels.append(f'p{port}-main-b')
        labels += ['analysis-return', 'password-return']
    return tuple(f'{label}.png' for label in labels) + (('mode-audio.json',) if tour == 'mode' else ())


def preflight(source, assets, output, tour):
    inputs = [stage.REGISTRY, *assets.rglob('*')]
    paths = tuple(output / name for name in output_names(tour))
    for path in paths:
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise ValueError(f'output must be an unlinked regular file: {path}')
        stage.protect_output(source, path, inputs)
        stage.score_stage.refuse_inside(path, assets)
    return paths, inputs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--assets', type=Path, default=stage.ASSETS)
    ap.add_argument('--tour', choices=('mode', 'score'), required=True)
    ap.add_argument('--session', default='stockart32-ui')
    args = ap.parse_args()
    registry = stage.read_registry()
    stage.load_assets(args.assets, registry)
    if stage.sha256(args.rom.read_bytes()) != registry['rom']:
        ap.error('ROM differs from the stockart32 digest registry')
    out = args.output.resolve()
    paths, inputs = preflight(args.rom, args.assets, out, args.tour)
    allowed = {path.resolve() for path in paths if path.suffix == '.png'}
    original_call = romdev.call

    def checked_call(name, payload, *positional, **keywords):
        if name == 'frame' and payload.get('op') == 'screenshot':
            destination = Path(payload['path'])
            if destination.resolve() not in allowed:
                raise ValueError(f'unplanned screenshot destination {destination}')
            stage.protect_output(args.rom, destination, inputs)
        return original_call(name, payload, *positional, **keywords)

    probe = mode_probe if args.tour == 'mode' else score_probe
    asset = stage.MODE_JSON if args.tour == 'mode' else stage.SCORE_JSON
    argv = [str(Path(__file__)), '--rom', str(args.rom), '--output', str(out), '--session', args.session]
    with patch.object(probe, 'ASSETS', args.assets / asset), patch.object(sys, 'argv', argv), \
            patch.object(romdev, 'call', checked_call):
        probe.main()


if __name__ == '__main__':
    main()
