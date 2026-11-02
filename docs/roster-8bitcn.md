# Roster Lab 8-bit rebuild

Roster Lab keeps the team workspace from [roster-workspace.md](roster-workspace.md):
the 32-team roster opens without a ROM, with a 152 px team rail, a ratings
strip, the uniform row with one shared palette, and the roster below. This
change restyles that page with 8bitcn's pixel components and real game art.
It also shows the game's batter before a ROM is open. Sessions, ROM admission
and export are unchanged, and `web/rom.js` is byte-identical.

## 8bitcn components

Source: [8bitcn/ui](https://github.com/theorcdev/8bitcn-ui) at commit
`56066c038165223b8505a344309279ae27757a81` (2026-10-26), MIT License,
copyright 2025 8bitcn. `web/8bit.css` holds the port, the commit, the source
files and the full license notice. The About section credits it on the page.

| 8bitcn component | Roster Lab class | Used for |
|---|---|---|
| `Button` | `.bit-btn` (`secondary`, `outline`, `destructive`) | Open ROM, Download ROM, Change file, More tools, Use code, Reset team, dialog buttons |
| `Card`, `Dialog` and `DropdownMenu` content | `.bit-frame` | Uniform card, roster table frame, More tools menu, loading card, dialog, toasts, drop card |
| `Input` | `.bit-input` | Team search, team name fields, exact code, roster name and number fields |
| `Select` trigger | `.bit-select` | Rating selects, the narrow-screen team select |
| `Badge` | `.bit-badge` (`secondary`, `destructive`) | File status, team code, active count, pitcher `P` |
| `Toggle` (outline) | `.bit-toggle` | Cap & trim, Jersey and Hair part buttons |
| `Progress` (retro) | `.bit-meter` | One four-square meter beside each rating select |
| `Table` | `.bit-table` | Roster and stored-player tables |
| `Alert` | `.bit-alert` | Status banner |
| `DropdownMenu` item | `.bit-menu-item` | More tools items |
| `Kbd` | `.bit-kbd` | Arrow keys, Enter and Escape in the palette hint |
| `Separator` | `.bit-sep` | Divider in More tools; the same dash pattern under the ratings and beside the rail |
| `retro.css` | `.retro`, `.pixelated` | Pixel labels; 1x art and the batter canvas |

The port keeps 8bitcn's geometry and drops its runtime:

- No React, Next, Tailwind or Radix. The decoration `<span>`s and border
  overlays become box-shadows and background layers on the native element.
  Native buttons, inputs, selects and the `<dialog>` keep their own keyboard
  and screen-reader behavior.
- Frames and buttons scale by `--bit`, 2-4 px here, where 8bitcn uses 6 px.
  The narrower frames keep the roster rows compact.
- `retro.css` loads Press Start 2P from Google Fonts. The port loads no font:
  `.retro` uses local monospace fonts, and data text stays in Arial.
- Hover colors are fixed theme tokens (8bitcn uses `primary/90` and
  `secondary/80`). No filters, no infinite animations and no canvas loops.
  The batter canvas redraws only when a color, team or file changes.
- In forced-colors mode, frames become system-color borders and the select
  shows its native arrow.

## Game art

The screen crops are shown at 1× and the batter at 2×, with
`image-rendering: pixelated`. The screenshot files are copied unchanged.

| File | Source | Shown |
|---|---|---|
| `web/assets/mode-menu.png` (already in the repo) | Emulator capture of the Preview 8 mode menu, SHA-256 `b07448fc…`; see [roster-lab-theme.md](roster-lab-theme.md#provenance) | Header: rows 0-35 (sky, flags, light towers, the LITTLE ★ LEAGUE BASEBALL sign). At 720 px and narrower, columns 64-191, the sign alone |
| `web/assets/game/homerun-a.png` | Byte-for-byte copy of `build/homerunart32/render/scenes/homerun_a.png`, SHA-256 `4a41f7be3d1e4edb832870d0b69cf7e807958922df92003da9fcf1dd2c37acea`, recorded in `data/homerunart32/digests.json` | Footer: rows 157-239 (the pair at the counter, the cheerleader, the running batter). A 1 px navy rule continues row 156, and rows 224-239 repeat as the lawn band |
| `web/assets/game/batter.json` | Decoded from the Preview 8 ROM, below | Uniform preview before a ROM is open |

The mode menu and home-run scene are Preview 8 screens with the original
game's characters and crowd. Their credit is in the page's About section and in
the README's Legal section.

## Batter before a ROM is open

`web/assets/game/batter.json` (3,745 bytes) holds what `batterPicture()` in
`web/colors.js` decodes from the pinned Preview 8 ROM: the 49 × 58 batter as
one hex palette entry per pixel ('.' is clear), and the 16-byte field sprite
palette record. It holds no CHR tiles and no code. Build it with:

```sh
node tools/build_batter_asset.mjs build/homerunart32.nes > web/assets/game/batter.json
```

The builder refuses any file whose SHA-256 is not
`a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`. The 16-team
US ROM (`58e038f1…`) decodes to the same pixels and palette record.

`readBatterAsset()` returns the same `{width, height, pixels, palette}` shape
as `batterPicture()`, so one draw function serves both. In `web/app.js`:

- With a ROM open, the preview draws that ROM's own decode, captioned "From
  your ROM".
- Without one, it draws the bundled picture, captioned "Game sprite". Cap and
  trim, jersey and hair recolor live, as with a ROM.
- The file is optional. While it loads, or if it is missing or malformed, the
  preview shows "Open a ROM to preview the game uniform" and editing works.
  No error banner appears.
- The picture is chosen at each draw from the current session. A file that
  arrives after a ROM opens never covers the ROM's batter.

## Layout budget

Measured in Chromium through the HTML renderer, using the production HTML,
CSS and JavaScript with local JSON responses embedded. The renderer substitutes
800 px for viewport-height sizing; it does not test the live server or uploads.

At 1280 px width, the first player row starts at **507.4 px** and the ratings
strip is **60 px** high. At 390 and 320 px, document width equals viewport
width. The roster and palette scroll inside their frames when needed.
The rendered page also passed team search, the mobile team selector, all
three color edits, color reset, and opening/closing More tools within the
viewport. See [verification/roster-8bitcn.md](verification/roster-8bitcn.md).

## Tests

```sh
node --test --test-timeout=60000 tools/test_web_rom.mjs tools/test_web_app.mjs tools/test_web_colors.mjs
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
  node --test --test-timeout=60000 tools/test_web_rom.mjs tools/test_web_app.mjs tools/test_web_colors.mjs
```

- Without ROMs, `tools/test_web_colors.mjs` checks the bundled batter against
  the approved role-map SHA-256 and the field palette entries, checks that
  each team slot recolors exactly its own pixels, and checks the reader's
  refusals.
- With both ROMs, it checks that the bundled batter equals each ROM's decode
  pixel for pixel, recolors identically for 64 uniforms, and that the builder
  reproduces the committed file byte for byte.
- `tools/test_web_app.mjs` covers startup (a loading card, no ROM gate, focus
  on the team title), the live bundled batter, a missing or malformed batter
  file, late arrival before and after a ROM opens, the ROM's own batter, the
  rating meters, and the art (two images, byte-identical to their recorded
  sources, at 1x, decorative).

## Not covered

- The renderer checks cover Chromium layout and DOM interactions, not a live
  file-picker/upload/download tour, forced-colors mode, or the user’s Chrome
  installation. The cause of the earlier Chrome freeze remains unconfirmed.
- The score screen art is not used. Its line score has no place in a roster
  editor that would not add noise.
