# Select and control any of the 32 teams

`build/control32.nes` opens the four-page selector directly from START NEW
SERIES. Confirming a team gives that team to controller 1 and makes the
other 31 teams CPU-controlled. The selected team seeds the first bracket
slot. Redrawing the bracket preserves that order after match initialization
reuses the selector's scratch bytes.

Ownership uses one four-byte CPU mask at `$074B/$074C/$07F1/$07F2`.
A set bit means CPU. The original low-team reader remains unchanged;
the high-team reader uses the upper two bytes. The stock pre-game COM
switch applies to the current match and does not rewrite the series mask.
Password-restored masks can represent more than one human team; CPU tests
cover those masks, while the selector creates exactly one human team.

The selector ignores buttons held on entry, hides leftover sprites, and
waits for release before committing. The bracket also waits for release
before handing off to the password screen. Debug writes into the saved
stack area are removed.

The guarded builder starts from results32 SHA256
`9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b`.
Its output is
`a1caf9a28e750a777343f2bdbd5c02987a03ccac0f58b6257e62dbee0faf30a8`.
It changes 1,929 bytes, including 85 outside bank 10.

| Region | Purpose |
|---|---|
| Bank 10 | Source-generated selector and team names |
| Bank 5 `$BD60-$BD76` | High-team ownership reader |
| Fixed `$FF14-$FF1B` | Selector-to-bracket bank switch |
| Bank 11 `$8540-$854A` | Release before game launch |
| Bank 11 `$86E0-$86F4` | Clear view mode, set active-series marker, seed once |

CPU checks execute all 32 selection commits, 31,744 matchup ownership
cases, 5,888 exact stock-parity cases and 7,936 controller-routing cases.
They also retain the completed-game result regressions. Independent review
approves the code and reserved regions.
[CPU evidence](verification/control32-cpu.txt).

Controller-only emulator probes selected every team, checked the complete
ownership mask, and reached each matchup with the selected team human.
Ten-frame A holds did not skip the selector or password screen. Team 31's
human order menu reached the field, and a matched saved-state comparison
showed different gameplay after repeated controller-1 A presses.
[UI evidence](verification/control32-ui.txt).

The source pipeline and stock-six/full-31 speed gate pass, with team 31
seeded, champion 07 and stack FF at every match entry.
[Pipeline](verification/control32-pipeline.txt),
[combined gate](verification/control32-gate.txt),
[full tournament](verification/control32-soak.txt).
Speed mode writes both sides to CPU on field entry, so this proves tournament
progression rather than human gameplay. The separate WATCH run uses only
controller input, including the pre-game COM toggle. It completed all 31
matches with champion 1E and stack FF throughout.
[Controller-only WATCH evidence](verification/control32-watch.txt).

High-team labels on the matchup, cutscene, order and field screens still
use old tables or placeholders. The `high-team-display-names` task owns
that repair. Flag pictures remain the existing selector placeholders.
Hardware, audio and controller electrical behavior have not been tested.
