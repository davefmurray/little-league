# Little League Baseball: Championship Series — ROM layout notes

Source ROM: `Little League Baseball - Championship Series (USA).nes` (262,160 bytes)
MD5 `cd724fd557d323ce7fefe8a82ddf8337` · SHA-256 `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e`

## Cartridge

| Field | Value |
|---|---|
| iNES mapper | **1 (MMC1 / SxROM)** |
| PRG ROM | **128 KiB** = 8 × 16 KiB |
| CHR ROM | **128 KiB** = 16 × 8 KiB = 32 × 4 KiB |
| PRG RAM | none declared (header byte 8 = 0) |
| Header mirroring | horizontal |
| Battery / trainer | no / no |
| iNES 2.0 | no |

Header bytes: `4E 45 53 1A 08 10 10 00 00 …`

### MMC1 control actually used

`$CBE3` writes **$1E** to the control register once at boot:

| Bits | Value | Meaning |
|---|---|---|
| 0–1 | `10` | vertical mirroring |
| 2–3 | `11` | PRG mode 3 — last 16 KiB bank fixed at `$C000`, `$8000` window switchable |
| 4 | `1` | CHR mode 4 KiB |

So the header's "horizontal" is only the initial emulator state; the game immediately
switches to **vertical**. It toggles mirroring later:

- `$99B1` (bank 5): control **$1F** → horizontal mirroring (bits 0–1 = `11`)
- `$9AF5` (bank 5): control **$1E** → back to vertical

CHR is in **4 KiB mode**, so the two MMC1 CHR registers select 4 KiB banks
independently for PPU `$0000–$0FFF` and `$1000–$1FFF`.

## Vectors (PRG bank 7, at `$FFFA`)

| Vector | Address | PRG offset |
|---|---|---|
| NMI | `$CD85` | `$1CD85` |
| RESET | `$CBD5` | `$1CBD5` |
| IRQ/BRK | `$CDF4` | `$1CDF4` |

IRQ is a bare `RTI`.

## MMC1 register writers (all in fixed bank 7)

Each routine does the standard 5-write serial sequence (LSR A between stores) and
brackets itself with `INC/DEC $2D`, a "mapper write in progress" guard used by the NMI.

| Routine | Store address | MMC1 register |
|---|---|---|
| `$C102` | `$9FFF` | control |
| `$C11C` | `$BFFF` | CHR bank 0 (PPU `$0000`) |
| `$C134` | `$DFFF` | CHR bank 1 (PPU `$1000`) |
| `$C14C` / `$C14E` / `$C150` | `$FFFF` | PRG bank |

- `$C102` called from `$CBE3` (boot), `$99B1`, `$9AF5`.
- `$C11C` called from `$CE36`, `$CE4B`; `$C134` reached by `JMP` from `$CE42`, `$CE50`.
- `$C150` has ~106 call sites in bank 7 — PRG banking is frequent.

Pending CHR banks live in zero page: **`$23` = CHR0**, **`$25` = CHR1** (applied by
`$CE45` during NMI); `$24` / `$26` are used by the immediate-update path at
`$CE30–$CE42`, gated by bits 1–2 of `$047A`.

## PRG banks

Bank 7 is the fixed core (reset, NMI, mapper helpers, main loop at `$CC09`).
Banks 0–6 are switched into `$8000–$BFFF`.

| Bank | CPU when mapped | Notes |
|---|---|---|
| 0 | `$8000` | 10% `$FF`, ~46 JSR-shaped words |
| 1 | `$8000` | team/mode text (`$95F8` CHAMPIONSHIP SERIES, `$960E` EXHIBITION MODE) |
| 2 | `$8000` | ~59 JSR-shaped words, low padding |
| 3 | `$8000` | sparse, ~22 JSR-shaped words |
| 4 | `$8000` | **44.8% `$FF`** — mostly padding/data, but ~296 JSR-shaped words |
| 5 | `$8000` | front-end/menu text (`$9C86` QUARTER FINALS, `$9F1D` SPEED MODE, `$A02B` PASS WORD, `$B10C` intro poem) |
| 6 | `$8000` | ~131 JSR-shaped words |
| 7 | `$C000` | **fixed**: vectors, MMC1 writers, NMI/IRQ, main loop |

"JSR-shaped" = raw `20 xx hi` byte pattern, a rough code-density hint only.

## CHR

32 unique 4 KiB banks, no duplicates. Several are very sparse
(bank 18 is 82% `$00`, bank 25 is 70%, bank 24 is 62%), which suggests blank/UI
tilesets rather than dense graphics. Bank 0 (59% `$00`) is the most likely blank
background set. Tiles are plain NES 2bpp; no compression evident.

Banks 28–31 (CHR offset `$1C000–$1FFFF`) have the lowest `$FF` density
(under 18%), so they are the most likely candidates for detailed field/portrait
graphics rather than UI tilesets.

## Text landmarks (PRG offsets)

Text is stored as ASCII in PRG, so it can be searched directly:

| String | PRG offset | Bank | CPU |
|---|---|---|---|
| `CHAMPIONSHIP SERIES` | `$055F8` | 1 | `$95F8` |
| `EXHIBITION MODE` | `$0560E` | 1 | `$960E` |
| `QUARTER FINALS` | `$15C86` | 5 | `$9C86` |
| `SEMI FINALS` | `$15C97` | 5 | `$9C97` |
| `SPEED MODE` | `$15F1D` | 5 | `$9F1D` |
| `WATCH THE GAME` | `$15F2A` | 5 | `$9F2A` |
| `PASS WORD` | `$1602B` | 5 | `$A02B` |
| intro poem | `$1710C` | 5 | `$B10C` |

Team names also appear in banks 1 and 5 (`PENNSYLVANIA`, `CHINESE TAIPEI`,
`CALIFORNIA`, `PUERTORICO`).

## Tooling in this repo

```
.venv/                      # py65 (disassembler) — gitignored
tools/rominfo.py            # header, bank CRCs, vectors, strings
tools/trace.py              # control-flow trace from RESET / NMI with py65
```

```sh
python3 tools/rominfo.py "Little League Baseball - Championship Series (USA).nes"
.venv/bin/python tools/trace.py "Little League Baseball - Championship Series (USA).nes" 600
```

Rebuild the venv if needed:

```sh
python3 -m venv .venv && .venv/bin/pip install py65
```

## Disassembly starting points

1. `$CBD5` reset → MMC1 init → wait on `$047D` (NMI clears/arms it) → main loop `$CC09`.
2. `$CD85` NMI: sprite DMA (`$CE53`), PPU updates, CHR bank apply (`$CE45`).
3. `$C14E` is the PRG-bank switch — log its argument to build a bank call graph.
4. `$CE45` is the CHR bank apply — log `$23`/`$25` to map 4 KiB CHR usage per scene.
