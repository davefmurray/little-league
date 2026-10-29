# modeart32 independent review (Opus)

## Verdict

- **ROM bytes `7624f8f8…ccbd9`: approve.** I found no runtime defect. My byte census, in-memory rebuild, disassembly of every new instruction, NMI/mapper path reading, NMI write census and an extra entry route all agree with the B contract.
- **Tooling as frozen in `build/modeart32-design/review-hashes.txt`: request changes.** The frozen converter's documented `--pxl` regeneration path writes PNG bytes through symlinks and hardlinks in `art/modeart32/out` (finding 1, reproduced). The working tree already fixes this. I verified the fix independently.
- **To publish the live tree:**
  1. Refresh the hash ledger.
  2. Rerun the full CPU suite on the live tools, with and without `--pxl`.
  3. Preferably add the palette assertion (finding 3).

  The ledger no longer matches 2 of its 8 files (finding 2). Everything else is a nit or optional.

No blockers remain in the runtime. The single real tooling defect is fixed but not yet re-gated.

## Intent

> Replace only the presentation of the main, Championship and Exhibition mode menus with the selected colorful sunny-ballpark art and people. Keep stock input, every mode exit, series state, ownership bytes and stock song 06. Use design B unchanged: identical 16-byte hop pads at `$9432` in banks 1 and 13, the bank-13 block `$9000-$9FFF`, and replacement CHR `$06`. Do not change the fixed bank, the main font, or stock input and audio. Validate malformed data before any mutation and refuse aliased outputs.

## Measured hashes (00:12, 2026-10-29)

| Item | SHA-256 | Status |
|---|---|---|
| `build/title32.nes` input | `8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c` | matches pin |
| `build/modeart32.nes` | `7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9` | on disk = in-memory rebuild = integration copy |
| `data/modeart32/modeassets.json` | `9af59518eb1d917f2705073d4351145fa73e0fd030db93f140aaaba36ad0a01f` | in-memory reconvert is byte-identical |
| art + data (16 files) | `frozen-art-data.sha256` | 16/16 OK |
| `tools/build_modeart32.py` | `81c5fe1d…` | ledger OK |
| `tools/modeart32_assets.py` | `02cb76be…` | ledger OK |
| `tools/probe_modeart32.py` | `9c8907b1…` | ledger OK |
| `tools/probe_menu_chr.py` | `db497490…` | ledger OK |
| `tools/verify.sh` | `d426c86e…` | ledger OK |
| `tools/build_32team_full.py` | `306230db…` | ledger OK |
| `tools/modeart32_convert.py` | ledger `37bddf3c…`, now **`b8d1b3cb528e27a1beafd58808c8de71939f2b61cecf69d6a36b4fa98cbfdad7`** | changed 00:04 |
| `tools/test_modeart32.py` | ledger `64317218…`, now **`2b53d74ad721635cd92f2f0f12c616c4a16302414718fb05c9385b8053b1be33`** | changed 00:05 |

I reviewed the ledger versions, reconstructed byte-exact from `modeart32-tools.patch` into `frozen/`. I also reviewed the live delta, snapshotted with diffs in `live-snapshot/`.

## Findings

### 1. [warning, frozen scope; fixed in live tree] PNG regeneration writes through aliased art inputs

- **Location:** `tools/modeart32_convert.py` (`37bddf3c`) `render_pxl`. It runs `shutil.copyfile(temp/relative, PNGS/relative)`, reached from `main()` via `render_pxl(args.pxl, PNGS)`.
- **Problem:** `--out` and `--preview` refuse aliases, but the 12 PNG writes into `art/modeart32/out/**` had no alias check. `copyfile` opens the destination for writing, so it follows symlinks and truncates hardlinked inodes.
- **Evidence (`probes/p6_frozen_pxl_alias.log`):** I ran the frozen module against a scratch destination, using the real pinned pxl `3bc816cb` and node 26.7.0.
  - `scenes/mode.png` was a symlink and `sprites/dad.png` a hardlink, each to a scratch victim file.
  - After the render, both victims start with `\x89PNG`, so both were overwritten.
  - In the repo, the same thing happens through `art/modeart32/out` when running the documented `--pxl` regeneration command. The other reviewer reached the input ROM this way (now recorded in `docs/modeart32.md`).
- **Fix status:** Live `b8d1b3cb` adds `install_pngs`. It checks every target against `protected_paths`, the source, layout, lock, assets, outputs and sibling targets before any copy, then writes a sibling temp file and calls `os.replace`.
- **My recheck (`probes/p7_live_pxl_alias.log`):**
  - Unprotected symlink and hardlink: the links are replaced and the victims stay intact.
  - Symlink to the protected `art/title32/out/scenes/title.png`: refused before any write, and the repo file is unchanged.
- **Suggestion:** Keep the fix and gate it (finding 2). One live nit: `test_modeart32.py:198` passes `builder.ROOT / "build/title32.nes"` to `check_pxl` instead of the CLI ROM path, so a ROM at any other path makes `--pxl` fail on `read_bytes`. Thread `args.rom` through instead.

### 2. [warning, process] The hash ledger and every CPU log predate the live tool changes

- **Location:** `build/modeart32-design/review-hashes.txt`, written 23:48. The two tools changed at 00:04 and 00:05.
- **Problem:**
  - `shasum -c` now fails for 2 of 8 files.
  - `final-art-pxl.log`, `final-art-verify.log` and the gate's CPU section were produced by the old converter and test.
  - The new `test_png_regeneration` has no recorded PASS in the evidence I could inspect. `docs/modeart32.md` itself says "corrected CPU suite … still in progress".
  - The ROM bytes are unaffected: the change is converter-only, and I measured `7624f8f8` after it.
- **Suggestion:**
  1. Regenerate the ledger.
  2. Rerun `test_modeart32.py build/title32.nes --candidate build/modeart32.nes` with and without `--pxl build/vendor/claude-pxl`.
  3. Record both PASS logs before publication.

### 3. [warning, verification gap] The real-core tour never checks palette RAM, so the cursor and background palette are only model-proven on the core

- **Location:** `tools/probe_modeart32.py:26-41` (`check_view`). It checks nametables, mapped CHR, OAM, song and guards, but not the palette.
- **Evidence:**
  - The cursor's colors come from sprite palette 0 in the bank-13 palette, which the NMI uploads via `$01B5`.
  - On the real core this is shown only by screenshots. The CPU model checks it (`check_view`: `m.palette32() == assets.palette`).
  - romdev exposes `nes_palette` (32 bytes), already used by `tools/render_ppu.py:59`.
  - In my mutation probe, removing `INC $01B5` or changing one sprite-palette color fails first on the model's palette assertion; the composed-frame comparison would also differ. The real-core probe checks neither.
- **Suggestion:** Add `assert memory('nes_palette', 0, 32) == assets.palette` to `check_view`, normalizing `$3F10/14/18/1C` mirrors if romdev returns raw RAM. Rerun the ui tour.

### 4. [warning/nit, evidence provenance] Both committed mapper reports came from the pre-edit tracer

- **Location:** `docs/verification/modeart32-menu-mapper.json` (23:44:47) and `modeart32-1p-mapper.json` (started before the 23:48 edit).
- **Evidence:**
  - Neither file has the `command` or `rom_sha256` keys the current `probe_menu_chr.py:127` writes.
  - Their `limit` text is the old one. It omits that `audioDebug` advancement is untraced, and `probe_modeart32.py:78` advances 180 untraced frames.
  - The contents themselves support the claims. Every PRG `$0D` selection (73 in the menu tour, 20 in 1P) and every CHR1 `$06` selection falls in windows touching scene 6 or 7. The `13>06` and `19>07` windows are draw re-entries.
- **Suggestion:** Re-trace with the final tracer so the evidence carries the ROM hash and the accurate limit, or note the format gap in `docs/modeart32.md`.

### 5. [nit] The printed static-census claim is broader than what it checks

- **Location:** `test_modeart32.py` `test_builder` (frozen ~591-607), which prints "static census: only the pads map bank 13 and only bank-13 code selects CHR $06".
- **Evidence:**
  - The test matches only `A9 0D 20 4E C1`, `A9 06 85 25` and `A9 06 20 34 C1`.
  - My wider immediate scan agrees: LDA/LDX/LDY `#$0D` near `$C14E`/`$C150`/`$27`, and `#$06` near `$23-$26`/`$C11C`/`$C134`. Each pattern appears only at the pads and bank-13 `$947C`, with none in title32 (`probes/p3_census.log`).
  - Computed selections (tables, `$27` restores) are covered only by the runtime mapper tours.
- **Suggestion:** Print "the immediate bank-13 and CHR-$06 selection patterns occur only in the new code". `docs/modeart32.md` already phrases this correctly.

### 6. [consider] Add the bracket LIST exit to the entry matrix

- **Location:** `test_entries`. A live series + Championship → LIST OF TEAMS goes `$9511 → $FEA0`, which writes `$2000=0` and maps bank 11. A or B exits at bank 11 `$86C7` and re-enters scene 6. Neither the CPU entry matrix nor the real-core ui tour covers this.
- **Evidence (`probes/p8_bracket_route.log`):** I ran this route in the model. With both A and B exits, stock and candidate match on scene sequence `0,1,6,7,6,7`, mode/ownership bytes, sounds and series. The candidate lands on the exact main menu: VRAM, palette, CHR 06/1B, ball and composed frame. No late VRAM writes.
- **Suggestion:** It passes, so this is coverage, not a bug. It costs about 10 s per exit.

### 7. [nit] The draw's `STA $32` (drop a stale display list) is untested

- **Evidence (`probes/p5_mutations.log`):** I NOP'd bank 13 `$9459` (`85 32`) and neither the suite's `tour` nor `test_entries` detected it. The other draw instructions I mutated are caught:
  - `STA $23` → CHR `$06/$12`
  - `INC $01B5` → palette
  - `JSR $C260` → late VRAM writes
  - swapped list pointers → Championship VRAM
  - sprite-palette edit → palette
- **Why it matters:** The store matters only if an entry route arrives with a non-empty `$0300` list. `$2C` holds the flush during the upload, and the next NMI would then paint stale tiles over the new screen. It mirrors stock `$C5C4`.
- **Suggestion:** Add one entry case that plants `$32≠0` with a stale run before scene 6, or accept it as stock parity.

### 8. [nit] Two rejection reasons aren't pinned, and one message names the wrong CHR bank

- **Converter tile-budget case:** `test_converter` uses `rejects(converted, base)`, which accepts any error. The printed claim is "26 … each for its own reason". The actual message is "CHR bank $19 is full at mode:0,29", because `menu32_convert.CHR_BANK = 0x19` while this art goes to CHR `$06` (`probes/p2_rebuild.log`). With 2 free tiles left, the next art edit will likely hit this misleading message. `title32_convert` has the same pre-existing behavior.
- **Asset case "terminator inside a run":** the expected reason is `""`. The actual error is "flags/address byte $53 is not a narrow raw run" (`probes/p9_boundary_reasons.log`). All 54 cases are rejected at load, so the claim holds.
- **Suggestion:** Pin both reasons. Give `TileBank` an optional bank number for its message.

### 9. [nit, code quality] A test-only helper backs a tautological assertion

- **Location:** `build_modeart32.labels()` exists only for `test_modeart32.py` (frozen ~567, live 632): `assert labels == builder.labels()`.
- **Why it's tautological:** the test computes `labels` from the same `assemble(builder.far_asm(), builder.CODE)`, so the comparison is always true. The meaningful check, `request == CODE`, is already enforced in `far_block`.
- **Suggestion:** Delete both.

### 10. [nit] `probe_menu_chr.py:117-119` mishandles `--rom` edge cases

- `--rom` as the last argument raises `IndexError` before the probe runs.
- `--rom=PATH` silently records `rom_sha256: null`.
- **Suggestion:** Parse with `argparse.parse_known_args`, or fail loudly when the ROM can't be found.

### 11. [nit, code quality] Smaller structure points

- `modeart32_convert.ModeArtwork` uses `dict`/`tuple` fields with explanatory trailing comments (lines 81-86). Precise annotations would remove the comments: `dict[str, tuple[Text, ...]]`, `tuple[int, int]`.
- `contract_run` swaps `m.__class__ = Contract` on a live Boot. Letting `Driver` take a machine class would be more direct, but it's shared code, so this is optional.
- `pad_trace` and `test_overlays` repeat the same direct-call machine setup.

The 1,175/1,240-line test file is a cohesive gate with clear functional sections. I see no actionable split.

### 12. [nit, docs] The plan doc opens with the superseded request

`docs/modeart32-plan.md` starts by stating the request as navy, cream and gold, and still says "Opus's independent candidate remains pending". Later sections supersede both. As a chronological log this is defensible, but a one-line "superseded by the sunny-ballpark selection below" would prevent misreading.

## Checked and found sound (independent evidence)

- **Byte ownership (`probes/p1_diff.log`):**
  - Exactly 4,652 changed bytes, all inside the 7 regions:
    - bank 1: 31 + 5 + 5 + 5 + 18 = 64 bytes
    - bank 13: 1,333 bytes
    - CHR `$06`: 3,255 bytes
  - Only PRG 1, PRG 13 and CHR `$06` differ, and the header is equal.
  - Bank 13 outside `$9000-$9FFF` is all `$FF`, and the base bank 13 is all `$FF`.
  - The bank-13 layout, re-derived from the JSON without the builder, matches byte for byte: screen, palette, pads, list table `$9506/$9541/$957C`, three 59-byte lists, and `$FF` elsewhere.
  - Stock CHR06 digest `c639380f…` confirmed.
- **Call contract (disassembly):**
  - Bank-1 `$942A` is `LDA #0; JSR $9432; JMP $944B`.
  - The text calls match: `$9464` → 1, `$948F` → 2, `$9484` → 3, consistent with jump table `$947E` (`$948F/$9484/$949D`).
  - The pads are byte-identical.
  - Bank-13 `request` is `TAX/BEQ` → lists via `$94FF,X`/`$9502,X`, then `JMP $C863`.
  - Each caller's continuation (`$944B`, `$9469`, `$9489`, `$9494`) reloads A and ignores X, Y and flags. The stack is 2 bytes deeper than stock.
- **NMI, mapper and PPU safety:**
  - The NMI short path (`$2C≠0`) runs audio only, with no `$2002` read or PPU access. Audio maps bank 0 via `$C150` and restores via `$C14C` from `$27`, which `$C14E` writes before its serial writes.
  - `$CE45` skips CHR writes while `$2D` is held.
  - `$C713` saves and restores the bank through `$2E`, so the walker re-reads lists in bank 13.
  - No NMI subroutine (`$C274…`, `$CE45-$CF58`, `$CD85-$CDF4`) references `$8000-$BFFF`, so NMIs while bank 13 is mapped are safe. The IRQ/BRK vector is the RTI at `$CDF4`.
  - In the model (`probes/p4_nmi_census.log`):
    - NMIs during requests never write `$00/$01`, `$AA/$AB`, `$2E`, `$AC` or `$06B3-$06D5`.
    - All 4 natural draw-time NMIs land in `$C260`'s poll with `$2C=1`.
    - All 12 text-request NMIs run the normal path with bank 13 mapped.
- **Static reachability:**
  - The fixed-bank `JSR $9431` sites at `$D7A5`/`$D9AA` map bank 6 first, so they don't touch bank 1's new bytes.
  - Apart from those two bank-6 calls and the pad's own bank-1 copy of `JSR $9442` (never executed in bank 1), no JSR/JMP targets the replaced bank-1 interiors. Bank 2 and bank 6 hits target their own banks.
  - The stock lists `$95F6/$9637/$9662` are now unreferenced (`probes/p3_census.log`).
- **Asset boundary (`probes/p2_rebuild.log`, `probes/p9_boundary_reasons.log`):**
  - 15 extra malformed records are rejected with `AssetError` and none crash. They include type confusion, floats, bools, negative spans, empty or list runs, sprite backdrop mismatch, and `$FE`/`$FF` nametable tiles.
  - Two variants were accepted, both valid by design: `$1F` is a supported color, and the JSON deliberately does not tie the cursor to label cells (the test's layout oracle does).
  - All 54 suite cases reject at load. Production modules use explicit errors, with no `assert`.
- **Rebuild:** The in-memory build equals the frozen ROM, and the in-memory convert equals the committed JSON.
- **Art:** The ROM preview (`preview-from-frozen-rom.png`) shows the sunny ballpark: sky, scoreboard with three single-row labels, brick concourse with families, players, vendor and grass. The ball sits 4 px left of each label without overlapping it.
- **Mapper reports:** The contexts are documented as ≤40-frame before/after windows, and `docs/modeart32.md` doesn't overclaim exact event scenes.

## Report-only comment audit

I recommend no comment-only edits. Line numbers are from the ledger (frozen) files.

- `modeart32_assets.py:47-50`: four constant comments (`MAX_RUN`, `RAW`, terminators, `CURSOR_X_MAX`). They explain hardware constraints. Keep them.
- `modeart32_convert.py:81-86`: six dataclass field comments. These compensate for loose types; encode them as annotations (finding 11).
- `build_modeart32.py`: none. The module docstring carries the contract, and it matches the bytes and the test `CONTRACT` set.
- `test_modeart32.py`: seven section banners. They are neutral navigation in a long cohesive gate.
  - `:537` "stale copy of the stock fixed bank" could become a named constant.
  - `:772` "the $A5BF exit's store" should say that it emulates the password EXIT path.
- `probe_modeart32.py`, the `probe_menu_chr.py` diff and the live delta: none.
- Docstring accuracy:
  - `modeart32_assets` says "nothing downstream checks again". The builder still runs ROM-context checks (font vs CHR `$00`, bank-13 space), so this is slightly overstated.
  - `modeart32_convert` says TileBank enforces "the 256-tile budget of CHR bank $06", but its error text names `$19` (finding 8).

## Limitations

- **CPU model only.** I made no romdev or emulator calls and edited nothing in the repo. Timing, NMI placement and vblank figures come from `render_menu32.Machine`, not hardware.
- **No gate claims.** I did not poll or rely on the running gate or full Exhibition logs. `docs/modeart32.md` now states a gate PASS, which I have not verified.
- **Not rerun by me:** the full 314 s suite. I relied on the root's logs for its sections and reran only targeted pieces (`tour`, `test_entries`, boundary cases).
- **Live tree moving.** The working tree changed during review: two tools, `docs/modeart32.md` and `docs/modeart32-plan.md`. Live-tree conclusions are as of 00:12. I did not review the newer docs or verification files beyond the excerpt quoted.
- **Hardlinks:** to avoid touching repo inodes, I made hardlinks only between scratch files. Repo files were targeted by symlink only, against the live (non-writing-through) code.

## Artifacts

All under `/tmp/ll-modeart32-review-opus/`:

- this report
- `probes/p1…p10*.py` with `.log`
- `frozen/tools/` (ledger versions)
- `live-snapshot/` (00:05 versions plus diffs)
- `preview-from-frozen-rom.png`

Run every probe with `.venv/bin/python -I -B` from the scratch dir.
