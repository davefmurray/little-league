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
