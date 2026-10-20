# TODO — FINISH LIST (Step 1), then STEP 2 audit

This is the ordered finish queue. Each item gets a romdev probe or a ROM
change, a commit, and a report/TODO update. Historical detail is in
`docs/AUTORUN-REPORT.md`.

## Step 1 — finish the list

1. [ ] **Seeded bracket A launch / high-team field (P0).**
       The seeded ROM boots straight to the 32-team bracket (cursor 16,
       `$07FC=8`). A still does not launch: the bracket input's A edge is
       not producing the `$04EF/$04F0` write, and the `--launch-on-a`
       `JMP $8300` branch never runs. The real launch path exists:
       `tools/build_launch_bridge.py` hooks scene-18 `$98B9` -> `$FF20`
       (NMI guards, `JSR $8000`, `$FF60` team seed, resume `$98C0`,
       `--direct-teams`/`--skip-password`), but it is **not in
       build_32team_full** and `$FF20` is occupied by the stock boot table.
       `build/launch-prod.nes` validates the bridge on the 16-team base.
       Rebuild `launch-prod` + `build_extra_rosters`/`build_names32` + the
       data chain, then patch `$FF60` (currently `$7700[0..15]`) to the
       selected bracket pair; then drive AUS/CUB through scene 13/11/0F and
       the field. The data chain (extra rosters/names/ratings/lineups) applies
       to launch-prod, but `build_round_labels` fails at `$8077` (WIN tail
       layout differs); adapt/skip those cosmetic steps.
2. [ ] **High-team order-screen / field start (P0).**
       If the match still stalls at scene 0F, fix `$0489`/`$95`/`$C7` or
       force the field entry from the order screen.
3. [ ] **LIST OF TEAMS names (P1).**
       The stock list screen repeats JAPAN; wire the bank-9 32-team names
       into that list.
4. [ ] **Field render / SPEED MODE (P1).**
       The bracket match auto-simulates to the box score; trace the scene-03
       render and confirm SPEED MODE shows the live field.
5. [ ] **Match-5 soak stall (P1).**
       26-match speed soak: matches 0-4 pass, match 5 (09 v 0A) times out at
       40k frames. Capture the timeout state; fix or document.
6. [ ] **Scene 1E/1F / match-26 (P1).**
       `direct31` scene 1E/1F entries are `$0101`/bank `$AD`; relocate the
       stock scene table for the 16-bank layout or add a safe handler.
7. [ ] **32-team password screen wiring (P2).**
       Stock alphabet confirmed: `5 7 H J K M O Q S U e g h j l n`; 11-char
       base-32 codec done. Decide/implement the screen (wider buffer or
       entry/continue code) and keep the stock `$074D` path.
8. [ ] **In-game bench / attribute card (P2).**
       Once the field is live: START-menu substitution/pitcher change and a
       printed power/speed/skill card read.
9. [ ] **Hardware / sound execution (P2).**
       Run `docs/hardware-checklist.md` and `docs/sound-checklist.md` on a
       flash cart/MMC1 donor and capture results.

## Step 2 — needs audit

10. [ ] **Audit remaining gaps and write a new TODO list.**
        After 1-9, inspect the build/tools/docs for new need areas and
        produce the next prioritized list.

## Done / do not re-open

- 32-team bracket state, five rounds, champion slot 62.
- Real bracket codes, nametable clear, header/title layout.
- Cold-boot 2 KB RAM seed reaches the 32-team bracket.
- Password hex/letter/stock-tile/stock-ascii/11-char codecs + live screen.
- Teams 16-31 data, roster cache, web editor, CLI, build manifest.
- Stock regression green; docs/hardware/sound/distribution writeups.
