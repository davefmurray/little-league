#!/usr/bin/env python3
"""Drive the shared picker and title through real controller input in romdev.

Screenshots and APU activity complement the CPU tests; they do not model hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path

import romdev
from soak_bracket import leave_lineup, rd_cart, rd_sys, step, wait_for


def press(button, port=0, frames=3, gap=8):
    romdev.call('input', {'op': 'press', 'button': button, 'port': port, 'frames': frames})
    step(gap)


def picker():
    return rd_sys(0x27)[0] == 10 and rd_sys(0x2C, 2) == b'\x01\x01'


def wait_picker():
    wait_for(picker, 600, 10, 'shared picker')
    step(15)


def select(team, port=0):
    row, col = rd_sys(0x07C0, 2)
    for _ in range(((team >> 3) - row) % 4):
        press('down', port)
    for _ in range(abs((team & 7) - col)):
        press('right' if (team & 7) > col else 'left', port)
    assert rd_sys(0x07C0, 2) == bytes((team >> 3, team & 7))


def canonical_series():
    return {
        'heap': rd_cart(0x7700, 63).hex(),
        'draw_seed': rd_cart(0x7760, 2).hex(),
        'markers': rd_sys(0x07ED).hex() + rd_sys(0x07EF, 2).hex(),
        'played': rd_sys(0x07FC).hex(),
        'mask': (rd_sys(0x074B, 2) + rd_sys(0x07F1, 2)).hex(),
    }


def boot_mode(rom, mode, password=None):
    if password:
        from probe_password_ui import open_entry, type_password
        open_entry(rom, 'continue')
        type_password(rom.read_bytes(), password)
        press('a', frames=10, gap=60)
        assert rd_sys(0x27)[0] == 11 and rd_sys(0x07FC)[0] < 31
        restored = canonical_series()
        press('a', gap=30)
        assert rd_sys(0x047B, 2) == bytes((0x13, 8))
        press('a')
        wait_for(lambda: rd_sys(0x047B, 2) == bytes((0x13, 3)), 240, 10, 'restored matchup')
        step(20)
        press('b', gap=60)
        assert rd_sys(0x047B)[0] == 7
        assert canonical_series() == restored
        print('password restored through keyboard; matchup B preserved series', flush=True)
    else:
        romdev.call('loadMedia', {'platform': 'nes', 'path': str(rom.resolve())})
        step(120)
        press('start', gap=60)
    for _ in range(mode):
        press('down', gap=20)
    press('a', gap=60)


def shot(out, name):
    romdev.call('frame', {'op': 'screenshot', 'path': str(out / f'{name}.png')})


def analysis(rom, out, password=None):
    boot_mode(rom, 2, password)
    wait_picker()
    baseline = canonical_series()
    for team in range(32):
        select(team)
        assert rd_sys(0x0401)[0] == 6
        press('a', gap=120)
        assert rd_sys(0x047B)[0] == 0x15, f'team {team}: analysis did not open'
        assert rd_sys(0x04EF)[0] == team
        shot(out, f'analysis-{team:02d}')
        assert canonical_series() == baseline, f'team {team}: series changed in analysis'
        press('b', gap=30)
        wait_picker()
        assert rd_sys(0x07C0, 2) == bytes((team >> 3, team & 7)), f'team {team}: cursor lost'
        assert canonical_series() == baseline
        print(f'analysis {team:02X}: selected, details, B return, cursor and series preserved', flush=True)
    press('b', gap=60)
    assert rd_sys(0x047B)[0] == 7 and rd_sys(0x2C, 2) == b'\0\0'
    print('analysis B returns to mode menu with NMI guards clear', flush=True)


def exhibition(rom, out, submode, teams, password, complete, attract):
    boot_mode(rom, 1, password)
    for _ in range(submode):
        press('down', gap=20)
    press('a', gap=60)
    wait_picker()
    baseline = canonical_series()
    select(teams[0])
    press('a', gap=30)
    assert rd_sys(0x07C4)[0] == 1
    port = int(submode == 1)
    if port:
        cursor = rd_sys(0x07C0, 2)
        for button in ('right', 'down', 'a'):
            press(button)
        assert picker() and rd_sys(0x07C4)[0] == 1 and rd_sys(0x07C0, 2) == cursor
        print('2P side 2 ignores controller 1 movement and confirmation', flush=True)
    select(teams[0], port)
    press('a', port)
    assert picker() and rd_sys(0x07C4)[0] == 1
    press('b', port)
    assert picker() and rd_sys(0x07C4)[0] == 0
    select(teams[0])
    press('a', gap=30)
    select(teams[1], port)
    shot(out, f'exhibition-{submode}-second-pick')
    press('a', port, gap=60)
    wait_for(lambda: rd_sys(0x047B)[0] == 0x11, 600, 10, 'exhibition pre-game')
    assert rd_sys(0x04EF, 2) == bytes(teams)
    assert rd_sys(0x04EB, 2) == (b'\x00\x80', b'\x00\x00', b'\x80\x80')[submode]
    assert rd_sys(0x04E2)[0] == 0
    assert canonical_series() == baseline
    for team, address in zip(teams, (0x7800, 0x7A00)):
        if team >= 16:
            assert int.from_bytes(rd_cart(0x7F00 + 2 * team, 2), 'little') == address
    shot(out, f'exhibition-{submode}-pre-game')
    print(f'exhibition submode={submode} teams={teams}: ports, duplicate refusal, B back, cache and series pass', flush=True)
    if not complete:
        return
    if submode == 1:
        print('2P completion driver pitches from the fielding port and leaves the batting port idle', flush=True)
    started = False
    last_half = None
    for _ in range(16000):
        live = rd_sys(0x047B, 0x80)
        scene = live[0]
        if scene in (3, 5):
            started = True
            half = live[0x048A - 0x047B]
            if half != last_half:
                print(f'field half={half} teams={live[0x74:0x76].hex()} scores={live[0x10:0x12].hex()}', flush=True)
                last_half = half
        if started and live[0x04D0 - 0x047B]:
            break
        if scene == 0x0F:
            if submode == 1:
                for _ in range(6):
                    if rd_sys(0x047B)[0] != 0x0F:
                        break
                    press('b', 1, frames=2, gap=15)
                if rd_sys(0x047B)[0] == 0x0F:
                    press('a', 1, frames=2, gap=30)
            if rd_sys(0x047B)[0] == 0x0F:
                leave_lineup()
        elif scene in (0x0B, 0x11):
            press('a')
        elif scene in (3, 5) and submode < 2:
            controllers = ((live[0x04EE - 0x047B] ^ int(bool(live[0x04E9 - 0x047B])),)
                           if submode == 1 else (0,))
            for controller in controllers:
                press('a', controller, gap=1)
        step(500 if submode == 2 else 100)
    else:
        raise AssertionError('exhibition did not finish within controller-script budget')
    assert rd_sys(0x04E2)[0] == 0 and canonical_series() == baseline
    print(f'exhibition completed game-over={rd_sys(0x04D0).hex()} scores={rd_sys(0x048B, 2).hex()}', flush=True)
    for _ in range(80):
        press('a', gap=60)
        if rd_sys(0x047B)[0] == 1:
            break
    assert rd_sys(0x047B)[0] == 1 and canonical_series() == baseline
    shot(out, f'exhibition-{submode}-return-title')
    print('exhibition title return preserves heap, draw seed, progress, markers and ownership', flush=True)
    if attract:
        wait_for(lambda: rd_sys(0xA7)[0] == 1 and rd_sys(0x047B)[0] != 1,
                 3000, 10, 'attract demo with active series')
        assert canonical_series() == baseline
        wait_for(lambda: rd_sys(0x047B)[0] == 1, 240000, 100, 'demo return to title')
        assert canonical_series() == baseline
        print('attract and demo round trip preserves the suspended series', flush=True)
    if password:
        press('start', gap=60)
        press('a', gap=30)
        press('a', gap=60)
        assert rd_sys(0x27)[0] == 11 and canonical_series() == baseline
        played = rd_sys(0x07FC)[0]
        pair = rd_cart(0x7700 + 2 * played, 2)
        press('a', gap=30)
        assert rd_sys(0x047B, 2) == bytes((0x13, 8)) and rd_sys(0x07FA, 2) == pair
        display = (password[:6] + ' ' + password[6:12]).encode() + b'\xff' + (
            password[12:18] + ' ' + password[18:]).encode() + b'\xff'
        assert rd_sys(0x0643, 26) == display
        print(f'CONTINUE launches preserved pair {pair.hex()} and exports the exact restored password', flush=True)


def title(rom, out):
    data = rom.read_bytes()
    chr_start = 16 + 16 * 0x4000
    expected = data[chr_start + 0x17 * 4096:chr_start + 0x18 * 4096]
    romdev.call('loadMedia', {'platform': 'nes', 'path': str(rom.resolve())})
    step(120)
    assert rd_sys(0x047B)[0] == 1 and rd_sys(0x0401)[0] == 4
    actual = bytes.fromhex(romdev.call('memory', {'op': 'read', 'region': 'nes_chr',
                          'offset': 4096, 'length': 4096, 'inline': True})['hex'])
    assert actual == expected
    shot(out, 'title')
    audio = romdev.call('audioDebug', {'op': 'inspect', 'chip': 'nes', 'frames': 120, 'sampleEvery': 1})
    assert audio['transitions'] > 20
    (out / 'title-audio.json').write_text(json.dumps(audio, indent=2) + '\n')
    print(f'title: CHR17, song04, {audio["transitions"]} APU transitions in 120 frames', flush=True)
    wait_for(lambda: rd_sys(0xBA)[0] == 4, 2400, 10, 'attract title redraw')
    step(30)
    assert rd_sys(0x047B)[0] == 1
    shot(out, 'title-attract-redraw')
    actual = bytes.fromhex(romdev.call('memory', {'op': 'read', 'region': 'nes_chr',
                          'offset': 4096, 'length': 4096, 'inline': True})['hex'])
    assert actual == expected
    wait_for(lambda: rd_sys(0xA7)[0] == 1, 1200, 10, 'attract demo')
    shot(out, 'title-demo')
    print('attract redraw uses CHR17 and enters demo', flush=True)
    for frames in (120, 400, 1000, 1550):
        for port in (0, 1):
            romdev.call('loadMedia', {'platform': 'nes', 'path': str(rom.resolve())})
            step(frames)
            press('start', port, gap=60)
            assert rd_sys(0x047B)[0] == 7, (frames, port, rd_sys(0x047B).hex())
            assert rd_sys(0x0401)[0] == 6
            print(f'START port {port + 1} after {frames} frames: mode menu and song06', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--tour', choices=('title', 'analysis', 'exhibition'), required=True)
    ap.add_argument('--password', help='restore an unfinished series through the keyboard before changing modes')
    ap.add_argument('--submode', choices=('1p', '2p', 'watch'), default='watch')
    ap.add_argument('--teams', type=int, nargs=2, default=(31, 30))
    ap.add_argument('--complete', action='store_true', help='play Exhibition to game over using controller input')
    ap.add_argument('--attract', action='store_true', help='after Exhibition, idle through the attract/demo round trip')
    ap.add_argument('--session', default='frontend32-ui')
    args = ap.parse_args()
    if any(team not in range(32) for team in args.teams) or args.teams[0] == args.teams[1]:
        ap.error('--teams requires two distinct IDs in 0..31')
    if args.password and args.tour == 'title':
        ap.error('--password is for analysis or exhibition')
    if args.attract and (args.tour != 'exhibition' or not args.complete):
        ap.error('--attract requires --tour exhibition --complete')
    romdev.SESSION = args.session
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(args.rom.read_bytes()).hexdigest()
    print(f'ROM SHA256 {digest}', flush=True)
    print(f'controller-only tour={args.tour} submode={args.submode} complete={args.complete} attract={args.attract} password={args.password}', flush=True)
    if args.tour == 'exhibition':
        exhibition(args.rom, out, ('1p', '2p', 'watch').index(args.submode), args.teams, args.password, args.complete, args.attract)
    elif args.tour == 'analysis':
        analysis(args.rom, out, args.password)
    else:
        title(args.rom, out)
    (out / f'{args.tour}-run.json').write_text(json.dumps({'rom_sha256': digest, 'tour': args.tour,
        'input': 'controller-only', 'status': 'passed'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
