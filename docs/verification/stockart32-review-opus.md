# stockart32 independent review (Opus, read-only)

Verdict: **no blockers. Execution matches the frozen selected design.** Two small defects are
worth fixing before publishing, but neither blocks acceptance: an audio-file link gap in the
probe wrapper and a latent dict-key collision in `check_targets`. Root still owns acceptance of
the in-progress emulator score tour and integrated gate. This review does not claim either one.

Scope: all 18 files pinned in `build/stock-characters-design/review-freeze.json` (hashes verified
at start and end: 18/18 unchanged). Baseline HEAD 511d221. Input `build/scoreart32.nes`
2ae1a7ab…, candidate `build/stockart32.nes` a5bf74ee…. Every experiment ran on copies under
`/tmp/ll-stockart32-review-opus` (a scratch repo copy has its own `ROOT`, because `ROOT` comes
from `__file__`). I made no repo edits and no git, emulator or romdev calls. The full
13-minute suite was not rerun.

## Measured checks (all independent of the code under review unless noted)

| Check | Result |
|---|---|
| Byte diff scoreart32 → stockart32 (own iNES offsets) | 4,634 bytes; per region 628/2/2,383/1/306/1,314; 0 outside the six regions; PRG banks changed {4,13}; CHR 4K banks {5,6}; header equal |
| Palettes from ROM bytes | mode: only bytes 11,15 → $36; score: only byte 11 → $36; sprite halves (16–31) and palette 0 identical on both screens |
| Own renderer, base vs candidate | score: 0 pixel changes for y<160, changes only y 160–223; mode: 0 changes for y<64 and 0 inside the sign/board x32–223,y<128; no attribute change inside the board |
| Text/cursor/run lists | font_glyphs, spans, runs and cursor equal to accepted modeart32 assets; 24 font glyph patterns equal CHR $00 and accepted CHR $06; 65 lettered cells identical; span attribute palettes unchanged; bank 13 $9420–$9FFF and bank 1 cursor table unchanged; font uses values {0,2} only |
| Score glyphs | 78 GLYPHS patterns unchanged; score rows 0–19 tile ids identical; no upper-row tile pattern changed |
| Draw timing | both 1 KB copies are fixed `LDA ($00),Y / STA $2007 / INY / BNE` over page-aligned data, so cycle cost does not depend on the data |
| Source pins vs the **original 8-bank cartridge ROM** | all 10 pinned ranges hash-equal on stock ROM and on scoreart32/modeart32/title32/stockart32 |
| `$AEE6` disassembly (stock ROM, py65) | (x,y) origins at $B1E8, 64-byte tile maps, 2-bit selectors low bits first, `ORA #$20`, no flips; matches `stockart32_source` |
| Own stock decode vs user captures | glove, batter, cheer, pair 0/4096 px differ; both crowds 0/2560 |
| Parts vs own decode | every painted pixel is its source colour through the manifest map, or $0C on a source zero; 0 errors; all 4 mask digests match; crowds 0 errors |
| Pair corrections | (17,23),(53,26) = $0C; 18 opaque hand pixels in [55,0,9,18] all dropped; only (55,16),(55,17) navy cap outline kept; cap edge (54,16),(54,17) = $16 |
| Batter corrections | 115 ink_keep points, unique, all source-zero, all $0C, rows 8–18 |
| Placements vs own ROM render | all 14: 0 mismatching visible pixels (batter 803, glove 987, cheer 852, pair 1,323, crowds 4,608/6,592); declared-hidden areas are covered as the `why` says |
| provenance.json | 288 part cells vs stock ROM and 282 destination tiles vs candidate bytes: 0 mismatches |
| Scratch rebuild | `--check` writes nothing; default run installs 17 outputs byte-identical to `build/stockart32`; builder gives a5bf74ee… |
| `--record` round trip | art edit: default and `--check` refuse, write nothing; `--record` installs and records; builder follows (715f9b24…); restore + `--record` gives the registry back byte-for-byte |
| Extra alias/missing-path cases (14, scratch) | refused with nothing changed: symlinked *parent* into art/ and build/vendor, hardlinked render output (post-render guard), dangling symlink in --out, registry missing (default and --check), symlinked data/stockart32 on --record, registry hardlinked to verify.sh, builder -o under linked parent, case-variant of scoreart32.nes, new file inside build/stockart32, missing --rom. Builder -o hardlinked to an unrelated file replaces the link; the other file keeps its bytes |
| Stage palette mutations (in memory) | 14/14 refused (13 by stage, 1 by asset validation) |
| test_stockart32_probe.py on scratch copy | PASS, 39 refusals |
| Suite's fast CPU sections from scratch | manifest (58 cases), pins, parts, regeneration, provenance, readback, converter controls, assets (95 cases), stage, installed: PASS in ~5 s |
| Python 3.12 grammar | all new tools compile on 3.13 with `feature_version=(3,12)` (CI byte-compiles on 3.12) |

## Findings

### 1. [warning, low] Probe wrapper's audio destination follows links to non-input files
- Location: `tools/probe_stockart32.py:35-41` (`preflight`) and `:58-67` (`allowed`/`checked_call`
  cover `.png` only). The write happens in the accepted probe, `tools/probe_modeart32.py:84`:
  `(out / 'mode-audio.json').write_text(...)`.
- Evidence (scratch): with `out/mode-audio.json` hardlinked **or** symlinked to an unrelated
  file, `preflight(...)` accepts it (nlink=2), and the probe's exact `write_text` call rewrites
  the other file (`{"accepted": "earlier run"}` → `{"transitions": 183}`). Screenshots have a
  second layer: `checked_call` compares `destination.resolve()` against the planned set, so
  symlinks are refused there. Hardlinked PNGs pass too; whether they get clobbered depends on
  how romdev writes (not verified).
- Impact: inputs remain protected, so the stated contract holds. A pre-existing link in the
  output directory (for example, a reused earlier evidence file) can still be overwritten, and
  the convert tool already refuses exactly this case (`st_nlink != 1`, `is_symlink`).
- Suggestion: in `preflight`, refuse any planned path where
  `path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1))`.
  This mirrors `stockart32_convert.protect_outputs` lines 288-289.

### 2. [warning, low, latent] `check_targets` drops shirts that share a target palette
- Location: `tools/stockart32_parts.py:398-399`:
  `{part.palettes[s]: set(m.values()) for s, m in part.shirts.items()}`.
- Evidence (in memory): add shirt `x` mapping teal/magenta → gold $28 with `palettes x: 2`. If
  `x` is listed **before** `r` (also palette 2), it is **ACCEPTED**. If listed after, it is
  refused ("targets $28 are not in mode palette 2"). The result depends on key order.
- Impact: the current manifest is unaffected (crowd-mix maps r→2, b→3). The converters still
  refuse cells whose colours fit no palette, but a cell that fits a different palette would
  slip through the manifest's declared-target check.
- Suggestion: iterate pairs instead of building a dict:
  `wanted = [(part.palette, part.colors.values())] if isinstance(part, Character) else [(part.palettes[s], m.values()) for s, m in part.shirts.items()]`.
  Add one manifest case to `test_manifest`.

### 3. [observation, frozen design] A few black source-zero outline pixels now show the cream wall
Execution reproduces the frozen masks exactly. These come from the reviewed masks, not from the
code. The automatic ink rule keeps only zeros 8-adjacent to figure pixels, so a 2-px outline
can lose an outer pixel. Dropped source zeros lying between kept pixels, visible in the ROM:
- cheer (crop coords): (25,10) top of hair outline, (25,42), (26,43), (32,43)
- batter: (27,19) face box, just below the reviewed rows 8–18; (39,29)
- pair: (33,39), and the outer part of the left boy's black brim underside, 15 px including
  (22,23): (28,19), (28,20), (25–28,21), (23–27,22), (22–25,23). All but (28,19) lie in face
  box 1. A 1-px navy outline remains.

All of these show $38 in the ROM; the intro showed black. No check guards source-zero pixels:
`faces_and_seams` only checks opaque pixels. If root wants these closed, it is the same
mechanism as (17,23): add `ink_keep` points and re-record mask digests (design change, root's
call). Otherwise, soften `docs/stockart32.md:23` ("The masks explicitly preserve the face and
hair pixels needed…"), because a handful of outline pixels are not preserved.

Also frozen-design: the pair's single `2C → 16` map turns the right boy's cyan shirt shading
into scattered 1–3 px red specks on his cream shirt (34 kept cyan components; 28 of them are
1–3 px). This follows from the accepted palette-limited recolour.

### 4. Optional simplifications (no behaviour change)
- `stockart32_convert.py:276-304, 333-360`: `regenerate` writes only to a TemporaryDirectory.
  The pre-render guard pass, its `renders=` exemption and the `known` list exist only to fail
  ~2 s earlier. One guard pass on the exact output set after regeneration (plus one
  `protect_registry`) would delete the parameter and its subtle "anything under renders counts
  as planned" rule.
- `stockart32_convert.py:46, 309`: `protect_registry` borrows `build_title32.protect_output`.
  That is the deepest earlier chain that does not forbid `data/`, so `--record` is coupled to
  four older stages' guard composition. The nlink/symlink/samefile/protected-sha checks already
  in `protect_registry` cover the risk. Drop the call, or assert that the registry resolves to
  `ROOT/data/stockart32/digests.json`.
- `stockart32_parts.py:124-130`: resolve `Placement.area`/`visible` defaults in
  `parse_manifest` (sizes are known there). This removes the `None` cases, the
  `or (...)` fallbacks in `convert.visible_rect` and `test_readback`, and two comments.
- `stockart32_parts.py:17, 281`: `faces` is required and validated but used only by the test.
  Enforcing it inside `cut_character` would make `--record` of a new mask fail when a face
  pixel drops, without relying on the suite.
- `stockart32_parts.py:493`: `clear` holds source-*transparent* pixels, while the docstring
  uses "clear" for output-clear. Rename it to `transparent`.
- `test_stockart32_probe.py:15-41`: the test hardlinks and symlinks **real tracked files**
  (ROM, verify.sh, registry, characters.json, assets) into a temp dir. It is safe today because
  romdev is patched to raise before any write, but it would turn destructive if a future probe
  wrote before its first romdev call. It passes unchanged from a scratch copy, so run it on a
  `checkout()`-style copy.
- `test_stockart32.py` is 1,085 lines. That is over 1k, but it matches precedent
  (test_scoreart32 1,035; test_modeart32 1,264) and is cleanly sectioned. Waived.

### 5. Ops and evidence limits
- `tools/verify.sh:57-60` now needs Node ≥ 22.18 and the pinned pxl checkout. Earlier stages'
  converter checks ran without pxl because their renders were committed. Here this is inherent,
  since stock-derived renders must not be tracked. It fails loudly, about 10 minutes into
  verify.sh. CI does not run verify.sh.
- `README.md:86` still names `build/scoreart32.nes` as the final build. Update it at publish.
- Not reviewed/claimed: the emulator score WATCH tour, the integrated stock-six/full-31 gate,
  physical hardware and runtime CPU-model suites (I relied on the implementer's and root's
  reported passes). `docs/verification/stockart32-gate.txt` and `stockart32-review-sol.md`
  changed during this review (other jobs). I did not read them.

## No-comments audit (report only, comment-sicko rules; shebangs, CLI/format docstrings and `why` data fields excluded)
- 39 comment lines in the 7 new Python files. Kill candidates: **31**. That is 14 section
  banners (build 1, convert 3, parts 2, test 8), narration (build `:41`, test `:59`, `:63-64`)
  and type-shape notes (parts `:112-117, :129-130, :412-414`; source `:76-77`; convert `:59`;
  test `:74`).
- Keeps: source `:28-31, :69-70` (stock ROM and NES hardware facts we cannot change);
  `# noqa: E731` at source `:99` and test `:104, :192` (style-only rule; trivially removable
  with `def`).
- MUST KILL (reshape so the prose is unnecessary):
  `stockart32_convert.SCREEN_BYTES` → NamedTuple (bank, screen, palette, chr);
  `stockart32_parts.Placement.area/visible` → concrete boxes at parse time;
  `Crowd`/`Part`/`Composition` shape comments → typed annotations or a small `Metatile`;
  `test_stockart32.SHOT_RGB` → `FCEUX_CAPTURE_RGB`.
- The pxl sources hold 36 + 53 `//` lines. The NES-code-per-letter palette notes are
  constraints; most layout narration ("the ticket counter … hides the panel edge") is
  intent narration and could go. Low priority for art sources.

## Ledger
review-freeze.json 18/18 unchanged at start and end; scoreart32 and stockart32 SHAs unchanged;
installed `build/stockart32` matches the registry; `git status` identical to the start apart
from the two docs/verification files written by other jobs; no new `__pycache__`.
