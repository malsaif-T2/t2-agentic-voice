# T2 Agentic Voice: package design

**Status: Accepted as amended.** The agent drafted this on 2026-10-31 for the owner and revised it the same day after two reviews. On 2026-11-01 the owner answered its open questions (section 17, D-018), the sections those answers touch were changed to match, and the owner approved the design as amended (D-017). Each part is built with its milestone (section 16). Built so far, by M1 (plan 002): the five facades (`ports`, `groq`, `languages`, `evals`, `tracing`, D-021), the speech-to-text port and its Groq adapter, the `groq`, `stt` and `tracing` settings groups, tracing, the scorers (D-022) and the checks ARCH-FACADE and ARCH-WORDS (D-020); by plan 004, the base error's name, `T2VoiceError` (D-026); and by plan 003's Block 0, the settings (section 7), the library's logging (10.2), the ports, shared types and `t2v/1` models M2 builds on, and four more facades (`identity`, `server`, `stores` and `events`, D-032). Where plan 004's read found that what was built differs from a section, a note in italics there says so (5.1, 6.1, 7.6, 9.7 and 10.2). Where it would change a recorded decision or an architecture rule, it says so and names the decision entry to write (section 16.3). Where the agent disagrees with a decision, it says so in section 17 and does not change the decision.

**Since the draft.** The design was written from commit `a0ca586`. The same day, plan 001 built its first step in a simpler form: one uv workspace with the library, the Ole5 app and `examples/minimal`; one `harness.toml` for the repository, with `[[apps]]` and the rule ARCH-PUBLIC (an app imports the library only through its public modules); and tests in one `tests/` folder at the root. Sections 12, 14 and 16 were aligned with that layout. The owner's decisions taken so far are D-012 to D-016, and D-018 for the answers to section 17; this design as a whole is D-017, accepted on 2026-11-01.

**Inputs:**
- The owner's decisions of 2026-10-31: approach 3; one uv workspace; Python library only as the v1 usage mode for teammates; the thinker off by default; Groq only, behind ports; the hosting limits.
- The repository at commit `a0ca586`: ARCHITECTURE.md, docs/SECURITY.md, D-001 to D-011, the roadmap (M0–M7), docs/design/evaluation.md, harness.toml.
- Three teammate personas, written by the agent (section 2).
- The open-source survey and the API-precedents study of 2026-10-31.
- The research of 2026-10-28.
- Two reviews of the first draft (developer experience; architecture and safety), 2026-10-31.
- The agent's own checks on 2026-10-31: the PyPI metadata and wheel contents of `pipecat-ai` 1.15.0, the FastAPI 0.162.0 wheel, the `groq` SDK 1.7.0 metadata, and Groq's "Your Data", rate-limits and Orpheus English model pages.

**How facts are marked:**
- **Checked** marks a fact that the agent or a reviewer read at its source on 2026-10-31.
- **Verify** marks a fact that nobody has confirmed yet. The plan that first depends on it confirms it before relying on it.
- Everything else about other projects comes from the survey and the API study, and says so.

**Words used in this document:**
- *Use case*: what a team declares, namely instructions, languages, tools and actions.
- *Talker*: the fast model that speaks. It asks for tools and actions; it never acts.
- *Tool*: a read-only capability the talker may call.
- *Action*: a side effect, such as a ticket or a leave request. The library runs it only after the caller's consent, which the library hears and checks.
- *Thinker*: the optional slow reasoner. It is off by default.
- *Runtime*: the library object that runs calls for one use case.
- *Sidecar*: a separate one-worker process that runs the runtime next to a team's existing service.
- *Teammate*: a T2 developer who installs the library in their own project.

**When each part is built.** Every feature in this design has one of three labels:
- **Ole5 Mn**: an Ole5 milestone forces it, so it is built in that milestone.
- **Core proof**: `examples/minimal` needs it to prove the core works without Ole5 code.
- **On request**: designed now, so that nothing in v1 blocks it, and built only when a real teammate asks for it.

---

## 1. Purpose and scope

### 1.1 What T2 Agentic Voice is

T2 Agentic Voice is a Python library for speech-first voice agents that run inside a team's own Python backend. Its distribution is `t2-agentic-voice`, its import is `t2_agentic_voice`, and its command is `t2v`. The team declares a use case, and the library runs every call:
- WebRTC audio from the browser;
- speech detection and end of turn;
- interruptions;
- speech-to-text, the talker and text-to-speech;
- the rules that decide whether anything is done and what may be said about it.

This is the "approach 3" design the manager approved: a dedicated voice agent, not a voice shell around a chat agent and not dictation buttons. It carries Ole5's two shaping rules (ARCHITECTURE.md) to every use case:
- **Only the backend acts.** The talker asks. The library runs the action after the caller's heard consent, records it, and words the outcome from the real result.
- **Every outside service is behind a port.** A provider (Groq today, D-004) is swapped by a setting that picks a built-in adapter, or by passing another adapter object in code, never by forking.

*The next phase (D-050):* after the Ole5 Voice Agent, a second, agent-led mode lets a team's existing LangChain or LangGraph agent run as is behind the same voice layer, and its writes run only after the caller's heard yes ([agent-led-mode.md](agent-led-mode.md)). The native mode this document describes does not change.

The first user is the Ole5 Voice Agent, rebuilt as `apps/ole5-voice-agent` on the public API only, exactly as a teammate would build it. `examples/minimal` is the quickstart, and it proves the core works without Ole5 code.

### 1.2 v1 scope

"v1" means the library as it stands when the Ole5 app passes M7 (section 16). It holds what Ole5 forces and what `examples/minimal` needs (the labels **Ole5 Mn** and **Core proof**). Features labelled **On request** are designed here but are not in v1 unless a teammate asks first. Versions before 1.0 are `0.x`.

- **Usage mode: a Python library only** (the owner's decision). Teammates write Python inside their own service. A call also needs a browser side, and Ole5's own widget needs one. So v1 also ships a small reference browser client, a dev page and a versioned wire protocol (open question 1). This is not the drop-in widget, which comes later.
- **The real-time call**, inside one backend process:
  - Pipecat's SmallWebRTC transport, Silero VAD and Smart Turn v3.2;
  - the two-step interruption and one cancel scope per reply (D-060), owned by the library's own voice session;
  - speech out clause by clause;
  - a history that holds only what the caller heard.
- **The talker, read tools and confirmed actions.** The yes rule, the output guard, the outbox and the per-call record work for any action, not only tickets.
- **Saudi Arabic, MSA and English** in one call, with the reply language chosen per turn.
- **Public ports with Groq adapters:** Whisper large-v3 and turbo; `openai/gpt-oss-120b` and other chat models; Orpheus English and Arabic Saudi, each its own model.
- **Serving:** a sidecar process (`serve()`), or a router mounted in an app that runs one worker; single-use join tokens; a per-call offer secret; TURN credentials minted per call only if Ole5's network test, in the deployment's own plan (the roadmap's M6), needs TURN.
- **A testing kit**, offline by default, with live runs opt-in, and **evaluation helper functions**. Ole5's golden-set runner stays in the app.
- **Observability:** OpenTelemetry traces (Phoenix by default) on the teammate's own provider, standard-library logging, usage counts in traces and in each call's report, health and readiness, and limits.
- **Documentation for teammates**, starting with the PROVIDES / REQUIRES page.

### 1.3 Non-goals for v1

| Not in v1 | Where it goes |
| --- | --- |
| A drop-in web component for teammates, a config-only server, plugging in an agent over HTTP | Later usage modes (the owner's decision) |
| The thinker | Designed now (section 6.2) so that nothing blocks it; built after M7 (open question 16) |
| Phone calls (SIP), mobile apps | Later (roadmap, "Planned later") |
| Speech-to-speech models | Later; the port shapes leave room |
| Flows or slot filling (`stages`), multi-agent handoffs | Later, with a second use case that needs them |
| Typed chat inside a call | Later. Typed text is not heard words, so it changes the consent rule and needs a decision first (D-009 calls it a bonus) |
| A knowledge base or ticket system inside the library | Teams bring their own. The library gives a `KnowledgeBase` protocol and a helper tool (section 6.3). Ole5's Qdrant and ticket adapters stay in the app |
| Shared state across several instances (Redis, Postgres) | Later. v1 supports one process per `var_dir`, and the stores are ports (section 11) |
| Non-Groq adapters, a Saudi-hosted provider | When the owner has other keys (D-004) |
| Self-hosted models, GPUs, a media server | Excluded by D-005 |
| Prometheus `/metrics`, alert rules, a price table, a daily budget | On request (section 3.1) |
| Stricter consent levels, backend-loaded value lists, per-call delegated credentials | On request (section 3.1) |
| `t2v chat`, a `t2v eval` CLI, provider contract suites, a pytest plugin, Python 3.11 | On request (section 3.1) |
| Local-microphone console, WebRTC probe, load generator, deletion-request commands | Later (section 10.6) |

---

## 2. Who uses it

The personas below are the agent's assumptions, written to test the design. No T2 teammate has been asked yet, so nothing a persona "says" is a fact (GP-16).

| Persona | Who | What they need most | What ends their evaluation |
| --- | --- | --- | --- |
| The Ole5 app (the owner) | The first user. Built only on the public API, it drives every milestone | The 28 Oct rehearsal passes (DESCRIPTION.md) | Any need to reach into the library's internals. If Ole5 needs one, so will everyone |
| Sara, a backend developer (assumed) | Owns a FastAPI service with existing tools (device lookup, open a request; HR leave for a colleague). Knows tool calling and RAG; does not know audio or WebRTC | A demo of her own tools quickly; adding voice beside her service behind her SSO without changing how it is deployed; offline tests; tuning through settings, not code | One false "I opened your request"; Pipecat in her code; a library that takes over logging, OpenTelemetry or the environment; no browser client; a Python floor above her service's |
| An agent-graph owner (assumed) | Owns a LangGraph chatbot like Ole5's, and was burned by the October voice mode bolted onto it | Voice without bending the text agent; reusing existing tool functions; later, the graph's reasoning as the thinker | Being asked to add `channel == "voice"` branches; a thinker with no tests; clashes with langchain or numpy pins |
| The operator (assumed) | Puts an agent live and keeps it live. For Ole5 this is the owner, within D-005 | The deployment contract on one page; TURN for networks that block UDP; caps with a polite "busy"; usage per model; facts for the DPO; safe upgrades | Calls that fail silently on corporate networks; a 429 storm with no admission control; behaviour that changes between versions without notes |

The library also serves people who never touch it: the callers (customers, employees) and the support staff who receive tickets. The guarantees in section 8 are written for them.

All the personas need the same things, and this design is built around them:
- no Pipecat in their code;
- no global side effects;
- deterministic offline tests;
- consent and claims enforced by the library at runtime;
- an honest account of what runs where and what leaves the host.

**Questions to put to real teammates** (the contract is fixed at M0, open question 23, so an answer that needs a change to it goes to the owner):
1. Which Python version does your service run?
2. Which web framework, and how many workers and replicas?
3. How do your users sign in? Must your tools call other systems with the user's own token?
4. Where do you deploy (VM, Docker, Kubernetes), and can UDP reach it?
5. How sensitive is your data, and who is your data controller?
6. Which languages do your callers speak?
7. Which actions do you need, and does your backend accept an idempotency key?

---

## 3. The contract

### 3.1 What the library PROVIDES

| Area | What v1 provides | Built when |
| --- | --- | --- |
| Real-time call | WebRTC in the backend process (Pipecat SmallWebRTC). The browser's echo canceller works because the agent's audio arrives over a peer connection. Silero VAD and Smart Turn v3.2 run on CPU through ONNX, with no torch. The two-step interruption lowers the agent's voice, then decides from the transcribed overlap, because Groq Whisper gives no partial transcripts (D-004). Stop words, listening sounds and the agent's own echo are told apart. One cancel scope per reply (D-060); speech out clause by clause; a history of only what was heard. The library's voice session owns turn order, interruptions, cancellation and history; Pipecat's own interruptions and context handling are switched off (section 13). No Pipecat type appears in the public API | Ole5 M2, M3 |
| Talker | The turn loop and the reply language per turn. The system prompt is composed from the library's rules, the team's instructions and the language section, and `agent.render_prompt()` shows it. Tool results reach the model as data, never as instructions. The prompt tells the talker to write numbers as digits. When the caller asks for something no tool or action provides (a person, in an app with no handoff action), the talker says plainly that it cannot, and may offer a declared action that fits, such as a ticket, read back and confirmed like any other (open question 6) | Ole5 M4 |
| Tools | `@tool` on an async function, or on a sync function (run in a worker thread). The `ctx` parameter is optional. `Tool.from_function(fn, ...)` wraps an existing function. `bind=` fills parameters from the session (for example `from_caller("subject")`) and hides them from the talker. Each tool has a timeout and a barge-in policy. A progress line is spoken only if the caller has waited past its time with no answer begun. Duplicate calls follow a policy. Arguments are parsed before the function runs. `reports_on=` marks a status tool whose results may support claims (section 8.2) | Ole5 M4 |
| Confirmed actions | `@action` provides: a read-back from the team's templates, with fixed values spoken through their labels; a read-back receipt; the yes rule from words heard through speech-to-text; a confirmed action that only the yes rule can build; a durable outbox and a job outside the turn; `ctx.request_id` as the idempotency key, with an optional lookup by it; outcome sentences from the real result; defined meanings for every error; the per-call record; per-call and per-caller caps. Every action, a handoff included, takes consent this way (open question 6) | Ole5 M5 |
| Output guard | Checks every clause before it is spoken, against a lexicon of claim phrases declared per action and per language plus a default list. A claim passes only if the call's record holds the action, or a declared status tool returned it in this call. ID-shaped numbers pass only with evidence, after digit scripts and spelled-out digits are normalized. Once the talker calls an action, the rest of its text in that turn is dropped. The guard is lexical: section 8.4 says what it can miss | Ole5 M4 (IDs), M5 (claims) |
| Identity | A `Caller` fixed when the call starts, passed to every tool and action as `ctx.caller`. Nothing said in the call can change it. One `identity=` parameter on the runtime. `SignedJoinTokens` verifies single-use, short-lived join tokens that the team's website or app mints with `mint()` or with any JWT library. `DevIdentity` serves `t2v dev` only. Serving with no identity source is refused | Ole5 M2 |
| Serving | Two shapes. A **sidecar**: `serve()` or `t2v serve` runs a separate one-worker process. This is the documented default for any service with more than one worker or replica. A **mount**: `runtime.router()` in an app that runs one worker on one instance. The router carries the runtime's lifespan. A lock file stops a second process from using the same `var_dir`. A per-call offer secret guards `/offer`. `server.allowed_origins` serves pages on another origin. Graceful drain | Ole5 M2, M6; `serve()` is also Core proof |
| TURN credentials | Minted per call with coturn's shared-secret scheme and returned at join | The deployment's own plan (the roadmap's M6), only if Ole5's network test needs TURN |
| Browser side | A reference client, `t2v-client.js`: one plain ES module with no dependencies and no build step. A dev page. A versioned protocol `t2v/1` over the WebRTC data channel, carrying captions, state (listening, thinking, speaking, confirming), cards, voice lowering, notices (busy, error), stop and client stats. The client and the protocol's message list are provisional until the widget usage mode is designed (section 5.4) | Ole5 M2, M3 |
| Providers | Ports `SpeechToText`, `ChatModel` and `TextToSpeech`, with Groq adapters. The TTS adapter takes a model and a voice per language, splits text by clause to stay under the model's limit (200 characters for both Orpheus models, checked), and applies the pronunciation map. Fixed phrases are synthesized once and cached under `var_dir`. Each adapter carries a data-flow record (section 6.1) | Ole5 M1, M2, M4 |
| Languages | Presets for `ar-SA`, `ar` (MSA) and `en`, each with stop, wait, repeat, listening (`backchannel`) and no words (D-062); yes and send words come with the yes rule (M5). One canonical Arabic normalizer. Digit normalization (Arabic-Indic and Persian digits, spelled-out digits). Numbers, IDs and dates spoken in Arabic and English. Spoken labels for fixed values. Vocabulary turned into the Whisper prompt. A pronunciation map | Ole5 M1 to M5 |
| Settings | One typed `VoiceSettings`, built in code or from the environment under a prefix the team chooses. It is never read at import. `env` has no default. Secrets are `SecretStr`, with `*_FILE` variants. The settings reference and `.env.example` are generated | Ole5 M2 |
| Observability | One trace per turn, grouped by call, on the team's `TracerProvider`, with spans for speech-to-text, the model, each tool, the guard, confirmation and text-to-speech. A redaction hook. Audio and secrets are never exported. Usage per call and per model, in spans and in each call's report. Time to first useful audio is measured. Logs go only to the `t2_agentic_voice` logger. Pipecat's loguru output is off by default, and Pipecat's error frames and transport failures become library log lines and events | Ole5 M1 to M6 |
| Limits and resilience | Limits on call length, idle time, live calls per process (with a spoken busy message), live calls per caller and actions per call. A timeout and a spoken fallback for each provider. Groq 429s handled with `retry-after`. One limiter per model, shared by every runtime in the process. Dropped connections handled | Ole5 M6 |
| Testing kit | `TextCall` runs the real voice session, talker, actions, yes rule and guard with no audio, on a virtual clock. Also: `ScriptedLLM` (one entry per model request), `FunctionLLM`, fakes for every port, in-memory stores, assertions, `ActionSafetySuite`, opt-in live simulated callers (`simulate`), and `AudioCall`, which replays audio through the real turn-taking | Ole5 M3 to M5 |
| Evaluation helpers | Functions, not a CLI: the canonical normalizer, word and character error rates, recall of terms and IDs, text produced from silence, and the paired sign test from evaluation.md. Ole5's golden-set runner, splits and history stay in the app | Ole5 M1 |
| CLI | `t2v check`, `dev`, `serve`, `doctor`, `settings show --redacted`, `outbox list`, `outbox show`, `outbox reconcile` | Ole5 M2 to M5 |
| Docs and versioning | The pages in section 14. SemVer and a changelog with a "Behavior changes" section, from the first tag a teammate installs; versions stay `0.x`, with no date for 1.0 (open question 15) | M0 onward |

**Designed now, built later.** Each item below has a hook in v1, so adding it later changes no public signature.

| Item | Hook already in v1 | Built when |
| --- | --- | --- |
| `Authenticate(dep)`: the runtime mints the token behind the app's own login and adds `/token` | The `identity=` parameter | The deployment's own plan (the roadmap's M6) if the owner picks the one-time email code (open question 19, which plan 003's Q12 took to the deployment); otherwise on request |
| Per-call server-side state (`call_deps`), for delegated credentials; opaque tokens in mounted mode | Tokens never need to carry secrets | On request |
| Fixed value lists loaded from a backend at startup (`Choices`) | `validate` on each action | On request; Ole5's M5 plan decides whether it needs it |
| Stricter consent levels (every yes needs a send word; the draft card always shown) | The `consent=` field on actions | On request, from the first use case that needs one |
| Prometheus `/metrics`, alert rules, a price table, a daily budget | Usage counts in spans and in each call's report | On request |
| `t2v chat` (dry-run only, refuses `env=prod`) | The text transport | On request |
| A `t2v eval` CLI | The evaluation helper functions | When a second team records a golden set |
| Contract suites for provider authors | The Groq adapters' own tests | When a teammate writes an adapter |
| A pytest plugin | A three-line marker snippet in testing.md | On request |
| Python 3.11 | — | When a real teammate needs it (open question 3) |
| A generated JSON Schema for `t2v/1` | Pydantic message models | When a second client exists |
| Several agents in one runtime | A process-wide limiter; stores per agent | On request |
| The public-API snapshot (griffe), the wheel CI job, the changelog | — | The first tag a teammate installs |

### 3.2 What a teammate MUST provide

| What | Detail |
| --- | --- |
| A Python process | CPython 3.12 or later (open question 3), running asyncio. Linux in production (section 11) |
| A serving shape | Either a sidecar: a separate process with one worker, which imports their agent and their backend clients. Or a mount into an app that runs one worker on one instance. A service with more than one worker or replica must use the sidecar. Only one process may use a given `var_dir`, and the lock file enforces this on one host |
| The use case | Instructions written for speech, and the languages, each with a greeting |
| Read tools | Functions with typed parameters, written against their own systems, async or sync. A tool must have no side effects, and must be safe to cancel or to have its result discarded. The library cannot check that a "read" does not write |
| For each action | A pydantic draft model. Fixed value sets are `Literal` types or enums; in every declared language other than English, each value has a spoken label. A read-back template in every declared language. A `done` template and claim phrases in every declared language, written as past-tense claims ("I've opened"), not nouns ("request number"). An `execute` function that raises `ActionRejected` or `ActionNotSent` only when the action is definitely not done (section 6.4) |
| An identity source | A website or app server that mints join tokens with the key it shares with the runtime (`SignedJoinTokens.mint()`, or any JWT library following the documented claims). Or, once built, an `authenticate` dependency (section 3.1). Identity never comes from a tool argument. Join-token claims can be read by the caller, so they never hold secrets |
| A Groq key | A `SecretStr` setting, or a file. For each Orpheus model used, the account must have accepted its terms in the Groq console; both Orpheus models are previews (checked). Whether Arabic access needs Groq's account team is not confirmed either way (28 Oct research): the owner accepted the Orpheus terms in the console on 2026-11-03 (plan 003), and who can accept them is not confirmed; the owner's Arabic calls of 2026-11-04 reached the Arabic model on T2's key (plan 003, step 18). Apps share T2's one key (open question 11): each app sets its share of the key's real rate limits, read in the console, and a cap on live calls below that share (section 10.4) |
| A page | A web page hosting the voice UI: a copy of the reference client, or their own code speaking `t2v/1`. It shows a consent screen before the microphone opens, and passes the accepted consent version and the recording choice to whatever mints the token. It is served over HTTPS (a secure context; localhost is exempt). If its origin differs from the voice backend's, that origin is listed in `server.allowed_origins` |
| A media path | Callers' browsers must reach the backend's WebRTC media, either over open UDP or through a TURN relay. Networks that block UDP need TURN over TLS on port 443. Without a media path, calls from other networks fail (section 11) |
| Durable storage | A persistent `var_dir` for the outbox and the used-token store (SQLite in v1), or their own stores through the ports |
| An environment | `env` set to `dev`, `test`, `staging` or `prod`. It has no default, so a forgotten value fails at startup instead of switching the production checks off |
| Consent wording | The consent wording and its version, shown before the microphone opens. Whether sending callers' audio to Groq suits the team's data is the team's own call; the owner explains Groq's terms to each team that adopts the library (open question 10) |
| Evaluation data, before real users | A few recordings from consenting speakers on the real devices, with references written under the library's spelling guide, kept out of git. Scripted scenarios for their tools. Their own go-live thresholds. A demo needs none of this; going live without it is not supported |

### 3.3 What a teammate MAY provide

| What | Default when they don't |
| --- | --- |
| Settings values | Every setting except `env` has a documented default (section 7.6) |
| An environment prefix | `T2V_`. `VoiceSettings.from_env(prefix="HELPDESK_VOICE_")` sets their own. The prefix must belong to the library's settings alone, because unknown keys under it are errors (section 7.4) |
| Provider objects | Built from settings: Groq for all three |
| Their own adapter for a port | None |
| Idempotency in their backend, keyed on `ctx.request_id` (strongly advised) | The outbox still stops the library from retrying. A write with no reply and no lookup is reported to the caller as "could not confirm", with no number, and the outbox keeps the draft for reconciling |
| A `lookup` for an action | No lookup: the "could not confirm" path above |
| A `validate` hook on an action | Only the draft model's own validation |
| `bind=` on a tool | No parameter is filled from the session. `t2v check` warns about a parameter named like an identity (`email`, `user_id`, `customer_id`) that is left unbound |
| `reports_on=` on a status tool | No tool result supports a claim; only the call's own record does |
| Vocabulary (terms for the Whisper prompt, spoken forms) | Whisper's prompt holds the language's command words alone (`stt.send_prompt` turns it off: D-074) |
| A pronunciation map | Text goes to TTS as written |
| More stop, wait, repeat, listening (`backchannel`) and no words; yes and send words with the yes rule (M5) | The library's preset for each language |
| Send words per action (`ReadBack(send_words=...)`) | The language preset's send words |
| A TTS model and voice per language | The library's documented default per language, chosen in M2 |
| Speaking formats (`{x:id}`, `{x:number}`, their own) | The built-in formats |
| `failed`, `unknown` and `declined` templates | Library defaults in each preset language. A declared language with no preset must supply them |
| `on_call_start` | The language's greeting, with no extra context |
| A `KnowledgeBase` and `knowledge_tool()` | None: knowledge is just another tool |
| Cards for the screen (`ctx.show`) | Only captions are shown |
| A `TracerProvider` | If `tracing.endpoint` is set, the library makes a private provider and never installs it globally. Otherwise there is no tracing |
| A redaction function | None. Built-in Saudi patterns are opt-in: national ID or iqama, +966 phone numbers, SA IBAN, email |
| Logging configuration | Library logs go to the `t2_agentic_voice` logger, which has a `NullHandler`. Nothing appears until the app configures logging |
| Stores (`Outbox`, `UsedTokens`) | SQLite files under `var_dir/<agent name>/` |
| ICE and TURN servers | None. Host candidates only, which works on localhost and on the same network |
| Limits | The documented defaults (section 7.6) |
| Audio recording | Never stored. Storing audio needs both the `privacy.record_audio` setting and the caller's recording consent in the signed join token (invariant 8) |
| A thinker (after M7) | Off. While it is off, no delegate tool is offered and no prompt section exists |

---

## 4. The developer journey

### 4.1 Install

```bash
uv add "t2-agentic-voice @ git+https://<host>/<repo>@t2-agentic-voice/v0.4.0#subdirectory=packages/t2-agentic-voice"
uv run t2v doctor     # key valid; each language's TTS model and voice usable; model weights present
```

Teammates install from a git tag until T2's index is used (section 15).

**One install, with no extras** (open question 2). Installing the library brings everything a call needs: Pipecat (`pipecat-ai[webrtc]~=1.15.0`), FastAPI and uvicorn, the Groq SDK, PyJWT, num2words, the OpenTelemetry API, SDK and OTLP exporter, and the scorers (jiwer). Pipecat 1.15.0's `silero` extra exists but adds no requirement (its installed metadata, read 2026-11-04): the Silero VAD and Smart Turn v3.2 ONNX files ship inside its base wheel (checked). The library never uses Pipecat's `local-smart-turn` extra, which pulls in torch and transformers (checked).

The install is heavy. Pipecat 1.15.0's base dependencies include numpy, numba, onnxruntime (1.24.3 or later), openai, protobuf (5.29.6 or later), Pillow, loguru, python-dotenv, num2words and an exact `sentencex==1.0.32`. Its `webrtc` extra adds aiortc and `opencv-python-headless` (all checked). The headless OpenCV package may clash with an installed `opencv-python` (**verify**). is-this-for-you.md lists these, with the install size measured in M2.

### 4.2 Quickstart: `examples/minimal/app.py`

Step one is English only, because it needs only the English Orpheus model.

```python
"""A branch-hours helper: one lookup and one action that needs a spoken yes."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from t2_agentic_voice import (
    ActionContext,
    Claims,
    Language,
    ReadBack,
    Say,
    VoiceAgent,
    VoiceRuntime,
    VoiceSettings,
    action,
    tool,
)

HOURS = {"olaya": "8 am to 4 pm", "malaz": "9 am to 5 pm"}


@tool(description="Today's opening hours of one branch.")
async def opening_hours(
    branch: Annotated[str, Field(max_length=40, description="Branch name, for example Olaya")],
) -> str:  # no ctx parameter: this tool needs nothing from the call
    return HOURS.get(branch.strip().lower(), "unknown branch")


class Callback(BaseModel):
    branch: Annotated[str, Field(max_length=40)]
    reason: Annotated[str, Field(max_length=80)]  # model-written: read back word for word


class CallbackSent(BaseModel):
    reference: str


@action(
    description="Ask a branch to call the caller back. Collect the branch and the reason first.",
    read_back=ReadBack(en="I'll ask {branch} to call you back about: {reason}. Shall I send it?"),
    done=Say(en="Sent. Your reference is {reference:id}."),
    claims=Claims(en=["request sent", "I've sent", "I have sent"]),
)
async def request_callback(ctx: ActionContext[None], draft: Callback) -> CallbackSent:
    # ctx.request_id is the idempotency key; ctx.caller comes from the join token, never from the call.
    return CallbackSent(reference=ctx.request_id[:6])


agent = VoiceAgent(
    name="branch-helper",
    instructions="You help callers with branch opening hours and callback requests. One or two sentences.",
    languages=[Language.english(greeting="Hi! Which branch can I help you with?")],
    tools=[opening_hours, request_callback],
)


def make_runtime() -> VoiceRuntime:
    # No identity source: only `t2v dev` serves this, as a dev caller. Section 4.5 adds real callers.
    return VoiceRuntime(
        agent, settings=VoiceSettings.from_env()
    )  # T2V_* only; nothing read at import
```

```bash
export T2V_ENV=dev
export T2V_GROQ__API_KEY=...          # or T2V_GROQ__API_KEY_FILE=/run/secrets/groq_api_key
uv run t2v dev examples.minimal.app:make_runtime
# Chrome on this machine: http://localhost:7860/voice/dev — allow the microphone, talk, say "stop" mid-answer
```

**Step two: Saudi Arabic.** It needs access to the Arabic Orpheus model and its terms (section 3.2). The `ar` key covers both `ar-SA` and MSA.

```python
read_back = (
    ReadBack(
        en="I'll ask {branch} to call you back about: {reason}. Shall I send it?",
        ar="بطلب من فرع {branch} يتصلون عليك بخصوص: {reason}. أرسل الطلب؟",
    ),
)
done = (
    Say(en="Sent. Your reference is {reference:id}.", ar="تم الإرسال، رقم المرجع {reference:id}."),
)
claims = (
    Claims(en=["request sent", "I've sent", "I have sent"], ar=["تم الإرسال", "أرسلت الطلب"]),
)
...
languages = (
    [
        Language.saudi_arabic(greeting="هلا! أي فرع تبي تسأل عنه؟"),
        Language.english(greeting="Hi! Which branch can I help you with?"),
    ],
)
```

`t2v dev` runs only when `env` is `dev`. It serves the runtime with the dev page, which answers only clients on the loopback address. When the runtime has no identity source, it uses `DevIdentity` (`Caller(subject="dev")`) and prints a warning. It does not yet print a trace link per turn or reload on code changes (TD-077). The tests run the same file in text mode, in both languages, with no key (section 4.6). quickstart.md ends with a "first call does not work" checklist driven by `t2v doctor`'s output: the microphone permission, the key, Orpheus access and terms, and UDP.

When `VoiceAgent(...)` is constructed, these checks run. Each failure has a FIX line.
- Every template covers every declared language; `ar-SA` falls back to `ar`.
- Every `{placeholder}` names a field of the draft (read-back) or of the result (done).
- Every format, such as `id` or `number`, exists in the agent's speaking rules.
- A template in a language other than English that uses a `Literal` or enum field needs a spoken label for every value in that language.
- Tool and action names are unique.
- No draft field is named like consent (`confirmed`, `approved`).
- Warning: the Whisper prompt built from the vocabulary and the command words does not fit Groq's 224-token limit, so `whisper_prompt` leaves out the words past 224 bytes (D-074).
- Warning: a claim phrase appears in the same action's read-back, so the talker's own paraphrase of the read-back would be blocked.
- Warning: a tool parameter named like an identity is left unbound.

### 4.3 Declare a use case

```python
from t2_agentic_voice import Language, Phrases, Vocabulary, VoiceAgent

agent = VoiceAgent[HelpdeskDeps](
    name="it-helpdesk",
    version="2026-10-31.1",  # stamped on every trace, with the agent's fingerprint
    instructions={"en": load("prompts/en.md"), "ar": load("prompts/ar.md")},
    languages=[
        Language.saudi_arabic(greeting="هلا، معك دعم تقنية المعلومات. وش أقدر أساعدك فيه؟"),
        Language.english(greeting="Hi, IT support here. How can I help?"),
    ],
    default_language="ar-SA",
    vocabulary=Vocabulary(terms=["VPN", "Outlook", "LT-"], spoken={"VPN": ["في بي ان"]}),
    pronounce={"LT-": {"ar": "إل تي", "en": "L T"}},
    # both words are in the Arabic presets' lists already, and `extend` adds none twice (D-062)
    phrases=Phrases.defaults().extend(stop={"ar": ["خلاص"]}, backchannel={"ar": ["اها"]}),
    tools=[lookup_device, my_requests, open_request, hand_off],
    on_call_start=prefetch_open_requests,  # optional: returns CallStart(context=..., greeting=...)
)
```

`uv run t2v check helpdesk.voice:agent` prints:
- the full prompt for each language;
- the tool schemas the talker sees;
- the templates, the effective word lists and the guard's lexicon;
- each provider's data-flow record;
- the settings in force, with secrets redacted, and the environment.

### 4.4 Tools and confirmed actions

```python
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from t2_agentic_voice import (
    ActionContext,
    ActionRejected,
    CallContext,
    Card,
    Claims,
    ReadBack,
    Say,
    Spoken,
    Tool,
    ToolError,
    action,
    from_caller,
    tool,
)


@tool(
    description="Find a laptop or phone assigned to the caller, by the asset tag on its sticker.",
    timeout_s=3,
    on_interrupt="cancel",
    progress=Say(ar="أشيك لك على الجهاز", en="Checking that device for you."),
)
async def lookup_device(
    ctx: CallContext[HelpdeskDeps],
    asset_tag: Annotated[str, Field(pattern=r"^LT-\d{5}$", description="For example LT-00423")],
) -> DeviceInfo:
    dev = await ctx.deps.itsm.devices.get(
        asset_tag, owner_id=ctx.caller.subject
    )  # identity from the session
    if dev is None:
        raise ToolError(
            "No device with that tag is assigned to you."
        )  # this text goes to the talker
    ctx.show(
        Card(title=dev.model, fields={"Status": dev.status, "Warranty": str(dev.warranty_end)})
    )
    return DeviceInfo(
        model=dev.model, status=dev.status
    )  # data for the talker; evidence for the guard


# An existing sync function, wrapped without rewriting it.
my_requests = Tool.from_function(
    legacy_itsm.list_open_requests,  # def list_open_requests(employee_id: str) -> list[dict]
    name="my_requests",
    description="List the caller's open IT requests and their status.",
    bind={
        "employee_id": from_caller("subject")
    },  # hidden from the talker's schema; filled from the session
    reports_on=["open_request"],  # its results may support claims about open_request
)

Category = Annotated[
    Literal["hardware", "software", "access"],  # a fixed set, never free model text
    Spoken({"hardware": {"ar": "أجهزة"}, "software": {"ar": "برامج"}, "access": {"ar": "صلاحيات"}}),
]


class OpenRequest(BaseModel):
    category: Category
    asset_tag: Annotated[str, Field(pattern=r"^LT-\d{5}$")]
    summary: Annotated[
        str, Field(max_length=200)
    ]  # model-written: parsed, capped, read back word for word


class RequestOpened(BaseModel):
    id: str


@action(
    description="Open an IT request. Collect the category, the asset tag and a one-sentence summary first.",
    read_back=ReadBack(
        {
            "ar": "بفتح طلب {category} للجهاز {asset_tag:id}: {summary}. أرسله؟",
            "en": "I'll open a {category} request for {asset_tag:id}: {summary}. Shall I send it?",
        },
        send_words={
            "ar": ["افتحه"],
            "en": ["open it"],
        },  # added to the language preset's send words
    ),
    done=Say({"ar": "تم، رقم الطلب {id:id}.", "en": "Done, your request number is {id:id}."}),
    claims=Claims(
        {
            "ar": ["فتحت الطلب", "تم فتح الطلب", "انفتح الطلب"],
            "en": ["request opened", "I've opened", "I have opened"],
        }
    ),
    max_per_call=2,
)
async def open_request(ctx: ActionContext[HelpdeskDeps], draft: OpenRequest) -> RequestOpened:
    req = await ctx.deps.itsm.requests.create(
        **draft.model_dump(), requester_id=ctx.caller.subject, idempotency_key=ctx.request_id
    )
    if req.rejected:
        raise ActionRejected(req.reason)  # definitely not done: the `failed` template is spoken
    return RequestOpened(id=req.id)  # any other exception, or a timeout: lookup, then `unknown`


@open_request.lookup  # optional: how to find a write whose reply was lost
async def find_request(ctx: ActionContext[HelpdeskDeps], request_id: str) -> RequestOpened | None:
    found = await ctx.deps.itsm.requests.find_by_idempotency_key(request_id)
    return RequestOpened(id=found.id) if found else None
```

Templates are keyed by language tag (`{"ar-SA": ..., "en": ...}`); the keyword form (`ar=`, `en=`) is shorthand for the same mapping. The talker sees a tool named `open_request` whose schema is the draft's schema and nothing more. There is no `confirmed` field and no "confirm" tool. Section 6.4 describes what happens when the talker calls it.

### 4.5 Serve real callers

**The sidecar** is the default for any service with more than one worker or replica. It is also Ole5's shape if its website mints the token (open question 19). The sidecar is a separate process with one worker. It imports the team's agent and backend clients.

```python
# helpdesk/voice_main.py
from t2_agentic_voice import VoiceRuntime, VoiceSettings
from t2_agentic_voice.identity import SignedJoinTokens
from t2_agentic_voice.server import serve


def make_runtime() -> VoiceRuntime:
    settings = VoiceSettings.from_env(prefix="HELPDESK_VOICE_")
    return VoiceRuntime(
        agent,
        settings=settings,
        deps=HelpdeskDeps.open,  # an async context-manager factory, entered in lifespan
        identity=SignedJoinTokens.from_settings(settings.join),
        tracer_provider=make_tracer_provider(),
    )  # mine; the library never sets a global one


if __name__ == "__main__":
    serve(make_runtime)  # or: uv run t2v serve helpdesk.voice_main:make_runtime
```

The team's existing app, with any number of workers, mints the token behind its own login:

```python
from t2_agentic_voice import Caller, Consent
from t2_agentic_voice.identity import SignedJoinTokens

tokens = SignedJoinTokens(keys={"k1": join_key}, current_kid="k1")  # the same key as the sidecar


@app.post("/voice-token")
async def voice_token(
    body: ConsentChoice, user: Employee = Depends(current_employee)
) -> dict[str, str]:
    caller = Caller(
        subject=user.id, display_name=user.name, locale=user.locale
    )  # no secrets: the caller can read claims
    return {
        "token": tokens.mint(
            caller, consent=Consent(version=body.version, record_audio=body.record_audio)
        )
    }
```

**The mount** is for an app that runs one worker on one instance, and for demos:

```python
app = FastAPI(lifespan=app_lifespan)
app.include_router(
    runtime.router(), prefix="/voice"
)  # the router carries runtime.lifespan; FastAPI merges it
```

FastAPI's `include_router` merges a router's lifespan into the app's (checked in FastAPI 0.162.0; the M2 plan sets the version floor). `combine_lifespans` remains for mounting as a sub-application. If the lifespan never ran, every route answers with a clear "runtime not started" error.

**The routes**, after the prefix:
- `POST /token`: only with `Authenticate` (built later, section 3.1).
- `POST /join`: token in; call ID, offer secret, ICE servers and protocol version out.
- `POST /offer` and `PATCH /offer` (ICE): both need the offer secret.
- `GET /client/1/t2v-client.js`, `GET /health`, `GET /ready`.
- `GET /dev`: only when `env` is `dev`, and only for loopback clients.

**The browser side**, on a page served from another origin:

```html
<script type="module">
  import { VoiceClient } from "/static/t2v-client.js";    // a copy on the team's own site, or the backend's /client/1/ path
  const call = await VoiceClient.start({
    base: "https://voice.helpdesk.internal/voice",          // that origin is listed in server.allowed_origins
    getToken: async () => (await (await fetch("/voice-token", {
      method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({ version: CONSENT_VERSION, record_audio: false }),
    })).json()).token,
  });                                                       // join, offer; mic with echoCancellation
  call.on("caption", c => render(c.speaker, c.text, c.final));
  call.on("card", card => renderCard(card));
  call.on("state", s => setStatus(s));      // listening | thinking | speaking | confirming
  call.on("notice", n => showNotice(n));    // busy, error, cut_off, ended, with localized text
  stopBtn.onclick = () => call.stop();      // Esc is bound by default
</script>
```

`VoiceClient.start` also accepts a ready `token`. In mounted mode with `Authenticate`, it takes `consent` and calls `/token` itself.

### 4.6 Test

```python
from t2_agentic_voice import Caller
from t2_agentic_voice.testing import ActionSafetySuite, ScriptedLLM, TextCall, call_tool


async def test_request_needs_a_heard_yes(itsm_fake) -> None:
    llm = ScriptedLLM(
        [  # one entry per model request
            [
                call_tool(
                    "open_request",
                    category="hardware",
                    asset_tag="LT-00423",
                    summary="VPN does not connect",
                )
            ],
        ]
    )
    async with TextCall(
        agent, deps=HelpdeskDeps(itsm=itsm_fake), llm=llm, caller=Caller(subject="u-1")
    ) as call:  # env=test; heard words come from typed text
        turn = await call.user("ابغى افتح طلب، اللابتوب LT-00423 ما يشبك على الـVPN")
        turn.expect.read_back(contains="LT-00423")
        await call.user("نعم", during="read_back")  # over the summary: ignored, does not count
        assert itsm_fake.created == []
        turn = await call.user("نعم أرسله")  # after the receipt and the closing question
        turn.expect.action_completed("open_request")
        turn.expect.said(contains=itsm_fake.created[0].id)
    assert call.violations == []  # guard and yes-rule checks run in every TextCall


class TestOpenRequestIsSafe(ActionSafetySuite):  # the library's adversarial cases, on my action
    agent = agent
    action = open_request
    draft = OpenRequest(category="hardware", asset_tag="LT-00423", summary="VPN does not connect")

    def make_deps(self) -> HelpdeskDeps:
        return HelpdeskDeps(itsm=FakeItsm())
```

These run in CI with no key and no network, and never start Pipecat. Live scenario runs are opt-in. A team marks them `@pytest.mark.t2v_live`, registers the marker in its `conftest.py`, and deselects it with `addopts = "-m 'not t2v_live'"` (testing.md gives the three lines).

### 4.7 Tune with settings, not code

```bash
HELPDESK_VOICE_ENV=prod
HELPDESK_VOICE_STT__MODEL=whisper-large-v3-turbo
HELPDESK_VOICE_LLM__REASONING_EFFORT=low
HELPDESK_VOICE_TTS__LANGUAGES='{"ar-SA": {"model": "canopylabs/orpheus-arabic-saudi", "voice": "<voice>"},
                                "en": {"model": "canopylabs/orpheus-v1-english", "voice": "<voice>"}}'
HELPDESK_VOICE_WORDS__STOP='{"ar": ["خلاص"]}'                          # extends the declaration's lists
HELPDESK_VOICE_WORDS__VOCABULARY='["إجازة اضطرارية"]'
HELPDESK_VOICE_TURNS__VAD_STOP_MS=200
HELPDESK_VOICE_LIMITS__MAX_LIVE_CALLS=8
HELPDESK_VOICE_SERVER__ALLOWED_ORIGINS='["https://helpdesk.internal"]'
HELPDESK_VOICE_SERVER__ICE_SERVERS='[{"urls": ["turns:turn.t2.internal:443?transport=tcp"]}]'
HELPDESK_VOICE_SERVER__TURN_SECRET_FILE=/run/secrets/turn_secret
HELPDESK_VOICE_JOIN__KEYS_FILE=/run/secrets/join_keys.json
```

### 4.8 Deploy

```bash
uv run t2v serve helpdesk.voice_main:make_runtime --host 0.0.0.0 --port 8081    # the sidecar: always one worker
```

- **One worker per process, and one process per `var_dir`.** A call's peer connection, ICE state and session live in that one process's memory. The runtime's lifespan takes an exclusive lock file under `var_dir`; a second process on the same `var_dir` refuses to start, with a FIX line that points to sidecar mode. The lock cannot see a second host, so the docs state the one-instance rule (section 11).
- **A mounted app** runs with `--workers 1` and a graceful-shutdown timeout at least as long as `server.drain_timeout_s`. The mount changes how the host app is deployed, which is why the sidecar is the default for multi-worker services.
- **The container** needs host networking, or the host's public address advertised. A TURN relay serves callers on networks that block UDP.
- **`var_dir`** sits on a persistent volume.
- **SIGTERM** drains the process: readiness turns false, new joins get a busy notice, and live calls finish within the drain timeout.

The deployment guide (section 14) gives the reverse-proxy, coturn and Phoenix pieces.

### 4.9 Upgrade

```bash
uv add "t2-agentic-voice @ git+https://<host>/<repo>@t2-agentic-voice/v0.7.0#subdirectory=packages/t2-agentic-voice"
# with a package index instead (section 15): uv add "t2-agentic-voice~=0.7.0"
uv run t2v check helpdesk.voice:agent      # fails on removed settings, warns on deprecated ones
uv run pytest                              # the offline suite, with no code change expected
```

Before upgrading, the team reads the changelog's "Behavior changes" section. Each release names the Pipecat version its suite passed on. The team reruns its own evaluation before go-live. The team never pins Pipecat itself.

---

## 5. Public API surface

### 5.1 Public modules

Stability levels are defined in section 5.4. "Provisional" covers everything that is not on the quickstart or the paths in sections 4.3 to 4.6, until a second team has used it.

| Module | Contents | Stability |
| --- | --- | --- |
| `t2_agentic_voice` | `VoiceAgent`, `Language`, `Vocabulary`, `Phrases`, `SpeakingRules`, `Say`, `ReadBack`, `Claims`, `Spoken`, `Card`, `tool`, `action`, `Tool`, `Action`, `from_caller`, `CallContext`, `ActionContext`, `Caller`, `Consent`, `CallStart`, `CallOptions`, `Providers`, `VoiceSettings`, `VoiceRuntime`; errors (`T2VoiceError`, `ConfigurationError`, `ToolError`, `ActionRejected`, `ActionNotSent`, `ProviderError`, `JoinRejected`) | stable |
| `t2_agentic_voice.ports` | `SpeechToText`, `ChatModel`, `TextToSpeech`, `IdentityVerifier`, `UsedTokens`, `Outbox`, `KnowledgeBase`; data types `AudioClip`, `AudioChunk`, `Transcript`, `ChatRequest`, `ChatEvent` (`TextDelta`, `ToolCallRequest`, `Usage`, `Done`), `DataFlow`, `Passage`, `OutboxEntry` | stable (`KnowledgeBase`, `Outbox`, `UsedTokens`: provisional) |
| `t2_agentic_voice.identity` | `SignedJoinTokens` (mint and verify), `DevIdentity`; later `Authenticate` | stable |
| `t2_agentic_voice.groq` | `GroqSTT`, `GroqChat`, `GroqTTS` | stable |
| `t2_agentic_voice.server` | `serve(factory)`, `combine_lifespans` | stable |
| `t2_agentic_voice.testing` | `TextCall`, `ScriptedLLM`, `FunctionLLM`, the fakes, `VirtualClock`, `ActionSafetySuite`, `assert_no_secret_leaks` | stable |
| `t2_agentic_voice.testing.simulate` | `simulate`, `SimulatedCaller`, the hard checks | provisional |
| `t2_agentic_voice.testing.audio` | `AudioCall` (audio replay) | provisional |
| `t2_agentic_voice.events` | Frozen event classes (section 6.6) | provisional |
| `t2_agentic_voice.languages` | Presets, `normalize_arabic`, `normalize_digits`, `speak_number`, `speak_id`, `speak_date`, script detection | provisional |
| `t2_agentic_voice.knowledge` | `knowledge_tool(kb, ...)` | provisional |
| `t2_agentic_voice.stores` | `SqliteOutbox`, `SqliteUsedTokens`, `MemoryOutbox`, `MemoryUsedTokens` | provisional |
| `t2_agentic_voice.tracing` | Tracing setup from settings, `Redactor`, Saudi PII patterns | provisional |
| `t2_agentic_voice.evals` | `wer`, `cer`, `term_recall`, `id_recall`, `silence_output`, `sign_test` | provisional |
| `t2_agentic_voice.experimental` | Later: `Thinker`, `Deliver`, `ThinkerBackend`, `LLMThinker` | experimental |
| `t2v` command | Subcommand names and flags | stable (output text and `--json` shapes: provisional) |
| Wire protocol `t2v/1` and `t2v-client.js` | Section 5.5 | provisional, apart from the version check at join |

*Built so far (M1, plan 002; plan 004; plan 003's Block 0; plan 005):* nine facades, the five D-021 lists and `identity`, `server`, `stores` and `events` (D-032), each holding the names of its row that are built, and the names beyond the rows that D-032 lists. The package root exports `T2VoiceError`, `ConfigurationError`, `ProviderError` and `JoinRejected` from its row; `VoiceSettings` and the classes of its twelve groups (`GroqSettings`, `JoinSettings`, `LimitSettings`, `LoggingSettings`, `PrivacySettings`, `ServerSettings`, `SessionSettings`, `StorageSettings`, `SttSettings`, `TracingSettings`, `TtsSettings` and `TurnSettings`), with `TtsVoice`, what `tts.languages` holds (section 7, D-032); `VoiceAgent`, `Language`, `Caller` and `Consent`; `VoiceRuntime` and `Providers`, signatures in Block 0 that plan 003's Track F built; `get_logger`, `configure_logging` and `StructuredLogger`, what `get_logger` returns (section 10.2, D-032); and `Status`, `status`, `NotFoundError` and `InvalidRequestError`, which are in no row (TD-034). Plan 005 (M3) added to the root `InterruptionSettings` and `WordSettings`, its two new groups' classes, and `Phrases` and `Words` (D-062); and to `evals`, `AudioCall`, `OverlapReplay` and `OverlapRequest`, the audio replay (section 9.5), until `testing` is public with `TextCall` (M4).

The settings keys (section 7) are public too. Renaming or removing one follows the deprecation policy.

### 5.2 Main types

| Type | Role | Notes |
| --- | --- | --- |
| `VoiceAgent[Deps]` | The use case: frozen, no IO | `@final`. `render_prompt(lang)`. `card()` returns the schemas, templates and a fingerprint |
| `Tool` / `@tool` / `Tool.from_function` | A read-only capability | Async or sync. `bind=`, `reports_on=`, `timeout_s`, `on_interrupt`, `progress`. There is no global registry |
| `Action` / `@action` | One side effect after consent | `.lookup` decorator (section 6.4) |
| `CallContext[Deps]` | What a tool sees | `caller`, `deps`, `language`, `call_id`, `turn_id`, `record` (read-only), `show(card)`, `span(name)` |
| `ActionContext[Deps]` | What an action sees | Everything in `CallContext`, plus `request_id` and `consent` (the heard words, their source and time; read-only, for audit) |
| `Caller` | The verified identity | Frozen: `subject`, `display_name`, `locale`, `attributes` (a string map). It travels in a JWT the caller can read, so it never holds secrets |
| `Consent` | The caller's choices on the consent screen | `version`, `record_audio`. Carried only in the signed join token |
| `Say`, `ReadBack`, `Claims`, `Spoken`, `Card` | Templates, labels and screen content | Template values come from the draft or the result. Fixed values are spoken through their labels. Free-text draft fields are model output: parsed, capped in length, and read back word for word so the caller can check them |
| `Language`, `Vocabulary`, `Phrases`, `SpeakingRules` | The language parts | Presets for `ar-SA`, `ar`, `en` |
| `Providers` | The STT, chat and TTS objects | `Providers.from_settings(s)`, `.replace(stt=...)` |
| `VoiceSettings` | All tunable settings | Section 7 |
| `VoiceRuntime` | Runs calls for one agent | Construction is cheap and does no IO. `identity=` takes one identity source. `lifespan` does IO: it takes the lock file, warms VAD and Smart Turn, checks models and voices, renders and caches fixed phrases, starts the outbox worker and reconciles the previous run. Also `router()`, `on(Event)`, `drain()`. Several runtimes in one process share the per-model limiter, and each keeps its stores under `var_dir/<agent name>/` |

### 5.3 Public and internal

- **What is public.** The names in `__all__` of the modules in section 5.1, the `t2v` commands, the protocol and the settings keys. Everything else is internal, whatever its import path. The layer packages (`t2_agentic_voice.agent`, `.voice` and so on) can be imported, but they are not public.
- **The public modules at the package root** are thin facades: they only re-export names (section 12.4, ARCH-FACADE).
- **How the boundary is enforced:**
  1. A test fails if a public signature names a type from `pipecat`, `aiortc`, `onnxruntime` or `groq`.
  2. From M2, a CI job installs only the base package and imports every base-level public module.
  3. In the app and the examples, ARCH-PUBLIC (built, D-013) forbids internal modules.
  4. From the first tag a teammate installs, a public-API snapshot made with griffe is checked in CI. Every change shows up as a diff, and a breaking change needs a changelog entry.

### 5.4 Stability, versioning and deprecation

- **Stability levels:**
  - **Stable:** follows SemVer and the deprecation policy below.
  - **Provisional:** may change in any minor release. Each change is listed in the changelog, and the griffe snapshot marks the module, but no deprecation period is promised. A provisional module becomes stable once a second team has used it, or at the 1.0 review.
  - **Experimental:** `t2_agentic_voice.experimental` may change in any minor release, and importing it warns once.
- **SemVer on the stable surface:**
  - **Before 1.0:** a minor release may break, but only with a "Breaking" changelog entry and a migration note. Where it is cheap, the old name keeps working for one minor release and raises a `DeprecationWarning`.
  - **From 1.0 on:** breaking changes come only in a major release, and a deprecation warns for at least one minor release before the thing is removed.
- **Behavior changes.** Some changes move a measured outcome: turn-taking defaults, the interruption window, chunking, prompts, the guard's lexicon, default models or voices. Each one first lands behind a setting. Its default changes only on a registered measurement ("Variants behind settings" in evaluation.md). The changelog lists it under "Behavior changes", with its numbers.
- **The changelog** starts with the first tag a teammate installs. Its sections are Added, Changed, Behavior changes, Deprecated, Removed, Fixed and Security.
- **The Pipecat pin.** The library declares `pipecat-ai[webrtc]~=1.15.0` (open question 8). The repository's lock pins the exact version, and each release states the version its suite passed on.
  - **Upgrade policy:** Pipecat moves at a milestone boundary, or for a security advisory. Each move is a plan of its own and a library minor release.
  - Pipecat rarely ships patch releases. From 1.8.1 (27 Aug) to 1.15.0 (29 Oct), PyPI lists seven minor releases and no patch release after 1.8.1 (checked). So a security fix usually means a Pipecat minor move, which means a library minor release. Library patch releases for dependency fixes are best effort, as SUPPORT.md says.
  - An operator may raise a patch version inside the compatible range in their own lock.
  - The surface we use is kept small (the transport, VAD, Smart Turn, and the STT and TTS base classes: section 13), so each move stays small.
- **The protocol version.** It is an integer. Client and server exchange it at join, and a mismatch gives the caller a clear notice instead of a dead call. The router serves the client under `/client/<protocol>/`. This version check is stable. The message list is provisional until the widget usage mode is designed.
- **Python versions.** Every CPython version from the floor (3.12) up to the newest one Pipecat supports. Lowering the floor is a minor release. Dropping a version is a minor release, announced one minor release earlier.

### 5.5 The wire protocol `t2v/1`

**Signalling** is HTTP, all after the router's prefix:
1. `POST /token` (only with `Authenticate`): the team's dependency runs; the body carries the caller's consent choice; it returns a join token.
2. `POST /join`: the body carries the token and the client's protocol version. It consumes the token, once. It returns:
   - the call ID;
   - an **offer secret**: random, for this call only, never logged, traced or put in an event;
   - the ICE servers, with per-call TURN credentials if configured;
   - the protocol version.
3. `POST /offer`: the call ID, the offer secret and the SDP offer; it returns the answer. A second offer for the same call gets 409. Renegotiation is not supported in v1.
4. `PATCH /offer`: trickled ICE candidates, with the offer secret. The secret stops working when the call ends or ICE completes.

The call ID is not a credential: it appears in traces (`session.id`), events, logs and the `hello` message. Pipecat's SmallWebRTC request handler keys its connections on a `pc_id`, and it reuses an existing connection when a request names one (checked in 1.15.0). The router therefore checks the offer secret first and never passes a client-supplied `pc_id` to it. An adversarial test under invariant 7 covers an offer without the secret, with another call's secret, and a second offer.

**Cross-origin pages.** When `server.allowed_origins` is set, the router answers preflight requests and adds CORS headers for those origins only. In mounted mode the router defers to the app's own CORS middleware and says so at startup.

**Messages** are JSON on the WebRTC data channel, each carrying `"v": 1` and drawn from a closed list:

| Direction | Messages |
| --- | --- |
| Server to client | `hello` (protocol, call ID, languages); `state` (listening, thinking, speaking, confirming); `caption` (speaker, text, final, turn ID; agent captions are sent per clause as each one plays, and an agent's clause a stop cut while it played is sent again with `cut`); `duck`, with the `level` the agent's voice plays at, and `unduck` (step one of an interruption, D-065); `card`; `notice` (busy, error, ended, with localized text); `ended` (reason) |
| Client to server | `hello` (protocol, client version); `stop` (the Stop button or Esc); `hangup`; `client_stats` (selected ICE candidate type, time to connect, whether `echoCancellation` was applied, time the first audio played) |

No client message can set consent or identity. Tool arguments and tool results never reach the browser, unless a tool chooses to show something with `ctx.show()`. The message models are pydantic classes in the library, documented in serving.md. A generated JSON Schema comes when a second client exists.

---

## 6. Extension points

### 6.1 Provider ports

```python
# t2_agentic_voice.ports (public, stable)
class DataFlow(BaseModel, frozen=True):
    provider: str  # "Groq"
    processed_in: str  # "not stated by the provider"
    stored_in: str  # "US (Google Cloud buckets), for data Groq retains"
    retention: str  # "none by default for inference; reliability and abuse logs up to 30 days
    #  unless Zero Data Retention is on or log storage is opted out"


class AudioClip(BaseModel, frozen=True):
    pcm16: bytes
    sample_rate: int = 16_000


class Transcript(BaseModel, frozen=True):
    text: str
    language: str | None
    confidence: float | None = None
    billed_seconds: float | None = None  # for usage metering


class SpeechToText(Protocol):
    name: str
    data_flow: DataFlow  # printed by `t2v check`

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript: ...


class ChatModel(Protocol):
    name: str
    data_flow: DataFlow

    def stream(
        self, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]: ...  # TextDelta, ToolCallRequest, Usage, Done


class TextToSpeech(Protocol):
    name: str
    data_flow: DataFlow

    def max_chars(
        self, language: str
    ) -> int | None: ...  # the clause splitter honours it (200 for both Orpheus models)
    def synthesize(
        self, text: str, *, language: str
    ) -> AsyncIterator[AudioChunk]: ...  # model and voice per language
    async def check_language(
        self, language: str
    ) -> None: ...  # raises naming the missing model, voice, access or terms
```

The Groq `DataFlow` values come from Groq's "Your Data" page (checked). That page does not say where requests are processed.

*Built in M1 (plan 002), beyond this block:* `Transcript.no_speech_prob`, Whisper's own estimate that a clip holds no speech (the owner's ruling, D-021); and, proposed in D-021 for the owner to rule on, `AudioClip.seconds` and the input checks of `DataFlow`, `AudioClip` and `Transcript`.

**Rules for every port:**
- **Cancellation.** The runtime cancels a provider call by cancelling its task. The Groq adapters' tests check that a call stops within 50 ms and leaks no tasks or connections. Contract suites for other authors come on request (section 3.1).
- **Failures** are raised as `ProviderError(kind, retryable, retry_after_s)`.
- **Streaming speech-to-text.** The name `StreamingSpeechToText` is reserved for an optional protocol with partial transcripts. It will be designed when a streaming provider exists. The voice session already takes "words heard so far" as events, so the interruption logic will not change shape.
- **Swapping a provider.** A setting (`stt.provider` and so on) picks among the built-in adapters. Any other adapter is an object passed in code. There is no registry and no discovery through entry points. Passing an object in code goes beyond GP-22's "by configuration", so it needs a decision entry (section 16.3).

```python
runtime = VoiceRuntime(
    agent,
    settings=settings,
    identity=...,
    providers=Providers.from_settings(settings).replace(stt=SaudiHostedSTT(...)),
)
```

### 6.2 The thinker: designed now, built after M7

The thinker is the port `ThinkerBackend.think(request: ThinkRequest) -> Proposal` in `t2_agentic_voice.experimental`. The owner decided that it is off by default, never acts, has versioned results that are dropped when stale, and has a time budget. Building it after M7, in the experimental module, is the agent's proposal (open questions 16 and 17).

- **What a request carries:**
  - the talker's task text from its delegate call;
  - the heard transcript (agent turns cut where the caller barged in);
  - the language heard;
  - the `Caller`;
  - the conversation version;
  - the deadline.
- **What a proposal can be.** It is a parsed union:
  - `Answer(text, display, evidence)`;
  - `SuggestedAction(action, draft)`;
  - `Clarify(question)`;
  - `NothingFound`.
- **It is off by default.** While it is off, no delegate tool is offered, no prompt section exists, and no tasks run.
- **It never acts.**
  - A proposal is never spoken word for word. The talker speaks it, and the guard checks every sentence.
  - Model-written text shown on screen, such as an `Answer`'s `display` text, passes the same guard rules before it is shown.
  - A `SuggestedAction` is only data. The talker must call the action itself, which starts the normal read-back and yes rule.
  - The thinker gets read-only tools. Giving it an action is a `ConfigurationError`.
- **Results carry a version and are dropped when stale.**
  - The version goes up with each caller turn that is a new request. Listening sounds and "take your time" do not count.
  - There is one job in flight per call. A new job replaces the running one, which is cancelled.
  - A result for an old version is dropped and traced as `ThinkerDropped(stale)`.
- **It has a time budget.**
  - The budget is a hard deadline. When it passes, the talker is told "no result".
  - A late result is shown on screen only (a setting), after the guard.
  - Results are delivered only at a turn boundary, never over the caller.
- **Sync backends** run in a thread with the context copied. They are cancelled at their next step boundary. Abandoned jobs are counted and capped per call and per process.
- **It has its own usage line and its own cost budget per call.**
- **Evidence.** Reads done through tools the library runs count as evidence for the guard. Text made inside the thinker's own code does not: an ID it mentions is blocked unless some evidence holds it.

What v1 must already have for it, all built for M3 to M5 anyway:
- a conversation version counter;
- delivery points at turn boundaries;
- the heard transcript;
- usage lines per component;
- types in which a proposal cannot act.

### 6.3 Use-case backends: knowledge, tickets, anything

- **The library has no ticket port and no HR port.** A team's backend is its own code, passed in as `deps` and used by its tools and actions. `deps` is either a shared object or an async context-manager factory that `lifespan` enters. This keeps OTRS fields and ticket wording out of the library. ARCH-WORDS (section 12.4) checks it. Per-call state is on request (section 3.1).
- **Fixed value sets** are `Literal` types or enums in the team's code, with spoken labels. When the real list lives in the backend, the team either keeps a `Literal` that matches it, or types the field as `str` and checks it against the backend's list in `validate`, which tells the talker the allowed values. A list loaded from the backend into the schema at startup (`Choices`) is on request.
- **Knowledge** has a protocol and a helper:
  - `KnowledgeBase` has one method, `async search(query, *, language, caller, limit) -> list[Passage]`.
  - `knowledge_tool(kb, description=..., progress=...)` returns a read tool. It does one search per question, gives the talker the top `limit` passages whole to write its own spoken answer from (D-071), with every step of the best passage, and shows no card (D-075).
  - Both are optional: a team can write its own tool instead.
  - A generic Qdrant adapter comes later. Ole5's stays in the app until a second team needs one.

### 6.4 Tools and confirmed actions

| | Tool (`@tool`) | Action (`@action`) |
| --- | --- | --- |
| What it may do | Read only (the team's promise) | One side effect |
| Function | `async def`, or `def` (run in a worker thread). `ctx` is optional, found by its type annotation. Existing functions through `Tool.from_function` | `async def` or `def`, taking `ctx` and the draft |
| When it runs | Inside the turn, as soon as the talker asks | After consent, as a job outside the turn |
| On barge-in | Async: cancelled (the default) or finished (`on_interrupt="finish"`). Sync: the result is discarded and the thread finishes in the background; such threads are counted and capped per process | Never cut in half |
| Arguments | Model output parsed into the typed parameters. Bound parameters are filled from the session and never shown to the talker | Parsed into the draft model; then `validate` may reject it |
| Result | Data for the talker, and evidence for the guard's ID rule. With `reports_on=`, also evidence for claims about those actions | Recorded as a completed action. The outcome sentence is the `done` template filled from the result |
| What the talker may say about it | Anything the guard accepts | Never the outcome: the runtime speaks it. The talker's text after the call, in that turn, is dropped |
| Retries | The talker may call again, subject to the duplicate policy | Never blindly: a lookup by `request_id`, or "could not confirm" |

**What errors mean:**

| Raised in | Exception | Meaning | What happens |
| --- | --- | --- | --- |
| A tool | `ToolError(message)` | An expected failure | The talker gets the message |
| A tool | Anything else, or a timeout | A bug or an outage | The talker gets a generic "the tool failed", with no details. The exception type and stack go to the log at ERROR, without argument values. `ToolFinished(ok=False)` fires |
| `validate` | `ToolError(message)` | The draft is rejected before the read-back | The talker is told why |
| `execute` | `ActionRejected(reason)` | The backend refused: definitely not done | The `failed` template. The outbox row is marked rejected |
| `execute` | `ActionNotSent(reason)` | Failed before anything was sent: definitely not done | The `failed` template. The outbox row is marked not sent. No automatic retry in v1 |
| `execute` | Anything else, or a timeout | It may or may not have been done | `lookup(request_id)`: if found, `done`; otherwise `unknown`, with no number. The outbox row is flagged for reconciling |

**The fields of an action:**

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | no (the function's name) | The tool name the talker sees |
| `description` | yes | Shown to the talker. Write it in English even for Arabic agents: the earlier research found English tool descriptions called more reliably |
| The draft (the function's `draft` parameter type) | yes | A pydantic model, and the only schema the talker sees. A field named like consent is refused |
| `read_back` | yes | `ReadBack(templates, send_words=..., show_draft=True, max_attempts=2)`. Each template is a summary followed by a closing question. The receipt covers the summary |
| `consent` | no; `ReadBack` | The consent mode (table below) |
| `done` | yes | The outcome sentence, filled from the real result |
| `failed`, `unknown`, `declined` | no; library defaults | `failed`: definitely not done. `unknown`: no reply and no lookup hit. `declined`: the caller said no |
| `claims` | yes, in every declared language | Past-tense phrases that claim this action. The guard blocks them unless the record holds the action or a `reports_on` tool returned it |
| `validate` | no | `async (ctx, draft) -> draft`, or it raises `ToolError`. Checks the draft against the backend's own lists before the read-back |
| `lookup` | no | Finds a completed write by `request_id` (invariant 6) |
| `max_per_call` | no; 1 | Also capped per caller (M6) |
| `timeout_s` | no; 20 | After it, a lookup or `unknown` |

**Consent modes:**

| Mode | Consent | A yes spoken over the closing question | Available |
| --- | --- | --- | --- |
| `ReadBack` (the default) | The read-back's summary played in full without interruption (the receipt), then a yes from words heard through speech-to-text | Needs a send word, as in «نعم أرسلها». A bare «نعم» there is asked again (invariant 1) | v1 |
| Stricter levels (every yes needs a send word; the draft card always shown) | — | — | On request |

**The lifecycle the library runs.** No step belongs to the model:

```
talker calls open_request({...})
  -> the talker's further text in this turn is dropped              (guard rule C, section 8.2)
  -> parse into the draft model                    invalid: the talker is told which field
  -> validate(ctx, draft)                          rejected: the talker is told why
  -> caps (per call, per caller) and the duplicate check
  -> state CONFIRMING; the draft card is shown (show_draft)
  -> the runtime speaks the read-back rendered from the draft (a template; fixed values through their labels)
       summary played in full                      -> ReadBackReceipt        (built only by the voice session)
       yes words or listening sounds over it       -> ignored: the summary plays on, and they do not count
       other real words over it                    -> no receipt; the words go to the talker as a question
                                                      or a correction; the read-back plays again later
  -> heard words after the receipt                 -> the yes rule (section 8.3)
       built from speech-to-text, or from typed text only when env is "test"
       yes              -> ConfirmedAction (only the yes rule builds one)
                        -> outbox row with request_id, then a job outside the turn: execute(ctx, draft)
       no or correction -> the talker gets "declined: <heard words>" and may call again with a new draft
       unclear          -> asked again (a template), at most max_attempts times, then declined
  -> result     returned                       -> CompletedAction recorded; the runtime speaks `done`
                ActionRejected, ActionNotSent  -> `failed`
                any other exception, timeout   -> lookup(request_id): found -> `done`; otherwise `unknown`,
                                                  no number; the outbox row is flagged for reconciling
```

### 6.5 Identity and join tokens

- **One parameter.** `VoiceRuntime(identity=...)` takes exactly one identity source:
  - `SignedJoinTokens`: verifies tokens minted by the team's website or app. The Ole5 website mode and the sidecar use it.
  - `Authenticate(dependency)`: the runtime runs the team's FastAPI dependency at `/token` and mints the token with its own key. Built in the deployment's own plan (the roadmap's M6) only if Ole5 picks the one-time email code (open question 19, which plan 003's Q12 took to the deployment); otherwise on request.
  - `DevIdentity()`: a fixed dev caller, allowed only when `env` is `dev` and only for loopback clients.
- **No identity source.** `router()` and `serve()` raise a `ConfigurationError` with a FIX line. `t2v dev` alone falls back to `DevIdentity`, with a printed warning.
- **The `IdentityVerifier` port** has one method, `verify(token) -> (Caller, Consent)`. It runs once, at join, before the offer is answered.
- **`SignedJoinTokens`:**
  - **Format:** a compact JWT, HS256 only. There is no algorithm negotiation, so a token cannot choose its own algorithm.
  - **Claims:** `sub`, `name`, `locale`, `attrs`, `consent` (`version`, `record_audio`), `jti`, `iat`, `exp`, and a `kid` header.
  - **Keys:** a map from key ID to secret. Any listed key verifies, and `current_kid` signs. Rotating means adding a key, switching `current_kid`, then removing the old key.
  - **Single use:** the `UsedTokens` store rejects a second use of a `jti`.
  - **Lifetime:** 60 s by default, 120 s at most, with a configurable clock-skew allowance.
  - **Readable claims:** a JWT is signed, not encrypted, so the caller can read every claim. Claims never hold secrets or internal data; serving.md says so.
  - Website teams can mint tokens in any language with any JWT library, following the documented claims. `SignedJoinTokens.mint()` is the reference implementation in Python.
- **Consent version.** When `privacy.consent_version` is set, `/join` refuses a token whose consent version differs, with a notice. The version is stamped on the call's report and its traces.

### 6.6 Events and hooks

- **Events** (provisional). They are frozen, drawn from a closed list, and each carries `call_id`, `turn_id` and `at`:
  - Call: `CallStarted`, `CallEnded(report)`, `Busy`.
  - Speech and turns: `UserTurnEnded(heard)`, `Interrupted(kind: stop, correction, new_words, false; reason)`, `AgentSpeechEnded(text, played_fraction)`. An `Interrupted` comes for each overlap decided, of kind `false` when the reply went on; its `reason` is the rule's step that decided, none for the Stop button or Esc (D-061).
  - Tools and actions: `ToolStarted`, `ToolFinished(ok, ms)`, `ConfirmationRequested`, `ConfirmationAnswered(decision)`, `ActionCompleted`, `ActionUnconfirmed`.
  - Safety, errors and timing: `GuardBlocked(reason)`, `ProviderFailed(kind, retryable)`, `TransportFailed(stage)`, `TurnMetrics(ttfa_ms, stt_ms, llm_first_token_ms, tts_first_audio_ms)`.
- **Observers.** `@runtime.on(events.CallEnded)` registers one. Observers run off the call's path: queued, with a timeout. If one raises, the exception is logged and the call goes on. Observers cannot change behaviour.
- **`CallReport`** holds what was heard and said, the actions and tool calls, the timings, the usage per model, the consent version and the agent's fingerprint.
- **Hooks that change behaviour.** There are only two, both on the agent:
  - `on_call_start(ctx) -> CallStart | None`: a greeting, extra context, or tighter per-call options.
  - `on_call_end(ctx, report)`.
- **Deliberately absent:**
  - hooks that edit the model's input or output, which would let the guard and the yes rule be bypassed;
  - a hook that marks consent;
  - a raw Pipecat processor slot, which may come later as an escape hatch outside SemVer.

---

## 7. Configuration

### 7.1 What goes where

| Kind | Holds | Changed by |
| --- | --- | --- |
| The declaration (`VoiceAgent`) | What the use case means: instructions, languages, tools, actions, templates, labels, the base word lists, vocabulary, pronunciation | A code change, reviewed and versioned with the app |
| Settings (`VoiceSettings`) | How it runs in this deployment: environment, providers, models, voices, thresholds, limits, network, tracing, privacy, storage. Also additions to the word lists and vocabulary, for tuning | An environment variable, a file or code, with no code change |
| Per-call options (`CallOptions`) | Set by `on_call_start`, or by the identity source | They can only tighten: a shorter maximum length, fewer actions, a language preference |
| Recording consent | The caller's choice, carried only in the signed join token | The one per-call value that turns something on, and only when `privacy.record_audio` is on. No client message can set it |

Settings may add to the declaration's word lists. They never replace templates, tools or actions.

### 7.2 Layers and precedence

From lowest to highest precedence:
1. library defaults;
2. a TOML file, only if one is passed;
3. a `.env` file, only if `env_file=` is passed;
4. environment variables under the prefix, only inside `VoiceSettings.from_env()`;
5. code arguments;
6. per-call options, which can only tighten.

- The library reads the environment only inside `from_env()`. That is the library's own version of ARCH-ENV.
- Nothing is read at import, there is no settings singleton, and the library never reads a team's `.env` unless the team asks.
- `VoiceSettings(...)` built directly uses defaults and code arguments only, and `env` must be passed.

### 7.3 Naming and prefixes

- **Groups** are nested with `__`, for example `T2V_INTERRUPTIONS__MIN_WORDS=2`. Every timing or size setting has its unit in its name (`_ms`, `_s`, `_chars`).
- **The library's default prefix is `T2V_`** (open question 4). A team picks its own with `from_env(prefix=...)`. The prefix must belong to the library's settings alone. A team whose own settings use `HELPDESK_` picks `HELPDESK_VOICE_`, not `HELPDESK_`.
- **The Ole5 app** keeps `OLE5_VOICE_` for its own settings (environment, knowledge base, tickets) and uses `T2V_` for the library's. Its `core/config.py` stays the only module that reads the environment (ARCH-ENV in the app), and it builds both settings objects.
- **Secrets.** Each secret field `X` also accepts `X_FILE`, a path whose contents are the value.
- **Other names are never read.** If `GROQ_API_KEY` is set but `<PREFIX>GROQ__API_KEY` is not, the `ConfigurationError` names the variable to set. The library does not read the other one.

### 7.4 Validation

- **Type checks.** Pydantic types, ranges and enums apply to every field.
- **`env` is required.** It is one of `dev`, `test`, `staging` or `prod`, with no default. `t2v dev` refuses to run unless it is `dev`. `TextCall` and the testing fakes build their own settings with `test`. `router()` and `serve()` refuse `test`, so typed consent can never reach a served runtime.
- **Unknown keys.** A key in the TOML file that matches no field is an error. So is an environment variable that carries the prefix but matches no field, raised at `from_env()`, so a typo never falls back silently to a default. The error says that the prefix must belong to the library alone. `from_env(unknown="warn")` turns it into a warning.
- **Cross-checks at runtime construction.** There must be a TTS model and voice for every agent language, and each model's `max_chars` must suit the templates. There must be an identity source before serving (section 6.5).
- **Provider checks at `lifespan` start**, behind `startup_checks=true`: each language passes `check_language`, and each model is reachable with the key.
- **Outside `dev`**, the library refuses `server.dev_page=true`, `DevIdentity` and `logging.content=true`. Ole5's `api/status.py` already refuses DEBUG in production.
- **Every failure** is a `ConfigurationError` with a FIX line. `t2v check` and the `/health` payload show the environment in force.

### 7.5 Secrets

- The Groq key, the join keys, the TURN secret and every adapter credential are `SecretStr`. The offer secret is generated per call and treated the same way.
- They never appear in a repr, a log, a trace, an event, an error body or the browser (except the offer secret, which goes only to the browser that joined).
- A library test asserts this (invariant 5). `testing.assert_no_secret_leaks(runtime)` gives teams the same check for their own wiring.

### 7.6 Settings groups

The defaults below are the agent's starting values, to be measured in the milestone named in each row. Each move of a default is a behavior change (section 5.4).

| Group | Main keys (default) | Measured or decided in |
| --- | --- | --- |
| top level | `env` (required) | — |
| `groq` | `api_key` (required for Groq adapters), `api_key_file`, `base_url`, `timeout_s` | — |
| `stt` | `provider` (groq), `model` (`whisper-large-v3`, chosen by the M1 baseline: D-025), `timeout_s` (6), `no_speech_max` (0.55) and `caption_filter` (true), the filter for text from silence (D-063, D-068) | M1, M3 |
| `llm` | `provider` (groq), `model` (openai/gpt-oss-120b), `reasoning_effort` (medium: D-074), `max_output_tokens`, `timeout_s` (8), `vary_first_line` (true: D-072) | M4 |
| `tts` | `provider` (groq), `languages` (a map from language to `{model, voice}`; models `canopylabs/orpheus-arabic-saudi` and `canopylabs/orpheus-v1-english`; voices chosen in M2), `timeout_s`, `cache_phrases` (true) | M2 |
| `turns` | `vad_confidence`, `vad_start_ms`, `vad_stop_ms` (200), `smart_turn` (true), `smart_turn_threshold` (0.5), `complete_hold_ms` (600, the hold after Smart Turn's "complete": D-067), `max_silence_ms` (fallback end of turn) | M2, M3 |
| `interruptions` | `mode` (two_step, by the owner's ruling: D-068; or drop), `duck_level` (0.25), `first_window_ms` (750), `min_words` (2), `short_words` (2), `short_s` (1.2), `own_words_s` (5) (D-061) | M3 (from the M1 overlap data) |
| `words` | `stop`, `wait`, `repeat`, `backchannel`, `no` (M3, D-062); `yes`, `send`, `vocabulary`: additions to the declaration | M3 to M5 |
| `guard` | `id_patterns` ([]), `min_id_digits` (3), `on_block` (`drop_rest`; or `drop_clause`) | M4, M5 |
| `limits` | `max_call_s` (600), `idle_s`, `max_live_calls`, `max_live_calls_per_caller` (1), `calls_per_caller_per_day`, `max_abandoned_threads` | M6 |
| `server` | `public_url`, `allowed_origins` ([]), `ice_servers` ([]), `turn_secret`, `turn_ttl_s`, `dev_page` (false), `drain_timeout_s` | M2, M6 |
| `join` | `keys` (a key-ID-to-secret map), `keys_file`, `current_kid`, `ttl_s` (60), `max_clock_skew_s` (30) | M2 |
| `tracing` | `endpoint` (none), `project`, `include_transcripts` (true), `redact` ([]) | M1 |
| `privacy` | `record_audio` (false), `consent_version` (none) | M2 |
| `logging` | `content` (false), `pipecat` (`off`; or `forward`) | M2 |
| `storage` | `var_dir` (var) | — |

*Built so far (M1, plan 002; plan 003's step 7; plan 005):* `env`, required, and the groups `groq`, `stt`, `tts`, `turns`, `interruptions`, `server`, `join`, `tracing`, `privacy`, `logging` and `storage`, with `limits`' `max_call_s` and `idle_s`, and `words`' `stop`, `wait`, `repeat`, `backchannel` and `no`; `llm`, `guard`, the rest of `limits` and of `words`, and `server.drain_timeout_s` come in the milestones their rows name. M3 (plan 005) added the `interruptions` and `words` keys, `stt.no_speech_max` and `stt.caption_filter`, and `turns.smart_turn_threshold` and `turns.complete_hold_ms`, each in its row above. `groq` has no `timeout_s` (the timeouts are `stt.timeout_s` and `tts.timeout_s`). M2 adds keys this table does not list: `stt.live_language`, `tts.trim_silence`, `turns.vad_min_volume` and the Smart Turn keys, a `session` group (`mode`, `echo` until the talker), `server.turn_secret_file` and `server.forwarded_allow_ips`, and `logging.level` and `logging.format`, top-level keys in M1; M1's `T2V_VAR_DIR` is `storage.var_dir`, refused under its old name with the new one. Every key, its default and its unit are in [the settings reference](../generated/settings.md).

### 7.7 The generated reference

- A script generates `docs/guide/reference/settings.md` (section 14) and `.env.example` from the model. For each field they give the environment name, type, default, unit and description, and a test fails when either is stale.
- `t2v settings show --redacted` prints every value and its source: default, file, `.env`, environment or code.
- `t2v check` prints the defaults in force, so nothing differs silently between environments.

---

## 8. Guarantees

### 8.1 What the library enforces for every use case

Ole5's invariants (docs/SECURITY.md) are generalized from tickets to any action. The library's SECURITY.md becomes the **one invariants register**, with the same numbers 1 to 8. The app's SECURITY.md keeps Ole5's threat model and cites them; a rule that only the app has is cited as "app invariant N" (section 12.4). The guarantees live in runtime code paths and types, not in the team's CI, so they hold for teams that never run Ole5's harness. The harness rules guard the library's own code.

| Invariant | What the library enforces, and how | What stays the app's |
| --- | --- | --- |
| 1. No action without consent heard from the caller | The talker's schema holds only the draft. The read-back is a template filled from the draft. Heard words are built only by the voice session, from speech-to-text results, and carry their source. Read-back receipts are built only by the voice session, from the transport's playback reports. The yes rule is the only thing that builds a `ConfirmedAction`, and the action runner accepts nothing else. Consent built from typed text reaches `execute` only when `env` is `test`, and serving refuses `test`. No public constructor or parameter accepts consent. These classes are `[[restricted]]` in the library's harness. Adversarial tests run in the library, and `ActionSafetySuite` runs the same cases on each team's actions. A handoff is an action like any other (open question 6) | Templates that state every field that matters, truthfully. Spoken labels callers understand. Its own word additions |
| 2. No claim without a record | Outcome sentences come only from `done` templates filled from real results. The guard applies rules A to C (section 8.2) to every clause before TTS, and to model-written text shown on screen. A status result counts only from a tool declared with `reports_on=`. Simulated calls count violations, and the check runs in every `TextCall` | Claim phrases that cover how its domain talks ("submitted" against "approved"). `reports_on=` on its status tools. Tool results that carry only true data |
| 3. Identity comes from the session | The `Caller` is fixed at join. `ctx.caller` is read-only, and nothing said in the call changes it. `bind=from_caller(...)` fills identity parameters from the session and hides them from the talker. `t2v check` warns about identity-like parameters left unbound | A correct identity source. Tools that scope data by `ctx.caller`, never by an argument |
| 4. Model output is parsed | Every tool and action argument is parsed into pydantic types, and invalid values go back to the talker with the field named. `Literal` types and enums fix value sets, and `validate` checks against the backend's lists. Tool results and passages are framed as data in the prompt | Fixed sets that match its backend. No tool that executes instructions found in text |
| 5. Secrets stay in the backend | Section 7.5. Join-token claims are documented as readable by the caller | Its own secrets; no secrets in token claims; tool results that return none |
| 6. Writes are never cut in half | An outbox row with the `request_id` is written before `execute`. The write runs as a job outside the turn and is never repeated blindly. Every exception has a defined meaning (section 6.4). A lookup, the `unknown` template, `t2v outbox list` and `t2v outbox reconcile`. At startup, rows left "sending" are looked up or flagged, never re-sent | Idempotency in its backend, keyed on `request_id` (advised). A lookup where possible. A person who reconciles flagged rows |
| 7. Join tokens are single-use and short-lived | Mint and verify, the `jti` store, a lifetime, a clock-skew allowance, a key map. A per-call offer secret, so the call ID is never a credential. A lock file, so a second process cannot share the used-token store on one host | Minting only for signed-in users. A rate limit on its minting endpoint. One process per `var_dir` |
| 8. Audio is kept only with consent | No audio is written unless `privacy.record_audio` is on and the signed join token carries the caller's recording consent. Audio is never exported to traces. Call content is not logged at any level unless `logging.content` is on, which only `dev` allows. Pipecat's loguru namespace is disabled by default, and a test checks that a Pipecat debug line holding a transcript reaches no output | The consent wording and its version. Retention in its own Phoenix. Deletion requests |

### 8.2 How the output guard decides

The guard checks each clause before it goes to TTS.

**First, it normalizes the clause:**
- the canonical Arabic normalizer;
- Arabic-Indic (٠–٩) and Persian (۰–۹) digits mapped to ASCII digits;
- runs of digit words in Arabic and English («أربعة خمسة اثنين واحد», "four five two one") collapsed into digits.

The prompt tells the talker to write numbers as digits. The speaking rules turn digits into words after the guard, so the guard sees digits.

**Rule A, claims.** A clause that contains a claim phrase of action A passes only if one of these holds:
- the call's record holds a completed A; or
- a tool declared with `reports_on=["A"]` returned a result in this call.

Every ID-shaped token in that clause must also equal a value in that completed A's result, or in that status tool's result. Claim phrases come from each action's `claims`, plus a short default list per language ("I've created", «تم إنشاء», «سجلت لك» and the like), which counts as a claim about any action. Teams can extend or replace the default list. Matching runs on normalized text, on word boundaries.

**Rule B, IDs.** In a clause with no claim phrase, every ID-shaped token must appear in the call's record, in a tool result from this call (passages included), or in the caller's own heard words.
- "ID-shaped" means a run of `guard.min_id_digits` (3) or more digits after normalization, or a match of a declared pattern: `guard.id_patterns`, and the `pattern` constraints of draft and result fields.
- The current year and the next one are exempt, because the prompt holds the current date.
- So a number from a knowledge-base passage may be spoken as a fact, but never as a request number (rule A).

**Rule C, after an action call.** Once the talker calls an action in a turn, its further text in that turn is dropped. Only the runtime's templates speak until the outcome has been spoken.

**Templates are not checked.** The runtime's own templates are exempt from rules A and B: greetings, read-backs, `done`, `failed`, `unknown`, `declined`, progress lines and fixed phrases. Their values come from the draft, read back so that the caller can check them, or from the real result.

**When a clause is blocked:**
- that clause and the rest of the reply are dropped (`guard.on_block="drop_rest"`), or only that clause (`"drop_clause"`);
- the runtime speaks a fixed phrase in the reply language;
- the talker's history gets a developer note;
- a `GuardBlocked` event is traced.

False positives cost a sentence. They show up in traces for review. `t2v check` prints the effective lexicon.

### 8.3 How the yes rule decides

The rule looks only at heard words that came after the receipt, normalized. In a served runtime they come from speech-to-text.
- **After the closing question has finished:** a yes word, with no content beyond send words and fillers, is a **yes**.
- **Over the closing question:** a yes needs a send word. A bare yes there is **asked again** (invariant 1).
- A no word is **declined**.
- Other content words are a **correction**, which goes to the talker.
- Nothing heard is **asked again**.

Yes words and listening sounds spoken over the summary are ignored and do not count (section 6.4). The send words are the language preset's plus the action's own `send_words`. `t2v check` warns when no word of an action's closing question is among its effective send words. «نعم بس غيّر العنوان» is therefore a correction, never a yes.

### 8.4 What the library does not guarantee

- That a read tool does not write.
- That the team's backend honours idempotency.
- That the templates describe what `execute` really does.
- That the guard catches every claim. It is lexical: a paraphrase that is in no claim list («رفعت طلبك», «خلصت الموضوع») passes. The backstops are rule C, the hard check `no_unrecorded_claims` in simulated calls, and review of traces. Teams extend their lexicon from what simulated calls find.
- The correctness of answers (knowledge-base content), the model's quality, or speech-to-text accuracy.
- Resistance to injected instructions beyond limiting the damage. A hidden instruction in a passage can still steer what the talker says, but it cannot make it act or claim an action.
- The privacy of join-token claims, which the caller can read.
- Compliance with PDPL, the consent text, or the retention policy.

---

## 9. Testing kit for teammates

### 9.1 Fakes

| Fake | Behaviour |
| --- | --- |
| `ScriptedLLM` | A list with one entry per model request, each a list of events (`call_tool`, `reply`). One caller turn that uses a read tool makes two requests. When the script runs out, it fails clearly and prints the log of requests so far, with the last user text |
| `FunctionLLM(fn)` | A custom fake model, for example one that answers by matching the last user text or tool result, so a test does not depend on the number of requests |
| `FakeSTT` | Clips tagged with their text, or a map from clip to text |
| `FakeTTS` | Records texts; `chars_per_second` sets the playback timing |
| `MemoryOutbox`, `MemoryUsedTokens` | In-memory stores |
| `VirtualClock` | Time advances only when the test says so |
| `failing(provider, Fail429(retry_after_s=20))`, `Hang()`, `Timeout()` | Provider failures, for M6 tests |

### 9.2 `TextCall`

`TextCall` runs the real voice session through a text transport, together with the real talker, actions, yes rule, guard and outbox (in memory by default). It needs no key and no network, never starts Pipecat, and is deterministic. It always runs with `env="test"`, which is the only place typed text can stand in for heard words. It is not a chat channel, and testing.md says so.

- **Playback.** The read-back counts as fully played unless the test says otherwise.
- **Injection:**
  - `call.user(text, during="read_back" | "closing_question" | "agent_speaking")`;
  - `call.user(text, at="tool_running")`;
  - `call.advance(seconds)`;
  - `call.stop()`.
- **Expectations:** `turn.expect.tool_call(name, **args)`, `.read_back(contains=)`, `.asked_again()`, `.action_completed(name)`, `.no_action()`, `.said(contains=)`, `.blocked()`, `.cancelled(tool)`, `.language("ar-SA")`.
- **`call.violations`** holds the guard and yes-rule checks. They run automatically in every call.

### 9.3 The adversarial suite

`ActionSafetySuite` is a pytest base class. A team subclasses it with its agent, its action, a sample draft and fake dependencies. It runs these cases:
- a yes spoken over the read-back's summary;
- an eager yes before the read-back;
- a bare yes over the closing question;
- a tool call whose arguments claim consent;
- model text that claims the action is done;
- model text after the action call in the same turn;
- a status answer from a `reports_on` tool, which must not be blocked;
- a passage carrying a fake request number, which must not be spoken in a claim;
- an ID spelled out in digit words or written in Arabic-Indic digits;
- the backend times out and the lookup finds the write;
- the backend times out and there is no lookup;
- `ActionRejected` and `ActionNotSent`;
- the same `request_id` arrives twice;
- the per-call cap is reached.

### 9.4 Simulated callers (opt-in, live; provisional)

- `simulate(agent, scenarios=..., providers=..., repeats=5)` runs scenarios with `SimulatedCaller(persona, language, llm)` and hard checks: `no_unrecorded_claims` and `no_action_without_yes`.
- Groq plays the simulated caller and the judge.
- It reports tool accuracy and false claims over the repeats, and the noise rules of evaluation.md apply to its results.
- These tests are marked `t2v_live` and deselected by default.

### 9.5 Audio replay (provisional)

`AudioCall` runs the real media pipeline on a transport fed from files, with no WebRTC: VAD, Smart Turn and the two-step interruption. It uses `FakeSTT` or a real provider.
- It plays a golden WAV file over a reply, the reply played as the file-fed call's greeting, and reports each overlap's verdict, its Whisper requests and the time from a marked word end to the last agent audio frame sent. How often the caller is cut off is measured by `turn_ends`, on the same file-fed pipeline.
- Built in M3 (plan 005), in `testing/audio_call.py`, and reached through the `evals` facade until the testing kit is public with `TextCall` (M4). Ole5's `poe overlap` runs it.
- **The parity test** in the library's CI runs the same scripted call through `TextCall` and `AudioCall` and requires the same sequence of session events. It proves that text mode tests the same consent path as a real call. It moved to M4 with `TextCall`, which it needs (plan 005).

### 9.6 Provider tests

The Groq adapters' tests in the library's CI check shapes, cancellation, errors, `max_chars` and that no secret appears in a repr. The live part is opt-in. Contract suites that other authors can subclass come when a teammate writes an adapter (section 3.1).

### 9.7 Evaluation helpers (provisional)

The prototype's scorer is ported to the library as functions, as D-010 allows:
- the canonical Arabic normalizer (in `languages`);
- `wer` and `cer`, after that normalization;
- `term_recall` and `id_recall`, for product terms and IDs;
- `silence_output`: text produced from silence or from the agent's own echo;
- `sign_test`: the paired sign test by item from evaluation.md.

Ole5's golden-set machinery stays in the app, under `apps/ole5-voice-agent/evals` with its poe tasks, exactly as evaluation.md defines it: `poe golden`, `poe eval`, `poe eval-compare`, item validation, frozen answers, splits, held-out aggregates and `history.jsonl`. A `t2v eval` CLI comes when a second team records a golden set.

**Golden data stays in each team's repository, and its audio stays out of git.** Ole5's golden set (the owner's voice, D-006) keeps only items, references, manifests and file hashes in `evals/`. The audio lives under the git-ignored `var/` or in a private store. A CI check fails if an audio file is committed under `apps/`. The library's published numbers say "one speaker" while D-006 holds.

*Built in M1 (plan 002, D-022):* the scorers' pure parts and the sign test in `domain`, and `wer` and `cer` in `testing`, behind the `evals` facade; the normalizers and the spelling-guide check (`spelling_issues`) behind `languages`. Proposed in D-022, for the owner to rule on: the golden-set code in `apps/ole5-voice-agent/src/ole5_voice/evals/`, with its data in `apps/ole5-voice-agent/evals/`, and the check that no audio is committed as a test inside `poe check` (`tests/ole5_voice/evals/test_no_audio.py`, over `apps/`, `packages/`, `examples/`, `docs/` and `tests/`) until CI runs (TD-001).

### 9.8 `examples/minimal` as a test of the core

`examples/minimal` is a workspace member with its own `pyproject.toml`. It depends only on `t2-agentic-voice` and is banned from importing internals (section 12.5). CI runs:
1. its text-mode tests in English and Saudi Arabic, with no key;
2. `t2v check` on its agent;
3. from M2, a **torch check**: the resolved install must not contain torch;
4. from the first teammate tag, a **wheel job**: CI builds the library wheel and installs it into a fresh environment outside the workspace, then imports it, runs `t2v check`, starts `serve()` and requests `/health`, which proves the packaging;
5. an opt-in live smoke test with a key, run by hand or on a schedule.

---

## 10. Observability and operations

### 10.1 Tracing

- **Packages and providers.** The OpenTelemetry API, SDK and OTLP exporter are part of the one install.
  - The library uses the team's `TracerProvider` if one is given. Otherwise it builds a private one from `tracing.endpoint`.
  - It never calls `set_tracer_provider` and never instruments other libraries: no LangChain instrumentor, and Pipecat's own tracing is off.
  - Plain OTLP goes to Phoenix by default, and to any OpenTelemetry backend if the team points it elsewhere.
- **One trace per turn.** Phoenix groups a call's traces through `session.id`, which is set to the call ID. The call ID is not a credential (section 5.5).
- **Spans**, following OpenInference conventions:
  - the turn;
  - speech-to-text (audio seconds, billed seconds, model, language);
  - the model (tokens, time to first token);
  - each tool (arguments and results after redaction);
  - the guard's decisions;
  - confirmation (read-back, receipt, decision);
  - text-to-speech (characters, chunks, requests, time to first audio, cache hits).
- **Resource attributes:** the library version, the Pipecat version, a digest of the settings, the agent's fingerprint and version, the model IDs, and the consent version.
- **Redaction and content:**
  - The redaction hook runs on every text attribute.
  - `include_transcripts` is on by default, because invariant 8 keeps what was said in traces as the only call content stored by default: the transcript, the agent's replies and the arguments the model wrote for a tool (D-079).
  - Audio and secrets, the offer secret included, are never exported.
- **Exporter failures never touch a call.** The batch processor has a bounded queue and short timeouts, and dropped spans are counted.
- **Explicit spans.** The span helpers take the turn's span as an argument, because an implicit current span does not cross Pipecat's tasks (ARCHITECTURE.md).
- **The tracing path:** the library's own spans, in OpenInference's format, not Pipecat's OpenInference instrumentor (D-018, answer 7), sent as plain OTLP through the OpenTelemetry SDK (D-023).

### 10.2 Logs

*Built in plan 003's step 8, with one reading:* a message's key-value fields travel in one `extra` key, `fields` (`record.fields`), since the standard library refuses an `extra` key named like one of a record's own attributes, and the Ole5 app's events use `name` and `message`. Pipecat's lines (section 12.2) come with plan 003's Track E.

- The library logs through the standard library, under `t2_agentic_voice.*`, with a `NullHandler`. Messages are snake_case event names with key-value `extra` fields.
- It never calls `basicConfig` and never adds handlers to the root logger.
- **INFO and above carry no call content:** only IDs, timings and outcomes. Content appears only with `logging.content=true`, at DEBUG, and only `dev` allows that setting.
- **Pipecat logs through loguru,** a process-wide logger:
  - The default, `logging.pipecat="off"`, calls `loguru.logger.disable("pipecat")` at runtime start. This is loguru's switch for one namespace; no sink is added or removed.
  - `"forward"` re-enables the namespace and adds a sink that forwards Pipecat's WARNING and above to `t2_agentic_voice.pipecat`. If the team's own loguru default sink is still installed, it also prints Pipecat's lower-level lines, which may hold call content; the logging docs say so, and recommend `forward` only where that sink is removed.
  - With Pipecat's logs off, failures are still visible: the `voice` layer turns Pipecat's error frames, transport and ICE failures, and processor exceptions into library log lines (with no call content) and `TransportFailed` or `ProviderFailed` events.
  - This is the library's one global touch. It is limited to the `pipecat` namespace, which the contract reserves to the library.

### 10.3 Latency

- **Time to first useful audio** is measured from the true end of the caller's speech to the first agent audio frame. The server measures it, and the browser reports when that audio actually played (`client_stats`). Progress lines are counted apart.
- **The latency page** gives a budget per stage:
  - the VAD stop delay (a setting);
  - the Smart Turn decision;
  - Whisper on the finished segment (there are no partial transcripts);
  - the talker's first token;
  - the first clause ready;
  - Orpheus's first byte;
  - the network to the browser.
- **No target is set yet.** M4's plan registers its target before any run, as the roadmap requires. Known so far: Whisper large-v3's request took a median of 323 and 271 ms on the golden set's dev split (plan 002's runs R1 and R3). In the owner's recorded session, over 26 turns (plan 003, step 18, 2026-11-04), the medians were: from the end of speech to the transcript 542 ms in Saudi Arabic and 568 ms in English (236 ms to the turn closed, the VAD stop and Smart Turn's decision together, then 311 ms to the transcript); to the echo's first audio queued about 555 ms; and from the echo's Orpheus request to its first audio about 188 ms. The caller heard the echo about 0.8 to 1.2 s after their speech ended, since its audio leads with silence (TD-090). The prototype took 12–43 s per knowledge answer (DESCRIPTION.md).

### 10.4 Usage, cost and rate limits

- **Usage per call and per model**, on spans and in the `CallReport`:
  - requests;
  - audio seconds sent and billed (Groq bills at least 10 s per transcription request: checked);
  - input and output tokens;
  - TTS characters, requests and cache hits.
- **Cost.** The library holds no prices. A price table and a daily budget are on request (section 3.1).
- **Rate limits:**
  - One limiter per model, shared by every runtime in the process, keyed by provider, key fingerprint and model, and sized from settings: the app's share of T2's one shared key (open question 11).
  - It honours `retry-after` (set only on a 429) and the `x-ratelimit-limit-*`, `x-ratelimit-remaining-*` and `x-ratelimit-reset-*` headers for requests and tokens (checked).
  - Repeated 429s start a short cool-off, during which new calls are refused with a busy notice.
  - The spoken fallback plays a cached phrase, so it works even when TTS itself is rate-limited.
- **Groq's published limits are low.** Groq's rate-limits page, read on 31 Oct, lists:
  - 10 requests a minute, 100 a day and 3.6K tokens a day for each Orpheus model;
  - 20 requests a minute for each Whisper model;
  - 30 requests a minute for `openai/gpt-oss-120b`.

  One read of the page described these as the Developer plan's base limits; another read found the plan unclear. The prototype's key was on Groq's on-demand tier at 400 requests a minute (roadmap, M6). Clause-by-clause synthesis at 100 TTS requests a day would carry only a few calls. So M2 counted requests per call minute per model in the owner's recorded session (open question 21, D-040). Reading the key's real limits in the console became optional in M2 (plan 003's Q17), and the owner has not read them; Groq's rate-limit headers show daily limits far above the published ones but no limits a minute, so the published limits a minute stay the bound (D-040).
- **TTS caching.** `lifespan` renders the fixed phrases once (greetings, progress lines, fallbacks, the yes-rule prompts) and caches them under `var_dir`, keyed by a hash of the text, model and voice. Rendered templates and talker clauses that repeat exactly are cached the same way.
- **How many calls one key carries** (M6) comes from those counts. The cap on live calls is set below the app's share of the key's limit.

### 10.5 Health, readiness and drain

- **`/health`** is liveness. Its body also shows the environment, the live-call count against the cap, and whether a provider cool-off is active.
- **`/ready`** reflects only startup and drain. It is false until `lifespan` has finished its checks, and false while the process drains. The call cap and a provider cool-off do not change it, because taking the only instance out of a load balancer would also break live calls' ICE updates and hangups.
- **Admission control.** At the cap or during a cool-off, `/join` (and `/token`) answer with a busy notice in the caller's language.
- **Drain** starts on shutdown (SIGTERM, through the lifespan):
  - readiness turns false;
  - new joins get a busy notice;
  - live calls run until `server.drain_timeout_s`;
  - outbox jobs finish or stay pending durably.
- **Prometheus `/metrics`** is on request (section 3.1). Until then, the operator reads usage, outcomes, guard blocks, outbox state and time to first audio from the traces and the call reports.

### 10.6 The CLI

| v1 | Later or on request |
| --- | --- |
| `t2v check APP` (validate; print the card, prompts, word lists, lexicon, data flows and settings, redacted) | `t2v chat APP` (on request: a typed conversation through the real talker, always dry-run: `execute` is replaced by a recorder; refuses `env=prod`) |
| `t2v dev APP` (dev server, dev page, reload; `env=dev` only) | `t2v eval ...` (when a second team records a golden set) |
| `t2v serve APP` (the sidecar: one worker) | `t2v probe URL` (a headless aiortc client that plays a WAV file into a deployed backend) |
| `t2v doctor` (M2: key, models, each language's model and voice with access and terms, model-weight checksums, clock skew; M6 adds TURN allocation and an OTLP test span). It cannot check Groq's Zero Data Retention setting, and says so | `t2v loadtest --fake-providers`, `t2v usage --since 24h` |
| `t2v settings show --redacted` | `t2v purge`, `t2v dsr find` and `t2v dsr delete` |
| `t2v outbox list`, `show` and `reconcile` | `t2v upgrade-check`, `t2v console APP`, `t2v dataflow --format md` |

---

## 11. Deployment requirements

| Requirement | v1 |
| --- | --- |
| Python | CPython 3.12 or later, for the library and the app alike. A uv workspace resolves one `requires-python` for all members (uv docs, checked by a reviewer), and the harness's coverage setting `core = "sysmon"` needs 3.12 (harness.toml). Pipecat 1.15.0 itself supports 3.11 and later (checked), so the floor can be lowered when a real teammate needs it (open question 3) |
| OS and CPU | Production on Linux x86_64. Development on macOS arm64 and Windows x64, if the pinned aiortc, PyAV and onnxruntime wheels exist (**verify** at the pin; the owner develops on Windows). CPU only, with no torch |
| Model weights | Silero VAD (`silero_vad.onnx`) and Smart Turn v3.2 (`smart-turn-v3.2-cpu.onnx`) ship inside the pipecat-ai 1.15.0 wheel, which is 12.2 MB (checked). Nothing is downloaded at runtime. `t2v doctor` checks their sha256 |
| Process model | One process per `var_dir`, with one worker, because the peer connection, ICE state and call session live in that process's memory. A service with several workers or replicas runs the runtime as a sidecar (section 4.5). Its outbox and used-token store are local SQLite, so a second process would break single-use tokens and the per-caller caps (invariants 6 and 7): the lock file stops one on the same host, and the docs forbid one on another host. Several instances need shared stores (later) and session affinity from join to the end of the call |
| HTTPS | Required for the microphone outside localhost. TLS ends at the team's reverse proxy |
| WebRTC media | See below |
| Groq | A key. The terms accepted for each Orpheus model used. Both Orpheus models are previews, under 200 characters per request (checked). The key's real rate limits read and recorded (section 10.4). A spend limit set in the console (the team's choice) |
| Groq data | Groq's "Your Data" page says (checked): by default Groq does not retain customer data from inference requests; it may keep logs for reliability or abuse checks for up to 30 days, which a customer can opt out of in Data Controls; Zero Data Retention can be turned on by any customer; data Groq does retain is held in Google Cloud buckets in the United States. The page does not say where requests are processed. The 28 Oct research's line that Groq "stores customer data in US GCP buckets" holds only for retained data. The library sets no requirement here: the owner explains Groq's terms to each team that adopts the library, and each team decides for its own data (open question 10) |
| Storage | `var_dir` on a persistent volume, holding the lock file, `outbox.db`, `used_tokens.db` and the phrase cache, one folder per agent. Recordings are stored there only if they are enabled |
| Phoenix | A small service with auth on, a persistent volume and no public exposure. The Elastic License 2.0 allows running it inside T2, but not offering it as a service |
| CPU per call | Not measured yet. M6 measures it with fake providers on a named machine, and the deployment guide publishes the number |

**WebRTC networking:**
- **The media path.** The browser sends audio over UDP to the backend's ICE candidates.
  - On localhost and on the same network, this works with no other server.
  - From other networks, the backend needs either a public address with a UDP range open, or a TURN relay.
- **Networks that pass only TCP 443**, as many corporate networks do, need TURN over TLS on 443 (`turns:` URLs). coturn (BSD-3) runs as a small service. It needs its own hostname and IP, or SNI routing, because port 443 on the host already serves the website.
- **TURN credentials.** If the network test in the deployment's own plan (the roadmap's M6) shows TURN is needed, the library mints them per call from the shared secret, using coturn's REST scheme, and returns them in the join response. They expire with the call's lifetime. Otherwise `server.ice_servers` stays static.
- **TURN beside the backend.** When coturn runs on the same host as the backend, the backend may need no public UDP at all: the browser reaches coturn over 443, and coturn relays to the backend locally. coturn must be configured to allow the backend's address as a peer (**verify** in the deployment's own plan, the roadmap's M6).
- **Docker.** Run the backend with host networking, or advertise the host's public IP. A hypothesis for the deployment's own plan (the roadmap's M6) to test: aiortc behind Docker's NAT advertises container addresses.
- **UDP port range.** Whether aiortc can pin its UDP port range is not known (**verify**). If it cannot, "open a UDP range" means opening the whole ephemeral range, and TURN becomes the practical path.
- **Diagnosis.** The reference client reports the selected candidate type (host, srflx or relay) and the time to connect, so a failed call shows whether the network or the agent failed.
- **For Ole5**, the network test in the deployment's own plan (the roadmap's M6) decides the media path, and the deployment guide publishes the measured outcome.

**What runs where (D-005):**

| Where | What |
| --- | --- |
| The website (the owner's) | The page with the client; for Ole5, the server that mints join tokens, if open question 19 picks (a) |
| The backend host | One container: the team's FastAPI app with the library (one worker), or the app plus a sidecar; and the `var_dir` volume |
| Small services on the host | coturn (if the deployment's network test needs it, the roadmap's M6) and Phoenix |
| Outside the host | Groq (data retained in the US), and the team's own systems. For Ole5 these are T2's Qdrant at ds.t2.sa and the T2 Ticket API |
| Not needed | A GPU, a model server, a media server, LiveKit or Pipecat Cloud, Prometheus, any download at runtime, any phone-home |

**Outbound hosts:** api.groq.com, the OTLP endpoint, the TURN service, and the team's own systems. The library contacts nothing else.

---

## 12. Repository and package layout

### 12.1 The workspace

The layout built in plan 001, with the files this design adds; each lands with its milestone (section 16):

```
t2-agentic-voice/                     the repository (renamed from Ole5-voice-agent on 2026-11-01, open question 13)
  pyproject.toml                      uv workspace root (not a package): members, dev tools, poe tasks
  uv.lock                             one lock for every member; one requires-python (>=3.12)
  harness.toml                        the rules for every member: the library's layers, [package] public, [[apps]]
  tests/                              one folder per package, and harness/ for the checks' own tests
  CLAUDE.md  ARCHITECTURE.md  WORKING-RULES.md
  docs/                               the project's record: plans, roadmap, decisions, harness docs
  packages/t2-agentic-voice/
    pyproject.toml                    distribution t2-agentic-voice; no extras (open question 2); requires-python
    README.md                         CHANGELOG.md  SUPPORT.md  CONTRIBUTING.md  THIRD_PARTY_NOTICES.md (proposed)
    src/t2_agentic_voice/
      __init__.py ports.py events.py languages.py knowledge.py identity.py stores.py
      groq.py server.py tracing.py evals.py              public facades (re-exports only)
      core/ domain/ adapters/ actions/ agent/ voice/ testing/ api/     the layers
      api/static/t2v-client.js  api/static/dev.html      served by the router; shipped in the wheel
  apps/ole5-voice-agent/
    pyproject.toml                    t2-agentic-voice from the workspace
    src/ole5_voice/                   today one package; core/ domain/ adapters/ agent/ api/ (proposed, 12.3)
    web/                              the Ole5 widget, built on t2v-client.js
    evals/                            items, references, manifests and hashes (D-006, D-011); no audio; never shipped
  examples/minimal/
    pyproject.toml  src/minimal_example/   (app.py of section 4.2 when the API exists)
  docs/guide/                         the teammate guide (section 14)
```

The golden set's audio lives under the git-ignored `var/` or in a private store, never in git (section 9.7).

### 12.2 The library's layers

| Layer | Responsibility | May import | Owns |
| --- | --- | --- | --- |
| `core` | The settings model (the environment is read only inside `from_env`), logging helpers on the standard library, errors with stable codes, tracing helpers (OpenTelemetry API), shared types | none | `pydantic_settings`, `opentelemetry`, `openinference` |
| `domain` | Pure rules, with no IO: the yes rule, the interruption rule, the guard's rules and digit normalization, templates, labels and speaking, Arabic normalization, the choice of reply language, the clause splitter, the declaration types, the evaluation scorers' pure parts, and the ports | `core` | `num2words` |
| `adapters` | The Groq adapters, the SQLite stores, signed join tokens, TURN credential minting | `core`, `domain` | `groq`, `sqlite3`, `jwt` |
| `actions` | The tool runner (async and threaded), the action lifecycle, outbox jobs, the per-call record, per-call caps | `core`, `domain` | — |
| `agent` | The talker: prompt composition; one turn from heard words to a reply and tool calls; the reply language; the guard applied per clause; the confirmation sub-flow, which calls the yes rule | `core`, `domain`, `actions` | — |
| `voice` | The call session: turn order, cancel scopes, heard words (with their source) and read-back receipts, playback bookkeeping, heard history, the two-step interruption flow, per-call limits, the text transport. And Pipecat, in modules of its own: the pipeline, SmallWebRTC, Silero, Smart Turn, the STT and TTS bridges, the session bridge, the file-fed transport; they map Pipecat events to session events, carry out the session's commands, turn Pipecat errors into library events, and hold the loguru policy. The session's modules never import Pipecat | `core`, `domain`, `agent` | `pipecat`, `loguru` |
| `testing` (new, public) | Fakes, `TextCall`, `AudioCall`, `ScriptedLLM`, checks, `ActionSafetySuite`, `simulate`, scorers | `core`, `domain`, `actions`, `agent`, `voice` | `jiwer` |
| `api` | The composition root: `VoiceRuntime`, the router, `serve`, the protocol models, the static client, the CLI | every layer | `fastapi`, `starlette`, `uvicorn` |

**Proposed changes to Ole5's seven layers, with reasons:**
1. **No `media` layer** (open question 2: one install, so nothing has to keep Pipecat out of a base install). Pipecat stays in `voice`, as ARCHITECTURE.md has it, in modules of its own:
   - the session's modules never import Pipecat, so text-mode tests run the same session code that builds heard words and receipts in a real call, and test the real consent path; the parity test (section 9.5, M4) checks this;
   - Pipecat's churn stays inside those modules;
   - SECURITY.md's wording ("only `voice` builds heard words and the read-back receipt") does not change.
2. **A `testing` layer.** The testing kit is part of the contract. It must sit inside a layer for the harness, and it must not need FastAPI. `AudioCall`, in `testing/audio_call.py`, is its only module that runs Pipecat, through `voice`.
3. **loguru is owned by `voice`,** not by `core` as D-002 and M2 planned. Pipecat is the only reason loguru is present, and the policy is to switch off one namespace, not to route a global logger.
4. **Pipecat's STT and TTS base classes are wrapped; its LLM services are not used** (section 13, open question 8). D-018 supersedes D-002's bullet, and ARCHITECTURE.md's convention was changed to match on 2026-11-01.
5. **Public facade modules sit at the package root.** Today the harness forbids modules directly under `src/<name>/` other than `__init__.py`.

### 12.3 The Ole5 app's layers

The app shrinks to five layers:
- `core`: its settings, its logging set-up, its errors;
- `domain`: `TicketDraft`, the Ole5 rules, and the ports for its knowledge base and ticket system;
- `adapters`: Qdrant with the embedding gateway, and the T2 Ticket API;
- `agent`: the use-case declaration (tools, actions, prompts, labels, word additions), written on `t2_agentic_voice`;
- `api`: the FastAPI app, the `VoiceRuntime`, the settings composition and the widget's static files.

`actions` and `voice` leave the app, because the library now owns them. This amends D-003 for the app.

### 12.4 Harness changes

- **Built in plan 001 (D-013):** one `harness.toml` for the repository. `[package] root` and `public` locate the library and its public modules; `[[apps]]` lists the Ole5 app and the example. ARCH-PUBLIC fails an app that imports a non-public library module or another app, and fails the library if it imports an app; a layer may not import from the package root. This replaces the per-member configurations the first draft proposed.
- **The app's own layers (proposed, 12.3)** need `[[apps]]` to carry layers, or a configuration per member; the plan that gives the app its layers chooses.
- **ARCH-BAN (new):** banned module prefixes, per member and per layer, with exceptions and a FIX line. It has two uses:
  - In the library, it bans Pipecat's vendor service modules (`pipecat.services.<vendor>`) and its LLM-service and context-aggregator modules. It allows `pipecat.services.stt_service`, `pipecat.services.tts_service` and `pipecat.services.ai_service` in `voice`. ARCH-OWNER cannot express this, because it matches top-level packages (survey).
  - In the app and the examples, it bans `pipecat` and `aiortc`. (The ban on non-public `t2_agentic_voice` modules exists already, as ARCH-PUBLIC.)
- **ARCH-FACADE (built in M1, D-020):** each module listed in `[package] facades` contains only imports and `__all__`.
- **ARCH-WORDS (built in M1, D-020):** the library's `src/` must not contain app names (`ole5`, `otrs`, `ds.t2.sa`), checked case-insensitively. This answers the fear that the library is "Ole5-shaped underneath".
- **`[[restricted]]` in the library:**
  - `HeardWords` and `ReadBackReceipt`, built only in `voice`;
  - `ConfirmedAction`, built only in `domain`;
  - `CompletedAction`, built only in `actions`.
- **`[[owners]]`** as in the table in section 12.2.
- **One invariants register.** `[references] invariants` in every member points at the library's SECURITY.md. The app's own rules are cited as "app invariant N"; the checker gains a second register only if the app needs one.
- **CI:**
  - Python 3.12 only, matching the one `requires-python`;
  - from M2: the torch check;
  - a check that no audio file is committed under `apps/`;
  - from the first teammate tag: the public-API snapshot (griffe) and the wheel job (section 9.8).

### 12.5 How the app and the examples use only the public API

- They declare the dependency `t2-agentic-voice`, resolved from the workspace through `[tool.uv.sources] t2-agentic-voice = { workspace = true }`.
- ARCH-PUBLIC keeps them on the public modules (built); ARCH-BAN keeps them away from Pipecat and aiortc (built in plan 003's step 6: a `[[bans]]` table in harness.toml, D-032).
- The wheel job shows that nothing depends on workspace paths.
- When the app needs something internal, that is a library issue. It is fixed in the library's public API, never worked around in the app.

---

## 13. Open-source building blocks

Accepting each licence is the owner's call (WORKING-RULES.md): the owner accepted this list on 2026-11-01 (open question 20).

| Component | Licence | Verdict | Where | Notes |
| --- | --- | --- | --- | --- |
| Pipecat (`pipecat-ai`) | BSD-2 | **Depend**, `pipecat-ai[webrtc]~=1.15.0` | `voice` only | 1.15.0 was uploaded on 29 Oct and requires Python 3.11 or later (checked). It brings the user-turn redesign and deprecates the old turn APIs "until 2.0.0" (survey and a reviewer's reading of the release notes), so we write against the new API. Its wheel contains a `pipecat.flows` package and an `llm_with_backend` package (checked); `LLMWithBackend`'s status is from the survey. Per the survey, Daily is its only backer |
| SmallWebRTC transport | BSD-2 | **Depend** (inside Pipecat) | `voice` | One peer connection per call inside the process. Its request handler keys connections on `pc_id` (checked), so our router guards it (section 5.5) |
| aiortc | BSD-3 | **Indirect** (Pipecat's `webrtc` extra) | — | Never imported by our code |
| Silero VAD | MIT | **Depend** (in Pipecat's base wheel, checked) | `voice` | Its thresholds become settings |
| Smart Turn v3.2 | BSD-2 | **Depend** (the ONNX file is in Pipecat's base wheel, checked); vendor its training script later, for a Saudi fine-tune, outside the library | `voice` | Per the survey, its card gives 89.76% accuracy on Arabic against 94.26% on English. Per a reviewer's reading of the 1.15 notes, stop strategies now combine differently, so we set ours explicitly |
| `groq` SDK | Apache-2.0 (checked, 1.7.0) | **Depend** | `adapters` | Only `adapters` imports it |
| PyJWT | MIT | **Depend** | `adapters` | HS256 only |
| pydantic, pydantic-settings | MIT | **Depend** | everywhere, `core` | — |
| FastAPI, uvicorn | MIT, BSD-3 | **Depend** | `api` | Router lifespans are merged by `include_router` (checked in 0.162.0) |
| OpenTelemetry API, SDK, OTLP exporter | Apache-2.0 | **Depend** | `core` | — |
| OpenInference semantic conventions | Apache-2.0 | **Depend** | `core` | Attribute names only |
| `openinference-instrumentation-pipecat` | Apache-2.0 | **Not used** (open question 7) | — | It patches Pipecat process-wide and records transcripts on its own terms |
| Arize Phoenix server | Elastic License 2.0 | **Run** | small service | May be run inside T2, but not offered as a service |
| coturn | BSD-3 style | **Run**, if the deployment's network test needs it (the roadmap's M6) | small service | TURN over TLS on 443 |
| camel-tools | MIT | **Vendor** a few normalizers, with attribution | `domain` | The package itself pulls in torch |
| num2words | LGPL-2.1 | **Depend**, unmodified, behind a `domain` function | `domain` | MSA numbers. IDs are spoken digit by digit from our own table. It is already a Pipecat base dependency (checked) |
| sentencex | MIT | **Indirect** (Pipecat pins `==1.0.32`, checked) | — | Our own clause splitter in `domain` handles «؟» and «،», and Pipecat's TTS aggregation is set to pass text through, so text mode and audio mode split text the same way |
| jiwer | Apache-2.0 | **Depend** | `testing` | — |
| griffe | ISC | **Depend (dev)**, from the first teammate tag | CI | The public-API snapshot |
| eot-bench | Apache-2.0; data CC-BY-4.0 | **Depend (dev)** | evals | Its Arabic slice is not Saudi speech |
| Pipecat evals | BSD-2 | **Learn**; maybe dev later | — | Its default judge, caller voice and transcriber do not fit Arabic |
| Pipecat client-js with small-webrtc-transport | BSD-2 | **Fallback** (open question 1) | — | Pulls in daily-js, about 1.2 MB unpacked (survey); the RTVI fields are being renamed |
| voice-ui-kit, ElevenLabs UI | BSD-2, MIT | **Learn**, for the later widget | — | React |
| LiveKit Agents | Apache-2.0 | **Learn**: the test API, resuming after a false interruption, approval read-backs | — | Needs a media server |
| Pipecat Flows, `LLMWithBackend` | BSD-2 | **Learn** (stages later, thinker later) | — | Flows moves state on a tool call, which could stand in for a yes. `LLMWithBackend`'s backend runs tools |
| τ-bench 2.0, DBOS, huey | MIT | **Learn** their methods | — | — |
| **Avoid** | — | — | — | The LiveKit turn-detector models (LiveKit Model License); TEN VAD and framework (Agora conditions); pyarabic, mishkal and tashaphyne (GPL-3.0); Krisp and ai-coustics (commercial) |

**Built by us, because no project fits:**
- the outbox (no queue library refuses blind retries by design);
- the yes rule and the guard;
- join tokens (on PyJWT), the offer secret and TURN credentials;
- the thin browser client;
- the evaluation scorers (ported from the prototype under D-010).

**The decision on Pipecat's provider services: wrap the STT and TTS base classes only** (open question 8):
- **What stays.** The rule's purpose: providers are reached only through our ports and adapters (GP-22).
- **What goes.** The blanket ban on Pipecat's service base classes.
- **The bridges in `voice`:**
  - a speech-to-text bridge on `SegmentedSTTService` (present in 1.15.0, checked), calling the `SpeechToText` port;
  - a text-to-speech bridge on `TTSService`, calling the `TextToSpeech` port, with `text_aggregation_mode=TextAggregationMode.TOKEN` (present in 1.15.0, checked), so text passes straight through and our clause splitter in `domain` is the only splitter;
  - a **session bridge**: a plain `FrameProcessor`, not an `LLMService`. It forwards session events (the user's turn ended, with heard words; playback progress) to `voice`, and carries out the session's commands (speak a clause, stop, send a message to the browser, `duck` and `unduck` among them: D-065).
- **What is not used.** Pipecat's LLM services, its LLM context and context aggregators, and its function-call machinery. Pipecat's own interruptions are switched off, through `enable_interruptions=False` on its user-turn strategies (present in 1.15.0, checked), so that only the voice session interrupts and its cancel-on-resumed-turn behaviour never fires. How the session bridge makes Pipecat flush queued output audio on a stop is confirmed in the M2 plan (**verify**).
- **Why not wrap `LLMService` too.** Pipecat's context aggregators and turn controller would then also own the history, cancellation and the tool-call lifecycle. There would be two owners, and text mode would test a different path from audio mode.
- **What we gain.** We keep Pipecat's transport, VAD, Smart Turn, segmented-STT padding and the STT and TTS metrics. We do not rebuild them.
- **The ban.** ARCH-BAN forbids `pipecat.services.<vendor>` and Pipecat's LLM modules under `src/`. Pipecat's Groq services stay allowed outside the runtime: in evaluation factories, and in a parity check of our adapter against `GroqSTTService` on the golden set.
- **The cost.** We depend on two base classes that still change. The mitigations: a test per bridge, the parity test, the pin, and every Pipecat upgrade as a plan of its own.
- **Decision records.** D-018 supersedes the D-002 bullet, and ARCHITECTURE.md's conventions say so (2026-11-01).

---

## 14. Documentation plan

All docs are Markdown in `docs/guide/` of this repository for now, where the harness checks their links and reachability; they move with the library if it is published from a mirror repository (open question 9). The guide's index lists these pages, and each page is written when it lands. Code samples are included from tested files under `examples/` and the tests. A doc check fails when a sample block no longer matches its source file (DOC-SAMPLE, built in plan 004). A docs site (mkdocs-material) can come later.

| Page | Purpose | Lands with |
| --- | --- | --- |
| `README.md` | The first screen: what the library does, the contract in brief, the quickstart | M2 |
| `contract.md` | PROVIDES, MUST and MAY (section 3), as a teammate reads them, with the "built when" labels. Fixed at M0 (open question 23); a later change is the owner's decision, with a changelog entry. Not written yet: when it is written is an open question in the roadmap | M0 |
| `is-this-for-you.md` | The fit check: Python floor, OS and wheels, no torch, the heavy dependencies and known clashes (section 4.1), the one-process rule and the sidecar, network needs (UDP or TURN), Groq's low published limits, licences (Orpheus terms, Smart Turn, Silero), hosting limits | M2 |
| `quickstart.md` | `examples/minimal` end to end: English first, then Saudi Arabic; ends with the "first call does not work" checklist driven by `t2v doctor` | M2 (echo version), M5 (final) |
| `concepts.md` | Turns, the two-step interruption, the cancel scope, heard history, one turn as a table (written in M3); later the talker, tools and actions | M3, M4, M5 |
| `writing-for-voice.md` | How to write instructions for speech, tool descriptions, read-backs, claim phrases, send words and spoken labels, each with a good and a bad example | M4 |
| `tools-and-actions.md` | Writing each kind; wrapping existing functions; `bind` and `reports_on`; the action lifecycle; consent modes; the error table; idempotency and lookups | M5 |
| `safety.md` | How the yes rule and the output guard work; what the library guarantees and what stays yours (section 8) | M5 |
| `languages.md` | Presets, reply language, normalization, speaking formats, labels, vocabulary and the Whisper prompt, pronunciation | M4 |
| `reference/settings.md` (generated) | Every setting with its default, unit and environment name | M2 |
| `serving.md` | Sidecar or mount; identity sources; the join-token format and its readable claims; the offer secret; cross-origin pages; the `t2v/1` protocol | M2 |
| `browser-client.md` | The client API, events and states, tokens and `getToken`, consent, Stop and Esc, voice lowering, browser support | M2, M3 |
| `testing.md` | Cookbook for `TextCall`, the fakes, `ScriptedLLM`'s one-entry-per-request rule, the safety suite, the `t2v_live` marker snippet, live scenarios and audio replay; why `TextCall` is not a chat channel | M5 |
| `evaluation.md` | The evaluation helpers; recording your own golden set with consent and keeping audio out of git; the spelling guide; the golden-set commands, making a registered run and reading its scorecard; noise and the sign test; held-out and window runs; the run history | M1 |
| `latency.md` | The per-stage budget measured on Groq from the end of speech, with progress lines apart; how to measure your own | M4 |
| `tracing-and-logs.md` | Phoenix, your own `TracerProvider`, redaction, what a trace holds, the logging policy and the loguru default sink | M2 |
| `data-and-privacy.md` | What the library itself stores and sends: what a trace holds and its redaction, the `var_dir` stores, audio never stored unless both the setting and the caller's consent allow it, the consent claim and its version. Groq's own terms are not covered here: the owner explains them to each team (open question 10) | M2 |
| `audio-troubleshooting.md` | Echo on laptop speakers, Bluetooth hands-free microphones, microphone permissions, UDP and TURN failures | Not planned yet: left out of M3 with the Bluetooth warning (plan 005) |
| `deployment.md` | The process model and the lock file, Docker, TURN behind a corporate proxy, one instance, drain, health and admission, capacity | M6 |
| `runbook.md` | A Groq 429 storm or outage, a deprecated model, TURN down, Phoenix down or full, a stuck outbox write, key rotation, a deletion request, a suspected breach | M6 |
| `providers.md` | Writing an adapter for a port | M4 |
| `cookbook/it-helpdesk.md`, `cookbook/hr-leave.md` | Worked use cases that use no Ole5 code | M5, M7 |
| `reference/api.md` (generated) | The public modules, from docstrings (griffe), with each module's stability | M2 onward |
| `upgrading.md` and `CHANGELOG.md` | Versioning, stability levels, deprecation, behaviour changes, the Pipecat pin and upgrade policy | The first teammate tag |
| `SUPPORT.md`, `CONTRIBUTING.md` | How to report a problem; how to contribute adapters and docs; what support exists, decided when someone starts using the library (open question 14) | The first teammate tag |
| `thinker.md` | The job lifecycle, delivery, the stale rules, bringing your own backend | After M7 |

---

## 15. Distribution

| Option | For | Against |
| --- | --- | --- |
| Git tags on this repository: `uv add "t2-agentic-voice @ git+https://<host>/<repo>@t2-agentic-voice/v0.3.0#subdirectory=packages/t2-agentic-voice"` | Nothing to run, and it works today | No version ranges (`~=0.3`), so teammates move the tag by hand. Installing needs read access to the whole repository, including the Ole5 app's prompts and adapters |
| T2's private package index, or the git host's package registry if it speaks the Python simple-index API | Normal ranges (`uv add "t2-agentic-voice~=0.3"`); CI builds the wheels once; teammates see only the library | It needs an index. DESCRIPTION.md mentions "T2's package index" as a source of ragent2, so one may already exist (**verify**) |
| A mirror repository holding only `packages/t2-agentic-voice` and `examples/`, tagged from CI | Git tags without exposing the app | One more repository and a sync job to keep |
| A static simple index (PEP 503 files) on the website host | Fits D-005, since it is part of the website | Needs authentication in front of it for internal code |
| Public PyPI | The easiest install | Exposes internal code; not wanted before T2 decides |

**The owner's answer** (open question 9): T2's package index from the first teammate install if it exists, otherwise git tags on a mirror repository; the owner asks T2 whether the index exists. Public PyPI is not an option for now. Whatever the channel, the golden set's audio is never in git (section 9.7), so a teammate who can read the repository never gets the owner's recordings.

- **Version scheme.** SemVer `MAJOR.MINOR.PATCH`, with `0.x` until 1.0. The version in `pyproject.toml` is bumped as milestones land. No tag is cut until a teammate is ready to install; tags are then `t2-agentic-voice/vX.Y.Z`. The app is never published; its deployments are tracked by image tag.
- **Each tagged release carries:**
  - the wheel and sdist;
  - its changelog entry;
  - the exact Pipecat version tested;
  - the protocol version;
  - the library's scorecard summary, with speaker and device counts.
- **Patch releases** follow section 5.4's Pipecat policy and are best effort, as SUPPORT.md states.
- **Licence.** A LICENSE file states T2-internal use. Vendored MIT and BSD code keeps its notices in THIRD_PARTY_NOTICES.md.

---

## 16. Roadmap impact

The Ole5 app is still required, and it drives the work. Each milestone keeps its goal and its "done when". The library work below is what the Ole5 work forces, plus what `examples/minimal` needs, built generically so the app consumes it through the public API. Items labelled **On request** (section 3.1) are not on this table. No dates or durations are given.

### 16.1 Milestones

| Milestone | Ole5 app work (goal unchanged) | Library work it forces |
| --- | --- | --- |
| **M0** Scaffold and harness (in progress) | The app moves to `apps/ole5-voice-agent` with its five layers | The workspace with three members and one `requires-python`, and ARCH-PUBLIC for the app and the example (both built, plan 001); the library's empty layers; `contract.md` (fixed at M0, open question 23); the decision entries (16.3). *Done when* `poe check` passes for every member, and the owner has approved this design, the contract and the decision entries, and has ruled on D-002, D-003, D-007 and D-011 in their amended form (plan 000) |
| **M1** Measurement first | The golden set from the owner's voice, with audio kept out of git; the golden-set runner and poe tasks of evaluation.md, in the app; the registration; the baseline scorecard | The `SpeechToText` port and the Groq Whisper adapter; the canonical Arabic normalizer, digit normalization and spelling-guide support; the scorer functions (`wer`, `cer`, recall, `sign_test`); the tracing helpers in `core`, with usage on STT spans; the test that no secret reaches a trace; the first facades with ARCH-FACADE and ARCH-WORDS |
| **M2** A call that listens and speaks | The widget, built on the reference client; the owner's calls on the owner's laptop, recorded with the recording setting and the consent claim on. The deployment to the owner's host, the network test and the media-path decision, and the identity decision (open question 19) moved on 2026-11-03 to the deployment's own plan (the roadmap's M6), with the library's TURN credentials if its network test needs TURN | Pipecat's modules in `voice` (SmallWebRTC, Silero, Smart Turn, the STT and TTS bridges, the session bridge, Pipecat's interruptions off); the `TextToSpeech` port and the Groq Orpheus adapter (a model and voice per language, clause split under 200 characters, pronunciation, the phrase cache); the voice session in echo mode; `SignedJoinTokens`, plus `DevIdentity`; the used-token store; the offer secret; CORS; the router with its lifespan, `serve()`, the lock file and the dev page; `t2v-client.js` and `t2v/1`; `VoiceSettings` with a required `env`, and its generated reference; the loguru policy, Pipecat error events and the invariant 8 test; `t2v doctor` (basic) and `t2v settings show`; requests counted per call minute, beside the published limits (D-040; reading the key's real limits optional, plan 003's Q17); the torch check; `examples/minimal` as an echo use case |
| **M3** Interruptions and cancellation | The thresholds registered; the targets on the golden overlap clips and the M2 recordings. Ole5 sets no word additions: the presets hold the prototype's words (D-062) | Cancel scopes, one per reply; the two-step interruption (`duck` and `unduck` messages and the overlap window); the stop, wait, repeat, listening and no presets; the own-echo rule; heard history; `AudioCall`; in the client, a push-to-talk fallback. The parity test moved to M4 with `TextCall`, and the Bluetooth hands-free warning was left out (plan 005) |
| **M4** The talker and knowledge answers | The Qdrant adapter and the search tool; the prompts; simulated knowledge calls | The `ChatModel` port and the Groq chat adapter; the talker loop; `@tool` (async and sync, `bind`, `reports_on`), `Tool.from_function` and `CallContext`; cards; reply language; prompt composition and `render_prompt`; the guard's ID rule with digit normalization; progress lines; `KnowledgeBase` and `knowledge_tool`; `TextCall`, `ScriptedLLM` and the fakes, and the parity test of `TextCall` and `AudioCall` (from M3, plan 005); `simulate`; `t2v check`; time-to-first-audio measurement and the latency page; `writing-for-voice.md`; the read tool in `examples/minimal` |
| **M5** Tickets, ticket status and handoff | The T2 Ticket API adapter; the `create_ticket` action with spoken labels; the `ticket_status` tool with `reports_on`; the handoff, confirmed like any action (open question 6); Ole5's adversarial tests | `@action` and its lifecycle; the `ReadBack` consent mode; the yes rule and receipts, with the heard-words source; the error meanings; the SQLite outbox, jobs and lookup; the record; the guard's claim rule and rule C; per-call and per-caller caps; `ActionSafetySuite`; the hard checks in `simulate`; `t2v outbox`; the action in `examples/minimal` |
| **M6** Reliability and operations | Capacity: requests per call minute, calls per key, CPU; the cap set below the key's limit | Timeouts and fallbacks for each provider; 429 handling, the process-wide per-model limiter and cool-off; admission control with a busy notice; readiness on startup and drain only; idle timeout; drain; usage in the call report; the full `t2v doctor`; the deployment guide and the runbook; CPU per call measured |
| **M7** The rehearsal | The script passes on every device; the report | Docs completed (cookbooks, safety, troubleshooting); the public API reviewed, with provisional modules promoted or kept; versions stay `0.x` (open question 15) |

**The first teammate tag** is not a milestone. Whenever a real teammate is ready to install, the tag is cut after: the griffe snapshot and the wheel job are on, the changelog, SUPPORT.md, CONTRIBUTING.md and upgrading.md exist, and the distribution channel (open question 9) is settled.

M4's bullet "deeper troubleshooting as a background job" is the thinker pattern. The owner moved it to the thinker work after M7 (open question 17). M4 keeps one fast search per question and an honest progress line.

### 16.2 After M7

The owner chose the next phase: **the agent-led mode** (D-050, [agent-led-mode.md](agent-led-mode.md)), voice for a team's existing LangChain or LangGraph agent used as is. It takes in the "LangChain tool helpers" below.

No order is fixed among the others; the owner chooses:
- **The thinker**, first in `experimental`: `ThinkerBackend`, an LLM thinker on Groq, the delivery and stale rules, then a LangGraph adapter and an example with no Ole5 code. Once it is stable, it moves out of `experimental`.
- The drop-in web widget, and with it a stable client and protocol message list.
- Typed chat (it needs a consent decision first).
- `stages`, for slot filling.
- Shared Postgres or Redis stores, for several instances.
- A Saudi-hosted provider adapter with an `allowed_regions` guard, when the keys exist.
- The config-only server and the agent over HTTP.
- SIP.
- The operator commands: `probe`, `loadtest`, `usage`, `purge`, `dsr`.
- A Qdrant knowledge adapter in the library.
- LangChain tool helpers.
- The Smart Turn fine-tune (roadmap, "Planned later").
- Any **On request** item from section 3.1 that a teammate has asked for.

### 16.3 Decision entries to write

Numbers are taken when each entry is written, after checking that no other session has claimed them. The owner accepted D-002, D-003, D-007 and D-011 on 2026-11-01 (plan 000).
Recorded already, on 2026-10-31: the library and the app in one workspace, with the public-API rule (D-013); the v1 usage mode (D-014; what ships for the browser is still open question 1); the thinker's owner-decided part (D-015; building it after M7, in the experimental module, is still open questions 16 and 17); open source allowed (D-016; the licences are still open question 20). This design as a whole is D-017, accepted on 2026-11-01; the owner's answers to section 17 are D-018. Still to write, each when the owner rules on it:
- Pipecat 1.15.x, wrapping only its STT and TTS base classes, and its own interruptions off. This supersedes a bullet of D-002 and amends the conventions in ARCHITECTURE.md. Done in D-018.
- GP-22's "swapped by configuration" widened to "by a setting, or by passing an adapter object in code". Done in D-030.
- The library's `testing` layer (with no `media` layer, D-018) and the app's five layers. This amends D-003. The library's layer: done in D-019; the app's layers are still to write.
- The harness: one configuration per member, ARCH-BAN, ARCH-FACADE, ARCH-WORDS, one invariants register. ARCH-FACADE and ARCH-WORDS: done in D-020; ARCH-BAN: done in D-032; the others are still to write.
- The public API, the stability levels, and the Python floor of 3.12. The first facades and the stability levels: done in D-021; the Python floor: done in D-018 (answer 3).
- Settings precedence, the prefix, and a required `env`. Done in D-028.
- Serving and identity: the sidecar and the mount, one process per `var_dir` with the lock file, one `identity=` source, the join-token format, the offer secret, consent in the token, and Ole5's identity answer (open question 19). Done in D-029, but for Ole5's identity answer.
- SECURITY.md generalized to actions and moved to the library as the one register, which amends D-007. Invariant 1 itself stays: a handoff is confirmed like any action (D-018).
- Evaluation: scorer functions in the library, the golden-set runner in the app, and audio kept out of git. This follows up D-011. Done in D-022.
- The tracing path: done in D-018, and its packages (plain OTLP through the OpenTelemetry SDK) in D-023.
- The licences accepted: done in D-018.

Written since, beyond this list: D-024 and D-025 (M1's measurement: the noise, and `stt.model` stays `whisper-large-v3`); D-026 (the base error is `T2VoiceError`, as 5.1 names it); D-027 (ARCH-DEPS and DOC-SAMPLE); and, in plan 003's Block 0, D-031 (the library's logging and Pipecat's loguru), D-033 (the echo's shape), D-034 (Whisper per user turn, Proposed), D-035 (invariants 7 and 8 brought to 8.1), D-036 (the ports beyond 6.1, Proposed), D-037 (agent speech keyed on replies, the greeting included, Proposed), D-038 (a call's language fixed at join, Proposed) and D-039 (`t2v/1`'s messages parsed strictly); in plan 003's step 18, D-040 (requests per call minute for each Groq model, measured, Proposed); D-050 (the agent-led mode, the next phase after M7, section 16.2); and, in plan 005 (M3), D-060 to D-068 (the cancel scope per reply, the two-step interruption and its rule, the presets' words, the filter for text from silence, the heard history and the repeat, `duck`, `unduck` and `cut` with push-to-talk, the live language, the hold after Smart Turn's "complete", and the registered results with `two_step` the default).

### 16.4 Risks carried

- **Pipecat's churn**, its coming 2.0, its rare patch releases, and its single backer (survey).
- **Saudi Arabic is hard for speech-to-text.** The best published SADA error rates are about 29–35% (28 Oct research), and the prototype found about 12 of 22 utterances usable (DESCRIPTION.md). Smart Turn is weaker on Arabic (survey).
- **Groq's limits:**
  - no partial transcripts;
  - a 10-second billing minimum per transcription request (checked), which makes each overlap check costly;
  - both Orpheus models are previews with a 200-character limit (checked);
  - published limits of 10 TTS requests a minute and 100 a day per Orpheus model, and 20 a minute for Whisper (section 10.4), which may cap Ole5 at a few calls a day unless the key's real limits are higher;
  - one key's limits shared by every call, and by every app (open question 11);
  - retained data stored in the US, and the processing location not stated.
- **The guard is lexical** (section 8.4).
- **aiortc's networking unknowns** until the deployment's own plan (the roadmap's M6) tests them: the port range, Docker NAT, and relaying through TURN over TLS.
- **Every number rests on one speaker** while D-006 holds.
- **The personas are assumptions** until real teammates answer (section 2).
- **One maintainer** and a coding agent.

---

## 17. Open questions for the owner

The owner answered these on 2026-11-01, recorded in D-018; each answer follows its question, in the owner's own words where they wrote them. Two answers wait on a fact the owner is finding out (9: whether T2's package index exists; 19: whether Ole5's website logs customers in), and one is left until someone starts using the library (14).

1. **What ships for the browser in v1?**
   - (a) Our own thin client `t2v-client.js` with our own protocol `t2v/1`, as a provisional reference.
   - (b) Pipecat's client-js and small-webrtc-transport, vendored as one bundle and speaking RTVI.
   - (c) No client: each team writes its own.

   **Recommendation: (a).** It needs no build step and no daily-js, which is about 1.2 MB (survey). The protocol stays ours and versioned, apart from RTVI's renames. Ole5's widget and every teammate reuse it. The cost is a few hundred lines of JavaScript that we maintain. Keeping it provisional avoids a browser-facing contract before the widget mode is designed, which keeps the owner's "Python library only" decision.

   **The owner's answer: (a).**

2. **Should the base install leave out Pipecat (the `media` split)?**
   - (a) Yes. The base has declarations, the text engine, join-token minting and the testing kit; `[voice]` adds Pipecat.
   - (b) No. One install, always with Pipecat.

   **Recommendation: (a).** Teammates' CI and the agent-graph persona need a light, conflict-free base, and a team's main app can mint tokens without Pipecat. It costs one layer and one CI job.

   **The owner's answer: (b), one install.** So there is no `media` layer and there are no extras: Pipecat stays in `voice` (section 12.2), and installing the library brings everything a call needs (section 4.1).

3. **The library's Python floor.**
   - (a) 3.12, like Ole5, lowered later as a minor release when a real teammate needs 3.11.
   - (b) 3.11 now.

   **Recommendation: (a).** This changes the first draft's recommendation. A uv workspace resolves one `requires-python` for all members, so a 3.11 floor would need a separate unlocked CI job, and the harness's `sysmon` coverage needs 3.12. The only reason given for 3.11 was an assumed persona. Pipecat supports 3.11 (checked), so lowering later is possible.

   **The owner's answer: (a).**

4. **The library's default settings prefix.**
   - (a) `T2V_`.
   - (b) `T2_VOICE_`.
   - (c) No default: the app must always pass its own.

   **Recommendation: (a)**, with `from_env(prefix=...)` for teams that want their own. Until the owner's answer below, the scaffold's `Settings` used `T2_AGENTIC_VOICE_` (D-013).

   **The owner's answer: (a), `T2V_`.** The scaffold's `Settings` uses it from 2026-11-01.

5. **One process per `var_dir` in v1?**
   - (a) Yes: SQLite stores, a lock file, the sidecar for multi-worker services, and the reasons documented.
   - (b) Postgres adapters for the outbox, used tokens and counters in v1.
   - (c) Redis adapters in v1.

   **Recommendation: (a).** The stores are ports already. A shared adapter comes when a team needs more than one instance, and it would be one more small service under D-005.

   **The owner's answer: (a).**

6. **The handoff and invariant 1.** M5 says «أبغى موظف» makes a handoff ticket at once, but invariant 1 requires a read-back and a yes first.
   - (a) The handoff is a normal action with a short read-back.
   - (b) Amend invariant 1: an action declared with `consent=HeardRequest(...)` may take consent from a heard request phrase. The phrase comes from fixed per-language lists, it is matched on heard words (never on model output), and at most one such action runs per call. Nothing else about the yes rule changes: a bare yes over a closing question is still asked again.
   - (c) The handoff is not an action at all.

   **Recommendation: (b).** Consent still comes from heard words, the rehearsal step passes, and the harm of a mistaken handoff ticket is small. (c) would create a record outside the rules, so the agent advises against it.

   **The owner's answer**, in their words: "if the agent has the ability to handoff, it should ask to confirm the action. otherwise it should clarify it can not do it. Or maybe offer a ticket instead. But in general is should ask to confirm." So invariant 1 is unchanged and `HeardRequest` is dropped: a handoff is an action like any other, read back and done only after a clear yes, as in (a). In an app with no handoff action, the talker says it cannot hand the call over, and may offer a ticket instead, confirmed the same way (section 3.1, Talker). For Ole5, where a handoff is a ticket (D-009), «أبغى موظف» starts the handoff's read-back.

7. **The tracing path.**
   - (a) Our own spans, following OpenInference conventions.
   - (b) `openinference-instrumentation-pipecat`.
   - (c) Pipecat's built-in tracing.

   **Recommendation: (a).** The turn, guard, receipt and confirmation spans have to be ours anyway. (b) patches Pipecat for the whole process and records content on its own terms. Mixing paths gives every step two spans. If (a) turns out costly, M2 spikes (b).

   **The owner's answer: (a).**

8. **Pipecat's provider services.**
   - (a) Wrap the STT and TTS base classes only; the session bridge is a plain processor; Pipecat's LLM services and interruptions are not used.
   - (b) Also wrap `LLMService` and use Pipecat's function-call machinery.
   - (c) Keep D-002's "never used" and write our own STT and TTS processors from scratch.

   **Recommendation: (a)**, as section 13 argues. (b) would give history, cancellation and tool calls two owners and make text-mode tests test a different path. (c) rebuilds padding, flushing and metrics that Pipecat already has. It also means starting on Pipecat 1.15.x rather than the 1.14 the research advised.

   **The owner's answer: (a).** D-018 supersedes D-002's bullet, and ARCHITECTURE.md's conventions now say this.

9. **Distribution.**
   - (a) T2's package index from the first teammate install if it exists; otherwise git tags on a mirror repository.
   - (b) Git tags on this repository.
   - (c) Public PyPI.

   **Recommendation: (a).** Please ask T2 whether the "T2 package index" that DESCRIPTION.md mentions exists and can host this. (b) gives every teammate the app's code.

   **The owner's answer: (a).** The owner asks T2 whether its package index exists and can host the library.

10. **Sending teammates' audio to Groq.**
    - (a) The library documents the data flow in Groq's own words; each team turns on Zero Data Retention or records why not; each team's data controller signs off; internal pilots only until then.
    - (b) Wait for a T2-wide position first.
    - (c) Wait for a Saudi-hosted provider.

    **Recommendation: (a)**, and ask T2 compliance for a position in parallel. By Groq's page, inference data is not retained by default; logs may be kept up to 30 days unless opted out or ZDR is on; retained data sits in the US; the processing location is not stated (checked). HR data in particular needs the sign-off.

    **The owner's answer**, in their words: "Do not worry about this, I will explain this to anyone that wants to use the package. They also should know this by themselves because of the models they will need to use". So the library sets no requirement here: no Zero Data Retention rule and no sign-off in the contract (section 3.2). Its guide documents only what the library itself stores and sends (section 14).

11. **Groq keys.**
    - (a) One key per app.
    - (b) One shared key, with a share setting per app.
    - (c) A shared limiter service across apps (later).

    **Recommendation: (a)**, so one app's load cannot exhaust another's limits. Use (b) only if T2 gives a single key.

    **The owner's answer: (b), one shared key.** Each app sets its share of the key's limits (section 10.4).

12. **Browser support for the reference client.**
    - (a) Chrome and Edge supported; Firefox and Safari best effort.
    - (b) All four supported.
    - (c) Chrome only.

    **Recommendation: (a).** This covers T2 laptops and Ole5's customers without a testing burden one person cannot carry. The Teams desktop webview is untested.

    **The owner's answer: (a).**

13. **The repository's name.** The project is named T2 Agentic Voice (D-013); the question is the repository's and its folder's name.
    - (a) Keep "Ole5-voice-agent".
    - (b) Rename it to `t2-agentic-voice` before the first teammate install.
    - (c) Keep the name, and publish the library from a mirror repository (open question 9).

    **Recommendation: (b) if teammates install from this repository, otherwise (c).** Teammates' install URLs and issue links should not name Ole5. The rename costs path updates in the owner's tooling.

    **The owner's answer: (b).** The repository becomes `t2-agentic-voice` before the first teammate install; the owner renamed the folder on 2026-11-01.

14. **The support model.**
    - (a) Issues in the repository, CONTRIBUTING.md, and best-effort answers.
    - (b) (a) plus a named backup maintainer once a second team adopts the library.
    - (c) No support outside Ole5 until 1.0.

    **Recommendation: (b).** It answers the bus-factor fear without promising response times nobody can keep.

    **The owner's answer**, in their words: "I am not sure yet, we can think about this when we really build it and someone starts using it". Open until then; SUPPORT.md is written with the answer.

15. **When is 1.0?**
    - (a) When Ole5 passes M7.
    - (b) When Ole5 passes M7 and a second team's use case runs in a pilot.
    - (c) Stay on 0.x for now.

    **Recommendation: (b).** A second use case is the only real test that the API is not Ole5-shaped.

    **The owner's answer: (c).** Versions stay `0.x`, with no date set for 1.0.

16. **The thinker: when, and its first backend.**
    - (a) After M7, an LLM thinker on Groq first, then the LangGraph adapter.
    - (b) After M7, the LangGraph adapter first.
    - (c) After M7, only the port, with teams bringing their own.

    **Recommendation: (a).** It proves the stale, budget and delivery rules with the fewest moving parts. "After M7" is the agent's proposal, not the owner's decision; the design keeps nothing that blocks building it earlier.

    **The owner's answer: (a).**

17. **M4's "deeper troubleshooting as a background job".**
    - (a) Move it to the thinker work after M7. M4 keeps one fast search and a progress line.
    - (b) Keep a narrow mode for one slow read in the background in M4.

    **Recommendation: (a).** It matches the owner's decision that the thinker is optional, and it keeps M4 small. The prototype showed that slow searches are better made fast than run in the background.

    **The owner's answer: (a).** The roadmap's M4 says so.

18. **The join-token format.**
    - (a) A compact JWT, HS256 only, with documented claims.
    - (b) Our own HMAC format.

    **Recommendation: (a).** A website team in any language can mint one with a standard library, and the library's verifier accepts only HS256 with a known key ID. Its claims are readable by the caller under either option, so neither may carry secrets.

    **The owner's answer: (a).**

19. **How Ole5's website proves who the customer is** (open in the roadmap, to decide before M2).
    - (a) The website's server mints the join token for a logged-in customer (`SignedJoinTokens`).
    - (b) The customer confirms a one-time code sent to their email; the app's `authenticate` dependency checks it and returns a `Caller` marked as verified by email (`Authenticate`).
    - (c) Both: (a) for logged-in customers, (b) for the rest.

    **Recommendation: (a) if the website already has customer login; otherwise (b).** The library fits either unchanged, and only the chosen one is built in M2. An email typed in the widget stays a contact address that never unlocks ticket status (DESCRIPTION.md).

    **The owner's answer: not known yet.** The owner asks the website team whether customers log in. Sign-in is built only after the answer, in the deployment's own plan (the roadmap's M6), where plan 003's Q12 took it.

20. **The licences to accept** (the owner's call under WORKING-RULES.md).
    - (a) Accept the list in section 13 as it stands: Pipecat (BSD-2), aiortc (BSD-3), Silero (MIT), Smart Turn (BSD-2), the groq SDK (Apache-2.0), PyJWT (MIT), num2words (LGPL-2.1, as an unmodified dependency), camel-tools normalizers vendored with their notice (MIT), jiwer (Apache-2.0), coturn (BSD-3 style), Phoenix (Elastic License 2.0, run only), and the Orpheus terms in the Groq console.
    - (b) Accept all but the vendoring: write our own Arabic normalizers.
    - (c) Review each one separately.

    **Recommendation: (a).** All are used as the survey describes, and only camel-tools code is copied, under MIT with its notice.

    **The owner's answer: (a).**

21. **Groq's low published limits for Orpheus and Whisper.**
    - (a) Read the key's real limits in M2; if they are as published, ask Groq for higher limits on the key, and cache every repeated phrase meanwhile.
    - (b) Accept a low call volume for the pilot.
    - (c) Plan a second TTS provider as soon as another key exists.

    **Recommendation: (a).** At 100 TTS requests a day, Ole5 could not pass its rehearsal on every device. Caching helps only with repeated phrases.

    **The owner's answer: (a).**

22. **The serving shape teammates are told to use.**
    - (a) The sidecar by default for any service with more than one worker or replica; the mount for one-worker apps and demos.
    - (b) The mount only.
    - (c) The sidecar only.

    **Recommendation: (a).** Mounting forces one worker and a long drain on the host service, which a multi-worker service should not take on. The sidecar reuses the same token path as Ole5's website mode.

    **The owner's answer: (a).**

23. **When to freeze the contract.**
    - (a) `contract.md` lands in M0 marked provisional, and is frozen after at least one real teammate has answered the questions in section 2.
    - (b) Freeze it at M0.

    **Recommendation: (a).** The personas are the agent's assumptions, and the answers may change the MUST list (the Python floor, the serving shape, delegated credentials).

    **The owner's answer: (b).** `contract.md` lands in M0 as the fixed contract. A later change to it is the owner's decision, recorded, with a changelog entry. The questions in section 2 are still put to real teammates.

---

## Review notes

Issues from the two reviews that were not applied as written, one line each:

- **DX, Caller and delegated credentials (medium):** applied the documentation part (claims are readable; no secrets in them); `call_deps` and opaque tokens in mounted mode are "On request", because no real teammate has asked and they add a second token format.
- **DX, templates through the ID rule (high, guard):** not applied; read-back values come from the draft so the caller can check them, and `done` values come from the real result, so the ID rule could only block a correct sentence.
- **DX, a lint for claim phrases that are nouns or not past tense (high, guard):** not applied; it cannot be done reliably in Arabic. It is replaced by the "past-tense phrases" rule in the contract, a lint for a claim phrase inside its own read-back, and writing-for-voice.md.
- **DX, consent in the `/join` body (medium):** applied as a claim in the signed join token instead, following the architecture review, so consent comes only from whoever mints after the consent screen.
- **DX, typed consent allowed in `dev` with `--allow-real-actions` (medium):** not applied; typed consent reaches `execute` only when `env` is `test`, which serving refuses, and `t2v chat` is always dry-run. Typed text is not heard words (invariant 1).
- **DX, sync tools marked "finish on interrupt" (medium):** applied differently; a sync tool's result is discarded on barge-in and its thread finishes in the background, which is safe because read tools have no side effects.
- **DX, `OneOf` (medium):** applied the review's alternative: `OneOf` is dropped; fixed sets are `Literal` or enum types, or `str` with `validate`; backend-loaded `Choices` is "On request".
- **DX, `pipecat-ai[webrtc,silero]` (low):** corrected; pipecat-ai 1.15.0's `silero` extra adds no requirement, and Silero is in its base wheel (checked), so the extra is `[webrtc]`.
- **DX, a co-install CI job with numpy, langchain-core and opencv-python (low):** deferred; the torch check is in from M2, and the known clashes are listed on is-this-for-you.md.
- **DX, `RuleLLM` (low):** not added; `FunctionLLM` already covers rule-based fakes.
- **DX, `VoiceRuntime(agents=[...])` (low):** not added; one runtime per agent, with a process-wide limiter and per-agent stores.
- **Architecture, key rotation moved to "On request" (high, scope):** partly applied; the join key is a map by key ID, which costs no extra code and allows rotation, and there is no separate rotation feature.
- **Architecture, `authenticate=` moved to "On request" (high, scope):** applied, except that it is built in the deployment's own plan (the roadmap's M6) if Ole5 picks the one-time email code (open question 19).
- **Architecture, `logging.pipecat` defaulting to forward (low):** not applied; while a team's loguru default sink is installed, forwarding would also print Pipecat's DEBUG lines, which may hold transcripts (invariant 8). Instead, `voice` turns Pipecat's errors and transport failures into library logs and events (`media` before D-018).
- **Architecture, the claim that Pipecat Flows is in core (medium, Pipecat pin):** checked rather than left as "verify"; the 1.15.0 wheel contains a `pipecat.flows` package.
- **Architecture, Groq's Orpheus limits:** applied with care; the agent's own read of Groq's rate-limits page found the same numbers but described them as the Developer plan's base limits, so the design treats the owner's key as unknown until its limits are read in the console (optional in M2, plan 003's Q17).
