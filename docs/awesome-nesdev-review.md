# AWESOME-NESDEV review (Fable 5.1)

Source: <https://github.com/davefmurray/AWESOME-NESDEV> (CC0).
Reviewed against our 32-team MMC1 hack and current blockers.

## Verdict

Useful, but narrowly. One entry directly fills our biggest gap; most of the rest
is homebrew or Windows-only agent tooling we should skip.

## Useful now, ranked

1. **romdev** (`npx romdevtools`, Node 24+) — write/exec breakpoints, computed
   jump tables, range/PC/copy watches, mapper-aware disassembly. Runs a libretro
   fceumm core with correct MMC1. This is the runtime inspector we lack; jsnes
   has no breakpoints and py65 has no mapper/PPU.
2. **retrodisasm + CDL** — code/data separation and `-verify` reassembly.
   Prefer building from `retroenv/retrodisasm`; the bundled blob has no license.
3. **`tools/addr.py` + `tools/nes_header.py`** — the address helper refuses
   banked conversions without an explicit bank, which is the discipline our
   bank-11 work needs.
4. **Cold-ROM playbook, “banked caveat”** — every observed address must carry the
   live bank and frame; keep a `labels.csv`.
5. **mcp-bizhawk** — fallback only, Wine on macOS.

## Traps for us

- Mesen MCP: Windows x64 prebuilt.
- MesenCE + `mesence`: zero-star fork, unverified on macOS.
- mcp-nes: no memory access.
- Nes.Mcp: .NET 10, no watchpoints.
- re-skill: autonomous multi-session loop, overkill.
- sadnescity/romhacking: translation workflow.
- GhidraMCP: no iNES loader/mapper awareness.
- NesBlockFinder: Python 2, generated screens won’t match.

## macOS verdict

Adopt romdev for **inspection**, keep our Python builders + py65 for data/logic.
Do not move the build to romdev.

## Highest-leverage next step

Load the expanded ROM in romdev, savestate on the bracket screen, set **write
breakpoints on `$04EF`/`$04F0`**, then set an exec breakpoint where the stock
team-select path writes them. Diff the two paths.

Acceptance: pressing A from the bracket launches a game between the two teams,
and 300 frames match a stock team-select launch for the same pair
(`regression({op:'capture'})` vs `check`).

## Banked-address discipline

- Only `$C000–$FFFF` is fixed on MMC1. Any `$8xxx` note without a bank is
  unreproducible.
- Treat displayed values as possible mirrors; write breakpoints find the owner.
- Capture CDL per mode (team select, bracket, game start).

## Adopted here

- `romdev` v0.150.2 skill saved at `.claude/skills/romdev/SKILL.md` (generated
  from the running server).
- npm needed a workspace cache: `npm_config_cache=$PWD/.npm-cache`.
