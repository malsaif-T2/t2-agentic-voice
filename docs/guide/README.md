# T2 Agentic Voice: the guide for teammates

How to add a speech-first voice agent to your own product with T2 Agentic Voice: install the
library, declare your use case, add your tools and the actions that need a spoken yes, test it
without a microphone or a key, and run it.

**Status: nothing to install yet.** The library's public API is designed, and M1 built its
first public modules (`ports`, `groq`, `languages`, `evals` and `tracing`): the design is
[package-design.md](../design/package-design.md) (D-017, approved as amended by D-018), and its
section 3 is the contract, what the library provides and what your app must provide. The first
version is used from Python only (D-014). Each page below is written when the part it describes
lands in the library, with the milestone named in its row ([roadmap](../plans/roadmap.md)); code
samples on these pages are taken from tested files, so a page never shows code that does not
run (`poe docs` checks it, DOC-SAMPLE: a block after a link to a `.py` file must be a run of
that file's lines).

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
  one, but a `content-type` line makes every request fail, as a `rejected` provider error.
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
  runner: each file it names is run inside every call, so a shell variable can load code.
- `PIPECAT_SMART_TURN_LOG_DATA`, read when Smart Turn's analyzer is built: true writes the
  caller's audio of every turn it analyses as WAV files under `smart_turn_audio_log` in the
  working folder, whatever the caller consented to, and a value Pipecat reads as neither true
  nor false makes the analyzer fail.
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
  (its provider services); `poe arch` keeps all but the transports out of the library's
  imports (ARCH-BAN).
- The proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`; on Windows, the
  Internet Options proxy when none of them is set) and the CA variables (`SSL_CERT_FILE` and
  `SSL_CERT_DIR` for httpx, under `groq`; `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` for
  requests, under the trace exporter) are trusted by both HTTP clients: a proxy they name
  carries the key, the audio and the transcripts, and a CA they name is trusted for Groq and
  the trace backend. No `T2V_` setting turns them off yet, so set them only for a proxy and a
  CA you trust (TD-004, TD-015).

## Pages

| Page | What it will cover | Lands with |
| --- | --- | --- |
| `contract.md` | What the library provides, what you must provide, and what you may provide, with the default for each | M0 (fixed then, D-018); not written yet, and when it is written is an open question in the roadmap |
| `is-this-for-you.md` | The fit check: Python version, operating system, the heavy dependencies, one process per data folder and the sidecar, network needs (UDP or TURN), Groq's published limits, the licences | M2 |
| `quickstart.md` | `examples/minimal` end to end, English first, then Saudi Arabic; a checklist for a first call that does not work | M2 (an echo agent), M5 (the final quickstart) |
| `concepts.md` | The talker, tools, actions, turns, the two-step interruption, the cancel scope, the history of what the caller heard; one turn in a diagram | M3 |
| `writing-for-voice.md` | Instructions written for speech, tool descriptions, read-backs, claim phrases, send words and spoken labels, each with a good and a bad example | M4 |
| `tools-and-actions.md` | Writing each kind, wrapping existing functions, the action lifecycle, consent, the error table, idempotency and lookups | M5 |
| `safety.md` | How the yes rule and the output guard work; what the library guarantees and what stays yours | M5 |
| `languages.md` | Language presets, the reply language, normalization, speaking numbers and IDs, spoken labels, vocabulary, pronunciation | M4 |
| [settings.md](../generated/settings.md) (generated, `uv run poe settings-ref`) | Every setting, with its default, unit and environment name | M2 (written) |
| `serving.md` | The sidecar or the mount, identity and join tokens, cross-origin pages, the browser protocol | M2 |
| `browser-client.md` | The reference browser client: its events and states, tokens, consent, Stop and Esc | M2, M3 |
| `testing.md` | Text calls, the fakes, the safety suite for your actions, live scenarios, audio replay | M5 |
| [evaluation.md](evaluation.md) | The evaluation helpers; recording your own test set with consent and keeping audio out of git; writing your own spelling guide; the golden-set commands, making a registered run and reading its scorecard; noise and the sign test; held-out and window runs; the run history | M1 |
| `latency.md` | Where the time goes in a turn, and how to measure yours | M4 |
| `tracing-and-logs.md` | Phoenix or your own tracing, redaction, what a trace holds, the logging policy | M2 |
| `data-and-privacy.md` | What the library itself stores and sends: what a trace holds, the data folder, recording and consent | M2 |
| `audio-troubleshooting.md` | Echo on laptop speakers, Bluetooth headsets, microphone permissions, UDP and TURN failures | M3 |
| `deployment.md` | The process model, containers, TURN, drain, health, capacity | M6 |
| `runbook.md` | Rate limits and outages, a stuck write, key rotation, a deletion request | M6 |
| `providers.md` | Writing an adapter for another speech, model or voice provider | M4 |
| `cookbook/` | Worked use cases with no Ole5 code: an IT helpdesk, HR leave | M5, M7 |
| `reference/api.md` (generated) | The public modules, from their docstrings, with each module's stability | M2 onward |
| `upgrading.md` | Versions, stability levels, deprecations, behaviour changes | The first version a teammate installs |
