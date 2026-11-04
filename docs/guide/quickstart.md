# Quickstart: an echo agent

Run the smallest agent the library serves, [examples/minimal](../../examples/minimal/), and talk
to it in your browser: it says back what it heard, in English, then in Saudi Arabic. This is the
M2 quickstart; the final one, with a talker that answers and an action that needs a spoken yes,
comes in M5.

## Before you start

- **Python 3.12 and uv**, on the machine you will talk from ([is-this-for-you.md](is-this-for-you.md)
  says which systems are checked).
- **A checkout of this repository.** No tagged version exists to install in your own project
  yet, so the quickstart runs from this repository's workspace: `uv sync` at its root installs
  the library and `examples/minimal` together.
- **A Groq key**, in a file outside the repository that holds only the key. The example speaks
  English (`canopylabs/orpheus-v1-english`, voice `troy`) and Saudi Arabic
  (`canopylabs/orpheus-arabic-saudi`, voice `abdullah`): accept each model's terms in Groq's
  console first. Access to the Arabic model may need Groq's account team.
- **Chrome or Edge, and a microphone,** on the same machine as the server.

## The agent

The whole agent, from
[app.py](../../examples/minimal/src/minimal_example/app.py):

```python
from t2_agentic_voice import Language, VoiceAgent, VoiceRuntime, VoiceSettings
from t2_agentic_voice.identity import DevIdentity

# The Saudi greeting, "hala, takallam wa a'eed lak kalaamak": hi, speak and I will say your
# words back to you.
SAUDI_GREETING = (
    "\u0647\u0644\u0627\u060c \u062a\u0643\u0644\u0645 \u0648\u0623\u0639\u064a\u062f "
    "\u0644\u0643 \u0643\u0644\u0627\u0645\u0643."
)

agent = VoiceAgent(
    name="minimal-echo",
    languages=[
        Language.english(greeting="Hi! Say something, and I will say it back."),
        Language.saudi_arabic(greeting=SAUDI_GREETING),
    ],
)


def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The echo agent's runtime, with `settings`, or those the `T2V_*` variables give (nothing
    is read at import)."""
    return VoiceRuntime(
        agent, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
```

- **`name`** is a lowercase word: it names the agent's folder under the data folder
  (`storage.var_dir`, `var` by default) and its traces.
- **`languages`** come from presets, `Language.english`, `Language.saudi_arabic` and
  `Language.arabic` (Modern Standard Arabic), each with your greeting. A preset brings the echo's
  frame ("I heard:", «سمعتك تقول:» in both Arabic presets) and the notices a caller is told (a
  failure, the end of a call), which `notices=` can replace. The first language is a call's when
  nothing picks another.
- **`make_runtime`** is the factory `t2v` and `serve()` take. Building the runtime does no IO:
  the settings are read when it is called, the server's files are opened when it starts.
- **`DevIdentity()`** is the dev caller: it joins only a server whose `env` is `dev`, and only
  from this machine. A runtime for real callers verifies signed join tokens instead
  ([serving.md](serving.md)).

## Run it

In a shell at the repository's root (Git Bash shown; in PowerShell, set each variable with
`$env:T2V_ENV = "dev"`):

```bash
uv sync
export T2V_ENV=dev
export T2V_GROQ__API_KEY_FILE=/full/path/to/groq_api_key
uv run t2v doctor
uv run t2v dev minimal_example.app:make_runtime
```

- **`t2v doctor`** checks what a first call needs, with no synthesis: the key, each language's
  model and voice in Groq's model list (one request), the ONNX files of Silero VAD and Smart
  Turn, and this machine's clock against Groq's, read from the model list's `Date` (its skew,
  to the second, within `join.max_clock_skew_s`). Every line starts `ok` or `FAIL`; a `FAIL`
  says what to fix.
  `t2v doctor --synthesize` also sends one short synthesis per language, the only way to learn
  whether a model's terms are accepted.
- **`t2v dev`** serves the runtime on 127.0.0.1:7860 with its dev page, and only under
  `env` dev. Nothing reads a `.env` file here: the variables come from the shell.
- **At its start** the runtime locks its data folder (`var/runtime.lock`, so a second process
  on the same folder is refused), reads the key, synthesizes each language's greeting, echo
  frame and spoken notices once into `var/minimal-echo/phrases/` (the `runtime_started` line's
  `phrase_requests` says how many requests that took; 0 once they are cached), and loads the
  turn models. It is ready when uvicorn says it is running.

## Talk to it, in English, then in Saudi Arabic

1. Open `http://127.0.0.1:7860/voice/dev` in Chrome or Edge on the same machine.
2. Leave the join token as `dev` (the dev caller reads none) and the language as "The agent's
   first", English here. Press **Start** and allow the microphone.
3. The agent greets you. Say a sentence and pause: it says "I heard:" and your words back,
   and the captions show both. **Stop** or **Esc** cuts it short; **Hang up** ends the call.
4. Pick `ar-SA`, press **Start** again, and speak Saudi Arabic: the greeting, the frame and your
   words come back in the Arabic voice. A call keeps the language it joined with to its end; a
   tag the agent does not speak (`ar` here) joins in its first language.

Each turn sends Groq one Whisper request (at most 30 s of audio) and each echo at most three
Orpheus requests; a call ends itself after 600 s (`limits.max_call_s`) or 120 s with nothing
heard (`limits.idle_s`), telling the caller first. Groq's published limits for Orpheus are low:
[is-this-for-you.md](is-this-for-you.md).

The example also starts itself, `uv run python -m minimal_example`, which serves it the same
way; its dev page then needs `T2V_SERVER__DEV_PAGE=true`. Its entry point is the shape of your own
app's: the logging it sets up is in [tracing-and-logs.md](tracing-and-logs.md), and serving real
callers in [serving.md](serving.md).

## When the first call does not work

Start with `uv run t2v doctor`, then this list.

| What you see | What to do |
| --- | --- |
| `FAIL key` | The line names the setting: set `T2V_GROQ__API_KEY_FILE` to the full path of a file that holds only the key (or `T2V_GROQ__API_KEY`). The library never reads `GROQ_API_KEY`. |
| `FAIL model and voice <tag>` | The key cannot see that model: open the model to the key's organization in Groq's console, or ask Groq for access (the Arabic model). |
| `FAIL synthesis <tag>` (with `--synthesize`) | The model's terms are not accepted: accept them in Groq's console, as the line's FIX says. |
| `FAIL onnx <file>` | The installed Pipecat is damaged: `uv sync --reinstall-package pipecat-ai`. |
| `FAIL clock` | This machine's clock is off Groq's by more than join tokens allow (`join.max_clock_skew_s`, with 1 s for the reading): set it, on Windows with Settings > Time & language > Date & time > **Sync now** (or `w32tm /resync`), elsewhere with NTP. A line saying the skew was not measured passes: no language check passed, or Groq's answers gave no readable `Date`. |
| The server stops as it starts | Its last line says why, with a FIX: `env` is not `dev`; another process holds the data folder (stop it, or give this one its own `T2V_STORAGE__VAR_DIR`); `PIPECAT_SETUP_FILES` or `PIPECAT_SMART_TURN_LOG_DATA` is set (unset it); or a fixed phrase could not be synthesized (run `t2v doctor --synthesize`). |
| `/voice/dev` answers 404 | The dev page answers only `t2v dev`, or a server with `T2V_SERVER__DEV_PAGE=true`, under `env` dev, to a browser on the same machine. |
| `microphone_refused`, `microphone_busy`, `microphone_missing` or `microphone_failed` on the page | Allow the microphone for the page in the browser's site settings; close the program that holds it; plug one in; or open the page at `http://127.0.0.1` or over HTTPS, where a browser allows a microphone. |
| The call never connects, or ends with `transport` | The browser and the backend found no media path over UDP within 20 s. On one machine nothing else is needed; a browser on another network needs an open UDP path or a TURN relay, which come with the deployment, not M2. |
| No voice, but the captions come | Check the browser's output device and volume. |
