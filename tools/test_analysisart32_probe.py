#!/usr/bin/env python3
"""Exercise probe output refusals on disposable copies, before emulator dispatch."""
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import probe_analysisart32 as probe


def main():
    count = 0
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = Path(shutil.copyfile(probe.stage.ROOT / 'build/analysisart32.nes', root / 'input.nes'))
        assets = root / 'assets'
        assets.mkdir()
        (assets / 'input.json').write_text('protected asset\n')
        earlier = root / 'earlier.txt'
        earlier.write_text('earlier evidence\n')
        out = root / 'output'
        out.mkdir()
        snapshots = {path: path.read_bytes() for path in (source, earlier, assets / 'input.json')}

        def refused(directory=out, input_rom=source):
            nonlocal count
            try:
                probe.Outputs(input_rom, assets, directory)
            except ValueError:
                count += 1
            else:
                raise AssertionError(f'accepted unsafe probe output {directory}')
            assert all(path.read_bytes() == data for path, data in snapshots.items())

        with patch.object(probe.romdev, 'call', side_effect=AssertionError('emulator called before refusal')):
            for name in ('team-00.png', 'audio.json', 'report.json'):
                target = out / name
                for original in snapshots:
                    for symbolic in (False, True):
                        target.symlink_to(original) if symbolic else os.link(original, target)
                        refused()
                        target.unlink()
            target = out / 'team-00.png'
            target.mkdir()
            refused()
            target.rmdir()
            refused(input_rom=target)
            alias = root / 'linked-parent'
            alias.symlink_to(root, target_is_directory=True)
            refused(alias / 'new-output')
            stray = out / 'foreign.txt'
            stray.write_text('keep me\n')
            refused()
            assert stray.read_text() == 'keep me\n'
            stray.unlink()
            outputs = probe.Outputs(source, assets, out)
            try:
                outputs.path('../input.nes')
            except ValueError:
                count += 1
            else:
                raise AssertionError('unplanned output accepted')
            assert not list(out.iterdir())
    print(f'PASS: {count} output refusals before emulator dispatch; fresh destinations accepted')


if __name__ == '__main__':
    main()
