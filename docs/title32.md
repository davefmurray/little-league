# New title artwork

The title uses the same navy, white and gold palette as the new menus, with a
larger baseball wordmark, stadium, floodlights and baseballs. Its original song,
START handling, attract cutscene and demo remain. The final source build,
independent review and runtime gates are complete.

Editable source is `art/title32/title32.px.js`; text placements and palettes are
in `art/title32/layout.json`. The pinned pxl checkout is recorded in
`art/title32/PXL.json`. The converter enforces NES colors, 16×16 attribute-cell
palettes and the tile budget. The art uses 201 of 256 tiles in the title's
existing CHR bank $17, leaving 55 free. Menu CHR $19 is unchanged.

```sh
.venv/bin/python tools/title32_convert.py --rom build/pick32.nes --pxl build/vendor/claude-pxl --check
.venv/bin/python tools/build_title32.py build/pick32.nes -o build/title32.nes
.venv/bin/python tools/test_title32.py build/pick32.nes --candidate build/title32.nes
.venv/bin/python tools/probe_frontend32.py --rom build/title32.nes --output build/title-ui --tour title
```

This stage produces `build/title32.nes`, SHA-256
`8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`.
It changes 4,584 bytes from pick32. The guarded title hook at bank 0 $AC5A
serves both initial entry and attract redraw. Code and data occupy bank 0
$A980–$ABDF and $BD20–$BF5F; the builder also claims the intervening padding
inside its code reservation. The other edit is CHR $17. Fixed-bank code,
input and audio routines are unchanged.

The draw holds the stock short-NMI guard during its nametable upload, blanks
rendering, hides sprites, requests the palette through the stock buffer and
resets scroll and attract timers. CPU tests compare booted VRAM and palette
with generated assets, exercise START on both pads, compare unchanged attract
screens and verify the title redraw. Their timing model is not a cycle-exact
PPU. Real-core probes separately check CHR $17, audio activity, redraw, demo
entry and START during several attract phases.

The original attribution is retained. Physical hardware, a second emulator
implementation and battery-backed persistence remain outside acceptance.

## Acceptance

The [source pipeline](verification/frontend32-pipeline.txt) reproduces the final
hash. [CPU checks](verification/frontend32-title-cpu.txt) and
[pinned pxl regeneration](verification/frontend32-art.txt) pass after the
output-protection review fixes. The [combined gate](verification/frontend32-gate.txt)
passes the baseline six games and all 31 matches of a random tournament, with
entry stack `$FF` and game-over 1 for each final-ROM match. Its CPU section
predates the guard-only follow-up; the dedicated CPU logs cover those changes
against the identical ROM.

The [title controller tour](verification/frontend32-title.txt) checks both START
ports, audio activity and attract redraw. A separate [full attract tour](verification/frontend32-attract-chr.txt)
starts from a typed v2 password, completes Exhibition WATCH, idles through the
demo and returns to the title. CONTINUE then launches `$18/$0A` and exports the
same password. The first probe budget of 20,000 demo frames ended during live
play; a 240,000-frame bound allowed the unchanged stock demo to finish.

The [MMC1 report](verification/frontend32-chr.json) covers 90,022 scripted frames
and 9,885,056 mapper writes. No stock CHR writer started with a partial serial
sequence. CHR `$19` appears only in CHR1, three times at menu transitions;
CHR `$17` is used for the title. Startup before loadMedia returns is excluded.

```sh
.venv/bin/python tools/probe_menu_chr.py --report build/frontend-chr.json   tools/probe_frontend32.py --rom build/title32.nes --output build/frontend-attract   --tour exhibition --submode watch --complete --attract   --password 4995FEC5ESTVP6KM5YCNYM --session frontend-attract
```

The source pipeline now adds [modeart32](modeart32.md) after this frozen stage.
