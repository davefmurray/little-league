# Scoreboard review resolution

The independent review in scoreart32-review.md covers ROM `2ae1a7ab`.
The ROM bytes are unchanged by these fixes.

- Screenshot targets now pass source/ROM alias protection before any emulator
  request. Preflight covers every planned capture, including the inherited
  Exhibition helper. Tests reject 37 direct, symbolic-link, hard-link and
  missing-path collisions and accept fresh capture paths.
- Non-string font declarations now produce a controlled validation error.
  Four malformed values exercise that boundary.
- The inaccurate “up four rows” art comment was removed. Regenerating the
  source-hash metadata changes the asset JSON hash, but no rendered bytes.

`scoreart32-review-fixes.txt` records these regressions. The final full
suite with pinned pxl regeneration passes in `scoreart32-final-cpu.txt`.
The integrated gate exits 0 with stock6 and final31 complete in
`scoreart32-gate.txt`; it predates only these tooling/metadata fixes.
