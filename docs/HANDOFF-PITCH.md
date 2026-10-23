# HANDOFF — 32-team ROM, pitch capture/restore (fresh-start)

Repo: `/Users/dfm/GitHub/nesdav/little-league` · branch `main` · HEAD `0fd0e8d`
Working tree clean; stock `build/direct31.nes` = pinned `d043ecdf…`.

> Older context: `docs/HANDOFF.md` covers the launch bridge; this file covers
> the current pitch blocker and the whole remaining graph.

## Read first

1. `docs/AUTOLOOP.md` — loop contract (pick → start → baseline → change → verify → done/block/add → commit).
2. `docs/backlog.json` — 20 tasks; see the `pitch-06e2` resume note.
3. `docs/AUTORUN-REPORT.md` — rounds 250–267 are the pitch debug trail.
4. `TODO-NEXT.md` / `TODO-STEP2.md` — the human list.

## State

- **10/20 done:** launch-bridge, order-start, field-cache, match5, scene1e, hw-docs, bench-design, step2, regression, pitch-ad10-trace.
- **Blocked:** pitch-06e2, list-dispatch, password-decode, hardware-audio.
- **Queued:** pitch-odd, pitch-restructure, soak-26, bridge-integrate, list-seed, password-encode.
- Skills installed: `6502-assembly` + the `nes-*` set (`~/.agents/skills`, symlinked to `~/.claude/skills`; also `~/.codex/skills`).

## Pitch — finish this first

Base ROM: `build/direct31-pair17.nes` (keep its three patches).

| Patch | Bytes | Purpose |
|---|---|---|
| pair13 | `$AD4E`: prefill `$06E2[2t]=$06E2[2t+1]=(t<<4)\|t` | real 32-byte group table |
| pair16 | `$AA65`/`$AA68`: `EA ×6` | stops `STA $06F4/$06F5` zeroing team-9 slots |
| pair17 | `$B24C`: `EA ×5` | forces the `$B234` copy |

Result: boots, matches 0–4 OK, **match 5 stalls** with `$0490=00/$0491=00`.

### Debug evidence

- Pair loader: `$A490` → `$A3C2` → `$0525/$0526`; `$B234` copies `$0524/$0525` → `$0490/$0491` (`$B23E-$B247`).
- At field entry (`$047B=03`): **`$0490=01`, `$0491=09`**.
- At scene 05 (`$047B=05`): `$AC09`/`$AC9F` (bank7; fixed copies `$EC09`/`$EC9F`) write `$00` to them. Every live pair cell (`$0490/$0491/$0524/$0525/$0526/$04EF/$04F0`) reads `00` at that point.
- The order then reads `$0490=00` and never matches group 9.

### The fix

1. Capture at `$B247` (after the `$0491` store), into spare RAM (`$04D1/$04D2` — verify free first):

```
AD 90 04   LDA $0490
8D D1 04   STA $04D1
AD 91 04   LDA $0491
8D D2 04   STA $04D2
```

2. Restore at the scene-05 clear (`$AC09` / `$AC9F`) instead of `LDA #$00`:

```
AD D1 04   LDA $04D1      AD D2 04   LDA $04D2
8D 90 04   STA $0490      8D 91 04   STA $0491
```

3. Soak:

```bash
timeout 300 python3 tools/soak_bracket.py --rom build/direct31-pair22.nes --matches 10 --winner score --mode speed
./tools/verify.sh --with-soak          # stock must stay green
```

**Risk:** the capture at `$B247` overwrites `$B24C` (`LDA $0523` / `BNE $B259`), which pair17 already NOPs. If that hurts other paths, put the capture in a `JSR` helper in free ROM instead.

### Acceptance

10-match passes match 5 → stock verify green → `python3 tools/backlog.py done pitch-06e2 --evidence "10-match pass, stock verify green" --commit "$(git rev-parse --short HEAD)"` → `backlog.py pick`.

## Tried and failed (do not repeat)

- pairs 8–12: inline `$06E3,Y` writes broke the order; `$FD80` second half; `$0524/$0525` wrong source.
- pair18: reload from `$0524/$0525` at `$AC09/$AC9F` **broke boot** (those clears also run on the boot path).
- pair19: guarded reload skipped — `$0524=0` at scene 05.
- pair20: `$0526=0` at scene 05. pair21: `$04EF/$04F0=0` at scene 05.
- Two delegated subagents produced **no changes**; canceled.

## Other blocked tasks

- **list-dispatch:** dump `$A0C6..$A286` (stride `$40`); trace `$047B` title menu; then `list-seed` (seed `$06E2` + 32 names).
- **password-decode:** 32-team `seed_order`/`advance` 6502 in bank5 → `$7700/$7720`; then `password-encode`.
- **hardware-audio:** needs the user's Mesen2/FCEUX/EverDrive/NES + audio + SRAM.

## First actions

```bash
git pull
python3 tools/backlog.py pick
# read the pitch-06e2 note, apply the capture/restore, soak, verify
# commit/push, update docs/AUTORUN-REPORT.md, backlog done/block
```

If the pitch passes, the queue flows: `pitch-odd`/`pitch-restructure`/`soak-26` → `bridge-integrate`, then list/password.

## Environment

```bash
# romdev server (per run; dies between turns)
npm_config_cache="$PWD/.npm-cache" npx -y romdevtools   # wait for "server up" on :7331
# breakpoints
python3 tools/romdev.py load build/direct31-pair17.nes
python3 tools/romdev.py tool breakpoint '{"on":"write","address":1168,"maxFrames":3000}'
# soak
timeout 300 python3 tools/soak_bracket.py --rom build/<rom> --matches 10 --winner score --mode speed
# stock regression
./tools/verify.sh --with-soak
```

`build/` is gitignored; never commit ROMs. `docs/build-manifest.json` pins `direct31` = `d043ecdfc46c4d50c509db30f757425759a556dec3258be462fa9b3d81091ec1`.
