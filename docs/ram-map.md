# RAM map — verified addresses

Sources: DataCrystal RAM map (user-supplied capture), GameHacking.org game 30118,
and our own disassembly. NES RAM is `$0000–$07FF`; addresses here are CPU
addresses, **not file offsets**.

## Pitcher state

| Address | Meaning | Notes |
|---|---|---|
| `$04EE` | Away/home selector | `0` = away, `1` = home |
| `$04F9` | Away pitcher "value 4" | indexed as `$04F9,X`; 4th pitcher record byte (unknown `02–0F`) |
| `$04FA` | Home pitcher "value 4" | `$04F9,X` with `X=1` |
| `$04FB` | Away pitcher stamina remaining | 2nd pitcher record byte |
| `$04FC` | Home pitcher stamina remaining | indexed `$04FB,X` |
| `$04FD` | Away pitcher's lineup position | `00–08` |
| `$04FE` | Home pitcher's lineup position | `$04FD,X` with `X=1` |

The trailer routine confirms the indexing:

```
$B094  LDX $04EE
$B097  LDA $04FD,X     ; away/home pitcher slot
```

`$04FB,X` and `$04F9,X` appear throughout banks 1, 4, 5, 6, 7 for stamina and
pitcher value reads/writes. `$04FA/$04FE` have no standalone absolute references
because they are reached through the `,X` form.

## Game state (GameHacking standard codes)

| Address | Meaning |
|---|---|
| `$00C0` | Ball travel distance (`00C0:11` code) |
| `$0487` | Strikes modifier |
| `$0488` | Balls modifier |
| `$0489` | Outs modifier |
| `$048B` | Team 2 score |
| `$048C` | Team 1 score |

## Rendering / PPU buffers

| Address | Meaning |
|---|---|
| `$0195–$01B4` | 32-byte palette buffer; `$CE77` copies it to `$3F00` |
| `$0200–$02FF` | OAM shadow; DMA via `$4014` |
| `$0300–$03FF` | Display-list buffer |
| `$0032` | Display-list length (cleared by `$C53A` after flush) |
| `$06B3/$06B4` | PPU address for text builder |
| `$06B5` | Text/tile string buffer |

## CHR bank state

| Address | Meaning |
|---|---|
| `$23/$24` | CHR0 bank candidates written by `$CE36/$CE4B` |
| `$25/$26` | CHR1 bank candidates written by `$CE40/$CE50` |
| `$2D` | MMC1 serial-write nesting counter |

## Tournament / bracket

| Address | Meaning |
|---|---|
| `$0650` | Bracket slot array |
| `$0746` | Round counter |
| `$074B–$0756` | Password state bytes |

## Selector hack state (our code)

| Address | Meaning |
|---|---|
| `$07C0` | Page (0–3) |
| `$07C1` | Cursor (0–7) |
| `$07C3` | Selected team (`$FF` = none) |
| `$07C6` | Controller buttons (bit 0 Right … bit 7 A) |
| `$07F0–$07F7` | Debug scratch (length/`$06` traces; remove for release) |

## Notes

- `$04FD` is **not** a generic player-index array; it is the away/home pitcher's
  lineup position, selected by `$04EE`.
- The pitcher record fields map to RAM as: byte 1 → stamina (`$04FB/$04FC`),
  byte 3 → "value 4" (`$04F9/$04FA`).
- Verify any new address in the debugger (`tools/debugger.html`) before relying
  on it; add it to the watch list.
