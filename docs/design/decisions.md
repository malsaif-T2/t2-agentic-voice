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

## D-004 · Groq is the only provider for now, and each can be swapped later · 2026-10-28 · Accepted

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

## D-018 · The owner's answers to the package design's open questions · 2026-11-01 · Accepted

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
  the environment's, and several bounds, all written below.
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
    `server.turn_secret_file`). Every failure is a `ConfigurationError` with a FIX line, and
    never holds the value it refused (GP-19). A command writes the settings reference and
    `.env.example` from the model, each with a test that fails when it is stale.
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
      join key or TURN secret too short is named with the rest; a `.env` that is not UTF-8
      text is refused with "save it as UTF-8 text", showing none of its bytes; an environment
      check names its one setting. A group built on its own (`JoinSettings(...)`) raises
      pydantic's `ValidationError`, its input hidden. Set aside: pydantic's `ValidationError`
      for settings built in code, which a team catching `ConfigurationError` for its FIX line
      would miss.
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
      or voice reaches a call that no check saw.
    - The values nobody gave, the agent's: `tts.timeout_s` 6, as `stt.timeout_s`; the limits
      in seconds as numbers; a voice name matching `^[a-z][a-z0-9_-]{0,31}$`;
      `server.ice_servers` as `stun:`, `turn:` or `turns:` URLs with no credentials; each of
      `server.allowed_origins` a scheme, a host and a port only, in the form a browser's
      `Origin` header takes (the scheme and the host in lowercase, the host in ASCII, its
      `xn--` form, no `:443` for https or `:80` for http), any other form refused with a FIX
      that states the rule and never repeats the value; `server.turn_ttl_s` 3600, refused above
      86400 (plan 003's criterion); `join.max_clock_skew_s` at most 60, since a token verifies
      until its expiry plus the allowance (invariant 7); and each of
      `server.forwarded_allow_ips` an address or a network in its network form (`10.0.0.0/24`;
      `10.0.0.1/24`, which uvicorn would never match, is refused with a FIX naming that form),
      no wider than /8 for IPv4 or /32 for IPv6, and within the IPv6 ranges that carry IPv4
      addresses (`::ffff:0:0/96`, `64:ff9b::/96`) no wider than /104: a wider entry trusts
      nearly every peer's `X-Forwarded-For`, as `*` does, which is refused too.
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
  `test_settings_errors.py`, `test_settings_checks.py`, `test_settings_secrets.py` and
  `test_settings_ref.py`, and `tests/harness/test_isolation.py`.

## D-029 · Serving and identity: the sidecar and the mount, one process per `var_dir`, signed join tokens, the offer secret · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 4.5, 5.2, 5.5, 6.5, 7.4 and 11; one bullet Proposed)

- **Context:** the design gives a team two ways to serve calls, the sidecar by default and the
  mount for one-worker apps (its 4.5; D-018, question 22); one process per `var_dir`
  (question 5); a caller's identity and consent from a signed, single-use join token (its 6.5;
  question 18); and the call's set-up over HTTP (its 5.5). Its 16.3 lists this entry, with
  Ole5's identity answer (its open question 19), which the owner has not given yet. Plan 003's
  Block 0 laid down the signatures, the identity port and the HTTP bodies; its Tracks C and F
  build them. The fixes after Block 0's review (2026-11-03) gave the HTTP routes their one error
  body and their byte caps, written below.
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
    secret (random, for this call only), the ICE servers (with per-call TURN credentials when
    configured) and the protocol version. `POST /offer` and `PATCH /offer` both need the
    call's offer secret, which stops working when the call ends or ICE completes; a second
    offer gets 409; no client's `pc_id` reaches Pipecat. The call ID is no credential. The
    offer secret is never logged, traced or put in an event, and goes only to the browser that
    joined.
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
      with `aclose()` (D-036). Its `expires_at` is the last instant the verifier could still
      accept the token, its `exp` plus `join.max_clock_skew_s`, never `exp` alone, so a store
      that prunes at it never lets a token start a second call within the allowance (Track C's
      test replays a token after the store pruned it at its `exp`). `SignedJoinTokens` refuses
      at construction a `ttl_s` over 120 or a `max_clock_skew_s` over 60, as the settings do,
      since it takes both directly. `DevIdentity` refuses any `env` but dev before it reads
      the client's address, and always returns `Consent(version=None, record_audio=False)`.
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
      never in a URL, which logs and traces keep. A `PATCH` with the call's own secret after
      ICE completed or after the call ended gets a quiet 409 (`ice_completed`, `call_ended`),
      logged at DEBUG with no value, which the client ignores once connected. `voice` forgets a
      call once it has ended and its peer has closed, and `api` keeps its own record of the
      calls it joined, so a call `voice` has forgotten still gets `call_ended`; set aside:
      `voice` keeping ended calls for a fixed lifetime, a value nobody gave (GP-16). `voice`
      keeps Pipecat's `pc_id` behind the call ID and never passes a client's.
    - Each `t2v/1` route reads its own body, never past its route's cap in bytes (twice the
      longest values its body holds, since JSON writes a quote or a line break in two bytes,
      plus 4 KiB; `BODIES` in `api/protocol.py`): a `Content-Length` over the cap is refused
      before a byte is read, and a body that streams past it is refused at the cap, each 413
      `too_large`, so no body is buffered whole on the event loop that paces every call's
      audio. It parses the body with the model's `model_validate_json`, strictly, and answers a
      refusal with `refusal()`: 400 `invalid_request`, naming pydantic's error types only. No
      route declares a model as a FastAPI body parameter, since FastAPI's own 422 sends the
      error's `errors()` back, with the token, the offer secret or a candidate's address in it,
      and in the mount the app's handler would answer it.
    - Every refusal and failure, a crash included, answers one `ErrorBody` (`code`, `message`,
      `notice`, `reference`): a code from a closed list of ten (`invalid_request`, `too_large`,
      `protocol_mismatch`, `join_rejected`, `forbidden`, `already_offered`, `ice_completed`,
      `call_ended`, `not_started`, `internal_error`), a message safe to show that holds no value
      the request sent, a `notice` with `protocol_mismatch` alone (the design's 5.4), and a
      random reference the router logs with the refusal (GP-19). The statuses: 400
      (`invalid_request`, and on `/join` `protocol_mismatch`); 403 (`join_rejected` on
      `/join`; `forbidden` on `/offer` for a secret that is missing, wrong or no longer
      working); 409 (`already_offered` on `POST /offer`; the quiet `ice_completed` and
      `call_ended` on `PATCH`); and on every route 413, 500 `internal_error` and 503
      `not_started`. A success is 200, 200 and 204 (`PATCH` answers no body). No 404: the
      secret is checked first, so an unknown call gets 403, and no answer shows whether a call
      exists; 400, not 422, since the router parses, not FastAPI. `/join` compares the client's
      protocol version before it verifies the token, so a mismatch spends no token. A
      response's secrets (the offer secret, a TURN password) are revealed only as it is
      serialized to JSON, as it is sent, never in a python-mode dump or a repr. Set aside:
      FastAPI's `{"detail": ...}`, which carries no code or reference; a nested
      `{"error": {...}}`.
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
      called once per call, since each of Pipecat's analyzers keeps one stream's state, and
      typed with Pipecat's classes under `TYPE_CHECKING` only, so no Pipecat loads at import.
      Track F's tests give `FakeCalls`, and step 16's test a fake speech detector.
    - In M2 the Ole5 app mounts the router in its own FastAPI app, beside its token route
      (behind the owner's access code: plan 003's Q4) and its widget's files, rather than run
      the sidecar, which is its shape once its website mints the tokens (the design's open
      question 19); `examples/minimal` uses `serve()`.
- **Consequences:** a team that runs several workers or replicas runs the sidecar, and a second
  process on one `var_dir` fails at its start rather than share single-use tokens. A team's
  website mints tokens with any JWT library from the documented claims (`serving.md`), and a
  browser client reads one error body on every route. Until the design's open question 19 is
  answered, Ole5's callers get their tokens from the app's own access-code route. The media path
  (UDP, TURN or another transport) is decided by plan 003's network test, in an entry of its
  own.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01; D-018, questions 5, 18 and 22; for
  plan 003's Q4, the owner's answer of 2026-11-02, "Yes go with the recommended." (plan 003,
  "The owner's decisions"). The spike on this machine (plan 003's appendix, step 5): on the
  proactor event loop, 2 or 3 of 16 call closes hung, against 0 of 16 on a selector loop. The
  tests of the bodies and the error body: `tests/t2_agentic_voice/api/test_protocol.py` and
  `tests/t2_agentic_voice/test_protocol_list.py`, against the `t2v/1` fixture.

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
    raises, loses no value, and cannot forge a console line or add a traceback (set aside:
    refusing the name, and dropping it). `get_logger` returns the library's own
    `StructuredLogger` (`debug`, `info`, `warning`, `error`, each taking an event and its
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
  `tests/t2_agentic_voice/core/test_logging.py` and `test_logging_import.py`; plan 003's Track E
  adds invariant 8's tests in a child process.

## D-032 · ARCH-BAN, the owners M2 adds, and the facades `identity`, `server`, `stores` and `events` · 2026-11-02 · Accepted (the owner, 2026-11-01, as the design's 5.1, 5.3, 12.2 and 12.4; one bullet Proposed)

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
      `TurnEnd`, `TurnTiming` and `EchoTiming`; at the package root, beside `VoiceSettings`
      and `get_logger`, the classes of `VoiceSettings`'s twelve groups (`GroqSettings`,
      `ServerSettings` and the rest), `TtsVoice` (what `tts.languages` holds) and
      `StructuredLogger` (what `get_logger`
      returns), so a team builds a typed `VoiceSettings(env=..., server=ServerSettings(...))`
      from one module; and in `languages`, `Pronunciations` (`VoiceAgent.pronounce`'s type,
      D-033) with `pronounce` and `split_clauses`, the pronunciation map and the clause
      splitter plan 003's criterion asks of that facade. `speak_digits` is held back, as no
      public signature names it and no app imports it in M2. Set aside: the 5.1 names alone,
      which would leave public signatures typed by names an app cannot import; spreading the
      settings groups across the facades by topic, which leaves half of them with none; and a
      `settings` facade, a change to 5.1 for the owner.
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

## D-033 · The echo's shape: an agent with a name and its languages, `session.mode`, a fixed frame · 2026-11-02 · Accepted (the owner, 2026-11-02, plan 003, Q3, and the design's 4.3 for the pronunciation map; one bullet Proposed)

- **Context:** M2 has no talker: the voice session says back what it heard (the design's 16.1:
  "the voice session in echo mode", and `examples/minimal` "as an echo use case"). The design
  gives neither a public form, which is a design choice, so plan 003 asked the owner (its Q3):
  the agent's declaration with only a name and its languages and a setting for the session's
  mode, a runtime argument that M4 would have to deprecate, or an internal stand-in; and
  whether a fixed frame comes before the heard words. The fixes after the review of plan 003's
  Block 0 (2026-11-03) gave the declaration what plan 003's tracks need of it: the
  pronunciation map, each preset's notice texts, and its errors, written below.
- **Decision** (the owner's answer to Q3, (a) and (i), and the design's 4.3):
  - `VoiceAgent(name, languages=[Language.saudi_arabic(greeting=...), ...])`, built in M2 with
    these fields and the pronunciation map below, and the setting `session.mode`, with `echo`
    its only value in M2. M4 adds the talker, and the talker's fields arrive as optional
    arguments, so an echo agent stays a team's first audio check.
  - `VoiceAgent(pronounce=...)`, the design's 4.3 pronunciation map: each written form, as a
    text holds it, to how each language says it, keyed `ar` or `en`
    (`pronounce={"LT-": {"en": "L T"}}`); the design's 16.1 puts pronunciation in M2.
  - Each reply starts with a fixed frame in the turn's language, «سمعتك تقول: …» or
    "I heard: …", then the heard words. The frame says the words are the caller's, so the echo
    never sounds like the agent answering or claiming an action (invariant 2). It is a cached
    phrase (the design's 10.4), so it plays as soon as the turn's transcript is in, while
    Orpheus synthesizes the heard words. M2's fixed phrases are in Saudi dialect (plan 003's
    Q5).
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
      kinds they name, and a `Language` built without its preset gives all three. A greeting, a
      notice and a spoken form hold a character, and no line break or control character.
    - The pronunciation map's inner keys are checked at run time to be `ar` or `en` (a
      pronunciation names a language by its primary code, which both Arabic presets share),
      not typed as a `Literal`, so an app's map built in a plain `dict` type-checks; its type is
      the `languages` facade's `Pronunciations`, a `type` alias, and the map is read-only.
    - Every failure to build a `Language` or a `VoiceAgent`, `model_validate` included, is a
      `ConfigurationError` with a FIX line (the design's 4.2) that names its first failing
      field (its details `{"field": ...}`, None for an input that is no mapping at all) and
      never the value; only assigning to a built one raises pydantic's `ValidationError`, as
      for every frozen model. Set aside: the settings' collected shape (D-028), since a
      declaration is code the team reruns at once.
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
      notice has played or failed. Each goes out as `t2v/1`'s `notice`, whose text the client
      shows, and is spoken from the phrase cache as the next reply (D-037), so it plays even
      when text-to-speech is rate-limited (the design's 10.4). `busy` is never spoken: admission
      control answers it at join, before a call has audio (the design's 10.5). Set aside:
      notices as text only, which would leave the cached notices unused.
    - Text built from heard words never reaches the phrase cache, which holds only what
      `fixed_phrases(agent)` declares at the runtime's start: each language's greeting, echo
      frame and its `error` and `ended` notices (not `busy`, one request per language that no
      call plays), so the cache keeps no call content (invariant 8). A fixed phrase longer than
      the text-to-speech's `max_chars` is spoken whole: the cache cuts it with the clause
      splitter, which cuts inside a word only a word longer than `max_chars`, at `max_chars`,
      and joins the takes into one chunk, which the session plays as one clause; so the runtime
      refuses no greeting or notice at its start. Set aside: refusing such a phrase at start,
      and the session splitting fixed phrases, under which every greeting with a comma would
      cost two requests. Caching talker clauses that repeat exactly (the design's 10.4) is M4's
      to decide.
- **Consequences:** `examples/minimal` is an echo agent (`make_runtime()`) whose tests need no
  key and no network, and may catch `ConfigurationError` around its declaration. M4 adds the
  talker to the same declaration, with no deprecation. The call's language picks Whisper's
  language (`stt.live_language`, D-028) and the voice.
- **Evidence:** the owner, 2026-11-02, to plan 003's Q1 to Q6, each put with the agent's
  recommendation, (a) and (i) for Q3: "Yes go with the recommended." (plan 003, "The owner's
  decisions"); for the design's 4.3, as for D-019 (plan 002, Q3), 2026-11-01. The tests:
  `tests/t2_agentic_voice/domain/test_declaration.py`.

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
  empty, failed or unusable one included, unless the call ends first: then it drops the turn's
  held audio and cancels a request in flight (D-037). Smart Turn's stop strategy is given
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
  `adapters` copy, subclass or rebuild a `SignedConsent`; its fixes are written below.
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
      token's `jti` until its expiry plus that allowance (D-028, D-029); and the offer secret
      never in a URL (D-029).
    - Only a `SignedConsent` counts as the token's consent: a `@final` subclass of `Consent` in
      `core/identity.py`, built in `adapters` alone, and there by `SignedJoinTokens` alone, from
      a token whose signature it verified, as
      `SignedConsent.model_validate(claim, context=CONSENT_SEAL)`. The seal is a bare object
      compared by identity (a copy of it is no seal), given as the validation's context, which
      the class checks after every validation (`model_post_init`). Every other way to build
      one raises TypeError: its constructor, a validation without the seal (`model_validate`,
      `model_validate_json`, a `TypeAdapter`, a model that holds one), `model_construct`,
      `model_copy` with an update (pydantic validates neither, so even the seal's holder builds
      a changed consent anew), and a subclass. A copy with no change is the same consent, and
      allowed. Every other layer asks
      `allows_recording(consent)`, true only for a `SignedConsent` (its exact type) that says
      `record_audio`, and never names the class. A consent that `DevIdentity` or a team's own
      verifier returns never turns recording on, and a `SignedConsent` never equals a plain
      `Consent` with the same choices.
    - `[[restricted]]` keeps it statically, in two tables (ARCH-CONSTRUCT): `SignedConsent`'s
      `classes` row reports a call that builds one outside `adapters`; and a new kind of table,
      which lists `names` instead of `classes`, reports any reference to `CONSENT_SEAL` outside
      `adapters` (an import under any alias, an attribute, a name read, a string that is the
      name, which catches `getattr`), the module that binds the name aside. Both hold a layer:
      that only `SignedJoinTokens` in `adapters` gives the seal is a review. Neither guard sees
      a seal's name computed at run time, a direct write to a frozen model's fields, or a
      crafted pickle; review does (SECURITY.md, invariant 8). This is the `[[restricted]]`
      change `harness.toml` asks a decision for; ARCHITECTURE.md's conventions and enforcement
      list name it.
    - Set aside: a private flag on `Consent`, which any layer could set and the check cannot
      see; a constructor that takes the seal, under which pydantic's `model_validate` calls
      `__init__` again without it; the seal as a key of the data, which would be a field held
      on every consent; and `core` among the seal's layers, which would let any `core` module
      validate a `SignedConsent`.
- **Consequences:** D-007's heading points here. The recorder writes audio only when both
  conditions hold, asking `allows_recording`, and never copies or rebuilds a consent; no client
  message can set either condition. What stays the app's is the design's 8.1: minting tokens
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
  headroom.
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
  - `Transcript` gains `remaining_requests` and `remaining_tokens`, optional and None by
    default, the headroom the provider reported with the answer, so the call's report can keep
    Whisper's as it keeps Orpheus's. `GroqSTT` reads none yet: the request hook drops the SDK's
    raw-response marker, and without it the SDK hands a JSON answer back parsed, with no
    headers; plan 003's Track B, which reads the same headers for `GroqTTS`, is named to fill
    them. An optional field breaks no caller of a stable port (the design's 5.4). Set aside:
    fields on the session's `Transcribed`, which already carries the `Transcript`; and the
    report's criterion narrowed to the text-to-speech models.
- **Consequences:** an adapter a team writes for these ports implements `aclose()`; no team has
  one yet, since no tag has been installed. The design's 6.1 does not show these fields, nor
  its 6.5 the store's `aclose()`.
- **Evidence:** the types builder's choices in plan 003's decision log (step 10, 2026-11-02),
  and the review's finding on Whisper's headroom (2026-11-03). The tests:
  `tests/t2_agentic_voice/domain/test_ports.py`, `test_text_to_speech_port.py` and
  `test_identity_port.py`.

## D-037 · Agent speech is keyed on replies, and the drop rule covers every reply, the greeting included · 2026-11-03 · Proposed (the agent's, plan 003's Block 0 after its review; beyond the design's 5.5 and 6.6)

- **Context:** the voice session greets the caller once connected, in the greeting the call's
  language declares, before any turn of the caller's exists. Block 0 keyed every clause the
  agent speaks, and its events, captions and playback reports, on the caller's turn number,
  which the speech-to-text bridge counts, so the greeting and the echo of turn 0 would have
  shared a key. The drop rule (D-033) named the echo alone: read so, the greeting leaking past
  echo cancellation on laptop speakers would be said back; read as any speech, every file-fed
  call's clip, fed while the greeting played, would be dropped. And a turn still open when the
  call ends could not get both its transcript and no event after the last command. The review
  of plan 003's Block 0 found the three (2026-11-03), and the integrator ruled on each.
- **Decision:**
  - **Replies.** The caller speaks in turns and the agent in replies, numbered apart: the
    speech-to-text bridge numbers the caller's turns from 0 (`TurnId`), and the session the
    agent's replies from 0 (`ReplyId`, in `voice/protocol.py` beside `ClauseIndex`): the
    greeting is reply 0, and each echo and each spoken notice the next. `Speak` keys each
    clause on its reply and its index there, and names the caller's turn the reply answers,
    None for the greeting or a notice; `StopSpeaking(reply_id)` drops that reply and any before
    it; `ClauseQueued`, `ClausePlayed` and `ClauseFailed` carry the reply and the clause alone,
    since the session knows which turn a reply answers. On `t2v/1`, a caller's caption names
    its turn only, an agent's its reply and clause, with the turn it answers when there is one,
    and a `playback` report a reply and a clause. `core`'s `AgentSpeechEnded` and `Interrupted`
    take an optional `turn_id`, None for the greeting or a notice. Set aside: one numbering for
    turns and replies, under which the greeting and turn 0's echo share a key.
  - **The drop rule covers every reply.** A turn whose speech began (the speech detector's
    onset) while any reply played, the greeting included, or within 300 ms after a reply's last
    clause played, is not answered; it is still closed, transcribed and kept on the timeline.
    The 300 ms count from the reply's last `ClausePlayed`, when its audio left the output
    transport, which a WebRTC call and a file-fed one both know, not from the browser's
    playback report, which comes a jitter buffer later and never in a file-fed call.
  - **The file-fed call** feeds silence until the greeting has played (its last `ClausePlayed`
    or `ClauseFailed`), then the clip's lead (`lead_s`; the registration's 1 s), so the clip
    never overlaps the greeting. The greeting is a cached phrase like the frame, synthesized
    once, and its request counts in run T's budget. Each command it records carries when it
    reached `Commands.run`, so "the echo's text ready" is the time of the heard words' `Speak`.
    Set aside: an option for a file-fed call with no greeting, which would make the measured
    call differ from a live one.
  - **A turn open when the call ends.** At an `Ending` or a `TransportFailure`, the Pipecat
    side drops an open turn's held audio and sends no request for it, cancels a request in
    flight, and hands the session no `TurnClosed` or `Transcribed` of it; the call's report
    keeps the turn as unfinished (`TurnRecord.unfinished`, a field of the provisional
    `CallReport`) and does not count the cancelled request. The session's last command is
    `HangUp`, after which no event comes. Set aside: sending the turn to Whisper after the end,
    which bills a request and hands an event after `HangUp`.
- **Consequences:** plan 003's Tracks D, E and G key the agent's speech on its reply and clause
  (the session, the speech bridges, the widget's playback reports), and Track H counts the
  lead from after the greeting. `voice/session/io.py` says the rules, and the `t2v/1` fixture
  pins the fields. The design's 5.5 (a caption's turn ID) and 6.6 (every event's `turn_id`)
  do not say so.
- **Evidence:** the review of plan 003's Block 0 (2026-11-03). The tests:
  `tests/t2_agentic_voice/test_session_fakes.py` (the greeting with a turn that opens while it
  plays, and a call that ends with a turn open),
  `tests/t2_agentic_voice/voice/session/test_io.py` and
  `tests/t2_agentic_voice/test_protocol_list.py`.

## D-038 · A call's language is fixed at join · 2026-11-03 · Proposed (the agent's, plan 003's Block 0 after its review; beyond the design's 5.5)

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
  and never applied on the path a call takes.
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
      1, every size bounded, and a key held twice refused. The whole message is at most 1024
      bytes of UTF-8, on both paths: text measured as it came, and the object Pipecat's Small
      WebRTC parsed before handing it on, the path a call takes, written back as compact JSON
      and measured. A refusal is an `InvalidRequestError` whose details name only its kinds
      (`too_large`, `json_invalid`, `duplicate_key`, or pydantic's error types), never the
      client's text. Set aside: having `voice` read each message's raw text before Pipecat
      parses it; the object is what Pipecat's `on_app_message` hands on.
- **Consequences:** the session and the widget build against one list, which the fixture
  `tests/t2_agentic_voice/fixtures/t2v_protocol.json` pins, and a change to `t2v/1` changes it
  in the same commit. The design's 5.5 lists neither `playback` nor a caption's reply.
- **Evidence:** as for D-019 (plan 002, Q3), 2026-11-01. The tests:
  `tests/t2_agentic_voice/voice/test_protocol.py` and
  `tests/t2_agentic_voice/test_protocol_list.py`.
