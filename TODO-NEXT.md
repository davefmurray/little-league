# TODO — FINISH LIST (Step 1), then STEP 2 audit

Ordered finish queue. Each item: romdev probe or ROM change, commit, report.
History: `docs/AUTORUN-REPORT.md`.

## Step 1 — finish the list

1. [x] **Launch bridge + high-team field entry (P0).**
       `tools/build_launch32.py`: launch-prod base + 32-team data +
       `$9BFD JSR $FF60` + `$98C8=02` + `$8100` cursor 16 + `$FF60` pair.
       Flow reaches scene 03 with the field rendered
       (`docs/high-team-field.png`).
2. [x] **Order-screen / field start (P0).**
       The proper 0F `$0489=0` A/START enters scene 03.
3. [ ] **Pitch / live-field handler + roster cache (P0).**
       3a. The uncached `launch32-high` advances 03 -> 05 -> 02 (`$ACAA`,
           the real field/pitch handler), then jams at `$6006`: the CPU is
           executing the stock `$6000` player-name buffer (UMEDA/NAKATU).
           The high team's `$7F00` roster pointer is the stock/dummy one.
       3b. The full cache port (`$CBE6 -> JSR $FD00` init + `$FC00` cache +
           `$8470` launch + `$FF90` resume + `$FF58 JMP $8470`) stalls the
           bridge bracket at scene 12/PC `$84CE`; the `$FD00`/boot/PPU
           interaction is the suspect.
       3c. cache3 (without `$CBE6`/`$FD00`) still stalls. Isolation:
           cache6 (bank7 reads only) and cache7 (`$FC00`+`$FF90` only) both
           pass to scene 13; the stall is the **`$FF58 JMP $8470` +
           `$8470` LAUNCH** path (returns to the bracket `$84CE`). Next:
           isolate the `$FC00` bank-8 copy / `$FF90` / `$98C0` return-stack.
           **Fixed:** the `$8470` bank11 write corrupted the bracket; moving
           the launch to fixed `$FFC0` works. cache13 = `$FF58 JMP $FFC0` ->
           `$FFC0` pair -> `$FC00` cache -> `$FF90`. The match engine now runs
           (scene 0B, score 0-13, no `$6006` jam). Remaining: the SPEED/player
           field selection (WATCH vs SPEED; `$04EB/$04EC`/`$BE`). Found:
           `$04EB/$04EC=80/80` = WATCH (0B result); `00/00` = player/SPEED,
           which enters the 32-team `$17`/`$1D` scenes and cycles. The player
           field is blocked by the scene `$1E/$1F` table (item 6).
4. [ ] **LIST OF TEAMS names (P1).**
       The stock list repeats JAPAN; wire the bank-9 32-team names.
5. [ ] **Match-5 soak stall (P1).**
       26-match speed soak: match 5 (09 v 0A) times out at 40k frames.
6. [ ] **Scene 1E/1F / match-26 (P1).**
       **Re-scoped:** the table entries are bank-relative and are identical
       to the stock ROM. `0x17` -> bank6 `$B0EE`, `0x1D` -> bank5 `$81A8`
       (valid); `0x1E/1F` -> `$0101` in bank `$AD` is the stock dummy, not a
       32-team regression. The player path loops because `$9EC2` (bank1
       order screen) keeps setting `$047B=0x16`; debug the 0x16 order/lineup
       state, not the table.
7. [ ] **32-team password screen wiring (P2).**
       Stock alphabet `5 7 H J K M O Q S U e g h j l n`; 11-char base-32
       codec done; wire the screen or entry/continue code.
8. [ ] **In-game bench / attribute card (P2).**
       START-menu substitution/pitcher change + printed power/speed/skill.
9. [ ] **Hardware / sound execution (P2).**
       Run `docs/hardware-checklist.md` and `docs/sound-checklist.md`.
10. [ ] **STEP 2 audit: find new need areas and write the next TODO.**

## Done / do not re-open

- 32-team bracket state/codes/layout; cold-boot 2 KB RAM seed reaches the
  bracket; launch bridge validated; 32-team data on launch-prod.
- High-team matchup and field render (scene 03, `$0489=0`).
- Password codecs/screen capture; teams 16-31 data; roster cache tool;
  web editor; CLI; build manifest; stock hash/tests green.
