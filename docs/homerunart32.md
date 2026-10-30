# HOME RUN ballpark celebration

The celebration uses a navy and gold HOME RUN marquee, sunny sky, original
crowd and original intro characters. The pair on the left and batter on the
right hold their positions and poses in both frames. The center cheerleader,
crowd, pennants and marquee animate at the stock eight-frame cadence.

`build/homerunart32.nes` builds from the accepted `build/analysisart32.nes`.
Its SHA-256 is
`a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.
The production build reproduces the user-approved stationary-player prototype
exactly. It changes 8,275 bytes inside 8,972 claimed bytes, with no executable
byte changes. It uses 223 of 256 tile pairs and 115 of 151 available metatiles.

## Rendering contract

The stock ball-in-play scene `$05` records the runs before showing the picture.
Its original states 1–3, music `$0A`, CHR flip and return path remain intact.
Each CHR phase supplies a complete background, so the animation needs no new
sprites, code or RAM. The 1,621 visible pair pixels and 803 batter pixels match
across both phases, checked in the render and the ROM's decoded picture.

| Region | Purpose |
|---|---|
| CHR `$04` and `$15` | Two animation frames. |
| PRG1 `$8DF0-$8F1F` | Map `$24` and its attributes. |
| PRG1 `$8400/$8500/$8600/$8700 + id` | Four plane bytes for each of 115 metatiles. |
| Fixed `$F8C0-$F8CF` | Background palette record `$0E`. |

The VICTORY ending and an unused split screen share the metatile set. Their
105 metatile ids retain all four original plane bytes. CHR `$15` has another
selector in the unused split screen, reached only through scene `$1C`.
Nineteen builder checks pin the reviewed direct-reader chains supporting its
exclusion from dispatched scenes.
SPEED simulation temporarily decrements `$1D` through `$1C` and `$1B`, then
restores its simulation scene before dispatch; that path is guarded too.
The scans do not cover all indexed/indirect stores, table-driven CHR loads,
non-immediate palette requests, masked CHR aliases or scene increments outside
banks 5/15. The whole-input hash freezes those bytes too. A new input pin needs
a new ownership audit; passing these scans alone is insufficient. The real-core
census provides complementary evidence, not a proof of all computed paths.

Original pixels are decoded from the input ROM. `cast.json` refers to approved
stockart32 parts and records the second cheer pose's source, mask and excluded
neighbor pixels. Only references, pxl sources and hashes are committed.
Parts, renders, assets and provenance are generated under `build/homerunart32/`.

## Reproduce

```sh
.venv/bin/python -B tools/homerunart32_convert.py --rom build/analysisart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/build_homerunart32.py build/analysisart32.nes -o build/homerunart32.nes
.venv/bin/python -B tools/test_homerunart32.py build/analysisart32.nes --candidate build/homerunart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/probe_homerunart32.py --rom build/homerunart32.nes --output build/homerunart32-events
```

The converter requires the pinned pxl checkout. `--check` regenerates in
scratch without installing; `--record` accepts an intentional source change
by updating this stage's digest registry after validation. The builder refuses
unregistered assets or ROM bytes. Outputs cannot alias protected inputs,
generated parts, fixture caches or earlier evidence, including through links.

The CPU fixture generator plays WATCH games from RESET and caches ten states
with provenance under `build/homerunart32-fixtures/`. A first full run takes
about 25 minutes to create those fixtures. Replays validate provenance before
loading them. `--quick` reduces the matrix; it is not the full acceptance gate.
These are locally generated, trusted pickle files. Their digests detect drift
and corruption; they do not authenticate a cache obtained from someone else.
Cache generation checks the source and candidate paths before any game runs.
It updates only files named by its own provenance. Stale recognized caches can
regenerate; unrelated files or malformed ownership records are preserved and
require a fresh cache directory. Sweeps time out on elapsed frames even when
a broken candidate never shows a picture.

## Verification

The [integrated gate](verification/homerunart32-gate.txt) passes every stage,
the six-game baseline and all 31 final-ROM tournament matches. Each match
reaches game-over, advances correctly and leaves the stack at `$FF`; team 07
wins. The final HOME RUN suite passes 19 sections in 1,789 seconds, including
1,357 seconds to generate ten fresh WATCH fixtures from RESET. It covers 512 scoring
cases, 64 HR-stat tails, 128 suppression cases, 384 exits, next-batter wrap,
both HUD-expiry forms, attract START and six vblank phases. Played and planted
replays compare RAM, WRAM, audio writes and timing with the pinned input.
Mutation controls reject broken code and shared-reader contracts.

On the exact output hash, root's prototype real-core checks completed a
natural three-run homer, a 31-match CPU-forced field tournament and both
password-version tours. The tournament checked stack `$FF` at each advance.
Its [mapper census](verification/homerunart32-prototype-full31-mapper.json)
covered 144,900 frames and 14,869,368 writes without misalignment. The driver
calls this SPEED mode but still renders field play. A separate controller-
selected stock SPEED simulation exercised the transient scene writes.

A planted championship ending produced 25 screenshots identical to the input,
including VICTORY, over a 3,000-frame trace. A separate 9,000-frame attract tour
and the ending never mapped CHR `$15` into CHR0. The 600-frame home-run WAV
captures were byte-identical. These are NTSC emulator results, not listening,
physical-hardware, PAL or second-emulator evidence.

The [production rebuild](verification/homerunart32-pipeline.txt) reproduces
the approved hash. The [production event probe](verification/homerunart32-events.txt)
passes the played three-run homer and both planted grand slams, including
the 3–6 walk-off and scoreboard return. Each case checks all 32 pitcher-debit
bytes and four visible cutscene frames against decoded ROM pixels. Earlier
prototype plants omitted explicit pitcher ownership and are superseded for
pitcher-stat claims.

The [paired baseline run](verification/homerunart32-event-parity.txt) matches
all 2,220 frame records and the 600-frame WAV byte for byte. The
[probe guard tests](verification/homerunart32-probe-guards.txt) refuse 23 unsafe
outputs before emulator dispatch and check valid pitcher ownership in plants.
Both independent implementation reviews are complete. Neither found a ROM or
art defect. The first review's cache-writer collision and sweep-timeout findings are fixed.
Root [reproduced both failures](verification/homerunart32-review-reproduction.txt)
against the frozen implementation. The
[focused regressions](verification/homerunart32-safety.txt) now refuse the
collisions, preserve existing files and bound the invisible-cutscene failure.
Comment cleanup regenerated identical ROM and image bytes; only source and
provenance digests changed. The second review's case/Unicode path bypass is
fixed in the shared directory guard. Forty alias tests cover the builder,
converter, probe and cache on this filesystem. Verification now checks installed
assets against the registry and rejects VICTORY corruption even when supplied
matching tampered assets. The probe requires four exact captures covering both frames,
and its checks remain active under Python optimization. A removed pitcher-debit
instruction fails the independent scoring oracle. See
[review resolution](verification/homerunart32-review-resolution.md).
The final HOME RUN suite, safety tests and emulator soaks ran after these
fixes. Earlier-stage CPU checks began before the last CLI-only guard edits;
the final dedicated guard regressions cover those shared helpers. The source
pipeline reproduces every pinned intermediate ROM and the final hash.

The CPU model approximates the PPU. The real-core probe checks visible pixels
in the 224-line NTSC crop. The three blank exit frames are navy instead of
black, and the right marquee star still touches the N, as in the approved art.
The title changes color every eight frames. Grand slams and walk-offs in the
probe are planted at a played fence event; they are not controller-played wins.
