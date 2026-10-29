# Sunny ballpark mode menu

The mode menu shows a sunny ballpark entrance with families, young players,
bleacher crowds, a ticket queue and a popcorn vendor. The main menu,
Championship submenu and Exhibition submenu share the scene. Their original
controls, mode choices, music and sound effects remain.

The selected art replaces the rejected sparse navy-and-gold draft. Compact
labels leave the lower half for people and the stadium entrance. The editable
source is `art/modeart32/mode32.px.js`. Label positions, cursor origins and
palettes are in `layout.json`; `PXL.json` pins the renderer. The converted asset
is `data/modeart32/modeassets.json`. It uses 254 of 256 tiles, including 24
stock font and blank slots. Any art expansion must fit the two remaining tiles
or reclaim existing patterns.

## Build and regenerate

Run these commands from the repository root after building title32:

```sh
.venv/bin/python tools/modeart32_convert.py --rom build/title32.nes --check --pxl build/vendor/claude-pxl
.venv/bin/python tools/build_modeart32.py build/title32.nes -o build/modeart32.nes
.venv/bin/python tools/test_modeart32.py build/title32.nes --candidate build/modeart32.nes
```

Remove `--check` from the converter command to regenerate the PNGs and asset
JSON after an art edit. The converter checks NES colors, one palette per
16-by-16 attribute cell, the tile budget and text spans. It copies font glyphs
from the pinned ROM. The builder checks those glyphs against the source again.

Input title32 has SHA256
`8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`.
Output modeart32 has SHA256
`7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9`.
The stage changes 4,652 bytes. The source pipeline and verify script append it
after title32; earlier pinned stages remain reproducible.

## Byte ownership and runtime contract

| Region | Purpose |
|---|---|
| Bank 1 `$942A-$944A` | Draw request and matching bank-switch code. |
| Bank 1 `$9464-$9468`, `$9484-$9488`, `$948F-$9493` | Main, Exhibition and Championship text requests. |
| Bank 1 `$95E4-$95F5` | Nine cursor origins. Championship shares the main entries. |
| Bank 13 `$9000-$9FFF` | Nametable, palette, draw routine, bank-switch code and text lists. |
| CHR `$06` | Mode-menu background tiles. |

The 16-byte code at `$9432` is identical in banks 1 and 13. It calls the stock
mapper writer to enter bank 13, draws the requested content, then maps bank 1
before returning. Whole-region and dependency guards enforce this contract.
The fixed bank, other PRG banks and other CHR banks are byte-identical.

The draw blanks rendering and holds the stock short-NMI guard during its
1 KiB nametable upload. Submenu changes use the stock text engine, with at most
32 tiles per row. Every menu rewrites the union of its text spans, so shorter
labels clear the previous text. Cursor sprites remain in CHR `$1B`.
The stock NMI continues to update audio; no foreground audio tick is added.
The stage allocates no persistent RAM and does not write the bracket, draw
seed, ownership mask or series markers.

Static scans found CHR `$06` confined to the stock mode draw and no existing
bank-13 entry. The runtime mapper census records selections during specific
controller tours. Its scene contexts are sampled before and after windows of
up to 40 frames; they do not identify the exact scene at each write. CHR06 can
remain selected briefly during a transition before the next screen replaces it.

## Verification

The [asset check](verification/modeart32-assets.txt) reproduces the committed
PNGs with pinned pxl. The [source pipeline](verification/modeart32-pipeline.txt)
reproduces the ROM hash. The CPU suite checks all three menus, all nine
source-to-target overlays, cursor composition, stock exit and sound parity,
series preservation, 148 injected NMIs, malformed assets and output aliases.
Its timing checks use an approximate CPU/PPU model. The default-options
rerun is retained in [modeart32-cpu-default.txt](verification/modeart32-cpu-default.txt);
it predates the final missing-PNG regression. The final run with pxl executes
that same CPU suite plus renderer and collision checks.

The [controller menu tour](verification/modeart32-ui.txt) compares actual
nametables, palettes, mapped CHR and all four cursor sprites with the assets. It covers
both START ports, every choice, wrap, B and returns from Power Analysis and
the password keyboard's EXIT key. B on that keyboard deletes a character;
the probe selects EXIT to leave. Stock song 6 produces 183 APU state
transitions during the 180-frame idle sample. This measures activity, not
subjective audio quality.

The [combined gate](verification/modeart32-gate.txt) passes the stock six-game
regression and all 31 tournament games on the final ROM. Every tournament
game ends with game-over 1 and stack $FF; the champion is team $07.
The gate's CPU section predates the regeneration-only safety correction.
The ROM bytes did not change.

Independent review reproduced a nested PNG hardlink that allowed pxl
regeneration to overwrite an input ROM. The converter now checks every
generated destination before replacing any file. Sibling temporary files and
atomic replacement avoid truncating linked inodes. The
[regeneration regressions](verification/modeart32-regeneration.txt) cover
12 source, data and output aliases. A follow-up review found that a missing
PNG could also be chosen as the JSON or preview destination. Explicit outputs
now remain protected even when they equal a generated target. Both missing-file
cases fail before any persistent write, through the helper and the real pxl CLI.
The [final CPU run](verification/modeart32-cpu.txt) includes these regressions.
The [review record](verification/modeart32-review.txt) separates independent
ROM approval from root verification of the final tooling correction.

The [2P Exhibition run](verification/modeart32-2p.txt) reaches the stock
terminal tie, returns to the title and resumes the exact suspended tournament.
The [1P setup probe](verification/modeart32-1p.txt) checks both team picks,
ownership, duplicate refusal and roster caches. A separate
[human field probe](verification/modeart32-human.txt) reaches gameplay with
team 31 human and its canonical HUD label.
The extended 1P A-only driver stopped on a loose ball in half-inning 2.
That incomplete [diagnostic](verification/modeart32-1p-diagnostic.txt) is not
counted as a full-game pass. The stock fielding code is unchanged; manual
directional input on the live core moved the fielder.

The [WATCH tour](verification/modeart32-watch.txt) completes an Exhibition
game, returns through the full attract/demo cycle and resumes the suspended
tournament with its exact password. Its
[mapper census](verification/modeart32-watch-mapper.json) covers 95,811 frames
and 11,273,206 writes without serial misalignment. Observed PRG13 selections
occur only in windows touching mode-menu scenes. These are window-level
observations, not a proof of every possible indirect bank selector.

All [32 Analysis teams](verification/modeart32-analysis.txt) open and return
while preserving the active series. The [password and LIST flow](verification/modeart32-list.txt)
restores the full heap and ownership mask, then checks the next launched pair.
[Invalid-password re-entry](verification/modeart32-password.txt) also passes.
The [title tour](verification/modeart32-title.txt) checks both START ports and
the original attract redraw and demo entry.

Both independent ROM reviews approve the candidate. Their output-protection
findings are fixed without changing the ROM. The release is
[32-team preview 4](https://github.com/davefmurray/little-league/releases/tag/32-team-preview-4).

## Repeat the runtime checks

Each command loads the ROM into a separate romdev session. The saved series
code below is a fixed v2 fixture.

```sh
.venv/bin/python tools/probe_menu_chr.py --mode-context --report build/mode-menu-mapper.json tools/probe_modeart32.py --rom build/modeart32.nes --output build/modeart32-ui
.venv/bin/python tools/probe_frontend32.py --rom build/modeart32.nes --tour title --output build/modeart32-title --session modeart-title
.venv/bin/python tools/probe_frontend32.py --rom build/modeart32.nes --tour exhibition --submode 2p --teams 31 30 --password 4995FEC5ESTVP6KM5YCNYM --complete --output build/modeart32-2p --session modeart-2p
.venv/bin/python tools/probe_menu_chr.py --mode-context --report build/mode-watch-mapper.json tools/probe_frontend32.py --rom build/modeart32.nes --tour exhibition --submode watch --teams 31 30 --password 4995FEC5ESTVP6KM5YCNYM --complete --attract --output build/modeart32-watch --session modeart-watch
.venv/bin/python tools/probe_frontend32.py --rom build/modeart32.nes --tour analysis --password 4995FEC5ESTVP6KM5YCNYM --output build/modeart32-analysis --session modeart-analysis
.venv/bin/python tools/probe_password_ui.py --rom build/modeart32.nes --seed 31 --draw-seed 0x1234 --played 15 --list-flow --session modeart-list --shot build/modeart32-ui/list.png
```

## Limits

Figures and flags are simplified to fit NES tiles and palettes. Artwork is
static. Physical hardware and a second emulator implementation are untested.
CPU NMI injection visits each new instruction under the tested guard states,
not every possible timing phase. SPEED tournament tests force both sides to
CPU control. Separate Exhibition probes use controller input only.
