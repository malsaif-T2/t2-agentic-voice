# Execution plans

Plans are first-class, versioned artifacts, so any agent can pick up work without relying on
chat history. The [roadmap](roadmap.md) orders them into milestones; [tech-debt.md](tech-debt.md)
holds what is known to be owed.

## When to write one

- **Small change** (a few files, one sitting): no plan file. Describe it in the commit.
- **Anything larger:** copy [TEMPLATE.md](TEMPLATE.md) to `active/NNN-short-slug.md` before
  writing code, where NNN is the next free number across `active/` and `completed/`. Update its
  progress and decision logs as you go, not at the end.
- **Done** when every acceptance criterion is met and `uv run poe check` passes. Then move the
  file to `completed/`, change its Status line (see below), and update the roadmap's row.
- **Several plans can be active at once** (one waiting on the owner while another moves). Each
  is linked from the roadmap: from its milestone's row, or, for work outside the milestones
  (garbage collection, side work), from the roadmap's "Outside the milestones" line.
- **Debt** discovered along the way goes into [tech-debt.md](tech-debt.md), not into chat.
- **Size:** a plan that grows a module above `[gc] size_watch` lines (`harness.toml`) names the
  split that brings it back, and a split leaves every module at or under the watch, not just
  under the hard limit (`[modules] max_lines`). Splitting just under the limit made plan 002
  split again and again.

Folders: [active/](active/) holds plans in progress, and `completed/` the finished ones.

## The format the checks read

`uv run poe docs` (DOC-PLAN, DOC-REGISTER) parses every `*.md` in `active/` and `completed/`,
and fails on each item below that does not hold:

- **File name:** `NNN-short-slug.md`: three digits, a hyphen, and a lowercase slug of letters,
  digits, and hyphens. No two plans share a number, across both folders (DOC-REGISTER). A
  garbage-collection round is named `NNN-garbage-collection-K.md` (K counts the rounds), which
  is how `uv run poe gc` finds the last round.
- **Status line**, on its own line under the title:
  - in `active/`: `Status: active · Milestone: Mx · Started: YYYY-MM-DD`
  - in `completed/`: `Status: completed · Milestone: Mx · Started: YYYY-MM-DD · Completed: YYYY-MM-DD`
  - maintenance work outside any milestone says `Milestone: none (maintenance)` (another
    reason in the brackets is fine: `none (side work)`).

  DOC-PLAN checks the whole line, separators included, since `poe gc` reads
  `Status: completed · Milestone: Mx` and `Completed: YYYY-MM-DD` from it to see which
  milestones completed since the last round.
- **Required sections** (`##` headings, spelled as in the template): Goal, Acceptance
  criteria, Plan, Progress log, Decision log. DOC-PLAN fails a plan that misses one, and an
  active plan the roadmap does not link.
- **References:** "plan NNN", `D-NNN`, `TD-NNN`, `GP-NN` and "invariant N" must exist wherever
  they are cited (DOC-REF), so never cite a plan number before its file exists.
- **Code samples:** a fenced block that follows a link to a `.py` file, with no other fence
  between them, is read as a copy of that file and must be a run of its lines, indentation
  aside (DOC-SAMPLE). A block of new or changed code has no `.py` link between it and the
  fence before it.

## Optional sections

Add them after the required ones when they help; each proved useful before.

- `## The owner's decisions`: the owner's calls, dated and quoted in their own words
  (`- YYYY-MM-DD: "..."`), so a later reader can tell what the owner said from what the agent
  proposed.
- `## Inventory`: findings recorded before any change (a garbage-collection round, a failure
  diagnosis), including what was considered and kept, and why.
- `## The measurement, registered before any result`: for any plan that measures (see
  [evaluation.md](../design/evaluation.md)): the data, the arms, the metric, the keep and
  reject rule, the expected outcomes, the cost, and every open question marked "the owner's
  call before the run". Amendments are dated and made before the result they affect.
- `## Proposal for the owner (not started)`: a design waiting for approval.
- `## Future improvements`: written when a plan closes, ordered by expected value, with a
  pointer from the roadmap's "Planned later".
- `## Schedule (unattended)`: for a session that runs while the owner is away (overnight, a
  long run); the shape is in [WORKING-RULES.md](../../WORKING-RULES.md), "Unattended sessions".
- `## Tracks`: for a plan built by several agents at once (below, "Parallel tracks").

A progress-log line that departs from a registered protocol starts with `Deviation:`.

## How work moves

- **Commits:** a commit of a plan belongs to that plan alone and names it in its subject
  (`Plan NNN: <what>`), with that plan's logs updated in the same commit, so every plan's
  history reads on its own; a small change outside any plan says what it changes in its
  subject. Review fixes land as their own commits (`Plan NNN: review fixes, block X`).
- **Blocks:** a larger plan lands as small blocks, each gated by `uv run poe check`. The
  default for a plan of several blocks: each block is built in its own worktree
  (`.claude/worktrees/<name>`) and reviewed by an agent that did not write it before it is
  merged, and the whole plan gets one more review at the end. Findings become fixes (a bug
  gets a failing test first), or rows in [tech-debt.md](tech-debt.md) that say which review
  found them.
- **Numbers:** several sessions may share a checkout. Before claiming a plan number or a
  decision number, list `active/`, `completed/` and
  [decisions.md](../design/decisions.md), and check no other session has claimed it
  ([working rules](../../WORKING-RULES.md)). If two sessions took the same number anyway,
  DOC-REGISTER fails on the second one.
- **Lasting decisions** move from a plan's decision log to
  [decisions.md](../design/decisions.md) as a `D-NNN` entry.

## Parallel tracks

When a plan is built by several agents at once, each in its own worktree, the work is split so
that no two agents edit the same file and every track can be reviewed alone:

1. **Block 0 first, by one agent, merged before any track starts.** It lays down the shared
   interfaces (the models, the protocols, the function signatures, the settings) with stubs
   that raise, and records baselines for whatever must not change by accident (a request's
   body, a prompt, a generated file, a command's output) so the tracks can be compared with
   them byte for byte.
2. **The `## Tracks` section** lists each track: its goal, the files it owns (one owner per
   file; a file two tracks need goes into Block 0), what it may read, and its tests.
3. **Each track builds against fakes of the protocols** (a fake implements the protocol and
   nothing else), never against another track's unfinished code.
4. **Reviewers are named by concern,** not by track: for example security (trust boundaries,
   invariants), harness (layers, checks, docs, tests), and faithfulness (the code does what the
   plan and the baselines say). Each reviews every track for its concern; findings are checked
   by an agent told to refute them.
5. **Merging goes through an integration branch:** `Plan NNN: merge track X`, then
   `Plan NNN: review fixes, track X`, with the full gate after each merge, and the plan's logs
   updated in the same commits. The integration branch merges into the main branch once the
   whole plan's review is done.
