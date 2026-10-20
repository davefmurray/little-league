# 32-team hack — current status

This is the user-facing snapshot of the 32-team Little League hack: what
works, what is still blocked, how to build it, and where the evidence lives.

| Area | Status |
| --- | --- |
| 32-team bracket state / champion 62 | working |
| Bracket visuals (codes, clear, header) | working |
| Selector / teams 16-31 data | working |
| Roster cache / web editor / CLI | working |
| Password model (hex/letter/tile/11-char) | working |
| Stock regression | green |
| High-team live field | blocked (card/order state machine) |
| Password screen font/wiring | blocked (11-char buffer, glyph bank) |
| In-game bench/attribute card | blocked (depends on live field) |
| Match-26 crash | open (invalid scene 1E/1F table entries) |
| Hardware / sound validation | not run (checklists written) |

## Working

- **32-team bracket state** in bank 11: 63-slot heap (`$7700-$773E`), live
  match index `$07FC`, real-score winner (`$048B/$048C`), five rounds,
  champion slot 62 (`$773E`).
- **Round labels / champion banner**: live `ROUND 1..5` / `CHAMPION` title
  from `$07FC`.
- **Bracket visuals**: real 32-team codes (`AUS`, `CUB`, ... `CZE`), a full
  nametable clear before the draw (no leftover box-score rows), and a clean
  header/title (`R32 R16 QF SF`, `ROUND 1 R32`).
- **Selector**: four pages, real teams on pages 3-4; page-3 screenshot in
  `docs/teams16-31-select.png`.
- **Teams 16-31 data**: real names/codes/regions, 20-player rosters, three
  pitcher records, 32-entry ratings (`$BC80`) and lineups (`$FD80`).
- **On-demand roster cache**: the two current teams are copied to
  `$7800/$7A00` and `$7F00` is repointed. The missing step was the MMC1
  reset before the bank-8 switch. Match 8 shows `HARRIS`/`GARCIA` with real
  ids 16/17.
- **Browser editor**: 32x20 JSON and ROM modes; team codes/regions; the
  stock 16-team path remains byte-identical.
- **CLI**: `roster.py show` (32-team), `roster32.py extract/apply`,
  `rominfo.py` layout detection.
- **Password model**: stock encode/decode located, stock round-trip exact,
  32-team model with 100 hex + 100 letter + 100 stock-tile round-trips.
- **CI**: password model, roster32 round-trip/edit/show32/rominfo,
  metadata sync, JS syntax, stock regression.

## Blocked / not finished

- **Order screen (scene `0F`) display-list flush**: on the current
  `build/direct31.nes` both the low- and high-team order screens stall in the
  flush's RLE loop (`PC=$C57E`) with a tiny `$32` (e.g. 6) and a garbage list
  at `$0300` (`ce cf ce cf ...`). That is a *shared* scene-`0F` regression,
  not a high-team-only card loop; the earlier "low team auto-confirms" was an
  older build. Needs a bisect over the bracket-clear/layout/data steps.
- **High-team input**: the player-change screen is reachable and renders
  (`T18` lineup, `PLAYER CHANGE > DIAZ`), but A/B/right do not change it —
  consistent with `$95`/`$C7` never being written.
- **Post-game bracket**: the team codes and box-score rows are fixed; the
  remaining garbled rows are score/round placeholders.
- **32-team password screen**: the model and a candidate stock tile
  alphabet exist, but the stock `$06B5` buffer is 11 characters and the
  glyph render was inconclusive (wrong CHR bank or tile base). The 11-char
  base-32 fallback and a visual mockup are in `docs/password-mockup.html`.
- **In-game bench/substitution and attribute semantics**: the data audit is
  green; the live-field UI is blocked by the card/order issue above.
- **Match-26 crash**: the stock post-game path beyond its 16-team design
  still needs a trace.
- **Hardware validation and sound checks**: not done in this environment.

## Build

Requires the base ROM (not distributed) at the repo root:

```sh
python3 tools/build_extra_rosters.py build/direct20.nes data/roster32.json \
  -o build/direct20-extra.nes
python3 tools/build_names32.py build/direct20-extra.nes \
  -o build/direct20-names.nes

python3 tools/build_32team_full.py
# direct20-names -> ratings32 -> lineups32 -> round labels -> top row
# -> bracket codes32 -> bracket clear -> bracket layout -> roster cache
# -> build/direct31.nes
```

`build/` is gitignored; the players and data live in `data/`.
`direct20.nes` itself is produced by the earlier direct chain documented in
`docs/AUTORUN-REPORT.md`.

## Evidence

- `docs/bracket-codes32.png` — real 32-team codes in the bracket.
- `docs/bracket-clear-post.png` — post-game bracket after the nametable clear.
- `docs/bracket-layout.png` — clean header/title and all 32 codes.
- `docs/teams16-31-select.png` — selector page 3 (Australia, Cuba, ...).
- `docs/AUTORUN-REPORT.md` — full probe log (the latest rounds cover the
  field card/order state machine, the password alphabet, and the bracket
  fixes).
- `TODO-NEXT.md` — the live, prioritized open list.

## Next probes

1. Capture the low-team **live field** per frame and compare `$047C`,
   `$0489`, `$0543`, `$0545` with the high-team card state.
2. Map the `$BA` order-menu states and the final match-start selection.
3. Find the password font's real CHR bank/tile base (use
   `tools/render_chr_tiles.py` at the live password screen).
4. Trace the match-26 `$1D`/`$00C3` crash.
