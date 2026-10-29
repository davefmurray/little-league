# modeart32 PNG guard follow-up review

**Decision: REQUEST CHANGES.** The original ROM/source/data alias corruption is fixed. One remaining P2 defect lets an explicit JSON or preview output collide with a generated PNG when that PNG is initially absent. Both real CLI reproductions return success and leave the generated art inconsistent. No repository artifact was changed.

**Scope.** Fresh read-only review of `tools/modeart32_convert.py`, the new `test_png_regeneration` regression and relevant callers/guards in `test_modeart32.py`, `build_modeart32.py`, `build_title32.py`, `build_draw32.py` and the preceding output-guard chain. Compared the converter with the original extracted from `/tmp/ll-modeart32-impl/integration/modeart32-tools.patch`. Read the original review and supplied regeneration log. No repository edits, commits, pushes, delegation or emulator/romdev calls. Every dangerous alias points exclusively to scratch copies under `/tmp/ll-modeart32-guard-review`.

**Finding 1 — [P2] Exact JSON/preview collisions are filtered out of PNG preflight.**

Location: `tools/modeart32_convert.py:282`, with the explicit outputs supplied at line 356 and written at lines 365–367. Missing regression: `tools/test_modeart32.py:test_png_regeneration` covers distinct hardlink/symlink aliases but does not cover an explicit output naming an initially missing generated destination.

`install_pngs` combines protected inputs, explicit `outputs` and generated `targets`, then excludes **every** entry whose absolute path equals the current target. Excluding the target's own normal art entry is necessary to permit regeneration, but this also excludes an explicit `--out` or `--preview` that names that very destination. The earlier `protect_output` call cannot discover a missing PNG through `protected_paths(...).rglob(...)`.

Concrete trigger: remove a generated sprite in a scratch checkout, then run regeneration with `--out art/modeart32/out/sprites/woman.png` or `--preview art/modeart32/out/sprites/woman.png`. These are ordinary repository-relative arguments; no monkeypatch or path race is involved. The renderer installs the PNG, and the later JSON/preview writer overwrites it.

Independent real subprocess measurements, using fresh copied tools/art/data/ROM for each case:

| Explicit output | CLI result | Final contents of `sprites/woman.png` | Next `--check --pxl` |
|---|---|---|---|
| `--out` | exit 0 | 11,325-byte `modeassets/1` JSON, SHA256 `9af59518eb1d917f2705073d4351145fa73e0fd030db93f140aaaba36ad0a01f` | exit 2, cannot identify image |
| `--preview` | exit 0 | 10,383-byte, 768×240 preview; expected sprite is 16×46 | exit 2, sprite differs from pinned render |

Both probes also placed a sentinel in the earlier `scenes/mode.png`; regeneration replaced it. The collision is therefore accepted through the complete installation, rather than rejected before persistent writes. This does not reproduce corruption of the protected input ROM or source/data files. It is a remaining output-consistency defect in the requested batch preflight.

**Requested change:** check every generated target against the explicit JSON/preview outputs without the self-path exemption. Restrict that exemption to the intended existing art/target entry. Add initially missing destination cases for both options, asserting rejection before any PNG, JSON or preview changes. Keep the existing successful canonical regeneration and link tests.

Reproduction runner: `/tmp/ll-modeart32-guard-review/collision_repro.py`. It creates new scratch copies on each run. Exact commands, working directories, results and subsequent check failures are in `collision-and-explicit-guards.json`; `collision-repro.log` contains the observed output. An earlier absolute-path probe is recorded separately in `exact-collisions.json`.

**Original critical finding: fixed and independently verified.**

The original converter, restored only in scratch from the integration patch, reproduced the original exploit through both a hardlink and a symlink at `out/sprites/dad.png`. Each real `--pxl` subprocess returned exit 0 while changing its copied title32 input from 393,232 bytes to the 265-byte dad PNG, SHA256 `d05967d0cc34c8cca87a8c1be1f610c0645a6b2c3fb128bb6414fbba0c574c82`. Its emitted JSON still matched the pinned hash. This establishes that the test setup exercises the original failure.

The fixed converter renders into temporary storage, completes the target loop before starting installation, and writes each PNG through a sibling temporary file plus `os.replace`. Its calls to `protected_paths`, the preceding stage guard and `refuse_aliases` cover the supplied ROM path, protected content hashes, source/art/data and output aliases. `main`, `render_pxl` and `check_pxl` pass the actual ROM path consistently; the remaining test caller supplies its title32 path. Other converters' similarly named functions are separate modules.

Independent checks in `independent.py`, exit 0, **44.316 seconds**:

- **16 real CLI rejection cases:** hardlink and symlink aliases to the actual ROM, JS source, layout, pxl lock, canonical assets, team data, converter source and another generated destination. The trap was the last sorted PNG. Each rejection left all **257 persistent project entries** identical, including file contents, inode identities, modes, modification times and symlink targets. Existing JSON and preview outputs were included.
- **16 helper rejection cases:** both alias kinds against the actual ROM, SOURCE, LAYOUT, LOCK, ASSETS, JSON output, preview output and an earlier generated PNG. Full scratch-tree snapshots remained identical. These exercise explicit JSON/preview aliases independently of the CLI's earlier guards.
- An independent copy of the ROM under a different filename/inode was rejected by its content hash. Two initially absent generated destinations resolving to the same path through a parent-directory symlink were rejected without creating outputs.
- Replacement of an unrelated hardlink and an unrelated symlink preserved the referenced file's contents and inode, installed the intended regular PNG and severed the output alias. All **12 installed PNGs** matched staging byte for byte.
- Two ordinary real `--pxl --preview` regenerations from another working directory succeeded, reproduced all **12 PNGs** byte for byte, and produced the pinned JSON. Output was **254 tiles, 2 free, 3 text rows**. Preview SHA256 was `d234357a84c7d3695fa93e8c5cc285b46f8fc9ba964ee43efd8080fdf870c202` on both runs. Source/data/ROM identities remained unchanged. Canonical JSON regeneration also succeeded.
- Current JSON checks with and without pxl succeeded without persistent writes. Stale and missing JSON checks failed without changing or creating persistent outputs. Both hardlink and symlink forms of the supplied ROM argument remained protected.
- Reran only the supplied `test_png_regeneration(base, PXL)`: all **12 helper alias cases**, unrelated-hardlink preservation and **two real-render CLI cases** passed. Its output is saved in `supplied-regression.log`. No CPU test function was called.

Additional checks in `collision_repro.py`, exit 0, **11.807 seconds**, reproduce Finding 1 and verify **24 explicit output-guard rejection cases**: direct/hardlink/symlink destinations against ROM, JS source, team data and scene PNG, each as `--out` and `--preview`. Every rejection preserved the entire scratch-tree snapshot. `--check --preview` also rejected without writes. The runner's successful exit means its assertions passed, including assertions demonstrating the two accepted collisions; it does not mean the converter is free of defects.

**Commands and environment.** From `/Users/dfm/GitHub/nesdav/little-league`, the two saved runners were executed as:

```sh
.venv/bin/python -B /tmp/ll-modeart32-guard-review/independent.py > /tmp/ll-modeart32-guard-review/independent.log 2>&1
.venv/bin/python -B /tmp/ll-modeart32-guard-review/collision_repro.py > /tmp/ll-modeart32-guard-review/collision-repro.log 2>&1
```

The runners use scratch temporary storage and invoke the pinned renderer read-only at `build/vendor/claude-pxl`, commit `3bc816cb15a14592e0dc062ee98013637d399457`, with Node `v26.7.0`. They copy tools/art/data and title32 before constructing aliases. The original converter was extracted as text, not applied to the repository. Full subprocess argument lists and per-case measurements are retained in `evidence.json` and `collision-and-explicit-guards.json`.

**Report-only no-comments audit.** Applied the no-comments lens directly without spawning an agent, as instructed. The new installer and regeneration regression introduce no explanatory comments, lint/type suppressions, TODO workarounds or permission-only constraints. The render/check docstrings describe their callable contracts; protection is implemented and tested at the write boundary. The pre-existing broad `protected_paths` docstring is not evidence that every consumer handles exemptions correctly. Finding 1 needs a runtime collision check and regression cases. No comment-only findings or `MUST KILL` flags in this follow-up's changed scope. Source files touched: 0; deletions: 0; restorations: 0; encoding offers: 0. No unrelated runtime-comment cleanup was attempted.

**Artifact preservation and limits.** SHA256 inventories of **237 repository source/art/data/ROM files** matched before testing, after the primary runner and after the supplemental reproductions. Records: `repo-before.json`, `repo-after.json`, `repo-final.json`.

| Artifact | Unchanged SHA256 |
|---|---|
| title32 input | `8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c` |
| modeart32 ROM | `7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9` |
| modeassets JSON | `9af59518eb1d917f2705073d4351145fa73e0fd030db93f140aaaba36ad0a01f` |
| reviewed converter | `b8d1b3cb528e27a1beafd58808c8de71939f2b61cecf69d6a36b4fa98cbfdad7` |
| reviewed test tool | `2b53d74ad721635cd92f2f0f12c616c4a16302414718fb05c9385b8053b1be33` |

No whole-ROM/runtime review was repeated. The full CPU rerun in `docs/verification/modeart32-cpu.txt` was not read or polled; this report makes no claim about its completion. The approval blocker remaining from this follow-up is Finding 1 above.
