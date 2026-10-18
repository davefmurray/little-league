# Cheat codes, RAM map, and translated Game Genie patches

Sources:

- <https://gamehacking.org/game/30118> — Little League Baseball (NES) codes.
- <https://github.com/Fordi/nes-gg> — NES Game Genie encode/decode algorithm.
- <https://www.nesdev.org/wiki/Game_Genie> — hardware behavior.
- <https://datacrystal.tcrf.net/wiki/Little_League_Baseball:_Championship_Series/ROM_map>
  — **blocked by Cloudflare at capture time**; no Wayback snapshot. Pending.

The GameHacking page lists two different kinds of codes:

- **Standard codes** like `0488:??` are **RAM addresses**, not ROM offsets.
- **Game Genie codes** are ROM patches: 15-bit CPU address, 8-bit data, optional
  8-bit compare.

## Game Genie decoding

NES Game Genie alphabet:

```
hex  0123456789ABCDEF
GG   APZLGITYEOXUKSVN
```

For an 8-letter code, the address is 15 bits and the compare byte selects the
bank. The decoder used here is the `nes-gg` algorithm; the compare byte matched
exactly one bank for every code below.

## Translated codes

| Code | Label | CPU | Bank | File offset | Old → New | What it does |
|---|---|---|---|---|---|---|
| `OZUITLEN` | Balls Are Strikes | `$D336` | 7 (fixed) | `0x1D346` | `F0` → `A9` | `BEQ $D33B` becomes `LDA #$03`, then falls into `JMP $D412` |
| `UPEUYLOG` | Hit A Homerun #1 | `$B30F` | 6 | `0x1B31F` | `C1` → `93` | operand of `LDA $C1` at `$B30E` becomes `LDA $93` |
| `AGOLPUNI` | Hit A Homerun #2 | `$B311` | 6 | `0x1B321` | `DF` → `40` | operand of `AND #$DF` at `$B310` becomes `AND #$40` |
| `OXVXSKPX` | Skip Intro Screen | `$ACED` | 0 | `0x2CFD` | `29` → `A9` | `AND #$10` becomes `LDA #$10` (always nonzero) |

Disassembly context:

```
$D331  LDA $C1
$D333  BIT $C001
$D336  BEQ $D33B        ; OZUITLEN patches this
$D338  JMP $D412
$D33B  AND #$80
```

```
$B30E  LDA $C1          ; UPEUYLOG changes the operand $C1 -> $93
$B310  AND #$DF         ; AGOLPUNI changes the operand $DF -> $40
$B312  STA $C1
$B314  RTS
```

```
$ACEB  ORA $92
$ACED  AND #$10         ; OXVXSKPX changes the opcode $29 -> $A9
$ACEF  BNE $AD34
$ACF1  RTS
```

Note that a Game Genie address can hit an **operand byte**, not just an opcode
(`UPEUYLOG`, `AGOLPUNI`). Always disassemble around the address before assuming
it is an instruction start.

## Standard-code RAM map

| Code | Address | Meaning |
|---|---|---|
| `00C0:11` | `$00C0` | Ball travels a long distance (write `$11`) |
| `0487:??` | `$0487` | Strikes modifier |
| `0488:??` | `$0488` | Ball modifier |
| `0489:??` | `$0489` | Out modifier |
| `048B:??` | `$048B` | Team 2 score |
| `048C:??` | `$048C` | Team 1 score |

These are useful anchors for a RAM map; they sit below the bracket/state area
(`$0650+`) used elsewhere in this repo.

## Cross-check with our map

- `$D336` is in the fixed bank; our fixed bank is 15 in the expanded ROM, so the
  same code lives at bank 15 and the file offset moves.
- `$B30F/$B311` are in bank 6, which our 32-team build does not relocate.
- `$ACED` is in bank 0, unchanged.

## Pending

- Capture the DataCrystal ROM map through a browser session and reconcile it with
  `docs/roster-format.md` and this file.
- Test the two "Hit A Homerun" codes independently; they patch adjacent bytes in
  the same routine and may be alternatives rather than a pair.
