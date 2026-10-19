# Autonomous run plan (Fable 5.1)

Goal: wire the 32-team bracket into the game over a 4–6 hour unattended run.
Build from stock each phase; never commit `build/` or `*.nes`.
Commit + push `main` after every green acceptance. Update `TODO.md` and
`docs/PLAN-32-TEAM.md` in the same commit.

## Phase 0 — find the true handoff owner (30 min)

Stock ROM in romdev, session `llb-auto-p0`.

1. Save state at title, then drive team select → CONTINUE/END → bracket →
   first game start with `input op:sequence`.
2. `breakpoint on:write address:$04EF` and `$04F0`, maxFrames 1500.
   Record PC, bank (`$27`), caller.
3. If no write: `breakpoint on:read` on both from the bracket screen on.
4. `disasm xrefs` for `$04EF/$04F0/$0650` across banks 0–5.
5. On `build/bracket-input.nes`, after A, diff RAM against stock at the same
   point (`$0746`, `$04EB/$04EC`, `$047D`, `$BE/$BF`, CHR bank).

Acceptance: `docs/bracket-handoff.md` has a “Stock owner” section with
PC/bank/frame and the diff list. Commit.

## Phase 1 — game launch from bracket (60 min)

Bank-11 A-handler: write ids, set `$04EB/$04EC=$80`, replicate the Phase 0
diff, jump into the stock game-start scene via `$C14E`.

Acceptance: romdev A → 600 frames → field screenshot; ids match cursor; NMI
alive. Stock regression still plays. Commit.

## Phase 2 — post-game return and advance (60 min)

Find the `$0746` increment. Hook: if `$07C3 != $FF`, call bank-11
`advance(winner)` on `$7700`, redraw.

Acceptance: py65 31-match replay still passes; romdev forced result returns to
bracket with winner moved. Commit.

## Phase 3 — seed 32 from selector (45 min)

Selector OK (`$07C3`) → bank-11 init: human at leaf 0, others in table order
into `$7770`.

Acceptance: py65 all 32 ids once, human at leaf 0 for teams 0/15/31; romdev
team 20 shows top-left. Commit.

## Phase 4 — round labels, redraw, five-round soak (60 min)

Acceptance: scripted five rounds, champion slot 62, screenshot per round,
stock regression. Commit.

## Phase 5 — password (optional, 75 min)

32×5 seed bits + 32×3 win bits + round + checksum; 100 Python round-trips.

## Phase 6 — handoff (20 min)

Byte-diff vs stock (banks 0–9 untouched except `$CBE6` and the Phase 2 hook),
update docs, write `docs/AUTORUN-REPORT.md`, final push.

## Stop rules

- 30 min without new evidence, or 3 failed hypotheses → stop the phase.
- Revert tool edits to last green state; write what was tried, exact PCs, and
  the next probe in `docs/AUTORUN-REPORT.md`; move to an independent phase.
- Never leave uncommitted edits or a red stock regression.

## Decision tree

- Handoff owner not found → read-breakpoint `$04EF`/`$0650` during game-start;
  poke ids at the stock bracket screen. If honoured, mirror semantics are fine.
- Wrong teams → RAM diff stock vs hack at first field frame; patch one byte,
  two retries.
- Crash/blank in bank 11 → check `$27` shadow and control `$0C/$1E`; NMI via
  `$047D`.
- ids 16–31 crash loader → fall back to ids 0–15 and document table extension.
- py65 vs romdev disagree → trust romdev/fceumm.

## Risks

MMC1 control/shadow; `$7700` vs `$6000–$76FF`; pad scratch `$07C6–$07C9`;
NMI/PPU flush; 16-team tables for names/ratings/flags; stock password must not
serialise 32-team state.
