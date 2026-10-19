# AUTORUN report — rounds 1–2

## Phase 0 — handoff owner (qualified)

- 52 static refs to `$04EF`. Writers: bank0 `$AD1B/$AD22/$AD2B`, bank1
  `$B119` (home/away swap), bank2 `$BC8C` (table `$B8C9`), bank5
  `$9C0E/$9C14` (bracket).
- Bank0's routine uses `$33` and `$C46F`; `$C46F` is a table sequencer
  (`INC $34`, table `$C4FA`), not a team lookup.
- Direct `cpu({op:'call'})` into bank6 `$AC3A` produced `$04EF=$02`,
  `$04F0=$06`, confirming that path is a different context, likely field/demo.
- Conclusion: bracket raw-slot writes remain plausible; do not change the
  contract without a real bracket→game trace.

## Phase 1 — launch (parked)

Jumping from the A-handler into bank6 `$AC3A` (after `$C1|=2`, bank6 mapped)
crashed the core (`PC=0`). Calling it sandboxed returned but did not change the
scene. This is not the launch entry. Parked under the 30-minute rule.

## Phase 3 — 32-team seeding (logic green)

- Bank-11 `seed` at `$8011`: reads `$07C3`, writes leaf 0, fills 1–31.
- py65: human 0/15/31 → leaf 0 correct, all 32 unique.
- Fixed `size_of` in `build_bank11.py` (zero-page operands were counted as
  3 bytes, shifting branches). Advance re-verified: champion slot 62, win sum 31.
- Screen integration blocked: at the `$CBE6` hook, PRG RAM writes to `$7700`
  read back as open bus, and `$07C3` is not set yet. The selector/dispatcher
  must set `$07C3` and enable PRG RAM before seeding.

## Next probes

1. Enable PRG RAM (MMC1 CHR0 bit 4 / board rules) before any `$7700` access;
   verify with `memory({op:'read'})` on the cart-RAM region.
2. Have the dispatcher write `$07C3` before jumping to bank 11.
3. Find the true launch entry by tracing the stock bracket handler's scene
   transition, not bank6 `$AC3A`.

## Regression

Stock ROM untouched; default build remains table-only. No red regression left.

## Round 3 — PRG RAM investigation (partial)

- iNES header byte 8 (PRG RAM size) is `0`. Patching it to `1` (8 KiB) did **not**
  change behavior in fceumm.
- Bank-11 seed logic passes in py65 with the human copied to `$07CA` instead of
  zero-page `$02` (which stock code clobbers): human 15 → slot 0, all 32 unique.
- In-ROM seed at `$8200` still corrupts: `$7702` stays `FF`, values after it
  shift, and a manual `cpu call` to the seed leaves the slots untouched even
  after `$C11C` CHR0=0. Cart RAM region writes via romdev work, so the mapper
  write path is the suspect, not the array.
- Screen integration reverted; no broken build committed.

### Next probe

Watch CPU writes to `$7700` in romdev during the seed (`breakpoint on:write`),
and log the MMC1 CHR0 value at the same instant. If writes are dropped, test
SNROM PRG-RAM enable semantics or move bracket state into system RAM until the
board behavior is understood.
