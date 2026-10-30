# Power Analysis redesign

Replace the sparse ratings screen with a readable ballpark-style team card.
Keep the four real team ratings, all 32 names, the shared picker, return
controls, music and any suspended championship state. Use the original
characters where the layout benefits from them.

## Grounding

Input stockart32 is `a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55`.
The baseline controller tour opens all 32 teams and returns to each selected
team without changing an active v2 series. The current detail scene runs in
bank 3, with CHR1 mapped to the shared CHR18 and CHR0 to CHR1B. Its four-byte
rating records live at bank 3 `$BC80-$BCFF`; each value is 1 through 4.
The old display animates a small sprite-based radar chart.

The rendering contract must establish each rating's axis, every dynamic
writer, entry/exit timing and all consumers of proposed CHR space. Replacing
shared CHR18 globally is not a safe default. Existing mode art has 70 unused
tile slots and may offer reuse, subject to actual reference checks.

## Throughput checkpoint

- Blocking first steps. Capture the current screen and actual ratings,
  identify shared CHR and trace the scene's writers before choosing storage.
- Independent workstreams. Sol and Opus develop separate scratch designs,
  source audits and CPU prototypes. The configured Grok provider remains
  disabled; it is not silently replaced.
- Shared mutable state. Root alone uses the emulator. Freeze both design
  candidates before independent judging. One owner integrates the selected
  renderer and assets after the storage contract is agreed.
- Smallest safe decomposition. One implementation owns the ratings model,
  layout, converter and byte guards so values and visual geometry cannot
  drift between competing writers.

## Design comparison

Compare a four-stat board with a larger diamond/radar composition. Grade
each on rating readability and truthful values, compatibility with the
accepted colorful style, verified tile/ROM ownership, preserved controls
and audio, and reproducible conversion with useful negative controls.

Model the Domain means defining one team-rating record and one layout
contract before renderer code. Exhaust the Design Space means measuring
both compositions instead of polishing the first sketch. Prove It Works
requires real ROM readbacks and emulator paths before acceptance.

## Status

Accepted: selected B is integrated as analysisart32, byte-identical to the
frozen prototype. Both reviews found no ROM defect. The all-32-team tour,
phase/split checks, post-Analysis continuation and stock-six/full-31 gate
pass. See [acceptance and limits](analysisart32.md).

## First candidate

Sol's four-stat board uses 25 new CHR06 tiles, 211 total, leaving 45 free.
It preserves the four real ratings, labels them explicitly and keeps the
original animation counters and A/B return state machine. The alternative
connected-background radar overflowed its all-team tile union; this does
not rule out a radar built with sprites.

Its source trace establishes rating order as Batting, Running, Pitching,
Defense. The shared sprite-0 marker matters to stock NMI/audio timing, so
its hidden position and solid background hit pixels remain. The candidate
claims bank3 AF71-AF9F and AFF8-B0AF, bank13 A000-AFFF, and CHR06 BA-D2.
No earlier mode-owned tile changes.

Root froze the candidate and ran the existing controller Analysis tour on
its ROM. All 32 teams opened and returned to the selected picker cell while
preserving an active v2 championship. Root inspected team31 in the emulator;
the four displayed ratings match 3,3,4,2. This is preliminary real-core
coverage, not full transition/audio/tournament acceptance. The second
candidate has since completed; no production base is selected yet.

Root found one presentation issue in the first emulator capture: romdev
outputs 256x224, cropping the outer eight lines of the 256x240 NES frame.
The candidate's A/B hint is at the bottom edge and disappears in that
capture. The selected design must put essential hints inside the visible
224-line area, with margin. This was not caught by its full-frame CPU PNGs.

## Second candidate and preliminary assessment

Opus's baseball-marker card uses 11 new CHR06 tiles, leaving 59 free. It
keeps the stock name fonts in CHR18 above the existing sprite-0 split and
uses CHR06 below it. The split row has matching patterns in both banks.
Ratings still come directly from the unchanged table and retain their
count-up counters; baseball sprites replace the radar markers.

Root froze all 147 candidate files, then ran the existing all-32-team
emulator tour on SHA 1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e.
All teams opened and returned to the same cell with the active v2 series
preserved. The team31 capture shows 3,3,4,2 and a visible B BACK hint.
The preliminary preference is this card: stock name handling, baseball
markers and fewer additional tiles. The independent judge must assess
the split/timing contract and source guards before it becomes the base.

Possible presentation grafts are a POWER ANALYSIS caption and an accurate
A/B BACK hint. These need a palette/geometry check; they are not assumed
safe or required to change the renderer. Earlier mode-owned tiles and
the approved original-character masks must remain unchanged.

## Selected design

The user selected B, the baseball-marker card. Its composition is the
production base. Independent review resolved rendering, timing and
regression risks without changing that visual choice.
Retain the selected artwork unless a correctness or readability fix is
needed. Optional caption and hint changes are not a reason to redesign it.

## Synthesis and implementation contract

The independent judge supports B, scoring it 18/20 against A's 16/20.
The judge reconstructed all 64 existing A/B emulator captures independently
from ROM data with no pixel differences. B retains the authoritative rating
table and stock name/flag writers with fewer new patterns and reservations.
The selected composition stays byte-for-byte intact, including B BACK.
No caption or hint redesign is included.

Grafts from A are verification techniques only: independent field geometry,
held-input/phase cases, source-pixel provenance and earlier-screen return
fixtures. Its copied ratings/names, bar renderer and timing waits are not
part of the production implementation.

Required production corrections from the judge are nonzero CLI status on
failed checks, an independent socket-to-ball alignment oracle, a real title
template/name-region assertion, and NMI comparisons that include stack,
physical/logical bank, serial mapper state, guards and active series.
The frozen renderer itself requires no byte change. The target output is
1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e.

One isolated implementation owner will add art references, a digest registry,
converter, guarded builder and CPU tests. Stock-derived outputs stay under
build/analysisart32. Earlier stages and their tests remain unchanged. Root
owns pipeline integration, the real-core phase/split/audio probe, mapper
census, stock-six/full-31 gates, independent final review and publishing.

The judge report and rerunnable evidence are in
/tmp/ll-analysisart32-judge/review.md. The frozen B design is in
/tmp/ll-analysisart32-opus/design.md. Both freeze ledgers remain unchanged.
