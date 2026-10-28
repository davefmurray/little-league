"""Assembled format-v1 codec and restore segments for the ROM builder.

BANK12_SEGMENTS and BANK11_SEGMENTS are immutable (CPU address, bytes)
pairs. Assemble with the repository's build_bank11 assembler. This module
reads no ROM and installs no hooks.

$8000 decodes exactly 22 uppercase ASCII bytes at $0643..$0658. Carry is
clear on success, with the unwhitened payload at $0627..$0634, and set on
failure. Only $00..$04, payload, stack and A/X/Y/P are clobbered. A failed
decode never changes the live bracket or ownership.

$8003 encodes a valid live heap, $07FC and the four ownership bytes into
$0643..$065C, including stock spaces and FF terminators. It uses the same
scratch bytes and destroys the payload. The caller must supply seed and
played in 0..31 and a winner from the actual pair for each played match.

$8600 restores a successfully decoded payload. It calls the real bank-11
$8200 seeder and fixed-bank $C199 OAM clear, then jumps to bank-11 $8000.
The caller must map bank 11 and disable NMI before entry. The bracket
entry must preserve the seeded heap. No fixed stubs or UI hooks live here.
"""
from types import MappingProxyType

from build_bank11 import assemble
from password32 import ALPHABET, MASK, VALUE

DECODE_ENTRY = 0x8000
ENCODE_ENTRY = 0x8003
RESTORE_ENTRY = 0x8600
PAYLOAD = 0x0627
PASSWORD = 0x0643
SLOTS = 0x7700
WINNERS = 0x7720
PLAYED = 0x07FC
CPU_MASK_ADDRESSES = (0x074B, 0x074C, 0x07F1, 0x07F2)
DECODE_TABLE_ADDRESS = 0x8F00
ALPHABET_ADDRESS = 0x8F30
MASK_ADDRESS = 0x8F50
BITS_ADDRESS = 0x8F60
DISPLAY_POSITIONS_ADDRESS = 0x8F68
RESTORE_BITS_ADDRESS = 0x8678

DECODE_ASM = (
    "pw32_decode:", "LDX #$0D", "LDA #$00",
    "dec_clr:", "STA $0627,X", "DEX", "BPL dec_clr",
    "LDA #$00", "STA $03", "BEQ dec_sym",
    "dec_bad:", "SEC", "RTS",
    "dec_sym:", "LDX $03", "LDY $0643,X",
    "CPY #$30", "BCC dec_bad", "CPY #$5B", "BCS dec_bad",
    "LDA $8ED0,Y", "BMI dec_bad",
    "ASL A", "ASL A", "ASL A", "STA $02", "LDA #$05", "STA $04",
    "dec_bit:", "ASL $02", "JSR shl_in", "DEC $04", "BNE dec_bit",
    "INC $03", "LDA $03", "CMP #$16", "BNE dec_sym",
    "JSR whiten", "JSR crc16",
    "LDA $00", "CMP $0633", "BNE dec_fail",
    "LDA $01", "CMP $0634", "BNE dec_fail",
    "LDA $0627", "CMP #$08", "BNE dec_fail",
    "LDA $0628", "ORA $0629", "AND #$E0", "BNE dec_fail",
    "LDA $062D", "BMI dec_fail", "LDA $0632", "BNE dec_fail",
    "LDA $062A", "STA $00", "LDA $062B", "STA $01",
    "LDA $062C", "STA $02", "LDA $062D", "STA $03",
    "LDX $0629", "BEQ dec_zero",
    "dec_shift:", "LSR $03", "ROR $02", "ROR $01", "ROR $00", "DEX", "BNE dec_shift",
    "dec_zero:", "LDA $00", "ORA $01", "ORA $02", "ORA $03", "BNE dec_fail",
    "CLC", "RTS",
    "dec_fail:", "SEC", "RTS",
    "shl_in:", "ROL $0634", "LDX #$0C",
    "shi_loop:", "ROL $0627,X", "DEX", "BPL shi_loop", "RTS",
)

ENCODE_ASM = (
    "pw32_encode:", "LDX #$0D", "LDA #$00",
    "enc_clr:", "STA $0627,X", "DEX", "BPL enc_clr",
    "LDA #$08", "STA $0627",
    "LDA $7700", "AND #$1F", "STA $0628",
    "LDA $07FC", "AND #$1F", "STA $0629", "LDX #$00",
    "enc_res:", "CPX $0629", "BCS enc_mask",
    "TXA", "ASL A", "TAY", "LDA $7720,X", "CMP $7700,Y", "BEQ enc_next",
    "TXA", "AND #$07", "TAY", "LDA $8F60,Y", "STA $02",
    "TXA", "LSR A", "LSR A", "LSR A", "TAY",
    "LDA $062A,Y", "ORA $02", "STA $062A,Y",
    "enc_next:", "INX", "BNE enc_res",
    "enc_mask:", "LDA $074B", "STA $062E", "LDA $074C", "STA $062F",
    "LDA $07F1", "STA $0630", "LDA $07F2", "STA $0631",
    "JSR crc16", "LDA $00", "STA $0633", "LDA $01", "STA $0634",
    "JSR whiten", "JSR shl1", "JSR shl1", "LDA #$00", "STA $03",
    "enc_sym:", "LDA #$00", "STA $02", "LDA #$05", "STA $04",
    "enc_bit:", "JSR shl1", "ROL $02", "DEC $04", "BNE enc_bit",
    "LDY $02", "LDA $8F30,Y", "LDY $03", "LDX $8F68,Y", "STA $0643,X",
    "INC $03", "LDA $03", "CMP #$16", "BNE enc_sym",
    "LDA #$20", "STA $0649", "STA $0657",
    "LDA #$FF", "STA $0650", "STA $065C", "RTS",
    "shl1:", "ASL $0634", "LDX #$0C",
    "shl_loop:", "ROL $0627,X", "DEX", "BPL shl_loop", "RTS",
)

CRC_ASM = (
    "crc16:", "LDA #$FF", "STA $00", "STA $01", "LDX #$00",
    "crc_byte:", "LDA $0627,X", "EOR $00", "STA $00", "LDY #$08",
    "crc_bit:", "ASL $01", "ROL $00", "BCC crc_next",
    "LDA $00", "EOR #$10", "STA $00", "LDA $01", "EOR #$21", "STA $01",
    "crc_next:", "DEY", "BNE crc_bit", "INX", "CPX #$0C", "BNE crc_byte", "RTS",
)

WHITEN_ASM = (
    "whiten:", "LDX #$0D",
    "wh_loop:", "LDA $0627,X", "EOR $8F50,X", "STA $0627,X", "DEX", "BPL wh_loop", "RTS",
)

RESTORE_ASM = (
    "br32_restore:", "LDA $0628", "STA $07C3", "JSR $8200",
    "LDA #$FF", "LDX #$1E",
    "rs_clr:", "STA $7720,X", "DEX", "BPL rs_clr",
    "LDA $0629", "STA $07FC", "LDX #$00",
    "rs_loop:", "CPX $07FC", "BCS rs_done",
    "TXA", "AND #$07", "TAY", "LDA $8678,Y", "STA $02",
    "TXA", "LSR A", "LSR A", "LSR A", "TAY", "LDA $062A,Y", "AND $02",
    "PHP", "TXA", "ASL A", "TAY", "PLP", "BEQ rs_a", "INY",
    "rs_a:", "LDA $7700,Y", "STA $7720,X", "INX", "BNE rs_loop",
    "rs_done:", "LDA $062E", "STA $074B", "LDA $062F", "STA $074C",
    "LDA $0630", "STA $07F1", "LDA $0631", "STA $07F2",
    "LDA #$01", "STA $07ED", "LDA #$32", "STA $07EF",
    "LDA #$00", "STA $07F0", "JSR $C199", "JMP $8000",
)

CODEC_ASM = ("JMP pw32_decode", "JMP pw32_encode") + DECODE_ASM + ENCODE_ASM + CRC_ASM + WHITEN_ASM
BANK12_CODE, _codec_labels = assemble(CODEC_ASM, DECODE_ENTRY)
BANK11_RESTORE_CODE, _restore_labels = assemble(RESTORE_ASM, RESTORE_ENTRY)
BANK12_LABELS = MappingProxyType(_codec_labels)
BANK11_LABELS = MappingProxyType(_restore_labels)
DECODE_TABLE = bytes(VALUE.get(chr(char), 0xFF) for char in range(0x30, 0x5B))
BITS_TABLE = bytes(1 << bit for bit in range(8))
DISPLAY_POSITIONS = bytes((0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12,
                           14, 15, 16, 17, 18, 19, 21, 22, 23, 24))
BANK12_SEGMENTS = (
    (DECODE_ENTRY, BANK12_CODE),
    (DECODE_TABLE_ADDRESS, DECODE_TABLE),
    (ALPHABET_ADDRESS, ALPHABET.encode("ascii")),
    (MASK_ADDRESS, MASK),
    (BITS_ADDRESS, BITS_TABLE),
    (DISPLAY_POSITIONS_ADDRESS, DISPLAY_POSITIONS),
)
BANK11_SEGMENTS = (
    (RESTORE_ENTRY, BANK11_RESTORE_CODE),
    (RESTORE_BITS_ADDRESS, BITS_TABLE),
)

if len(BANK12_CODE) != 427 or len(BANK11_RESTORE_CODE) != 113:
    raise ValueError("password codec exceeds its designed segment sizes")
