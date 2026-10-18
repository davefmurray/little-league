# Palette notes for the flag grid

Sources: [NESdev PPU palettes](https://www.nesdev.org/wiki/PPU_palettes),
[NESdev PPU attribute tables](https://www.nesdev.org/wiki/PPU_attribute_tables),
and the romhacking.net threads on
[changing a background object's palette](https://www.romhacking.net/forum/index.php?topic=23123.0)
and
[individual tile palettes](https://www.romhacking.net/forum/index.php?topic=28262.0).

## The hardware rules

- Backgrounds and sprites each have **4 palettes of 4 colors** at `$3F00–$3F1F`.
- Color 0 of each palette is **transparent**; palette 0 color 0 is the backdrop.
- Palette selection is a **2-bit attribute**, so only 4 palettes exist per layer.
- **Background:** one palette per **16×16 pixel region** (one quadrant of an
  attribute byte; the byte itself covers 32×32, split into four 16×16 quadrants).
- **Sprite:** one palette per **sprite object** (8×8 or 8×16), selected by bits
  0–1 of its attribute byte.
- Palette RAM is mirrored through `$3F00–$3FFF`; writes take effect immediately
  (do them in VBlank to avoid mid-frame artifacts).
- 64 colors total; `$0F` is black, `$30` white, `$16` red, `$1A` green,
  `$28` yellow, `$12` blue.

## What this means for 24×24 flags

A 24×24 flag spans **two 16×16 regions in each axis** (four attribute quadrants).
You cannot give it one background palette unless the flag is placed inside an
aligned 32×32 cell and all four quadrants are set to the same palette.

Three workable designs:

### A. Sprites — 3×2 (recommended for colour)

- 8 flags × 6 sprites = **48 OAM entries**, under the 64 limit.
- Each flag is 24×16 px, one palette per flag, so four palettes cover eight
  flags (two flags per palette).
- No CHR bank-0 packing, no attribute-table surgery.
- Cost: flags are 24×16 instead of 24×24; 3×3 needs 72 sprites and does not fit.

### B. Background — 32×32 aligned cells

- Place each flag inside a 32×32 cell aligned to the attribute grid.
- Set all four 16×16 quadrants of that cell to one palette.
- 8 flags = 72 tiles; still one tile over CHR bank 0's 71 empty tiles.
- Needs a page-time CHR copy, and the 8th-tile fix.

### C. Palette swapping (more colours than 4 palettes allow)

- **Per page:** rewrite `$3F00–$3F1F` in VBlank with a palette set chosen for the
  visible eight flags. Four palettes still, but you can choose them per page.
- **Per scanline:** rewrite palette entries during HBlank using `$2002` polling
  or a mapper IRQ. MMC1 has no IRQ, so this is cycle-timed `$2002` polling;
  fragile, but it is how games exceed four on-screen palettes.
- **Per frame:** fade/cycle palettes by writing a table each VBlank.

## Concrete recommendation

Use **sprites at 3×2** for the flags:

- 48/64 OAM entries leaves room for the cursor and any UI sprites.
- Four sprite palettes, two flags each; pick palettes to fit the actual flag
  colours:
  - P0: white, red, blue
  - P1: white, green, gold
  - P2: white, blue, gold
  - P3: white, red, green
- Flags that need a colour outside their assigned palette get a per-page palette
  swap (option C) rather than more tiles.

The earlier background-tile route is still valid, but it costs nine tiles per
flag, needs 32×32 attribute alignment, and hits the 71-tile ceiling.

## Code sketch (sprites, 3×2)

For each visible flag `i` (0–7):

```
tile_base = flag_tiles[i]          ; 6 tiles, row-major 3×2
palette   = flag_palette[i] & 3
y = 40 + (i/4)*72
x = 16 + (i%4)*60
for s in 0..5:
    OAM[s] = y + (s/3)*8
    OAM[s+1] = tile_base + s
    OAM[s+2] = palette
    OAM[s+3] = x + (s%3)*8
```

Palette writes in VBlank:

```
LDA #$3F : STA $2006
LDA #$10 : STA $2006          ; sprite palette 0
LDX #0
loop: LDA pal_data,X : STA $2007 : INX : CPX #12 : BNE loop
```

## Open questions

- Which eight flags share a palette without conflicts?
- Do we want 24×16 sprites or 24×24 with a missing entry?
- Is a per-page palette swap enough, or do we need per-scanline?
