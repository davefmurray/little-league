# homerunart32 production review (Opus lane, read-only)

Scope: the 16 files in `build/homerunart32-design/production-review-freeze.json` (base `4ed637d`), plus
`docs/homerunart32.md` and `docs/homerunart32-plan.md` as claims. Everything below judges that original freeze
unless it says **live**. Live observations are of root's fixed tree (`production-fixed-freeze.json`, 17 files).
I did not re-review the live tree; root owns targeted reruns.

## Verdict

**No blockers against the original freeze.** I independently reproduced the selected ROM
`a66add03…` from `analysisart32` `1e524b53…`. It changes data only, the art is faithful, and the pair and batter
are pixel-still across both frames. The full CPU suite passed against the frozen code (19 sections, exit 0).

- 4 warnings, 11 nits. W1 makes the docs' output-alias guarantee false on this Mac (case-insensitive APFS),
  and it is still present live. W2 (fixture cache writer unguarded) is fixed live for exact-case paths.
  W3: the shared-reader module claims more coverage than it scans. I found no reachable path in the pinned
  input. W4: the suite file is 1,375 lines.
- **Process incident (mine):** my exit-code sweep accidentally drove one real-core probe run through romdev.
  Details are in the "Process incident" section. Root's evidence was not touched.

## Ledger and hashes

| When (local) | Result |
|---|---|
| 14:1x start | 16/16 match the original ledger; input `1e524b53…`, output `a66add03…` |
| 14:32 | live drift in 4 files (root's fix in progress) |
| 14:35 | live drift in 8 files; `homerun32.px.js` changed before `digests.json` (transient) |
| 14:40 end | original ledger: 8/16 drifted live (`homerun32.px.js`, `digests.json`, `build_homerunart32.py`, `homerunart32_fixtures.py`, `homerunart32_machine.py`, `homerunart32_readers.py`, `test_homerunart32.py`, `verify.sh`). Fixed 17-file ledger: 0 drift. ROM hashes unchanged throughout. |

`frozen/` holds a byte-exact snapshot of the original 16 files (re-verified against the ledger at 14:40).
Live diffs vs that snapshot are in `live-diffs-small.txt` and `live-diff-fixtures.txt`. Root's live registry
changes only the px.js source digest and the `provenance.json` output digest. The `rom` and PNG digests are
identical.

## Independent verification (original freeze)

My own decoder (`probe_static.py`) does iNES offsets, the `$C5C4` tables, CHR and the byte diff itself. It
imports only `NES_RGB` and PIL.

- 8,275 changed bytes: CHR $04 3,723, CHR $15 3,805, bank 1 734 (278 map $24, 456 planes), fixed 13 (all in
  `$F8C0-$F8CE`). No other PRG bank and no header byte changed. Claimed bytes: 8,192 + 304 + 16 + 460 = 8,972;
  4 + 460 = 464 regions. 223 tile pairs (119 animated), CHR ids ≥223 blank in both banks, 115 metatiles.
- 105 protected ids (maps $2A/$33), 151 free, overlap 0. The VICTORY and split-screen decodes are identical.
  No other set-table entry aliases the set-$15 planes, and no map entry overlaps `$8DF0-$8F1F`.
- Palette loader (`$C1A4` reads `$FFF0+(r>>6)`, 16-bit wrap): only record $0E covers `$F8C0-$F8CF`.
- Frame digests equal the pinned `RENDER_PIXELS` (a `f6a3a5c1…`, b `fd3c0581…`).
- Every placement's visible opaque part pixels equal the registered part PNG in every listed frame: 0
  mismatches across 20 placements. Pair 1,621/1,621 and batter 803/803 pixels are identical a↔b. No
  background pixel 4-adjacent to either figure changes between frames. The batter's whole box is static; the
  pair box has 67 changing transparent pixels at y 150–151 (crowd behind). Moving: cheer 562, crowd 5,895,
  marquee 4,375, pennants 9+9. Nothing changes outside sky/marquee/crowd/cheer.
- Executable bytes: the only byte-aligned control transfers into the rewritten PRG data come from data or
  misaligned decodes. `$D02F` maps bank 6 first and `$FCDF` maps bank 11 (`probe_exec*.out`).
- Full suite on the original freeze: `PASS (19 sections, 1257.4s)` (`suite-full.log`). It ran with
  `--pxl --fixtures <copied validated cache> --jobs 2`, and its code loaded at 14:18, before root's first
  edit. This includes 512 scoring, 64 tail, 128 suppression, 384 exit, 112 game-over and 2 HUD contracts, all
  equal to stock and the RAM-derived oracle; all 6 contract and 5 replay negative controls bite; the natural
  WATCH game from RESET; 15 played and planted replays (milestones to the cycle, RAM/WRAM/APU/queue/mapper
  equal, debits match); the 32-team sweep; 3 touched plays; 6 vblank phases × natural and grand slam; and
  earlier screens.
- Pitcher debits: `plant_runners` writes `$056D-$056F = 0` (probe:83-88). `capture` checks all 32 bytes
  `$0793-$07B2` at the first scene-5/state-3 frame (probe:103-106). `test_homerunart32_probe.planted_runners`
  fails if the plant drops pitcher bytes (255 → `$0892`, outside the table). The contract matrix gives each
  slot a distinct pitcher (machine:229-231) and reads the full table (machine:236).

## Findings

### Blockers

None for the frozen ROM, art or stage logic.

### W1: case-variant paths bypass every output guard (live: still present)

- **Where:** shared helpers, unchanged since `4ed637d`: `build_stockart32.py:183 refuse_tracked`,
  `build_scoreart32.py:244 refuse_inside`, `build_draw32.py:162 refuse_aliases` (only `samefile` for existing
  files) and `build_analysisart32.py:427 output_path`. All compare path strings case-sensitively. This stage
  relies on them in `build_homerunart32.py:255-262`, `homerunart32_convert.py:334-372` and
  `probe_homerunart32.py:34-41`, and live in `homerunart32_fixtures.protect_cache`.
  `docs/homerunart32.md:56-57` claims outputs cannot alias protected inputs, caches or evidence.
- **Evidence** (disposable copy `repo/`; `exploit_case_alias.out`, `exploit_more.out`): the exact path
  `repo/art/homerunart32/new.nes` exits 2, but `REPO/art/homerunart32/new.nes` exits 0 and writes the ROM into
  tracked art. The same happens for `REPO/data/homerunart32`, `REPO/build/homerunart32-fixtures` and
  `REPO/build/homerunart32-design`. `REPO/build/vendor/claude-pxl/bin/pxl.js` **overwrote an existing
  vendored file** with the ROM, and `repo/build/VENDOR/…/new.js` was written. The converter with
  `--out REPO/build/homerunart32-design/conv` exits 0 and installs `homerunassets.json`, `parts/`, `render/`,
  `preview.png` and `provenance.json`. Probe `Outputs()` accepts
  `REPO/build/homerunart32-fixtures/probe-out` and creates it. Existing files on the protected list
  (`verify.sh`, `preview.png`) are still refused via `samefile`. **Live** (`live_cache_case.out`): the four
  exact-case cache targets are refused, and all four case variants are accepted.
- **Trigger:** `ROOT` comes from `__file__`, so a cwd or absolute path spelled `~/github/…` against
  `~/GitHub/…` mismatches. So does a one-letter case slip in any component.
- **Fix:** compare identities, not strings, once in the shared helper. Take the deepest existing ancestor of
  the output. Refuse when any ancestor `os.path.samefile`s a protected directory (ROOT/art, data, tools, docs,
  BUILD/vendor, the evidence dirs, ASSETS). Refuse when it is inside ROOT but not inside BUILD, checked by a
  samefile walk. Add case-variant and NFD/NFC cases to the CLI tests. Otherwise, qualify the doc claim.

### W2: fixture cache writer had no output guard (live: fixed for exact-case paths; overlaps Sol)

- **Where:** frozen `homerunart32_fixtures.py:183-197 save_cache` only calls `output_path` and checks for a
  symlink or non-directory. It is reached through `states():200-218` from `test_homerunart32.py --fixtures`
  (1327-1330) and `homerunart32_fixtures.py --cache`.
- **Evidence** (`exploit_more.out`): exact-case calls wrote `provenance.json` and a pickle into tracked
  `data/homerunart32/`. They also replaced the converter's registered `build/homerunart32/provenance.json`.
- **Live:** `protect_cache` runs before play and before save; exact-case protected targets are refused. Case
  variants are still open (W1).

### W3: the reader argument claims more coverage than it scans (live: unchanged except one comment)

- **Where:** frozen `homerunart32_readers.py:11-21` ("every store to the scene byte $047B and every value it can
  write") and `docs/homerunart32.md:33` ("pin and re-derive").
  - `:70-74` and `:221-222`: INC/DEC are scanned only in banks 5 and 15.
  - `:197`: only `STA/STX/STY abs` are scanned.
  - `:271-282`, `:293-295`, `:325`: CHR values are compared exactly to $04/$15.
  - `:315-317`, `:329-330`: only immediate `$C1A4` loads are checked.
- **Evidence** (`probe_readers*.out`):
  - Nine `INC $047B` sites in banks 0-4 (0:AC18 1:944B 1:96E2 1:A471 1:AC72 1:AF10 2:B999 3:AF94 4:B3F4) are
    neither scanned nor pinned. Per `$CC52`/`$CCAC`, each is the scene step of a bank-0-4 scene ($00 $06 $0A
    $0C $0E $10 $14 $18/$19), so none can run while bank-5 scene $1B is dispatched.
  - 150 indexed and 672 indirect stores can reach `$047B` by address arithmetic. One example is the sound
    queue `STA $0470,X` at `$C253`.
  - `$C11C`/`$C134` shift 5 bits into MMC1, so `#$24`/`#$84` or `#$35`/`#$95` would select CHR $04/$15
    without tripping the exact compares. The current ROM has none.
  - Table-driven CHR writers are unargued: 6:`$8FF5`, `$D025`, `$D043`, `$E0A5`, `$E943`, `$EA88`. Their
    tables hold no $04/$15 mod 32.
  - 2:`$B97C` calls `$C1A4` with A returned by the `$FF20` trampoline into bank 10. I did not resolve it
    statically.
- **Impact:** no defect in the pinned input, which `BASE_SHA256` locks; root's census complements it. The
  checks would not catch a future input that adds one of these readers.
- **Fix:** scan INC/DEC/ASL/LSR/ROL/ROR `$047B` in all 16 banks and pin the observed set with the owning
  scenes. Compare CHR values `& 0x1F`. Add reviewed lists for non-immediate `$C1A4` callers and table-driven
  CHR writers. Add mutations "INC $047B in bank 1" and "`LDA #$24; STA $25`". Say in the docstring and docs
  that indexed and indirect writes are left to the census.

### W4: `test_homerunart32.py` is a new 1,375-line file (code-quality lens; live 1,376)

It mixes independent decoders and oracles, CLI sandbox tests, job orchestration and runtime judges. Earlier
stages set the precedent (1,035–1,788 lines), so this is not blocking. A clean split:
`homerunart32_oracles.py` (`decode_panel`, `decode_call`, `frame_rows`, `verify_character`/`verify_crowd`),
`test_homerunart32_cli.py` (`checkout`, `snapshot`, `run`, `failed` and the three CLI tests), and the
orchestration plus judges.

### Nits (optional cleanup)

1. **`--verify-only` trusts an unauthenticated asset file.** `test_homerunart32.py:1259-1266` parses the
   installed `homerunassets.json` without the registry digest. `verify()` (1194-1208) takes owned plane bytes
   from that file and never checks shared screens. In `exploit_verify_only.out` and `.live.out`, moving
   metatile $01 onto VICTORY id $89 gives a VICTORY-corrupting ROM. It exits 1 with genuine assets and
   `PASS verify-only` with the edited file. Fix: load through `stage.load_assets(stage.ASSETS,
   stage.read_registry())`, and add test_static's "all live `$C5C4` screens but `$D767` decode as stock" check.
2. **Probe pixel oracle accepts either frame.** `probe_homerunart32.py:107-117` passes a capture equal to
   either frame and requires only `pixel_checks >= 2`, so CHR1 stuck at $04 passes. `docs/homerunart32.md:95`
   says "four visible cutscene frames". The CPU mutant and paired `chr` parity already cover this. Fix:
   require both frames among the captures.
3. **Probe oracles are bare `assert`s** (probe:93-122). `python -O` or `PYTHONOPTIMIZE` strips them and the
   tour still prints PASS. Use an explicit check helper.
4. **Missing-input exit codes differ.** The builder and converter exit 2. The fixtures CLI (frozen `:229`,
   read outside `try`) and the test CLI (`:1260`, `:1288`, `:1318`) exit 1 with a traceback (`exit_codes.out`).
   Live: the fixtures CLI now reads inside `states()`.
5. **Fixture provenance is self-attesting.** `load_cache` checks each pickle against a digest stored in the
   same directory, then calls `pickle.loads`. That catches corruption, not substitution. Document it as
   integrity-only, or move to a non-executable format.
6. **Sweep bound counted shown frames** (frozen `machine.py:155`), so the loop never ended if no frame showed.
   Sol's finding; I confirmed it by reading. Fixed live.
7. **`load_cache` crashed on malformed shapes** (frozen `:170-179`, `.items()` on non-dicts). Sol's finding;
   fixed live.
8. **Batch guard lives in the converter.** The probe imports `protect_outputs` from the converter (probe:16),
   and live `protect_cache` adds a third variant. One `protect_batch(...)` beside `stage.protect_output`
   would serve the converter, probe and fixtures.
9. **Same-name helpers with different contracts.** `machine.patched` takes `(offset, value)` while the test's
   `patched` takes `(bank, addr, values)`. `fixtures.snapshot` pickles a machine while the test's `snapshot`
   fingerprints a tree. The test also re-defines `sha256`.
10. **Vacuous plane hooks.** The 460 plane claims pass the input's own byte as the expected old byte
    (`build_homerunart32.py:157-160`), so `claim`'s check does nothing there; the planes digest in `DIGESTS`
    provides the safety. Make that explicit with a `claim_pinned` helper. Live: the comment is gone, the code
    is unchanged.
11. **No debit negative control.** `CONTRACT_MUTANTS` has no mutant for the pitcher-debit oracle. Add
    `"pitcher debit removed ($E40A INC -> LDA)": [(15, 0xE40A, b"\xBD")]`. The stock `INC $0793,X` is at
    fixed `$E40A`.

## Comment audit (report-only, comment-sicko lens, original freeze)

I edited nothing. 26 comment blocks would go: build 3, fixtures 1, machine 1, readers 6, suite 5, px.js 10.
**Live:** 17 are already gone in root's pass, and 9 remain.

| Comment (frozen) | Why it goes | Live |
|---|---|---|
| build:43 `# accepted analysisart32` | narration | gone |
| build:55 `# where the pinned table entries below point` | narration (MUST KILL: derive `PLANES, MAP, RECORD` from the pins) | gone |
| build:159 `# the old byte is whatever…` | excuses a vacuous hook (MUST KILL: `change_manifest` plane claims, nit 10) | gone |
| fixtures:50-51 `# name: (game, hook, frame, kind)…` | tuple shape (MUST KILL: `FIXTURES` → NamedTuple) | remains (:51) |
| machine:336 `# (half, away, home)…` | tuple shape (MUST KILL: `GAME_OVER_CASES`) | remains (:337) |
| readers:41 `# opcode -> (mnemonic, mode)` | obvious | gone |
| readers:43 `# NOP; STA/STX/STY…` | explains magic bytes (MUST KILL: `PASS_THROUGH` → derive from `OPCODES`) | remains |
| readers:45-47 | justification (MUST KILL: `REVIEWED_SCENE_STORES` 4-tuples; the `why` field is never read) | remains |
| readers:70 | hides the bank-scope gap (MUST KILL: `SCENE_STEPS`, W3) | remains |
| readers:75-77 | duplicates the Check text at 236-238 | remains |
| readers:81 `# every byte-scan entry…, reviewed` | narration | remains |
| suite:79-80 | MUST KILL: name the "240 frames later" rule (`judge_replay` uses `machine.LOADER_BUFFERS`) | remains |
| suite:84 | units in a comment (MUST KILL: rename `LEADS` → `LEAD_CYCLES`) | remains |
| suite:680 | narration | gone |
| suite:856 | misstates the tuple (3 fields named, 2-tuples stored) | gone |
| suite:1244 | narration | gone |
| px.js:7-10, 27, 42, 53, 54-55, 98, 119, 121-122, 152 | narration and banners | gone |
| px.js:111 `R U N at x 144..` | **wrong**: the code draws at x 152 (MUST KILL: derive glyph x from one constant) | gone |

Survivors: `# noqa: E731` (style-only rule); the ROM-layout constant comments in assets and machine (external
stock facts); dataclass field docs (public contract); px.js 1-6, its palette map and :103 (NES PPU and palette
constraints).

## Process incident

`exit_codes.sh` meant to show the probe refusing a wrong ROM. I passed `repo/build/vendor/claude-pxl/bin/pxl.js`,
which my own W1 exploit had just overwritten with the selected ROM bytes. The digest guard therefore passed,
and the probe drove the shared romdev server (127.0.0.1:7331) under its default session `homerunart32-events`
from about 14:30 to 14:31:40 local (first output 14:31:04). All 36 outputs stayed in `elsewhere/p/`. The result matched root's
(`PASS home-run real-core tour`: natural 3 runs, both planted slams), but I am not using it as review
evidence.

- Root's event runs finished at 14:11–14:14, so there was no session overlap.
- Root's soak uses the `verify-stock` and `verify-gameplay` sessions.
- If the soak was running then, the shared server took about 40 s of extra load; its `timeout 300` runs were
  the only exposure.
- This broke the "no emulator/romdev calls" instruction.
- Lesson: any `tools/probe_*.py` reaches romdev once its digest guard passes. For "wrong input" tests, use a
  freshly written non-ROM file.

## Evidence files (all in /tmp/ll-homerunart32-review-opus)

`ledger-start.txt`, `ledger-end.txt`, `frozen/`, `suite-full.log`, `probe_static.{py,out}`,
`probe_readers{,2,3,4}.{py,out}`, `probe_exec*.{py,out}`, `probe_ff20.out`, `readers-input.out`,
`exploit_case_alias.{sh,out}`, `exploit_more.{sh,out}`, `exploit_verify_only.{py,out,live.out}`,
`live_cache_case.{py,out}`, `exit_codes.{sh,out}`, `live-diffs-small.txt`, `live-diff-fixtures.txt`.
Disposable trees: `repo/` (original freeze; holds exploit leftovers, including the ROM-overwritten `pxl.js`)
and `repo-live/` (fixed ledger). The fixture cache was copied read-only from the implementation worktree;
its provenance, harness, environment and pickle digests all matched before use.

## Measured limits

- CPU model only. My checks are static decode and ROM-byte scans. Byte-aligned scans over-approximate code.
- I did not resolve indexed or indirect writes or the bank-10 return value.
- The full suite ran once, against the original freeze. I did not rerun it on the live tree.
- The live tree got targeted exploit probes only (`live_cache_case`, `exploit_verify_only.live`).
- No listening, hardware, PAL or second emulator. Real-core evidence belongs to root, apart from the
  accidental run disclosed above.
- Workers capped at 2. Suite wall time was 1,257 s.
