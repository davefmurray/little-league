---
name: mmc1
description: Work with NES MMC1 / SxROM cartridges — serial register writes, PRG and CHR bank modes, the 512 KiB A18 trap, PRG-RAM enable, reset, and board variants. Use when reading or patching an MMC1 ROM, debugging bank selection, expanding PRG, or deciding whether a mapper change is required.
---

# MMC1 (SxROM) playbook

Primary source: <https://www.nesdev.org/wiki/MMC1>. This is a distilled,
operational summary — read the wiki for the full board/pinout history.

## Register map

| CPU range | Register | Width | Notes |
|---|---|---|---|
| `$8000–$9FFF` | Control | 5 bits | mirroring, PRG mode, CHR mode |
| `$A000–$BFFF` | CHR bank 0 | 5 bits | PPU `$0000`, or 8 KiB bank |
| `$C000–$DFFF` | CHR bank 1 | 5 bits | PPU `$1000`, ignored in 8 KiB mode |
| `$E000–$FFFF` | PRG bank | 4 bits | 16 KiB bank at `$8000` |

Only bits 14–13 of the address matter on the fifth write. Lower address bits are
not decoded.

## Serial write protocol

1. Write five times, **LSB first**, with the data bit in bit 0.
2. A write with **bit 7 set** resets the shift register and forces
   `Control |= $0C` (PRG mode 3, fixed last bank).
3. The **fifth** write latches the register selected by address bits 14–13.
4. After the fifth write the shift register clears automatically.

Canonical PRG-bank write:

```asm
; A = bank number
sta $E000
lsr a
sta $E000
lsr a
sta $E000
lsr a
sta $E000
lsr a
sta $E000
rts
```

### Consecutive-cycle writes

If the serial port is written on consecutive CPU cycles, every write after the
first is ignored. This matters for read-modify-write instructions (`INC`, `ASL`,
etc.) which write twice. Use plain `STA` with at least one cycle between writes;
avoid `INC` on a ROM location unless you specifically want the reset behavior.

## Control register

```
4bit0
-----
CPPMM
|||||
|||++- nametable arrangement
|++--- PRG bank mode
+----- CHR bank mode
```

PRG modes:

| Mode | Behavior |
|---|---|
| 0, 1 | 32 KiB at `$8000`, low bank bit ignored |
| 2 | first bank fixed at `$8000`, switch 16 KiB at `$C000` |
| 3 | **last bank fixed at `$C000`**, switch 16 KiB at `$8000` |

Most games, including this one, use mode 3.

CHR mode: 0 = 8 KiB banks, 1 = two independent 4 KiB banks.

## CHR banks and the 128 KiB ceiling

- CHR register is 5 bits → 32 × 4 KiB = **128 KiB max**.
- In 8 KiB mode, bit 0 is ignored; bank number is effectively `value & ~1`.

## PRG banks and the 512 KiB trap

- The PRG register is **4 bits** → 16 × 16 KiB = **256 KiB** addressable directly.
- 512 KiB MMC1 boards reuse **CHR bank 0 bit 4 as PRG A18**.
- That same line is **CHR A16** when CHR is 128 KiB. They are mutually exclusive.
- Therefore **512 KiB PRG + 128 KiB CHR is not a valid MMC1 cartridge**. Boards
  that do 512 KiB (SUROM, SXROM) address only **8 KiB CHR RAM**.

Practical consequence: if a 512 KiB build must keep 128 KiB CHR, the mapper is
wrong — use MMC3 (or another mapper) instead of hacking A18.

## PRG-RAM enable

- MMC1B: `$E000` bit 4 — `0` enables PRG-RAM at `$6000–$7FFF`, `1` disables.
- SNROM additionally uses CHR bank 0 bit 4 as a PRG-RAM disable.
- MMC1A has different fixed-bank behavior; do not assume MMC1B semantics.

## Reset and power-on

- Reset the mapper by writing `$80` (bit 7 set) to any ROM address.
- Power-on bank state is not reliable across revisions; initialize explicitly.
- The reset write also sets PRG mode 3, so the last bank is at `$C000` afterward.

## Board variants that change register meaning

| Board | PRG | CHR | Special |
|---|---|---|---|
| SNROM | ≤256 KiB | 8 KiB RAM | CHR0 bit4 disables PRG-RAM |
| SUROM | 512 KiB | 8 KiB RAM | CHR0 bit4 = PRG A18 |
| SXROM | 512 KiB | 8 KiB RAM | A18 + 32 KiB PRG-RAM banking |
| SZROM | ≤256 KiB | 64 KiB | CHR bit4 banks PRG-RAM |

Always check the board before assuming a register bit means what the generic
table says.

## Pitfalls checklist

- [ ] Fifth write address selects the register — verify the `$8xxx/$Axxx/$Cxxx/$Exxx` target.
- [ ] Five writes, LSB first, bit 7 clear.
- [ ] No read-modify-write on the serial port.
- [ ] Bank number fits the register width (4 bits PRG, 5 bits CHR).
- [ ] Fixed bank is the **last** bank in mode 3; expanding PRG moves it.
- [ ] CHR bit 4 is not reused for A18 unless CHR is 8 KiB.
- [ ] Reset/power-on state initialized, not assumed.
- [ ] PRG-RAM enabled before relying on `$6000–$7FFF`.

## Debug recipes

- **Vectors:** read `$FFFA–$FFFF` from the **last** PRG bank; NMI/RESET/IRQ must
  point into mapped code.
- **Bank switch routine:** disassemble it. Five `STA $FFFF`-style writes = 4-bit
  PRG register. A fifth bit written there is dropped by hardware.
- **512 KiB check:** if the header says 32 PRG banks and 16 CHR banks, the ROM is
  not hardware-valid on MMC1.
- **Marker test:** write a distinct byte at a fixed address in each bank, switch
  banks, read it back; confirms the mapping without relying on code.

## In this repository

- `tools/expand_rom.py` grows PRG and copies the **input's last bank** to the new
  fixed bank, preserving vectors and patches.
- `docs/rom-layout.md` records this ROM's MMC1 helpers: control `$C102`, CHR0
  `$C11C`, CHR1 `$C134`, PRG `$C150`.
- The stock PRG routine writes five bits to `$FFFF`; banks 16–31 alias because
  hardware latches only four. The 512 KiB experiment is emulator-only.
- CHR is already at the 128 KiB maximum; new graphics must reuse spare tiles.
