# Bracket → game handoff contract (M2)

Verified from stock disassembly. This is the minimum interface a new 32-team
bracket must satisfy before launching a game.

## The two teams

```
$9C08  LDY $8941,X      ; table record for this match
$9C0B  LDA $0650,Y      ; slot A team id
$9C0E  STA $04EF
$9C11  LDA $0651,Y      ; slot B team id
$9C14  STA $04F0
```

- **`$04EF`** = first team id.
- **`$04F0`** = second team id.

Both are read well outside bank 5:

- bank 1: `$AF40`, `$B110`, `$B113`
- bank 2: `$BA45`, `$BB2E`, `$BB49`, `$BC17`, `$BD74`
- bank 0: `$AD1B`, `$AD22`, `$AD2B`

So writing these two bytes is the actual handoff; everything else is display or
post-game bookkeeping.

## Per-side flags

`$9CAC` loops `X=0,1`:

```
LDY $04EF,X
LDA $9CD0,Y        ; bit mask for this team
...
LDA $074B,Y        ; CPU ownership bitfield
AND mask
BEQ ...
LDA #$80
STA $04EB,X        ; $04EB/$04EC = CPU control flag ($80)
```

- **`$04EB/$04EC`** = `$80` for CPU control, zero for human control.
- **`$074B/$074C`** = 16-bit CPU ownership mask (one bit per team).
- `$9CD0` = `01 02 04 08 10 20 40 80` repeated twice for teams 0–15.

`$9F55` records CPU ownership in `$074B,Y`. The result bits are handled
separately by `$9F87`. Fixed `$C585` filters controller input according to
the ownership flags. The teamtables32 stage preserves low-team ownership
and defaults high teams to CPU without writing past the two-byte mask.

## Display setup

`$9CE0` loops the two sides, storing:

- `$BE/$BF` = side status (`$80`/`0`)
- `$047E` = 0/1 side index
- `$06B3/$06B4` = text pointer
- `$C9A8` → draw team name
- `$CB56` → draw flag/team block
- `$C53A` → flush display list

## What the 32-team scene must provide

1. Write the two team ids to **`$04EF` / `$04F0`** before entering the game.
2. Set **`$04EB` / `$04EC`** according to human or CPU ownership.
3. Keep its own bracket result state; do **not** reuse the CPU mask `$074B/$074C`.
4. Extend the team tables to 32 entries before handing over ids 16–31:
   names, ratings, rosters, flags, uniforms.
5. Preserve `$0746` if the stock post-game path is reused, or provide a new
   post-game hook that reports the winner.

## Status

Contract documented from disassembly (`$9C08`–`$9D40`, consumers above).
The in-game poke test (set `$04EF/$04F0`, start a match, confirm the teams) is
still pending; do not claim it verified until that runs.


## romdev confirmation (fceumm)

Loaded `build/bracket-input.nes` in romdev (session `llb-bracket`). A write
breakpoint on `$04EF` with a scheduled A press hit at:

```
pc = $8165   bank 11   value = $00
caller = $CBE6 (JSR)
```

This is our bracket handoff write, confirmed on a real MMC1 core.

A stock-path probe did not hit `$04EF` within 500 frames after selecting a team
and confirming at CONTINUE/END. That supports the "mirror vs owner" warning:
`$04EF/$04F0` are likely written when the bracket/game screen initializes, not
by the team-select screen. The next probe should watch reads of `$04EF` at game
start, and/or widen the stock probe to the bracket screen.

romdev note: its NES framebuffer is 256x224 (8 px cropped top/bottom), which is
why the first bracket row looked missing in the browser harness too.

## Stock owner found (Phase 0, romdev + xrefs)

Static references to `$04EF` include 52 sites. The writers are:

| Bank | Address | Instruction | Role |
|---|---|---|---|
| 0 | `$AD1B` | `STA $04EF` | **owner**, derives from `$33` |
| 0 | `$AD22` | `STA $04F0` | owner, from `JSR $C46F` |
| 0 | `$AD2B` | `STA $04F0` | owner, XOR with `$33 & 1` |
| 1 | `$B119` | `STX $04EF` | swaps `$04EF/$04F0` (home/away) |
| 2 | `$BC8C` | `STA $04EF,X` | copies from table `$B8C9` |
| 5 | `$9C0E/$9C14` | `STA $04EF/$04F0` | bracket display path |

The bank-0 routine:

```
$AD15  LDA $33
$AD17  PHA
$AD18  AND #$1C
$AD1A  LSR A
$AD1B  STA $04EF
$AD1E  JSR $C46F
$AD21  ASL A
$AD22  STA $04F0
$AD25  PLA
$AD26  AND #$01
$AD28  EOR $04F0
$AD2B  STA $04F0
$AD2E  LDA #$08
$AD30  STA $047B
$AD33  RTS
```

**This invalidates the simple contract.** `$04EF/$04F0` are not raw team
ids; they are derived from game-state `$33` and `$C46F`. Our bracket A-handler
writing raw 0..31 is likely the wrong value domain. Phase 1 must either:

- compute these the same way stock does from the selected teams, or
- find the upstream owner of `$33`/`$C46F` and set that instead.

Next probe: log `$33`, `$C46F` return, and `$04EF/$04F0` at the stock
game-start transition, then at the same point in our bracket build.

## Live call result (romdev)

Called the bank-6 caller at `$AC3A` directly (after mapping bank 6 and setting
`$C1 = 2`) via `cpu({op:'call'})`. It returned and left:

```
$04EF = $02
$04F0 = $06
```

But `$C46F` is not a team lookup:

```
$C46F  INC $34
$C471  LDA $34
$C473  AND #$3F
$C475  TAX
$C476  LDA $C4FA,X
$C479  RTS
```

It is a table-driven sequencer (sine/pseudo-random table at `$C4FA`). That makes
the bank-0 routine a **different context** (likely field/demo state), not proof
that the bracket launch uses derived values.

The bracket path still writes raw slot values at `$9C0E/$9C14`, and `$9CAC`
indexes `$9CD0,Y` with them. **Do not change the contract yet.** The decisive
test is launching from the bracket screen and checking which writer runs at that
transition.
