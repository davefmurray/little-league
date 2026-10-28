# Restore tournaments and browse the 32-team list

`build/password32.nes` displays and accepts the existing 22-symbol password
screen. A valid v1 password restores the entire tournament heap, completed
matches and four ownership bytes before showing the bracket. Stock
16-team championship passwords are rejected. The original codec bytes
remain unchanged for parity checks and fallback display behavior.

CONTINUE PLAY opens the current 32-team bracket. LIST OF TEAMS opens the
same 32-team grid in view mode; A or B returns to the title. Buttons held
on entry are ignored, and exit waits for release. A completed tournament
always uses view mode, including when reopened through CONTINUE.
The grid lists every seeded team and the last winner; it does not mark
all eliminated teams.

The guarded input is control32
`a1caf9a28e750a777343f2bdbd5c02987a03ccac0f58b6257e62dbee0faf30a8`.
The output is
`978abc4227eac24d0c779ea3fbbdfdc42c89ca0a1fcce350cff6db44501da34a`,
with 902 changed bytes. Earlier pipeline stages remain pinned.

| Region | Content |
|---|---|
| Bank 12 `$8000-$81AA` | Decode, encode, CRC and whitening |
| Bank 12 `$8F00-$8F7D`, with gaps | Alphabet and format tables |
| Bank 11 `$8600-$8670`, `$8678-$867F` | Bracket restore and bit table |
| Bank 11 `$8680-$86D6` | View dispatch and controller loop |
| Fixed `$FCC0-$FCE1` | Decode and restore bank switching |
| Fixed `$FCE2-$FCFD` | Format-aware encoder call |
| Fixed `$FEA0-$FEC8` | Active-series list and bracket entry |
| Bank 1 `$BE40-$BE64` | CONTINUE routing |

Hooks replace the calls at bank1 `$A584`, bank5 `$9FF5`, title paths at
bank1 `$94F8/$951C`, and the bracket's final jump at bank11 `$808B`.
Mode dispatch requires both `$07ED!=0` and `$07EF=32`. The shared seed-once
entry at bank11 `$86E0` belongs to control32 and is unchanged here.
The bank1 name records end at `$BE3F`; they must not grow into the
CONTINUE helper at `$BE40`.

The additional CONTINUE hook fixes a runtime defect in the first integration
candidate. Restoring a completed tournament and returning to the title
left the old matchup scratch bytes uninitialized. CONTINUE read FF/FF
from them. It now opens the restored bracket, which derives a live matchup
only when an unfinished tournament is launched.

## Verification

The independent codec review approves the host model, bank12 routines and
bank11 restore. The reproducible suite runs 14 tests, with 2,050 CPU
decodes, 160 encodes and 1,056 restores. Maximum observed cycles are
25,869, 27,211 and 5,926 respectively in the CPU harness. These are
cycle counts reported by py65, without an executing NMI or PPU.
[Codec evidence](verification/password32-codec-cpu.txt).

Hook tests execute MMC1 serial writes and cross-bank calls, including
36 complete display/decode/restore cases, 66 rejected inputs, mode guards,
held-input view transitions and stock-codec preservation. The harness
models bank switching and controller reads but does not model NMI timing.
[Hook evidence](verification/password32-hooks-cpu.txt).

Real controller input typed passwords through both title menu paths at
completed-match counts 0, 1, 15, 16, 23, 27, 29, 30 and 31. Every heap,
index and mask matched. Each unfinished checkpoint then completed its
next game with a live-score winner check. Those match probes use SPEED
mode and may force CPU ownership on the field; password entry itself uses
only controller input. The finished bracket returns to the title and can
be reopened safely through CONTINUE.
[Resume evidence](verification/password32-resume.txt).

The displayed password equals the typed code after restore. Active LIST,
B back to title and CONTINUE preserve the same heap and index.
[List and display evidence](verification/password32-list.txt).
Corrupt-code rejection and corrected-code re-entry use the original error
screen and keyboard. [Error-path evidence](verification/password32-ui.txt).

The source pipeline reproduces the pinned ROM and the combined stock-six
and final-31 speed gate passes, champion 05.
[Pipeline](verification/password32-pipeline.txt),
[combined gate](verification/password32-gate.txt). Independent hook review
approves the ROM and the final evidence and output-guard changes.
Hardware/audio validation and high-team label corrections remain separate tasks.

## Reproduce controller verification

With the romdev server running, this loop reproduces the nine restore
checkpoints and the eight following games in the resume log. The probe
uses alternating result bits and a single human seed team. Odd completed
counts enter through LIST; even counts enter through CONTINUE.

```sh
set -eu
for played in 0 1 15 16 23 27 29 30 31; do
  menu=continue
  if [ $((played % 2)) -eq 1 ]; then menu=list; fi
  python3 -u tools/probe_password_ui.py --rom build/password32.nes \
    --seed 31 --played "$played" --menu "$menu" \
    --session password32-resume \
    --state-path "/tmp/password32-resume-$played.state" \
    --shot "/tmp/password32-k$played.png"
  if [ "$played" -lt 31 ]; then
    python3 -u tools/soak_bracket.py --rom build/password32.nes \
      --bracket-state "/tmp/password32-resume-$played.state" \
      --matches 1 --winner live-score --require-complete --check-stack \
      --session password32-resume
  fi
done
printf 'all 9 resume checkpoints passed\n'
```

The error and active-list probes are separate controller-only runs.

```sh
python3 -u tools/probe_password_ui.py --rom build/password32.nes \
  --seed 16 --played 0 --invalid --session password32-error \
  --shot /tmp/password32-error.png
python3 -u tools/probe_password_ui.py --rom build/password32.nes \
  --seed 16 --played 15 --list-flow --session password32-list \
  --shot /tmp/password32-list.png
```
