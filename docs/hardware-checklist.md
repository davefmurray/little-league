# Hardware validation checklist

The hack is emulator-verified only so far. This is the exact bench checklist
for a flash cart or MMC1 donor.

## Cartridge requirements

- MMC1 (mapper 1), **16 PRG banks = 256 KiB**, **16 CHR banks = 128 KiB**,
  8 KiB PRG-RAM.
- iNES header from `build/direct31.nes`: mapper 1, 16 x 16 KiB PRG, 16 x
  8 KiB CHR, vertical mirroring (the header is the source of truth; check it
  with `tools/rominfo.py`).
- Battery only if you want in-cart saves; the soft save/password path does
  not require it.

## Bench checklist

1. Power-on/title; verify the title and menu music.
2. Selector pages 1-4; verify teams 16-31 (`AUS`..`CZE`) and the page-3
   screenshot layout.
3. Enter the bracket; verify all 32 codes, `R32/R16/QF/SF`, `ROUND 1`,
   cursor, and the `WIN` row.
4. Play match 0 (low teams) to the box score; verify the score, winner slot,
   and the next bracket.
5. Play a team 16/17 match; record whether the field card/order sequence
   starts (currently blocked in emulator: see `docs/32-team-status.md`).
6. Password screen: record the visible text and whether it round-trips.
7. Reset/power-cycle; verify the save/password path.
8. NTSC and PAL (if available); record any timing/audio differences.

## Record

Keep a table: cart/PCB, mapper, PRG/CHR, region, firmware, result, and
screenshot/photo. Do not report "works" without the specific test number.

Status: **not run** in this environment.
