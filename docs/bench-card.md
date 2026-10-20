# Bench / Attribute Card

Design and code notes for the in-game team/bench card (item 8).

## Stock card code

- `$9A1C` draws the team card:
  - `LDA $BC / ASL / PHA / TAY`
  - `LDA $9B60,Y / STA $06B4`, `LDA $9B61,Y / STA $06B3`
  - `PLA / ORA $BD / TAY`
  - `LDA $06E2,Y` -> the group/team entry
  - `SEC / SBC #$01 / AND #$0F / ASL x3 / TAY`
  - `LDX #$00 / LDA $9A70,Y / STA $06B5,X` (8 attribute bytes)
  - `JMP $C713` redraw
- `$9A4E` uses `$9B72,Y` + `$06E2[$BC*2+$BD] >> 4` -> `$CB17` (the
  name/number draw).
- `$9A70` is the 8-groups x 8-bytes attribute table (64 bytes).
- `$06E2` is the 8-groups x 2 team table (16 bytes).

## 32-team extension

- `$06E2` must be 32 bytes (16 groups x 2) — already in `pair3`/`pair4`.
- `$9A70` must cover 16 groups (128 bytes) instead of 8 (64).
- `$9A1C`/`$9A4E` need the `$B2 & 0x10` page offset for groups 8-15.
- The bench (16 players) comes from the `$FD80` lineups (9 bytes/team,
  32 teams) and `data/roster32.json` attributes.

## Screen layout

1. Team header (name, group, record).
2. 16 roster rows: name, position, attribute bars (speed/power/field).
3. Bench markers for the 5 inactive players.
4. Swap prompt (A = swap, B = back).

## Data model

- `data/roster32.json`: 32 teams, player names/ratings, lineups.
- `$FD80`: 32 x 9-byte lineup records (the runtime copy).
- `$074D`/`$0755`/`$0756`: the password state that seeds the bracket.

## Acceptance

- [ ] Card renders for all 32 teams.
- [ ] Attribute table covers 16 groups.
- [ ] Bench/swap works; no slot overflow.
- [ ] `$A1AA` list and `$9A1C` card agree on the team/group.
