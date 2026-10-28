# 32-team ROM status

The current source pipeline produces `build/teamnames32.nes`, SHA-256
`5998632da930ec063ea3029320a2b5d901043baa662add8adb8d14b809633f5c`.
It supports 32-team selection, human ownership, completed-game bracket
progression, password resume and real high-team names. Flag and uniform
table bounds and the matchup round label remain open.

| Area | Evidence and limits |
|---|---|
| Gameplay and lineup | All 32 teams retain the stock 18-byte lineup; loader, row output and stack repairs pass CPU tests and tournament gates. |
| Pitchers and roster cache | Runtime cache uses 15 players and the stock trailer layout; starters and relief records are tested. JSON retains 20 players. |
| Human ownership | All 32 selections reach the matchup with the chosen team human. Team 31 has a controller-driven field probe. |
| Completed games | All 31 matches advance on game-over and credit live teams after side swaps. Ties use the first bracket team, tested only in the CPU harness. |
| Passwords | The existing 22-symbol keyboard restores seed, results, match index and the 32-bit CPU mask. Nine checkpoints and eight subsequent games pass. Old 16-team passwords are rejected. |
| LIST and CONTINUE | Active LIST shows the seeded 32-team grid. CONTINUE opens the bracket. Finished tournaments return safely to the title. The grid does not mark eliminated teams. |
| Tournament gates | Final team-name ROM passes stock-six/full-31 SPEED verification. Control32 separately passes 31 controller-only WATCH games. SPEED forces CPU ownership on field entry; WATCH uses menu toggles. |
| Display labels | Full high-team names and canonical HUD codes pass CPU and controller checks. Low-team output is unchanged. |
| Visual tables | High-team flags and uniform palettes still overread 16-team tables. The matchup round label remains 1ST ROUND. Repairs are queued; selector flag images are placeholders. |
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
git. The final stage is `teamnames32.nes`; `direct31.nes` remains the frozen
regression baseline.

## Evidence

- [Gameplay repairs](gameplay32.md), [pitching and cache](cpu32.md),
  [team tables](teamtables32.md), and [player roles](roles32.md).
- [Completed-game results](results32.md) and [human control](control32.md).
- [Password integration](password32.md) includes exact resume commands;
  [format](password-format.md) documents the codec.
- [Real gameplay names](teamnames32.md), [final combined gate](verification/teamnames32-gate.txt) and
  [controller-only WATCH tournament](verification/control32-watch.txt).
- [Backlog](backlog.json) is the task authority.
  [Decision trail](decisions.tsv) records accepted designs.
  [Hardware checklist](hardware-sound.md) separates untested release work.
