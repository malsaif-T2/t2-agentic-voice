# Tracing and logs

What the library logs and how your app shows it; what it does with Pipecat's own lines; and the
traces it sends to Phoenix or to your own tracer provider (D-023, D-031).

## Logs

The library logs through Python's standard `logging`, under the logger `t2_agentic_voice`,
which has a `NullHandler`: importing the library prints nothing, and it never adds a handler to
the root logger. Each line is an event, a snake_case name with its fields (`call_started`
`call_id=... language=en`).

- **Lines at INFO and above hold no call content:** IDs, timings, counts and outcomes, never what
  was said, a token or a key. The setting `logging.content` lets the WebRTC stack's lines below
  WARNING through (they hold addresses and SDP), and only `env` dev allows it.
- **Levels:** `logging.level` is INFO by default; `staging` and `prod` refuse DEBUG.
- **Format:** `logging.format` is `console` (one readable line) or `json`.

Your app shows the lines with `configure_logging`, once, at its start. Pass it, as `loggers`, your
own package and `__main__`, since a command run with `python -m` logs as `__main__`, not under
your package; and `uvicorn` when you run uvicorn. `examples/minimal` names its loggers in
[\_\_init\_\_.py](../../examples/minimal/src/minimal_example/__init__.py):

```python
LOGGERS = (__name__, "__main__")
```

and sets up logging from the settings before it serves, in
[\_\_main\_\_.py](../../examples/minimal/src/minimal_example/__main__.py):

```python
    settings = VoiceSettings.from_env()
    logs = settings.logging
    configure_logging(logs.level, logs.format, loggers=(*LOGGERS, "uvicorn"), content=logs.content)
    serve(partial(make_runtime, settings))
```

`configure_logging` puts one handler on `t2_agentic_voice` and on each logger named, writing to
standard output unless given a `stream`, and replaces the one an earlier call put; the root
logger and your other handlers are left alone. `t2v serve` and `t2v dev` call it for you, with
the package of `APP`, `__main__` and `uvicorn`. Give uvicorn `log_config=None`, as `serve()`
does, or its own handlers print its lines twice. Your own modules log the same way, with
`get_logger(__name__)` from the package root.

## Pipecat's own lines

Pipecat, which carries each call, logs through loguru, a logger for the whole process, and its
lines below WARNING hold call content. The library switches Pipecat's loguru namespace off before
it first imports Pipecat (`logging.pipecat = "off"`, the only value): no line of Pipecat's
reaches any sink, loguru's default one included, and no sink is added or removed, so your own
loguru lines are unchanged. Pipecat's failures still show, as the library's own lines
(`transport_failed`, `pipeline_failed`) and as the events `TransportFailed` and
`ProviderFailed`. Forwarding Pipecat's warnings to the library's logger waits for the owner's
ruling (D-031).

## Traces

The library sends its own spans as plain OTLP over HTTP. It never installs a tracer provider
globally and never instruments another library.

- **To Phoenix, or any OpenTelemetry backend:** set `T2V_TRACING__ENDPOINT` to its OTLP/HTTP
  traces endpoint, such as a local Phoenix's `http://127.0.0.1:6006/v1/traces`, and
  `T2V_TRACING__PROJECT` to file the spans under a project. The library builds a private
  provider for it inside the runtime's lifespan.
- **To your own provider:** pass `VoiceRuntime(..., tracer_provider=your_provider)`; the spans
  join your traces and your provider is left as it is.
- **Neither:** no span leaves the process.

Phoenix is run beside your app, never installed with it (its Elastic License 2.0 allows running
it inside T2, not offering it as a service). Plan 002 ran it on this machine with
`uvx --from "arize-phoenix==21.0.0" phoenix serve`, `PHOENIX_HOST=127.0.0.1` and a
`PHOENIX_WORKING_DIR` of its own: without `PHOENIX_HOST`, Phoenix may listen on every network
interface with no login, and its traces hold what callers said. How long it keeps them:
[data-and-privacy.md](data-and-privacy.md).

### What a trace holds

One trace per turn, and one for the call itself, grouped by call: Phoenix's session is the
call's ID (`session.id`), which is no credential.

| Span | Its attributes |
| --- | --- |
| `turn`, the root of each turn's trace | The resource attributes below, the turn's number, and at its end its outcome and times; on a turn whose reply lost a character to the stray-script filter, `turn.stray_characters` (how many were taken out or rewritten) and `turn.stray_scripts` (their kinds, comma-separated, such as `CJK,PICTOGRAPH`); with `tracing.include_transcripts`, what was heard (`input.value`) and what its reply said (`output.value`) |
| `speech_to_text`, under its turn | The model, the audio's length, the language sent, the language and billed seconds returned, and the transcript (`tracing.include_transcripts`, on by default) |
| `text_to_speech`, one per reply, under its turn (the greeting and a notice under the call) | With `tracing.include_transcripts`, the reply's text (`input.value`); the model, the voice, the language, the characters sent, the chunks played, the requests, the phrases played from the cache, the time to first audio, and whether a take came back cut short; never the text |
| `tool`, one per tool call, under its turn | The tool's name, `tool.ok`, and when it failed `tool.failure`: what failed, such as `timeout at search` or `bad_arguments`; with `tracing.include_transcripts`, the arguments the model wrote, after the stray-script filter (`input.value`), so a search's text, and what the tool gave back (`output.value`), so the passages it found |
| `call`, the root of the call's own trace | The resource attributes, and the call's report in numbers, with no text |

The talker's model requests have no span of their own yet: each model's requests and tokens are
in the call's report (`ModelUsage`, and the `call` span's numbers), and each turn's time to the
model's first token in its times ([latency.md](latency.md)). Each tool call also reaches a
runtime's observers as `ToolStarted` and `ToolFinished`, with the arguments the model wrote
and what the tool gave back, which the test console shows
([browser-client.md](browser-client.md), "The test console").

What a reply said, in its span and its events, is the text after the stray-script filter
(D-084; [languages.md](languages.md), "Scripts a reply may hold"), and so are a tool call's
arguments: the trace holds what the caller heard, never the characters taken out. Each model
request whose answer lost any also logs one line at INFO, `talker_stray_script_removed`, with
`call_id`, `turn_id`, `characters` (how many) and `scripts` (their kinds), never a character or
a word of the reply.

A reply that stopped before a question past its limit (`guard.questions_per_reply`, D-085;
[writing-for-voice.md](writing-for-voice.md), "One question at a time") logs one line at INFO,
`talker_reply_stopped`, with `call_id`, `turn_id`, `reason` (`question_limit`) and
`unsaid_clauses` (how many of the talker's clauses it did not say), never a word of the reply.
The trace holds only what was said.

The resource attributes, on each root span: `t2v.version`, `t2v.pipecat.version`,
`t2v.settings.digest` (a hash of the settings with every secret left out), `t2v.agent.name`,
`t2v.models` and, when the caller's consent names one, `t2v.consent.version`.

Audio, secrets (the offer secret among them) and exception messages are never exported: a
failed span names its exception's type alone. Spans go through a bounded queue to a worker
thread, so an exporter that fails or hangs never touches a call; the spans it drops are counted.

### Redaction

`T2V_TRACING__REDACT` is a JSON list of regular expressions; every match is replaced with
`[redacted]` in every text a span holds, keys included, before it leaves the process. To keep
transcripts out of traces altogether, set `T2V_TRACING__INCLUDE_TRANSCRIPTS=false`.
