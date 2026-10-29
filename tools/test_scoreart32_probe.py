#!/usr/bin/env python3
"""Check screenshot preflight without starting an emulator or writing a screenshot."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from build_draw32 import ROOT
import probe_scoreart32 as probe
from scoreart32_convert import read_layout


def main():
    rom_path = ROOT / 'build/scoreart32.nes'
    rom = rom_path.read_bytes()
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory)
        with patch.object(probe.romdev, 'call', side_effect=AssertionError('emulator called before refusal')):
            for filename in ('played-half-1.png', 'planted-half-36.png', 'exhibition-2-second-pick.png',
                             'exhibition-2-pre-game.png'):
                target = out / filename
                for source in (rom_path, ROOT / 'art/scoreart32/score32.px.js',
                               ROOT / 'data/scoreart32/scoreassets.json', ROOT / 'tools/verify.sh'):
                    before = source.read_bytes()
                    for symbolic in (False, True):
                        if symbolic:
                            target.symlink_to(source)
                        else:
                            os.link(source, target)
                        try:
                            probe.preflight(rom, rom_path, out)
                        except ValueError:
                            count += 1
                        else:
                            raise AssertionError(f'accepted {target} alias to {source}')
                        assert source.read_bytes() == before
                        target.unlink()
                target.write_bytes(rom)
                try:
                    probe.preflight(rom, target, out)
                except ValueError:
                    count += 1
                else:
                    raise AssertionError('accepted input ROM at screenshot path')
                assert target.read_bytes() == rom
                target.unlink()
            missing = out / 'played-half-1.png'
            try:
                probe.preflight(rom, missing, out)
            except ValueError:
                count += 1
            else:
                raise AssertionError('accepted missing input at screenshot path')
            assert not missing.exists()
            probe.preflight(rom, rom_path, out)
            assert not list(out.iterdir())
        layout = json.loads((ROOT / 'art/scoreart32/layout.json').read_text())
        for value in ([], {}, None, 7):
            layout['text'][0]['font'] = value
            path = out / 'layout.json'
            path.write_text(json.dumps(layout))
            try:
                read_layout(path)
            except ValueError as exc:
                assert 'font must be' in str(exc)
            else:
                raise AssertionError(f'accepted font {value!r}')
    print(f'PASS: {count} screenshot aliases refused before emulator dispatch; new destinations accepted; four malformed font types refused')


if __name__ == '__main__':
    main()
