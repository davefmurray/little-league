# 32-team plan (adopted)

Author: Fable 5.1, with repo verification. This supersedes the in-place bracket
patching experiments.

## Decision

Build a **new 32-team bracket scene in PRG bank 11** and leave the stock 16-team
bracket, password, and screen untouched.

Why:

- The stock state is 16-team-shaped everywhere: 8 packed nibbles at `$074D`,
  slots `$0650`, losses `$0670`, match counter `$0746`, and consumers we have
  not all found.
- A new scene has one unknown boundary (handoff to the game engine) instead of
  dozens of patched consumers.
- Stock remains the regression oracle: every build must still play a normal
  16-team series with the hack disabled.
- `tools/build_32bracket.py --state` stays as a CPU-validated **reference
  implementation** of advance logic, not the shipped path.

Bank 11 was verified free: 16 KiB of `$FF` in `build/32x20-ui.nes`.

## Entry

Keep the stock reset. Hook after init at `$CBE6 → JSR $FF00`, selector-style.

`$FF00` becomes a scene dispatcher:

- `$07C3 == $FF` → run the selector in bank 10.
- otherwise → map bank 11 and run the bracket scene.

Never replace the reset vector again. The `$C26F` hang proved the scene handlers
need stock RAM/NMI/`$047D` arming.

Any trampoline must still start with the jsnes-safe MMC1 reset
(`STX $9FFF`), control `$1E`, and bank switching through `$C14E` (which sets the
`$27` shadow).

## RAM layout

| Block | Address | Size |
|---|---|---|
| Roster cache | `$6000-$76FF` | `0x1700` |
| Bracket slots | `$7700-$773E` | 63 |
| Loss counts | `$7740-$775F` | 32 |
| Round / match counter | `$7760` / `$7761` | 2 |
| Human team / seed order | `$7762`, `$7770-$778F` | 1 + 32 |
| Password scratch | `$7790-$77AF` | 32 |
| Pointer table | `$7F00` | unchanged |

Stock `$0650/$0670/$0746/$074B` are **not** written by the new scene until the
handoff writes only the two team IDs the game loader reads.

Seeding: the selector’s chosen team is leaf 0; the other 31 fill leaves 1–31 in
table order. Password seeding is deferred to M5.

## Disassembly targets

| Target | Address | Question |
|---|---|---|
| Stock bracket caller | bank 5, sets `$0746=0`, JSRs `$9B5F` | What scene/RAM the game expects before a round |
| Game loader | fixed bank, consumers of the two matchup IDs | Minimum handoff contract |
| Round display | `$9C08-$9C40`, `$9C86` | Round labels and team-name composition |
| Password | bank 5 `$A036` | Format/checksum for M5 |
| `$0650/$0670` consumers | all banks | Which reads are bracket-only vs shared uniform state |
| Scene dispatcher | fixed `$CC09` main loop | How scenes are selected and returned from |
| Post-game return | routine that increments `$0746` | Where “match played, advance” hooks in |

## Milestones

**M1 — Dispatcher.** `$FF00` dispatches on `$07C3`. Test: selector unchanged;
with `$07C3=5` preset, PC reaches bank 11 `$8000`, `$27=11`, NMI still toggles
`$047D`. Do not claim bracket entry yet.

**M2 — Handoff contract.** Documented in `docs/bracket-handoff.md`: team ids
`$04EF/$04F0`, alive flags `$04EB/$04EC`, 16-bit results `$074B/$074C`.
Remaining acceptance: poke two ids from the debugger and confirm a match starts.

**M3 — Bracket logic only.** Port advance/display loops into bank 11 using
`$7700` state. Test: py65 replay of 31 matches, champion at slot 62, losses sum
to 31, and no writes to `$0650-$068F` from bank 11.

**M4 — Bracket screen.** Four columns of eight, five round labels, Koushien
layout, text-only first. Test: screenshots at round 0 and round 4; A launches a
game via the M2 contract; winner advances and screen redraws. Only now claim
“32-team tournament playable.”

**M5 — Password.** Encode seed order (32×5 bits) + losses (32×3 bits) + round +
checksum. Test: 100 random round-trips in Python, then 3 in-ROM states.

**M6 — Soak.** Full five-round run, stock-mode regression, byte diff showing
banks 0–9 untouched except `$CBE6`.

## First three actions

1. **M2:** trace `$9BC1` → `$9C42` with py65 and log every store to
   `$04xx/$06xx/$07xx`; produce the handoff contract.
2. Scan all banks for `$0650`/`$0670` operands; classify bracket-only vs shared.
3. Convert `$FF00` into the `$07C3` dispatcher; verify bank 11 is reached with
   NMI alive.

## Risks

- Handoff may be more than two team IDs (palette, CHR bank, flag).
- CHR budget: ship a text-only bracket first.
- jsnes-specific MMC1 behavior; validate on Mesen before claiming correctness.
- Password entropy may force a 24-character code.
