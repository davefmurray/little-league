# Little League Baseball: Championship Series — A Complete Companion

*Everything we can document about SNK's 1990 NES baseball game: its Japanese
origin, how it plays, the sixteen teams and their hidden data, the cartridge
internals, and the small ROM-hacking scene around it. Compiled from community
documentation, wiki sources, and direct analysis of the US ROM. Sources are
listed at the end.*

---

## At a glance

| | |
|---|---|
| **US title** | Little League Baseball: Championship Series |
| **Japanese title** | Koushien (甲子園) |
| **Developer** | SNK |
| **Publishers** | SNK (US); K. Amusement Leasing (JP) |
| **Platform** | Nintendo Entertainment System / Famicom |
| **JP release** | October 6, 1989 |
| **US release** | July 1990 |
| **Genre** | Arcade baseball |
| **Modes** | Single-player tournament, 2-player exhibition, CPU-vs-CPU |
| **Players** | 1–2 (up to 2 on the field; tournament can rotate humans) |
| **Cartridge** | MMC1, 128 KiB PRG, 128 KiB CHR, no battery |
| **Save** | Password (US version only) |

The pitch is simple: SNK took its **Baseball Stars** engine, retuned it for the
shorter, faster Little League game, and dressed it in the Little League World
Series. The result is a game that plays quicker than most NES baseball titles and
has a reputation, in the small circle that still plays it, as one of the most
underrated sports games on the system.

---

## From Koshien to Williamsport

The game began life as **Koushien**, a Famicom baseball game about Japan's
national high-school tournament at Koshien Stadium. It was released in Japan on
October 6, 1989, with K. Amusement Leasing handling publishing and SNK
developing.

For North America, SNK did not simply translate it. According to The Cutting Room
Floor, **all of the game's graphics and cutscenes were modified** for the US
release. The team-select screen, the tournament bracket, the opening ceremony,
the home-run cutscene, the scoreboard, the game-over screen and the ending were
all redrawn or replaced. Even the method for deciding who bats first changed:
the Japanese version uses rock-paper-scissors, while the US version drops a bat
and has the players grab it.

The changes were not only cosmetic. The Japanese bracket is much larger, the
sandlot area of the field is bigger, and the US version adds a **password
system** so a tournament can be resumed. The US version also reframes the whole
competition as the Little League World Series, with sixteen national and
American teams instead of Japanese high schools.

One artefact survived the rewrite: an **unused sprite of Dugout**, the Little
League World Series mascot, who was meant to stand on the right side of the
title screen. He was replaced by an ordinary boy, likely for licensing reasons.
The unused graphic has "1989" beneath it, suggesting the US release was
originally planned for that year. The sprite's palettes and layout data are gone,
so any reconstruction of his colours is a guess (TCRF).

The result is a localization that is closer to a reskin than a port — a
Japanese high-school tournament game rebuilt around an American youth-baseball
institution, with the underlying Baseball Stars-derived engine left intact.

---

## Modes and structure

The US ROM's own text strings map the front end:

```
CHAMPIONSHIP SERIES     EXHIBITION MODE      POWER ANALYSIS
WATCH GAME              CONTINUE PLAY        LIST OF TEAMS
START NEW SERIES        SPEED MODE           PASS WORD
```

- **Championship Series** — the single-player mode. A mandatory sixteen-team,
  single-elimination tournament: first round, quarter-finals, semi-finals,
  final. Four wins take the title.
- **Exhibition Mode** — a single game between any two teams, for one or two
  players.
- **Watch Game** — CPU versus CPU, useful for scouting or for letting the game
  play itself.
- **Speed Mode** — a faster-playing variant for quick games.
- **Power Analysis** — the team-select screen's four-bar rating for every team.
- **Continue Play / Pass Word** — resume a tournament. The US version issues a
  password after each game, including games you let the CPU simulate. That
  simulation loophole is a known trick: if New York is next and you would rather
  not face them, simulate until you get a bracket you like.

### Tournament format

Sixteen teams, single elimination, four rounds. The bracket screens in the ROM
are labelled `ST ROUND`, `QUARTER FINALS`, `SEMI FINALS`, `FINALS`.

### Rules

- **Six innings**, plus extra innings if tied. (TCRF's misc section says seven;
  Wikipedia, StrategyWiki and NES Archives all say six. The weight of evidence
  is on six.)
- **Mercy rule**: ten runs.
- **No lead-offs**, as in real Little League.
- **Re-entry**: a player removed from the game can be put back in later, which
  mirrors the Little League substitution rule. NES Archives calls this out as a
  nice touch of authenticity.
- **No mandatory-play rule**: the real Little League requirement that every
  player bat and field for at least two innings is not enforced.
- **Fifteen-player rosters**, three pitcher types per team.

---

## On the field

The game is built for speed and hands-on control rather than simulation depth.

**Pitching.** Three pitch types: fastball, change-up and curve. The pitcher can
move around the mound. Stamina is consumed partly by how long the pitch is
charged, so working deep counts and long at-bats has a cost. Each team carries
three pitcher records with their own stamina and skill values; a fourth pitcher
on Pennsylvania is a data quirk that shares the third slot.

**Batting.** The batter can move around the box, swing for contact or power, or
bunt. Bunting is notably easy compared with Baseball Stars — NES Archives calls
it an improvement — and the squeeze play is viable. The batter's stance and
animation change with the situation; low-skill batters visibly look nervous, and
batters throw tantrums after crucial strikeouts.

**Baserunning.** Stealing is in. Speed is a real attribute; the community
identified it in the player record and it visibly affects baserunning.

**Fielding.** Fielders can jump and dive. The player can shift the defence and
call formations designed to stop bunts. Defensive positioning matters more than
in many NES baseball games because bunts are so effective.

**Substitutions.** The menu strings cover the full set: `PINCH HITTER`,
`PINCH RUNNER`, `PLAYER CHANGE`, `CHANGE FIELDER`, `CHANGE ORDERS`.

**Ratings.** Each player has a printed **SKILL** from 1 to 5, shown on the player
card and used for hitting and fielding. Each team also has four hand-authored
**POWER ANALYSIS** bars — batting, running, pitching, defence — rated 1 to 4.
These are not averages of the player data; they are their own table, and they
sometimes disagree with the underlying numbers (see below).

**Presentation touches.** The pitcher's hat flies off on a hard throw; players
dive and slide; the home-run and bat-throw cutscenes are elaborate for the era.
The crowd, field and animations are a clear step above the average 1990 NES
baseball game.

---

## The sixteen teams

The roster is exactly the Little League World Series field of the era: eight
American teams and eight international ones.

| # | Team | Region |
|---|---|---|
| 1 | JAPAN | International |
| 2 | ARIZONA | US |
| 3 | PENNSYLVANIA | US |
| 4 | CHINESE TAIPEI | International |
| 5 | KOREA | International |
| 6 | NEW YORK | US |
| 7 | CALIFORNIA | US |
| 8 | TEXAS | US |
| 9 | HAWAII | US |
| 10 | SPAIN | International |
| 11 | PUERTORICO | International |
| 12 | MEXICO | International |
| 13 | CANADA | International |
| 14 | ITALY | International |
| 15 | ILLINOIS | US |
| 16 | FLORIDA | US |

The mix reflects the LLWS of the late 1980s: Chinese Taipei was the dominant
international power of the period, Japan and Korea were regulars, and the
American entries are the big baseball states. Spain and Italy are the odd ones
out to modern eyes, but they represent the international regions of the era.

### Who is actually good?

The POWER ANALYSIS table, read straight from the ROM, ranks the teams like this
(sum of the four 1–4 bars):

| Rank | Team | Batting | Running | Pitching | Defense | Sum |
|---|---|---|---|---|---|---|
| 1 | NEW YORK | 3 | 4 | 4 | 4 | **15** |
| 2 | CANADA | 4 | 3 | 3 | 4 | **14** |
| 3 | TEXAS | 3 | 3 | 3 | 3 | 12 |
| 3 | CALIFORNIA | 2 | 3 | 4 | 3 | 12 |
| 3 | CHINESE TAIPEI | 3 | 2 | 4 | 3 | 12 |
| 6 | FLORIDA | 3 | 2 | 3 | 3 | 11 |
| 6 | SPAIN | 3 | 4 | 2 | 2 | 11 |
| 6 | KOREA | 2 | 3 | 3 | 3 | 11 |
| 6 | ARIZONA | 2 | 2 | 3 | 4 | 11 |
| 10 | HAWAII | 4 | 2 | 2 | 2 | 10 |
| 10 | MEXICO | 4 | 4 | 1 | 1 | 10 |
| 12 | JAPAN | 1 | 3 | 2 | 3 | 9 |
| 12 | PENNSYLVANIA | 2 | 3 | 2 | 2 | 9 |
| 14 | ILLINOIS | 2 | 2 | 2 | 2 | 8 |
| 14 | PUERTORICO | 1 | 2 | 2 | 3 | 8 |
| 16 | ITALY | 1 | 1 | 1 | 1 | **4** |

That matches the community memory: **New York is the team to beat**, and a
tournament run with Illinois or Italy is the hard mode. NES Archives' reviewer
specifically mentions never beating New York with Illinois.

Mexico is the interesting outlier: four bars in batting and running, one in
pitching and defence. It is a team built to outscore you, not to hold a lead.

### The hidden numbers disagree

Averaging the raw player records gives a different picture from the bars:

| Team | Mean SKILL | Mean byte 9 | Mean byte 10 |
|---|---|---|---|
| CANADA | 3.33 | 128.6 | 128.1 |
| NEW YORK | 3.27 | 98.1 | 170.7 |
| TEXAS | 3.27 | 120.1 | 142.3 |
| HAWAII | 3.20 | 104.9 | 65.8 |
| SPAIN | 2.87 | 99.3 | **175.4** |
| MEXICO | 2.87 | 119.4 | 149.7 |
| ITALY | 2.33 | 77.1 | 98.5 |

Spain has the highest mean byte 10 in the game and the third-highest byte 9, yet
only 11 bar-points and a 2–2 pitching/defence split. Canada has the highest mean
skill but is second on the bars. The POWER ANALYSIS screen is a designer's
summary, not a computed average — which is useful to know when tuning a hack:
changing player stats will not move the bars, and changing the bars will not
change the underlying players.

---

## The players

Every team has fifteen players in a 16-byte record. The name is six ASCII
characters, space padded, so longer names are truncated in ways that are now
part of the game's character: `SANCHE` (Sanchez), `STAURT` (Stuart), `YODOYA`
(Yodoyabashi), `ESSE` and `HOSE` on Puerto Rico.

### The Japan roster is an Osaka in-joke

Japan's fifteen names are not Japanese family names. They are Osaka place names
and train stations:

`UMEDA`, `NAKATU`, `MIKUNI`, `ESAKA`, `YODOYA`, `NANBA`, `TENOJI`, `NODA`,
`TENMA`, `HIRANO`, `NISHI`, `NAKA`, `SHIMA`, `MINAMI`, `KATA`

Umeda, Nakatsu, Mikuni, Esaka, Yodoyabashi, Namba, Tennoji, Noda, Tenma, Hirano,
Nishi, Naka, Shima, Minami and Kata are all Osaka-area locations, many of them on
the Midosuji subway line and the Osaka Loop Line. This is almost certainly a
leftover from **Koushien**: a Japanese team's roster built from the developers'
home city, carried into the US version when the team was renamed `JAPAN` but the
player names were left alone. It is the clearest fingerprint of the game's
Japanese origin in the US ROM.

### Body types and handedness

Byte 6 of each record encodes handedness and build. Across the 240 players:

- **140 right-handed, 100 left-handed**
- **95 tall, 56 heavy, 89 short**

The bit layout is documented by the community: bit 7 sets left-handedness, and
the low two bits select tall / heavy / short. This is why some batters look
visibly bigger than others at the plate.

### Pitchers

Each team has three pitcher records (Pennsylvania has a fourth player flagged to
the third slot). The pitcher record is eight bytes: arm angle, stamina, two
unknown values, two unused bytes, printed mound skill, and a final `00`/`02`
flag. The player's byte 12 selects which of the three records they use, and the
game reads that record's stamina byte directly when the player takes the mound.

That means a ROM hack can create a sidearm left-hander simply by editing the
pitcher record's first byte — a detail the community discovered years ago and
one of the more satisfying small hacks in the game.

---

## Presentation

**Graphics.** Large, expressive sprites; a full stadium view; animated crowd
reactions; cutscenes for home runs, strikeouts and the end of the tournament.
The Japanese version's cutscenes are entirely different, and the US version
redrew all of them. The unused Dugout mascot is the best-known piece of cut
content.

**Sound.** NES-era music and effects; NES Archives sums it up as "catchy at first
but annoying after awhile." No composer credit is documented in the sources
surveyed, and the ROM does not contain an obvious staff roll.

**Box and manual.** The cartridge is common; the box and manual are rated
"average" rarity and are harder to find than the game itself (Wikipedia, citing
Nintendo Age). The back of the box sells the fantasy directly: jump or dive for a
catch, full swing or bunt, shift fielders, pinch hit or run, choose fast, slow or
curve, steal, and "you might even try a squeeze play."

---

## Development and credits

SNK developed the game and published the US release. K. Amusement Leasing
published the Japanese version. The engine is a modified **Baseball Stars**
engine, adapted for the shorter little-league/high-school game — which explains
the shared field perspective, the dive/jump fielding, and the overall feel.

Specific staff credits are not documented in the sources available. MobyGames'
credits page is the usual reference, but it was not reachable during this
research; no staff roll is known from the ROM. This is one of the open questions
in the game's history.

---

## Release and reception

- **Japan:** October 6, 1989, as *Koushien*.
- **North America:** July 1990, as *Little League Baseball: Championship Series*.
- **Europe/PAL:** no release is documented in the sources surveyed.

Contemporary coverage is thin. The best-known modern appraisal is **Nintendojo's
95%** review, cited by Wikipedia via MobyGames, and **NES Archives**, which gave
it a **B** with a **B+** second opinion. NES Archives' review is worth quoting in
spirit: it calls the game "yet another gem of a baseball game from SNK," praises
the six-inning pace ("about as quickly as one inning in Bases Loaded"), the
playoff structure, the easy bunting, and the little presentation touches, while
knocking the lack of a dynasty mode and stat tracking. Its second reviewer
summed up the trade-off: great gameplay, but no real players and no stat
tracking.

The common comparison is to **Baseball Stars**, **RBI Baseball**, **Bad News
Baseball** and **Tecmo Super Bowl**. The consensus is that it is not Baseball
Stars — no team creation, no battery save, no stat tracking — but that it is a
faster, tighter, weirder game that rewards repeat play, especially in
multiplayer.

---

## Under the hood

### Cartridge

| | |
|---|---|
| Mapper | MMC1 (SxROM) |
| PRG | 128 KiB, 8 × 16 KiB |
| CHR | 128 KiB, 16 × 8 KiB (32 × 4 KiB banks) |
| PRG RAM | none declared |
| Header mirroring | horizontal |
| Runtime mirroring | vertical (control `$1E`), toggled to horizontal (`$1F`) later |
| Battery | no |

The iNES header says horizontal mirroring, but the boot code writes **`$1E`** to
the MMC1 control register at `$CBE3`: vertical mirroring, PRG mode 3 (last bank
fixed at `$C000`), CHR mode 4 KiB. Later screens switch to `$1F` (horizontal)
at `$99B1` and back to `$1E` at `$9AF5`. Anyone testing a hack on hardware should
remember that the header is not the whole story.

### Memory map and entry points

| | |
|---|---|
| NMI | `$CD85` |
| RESET | `$CBD5` |
| IRQ/BRK | `$CDF4` (bare `RTI`) |
| Fixed PRG bank | bank 7 at `$C000` |
| Switchable window | banks 0–6 at `$8000` |

MMC1 register writers all live in the fixed bank:

| Routine | Store | Register |
|---|---|---|
| `$C102` | `$9FFF` | control |
| `$C11C` | `$BFFF` | CHR bank 0 |
| `$C134` | `$DFFF` | CHR bank 1 |
| `$C150` | `$FFFF` | PRG bank |

PRG banking is frequent — around a hundred `$C150` call sites in the fixed bank
alone. CHR banks are staged in zero page (`$23` for CHR0, `$25` for CHR1) and
applied during NMI by `$CE45`.

### Text and graphics

Team names, menu strings and the intro poem are stored as plain ASCII in PRG.
That is unusual for the era and makes text editing trivial: the game converts
ASCII to tile indices at draw time. The intro poem — "FROM THE RANKS OF
YOUNGSTERS…" — sits at bank 5, `$B10C`. Team names are at `$9180`, and the
scoreboard abbreviations use a pointer table with variable-length, `FF`-terminated
entries.

CHR is uncompressed 2bpp. All 32 four-kilobyte banks are unique; several are
mostly blank (bank 18 is 82% `$00`), suggesting per-scene UI tilesets. The
lowest-`$FF` banks are 28–31, the best candidates for the detailed field and
portrait graphics.

---

## The data tables

A full map lives in [`roster-format.md`](roster-format.md). The short version:

| Data | File offset | Layout |
|---|---|---|
| Player records | `0x10430` | 16 teams × 15 players × 16 bytes |
| Pitcher records | team base + `$F0` | 3 × 8 bytes, after a 24-byte header |
| Lineups | `0x116DA` | 16 × 9 bytes (order/position nibbles) |
| Team flags | `0x1176A` | 16 tile IDs, `$48` = USA |
| Team ratings | `0xF234` | 16 × 4 bytes, values 1–4 |
| Long names | `0x5190` | 16 × 16 bytes |
| Short-name pointers | `0x5290`, `0x52A0` | 8 + 8 words |
| Team colours | `0x1FAD0` | 16 × 3 bytes (cap and trim, jersey, hair) |

Two things surprised us during the analysis:

1. **The pitcher records are not player records.** Byte 12 of a player is a
   pitcher-slot selector, not an appearance index. It points at one of three
   eight-byte records in the 48-byte trailer after slot 14, and the game reads
   that record's stamina byte when the player pitches.
2. **The POWER ANALYSIS bars are independent data.** They are not computed from
   the player records, which is why a team like Spain can have the best raw
   speed byte in the game and still show only two running bars.

A third open question is byte 9. The community reads it as a single hitting-power
byte; the code splits it into two nibbles and uses them separately for the
batting and pitching checks. The editor exposes them as separate BATTING and
PITCHING values, with the caveat documented in `roster-format.md`.

---

## The ROM-hacking story

For a game with a cult following, there is remarkably little published hacking
work. Data Crystal's page (as of its 2024/2025 snapshots) lists **no utilities,
no hacks and no translations**. The main public document is a 2017 TecmoBowl.org
forum post by **davidjoshualightman**, who had been poking at the ROM since 2007.
That post is the source for much of the community's knowledge:

- the 16-team order and the `0x10430` roster base
- the 16-byte player record and its fields
- the pitcher records in the trailer
- the lineup table at `0x116DA`, the flags at `0x1176A`, and the colour tables
- the RAM addresses for pitcher value and stamina (`$04F9`–`$04FE`)

The post is also candid about what was still unknown: defensive ability, the
meaning of the pitcher record's third and fourth bytes, team locations on the
map, and colour/text changes.

This project picks up from there. It provides:

- a documented, byte-exact map of the roster and team tables
- `tools/roster.py`, an extract/apply roster editor with a byte-identical
  round trip
- `tools/rominfo.py` and `tools/trace.py` for cartridge and code analysis
- a browser editor (`web/`) for editing teams visually and exporting a patched
  ROM
- this write-up

The biggest unsolved problems are the exact gameplay semantics of byte 9, the
pitcher record's unknown bytes, and the palette tables. All three are tractable
with controlled emulator tests: patch one byte, play one game, record the
difference.

---

## Playing and preserving it

The cartridge is common and inexpensive; the box and manual are the scarce parts.
For research, the US ROM is the reference (MD5
`cd724fd557d323ce7fefe8a82ddf8337`). The Japanese *Koushien* is a separate ROM
and a separate experience: different teams, different cutscenes, a bigger
bracket, no password system, and rock-paper-scissors to decide the first bat.

If you want to see the difference for yourself, the TCRF page has side-by-side
screenshots of the title screen, attract mode, menu, bracket, opening ceremony,
first-batter ritual, sandlot, home run, scoreboard, game over and ending.

---

## Sources

- [TecmoBowl.org — "Little League Baseball for NES"](https://tecmobowl.org/forums/topic/69604-little-league-baseball-for-nes/) — davidjoshualightman's 2017 ROM-hacking notes, the core community document.
- [Data Crystal — Little League Baseball: Championship Series](https://datacrystal.tcrf.net/wiki/Little_League_Baseball:_Championship_Series) — cartridge facts, sub-pages, known dumps; page lists no hacks or utilities.
- [The Cutting Room Floor — Little League Baseball: Championship Series](https://tcrf.net/Little_League_Baseball:_Championship_Series) — unused Dugout mascot, full regional-difference comparison with Koushien.
- [Wikipedia — Little League Baseball: Championship Series](https://en.wikipedia.org/wiki/Little_League_Baseball:_Championship_Series) — release, modes, rules, ratings, reception.
- [StrategyWiki — Koushien / Little League Baseball](https://strategywiki.org/wiki/Koushien) — Japanese origin, publisher, relationship to Koushien and Baseball Stars.
- [LaunchBox Games Database — entry 8177](https://gamesdb.launchbox-app.com/games/details/8177) — box copy, release date, alternate names, engine note.
- [NES Archives review (archived)](https://web.archive.org/web/20080503192431/http://www.nesarchives.com/Littleleague.html) — contemporary-style review, B / B+, gameplay details.
- MobyGames — [game page](https://www.mobygames.com/game/nes/little-league-baseball-championship-series) (referenced via Wikipedia; not directly reachable during this research).
- Direct analysis of the US ROM for all table addresses, team ratings, roster statistics and code references.

*Screenshots and box art belong to their respective rights holders. This
document is a technical and historical reference for preservation and
ROM-hacking purposes.*
