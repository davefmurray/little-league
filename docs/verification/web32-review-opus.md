# Adversarial review: current32 roster editor (frozen handoff 95456007)

Reviewer: Opus lane. Scope: the 15 sources in `build/web32-acceptance/review-freeze.json`, against base `4a889a7`, judged against `/tmp/ll-web32-judge/report.md`. No subagents, repository writes, git writes, browser, romdev, deploy or network use. All writes are under `/tmp/ll-web32-review-opus`.

## Verdict

No blocking defect remains in the frozen implementation, provided root's post-freeze PARK fix ships. Byte admission, the diff-only writer, read-only enforcement, JSON validation, the legacy padding migration and the async session rules all hold under independent probes.

- **One Medium contract deviation in the frozen code:** JSON can re-create PARK's skill 7 over an edited baseline (F1). Root fixed this at 18:02 after the freeze. I checked that fix by reading its diff only.
- **One Low tooling hazard in the frozen helper:** `web32_export.mjs` can overwrite its own source ROM (F5). Root fixed this at 18:08.
- **Everything else is Low or optional:** F2 to F4, F6 and the maintainability notes.

## Source integrity

| Check | Result |
|---|---|
| Freeze hashes at review start (17:55) | 15/15 match |
| Freeze hashes at review end | **10/15 match; 5 drifted** |
| Drift, by another actor, not this lane | 18:02:08: `web/rom.js`, `tools/test_web_rom.mjs`, `docs/editor32.md`, `docs/rom-distribution.md`. 18:08: `tools/web32_export.mjs`, and `docs/editor32.md` again |
| Reviewed content | Scratch snapshot `/tmp/ll-web32-review-opus/tree`, extracted from handoff commit `95456007` with `git archive` (a read-only command). 15/15 freeze hashes match |
| `build/homerunart32.nes` | `a66add03…2993b`, mtime unchanged (Oct 30 15:15) |
| Stock ROM | `58e038f1…481e`, mtime unchanged (Oct 18) |
| Repo file listing, before vs after | Differs only by root's new `build/web32-acceptance/browser-*`, `node-synthetic.txt`, `readonly-invalid.json` and `docs/verification/web32-*` files. Nothing came from this lane. No new `__pycache__` |

Current root hashes are in `freeze-after.txt`. Hostile writes used only `/tmp/ll-web32-review-opus/hostile/victim.nes`, a writable scratch copy. `roms/*.nes` are read-only copies.

## Findings

### F1. Medium, contract deviation (frozen). Fixed in root post-freeze.

JSON and `writeRom` can set PARK's skill to 7 when the loaded baseline holds 0–4.

- **Location:** `web/rom.js:205` `skillAllowed` allows 7 at team 4, slot 2 without reference to the baseline. `checkReadOnly` (`:241`) has no skill rule. The frozen test `tools/test_web_rom.mjs:247` asserts this behavior as intended ("a file may restore the source value").
- **Repro (frozen):** open the original, set PARK's skill to 2, export, reopen the export, then `fitRoster(readRosterFile(rosterJson(profile, originalTeams)), reopened.teams)`. It accepts, and `writeRom` writes 7.
- **Contract:** mandatory correction 1 says "a JSON write may preserve a source-baseline exception unchanged, but must not manufacture other out-of-range values." Root reads this as forbidding re-creation, and so do I.
- **Status:** at 18:02 root added `if (player.attrs[5] > 4 && player.attrs[5] !== before.attrs[5]) fail(...)` to `checkReadOnly`. That fix is correct: `checkValues` runs first in both `fitRoster` and `writeRom`, so only PARK's 7 can reach the rule. One accepted consequence: on an edited copy where PARK's skill changed, importing the original's JSON is refused. Revert and reopening the original still work.

### F2. Low, optional. A dirty ROM session is replaced with no prompt when the draft equals the new target.

- **Location:** `web/app.js:68`. The `mayReplace` loop condition `!sameTeams(draft, state.teams)` skips the prompt even when the session itself changes (`showPreview`, `:119`).
- **Repro (DOM stub, `probes/p5_races.mjs`):**
  1. Open an edited Preview 8 copy whose player 1 name differs from the original.
  2. Type the original name back. The chip reads `Preview 8 · EDITED ROM · UNSAVED`.
  3. Choose Data → Preview 8 roster. There is no prompt, and the chip becomes `Preview 8 · ROSTER ONLY`. The open ROM and the unsaved change against it are gone.
  4. Reopening that ROM replaces the draft with no prompt, because the session is now clean. The edit is lost across two prompt-free steps.
- **Contract:** judge item 6 and the design both require a Keep editing / Replace choice when there are unsaved edits.
- **Fix:** skip the prompt for equal content only when importing into the same session. Prompt on any new session while `isDirty()`. Rare in practice, because the whole draft must equal the target.

### F3. Low, optional. A v1 16-team `short_name: ""` blanks scoreboard names; the CLI treats `""` as keep.

- **Location:** `web/rom.js:336` accepts an explicit `""`. `fitRoster` (`:373`) keeps the baseline only for `undefined`. By contrast, `tools/roster.py:233` (`if team.get("short_name")`) skips `""`. The old editor turned a missing short name into `""` (old `app.js:39`, `String(raw.shortName ?? raw.short_name ?? '')`).
- **Repro (`probes/p4_json.mjs`):** a v1 stock file with `short_name: ""` on every team is accepted. Export then writes spaces over all 16 scoreboard names. The same file applied with `tools/roster.py apply` leaves them unchanged.
- **Contract:** "missing stock short-name data must never become an empty-string write." The literal missing case is handled correctly. This is the laundered case.
- **Fix:** for legacy files, treat `""` as missing, or refuse empty scoreboard names.

### F4. Low, optional UX. After a failed boot the chip stays at `LOADING`.

- **Location:** `web/app.js:246` together with the `showPreview` catch at `:126–128`.
- **Repro (stub):** make `teams32.json` return 404. The banner says the Preview 8 roster failed to load, but the chip still reads `LOADING` indefinitely. Open ROM and Import still work.
- **Fix:** show an error or empty state in the chip when no session exists and the latest load failed.

### F5. Low, tooling hazard (frozen). Fixed in root at 18:08.

`tools/web32_export.mjs:30` writes its output with no existence check. Running `node tools/web32_export.mjs X X` replaces X with an edited copy.

- **Repro (scratch copy):** `hostile/victim.nes` went from `a66add03…` to `b4bf5182…`, with 4,426 bytes changed. The CPU runner itself writes into a temporary directory, so the normal path was always safe. A manual run with a typo could clobber `build/homerunart32.nes`.
- **Status:** root's `{ flag: 'wx' }` refuses any existing output, which covers this. I found this hazard by verifying root's diff, not independently.

### F6. Informational, contract-intended. Old-editor names with punctuation are now refused.

The old editor accepted printable ASCII 0x20–0x7E (old `app.js:29–31`). An old stock export with a name like `J.R.` no longer opens: "Team 1 (JAPAN), player 1: names are up to 6 letters, digits or spaces." Old v1 JSON files with such names are refused the same way (`probes/p6_oldnames.mjs`).

This matches the contract's `A-Z 0-9 space` set, and the message is clear. The user cannot repair such a file in the editor. If the font actually renders punctuation, the owner may want a CLI recovery note. I did not check font coverage.

## Contract checks with no finding

Each row was checked against executed evidence, not by reading alone.

| Area | Evidence |
|---|---|
| Masked-digest admission | `probes/p1_mask.mjs` captures the exact array `readRom` hashes and recovers the production mask from it. That mask equals my contract-derived mask bit for bit: Preview 8 has 4,448 positions and 33,664 bits, stock has 2,622 and 20,016. Both pinned digests and both original SHAs reproduce. This rules out an over-broad mask hiding behind zero bits in the original. |
| Refusals | `probes/p2_admission.mjs` ran 16,820 single-bit flips outside the mask and admitted none. They covered all 128 header bits, random PRG and CHR bytes, and every unmasked bit of sampled active and stored records and trailers. Exhaustive 0–255 sweeps at 22 masked positions admit exactly the legal set: names, byte 9, skill (PARK 0–4 or 7; elsewhere 0–4), ratings 1–4 and stock text. Speed is refused unless its high nibble is unchanged. Empty, header-only, wrong-size, appended, DiskDude, mirroring and battery inputs are refused. |
| Writer | `probes/p3_writer.mjs`: 240 random drafts, up to 400 edits each, match an independent writer byte for byte. Each reopens as its draft. Restoring the original roster onto any edited copy returns the exact original SHA. Re-export is idempotent, and source buffers never change. |
| UI write paths | Stored rows render no controls. `onEditorInput` gates on `p < ACTIVE_PLAYERS`. Preview 8 identity inputs are ignored through `textField(...).editable`. A skill click on the shown value is a no-op, and picks store 0–4. |
| JSON | `probes/p4_json.mjs`: 68 hostile and edge cases, 0 failures. Refusals are atomic, nothing is clamped, inputs are never mutated, permission claims are ignored, and cross-profile files are refused. The padding migration drops exactly the empty-name, ten-zero records and counts them. Version 2 files get no migration. |
| Async sessions | Every load and import takes a ticket, and stale errors are suppressed. A failed newest load keeps the prior session. A prompt is tied to its ticket and revision. A late `close` event is ignored while the dialog is open, which matches the HTML spec: the close event is queued as a task. Extra stub scenarios also pass: a stale failing import, a cross-profile import superseded mid-fetch, and an export in flight across a session switch, which downloads the snapshot taken at click time. |
| Exports and provenance | Version 2 files carry `profile` and `source{name, sha256}`. The chip separates ORIGINAL and EDITED. Downloads never mark the draft clean. |
| CPU readers | The CPU helper on the frozen tree passes. The export changes 4,426 bytes, all inside the mask. The roster cache and roles pass for all 32 teams on both sides. All 128 `$AFE2` reads and 32 `$BD30` calls see the live table. Edited names reach `$7800`, and records 16–20 are skipped. Output: `cpu-frozen.txt`. |
| Suites (frozen tree) | With real ROMs: 68/68. Without: 45 pass, 23 skipped. Node 26.7.0. CI pins Node 20, and versions from 20.19 on detect ESM syntax. |
| Hosting | The Dockerfile is unchanged, `web/` contains no `.nes`, Repo ROM is gone, and the link points to the pinned release asset. Asserted by test and confirmed by reading. |
| Security | `innerHTML` interpolates only validated numbers and `esc()`'d names. File names reach the page through `textContent` and attributes only. The ROM is never fetched. |

## Maintainability (proportionate)

No file crosses 1,000 lines: `rom.js` is 420 and `app.js` is 567. The two profiles are plain data, no premature abstraction was added, and no special cases leak into shared paths. The 296-line DOM stub is justified by the repository's zero-dependency policy.

- **M1, optional hardening with a concrete hazard.** `mayReplace` does not check staleness before prompting. It relies on each caller running `if (isStale(t)) return;` immediately before the call (`app.js:118`, `:137`, `:170`). If any await is added between that check and the call, the stale-load-steals-the-dialog bug that the handoff's mutation run found comes back. Fix: add `if (isStale(t)) return false;` inside `mayReplace` before each `askReplace`.
- **M2, nit.** `writeRom(source, profile, baseline, teams)` requires the baseline to be what `source` opened as, and only prose says so (`rom.js:266–269`). The read-back check makes a mismatch fail closed. Passing the opened-ROM object would encode the rule.
- **M3, nit.** `ATTR_BITS` (`rom.js:29`) is a positional array, and `app.js` uses bare `attrs[3]` through `attrs[6]` plus hole destructuring. Shared named indices would remove the explaining comments.
- **M4, nit.** `sameTeams` (`rom.js:89`) compares with `JSON.stringify`, so it depends on key order, and it is also used for `attrs` arrays despite its name. This is fail-closed today because every constructor emits keys in the same order.

## Comment audit (report only, comment-sicko standard, done in this lane)

There are about 41 comment blocks in scope.

**Keep (11):**

- The 7 exported-API JSDoc blocks in `rom.js`: `openRom`, `readRom`, `writeRom`, `readRosterFile`, `fitRoster`, `previewRoster`, `rosterJson`.
- `skillStars` (`rom.js:91`), which documents the game's `12345555` lookup, an external constraint.
- The dialog note at `app.js:505–506`, about platform timing that is true today.
- The no-ROM-in-CI note in `ci.yml`, which is a policy constraint.
- The `styles.css` section banner, which matches the file's existing convention.

**Delete as narration:** everything else. That includes the `rom.js` module-header admission narrative, which duplicates `docs/editor32.md`. Keep its "Team shape" paragraph as a `@typedef`. Also delete `:103`, `:121`, `:210`, `:240`, the typedef narration and `:41`, `:66`, `:566` in `app.js`, the headers and helper JSDoc in the test, fixture and stub files, the `web32_export.mjs` usage header (the script prints its own usage), and the runtime docstring.

**MUST KILL, reshape so the comment is unnecessary:**

| Location | Reshape |
|---|---|
| `rom.js:29` `ATTR_BITS` | Named attribute indices (see M3) |
| `rom.js:32` `prg` | `prgOffset` |
| `rom.js:35` `STOCK_SHORT` tuples | Named fields |
| `rom.js:104` `canonical` | `trimPadding` |
| `rom.js:266` `writeRom` precondition | See M2 |
| `app.js:24–27` ticket convention | See M1 |
| `app.js:16–20` `revision` prose | Rename |
| `app.js:42` `clean` | `toGameText` |
| `app.js:447` | Named predicate for the shown-value no-op |
| `test_web_app.mjs:1–5` SWAP crypto wrapper | Named wrapper |

**Unenforced constraint:** the `web_fixtures.mjs` header says its offsets are written "independently of web/rom.js". The cheapest encoding is a test that fails if the fixture's offset functions come from `rom.js`. Reported open. No edits were made.

## Evidence index (`/tmp/ll-web32-review-opus`)

- **Integrity:** `freeze-before.txt`, `freeze-after.txt`, `roms-before.txt`, `tree-before.txt`, `tree-after.txt`
- **Frozen snapshot:** `frozen/` (15 files) and `tree/` (the full commit)
- **Suite runs:** `node-frozen-real.txt`, `node-frozen-synth.txt`, and `node-real.txt` (root tree at start)
- **CPU check:** `cpu-frozen.txt`
- **Probes:** `probes/p1_mask.mjs` through `probes/p6_oldnames.mjs`, with outputs `p1_mask.out` through `p6_oldnames.out`
- **Reproduce one probe:** `TREE=/tmp/ll-web32-review-opus/tree R32=roms/p8.nes R16=roms/us16.nes node probes/p1_mask.mjs`, run from this directory

## Limits

- No browser, deploy or emulator was used. DOM-stub results show wiring and state transitions, not browser behavior.
- Root's post-freeze tree was not re-reviewed beyond the diffs quoted above.
- Font coverage for punctuation (F6) was not checked.
