# Roster Lab team workspace

The browser editor follows the approved team-workspace design (Comp A,
2026-10-31). This note covers the page's flow, layout and color state. It
replaces the page layout in [roster-lab-theme.md](roster-lab-theme.md). ROM
admission, export and roster files stay as described in
[editor32.md](editor32.md); this change does not touch `web/rom.js`.

## Flow

The page opens directly on the 32-team roster. A ROM is optional for editing
and JSON export; the game-character preview and ROM download use an opened ROM.
The former ROM-first entry screen is removed.

| Session | Page |
|---|---|
| Loading | The bundled Preview 8 roster loads automatically; no ROM is required to enter the editor. |
| Roster only (no ROM) | The file bar says "No ROM open" and offers Open ROM and Get Preview 8. The uniform preview says "Open a ROM to preview the game uniform". |
| ROM open | The file bar shows the file name, its status and **Change file**. **Download ROM** in the header saves an edited copy; the opened file never changes. |

**More tools** in the footer imports and exports roster JSON, reverts every
change, and opens the Preview 8 or 16-team roster without a ROM. Dropping a
`.nes` or `.json` file anywhere still opens it. Load tickets, the replace
prompt and the unsaved-changes prompt work as before.

## Layout

- A small navy header, a cream body and gold accents. The sky marquee, crowd
  screenshot and board frames are gone.
- Desktop: a 152 px team rail with search, the team title, one ratings strip
  with four 1–4 selects, the uniform row, then the 15 active players.
  Stored players that the game does not load stay read-only in a disclosure.
- Uniform row: the batter decoded from the open ROM at twice its size, three
  part buttons (Cap & trim, Jersey, Hair) and one shared palette of 52 hues
  plus `$0F`, with any stored code outside the grid. Colors apply as soon as
  they are chosen. Advanced code entry, the below-black note and the export
  note sit beside the palette.
- Roster numbers are small fields: 0–15 for Bat, Pitch and Speed, 1–5 for
  Skill. Arrow keys step them. A blank or out-of-range entry keeps the last
  good value and is restored when the field is left. Entering the shown
  skill keeps the stored byte, so PARK's source skill of 7 survives.
- 720 px and narrower: a team select replaces the rail. The palette scrolls
  inside its own box when it has less than 318 px.

Measured in the browser at 1280 × 800 with Preview 8 open, the ratings are
61.2 px high and the first player row starts at 517.8 px with the open-ROM
banner visible. At 390 and 320 px, the page fits the viewport and the mobile team
selector is visible. See the [acceptance record](verification/roster-workspace.md).

## Color state

`state.picker` is `{ team, part, opening, announced, extra }`: the part the
palette edits, its value when it was chosen or last kept, the last value
announced and a stored code outside the basic grid.

- Arrow keys, Home and End choose live. Enter or a click keeps the color.
- Escape puts back `opening` and returns focus to the part button.
- Choosing another part or team keeps the shown color and announces it once.
- Reset colors returns all three parts of the shown team to the baseline.

## Batter provenance

`BATTER` in `web/colors.js` lists 24 sprites. The measured frame also had
tiles `$FD` at (12, 15) and `$FF` at (12, 41). Those are field overlay
markers that drew a black cross under the bat, so the pose leaves them out.
Pixels still come only from the opened ROM. For both pinned ROMs the decode
equals the approved design's decode, pixel for pixel, with the same palette
record. `tools/test_web_colors.mjs` pins the role map's SHA-256 and compares
against that decode when `ROSTER_BATTER_JSON` points at it.
