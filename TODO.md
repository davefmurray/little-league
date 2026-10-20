# Little League hack — living TODO

**Last updated:** commit `fe69d44` (MMC1 skill)
**Target:** 32 teams × 20 players, 32-team tournament, emulator-first,
MMC1 / 256 KiB PRG / 128 KiB CHR.

Update this file in the same commit as any change to status. Keep the "Now"
section to five items or fewer.

---

## Plan of record (adopted)

**New 32-team bracket scene in bank 11; stock 16-team path untouched.**
Full plan: `docs/PLAN-32-TEAM.md` (Fable 5.1, repo-verified).

The `--state` bracket patch is now a **reference implementation**, not the
shipped path. No more reset-vector hacks.

M4 static bracket screen renders 32 codes in four columns (`docs/bracket-screen.png`); header/cursor/A-handoff still missing. M3 bank-11 logic is implemented and py65-tested (`tools/build_bank11.py`): init,
31-match advance, champion slot 62, win counts sum 31. M2 handoff contract documented in `docs/bracket-handoff.md`: `$04EF/$04F0` are
the two team ids; `$04EB/$04EC` alive; `$074B/$074C` results. M1 dispatcher is
implemented and verified (`tools/build_dispatcher.py`). Next: M2 poke test and
M3 logic port to bank 11.

## Status snapshot

| Area | State |
|---|---|
| ROM base | 128 KiB → **256 KiB**, 16 PRG banks, fixed bank 15 |
| Rosters | **32 × 20** in bank 8; teams 16–31 placeholder |
| PRG-RAM cache | 16 active teams at `$6000`; table `$7F00` |
| Data tables | bank 9: codes `$8000`, names `$8080`, regions `$8280` |
| Team select | bank 10, **4 pages × 8**, cursor, edge paging, detail, A/OK, B/clear |
| Selector integration | **not wired** into the game flow |
| Tournament | still 16-team; **32-slot bracket not started** |
| Password | still 16-team format; **not redesigned** |
| Flags | region flags only; 3×3 = 9 sprites; no 32 team flags |
| CHR | 128 KiB full; 71 empty tiles in bank 0 |
| Web editor | 16 × 15 hardcoded; **not 32 × 20 yet** |
| Hosting | editor/docs only; ROM not served |

---

## Now (P0)

- [x] **Fix variable team bases.** `tools/llbcs_map.py` now holds the verified
      bases; `roster.py` and `build_16x20.py` use it. Puerto Rico extracts
      `EMILLO…` correctly and the rebuilt ROM boots.
- [ ] **Mirror the base table in the web editor** (if it computes offsets).
- [x] **Fix colour model.** Two 16-byte tables at `$FAC0`/`$FAD0`; extracted
      and applied in `roster.py`.
- [x] **Fix flag extraction.** Bank-4 offset table `$975A` + records `$976A`,
      CHR bank `$1B`; all 16 flags regenerate (`docs/flags-extracted.png`).
- [x] **Fix lineup parser.** 9 packed-nibble bytes per team at `$96CA`; decoded
      to order/position and round-tripped byte-identically.

- [x] **Integrate the selector into the game flow.** Selector A sets `$07C3`,
      hands the stock dispatcher scene 18 and the bridge runs the bracket.
      Full flow reaches the field (selector → bracket → password → matchup →
      speed mode → cutscene → field).
- [x] **Bracket → game launch bridge.** `$98B9` (scene 18) tail-jumps to a
      fixed-bank trampoline that runs bank 11, rebuilds the password and
      re-enters the stock scene-18 body. Password → matchup → speed mode →
      cutscene → field verified, `S=$FF`, regression green. See
      `docs/LAUNCH-DEBUG-LOG.md`; build with `tools/build_launch_bridge.py`.
- [x] **Team handoff through the bridge.** `$FF60` copies `$7700[0..15]`
      into `$0650` and repacks `$074D`; `$9C00` reads
      `$0650[$8941[3*$0746]]` into `$04EF/$04F0`. Field now shows the
      bracket's first-round pair (JAPAN vs ARI).
- [x] **True 32-slot tournament.** Done via `build_32bracket.py`/the bank-11
      63-slot heap; the stock `$8941` 15-match table is no longer the bracket
      source.
- [x] **Teams 16–31 launch.** `--direct-teams` bypasses the 4-bit team
      unpack, and `tools/build_names32.py` extends the long/short name tables
      to 32 entries (the 16-entry tables hung scene 16). All 32 ids reach the
      field.
- [x] **Names/codes/regions for teams 16–31.** `data/teams32.json` now has
      AUSTRALIA, CUBA, DOMINICAN REP, VENEZUELA, PANAMA, NETHERLANDS, GERMANY,
      SOUTH AFRICA, BRAZIL, COLOMBIA, NICARAGUA, PHILIPPINES, HONG KONG, GUAM,
      NEW ZEALAND, CZECH REPUBLIC. Selector page 3 verified.
- [x] **Roster data for teams 16–31.** `data/roster32.json` + 
      `tools/build_extra_rosters.py` write 20 generated players and three
      pitcher records per team into bank 8.
- [x] **On-demand roster cache for teams 16–31.** Working build
      `build/direct31.nes`: MMC1 reset before the bank-8 switch, real ids,
      `$7800/$7A00` copies, `$7F00` repoints. Match 8 shows HARRIS/GARCIA
      and reaches the field (scene 03).
- [ ] High-team field auto-play: teams 16/17 reach scene 03 and run frames
      but never pitch (0-0). Ruled out: NMI/vblank, trailer stub, COM flags,
      `$C1`, `$04/$05` (hardcoded card pointer), and `$047E`. Next: the
      scene-3 card/lineup setup or the pitch loop.
- [x] **Ratings for teams 16–31.** 32 x 4 table at bank3 `$BC80`
      (`tools/build_ratings32.py`), reader repointed.
- [x] **Lineups for teams 16–31.** 32 x 9 table in the fixed bank at `$FD80`
      (`tools/build_lineups32.py`), reader repointed.
- [x] **Colours for teams 16–31.** Audited: the `$BAC0`/`$BAD0` tables have
      no absolute, indexed, or pointer consumer in this revision, so there is
      nothing to repoint; the 32-team colour table is a no-op for this ROM.
- [x] **Flag data.** 32 × 24×16 flags generated and packed into bank 10
      (`$A000`), 48 CHR slots reserved, four palettes at `$AC40`.
- [x] **Flag primitive.** Isolated test (`tools/build_flag_test.py`) proves the
      CHR copy and one 9-byte run render correctly.
- [x] **Draw flags in the grid.** Eight 24×16 flags above the codes, page-time
      CHR copy into safe slots, `append_flag` helper. Verified in-harness.
- [ ] **Bench / pinch-hitter bound + pitching test.** On the 16×20 build,
      confirm the 20-player bench is reachable and all three pitcher slots work.
- [x] **32-slot bracket.** Five rounds, 32 first-round slots, new bracket table
      and screen. Koushien reference captured in `docs/koushien-bracket.md`.
- [x] **Password format** for 32 teams / 5 rounds (model:
      `tools/password32.py`; the stock 11-character letter screen is still
      the wiring blocker).

## Data-map completion (in progress)

- [ ] **Player attribute semantics in-game.** Prove byte 9 = power, byte 10 =
      speed, byte 11 = printed Skill by editing one player and reading the card.
- [x] **Pitcher record editing.** `roster.py` reads/writes the three 8-byte
      records; round-trip identical, mutation hits only `+0x109`/`+0x10E`.
- [x] **Flag writing.** `write_flags.py` swaps/repoints `$975A`;
      `import_flag.py` writes a 24x24 PNG into CHR bank `$1B` and its 9 tiles.
      Both verified by re-extraction.
- [x] **Bracket tables.** Found: bank-5 `$8941`, 15×3 records; the 32-team
      table (31×3) is generated by `tools/bracket.py` and relocated to fixed
      `$FC00` with the readers repointed.
- [x] **Bracket table relocation.** 31 records at fixed `$FC00`; readers
      repointed; ROM boots.
- [x] **32-team bracket state.** Seeds `$FD00`, slots `$6800`, losses `$6840`;
      init/advance/display patched. CPU-validated through five rounds. Opt-in
      via `--state` so the default build keeps the stock seed path.
- [x] **Bracket entry root cause.** jsnes 1.2.1 MMC1 counter needs a bit-7
      reset; use `STX $9FFF`, control `$1E`, `$C14E` shadow. Probe verified.
- [ ] **Wire bracket entry.** Feed 32 teams from the selector/password and enter
      the bracket screen; today the stock flow still seeds 16.
- [ ] **Passwords.** Locate encode/decode; extend to 32 teams.

## Next (P1)

- [x] **Text table.** `data/llbcs.tbl` + `tools/tbl.py`; verified team/menu
      strings at `$5190`, `$51E0`, `$568A`, `$7306`.
- [x] **RAM map.** Pitcher state `$04EE–$04FE`, game state `$0487–$048C`,
      display buffers and selector state documented in `docs/ram-map.md`.

- [x] **Cheat/ROM-map research.** Game Genie codes decoded to ROM offsets and
      RAM-map addresses documented in `docs/cheats-and-ram.md`.
- [ ] **Capture DataCrystal ROM map.** Page is Cloudflare-blocked and has no
      Wayback snapshot; needs a browser session, then reconcile with our docs.

- [x] **ROM debugger.** `tools/debugger.html`: registers, named watches, OAM,
      display list, write-to-address log with PC.

- [x] Real data for teams 16–31: names, regions, ratings, lineups (done);
      colours have no consumer in this revision.
- [ ] Extend team name/lineup/flag/rating/colour arrays to 32 teams.
- [ ] Bracket screen layout for 32 teams.
- [ ] CHR plan for flags: copy 8 flags' tiles or 3×2 sprite art; respect the
      71-empty-tile budget.
- [ ] Selector: page-memory polish, B-to-back behaviour, selected-team marker.
- [x] Web editor: 32 x 20 JSON mode (`web/roster32.json`, Data -> Load
      32-team demo). Verified 32 team cards / 20 player rows.
- [x] Web editor ROM mode: parse/export the bank8 `t*$170` 32-team layout,
      20 players, bank9 names, bank3 ratings; stock 16 x 15 round-trip
      remains byte-identical.
- [ ] Serve a downloadable patched ROM from the editor? Decide policy.

## Later / nice to have

- [ ] Full-game soak: 26 complete real games (matches 0-25, all 16 R1, all
      8 R2, 2 R3) under the COM/cutscene handler. This game is 6 innings, not
      9. Substitution/save-password runs remain open.
- [ ] Hardware validation on a flash cart / MMC1 donor.
- [ ] Sound/music checks after data moves.
- [ ] Docs: regenerate screenshots, update README status table.
- [ ] CI: build variants on push, publish checksums.

---

## Decisions locked

- 20 players per team, 32 teams, expanded tournament.
- Stay at **256 KiB PRG / 128 KiB CHR / MMC1**. 512 KiB + 128 KiB CHR is not a
  valid MMC1 configuration (CHR0 bit 4 is A18 vs CHR A16).
- Copy-on-select through PRG RAM; readers stay untouched.
- Team select: **4 pages × 8**, 2 rows × 4, codes + detail bar.
- Flag route: **sprites 3×2** recommended over background tiles.

## Open questions

- Are 24×16 flags acceptable, or do we need 24×24 (7 flags/page max)?
- Final names/regions/ratings for teams 16–31.
- Tournament seeding and bracket presentation.
- Password policy (checksum, length, team encoding).
- Real hardware target: flash cart only, or MMC1 donor board?

---

## Key addresses

| Thing | Address |
|---|---|
| Selector code (bank 10) | `$8000` |
| Selector page lists | `$9000`, 160-byte stride |
| Selector palette / marker / page ptr | `$9300` / `$9320` / `$9330` |
| Selector names | `$9400`, 16 bytes/team |
| `SELECTED` | `$07C3` (`$FF` = none) |
| Page / cursor | `$07C0` / `$07C1` |
| PRG-RAM cache | `$6000` + `team*0x170` (first 16) |
| RAM roster table | `$7F00` |
| Bank-9 codes / names / regions | `$8000` / `$8080` / `$8280` |
| Flag tile offsets | `$975A`, records `$976A` |
| Flag CHR banks | `$FB4E`, 6 bytes/team |
| OAM flag (ground truth) | 3×3, tiles `$05–$0A`, attr `$02`, CHR `$1B`, palette 2 |

## Build / test commands

```sh
# 16 x 20 base
python3 tools/build_16x20.py "Little League Baseball - Championship Series (USA).nes" data/roster.json -o build/16x20.nes

# 32 x 20 bank-8 data + PRG-RAM cache
python3 tools/build_32x20.py "Little League Baseball - Championship Series (USA).nes" data/roster.json -o build/32x20.nes

# bank-9 team table
python3 tools/pack_team_table.py build/32x20.nes data/teams32.json -o build/32x20-ui.nes

# bank-10 selector (boots straight into it)
python3 tools/build_select_screen.py build/32x20-ui.nes data/teams32.json -o build/select-screen.nes

# test harness
python3 -m http.server 8097 --bind 127.0.0.1
# http://127.0.0.1:8097/tools/harness.html?rom=../build/select-screen.nes
```

## Reference docs

- `docs/expanding-teams-and-rosters.md` — data map, space math, milestones.
- `docs/palette-notes.md` — PPU palette/attribute constraints.
- `docs/flags-in-chr.md` — flag packing prototype and notes.
- `docs/rom-layout.md` — cartridge, MMC1 helpers, vectors.
- `docs/roster-format.md` — roster records and fields.
- `.claude/skills/mmc1/SKILL.md` — MMC1 operational playbook.

---

## Launch bridge / post-launch (authoritative as of `bc05155`)

**Scope for the current run: P0 then P1. Stop after P1.**
Do not start P2–P4 until P0/P1 are green or explicitly re-prioritized.

### P0 — Launch bridge (GREEN)

Bracket runs; A crashes at `$B005` before the `$8162` A branch. Saved frame is
intact (`$98BB`, `S=$FB`). Full details and dead ends: `docs/HANDOFF.md`.

- [x] Break `$810B` / `$8126` with A held; capture `S` at entry/return.
- [x] Capture interrupt state at `$B005`: `$2C`, `$AD`, `$047D`, `$2000`, `$2001`.
- [x] Branch-bypass discriminator: patch `$8160 BEQ` to `EA EA`.
- [x] Minimal ROM: `JSR $810B; JMP $B005`.
- [x] Acceptance: bracket A → stock matchup → playable field.
      Proof: `docs/p0-field.png`.
- [x] Cleanup: remove diagnostic `$B005` JAM guard, rebuild without corrupting
      the team-code table, re-verify launch and stock regression.
- [x] Fix duplicate team: matches now show JAPAN vs ARIZONA; IDs read from `$07FA/$07FB`.

### P1 — Tournament loop

- [x] Carry real bracket pairing into matchup ($7700/$7701).
- [x] Expand bracket state to 63 slots (32 seeds + 31 FF winner slots).
- [x] Reach live gameplay scene 3 (FLORIDA vs JAPAN, 0-0).
- [x] Prove $0515/$0516 are not scores (poke has no effect).
- [x] Find real score bytes: `$048B`/`$048C` (scoring `INC $048B,X` at
      bank7 `$A418`; HUD reads at bank4 `$B133/$B141`). `$04ED` selects the side.
- [x] Use `$048B/$048C` to choose the winner instead of the forced first team.
      Verified: match 0 (`0F/00`, 0-2 -> `00`), match 1 (`01/02`, 1-2 -> `02`),
      round-2 probe (`00/02`, 0-2 -> slot 48 `$7730=02`).
- [x] Match index `$07FC`: pair `$7700[2m]`/`$7700[2m+1]`; forced winner to
      `$7720[m]`; increment. Heap destination is `32+m`, not `32+(m>>1)`.
- [x] Post-game return to bracket (functional; CHR/tile corruption is P4).
- [x] Advance winner across rounds: round-2 probe wrote slot 48 (`$7730`) and
      advanced the index to 17.
- [x] Redraw bracket after each game: `"WIN<code>"` line at `$22A1`, updated
      from `$7720[$07FC-1]` by `tools/build_winner_display.py`. Tiles are still
      hard to read because of the known post-game CHR-bank issue (P4).
- [x] High-team launch mapping: `id & $0F` for the stock launch only, real ids
      kept in `$7700`. Match 8 (`10/11` -> `00/01`, score 5-0) wrote slot 40
      `$7728=10` and advanced the index.
- [x] Pre-game order screen: B selects END (`$BE=7`, handler bank1 `$9BAB`
      at `$9C3D`) and A confirms. Harness now uses B+A per team.
- [x] Five-round soak, champion at slot 62: **state-only GREEN**. 31/31
      calls to the real bank11 `$83A0` winner routine, champion `$773E=0F`,
      index 31 (`tools/state_soak.py`, `tools/build_winner_rts.py`).
- [x] Acceptance: 31 wins, five rounds, regression green (state-only soak;
      in-context games 0/1/8/16).
- [x] P1 closeout: state-only 31/31, champion `$773E=0F`, visible
      `"WIN<code>"` redraw, stock regression green. P1 scheduled loop disabled.
- [x] **P3 follow-up (mitigated):** real-game field control for some pairings.
      The soak harness reasserts `$04EB/$04EC=$80`, `$04E9=0` at scene 03 and
      presses A at a waiting cutscene. Real SPEED flow now passes matches 0-25
      with real scores (all round 1, all round 2, two round-3 games).
- [ ] **P3 stock-path follow-up:** match 26 (`11/13`, 2-0) goes to scene `$1D`
      and jams at `PC=$00C3`; the stock post-game path is past its 16-team
      design. State-only soak still covers champion math.

### P2 — Password (deferred)

- [x] Locate password encode/decode: encode/series init bank5 `$98D5`,
      decode/advance bank5 `$9B5F`; decode verified with
      `$074D=0123456789abcdef -> $0650=00..0F`. Format documented in
      `docs/password-format.md`.
- [x] 32-team / 5-round password encode + decode model
      (`tools/password32.py`: 4-byte seed + 31 result bits + version bit).
- [x] 100 random round-trips: `python3 tools/password32.py test` (100/100).
- [ ] Wire into stock password screen.
- [x] Keep the stock 16-team password path working: encoder `$98D5` ->
      decoder `$9B5F` round-trip is exact (`$0650` before == after,
      `$074D=35dca1b6f2479e80`).

### P3 — Content correctness (deferred)

- [x] Real names/codes/regions for teams 16–31.
- [x] Ratings table (bank3 `$BC80`) and lineups table (fixed `$FD80`).
- [x] Colours for teams 16–31 — audited, no reader/consumer in this ROM.
- [x] On-demand roster cache for teams 16–31 (`build/direct31.nes`,
      MMC1 reset + `$7800/$7A00` + `$7F00` repoints).
- [x] 20-player bench + three pitcher slots at the data level
      (`tools/audit_roster32.py`: 16 x (20 players + 3 records)).
- [ ] In-game substitution/pitcher test with a 20-player team.
- [ ] Prove power/speed/skill byte semantics in-game.

### P4 — Polish (deferred)

- [x] Bracket round labels: live `ROUND 1..5` / `CHAMPION` title from
      `$07FC` (`tools/build_round_labels.py`).
- [x] Champion screen: index 31 shows `CHAMPION` + the WIN line code.
- [x] Bracket top-row clipping: header/title moved down one row
      (`tools/build_top_row.py`).
- [x] Cursor marker: already drawn by the bracket input handler at `$0200`.
- [ ] Post-game bracket CHR bank restore (currently corrupted tiles).
- [ ] Web editor 32×20.
- [ ] Final user-facing writeup.
