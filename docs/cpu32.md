# CPU pitching and runtime roster view

`build/cpu32.nes` extends the gameplay candidate with CPU manager and
relief-pitcher tables for all 32 teams and a compatible runtime roster
cache. Build it with `.venv/bin/python tools/build_32team_full.py` and run
`./tools/verify.sh --with-soak`.

The first 16 manager styles and reliever pairs remain byte-identical to
the original tables. Teams 16-31 use manager style 1, an explicit default
because the roster data has no manager-strategy field. Their declared
relief specialists are players 1 and 2. Both start in the field, so the
stock CPU queue swaps fielding positions to make the selected specialist
the pitcher. No specialist bench pair exists in the current data.

High-team lineups now put player 0, the declared P1 specialist, on the
mound and player 3 in center field. This changes two position nibbles per
team, preserving batting order, player identities and all nine positions.
The inherited lineup started player 3, whose pitcher selector was zero.

The ROM stores 20 player records followed by a 48-byte trailer for each
high team. The stock runtime expects 15 records followed by that trailer.
The cache adapter copies the first 240 player bytes, then copies the
trailer from source offset `$140` to cache offset `$F0`. This preserves
all stored roster records and keeps the stock pitcher-pointer and stamina
consumers unchanged. Players 15-19 are not exposed by the stock bench UI.
Low teams retain their original bank4 roster pointers after cache loading.

The adapter sets pitcher flag bit 7 on cached players 0, 1 and 2, whose
selectors are validated as P1/P2/P3. The generated roster originally
randomized this flag, causing 13 of 16 high-team starters to bypass
fatigue checks and trigger immediate relief. Other flag bits and stored
roster bytes remain unchanged. Low teams use their original roster flags.
The adapter copies 240 player bytes, updates three flags, and copies the
48-byte trailer. Tests check that exact sequence and the surrounding canaries.

The manager table starts at bank5 `$BC80`, followed by relievers at `$BCA0`.
This leaves the still-unextended batting-bias reads at `$BC5F-$BC6E`
unchanged until the separate table repair.

The builder writes four bank5 regions for the tables and reader operands,
plus fixed-bank `$FC4A`, an 83-byte cache helper at `$FB90`, and 32
position bytes in the high-team lineups at `$FD80`. It guards the
input hash, bytes, layout, reservations and output aliases. It also checks
that high-team JSON roster records match the input ROM.

CPU tests exercise every team and side, both relievers, threshold edges,
used-player flags and exhausted queues. They compare all low-team queue
cases against the original ROM. Cache tests execute the copy, pointer
restore, player-state initialization and pitcher-record lookup, checking
bounded writes and the intended trailer bytes. Fresh-pitcher tests take flags from the executed
cache adapter and require the stock fatigue path for all high specialists. The unmodified input fails
the manager, reliever, queue and cache tests. Starter tests execute the
actual `$ABB8` initialization and check P1 stamina, skill and arm. A
cache-only candidate fails this test by starting player 3.

The final gate passes stock6 and all 31 cpu32 matches. Every match starts
with stack `$FF`; team `$00` wins the final.
The deterministic output SHA256 is
`338c1cc9bf80f6b77f441b472e91fd7536223d0b1b129fc8b7307ccb6f006327`.
Exact evidence is in [verification/cpu32-cpu.txt](verification/cpu32-cpu.txt),
[verification/cpu32-pipeline.txt](verification/cpu32-pipeline.txt) and
[verification/cpu32-soak.txt](verification/cpu32-soak.txt).

Other generated role flags remain unaudited. In particular, 39 high-team
non-pitchers carry bit 7, and bits 3-6 affect pinch hitting and running.
This stage sets bit 7 only for declared players 0/1/2 and preserves the
remaining data. `high-roster-role-flags` tracks that separate repair.

The later [teamtables32](teamtables32.md) stage repairs bonus and batting
tables and guards the original ownership mask. Human-team selection and
bracket ownership remain separate work. Password resume, the tournament team-list UI, manual gameplay and
hardware/audio validation are not established by this gate.
