# 32-team ROM status

The current source pipeline produces `build/analysisart32.nes`, SHA-256
`1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`.
It supports 32-team selection, human ownership, completed-game bracket
progression, password resume, real high-team names and correct matchup
round labels, a shared flag-grid picker, bracket tree and stock menu music.
The new title preserves the attract sequence. New championships shuffle once
and save their draw in v2 passwords. The mode menu shows the selected sunny
ballpark scene with original intro characters and the stock crowd. The
scoreboard uses the same style and source characters while preserving score
and statistic rules. Power Analysis shows the selected baseball-marker
card with labeled ratings and original characters. All software backlog tasks are accepted. Physical hardware
and a second emulator implementation remain unvalidated.

| Area | Evidence and limits |
|---|---|
| Gameplay and lineup | All 32 teams retain the stock 18-byte lineup; loader, row output and stack repairs pass CPU tests and tournament gates. |
| Pitchers and roster cache | Runtime cache uses 15 players and the stock trailer layout; starters and relief records are tested. JSON retains 20 players. |
| Human ownership | All 32 selections reach the matchup with the chosen team human. Team 31 has a controller-driven field probe. |
| Completed games | All 31 matches advance on game-over and credit live teams after side swaps. Ties use the first bracket team, tested only in the CPU harness. |
| Passwords | The existing 22-symbol keyboard restores seed, results, match index and the 32-bit CPU mask. Eighteen v1/v2 checkpoints and sixteen subsequent games pass. Old 16-team passwords are rejected. |
| LIST and CONTINUE | Active LIST shows the seeded 32-team grid. CONTINUE opens the bracket. Finished tournaments return safely to the title. The grid does not mark eliminated teams. |
| Tournament gates | Analysisart32 passes stock-six/random-full-31 SPEED and a resumed game after Analysis. Stockart32 separately passes a controller-driven WATCH game. Control32 separately passes 31 WATCH games. SPEED forces CPU ownership on field entry; WATCH uses menu toggles. |
| Display labels | Full high-team names and canonical HUD codes pass CPU and controller checks. Low-team output is unchanged. |
| Visual tables | All five matchup labels pass controller checks. High-team gameplay flags are omitted, and high uniforms use declared stock presets. Shared reads are bounded. |
| Menus and music | The 32-team selector has simplified flags, full names and regions. The bracket shows advancement and the next matchup. Stock song06 advances in both menus; exact CPU APU traces and emulator activity checks pass. |
| Shared picker and title | The title32 stage passes all 32 Analysis choices and full high-team 1P/2P/WATCH exhibitions. Original title music, both START ports and attract redraw are checked. See [picker](pick32.md) and [title](title32.md). |
| Ballpark mode menu | All three menus match the assets in the emulator, including palettes and cursor sprites. Stock exits and audio remain. Modeart32 2P and WATCH exhibitions complete; 1P has setup and human-field evidence, not a completed game. See [modeart32](modeart32.md). |
| Ballpark scoreboard | Stock score/stat writers draw cream and gold numbers over a sunny crowd scene. CPU parity, played WATCH boards, extra-inning fixtures and the final tournament gate pass. See [scoreart32](scoreart32.md) and [stock characters](stockart32.md). |
| Power Analysis | All 32 cards and returns, 27 phase frames and split pixels match in the emulator; ratings, animation and audio match stock in CPU tests. Active-series continuation passes. See [analysisart32](analysisart32.md). |
| Random draw | Selected team plays first; 14-bit draw seed saved in v2. Legacy v1 retains ascending order. See [draw contract and resume matrix](draw32.md). |
| Hardware and sound | Audio captures are available; physical hardware and a second emulator remain unvalidated. Savestates do not prove battery-backed persistence. |

## Build and verify

The current pipeline requires the earlier `build/direct20-names.nes`
artifact, Node >= 22.18 and the pinned `build/vendor/claude-pxl` checkout.
The script documents how to derive that from `direct20.nes`;
those bootstrap artifacts are not distributed. Keep the original game
ROM at the repository root for stock checks, then run:

```sh
.venv/bin/python tools/build_32team_full.py
./tools/verify.sh --with-soak
```

The source chain retains pinned intermediate ROMs. `build/` is ignored by
git. The final stage is `analysisart32.nes`; `direct31.nes` remains the frozen
regression baseline.

## Evidence

- [Gameplay repairs](gameplay32.md), [pitching and cache](cpu32.md),
  [team tables](teamtables32.md), and [player roles](roles32.md).
- [Completed-game results](results32.md) and [human control](control32.md).
- [Password integration](password32.md) includes exact resume commands;
  [format](password-format.md) documents the codec.
- [Real gameplay names](teamnames32.md), [visual-table repairs](visualtables32.md),
  [menu art and music](menuart32.md), [final combined gate](verification/analysisart32-gate.txt) and
  [controller-only WATCH tournament](verification/control32-watch.txt).
- [Backlog](backlog.json) is the task authority.
  [Decision trail](decisions.tsv) records accepted designs.
  [Hardware checklist](hardware-sound.md) separates untested release work.
