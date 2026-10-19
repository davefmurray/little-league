---
name: nes-romdev-debug
description: Drive romdev from the shell to debug NES ROMs — session setup, screenshots, input schedules, exact write/PC breakpoints, CPU calls, memory regions, and the NES-specific traps that produce false conclusions. Use when tracing a NES routine, comparing ROMs, or verifying a hack in an emulator.
---

# NES debugging through romdev

romdev runs locally on `http://localhost:7331`; each tool is
`POST /tool/{name}` with a JSON body. Use fceumm for NES — jsnes 1.2.1 has a
broken MMC1 shift counter.

## Start and keep a session

```sh
npm_config_cache="$PWD/.npm-cache" npx -y romdevtools &
curl -s http://127.0.0.1:7331/healthz
```

Pick one descriptive session id and send it on **every** call:

```sh
S='x-romdev-session: llbcs-debug'
B='http://127.0.0.1:7331'
curl -s -X POST $B/tool/loadMedia -H 'content-type: application/json' -H "$S" \
  -d '{"platform":"nes","path":"/abs/path/game.nes"}'
```

The server may be killed at turn boundaries. If a call gets connection-refused,
restart it and re-load the ROM; do not assume the previous state survived.

## Screenshots

```sh
curl -s -X POST $B/tool/frame -H 'content-type: application/json' -H "$S" \
  -d '{"op":"screenshot","path":"/tmp/shot.png"}'
```

Then read `/tmp/shot.png` with the image reader. **The NES viewport is
256×224** (8 px cropped top and bottom), not 240. A missing first row is often a
crop, not a bug.

## Input

Buttons must be lowercase: `a`, `b`, `start`, `select`, `up`, `down`, `left`,
`right`.

```sh
curl -s -X POST $B/tool/input -H 'content-type: application/json' -H "$S" \
  -d '{"op":"press","button":"a","frames":4}'
```

Menus often need a step between presses. Two frames is usually enough for a
press; 4 is safer. A held button can be re-read as a repeat — use
rising-edge logic in ROM, not a tight loop.

## Exact breakpoints

`on:"write"` with `precision:"exact"` reports the real writer PC, bank, caller,
and value. Drive the game while it waits with `pressDuring`:

```sh
curl -s -X POST $B/tool/breakpoint -H 'content-type: application/json' -H "$S" \
  -d '{"on":"write","address":1263,"precision":"exact","maxFrames":180,
       "pressDuring":[{"frame":10,"button":"a","frames":4}]}'
```

Response includes `pc`, `bank`, `prgOffset`, `registersAtHit`, `callStack`, and
`hits`. For reads use `on:"read"`; for “who runs here” use `on:"pc"` and read
`registersAtHit` in the hit response (a follow-up `cpu read` is too late).

A no-hit result has two meanings: the event did not fire, or the region is
rebuilt as a block (OAM/VRAM/display-list copy). Watch the source struct or the
copy loop, not the destination byte.

## Calling ROM routines

```sh
curl -s -X POST $B/tool/cpu -H 'content-type: application/json' -H "$S" \
  -d '{"op":"call","pc":44090,"presetMemory":[{"addr":193,"hex":"02"}],
       "maxInstructions":300000,"sandbox":false}'
```

- `presetMemory` entries are `{addr,hex}` — `{region,offset,value}` is rejected.
- `sandbox:true` discards writes; use it to test that a routine returns, then
  rerun with `false` to inspect memory.
- `returned:false` means the routine did not RTS; the harness restores the CPU
  context, so the callee's stack may still be dirty. Reload before trusting RAM.
- `framesRun:1` means the game's frame machinery ran during the call; a
  timing-sensitive result can be suspect.

## Memory regions

- `system_ram` is 2 KiB (`$0000–$07FF`).
- `nes_cart_ram` is PRG RAM at `$6000–$7FFF`; offset = `addr - 0x6000`.
- `$8000+` is banked ROM, not a writable region.
- Region offsets are not always the CPU address you think. For ground truth,
  write a tiny routine in system RAM that copies the target range to `$0400`,
  `cpu call` it, then read `$0400`. This avoids mapper/region mapping doubts.

```asm
; copy $7700..$771F to $0400
LDX #$00
loop: LDA $7700,X
      STA $0400,X
      INX
      CPX #$20
      BNE loop
      RTS
```

## NES-specific traps

1. **PRG RAM must be enabled.** Clearing CHR0 bit 4 (`LDA #0; JSR $C11C`) is not
   enough if it happens after the write. Verify with a CPU write/read
   round-trip, not by reading a debugger region.
2. **NMI corrupts timing-sensitive writes.** Disable NMI (`LDA #0; STA $2000`)
   before a seed/table build, then re-enable before returning to the main loop.
3. **Hook the right instruction.** Do not replace an instruction that loads A
   with a `JSR` unless the trampoline re-executes it. Prefer hooking a store
   after init, and re-run the replaced instruction first.
4. **`$C040` is a ROM constant (`$40`), used as a `BIT` mask by the display-list
   flush.** Writing it does nothing. To choose normal vs RLE, control each run's
   high byte (bit 6), not `$C040`.
5. **A blank screen can be an infinite wait, not a crash.** Read `cpu.pc`; if it
   sits in a known wait loop, check the flag it polls (e.g. `$047D` needs NMI).
6. **Bank-tag every `$8000–$BFFF` address.** `disasm` needs `bank`; a PC in that
   range is meaningless without it.
7. **Menu navigation is a hypothesis.** Verify each screen after every press;
   "CONTINUE" can mean keep editing, not confirm.

## Regression comparison

`tools/verify_regression.py` loads two ROMs, runs both 180 frames, and compares
screenshot + all 2 KiB of system RAM:

```sh
.venv/bin/python tools/verify_regression.py stock.nes build/hack.nes
```

Green is `screenshots MATCH` and `system_ram differs in 0 bytes`. If it differs,
do not ship the build; find the first frame where RAM diverges.
