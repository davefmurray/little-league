# Team-color review resolution

Two independent reviewers tested the 24-file implementation snapshot. Neither
found a critical defect. Both reproduced the pinned ROM variants and exact
exports. The implementation was reviewed before deployment.

Accepted fixes:

- Both reviewers found duplicate Advanced-entry announcements and a missing
  announcement on team navigation. The picker tracks its last announced code
  and closes before switching teams. A regression observes status writes.
- Reset now puts keyboard focus on the enabled color button. The real browser
  confirmed that Enter on Reset restores the value and returns focus there.
- Export now refuses a baseline that does not describe its source ROM,
  including a mismatched color baseline that would otherwise add an
  unnecessary upgrade. Tests cover both layouts and real ROMs.
- The below-black warning is attached to the button's accessible description
  only while applicable, and is included in the polite status announcement.
  Browser checks verified both DOM properties; screen-reader speech was not
  tested.
- About text discloses the first Preview 8 color export's upgrade. The stale
  TODO entry and incorrect legacy-offset comment were corrected. CLI advice
  for old two-color data now directs 32-team users to Roster Lab.
- Ten narration-only comment blocks were removed. ROM ownership, palette,
  OAM and hardware facts remain documented.

The stylesheet-size warning is waived. The new color rules form one
contiguous component section in the existing shared theme. Keeping the
single stylesheet preserves its established organization and avoids an
unnecessary asset dependency. No rule in the deployed ratings repair moved.
Broader comment cleanup and removal of explicit upgrade guards were deferred;
neither changes the demonstrated behavior or addresses a current defect.

Final checks cover Node 20 and 26, the CLI, the actual-export CPU matrix,
and real-browser input, layout and downloads. CPU evidence does not establish
hardware or gameplay-emulator behavior.
