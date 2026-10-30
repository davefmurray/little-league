# Roster editor browser acceptance

Root tested the integrated change in T3's Chromium browser against the local
Python host at `http://127.0.0.1:8098/` on 2026-10-30. These are browser tests,
separate from the DOM-stub and CPU-model tests. Production acceptance follows
the reviewed source push.

## Baseline failure

On the deployed site before changes, uploading the accepted Preview 8 ROM
displayed ROM READY, 16 teams and 15 rows. The new teams were inaccessible.
Railway's deployed commit was `4a889a720cee7bdf8d98c9ef64bb29e92609c34e`.

## Local candidate

- Default preview displayed 32 teams, 15 editable rows and the Preview 8
  release download link. Export ROM was disabled without a source ROM.
- Uploading Preview 8 displayed ORIGINAL ROM and all 32 teams. Identity fields
  were read-only. Team 32 displayed five stored rows with no inputs or buttons.
- Downloading an untouched ROM produced SHA-256
  `a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b`.
  Its bytes equal the uploaded Preview 8 file.
- Edited team 1 player 15 to LOWEND and team 32 player 15 to HIEND, then set
  their first ratings to 4 and 1. The downloaded file matched an independently
  constructed expected image exactly. Differences were limited to file offsets
  `0xFC90`, `0xFD0C`, `0x10510..0x10515` and `0x22D80..0x22D85`.
- Reopening that download displayed EDITED ROM with both names and ratings
  intact. Because the draft matched the reopened file, no discard prompt appeared.
- After a new unsaved name edit, opening another ROM displayed the native
  replacement dialog with focus on Keep editing. Keep editing and Escape each
  retained the old source and draft. Replace loaded the candidate and cleared
  the unsaved state. Repeated prompts remained usable.
- Exported JSON retained code and region metadata and the 15/20 stored counts.
  Reimporting the draft retained the original ROM baseline and unsaved state,
  without a prompt. An attempted unused-player edit and an incompatible stock16
  import were refused without changing the draft or showing a replacement dialog.
- Reset team restored the loaded-ROM player and cleared the unsaved state.
- Uploading the original US ROM displayed 16 teams, 15 rows, editable stock
  identity controls and no unused-player section. Its untouched download equals
  the source, SHA-256
  `58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e`.
- At 390 CSS pixels, document width remained 390. Top actions stayed within
  the viewport, and the roster table scrolled horizontally within its container.
  A real screenshot was inspected. The speed slider was reachable at the right
  edge; ArrowRight changed 8 to 9, updated the displayed value and preserved the
  record's high nibble. Escape closed the Data menu and reset aria-expanded.
- After the review correction, opened a ROM whose first name was EDITED,
  restored UMEDA, and selected the identical Preview 8 roster. The native
  dialog opened with Keep editing focused. Cancel retained the ROM, UMEDA
  and UNSAVED. This checks session replacement even when draft pixels match.
- Desktop checks used the default viewport and 1440 CSS pixels. The candidate
  retains the existing visual style and a local-file-only editing flow.

Downloaded files were copied into `build/web32-acceptance/` before closing the
browser tab. They are not committed. These checks do not claim physical-phone,
Safari, Firefox or gameplay-emulator acceptance.
