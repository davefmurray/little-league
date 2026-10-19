#!/usr/bin/env python3
"""Add cursor + A handoff to the static bracket screen.

    python3 tools/build_bracket_input.py build/bracket-screen.nes -o build/bracket-input.nes
"""
import argparse

from build_bank11 import assemble

HEADER = 16
PRG = 0x4000
ENTRY = 0x8100

ASM = [
    "start:",
    "LDA #$00",
    "STA $07C7",
    "STA $07C8",
    "JMP loop",
    "read_pad:",
    "LDA #$01",
    "STA $4016",
    "LDA #$00",
    "STA $4016",
    "LDX #$08",
    "LDA #$00",
    "STA $07C6",
    "rd:",
    "LDA $4016",
    "LSR A",
    "ROL $07C6",
    "DEX",
    "BNE rd",
    "RTS",
    "loop:",
    "JSR read_pad",
    "LDA $07C6",
    "STA $07C9",
    "LDA $07C8",
    "EOR #$FF",
    "AND $07C9",
    "STA $07C9",
    "LDA $07C9",
    "AND #$08",
    "BEQ chk_down",
    "LDA $07C7",
    "BEQ chk_down",
    "DEC $07C7",
    "chk_down:",
    "LDA $07C9",
    "AND #$04",
    "BEQ chk_a",
    "LDA $07C7",
    "CMP #$1F",
    "BCS chk_a",
    "INC $07C7",
    "chk_a:",
    "LDA $07C9",
    "AND #$80",
    "BEQ marker",
    "LDA $07C7",
    "STA $04EF",
    "EOR #$01",
    "STA $04F0",
    "LDA #$B0",
    "STA $07FF",
    "LDA #$80",
    "STA $04EB",
    "STA $04EC",
    "LDA $C1",
    "ORA #$02",
    "STA $C1",
    "LDA #$06",
    "JSR $C14E",
    "LDX #$00",
    "JMP $AC3A",
    "marker:",
    "LDA $07C6",
    "STA $07C8",
    "JSR draw_marker",
    "JMP loop",
    "draw_marker:",
    "LDA $07C7",
    "AND #$07",
    "ASL A",
    "ASL A",
    "ASL A",
    "ASL A",
    "CLC",
    "ADC #$28",
    "STA $0200",
    "LDA #$41",
    "STA $0201",
    "LDA #$00",
    "STA $0202",
    "LDA $07C7",
    "AND #$18",
    "ASL A",
    "ASL A",
    "ASL A",
    "CLC",
    "ADC #$08",
    "STA $0203",
    "LDA #$00",
    "STA $2003",
    "LDA #$02",
    "STA $4014",
    "RTS",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/bracket-input.nes")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    code, labels = assemble(ASM, ENTRY)
    off = HEADER + 11 * PRG + (ENTRY - 0x8000)
    rom[off:off + len(code)] = code
    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}: entry ${ENTRY:04X}, {len(code)} bytes, "
          f"loop ${labels['loop']:04X}")


if __name__ == "__main__":
    main()
