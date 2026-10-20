# TODO — FINISH LIST (Step 1), then STEP 2 audit

Ordered finish queue. Each item: romdev probe or ROM change, commit, report.
History: `docs/AUTORUN-REPORT.md`.

## Step 1 — finish the list

1. [x] **Launch bridge + high-team field entry (P0).**
       `tools/build_launch32.py`; field rendered (`docs/high-team-field.png`).
2. [x] **Order-screen / field start (P0).** 0F `$0489=0` A/START -> scene 03.
3. [x] **Live field / match engine + roster cache (P0).**
       cache13: fixed `$FFC0` launch -> `$FC00` roster cache -> `$FF90`.
       WATCH/SPEED run the match; no `$6006` jam; box 0-13. Scene 0x17 is
       the **SPEED MODE / WATCH THE GAME** menu; SPEED -> 0x0A result.
4. [ ] **LIST OF TEAMS names (P1).**
       Name tables (`$B2D6`/`$BC80`/`$BC40`) and loaders are intact; the
       only `$AF53` caller is the matchup draw with `$04EF/$04F0`. The
       list repeats JAPAN because the team ids/slots are 0 (JAPAN), not
       because the table is corrupt. Next: initialize the stock 4-team
       slots for the list path, or replace the screen with the 32-team
       selector/table. **Located:** the LIST OF TEAMS menu action is bank1
       `$A1C6` (`$C0=0x0E`) -> `$A1AA`; the list reads `$C0`/`$BD`/`$071A`.
       Trace those rows and initialize the 32-team data.
5. [ ] **Match-5 soak stall (P1).**
       26-match speed soak: match 5 (09 v 0A) times out at 40k frames.
6. [x] **Scene 1E/1F / match-26 (P1).**
       Resolved: table is bank-relative and stock-identical; 0x17 -> bank6
       `$B0EE`, 0x1D -> bank5 `$81A8`, 0x1E/1F `$0101`/bank `$AD` is the
       stock dummy. The 0x16 order loop is the mode menu/box, not a table bug.
7. [ ] **32-team password screen wiring (P2).**
       Stock alphabet `5 7 H J K M O Q S U e g h j l n`; 11-char base-32
       codec done; wire the screen or entry/continue code.
8. [ ] **In-game bench / attribute card (P2).**
       START-menu substitution/pitcher change + printed power/speed/skill.
9. [ ] **Hardware / sound execution (P2).**
       Run `docs/hardware-checklist.md` and `docs/sound-checklist.md`.
10. [ ] **32-team PLAY mode / player pitch (P1, new).**
        The bracket only offers SPEED (sim) / WATCH (auto); restore or add
        the stock PLAY field so the player pitches/hits.
11. [ ] **STEP 2 audit: find new need areas and write the next TODO.**

## Done / do not re-open

- 32-team bracket state/codes/layout; cold-boot seed; launch bridge; data;
  high-team field render and match result; password codecs; teams 16-31
  data; roster cache; web editor; CLI; build manifest; stock hash/tests.
