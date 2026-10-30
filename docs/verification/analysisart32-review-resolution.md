# Power Analysis acceptance and review resolution

The accepted ROM is `1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`.
It is byte-identical to selected design B. The final output-path fixes change
Python tools only; the ROM, registered assets and chosen composition remain unchanged.

## Independent findings

[Sol's review](analysisart32-review-sol.md) found no ROM defect and requested
an output-ancestor guard. [Opus's review](analysisart32-review-opus.md)
approved the ROM, confirmed that fix, then found its macOS temp-path regression.
Their historical hash ledgers describe the versions each reviewed, not the
final files after these fixes.

- **Arbitrary symlink ancestors:** converter, builder and probe use one
  `output_path` check before creating destinations. Missing and existing
  children beneath a custom linked directory are refused. The error identifies
  the link and suggests the resolved path. Existing protected-input and hardlink
  checks still apply.
- **macOS temporary directories:** on macOS only, `/tmp` and `/var` are
  normalized when they are links to the expected `/private/tmp` and
  `/private/var`. This does not permit arbitrary links below them.
  The real converter and builder CLIs test both the platform temp directory
  and `/tmp`, including exact outputs, `--check`, `--record`, and refusals
  that leave inputs unchanged. See [final CLI checks](analysisart32-output-guards-final.txt).
- **Probe destinations:** [the final probe guard test](analysisart32-probe-guards-final.txt)
  exercises natural temporary paths and 23 hostile destinations before any
  emulator dispatch.
- **Leave-state wording:** the picker retains `$047A=$06`; its short NMI
  path skips CHR work. Both exits clear `$047A` before drawing, and split
  presets rewrite `$26`. The documentation now explains this rather than
  claiming that the picker clears the split flag. The suite's static-check
  message distinguishes pinned reader bytes from the separate review audit.
- **Bias-table boundary:** the stage document records the unchanged bank-3
  `$BD00-$BD1F` table, its 0–31 index and the adjacent new pad.
- **Lineup driver:** a resumed mixed-ownership series can put controller 2
  in the editor. The driver checks both ports and stops after scene exit.
  Its [unit test](analysisart32-lineup-driver.txt) is now in `verify.sh`.

No large test-file split or output-guard performance rewrite is included.
Those suggestions are maintainability follow-ups, not correctness defects.
The 182 NMI injections include repeated instructions at different execution
points; they are not a claim of 182 unique instruction sites. Cosmetic pxl
comment changes would require updating source digests without changing pixels,
so the accepted art source stays frozen.

## Final evidence and limits

- [Source pipeline](analysisart32-pipeline.txt): selected ROM reproduced.
- [Integrated gate](analysisart32-gate.txt): all CPU stages, Analysis's 23
  sections with pxl, stock six games and all 31 candidate matches pass.
  Candidate stack is `$FF` after every match; champion is 07.
- [Controller tour](analysisart32-ui.txt): all 32 teams, 27 phase captures,
  exact split-strip pixels, return to the same team, and active-series preservation.
- [Mapper census](analysisart32-mapper.json): 6,467 traced frames,
  158,713 writes and no misaligned writes. Audio-capture advances are excluded.
- [Post-Analysis continuation](analysisart32-after-analysis.txt): resumed
  match 24 completes 7–3 and advances to 25, stack `$FF`.

The integrated gate predates the final CLI-only path normalization. The final
CLI and probe guard tests cover those changes separately. The newly wired
lineup unit also passes separately. No ROM instruction or asset byte changed
between these runs.

The incomplete WATCH and first SPEED logs are retained as diagnostics. Neither
is counted as a passing gate. The successful post-Analysis run and full-31 run
use SPEED, which forces CPU ownership. Earlier stockart32 WATCH evidence belongs
to that earlier ROM. Hardware, PAL, a second emulator and subjective listening
remain unvalidated. CPU-model APU equality and real-core activity are not
listening tests.
