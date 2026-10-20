# TODO — active backlog (post-25-task goal)

This is the clean, prioritized list of what is **actually still open** after the
25-task goal closeout. The long historical list is in `TODO.md`; the evidence
log is in `docs/AUTORUN-REPORT.md`.

## P0 — unblock the high-team field

- [ ] **High-team field pitch loop.** Teams 16/17 reach scene `$03` and the
      engine runs frames, but no pitch is thrown (score stays 0-0). Ruled out:
      NMI/`$047D`, PPU vblank, pitcher-trailer stub (`$B094`/`$FEB0`), COM
      flags `$04EB/$04EC`, `$C1`, the `$04/$05` card pointer, and `$047E`
      resets. Next: find the scene-3 dispatch target and trace its pitch
      sub-state (`$047A`, `$06DE/$06DF`, the batter/pitcher role bytes).
      Progress: the scene-3 handler is a no-op in stock too; a one-frame
      trace shows the card/CHR routines (`$E2B2-$E3FB`, `$C11C/$C14C`) and
      `$047A` stays `04` (the immediate CHR path at `$CE30-$CE42`). COM
      flags/`$04E9` reassertion did not start a pitch; player statuses
      (`$0555`) match the stock pattern. The field is stuck in the
      card/order state machine: `$047F` is rewritten to `$7C` every frame at
      bank6 `$9018`, `$05D3` is stuck below the `$903C[$0545]` threshold,
      and START can reach scene `0F` but B+A returns to the card loop.
      `$0489=0` is the live field phase, `$0489=3` is the box score; the
      blocker is the `$0545=3` card-cutscene step whose `$05D3` timer never
      reaches `$903C[$0545]`. The script pointer `$0543` starts at 0 and
      forcing 4 runs the interpreter then clears it; the missing piece is the
      match-start/order-screen exit that sets the live-field phase. The
      high-team order screen's B acts as back/cancel (`$BE=02`), returning to
      the card loop; `$06E1` selects B=END vs back. Setting `$06E1=1` makes B
      set `$BE=7`, but A only advances the `$BA` menu; `$C3` bit 7 is the
      back/cancel flag (clearing it lets `$BA` reach 11), and the final
      match-start condition is still missing. `$9F89` validator analysis
      rules out the lineup arrays; the remaining gate is the `$BE=7`/`$BA`
      menu with `$C3` bit 7 as the back flag and unreliable manual timing.
      The start path is identified: `$BE=1/4` -> `$9D9F` -> `$9DAE JMP $96E6`
      (live field init); forcing `$C7` does not dispatch, so the real button
      edge timing is the remaining probe. `$C7` (the edge) is never written
      at the high-team scene `0F`; the input loop that should set it is not
      running, so the `$9D9F` start path is never dispatched. `$C040` is ROM
      `$40`, and `$C7` requires `$95,X` bit 6 (B); the `$B8xx`/`$9EF0` input
      decoders are not in the scene-`0F` trace, so `$95` stays 0. `$95` is
      a status byte written by `$B8A9`/`$B90C` (from `$047C`/`$0630`/
      `$0547`/`$0527`), and that writer is absent from the scene-`0F` loop. The low-team path auto-confirms past
      scene `0F`, so the comparison needs a per-frame live-field capture.

## P0 continuation (user-requested, started)

- [ ] **Capture a low-team live-field/card-handoff save state** (or a
      breakpoint trace at the scene-`0F`/field transition). Probe result:
      speed-mode matches are simulated (~0.8 s, no scene `03` seen); watch
      mode stalls at match 0. No rendered low-team field to capture.
- [ ] **Capture the live password overlay state** (`$06B5` password text,
      `$23-$26`/CHR bank) so the 16 glyphs can be confirmed. Probe result:
      boot/series-start `$06B5` goes FF -> POWER ANALYSIS -> START NEW
      SERIES -> NEW YORK -> CONTINUE END; no password text, scene 13 shows
      the team name.
- [x] **Targeted skip-card -> live-field patch**: tested `$9011 =
      LDA #7/JSR $C14E/JMP $96E6`. The score moves to 1-0 and `$047C=07`,
      but the CPU runs into `$B005` and jams at `$0013`; not viable as-is.

## P1 — visible/gameplay correctness

- [x] **Post-game bracket cleanup.** Real 32-team codes
      (`build_bracket_codes32.py`) + nametable clear before the draw
      (`build_bracket_clear.py`); verified with a full match and
      `docs/bracket-clear-post.png`. Header/title leftovers fixed
      (`build_bracket_layout.py`, `docs/bracket-layout.png`).
      `$23-$26` shadows differ from the normal entry but are **not** the
      latched MMC1 CHR banks; writing them glitches the screen. Needs a
      mapper/PPU-level probe of the latched banks.
- [ ] **32-team password screen.** The model is done
      (`tools/password32.py`: 8-byte seed + 31 result bits + version), but the
      stock screen is an 11-character **letter-coded** buffer (`$06B5`), not
      16 hex digits. The A-P letter codec is implemented
      (`encode_letters`/`decode_letters`, 100 letter round-trips) and a
      candidate stock tile alphabet (`STOCK_TILES` from bank5 `$908B`,
      `encode_stock`/`decode_stock`); `tools/render_chr_tiles.py` is available
      for glyph confirmation, but the initial bank `$1B`/`$18` renders were
      blank/fragments. Still need the right CHR bank/tile base plus a wider
      buffer or 11-char compression. The 11-char fallback is implemented:
      16-bit seed + 31-bit results + version -> 10 base-32 chars + XOR
      checksum (`encode_short`/`decode_short`, 100 round-trips). It needs 32
      glyphs, so the stock 16-glyph font still needs a two-screen form or a
      wider buffer.
- [x] **Bench/pitcher data audit.** `test_roster32.py` now builds the 3
      pitcher records (08/10/18) and checks all 32 teams: 20 players,
      exactly `[8,16,24]`. In-game START-menu substitution still needs the
      live field (P0).
- [x] **Attribute data semantics.** `test_roster32.py` edits attrs[3]/[4]/[5]
      (bytes 9/10/11 = power/speed/skill index) and asserts the
      apply/extract round-trip. The printed-card proof remains blocked by
      the live field.

## P2 — password / soak / hardware

- [ ] **Wire the 32-team password into the stock screen** (after the screen
      format decision above) and keep the stock 16-team `$074D` path working.
- [ ] **Full-game soak with substitutions/save-password.** A 4-match
      `tools/soak32.py` run passes with real scores and the 400-round-trip
      password model (`build/soak32.json`). In-game substitution and the
      save-password UI still need the live field / password screen.
- [ ] **Match 5 soak stall (new).** 26-match speed soak: matches 0-4 pass,
      match 5 (09 v 0A) times out after 40k frames. Capture the field state at
      the timeout; determine whether it is the card loop or a COM/pitch stall.
- [ ] **Match 26 crash follow-up.** `11/13` at 2-0 enters scene `$1D`,
      `PC=$00C3` (RAM jam). Static finding: `direct31` scene `1E`/`1F` table
      entries are `$0101`/bank `$AD`. The earlier stock comparison was against
      an 8-bank layout and is not address-comparable; the fix needs the stock
      scene table relocated for the 16-bank build.
- [ ] **Hardware validation** on a flash cart / MMC1 donor. Checklist is
      written (`docs/hardware-checklist.md`); bench execution still pending.
- [ ] **Sound/music checks** after the data moves. Checklist is written
      (`docs/sound-checklist.md`); execution still pending.

## P3 — docs / product

- [x] **Regenerate screenshots and refresh the README status table** with the
      final 32-team build (selector page-3, bracket-layout, bracket-clear-post,
      and bracket-codes32 shots are in; README gaps refreshed).
- [x] **Final user-facing writeup** of the 32-team hack
      (`docs/32-team-status.md`: what works, what is still blocked, build
      instructions).
- [x] **Web editor base-table mirror** — not applicable: `web/rom.js` uses
      explicit `OFF32` offsets and reads the ROM tables directly; it does not
      compute offsets from a base table.
- [x] **Serve a downloadable patched ROM from the editor?** No: the policy
      is patch/build instructions only, no hosted ROM
      (`docs/rom-distribution.md`); the editor keeps the user's ROM local.
- [x] **DataCrystal ROM map** — closed as optional/external: the page is
      Cloudflare-blocked and has no usable text capture; `tools/llbcs_map.py`
      and the local docs remain the map of record.

## Done / do not re-open

- 32-team bracket state, five rounds, champion slot 62.
- Round labels, champion banner, top-row shift, cursor marker.
- Real 32-team bracket codes (`build_bracket_codes32.py`); `T17`..`T32`
  placeholders removed.
- Nametable clear before the bracket draw (`build_bracket_clear.py`); no
  leftover box-score rows.
- Bracket header/title cleanup (`build_bracket_layout.py`).
- Password hex/letter/stock-tile codecs with 100 round-trips each.
- `docs/32-team-status.md` and the refreshed README gaps/screenshots.
- Teams 16-31 names/codes/regions, 20-player rosters, ratings, lineups.
- On-demand roster cache (`build/direct31.nes`, MMC1 reset fix).
- Web editor 32x20 JSON + ROM modes, team codes/regions.
- CLI `roster.py show32`, `roster32.py extract/apply`, `rominfo.py` layout.
- Password encode/decode location, stock round-trip, 100-round-trip model.
- CI: password model, roster32, rominfo, metadata sync, JS syntax.
