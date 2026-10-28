# Extended gameplay tables

`build/teamtables32.nes` builds on `cpu32.nes` and removes high-team reads
past three original 16-team table boundaries. The full pipeline now produces this candidate. Build and verify it with:

```sh
.venv/bin/python tools/build_32team_full.py
./tools/verify.sh --with-soak
```

The packed rating bonuses retain all 64 original bytes for teams 0-15.
Teams 16-31 receive zero bonuses. The original match-counter-to-tier map
and both saturating rating helpers stay intact. Bracket launches still
set the stock match counter to zero; this repair does not introduce a
new progression policy.

All four batting-bias readers in banks 0, 1, 3 and 5 use 32-byte tables.
Original teams retain their signed biases. High teams receive zero bias,
an explicit default because roster ratings do not define an AI strategy.
The original byte arithmetic, signed underflow and action branches remain.

The original two-byte ownership mask at `$074B/$074C` describes CPU
ownership, with a set bit selecting CPU control. It is not an elimination
mask. Low teams retain the original read and persistence behavior. High
teams return CPU control and skip persistence into the 16-bit mask. The
shared bit-mask utility and the separate result-mask reader remain intact.
High teams therefore remain unavailable for human control in this stage.
The selector and bracket ownership integration is tracked separately.

CPU tests execute the bonus loader and saturation helpers, all four
batting routines, both ownership paths, side swaps and controller routing.
They compare low-team RAM, registers, flags, stack and writes against the
input ROM. Seven unpatched negative controls reproduce the original bugs.
The emulator run completes 31 matches with stack `$FF` at every entry,
ending with champion `$06`. The speed driver forces computer control;
it does not prove manual gameplay or high-team selection. A separate
controller-only watch run stops at match 5 in scene `$03` with ownership
flags `$80/$00`, a game waiting for human input. The preserved stock mask
can still assign low teams to humans. The bracket ownership task must
replace that inherited policy within the new 32-team mode. The timeout is
recorded in [verification/teamtables32-watch.txt](verification/teamtables32-watch.txt).
The scene and ownership readback is recorded in the `watch-driver-match5`
blocked reason in [backlog.json](backlog.json).

The output SHA256 is
`775595bef3506de25f704fe0530f6833d8ce0541155110920e739f19425cd006`.
The builder changes exactly 274 bytes and preserves the CPU-stage tables
at bank5 `$BC80-$BCDF`. Input hash, byte, reservation and alias guards
protect the pinned intermediate artifacts. Evidence is saved in
[verification/teamtables32-cpu.txt](verification/teamtables32-cpu.txt) and
[verification/teamtables32-soak.txt](verification/teamtables32-soak.txt).

The complete build and verification gate also pass, recorded in
[verification/teamtables32-pipeline.txt](verification/teamtables32-pipeline.txt)
and [verification/teamtables32-gate.txt](verification/teamtables32-gate.txt).

This stage owns bank4 `$B700-$B77F`, banks0/3/5 `$BD00-$BD1F`,
bank1 `$BF00-$BF1F`, and bank5 `$BD40-$BD4E` and `$BD50-$BD5A`,
plus the guarded reader operands.

The original bank2 picker remains limited to teams0-15. Its reads at
`$BA45`, `$BB2E`, `$BB49`, `$BC70`, `$BCB7` and `$BD87` are not extended.
The high-team selector must bypass those paths. In particular, `$BB2E`
would corrupt low-team ownership bits for a high ID, and `$BA49/$BA53`
would address past the picker's zero-page team array. These sites are
part of the separate human-control integration.
