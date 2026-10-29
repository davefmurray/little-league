#!/usr/bin/env python3
"""Refuse probe destinations that alias inputs before any emulator request."""
import os
from pathlib import Path
import sys
import shutil
import tempfile
from unittest.mock import patch

import probe_stockart32 as probe


def main():
    stage = probe.stage
    source = stage.ROOT / 'build/stockart32.nes'
    protected = [source, stage.ROOT / 'tools/verify.sh', stage.REGISTRY,
                 stage.ROOT / 'art/stockart32/characters.json',
                 stage.ASSETS / stage.MODE_JSON, stage.ASSETS / stage.SCORE_JSON]
    count = 0
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        output = scratch / 'output'
        output.mkdir()
        copies = scratch / 'inputs'
        copies.mkdir()
        protected = [Path(shutil.copyfile(path, copies / f'{i}-{path.name}'))
                     for i, path in enumerate(protected)]
        source = protected[0]
        unrelated = copies / 'unrelated-evidence.txt'
        unrelated.write_text('earlier evidence remains intact\n')
        protected.append(unrelated)
        with patch.object(probe.romdev, 'call', side_effect=AssertionError('emulator called before refusal')):
            for tour, name in (('mode', 'p1-main-0.png'), ('mode', 'mode-audio.json'),
                               ('score', 'played-half-1.png')):
                target = output / name
                for original in protected:
                    before = original.read_bytes()
                    for symbolic in (False, True):
                        if symbolic:
                            target.symlink_to(original)
                        else:
                            os.link(original, target)
                        argv = ['probe', '--rom', str(source), '--output', str(output), '--tour', tour]
                        try:
                            with patch.object(sys, 'argv', argv):
                                probe.main()
                        except ValueError:
                            count += 1
                        else:
                            raise AssertionError(f'accepted {target} alias to {original}')
                        assert original.read_bytes() == before
                        target.unlink()
                try:
                    probe.preflight(target, stage.ASSETS, output, tour)
                except ValueError:
                    count += 1
                else:
                    raise AssertionError('accepted a missing input at an output path')
            for tour in ('mode', 'score'):
                probe.preflight(source, stage.ASSETS, output, tour)
            audio = output / 'mode-audio.json'
            audio.mkdir()
            try:
                probe.preflight(source, stage.ASSETS, output, 'mode')
            except ValueError:
                count += 1
            else:
                raise AssertionError('accepted a directory as the audio output')
            audio.rmdir()
            assert not list(output.iterdir())
    print(f'PASS: {count} screenshot/audio/input collisions refused before emulator dispatch; fresh destinations accepted')


if __name__ == '__main__':
    main()
