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
- [ ] **True 32-slot tournament.** `$8941`/`$0746` still describe the stock
      16-team / 15-match bracket; port the 32-slot state from
      `tools/build_32bracket.py` (`--state`).
- [x] **Teams 16–31 launch.** `--direct-teams` bypasses the 4-bit team
      unpack, and `tools/build_names32.py` extends the long/short name tables
      to 32 entries (the 16-entry tables hung scene 16). All 32 ids reach the
      field.
- [ ] **Real data for teams 16–31.** Bank 8 still holds team 15's block with
      `B1601`-style names, and the field HUD shows `FLO`/`JAPAN`. Fill the
      rosters/ratings/lineups/colours and the on-demand `$6000`/`$7F00` cache.
- [x] **Flag data.** 32 × 24×16 flags generated and packed into bank 10
      (`$A000`), 48 CHR slots reserved, four palettes at `$AC40`.
- [x] **Flag primitive.** Isolated test (`tools/build_flag_test.py`) proves the
      CHR copy and one 9-byte run render correctly.
- [x] **Draw flags in the grid.** Eight 24×16 flags above the codes, page-time
      CHR copy into safe slots, `append_flag` helper. Verified in-harness.
- [ ] **Bench / pinch-hitter bound + pitching test.** On the 16×20 build,
      confirm the 20-player bench is reachable and all three pitcher slots work.
- [ ] **32-slot bracket.** Five rounds, 32 first-round slots, new bracket table
      and screen. Koushien reference captured in `docs/koushien-bracket.md`.
- [ ] **Password format** for 32 teams / 5 rounds.

## Data-map completion (in progress)

- [ ] **Player attribute semantics in-game.** Prove byte 9 = power, byte 10 =
      speed, byte 11 = printed Skill by editing one player and reading the card.
- [x] **Pitcher record editing.** `roster.py` reads/writes the three 8-byte
      records; round-trip identical, mutation hits only `+0x109`/`+0x10E`.
- [x] **Flag writing.** `write_flags.py` swaps/repoints `$975A`;
      `import_flag.py` writes a 24x24 PNG into CHR bank `$1B` and its 9 tiles.
      Both verified by re-extraction.
- [~] **Bracket tables.** Found: bank-5 `$8941`, 15×3 records, slots `$0650`.
      32-team table (31×3) generated by `tools/bracket.py`. Blocked on RAM:
      63 slots + 32 loss counts don't fit `$0650–$068F`.
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

- [ ] Real data for teams 16–31: names, regions, colours, ratings, lineups.
- [ ] Extend team name/lineup/flag/rating/colour arrays to 32 teams.
- [ ] Bracket screen layout for 32 teams.
- [ ] CHR plan for flags: copy 8 flags' tiles or 3×2 sprite art; respect the
      71-empty-tile budget.
- [ ] Selector: page-memory polish, B-to-back behaviour, selected-team marker.
- [ ] Web editor: layout-driven 16/20/32-team support; load `data/teams32.json`;
      export the 32×20 build variant.
- [ ] Serve a downloadable patched ROM from the editor? Decide policy.

## Later / nice to have

- [ ] Full-game soak test (9 innings, subs, save/password).
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
- [ ] Find real score bytes via scoreboard draw / RAM diff.
- [ ] Compute winner and write $7720 + (match/2).
- [ ] Write winner into $7720 + (match/2); add round map.
- [ ] Post-game return to bracket.
- [ ] Advance winner into `$7700` / wins `$7740`.
- [ ] Redraw bracket after each game.
- [ ] Five-round soak with forced winners; champion at slot 62.
- [ ] Acceptance: 31 wins, five rounds, regression green.

### P2 — Password (deferred)

- [ ] 32-team / 5-round password encode + decode.
- [ ] 100 random round-trips.
- [ ] Wire into stock password screen.
- [ ] Keep stock 16-team password path working.

### P3 — Content correctness (deferred)

- [ ] Real names/regions/colours/ratings/lineups for teams 16–31.
- [ ] On-demand roster cache for teams 16–31.
- [ ] 20-player bench + all three pitcher slots.
- [ ] Prove power/speed/skill byte semantics in-game.

### P4 — Polish (deferred)

- [ ] Bracket top-row clipping, cursor marker, round labels, champion screen.
- [ ] Post-game bracket CHR bank restore (currently corrupted tiles).
- [ ] Web editor 32×20.
- [ ] Final user-facing writeup.
