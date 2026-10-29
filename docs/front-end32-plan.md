# Random draws and a shared front end

Requested after preview 2: randomized tournaments, the same team picker in
Exhibition and Power Analysis, and a new title screen made with pxl.
Baseline is commit 030db80 and menuart32 SHA
bcb7fcdc2c1decd47de2f3504c8c81d907a3d195629a1526ff4b0e919a89f2a3.
This records the design process. Final acceptance is linked at the end.

## Definition of done

- New tournaments contain every team exactly once and produce varied draws
  from different draw seeds. Redraws never change the draw. A saved password
  reconstructs exactly the same teams, results and ownership. Existing v1
  passwords remain valid.
- Championship, Exhibition and Power Analysis use the flag-grid picker.
  All 32 teams are reachable. Exhibition retains 1P, 2P and WATCH ownership,
  selects both teams and plays high/high fixtures with the proper caches.
  Analysis shows the actual four ratings for every team and supports back.
- Browsing analysis or playing exhibition does not overwrite a saved active
  championship's heap, draw seed or ownership. Mode transitions cannot
  accidentally advance its bracket.
- The title uses editable pxl art and the established NES palette language.
  Start, mode selection, cancellation, music and attract behavior have an
  explicit contract and work through actual controller input.
- The final guarded build passes CPU regressions and negative controls,
  emulator navigation/audio checks and a full tournament. Independent review
  closes correctness findings before source push and ROM release.

## Workflow

1. Capture baseline flows and trace callers, state ownership, codec space
   and graphics reservations. Root owns the emulator.
2. Compare two independent architectures with CPU prototypes. Require
   distinct alternatives, then cross-judge against the rubric below.
3. Freeze a shared state/space contract and sequence independently verifiable
   stages. Prefer random draw/codec, shared picker routing, then title art;
   revise that order if evidence reveals a dependency.
4. Implement one accepted unit at a time. Compare generated artifacts and
   behavior against the frozen baseline. Keep old-stage inputs reproducible.
5. Review and test the complete user flows, update evidence and publish.

Both designs are complete. A fresh Sol cross-judge is comparing them against
the rubric while root verifies their integration claims. The configured
Grok lane remains unavailable from the
prior capability check; it is not replaced with another provider.

The rubric weights five concrete checks: exact state/codec compatibility;
complete callers and mode contracts; verified RAM/PRG/CHR ownership;
maintainable stage/API boundaries; and controller-visible experience with
reproducible art and meaningful negative controls.

## Initial evidence

The emulator shows Exhibition's 1P/2P/WATCH submenu followed by the old
world-map picker at scene0D/bank2. Power Analysis enters the same screen
with mode06E0=2. The 32-team ratings already reside at bank3 BC80, read
by AFE2. Bank1 9532 initializes exhibition ownership and clears04E2;
9527 selects analysis. Both proceed through scene0C. The new championship
picker instead lives in bank10. Its shared use needs a mode-specific
commit and return contract, not just a redirect to the tournament commit.

The existing 22-symbol codec stores a selected team and ascending draw,
not a random seed. It has reserved bits, but changing codec exporters
in place would also alter earlier pinned builds. The design must resolve
both payload compatibility and source-stage ownership explicitly.

Model the Domain motivates one explicit picker request/return contract
and a persistent tournament draw record. Prove It Works requires actual
mode transitions, decoded passwords and ROM output, not only mock screens.
Exhaust the Design Space motivates the two architecture candidates before
claiming new RAM or changing password semantics.

## Additional root probes

The stock Power Analysis details render team31's correct name and four
ratings when the selected ID and detail scene are injected for diagnosis.
B returns to the old picker. This is evidence for reusing the detail view,
not acceptance of controller-driven high-team selection.

The earlier menu stage conservatively avoided PRG-RAM access with CHR19
mapped. Its design explicitly called that a precaution after a historical
misaligned MMC1 sequence, not a proven CHR-ROM board requirement. A scratch
routine executed by the real core reads7760 and writes7761 correctly while
CHR1=19, with a CHR1=1 control. NESdev distinguishes SNROM's CHR-RAM-specific
RAM gating from ordinary MMC1 PRG-register gating; this ROM has128KiB CHR
ROM. New menu-state access needs an explicit mapper contract and tests,
not an unexamined extension of the old conservative rule.
Source: https://www.nesdev.org/wiki/INES_Mapper_001.

A full 31-match baseline trace observed zero writes to $7760-$777F over
159,896 scripted frames. A second complete run observed zero reads or
writes over the same frame count. Both finished with game-over 1, stack
$FF and champion $07. The second report is
`build/front-end32-design/wram-tournament-access.json`.

A separate 66,536-frame trace observed zero reads or writes in that range
while browsing Power Analysis details and returning to its picker, then
playing a complete Exhibition WATCH game and returning to the title.
Analysis visited 12 distinct stock teams; the exhibition finished with
teams $01/$05, score 0-5 and championship flag $04E2=0. Report and driver:
`build/front-end32-design/wram-stock-modes.json` and
`build/front-end32-design/tour_stock_modes.py`.

These are baseline allocation probes, not tests of suspended-series
restoration, which is not implemented yet. Startup before loadMedia returns,
state loading and direct CPU calls are outside the trace window. The
reports pin the baseline ROM hash. No persistent allocation is accepted
solely from a raw opcode scan.

## Prototype integration check

Root ran the Opus combined prototype (`b05b4a60`) on the real emulator core.
A suspended legacy series was injected at the Exhibition WATCH picker, then
controller input selected teams 31 and 30. The game finished 5-3 with
$04E2=0 and returned to the title. The heap, active-series markers, match
count, ownership mask and draw seed all remained identical. CONTINUE then
launched the expected next bracket pair $02/$03. Evidence is in
`build/front-end32-design/exhibition-preservation.json`; the game driver is
`probe_exhibition_preservation.py` in that directory. This is a prototype
integration check with an injected series, not final release acceptance.

This result challenges the need for a duplicate suspended-series snapshot.
The stock $CD5C routine clears $07ED, but a direct CPU call to that reset
routine does not establish that an ordinary return to the title invokes it.
The cross-judge must resolve the reachable callers before adding that state.

## Synthesis decision

Use Opus candidate B as the base. The independent judge scored B 18/20 and
Sol candidate A 14/20. Root's comparison also favors B. Both keep native
mode routes and the existing grid; B supplies integrated prototypes and
preserves the title's own music, CHR bank and attract loop. Grok was unavailable.

Three additive stages are the implementation boundary:

1. `draw32` adds a 14-bit saved draw seed and v2 password support.
2. `pick32` makes the flag grid serve Championship, Exhibition and Analysis.
3. `title32` replaces the title drawing and CHR $17, preserving its input,
   song $04 and attract/demo routes. Shared menu CHR $19 stays unchanged.

The canonical series remains the existing heap, masks and markers plus
$7760/$7761. No suspended snapshot or new fixed-bank gateway is required.
RESET ends the active series, as before. Ordinary mode changes preserve it.
New-series cancellation preserves the old series until confirmation.

Freeze the draw and wire format together. Seed 0 is the legacy ascending
order and emits byte-identical v1 passwords. Seeds 1..16383 initialize
xorshift16 with seed XOR $9E37, advance it twice, then shuffle slots 31..2
using j=1+((state*i)>>16). The chosen team stays in slot 0. New-series capture
uses (($33<<6) XOR $07F3) AND $3FFF, mapping zero to one. This is a finite,
timing-derived draw family, not uniform sampling of every possible bracket.

V2 byte 0 is $10. Draw-seed bits 0..7 occupy payload byte 11, bits 8..10
occupy byte 1 bits 5..7, and bits 11..13 occupy byte 2 bits 5..7. The existing
team, played, results, mask, whitening and CRC meanings stay unchanged. A v2
zero seed is invalid. The two design candidates' experimental v2 layouts
are incompatible; only B's interpretation will ship. Later incompatible
changes need a different version.

Graft Sol's exact runtime-cache/content and input-routing regressions,
correct-CRC invalid-form/failed-decode preservation tests, and clear host
names distinguishing selected team from draw seed. Keep the original v1
module and CLI semantics intact. Add judge tests for active-series cancel
and post-game-tail preservation. Do not graft the snapshot, replacement
title loop, larger seed format or new gateways.

Implementation ownership follows one coupled ROM owner for all three
builders and CPU suites. Root owns title artwork/assets, integration docs,
runtime drivers, the emulator, final review and publication. Tool and art
paths do not overlap. The title builder takes generated assets, so art can
improve while draw/picker work proceeds; freeze final title bytes before
its acceptance gate. The production artifact must reproduce pinned draw
and picker prototypes unless a verified defect justifies byte changes.

## Root art and controller probes

The root pxl title pass uses a larger wordmark, a stadium and floodlights,
plus baseballs around the edition line. It uses 201/256 tiles, retains the
original attribution and leaves shared menu assets unchanged. An exploratory
combined ROM with these assets hashes to `8f4a14a3`.

On that ROM, `tools/probe_frontend32.py` passed title CHR/song checks, attract
redraw and demo entry, and START from both pads after 120, 400, 1000 and 1550
frames. All 32 Analysis details opened, B returned to the selected team, and
B from the picker returned to the mode menu with both NMI guards clear.

A second Exhibition preservation probe used no injected game state. It typed
v2 code `4995FEC5ESTVP6KM5YCNYM` through the keyboard, backed out of its matchup,
selected high teams 31/30 in WATCH, and completed a 2-8 game. Title return
preserved all series fields. CONTINUE launched pair $18/$0A and exported the
identical password. These tests currently cover the prototype bytes; final
production builders and guards still require their own acceptance.

## Accepted implementation

The production builders reproduce the tested prototypes: draw32 `b263bd49`,
pick32 `8fb36a7b`, title32 `8f4a14a3`. See [draw acceptance](draw32.md),
[picker acceptance](pick32.md), [title acceptance](title32.md) and
[independent review](verification/frontend32-review.txt). Root fixed the review's
output-alias blocker without changing ROM bytes. Full source, CPU, runtime,
resume, memory and attract gates pass. The design's provisional statements
above describe the evidence available then, not the final acceptance state.
