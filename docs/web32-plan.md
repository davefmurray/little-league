# Current 32-team roster editor

The requested target is the existing roster editor at
https://little-league-production.up.railway.app/. It must load, edit and export
the accepted Preview 8 ROM without changing unrelated game bytes.

## Grounding

Input commit is `4a889a720cee7bdf8d98c9ef64bb29e92609c34e`.
Input ROM is `build/homerunart32.nes`, SHA-256
`a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.

Root reproduced the deployed failure by uploading that file through the
browser's file input. The site showed ROM READY, 16 teams, 15 player rows and
Team 01 / 16. Export was enabled. The initial page also displayed a Repo ROM
button even though the public server disables that endpoint.

The first independent investigation found that the current detector expects
team 0 in bank 8, which is empty in Preview 8. Low-team records remain in bank 4;
high-team records use bank 8. All 32 live ratings use bank 3 at $BC80. A corrected
detector alone cannot make the old export offsets safe.

Railway reports production deployment `41bfd2f5-1d83-41f8-a987-e38077b0a56b`
as successful at the input commit. Its source is this repository's main branch.
Project is `b36d7e27-f48d-48f0-a4f4-fe8bda0c6281`, service is
`17ed46cc-23fa-466a-a7d5-d92f5950c2fb`, environment is
`d5a3f8e4-463c-47c4-93dd-11fda2f21c6b`. The other same-name project has no service.

## Work and acceptance

- Ground the parser, current runtime readers and editor state before changing
  exports. Two independent design lanes compare a layout adapter and alternatives.
- Root owns deployed-browser evidence and deployment. Design lanes write only
  separate scratch directories. One implementation owner will use a worktree
  because parser, document state and editor controls share a single contract.
- Make current32 the default preview, keep stock16 support, and derive editable
  controls from the verified layout. Distinguish active players from stored data.
- Require unchanged export equality, edit footprints, export/reload and JSON
  round trips. Reject unsupported layouts and incompatible imports without
  changing the current document.
- Verify actual browser file upload, edits and downloads. Confirm representative
  exported edits reach the game's existing readers.
- Preserve Docker's static-file boundary. Link the existing release download;
  do not assume GitHub release binaries allow cross-origin JavaScript fetches.
- Review the final change, push through the established direct-main workflow,
  and verify the deployed commit and browser behavior.

At the design kickoff, production files were unchanged and synthesis was
pending. The configured Grok lane is unavailable; Opus and Sol are the two
available design lanes, with the user's earlier Opus implementation choice retained.

## Selected contract

The completed design review selects Sol's adapter and stored-player model,
with Opus's exact migration for the old editor's five blank low-team records.
Recognition uses a digest with only permitted editable bits masked, followed
by value validation. Supported families are the accepted US stock ROM and
Preview 8, including compatible edits. Reader-byte checks alone admitted
mutated cache entry code and an NES2 header in the review prototype.

Each team keeps one stored-player array and an adapter-owned active count of
15. Low teams store 15, high teams store 20. High slots 16–20 are displayed as
stored but unused. Preview 8 identity stays read-only. Ratings and active
player names, skill and stat nibbles are editable. PARK's original skill byte
7 remains unchanged until the user selects a new value.

A JSON import into a ROM session retains that ROM's baseline. A new ROM or
preview establishes a new baseline. Requests and verification completion use
one ordering token so late loads cannot overwrite newer intent or edits.
Tests must exercise these transitions and the exported bytes rather than
internal helper-call order.

The host remains unchanged. Remove Repo ROM from the UI, retain external
Preview 8 download plus local upload, and keep Docker free of ROM binaries.
One implementation owner receives all coupled web files and tests in a
worktree. Root retains this decision log, deployed-browser acceptance and
publication. The finite gate is exact exports, bit-boundary and JSON/session
tests, all32 bounded CPU readers on editor output, review and browser checks.
A full tournament soak is unnecessary for this data-only editor change unless
the implementation expands the allowed write mask or reader checks fail.

## Implementation and local acceptance

The implementation patch is integrated. Real-ROM Node checks pass 70/70;
without ROM inputs the synthetic run passes 47 and explicitly skips 23.
The CPU reader checks pass after exporting edits to all 480 active players
and 128 ratings. Browser acceptance covers unchanged downloads for both
profiles, exact low/high edits, reopening exports, native replacement dialogs,
JSON baseline retention and phone-width controls. Evidence is in
`docs/verification/web32-browser.md` and the adjacent test logs.

Sol's required review correction is resolved: JSON and direct exports cannot
restore PARK's exceptional raw skill 7 when the loaded baseline has 0–4.
ROM admission still accepts the original 7. The updated suite and Sol's two
independent regression cases pass. The test export CLI also uses exclusive
creation, so existing files and symlink/hardlink aliases are not overwritten;
five scratch cases cover refusal and successful fresh output.

Both reviews are complete. Opus confirms no blocker once the PARK correction
ships. Root also resolved its smaller findings: dirty session changes always
ask even for an equal roster, legacy empty scoreboard names retain the baseline,
and startup failure displays NO ROSTER. The shared prompt checks staleness before
asking. Tests cover cancellation without losing a restoration, startup recovery,
and legacy empty names versus deliberate version-2 empties. No broad refactor was
needed for the optional comment/API nits. Deployment remains the next step.
