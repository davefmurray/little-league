# Hardware & Sound Execution

Operational notes for running and validating the 32-team ROM on real
hardware, in emulators, and for the audio path.

## Cartridge / mapper

- Mapper: **MMC1** (iNES mapper 1).
- PRG: 16 x 16 KiB banks (256 KiB image), fixed bank 15 at `$C000`.
- CHR: 128 KiB.
- Mirroring: vertical (header-controlled).
- Battery: **yes** (SRAM), used by the stock save/continue path.
- The build manifest pins the exact binary:
  `docs/build-manifest.json` + `python3 tools/check_build.py build/direct31.nes`.

Known bank map (direct31):

| bank | use |
| ---- | --- |
| 0-1 | menu / list / team card / password helpers |
| 4 | low-team rosters (`$8420 + t*0x120`) |
| 5 | password `$9B5F`/`$98D5`, series init |
| 6 | field/order handlers |
| 7 | bracket/scene helpers |
| 8 | high-team rosters (`$8000 + t*0x170`) |
| 11 | 32-team bracket codes |
| 15 | fixed: scene table, NMI, cache, launch |

## Emulator execution (romdev)

- Server: `npm_config_cache="$PWD/.npm-cache" npx -y romdevtools` on
  `127.0.0.1:7331`; client `tools/romdev.py`; session `llbcs`.
- Deterministic frame stepping; `frame {op:'screenshot', path:...}` for
  evidence; memory reads via `system_ram`/`nes_cart_ram`.
- Harness: `tools/soak_bracket.py` (CONTINUE/END navigation, scene
  handlers, 6/26-match soaks, final-state screenshots).
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

## Known open gaps (link to TODO)

- Field pitch / live-field gameplay (item 10) — `$06E2` group/team.
- LIST OF TEAMS full 32 scan (item 4) — `$071A`/`$06E2` 32-byte tables.
- Password screen bank5 wiring (item 7) — `docs/password-screen.html`.
- Bench/attribute card (item 8).

## Release checklist

- [ ] `check_build` green against `docs/build-manifest.json`
- [ ] 6-match soak green
- [ ] 26-match soak (field/pitch pending)
- [ ] Brackets render all 32 team names
- [ ] Password round-trip on hardware
- [ ] Audio regression vs stock
- [ ] SRAM CONTINUE after power cycle
