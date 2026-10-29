Independent review found one blocking source-safety gap in the new emulator probe. I found no defect in the frozen scoreboard ROM's ownership, geometry, glyph semantics or tested CPU timing. Two optional cleanup findings follow. Final release acceptance also needs the root's separate mapper census and combined tournament gate results.

This was a read-only review of `/Users/dfm/GitHub/nesdav/little-league`. I used no subagents, emulator service, commits or repository writes. All new files are under `/tmp/ll-scoreart32-review`. The probe boundary experiment used an inert replacement module that only captured screenshot arguments. It contacted no service and wrote no screenshot.

**Blocking finding.**

- **P2. Protect the probe's screenshot destinations before dispatch.** [tools/probe_scoreart32.py:47](/Users/dfm/GitHub/nesdav/little-league/tools/probe_scoreart32.py:47) passes `out / f'{label}.png'` directly to the screenshot writer. The entry point at lines 80-84 only resolves and creates the output directory before invoking another screenshot-producing probe. It applies none of the source guards used by the builder and converter. With a valid played-board memory image, `check()` dispatches `played-half-1.png` when that path is a symlink or hard link to the supplied ROM. It also dispatches when the supplied ROM itself occupies that exact output path. The same missing guard permits aliases to art/data sources. The captured requests prove the missing preflight; I did not run the actual writer or claim that a protected file was corrupted. Source preservation currently depends on undocumented behavior in that writer. This is blocking for the task's explicit source-protection requirement, independently of the ROM's correctness. Preflight every planned screenshot path, including the inherited Exhibition screenshots, against the ROM and protected tools/art/data/docs before starting the emulator workflow. Cover direct, symlink, hard-link and missing-target aliases. Evidence is [boundary-evidence.json](/tmp/ll-scoreart32-review/boundary-evidence.json), with the exact experiment in [boundary_checks.py](/tmp/ll-scoreart32-review/boundary_checks.py).

**Optional findings.**

- **P3. Malformed layout font values escape the CLI error boundary.** [tools/scoreart32_convert.py:150](/Users/dfm/GitHub/nesdav/little-league/tools/scoreart32_convert.py:150) tests dictionary membership before establishing that `font` is a string. A layout entry with `"font": []` raises an uncaught `TypeError` and exits 1, instead of producing the existing `AssetError` diagnostic and exiting 2. I reproduced this through the real CLI in a scratch checkout and verified that it changed no files. Validate the value's type before membership. [malformed-font-stderr.txt](/tmp/ll-scoreart32-review/malformed-font-stderr.txt) records the traceback. This does not affect the committed, valid art.
- **P3. Remove the obsolete four-row claim.** [art/scoreart32/score32.px.js:9](/Users/dfm/GitHub/nesdav/little-league/art/scoreart32/score32.px.js:9) still says the writer moves up four rows. `ROW`, the ROM tables, the plan and the runtime all give one row for inning/line scores and three for statistics. This repeats the exact wording error identified by the design judge. Deleting that statement is sufficient. Changing this source comment requires refreshing the asset's source digest and the test's asset-file SHA, even though the generated graphics and ROM bytes should stay identical.

**Frozen inputs and reproducibility.**

The initial freeze was `2026-10-29T15:38:12.722850+00:00`. [source-hashes.json](/tmp/ll-scoreart32-review/source-hashes.json) records all 27 scoped files, including all art PNGs, both design documents, the six new tools and the three integration files. Copies are in `frozen/`; the tracked integration diff is [root-diff.patch](/tmp/ll-scoreart32-review/root-diff.patch). [dependency-hashes.json](/tmp/ll-scoreart32-review/dependency-hashes.json) additionally records the ROMs and tools used by execution. The final [source check](/tmp/ll-scoreart32-review/final-source-check.json) confirms every scoped file and recorded dependency retained its initial hash.

| Artifact | SHA-256 |
|---|---|
| modeart32 input, independently copied before building | `7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9` |
| Existing candidate and independent fresh build | `2ae1a7ab2f75aeea4287943ba8153ab0ee0cc188a3d9a67f64bf7398f9e3360a` |
| `data/scoreart32/scoreassets.json` | `38dc9cb1adca8d97543b69f491bd18c41ec397613217a4c0f17553ec3c91bfc0` |
| `art/scoreart32/score32.px.js` | `ce0e21acf123ad3c3bd6780742916729dac1442e4c882ad54737e2575c3f04eb` |
| `docs/scoreart32-plan.md` | `469327b3b02eed2b023d91d8256c178305d4e00cfb124a99a2fcf3d6233a5f08` |
| Design judge's `design-review.md` | `76ab08cc758b924c91abf7783ff305e7b0eef47a1716d4ec6c59f01fcea06f55` |

The renderer checkout was clean and its HEAD matched `PXL.json`, commit `3bc816cb15a14592e0dc062ee98013637d399457`. All eight asset source digests match their current source files. The full suite rendered all eleven PNGs twice with that checkout, reproduced the committed pixels and reproduced the converted asset bytes.

[commands.sh](/tmp/ll-scoreart32-review/commands.sh) records the successful commands and output paths. The main independent execution was:

```sh
cd /Users/dfm/GitHub/nesdav/little-league
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tools/build_scoreart32.py \
  /tmp/ll-scoreart32-review/modeart32.nes \
  -o /tmp/ll-scoreart32-review/rebuilt-scoreart32.nes --manifest \
  > /tmp/ll-scoreart32-review/build-manifest.json
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/ll-scoreart32-review \
  .venv/bin/python -u -B tools/test_scoreart32.py \
  /tmp/ll-scoreart32-review/modeart32.nes \
  --candidate /tmp/ll-scoreart32-review/rebuilt-scoreart32.nes \
  --pxl build/vendor/claude-pxl \
  > /tmp/ll-scoreart32-review/cpu-suite.txt 2>&1
```

The full suite independently passed in 232.9 seconds. [cpu-suite.txt](/tmp/ll-scoreart32-review/cpu-suite.txt) records 41 malformed asset cases, 30 malformed art/layout cases, 30 converter output targets, 55 builder output targets, regeneration aliases, 409 generated boards, nine shown samples, all 256 byte values, all 32 teams on both sides, RAM/WRAM comparison, 13 flows, 15 phase/song variants, 40 injected NMI positions and eight detected negative controls. This executes the actual newly built ROM bytes in the CPU model; it is not an additional real-core emulator run.

**Independent ROM and art checks.**

[Independent checks](/tmp/ll-scoreart32-review/independent_checks.py) use explicit design addresses, an independently written tile oracle and direct ROM/VRAM/OAM reads. They do not use `drawn()` or the builder's ownership registry for their comparisons. Results are in [independent-evidence.json](/tmp/ll-scoreart32-review/independent-evidence.json).

- Exactly 4,712 bytes change. All changes are within the declared bank-4 hook/row/code/palette/screen regions or CHR05. Every other PRG bank and CHR bank is byte-identical, including bank 14, fixed bank 15 and CHR18. The input's entire `$B780-$BF3F` range is `$FF`; each chosen code/palette/screen reservation is therefore free, and the `$B8A0-$B8FF` gap remains `$FF`. The suite separately proves that each of the 36 dependency/digest/reservation guards rejects drift.
- The direct row bytes are header `$2108`; line rows 9/11, with lower halves 10/12; statistic rows 15/17, with lower halves 16/18. The name Y operands are `47 57 77 87`, giving visible Y positions 72, 88, 120 and 136. Columns and name tile/attribute/X bytes remain stock. The lower scene starts at Y=160 and has 80 pixels.
- The asset defines 78 reserved glyph IDs and 176 art IDs. Only `$FE/$FF` remain unallocated, and all sixteen bytes of each tile are zero. The wholly blank patterns are `$5E/$E8/$FE/$FF`; `$5E` is an intentionally blank quarter of a reserved big glyph, not free art space. Every one of the 248 blank background cells uses `$E8`. All 214 writer/name background cells are blank in both bitplanes, and all 174 possible writer cells select background palette 0.
- Palette 0 uses navy `$0C` as value 0, sky `$21` as value 1, cream `$38` as value 2 and gold `$28` as value 3. The sprite font uses cream at sprite value 1. This preserves B's background glyph convention and the shared CHR18 name convention without mixing them. All palette backdrops agree. Narrow glyph ink occupies at most X=2..7, including shadow, and the header is separately encoded. Narrow cells have a blank margin, but repeated digits still have uniform eight-pixel pitch across neighboring totals.
- My six planted boards at halves 1, 14, 15, 28, 29 and 36 independently verify page transitions, stock tile meanings, modulo-100 values, literal E=0, big X and digit-plus-X markers. Their line, R/H/E and statistic fields match the stock ROM at the appropriate old/new coordinates. Name sprites move only by -8/-8/-24/-24 pixels. The full suite covers the remaining byte/team combinations.
- A separate executed instruction trace masks NMIs after the second wait returns and sums every executed instruction's cycle delta until `$B3D4`. Stock and candidate both take two waits and 41,436 cycles. The candidate's actual delay instructions account for 27,012 cycles; the rest accounts for 14,424. [candidate-cycle-trace.tsv](/tmp/ll-scoreart32-review/candidate-cycle-trace.tsv) retains that trace. The full suite additionally verifies this with a separate opcode-cost table, four vblank phases, frame/scene/APU comparisons and injected NMIs. These counts are specific to the frozen placement.

I rendered fresh boards from executed VRAM and the two separately mapped CHR banks, then inspected the 1x and enlarged images. [Half 29](/tmp/ll-scoreart32-review/independent-half-29-4x.png) shows the extra-inning header, name alignment, compact captions and full people scene. I also inspected the root's played-final screenshot and read the complete `docs/verification/scoreart32-ui.txt` log. That existing evidence reports all twelve played halves, five explicitly planted edge states, exact board/palette/CHR/OAM comparisons, a 3-0 Exhibition final and title return. I did not rerun or extend that service-based evidence.

**Output boundaries and integration.**

The builder and converter protect the actual input, renamed pinned ROM copies, custom `--assets`, previous stages, tools, art, data and docs. The full suite verifies direct, symlink, hard-link and missing generated-PNG collisions, including PNG installation preflight before any replacement. The atomic writer replaces the destination entry rather than writing through a linked inode. My eleven additional refusal cases cover symlinked parent directories, dangling links into art, missing targets through symlinked directories, a custom art directory reached through a symlink, external asset aliases and mutually hard-linked JSON/preview outputs. Every refusal preserved file content and metadata. The screenshot probe is the exception identified above.

The pipeline appends scoreart32 after modeart32. `verify.sh` checks conversion and the built ROM, and its full tournament soak selects scoreart32. Shell syntax and `git diff --check` pass. The mapper diff retains its old defaults and adds configurable CHR/PRG context targets, so the root can inspect CHR05/bank 4. Its report correctly describes the scene contexts as before/after samples for windows of up to forty frames.

The fixed-bank latent preset 1 at `$FB53` still contains `06 18 05 05 18 70`. The replaced descriptor is the only found literal scoreboard CHR05 load, and the new draw is the only new immediate CHR05 selector. This static evidence supports the chosen reuse but cannot prove that every computed selector avoids the latent preset. I did not poll, read or claim a result for the root's combined gate or mapper reports. Those separate acceptance items must supply their own completed evidence.

**Comment-sicko audit, report only.**

I read the installed audit specification and applied it directly, without delegation or edits. Files touched, actual deletions, restorations and audit reruns are all zero. The optional stale geometry statement at `score32.px.js:9` should be removed. It is a false comment, with no reason to reshape working geometry code around it. Twenty-four decorative section-banner lines are also deletion candidates, seventeen across the three Python asset/converter/test files and seven in the art source. These are optional style cleanup.

I kept the public CLI/schema/API contract documentation and non-obvious NES/stock-ROM constraints, including tile meanings, sprite Y conventions, palette bitplanes and the measured compensation interval. The six `noqa: E731` suppressions cover style-only lambda assignments and meet the audit's suppression exception. I found no correctness/safety suppressions, commented-out code, approval-demanding constraint comments or code workarounds requiring a `MUST KILL` rearchitecture flag. No additional encoding or approval is needed for this report.

**Limits of this verdict.**

The CPU model approximates PPU timing. Equal frame-stamped APU register writes are not a waveform comparison or cycle-exact hardware audio proof. The NMI sweep injects before each distinct new instruction, not every repetition of every loop. Physical hardware and a second emulator were not tested. The existing root UI log supplies real-core evidence, while this review's fresh execution is CPU-model evidence.

The accepted stock limits remain E=0, modulo-100 counters, compact statistic captions, uniform spacing between adjacent two-digit values and immediate championship routing back to the bracket. The championship flow has no held final scoreboard; neither the code nor this review claims otherwise. The source-safety finding affects probe tooling and leaves the tested output ROM hash unchanged.

Prove It Works led me to rebuild and execute the ROM and inspect its actual outputs. Boundary Discipline led me to test resolved/inode aliases and the screenshot sink, which exposed the blocking probe gap.
