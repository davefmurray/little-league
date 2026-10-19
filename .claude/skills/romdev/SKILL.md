---
name: romdev
description: Homebrew retro game development and ROM reverse-engineering for 19 platforms (NES, SNES, Game Boy/Color, Genesis, GBA, Atari 2600/7800, Lynx, C64, SMS, Game Gear, PC Engine, MSX, GameTank, sync32, N64, PlayStation, Dreamcast). Use when building, running, debugging, disassembling, asset-converting, or romhacking a retro game - drives bundled emulators and toolchains over HTTP. NEVER install a host compiler/emulator; romdev bundles all of them as WASM (use the build tool).
metadata:
  version: "0.150.2"
---

romdev gives you homebrew retro game development + reverse-engineering for 19 platforms (NES, SNES, Game Boy, Genesis, GBA, Atari, C64, GameTank, sync32, the 3D consoles N64/PlayStation/Dreamcast, and more) - build, run, screenshot, inspect, patch, disassemble, convert assets, drive emulators.
It also ships a full RE analysis engine (Rizin + Ghidra, 18 platforms: all but sync32): control-flow graphs, cross-references, auto-detected functions, a one-shot structural map, and a C-pseudocode decompiler - `disasm({target:'cfg'|'xrefs'|'functions'|'decompile'})` and `symbols({op:'analyze'})`.

## HARD RULE: never install a compiler or emulator - romdev already bundles every one
Every compiler/assembler/linker (cc65, sdcc, gcc, arm/m68k/mips/sh-gcc, tcc, wla, rgbds, asar, dasm) and every emulator core ships as WASM INSIDE romdev and runs in-process through these tools - `build({output:'rom'|'run'})` compiles, `loadMedia`+`frame` runs. You do NOT need, and must NOT install, a host `clang`/`gcc`/Xcode/Command-Line-Tools/devkitPro/`brew`/`apt` compiler or any emulator to build or run a ROM here. If you catch yourself about to install or invoke a host compiler/emulator - STOP. That's never the move: use the romdev `build` tool. (`platform({op:'toolchains'})` lists what's bundled for each platform.) A compiler/emulator install kicking off while using romdev is a DEFECT to report, not a step to take.

## Prerequisite: romdev runs LOCALLY (same machine as you)
The romdev SERVER hosts all that bundled WASM in-process; start it once with `npx romdevtools` (listens on http://localhost:7331 - that single `npx` is the ONLY install, and it pulls the toolchains/cores as bundled WASM, never a host compiler). If a call gets connection-refused, the server isn't running - start it.
**romdev runs on the SAME machine as you, and tools take FILESYSTEM PATHS** (`path`, `outputPath`, `modulePath`, `vgmPath`, ...) - those are paths on the local disk romdev shares with you, NOT uploads. Pass an absolute local path; romdev reads/writes it directly. (This is also why it's localhost-only and needs no auth.) Likewise output paths land on the local disk where you can read them back.

## How to call romdev
Each capability is an HTTP route on the local romdev server (default http://localhost:7331):
  • POST /tool/{name}  - run a tool. The JSON request body is the arguments. The response is JSON.
  • GET  /tool/{name}/schema - that tool's JSON Schema (the exact parameters + types).
  • GET  /openapi.json - the full machine-readable API; GET /documentation - a browsable console.

## Sessions - IMPORTANT for stateful work (load → step → read)
**Pick ONE session id for yourself and send it as the `x-romdev-session` header on EVERY call.** Make it UNIQUE and DESCRIPTIVE of what you're doing - e.g. `nes-platformer-build`, `rpg-romhack-text`, `gba-sprite-debug` (a slug, optionally with a short random suffix to stay unique). A human may be watching the live observer at /livestream, where your session id is the label for all your activity - a descriptive id tells them at a glance which agent/task each call belongs to; a bare uuid or `default` is opaque. The emulator/host is per-session: the ROM you `loadMedia` lives in YOUR session, and the next `frame`/`memory`/`cpu` call only sees it if it carries the SAME id. Do NOT send a new id each call - that's a fresh empty session every time (your loaded ROM vanishes; "No ROM loaded"). Several agents can share one server safely: each just sends a DIFFERENT id, so nobody clobbers another's ROM (another reason to make yours distinctive). The header is REQUIRED on every `/tool/{name}` call - omit it and you get a **401** (the server will NOT silently run you in a throwaway session). Pure file tools (romPatch/cart/encodeAudio) still need the header; just reuse your one id everywhere.

**Showing a game running on /livestream: one call, never a loop.** POST /tool/host {"op":"play","seconds":120} runs your session in real time on the server and returns at once; it stops on time, on {"op":"stop"}, or on your session's next tool call. Do NOT script a loop of frame step calls to keep the stream alive.

Each tool is a domain VERB keyed by an operation axis - e.g. POST /tool/memory {"op":"read",...},
POST /tool/build {"output":"rom",...}, POST /tool/romPatch {"op":"findPointer",...}. The full per-tool
parameter list is in the TOOL REFERENCE at the end of this doc (and /openapi.json).

## Keeping this skill current
This skill was generated by romdev **v0.150.2** (it's a snapshot - it does not auto-update). romdev generates it live from the running server, so to update: run the latest `npx romdevtools`, then re-fetch `GET http://localhost:7331/skills/romdev/SKILL.md` and overwrite your saved copy. To check whether you're stale, ask the running server its version - `POST /tool/catalog {"op":"status"}` returns `romdevVersion` (or `GET /healthz` → `version`); if it's newer than the `metadata.version` above, re-fetch.

---

# romdev - Agent guide

This is romdev's general orientation. Read it once. Detail lives in docs you fetch on demand with `platform({op:'doc'})`; this guide says which one to read when.

## What romdev does

romdev runs the whole retro game development and reverse-engineering loop in-process: build, run, screenshot, inspect, debug, patch, disassemble, decompile, recompile, convert assets and drive emulators. Every compiler and emulator core is bundled as WASM.

- Platforms: 19 consoles and computers (see "Platforms"), plus the PICO-8 fantasy console and two native runtimes (wasmcart, jsgame).
- Homebrew: fork a working example game, edit it, `build({output:'run'})` to build, load, run and screenshot in one call.
- Reverse engineering: byte-exact rebuildable disassembly, value search, write/read/pc breakpoints, coverage, Rizin/Ghidra analysis and decompilation, cheat lookup, ROM patching and asset re-injection.
- Static recompilation: turn a NES, SNES, Game Boy, GBA, SMS/GG or Genesis ROM into a wasmcart and verify it against the reference core.
- Matching decompilation: recover C that compiles to the original bytes with the project's original compiler, run as WASM.

You drive the work. The human directs: they may want a game, a disassembly, a romhack, a recompile, or anything else here.

### Where the detail lives

| Read | When |
|---|---|
| `platform({op:'doc', platform, name:'mental_model'})` | Before writing code or doing RE on a platform: memory map, video chip, input, build pipeline, footguns, debug regions. |
| `platform({op:'doc', platform, name:'troubleshooting'})` | The moment something on that platform is broken. |
| `platform({op:'doc', platform, name:'upstream_sources'})` | Where the bundled library and compiler sources are. |
| `platform({op:'doc', platform:'n64', name:'decomp'})` | Matching decompilation. |
| `platform({op:'doc', platform:'romhacking', name:'playbook'})` | Before any romhack or RE task: the decision tree and per-asset round trips. |
| `platform({op:'doc', platform:'guide', name:'recompile'})` | Static recompilation and its verification ops. |
| `platform({op:'doc', platform:'guide', name:'debugging'})` | Per-platform inspector coverage, memory/state tools, symbol-aware reads, input mapping, save states. |
| `platform({op:'doc', platform:'guide', name:'assets'})` | Art, tilemaps, sprite capture, audio formats, cross-platform moves. |
| `platform({op:'doc', platform:'guide', name:'music'})` | Where to get music and how to turn it into platform data. |
| `platform({op:'doc', platform:'guide', name:'wasmcart'})` | wasmcart carts: ABI, input, WebGPU, `presentWindow`, the `wasm` tool. |
| `platform({op:'doc', platform:'guide', name:'bezels'})` | Active Bezels (`.ab` companions that composite over a game). |
| `platform({op:'doc', platform:'guide', name:'sessions'})` | Sessions, eviction, many agents on one server, the playtest window, the livestream, feedback. |

`platform({op:'docs', platform})` lists what a platform ships; `platform({op:'docs', platform:'guide'})` lists the guides.

## The one hard rule: never install a compiler or emulator

You never need, and must never install, a compiler or emulator to build or run a ROM here. Every compiler, assembler and linker (cc65, sdcc, gcc and binutils for m68k/arm/mips/sh, tcc, wla, rgbds, asar, dasm), every SDK (SGDK, PVSnesLib, libtonc/libgba, cc65 libs) and every emulator core is bundled as WASM and runs through these tools: `build`, `loadMedia`, `frame`, the inspectors, `playtest`.

If a compiler or emulator install is invoked or prompted (`clang`, `gcc`, Xcode or Command Line Tools, `node-gyp`, devkitPro, `brew`/`apt install <compiler>`), that is a defect. Do not install it, do not investigate it with host commands, and report it ("romdev should provide this"), for example with `feedback({op:'record'})`. `platform({op:'list'})` and `platform({op:'toolchains'})` show what is bundled.

- Native addons (the playtest window's `@kmamal/sdl`) ship prebuilt. A compile kicking off means the prebuilt is missing: do not let it compile. `playtest` self-heals by downloading the binary, or fails with `reason:"sdl-binary-missing"` and a one-line `fixCommand`.
- Content tools are fine: ImageMagick, GIMP, LibreSprite/Aseprite, Audacity, Tiled, a tracker, a quick art script. They make source PNGs, `.wav`, `.tmx`; romdev imports and packs them (see the assets guide), and often does the whole conversion itself.
- romdev itself is JavaScript and WASM only and never runs Python, make or git on the host.

Matching decompilation also uses the original compiler as WASM. `decomp({op:'setup', root})` runs a fresh checkout's own setup and extract goals in-process (splat as the JS port romdev-splat at the versions the project pins), and `decomp({op:'import'})` registers it. Compiles use the flags the project's Makefile chooses per file (romdev reads the Makefile). Supported compilers: IDO 5.3/7.1, KMC gcc 2.7.2, EGCS 1.1.2, PS1 gcc 2.6.3 with maspsx, mips-linux-gnu gcc 14, with mips-linux-gnu binutils, armips and a JS asm-processor. IDO is SGI's proprietary compiler and is not shipped: build it with `scripts/build-ido.sh` from a romdev source checkout, or point `ROMDEV_IDO_DIR` at your build. A build step with no WASM/JS equivalent (a Python asset packer) is never run on the host: its existing output is kept and reported in `keptPrebuilt`.

## The second rule: read your platform's docs before writing code for it

This guide cannot hold 19 platforms of detail. Read `platform({op:'doc', platform, name:'mental_model'})` for every system you build for or reverse-engineer, before writing code. Most "why won't this work" dead ends are a documented footgun there (a C64 game that needs a key to start, an SDCC WRAM-layout trap, a render-enable order, a core that exposes `gb_vram` not `video_ram`). Read `troubleshooting` the moment something breaks, and the romhacking playbook first for any hack.

## Platforms

| Tier | Platforms | What works |
|---|---|---|
| Classic (15) | NES, SNES, Game Boy, Game Boy Color, GBA, Genesis, Master System, Game Gear, Atari 2600, Atari 7800, Atari Lynx, C64, PC Engine, MSX/MSX2, GameTank | Build, run, inspect, sound and music, forkable genre examples, write/read/pc breakpoints, single-step, coverage, byte-exact disassembly projects, re-inject tools, mental model and troubleshooting docs. |
| sync32 | an open RP2350-based console (Cortex-M33, `.s32`) | C carts against a function-pointer ABI, WASM toolchain, memory/cpu/palette inspection, five genre examples, cycle profiling. No PPU, OAM or tilemap. |
| 3D consoles | Nintendo 64, PlayStation, Dreamcast | Build and run examples (GPU-rendered cores), disassembly, Rizin/Ghidra analysis, memory tools; N64 breakpoints and single-step; matching decompilation projects. |
| Fantasy console | PICO-8 (FAKE-08) | `build` packages a `.p8` from Lua; `disasm({target:'source'})` reads the cart's Lua; `memory({region:'system_ram'})` is its 64 KB. CPU and tile inspectors do not apply. |
| Native runtimes | wasmcart, jsgame | Load, step, screenshot, input, `frame({op:'verify'})`, the `wasm` tool, `pack`. |

Genre examples (`shmup`, `platformer`, `puzzle`, `sports`, `racing`) ship for every classic platform except the Atari 2600, which has four (no `puzzle`: the TIA has no tilemap for a match-3 board), and for sync32, GameTank, PICO-8, N64, PlayStation and Dreamcast. The platformer side-scrolls with a hardware camera everywhere except NES and the Atari 2600, which are single-screen. Classic platforms also ship a music demo (`music_demo`) on the de-facto engine (FamiTone2, hUGEDriver, an SPC700 driver, XGM2, maxmod, PSG trackers, a SID sequencer, `lynx_snd_play`, TIA; PC Engine and MSX as `music_sfx`, plus `sprite_move`/`catch_game` projects).

`platform({op:'list'})` is the live matrix with language defaults and quirks (`platform` filters to one row, `slim:true` drops prose). C is the default wherever a C compiler is bundled; asm-only platforms default to asm; pass `language` to override. Platform-specific inspectors, regions and traps are in each mental model; the debugging guide has the coverage matrix.

## Tools

All 38 tools are registered at session start; call any by name. Each is a verb with an operation axis. `catalog({op:'categories'})` maps them by purpose; `catalog({op:'status'})` re-orients a session (what is loaded, version, health, play and bezel state).

| Tool | Axis and values |
|---|---|
| `catalog` | `op`: categories, status |
| `platform` | `op`: list, capabilities, resolve, toolchains, docs, doc |
| `examples` | `op`: list, fork, show, snippets, copySnippets |
| `build` | `output`: rom, romWithDebug, run, project, reassemble |
| `loadMedia` | load a ROM, disk, tape, program or cart (`path` or `base64`; `slot:'b'`, `core`, `firmware`, `cheats`, `coreOptions`, `useActiveBezel`, wasmcart options) |
| `host` | `op`: unload, shutdown, reset (`hard:true` power-cycles), pause, resume, play, stop |
| `frame` | `op`: step, screenshot, stepAndShot, sideBySide, compareRam, findDiverge, compareRender, portStatus, stepInstruction, stepInstructions, traceInstructions, verify, verifyRecompile, fuzzRecompile, cycles |
| `input` | `op`: set, press, sequence, timeline, navigate, layout, pressKey, typeText, joyport, pointer, wheel |
| `state` | `op`: save, load, list, export, dump, diff, exportSram, importSram, exportDisk, importDisk, putDiskFile, autoSnapshot, recoverSnapshot |
| `memory` | `op`: read, write, readCart, regions, snapshot, diff, diffRuns, classify, search, searchUnknown, searchNext, provenance |
| `symbols` | `op`: resolve, lookup, map, list, addr, analyze |
| `disasm` | `target`: bytes, rom, range, project, references, cfg, xrefs, functions, reachable, decompile, source, resolveJumptable, pointerTable, recompile, script, accessScan, sourceLookup |
| `breakpoint` | `on`: write, read, pc, jumptable |
| `watch` | `on`: mem, range, pc, dma, copy |
| `cpu` | `op`: read, setReg, call, decompress |
| `runUntil`, `recordSession` | step until a memory or framebuffer condition; record a timeline of screenshots and memory samples |
| `sprites` | `op`: inspect, group, preview, capture, render, emitC, extractScreenshot |
| `tiles` | `op`: png, pixels, fingerprints, ascii, preview |
| `background` | `view`: map, renderState, rendered |
| `palette` | `source`: live, platformMaster, lospec |
| `videoDebug`, `audioDebug` | VDP state (`chip:'vdp'`); audio chip state and traces (`op`: inspect, record) |
| `encodeArt`, `importArt` | `stage`: quantize, crop, tiles, tilemap, validate; `from`: aseprite, gif, texturepacker, tiled, rom |
| `encodeAudio` | `target`: brr, xgm2pcm, xgm2, maxmod, famitone, spc, gg, sms, c64, lynx, atari7800, gb, gbc, sync32, sync32pcm |
| `romPatch` | `op`: write, writeMany, spliceCHR, relocate, makeStored, findFree, findPointer, diff, gbHeader |
| `assembleSnippet` | assemble a few instructions to bytes at an origin (6502, 65816, 68k, Z80, SM83, HuC6280) |
| `cart` | `op`: identify, extract, wrap, packDisk |
| `cheats` | `op`: lookup, search, apply, remove, clear, make |
| `text` | `op`: learn, encode, find (custom-font text) |
| `wasm` | `op`: conformance, info, exports, debugState, events, read, write, save, command |
| `pack` | `target`: wasc, jsgame |
| `playtest` | `op`: open, stop, status, framebuffer, fps, bezel |
| `regression` | `op`: capture, check (golden checkpoint runs) |
| `decomp` | matching decompilation, about 45 ops (see "Matching decompilation") |
| `files` | `op`: read, write, list |
| `feedback` | `op`: record, list |

## Making a game: fork an example, then iterate

Never start from a blank file. Fork the example whose core loop is nearest your game (even for a very different game), then change one thing at a time and re-run `build({output:'run'})`. Retro bring-up is a long chain of fragile hardware init with no partial credit; a working game is your regression oracle.

1. `examples({op:'list', platform?})`: every example with its kind (`game` or minimal `reference` such as `default`, `hello_sprite`, `tile_engine`), mechanics, hardware techniques, players and SRAM, plus genre-to-nearest-fork guidance.
2. `examples({op:'fork', example:'<platform>/<name>', name, path, title?, overwrite?})`: copies the example into a new directory as your game (sources, runtime files, crt0, linker config, vendored library source, README, `.gitignore`), renamed throughout. It builds before you change a line. The response lists the files you edit plus `vendorFileCount` (`verbose:true` for the full list). You can pass `platform` + `template` instead of `example`.
3. `build({output:'run', path, platform})` builds the directory, loads it, runs it and returns a screenshot inline. `build({output:'project', path, outputPath})` builds the directory to a ROM.
4. `examples({op:'show', example, file?, technique?})` reads a donor example without forking; `technique` extracts one marked HARDWARE IDIOM block with its dependency header to graft.
5. `examples({op:'snippets', platform, mode:'list'|'get'|'getAll'})` and `examples({op:'copySnippets', platform, destinationDir, include?})` fetch vetted helpers (reset, read_pad, OAM DMA, palette upload); `copySnippets` writes to disk without passing bytes through your context.

Want a side-scroller? Fork `<platform>/platformer`. NES scrolling needs platforms drawn into the nametables plus `ppu_scroll(camX,0)` and column streaming past 512 px; each platformer's `describe` text and the mental model's "Horizontal scrolling" section give the details.

### Project layout and the directory build

A forked project is flat: `main.c`/`main.asm`, your helper modules, crt0 and linker config sit at the root, so includes resolve without `-I`. The only subdirectory is `vendor/`, the full source of every library the ROM links (`vendor/cc65/libsrc/<platform>/`, `vendor/libtonc/src/`, `vendor/libgba/src/`, `vendor/pvsneslib/source/`, `vendor/sgdk/src/`). It is read-only in practice: the linker uses the precompiled libraries, so edits there do not reach the ROM. `grep -rn <symbol> vendor/` finds any library function's implementation.

The directory build finds the entry (`main.c`, `main.s`, `main.asm`), routes the crt0 (GB/GBC `gb_crt0.s` through the cart-header path), applies the linker preset (NES `chr-ram-runtime`), skips SDK intermediates, wires runtimes (GBA libtonc/libgba/maxmod by include), treats `.h`/`.inc` as includes and folds binary assets (`.bin`, `.chr`, `.pcm`, `.brr`, `.vgm`, `.xgc`, ...) in as `binaryIncludes`. Use `build({output:'rom'})` with explicit `sources` only for files not on disk.

`build({output:'run'})` takes `frames` and `holdInputs` (for example `[{right:true}]`) to test input in the same call; round trips are 50-500 ms. Use the separate `loadMedia` / `frame` / `state` calls only when you need several state changes in one ROM lifetime.

### ROMs are finalized for real hardware

`build` output boots on real hardware, flashcarts and strict emulators; the post-link finalize step runs for you (do not checksum or pad by hand): Genesis padding and `$18E` checksum; GB/GBC `rgbfix` (logo, header and global checksums, CGB flag); SMS `TMR SEGA` header, checksum and region byte; SNES power-of-two padding and internal checksum with LoROM/HiROM detection; NES iNES header from the linker config. The response's `romLayout` / `log` say what was applied.

### Where ground truth is when the example disagrees with behaviour

1. The bundled examples (verified to build and run).
2. Your project's runtime source (`gb_runtime.c`, `lynx_sfx.c`, ...; 50-200 readable lines each).
3. Your project's `vendor/` library source.
4. `platform({op:'doc', platform, name:'upstream_sources'})` for bundled source paths and upstream links.
5. Upstream repositories for compilers and emulators.
6. A real romdev bug: open an issue at https://github.com/monteslu/romdev/issues with a diagnosis and repro.

If two or three iterations on the example do not converge, switch from editing to reading the library source. When the example and the library disagree, trust the library.

### Toolchain traps that apply everywhere

- C builds run a pre-flight lint. Read `issues[]`; `stage:"lint"` entries name the right file:line (raw compiler line numbers are often off by one) and carry a `ref:` into the platform's gotchas. `lint:"strict"` fails the build on any lint hit.
- All SDCC platforms (GB, GBC, SMS, GG, MSX) are C89: declarations at the top of each block, no `for (int i...)`, no compound literals or designated initializers. The GB/GBC SDCC notes (in the package at `src/platforms/gb/lib/c/SDCC_GOTCHAS.md`) also cover WRAM-layout traps that look like miscompiles.
- cc65 zero page starts at $02 ($00-$01 are reserved).
- Platform-specific traps (asar silent failures and CHR/tilemap overlap on SNES, SNES audio as a separate SPC700 build, NES 256-unique-tile cap, GB `shadow_oam` alignment and `memcpy_vram`, SMS/GG 8-sprites-per-line and `$D0` terminator) are in each platform's mental model and troubleshooting docs.

## Running, looking and asserting

- `frame({op:'verify'})` answers "is the game actually rendering?" without vision: `{verified:true|false|null, issues[], pixels, render}`.
- Assert state by reading memory, not by reading screenshots: `build({output:'romWithDebug'})`, `symbols({op:'resolve', name})`, `memory({op:'read'})`. The debugging guide has the per-toolchain table.
- `frame({op:'screenshot'})` takes `crop:{x,y,w,h}` (a native-resolution HUD strip for a fraction of the tokens), `scale` (below 1 for cheap change checks, not for reading text; integer above 1 to enlarge), `format:'ascii'`, and `source` when an Active Bezel is attached.
- Input: `input({op:'set', ports})` is positional (`ports[N]` is port N) with one boolean per button; the spatial names `north/east/south/west` resolve to the right physical button on every platform (the raw libretro `a`/`b` are inverted on Genesis, SMS and Game Gear). `input({op:'layout', platform})` gives the real buttons and bit order; read it before writing a `read_pad` routine. `input({op:'timeline'})` is an absolute per-frame schedule for differential runs; `navigate` advances menus on screen change.
- `memory({op:'regions'})` lists the regions for the loaded platform; start there rather than guessing.

### Large output: a path, or ask for it inline

Tools that can return large payloads (ROM bytes, disassembly, memory dumps, build logs, tile blobs, screenshots) default to `inline:false` and need an output path (`outputPath`, `outputDir` or `path`); you get back `{path, bytes}`. Pass `inline:true` to get the payload in the response. There is no hidden default location. Exceptions: `memory({op:'read'})` of 4 KB or less is inline, and `build({output:'run'})` returns its screenshot inline (`screenshotPath` to write it instead). If you are not sure your client shows inline images, work from `frame({op:'verify'})` and the decoded JSON of `sprites`, `palette` and `background`.

Prefer paths over base64 for inputs too: the server shares your filesystem.

### When a call fails, read the error first

Errors name the fix. Build failures return `issues: [{file, line, col, severity, message, stage}]` ranked critical first; fix `critical:true` entries (such as `WILL HANG:` loop-bound traps) even on a successful build; fall back to `log` only when `issues` is empty. Tool errors carry the recovery step (an eviction's "No ROM loaded" names the exact `loadMedia({...})`; a rejected load points at `cart({op:'identify'})`; a mistyped button returns `ignoredButtons[]`). A crashed WASM toolchain returns `stage:"crash"` without affecting the session.

## Reverse engineering and romhacking

Read the playbook first: `platform({op:'doc', platform:'romhacking', name:'playbook'})`. It wires the tools below into a decision tree and covers text, compressed assets and graphics round trips.

A good default order:

1. `cart({op:'identify', path})`: platform, title, mapper, save RAM (handles zip-wrapped ROMs).
2. `cheats({op:'lookup', path})`: the bundled cheat database is a labeled RAM and code map for thousands of known ROMs (`kind:ram` = a variable, `kind:code` = a patch site). Cheap; check early. Labels are probable name matches; verify before patching.
3. Disassemble and trace for anything about code or data the cheats do not cover: `disasm({target:'project'})` for a byte-exact rebuildable project (edit a region `.asm`, then `build({output:'reassemble', platform, path})`; pass `background:true` for ROMs of 512 KB or more and poll with `job`); `disasm({target:'references'|'accessScan'})` for who touches an address; `breakpoint({on:'write'|'read'|'pc'})` for the exact instruction; `watch({on:'range'|'pc'|'copy'|'dma'})` to discover routines; `symbols({op:'analyze'})`, `disasm({target:'functions'|'cfg'|'xrefs'|'reachable'})` for structure; `disasm({target:'decompile'})` for Ghidra pseudocode; `breakpoint({on:'jumptable'})` for computed dispatchers no static walk can follow.
4. Verify live before patching: `memory({op:'write'})` the address and watch the effect.
5. Patch: `romPatch({op:'write'|'writeMany'})` with `expect:` bytes (refuses a wrong revision), or prototype with `cheats({op:'apply'})`.

Find a value's address with the search loop (`memory({op:'search'})` then `searchNext`), not a full-RAM diff. Drive the ROM's own codecs with `cpu({op:'call'|'decompress'})` and put assets back with `romPatch({op:'makeStored'|'findFree'|'relocate'|'findPointer'})`. Edit on-screen text with `text({op:'learn'|'find'|'encode'})`. Assemble patches with `assembleSnippet`. These work on the 15 classic platforms; disassembly and the Rizin/Ghidra analysis cover 18 platforms including the 3D consoles' MIPS and SH-4.

## Static recompilation

`disasm({target:'recompile', emit:'wasmcart', platform, path, outputPath})` recompiles a whole ROM into a playable wasmcart for nes (fceumm), snes (snes9x, with SA-1, SuperFX, DSP-n, ST010/011/018, S-DD1, SPC7110, CX4, OBC1, S-RTC, MSU-1, BS-X, Sufami Turbo), gb/gbc (gambatte), gba (mGBA), sms/gg and genesis (genesis_plus_gx, including SVP carts). Every ROM byte offset is a compiled entry point and RAM code runs in a matching interpreter, so no discovery run is needed. Per-game settings go in `options` (ST011/ST018 and DSP-1 carts need firmware you supply; romdev does not ship chip firmware). `emit:'sync32'|'c'` builds a native sync32 cart from a Genesis ROM; `emit:'ir'|'blockMap'` exports decoded instructions for your own tools; the default `asm` output translates one routine to SNES or Genesis assembly.

Verify with the `frame` ops: `verifyRecompile` (pixels, memory regions, audio and must-fail controls against the reference core in one call; `auto:true` picks the schedule itself), `findDiverge` with `cart` (first differing frame and byte; `level:'instruction'` finds the first divergent instruction), `fuzzRecompile` (seeded play hunting traps), `traceInstructions` (the real executed instruction stream), `cycles` (sync32 frame cost and profile).

Every recompiled cart carries a `licence` entry naming the emulator code it contains (GPL, MPL or non-commercial terms, depending on the platform); the texts are in the package's `LICENSES/` directory. Read `platform({op:'doc', platform:'guide', name:'recompile'})` before using any of this.

## Matching decompilation

`decomp({op})` drives a splat-based decomp project (N64 and PlayStation) through the original compiler as WASM. The loop: `setup` (fresh checkout), `import`, `plan`, `resolve`, `generate` (m2c candidate via romdev-m2c), `compare` (compile inside its translation unit; per-instruction and relocation equality), `search` (bounded permuter job via romdev-permuter; `job`, `jobs`, `candidates`), `integrate` (patch, full-ROM byte verify, auto-revert), `progress`. Runtime ops (`smoke`, `overlays`, `symbolize`, `state`, `trace`, `coverage`) check a live session. Campaign ops (`workbench`, `dispatch`, `experiment`, `gate`, `diagnose`, `variants`, `rank`, `ledger`, `research`, `knownSource`, `assets`, `skill`, `handoff` and others) run the bundled decomp workbench in process. `exactFunctionMatch` and `romLinked.status:'exact'` are the acceptance signals; `distance` only ranks. Read `platform({op:'doc', platform:'n64', name:'decomp'})` first; `decomp({op:'skill'})` returns the bundled campaign skill.

## wasmcart, WebGPU and jsgame

`loadMedia({platform:'wasmcart', path})` runs a WebAssembly cart. Carts must target wasmcart ABI v4 or later (older ones are refused). Buttons map by position (`a` is east). GL carts get their own GL context; WebGPU carts load the same way (`gpuPower`, `wgpu:false`, `deterministicStepMs` are load options). Load GL carts with `presentWindow:true` before opening a playtest window. `wasm({op})` inspects a cart (conformance, named debug state, events, a `command` request/reply channel). `pack({target:'wasc'|'jsgame'})` builds the archive. Details: `platform({op:'doc', platform:'guide', name:'wasmcart'})`.

## If a human is watching, open playtest early

If a human is with you, open the playtest window as soon as the first build succeeds: `playtest()` opens a native SDL window that runs the ROM live with USB gamepads and returns immediately. Every other tool keeps working on the same live host, and rebuilds update the window in place. The human should be playing while you iterate.

- No gamepad: relay the `keyboardControls` / `tellUser` note from the response.
- `playtest({op:'status'})` reports `perf` (fps and per-stage costs); `playtest({op:'fps', show:true})` draws a counter for the human.
- While the human presses buttons, their input wins and responses carry `humanCoDriveWarning`; `catalog({op:'status'})` shows `humanInputActive`. Use `host({op:'pause'})` or a second session for deterministic stepping.
- Skip it for CI, batch RE, or when told "headless". A failed open is a tool error with a `reason` (`sdl-binary-missing`, `no-display`, `sdl-error`) and every other tool stays headless.

To show a game moving on the `/livestream`, call `host({op:'play', seconds})` once; never loop `frame({op:'step'})` calls to keep the stream alive.

The sessions guide covers the window ops, hotkeys, aspect, pointer carts and the livestream in full.

## Active Bezels

An Active Bezel (`.ab`) runs beside a ROM every frame and draws a composite scene. With one attached, `frame({op:'screenshot'})` returns the composite by default, not the core's picture; `catalog({op:'status'})` reports `activeBezel` whenever one is attached, so check it before interpreting captures in an unfamiliar session. `source:'core'|'both'` selects the picture. Bezels with `pre_frame` can poke memory and override input invisibly to breakpoints (`activeBezel.preFrame` in status). Load with `loadMedia({..., useActiveBezel:true})`; authoring needs no toolchain (`npx --package active-bezel abtool scaffold my-bezel lua`). Details: `platform({op:'doc', platform:'guide', name:'bezels'})`.

## Sessions

Your emulator lives in your session for the server's lifetime; sessions do not expire. Use one session for the whole job and keep sending the same identity.
Clients on the 2026-07-28 protocol revision should pass one stable `session` argument (a descriptive slug) on every tool call.

- A host idle for about 10 minutes may be evicted; the next call fails with "No ROM loaded" and names the exact `loadMedia({...})` to re-run. Open playtest windows are never evicted.
- `state({op:'autoSnapshot', enabled:true})` and `state({op:'recoverSnapshot'})` survive a server restart.
- Running several sessions: declare yourself with the `x-romdev-agent` header (or `dev.romdev/agentHandle` in `_meta`) and end sessions with `host({op:'shutdown'})`.
- A different `session` value is a fully isolated second emulator.
- `feedback({op:'record', title, body, severity})` logs a defect locally for the human.

Details: `platform({op:'doc', platform:'guide', name:'sessions'})`.

## When in doubt

`platform({op:'list'})` for capabilities, `platform({op:'capabilities', platform})` for which ops a platform supports, `catalog({op:'status'})` for what is loaded, `platform({op:'toolchains'})` for build tools, `state({op:'list'})` for save slots, `memory({op:'regions'})` for memory. Tools describe themselves; you do not have to remember the matrix.

---

# TOOL REFERENCE

38 tools. POST the args as JSON to /tool/{name}.

## assembleSnippet
Use this to assemble a tiny chunk of asm to raw bytes - no header/linker/segments, just the bytes at `origin`. With patchFile this is the whole byte-patch workflow in 2 calls. `cpu` routes to the right assembler (6502/65c02/huc6280→ca65, 65816→asar, 68k→m68k-elf-as (Motorola syntax), z80→sdasz80, sm83→rgbasm; spc700 unsupported). Set `origin` to where the code will live so branches/absolute refs encode right. GOTCHA: z80 immediates need a `#` prefix (`ld a,#5`, not `ld a,5`). Returns `{hex, bytes(base64), log}` - feed `bytes` straight into patchFile.base64.
`POST /tool/assembleSnippet` params: cpu:string(6502|65816|65c02|huc6280|68k|m68k|z80|sm83|gb|gbc|spc700), origin?:integer, code:string

## audioDebug
Debug sound / transcribe music on the running ROM. `op`: 'inspect' | 'record'.
`POST /tool/audioDebug` params: op:string(inspect|record), chip?:string(nes|gb|gba|dsp|psg|ym2612|sid|mikey|pce|ay8910|spu|ai|aica|acp), frames?:integer, sampleEvery?:integer, path?:string, setInputs?:array

## background
Background/tilemap inspection + render state, one tool keyed by `view`.
`POST /tool/background` params: view:string(map|renderState|rendered), platform?:string, area?:string(bg|sprites|window|all), outputPath?:string, inline?:boolean, render?:boolean, region?:object, attributesOnly?:boolean, tilesOnly?:boolean, which?:integer, window?:boolean, plane?:string(A|B), tilemapBaseByte?:integer, tileBaseByte?:integer, bpp?:any, mapWidth?:any, mapHeight?:any, snesTilemapBaseByte?:integer, snesMapWidth?:any, snesMapHeight?:any

## breakpoint
STOP-on-first dynamic breakpoints - run until a condition hits, then stop. One tool keyed by `on`. (For LOG-ALL coverage over many frames use `watch`; for a value-predicate closure use `runUntil`.)
`POST /tool/breakpoint` params: on:string(write|read|pc|jumptable), precision?:string(exact|sampled), address?:integer, region?:string, offset?:integer, length?:integer, condition?:string(increase|decrease|equals), conditionValue?:integer, conditionWidth?:any, maxFrames?:integer, pressDuring?:array, settleFrames?:integer, abortIf?:array, captureMemory?:array, maxTargets?:integer, stepLimit?:integer, jumpThreshold?:integer, fromState?:integer, fromStatePath?:string

## build
Compile/assemble source for a target platform; one tool keyed by `output`.
`POST /tool/build` params: output:string(rom|romWithDebug|run|project|reassemble), platform:string, language?:string, source?:string, sourcePath?:string, sources?:object, sourcesPaths?:object, includes?:object, asmIncludes?:object, asmIncludePaths?:object, includePaths?:object, binaryIncludes?:object, binaryIncludePaths?:object, crt0?:string, crt0Path?:string, codeLoc?:integer, dataLoc?:integer, options?:array, defines?:object, linkerConfig?:string, linkerConfigPath?:string, inesHeader?:object, runtime?:string, maxmod?:boolean, rebuildSdk?:boolean, lint?:string(advisory|strict), includeSymbols?:boolean, resolveSymbols?:array, frames?:integer, holdInputs?:array, screenshotPath?:string, projectName?:string, title?:string, id?:string, mode?:string(ram|xip), video?:string(128|180|240), api?:integer, linkOptions?:array, data?:object, dataPaths?:object, icon?:string, iconPath?:string, form?:string(archive|folder), path?:string, entry?:string, exclude?:array, includeDirs?:array, outputPath?:string, inline?:boolean

## cart
Cartridge container ops - identify / split / reassemble a ROM file. `op`: 'identify' | 'extract' | 'wrap' | 'packDisk'.
`POST /tool/cart` params: op:string(identify|extract|wrap|packDisk), path?:string, base64?:string, hint?:string, platform?:string(nes|snes|genesis|megadrive|md|gb|gbc|sms|gg|atari2600|a2600|atari7800|a7800|c64), outputDir?:string, inline?:boolean, prgPath?:string, chrPath?:string,null, mapper?:integer, mirror?:string(horizontal|vertical|four-screen), prgBanks?:integer, chrBanks?:integer, hasBattery?:boolean, romPath?:string, copierHeaderPath?:string, headerPath?:string, bodyPath?:string, bootPath?:string, preHeaderPath?:string, vectorsPath?:string, a78HeaderPath?:string, bodyBytes?:integer, loadAddress?:integer, name?:string, diskName?:string, outputPath?:string

## catalog
Orient yourself, keyed by `op`.
`POST /tool/catalog` params: op?:string(categories|status)

## cheats
Cheat lookup / search / apply / create for the loaded ROM. `op`: 'lookup' (THIS game's known cheats from the bundled DB - returns labeled RAM addresses + Game Genie/ROM code sites, so it answers 'which byte holds X?' for free); 'search' (fuzzy-find a game by NAME when you don't have the exact No-Intro title - searches ALL platforms by default and each match reports its own `platform`, so you don't need to know the console; pass `platform` only to scope it. Returns game names + cheat counts; then lookup the chosen one with its platform); 'apply' (enable a cheat on the LOADED game - pass a raw `code` or a `desc` from lookup); 'clear' (remove all active cheats); 'make' (CREATE a shareable code from an address+value). TRUST: lookup matches by NAME/fuzzy similarity, NOT a verified CRC - a PROBABLE match. Labels are usually right, but a different region/revision can use different addresses - VERIFY before patching: apply + observe, or check the address in live memory with memory/watch. apply is NON-DESTRUCTIVE (volatile core state; reset / state({op:'load'}) / op:'clear' removes it, the ROM file is never touched), so it doubles as the verifier - apply a label, screenshot, confirm. make emits the platform's NATIVE device code (not always 'Game Genie': NES/Genesis=Game Genie; SNES=Pro Action Replay+GG; GB/GBC=Game Genie(ROM)+GameShark(RAM); SMS/GG=Action Replay) plus the raw ADDR:VAL, all round-trip `verified`. RAM cheat = address+value; ROM/code cheat = also `compare` (the byte currently there - read it first).
`POST /tool/cheats` params: op:string(lookup|search|apply|remove|clear|make), path?:string, filter?:string, kind?:string(ram|code|all), query?:string, limit?:integer, code?:string, desc?:string, index?:integer, enabled?:boolean, slot?:integer, platform?:string(nes|gb|gbc|snes|genesis|sms|gg|atari2600|atari7800|lynx|gba|c64|pce|msx|gametank), address?:integer, value?:integer, values?:array, entries?:array, compare?:integer, device?:string(game-genie|pro-action-replay|gameshark|action-replay|raw)

## cpu
Read or drive a CPU, one tool keyed by `op`.
`POST /tool/cpu` params: op:string(read|setReg|call|decompress), platform?:string, cpu?:string(main|spc700|z80), regId?:integer, value?:integer, pc?:integer, regs?:object, sentinelPC?:integer, stopAtPC?:integer, presetMemory?:array, maxFrames?:integer, maxInstructions?:integer, sandbox?:boolean, pure?:boolean, callMode?:string(jsr|jsl), entryPC?:integer, sourceAddress?:integer, destAddress?:integer

## decomp
Matching decompilation: recover C that compiles to the ORIGINAL bytes with the project's ORIGINAL compiler (splat + IDO/GCC projects; proven on an N64/IDO 5.3 checkout). Keyed by `op`. The compile path runs as WASM inside romdev: IDO 5.3/7.1 (SGI's compiler is proprietary and not shipped: build it with scripts/build-ido.sh from a romdev checkout, or set ROMDEV_IDO_DIR), the mips-linux-gnu binutils, asm-processor (JS port) and the C preprocessor, driven by the recipe romdev reads from the project's own Makefile (or a manifest-declared per-TU recipe). On the compile/compare/integrate/verify path no host make, compiler, python, binutils or diff is run; a recipe step with no WASM/JS equivalent is reported, never delegated to the host. LOOP: import (once) → plan (payoff-ordered queue + batches over the call graph) → resolve (segment-exact address, provenance) → generate (m2c candidate with the TU's real type context) → compare (compile the candidate INSIDE its translation unit with the TU's exact flags; strict per-instruction + relocation equality; ROM-linked word equality; other functions in the TU unchanged; a documented distance for ranking) → search (bounded decomp-permuter job; cancel/resume/best/report) → integrate (reviewable patch; apply + full-ROM byte verify, auto-revert on mismatch) → progress (code-byte progress from the build's objects, states kept separate). RUNTIME: smoke (base vs rebuilt, decoded pixels + CPU regs, replayable script), overlays (which overlay is resident, by bytes), symbolize (live PC → symbol with the resident overlay), state (is the session's emulator still there, and why not), trace (args/return of a function where the core can stop), coverage (sampled function-level observed/unobserved/unreferenced). Every result names the project, function {symbol, segment, va}, candidate sha, compiler fingerprint and artifact paths; errors carry a typed [CODE]. `exactFunctionMatch` and `romLinked.status:'exact'` are the acceptance signals; `distance` is a ranking hint, never proof. Ghidra pseudocode stays in disasm({target:'decompile'}) for understanding; it is never counted as matched.
`POST /tool/decomp` params: op:string(setup|import|status|refresh|list|map|plan|batch|resolve|context|generate|types|compare|search|job|jobs|candidates|integrate|verify|progress|smoke|overlays|symbolize|state|trace|coverage|workbench|dispatch|experiment|gate|typeGraph|rank|ledger|scenario|capabilities|knownSource|assets|artifacts|handoff|skill|diagnose|research|variants|layout|replay), project?:string, action?:string(status|best|cancel|report|create|control|candidate|conclude|list|families|save|run|unpack|repack|preview|write|prune|restore|pin|import), experimentId?:string, hypothesis?:string, lever?:string, family?:string, controlKind?:string(positive|negative|determinism), moved?:boolean, verdict?:string(accepted|rejected|exhausted), scope?:string, rationale?:string, exactFunctionMatch?:boolean, functionLocal?:string, distance?:number, notes?:string, baseline?:object, parentId?:string, workClass?:any, includeAllClasses?:boolean, forceGraph?:boolean, inputPath?:string, outputPath?:string, batch?:string, romOffset?:integer, length?:integer, scenarioName?:string, scenarioDef?:object, rebuild?:boolean, base?:string, preferTemporaryPrefix?:boolean, candidates?:array, baselineText?:string, budgetMiB?:integer, maxWorkers?:integer, wbGroup?:string, wbCommand?:string, wbArgs?:array, traceMode?:string(scheduler|globalcolor), allowDestructive?:boolean, allowNetwork?:boolean, timeoutMs?:integer, force?:boolean, root?:string, splatYaml?:string, buildPath?:string, targets?:array, makeVariables?:object, rom?:string, expectedSha1?:string, buildCommand?:array, symbol?:string, symbols?:array, va?:any, segment?:string, tu?:string, limit?:integer, offset?:integer, ignoreCooldown?:boolean, cooldownBatches?:integer, cooldownMinutes?:integer, proposedLever?:string, objective?:string(byte-coverage|function-count|shared-type|diagnostic-research), maxFunctions?:integer, timeBudgetS?:integer, candidatePath?:string, candidateText?:string, variants?:array, prefer?:string(best|newest), artifactId?:string, tracePath?:string, ownerPath?:string, contextHash?:string, declarations?:string, extraContext?:string, propose?:boolean, chunkFrames?:integer, cpuCore?:string(pure_interpreter|cached_interpreter|dynamic_recompiler), label?:string, maxDiffInstructions?:integer, noCache?:boolean, verifyTu?:boolean, timeLimitS?:integer, purpose?:string, mutationPasses?:array, noImprovementS?:integer, repeatSearch?:boolean, threads?:integer, detail?:boolean, preflight?:boolean, seed?:string, jobId?:string, resumeFrom?:string, apply?:boolean, verify?:boolean, jobs?:integer, frames?:integer, inputs?:array, scriptPath?:string, maxFrames?:integer, pressDuring?:any, session?:string

## disasm
Disassemble code - raw bytes, a whole ROM (mapper-aware), a full re-buildable project, or find references to an address. `target`: 'bytes' | 'rom' | 'project' | 'references'.
`POST /tool/disasm` params: target:string(bytes|rom|range|project|references|cfg|xrefs|functions|reachable|decompile|source|resolveJumptable|pointerTable|recompile|script|accessScan|sourceLookup), path?:string, base64?:string, platform?:string(nes|snes|genesis|sms|gg|gb|gbc|gba|atari2600|atari7800|c64|lynx|gametank|pico8|pce|msx|ps1|n64|dreamcast), startAddress?:integer, length?:integer, emit?:string(asm|ir|blockMap|wasmcart|wasm|wat|c|sync32), options?:object, cpuState?:string(arm|thumb), primaryOnly?:boolean, allOffsets?:boolean, alignments?:string(primary|all), slot?:integer, addOrigin?:boolean, outputPath?:string, inline?:boolean, cpu?:string(6502|65816|65c02|65sc02|huc6280), symbolsPath?:string, symbolsText?:string, symbolsFormat?:string(wla|cc65-lbl), bank?:integer, thumb?:boolean, widths?:object, endAddress?:integer, untilReturn?:boolean, mapper?:string(lorom|hirom|sega|codemasters|korean|korean-16k-v2), mapperState?:object, dataRanges?:array, autoLabelVectors?:boolean, annotateRegisters?:boolean, annotateFileOffsets?:boolean, outputDir?:string, background?:boolean, job?:string, targetPlatform?:string, withShim?:boolean, withRuntime?:boolean, topN?:integer, entries?:array, maxBlocks?:integer, minSize?:integer, address?:integer, maxRefsReturned?:integer, includeTableHits?:boolean, loBase?:integer, hiBase?:integer, count?:integer, convention?:string(direct|rts+1), grammar?:object, fileOffset?:integer, maxRecords?:integer, project?:string, splatYaml?:string, segment?:string, projectDir?:string, context?:integer, window?:integer, banks?:array, maxSitesPerBank?:integer, excludeBanks?:array, endian?:string(LE|BE), reverseHandler?:integer

## encodeArt
Encode a PNG into a platform's native art format, one tool keyed by `stage` - the PNG→tiles pipeline. tiles/tilemap read `pngPath` (preferred - server reads it, no base64 token cost) or `pngBase64`, write to `outputDir` (or `inline`). quantize/crop instead take `path` (source PNG) + `outputPath`. **Image width & height must be multiples of 8.** **GENESIS: a 17th color (palette index > 15) leaking into the tile words builds fine but renders GARBAGE - run stage:'validate' on generated Genesis tiles.**
`POST /tool/encodeArt` params: stage:string(quantize|crop|tiles|tilemap|validate), platform?:string, pngBase64?:string, pngPath?:string, path?:string, outputPath?:string, outputDir?:string, inline?:boolean, mode?:string(frequency|luminance|platform-master), maxColors?:integer, tileX?:integer, tileY?:integer, tileW?:integer, tileH?:integer, tileSize?:integer, tileOrder?:string(row|sprite), baseIndex?:integer, flip?:boolean, name?:string, outputCPath?:string, maxTiles?:integer, backdrop?:integer, dedup?:boolean, singlePalette?:boolean, tileDataPath?:string, paletteJson?:array, maxPaletteIndex?:integer, intent:string(homebrew|rom-hack)

## encodeAudio
Encode an external audio clip into a platform's native sample/music format, keyed by `target`.
`POST /tool/encodeAudio` params: target:string(brr|xgm2pcm|xgm2|maxmod|famitone|spc|gg|sms|c64|lynx|atari7800|gb|gbc|sync32|sync32pcm), rate?:integer, psgQuantize?:boolean, pcmBase64?:string, pcmPath?:string, loop?:boolean, wavPath?:string, wavBase64?:string, name?:string, halfRate?:boolean, format?:string(wav|pcm16), pcmRate?:integer, outputCPath?:string, outputPcmPath?:string, vgmPath?:string, vgmBase64?:string, system?:string(ntsc|pal), outputBinPath?:string, modulePath?:string, moduleBase64?:string, outputHeaderPath?:string, txtPath?:string, txt?:string, outputAsmPath?:string, noWarnings?:boolean, keepInstruments?:boolean, song?:any, base?:string,number, baseP?:integer, defaultTicks?:integer, outputPath?:string

## examples
The example-game library - one buildable, rendering starting point per platform×genre, and the ONLY way to start a new project: **never start from a blank file - fork the nearest example and modify it into your game, even a very different game.** These are SCAFFOLDING, not showcases: the gameplay is intentionally thin (treat it as placeholder and reshape it) - their value is that they already carry the platform's boot sequence, APIs, and syntax wired up and WORKING, so you change 2 things while 13 keep working instead of getting 15 right from nothing. (Retro bring-up is a long chain of fragile hardware init with zero partial credit; a working game is a regression oracle.) `op`: 'list' | 'fork' | 'show' | 'snippets' | 'copySnippets'.
`POST /tool/examples` params: op:string(list|fork|show|snippets|copySnippets), platform?:string, example?:string, template?:string, name?:string, path?:string, title?:string, overwrite?:boolean, verbose?:boolean, file?:string, technique?:string, mode?:string(list|get|getAll), snippetName?:string, language?:string, outputPath?:string, inline?:boolean, destinationDir?:string, include?:array

## feedback
Report a romdev defect or a token sink you actually hit, keyed by `op`. op:'record' (default) appends ONE structured line to a LOCAL append-only log (~/.romdev/feedback.jsonl, or $ROMDEV_FEEDBACK_PATH) stamped with romdevVersion, serverPid, the session's loaded platform + media path, and the time - the stamps every hand-written report used to pay shell calls to collect. Nothing leaves the machine; the human sends the file to the maintainer. Use it for: a tool that returned wrong/misleading output, a documented step that fails, an error whose text hid the cause, a host-toolchain install that started, or a job that took far more calls than it should have (say what would have made it one call). NOT for restating doc nits noticed in passing - one report per distinct issue. op:'list' reads back the last `last` entries.
`POST /tool/feedback` params: op?:string(record|list), title?:string, body?:string, severity?:string(blocker|bug|ergonomics|token|doc|idea), tool?:string, platform?:string, tokensWasted?:string, last?:integer

## files
Generic file I/O on disk for arbitrary agent artifacts (a generated PNG, a backup ROM, a notes file, a work-in-progress source). `op:'read'|'write'|'list'`. `write` takes `text` (utf-8) OR `base64` (binary) and creates parent dirs. `read` returns `text` or `base64` per `as`, with a default 64 KB cap so a bare read can't dump a huge file into your context - if larger, it returns a note telling you to raise `maxBytes` (up to 10 MB) deliberately. `list` enumerates a directory with an optional case-insensitive `pattern` substring filter.
`POST /tool/files` params: op:string(read|write|list), path:string, text?:string, base64?:string, as?:string(text|base64), maxBytes?:integer, pattern?:string

## frame
Advance the emulator and capture frames. `op`: 'step' | 'screenshot' | 'stepAndShot' | 'sideBySide' | 'compareRam' | 'findDiverge' | 'compareRender' | 'portStatus' | 'stepInstruction' | 'stepInstructions' | 'traceInstructions' | 'verify' | 'verifyRecompile' | 'fuzzRecompile'.
`POST /tool/frame` params: op:string(step|screenshot|stepAndShot|sideBySide|compareRam|findDiverge|compareRender|portStatus|stepInstruction|stepInstructions|traceInstructions|verify|verifyRecompile|fuzzRecompile|cycles), count?:integer, withRegisters?:boolean, stepFormat?:string(full|compact), frames?:integer, slot?:string(a|b), region?:string, regionB?:string, offsetA?:integer, offsetB?:integer, compareLength?:integer, restore?:boolean, maxRanges?:integer, maxFrames?:integer, cart?:string, reference?:string, platform?:string, referenceCore?:string, firmware?:string, from?:integer, to?:integer, profile?:boolean, map?:string, groups?:object, top?:integer, series?:boolean, annotate?:string, perFrame?:boolean, atFrames?:array, auto?:any, input?:any, wrongInput?:any, cartFrameOffset?:any, searchFrame?:integer, searchWindow?:integer, minSharpness?:number, sweep?:integer, cartOrigin?:array, cartButtonMap?:object, regions?:object, fields?:object, probe?:object, warmupFrames?:integer, vramZero?:array, controls?:array, movingWindow?:integer, wrongFrameDelta?:integer, wrongFrameMaxDelta?:integer, minChangePx?:integer, minContentPct?:number, minContentPx?:integer, minMovingPct?:number, minMovingPx?:integer, requireStateMatch?:boolean, outputDir?:string, tag?:string, level?:string(frame|instruction), atFrame?:integer, context?:integer, refState?:boolean, seeds?:array, fromPc?:integer, maxEntries?:integer, head?:integer, startFrame?:integer, stride?:integer, audio?:any, audioFrames?:array, audioStream?:string, audioBar?:object, audioControls?:array, audioDropChannel?:string, audioWav?:boolean, audioMaxLag?:integer, format?:string(png|ascii|full|compact), source?:string(composite|core|both), path?:string, outputPath?:string, inline?:boolean, overlayBoxes?:boolean, crop?:object, scale?:number, cols?:integer, rows?:integer, symbols?:string(ascii|halfblock|block|quad|sextant), colors?:string(16|256|true|fgbg)

## host
Emulator host lifecycle. `op`: 'unload' | 'shutdown' | 'reset' | 'pause' | 'resume' | 'play' | 'stop'. (Loading media is the separate `loadMedia` tool.)
`POST /tool/host` params: op:string(unload|shutdown|reset|pause|resume|play|stop), seconds?:number, hard?:boolean, slot?:string(a|b)

## importArt
Import art from an editor file or a source ROM into the target platform's native tile bytes, one tool keyed by `from`. Shared spine: `platform` (controls the tile encoding - NES planar 2bpp, GB interleaved 2bpp, SNES planar-pairs 4bpp, Genesis packed 4bpp, ...), `outputDir` (write blobs to disk instead of base64-inlining), and for the editor formats `emit` (c=`const unsigned char tiles[]`; ca65=`.byte $NN` for cc65/NES; rgbasm=`db $NN` for GB/GBC - each tile preceded by a slice-naming comment) + `emitDefines` (name→tile-id constants). All editor loaders dedup tiles and return tile_bytes + per-frame/slice/cell `tile_indices`.
`POST /tool/importArt` params: from:string(aseprite|gif|texturepacker|tiled|rom), platform:string, outputDir?:string, emit?:string(raw|c|ca65|rgbasm), emitDefines?:boolean, path?:string, pngPath?:string, manifestPath?:string, slice_strategy?:string(slices|frames|grid), frame_indices?:array, dedup?:string(merge|preserve|preserve-blanks), sourceRom?:string, sourcePlatform?:string, sourceBank?:integer, sourceOffset?:integer, sourceTileX?:integer, sourceTileY?:integer, sourceTileW?:integer, sourceTileH?:integer, outputPng?:string, outputManifest?:string, quantizeMode?:string(frequency|luminance|platform-master), tilesPerRow?:integer, namePrefix?:string, paletteFromEmulator?:boolean, paletteIndex?:integer, intent?:string(homebrew|rom-hack)

## input
Drive the controller. `op`: 'set' | 'press' | 'sequence' | 'navigate' | 'layout'.
`POST /tool/input` params: op:string(set|press|sequence|timeline|navigate|layout|pressKey|typeText|joyport|pointer|wheel), x?:integer, y?:integer, left?:boolean, right?:boolean, id?:integer, active?:boolean, notches?:number, notchesX?:number, dx?:integer, dy?:integer, ports?:array, timeline?:array, untilFrame?:integer, button?:string(1|2|up|down|left|right|north|east|south|west|a|b|x|y|l|r|l2|r2|l3|r3|start|select|c), frames?:integer, port?:integer, steps?:array, platform?:string, key?:string, text?:string, joyport?:integer, verify?:boolean

## loadMedia
Load a ROM/disk/tape/program into a fresh host - resolves the libretro core automatically. Pass `path` (file on disk) OR `base64` (ROM bytes - e.g. straight from build, no disk write, for a fast iteration loop). `cheats` apply BEFORE the first frame (one call instead of loadMedia + cheats({op:'apply'})), so a boot-time code that changes a value the reset code reads is in effect from frame 0. `slot:'b'` loads into the SECONDARY comparison host (a different platform is fine) so two cores can run at once for frame({op:'sideBySide'}) - the original-vs-port compare loop; slot B does not affect slot A or the livestream. NOTE: framebuffer dimensions are omitted until you step frames (frame({op:'step'})) - the pre-boot default does not match the real output resolution.
`POST /tool/loadMedia` params: platform:string, path?:string, base64?:string, mediaKind?:string(cartridge|disk|tape|program), virtualName?:string, cheats?:array, slot?:string(a|b), useActiveBezel?:boolean, activeBezelPath?:string, activeBezelConfig?:object, activeBezelForce?:boolean, activeBezelRenderer?:string(software|gpu), deterministicStepMs?:number, deterministicSeed?:integer, core?:string, firmware?:string, coreOptions?:object, gpuPower?:string(low-power|high-performance), wgpu?:boolean, presentWindow?:boolean

## memory
Read / write / search the core's memory regions, one tool keyed by `op`. `region` is the single canonical enum (system_ram, save_ram, video_ram, rtc; NES nes_nametables/nes_palette/nes_oam/nes_chr; SNES snes_oam/snes_cgram/snes_aram/snes_fillram; Genesis genesis_cram/vsram/vdp_regs/z80_ram/...). The response carries each region's endianness + wordSize.
`POST /tool/memory` params: op:string(read|write|readCart|regions|snapshot|diff|diffRuns|classify|search|searchUnknown|searchNext|provenance), region?:string(save_ram|rtc|system_ram|video_ram|nes_nametables|nes_palette|nes_oam|nes_chr|nes_apu_regs|nes_cpu_regs|nes_ppu_regs|nes_cart_ram|nes_ppu_scroll|nes_ppu_scroll_lines|nes_chr_lines|nes_bgfetch|nes_sprlines|nes_ntmap|nes_pallines|nes_masklines|nes_ntmaplines|nes_bgpix|nes_backdrop|nes_sprdrawn|nes_bgval|nes_maskpix|nes_linepix|nes_linedeemp|nes_palrgb|snes_oam|snes_cgram|snes_aram|snes_fillram|snes_linepix|snes_linestate|snes_frameinfo|snes_m7lines|snes_linedepth|snes_cliplines|snes_lp_world|snes_lp_obj|snes_timing|snes_chipstate|snes_bsx_psram|snes_chiplog|genesis_cram|genesis_vsram|genesis_vdp_regs|genesis_z80_ram|genesis_m68k|genesis_ym2612|genesis_psg|genesis_svp_dram|genesis_svp_iram|genesis_svp_ssp|md_linepix|md_bgpix|md_objpix|md_pixrgb|md_linestate|md_pixlines|sms_linepix|sms_bgpix|sms_objpix|sms_pixrgb|sms_linestate|sms_pixlines|gg_linepix|gg_bgpix|gg_objpix|gg_pixrgb|gg_linestate|gg_pixlines|sms_vram|sms_cram|sms_vdp_regs|sms_z80_regs|gg_vram|gg_cram|gpgx_blip_deltas|gb_vram|gb_oam|gb_io|gb_hram|gb_bgpdata|gb_objpdata|gb_cpu_regs|gb_lineregs|gb_bgpix|gb_sprpix|gb_palline|gb_bgcol15|gb_sprcol15|gb_lcdlog|gb_apu_raw|a78_cpu_regs|a26_tia_regs|a26_cpu_regs|c64_color_ram|c64_vic_regs|c64_sid_regs|c64_cia1_regs|c64_cia2_regs|c64_cpu_regs|gba_cpu_regs|gba_io_regs|gba_palette|gba_oam|gba_iwram|gba_timing|gba_audio_raw|sync32_cpu_regs|sync32_palette|sync32_canvas|sync32_timing|sync32_profile|sync32_sheet0|lynx_cpu_regs|lynx_hw_regs|pce_vdc_vram|pce_vdc_satb|pce_vdc_regs|pce_vce_palette|pce_cpu_regs|pce_psg_regs|pce_vdc_reglines|pce_vce_pallines|pce_vdc_linepix|pce_vce_xofflines|pce_vce_srclines|pce_paldeltas|msx_vram|msx_vdp_regs|msx_vdp_status|msx_palette|msx_cpu_regs|msx_psg_regs|msx_vdp_reglines|msx_vram_deltas|msx_fb_tail), offset?:integer, address?:any, length?:integer, cpuAddress?:integer, bank?:integer, mapper?:string(lorom|hirom), offsets?:array, compact?:boolean, romPath?:string, platform?:string, findHex?:string, maxMatches?:integer, hex?:string, dataHex?:string, base64?:string, data?:any, bytes?:any, name?:string, view?:string(summary|raw), maxChanges?:integer, maxClusters?:integer, gap?:integer, minDelta?:integer, changeDir?:string(inc|dec), deltaEq?:integer, beforeMin?:integer, beforeMax?:integer, afterMin?:integer, afterMax?:integer, frames?:integer, portsA?:array, portsB?:array, value?:integer, size?:integer, as?:string(raw|bcd|digits), compare?:string(eq|changed|unchanged|inc|dec|gt|lt), maxCandidates?:integer, nearDistance?:integer, extendBy?:integer, minLength?:integer, outputPath?:string, path?:string, inline?:boolean, echo?:boolean

## pack
Package a native-runtime game's source into its distributable archive (the 'build' step for wasmcart/jsgame - a ZIP, NOT a compiler). `target`:
`POST /tool/pack` params: target:string(wasc|jsgame), source?:string, wasm?:string, assets?:string, outputPath:string, name?:string, players?:integer

## palette
Color palettes - read the running ROM's live palette, get a platform's master palette, or fetch a Lospec palette. `source`: 'live' | 'platformMaster' | 'lospec'.
`POST /tool/palette` params: source:string(live|platformMaster|lospec), platform?:string, area?:string(bg|sprite|all), subPalette?:integer, outputPath?:string, inline?:boolean, format?:string(png|lospec|hex), id?:string, asPlatform?:string

## platform
Platform/toolchain/docs discovery - what romdev can run and how. `op`: 'list' | 'capabilities' | 'resolve' | 'toolchains' | 'docs' | 'doc'.
`POST /tool/platform` params: op:string(list|capabilities|resolve|toolchains|docs|doc), platform?:string, slim?:boolean, id?:string, name?:string

## playtest
Show the loaded ROM to a HUMAN in a native SDL window, one tool keyed by `op`. For your OWN build-iteration testing use frame({op:'screenshot'}) / build({output:'run'}) instead.
`POST /tool/playtest` params: op?:string(open|stop|status|framebuffer|fps|bezel), scale?:integer, title?:string, aspect?:string(fb|tv|core), path?:string, inline?:boolean, fpsOverlay?:boolean, fastPresent?:boolean, show?:boolean

## recordSession
Run the loaded ROM for N frames, sampling screenshots and/or memory every sampleEvery frames. Returns a timeline the agent can analyze. Inputs are either held for the whole session (holdInputs) or scripted as {atFrame, ports} entries each held until the next (inputScript). Screenshots (includeScreenshots, default true): every sampled frame ALWAYS streams to the human's /livestream (over REST or romdev, no flag needed). For the AGENT's response: pass outputDir to also write frame-<n>.png per sample (timeline gets screenshotPath), or inline:true to embed screenshotBase64 per entry (opt-in - NOT default, so image bytes don't flood your context). With neither, frames still go to /livestream and the response stays compact (just the timeline). Set includeScreenshots:false to skip capture entirely (memory-only runs). Memory (memorySamples): accepts the full memory({op:'read'}) region set incl. hardware registers (nes_apu_regs, etc.); hex appears per-sample in the timeline. For dense sampling (sampleEvery:1 over a long loop, e.g. APU regs across a music loop) add memoryOutputPath to stream rows to NDJSON on disk and keep the hex OUT of context - the response returns a compact summary {path, rows, regions, valueRanges} instead.
`POST /tool/recordSession` params: frames?:integer, sampleEvery?:integer, holdInputs?:array, inputScript?:array, memorySamples?:array, includeScreenshots?:boolean, outputDir?:string, inline?:boolean, memoryOutputPath?:string

## regression
Checkpoint-based golden regression harness - prove a change didn't break a game. Host-kind-agnostic (emulators AND wasmcart). `op:'capture'` runs an `inputScript`, records observations at `checkpoints` into a golden JSON at `goldenPath`. `op:'check'` re-runs the SAME script and compares to the golden → {passed, diffs[]}. REPLAYS FROM THE LOADED STATE (loadMedia fresh first) - no per-frame savestate, so it scales to any cart size. Observations per checkpoint: 'frameHash' (framebuffer fingerprint - reproducible only on a deterministic cart), 'debug' (wasmcart NAMED debug-state values - the size-independent, deterministic path: 'at frame 600, hp==3' costs the same at 128KB or 2GB of heap), 'memory' (emulator regions). For large / non-deterministic carts, prefer 'debug' (or 'memory' on emulators) over 'frameHash'. Load the ROM/cart, then capture once, then check after every change.
`POST /tool/regression` params: op:string(capture|check), goldenPath:string, inputScript?:array, checkpoints?:array

## romPatch
Patch / re-inject / inspect a ROM file on disk, one tool keyed by `op`. **`expect=` (the bytes you think are there now) on every write guards the classic wrong-revision-corruption footgun - highly recommended.** Spine: `{path, platform}`. **TIP: before patching, prove the byte matters by forcing it live with memory({op:'write'}) on the running emulator (static disasm can't tell 'matches the pattern' from 'actually runs').**
`POST /tool/romPatch` params: op:string(write|writeMany|spliceCHR|relocate|makeStored|findFree|findPointer|diff|gbHeader), path?:string, platform?:string(nes|gb|gbc|sms|gg|c64|lynx|atari2600|atari7800|pce|msx|genesis|snes|gba), offset?:integer, hex?:string, base64?:string, expect?:string, outputPath?:string, allowExpand?:boolean, input?:string, output?:string, writes?:array, pngBase64?:string, tileIndex?:integer, bank?:integer, chrFileOffset?:integer, paletteHint?:array, newHex?:string, newBase64?:string, toOffset?:integer, pointerOffset?:integer, pointerWidth?:integer, pointerEndian?:string(le|be), pointerValue?:integer, dryRun?:boolean, rawHex?:string, rawBytes?:array, format?:string, interleave?:integer, minLength?:integer, fillBytes?:array, start?:integer, end?:integer, maxRunsReturned?:integer, romOffset?:integer, mapper?:string(lorom|hirom), maxHitsReturned?:integer, widths?:array, suppressShadows?:boolean, a?:string, b?:string, maxChangesReturned?:integer, cgb?:boolean, title?:string, cartType?:integer, romSize?:integer, ramSize?:integer, destination?:integer

## runUntil
Step the emulator forward until a condition holds, or until maxFrames is reached. Use this instead of polling frame({op:'step'}) + memory({op:'read'}) yourself for 'play until X happens' workflows. condition.type is one of: 'memory' (byte at region/offset equals/notEquals a value, or mask hits when byte & mask is nonzero); 'memoryChanged' (any byte in offset..offset+length differs from start-of-call); 'framebufferChanged' (any pixel differs from start-of-call); 'framebufferPixel' (pixel x,y equals/notEquals an [r,g,b]). checkEvery throttles condition checks (and is the step batch size), so the actual stop frame can overshoot by up to checkEvery-1. Returns {conditionMet, framesStepped, finalValue} (finalValue is null when the condition was not met).
`POST /tool/runUntil` params: condition:any, maxFrames?:integer, checkEvery?:integer

## sprites
Hardware-sprite (OAM/SAT) inspection + the meta-sprite asset pipeline, one tool keyed by `op`.
`POST /tool/sprites` params: op:string(inspect|group|preview|capture|render|emitC|extractScreenshot), platform?:string, maxSlots?:integer, rect?:object, slots?:array, includePartials?:boolean, name?:string, emit?:string(json|c|both), gap?:integer, maxGroups?:integer, tilesPath?:string, palettePath?:string, layoutPath?:string, pngPath?:string, crop?:object, seed?:object, backgroundMode?:string(edge-flood|color), bgColor?:array, tolerance?:number, previewScale?:integer, outputPath?:string, outputDir?:string, inline?:boolean

## state
Save-state lifecycle for the emulator. `op`: 'save' | 'load' | 'list' | 'export' | 'dump' | 'diff'.
`POST /tool/state` params: op:string(save|load|list|export|dump|diff|exportSram|importSram|exportDisk|importDisk|putDiskFile|autoSnapshot|recoverSnapshot), name?:string, unit?:integer, path?:string, enabled?:boolean, intervalSeconds?:integer, dir?:string, recordCheats?:boolean, render?:boolean, probeLiveness?:boolean, reapplyCheats?:boolean, fromSlot?:string, findHex?:string, maxMatches?:integer, snapOrDiff?:string(snapshot|diff)

## symbols
Symbol/linker-map lookups for C/asm-built ROMs - resolve names ↔ addresses and see the memory layout. `op`: 'resolve' | 'lookup' | 'map' | 'list' | 'addr'.
`POST /tool/symbols` params: op:string(resolve|lookup|map|list|addr|analyze), dbg?:string, map?:string, dbgPath?:string, mapPath?:string, name?:string, address?:integer, max?:integer, platform?:string, pc?:integer, symbolsText?:string, symbolsPath?:string, romPath?:string, summary?:boolean, topN?:integer

## text
Custom-font text workflow for ROM hacking - learn a game's character→tile encoding, then encode/find strings. `op`: 'learn' | 'encode' | 'find'.
`POST /tool/text` params: op:string(learn|encode|find), romPath?:string, platform?:string, text?:string, fontMap?:object, fontMapPath?:string, knownStrings?:array, fromScreen?:array, which?:integer, alphabet?:string, unknownChar?:integer, maxResults?:integer

## tiles
DECODE & render tile / CHR / pattern-table / VRAM bytes, one tool keyed by `op`. `intent` is REQUIRED on EVERY call (no default); it only changes output for the file/preview palette path but the schema demands it always. OP CHEAT-SHEET (params each op uses, plus the required `intent`): png live VRAM → {platform?, scale?, bpp?, tileBaseByte?, paletteBase?, paletteIndex?, tileCount?, outputPath?|inline?}; png file → {platform, path, bank?|offset?, count?, paletteIndex?, paletteFromEmulator?, tilesPerRow?, outputPath?}; pixels → {tileIndex, platform?, path?, logicalPixels?}; fingerprints → {start?, count?, platform?, path?, logicalPixels?}; ascii → {start?, count?, platform?, path?, logicalPixels?}; preview → {tileBytes|tilePath|fromEmulator, platform, palette?|paletteFromEmulator?|palettePath?, paletteIndex?, tileStart?|byteOffset?, tileCount?, tilesPerRow?, scale?, outputPath?}.
`POST /tool/tiles` params: op:string(png|pixels|fingerprints|ascii|preview), platform?:string, path?:string, logicalPixels?:boolean, tileIndex?:integer, start?:integer, count?:integer, scale?:integer, bpp?:any, tileBaseByte?:integer, paletteBase?:integer, paletteIndex?:integer, tileCount?:integer, offset?:integer, bank?:integer, paletteFromEmulator?:boolean, tilesPerRow?:integer, tileBytes?:string, tilePath?:string, fromEmulator?:boolean, tileStart?:integer, byteOffset?:integer, palette?:array, palettePath?:string, outputPath?:string, inline?:boolean, intent:string(homebrew|rom-hack)

## videoDebug
Decode the running ROM's VIDEO chip state into named fields - the counterpart to audioDebug({op:'inspect'}).
`POST /tool/videoDebug` params: op?:string(inspect), chip?:string(vdp)

## wasm
Inspect a WASM-runtime cart (wasmcart) - the introspection an emulator can't give, because the cart is a real WebAssembly instance in V8. `op`:
`POST /tool/wasm` params: op:string(conformance|info|exports|debugState|events|read|write|save|command), text?:string, maxFrames?:integer, name?:string, value?:number, offset?:integer, length?:integer, hex?:string, base64?:string, inline?:boolean

## watch
LOG-ALL dynamic tracing - run N frames and log EVERY hit (not stop-on-first; for stop-on-first use `breakpoint`). One tool keyed by `on`.
`POST /tool/watch` params: on:string(mem|range|pc|dma|copy), region?:string(save_ram|rtc|system_ram|video_ram|nes_nametables|nes_palette|nes_oam|nes_chr|nes_apu_regs|nes_cpu_regs|nes_ppu_regs|nes_cart_ram|nes_ppu_scroll|nes_ppu_scroll_lines|nes_chr_lines|nes_bgfetch|nes_sprlines|nes_ntmap|nes_pallines|nes_masklines|nes_ntmaplines|nes_bgpix|nes_backdrop|nes_sprdrawn|nes_bgval|nes_maskpix|nes_linepix|nes_linedeemp|nes_palrgb|snes_oam|snes_cgram|snes_aram|snes_fillram|snes_linepix|snes_linestate|snes_frameinfo|snes_m7lines|snes_linedepth|snes_cliplines|snes_lp_world|snes_lp_obj|snes_timing|snes_chipstate|snes_bsx_psram|snes_chiplog|genesis_cram|genesis_vsram|genesis_vdp_regs|genesis_z80_ram|genesis_m68k|genesis_ym2612|genesis_psg|genesis_svp_dram|genesis_svp_iram|genesis_svp_ssp|md_linepix|md_bgpix|md_objpix|md_pixrgb|md_linestate|md_pixlines|sms_linepix|sms_bgpix|sms_objpix|sms_pixrgb|sms_linestate|sms_pixlines|gg_linepix|gg_bgpix|gg_objpix|gg_pixrgb|gg_linestate|gg_pixlines|sms_vram|sms_cram|sms_vdp_regs|sms_z80_regs|gg_vram|gg_cram|gpgx_blip_deltas|gb_vram|gb_oam|gb_io|gb_hram|gb_bgpdata|gb_objpdata|gb_cpu_regs|gb_lineregs|gb_bgpix|gb_sprpix|gb_palline|gb_bgcol15|gb_sprcol15|gb_lcdlog|gb_apu_raw|a78_cpu_regs|a26_tia_regs|a26_cpu_regs|c64_color_ram|c64_vic_regs|c64_sid_regs|c64_cia1_regs|c64_cia2_regs|c64_cpu_regs|gba_cpu_regs|gba_io_regs|gba_palette|gba_oam|gba_iwram|gba_timing|gba_audio_raw|sync32_cpu_regs|sync32_palette|sync32_canvas|sync32_timing|sync32_profile|sync32_sheet0|lynx_cpu_regs|lynx_hw_regs|pce_vdc_vram|pce_vdc_satb|pce_vdc_regs|pce_vce_palette|pce_cpu_regs|pce_psg_regs|pce_vdc_reglines|pce_vce_pallines|pce_vdc_linepix|pce_vce_xofflines|pce_vce_srclines|pce_paldeltas|msx_vram|msx_vdp_regs|msx_vdp_status|msx_palette|msx_cpu_regs|msx_psg_regs|msx_vdp_reglines|msx_vram_deltas|msx_fb_tail), offset?:integer, length?:integer, ranges?:array, onChange?:string(any|increase|decrease|reset), valueFilter?:object, maxEvents?:integer, format?:string(events|series), sampleEvery?:integer, groupByPC?:boolean, cheatLabels?:string, stopOnFirst?:boolean, kind?:string(read|write|both), distinctPCsOnly?:boolean, dbg?:string, map?:string, dbgPath?:string, mapPath?:string, autoNarrow?:boolean, start?:integer, end?:integer, frames?:integer, limit?:integer, outputPath?:string, perFrame?:boolean, precision?:string(exact|sampled), vramDest?:integer, destWindow?:integer, dedupe?:boolean, sourceFilter?:string(all|rom-only|ram-only), romPreviewBytes?:integer, minLengthBytes?:integer, pressDuring?:array, fromState?:string, fromStatePath?:string

