# 32-team ROM status

The current source pipeline produces `build/password32.nes`, SHA-256
`978abc4227eac24d0c779ea3fbbdfdc42c89ca0a1fcce350cff6db44501da34a`.
It supports 32-team selection, human ownership, completed-game bracket
progression and password resume. High-team display labels remain open.

| Area | Evidence and limits |
|---|---|
| Gameplay and lineup | All 32 teams retain the stock 18-byte lineup; loader, row output and stack repairs pass CPU tests and tournament gates. |
| Pitchers and roster cache | Runtime cache uses 15 players and the stock trailer layout; starters and relief records are tested. JSON retains 20 players. |
| Human ownership | All 32 selections reach the matchup with the chosen team human. Team 31 has a controller-driven field probe. |
| Completed games | All 31 matches advance on game-over and credit live teams after side swaps. Ties use the first bracket team, tested only in the CPU harness. |
| Passwords | The existing 22-symbol keyboard restores seed, results, match index and the 32-bit CPU mask. Nine checkpoints and eight subsequent games pass. Old 16-team passwords are rejected. |
| LIST and CONTINUE | Active LIST shows the seeded 32-team grid. CONTINUE opens the bracket. Finished tournaments return safely to the title. The grid does not mark eliminated teams. |
| Tournament gates | Final password ROM passes stock-six/full-31 SPEED verification. Control32 separately passes 31 controller-only WATCH games. SPEED forces CPU ownership on field entry; WATCH uses menu toggles. |
| Display labels | High-team matchup, order and HUD readers still use placeholders or old tables. Repair is queued. Selector flag images are placeholders. |
| Hardware and sound | Not validated on physical hardware or a second emulator implementation. Savestates do not prove battery-backed persistence. |

## Build and verify

Supply the original game ROM at the repository root, then run:

```sh
.venv/bin/python tools/build_32team_full.py
./tools/verify.sh --with-soak
```

The source chain retains pinned intermediate ROMs. `build/` is ignored by
git. The final stage is `password32.nes`; `direct31.nes` remains the frozen
regression baseline.

## Evidence

- [Gameplay repairs](gameplay32.md), [pitching and cache](cpu32.md),
  [team tables](teamtables32.md), and [player roles](roles32.md).
- [Completed-game results](results32.md) and [human control](control32.md).
- [Password integration](password32.md) includes exact resume commands;
  [format](password-format.md) documents the codec.
- [Final combined gate](verification/password32-gate.txt) and
  [controller-only WATCH tournament](verification/control32-watch.txt).
- [Backlog](backlog.json) is the task authority.
  [Decision trail](decisions.tsv) records accepted designs.
  [Hardware checklist](hardware-sound.md) separates untested release work.
