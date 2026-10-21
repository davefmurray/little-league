# AUTOLOOP — one contract for every agent

## State

`docs/backlog.json` is the **only queue**. Every agent reads/writes it with
`tools/backlog.py`; the markdown TODO files are notes, not the source of
truth.

Task fields:

```
id, title, priority (P0/P1/P2), status (queued|active|blocked|done),
depends_on[], next, verify, attempts, evidence, last_commit, blocked_reason
```

## The loop — one iteration = one experiment

1. **pick** — highest-priority ready task (all `depends_on` done).
2. **start `<id>`** — status `active`, `attempts++`.
3. **Baseline** — run the task's `verify` command *first* to confirm the
   current failure/state. No assumptions.
4. **Change** — one reversible change. Write the hypothesis in the commit
   message and `docs/AUTORUN-REPORT.md`.
5. **Verify** — run the `verify` command; capture exact output.
6. Record:
   - pass → `done <id> --evidence "..." --commit <sha>`
   - fail → `block <id> --reason "..."` **and** `add` a blocker task if
     the fix is not the current task.
7. **Commit + push** — code, `docs/AUTORUN-REPORT.md`, `docs/backlog.json`.
8. End the round. The next round starts at 1.

## Evidence rule

No `done` without the verify command output. “Should work” is not evidence.

## Blocker rule (anything that pops up)

Any of these creates a new **P0** task via `backlog.py add` and links it
with `depends_on`:

- verify fails and the fix is outside the current task;
- a new unknown appears (e.g., the table is the wrong shape);
- a tool/server is down;
- the change touches an unexpected bank/table.

The blocker task has its own `next` and `verify`; the loop picks it next.
Nothing is silently absorbed.

## 3-strike rule

- `attempts >= 3` on the same task → stop, write a **resume packet**
  (state, what was tried, the exact next probe), `block` it, and ask the
  user.
- Never retry the same patch twice without a new hypothesis.

## Context checkpoint

When context is low or N rounds pass without a `done`: commit everything,
write the resume packet into the task's `next`, `block`, and stop. No
status-only rounds.

## Agent contract (all agents)

```bash
python3 tools/backlog.py pick
python3 tools/backlog.py start <id>
# ... work ...
./tools/verify.sh                 # stock gate (check_build + data tests)
./tools/verify.sh --with-soak     # + 6-match soak (needs romdev)
python3 tools/backlog.py done <id> --evidence "..." --commit "$(git rev-parse --short HEAD)"
# or
python3 tools/backlog.py block <id> --reason "..."
python3 tools/backlog.py add --id <new> --title "..." --priority P0 \
  --next "..." --verify "..." --depends-on <parent>
```

## T3 integration

- The **goal rounds are the timer**: one loop iteration per round.
- If the goal is idle, `schedule_task` with an interval wakes the thread;
  the prompt is the loop above.
- `tools/verify.sh` is the gate; `docs/backlog.json` is the memory.
