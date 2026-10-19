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

## Round 4 — PRG RAM is writable; NMI corrupts the seed

Decisive CPU test (romdev):

```
LDA #$AB
STA $7700
LDA $7700
STA $0400
RTS
```

`$0400` read back `$AB`, so PRG RAM is writable; the mapper is not blocking
writes. A hardcoded-human seed run from system RAM with `$2000=0` (NMI off)
produced a perfect 32-slot array. The same seed at boot still leaves `$7702=FF`,
so something in the boot/screen path corrupts it after the seed.

Manual seed with NMI left on wrote nothing; with NMI off it wrote correctly.
That points at the stock NMI handler touching cart RAM, not the seed loop.

Screen feature reverted; no broken build committed.

### Next probe

Boot the screen, immediately after the seed copy `$7700..$771F` to system RAM
inside the same routine (before enabling rendering/NMI), and inspect that copy.
If it is clean, the corruption is post-seed from NMI; if not, instrument each
store.

## Round 5 — seed integration GREEN

Root cause of the earlier corruption: the test ROM jumped to an empty `$8100`
(input stub missing) and executed `FF`; the seed itself was fine. With the input
stub present and NMI disabled immediately before `JSR $8200`, the boot-time seed
produces:

```
0f 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e
10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f
```

32 unique values, human 15 at leaf 0, stable across frames. `build_bracket_screen.py`
now supports `--seed-human`; the production selector supplies `$07C3`.

Phase 3 is green. Next: render names from `$7700` and then return to launch.

## Round 6 — dynamic names blocked by display-list/RLE state

- Seed integration remains green (commit `9cea1e0`).
- Attempted to rewrite each team run in the copied display list from
  `$7700`/code table. The list itself updated correctly (`FLA` appeared at
  leaf 0), but `$C53A` then stalled in its RLE branch and the screen went blank.
- `BIT $C040` selects the RLE path. ROM byte `$C040` is `$40`, yet the static
  list (high bytes `$20`) rendered earlier, so the runtime value/semantics need
  measurement, not assumptions.
- Render experiment reverted; no broken build committed.

### Next probe

Read `$C040` on the CPU bus at the moment of flush (romdev memory read at
`$C040`, not `$0040/$00C0`), and compare a static list vs the rewritten list.
If the static list is normal-mode, our rewritten bytes must be corrupting a run
header; dump `$0300..$033F` before flush.

## Round 7 — seeded names render GREEN

Root cause of the previous blank/RLE corruption: team 5's code is `"NY"` (2
chars), so its display-list run was 5 bytes and every later run shifted by one,
corrupting a run header. Codes are now padded to 3 chars (`"NY "`), list length
is 245, and the dynamic renderer writes 3 tiles into each 6-byte run.

romdev screenshot: human team 15 (`FLA`) at leaf 0, then `JPN, ARI, PEN, ...`
with team 15 skipped — exactly the seeded order. Phase 3 is now green end-to-end.
