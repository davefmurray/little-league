# Mode menu artwork

The initial sparse concept below is superseded by the user's sunny-ballpark
selection. The current target includes color, families, players and crowds.

The request is to replace the stock stadium mode menu with artwork matching the
navy, cream and gold title and team picker. Frozen input is title32
`8f4a14a34e4daad9b45e31bf633005d855912cb12ecbcdcdf2192d3ff4b9696c`,
main commit `568ccd1339731613310492a70b9abdc0be35a6b0`.
This is design/prototype evidence, not acceptance.

## Throughput checkpoint

- Blocking first steps: inspect scene 6/7 draw and all native submenu/font/cursor
  footprints; establish CHR and padding ownership before choosing a hook.
- Independent workstreams: Opus and Sol design in separate scratch directories.
  Root owns pxl artwork, real-core captures, integration and release evidence.
  The configured Grok lane is unavailable in this session and is not substituted.
- Shared mutable state: designers do not write the repository or run romdev.
  One implementation owner will own the coupled builder/converter/CPU suite;
  root art paths and the owner's tool paths remain disjoint.
- Smallest safe decomposition: one additive modeart32 stage, followed by root
  controller/mapper/audio checks and independent review. It does not replace
  input dispatch, ownership, password, random-draw or gameplay logic.

## Design rubric

Score each candidate 0–4 on reachable byte ownership, preserved menu semantics,
NMI/mapper/audio correctness, freedom to author NES-valid art, and reproducible
verification. Read both designs before a fresh cross-judge selects a base.
Require a normal-art interface that hides physical map/dictionary placement.

## Initial grounding and prototype

The stock scene 6 handler is bank 1 $9400. It initializes song 6 and menu state,
then draws a metatile background and native labels. Scene 7 at $944F dispatches
main/submenu states through $BA. The submenu labels and cursor have different
footprints, notably wide 1P/2P glyphs and Exhibition's cursor at x=80.

Sol's completed design proposes a 94-byte adapter in the reclaimed old map,
private native-format dictionary/map in bank 4 padding, and replacement CHR06.
It keeps the entire input/dispatch program and native uploader/text/audio.
Its stock-equivalent and synthetic-art CPU probes pass. Opus's independent
candidate remains pending; no synthesis decision has been made.

Root art is in art/modeart32. The first prototype reserves all native text
bands and uses 195 of 256 tiles, including the 49 native label tiles. The
layout has a cream sign frame, gold rules, native baseball cursor and a small
stadium ticket entrance. All colors come from the exact NES palette.

The scratch build uses Sol's adapter and loads successfully on the real core.
Main, Championship and Exhibition submenus render in the new style, with scene
7, expected $BA, CHR(1B,06) and song 6. Screenshots and the exploratory builder
are under build/modeart32-design. These are visual/prototype checks, not final
production guards, full flow acceptance or a new published ROM.

## Selected direction and synthesis

The user rejected the sparse draft for lacking color and people, then selected
the sunny ballpark concept. The implementation target is now red brick, blue
sky, green grass, families, players and a popcorn vendor. The earlier draft
art and its 195-tile prototype are rejected, not the visual acceptance target.

The independent judge recommends Opus B, 17/20 versus Sol A's 15/20. Root agrees:
B's compact, movable text preserves room for the people in the lower half.
A can render colors correctly; its limiting factor is fixed two-row native
font geometry, not palette support. Experience First changes the choice from
the smallest adapter to the renderer that supports the selected composition.

Use B's bank-13 block and matching bank-1/bank-13 hop pad. Keep the existing
mode input, dispatch, exits and audio. Graft A's exact guard ledger, deeper
semantic tests, normalized audio comparisons and interrupt probes. Add strict
asset-length and raw-run validation, all-menu overlay checks, whole cursor
composition and output alias tests. Reject malformed assets before mutation;
43 raw tiles plus a terminator can overwrite mode byte $06E0, so production
runs must remain at most 32 tiles and within their declared row spans.

Model the Domain shapes one immutable mode-art asset with three named menu
presentations, shared background/palette, legal text spans and cursor origins.
The art owner writes only /tmp/ll-modeart32-art; the implementation owner
writes only new tools in its isolated checkout. Root integrates the selected
art and owns emulator, documentation and publication. There is no animation
or new input behavior in this first mode-art stage.

## Selected art and first real-core render

The completed sunny-ballpark pxl art replaces the rejected draft in
art/modeart32. It includes red brick, blue sky, green grass, families, players,
bleacher crowds, a ticket queue and a popcorn vendor. The converter measures
254 tiles including 24 font/blank slots. The source PNG SHA256 is
37557f66f4caa5ce572b7ccdc35acc3c39ebea2b748afd6f9bd08541d80754cf.

Root built the completed art through the B scratch adapter on title32. The
prototype SHA256 is
7624f8f8ceb676926b90f773f062f2f4cf1796e8bbc17889bf2964ece76ccbd9.
Controller input from boot opens main, Championship and Exhibition with scene
7, expected submenu state and song $06 selected. Actual emulator screenshots
are under build/modeart32-design/sunny. These are preliminary visual checks;
the guarded production build, full regressions and independent review remain
pending. The implementation owner has received the final asset paths.

## Guarded integration and review scope

The implementation tools and final art reproduce the same 7624f8f8 ROM as the
scratch preview. Root integrated the four new tools, generated assets and 12
PNGs, then appended the stage to the source pipeline and verify script.
Pinned pxl regeneration and the source rebuild pass. The real-core tour passes
all menu choices, wrap, B, both START ports, Analysis return and keyboard EXIT.
The keyboard B control deletes characters; the first probe's mistaken B-exit
expectation was corrected without changing any ROM bytes.

Independent review uses the interrogate rubric with available Opus and Sol
lanes. Grok remains unavailable. Both receive the same frozen code/art scope,
with report-only comment auditing. Long runtime logs may still be in progress
and cannot support an acceptance claim until their final PASS is recorded.

## Review correction and runtime limits

Sol reproduced a regeneration bug using a nested PNG hardlink to a scratch
copy of title32. The --pxl regeneration branch bypassed the explicit output
guards. Root added whole-batch destination preflight and atomic replacement
for generated PNGs. Twelve alias cases and two real pinned-pxl CLI cases now
reject before persistent outputs change. A linked unrelated inode also stays
unchanged when its intended PNG entry is replaced. The asset and ROM hashes
are unchanged. The full CPU suite was rerun after this tooling-only fix; the final log also
includes the subsequent exact-output collision regressions.

The combined stock-six/random-full-31 gate passes, champion 07. Full controller
2P Exhibition reaches the stock terminal tie and preserves the suspended
series through title and CONTINUE. The 1P A-only driver stalled on a loose ball
in half-inning 2; manual directional input moved the fielder on the live core.
Root stopped that diagnostic and retains it as incomplete evidence. This is
not counted as a completed 1P game. The current stage's exact 1P setup/cache
and controller checks remain valid, and prior title32 has a full 1P run.

The final WATCH Exhibition/attract/demo/CONTINUE tour passes on 7624f8f8.
It preserves the canonical series and exported password. Its mapper census
covers 95811 frames and 11273206 writes with no serial misalignment and no
PRG13 selections in windows wholly outside the mode-menu scenes. All32
Analysis screens and the real-keyboard LIST/CONTINUE flow also pass. The
runtime probes disclose SPEED ownership injection and the incomplete 1P
fielding-driver diagnostic separately from the completed gates.


## Final output collision correction

The safety recheck confirmed the original alias fix, then found an initially
missing generated PNG could equal --out or --preview. Root reproduced the
failure with a new regression before editing the installer. The intended PNG
may replace its own old art entry, but ROM, source, data and explicit outputs
now always remain protected. Two independent scratch-checkout subprocesses
reject these cases with all 236 file hashes unchanged. Committed tests exercise
both helper and real-pxl CLI routes, preserve prior outputs, and still allow
normal regeneration. This final small correction was verified by root, not
sent back to the completed reviewer. No ROM bytes changed.
