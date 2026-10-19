# AUTORUN report — rounds 1–2

## Phase 0 — handoff owner (qualified)

- 52 static refs to `$04EF`. Writers: bank0 `$AD1B/$AD22/$AD2B`, bank1
  `$B119` (home/away swap), bank2 `$BC8C` (table `$B8C9`), bank5
  `$9C0E/$9C14` (bracket).
- Bank0's routine uses `$33` and `$C46F`; `$C46F` is a table sequencer
  (`INC $34`, table `$C4FA`), not a team lookup.
- Direct `cpu({op:'call'})` into bank6 `$AC3A` produced `$04EF=$02`,
  `$04F0=$06`, confirming that path is a different context, likely field/demo.
- Conclusion: bracket raw-slot writes remain plausible; do not change the
  contract without a real bracket→game trace.

## Phase 1 — launch (parked)

Jumping from the A-handler into bank6 `$AC3A` (after `$C1|=2`, bank6 mapped)
crashed the core (`PC=0`). Calling it sandboxed returned but did not change the
scene. This is not the launch entry. Parked under the 30-minute rule.

## Phase 3 — 32-team seeding (logic green)

- Bank-11 `seed` at `$8011`: reads `$07C3`, writes leaf 0, fills 1–31.
- py65: human 0/15/31 → leaf 0 correct, all 32 unique.
- Fixed `size_of` in `build_bank11.py` (zero-page operands were counted as
  3 bytes, shifting branches). Advance re-verified: champion slot 62, win sum 31.
- Screen integration blocked: at the `$CBE6` hook, PRG RAM writes to `$7700`
  read back as open bus, and `$07C3` is not set yet. The selector/dispatcher
  must set `$07C3` and enable PRG RAM before seeding.

## Next probes

1. Enable PRG RAM (MMC1 CHR0 bit 4 / board rules) before any `$7700` access;
   verify with `memory({op:'read'})` on the cart-RAM region.
2. Have the dispatcher write `$07C3` before jumping to bank 11.
3. Find the true launch entry by tracing the stock bracket handler's scene
   transition, not bank6 `$AC3A`.

## Regression

Stock ROM untouched; default build remains table-only. No red regression left.

## Round 3 — PRG RAM investigation (partial)

- iNES header byte 8 (PRG RAM size) is `0`. Patching it to `1` (8 KiB) did **not**
  change behavior in fceumm.
- Bank-11 seed logic passes in py65 with the human copied to `$07CA` instead of
  zero-page `$02` (which stock code clobbers): human 15 → slot 0, all 32 unique.
- In-ROM seed at `$8200` still corrupts: `$7702` stays `FF`, values after it
  shift, and a manual `cpu call` to the seed leaves the slots untouched even
  after `$C11C` CHR0=0. Cart RAM region writes via romdev work, so the mapper
  write path is the suspect, not the array.
- Screen integration reverted; no broken build committed.

### Next probe

Watch CPU writes to `$7700` in romdev during the seed (`breakpoint on:write`),
and log the MMC1 CHR0 value at the same instant. If writes are dropped, test
SNROM PRG-RAM enable semantics or move bracket state into system RAM until the
board behavior is understood.

## Round 4 — PRG RAM is writable; NMI corrupts the seed

Decisive CPU test (romdev):

```
LDA #$AB
STA $7700
LDA $7700
STA $0400
RTS
```

`$0400` read back `$AB`, so PRG RAM is writable; the mapper is not blocking
writes. A hardcoded-human seed run from system RAM with `$2000=0` (NMI off)
produced a perfect 32-slot array. The same seed at boot still leaves `$7702=FF`,
so something in the boot/screen path corrupts it after the seed.

Manual seed with NMI left on wrote nothing; with NMI off it wrote correctly.
That points at the stock NMI handler touching cart RAM, not the seed loop.

Screen feature reverted; no broken build committed.

### Next probe

Boot the screen, immediately after the seed copy `$7700..$771F` to system RAM
inside the same routine (before enabling rendering/NMI), and inspect that copy.
If it is clean, the corruption is post-seed from NMI; if not, instrument each
store.

## Round 5 — seed integration GREEN

Root cause of the earlier corruption: the test ROM jumped to an empty `$8100`
(input stub missing) and executed `FF`; the seed itself was fine. With the input
stub present and NMI disabled immediately before `JSR $8200`, the boot-time seed
produces:

```
0f 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e
10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f
```

32 unique values, human 15 at leaf 0, stable across frames. `build_bracket_screen.py`
now supports `--seed-human`; the production selector supplies `$07C3`.

Phase 3 is green. Next: render names from `$7700` and then return to launch.

## Round 6 — dynamic names blocked by display-list/RLE state

- Seed integration remains green (commit `9cea1e0`).
- Attempted to rewrite each team run in the copied display list from
  `$7700`/code table. The list itself updated correctly (`FLA` appeared at
  leaf 0), but `$C53A` then stalled in its RLE branch and the screen went blank.
- `BIT $C040` selects the RLE path. ROM byte `$C040` is `$40`, yet the static
  list (high bytes `$20`) rendered earlier, so the runtime value/semantics need
  measurement, not assumptions.
- Render experiment reverted; no broken build committed.

### Next probe

Read `$C040` on the CPU bus at the moment of flush (romdev memory read at
`$C040`, not `$0040/$00C0`), and compare a static list vs the rewritten list.
If the static list is normal-mode, our rewritten bytes must be corrupting a run
header; dump `$0300..$033F` before flush.

## Round 7 — seeded names render GREEN

Root cause of the previous blank/RLE corruption: team 5's code is `"NY"` (2
chars), so its display-list run was 5 bytes and every later run shifted by one,
corrupting a run header. Codes are now padded to 3 chars (`"NY "`), list length
is 245, and the dynamic renderer writes 3 tiles into each 6-byte run.

romdev screenshot: human team 15 (`FLA`) at leaf 0, then `JPN, ARI, PEN, ...`
with team 15 skipped — exactly the seeded order. Phase 3 is now green end-to-end.

## Round 8 — regression guard GREEN

`tools/verify_regression.py` loads two ROMs in romdev, runs both 180 frames,
compares screenshots and all 2 KiB of system RAM.

Stock vs default `build/32bracket.nes` (table-only):

```
screenshots MATCH
system_ram differs in 0 bytes
```

This is now the stop-rule oracle: any phase that changes stock behavior fails
this test.

Attempted to force the stock bracket screen from the `$CBE6` hook
(`$C1|=2`, `$047C=0`, bank5 `$9BC1`); it stayed black. Parked; that scene needs
more state than a post-init jump provides.

## Round 9 — resume path enters a baseball scene (partial)

After writing `$04EF/$04F0` and setting `$C1` bit 1, jumping to `$CBE9` (the
instruction after the `$CBE6` hook) enters a baseball scene instead of the
bracket: green field tiles, blue dots, a player sprite, PC in bank 6. The scene
is visually broken because stock scene init (CHR/PPU/nametable) was skipped by
the hook.

This is the first confirmed path from bracket input into game code. Next probe:
compare `$2000`, CHR0/CHR1, `$C1`, `$047C`, `$0746`, and PPU mask at the same
frame in stock game start vs this resume path; replicate the missing init before
`JMP $CBE9`.

Experimental handler reverted; default A behavior unchanged.

## Round 10 — hook moved after reset init (GREEN)

Root problem: `$CBE6` is `LDA #$00`, not a callable routine. Replacing it with
`JSR $FF00` skipped that load and made `STA $2001` run with the wrong A.

Fix in `build_dispatcher.py`:

- restore `$CBE6..$CBEA` to `A9 00 8D 01 20` (LDA #0 / STA $2001)
- hook at `$CC06` (`STA $2000`) instead
- trampoline starts with `STA $2000`, preserving the store it replaced
- `--force` patches the dispatch's `LDA $07C3`, not the trampoline prologue

Verified:
- default selector renders with full stock reset init complete
- 32-team bracket renders with `FLA` at leaf 0, full init complete
- stock regression still MATCH / 0 RAM diff

## Round 11 — stock game path reached (GREEN)

The stock flow was misread earlier. The team-select prompt is:

- **CONTINUE** = keep editing teams (returns to map)
- **END** = finish selection

Correct path:

```
team select -> END -> PASSWORD -> A -> matchup (Italy vs Pennsylvania)
-> A -> SPEED MODE / WATCH THE GAME -> down + A -> pre-match cutscene
-> field
```

Field state captured:

```
$04EF = $0D (Italy)
$04F0 = $02 (Pennsylvania)
$047B = $03 (field scene)
$C1   = $76
$0746 = $0000
```

This is the authoritative target. Setting the same bytes directly from the
32-team bracket still returns to the bracket, so the missing piece is the
pre-match/scene init routine (the password/matchup path), not the handoff values.

## Round 12 — field scene writer found (partial)

Exact write breakpoint on `$047B=3` through the stock mode-select/pre-match path:

```
pc        = $D010   (bank 7)
instruction = INC $047B
caller    = $CC11
old -> new = $02 -> $03
```

Routine:

```
$D001  STA $B6
$D003  JSR $D161
$D006  LDA #$00
$D008  STA $0486
$D00B  LDA #$04
$D00D  STA $047A
$D010  INC $047B
$D013  RTS
```

So `$047B=3` is reached by **incrementing from 2**, not by a direct store. The
scene-3 handler then runs (`$D014...`, banks 4/6, `$8EF8`, `$AE34`, `$E80A`).

From the 32-team bracket, setting `$047B=2`, `$047A=4`, `$0486=0`, `$C1=$76`
and returning to `$CC09` now reaches a scene-3 screen (no longer the bracket),
but it renders garbled field/text tiles: CHR and the team pointers
(`$0511/$0512`, `$23/$24`) are not initialized.

Next probe: freeze the stock field state, diff full RAM against this scene-3
state, and set the missing pre-match fields before entering `$CC09`.

## Round 13 — probe 1: aligned diff (negative result)

A naive 300-frame field-vs-hack diff was meaningless (1178 system bytes, wholly
different phases). Aligned instead on the exact `$047B=3` write.

Stock at that instant:

```
$047B=03  $047A=04  $C1=$76
$04EF=0B 06 (Mexico/California)
$0023=08 08   $0511=0000
```

Hack (`bracket-scene2`) after A:

```
$047B=02  $047A=$FF
PC=$C002  (executing the data table at $C000, not code)
```

The hack **never reaches scene 3**. Its garbled screen was stale scene-2
rendering; the `JMP $CC09` path crashes into `$C000` data. Also, `$D014` is not
the scene-3 handler: breaking there hit while `$047B` was still 2.

Probe 1 outcome: no meaningful byte diff is possible until the `$CC09` entry is
fixed. That is the next blocker, not CHR or team pointers.

## Round 14 — stack/PC dump at the $C002 crash

`$C002` is opcode `$02` = **KIL/JAM**. The CPU is dead, not looping. There is no
`JMP $C002`, `JSR $C002`, or `JMP ($C000)` anywhere in the ROM, so the PC came
from a corrupted return/RTI frame.

At `$CC09` entry (after A):

```
PC=$CC09  A=$80  X=$00  Y=$20  P=$A4  S=$FD
stack $01F0..FF = e3cd0a40d7a40b9fa9d0d2cf13cc08cc
$2C=$00  $AC=$00  $AD=$1E  $0190=$00  $047B=02
```

At the `$C002` hit:

```
PC=$C002  A=$40  X=$10  Y=$40  P=$37  S=$F7
stack $01F0..FF = e3cd0a40d7a40b9fa9d0d2cf13cc08cc
$2C=$00  $047B=02
```

`S` moved FD→F7 (6 bytes), but the stack contents look like scene data
(`9F0B D2CF ...`), not balanced JSR frames. Resetting `S=$FF` before
`JMP $CC09` did **not** fix it.

Relevant NMI rule:

```
$CD8A  LDA $2C
$CD8C  STA $04E6
$CD8F  BNE $CDE1          ; skip main body if locked
...
$CDE4  LDA $AD
$CDE6  AND #$1E
$CDE8  BEQ $CDEF          ; only clear $047D when rendering bits set
$CDEA  LDA #$00
$CDEC  STA $047D
```

Trace from `$CC09` sits at `$CD86` (NMI entry) and never returns to the main
loop; once jammed, traces are all `$C002`.

Next: capture the exact instruction before `$C002` with a held-A trace from the
input loop, and log every push/pop in the NMI path. The prime suspect is a
return frame consumed during scene 2→3 transition.

## Round 15 — exact runaway path found

Frame-by-frame `traceInstructions` from `$CC09` caught the transition:

```
... CFA7 CFA9 CDE4 ... CDF4 (RTI)
9F0B 9F0E 9F11 ... A000 ... BFFF C002 (KIL)
```

The RTI at `$CDF4` returns to **`$9F0B`**, then execution runs sequentially
through the entire `$9F0B–$BFFF` window into `$C000` data and jams at `$C002`.

Key facts:

- `$9F0B` is a **bank-5** code address. While our bracket build has **bank 11**
  mapped at `$8000–$BFFF`, `$9F0B` is bank-11 data, not that routine.
- No `JSR $9F0B` / `JMP $9F0B` exists in the hack ROM.
- Disabling NMI, resetting `S=$FF` before entry, and entering at `$CC0E`
  (skipping the `$047D` wait) **all still jam at `$C002`**.
- Therefore the failure is a **bank-relative resume into bank 5 while bank 11 is
  mapped**, not merely a corrupted stack byte.

Implication: jumping into stock scene code from the bank-11 scene is unsafe
while stock still has bank-5-relative continuations. The launch path must either
keep bank 5 mapped until those continuations finish, or enter through a stock
routine that establishes bank-11-safe frames.

Next: log every `JMP`/`RTS` target in the frame and identify the first target
that assumes bank 5, then either remap that pointer or preserve bank 5.

## Round 16 — $9F0B is valid bank-5 code

Disassembly of bank 5 at `$9F0B`:

```
9F09  LDX #$E6
9F0B  STX $0201
9F0E  INX
9F0F  STX $0205
9F12  INX
9F13  STX $0209
9F16  INX
9F17  STX $020D
9F1A  RTS
```

It is a legitimate OAM/sprite routine, not data. With bank 11 mapped, the same
address is bank-11 data — hence the runaway to `$BFFF`/`$C002`.

Bank-5 mapping via a fixed trampoline (`$FF20`, five `STA $E000` writes):

- **without NMI**: PC waits cleanly at `$CC09` (no jam)
- **with NMI**: jams again at `$C002`
- **bank 5 + `$047D=0` + `JMP $CC0E`**: jams again

So this is a **bank switch under a bank-5-resident call**, not a corrupt return
address. The next probe is to log the fifth MMC1 PRG write during the field
transition and find which code switches away from bank 5 while PC is inside it.

## Round 17 — bank activity during the stock field transition

Watched `$27` (the MMC1 PRG shadow) for 2200 frames from mode select, driving
down+A through the cutscene. 122 bank changes; representative sequence:

```
f2327  4->6 at $C264
f2329  6->2 at $C636
f2330  2->4 at $C271
f2333  0->6 at $CC0C
f2638  2->5 at $C155
f2639  5->3 at $E2F2
f2645  3->6 at $AA30
f2657  6->5 at $986B
f2667  5->6 at $9FEC
```

The field routine runs primarily in **banks 2, 5, and 6**; `$9F0B` is a bank-5
OAM routine called in that rotation. Bank 11 is never part of the field's
expected bank state.

Conclusion: a bank-11-resident scene **cannot jump into the stock main loop** and
expect it to work, even with `$27=5` set once. The field's own `$C14E` calls
immediately rotate banks 6→2→5→3, and any return into `$9Fxx` after the rotation
executes whatever bank is mapped.

The launch path must be a **fixed-bank/RAM stub** that:
1. writes the handoff and scene state,
2. enters a stock scene entry with the bank state stock expects,
3. never returns to bank 11.

Next probe: find the stock routine that begins the bank-6 field loop (the
`0->6 at $CC0C` transition) and call that from a fixed-bank stub, rather than
`JMP $CC09`.

## Round 18 — exact bank-6 writer

Exact write breakpoint on `$27=6` through the stock field transition:

```
pc=$C14E  A=6  X=0  Y=6  S=$F9
old->new = $01 -> $06
```

`$C14E` is the bank-switch helper itself. Its callStack (`$CC1B -> $CECC ->
$CEE1`) is **not trustworthy**: `$CEE1` is `JSR LCEED`, which reads `$4016`
(controller), not a bank switch. Stock uses RTS-threaded dispatch, so stack
walks lie.

Static `LDA #6; JSR $C14E` sites: 31, all in fixed bank 7. Likely field-entry
candidates:

```
$CBB9  early scene init
$D02A  scene-3 block (after $D014)
$D045  scene-3 block
$D098
```

Next: PC breakpoint at `$CBB9` and `$D02A` independently during the transition,
trace one frame from each, and identify which one sets `$27=6` for the field
loop. That call site is the target for the fixed-bank launch stub.
