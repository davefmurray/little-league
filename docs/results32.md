# Completed-game bracket results

`build/results32.nes` advances the bracket only when the stock game-over
flag at `$04D0` is set and `$04E2` marks Championship mode.
Exhibition and demonstration games keep the original handler. Between innings, scene `$0B` runs the original
bank4 `$B63D` handler. The completed game's winning score side is mapped
through the live team IDs at `$04EF/$04F0`. A terminal tie retains the
existing first-bracket-team policy. This advances the bracket instead of
using the stock terminal-tie route back to the menu.

The previous hook advanced on every scene `$0B` entry. A controller-only
WATCH probe reproduced an advance after one half-inning at 0-0 with
`$04D0=0`. The old winner routine also credited the wrong team when live
sides had swapped relative to bracket order. Both negative controls are
recorded in [verification/bracket-result-negative.txt](verification/bracket-result-negative.txt).

This stage replaces the fixed `$FFC0-$FFE6` gate and bank11
`$83A0-$83CF` winner routine. The input hook at `$8105` calls a ten-byte
helper in bank11 padding at `$81D0-$81D9`. It samples the current buttons
on bracket entry, so a held A must be released before it can launch the
next game. A controller CPU test reproduces the old immediate launch and
requires release followed by a new press. In total, 98 bytes change. Its input is the pinned
roles32 artifact; the output SHA256 is
`9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b`.

CPU regressions compare 1,152 ongoing-game cases against the original stock
handler, including exact RAM writes, registers and stack. Another 9,920
cases cover all teams and match positions, side swaps, terminal ties and
score boundaries. A completed bracket cannot write another winner.
Evidence is in [verification/results32-cpu.txt](verification/results32-cpu.txt).

The final ROM completes a controller-only WATCH game with live teams
00/0F, score 3-5 and winner 0F. The SHA-stamped result is in
[verification/results32-watch-gate.txt](verification/results32-watch-gate.txt).
The earlier prototype's inning trace remains in
[verification/results32-watch.txt](verification/results32-watch.txt); it
predates the held-A guard and Championship check and is not final-ROM evidence.

The soak driver now supports `--winner live-score --require-complete`.
It checks live identities and the stock completion flag for every result.
WATCH presses A at between-inning score screens. The frame allowance covers full games.
Speed mode still forces both sides to CPU through RAM writes.

Independent review approves the final ROM code contract. An input trace
confirmed that a fast game could finish during the driver's fixed
60-frame pre-game wait, after which the next blind A launched another
game. The driver now acts on the actual pre-game substate and stops
navigation as soon as play begins. The failure trace is in
[verification/results32-input-negative.txt](verification/results32-input-negative.txt).
Every new run records the artifact SHA256.

The final ROM passes all 31 matches with completion, live identity,
score-to-winner and stack checks, ending with champion 07. See
[verification/results32-soak.txt](verification/results32-soak.txt).
The combined stock-six and final-31 gate also passes; see
[verification/results32-gate.txt](verification/results32-gate.txt). Independent review approves the ROM and corrected driver. Pressing A after the completed tournament remains a separate
bracket-view integration task.
