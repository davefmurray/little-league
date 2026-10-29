# Remaining work

The software backlog is complete. Physical hardware/audio validation is
the one blocked item in [docs/backlog.json](docs/backlog.json). It requires
an external console/flash-cart setup and independent emulator applications.
See [hardware-sound.md](docs/hardware-sound.md) for the matrix.

The accepted source pipeline produces `build/title32.nes`, SHA-256
`8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`.
The new stages add repeatable random draws, v2 passwords, a shared picker
for Exhibition and Power Analysis, and title artwork. The source rebuild,
CPU suites and stock-six/random-full-31 gate pass. Controller checks cover
all 32 Analysis teams, both input ports, 1P/2P/WATCH exhibitions and v1/v2
resume. Independent review found no ROM correctness blocker; output guard
findings are fixed and covered by CLI regressions.

Known limitations remain explicit. High gameplay flags remain omitted;
high uniforms reuse stock presets; selector flags are simplified to
16-by-8 pixels; the bracket has no elimination marks. The
source pipeline still requires the existing `direct20-names.nes` bootstrap
artifact. The ROM header declares no battery-backed persistence; passwords
are the supported resume path.

See [32-team-status.md](docs/32-team-status.md) for stage evidence and
[HANDOFF.md](docs/HANDOFF.md) for maintained invariants.
