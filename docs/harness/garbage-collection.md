# Garbage collection

Entropy management ([PRINCIPLES](PRINCIPLES.md), section 5): a recurring round that finds and
removes duplicated patterns, drift, stale docs, and technical debt, and turns recurring
mistakes into checks. Each round is an execution plan, not a milestone
([plans](../plans/README.md)):

- file name `NNN-garbage-collection-K.md`, where K counts the rounds (1, 2, ...);
- Status line `Status: active · Milestone: none (maintenance) · Started: YYYY-MM-DD`;
- linked, while active, from the roadmap's "Outside the milestones" line;
- an `## Inventory` section, written before anything changes.

## When

The owner asks for a round when they see fit. `uv run poe gc` opens by saying whether one is due,
and why (`scripts/gc_due.py`). Counted after the commit that moved the last round's plan into
`completed/` (before the first round, after the repository's first commit):
- a milestone completed (a completed plan's Status line names it, and no active plan's does);
- a set number of commits landed, merges left out, since a merge repeats its branch's commits
  (`[gc] due_after_commits` in `harness.toml`; 100, about one milestone);
- a layer grades below what [quality.md](quality.md) records (compared only when coverage was
  measured alike).

It informs and blocks nothing. Two more reasons to ask for one, which only a reader sees: the
same kind of fix or review comment showing up a second time, and new duplicates or a module
crossing the size watch in the candidates below the signal.

## A round

1. **Measure.** `uv run poe gc` lists candidates after its signal (not a gate: each one needs
   judgment):
   - duplicated code outside `tests/` (runs of `[gc] min_tokens` tokens or more; imports,
     dunder methods, comments and layout ignored), one line per run with every place it starts;
   - unreferenced top-level definitions and methods (decorated ones, `main`, tests, and the
     framework hooks listed in `[gc] hooks` excepted);
   - suppressions per file, and every `noqa` without a reason;
   - modules above `[gc] size_watch` lines (below the hard limit `poe arch` enforces,
     `[modules] max_lines`);
   - file paths named in the living docs and the code that do not resolve (in `tests/`, read
     from comments and docstrings only);
   - code names the living docs cite in backticks that the code no longer has.

   History (`[docs] historical`) is not read; a doc of planned code (`[gc] planned_docs`) gets a
   count instead of a list.
2. **Read.** Walk every layer, every app (`[[apps]]` in `harness.toml`), the scripts, the
   tests' shared helpers, and the living docs, looking for:
   - the same logic or message in two places (the report finds copies; only a reader finds
     re-implementations);
   - models and helpers that restate a core definition instead of reusing it;
   - docs, docstrings, and comments that no longer match the code;
   - tests that are slow for no reason (`uv run pytest -n auto --durations=20`, as `poe test`
     runs them);
   - tech-debt rows that have become cheap, or are stale;
   - every number and reason in the docs written since the last round, traced to a
     measurement, a command's output, or the owner's words (GP-16);
   - the warnings of the last gate run: a warning can be a bug.
3. **Record.** Write the inventory into the plan before changing anything: duplications, drift,
   recurring mistakes, bugs, what was considered and kept (with why), and the debt that is
   payable now.
4. **Fix in blocks.** Each block is verified by `uv run poe check`. Cleanup preserves behavior:
   a bug found on the way gets a failing test first, and the plan lists it.
5. **Promote.** A mistake seen twice becomes a check, test, or doc, and
   [golden-principles.md](golden-principles.md) says which. Principles still enforced by
   "review" are the candidates.
6. **Pay debt.** Pay the payable rows in the [tracker](../plans/tech-debt.md), and bring the
   others up to date.
7. **Grade.** After the gate, `uv run poe quality`; update [quality.md](quality.md)'s table, and
   each layer's gaps in words.
8. **Close.** Docs updated, plan completed, gate green.

Every round also checks the thresholds in `harness.toml`'s `[gc]` (the duplicate run length,
the size watch, the commit count, the path bases, the lists of hooks and foreign names) against
what its read found to be noise, and records each value it changes in its decision log; the
harness's tests show that each kind of noise silenced still leaves a stale path or name beside
it reported.

## Rules of thumb

- **Fewer places, not fewer lines.** Consolidate when two copies must change together. Leave
  look-alike code whose inputs differ, and say so in the plan, so the next round does not redo
  the analysis.
- **Parse once, at the boundary.** A model at a boundary restates a core model's constraints
  only by reusing them. Copies drift, and drift at a boundary becomes a server error.
- **No silent behavior changes.** A change a caller could notice (a message, an output format)
  is listed in the plan and covered by a test.

## Rounds

Each round adds a line here: its plan, what prompted it, and what it found.

- [Round 1](../plans/completed/004-garbage-collection-1.md), 2026-11-02, after M1: `poe gc`
  said one was due (M1 completed; 'commits: 101' with no round yet). The read of five areas
  found 143 things, 8 of them bugs, each fixed with a failing test first. Four blocks and the
  close renamed the base error (D-026), made copies one, fixed drift and stale docs, promoted
  8 mistakes seen twice to a check, a test or a doc (ARCH-DEPS and DOC-SAMPLE new, D-027), paid
  7 debt rows and merged 3, and calibrated `[gc]`.
- [Round 2](../plans/completed/008-garbage-collection-2.md), 2026-11-13, after M5, when the owner
  asked ("its been long overdue"): `poe gc` said one was due (M2 to M5 completed; 451 commits).
  Six readers found about 180 things, 5 of them bugs, each fixed with a failing test first. Six
  blocks made about 60 copies one, split 11 of the 13 modules at the cap, ran the guard and the
  action states on the domain's rules, brought the docs and the debt list up to date,
  promoted the plan-time names to a check (DOC-PLANWORDS) and the real-time tests' bounds to
  GP-12 (D-090), and recalibrated `[gc]` (a round due after 100 commits; duplication scored per
  1,000 lines). The duplicate pairs fell from 861 to 603.
