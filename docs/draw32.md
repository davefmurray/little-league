# Repeatable random tournaments

Accepted in the final `title32` build. The [combined gate](verification/frontend32-gate.txt),
[CPU suite](verification/frontend32-draw-cpu.txt), [independent review](verification/frontend32-review.txt)
and resume matrix below cover this stage.

A new championship keeps the chosen team in the first match and shuffles the
other 31 teams. Its saved draw seed makes the order repeatable. Viewing the
bracket never shuffles it again. Passwords preserve that order, completed results
and all 32 human/CPU ownership bits.

Existing v1 passwords retain their ascending order and export the same v1 code.
New random tournaments use v2. The previous release rejects v2 codes through the
normal error screen. Reset ends the active series; passwords provide persistence
across resets. Exhibition and Power Analysis preserve the active series during
ordinary navigation.

## Frozen draw and password contract

The selected team is an ID from 0 to 31. The draw seed is a separate 14-bit value.
Zero selects the legacy ascending order. Values 1 through 16383 select random
orders. The former `password32.py --seed` argument continues to mean team ID.

For a nonzero draw seed, the initial 16-bit random state is `seed XOR $9E37`.
Advance xorshift16 twice before shuffling. Each step applies these operations,
truncating to 16 bits after left shifts:

```
x ^= x << 7
x ^= x >> 9
x ^= x << 8
```

Start with the chosen team followed by the other IDs in ascending order. For
`i=31` down through `2`, advance the random state once and swap slots `i` and
`1 + ((state * i) >> 16)`. Slot 0 never moves. The new-series entry captures
`(($33 << 6) XOR $07F3) AND $3FFF` and maps zero to one. These are timing inputs;
the draw does not consume the gameplay RNG.

The finite family has 16,383 distinct random orders per selected team in the
exhaustively enumerated prototype. It does not sample all possible orders, and
human timing is not assumed uniform. The measured CPU draw maximum over that
family was 10,082 cycles on the CPU model, excluding interrupt work. This is a
bounded execution measurement, not a hardware timing guarantee.

The password remains 22 symbols with the existing alphabet, aliases, whitening
and CRC-16. Payload bytes are:

| Bytes | Meaning |
|---|---|
| 0 | `$08` for v1; `$10` for v2. Other bits must be zero. |
| 1 low five bits | Selected team. |
| 1 high three bits | V2 draw-seed bits 8–10; zero in v1. |
| 2 low five bits | Completed match count, 0–31. |
| 2 high three bits | V2 draw-seed bits 11–13; zero in v1. |
| 3–6 | Little-endian result bits. A set bit means the second heap team won. Bits at or above the completed count must be zero. |
| 7–10 | Little-endian CPU ownership mask. Set means CPU. |
| 11 | V2 draw-seed bits 0–7; zero in v1. |
| 12–13 | CRC-16/CCITT-FALSE over bytes 0–11, big-endian. |

V2 with seed zero is invalid. Seed zero has one canonical representation, v1.
The decoder validates CRC and version before normalizing fields for the existing
semantic checks. A rejected code cannot change the live heap, mask or saved seed.

These fields and the draw algorithm form one versioned contract. The unused
experimental 18-bit proposal also called itself v2 but encoded different seeds;
its interpretation is unsupported. Because the prototypes reused a version
byte and CRC domain, some experimental codes also parse under this production
layout with a different meaning. Only this layout and draw algorithm ship.
Future incompatible changes require a different version.

## Byte ownership

`draw32` consumes frozen `menuart32` and owns only these new regions and hooks:

| Bank | Address | Role |
|---|---|---|
| 11 | `$8220–$82CE` | New-series capture, restored seed and shuffle. |
| 11 | `$8607–$8608` | Password restore's seeder-call operand. |
| 11 | `$86F0–$86F1` | New-series seeder-call operand. |
| 12 | `$8058–$805A` | Version gate hook. |
| 12 | `$8114–$8115` | Encoder's CRC-call operand. |
| 12 | `$8200–$8286` | V2 normalization and encoding fields. |

The seed lives in WRAM `$7760/$7761`. Only new-series commit and successful
restore write it. Decoder scratch `$0633/$0634` holds the decoded seed after
CRC validation; the shuffle uses zero page `$00–$08`. New WRAM accesses occur
with CHR banks `(0,1)`, matching the existing heap paths.

No earlier builder or codec exporter changes. The fixed bank, header, CHR,
existing result handling and ownership rules remain unchanged by this stage.

## Runtime resume matrix

The final ROM is exercised at completed counts 0, 1, 15, 16, 23, 27, 29,
30 and 31 with both legacy seed 0 and random seed $1234. Each unfinished
checkpoint then plays its next game. The subsequent games use SPEED mode,
which forces both sides to CPU on field entry. Password entry itself is
controller-only. The log records every command, ROM hash, restored heap check
and game-over result: [resume matrix](verification/frontend32-resume.txt).

Reproduce the matrix from the repository root:

```sh
mkdir -p build/frontend-resume
for draw in 0 4660; do
  for played in 0 1 15 16 23 27 29 30 31; do
    stem="$PWD/build/frontend-resume/d${draw}-k${played}"
    menu=continue
    if (( played % 2 )); then menu=list; fi
    .venv/bin/python tools/probe_password_ui.py --rom build/title32.nes \
      --seed 31 --draw-seed "$draw" --played "$played" --menu "$menu" \
      --session frontend-resume --shot "$stem.png" --state-path "$stem.state"
    if (( played < 31 )); then
      .venv/bin/python tools/soak_bracket.py --rom build/title32.nes \
        --bracket-state "$stem.state" --matches 1 --winner live-score \
        --require-complete --check-stack --mode speed --session frontend-resume
    fi
  done
done
```

## Memory and invalid-input checks

The final ROM rejects a corrupted v2 code and accepts the corrected code through
its keyboard: [runtime log](verification/frontend32-invalid.txt). A new-series
WATCH game traced 66,378 frames and 12 seed accesses; restore/LIST/CONTINUE traced
1,179 frames and 16 accesses. Every observed access to `$7760-$777F` stayed at
`$7760/$7761` in the owned instruction sites. Event PCs alone do not identify the
mapped PRG bank; CPU and mapper checks cover that separately.

```sh
.venv/bin/python tools/probe_draw_memory.py --report build/draw-memory.json   tools/soak_bracket.py --rom build/title32.nes --team 31 --matches 1   --mode watch --winner live-score --require-complete --check-stack --session draw-memory
.venv/bin/python tools/probe_draw_memory.py --report build/restore-memory.json   tools/probe_password_ui.py --rom build/title32.nes --draw-seed 4660   --played 24 --list-flow --session restore-memory --shot build/restore-memory.png
```

Reports: [new series](verification/frontend32-newdraw-wram.json),
[restore/list](verification/frontend32-wram.json). Startup, savestate loading and
direct CPU calls are outside these runtime trace windows.
