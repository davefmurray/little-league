#!/usr/bin/env python3
"""Verify lineup automation respects controller ownership and stops on scene exit."""
from unittest.mock import patch

import soak_bracket as soak


def main():
    for owner in (0, 1):
        state = {'scene': 0x0F, 'backs': 0}
        inputs = []

        def call(name, payload):
            if name == 'input':
                inputs.append(payload)
                assert state['scene'] == 0x0F, 'input leaked into the following scene'
                if payload['port'] == owner:
                    if payload['button'] == 'b':
                        state['backs'] += 1
                    elif payload['button'] == 'a' and state['backs'] >= 6:
                        state['scene'] = 3
            elif name == 'frame':
                assert payload['op'] == 'step'
            else:
                raise AssertionError(name)

        with patch.object(soak, 'rd_sys', side_effect=lambda _: bytes((state['scene'],))), \
                patch.object(soak.romdev, 'call', side_effect=call):
            soak.leave_lineup()
        assert state['scene'] == 3, f'controller {owner + 1} editor not left'
        assert len(inputs) == 7 * (owner + 1)
        assert inputs[-1]['button'] == 'a' and inputs[-1]['port'] == owner
    with patch.object(soak, 'rd_sys', return_value=b'\x03'), \
            patch.object(soak.romdev, 'call', side_effect=AssertionError('input outside lineup')):
        soak.leave_lineup()
    print('PASS: controller 1 and 2 lineup confirmation; no input after scene exit')


if __name__ == '__main__':
    main()
