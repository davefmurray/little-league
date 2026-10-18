# Text table (TBL) and text locations

Source: DataCrystal TBL capture. The game's font tiles follow ASCII for the
subset used:

| Byte | Character |
|---|---|
| `20` | space |
| `30–39` | `0–9` |
| `41–5A` | `A–Z` |

No punctuation beyond space is mapped. Tiles outside this range are graphics or
unmapped symbols; treat a hit there as binary data, not text.

Files:

- `data/llbcs.tbl` — the table in standard `.tbl` form.
- `tools/tbl.py` — encode/decode/scan.

```sh
python3 tools/tbl.py --encode "NEW YORK"
# 4e 45 57 20 59 4f 52 4b

python3 tools/tbl.py --decode 5445414d2053454c454354
# TEAM SELECT

python3 tools/tbl.py ROM --scan --min 4
python3 tools/tbl.py ROM --at 0x5190 --len 64
```

## Verified text locations

Scan hits (file offsets):

| Offset | Text | Notes |
|---|---|---|
| `0x05190` | `JAPAN` + padding | long team names; CPU `$9180` |
| `0x051E0` | `NEW YORK` | second name table |
| `0x052B1` | `JAPAN` | another name copy |
| `0x052F5` | `NEW YORK` | |
| `0x0537E` | `JAPAN` | |
| `0x0568A` | `LIST OF TEAMS` | menu string, bank 1 |
| `0x05AB8` | `CENTER` | position label |
| `0x07306` | `JAPAN` | bank 3 copy |
| `0x07336` | `NEW YORK` | |

The `0x5190` hit matches our long-team-name table at CPU `$9180`. `0x51E0`
matches the second name table we had documented loosely as "short names"; it is
a full-name copy, not abbreviations.

## Caveats

- The scanner finds **tile data** that happens to fall in `$41–$5A`
  (e.g. `BYUBYUB`, `HGIJKLMH`). Always inspect the surrounding bytes.
- Strings are often padded with spaces and terminated by `$FF`.
- `0x20` must map to a real space in the `.tbl`; an empty mapping silently
  drops spaces when decoding.
