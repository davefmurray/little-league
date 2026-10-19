---
name: llbcs-32-team
description: Work on the Little League Baseball Championship Series 32-team ROM hack in this repo — build chain, bank layout, bracket state, selector, stock game handoff, and known traps. Use when editing teams, rosters, brackets, banks, the selector, or launching games from the hack.
---

# LLBCS 32-team ROM hack

Locked target: **32 teams × 20 players, 32-team bracket, 256 KiB PRG + 128 KiB
CHR, MMC1, emulator-first**. Stock 16-team path must keep working.

Repo root: `/Users/dfm/GitHub/nesdav/little-league`
Base ROM: `Little League Baseball - Championship Series (USA).nes`
Report: `docs/AUTORUN-REPORT.md` · Plan: `docs/PLAN-32-TEAM.md`

## Build chain

```sh
BASE="Little League Baseball - Championship Series (USA).nes"
.venv/bin/python tools/expand_rom.py "$BASE" -o build/32x20.nes
.venv/bin/python tools/build_32x20.py build/32x20.nes data/roster.json -o build/32x20-ui.nes
.venv/bin/python tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes
python3 tools/build_dispatcher.py build/select-screen.nes -o build/dispatcher.nes
.venv/bin/python tools/build_bank11.py build/dispatcher.nes -o build/bank11.nes
.venv/bin/python tools/build_bracket_screen.py build/dispatcher.nes -o build/bracket-screen.nes
.venv/bin/python tools/build_bracket_input.py build/bracket-screen.nes -o build/bracket-input.nes
```

`build_bracket_screen.py` owns bank 11's code/data, so it replaces the bank-11
logic image. Use `--loop-to 0x8100` when input code will be added, and
`--seed-human N` only for test builds (production reads `$07C3`).

Never commit `build/` or `*.nes`. Build outputs are gitignored on purpose.

## Bank map (expanded ROM)

| Bank | Use |
|---|---|
| 8 | 32 rosters, 32×`$170` bytes, pointer table `$7F00` |
| 10 | 32-team selector |
| 11 | bracket scene: screen `$8000`, input `$8100`, seed `$8200`, bracket table `$A000`, codes `$B000`, palette `$B100`, list `$B200` |
| 15 | fixed bank (was 7 in stock) |

Only `$C000–$FFFF` is fixed. Any address `$8000–$BFFF` needs a bank tag.

## State map

| Address | Meaning |
|---|---|
| `$07C0–$07C2` | selector page / cursor |
| `$07C3` | selected team (`$FF` = none) |
| `$07C6–$07C9` | pad scratch + edge state |
| `$04EB/$04EC` | alive flags (`$80`) |
| `$04EF/$04F0` | **raw team IDs** for the two sides |
| `$047B` | scene index; stock field = 3 |
| `$047C` | frame/scene tick |
| `$047D` | vblank handshake |
| `$04E6` | scene-transition request |
| `$C1` | game/mode flags; stock field `$76` |
| `$0746` | matches completed |
| `$074B/$074C` | 16-bit result bits |
| `$7700` | 63 bracket slots (cart RAM) |
| `$7740` | 32 win counts |
| `$7760` | round / match |

Stock field state observed: `$04EF=$0D` (Italy), `$04F0=$02` (Pennsylvania),
`$047B=$03`, `$C1=$76`, `$0746=$0000`.

## Stock menu path

Team select's prompt is **not** confirm/cancel:

- `CONTINUE` = keep editing teams → back to map
- `END` = finish selection

Full path to a field:

```
team select → END → PASSWORD → A → matchup
→ A → SPEED MODE / WATCH THE GAME → down + A
→ pre-match cutscene → field
```

Directly poking the field state from the 32-team bracket returns to the bracket;
the missing piece is the pre-match/scene init routine, not the handoff values.

## Traps that already cost time

1. **`$CBE6` is not an entry point.** It is `LDA #$00`. Hooking it with `JSR`
   makes `STA $2001` use the wrong A. Hook at `$CC06` (`STA $2000`) after reset
   init, and have the trampoline re-execute `STA $2000`.
2. **PRG RAM writes are dropped before CHR0 bit 4 is cleared.** Call
   `LDA #0; JSR $C11C` before touching `$6000–$7FFF`.
3. **NMI corrupts timing-sensitive cart-RAM writes.** Disable with
   `LDA #0; STA $2000` immediately before the 32-team seed; re-enable before
   `JMP $CC09`.
4. **Every display-list team code must be 3 bytes.** `"NY"` shifted every later
   run by one and sent the flush down the RLE path. Pad with
   `code.ljust(3)[:3]`.
5. **Custom byte builders must size zero-page operands as 2 bytes.**
   `CMP $02` is 2 bytes, not 3. Mis-sizing silently shifts branch targets.
6. **`$04EF/$04F0` are raw team IDs** — confirmed by the bank-1 name renderer
   at `$AF40`, which indexes team-name pointers with them.
7. **Do not write `$C040`.** It is a ROM byte (`$40`) used by `BIT` as a bitmask;
   the flush checks bit 6 of each run's high byte for RLE.
8. **jsnes 1.2.1 has an MMC1 shift-counter bug.** Use fceumm through romdev for
   real mapper behavior.

## Verification

```sh
.venv/bin/python tools/verify_regression.py \
  "Little League Baseball - Championship Series (USA).nes" build/32bracket.nes
```

Expected: `screenshots MATCH`, `system_ram differs in 0 bytes`.

romdev checks that matter:

- selector renders after reset init
- bracket leaf 0 shows the seeded human (`FLA` for human 15)
- `$7700..$771F` is 32 unique values, human at slot 0
- stock field reachable through the menu path above

## Current status

- 32 rosters and selector: working.
- 32-team seed + names: green (`$07C3` → `$7700`, human at leaf 0).
- Scene dispatcher: fixed hook at `$CC06`, committed.
- Game launch from the 32-team bracket: **open**. Best next step is capturing the
  stock password→matchup→field init, not poking more state.
