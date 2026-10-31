# Roster Lab independent team colors

User scope: fix the rating overlap and add team-color editing. The overlap
repair is deployed at e0c0853. Color design and cross-review are complete.

## Selected contract

Use Sol's single 96-byte table at fixed-bank $F380–$F3DF and three constant
changes, as selected in /tmp/ll-webcolors-judge/review.md. The whole-image
variant digests keep code immutable. Upgrade only when final colors differ
from the opened legacy Preview 8 baseline. Never downgrade an opened variant.
Unchanged and roster-only exports retain their existing bytes.

Every team owns uniform {cap, jersey, hair}. JSON v3 names these fields and
the NES palette; old roster imports retain current draft colors. No two teams
share a mutable uniform object. All 64 native values round-trip exactly.
The ordinary picker offers 53 swatches; Advanced accepts exact codes, with
an inline note for $0D. Labels are Cap & trim, Jersey and Hair.

The live batter preview decodes the user's admitted ROM. Numeric pose
metadata is approved for the implementation; no extracted pixels, role maps,
ROM files or sprite packs are committed. Without a ROM, use a clearly labeled
illustration. A color export needs an inline explanation, not another prompt.

Correct the stock CLI's wrong two-table color model in this change, with
regressions for cross-team corruption and refusal of 32-team color writes.
Old incorrectly extracted two-color fields must never be silently reinterpreted.
Correct the associated stale ROM-map documentation.

The batting side is $04ED; the fielding side is $04EE. Field slot 2 comes
from the batting team. Palette-set aliases include $2E–$30 and $94–$96.

## Work and acceptance

Blocking work: the two designs and independent judge established ownership,
reader behavior, exact identity and session semantics before implementation.
One isolated writer owns the adapter, UI, CLI and their coupled tests. The
root owns this plan, acceptance, review and deployment. No concurrent source
writers or extra abstraction layer are needed.

Acceptance includes all32 independent records, exact no-op/roster-only exports,
immutable masks, upgraded-source identity, all eight live palette callers,
JSON/session/reset/race behavior, legacy CLI safety, keyboard and responsive
browser checks, and deployed asset verification. CPU evidence is distinct
from emulator/hardware evidence. No full tournament soak is required for
three cycle-identical operand changes and a fixed data table.

Designs are frozen by build/webcolors-design/freeze.json (97 files).
Implementation must not alter either candidate, the judge, source ROMs or art.

## Integration progress

Integrated the 24-file implementation patch at e0c0853. Root reran all 134
Node tests with both real ROMs and the batter provenance fixture: all pass.
The actual-export CPU matrix and stock/Preview 8 CLI checks also pass.
Evidence is in docs/verification/webcolors-{node,cpu,cli}.txt.
The independent review snapshot is build/webcolors-review/source with the
24-file ledger source-hashes.json. UI and deployed acceptance remain pending.

Root browser checks now pass for opening, no-op export, the exact 99-byte
Venezuela recolor, reopening, native keyboard actions, Reset, Advanced codes
and five responsive widths. See verification/webcolors-browser.md.
Sol found one accessibility announcement defect; root fixed it and added
an event-path regression. All 135 tests pass on Node 20 and Node 26.
Both independent reviews are complete. Root fixed the announcement, Reset
focus and mismatched-baseline issues, corrected the small documentation and
CLI-advice findings, and made the below-black note accessible. The browser
confirmed Reset focus and the warning description. The stylesheet-size
warning is waived for the existing single-theme organization. See
verification/webcolors-review.md. Deployment is next.
