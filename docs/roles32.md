# Runtime player roles

`build/roles32.nes` corrects pitcher classification in the runtime roster.
It builds on the pinned teamtables32 stage. Stored roster records and all
earlier intermediate ROMs remain unchanged.

The generated roster randomly assigned one of several role bits to each
player. This left 39 non-pitchers among the usable high-team players with
the pitcher bit set, including 20 starters. Bank1 `$A10C/$A125` uses that
bit to classify players in the lineup menu. The old candidate classifies
team 17 player 5 as a pitcher despite its zero pitcher-record selector.

The cache adapter now sets bit 7 for declared specialists 0, 1 and 2 and
clears it for players 3-14. It validates those pitcher-record assignments
against the pinned ROM. Low teams still use their original bank4 pointers
and flags. Other bits retain their existing assignments, including the
outgoing/incoming pinch-run roles at bits 3/4 and pinch-hit roles at bits
5/6. This preserves current strategy rather than deriving a new strategy
from player ratings.

The replacement helper is 82 bytes in the existing 83-byte reservation at
`$FB90`. It copies 240 player bytes, updates 15 flags, then copies the
48-byte trailer. That is 303 writes to 288 addresses. CPU tests check the
exact writes and surrounding canaries, all high-team menu classifications,
player-state initialization, fresh pitchers, and 2,304 substitution cases
against the previous ROM. The old ROM fails the classification test.

Build and test this stage with:

```sh
.venv/bin/python tools/build_roles32.py build/teamtables32.nes -o build/roles32.nes
.venv/bin/python tools/test_roles32.py build/teamtables32.nes --candidate build/roles32.nes
```

The output SHA256 is
`ddb83443653af408926d98843709e7831fed8fabd40f5e762db655c9a868431b`.
Exactly 58 helper bytes change. CPU evidence is recorded in
[verification/roles32-cpu.txt](verification/roles32-cpu.txt).
A 31-match emulator run passes with champion `$04` and stack `$FF` at
every entry, recorded in [verification/roles32-soak.txt](verification/roles32-soak.txt).
The speed driver forces CPU control, so this does not prove manual gameplay.
The full pipeline now produces this stage. The combined stock-six and
full-31 gate also passes, recorded in
[verification/roles32-pipeline.txt](verification/roles32-pipeline.txt) and
[verification/roles32-gate.txt](verification/roles32-gate.txt).
Independent review approves the builder and CPU regressions. The menu readers
at `$A125` and `$A1D3` have CPU coverage, but no manual emulator coverage.
Matches 05 and 18 in this stage's recorded soak advanced at 0-0. The older
bracket hook could advance before game over and could miscredit swapped
sides. The separate `bracket-result-contract` task tracks both defects;
this stage's speed gate proves progression, not correct game completion.
