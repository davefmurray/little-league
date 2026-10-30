# Home-run screen and animation redesign

Refresh the home-run celebration to match the accepted colorful ballpark
screens. Reuse original game characters and crowd where useful, with a
readable HOME RUN treatment and intentional animation. Preserve scoring,
runner advancement, gameplay state, audio and the return to play.

Input: analysisart32, SHA-256
`1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`.
Previous stages and shared graphics must remain reproducible.

## Work sequence

1. Trace entry, draw/update, graphics readers, palette changes, music/SFX and exit.
2. Produce two independent runnable designs, with timed frame previews.
3. Cross-judge visual coherence, source fidelity, animation/readability,
   integration safety and reproducible behavior; select and graft tests.
4. Implement a guarded additive stage, run CPU and real-core checks, review,
   then publish the updated ROM.

## Throughput and boundaries

Independent designs run in isolated scratch directories. Root owns real-core
sessions; designers use ROM decoding and CPU models only. No shared writes,
production edits or commits during design. Grok is disabled; use the established
Opus and Sol lanes. The animation and its state contracts, rather than drawing
speed, are the likely integration constraint. Measure them before selecting hooks.

Track immutable scene assets and animation frames, scene-state transitions,
owned ROM ranges and source provenance as explicit data. Stock-derived pixels
stay generated under build/, with references and hashes committed. Existing
output-path guards and natural temporary-path regressions apply to new tools.

## Root baseline

A controller-driven WATCH Exhibition (teams 11 and 29) reached the real
home-run draw at fixed `$D755`, scene 05/state 02. Root captured the entry
savestate and 550 subsequent frames under
`build/homerunart32-design/baseline-runtime/`. This is the accepted input ROM,
not a prototype. No scoring or scene RAM was planted.

The stock state-3 code at `$D77B` waits for song `$0A` to finish and alternates
CHR1 banks through `$D793` every eight frames. `$C5C4` at `$D767` consumes four
inline argument bytes; a linear disassembler must skip those before continuing.
The prototype must be judged against this event sequence and its field return.

## First prototype emulator check

Opus flipbook `1beb37e6…` is frozen (130 files). A second controller-driven
WATCH tour reached the same natural home run. All 550 sampled scene/state,
score, CHR-bank and song values equal the baseline, including return to
field scene 03 at frame 478. Captures are under `opus-runtime/`. This is
exploratory acceptance of the prototype, not final stage acceptance; the
second design and cross-judge are still pending.

## User selection and motion correction

The user selected First / Ballpark celebration (Opus flipbook), and explicitly
confirmed that the left pair and right batter stay visible but do not animate.
Hold both at frame-A positions in both CHR phases. Keep the cheerleader, crowd,
marquee and other environmental animation. Do not remove figures or change
layout, music, scoring or timing. Root's corrected scratch art lives under
`build/homerunart32-design/still-players/`; original candidates stay frozen.
The cross-judge still informs safety and test grafts, not the visual selection.

Corrected candidate SHA-256:
`a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.
It uses 223 tile pairs and 115 metatiles; no executable bytes change.
All 1,621 visible pair pixels and 803 batter pixels are identical across
phases. Cheer, crowd and marquee still change. The 22 static checks pass.
A natural emulator home run matches all 550 baseline state/score/CHR/song
samples. The corrected candidate passed the full prototype CPU replay suite.

## Design review accepted

The independent judge supports selected B, 23/25 versus A 15/25, including
the corrected still-player candidate. Required grafts are the all32 scoring,
HR/suppression/exit/next-batter matrices, both HUD expiry cases, attract START
and vblank phases. Production must register cheer-b and enforce the CHR15
second-reader reachability argument with executable stage checks. The
implementation lane has these constraints. No A rendering code is included.
Optional star positioning/title-flash changes are deferred to preserve the
user-approved composition. See verification/homerunart32-design-review.md.

## Corrected-candidate emulator acceptance so far

The natural event was a three-run homer (not the CPU model's solo fixture).
Input and corrected candidate match all 2,220 state/score/song/CHR/HR/game-over
samples across that event, a planted grand slam and a planted walk-off slam.
The walk-off fixture sets half 11 and batting/fielding side coherently; the
initial half-only fixture still credited the visiting side and was corrected.
The final score is 3–6 and the stock scoreboard follows.

A planted stock championship ending has 25 byte-identical screenshots and
identical 3,000-frame state records. A 9,000-frame attract trace and the ending
trace never map CHR15 into CHR0. The 600-frame WAV captures are byte-identical;
this is digital-output parity, not subjective listening or hardware evidence.

The 31-match CPU-forced field tournament passes with stack $FF each match and
champion 05. Its mapper trace covers 144,900 frames / 14,869,368 writes without
misalignment. This driver is named speed but still renders field gameplay;
a separate controller-selected stock SPEED simulation exercises the stock simulation
and the transient scene $1D store. Root retains these as prototype checks until
the production builder reproduces the same SHA.

## Production integration

The production stage reproduces the selected ROM and both frame renders exactly.
It registers cheer-b, enforces 19 shared-reader checks and adds the required
scoring, suppression, exit, HUD and attract tests. The build pipeline now ends
at homerunart32. Root is running the integrated gate and independent reviews.

The new real-core probe gives each planted runner a valid responsible pitcher.
The earlier prototype grand-slam plants omitted this field and could charge
mirrored RAM; those results do not establish pitcher-stat correctness. The
production probe checks the complete debit table and replays both ROMs.

Throughput checkpoint: the fixture-producing full gate runs concurrently with
read-only reviews; emulator probes use their own sessions and finish before
the gate reaches its tournament tours. No source changes to the approved art
or assembly are planned.

## Implementation review fixes

Sol found a cache-writer input collision and a sweep timeout tied to visible
frames. Root reproduced both against the frozen implementation in disposable
paths. Cache generation now receives the source path, preflights every planned
file and preserves unrelated provenance and foreign files. Recognized stale
caches can regenerate; malformed ownership requires a fresh directory. The
suite also protects its candidate path. The sweep bounds elapsed frames even
when the screen stays blank. Focused tests cover both failures.

The comment audit removed 23 narrative/stale comments and qualified the SPEED
scene explanation. Pinned pxl regeneration and the builder still produce
a66add03 exactly. Only source/provenance digests changed. The original review
freeze is retained; production-fixed-freeze.json records the updated files.

## Accepted

The final source build and full integrated gate pass. The HOME RUN suite
passes all 19 sections with ten newly played WATCH fixtures, the seventh
pitcher-debit mutation control, case/Unicode output checks and bounded
failure tests. Both independent reviews found no ROM/art defect. Root
resolved their output, cache and verification findings without changing
the selected ROM.

The stricter real-core event runs match all 2,220 state records and digital
audio, with both animation phases visible. The baseline six-game and final
31-match tournament gates pass; the final champion is 07 and every match
leaves stack $FF. The earlier mapper-census tournament had champion 05.
The two runs used different draws.
Preview 8 is the release target for this accepted stage.
