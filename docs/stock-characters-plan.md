# Original characters in the ballpark screens

The user requested original Little League players and spectators in place of
the newly drawn people on the mode menu and scoreboard. Keep the sunny
stadium architecture, readable navy panels and gold trim. Preserve the
original characters' silhouettes, faces and poses. Start with these two
screens; picker and victory-bracket changes are outside this first unit.

## Baseline and constraints

The accepted scoreboard is `build/scoreart32.nes`, SHA256
`2ae1a7ab2f75aeea4287943ba8153ab0ee0cc188a3d9a67f64bf7398f9e3360a`.
Its input is `build/modeart32.nes`, SHA256
`7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9`.
Both screens currently use 254 of 256 background tiles. Replacing people
must reclaim their tiles before adding original characters. Scoreboard
runtime glyphs, menu text/cursor fields, controls, music and game state
remain part of the accepted contract.

Use the existing ROM and screenshots to identify original graphics. A
screenshot is a pose reference, not evidence that a particular CHR bank
or palette is free. Record source bank/tile IDs, composition, flips,
transparency and recoloring in a checked character manifest. Prefer
extracting source pixels at build time over manually tracing faces.

## Work sequence

1. Ground the original character graphics and the current converters.
2. Compare two independent extraction/composition designs, then cross-judge.
3. Freeze the character manifest and chosen screen layouts.
4. Implement one guarded art stage with reproducible pxl assets.
5. Check real ROM renders, menu/score behavior, emulator transitions and
   the existing tournament gate before publishing.

The design rubric is authentic character reconstruction, NES palette/tile
fit, readable composition, preserved runtime contracts and reproducibility.

## Throughput checkpoint

- Blocking first steps. Locate the character tiles and verify reconstruction
  against the supplied poses before drawing the new compositions.
- Independent workstreams. Independent design experiments use separate
  scratch directories and do not modify the accepted assets.
- Shared mutable state. Freeze source mappings before one owner changes
  the two screen assets and their conversion pipeline.
- Smallest safe decomposition. The screens share original character data;
  one implementation owner avoids incompatible extraction conventions.

## Status

Started source-graphics investigation and design. The configured Grok
provider is disabled in this environment. Its panel lane is unavailable;
the configured Opus and Sol design lanes remain available. No provider
substitution is authorized or assumed.

## First candidate assessment

Sol's completed prototype reconstructs four intro compositions from CHR14
and PRG5 placement tables, plus a crowd rectangle from CHR04 and the stock
metatile decoder's data. Its supplied-image comparisons and ROM readbacks
support authentic source pixels. It proposes a data-only additive stage
with no changed executable bytes. The menu uses 187 tiles; the scoreboard
uses 254.

Root inspected both readback images. The source characters are recognizable,
but the complete 64-pixel vignettes retain rectangular sky, fence and dirt
patches plus clipped neighboring figures. These appear pasted onto the
stadium. The crowd crop also has visibly clipped figures. This is a useful
extraction proof, not yet the selected composition. Compare the second
candidate before choosing a base. Prefer deliberate character masks or
architectural framing that integrates the original poses without inventing
missing anatomy. Preserve the facial pixels when masking and recoloring.

Model the Domain shaped the proposed checked character manifest. Prove It
Works requires both source reconstruction checks and actual in-game renders;
static readbacks alone do not establish runtime acceptance.

## Second candidate and synthesis in progress

Opus reconstructs the same intro panels and uses the smaller CHR10 stands
crowd. Its masks remove source scenery, keep the faces, and retain outlines
against the destination background. A cream dugout makes the batter's hair
visible; a ticket counter hides the original pair's cropped lower edge.
The existing scoreboard's upper 160 pixels and menu's sign/choice board
remain unchanged. Measured budgets are 237 scoreboard tiles and 189 menu
tiles. The candidate changes data only in six previously owned regions.

Root inspected both before/after renders and prefers this composition
provisionally. Root reran its 30 checks, including CPU-model scene execution.
The independent cross-judge will assess masks, source fidelity, palette
claims, tile counts and the proposed production boundary before selection.

Implementation should generate stock-derived parts and asset blobs under
`build/` from the pinned input. Commit the source-reference manifest, pxl
composition and digest expectations. No extra third figure is needed in
this unit. The pair's palette-limited recolor is acceptable if the checked
source faces and silhouettes remain intact.

## Selected design and root corrections

The independent cross-judge selected Opus/B as the base, with Sol/A's
source-provenance records and concrete malformed-art controls as grafts.
The review is `/tmp/ll-stockcharacters-judge/review.md`. Original candidates
remain frozen. The corrected reference is `/tmp/ll-stockcharacters-final`.

Root corrected the small findings before implementation:

- Preserve source-zero ink at pair coordinates `(17,23)` and `(53,26)`.
- Remove the detached neighboring hand with crop-space exclusion
  `[55,0,9,18]`. The wider reviewed suggestion also clipped two cap pixels;
  the final exclusion preserves the cap and passes the seam check.
- Preserve 115 explicit source-zero head pixels inside the batter's reviewed
  source boundary. Pin all four complete masks, including transparent-source
  ink. A mutation that removes all ink must fail the independent mask check.
- Preserve the glove and cheer masks exactly, including the raised boot.
- Require both full sprite palettes to match accepted scoreart32. Permit
  only the three chosen background skin-slot changes across both screens.

The corrected prototype rebuilds and passes all 30 original checks, including
the CPU-model menu and three scoreboard cases. Root's additional mask and
palette checks pass, including all 32 sprite-slot mutation refusals (eight
at asset validation and 24 at stage validation). These are prototype/CPU
results, not emulator acceptance.

The user explicitly selected Opus for implementation after the configured
Grok provider was found disabled. The production implementation will use a
fresh isolated Opus worktree and the frozen corrected reference. Root owns
integration, emulator probes, full gates, docs and publishing.

## Production integration

The isolated Opus implementation reproduces the corrected prototype at
`a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55`.
Its full suite passes. Root applied the twelve-file patch and reproduced
the same ROM through the complete source pipeline. The runtime probe reuses
the accepted mode and scoreboard assertions with generated assets and
preflights every screenshot and audio destination before emulator access.

The root mode-menu emulator tour passes, including both controllers,
Analysis/password returns, palette memory and cursor sprites. The played
scoreboard tour and complete integrated gate are running. Final review and
release remain pending; see `docs/stockart32.md` for the maintained contract.

## Independent review and tooling corrections

Both production reviewers approve the frozen ROM. Root fixed their small
tooling findings: reject linked audio outputs, validate every crowd shirt
even when palettes repeat, and report malformed collection/identifier types
at the manifest boundary. Targeted regressions pass 63 malformed manifests,
both conflicting-shirt orders and 46 probe output collisions. Regeneration
still matches all 17 files and the ROM. The approved appearance is unchanged.

The WATCH game completes 4-6 with all played and planted boards checked.
The integrated regression gate remains the last acceptance step.

## Acceptance

The integrated gate passes on a5bf74ee. The full CPU suite finishes in
764.5 seconds; post-review boundary regressions pass separately. The stock
six games and all 31 tournament matches complete. Each tournament match has
stack FF and game-over 1; champion slot 62 is 07. Both emulator art tours
and source regeneration pass. Preview 6 is ready to publish.
