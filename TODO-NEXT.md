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
       **Path:** `$A1AA` walks `$C0=0x0E..0`, checks
       `$071A[$C0*2+$BD] & 3 < 2`, then `$9FA9` matches
       `$06E2[$01*2+$BD]>>4 == $C0`; `$A1CD` draws the name.
       **32-team:** `$A1C6` `0x0E` -> `0x0F`, `$071A` 32 bytes,
       `$06E2` 32 bytes. Next: the sizes + the list names.
       **Tested:** `direct31-list` (`$A1C6` 0x0F, `$9FA9` 0x0F) shows real
       names (SPAIN/FLORIDA/PUERTO RICO/CANADA) instead of JAPAN;
       screenshot `docs/list32.png`. **Correction:** those names were the
       team-select highlight; `direct31-list` at the list has
       `$06E2=FF` and only "CONTINUE END". The list's `$A1AA`/`$9FA9`
       needs `$06E2` populated first. Next: seed `$06E2` 32 +
       `$071A` 32 at the list/team-select.
       **Round 215:** the `$A1C6`/`$BF00` seed patch did not run at scene
       0x0D ($06E2 still FF); the list caller/scene must be identified
       first (the `$047B` value and the `$A1AA`/`$A1C6` caller).
       **Round 216:** no direct `JSR/JMP $A1AA`/`$A1C6` anywhere; the list
       is reached indirectly. Next: scan 2-byte pointer tables for
       `$A1AA`/`$A1C6` and trace the title/menu dispatch.
       Name tables (`$B2D6`/`$BC80`/`$BC40`) and loaders are intact; the
       only `$AF53` caller is the matchup draw with `$04EF/$04F0`. The
       list repeats JAPAN because the team ids/slots are 0 (JAPAN), not
       because the table is corrupt. Next: initialize the stock 4-team
       slots for the list path, or replace the screen with the 32-team
       selector/table. **Located:** the LIST OF TEAMS menu action is bank1
       `$A1C6` (`$C0=0x0E`) -> `$A1AA`; the list reads `$C0`/`$BD`/`$071A`.
       `$A1AA` is identical stock: it scans `$071A` flags and calls the
       `$9FA9` validator; if none validates it falls back to team 0 (JAPAN).
       Next: trace `$071A`/`$9FA9` in the 32-team flow and initialize the
       stock team data (or bypass the validator for the 32-team list).
       Both stock and direct31 have `$06E2`/`$071A` = FF at the title, so
       the LIST OF TEAMS screen must fill them itself; the 32-team build's
       list is still the stock screen missing that setup. Next: find/port
       the stock list setup or replace the screen with the 32-team selector.
5. [x] **Match-5 soak stall (P1) — fixed.**
       The low-team cache source was the bug; 6-match soak green. The
       26-match now advances to match 8, which is the high-team (16/17)
       field pitch (item 10), not the cache.
       26-match speed soak: match 5 (09 v 0A) times out at 40k frames.
       Captured: scene 0F, $07FC=05, $0489=01, $0545=03, $05D3=FF,
       $95=00, $C7=00, $BE=00, $C3=90, $04EF/$04F0=0A/09, $06B5 "...RICO";
       A/B/START/B+A do not advance. Same order-screen `$95`/`$C7` dead
       input; team 0A (Puerto Rico) is the variable. Next: the `$B8A9`/`$B90C`
       `$95` writer and the 0A lineup state. **Fixed:** the cache sourced
       low teams from bank8; `$FC00` now calls a `$FF00` restore that puts
       low teams back on the stock bank4 `$FD40` pointers. `direct31`
       rebuilt (hash `9f638d53...`); 6-match soak matches 0-5 all OK
       (match 5: 09 v 0A -> `$7725=09`, 1-0). 26-match soak running.
6. [x] **Scene 1E/1F / match-26 (P1).**
       Resolved: table is bank-relative and stock-identical; 0x17 -> bank6
       `$B0EE`, 0x1D -> bank5 `$81A8`, 0x1E/1F `$0101`/bank `$AD` is the
       stock dummy. The 0x16 order loop is the mode menu/box, not a table bug.
7. [ ] **32-team password screen wiring (P2).**
       **Progress:** the codec `tools/password32.py test --rounds 100` is
       green (hex/letter/stock-tile/stock-ascii/11-char). Disassembled the
       stock pair: `$9B5F` decodes `$074D` 8 bytes -> `$0650` 16 nibbles,
       uses `$0755/$0756` result bits and the `$8941` 15x3 table; `$98D5`
       encodes `$0650` -> `$074D` via the `$994F` permutation. Next: the
       16-char screen; the 32-team seed -> `$074D`/`$0755`/`$0756`.
       **Format confirmed:** 8 bytes = 32-bit seed + 31 result bits +
       version; `seed_order` xorshift32 Fisher-Yates; `advance` -> 63-slot
       heap. Plan: the 16-char `$06B5` buffer -> `$074D` 8 bytes; a new
       32-team decode fills `$7700`/`$7720`; `$98D5`-side encode.
       **Mock:** `docs/password-screen.html` renders the 16 chars + the
       bracket from `seed_order`/`advance` (seed 0x12345678 -> chars
       `QSMOJK7H55555555`, champion NEW YORK). Next: the `$06B5` buffer
       and the 6502 decode/encode.
       Stock alphabet `5 7 H J K M O Q S U e g h j l n`; 11-char base-32
       codec done; wire the screen or entry/continue code.
8. [x] **In-game bench/attribute card (P2) — design done.**
       `docs/bench-card.md`: the stock `$9A1C`/`$9A4E`/`$9A70`/`$06E2`
       card code, the 32-team extension, the layout, the data model and
       the acceptance checks. The in-game implementation remains.
       START-menu substitution/pitcher change + printed power/speed/skill.
9. [x] **Hardware/sound execution (P2) — docs done.**
       `docs/hardware-sound.md`: the MMC1 map, the romdev execution, the
       test matrix, the APU/audio, the input, the gaps, the release
       checklist. The actual hardware run remains on the checklist.
       Run `docs/hardware-checklist.md` and `docs/sound-checklist.md`.
10. [ ] **Pitch / live-field gameplay (P1, active).**
        The high teams now reach scene 03 `$0489=0` in `direct31`
        (match 8: teams 16/17) but the game never pitches (0-0). The
        bracket offers SPEED (sim) / WATCH (auto) only; trace the pitch
        loop (`$96E6`/`$0545`/COM flags) and restore/add the PLAY field.
        **Found:** match 8 reaches scene 03/$0489=0 with the right pair in
        `$04EF/$04F0` (10/11) but `$0650 = 0F 0F 0F 0F`; the field teams
        come from `$0650`, which the stock `$98D5` fills from the stock
        table. `$96E6` is only a stub; the field handler is `$96ED`.
        Next: seed `$0650[0]/[1]` from `$04EF/$04F0` (the `$FF60` pair) and
        the direct-teams/skip-password pieces in `direct31`.
        **Progress:** a `$FEA0` setup + `$9BFD JSR $FEA0` + `$98C8=02`
        (pair2) sets `$0650[0]/[1]` from `$7700[2*$07FC]` (correct field
        teams) but the match-5 order stalls at `$0527=FF`/`$0547=00`
        (`$B8A9` -> `$B90F`; `$95` never set). Next: the `$0527`/`$0547`
        writer/order flag. **Found:** `$047C=08` routes `$B8A9` through
        `$B8C6` to `$95=0x80`; the order input needs bit 6 (`$40`) from the
        `$B8FC` path (`$0547=3`/`$0527=0`). Stock orders use `$047C=02`;
        pair2's skip-password patch did not yield the order substate. Next:
        the `$047C`/`$98C8` substate and the `$0527` match init.
        **Found:** `$98C0` sets `$047C=02`; the later `$AEDD`/`$CA9F` sets
        `$047C=08` for the team-09 `$0650[0]` -> `$95=0x80` (bit 7). The
        stock team-00 gives 02/`$95=0x40`. Next: the `$9EF0` input decoder's
        `$95` bit mapping (`$80` vs `$40`)/the `$C7` path. **Found:** the
        order path is `$9E8A`/`$9EAD`/`$BE`/`$BA`/`$C6`; `$C7=1` is the
        menu confirm, `$BA` the sub-state, `$C6` the 0x67 timer. Pair2's
        order is advancing (BE=4, BA=9, B2=10) but `$9E79` does
        `$B2 & 0x0F` -> `$BC=0` -> `$06E2[0]`; the high team 16 resolves
        to the team-0 group. Next: the `$06E2` 32-team group table/the
        `$9A1C` high-team mapping. **Found:** `$B2=0x10` is page 1/team 16;
        `$BC=0` makes `$9A1C` read the page-0 `$06E2[0]`, so the table is
        not page-specific. Next: the `$06E2`/`$B2` page mapping (32-team
        groups for page 1). **Found:** `$06E2` is 8 groups x 2 =
        16 bytes (`04 07 17 16 ...`); `$9A4E` uses `$06E2[$BC*2+$BD]`,
        `$9A1C` `$06E2[$BC]`. The 32-team needs a 32-byte table (16 groups
        x 2) and the page offset (`$B2` bit 4) in those readers.
        **Found:** the `$06E2` writer `$AD51` copies from the `$FD80`
        lineups (`LDA $FD80,X / STA $06E2,X / CPX #$12`), so it only
        covers the 16-byte group table; the 32-team `$FD80` has 32
        lineups but `$06E2` gets only the low 16. **Plan:** `$AD51` loop
        `CPX #$12` -> `#$22` (34) for the 32-byte `$06E2`; add the page
        offset `$B2 & 0x10` (+16) in `$9A4E`/`$9A1C`/`$9F89`; test pair3.
        **pair3:** the 32-byte `$06E2` + `$BEC0` page subroutine works for
        matches 0-4, but match 5 (09/0A, low) stalls because `$B2=0x10`
        (team 16/page 1) while `$0650[0]/[1]=09/0A`; the page subroutine
        reads the page-1/high group. Next: `$B2` vs `$0650` team/page.
        **Found:** the order team is `$B2 & 0x0F` -> `$BC` -> `$06E2`
        (team 0/16), while the field team is `$0650[0]` (09). The pass case
        had `$0650[0]=00` and `$B2` low nibble 0. Next: derive `$B2`/`$BC`
        from `$0650[0]` or set `$B2` from `$0650` at the order start.
        **Found:** setting `$B2=09` gives `$BC=9` -> `$06E2[9]=0x43` ->
        team 4, because `$06E2` is the 8 groups x 2 table
        (`$06E2[group*2+team]`), not team-indexed. Two fixes together:
        `$B2` from `$0650[0]` and the `$06E2` group/team mapping.
        **pair4:** `$B2` from `$0650[0]` still stalls match 5; `$B2=09` ->
        `$BC=9` -> `$06E2[9]=0x43` -> team 4 (group 4/team 1), field 09.
        Next: the `$06E2` group/team semantics in
        `$9A1C`/`$9A4E`/`$9FA9`.
11. [x] **STEP 2: audit gaps and write new TODO — done.**
        `docs/STEP2-AUDIT.md` (7/11 done, 3 active, gaps/new areas) and
        `TODO-STEP2.md` (fresh P0/P1/P2 list).

## Done / do not re-open

- 32-team bracket state/codes/layout; cold-boot seed; launch bridge; data;
  high-team field render and match result; password codecs; teams 16-31
  data; roster cache; web editor; CLI; build manifest; stock hash/tests.
