#!/usr/bin/env python3
"""Exercise probe output refusals on disposable copies, before emulator dispatch."""
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import probe_homerunart32 as probe


def main():
    count = 0
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = Path(shutil.copyfile(probe.stage.ROOT / 'build/homerunart32.nes', root / 'input.nes'))
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
                probe.Outputs(input_rom, directory, assets)
            except ValueError:
                count += 1
            else:
                raise AssertionError(f'accepted unsafe probe output {directory}')
            assert all(path.read_bytes() == data for path, data in snapshots.items())

        with patch.object(probe.romdev, 'call', side_effect=AssertionError('emulator called before refusal')):
            for name in ('natural-0-080.png', 'home-run.wav', 'summary.json'):
                target = out / name
                for original in snapshots:
                    for symbolic in (False, True):
                        target.symlink_to(original) if symbolic else os.link(original, target)
                        refused()
                        target.unlink()
            target = out / 'natural-0-080.png'
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
            outputs = probe.Outputs(source, out, assets)
            try:
                outputs.path('../input.nes')
            except ValueError:
                count += 1
            else:
                raise AssertionError('unplanned output accepted')
            assert not list(out.iterdir())
    planted_runners()
    print(f'PASS: {count} output refusals before emulator dispatch; fresh destinations accepted')


def planted_runners():
    ram = bytearray(2048)
    ram[0x055E:0x0562] = bytes((0, 255, 255, 255))
    ram[0x056D:0x0570] = bytes((255, 255, 255))
    ram[0x04EE] = 1

    def write(name, payload):
        assert name == 'memory' and payload['op'] == 'write'
        data = bytes.fromhex(payload['hex'])
        ram[payload['offset']:payload['offset'] + len(data)] = data

    with patch.object(probe.romdev, 'call', side_effect=write):
        for walkoff in (False, True):
            probe.plant_runners(walkoff)
            expected = probe.expected_home_run(ram)
            assert expected['runs'] == 4
            assert all(probe.DEBIT <= address < probe.DEBIT + probe.DEBITS for address in expected['debits'])
            if walkoff:
                assert expected['score'] == [3, 6] and expected['over']
    print('PASS: planted runners debit pitcher 0; walk-off credits the home side')


if __name__ == '__main__':
    main()
