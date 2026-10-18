# DataCrystal ROM map — reconciled and verified

Source: DataCrystal, *Little League Baseball: Championship Series/ROM map*
(<https://datacrystal.tcrf.net/wiki/Little_League_Baseball:_Championship_Series/ROM_map>),
captured via the page text. Cross-checked byte-for-byte against our ROM.

This supersedes parts of `roster-format.md` and `prior-art-llbcs.md`.

## Team order

JAPAN, ARIZONA, PENNSYLVANIA, CHINESE TAIPEI, KOREA, NEW YORK, CALIFORNIA,
TEXAS, HAWAII, SPAIN, PUERTO RICO, MEXICO, CANADA, ITALY, ILLINOIS, FLORIDA.

## Roster bases

DataCrystal describes a uniform `0x120` pattern. Verified names agree for teams
0–9, then diverge:

| Team | File base | Verified name | Note |
|---|---|---|---|
| Japan | `0x10430` | UMEDA | |
| Arizona | `0x10550` | BERT | |
| Pennsylvania | `0x10670` | LEE | |
| Chinese Taipei | `0x10790` | LU | |
| Korea | `0x108B0` | LEE | |
| New York | `0x109D0` | TOMMY | |
| California | `0x10AF0` | BIFF | |
| Texas | `0x10C10` | AUSTIN | |
| Hawaii | `0x10D30` | THOMAS | |
| Spain | `0x10E50` | ENRICO | |
| Puerto Rico | `0x10F50`* | zeros | players start `0x10F70` (`EMILLO`) |
| Mexico | `0x11090` | JUAN | `+0x140` from PR |
| Canada | `0x111B0` | CHUCK | |
| Italy | `0x112D0` | LOGI | |
| Illinois | `0x113F0` | CONRAD | |
| Florida | `0x11510` | DON | |

\* The uniform-pattern claim breaks here. Use the verified bases.

## Player row (16 bytes)

| Byte | Meaning |
|---|---|
| 0–5 | name (6 chars) |
| 6 | hand/size: `00/01/02` right tall/fat/short, `80/81/82` left |
| 7 | always `FF` |
| 8 | unknown (CPU sub choice suspected) |
| 9 | **hitting power** (`00` low … `DF` highest) |
| 10 | **speed** (`00`–`FF`, baserunning) |
| 11 | **printed Skill** (`00`–`04` = Skill 1–5; KOREA PARK is `07`) |
| 12 | pitcher slot: `00`, `08`, `10`, `18` |
| 13 | always `00` |
| 14 | multiplier `00/02/03/04` (batting/power suspected) |
| 15 | always `00` |

This contradicts llbcs.py's byte 9/10 "ARM/RUN" labels; DataCrystal's reading
fits the observed `D4/C9` values as power/speed.

## Pitcher records

Immediately after the all-`FF` row:

| Record | Location |
|---|---|
| #1 | bytes 8–15 of first row after `FF` |
| #2 | bytes 0–7 of second row |
| #3 | bytes 8–15 of second row |

Eight bytes:

| Byte | Meaning |
|---|---|
| 0 | hand/delivery (`00/01/02/80/81/82`) |
| 1 | stamina (`FF` max) |
| 2 | unknown (quality?) |
| 3 | unknown, `02`–`0F` |
| 4 | `00` |
| 5 | `00` |
| 6 | printed pitcher Skill |
| 7 | `00`/`02` multiplier suspected |

## Team colours — two 16-byte tables

DataCrystal: two colours per team at `0x1FAD0` and `0x1FAE0`.

```
0x1FAD0: 05 20 0F 26 20 38 02 22 38 1B 2B 0F 12 20 0F 15
0x1FAE0: 11 38 11 15 38 00 10 38 14 12 0F 15 15 0F 15 25
```

This is **two tables of 16**, not 16 × 3-byte entries. The llbcs.py 3-byte
grouping is wrong: it mixes the secondary colour of one team with the primary of
the next.

## Lineups

File `0x116DA`–`0x11769`, 9 bytes per team, packed nibbles: high nibble = lineup
order, low nibble = position (baseball scoring). Japan verified:

```
08 16 29 31 42 57 65 73 84
```

## Flags — offsets at `$975A`, records at `$976A`

Both tables are in **bank 4**:

- `$975A` (file `0x1176A`): 16-byte offset table, one byte per team.
- `$976A` (file `0x1177A`): records of 12 `(tile, attr)` pairs (24 bytes).
- The draw routine (`$CB63`) does `LDY $975A,X` then reads `$976A,Y`.
- Flags use **CHR bank `$1B` for every team**; `$FB4E` is player/uniform CHR.
- Offset `$48` is the USA flag record, matching DataCrystal's "48 is USA".

Lineups occupy `$96CA`–`$9759` (16 × 9 = 144 bytes); `$975A` is the first byte
after them. My earlier claim that `$975A` was lineup tail was off by the bank-4
base and is retracted.

## Power Analysis

Bars are driven by file `0x00F234` in team order. That file offset is bank 3,
CPU `$B224` — matching our existing ratings table at `$B224`.

## What to fix in the repo

- [x] `roster.py` / `build_16x20.py`: use `tools/llbcs_map.py` verified bases.
- [x] Colour model: two 16-byte tables at `$FAC0`/`$FAD0`.
- [ ] Player field map: power/speed/skill per above; re-test in-game.
- [x] Flag pipeline: bank-4 `$975A`/`$976A`, CHR bank `$1B`; all 16 extract.
- [x] Lineup parser: unpack nibbles (order/position); round-trip identical.

## Validation (roster map)

Two independent checks:

1. **Round-trip:** `extract` → `apply` → `cmp` is byte-identical over the whole
   ROM for names, ratings, colours, lineups, and player rows.
2. **Mutation:** change Japan player 0 to `TESTER`, primary colour `05`→`0F`,
   lineup byte `08`→`81`, batting rating `1`→`4`. The diff touches exactly:

```
0x0F234  01 -> 04     ratings
0x10430  55 4D 45 44 41 20 -> 54 45 53 54 45 52   UMEDA -> TESTER
0x116DA  08 -> 81     lineup order/position
0x1FAD0  05 -> 0F     primary colour
```

Re-extracting the mutated ROM returns the new values.

## Still not mapped/verified

- Player attribute **semantics** (power/speed/skill byte meaning in-game).
- Editing pitcher records (read-only trailer copy today).
- Editable flags (extraction works; write path does not).
- Bracket tables, passwords, short-name pointer table details.
