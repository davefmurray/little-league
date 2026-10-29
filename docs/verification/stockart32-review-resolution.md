# Original-character stage review resolution

Both independent reviewers approve the ROM at
`a5bf74ee453bee21afcf0b92696aaebfc013905a53921206fe7614321311cb55`.
Neither review substitutes for the root's emulator or integrated gates.

## Fixed

- Probe outputs now reject all symlinks, multiple hard links and nonregular
  files before emulator dispatch, including `mode-audio.json` linked to
  unrelated earlier evidence. The regression uses scratch copies instead
  of linking real tracked inputs.
- Crowd target validation iterates every shirt instead of collapsing shirts
  by palette index. A bad gold shirt sharing palette 2 fails in either
  insertion order.
- Manifest parsing validates optional collections and screen/part identifiers
  before iteration or dictionary lookup. Null seeds, specks and ink lists,
  and list-valued identifiers produce field-specific manifest errors.
- Removed Python section-divider comments. Retained comments explaining
  source transparency, NES palette/OAM constraints and reference provenance.

The [targeted regression log](stockart32-review-fixes.txt) exercises these
changes. The [post-fix asset check](stockart32-assets.txt) reproduces all
17 registered files and the same ROM without writing outputs. No art,
manifest, registry or executable ROM bytes changed during review fixes.

## Deliberately retained

The reviewed composition is unchanged. A few source-zero outlines show the
cream wall, and cyan-to-red recoloring changes small shirt-shading patches.
These are documented art limitations, not a claim of full source-pixel
identity. Tests independently verify every retained pixel and pin the
complete selected masks. The user approved the rendered appearance.

Optional broader changes to converter phases, registry helper reuse,
placement defaults and test-file organization are deferred. The selected
implementation has measured regeneration, failure and alias coverage;
these suggestions identify no additional current data-loss or ROM defect.

The integrated gate began before these tool-only fixes. Its ROM matches
the final artifact; the targeted regressions above cover the changed
parser, palette checker and probe preflight directly.
