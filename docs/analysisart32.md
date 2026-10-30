# Power Analysis baseball card

Power Analysis shows the selected team's full name above four labeled
ratings: Batting, Running, Pitching and Defense. Each row has four baseball
sockets, an animated fill and its final value. The original crowd,
celebrating pair and cheerleader frame the card. A or B returns to the
same team in the shared picker; the visible hint says B BACK.

The stage builds `build/analysisart32.nes` from `build/stockart32.nes`.
The output SHA-256 is
`1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`.
It reproduces the selected prototype exactly. It changes 1,524 bytes in
nine guarded regions and adds 11 CHR06 patterns, leaving 59 unused tiles.
The four ratings and their original count-up cadence are unchanged.

## Rendering contract

The name uses the stock wide or narrow font in CHR18 above the existing
sprite-0 split. CHR06 supplies the card and figures below it. Row 8 has
identical patterns in both banks, hiding the bank swap within that strip.
Every earlier mode-menu tile at CHR06 `$00-$B9` remains unchanged.

The stock name and flag writers still run. Low teams retain their flags;
high teams retain the existing omission. Ball sprites use CHR1B tile `$61`
and sprite palette 1, which the existing flags do not use. Two waits on
the stock NMI latch preserve initialization timing. The fixed bank, input
loop, rating table, music and tournament state are unchanged.

After returning, the below-split shadow `$26` remains `$06` rather than
the previous `$18`. The picker retains `$047A=$06`, as in stock, but its
NMI takes the short path and skips CHR work. Both exits clear `$047A`
before drawing; presets that enable the split rewrite `$26`. The CPU
suite checks subsequent screens, and a real-core game completed after
visiting Analysis and resuming the tournament.

The new bank-3 pad follows the unchanged batting-bias table at
`$BD00-$BD1F`. Its indexed reader uses a live team id in 0–31; the
builder pins both the table and its reader contract.

| Bank | Inclusive region | Purpose |
|---|---|---|
| PRG3 | `$AF80-$AF91`, `$AF9B-$AF9F`, `$AFB9-$AFBB` | Initialization and marker-draw hooks. |
| PRG3 | `$BD20-$BD2F` | Bank-switch pad. |
| PRG3 | `$BD30-$BDB7` | Digits, balls and geometry tables. |
| PRG13 | `$A000-$A3FF` | Nametable and attributes. |
| PRG13 | `$A400-$A4FF` | Palette, placement tables and card loader. |
| PRG13 | `$BD20-$BD2F` | Matching bank-switch pad. |
| CHR06 | Tiles `$BA-$FF` | Eleven new patterns; other slots remain blank. |

## Reproduce

```sh
.venv/bin/python -B tools/analysisart32_convert.py --rom build/stockart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/build_analysisart32.py build/stockart32.nes -o build/analysisart32.nes
.venv/bin/python -B tools/test_analysisart32.py build/stockart32.nes --candidate build/analysisart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/probe_analysisart32.py --rom build/analysisart32.nes --output build/analysisart32-runtime --session analysisart32-final
```

Only pxl/layout/placement references and the digest registry are tracked.
Stock-derived PNGs, assets, previews and provenance are generated under
`build/analysisart32/`. The converter reuses the approved stockart32 masks
and rejects changes to their digests. `--check` regenerates in scratch
without installation. An intentional change requires `--record`; it
updates only this stage's registry after validation. The builder checks
source pins, exact owned bytes and the registered output hash.

## Verification status

The [integrated gate](verification/analysisart32-gate.txt) passes all CPU
stages, the six-game baseline and all 31 tournament matches. Every match
reaches game-over, advances the bracket and leaves the stack at `$FF`;
team 07 wins. The Analysis CPU suite passes 23 sections with pinned pxl,
including all 32 teams, animation/APU parity, 182 NMI injections,
independent socket alignment and earlier-screen returns.

The [real-core tour](verification/analysisart32-ui.txt) checks all 32
cards and 27 entry/count-up frames against ROM reconstruction, including
the split strip at lines 64–72. A/B returns to the selected picker cell
and preserves an active v2 championship. The
[mapper census](verification/analysisart32-mapper.json) covers 6,467
frames and 158,713 writes with no misaligned writes. Audio changes 178
times over 180 sampled frames. The separate audio capture advances frames
outside the mapper trace, as its report states.

After the Analysis tour, a [resumed game](verification/analysisart32-after-analysis.txt)
finishes 7–3, credits team 18 and advances match 24 to 25 with stack `$FF`.
This is a SPEED run. An initial attempt exposed a driver assumption that
only controller 1 could own the lineup editor; the driver now checks both
ports, with [unit coverage](verification/analysisart32-lineup-driver.txt).
It is not evidence of a completed WATCH game on this ROM.

Both independent reviews found no ROM defect. Their tool findings and
final CLI regressions are recorded in
[review resolution](verification/analysisart32-review-resolution.md).
The final path-guard changes do not alter ROM or asset bytes; the full
tournament gate predates those CLI-only changes.

The CPU model approximates sprite-0 hits and PPU fetch timing. Real-core
screenshots cover NTSC's visible 224-line crop; physical hardware, PAL
and a second emulator remain unverified. APU activity is not a listening
test. The whole-tournament SPEED gate forces CPU field ownership.
