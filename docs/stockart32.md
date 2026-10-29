# Original characters in the ballpark screens

The mode menu and scoreboard reuse the game's intro characters and stands
crowd inside the new ballpark architecture. The menu has the cheerleader
and celebrating pair at the gate. The scoreboard has the batter and glove
kid below the score panels. Both keep their accepted text, numeric glyphs,
cursor, input, music and scoring code.

The stage builds `build/stockart32.nes` from `build/scoreart32.nes`. Its
SHA-256 is `a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55`.
Exactly 4,634 bytes change inside six existing data regions. No executable
byte changes. The mode menu uses 186 of 256 tiles; the scoreboard uses 237.

## Sources and composition

`art/stockart32/characters.json` describes source ranges, crops, masks,
color maps and placements. Intro poses are reconstructed from CHR14 and
bank-5 sprite placement data. The crowd uses CHR10 metatiles and the stock
palette. Its arrangement is observed from the supplied screenshot; each
tile and color is independently decoded from the ROM.

Source color zero originally showed the black backdrop through transparent
sprites. The masks preserve explicit face and hair pixels from the reviewed
composition, but do not reproduce every source-zero outline pixel. The pair loses a detached
hand belonging to its neighboring source figure. Its own cap and face
remain. A counter hides the source picture's cropped lower edge.

The pair's left jersey becomes red to fit the NES background palette.
Three background skin-color slots change; both complete sprite palettes
and the text palette remain identical. Figures are baked into background
tiles, so they consume no extra runtime sprite slots or scanline budget.

## Reproduce

```sh
.venv/bin/python -B tools/stockart32_convert.py --rom build/scoreart32.nes --font-rom build/modeart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/build_stockart32.py build/scoreart32.nes -o build/stockart32.nes
.venv/bin/python -B tools/test_stockart32.py --pxl build/vendor/claude-pxl --candidate build/stockart32.nes
```

The converter generates parts, scenes, previews, asset JSON and provenance
under `build/stockart32/`. Only reference manifests, pxl source and a digest
registry are tracked. The normal command refuses unrecorded outputs;
`--check` regenerates in scratch and writes nothing. An intentional art
change requires `--record`, which updates the registry after validation.
The renderer commit and toolchain are pinned. PNG-encoder changes can
invalidate digests even if pixels remain identical.

The full source pipeline now ends at this stage. Earlier builders and
accepted hashes remain reproducible.

## Owned regions

| Region | Data |
|---|---|
| Bank 13 `$9000-$93FF` | Mode nametable and attributes. |
| Bank 13 `$9400-$941F` | Mode palette. |
| CHR `$06` | Mode background tiles. |
| Bank 4 `$B880-$B89F` | Scoreboard palette. |
| Bank 4 `$B900-$BCFF` | Scoreboard nametable and attributes. |
| CHR `$05` | Scoreboard tiles; all 78 runtime glyphs preserved. |

## Verification status

The root's full CPU suite passes in the [integrated log](verification/stockart32-gate.txt). It covers independent source
decoding, all 14 placements through ROM readback, mask and palette negative
controls, malformed manifests, output aliases and deterministic rendering.
It also runs the accepted score/menu runtime checks against the new assets,
including 409 boards, exit/audio parity, the 41,436-cycle draw interval and
40 scoreboard plus 148 menu NMI injections. The model approximates the PPU.

The [root source rebuild](verification/stockart32-pipeline.txt) reproduces
the pinned output. The [mode emulator tour](verification/stockart32-mode-ui.txt)
passes both controllers, all three menus, exact nametable/CHR/palette/cursor
checks and returns from Analysis and password entry. Its audio probe records
183 APU transitions over 180 frames. Those audio frames are outside the
[mapper census](verification/stockart32-mode-mapper.json).

The [scoreboard emulator tour](verification/stockart32-score-ui.txt) completes
a WATCH Exhibition between teams 31 and 30, ending 4-6 and returning to title.
All 12 played boards and five planted extra-inning/marker boards match the
expected 1,024-byte screen, palette, CHR and OAM. Its
[mapper census](verification/stockart32-score-mapper.json) covers 72,964 frames,
with no misaligned writes or bank-14 selection. Scene attribution uses
windows of up to 40 frames.

Both independent reviews found no ROM blocker. The
[Sol report](verification/stockart32-review-sol.md) and
[Opus report](verification/stockart32-review-opus.md) document independent
source decoding, exact rebuilds and output protection. Tool-only corrections
are recorded in the [resolution](verification/stockart32-review-resolution.md).
The [integrated gate](verification/stockart32-gate.txt) passes the stock six
games and all 31 random-tournament games on the final ROM. Every tournament
match reports game-over 1 and stack FF; champion slot 62 contains team 07.
SPEED forces CPU control on the field. The separate WATCH game uses menu
ownership and controller input.

## Limits

Characters are static and palette-constrained. No new animation is added.
The cyan-to-red pair recolor also changes small shirt-shading patches.
Some source-zero outlines show the destination wall; the frozen mask
checks pin this reviewed appearance rather than asserting every black
source pixel is retained.
Adjacent two-digit totals retain stock spacing. The scoreboard probe's
extra-inning and marker cases are explicitly planted RAM states, separate
from its played WATCH game. SPEED tournament gates force CPU ownership.
Physical hardware and a second emulator remain unverified. See the
[scoreboard contract](scoreart32.md) and [mode-menu contract](modeart32.md)
for inherited limits.
