# Remaining work

The software backlog is complete. Physical hardware/audio validation is
the one blocked item in [docs/backlog.json](docs/backlog.json). It requires
an external console/flash-cart setup and independent emulator applications.
See [hardware-sound.md](docs/hardware-sound.md) for the matrix.

The accepted source pipeline produces `build/visualtables32.nes`, SHA-256
`cf4f1126a4afde0cd04bd13f06ebbea2867029cba78cedb3944ee7b15d582780`.
It passes the final stock-six/full-31 SPEED gate. Controller probes cover
all five matchup labels, password restore, high-team human play and flag
omission. Independent review approves the guarded builders and CPU tests.

Known limitations remain explicit. High flags are omitted rather than
invented; high uniforms reuse stock presets; the 32-team selector flag
area is a placeholder; the bracket grid has no elimination marks. The
source pipeline still requires the existing `direct20-names.nes` bootstrap
artifact. The ROM header declares no battery-backed persistence; passwords
are the supported resume path.

See [32-team-status.md](docs/32-team-status.md) for stage evidence and
[HANDOFF.md](docs/HANDOFF.md) for maintained invariants.
