# Design decisions

Append-only log. Each entry records the context, the decision, and its consequences. To change a
decision, add a new entry that supersedes the old one instead of editing it. Only the status in
an old entry's heading changes, to point at its successor.

Entries are history: milestone numbers inside them refer to the roadmap as it was when they were
written. The current plan is [roadmap.md](../plans/roadmap.md). Code cites decisions (`D-NNN`),
never milestone numbers, because milestones are renumbered when the roadmap is re-planned.

## The format

`uv run poe docs` reads each entry's heading (DOC-REGISTER: its shape, and no number used
twice; DOC-REF: every `D-NNN` cited anywhere is a heading here), so keep its shape:

```
## D-NNN · Title · YYYY-MM-DD · Status
```

- **Status** is `Proposed` (waiting for the owner), `Accepted`, `Rejected` (the owner turned
  it down; kept so it is not proposed again without new evidence), `Amended by D-NNN`, or
  `Superseded by D-NNN`. Anything may follow it, as in `Accepted (a setting; not the default)`.
  The check reads the number, the date's shape, and the status's first words; the title and
  the bullets are for the reader.
- **Bullets:** **Context** (what forced a choice), **Decision** (what was chosen, with the
  alternatives considered when they matter), **Consequences** (what follows, good and bad), and
  **Evidence** when a measurement or the owner's words decided it. The owner's words are quoted
  with their date; the agent's own reasoning is marked as its own.
- Changing an architecture rule means changing `harness.toml`, ARCHITECTURE.md, and recording
  why here, in the same commit. ARCH-DOC checks the first two agree; the entry here is a review.
- Before taking a number, check that no other session has claimed it (plans README, "How work
  moves"). DOC-REGISTER fails when two headings share a number.

## D-001 · Harness engineering as the way of working · 2026-10-28 · Accepted

- **Context:** Ole5 Voice Agent is built by an AI coding agent while the owner steers. Agents
  copy the patterns they find, and lose what lives only in chat, so the environment has to
  carry the rules.
- **Decision:**
  - The owner sets goals, acceptance criteria, and the harness's design, and judges outcomes;
    the agent writes all code, tests, docs, CI, and tooling
    ([PRINCIPLES](../harness/PRINCIPLES.md)).
  - The repository is the system of record. `CLAUDE.md` is a map, not a manual; durable
    knowledge lives under `docs/` and is reached by links.
  - Non-trivial work runs from an execution plan and lands in small, verified blocks
    ([plans](../plans/README.md)).
  - One gate, `uv run poe check` (lint, types, arch, docs, test), defines done, locally and in
    CI. Its rules live in one config file, `harness.toml`, which the checks read; every
    violation is printed with a FIX line.
  - Entropy is managed by [garbage-collection rounds](../harness/garbage-collection.md) and
    [quality grades](../harness/quality.md), which inform and never block.
  - A mistake seen twice becomes a check, test, or doc
    ([golden principles](../harness/golden-principles.md)).
  - The owner's working rules are in [WORKING-RULES.md](../../WORKING-RULES.md).
- **Consequences:** Every rule has a home and, where possible, a check. The harness itself is
  maintained like product code: its checks have tests, and changing a rule means changing its
  config, its doc, and a decision together.
- **Evidence:** the owner, 2026-10-28: "in the new folder I have put some files to define how
  the Harness should Go and the dynamic of building this project."

## D-002 · Technology stack · 2026-10-28 · Accepted (the owner, 2026-11-01; its Pipecat bullet amended by D-018, its tracing bullet by D-023, its loguru bullet by D-031)

- **Context:** The kit's default tooling is Python 3.12 with uv, poethepoet, ruff, mypy
  (strict), and pytest with coverage. The product needs real-time voice in a browser, from Groq
  only (D-004), on a host that runs only the website, the backend, and some small services
  (D-005), traced in Phoenix (D-008). [DESCRIPTION.md](../project/DESCRIPTION.md) has the idea.
- **Decision (proposed by the agent on 2026-10-28; Accepted when the owner approves):**
  - The kit's tooling, unchanged: Python 3.12 with uv; poethepoet as the task runner; ruff,
    mypy strict, pytest with a coverage floor; pydantic and pydantic-settings; structlog.
  - **Voice pipeline: Pipecat** (BSD-2), pinned to one version. Its peer-to-peer WebRTC
    transport runs inside the backend, so no media server is hosted (the agent's reading of
    D-005). Silero VAD and the Smart Turn end-of-turn model run in-process on the backend's
    CPU. The agent reads the owner's "we can not try other models for now" as hosted model
    providers: these two small models need no key and no server, and run only if the owner
    approves this entry.
  - Only Pipecat's pipeline, transport, and speech detection are used. Its provider services
    (its Groq speech-to-text, model, and text-to-speech services) are not: they would reach
    Groq without a port (GP-22). Our own Pipecat processors call the ports.
  - **HTTP:** FastAPI on uvicorn.
  - **Providers:** the `groq` SDK for speech-to-text (Whisper), the chat model, and
    text-to-speech (Orpheus), each wrapped in our own adapter (D-003, D-004).
  - **Knowledge base:** `qdrant-client` and `httpx` to T2's Qdrant and embedding gateway, with
    one embedding and one search per question. The agent recommends this over ragent2, the
    library the old repository uses: the prototype measured ragent2 at 20–45 s per answerable
    search and 33–84 s with no answer (Ole5-chatbot VOICE_LOG.md, D28). Using ragent2 instead
    is the owner's call (the roadmap's open questions).
  - **Tickets:** `httpx` to the T2 Ticket API, with a fake for tests.
  - **Tracing:** Arize Phoenix through `arize-phoenix-otel` and OpenInference (D-008), run as
    one of the small services (the agent's proposal; Arize also hosts Phoenix).
  - **Web widget:** plain HTML, JavaScript and CSS, with no build step.
  - None of the product libraries is installed yet: each is added with `uv add` by the plan
    that first uses it, and pinned. Pipecat logs through loguru; the plan that installs Pipecat
    routes loguru through `core/logging.py`, gives it to `core` in `[[owners]]`, and records why
    in a decision.
  - Alternatives considered (the agent's reading of the 28 Oct 2026 research, in the
    architecture proposal the agent drafted for the owner that day,
    [Ole5 Voice Agent Architecture](https://claude.ai/artifact/WVGaY7fH8mckPgGn45oMzJ), a
    Claude Docs document in the owner's account, outside the repository; the owner's messages
    of that day set aside its in-Kingdom profile, its self-hosted models, and its timeline):
    LiveKit Agents needs a LiveKit media server, one more service to host, and its best
    end-of-turn model runs on LiveKit's cloud; a hosted voice platform cannot use Groq alone;
    the prototype's own WebSocket pipeline had no cancellation and no WebRTC transport;
    LangGraph, which the old repository uses, is not needed for a talker with a few tools.
- **Consequences:** Every library is well known and inspectable. Each IO or framework library is
  owned by one layer (`harness.toml`, ARCHITECTURE.md). Pipecat's API changes often, so its
  version is pinned and an upgrade is a plan of its own. If the owner's host cannot open a UDP
  path to the backend, WebRTC needs a TURN service or another transport (the roadmap, M2).

## D-003 · Layered architecture, enforced from one config · 2026-10-28 · Accepted (the owner, 2026-11-01; its layers amended by D-019, how a provider is chosen by D-030)

- **Context:** Agents replicate existing patterns, so drift has to be prevented structurally
  rather than by instruction. The prototype's failures came from its structure: the voice code
  could not cancel the text agent's turn, and the model, not the code, wrote the ticket
  confirmation.
- **Decision (proposed by the agent on 2026-10-28; Accepted when the owner approves):**
  - Seven layers, written in `harness.toml` and explained in
    [ARCHITECTURE.md](../../ARCHITECTURE.md): `core`, `domain` (the call's rules and the ports,
    no IO), `adapters` (the outside services), `actions` (the backend that acts), `agent` (the
    talker), `voice` (the real-time pipeline), and `api` (HTTP and the composition root).
  - Every outside service is reached through a port in `domain` and an adapter in `adapters`,
    chosen by a setting: the agent's mechanism for the owner's condition that providers can be
    swapped later (D-004). `core` owns the tracing libraries (D-008).
  - `api` injects into the talker only the chat-model port and the tool runner of `actions`, so
    the talker acts only through a tool call. No import rule can enforce that, since the ports
    live in `domain`, which `agent` may import: it is a review, plus a test of `api`'s wiring
    added with the talker. `voice` reaches `actions` only through the talker's tool calls.
  - What only one layer may create goes into `[[restricted]]` in the commit that creates each
    class: a confirmed ticket draft (`domain`), the caller's heard words and the read-back
    receipt (`voice`), and a completed action (`actions`).
  - Alternatives considered: the kit's `core → domain → adapters → services → api`, with the
    talker and the backend in one `services` layer (rejected by the agent: it would let the
    talker reach the ticket system directly, the prototype's failure); a single `voice` layer
    holding the pipeline and the talker (rejected: the talker could then bypass `actions`).
  - A custom AST checker (`scripts/check_architecture.py`) enforces the layers instead of
    import-linter, because it also enforces non-import invariants (no `print`, no environment
    access outside the settings module, module size) and prints a FIX line with every
    violation.
- **Consequences:** `harness.toml` is the source of truth for the rules, and the checker has its
  own tests. A rule changes only with its config, ARCHITECTURE.md, and a decision together:
  ARCH-DOC fails until ARCHITECTURE.md's layer table matches `[layers]` and `[[owners]]`, and
  the decision is a review. More layers mean more wiring in `api`, accepted for the guarantee.

## D-004 · Groq is the only provider for now, and each can be swapped later · 2026-10-28 · Amended by D-100 (other providers measured, 2026-11-16)

- **Context:** The owner has one API key.
- **Decision:** Speech-to-text, the chat model, and text-to-speech come from Groq for now. Each
  must be swappable for another provider later, one hosted in Saudi Arabia included. How it is
  swapped (ports and adapters) is the agent's proposal in D-003.
- **Consequences:** Accuracy is bounded by Groq's models (Whisper for speech, Orpheus for the
  voice); the measurements say by how much. Groq's Whisper transcribes a finished recording and
  gives no partial transcripts, which shapes how interruptions are judged (the roadmap, M3).
- **Evidence:** the owner, 2026-10-28: "Also for now I can only use the Groq API key, we can
  not try other models for now", and "When it comes to profiles, lets not focus on it being in
  Saudi as long as we can swap it later".

## D-005 · Hosting: the website, the backend, and some small services · 2026-10-28 · Accepted

- **Context:** The owner's hosting limits.
- **Decision:** Only the website, the backend, and some small services are hosted (the owner's
  words). The agent's reading, proposed with D-002: no model servers, no GPUs, and no separate
  media server; the voice pipeline, speech detection, and the end-of-turn model run inside the
  backend; Phoenix runs as one of the small services.
- **Evidence:** the owner, 2026-10-28: "I can not host anything other than the website itself,
  the backend and some small services."

## D-006 · For Phase 0, the only data is the owner's own voice · 2026-10-28 · Accepted

- **Context:** Measuring speech-to-text and turn-taking needs recordings.
- **Decision:** For Phase 0, no recordings are gathered from anyone but the owner. While this
  holds, every number describes one speaker and is never reported as Saudi speakers in general.
  The agent reads Phase 0 as the measurement phase of its architecture proposal, now M1; when
  it ends, and whether other speakers can be recorded then, is an open question in the roadmap.
- **Evidence:** the owner, 2026-10-28: "For Phase 0, I do not have the ability to gather data
  other than my own. I am the only one working in this repo."

## D-007 · SECURITY.md: threat model and invariants · 2026-10-28 · Accepted (the owner, 2026-11-01; its invariants 7 and 8 amended by D-035)

- **Context:** The product has trust boundaries: callers who must not reach each other's
  tickets, a model whose output is untrusted, a ticket system it writes to, and secrets in the
  backend.
- **Decision (proposed by the agent; the owner keeps or drops it in plan 000):**
  [SECURITY.md](../SECURITY.md) records the threat model and the invariants, each with the test
  that enforces it.
- **Consequences:** Every change at a boundary ships with adversarial tests (GP-08).

## D-008 · Arize Phoenix for traces · 2026-10-28 · Accepted

- **Context:** Calls must be inspectable turn by turn to find and measure failures.
- **Decision:** Every call is traced in Arize Phoenix. Where Phoenix runs, and which layer owns
  the tracing libraries, are the agent's proposals in D-002 and D-003.
- **Evidence:** the owner, 2026-10-28: "Lets use Phoenix Arize instead of LangFuse."

## D-009 · A handoff is a ticket; typed chat is a bonus · 2026-10-28 · Accepted

- **Context:** There is no call center to transfer a call to.
- **Decision:** A handoff creates a ticket for support staff; there is no live transfer. Typed
  chat in the widget is optional. The agent's design, proposed with the roadmap: one handoff
  ticket per call, with the call's summary; the agent gives its number from the ticket system's
  reply and never says a person is joining.
- **Evidence:** the owner, 2026-10-28: "Handoff is only a ticket, there is no real
  call-center", and "we will build our own Voice oriented agent, the chat is a not necessary
  (only a bonus)".

## D-010 · The Ole5 chatbot repository is a read-only source · 2026-10-28 · Accepted

- **Context:** Joori's Ole5 chatbot repository holds working code for the T2 Ticket API, the
  knowledge base, and the prototype's voice rules, and the prototype's recordings sit beside it.
- **Decision:** This repository may port code from it, rewritten to this repository's layers
  and checks, with the source file named in the porting plan. Nothing in it is edited,
  committed, or run in a way that writes into it, and its recordings are read, never changed.
- **Consequences:** No shared code or package between the two repositories; a fix in one is not
  a fix in the other.
- **Evidence:** the owner, 2026-10-28, on the fresh folder "Ole5-voice-agent": "to start there
  without affecting Joori work", and "You can use the old (Jooris) repo to help you initiate the
  new one."

## D-011 · evaluation.md adopted: a golden set from the owner's recordings, and simulated calls · 2026-10-28 · Accepted (the owner, 2026-11-01)

- **Context:** Speech-to-text accuracy, turn-taking, and the talker's answers vary from run to
  run and cannot be settled by one assertion; the prototype's failures were found only by
  rehearsals.
- **Decision (proposed by the agent on 2026-10-28; the owner keeps or drops evaluation.md in
  plan 000):** [evaluation.md](evaluation.md) is adopted. Its golden set holds new recordings of
  the owner on each target device, and the 124 talk-over segments the owner recorded for the
  prototype on the laptop speakers (Ole5-chatbot VOICE_LOG.md, 2026-10-27 23:50), within the
  data limit of D-006. Simulated calls cover the talker and the backend.
- **Consequences:** The measurement is built before the features it measures (the roadmap, M1).
  Every result describes the owner's voice only, while D-006 holds.

## D-012 · Approach 3: a dedicated voice agent · 2026-10-31 · Accepted

- **Context:** The owner presented three ways to bring voice to Ole5 to their manager: a
  dictation and read-aloud button in the chat, the hybrid voice shell around the chat agent
  (the October prototype), and a dedicated, speech-first voice agent (this repository).
- **Decision:** Approach 3, the dedicated voice agent. The owner, on 2026-10-31: "I presented
  the presentation and we are doing Approach 3 now."
- **Consequences:** This repository is the voice product; the prototype's voice mode in the Ole5
  chatbot repository stays as it is, read-only to us (D-010). What the prototype taught (its
  recordings, word lists, voices and the rehearsal script) carries over.

## D-013 · T2 Agentic Voice: a shared library and the Ole5 app in one workspace · 2026-10-31 · Accepted (its settings prefix amended by D-018)

- **Context:** The owner widened the project: teammates should be able to reuse this work to add
  voice to their own products, while the Ole5 Voice Agent is still required. The owner, on
  2026-10-31: "We also need to rename the project to a more general name than
  "Ole5-voice-agent" and the description it is bigger than that now", and "we need to imagine
  it from their side in how they can use it in their projects, and how to make it good for
  them. This requires our work to be highly modular, with settings they can change to fit them
  and documentation to show them how to use it. All of this while we make our
  "Ole5-voice-agent" because it is still required."
- **Decision:** The project is named **T2 Agentic Voice** (the owner's answer, 2026-10-31). One
  repository, a uv workspace of two packages (the owner chose "One repo, two packages" over one
  package with use-case folders and over two repositories):
  - the library teammates install: `packages/t2-agentic-voice`, distribution
    `t2-agentic-voice`, import `t2_agentic_voice`, settings prefix `T2_AGENTIC_VOICE_` for now
    (D-017, open question 4); its layers are those of D-003;
  - the Ole5 Voice Agent: `apps/ole5-voice-agent`, import `ole5_voice`, built only on the
    library's public API, exactly as a teammate's app would be;
  - `examples/minimal`: the smallest app, the guide's quickstart and a test that the library
    works without any Ole5 code.
  The agent's mechanism: the library's public API is its package root, which re-exports what
  apps use (`[package] public` in harness.toml). ARCH-PUBLIC fails an app that imports anything
  else from the library, or another app, and fails the library if it imports an app; a layer
  may not import from the package root. Tests stay in one `tests/` folder at the root, one
  subfolder per package, under one gate.
- **Consequences:** Ole5 proves the public API as it is built, and the minimal example catches a
  library change that quietly depends on Ole5. Every name an app needs must be exported from the
  package root, or the module made public with a decision. The [[owners]] rules apply to the
  library's layers, not to apps (an app has no layers), so an app that imports a provider's
  client directly is caught only in review. The folder on disk keeps its old name until the owner
  renames it, since the agent's sessions run inside it. The package design that decides what the
  library provides and requires is D-017.

## D-014 · Teammates use the library from Python first · 2026-10-31 · Accepted

- **Context:** A teammate could use the library several ways: as a Python library, through a
  drop-in web widget, as a server configured by a file with no Python, or by plugging in their
  own agent over HTTP.
- **Decision:** The first version supports the Python library only (the owner's answer,
  2026-10-31, from those four options). The others are later options.
- **Consequences:** The library's public API is Python. The browser widget is built for the Ole5
  app; making it a drop-in for teammates is a later decision, as are the config-only server and
  the HTTP agent mode.

## D-015 · The thinker is optional and off by default · 2026-10-31 · Accepted

- **Context:** The agent proposed, on 2026-10-29, the pattern of Decagon Voice 3 and Sierra's
  Tandem Voice: the fast talker may hand a complex task to a slower reasoning agent (the
  thinker) that works in the background, a dedicated one or a chat agent behind an adapter.
- **Decision:** The owner, on 2026-10-29: "Also make the thinker optional and not required."
  The agent's mechanism: a setting chooses the thinker, and the default is none. With none, the
  talker is never offered the tool; with one, the thinker never acts (it may only propose an
  action, which still goes through the yes rule), each task has a time budget, and a result that
  arrives after the caller moved on is dropped.
- **Consequences:** Nothing up to the rehearsal depends on it: it is planned after M7. The
  knowledge answers of M4 stay one search per question.

## D-016 · Open-source code and projects may be used · 2026-10-31 · Accepted

- **Context:** Much of a voice agent exists as open source: pipelines, transports, speech and
  turn detection, client SDKs, evaluation tools.
- **Decision:** The owner, on 2026-10-31: "Also we could use open-source code and projects to
  help us accomplish ours." The agent's proposal for how: a permissive licence (MIT, BSD,
  Apache-2.0) is used as a dependency through `uv add`; code copied into the repository keeps
  its licence notice and names its source; a copyleft licence (GPL, AGPL) needs the owner's
  approval first, since teammates' products would inherit it. Each new dependency is recorded in
  the plan that adds it.
- **Consequences:** Which projects to build on is part of the package design (D-017), including
  whether Pipecat's own provider services may be used (ARCHITECTURE.md says today they are not).

## D-017 · The package design: what the library provides, and what an app provides · 2026-10-31 · Accepted (the owner, 2026-11-01, as amended by D-018)

- **Context:** The owner, on 2026-10-31: "we need to determine what we provide for teammate
  developers and what we require for them, I mean we need to do the whole design of the
  package early."
- **Decision (proposed by the agent on 2026-10-31; the owner approves, changes or rejects it in
  plan 001):** [package-design.md](package-design.md). It was written by a workflow of nine
  agents: three teammate personas (assumptions, not interviews), a survey of open-source building
  blocks, a study of the developer APIs of LiveKit Agents, Pipecat, the OpenAI Agents SDK and
  config-driven platforms, one synthesis, two adversarial reviews, and a revision. In short:
  - a team declares a use case (`VoiceAgent`: instructions, languages, `@tool` read tools and
    `@action` actions with read-back, done and claim templates) and runs it with
    `VoiceRuntime`, as a sidecar process or mounted in a one-worker app;
  - the library enforces the security invariants for every action at runtime: consent from
    heard words after a played read-back, no claim without a record, identity from a signed
    single-use join token, parsed model output, an outbox for writes;
  - a team must bring a Python 3.12 process, its tools and actions, an identity source, a Groq
    key, a page, a media path (UDP or TURN), durable storage, an `env`, and its data and
    consent decisions; everything else has a default;
  - a testing kit (`TextCall`, fakes, `ActionSafetySuite`) runs with no key and no Pipecat;
  - Pipecat is wrapped behind a new `media` layer, with only its STT and TTS base classes used;
  - twenty-three open questions, each with options and a recommendation.
- **Consequences:** Until it is approved, nothing in it is built beyond plan 001's workspace and
  ARCH-PUBLIC. Several parts would amend recorded decisions (D-002's Pipecat bullet, D-003's
  layers, D-007's register, GP-22's wording); its section 16.3 lists the entries to write. The
  settings prefix of the scaffold (`T2_AGENTIC_VOICE_`, D-013) is interim until its open
  question 4 is answered.

## D-018 · The owner's answers to the package design's open questions · 2026-11-01 · Accepted (its answer to open question 2, one install, amended by D-086 for the `ecapa` extra)

- **Context:** The package design (D-017) ended with 23 open questions, each with options and
  the agent's recommendation. The owner went through them with the agent on 2026-11-01, in six
  groups ordered by the milestone each blocks. Section 17 of
  [package-design.md](package-design.md) gives each question, its options, and the answer.
- **Decision:** The owner's answers, by the design's question number:
  - The agent's recommendation, taken:
    - 1: our own thin browser client `t2v-client.js` and protocol `t2v/1`, provisional;
    - 3: Python 3.12 as the floor;
    - 4: the settings prefix `T2V_`, with `from_env(prefix=...)` for a team's own;
    - 5: one process per `var_dir`, with SQLite stores;
    - 7: our own spans, in OpenInference's format;
    - 8: Pipecat's STT and TTS base classes wrapped; its model services and its interruptions
      not used;
    - 9: T2's package index if it exists, otherwise git tags on a mirror repository;
    - 12: Chrome and Edge supported, Firefox and Safari best effort;
    - 13: the repository renamed `t2-agentic-voice` before the first teammate install;
    - 16: the thinker after M7, an LLM thinker on Groq first, then a LangGraph adapter;
    - 17: M4's background troubleshooting moved to the thinker work;
    - 18: join tokens as compact JWTs, HS256 only;
    - 20: the licence list of the design's section 13;
    - 21: the key's real limits read in M2, Groq asked to raise them if they are low, and
      repeated phrases cached;
    - 22: the sidecar by default; the mount for one-worker apps and demos.
  - Chosen otherwise:
    - 2: one install. The library always brings Pipecat and everything a call needs: there are
      no extras and no `media` layer, and Pipecat stays in `voice`;
    - 11: one shared Groq key; each app sets its share of the key's limits;
    - 15: versions stay `0.x`, with no date for 1.0;
    - 23: the contract is fixed at M0, not provisional; a later change is the owner's decision.
  - In the owner's own words:
    - 6, the handoff and invariant 1: "if the agent has the ability to handoff, it should ask to
      confirm the action. otherwise it should clarify it can not do it. Or maybe offer a ticket
      instead. But in general is should ask to confirm." So invariant 1 is unchanged: a handoff
      is an action like any other, read back and done only after a clear yes, and an app with no
      handoff action says it cannot hand the call over and may offer a ticket instead;
    - 10, teammates' audio sent to Groq: "Do not worry about this, I will explain this to anyone
      that wants to use the package. They also should know this by themselves because of the
      models they will need to use". So the contract asks for no Zero Data Retention setting and
      no data controller's sign-off;
    - 14, support for teammates: "I am not sure yet, we can think about this when we really
      build it and someone starts using it".
  - Not known yet: 19, how Ole5's website proves who the customer is. The owner asks the website
    team whether customers log in.
- **Consequences:**
  - The library's settings prefix is `T2V_` from this entry (it was `T2_AGENTIC_VOICE_`, D-013).
  - D-002's bullet that Pipecat's provider services are never used is amended: `voice` builds
    on Pipecat's STT and TTS base classes, which call our ports, while Pipecat's ready-made
    provider services, its model services and its interruptions stay unused. ARCHITECTURE.md's
    conventions say so.
  - The design was changed to match: no extras, no `media` layer, no `HeardRequest`, the
    contract fixed at M0, one shared key, `0.x`. The roadmap's M4 and M5 changed with it; M5's
    rehearsal step now reads: «أبغى موظف» over an answer starts the handoff's read-back, and the
    ticket is made after a clear yes.
  - The agent read "one install" as no extras at all (plan 001's decision log); the owner may
    still choose optional extras for the tracing exporter and the scorers.
  - Still open: the design as a whole (D-017) awaits the owner's approval as amended; question 9
    waits on whether T2's package index exists, 19 on the website team, and 14 until someone
    starts using the library. The owner renames the folder when no session runs inside it.
- **Evidence:** the owner's answers on 2026-11-01, to questions and options the agent wrote; the
  three quoted above are the owner's own words.

## D-019 · The library's `testing` layer · 2026-11-01 · Accepted (the owner, 2026-11-01, as the design's 12.2; one bullet Proposed)

- **Context:** The package design (D-017, as amended by D-018) makes a testing kit part of the
  contract: the fakes of every port, text-mode calls, the adversarial suite, simulated callers
  and the evaluation scorers ([package-design.md](package-design.md), sections 9 and 12.2). Its
  code must sit inside a layer, and a team's tests must not need the HTTP stack. Its first part,
  the scorers `wer` and `cer` on jiwer, is built by plan 002, so the layer comes now. D-003 has
  seven layers; this entry amends it.
- **Decision** (as the design's 12.2 describes it):
  - An eighth layer, `testing`, may import `core`, `domain`, `actions`, `agent` and `voice`; it
    never imports `adapters`, so a test reaches a provider only through a port it passes in, nor
    `api`. `api` may import it, as it imports every layer.
  - `testing` is the only layer that may import `jiwer` (`[[owners]]`).
  - `harness.toml` and [ARCHITECTURE.md](../../ARCHITECTURE.md) say so together (ARCH-DOC
    compares them), and CLAUDE.md's code map has its line.
  - Alternative considered (plan 002's decision log): our own edit distance in `domain`, like
    the prototype's `lev`, with no new layer; set aside by the agent because GP-10 prefers a
    well-known library, and the testing kit needs the layer anyway.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on): the layer joins
    `[package] public` (its modules become public) in the plan that builds the testing kit's
    fakes and `TextCall`. Until then it holds only the scorers, which an app reaches through the
    `evals` facade at the package root, so none of its modules is public yet.
- **Consequences:** The library has eight layers. jiwer stays out of the layers a call runs
  through. When the testing kit lands, the parts that run Pipecat (`AudioCall`, the design's
  12.2) stay in modules of their own inside `testing`, as `voice` keeps Pipecat's.
- **Evidence:** the owner, 2026-11-01: "Approve all", for the package design as amended (plan
  000); and, on whether that covers the entries recording what the design describes, "Yes, as
  Accepted", with the agent's note that anything beyond the design is written as Proposed (plan
  002, Q3).

## D-020 · The harness checks ARCH-FACADE and ARCH-WORDS · 2026-11-01 · Accepted (the owner, 2026-11-01, as the design's 12.4; one bullet Proposed)

- **Context:** The design puts the library's public modules at the package root as thin
  facades that only re-export names (its 5.3), where the harness allowed only `__init__.py`.
  Its 12.4 adds two checks with the first facade: ARCH-FACADE, each module listed in
  `[package] facades` holds only imports and `__all__`; and ARCH-WORDS, the library's `src/`
  holds no app name (`ole5`, `otrs`, `ds.t2.sa`), in any case, which answers the fear that the
  library is shaped by one app underneath.
- **Decision** (as the design's 12.4 describes it):
  - `[package] facades` in `harness.toml` names the facades. `scripts/harness_config.py` checks
    that each sits directly under the package root, is in `[package] public`, does not take a
    layer's name, and has its module file. A facade is checked as the package root is: it may
    import every layer, and ARCH-OWNER still applies to it. No layer imports a facade
    (ARCH-LAYER), as no layer imports the package root.
  - ARCH-FACADE (`scripts/arch_facade.py`): a facade holds its docstring, its imports and one
    `__all__`, a list or tuple of string literals, and nothing else.
  - ARCH-WORDS (`scripts/arch_words.py`): no word of `[package] banned_words` (`ole5`, `otrs`,
    `ds.t2.sa`) in the library's `src/`, in any case, inside longer words too.
  - ARCH-PUBLIC treats `from t2_agentic_voice import <facade>` as an import of that module, as
    it already treated a layer's name; ARCH-PUBLIC itself moved into `scripts/arch_public.py`, so
    `scripts/check_architecture.py` stays under ARCH-SIZE.
  - Not built here: ARCH-BAN, one configuration per member, and one invariants register, which
    the design's 12.4 also lists; each lands with the plan that needs it.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on): the key's name,
    `banned_words` (the design names none); the files whose text ARCH-WORDS reads (`*.py`,
    `*.md`, `*.toml`, `*.json`, `*.txt`, `*.js`, `*.html`, `*.css`), and the path below
    `[package] root` of every file there, whatever its type, so a module, folder or asset named
    after an app is caught too; and what it skips: `__pycache__/` and the folders above
    `[package] root`, since a bytecode file holds its module's absolute path and the owner's
    checkout sits in a folder named `OTRS-voice-agent`.
- **Consequences:** A public name lives in the layer that owns it, under that layer's rules, and
  a facade says only which names are public. A banned word that is not an app's name changes
  `banned_words` with a decision. The facades themselves, and the names each holds, are recorded
  with the first facades.
- **Evidence:** as for D-019: the owner's "Approve all" and "Yes, as Accepted" (plan 002, Q3),
  2026-11-01.

## D-021 · The first public facades, and their stability · 2026-11-01 · Accepted (the owner, 2026-11-01, as the design's 5.1 and 5.3; one bullet Proposed)

- **Context:** The design lists the library's public modules, each with a stability level (its
  5.1, with the levels' rules in 5.4), and makes each public module at the package root a thin
  facade (its 5.3; ARCH-FACADE, D-020). Plan 002 builds the first names behind five of them.
- **Decision** (as the design's 5.1, 5.3 and 5.4 describe it):
  - `t2_agentic_voice.ports`, stable: `SpeechToText`, `AudioClip`, `Transcript` and `DataFlow`
    now; the other ports of 5.1 join it with the plans that build them.
  - `t2_agentic_voice.groq`, stable: `GroqSTT` now; `GroqChat` and `GroqTTS` later.
  - `t2_agentic_voice.languages`, provisional: `normalize_arabic`, `normalize_digits` and the
    spelling-guide check now; the presets and the speaking functions later.
  - `t2_agentic_voice.evals`, provisional: `wer`, `cer`, `term_recall`, `id_recall`,
    `silence_output` and `sign_test`.
  - `t2_agentic_voice.tracing`, provisional: tracing set up from settings, its span helpers,
    and `Redactor`; the Saudi PII patterns later.
  - Each is in `[package] public` and `[package] facades`, and re-exports names that live in the
    layers (`domain`, `adapters`, `testing`, `core`); a layer never imports a facade.
  - The package root also exports `ProviderError(kind, retryable, retry_after_s)`, one of 5.1's
    errors, which every port raises on a provider's failure (the design's 6.1).
  - A stable module follows SemVer and the deprecation policy; a provisional one may change in
    any minor release, with the change in the changelog (5.4). A public signature names no type
    from `groq` (5.3), which `GroqSTT`'s tests check.
  - `Transcript` carries an optional `no_speech_prob`, Whisper's own estimate that a clip holds
    no speech: the owner's ruling (plan 002, Q2), beyond the design's 6.1.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on): the public names
    the design does not name, each the type or entry point of a function it does name: in
    `languages`, `spelling_issues`, `SpellingRule` and `SpellingIssue` (the spelling-guide check
    and its data); in `evals`, `Recall` (what `term_recall` and `id_recall` return); in
    `tracing`, `Tracing` (the set-up, holding the span helpers) and `SpeechToTextSpan`. And, on
    the stable `ports` types, beyond the design's 6.1: `AudioClip.seconds`, a read-only property
    giving the clip's length (`len(pcm16) / 2 / sample_rate`); and their input checks, each
    refusing a value as it is built: no unknown field on `DataFlow`, `AudioClip` or
    `Transcript`, `pcm16` holding whole 16-bit samples (an even number of bytes), `sample_rate`
    above 0, `billed_seconds` 0 or more, and `no_speech_prob` from 0 to 1 (GP-06: relaxing a
    check later breaks no caller, while adding one later might).
- **Consequences:** An app imports these modules by name (`from t2_agentic_voice.ports import
  Transcript`), as ARCH-PUBLIC allows; the package root keeps the stable names of 5.1 that
  exist so far. Moving a name from provisional to stable is a decision of its own, once a
  second team has used it (5.4).
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01; and, for `no_speech_prob`, the
  owner's "Keep it" (plan 002, Q2), 2026-11-01.

## D-022 · Evaluation: the scorers in the library, the golden-set runner in the app, no audio in git · 2026-11-01 · Accepted (the owner, 2026-11-01, as the design's 9.7 and 12.1; one bullet Proposed)

- **Context:** D-011 adopted [evaluation.md](evaluation.md). The package design splits it
  between the library and its apps (its 9.7 and 12.1): every team needs the scorers, while a
  golden set is one team's data. Plan 002 builds both halves for Ole5. This entry follows up
  D-011, as the design's 16.3 lists it.
- **Decision** (as the design's 9.7 and 12.1 describe it):
  - The library holds the scorers, ported from the prototype's (D-010): the canonical Arabic
    normalizer and digit normalization in `languages`; `wer` and `cer` after that normalization
    (on jiwer, in `testing`, D-019), `term_recall`, `id_recall`, `silence_output` and
    `sign_test` in `evals` (D-021). Their pure parts sit in `domain`.
  - Ole5's golden-set machinery stays in the app, with its poe tasks: `poe golden`, `poe eval`
    and `poe eval-compare`, item validation, the frozen answers, the splits, held-out
    aggregates and `history.jsonl`, as evaluation.md defines them. A `t2v eval` command comes
    when a second team records a golden set.
  - Golden data stays in each team's repository, and its audio stays out of git: Ole5's keeps
    only items, references, manifests and file hashes, and the audio lives under the
    git-ignored `var/` or in a private store. Every number says "one speaker" while D-006 holds.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 002's decision
    log has the reasons): the app's evaluation code in
    `apps/ole5-voice-agent/src/ole5_voice/evals/`, inside the app's package, where the gate
    lints, types and covers it, and its tests in `tests/ole5_voice/evals/`, while its data
    stays in `apps/ole5-voice-agent/evals/`; and the check that no audio is committed as a test
    inside `poe check`, failing on an audio file under `apps/`, `packages/`, `examples/`,
    `docs/` or `tests/` (the design's 12.4: a CI check, under `apps/`), since CI waits for a
    remote (TD-001).
- **Consequences:** A second team scores its own golden set with the same functions, and the
  guide's `evaluation.md` says how. The library publishes no golden data.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01.

## D-023 · Tracing: plain OTLP through the OpenTelemetry SDK, to Phoenix by default · 2026-11-01 · Accepted (the owner, 2026-11-01, as the design's 10.1; one bullet Proposed)

- **Context:** D-002's tracing bullet reads "Arize Phoenix through `arize-phoenix-otel` and
  OpenInference (D-008)". The package design, approved as amended (D-017), puts the
  OpenTelemetry API, SDK and OTLP exporter in the library's one install and sends plain OTLP to
  Phoenix by default (its 10.1). D-018 settled the tracing path the design left open (its
  question 7): our own spans, in OpenInference's format, rather than an instrumentor or
  Pipecat's tracing. D-018 names no package or exporter and leaves D-002's bullet as it was, so
  this entry amends that bullet.
- **Decision** (as the design's 10.1 describes it, with D-018's answer):
  - The library depends on `opentelemetry-api`, `opentelemetry-sdk` and
    `opentelemetry-exporter-otlp-proto-http`, and on `openinference-semantic-conventions` for
    the attribute names only, all owned by `core`. Not `arize-phoenix-otel`, and no
    instrumentor: `openinference-instrumentation-pipecat` is not used (D-018).
  - It uses the team's `TracerProvider` if given, otherwise a private one built from
    `tracing.endpoint`. It never calls `set_tracer_provider` and never instruments another
    library.
  - Plain OTLP over HTTP goes to Phoenix by default, or to any OpenTelemetry backend the team
    points it at.
  - Phoenix is run, never imported, outside the library's install (Elastic License 2.0, D-018).
  - The spans, their attributes, the redaction hook, what is never exported (audio, secrets),
    the bounded export queue and the explicit parent spans are the design's 10.1.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on): nothing the
    OpenTelemetry SDK or exporter would read from an `OTEL_*` variable is left to them: each
    such value is passed explicitly, and any they read whatever is passed is listed as debt.
    This applies the design's 7.3 ("Other names are never read") to the tracing packages; plan
    002's decision log lists the variables of the installed 1.45.2. To that end the library also
    depends directly on `requests` (Apache-2.0, already locked under the exporter), owned by
    `core` through its own `[[owners]]` row and used only for the `requests.Session` given to the
    OTLP exporter: passing one is the only way to keep
    `OTEL_PYTHON_EXPORTER_OTLP_HTTP_CREDENTIAL_PROVIDER` out (plan 002's decision log).
- **Consequences:** D-002's heading points here. A team that already traces passes its own
  provider and gets the library's spans in its own backend. The owner runs Phoenix on the same
  machine, bound to 127.0.0.1 (plan 002, "What the owner does").
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01; D-018, question 7.

## D-024 · The speech-to-text noise on the golden set's dev split · 2026-11-02 · Accepted (the registered measurement, plan 002)

- **Context:** evaluation.md's "Noise" measures how much one run differs from an identical one
  before anything is tuned, so a later change is read against it. Plan 002 registered two
  identical dev runs per model and the smallest change one run can detect (its "The noise").
- **Decision** (the measured numbers, as registered): with each arm's settings as plan 002
  registers them (Groq, `language` from the item's label, no prompt, temperature 0,
  `verbose_json`), at the measurement commit 1c3c4dc on 2026-11-01:
  - `whisper-large-v3`, R1 against R3: 0 of 231 variants changed their verdict, 0 of 66 items
    better or worse (p = 1.0).
  - `whisper-large-v3-turbo`, R2 against R4: 0 of 231 variants, 0 of 66 items (p = 1.0).
  - So d = 0 for each model, and the smallest change one run can detect is c = 6 items
    (b = 6, w = 0 gives p = 2/64 = 0.031 by the sign test; b = 5 gives 0.0625).
- **Consequences:** a change to these arms that moves fewer than 6 of the dev split's 66 items
  cannot be told from the noise with one run; a change is judged by the sign test by item with
  this floor. The noise was measured on one evening with one key (TD-032): one run is one
  sample, and repeated runs, on other days, are the lasting fix. Both runs of each model were
  identical, so the comparison of the models (D-025) is not held back by the noise.
- **Evidence:** the history lines of R1 to R4 (`apps/ole5-voice-agent/evals/history.jsonl`) and
  `poe eval-compare` of R1 with R3 and of R2 with R4 (plan 002's progress log, 2026-11-02).

## D-025 · `stt.model` stays `whisper-large-v3` · 2026-11-02 · Accepted (the registered rule, plan 002)

- **Context:** plan 002 registered the keep or reject rule for `stt.model` before any run:
  turbo becomes the default only if it is better beyond the noise in both comparisons with no
  language or device stratum worse; large-v3 stays if large-v3 is better beyond the noise in
  both (its "The keep and reject rule for `stt.model`").
- **Decision:** the default stays `whisper-large-v3`, in `core/config.py` and `.env.example`,
  where it already was, so no file changes. On the dev split (66 items, 231 variants), turbo
  against large-v3, R2 against R1: 2 items better and 18 worse, p = 0.0004, beyond the noise
  (D-024) in large-v3's favour; the replication, R4 against R3, gives the same (2 and 18,
  p = 0.0004). Exact match 0.303 for turbo against 0.429 for large-v3, WER 0.360 against 0.250.
  The stratum guard reads turbo worse beyond the noise on Saudi Arabic (2 better, 12 worse,
  p = 0.0129), on the laptop (3 and 16, p = 0.0044) and on the wired headset (1 and 8,
  p = 0.0391); the other strata are too small to guard.
- **Consequences:** turbo's lower price ($0.04 an hour against $0.111) does not buy its loss on
  Arabic. Every number describes one speaker, the owner (D-006). A later model or setting is
  judged against large-v3 on this set, by the same rule.
- **Evidence:** R1 to R4's history lines and `eval-compare` (plan 002's progress log,
  2026-11-02).

## D-026 · The library's base error is `T2VoiceError` · 2026-11-02 · Accepted (the owner, 2026-11-02)

- **Context:** the design's 5.1 names `T2VoiceError` among the package root's errors (D-017), but
  Block 0 of plan 002 built the base error as `AppError`, the kit's name, and TD-007 recorded the
  gap. Nothing has been tagged or installed outside this repository, so renaming costs least now.
- **Decision:** the base error is `T2VoiceError` (`core/errors.py`), and every subclass and use
  follows. The package root exports it in place of `AppError`, which still works until the next
  minor release: reading `t2_agentic_voice.AppError` raises a `DeprecationWarning` and returns
  `T2VoiceError`, as the design's 5.4 asks of a name changed before 1.0 where it is cheap.
- **Consequences:** an app catches `T2VoiceError`; `AppError` is removed in the release after the
  first one a teammate installs, with a "Removed" changelog entry. TD-007 is paid.
- **Evidence:** the owner's answer in garbage collection round 1 (plan 004's decision log,
  2026-11-02): "Rename it now (Recommended)".

## D-027 · The harness checks ARCH-DEPS and DOC-SAMPLE · 2026-11-02 · Accepted (the owner, 2026-11-02, plan 003)

- **Context:** code imported a library that only another package brought, four times (requests
  and httpx in the library, pydantic in the app, coverage in `scripts/`; plan 004's deb6 and
  lib18). The guide promises that its samples come from tested files, and nothing checked it
  (plan 004's deb3). garbage-collection.md's step 5 makes a mistake seen twice into a check;
  this entry records why the round added these two, which it built before the owner ruled.
- **Decision:**
  - ARCH-DEPS (`scripts/arch_deps.py`, from `poe arch`): every outside module the code imports
    is declared by the code's own project: for a member's `src/`, the member's
    `pyproject.toml`; for `scripts/` and `tests/`, the root's dependencies or `dev` group, or a
    member's. A module maps to its distributions through the installed environment, on its
    top-level name, so a namespace package is covered by any one of its distributions. A module
    that does not parse is left to ARCH-PARSE.
  - DOC-SAMPLE (`scripts/doc_samples.py`, from `poe docs`): a fenced block that follows a link
    to a `.py` file, with no other fence between them, is a run of that file's lines,
    indentation aside and blank lines left out, with nothing elided. History is not read.
- **Consequences:** a dependency is added with `uv add` in the member whose code imports it. A
  guide's sample is copied again when its source changes. The other distributions of a
  namespace package are not checked (TD-036). ARCHITECTURE.md's enforcement list names both,
  and GP-24 and GP-09 cite them.
- **Evidence:** plan 004's inventory (deb3, deb6, lib18) and its decision log. The rules' tests
  are `tests/harness/test_arch_deps.py` and `tests/harness/test_doc_samples.py`. Written as
  Proposed; on 2026-11-02 the owner, asked to approve plan 003 with the agent's message saying
  that approval would cover this entry: "Yes go with the recommended" (plan 003, "The owner's
  decisions").

## D-028 · Settings: precedence, the prefix and a required `env` · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 7.2 to 7.5 and 7.7; one bullet Proposed)

- **Context:** the package design (D-017) makes the library's settings one `VoiceSettings`,
  layered with a fixed precedence, read from the environment only inside `from_env()`, under a
  prefix that belongs to the library alone, with a required `env` (its 7.2 to 7.5); its 16.3
  lists this entry. M1 built `Settings` on pydantic-settings, read through a `get_settings()`
  singleton, with no `env`. Plan 003's step 7 rebuilt it for M2; the fixes after the review of
  plan 003's Block 0 (2026-11-03) changed how a failure reads, how a group given in code meets
  the environment's, and several bounds; the check of those fixes (2026-11-03) made built
  settings read-only, checked a group given in code again, and brought every file and JSON
  failure into the one error, all written below.
- **Decision** (as the design's 7.2 to 7.5 and 7.7 describe it):
  - **Precedence**, from lowest to highest: the defaults; a `.env` file, only when
    `from_env(env_file=...)` names one; the environment variables under the prefix, read only
    inside `VoiceSettings.from_env()`; code arguments. `VoiceSettings(env=..., ...)` built in
    code takes its defaults and its arguments and reads nothing. There is no settings
    singleton: `Settings` and `get_settings` are gone, with no alias, and a module receives a
    `VoiceSettings`. The design's TOML file (its 7.2, layer 2) and per-call options (layer 6)
    are not built in M2.
  - **The prefix** is `T2V_` (D-018, question 4); a team picks its own with
    `from_env(prefix=...)`. Groups nest with `__` (`T2V_GROQ__API_KEY`). A variable that carries
    the prefix but names no setting is a `ConfigurationError` naming it, never its value, since
    the prefix belongs to the library's settings alone; `from_env(unknown="warn")` logs it and
    leaves it out. No other name is read: a provider's own variable (`GROQ_API_KEY`) is noted
    by its name only, so the error can say which name to set instead.
  - **`env` is required:** `dev`, `test`, `staging` or `prod`, with no default. Outside `dev`,
    `server.dev_page` and `logging.content` are refused, and `router()` and `serve()` refuse
    `test`, so typed consent never reaches a served runtime.
  - Each secret is a `SecretStr` with a `_file` form (`groq.api_key_file`, `join.keys_file`,
    `server.turn_secret_file`). Every failure is a `ConfigurationError` with a FIX line, a
    secret file that cannot be read included (check the file and that this process may read
    it, or save it as UTF-8 text), and never holds the value it refused (GP-19); a change to
    built settings is no load, and raises a TypeError (the Proposed bullets). A command writes
    the settings reference and `.env.example` from the model, each with a test that fails when
    it is stale.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log has the reasons):
    - `from_env(prefix=, env_file=, unknown=, **values)`: code values ride in `**values`, above
      the environment and the file as the design's 7.2 orders its layers, though its signature
      lists only the first three; the Ole5 eval commands pass `env="dev"` so. A group given as
      a dict merges into what the environment and the file gave for that group, key by key,
      while a group object (`server=ServerSettings(...)`) replaces its group whole, being
      complete in itself. `VoiceSettings` is a frozen pydantic `BaseModel` that refuses extra
      keys, not a `BaseSettings`, so settings built in code cannot read anything; `from_env`
      reads `os.environ` itself, only the names under the prefix, in any case, and refuses two
      names in one source that differ only in case (GP-06). Set aside: `BaseSettings` with a
      loader subclass, under which an unknown name inside a group still fails with
      `unknown="warn"`; and a dict that replaces its group, which silently dropped the
      environment's other keys of that group.
    - How a failure reads: every failure of one load, in code (the constructor,
      `model_validate`, `model_validate_json`) as through `from_env`, is one
      `ConfigurationError` that names each failing setting under the prefix (its details
      `{"settings": [{"setting": ..., "problem": ...}]}`), with a FIX line that says where to
      correct them (the code that builds the settings; or the environment, the `.env` file or
      the code values given), and nothing chained, so no traceback leads back to a value. A
      join key or TURN secret too short is named with the rest, and so are a value `from_env`
      reads that is not JSON and a name set twice, each named once, its values left out; so is
      a `tracing.redact` pattern Python's `re` cannot compile, whatever error `re` raises (an
      overflow or a recursion among them), named by its place in the list, never with `re`'s
      text, which may quote it. Text given to `model_validate_json` that is not JSON (cut
      short, nested too deep, not UTF-8) is the same one error, naming "the settings" (not
      valid JSON). A `.env` whose text is not UTF-8, one holding a NUL included (UTF-16 written
      with no byte-order mark), is refused with "save it as UTF-8 text", and one that cannot be
      opened or read with "check that the file exists and that this process may read it",
      each showing none of its bytes; a secret file is refused the same way. An environment
      check names its one setting, and runs only on a load nothing else failed. A group built
      on its own (`JoinSettings(...)`) raises pydantic's `ValidationError`, its input hidden.
      Set aside: pydantic's `ValidationError` for settings built in code, which a team
      catching `ConfigurationError` for its FIX line would miss; `json.loads` before
      validating, which would validate in Python mode, not JSON mode; and `from_env` raising
      the problems it finds before validating, which dropped every other failing setting.
    - The reference is `docs/generated/settings.md`, where GP-11 puts generated docs with their
      freshness tests, not the design's 7.7 path (`docs/guide/reference/settings.md`);
      `uv run poe settings-ref` writes it and `.env.example`. Each group is a module of its own
      under `core/settings/` (ARCH-SIZE).
    - A blank value counts as unset under any name, so a `.env` copied from M1's
      `.env.example`, which left every key blank, keeps every default. M1's names
      (`T2V_VAR_DIR`, `T2V_LOG_LEVEL`, `T2V_LOG_FORMAT`) set to a value are refused, each with
      the name to use now.
    - `staging` holds every check `prod` holds, and both refuse `logging.level` DEBUG, which
      the design's 7.4 gives only Ole5's own status check; the checks run at every load, again
      in `status()`, and when a `VoiceRuntime` is built (plan 003's Track F), since a copy made
      with `model_copy(update=...)` skips validation.
    - A join key and the TURN secret hold at least 32 bytes of printable ASCII with no space
      (for the join keys, RFC 7518's 3.2 on HS256): refused at load when given inline, and when
      resolved when given in a file, since loading the settings reads no file. The join key
      file is one JSON object from key ID to secret, and a key ID matches
      `^[A-Za-z0-9._-]{1,64}$`.
    - `core.config.foreign_set(names)` says which of the named variables, ones the library
      never reads as settings, are set to a value, by name only, however the settings were
      built: `voice`, which reads no variable (ARCH-ENV), asks it, to refuse
      `PIPECAT_SETUP_FILES` and `PIPECAT_SMART_TURN_LOG_DATA` at start. An empty value counts as
      unset there too, so an empty `GROQ_API_KEY` is not noted.
    - The keys beyond the design's 7.6: `stt.live_language` (`session`, the call's language,
      until plan 003's runs R5 to R7 set it by their registered rule, GP-18; or `auto`); the
      `session` group, whose one key, `mode` (`echo`, its only value), is the owner's answer to
      plan 003's Q3 (D-033), so only its place outside 7.6's table is the agent's;
      `tts.trim_silence` (false: Orpheus's audio is kept as it comes);
      `server.forwarded_allow_ips` (empty, bounded below: D-029); `server.turn_secret_file` (the
      `_file` form the design's 7.3 asks of each secret); the `turns` keys `vad_min_volume`,
      `smart_turn_stop_ms`, `smart_turn_pre_speech_ms` and `smart_turn_max_duration_s`, at
      Pipecat's own defaults, the starting values of plan 003's decision log, none tuned in M2;
      and `logging.level` and `logging.format`, M1's top-level `log_level` and `log_format`
      moved into the group.
    - The map settings, `join.keys` and `tts.languages`, are read-only once loaded: a mapping
      nothing can change, dumped as a plain object, which a copy and a pickle keep, so no key
      or voice reaches a call that no check saw. A read-only map hashes as its entries do, so
      a frozen group that holds one hashes. Built settings refuse every change: assigning to,
      or deleting, a field of `VoiceSettings` or of any group raises a TypeError of fixed text
      that names `<Class>.<field>` and says settings are read-only once built, never the value
      (`core/settings/base.py`'s `ReadOnlyModel`), where pydantic's own frozen error shows the
      value assigned, a key among them. A group object given to `VoiceSettings`, one made with
      `model_copy(update=...)` included, is validated again (`revalidate_instances`), so its
      checks run and its maps become read-only, and the settings hold a new object, not the
      one given; `VoiceSettings` is not, so a copy of it made with an update still skips
      validation, and the environment checks run again (above). Set aside: naming the
      variable under the prefix, which a group cannot know, built alone or held in a map.
    - The values nobody gave, the agent's: `tts.timeout_s` 6, as `stt.timeout_s`; the limits
      in seconds as numbers; a voice name matching `^[a-z][a-z0-9_-]{0,31}$`;
      `server.ice_servers` as `stun:`, `turn:` or `turns:` URLs with no credentials; each of
      `server.allowed_origins` a scheme, a host and a port only, in the form a browser's
      `Origin` header takes (the scheme in lowercase; the host a name of lowercase letters,
      digits and hyphens between dots, a name in another script in its `xn--` form, a
      dotted-quad IPv4 address with no shorthand, or a bracketed IPv6 address in the short
      form a browser writes, never with a dotted part or a zone; no `:443` for https or `:80`
      for http), any other form, a percent-escape, a backslash or a control character among
      them, refused with a FIX that states the rule and never repeats the value (set aside:
      any address Python parses, which CORS, comparing text, would never match);
      `server.turn_ttl_s` 3600, refused above 86400 (plan 003's criterion);
      `join.max_clock_skew_s` at most 60, since a token verifies until its expiry plus the
      allowance (invariant 7); and each of `server.forwarded_allow_ips` an address or a network
      in its network form (`10.0.0.0/24`; `10.0.0.1/24`, which uvicorn would never match, is
      refused with a FIX naming that form), no wider than /8 for IPv4 or /32 for IPv6, no
      wider than /104 where it overlaps an IPv6 range that carries IPv4 addresses
      (`::ffff:0:0/96`; SIIT's `::ffff:0:0:0/96`; NAT64's `64:ff9b::/96` and its local-use
      `64:ff9b:1::/48`, RFC 8215; and `::/96`), and no wider than /24 where it overlaps 6to4's
      `2002::/16`: a wider entry trusts nearly every peer's `X-Forwarded-For`, as `*` does,
      which is refused too. Each refusal says why, true of its entry, and states the whole
      rule, as the setting's description does (one text, `_PROXY_RULE`, which a test reads
      back against the ranges).
- **Consequences:** a teammate's process keeps its own variables: the library reads only the
  names under its prefix, and a `.env` only when given one. A `.env` written for M1 says which
  names to change. An app sets one key of a group in code without losing the environment's
  others, or builds a typed group from the package root (D-032). Comparing an M1 run with a new
  one lists `logging.level` and `logging.format` (TD-026). `limits.max_call_s` (600) and
  `limits.idle_s` (120) come before M6 by the owner's answer to plan 003's Q4, and the voices
  `abdullah` and `troy` by its Q5. What `from_env` learned, its prefix among it, lives in private
  attributes that a dump drops (TD-041). The design's 7.6 notes the keys built beyond its table.
- **Evidence:** the owner's "Approve all" and "Yes, as Accepted" (plan 002, Q3), 2026-11-01;
  for plan 003's Q3 to Q5, the owner's answer of 2026-11-02, "Yes go with the recommended."
  (plan 003, "The owner's decisions"). The tests: `tests/t2_agentic_voice/core/test_config.py`,
  `test_settings_errors.py`, `test_settings_checks.py`, `test_settings_secrets.py`,
  `test_settings_read_only.py` and `test_settings_ref.py`, and
  `tests/harness/test_isolation.py`.

## D-029 · Serving and identity: the sidecar and the mount, one process per `var_dir`, signed join tokens, the offer secret · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 4.5, 5.2, 5.5, 6.5, 7.4 and 11; its Proposed bullet accepted by the owner on 2026-11-04, plan 003)

- **Context:** the design gives a team two ways to serve calls, the sidecar by default and the
  mount for one-worker apps (its 4.5; D-018, question 22); one process per `var_dir`
  (question 5); a caller's identity and consent from a signed, single-use join token (its 6.5;
  question 18); and the call's set-up over HTTP (its 5.5). Its 16.3 lists this entry, with
  Ole5's identity answer (its open question 19), which the owner has not given yet. Plan 003's
  Block 0 laid down the signatures, the identity port and the HTTP bodies; its Tracks C and F
  build them. The fixes after Block 0's review (2026-11-03) gave the HTTP routes their one error
  body and their byte caps; the check of those fixes (2026-11-03) added the one media type a
  route takes, a version check that any client reaches, a code for a candidates `PATCH` before
  the offer, a lifetime for the router's records of its calls, and the bound the used-token
  store keeps a token by, all written below.
- **Decision** (as the design's 4.5, 5.2, 5.5, 6.5, 7.4 and 11 describe it):
  - **The sidecar and the mount.** `serve(factory)` (and `t2v serve`) runs one runtime in a
    process of its own, with one worker. `app.include_router(runtime.router(), prefix=...)`
    mounts it in a one-worker app: the router carries the runtime's lifespan, which FastAPI
    merges, and `combine_lifespans` serves a mount as a sub-application. Every route answers
    "runtime not started" while the lifespan has not run. CORS answers only
    `server.allowed_origins`; in the mount, the app's own CORS middleware answers, and the
    router says so at startup.
  - **One process per `var_dir`.** The runtime's lifespan takes an exclusive lock file under
    `storage.var_dir`, so a second process on the same folder is refused with a FIX line: the
    used-token store is a local SQLite file there, which a second process would break
    (invariant 7).
  - **One identity source.** `VoiceRuntime(identity=...)` takes exactly one `IdentityVerifier`:
    `SignedJoinTokens`, or `DevIdentity`, which serves only `env` dev and loopback clients
    (`Authenticate` waits on the design's open question 19). `router()` and `serve()` refuse a
    runtime with none, and `env` test, each with a FIX line; `t2v dev` alone falls back to
    `DevIdentity`, with a warning.
  - **The join token** is a compact JWT, HS256 only, with no algorithm negotiation. Its claims
    are `sub`, `name`, `locale`, `attrs`, `consent` (`version`, `record_audio`), `jti`, `iat`
    and `exp`, with a `kid` header; any key of the `join.keys` map verifies, and
    `join.current_kid`'s signs; it lives `join.ttl_s` (60 s by default, 120 s at most) within a
    clock-skew allowance, `join.max_clock_skew_s`, and the `UsedTokens` store refuses its `jti`
    a second time. It is signed, not encrypted, so its claims hold no secret.
  - **The offer secret.** `/join` consumes the token once and answers the call's ID, an offer
    secret (random, for this call only), the ICE servers (with per-call TURN credentials when a
    TURN secret is set, inline or in its file) and the protocol version. `POST /offer` and
    `PATCH /offer` both need the call's offer secret, which stops working when the call ends or
    ICE completes; a second offer gets 409; no client's `pc_id` reaches Pipecat. The call ID is
    no credential. The offer secret is never logged, traced or put in an event, and goes only
    to the browser that joined.
  - **Consent in the token.** The caller's consent (`version`, `record_audio`) is carried only
    in the signed join token: no client message sets it, or the caller's identity. With
    `privacy.consent_version` set, `/join` refuses a token whose consent version differs, and
    the version is stamped on the call's report and traces.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log and its appendix, "Block 0's reading of the installed packages", have the reasons):
    - The identity port's method is `verify(token, *, join: JoinContext) -> (Caller, Consent)`,
      `JoinContext` holding `env`, the client's address and the runtime's used-token store: a
      verifier is built in the team's code with no IO, while the store is opened in the
      lifespan under `var_dir`. The design's 6.5 has `verify(token)`. `UsedTokens` is async,
      `use(token_id, *, expires_at) -> bool` giving exactly one True to two joins of one token,
      with `aclose()` (D-036). Its `expires_at` is the last instant any verifier could still
      accept the token, its `exp` plus `MAX_CLOCK_SKEW_S` (60 s, the bound on
      `join.max_clock_skew_s`), never `exp` alone nor `exp` plus the allowance configured, so a
      store that prunes at it never lets a token start a second call, after a restart with a
      larger allowance included; and `use()` gives False, recording nothing, for an
      `expires_at` that is not after the store's own now, since a token past its last instant
      is never a first use. Track C's tests: a token replayed after the store pruned it at its
      `exp`; one used under a 30 s allowance, the store reopened, and replayed at its `exp`
      plus 45 s to a verifier allowed 60 s; a use 1 ms late; and two replays on either side of
      the store's clock. `SignedJoinTokens` refuses at construction a `ttl_s` over 120 or a
      `max_clock_skew_s` over 60, as the settings do, since it takes both directly.
      `DevIdentity` refuses any `env` but dev before it reads the client's address, and always
      returns `Consent(version=None, record_audio=False)`.
    - `/join` compares with `privacy.consent_version` only a `SignedConsent`'s version
      (D-035): a plain `Consent` never lets audio be kept, so its version is not compared, and
      `DevIdentity` joins still work in `dev` with the setting given. Plan 003's Track F builds
      the check, after `verify`.
    - Every join key holds at least 32 bytes, refused at verify too, with PyJWT's
      `enforce_minimum_key_length` on for encode and decode (RFC 7518's 3.2). The claims are
      parsed strictly: `record_audio` a JSON boolean, the consent version
      `privacy.consent_version`'s own pattern; a `Caller`'s subject, name and attribute values
      are printable text of at most 256 characters, its locale a BCP 47 tag of at most 35, and
      it holds at most 16 attributes.
    - The offer secret rides in the `X-T2V-Offer-Secret` header or the body's `offer_secret`,
      never in a URL, which logs and traces keep. A `PATCH` with the call's own secret before
      `voice` answered the call's offer (not yet, or refused), after ICE completed or after the
      call ended gets a quiet 409 (`not_offered`, `ice_completed`, `call_ended`), logged at
      DEBUG with no value, which the client ignores once connected; a client sends its
      candidates only once `POST /offer` has answered. `voice` forgets a call once it has ended
      and its peer has closed, and `api` keeps its own record of the calls it joined, so a call
      `voice` has forgotten still gets `call_ended`. `api` drops a record a bounded time later,
      on the runtime's clock (a private `_clock`, `SYSTEM_CLOCK` unless a test gives one, which
      the runtime passes to its calls): a join never offered once its join token's window has
      passed, `join.ttl_s` plus twice `join.max_clock_skew_s` after the join, the longest a
      token valid at the join can still verify, since the router cannot read the token's
      `exp`; and an answered call `FORGOTTEN_KEPT_S` (60 s, the integrator's ruling) after
      `voice` forgets it, counted from the router's first sweep that finds its `phase` None,
      the sweep's period Track F's to set and record, well under that. A request for a call
      whose record was dropped gets 403 `forbidden`, as for a call never joined, so the
      records stay bounded by one token window's joins and the calls `voice` holds. Set aside:
      `voice` keeping ended calls for a fixed lifetime of its own; a callback from `voice` as
      it forgets a call, which changes Track E's contract and `FakeCalls`; and sweeping only on
      requests, under which a record outlives the 60 s when no request comes. `voice` keeps
      Pipecat's `pc_id` behind the call ID and never passes a client's.
    - Each `t2v/1` route first answers a `Content-Type` other than `application/json` with 415
      `unsupported_media_type` before it reads a byte, a parameter such as `charset=utf-8`
      allowed and none at all refused (`is_json` in `api/protocol.py`), since a page on any
      origin may send a form or `text/plain` with no CORS preflight, and a JSON body never goes
      without one. It reads its own body, never past its route's cap in bytes (twice the
      longest values its body holds, plus 4 KiB; `BODIES` in `api/protocol.py`): twice, since
      every field the caps count takes printable ASCII alone, the SDP tabs and line breaks too
      (`OfferRequest.sdp`'s pattern), which JSON writes in two bytes a character at most. A
      `Content-Length` over the cap is refused before a byte is read, and a body that streams
      past it is refused at the cap, each 413 `too_large`, so no body is buffered whole on the
      event loop that paces every call's audio. It parses the body with the model's
      `model_validate_json`, strictly, and answers a refusal with `refusal()`: 400
      `invalid_request`, naming pydantic's error types only. No route declares a model as a
      FastAPI body parameter, since FastAPI's own 422 sends the error's `errors()` back, with
      the token, the offer secret or a candidate's address in it, and in the mount the app's
      handler would answer it.
    - Every refusal and failure of a `t2v/1` route, a crash included, answers one `ErrorBody`
      (`code`, `message`, `notice`, `reference`): a code from a closed list of twelve
      (`invalid_request`, `too_large`, `unsupported_media_type`, `protocol_mismatch`,
      `join_rejected`, `forbidden`, `already_offered`, `not_offered`, `ice_completed`,
      `call_ended`, `not_started`, `internal_error`), a message safe to show that holds no
      value the request sent, a `notice` with `protocol_mismatch` alone (the design's 5.4),
      and a random reference the router logs with the refusal (GP-19). The statuses: 400
      (`invalid_request`, and on `/join` `protocol_mismatch`); 403 (`join_rejected` on
      `/join`; `forbidden` on `/offer` for a secret that is missing, wrong or not this call's,
      a call whose record the router dropped included); 409 (`already_offered` on
      `POST /offer`, which the call's own secret also gets after ICE completed or the call
      ended; on `PATCH` the quiet `not_offered`, `ice_completed` and `call_ended`), so the
      call's own secret never gets 403 while the router holds the call's record; and on every
      route 413 `too_large`, 415 `unsupported_media_type`, 500 `internal_error` and 503
      `not_started`. A success is 200, 200 and 204 (`PATCH` answers no body). No 404 on a
      `t2v/1` route: the secret is checked first, so an unknown call gets 403, and no answer
      shows whether a call exists; 400, not 422, since the router parses, not FastAPI.
      `GET /dev` is no `t2v/1` route: mounted only with `env` dev, it answers a client that is
      not loopback with the server's plain 404, as for a path it does not have. `/join` reads
      the body's top-level `protocol` alone, leniently, before the strict parse and before it
      verifies the token (`version_mismatch` in `api/protocol.py`, through the strict parse's
      own JSON reader, so a key held twice, a byte-order mark or text after the object reads
      the same both times): any value there but the JSON integer 1 (a string, a float, a
      boolean or null among them) gets 400 `protocol_mismatch` with its notice, whatever else
      the body holds, and spends no token, so the stable version check (the design's 5.4)
      reaches a client of any version; a body with no `protocol`, or that is no JSON object,
      goes on to the strict parse. The notice is `MISMATCH_NOTICE`, Modern Standard Arabic and
      English in one text, since a body of another version is read for nothing that names the
      caller's language: the agent's words, for the owner to change (GP-16). A response's
      secrets (the offer secret, a TURN password) are revealed only as it is serialized to
      JSON, as it is sent, never in a python-mode dump or a repr. Set aside: FastAPI's
      `{"detail": ...}`, which carries no code or reference; a nested `{"error": {...}}`;
      `json.loads` for the version check, which takes a body with a byte-order mark that the
      strict parse refuses; and the notice in English alone, or as a new notice kind of the
      declaration, which every preset would have to give.
    - FastAPI's own telemetry is off in both shapes: `serve()` builds its app with `telemetry`
      tracing, metrics and logs off and `auto_configure` false, and an app that mounts the
      router does the same itself (the Ole5 app's server does; `serving.md` tells a team), since
      a mounted router cannot reach the app's object and the library instruments no other
      library (D-023). `serve()`'s CORS lists `POST` and `PATCH` as its methods and
      `content-type` and `X-T2V-Offer-Secret` as its headers, so a page on a listed origin
      passes the preflight either header asks for. uvicorn runs with one worker, no access log,
      no server header, no `env_file` and `log_config=None`, and with proxy headers off while
      `server.forwarded_allow_ips` is empty, trusting them from those addresses alone otherwise
      (`*`, and a network wider than D-028's bounds, refused): uvicorn's own defaults trust
      127.0.0.1 and ::1, so any local client could set its address. `t2v dev` binds 127.0.0.1.
      On Windows, uvicorn runs on a selector event loop (whether a running server takes it is
      UNVERIFIED until Track F runs one), and each peer's close is bounded by a timeout.
    - For its tests, `VoiceRuntime` takes a private, keyword-only `_calls` factory (`VoiceCalls`
      unless given; in no facade), and `VoiceCalls` zero-argument factories for each call's
      speech detector and turn analyzer (Silero and Smart Turn v3.2 from `turns` unless given),
      called once per call, since each of Pipecat's analyzers keeps one stream's state and its
      public constructor loads its own ONNX session, and typed with Pipecat's classes under
      `TYPE_CHECKING` only, so no Pipecat loads at import. So `start` imports onnxruntime and
      warms one pair, the default factories load each model again per call (the review's probe
      on the owner's machine: 85.2 to 102.3 ms for Silero and 106.6 to 134.2 ms for Smart Turn
      after the warm-up), and `VoiceCalls` calls each factory off the event loop
      (`asyncio.to_thread`) before it answers the offer, so no live call's audio waits on a
      join. Track F's tests give `FakeCalls`, and step 16's test a fake speech detector.
    - In M2 the Ole5 app mounts the router in its own FastAPI app, beside its token route
      (behind the owner's access code: plan 003's Q4) and its widget's files, rather than run
      the sidecar, which is its shape once its website mints the tokens (the design's open
      question 19); `examples/minimal` uses `serve()`.
- **Consequences:** a team that runs several workers or replicas runs the sidecar, and a second
  process on one `var_dir` fails at its start rather than share single-use tokens. A team's
  website mints tokens with any JWT library from the documented claims (`serving.md`), and a
  browser client reads one error body on every `t2v/1` route. Until the design's open question
  19 is answered, Ole5's callers get their tokens from the app's own access-code route. The
  media path (UDP, TURN or another transport) is decided by plan 003's network test, in an
  entry of its own.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01; D-018, questions 5, 18 and 22; for
  plan 003's Q4, the owner's answer of 2026-11-02, "Yes go with the recommended." (plan 003,
  "The owner's decisions"). The spike on this machine (plan 003's appendix, step 5): on the
  proactor event loop, 2 or 3 of 16 call closes hung, against 0 of 16 on a selector loop. The
  tests of the bodies and the error body: `tests/t2_agentic_voice/api/test_protocol.py`,
  `test_protocol_caps.py` and `tests/t2_agentic_voice/test_protocol_list.py`, against the
  `t2v/1` fixture; of the used-token bound, `tests/t2_agentic_voice/domain/test_identity_port.py`;
  of the runtime's private calls and clock, `tests/t2_agentic_voice/api/test_runtime.py`.

## D-030 · GP-22: a provider is swapped by a setting, or by passing an adapter object in code · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 6.1 and 16.3)

- **Context:** GP-22 says every outside service is reached through a port and an adapter,
  "chosen by a setting, so a provider is swapped by configuration" (D-004; the mechanism is
  D-003's). The design's 6.1 lets a team pass any other adapter as an object in code, with no
  registry and no discovery through entry points, and says that goes beyond GP-22's "by
  configuration", so it needs an entry (its 16.3). M2 builds the first place it happens:
  `Providers` and `VoiceRuntime(providers=...)`, through which `examples/minimal` and plan
  003's integration test pass fake providers.
- **Decision:** GP-22 reads "swapped by a setting, or by passing an adapter object in code". A
  setting (`stt.provider`, `tts.provider`) picks among the library's own adapters
  (`Providers.from_settings`); any other adapter is an object that implements the port, passed
  in code (`Providers.from_settings(settings).replace(stt=...)`). There is no registry and no
  discovery. The ports stay in `domain` and the library's own adapters in `adapters`, where
  ARCH-OWNER keeps each service's client.
- **Consequences:** GP-22's row says so, and this entry amends D-003's bullet on how a provider
  is chosen. A team's own adapter lives in the team's code, outside the library's layers,
  where only review sees it (D-013); the guide's `providers.md`, planned for M4, says how to
  write one. An adapter passed in code is still the port's, so the design's rules for every
  port (cancellation, failures as `ProviderError`) apply to it.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01.

## D-031 · The library's logging, and Pipecat's loguru · 2026-11-02 · Accepted (the owner, 2026-11-02; `logging.pipecat = "forward"` waits for plan 003's Q19; one bullet Proposed)

- **Context:** the design's 3.3 and 10.2 have the library log on the standard library under
  `t2_agentic_voice`, with a `NullHandler`, configuring nothing until an app does, and with no
  call content at INFO and above; M1's logging did not meet that (plan 004's read). D-002's
  bullet on loguru said the plan that installs Pipecat routes loguru through `core/logging.py`
  and gives it to `core`, while the design's 12.2 (its change 3) gives it to `voice`, which
  switches one namespace off; plan 003 asked the owner which (its Q2). Pipecat logs through
  loguru, one logger for the whole process, and its debug lines hold what the caller said
  (plan 003's appendix, step 4, bullet 2).
- **Decision** (the owner's answers, and the design's 10.2):
  - The library's own logging is the design's: its loggers sit under `t2_agentic_voice` on the
    standard library, with a `NullHandler`, never calling `basicConfig` or adding a handler to
    the root logger; an event is a snake_case name with key-value fields, in the call shape
    `get_logger` already had (`log.info("event_name", key=value)`); and INFO and above carry no
    call content, which appears only at DEBUG with `logging.content`, which only `dev` allows.
  - `voice` owns loguru (`[[owners]]`), as Q2's (a) settled it: it switches Pipecat's namespace
    off with `logger.disable("pipecat")` before it first imports any Pipecat module, transitive
    ones included, so Pipecat's import banner never prints, and again at runtime start; `off`
    is `logging.pipecat`'s default, and no sink is added or removed. Pipecat's error frames and
    its transport and ICE failures become library log lines with no call content, and
    `TransportFailed` or `ProviderFailed` events. Plan 003's Track E builds it.
  - `logging.pipecat = "forward"` is not built: plan 003's Q19, asked of the owner on
    2026-11-02, is open. Q2's (a) also said that `forward` re-enables the namespace and
    forwards Pipecat's WARNING and above to `t2_agentic_voice.pipecat`, no sink added or
    removed, which cannot hold: a namespace switched off reaches no sink
    (`loguru/_logger.py`, line 1995), so `forward` must add a forwarding sink, and loguru's
    default sink, which prints to the screen, would then print every Pipecat DEBUG line unless
    it is removed. Q19's options: (a) `forward` adds a sink that forwards WARNING and above with
    the record's level and module but never its text, and removes loguru's default sink if it
    is still installed; (b) M2 builds only `off`, and `forward` waits for a team that asks,
    built then as (a), the agent's recommendation; (c) `forward` leaves the sinks alone, set
    aside because the default sink would print call content (invariant 8). Until the owner
    answers, `logging.pipecat` takes `off` alone, any other value refused at load; `off`
    behaves as Q2 settled it whatever the answer.
  - This amends D-002's loguru bullet: loguru is `voice`'s, not `core`'s, and Pipecat's lines
    are switched off, not routed through `core/logging.py`.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log has the reasons): `configure_logging(level, fmt, *, stream=None, loggers=(),
    content=False)`, a helper an app calls, which the design's 10.2 does not name: it puts one
    handler on `t2_agentic_voice` and on each logger it names, replacing the one an earlier
    call put, writing to the stream it is given or else to the standard output of the moment,
    and leaves the root logger and `propagate` alone; unless `content` is on, it holds
    aiortc's and aioice's loggers at WARNING (`hold_transport_loggers()`, which `voice` calls
    at start too), since their lower lines hold SDP and IP addresses. The design's 10.2
    key-value `extra` fields travel in one `extra` key, `fields` (`record.fields`), since a
    `LogRecord` refuses an extra key named like one of its own attributes and the Ole5 app's
    events use `name` and `message`; a field named like a line's own key or a structlog
    directive (`event`, `level`, `timestamp`, `logger`, `logger_name`, `exception`,
    `exc_info`, `stack`, `stack_info`, `_record`, `_from_structlog`) is written as
    `field_<name>`, with one more `field_` while that name is taken, so a log call never
    raises, loses no value, and adds no traceback (set aside: refusing the name, and dropping
    it). Nor can it forge a console line: on the console a field's key or value is written as
    its text's repr, on the line, when that text (a str's, or another object's `str()`) or its
    repr holds a control character (an escape among them), a format character, a line or
    paragraph separator, or a lone surrogate, which no UTF-8 stream writes; an escaped key
    that another field holds takes one more `field_`; the line's own keys are left alone, and
    the JSON format is unchanged (set aside: escaping all that `str.isprintable` refuses,
    which would escape a no-break space in printable text). `get_logger` returns the library's
    own `StructuredLogger` (`debug`, `info`, `warning`, `error`, each taking an event and its
    fields), with no `exception`, `critical` or `bind`, since a traceback is content-shaped;
    structlog only formats the handler `configure_logging` installs, so a console line reads
    as M1's did; `serve()` runs uvicorn with `log_config=None`; and a command run with
    `python -m` logs as `__main__`, so the Ole5 app names `ole5_voice` and `__main__` to
    `configure_logging`.
- **Consequences:** importing the library prints nothing and configures nothing, and a
  teammate's process keeps its own loguru sinks. D-002's heading points here; ARCHITECTURE.md's
  conventions and the roadmap's M2 line say the same, and GP-03, which names the standard
  library and the `NullHandler`, is unchanged. The guide's "Variables to leave unset" names
  `LOGURU_*`, and its `tracing-and-logs.md` (plan 003's Track I) gives the policy. If the owner
  picks Q19's (a), `forward` is added in an entry of its own.
- **Evidence:** the owner, 2026-11-02, in plan 004's read, on the library's logging: "Fix it in
  M2 (Recommended)"; and to plan 003's Q1 to Q6, each put with the agent's recommendation, Q2's
  (a) among them: "Yes go with the recommended." (plan 003, "The owner's decisions"). Q19 is
  among plan 003's open questions, not answered. The tests:
  `tests/t2_agentic_voice/core/test_logging.py`, `test_logging_console.py` and
  `test_logging_import.py`; plan 003's Track E adds invariant 8's tests in a child process.

## D-032 · ARCH-BAN, the owners M2 adds, and the facades `identity`, `server`, `stores` and `events` · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 5.1, 5.3, 12.2 and 12.4; one bullet Proposed; its torch check amended by D-086)

- **Context:** the design's 12.4 adds ARCH-BAN, banned module prefixes with exceptions, since
  ARCH-OWNER gives a whole library to its layers and cannot keep Pipecat's provider services
  out of `voice`, nor Pipecat and aiortc out of the apps; D-020 left it for the plan that needs
  it. The design's 5.1 lists the public modules M2 first fills (`identity`, `server`,
  `stores`, `events`), its 5.3 the test that keeps framework types out of public signatures,
  and its 12.2 the layers that own the libraries M2 installs. This entry follows up D-020 and
  D-021. The fixes after the review of plan 003's Block 0 (2026-11-03) widened ARCH-BAN's
  reach and the public-types test, written below.
- **Decision** (as the design's 5.1, 5.3, 12.2 and 12.4 describe it):
  - ARCH-BAN (`scripts/arch_ban.py`, from `poe arch`), read from `harness.toml`'s `[[bans]]`:
    each table names its `modules` (each with every module under it), the `allowed` ones
    inside them, the code it covers (`within`: the library, a part of it, or an app's
    package) and a fix. In the library, Pipecat's provider and model services
    (`pipecat.services`, the speech base classes' modules allowed) and its LLM adapters and
    context aggregators are banned; in `voice/session/`, all of Pipecat; in the apps and the
    examples, Pipecat and aiortc.
  - `[[owners]]`: `loguru` to `voice` (D-031), `jwt` and `sqlite3` to `adapters`, and
    `num2words` to `domain`.
  - The torch check (no `torch` in `uv.lock`), and an import of every public module alone in a
    fresh process (the design's 5.3, point 2, and 12.4).
  - Four facades join `[package] public` and `facades`, each re-exporting the names of the
    design's 5.1 that M2 builds: `identity` (`SignedJoinTokens`, `DevIdentity`) and `server`
    (`serve`, `combine_lifespans`), stable; `stores` (`SqliteUsedTokens`, `MemoryUsedTokens`)
    and `events` (the eight event classes M2 emits, and `CallReport`), provisional. The
    package root gains `VoiceAgent`, `Language`, `Caller`, `Consent`, `Providers` and
    `VoiceRuntime`; `ports` gains `TextToSpeech`, `AudioChunk`, `IdentityVerifier` and
    `UsedTokens` (provisional); `groq` gains `GroqTTS`; `languages` gains `speak_number` and
    `speak_id`.
  - The design's 5.3, point 1: `tests/t2_agentic_voice/test_public_types.py` fails when a
    public signature names a type from `pipecat`, `aiortc`, `onnxruntime` or `groq`.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log and appendix have the reasons):
    - ARCH-BAN allows six modules of `pipecat.services`: the design's `ai_service`,
      `stt_service` and `tts_service`, and `settings`, `stt_latency` and `websocket_service`,
      which the speech base classes import in Pipecat 1.15.0. It also bans, from plan 003's
      reading of the installed Pipecat (its appendix, item 18): Pipecat's runner, command line,
      evals and buses (importing `pipecat.runner.run` loads a `.env` with override and removes
      loguru's sinks, and a test finds it out of `sys.modules` after `voice` is imported);
      Smart Turn v2 (torch) and the resampy resampler (numba); its frame logger and logging
      observers, which write call content; and its DTMF aggregator and RTVI, which inject
      caller input past speech-to-text and the session (each pipeline worker runs with
      `enable_rtvi=False`). And, after Block 0's review, the rest of Pipecat's LLM machinery
      (Pipecat Flows, the LLM switchers and `llm_with_backend`, the LLM and UI workers, the
      extensions an LLM runs, the LangChain and Strands processors, and the turn ends an LLM or
      a classifier decides), and the modules that send a call's audio or text to a host outside
      the design's 11, or fetch from one, with no port (the classifiers, the HTTP Smart Turn,
      the serializers and the processor that streams a call's frames through one, the worker
      proxy, the file resolver, the Tone models, and every transport but Small WebRTC, whose
      base transports and video sampler stay allowed), each table with a fix that says what to
      do instead. `tests/harness/test_installed_pipecat.py` recomputes the allowed services and
      transports from the installed source, and walks the installed Pipecat for every module
      that imports an HTTP or websocket client or a banned module, each to be banned or listed
      there as reviewed, with its reason, so a new Pipecat that adds one fails until someone
      reads it. Set aside: listing the other transports one by one, which a new transport in a
      later Pipecat would escape.
    - How ARCH-BAN reads: a ban on part of a package (`voice/session/`) follows that package's
      own imports, relative ones resolved and `TYPE_CHECKING` ones included, through every
      module the ban does not cover, so a session module that imports a library module which
      reaches Pipecat (`voice/calls.py` does, for its analyzers' types) is refused where its
      import is written; a parent package's `__init__` is not followed, or every module would
      reach the root. A literal `importlib.import_module` or `__import__` counts, a relative
      name resolved against its literal package and the `name=` keyword read; a `within` that
      names no module on disk is a HARNESS-CONFIG problem, so no command runs on a ban that
      guards nothing. What Pipecat imports by itself is still not read (TD-043). Set aside: a
      rule that the session imports only `voice.session` and `voice.protocol`, which needs a
      second rule and breaks once `voice.protocol` imports anything new.
    - The torch check and the fresh-process imports run inside `poe check`
      (`tests/harness/test_install.py`), not in CI, while CI waits for a remote (TD-001); each
      import must print nothing, and its child shows every warning once (`-W default`), so a
      warning on import fails it.
    - A name the design's 5.1 does not list is public only where a public signature names its
      type: `ports.JoinContext` (`IdentityVerifier.verify`'s `join`); `events.Event` (what
      `runtime.on` takes), `ModelUsage`, `TurnRecord`, `TurnTimes` and `ClientConnection`
      (`CallReport`'s parts); in `evals`, `turn_ends` and `echo_timings`, which plan 003's
      decision log puts there while `testing` is not public (D-019), with what they yield,
      `TurnEnd`, `TurnTiming` and `EchoTiming`, and `PhraseAudio`, the phrase audio
      `echo_timings` takes (set aside: `ports`, whose protocols reach an outside service, and
      `stores`, where no signature names it); at the package root, beside `VoiceSettings` and
      `get_logger`, the classes of `VoiceSettings`'s twelve groups (`GroqSettings`,
      `ServerSettings` and the rest), `TtsVoice` (what `tts.languages` holds) and
      `StructuredLogger` (what `get_logger` returns), so a team builds a typed
      `VoiceSettings(env=..., server=ServerSettings(...))` from one module; and in `languages`,
      `Pronunciations` (`VoiceAgent.pronounce`'s type, D-033) with `pronounce` and
      `split_clauses`, the pronunciation map and the clause splitter plan 003's criterion asks
      of that facade, and, since the check of Block 0's fixes, `provider_text`, the text a
      text-to-speech provider is sent for a phrase (D-033). One name is public that no public
      signature names: `stores`' `PhraseCache`, the phrase cache (the design's 10.4; its 11
      keeps it under `var_dir` beside the used tokens), so a timing run builds the phrase audio
      `echo_timings` takes as the runtime does, since `testing` never imports `adapters` (the
      integrator's ruling after that check; set aside: `groq`, the cache being no Groq
      adapter, and a builder function in `api`, a second way to build the same thing). D-087
      adds a second such name, for the same reason: `stores`' `ClauseCache`, the clause cache
      (`ClauseCounts`, beside it, is named by its `counts`).
      `speak_digits` is held back, as no public signature names it and no app imports it in
      M2. Set aside: the 5.1 names alone, which would leave public signatures typed by names an
      app cannot import; spreading the settings groups across the facades by topic, which
      leaves half of them with none; and a `settings` facade, a change to 5.1 for the owner.
    - The 5.3 test resolves each annotation with `typing.get_type_hints` and reads every name
      in a public module's `__all__`, then every library class its signature names, in turn: a
      function's parameters and return; a class's bases, fields and annotated attributes, the
      parameters and return of its constructor, of the dunders a caller uses (`__call__`,
      `__enter__`, `__getitem__` and the like) and of each public method, property and cached
      property on it or on a base of its own; a type alias's value; through any type alias or
      `NewType`. A parameter or field whose name starts with `_` is private and not read. It
      also fails when a library class a public signature names is in no public module's
      `__all__`.
    - The package root imports `api.runtime` at once, as it imports every name it re-exports,
      so `import t2_agentic_voice` loads FastAPI (2.94 s and 2.91 s for `fastapi` alone on the
      owner's machine, `python -I`, as plan 003's Block 0 timed it). TD-046 records it, and
      plan 003's Track F removes it.
- **Consequences:** ARCHITECTURE.md's enforcement list and conventions name ARCH-BAN and the
  owners. `tests/t2_agentic_voice/test_facades.py` pins each facade's names and the package
  root's `__all__`, so adding a public name is deliberate. Neither ARCH-BAN nor ARCH-OWNER sees
  an import made inside Pipecat. The `[[restricted]]` rows M2 adds, `SignedConsent` and its
  seal, are D-035's. Of the design's 16.3 harness entry, one configuration per member and one
  invariants register are still to write, each with the plan that needs it.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01. The rules' tests:
  `tests/harness/test_arch_ban.py`, `tests/harness/test_installed_pipecat.py`,
  `tests/harness/test_install.py`, `tests/t2_agentic_voice/test_facades.py` and
  `tests/t2_agentic_voice/test_public_types.py`.

## D-033 · The echo's shape: an agent with a name and its languages, `session.mode`, a fixed frame · 2026-11-02 · Accepted (the owner, 2026-11-02, plan 003, Q3, and the design's 4.3 for the pronunciation map; one bullet Proposed; amended by D-087 for a talker's clauses)

- **Context:** M2 has no talker: the voice session says back what it heard (the design's 16.1:
  "the voice session in echo mode", and `examples/minimal` "as an echo use case"). The design
  gives neither a public form, which is a design choice, so plan 003 asked the owner (its Q3):
  the agent's declaration with only a name and its languages and a setting for the session's
  mode, a runtime argument that M4 would have to deprecate, or an internal stand-in; and
  whether a fixed frame comes before the heard words. The fixes after the review of plan 003's
  Block 0 (2026-11-03) gave the declaration what plan 003's tracks need of it: the
  pronunciation map, each preset's notice texts, and its errors; the check of those fixes
  (2026-11-03) had the session and the phrase cache say text through the map, the cache pack
  and pace its requests, and a phrase hold the unseen characters pasted text carries, all
  written below.
- **Decision** (the owner's answer to Q3, (a) and (i), and the design's 4.3):
  - `VoiceAgent(name, languages=[Language.saudi_arabic(greeting=...), ...])`, built in M2 with
    these fields and the pronunciation map below, and the setting `session.mode`, with `echo`
    its only value in M2. M4 adds the talker, and the talker's fields arrive as optional
    arguments, so an echo agent stays a team's first audio check.
  - `VoiceAgent(pronounce=...)`, the design's 4.3 pronunciation map: each written form, as a
    text holds it, to how each language says it, keyed `ar` or `en`
    (`pronounce={"LT-": {"en": "L T"}}`); the design's 16.1 puts pronunciation in M2.
  - Each echo reply starts with the fixed frame, «سمعتك تقول: …» or "I heard: …", in the
    call's language (D-038), then the heard words; the greeting and the notices, replies too
    (D-037), take none. The frame says the words are the caller's, so the echo never sounds
    like the agent answering or claiming an action (invariant 2). It is a cached phrase (the
    design's 10.4), so it plays as soon as the turn's transcript is in, while Orpheus
    synthesizes the heard words. M2's fixed phrases are in Saudi dialect (plan 003's Q5).
  - **Proposed** (the agent's, beyond the design and Q3, for the owner to rule on; plan 003's
    decision log has the reasons):
    - `VoiceAgent` is `@final` and frozen, and not yet generic (the design's 5.2 has
      `VoiceAgent[Deps]`; `Deps` comes with the talker). Its name matches
      `[a-z][a-z0-9-]{0,63}`, since it names the agent's folder under `storage.var_dir`, and is
      none that Windows keeps for a device (`con`, `prn`, `aux`, `nul`, `com1` to `com9`,
      `lpt1` to `lpt9`), which no folder can take. Its languages are one or more presets with
      distinct tags, the first a call's language when nothing picks another; a call's language
      is fixed at join (D-038). `Language` holds a tag, a greeting, the echo's frame and the
      text of each notice kind (`busy`, `error`, `ended`, the design's 5.5); its presets
      `saudi_arabic` (`ar-SA`), `arabic` (`ar`, MSA) and `english` (`en`) each take `greeting=`
      and may take `notices=`, and set the frame, the Arabic one for both Arabic presets, and
      each notice's text in the language's register: `ar-SA`'s in the Saudi register Q5 chose,
      `ar`'s in Modern Standard Arabic, `en`'s in English. A team's `notices` replace only the
      kinds they name, and a `Language` built without its preset gives all three, its notices'
      FIX saying so, where a preset's says that a kind left out keeps the preset's text. The
      presets return the class they are called on, so a team may subclass `Language`. A
      greeting, the frame, a notice, and a written or spoken form of the pronunciation map say
      something once a provider's text is made of them, and hold no control or format
      character, line or paragraph separator, lone surrogate (which no UTF-8 request or file
      hash can encode) or space other than U+0020, but the no-break spaces U+00A0 and U+202F,
      the joiners U+200C and U+200D and the direction marks U+200E, U+200F and U+061C, which
      pasted text often carries (`domain/text/invisible.py`); the refusal states that whole
      rule, since the team cannot see the character. A caption shows a phrase as written; a
      provider is sent `provider_text`'s form, the no-break spaces made spaces and the joiners
      and marks dropped (below).
    - The pronunciation map's inner keys are checked at run time to be `ar` or `en` (a
      pronunciation names a language by its primary code, which both Arabic presets share),
      not typed as a `Literal`, so an app's map built in a plain `dict` type-checks; its type is
      the `languages` facade's `Pronunciations`, a `type` alias, and the map is read-only.
    - Every failure to build a `Language` or a `VoiceAgent`, `model_validate` and
      `model_validate_json` included, and on a team's subclass of `Language` too, is a
      `ConfigurationError` with a FIX line (the design's 4.2) that names its first failing
      field (its details `{"field": ...}`, None for an input that is no mapping at all, and for
      a text given to `model_validate_json` that is not JSON, whose message is pydantic's,
      which gives a position, never the text, and whose FIX asks for one JSON object of the
      fields, as `model_dump_json()` writes) and never the value; a field a subclass adds is
      named with a FIX to correct it. Only assigning to a built one raises pydantic's
      `ValidationError`, as for every frozen model. Set aside: the settings' collected shape
      (D-028), since a declaration is code the team reruns at once; and a fixed reason for a
      text that is not JSON, as the settings give, which drops the position a team needs.
    - The echo: one voice speaks each reply, the language's (the prototype's D35); an empty
      transcript is said back as nothing and kept on the timeline; speech that starts while any
      reply plays, the greeting included, or within 300 ms after a reply's last clause played
      (D-037), from the speech detector's onset, is not said back, the turn kept on the
      recording and the timeline for M3, so on laptop speakers the agent never echoes its own
      voice (as the prototype's D23 was half-duplex); and only Stop, Esc and `hangup` interrupt
      in M2, the interruption rules being M3's.
    - The notices: the session sends and speaks `error` after a turn it would say back whose
      transcript failed, or an echo one of whose clauses failed, and `ended` when it ends the
      call at `limits.max_call_s` or `limits.idle_s` (plan 003's Q4), hanging up once the
      notice has played or failed, or at once when a stop drops it (D-037). Each goes out as
      `t2v/1`'s `notice`, whose text the client shows, and is spoken from the phrase cache as
      the next reply (D-037), so it plays even when text-to-speech is rate-limited (the
      design's 10.4). `busy` is never spoken: admission control answers it at join, before a
      call has audio (the design's 10.5). Set aside: notices as text only, which would leave
      the cached notices unused.
    - Text built from heard words never reaches the phrase cache, which holds only the fixed
      phrases `PhraseCache.declare(agent)` reads from the agent at the runtime's start
      (`domain/fixed_phrases.py`'s `fixed_phrases`, each a `FixedPhrase` of a text, its
      language and its kind, `greeting`, `echo_frame`, `notices.error` or `notices.ended`):
      each language's greeting, echo frame and its `error` and `ended` notices (not `busy`,
      one request per language that no call plays), so the cache keeps no call content
      (invariant 8). A fixed phrase longer than the text-to-speech's `max_chars` is spoken
      whole: the cache cuts the text it sends with the clause splitter, which cuts inside a
      word only a word longer than `max_chars`, at `max_chars`, and packs the clauses
      greedily, in order, into requests of at most `max_chars`, the clauses of one request
      joined by a space, so a phrase of n characters costs about n / `max_chars` requests; it
      sends them one at a time and joins the takes into one chunk, which the session plays as
      one clause; so the runtime refuses no greeting or notice at its start. A request refused
      as rate-limited waits the delay the provider asked for, at most 60 s
      (`MAX_RETRY_DELAY_S`, and that bound when it asked none), and is sent again at most
      twice (`RETRIES`), the agent's bounds; its next refusal fails `declare` with a
      `ProviderError` (`rate_limited`) whose details name the phrase's kind and language,
      never its text. `declare` returns the requests it sent, none for a phrase its folder
      held. Set aside: refusing such a phrase at start; the session splitting fixed phrases,
      under which every greeting with a comma would cost two requests; one request a clause,
      under which a long greeting of short sentences sent a burst at start that Groq's
      published 10 requests a minute refuses (the check of Block 0's fixes); and a default
      delay of the cache's own, a number nobody gave (GP-16). Caching talker clauses that
      repeat exactly (the design's 10.4) was left for later: D-087 keeps every clause a talker
      call speaks in a cache of its own, the clause cache, never the echo's words, keyed on the
      text sent as this bullet keys a phrase. The phrase cache still holds only the declared
      phrases.
    - The session and the phrase cache, not the text-to-speech adapter the design's 3.1 gives
      them to, say text through the pronunciation map and cut it into clauses. The session
      applies `pronounce` with `agent.pronounce`, in the call's language, to a reply's text
      before it cuts the text with `split_clauses` at the provider's `max_chars`, so each
      clause is measured on the said form; each clause's `Speak` carries the text the
      provider is sent, `provider_text` of the clause, which is never longer and which the
      Pipecat side sends unchanged, so the text-to-speech bridge's TOKEN aggregation sends one
      request a clause (plan 003's appendix, item 9); and the agent's caption shows the said
      form. The phrase cache says each fixed phrase through the map and sends only its
      provider text, keys the phrase's file on that text, the model and the voice, and keeps
      the phrase under its written form, which `audio` finds and captions show. Set aside: the
      text-to-speech bridge making the provider's text, which would split one rule between two
      tracks; and keying a phrase's file on the written phrase, which would play stale audio
      after the map changed.
- **Consequences:** `examples/minimal` is an echo agent (`make_runtime()`) whose tests need no
  key and no network, and may catch `ConfigurationError` around its declaration. M4 adds the
  talker to the same declaration, with no deprecation. The call's language picks Whisper's
  language (`stt.live_language`, D-028) and the voice.
- **Evidence:** the owner, 2026-11-02, to plan 003's Q1 to Q6, each put with the agent's
  recommendation, (a) and (i) for Q3: "Yes go with the recommended." (plan 003, "The owner's
  decisions"); for the design's 4.3, as for D-019 (plan 002, Q3), 2026-11-01. The tests:
  `tests/t2_agentic_voice/domain/test_declaration.py`, `test_declaration_paths.py`,
  `test_invisible.py` and `test_fixed_phrases.py`.

## D-034 · Whisper gets one request per user turn · 2026-11-02 · Proposed (the agent's, plan 003; the design's 13 names a bridge on `SegmentedSTTService`)

- **Context:** Groq's Whisper transcribes a finished clip, with no partial transcripts (D-004),
  and bills each request at least 10 s (the design's 10.4); M1's baseline measured whole clips
  (D-025). The design's 13 puts the speech-to-text bridge on Pipecat's `SegmentedSTTService`,
  which sends one request per VAD segment (`pipecat/services/stt_service.py`, read at 1.15.0 by
  plan 003's step 4): with a 200 ms VAD stop and the owner's pauses of about 0.83 s, a paused
  request would become two requests or more, each billed at least 10 s, of fragments Whisper
  hears without their context. Plan 003's spike asked whether one request per user turn can be
  had.
- **Decision:** the speech-to-text bridge holds a user turn's audio from its start to its end
  and sends it whole, one request per turn. It subclasses Pipecat's `STTService`, not
  `SegmentedSTTService`, and sits after `UserTurnProcessor`: the transport's input, the VAD,
  the turn processor, the bridge, the session bridge, the text-to-speech bridge, the
  transport's output. It opens on the downstream `UserStartedSpeakingFrame` with at least
  0.5 s of the audio before it, closes on `UserStoppedSpeakingFrame`, trims at the last VAD
  stop plus padding, caps a turn's length itself, and gives exactly one result per turn, an
  empty, failed or unusable one included, unless the call ends first, at an `Ending`, a
  `TransportFailure` or the session's `HangUp`: then it drops the turn's held audio and cancels
  a request in flight (D-037). It hands the session a `Transcribing` as each request goes, so
  a request the end cancels is still counted. Smart Turn's stop strategy is given
  `wait_for_transcript=False` explicitly, so a turn's end is the analyzer's alone and the
  session waits for the transcript itself. Set aside: one request per VAD segment, which bills
  every fragment, hides the earlier segments' time inside the caller's speech, and spends the
  published 20 requests a minute of `whisper-large-v3` sooner.
- **Consequences:** whether a paused request is one request is Smart Turn's verdict at the
  pause, not the bridge's: a first clause that sounds complete ends the turn, so plan 003's
  registered request counts keep their upper bounds. A turn that only the silence fallback ends
  carries about 3 s of trailing silence, billed, unless the bridge trims it.
- **Evidence:** plan 003's pipeline spike on the owner's machine, with fake speech services and
  no request to Groq (its appendix, step 5): with `wait_for_transcript` off, run A sent one
  request for an utterance with a 0.86 s pause, 5.84 s of audio holding both parts and the
  pause; run C, that utterance looped for 62.86 s, sent 7 requests, one per turn, two of the
  turns ended by the 3.0 s fallback (request 3: 8.88 s); run B, two complete-sounding clauses
  0.88 s apart, gave 2 turns and 2 requests, Smart Turn calling the pause complete
  (p = 0.942). With `wait_for_transcript` on (run D), Smart Turn said complete at 6.286 s and
  the turn ended only at the stop timeout, at 11.191 s. `UserStartedSpeakingFrame` came about
  0.34 s after the speech began, hence the pre-roll.

## D-035 · SECURITY.md's invariants 7 and 8 brought to the design's 8.1 · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 8.1; one bullet Proposed)

- **Context:** the design's 8.1 (D-017) says what the library enforces for each invariant. For
  invariant 7 it adds to the token's own checks a per-call offer secret, so the call ID is
  never a credential, and a lock file, so a second process cannot share the used-token store;
  for invariant 8 it adds a second condition for keeping audio, beside `privacy.record_audio`:
  the recording consent a verified signed join token carries; and it switches Pipecat's loguru
  namespace off by default. SECURITY.md's invariants 7 and 8 predate the design (D-007),
  and plan 003 builds both. Generalizing SECURITY.md to actions and moving it into the library
  as the one register stays with the plan that builds actions (the design's 16.3). The review
  of plan 003's Block 0 (2026-11-03) found that the static check alone let code outside
  `adapters` copy, subclass or rebuild a `SignedConsent`; its fixes are written below. Its
  recheck (2026-11-03) found that pydantic's v1 `copy(update=...)`, an unbound base
  `model_copy` (`Consent.model_copy`, `BaseModel.model_copy`, `super()`), a `__class__`
  assignment and a re-called `__init__` still gave a `SignedConsent` that `allows_recording`
  accepted, and that ARCH-CONSTRUCT's names check missed a class pattern's keyword, a star
  import, and names its own-definition exemption let through; the second round's fixes are
  written below too.
- **Decision** (as the design's 8.1 describes it): invariant 7 holds the token's checks (mint
  and verify, HS256 only, a lifetime of `join.ttl_s`, at most 120 s, within a clock-skew
  allowance, one use of each `jti`, a key map), the offer secret (random, one call's, needed
  by the offer and each ICE update, stopping when ICE completes or the call ends, so the call
  ID is never a credential) and the lock file (one process per `storage.var_dir`). Invariant 8
  holds the two conditions for keeping audio (`privacy.record_audio` on, and the recording
  consent of a verified signed join token), audio never exported to traces, call content
  logged only with `logging.content`, which only `dev` allows, and Pipecat's loguru namespace
  off by default. Each names what enforces it now, and the tracks of plan 003 whose
  adversarial tests will (C, D, E and F), as SECURITY.md words a check not built yet. This
  amends D-007 for these two invariants.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log has the reasons):
    - Invariant 7 also holds rules beyond the design's 8.1: a join key of at least 32 bytes
      (D-028, D-029); a clock-skew allowance of at most 60 s, the used-token store keeping a
      token's `jti` until its expiry plus that bound, whatever allowance is configured, and
      never recording as a first use a `jti` whose last instant has passed by its own clock
      (D-028, D-029); and the offer secret never in a URL (D-029).
    - Only a `SignedConsent` counts as the token's consent: a `@final` subclass of `Consent` in
      `core/identity.py`, built in `adapters` alone, and there by `SignedJoinTokens` alone, from
      a token whose signature it verified, as
      `SignedConsent.model_validate(claim, context=CONSENT_SEAL)`. The seal is a bare object
      compared by identity (a copy of it is no seal), given as the validation's context, which
      the class checks after every validation (`model_post_init`). The validation records that
      very instance as sealed, in a module-private registry keyed by its id: each entry holds a
      weak reference to the instance, its `__dict__` and its fields as they were, and goes when
      the consent is collected. Every other layer asks `allows_recording(consent)` and never
      names the class. It is true only for that instance, alive and unchanged since (its exact
      type, its own `__dict__`, each field the same object), when it says `record_audio`. Any
      other consent allows nothing: a copy of any kind, even with no change (pydantic's
      `copy`, `model_copy` by any path, `copy.copy`, `copy.deepcopy`, a pickle), one rebuilt
      by a re-called `__init__`, one re-typed by an assigned `__class__`, one whose fields were
      written in place, and a subclass's. So that the common mistakes fail loudly, these raise
      TypeError: its constructor; a validation without the seal (`model_validate`,
      `model_validate_json`, a `TypeAdapter` of the class, a model with a field of it; the
      seal alone guards those last two); `model_construct`; `model_copy` with an update, and
      pydantic's deprecated `copy` given `update`, `include` or `exclude` (pydantic validates
      none of them, so even the seal's holder builds a changed consent anew); and a subclass,
      as it is defined or, past a mixin that skips `__init_subclass__`, as it is validated. A
      consent that `DevIdentity` or a team's own verifier returns never turns recording on,
      and a `SignedConsent` never equals a plain `Consent` with the same choices.
    - `[[restricted]]` keeps it statically, in two tables (ARCH-CONSTRUCT), each held by its
      `layers` and, new, its `files` (modules of the library, each a path inside the package
      under a layer; every table has both keys, and one may be empty, not both).
      `SignedConsent`'s `classes` row reports a call that builds one outside `adapters`. A
      table that lists `names` instead of `classes`, a new kind, reports any mention of
      `CONSENT_SEAL` outside `adapters/join_tokens.py` and `core/identity.py`, in the library
      or an app. Mentions are read from the module's tokens and constants: any token that is
      the name, read as Python reads an identifier (an import under any alias, an attribute,
      a read, an annotation, a subscript's key, a keyword, a class pattern's keyword); any
      literal that holds it (a string, bytes, an f-string's part, a docstring, escapes and
      joined literals included); and a star import from a module of the row's files or
      layers. The defining module is exempt only because the row names it; no module has an
      own-definition exemption. That only `SignedJoinTokens.verify` gives the seal, inside
      that module, is a review. What gets past both guards is deliberate, and review sees it:
      the seal's name computed at run time, or the seal found without its name
      (`vars(module)`, the garbage collector's referents); memory rewritten through `ctypes`;
      and writes to `core/identity.py`'s own state, its registry or `allows_recording`
      replaced (SECURITY.md, invariant 8). This is the `[[restricted]]` change `harness.toml`
      asks a decision for; ARCHITECTURE.md's conventions and enforcement list name it.
    - Set aside: a private flag on `Consent`, which any layer could set and the check cannot
      see; a constructor that takes the seal, under which pydantic's `model_validate` calls
      `__init__` again without it; the seal as a key of the data, which would be a field held
      on every consent; `core` among the seal's layers, which would let any `core` module
      validate a `SignedConsent`; a private attribute holding the sealed values, which every
      copy carries over, so an unchanged copy would still allow recording, and which any
      layer could set; a weak-keyed map, whose keys compare by equality, so a copy would find
      its original's entry; overriding every copy entry point, which a call through the base
      class skips; a static check of a `TypeAdapter` of the class or a model field of it,
      which the seal guards at run time; an optional `files` key, against `harness.toml`'s
      "Each key is required"; and an exemption for every module that defines a name of the
      seal's spelling.
- **Consequences:** D-007's heading points here. The recorder writes audio only when both
  conditions hold, asking `allows_recording` of the very consent the identity source returned
  (a copy of it records nothing), and never copies or rebuilds a consent; no client message
  can set either condition. What stays the app's is the design's 8.1: minting tokens
  only for signed-in callers, a rate limit on its minting route and one process per
  `var_dir`; the consent wording and its version, the retention in its own Phoenix, and
  deletion requests. SECURITY.md's trust boundaries now also name the variables the call's
  packages read, and say that a browser and the backend on one machine meet over its private
  network addresses, not loopback (plan 003's decision log); the owner has not reviewed those
  rows yet.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01. The tests SECURITY.md's invariants 7
  and 8 name.

## D-036 · The ports beyond the design's 6.1: `aclose`, `AudioChunk`'s fields, `check_language` with no synthesis, `Transcript`'s headroom · 2026-11-03 · Proposed (the agent's, plan 003's Block 0; the design's 6.1 gives none of them)

- **Context:** the design's 6.1 gives the ports' shapes, `SpeechToText` and `TextToSpeech`
  stable (D-021). M2's runtime owns its adapters' lifetimes, one adapter serves every call at
  once, and each call's report keeps the usage and the rate-limit headroom per model (plan
  003's criteria); the lifespan warms the adapters without speaking. Plan 003's decision log
  (2026-11-02) wrote these changes to the ports as Proposed, for an entry after D-035 that step
  12 left out; the review of plan 003's Block 0 (2026-11-03) added the speech-to-text
  headroom, and the check of its fixes (2026-11-03) had `GroqSTT` read it.
- **Decision:**
  - One close for every port that holds connections: `aclose()` on `SpeechToText` and
    `TextToSpeech` (stable) and on `UsedTokens` (provisional), which closes what the adapter
    holds open and returns at once when it holds nothing; whoever built it calls it once, when
    done with it (the runtime as it stops, a run). The eval runner closes its adapter through
    the port, which paid TD-020. Set aside: an async context manager, since `GroqSTT` already
    had `aclose` and the lifespan closes each adapter itself.
  - `AudioChunk` is mono 16-bit PCM, little-endian, `sample_rate` read from the provider's
    audio, never assumed, with `seconds`; a chunk may be empty. A response's usage travels on
    its chunks: `remaining_requests` and `remaining_tokens` (Groq's
    `x-ratelimit-remaining-requests` and `-tokens`) on its first chunk, None on the others and
    on a phrase played from the cache; and `cut_short` on a take's last chunk, a take that came
    back shorter than its text needs, flagged, not made again (plan 003's decision log). It
    checks its input as D-021's types do: no unknown field, whole samples, a rate above 0, no
    negative headroom. Set aside: an attribute on the adapter, which calls served at once would
    race on; and an object `synthesize` returns beside its chunks, which departs from the
    design's `AsyncIterator[AudioChunk]`.
  - `TextToSpeech.check_language` sends no synthesis request: it raises `ConfigurationError`
    for a language the settings give no model or voice, and `ProviderError` when the provider
    refuses the model or the voice; `GroqTTS` returns when the language has a model and a voice
    and Groq lists the model (a GET, which the Groq client's request hook sends with no body).
    A model whose terms are not accepted may show only at its first synthesis, which
    `t2v doctor --synthesize` checks: Groq documents no other way to learn it. This narrows the
    design's "raises naming the missing model, voice, access or terms".
  - `check_language` returns the provider's time as its answer gave it, aware (UTC), or None
    when it gave none (2026-11-04: plan 003's criterion names the clock's skew for
    `t2v doctor`, and the owner ruled "Do it now" on TD-067's fix). `GroqTTS` asks for the
    model list raw (`groq_client.raw_response()`), so that GET carries the raw-response marker
    too, and returns its `Date` (`groq_client.server_time()`: one HTTP-date in GMT, read by
    `email.utils.parsedate_to_datetime`, else None, never an error). `t2v doctor` measures this
    machine's clock against it with no request of its own (api/doctor.py). The wider return
    breaks no adapter that returns None and no caller (the design's 5.4). Set aside: an
    attribute on the adapter, which checks run at once would race on and which doctor could
    read only by naming the adapter's class; and a request of its own for the time.
  - `Transcript` gains `remaining_requests` and `remaining_tokens`, optional and None by
    default, the headroom the provider reported with the answer, so the call's report can keep
    Whisper's as it keeps Orpheus's. `GroqSTT` fills them. The SDK hands back an answer's
    headers only in its raw response, which it gives when the request carries its
    raw-response marker; the Groq client's request hook keeps that marker only for the
    adapter's own call that asks for the raw response (`groq_client.raw_response()` around a
    call through `with_raw_response`, read from a context variable, since the hook runs in the
    calling task), writing the SDK's own value, never one from `GROQ_CUSTOM_HEADERS` or the
    environment, so a transcription request carries one header more, the marker. The adapter
    reads `x-ratelimit-remaining-requests` and `-tokens` from the raw response
    (`groq_client.headroom()`: each a whole number in ASCII digits, else None) and parses the
    transcription as before; Track B can use `headroom()` for `GroqTTS`'s first chunk. An
    optional field breaks no caller of a stable port (the design's 5.4). Set aside: fields on
    the session's `Transcribed`, which already carries the `Transcript`; the report's
    criterion narrowed to the text-to-speech models; a flag on the hook for each adapter,
    which cannot tell the adapter's raw call from a `GROQ_CUSTOM_HEADERS` marker on its other
    requests; and importing the SDK's private constant into library code (a test pins
    `RAW_MARKER` to it).
- **Consequences:** an adapter a team writes for these ports implements `aclose()`; no team has
  one yet, since no tag has been installed. The design's 6.1 does not show these fields, nor
  `check_language`'s return, nor its 6.5 the store's `aclose()`.
- **Evidence:** the types builder's choices in plan 003's decision log (step 10, 2026-11-02),
  and the review's finding on Whisper's headroom (2026-11-03). The tests:
  `tests/t2_agentic_voice/domain/test_ports.py`, `test_text_to_speech_port.py` and
  `test_identity_port.py`; for Whisper's headroom,
  `tests/t2_agentic_voice/adapters/test_groq_stt.py` and `test_groq_client.py`; for the
  provider's time, `test_groq_client.py`, `test_groq_tts.py` and
  `tests/t2_agentic_voice/api/test_doctor.py`.

## D-037 · Agent speech is keyed on replies, and the drop rule covers every reply, the greeting included · 2026-11-03 · Proposed (the agent's, plan 003's Block 0 after its review; beyond the design's 5.5 and 6.6)

- **Context:** the voice session greets the caller once connected, in the greeting the call's
  language declares, before any turn of the caller's exists. Block 0 keyed every clause the
  agent speaks, and its events, captions and playback reports, on the caller's turn number,
  which the speech-to-text bridge counts, so the greeting and the echo of turn 0 would have
  shared a key. The drop rule (D-033) named the echo alone: read so, the greeting leaking past
  echo cancellation on laptop speakers would be said back; read as any speech, every file-fed
  call's clip, fed while the greeting played, would be dropped. And a turn still open when the
  call ends could not get both its transcript and no event after the last command. The review
  of plan 003's Block 0 found the three (2026-11-03), and the integrator ruled on each. The
  check of those fixes (2026-11-03) found that a stop naming one reply spared the replies
  queued after it, which Pipecat's interruption cannot do; that the end's rule left out the
  session's own `HangUp`; and that a request the end cancelled went uncounted; the integrator
  ruled on each again.
- **Decision:**
  - **Replies.** The caller speaks in turns and the agent in replies, numbered apart: the
    speech-to-text bridge numbers the caller's turns from 0 (`TurnId`), and the session the
    agent's replies from 0 (`ReplyId`, in `voice/protocol.py` beside `ClauseIndex`): the
    greeting is reply 0, and each echo and each spoken notice the next. `Speak` keys each
    clause on its reply and its index there, and names the caller's turn the reply answers,
    None for the greeting or a notice. `StopSpeaking` drops every clause the session has asked
    for so far, whatever its reply, its `reply_id` naming the newest, since Pipecat's
    interruption drops every queued frame; no event of a dropped clause follows, one the
    Pipecat side held included, the session counts each dropped reply as done, waiting for no
    event of it, and it hangs up at once if one was the `ended` notice. `ClauseQueued`,
    `ClausePlayed` and `ClauseFailed` carry the reply and the clause alone, since the session
    knows which turn a reply answers. On `t2v/1`, a caller's caption names its turn only, an
    agent's its reply and clause, with the turn it answers when there is one, and a `playback`
    report a reply and a clause. `core`'s `AgentSpeechEnded` and `Interrupted` take an
    optional `turn_id`, None for the greeting or a notice. Set aside: one numbering for turns
    and replies, under which the greeting and turn 0's echo share a key; and a stop that
    spares later replies, re-queuing them after the interruption.
  - **The drop rule covers every reply.** A turn whose speech began (the speech detector's
    onset) while any reply played, the greeting included, or within 300 ms after a reply's last
    clause played, is not answered; it is still closed, transcribed and kept on the timeline.
    The 300 ms count from the reply's last `ClausePlayed`, when its audio left the output
    transport, which a WebRTC call and a file-fed one both know, not from the browser's
    playback report, which comes a jitter buffer later and never in a file-fed call.
  - **The file-fed call** feeds silence until the greeting has played (its last `ClausePlayed`
    or `ClauseFailed`), then the clip's lead (`lead_s`; the registration's 1 s), so the clip
    never overlaps the greeting. The greeting is a fixed phrase, played from the phrase audio
    the calls were built with; the requests that synthesized it are the phrase cache's,
    counted in run T's budget as `PhraseCache.declare` returns them (one for each request it
    packed, none for a phrase its folder held), and `echo_timings` takes that phrase audio
    (`phrases`), so no fixed phrase sends a request there. `turn_ends`' call plays no
    greeting: its phrase audio is silence of no length, so its lead starts once the call is
    connected, and `poe eot`, an offline run, synthesizes nothing. Each command it records
    carries when it reached `Commands.run`, so "the echo's text ready" is the time of the
    heard words' `Speak`. Set aside: an option for a file-fed call with no greeting, which
    would make the measured call differ from a live one; and `turn_ends` taking the phrase
    cache's audio, under which `poe eot` would synthesize the greeting, which moves no turn
    end.
  - **Every request counted.** The speech-to-text bridge hands `Transcribing(turn_id, at,
    audio_s)` as each request goes, and the text-to-speech bridge `Synthesizing(reply_id,
    clause, at)` as it sends a clause's request, each before that turn's or clause's other
    events, whatever comes of the request; `Transcribed.sent_at` and
    `ClauseQueued.requested_at` equal their report's `at`. The session counts each model's
    usage from them alone: a speech-to-text request, its audio seconds, and at least 10 s
    billed a request (the design's 10.4); a text-to-speech request and its `Speak`'s
    characters; a phrase played from the cache is a cache hit. Set aside: counting from
    `Speak`, which counts clauses queued behind at the end or dropped by a stop and never
    sent; and dropping `sent_at` and `audio_s` from `Transcribed`.
  - **The end.** The call ends at the first of an `Ending` or a `TransportFailure` the
    Pipecat side hands, or the session's `HangUp`, whatever ended it. From then the Pipecat
    side starts nothing and finishes nothing: it drops the held audio of a turn still open,
    or closed with its transcript still to come, and sends no request for it, drops every
    clause's queued audio, and cancels any request in flight; it hands the session no
    `TurnClosed` or `Transcribed` of such a turn and no clause event after the end. The
    call's report keeps the turn as unfinished (`TurnRecord.unfinished`, a field of the
    provisional `CallReport`), counts a reply the end cut as done, and counts every request
    that went, a cancelled one included, from the `Transcribing` or `Synthesizing` handed as
    it went. The session's last command is `HangUp`, given at once at an `Ending` or a
    `TransportFailure`; after the end only those request reports come, and the Pipecat side
    then ends the call's stream with `Session.aclose`, once, where the session finishes and
    writes its report, giving no command. Set aside: sending the turn to Whisper after the
    end, which bills a request and hands an event after `HangUp`; not counting a cancelled
    request, which leaves the report's `requests_per_minute` under what the key was asked;
    handing every held event until the stream ends, which would need a rule for each kind
    after the end; `Commands.run(HangUp)` returning once the stream has drained, which
    deadlocks a session that awaits it inside `handle` while events come one at a time; and
    a last event after `HangUp`, which blurs `Ending`'s meaning.
- **Consequences:** plan 003's Tracks D, E and G key the agent's speech on its reply and clause
  (the session, the speech bridges, the widget's playback reports), and Track H counts the
  lead from after the greeting. Track E hands each request's report as it goes and ends each
  call's stream with `aclose`, and Track D counts usage from those reports and writes the
  report there. `voice/session/io.py` says the rules, and the `t2v/1` fixture pins the fields.
  The design's 5.5 (a caption's turn ID) and 6.6 (every event's `turn_id`) do not say so.
- **Evidence:** the review of plan 003's Block 0 and the check of its fixes (2026-11-03). The
  tests: `tests/t2_agentic_voice/test_session_scenes.py` (the greeting with a turn that opens
  while it plays, a call that ends with a turn open, and the stop, hang-up and usage scenes),
  `tests/t2_agentic_voice/test_session_fakes.py`,
  `tests/t2_agentic_voice/voice/session/test_io.py` and
  `tests/t2_agentic_voice/test_protocol_list.py`.

## D-038 · A call's language is fixed at join · 2026-11-03 · Amended by D-103 (the call's language may move, 2026-11-16)

- **Context:** live calls send Whisper the call's language, from the language the caller picks
  in the widget and the token's `locale` (`stt.live_language = "session"`, plan 003's decision
  log). Block 0 gave no `t2v/1` message or body a field for the pick, gave the session no
  language, and said nothing of how a locale such as `en-US` or `ar-EG` meets the agent's tags,
  while the declaration promised a pick in the middle of a call. The review of plan 003's
  Block 0 found it (2026-11-03).
- **Decision:**
  - In M2 a call is held in one language from its join to its end, since the echo has no
    other; the talker, which comes in M4, will pick each reply's (the design's 16.1, reply
    language).
  - `POST /join`'s body takes an optional `language`, the caller's pick, one of the library's
    tags (`ar-SA`, `ar`, `en`), parsed strictly: any other is `invalid_request`. The client's
    language buttons set it before `/join`.
  - `VoiceAgent.call_language(requested, *, locale)` resolves it once, in `domain`: the
    requested tag when the agent speaks it; else the caller's locale from the join token,
    matched in any case, its exact tag first, then the first of the agent's languages whose
    primary language is the locale's primary subtag (`ar-EG` reaches an Arabic preset, `en-US`
    English); else the agent's first language. `/join` resolves it after `verify`, and `api`
    keeps it with the call until its offer.
  - The session's set-up (`CallSetup.language`) and voice's entry point
    (`Calls.answer(..., language=)`, and the file-fed call) carry the resolved `Language`, not
    its tag, so the session reads its greeting, frame, notices and primary code with no lookup.
  - Set aside: a `language` message in `t2v/1` to switch in the middle of a call, which the
    echo cannot use.
- **Consequences:** a `DevIdentity` caller, who carries no locale, gets the agent's first
  language unless a button picks another. `/join`'s body cap holds a tag. The design's 5.5
  (`/join`'s body) does not name the field.
- **Evidence:** the review of plan 003's Block 0 (2026-11-03). The tests:
  `tests/t2_agentic_voice/domain/test_declaration.py` (the pick, then the locale, then the
  first language) and `tests/t2_agentic_voice/test_session_fakes.py`.

## D-039 · `t2v/1`'s data-channel messages, parsed strictly · 2026-11-03 · Accepted (the owner, 2026-11-01, as the design's 5.5; one bullet Proposed)

- **Context:** the design's 5.5 gives `t2v/1`'s messages on the WebRTC data channel, JSON each
  carrying `"v": 1`, from a closed list, as pydantic classes in the library, provisional but
  for the version check at join (its 5.4). Plan 003's Block 0 modelled them in
  `voice/protocol.py` (step 10) and pinned them in a fixture (step 11); D-029 holds the HTTP
  side. The review of plan 003's Block 0 (2026-11-03) found the size bound counted characters,
  and never applied on the path a call takes; the check of its fixes (2026-11-03) found that
  on that path Pipecat has parsed the channel's text before any bound of ours, so neither the
  text's size nor a key held twice reaches the session as sent.
- **Decision** (as the design's 5.5 describes it):
  - Server to client: `hello` (the protocol, in `v`, the call ID and its languages), `state`,
    `caption` (sent per clause as each plays), `notice` (`busy`, `error`, `ended`, with the
    text in the call's language) and `ended` (the reason); client to server: `hello` (the
    protocol, in `v`, and the client's version), `stop`, `hangup` and `client_stats`. `duck`,
    `unduck` and `card` wait for the milestones
    the design's 16.1 gives them. No client message sets the caller's identity or consent.
  - **Proposed** (the agent's, beyond the design, for the owner to rule on; plan 003's decision
    log has the reasons):
    - The client's playback reports are one `playback` message (a reply, a clause, and
      `started` or `ended`), and an agent's caption names its reply and clause (D-037), so a
      report names one clause. The client's `hello` carries `client`, its name and version,
      since `v` carries the protocol. No message is typed `signalling` and none starts with
      `ping`, the names Small WebRTC keeps for itself.
    - A client's message is parsed strictly: one of the client's types, exactly its fields,
      each of its JSON type (no "1" or 1.0 for an integer, no 1 for a boolean), `v` the integer
      1, every size bounded, and, on the text path, a key held twice refused (on the object
      path a call takes, Pipecat's `json.loads` has already kept its last value). The message
      as the session gets it is at most 1024 bytes of UTF-8: on a call's path, the object
      Pipecat's Small WebRTC parsed before handing it on, written back as compact JSON; on the
      text path, the text's own bytes. Pipecat parses the channel's text first, with no bound
      of ours (up to the transport's message size: aiortc advertises 64 KB), and holds the
      messages that come before the call connects, so a message padded with whitespace past
      the bound reaches a call within it. A refusal is an `InvalidRequestError` whose details
      name only its kinds (`too_large`, `json_invalid`, `duplicate_key`, or pydantic's error
      types), never the client's text. Set aside: having `voice` read each message's raw text
      before Pipecat parses it; the object is what Pipecat's `on_app_message` hands on.
- **Consequences:** the session and the widget build against one list, which the fixture
  `tests/t2_agentic_voice/fixtures/t2v_protocol.json` pins, and a change to `t2v/1` changes it
  in the same commit. The design's 5.5 lists neither `playback` nor a caption's reply.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01. The tests:
  `tests/t2_agentic_voice/voice/test_protocol.py` (among them
  `test_a_key_held_twice_reaches_a_call_with_its_last_value` and
  `test_a_message_padded_past_the_bound_reaches_a_call_within_it`) and
  `tests/t2_agentic_voice/test_protocol_list.py`.

## D-040 · Requests per call minute for each Groq model, measured, and the key's headroom · 2026-11-04 · Proposed (the agent's reading of plan 003's step 18 session, for M6's cap on live calls)

- **Context:** the design's 16.3 asks M2 for the requests a call makes in a minute for each Groq
  model, beside the key's limits, so that M6 can set the cap on live calls. Groq publishes its
  developer plan's limits: Whisper large-v3 20 requests a minute, 2K a day, 7.2K audio seconds an
  hour and 28.8K a day; each Orpheus model 10 requests a minute, 100 a day, 1.2K tokens a minute and
  3.6K a day (console.groq.com/docs/rate-limits, read 2026-11-04). The prototype found the key on
  Groq's on-demand tier, 400 requests a minute, not saying for which models
  (`Ole5-chatbot/VOICE_LOG.md`, line 361, 2026-10-27). The owner did not read the key's own limits
  (plan 003's Q17, optional).
- **Decision** (the measurement, the owner's six echo calls of 2026-11-04, 3.45 call minutes):
  - Whisper: 26 requests, one per transcribed turn (D-034): 7.5 a call minute over the session, 4.9
    to 10.1 per call (median 7.2). Each is billed 10 s, for 2.3 s of audio on average (58.6 s sent,
    260 s billed), so about 75 billed seconds a call minute.
  - Orpheus, each model in its own language's calls: 12 Arabic requests in 1.95 call minutes (6.2 a
    minute; 6.1 to 6.5 per call) and 9 English ones in 1.49 (6.0; 4.9 to 7.6 per call), one per
    echo, the frame and the notices from the phrase cache (27 cache hits); about 150 characters an
    Arabic call minute and 140 an English one.
  - The key's headroom, from Groq's rate-limit headers on every answer, which the same page says
    give requests per day and tokens per minute: Whisper 199,999 requests left after each request,
    so a daily limit of at least 200,000; each Orpheus model 99,999 left, so at least 100,000 a day,
    and 49,944 to 49,997 tokens left in the minute, so about 50,000 tokens a minute. The headers
    give no requests per minute and no audio seconds, so the published 20 and 10 requests a minute
    and 7.2K audio seconds an hour stay the bound until the console is read.
- **Consequences:** per day the key's limits are far from binding (the published 100 Orpheus
  requests a day would have held about 16 call minutes), and the headers' daily limits fit the
  prototype's on-demand tier rather than the published table. Per minute they bind, and are not
  known: at the peak of 10 Whisper requests a call minute, the published 20 hold about 2 echo calls
  at once on one key and Orpheus's 10 about 1.6 in one language, while 400 a minute for each model
  would hold about 40 and 60. So M6 reads the key's limits a minute in Groq's console (Q17) before
  it sets the cap on live calls; a cut-off or a long pause adds a Whisper request, and M4's talker
  adds its own model's. Plan 003's estimate (6 Whisper requests a minute, up to 12 with cut-offs,
  and 6 Orpheus requests) holds.
- **Evidence:** the six `CallReport`s under the main checkout's `var/reports/` (each `usage` row's
  requests, audio and billed seconds, characters, cache hits, and the headers' `remaining_requests`
  and `remaining_tokens`; `requests_per_minute`), and plan 003's progress log, 2026-11-04.

## D-050 · Voice for a team's existing agent: a second, agent-led mode, after the Ole5 Voice Agent · 2026-11-02 · Accepted (the owner, 2026-11-02, as the direction and the order; the mode's open choices are decided when its phase is planned)

- **Context:** in a meeting the owner relayed on 2026-11-02, a manager set the library's
  ultimate goal: teams install it, plug in their existing LangChain or LangGraph agent, and talk
  to it live, without rebuilding it. D-012 chose a dedicated voice agent, "not a voice shell
  around a chat agent", and D-014 left plugging in a teammate's agent for later. The agent's
  studies that day found that lifting a team's tools into our talker loses what their agent
  does; the owner: "we need to use the agent as is", and "if we can not reliably let their
  agent execute actions with the user permission then we didn't do it as we should". Reading
  LangGraph's source showed a way to do that for writes made through tool calls, without
  changing their code.
- **Decision:**
  - Two modes on one voice layer. The native mode is the talker as designed, for Ole5 and
    every new voice agent. In the agent-led mode a team's LangGraph graph runs as is, on one
    thread per call, behind the same voice layer
    ([agent-led-mode.md](agent-led-mode.md)).
  - The order. The owner, 2026-11-02: "I have decided to finish the first mode (pure voice with
    its tools) first and finish our use-case Ole5. The we can do the one where they can use
    their text-based agents as a next phase to focus on later." On the design: "I think your
    last idea is the most reasonable so record it to return to it later."
  - The direction recorded with it. Their agent makes a write only through a pause before its
    tool step that our yes rule releases, after a read-back of the exact arguments. Their own
    permission design is never relied on alone. Read-only agents are the floor and come first.
    The talker is not built on LangChain or LangGraph.
- **Consequences:** M2 to M7 change by two notes: M5's consent core keeps a place for a second
  executor, and M4's plan weighs keeping fixed spoken lines free of command, yes and listening
  words and the talker's tool list small. The design's progress-line example in 4.4 used two
  wait words and is fixed. D-012 holds for the native mode, and the agent-led mode is recorded
  as a second mode beside it. D-015's thinker keeps "never acts": the agent-led mode is not the
  thinker. The phase's plan settles the open choices in agent-led-mode.md and records the
  amendments it needs (D-012 for this mode, the contract's rows, D-014's later options, the
  thinker's place in D-018's answer 16), each in an entry of its own.
- **Evidence:** [agent-led-mode.md](agent-led-mode.md): approach 2's record, LangGraph 1.2.19
  and langchain 1.4.7 read in their source (nothing was run), and four studies by the agent on
  2026-11-02, each checked by a red team and a fact-checker.

## D-060 · Each reply runs in one cancel scope · 2026-11-03 · Accepted (the owner, 2026-11-03, approving plan 005; one bullet Proposed)

- **Context:** the design's 3.1 gives "one cancel scope per turn", and the roadmap's M3 "the
  cancel scope of every turn: a stop, a correction, or new words cancel the model, the speech,
  and read-only lookups at once"; its 6.4 runs an action's write as a job outside the turn.
  D-037 keyed the agent's speech on replies, numbered apart from the caller's turns: the
  greeting and each spoken notice answer no turn, and a stop drops every reply asked for so far.
  Plan 005, approved by the owner on 2026-11-03, asked for one scope per reply, the work that
  answers a turn starting inside it.
- **Decision** (plan 005's criterion; `voice/session/scope.py`):
  - The session opens one `CancelScope` for each reply it asks for (the greeting, each echo,
    each reply said again, each spoken notice), and the work that answers the caller's turn
    starts inside its reply's scope, whatever that work is: the talker's model stream and its
    read-only lookups from M4, or a team's agent in the agent-led mode (D-050). So a scope takes
    any coroutine, not only the talker's.
  - A stop cancels at once everything working for the replies it drops: `StopSpeaking` drops
    their speech and the text-to-speech requests still queued (D-037's stop path), and each
    reply's scope cancels every task it holds, then awaits them; a scope cancelled starts
    nothing more. The stop also tells the widget (`state`, and the clause it cut: D-065) and
    emits one `Interrupted`.
  - Work started outside a scope is never cancelled by one: an action's write, a job of
    `actions` from M5 (the design's 6.4).
  - **Proposed** (the agent's, beyond the design and the plan; plan 005's decision log has the
    reasons):
    - A stop waits for the scope's tasks at most 100 ms on the call's clock (`CANCEL_WAIT_S`).
      A task that has not ended by then (it suppresses its cancellation, or waits on a worker
      thread, which cannot be cancelled) is logged by its name alone (`scope_tasks_left`) and
      left to end on its own, the scope holding it, so it is never collected mid-run, and
      reading its outcome when it ends; a task's failure is logged by its kind, never its text.
    - A reply's scope is cancelled whenever the reply ends, however: played whole, stopped, or
      cut by the call's end. So M4's talker keeps its reply open while its work runs, or that
      work is cancelled with it.
    - Set aside: a scope per turn, under which the greeting and the spoken notices, which answer
      no turn (D-037), would have none.
- **Consequences:** in M3's echo no task runs inside a scope: a reply's work is its speech and
  its text-to-speech requests, which the stop path drops, so the first tasks a scope holds are
  M4's talker's. A turn whose reply a stop cut before any clause played whole is marked in the
  heard history (D-064), so the agent-led mode can roll it back. The design's 1.2 and 3.1, which
  said "per turn", say "per reply" since plan 005's close.
- **Evidence:** the tests `tests/t2_agentic_voice/voice/session/test_scope.py` (a slow model
  stream and a slow lookup cancelled within the bound on the fake clock, no task left, work
  outside the scope going on), `tests/t2_agentic_voice/voice/session/test_overlap_stop.py` (the
  same through the session, by the rule's stop and by the caller's own), and plan 005's step 9,
  `tests/t2_agentic_voice/test_loopback_interruptions.py` (plan 005's progress log, 2026-11-04).

## D-061 · The two-step interruption, its settings and its rule · 2026-11-03 · Accepted (the owner, 2026-11-03, approving plan 005 and its Q3 and Q4; `interruptions.mode` defaults to `two_step` by the owner's ruling of 2026-11-06, D-068; two bullets Proposed)

- **Context:** Groq's Whisper transcribes a finished clip, with no partial transcripts (D-004),
  so the caller's speech over a reply cannot be read word by word as it comes. The design's 3.1
  and 5.5 give a two-step interruption: the agent's voice lowered at once, then a decision from
  the transcribed overlap; its 7.6 gives the `interruptions` and `words` groups. M2's drop rule
  (D-037) answered no turn that began over a reply, so the agent never answered its own voice.
  Pipecat's own interruptions stay off, and only the session stops speech (D-018, answer 8).
  Plan 005, approved by the owner on 2026-11-03, registered the flow, its settings and a
  starting rule; its Q3 settled the targets, and its Q4 the short output.
- **Decision** (plan 005's criteria and its "The starting rule"):
  - **The overlap.** Under `interruptions.mode = "two_step"`, a turn whose speech began while a
    reply played, or within 300 ms after its last clause played (D-037's tail; none after the
    caller's own `stop`), is an overlap of that reply. The session sends `duck` at once, at the
    speech detector's onset (D-065), and asks for the overlap's transcripts (`HearOverlap`).
    The speech-to-text bridge sends at most two Whisper requests for it: a **window**, the first
    `first_window_ms` (750, plan 002's run W3) counted from 300 ms before the speech began, when
    the speech still goes on by then; and the **whole overlap**, as soon as the speech detector
    hears the speech stop (after `turns.vad_stop_ms`, 200 ms), never waiting for Smart Turn.
    When no speech follows the whole overlap, the turn's own transcript reuses it, with no
    request; when speech follows, the turn sends its own, as any turn does.
  - **The verdicts.** The rule judges the window's transcript, then the whole overlap's; a
    window's verdict decides only when it stops the agent. *Stop:* every reply in progress is
    dropped (`StopSpeaking`, each one's scope cancelled: D-060), `unduck` right after, the clause
    playing captioned again as cut (D-065), and one `Interrupted`; a stop or wait word's turn is
    a command, never said back, while new words or a correction are answered. *Repeat:* stopped
    as above, then the last reply the caller heard said again (D-064). *Go on:* `unduck` once
    the whole overlap's transcript has come, the turn not answered, and an `Interrupted` of
    kind `false`. Every `duck` ends with exactly one `unduck` once its overlap is decided, none
    while another overlap of the call is still undecided; an overlap the call's end cuts gets
    none, and the client restores its volume at the end.
  - **The rule** (the registered starting rule, read on the canonical normalizer's form, each
    listed phrase one word): (1) no words, or text from silence (D-063): go on; (2) a stop or
    wait word anywhere, or the stop word as Whisper mishears it over the agent's voice (one or
    two short Arabic words ending in «قف», «كف» or «غف», with no question or no word): stop;
    (3) a repeat request: stop, then repeat; (4) the agent's own words, each word within one
    edit of a word of the clauses that played in the last `own_words_s` (5 s) or of the one
    playing: go on; (5) listening sounds only: go on; (6) a short output, at most
    `short_words` (2) words under `short_s` (1.6 s) of speech, none a stop, wait, repeat or no
    word, asking no question: go on (Q4, (a)); (7) at least `min_words` (2) real words, a
    listening sound counting as none: stop, a correction when the first is a no word; fewer:
    go on. Its one registered revision (D-068) added a spelling to step 2's mishearings and one
    to the Arabic listening sounds, and moved `short_s` to 1.2 s.
  - **Settings.** The `interruptions` group: `mode` (`two_step` or `drop`, M2's rule),
    `duck_level` (0.25, the prototype's), `first_window_ms` (750), `min_words` (2),
    `short_words` (2), `short_s` (1.2 since the revision; 1.6 as registered) and `own_words_s`
    (5.0). The `words` group adds a team's words to each language's lists (D-062). As
    registered, `mode` was to default to `two_step`, in a commit of its own, only once the
    registered targets held on held-out and on M2's call recordings (plan 005's H3 and C3), a
    target that failed going to the owner with its numbers (GP-18). Two failed on held-out, and
    the owner ruled for `two_step` as the default all the same (afb6864; D-068).
  - **Proposed** (the agent's amendments of the registered rule, each dated and made before any
    result; plan 005's registration has them, (1) to (7)):
    - Step 2 goes on, as the agent's own words, when each stop or wait word heard is exactly a
      word or listed phrase of the clauses that played, another word was heard beside them,
      and every word is the agent's own; step 3 goes on when each repeat word heard, or it
      after «و», is a word of those clauses, or when a repeat-only transcript meets a played
      clause that holds any repeat word; «وقفت» joins step 2's noisy spellings, and the
      spellings only Whisper writes for the stop word count only as a whole short utterance
      (1). The echo says back what it heard, so a reply can hold any word the caller said.
    - A turn said while the agent is silent is read for a whole command: a repeat request,
      with only polite words and listening sounds beside it, says the last reply again; an
      utterance of only stop or pause words is not said back; a sentence that holds one of
      them is answered (2). Such a command, from a turn whose speech began before a reply to an
      earlier turn started, first stops the replies in progress to earlier turns, with one
      `Interrupted`, never a reply to its own turn or a later one (7).
    - "Whisper requests per interruption" counts the window and the whole overlap; the window
      falls due 450 ms after the speech began, so most stop words cost both (3). The dev
      talk-over clips' stops are timed from the detector's stop, the registered stop times read
      on marked stops (4).
    - The rule is applied to the window's text, then to the whole overlap's, whatever the
      window decided; after a window's stop, the whole overlap's verdict decides only what
      follows the stop, its new words or correction answered from the turn's own transcript,
      since a window may hold only a request's first word (5). A repeat the window decided
      waits for the whole overlap, so it never starts while the caller still speaks.
    - When speech followed, in the same turn, the part whose stop, pause or repeat request
      decided the overlap, the turn's own transcript is read with that request taken off (its
      leading command words, and the polite words and listening sounds among and after them):
      after a stop or pause word, a whole repeat request says the last reply again, a stop or
      nothing leaves the turn a command, and anything else is answered, the echo saying back
      only what followed; after a repeat request, what followed is answered only when it is no
      whole command and holds at least `min_words` words, else the repeat stands (6). No
      request is added. After a verdict to go on, the turn's own transcript is judged again
      when speech followed it.
  - **Proposed** (the agent's, beyond the design's 6.6 and 7.6): the `interruptions` keys
    `short_words`, `short_s` and `own_words_s`, the rule's constants made settings;
    `Interrupted.reason`, the step that decided, and an `Interrupted` of kind `false` for each
    overlap that went on; and a rule that raises (a bug) decides its overlap as going on, logged
    by its kind with no text, so its `unduck` follows.
- **Consequences:** under `drop`, M2's session scenes give the same commands as before (GP-18):
  a turn over a reply is still not answered; `two_step` is the default since 2026-11-06, and
  `drop` a team's to choose. The Stop button and Esc stop the agent at once under either mode.
  The design's 7.6 lists these keys, and its 6.6 `Interrupted`'s `reason`, since plan 005's
  close. M4's talker takes over what an interruption means beyond the fast stop (the roadmap's
  M4, "From M3").
- **Evidence:** the owner's answers of 2026-11-03 to plan 005's Q1 to Q7: "Go with your
  recommendation for Q1, Q2, Q3, Q4, Q5 and Q7." The tests:
  `tests/t2_agentic_voice/domain/test_interruptions.py`, `test_interruptions_echo.py` and
  `test_whole_commands.py` (each step, on texts written for the test);
  `tests/t2_agentic_voice/voice/session/test_overlap.py`, `test_overlap_session.py`,
  `test_overlap_order.py`, `test_overlap_after.py`, `test_overlap_follow.py`,
  `test_overlap_stop.py` and `test_commands_alone.py` (the rehearsal's steps 1 and 2 end to end);
  `tests/t2_agentic_voice/voice/test_stt_overlap.py` (at most two requests decide an overlap);
  and plan 005's step 9, `tests/t2_agentic_voice/test_loopback_interruptions.py` (a stop word
  over a long reply reaching the output within 30 ms, at most four 10 ms frames of the reply
  leaving the server's track after it).

## D-062 · The language presets' words, under the owner's ruling on Q1 · 2026-11-03 · Accepted (the owner, 2026-11-03, plan 005's Q1, (a); one bullet Proposed)

- **Context:** the design's 3.1 gives each language preset its stop, repeat, listening, yes, no
  and send words; its 4.3 a team's additions in the declaration (`phrases=`), and its 7.1 and
  7.6 additions in the settings (`words`). The words the rule needs («وقف», «تمام», "okay",
  "wait") are also one-word items of Ole5's golden set, which the test that no item's text is in
  the source refuses; plan 003's Q6 left the presets' words to M3. Plan 005's Q1 offered one
  ruling for the lists written from the prototype's, a ruling per word, or the held-out words
  left out of the presets.
- **Decision:**
  - Q1, (a), the owner's answer of 2026-11-03: one ruling covers the lists, written from the
    prototype's (its `voice/rules.py`, read only: D-010). Each word of them that an item's
    reference or a script line holds as its whole text is an entry of
    `apps/ole5-voice-agent/evals/allowed_in_source.toml` quoting the ruling (16 entries). Those
    items then measure how the rule meets Whisper's mishearings, not whether the word is
    listed.
  - Each preset carries five lists for the rule, by its primary code (`ar` for both Arabic
    presets, `en`): `stop`; `wait`, the words asking the agent to pause, which stop it as a stop
    word does; `repeat`; `backchannel`, the listening sounds; and `no` (`domain/words.py`'s
    `PRESET_WORDS`, the public `Words`). A team adds words in its declaration
    (`VoiceAgent(phrases=Phrases.defaults().extend(stop={"ar": [...]}))`) or in the `words`
    settings group, a JSON map by language code in the environment; a call's lists are the
    preset's, then the declaration's, then the settings', each kind in that order, none twice.
    Yes and send words come with the yes rule (M5).
  - **Proposed** (the agent's, from Track A as its review let it stand; plan 005's decision log):
    - The lists are per script: `ar`'s in Arabic letters, `en`'s in Latin, the Latin spellings
      Whisper writes for Arabic commands in an English call ("wagif", "lahza") among them, all
      written in the rule's form (the canonical normalizer's).
    - The words a preset's fixed phrase holds («ثانية», "say that again", which its notices
      say) are left out of its lists, so the echo of a notice stops nothing; a test holds every
      preset's greeting, frame and notices to it.
    - A repeat word counts only in a whole repeat request, a stop or pause word anywhere, and a
      listening sound is no real word in the rule's step 7. A team's words are brought to the
      rule's form when compared, never refused for their spelling. The spellings only Whisper
      writes for the stop word (`domain/interruption_words.py`) sit outside the lists and count
      only as a whole short utterance.
- **Consequences:** the design's 3.1, 3.3 and 7.6 gave the presets and the `words` group yes and
  send words, which wait for M5, and no `wait` list (3.3 and 7.6 no `repeat` list either); since
  plan 005's close they name the five lists M3 builds. Ole5's app sets no additions so far: the presets hold the
  prototype's words. M4's plan weighs keeping
  the talker's fixed lines free of these words (D-050).
- **Evidence:** the owner's answer of 2026-11-03 (plan 005's "The owner's decisions"). The
  tests: `tests/t2_agentic_voice/domain/test_words.py` (the lists in the rule's form, each word
  once and of one kind; no preset's fixed phrase holds a word its echo would stop the agent on),
  `tests/t2_agentic_voice/voice/session/test_overlap.py` (a call's words: the preset's, the
  agent's and the settings') and `tests/ole5_voice/evals/test_no_item_in_source.py`.

## D-063 · The filter for text from silence, on by default · 2026-11-04 · Accepted (the registered rule F, plan 005)

- **Context:** in M1 every silent, noise and echo clip came back from Whisper with text, such as
  its invented captions (plan 002's Future improvements), and M3's rule must not stop the agent
  for words written over audio that holds none, nor the echo say them back. Plan 005 registered
  the rule F before any run: on plan 002's stored scorecards of R1 and R3, `stt.no_speech_max`
  = 0.5 and the caption list (the prototype's, its `voice/stt.py` lines 35-54, with «موسيقى»,
  music) are on by default if, on both runs, they blank at least 3 of the 9 empty-reference
  variants and none of the 222 speech variants.
- **Decision:** a transcript is text from silence, and counts as no words for a turn and for an
  overlap, when it holds no word at all, when Whisper's `no_speech_prob` for it is above
  `stt.no_speech_max`, or when it is, whole, one of the captions Whisper invents for silence or
  noise (`domain/silence.py`'s `CAPTIONS`, under `stt.caption_filter`). F held: on both R1 and
  R3, the threshold and the list blank 6 of the 9 empty-reference variants and none of the 222
  speech variants, with no request spent. So the defaults moved in a commit of their own
  (2b901fd; GP-18): `stt.no_speech_max` 0.5 and `stt.caption_filter` on. A turn so heard is said
  back as nothing, and an overlap so heard goes on (the rule's step 1, D-061). Beside it, a
  clause with no letter or digit is never sent to text-to-speech (TD-060). The rule's one
  registered revision moved the threshold to 0.55, F's keep rule still holding there (6 of the
  9 and none of the 222, on R1 and R3), after a window holding a stop word had been blanked at
  0.523 (D-068).
- **Consequences:** a caption matches only whole, so a request that holds a caption's words is
  never blanked by the list. `stt.no_speech_max` unset turns the threshold off, and
  `stt.caption_filter = false` the list. The scorers' own measure of text from silence
  (`silence_output`, D-022) is unchanged. The design's 7.6 lists both keys since plan 005's
  close.
- **Evidence:** plan 005's progress log, 2026-11-04 and 05 (F, on R1's and R3's stored
  scorecards). The tests: `tests/t2_agentic_voice/domain/test_silence.py` and
  `tests/t2_agentic_voice/voice/session/test_turn_filter.py`.

## D-064 · The history of what the caller heard, and the repeat · 2026-11-03 · Accepted (the owner, 2026-11-03, approving plan 005; one bullet Proposed)

- **Context:** the design's 3.1 gives "a history of only what was heard", the roadmap's M3 "the
  history keeps only what the user heard, clause by clause", and the rehearsal's step 2
  ([DESCRIPTION.md](../project/DESCRIPTION.md)) asks the agent to say its last reply again. M4's
  talker takes its context from what the caller heard, not from what it asked to say, and the
  design's 6.6 gives `AgentSpeechEnded(text, played_fraction)`.
- **Decision** (plan 005's criteria; `voice/session/history.py`):
  - The session keeps, for each of the caller's turns, its heard words and what became of it,
    and for each of the agent's replies its clauses, each `played` (its `ClausePlayed` came),
    `cut` (playing at a stop or at the call's end, with the share of its audio played) or
    `unplayed`. A clause's words are never split: Orpheus gives no word times.
  - A repeat request (D-061) says again the last reply the caller heard any of, the one a stop
    just cut included, every clause of it, as the reply answering the request's turn, a
    command that is never said back. The `CallReport` (each turn's `said`) and
    `AgentSpeechEnded(played_fraction)` read the history, and M4's talker will take its context
    from it.
  - **Proposed** (the agent's, beyond the design; plan 005's decision log):
    - A turn's fate is one of `pending`, `answered`, `cut` (its reply cut after a clause played
      whole), `rolled_back` (cut before any did), `command` (a stop, pause or repeat request),
      `went_on` (an overlap the reply went on through), `dropped` (the drop rule) or
      `unfinished` (the call ended first); `rolled_back` marks a turn the agent-led mode (D-050)
      can roll back.
    - A clause counts as heard at its `ClausePlayed`, as D-037's tail counts. A cut clause's
      share is the agent's audio the output sent since it began playing, over its length
      estimated from the call's clauses played so far by their captions' characters (0.07 s a
      character before any played); a reply's `played_fraction` counts its clauses by
      characters.
    - The repeat says the reply again from its text: a fixed phrase (the echo's frame) from the
      phrase cache, the rest through text-to-speech, so it costs the reply's requests again.
      Keeping the reply's audio to play it again is set aside: a new store of agent audio,
      while a cut reply's audio was never all made; a debt row if Orpheus's limits bind in the
      live calls.
- **Consequences:** the history is the session's own and not public in M3: a team reads it
  through the `CallReport` and the events. The design's 6.6 gives `played_fraction` without
  saying how a cut clause's share is measured.
- **Evidence:** the tests `tests/t2_agentic_voice/voice/session/test_history.py`,
  `test_overlap_stop.py` (a cut clause's share, at a stop and at the call's end),
  `test_commands_alone.py` and `test_overlap_follow.py` (the repeat).

## D-065 · `t2v/1`'s `duck`, `unduck` and a caption's `cut`, and push-to-talk in the client · 2026-11-03 · Accepted (the owner, 2026-11-01, as the design's 5.5 and 16.1, for `duck`, `unduck` and push-to-talk; one bullet Proposed)

- **Context:** the design's 5.5 gives `duck` and `unduck` as "step one of an interruption", which
  D-039 left for the milestone that builds them, and its 16.1 a push-to-talk fallback in the
  client for M3. Plan 005 gave `duck` its level and a caption a `cut` mark, the protocol's
  fixture changing in the same commit (D-039).
- **Decision:**
  - Server to client: `duck` (`level`, from 0, silent, to 1, unchanged:
    `interruptions.duck_level`), sent at once when an overlap opens; `unduck`, sent once the
    overlap is decided, right after the stop when it stopped the agent (D-061). Both go as
    urgent transport messages, which a stop never drops (D-037), and only under `two_step`.
  - Push-to-talk in the reference client, off by default (`pushToTalk`, a property, and
    `talk(held)`): the microphone's track sends sound only while the page holds it, silence
    otherwise, and the call goes on; it sends no message. Ole5's widget has a switch for it,
    held with Space or a button: the fallback when the agent's voice comes back through a
    laptop's speakers.
  - **Proposed** (the agent's, beyond the design's 5.5; plan 005's decision log):
    - A caption's `cut`: under `two_step`, an agent's clause that a stop (the rule's, or the
      caller's Stop button) cut while it played is captioned again with `cut: true`; a caller's
      caption is never cut, and the model refuses one.
    - The reference client lowers the audio element's volume in one step, to the call's
      starting volume times the level, and restores it on `unduck`, on its own `stop()`, on a
      new reply's first caption and when the call ends, so no reply plays lowered whatever
      reaches it; each change is a `volume` event to the page, not a message. A cut caption
      ends its clause's playback report.
- **Consequences:** `tests/t2_agentic_voice/fixtures/t2v_protocol.json` pins `duck`'s level and
  a caption's `cut`; a client of `t2v/1` that ignores them still works, at full volume and with
  plain captions. The voice is lowered at the detector's onset, about 0.34 s into the speech
  (D-034's spike); the prototype found lowering better than pausing for what Whisper hears
  (`Ole5-chatbot/VOICE_LOG.md`, D53). The design's 5.5 gives `duck`'s level and the `cut` mark
  since plan 005's close.
- **Evidence:** the owner's approval of the design, 2026-11-01 (D-017, D-018). The tests:
  `tests/t2_agentic_voice/voice/test_protocol.py`, `tests/t2_agentic_voice/test_protocol_list.py`,
  `tests/t2_agentic_voice/test_browser_interruptions.py` and `tests/ole5_voice/test_widget.py`,
  which read the client and the widget as text; plan 005's live calls try them in Chrome.

## D-066 · `stt.live_language` stays `session` · 2026-11-04 · Accepted (the registered rule L, plan 005, as plan 003 registered it; a third value, `classified`, added by D-086)

- **Context:** a live call sends Whisper the call's language, fixed at join (D-038), under
  `stt.live_language = "session"`; `auto` sends none, for Whisper to detect it. Plan 003
  registered its runs R5 to R7 and their rule, with its Q15 for an outcome the rule leaves
  open; the owner moved them to M3 on 2026-11-03, and plan 005 kept the registration (its L),
  Q5 settling Q15 as (a) if the rule left it open. The noise had been measured on one evening
  only (D-024, TD-032).
- **Decision** (the measured numbers, as registered): on M1's dev split (66 items, 231
  variants), at one measurement commit (089fae9), A1 (`whisper-large-v3`, the item's label as
  the language) in R5 and R6 and A3 (no language sent) in R7, run R5, R7, R6 in that order:
  R5 99 of 231 right, R7 83, R6 99; each run 236 requests and $0.0748, no retry.
  - The noise first: R5 against R6, 0 items better and 0 worse (p = 1.0), so d = 0 again, on
    another day than D-024's.
  - The rule: A3 is worse beyond the noise in both comparisons, R7 against R5 and against R6, 0
    items better and 11 worse (p = 0.0010), the Saudi items and the laptop's worst, listening
    sounds and confirmations most. So `stt.live_language` stays `session`, where it already
    was, and no file changes; Q5 is not reached.
- **Consequences:** a call keeps sending Whisper the language it joined in, which the widget's
  language buttons pick. R7's smoke step read Groq's `language` as a name ("Spanish" for a
  Saudi listening sound), not a code (TD-011), which matters only under `auto`. Every number
  describes one speaker, the owner (D-006). R7 began 50 minutes after R5 ended, the laptop
  having slept, within the registered "at least 15 minutes".
- **Evidence:** the history lines of R5, R7 and R6 (`apps/ole5-voice-agent/evals/history.jsonl`),
  their scorecards under the main checkout's `var/runs/`, and plan 005's progress log, 2026-11-04
  and 05.

## D-067 · A hold after Smart Turn's "complete", 600 ms by the owner's ruling, the default once held-out confirmed it · 2026-11-05 · Accepted (the owner, 2026-11-05, over plan 005's E; `turns.complete_hold_ms` 600 by default since held-out E confirmed it the same day)

- **Context:** M2's end-of-turn baseline (E1, plan 005's progress log, 2026-11-04): with the
  default turn settings, Smart Turn cut 22 of the 23 dev paused requests, scoring the owner's
  pauses inside a request as complete (a median probability of 0.97 over 45 pauses) as it
  scores the true ends (0.96), so no threshold separates them; the pauses, as the speech
  detector hears them, last 220 to 720 ms. The owner had asked for the turn defaults to be
  tuned in M3 (Q6, (b)), and bounded how much later every turn may end at 600 ms at the median
  (Q8, (a), 2026-11-04: "Make it up to 600ms, it might change later if we found that its not a
  good choice."). Plan 005's E was amended before any arm ran ((8) and (9)): the arms Ea, Eb
  and Ec, a hold of 300, 500 and 600 ms after Smart Turn's "complete", cancelled when the
  speech resumes, the threshold staying 0.5; of several arms that pass, the one with the
  smaller median delay; held-out confirms by its aggregates before a default moves.
- **Decision:**
  - A new `turns` key, `complete_hold_ms` (at most 1000; 600 by default since held-out E, below):
    a turn Smart Turn judged finished ends only once the hold has passed with no speech; speech
    that resumes within it,
    as the speech detector hears it start, cancels the end, and Smart Turn judges again at the
    next pause, hearing the whole turn. It acts on the turn's end alone: the detector's 200 ms
    stop, which an overlap's decision waits on (D-061), is never delayed, and the silence
    fallback (`turns.smart_turn_stop_ms`) still ends a turn at once. At 0 a turn's end is
    Pipecat's own.
  - The runs, offline and with no spend, on dev's paused requests (51 variants, 20 items) and
    the secondary set (223 variants), with no miss in any: paused cut-offs E0 51 and 50 (its
    noise, 1 verdict of 51 and 1 of 223), Ea 39, Eb 22, Ec 9; against E0 by item, Ea 10 better
    and 0 worse (p = 0.0020), Eb 16 and 0, Ec 19 and 0; the median delay over timed variants,
    E0 none in its first run and 290 ms in its second (one variant), Ea 640, Eb 851, Ec 942 ms.
    The registered tie-break kept Ea, with 39 of 51 paused requests still cut.
  - Asked which hold should become the default, the owner, 2026-11-05: "600 ms". So Ec is the
    arm kept, by the owner's ruling over E's tie-break and over its 600 ms bound as read
    against E0's second run (+652 ms on its one timed variant; +466 to +600 ms read on every
    variant's first turn end at or after the owner's mark).
  - `turns.complete_hold_ms` was to become 600 by default, in a commit of its own, only once
    held-out E confirmed Ec by its aggregates (no more cut-offs than E0's). It did, the same
    day: on held-out's 28 paused variants of 10 items, E0 cut 27 and Ec 5, with no miss in
    either, Ec's delay a median of 933 ms (1,005 at the 90th percentile). So the default moved
    to 600 (8f1d762, merged as 35a82a0).
- **Consequences:** with the hold, every turn ends about that much later, and the echo (M4's
  answer) after it; a stop over the agent is not slowed. The hold rests on Pipecat 1.15.0's
  private paths (`voice/turn_hold.py` names them), which tests drive through the real strategy,
  and a Pipecat upgrade checks them. `turns.smart_turn_threshold` (0.5, Smart Turn's own) is a
  key too, with no arm moving it. E0's first run's Smart Turn decisions took about 220 ms
  against about 60 in its second, cause unknown. Smart Turn fine-tuned on the owner's turns
  stays in the roadmap's "Planned later". The design's 7.6 lists both keys since plan 005's
  close.
- **Evidence:** the history lines of E0 (twice), Ea, Eb and Ec, and of held-out E0 and Ec
  (`apps/ole5-voice-agent/evals/history.jsonl`), plan 005's progress log, 2026-11-04 and 05, and
  the owner's words in its "The owner's decisions". The tests:
  `tests/t2_agentic_voice/voice/test_turn_hold.py`, `tests/t2_agentic_voice/voice/test_turns.py`
  and `tests/ole5_voice/evals/test_eot.py`.

## D-068 · The registered results of the two-step interruption, and `two_step` the default at a plateau · 2026-11-06 · Accepted (the registered measurement and the owner's ruling, plan 005)

- **Context:** plan 005 registered, before any result, the targets of the two-step interruption
  (D-061; the owner's Q3, 2026-11-03), each to hold on O1's dev variants, on H3's held-out
  aggregates and on C3, M2's call recordings imported as golden items; O2, O1 again at the same
  commit, measured the noise. The arm: the replay (`AudioCall`, the `evals` facade) at real-time
  pace with the real `GroqSTT` (`whisper-large-v3`, the item's label as the language), a fake
  text-to-speech whose reply outlasts the clip, the clip 1 s into the reply, under
  `interruptions.mode = "two_step"`. The rule could be revised once after O1 and O2, as a dated
  amendment scored offline on their stored transcripts, before H3; a target still failing then
  went to the owner with its numbers, and `mode` was to default to `two_step` only once every
  target held.
- **Decision** (the measured numbers, one speaker, the owner: D-006):
  - **O1 and O2** (dev, at 35a82a0, O2 begun 62 minutes after O1 ended): 163 variants of 62
    items each, 128 right in both, no failed request, every variant on its first attempt; 324
    and 323 Whisper requests, $0.0999 and $0.0996. The noise: none of the 163 verdicts differs,
    and the marked stops' median moved from 393 ms to 435 ms.
  - **The revision** (amendment (10), registered after O1 and O2 and before its score; 8c44503,
    merged as 1d1cc97): `stt.no_speech_max` 0.5 to 0.55, F's keep rule still holding there
    (D-063); «وكيف» added to the stop word's mishearings and «كامل» to the Arabic listening
    sounds, each a spelling Whisper wrote for the owner's word; `interruptions.short_s` 1.6 to
    1.2 s. Scored on O1's and O2's stored transcripts, two verdicts changed in each run, both from
    wrong to right: 130 of 163 right. The new bound decided no verdict, since the rule times the
    session's speech, 0.79 to 0.97 s for the request it aimed at (the progress log's
    `Deviation:` line). Not revised, as no list or bound reads them without fitting a single
    take: «وانجح» and «حلو» for stop words, «اه» and «مشكلت» for repeat requests.
  - **H3** (held-out, once, aggregates only, at 1d1cc97; $0.0330): 62 variants of 24 items, 47
    right, no failed request. No variant that should let the reply go on stopped it (0 of 26),
    and 25 of the 36 that should stop it did.
  - **The targets,** on dev (O1 and O2, then the revision scored on them) and on held-out (H3):
    - Whisper requests per interruption, at most 2: **held** (a mean of 1.955 on dev and 1.926
      on held-out, in code at most 2).
    - From the end of the stop word to silence, on the marked stops, a median of at most 700 ms,
      a 90th percentile of at most 1,000 and none over 1,500: **held**. Dev's 11 marked stops: a
      median of 393 and 435 ms, a 90th percentile of 425 and 639, at most 494 and 751; held-out:
      486, 542 and 556.
    - Every «وقف» at normal volume stops the agent: **failed** on dev, 4 of 6 (Whisper wrote
      «وانجح» and «وكيف» on the laptop), 5 of 6 after the revision; not readable from
      held-out's aggregates.
    - At least 90% of the stop and pause words stop it: **held on dev** after the revision (34 of
      39, 87.2%, then 36 of 39, 92.3%); **failed on held-out**, 10 of 18 (55.6%).
    - At least 90% of the requests over a reply stop it: **failed** on dev, 60 of 74 (81.1%:
      every request and correction, 2 of 7 short requests, and 11 of 19 repeat requests, none
      of them repeated), unchanged by the revision; and on held-out, 15 of 18 (83.3%).
    - At most 10% of the listening sounds stop it: **failed on dev**, 5 of 38 (13.2%), unchanged
      by the revision; **held on held-out**, 0 of 19.
    - No echo, silence or noise variant stops it: **held** (0 of 12 on dev; none on held-out).
    - Nor the agent's own words, where their text is known: **not measured**, no such variant
      having opened an overlap in any run.
    - C3: the three dev call items were right in O1 and O2; the held-out one is read only in
      its group's aggregate.
  - In O1 and O2 every stop word and listening sound opened an overlap, so the speech detector's
    miss of a short word (TD-092) was not seen. The paid runs spent $0.4570 by H3, of the $5
    cap (Q7).
  - **The owner's ruling,** asked after H3 whether to make the two-step interruption the default
    and close at a plateau after the live calls, or keep it off and revise again on fresh
    recordings, 2026-11-06: "Yes make it the default and close. We might test other STT
    providers later and see if it any different, but this for another time and not in this
    milestone. Lets do the calls and Finnish M3". So `interruptions.mode` defaults to
    `two_step` (afb6864, merged as f9500be), the targets that failed accepted, and M3 closes at
    a plateau (evaluation.md, "Closing at a plateau"). The live calls passed the same day: "It
    is good, Everything works as intended", the owner's one complaint being Whisper's
    mishearing of short Arabic words.
- **Consequences:** a caller can stop the agent, or ask it to repeat, by speaking over it, and on
  held-out it never stopped when it should have gone on; what it misses, Whisper misheard: short
  command words, Saudi and MSA, and repeat requests seldom read as repeats. The Stop button and
  Esc stay the sure stop, and `drop` keeps the half-duplex call for a team that wants it. Every
  number describes one speaker on Ole5's golden set; a team measures its own callers with
  `AudioCall`. The owner, 2026-11-06, on what comes next: "The thing is that we don't really
  want to rely on "five or six command words" to interact with the system, our next step should
  be understanding the user request flexibly, but I think this is out of M3 scope." Plan 005's
  Future improvements put that first, then what would let the word rule, the fast path, hear
  short command words better.
- **Evidence:** the history lines of O1, O2 and H3 (3dbab64, 614ef41 and dc27b79, in
  `apps/ole5-voice-agent/evals/history.jsonl`), their scorecards under the main checkout's
  `var/runs/`, plan 005's progress log (2026-11-05 and 06) and its "The owner's decisions". The
  tests: `tests/ole5_voice/evals/test_overlap.py` (the `reference` answerer scores every committed
  overlap right at 0 ms, inside `poe check`) and `tests/ole5_voice/evals/test_overlap_score.py`.

## D-069 · A chat model decides the short overlaps the rule would let go on, on two or more words · 2026-11-08 · Accepted (the owner's ruling on run U, Q28 in plan 006, over run U's keep rule)

- **Context:** the two-step interruption's rule (D-061) lets a short overlap go on at its steps 6
  and 7 (`short_output`, `too_few_words`), so a caller who says «أبغى موظف» ("I want an employee")
  over a reply is ignored (run S's s09, 2026-11-08). Run U asked what a chat model would do with
  the overlaps the rule leaves there: on O1's 35 uncertain overlaps of 19 items, 15 of which
  should stop, U0 (the rule) got 20 right and stopped none of the 15; U2, `gpt-oss-120b` at low
  reasoning, got 25 right and stopped 8 of the 15, at a median of 177 ms, but failed run U's keep
  rule (the sign test: 3 items better, 2 worse), stopping 3 listening sounds, all single words
  («إيه؟» twice and a garbled one). On overlaps of two or more words only, U2 stopped 5 of the
  15, none wrongly, on O1's data. Asked after run U (Q28), the agent recommended the model on two
  or more words, single words keeping the rule; the owner chose that, over the keep rule.
- **Decision:**
  - The rule's steps stay as they are. When it goes on for `short_output` or `too_few_words` on
    the transcript that decides an overlap, and that transcript holds two or more words as the rule
    splits them (`domain/uncertain_overlaps.py`'s `is_uncertain`), a chat model decides,
    `gpt-oss-120b` at low reasoning, 256 output tokens, within 1 s on the call's clock. A single
    word, a window's transcript and the rule's own stops send nothing.
  - Off unless the agent asks: `VoiceAgent.ask_on_uncertain_overlaps`, False by default (a field
    on the declaration, not a setting, since every path through `talker_agent`, the server, run S
    and run T included, holds the agent, and `core/config.py` is near its size cap). Ole5's talker
    sets it; the echo, with no chat model, cannot.
  - The prompt that ran (run U's) moved into the library, so the eval and the call share it, the
    request is one of the call's chat requests (counted as the talker's are), and it runs in a
    cancel scope of the overlap's own, off the session's step lock, its verdict applied as a step
    of its own (`voice/session/overlap_ask.py`): the reply plays on, ducked, the overlap undecided
    until then, and the turn's own transcript waits for it.
  - `stop` stops the agent as new words, reason `model`, the turn's words going to the talker;
    `go_on`, anything else, a failure or the timeout leave the rule's verdict, logged by kind
    with no text. Each overlap still ends with exactly one `unduck`; a stop or the call's end during
    the wait cancels the request and nothing more happens.
- **Consequences:** a short request over a reply can now be answered; a two-word listening sound
  costs at most a model's answer (a median of 177 ms, 1 s at most) before the voice comes back,
  ducked meanwhile, and a request of Groq's per overlap so asked. No held-out replay was run: the
  numbers above are O1's dev data, the rest of the check being on the call's fakes.
- **Evidence:** run U's history line (at aedce08, in `apps/ole5-voice-agent/evals/history.jsonl`) and
  plan 006's progress log of 2026-11-08 and its Q28. The tests:
  `tests/t2_agentic_voice/voice/session/test_overlap_ask.py`,
  `tests/t2_agentic_voice/voice/session/test_overlap_ask_wait.py`,
  `tests/t2_agentic_voice/domain/test_uncertain_overlaps.py` and
  `tests/ole5_voice/test_uncertain_overlap_call.py`.

## D-070 · With a talker, a reply is kept while a newer turn of the caller's is open · 2026-11-07 · Accepted (the owner's ruling, Q19 in plan 006)

- **Context:** a turn the caller begins while nothing of the reply plays is no overlap of it
  (D-068's amendment 7), so when a search ended while the caller still spoke, the progress line
  and the first clauses played over them until their turn closed.
- **Decision:** from the newer turn's `TurnOpened` until it is taken, nothing more of that reply
  plays and what its talker gives is kept, in order. Heard with words, the turn stops the reply
  and both turns are answered; heard as nothing, or failed, what was kept plays. A stop or pause
  said whole stops it. This narrows D-068's amendment 7 for the talker only: the echo keeps M3's
  rule. While a reply to an earlier turn is in progress the newer turn has no early start, so
  the talker reads that reply as cut (TD-117).
- **Consequences:** a correction said over a search is never talked over. A reply kept behind a
  turn heard as nothing waits about 1.1 s after it, about 3.5 s when Smart Turn calls it
  incomplete. The remaining edges are TD-127.
- **Evidence:** plan 006's Q19 and its progress log; eaa44d5;
  `tests/t2_agentic_voice/voice/session/test_talker_kept.py` and `test_talker_kept_steps.py`.

## D-071 · The talker writes its answer from the top k passages whole, k measured for each app · 2026-11-07 · Accepted (the owner's ruling, Q20 in plan 006, and run K0); its card replaced by D-075

- **Context:** the knowledge tool gave the talker each passage's first 3 lines, cut near 400
  characters, and the best passage's steps: about 26% of each other passage's text, 122 of
  Ole5's 128 points cut. Knowledge bases are written to be read, not spoken, so the owner chose
  that the model formulate the answer itself from the retrieved passages, the full top k.
- **Decision:** `knowledge_tool` gives the talker each of the top `limit` passages whole, cut only
  past `passage_chars` (about 1,500), at the end of a line where it can. The best passage
  still goes to the caller as a card. The k is an app's, found on its own data: for Ole5,
  `SEARCH_LIMIT` is 7, the smallest k within 0.05 of k = 8's expected passages found (K0, 0.621
  against 0.651); the library's default stays 5.
- **Consequences:** the talker reads a median of 5,928 characters of passages at Ole5's k, 8,822
  at most. Retrieval stays a plain dense search; from the raw words, an expected passage is in
  the top 5 for 0.854 of the items, under K's 90% target.
- **Evidence:** plan 006's Q20 and K0's progress entry; a42848b, 84c3915, 7aa98e7.

## D-072 · Each chat request opens with a first line of its own · 2026-11-07 · Accepted (the owner's ruling, Q21 in plan 006)

- **Context:** plan 006 first chose no varying line, the spike having seen no slow cache path. In
  the live probe on Ole5's real prompt, 3 of 8 requests Groq served from its cache took 1.03 to
  5.71 s to the first token; 12 requests with a first line of their own took 0.15 to 0.30 s.
- **Decision:** `llm.vary_first_line`, true by default, opens each request's system message with
  a line new on every request, so no two requests share a cached prefix.
- **Consequences:** a reply's first token no longer waits on the slow cache path, at the price of
  Groq's half-price cached input. If the provider's cache improves, the setting turns it off.
- **Evidence:** plan 006's Q21 and its progress entry of the live probe.

## D-073 · The progress line by the caller's wait, 2.6 s after they stop, on the session's timer · 2026-11-08 · Accepted (the owner's ruling, Q27 in plan 006)

- **Context:** 59 of run T's T0's 67 search turns began after 2.0 s with no line: the line's clock
  was the tool's own, and the wait is mostly the model.
- **Decision:** `Tool.progress_after_s`, 2.6 s by default, counts from the end of the caller's
  speech, whether the search or the model holds the reply up. The line is said only if no clause
  was asked of the voice by then, the reply is not kept and no notice took its place. The timer
  is the session's, since only the session knows when the caller stopped and what was asked for.
  The target is 3.0 s; the line is set at 2.6 s since the cached lines open with up to about
  0.25 s of their own silence.
- **Consequences:** a clause already asked of the voice counts as the answer begun, so a reply
  asked for just before 2.6 s can be heard just after 3.0 s with no line before it. Run T on
  held-out (319c5d4) did not meet this target: 5 of 40 search replies had neither begun nor been
  preceded by a line by 3.0 s, and the line played in none of the 40; held-out keeps aggregates
  only, so the cause is not confirmed. The live calls are the first to hear it at this time.
- **Evidence:** plan 006's Q27, its decision log and the progress entry of 2026-11-09; run T's
  history line; `tests/t2_agentic_voice/voice/session/test_talker_progress.py`.

## D-074 · Live calls send the Whisper prompt, and `gpt-oss-120b` reasons at medium · 2026-11-08 · Accepted (the owner's rulings, Q23 and Q26 in plan 006)

- **Context:** run W's W1 (the agent's vocabulary, then the command words) met three of the five
  conditions set after dev (Q22); the other two could not be read from held-out's aggregates. An
  exploratory dev pass of run K put `gpt-oss-120b` at medium against low: 6 answers of 136
  invented against 18, for about 0.33 s more to the first clause.
- **Decision:** `stt.send_prompt` is on by default, each request sending its language's prompt
  (`whisper_prompt`, held to 224 bytes), and `llm.reasoning_effort` defaults to medium.
- **Consequences:** a term or command word that does not fit the prompt is left out. The live
  calls show whether the prompt holds; `stt.send_prompt` turns it off.
- **Evidence:** plan 006's Q22, Q23 and Q26 and their progress entries.

## D-075 · The caller only hears: every step is said, and no screen is relied on · 2026-11-09 · Accepted (the owner's rulings, Q30, Q31 and Q32 in plan 006)

- **Context:** the library told the model the caller "sees a screen beside the call" and never to
  read steps out; the steps went to a card. In run S's last pass 23 of 48 Arabic replies pointed
  the caller at the screen. The owner, listening: the agent is voice oriented and may run on
  voice-only channels, so looking at a screen is not to be encouraged. The owner's answer to how
  a caller gets the steps: "It should give all the steps in one reply, but be able to repeat
  all, repeat a specific step, or get in detail about one under the caller request. No card or
  screen is needed."
- **Decision:**
  - The library's rules and Ole5's instructions have a procedure said whole in one reply, in
    order, each step in one short sentence; said again whole, or one named step, or one step in
    more detail, when the caller asks; and never say that anything is on a screen or shown.
  - `knowledge_tool` shows no card. It gives the talker every step of the best passage under
    `best_passage_steps`, which it keeps for the rest of the call, so a later turn repeats a step
    with no new search. This replaces D-071's sentence on the card; the rest of D-071 stands.
  - The judge of runs K and S reads only what was said aloud (Q31), and the check of the judge
    against the knowledge base is an agent's, recorded as such, since the owner does not know
    the knowledge base well enough to judge it (Q32).
  - A team's own tool may still return a `Card`, as an extra for a client with a screen; nothing
    the library or Ole5 says depends on one.
- **Consequences:** a how-to answer is longer to hear, and the caller stops it by speaking
  (D-061). The Arabic voice costs more per reply. `llm.max_output_tokens`, 1,024 with the
  reasoning in it, must hold the longest procedure. Runs K and S before this entry credited the
  card and are not comparable with those after it on answer quality.
- **Evidence:** plan 006's Q30 to Q32 and its progress entry of 2026-11-09;
  `tests/t2_agentic_voice/actions/test_knowledge.py`,
  `tests/t2_agentic_voice/agent/test_prompt.py` and `tests/ole5_voice/test_agent.py`.

## D-076 · Ole5's page asks for no consent; the library's recording rule stays · 2026-11-09 · Accepted (the owner's ruling, Q34 in plan 006)

- **Context:** Ole5's page showed a consent screen before every call, its text still describing
  the echo. The owner: "any developer having access to and running this has already consented.
  it is tiring to manage that every time".
- **Decision:** the page has no consent screen. One box, off by default, asks to keep the call's
  audio, and the join token carries that choice as before. `CONSENT_VERSION` does not change, so
  no setting moves. The library's rule is unchanged (`docs/SECURITY.md`, invariant 8): no audio
  is kept unless `privacy.record_audio` is on and the signed token allows it. A team's page may
  still show its own consent screen.
- **Consequences:** this holds for the developers who run it. Before any other caller uses Ole5,
  a person decides what they must be told, their voice going to Groq, an outside company, and
  whether the law asks for more (the roadmap's M6).
- **Evidence:** plan 006's Q34; `tests/ole5_voice/test_server.py`,
  `tests/ole5_voice/test_widget_cards.py`.

## D-077 · What the owner's live calls changed in how the agent sounds · 2026-11-09 · Accepted (the owner's ruling on plan 006's Q35)

- **Context:** the owner's first three calls after D-075 and D-076 (13:42, 13:47 and 13:59 local
  time): Ole5 said wrongly, in Arabic even in the greeting; "←" badly handled; an English voice
  "out of breath"; Arabic words in English replies; the agent saying it did not know something
  the knowledge base holds; the error line and the answer each said at once after other speech.
  The calls were not traced, so what was said is not known; the reports give their timings. In 7
  of the 10 times the progress line played, the answer began within 0.1 s of its end.
- **Decision:**
  - Ole5's map holds `OLE5` and `ole5` beside `Ole5`, since the knowledge base writes `OLE5` and
    the model copies it; the Arabic form is «أو لي فايف», the owner's pick the same day of ten samples of the voice, after «أُولِي فايف» and «أولي فايف» both sounded wrong.
  - An arrow is said as "then" («ثم»), or dropped with no words on one side (`speak_arrows`,
    applied in `said`, so the caption keeps it).
  - An English reply is cut at sentence ends, or at a comma once a clause is 120 characters
    long (`ClauseStream(whole_sentences=True)`). Arabic replies are cut as before; the owner did
    not hear the fault there.
  - A progress line is followed, and a notice preceded, by 0.4 s of silence (`BEAT_S`).
  - A new notice, `cut_off`, offers the answer again after a reply that failed once some of it
    was heard. A clause's failed speech is told at the reply's end, so no clause follows the
    line, and not at all when the caller stopped the reply. An echo or a repeat keeps `error`.
  - Ole5's progress line is shorter and no longer names the product. Its instructions ask for one
    short question when the caller's words make no sense for Ole5 or could mean two things, and
    for a button's meaning and its Arabic sound in Latin letters in an English reply.
- **Consequences:** `t2v/1`'s `notice` has one more `kind`, and a language built without a preset
  must give its text. English first audio waits for the first sentence, not its first comma.
  Which of the causes the owner's archiving question had is unknown: the knowledge base holds
  archiving in 16 of its 128 passages.
- **Evidence:** plan 006's progress entry of 2026-11-09 and Q35;
  `tests/t2_agentic_voice/domain/test_clause_stream.py`,
  `tests/t2_agentic_voice/domain/test_speaking.py`,
  `tests/t2_agentic_voice/voice/session/test_talker_call.py`, `tests/ole5_voice/test_agent.py`.

## D-078 · A failed search is asked once more, and is seen in the trace · 2026-11-09 · Accepted (the owner's ruling, Q36 in plan 006)

- **Context:** in the owner's Arabic call of 15:57 the agent said it could not look anything up,
  on the first search since the server started at 15:56. Eighteen searches run afterwards from
  the same machine all passed, so the fault was brief. The search tried once, its reason went
  only to the server's log, and no span recorded a tool call.
- **Decision:**
  - Ole5's knowledge base asks once more after a failure that may pass, within the 4 s deadline
    of the search; a rate limit is not asked again.
  - The server signs in to the knowledge base once the runtime has started; a failure there is
    logged, and the first search tries again.
  - Each tool call is a `tool` span under its turn: the tool's name, `tool.ok` and
    `tool.failure`, a word or two the runner sets (`ToolResult.failure`), such as
    `timeout at search`. Never an argument or a result, which may hold a caller's records.
- **Consequences:** a slow service can still use the whole deadline, so the caller may wait up to
  4 s before hearing the same honest sentence. A provider's `details` may name a `step`, which
  the trace then shows, so a team's adapter keeps that value to its own short list.
- **Evidence:** plan 006's Q36; `tests/ole5_voice/test_knowledge_base_failures.py`,
  `tests/ole5_voice/test_server.py`, `tests/t2_agentic_voice/core/test_tracing_tts.py`,
  `tests/t2_agentic_voice/actions/test_runner.py`.

## D-079 · Traces hold what the agent said and what it searched for · 2026-11-09 · Accepted (the owner's ruling, Q37 in plan 006)

- **Context:** invariant 8 kept the speech-to-text transcript as the only call content in a
  trace, so the agent's words and a search's text were nowhere to be read after a call. In the
  owner's calls even the transcript was on 2 turns of 12: its span opens only for a turn with a
  request of its own. The owner: "make it do so to ease our job".
- **Decision:** under `tracing.include_transcripts`, on by default and through `tracing.redact`,
  a turn's root span holds what was heard and what its reply said, each reply's span its text,
  and each tool call's span the arguments the model wrote and what the tool gave back, the owner
  asking for the result too the same day, so a search's passages can be read. A value's length in
  a span may reach 32,768 characters, to hold a whole search. A value bound from the caller is
  not exported as such, but a result may repeat it. Invariant 8 says so.
- **Consequences:** Phoenix keeps more of each call, for as long as its retention says (none is
  set on the laptop). The roadmap's M6 question of what other callers must be told covers it.
- **Evidence:** plan 006's Q37; `tests/t2_agentic_voice/core/test_tracing_tts.py`,
  `tests/t2_agentic_voice/voice/session/test_talker_told.py`.

## D-080 · The consent objects are sealed, shared from below the rule that reads them · 2026-11-10 · Accepted (the agent's, in plan 007's Block 0, within the plan the owner approved)

- **Context:** invariants 1 and 2 keep four objects to one layer each: the heard words and the
  read-back receipt (`voice`), the confirmed action (the yes rule), the completed action
  (`actions`). `domain`'s yes rule must read the first two, which `voice` builds, and `domain`
  imports only `core`. `SignedConsent` is the pattern, but its code carries invariant 8 and was
  left alone.
- **Decision:**
  - `HeardWords` moved to `core/yes_inputs.py`, with `ReadBackReceipt`; `heard_words()` stays in
    `voice`. Each of the four is a sealed model (`core/seal.py`): built only by a validation given
    its class's seal, recognised by one module-level check, and listed in `[[restricted]]` with
    its seal's name. `CompletedAction` is defined in `domain`, where the guard reads it, and
    built only by `actions/record.py`.
  - The receipt holds the action and the draft as JSON text, and the confirmed action copies
    them, so a draft can be confirmed only by the receipt of its own read-back.
  - `HeardWords` gains `speech_at`, when the caller began speaking (its `at` is the transcript's
    arrival), and `source`.
  - Yes and send words stay out of `domain/words.py`'s five kinds, which the interruption rule
    reads, so a measured rule does not change; they live in `domain/yes_words.py`. Settings add
    to them through `words.yes` and `words.send`.
  - Read-back templates are pairs, summary and closing question, and there is no `deps`: a backend
    is reached by a closure, as `knowledge_tool` reaches its knowledge base.
- **Consequences:** a module that named `HeardWords` from `voice/session/heard.py` imports it from
  `core`; a test builds one through the seal, as `SignedConsent`'s do. The seal's check runs at
  run time for every built object, and costs a dictionary entry per live object. `ARCH-CONSTRUCT`
  still cannot see an aliased import of a class; the seal is what holds there.
- **Evidence:** plan 007's Tracks section; `tests/t2_agentic_voice/core/test_seals.py`,
  `tests/t2_agentic_voice/actions/test_action.py`,
  `tests/t2_agentic_voice/domain/test_declaration_actions.py`.

## D-081 · The yes rule refined, the guard split, one runner an agent, the session's routing, and the checks in text · 2026-11-10 · Accepted (the agent's, in plan 007's tracks and integration, within the plan the owner approved; the stop kind, what the caps count, an MSA caller's lines, the ticket number as a claim, run A's note pair and what a status backs follow the owner's rulings of 2026-11-10)

- **Context:** on D-080's base, plan 007's five tracks built the yes rule and the guard's rule A
  (A), the action runner and the talker's side (B), the session's confirming state (C),
  `TextCall` and the safety suite (D) and Ole5's tickets (E), each against fakes, and the
  integration joined them. Each met choices the design's 6.4, 8.2, 8.3, 9.2 and 9.3 left open;
  three tracks asked whether rule A should run for an agent with no actions; and the owner's stop
  ruling (a stop over the read-back keeps the draft, the agent asking what to change) had no
  decline kind of its own.
- **Decision:**
  - *The yes rule (A).* Words begun before the summary ended, or with no `speech_at`, count for
    nothing, a no or a correction too. A send word with no yes word (the closing question holds
    one, and its echo must confirm nothing), a yes with a question mark («نعم؟», pardon) and a
    yes beside a no are asked again; a word on none of the lists makes a correction; a word on
    two lists counts as no, then yes, then send, then filler. The words are the rule's own lists,
    its no words and fillers starting from `domain/words.py`'s, which stays unchanged (D-080).
  - *The flow (A).* A stop or pause word over the read-back (`stop`) and no clear answer after
    the last ask-again (`unclear`) end it `declined`, as a no and a correction do; a repeat and
    an ask-again keep it `confirming`, so only a yes to the new reading counts; `sending` takes
    no stop.
  - *The guard (A, B, E).* Rule B lives in `domain/guard_ids.py`, rule A in `domain/claims.py`;
    rule A runs first, and a clause it passed with a claim skips rule B. A claiming clause's
    numbers are read as rule B reads them, against the claimed action's evidence alone: its
    completed results this call and the ok results of the tools whose `reports_on` names it,
    those holding an ID-shaped token (since plan 007's whole-code review: a status that found
    nothing backed any claim), a status's backing fewer claims than the record's (*What a
    status backs*, below). Every language's
    phrases are read, whatever the reply's (the same review: a claim the model wrote in its
    other language passed). Rule B's evidence gains the record's results. The default claim phrases are past-tense,
    mostly first person, none only introducing a number. A `reports_on` tool's result is
    evidence, so it echoes no argument the model chose. Rule C drops the text after an action
    call in its own request; a read-back ends the reply; after a refused call the model may speak
    again, under rules A and B.
  - *Rule A's scope (the integration).* Rule A runs only for an agent that declares an action,
    as every rule added for actions does (plan 007's baseline), and `TextCall.violations` runs
    rules A and C and its yes-rule check on the same terms. The alternative, the default phrases
    for every agent, was set aside so that no measured run of an agent with none moves (GP-18).
  - *The runner (B, its review).* One `ActionRunner` an agent serves every call, each call's
    record kept by its ID; Block 0's `record=` stays, for `TextCall`. The request ID is derived
    from the confirmed action, so a job handed twice is written once. The caps count outbox rows,
    never proposals, and only a write that may have reached the backend (`sending`, `done`,
    `flagged`), never one `rejected` or `not_sent`, so a caller whose write was refused or never
    sent may try again (the owner's ruling of 2026-11-10, "Count only real writes"; until then
    every row counted). A write past its timeout runs on, its result discarded; a lookup or
    `validate` past its own is cancelled. The model reads only that its call is being read back,
    and one action is taken a request.
  - *The session (C, the integration).* A turn is the yes rule's when its speech began once the
    summary's last clause played; the receipt is built at that moment, and a turn with none is
    asked again. Real words that stop the closing question keep the receipt, so a yes with a send
    word said there counts. A stop or pause word over the read-back, or said whole while
    confirming, declines it as `stopped`, a new `DeclineKind`, the talker told to ask what to
    change and keep the draft; real words over the summary decline it as a `correction`, and so
    does a turn begun before its first audio once its words reach the talker (since plan 007's
    whole-code review: the summary played on over it, and a later yes confirmed the old draft);
    a repeat says it again as a new reply. *Amended 2026-11-11* (the owner's "Fix all, then run
    A", on his question whether a caller can cancel a read-back and ask something else): over
    the summary, words that hold a stop or wait word of the call's, read as the interruption
    rule reads them (the `words` settings' additions included), are never ignored, so the rule
    judges them as any stop word; «خلاص», a stop word of the `ar` list and a filler to the yes
    rule, said alone over the summary declined nothing and the summary played on, and now
    declines it as `stopped` (said once the read-back played, «ايه خلاص أرسلها» is still a
    yes). And words that cut the summary and are a plain no by the yes rule's lists for the
    read-back's language (`yes_rule.plain_no`: a no word, beside it only send words and
    fillers, the words `decide` declines once the summary played; "No, cancel it, don't send
    it.", «لا لا، لا ترسلها») decline it as a `no`, not a `correction`, read on the turn's whole
    words as it reaches the talker, so the talker is not told to call the action again; "No,
    not Monday, since Thursday." stays a correction. A single word over the summary that is no
    stop or wait word is still too few to stop it (D-069). A turn heard as nothing changes nothing while
    confirming. `sending` answers the yes turn, and the outcome is said once, at a turn boundary,
    as a reply that answers no turn. The session is the only sender of `ActionCompleted` and
    `ActionUnconfirmed`; the runtime's runner sends no event.
  - *Testing (D, the integration).* `ActionSafetySuite` takes `make_agent()`,
    `action_under_test()`, `sample_draft()`, `language` and `caller`, the session's caller its
    calls run as (`TextCall`'s made-up one unless a subclass gives one). `TextCall` and
    `AudioCall` build the runner as the runtime does (its caps from the settings), over a
    `MemoryOutbox` unless given an `outbox`; `TextCall` marks typed words `typed`, which the yes
    rule takes only under `env="test"`, and exempts the runtime's own lines from its checks, as
    the guard does. Its checks read the evidence the guard reads (a tool result's data and
    texts, what an action's call gave back, a record entry's result whole), and a summary played
    whole stands though a stop cut its reply after it, as for the receipt.
  - *Ole5 (E).* A mock ticket system is the only one any code here reaches (plan 007's Q2); it
    never dedupes a request ID, so a double send shows as two tickets, and scopes every read and
    note by the session's customer. A ticket's number is said whole in four groups of four, and in
    status only by its last four digits.
  - *An MSA caller's lines (the owner's ruling of 2026-11-10, "Add MSA read-backs").* Run A's
    MSA callers heard Ole5's Saudi read-back, so the check that a reply is in the caller's
    language failed on lines no model wrote; the check stays as registered, and the lines follow
    the caller instead. The talker reads an action's texts in `wording` (agent/language.py):
    `ar`, MSA, for an `ar-SA` reply whose caller's register is MSA (`call_register`), else the
    reply's tag. A text is read in its own tag, then the other Arabic one
    (domain/action_declaration.py's `read_in`), so an `ar-SA` agent may give an `ar` text
    beside each `ar-SA` one, which declares no language (the declaration never refused one),
    and an action with none says its `ar-SA` text, as before; the library's own lines are read
    in that wording too, its MSA ones. The read-back's plan keeps the wording
    (`ReadBackPlan.wording`) and the session hands it to the job (`ActionJobs.run`), so the
    outcome is read as its read-back was; every line is still said in the reply's tag, the
    `ar-SA` voice, since an agent that speaks no `ar` may have no voice for it. Ole5 gives each
    of its actions' lines an MSA text (tickets/lines.py), formal, with no dialect form, its
    closing question «هل أرسلها؟» holding the same send word. The alternative, judging the
    register of the talker's own words alone, was withdrawn by the ruling.
  - *The ticket number as a claim (the owner's ruling of 2026-11-10, "Yes, make them a
    claim").* A number said as the caller's ticket number passed rule A in a call with no
    ticket, and a passage's number then passed rule B as a fact. Ole5's «رقم تذكرتك» and "your
    ticket number is" (tickets/lines.py's `NUMBER_CLAIMS`, MSA's words the same) claim any
    action: the talker with tickets runs under settings whose `guard.claims` holds them
    (tickets/tools.py's `with_ticket_claims`, in the server, run A and the tests of its calls),
    so one passes when an action of the call or a status holds a ticket, its numbers read
    against that evidence alone. The phrase on both `create_ticket`'s and `hand_off`'s lists was
    set aside: rule A asks evidence of every action a phrase names, so a true number after
    either would be blocked. Ole5's `done` lines say the number in other words («تم، تذكرتك
    رقمها»; "Done. The ticket number is"), whole and digit by digit as before (Q6): nothing
    checks a done line, but the talker reads it in the call's history as its own reply and
    copies it, and `TextCall` reads a clause that copies a piece of a runtime line as that line,
    so a done line in the claim's words would hide the talker's claim from `call.violations`.
  - *What a status backs (the owner's ruling of 2026-11-10 on TD-144, "Number or same
    reply").* A status holding an ID-shaped token (`holds_an_id`) backed every claim about the
    actions its tool reports on, one that named no number too: a caller with a ticket from an
    earlier call who asked its status, then for a new ticket, could hear "I've opened a ticket
    for your reports page" with no action called, `call.violations` empty. The ruling: "a
    status result backs only a claim that names one of its ticket numbers (or its last digits),
    or a claim in the same reply that already said one of the status's numbers. A claim the
    call's record backs (an action done in this call) is unchanged." So each `ActionEvidence`
    says its `source`, `record` or `status`. An action with a record backs a claim as before.
    One with only a status backs it when the clause holds an ID-shaped token the status's texts
    hold, read as rule B reads one (`check_ids` against those texts, so last digits count when
    the status holds them, as Ole5's `ends_in` does); or, for a clause with no ID-shaped token,
    when an earlier clause of the same reply that the guard passed held one (`check_claims`'s
    `earlier`). A default phrase, the `guard.claims` ones included, stands for each action that
    backs it. The live guard keeps the clauses it passed in one reply (one `SpeechGuard` a
    `Turn`); `TextCall`'s check keeps, for each turn's talker reply, the clauses rules A and B
    found nothing in, so both decide alike. Rule B, rule C, the phrases read, `holds_an_id`, the
    record's evidence and every agent without actions (GP-18) are unchanged. Ole5's
    instructions tell the talker to say a ticket's last four digits first, before what happened
    to it, since an Arabic comma ends a clause. The ruling accepts that a false claim with no number, in a reply that said a
    status's number, passes, and that a status sentence with no number, in a reply that said
    none ("Yes, it has been escalated"), is blocked, the guard's fixed phrase said instead.
  - *Run A's note pair (the owner's ruling of 2026-11-10, "Yes add a pair").* No run A
    scenario put `add_ticket_note` to the model, so one kind of its own, `ticket_note`, joins
    before any run, in English on dev (a39) and MSA on held-out (a40): a ticket read back and
    made on a yes, then a note on it read back by that ticket's last four digits and added on a
    yes. A scenario states the notes its call adds (`noted`), and a note's call follows a turn
    whose ticket was made, as its `validate` asks. A play counts the notes its mock holds: the
    right action is the scenario's tickets and notes, and a note added beyond the notes'
    writes its turns confirmed is the scenario's own violation, as a ticket beyond the
    tickets' is, so a note sent twice fails the run.
- **Consequences:** an agent with read tools alone can still say it made a ticket, unblocked by
  rule A. A lexical rule asks a real yes again rather than take a doubtful one. Two parts are
  written but unread at run time, the flow's `advance` and the guard's `check_clause`. A ticket
  number said with no claim phrase is not rule A's (the design's 8.4); Ole5's phrases for one,
  which only introduce a number, also block a question asking for it and a caller's own number
  read back while no record or status holds a ticket (TD-134). The debt is TD-133 to TD-142,
  and TD-144's part the status ruling left: evidence keyed by an action's name alone.
- **Evidence:** plan 007's Tracks section, Progress log and Decision log;
  `tests/t2_agentic_voice/domain/test_yes_rule.py`, `test_action_flow.py`, `test_claims.py`;
  `tests/t2_agentic_voice/agent/test_talker_claims.py`, `test_talker_claim_evidence.py`,
  `test_talker_actions.py`; `tests/t2_agentic_voice/testing/test_text_call_claims.py`;
  `tests/t2_agentic_voice/actions/test_action_run.py`, `test_action_caps.py`;
  `tests/t2_agentic_voice/api/test_runtime_actions.py`;
  `tests/t2_agentic_voice/voice/session/test_yes_turns.py`, `test_yes_turns_safety.py`,
  `test_read_back_overlaps.py`; `tests/t2_agentic_voice/testing/test_action_safety.py`;
  `tests/ole5_voice/tickets/test_status.py`, `test_mock.py`, `test_lines.py`; the end-to-end
  calls, `tests/t2_agentic_voice/testing/test_action_calls.py`, `test_parity_actions.py`,
  `test_action_call_registers.py`, `tests/ole5_voice/tickets/test_ticket_calls.py`,
  `test_ticket_safety.py`, `test_ticket_calls_msa.py`, `test_ticket_claims.py`; run A's plays,
  `tests/ole5_voice/evals/test_action_play.py`, its scenarios and checks,
  `test_action_scenarios.py`, `test_action_score.py`; for the amendment of 2026-11-11,
  `tests/t2_agentic_voice/testing/test_action_call_cancels.py`, `test_read_back_overlaps.py`'s
  plain no and stop word on a filler, and `test_yes_rule.py`'s `plain_no` cases.

## D-082 · A chat model judges the answers the yes rule's lists leave unplaced, within its rails · 2026-11-10 · Accepted (the owner's rulings of 2026-11-10, plan 007's Block F)

- **Context:** the integration found «اممم» read as a correction for want of a list entry. The
  owner: "We should be more flexiable, we shouldn't just have a list and rely on it, there are
  things a caller might say (or STT might hear) that no list can cover, so the agent should
  handle this itself". Put three options, the agent's recommendation first (a model sorting what
  the lists miss into unclear, no or change, never yes), the owner chose it with an addition:
  "Lets do the model sorts the rest. But I would also want it to recognize different words of
  confirmation like ("go for it", "اكيد" etc.. While also capable of knowing that "Yes, but
  change.." is a request for change and not only confirmation)". The agent had advised against a
  model's yes ("a misjudged 'yes, but change X' would send a ticket the caller never approved").
  On the first draft, whose rail made a judged yes over the closing question still need a listed
  send word, the owner asked: "Over the closing question: a judged yes still needs a send word,
  as a listed yes does. Doesn't this defeat the purpose of a judged confirmation in first
  place?"; to the agent's change (the model telling an explicit go-ahead from plain agreement,
  only the go-ahead counting over the question, the agent's own words heard back unclear), the
  owner answered "Yes, send it". The same day, the agent's lead found that a send word said
  alone was still never put to the model, and asked: "A send word said alone («أرسلها», «توكل»,
  "go ahead", "send it") is still always asked again and never goes to the model, as in M3.
  Meanwhile "go for it" and «يلا أرسلها» do go to the model and can send. Should a send word
  alone go to the model too?"; the owner chose the recommended option, "Yes, let the model judge
  (Recommended)": "A send word alone goes to the model like any other unplaced answer, under the
  same rails. Words that copy the agent's own line are treated as its echo only if heard while
  the agent was speaking, so a caller who answers «أرسلها» once the question ended can send."
  The rulings amend invariant 1 (docs/SECURITY.md). On 2026-11-11 the owner asked: "When the
  agent offer a ticket, the user can approve or edit. But can he cancel the ticket all together
  and start to ask another question or open another ticket?" A trace found a plain no worked,
  but the instruction listed "a question" under `unclear` (the agent's wording when Block F was
  built, no ruling's), so a question said in answer to the read-back was asked again, up to
  `max_attempts` times, then met the declined line, and never reached the talker. Put with the
  fix, the owner answered "Fix all, then run A".
- **Decision:**
  - The lists stay first and unchanged: whatever `decide` places is its answer, and asks no
    model. It marks `askable` what it cannot place: a word on none of its lists (until now a
    correction), send words alone or among fillers with no yes word and no question mark
    («أرسلها», «يلا أرسلها», which the lists ask again; a send word alone since the third
    ruling), and a yes among fillers over the closing question with no send word. Its answers
    do not change (`askable` is no part of their equality), so an agent that does not ask
    hears a send word alone asked again, as before.
  - For an agent that asks (`VoiceAgent.ask_on_unlisted_answers`, False by default, as
    `ask_on_uncertain_overlaps` is under D-069), those words are put to a chat model
    (`domain/consent_check.py`: `openai/gpt-oss-120b` at low effort, temperature 0, 256 output
    tokens, 2.5 s on the call's clock, which the caller waits through in silence; 1.5 s until
    `a2-dev`, below), the request holding as data, in JSON, the read-back's
    summary and closing question as the plan rendered them and the heard words, nothing else;
    it answers `send`, `yes`, `no`, `change` or `unclear`, anything else read as `unclear`.
    *Amended 2026-11-11:* its `no` covers, beside a refusal or a cancel, an answer that turns to
    something else instead of answering: a question, about this action or anything else, or a
    request for something other than what was read back (another ticket, another topic; not
    "a person", since a person asked for over a handoff's read-back is that very thing, and a
    yes to it stays a yes); `unclear` keeps a sound, a hesitation, a word that answers nothing
    and the agent's own read-back or question heard back, and that rule comes first (words that
    match what the agent said are never the caller's answer, even when they are a question);
    `change` is unchanged, and there is no sixth word. *Reworded the same day* after run A's dev
    run (`a1-dev`), where the model still answered `unclear` to a bare question (a41 twice,
    a42 once) and, asked a Saudi one four times, ran out of its 256 tokens while reasoning in
    three: the echo rule now opens the instruction ("First: ..."), `no` says plainly that "any
    question the caller asks instead is no", and `unclear` is "only" a sound, a hesitation or a
    word that answers nothing. Asked again the same 13 answers four times each, the model gave
    48 of 52 right; the rest were 3 failed requests and one `no` to "Yes, I want to talk to a
    person" over a handoff's read-back, which drops it with nothing sent. *Amended again on
    2026-11-11*, after run A's second dev run (`a2-dev`), by the owner's "Fix, then dev again":
    the time limit is 2.5 s, up from 1.5 s, since 3 of the check's 24 requests ran out there,
    so the caller was asked again, and once a change was missed and the unchanged ticket made.
    The caller waits in silence for the check, so a slow one costs up to 2.5 s of silence.
  - The yes rule decides what the word makes (`judged`, beside `decide`, the only other builder
    of a `ConfirmedAction`). A `send` or `yes` is a yes only when the words hold no no word and
    no question mark (else asked again), no change marker (`domain/yes_words.py`'s new list a
    language: the brief's "but", "change", "instead", "except", "actually", "rather" and «بس»,
    «لكن», «غيّر», «عدّل», «بدل», «بدال», «خلها», «خله», with those verbs' forms with the
    object pronoun, each also after waw; else a correction), are not the agent's echo (below;
    else asked again), and the receipt built when the words reached the rule still stands (else
    asked again). Once the closing question ended, `send` and `yes` both confirm; over it,
    `send`, or `yes` to a listed send word beside other words, and `yes` alone, or to a send
    word alone, is asked again. `no` is declined, `change` a correction, and `unclear`, a
    failure and a timeout are asked again. *Amended 2026-11-11:* a `no` or `change` on the
    agent's echo (below, the same lines and window as for a yes) is asked again too, as its
    `yes` is, since a question is now a `no` and the closing question heard back is a question;
    the model's `no` stays `Declined`, so the turn goes to the talker with the action declined
    as a no and its words whole, and the talker answers the question or proposes the new action
    in its own words (the owner's ruling "The model always answers"). *Amended a third time on
    2026-11-11*, after run A's third dev run (`a3-dev`): a failure or a timeout, which gives no
    word, on words that hold a no word of the lists ("no", «لا», «ما» and the rest) is
    `Declined`, as the model's `no` is, unless the words are the agent's echo (below, the same
    lines and window), when it is asked again; on any other words it is asked again, as before,
    and `unclear` and every other word are unchanged. There the check ran out at 2.5 s in 5 of
    its 24 requests, and twice (a44) "No, forget that one. Open a ticket about the electronic
    signature instead ..." was asked again, so the scripted "Yes, send it." made the ticket
    the caller had dropped. Put among three fixes as "a consent check that fails or runs out of
    time on words holding a no word handed to the talker as a decline instead of asked again",
    with the question "Make the three fixes below, then run held-out?", the owner answered
    "Yes, all three". Either way nothing is sent without a later yes. An agent that does not
    ask is unchanged: its unplaced words stay a correction (GP-18).
  - The echo rail is the agent's own: the brief names the agent's words heard back unclear for
    the model, and the lists hand the model send words, alone or among fillers, which the Saudi
    closing question «أرسل الطلب؟» heard back is; a misjudged echo would send what the caller
    never approved, so the rule refuses it whatever the model says. Since the third ruling it
    reads only a line still heard as the speech began (`SaidLines`). The library already says
    how long that is: a reply is heard while it plays and within its tail after it ended, the
    agent's voice leaked past the browser's echo cancellation (the drop rule's `DROP_AFTER_S`,
    0.3 s, plan 003's decision log; none after the caller's own stop, TD-060), so the rule's
    "heard while the agent was speaking" is that window. Words that are the agent's own, read as
    the interruption rule reads its words heard back (every word a word of the lines heard then,
    taken together, or one edit from one of three letters or more: `own_words`; until plan 007's
    whole-code review a run of one line's words in their order, which an echo running from the
    summary into the question, or written a letter off, passed), are its echo when the speech
    began over the closing question (by the receipt) or while the read-back's reply played or within its tail (the summary and the
    question; `Confirming.over_read_back`), or while a line that asked it again played or
    within its tail (`Confirming.over_follow_up`): the transport's reports, as the question's
    end is read, through the drop rule's own `Reply.over`; True when the session cannot tell,
    so the rail stands. Speech begun when none of them was heard is judged on the model's word
    and the other rails alone: «أرسلها» or "send it" once the question and its tail ended can
    send, and "go ahead" said over the library's English ask-again line ("Shall I go ahead?"),
    or 0.25 s after it ended, is asked again. Only the rail's window has the tail: a yes over
    the closing question is still one whose speech began before the question ended
    (`question_ended_at`, the receipt's).
  - In the session (`voice/session/yes_ask.py`, shaped as D-069's `overlap_ask.py`): a task of a
    cancel scope of its own, no lock held, the verdict a session step applied only while the
    same read-back is current; a newer answer, the client's stop and the call's end cancel it;
    counted in the call's usage; logged by its outcome's kind alone. It runs on the call's chat
    model for the session's own requests (`CallSetup.overlap_model`, kept by its name).
  - Observers tell a judged answer from a listed one: `ConfirmationAnswered.by`, `words` or
    `model`. `TextCall` needs nothing new: its fake model receives the check's requests as it
    receives the overlap's, told by the instruction (`is_consent_check`, in the `evals` facade
    with the request and the answer's reader). `ActionSafetySuite` gains the rails' cases, each
    passing at once for an agent that does not ask, the closing question heard back as it plays
    among them (judged `send`, it confirms nothing).
- **Consequences:** an agent that asks hears "go for it" or «يلا أرسلها» as a yes, and «امممم»
  asked again, not corrected; the caller waits in silence while the check runs, at most 2.5 s,
  and that wait counts in the turn's time to first audio: the turn settles, its `TurnMetrics`
  sent and its trace ended, only once the reply its verdict says has played. A model fooled into `send` on words that carry no refusal, change or echo (a hesitation, after
  a read-back whose draft held text written to steer it) would still confirm: the rails are
  lexical, and the read-back's summary is the draft's own words, so the prompt frames it as
  data. «اكيد» and "sure" were listed yes words already, so they reach no model. An agent that
  does not ask, and every measured run, is unchanged (GP-18; `test_no_action_baseline.py`).
  Ole5 sets the flag, its end-to-end calls and run A's oracle answer the check, and run A gains
  scenarios for it (the plan's Block F, the Ole5 builder's part). After the third ruling a send
  word alone costs a chat request too, and a failed or slow one is asked again, as the lists
  asked it; no committed run A turn is a send word alone, so no expected outcome of run A
  moves. Since 2026-11-11 a question or a request for something else in answer to a read-back
  is never asked again when the model says `no`: the caller hears the talker's answer at once,
  and can go on to another question or another action; a model that still says `unclear` for
  one asks it again, as before. The instruction's text changed, so a measured run of the check
  before that day is not comparable with one after it. Since `a3-dev`, a check that fails or
  runs out of time on words with a no word drops the read-back to the talker instead of asking
  again, so a cancel for another action is answered at once on a slow network too; a no word
  the caller did not mean as a refusal ("yes, not like that") drops the read-back the same
  way, nothing sent, and the talker answers it, reading a new draft back when one is asked for.
- **Evidence:** plan 007's "The owner's decisions" (2026-11-10, the rulings; 2026-11-11, the
  owner's answers) and its Block F; run A's `a3-dev` (a44);
  `tests/t2_agentic_voice/domain/test_consent_check.py`, `test_yes_rule_judged.py`,
  `test_yes_rule_judged_no.py`, `test_yes_rule_send_alone.py`;
  `tests/t2_agentic_voice/voice/session/test_yes_ask.py`, `test_yes_ask_echo.py`,
  `test_yes_ask_tail.py`; `tests/t2_agentic_voice/testing/test_action_call_judged.py`,
  `test_action_call_cancels.py`, `test_action_safety_judged.py`;
  `tests/ole5_voice/tickets/test_ticket_calls_judged.py`.

## D-083 · A test console beside the dev page, fed by the runtime's events, which now carry each tool's arguments and result · 2026-11-10 · Accepted (the owner's approval of the agent's proposal, 2026-11-10; its Start's own token, the owner's "Yes, build it", 2026-11-11)

- **Context:** the owner: "Can you do a new interface for testing the agent, It should be
  informative: have the tools used and what they returned, the latency for each thing, and any
  information that might help me and fellow engineers test the system. Also make it with fairly
  good UI". The dev page showed captions, cards and notices only; Phoenix's traces held the
  tools' arguments and results but not the yes rule, the actions or the interruptions, and need a
  server of their own. The public events carried a tool's name and time but not what it was
  asked or gave back, and the turn's times had no end-of-turn step. The agent proposed a console
  in the library beside the dev page, fed over HTTP long-polling by one observer of the events,
  with five events given new fields; the owner answered "Approve, build it". On 2026-11-11 the
  owner asked "why can't I start a call from the dev console? can we do that easily". The
  console's Start joined with the token in its "Join token" field, `dev` by default, which only
  `t2v dev`'s identity takes, while Ole5's server takes only the tokens it signs after the
  access code, with the demo customer's email in them. The agent proposed: "when you leave the
  field empty, the console's Start makes its own signed token for a test caller the app names
  (for Ole5 the demo customer, so tickets work); only under dev with the dev page on, for a
  browser on this machine, the same guard the console's call feed already has; no access code
  and no daily count of 10 on that path; the same kind of signed token, so the call runs exactly
  as one from the widget". The owner answered "Yes, build it".
- **Decision:**
  - `<prefix>/dev/console`, with `dev/feed`, `dev/setup`, `dev/console.js`,
    `dev/console.css` and `dev/token` (below) (`api/dev_console.py`, its files in
    `api/static/`), mounted with the dev page and only then, so every team's `t2v dev` has it
    and an app's server under `env` dev with `server.dev_page`. Each route answers the plain 404 under any `env` but dev, to a
    client that is not loopback, and to a `Host` that is not a loopback name, so a page
    elsewhere cannot reach it through a name it points at this machine. The page's policy allows
    scripts and styles from the server alone, no framing; every text is set as text.
  - The feed (`DevFeed`) is a runtime observer of every event, its records the events as JSON,
    numbered: in memory the last 20 calls' (at most 20,000 records), never logged; each restart
    a feed of a new name. The proposal kept them in memory only; on seeing it built, the owner
    ruled (2026-11-10): "Make it save calls to the disk, since they are development related
    calls". So every call's events are also saved, one JSON line each, appended off the event
    loop, in `dev-console/<call ID>.jsonl` under `storage.var_dir`, which nothing deletes; a
    start's feed reads the newest 20 back, each line parsed as the event it names, one that is
    not skipped, before it keeps its first event. `GET dev/feed?after=N` answers at once with what
    is newer, or waits up to 10 s for it: no stream to hold uvicorn's shutdown, no message added
    to `t2v/1`, and a call from any page on the runtime is seen. The call's own data channel was
    the alternative: it would add messages every client of `t2v/1` must know, and show only the
    console's own calls.
  - The events gain fields, each with a default, so an observer written before keeps working:
    `ToolStarted.arguments` (the JSON the model wrote; on `ToolFinished` too),
    `ToolFinished.result` (what the tool gave the model back) and `failure` (what failed, no
    call content), `ConfirmationRequested.draft` (the draft its read-back reads),
    `ActionCompleted.result` (the write's real result, as the record holds it, through
    `ActionOutcome.result_json`), and `TurnMetrics.usage` (each model's usage so far). The
    turn's times gain `end_of_turn_ms` (from the end of speech to the turn's close) and
    `turn_complete_ms` (to Smart Turn's "complete"), and `stt_ms` now times the early start's
    request when the turn took its transcript as its own, which was none before for most turns
    of a call with a talker.
  - `dev/setup` shows the agent's tools, actions, languages and mode, the library's and
    Pipecat's versions and the settings' digest, and the settings groups `stt`, `llm`, `tts`,
    `turns`, `interruptions` and `limits`, which hold no secret (a test).
  - `POST dev/token`, the console's own token (the owner, 2026-11-11). With the "Join token"
    field left empty, Start asks it for a token and joins with it, or with `dev` when it gets
    none; a token typed in the field is used as typed. It answers under the console's guard
    alone (above): `env` dev, the dev page, a loopback client and a loopback `Host`, else the
    plain 404. It mints with `SignedJoinTokens.from_settings(settings.join)` for the caller the
    app declares in the setting `server.dev_caller` (a `Caller`, none by default; an app sets
    it in code, or `T2V_SERVER__DEV_CALLER` gives it as JSON), never for one the request names
    (invariant 3): the body is `{"record_audio": <bool>}` alone, at most 256 bytes, parsed
    strictly, false unless the page's "Keep the call's audio" box is ticked; the consent's
    version is `privacy.consent_version`. So the call runs as one from the app's widget: a
    signed token of the same kind, verified once by the runtime's identity source, its consent
    a signed one. No access code and no count of the app's own apply. With no dev caller
    declared, or no join key that signs (`join.current_kid`), it answers the plain 404, logged
    as `dev_token_refused` with why, so `t2v dev` works as before. It never logs the token:
    `dev_token_minted` holds the consent's `record_audio` alone. Ole5 names its demo customer
    the dev caller under `env` dev alone (`ole5_voice.settings.with_dev_caller`), so a console
    call's tickets are the demo customer's, as a widget call's are; its token route and its
    daily count are unchanged. A setting, not a parameter of the runtime, since
    `api/runtime.py` is at its size and the settings already carry what the router reads.
- **Consequences:** a team's observers receive call content they did not before (a search's
  words, the passages found, a draft, a ticket's number), as they receive what was heard; none
  of it is logged. A dev server's data folder holds every console call's content (no audio)
  until someone deletes `dev-console/`; data-and-privacy.md lists it. The
  console's script is checked by its text (no markup inserted, no inline script, every id it
  reads on its page) and by a live call, not by `poe arch`. Its first live call on this laptop
  showed the knowledge search timing out at 4 s, and Whisper once taking 3.9 s, each with its
  arguments and times on the page. The console's token needs no code, so under `env` dev a
  page the same server serves, or one whose origin `server.allowed_origins` lists (CORS lets
  it send JSON there), opened in a browser on this machine, can start a call as the dev
  caller; and the settings' digest counts the dev caller.
- **Evidence:** `tests/t2_agentic_voice/api/test_dev_console.py`, `test_dev_token.py`;
  `tests/t2_agentic_voice/core/test_settings_dev_caller.py`;
  `tests/ole5_voice/test_server_console.py`;
  `tests/t2_agentic_voice/voice/session/test_turn_times.py`, `test_talker_early.py`,
  `test_talker_call.py`, `test_read_back.py`; `tests/t2_agentic_voice/actions/test_action_run.py`;
  docs/guide/browser-client.md, "The test console".

## D-084 · No stray script in what the talker writes: one filter before the guard, on by default · 2026-11-11 · Accepted (the owner's ruling of 2026-11-10 and approval of 2026-11-11, plan 007's Block G)

- **Context:** in the owner's demo call of 2026-11-10 (report `0qPpF2-C`), `gpt-oss-120b`
  wrote «أيقونة "إ重新 كلمة مرور المستخدم"» where the passage holds «إعادة كلمة مرور المستخدم»,
  and no passage of the knowledge snapshot holds a Chinese character. Nothing stopped it: the
  output guard checks claims and IDs only, and the library read a text's script only to choose a
  reply's language. The owner, the same day, on the roadmap's item: "not only spoken, make it
  not appear as the llm response if we hook up a screen". Plan 007's Block G drafted the filter
  with five questions. Asked "Approve Block G with the agent's recommendations for Q10 to Q14?",
  the owner answered on 2026-11-11 "Approve Block G", so each is its option (a): on by default,
  with a setting to turn it off (Q10); it covers everything the talker writes, its text and the
  string values of every tool call's arguments, a search's query among them, never a key, while
  a tool's result, a card, a template and a fixed phrase stay the team's text (Q11); emoji and
  other pictographs are taken out and counted with the stray script (Q12); `ar-SA` and `ar`
  write Arabic and Latin, `en` writes Latin (Q13); each character is judged alone, nothing is
  held back, and nothing is guessed in a removed character's place (Q14).
- **Decision:**
  - **Where it sits.** One reply's filter (`agent/stray_script.py`'s `StrayScript`) is built
    beside the guard in each turn (`agent/turn.py`). Each piece of text the model streams is
    filtered once, and that piece goes to the turn's text, to the step that takes out a copied
    note, and to the clause splitter; each tool call is filtered as it is kept. So the guard, the
    voice, the captions, the history the next request reads, the trace, the public events
    (`ToolStarted.arguments`, `ToolFinished.arguments`, `ConfirmationRequested.draft`, D-083),
    the test console and an action's draft all hold one filtered text. The guard reads the text
    after the filter, as a safety rule: the other way round, «تم重 إنشاء» would pass the claim
    rule as two words and then be said as «تم إنشاء».
  - **The rule** (`domain/text/scripts.py`, pure, its ranges constants with comments;
    `remove_stray_script(text, *, languages, kept=())`, giving `Kept`, public through the
    `languages` facade, provisional as D-021 says). An agent's scripts are those of all its
    languages, never one reply's. *Kept:* the blocks of the agent's scripts (Latin U+0000-036F,
    U+1E00-1EFF, U+2C60-2C7F, U+A720-A7FF, U+FB00-FB06; Arabic U+0600-06FF, U+0750-077F,
    U+0870-08FF, U+FB50-FDFF, U+FE70-FEFF); General Punctuation (U+2000-206F); the Arabic-Indic
    and Persian digits; every character of a term the agent declares (its pronunciation map's
    written forms, `vocabulary.terms` and the `words.vocabulary` setting); any other
    punctuation, symbol, space, control or format character (quotes, «», %, a currency or math
    sign, and the arrows the speaking rules say as "then"); a number sign that is no decimal
    digit (², ½, ①); and a code point Python's Unicode tables leave unassigned, outside the
    ranges taken out. *Rewritten one for one:* a fullwidth form (U+FF01-FF5E) as its ASCII form;
    the ideographic space, comma and full stop (U+3000-3002) as a space, a comma and a full
    stop, so no two words are joined; a decimal digit of any other script as its ASCII digit.
    *Taken out:* any other letter or mark (Cyrillic, Greek, Hebrew, Devanagari, a variation
    selector), any private-use or surrogate code point; whatever its category, a character of
    the CJK and Hangul ranges (U+2E80-A4CF, U+AC00-D7FF, U+F900-FAFF, U+FE30-FE4F,
    U+20000-3FFFF), so one newer than Python's tables goes too; and the pictographs: U+1F000-1FAFF,
    U+2600-27BF but the two heavy arrows (U+2794, U+279C), and a fixed set of emoji below
    U+1F000 in other blocks (© ® ™ ‼ ⁉ stay, as symbols). `Kept` holds the text, how many
    characters were taken out or rewritten, and at most eight labels, sorted (the first word of
    the character's Unicode name, "PICTOGRAPH", "FULLWIDTH", or the category of a code point
    with no name), never a character it took. It is one `str.translate` over a table that keeps
    each verdict once found, one table per agent's scripts and declared characters; every code
    point gets a verdict, so no text makes it raise.
  - **A tool call's arguments** are parsed as JSON and each string value is filtered, never a
    key (a key names a field, which the runner checks as the model wrote it). They are written
    back only when a value changed, so a call with nothing to change keeps its exact text;
    arguments that are not JSON are kept as written, for the runner to refuse as it does.
  - **A clause left with nothing to say.** Once the filter has changed a reply's text, a clause
    with no letter or digit is no clause, so it is never counted as said in silence; a reply
    left with nothing to say gets the `error` notice, as an empty answer does.
  - **The count.** Each model request's end carries how many characters went and their labels
    (`ModelReplied`, internal). The session adds them to the turn's log, logs
    `talker_stray_script_removed` with the call, the turn, the count and the labels alone, and
    gives the turn's root span `turn.stray_characters` and `turn.stray_scripts` only when the
    count is above zero; `turn.stray_scripts` is one comma-separated string, since a span
    attribute holds one plain value. `TextTurn.stray_characters` sums a turn's, and Ole5's run A
    records each play's, each dev scenario's and the run's total, held-out's too.
  - **The setting:** `guard.remove_stray_script`, a bool, on (`T2V_GUARD__REMOVE_STRAY_SCRIPT`).
    Off, what the talker writes is kept as written.
  - **What it never does:** change the caller's heard words, a tool's result, a card, a
    template or a fixed phrase (the design's 8.2), or what the model is sent (the prompt, the
    tools' schemas, the turn's message and the word lists, `test_no_action_baseline.py`); guess
    at a removed character («إ重新» leaves «إ», the model's start of «إعادة»); hold text back;
    ask a model.
- **Why on by default:** it fixes the defect the owner heard from the next call on, and no
  measured outcome moves. Read only, the agent ran every stored text of the measured dev runs
  of K and S (k1-dev-a to d, k1-dev-spoken, k1-smoke, k1m-dev-a, k3-dev-a to d, s-120b-2 to 5)
  and the knowledge snapshot through the built rule, with Ole5's languages (`ar-SA`, `en`) and
  its 17 declared terms: none of the 5,747 clauses the talker wrote, none of the 1,415 argument
  values of their `search_knowledge` calls, and none of the snapshot's 1,528 texts (226,809
  characters) changes. Tests pin text in the agent's scripts unchanged, so it is the
  evaluation.md exception for a reliability fix; run A, the first run after it, records each
  removal; and the setting is the off arm a later run can compare, and a team's way out (GP-18).
- **Consequences:** invariant 2 holds on the text spoken: a stray character no longer hides a
  claim from the claim rule («تم重 إنشاء طلبك», "I've 重created your ticket"), and the ID rule
  reads a fullwidth colon or point as its ASCII form, and fullwidth or other-script digits, and
  "12重34重5", as the numbers they are. Invariant 4 gains one change: a fixed-set value that
  differs from a member only by a stray character (a ticket type "Bug重") parses as that member
  and is read back as it. A term a team needs in a third script ("μs", a supplier's Chinese name) is
  taken out unless the agent declares it. A letter Unicode adds after Python's tables, outside
  the removed ranges, is kept, and so is a later symbol. `remove_stray_script` called directly
  raises ValueError for a tag that is not `ar-SA`, `ar` or `en`. The settings' digest gains the
  key; `ModelReplied` gains two fields with defaults, the turn span two attributes, `TextTurn`
  one read, and the `languages` facade two names. `TurnRecord`, `CallReport` and `t2v/1`'s
  messages keep their fields, and no new public event is added.
- **Evidence:** plan 007's Block G and "The owner's decisions" (Q10 to Q14);
  `tests/t2_agentic_voice/domain/test_scripts.py`,
  `tests/t2_agentic_voice/agent/test_talker_scripts.py`,
  `tests/t2_agentic_voice/voice/session/test_talker_scripts.py`,
  `tests/t2_agentic_voice/testing/test_parity.py`; `tests/ole5_voice/test_agent_scripts.py`,
  `tests/ole5_voice/evals/test_action_score.py`, `test_action_play.py`, `test_action_run.py`.

## D-085 · A spoken reply stops before its second question · 2026-11-11 · Accepted (the owner's answer of 2026-11-11)

- **Context:** in a demo call, Ole5's talker was asked to open a ticket. It wrote one reply that
  asked how urgent the problem was a dozen ways, then played out the caller's silence («ما في
  رد، فأنا ما أقدر أفتح تذكرة الآن», "no answer, so I can't open a ticket now"), and all of it
  was spoken. A read-only scan of the 1,727 stored talker replies (the dev runs of K and S, and
  run A's dev run `a1-dev`; the talker's clauses, those with `phrase` false) found 139 that ask
  the caller a question (a clause ending in "?" or «؟») and none that asks two; 4 go on after
  their one question (a step answer, or "if you tell me more, I can help"). Asked "Add the
  library rule that a spoken reply stops before its second question?", the owner answered on
  2026-11-11 "Yes, add it".
- **Decision:**
  - **The rule** (`agent/question_limit.py`). In one talker reply (one turn, `agent/turn.py`,
    across its model requests), the talker's own clauses are said up to and including the
    first one that asks the caller a question. The next clause that also asks one is not said,
    nor anything after it in that reply: the reply stops there. The clauses between the two
    questions are said.
  - **A question** is a clause whose last character is "?" or «؟» (the library's
    `QUESTION_MARKS`), once the spaces at its end and the closing quotes and brackets the
    clause splitter reads past (`domain/text/clauses.py`'s `CLOSERS`) are taken off. So «...؟»
    and `...?"` ask. The agent's choice, as the scan counted: "?!", «؟.» and a mark inside the
    clause do not.
  - **What counts:** only the talker's own clauses, and only those said. The limit reads the
    clauses the guard passed in this reply, so a clause the guard blocked, or one the
    stray-script filter left with nothing to say, asks nothing. The session's fixed lines (a
    progress line, a notice, an action's read-back and its closing question, its outcome lines)
    are not the talker's clauses: they neither count nor stop a reply.
  - **Where it sits.** Each clause is judged as it comes, in the turn, after the check for a
    clause the filter emptied and before the guard. The question past the limit, and each
    clause after it, never reaches the guard: it is neither said nor blocked, and no notice is
    said in its place.
  - **The rest of the reply, beside the guard's `drop_rest`** (the agent's reading of what
    `drop_rest` does, and where the stop differs):
    - *The turn's remaining stream.* `drop_rest` closes it at once. The stop reads it to its
      end, its text unsaid, because a tool call comes after the text in the stream: a tool call
      the model makes in the same request still runs as it does today, and its result is kept
      for the call's next turns as always. An action called there is still read back.
    - *The next request inside the turn.* `drop_rest` makes none, and neither does the stop:
      after the request's tools have run, no request follows, since nothing more of the reply
      would be said. So the model's text of that request (`answer.text`, which holds the unsaid
      words) is never sent.
    - *The heard history.* For both, it holds only what was said, since the session builds it
      from what played. The stop gives the model no note (a blocked clause gives one).
  - **The setting:** `guard.questions_per_reply`, an integer of at least 1, 1 by default
    (`T2V_GUARD__QUESTIONS_PER_REPLY`). None, given in code, sets no limit; an environment
    variable left blank keeps the default.
  - **The count.** `ReplyDone.unsaid_clauses` (internal) counts the clauses the reply left
    unsaid, and `TextTurn.unsaid_clauses` reads it for a team's tests. The turn logs
    `talker_reply_stopped` at INFO with `call_id`, `turn_id`, `reason` (`question_limit`) and
    `unsaid_clauses`, never a word of the reply.
  - **What it never does:** change a clause's text; hold text back; ask a model; change a tool
    call; change what the model is sent (`test_no_action_baseline.py` and `test_baselines.py`
    pass unchanged).
- **Why on by default:** it stops the demo's defect from the next call on, and no measured
  outcome moves. Read only, the agent ran the same stored replies through the built rule's pure
  part (`said_clauses`) at the default: runs `k1-dev-a` to `d`, `k1-dev-spoken`, `k1-smoke`,
  `k1m-dev-a`, `k3-dev-a` to `d`, `s-120b-2` to `5` and `a1-dev`, 1,727 replies and 6,039
  clauses. 139 ask a question, none asks two, 4 go on after their one question, and none
  changes.
- **Consequences:** a reply asks the caller one thing at a time. A reply that asks two things
  in one go ("Is it urgent? Is it blocking your work?") says the first only. A question asked
  before a tool round counts too, so steps answered after the round that end in "Did that
  work?" lose that last question. A clause after the stop that the guard would have blocked is
  not blocked, so no `GuardBlocked` and no notice come of it. A team whose instructions ask for
  two questions in one reply raises the setting. `ReplyDone` gains one field with a default,
  `TextTurn` one read, `SpeechGuard` a read of the clauses it passed, and the settings' digest
  the key. `domain/text/clauses.py`'s closers are public (`CLOSERS`), and the turn's stream
  closer moved to the chat model port's module (`closing`), so `turn.py` stays under its size.
  No public event, `TurnRecord`, `CallReport` or `t2v/1` message changes.
- **Evidence:** the owner's answer above; `tests/t2_agentic_voice/agent/test_question_limit.py`,
  `tests/t2_agentic_voice/agent/test_talker_questions.py`,
  `tests/t2_agentic_voice/voice/session/test_talker_questions.py`,
  `tests/t2_agentic_voice/testing/test_parity.py`,
  `tests/t2_agentic_voice/core/test_settings_talker.py`.

## D-086 · Each turn's language from a classifier: a third value of `stt.live_language`, off until run H's keep rule · 2026-11-12 · Accepted (the owner's rulings of 2026-11-10 and approval of 2026-11-11, plan 007's Block H, Q15 to Q20 each settled (a); the downloads approved as listed)

- **Context:** Whisper writes a turn in the language it is told. Until now a live call told it
  the call's language, fixed at join (D-038, D-066), so an English question in an Arabic call
  came back as Arabic sounds (plan 006's run X: the English items' accuracy 0.813 sent as
  English, 0.027 sent as Arabic). A spoken-language classifier hears a few seconds of speech and
  says which language it is. The owner's ruling of 2026-11-10 in the roadmap: "We should
  implement both of them and see their effectiveness and the latency improvements or delays
  they bring"; to the draft of plan 007's Block H: "Yes, and I agree to download the
  dependencies and models". Asked on 2026-11-11 "Approve Blocks H and I with my recommendations
  for Q15 to Q25 and the downloads?", the owner answered "Approve both". The agent's offline
  check of 2026-11-10 (280 dev variants with speech, whole clips, Arabic against English) found
  ECAPA right on 93% and Silero on 84%: in-sample, one speaker (D-006). It shaped the block and
  proves nothing.
- **Decision:**
  - **A third value.** `stt.live_language = "classified"` sends each turn to Whisper in the
    language a classifier heard, chosen among the agent's languages. `session` stays the
    library's default (GP-18, Q19). An agent of one language runs no classifier.
  - **The rule** (`domain/turn_language.py`, pure; Q17, Q18, Q20). Once a turn holds
    `stt.classifier_from_s` (2.0) seconds from where the speech detector heard its speech
    begin, counted in bytes and never on the clock, those seconds go to the classifier, once a
    turn, on a task of its own. When the turn's request goes, in order: `short` (the speech had
    not reached 2.0 s), `late` (no verdict yet: the request never waits), `busy`, `failed`,
    `unsure` (the best share under `stt.classifier_min_share`, 0.7), else `classified`. Only
    `classified` moves the call's current language; every other case keeps it, so after an
    English question the short "yes" to its English read-back goes as English. The two numbers
    are registered for run H, not tuned on dev; another pair is a dated amendment.
  - **When it decides** (`voice/stt_language.py`, `TurnLanguages`). A turn's language is decided
    when its 600 ms hold begins (D-067), the moment a talker call sends its held request, in a
    call with no talker too; with no hold, when the turn closes. Every request of the turn names
    that language, its `Transcribing` carrying it, with when it was decided and the speech held
    then. Speech that resumes in the hold undoes the decision. An overlap's requests name the
    current language (`overlap`). The call's end cancels every classification in flight.
  - **The classifiers.** The port is `LanguageClassifier` with `LanguageScores`, parsed at the
    port (each share from 0 to 1, summing to 1, and `mass`, the share the agent's codes held of
    the model's whole output); an answer that does not parse is a failure. The adapters are
    reached through the `classifiers` facade: `SileroLanguage` (`stt.classifier = "silero"`, the
    default), Silero's 95-language model on the onnxruntime the base install already has; and
    `EcapaLanguage` (`ecapa`), ECAPA on VoxLingua107 on torch through SpeechBrain. One
    classification runs at a time a process (a second is `busy`), on
    `stt.classifier_threads` (2) threads.
  - **Where torch may live (Q15).** Only in the library's optional extra
    `t2-agentic-voice[ecapa]` (SpeechBrain 1.1.2, torch 2.15.0, torchaudio 2.11.1), which this
    workspace installs with `uv sync --group language-id` and no app depends on. On Linux,
    torch and torchaudio come from PyTorch's CPU index, so the lock holds no CUDA package; a
    team that adds the extra on Linux needs the same index lines in its own `pyproject.toml`
    (the guide's `languages.md`). Only `adapters` may import torch, torchaudio or SpeechBrain
    (an owner rule in `harness.toml`), and only inside `EcapaLanguage.load`; the library's own
    code may not import `huggingface_hub` (a ban).
  - **Where the model files are kept (Q16).** In the folder `stt.classifier_dir` names, with no
    default, fetched once by hand, outside every repository and `var/` (on the laptop,
    `%LOCALAPPDATA%\t2-agentic-voice\models\`, one folder a model). Each file is checked against
    its pinned size and SHA-256 at every load and by `t2v doctor`. Nothing is downloaded at run
    time. The files, from Hugging Face at pinned commits:
    - `speechbrain/lang-id-voxlingua107-ecapa` at `0253049ae131d6a4be1c4f0d8b0ff483a0f8c8e9`
      (Apache-2.0): `embedding_model.ckpt` 84,474,355 bytes, `classifier.ckpt` 762,555,
      `normalizer.ckpt` 1,063, `hyperparams.yaml` 1,519, `label_encoder.txt` 2,204,
      `config.json` 51 (85,241,747 in all);
    - `deepghs/silero-lang95-onnx` at `bf21c4f59503dc182ab4d69328889b93c51bf70f` (MIT, Silero
      Team): `lang_classifier_95.onnx` 16,972,591 bytes and `lang_dict_95.json` 2,183. A third
      party's re-upload of the file silero-vad v4.0 loads; whether it equals Silero's own was not
      checked.
    The hashes are in the adapters (`ECAPA_FILES`, `SILERO_FILES`) and the guide.
  - **The yes rule with a turn in another language.** When the heard words' language is not the
    read-back's, the rails of the model's judgement (D-082: the no words and the change markers)
    read those of every language the agent speaks; the lists that place a yes stay the
    read-back's. A rail only asks again or corrects, so this never confirms what the rule
    refused before.
  - **What observers see.** `TurnRecord.language` is now the tag of the language the turn was
    sent in, and `TurnRecord.language_by` says how it was chosen (`session` under `session`, so
    a report reads as before); the turn's speech-to-text span names the language sent and, for a
    classified turn, its share. No new public event, no audio, no score of a turn not classified.
  - **What a kept arm changes (Q19).** Nothing in the library's defaults. If run H's keep rule
    holds, the arm it keeps becomes the setting Ole5's live calls run with, which the owner sets
    in their `.env` (`T2V_STT__LIVE_LANGUAGE=classified` and the classifier's keys), recorded in
    an amendment of this entry with the numbers.
  - **The measurement, run H** (plan 007's "Run H"). H1, `poe eval-languages`: every variant of
    a split through the file-fed pipeline at real-time pace, with no spend, in four passes at one
    commit (off, Silero, ECAPA, off again), each turn's classification, decision and end
    recorded; the language each call language (the ordinary call, an Arabic call, an English
    call) would send is computed from that record with the library's rule, and `--read` gives
    the time condition (4) against the two off passes. H2, `poe eval --language-from <H1 pass>`
    (with `--language-base` on dev): Whisper on each variant in the language H1's rule named for
    its first turn. Runs O and the echo timing keep refusing any value but `session`.
- **Consequences:**
  - D-066 gains a third value; its `session` stays the default and its measured `auto` stays
    refused by its rule. D-067's hold and early start never wait on the classifier.
  - D-018's answer to open question 2 (one install, no extras) is amended for this one extra,
    which the base install never needs. D-032's torch check is amended: it now walks `uv.lock`
    from every member's base dependencies, refusing any `torch*`, `nvidia-*`, `cuda-*` or
    `triton` package there, and proves torch comes only through the extra.
  - `poe check` loads no model and imports no torch, and gives the same answer with or without
    the `language-id` group. An exact `uv sync` without the group removes the extra, after which
    ECAPA's `load` refuses with its fix.
  - Costs and risks, said plainly: ECAPA shares the CPU with every call's speech detector and
    Smart Turn (bounded by one classification at a time and the thread setting; run H measures
    one call, and how many calls a CPU holds is the reliability work's count); a verdict comes
    late on turns a little over 2 s, which keep the current language; a long Arabic turn may be
    sent as English when the share passes 0.7 wrongly; text from silence may be sent as English;
    the short turns, where most yeses are, keep the current language, so a short «لا» over an
    English read-back after an English turn goes to Whisper as English (the model's word on what
    it writes decides it, under today's rails). The model's memory is recorded by H1 where the
    platform tells it.
  - Public names gained, all provisional: the port and its scores, the `classifiers` facade,
    `Providers.classifier`, `TurnRecord.language_by` and the new meaning of
    `TurnRecord.language`; the `evals` facade's `turn_languages`, `LanguageTurn`, `chosen` and
    `LanguageChoice`.
  - Debt: several calls classify one at a time (TD-145); the CPU index is checked again at the
    deployment (TD-146); Silero's file is kept by a third party (TD-147).
  - *Amended 2026-11-12, run H on dev: no arm is kept; `session` stays the default, Q19's
    setting is not written, and held-out is not run.* Both classifiers meet condition 4 (10
    paused cut-offs each, 12 allowed; the median paired turn-end difference 0.8 ms for Silero
    and 2.0 ms for ECAPA against the off passes' 1.5 ms) and condition 3. Silero fails
    condition 2: the ordinary call 5 items worse, none better, one a request. ECAPA passes
    condition 1, English in an Arabic call 10 items better and none worse (p = 0.002, the
    English items' accuracy 0.08 to 0.37, no Arabic item worse), and fails condition 2: the
    ordinary call 4 items worse, none better, each a short English turn heard as Arabic in an
    English call, one a ticket number item. ECAPA helps a call held in Arabic and harms only one
    held in English; a rule for that is a dated amendment for the owner before any further run
    (plan 007's Future improvements).
- **Evidence:** the owner's words above; run H's passes and runs (`lid1-dev-off-a`,
  `lid1-dev-silero`, `lid1-dev-ecapa`, `lid1-dev-off-b`; `lid2-dev-label`, `lid2-dev-ar`,
  `lid2-dev-en` and each classifier's three arms, in the history); the download step's smoke of 2026-11-11 (each adapter
  loaded from the folder with no request and no file written; an English, a Saudi and an MSA
  dev variant classified as their items' languages by both; on 2.0 s clips at 2 threads, the
  wall-clock median about 7 ms for Silero and about 250 ms for ECAPA, which are run H's
  expected lines before H1); `tests/t2_agentic_voice/domain/test_turn_language.py`,
  `test_language_scores.py`, `test_yes_rule_languages.py`,
  `tests/t2_agentic_voice/voice/test_stt_language.py`,
  `tests/t2_agentic_voice/voice/session/test_turn_language.py`,
  `tests/t2_agentic_voice/adapters/test_silero_language.py`, `test_ecapa_language.py`,
  `test_model_files.py`, `tests/t2_agentic_voice/testing/test_turn_languages.py`,
  `tests/harness/test_install.py`, `tests/harness/test_arch_models.py`, and Ole5's
  `tests/ole5_voice/evals/test_languages_run.py`, `test_languages_score.py` and
  `test_run_arms.py`.

## D-087 · Every clause a talker call speaks kept on disk by its exact text, behind a setting · 2026-11-11 · Accepted (the owner's rulings of 2026-11-10 and approval of 2026-11-11, plan 007's Block I; `tts.cache_clauses` on by default by the owner's ruling of 2026-11-12, over run I's keep rule)

- **Context:** each clause of a reply is one request to Orpheus, Groq's text-to-speech, which
  streams its audio back. Only the fixed phrases (greetings, notices, progress lines) were made
  once and played from disk (the phrase cache, D-033), and D-033 left caching the talker's
  clauses for later. A clause said again cost a request again: one of Groq's published 10 a
  minute a model (the design's 10.4) and about 0.25 s of waiting for its first audio (plan 003).
  The owner ruled on 2026-11-10, in the roadmap: "we should cache everything we can, because all
  of it is what the agent generated and we have full access to it and since we would an exact
  match, no user will hear the info of another"; and "make it on disk without consent, because
  this what our agent produced". Plan 007's Block I drafted the cache with five questions. Asked
  "Approve Blocks H and I with my recommendations for Q15 to Q25 and the downloads?", the owner
  answered on 2026-11-11 "Approve both", so each is its option (a): every clause a talker call
  speaks is kept, a passage it reads, an action's read-back, its sending line and its outcome
  among them, never the echo's words (Q21); one run T arm measures it (Q22); it lives under
  `storage.var_dir/<agent name>/clauses/`, at most 512 MB, the clauses played longest ago
  removed past it (Q23); the key has no "speaking rules' version", since it holds the text sent
  (Q24); and run I's keep rule, if it passes, turns the library's default on for every team
  (Q25).
- **Decision:**
  - **The settings** (`core/settings/tts.py`): `tts.cache_clauses`, False by default, and
    `tts.clause_cache_mb`, at least 1, 512 by default (a megabyte is 1,000,000 bytes). No folder
    setting: the cache is `storage.var_dir/<agent name>/clauses/`, beside `phrases/`.
  - **The cache** (`adapters/clause_cache.py`, with `clause_files.py`, its folder and its index,
    and `clause_counts.py`, its counts): `ClauseCache` is a `TextToSpeech` that wraps another and
    meets `HeldSpeech`, a protocol beside the port (`domain/ports/text_to_speech.py`) with one
    method, `held(text, *, language)`. The port is unchanged, so `GroqTTS`, a team's adapter and
    every fake stay as they are. It is built with no IO (`ClauseCache(tts, *, folder, voices,
    trim_silence, max_mb)`, or `from_settings`); `open` reads its folder; `aclose` lets its
    writer finish, at most 5 s, drops the rest, and never closes the adapter it wraps.
  - **The key** is a SHA-256 of the files' format tag, the wrapped adapter's `name`, the language
    tag, that language's model and voice, `tts.trim_silence`, and the text exactly as the provider
    is sent it, hashed from a JSON list so two inputs cannot run together, cut to 32 hex
    characters. The text sent comes after the speaking rules, the pronunciation map and
    `provider_text`, so a change to any of them that changes a clause's words changes its key
    (Q24); D-033's rule of keying on the text sent, never the text written, is the clause
    cache's too. With the adapter's name in it, a take one adapter made never plays for another.
  - **Keeping a take.** `synthesize` passes each chunk on at once, unchanged, and keeps a copy.
    Only once the stream has ended whole is the take queued: one sample rate, some audio, no
    chunk cut short, at most 4 MB. A take that raised, came back cut short, gave no audio or was
    stopped is never kept. `synthesize` never serves a held take: the bridge asks `held` first.
  - **Writing.** One writer task, its queue at most 64 takes (a full queue drops the take); each
    write in a thread, to a temporary name and then renamed (`adapters/wav_files.py`, which the
    phrase cache now uses too). Two takes of one clause at once: the first is kept, the second
    is counted as held.
  - **Reading.** At `open`, in a thread, each take file of its own naming is an entry, and each
    temporary file of its own naming is removed; nothing else in the folder is read, touched or
    removed (GP-21). The index lives in memory, so a miss is a dictionary look-up. A hit is read
    in a thread within 100 ms, else it is a miss and the clause is requested as before. A file is
    a take only when it reads as the cache writes one (a mono 16-bit WAV, its frames matching its
    header, at most 4 MB); anything else is a miss, its entry dropped and its file removed.
    `held` never raises.
  - **The bound.** Past `tts.clause_cache_mb`, the writer removes the takes played longest ago
    until under nine tenths of it; a hit moves its take last and touches its file. A file the
    system will not let go of stays for the next round, and the trim goes on down the order, so
    the bound holds, the take just written included.
  - **`clear()`** removes every take it keeps (its own files, in its own folder) and resets its
    counts. **`counts()`** and **`taken()`** (which also resets them) give a frozen
    `ClauseCounts`: hits, misses, takes kept, takes not kept by why, unreadable files, failed
    writes, takes removed, the entries and megabytes held, and each look-up's seconds, hits' and
    misses' apart; no text and no key.
  - **The bridge** (`voice/tts_bridge.py`) checks once, when it is built, whether its
    text-to-speech holds speech. If so, a clause with text and no fixed audio asks `held` first.
    A take it gets plays as a fixed phrase plays, with no `Synthesizing` and no request, once the
    bridge has checked again that no stop dropped the clause while it was read; its
    `ClauseQueued` is marked `held`. With any other text-to-speech nothing is looked up.
  - **The session's counts** (`voice/session`). A held clause is a cache hit but never a fixed
    phrase: `Clause` gains `held` beside `cached`, the reply's span counts `cached or held` as its
    `cache_hits`, and the call's usage counts the hit with no characters.
  - **A reply said again says what was sent** (not behind the setting, since it corrects what a
    caller hears). `Clause` gains `sent`, the request's text, and its own language. The repeat
    (`Speaker.repeat`, the echo's `again`) sends each clause's `sent` text in its own language,
    the call's when it has none, where it used to send the caption in the call's language. So
    a repeat says each clause as it was first said (the speaking rules applied, an English clause
    of an Arabic call in the English voice), and finds its held takes.
  - **The composition** (`api/voices.py`): it declares the phrase cache on the providers'
    text-to-speech, then, with `tts.cache_clauses` on and an agent whose calls run the talker
    (`settings.session.mode_for`), builds and opens the clause cache over it and pushes the
    cache's own close on the runtime's stack; otherwise the calls get the providers'
    text-to-speech itself. An echo agent's calls never have one: the echo says the caller's words
    back, which the owner's reason ("what our agent produced") does not cover. An `OSError`
    making or reading the folder at the start stops the runtime's start, as the phrase cache's
    does.
  - **Public:** `ClauseCache` and `ClauseCounts` in the `stores` facade beside `PhraseCache`, so
    a timing run builds the cache as the runtime does. D-032's sentence on `stores` is amended
    with it: `ClauseCache` is the second public name no public signature names
    (`ClauseCounts` is named by `counts()`).
  - **Logs:** `clause_cache_opened`, `clause_cache_closed`, `clause_cache_trimmed`,
    `clause_unreadable`, and `clause_write_failed`, `clause_lookup_failed` and
    `clause_writer_failed` with the error's type only: never a text and never a key, since a key
    is a hash of a short text that can be guessed back (GP-19).
  - **What it never does:** keep the caller's audio or the echo's words; keep a take that
    failed, was cut short, gave no audio or was stopped; play a take for any text but the one it
    was made from, in the same language, model, voice, adapter and trimming; send a request of
    its own; fail or delay a clause on a disk error (a miss, then the request); write outside
    its folder, or remove a file not of its own naming; ask consent (the owner's ruling); log a
    text or a key.
  - **Ole5's part: run T's arm only** (run I, plan 007's measurement). `poe first-audio` gains
    `--clause-cache on|off`, off by default, refused for held-out. On, the run pins
    `tts.cache_clauses` true in its recorded settings and the replay builds the cache, new, in
    the run's folder (`<out>/clauses`), over its counting voice, so the voice counts only the
    requests a miss sends. The replay opens it before its start says the progress lines, takes
    its counts once each call has ended, and drains it at its close; the run clears it once the
    smoke call has passed, so the first measured call starts cold. A recording's attempts keep
    their counts apart, and one replayed after a rate limit is left out of the shares. The
    scorecard and the history line hold the run's numbers (`ole5_voice/evals/first_audio_cache.py`):
    the hits' shares in each item's first variant and in the rest, the look-ups' times, Orpheus's
    own first audio beside them, the turns whose first clause was held, the requests per call
    minute with and without the hits, the takes, and the keep rule's first four conditions. Ole5
    sets nothing in its own settings or server until the keep rule says so.
- **"No user will hear the info of another."** The audio is a function of the key alone, and the
  key holds the whole text, so a hit says exactly the words the agent is saying to this caller
  now. A ticket number reaches speech only in an outcome line, unique to its ticket, or in the
  last four digits of the caller's own tickets (invariant 3). A read-back is heard again only by
  a caller whose read-back is the same word for word. Said plainly: a hit starts sooner than a
  request, so a caller who can make the agent say a clause exactly could tell whether it was said
  in some call since it was last removed. The agent judged it negligible and proposed nothing
  (the owner's rule of 2026-11-03, no hardening rounds). At rest, the cache keeps the agent's
  words from calls as audio, read-backs of callers' requests among them; the traces keep the
  same text already (D-079).
- **The invariants.** D-033 is amended: "Text built from heard words never reaches the phrase
  cache" stays true of the phrase cache, which holds only the declared phrases; the clause cache
  keeps every clause a talker call speaks (a read-back too), never the echo's words, and this
  closes D-033's sentence that left caching talker clauses for later. Invariant 8
  (`docs/SECURITY.md`) gains a sentence: the agent's own synthesized voice (the phrase cache and
  the clause cache) is not call audio and is kept with no consent, though the clause cache's
  takes say the agent's words of a call; SECURITY.md's trust boundaries gain a row for call
  content at rest under `storage.var_dir`. Invariant 2 holds: the guard reads each clause
  before it is asked for, and a hit plays exactly that text's audio; Block G's filter sits
  before both (D-084). Invariant 3 holds: the cache gives no tool or caller anything. Invariant
  7's lock file keeps one writer a folder. D-066 and D-067 are not touched.
- **Why off by default:** GP-18. A characterization test proves the path with the setting off
  unchanged, and the existing text-to-speech, speaker, session and run T tests pass unchanged.
  Run I (plan 007's measurement, `i1-dev-120b`) reads, on run T's dev split, the hits, the
  Orpheus requests saved, each look-up's time and the time to first audio; only if all five of
  its keep rule's conditions hold does `tts.cache_clauses` become True by default for every team
  (Q25). Otherwise the default stays off, the result is recorded, and the cache stays for a team
  to turn on. *Amended 2026-11-12, run I's result: the default stays off.* Of 266 clauses asked,
  9 were held (3.4%), all in an item's later variants and none in a first one (condition 2,
  at least 2%, fails); a miss's look-up 0.038 ms and a hit's read 10.5 ms at p90 (conditions 3
  and 4 hold); two calls failed, neither from the cache (condition 1, no call failed, fails);
  the search path's p90 4,397 ms against T0's 3,009 and the 4,000 bound, the knowledge base
  timing out in the run (condition 5 fails). The cache works and costs no time, but a clause
  seldom comes back within the agent's calls.
  *Amended again 2026-11-12, the owner's ruling: on by default.* Told run I's result, the owner
  ruled "turn on clause cache as the default of the library since it helps and never costs
  anything except space, its failed conditions do not really reflect its value": of the three
  conditions that failed, two read the network of the day (a call lost to Whisper, one request
  refused, the knowledge base's timeouts on the search path) and one the share of first-variant
  hits, while a miss costs 0.04 ms and a hit saves a request and about 0.2 s. So
  `tts.cache_clauses` is True for every team, bounded by `tts.clause_cache_mb`, and
  `T2V_TTS__CACHE_CLAUSES=false` turns it off; run T's `--clause-cache` stays off unless named,
  so its runs stay comparable with T0's. GP-18's measured move is waived here by the owner's
  word, recorded as such.
- **Consequences:** a team that turns it on keeps the agent's words of its calls as audio under
  `var_dir`, at most `tts.clause_cache_mb`, removed only past the bound or with the folder; the
  guide's data-and-privacy page says so. `ModelUsage.cache_hits` (public) now counts held
  clauses too, so a call with the cache sends fewer `requests` and `characters`; a turn's
  `tts_first_audio_ms` is the first requested clause's, so a held first clause moves it to the
  next or leaves it empty. One bad take (clipped or mispronounced, but not flagged cut short)
  plays to every caller who gets that text until it is removed, and the same if Groq changes a
  model under its name: the remedy is to delete the folder. The phrase cache's key still leaves
  out `tts.trim_silence` and the adapter (TD-061). `ClauseQueued` gains a field with a default,
  `stores` two names, and the phrase cache's reading now refuses a file whose header counts more
  frames than its data. No public event, `TurnRecord`, `CallReport` or `t2v/1` message changes.
- **Evidence:** plan 007's Block I, "Run I" in its measurement, and "The owner's decisions" (Q21
  to Q25); the tests `tests/t2_agentic_voice/adapters/test_clause_cache.py`,
  `tests/t2_agentic_voice/adapters/test_clause_cache_files.py`,
  `tests/t2_agentic_voice/voice/test_tts_bridge_held.py`,
  `tests/t2_agentic_voice/voice/session/test_held_clauses.py`,
  `tests/t2_agentic_voice/testing/test_audio_call_clauses.py`,
  `tests/t2_agentic_voice/core/test_settings_clause_cache.py`,
  `tests/t2_agentic_voice/api/test_runtime.py`, and Ole5's
  `tests/ole5_voice/evals/test_first_audio_cache.py`.

## D-088 · The gate's tests run on every core, and its slowest tests do less of what the gate already does · 2026-11-11 · Accepted (the owner's request and approval of 2026-11-11)

- **Context:** the owner asked "can you optimize the gate tests so that it doesn't take too much
  time every time we use it". `poe check` took 14 to 15 minutes, almost all of it the test step:
  7,438 tests, one after another, on one core of the laptop's eight (coverage already on
  Python 3.12's `sys.monitoring`, `core = "sysmon"`). A profile (`--durations`) found 150 tests
  at half a second or more making 62% of the time: a test that ran the gate's own commands on the
  whole repository again, the architecture and docs checkers' "repository is clean" tests (what
  the gate's `arch` and `docs` steps run), a pacer test that played a real minute of frames, run
  A's runner tests playing every dev scenario, and 48 small-project architecture tests each
  reading every installed distribution's files.
- **Decision:**
  - **Every core:** `poe test` runs `pytest -n auto` (pytest-xdist 3.8.0, with execnet 2.1.2, MIT,
    in the root's dev group; the owner answered "Yes, download them"). Each worker is a process of
    its own, so the suite's isolation (tests/conftest.py, tests/isolation.py) holds in each; the
    whole suite passed on six workers with no change to a test.
  - **Less of what the gate already does**, each test keeping what it protects: the commands
    test runs the real `python -m` checks on two small projects, one clean and one with an
    architecture and a docs violation, and asserts each exit code and last line; the checkers'
    "repository is clean" tests keep only what the gate's steps do not fail on (that the check
    reads real code and docs, never an OK on zero files); ARCH-DOC's repository test calls its
    rule alone; `tests/harness/conftest.py` reads the installed distributions once a run for the
    48 architecture tests (the environment cannot change within a run).
  - **No wall clock for a minute:** the pacer test plays its minute on a fake clock that steps as
    Windows' 15.6 ms clock does at its worst, at the original 100 ms bounds, beside one real
    second (it still catches a pacer that drifts: one sleeping a frame each time ends 33.8 s late).
  - **Smaller fixtures:** run A's runner tests play three dev and two held-out scenarios; the
    committed set is still read and checked by the real loader.
- **Consequences:** the gate takes about 3 minutes (179 s wall, its tests 158 s, while two other
  builds used the machine), from 14 to 15; on one core the trimmed suite takes 499 s, from 645 s
  on a quiet machine. Coverage holds at 99.40%. `poe test` run alone no longer fails on an
  architecture or docs violation anywhere in the repository; `poe check`, the definition of done,
  still does through its `arch` and `docs` steps. The real-time call tests (about three minutes
  of a serial run) are left as they are, since shortening each means re-timing its silences
  against the speech detector and turn timers. TD-072's pacer part is paid.
- **Evidence:** the profile and the timings above; `tests/harness/test_commands.py`,
  `tests/harness/test_check_architecture.py`, `tests/harness/test_check_docs.py`,
  `tests/harness/test_arch_doc.py`, `tests/harness/conftest.py`,
  `tests/t2_agentic_voice/voice/test_file_transport.py`, `tests/ole5_voice/evals/test_action_run.py`.

## D-089 · Four fixes from the owner's live calls: a draft's change, the model's reasoning, a negated claim, a turn split by a pause · 2026-11-12 · Accepted (the owner's approval of 2026-11-12, "Yes build them all", and their ruling on split turns)

- **Context:** after plan 007's held-out run passed, the owner made ten calls on the dev console
  (and a friend tested the English agent): "all of them went good", with one exception, call
  `_Hdmiy0vDE`, where "it asked me for a ticket number when I tried to submit one". Reading
  the ten records found four faults, each once:
  - **A draft's change taken for a note** (`_Hdmiy0vDE`, turn 4). The read-back stopped with
    «خلاص خلاص» (as the owner's stop ruling has it), the talker asked what to change, and the
    owner said «اذكر في التذكرة انه النظام معلق على جميع المستخدمين في شركتنا» ("mention in the
    ticket that the system is stuck for all users in our company"). The model took "mention in
    the ticket" for `add_ticket_note` and asked for the last four digits of a ticket never
    made. The prompt says a change calls the action again; nothing said it after a stop, and
    the note tool's description did not say it is never for a ticket only read back.
  - **The model's reasoning said aloud** (`_Hdmiy0vDE`, turn 5): «…عشان أضيف الملاحظة.User:
    "ما أعرف، سولها". Possibly they want us to ask the system for ticket status? But we can't.
    According to policies, …», played whole. gpt-oss wrote it into its answer, glued to the
    sentence before with no space. The adapter keeps only the answer's channel; nothing caught
    reasoning inside it. Because the clause splitter cut nothing inside a word, the glued
    sentences also hid a second question from the question limit (D-085). Run A's a2-dev
    stored the same kind of leak («…حالياً.We need to respond accordingly.…»), and 7 of the
    4,467 distinct clauses the runs stored hold a glued sentence.
  - **A negated claim blocked** (`_Hdmiy0vDE`, turns 8 and 9). Asked «افتحت التذكرة؟» with no
    ticket made, the reply was held back twice as `unsupported_claim` and the caller heard the
    `error` notice twice. The guard stores no blocked text; an offline check shows rule A blocks
    «ما فتحت التذكرة» ("I did not open the ticket"), which holds «فتحت التذكرة». The guide
    listed this as a known limit.
  - **A turn split by a pause** (`LTLrFU`, turns 5 and 6): "what tickets submitted with my", a
    pause past the end of turn, then "email". The second turn stopped the first's reply before
    any of it played, so the talker had both turns, but as two messages. It answered "email" as
    a question about sending email. The owner, approving the fixes: "A turn being splitted into
    two is a common thing to happen, so we need to account for it".
- **Decision:**
  - **A change after a stop calls the action again.** The library's note for a stopped
    read-back (agent/context.py's `DECLINED["stopped"]`) now ends "…and once they say it, call
    {action} again with the change". Ole5's note tool says it is "never for one only read back
    and not yet made: a change or an addition to that one, such as "mention this in the
    ticket", is a change to its draft, so call create_ticket again with it". Run A's dev
    scenario a48 gains a third turn: the change said that way, read back in a new draft, with
    no ticket number asked for.
  - **The model's reasoning is never said** (agent/leaked_reasoning.py, before the clause
    splitter, after the stray-script filter). From a sentence glued to the one before (a
    sentence's mark after a letter, a digit or a letter's mark, then no space) that begins with
    a capital Latin letter in a reply in Arabic, or with one of the reasoning's openings ("We
    need", "According to", "The user", "Possibly", …) in any language, or from any sentence that
    begins with a speaker's label ("User:"), nothing more of that request's text is said. The
    clause before it is said, the stream is closed (as `drop_rest` closes it), no tool of that
    request runs, and no request follows. `talker_reasoning_dropped` logs the count alone. The
    clause splitter cuts a word at a glued sentence's end before a letter that is no lowercase
    Latin one, so "t2.example", "3.5" and "e.g." stay whole, and a glued sentence it lets
    through is a clause of its own. A word list is the fast path: a model check of every reply
    would cost every reply its time (the owner's "lists plus a model's judgement" keeps the model
    for what the lists miss; none is added here). There is no setting; one can be added if a
    team's model needs it.
  - **A negated claim claims nothing** (domain/claims.py). A phrase right after ma or mub (waw
    or feh written onto it too) is no claim, unless the word before the negation makes it a
    conjunction (ba'd, awwal, yawm, kull, zayy, mithl, qabl, leen, tuul, daam: «بعد ما فتحت»,
    after I opened), «إلا» or «غير» (only) follows the phrase, or the clause asks a question.
    Any other phrase in the clause is read as before. The English defaults hold no negation to
    begin with.
  - **A turn split by a pause reads as one** (agent/context.py's `continued`). When the caller's
    words stop the reply to their last turn before any of that reply was heard, and they were
    said over nothing heard, they go on with that turn: the two are one user message, the
    earlier's words first. The calls, results and notes the talker kept of the earlier turn stay
    where they came, before that message, so the model sees what it found for the first part
    and decides again on the whole (a correction's second part may need another search: run
    S's s05). Past turns read the same: a `rolled_back` turn and the caller's next turn, with no
    heard reply between them and the next not a command, are one message. Nothing of the
    session changes: the report, the events and the yes rule keep each turn's own words.
- **Consequences:**
  - The caller of `_Hdmiy0vDE` would have heard the read-back again with the change, "I need the
    ticket's last four digits to add the note." and nothing after it, and "no, I did not open
    the ticket".
  - The caller of `LTLrFU` would have been answered "what tickets submitted with my email".
  - Run A's held-out split runs once, and its run passed before these fixes, so a48's new turn is
    dev's alone, and the fixes are checked on dev run A and run S (plan 007's progress log).
  - Over the 1,827 distinct replies the runs stored, the leak rule fires once, on a2-dev's
    leak.
- **Evidence:** the ten dev-console records (`var/dev-console/*.jsonl`, the owner's, read
  only); `tests/t2_agentic_voice/agent/test_talker_split_turns.py`,
  `tests/t2_agentic_voice/agent/test_leaked_reasoning.py`,
  `tests/t2_agentic_voice/domain/test_claims.py` (the negation's adversarial cases),
  `tests/t2_agentic_voice/domain/test_clauses.py`, `test_clause_stream.py`,
  `tests/t2_agentic_voice/agent/test_talker_actions.py`, `tests/ole5_voice/tickets/test_actions.py`,
  `tests/t2_agentic_voice/voice/session/test_talker_kept_steps.py`; plan 007's progress log for
  the runs.

## D-090 · Code names no plan's tracks or blocks (DOC-PLANWORDS), and a real-time test holds on a loaded machine · 2026-11-13 · Proposed (the agent's, under garbage-collection.md's step 5, in the round the owner asked for on 2026-11-13; the inventory the owner answered named the check)

- **Context:** garbage collection round 2 (plan 008) read plan-time names in the library's and
  the Ole5 app's living docstrings in six areas (its agt-4, dom-10, tst-13, ada-9, api-11, and
  the facades' "plan 007's Block H"), after round 1 had removed them once (plan 004's app22): a
  plan's tracks and blocks are its own work units, and once it is completed they tell a reader
  nothing. The round's gates then failed real-time tests under the load of several gates at
  once, in three blocks' runs and on the merged branch, each passing alone: the clause cache's
  0.1 s disk reads, a 0.1 s chat deadline that held the SDK's first request, a 50 ms and a 0.1 s
  bound in `test_stt_language.py`, and a loopback duck bounded at 0.03 s that took 0.229 s.
  Both are mistakes seen twice; garbage-collection.md's step 5 makes such a mistake a check, a
  test or a doc.
- **Decision:**
  - **DOC-PLANWORDS** (`scripts/doc_refs.py`, from `poe docs`, beside DOC-MILESTONE): no code
    file (`[docs] code_dirs`, its exempt files aside) nor a TOML file at the root names a plan's
    track or block, the word followed by a capital letter or a number. Code names the
    capability, or cites the decision or the plan. Docs are not read: a plan's own record of its
    tracks is its history. GP-14 names it.
  - **A real-time test holds on a loaded machine**, since the gate runs on every core (D-088): it
    checks the order of events or what was given, or runs on the test's clock; a limit the test
    is not about is raised in the test; a wall-clock bound the test is about leaves room for the
    load. GP-12 says it, enforced by review: no check tells a bound a test is about from one it
    is not.
- **Consequences:** the branch held 209 such names after its first four blocks, 7 after the
  last two, and none at the close. The round's real-time tests changed as the rule says: the
  clause cache's tests raise the cache's read limit (`relaxed_reads`, in the adapters' tests'
  conftest) but for the test of a slow read; the chat deadline test warms the SDK first and
  bounds 0.5 s; the language test's held request is checked by order and its blocking
  classifier at half its 2 s block; the loopback test checks the stop path's order and the
  amount of audio the client heard. Three wall-clock bounds W2 saw and never saw fail
  (`test_file_transport.py`, `test_turn_hold.py`, the calls' ticker) are left as they are.
- **Evidence:** plan 008's inventory, progress log and decision log; the rule's test,
  `tests/harness/test_doc_refs.py`'s `test_code_and_the_root_toml_never_name_a_plans_track_or_block`;
  the tests changed, `tests/t2_agentic_voice/adapters/conftest.py`,
  `tests/t2_agentic_voice/adapters/test_groq_chat_checks.py`,
  `tests/t2_agentic_voice/voice/test_stt_language.py` and
  `tests/t2_agentic_voice/test_loopback_interruptions.py`.

## D-099 · M9, the voice experience at the level of top-tier voice agents, comes now, before M6 and M7 · 2026-11-16 · Accepted (the owner's approval of plan 010 on 2026-11-16)

- **Context:** M5 closed on 2026-11-12, and that day the owner asked to skip M6 and M7: "Ok, now
  that the pure voice agent is done, I want to skip M6 and M7 for now". On 2026-11-15 testers'
  calls showed what still keeps the voice behind top-tier agents (old search results drowning new
  questions, refusals without a search, repeats, Arabic hearing, the silence timer, the first
  connect), and the owner asked to take the voice experience to that level. Voice for a team's own
  agent is built on its own branch (`plan-009-integration`), which main does not hold; the owner
  ruled on 2026-11-15: "No I want to build on todays main, while only getting voice improvements
  from plan-9, I am not interested by integrating Langchain/Langgraph agents now. I just want to
  elevate the voice experience".
- **Decision:** plan 010 is M9 and comes now, built on main; M6 and M7 come after it. It takes
  from the team's-agent branch only five voice pieces, by path, each commit naming its source.
  The plan sets no dates and orders its work by gain per hour of work, the obvious wins first.
- **Consequences:** M6's reliability work and M7's rehearsal wait. The roadmap holds no M8 on
  main, since the team's-agent branch uses that number. If that branch is ever merged after this
  plan, its pure-move splits conflict with this plan's edits in `agent/` and `voice/`: a later
  decision, only if the owner wants it.
- **Evidence:** the owner's words of 2026-11-16: "Ok, I approve the plan. Lets start implementing,
  focus on what brings the best improvements by hour of work and obvious wins first." and "Lets
  not set timelines, we will work at our pace"; plan 010.

## D-100 · Other providers measured on the owner's and testers' calls; Groq stays the default until a bake-off and the owner's ruling · 2026-11-16 · Accepted (the owner's answers to plan 010's Q16, 2026-11-16)

- **Context:** D-004 kept Groq the only provider. Plan 010 found Arabic hearing the biggest gap
  in the voice (the owner's Saudi speech heard about 7 times worse than English, WER 0.344
  against 0.048; "Ole5" heard right 0 of 9 times live), the talker weak in Arabic, and no way to
  switch language with Whisper told the call's language. Its provider study named candidates
  Groq does not host: ElevenLabs, Speechmatics, Cohere and Soniox for speech-to-text, ElevenLabs
  and Inworld for voices, OpenAI and Google for the talker. The owner answered on 2026-11-16: "I
  can provide some new models providers for you if you make a search and give the best ones to
  test" and "I can provide this today if you guide me to the best options we can have".
- **Decision:** D-004 is amended for measurement. Another provider may receive the owner's and
  testers' audio or text, in a bake-off or a tester's call, once (1) its adapter sits behind the
  library's port for that part (D-030, GP-22); (2) its key is a `SecretStr` setting with a
  `_FILE` form, never logged (GP-19); (3) it has its trust-boundary row in SECURITY.md (its
  output is data, never an instruction) and its adapter's `DataFlow`; and (4) the owner has set
  its data controls (training off) before the first request. A provider becomes a default only
  on its bake-off's registered rule (plan 010's measurement section) and the owner's ruling;
  until then Groq stays the default and the fallback.
- **Consequences:** the Groq-only setting types are loosened (`stt.provider` first), and each
  key's setting is added before the owner pastes the key into `.env`, since a `T2V_` name the
  settings do not know stops the app. Callers who are not developers still wait for M6's notice
  (D-076); testers are told whose service hears them (plan 010, Q3).
- **Evidence:** the owner's words above; plan 010's provider guide of 2026-11-16 (the
  accounts, their data settings and the names of the keys' settings).

## D-101 · The flight-booking agent is the second app and the main agent shown; Ole5 is the check that a change is general · 2026-11-16 · Accepted (the owner's request and answers to plan 010's Q23, 2026-11-16)

- **Context:** plan 010 set out to take the voice to the level of top-tier voice agents, measured
  on Ole5's calls. On 2026-11-16 the owner gave the agent a teardown of a public airline-concierge
  demo they admired and asked: "For the sake of comparison, lets make our voice agent do a similar
  use-case (flight booking), and let make the ole5 as a reference or an assurance that both benefit
  from the improvements and a prove that the improvements are general, but lets make the demo and
  testing and comparing using the flight booking agent." Then: "I want the flight agent to be our
  main agent we show and work on."
- **Decision:** a second app, `apps/flight-voice-agent/` (package `flight_voice`), built only on
  the library's public API like Ole5, with a mock airline, read-only tools and one action, the
  booking, read back in full and confirmed by a clear spoken yes (invariant 1), never by a typed
  code. Every option is spoken; the page may also show cards mirroring what was said, never
  needed (the owner's answer "Spoken + optional cards"). It has its own page on its own port, a
  male Saudi voice, and a persona and an airline named by the owner. It is the main agent shown,
  and its scripted calls (run F) are plan 010's demo and main test set; Ole5's sets rerun after
  each change to a shared part, as the check that the change is general. Its build spec is
  [flight-voice-agent.md](flight-voice-agent.md).
- **Consequences:** the library gains what a second app needs (the access-code route, the call's
  date, spoken numbers by register, card rows, the measurement's paced model), each used by Ole5
  too. The library's checks and docs count two apps. Nothing is copied from the demo's brand, text
  or prompt.
- **Evidence:** the owner's words above, and their answers to Q23 of 2026-11-16: "Spoken +
  optional cards (Recommended)", "Read-back + spoken yes (Recommended)", "A male Saudi voice, name
  later (Recommended)", "Its own page (Recommended)".

## D-102 · websockets declared by the library and owned by its adapters · 2026-11-16 · Proposed (the agent's; needed by the two streamed providers the owner asked to test on 2026-11-16, with no download)

- **Context:** the owner asked on 2026-11-16 to test HUMAIN's speech engine and Nabrah's. Both
  hear a turn only over a WebSocket: HUMAIN's through Telnyx's streaming endpoint
  (`humain/realtime`), Nabrah's on its own. websockets 17.4 was already installed, under
  Pipecat, and ARCH-DEPS refuses an import the library does not declare.
- **Decision:** the library declares `websockets>=17.4` (uv.lock gained only the declaration;
  nothing was downloaded) and harness.toml's owners give it to the adapters layer beside httpx,
  with ARCHITECTURE.md's table to match. Its connections take no proxy variable and a logger
  that logs nothing (`adapters/provider_socket.py`), since its debug log writes the handshake's
  headers and every frame, and Nabrah's key travels in a frame. Its TLS keeps Python's default
  context, which still reads `SSL_CERT_FILE` and `SSL_CERT_DIR`: TD-004 and TD-015 cover it.
- **Consequences:** a streamed provider sits behind the batch speech-to-text port, one turn a
  connection, and pays its pacing there (TD-152) until a streaming port exists (plan 010's 5.1).
- **Evidence:** both adapters' smokes on 2026-11-16 (`b02_eh` heard right: Telnyx's HUMAIN engine
  in 4.8 s, Nabrah in 1.3 s); their tests on a fake socket.

## D-103 · A call's language may move within the call: any question or request in the other language moves it · 2026-11-16 · Accepted (the owner's ruling of 2026-11-16 under plan 010's Q20; off by default until run H keeps it)

- **Context:** D-038 fixed a call's language at join, so Whisper, told the call's language,
  translates an English question in an Arabic call into fluent wrong Arabic. On 2026-11-16 the
  owner ruled: "No, any English question or request should be enough to change the language and
  vice versa. We can achieve this be trying other providers STT, maybe they have auto-detection,
  they give probabilities or we use a language classifier to lock the language between Arabic
  and English."
- **Decision:** a fourth value of `stt.live_language`, `detected`, keeps the call's current
  language, the join's at first, as `session` does; each request names it with its prompt. A
  turn with at least `stt.detect_from_s` (1.2) seconds of voiced speech, counted from where the
  speech detector heard it begin to where it last stopped, never the silence after (ECAPA's gate
  failed by counting it, D-086), also goes at the same time naming no language and with no
  prompt. When that request hears the agent's other language (the provider's name mapped
  exactly, `domain/words.py`'s `heard_code`) and the turn is a question or request (two words or
  more, and not only the short replies of either language in either script,
  `domain/language_switch.py`), the turn's heard words are that request's and the call's current
  language moves to it: later requests name it, and the reply, the voice, the fixed phrases and
  the knowledge query follow. A spoken switch request ("English please", in both scripts,
  including how Whisper writes it told the other language) moves the call too, said over a
  reply or not, and the talker's `switch_language` tool moves it for any other wording. A
  read-back waiting when the call moves is dropped unconfirmed and read again in the new
  language, a new receipt required (invariant 1). A provider that reports no language it heard
  (Speechmatics' pack, Cohere, Telnyx's HUMAIN engine, Nabrah: `HEARS_NO_LANGUAGE`) gets no second
  request; its calls move only on a switch request or the tool.
- **Consequences:** each long turn costs one more Whisper request. `session` stays the library's
  default (GP-18); the Ole5 app turns `detected` on only when run H keeps the arm, by the rule
  plan 010 registered before any run. The dev console can choose it per call (D-104). A short
  "English please" said over an Arabic reply lets that reply play to its end, and the next one
  is English; stopping the reply would change the interruption rule, a measured outcome.
- **Evidence:** the owner's words above; tests `tests/t2_agentic_voice/domain/test_language_switch.py`,
  `tests/t2_agentic_voice/voice/test_stt_detect.py`, `tests/t2_agentic_voice/voice/session/test_call_language.py`,
  `tests/t2_agentic_voice/testing/test_audio_switch.py`; run H's numbers are added when it reads.

## D-104 · The dev console may choose one call's speech-to-text provider, model and language mode · 2026-11-16 · Accepted (the owner's request of 2026-11-16)

- **Context:** the owner, 2026-11-16: "A teammate wants to try them so as a way of trying them
  myself and my teammate in github, give me the option to try these deferent provider/models
  through the dev console as a quick way to try/switch them."
- **Decision:** the dev console's own routes (`<prefix>/dev/stt`, under `env` dev with the dev
  page on, loopback only) list the speech-to-text providers whose key is set (Groq's always), the
  models each takes, and the language modes, never a key or its path; a choice made before a
  call's offer is held to that closed list and taken by that call alone. No join token and no
  `t2v/1` message can choose. Each turn's line in the console, and its record, name the provider
  and model that heard it, with the request's time.
- **Consequences:** a developer tries each provider on a live call with their own keys in their
  `.env`; it measures nothing and moves no default (D-100 unchanged). A call heard by another
  provider still reports its usage under `stt.model`'s name (TD-153).
- **Evidence:** `tests/t2_agentic_voice/api/test_dev_stt.py`,
  `tests/t2_agentic_voice/voice/test_calls_talker.py`, the browser tests `test_browser_stt_choice.py`.

## D-105 · ElevenLabs' Scribe v3 is the default speech-to-text; Groq's Whisper the fallback · 2026-11-16 · Accepted (the owner's ruling of 2026-11-16, over the latency condition of plan 010's registered rule)

- **Context:** plan 010's comparison of 2026-11-16 (docs/project/stt-report-2026-11-16.md) ran
  seven providers on the golden set's dev split, 292 recordings of the owner's voice. ElevenLabs'
  Scribe v3 heard 209 right in its first run and 215 in its second, against Whisper large-v3's
  129 in both of its runs: 47 and 50 items better, 7 and 5 worse, beyond the noise each time, and
  better beyond the noise in Saudi Arabic and MSA in both runs (and in English in the second).
  Product terms caught 90% and 93% against 33%, ticket numbers 90% and 95% against 57%. It was
  slower: a request's median 514 ms and 669 ms from this laptop against Whisper's 259 ms and
  348 ms, so the registered rule's condition "no slower than Whisper plus its spread" fails, and
  the rule alone keeps Whisper. Asked "Make ElevenLabs Scribe v3 the default once its second run
  confirms it?", the owner answered on 2026-11-16: "Yes make ElevenLabs Scribe v3 the defualt".
- **Decision:** `stt.provider` defaults to `elevenlabs` (Scribe v3, keyterms from the agent's
  vocabulary, the language it heard and its probability on each transcript). Groq's Whisper is
  the fallback, chosen with `stt.provider = "groq"`. With the default and no ElevenLabs key, the
  runtime refuses to start, naming `T2V_ELEVENLABS__API_KEY` and the Whisper fallback in its FIX.
- **Consequences:** a call waits about a quarter to a third of a second more per turn for its
  words, until a streaming port lets Scribe v3 Live hear the caller while they speak (plan 010's
  5.1). Every developer needs an ElevenLabs key beside the Groq key, or sets the fallback; the
  quickstart sets it, to keep its one key. The audio of every call goes to ElevenLabs (D-100's
  conditions, its trust-boundary row in SECURITY.md); callers who are not developers still wait
  for M6's notice (D-076). The team keeps provider keys in `.env` as the key strings themselves
  (the owner, 2026-11-16: "I want the variables in .env to hold the real key strings and not a
  path to it").
- **Evidence:** the runs `b0-groq`, `el-dev` and `el-dev2` and the switch's Whisper baseline
  `sw2-dev-label`, in the run history (docs/generated/eval-history.md); the owner's words above.

## D-106 · An agent's time zone is a fixed offset from UTC, and a test call's date can be pinned · 2026-11-16 · Accepted (the lead's ruling of 2026-11-16 under D-101: no tzdata download)

- **Context:** the flight-booking agent (D-101) resolves "next Thursday" and «الخميس الجاي»
  against today in Riyadh, and its scripted calls need a fixed today. Python's zone names need
  the tzdata package on Windows, which is not installed and would be a download the owner has not
  approved; Riyadh keeps UTC+3 all year.
- **Decision:** `VoiceAgent.time_zone` is a `timedelta` or a fixed `datetime.timezone`, whole
  minutes from -12:00 to +14:00, UTC by default; a zone's name or anything else is refused when
  the agent is declared, naming the field. The prompt's "Today is" and the guard's year read in
  that zone. `TextCall(today=...)` and `AudioCall(today=...)` pin a test call's date.
- **Consequences:** an agent in a zone with summer time must give the offset it runs in; the
  flight agent's mock airline gives each airport a fixed offset and keeps its booking window in
  winter. Ole5 is unchanged (UTC).
- **Evidence:** the tests of `VoiceAgent.time_zone` and the pinned date (the flight library job,
  2026-11-16).

## D-107 · Numbers, times, dates and key combinations said in the caller's register, behind settings · 2026-11-16 · Accepted (the owner's answer to plan 010's Q11, "As proposed", 2026-11-16; off by default until row 1.8's measurement, GP-18)

- **Context:** replies said "Ctrl + Shift + R" symbol by symbol and numbers in one MSA form
  (num2words), and the flight agent says times, dates and fares in every turn. Q11's spoken forms
  were answered "As proposed" on 2026-11-16.
- **Decision:** `tts.spoken_numbers = "by_register"` says a reply's numbers, times, ISO dates and
  amounts in the caller's register (Saudi, MSA, English; `domain/text/arabic_numbers.py`,
  `spoken_words.py`), and `tts.spoken_key_combinations` says key combinations as their keys and
  spells capitals («كنترول شفت آر», "Control Shift R"). Both are off by default: they change what
  callers hear, so row 1.8's measurement keeps them first. Captions keep the text the guard read.
- **Consequences:** the Saudi forms are the agent's, unchecked by a native speaker (TD-058's
  15-minute check before the first demo). `TextCall` finds a read-back said in its shaped form.
- **Evidence:** the tests of the spoken forms (every timetable time, every day of a month and
  every number up to about 250,000 said with no digit) and of `TextCall`'s read-back forms.

## D-108 · A yes over the read-back books when the summary ends, for an agent that sets it · 2026-11-17 · Accepted (the owner's ruling of 2026-11-17, "Any yes books"; a library setting, off by default, which the flight app turns on: GP-18)

- **Context:** the owner's live test of 2026-11-17 (call 7tk, turns 6 to 16). A yes said over
  the flight agent's read-back, which runs 13 to 21 s, counted for nothing (D-081), so the caller
  had to say it again after the closing question; «خلاص، أكد الحجز» (OK, confirm the booking)
  stopped it as a stop word; and a bare yes over the closing question is asked again (the
  owner's ruling of 2026-11-10, "Yes, send it"). One booking took six read-backs.
- **Decision:** the owner chose "Any yes books": a yes said over the flight agent's read-back
  books once the summary has played to its end, a bare yes word («إيه», «نعم», «إي», "yes")
  included, unless the caller says anything else before it ends; and a yes over the closing
  question, after the summary played whole, books too, a bare one included. The lead's
  recommendation, not taken, was to hold only an explicit go-ahead ("book it", a yes beside a
  send word), since a bare «إيه» is often a listening sound. Built as
  `interruptions.yes_over_read_back` (off by default): in the `interruptions` group, because the
  read-back is a reply and a yes over it is speech over a reply that the session takes under
  `two_step`; not `turns` (the speech detector and Smart Turn), nor a `VoiceAgent` flag, so the
  flight app's settings turn it on as they turn on its guard settings. Under it:
  - a turn that is an overlap of the read-back's reply, begun after the summary's first audio
    and before its last clause played, the agent's voice going on over it, is the session's
    held yes (voice/session/held_yes.py): words the yes rule's lists read as a yes (a yes or a
    send word, the action's own among them, with only fillers beside them, and no no word,
    change marker or question mark) are held; for an agent that asks
    (`ask_on_unlisted_answers`), words the lists leave unplaced play on and go to the consent
    model under D-082's rails, its `yes` or `send` held, its `no` or `change` declining the
    read-back; never the agent's own lines heard back;
  - the held yes books once the summary has played in full with no other words begun since
    (no turn open or awaiting its words, no overlap undecided, no model's word awaited): the
    receipt is built as for any answer, now with the summary's first audio
    (`ReadBackReceipt.summary_began_at`), and `yes_rule.held` issues the confirmed action from
    the held turn's own words; the closing question is cut, or never said, and the `sending`
    line answers the held yes. A second yes, a filler or a listening sound keeps it held; any
    other words drop it; a new read-back, a decline, a repeat, the client's stop and the call's
    end leave it void;
  - over the closing question a bare yes (a yes among fillers) is a yes, and the model's plain
    `yes`, but to a send word alone; «خلاص» beside a yes or a send word, with only fillers
    else, plays on over the summary or the question and is a yes; each is asked again when the
    words are the agent's own lines heard back. «خلاص» alone still stops the read-back (D-081's
    amendment of 2026-11-11 stands).
- **Consequences:** for an agent that sets it, this amends invariant 1 (docs/SECURITY.md), D-081
  (a yes over the summary counts for nothing) and the ruling of 2026-11-10 (a bare yes over the
  closing question is asked again); with it off, every behaviour is as before, held by the
  characterization tests. A bare «إيه» meant only as a listening sound books, the risk the lead
  named. A single word such as «لا» over the summary goes on as before (fewer than `min_words`)
  and only drops a held yes; the caller answers after the question. The session's safety test
  found a yes said at the very instant of the summary's first audio, in the gap before it was an
  overlap, held; a held yes now needs an overlap of the read-back's reply begun after that
  audio, in the session and in the rule. Code moved out of the near-cap modules first
  (domain/yes_kinds.py, voice/session/read_back_heard.py, audible.py; `read_again` to
  read_back_moved.py; the send step to action_job.py).
- **Evidence:** the owner's ruling of 2026-11-17 (call 7tk of the live test); the tests
  `tests/t2_agentic_voice/domain/test_yes_rule_any_yes.py` and
  `tests/t2_agentic_voice/voice/session/test_read_back_held_yes.py` (each moment with the
  setting off and on, and the adversarial cases: before the summary played whole, a yes followed
  by other words, words before the read-back began, the agent's echo, a read-back replaced).

## D-110 · A card may name its slot on the page · 2026-11-17 · Accepted (the owner's ruling of 2026-11-17 on the flight page's three segments; a new optional field, which changes nothing for a page that ignores it)

- **Context:** the owner ruled on 2026-11-17 that the flight page shows three segments, the
  outbound flights (or a calendar of flights for a span of days), the return flights, and the
  review for confirmation, each filled in place. A card had no way to say which segment it
  fills, and the page could only guess from its title.
- **Decision:** `Card.slot`, an optional closed-shape name, lowercase letters and `_`, 1 to 20
  of them (`outbound`, `return`, `review`), none by default. `t2v/1`'s `card` carries it as
  `slot` (null when none), and the reference client hands it to the page, null for a session
  that sends none, and drops a card whose slot is of another shape, as it drops one whose
  source is not text. It is no text to show and carries no number, so the output guard does not
  read it. A page with segments puts the card in the one its slot names; any other page shows
  it where it shows every card.
- **Consequences:** no setting (GP-18: a new optional field that changes nothing for an app that
  ignores it). The protocol fixture (`tests/t2_agentic_voice/fixtures/t2v_protocol.json`) lists
  the field, and every card on the wire now holds `"slot": null` unless it names one. The
  flight app's tools set it, and its page fills its segments by it.
- **Evidence:** the protocol round trip, the client contract tests and the model's refusal of a
  slot of another shape (`test_protocol.py`, `test_browser_card_rows.py`,
  `test_browser_cards.py`, `tests/t2_agentic_voice/domain/test_cards.py`).

## D-111 · Plain speech: a clause that is not speech is never said, and the request is tried once more · 2026-11-17 · Accepted (the lead's ruling under GP-18; a library setting, off by default, which the flight app turns on)

- **Context:** the owner's English call of 2026-11-17 (91Sw) said nonsense twice. Turn 6 was
  markdown bold around a zero-width space, two more, an ellipsis, a dash, "The", "This" and a
  broken copy of the history's cut mark ("[cut ..."), and every filter passed it to
  text-to-speech; turn 2 joined two questions with a run of 21 dots, which the splitter did not
  cut, so the one-question limit (D-085) let both be said. gpt-oss writes such text now and
  then; the next request on the same context was clean.
- **Decision:** `guard.plain_speech` (off by default; agent/plain_speech.py), the diagnosis's
  option B: (1) a run of two or more dots or ellipses right after a sentence's mark is taken
  out, and one right after a word becomes one ellipsis, before the leak check and the splitter,
  a run at a piece's end held until the next character comes; (2) a whole clause is not speech
  when fewer than half of its characters, spaces aside, are letters, combining marks (the
  Arabic harakat among them) or digits, or when it holds "[", "{" or "<": from it on nothing
  more of that request is said and none of its tools runs, as a leak is dropped; (3) a request
  that said nothing so is sent once more, the same messages with a new first line and nothing
  of its text kept, while the turn has a request left (`llm.max_requests_per_turn`); a retry
  that is not speech too, or none left, ends the reply, and the session says the `error`
  notice when none of it was said; (4) the zero-width space, the word joiner, the byte order
  mark and the markdown marks, the asterisk and the backtick, are taken out of every clause
  before it is said.
- **Consequences:** a turn whose first request is junk costs one more request, about 2 s, and
  usage counts it as any request. A stage note glued to a real question is caught first by the
  leak check under `guard.drop_stage_notes`; alone, rule 2 drops that whole clause, the
  question with it. `agent/turn.py`'s request builder moved to `agent/turn_request.py` first, to
  stay under 300 lines.
- **Evidence:** the diagnosis of 2026-11-17. On the stored corpus (every heard text of runs
  f-dev-4, f-dev-5 and f-dev-6, and the owner's two replies: 818 replies, 3,011 clauses), the
  rules drop 13 clauses in 9 replies, all junk: f-dev-4's stage notes and its spoken tags and
  JSON dump (7 replies), f-dev-5's spoken `<action tool="book_trip"/>` (1), and the owner's
  turn 6 (4 clauses); none in f-dev-6. The dot rule changes what the question limit lets be
  said in exactly 2 replies, f-dev-5's f15 (five questions joined by dot runs) and the owner's
  turn 2. The tests in `tests/t2_agentic_voice/agent/test_plain_speech.py`.

## D-114 · ElevenLabs v4 Turbo is the default text-to-speech, in the owner's voice; Groq's Orpheus the fallback; Telnyx beside them · 2026-11-17 · Accepted (the owner's pick by ear and their ruling of 2026-11-17, "Make elelevnlabs as the default and groq as the fallback")

- **Context:** the owner wants a better voice for the flight agent's Saad than Groq's Orpheus
  (abdullah, troy), and will pick it by ear, Saudi speech first; they named ElevenLabs ("V4,
  maybe turbo") and Telnyx's Bayan. The key reads ElevenLabs' `eleven_v4`, `eleven_v4_turbo`,
  `eleven_v3`, `eleven_v3_conversational`, `eleven_multilingual_v2` and Flash v2.5, all with
  Arabic; Bayan is Telnyx's own model of 13 Arabic dialects and English, 113 speakers, the Saudi
  men among them Fahd, Jasem and Tamer (its voices list, 2026-11-17). Both stream: ElevenLabs'
  `/stream` answers raw PCM as it is made (v4 and v4 Turbo too, probed), Telnyx's WebSocket
  base64 PCM frames; Telnyx's REST answer arrives whole.
- **Decision:** `tts.provider` takes `elevenlabs` (the default, by the owner's ruling below),
  `groq` (the fallback) or `telnyx`, each on its key group's key (a missing key refused at the
  build, naming it and the Groq fallback).
  `tts.languages` holds the chosen provider's own models and voices (core/settings/
  tts_voices.py); unset, it is that provider's default map (ElevenLabs `eleven_v4_turbo` in the
  library voice Saud for Arabic and the premade Brian for English, until the owner's pick below;
  Telnyx Bayan Fahd and Michael), so one setting switches the voice, and the settings refuse a voice of another
  provider. The caches, the usage counts and the doctor go on reading `tts.languages`, so a
  take is keyed by the voice that made it whichever provider. `ElevenLabsTTS`
  (adapters/elevenlabs_tts.py) streams one HTTPS request a clause at 24 kHz with the clause's
  `language_code`; `TelnyxTTS` (adapters/telnyx_tts.py) one WebSocket a clause at Bayan's own
  16 kHz; both read the PCM through the Groq adapter's WAV reader (adapters/pcm_takes.py), so
  the silence trim and the cut-short flag are the same. Telnyx's occasional error frame is a
  retryable server error.
- **Consequences:** every developer needs the ElevenLabs key for speech as for Scribe (D-105),
  or sets `tts.provider = "groq"`, as the quickstart does; `GroqTTS` refuses another provider's
  voices, and the Ole5 eval commands build the text-to-speech the settings name
  (`Providers.text_to_speech`). Measured from
  this laptop on 2026-11-17 (20 requests each, a clause a request): the first audio of a short
  Saudi clause at p50 0.18 s on Groq, 0.21 s on ElevenLabs v4 Turbo, 0.85 s on v4, and 1.46 s
  on Telnyx Bayan, whose new WebSocket per clause costs about 0.65 s of it: one socket kept open
  for the call, each clause flushed on it, gave 0.60 s (not built; a pool of open sockets per
  voice, closed at Telnyx's 20 s idle limit, would be). An
  ElevenLabs key may carry its own credit cap: the owner's stopped at 10,000 and, raised, at
  20,000 during the measurement, and with it every ElevenLabs request, Scribe's included.
  ElevenLabs' own streaming socket for v4 Turbo (its Text-to-Dialogue socket, the line's
  clauses sent into one turn) gave 0.17 s and kept the voice's flow across clauses; using it, or
  Telnyx's kept socket, needs a session per call in the port, a later proposal. No per-call switch on
  the dev console yet: the greeting cache and the clause cache are built for the runtime's one
  text-to-speech, so a voice is heard live by starting the server with `T2V_TTS__PROVIDER` set.
- **The owner's pick:** having heard the sheet, the owner ruled on 2026-11-17: "I Think
  Elevenlabs v4 turbo takes the cake, although i didn't like the Saud sound", naming two voices
  of their own search, `nhJWWCFdNdusuVUT3x19` first and `rpGHcNQJvO8dFNNFNj1v`, to be the final
  choice once they matched Saud's price and latency. Both were billed the same credits as Saud
  for the same read-backs and timed as Saud was (`tts_pick.md`). So ElevenLabs' default map is
  `eleven_v4_turbo` in `nhJWWCFdNdusuVUT3x19` for all three presets, one voice for Saad. Asked
  then whether the library's default should stay Groq, the owner ruled: "Make elelevnlabs as the
  default and groq as the fallback". So `tts.provider` defaults to `elevenlabs`, and
  `T2V_TTS__PROVIDER=groq` brings Orpheus back.
- **Evidence:** the listening sheet, its runs and `tts_pick.md` in the session notes of
  2026-11-17; `tests/t2_agentic_voice/adapters/test_elevenlabs_tts.py`, `test_telnyx_tts.py`,
  `tests/t2_agentic_voice/core/test_tts_providers.py`, `tests/flight_voice/test_settings.py`.
