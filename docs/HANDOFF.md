# Handoff — 32-team launch bridge

**State: the launch bridge works.** Bracket → A → password screen → matchup →
speed mode → cutscene → field, with a balanced stack and green regression.

The full probe record and the four root causes are in
[`docs/LAUNCH-DEBUG-LOG.md`](LAUNCH-DEBUG-LOG.md). Read that before touching the
launch path; this file is the map, not the story.

---

## 1. What works

- 32 teams × 20 players in bank 8 (`data/roster.json`).
- 32-team selector in bank 10 (`data/teams32.json`).
- 32-team bracket screen in bank 11, seeded from `$07C3`.
- **Bracket → stock launch**, via the call-based bridge below:
  - bracket A sets `$04EF/$04F0`, `$07FF` and `RTS`es;
  - the trampoline rebuilds the password buffer and re-enters the stock
    scene-18 body;
  - stock takes over: password screen → matchup → speed mode → cutscene → field.
- **Selector → bracket → launch** in the production build: the selector's A
  hands the stock dispatcher scene 18, the hook runs the bracket, and the same
  bridge resumes. Reaches password → matchup → speed mode → cutscene → field.
- Stock regression green:

```sh
.venv/bin/python tools/verify_regression.py \
  "Little League Baseball - Championship Series (USA).nes" build/launch-stock.nes
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

# launch bridge (production: selector -> bracket -> launch)
.venv/bin/python tools/build_bracket_input.py build/bracket-screen.nes \
  --return-on-a -o build/bracket-launch-input.nes
.venv/bin/python tools/build_launch_bridge.py build/bracket-launch-input.nes \
  -o build/launch-prod.nes

# harness build: stock team select -> END -> bracket -> launch
.venv/bin/python tools/build_launch_bridge.py build/bracket-launch-input.nes \
  --stock-flow -o build/launch-stock.nes
```

`--stock-flow` restores stock `$CC06` so the stock team-select path runs and
END reaches `$98B9`; it is **test scaffolding** and the path that verifiably
reaches the field. Without it the bank-10 selector boots and its A hands off to
the hooked scene 18.

Build outputs are gitignored.

## 3. Key addresses

| Address | Meaning |
|---|---|
| `$07C3` | selected team (`$FF` = selector, otherwise team id) |
| `$04EF/$04F0` | matchup team IDs, set at `$9C00` from `$0650[$8941[...]]` |
| `$0650-$065F` | 16-team tournament buffer (seeded by `$FF60` from `$7700`) |
| `$074D-$0754` | packed password bytes, rebuilt by `$FF60` |
| `$0522` | lineup-init flag: `$FF` at boot, cleared by the stock team select |
| `$33/$34` | team ids used by the password/game path |
| `$047B` | scene id |
| `$047C` | scene sub-state / sub-handler index |
| `$047D` | frame flag: main loop waits for 0, NMI clears it, `$CC0E` sets it |
| `$0522` | lineup-init flag: `$FF` at boot, cleared by the stock team select; scene 15 skips its init when nonzero |
| `$2C` | NMI reentrancy guard (`$CD8A`) |
| `$2D` | bank-switch / deferred-task guard (`$C14E`, `$CF74`, `$CE45`) |
| `$AD` | PPU mask shadow (`$2001`), compared at `$CDBD` |
| `$CC52` | scene handler table, word at `$CC52 + 2*scene` |
| `$CCAC` | scene bank table, indexed `scene >> 1` |
| `$C232` | RTS-table dispatcher (pops its return address) |
| `$CC09` | stock main loop |
| `$CC0E` | main loop after `$047D` wait |
| `$98B9` | **scene-18 handler** (`END` / series init), bank 5 |
| `$98D5` | password buffer builder; polls `$047D`, needs NMI |
| `$995F` | **scene-19 handler** (password screen), bank 5 |
| `$CF74` | NMI/main-loop deferred-task helper; calls `$8048`/`$816C` in the **current bank** |
| `$C040` | ROM constant `$40` — **also MMC1 CHR-1. Never store to it.** |
| `$8000/$8100` | bracket screen / input in bank 11 |
| `$8200` | seed routine in bank 11 |
| `$B000/$B100/$B200` | codes / palette / display list |

## 4. The bridge

`tools/build_launch_bridge.py`:

- Bank 5 `$98B9`: `4C 20 FF EA EA EA` (`JMP $FF20`; NOPs). The scene-18
  handler is tail-jumped, so the stock caller's frame stays on the stack.
- Fixed bank `$FF20` (59 bytes, listed in the log): assert `$2C/$2D`, NMI
  off, bank 11, `JSR $8000` (bracket), bank 5, `$AD=$1E`, NMI on, `$047B=$12`,
  `$0522=0`, `JSR $FF60`, release guards, `JMP $98C0`.
- Fixed bank `$FF60` (`TEAMSETUP`): `$064F=$FF`, `$7700[0..15] -> $0650`,
  repack `$074D..$0754`. This is what makes the field teams match the
  bracket's first-round pair.
- The bracket is built with `--return-on-a`, so its A handler ends in `RTS`.

Production entry: the selector's A handler waits for release, drops the
`JSR $FF00` frame, sets `$047B=$12` and `JMP $CC09`, so the stock dispatcher
calls the hooked scene-18 handler with a normal frame. The stack is exactly
stock: `S=$FF` at the main loop after the resume.

## 5. The four root causes (short form)

1. **NMI deferred tasks are bank-relative.** `$CF74` calls `$8048`/`$816C` in
   whatever bank is mapped. With bank 11 mapped that is mid-instruction bracket
   code. Guard the bracket with `$2C=1` and `$2D=1`.
2. **`STA $C040` is an MMC1 CHR-1 write.** One stray bit de-aligns the shift
   register; the next bank-5 write latches bank 10. The bracket now NOPs those
   five bytes (`build_bracket_screen.py`).
3. **`$98D5` polls `$047D`, which only NMI clears.** Enable NMI and set
   `$AD=$1E` before calling it.
4. **Synthetic return frames are a trap.** v1's `JSR $FF20` + saved frame left
   `S` one low and returned mid-instruction. Use a tail `JMP` hook and a real
   `JSR` into the bracket.

## 6. What is still open

1. **Full 32-team tournament state.** The first-round matchup now matches the
   bracket: `$FF60` copies `$7700[0..15]` into `$0650`, and `$9C00` reads
   `$0650[$8941[3*$0746]]`. But the stock game still runs a 16-team / 15-match
   bracket (`$8941`, `$0746`). A true 32-slot, 5-round tournament needs that
   table and the advance/display logic ported (the `--state` work in
   `tools/build_32bracket.py` is the starting point).
2. **Password format** is still the stock 16-slot table (`$994F`); the
   32-team tournament state is not encoded.
3. **Bracket seeding in the stock flow** uses whatever `$07C3` held; in the
   selector flow it is the real pick (0–31).

## 7. Dead ends — do not repeat

- Cold-entering stock scenes: `$CC09`, `$CC0E`, `$D014`, `$B9C0`, `$995F`.
- Scene id poking without the dispatcher context (`$047B=$11`, `$13`, `$0F`).
- Registering a new scene by writing `$CCAC`/handler table by guessed offsets.
- `JMP` into the stock main loop; it destroys the RTS dispatch frames.
- Assuming `$CBE6` is a routine: it is `LDA #$00`.
- Assuming `$98B7` is the routine: it is data; real entry is `$98B9`.
- Enabling NMI immediately before a bank switch or `RTS` (NMI storm).
- **Believing `STA $C040` is harmless.** It is a mapper write.
- **Trusting a PC breakpoint without checking `$27`.** PC breakpoints are
  bank-agnostic; `$8162/$8172` hit in bank 2 are not the bracket.
- Trusting `stepInstructions` under NMI; use free-running `traceInstructions`.

## 8. Useful diagnostics

- `docs/LAUNCH-DEBUG-LOG.md` — loop-by-loop probes, proof of each root cause.
- `tools/romdev.py` — one-command romdev client (`load`, `step`, `press`, `pc`,
  `bp`, `trace`, `ram`, `save`, `loadstate`).
- `docs/AUTORUN-REPORT.md` — earlier chronological probe log.
- `.claude/skills/llbcs-32-team`, `.claude/skills/nes-romdev-debug`,
  `.claude/skills/nes-display-lists`.

## 9. Repo hygiene

- Commit/push after every green change.
- Never commit `build/` or `*.nes`.
- Run `tools/verify_regression.py` after any stock-side patch.
- Stock 16-team path must keep working.

## 10. Recommendation

The hard integration problem is solved. The next milestone is production
wiring (selector → `$07C3` → bracket → bridge) and the team handoff (`$33/$34`),
not more launch debugging. Ship the working hack if wiring slips.
