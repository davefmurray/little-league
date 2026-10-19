#!/usr/bin/env python3
"""Wire the bank-11 bracket into the stock scene-18 handler (END → launch).

    python3 tools/build_bracket_input.py build/bracket-screen.nes \
        --return-on-a -o build/bracket-launch-input.nes
    python3 tools/build_launch_bridge.py build/bracket-launch-input.nes \
        -o build/launch.nes

Design (v2, "call-based bridge"):

  Bank 5, scene-18 handler entry $98B9 is replaced by `JMP $FF20`.  The
  handler is entered by the stock dispatcher with the caller's frame already
  on the stack, so this is a clean tail-jump: no synthetic return address and
  no stack-pointer arithmetic.

  Fixed bank $FF20:

      LDA #$01 / STA $2C        NMI body short-circuit (stock's own guard)
      LDA #$01 / STA $2D        deferred-task guard; see root cause below
      LDA #$00 / STA $2000      NMI off while the bracket runs
      LDA #$0B / JSR $C14E      stock PRG-bank switch (+ $27 = 11)
      JSR $8000                 bracket: PPU setup, seed, input loop
                                (A sets $04EF/$04F0 and RTSes)
      LDA #$05 / JSR $C14E      back to bank 5 (+ $27 = 5)
      LDA #$00 / STA $2C, $2D   release the guards
      LDA $33 / STA $34         re-run the instructions the hook replaced
      JSR $98D5                 build the password buffer
      LDA #$80 / STA $2000      NMI back on, as stock had it
      JMP $98C0                 resume the scene-18 body

  $98C0..$98D4 then zeroes $0746/$BE, sets $047C=7, $07ED=1, bumps the scene
  to 19 (password screen) and RTSes to $CC14 with the stack exactly as stock
  left it.

ROOT CAUSE of every earlier crash (see docs/LAUNCH-DEBUG-LOG.md):

  Disabling the PPU NMI is not enough.  A late/pending NMI still fires once,
  and the stock NMI handler ($CD85) runs the deferred-task helper $CF74.
  $CF74 ends with `JSR $816C` — a **bank-relative call into the currently
  mapped PRG bank**.  With bank 11 mapped, $816C is the operand byte of
  `STA $04F0` in the bracket A handler, so the CPU runs into the middle of
  bank-11 code (v1 jams at $B005).  In a stock-flow build that restores bank 5
  first it runs into bank-5 data (v2 jammed at $AC88).  $2C=1 makes the NMI
  handler skip its body ($CD8F -> $CDE1); $2D=1 makes $CF74 return before the
  $8048/$816C bank-relative calls.  Both are the game's own critical-section
  guards ($CC19 and $C14E use them).

v1 (the crashing experiment) hooked $98B9 with `JSR $FF20`, saved the pushed
frame to $07F7-$07F9, ran the bracket from a `JMP $8000`, and synthesised an
RTS frame from the bracket.  That leaves S one byte low and returns into the
middle of the hook.  It never got that far because the NMI path above ran
first.
"""
import argparse

HEADER = 16
PRG = 0x4000

BANK5 = 5
BANK11 = 11
FIXED = 15

HOOK_ADDR = 0x98B9          # scene-18 handler (END / series init), bank 5
HOOK = bytes([0x4C, 0x20, 0xFF, 0xEA, 0xEA, 0xEA])   # JMP $FF20; NOP NOP NOP

TRAMPOLINE_ADDR = 0xFF20
# Assembled by hand so the tool has no assembler dependency; keep in sync with
# the listing in the docstring.
TRAMPOLINE = bytes([
    0xA9, 0x01,             # LDA #$01
    0x85, 0x2C,             # STA $2C            NMI body short-circuit
    0x85, 0x2D,             # STA $2D            deferred-task guard
    0xA9, 0x00,             # LDA #$00
    0x8D, 0x00, 0x20,       # STA $2000          NMI off while the bracket runs
    0xA9, BANK11,           # LDA #$0B
    0x20, 0x4E, 0xC1,       # JSR $C14E          bank 11 / $27=11
    0x20, 0x00, 0x80,       # JSR $8000          bracket; returns on A
    0xA9, BANK5,            # LDA #$05
    0x20, 0x4E, 0xC1,       # JSR $C14E          bank 5 / $27=5
    0xA9, 0x1E,             # LDA #$1E
    0x85, 0xAD,             # STA $AD            PPU mask shadow = $1E (matches
                            #                    the bracket's $2001 write)
    0xA9, 0x80,             # LDA #$80
    0x8D, 0x00, 0x20,       # STA $2000          NMI ON: $98D5 polls $047D,
                            #                    which only the NMI clears
    0xA5, 0x33,             # LDA $33
    0x85, 0x34,             # STA $34
    0xA9, 0x12,             # LDA #$12
    0x8D, 0x7B, 0x04,       # STA $047B          scene 18, so $98C0's INC -> 19
    0x20, 0xD5, 0x98,       # JSR $98D5          password buffer (needs NMI)
    0xA9, 0x00,             # LDA #$00
    0x85, 0x2C,             # STA $2C            release guard
    0x85, 0x2D,             # STA $2D            release guard
    0x4C, 0xC0, 0x98,       # JMP $98C0          resume scene-18 body
])


def bank_off(bank, addr, base):
    """File offset of a CPU address in a 16 KiB PRG bank.

    Switchable banks are mapped at $8000, the fixed bank at $C000.
    """
    return HEADER + bank * PRG + (addr - base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="output of build_bracket_input.py --return-on-a")
    ap.add_argument("-o", "--out", default="build/launch.nes")
    ap.add_argument("--stock-flow", action="store_true",
                    help="restore stock $CC06 (STA $2000) so the stock team "
                         "select runs and END reaches $98B9; without this the "
                         "bank-10 selector boots and the END hook is never hit")
    args = ap.parse_args()

    rom = bytearray(open(args.rom, "rb").read())
    banks = rom[4]
    if banks <= FIXED:
        raise SystemExit(f"{args.rom}: {banks} PRG banks, need 16")

    if args.stock_flow:
        # The selector/dispatcher build replaces STA $2000 at $CC06 with
        # JSR $FF00, which boots into the bank-10 selector and never reaches
        # scene 18.  Put the stock store back for launch testing.
        off = bank_off(FIXED, 0xCC06, 0xC000)
        rom[off:off + 3] = bytes([0x8D, 0x00, 0x20])
        print("fixed $CC06: JSR $FF00 -> STA $2000 (stock flow)")

    off = bank_off(BANK5, HOOK_ADDR, 0x8000)
    old = bytes(rom[off:off + len(HOOK)])
    rom[off:off + len(HOOK)] = HOOK
    print(f"bank5 ${HOOK_ADDR:04X}: {old.hex(' ')} -> {HOOK.hex(' ')}")

    off = bank_off(FIXED, TRAMPOLINE_ADDR, 0xC000)
    old = bytes(rom[off:off + len(TRAMPOLINE)])
    if old.count(0xFF) != len(old):
        raise SystemExit(
            f"fixed-bank ${TRAMPOLINE_ADDR:04X} is not free: {old.hex(' ')}")
    rom[off:off + len(TRAMPOLINE)] = TRAMPOLINE
    print(f"fixed ${TRAMPOLINE_ADDR:04X}: {len(TRAMPOLINE)} bytes trampoline")

    open(args.out, "wb").write(rom)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
