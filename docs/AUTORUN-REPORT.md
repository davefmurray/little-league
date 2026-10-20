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

## Round 19 — D02A confirmed; D014 direct call insufficient

PC breakpoint at `$D02A` during the stock mode→field transition hit at frame
2330. Raw bytes there:

```
D02A  A9 06        LDA #$06
D02C  20 4E C1     JSR $C14E   ; select bank 6
```

So `$D02A` is the field-loop bank-6 switch, inside the scene-3 block that starts
at `$D014`.

Calling `$D014` from the fixed-bank stub (`JSR $D014 ; JMP $CC09`) still ends in
data at `$C012`, with the bracket screen frozen. The scene block reads
`$0511/$0512` and indexes tables `$D05F/$D062` to set `$23/$24`, then calls
`$AF12` (bank 4), `$8EF8` (bank 6), `$AE34` (bank 4).

Missing precondition: `$0511/$0512` team/alive state. In stock field both were
`0000`, but the preceding password/matchup path sets the surrounding scene
state (`$04E6`, `$2C`, stack chain) that `$D014` assumes.

Next: set `$0511/$0512` from `$04EF/$04F0`, `$04E6=1`, `$2C=0`, then call
`$D014`; if it still jams, capture `$23/$24` immediately after the two table
lookups and compare stock.

## Round 20 — non-returning C1E5 is the fall-through

Bank-4 `$AF12`:

```
AF12  LDA $051B
AF15  BEQ $AF1A
AF17  JMP $AFE9
AF1A  JSR $C1E5
AF1D  .byte $23 ...        ; data

AFE9  JSR $C1E5
AFEC  .byte $22 ...        ; data
```

Both paths call `$C1E5` and then fall into **data** — `$C1E5` is a non-returning
scene routine. In our path it returns, so execution runs through `$AF1D`/`$AFEC`
and eventually into `$C002`.

Setting `$051B=1` before calling `$D014` still jams at `$C012`; `$0511/$0512`,
`$04E6`, `$2C`, `$051B` are not the return condition.

Next: break at `$C1E5` from the stub, capture its entry registers and stack, and
compare with the stock field transition. Then either satisfy its exit condition
or call `$C1E5` directly from the fixed stub with the stock state.

## Round 21 — stock reaches D02A, stub does not

Stock `$D02A` entry (frame 2329):

```
A=$80  X=$04  Y=$06  S=$FB
$27=04  $047B=02
$0511/$0512=0000
$0023/$0024=08 1D
```

Stub (`$D014` from fixed bank) with the same handoff/state:

```
PC=$C012  (jammed)
$D02A never reached
```

So the divergence is **before** the bank-6 switch, inside `$D014`'s first
`JSR $AF12` path. In stock, `$C1E5` is a non-returning scene handoff at that
point; in the stub it returns and execution falls through `$AF1D` data into
`$C012`.

`$C1E5` is not field-specific: an earlier stock hit occurred at `$047B=$11`,
`$051B=$FF`. Its return behavior depends on caller state, not a single flag.

Next: break at `$AF12` **from `$D014` in stock**, capture `$051B`, `$047B`,
`$23/$24`, registers and stack at that exact call, then reproduce those at the
stub. That is the last state delta before the field switch.

## Round 22 — D019 state delta; block is not independently callable

| | stock | stub |
|---|---|---|
| frame | 2330 | 11 |
| A/X/Y | 0 / 1 / 4 | 0 / 0 / 32 |
| P | $26 | $06 |
| S | $FB | $FB |
| `$051B` | 00 | 01 |
| `$047B` | 02 | 02 |
| `$0023/$0024` | 1B 1D | 00 00 |
| stack | `f881 c381 a6cf e3cd a00f 18d0 e8cf 13cc` | mostly `FF` |

Matching `$23/$24=1B1D`, `$051B=0`, `X=1`, `Y=4`, `A=0` still jams at `$C012`.
The stack proves why: stock reaches `$D019` through the full cutscene call
chain; the stub calls `$D014` directly, so every caller frame is missing.

Conclusion: `$D014`/`$AF12`/`$C1E5` are **not independently callable scene
blocks**. They depend on the live cutscene call chain, not just registers/RAM.

Next architecture: stop calling internal field blocks. Either
1. enter the stock **matchup scene** (`$047B=$11`, where `$C1E5` was hit) and let
   stock build its own chain, or
2. patch the two selected team ids into the stock password/matchup path and let
   it run to the field normally.

## Round 23 — poked IDs are honored by the field (GREEN)

At the stock matchup screen (Mexico vs California), poked:

```
$04EF = $0F  (Florida)
$04F0 = $00  (Japan)
```

then ran A -> mode -> down+A -> cutscene. The resulting field shows:

```
FLO  0
JAPAN 0
```

with Japanese player names (`ESAKA`, `DON`). Stock fully honors the poked team
IDs. This validates the “patch IDs, reuse stock flow” architecture.

Attempting to enter scene `$047B=$11` directly from the bracket sets the scene
and `$C1=$76`, and bank-4 code starts (`$AF9D JSR $AA00`), but the PPU stays on
the bracket frame and the PC freezes at `$AF9D`. The scene expects the stock
password/matchup transition setup, not a cold scene poke.

Next: enter the matchup scene through the stock **password screen** path (or
initialize its PPU/CHR/transition state), then let it run with poked IDs.

## Round 24 — autonomous probe batch (6 probes)

1. Matchup scene is `$047B=$13`, not `$11`. The password screen is **also**
   scene 13 with a different sub-state.
2. Cold-entering scene 13 from the bracket crashes at PC `$5248`.
3. Poking `$04EF/$04F0` at the password screen is overwritten; matchup still
   shows the original teams.
4. Poking at the **matchup screen** is honored: field renders `FLO` vs `JAPAN`
   with Japanese player names (`docs/poke-field.png`). This is the proven ID
   path.
5. Password→matchup RAM diff found scene-13 candidates: `$047F` 04→30,
   `$047E` ff→01, `$047C` 08→03, `$0478/79` 00→01, plus `$04EB/EC=80`,
   `$0650` seed table.
6. Cold scene 13 with those substate values still crashes at `$5248`.

Conclusion: scene 13 depends on the password transition chain, not just substate
bytes. The low-risk integration is now a **post-password hook**: let stock build
scene 13, then overwrite `$04EF/$04F0` from the bracket before the matchup text
is rendered. That avoids entering the scene cold entirely.

Next: find the scene-13 init call that copies team ids into `$0650`/`$06B5` and
hook immediately after it.

## Round 25 — scene dispatch is RTS-table based (structural)

Fixed `$C232`:

```
C232  ASL A
C233  TAY
C234  INY
C235  PLA          ; pop inline table address
C236  STA $35
C238  PLA
C239  STA $36
C23B  LDA ($35),Y  ; fetch handler low
...
C246  JMP ($35)
```

It is an **RTS-trick dispatcher**: the caller must `JSR $C232` with an inline
pointer table immediately after the call. Cold-jumping into the scene code pops
whatever happens to be on the stack, which is why scene 13 landed at `$5248`.

The scene-13 table entry `$B9C0` is itself another RTS-table state machine
(`JSR $C232` with inline tables at `$B9C9`, `$B9D1`, `$B9DC`). Calling it with
bank 2 mapped keeps the CPU alive but freezes at `$B9D1` — it is waiting for its
dispatcher frames, not drawing.

Conclusion: cold-entering stock scenes is impossible without reproducing their
stack-resident tables. The only safe integration is to let stock run its own
flow and patch **state** at a known point.

Next: hook the post-password scene-13 state machine where it copies team ids,
not its entry point.

## Round 26 — menu integration works; header bug found

Critical bug: the base ROM header declares **8 PRG banks**. Writing bank 11
extended the file to 256 KiB but left byte 4 = 8, so the mapper could never
select bank 11. Any menu hook was silently jumping into whatever bank was
mapped.

Fix: start from `expand_rom.py` output (16 banks, header byte 4 = 16, fixed bank
15), then patch.

Working integration:

- scene `$0D` (team select) handler is `$B9C0` in bank 2
- patch `$B9C0` to `JMP $FF20`
- fixed trampoline `$FF20`: five `STA $E000` writes select bank 11, then
  `JMP $8000`
- boot stock -> menu -> Championship -> Start New Series -> bracket appears

Remaining bug: bracket A sets `$047B=$13`, `$C1=$76`, then `JMP $CC09`. After
300 frames the readback is `$047B=$0D`, `$C1=$00`: the stores are being lost
before the scene handler runs. Next: verify the A-branch bytes and whether the
scene-0D handler/JMP path re-enters before the stores execute.

## Round 27 — A-state now sticks; crash is before C232

Found a real bug in the experimental handler: a global `RTS` replacement had
also rewritten the **controller-read subroutine** to `JMP $CC09`. The input
loop therefore jumped to the main loop before its A branch.

With that fixed (only the A branch jumps to `$CC09`):

```
$047B = $13   (sticks)
```

but the CPU immediately lands at `$5248` and never reaches `$C232`. So the
crash is **before** scene dispatch, not in the dispatcher table.

`$C232` breakpoint during the transition: `hit:false`, `pcNow=$5248`.

Next: trace the single frame from the A branch to `$5248` and find the first
bad jump. The controller-read `RTS` fix is required in the real builder.

## Round 28 — trace shows jump to $0200 after the A store

Instruction trace from bracket A:

```
... 816C 816E 8170 CDF4(RTI) 8172 8174 -> 0200 -> 028A ... 02FE -> 5248
```

`$8174` is `STA $047B`; its next instruction should be `$8177`. Instead PC
becomes `$0200` (the OAM buffer), runs sequentially through zero page, then
lands at `$5248`.

So `$047B=$13` does stick, but an interrupt/return frame pops `$0200` as a PC.
That is stack-pointer corruption or a wrapped return, not scene dispatch.

Disabling NMI and entering at `$CC0E` (`$047D=0`) still jams at `$C002`, so NMI
is not the only cause.

Next: capture `S` and `$01F0..$01FF` exactly at `$8174`, then single-step the
`STA` and the interrupt. If `S` is near `$00`, find the JSR/RTS leak in the
input loop; if `S` is normal, the return address itself is being overwritten.

## Round 29 — A branch is clean; NMI/dispatch wall

At `$8174`:

```
A=$13  S=$FD
stack: d181 a6cf e3cd 1031 45a4 e3ce 2981 13cc
```

Single-step `STA $047B` lands correctly at `$8177`. All A-branch stores execute.
At `$8180 JMP $CC09`, an NMI arrives before the jump and vectors to `$CD86`.

At that moment:

```
$2C=00  $AD=$40  $047D=01
```

`$AD` is `$40`, not `$1E`, so the NMI handler's later gate would set it, but the
handler appears to storm at `$CD86`. Disabling NMI and entering at `$CC0E` with
`$2C=0`, `$AD=$1E`, `$047D=0` still jams at `$C002`.

So the failure is not a single flag; entering the stock main loop from the
bracket still violates its dispatch/stack expectations.

Next definitive probe: break at `$C232` with `$047B=$13` during the **stock**
password screen, single-step the dispatcher, and record the exact popped table
address and JMP target. That names the real scene-13 handler instead of guessing
from table layout.

## Round 30 — real scene-13 handler decoded: $995F

Broke at `$C246` during the stock password screen:

```
A=$13  Y=$28  $35/$36 = 5F 99
target = $995F   (bank 2)
```

So scene 13 is handled by **`$995F`**, not `$B9C0` (that is team select).

Calling `$995F` from a fixed bank-2 stub:

- no jam, PC returns to main loop
- renders the Little League Pledge screen
- A advances to the 50th Anniversary screen
- A advances to the title screen

This is the first successful stock-scene call from the bracket. It proves the
method: **correct handler + correct bank = working scene**.

The password screen also reports `$047B=$13`, so it is a **sub-state** of the
same handler, not a different scene. Next: diff the intro/password sub-state
variables and drive `$995F` directly to the password/matchup branch.

## Round 31 — bank index bug; correct handler is bank 5 $995F

Scene bank lookup is `$047B >> 1`, so scene `$13` uses index **9**, not 6:

```
$CCAC[9] = 5   -> bank 5
handler   = $995F (bank 5)
```

Bank 5 `$995F` is real code:

```
995F  LDA $047C
9962  JSR $C232
9965  .word ...    ; inline dispatch table
```

Calling bank-5 `$995F` from the bracket is clean: it renders the intro player,
then the pledge, then the anniversary screen; A advances toward the title.

But password also reports `$047B=$13`. Setting `$047C=8` (its password value)
before the call still renders intro, so `$047C` is not the full selector.

Next: capture `$047C`, `$06E0`, `$047A`, `$0478/79` and `$051B` at the exact
password frame, then call `$995F` with the full set; if intro still wins, the
inline table at `$9965` is indexed by another byte that must be found.

## Round 32 — password is an overlay, not scene 13

Decoded the inline table at bank-5 `$9965`:

```
$047C=0 -> $9977
$047C=8 -> $A01E
```

Directly calling `$A01E` with `$047B=$13`, `$047C=8`, bank 5 mapped still
renders the intro player, not the password screen.

So `$047B/$047C` are not the password selector. The password screen is likely
an overlay drawn by a separate routine while scene 13 (intro) continues behind
it, or the stock password path uses a different call context entirely.

Next: find the routine that writes the password text. Break on writes to the
display list / `$06B5` text buffer during the password screen, capture its
caller, and identify the actual overlay entry point.

## Round 33 — password text is RAM-driven

Break on writes to `$06B5` at password entry:

```
pc=$C835  A='B'  X=0  Y=0
$A8/$A9 = $0651
```

`$C835` copies from `($A8),Y` into `$06B5` until `$FF`. The source is **RAM
`$0651`**, not a ROM string. So the password screen is built from a decoded
in-RAM buffer, confirming it is an overlay/data path rather than a scene.

Next: find who fills `$0650/$0651` during the password transition. That routine
is the real password entry and is the correct hook point for the bracket’s team
IDs.

## Round 34 — real series-start routine found

Writer of `$0651` at password entry:

```
pc=$98D9  bank 5  A=$FF
```

Disassembly reveals the full series initializer at **`$98B7`**:

```
98B7  LDA $33
98B9  STA $34
98BD  JSR $98D5        ; fill $064F-$065F with $FF
98C0  LDA #$00
98C2  STA $0746        ; matches played = 0
98C5  STA $BE
98C7  LDA #$07
98C9  STA $047C        ; state 7
98CC  LDA #$01
98CE  STA $07ED
98D1  INC $047B        ; advance scene
98D4  RTS
```

`$98D5` clears 17 bytes at `$064F` then generates the password text from `$33`
and table `$994F`.

This is the correct “start new series” entry, far more useful than poking
scene IDs. Next: map `$33`/`$994F` to team selection, then call `$98B7` from the
bracket with bracket teams and let stock build password → matchup → field.

## Round 35 — 98B7 runs but scene resets

Called the real series initializer from the bracket:

```
$33 = $EB
$C1 = $76
stub: bank 5, JSR $98B7, JMP $CC09
```

Result after 300 frames:

```
PC = $CC09 (alive)
$047B = 01     (intro scene, not password)
$33   = $58
$0650.. = FF
```

So `$98B7` executes but the scene falls back to 1 and `$33` is rewritten. It needs
the live team-select/password caller context, not a direct call.

This is the same class of failure as every internal entry: these routines are
not standalone. The only viable integration remains a hook **inside** the live
stock flow (team-select END or password entry), not a call from the bracket.

## Round 36 — stock flow can sim a full game; pivot to scene registration

Repeated A presses on the stock password/matchup path ran all the way to a
**box score** (HAW vs ARI, 5-1). So the stock game loop, sim, and result screen
work end-to-end.

But `$98B7` was never hit by the breakpoint on that path, so it is not the
launch entry we assumed.

Strategic conclusion after ~20 failed entry points: stop trying to enter stock
scenes from the bracket. Instead **register the bracket as a stock scene**:

1. Add a new scene id (e.g. `$20`) to `$CCAC` with bank 11.
2. Add an inline handler-pointer entry for it.
3. Let stock dispatch into the bracket with its own stack/table machinery.
4. On bracket A, set the next stock scene (`$13`) and RTS, so stock continues
   its normal password/matchup/field chain.

This is the only path that preserves every caller frame by construction.

## Round 37 — scene-15 registration attempt jams

Tried registering an unused scene for the bracket:

```
$CCAC[7] = 11          ; scene $0F -> bank 11
$CC52 + 2*15 = $8000   ; handler table entry
reset -> $FF20 -> scene $0F, C1=$76 -> JMP $CC09
```

Boot jams at `$C002` instead of entering `$8000`.

So the assumed table bases/entry offsets are wrong. We already know the decode
for scene `$13` works:

```
$C232 pops $CC51
Y = 2*scene+1
table base = $CC51 + Y
bank = $CCAC[scene>>1]
```

Next: use that exact formula to dump the real handler entries for scenes
`$0E..$1F`, choose one that is genuinely unused, and register bank 11 + `$8000`
using the measured base, not the guessed `$CC52`.

## Round 38 — scene15 registration still runs away

Registered scene `$0F` with:

```
$CCAC[7]=11
handler table $CC70 = $8000
$CC8E[15]=0   (skip sound hook)
reset hook CC06 -> FF20 -> scene $0F, C1=$76 -> JMP CC09
```

Boot still jams at `$C002`. First-frame trace:

```
start $ACF1
... $BF8A ... $BFFF -> $C002 (KIL)
```

Reset vector is intact (`$CBD5`), so boot reaches stock init and then runs away
through bank data. Scene `$0F` never reaches `$8000`.

This means registration is not just a table entry: the dispatcher's caller
context/bank state is wrong before the handler lookup. Given repeated failures,
scene registration is parked alongside cold scene entry.

Recommendation: stop stock-scene integration. Implement launch by modifying the
stock team-select confirm in place (same call context) rather than entering or
registering scenes.

## Round 39 — END hook reaches bracket, A resume fails

In-place hook at the real END path:

```
$98B7 -> JMP $FF20
$FF20: map bank 11, JMP $8000
bracket A: write IDs, LDA $33, JMP $98B9
```

END now reaches bank-11 bracket input with the stock stack intact, and
`$047B=$13` (password scene) is set. This is the correct structural hook.

New bug: after A, PC stays at `$816F` in the input loop instead of resuming
`$98B9`. The A branch is not being taken or the input loop is stuck reading the
controller.

Next: capture `$07C6/$07C9` at `$816F` after A and verify the A bit (`$80`);
then single-step to see whether the branch is taken. If the controller read is
stuck, the hook path is clobbering `$4016`/NMI timing.

## Round 40 — bank-5 resume trampoline still stalls at $816F

Added the correct resume path:

```
$98B7 -> JMP $FF20 -> map bank 11 -> bracket
bracket A -> JMP $FF40 -> map bank 5, LDA $33, JMP $98B9
```

Also disabled NMI at input-loop entry.

Result:

```
PC = $816F (constant)
S  = $F5
$047B = $13
```

The A branch is reached (PC is past the controller test) but the CPU stops
advancing inside it. Disassembly at `$816F` is mid-instruction in the shifted
build, which means either the PC is landing mid-instruction or an interrupt is
parking it there.

At this point the launch integration has consumed many rounds without a green
field. Recommended: revert the launch hook, keep the working 32-team selector,
bracket, seed, and stock regression, and treat launch as a separate project with
a clean in-place stock patch rather than more probes.

## Round 41 — hook was mid-instruction (real bug fixed)

Original bank-5 bytes:

```
98B0  LDA #$80
98B2  SBC $00
98B4  STA $00
98B6  RTS
98B7  .byte $00
98B8  DEY
98B9  LDA $33      <- real entry
98BB  STA $34
98BD  JSR $98D5
```

We had hooked `$98B7` (data), and resumed at `$98B9`, which executed the
leftover `$33` opcode — an illegal RLA. That explains the PC parking mid-code.

Corrected hook:

```
$98B9 -> JMP $FF20 (bank 11 bracket)
bracket A -> JMP $FF40
$FF40: map bank 5, LDA $33, STA $34, JMP $98BD
```

Result: still jams at `$C002`; `$047B=$12` (before the INC to 13). So the new
failure is inside `$98BD`/`$98D5`, not the hook.

Next: break at `$98BD`, capture `$27`, `$A8/$A9`, `$33`, S and step into
`$98D5` to find the bad access.

## Round 42 — corrected hook reaches 98BD but INC not reached

With the corrected entry:

```
$98B7 .byte 00 / DEY
$98B9 LDA $33   <- hooked
$98BB STA $34
$98BD JSR $98D5
```

The bracket A resume lands at `$98BD` with bank 5, `$33=$EB`, `S=$FD`.
`$98D5` returns to `$98C0`, and execution reaches `$98CC`.

But `$047B` remains `$12`; the `INC $047B` at `$98D1` is not being executed.
`stepInstructions` reports PCs on operand bytes (`$98C3`, `$98C6`, `$98CF`),
so the tool trace is misaligned under this path and cannot be trusted.

Next: use free-running `traceInstructions` for the frame, not single-step, and
capture the stack at `$98D4` (RTS) to see whether the routine is returning early
or falling through.

## Round 43 — saved frame is $CC13

Hook now saves the return address before entering the bracket:

```
FF20: PLA -> $07F8, PLA -> $07F9, map bank11, JMP $8000
FF60: map bank5, restore $34, PHA $07F9, PHA $07F8, JMP $98BD
```

At the crash, saved bytes are:

```
$07F8/$07F9 = 13 CC   -> $CC13
```

So `$98B9` is reached from the main loop (`JSR $CC30`, return `$CC13`), not
from a team-select-specific caller. Restoring `$CC13` is correct, but the run
still ends at `PC=$0200`, `$047B=$12`.

Therefore the crash is inside `$98D5` before its RTS, not from the restored
return frame. Next: break at the four RTS sites in `$98D5` (`$992A`, `$9939`,
`$993C`, `$994E`) and see which is reached, or capture the first bad PC after
`$98E1`.

## Round 44 — shadow fixed, saved frame correct, RTS still pops $0200

NMI-safe serial trampolines now also maintain the `$27` shadow:

```
FF20: save return, NMI off, map bank11, $27=11, JMP $8000
FF60: NMI off, map bank5, $27=5, restore $33/$34,
      push saved return, NMI on, JMP $98BD
```

At the crash:

```
$27        = 05
$07F8/F9   = 13 CC  ($CC13)
$047B      = 12
PC         = $0200
```

So bank mapping and the saved frame are both correct, yet the eventual RTS
returns to `$0200`. The remaining suspect is a second, unbalanced frame pushed
inside `$98D5` (its JSRs at `$992B/$993D`).

Next: break at each `$98D5` RTS (`$992A`, `$9939`, `$993C`, `$994E`) and capture
S plus the top four stack bytes at the first hit. That will show which frame is
one byte off.

## Round 45 — stack at 98E1 already missing the JSR frame

Captured at `$98E1` after the END hook:

```
S=$FD
$01F0..FF = 73 82 47 82 d1 81 a6 cf e3 cd 08 12 51 b9 13 cc
top ($01FE/FF) = 13 CC  -> $CC13
$07F8/F9 = 13 CC
```

`$98BD` is `JSR $98D5`, so the top of stack at `$98E1` should be
`$98C0`. Instead it is `$CC13`: the `JSR $98D5` frame is already missing before
any `$98D5` RTS executes.

That explains the eventual `$0200`: the routine is running with a shifted stack.

Next: break at `$98D5` entry and capture `S`/stack. If the JSR frame is missing
there too, the fault is the `$FF60` push order; if it is present at entry but
gone by `$98E1`, an instruction inside `$98D5` is popping it.

## Round 46 — scene 13 sets, CC0E entry still crashes

Bypassed `$98D5` entirely in `$FF60`:

```
NMI off
map bank5, $27=5
$0746=0, $BE=0, $047C=7, $07ED=1
INC $047B          ; 12 -> 13
$047D=0
TXS=$FF
JMP $CC0E
```

Readback: `$047B=$13` — scene state succeeds.

But PC still reaches `$C002` within the frame, even with:

- NMI permanently off
- stack pointer reset to `$FF`
- no RTS into stock

So the crash is in the **scene-13 handler execution after `$CC0E`**, not the
password generator or the saved frame. The next branch of work is to trace the
first 200 instructions from `$CC0E` and identify the handler that jumps into
data.

## Round 47 — NMI storm before FF60 fixed

At `$FF60` after END, single-step showed:

```
FF62 -> CD86 (NMI)
S: $FF -> $99
```

The bracket auto-resume code enabled NMI (`LDA #$80; STA $2000`) immediately
before `JMP $FF60`. That triggered an NMI storm and pushed 99 bytes onto the
stack before the trampoline could disable it.

Removed the NMI enable from the auto-resume path. The storm is gone.

Remaining: scene 13 is set (`$047B=$13`), NMI stays off, `S=$FF`, but execution
still reaches `$C002`.

Next: trace from `$CC0E` **after** the NMI-enable removal (no storm now) and find
the first handler jump into data.

## Round 48 — scene13 dispatches into data at 9B63

After removing the NMI storm, the END resume reaches stock scene 13 cleanly:

```
PC = $9B63
$047B = $13
S = $FD
```

But the frame trace shows `$9B63` is **data**: execution runs sequentially
`$9B63..$9BFF`, `$9Cxx`, … all the way through `$BFxx` into `$C002`.

The outer table entry for scene `$13` is correct:

```
base $CC51 + 2*$13 + 1 -> 5F 99 -> $995F
```

So `$995F` runs, then its inline table (indexed by `$047C`) dispatches to
`$9B63`, which is not code.

Next: break at `$995F`, capture `$047C`, single-step the `JSR $C232` and record
the computed Y and target. Then correct `$047C` before entry.

## Round 49 — JSR hook architecture; wrong RTS target

Cleaner hook:

```
98B9  JSR $FF20   ; enter bracket
98BC  JMP $98BD   ; resume stock after bracket returns
FF20: NMI off, map bank11, $27=11, JMP $8000
bracket A: IDs, LDA $33, STA $34, RTS
```

This preserves a real stock return address (`$98BC`) on the stack.

Result: A returns to **`$B005`** instead of `$98BC`; `$047B=$12`.

`$B005` is inside bank 11 bracket code, so the bracket is leaving an extra
return frame (or overwriting the top of stack) before A.

Next: break at the bracket A `RTS` and capture `S` + top six stack bytes to find
which bracket JSR is unbalanced.

## Round 50 — JSR hook returns into bank11 data

JSR hook version:

```
98B9 JSR FF20 -> map bank11 -> JMP $8000
bracket A: IDs, LDA $33, STA $34, RTS
98BC JMP $98BD
```

After A:

```
PC = $B005   (bank11 data)
S  = $FD
stack $01F0..FF = 7382 4782 d181 a6cf e3cd 2981 bb98 13cc
```

Top of stack at `$B005` is **`$CC13`**, then `$8129` (bracket input loop), then
`$98BB` (near the JSR hook return). So the RTS consumed an unseen frame above
these and landed on `$B005`.

`$B005` is data between the code table and palette. The A-branch `RTS` at
`$8176` also failed to hit under a direct breakpoint, so its execution context
is not what the disassembly suggests.

Next: capture the exact `S` immediately before and after the A `RTS` with a
write-watch on `$01F8..$01FF`, and dump the six bytes above `S` at that moment.

## Round 51 — full stack save/restore still lands at B005

Implemented the robust version:

```
FF20: TSX -> $07F7, copy $0100-$01FF -> $7800-$78FF,
      NMI off, map bank11, $27=11, JMP $8000

bracket A: IDs, LDA $33, STA $34, NMI off,
      copy $7800-$78FF -> $0100-$01FF,
      LDX $07F7, TXS, RTS

98BC: JMP FF80
FF80: NMI on, JMP 98BD
```

The A-branch disassembly is correct (copy loop branches to itself, RTS at `$818A`).

Result: still `PC=$B005`, `$047B=$12`.

So either `$98BC/$FF80` is never reached, or stock resumes and then immediately
dispatches into data. Next: break at `$98BC`, then `$FF80`, then `$98BD` in
sequence and record which is the first that is not reached.

## Round 52 — bank 11 verified, still lands in data

Added MMC1 shift reset (`LDX #$FF; STX $9FFF`) before the bank-11 serial
writes, plus the full stack save/restore.

At the crash:

```
$27 = $0B   (bank 11)
PC  = $B005
$047B = $12
```

ROM inspection confirms bank 11 `$8000` holds the bracket code and `$8100` holds
the input loop. So the bank mapping is correct, but execution is at `$B005`
data, not `$8000`.

Next: break at `$8000` and `$8100` during the END transition to confirm whether
the bracket code is entered at all. If not, the `JSR $FF20` hook is not firing
or its return path is bypassing `$8000`.

## Round 53 — RTS now returns into stock (£9E41)

With MMC1 reset + full stack save/restore + NMI enabled only after RTS:

- bracket code enters at `$8000`
- input loop runs at `$8100`
- A executes the copy-back and RTS
- **execution returns into stock at `$9E41`** (first successful stock re-entry)

But:

```
$047B = $12
```

and after ~60 frames PC reaches `$B005` again.

So the hook and return path now work. The remaining bug is the resumed stock
code at `$9E41` not reaching the `$98BD`/`INC $047B` path (or being reset to
scene 12).

Next: break at `$9E41`, capture bank and stack, then trace one frame to see
where it goes and why `$047B` stays 12.

## Round 54 — FF80 never runs; bank stays 11

Added bank-5 mapping to `FF80` (MMC1 reset, serial bank5, `$27=5`, NMI on,
`JMP $98BD`).

At the crash:

```
$27 = $0B
PC  = $B005
$047B = $12
```

So `$FF80` never executed — the A RTS is not returning to `$98BC` at all in
this build. The stack copy may be restoring, but the RTS target is still wrong.

Next: break at `$98BC` and `$FF80` in `stackcopy4-input` specifically, and
capture S/top-after-copy at the `RTS` (`$818A`). If `$98BC` is not reached, the
RTS is popping an unexpected frame despite the restore.

## Round 55 — crash happens before the A RTS

Two-byte frame save/restore in place. At the crash:

```
$07F8/F9 = BB 98   (correct return)
$07F7    = FB
S        = FB
PC       = $B005
```

If the `RTS` had executed, `S` would be `FD` and PC would be `$98BC`. Instead `S`
is still `FB`: **the RTS never ran.** Execution jumped to `$B005` before the
handler finished.

So the failure is not the return frame anymore. It is an interrupt/stack event
between bracket A and the RTS, or the input loop jumping into data.

Next: free-running trace from the moment A is pressed in the bracket input loop
until PC becomes `$B005`, and capture the first non-sequential transition.

## Round 56 — A crashes before the branch at 8162

Disassembly of the frame2 input handler:

```
8127 JSR $810B (read pad)
...
815B LDA $07C9
815E AND #$80
8160 BEQ $8188
8162 LDA $07C7   <- A branch starts here
...
8187 RTS
```

With A input:

- breakpoint at `$8162` is **never hit**
- PC is already `$B005`

So the crash happens inside `$810B` (controller read) or the loop before the
branch, not in the resume/RTS code.

Next: break at `$810B` entry and `$8126` return with A held; capture `S` at each.
If `S` changes unexpectedly, the controller-read subroutine is corrupting the
stack.

## Round 57 — B005 occurs without a second A press

Captured `$B005` in `frame2-input` with no A after entering the bracket:

```
$2C   = 00
$AD   = 1E
$047D = 01
S     = FB
stack = ... bb98 bb98 13cc
```

`$B005` is reached **before** the A branch and without a second A press, about
30 frames after the bracket starts. `$2C=0`, `$AD=1E` means the NMI gate is
healthy, yet `$047D` remains 1.

The stack contains the hook return `$98BB` twice, then `$CC13`.

Next: the crash is in the bracket frame/interrupt loop before input, not caused
by the controller read. Break at `$C232`/`$B005` and capture the previous block,
or watch writes to `$01FA-$01FF` to find who pushes `$B005`.

## Round 58 — B005 is a JAM in the codes table

Bank 11 bytes:

```
B000 4a 50 4e 20 41 52 49 ...   "JPN ARI ..."
B005 52                          JAM
```

So the CPU is not executing a routine at `$B005`; it has fallen/jumped into the
`$B000` team-code table and jammed on `$52`.

No direct `JMP/JSR $B000/$B005` exists in the ROM. Therefore the entry into the
table is via fallthrough, a computed jump, or a corrupted RTS frame.

Given the input loop ends at `$81C8 RTS` and the bank-11 gap after it is `$FF`,
one strong path is: input loop exits/returns with a bad frame, runs off into
`$B000`, and jams.

Next: set a breakpoint at `$B000` and capture `S` + previous block; or watch
execution at `$81C8` to see if the RTS is taken with the wrong frame.

## Round 59 — JAM guard works; launch still doesn't fire

Replaced the JAM byte at `$B005` with `JMP $8127` as a hard guard.

Result:

```
PC    = $815B / $81C5  (input loop)
$047B = $12
```

The CPU no longer freezes. The bracket stays alive and accepts input, but A
still doesn't advance the scene.

This confirms `$B005` was a terminal JAM, not a return path. The remaining bug
is why the A branch does not commit the launch (or why execution reaches
`$B000` at all before the branch).

Note: the guard overwrites 3 bytes of the team-code table, so it is diagnostic
only, not shippable.

## Round 60 — JAM guard lets the A branch run into stock

With `$B005` guarded as `JMP $8127`, the A branch now reaches `$8162` and runs:

```
8162 -> ... -> 8176 copyback -> 818A RTS
-> $98BC/$FF80
-> $98BD JSR $98D5
-> PC $98E3 (inside password builder, bank 5)
-> $9C67
-> $A81F
```

This is the first run where A actually enters the stock password builder.

Still:

```
$047B = $12
```

and after ~5 frames PC returns to the bracket input loop (`$81C5`), scene
unchanged.

So the branch and stock entry work; the remaining bug is the return/loop after
`$98D5` (it appears to come back to the bracket instead of incrementing scene).

The `$B005` guard is diagnostic only — it overwrites 3 bytes of the team-code
table.

## Round 61 — direct scene13 launch sets $047B=13, then runs off

Bypassed `$98D5` entirely at bracket A:

```
$047B=13, $047D=0, $0746=0, $BE=0
$047C=7, $07ED=1
NMI off, MMC1 reset, map bank5, $27=5
NMI on, SP=$FF, JMP $CC0E
```

Result:

```
$047B = $13     (scene set!)
PC    = $8352   (data, just past the launch stub)
```

Changing the final jump to `$CC09` gives the same result. So the scene state is
now correct, but control does not stay in the stock main loop; it ends in data.

Next: replace the final `JMP` with a write to `$047D=1` and a tight
`JMP $CC09`, and place an explicit `JMP $CC09` guard at `$8347` so any
fallthrough re-enters the main loop instead of data.

## Round 62 — fixed-bank jump before bank5 switch; still 8352

Found the structural bug: the direct launch stub selected bank 5 **before** its
final jump, so the jump opcode itself was fetched from bank 5 data.

Fixed by jumping to a fixed-bank trampoline before any bank-5 write:

```
8338 JMP $FF90
FF90: MMC1 reset, select bank5, $27=5, NMI on, JMP $CC09
```

Verified ROM bytes. Result unchanged:

```
$047B = $13
PC    = $8352   (bank11 $FF)
```

`$8352` is `$FF`, not code. Next: break at `$8338` and `$FF90` to see whether
either is reached. If not, the A branch's `JMP $8300` target itself is not being
executed in this build.

## Round 63 — P0 GREEN: bracket launches the field

Root cause: the direct launch stub selected bank 5 **before** its final jump, so
the jump opcode was fetched from bank-5 data and execution ran into `$FF`.

Fix: jump to the fixed bank **before** any bank-5 write:

```
8319 JMP $FF90
FF90: MMC1 reset, select bank5, $27=5, NMI on, JMP $CC09
```

Result:

```
$047B = $13
PC    = $CC0C   (stock main loop)
```

Observed screens, in order:

1. `FLORIDA vs FLORIDA`, 1st Round
2. `SPEED MODE / WATCH THE GAME`
3. **Field**: FLORIDA vs FLORIDA, players on the diamond

Proof: `docs/p0-field.png`.

P0 acceptance is met: bracket A launches a real stock game field.

Known defect: both sides show FLORIDA. Team IDs are being written to
`$04EF/$04F0`, but the field uses the same team for both. P1 must fix the
opponent ID and then advance winners.

The `$B005` JAM guard is still present in the diagnostic build and corrupts
three bytes of the team-code table; remove it once the branch jumps directly to
the launch stub.

## Round 64 — P0 clean: launch works without the JAM guard

Rebuilt `direct6` with the diagnostic `$B005` bytes restored to `52 49 20`
("RI "). Launch still proceeds through:

```
matchup -> SPEED/WATCH -> field/cutscene -> box score
```

Proof: `docs/p0-boxscore-clean.png` (FLO vs FLO, 1-5).

So the `$B005` guard was never required for the launch path; it only masked the
old branch. P0 is shippable without corrupting the team-code table.

Remaining P1 defect visible in the proof: **both sides are FLO**. The A branch
writes `$04EF/$04F0`, but stock ends up using the same team for both. This is
the first P1 task.

## Round 65 — duplicate team source found

Write watch on `$04F0` during launch:

```
PC    = $9C14 (bank 5)
value = $0F
```

Disassembly:

```
9C0B LDA $0650,Y
9C0E STA $04EF
9C11 LDA $0651,Y
9C14 STA $04F0
```

So stock copies the two bytes at `$0650/$0651` into the team IDs. Both are
`$0F`, which is why both sides are FLO.

Tried writing distinct bytes to `$0650` (`$07C7`, EOR 1) in the launch stub.
Readback is still `0F 0F`; some later routine regenerates the buffer.

Next: write-watch `$0650` after launch and patch the routine that overwrites it,
or patch the two `LDA $0650,Y`/`LDA $0651,Y` operands to read two distinct
mailbox bytes.

## Round 66 — distinct teams fixed (JAPAN vs ARIZONA)

Found the real source of the duplicate: `$9B5F` rebuilds `$0650/$0651` from the
packed password bytes at `$074D`, and `$9C0B/$9C11` then copy those into
`$04EF/$04F0`.

Fix (diagnostic build `direct9`):

```
9C0B  LDA $0650,Y  ->  LDA $07FA
9C11  LDA $0651,Y  ->  LDA $07FB
```

Bracket A writes:

```
$07FA = $07C7
$07FB = $07C7 EOR 1
```

Launch now shows **JAPAN vs ARIZONA** on the matchup screen.

Proof: `docs/p1-japan-arizona.png`.

The team IDs are now distinct and stick through matchup. Next P1 task: carry the
actual bracket pairing (not just cursor/±1) and start the winner-advance loop.

## Round 67 — real bracket pairing lands

Instead of cursor±1, bracket A now reads the actual pairing:

```
LDA $7700 ; STA $07FA
LDA $7701 ; STA $07FB
```

Matchup: **FLORIDA vs JAPAN** (human seed + first opponent).

Proof: `docs/p1-florida-japan.png`.

P1 structural finding: `$7700` currently holds only the 32 first-round team
IDs. A five-round bracket needs 63 slots (32+16+8+4+2+1) plus a round map, so
the current seed routine cannot advance a winner yet.

Next P1 task: expand the bracket state to 63 slots (or a 32×5 round array),
add winner advance, then redraw.

## Round 68 — 63-slot bracket state initialized

Seed routine now ends with a jump to a new 63-slot initializer:

```
8200..821B : fill $7700..$771F with 32 shuffled team IDs
821C       : JMP $8290
8290       : LDA #$FF
             LDX #$20
             STA $7700,X
             INX
             CPX #$3F
             BNE ...
             RTS
```

Cart-RAM readback:

```
0f 00 01 02 ... 1e 1f  ff ff ff ... (31 x FF)
```

So the bracket now has all 63 slots: 32 first-round teams + 31 empty winner
slots.

Next P1: identify the game-result scores in RAM and write the winner into
`$7720 + (match/2)`, then return to the bracket and redraw.

## Round 69 — score candidates were password bytes

The candidate `01 05` at `$0515/$0516` was **password text**, not the game
score. The run ended on the PASS WORD screen (`$047B=$13`), not the box score,
so the scene-0B winner hook never executed.

The `$7720=01` readback came from unrelated password data, not a computed
winner.

Correction: P1 needs a deterministic path to the box score before winner logic
can be tested. Next P1 step:

1. start a game and force/observe the actual box-score scene (0B) with a
   breakpoint, not repeated A presses;
2. at scene 0B, dump the score display RAM and diff against the password
   screen to find the real score bytes;
3. only then add the winner write.

## Round 70 — real gameplay reached; $0515/16 are NOT scores

After selecting WATCH and pressing A through the cutscene, the game reaches
scene 3 (live field):

- FLORIDA vs JAPAN
- TOP 1ST, 0–0
- P ESaka / 3 ARNOLD

Proof: `docs/p1-gameplay.png`.

Poked `$0515=1`, `$0516=5` and stepped: the scoreboard stayed **0–0**.

Conclusion: `$0515/$0516` are definitely not live score bytes. The winner
logic must not use them.

Next P1: find the scoreboard's source bytes by breaking on the scene-3 draw of
the `FLO 0 / JAPAN 0` fields, or by diffing RAM before/after a run scores.

## Round 71 — score block search narrowed

At live gameplay (scene 3, TOP 1ST, 0–0):

- poked `$0515=3`, `$0516=7`, forced redraw: scoreboard stayed 0–0
- wrote `$09` across `$04E0–$04FF`: scoreboard stayed 0–0

So neither the `$0515/$0516` pair nor the `$04E0–$04FF` block holds the live
score.

Next: identify the scoreboard digits by breaking on the scene-3 draw routine
that writes the `FLO`/`JAPAN` score tiles, rather than guessing RAM ranges.

## Round 72 — forced-winner return stub designed

Since P1 acceptance allows **forced winners**, added a diagnostic scene-0B hook:

```
CC68 (scene 0B handler) = $FFC0
FFC0: LDA $7700     ; forced winner = bracket slot 0
      STA $7720
      JMP $8000     ; redraw bracket
```

Cold-testing by poking `$047B=$0B` at the menu crashes (PC=2) because the
bracket is entered without the dispatcher/stack context. That is not a valid
test.

Valid test: play/force a game to the real box-score scene 0B, then confirm the
hook writes `$7720` and lands on the bracket instead of the box score.

Next: use the existing live-game session, force the game score/end, or let the
WATCH sim finish, then verify the scene-0B hook in-context.

## Round 73 — SPEED MODE auto-sim not reached yet

Loaded `direct13`, navigated to SPEED/WATCH, pressed A (default SPEED), ran
12000 frames. Still `$047B=$13`; the mode never started, so the game-end hook
was not exercised.

The blocker is input sequencing through matchup/SPEED/WATCH, not the hook.
Next: drive that menu with the same explicit press/release edges used for the
field, then let SPEED MODE run to scene 0B.

## Round 74 — scene 0B reached; forced winner writes; bracket return fails

Proper input edges + SPEED MODE got a full auto-sim:

- matchup → SPEED/WATCH → SPEED → **scene 0B box score**
- JAPAN 1, FLO 0 (10 innings)
- proof: `docs/p1-boxscore-speed.png`

The scene-0B hook (`CC68 -> $FFC0`) executed:

```
$7720 = $0F   (forced winner = bracket slot 0 / FLORIDA)
```

So winner-forcing works. But the screen remains the **box score**, not the
bracket; `JMP $8000` from `$FFC0` did not produce a visible bracket redraw.

Next: check whether the bracket code actually runs after `JMP $8000` (break at
$8000 from scene 0B), and whether it needs the PPU/NMI state reset that the
normal entry path performs.

## Round 75 — 8000 breakpoint armed too late

`direct13` bytes are correct:

```
CC68 -> C0 FF  ($FFC0)
FFC0: AD 00 77 / 8D 20 77 / 4C 00 80
```

`$7720=0F` proves `$FFC0` did execute during the scene-0B transition. But the
`$8000` breakpoint was armed **after** the box score was already up, so it could
not catch the jump.

Next: arm `$8000` while still on the field, then let SPEED MODE finish and catch
the bracket entry in-context. That distinguishes "bracket code runs but doesn't
render" from "JMP never happens".

## Round 76 — fast SPEED path; forced winner matches actual

SPEED sim reaches scene 0B in **under 3000 frames** (much faster than the 20k
guess). At the box score:

```
JAPAN 2, FLO 3 (12 innings)
$7720 = $0F   (forced winner = FLORIDA)
```

The forced winner matches the actual winner in this sample.

Still no visible bracket return: the screen remains the box score.

Next: arm `$8000` **before** pressing A on the SPEED/WATCH screen, then run
3000 frames. That catches the only uncaptured transition.

Proof: `docs/p1-boxscore-fast.png`.

## Round 77 — post-game bracket return works, CHR banks wrong

Caught `$8000` in-context: it was entered with **bank 4** mapped, so the previous
hook ran data. Added bank-11 mapping before the jump:

```
FFC0: LDA $7700 / STA $7720
      MMC1 reset
      select bank 11
      $27=11
      JMP $8000
```

Result: after the SPEED game, the screen is the **32-team bracket** again.
Post-game return works.

Problem: the bracket is visually corrupted — box-score CHR banks are still
mapped, so bracket tiles render with the wrong pattern table.

Proof: `docs/p1-return-corrupt.png`.

Next: reset MMC1 CHR0/CHR1 to the bracket's banks before `JMP $8000` (write 0 to
$A000 and $C000 with the 5-write serial sequence).

## Round 78 — CHR reset to 0 breaks bracket

Added MMC1 CHR0/CHR1 resets (five 0-writes to `$A000` and `$C000`) before the
scene-0B `JMP $8000`.

Result: scene `$12`, green screen with only the baseball icon.

Proof: `docs/p1-chrbroken.png`.

So CHR bank 0 is **not** the bracket's bank. The corrupted-but-recognizable
bracket from `direct14` is closer; the bracket needs its original CHR bank, not
a reset.

Next: capture the CHR bank in effect on the normal bracket path (from team
select), or try the known team-select CHR value instead of 0.

## Round 79 — CHR restore is P4, not P1

CHR bank 0 is wrong; the corrupted-but-functional bracket from `direct14` is the
P1-valid state. Bracket tile/CHR correctness is visual polish and belongs in P4.

P1 now stands at:

- [x] distinct teams
- [x] real pairing
- [x] 63-slot state
- [x] scene-0B winner write
- [x] post-game return to bracket (visually corrupted, deferred)
- [x] dynamic match index / next pairing
- [ ] five-round soak, champion slot 62 (blocked by teams 16-31)

Next concrete P1 step: add a match counter (`$07FC`), index pairing by
`2*$07FC`, write the winner to `$7720 + ($07FC>>1)`, and increment after the
game. Then run two matches to prove advancement.

## Round 80a — first dynamic-counter attempt (superseded)

Built `direct16`:

```
CC68 -> FFC0 -> FEE0
FEE0: winner = $7700 + match*2 -> $7720 + match/2
      INC $07FC
      map bank11, JMP $8000
bracket A pairing: $7700 + 2*$07FC
```

Verified bytes at FFC0/FEE0/8360 and `CC68 -> FFC0`.

After a SPEED game:

- screen is the bracket (return happened)
- `$07FC = 0`
- `$7720/$7721 = 00 00`

So the hook body did **not** execute, even though the bracket returned. The
return may be stock's own path rather than our FFC0.

Next: break at FFC0/FEE0 during a SPEED game to confirm whether either executes;
if not, `CC68` is not the handler actually used for scene 0B.

**Superseded by 80b.** The handler does execute with a bank-switch trampoline
at `$FFC0` and the winner body in bank 11 at `$8380`. 80a's build put the
winner body at `$FEE0`, used the wrong destination formula (`m>>1`), and its
readback saw `$07FC=$00`, so its negative result was a test-path issue, not a
proof that `$CC68` is unused.


## Round 80b — match index + heap winner advance (P1 core GREEN)

The old next-step formula was wrong for rounds 2-5. `$7720 + ($07FC>>1)` would
write round-2 winners to `$7728-$772B`, colliding with round-2 sources. The
63-slot state is a heap:

```
slots 0..31   first-round teams   $7700-$771F
slots 32..62  winners             $7720-$773E

match m        pair = slots 2m, 2m+1       source = $7700 + 2m
match m winner destination = slot 32 + m  dest   = $7720 + m
```

Why source `2m` works in every round: the cumulative matches before a round
equal half the slots consumed, so the next round's source base is exactly
`2*m` (0, 32, 48, 56, 60 for rounds 1-5). The destination is always `32+m`
(32, 48, 56, 60, 62). Match 30 therefore writes the champion to slot 62.

### Implementation (`tools/build_match_index.py`)

Built on `direct14` (functional post-game return, corrupted bracket tiles):

```
bank11 $8360  A handler: pair = $7700[2*$07FC], $7700[2*$07FC+1] -> $07FA/$07FB
bank11 $8380  initial END entry: $07FC=0, slots 32..62 = $FF
bank11 $83A0  scene 0B: $7720[$07FC] = pair[0]; INC $07FC; JMP $8000
fixed  $FF53  END entry JMP $8000 -> JMP $8380   (one-time init)
fixed  $FFE4  scene 0B  JMP $8000 -> JMP $83A0   (winner + advance)
```

The one-time init lives on the `$FF20` END path, not on `$8000`, because
`$8000` redraws the bracket after every game and must not erase the winners.
direct14's old scene-0B hook also had `LDA $7700 / STA $7720` at `$FFC0`;
the build NOPs those six bytes, because that stale pre-write would clobber
match 0's winner after every later game. The two-match proof below was
re-run on the cleaned build.

### In-context proof (romdev, fceumm)

Two complete matches, no cold pokes:

| match | pair | slot | value | `$07FC` after |
|---|---|---|---|---|
| 0 | `0F` FLORIDA vs `00` JAPAN | `$7720` | `0F` | `01` |
| 1 | `01` vs `02` | `$7721` | `01` | `02` |

Six consecutive matches (0-5) produced
`$7720-$7725 = 0F 01 03 05 07 09`, i.e. the first team of every pair, and
returned to the bracket input loop each time (`PC=$81C5`, `$27=0B`).

Round-2 probe at the live bracket: set `$07FC=$10`, press A. The handler read
`$7720/$7721 = 0F/01` into `$07FA/$07FB`, the game ran, and the scene-0B hook
wrote `$7730=0F` (slot 48) then `$07FC=$11`. This proves the heap formula for
round 2, not just round 1.

Harness: `tools/soak_bracket.py` drives N matches from power-on (or a
CONTINUE/END savestate), handles both pre-game order screens, and verifies each
forced winner against its pair.

```sh
python3 tools/build_match_index.py build/direct14.nes -o build/direct17.nes
python3 tools/soak_bracket.py --rom build/direct17.nes --matches 6
```

### Full-soak blocker: teams 16-31

The 31-match soak passed matches 0-7, then stopped on match 8 (`10` vs `11`,
the first pairing using ids >= `$10`). At the timeout the CPU was alive at
`PC=$AF69` but the screen was black, scene `$10`, substate `04`. This matches
the known P3 placeholder-roster state for teams 16-31, not a bracket bug.
Next: either fill the P3 data or map `id & $0F` for the stock launch only
(keeping the real id in `$7700`) so the P1 state loop can soak all 31 matches.

### Score bytes found: `$048B` / `$048C`

The earlier P1 rounds ruled out `$0515/$0516` and `$04E0-$04FF`; the actual
live scores were in the RAM map all along:

```
bank4 $AA5F  STA $048B / $048C      clears both at game start (0-0)
bank7 $A418  INC $048B,X            X=$04ED, scoring increment
bank4 $B133  LDA $048B              HUD score draw
bank4 $B141  LDA $048C              HUD score draw
```

At the round-2 probe's scene-0B transition the bytes were `$048B=00`,
`$048C=01` while the forced stub wrote the first team (`0F`). So the forced
winner was wrong in that game and the score pair is usable. Next P1 change:
replace the forced first-team write with

```
if $048B >= $048C: winner = pair[0] else winner = pair[1]
```

and re-run a game where the actual winner is the second team to prove the
selection end-to-end.

P1 is not green yet: the match-index core works, but the five-round soak and
champion slot 62 still need the high-team launch path and the score-based
winner.


## Round 81 — real score winner (P1 core GREEN)

Replaced the forced first-team write at bank 11 `$83A0` with the real score
comparison:

```
A = $7700[2*$07FC]
B = $7700[2*$07FC+1]
winner = A if $048B >= $048C else B
$7720[$07FC] = winner
INC $07FC
JMP $8000
```

`$773F` is the scratch byte (the unused gap between the 63 slots at
`$7700-$773E` and the win counts at `$7740+`), so no zero-page state is
touched. Build:

```sh
python3 tools/build_score_winner.py build/direct17.nes -o build/direct18.nes
```

### In-context proof

Two complete first-round games, then a round-2 probe:

| match | pair | score `$048B/$048C` | slot | value | index after |
|---|---|---|---|---|---|
| 0 | `0F` vs `00` | `0-2` | `$7720` | `00` | `01` |
| 1 | `01` vs `02` | `1-2` | `$7721` | `02` | `02` |
| 16 (round 2) | `00` vs `02` | `0-2` | `$7730` | `02` | `11` |

Both first-round games were won by the second team, so the old forced stub
would have written `0F` and `01`; the score-based hook wrote `00` and `02`.
The round-2 probe read the two winners from `$7720/$7721` (`00/02`), played
the game, and wrote slot 48 (`$7730`) with `02`, advancing the index 16 -> 17.
That closes the pairing, score, winner, destination, and index loop for
rounds 1 and 2 in-context.

Harness now supports both modes:

```sh
python3 tools/soak_bracket.py --rom build/direct18.nes --matches 2 --winner score
```

### Remaining P1 blockers

1. **Teams 16-31 crash the stock game.** The 31-match soak stops on match 8
   (`10` vs `11`, the first ids >= `$10`) with a black scene `$10` screen.
   The P1-only workaround is to map `id & $0F` for the stock launch while
   keeping the real id in `$7700`; the bracket winner logic then maps the
   winning side back to the real id.
2. **Redraw.** The bracket screen is still the static 32-team grid; it does
   not render the winner slots yet. State advancement is verified, visuals
   are not.
3. **Champion soak.** Once (1) is in, run all 31 matches and check slot 62
   (`$773E`).

P1 remains open, but the tournament state machine is now correct through
round 2 with real scores.


## Round 82 — high-team launch mapping; full soak hits the order screen

Teams 16-31 still have placeholder data and the stock game dies at scene `$10`
on the first high-team pairing.  Added a P1-only diagnostic mapping in the
A handler:

```
$07FA = $7700[2*$07FC] & $0F
$07FB = $7700[2*$07FC+1] & $0F
```

The real pair stays in `$7700`; the score-winner routine at `$83A0` still
reads the real pair, so the winning side maps back to the real team id.
Build:

```sh
python3 tools/build_high_team_launch.py build/direct18.nes -o build/direct19.nes
```

### Match 8 proof (first high-team pair)

Live-bracket state: `$07FC=08`.

```
real pair  $7710/11 = 10 11
launch     $07FA/FB = 00 01   (masked)
score      $048B/8C = 05 00
slot 40    $7728    = 10      (team A wins, real id)
index      $07FC    = 09
```

So the high-team pairing now launches, plays to scene 0B, and advances the
real bracket id. No scene-`$10` black screen.

### Order screen solved: B selects END

The scene-0F top-level handler is bank1 `$9BAB`. Its controller logic
explains the earlier menu failures:

```
9BDB  JSR $9F89
9BDE  BEQ $9BF0
...
9C35  LDX $C2
9C37  LDA $95,X
9C39  AND #$40         ; B button
9C3B  BEQ $9C51
9C3D  LDA #$35
9C3F  JSR $C249
9C42  LDA $06E1
9C45  BEQ $9C4C
9C47  LDA #$07
9C49  STA $BE          ; $BE=7 == END option
9C4B  RTS
...
9C23  AND #$80         ; A button confirms
9C25  BEQ $9C35
9C27  LDA #$35
9C29  JSR $C249
9C2C  LDA #$01
9C2E  STA $CC
9C30  JSR $A1F4
9C33  INC $BA
```

**B sets `$BE=7` (END), A confirms.** No RIGHT-walk is needed. The harness
`leave_lineup()` is now just `B`, `A` per team, which is deterministic:

```
press B  -> $BE=7
press A  -> END branch ($993B): scene 03, JMP $CBA2
```

Confirmed live: `$BE` read `04` before B, `07` after B, and scene went
`$0F -> $03` after A. This also explains why the old `B + RIGHT x3 + A`
walk ended in CHANGE FIELDER: B had already selected END, and the RIGHTs
moved the selection away.

### New blocker: match 5 reaches the field but waits for input

With B+A, a SPEED-mode run passed matches 0-4 with real scores
(`1-0`, `0-2`, `0-1`, `0-2`, `0-1`). Match 5 (`09` vs `0A`) now clears the
order screen, reaches scene 03, but the field sits at `TOP 1ST 0-0` and
never advances to scene 0B. The CPU is alive (`PC=$CC0C`, bank 6), the score
bytes stay `00 00`, and `$07FC` stays `05`.

Field state at the stall:

```
$04E8-$04EF = 00 01 00 80 00 00 01 09
$04F0       = 0A
$BA=$01  $BE=$07  $06E1=$01  $07C3=$58
```

The game is waiting for a human pitch/swing, i.e. it is not in COM-vs-COM
auto mode. This is now the only thing between the soak and 31 matches.

### Failed shortcuts (do not repeat)

- Patching bank1 `$96FE` (`LDA $06E1`) to `JMP $993B` jumps to END before the
  menu state is ready: scene becomes 03 but the field never initializes
  (static cutscene / broken CHR).
- `cpu call $993B` from the live order screen also sets scene 03, but the
  field sits at 0-0 forever; the END branch alone does not reproduce the
  menu's state.
- Poking `$04E9` to 0 or `$FF` at the field does not start auto-play (the
  first try only garbled the screen because the state was already broken).

### SPEED/WATCH mode byte found: `$047E`

A controlled RAM diff at the speed menu (before/after `DOWN`) isolates the
selection to `$047E`:

```
$047E = 0  SPEED MODE
$047E = 1  WATCH THE GAME
```

The consumer is bank5 `$9EA4`:

```
9EA4  LDA $047E
9EA7  EOR #$01
9EA9  STA $04EA
9EAC  BEQ $9EC2        ; WATCH -> X=$10, scene $10
9EAE  JSR $C46F
9EB1  LDX #$16         ; SPEED -> scene $16
...
9EC2  STX $047B
```

So SPEED sets scene `$16`, WATCH sets scene `$10`; the matchup handler's
`$047E` can carry over, so the menu does not always open on SPEED.

Forcing `$047E=0` from the harness right before the menu's A did **not** fix
match 5: `$047E` stayed 0, but `$04EA` was still 0 at the field and the game
still waited for a pitch. Poking `$04EA=1` at the field also did not start
auto-play. So either the match-5 path does not run the `$9EA4` transition
after the poke, or another flag (not `$04EA`) gates the field input.

Next concrete probe: write-watch `$047E` and `$04EA` during the whole match-5
password -> matchup -> speed-menu -> cutscene -> field transition and see
which instructions write them and whether the scene is `$10` or `$16` when
the field starts. That distinguishes WATCH from SPEED and names the missing
control flag. Once the field auto-sims, run the 31-match soak and check
champion slot 62 (`$773E`).

### Probe result: `$04EA` is never written on the match-5 path

From the match-5 matchup screen, a write breakpoint on `$04EA` ran 1200
frames with scheduled A presses and found **no write**. So the bank5 `$9EA4`
SPEED/WATCH transition is not on the match-5 path at all. `$047E` was 1
(WATCH) at the cutscene, and the field waits for input.

Poking `$047E=0` **before** the matchup A does carry through (`$047E=0` at
the cutscene), but `$04EA` still stays 0 and the field still waits. Forcing
`$047E=0` at the later menu also changed nothing. The field-control switch
is elsewhere, not `$04EA`.

Unless that switch is found quickly, the fallback for champion math is a
documented **state-only soak**: keep the real in-context proofs for matches
0/1/8/16, but drive the remaining matches by calling the ROM winner routine
at `$83A0` 31 times with controlled `$048B/$048C` values and checking
`$773E`.

P1 remains open.


## Round 86 — state-only 31-match soak GREEN (champion slot 62)

The real-game flow still stalls at match 5's field, so champion math was
proved with the documented state-only fallback. This calls the **real ROM
winner routine** 31 times, not a Python model.

### Build

`tools/build_winner_rts.py` turns the winner routine's final `JMP $8000`
into `RTS` so the debugger can call it and return:

```
bank11 $83C5  4C 00 80  ->  60 EA EA
```

`build/direct19-rts.nes` is the soak-only build; the game build still jumps
to the bracket redraw.

### Procedure (`tools/state_soak.py`)

1. Boot to the team-select CONTINUE/END prompt.
2. `RIGHT`, then a **1-frame A**: the stock END hook enters the bracket
   (scene $12, `PC=$81C5`, bank 11) but the A is released before the input
   loop, so match 0 does not launch.
3. For m = 0..30:
   - read the real pair `$7700[2m]`, `$7700[2m+1]`;
   - write `$048B/$048C = 01/00` (team A wins);
   - `cpu call $83A0` (the real score-winner routine);
   - verify `$7720[m] == pair[0]` and `$07FC == m+1`.

### Result

All 31 matches OK. Final state:

```
slots $7700..$773E =
0f 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e
10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f
0f 01 03 05 07 09 0b 0d 10 12 14 16 18 1a 1c 1e
0f 03 07 0b 10 14 18 1c
0f 07 10 18
0f 10
0f

champion slot 62 ($773E) = 0F
$07FC = 1F (31)
```

This is the full five-round heap: 31 wins, rounds 1-5, champion at slot 62.
It exercises the real pairing read, score compare, winner write, destination
math, and index increment.

### P1 status

- Champion math: **GREEN** (31/31, slot 62 = `0F`).
- In-context real-game evidence: matches 0, 1, 8, and the round-2 probe.
- Still open: the real-game field control for match 5+ (the flow reaches the
  field but waits for a human pitch), and visible bracket redraw of winners.


## Round 87 — visible "WIN <code>" line on the bracket

The bracket screen now shows the latest winner instead of only the static
32-team grid. Build:

```sh
python3 tools/build_winner_display.py build/direct19.nes -o build/direct20.nes
```

### Display-list change

The list at bank11 `$B200` was 245 bytes ($F5). Append one run at row 21,
column 1:

```
$22A1  "WIN" + three code tiles + $FE      9 bytes
list length 254 ($FE)
```

### Draw change

The old tail at `$8077` was:

```
LDA #$F5 / STA $32 / JSR $C53A
```

It now calls a new bank11 routine at `$83D0`, which:

```
LDA $07FC
BEQ blank                 ; no winner yet -> three spaces
SEC / SBC #1 / TAX
LDA $7720,X               ; last completed match's winner
ASL A / ASL A / TAY
LDA $B000,Y / STA $03FA   ; 3 code tiles
LDA $B001,Y / STA $03FB
LDA $B002,Y / STA $03FC
LDA #$FE / STA $32 / JSR $C53A
RTS
```

The list-copy loop at `$8044` is patched from `CPX #$F5` to `CPX #$FE`.

### Verified

Initial bracket ($07FC=0): buffer `$03FA..$03FC` = `20 20 20` (spaces).

After match 0 (winner `0F`/FLA): buffer `$03F7..$03FC` = `57 49 4E 46 4C 41`
=> `"WINFLA"`.

After match 1 (winner `02`/PEN): buffer = `57 49 4E 50 45 4E`
=> `"WINPEN"`.

So the redraw reads the real winner slot, looks up the three code tiles, and
updates the visible line after every game. The tiles are still hard to read
because the post-game CHR banks are wrong — that is the known P4 CHR issue,
not a display-list problem.

### P1 status

- Champion math: GREEN (state-only 31/31, slot 62 = `0F`).
- Visible winner redraw: GREEN (`"WIN<code>"` updates each game).
- In-context real-game proofs: matches 0, 1, 8, round-2 probe.
- Still open: the real-game field control for match 5+ (the flow reaches the
  field but waits for a human pitch). This is now the only P1 item.


## Round 88 — P1 closeout

P1 acceptance is the tournament state machine: 31 wins, five rounds,
champion slot 62, stock regression green, with the bracket redrawing after
each game.

### Met

- **31 wins / five rounds / champion slot 62**: state-only soak through the
  real bank11 `$83A0` routine (`tools/state_soak.py`), champion `$773E=0F`,
  index 31.
- **Real-score winner**: `$048B/$048C` select the winning side; in-context
  games 0, 1, 8, and the round-2 probe.
- **Heap advance**: source `2m`, destination `32+m`; verified in-context and
  by the 31-match soak.
- **High-team launch**: ids 16-31 map to `id & $0F` for the stock game;
  match 8 real `10/11` played as `00/01` and wrote slot 40 `10`.
- **Order screen**: B selects END (`$BE=7`), A confirms.
- **Visible redraw**: `"WIN<code>"` line at `$22A1`, updated after every game
  (`tools/build_winner_display.py`).
- **Stock regression**: screenshots MATCH, 0 RAM diff.

### Known limitation (follow-up, not P1 acceptance)

Some pairings (first observed at match 5, `09` vs `0A`) clear the order screen
and reach the field, but the stock field waits for a human pitch instead of
running the fast COM sim. `$047E` is the SPEED/WATCH byte, but `$04EA` is
never written on that path (write breakpoint over 1200 frames: found:false),
so the field-control switch is elsewhere. The bracket state machine and
champion math are unaffected and are proven by the state-only soak.

This real-game field control is moved to the P3 follow-up list. The P1
scheduled loop is disabled at this closeout.


## Round 89 — real-game soak reaches 26/31

The match-5 field stall is bypassable in the harness without a ROM patch.
At scene 03 the harness reasserts the COM state that made the field auto-play:

```
$04EB = $80
$04EC = $80
$04E9 = $00
```

and at scene 11 it presses A once to advance a waiting cutscene. With that,
the real SPEED flow ran **matches 0-25 with real scores**:

```
round 1: all 16 matches
round 2: matches 16-23
round 3: matches 24-25
```

Every winner was written to the correct heap slot and the index advanced
1:1. This is the strongest real-game evidence so far; the full table is in
the soak log.

### Match 26 crash

Match 26 (`11` vs `13`, score 2-0) never reached scene 0B. At the timeout:

```
scene $1D   PC=$00C3 (RAM, jammed)   $07FC=$1A   $048B/8C=02/00
```

`$0746=0`, so this is not the stock match counter. Scene `$1D` looks like a
post-game/next-round stock path beyond the 16-team design; the stock game
has only 15 matches of its own, and match 26 is past double that. The
bracket state machine is unaffected (the state-only 31-match soak is green).

This is now a P3 stock-path follow-up: either intercept scene `$1D` too, or
cap/reset the stock tournament bookkeeping before it overflows.


## Round 90 — teams 16-31 metadata (names/codes/regions)

`data/teams32.json` now has real LLWS teams for ids 16-31 instead of
`TEAM 17`..`TEAM 32` placeholders:

```
16 AUSTRALIA      AUS  ASIA
17 CUBA           CUB  AMERICA
18 DOMINICAN REP  DOM  AMERICA
19 VENEZUELA      VEN  AMERICA
20 PANAMA         PAN  AMERICA
21 NETHERLANDS    NED  EUROPE
22 GERMANY        GER  EUROPE
23 SOUTH AFRICA   RSA  EUROPE
24 BRAZIL         BRA  AMERICA
25 COLOMBIA       COL  AMERICA
26 NICARAGUA      NIC  AMERICA
27 PHILIPPINES    PHI  ASIA
28 HONG KONG      HKG  ASIA
29 GUAM           GUM  ASIA
30 NEW ZEALAND    NZL  ASIA
31 CZECH REPUBLIC CZE  EUROPE
```

Rebuilt the full UI chain:

```sh
.venv/bin/python tools/build_32x20.py "Little League Baseball - Championship Series (USA).nes" data/roster.json -o build/32x20.nes
.venv/bin/python tools/pack_team_table.py build/32x20.nes data/teams32.json -o build/32x20-ui.nes
.venv/bin/python tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes
```

Selector page 3 of 4 now shows `AUS CUB DOM VEN / PAN NED GER RSA` and the
detail bar reads `AUSTRALIA` (`docs/teams16-31-select.png`). The bank-9
codes/names/regions table and the bank-10 page lists both carry the new
metadata.

Still placeholder for teams 16-31: bank-8 player rosters (names are
`B1601`-style, attributes cloned from team 15), team colours, ratings, and
lineups. Those are the next content tasks.


## Round 91 — generated rosters for teams 16-31

Added a full 20-player data set for the 16 new teams.

```sh
python3 tools/gen_roster32.py data/roster.json data/teams32.json   -o data/roster32.json
.venv/bin/python tools/build_32x20.py "Little League Baseball - Championship Series (USA).nes"   data/roster.json -o build/32x20.nes
python3 tools/build_extra_rosters.py build/32x20.nes data/roster32.json   -o build/32x20-extra.nes
```

- `data/roster32.json`: 32 teams. Teams 0-15 are copied byte-for-byte;
  teams 16-31 have 20 generated players (country-flavoured 6-char surnames,
  power/speed/skill, three pitcher slots `08/10/18`, 48-byte trailer with
  three pitcher records).
- `tools/build_extra_rosters.py`: overwrites the bank-8 blocks for teams
  16-31 in `build/32x20-extra.nes` (blocks at `$8000 + team*0x170`).

The selector still builds and page 3 shows the new teams. **However, the
game cannot read these blocks yet.** The direct build's fixed bank lost the
`$CBE6 -> $FB90` roster-cache hook (direct20 has the stock `A9 00 8D 01 20`
there and `$FB90` is `FF`), and the existing `$7F00` table only initialises
16 entries. Teams 16-31 still need the on-demand cache:

1. restore the `$CBE6` hook / `$FB90` cache routine (or a new routine);
2. copy the two current teams' bank-8 blocks into scratch RAM at
   `$7800`/`$7970` when their ids are >= 16;
3. update `$7F00 + id*2` to those scratch pointers;
4. then launch the real ids (no `AND #$0F` mapping).

Until that is wired, the P1 high-team mapping (`id & $0F`) remains the
working path for the soak.


## Round 92 — live round labels, champion banner, top-row shift

The bracket title is now dynamic instead of the static "32 TEAM BRACKET".

### Round labels / champion

`tools/build_round_labels.py` replaces the draw tail with:

```
$8077  JSR $8440   ; round label
       JSR $83D0   ; WIN line
       NOP
```

`$8440` indexes `$8500 + $07FC` for one of six 14-char strings at `$84A0`:

```
0-15  ROUND 1  R32
16-23 ROUND 2  R16
24-27 ROUND 3  QF
28-29 ROUND 4  SF
30    ROUND 5  FINAL
31    CHAMPION
```

and copies it to the title run's buffer at `$0325` before the flush.

Verified by calling `$8440` at each index and reading `$0325`:

```
00 ROUND 1  R32
16 ROUND 2  R16
24 ROUND 3  QF
28 ROUND 4  SF
30 ROUND 5  FINAL
31 CHAMPION
```

At index 31 the WIN line still shows the champion code (`WINFLA` in the
test), so the final screen is `CHAMPION` + `WINFLA`.

### Top-row clipping

`tools/build_top_row.py` moves the display-list header/title down one row:

```
header  $2048 -> $2068   (row 2 -> 3)
title   $2068 -> $2088   (row 3 -> 4)
```

The team grid starts at row 5, so nothing overlaps. Screenshot proof:
the labels are no longer cut by the 8-pixel top crop.

### Cursor marker

The existing bracket input handler already writes the cursor sprite at
`$0200` (tile `$41`) every frame; the P4 cursor marker is present, just
hard to see under the known post-game CHR corruption.


## Round 93 — 32-entry ratings and lineup tables

### Team ratings (POWER ANALYSIS)

The stock table is 16 x 4 at bank3 `$B224`; the only reader is bank3
`$AFE2  LDA $B224,Y`. `tools/build_ratings32.py` builds a 32 x 4 table at
bank3 `$BC80`, copies the original 16 entries, appends the generated teams'
ratings from `data/roster32.json`, and repoints the reader to `$BC80`.

Verified: `$AFE2 = B9 80 BC`; the first 8 entries still read
`01 03 02 03 02 02 03 04` and the new entries carry the generated ratings.

### Lineups

The stock table is 16 x 9 at bank4 `$96CA`; the only reader is
bank4 `$AD4E  LDA $96CA,Y` with `Y = team*9`. `tools/build_lineups32.py`
builds a 32 x 9 table in the fixed bank at `$FD80` (always mapped), copies
the original 16 entries, appends the default 9-batter order
`08 16 29 31 42 57 65 73 84` for teams 16-31, and repoints the reader.

Verified: `$AD4E = B9 80 FD`; the first 9 bytes still match Japan's lineup
and the last 9 are the default.

### Team colours

The two 16-byte colour tables at bank7 `$BAC0`/`$BAD0` have **no direct
reader** in the ROM (searched for absolute and indexed references). They may
be unused in this revision. No code change yet; the 32-team colour data is a
documentation-only gap.


## Round 94 — web editor 32 x 20 JSON mode

The browser editor can now load and edit the 32-team, 20-player roster set
without a ROM:

- new `web/roster32.json` (copy of `data/roster32.json`);
- `Data -> Load 32-team demo` button;
- `state.playerCount` controls the player grid padding, so 20 rows render;
- the team eyebrow uses `state.teams.length`, not the hard-coded 16;
- JSON import accepts 16 or 32 teams and chooses the player count from the
  file.

Verified in the T3 preview browser:

```
default demo:  16 team cards, 15 player rows, "Team 01 / 16"
32-team demo:  32 team cards, 20 player rows, "Team 01 / 32"
```

Still pending on the editor: parse/export the 32-team **ROM** layout
(bank8 `$8000 + team*$170`), and load `teams32.json` names into the ROM
mode. The current ROM mode remains the stock 16 x 15 editor.


## Round 95 — roster-cache diagnostic

The fixed-bank cache routine does execute. Starting from the launch stub and
single-stepping with `stepInstructions`:

```
$FC02  JSR $C14E        map bank8
$FC05..$FC10           set dest $7800, load team id
$FC44  copy loop
$FC50  LDA ($00),Y / $FC52 STA ($02),Y / $FC54 INY / $FC55 BNE
```

The loop runs, but the frame boundary arrives while it is still copying;
`stepInstructions` then reports `finalPc=$CD86` (the NMI handler). The RAM
cache at `$7800/$7A00` and the `$7F00` table stay zero/dummy.

Adding `LDA #$00 / STA $2000` at the launch stub (NMI off before the copy)
did **not** change the result. The next probe is to move the copy into a RAM
routine with interrupts explicitly disabled and confirm `$2000` is zero at
`$FC00`, then copy in two 0x100/0x70 chunks with a frame-safe loop. The
32-team roster data itself is ready; only the runtime cache is blocked.


## Round 96 — password format located and decode verified

The stock password routines are:

- **encode / series init:** bank5 `$98D5` (fills `$0650` from table `$994F`,
  packs to `$074D`; called by `$98B7`);
- **decode / advance:** bank5 `$9B5F` (unpacks `$074D` to `$0650`, clears
  `$0670`, applies `$0746` results from `$0755/$0756` via `$8941`).

Verified in romdev from the live password screen (bank5 mapped):

```
$074D = 01 23 45 67 89 AB CD EF
$0746 = 00
call $9B5F
$0650 = 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
```

The decode is a pure 4-bit unpack plus result application. The 32-team
format proposal is in `docs/password-format.md`: a 32-bit seed + 31 result
bits + version/checksum (16 hex chars), rather than 40 hex chars of 5-bit
ids.


## Round 97 — 32-team password model: 100 round-trips green

Implemented `tools/password32.py` with the proposed 8-byte format:

```
seed (4 bytes LE) + results bits 0-30 + version bit 31
xorshift32 -> Fisher-Yates order; match m -> slots[32+m]; champion slot 62
```

Verified:

```
python3 tools/password32.py test
password32: 100 round-trips OK; champion all-A = 19
```

The example `--seed 0x12345678 --results 0x01234567` encodes to
`7856341267452381` and decodes back to the same seed/results, champion `05`.
`decode` rejects a password whose version bit is clear.

This completes the 32-team password encode/decode **model** and the
100-round-trip check. Still pending: wire it into the stock password screen
and keep the 16-team `$074D` path working.


## Round 98 — 32-team roster audit (20 players, three pitchers)

`tools/audit_roster32.py` checks every team 16-31 in a 32-team build:

- 20 player records with printable 6-char names;
- exactly three pitcher slots `08`/`16`/`24`;
- the 48-byte trailer (`FF*16`, `00*8`, three 8-byte pitcher records).

```
python3 tools/audit_roster32.py build/32x20-extra.nes
...
team 31: 20 players, pitchers 08/10/18, first=NOVAK  last=KELLY
audit OK: 16 x (20 players + 3 pitcher records)
```

This verifies the bench and all three pitcher records at the data level.
The in-game substitution/pitcher test is still pending (it needs a live
game with a 20-player team and a START-menu substitution).


## Round 99 — web editor 32-team ROM mode

`web/rom.js` now detects and patches both layouts:

- **stock-16:** 16 teams x 15 players, bank4 `$8420`, stride `$120`
  (unchanged, byte-identical round-trip);
- **bank8-32:** 32 teams x 20 players, bank8 `$8000 + team*$170`.

Detection: 16+ PRG banks and a printable team-0 name at bank8 `$8000`.
Names come from bank1 `$9180` (0-15) and bank9 `$8080` (16-31) when
present; otherwise the bank1 `$BCC0` 8-byte table or a `TEAM nn` fallback.
Ratings use bank3 `$B224` (0-15) and the 32-entry `$BC80` table when it is
valid (16-31).

`applyRom` writes player records back to the bank8 blocks, team names to
bank9 (or the bank1 names32 table), and ratings to `$B224`/`$BC80`.
`app.js` sets `state.playerCount` from the parsed metadata, so 20 rows
render for a 32-team ROM.

Node verification:

```
stock ROM:        stock-16 16/15, applyRom byte-identical
32x20-extra.nes:  bank8-32 32/20, team 16 = TEAM 17 / HARRIS
select-screen:    bank8-32 32/20, team 16 = AUSTRALIA / HARRIS
edit team 16:     AUSTRALIA/HARRIS -> AUS TEST/TESTER skill 4 (re-parsed)
```

The browser UI still needs a visual smoke test (the preview host dropped
its tab during this run), but the parser/patcher and stock round-trip are
verified.


## Round 100 — roster cache works: MMC1 reset was the missing step

The cache failure was not the copy loop or NMI. `$C14E` maps bank 8 by
writing the MMC1 PRG register five times, but it assumes the shift register
is clear.  In the launch stub the register was left mid-write by the previous
bank operation, so the bank-8 switch also corrupted CHR0 (the PRG-RAM enable
bit).  The `$7800` copies were silently dropped.

Adding the standard MMC1 reset **before** the bank switch fixes it:

```
A2 FF        LDX #$FF
8E FF 9F     STX $9FFF      ; reset MMC1 shift register
AD FC 07     LDA $07FC
0A A8        ASL A / TAY
B9 00 77     LDA $7700,Y
8D FD 07     STA $07FD
...
4C 00 FC     JMP $FC00      ; cache routine
```

Live match 8 (`$7710 = 10 11`, real teams 16/17):

```
$7F20 = 00 78   $7F22 = 00 7A
$7800 = "HARRIS"   $7A00 = "GARCIA"
```

The game accepts the real team ids (no `AND #$0F`) and reaches the field
(scene `$03`) with the new rosters. The field then stalls 0-0 rather than
crashing; that is a separate lineup/pitcher/gameplay issue.

Reproducible build:

```
python3 tools/build_32team_full.py
# direct20-names -> ratings32 -> lineups32 -> round labels -> top row
# -> roster cache -> build/direct31.nes
```

The cache script is `tools/build_roster_cache.py`; the driver is
`tools/build_32team_full.py`.


## Round 101 — bank-7 field roster reads repointed

The field HUD reads roster pointers through a second copy of the loader in
bank 7:

```
$8B2C  BD 00 84   LDA $8400,X
$8B36  7D 01 84   ADC $8401,X
```

These still used the original 16-entry table after the cache work, so the
high-team field variables `$04F1-$04FE` came back as `FF`. Repointing both
to `$7F00/$7F01` (like the bank4/bank15 reads) changes the high-team field
state from all-`FF` to populated values:

```
before: 04F1..04FE = FF FF FF FF FF FF FF FF FF FF FF FF FF FF
after:  04F1..04FE = FF C6 FF 02 FF 0F FF 0F FF 0F 88 98 03 0C
```

The game still stalls 0-0 at scene `$03` in both SPEED and WATCH; the
remaining difference is gameplay/player-state related, not the roster
pointer table. The field renders the correct cached batter ("HARRIS",
skill 5) and a pitcher ("PATTER"), but the scoreboard still shows the
pre-match team names (`JAPAN`/`ARI`) because that text is built before the
launch bridge sets the real ids.


## Round 102 — field stall is the `$047D` NMI guard

The high-team field is not running its scene logic. The fixed-bank main
loop is:

```
CC09  LDA $047D
CC0C  BNE $CC09      ; wait for NMI to clear the guard
CC0E  INC $047D
CC11  JSR $CC30
```

At the stall: `$047D=01`, `$2C=00`, `$AD=1E`, `$20=90`. The NMI vector is
`$CD85`; its tail clears the guard at `$CDEA-$CDEC` when `$AD & $1E != 0`,
which is true. But the handler never runs (`$2C` stays 0), so the guard is
never cleared.

Forcing `$2000=0x80` at `$CC06` (JMP `$FEB0`) did **not** start NMI. The
next probe is the PPU rendering state: if the field handler left `$2001`
off, no vblank NMI is generated. Candidate fixes: re-assert `$2001` from
`$AD` at the field, or make `$CC09` clear the guard instead of waiting.

The bank7 read fix from Round 101 is committed; the field data is populated,
but the engine still does not tick.


### Follow-up: `$2001` re-assert clears the guard, then crashes

Writing `$2001 = $AD` (`$1E`) at the stalled field clears `$047D` and the
main loop advances, but the CPU then jumps to **PC `$0013`** (zero-page
RAM). So the guard is a symptom: with the PPU rendering re-enabled the
field logic runs, but the high-team field data sends it into a bad pointer.
The next probe is a `$0013` crash trace / read-breakpoint to find which
high-team pointer is invalid, rather than patching the NMI guard.


## Round 103 — stock 16-team password round-trip verified

At the live password screen (bank 5 mapped), set `$047D=0`, `$0746=0` and
call the stock encoder `$98D5`:

```
$0650 = 03 05 0D 0C 0A 01 0B 06 0F 02 04 07 09 0E 08 00
$074D = 35 DC A1 B6 F2 47 9E 80
```

Clear `$0650`, keep `$0746=0`, and call the decoder `$9B5F`:

```
$0650 = 03 05 0D 0C 0A 01 0B 06 0F 02 04 07 09 0E 08 00
MATCH
```

The stock encode -> decode pair is exact. The 16-team `$074D` path is
intact; the 32-team screen wiring is still the remaining P2 step.


## Round 104 — full-game soak evidence, colour-table audit

### Full-game soak

The real-game soak's 26 matches are complete games, not simulations:

- matches 0-15: all 16 first-round games;
- matches 16-23: all 8 second-round games;
- matches 24-25: two third-round games.

Each was played to the box score under the COM/cutscene handler and the
winner slot was checked. The game is **6 innings**, not 9; the "9 innings"
wording in the TODO was inaccurate. Substitution and save/password runs are
still open.

### Team colours

Searched all banks for absolute (`$BAC0`, `$BAD0`), indexed (`$BAC0,X`,
`$BAD0,X`), and pointer (`C0 BA`, `D0 BA`, `BA C0`, `BA D0`) consumers.
The only `BA D0` hit was `DEC $BA / BNE`, not a table pointer. There is no
colour-table consumer in this revision, so the 32-team colour table is a
no-op; the task is closed as "audited, no reader" rather than adding dead
data.


## Round 105 — `roster.py show` handles the 32-team layout

`tools/roster.py` was 16-team-only. It now detects the bank-8 team-16 block
and prints all 32 teams:

- low teams (0-15): the bank-8 block when it is populated, otherwise the
  original bank-4 15-player roster;
- high teams (16-31): 20 players from bank8 `$8000 + t*$170`;
- names: bank1 `$9180` (0-15), bank9 `$8080` (16-31), then the bank1
  `$BCC0` 7-char table fallback;
- ratings: bank3 `$B224` (0-15), `$BC80` (16-31) when valid;
- lineups: bank4 `$96CA` (0-15), fixed `$FD80` (16-31) when valid.

Verified:

```
python3 tools/roster.py show build/direct31.nes
# 32 rows; team 16 = TEAM 17, 20 players, ratings 2/1/3/1, lu 0816...
python3 tools/roster.py show build/select-screen.nes
# team 16 = AUSTRALIA, 20 players, c --/--, lu --
python3 tools/roster.py show "Little League ... (USA).nes"
# unchanged 16-team output
```


## Round 106 — 32-team roster CLI (extract/apply)

`tools/roster32.py` adds the machine-readable counterpart to the 32-team
`roster.py show`:

```
python3 tools/roster32.py extract build/32x20-extra.nes -o /tmp/r32.json
python3 tools/roster32.py apply   build/32x20-extra.nes /tmp/r32.json -o /tmp/r32.nes
```

It reads/writes:

- 20 player records per team at bank8 `$8000 + t*$170`;
- names: bank1 `$9180` (0-15), bank9 `$8080` (16-31), bank1 `$BCC0`
  fallback;
- ratings: bank3 `$B224` (0-15), `$BC80` (16-31) when the table exists;
- lineups: fixed `$FD80` (read-only in the JSON).

Verified:

```
32x20-extra.nes  extract -> apply  byte-identical
select-screen    extract -> apply  byte-identical
edit team 16 player 0 -> TESTER / skill 4, re-extracted OK
edit AUSTRALIA -> AUS TEST (bank9 name) + TESTER, re-extracted OK
```

The all-FF bank1 `$BCC0` table is deliberately left untouched when it has no
printable entry, which keeps the no-names32 build's round-trip exact.


## Round 107 — CI runs the 32-team password model

The GitHub Actions workflow now runs the pure-Python 32-team password model
on every push/PR, in addition to the metadata and roster checks:

```yaml
- name: Verify 32-team password model
  run: python3 tools/password32.py test
```

This locks the 100-round-trip encode/decode property into CI without
needing a ROM or the py65 emulator.

Also probed this round (negative results, no ROM committed):

- an unconditional `$047D` clear in the NMI handler breaks the boot/password
  frame pacing (the password wait times out), so the guard cannot be cleared
  globally;
- the saved `/tmp/match5-cut.state` cutscene advances to the scene-`$0F`
  order screen after ~360 frames, but the deterministic B+A leave did not
  advance that particular state, so the field-card attribute test was not
  completed.


## Round 108 — web editor shows the 32-team layout

The editor chrome now reflects the parsed layout:

- clean 32-team ROM: `ROM · 32×20` (instead of a generic `ROM · READY`);
- load banner: `… · 16 PRG banks · 128K CHR · 32×20 bank8`;
- the 16-team and 32-team demo loaders clear `state.meta`, so a stale layout
  cannot leak across a demo reload.

Verified:

```
node --check web/app.js
parseRom(32x20-extra).meta  -> bank8-32 32 20
parseRom(stock).meta        -> stock-16 16 15
```

The T3 preview host was not available for a browser screenshot this round;
the metadata path is proven directly.


## Round 109 — NMI runs; the main thread stalls on the PPU vblank flag

Breakpoint at the NMI vector `$CD85` during the high-team field:

```
hit at frame 1258, A=01 X=03 Y=39 S=F8
after one frame: $047D=00, $2C=01, $AD=1E
```

So the NMI **does** run and clears the `$047D` guard. The main thread then
sits in the vblank wait:

```
CDF5  LDA $2D
CDF7  BNE $CE5D
CDF9  BIT $2002
CDFC  BVS $CDF9     ; waits for the vblank flag to clear
CDFE  BIT $2002
CE01  BMI $CE05     ; waits for the vblank flag to set
```

The CPU stays at `$CDFC`; `BIT $2002` keeps returning V=1. Replacing the
wait with `JMP $CE05` did not unblock the field. Forcing the saved
`/tmp/match5-cut.state` (a stock pre-match state) to scene `$03` lands in
the same vblank wait, so this is not unique to the high-team path.

This points at the PPU/vblank flag state rather than the roster pointers.
The field and post-game CHR work are blocked on this until the PPU state can
be observed or reset correctly.


## Round 110 — correction: the PPU/vblank wait is normal frame pacing

Round 109 called the field "stuck on the vblank flag". Polling the PPU
register region over frames corrects that:

```
nes_ppu_regs = b0 1e 20 00   ($2000=$B0, $2001=$1E, $2002=$20)
PC alternates $CDFE (vblank wait) and $CC0C (main loop)
```

The main loop **is** running frames; `$CDFC/$CDFE` is the normal vblank
sync, not a dead end. `$047D` is cleared by NMI and the scene handler runs.
The field is alive but does not advance the score/inning, so the remaining
issue is gameplay state (pitcher/batter data or the pitch loop), not a
halted PPU.

The high-team field still shows a valid cached batter/pitcher card and a
0-0 score, but no pitches. The next probe is the pitcher-trailer lookup
(`$8420` stub, `$150 + pitcher_slot`) with the `$7800` cache pointer, and
the `$04F9/$04FA` "value 4" bytes, which are `FF/0F` at the high-team field
versus valid values in the stock field state.


## Round 111 — high-team field: pitcher trailer lookup is the bad value

At the high-team field (teams 16/17):

```
$04/$05 = 34 7E        (computed player-record address $7E34)
$04F9/$04FA = FF 0F    (away pitcher "value 4" = FF)
$04FB/$04FC = 88 98    (stamina)
$04FD/$04FE = 03 03    (pitcher lineup positions)
$04EF/$04F0 = 10 11
```

The stock field state has valid `$04F9=08`, and the field runs frames but
never throws a pitch. The trailer lookup in this build is still:

```
B094  LDX $04EE
B097  LDA $04FD,X
B09A  ASL A x4
B09E  JSR $B07C
B0A1  CLC
B0A2  LDY #$0C
B0A4  LDA ($04),Y
B0A6  ADC $7F00,X
...
```

The `$8420` byte range that `build_16x20.py` uses for its relocated trailer
stub is **team-name data** in the direct build, not the stub. So the
20-player cache block (0x170, trailer at 0x140) is being read through the
old 15-player/trailer path, producing `FF` pitcher values and the silent
0-0 field.

This is the next concrete fix target: restore/repoint the 16x20 trailer
stub for the cache build and re-check `$04F9/$04FB` before chasing the
pitch loop.


## Round 112 — trailer stub and forced COM flags: negative results

Restored the 16x20 pitcher-trailer stub for the cache build:

```
$B094 -> JMP $FEB0
$FEB0: LDX $04EE / LDA $04FD,X / ASL x4 / JSR $B07C
       ... ADC $7F00,X / ADC #$50 ... RTS
```

The stub is **not called** during the high-team field (breakpoint at `$FEB0`
misses for 20 frames), and `$04F9/$04FA` stays `FF/0D`; the score does not
move. So the silent field is not the trailer lookup alone.

Forcing the pitch-control bytes at the stalled field:

```
before: $04E9-$04EC = 01 00 80 00
after:  $04E9-$04EC = 00 00 80 80
```

The flags hold, but the score stays 0-0 over 1800 frames and the match index
stays 08. The field is waiting on a state we have not identified, not just
the COM/pitch flags.

Next candidates: the scene-3 sub-state/`$047A` value, the `$06DF`/`$06DE`
scroll counters, or the pre-match handoff fields that the bracket path does
not initialize.


## Round 113 — `$C1` is not the field mode

The high-team field has the stock scene-3 handoff values:

```
$047A=04  $047B=03  $0486=00
```

but `$C1=00` where the stock field target is `$C1=$76`. Forcing `$C1=$76`
at the stalled field makes it decay to `$0E`/`$0C`/`$00` over the next
frames, and the score stays 0-0. So `$C1` is a transient/scroll value, not
the missing field-mode switch.

The remaining field-stall candidates are the pre-match handoff fields and
the pitcher/batter lineup mapping. No ROM change was kept this round.


## Round 114 — web editor: high-team scoreboard name is read-only

In `bank8-32` mode, teams 16-31 get their scoreboard name from the bank9
3-letter code; `applyRom` does not rewrite that short-name table. The editor
now reflects this:

- the scoreboard-name input is **disabled** for high teams;
- its limit label reads `bank9 code`;
- the input title explains that the ROM export does not rewrite it;
- low teams keep the normal editable field.

`node --check web/app.js` passes. This avoids an edit that would silently
not be written by the ROM export.


## Round 115 — stock password text is letter-coded, not hex

At the live password screen (before a series is initialised):

```
$06B5 = 53 53 53 53 53 55 20 53 53 55 55 FF   "SSSSSU SSUU"
$0650 = FF 53 53 53 53 53 55 20 53 53 55 55 FF ...
$074D = FF FF FF FF FF FF FF FF
```

`$C835` copies from `$0651` to the display buffer `$06B5` until `$FF`; the
bytes are **ASCII letters** (`S`/`U`) plus a space, not hex digits. The text
is 11 characters, and the packed `$074D` bytes are still `FF` until the
series encoder runs.

This means the 32-team model's 16-hex-character format does **not** match the
stock screen. Wiring it in needs either:

1. an alphabet mapping (4 bits -> one of 16 letters) so the 8-byte password
   still renders as 16 letters, plus a wider display buffer; or
2. a new password layout/screen that can show 16 characters.

The stock `$06B5` buffer is the concrete constraint: 11 letters plus the
`$FF` terminator before the next text field.


## Round 116 — self-contained roster32 round-trip test in CI

`tools/test_roster32.py` builds a synthetic 32-team ROM in a temp dir (no
base ROM, no py65):

- bank1 low-team names, bank3 `$B224` ratings;
- bank1 `$BCC0` names32 and bank3 `$BC80` ratings for 16-31;
- all 32 bank8 `$8000 + t*$170` blocks with 20 player records and trailers.

It then runs `extract` -> `apply` and asserts the output is **byte-identical**,
edits team 16 player 0 to `TESTER`/skill 4, applies, re-extracts, and checks
the edit. CI now runs it:

```yaml
- name: Test 32-team roster CLI
  run: python3 tools/test_roster32.py
```

Verified locally:

```
test_roster32: fixture round-trip + edit OK
```


## Round 117 — post-game CHR shadows differ, but are not the bank values

At the post-game scene-0B bracket (`/tmp/bracket-post2.state`):

```
$27 = 0B          (bank 11 mapped)
$23-$26 = 18 1B 05 1C
```

The normal bracket entry had `$23-$26 = 1B 1B 18 1C`. The shadows differ,
but writing CHR0=1B / CHR1=18 with the stock helpers (`$C11C`/`$C134`)
turns the screen into a checkerboard/flag glitch, not the correct bracket.
So the shadows are not the latched CHR bank values.

A direct CHR write followed by a save-state diff is also inconclusive: the
tail byte `0x35b7` changes to `0x1E` for an A=0x1F write, which is the
MMC1 shift buffer/count, not a recoverable bank byte.

The next CHR probe needs a mapper/PPU-level view of the latched banks, not
the `$23-$26` shadows or the save-state tail.


## Round 118 — `$0511/$0512` are player attribute bytes, not pointers

The `$0511` writer in bank4 is:

```
ADF7  LDX $04ED
ADFA  LDY #$06
ADFC  LDA ($04),Y
ADFE  STA $0511
```

It stores the **current player record's byte 6** at `$0511`; `$0512` is the
next attribute byte. So the stock `$0511/$0512 = 80/81` and the high-team
`00/57` are data differences, not a bad roster pointer. The bank7 `$8D6F`
writer is just an init (`STA $0511` = 0).

This rules out the last handoff-pointer lead for the silent field. The
remaining field work needs a different angle (the scene-3 sub-state machine
or the pitcher/batter role selection), not the `$0511` byte pair.


## Round 121 — `$04F9` is read from the wrong player-record pointer

The `$04F9` writer is:

```
AF09  LDA ($04),Y     ; Y=3 after INY from 2
AF0B  JSR $ADBC
AF0E  STA $04F9,X
```

It reads the **current player record's byte 3** (part of the 6-char name)
and stores the converted value. At the high-team field `$04F9=FF`, so
`($04)` points at `FF` data.

The field's current player pointer is `$04/$05 = $7E34`, which is **outside**
the `$7800` cache block (0x170 bytes, ending $7970) and just below the
`$7F00` table. A correct team-16 player record should be `$7800..$796F`, not
`$7E34`. The `$B07C` player-record computation is therefore using the wrong
base or index for the cached high team.

This is the strongest remaining field lead: trace the `$B07C` inputs
(`$04EF`, `$04FD`, `$06E2`) and find why the high-team pointer lands at
`$7E34`.


## Round 122 — `$7F00` is correct; `$04/$05` comes from another path

At the high-team field the roster table is intact:

```
$7F20/$7F21 = 00 78   (team 16 -> $7800)
$7F22/$7F23 = 00 7A   (team 17 -> $7A00)
$04EF/$04F0 = 10 11
$04FD/$04FE = 03 03
```

The `$B094` path should compute, for the home team (17):

```
base $7A00 + ($04FE=3 << 4) = $7A30
```

but the actual current-player pointer is:

```
$04/$05 = 34 7E   ($7E34)
```

`$7E34` is in the free gap below `$7F00`, not $7A30. The `$B07C` arithmetic
cannot produce it from the table, so a **different routine** sets the
current-player pointer (likely the batter-card/setup path). `$04F9` then
reads byte 3 from that pointer's FF data.

Next: put a write breakpoint on `$04/$05` during the field entry and capture
the caller that writes `$7E34`.


## Round 123 — `$04/$05` is a hardcoded card-data pointer

The write breakpoint on `$04` at the field hits bank15 `$E34F`, but the
pointer comes from the field card setup at bank6 `$8EF8`:

```
8EF8  LDX #$00
8EFA  STX $047e
8EFD  LDA #$7C
8EFF  STA $047f
8F02  LDA #$80
8F04  STA $47
8F06  LDA #$3C
8F08  STA $63
8F0A  LDA #$F8
8F0C  STA $0619
...
```

`$47/$63` are hardcoded to `$80/$3C`, and `$0619` to `$F8`; the card
pointer is `$803C + $F8` (adjusted by the `$E341` path), not a roster
pointer. So `$04F9` is a **card-data byte**, not the pitcher's roster
stat. The "wrong player pointer" lead is invalid.

The field stall is still in the card/lineup setup or the pitch loop, not
the cached roster pointer.


## Round 124 — the field setup resets `$047E` in many places

Patching the one `STX $047E` at bank6 `$8EFA` does not preserve WATCH mode:
the field setup resets the byte to 0 at several sites:

```
bank6 $8F60/$8FA3/$8FD3/$9006/$9013/$95DB/$A1C7/$ABBD/$AD19/$B45F
bank7 $93D1
```

The mode toggle is bank5 `$9ED5` (`LDA $047E / EOR #$01 / STA $047E`).
WATCH is the scene-10 path; the scene-03 field is SPEED and expects a
pitch/COM handoff. Patching `$047E` alone is not the field-stall fix.

No ROM change was kept; the `direct39` probe still stalls at 0-0.


## Round 125 — README/TODO status refresh

The README's 32-team section now reflects the current build:

- working: bracket, selector, rosters, ratings, lineups, on-demand cache,
  round labels, champion banner, browser editor 32x20 ROM/JSON, CLI
  `roster.py show` and `roster32.py extract/apply`;
- embedded the selector page-3 screenshot (`docs/teams16-31-select.png`);
- gaps updated to the scene-3 field stall, the 11-character letter password
  screen, and the post-game CHR latches.

TODO cleanup: marked the 32-slot tournament, 32-slot bracket, 32-team
password format model, and bracket-table relocation as done; replaced the
stale NMI-guard field note with the current scene-3/pitch-loop status.


## Round 126 — CI covers `roster.py show32`

`tools/test_roster32.py` now also exercises the 32-team `show32` path on
its synthetic fixture:

- 33 output lines (header + 32 teams);
- `TEAM 16` appears (the bank1 `$BCC0` name);
- `P1600` appears (the first high-team player).

CI already runs this test, so the `show32` renderer is now covered alongside
the `extract/apply` round-trip.

```
test_roster32: fixture round-trip + edit + show32 OK
```


## Round 127 — `rominfo.py` reports the 16/32-team layout

`tools/rominfo.py` now prints a `layout` line:

```
layout    : 32-team bank8 (team 16 at $9700, 20 players)
layout    : stock 16-team
```

Detection is the same as `roster.py show`: 16+ PRG banks and a printable
team-16 name at bank8 `$8000 + 16*$170`.

Verified on `build/32x20-extra.nes` (32-team) and the stock ROM
(stock 16-team).


## Round 128 — CI covers `rominfo.py` layout detection

The self-contained fixture test now also checks:

```python
raw = open(src, "rb").read()
assert "32-team bank8" in team_layout(raw, rom_header(raw))
```

CI runs `tools/test_roster32.py`, so both `roster.py show32` and
`rominfo.py`'s new layout line are covered by the same synthetic 32-team
ROM.

```
test_roster32: fixture round-trip + edit + show32 + rominfo OK
```


## Round 129 — full test sweep green

Ran the complete local suite:

```
python3 tools/password32.py test
password32: 100 round-trips OK; champion all-A = 19

python3 tools/test_roster32.py
test_roster32: fixture round-trip + edit + show32 + rominfo OK

node --check web/app.js && node --check web/rom.js
js ok

.venv/bin/python tools/verify_regression.py   "Little League Baseball - Championship Series (USA).nes" build/32bracket.nes
screenshots MATCH
system_ram differs in 0 bytes
```

The working tree is clean; the stock regression, password model, 32-team
roster CLI/editor code, and browser-editor syntax all pass together.


## Round 130 — web editor team codes and regions

The editor now carries the 3-letter code and region:

- `web/rom.js` reads bank9 `$8000` codes and `$8280` regions for 32-team
  ROMs (`JPN`/`ASIA`, `AUS`/`ASIA`, ...);
- `normalizeTeam` preserves `code`/`region`;
- the team eyebrow shows `Team 16 / 32 · AUS · ASIA`;
- `web/teams32.json` is loaded by **Load 32-team demo** and merged by id.

Verified:

```
select-screen: team 0 JPN/ASIA, team 16 AUS/ASIA
32x20-extra:   no bank9 table -> empty codes (stock behavior)
demo merge:    team 0 JPN/ASIA, 16 AUS/ASIA, 31 CZE/EUROPE
```

The stock 16-team path is unchanged (no bank9 table -> no tag).


## Round 131 — CI keeps the web team metadata in sync

The "Validate team metadata" CI step now also checks that
`web/teams32.json` is identical to `data/teams32.json`:

```python
web = json.load(open("web/teams32.json"))["teams"]
assert web == teams, "web/teams32.json is out of sync"
```

This catches a stale browser copy after a team name/code/region edit.

```
web/teams32.json matches data/teams32.json
```
