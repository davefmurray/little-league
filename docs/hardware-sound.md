# Hardware & Sound Execution

Operational notes for running and validating the 32-team ROM on real
hardware, in emulators, and for the audio path.

## Cartridge / mapper

- Mapper: **MMC1** (iNES mapper 1).
- PRG: 16 x 16 KiB banks (256 KiB image), fixed bank 15 at `$C000`.
- CHR: 128 KiB.
- Mirroring: the header declares horizontal; MMC1 controls mirroring at runtime.
- Battery: **not declared** in either the original or candidate iNES header.
  Cart RAM is used during play; power-cycle persistence is not promised.
- The build manifest pins the exact binary:
  `docs/build-manifest.json` + `python3 tools/check_build.py build/direct31.nes`.

Relevant bank ownership in the current source pipeline:

| Bank | Use |
| --- | --- |
| 0, 1, 3, 5 | Live gameplay/menu code and repaired batting-bias copies |
| 1 | Stock password entry, name tables, CONTINUE helper |
| 4 | Gameplay, stock rosters, lineup loader and rating bonuses |
| 5 | Series setup, stock password encoder and CPU pitching |
| 7 | Stale copy of the old fixed bank; not the live bracket |
| 8 | Stored 20-player roster blocks |
| 10 | Four-page team selector |
| 11 | 32-team bracket, restore and list view |
| 12 | 22-symbol v1 password codec |
| 15 | Fixed dispatch, NMI, cache adapter and bank-switch stubs |

## Emulator execution (romdev)

- Server: `npm_config_cache="$PWD/.npm-cache" npx -y romdevtools` on
  `127.0.0.1:7331`; client `tools/romdev.py`; session `llbcs`.
- Deterministic frame stepping; `frame {op:'screenshot', path:...}` for
  evidence; memory reads via `system_ram`/`nes_cart_ram`.
- Harness: `tools/soak_bracket.py` supports stock navigation, `--team`
  selection and `--bracket-state` resume. Final checks use 31 matches,
  live-score mapping and the stock game-over flag.
- Core: `fceumm`.

## Hardware test matrix

- [ ] Mesen2 (studio-owned fresh boot; no CONTINUE, END path)
- [ ] FCEUX (deterministic replay)
- [ ] EverDrive / N8 (real cartridge timing, SRAM save)
- [ ] Original NES / AVS (2-player controllers, 60 Hz)
- [ ] Power cycle + SRAM persistence (CONTINUE)

## Sound

- APU only (2 pulse, triangle, noise, DMC); no expansion audio.
- Music/SFX driven by the stock engine; the 32-team data does not add
  new tracks.
- Validation: title music, menu SFX, field ambience, hit/pitch SFX,
  bracket advance.
- Capture: emulator audio recording; compare against the stock ROM at
  the same scene.

## Input

- Player 1: D-pad, A (confirm/pitch), B (cancel/END), START.
- The bracket/order/list reads `$95`/`$C7` edge state; the title/team
  select uses the same.
- 2-player: the stock field supports it; verify P2 pad mapping.

## Current validation limits

The old 32-byte `$06E2` model was incorrect. The live lineup remains
18 bytes; extending it overwrote line scores. Gameplay, ownership and
password evidence now live in `docs/gameplay32.md`, `docs/control32.md`
and `docs/password32.md`.

FCEUmm execution through romdev is not an independent FCEUX application
run, a Mesen2 run, or a hardware test. Emulator savestates used by the
resume probes are not proof of battery-backed SRAM after a power cycle.
The portable, tested resume path is password entry. Real-hardware password
and audio acceptance remain open. Any flash-cart RAM persistence is an
additional platform capability, not a feature declared by this ROM header.

## Release checklist

- [x] Baseline `check_build` against `docs/build-manifest.json`
- [x] Stock six-match regression and completed-game 31-match speed gates
- [x] Controller selection and ownership for all 32 teams
- [x] Password keyboard restore across all round boundaries
- [x] Display-name correction on high-team game screens
- [x] Bound flag/uniform tables and correct matchup round labels
- [ ] Independent emulator applications and real hardware matrix above
- [ ] Password round-trip on hardware
- [ ] Audio regression against stock
- [ ] Confirm power-cycle behavior; use passwords for supported persistence
