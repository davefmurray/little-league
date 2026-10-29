# Scoreboard art plan

Replace the green in-game scoreboard with the sunny ballpark style used by
modeart32. Preserve stock scoring, statistic formatting, names, controls,
audio and results routing. Input is modeart32 SHA256
`7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9`.

## Selected design

Use Opus layout B with the cross-judge's local bank-4 adapter. Keep the stock
numeric writer and its 78 runtime tile meanings. The inning header moves
from row 9 to 8, score rows from 10/12 to 9/11, and statistic rows from
18/20 to 15/17. Name sprites move by the matching amounts. The lower
80 pixels hold the crowd, families and vendor. This is a tighter layout,
not a uniform four-row translation.

The hook occupies bank 4 `$B3C0-$B3D3`. Reserve code at `$B800-$B87F`,
palette at `$B880-$B89F`, and nametable at `$B900-$BCFF`. Replace CHR05;
preserve shared CHR18, the fixed bank, and bank 14. Preserve both stock
vblank waits and the measured 41,436 CPU cycles between the second wait
and the stock writer. The judge's local prototype needs 27,012 delay
cycles. Final instruction placement must be measured again.

The independent review scores the original local design 13/20 and Opus
layout B 15/20. The original raw local adapter skipped a wait and changed
scene/audio timing. Adopt local storage only, with B's timing contract.
The other graft is an artwork pass for readable narrow digits and captions.
Do not rewrite scoring logic or change championship results routing.

## Work boundaries

- Blocking first steps: both candidate designs and cross-review are complete.
  Final art must convert within 256 tiles before its ROM is accepted.
- Independent workstreams: artwork stays in `/tmp/ll-scoreart32-art`;
  tool implementation gets a prepared worktree. Root owns emulator runs.
- Shared mutable state: frozen candidate directories remain read-only.
  Root integrates art and tools, then freezes the candidate for review.
- Smallest safe decomposition: one implementation owner builds the asset
  validator, converter, guarded builder and CPU suite together, because
  they share the geometry and runtime glyph contract.

## Acceptance requirements (completed)

Verify malformed assets and all output aliases, including an initially
missing generated PNG chosen as JSON or preview output. Reproduce the
PNGs and converted asset with pinned pxl. Compare score values, markers,
extra-inning pages, sprites, game RAM, exits and frame-stamped APU writes
with the stock stage. Exercise NMI injection and enforce the cycle budget.

Root must check actual-core live and Exhibition-final boards, palette,
mapped CHR, nametables, OAM, input, attract and game continuation. CHR05
has a latent preset-table reference; a broad mapper census must support
its reuse. Run the stock-six and full-31 tournament gates on the final
candidate. CPU prototypes alone do not satisfy runtime acceptance.

Accepted evidence and review resolutions are linked from [scoreart32.md](scoreart32.md).
The final source, CPU, emulator and stock-six/full-31 gates pass on `2ae1a7ab`.
The design review is retained in `verification/scoreart32-design-review.md`.

## Requested follow-up

After the scoreboard is complete, create a reusable `nes-pxl-screen-art`
skill describing the demonstrated pxl-to-NES-screen workflow. Ground its
pxl instructions in the upstream agent guide at
<https://github.com/augusto-scarvalho/claude-pxl#use-it-with-an-ai-agent>.
Cover deterministic art sources, tile and attribute budgets, dynamic
fields, guarded ROM integration, regeneration safety and actual-core
validation. Keep project-specific addresses in a worked example.

Add the skill and relevant catalog/documentation links to
<https://github.com/davefmurray/AWESOME-NESDEV>, validate the package, and
commit and push that repository. The user explicitly requested this
follow-up and push. Complete scoreboard acceptance first.
