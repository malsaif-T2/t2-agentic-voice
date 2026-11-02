# Architecture

T2 Agentic Voice is a library for real-time voice agents: an app built on it is a Python
backend that serves a web widget and runs one voice pipeline per call over WebRTC, with
speech-to-text, the model, and text-to-speech from outside providers (Groq today, D-004). The
Ole5 Voice Agent is its first app. Two rules shape it most:

- **Only the backend acts.** The talker (the model that speaks) asks for tools; the `actions`
  layer runs them, records what it completed, and words every outcome from a real result. No
  sentence may claim an action that the call's record does not hold
  ([SECURITY.md](docs/SECURITY.md), invariants 1 and 2).
- **Every outside service is behind a port.** `domain` defines the protocol, `adapters`
  implements it, and a setting picks the adapter, so a provider is swapped by configuration
  without touching the layers that use it (GP-22).

The layers were proposed by the agent on 2026-10-28 and approved by the owner on 2026-11-01
([D-003](docs/design/decisions.md)); the libraries they own are in D-002. What the
library provides to an app, and what an app must provide, is in
[package-design.md](docs/design/package-design.md) (D-017), with the owner's answers to its
open questions in D-018.

## Repository layout: the library and its apps

One repository, a uv workspace (D-013):

```
packages/t2-agentic-voice/   the library teammates install: src/t2_agentic_voice/, its layers
apps/ole5-voice-agent/       the Ole5 Voice Agent: src/ole5_voice/, Ole5's prompt, tools,
                             knowledge base and ticket system, and its web widget
examples/minimal/            the smallest app: the guide's quickstart, and a test of the library
tests/                       one subfolder per package, harness/ for the checks' own tests, and
                             the helpers every package's tests share (leaks.py, isolation.py)
```

The library's **public API is its package root and the facades beside it**: the root's
`__init__.py` re-exports the main names, and each public facade (`ports`, `groq`, `languages`,
`evals` and `tracing`, D-021; `identity`, `server`, `stores` and `events`, the design's 5.1)
re-exports one area's names and holds nothing else (ARCH-FACADE);
`[package] public` in harness.toml lists the modules an app may import, and `[package] facades`
the facades among them. An app imports nothing else from the library and no other app, and the
library never imports an app (ARCH-PUBLIC). So the Ole5 app uses the library exactly as a
teammate's app would, and the minimal example breaks if the library starts to depend on Ole5.
Inside the library, a layer imports from the layer that defines a name, never from the package
root or a facade. The library's `src/` never names an app (ARCH-WORDS).

## Flow

One call, top to bottom, naming the library's layer that does each step; the app supplies its
prompt, its tools and its backends (the knowledge base and the ticket system, for Ole5):

```
web widget         microphone, speaker, captions, Stop; static files the app serves (Ole5's
                   from apps/ole5-voice-agent/web/); the api layer serves only the
                   reference client, t2v-client.js, and the dev page
  ▼ api        checks the join token, hands the WebRTC offer to voice, builds the call's session
  ▼ voice      answers the offer; audio in; speech detection; end of turn; the two-step
               interruption; the turn's cancel scope
  ▼ adapters   speech-to-text turns each stretch of speech into text (through a domain port;
               Groq's Whisper gives no partial transcripts)
  ▼ agent      the talker: the user's words in, a reply and tool calls out
  ▼ actions    runs each tool (knowledge search, ticket status, ticket flow, handoff),
               records what it completed, words the outcome
  ▼ adapters   the knowledge base and the ticket system (through domain ports)
  ▲ voice      text-to-speech streams the reply clause by clause; a cancel stops it at once
  ◆ domain     the rules every step applies: the yes rule, the ticket flow's states,
               interruption words, Arabic normalization, how numbers are spoken
  ◆ core       settings, structured logs, errors, and traces to Phoenix, for every layer
```

## Layers

```
               api ─────────────► testing
    ┌───────────┼────────────┐       │
  voice ◄───────┼────────────┼───────┘
    │           │         adapters
  agent         │            │
    │           │            │
  actions ◄─────┘            │
    │                        │
  domain ◄───────────────────┘
    │
  core
```

An arrow or a line down means "may import"; `api` may import every layer, `testing` included.
`testing` may import `voice` and every layer below it, never `adapters` or `api`.

| Layer | Responsibility | May import | Owns (only it may import) |
| --- | --- | --- | --- |
| `core` | Settings (`VoiceSettings` in `core/config.py`, the only module that reads the environment, and its groups in `core/settings/`), structured logging (`core/logging.py`), the error types (`core/errors.py`: `T2VoiceError` and its subclasses, each with a stable `code`), tracing to Phoenix, and the types every layer shares | none | `logging`, `structlog`, `pydantic_settings`, `opentelemetry`, `openinference`, `phoenix`, `requests` |
| `domain` | The rules of a support call, with no IO: what counts as a clear yes, the ticket flow's states, what an interruption is, Arabic text normalization, how numbers (through num2words) and ticket IDs are spoken, the evaluation scorers' pure parts (term recall, ID recall, text from silence, the sign test), and the ports (protocols) every outside service is reached through | core | `num2words` |
| `adapters` | One adapter per port: speech-to-text, the chat model and text-to-speech (Groq), the knowledge base, the ticket system, each chosen by a setting; the signed join tokens and the SQLite stores (the used tokens) | core, domain | `groq`, `httpx`, `qdrant_client`, `jwt`, `sqlite3` |
| `actions` | The backend that acts: runs the talker's tools through the ports, keeps each call's record of completed actions, words every outcome from a real result | core, domain | — |
| `agent` | The talker: prompts, the few tool definitions, the reply language, one turn from the user's words to a reply and tool calls; the output guard on every sentence | core, domain, actions | — |
| `voice` | One call's real-time pipeline: answers the WebRTC offer (Pipecat's peer connection), audio in and out, speech detection, end of turn, interruptions, each turn's cancel scope, speech-to-text and text-to-speech wired to the talker; Pipecat's logger (loguru), kept off | core, domain, agent | `pipecat`, `loguru` |
| `testing` | What a team tests and measures its agent with: the evaluation scorers (word and character error rates) today; later the fakes of every port, text-mode calls, the adversarial suite and simulated callers (D-019) | core, domain, actions, agent, voice | `jiwer` |
| `api` | The HTTP surface and composition root: serves the widget, starts calls, reports health, builds the adapters from the settings and injects them, maps every error to one shape | core, domain, adapters, actions, agent, voice, testing | `fastapi`, `starlette`, `uvicorn` |

`harness.toml` holds the same rules in `[layers]` (who may import whom) and `[[owners]]` (which
layer owns which library), and `poe arch` compares them with this table row by row (ARCH-DOC):
one row per layer, its first cell the layer's name in backticks; **May import** the other
layers it may import and **Owns** the libraries `[[owners]]` gives it, as names in backticks or
separated by commas, or `none` or `—`. The Responsibility column is prose and is not read.
Whether the reason for a change is recorded in a decision is a review, not a check.

### Why these layers

The agent's reasoning, from the questions the kit asks (D-003 records the alternatives):

- **Where does IO happen?** Each kind has one owner: the provider and service clients in
  `adapters`, the voice framework in `voice`, HTTP in `api`, tracing in `core`.
- **What must stay pure?** The rules the prototype got wrong (what a yes is, what an
  interruption is, when a ticket may be created) live in `domain`, with no IO, so each is a
  plain function with plain tests.
- **What must not know about each other?** `actions` never imports `adapters`: it gets the ports
  injected, so the backend is tested with fakes and a provider swap never touches it. `agent`
  never imports `adapters` or `voice`. `api` injects into the talker only the chat-model port
  and the tool runner of `actions`, so the talker acts only through a tool call. No import rule
  can enforce that, since the ports live in `domain`, which `agent` may import: it is a review,
  plus a test of `api`'s wiring added with the talker. `voice` never imports `actions`: the
  pipeline cannot act, only the talker's tool calls can, through `actions`.
- **What is the outermost surface?** `api`, the HTTP routes and the composition root that
  builds every adapter from the settings.
- **Where do a team's tests and measurements get their tools?** From `testing` (D-019), beside
  `api` and above `voice`: the scorers now, and the testing kit later, which runs the real
  pipeline's session code with fakes. It never imports `adapters`, so a test reaches a provider
  only through a port it passes in, and never `api`, so a team's tests need no HTTP stack.
- **What may only one layer create?** A confirmed ticket draft, issued only by `domain`'s yes
  rule; its two inputs, the caller's heard words and the read-back receipt, built only by
  `voice`; and a completed action, recorded only by `actions`. Each goes into `[[restricted]]`
  (ARCH-CONSTRUCT) in the commit that creates its class ([SECURITY.md](docs/SECURITY.md),
  invariants 1 and 2). The first there is `SignedConsent`, the consent a verified signed join
  token carried, built only by `adapters`' signed-token identity source, since only it lets a
  call's audio be recorded (invariant 8). A call is not the only way to build an object, so the
  class also checks at run time that its validation was given a seal, `CONSENT_SEAL`, and a
  `[[restricted]]` table of `names` reports any reference to the seal outside `adapters`.

## The web widget

The widget is plain HTML, JavaScript and CSS, with no build step; the app's backend serves it,
not the library's `api` layer. It is built for the Ole5 app first, in
`apps/ole5-voice-agent/web/`; making it a drop-in for teammates' pages is a later option
(D-014). It is not Python, so `poe arch` does not read it; the golden set's test that no item
sits in the product reads its text (`tests/ole5_voice/evals/test_no_item_in_source.py`), and it
is checked by running it in a browser ([WORKING-RULES.md](WORKING-RULES.md), "Seeing it
run").

## Conventions

- Types shared across layers live in `core`; the ports and the call's rules live in `domain`.
- `pydantic` is allowed everywhere: it is how data is parsed at boundaries, model output and
  tool arguments included.
- Lower layers raise `core.errors.T2VoiceError` subclasses with stable codes and user-safe
  messages; only `api` maps them to its transport.
- Configuration comes only from `VoiceSettings` in `core/config.py`: built in code, or loaded by
  `VoiceSettings.from_env()`, the only reader of the environment, with no singleton; a module
  receives it. `.env.example` and `docs/generated/settings.md` list every setting
  (`uv run poe settings-ref` writes both). A provider is chosen by a setting, never by an import
  in a layer above `api`.
- Logs are structured: `get_logger(__name__)`, snake_case event names, key/value context
  (`core/logging.py`; the design's 3.3 and 10.2). The library logs on the standard library's
  `logging`, under `t2_agentic_voice`, whose logger has a `NullHandler`: importing the library
  configures nothing and prints nothing, and it never adds a handler to the root logger or
  touches another library's logger by itself. An event is a record whose message is the event
  name and whose `fields` attribute holds its key/value context. The app configures logging:
  its own way, or with `configure_logging`, which puts one handler, writing structured lines
  to the stream it is given, on `t2_agentic_voice` and the loggers the app names (its own
  package's), and holds aiortc's and aioice's loggers at WARNING unless `logging.content` is on
  (their lower lines hold SDP and IP addresses). Pipecat logs through loguru, which `voice`
  owns: it switches Pipecat's namespace off before it first imports Pipecat, and again at
  runtime start, so no framework debug line carries call content
  ([SECURITY.md](docs/SECURITY.md), invariant 8).
- `voice` uses Pipecat for its pipeline, its WebRTC transport, speech detection, and the base
  classes of its speech-to-text and text-to-speech services (D-018). Its own subclasses of those
  call the speech-to-text and text-to-speech ports, and its own processor runs `agent`'s turn
  inside the turn's cancel scope. Pipecat's ready-made provider services (its Groq
  speech-to-text, model, and text-to-speech services), its model services, and its own
  interruptions are never used: a provider service would reach Groq without a port (GP-22).
  ARCH-BAN keeps those services out of the library's imports; neither it nor ARCH-OWNER can see
  an import made inside Pipecat.
- Every turn runs inside a cancel scope owned by `voice`: a stop, a correction, or new words
  cancel the model, the speech, and read-only lookups. Writes to the ticket system run as jobs
  of `actions`, outside any turn, so a cancel never cuts one in half.
- Every turn is one trace in Phoenix, with a span per step (speech-to-text, the model, each
  tool, text-to-speech), recorded through `core`'s tracing helpers. The helpers take the turn's
  span as an argument, since Pipecat runs each processor in its own task and an implicit
  current span does not cross tasks.
- The outermost layer turns every error, a crash included, into one shape for its transport,
  with the error's stable code and the request's reference, and never echoes a rejected value
  back (GP-19).
- Models at a boundary reuse core's field types and constraints, so invalid input is rejected
  as invalid input (a validation error, a usage error), never as a server error (GP-20).

## Enforcement

The rules live in [harness.toml](harness.toml), the source of truth;
[scripts/check_architecture.py](scripts/check_architecture.py) applies them (`uv run poe arch`):

- ARCH-LAYER: internal imports follow `[layers]` (an `importlib.import_module` or `__import__`
  of a literal name counts; a computed name cannot be checked, so avoid one), code sits inside
  a layer (a listed facade excepted), a subpackage's narrower rules (`[[subpackages]]`) hold,
  and no layer imports from the package root or a facade;
- ARCH-PUBLIC: an app in `[[apps]]` imports the library only through `[package] public`, and
  no other app; the library never imports an app (an app's modules also follow the module
  rules below; the layer and owner rules are the library's)
  ([scripts/arch_public.py](scripts/arch_public.py));
- ARCH-FACADE: a public facade (`[package] facades`) holds only its docstring, its imports and
  `__all__`, so every public name lives in the layer that owns it
  ([scripts/arch_facade.py](scripts/arch_facade.py));
- ARCH-WORDS: the library's `src/` never holds a word of `[package] banned_words` (the apps'
  names and their own services), in any case, in a file or a file's path
  ([scripts/arch_words.py](scripts/arch_words.py));
- ARCH-OWNER: a library in `[[owners]]` is imported only by its layers;
- ARCH-BAN: a module a `[[bans]]` table names is never imported by the code it covers (the
  library, a part of it, or an app), its `allowed` modules aside. ARCH-OWNER gives a library to
  a layer whole; a ban narrows it by module: the library uses no Pipecat provider or model
  service, none of its LLM machinery (adapters, context aggregators, flows, LLM workers), none
  of its modules that reach an outside host (classifiers, the HTTP Smart Turn, serializers,
  every transport but Small WebRTC), nor its runner, its frame loggers, its torch or numba
  modules, its DTMF aggregator or RTVI; `voice/session/` imports no Pipecat, not even through
  another of the library's modules; and the apps and the examples import neither Pipecat nor
  aiortc ([scripts/arch_ban.py](scripts/arch_ban.py));
- ARCH-CONSTRUCT: a class in `[[restricted]]` is constructed only by its layers, and a name
  in `[[restricted]]` is referred to only there (an import under any alias, an attribute, a
  name, a string that is the name), the module that defines it aside;
- ARCH-PRINT: no `print` or direct writes to standard output outside the files `[rules]`
  allows;
- ARCH-ENV: the environment is read only in the files `[rules]` allows;
- ARCH-DEPS: every outside library the code imports is declared by the code's own project: a
  member's `pyproject.toml` for its `src/`; for `scripts/` and `tests/`, the root's
  dependencies or `dev` group, or a member's. A namespace package that several distributions
  install, such as `opentelemetry`, is matched on its top-level name
  ([scripts/arch_deps.py](scripts/arch_deps.py));
- ARCH-DOC: this doc's layer table matches `[layers]` and `[[owners]]`, row by row
  ([scripts/arch_doc.py](scripts/arch_doc.py)).

The rules for every module, including `scripts/` and `tests/` (a size limit, `# fmt: skip` only
on data tables, valid Python), are in [scripts/module_rules.py](scripts/module_rules.py), with
their settings under `[modules]`. Every violation message includes a FIX line.

To change a rule, update `harness.toml` and this document together (ARCH-DOC fails until the
layer table agrees) and record the reason in [docs/design/decisions.md](docs/design/decisions.md)
(a review: no check reads it).
