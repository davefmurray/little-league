# Team-color browser acceptance

Local checks used the integrated editor on 2026-10-31 with the original
Preview 8 ROM. These checks ran in the real browser, separately from the
DOM-stub tests.

- Opening Preview 8 showed 32 teams and the batter decoded from the ROM.
- An unchanged download matched the source SHA-256
  `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.
- Changing Venezuela to cap `$16`, jersey `$30`, hair `$38` through the
  swatches produced exactly 99 changed bytes and SHA-256
  `f861d9674507165d371676e431e05351b36045fedd5546fadd2fed8cb17521b2`.
- Reopening that download selected the independent-colors variant and kept
  Venezuela's three values. Chinese Taipei retained `$1B/$2B/$0F`.
- Arrow keys changed the focused swatch. Escape restored the opening value
  and returned focus to the row button. Enter and Space kept the choice and
  closed the picker. Per-row Reset restored the opened ROM's color.
- Advanced entry rejected `64` without changing the color. `$0D` was accepted
  with the inline note. Escape restored the prior value.
- At viewport widths 320, 390, 760, 1100 and 1280, page overflow was zero and
  every rating button stayed within its group. The picker scrolled within
  its own box at the two narrow widths. The canvas stayed at 147 by 174 CSS
  pixels, three times its 49 by 58 source dimensions.
- Desktop and 390-pixel screenshots were inspected. The batter, controls,
  selected swatch, labels and narrow-screen scrolling rendered correctly.
  Browser snapshots reported no console errors.

The independent review found duplicate announcements after Advanced entry
and a missing announcement when leaving a team after an arrow-key edit.
The picker now tracks its last announced code and commits before switching
teams. A regression test observes the actual status-element writes for
Advanced, navigation and Reset. All 135 editor tests pass on Node 20 and 26
with both real ROMs. This is not a screen-reader speech test.

After the second review, a native keyboard pass confirmed that Enter on a
row's Reset button puts focus on the enabled color button. Setting `$0D`
updated both its accessible description and its polite status message with
the caution. The export-boundary fix also passes the complete Node suites.

ROM runtime evidence remains the CPU-model palette-consumer matrix. This
release does not claim hardware, emulator, ending-scene visual or full
tournament validation of recolored ROMs.
