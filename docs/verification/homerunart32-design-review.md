# HOME RUN cross-judge: A (Sol marquee) vs B (Opus flipbook)

> **Update during review.** At 12:10 root recorded in `docs/homerunart32-plan.md` that the user selected B and asked that the pair and batter hold still. Root's corrected candidate is `build/homerunart32-design/still-players/candidate.nes`, SHA-256 `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`. I ran my static, parity and visual checks on it as well (section "Root's corrected candidate" below). It keeps every safety property of B. Everything below about B also applies to it, except where noted.

**Verdict: build production on B (now root's still-players correction).** B matches the accepted ballpark screens. It reuses the approved original characters pixel-for-pixel, changes no executable byte, and matched stock frame-for-frame and cycle-for-cycle in every case I ran. A is correct at runtime, but its picture does not match the accepted family. Its "steady" HOME RUN title flashes pink in four letters every 8 frames, and its crowd recolor splits faces into cream and pink halves at attribute boundaries.

All evidence below is mine, produced in `/tmp/ll-homerunart32-judge` from my own natural CPU-model games, my own renderer and my own static scans. It is CPU-model evidence, not hardware evidence. Root owns the real-core gates listed at the end.

## Scores

| Criterion | A | B |
|---|---:|---:|
| 1. Visual coherence with accepted screens; readable motion at native resolution | 2 | 5 |
| 2. Character and source-pixel fidelity | 3 | 5 |
| 3. Scoring, audio, animation and return correctness | 4 | 5 |
| 4. Ownership, shared-reader safety and simplicity | 3 | 4 |
| 5. Reproducible stages and tests | 3 | 4 |
| **Total** | **15** | **23** |

Why, in one line each:

1. **A** is a navy-and-cream poster around the stock face crowd: no stands, concourse, light towers or intro cast. At native size the recolored crowd reads as speckle, and the "chasing lights" are 8×8 gold notches under the rail. **B** has the same composition as the accepted menu, scoreboard and analysis card: sky, clouds, towers and pennants, a navy/gold marquee, stands, cream concourse and the original cast. The title is readable in both poses, and the whole picture moves at the stock 8-frame cadence.
2. **A** keeps every CHR byte, but its palette makes the same skin ink render cream or pink depending on the 16×16 cell. It also turns letter strokes pink beside the pom-poms. **B** reproduces pair, cheer, batter and crowd with 0 mismatched pixels in ROM. The new `cheer-b` mask follows the approved `cheer` rules exactly (details below).
3. Both match stock on every measured game outcome. A gets 4, not 5, because its parity depends on a calibrated 26,229-cycle busy-wait, two fixed-bank hooks, a bank bridge and an NMI display-list write. Each of these is correct now but must be re-gated after any edit. B has no new runtime mechanism.
4. **A** writes only into padding and two hook sites, but it adds code in three banks. Its fixed-bank bridge sits right after simulation tables whose readers stay in bounds only because three other tables are pinned, and A pinned one of those three readers. **B** is data-only and simplest. It loses a point because it replaces all of CHR `$15`, which has one other, statically unreachable, reader (split preset 6).
5. Both rebuild byte-identically. **A**'s key visual claim passed a test that could not fail for it (the lettering oracle crops only the letter H). All of A's event fixtures are injected scenes, not played games. **B** tests from played states and has honest exit codes. Its gaps are an all-32 scoring matrix, HUD-expiry forms, a vblank-phase sweep and an attract-mode case.

## Immutable inputs

| Item | SHA-256 |
|---|---|
| Parent checkout | `4ed637d4a55ee02ef650de179f0fc7e41bebf0f9` (`git status`: only `?? docs/homerunart32-plan.md`, before and after) |
| Input `build/analysisart32.nes` | `1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e` |
| A `prototype-A.nes` (= `build/homerunart32-design/sol-proto.nes`) | `7104a50c01c17a51696ce21c651a964614019a7ff00c69f3e7695406559e638d` |
| B `proto/flip/homerun-flip.nes` (= `build/homerunart32-design/opus-proto.nes`) | `1beb37e6ad414b1bebb7964215993bd741ce3b4bac4462ff09a4f66f5b02ff4b` |
| `build/homerunart32-design/sol-freeze.json` (349 files) | `0de8ab690f6ee25d24371cb63662c7c2950b179442c3c5ab4b4069d61cf6511b` |
| `build/homerunart32-design/opus-freeze.json` (130 files) | `db43cfe77c2110b3d167050a84116fdb1eca2acdda99dbb481a9fb20a46e94fe` |
| `docs/homerunart32-plan.md` (untracked), at start of review | `80fb6f8f5daf31c589de0713683022d033eeea627b278e1c9a01dc827da12550` |
| same file at end (changed externally at 12:10: user selection and still-players note; I only read it) | `ec93d3bc2660540417cbb76f8b185691907f2eebbfcd624189a9a5117f7cea36` |
| Root's corrected candidate `still-players/candidate.nes` (= `still-players/homerun-flip.nes`) | `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b` |

Freeze ledgers were verified before and after this review: 0 missing, 0 changed in both (`out/freeze-before.json`, `out/freeze-after.json`). The Opus directory holds 6 unfrozen `__pycache__/*.pyc` files dated 10:44–11:32, which is before the 11:44 freeze. I created none, because every Python run used `-B`. I ran no writer inside either lane directory. B's converter ran on a copy of its art in my scratch, and A's builder ran in memory without its `main()`.

I did not use `build/homerunart32-design/sol-runtime/`, as instructed. It already held files when I listed the parent directory, and I did not open them or rely on them.

## Byte ownership, verified against each ledger

My own diff of each candidate against the input (`tools/romdiff.py`):

- **A**: 1,250 changed bytes in 9 regions, which matches `ledger-A.json`. The regions are fixed `$D768–$D76D` (JSR target + 4 NOPs) and `$D78D–$D78F` (`JMP $B900`), fixed `$F379–$F386` (bridge), bank 13 `$A500–$A548` (loader), `$A600–$A9FF` (nametable) and `$AA00–$AA1F` (palette), and bank 6 `$B900–$B92E` (helper), `$B980–$B99B` and `$B9C0–$B9DB` (light lists). All CHR is identical.
- **B**: 8,265 changed bytes inside 8,976 owned bytes, which matches `ledger/ledger.json`. They are CHR `$04` and `$15` (two × 4,096), bank 1 planes for ids `$01–$74` in all four planes (464), bank 1 `$8DF0–$8F1F` (map `$24` + attributes, 304) and fixed `$F8C0–$F8CF` (palette record `$0E`, 16). There is no executable change.

Earlier stages use CHR `$00/$05/$06/$17/$18/$19/$1B`, banks 0/1(`$942A–$95F6`)/3/4/10/11/13(`$8000–$A4FF`, `$BD20`). Neither candidate overlaps them. analysisart32 pins bank 13 `$A500–$BD1F` as untouched padding in its own input, so A's bank-13 use does not disturb earlier-stage reproducibility.

## Runtime parity from natural games (my states, no lane pickles)

I booted the stock ROM from RESET on the repo CPU model and drove WATCH Exhibitions with controller input (`tools/natural_hr.py`). I saved the machine at the natural home-run caller (bank 6 `$B6F8 JSR $B73E`):

- **29 v 11**: solo home run, team 11, top of the 1st, frame 3749.
- **11 v 29**: two-run home run, bottom of the 1st with a runner on first, frame 9165.

These are the same frames B's lane recorded, regenerated independently. I then ran stock, A and B from the identical state, including planted variants made at that natural caller state.

| Case (from the natural caller) | Runs | A vs stock | B vs stock |
|---|---:|---|---|
| 29v11 natural solo | 1 | equal at frame level (A's milestone cycles drift −3…+6 across all cases, never a frame) | equal to the cycle |
| 29v11 planted grand slam (`$055F–$0561=0`) | 4 | equal at frame level | equal to the cycle |
| 11v29 natural two-run | 2 | equal at frame level | equal to the cycle |
| 11v29 planted grand slam | 4 | equal at frame level | equal to the cycle |
| 11v29 planted walk-off, bottom 6th (→ scene 9, scoreboard) | 2 | equal at frame level | equal to the cycle |
| 11v29 planted ten-run rule, bottom 2nd (→ scene 9) | 2 | equal at frame level | equal to the cycle |
| 11v29 natural, both pads mashing A/B/START/SELECT | 2 | equal at frame level | equal to the cycle |
| 29v11 natural and grand slam, at 6 vblank phase offsets (1…29,000 cycles) | 1/4 | equal | equal |

"Equal" means all of the following match stock:

- the frame of every milestone: `$B73E`, `$D9DF`, `$D755`, the draw, `$D770`, `$D77B`, `$D790`, `$D7F8`, `$CFAA` or `$D872`, and scene 3;
- per-frame scene, state, `$BA` and song over 832–835 frames, plus CHR1 in the 11v29 runs and CHR1 and mask in the phase sweep;
- the complete APU write stream (5,317–6,244 writes per case) and the sound queue, including the four `$2C` run SFX plus song `$0A` on grand slams;
- game RAM at the exit;
- all 8 KiB of WRAM;
- late PPU writes and partial-mapper sequences.

The runs scored the expected runs, credited +1 HR and +1 hit to the batting side only, set the game-over flag where expected, and took the field or scoreboard exit. A continues in bank 6 (`$27=6`, PRG 6) at `$D770` in every case.

RAM 300 frames after the exit is identical to stock on the field path. On the scoreboard path (walk-off and ten-run), B leaves 126 bytes different, all in the two loader buffers (`$0100–$017F`, `$0340–$035F`). A leaves 168. 130 of those are in the same buffers, and the other 38 are:

- zero page `$14–$17` and `$37–$38`, which stock's `$C5C4` writes and A's raw copy does not;
- stack residue `$01E6–$01E9`;
- A's last light list, left in the display-list buffer at `$0300–$031B`.

A stale-read watch (`tools/stale_watch.py`, widened in `tools/stale_watch2.py` to `$01E0–$01EF` and `$0300–$031F`) found no read of any of these bytes before it was rewritten within 1,500 frames after the exit, on either path, for any ROM. These leftovers are benign.

Mutation controls prove my harness can fail (`tools/make_mutants.py`, `tools/run_mutants.py`):

- **M1**: A rebuilt without its timing compensation. Phase 3 starts one frame early (3811 vs 3812), the celebration shows one extra frame (469 vs 468) and audio is unchanged. This is everything A's 26,229-cycle busy-wait buys.
- **M2**: B with the `$D9E2` HR-stat INC changed to BIT. Caught: HR stat 0 vs 1.
- **M3**: B with one bit flipped in VICTORY plane id `$89`. Caught by the VICTORY decode check.

## What the player sees (native resolution)

- `out/compare-native.png` (and the 2× `out/compare-2x.png`) shows, NTSC-cropped like the real-core captures:
  - row 1: the accepted mode menu, scoreboard and analysis card;
  - row 2: stock HR;
  - row 3: A in three states;
  - row 4: B in both poses.
- `out/A-sequence.png` and `out/B-sequence.png` show frames 3812–3845 with BA and CHR bank. `out/A-animation.gif` and `out/B-animation.gif` play them at one frame per NES frame.
- I checked my renderer against root's real-core captures. After the 8-line crop, `opus-runtime/frame-016/020/024/032` match my CPU render of the corresponding B pose with **0 pixels violating a one-to-one color map**. `baseline-runtime/frame-016/024` match stock the same way. So the model and renderer are trustworthy for A as well, even though I did not use any real-core A capture.

Findings for A:

- **The title is not steady.** On every CHR `$15` pose, 565 cream pixels of the title band turn pink (479), red (58) or navy (28). They sit in tile columns 8–10 and 13–19, rows 10–13: the lower strokes of O, M, E and R next to the pom-poms (`out/A-letters-both.png`, `out/A-letter-diff.png`). A's report says "the title's unobscured strokes remain cream across both poses". That is false for these strokes. A's test (`tests.py` `animation`) compares only the crop `(16,48)-(48,112)`, the letter H, which does not change.
- **The crowd splits at attribute boundaries.** I counted same-ink pixel pairs that cross a 16 px attribute boundary and render in two colors. A has 587/2,745 (21.4%) on the `$04` pose and 670/2,729 (24.6%) on the `$15` pose. Stock has 0.2%/1.2% and B has 0%. Faces and hands are cut into cream and pink halves, and white shirts merge with cream skin (`out/A-crowd-zoom.png`, stock left, A right).
- **The lights read as notches.** The seven lights are 8×8 gold notches under the rail that alternate between 3 and 4 positions in lockstep with the pose flip (`out/A-chase-zoom.png`).
- **These problems are structural.** The stock letters and faces share the same CHR values across `$04` and `$15`, and four 3-color palettes cannot keep letters steady and skin consistent at the same time. Fixing A means changing CHR or redrawing cells, which removes A's main argument.

Findings for B:

- **The cast is pixel-exact in ROM** (`tools/visual_checks.py`):
  - pair: 1,621 and 1,696 opaque pixels across the two poses, 0 mismatches;
  - cheer: 852 px, 0 mismatches; cheer-b: 786 px, 0 mismatches;
  - batter: 803 px, 0 mismatches;
  - crowd-red: 12,288 visible px per pose, 0 mismatches.

  The part PNGs B stamps are byte-identical to `build/stockart32/parts/*.png`.
- **Polish: the right star touches the N.** The right marquee star at (219,52) merges into the N's right stroke and shadow in both poses. The left star clears the H by 3 px (`out/B-star-zoom.png`, `out/B-star-left-zoom.png`).
- **The exit blank frames are navy.** The 3 blank frames at the exit show navy `$0C` instead of stock black. A does the same. The backdrop must stay `$0C` because it is the parts' ink color.

## A-specific integration checks

- **Bridge at fixed `$F379`.** Three simulation readers end right before it:
  - `$EF4E LDA $F2C9,X` reaches at most `$F308`;
  - `$EF5F LDA $F309,X` reaches at most `$F348`;
  - `$EF8E LDA $F349,X` reaches at most `$F378`.

  These bounds hold only because the RNG table `$C4FA` (64 entries, max 7), the `$F1BF` table (max 14) and the clamps at `$F166`/`$F185` stay pinned. A's contract and its 192-case test cover only the `$EF8E` reader. A production A would have to pin all three readers and all three dependencies.
- **Bank 6 `$B900`.** Bank-6 content ends at `$B8C0` (an RTS) and resumes at `$BDB8`. No JSR or JMP targets the replaced tail `$D77B–$D792`. The plausible fixed-bank indexed readers near `$B8xx` (`$CAFC`, `$D9FB`) map banks 2 and 0 first.
- **Dynamic census** (`tools/census.py`): 30,000 frames of a natural 29 v 11 WATCH game from RESET, through the bottom of the 3rd with one home run. Scenes 02/03/04/05/09/0A/0C/10 were visited.
  - Stock ROM: **zero reads** of bank 6 `$B8E1–$BDB7` (which includes A's `$B900–$B9DB`), fixed `$F379–$F386`, bank 13 `$A500–$AA1F` or the simulation tables `$F2C9–$F378`.
  - A ROM: those regions are touched only by A's own code, and only in scene 5.
  - CHR selections are identical in both ROMs. CHR0 never selects `$04` or `$15`. CHR1 holds `$04` for 237 frames and `$15` for 232, which is one home-run window.
  - This run did not include SPEED mode, so it does not exercise the simulation readers. Their bound is the static proof above.
- **NMI and display list.** The helper overwrites `$0300` from index 0 and sets `$32=28`, so it would clobber any pending display-list entry. That is safe only because nothing else queues during phase 3, which the parity runs confirm. The display-list format (`[hi lo tile $FE]×7`, last `$FF`) matches `$C53A`. On chase frames the last PPU write lands 1,093–1,096.5 cycles after vblank, against stock's 676.5 (budget about 2,273).
- **Late writes.** The only late PPU writes in natural play are stock's field-initializer blank at `$CFB4` (`STA $2001=#$40`), identical in count and offset for stock, A and B. A's reported `$C268` late write comes from its planted trigger fixture; I did not see it in natural play.
- **Draw timing.** The stock interval is 40,724 foreground cycles. A's raw copy takes 14,495 and is padded by 26,229, and I recomputed both numbers.

## B-specific integration checks

**CHR `$15`'s other reader is unreachable** (`tools/static_checks.py`, 28/28 pass). Split preset 6 (`$FB71: 06 15 12 12 12 68`, CHR0=`$15`) is requested only at `5:$AC76`, by screen 5, which appears only in sequence 5. The chain that rules sequence 5 out:

- Scene `$1A` clears `$10` and always recomputes `$CC` through `$A930`, giving 0–2, or 3–4 for VICTORY.
- Only scene `$1C` sets `$CC=5`.
- No writer stores `$1B` or `$1C` to `$047B`. The computed stores yield only `$10/$16` (`5:$9EC2`), `$00/$06` (`4:$B6F3`), `$13/$00` (`5:$A901` table) and `#$0A` (`4:$B323`). The only `INC $047B` sites in bank 5 are `$98D1` (scene `$12`→`$13`), `$A8B2` (`$1A`→`$1B`) and `$A8CA` (`$1C`→`$1D`). The indexed stores near `$047B` are the sound queue, whose indices wrap with `AND #7`.
- One direct write of scene `$1D` exists, at fixed `$F0CA` in the SPEED simulation. A control-flow walk of `$F0C0` and `$EE43` finds only two returns to the dispatcher. `$EE42` returns after storing scene `$17` and `$F0FF` after storing scene `$0A`, so `$1D` is never dispatched.

MMC1 control is only ever `#$1E` or `#$1F` (4 KB CHR mode), so `$14` and `$15` are never paired. Apart from `$D76C`, `$D793` and the unreachable preset 6, no immediate, preset, camera-table entry or loader argument selects `$04` or `$15`. Real-core censuses from earlier stages agree: about 1.3 M frames across WATCH, 1P, attract and menus never put `$04` or `$15` in CHR0. None of those censuses covers a SPEED tournament or the championship ending, so those remain root gates.

**Shared metatile set `$15` is untouched for the other screens.**

- Exactly three loader calls use set `$15`: HR map `$24` (`$D767`), split map `$33` (`5:$AC6D`) and VICTORY map `$2A` (`5:$ACC6`). Maps are packed back-to-back with no overlap.
- My own decoder shows VICTORY and split are byte-identical to stock in B (and in A).
- B's 116 changed ids (`$01–$74`) are disjoint from the 105 ids VICTORY and split use, leaving 151 free.
- The set and map descriptor tables are read only by `$C5C4`.

**Dynamic confirmation.** In the stock census game, bank 1 planes `$8400–$87FF` were read only by `$C687–$C69C`, map `$24` only by `$C659/$C676`, and palette record `$0E` only by `$C1D9`. All of those reads were the `$C5C4` and `$C1A4` calls in scene 5.

**Palette record `$0E` is read only at `$D75F`.** `$C1A4` maps record `r<$40` to `$F7DF+16r`, so only `r=$0E` reaches `$F8C0`. Every other caller is ruled out:

- All other callers load an immediate other than `$0E`.
- The bank-5 player palettes are `{$88,$89,$87,$8D,$8E,$8F}` and `{$10,$11,$14,$15,$0A,$16}`.
- The field camera table yields only palette 9 with CHR 1–3, and zeros past index `$A0`.
- `2:$B97C` gets its argument back from the 32-team selector bridge (`$FF20` → bank 10 → bank 11 `$817B` returns with A=`$07F8`, the saved return-address low byte `$6B`). It loads record `$6B`, not `$0E`.

**The `cheer-b` mask is sound** (`tools/cheer_audit.py`, `out/cheer/cheer-b-audit.png` beside `out/cheer/cheer-audit.png`).

- My recomputation reproduces mask `b88111f1…` and PNG `f7008b62…` exactly, and the approved `cheer` digests (`4a9c0053…`, `0e8f4270…`).
- The two drop boxes remove exactly two 8-connected components lying wholly inside them, 57 and 54 px: the neighbours' pom-poms. Nothing connected to her body is cut.
- The face box loses no opaque non-sky pixel.
- Source-zero handling is the approved rule. 574 source zeros are cleared (approved `cheer`: 567), mostly the bleacher dither and ground shadow. The outer layer of the thick hair outline also clears, exactly as in the approved panel-4 cut.
- I find it faithful. It still needs a reviewed manifest entry and digests in production.

## Root's corrected candidate (`a66add03…`)

I copied the corrected candidate into my scratch as `roms/C.nes` and ran these checks (`tools/check_C.py` plus the inline checks recorded in this session):

- **Ownership.** Data-only. 8,275 bytes changed from the input, all in bank 1 (planes for ids `$01–$73`, which is 115 ids and a subset of B's; map `$24` + attributes), fixed `$F8C0–$F8CF` (the same record as B) and CHR `$04`/`$15`. No other PRG bank or CHR bank changes, and the fixed bank is unchanged outside the palette record.
- **Shared screens.** VICTORY and split decodes are byte-identical to stock, and the changed ids are disjoint from the 105 ids those screens use.
- **Runtime.** Equal to stock *to the cycle* from my natural states: 29v11 natural (1 run) and planted grand slam (4), 11v29 natural (2) and planted walk-off (2, scoreboard path). Milestones, per-frame scene/state/BA/song/CHR1/mask, APU streams (5,380/5,426/5,317/5,350 writes), sound queues, WRAM and exit game RAM all match. RAM 300 frames later differs only in the two loader buffers. Late and partial-mapper records match.
- **Picture.** The pair and batter match their approved parts at the frame-A positions in both CHR phases: 1,621 and 803 opaque pixels, 0 mismatches. The cheer alternates `cheer`/`cheer-b` (852/786 px, 0 mismatches), and the crowd and marquee still change. See `out/C-both-native.png`. The right-star/N collision is still present.

## Test review

**A**

- *Exit codes:* honest. Assertions raise, `rerun.sh` uses `set -euo pipefail`, negative controls must raise, and `finalize.py`'s hard-coded `True` fields are each preceded by a guarding assert. The suite would silently pass under `python -O`; no rerun uses `-O`.
- *Weak oracle:* the lettering oracle crops only the letter H. It passed while the O, M, E and R strokes flash.
- *Parity by construction:* the 512-case scoring parity calls the unchanged `$B73E` on a flat bus, so stock equals A by construction. Its independent oracle (1 + occupied bases, per-run pitcher debit, runner deactivation, series bytes) is the valuable part.
- *Injected fixtures:* every event fixture is injected. `trace_stock.enter` zeroes `$0480–$06B2`, plants scene 5 state 2 and starts at `$D755`. `real_event.enter` calls `$B73E` directly and starts at `$D9D6`. There is no played home run.
- *Zero page unchecked:* timeline parity compares `$0480–$0514`, `$0555–$06B2`, `$06E0–$07FF` and WRAM, but not zero page. Guard bytes are returned but not compared. My full-RAM runs found no zero-page defect.
- *Round-trip oracle:* the pxl "zero pixel" check is a round trip of ROM-derived data. The independent metatile expansion against CPU VRAM is a real check.

**B**

- *Exit codes:* honest. The suite exits 1 on any FAIL, and the logs show 284/0 (CPU) and 22/0 (static). Each negative control must trip at least one named check.
- *Circular pixel oracle:* the pixel oracle compares B's own renderer with B's own converter render, which is circular. Root's real-core frames match my independent render exactly, which closes that gap.
- *Loader-buffer exclusion:* RAM comparisons exclude presentation scratch at the exit and only the two loader buffers 240 frames later. Each exclusion is backed by a stale-read watch, which I re-ran over a wider set (zero page, the loader buffers, `$01E0–$01EF` and `$0300–$031F`).
- *Played states:* the cases come from played WATCH games; the planted RAM is set at the natural caller.
- *Planted team ids:* the 32-team sweep plants team ids only for the cutscene, because a mid-game team swap crashes the stock field re-initializer.

## Recommendation for root

**Production base: B's data-only flipbook stage, in root's still-players form (`a66add03…`)**, built from analysisart32 with B's guarded builder pattern (input hash pin, claimed-edit-only diff, protected VICTORY and split ids, fixed bank unchanged outside `$F8C0–$F8CF`).

**Exact ownership** (file offsets include the 16-byte header). These are B's claims. The corrected candidate uses a subset: plane ids `$01–$73`, so file offsets `0x4411–0x4483`, `0x4511–0x4583`, `0x4611–0x4683` and `0x4711–0x4783`; plane id `$74` returns to its stock bytes. Claim exactly the bytes the final assets own.

| Region | File offset | Bytes |
|---|---|---:|
| CHR `$04` (pose A) | `0x44010–0x4500F` | 4,096 |
| CHR `$15` (pose B) | `0x55010–0x5600F` | 4,096 |
| Bank 1 planes, ids `$01–$74` | `0x4411–0x4484`, `0x4511–0x4584`, `0x4611–0x4684`, `0x4711–0x4784` | 464 |
| Bank 1 `$8DF0–$8F1F`, map `$24` + attributes | `0x4E00–0x4F2F` | 304 |
| Fixed `$F8C0–$F8CF`, palette record `$0E` | `0x3F8D0–0x3F8DF` | 16 |

**Mandatory before publication**

1. Add `cheer-b` to the production character manifest with its drop boxes, a `drop_why`, mask `b88111f1cdd2c16ecfe4db3d2e652451a99d92ea2097f3a544860cc26f291c4b` and PNG `f7008b62e938fc1b9f1acfaa13a547140d8bf7c45ae49960d54f8c6be0d948ed`. Keep stock-derived pixels generated under `build/`.
2. Encode the CHR `$15` second-reader argument as stage checks, not prose. Pin or re-verify:
   - every scene store and its value, and `$A8A6–$A958`;
   - the `$A959` sequence table and `$AC5C` screen table;
   - preset table `$FB4D`, the `$C6C1` callers and `$F0C0–$F0FF`;
   - the `$C102` control values;
   - the set and map users of set `$15`.

   `tools/static_checks.py` is a working template. Any later stage that touches these must re-run it.
3. Graft these regression cases from A into B's suite, run on the built B ROM:
   - the 512-case all-32-teams × both sides × 8 base-occupancy scoring oracle through `$B73E`;
   - the 64 HR-stat tails through `$D9DF`;
   - the 128 suppression-gate cases (`$C1&$04`, `$048E&$20`);
   - the 384 exit and next-batter cases (`$0513 += 2`, wrap at `$12`; scene 2 vs 9);
   - both HUD-expiry forms (60 updates inside the camera window, immediate outside);
   - the attract-mode START route during the cutscene.

   Also add my vblank-phase sweep. Skip A's NMI edge sweep and its `$F349` bound test, which have nothing to test in a data-only stage.

**Optional polish**

- Move the right star 2–4 px right, or shift the title left, so it clears the N.
- Consider holding the title face color constant and alternating only its shadow and the bulbs, if the full cream/gold title swap feels too strobing on hardware.
- A third motion phase (B's "S" palette layer) can come later as its own gated stage. Do not graft A's chase code into this stage.

**Do not take from A:** the bank bridge, the busy-wait, the display-list overwrite or the palette-only recolor of the stock screen. A's cell-level provenance file and its stock-screen extraction checks are not needed, because B does not reuse those cells.

**Lesson from A's rejected sprite panel** (prototype-B in the Sol lane; its lessons only). Showing the intro cast as sprites over the stock background costs:

- 63 sprites, with 8 on one scanline at the hardware limit;
- a borrowed CHR0 (`$14`) that the exit must restore;
- OAM writes on every update;
- a hard rectangle that competes with the cheerleaders.

Keep the cast in background tiles as B does. Treat any later OAM motion layer (B's "S" idea) as a separate stage with its own scanline, CHR0-restore and exit gates.

## Remaining real-core gates (root-owned)

1. Natural multi-run home runs on the real core (two-run and grand slam), plus a state-loaded walk-off or ten-run exit through the scoreboard. So far root has natural captures (550 frames each) for the baseline, B and, per the plan, the corrected candidate. All of them are the same solo home run.
2. A mapper census of a **SPEED tournament** and the **championship ending (VICTORY)** plus long attract cycles. CHR0 must never select `$15`, and `$04`/`$15` must appear in CHR1 only inside home-run windows. This is the real-core confirmation of the static proof, including the transient `$F0CA` scene `$1D`.
3. A visual check of the VICTORY screen on the built ROM. The decode is byte-identical in the model.
4. On the real core: the NTSC 224-line crop, the 8-frame cadence, the pair and batter holding still in both phases, and the three navy exit frames.
5. A listening check: song `$0A` and one `$2C` per run.
6. The stock-six and full-31 tournament and password flows, and title, menus, Analysis and scoreboard regression, since CHR `$04`/`$15` and bank 1 change.
7. Hardware or flashcart, PAL and a second emulator remain open, as in earlier stages.

## How to reproduce

From `/Users/dfm/GitHub/nesdav/little-league`, with `J=/tmp/ll-homerunart32-judge`:

```sh
python3 -B $J/tools/verify_freeze.py $J/out/freeze-after.json      # both ledgers, 0 missing/changed
python3 -B $J/tools/romdiff.py $J/roms/stock.nes $J/roms/A.nes      # 1,250 bytes, 9 regions
python3 -B $J/tools/romdiff.py $J/roms/stock.nes $J/roms/B.nes      # 8,265 bytes
.venv/bin/python -B $J/tools/static_checks.py                       # 28 pass; exit 0
.venv/bin/python -B $J/tools/cheer_audit.py                         # cheer/cheer-b masks + audit PNGs
.venv/bin/python -B $J/tools/natural_hr.py 29 11                    # ~2 min; states/29-11-*.pkl
.venv/bin/python -B $J/tools/natural_hr.py 11 29                    # ~6 min; states/11-29-*.pkl
.venv/bin/python -B $J/tools/run_parity.py $J/states/29-11-B6F8.pkl 29-11 && .venv/bin/python -B $J/tools/analyze_parity.py 29-11
.venv/bin/python -B $J/tools/run_parity2.py $J/states/11-29-B6F8.pkl 11-29 && .venv/bin/python -B $J/tools/analyze_parity2.py 11-29
.venv/bin/python -B $J/tools/stale_watch.py && .venv/bin/python -B $J/tools/stale_watch2.py
.venv/bin/python -B $J/tools/phase_sweep.py
.venv/bin/python -B $J/tools/make_mutants.py && .venv/bin/python -B $J/tools/run_mutants.py
.venv/bin/python -B $J/tools/render_sets.py 29-11 && .venv/bin/python -B $J/tools/visual_checks.py
bash $J/tools/repro.sh                                              # B: identical ROM + 8 assets; A: in-memory 7104a50c…
.venv/bin/python -B $J/tools/check_C.py                             # root's corrected candidate vs stock, 4 natural-state cases
.venv/bin/python -B $J/tools/census.py stock 29 11 30000            # dynamic read census (slow)
.venv/bin/python -B $J/tools/census.py A 29 11 30000
```

Reproduction results: B's pxl render, converter and builder give `1beb37e6…` with all 8 assets byte-identical, and the pxl vendor stays clean at `3bc816cb…`. A's `build()`, run in memory, gives `7104a50c…`. Its source nametable equals my independent decode of map `$24`.

Every judge artifact (scripts, states, ROM copies, renders, JSON results and this file) is hashed in `out/manifest.json`.

## Limits of this review

- The CPU model approximates PPU timing and sprite-0, so none of this is hardware evidence.
- The planted cases change named RAM at a natural caller state; only the solo and two-run home runs were played.
- I did not run SPEED mode, the championship ending or the analysis screen in the model. CHR `$15` unreachability is a static proof plus earlier real-core censuses that do not cover those paths.
- The dynamic census covers only one long WATCH game.
- I checked root's corrected candidate on 4 natural-state cases plus the static and visual checks. I did not run the phase sweep, mash, ten-run or mutation runs on it. Root's full CPU suite on it was still running when I read the plan.
- I did not listen to audio.
