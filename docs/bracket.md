# Tournament bracket

## US 16-team table

- Location: bank 5, CPU `$8941` (file `0x14951`).
- 15 records × 3 bytes: `slotA, slotB, destSlot`.
- Round sizes: 8, 4, 2, 1.
- RAM:
  - `$0650` bracket slots (team IDs)
  - `$0670` loss counts
  - `$0746` current round
  - `$074B–$0756` password state

Code:

```
$9BA3  LDY $8941,X     ; slot A
$9BA6  LDA $0650,Y     ; team A
$9BAA  INC $0670,X     ; loss count
$9BAF  LDY $8943,X     ; destination
$9BB2  STA $0650,Y     ; advance
...
$9C08  LDY $8941,X     ; display: round*3
$9C0B  LDA $0650,Y     ; team A
$9C11  LDA $0651,Y     ; team B
```

Pointers to the table live at bank-5 `$9BA4` and `$9C09`.

## Decode

`python3 tools/bracket.py ROM` prints:

```
round 0 (8 matches)
  slot  0 vs  1  ->  16
  ...
round 3 (1 match)
  slot 28 vs 29  ->  30
```

## 32-team design

31 records × 3 = **93 bytes**:

```
00 01 20  02 03 21  04 05 22  06 07 23
08 09 24  0a 0b 25  0c 0d 26  0e 0f 27
10 11 28  12 13 29  14 15 2a  16 17 2b
18 19 2c  1a 1b 2d  1c 1d 2e  1e 1f 2f
20 21 30  22 23 31  24 25 32  26 27 33
28 29 34  2a 2b 35  2c 2d 36  2e 2f 37
30 31 38  32 33 39  34 35 3a  36 37 3b
38 39 3c  3a 3b 3d  3c 3d 3e
```

- Leaves 0–31 → 32–47 → 48–55 → 56–59 → 60–61 → 62.
- Generate with `python3 tools/bracket.py --gen32 --hex`.

## RAM blocker

32 teams need:

- 63 bracket slots (`0x3F`)
- 32 loss counts

= 95 bytes. The current region `$0650–$068F` is only 64 bytes and the loss
counts begin at `$0670`, so the 32-team table **cannot** be dropped in without
relocating RAM.

Options:

1. Move slots and loss counts to a larger free RAM block and patch every
   `$0650`/`$0670` reference (many sites).
2. Keep slots at `$0650` but spill rounds beyond `$067F` into a second area and
   add a base-offset helper.
3. Shrink loss counts to nibbles (32 teams → 16 bytes), buying 16 bytes but still
   16 short.

Recommended: option 1, after mapping all `$0650`/`$0670` references.

## Applied: table relocation

`tools/build_32bracket.py` writes the 31 records to fixed-bank `$FC00` and
repoints:

```
$9BA3  LDY $FC00,X   ; advance
$9C08  LDY $FC02,X   ; display
```

Verified by disassembly and the ROM boots. This is the **safe half**: it changes
no state format and cannot play a 32-team bracket yet.

## Applied: PRG-RAM state

`tools/build_32bracket.py` (default mode) now:

- seeds fixed `$FD00` with 32 bytes `0..31`;
- rewrites init at `$9B5F` to copy seeds to `$6800` and zero `$6840` (32 losses);
- repoints advance/display operands to `$6800`/`$6840`.

CPU-level validation (py65, bank 5 mapped):

```
init reached advance in 226 steps
slots  = 0,1,2,...,31
losses = 0 x32
round=4 advance returns at $9BC0 in 97 steps
champion slot 62 = 0
```

The ROM also boots to the title screen. Entry is not wired: the stock
team-select/password flow still seeds the old 16-team format, and the rewritten
init ignores that seed and starts from `0..31`.

## Next: state format

The init routine is the real blocker:

```
$9B63  LDA $074D,Y    ; 8 packed bytes = 16 team IDs
```

32 teams need 5-bit IDs and 32 seeds, but `$074D–$0754` is only 8 bytes and
`$0755/$0756` are password state. The loss array at `$0670` is also shared with
player/uniform variables (`$067B`, `$0684`, `$0685`, `$0689`).

Plan:

- New PRG-RAM bracket state: slots `$6800` (63 bytes), losses `$6840` (32).
- Patch only the bracket routines (`$9B5F–$9C40`) to use it, leaving shared
  arrays alone.
- New 32-byte seed table; stop packing two teams per byte.
- Then wire the 32-team team-select handoff.
