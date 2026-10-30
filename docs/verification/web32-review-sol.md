# Current32 editor adversarial review

**Verdict: one required P2 contract correction; no P0/P1 finding.** JSON can manufacture PARK's exceptional skill value on a loaded baseline that does not have it. The existing test suite explicitly endorses this behavior. Other tested admission, preservation and session paths did not produce an additional actionable failure. Comment cleanup below is optional.

Review target: `/Users/dfm/GitHub/nesdav/little-league`, working tree against `4a889a720cee7bdf8d98c9ef64bb29e92609c34e`. Binding contract: `/tmp/ll-web32-judge/report.md`; Sol's design and the implementation handoff were background. The 15-source freeze matched at entry. `docs/web32-plan.md` and later root evidence are excluded. No delegation, repository edits, git write commands, browser/preview, romdev, deployment, push or network requests were used. All review artifacts and hostile ROM copies are in this scratch directory.

## Required correction

### R1 — P2: enforce the skill exception against the loaded baseline at JSON/write boundaries

**Locations:** `web/rom.js:205` (`skillAllowed`); `web/rom.js:240` (`checkReadOnly`, notably the active-player loop at 257); `tools/test_web_rom.mjs:245` (the contrary test expectation).

The binding contract says a JSON write may preserve a source-baseline exception unchanged. ROM admission may accept raw 7 at team id 4, player slot 2, but a loaded ROM whose PARK byte is 2 must not acquire raw 7 from JSON. `skillAllowed` allows that slot/value unconditionally, and `checkReadOnly` treats the entire skill byte as freely writable. Neither import nor export checks whether an out-of-range skill equals the loaded baseline.

**Actual UI path:** `jsonInput change` → `importJsonFile` (`web/app.js:151`) → `readRosterFile` → `fitRoster` → `checkValues`/`checkReadOnly` → draft commit. `Export ROM` then calls `writeRom` with the same baseline, passes the same checks and downloads the changed byte. This uses the actual production `openRom` path and real WebCrypto, not an injected fixture profile or a console mutation of app state.

**Reproduction, demonstrated for both Preview 8 and stock16:**

1. Open the accepted source, deliberately change PARK's skill to 2, export, then open that edited ROM as a fresh session.
2. Export its JSON and set only `teams[4].players[2].attrs[5]` to 7.
3. Import the JSON. The app reports `Imported manufacture-park7.json into the open ROM.` and the draft holds 7 despite the frozen loaded baseline holding 2.
4. Export ROM. The only byte changed from the opened file is `0x108DB`, from 2 to 7.

This is a narrow write-contract violation, not an arbitrary immutable-byte bypass. The game displays the new 7 as 5 stars; severity is P2 because the exceptional source value is being newly written outside the specified JSON rule. It blocks compliance with mandatory correction 1, not ordinary ROM admission of a source that already has 7.

**Evidence:** `probe-results.json`, third probe, includes both profiles, loaded/imported values, changed offsets and the UI banner. `probes.mjs` reproduces the UI route using real files and handlers. `preview8-park2.nes` and `stock16-park2.nes` are scratch inputs only. Run:

```sh
node /tmp/ll-web32-review-sol/probes.mjs
node --test --test-timeout=60000 /tmp/ll-web32-review-sol/park-contract.test.mjs
```

The first command confirms the observed behavior. The second encodes the binding contract and currently fails **2/2** with `Missing expected exception`; `park-contract-tests.txt` records it. The repository's `tools/test_web_rom.mjs:246` currently asserts that the reopened baseline of 2 may restore 7, explaining why its green suite does not catch the discrepancy.

**Small fix:** keep the per-slot allowance in ROM admission. At the existing baseline-aware boundary used by both `fitRoster` and `writeRom`, reject an exceptional skill unless it equals that player's baseline skill. Preserve unchanged source 7, permit deliberate new values 0–4, and reject manufacturing 7 from a baseline in 0–4. Replace the contrary test expectation and check both import and direct writer rejection. No broader parser/session redesign is required.

## Executed checks and evidence

Node was `v26.7.0`. The requested command completed with **68 tests, 68 pass, zero skips/failures**:

```sh
ROSTER_ROM32=build/homerunart32.nes \
ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
TMPDIR=/tmp/ll-web32-review-sol \
node --test --test-timeout=60000 tools/test_web_rom.mjs tools/test_web_app.mjs
```

Log: `node-tests.txt`. The app suite itself uses synthetic images and a digest wrapper. My separate UI probes use accepted real ROMs and real WebCrypto without digest substitution; they still use the DOM stub, so they establish handler/state behavior only.

The bounded CPU command also passed:

```sh
TMPDIR=/tmp/ll-web32-review-sol PYTHONDONTWRITEBYTECODE=1 \
ROSTER_ROM32=build/homerunart32.nes \
.venv/bin/python -B tools/test_web32_runtime.py
```

Log: `cpu-tests.txt`. The adapter-produced export changed 4,426 bytes, all within writable bits. Original and export passed all32/both-side cache checks, 303 writes/288 addresses, canaries, low-pointer restoration and AB22 state, 480 role classifications, all 128 `$AFE2` reads and 32 `$BD30` calls. Edited high-team names reached `$7800`; unused records were skipped. The source file was read-only. No full31 soak was run or required.

Independent probes in `probes.mjs`/`probe-results.json`:

- Refused 14 immutable mutation classes through production `openRom`: NES2, cache entry, low-pointer restoration, centered-name pointer, rating-reader operand, CHR, unused high record, trailer, speed high nibble, erased low bank8, erased bank9, role byte, obsolete ratings and lineup. Four masked-but-invalid name/skill/rating cases also refused.
- Edited all 480 active players' names, both stat nibbles, speed and skill plus all 128 ratings. A separately constructed whole-image oracle matched exactly: 4,040 changed bytes, output SHA-256 `9c9802bbd4374d7f78bdc07b0ab0f32f86b3ad0116ca40ec6256ad28f51fb917`. The source hash stayed unchanged.
- Rejected 21 malformed/read-only JSON cases through real UI handlers, including null records, missing/bad shapes, fractional/null bytes, illegal text, changed read-only attrs/high speed bits/identity/unused players, wrong ids/counts and invalid JSON. Each preserved the session object, frozen baseline, source buffer, SHA/exact provenance, draft, selection and revision; no replace dialog appeared.
- Held an actual WebCrypto digest so an older ROM completed after a newer dirty-replacement prompt. The old completion did not steal the dialog or source; Keep editing retained the draft.
- Failed the latest JSON request while an older ROM read remained pending. Releasing that read did not alter the session, provenance or latest error.
- Changed the draft revision during a replacement choice and allowed the old asynchronous close event to arrive after the prompt reopened. The second prompt survived and cancellation retained both edits. This is DOM-stub evidence, not a native browser claim.
- Imported forged JSON `source` claims, then exported JSON. The export retained the actual loaded ROM filename and SHA, and the loaded baseline remained unchanged.

`independent-mask-audit.json` recomputes masks using literal offsets independently of the implementation and fixture helpers:

| Profile | Mutable positions | Mutable bits | Masked SHA-256 |
|---|---:|---:|---|
| Preview 8 | 4,448 | 33,664 | `26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586` |
| stock16 | 2,622 | 20,016 | `6f4fbd41e6a7235596aef7ce8c13877b1df96731a9a5e21ce4a04268ca176b2a` |

Both syntax checks and `git diff --check` completed without output. The existing public `/rom` handler was invoked in process with `allow_rom=False`: it returned 404 without attempting ROM discovery. Docker still copies only `web/` and `tools/serve.py`; `.dockerignore` excludes ROMs. The page's ordinary external link is the pinned Preview 8 URL. No service, socket, download, deployment or external link fetch was attempted.

## Rubric disposition

| Lens | Disposition |
|---|---|
| Correctness, boundaries, encoding | R1 is the required correction. Field-location, exact no-op/JSON round trips, counts, canonical padding, stock bounded names, readonly preservation and malformed input are covered by the real-ROM suite and independent probes above. |
| Root cause | R1 belongs in the shared baseline-aware validator, not in the UI star handler or by clamping source 7. The profile-wide ROM-admission exception and a JSON write permission are distinct rules. |
| State, concurrency, atomicity, idempotency | Reviewed ticket allocation, private candidate preparation, failed-latest/stale suppression, baseline/draft separation, revision-bound replacement, Reset/Revert and exports retaining dirty state. Additional real-crypto and late-close probes did not reproduce a session replacement failure. |
| Structural integrity and boundary placement | Profile offsets/masks/field rules stay in the adapter; UI uses the two production profiles. No alternate historical production path or live caller left on removed `parseRom`/`applyRom` was found. The exported fixture-profile reader does not create a UI upload bypass. |
| Complexity and code quality | `app.js` is 567 lines, `rom.js` 420; neither crosses the 1,000-line threshold. Profile-specific behavior is in pinned profile data; one stored-player array owns 15/20 shapes. No concrete structural regression justifies an architectural blocker or another module. |
| Verification quality | Tests exercise output bytes and transitions, with independently specified fixture offsets and opt-in real ROMs. R1's contrary expectation is a specification/test failure, not missing coverage of an untested function. CPU evidence comes from actual adapter output. Browser proof remains root's separate gate. |
| Security and provenance | Production admission pins immutable bytes, read-only fields are enforced independently of imported permissions, rendered text uses escaping/textContent, and imported provenance does not overwrite source provenance. No additional concrete upload-to-write or HTML-injection path was found. Console mutation of the exposed debug state is not an upload attack. |

No release-wide compatibility guarantee, native dialog behavior, keyboard/focus behavior, phone layout, downloaded browser bytes, deployed `/rom` response or browser WebCrypto result is claimed. Root owns those browser/deployment checks. Historical builds are intentionally outside scope. No hypothetical null/console-tampering findings or speculative refactor proposals are being counted.

## Report-only no-comments audit

Applied the requested no-comments skill and read its comment-sicko rules directly; no audit was delegated. Audited the frozen source/test/config diff and nearby comments. **Files edited: none. Comments deleted/restored: 0/0. Reruns, architect sketches, application fixes and encoding changes: none.** No scoped correctness/safety lint suppression, `@ts-ignore`/`@ts-expect-error`, protected `IMPORTANT`/`do not remove` instruction or unenforced comment-only constraint was found.

Optional deletion candidates under that strict style policy:

- `web/app.js:24`: the three-line ticket narration repeats `nextTicket`/`isStale` and the documented session contract.
- `web/app.js:41`, `web/app.js:66`, `web/app.js:566`: short helper/hook narration repeats the following code.
- `tools/test_web_app.mjs:19`: timeout rationale repeats the explicit test wrapper behavior.
- `.github/workflows/ci.yml:87`: skipped-case explanation duplicates test output and editor documentation.
- `web/styles.css:728`: the added section banner is organizational prose.

These total nine candidate comment lines across four files and are **optional style nits**, not functional blockers or grounds for restructuring. No behavior-changing `MUST KILL` target was substantiated. Keep public API contracts/typedefs, measured ROM-format offsets and skill-lookup quirks, and especially `web/app.js:505` explaining the external browser task ordering of `close`. Existing CSS banners outside the added diff are excluded. No extra permission/encoding workflow is needed for this report-only audit.

## Source integrity

Final before/after results are in `integrity-before.json`, `integrity-after.json` and `integrity-summary.json`. They cover all 15 frozen sources, both ROMs, Docker/host files and bundled roster/team metadata. Final values and any changes are recorded below after the closing hash check.

Final integrity: **15/15 frozen sources match the freeze and their entry hashes; all 23 hashed files are unchanged.**

- Preview 8 ROM: `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.
- Stock16 ROM: `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e`.
