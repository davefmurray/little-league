# 32-team passwords: v1 and v2

New random series use [v2](draw32.md#frozen-draw-and-password-contract),
which also saves a 14-bit draw seed. Existing v1 codes retain their original
order and encode byte for byte. The v1 layout below remains supported. Both
versions use the same keyboard, alphabet, whitening and CRC.

A password restores the selected seed, completed matches, winners and all
32 CPU ownership bits. It uses the existing 22-symbol input and display
screens. The 32-team championship rejects stock 16-team passwords.
Exhibition mode does not use this codec.

The alphabet is `1AKV5EPR2BLW6FGS3CMX78HT4DNY09JU`. Each symbol carries
five bits. The input grid also accepts I as 1, O as 0, Q as 9 and Z as 2.
The host CLI accepts spaces and lowercase; the ROM keyboard emits uppercase.

## Payload

The canonical payload is 14 bytes. Results and ownership are little-endian;
the CRC and the complete symbol stream are big-endian.

| Bytes | Value |
|---|---|
| 0 | `08`, version 1 with reserved bits zero |
| 1 | Seed team, 0 through 31 |
| 2 | Completed matches, 0 through 31 |
| 3–6 | Result bits; bit m is 1 if the second team wins match m |
| 7–10 | CPU mask; bit t is 1 if team t is CPU-controlled |
| 11 | Reserved zero |
| 12–13 | CRC-16/CCITT-FALSE over bytes 0 through 11 |

The CRC uses polynomial `1021`, initial value `FFFF`, no reflection and no
final XOR. Its check value for `123456789` is `29B1`. Result bits at or
beyond the completed-match count must be zero, including bit 31. All
reserved bits are validated even when the CRC is correct.

Before symbol encoding, XOR the payload with
`2181c9f0dc5ffb2996b1d38cd0aa`. The first two bits are implicitly zero;
the remaining 110 bits become 22 consecutive five-bit symbols, most
significant first. This fixed whitening mask changes appearance only.
The checksum detects mistakes; it is not authentication.

The display groups symbols as 6+6 on the first row and 6+4 on the second.
For seed 15, zero completed matches, no results and CPU mask `FFFFFFDF`,
the password is `749MS3YCSUT9XBB4H245S6`.

## Bracket reconstruction

The first 32 heap entries are the seed team followed by all other teams
in ascending order. Match m reads slots 2m and 2m+1 and writes its winner
to slot 32+m. Slot 62 is the champion. Unplayed winner slots contain FF.
The decoder validates first; restore then runs the ROM's `$8200` seeder
and replays the completed results. Bracket redraw never seeds again.

The runtime ownership bytes are `$074B`, `$074C`, `$07F1`, `$07F2`.
`$07FC` holds matches completed. `$07EF=32` identifies this format only
when the active-series byte `$07ED` is nonzero. `$07F0` is transient list
view state and is cleared on restore and new-series creation.

## Source and commands

`tools/password32.py` is the host model. `tools/password32_6502.py` exports
the assembled codec and restore segments. `tools/build_passwordrom32.py`
installs the hooks on the guarded control32 input.

```sh
python3 tools/password32.py test --rounds 100
python3 tools/password32.py encode --seed 15 --played 0 --results 0 --cpu-mask 0xFFFFFFDF
python3 tools/password32.py decode 749MS3YCSUT9XBB4H245S6
.venv/bin/python tools/test_password32.py build/results32.nes
```

The stock codec remains byte-identical at bank 5 `$A036` (encode) and
bank 1 `$A8A2` (decode). The former documentation confused series seeding
at `$98D5` and result unpacking at `$9B5F` with the password codec, and
miscounted the screen as 11 or 16 symbols. Those models are superseded.

Independent review approves the host codec, bank-12 codec and bank-11
restore. The reproducible suite runs 2,050 CPU decodes, 160 encodes and
1,056 restores, alongside host corruption tests and stock codec parity.
[CPU evidence](verification/password32-codec-cpu.txt).
ROM hook and runtime acceptance are recorded in [password32.md](password32.md),
including the CONTINUE hook at bank1 `$94F8` and its `$BE40-$BE64` helper.
