# Launch bridge — debug log (2025-10-19, session 2)

The launch bridge **works**. Bracket → A → password screen → matchup → speed
mode → cutscene → field, with a fully balanced stack.

This file records the probes and the four root causes, in order, so the next
person does not re-burn them.

Reference results:

```
after bracket A:   PC=$FF35 S=$FD $27=$0B   (trampoline, bank 11 still mapped)
after bank 5:      PC=$FF41 S=$FD $27=$05
after $98D5:       PC=$98C0 S=$FD $27=$05
stock body RTS:    PC=$CC14 S=$FF $27=$05
password screen:   $047B=$13 $047C=$08      screenshot: PASS WORD / C9UYD7…
matchup:           JAPAN vs CANADA, 1ST ROUND, COM/COM
speed mode:        SPEED MODE / WATCH THE GAME
field:             $047B=$03 $27=$06         screenshot: CAN 0 JAPAN 0, bats/AB
regression:        screenshots MATCH, system_ram differs in 0 bytes
```

---

## Loop 1 — reconstruct the experiment

The v1 build (`build/frame2-input.nes`) was ad-hoc and unreproducible. Rebuilt
the chain from `tools/` and made the experiment reproducible:

- `tools/build_bracket_input.py --return-on-a` — A writes `$04EF/$04F0`, `$07FF`
  then `RTS` instead of looping.
- `tools/build_launch_bridge.py` — patches the scene-18 entry (`$98B9`) and
  installs a fixed-bank trampoline at `$FF20`.
- `tools/romdev.py` — one-command romdev client (load/step/press/pc/bp/trace).

Confirmed from the scene table that `$98B9` is the **scene-18 handler**, not a
random routine: handler table base `$CC52 + 2*scene`, bank table `$CCAC[scene>>1]`.

| scene | handler | bank |
|---|---|---|
| 18 (`$12`) | `$98B9` | 5 |
| 19 (`$13`) | `$995F` | 5 |
| 3 (`$03`) | `$D17A` | 6 |

So END advances `$047B` 18 → 19 (the docs' "12 → 13" was reading hex as
decimal), and scene 19 is the password screen.

## Loop 2 — v1's frame is off by one, and the hook returns mid-instruction

`JSR` pushes PC+2 and `RTS` adds one, so the saved frame is correct, but after
the synthetic `RTS` `S` ends at `$FC` instead of `$FD`. Every later dispatcher
table lookup is then byte-shifted. The v1 hook also ended with `JMP $98BD`,
which is the middle of its own instruction. Both are fixed by the call-based
bridge: the handler is tail-jumped (`JMP $FF20`), the bracket is entered with
`JSR $8000`, and the scene-18 body is re-entered at `$98C0` with the stock
stack untouched.

## Loop 3 — restore a live task queue probe

`$CF74` (called from the NMI handler at `$CDE1`, and from the main loop at
`$CC2A`) ended with `JSR $816C` and `JSR $8048` into the **currently mapped
bank**. With bank 11 mapped, `$816C` is the operand byte of `STA $04F0` inside
the bracket A handler. Probe:

```
breakpoint PC=$816C, press A at END
hit: true  framesRun: 1  S=$F5  $27=$02
```

The bank check showed `$816C` was being hit in **bank 2** (a legitimate stock
routine), which is why earlier "hits" at `$8162/$8172` were false positives —
**romdev PC breakpoints are bank-agnostic**. Always read `$27` at the hit.

With bank 11 mapped the same call runs into bracket code. That is the v1 `$B005`
and the v2 `$AC88`/`$C002` family of crashes.

## Loop 4 — NMI guards ($2C/$2D) are necessary but not sufficient

Set `$2C=1` (the NMI handler's own reentrancy guard: `$CD8F` skips the body)
and `$2D=1` (`$CF74` returns at `$CFA9` before its bank-relative calls).
The bracket then survives indefinitely (S=$FB, `$27=$0B`, PC in the input
loop), but A still resumed into garbage.

## Loop 5 — the bank switch after the bracket selects bank 10, not 5

The bracket init did `LDA #$00 / STA $C040`. `$C040` is ROM, so the store does
not change the `BIT $C040` mask — but `$C040` is also **MMC1's CHR-1 register**.
That store pushes one stray bit into the mapper shift register. The next
`$C14E` write for bank 5 emits bits `1,0,1,0,0`; with the stray `0` first the
register latches `0,1,0,1,0` = **bank 10**. `$27` says 5, the hardware is on 10.

Proof (CPU stub copying the live bus to RAM):

```
$993D -> FF   (bank 5 has AD)
$8000 -> 78   (bank 10's first byte)
$A000 -> FF
```

Fix: replace the five `STA $C040` bytes with NOPs in `build_bracket_screen.py`
(same length, so the hand-assembled branch offsets are unchanged). The
display-list flush still takes its RLE path from the ROM byte `$40`.

## Loop 6 — `$98D5` waits on `$047D`, which only NMI clears

`$993D: LDA $047D / BNE $993D` waits for zero; `$9942` then sets it to one, so
every subsequent password character needs an NMI to clear it. With NMI disabled
the builder spins forever (the "infinite wait, not a crash" trap).

Fix: set `$AD=$1E` (matching the bracket's `$2001=$1E` write) and enable NMI
**before** `JSR $98D5`, keeping `$2C/$2D` asserted so the NMI handler only
clears `$047D`. Release the guards after `$98D5` returns.

## Loop 7 — end-to-end

With all four fixes: password screen, matchup, speed-mode menu, cutscene, field.
Stack `S=$FF` at the main loop; regression green.

---

## Final trampoline ($FF20, 49 bytes)

```
FF20 A9 01      LDA #$01
FF22 85 2C      STA $2C        NMI body short-circuit
FF24 85 2D      STA $2D        deferred-task guard
FF26 A9 00      LDA #$00
FF28 8D 00 20   STA $2000      NMI off for the bracket
FF2B A9 0B      LDA #$0B
FF2D 20 4E C1   JSR $C14E      bank 11 / $27=11
FF30 20 00 80   JSR $8000      bracket; A returns
FF33 A9 05      LDA #$05
FF35 20 4E C1   JSR $C14E      bank 5 / $27=5
FF38 A9 1E      LDA #$1E
FF3A 85 AD      STA $AD        PPU mask shadow
FF3C A9 80      LDA #$80
FF3E 8D 00 20   STA $2000      NMI on: $98D5 polls $047D
FF41 A5 33      LDA $33
FF43 85 34      STA $34
FF45 20 D5 98   JSR $98D5      password buffer
FF48 A9 00      LDA #$00
FF4A 85 2C      STA $2C
FF4C 85 2D      STA $2D
FF4E 4C C0 98   JMP $98C0      resume scene-18 body
```

## Corrections to the previous handoff

- `$C040` **is not a harmless no-op**: writing it is an MMC1 CHR-1 write and
  de-aligns the mapper shift register. Never `STA` to `$C000-$FFFF` casually.
- `$047B=$12` means scene **18**, not "12". The handler table is authoritative.
- romdev PC breakpoints ignore the PRG bank; read `$27` at every hit.
- The v1 "crash before `$8162`" was measurement noise: `$8162` in *another
  bank* was matched, and the real stop was the NMI/data path above.

## Remaining work (not launch-critical)

- Production flow: selector A currently just redraws; wire
  selector → `$07C3` → bracket → the same bridge.
- The bracket's A writes `$04EF/$04F0`, but the password/game path takes teams
  from `$33/$34`; set those from the bracket pick (and seed `$7700` from the
  selector's `$07C3`) so the launched game uses the bracket teams.
- The `--stock-flow` patch (restoring stock `$CC06`) is test scaffolding, not
  the shipped wiring.

---

# Session 2 — production wiring (loops 8–10)

## Loop 8 — selector → bracket → bridge

The bank-10 selector's A handler only set `$07C3` and redrew. Wired it to the
stock dispatcher instead of hardwiring `$FF20`:

```
select:  ... STA $07C3; JMP launch
launch:  wait for buttons released
         PLA / PLA            ; drop the JSR $FF00 return frame
         LDA #$12 / STA $047B ; scene 18 (the hooked handler)
         JMP $CC09            ; stock main loop
```

This reuses the exact stock call path and stack: the main loop's
`JSR $CC30` frame is the one the bridge's final `RTS` returns to. Verified:

```
selector A -> $047B=$12, $27=$0B, bracket input S=$F9 (inside JSR $817F)
bracket A  -> $FF35 S=$FD -> $98D5 -> $98C0 RTS -> $CC14 S=$FF
password   -> $047B=$13 $047C=$08
```

Bug hit on the way: `STA $047B` in the fixed-bank trampoline was assembled as
`85 7B` (zero page $7B) instead of `8D 7B 04`; the scene stayed 0 and the
password path advanced to scene 1. Absolute and zero-page forms are easy to
confuse in hand-assembled bytes.

## Loop 9 — the bracket inherited the selector's nametable

In the stock flow the scene transition clears the screen, so the bracket looked
clean. In the production flow the selector's tiles stayed on screen around the
bracket's runs. Added a nametable clear at the top of the bracket init
(`$2000-$23FF`, four 256-byte pages) — 25 bytes, no hardcoded branch offsets
changed.

## Loop 10 — production flow reaches the pre-game order screen

Selector → bracket → password → matchup → speed mode → cutscene now works and
ends at scene 15 (`$047B=$0F`) — the **pre-game batting-order / lineup screen**
("CHANGE ORDERS"), which the stock COM-vs-COM harness flow skips. It does not
advance on A/B/START/SELECT and the player portraits are garbled, so this is a
new open item (CHR-bank/state or an input this sweep did not hit), not a launch
bridge failure.

Working harness path (stock END, `--stock-flow`) still reaches the field:

```
END -> bracket -> A -> password -> matchup -> speed mode -> cutscene -> field
$047B = $03, $27 = $06, S = $FF
```

## Loop 11 — `$0522` (ROOT CAUSE of the production order-screen stall)

Comparing the cutscene state in both paths:

| var | stock harness | production |
|---|---|---|
| `$047B/$047C` | `11/08` | `11/08` |
| `$0522` | `00` | **`FF`** |
| `$04EF/$04F0` | `0c/00` | `0d/08` |
| `$33/$34` | `2d/39` | `a2/30` |

`$0522` is read at the top of the scene-15 handler (`$96ED`):
`LDA $0522 / BNE $96F8` — **nonzero skips the lineup init** (`$C585`/`$972C`).
It is `$FF` at boot, and the stock team-select path clears it. The selector
path never does, so scene 15 skipped its init and sat on the order screen.

Poke test from the production cutscene: `$0522=0` → field within 900 frames.

Fix: the trampoline stores `$0522=0` before resuming (a no-op in the stock
path, where it is already 0).

Production flow now reaches the field:

```
selector A -> $047B=$12 -> scene 18 hook -> bracket -> A
-> $FF35 -> $98D5 -> $98C0 -> $047B=$13
-> password -> matchup -> speed mode -> cutscene -> field
$047B=$03, $27=$06, S=$FF (main loop); gameplay PC=$CE01, S=$F7
```

Both builds (production and `--stock-flow`) reach the field; regression green.

## Loop 12 — where the launched teams actually come from

At the production field (`$047B=$03`):

```
$04EF/$04F0 = 0d 08
$0650..     = 08 0d 0f 03 01 0c 0a 05 0b 06 00 00 04 0e 07 02
$7700..     = 00 01 02 ... 1f        (the 32-team seed, correct)
```

The field teams are `$0650[0]`/`$0650[1]`, not `$7700` and not the bracket
cursor. `$0650` is built by `$98D5` → `$992B` from the fixed 16-value table at
`$994F` (`05 0c 03 0a 01 08 0f 06 0d 04 0b 02 09 00 07 0e`), rotated by `$04`
(`($C46F + $F5) & 15`). So the stock password path **always** launches a
16-team permutation of teams 0–15, independent of `$04EF/$04F0` and `$33/$34`.

That is why the bracket pick (and the team-name conversion tried earlier) does
not reach the field. Making the launched game use the bracket's teams requires
replacing this password/seed generator with the 32-team `$7700` array — i.e.
the "Password format for 32 teams / 5 rounds" milestone, not a launch fix.

---

# Session 3 — team handoff (loops 13+)

## Loop 13 — `$0650` is the team source; seed it from `$7700`

`$9C00` (scene 19 substate 2) is the real handoff:

```
$9C00 LDA $0746          ; match index
$9C03 ASL A / ADC $0746  ; 3*$0746
$9C07 TAX
$9C08 LDY $8941,X        ; bracket slot table
$9C0B LDA $0650,Y        ; team
$9C0E STA $04EF
$9C11 LDA $0651,Y        ; opponent
$9C14 STA $04F0
```

So the field teams are `$0650[$8941[3*match]]`/`+1`. `$0650` was built by
`$98D5` → `$992B` from the fixed table `$994F`, which is why nothing we wrote
to `$33/$34`, `$04EF/$04F0` or `$7700` reached the field.

Fix: a new fixed-bank routine `$FF60` (`TEAMSETUP`) replaces `JSR $98D5` in
the trampoline. It copies `$7700[0..15]` straight into `$0650` (and sets
`$064F=$FF`), then rebuilds the packed `$074D..$0754` pairs with the stock
packing loop.

Result, production field:

```
$04EF/$04F0 = 00 01        (bracket slot 0 vs slot 1)
$0650       = 00 01 .. 0f  (the bracket seed)
$074D       = 01 23 45 67 89 ab cd ef
field       = JAPAN vs ARI  (screenshot)
```

That is the bracket's first-round pairing on the field. The harness build
(`--stock-flow`) still launches, but its `$07C3` is `$FF`, so `$7700[0]=$FF`
and the harness field teams are garbage — expected: `$07C3` is a selector
variable that path never sets.

Limits: this maps the **first 16 bracket slots** into the stock 16-team
tournament. A real 32-team tournament (32 slots, 5 rounds, new `$8941`/state)
is still the larger milestone; the first match now matches the bracket.

## Loop 14 — selector regressions found while testing a non-default pick

Trying to pick team 5 exposed two real selector bugs (both pre-existing in the
dynamic-redraw path, both now fixed):

1. **Out-of-range branches.** Adding the `launch:` block pushed the direction
   handlers past the +-127 branch range. The assembler masked the offsets, so
   `BNE right` wrapped to `$802D` and up/down's `BCC/BCS release` wrapped too.
   The main loop now uses `BEQ nextcheck` + absolute `JMP handler`, and both
   assemblers (`build_select_screen.py`, `build_bank11.py`) raise on an
   out-of-range branch instead of masking it.
2. **Dynamic redraw hung the display-list flush.** `append_flag` copies 6
   bytes per team from the unimplemented flag area at `$AC00`, which is `$FF`
   filler. The flush (`$C55C CMP #$FE / BCS`) treats `$FF` as an end-of-run
   marker, then reads the next `$FF` as an RLE header and copies 255 bytes,
   overshooting `$32` forever. `append_flag` now replaces `$FF` with `$00`
   (blank tile), so the redraw completes.

Verified picks:

```
team 0  -> $7700 = 00 01 02 03...  -> 04EF/04F0 = 00 01  -> JAPAN vs ARI
team 5  -> $7700 = 05 00 01 02...  -> 04EF/04F0 = 05 00  -> NEW YORK vs JAPAN
```

Both reach the field with the same pair. The flags themselves are still
placeholders (blank tiles) in this chain — that is the separate flags milestone.
