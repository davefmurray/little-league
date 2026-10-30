# HOME RUN implementation review resolution

Both independent reviews reproduced the selected ROM and found no ROM or art
defect. Opus completed all 19 CPU sections on the original freeze. Sol completed
the static/CLI sections and targeted CPU contracts, then stopped its duplicate
full run to reduce contention. Neither result is presented as a full rerun of
root's subsequent tool fixes.

The input remains `1e524b53…` and the output remains `a66add03…`. Source-comment
cleanup changes the pxl source and provenance digests, with identical images
and ROM bytes. Root retains the original review and intermediate fixed ledgers
under `build/homerunart32-design/`.

## Findings acted on

| Finding | Resolution and evidence |
|---|---|
| Fixture writes could overwrite the input or unrelated provenance. Both reviewers. | The cache boundary now receives input paths, validates the complete output batch before generation and before writing, and permits only owned entries. Links, foreign files and unrelated provenance are preserved. Root reproduced the original failure in scratch. |
| Sweep timeout counted visible frames. Sol and Opus. | The timeout now counts elapsed machine frames. A deterministic invisible-cutscene regression stops at 3,001 frames rather than needing an external sentinel. |
| Malformed cache record types raised raw exceptions. Both reviewers. | Loading treats malformed shapes as misses. Writing refuses malformed ownership records rather than replacing unidentified evidence; the caller can choose a fresh directory. |
| Case/Unicode aliases bypassed directory protection. Opus. | Shared directory checks now compare existing filesystem identities. Missing protected roots reserve normalized spellings. Forty case/Unicode tests cover the builder, converter, probe and cache on this disk, with unchanged disposable input trees. |
| Verify-only trusted an unchecked installed asset. Opus. | It checks the registry digest and the builder's shared-screen postconditions. A crafted ROM that moves HOME RUN metatiles onto VICTORY is rejected with either genuine or tampered assets. |
| The event probe could accept a single animation phase or optimized-away checks. Opus. | It requires at least four exact screenshots covering both frames. Explicit checks remain active under `python -O`; regressions reject a missing phase and too few captures. |
| Pitcher-debit oracle lacked a mutation control. Opus. | Removing fixed `$E40A`'s debit instruction fails the independent rules even when the mutated result is compared with itself. The control is part of the full suite. |
| Reader coverage was overstated. Opus. | The module and stage document now identify the reviewed direct chains and the scans' omissions. The whole-input SHA remains mandatory. A new input pin requires a new ownership audit, not merely passing the existing scans. |

Completed focused evidence is in
[failure reproductions](homerunart32-review-reproduction.txt),
[case-alias reproduction](homerunart32-case-reproduction.txt),
[safety regressions](homerunart32-safety.txt),
[pitcher-debit mutation](homerunart32-debit-control.txt), and
[unchanged-art regeneration](homerunart32-comment-regeneration.txt).
The integrated gate and stricter paired event rerun are separate root-owned
checks; their completion is recorded in the stage document.

## Considered or deferred

The 1,375-line acceptance suite is organized into separate test sections with
production code already split into smaller modules. A broad test-file split is
deferred; it would not change the selected ROM or close a correctness gap.
Similar helper names across test contexts are also nonblocking.

Local fixture pickle digests establish integrity, not authenticity against
someone replacing both the file and its provenance. The documentation now
states that the cache must be locally generated and trusted. Converting the
entire CPU-machine snapshot format is outside this art stage.

The plane preimages are guarded by the whole-input and whole-plane-table
digests. Their per-byte claims delimit ownership. An additional claim wrapper
would duplicate that contract without adding coverage.

Root removed 23 accepted narrative or stale comment lines/fragments, including
the wrong marquee coordinate and palette prose. Public data-shape descriptions
and explanations of stock hardware contracts remain. Additional tuple/type
refactors from the second comment audit are deferred; they do not hide a
workaround or change the external contract.

## Review process incident

Opus accidentally ran the real-core probe after an exploit had replaced its
supposed invalid input with a valid ROM. This violated the review's no-emulator
instruction. All outputs stayed in its scratch directory and its session was
separate from root's completed event sessions. Root's integrated gate was still
in CPU tests, before its emulator soaks. That accidental run is excluded from
the independent review evidence. Root's own paired event runs provide the
runtime evidence.
