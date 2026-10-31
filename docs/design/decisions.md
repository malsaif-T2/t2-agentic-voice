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

## D-002 · Technology stack · 2026-10-28 · Proposed

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

## D-003 · Layered architecture, enforced from one config · 2026-10-28 · Proposed

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

## D-007 · SECURITY.md: threat model and invariants · 2026-10-28 · Proposed

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

## D-011 · evaluation.md adopted: a golden set from the owner's recordings, and simulated calls · 2026-10-28 · Proposed

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
