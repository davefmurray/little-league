# Roster Lab editor contract

Roster Lab (`web/`) edits two ROMs: the original 16-team US cartridge and the
32-team Preview 8 release. This page records what the editor opens, what it
can change, where it writes, how roster files and sessions behave, and how
the behavior is tested. `web/rom.js` implements the ROM and file rules;
`web/app.js` implements sessions and the page.

## Supported ROMs

The editor recognizes two roster layouts and, under them, three pinned ROM
variants. Anything else is refused before a session opens.

| Layout | File | Size | PRG / CHR | SHA-256 of the original |
|---|---|---|---|---|
| `preview8-32-v1` | `little-league-32-team.nes` from the [Preview 8 release](https://github.com/davefmurray/little-league/releases/tag/32-team-preview-8) (`build/homerunart32.nes`) | 393,232 | 16 / 16 | `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b` |
| `stock16-v1` | Little League Baseball: Championship Series (USA) | 262,160 | 8 / 16 | `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e` |

A file opens only when all of these hold:

1. The header is iNES 1.0 with mapper 1 (MMC1), no trainer and no NES 2.0
   bits, and its PRG and CHR bank counts match a layout.
2. The file length equals the size the header describes. Truncated files and
   files with extra bytes are refused.
3. For exactly one ROM variant of that layout, the SHA-256 of the file with
   every bit the variant may write cleared equals the variant's pinned value.
   Writable bits come from offsets pinned in `web/rom.js`, never from pointers
   inside the uploaded file.
4. Every writable field holds a legal value (see the next table).

| Variant | Layout | Writable byte positions | Masked digest |
|---|---|---|---|
| `preview8-legacy` | `preview8-32-v1` | 4,448 (33,664 bits): roster fields | `26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586` |
| `preview8-independent-colors-v1` | `preview8-32-v1` | 4,544 (34,240 bits): roster fields and the low six bits of `0x3F390-0x3F3EF` | `430000e74c40123c3b404b19858eed507154c3a9843e5963b5ca1ee405050ca7` |
| `stock16-native-colors-v1` | `stock16-v1` | 2,670 (20,304 bits): roster fields and the low six bits of `0x1FAD0-0x1FAFF` | `aa7a1e270e6300c6f0bc39be64d9180fe23cf9cb6ec70514d6d854209ccdb2d3` |

The original Preview 8 file is `preview8-legacy`; `preview8-independent-colors-v1`
is a copy with Roster Lab's own-colors upgrade (see [Team colors](#team-colors)).
Their pinned code differs, so no file matches both. The 16-team variant admits
every file the earlier roster-only digest (`6f4fbd41…`, 2,622 positions)
admitted, plus color edits. Masks are cached per variant, and the high two bits
of every color byte stay pinned to zero.

Step 3 lets a copy exported by the editor reopen. It also refuses any change
to code, graphics, pointers, terminators, pitcher trailers, lineups, unused
records, team identity, or the high nibble of the speed byte. A file whose
full SHA-256 equals the original is labeled the original ROM. Any other
admitted file, including every upgraded copy, is labeled an edited copy.
Neither label claims more than this byte-level match.

Hashing uses WebCrypto. A page without `crypto.subtle` (a plain-HTTP page that
is not localhost) refuses every ROM rather than skipping the check.

## Editable fields

Indices are 0-based. `attrs` is record bytes 6-15.

| Field | Record or table bytes | Values | `stock16-v1` | `preview8-32-v1` |
|---|---|---|---|---|
| Player name | bytes 0-5 | 0-6 of `A-Z`, `0-9`, space; stored space padded | players 1-15 | players 1-15 |
| Batting / pitching | byte 9 high / low nibble (`attrs[3]`) | 0-15 each | yes | yes |
| Speed | byte 10 low nibble (`attrs[4]`) | 0-15; high nibble kept | yes | yes |
| Skill | byte 11 (`attrs[5]`) | 0-4, shown as 1-5 | yes | yes |
| Team ratings | 4 bytes per team | 1-4 | bank 3 `$B224` | bank 3 `$BC80` |
| Team name | bank 1 `$9180 + 16t`, 14 bytes | as player names, up to 14 | yes | read-only |
| Scoreboard name | stock centered text, pinned widths 10-14 | up to the stored width | yes | read-only |
| Team colors | 3 bytes per team: cap and trim, jersey, hair | NES codes 0-63, kept exactly | fixed `$FAC0 + 3t` | fixed `$FAC0 + 3(t & 15)` as built, `$F380 + 3t` once upgraded |

Every other attribute byte is read-only. The editor keeps all ten `attrs`
bytes so JSON stays lossless, and refuses any input that changes a read-only
bit.

PARK, Korea's third player (team id 4, slot 2), stores skill 7 in both ROMs.
The game's skill lookup (`12345555` at bank 4 `$AEBE`) shows it as 5. The
editor accepts 7 only at that slot, keeps it until someone picks a skill, and
stores 0-4 for any skill picked in the editor. Clicking the shown star count
changes nothing.

JSON can preserve that 7 only when the loaded baseline already contains it.
After opening an edited ROM whose value is 0–4, an import cannot recreate 7.

The 16-team name fields edit the main team-name table and the scoreboard
names. Some screens keep separate copies, so a rename does not reach every
screen.

## Where Preview 8 keeps rosters

| Data | Preview 8 location | Editor |
|---|---|---|
| Teams 0-15, 15 players | bank 4 `$8420 + $120t` (file `0x10430`), same as the original | edit players 1-15 |
| Teams 16-31, 20 records | bank 8 `$8000 + $170t` (team 16 at file `0x21710`, team 31 at `0x22CA0`) | edit players 1-15; show 16-20 read-only |
| Team ratings, all 32 | bank 3 `$BC80 + 4t` (file `0xFC90`), read at `$AFE2` and `$BD46` | edit |
| Original rating table | bank 3 `$B224` | read-only; no reader in Preview 8 |
| Names, codes, regions | bank 1 `$9180`/`$BCC0`, bank 11 `$B000`, bank 10 `$AA00` and more copies | read-only |

The fixed-bank cache at `$FC4A` copies a high team's first 15 records and its
48-byte trailer into PRG-RAM. Records 16-20 are never loaded, so the editor
shows them as "stored, unused by this ROM". Team names, codes and regions
appear in several tables and in generated menu and bracket art, so Preview 8
identity stays as built.

## Team colors

Each team has three NES color codes: cap and trim, jersey and hair. The
game's palette routine at fixed `$C6FE` points eight live callers at a team's
record; [roster-format.md](roster-format.md#team-colors) lists the callers and
what each byte paints. On the field, the batting side (`$04ED`) supplies all
three bytes, including the hair slot `$3F1B`; the fielding side (`$04EE`)
supplies cap and jersey.

The 16-team ROM has one record per team at `$FAC0`, so color edits are written
in place. Preview 8's routine reads team `t & 15` from the same 16 records, so
teams 17-32 share the records of teams 1-16. Roster Lab gives every team its
own record with one fixed upgrade. It applies the upgrade to an exported copy
only when the copy's final colors differ from the colors the opened file had:

| File offset | CPU, fixed bank 15 | As built | Upgraded | Owner |
|---|---|---|---|---|
| `0x3C712` | `$C702` | `$0F` | `$1F` | `AND` team mask; pinned |
| `0x3C719` | `$C709` | `$C0` | `$80` | `ADC` table low byte; pinned |
| `0x3C71F` | `$C70F` | `$FA` | `$F3` | `LDA` table high byte; pinned |
| `0x3F390-0x3F3EF` | `$F380-$F3DF` | 96 × `$FF` | 32 records seeded from the file's own shared records | team colors; low six bits writable |

The routine keeps its 21 bytes, its 32 cycles, its exits and its control flow.
`B9 EF 04 29 1F 85 05 0A 65 05 69 80 85 04 A0 00 A9 F3 85 05 60` points at
`$F380 + 3 × (team & 31)` and returns `A = $F3`, `Y = 0` and X unchanged. The
old records at `$FAC0` stay pinned and are no longer read. The upgrade owns
`$F380-$F3DF`. The rest of the padding, `$F379-$F37F` and `$F3E0-$F3FF`, stays
free and pinned; the nearest simulation readers end at `$F378`. A later build
stage must not reuse the reserved range.

Export compares the final draft with the baseline the file opened with:

- No change: an exact copy of the opened file.
- Preview 8 as built, with only roster edits, or with colors changed and
  changed back: only the roster bytes. No upgrade.
- Preview 8 as built, with any final color difference: the 99 upgrade bytes,
  then the changed color slots and the roster bytes. The seeded copy must
  already admit as `preview8-independent-colors-v1` before any color is
  written. Roster edits already in the file are kept.
- An upgraded Preview 8 copy, or the 16-team ROM: only the changed color slots
  and roster bytes. Export never removes the upgrade or reseeds the table,
  even when every team matches its old partner again.

The copy is reopened through the normal admission path. It must read back as
the expected variant and as the draft, and every changed bit must be writable
in the opened file's variant or be one of the 99 upgrade bytes. Before
writing, the builder also checks the 21-byte routine, the `$FFF4` pointer,
that the 48 shared color bytes are NES codes, and that all 135 padding bytes
are `$FF`. On the reference files the
first change, team 20 to `$16/$30/$38`, gives SHA-256
`f861d9674507165d371676e431e05351b36045fedd5546fadd2fed8cb17521b2`. An upgraded
copy reopens as an edited copy labeled "Preview 8 · own team colors". Roster
Lab versions from before this change refuse upgraded copies.

Every code from 0 to 63 is accepted, stored and exported exactly, including
the black aliases (`$0E`, `$0F`, `$1D`, `$1E`, `$1F`, `$2E`, `$2F`, `$3E`,
`$3F`), both whites (`$20`, `$30`), the grays `$2D` and `$3D`, and below-black
`$0D`. Nothing is normalized or clamped. Anything else is refused with the
team, slot and value. Swatch colors come from the FCEUX palette in
`tools/menu32_convert.py` and are labeled approximate.

The panel has three rows, Cap & trim, Jersey and Hair, each with a swatch, the
code, its decimal value, a name and its own Reset. The basic picker is a radio
group of 53 swatches: `$x0-$xC` of the four brightness rows, then `$0F`. A
stored code outside that grid is added as the current choice. Arrow keys move
and choose, Home and End go to the row's ends, Enter keeps the choice, and
Escape restores the value the picker opened with and returns focus to the row.
A click chooses and closes. Advanced code accepts an exact decimal or `$HH`
code from 0 to 63; anything else shows an inline error and keeps the draft.
Choosing `$0D` shows an inline note about original hardware, never a dialog.
Each kept change is announced once in a polite live region.

With a ROM open, the preview draws the batter at the plate from that ROM: 26
8×8 sprites from CHR 4K bank 8, placed by numeric pose data in `web/colors.js`
and colored from the field sprite palette record at fixed `$F9D0`, with the
team's jersey and cap in sprite palette 0 entries 2 and 3 and its hair in
palette 2 entry 3. The repository holds no pixels, role maps or screenshots
for it. Without a ROM the preview is a simple drawing labeled "Illustration,
not game art". Both have `role="img"` and a label that names all three colors.

When an export from a Preview 8 file as built will add the upgrade, the panel
says "This export gives all 32 teams their own colors." Byte counts sit in a
details disclosure. Roster-only and unchanged exports show no note, nothing
asks for confirmation, and the export toast says when a copy gained its own
colors.

## Roster files

Export JSON writes version 3. Every stored record is included with all ten
attribute bytes, and every team with its colors:

```json
{
  "format": "little-league-roster",
  "version": 3,
  "profile": "preview8-32-v1",
  "palette": "nes-2c02-6bit-v1",
  "source": { "name": "little-league-32-team.nes", "sha256": "a66add03...", "variant": "preview8-legacy" },
  "teams": [
    { "id": 0, "name": "JAPAN", "code": "JPN", "region": "ASIA", "ratings": [1, 3, 2, 3],
      "uniform": { "cap": 5, "jersey": 32, "hair": 15 },
      "players": [{ "name": "UMEDA", "attrs": [2, 255, 0, 212, 201, 4, 0, 0, 2, 0] }] }
  ]
}
```

`profile` names the roster layout, not the ROM variant. `stock16-v1` teams
carry `name` and `short_name` instead of `code` and `region`. Teams 16-31
carry 20 players; all others carry 15. `source`, including `variant`, is
provenance only. Import ignores it, along with any width, activity or
permission field a file adds.

Import accepts:

- Version 3 for either layout. `palette` must be `"nes-2c02-6bit-v1"` and
  every team needs `uniform` with exactly `cap`, `jersey` and `hair`, whole
  numbers 0-63. Its colors replace the draft's. A Preview 8 file fits either
  Preview 8 variant; the open ROM decides whether an export upgrades.
- Version 2 for either layout.
- Version 1 files from the earlier editor, and unversioned `{rom, teams}`
  files: the bundled previews and `tools/roster.py` extracts. Sixteen teams
  map to `stock16-v1`, 32 to `preview8-32-v1`. On Preview 8 the earlier
  editor padded teams 0-15 to 20 players with blank records (empty name, ten
  zero bytes). Import drops exactly those records and says how many. Any
  other content in players 16-20 of those teams refuses the file.

Version 1 and 2 files have no colors. Importing one keeps the colors of the
roster being edited and says so when those differ from the baseline; a file
that starts a new session uses that session's baseline colors. A version 1 or
2 file that carries `uniform` or `palette` is refused with "Team colors need
roster version 3." An unversioned file may carry the `uniform` written by
the current `roster.py`, read like version 3. An old `roster.py` `colors`
object (`primary`, `secondary`) is ignored with a notice and never read as
colors.

Import refuses, and leaves the session untouched, when a file has an unknown
version, profile or palette, team colors that are not exactly `cap`, `jersey`
and `hair` with whole numbers 0-63, teams out of order, the wrong player count, a name with
other characters or more than its width, attributes that are not ten whole
numbers 0-255, ratings outside 1-4, a skill outside 0-4 except the source
value above, or any change to a read-only value. Values are never clamped. A
file that omits a text field keeps the open roster's value. A missing 16-team
scoreboard name is kept, never blanked. Empty scoreboard names in legacy files
also keep the baseline; version 2 retains explicit empty strings. Stored trailing spaces in names are
normalized after validation.

## Sessions

The page starts on the Preview 8 roster preview built from
`web/roster32.json` and `web/teams32.json`. The Data menu switches to the
16-team preview (`web/roster.json`). A preview can export JSON but not a ROM.
Preview teams wear the original ROMs' colors, from a 16-record table in
`web/rom.js` that the real-ROM tests check against both files.

A session holds a baseline: the ROM as read, or the bundled preview. The
draft is dirty while it differs from the baseline.

- Opening a ROM or switching previews starts a new session. If the draft has
  unsaved edits, the page asks Keep editing or Replace first, even when the
  incoming roster equals the draft.
- Importing JSON replaces only the draft. With a ROM open, the file must match
  the ROM's layout, and Revert and Reset team still return to the ROM. The
  opened file, its variant and the baseline never change. Re-importing the
  current draft asks nothing and keeps the dirty state.
- Dirty compares exact color codes. A color row's Reset returns that slot to
  the baseline; Reset team and Revert include colors. No two teams ever share
  a color object, so editing one team never changes its old partner.
- Importing JSON with no ROM open puts the draft on the matching preview.
  Opening a ROM afterwards starts from the ROM; import the file again to apply
  it.
- Every load or import takes a ticket. Only the newest ticket may change the
  session or show an error, so a slow read, hash or fetch cannot override a
  later choice. The Replace answer applies only to its own load; edits made
  while the prompt is open bring the prompt back.
- Export ROM writes only the fields that differ from the baseline, onto a copy
  of the opened file, then reopens the copy and checks it reads back as the
  draft before downloading it. Exports never mark the draft saved. Team colors
  follow the rules in [Team colors](#team-colors).

The hosted page never fetches a ROM. Get Preview 8 is an ordinary link to the
release asset, and Open ROM reads a local file in the browser. GitHub's
release downloads do not send CORS headers, so a direct browser fetch of the
asset would fail anyway.

## Tests

```sh
node --check web/rom.js && node --check web/app.js && node --check web/colors.js
node --test tools/test_web_rom.mjs tools/test_web_app.mjs tools/test_web_colors.mjs
python3 tools/test_roster.py
.venv/bin/python -B tools/test_colors32.py
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
  node --test tools/test_web_rom.mjs tools/test_web_colors.mjs
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
  .venv/bin/python -B tools/test_colors32.py
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
  python3 tools/test_roster.py
ROSTER_ROM32=build/homerunart32.nes .venv/bin/python -B tools/test_web32_runtime.py
```

- `tools/test_web_rom.mjs` checks admission, exact field writes for all active
  players and ratings, refusals, the skill exception and roster files. Its
  color cases cover the 99-byte upgrade, byte-identical no-op and roster-only
  exports, one-slot writes on every team, never downgrading, every code 0-63,
  immutable code, table and padding bits, version 3 and older files, and
  separate color objects per team. It runs on synthetic images built by
  `tools/web_fixtures.mjs` with test-only variant registries, and, when git
  history is present, opens ROMs written by the previous editor. Its real-ROM
  cases are reported as skipped unless both variables are set; CI has no ROM,
  so CI runs only the synthetic cases.
- `tools/test_web_colors.mjs` checks the swatch palette against
  `tools/menu32_convert.py`, the color names, the 53-swatch grid, the strict
  code parser and the batter decoder. With both ROMs it checks that each ROM
  renders the reviewed batter role map, by SHA-256; set
  `ROSTER_BATTER_JSON` to compare the reviewed file too.
- `tools/test_colors32.py` runs the palette routine of an export
  `tools/web_colors_export.mjs` makes through `web/rom.js`: always on a
  synthetic image, and with both ROMs over the full CPU matrix (call census,
  all eight consumers' destinations and bounded reads, the direct routine
  contract, parity with the original at every consumer exit, and the padding,
  RNG, simulation-reader and `$C1A4` bounds). It needs Node and py65.
- `tools/test_roster.py` runs the `roster.py` CLI on synthetic images and, with
  both ROMs, the real ones: `uniform` extract and apply, old two-color objects,
  32-team refusals and `show32` colors, output guards, and a CLI to Roster Lab
  round trip.
- `tools/test_web_app.mjs` runs `web/index.html` and `web/app.js` against the
  DOM stub in `tools/web_dom_stub.mjs`. It covers boot races, reads and hashes
  that finish out of order, failed loads, edits during a load, the replace
  prompt, imports, Reset team and Revert. The stub does not check layout,
  styling or real browser behavior.
- `tools/test_web32_runtime.py` exports a copy with every editable field
  changed through `web/rom.js` (`tools/web32_export.mjs`), then runs the py65
  roster cache, role and Power Analysis rating checks on it. It prints
  SKIPPED without the ROM.

The [browser acceptance record](verification/web32-browser.md) covers local
file handling, downloads and layout for the original editor integration.
The [team-color browser checks](verification/webcolors-browser.md) cover the
new picker, responsive layout, real ROM downloads and reopening. CPU-model
checks do not claim a gameplay emulator run. Deployment acceptance is
recorded separately when completed.

## Not covered

- `tools/roster32.py`, `tools/test_roster32.py` and the `bank8-32` notes in
  older docs describe the experimental 32x20 builds. They do not read
  Preview 8: its bank 8 area for teams 0-15 and all of bank 9 are erased. Use
  the web editor or `web/rom.js` for Preview 8.
- Renaming Preview 8 teams needs coordinated writes to every name copy, font
  flags and generated art. It is not supported.
- Other builds, including earlier previews, are refused even when their
  layout looks similar.
- `tools/roster.py` edits team colors only on the 16-team ROM. On 32-team
  files it refuses color writes and `show32` only displays the live colors.
- Color runtime evidence comes from the bounded CPU model. It does not
  include an emulator, hardware or full-tournament run. Real-browser editor
  checks are recorded separately from the stub-based page tests.
