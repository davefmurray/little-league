# Sunny ballpark scoreboard

The in-game box score uses navy panels, cream numbers, gold trim, sky,
grandstands, families and a popcorn vendor. It keeps the stock score and
statistic writers. Extra innings, X markers, team labels, controls and
music follow the existing game rules.

The editable source is `art/scoreart32/score32.px.js`. Its layout file
defines the four background palettes and static text. `PXL.json` pins
the renderer. The converted asset uses 254 of 256 tiles, including 78
runtime glyph IDs. Two tiles remain free.

## Rebuild

```sh
.venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --check --pxl build/vendor/claude-pxl
.venv/bin/python tools/build_scoreart32.py build/modeart32.nes -o build/scoreart32.nes
.venv/bin/python tools/test_scoreart32.py build/modeart32.nes --candidate build/scoreart32.nes --pxl build/vendor/claude-pxl
```

Omit `--check` to regenerate assets after editing the source. Regeneration
renders into temporary storage, checks every destination, and replaces
files atomically. Output aliases, including missing generated PNGs named
as JSON or preview destinations, are rejected.

Input modeart32 SHA256 is
`7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9`.
Output scoreart32 SHA256 is
`2ae1a7ab2f75aeea4287943ba8153ab0ee0cc188a3d9a67f64bf7398f9e3360a`.
The stage changes 4,712 bytes. The full pipeline appends it after modeart32.

## ROM ownership

| Region | Use |
|---|---|
| Bank 4 `$B3C0-$B3D3` | Replace palette and background draw calls. |
| Bank 4 `$B41D`, `$B54A-$B559`, `$B5BE-$B5C1` | Header, score/stat rows and name sprite positions. |
| Bank 4 `$B800-$B87F` | Drawing routine and timing compensation. |
| Bank 4 `$B880-$B89F` | Local palette. |
| Bank 4 `$B900-$BCFF` | Nametable and attributes. |
| CHR `$05` | Background and numeric glyphs. |

The fixed bank, bank 14 and shared sprite/font CHR18 remain unchanged.
No persistent RAM is allocated. The line scores move up one tile row and
statistics up three, leaving 80 pixels for the crowd scene.

Both stock vblank waits remain. The local copy takes 14,424 CPU cycles;
27,012 compensation cycles preserve the stock 41,436-cycle interval from
the second wait to the score writer. Tests measure this interval and also
compare controller, scene and APU timelines. These counts depend on the
routine's current placement and must be remeasured if it changes.

## Verification

The [CPU log](verification/scoreart32-final-cpu.txt) records the full suite with
pinned pxl regeneration. It covers 409 drawn boards, all 256 byte values,
extra-inning pages, all 32 teams, 13 exits, 15 phase/song variants and
40 injected NMI positions. Eight broken candidates fail the same checks.
The CPU model approximates PPU timing.

The [emulator probe](verification/scoreart32-ui.txt) plays a WATCH Exhibition
between teams 31 and 30. Each captured board must match all 1,024 nametable
and attribute bytes, including expected scores from RAM, the local palette,
CHR05/18 and the uploaded OAM. The game finishes 3-0 and returns to title.
Five extra-inning/marker cases are explicitly planted in RAM between saved
state restores; they are not claimed as played innings.

The [source rebuild](verification/scoreart32-pipeline.txt) reproduces the
accepted hash. The [integrated gate](verification/scoreart32-gate.txt) passes
the stock six games and all 31 random tournament games, champion 07, with
stack FF and game-over 1 throughout. SPEED mode forces CPU ownership.
The final post-review CPU run passes separately; the integrated gate used
the same ROM before the tooling-only review fixes.

The [mapper census](verification/scoreart32-mapper.json) covers 72,964 frames
of a separate WATCH game and the planted cases. It records no misaligned
mapper writes or bank-14 selection. CHR05 occurs only in scoreboard/transition
windows. This trace's game finishes 4-6; it is a different run from the 3-0
UI probe. Scene attribution uses windows of up to 40 frames.
[Attract](verification/scoreart32-attract.txt) and
[all-32 Analysis](verification/scoreart32-analysis.txt) tours also pass,
with no CHR05 use in their mapper traces. Attract coverage reaches the demo,
not its full game completion. Static scans and these tours support reuse
of CHR05; they do not prove every possible computed path.

The [independent review](verification/scoreart32-review.md) found no ROM
blocker. Its screenshot-output alias finding and two small tooling/doc
findings are resolved in the [resolution record](verification/scoreart32-review-resolution.md).
[Guard regressions](verification/scoreart32-review-fixes.txt) run without
contacting the emulator. Use a fresh output directory for controller probes
so captures cannot replace protected evidence or sources.

## Limits

Adjacent two-digit totals still have stock's uniform eight-pixel spacing.
Labels and rules identify their columns. Statistics use compact captions.
Stock drops hundreds from counters and always displays E as zero; this art
stage preserves those rules. The championship result gate returns directly
to the bracket, so its final box score is not held on screen. Physical
hardware and a second emulator remain unverified.
