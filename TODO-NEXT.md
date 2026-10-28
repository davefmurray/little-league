# Remaining work

The authoritative queue is [docs/backlog.json](docs/backlog.json).
Run `python3 tools/backlog.py pick` to select the next ready item.
The former investigation log in this file is preserved in git history;
its 32-byte lineup premise and password-buffer assumptions were disproved.

1. Repair matchup round labels using the actual 32-team match index.
2. Bound gameplay flag reads. Preserve stock low-team flags and omit high
   flags until real artwork is available.
3. Extend uniform palettes. Preserve low-team palettes and explicitly
   assign their valid presets to teams 16-31.
4. Run physical hardware/audio validation. This requires an external
   console/flash-cart setup and is blocked in this environment. See
   [hardware-sound.md](docs/hardware-sound.md).

Start the next visual-table unit from `build/teamnames32.nes` (`5998632d`).
Accepted work and evidence are summarized in
[32-team-status.md](docs/32-team-status.md). Password, LIST, CONTINUE, all
32 human selections, completed-game results, real high-team names and
both 31-match SPEED and WATCH gates have passed their documented checks.
