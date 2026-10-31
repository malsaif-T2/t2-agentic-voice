# 001 · T2 Agentic Voice: the library and the Ole5 app

Status: active · Milestone: M0 · Started: 2026-10-31

## Goal

Turn the Ole5 Voice Agent scaffold into **T2 Agentic Voice**: a workspace holding the library
teammates install and the Ole5 Voice Agent built on its public API, with a check that keeps the
app on that API. Then design the library from its users' side (what it provides, what an app
must provide, its public API, settings, testing kit and documentation) before features are
built on it, so every milestone builds library and app together.

## Acceptance criteria

- [x] One uv workspace: `packages/t2-agentic-voice` (the library), `apps/ole5-voice-agent` (the
  Ole5 app) and `examples/minimal` (the smallest app); `uv sync` installs all three, editable.
- [x] ARCH-PUBLIC: an app imports the library only through `[package] public` and no other app,
  and the library never imports an app; a layer never imports from the package root. Each rule
  has tests in `tests/harness/`.
- [x] Renamed: the project (T2 Agentic Voice), the library's package (`t2_agentic_voice`) and its
  settings prefix (`T2_AGENTIC_VOICE_`, then `T2V_` by D-018); the Ole5 app keeps its name and
  package (`ole5_voice`).
- [x] [DESCRIPTION.md](../../project/DESCRIPTION.md) widened to the library and its users,
  awaiting the owner's approval (plan 000).
- [ ] The package design ([package-design.md](../../design/package-design.md), D-017) is
  approved or changed by the owner.
- [x] The teammate guide's index, [docs/guide/](../../guide/README.md), lists its pages, each
  with its purpose and the milestone it lands with; each page is written when its part lands.
- [ ] The roadmap pairs each milestone's Ole5 work with the library work it needs, and the owner
  approves it.
- [x] `uv run poe check` passes, and the restructure is a commit of its own.

## Plan

1. **A safety net.** `git init` and a first commit of the scaffold as it was, before anything
   moves (the owner's go-ahead, 2026-10-31).
2. **The workspace.** Move the package to `packages/t2-agentic-voice/src/t2_agentic_voice/` and
   its tests to `tests/t2_agentic_voice/`; add the Ole5 app and the minimal example as members,
   each a small package built on the public API, with a test; make the root a workspace that is
   not a package itself.
3. **The rule.** Teach the harness the library's location (`[package] root`), its public API
   (`[package] public`) and the apps (`[[apps]]`), and enforce ARCH-PUBLIC, with tests.
4. **The names and the description.** Rename the project, the library and its settings prefix;
   widen DESCRIPTION.md, ARCHITECTURE.md, README.md and CLAUDE.md; record D-012 to D-016.
5. **The package design.** Design the library from its users' side: three teammate personas
   (a backend developer, the owner of an existing chat agent, the person who runs it), a survey
   of open-source building blocks, a study of the developer APIs of LiveKit Agents, Pipecat, the
   OpenAI Agents SDK and config-driven platforms, then one synthesis, two adversarial reviews
   (the developer's experience; architecture and safety) and a revision. The result is
   [package-design.md](../../design/package-design.md), proposed as D-017.
6. **The guide.** Lay out [docs/guide/](../../guide/README.md): one page per step of a
   teammate's journey, each saying what it will cover; pages fill as the library grows.
7. **The roadmap.** Re-plan the milestones so each pairs Ole5's work with the library work it
   needs, the optional thinker after M7 (D-015).
8. **Close.** The gate, the commit, and the owner's review of the design; then tick the
   criteria and move this plan to `completed/`.

## Progress log

- 2026-10-31: Steps 1 to 4 done.
  - `git init` and the first commit (the scaffold as it was, 68 files).
  - The workspace laid out; the library's package moved with its history (`git mv`); the Ole5
    app and the minimal example added, each with a test.
  - ARCH-PUBLIC added to `scripts/check_architecture.py`, with `[package] root` and `public`
    and `[[apps]]` in `scripts/harness_config.py`; `poe gc` and `poe quality` read the folders
    from the config instead of `src/`. New tests for each rule and each config error.
  - `uv lock --offline` and `uv sync --offline`; lint, types, arch and tests pass (111 tests,
    coverage 100%).
- 2026-10-31: Step 5 run as a workflow of nine agents (three personas, an open-source survey,
  an API study, a synthesis, two adversarial reviews, a revision); its result is
  [package-design.md](../../design/package-design.md), proposed as D-017. Its agents read
  package metadata and wheel contents on PyPI and Groq's public pages to check their facts; the
  repository was read from the first commit only. The agent then aligned its sections 12, 14 and
  16 with what steps 2 and 3 had built (one harness.toml with ARCH-PUBLIC instead of one per
  member, tests at the root, the guide in `docs/guide/`), and `poe fmt` formatted its Python
  samples.
- 2026-10-31: Steps 6 and 7 done: the guide's index, and the roadmap's *Library* line for each
  milestone, from the design's section 16, with the thinker under "Planned later". `uv run poe
  check` passes (111 tests, coverage 100%). Waiting on the owner: the design and its open
  questions, and the re-planned roadmap.
- 2026-11-01: The owner answered the design's 23 open questions with the agent, in six groups
  ordered by the milestone each blocks (D-018). The design, the roadmap (M2, M4, M5, M7 and its
  open questions), ARCHITECTURE.md's Pipecat convention, DESCRIPTION.md's handoff line, the
  guide's index and the settings prefix (`T2V_`, in `core/config.py` and `.env.example`) were
  changed to match. Waiting on the owner: approval of the design as amended and of the roadmap;
  T2's answer on its package index; the website team's answer on customer login.

## Decision log

- 2026-10-31: Tests stay in one `tests/` folder at the root, one subfolder per package, rather
  than inside each package: one gate and one coverage floor for all, and the harness's support
  folders stay as they were. Wheels never ship tests either way.
- 2026-10-31: The library's settings prefix is `T2_AGENTIC_VOICE_`, from its name, not an
  abbreviation a teammate would have to learn; whether an app may choose its own prefix is part
  of the package design.
- 2026-10-31: The `[[owners]]` rules stay the library's: an app has no layers, so they cannot
  apply as they are. An app that imports a provider's client directly is a review finding; the
  package design decides whether a rule is needed.
- 2026-10-31: The folder on disk keeps the name `Ole5-voice-agent`: the agent's sessions run
  inside it, so renaming it from inside a session would break that session. The owner renames
  it when no session is open in it (nothing in the repository depends on the folder's name).
- 2026-11-01: The owner's "one install" (the design's open question 2) is read as no extras at
  all, not only Pipecat in the base install: each extra the design listed (`[groq]`, `[server]`,
  `[phoenix]`, `[eval]`) held something a call or its tests need. The owner may still choose
  optional extras for the tracing exporter and the scorers.
- 2026-11-01: The open questions are answered, but the design as a whole stays Proposed (D-017)
  until the owner approves it as amended, so its criterion stays open.

## The owner's decisions

Between 2026-10-29 and 2026-10-31, in the owner's words, or their answers to the agent's
questions:

- "Yes Lets apply what we agreed on. We also need to rename the project to a more general name
  than "Ole5-voice-agent" and the description it is bigger than that now."
- "Also we need to determine how the teammates will be using the package? we need to imagine it
  from their side in how they can use it in their projects, and how to make it good for them.
  This requires our work to be highly modular, with settings they can change to fit them and
  documentation to show them how to use it. All of this while we make our "Ole5-voice-agent"
  because it is still required."
- The name: "T2 Agentic Voice".
- The repository: "One repo, two packages".
- The first way teammates use it: "Python library".
- Before the restructure: "Yes, init and commit".
- "for context: I presented the presentation and we are doing Approach 3 now. Also we could use
  open-source code and projects to help us accomplish ours. Also we need to determine what we
  provide for teammate developers and what we require for them, I mean we need to do the whole
  design of the package early."

On 2026-11-01, the answers to the design's open questions; D-018 lists every answer. The
owner's own words:

- The handoff: "if the agent has the ability to handoff, it should ask to confirm the action.
  otherwise it should clarify it can not do it. Or maybe offer a ticket instead. But in general
  is should ask to confirm."
- Teammates' audio sent to Groq: "Do not worry about this, I will explain this to anyone that
  wants to use the package. They also should know this by themselves because of the models they
  will need to use"
- Support for teammates: "I am not sure yet, we can think about this when we really build it
  and someone starts using it"
