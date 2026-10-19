# Bracket → game handoff contract (M2)

Verified from stock disassembly. This is the minimum interface a new 32-team
bracket must satisfy before launching a game.

## The two teams

```
$9C08  LDY $8941,X      ; table record for this match
$9C0B  LDA $0650,Y      ; slot A team id
$9C0E  STA $04EF
$9C11  LDA $0651,Y      ; slot B team id
$9C14  STA $04F0
```

- **`$04EF`** = first team id.
- **`$04F0`** = second team id.

Both are read well outside bank 5:

- bank 1: `$AF40`, `$B110`, `$B113`
- bank 2: `$BA45`, `$BB2E`, `$BB49`, `$BC17`, `$BD74`
- bank 0: `$AD1B`, `$AD22`, `$AD2B`

So writing these two bytes is the actual handoff; everything else is display or
post-game bookkeeping.

## Per-side flags

`$9CAC` loops `X=0,1`:

```
LDY $04EF,X
LDA $9CD0,Y        ; bit mask for this team
...
LDA $074B,Y        ; alive/result bitfield
AND mask
BEQ ...
LDA #$80
STA $04EB,X        ; $04EB/$04EC = side alive flag ($80)
```

- **`$04EB/$04EC`** = `$80` if the side is still alive/eligible.
- **`$074B/$074C`** = 16-bit result/elimination bitfield (one bit per team).
- `$9CD0` = `01 02 04 08 10 20 40 80` repeated twice for teams 0–15.

`$9F55` ORs the winner’s bit back into `$074B,Y` after a game, confirming this is
the persistent tournament state.

## Display setup

`$9CE0` loops the two sides, storing:

- `$BE/$BF` = side status (`$80`/`0`)
- `$047E` = 0/1 side index
- `$06B3/$06B4` = text pointer
- `$C9A8` → draw team name
- `$CB56` → draw flag/team block
- `$C53A` → flush display list

## What the 32-team scene must provide

1. Write the two team ids to **`$04EF` / `$04F0`** before entering the game.
2. Set **`$04EB` / `$04EC`** to `$80`.
3. Keep its own 32-bit result state; do **not** reuse `$074B/$074C` (16 bits).
4. Extend the team tables to 32 entries before handing over ids 16–31:
   names, ratings, rosters, flags, uniforms.
5. Preserve `$0746` if the stock post-game path is reused, or provide a new
   post-game hook that reports the winner.

## Status

Contract documented from disassembly (`$9C08`–`$9D40`, consumers above).
The in-game poke test (set `$04EF/$04F0`, start a match, confirm the teams) is
still pending; do not claim it verified until that runs.
