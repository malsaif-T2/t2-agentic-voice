# T2 Agentic Voice: the guide for teammates

T2 Agentic Voice is a Python library for speech-first voice agents: a caller talks to your
agent in the browser, in Saudi Arabic, Modern Standard Arabic or English, and hears it answer.
This guide shows how to add one to your own product.

**Status: an agent that answers, and acts on a spoken yes.** What works today: the browser
opens a live call to your backend over WebRTC; the library hears when the caller has finished a
turn (Silero VAD and Smart Turn v3.2, on the CPU, with a hold after "complete"), sends the turn
to Groq's Whisper, and the **talker**, Groq's chat model with your instructions, answers it: it
reads what the caller heard, calls your read tools and your knowledge base, speaks its reply
clause by clause through Groq's Orpheus voices while it still writes, and says an ID only when a
tool or the caller gave it ([concepts.md](concepts.md)). The talker can also propose an
**action** of yours, one change in your system: the library reads it back aloud from your
template, carries it out only after the caller's clear yes, heard once the read-back's summary
has played whole, as a job of its own that a stop never cuts in half, and then says how it ended
from your backend's real answer; the output guard blocks a sentence that claims an action the
call's record does not hold ([tools-and-actions.md](tools-and-actions.md),
[safety.md](safety.md)). The caller can speak over the agent: its voice is lowered at once, a
stop or real words stop it, and the talker reads what they meant. An agent with no instructions
is an **echo**, which says back what it heard: a team's first audio check. Around it: serving (a
process of its own, or mounted in your FastAPI app), signed join tokens, the reference browser
client, settings, logs, traces, and a call held in text for your tests, with a safety suite for
your actions ([testing.md](testing.md)). Actions are tested in text calls on fake models, on the
example's action and on Ole5's mock ticket system, in Ole5's scripted calls on a real model (run
A), and in the owner's first live calls against that mock (plan 007). Not built yet: the deployment with TURN, which
has a plan of its own once a server is available ([roadmap](../plans/roadmap.md)). The library
is used from Python only (D-014), and no tagged version exists to install yet: until the first
one, run it from this repository's workspace ([quickstart](quickstart.md)). The design is
[package-design.md](../design/package-design.md) (D-017, as amended by D-018).

Code samples on these pages are taken from tested files: a block after a link to a `.py` file is
a run of that file's lines, which `poe docs` checks (DOC-SAMPLE).

## The contract in brief

The design's section 3 is the full contract; for an agent that answers and acts, it comes to
this.

| The library provides | Your app provides |
| --- | --- |
| The call: WebRTC in your backend process, end of turn, Whisper, Orpheus, captions, Stop, interruptions | A `VoiceAgent`: a name and its languages, each with a greeting |
| The talker: the chat model's turn from what the caller heard, its prompt's rules for the ear (and for actions, when the agent has one), the reply's language, clauses spoken as they are written | Its `instructions`, written for the ear ([writing-for-voice.md](writing-for-voice.md)) |
| `@tool`, `Tool.from_function` and `knowledge_tool`, run with their arguments checked, a timeout and a progress line; cards, an extra for a client with a screen | Its read tools over your own systems, and a `KnowledgeBase` adapter for your knowledge base ([concepts.md](concepts.md)) |
| `@action`, with `ReadBack`, `Say`, `Claims` and `Spoken`: the draft parsed, then your `validate` if you give one; the read-back said from your template, with nothing shown; the write run as a job outside the turn, which a stop never cuts in half; a line while it runs, then how it ended, said from your backend's real answer; the library's own lines for those you leave out | Each action's function over your backend, reached by a closure; its draft model; its read-back (a summary and a closing question), its `done` line and its claim phrases in every language it speaks, written for the ear ([tools-and-actions.md](tools-and-actions.md), [writing-for-voice.md](writing-for-voice.md)) |
| The yes rule, the only way to a confirmed action: the caller's own words, heard through Whisper once the read-back's summary played whole, read on each preset's yes, send and no words; with `ask_on_unlisted_answers`, a chat model's word on what its lists leave unplaced, within its rails | Your own send words when your closing question's verb is on no list (`send_words`, `words.send`), and whether your agent asks the model ([safety.md](safety.md)) |
| The output guard: no ID-shaped number said without evidence from the call, and, for an agent with actions, no claim phrase without the record or a `reports_on` result | The IDs your tools return, as evidence; your actions' claim phrases, and `reports_on=` on your status tools |
| The outbox and the record: a row with the write's `request_id` before each write (SQLite, in the agent's data folder), never sent again blindly; the rows a stopped process left `sending` looked up or flagged at the next start; `t2v outbox` to list, show and reconcile them; the record of the call's completed actions, which the guard reads | Idempotency in your backend, keyed on `request_id`; a `lookup` where your backend can find a write by it; someone who reconciles a flagged row ([tools-and-actions.md](tools-and-actions.md)) |
| The caps: `max_per_call` on each action (1 by default) and `limits.actions_per_caller_per_day` (20), each refused before the read-back | The caps your use case needs |
| `TextCall`, `ScriptedLLM`, `FunctionLLM` and `FakeKnowledgeBase`, to test an agent with no key, its read-backs and the caller's answers to them included ([testing.md](testing.md)) | Your tests |
| `ActionSafetySuite`: the library's adversarial cases, run on your action in text calls | A subclass of it in your tests, with `make_agent()`, `action_under_test()` and `sample_draft()` ([testing.md](testing.md)) |
| `VoiceRuntime`, served by `serve()`, `t2v serve`, `t2v dev`, or mounted with `runtime.router()` | One process with one worker per data folder (`storage.var_dir`), and a serving shape ([serving.md](serving.md)) |
| `SignedJoinTokens` to mint and verify join tokens; `DevIdentity` for `env` dev on your machine | An identity source: your website or app mints a join token for each caller, with their consent |
| `t2v-client.js`, the reference browser client, and a dev page | A page with a consent screen, served over HTTPS or from localhost ([browser-client.md](browser-client.md)) |
| `VoiceSettings`, loaded from `T2V_*` variables or built in code | `env` (dev, test, staging or prod; no default) and a Groq key that can call the chat model, with each Orpheus model's terms accepted |
| Structured logs and traces, with no call content in logs at INFO and above | A logging configuration, and a trace backend if you want traces ([tracing-and-logs.md](tracing-and-logs.md)) |

What the library stores and sends is [data-and-privacy.md](data-and-privacy.md); whether it fits
your product is [is-this-for-you.md](is-this-for-you.md).

## The quickstart, in short

From a checkout of this repository, with a Groq key in a file outside it
([quickstart.md](quickstart.md) has the details and a checklist for a first call that fails):

```bash
uv sync
T2V_ENV=dev T2V_STT__PROVIDER=groq T2V_GROQ__API_KEY_FILE=/path/to/groq_api_key uv run t2v dev minimal_example.app:make_runtime
# then, in Chrome or Edge on the same machine: http://127.0.0.1:7860/voice/dev
```

## Variables to leave unset

The library's settings are one `VoiceSettings`: built in code, or loaded by
`VoiceSettings.from_env()` from the `T2V_*` environment variables, and from a `.env` file only
when `env_file=` names one; `env` (dev, test, staging or prod) has no default
([.env.example](../../.env.example) lists them, and the generated
[settings.md](../generated/settings.md) describes each). The packages under it read some
variables of their own whatever the library passes, so a process that uses the library leaves
these unset, or, for the proxy and CA variables, sets only values it trusts (the other docs
point here rather than list them, and the debt rows named say why each is still read):

- `GROQ_LOG`, read when `groq` is imported: `debug` or `info` adds a handler to the root logger
  and sets the `groq` and `httpx` loggers' levels, and at DEBUG the SDK logs each request's
  options, the audio and the prompt included. The library undoes this only when it is the first
  to import `groq`. Even with `GROQ_LOG` unset, a root or `groq` logger at DEBUG gets those
  request options, so keep both above DEBUG (TD-003).
- `GROQ_CUSTOM_HEADERS`, read by the Groq SDK when the adapter builds its client: the adapter
  replaces every header with its own on each request, so no line of it adds a header or changes
  one, but a `content-type` line makes every request that sends a body (a synthesis, a
  transcription) fail, as a `rejected` provider error, while the model list still answers, so
  `t2v doctor` shows it only with `--synthesize`.
- `OTEL_SDK_DISABLED` turns the library's own tracer provider off: no span is exported, and the
  library logs `tracing_disabled_by_sdk` (TD-005).
- `OTEL_PYTHON_CONTEXT`, read when `opentelemetry.context` is imported, before any of the
  library's code runs, loads the entry point it names, so a shell variable can load code
  (TD-005).
- `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`, read in a child process forked after the library's
  tracer provider was built, loads the entry points it names (TD-005).
- `OTEL_PROPAGATORS`, read when `fastapi` is imported, loads the entry points it names, and a
  name it does not know makes the import fail.
- `FASTAPI_OTEL_AUTO_CONFIGURE`, read when a FastAPI app is built: true adds OpenTelemetry
  exporters, from the `OTEL_*` variables, when the app starts, to a provider already set up
  too, unless the app is built with `telemetry={"auto_configure": False}`.
- `PIPECAT_SETUP_FILES`, read each time Pipecat sets up a call's pipeline and starts its
  runner: each file it names is run inside every call, so a shell variable can load code. The
  runtime refuses to start while it holds any value, naming it.
- `PIPECAT_SMART_TURN_LOG_DATA`, read when Smart Turn's analyzer is built: true writes the
  caller's audio of every turn it analyses as WAV files under `smart_turn_audio_log` in the
  working folder, whatever the caller consented to. The runtime refuses to start while it holds
  any value, naming it.
- `PIPECAT_SCTP_MAX_CHUNK_SIZE`, read when Pipecat's WebRTC connection module is imported,
  sets the data channel's chunk size for the whole process, and a value that is not a whole
  number makes the import fail.
- `LOGURU_*`, read when loguru is imported (Pipecat imports it): they set loguru's default
  output and a level's number for the whole process, which no code can change back, and a
  value of the wrong kind makes the import fail.
- `WEBSOCKETS_*`, read when websockets is imported (Pipecat's speech-service base classes
  import it), set its limits and the headers it sends for the whole process, and a limit that
  is not a number makes the import fail.
- `ORT_LOAD_CONFIG_FROM_MODEL`, read when onnxruntime builds a session: `1` takes the
  session's options from the model's file, for Silero's and Smart Turn's sessions too, which
  pass no override.
- `FORWARDED_ALLOW_IPS` and `WEB_CONCURRENCY`, read by uvicorn only when the code passes no
  `forwarded_allow_ips` or `workers`: by default it trusts `X-Forwarded-For` from 127.0.0.1
  and ::1, so any local client can set its own address, and `WEB_CONCURRENCY` with an app
  object makes `uvicorn.run` exit. A process that runs uvicorn itself passes both. uvicorn's
  command line also takes every option from `UVICORN_*` (`UVICORN_ENV_FILE` loads a `.env`).
- Read only by parts of Pipecat the library does not use: `PIPECAT_LOG_LLM_CONTEXT` and
  `PIPECAT_ALLOWED_FILE_URL_NETWORKS` (its model services), `PIPECAT_ALLOWED_ORIGINS` (its
  WebSocket transports), `NUMBA_*` and `LLVMLITE_*` (its resampy resampler), and `OPENAI_*`
  (its provider services); `poe arch` keeps them all out of the library's imports (ARCH-BAN).
- The proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`; on Windows, the
  Internet Options proxy when none of them is set) and the CA variables (`SSL_CERT_FILE` and
  `SSL_CERT_DIR` for httpx, under `groq`; `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` for
  requests, under the trace exporter) are trusted by both HTTP clients: a proxy they name
  carries the key, the audio and the transcripts, and a CA they name is trusted for Groq and
  the trace backend. No `T2V_` setting turns them off yet, so set them only for a proxy and a
  CA you trust (TD-004, TD-015).

## Pages

Each page is written when the part it describes is built. The pages written so far are linked.

| Page | What it covers | Status |
| --- | --- | --- |
| [is-this-for-you.md](is-this-for-you.md) | The fit check: Python version, operating system, the install's size and its heavy dependencies, one process per data folder and the sidecar, network needs, Groq's published limits, the licences | Written |
| [quickstart.md](quickstart.md) | `examples/minimal` end to end: a helper that answers with one read tool, and an echo, in English, then in Saudi Arabic; the helper with an action, a callback read back and booked on a spoken yes; their tests with no key; a checklist for a first call that does not work | Written |
| [concepts.md](concepts.md) | Turns and replies; the talker's turn; tools, progress lines, knowledge and cards; the output guard's ID rule; confirmed actions, from the talker's call to the outcome, the caller's answer and the record of completed actions; the two-step interruption and its words, handed to the talker; the cancel scope; the history of what the caller heard; the repeat; text from silence; the hold after the end of a turn | Written |
| [tools-and-actions.md](tools-and-actions.md) | Writing a read tool and an action, wrapping a function you already have as either, the lines an action speaks, one action in a call, the error table, writing at most once, the caps, lookups and status tools | Written |
| [safety.md](safety.md) | How the yes rule decides and why a yes over the closing question needs a send word; the model check of the words its lists cannot place; the output guard's ID and claim rules; what the library guarantees, what stays yours, and what the rules do not catch | Written |
| [writing-for-voice.md](writing-for-voice.md) | Instructions written for the ear, every step said by voice, numbers as digits, a plain "I cannot", no promise the agent cannot keep, tool descriptions, greetings and progress lines; an action's words: the read-back's summary and closing question, the lines while the write runs and when no clear answer came, claim phrases and send words; and why no fixed line holds a command word; each with a weak and a better example | Written |
| [languages.md](languages.md) | The presets, the call's language and each reply's, Saudi Arabic and MSA, product terms inside Arabic, the pronunciation map, numbers and IDs, the vocabulary | Written |
| [latency.md](latency.md) | The time to first audio, from where to where; where the time goes in a turn; the early start, connections kept open and progress lines; the budget; measuring yours | Written |
| [serving.md](serving.md) | The sidecar or the mount, one process per data folder, identity and join tokens, which agent a served app runs, the routes, cross-origin pages, the browser protocol | Written |
| [browser-client.md](browser-client.md) | The reference browser client: starting a call, its events and states, cards and the agent thinking, tokens and consent, Stop and Esc, the agent's voice lowered, cut captions, push-to-talk, errors, browser support | Written |
| [tracing-and-logs.md](tracing-and-logs.md) | The logging policy and `configure_logging`, Pipecat's own lines, Phoenix or your own tracer provider, what a trace holds, redaction | Written |
| [data-and-privacy.md](data-and-privacy.md) | What the library itself stores and sends: the data folder, recordings and consent, what a trace holds, how long Phoenix keeps it | Written |
| [settings.md](../generated/settings.md) (generated, `uv run poe settings-ref`) | Every setting, with its default, unit and environment name | Written |
| [testing.md](testing.md) | Testing an agent in text with `TextCall`, the fake models and the fake knowledge base; a call with an action, from the request to the read-back, the yes and the write; a fake model that answers the yes rule's check; `ActionSafetySuite` on your actions; live scenarios on a real model; audio replay | Written |
| [evaluation.md](evaluation.md) | Measuring speech-to-text on your own voices: the evaluation helpers; recording your own test set with consent and keeping audio out of git; writing your own spelling guide; the golden-set commands, making a registered run and reading its scorecard; noise and the sign test; held-out and window runs; the run history | Written |
| `contract.md` | What the library provides, what you must provide, and what you may provide, with the default for each | Fixed in the design (D-018); when it is written is an open question in the roadmap |
| `audio-troubleshooting.md` | Echo on laptop speakers, Bluetooth headsets, microphone permissions, UDP and TURN failures | Not planned yet: left out with the Bluetooth warning (plan 005) |
| `providers.md` | Writing an adapter for another speech, model or voice provider | Not written yet: with the guide's last pages |
| `deployment.md` | The process model, containers, TURN, drain, health, capacity | With the deployment |
| `runbook.md` | Rate limits and outages, a stuck write, key rotation, a deletion request | With the deployment |
| `cookbook/` | Worked use cases with no Ole5 code: an IT helpdesk, HR leave | With the guide's last pages (M7) |
| `reference/api.md` (generated) | The public modules, from their docstrings, with each module's stability | The first version a teammate installs |
| `upgrading.md` | Versions, stability levels, deprecations, behaviour changes | The first version a teammate installs |
