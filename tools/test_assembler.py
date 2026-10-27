#!/usr/bin/env python3
"""Execute assembled loops that combine zero-page addressing modes."""
from py65.devices.mpu6502 import MPU

from build_bank11 import assemble


def main():
    source = [
        'LDA #$00', 'STA $00', 'LDA #$60', 'STA $01',
        'LDA #$00', 'STA $02', 'LDA #$61', 'STA $03',
        'LDX #$00', 'LDY #$00',
        'copy:', 'LDA ($00,X)', 'STA $10,X', 'LDA $10,X', 'STA ($02),Y',
        'INC $00', 'INY', 'CPY #$04', 'BNE copy', 'JMP done',
        'LDA #$FF', 'done:', 'LDY #$01', 'LDX #$3C', 'STX $11,Y',
        'LDX #$00', 'LDX $11,Y', 'STX $6201',
        'LDA $11,Y', 'STA $20,Y', 'LDA $0012', 'STA $6202',
        'LDA #$5A', 'STA $6200', 'RTS',
    ]
    code, _ = assemble(source, 0x8000)
    cpu = MPU()
    cpu.memory[0x8000:0x8000 + len(code)] = code
    cpu.memory[0x6000:0x6004] = [0x17, 0x42, 0x93, 0xCE]
    cpu.stPushWord(0x01FF)
    cpu.pc = 0x8000
    for _ in range(100):
        if cpu.pc == 0x0200:
            break
        cpu.step()
    else:
        raise AssertionError(f'branch loop did not finish, PC=${cpu.pc:04X}')
    assert cpu.memory[0x6100:0x6104] == [0x17, 0x42, 0x93, 0xCE]
    assert cpu.memory[0x6200:0x6203] == [0x5A, 0x3C, 0x3C]
    assert cpu.memory[0x21] == 0x3C
    print('test_assembler: indexed and indirect zero-page loop plus forward jump OK')


if __name__ == '__main__':
    main()
