# Bracket entry debug (unresolved)

Goal: boot a test ROM straight into the 32-team bracket screen by calling
`$9BF0` (bank 5) from a fixed-bank trampoline.

## Symptom

jsnes aborts with `this.nes.stop is not a function` (its invalid-opcode path).
At the abort:

```
PC = $9BF2
SP = $01FD
mem[$9BF0..] = 33 59 2A 42 61 20 77 2F
```

Those are not the bracket routine bytes (`A4 C1 A9 18 ...`). They match **bank
0**. So the CPU is executing data because bank 5 is not mapped at `$8000`.

## Attempts

1. `LDA #5 / JSR $C14E` — same crash, bank 0 mapped.
2. `LDA #5 / JSR $C150` — same crash, bank 0 mapped.
3. `LDA #$80 / STA $FFFF` reset before the bank write — same crash.

`$C150` disassembles as five `STA $FFFF` writes (correct MMC1 serial form), so
the helper itself looks right. The selector's trampoline used `$C14E` + `JMP
$8000` successfully, so the difference is likely in the surrounding state:
reset-vector trampoline, PPU init, or a later bank switch before the call.

## Next

- Set a write watch on `$FFFF` in the debugger and log every MMC1 write and PC.
- Compare with the working selector trampoline at `$FF00`.
- Step from `$FF00` to the `JSR $9BF0` and dump the mapped bank immediately
  before the call.
- If the mapper is right at the call, check whether `$9C42`/`$9B5F` switches
  banks before the crash PC.


## Root cause (resolved)

Two separate mistakes:

1. `$C102` was called with `A=0`, which sets **PRG mode 0** (32 KiB). The later
   bank-5 write therefore did not map bank 5 at `$8000`. Control must be
   `$0C` (PRG mode 3, fixed last bank). With `$0C`, the invalid-opcode crash
   disappears.
2. `$9BF0` is **not a routine entry** — `$9BEF` is `JSR $C1A4` and `$9BF0` is
   its operand. The real screen handler is `$9BC1`. Calling `$9BC1` reaches the
   setup path; `$9BF0` skips it.

The screen is still blank in the standalone test because the scene handler
expects full scene state/NMI timing; entry wiring remains open.


## Confirmed by multi-model review (Opus 5.5)

Live jsnes 1.2.1 reproduction found the decisive cause: **the mapper's MMC1
shift counter is `undefined` after `loadROM`**. `nes.js` calls `reset()` before
`mmap` exists, so `Mappers[1].reset` never runs and every serial write does
`undefined++` → `NaN`; `NaN === 5` never latches. A bit-7 write initializes it.

Working probe (tested):

```
FF00 78        SEI
FF01 D8        CLD
FF02 A2 FF     LDX #$FF
FF04 9A        TXS
FF05 8E FF 9F  STX $9FFF     ; MMC1 reset
...
FF1A A9 1E     LDA #$1E
FF1C 20 02 C1  JSR $C102     ; control: 8 KiB CHR mode, PRG mode 3
FF1F A9 05     LDA #$05
FF21 20 4E C1  JSR $C14E     ; also sets $27 shadow
FF24 AD F0 9B  LDA $9BF0
FF27 8D FF 07  STA $07FF
FF2A 4C 2A FF  JMP $FF2A
```

Result in-harness: `$07FF = $A4`, `$27 = 5`, `$9BF0 = A4 C1 A9 18` — bank 5 is
mapped. Notes:

- Use `$C14E`, not `$C150`, so the `$27` bank shadow is updated.
- `$0C` selects 8 KiB CHR mode; this game uses `$1E`.
- The last ad-hoc test ROM had RESET still pointing at stock `$CBD5`, so the
  `$FF00` trampoline never ran. Always verify the reset vector after building.
- `JSR $9BF0` maps correctly but returns into a hang at `$C26F`; real entry
  should hook after stock reset/NMI init, like the selector at `$CBE6`.

## Review disagreement (resolved)

- **Opus 5.5** reproduced the crash live and proved the jsnes 1.2.1 MMC1
  counter bug; its probe (`STX $9FFF`, control `$1E`, `$C14E`) produced
  `$07FF=$A4`, `$27=5`, bank-5 bytes `A4 C1 A9 18`.
- **Fable 5.1** reviewed an older build and correctly noted that RESET still
  pointed at stock `$CBD5`, so the trampoline was not on the real boot path.
  It also claimed `$9BC1` is mid-routine; disassembly shows `$9BC1` is the
  screen-handler entry (`LDA $0746 / CMP #$0F / ...`), while `$9BF0` is the
  mid-handler address. The live probe is authoritative here.
- **GPT-6.1-Sol** found four independent P1s in the builder: display operand,
  destination operand, fixed-bank hardcode, and the `$6800` cache collision.
  All four are fixed in `tools/build_32bracket.py` (commit `34af69a`).

No reviewer edits were applied blindly; the confirmed Opus probe and Sol's
disassembly-backed fixes were used.
