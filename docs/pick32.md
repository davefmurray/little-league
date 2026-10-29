# One picker for all 32 teams

The Championship flag grid also serves Exhibition and Power Analysis. The
existing mode menu, Exhibition submodes and Analysis rating screen stay in place.
Accepted after CPU tests, independent review and controller-driven runtime checks.

| Mode | Selection and controls |
|---|---|
| Championship | Controller 1 chooses one team. A commits a new random series; B cancels without replacing an existing series. |
| Exhibition 1P | Controller 1 chooses its team, then a CPU opponent. |
| Exhibition 2P | Controller 1 chooses the first team; controller 2 chooses the second. During the second choice, controller 2 also owns B. |
| Exhibition WATCH | Controller 1 chooses both CPU teams. |
| Power Analysis | A opens the selected team's existing rating screen. A or B returns to that team in the grid; B from the grid returns to the mode menu. |

Exhibition refuses identical teams. The first choice stays marked while choosing
the second; B returns to the first choice, and B again leaves the picker. Held
buttons are released at transitions. Exhibition and Analysis preserve the
active tournament's order, progress, ownership and draw seed.

The existing mode setup supplies 1P, 2P and WATCH ownership. Exhibition launches
through the runtime roster cache with both selected IDs and championship flag
$04E2 clear. It does not use the championship matchup initializer, which would
replace its teams and ownership. High-team rosters therefore have the same
15-player runtime shape and pitcher trailer used by championship games.

## Build and ownership

```sh
.venv/bin/python tools/build_pick32.py build/draw32.nes -o build/pick32.nes
.venv/bin/python tools/test_pick32.py build/draw32.nes --candidate build/pick32.nes
```

Input is draw32 `b263bd49`; output is
`8fb36a7b6f3fea03ec9b4bc76dce24141e7dc6522a0675a64b5d7b9135ac8cfa`.
The builder changes 721 bytes and guards complete reservations and dependencies.

| Bank | Reservation or hook | Purpose |
|---|---|---|
| 10 | `$8001–$8002` | Redirect grid entry to the shared picker. |
| 10 | `$B400–$BAFF` | Picker state machine and mode exits. |
| 10 | `$BB00–$BBFF` | Mode and selection-stage headers. |
| 2 | `$B969–$B96B` | Bridge the former world-map entry to the grid. |
| 1 | `$950A–$950C` | Remove the premature active-series marker before a new choice is confirmed. |

Picker scratch `$07C2/$07C4/$07C5` is transient. The stage introduces no
persistent series copy and changes no fixed-bank, header or CHR bytes. The
former world-map bytes remain in the ROM but are bypassed.

CPU regressions drive real routines and controller flows from RESET. They
cover cancellation with an active v1/v2 series, duplicate refusal, both ports,
roster contents and pointer restoration, input routing after side swaps,
failed-control variants and low-team exit parity. The CPU model's PPU timing
approximations are documented in `frontend32_test_machine.py`.

The real-core driver is `tools/probe_frontend32.py`. Its optional `--password`
types a code through the keyboard before changing modes. `--complete` plays
Exhibition through game over and checks title return and CONTINUE export. For
2P it pitches with the fielding controller and leaves the batting controller
idle; this is a controller-path regression, not a test of skilled human play.

## Runtime evidence

The final ROM completes high-team Exhibition in all three modes:
[1P](verification/frontend32-exhibition-1p.txt),
[2P](verification/frontend32-exhibition-2p.txt) and
[WATCH](verification/frontend32-exhibition-watch.txt). The 2P script reaches the
stock terminal tie after 36 half-innings. Each run types a v2 password first,
then checks the same heap, seed, masks and markers after title return. CONTINUE
exports the exact password and launches its expected pair. These are full-game
controller tests; they do not use the SPEED soak's ownership writes.

[All 32 Analysis teams](verification/frontend32-analysis-active.txt) also retain
that active series. [CPU regressions](verification/frontend32-pick-cpu.txt)
include old/new exit parity and both controller routes through side swaps.

```sh
for mode in 1p 2p watch; do
  .venv/bin/python tools/probe_frontend32.py --rom build/title32.nes     --output "build/exhibition-$mode" --tour exhibition --submode "$mode"     --complete --password 4995FEC5ESTVP6KM5YCNYM --session exhibition-check
done
.venv/bin/python tools/probe_frontend32.py --rom build/title32.nes   --output build/analysis-check --tour analysis   --password 4995FEC5ESTVP6KM5YCNYM --session analysis-check
```
