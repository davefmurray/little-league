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


## Implemented model: `tools/password32.py`

The 32-team proposal is implemented and tested as a pure model:

```
8 bytes = 16 hex chars
  bytes 0-3  seed, little-endian 32-bit
  bytes 4-7  result bits 0-30 (1 = team A wins)
             bit 31 = version (1 = 32-team format)

seed order = Fisher-Yates 0..31 with an xorshift32 stream:
  x ^= x << 13; x ^= x >> 17; x ^= x << 5
  state = seed or 0x9E3779B9
  for i = 31..1: state = next(state); j = state % (i+1); swap(i, j)

match m: slots[2m] vs slots[2m+1]; winner -> slots[32+m]
champion = slots[62]
```

Commands:

```sh
python3 tools/password32.py test                   # 100 random round-trips
python3 tools/password32.py encode --seed 0x12345678 --results 0x01234567
python3 tools/password32.py decode 7856341267452381
```

Verified: 100/100 encode-decode round-trips match the Python heap model;
seed 0 with all-A wins gives a valid champion; the example above decodes to
seed `0x12345678`, results `0x01234567`, champion `05`.

This is the format/model layer. Wiring it into the stock password screen
and leaving the 16-team `$074D` path untouched is the next P2 step.


## Letter rendering (model)

`tools/password32.py` now has a letter codec alongside the hex form:

```python
LETTERS = "ABCDEFGHIJKLMNOP"
encode_letters(seed, results) -> 16 letters
decode_letters(text) -> (seed, results, order, slots)
```

Example: `--seed 0x12345678 --results 0x01234567` encodes to
`HIFGDEBCGHEFCDIB` and decodes back to the same seed/results.

`python3 tools/password32.py test` now runs **100 hex + 100 letter**
round-trips. The stock password screen's `$06B5` buffer is 11 characters,
so a 16-letter password still needs a wider buffer or an 11-letter
compression; the actual stock letter alphabet (the S/U table) also needs to
be mapped before ROM wiring.


## Stock tile alphabet (candidate)

Bank5 `$908B` holds 16 tile codes:

```
35 37 48 4A 4B 4D 4F 51 53 55 65 67 68 6A 6C 6E
```

The live password screen's `$06B5` text used `$53`/`$55`, which are entries
8/9 of this table. `tools/password32.py` now has:

```python
STOCK_TILES = bytes([...])
encode_stock(seed, results) -> 16 tile codes
decode_stock(raw) -> (seed, results, order, slots)
```

Example: `--seed 0x12345678 --results 0x01234567` gives
`51 53 4D 4F 4A 4B 37 48 4F 51 4B 4D 48 4A 53 37`.

The glyphs still need to be confirmed against the password CHR bank, and the
stock `$06B5` buffer is 11 characters, so the 16-tile form still needs a
wider buffer or an 11-tile compression before ROM wiring.


## 11-character screen decision

The stock `$06B5` buffer is 11 characters. A full 32-bit seed + 31-bit
results + version is 64 bits; 11 characters at 4 bits each is only 44 bits,
so the full model cannot fit.

Chosen fallback for the 11-char screen:

- 16-bit seed + 31-bit results + 1 version bit = 48 bits;
- **10 base-32 characters** (50 bits) + **1 XOR checksum** = 11 characters;
- `encode_short` / `decode_short` in `tools/password32.py`, 100 round-trips.

Example: `encode_short(0x1234, 0x01234567)` -> `EBENCWOERUX`.

This needs 32 glyphs instead of the stock 16; the existing 16-glyph font
would need a two-screen form or a wider buffer. The full 32-team model
remains `encode`/`decode`; the short form is only for the stock-width screen.


## Live password screen + stock alphabet (confirmed)

`tools/render_ppu.py` reads the emulator's live `nes_nametables`, `nes_chr`,
and `nes_palette` regions through romdev and renders the screen. At the
password scene this produced `docs/password-screen-live.png`:

```
PASS WORD
UUUUUU UUUJUU
SSSSSU SSUU
```

The `$06B5` buffer at that moment is `SSSSSU SSUU`. The bank5 `$908B`
table values are ASCII screen codes, not tile IDs:

```
5 7 H J K M O Q S U e g h j l n
```

S (`$53`), U (`$55`), and J (`$4A`) are all visible on the live screen,
confirming the alphabet. `tools/password32.py` now has
`encode_stock_ascii`/`decode_stock_ascii` for the 16-character form, with
100 round-trips.

The screen is 11 characters = 44 bits at 4 bits/symbol. The 32-team model
needs 64 bits, so it needs **16 characters** (a wider screen) or a larger
alphabet; 11 characters cannot carry the full model.
