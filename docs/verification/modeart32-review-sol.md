# modeart32 independent adversarial review

**Decision: REQUEST CHANGES.** One blocker in converter regeneration can overwrite a protected input through a nested PNG alias. No defect was reproduced in the frozen ROM's menu rendering, bank-switch contract, input exits, ownership or series preservation. Fixing the tooling issue should not change the frozen ROM or the selected B architecture.

## Intent and scope

Review the sunny, colorful ballpark menu with people, replacing presentation for main, Championship and Exhibition while retaining the stock choices, input, exits, series state and song `$06`. The selected B implementation owns the matching bank-1/bank-13 hop pads at `$9432`, bank 13 `$9000-$9FFF` and CHR `$06`.

Reviewed main `568ccd1339731613310492a70b9abdc0be35a6b0` with the uncommitted work. Read the five new modeart32 Python tools, the three integration diffs, all modeart32 art/data, `docs/modeart32.md`, the review hash ledger, the design/boundary/cross-judge grounding and implementation handoff/logs. Inspected the completed UI, assets, source-pipeline, title and password evidence. Applied the supplied interrogate rubric, code-quality lens and intent/findings structure directly. No delegation, repository edits, commits, pushes or romdev/emulator calls. All generated files are in this scratch directory. Scratch aliases to repository inputs were removed after guard checks.

## Findings

### 1. [critical, BLOCKER] Pinned pxl regeneration bypasses alias protection for its PNG outputs

**Location:** `tools/modeart32_convert.py:291` (`render_pxl`, `shutil.copyfile`); reachable from `main` at line 339. Missing test coverage: `test_converter_cli` at `tools/test_modeart32.py:287` never uses the regeneration `--pxl` branch.

**Finding:** `main` protects only `--out` and `--preview` at lines 330-333. With `--pxl` and without `--check`, it also writes every rendered PNG under `PNGS`. Those destinations never pass an alias check. `shutil.copyfile` follows an existing symlink and truncates a hardlinked inode. A nested generated PNG alias can therefore overwrite the actual input ROM, source, lock/layout or another protected data file despite the advertised input protection.

**Concrete reproduction:** `/tmp/ll-modeart32-review-sol/render_alias.py` copies the pinned title32 ROM into scratch, hardlinks `out/sprites/dad.png` to that copy, redirects only `converter.PNGS` to the scratch output directory, then invokes the real `main` with the pinned pxl renderer, `--rom <scratch>/title32.nes --out <scratch>/assets.json --pxl <repo>/build/vendor/claude-pxl`. Source code and the real repository input remain unchanged. The converter exits successfully and reports the correct asset hash, but the input ROM becomes the generated 265-byte dad PNG:

- Before: **393,232 bytes**, SHA256 `8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`.
- After: **265 bytes**, SHA256 `d05967d0cc34c8cca87a8c1be1f610c0645a6b2c3fb128bb6414fbba0c574c82`.
- Prefix after conversion: `89504e470d0a1a0a`; `samefile(input, nested_png)` remains true.
- Written asset JSON still hashes to `9af59518eb1d917f2705073d4351145fa73e0fd030db93f140aaaba36ad0a01f`.

This is the documented regeneration command in `docs/modeart32.md:25`, not an unreachable helper. `--check --pxl` renders to scratch and does not hit this destructive destination, which explains why the existing check-mode evidence passes. Existing explicit `--out`/`--preview` alias guards work; the gap is the additional renderer outputs.

**Fix:** After rendering into staging and before the first persistent copy, preflight *all* generated destinations against the actual `--rom`, tools, JS/layout/lock, data, protected earlier ROMs and other protected files/outputs. Permit replacing the intended PNG entry without permitting aliases to unrelated protected files. Install staged PNGs by replacement rather than truncating a linked inode. Add scratch-only hardlink and symlink tests for a nested sprite PNG aliasing the input ROM and a protected source/data file; rejection must occur before any persistent destination changes. Keep this protection at the output boundary rather than scattering guards inside image conversion.

**Frozen artifact impact:** None observed. The current frozen input/output hashes remain unchanged. This is a source-pipeline safety blocker, not a request to change the art or runtime architecture.

## Independent checks reproduced in this review

`independent.py` and `independent.log`, exit 0:

- Converted the committed PNG/layout in memory and rebuilt twice; JSON and ROM are byte-identical to the frozen artifacts. Independently computed file offsets and the seven ownership ranges rather than relying on the builder's manifest.
- Exactly **4,652 differing bytes**: 64 in the 66 allocated bank-1 bytes, 1,333 in bank 13, and 3,255 in CHR `$06`. No differences elsewhere. Bank 13 outside `$9000-$9FFF` stays `$FF`; the complete input bank 13 was `$FF`.
- The two 16-byte pads equal `48 A9 0D 20 4E C1 68 20 42 94 A9 01 20 4E C1 60`. The whole fixed bank, CHR `$00/$17/$19/$1B` and other banks remain unchanged.
- All eight tool/integration hashes in `build/modeart32-design/review-hashes.txt` match.
- **52** independent dependency/digest mutations at first/middle/last bytes are rejected by `change_manifest` before applying a ROM change. These supplement the supplied one-bit guard evidence.
- **32** direct, symlink, hardlink and parent-directory-symlink output-guard decisions pass, including `art/modeart32/out/sprites/dad.png`. The converter's permitted canonical asset aliases behave as intended. No protected contents were written during these guard tests.
- All **nine source/target overlays**, called through the actual hop and stock text walker with rendering and NMIs active, match an independent layout-based nametable oracle. Attributes, protected mode bytes, active series, stack, mapper serial count, return PRG/shadow and guards remain correct.
- **34 additional injected-NMI cases** exercise data-loop positions absent from the existing first-visit-per-instruction sweep: before/after selected uploads including bytes 255/256, 511/512, 767/768 and 1023, plus the first/last glyph of each of the three runs for all three text requests. All pass with the active high-team series intact and no modeled late VRAM writes. An in-memory removal of the short-NMI guard is detected by these checks. These are additional CPU-model cases, not exhaustive phase coverage.

`semantics.py` and `semantics.log`, exit 0:

- All **nine controller-driven menu/choice views** match a separate pixel oracle built from the original scene PNG, the stock CHR `$00` glyphs and stock CHR `$1B` ball. The oracle does not use `convert.compose`, `convert.frame` or the production renderer. All 32 palette bytes, four OAM entries and hidden remaining sprites match. The actual model uses 8x8 sprites with left-column rendering enabled. Per-frame RGB hashes are in `semantics.json`.
- Independently compared title32 and modeart32 Exhibition **1P/2P/WATCH**, teams **31/27**, with an active **team-31**, played-15 series, mask `$7FFFFFFF`, stale `$04E2=1` and seeds **0 / `$1234` / `$3FFF`** respectively. Second-player selection uses controller 2 in 2P. Scene `$11`, mode/ownership bytes, stale-flag clearing, both roster caches and the complete canonical series state agree with title32. This supplements the supplied team-9 active-series coverage.

`render_alias.py`, exit 0: reproduces Finding 1 using real pinned Node/pxl output and scratch-only persistent writes. Exact details are in `render-alias.log` and `render-alias/evidence.json`.

Also parsed all reviewed Python tools, ran `bash -n tools/verify.sh` and checked tracked integration diffs for whitespace errors. Did not rerun all earlier-stage suites or the full 314-second stage suite.

## Call-contract and quality assessment

The draw stub returns to the original `$944B` init tail; the text replacements return to their original state-machine continuations. Neither continuation consumes the replaced routines' register results before overwriting them. The stock mode handler, ownership table and cursor drawing routine remain outside the changed bytes. The input/song prefix and all fixed-bank audio/input/NMI code are identical to title32.

The real fixed-bank bytes establish the intended safety mechanism: `$C14E` sets shadow `$27`, guards its serial write with `$2D`; the normal NMI CHR writer and audio mapper work respect that guard. Audio maps bank 0 without replacing the foreground shadow and restores through `$C14C`. Raw text temporarily maps bank 4 through `$C713` and restores bank 13 through `$2E`; it does not stay in bank 13 throughout. The draw holds `$2C`, blanks through `$C260`, drops the stale display list, uploads the nametable and queues palette/CHR installation for the normal NMI. Source/disassembly and the additional loop injections support this contract within the model.

`ModeAssets` provides a useful single validation boundary: immutable bytes/tuples, exact lengths/keys, legal raw-run flags and nametable addresses, row limits, terminators and complete span coverage. The converter's layout validation and builder's font check complete the supported source pipeline. No malformed run reaching the stock unchecked buffer was found in the accepted frozen data.

One boundary observation is **not promoted to a finding**: a hand-edited serialized Championship list can exchange `LIST OF TEAMS` and `CONTINUE PLAY` while satisfying `ModeAssets`' exact-once label check. The standalone builder accepts it. The supported layout/converter freshness check and frozen output hash reject this change, and the asset format does not encode the layout's item-to-cursor association. Consequently the builder's label-count check alone should not be described as proving choice-to-label semantics. The current artifact passes the independent choice oracle.

No actionable broad structural simplification was found beyond making every renderer output use the same boundary protection. The new 1,175-line test file is a cohesive stage gate with functional sections, reusable stage harnesses and meaningful negative controls; splitting it on a line-count threshold would not resolve the blocker. No competing renderer, new fixed-bank trampoline or altered mode-state architecture is warranted.

## Report-only no-comments audit

Inventoried comments and docstrings in `comments.json`, inspected JS art comments and shell/integration comments. No suppressions, TODO workarounds, permission-only constraints or comment instructions substituting for missing runtime guards were found. ROM ABI/register comments describe external stock behavior; the run, cursor, font, palette and byte-reservation constraints are enforced by validation/guards/tests. The excluded stale bank-7 scan is contextual static evidence, not a general reachability proof.

No comment-only source edits are proposed. Deletions: 0. Restorations: 0. No delegated comment audit or implementation was run, per the review-only instruction. Finding 1 needs an executable output invariant and negative tests, not a warning comment. The generic `protected_paths` docstring at `build_modeart32.py:263` must not be treated as protection for renderer writes that never call it.

## Evidence limits and publication state

- The inherited implementation logs report their full CPU suite passing; that is supplied evidence, not a full-suite run performed by this reviewer. The independent additions above use the repository's approximate CPU/PPU harness.
- No hardware, romdev/core run or subjective audio listening was performed here. CPU render/PPU/NMI evidence is not physical-hardware certification.
- The completed actual-core UI probe checks nametables, mapped CHR and OAM; it does not directly assert the 32 hardware palette bytes. Palette assertions and the independent full-pixel composition above are CPU-model evidence. The stored screenshots are additional visual evidence.
- Mapper contexts are **before/after scene samples in windows of at most 40 frames**, not event-scene labels. The literal-pattern census in `test_builder` is not by itself a complete computed-selector reachability proof. The whole-input pin, unchanged surrounding program, supplied static investigation and root's bounded runtime tours are separate evidence.
- The completed controller password evidence uses the real keyboard EXIT key 39; keyboard B deletes. The CPU suite's synthetic password exit only tests redraw entry. These are different checks.
- The combined gate and full Exhibition logs were stated to be running. **They were not polled, and this review does not claim they passed.** Root owns those gates, final documentation and publication.

## Measured identities

| Artifact | SHA256 |
|---|---|
| title32 input | `8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c` |
| modeart32 frozen and independently rebuilt output | `7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9` |
| converted JSON | `9af59518eb1d917f2705073d4351145fa73e0fd030db93f140aaaba36ad0a01f` |
| source scene PNG | `37557f66f4caa5ce572b7ccdc35acc3c39ebea2b748afd6f9bd08541d80754cf` |

All 16 identities recorded in `evidence.json` were rechecked unchanged after the probes. It also records all seven region hashes, guard cases and alias decisions. `disassembly.txt` contains the actual stock mode/mapper/text/NMI/audio contracts inspected. All reproduction commands use the repository `.venv/bin/python -B`, with `TMPDIR=/tmp/ll-modeart32-review-sol`.

Report: `/tmp/ll-modeart32-review-sol/report.md`.
