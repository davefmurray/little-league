# Sound/music checks

The data moves (bank 1 names, bank 3 ratings, bank 8 rosters, bank 9
codes/regions, bank 11 bracket, fixed lineups) should not touch the audio
engine, but bank switching and the new scenes can change which track/SFX is
selected.

## Checklist

| Area | Track/SFX expected | Result |
| --- | --- | --- |
| Title/menu | stock title music | not run |
| Selector pages 1-4 | menu move/confirm | not run |
| Bracket draw/cursor | bracket SFX | not run |
| Password screen | password SFX | not run |
| Field (low team) | field music, pitch/bat SFX | not run |
| Box score | result jingle | not run |
| Champion/ending | ending music | not run |

## Method

- Capture audio from the same emulator/core for stock and 32-team builds.
- Compare track identity and channel balance, not just "sound present."
- Note any missing/extra SFX and the exact scene/button.
- A bank-switch bug often shows as silence or a stuck note; check the
  `$C14E` calls around the field/bracket transitions.

Status: **not run** in this environment.
