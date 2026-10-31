# 000 · Project scaffold and harness

Status: active · Milestone: M0 · Started: 2026-10-28

## Goal

Create the smallest environment in which an agent can reliably build Ole5 Voice Agent: a
uv-managed project on the chosen stack, a layered package chosen for this domain, one
validation gate, mechanical enforcement of the architecture and documentation rules, and a
repository-local knowledge base that says what is being built and how work is done. The
harness came from a starter kit; this plan makes it this project's own.

## Acceptance criteria

- [x] No placeholder of the kit is left: `uv run poe docs` reports no DOC-PLACEHOLDER
  violation (it reads every file and every file and folder name, `.github/` included).
- [x] [DESCRIPTION.md](../../project/DESCRIPTION.md) states the product idea, written with the
  owner, and the owner approved it.
- [x] The layers for this domain are chosen and approved by the owner: `harness.toml`,
  [ARCHITECTURE.md](../../../ARCHITECTURE.md), and a decision in
  [decisions.md](../../design/decisions.md) agree, and the library's package holds one package
  per layer.
- [x] The stack is recorded as a decision and approved; `uv sync` installs the locked
  dependencies.
- [x] `uv run poe check` runs lint, types, arch, docs, and test, and passes.
- [x] Every check reports each violation with a FIX line, and has tests in `tests/harness/`.
- [x] `CLAUDE.md` is a map that reaches every doc, within its line cap.
- [x] The optional docs are adopted or dropped, each with its reason in the decision log:
  [SECURITY.md](../../SECURITY.md) (does the product have trust boundaries?) and
  [evaluation.md](../../design/evaluation.md) (does it have a quality that can be measured?).
- [ ] CI runs the same gate on every push and pull request, and passes.
- [ ] The owner has read [WORKING-RULES.md](../../../WORKING-RULES.md) and said which rules to
  keep, change, or add; their answer is recorded there in the rule shape it describes.
- [x] The roadmap lists the milestones after this one, approved by the owner.

## Plan

1. **Placeholders.** Find the kit's placeholders still left (an uppercase name between double
   braces, in files and folder names). Until the package and distribution names are filled
   nothing installs, so search for them with the editor's or the agent's search tool (or
   `git grep -n "{{"` after `git init`); once the package installs, `uv run poe docs` reports
   each one left as DOC-PLACEHOLDER. Propose values from the owner's idea, ask the owner to
   confirm them, and fill every one. The installer leaves none, and the gate is green from the
   start.
2. **The idea.** Write [DESCRIPTION.md](../../project/DESCRIPTION.md) with the owner: ask,
   draft, and revise until they approve it. Record their words in the decision log, dated.
3. **Layers and stack: a proposal first.** Propose the layers (what each owns, what each may
   import, which libraries each owns) and the stack (the product libraries beside the default
   tooling), with objections, and change nothing until the owner approves. Then update
   `harness.toml`, ARCHITECTURE.md, the decisions, and the skeleton under `src/` and `tests/`
   together.
4. **The gate.** `uv lock`, `uv sync`, `uv run poe fmt`, then `uv run poe check` until it is
   green. Fix the environment, not the checks' expectations, unless a rule is wrong for this
   domain: then change the config, ARCHITECTURE.md, and a decision together.
5. **Optional docs.** Keep or drop SECURITY.md and evaluation.md with the owner (the kit's
   README says how to drop one cleanly).
6. **Version control and CI.** `git init`, the first commit, the remote, and a CI run of the
   gate.
7. **Next milestones.** Propose them from DESCRIPTION.md, depth-first: the first ones build
   what the later ones rely on (test data and fixtures, the trust boundary with adversarial
   tests if there is one, the measurement before the feature it measures). Record the owner's
   answer in the roadmap.
8. **Close.** Tick the criteria, set the Status line to completed with its date, move this file
   to `completed/`, update the roadmap's row, and open the first product plan.

## Progress log

- 2026-10-28: The harness kit was copied in. Nothing is verified yet.
- 2026-10-28: Steps 1 to 3 and 7 done as drafts, at the owner's request ("Do the files for the
  Harness (with description too, you know the idea already)"):
  - Placeholders filled: project "Ole5 Voice Agent", package `ole5_voice`, distribution
    `ole5-voice-agent`, settings prefix `OLE5_VOICE_`.
  - [DESCRIPTION.md](../../project/DESCRIPTION.md) drafted from the owner's messages, the
    prototype's logs, and the agent's architecture proposal, with the agent's parts marked.
  - The layers proposed and laid down: `harness.toml`, ARCHITECTURE.md, D-003, and one package
    per layer under `src/ole5_voice/`. The kit's status use case moved from its `services` layer
    to `api/status.py`, with its test.
  - The stack proposed (D-002); no product library installed yet.
  - [SECURITY.md](../../SECURITY.md) proposed (D-007) and
    [evaluation.md](../../design/evaluation.md) proposed (D-011).
  - The owner's decisions recorded as D-004 to D-006 and D-008 to D-010 (D-007 and D-011 are
    the agent's proposals), and their rule on timelines in WORKING-RULES.md.
  - The roadmap's milestones M1 to M7 proposed from the agent's architecture proposal, at the
    owner's request ("write your proposed design as milestones in the roadmap").
- 2026-10-28: Step 4 done: `uv lock --offline` and `uv sync --offline` (the kit's dependencies,
  from the local cache); `uv run --offline poe check` passes (103 tests, coverage 100%).
- 2026-10-28: Reviewed by three agents that did not write the files (harness consistency,
  design soundness, faithfulness to the owner), each finding re-checked by an agent told to
  refute it: 36 findings, several overlapping; 31 confirmed and fixed, 5 refuted. The main
  changes:
  - The Accepted entries were narrowed to the owner's words, and the agent's mechanisms moved
    into D-002 and D-003. Evaluation became its own proposal, D-011.
  - Invariant 1 now needs inputs only `voice` can build, and invariant 6 holds without a ticket
    lookup (an outbox).
  - M3 judges interruptions from Whisper on the overlap, since Groq has no partial transcripts.
  - M2 deploys the backend and tests the media path from other networks.
  - M6 counts calls against the Groq key's limits.
  - The rehearsal steps are written out in DESCRIPTION.md with their source.
- 2026-10-28: Waiting on the owner: approval of the description, the layers (D-003), the stack (D-002),
  SECURITY.md (D-007), evaluation.md (D-011), and the milestones; their review of
  WORKING-RULES.md; then step 6 (`git init`, the first commit, the remote, and CI), which needs
  the owner's go-ahead to commit.

- 2026-10-31: Step 6 begun at the owner's go-ahead ("Yes, init and commit"): `git init` and the
  first commit of the scaffold; the remote and CI wait for the owner. The project then became
  T2 Agentic Voice, a library and the Ole5 app built on it (D-013, plan 001): the package that
  criterion 3 speaks of is now the library's, `packages/t2-agentic-voice/src/t2_agentic_voice/`,
  and the description awaiting approval is the widened one.
- 2026-11-01: The owner approved the description, the layers (D-003), the stack (D-002),
  SECURITY.md (D-007), evaluation.md (D-011) and the milestones M1 to M7, with the package
  design as amended (D-017, plan 001). Two criteria stay open: CI, which waits for a remote
  (TD-001; the owner chose to start M1 first), and the owner's review of WORKING-RULES.md.

## Decision log

- 2026-10-28: The repository starts from a harness kit taken from an earlier project built
  the same way; the way of working is recorded in D-001.
- 2026-10-28: The layers and the stack were laid down in the files before the owner's approval,
  because the owner asked for the files; both stay `Proposed` until the owner approves (the
  agent's reading of "Explicit implementation requests run straight away" in WORKING-RULES.md).
- 2026-10-28: The kit's `docs/SECURITY.md` was missing although `harness.toml` requires it; it
  was written for this product rather than dropped, since the product has trust boundaries
  (D-007).

## The owner's decisions

All on 2026-10-28, in the owner's words:

- "I have created a fresh folder "Ole5-voice-agent" to start there without affecting Joori
  work, we will build our own Voice oriented agent, the chat is a not necessary (only a
  bonus)."
- "When it comes to profiles, lets not focus on it being in Saudi as long as we can swap it
  later, also I can not host anything other than the website itself, the backend and some
  small services."
- "Also for now I can only use the Groq API key, we can not try other models for now."
- "Lets not rely on the timeline you provided, we will rely on a plan and our own progress."
- "You can use the old (Jooris) repo to help you initiate the new one."
- "Lets use Phoenix Arize instead of LangFuse."
- "Handoff is only a ticket, there is no real call-center."
- "For Phase 0, I do not have the ability to gather data other than my own. I am the only one
  working in this repo."
- "in the new folder I have put some files to define how the Harness should Go and the dynamic
  of building this project."
- "Do the files for the Harness (with description too, you know the idea already)"
- "After Finishing with the Harness, write your proposed design as milestones in the roadmap."

On 2026-11-01, the owner's answers to the agent's questions:

- "Approve all": the stack (D-002), the layers (D-003), SECURITY.md (D-007), evaluation.md
  (D-011), DESCRIPTION.md, the roadmap's M1 to M7, and the package design as amended (D-017).
- "Start M1, CI later": M0 stays open only for CI, recorded as tech debt (TD-001).
