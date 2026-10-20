# STEP 2 Audit — after the 11-item list

Snapshot of where the 32-team ROM stands and what a fresh TODO needs to
cover.

## Done (7/11)

1. Launch bridge + high-team field entry.
2. Order-screen/field start fix.
3. Live field/match engine + roster cache (6-match soak green).
4. Match-5 soak stall — low-team cache fixed.
5. Scene 1E/1F — resolved, stock-identical.
6. Hardware/sound execution docs — `docs/hardware-sound.md`.
7. Bench/attribute card design — `docs/bench-card.md`.

## Active (3/11)

- **LIST OF TEAMS (4):** `$A1C6 0x0F` + `$9FA9 0x0F` shows real 32-team
  names (SPAIN/FLORIDA/PUERTO RICO/CANADA); `$071A` 32-byte flags and
  `$06E2` 32-byte groups still needed for the full scan.
- **Password (7):** format confirmed (8 bytes = seed+results+version,
  16 chars); `$9B5F`/`$98D5` disassembled; `docs/password-screen.html`
  mock; bank5 32-team decode/encode not wired.
- **Pitch / live-field (10):** high teams reach scene 03 `$0489=0`;
  `$0650` teams vs `$B2`/`$06E2` group mapping mismatch; pair3/pair4
  page table works for matches 0-4 only.

## Gaps / risks

- Table sizes: `$06E2` (16 -> 32), `$9A70` (64 -> 128), `$071A` (16 -> 32).
- High teams 16-31 vs the stock 16-team tables (`$06E2`, `$9A70`, `$8941`).
- Field pitch never runs for the high-team match 8 (26-soak stall).
- Bank5 32-team decode and the `$06B5` 16-char buffer.
- Hardware/audio/SRAM/2-player are untested.
- Build reproducibility: manifest/check_build covers `direct31` only.

## New need areas

- Audio regression (stock vs 32-team).
- SRAM battery CONTINUE path.
- 2-player field.
- Release pipeline: manifest, screenshots, hardware checklist.
- Regression/CI: check_build + 6-match soak + data tests.
