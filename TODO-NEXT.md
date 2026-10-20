# TODO — FINISH LIST (Step 1), then STEP 2 audit

Ordered finish queue. Each item gets a romdev probe or ROM change, a commit,
and a report/TODO update. History: `docs/AUTORUN-REPORT.md`.

## Step 1 — finish the list

1. [x] **Launch bridge + high-team field entry (P0).**
       `tools/build_launch32.py` applies the 32-team data to the real
       launch-bridge base (`launch-prod`, scene-18 `$98B9` -> `$FF20`),
       patches `$9BFD JSR $FF60`, `$98C8=02` (skip password), `$8100`
       cursor 16, and `$FF60` pair (`$04EF/$04F0` -> `$0650/$0651`).
       Flow: Start New Series -> team A -> mode A -> scene 11 -> B ->
       scene 07 -> scene 0F (`$0489=0`, `CHANGE ORD`) -> A/START ->
       **scene 03 field rendered** (`docs/high-team-field.png`).
2. [x] **Order-screen / field start (P0).**
       The proper 0F `$0489=0` A/START enters scene 03; the earlier
       `$0489=FF` stall was the wrong (END) path.
3. [ ] **Pitch / card loop (P0).**
       The field renders but does not pitch: `$0545=0`, `$05D3=06`,
       `$047F=7C`, `$95=0`, `$C7=0`; the `$96E6` live-field init is never
       dispatched. Next: dispatch `$96E6` / drive `$0545` through the
       `$9011`/`$903C` card steps.
4. [ ] **LIST OF TEAMS names (P1).**
       The stock list screen repeats JAPAN; wire the bank-9 32-team names.
5. [ ] **Match-5 soak stall (P1).**
       26-match speed soak: match 5 (09 v 0A) times out at 40k frames.
6. [ ] **Scene 1E/1F / match-26 (P1).**
       `direct31` scene 1E/1F entries are `$0101`/bank `$AD`; relocate the
       stock table or add a safe handler.
7. [ ] **32-team password screen wiring (P2).**
       Stock alphabet `5 7 H J K M O Q S U e g h j l n`; 11-char base-32
       codec done; wire the screen or the entry/continue code.
8. [ ] **In-game bench / attribute card (P2).**
       START-menu substitution/pitcher change + printed power/speed/skill.
9. [ ] **Hardware / sound execution (P2).**
       Run `docs/hardware-checklist.md` and `docs/sound-checklist.md`.
10. [ ] **STEP 2 audit: find new need areas and write the next TODO.**

## Done / do not re-open

- 32-team bracket state, real codes, nametable clear, layout, cold-boot
  2 KB RAM seed reaching the bracket.
- Launch bridge validated on the stock 16-team base; 32-team data applied
  to `launch-prod` (extra rosters/names/ratings/lineups; the cosmetic
  round-label step fails at `$8077` because the launch-prod draw differs).
- High-team matchup and live field entry (scene 03, `$0489=0`).
- Password codecs/screen capture; teams 16-31 data; roster cache; web
  editor; CLI; build manifest; stock regression green.
