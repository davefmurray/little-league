# Little League Baseball: Championship Series — ROM Lab

A preservation-minded hacking toolkit for SNK's 1990 NES baseball game: a
zero-dependency **browser roster editor**, a **byte-exact data map**, command-line
tools with a verified round trip, and a long-form **[history and technical
companion](docs/game-writeup.md)**.

<p align="center">
  <img src="https://github.com/davefmurray/little-league/releases/download/32-team-preview-8/home-run.png" alt="HOME RUN ballpark celebration" width="512">
</p>
<p align="center">
  <img src="docs/editor.png" alt="Roster Lab editing the Japan roster" width="900">
</p>

<p align="center">
  <a href="https://little-league-production.up.railway.app"><strong>Live editor</strong></a> ·
  <a href="docs/game-writeup.md"><strong>Read the write-up</strong></a> ·
  <a href="docs/roster-format.md"><strong>Roster format</strong></a> ·
  <a href="TODO.md"><strong>Living TODO</strong></a> ·
  <a href="docs/rom-layout.md"><strong>ROM layout</strong></a>
</p>

---

## The game

*Little League Baseball: Championship Series* is SNK's 1990 NES localization of
**Koushien** (甲子園), a 1989 Famicom game about Japan's national high-school
tournament. SNK rebuilt the graphics, cutscenes, menus, bracket and endings around
the Little League World Series, kept the **Baseball Stars**-derived engine, and
shipped one of the faster, stranger baseball games on the system.

Sixteen teams. Six innings. Ten-run mercy rule. No lead-offs, but you can pull a
player and put him back in. Three pitcher types per team, fifteen-player rosters,
a 1–5 skill rating on every card, and four hand-authored power-analysis bars per
team. It is not a simulation — there are no stat lines, no season mode, no team
creation — but the moment-to-moment baseball is quick, expressive and unusually
physical: dives, jumps, bunts, squeeze plays, hat-flying fastballs and batters who
throw tantrums.

The full story — Koshien, the localization, the unused Dugout mascot, the Osaka
in-joke hidden in Japan's roster, the data tables and the small hacking scene —
is in **[docs/game-writeup.md](docs/game-writeup.md)**.

---

## What's here

| | |
|---|---|
| **Browser editor** | Edit the 32-team Preview 8 rosters or the original 16 teams: player names, skill, stats and team ratings; export an edited ROM or JSON. No build step, no dependencies. |
| **CLI roster tool** | `tools/roster.py` — `show`, `extract`, `apply`, `patch`; extract → apply is byte-identical on an untouched ROM. |
| **Data map** | Every roster, lineup, pitcher, name, flag and rating table, with CPU and file offsets. |
| **ROM analysis** | `tools/rominfo.py` (banks, CRCs, vectors, strings) and `tools/trace.py` (6502 trace from RESET). |
| **History** | A sourced, long-form write-up of the game, its Japanese origin and its technical structure. |
| **Hosting** | Dockerfile + `railway.json`; the editor runs as a small Python server on Railway. |

---

## 32-team edition

[Download the current ROM](https://github.com/davefmurray/little-league/releases/download/32-team-preview-8/little-league-32-team.nes)
or open the [release and screenshots](https://github.com/davefmurray/little-league/releases/tag/32-team-preview-8).

- **Random tournaments:** choose any of 32 teams. Your team plays first; the
  other teams are shuffled once. Passwords save the draw and progress.
- **One team picker:** the flag grid serves Championship, Exhibition
  (1P, 2P and WATCH) and Power Analysis. In 2P, controller 2 chooses the opponent.
- **New title and menus:** NES pixel art, a full bracket tree, and stock menu
  music. The sunny ballpark mode menu reuses the original intro characters
  and crowd. The title retains its original music and attract sequence.
- **New scoreboard:** cream and gold score panels, a sunny ballpark crowd,
  original game characters, and the original score/stat rules, including extra innings.
- **Power Analysis:** a matching team card with four labeled ratings, animated
  baseball markers and original game characters. All 32 teams are supported.
- **HOME RUN:** a matching ballpark celebration with original characters. The
  pair and batter stay still while the cheerleader, crowd and marquee animate.
  Scoring, music and cutscene timing retain their original code.
- **Resume:** existing 32-team v1 passwords still work. Random tournaments use
  v2 codes; original 16-team game passwords are not supported.
- **Gameplay:** completed-game results, high-team names, pitchers and roster
  caches are covered by CPU tests and emulator tournament runs.

<p align="center">
  <img src="https://github.com/davefmurray/little-league/releases/download/32-team-preview-6/scoreboard.png" alt="New ballpark scoreboard" width="512">
</p>
<p align="center">
  <img src="https://github.com/davefmurray/little-league/releases/download/32-team-preview-6/mode-menu.png" alt="Sunny ballpark mode menu with original game characters" width="512">
</p>
<p align="center">
  <img src="docs/verification/frontend32/exhibition-2p/exhibition-1-second-pick.png" alt="Shared 32-team Exhibition picker" width="512">
</p>

The final build is `build/homerunart32.nes`. It passes the baseline six-game
and random 31-match emulator gates. A played three-run homer and planted
grand-slam and walk-off cases match the previous ROM in scoring, pitcher
statistics, timing and digital audio. Shared ending graphics remain intact.
Earlier stages separately cover all 32 Analysis cards, a resumed game after
Analysis, WATCH and 2P completion, and 1P setup. Full 1P completion was tested
on title32. SPEED soaks force CPU ownership; controller probes do not.
See [HOME RUN evidence and limits](docs/homerunart32.md).

Physical hardware and a second emulator implementation remain unvalidated.
High-team uniforms reuse stock presets, gameplay flags are omitted, and the
small selector flags are simplified. The source pipeline still needs the
existing `direct20-names.nes` bootstrap artifact.

See [status and build commands](docs/32-team-status.md),
[random draws and passwords](docs/draw32.md), [picker controls](docs/pick32.md),
[title artwork](docs/title32.md), and [menu art/music](docs/menuart32.md).
The hosted editor opens on the Preview 8 roster. Download the ROM above, then
open it in the editor to export an edited copy; see the
[editor contract](docs/editor32.md).

---

## Browser editor

**Hosted:** <https://little-league-production.up.railway.app>. The page opens on
the Preview 8 roster. **Get Preview 8** downloads the ROM from the release;
**Open ROM** then reads it in the browser. Nothing is uploaded, and the site
never serves a ROM.

```sh
python3 tools/serve.py
# http://127.0.0.1:8080
```

Open a `.nes` file or drop it anywhere on the page. Pick a team, edit, then
**Export ROM** to download an edited copy. **Data → Export JSON** saves a
roster you can import later, and the Data menu switches to the original
16-team roster.

- **ROMs** — the 32-team Preview 8 release and the original US ROM, plus copies
  this editor exported. Other files are refused.
- **Players** — 6-character names, SKILL 1–5, batting and pitching (0–15
  each) and speed (0–15) for players 1–15 on every team.
- **Teams** — four 1–4 Power Analysis ratings. On the 16-team ROM the team and
  scoreboard names are editable within their stored widths. Preview 8 names,
  codes and regions are read-only because the menus and bracket art use them.
- **Stored records** — Preview 8 teams 17–32 store 20 players, but the game
  loads 15, so players 16–20 are shown read-only.
- **Pitchers** are marked with a red `P`; the three pitcher records per team are
  not edited.
- **Safety** — export writes only the fields you changed and reopens the copy
  to check it. Opening another file asks before replacing unsaved edits.

The editor reads and writes the ROM **in the browser**. The server only serves
`web/` (and, on loopback only, `/rom` for local tools; the editor does not use
it). [docs/editor32.md](docs/editor32.md) has the full contract.

Tests: `node --test tools/test_web_rom.mjs tools/test_web_app.mjs` runs on
synthetic ROM images. Set `ROSTER_ROM32` and `ROSTER_ROM16` to add the
real-ROM cases, and run `tools/test_web32_runtime.py` for the CPU checks on an
exported Preview 8 copy.

---

## CLI

```sh
# inspect the cartridge
python3 tools/rominfo.py "Little League Baseball - Championship Series (USA).nes"

# print all 16 rosters
python3 tools/roster.py show ROM

# extract to JSON, edit, rebuild
python3 tools/roster.py extract ROM -o data/roster.json
python3 tools/roster.py apply   ROM data/roster.json -o build/hack.nes

# one-off player edit
python3 tools/roster.py patch ROM --team 2 --slot 14 --name DAVE --skill 5 -o build/demo.nes

# cartridge layout / PRG expansion
python3 tools/expand_rom.py ROM --inspect
python3 tools/expand_rom.py ROM -o build/expanded.nes --prg-banks 16

# 6502 trace from RESET (needs the py65 venv)
python3 -m venv .venv && .venv/bin/pip install py65
.venv/bin/python tools/trace.py ROM 600
```

The base ROM is not included. The reference dump has MD5
`cd724fd557d323ce7fefe8a82ddf8337`; the tools check the iNES header and refuse
trainer ROMs, and the editor refuses files other than the two supported ROMs.

---

## ROM test harness

A browser-based jsnes harness lives at `tools/harness.html` so patches can be
boot-tested without installing an emulator:

```sh
python3 -m http.server 8097 --bind 127.0.0.1
# http://127.0.0.1:8097/tools/harness.html
# http://127.0.0.1:8097/tools/harness.html?rom=../build/16x20.nes
```

ROM-specific debugger:

```sh
# http://127.0.0.1:8097/tools/debugger.html?rom=../build/select-flags.nes
```

Shows CPU registers, named zero-page watches (`$07C0` page, `$07C1` cursor,
`$07C3` selected, `$06`, `$32`, display list), OAM, and a write log with the PC
that performed each write to the watched addresses.

Buttons and a console API (`stepFrames`, `tap`, `press`) drive the game. jsnes
uses a different NTSC palette than the console, so colours are approximate —
use it for layout, menus and crashes, not palette verification.

## Data model at a glance

| Table | File offset | Layout |
|---|---|---|
| Player records | `0x10430` | 16 teams × 15 players × 16 bytes |
| Pitcher records | team base + `$F0` | 3 × 8 bytes after a 24-byte header |
| Lineups | `0x116DA` | 16 × 9 bytes (batting order / position nibbles) |
| Team flags | `0x1176A` | 16 tile IDs |
| Team ratings | `0xF234` | 16 × 4 bars, values 1–4 |
| Team names | `0x5190` | 16 × (14 chars + `FF FF`) |
| Scoreboard names | `0x5290`, `0x52A0` | two 8-entry pointer tables |
| Team colours | `0x1FAD0`, `0x1FAE0` | 16 bytes each |

A player record is `name[6]` + ten attribute bytes. SKILL is byte 11; byte 12
selects one of the team's three pitcher records. The POWER ANALYSIS bars are
independent data, not averages of the roster — which is why Spain can have the
best raw speed value in the game and still show two bars.

The unresolved question is byte 9: the community reads it as one power byte, the
code splits it into two nibbles used separately by the batting and pitching
checks. The editor exposes the nibbles and documents the conflict in
**[docs/roster-format.md](docs/roster-format.md)**.

---

## Project layout

```
web/                  browser editor (no build step)
  index.html          layout
  styles.css          scoreboard/field styling, responsive
  rom.js              iNES parser + patcher (DOM-free, Node-testable)
  app.js              state, rendering, import/export
  roster.json         preview data
tools/
  roster.py           CLI extract/apply/patch
  expand_rom.py       PRG expansion with fixed-bank relocation
  build_16x20.py      first roster-expansion build (16 teams x 20 players)
  build_32x20.py      32-team bank-8 data + PRG-RAM cache
  pack_team_table.py  packs codes/names/regions into bank 9
  build_select_screen.py  bootable static 4x8 select screen
  extract_chr.py      every CHR tile -> per-bank PNGs, atlas, manifest
  extract_flags.py    per-team flag/label sprite blocks + sheet
  pack_flags.py       prototype: pack 24x24 flags into CHR bank 0
  build_flags32.py    generate/pack 32 flags at 24x16 into bank 10
  harness.html        jsnes browser test harness
  debugger.html       ROM debugger: regs, watches, OAM, write log
  tbl.py              text encode/decode/scan
  write_flags.py      swap/repoint team flag records
  import_flag.py      import a 24x24 PNG as a team flag
  bracket.py          decode/print bracket; generate 32-team table
  build_32bracket.py  install 31-record table and repoint readers
  build_dispatcher.py M1 $07C3 scene dispatcher (selector/bank11)
  build_bank11.py     M3 bank11 init/advance logic + 31-record table
  build_bracket_screen.py M4 static 32-team bracket screen
  build_bracket_input.py  M4 cursor + A handoff
  rominfo.py          cartridge report
  trace.py            6502 trace
  serve.py            local + Railway server
docs/
  game-writeup.md     the long-form history / technical companion
  roster-format.md    data tables and field map
  prior-art-llbcs.md  external editor findings + verified corrections
  datacrystal-rom-map.md  authoritative ROM map, reconciled
  ram-map.md          verified RAM addresses (pitcher, game state, buffers)
  text-table.md       TBL mapping + verified text offsets
  koushien-bracket.md 32-team Japanese bracket reference
  bracket.md          bracket format, 32-team table, RAM blocker
  PLAN-32-TEAM.md     adopted architecture and milestones (bank 11 scene)
  cheats-and-ram.md   Game Genie codes translated + RAM address map
  rom-layout.md       cartridge, banks, MMC1, vectors
  expanding-teams-and-rosters.md
                      dependency map and phased plan for 32 teams / 20 players
  editor.png          screenshot
Dockerfile            hosting image
railway.json          Railway build/deploy config
```

---

## Hosting

The editor is a static app plus a tiny Python server, so it runs anywhere:

```sh
docker build -t little-league .
docker run --rm -p 8080:8080 little-league
```

On Railway:

```sh
railway up --service little-league
```

`railway.json` uses the Dockerfile and `/healthz`; the server binds `0.0.0.0` and
reads `$PORT`. Off loopback, `/rom` is disabled — the hosted site is a viewer and
editor for **your** ROM, not a distribution channel for the game.

### Automatic deploys

The Railway service is connected to this GitHub repository, so **every push to
`main` builds the image and deploys automatically** — no tokens or secrets
involved. Railway checks out the commit and builds the `Dockerfile`.

[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) is kept as a
manual fallback (**Run workflow** only). It needs a Railway project token and is
skipped with a warning when the secret is absent:

```sh
gh secret set RAILWAY_TOKEN --repo davefmurray/little-league
```

You can also deploy from a checkout without Actions:

```sh
railway up --service little-league
```

---

## Status

| Area | State |
|---|---|
| Cartridge / mapper / bank analysis | done |
| Roster, lineup, pitcher, flag, rating tables | done |
| Team names + scoreboard names | done |
| Player record fields | names, skill, pitcher slot confirmed; byte 9 semantics open |
| CLI editor | done, byte-identical round trip |
| Browser editor | done, tested at desktop and phone widths |
| Hosted build | Railway config ready |
| Actual custom roster | not started — that's the fun part |

Open problems worth solving next: control the pitcher record's unknown bytes,
map the palette tables, and settle byte 9 with a controlled emulator test.

---

## Legal

No ROM or game code is included in this repository. The tools operate on a ROM
you supply. The site includes the game's title-screen screenshot and box art for
identification and commentary, with credit; all rights remain with SNK and Little
League Baseball, Inc. *Little League Baseball* is a trademark of Little League
Baseball, Inc. This is an unofficial preservation and research project.

---

## Sources and credit

The write-up cites the [TecmoBowl.org hacking thread](https://tecmobowl.org/forums/topic/69604-little-league-baseball-for-nes/),
[Data Crystal](https://datacrystal.tcrf.net/wiki/Little_League_Baseball:_Championship_Series),
[The Cutting Room Floor](https://tcrf.net/Little_League_Baseball:_Championship_Series),
[Wikipedia](https://en.wikipedia.org/wiki/Little_League_Baseball:_Championship_Series),
[StrategyWiki](https://strategywiki.org/wiki/Koushien),
[LaunchBox](https://gamesdb.launchbox-app.com/games/details/8177) and the
[archived NES Archives review](https://web.archive.org/web/20080503192431/http://www.nesarchives.com/Littleleague.html).
The table addresses and team statistics were derived directly from the US ROM.

## Hardware & sound

See [docs/hardware-sound.md](docs/hardware-sound.md) for the MMC1/bank map, emulator/hardware test matrix, APU audio path and release checklist.
