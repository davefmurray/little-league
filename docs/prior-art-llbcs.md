# Prior art: llbcs.py roster editor — verified findings

Source: <https://github.com/bblgamified/llb-cs_rostereditor/blob/main/llbcs.py>

This external PySide6 editor edits one team at a time using **absolute file
offsets** rather than a uniform stride. Checking those offsets against our ROM
confirmed several corrections to `docs/roster-format.md`.

## Team roster bases are NOT uniform

Names at each base were verified in our ROM. Only teams 0–8 are `0x120` apart.

| # | Team | File offset | CPU (bank 4) | Gap | First name |
|---|---|---|---|---|---|
| 0 | Japan | `0x10430` | `$8420` | — | UMEDA |
| 1 | Arizona | `0x10550` | `$8540` | `+0x120` | BERT |
| 2 | Pennsylvania | `0x10670` | `$8660` | `+0x120` | LEE |
| 3 | Chinese Taipei | `0x10790` | `$8780` | `+0x120` | LU |
| 4 | Korea | `0x108B0` | `$88A0` | `+0x120` | LEE |
| 5 | New York | `0x109D0` | `$89C0` | `+0x120` | TOMMY |
| 6 | California | `0x10AF0` | `$8AE0` | `+0x120` | BIFF |
| 7 | Texas | `0x10C10` | `$8C00` | `+0x120` | AUSTIN |
| 8 | Hawaii | `0x10D30` | `$8D20` | `+0x120` | THOMAS |
| 9 | Spain | `0x10E50` | `$8E40` | `+0x120` | ENRICO |
| 10 | Puerto Rico | `0x10F50`* | `$8F40`* | `+0x100` | **zeros** |
| 11 | Mexico | `0x11090` | `$9080` | `+0x140` | JUAN |
| 12 | Canada | `0x111B0` | `$91A0` | `+0x120` | CHUCK |
| 13 | Italy | `0x112D0` | `$92C0` | `+0x120` | LOGI |
| 14 | Illinois | `0x113F0` | `$93E0` | `+0x120` | CONRAD |
| 15 | Florida | `0x11510` | `$9500` | `+0x120` | DON |

\* Puerto Rico's listed base is **16 zero bytes followed by a pitcher-like
record**; the first player name `EMILLO` starts at `0x10F70` (`$8F60`). The
editor's PR base appears to be 0x20 early, or the block has a 0x20 prefix.

**Implication:** any tool using `base = 0x8420 + team*0x120` is correct for teams
0–9 and **wrong for 10–15**. `tools/roster.py` and `tools/build_16x20.py` both do
this and need a base table.

## Player row fields (external map)

After the 6-byte name:

| Byte | llbcs.py meaning | Our old doc |
|---|---|---|
| 6 | hand/size (`00` R tall, `01` R fat, `02` R short, `80` L tall, `81` L fat, `82` L short) | name padding |
| 7 | buffer `FF` | |
| 8 | unknown | |
| 9 | ARM power (llbcs) | power per DataCrystal |
| 10 | RUN speed (llbcs) | speed per DataCrystal |
| 11 | HIT (llbcs) | printed Skill per DataCrystal |
| 12 | pitcher profile (`00`, `08`, `10`, `18`) | pitcher slot |
| 13 | buffer | |
| 14 | team constant/scaler, often `02` | |
| 15 | buffer | |

**Conflict:** our ROM's UMEDA row has byte9 `D4`, byte10 `C9`, byte11 `04`.
Read as raw ARM/RUN those are 212/201 — implausible. Our nibble-packed reading may
be right, or the bytes are scaled. Resolve by editing one byte and checking the
in-game player card; do **not** change the tools until then.

## Pitcher profiles

Matches our trailer model:

- All-`FF` padding row ends the player rows.
- Profile #1 = bytes 8..15 of the first 16-byte row after the FF row.
- Profiles #2/#3 = bytes 0..7 and 8..15 of the second row.
- Byte 0 bit 7 = left hand; low nibble delivery; byte 1 stamina; byte 2
  quality/movement; byte 3 tune; byte 6 displayed pitch skill; byte 7 mult.

## Team colours: llbcs.py's 3-byte model is WRONG

DataCrystal and the ROM show **two 16-byte tables** at `0x1FAD0` and `0x1FAE0`
(primary and secondary per team). The 3-byte grouping below mixes one team's
secondary into the next team's primary; it is retained only as a record of the
external tool's assumption.

At file **`0x1FAD0`** (CPU `$FAC0`), 16 entries × **3 bytes** = 48 bytes through
`$FAEF`. The old docs treated `$FAC0` and `$FAD0` as separate 16-byte tables;
`$FAD0` is simply the middle of the same table (team 5 onward).

```
05 20 0F   Japan
26 20 38   Arizona
02 22 38   Pennsylvania
1B 2B 0F   Chinese Taipei
12 20 0F   Korea
15 11 38   New York
...
```

## Lineups

File `0x116DA` (CPU `$96CA`), 9 bytes per team, contiguous. Matches our docs.

## Action items

- [ ] Replace uniform `team*0x120` with the verified base table in `roster.py`,
      `build_16x20.py`, and any editor offsets.
- [ ] Resolve Puerto Rico's true base (`0x10F50` vs `0x10F70`).
- [ ] Test byte 9/10 semantics in-game before changing the field map.
- [ ] Fix the colour model to 16 × 3 bytes at `$FAC0`.
