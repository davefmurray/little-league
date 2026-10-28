# Remaining work

The software backlog is complete. Physical hardware/audio validation is
the one blocked item in [docs/backlog.json](docs/backlog.json). It requires
an external console/flash-cart setup and independent emulator applications.
See [hardware-sound.md](docs/hardware-sound.md) for the matrix.

The accepted source pipeline produces `build/menuart32.nes`, SHA-256
`bcb7fcdc2c1decd47de2f3504c8c81d907a3d195629a1526ff4b0e919a89f2a3`.
It passes the final stock-six/full-31 SPEED gate. Controller probes cover
all five matchup labels, password restore, high-team human play and flag
omission. The new selector and bracket add NES artwork and stock menu
music. All 32 selections and audio activity pass emulator checks.
Independent review found no assembly blocker; its two build-output guard
findings were fixed and covered by CLI regressions.

Known limitations remain explicit. High gameplay flags remain omitted;
high uniforms reuse stock presets; selector flags are simplified to
16-by-8 pixels; the bracket has no elimination marks. The
source pipeline still requires the existing `direct20-names.nes` bootstrap
artifact. The ROM header declares no battery-backed persistence; passwords
are the supported resume path.

See [32-team-status.md](docs/32-team-status.md) for stage evidence and
[HANDOFF.md](docs/HANDOFF.md) for maintained invariants.
