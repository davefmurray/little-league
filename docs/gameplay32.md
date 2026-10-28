# Gameplay build

The gameplay candidate preserves the stock nine-player lineup for each
side. Tournament team IDs select the roster and lineup source. They are
not stored as a 32-entry table at `$06E2`. That address holds 18 packed
lineup bytes, followed by score and inning data at `$06F4`.

Three repairs build on the pinned `direct31.nes` baseline.

- The lineup loader reads teams 28-31 through a second source window so
  its eight-bit index cannot wrap inside a nine-player record.
- The display-list row writer skips empty text before emitting a header.
  This avoids 256 iterations in both the buffer writer and PPU consumer.
- The bracket launch restores the stack pointer before jumping back to
  the main frame loop. The old launch leaked two bytes per match until
  palette writes overlapped active return addresses.

The normal order-menu exit is retained. No pair-capture, forced-copy,
identity-lineup, extended group-table, or forced-menu-exit patch is used.
The pitcher routine at bank4 `$AD5C` and score initialization stay intact.

## Build and verify

Run the pipeline with the repository Python environment:

```sh
.venv/bin/python tools/build_32team_full.py
./tools/verify.sh --with-soak
```

The pipeline retains `build/direct31.nes` as the pinned regression baseline
and writes these core repairs to `build/gameplay32.nes`. It then builds
[cpu32](cpu32.md), which repairs CPU pitching tables and the runtime
roster view. These files are
ignored by git. The repair deliberately pins the exact baseline independently
of the manifest. Updating the manifest alone does not authorize a new
input; roster changes require reviewing and updating the repair pin too.
The pipeline still requires the existing
`build/direct20-names.nes` intermediate documented in the builder.

The CPU tests exercise all 32 teams on both sides, the pitcher entry,
empty and populated display rows through the PPU consumer, and the launch
stack. The runtime
gate follows all 31 matches through the real emulator and checks the
stack pointer at every match entry.

The speed-mode driver assigns both teams to the computer. Its score rule
awards a tie to the first team, matching the current bracket hook. Passing
this gate proves scene progression, winner writes and stable stack usage.
It does not establish regulation tie handling, manual gameplay, hardware
compatibility, audio quality, or password resume support.

The gameplay32 intermediate still has high-team defects in CPU pitching
tables and the runtime pitcher-record view; the cpu32 stage repairs them.
Per-round modifiers, the human-control mask and batting bias remain open
in `docs/backlog.json`. The empty-row branch is
covered by CPU producer/consumer tests; its execution was not measured
during the tournament soak.

## Design decision

The source review found that the proposed 16-by-2 group table had the wrong
meaning and overlapped score RAM. Widening that table and adding an inverse
player lookup were considered. Both add state that the working stock
lineup consumers do not require. The selected implementation preserves
those consumers and fixes the source-index and launch boundaries.

The independent review caught a defect in the initial row guard, which
still emitted a zero-count header. The PPU consumer interprets count zero
as 256 writes. The corrected guard runs at `$C790` before any header is
written, and the CPU regression counts `$2007` writes after `$C53A`.

