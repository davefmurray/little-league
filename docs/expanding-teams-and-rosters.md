# Expanding teams and rosters

"More teams" and "more players per team" are two different projects with very
different costs.

- **More players per team** is a data-layout change. The tables are small, the
  menus are the only real risk, and it can be done without growing the cartridge.
- **More teams** changes the tournament, the team-select screens, the password
  format and the graphics. It is a UI and game-design project, not a table edit.

This document maps every hard-coded assumption, the space budget, and a phased
way to get to **32 teams × 20 players** without a rewrite.

---

## The limits as shipped

| Limit | Value | Where it lives |
|---|---|---|
| Teams | 16 | pointer table at `$8400`, 4×4 select grid, bracket, password |
| Players per team | 15 | 15 × 16-byte records per team |
| Team block | `0x120` bytes | 15 records + 48-byte pitcher trailer |
| Pitcher records | 3 × 8 bytes | trailer at team base + `$F0` |
| Tournament | 16 teams, 4 rounds | bracket table `$8941`, slots `$0650` |
| Cartridge | MMC1, 128 KiB PRG, 128 KiB CHR | header |

Team block size for *N* players is `N * 16 + 48`:

| Players | Stride | 16-team block | 32-team block |
|---|---|---|---|
| 15 | `0x120` | `0x1200` (4,608 B) | `0x2400` (9,216 B) |
| 18 | `0x150` | `0x1500` (5,376 B) | `0x2A00` (10,752 B) |
| 20 | `0x170` | `0x1700` (5,888 B) | `0x2E00` (11,776 B) |
| 24 | `0x1B0` | `0x1B00` (6,912 B) | `0x3600` (13,824 B) |

---

## Where the 16-team assumption lives

| System | Address | What assumes 16 | Work if you expand |
|---|---|---|---|
| Roster pointer table | `$8400` | 16 words, immediately followed by team 0's data at `$8420` | 32 words need a new home; 19 code references use `$8400,X` |
| Team long names | `$9180` (bank 1) | 16 × 16 bytes, 14 chars + `FF FF` | 32 × 16 = +256 B, and any name-list code |
| Team short names | pointers `$9280`, `$9290` | two 8-entry tables | one 32-entry table, or four 8-entry tables |
| Team ratings | `$B224` (bank 3) | 16 × 4 bytes | 128 B; the power-analysis routine at `$AFD4` indexes `team*4+3` |
| Team flags | `$975A` (bank 4) | 16 tile IDs | 32 IDs + 16 new flag tiles |
| Team colours | `$FAC0`, `$FAD0` (bank 7) | 16 + 16 palette bytes | 32 + 32 |
| Lineups | `$96CA` (bank 4) | 16 × 9 bytes | 32 × 9 = 288 B; `$AD44` computes `team*9` |
| Team select grid | `$CB52` (bank 7) | 4 rows × 4 teams, flags drawn from `$975A,X` | 8×4 paged grid or a scrollable list; new cursor/selection code |
| Team list bound | `$96CD` (bank 1) | `LDA #$0F; STA $CE` — max index 15 | set to `teams-1`; also check `$9BB3` (`LDA #$0F; STA $B1`) |
| Tournament bracket | `$8941` (bank 5) | 3-byte records per round: two team slots + next slot | regenerate for 5 rounds; new bracket screen layout |
| Bracket storage | `$0650` (RAM) | 16 first-round slots plus winners | 32 slots + 16 winners, and the round counter `$0746` |
| Password | `$A036` (bank 5) | 12 state bytes `$074B–$0756` + round `$0746` packed into chars | new encoding for more teams/rounds; verify checksum |
| CHR flags | CHR banks | flag tiles already in the 128 KiB CHR | 16 more flags must fit existing CHR (MMC1 cap) |

The 4×4 grid at `$CB52` is the clearest hard stop: it draws four rows of four
teams, 12 sprites wide, with no paging. A 32-team game needs a different screen,
not a bigger table.

---

## Where the 15-player assumption lives

| System | Address | What assumes 15 | Work |
|---|---|---|---|
| Player records | team base + 0..`$E0` | 15 × 16 bytes | add records; stride grows |
| Pitcher trailer | team base + `$F0` | FF row, then 3 pitcher records | moves to `N*16` |
| Trailer lookup | bank 4 `$B094` | computes `base + $100 + byte12` | must become `base + N*16 + $10 + byte12`; needs a trampoline, not a one-byte patch |
| Lineup | 9 players | fixed by baseball | unchanged |
| Player-change menu | unknown | likely draws 15 names / 3 rows of 5 | **discovery task**: find the list bound and grid height, patch to *N* |
| Player index arrays | `$04EF`, `$04FD`, `$06E2` | sized around the active lineup, not the roster | verify no overflow |

The one code change that is definitely required is the trailer math. The current
routine is:

```
$B094  LDX $04EE
$B097  LDA $04FD,X
$B09A  ASL A ×4          ; player index × 16
$B09E  JSR $B07C         ; $04 = team_base + player*16
$B0A1  CLC
$B0A2  LDY #$0C
$B0A4  LDA ($04),Y       ; byte 12: 08/10/18
$B0A6  ADC $8400,X       ; + team base low
$B0A9  STA $04
$B0AB  LDA $8401,X
$B0AE  ADC #$01          ; + $100
$B0B0  STA $05
$B0B2  RTS
```

For 20 players the trailer's first pitcher line is at `base + $150`, so the
routine must add `$150` instead of `$100`. There is no room in place for two more
bytes, so replace `$B094` with `JMP` to a relocated copy in free space that does:

```
LDA ($04),Y
ADC $8400,X
ADC #$50        ; extra $50 on top of the $100
STA $04
LDA $8401,X
ADC #$01        ; carry from the $50 propagates
STA $05
RTS
```

Every caller keeps calling `$B094`; only the destination moves.

---

## Space budget

### Inside the existing 128 KiB

Bank 4 free runs (all `$FF`):

| Range | Size |
|---|---|
| `$985A–$AA40` | 4,518 B |
| `$B6F7–$C000` | 2,313 B |

The original roster block (`$8420–$9620`) becomes free once rosters move, but it
is **not contiguous** with the free runs — lineups, flags and a large table at
`$976A–$985A` sit in between. That table is used, so it cannot be overwritten.

**16 × 20 fits in the free runs if teams are allowed to be non-contiguous:**

- teams 0–11 at `$985A + team * $170` (last block ends `$A9AA`, inside the run)
- teams 12–15 at `$B6F7 + (team-12) * $170` (last block ends `$BCB7`)
- the pointer table at `$8400` simply points at each block, so no relocation of
  lineups, flags or the `$976A` table is needed.

**32 × 20 does not fit** (`0x2E00` = 11,776 B vs 6,831 B free), even after
reclaiming the old roster block (11,439 B total — still short).

### Cartridge limits

| | MMC1 limit | This ROM |
|---|---|---|
| PRG | 32 × 16 KiB = **512 KiB** | 128 KiB (8 banks) |
| CHR | 32 × 4 KiB = **128 KiB** | 128 KiB — **already maxed** |

So PRG can grow to 256 or 512 KiB; CHR cannot grow at all. New team flags must
fit into the existing 128 KiB CHR (several banks are sparse: bank 18 is 82%
empty, bank 25 70%, bank 24 62%).

MMC1 fixes the **last** PRG bank at `$C000`. Growing from 8 to 16 banks moves the
fixed bank from 7 to 15, so the original bank 7 must be copied to bank 15 or the
reset vector disappears.

`tools/expand_rom.py` does exactly that and verifies the result:

```
$ python3 tools/expand_rom.py ROM -o build/expanded.nes --prg-banks 16
  size        393,232 bytes
  PRG         16 banks (256 KiB)
  CHR         16 banks (128 KiB, unchanged)
  fixed bank  15 (copy of original bank 7)
  vectors     $CD85/$CBD5/$CDF4
  free banks  8-14 (7 banks, 112 KiB)
```

---

## Progress log

- `tools/expand_rom.py` — done and verified: 16 PRG banks, fixed bank 15, banks
  8–14 free, banks 0–7 and CHR byte-identical.
- `tools/harness.html` — done: jsnes boots the stock ROM and patched builds in
  the browser; buttons plus `stepFrames` / `tap` console API.
- `tools/build_16x20.py` — done: 16 teams × 20 players, split across the two free
  runs, pointer table rewritten, trailer lookup relocated.
- 16 × 20 build tested: boots, title, menu, team select, pre-game lineup screen;
  all nine starter names load from the relocated records.
- Still to verify on 16 × 20: pitching from each of the three slots, the bench /
  pinch-hitter list (its bound is the remaining unknown), and a full game.
- 32-team build not started: needs the bank-8 migration, team-select paging,
  32-slot bracket and password work.

## Recommended path

### Milestone 0 — cartridge expansion (ready)

Use `tools/expand_rom.py` to make a 256 KiB PRG build. It is byte-identical to
the original in banks 0–7, so the unmodified game still runs; it just has 112 KiB
of new bank space and a relocated fixed bank. Boot-test in an emulator before
building on it.

### Milestone 1 — 16 teams × 20 players, in place

No cartridge expansion needed. This validates the trailer patch and the menus
before adding teams.

1. Build the new rosters in the two free runs (12 + 4 teams).
2. Rewrite the 16 pointers at `$8400` to the new bases.
3. Replace `$B094` with a `JMP` to the relocated trailer routine.
4. Find and patch the player-change list bound (15 → 20) and its grid height.
5. Update the editor/JSON layout to 20 players.
6. Test: pitching with each of the three slots, substitutions, player cards,
   pinch hitter/runner, lineup screen, full game.

Risk: the player-change menu is the only unknown. Everything else is table
plumbing.

### Bank-8 blocker (discovered while planning 32 × 20)

Moving the rosters to bank 8 is not a table move. Three roster readers live in
**bank 4 itself**:

| routine | what it does |
|---|---|
| `$AB2D` | reads the pointer table at `$8400,X` to set up the active players |
| `$B086` | computes the player pointer for the card/stat path |
| `$B0A7` | reads the pointer high byte for the same path |

Code running in bank 4 cannot switch to bank 8 and keep executing: the next
instruction fetch would come from the wrong bank. So a 32-team bank-8 layout
requires one of:

1. relocating those routines to the **fixed bank** (`$C000`, 1,133 free bytes at
   `$BB83`) and calling them there,
2. a fixed-bank trampoline that switches to bank 8, performs the record read,
   and switches back, or
3. copying the active teams' records into RAM at game start (only the active
   roster fits, not all 32).

Option 1 is the cleanest **if** the readers must move. But there is a better
route: **copy-on-select**.

### Chosen: copy-on-select

Keep all 32 rosters in bank 8, but never let the engine read them directly.

1. The old 16-team roster block in bank 4 (`$8420–$9620`, 4,608 bytes) becomes a
   **scratch area**.
2. When a team is selected, previewed or loaded into a game, a new routine in the
   **fixed bank** switches to bank 8, copies that team's `0x170` block into
   scratch, switches back to bank 4, and repoints that team's entry in the
   `$8400` table at the scratch address.
3. Two teams per game × `0x170` = 736 bytes, so both fit in scratch with room to
   spare.
4. Every existing bank-4 reader keeps working unchanged — it still reads
   `$8400,X` and still gets a bank-4 address.

This avoids relocating any code. The only new code is the copy routine (fixed
bank, free space at `$BB83`) plus hooks at the team-select confirm, the player
card, and game start. It is the approach the 32-team build will use.

The 16 × 20 build keeps rosters permanently in bank 4, which is why it works
without any of this.

### Milestone 2 — 32 teams × 20 players

1. Build the 256 KiB PRG image with `expand_rom.py`.
2. Put the new roster block in **bank 8**: 32 × `0x170` = `0x2E00`, plus the
   64-byte pointer table. Bank 8 is `$8000–$BFFF` when selected; the block fits
   with about 4 KiB to spare.
3. Move the team tables to bank 8/9: names 512 B, short names ~700 B, lineups
   288 B, flags 32 B, colours 64 B, ratings 128 B.
4. Patch the 29 `LDA #$04; JSR $C14E` sites. Only the ones that read roster or
   team tables become `LDA #$08`; the rest stay on bank 4 for its code/data.
5. Patch the 19 references to `$8400` to the new table address.
6. Rebuild the team-select screen, team list, bracket and password.

### Milestone 3 — tournament and presentation

- 5-round bracket (32 → 16 → 8 → 4 → 2 → 1), new bracket table and screen.
- Password encoding for 32 teams and 5 rounds.
- 16 new flag tiles from spare CHR space, plus colour entries.
- Team-select paging (8×4 with two pages, or a 6×5 grid plus overflow).

---

## Tooling setup

The tools currently hard-code 16 teams, 15 players, `$8400`, `0x120` and the
table addresses. Before building a variant, introduce a layout manifest that both
`tools/roster.py` and `web/rom.js` read:

```json
{
  "name": "32x20",
  "prg_banks": 16,
  "teams": 32,
  "players": 20,
  "roster_table": "0x8000",
  "roster_table_bank": 8,
  "team_stride": "0x170",
  "trailer_offset": "0x150",
  "lineups": "0x9000",
  "flags": "0x9120",
  "ratings": "0x9140",
  "names": "0x9200",
  "short_names": "0x9400"
}
```

Then:

- `roster.py show/extract/apply/patch` take `--layout layout.json`.
- `web/rom.js` loads the same JSON and renders N teams × M players.
- The editor gains a variant selector; export validates against the layout.
- A patch script per milestone turns the base ROM into the variant, so the
  transformation is reproducible instead of a hand-edited binary.

Suggested branches:

```
main                 stock 16x15 tooling
hack/16x20           in-place roster expansion
hack/32x20           expanded cartridge + new UI
```

## Test plan

There is no emulator installed on this machine yet. Before milestone 1, install
one with save states and a tile/RAM viewer (Mesen2 or FCEUX). Minimum checks:

1. Boot to title, start a game, pitch with each of the three pitcher slots.
2. Open the player-change screen and confirm all 20 names are reachable.
3. Pinch hit/run from the new bench slots.
4. Player card for a new slot shows the right name/skill.
5. Save/password round-trip.
6. 32-team build: team select, bracket, all five rounds, password.

---

## What I need from you

1. **Target roster size** — 18, 20 or 24 players per team? 20 is the sweet spot
   for a 4×5 menu grid and fits the free space comfortably.
2. **Target team count** — 24 or 32? 32 is cleaner for the bracket (five full
   rounds, no byes); 24 needs byes and a more awkward bracket.
3. **Tournament** — must single-player expand to the new team count, or are the
   extra teams exhibition-only?
4. **Hardware** — emulator/flash cart only, or does this need to run on a real
   MMC1 donor board? (PRG expansion to 256 KiB is fine on SxROM boards and flash
   carts; CHR cannot grow.)

My recommendation: **16 × 20 first**, then **32 × 20** on the expanded cartridge.
It gets a playable result quickly, proves the trailer and menu patches, and
leaves the bracket/password work for a focused second phase.
