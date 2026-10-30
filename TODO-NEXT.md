# Remaining work

The software backlog is complete. Physical hardware/audio validation is
the one blocked item in [docs/backlog.json](docs/backlog.json). It requires
an external console/flash-cart setup and independent emulator applications.
See [hardware-sound.md](docs/hardware-sound.md) for the matrix.

The accepted source pipeline produces `build/analysisart32.nes`, SHA-256
`1e524b53946ac45f1560c1908659c3a44c0f10088205403f6e79ae5033fcb94e`.
The new stages add repeatable random draws, v2 passwords, a shared picker
for Exhibition and Power Analysis, title artwork and the colorful ballpark
mode menu, matching scoreboard and baseball-marker Power Analysis card
with original game characters and crowd.
See [analysisart32](docs/analysisart32.md)
for final-stage evidence. The reusable [pxl/NES screen-art skill](https://github.com/davefmurray/AWESOME-NESDEV/tree/main/skills/nes-pxl-screen-art)
is published in AWESOME-NESDEV (commit `408bac9`).
The source rebuild, CPU suites and stock-six/random-full-31 gate pass. Controller checks cover
all 32 Analysis teams, both input ports and password resume. Final modeart32
completes 2P and WATCH exhibitions; its 1P coverage is setup and human field
entry. Full 1P completion belongs to the earlier title32 stage. Independent
review found no ROM correctness blocker; output guard findings are fixed and covered by CLI regressions.

Known limitations remain explicit. High gameplay flags remain omitted;
high uniforms reuse stock presets; selector flags are simplified to
16-by-8 pixels; the bracket has no elimination marks. The
source pipeline still requires the existing `direct20-names.nes` bootstrap
artifact. The ROM header declares no battery-backed persistence; passwords
are the supported resume path.

See [32-team-status.md](docs/32-team-status.md) for stage evidence and
[HANDOFF.md](docs/HANDOFF.md) for maintained invariants.
