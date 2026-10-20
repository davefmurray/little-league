# Password format — stock and 32-team proposal

## Stock 16-team format

The stock password is a 16-team tournament state:

| Address | Meaning |
|---|---|
| `$074D-$0754` | 8 packed bytes: 16 team ids, high nibble then low nibble |
| `$0755/$0756` | 16-bit result/progress bitstream |
| `$0746` | matches played (0-15) |
| `$0650-$065F` | unpacked 16-team slot array |
| `$0670-$067F` | per-team win counts |
| `$8941` | 15 x 3 match table (team A, team B, destination) |

### Encode / series init — bank5 `$98D5`

`$98D5` clears `$064F-$065F` to `$FF`, then fills `$0650` with a shuffled
permutation of the 16 ids in table `$994F`. It uses `$C46F` + `$F5` as the
slot index, retries on collision, and finally packs `$0650` pairs into
`$074D` (8 bytes). `$98B7` calls it at "start new series".

### Decode / advance — bank5 `$9B5F`

`$9B5F` reads the 8 bytes at `$074D`, splits each into two nibbles, writes
`$0650[0..15]`, clears `$0670[0..15]`, and then applies `$0746` match
results from the `$0755/$0756` bitstream using the `$8941` table.

Verified in romdev (password screen, bank5 mapped):

```
$074D = 01 23 45 67 89 AB CD EF
$0746 = 00
call $9B5F
$0650 = 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
```

So the decode is a pure 4-bit unpack plus result application, not a
checksum/encryption step.

## 32-team / 5-round proposal

A 32-team bracket needs:

- 32 seed ids (5 bits each = 160 bits) **or** a deterministic seed order
  plus a 32-bit seed;
- 31 match results (one bit each);
- a version/checksum.

Two viable encodings:

1. **Seed-order + result bits (recommended):** 32-bit seed (8 hex digits)
   reproduces the shuffled 32-team order from a deterministic PRNG; 31
   result bits (8 hex digits) drive the 31-match heap; 1 version/checksum
   byte. Total 16 hex characters, same order of magnitude as the stock
   password and fits the existing 8-character display with two pages or a
   16-character mode.
2. **Full 5-bit packed ids:** 32 x 5 = 160 bits = 20 bytes = 40 hex
   characters. Too long for the current screen without a new layout.

The 32-team encode/decode should live in the same bank5 area as `$98D5`/
`$9B5F` but use a new buffer (e.g., `$0760-$077F`) and leave the stock
`$074D` path untouched for the 16-team game.
