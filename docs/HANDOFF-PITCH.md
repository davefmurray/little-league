# Retired pitch investigation

Use [HANDOFF.md](HANDOFF.md) and [32-team-status.md](32-team-status.md).
The former capture/restore proposal and 32-byte `$06E2` model were
incorrect. Their historical record remains in git and AUTORUN-REPORT.md.

`$06E2-$06F3` is an 18-byte lineup for nine batting rows on two sides.
The adjacent bytes are line scores. The accepted gameplay repair fixes
the source loader for teams 28-31 while preserving the stock lineup
readers and writers. Later CPU and role stages repair pitcher tables,
record layout and flags. Do not resume the abandoned pair-chain patches.

See [gameplay32.md](gameplay32.md), [cpu32.md](cpu32.md) and
[roles32.md](roles32.md) for implemented behavior and executable evidence.
