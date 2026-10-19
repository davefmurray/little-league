# Project skills

Skills live in `.claude/skills/` and load automatically in new sessions.

| Skill | Use when |
|---|---|
| `llbcs-32-team` | Editing teams, rosters, brackets, banks, selector, or launching games from the hack |
| `nes-romdev-debug` | Tracing a NES routine, breakpoints, CPU calls, memory regions, emulator verification |
| `nes-display-lists` | Building or debugging text screens, blank/garbled displays, run lengths, RLE |
| `mmc1` | MMC1 bank/mode/PRG-RAM semantics and 512 KiB traps |
| `romdev` | Full romdev tool catalog and multi-platform reference |

The three project skills above encode lessons that cost real debugging time:
the `$CBE6` hook is not a routine, PRG RAM needs CHR0 bit 4 clear, NMI can
corrupt a seed, `"NY"` breaks a display list, and zero-page operands are 2
bytes. Read the relevant skill before repeating those experiments.
