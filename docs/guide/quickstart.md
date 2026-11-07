# Quickstart: a helper that answers, and an echo

Run the smallest agents the library serves, [examples/minimal](../../examples/minimal/), and
talk to them in your browser, in English, then in Saudi Arabic:

- **the helper** answers a question about a branch's opening hours: the talker (the chat model
  that writes what the agent says) looks the hours up with one read tool and says them in a
  short sentence. It needs no knowledge base: its tool reads a table of its own.
- **the echo** says back what it heard. It sends no model request, so it is the first check that
  your microphone, the turn-taking and the voices work.

A quickstart with an action taken on a spoken yes comes with confirmed actions, which are not
built yet.

## Before you start

- **Python 3.12 and uv**, on the machine you will talk from ([is-this-for-you.md](is-this-for-you.md)
  says which systems are checked).
- **A checkout of this repository.** No tagged version exists to install in your own project
  yet, so the quickstart runs from this repository's workspace: `uv sync` at its root installs
  the library and `examples/minimal` together.
- **A Groq key**, in a file outside the repository that holds only the key. The example speaks
  English (`canopylabs/orpheus-v1-english`, voice `troy`) and Saudi Arabic
  (`canopylabs/orpheus-arabic-saudi`, voice `abdullah`): accept each model's terms in Groq's
  console first. Access to the Arabic model may need Groq's account team. The helper's replies
  are written by Groq's `openai/gpt-oss-120b` (`llm.model`), which the key must be able to call.
- **Chrome or Edge, and a microphone,** on the same machine as the server.

## The helper

Its tool and its instructions, from
[app.py](../../examples/minimal/src/minimal_example/app.py):

```python
from typing import Annotated

from pydantic import Field
from t2_agentic_voice import Language, VoiceAgent, VoiceRuntime, VoiceSettings, tool
from t2_agentic_voice.identity import DevIdentity

# Today's opening hours of each branch, by its name in lowercase English letters.
HOURS = {"olaya": "8 am to 4 pm", "malaz": "9 am to 5 pm"}


@tool(description="Today's opening hours of one branch, by the branch's name.")
async def opening_hours(
    branch: Annotated[
        str,
        Field(min_length=1, max_length=40, description="The branch's name, such as Olaya."),
    ],
) -> str:
    """The branch's hours today; the branches there are, when it names none of them."""
    hours = HOURS.get(branch.strip().casefold())
    if hours is None:
        return f"No branch has that name. The branches are {', '.join(map(str.title, HOURS))}."
    return hours


# What the helper does, for the talker: the library adds its rules for the ear and the reply's
# language around it.
INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches. When the caller names a branch, "
    "look its hours up with opening_hours, its name in English letters, and say them in one "
    "short sentence. When no branch has that name, say which branches there are. For anything "
    "else, say plainly that you can only tell the branches' hours."
)
```

- **`@tool`** makes a read tool of a function, async as here or sync. The talker calls it by
  its name (the function's), and its `description`, in English, tells the talker when to.
- **Its parameters** are read from the signature, and they are the only schema the talker sees.
  The bound in `Annotated` is checked before the function runs: a branch name of 41 characters
  never reaches it, and the talker is told which field was wrong, so it can try again. The
  bound is pydantic's `Field`: declare `pydantic` in your own project when you import it, as
  the example's `pyproject.toml` does.
- **It returns** a plain string here; any value that is JSON works, and so does a `ToolResult`
  with a card for the screen ([concepts.md](concepts.md), "Tools").
- **A read tool changes nothing.** When the caller speaks over the reply, its tool is cancelled
  or its result thrown away, so it must be safe to stop at any point.
- **`INSTRUCTIONS`** say what the helper is for, when to use the tool, and what to say for
  anything else. The library wraps them in its own rules for the ear (short spoken sentences,
  numbers in digits, tool results read as data) and the reply's language:
  `render_prompt(helper, "en")` shows the whole prompt
  ([writing-for-voice.md](writing-for-voice.md)).

The helper's declaration, from [app.py](../../examples/minimal/src/minimal_example/app.py):

```python
helper = VoiceAgent(
    name="minimal-helper",
    languages=[
        Language.english(greeting="Hi! Which branch's opening hours would you like to know?"),
        Language.saudi_arabic(greeting=HELPER_GREETING),
    ],
    instructions=INSTRUCTIONS,
    tools=[opening_hours],
)
```

- **`name`** is a lowercase word: it names the agent's folder under the data folder
  (`storage.var_dir`, `var` by default) and its traces.
- **`languages`** come from presets, `Language.english`, `Language.saudi_arabic` and
  `Language.arabic` (Modern Standard Arabic), each with your greeting. A preset brings the
  notices a caller is told (a failure, the end of a call), which `notices=` can replace. The
  first language is a call's when nothing picks another; each reply then follows the language
  of the caller's words ([languages.md](languages.md)).
- **`instructions`** make it a talker: an agent with none is an echo. **`tools`** are its read
  tools; a knowledge base joins them as one more ([concepts.md](concepts.md), "Knowledge").

Its runtime, from [app.py](../../examples/minimal/src/minimal_example/app.py):

```python
def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The helper's runtime, with `settings`, or those the `T2V_*` variables give (nothing is
    read at import)."""
    return VoiceRuntime(
        helper, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
```

- **`make_runtime`** is the factory `t2v` and `serve()` take. Building the runtime does no IO:
  the settings are read when it is called, the server's files are opened when it starts.
- **`DevIdentity()`** is the dev caller: it joins only a server whose `env` is `dev`, and only
  from this machine. A runtime for real callers verifies signed join tokens instead
  ([serving.md](serving.md)).

## The echo

The same file declares the echo, with no instructions, and its runtime, in
[app.py](../../examples/minimal/src/minimal_example/app.py):

```python
agent = VoiceAgent(
    name="minimal-echo",
    languages=[
        Language.english(greeting="Hi! Say something, and I will say it back."),
        Language.saudi_arabic(greeting=SAUDI_GREETING),
    ],
)


def make_echo_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The echo's runtime, as `make_runtime` makes the helper's."""
    return VoiceRuntime(
        agent, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
```

The echo says each turn back after a short frame in the call's language ("I heard:", «سمعتك
تقول:» in both Arabic presets), and the language presets give it. Any agent, a talker included,
runs as the echo with `T2V_SESSION__MODE=echo`. (The two Saudi greetings, `HELPER_GREETING` and
`SAUDI_GREETING`, are written in the file with Unicode escapes, as the library writes its
Arabic, each with its sound and meaning in a comment.)

## Run it

In a shell at the repository's root (Git Bash shown; in PowerShell, set each variable with
`$env:T2V_ENV = "dev"`):

```bash
uv sync
export T2V_ENV=dev
export T2V_GROQ__API_KEY_FILE=/full/path/to/groq_api_key
uv run t2v doctor
uv run t2v dev minimal_example.app:make_echo_runtime
```

Then, once the echo works, stop it (Ctrl+C) and serve the helper:

```bash
uv run t2v dev minimal_example.app:make_runtime
```

- **`t2v doctor`** checks what a first call needs, with no synthesis: the key, each language's
  model and voice in Groq's model list (one request), the ONNX files of Silero VAD and Smart
  Turn, and this machine's clock against Groq's, read from the model list's `Date` (its skew,
  to the second, within `join.max_clock_skew_s`). Every line starts `ok` or `FAIL`; a `FAIL`
  says what to fix. `t2v doctor --synthesize` also sends one short synthesis per language, the
  only way to learn whether a model's terms are accepted. It does not check the chat model: a
  key that cannot call it shows on the helper's first answer (the checklist below).
- **`t2v dev`** serves the runtime on 127.0.0.1:7860 with its dev page, and only under
  `env` dev. Nothing reads a `.env` file here: the variables come from the shell.
- **At its start** the runtime locks its data folder (`var/runtime.lock`, so a second process
  on the same folder is refused), reads the key, synthesizes each language's greeting, echo
  frame and spoken notices once into the agent's `phrases/` folder (`var/minimal-helper/` or
  `var/minimal-echo/`; the `runtime_started` line's `phrase_requests` says how many requests
  that took, 0 once they are cached), and loads the turn models. It is ready when uvicorn says
  it is running.

## Talk to it, in English, then in Saudi Arabic

1. Open `http://127.0.0.1:7860/voice/dev` in Chrome or Edge on the same machine.
2. Leave the join token as `dev` (the dev caller reads none) and the language as "The agent's
   first", English here. Press **Start** and allow the microphone.
3. **The echo** greets you. Say a sentence and pause: it says "I heard:" and your words back,
   and the captions show both. **Stop** or **Esc** cuts it short; **Hang up** ends the call.
4. **The helper** greets you with its question. Ask "When does the Olaya branch open today?"
   and pause. The state shows `thinking` while the talker asks the model and the tool runs,
   then the helper says the hours, "8 am to 4 pm", in a short sentence. Ask about a branch it
   does not have, and it names the two it has; ask about anything else, and it says it can only
   tell the branches' hours. Say "stop" over a reply and it stops at once.
5. Pick `ar-SA`, press **Start** again, and speak Saudi Arabic («متى يفتح فرع العليا اليوم؟»,
   when does the Olaya branch open today?): the greeting and the answer come back in the Arabic
   voice. A call joins in the language you picked, and each of the helper's replies follows the
   language you speak in, among the two it speaks; a tag the agent does not speak (`ar` here)
   joins in its first language.

Each turn sends Groq one Whisper request (at most 30 s of audio). The helper's answer sends one
chat request, or two when it calls its tool (one asks for the tool, the next answers from its
result; three at most), and one Orpheus request per clause; the echo's sends at most three
Orpheus requests. A call ends itself after 600 s (`limits.max_call_s`) or 120 s with nothing
heard (`limits.idle_s`), telling the caller first. Groq's published limits for Orpheus are low:
[is-this-for-you.md](is-this-for-you.md).

The example also starts itself, `uv run python -m minimal_example`, which serves the helper the
same way; its dev page then needs `T2V_SERVER__DEV_PAGE=true`. Its entry point is the shape of
your own app's: the logging it sets up is in [tracing-and-logs.md](tracing-and-logs.md), and
serving real callers in [serving.md](serving.md).

## Test it with no key

The example's test holds a call in text, `TextCall`, with a scripted model, `ScriptedLLM`, one
entry per model request: the real session, talker, tool and output guard run, with no audio, no
key and no network. From
[test_helper.py](../../tests/minimal_example/test_helper.py):

```python
llm = ScriptedLLM(
    [  # one entry per model request: the tool call, then the answer from its result
        ScriptedLLM.call_tool("opening_hours", branch="Olaya"),
        ScriptedLLM.reply(reply),
    ]
)
async with TextCall(helper, llm=llm, language=tag) as call:
    turn = await call.user(question)
    await call.advance(10.0)  # the reply plays to its end
    return turn, llm, call.violations
```

and then, in [test_helper.py](../../tests/minimal_example/test_helper.py)'s test, on the turn
it returns:

```python
turn.expect.tool_call("opening_hours", branch="Olaya")
turn.expect.said(contains=heard)
turn.expect.language(tag)
```

The test runs in English and in Saudi Arabic: `uv run poe test` runs it with the rest, and
[evaluation.md](evaluation.md) ("Testing an agent in text") has the rest of the kit.

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
| The call never connects, or ends with `transport` | The browser and the backend found no media path over UDP within 20 s. On one machine nothing else is needed; a browser on another network needs an open UDP path or a TURN relay, which come with the deployment, not built yet. |
| No voice, but the captions come | Check the browser's output device and volume. |
| The echo works, but the helper says its error notice after every question | The chat model's request failed: the server logs `talker_failed`, and a runtime's observers get `ProviderFailed` with its kind. Check that the key can call `llm.model` in Groq's console, or set `T2V_LLM__MODEL` to a model it can call ([settings.md](../generated/settings.md) lists them). |
