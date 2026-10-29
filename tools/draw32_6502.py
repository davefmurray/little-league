"""Assembled draw32 routines for tools/build_draw32.py.

DRAW_SEGMENT and CODEC_SEGMENT are immutable (CPU address, bytes) pairs and
DRAW_LABELS and CODEC_LABELS their entry points. This module reads no ROM and
installs no hooks; the builder owns the call operands and every byte guard.

Bank 11 from $8220, padding after the stock $8200 seeder:
  new_series_draw  replaces the seeder call at $86EF in the new-series entry.
                   Captures a draw seed from $33 and $07F3 into WRAM
                   $7760/$7761 (tools/draw32.py capture), then draws.
  restore_draw     replaces the seeder call at $8606 in the password restore.
                   Copies the decoded seed from $0633/$0634 to $7760/$7761,
                   then draws.
  draw32           calls the stock seeder, then shuffles slots 1..31 of $7700
                   when the seed is nonzero (tools/draw32.py draw_order). It
                   writes only $7700-$771F, $00-$08 and the stack.

Bank 12 from $8200, padding after the v1 codec:
  v2_gate          replaces the decoder's version load at $8058, which runs
                   after the CRC matched. Version $08 sets the decoded seed
                   $0633/$0634 to 0. Version $10 moves its 14-bit seed there,
                   rejects seed 0, and clears the seed bits from bytes 1, 2
                   and 11. Both resume at $805F, so every v1 reserved-bit,
                   result and canonical check runs unchanged on both versions.
                   Any other version fails like v1.
  v2_fields        replaces the encoder's crc16 call operand at $8114. A
                   nonzero WRAM seed rewrites bytes 0, 1, 2 and 11 as v2;
                   either way it tail-calls crc16.
"""
from types import MappingProxyType

from build_bank11 import assemble
import draw32

SEED_LO, SEED_HI = 0x7760, 0x7761
DECODED_LO, DECODED_HI = 0x0633, 0x0634
FRAME_COUNTER, MENU_FRAME = 0x33, 0x07F3
SLOTS, SELECTED = 0x7700, 0x07C3
STOCK_SEEDER = 0x8200
DRAW_ORIGIN = 0x8220
CODEC_ORIGIN = 0x8200
GATE_RESUME = 0x805F
DEC_FAIL = 0x80A3
CRC16 = 0x8170
VERSION_BYTE, TEAM_BYTE, PLAYED_BYTE, SEED_BYTE = 0x0627, 0x0628, 0x0629, 0x0632

DRAW_ASM = (
    "new_series_draw:",
    f"LDA ${FRAME_COUNTER:02X}", "LSR A", "LSR A", f"STA ${SEED_HI:04X}",
    f"LDA ${FRAME_COUNTER:02X}", *["ASL A"] * 6,
    f"EOR ${MENU_FRAME:04X}", f"STA ${SEED_LO:04X}",
    f"ORA ${SEED_HI:04X}", "BNE draw32",
    f"INC ${SEED_LO:04X}",
    "JMP draw32",
    "restore_draw:",
    f"LDA ${DECODED_LO:04X}", f"STA ${SEED_LO:04X}", f"LDA ${DECODED_HI:04X}", f"STA ${SEED_HI:04X}",
    "draw32:",
    f"JSR ${STOCK_SEEDER:04X}",
    f"LDA ${SEED_LO:04X}", f"ORA ${SEED_HI:04X}", "BEQ dr_done",
    f"LDA ${SEED_LO:04X}", f"EOR #${draw32.STATE_XOR & 0xFF:02X}", "STA $00",
    f"LDA ${SEED_HI:04X}", f"EOR #${draw32.STATE_XOR >> 8:02X}", "STA $01",
    *["JSR dr_rng"] * draw32.WARMUP,
    f"LDX #${draw32.TEAMS - 1:02X}",
    "dr_slot:",
    "JSR dr_rng",
    # $05 = (state * slot) >> 16: shift-and-add of the 16-bit state into $03-$05.
    "STX $02",
    "LDA #$00", "STA $03", "STA $04", "STA $05", "STA $08",
    "LDA $00", "STA $06", "LDA $01", "STA $07",
    "dr_mul:",
    "LSR $02", "BCC dr_shift",
    "CLC",
    "LDA $03", "ADC $06", "STA $03",
    "LDA $04", "ADC $07", "STA $04",
    "LDA $05", "ADC $08", "STA $05",
    "dr_shift:",
    "ASL $06", "ROL $07", "ROL $08",
    "LDA $02", "BNE dr_mul",
    "LDY $05",
    f"LDA ${SLOTS:04X},X", "PHA",
    f"LDA ${SLOTS + 1:04X},Y", f"STA ${SLOTS:04X},X",
    "PLA", f"STA ${SLOTS + 1:04X},Y",
    "DEX", "CPX #$01", "BNE dr_slot",
    "dr_done:",
    "RTS",
    # xorshift16 (7,9,8) on $00 (low) and $01 (high).
    "dr_rng:",
    "LDA $01", "LSR A", "LDA $00", "ROR A", "EOR $01", "STA $01",
    "ROR A", "EOR $00", "STA $00", "EOR $01", "STA $01",
    "RTS",
)

CODEC_ASM = (
    "v2_gate:",
    f"LDA ${VERSION_BYTE:04X}", "CMP #$08", "BNE vg_v2",
    "LDA #$00", f"STA ${DECODED_LO:04X}", f"STA ${DECODED_HI:04X}",
    f"JMP ${GATE_RESUME:04X}",
    "vg_v2:",
    "CMP #$10", "BNE vg_fail",
    f"LDA ${SEED_BYTE:04X}", f"STA ${DECODED_LO:04X}",
    f"LDA ${PLAYED_BYTE:04X}", "AND #$E0", "LSR A", "LSR A", f"STA ${DECODED_HI:04X}",
    f"LDA ${TEAM_BYTE:04X}", *["LSR A"] * 5, f"ORA ${DECODED_HI:04X}", f"STA ${DECODED_HI:04X}",
    f"ORA ${DECODED_LO:04X}", "BEQ vg_fail",
    f"LDA ${TEAM_BYTE:04X}", "AND #$1F", f"STA ${TEAM_BYTE:04X}",
    f"LDA ${PLAYED_BYTE:04X}", "AND #$1F", f"STA ${PLAYED_BYTE:04X}",
    "LDA #$00", f"STA ${SEED_BYTE:04X}",
    f"JMP ${GATE_RESUME:04X}",
    "vg_fail:",
    f"JMP ${DEC_FAIL:04X}",
    "v2_fields:",
    f"LDA ${SEED_LO:04X}", f"ORA ${SEED_HI:04X}", "BEQ vf_done",
    "LDA #$10", f"STA ${VERSION_BYTE:04X}",
    f"LDA ${SEED_LO:04X}", f"STA ${SEED_BYTE:04X}",
    f"LDA ${SEED_HI:04X}", "AND #$07", *["ASL A"] * 5, f"ORA ${TEAM_BYTE:04X}", f"STA ${TEAM_BYTE:04X}",
    f"LDA ${SEED_HI:04X}", "AND #$38", "ASL A", "ASL A", f"ORA ${PLAYED_BYTE:04X}", f"STA ${PLAYED_BYTE:04X}",
    "vf_done:",
    f"JMP ${CRC16:04X}",
)

_draw_code, _draw_labels = assemble(DRAW_ASM, DRAW_ORIGIN)
_codec_code, _codec_labels = assemble(CODEC_ASM, CODEC_ORIGIN)
DRAW_SEGMENT = (DRAW_ORIGIN, _draw_code)
CODEC_SEGMENT = (CODEC_ORIGIN, _codec_code)
DRAW_LABELS = MappingProxyType(_draw_labels)
CODEC_LABELS = MappingProxyType(_codec_labels)
