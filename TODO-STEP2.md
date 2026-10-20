# TODO — STEP 2 (fresh list)

## P0 — gameplay completion

1. `$06E2` group/team mapping (pitch item 10): make the field team index
   map to the right group/team slot; the pair4 `$B2=09 -> $BC=9 ->
   $06E2[9]=0x43 -> team 4` mismatch.
2. `$071A` 32-byte flags + `$06E2` 32-byte groups (list item 4): full
   32-team scan, names, no JAPAN fallback.
3. Bank5 32-team password decode/encode (item 7): 16-char `$06B5` ->
   `$074D` -> `seed_order`/`advance` -> `$7700`/`$7720`; encode back.

## P1 — field / match

4. High-team field/match: the launch bridge/`$FF60` pair + the 32-team
   bracket in the main build.
5. 26-match soak: field/pitch for all rounds; the match-8 stall.
6. Audio regression: title/menu/field SFX vs stock.
7. SRAM battery save/CONTINUE after power cycle.

## P2 — polish / release

8. 2-player field.
9. Hardware run: Mesen2/FCEUX/EverDrive/real NES checklist.
10. Docs/assets: screenshots, README, manifest.
11. Regression/CI: check_build + 6-match soak + bracket/roster tests.
