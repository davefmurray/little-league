# Comp A workspace acceptance

Checked 2026-10-31. The hybrid restores Comp A with automatic roster loading,
after rollback `94c19a9`. The user reported that the earlier ROM-first build
froze Chrome; the exact cause was not reproduced or established.

## Browser

- At 1280 × 800, the ratings strip is 61.2 px high, the uniform row is 185 px,
  and the first player row begins at 517.8 px with the load banner visible.
- At 390 and 320 px, document width equals viewport width. The mobile team
  selector stays usable. The palette scrolls within its own container at 320 px.
- Both admitted ROMs display their decoded batter. No generic illustration or
  field-overlay cross is shown.
- Searching KOREA yields one team; Enter selects it. PARK still displays skill 5.
- The mobile selector chose Venezuela. Cap, jersey and hair changed through
  the shared palette; Reset colors returned all three and retained keyboard focus.
- Native keyboard Enter, arrow and Escape retained/restored palette selections.
- A number edit marked the draft dirty. Switching roster previews prompted;
  Keep editing preserved the edit, and Revert restored the baseline.
- Startup now opens the 32-team editor automatically, with no ROM loaded.
  Browser checks selected Venezuela and changed its jersey before opening a ROM.
  A review found that opening from the uniform
  placeholder lost focus when the placeholder disappeared. Reproduced in the
  browser, fixed by focusing the team heading, and checked again in-browser.

## Browser downloads

| Download | SHA-256 | Changed bytes |
|---|---|---:|
| Unchanged Preview 8 | `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b` | 0 |
| Venezuela cap $16, jersey $30, hair $38 | `f861d9674507165d371676e431e05351b36045fedd5546fadd2fed8cb17521b2` | 99 |
| Unchanged original US ROM | `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e` | 0 |

## Code and limits

The bounded independent review found no blocking session or export regression.
Its one focus finding is fixed with a regression test. The implementation's
141 tests passed on Node 20 and 26 with both real ROMs. Root reran the suite
with the additional focus regression (142 tests). The codec, source ROMs,
game behavior, and JSON schema are unchanged. This UI change does not claim
new emulator or hardware testing. Browser checks use Chromium desktop and
resized viewports, not physical phones or assistive-technology certification.

The hybrid suite passes all 142 tests with both source ROMs. The ROM codec is
unchanged. A responsive test browser does not establish the cause of the
previous user-reported Chrome freeze.
