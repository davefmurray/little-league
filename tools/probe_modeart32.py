#!/usr/bin/env python3
"""Check the sunny-ballpark menus through controller input on the romdev core.

Checks exact nametables, mapped CHR and all cursor sprites. Screenshots and APU
activity supplement the CPU suite; this does not verify physical hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path

import romdev
from build_draw32 import locate
from modeart32_assets import ASSETS, ModeAssets
from modeart32_convert import cursor_sprites
from probe_frontend32 import canonical_series, press, select, wait_picker
from probe_password_ui import key_path
from soak_bracket import rd_sys, step, wait_for


def memory(region, offset, length):
    return bytes.fromhex(romdev.call('memory', dict(op='read', region=region,
                         offset=offset, length=length, inline=True))['hex'])


def check_view(rom, assets, out, name, choice, label):
    assert rd_sys(0x047B)[0] == 7, (label, rd_sys(0x047B).hex())
    assert rd_sys(0xB9)[0] == choice, (label, rd_sys(0xB9).hex())
    assert rd_sys(0xBA)[0] == (0 if name == 'main' else 3)
    assert memory('nes_nametables', 0, 1024) == assets.screen(name), label
    palette = bytearray(memory('nes_palette', 0, 32))
    for index in range(0, 16, 4):
        palette[index + 16] = palette[index]  # $3F10/14/18/1C mirror the background entries.
    assert palette == assets.palette, label
    assert memory('nes_chr', 4096, 4096) == assets.chr, label
    start = locate('chr', 0x1B * 4096)
    assert memory('nes_chr', 0, 4096) == rom[start:start + 4096], label
    entry = choice + (3 if name == 'exhibition' else 0)
    expected = bytes(v for sprite in cursor_sprites(rom, *assets.cursor_origin(entry)) for v in sprite)
    oam = memory('nes_oam', 0, 256)
    assert oam[:16] == expected, (label, oam[:16].hex(), expected.hex())
    assert all(y >= 0xEF for y in oam[16::4]), label
    assert rd_sys(0x0401)[0] == 6 and rd_sys(0x2C, 2) == b'\0\0'
    romdev.call('frame', dict(op='screenshot', path=str(out / f'{label}.png')))
    print(f'{label}: exact screen and palette, CHR06/1B, ball {entry}, song06, guards clear', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--session', default='modeart32-ui')
    args = ap.parse_args()
    romdev.SESSION = args.session
    data = args.rom.read_bytes()
    assets = ModeAssets.load(ASSETS)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    print(f'ROM SHA256 {digest}; controller-only menu tour', flush=True)
    for port in (0, 1):
        romdev.call('loadMedia', dict(platform='nes', path=str(args.rom.resolve())))
        step(120)
        press('start', port, gap=60)
        for name in ('main', 'championship', 'exhibition'):
            if name != 'main':
                if name == 'exhibition':
                    press('down', gap=20)
                press('a', gap=60)
            for choice in range(3):
                check_view(data, assets, out, name, choice, f'p{port + 1}-{name}-{choice}')
                press('down', gap=20)
            check_view(data, assets, out, name, 0, f'p{port + 1}-{name}-down-wrap')
            press('up', gap=20)
            check_view(data, assets, out, name, 2, f'p{port + 1}-{name}-up-wrap')
            press('down', gap=20)
            if name != 'main':
                press('b', gap=60)
                check_view(data, assets, out, 'main', 0, f'p{port + 1}-{name}-back')
        press('b', gap=60)
        check_view(data, assets, out, 'main', 0, f'p{port + 1}-main-b')
    audio = romdev.call('audioDebug', dict(op='inspect', chip='nes', frames=180, sampleEvery=1))
    assert audio['transitions'] > 20
    (out / 'mode-audio.json').write_text(json.dumps(audio, indent=2) + '\n')
    print(f'menu audio: {audio["transitions"]} APU transitions across 180 frames', flush=True)
    baseline = canonical_series()
    for _ in range(2):
        press('down', gap=20)
    press('a', gap=60)
    wait_picker()
    select(31)
    press('a', gap=120)
    assert rd_sys(0x047B)[0] == 0x15
    press('b', gap=30)
    wait_picker()
    press('b', gap=60)
    check_view(data, assets, out, 'main', 0, 'analysis-return')
    assert canonical_series() == baseline
    press('a', gap=60)
    press('a', gap=60)
    wait_for(lambda: rd_sys(0x047B)[0] == 0x19, 240, 10, 'password entry')
    for button in key_path(data, rd_sys(0xBC)[0], 39):
        press(button)
    assert rd_sys(0xBC)[0] == 39
    press('a', gap=60)
    wait_for(lambda: rd_sys(0x047B)[0] == 7, 240, 10, 'password EXIT return')
    check_view(data, assets, out, 'main', 0, 'password-return')
    assert canonical_series() == baseline
    print('PASS: controller password EXIT and Analysis return restore the exact menu', flush=True)


if __name__ == '__main__':
    main()
