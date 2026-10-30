# analysisart32 production integration: independent review (Opus, read-only)

## Verdict

**Approve for integration.** I found no critical defect and no ROM, rating, name, flag, timing, input/return,
audio or championship problem. The production ROM `build/analysisart32.nes` is byte-identical to frozen
candidate B (`1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`) from the pinned input
(`a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55`). Every judge-required production fix is
present, and I exercised each one independently. One of them, accepting a normal temp output, regressed on macOS
with root's live ancestor fix (finding 2).

There are two warnings, both about output-path guards and neither touching the ROM:

1. Original-16 scope: the frozen converter accepted symbolic links in ancestors above `--out`. Sol found it, and
   root has already fixed it in the live tree.
2. Live scope: that fix now refuses every natural macOS temp path, and its message is misleading.

Everything else is a nit. My acceptance does not cover root's integrated gate or ancestor-guard rerun, which are
still in progress, or root's runtime logs.

## Scope: original-16 freeze vs live tree

| Set | Result |
|---|---|
| `review-freeze.json`, 16 files | All 16 matched at the start. At the end 14 match. The 2 that differ are exactly root's announced ancestor fix: `tools/analysisart32_convert.py` `507d1056…` → `9bc93c29bf7c680ca14568b8b74295ec7e46a82c3f623c7011a1372178cafdd8`, and `tools/test_analysisart32.py` `c6edc10c…` → `e1c6c30bcfdd0875ec4dca347d72c26e32b5019598ad6ace52e82a1934cfd39b`. |
| `driver-review-freeze.json`, 2 files | Match: `tools/soak_bracket.py` `d31d08a3…`, `tools/test_soak_lineup.py` `2337049f…`. |
| Design ledgers `sol-freeze.json` 167 + `opus-freeze.json` 147 | **All 314 design files unchanged** at every check (before, mid, after runs, final). |
| ROM | Root output = `build/analysisart32-design/opus-proto.nes` = `/tmp/ll-analysisart32-opus/build/analysis-board.nes` = handoff ROM = `1e524b53…`. |

I compared the live files with the handoff worktree versions. The only substantive change is three lines at the
top of `protect_outputs` (`for parent in out.parents: if parent.is_symlink(): raise …`), plus three test changes:
`Path(temporary).resolve()` for the scratch checkout, `(safe / "existing").mkdir()`, and two hostile cases ("missing" and
"existing" child beneath a linked ancestor). The other diff lines are the earlier comment-only removals (4 and 7
lines).

## Findings, most severe first

### 1. [warning, original-16 scope; fixed live] The converter accepted symbolic links above `--out`

- **Location:** frozen `tools/analysisart32_convert.py` `protect_outputs`. It checked `out` itself and the
  directories from `out` down to each target (`walk_down`), never `out.parents`.
- **Reproduction:** Root and Sol: `--out elsewhere/linked-out/new-output`, with `linked-out -> real-out`, was
  accepted and installed through the link. My reading of the frozen code agrees. I did not rerun the frozen
  version.
- **Impact:** A contract gap against the judged rule "symlinks in files or ancestors". The practical risk was low:
  the resolve-based guards (`refuse_aliases`, `refuse_inside`, `refuse_tracked`) still refused any resolved
  target inside a protected location. Finding 3 shows the equivalent builder case is refused.
- **Status:** Fixed in the live tree. My live suite run refuses both new cases ("missing beneath a linked
  ancestor", "existing beneath a linked ancestor") with every file unchanged.

### 2. [warning, low impact, live scope] The ancestor fix refuses every default macOS temp location

- **Location:** live `tools/analysisart32_convert.py:545-547`.
- **Reproduction** (live converter; nothing was created in any case):
  - `--out /tmp/ll-analysisart32-review-opus/conv-out-tmp` → exit 2, "output aliases protected location through
    the linked ancestor /tmp".
  - `--out $TMPDIR/conv-out-tmpdir` (with `TMPDIR` under `/tmp`) → exit 2, same message.
  - `--out /var/folders/conv-out-probe` → exit 2, "… /var". That is where the macOS default `TMPDIR` lives.
  - `--out /private/tmp/ll-analysisart32-review-opus/conv-out-real` → exit 0. It installed 8 outputs equal to the
    registry.
  - Builder, run from a scratch repository copy: `-o /tmp/…/via-tmp.nes` → exit 0, wrote `1e524b53…`.
- **Impact:** On darwin, `/tmp` and `/var` are system symbolic links. The judged requirement that "a new temp
  output is accepted" therefore no longer holds for natural temp paths. The suite itself had to resolve its
  checkout root to keep passing. The message claims a protected alias where there is none. The stage's two CLIs
  now accept different output paths: the probe was already strict, but the builder is lenient. The pipeline uses
  the default path under the resolved repository root, so the gate and the ROM are unaffected, and the refusal
  fails closed.
- **Suggestion:** Keep the rule, since it is the judged contract. Make the refusal actionable, for example
  "`--out` passes through the symbolic link /tmp; pass the real path /private/tmp/…". Then either apply the same
  rule in `build_analysisart32.main` or document why the single-file builder relies only on the resolve-based
  guards. The probe's own ancestor loop (`probe_analysisart32.py:46-48`) is now redundant with `protect_outputs`.

### 3. [nit, live scope] The resolve-based ancestor guard lost its converter coverage, and the builder has no such case

- **Location:** the `test_convert_cli` hostile case "--out under a link into tracked art"; `test_builder_cli`.
- **Evidence:** In my live run, that converter case is now refused by the new pre-check ("…through the linked
  ancestor <tmp>/…/elsewhere/link…"). A regression in the resolve handling of `refuse_inside` or
  `refuse_tracked` would no longer show there. The builder relies only on those guards, and
  `check_output_guards` covers linked files, not linked ancestors. I checked the builder in a scratch repository
  copy: `-o <link into art/analysisart32>/x.nes` is refused (exit 2, "protected repository path …; generated
  files belong under …/build"). The behavior is correct; only the regression test is missing.
- **Suggestion:** Add that builder case, one tuple in `test_builder_cli`.

### 4. [nit] Leave-state: the conclusion holds, but the suite reports a scan it does not run, and the doc misstates the mechanism

- **Location:** `tools/test_analysisart32.py:1132-1138`, whose report line says "literal and instruction-context
  scans found no other setter"; `docs/analysisart32.md:30`, "The split is disabled there".
- **Evidence:**
  - The suite checks only the nine preset records and the `$CE39` bytes; it runs no scan. My independent scan
    (see "Leave-state evaluation") agrees with the claim.
  - On the CPU model, after a visit the picker keeps `$047A = $06` (split bits set) in stock and card alike.
  - What keeps the card's `$26 = $06` dormant is threefold:
    - picker frames take the NMI's short path, with no CHR commit in 12 frames;
    - the mode-menu init clears `$047A` (bank 1 `$9414`) before the menu shows;
    - the card's own prologue clears it (`$AF60`) before preset 2.
- **Suggestion:** Reword the report line ("pinned by the input hash; audited separately"), or encode the scan;
  about 30 lines are needed, and my scanner is in this directory. Reword the doc to say: "`$047A` stays `$06` in
  the picker, as in stock; the picker's NMI takes the short path, and the mode menu and the card clear `$047A`
  before releasing `$2C`."

### 5. [nit] The doc omits the judge-requested note on the bias table beside the pad

- **Location:** `docs/analysisart32.md:37` (PRG3 `$BD20-$BD2F`, bank-switch pad).
- **Evidence:** The new bank-3 pad begins immediately after the 32-byte batting-bias table `$BD00-$BD1F`. That
  table is read by `ADC $BD00,Y` at `$BB90` (replicated in banks 0, 1, 3 and 5), where
  `Y = $04EF,X` is the live team id, so the reader is bounded to 0-31. The stage pins both by digest, but the
  doc doesn't say so, and the judge asked to "preserve and document".
- **Suggestion:** One sentence in the rendering contract or the region table.

### 6. [nit, efficiency] Output preflight re-resolves the whole protected set once per planned file

- **Location:** `analysisart32_convert.protect_outputs` → `build_analysisart32.protect_output` (line 425) for
  every target; the probe's `Outputs.path` for every write.
- **Evidence:** One `protect_output` call took 0.31 s: 1,479 protected paths, resolved through each earlier
  stage's chain. The probe guard test builds `Outputs` about 22 times over 66 planned names and took about
  4 min 18 s. Both numbers were measured while my suite ran alongside.
- **Suggestion:** Resolve the protected set once per batch and check every target against it.

### 7. [nit] The new driver test is not in any gate, and `leave_lineup`'s docstring predates the port loop

- **Location:** `tools/verify.sh`; `tools/soak_bracket.py:55-63`.
- **Evidence:** `test_soak_lineup.py` is offline (romdev patched) and passed for me in under a second.
  `verify.sh` never runs it, so a regression would surface only in a manual soak. The docstring still describes a
  single controller.
- **Suggestion:** Add `.venv/bin/python -B tools/test_soak_lineup.py` next to the probe guard test, and say
  "controller 1, then controller 2" in the docstring.

The driver change itself is correct:

- `port` is zero-based with default 0, matching the local model in `probe_menu_chr.py:90`.
- Every other caller passes `(button, frames)` positionally.
- Nothing monkeypatches `soak_bracket.press`.
- Input is sent only while `$047B == $0F`.
- Its worst case on a controller-1 editor is seven ignored controller-2 presses.

### 8. [nit] Vestigial parameters and fields

- `analysisart32_convert.placement_record(placement, part, rom, assets)` (line 371) never reads `assets`.
- `provenance(base, sources, manifest, …)` (line 424) never reads `manifest`.
- `analysisart32_assets.TitlePlacement.cells` and `.ink` (line 413) are computed and stored, but no consumer
  reads them.

### 9. [nit, structure] `test_analysisart32.py` is 1,773 lines; concrete split proposal

The file already has eight natural sections; its 7 triple-blank-line gaps mark where dividers were. No ROM or
behavior change is needed:

- `analysisart32_oracle.py`, about 350 lines: `planar`, `background`, `find_rings`, `balls_on`,
  `read_letters`, `words`, the `stock_*` helpers and the `judge_*` functions. Both `--verify-only` and the main
  suite import it.
- `test_analysisart32_boundaries.py`, about 430 lines: the layout, placement, asset and converter case tables.
- `test_analysisart32_cli.py`, about 350 lines: `checkout`, `snapshot`, and the convert, builder and test CLI
  matrices.
- `test_analysisart32.py`, about 250 lines: `Suite`, `Jobs`, `main`.

Two deletions cost no independence:

- `stock_meaning` re-implements `AnalysisRatings.from_rom`'s dot-product heuristic. Its independence comes only
  from the pinned `STAT_LABELS` and `CHART_DIRECTIONS` literals, so assert those literals and the expected order
  directly.
- `planar`, `prg` and `chr_bank` duplicate earlier-stage helpers (`menu32_convert.decode`,
  `build_draw32.read`/`locate`) that are not under test here.

### 10. [nit, structure] `analysisassets/1` copies and re-validates the layout geometry

- **Location:** `analysisart32_assets.AnalysisAssets` (line 522: `__post_init__`, `record`, `parse`).
- **Evidence:** `Layout.parse` validates these fields, the converter copies them into the asset, and the asset
  validates them again: stats, text, socket columns, ball, flag y, pacing, split/name/rail rows, title palette and
  split ids. The builder only loads an asset whose digest the registry pins, so the second validation of this
  geometry has no reachable input. The converted-output invariants in `__post_init__` are valuable and should
  stay: socket-tile placement, lettered cells, blank digit and name rows, split ids, undefined ids, title palette.
- **Suggestion** (only if the stage is touched again): carry the layout by its digest, which the asset already
  records as `layout_sha256`, and have the builder load `Layout` from `art/analysisart32/layout.json`. That
  deletes the copied fields, their parse code and roughly 10 of the 25 malformed-asset cases. The asset digest
  would change; the ROM would not.

### 11. [nit, test quality] Sampled NMI windows mostly land in the `$04E6` spin loops

- **Evidence:** Team 0 gets 130 injections at 40 distinct sites; team 31 gets 52 at 29 sites. The named sites
  carry the important boundaries: the pads, card entry, numerals, balls, and every switch at `$C150`, at each
  serial bit and at `$C165`. Of these, 49 and 12 fired with `$27` ahead of the physical bank, and 33 and 8 fired
  mid-serial. Coverage is adequate, but "sampled init instructions" overstates how diverse the samples are.
- **Suggestion** (optional): skip repeated spin-loop iterations when counting the init window.

### 12. [nit] The plan doc's Status section is stale

`docs/analysisart32-plan.md:48-52` still says "Independent comparison is next. No production ROM changes have been
made."

**No other substantive findings.**

## Judge-required fixes: independent challenge

| Requirement | Result | My evidence |
|---|---|---|
| Failed sections and known-bad CLI candidates exit nonzero | Met | Live suite "test CLI": `$26` left at `$18`, +8 px self-consistent tables and reversed rows each exit 1 in a subprocess; the card exits 0. `Suite.run` records every exception and `main` exits 1. No job path raises `SystemExit`. |
| Socket/ball oracle independent of the tables | Met | `find_rings` scans the decoded background at every pixel offset against the input ROM's `$61` outline. The +8 px variant (layout and tables agree) fails with "sit on no socket"; reversed rows fail. The converter refuses a layout-only shift and sockets drawn 8 px right. The probe pins x 128-176 and y 88-136 independently. ROM tables decode to X `80 90 A0 B0` and Y `57 67 77 87`. |
| Real title template; no tautology | Met | `TITLE_TEMPLATE` is a pinned literal. Stock-writer output must match at exactly one column, and the pinned render's rows 0-63 must decode to those CHR `$18` patterns. |
| 182 NMI injections with full state | Met | 182, comparing SP, physical/logical PRG, MMC1 shift and count, control, CHR, guards, screen and series (counts as in finding 11). |
| Ownership and source proofs | Met | Digests cover CHR06 `$00-$B9`, whole CHR18, CHR1B and CHR00. The mode union equals `$00-$B9` from the ROM and from the approved `modeassets.json`. Flag palettes are `[0,2,3]`. My own byte diff: 1,524 changed of 2,594 claimed, 0 outside; per region 18/5/2/16/123/1008/227/16/109; new tiles `$BA-$C3` and `$E0`; 59 free; pads identical (`48 A9 0D 20 4E C1 68 20 60 A4 A9 03 20 4E C1 60`); every other bank, the ratings and the bias table unchanged. |
| Split contract, marker, two `$04E6` waits | Met (CPU) | Sprite 0 `40 FE 20 F8` hits at (254,65) and (254,66). Row 8 uses only `$E0`/`$20`, identical in both banks. The `$CD8A` store and `$CC14` consumer are pinned, and drifting them is refused. `card()` disassembled from the ROM shows both waits and `$26 := $06`, and ends at `$A4EF`. The hit itself is manufactured by the CPU model. |
| Leave-state `$26` | Agree, no ROM change | See below. |
| CPU all-32 and earlier screens | Met | My live run: 32 visits, 12 timing fixtures, 9 mode exits, the pick flow, 13 scoreboard flows, and post-visit picker, mode and three menu paths. |
| Art generation by reference; build-only; deterministic; `--check`; `--record` | Met | `--check` wrote nothing. Registry: 28 unique pin labels (no silent dict collisions), sorted sources and outputs, path-free. The suite's `--record` round trip restores the registry byte for byte. |
| Whole-batch output guards | Met, with findings 1-3 | Live matrix: "29 hostile outputs and both linked registries" refused with every file unchanged. Builder: 40 protected targets. Probe: 23 refusals before dispatch. |
| Normal use accepted | Partly (finding 2) | The default path and resolved temp paths are accepted; natural macOS temp paths are refused. |

## Leave-state evaluation

These conclusions come from an independent literal audit of all 16 PRG banks of the pinned input (a linear sweep,
then each hit checked by hand in context) plus CPU-model runs:

- **Readers of `$26`:** Code reads `$26` only at fixed `$CE40`, where `LDA $26` follows `LDA $047A / AND #$02`.
  Bank 7 holds an identical copy at `$8E40`, but bank 7 is a dead copy of the old fixed bank (15,371 of 16,384
  bytes equal). The remaining hits are tile data.
- **Writes of `$047A`:** Only the preset routine `LDA $FB4D,X / STA $047A` at fixed `$C6FA` can set bit 1. Every
  other store writes 0, either `LDA #0`, `LDX #0`, or after `JSR $CA9F`, which returns A = 0. The one exception is
  fixed `$D00D`, which writes 4 (bit 2 only).
- **Preset records:** All nine have bit 1 set and all write `$25/$26`.
- **Callers of `$C6C1`:** Literal callers pass immediates 0, 2, 4, 6, 7 and 8, plus the card's own preset 2. No
  data table points at `$C6C1`.
- **Indexed stores near `$047A`:** they hit an 8-entry ring buffer at `$0470-$0477` (masked with `AND #$07`) and
  6-wide actor arrays ending by `$046F`; none can reach `$047A`.
- **Stock behavior:** Stock already leaves other scenes' values in `$26` while the split is idle: presets 0, 4,
  6, 7 and 8 write `$1C`, `$07`, `$12`, `$1A` and `$13`.
- **CPU-model runs,** comparing stock and card on the same script:
  - On exits with A and with B, no rendered frame after the press starts its top band on CHR1 `$06`. The picker
    blanks at +5 frames and returns on CHR1 `$19`.
  - In the picker after a return, `$047A` is `$06` in both ROMs and no CHR commit occurs in 12 frames.
  - On B to the mode menu, the init stores `$047A = 0` (bank 1 `$9414`) before the menu shows. Afterwards CHR is
    `($1B, $06)` in both ROMs and only `$26` differs.

Conclusion: I agree with root that no ROM change is needed for scratch parity. The residual risks are computed
paths, which a literal scan cannot rule out, and any future change that makes the picker run the full NMI path.
The second would mis-draw stock too (the vblank reload uses `$25 = $18` over the picker's `$19`), so it is not
specific to the card.

## Checks I ran

All runs used `.venv/bin/python -B` with `PYTHONDONTWRITEBYTECODE=1`, `TMPDIR` inside this directory, and
`ROMDEV_URL=http://127.0.0.1:9`, a dead port, so nothing could reach an emulator.

1. Freeze verification of all four ledgers: before, mid, after the runs, and final (`freeze-*.json`).
2. Hash identity of the four ROM copies and the input.
3. Independent byte diff and per-region counts (`rom_facts.py`).
4. Disassembly of the new hook, the state-1 jump, `numerals`, `balls` and `card()`, with their tables, from the ROM
   bytes (`dis_card.py`).
5. Live converter `--check` from the root tree: exit 0, nothing written. 11 tiles, 59 free, 1,524 bytes changed.
6. Live converter default run into a fresh `/private/tmp` scratch directory: exit 0. The 8 outputs equal the
   registry.
7. Live converter refusal reproductions under `/tmp`, `$TMPDIR` and `/var/folders`: exit 2 each, nothing created.
8. Builder in a scratch repository copy: a target under a link into `art` → exit 2; a target via `/tmp` → exit 0.
9. **The full live suite** (`--pxl build/vendor/claude-pxl --jobs 2`): **PASS, 23 sections, 649.7 s**, run against
   the live hashes above (`suite-full-live-jobs2.txt`).
10. `test_analysisart32_probe.py`: PASS, 23 refusals before dispatch (romdev patched).
11. `test_soak_lineup.py`: PASS.
12. The `$26`/`$047A`/`$C6C1` literal audit (`leave_state_audit.py`, `presets.py`, `ctx*.py`).
13. Three CPU-model probes: exit transitions (`exit_frames.py`), picker CHR commits after a return
    (`picker_maps.py`), and the picker-to-mode-menu `$047A` trace (`mode_after.py`).
14. Registry pin-label collision check.
15. AST audit for unused imports and parameters, plus a comment grep (`unused_audit.py`).
16. `protect_output` timing.
17. Before/final snapshots of the vendor checkout, `build/analysisart32`, `build/stockart32`, `art`, `data`, the
    design directory and the input ROM, including mtimes. My runs changed none of the 755 entries. The one new
    entry is described under Limits.

## Limits

- **Not run:** no emulator, romdev, hardware, PAL or second emulator. I did not rerun the frozen converter;
  finding 1 rests on code reading and root's reproduction.
- **Root's logs, not read or claimed:** `analysisart32-ui.txt`, `-mapper.json`, `-after-analysis.txt`,
  `-probe-guards.txt`, `-gate.txt` and `-ancestor-guard.txt`. Root reports the final runtime run and the
  post-analysis SPEED continuation completed; I did not verify them. The integrated gate and the ancestor-guard
  rerun are still in progress. The WATCH continuation was stopped by root, and I claim nothing about it.
- **CPU-model limits:** the sprite-0 hit is manufactured from beam position and OAM; PPU fetch, real MMC1 write
  timing and the analog picture are not modelled; audio is compared as APU register writes.
- **Literal audits** cannot prove computed paths or self-modifying code.
- **Out-of-scope observation:** the shared `build_bank11.assemble` raises `SystemExit` on an out-of-range branch,
  so such an overflow in this builder would exit 1 rather than the documented refusal code 2. It is unreachable
  with the fixed assembly.
- **Git:** At the very start I ran one `git diff --stat` and one `git status --short`; a plain status can refresh
  the index stat cache. After that I used only `git --no-optional-locks` reads. I made no git mutation.
- **New root file:** root created `build/analysisart32-design/acceptance.json` at 00:18:54 during my CPU-model
  probes. It is not one of the 314 ledgered files, no tool I ran references it, and I did not read it.
- **Scratch:** All my writes are under `/tmp/ll-analysisart32-review-opus`, including a copied scratch repository
  in `builder-check/` (copies, not hardlinks) and the converter outputs in `conv-out-real/`. The harness keeps its
  own background-task logs under `/private/tmp/claude-501/…`.

## Comment audit (report-only; no edits made)

Flagged:

- **Blank-line runs:** 24 runs of three or more blank lines remain where the dividers were removed: assets 5,
  convert 4, machine 5, build 3, test 7. No linter is configured, so this is cosmetic.
- **pxl dividers:** `art/analysisart32/card32.px.js` lines 23, 62 and 73 keep `// ----------` dividers.
  Removing them would change the tracked source digest and require `--record`; the render is unaffected. Low
  value.
- **Row range:** `card32.px.js:3-4` says the writer prints the name "on rows 2-5". It prints rows 3-5, and row 2
  is reserved blank (`analysisart32_assets.py:49`).
- **Docstring:** `soak_bracket.leave_lineup` still describes a single controller.
- **Unused code:** see finding 8. The pxl helpers are all used.
- **Narration:** none found in the Python tools.

Keep (these explain the stock or external contract):

- the `$04E6` latch and short-path explanations in `build_analysisart32`'s docstring and in `wait_nmi`;
- the notes on `FIRST_FREE`, `SPLIT_ROW`, `NAME_ROWS`, `CENTER`, `READER`, `FONT_FLAGS` and `FIRST_BALL_SLOT`;
- the CHR `$18` `$E9` rail pattern;
- "socket = CHR `$1B` ball outline";
- the reasons in `LEAVE_SCRATCH`;
- the `about` fields of `layout.json` and `placements.json`;
- the controller-2 reason at `soak_bracket.py:64`;
- the broad-`except` reason at `test_analysisart32.py:1584`;
- the quick-timing index comment, which I checked and is accurate.
