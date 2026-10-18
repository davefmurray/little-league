# Little League hack — living TODO

**Last updated:** commit `fe69d44` (MMC1 skill)
**Target:** 32 teams × 20 players, 32-team tournament, emulator-first,
MMC1 / 256 KiB PRG / 128 KiB CHR.

Update this file in the same commit as any change to status. Keep the "Now"
section to five items or fewer.

---

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

- [ ] **Integrate the selector into the game flow.** Replace the 16-team
      list/map path with the bank-10 selector and pass the chosen team
      (`$07C3`) into the bracket setup. Today the selector is a standalone
      boot ROM (`build/select-screen.nes`).
- [ ] **On-demand roster cache for teams 16–31.** Boot caches only 0–15.
      Add copy hooks at team-select confirm, player card and game load; copy
      `0x170` from bank 8 to `$6000 + slot*0x170`, update `$7F00` table.
- [x] **Flag data.** 32 × 24×16 flags generated and packed into bank 10
      (`$A000`), 48 CHR slots reserved, four palettes at `$AC40`.
- [ ] **Draw flags in the grid.** 3×2 background tiles per cell, page-time CHR
      copy from bank 10 into the reserved slots, then add the nine-byte display
      list run per flag.
- [ ] **Bench / pinch-hitter bound + pitching test.** On the 16×20 build,
      confirm the 20-player bench is reachable and all three pitcher slots work.
- [ ] **32-slot bracket.** Five rounds, 32 first-round slots, new bracket table
      and screen. See `docs/expanding-teams-and-rosters.md`.
- [ ] **Password format** for 32 teams / 5 rounds.

## Next (P1)

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
