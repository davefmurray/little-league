# Handoff — 32-team launch bridge

**State as of `9a601bc`**  
32-team data, selector, bracket, seeding, and regression are green.  
The bracket-to-game launch bridge is **not working**.

This document is for whoever picks this up next. Read it before touching the
launch path; most of the obvious approaches have already been tried and failed.

---

## 1. What works

- 32 teams × 20 players in bank 8 (`data/roster.json`).
- 32-team selector in bank 10 (`data/teams32.json`).
- 32-team bracket screen in bank 11, seeded from `$07C3`.
- Human team at bracket leaf 0; all 32 slots unique.
- Stock regression green:

```sh
.venv/bin/python tools/verify_regression.py \
  "Little League Baseball - Championship Series (USA).nes" build/32bracket.nes
# screenshots MATCH, system_ram differs in 0 bytes
```

## 2. Build chain

```sh
BASE="Little League Baseball - Championship Series (USA).nes"
.venv/bin/python tools/expand_rom.py "$BASE" -o build/32x20.nes
.venv/bin/python tools/build_32x20.py build/32x20.nes data/roster.json -o build/32x20-ui.nes
.venv/bin/python tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes
python3 tools/build_dispatcher.py build/select-screen.nes -o build/dispatcher.nes
.venv/bin/python tools/build_bracket_screen.py build/dispatcher.nes --loop-to 0x8100 -o build/bracket-screen.nes
.venv/bin/python tools/build_bracket_input.py build/bracket-screen.nes -o build/bracket-input.nes
```

Build outputs are gitignored. The launch experiments below are *not* in the
normal chain; they were built with ad-hoc patches.

## 3. Key addresses

| Address | Meaning |
|---|---|
| `$07C3` | selected team |
| `$04EF/$04F0` | raw team IDs (confirmed) |
| `$047B` | scene id |
| `$047C` | scene sub-state |
| `$7C51` | scene handler table base (`$CC51 + 2*scene + 1`) |
| `$CCAC` | scene bank table, indexed `scene >> 1` |
| `$C232` | RTS-table dispatcher |
| `$CC09` | stock main loop |
| `$CC0E` | main loop after `$047D` wait |
| `$98B9` | END-confirm entry (`LDA $33; STA $34; JSR $98D5`) |
| `$98D5` | password buffer builder |
| `$995F` | scene-13 handler, bank 5 |
| `$8000/$8100` | bracket screen / input in bank 11 |
| `$8200` | seed routine in bank 11 |
| `$B000/$B100/$B200` | codes / palette / display list |

## 4. What the stock flow actually does

Team select is scene `$0D`. END confirms and calls `$98B9`, which:

1. `LDA $33; STA $34`
2. `JSR $98D5` — fills `$064F–$065F` with `$FF`, generates password text
3. `$0746=0`, `$BE=0`, `$047C=7`, `$07ED=1`
4. `INC $047B` (12 → 13, password screen)
5. `RTS`

The password screen is **RAM-driven** and is not a separate scene handler.

## 5. Current launch experiment

This is the latest and most promising version. It uses a real `JSR` hook:

Bank 5 at `$98B9`:

```
98B9  20 20 FF     JSR $FF20
98BC  4C 80 FF     JMP $FF80
```

Fixed bank `$FF20`:

```
TSX; STX $07F7
LDA $0101,X; STA $07F8
LDA $0102,X; STA $07F9
NMI off
MMC1 reset (STX $9FFF)
select bank 11
$27 = 11
JMP $8000
```

Fixed bank `$FF80`:

```
MMC1 reset
select bank 5
$27 = 5
NMI on
JMP $98BD
```

Bracket A (`build_bracket_input.py` experimental block):

```
IDs -> $04EF/$04F0
$07FF = $B0
LDA $33; STA $34
NMI off
LDX $07F7; TXS
LDA $07F9; PHA
LDA $07F8; PHA
RTS
```

### Current result

- `$8000` bracket code runs.
- Input loop runs; bracket renders.
- A press causes PC to become **`$B005`** (bank-11 data).
- `$8162` (A branch) is **never reached**.
- Saved frame is still correct at crash: `$07F8/F9 = BB 98`, `$07F7=$FB`, `S=$FB`.
- `$27 = $0B` at the crash.

So the crash happens **inside the controller-read loop, before the A branch**,
not in the resume/RTS code.

## 6. Ordered next probes

1. **Controller read.** Break at `$810B` entry and `$8126` return with A held.
   Capture `S` at both. If `S` changes, `$810B` is corrupting the stack.
2. **Interrupt.** Break at `$B005` with A held, capture `$2C`, `$AD`, `$047D`,
   `$2000`, `$2001`, and the NMI return frame.
3. **No input path.** Run the bracket for 300 frames without pressing A. If it
   stays in the input loop, the controller read is the only trigger.
4. **Branch bypass.** Patch `$8160 BEQ` to `EA EA` (always A branch) in a test
   build. If it still reaches `$B005`, the failure is in the branch body; if it
   now returns to stock, the edge detection/read is the fault.
5. **Minimal ROM.** Build a tiny ROM that only does
   `JSR $810B; JMP $B005` to reproduce the crash in isolation.

## 7. Dead ends — do not repeat

- Cold-entering stock scenes: `$CC09`, `$CC0E`, `$D014`, `$B9C0`, `$995F`.
- Scene id poking (`$047B=$11`, `$13`, `$0F`) without the dispatcher context.
- Registering a new scene by writing `$CCAC`/handler table by guessed offsets.
- `JMP` into stock main loop; it destroys the RTS dispatch frames.
- Assuming `$CBE6` is a routine: it is `LDA #$00`.
- Assuming `$98B7` is the routine: it is data; real entry is `$98B9`.
- Enabling NMI immediately before a bank switch or RTS: it causes an NMI storm
  (stack dropped from `$FF` to `$99` in one case).
- Trusting `stepInstructions` under NMI: it reports operand bytes; use
  free-running `traceInstructions`.
- Trusting breakpoints armed before END: they hit stock idle at `$CFA1`/`$8176`.

## 8. Useful diagnostics

- `docs/AUTORUN-REPORT.md` — full chronological probe log.
- `docs/bracket-handoff.md` — original handoff contract.
- `.claude/skills/llbcs-32-team` — project map and traps.
- `.claude/skills/nes-romdev-debug` — romdev workflow.
- `.claude/skills/nes-display-lists` — renderer format.

## 9. Repo hygiene

- Commit/push after every green change.
- Never commit `build/` or `*.nes`.
- Run `tools/verify_regression.py` after any stock-side patch.
- Stock 16-team path must keep working.

## 10. Recommendation

If launch is not required for the next milestone, **ship the working hack**
(selector + bracket + rosters) and park the bridge. The bridge is a deep
call-stack integration problem, not a data problem, and it has already consumed
more time than the rest of the project combined.
