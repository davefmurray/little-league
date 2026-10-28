# Current 32-team handoff

Start with [32-team-status.md](32-team-status.md),
[backlog.json](backlog.json) and [TODO-NEXT.md](../TODO-NEXT.md).
The old launch investigation is preserved in git history.

The accepted candidate is `build/teamnames32.nes`, SHA-256
`5998632da930ec063ea3029320a2b5d901043baa662add8adb8d14b809633f5c`.
The source pipeline reproduces it from the existing
`build/direct20-names.nes` bootstrap artifact. The original-ROM-only
bootstrap is not yet reproducible from committed scripts alone.

## Continue work

Run `python3 tools/backlog.py pick`. The remaining software tasks are
matchup round labels, high-team flag bounds and uniform palette bounds.
The bounded visual-table design lives in
`build/pitch-design/visual-tables.md` when that delegated design completes.
Root owns the romdev server and every emulator session. Parallel workers
must use isolated CPU tests and must not touch emulator sessions.

Physical hardware/audio validation remains blocked on an external setup.
Do not mark that task complete from emulator or savestate evidence.

## Accepted behavior and evidence

Names, all 32 human selections, completed-game bracket advancement,
password restore, LIST and CONTINUE have committed builders and tests.
See the linked status document for each stage and its limitations.
The final name ROM passes stock-six/full-31 SPEED gates. Control32 also
passes a full controller-only WATCH tournament. SPEED writes CPU control
flags on field entry; it does not prove human gameplay.

Team-name CPU probes use ending entries `$AC85` and `$ACCD`. Their old
one-byte-early entries executed PPU mirror space; the harness now rejects
execution below PRG ROM. Controller probes must follow team identity
through stock home/away swaps, rather than assume the human is side 0.

## Invariants

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

Known separate limitations include placeholder selector flags, no
eliminated-team marks in the bracket grid, rejection of old passwords,
and no physical hardware/audio validation.
