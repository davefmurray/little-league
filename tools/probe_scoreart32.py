#!/usr/bin/env python3
"""Verify the scoreboard on romdev during a played WATCH exhibition and planted edge states.

Controller input reaches the first board and completes the game. The explicit edge-state
section restores that board and writes RAM to exercise extra innings and marker glyphs.
"""
import argparse
import hashlib
from pathlib import Path

import romdev
from build_draw32 import locate
from build_draw32 import ROOT, refuse_aliases
from build_scoreart32 import protect_output
from probe_frontend32 import exhibition, press
from scoreart32_assets import ASSETS, Board, ScoreAssets, drawn
from soak_bracket import rd_sys, step, wait_for


def memory(region, start, size):
    return bytes.fromhex(romdev.call('memory', dict(op='read', region=region,
                         offset=start, length=size, inline=True))['hex'])


def write(address, values):
    romdev.call('memory', dict(op='write', region='system_ram', offset=address,
                              hex=bytes(values).hex()))


def protect_screenshot(rom, path, source=None):
    protect_output(source or ROOT / 'build/scoreart32.nes', path)
    refuse_aliases(path, [ASSETS], {hashlib.sha256(rom).hexdigest()})


def preflight(rom, source, out):
    names = ['exhibition-2-second-pick', 'exhibition-2-pre-game']
    names += [f'played-half-{half}' for half in range(1, 42)]
    names += [f'planted-half-{half}' for half in (14, 15, 28, 29, 36)]
    for name in names:
        protect_screenshot(rom, out / f'{name}.png', source)


def check(rom, asset, out, label):
    path = out / f'{label}.png'
    protect_screenshot(rom, path)
    ram = memory('system_ram', 0, 2048)
    assert ram[0x047B] == 0x0B, label
    board = Board(ram[0x048A], ram[0x06F6:0x0720], tuple(ram[0x048B:0x048D]),
                  tuple(tuple(ram[0x0738 + 2*k:0x073A + 2*k]) for k in range(7)))
    expected = bytearray(asset.nametable + asset.attributes)
    for (col, row), tile in drawn(board).items():
        expected[row * 32 + col] = tile
    assert memory('nes_nametables', 0, 1024) == expected, f'{label}: score or background'
    assert memory('nes_chr', 4096, 4096) == asset.chr, label
    start = locate('chr', 0x18 * 4096)
    assert memory('nes_chr', 0, 4096) == rom[start:start + 4096], label
    palette = bytearray(memory('nes_palette', 0, 32))
    for i in range(0, 16, 4):
        palette[i + 16] = palette[i]
    assert palette == asset.palette, f'{label}: palette'
    oam = memory('nes_oam', 0, 256)
    assert oam == ram[0x0200:0x0300], f'{label}: OAM upload'
    assert ram[0x2C:0x2E] == b'\0\0', f'{label}: NMI guards'
    romdev.call('frame', dict(op='screenshot', path=str(path)))
    print(f'{label}: half={board.halves} teams={ram[0x04EF:0x04F1].hex()} '
          f'runs={board.runs} game-over={ram[0x04D0]}; exact 1024-byte board, palette, CHR05/18 and OAM', flush=True)


def edge_states(rom, asset, out):
    for index, half in enumerate((14, 15, 28, 29, 36)):
        romdev.call('state', dict(op='load', name='scoreart-natural', render=False, probeLiveness=False))
        line = bytes((i * 3 + index) % 10 for i in range(42))
        if half in (14, 36):
            line = line[:half-1] + bytes((0x80 if half == 14 else 0x83,)) + line[half:]
        write(0x048A, [half])
        write(0x048B, [16 + index, 18 + index])
        write(0x06F6, line)
        write(0x0738, [(k * 23 + index) & 255 for k in range(14)])
        write(0x04EF, [index, 31-index])
        write(0x04D0, [0])
        write(0x0402, [255])
        write(0x07EE, [1])
        write(0x047B, [0x0A])
        wait_for(lambda: rd_sys(0x047B)[0] == 0x0B, 120, 1, 'planted board')
        step(3)
        check(rom, asset, out, f'planted-half-{half}')
    romdev.call('state', dict(op='load', name='scoreart-natural', render=False, probeLiveness=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--session', default='scoreart32-ui')
    args = ap.parse_args()
    romdev.SESSION = args.session
    data, asset = args.rom.read_bytes(), ScoreAssets.load(ASSETS)
    out = args.output.resolve()
    preflight(data, args.rom, out)
    out.mkdir(parents=True, exist_ok=True)
    print(f'ROM SHA256 {hashlib.sha256(data).hexdigest()}; WATCH 31/30, played boards plus explicit RAM edge states', flush=True)
    exhibition(args.rom, out, 2, [31, 30], None, False, False)
    press('a', gap=10)
    seen = set()
    for _ in range(10000):
        scene = rd_sys(0x047B)[0]
        if scene == 0x11:
            press('a', gap=10)
        if scene == 0x0B:
            step(2)
            if rd_sys(0x047B)[0] != 0x0B:
                continue
            half = rd_sys(0x048A)[0]
            if half not in seen:
                check(data, asset, out, f'played-half-{half}')
                if not seen:
                    romdev.call('state', dict(op='save', name='scoreart-natural'))
                    edge_states(data, asset, out)
                seen.add(half)
            if rd_sys(0x04D0)[0]:
                for _ in range(80):
                    press('a', gap=60)
                    if rd_sys(0x047B)[0] == 1:
                        print('PASS: played Exhibition final and title return', flush=True)
                        return
                raise AssertionError('final did not return to title')
            press('a', gap=2)
        step(30)
    raise AssertionError('WATCH game did not finish')


if __name__ == '__main__':
    main()
