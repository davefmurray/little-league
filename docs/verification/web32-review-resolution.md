# Editor review resolution

Both independent reviews are preserved beside this file. They evaluated the
frozen implementation; root applied the following focused corrections afterward.

| Finding | Resolution | Evidence |
|---|---|---|
| Sol R1 / Opus F1, manufacture PARK skill 7 | Shared import/write boundary requires an existing baseline 7 | Updated real-ROM suite; independent two-case PARK regression |
| Opus F5, CLI source overwrite | Exclusive creation refuses existing output | Five scratch output/alias cases |
| Opus F2, equal roster loses dirty session | New sessions always prompt while dirty; equal imports into the same session remain prompt-free | Session tests and native browser cancellation |
| Opus F3, empty legacy scoreboard names | Legacy empty strings retain baseline; v2 empty strings stay explicit | Stock synthetic and real-ROM import tests |
| Opus F4, failed boot shows Loading | Empty error state shows NO ROSTER; opening ROM recovers | Failed-fetch/recovery test |
| Opus M1, stale prompt boundary | Replacement helper checks ticket before each prompt | Existing reversed-read/hash and late-dialog tests |

Final real-ROM Node run passes 70/70. Synthetic-only run passes 47 and explicitly
skips 23 real-ROM cases. CPU checks use a real editor export and pass all32 cache,
role and live-rating reads. See the browser acceptance record for measured UI
checks. The final code hashes are in web32-source-hashes.json.

The punctuation restriction is intentional under the accepted font contract.
Optional API/comment refactors were not needed to resolve the reported behavior.
No emulator gameplay or physical-phone claim is made.
