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
      set `$BE=7`, but A only advances the `$BA` menu; the final match-start
      selection is still missing. The low-team path auto-confirms past
      scene `0F`, so the comparison needs a per-frame live-field capture.

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
      buffer or 11-char compression.
- [ ] **In-game bench / substitution test.** The data audit is green
      (16 x 20 players + 3 pitcher records); still need a live START-menu
      substitution/pitcher change on a 20-player team.
- [ ] **Attribute semantics in-game.** Prove byte 9 = power, byte 10 = speed,
      byte 11 = printed Skill by editing one player and reading the card.

## P2 — password / soak / hardware

- [ ] **Wire the 32-team password into the stock screen** (after the screen
      format decision above) and keep the stock 16-team `$074D` path working.
- [ ] **Full-game soak with substitutions/save-password.** 26 complete real
      games already pass; add substitution and save/password round-trip runs.
- [ ] **Match 26 crash follow-up.** `11/13` at 2-0 enters scene `$1D`,
      `PC=$00C3` (RAM jam). Trace the stock post-game path beyond its 16-team
      design.
- [ ] **Hardware validation** on a flash cart / MMC1 donor.
- [ ] **Sound/music checks** after the data moves.

## P3 — docs / product

- [ ] **Regenerate screenshots and refresh the README status table** with the
      final 32-team build (the selector page-3 shot is already in).
- [ ] **Final user-facing writeup** of the 32-team hack (what works, what is
      still blocked, build instructions).
- [ ] **Web editor base-table mirror** (only if it computes offsets; the
      current editor reads the ROM tables directly).
- [ ] **Serve a downloadable patched ROM from the editor?** Decide policy.
- [ ] **DataCrystal ROM map** — optional; the page is Cloudflare-blocked and
      has no usable text capture.

## Done / do not re-open

- 32-team bracket state, five rounds, champion slot 62.
- Round labels, champion banner, top-row shift, cursor marker.
- Teams 16-31 names/codes/regions, 20-player rosters, ratings, lineups.
- On-demand roster cache (`build/direct31.nes`, MMC1 reset fix).
- Web editor 32x20 JSON + ROM modes, team codes/regions.
- CLI `roster.py show32`, `roster32.py extract/apply`, `rominfo.py` layout.
- Password encode/decode location, stock round-trip, 100-round-trip model.
- CI: password model, roster32, rominfo, metadata sync, JS syntax.
