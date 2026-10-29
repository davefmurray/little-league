Recommend **Candidate B, layout b, as the base**, with two bounded grafts below. Its complete people scene meets the brief better, and it preserves the stock score writer while supplying meaningful timeline evidence. Prefer bank-4 storage for integration. I independently built a scratch variant that keeps B's art, geometry, palette staging, both waits and cycle budget entirely in bank 4. The far-bank hop is unnecessary for this screen.

This is a read-only cross-judge review against clean main `877ddbc7d9e3e339f2e69ac101a15f6bd1a10ea6`. Both designs were read in full. Candidate files and repository files were unchanged at the end. No subagents, romdev, commits or repository edits were used. All new files are in `/tmp/ll-scoreart32-judge`. CPU model results below are not real-core acceptance.

Scores use the requested 0-5 rubric and assess the frozen candidates, before grafts.

| Criterion | A, recommended raw adapter | B, recommended layout b |
|---|---:|---:|
| Visual fit, readability and people | 3 | 4 |
| Score semantics, timing, input and audio | 2 | 4 |
| CHR, PRG and RAM ownership safety | 4 | 4 |
| Source simplicity and verifiability | 4 | 3 |
| Total | 13/20 | 15/20 |

A's palette, recognizable menu marquee and stock-sized captions fit well. Its borrowed people strip cuts figures at the bottom, and its adjacent two-digit counters remain crowded. B gives people complete poses, distinguishes the two crowd palettes and retains the sunny sky, navy, cream, gold and brick vocabulary. Its 3x5 stat captions are too small at 1x, and adjacent narrow values still merge visually. Those are bounded art problems. A's raw timing defect is a behavioral problem. B loses simplicity points for the redundant mapper hop and for repeating geometry in assembly data, converter, harness and art source.

I inspected A's CPU-rendered fixture, B's stock/A/B comparisons for the opening board, two-digit scores and 15th inning, and the menu reference. I also independently regenerated B's asset in memory, reproduced both recommended ROMs from their frozen builders, ran B's real draw to produce `B-independent-1x.png` and `B-independent-4x.png`, and inspected the new art probes. The frozen B asset reproduced byte for byte.

The layout is consistent, but B's repeated phrase **“up four rows” is wrong for the live fields**. These coordinates come from the ROM bytes and independently executed OAM, rather than accepting the design's geometry constants.

| Field | Stock and A | B | Actual displacement |
|---|---|---|---|
| Inning header | Row 9, col 8, `$2128` | Row 8, col 8, `$2108` | Up 1 tile |
| Upper line score and R/H/E | Rows 10-11 | Rows 9-10 | Up 1 tile |
| Lower line score and R/H/E | Rows 12-13 | Rows 11-12 | Up 1 tile |
| Stat captions | Row 17 | Row 14 | Up 3 tiles |
| Upper stats | Rows 18-19 | Rows 15-16 | Up 3 tiles |
| Lower stats | Rows 20-21 | Rows 17-18 | Up 3 tiles |
| Visible name Y positions | 80, 96, 144, 160 | 72, 88, 120, 136 | Up 8, 8, 24, 24 pixels |

Columns are unchanged. Names align with their associated value rows. R/H/E captions at Y=64 and stat captions at Y=114 match the respective header bands. B's bottom frame is row 19, and people/crowd begin at row 20. The 80-pixel art band is real. It results from a tighter composition, not a uniform four-tile translation. The one immediate operand and three tables claim 21 bytes and actually change 14. Update the description and keep these exact coordinates as the integration contract. Six independently executed boundary cases at halves 1, 14, 15, 28, 29 and 36 preserve header and value semantics with the expected moved name sprites. See `geometry.json`.

The timing disagreement favors B. A's 180 exit comparisons begin from planted exit states. They cannot detect a draw that reaches those states earlier. I reran A's 368 draw cases per implementation, all 256 number cases and all 180 exit cases. They pass, while the independent scene/audio timelines expose a regression in A's recommended raw adapter.

| Implementation | Vblank waits before writer | CPU cycles from second wait return to `$B3D4`, excluding NMIs | Writer reached in model frame |
|---|---:|---:|---:|
| Stock | 2 | 41,436 | 3 |
| A raw | 1 | No second wait; 14,890 from its sole wait | 1 |
| A packed fallback | 2 | 41,312 | 3 |
| B | 2 | 41,436 | 3 |

The four phase offsets 0, 997, 14,900 and 29,779 cycles preserve these results. A raw changes the frame-stamped APU stream in all four independently compared flows. In the A-button live case, sampled scenes go `$0A -> $02`; stock goes `$0A -> $0B -> $02`. This means no sampled scoreboard frame, not that the scene byte never briefly takes `$0B`. A packed passes those four 80-frame scene/audio comparisons, but changes bank 2 and fixed palettes and remains a weaker art base.

B's need for compensation is not merely an unexplained CPU-model magic constant. Disabling further NMIs immediately after the second wait still measures 41,436 cycles for stock and B. An independent opcode-cost sum, including taken branches, branch page crossings and indexed-read page crossings, also yields 41,436 for each. This calculation does not consult the model's instruction-cost table or its frame period. The raw copy path saves real 6502 work that the stock metatile decoder performed.

The precise number is specific to the code placement and continuation path. B's uncompensated path is 14,476 cycles, requiring 26,960 here. Removing that delay changes all four independent scene/audio comparisons. A seven-value sweep across two flows and two phases shows why matching one flow is inadequate. Delays of 12,000-24,000 match the sampled championship flow but fail live A. Delays of 30,000 and 36,000 match live A but fail championship. The calibrated 26,960 is the only sampled delay that passes all four combinations. This is evidence for preserving the stock budget, not a proof that exactly one integer delay can work.

B's wording that the writer starts on the identical absolute cycle also overstates the evidence. At the four phases its entry differs from stock by -2, +5, +5 and -2 cycles, due to the wait loop's polling phase. The measured interval from the second wait return is identical. Hardware NMI/status races, PPU behavior, DMA/APU effects and visibility still require the root's real-core checks. APU comparisons here mean equal `(frame, register, value)` writes, not equal audio waveforms or cycle timestamps.

I reran B's `--quick` suite successfully. This includes 46 random/edge boards, nine samples per internal layout, builder guards, RAM comparisons, all seven 600-frame flows per layout and 45 injected NMI instruction positions per layout. The independently written comparisons add four 80-frame flows against A raw, A packed, B, B without delay and the local-storage variant. B and the local variant also pass the live-A and championship comparisons under additional phase and initial-song combinations. Evidence is in `B-rerun.log`, `timelines.json`, `timing.json` and `delay-sweep.json`.

Static ownership supports both storage choices, with a shared CHR condition. Bank 4 `$B780-$BF3F` is exactly 1,984 `$FF` bytes. Prior stages occupy `$B700-$B77F` and the gameplay helper at `$BF40-$BF79`; the proposed local reservations avoid both. The name helper at `$9A00` and flag helper reservation at `$9B00-$9B3F` are also separate. Bank 14 is entirely `$FF` and has no found immediate selector in the input. B's mirrored pad and `$C14E` guard are sensible, and its NMI tests pass. They solve a mapper problem the local adapter does not need to introduce.

The latent CHR05 preset must remain explicit. The only literal stock `$C5C4` descriptor selecting CHR05 is bank 4 `$B3CD`. Fixed `$FB53` still contains preset 1, `06 18 05 05 18 70`, which writes `$05` to `$24` and `$25`. The six aligned literal callers use 7, 0, 2, 6, 4 and 8. Raw hits at bank 7 `$8FA5` and fixed `$CFA5` overlap the real `JSR $C14C; DEC $2D` sequence and are not setup calls. The independently inspected table-driven stores likewise do not establish an additional normal CHR05 consumer. For example, all 256 low nibbles at `2:$97C0` are in `{0,1,2,3,6}`, and `$D793` supplies `$04/$15`, where `$15` is page 21, not page 5.

These facts support conditional reuse, not a proof that preset 1 or every computed selector is unreachable. Both designs appropriately leave that final inference to the root's mapper census. Preserve the preset/table and guard its fixed-bank bytes. CHR18 is shared by other background descriptors and the scoreboard name font; both frozen candidates preserve all 4 KiB. No new persistent RAM is needed. B's game RAM comparisons pass, with `$06B4` differing only because the last name's Y moved. See `ownership.json` and the rerun logs.

The two coherent grafts are:

1. **Use A's bank-4 storage arrangement with B's draw contract.** Retain B's art, the 78 runtime tile meanings, row patches, palette bitplane convention, both waits and balanced inner `$2C` hold. Do not transplant A's raw loader unchanged. The tested local variant uses the 20-byte hook region, code at `$B800`, palette at `$B880` and screen at `$B900-$BCFF`. Its adapter is 78 bytes, fits the 128-byte code reservation and leaves bank 14 unchanged. Its copy path costs 14,424 cycles, so this exact variant needs 27,012 compensation cycles, not 26,960. It matches the stock 41,436-cycle interval, passes the independent timeline cases, all nine B sample boards, RAM comparison and 40 injected NMI positions. `B-local-feasibility.nes` is a review probe, not a release artifact. Recalibrate if implementation placement or instructions change.

2. **Make a single art readability pass without changing the writer.** B's narrow glyphs, including their shadow, occupy X=1..7 in an 8-pixel tile. Its usual header digits occupy X=1..6. Narrower ink and a restrained shadow give adjacent `16`, `18` and headers `15` through `18` more breathing room. `glyph-spacing-feasibility-*.png` demonstrate a five-column font within the existing tile IDs while leaving the nametable unchanged. These are feasibility drawings, not approved final glyph shapes. The same digit IDs serve both positions of every two-digit counter, so glyph changes alone cannot create a uniquely larger gap between R and H than between their digits. Keep R/H/E clearly aligned, preserve single-digit header 1's position, and judge the pairs together at 1x. The `larger-label-feasibility.png` probe replaces 3x5 stat captions with existing menu-style 6x7 ink. It fits the existing static band, uses 178 art tiles plus 78 reserved IDs and leaves zero free. Final source conversion must account for the full combined tile budget. Simplify decorative patterns if additional space is needed.

Implementation remains bounded by these constraints.

- Keep the stock numeric writer, inning window/header tables, X and nX markers, modulo-100 formatting, literal E=0, canonical team names, half-zero bypass, jingle and exit handlers. Move only the four specified geometry regions. Add no new wait to the championship results gate.
- Preserve CHR18 whole and keep B's palette contract. A's stock-glyph panel palette uses cream in value 1; B's redrawn background digits use cream in value 2. Combining those conventions would recolor the digits incorrectly.
- Guard the pinned input hash, exact hook and row bytes, new `$FF` reservations, fixed bank and shared-font dependencies. Reject changes outside the declared ownership regions. Use the repository's existing guarded builder, output-alias protections and source regeneration approach.
- Preserve both waits and assert the stock CPU interval after the final placement is known. Keep frame/scene/APU comparisons alongside that assertion. A cycle-count assertion by itself does not verify controller handling or an actually visible board.
- The root owns real-core CHR/PRG census, live and final-board VRAM/palette/CHR/OAM comparisons, input on both human ports, audio behavior, extra-inning pages, exhibition/title return, championship continuation, attract and the existing tournament gates. Neither candidate nor this review has completed those checks.

Prove It Works drove asset regeneration and inspection of independently executed VRAM/OAM. Explain the Number drove the opcode-cost calculation and delay sweep instead of accepting a frame-only calibration. Laziness Protocol drove the bank-4 graft, which removes the hop without re-owning baseball rules.

Exact successful test commands, including output paths and working directory, are recorded in `commands.sh`. `probe_review.py` contains every independent experiment and writes only into this review directory. It imports frozen helpers read-only with bytecode writing disabled. Source inspection also read the complete two designs, the candidate builders, tests, converter, art and ownership helpers, plus the repository CPU model and relevant prior-stage ownership declarations.

Key SHA-256 fingerprints are:

| Reviewed file | SHA-256 |
|---|---|
| Input `build/modeart32.nes` | `7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9` |
| A `design.md` | `d2d39835a0257bc38eede40081a8abbb21f797968a880af2c693c835c0123b75` |
| A `raw-prototype.nes` | `5e1f644ad75ede5fcba05cc45053d4a5009a271f8e5b073f2c98f59173999053` |
| A `compressed-prototype.nes` | `380dc4216f5678a3498cfddc166beeeb64bf7e22d5099f5b07c444662264e131` |
| B `design.md` | `9448342896baec0cf8275fa7606029b1fb6b9868c68ebb86fd12d9d42c187d6f` |
| B `rom/scoreart32-b.nes` | `62741c525dc51e20c6efd9c61b39c3eed81cb389be52554f016e7c311e475dc9` |
| Review local-storage probe | `ac60a71956fff8b1da488270c8f65a3ff47d67d0c4ea12b06889d25128018c63` |

`reviewed-inputs.json` and `reviewed-inputs.sha256` record 117 frozen input files, including all candidate files outside any preexisting bytecode cache and the primary repository references. The final `check` command confirms every one retained its initial hash. `additional-reviewed.sha256` records the extra prior-stage sources, four skill files, experiment script and command transcript. The repository remains clean at the reviewed commit.
