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

## Loop 15 — the 4-bit password ceiling

Picks from the first page work; a page-2 pick (team 16, `$07C3=$10`) does not:

```
$7700        = 10 00 01 02 ...     (correct)
$0650 @pw    = ff 57 46 57 ...     (password text takes the buffer)
matchup      = 00 00               (id 16 collapsed to 0)
$0650 @match = 00 00 01 02
```

The stock password packs team ids as **4-bit nibbles** (`$9916` shifts each id
left four times), so ids 16–31 truncate to 0–15. Poking `$047C=2` to jump past
the password display does not help: substate 2 still rebuilds `$0650` from the
packed bytes.

So the bridge hands off correctly for teams 0–15 (the stock tournament size);
a real 32-team field needs the password/`$0650` generator replaced (the
"32-team password format" + 32-slot tournament milestone). This is a data
format change, not a launch-path bug.

## Loop 16 — the launched game really plays

From the field, 1800 frames of free-running (no input) show the camera following
play: the ball leaves the mound, fielders move, the batter animation changes.
`$047B` stays `$03`, `$27=$06`, not jammed. So the launch reaches a *running*
game, not a parked field.

## Loop 17 — skipping the password display is not enough

Patching the scene-18 body's `LDA #$07` at `$98C8` to `$02` enters scene 19 at
the matchup substate and skips the password display. Team 16 still collapsed to
0, because the matchup calls the 4-bit unpacker directly:

```
$9BFD JSR $9B5F
$9B5F LDA $074D,Y / LSR x4 / STA $0650,X / ... / AND #$0F / STA $0650,X
```

`$0650` is rebuilt from the packed `$074D` (4 bits per team) before `$9C00`
reads it.

## Loop 18 — direct team handoff at the matchup

`--direct-teams` patches `$9BFD: JSR $9B5F` to `JSR $FF60` (the team setup,
extended to zero `$0670` as well). The matchup then reads `$7700[0..15]`
directly:

```
team 16: $0650 = 10 00 01 ..., $04EF/$04F0 = 10 00
matchup: "JAP vs JAPAN"  (team 16's placeholder name/code)
```

But the **field is blank** for team 16 (`$047B=$10`, black screen). Teams 16–31
have placeholder roster/name data and no on-demand cache, so the game cannot
build their lineup. That is the "on-demand roster cache for teams 16–31"
milestone, not a launch bug.

Both new switches are opt-in: `--skip-password`, `--direct-teams`.

## Loops 19–25 — verification sweep

| loop | check | result |
|---|---|---|
| 19 | all four d-pad directions + page wrap | right 0→1, down 1→5, left 5→4, up 4→0, left 0→page3/cursor3, right page3/3→page0/0 |
| 20 | bracket seed for a page-2 pick | `$7700 = 10 00 01 02 …`, slot 0 shows team 16 (`T17`), cursor `$07C7` 0→1 on down |
| 21 | bracket A at slot 1 | writes `$04EF/$04F0 = 01 00`; the launch still uses match 0 (`$0650[0]/[1]`) — cursor is browse-only for now |
| 22 | clean rebuild from the documented chain + regression | `screenshots MATCH`, 0 RAM bytes differ |
| 23 | default and `--direct-teams` builds | both reach `$047B=$03` on the field |
| 24 | stock-flow harness after the team setup change | still reaches the field (`$047B=$03`, teams `0f/00`) |
| 25 | team 5 from the final build, end-to-end | `$07C3=05`, matchup `05/00` (NEW YORK vs JAPAN), field `05/00`, `$27=$06`, PC `$CE01` |

Working state: selector → bracket → A → (password) → matchup → speed mode →
cutscene → field, with the player's first-round pair. Teams 16–31 reach the
matchup with `--direct-teams` but need the roster cache/data before the field.

### Loop log index

1 reproduce · 2 frame/RTS · 3 NMI task queue · 4 `$2C/$2D` · 5 `$C040` MMC1 ·
6 `$98D5/$047D` · 7 end-to-end · 8 selector wiring · 9 nametable · 10
`$047B` zero-page · 11 `$0522` · 12 team data path · 13 `$0650←$7700` · 14
selector branches + `$FF` redraw · 15 pick verification · 16 playability · 17
skip-password · 18 direct-teams · 19 directions · 20 bracket seed · 21 bracket
cursor · 22 rebuild/regression · 23 default/direct field · 24 harness · 25
final team-5 run.

---

# Session 4 — teams 16–31 (loops 26–30)

## Loop 26 — the scene-16 hang is a 16-entry name table

Team 16 with `--direct-teams` reached the matchup but the field was a black
screen, stuck in scene 16. The scene-16 code at `$AF53` loads a team name:

```
AF53 ASL A / TAY
AF55 LDA $B2D6,Y / STA $00     ; 16-entry pointer table
AF5A LDA $B2D7,Y / STA $01
AF63 LDA ($00),Y / STA $06B5,X ... CMP #$FF / BNE
```

For team 16, Y=32 reads past the table into the name strings themselves, gets a
bogus pointer, and copies until it happens to see `$FF` — which never came.
`$AF55` is also where the "TEAM 17" name came from once the table was fixed.

Fix: `tools/build_names32.py` builds a 32-entry long-name table + placeholder
names at `$BC80`/`$BCC0` in bank-1 free space and repoints `$AF55/$AF5A`.

## Loop 27 — the patch wrote to the wrong bank

The short-name table at `$9280` has the same 16-entry problem, and its loader
is at **`$C958` in the fixed bank**, not bank 1. The first version of the tool
used the bank-1 offset for `$C966`/`$C96B`, so it (a) never patched the loader
and (b) wrote two bytes into bank 2 at `$8966`/`$896B`. The scene still hung.

Fix: a `foff()` helper for `$C000-$FFFF`; the loader now reads `$BD40/$BD41`.

## Loop 28 — team 31 works too

With both tables extended, a page-3 cursor-7 pick (`$07C3=$1F`) reaches
matchup `1f/00` and the field (`$047B=$03`, teams `1f/00`).

## Loop 29 — `--direct-teams` without skipping the password screen

The bridge patch alone (password display intact) is enough: the display runs,
then the matchup's patched `$9BFD` call re-seeds `$0650` from `$7700`. Team 16
reaches the field with the password screen preserved.

## Loop 30 — teams 0–15 unchanged

Team 0 on the 32-team build: matchup `00/01`, field `00/01`, `$047B=$03`.

### 32-team build

```
build_launch_bridge.py build/bracket-launch-input.nes --direct-teams -o build/launch-direct.nes
python3 tools/build_names32.py build/launch-direct.nes -o build/launch32.nes
```

All 32 ids are selectable and reach the field. Teams 16–31 still use the
placeholder bank-8 blocks (Florida's roster copied with `B1601`-style names),
and the field HUD shows `FLO`/`JAPAN` for them — the real per-team data is the
next data milestone, not a launch blocker.

## Loop 31 — the field HUD still says FLO for team 31

The short-name loader has a second copy in bank 7 (`$8958`), which the field
HUD reaches through the bank-7 mapping; `build_names32.py` now patches both
copies (`$C965/$C96A` and `$8965/$896A`).

The HUD nevertheless still shows `FLO` for team 31. A write breakpoint on the
name buffer `$06B5` lands at `$AF65` (the LONG-name loader, bank 1), so the
`$06B5` buffer is not the HUD source. The 3-letter scoreboard name comes from a
different path and is almost certainly tied to the placeholder block being a
copy of team 15's (Florida) — the roster/name data milestone, not a table
pointer bug. Cosmetic; the game plays.

## Loop 32 — 32-team bracket state in the launch path

`build_32bracket.py --state` installs a 31-record table at `$FC00`, a seed at
`$FD00`, slots at `$7700` and counters at `$7740`, and rewrites the bank-5 init
(`$9B5F`) to copy the seed and zero the counters.

The stock `--state` init overwrites `$7700`, which would discard the bracket
screen's human-first seed. Added `--keep-seed`: the init's `LDA $FD00,X` becomes
`LDA $7700,X` (a self-copy), so the screen's seed survives and the counters are
still zeroed.

Verified: team-5 pick → matchup `05/00`, `$7700 = 05 00 01 02 …`,
`$7740 = 00 …`. The advance routine checks the 16-bit result mask at
`$0755/$0756`, picks slot A/B from `$FC00`, increments the selected team's
`$7740` counter and writes it to the destination `$FC02`. A CPU call with
`$0746=1`, `$0755=1` advanced team 0 to slot 32 and incremented `$7740[0]`.

## Loop 33/34 — a full COM game returns to the title, no advance

Stepping 20 000 frames from the field ends at scene 2 (`$047B=$02`, handler
`$CFAA`, the title/boot scene) with a garbled screen, on **both** the stock
16-team `launch32` and the 32-team-state build. `$0746` stays 0 and no slot is
advanced.

So this is a launch-path/post-game issue that predates the 32-team state: the
hack reaches a playable field, but the end-of-game path returns to a broken
title scene instead of a result/bracket update. Next probe: log `$047B` in
300-frame slices from the field to catch the field → result → title
transitions, then inspect the first non-field scene.

## Loops 35–40 — the post-game crash was the missing roster cache

A full COM game on the launch builds ended with PC=`$7703` (PRG RAM), jammed,
and a garbled title scene. The **pure stock ROM does not crash** — it goes
field → scene 5 → scene 2 cleanly. So the hack introduced it.

`build_32x20.py` repoints roster reads to `$7F00`, expecting the `$FB90` cache
routine to run from the `$CBE6` hook. But `build_dispatcher.py` restores `$CBE6`
to stock and hooks `$CC06` instead, so **the cache never ran** and `$7F00` was
all zeros. The box-score / post-game path dereferences those pointers and jumps
into RAM.

Fix: `build_dispatcher.py --roster-cache` prepends `JSR $FB90` to the `$FF00`
dispatcher. First attempt still stalled in the main loop because the cache
leaves A=0 and the dispatcher's `STA $2000` then disables NMI; added
`LDA #$80` before it.

With the cache in the chain:

```
boot: $7F00 = 00 60 70 61 e0 62 ...   (pointers populated)
field -> scene 11 (box score) -> A -> $0746 = 1, $047B = $13
box score: JAPAN 3, N.Y. 0 (line score 000300 / 000000)
```

So a full game completes, the box score shows, and the tournament advances to
the next match. This also explains the earlier "garbled title" after a game.

Note: `--stock-flow` bypasses the dispatcher, so the harness build does not run
the cache and still crashes after a game; the production/32-team builds do.
