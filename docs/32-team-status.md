# 32-team ROM status

The current source pipeline produces `build/visualtables32.nes`, SHA-256
`cf4f1126a4afde0cd04bd13f06ebbea2867029cba78cedb3944ee7b15d582780`.
It supports 32-team selection, human ownership, completed-game bracket
progression, password resume, real high-team names and correct matchup
round labels. All software backlog tasks are accepted. Physical hardware
and audio validation remain blocked.

| Area | Evidence and limits |
|---|---|
| Gameplay and lineup | All 32 teams retain the stock 18-byte lineup; loader, row output and stack repairs pass CPU tests and tournament gates. |
| Pitchers and roster cache | Runtime cache uses 15 players and the stock trailer layout; starters and relief records are tested. JSON retains 20 players. |
| Human ownership | All 32 selections reach the matchup with the chosen team human. Team 31 has a controller-driven field probe. |
| Completed games | All 31 matches advance on game-over and credit live teams after side swaps. Ties use the first bracket team, tested only in the CPU harness. |
| Passwords | The existing 22-symbol keyboard restores seed, results, match index and the 32-bit CPU mask. Nine checkpoints and eight subsequent games pass. Old 16-team passwords are rejected. |
| LIST and CONTINUE | Active LIST shows the seeded 32-team grid. CONTINUE opens the bracket. Finished tournaments return safely to the title. The grid does not mark eliminated teams. |
| Tournament gates | Final visual-table ROM passes stock-six/full-31 SPEED verification. Control32 separately passes 31 controller-only WATCH games. SPEED forces CPU ownership on field entry; WATCH uses menu toggles. |
| Display labels | Full high-team names and canonical HUD codes pass CPU and controller checks. Low-team output is unchanged. |
| Visual tables | All five matchup labels pass controller checks. High-team flags are omitted, and high uniforms use declared stock presets. Shared reads are bounded. The separate 32-team selector still has placeholder flag artwork. |
| Hardware and sound | Not validated on physical hardware or a second emulator implementation. Savestates do not prove battery-backed persistence. |

## Build and verify

The current pipeline requires the earlier `build/direct20-names.nes`
artifact. The script documents how to derive that from `direct20.nes`;
those bootstrap artifacts are not distributed. Keep the original game
ROM at the repository root for stock checks, then run:

```sh
.venv/bin/python tools/build_32team_full.py
./tools/verify.sh --with-soak
```

The source chain retains pinned intermediate ROMs. `build/` is ignored by
git. The final stage is `visualtables32.nes`; `direct31.nes` remains the frozen
regression baseline.

## Evidence

- [Gameplay repairs](gameplay32.md), [pitching and cache](cpu32.md),
  [team tables](teamtables32.md), and [player roles](roles32.md).
- [Completed-game results](results32.md) and [human control](control32.md).
- [Password integration](password32.md) includes exact resume commands;
  [format](password-format.md) documents the codec.
- [Real gameplay names](teamnames32.md), [visual-table repairs](visualtables32.md),
  [final combined gate](verification/visualtables32-gate.txt) and
  [controller-only WATCH tournament](verification/control32-watch.txt).
- [Backlog](backlog.json) is the task authority.
  [Decision trail](decisions.tsv) records accepted designs.
  [Hardware checklist](hardware-sound.md) separates untested release work.
