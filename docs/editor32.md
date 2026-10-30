# Roster Lab editor contract

Roster Lab (`web/`) edits two ROMs: the original 16-team US cartridge and the
32-team Preview 8 release. This page records what the editor opens, what it
can change, where it writes, how roster files and sessions behave, and how
the behavior is tested. `web/rom.js` implements the ROM and file rules;
`web/app.js` implements sessions and the page.

## Supported ROMs

The editor recognizes exactly two profiles. Anything else is refused before a
session opens.

| Profile | File | Size | PRG / CHR | SHA-256 of the original |
|---|---|---|---|---|
| `preview8-32-v1` | `little-league-32-team.nes` from the [Preview 8 release](https://github.com/davefmurray/little-league/releases/tag/32-team-preview-8) (`build/homerunart32.nes`) | 393,232 | 16 / 16 | `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b` |
| `stock16-v1` | Little League Baseball: Championship Series (USA) | 262,160 | 8 / 16 | `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e` |

A file opens only when all of these hold:

1. The header is iNES 1.0 with mapper 1 (MMC1), no trainer and no NES 2.0
   bits, and its PRG and CHR bank counts match a profile.
2. The file length equals the size the header describes. Truncated files and
   files with extra bytes are refused.
3. The SHA-256 of the file with every writable bit cleared equals the
   profile's pinned value. Writable bits come from offsets pinned in
   `web/rom.js`, never from pointers inside the uploaded file.
4. Every writable field holds a legal value (see the next table).

| Profile | Writable byte positions | Masked digest |
|---|---|---|
| `preview8-32-v1` | 4,448 (33,664 bits) | `26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586` |
| `stock16-v1` | 2,622 | `6f4fbd41e6a7235596aef7ce8c13877b1df96731a9a5e21ce4a04268ca176b2a` |

Step 3 lets a copy exported by the editor reopen. It also refuses any change
to code, graphics, pointers, terminators, pitcher trailers, lineups, unused
records, team identity, or the high nibble of the speed byte. A file whose
full SHA-256 equals the original is labeled the original ROM. Any other
admitted file is labeled an edited copy. Neither label claims more than this
byte-level match.

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

## Roster files

Export JSON writes version 2. Every stored record is included with all ten
attribute bytes:

```json
{
  "format": "little-league-roster",
  "version": 2,
  "profile": "preview8-32-v1",
  "source": { "name": "little-league-32-team.nes", "sha256": "a66add03..." },
  "teams": [
    { "id": 0, "name": "JAPAN", "code": "JPN", "region": "ASIA", "ratings": [1, 3, 2, 3],
      "players": [{ "name": "UMEDA", "attrs": [2, 255, 0, 212, 201, 4, 0, 0, 2, 0] }] }
  ]
}
```

`stock16-v1` teams carry `name` and `short_name` instead of `code` and
`region`. Teams 16-31 carry 20 players; all others carry 15. `source` is
provenance only. Import ignores it, along with any width, activity or
permission field a file adds.

Import accepts:

- Version 2 for either profile.
- Version 1 files from the earlier editor, and the bundled unversioned
  `{rom, teams}` files. Sixteen teams map to `stock16-v1`, 32 to
  `preview8-32-v1`. On Preview 8 the earlier editor padded teams 0-15 to 20
  players with blank records (empty name, ten zero bytes). Import drops
  exactly those records and says how many. Any other content in players
  16-20 of those teams refuses the file.

Import refuses, and leaves the session untouched, when a file has an unknown
version or profile, teams out of order, the wrong player count, a name with
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

A session holds a baseline: the ROM as read, or the bundled preview. The
draft is dirty while it differs from the baseline.

- Opening a ROM or switching previews starts a new session. If the draft has
  unsaved edits, the page asks Keep editing or Replace first, even when the
  incoming roster equals the draft.
- Importing JSON replaces only the draft. With a ROM open, the file must match
  the ROM's profile, and Revert and Reset team still return to the ROM.
  Re-importing the current draft asks nothing and keeps the dirty state.
- Importing JSON with no ROM open puts the draft on the matching preview.
  Opening a ROM afterwards starts from the ROM; import the file again to apply
  it.
- Every load or import takes a ticket. Only the newest ticket may change the
  session or show an error, so a slow read, hash or fetch cannot override a
  later choice. The Replace answer applies only to its own load; edits made
  while the prompt is open bring the prompt back.
- Export ROM writes only the fields that differ from the baseline, onto a copy
  of the opened file, then reopens the copy and checks it reads back as the
  draft before downloading it. Exports never mark the draft saved.

The hosted page never fetches a ROM. Get Preview 8 is an ordinary link to the
release asset, and Open ROM reads a local file in the browser. GitHub's
release downloads do not send CORS headers, so a direct browser fetch of the
asset would fail anyway.

## Tests

```sh
node --check web/rom.js && node --check web/app.js
node --test tools/test_web_rom.mjs tools/test_web_app.mjs
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
  node --test tools/test_web_rom.mjs
ROSTER_ROM32=build/homerunart32.nes .venv/bin/python -B tools/test_web32_runtime.py
```

- `tools/test_web_rom.mjs` checks admission, exact field writes for all active
  players and ratings, refusals, the skill exception and roster files. It runs
  on synthetic images built by `tools/web_fixtures.mjs` with test-only
  digests. Its real-ROM cases are reported as skipped unless both variables
  are set; CI has no ROM, so CI runs only the synthetic cases.
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
file handling, downloads and layout. CPU-model checks do not claim a gameplay
emulator run. Deployment acceptance is recorded separately when completed.

## Not covered

- `tools/roster32.py`, `tools/test_roster32.py` and the `bank8-32` notes in
  older docs describe the experimental 32x20 builds. They do not read
  Preview 8: its bank 8 area for teams 0-15 and all of bank 9 are erased. Use
  the web editor or `web/rom.js` for Preview 8.
- Renaming Preview 8 teams needs coordinated writes to every name copy, font
  flags and generated art. It is not supported.
- Other builds, including earlier previews, are refused even when their
  layout looks similar.
