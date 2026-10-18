> **Correction (verified against llbcs.py):** team roster bases are **not** a
> uniform `0x120` stride. Teams 10–15 differ (Puerto Rico `+0x100`, Mexico
> `+0x140`). See `docs/prior-art-llbcs.md` for the verified base table. Team
> colours are **16 × 3 bytes** at `$FAC0`, not two 16-byte tables at
> `$FAC0`/`$FAD0`.

# Roster and team data format

All tables are plain data in the PRG ROM. Bank 4 is switched in before the game
touches the roster, so these file offsets are stable for this revision.

| Table | CPU | Bank | File offset | Size |
|---|---|---|---|---|
| Team long names | `$9180` | 1 | `0x5190` | 16 × 16 |
| Short-name pointers (teams 0–7) | `$9280` | 1 | `0x5290` | 8 × 2 |
| Short-name pointers (teams 8–15) | `$9290` | 1 | `0x52A0` | 8 × 2 |
| Team ratings | `$B224` | 3 | `0xF234` | 16 × 4 |
| Player records | `$8420` | 4 | `0x10430` | 16 × 15 × 16 |
| Lineups | `$96CA` | 4 | `0x116DA` | 16 × 9 |
| Team flags | `$975A` | 4 | `0x1176A` | 16 |
| Team colors | `$FAC0` | 7 | `0x1FAD0` | 16 |
| Team colors (second set) | `$FAD0` | 7 | `0x1FAE0` | 16 |

Team order everywhere: **JAPAN, ARIZONA, PENNSYLVANIA, CHINESE TAIPEI, KOREA,
NEW YORK, CALIFORNIA, TEXAS, HAWAII, SPAIN, PUERTORICO, MEXICO, CANADA, ITALY,
ILLINOIS, FLORIDA**.

## Team names

16 entries, 16 bytes each: 14 ASCII bytes, space padded, then `FF FF`.
Used on team select and the power-analysis screen. Max 14 characters.

```
$9180: 4A 41 50 41 4E 20 ... 20 FF FF   "JAPAN         "
$91A0: 50 45 4E 4E 53 59 4C 56 41 4E 49 41 20 20 FF FF   "PENNSYLVANIA  "
```

## Short names

Two 8-entry pointer tables (`$9280` for teams 0–7, `$9290` for 8–15). Each target
is `[attr byte][text][FF]`, space padded, e.g. `04 "JAPAN     " FF`. Used on the
scoreboard. A replacement must not exceed the stored width.

## Team ratings (POWER ANALYSIS)

16 teams × 4 bytes, values **1–4**, drawn as bars. Display order is
**BATTING, RUNNING, PITCHING, DEFENSE** (inferred from the comparison loop at
`$AFCC` and the label order at `$B1FD`).

```
JAPAN      [1,3,2,3]     NEW YORK   [3,4,4,4]
ITALY      [1,1,1,1]     MEXICO     [4,4,1,1]
```

## Player records

15 players per team, 16 bytes each. Team base = `$8420 + team * $120`;
player record = base + `slot * 16`.

| Offset | Field | Status |
|---|---|---|
| 0–5 | Name, ASCII, space padded, max 6 chars | **confirmed** (`$CB3B` copies 6 bytes to `$06B5`) |
| 6 | Player type: bit 7 = left-handed; low 2 bits = body (0 tall, 1 heavy, 2 short) | community-documented; values observed match |
| 7 | Always `FF` | constant |
| 8 | Unknown; copied to `$071A` | unknown, possibly CPU substitution logic |
| 9 | Batting / pitching ratings **or** hitting power | see below |
| 10 | Speed / secondary rating | see below |
| 11 | **SKILL** 0–4, displayed 1–5 | **confirmed** (`"12345555"` table at `$AEBE`, `SKILL` string at `$AE3C`) |
| 12 | Pitcher slot: `00` none, `08` P1, `10` P2, `18` P3 | **confirmed** |
| 13 | Always `00` | constant |
| 14 | `00`, `02`, `03`, `04`; only two players use 3/4 | effect unknown |
| 15 | Always `00` | constant |

### Byte 12 and the pitcher records

`$B0A2` computes `team_base + $100 + byte12 + 1` and reads the result. That is the
**stamina byte of the pitcher record** selected by byte 12:

| byte 12 | record | address from team base |
|---|---|---|
| `08` | pitcher 1 | `+$109` |
| `10` | pitcher 2 | `+$111` |
| `18` | pitcher 3 | `+$119` |

So byte 12 does not point at the 15 player records — it selects one of three
8-byte pitcher records stored in the 48-byte trailer after slot 14.

### The trailer (48 bytes at team base + `$F0`)

```
+$00  FF × 16                       reserved
+$10  00 × 8                        unused
+$18  pitcher 1, 8 bytes
+$20  pitcher 2, 8 bytes
+$28  pitcher 3, 8 bytes
```

Pitcher record layout (community-documented, values verified against the ROM):

| Byte | Meaning | Observed range |
|---|---|---|
| 1 | Arm: `00`/`01`/`02` right, `80`/`81`/`82` left; low bits normal/hard/sidearm | 6 values |
| 2 | Stamina | `$31`–`$FF` |
| 3 | Unknown | `$18`–`$FD` |
| 4 | Unknown | `$00`–`$0F` |
| 5 | Always `00` | — |
| 6 | Always `00` | — |
| 7 | Printed SKILL on the mound | 0–4 |
| 8 | `00` or `02` | 2 values |

Pennsylvania is a data quirk: it has four players flagged as pitchers, two of
them with `18`, so the fourth shares pitcher 3's record.

### Bytes 9 and 10: the open question

Two readings are in circulation and they disagree:

- **Community (TecmoBowl thread, 2017):** byte 9 is hitting power (`00`–`DF`),
  byte 10 is baserunning speed (`00`–`FF`), both as whole bytes.
- **Code:** the card loader at `$ADDE` splits byte 9 into nibbles into `$0531` /
  `$0532` and `$0516` / `$0517`. `$0516` indexes the hit-range table at `$AA2D`
  (`$AA0D`), and `$0517` is used in the pitch-accuracy path (`$EF97`, `$F166`).
  Byte 10's low nibble is copied to `$0689` (`$AD8C`) and bits 6–7 feed a bar
  graphic (`$AD7F`).

The most consistent reading is that byte 9 packs **two 4-bit ratings**
(batting high nibble, pitching low nibble) and that byte-level edits in the
community made both move at once. This editor exposes them separately as
BATTING and PITCHING. Byte 10's low nibble is exposed as SPEED; the high nibble
is preserved but unmapped.

### Skill and stats at a glance

- SKILL is the only rating printed on the player card (1–5).
- Team ratings are a separate 1–4 table, not an average of player records.
- There is no stat tracking in-game (no averages, home runs, ERA).

## Lineups

16 teams × 9 bytes at `$96CA`. Each byte packs **batting order in the high
nibble (0–8)** and **fielding position in the low nibble (1–9)**:

```
JAPAN  08 16 29 31 42 57 65 73 84
       order 0..8, positions 8,6,9,1,2,7,5,3,4
```

Positions use scorekeeping numbering: 1 pitcher, 2 catcher, 3 first, 4 second,
5 third, 6 shortstop, 7 left, 8 center, 9 right.

## Team flags

16 bytes at `$975A`, one per team, used for the flag on the team-select screen.
`$48` is the USA flag; other values are tile IDs.

```
00 48 48 18 30 48 48 48 48 d8 78 90 a8 c0 48 48
```

## Team colors

Two 16-byte tables at `$FAC0` and `$FAD0`, one byte per team each, described by
the community as the two uniform colours used on the field and in the bat-throw
cutscene:

```
$FAC0: 05 20 0f 26 20 38 02 22 38 1b 2b 0f 12 20 0f 15
$FAD0: 11 38 11 15 38 00 10 38 14 12 0f 15 15 0f 15 25
```

Exact palette interpretation is unverified.

## Editing constraints

- 16 teams fixed; the pointer tables have no spare entries.
- 15 usable player slots. Slot 15 is `FF`; the rest of the trailer is pitcher
  data.
- Names: 6 chars player, 14 chars team, stored width for scoreboard names.
- Uppercase ASCII is safe; lowercase glyphs may not exist in the font.
- Three pitcher records per team; byte 12 on a player decides which one they use.

## Tooling

```sh
python3 tools/roster.py show ROM
python3 tools/roster.py extract ROM -o data/roster.json
python3 tools/roster.py apply ROM data/roster.json -o build/hack.nes
python3 tools/roster.py patch ROM --team 2 --slot 14 --name DAVE --skill 5 -o build/demo.nes
```

The extract → apply round trip is byte-identical on the unmodified ROM.

## Known gaps

1. Bytes 8, 13, 15 and the high nibble of 10 are unmapped.
2. The exact gameplay meaning of byte 9's nibbles vs. the community's whole-byte
   reading is unresolved without controlled emulator tests.
3. Pitcher record bytes 3 and 4 are unknown; byte 2 is stamina but the formula
   is not linear.
4. Team colours need palette-level verification.
