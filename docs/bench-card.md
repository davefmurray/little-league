# Bench and position card

The stock order menu uses the current match's nine-player lineup. It does
not need a wider lineup table when tournament team IDs extend to 31.

Bank1 `$9A1C` reads `$06E2 + row*2 + side` and uses its low nibble to
select a fielding-position label from `$9A70`. Those are eight-character
labels such as PITCHER and CATCHER, not player attributes. `$9A4E` uses
the high nibble as the roster player number for the name renderer `$CB17`.
The team ID comes from `$04EF/$04F0` through the roster-pointer path.

The earlier proposal to extend `$06E2` to 32 bytes and add a page offset
was incorrect. It overwrote score RAM and indexed beyond the live lineup.
The corrected gameplay build retains the stock 18-byte layout and menu.
See [gameplay32.md](gameplay32.md) for its CPU and runtime checks.

The stock bench scan considers player numbers 0-14. The packed lineup can
represent 0-15. Extra records in `data/roster32.json` do not by themselves
make players 16-19 selectable. A larger bench would require a separate
player-storage design and tests for substitutions, names, used flags and
pitcher state. It is not implemented by widening the team list.

Manual bench swaps and position-card rendering across all 32 teams still
need dedicated runtime coverage. The automated tournament soak checks
scene progression and winner writes, not every menu operation.
