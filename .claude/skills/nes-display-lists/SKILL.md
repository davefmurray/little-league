---
name: nes-display-lists
description: Build and debug the LLBCS display-list renderer — run format, buffer/length, $C53A flush, RLE bit, grid addresses, font tiles, and the run-length bugs that blank the screen. Use when a NES screen is blank, garbled, or when adding text/rows to the bracket or selector.
---

# LLBCS display lists

This game does not write nametables directly. It builds a small command buffer
and flushes it with `$C53A`.

## Format

```
[addrHi, addrLo, ASCII tile, ASCII tile, ..., $FE]
```

- Address is a nametable address: `$2000 + row*32 + col`.
- `$FE` terminates the run.
- High byte bit 6 (`$40`) selects the **RLE path** in `$C53A`; normal text runs
  have addresses `$20xx`, so bit 6 is clear.
- Buffer: `$0300`.
- Length: zero page `$32`.
- Flush: `$C53A`.

`$C040` is **not** a RAM flag. It is a ROM byte `$40` used by `BIT` as the bit-6
mask. `STA $C040` is a no-op; control RLE through each run's high byte.

## Building runs

```python
def run(addr, text):
    return bytes([addr >> 8, addr & 0xFF]) + text.encode("ascii") + b"\xFE"
```

Every character is one byte. The game font maps ASCII space, `0-9`, `A-Z`;
punctuation may be blank or somewhere else entirely. Do not assume `<`, `>`, `/`
exist at their ASCII tiles.

## Bracket grid

```python
labels = "R32   R16   QF    SF    F".ljust(32)[:32]
out  = run(0x2048, labels)          # 32 chars
out += run(0x2068, "32 TEAM BRACKET")
for i, team in enumerate(teams):
    col = i % 4
    row = 5 + (i // 4) * 2
    out += run(0x2000 + row * 32 + 1 + col * 8, team["code"].ljust(3)[:3])
```

- Labels must be exactly 32 chars; a 33rd wraps to the next line.
- Header is 15 chars.
- Every team run must be **exactly 6 bytes**: 2 address + 3 chars + `$FE`.
- Pad short codes: `"NY"` → `"NY "`. A 2-char code shifts every later run by
  one byte and corrupts a run header; the flush then takes the RLE path and the
  screen goes blank.
- Keep the whole list under 250 bytes; the builder rejects longer lists.

The NES viewport is 256×224, so the top and bottom 8 px are cropped. Keep
content inside rows 1–27 for emulator screenshots.

## Debugging a blank or garbled screen

1. Read `$32`; it should equal the list length the builder wrote. A stuck flush
   leaves the old value; a finished flush writes 0.
2. Dump `$0300..$033F` and verify each run:
   - starts with a plausible `$20xx` address,
   - ends with `$FE`,
   - grid runs are exactly 6 bytes apart.
3. Check `cpu.pc`. If it sits in `$C53A`, the flush is looping:
   - run header high byte has bit 6 set (RLE) unexpectedly,
   - a run is missing its `$FE`,
   - a length byte disagrees with the copied data.
4. Check whether the list was copied at all. The screen code copies
   `$B200`-style source data to `$0300`; if the copy length is wrong, the tail is
   stale or `$FF`.
5. If only one row is wrong, suspect a variable-length string. Pad every cell to
   the run width before building.

## Screen-code checklist

A scene should, in this order:

1. `LDA #0; STA $2000` (NMI off)
2. `LDA #0; STA $2001` (rendering off)
3. `LDA #$1E; JSR $C102` (MMC1 control)
4. `LDA #0; JSR $C11C` (CHR0; clears PRG-RAM write protect)
5. seed/table build with NMI still off
6. `LDA #1; JSR $C134` (CHR1)
7. palette upload to `$2006/$2007`
8. copy list to `$0300`, set `$32`
9. `JSR $C53A`
10. `LDA #$1E; STA $2001`, then enable NMI if the scene needs it

Steps 3–4 must precede any `$6000–$7FFF` write. Step 8 must set `$32` **after**
the copy, not before.
