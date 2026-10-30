#!/usr/bin/env python3
"""Check fixture writes and bounded failures without playing fixture games."""
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unicodedata
from unittest.mock import patch

import homerunart32_fixtures as fixtures
import homerunart32_machine as machine
import probe_homerunart32 as probe
import test_homerunart32 as suite


def cache_guards():
    base = (fixtures.ROOT / 'build/analysisart32.nes').read_bytes()
    name = fixtures.QUICK_FIXTURES[0]
    filename = fixtures.cache_name(name)
    info = dict(frame=fixtures.FIXTURES[name][2], hook=fixtures.FIXTURES[name][1],
                half=0, bat_side=0, slots=[0, 255, 255, 255], score=[0, 0])
    sample = {name: (b'disposable cache data; never unpickled', info)}
    count = 0
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / 'input.nes'
        source.write_bytes(base)
        out = root / 'cache'
        out.mkdir()
        prior = root / 'earlier.json'
        prior.write_text('keep earlier evidence\n')

        def refuse(directory=out, input_path=source, inputs=()):
            nonlocal count
            files = {p: p.read_bytes() for p in (source, prior, *directory.glob('*')) if p.is_file()}
            with patch.object(fixtures, 'ProcessPoolExecutor', side_effect=AssertionError('generation started')):
                try:
                    fixtures.states(input_path, [name], cache=directory, inputs=inputs)
                except ValueError:
                    count += 1
                else:
                    raise AssertionError(f'unsafe cache accepted: {directory}')
            assert all(p.read_bytes() == data for p, data in files.items())

        collision = out / filename
        collision.write_bytes(base)
        refuse(input_path=collision)
        with patch.object(sys, 'argv', ['fixtures', str(collision), '--quick', '--cache', str(out)]):
            with patch.object(fixtures, 'ProcessPoolExecutor', side_effect=AssertionError('generation started')):
                try:
                    fixtures.main()
                except SystemExit as exc:
                    assert exc.code == 2
                else:
                    raise AssertionError('CLI accepted input/cache collision')
        assert collision.read_bytes() == base
        collision.unlink()
        for value in ('earlier evidence', '[]', 'null', '{"format":"another-stage"}'):
            (out / 'provenance.json').write_text(value)
            refuse()
        (out / 'provenance.json').unlink()
        for target_name in (filename, 'provenance.json'):
            target = out / target_name
            for original in (source, prior):
                for symbolic in (False, True):
                    target.symlink_to(original) if symbolic else os.link(original, target)
                    refuse()
                    target.unlink()
        collision.mkdir()
        refuse()
        collision.rmdir()
        (out / 'unrelated.txt').write_text('keep me')
        refuse()
        (out / 'unrelated.txt').unlink()
        alias = root / 'alias'
        alias.symlink_to(root, target_is_directory=True)
        refuse(alias / 'new-cache')

        fixtures.save_cache(source, base, sample, out)
        assert fixtures.load_cache(base, out) == sample
        fixtures.save_cache(source, base, sample, out)
        assert fixtures.states(source, [name], cache=out) == sample
        refuse(inputs=[out / filename])
        record = json.loads((out / 'provenance.json').read_text())
        malformed = [[], None, dict(record, states=[]), dict(record, states={name: None}),
                     dict(record, states={name: dict(record['states'][name], summary=None)}),
                     dict(record, states={name: dict(record['states'][name], file=[])})]
        for value in malformed:
            (out / 'provenance.json').write_text(json.dumps(value))
            assert fixtures.load_cache(base, out) == {}
        (out / 'provenance.json').write_text(json.dumps(record))
        (out / filename).write_bytes(b'corrupted cache data')
        assert fixtures.load_cache(base, out) == {}
        fixtures.save_cache(source, base, sample, out)
        assert fixtures.load_cache(base, out) == sample

        fixtures.protect_cache(source, fixtures.CACHE)
        assert source.read_bytes() == base and prior.read_text() == 'keep earlier evidence\n'
    print(f'PASS {count} cache refusals, real CLI rejection, owned-cache updates and malformed-cache misses')


def sweep_bound():
    class Stalled:
        def __init__(self):
            self.ram = bytearray(2048)
            self.ram[0x047B:0x047D] = bytes((5, 2))
            self.on_pc = {}
            self.mask = 0
            self.frame = 42

        def frames(self, count):
            self.frame += count
            if self.frame > 3044:
                raise RuntimeError('external sentinel: sweep did not stop')

    stalled = Stalled()
    with patch.object(machine, 'restore', return_value=stalled):
        try:
            machine.sweep(b'', b'', 0)
        except AssertionError as exc:
            assert str(exc) == 'the cutscene never exited'
        else:
            raise AssertionError('stalled sweep accepted')
    assert stalled.frame == 3043
    print('PASS sweep stops after 3001 elapsed frames even with zero shown frames')


def case_aliases_and_verifier():
    source = fixtures.ROOT / 'build/analysisart32.nes'
    base = source.read_bytes()
    good = (fixtures.ROOT / 'build/homerunart32.nes').read_bytes()
    with suite.checkout(source) as (initial, elsewhere):
        repo = initial.rename(initial.with_name('répo'))
        suite.install(repo, suite.installed_outputs())
        vendor = repo / 'build/vendor'
        vendor.mkdir()
        (vendor / 'keep.js').write_text('keep vendor bytes')
        source = repo / 'build/analysisart32.nes'
        rom = elsewhere / 'good.nes'
        rom.write_bytes(good)
        aliases = [repo.with_name(repo.name.upper()), repo.with_name(unicodedata.normalize('NFD', repo.name))]
        targets = ['art/homerunart32', 'data/homerunart32', 'build/vendor',
                   'build/homerunart32-design', 'build/homerunart32-fixtures']
        count = 0
        for alias in aliases:
            if not alias.exists() or not alias.samefile(repo):
                continue
            before = suite.snapshot(repo)
            for directory in targets:
                target = alias / directory
                commands = [
                    [sys.executable, '-B', str(repo / 'tools/build_homerunart32.py'), str(source),
                     '-o', str(target / 'keep.js')],
                    [sys.executable, '-B', '-c',
                     'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                     'from homerunart32_convert import protect_outputs;'
                     'protect_outputs(Path(sys.argv[2]),Path(sys.argv[3]),["out.json"],[],Path(sys.argv[4]))',
                     str(repo / 'tools'), str(source), str(target / 'converter'), str(vendor)],
                    [sys.executable, '-B', '-c',
                     'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                     'from probe_homerunart32 import Outputs;Outputs(Path(sys.argv[2]),Path(sys.argv[3]))',
                     str(repo / 'tools'), str(source), str(target / 'probe')],
                    [sys.executable, '-B', '-c',
                     'import sys;from pathlib import Path;from unittest.mock import patch;sys.path.insert(0,sys.argv[1]);'
                     'import homerunart32_fixtures as f;'
                     'p=patch.object(f,"ProcessPoolExecutor",side_effect=AssertionError("generation started"));p.start();'
                     'f.states(Path(sys.argv[2]),f.QUICK_FIXTURES,cache=Path(sys.argv[3]))',
                     str(repo / 'tools'), str(source), str(target / 'cache')],
                ]
                for command in commands:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0 or 'protected' not in result.stderr:
                        raise AssertionError(f'case alias accepted: {command}: {result.stderr[-500:]}')
                    count += 1
            assert suite.snapshot(repo) == before
        print(f'PASS {count} case/Unicode alias refusals across builder, converter, probe and cache; files unchanged')

        assets_path = repo / 'build/homerunart32/homerunassets.json'
        original = assets_path.read_bytes()
        assets = suite.HomerunAssets.parse(json.loads(original))
        first, victim = next(iter(assets.planes)), sorted(suite.model.protected_ids(base))[5]
        record = assets.record()
        record['planes'][f'{victim:02X}'] = record['planes'].pop(f'{first:02X}')
        record['planes'] = dict(sorted(record['planes'].items()))
        record['metamap'] = bytes(victim if b == first else b for b in assets.metamap).hex()
        tampered = suite.HomerunAssets.parse(record)
        bad = bytearray(good)
        for quadrant in range(4):
            old = suite.stage.locate(1, 0x8400 + 0x100 * quadrant + first)
            new = suite.stage.locate(1, 0x8400 + 0x100 * quadrant + victim)
            bad[new], bad[old] = assets.planes[first][quadrant], base[old]
        offset = suite.stage.locate(1, 0x8DF0)
        bad[offset:offset + 240] = tampered.metamap
        corrupted = elsewhere / 'bad-victory.nes'
        corrupted.write_bytes(bad)
        command = [sys.executable, '-B', str(repo / 'tools/test_homerunart32.py'), str(source), '--verify-only', '--candidate']
        result = subprocess.run(command + [str(rom)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        for changed_assets in (False, True):
            if changed_assets:
                assets_path.write_text(tampered.dumps())
            result = subprocess.run(command + [str(corrupted)], capture_output=True, text=True, timeout=30)
            assert result.returncode == 1 and 'FAIL' in result.stdout, result.stdout + result.stderr
        print('PASS verify-only rejects VICTORY corruption with genuine or tampered installed assets')


def animation_checks():
    for seen, count in (({'a'}, 4), ({'a', 'b'}, 3)):
        try:
            probe.check_animation(seen, count)
        except AssertionError:
            pass
        else:
            raise AssertionError('incomplete animation accepted')
    probe.check_animation({'a', 'b'}, 4)
    result = subprocess.run([sys.executable, '-B', '-O', '-c',
                             'import sys;sys.path.insert(0,"tools");'
                             'from probe_homerunart32 import check_animation;check_animation({"a"},4)'],
                            cwd=fixtures.ROOT, capture_output=True, text=True)
    assert result.returncode == 1 and 'four exact captures' in result.stderr
    print('PASS animation requires four captures of both frames, including under python -O')


if __name__ == '__main__':
    cache_guards()
    sweep_bound()
    case_aliases_and_verifier()
    animation_checks()
