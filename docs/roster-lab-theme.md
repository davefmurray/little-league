# Roster Lab ballpark theme

The browser editor uses the look of the Preview 8 mode menu: a sunny
ballpark, a navy sign on a gold-framed board, cream text and the game's
original crowd and characters. The theme changes only `web/index.html`,
`web/styles.css` and `web/assets/`. `web/app.js` and `web/rom.js` are
unchanged, and every element id and `data-*` attribute they use is kept.

## Layout decision

Two header shapes were compared by the editor space they leave.

| Shape | Header height before the editor (desktop) | Roster rows above the fold at 1280x800 |
|---|---|---|
| Old box-art and CRT hero | about 440 px (62 px bar + hero) | none |
| Scenic split header (copy beside the full 256x224 screen) | about 340 px, more when stacked on phones | none |
| Compact marquee (chosen) | about 220 px (148 px marquee + 70 px sticky board) | two to three |

The heights are layout arithmetic from the stylesheet, not browser
measurements. The compact marquee keeps the sign, sky, pennants, light
towers and the original characters, and gives the rest of the page to the
editor. On phones the screenshot frame narrows to the cheerleader and the
pair, so the marquee stays one row.

## Structure

- One palette in `:root`: navy `#183C5D`, sky `#3CBEFF`, cream `#FFE7A2`,
  gold `#F3BE3C`, brick `#DB2800` and green `#00AA00`, the menu's NES colors
  `$0C $21 $38 $28 $16 $1A`. Two helpers: a lifted cream for editable fields
  and white for text on brick.
- One `.board` frame used by the screenshot, team list, editor, Data menu
  and dialog: navy edge, 6 px gold band with cream bulbs every 16 px, and a
  navy inner line. One NES pixel is 2 CSS px.
- Navy boards carry menus and labels (sign, action board, team list,
  ratings card, table header). Cream boards carry the data the user edits.
- Each surface sets `--focus`: navy rings on cream and sky, cream rings on
  navy. Every text pair meets WCAG AA; the lowest is white on brick at
  4.87:1.
- The selected team and the hovered Data menu item show the sign's ball as
  a cursor. Team ratings fill every socket up to the value, like the Power
  Analysis card.

## Provenance

`web/assets/mode-menu.png` is an unedited copy of
`build/stockart32-mode-ui/p1-main-0.png`, SHA-256
`b07448fc48df00e36fb57bfd9e29bcd4538b90a06897fd67cebcc10e67e07c10`. It is
the emulator capture of the main mode menu from the accepted stockart32 ROM
(`a5bf74ee…`) in the [mode emulator tour](verification/stockart32-mode-ui.txt).
It matches rows 8-231 of the first panel of the recorded
`build/stockart32/mode-preview.png` with no differing pixels. Later stages
leave the mode menu alone: analysisart32 keeps CHR06 tiles `$00-$B9` and the
mode tables, and homerunart32 owns other regions. The page shows it as a
screenshot for identification and commentary under
[the distribution policy](rom-distribution.md), credited in the footer. CSS
frames and crops it; the file holds the full screen.

`web/assets/park/*.svg` are ornaments traced pixel for pixel from the
recorded scene render `build/stockart32/mode/out/scenes/mode.png` (SHA-256
`9cf72358…`, listed in `data/stockart32/digests.json`). That art is the
project's own pxl source, `art/stockart32/mode/mode32.px.js`. No traced
region contains ROM-derived crowd or character pixels.

| File | Source |
|---|---|
| `crest.svg` | Sign crest with ball and bats, x 114-141, y 9-22 |
| `pennants.svg` | Left pennant pair, x 44-61, y 16-43 |
| `tower.svg` | Light tower head, x 5-26, y 32-47; CSS draws the pole |
| `cloud.svg` | Left cloud, x 3-30, y 11-23 |
| `lawn.svg` | Lawn tile, x 0-15, y 224-239 |
| `ball.svg`, `star.svg` | The ball and star grids in `mode32.px.js`, checked against the render |

The old hero's `box-art.webp` and `title-screen.png` are removed.

## Checks

- `node --test tools/test_web_rom.mjs tools/test_web_app.mjs` with
  `ROSTER_ROM32` and `ROSTER_ROM16` set to the accepted ROMs.
- Static checks: ids, `data-*` attributes and the `.menu` and `#editor`
  containment that `app.js` relies on, CSS references, asset paths and the
  contrast pairs above.
- Root inspected real Chromium captures at 1280×800 and 390×844. The crest,
  sign, cropped scene and controls render correctly. Document width stays
  390 at phone width; the roster table scrolls inside its panel.
- Real browser upload and export passed. The unchanged Preview 8 download
  equals its input; changing team 32 player 15 to THEME changes only the
  independently expected six-byte name field. The replacement dialog fits
  the phone viewport, focuses Keep editing, and cancellation preserves edits.
- The integrated real-ROM Node run passes 70/70. app.js and rom.js are
  byte-identical to the previously accepted editor. These browser checks
  do not claim physical-phone or alternate-font testing.
