# 8bitcn Roster Lab acceptance

The patch is based on `ebb9b88`. It adapts upstream 8bitcn components at
`56066c038165223b8505a344309279ae27757a81` and adds two credited display assets.
`web/rom.js` is unchanged, SHA-256
`c43d0bb91e35193ac6aa1d4261a3caa662bba9ea6028dba2cef37688f8c78c02`.

## Automated behavior

With both actual ROMs supplied, the codec, app and color suites pass all
150 tests on Node 26.7.0 and Node 20.20.2. They cover unchanged ROM exports,
independent team-color exports, imports, baseline/reset behavior, asynchronous
load races, bundled-batter validation and precedence of the opened ROM.

```sh
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
node --test --test-timeout=60000 \
  tools/test_web_rom.mjs tools/test_web_app.mjs tools/test_web_colors.mjs
```

Both source ROM hashes are unchanged. The default batter regenerates from
Preview 8 and matches the original US ROM's decode. The footer PNG matches
the accepted home-run screen. The independent focused review found no
blocking defect and confirmed that loading the default art adds no recurring
render or fetch loop. Root removed redundant new comments and corrected the
art scale documentation.

## Rendered layout and interactions

The HTML renderer executed the production HTML, CSS and JS in Chromium.
Local JSON transport was replaced with embedded copies, and `100vh` was
replaced by `800px` to make the renderer's content-sized frame finite. No
production file contains those substitutions.

| Width | Document width | First player row y | Ratings height |
|---|---|---|---|
| 1280 px | 1280 px | 507.4 px | 60 px |
| 390 px | 390 px | 1009.2 px | 110 px |
| 320 px | 320 px | 1069.8 px | 110 px |

All three widths show 32 teams and the default game batter without a ROM.
At each width, DOM interactions pass team search, the mobile selector,
cap/jersey/hair recoloring, resetting colors to baseline, and opening and
closing More tools. Its dropdown stays within the viewport. The small
palette and roster scroll internally at 320 px. `docs/editor.png` is the
updated desktop render.

## Limits

This acceptance does not include native file-picker or download interactions
against the live server, forced-colors mode, hardware or the user's Chrome
installation. The previous Chrome freeze was not reproduced and its cause
remains unconfirmed. These checks do not establish that it is fixed.
