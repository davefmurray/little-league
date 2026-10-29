# Current 32-team handoff

Start with [32-team-status.md](32-team-status.md),
[backlog.json](backlog.json) and [TODO-NEXT.md](../TODO-NEXT.md).
The old launch investigation is preserved in git history.

The accepted candidate is `build/title32.nes`, SHA-256
`8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`.
The source pipeline reproduces it from the existing
`build/direct20-names.nes` bootstrap artifact. The original-ROM-only
bootstrap is not yet reproducible from committed scripts alone.

## Continue work

The software backlog is complete. `python3 tools/backlog.py pick` reports
no ready tasks. The final front-end stages are documented in
[draw32.md](draw32.md), [pick32.md](pick32.md) and [title32.md](title32.md), with source, CPU, controller and
stock-six/full-31 gate evidence. Root owns romdev sessions; any future
parallel workers must use isolated CPU tests.

Physical hardware/audio validation remains blocked on an external setup.
Do not mark that task complete from emulator or savestate evidence.

## Accepted behavior and evidence

Names, all 32 human selections, completed-game bracket advancement,
password restore, LIST and CONTINUE have committed builders and tests.
See the linked status document for each stage and its limitations.
The final title ROM passes stock-six/random-full-31 SPEED gates. Control32 also
passes a full controller-only WATCH tournament. SPEED writes CPU control
flags on field entry; it does not prove human gameplay.

Team-name CPU probes use ending entries `$AC85` and `$ACCD`. Their old
one-byte-early entries executed PPU mirror space; the harness now rejects
execution below PRG ROM. Controller probes must follow team identity
through stock home/away swaps, rather than assume the human is side 0.

## Invariants

- Random draw state is `$7760/$7761`; only new-series commit and valid
  password restore write it. Seed zero means legacy v1 order. Freeze the
  production v2 wire layout and shuffle together; unreleased experimental
  layouts are incompatible. Ordinary title return preserves the series;
  RESET ends it. There is no second suspended-series snapshot.
- The shared picker uses controller 2 for the second 2P choice, including B.
  Exhibition must enter through `$FC00` with `$04E2=0`.
- Title art owns CHR `$17`; menu art owns CHR `$19`. Keep earlier stage pins.

- `$06E2-$06F3` is the stock 18-byte lineup, nine rows per side. Each byte
  packs player number and field position. `$06F4` onward holds scores.
- Do not restore any pair-chain patch or the abandoned 32-byte initializer.
  Bank 7 is a stale copy and is not the live fixed bank.
- Bracket seeding happens once per series. `$07C3` is cleared by stock
  match initialization; redraws must retain the heap at `$7700`.
- CPU ownership uses `$074B/$074C/$07F1/$07F2`, set bit means CPU.
  The 32-team mode requires `$07ED != 0` and `$07EF == $32`.
- Preserve the input and output hashes of accepted stages. New repair
  stages build on the final candidate and guard every claimed ROM region.
- Use `tools/build_32team_full.py` and `tools/verify.sh --with-soak` for
  integrated validation. Read each stage document before claiming space.

Known separate limitations include omitted high-team gameplay flags,
stock-preset high-team uniforms, placeholder selector flags, no
eliminated-team marks in the bracket grid, rejection of old passwords,
and no physical hardware/audio validation.
