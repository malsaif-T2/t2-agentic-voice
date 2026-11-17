# Quickstart: a helper that answers, an action on a spoken yes, and an echo

Run the smallest agents the library serves, [examples/minimal](../../examples/minimal/), and
talk to them in your browser, in English, then in Saudi Arabic:

- **the helper** answers a question about a branch's opening hours: the talker (the chat model
  that writes what the agent says) looks the hours up with one read tool and says them in a
  short sentence. It needs no knowledge base: its tool reads a table of its own.
- **the echo** says back what it heard. It sends no model request, so it is the first check that
  your microphone, the turn-taking and the voices work.

Then meet the helper with one action: it asks a branch to call the caller back, reads the request
back aloud, and books it only after the caller's clear yes. The example holds that call in text,
in its tests, with no key ("An action on a spoken yes", below).

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
  ([concepts.md](concepts.md), "Tools").
- **A read tool changes nothing.** When the caller speaks over the reply, its tool is cancelled
  or its result thrown away, so it must be safe to stop at any point. What changes something is
  an action ("An action on a spoken yes", below).
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
  first language is a call's when nothing picks another. Each reply follows the language its
  turn's transcript is in, and since Whisper is told the call's language, that is most often
  the call's own ([languages.md](languages.md)).
- **`instructions`** make it a talker: an agent with none is an echo. **`tools`** are its read
  tools; a knowledge base joins them as one more ([concepts.md](concepts.md), "Knowledge"), and
  so does an action (below).

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
export T2V_STT__PROVIDER=groq   # Whisper on the Groq key alone; or set T2V_ELEVENLABS__API_KEY for the default, Scribe v3 (D-105)
export T2V_TTS__PROVIDER=groq   # Orpheus on the Groq key alone; with the ElevenLabs key, the default voice (D-114)
uv run t2v doctor
uv run t2v dev minimal_example.app:make_echo_runtime
```

Then, once the echo works, stop it (Ctrl+C) and serve the helper:

```bash
uv run t2v dev minimal_example.app:make_runtime
```

- **`t2v doctor`** checks what a first call needs, with no synthesis: the key, each language's
  model and voice in Groq's model list (one request for each language of `tts.languages`, three
  by default), the ONNX files of Silero VAD and Smart
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
   voice. A call joins in the language you picked; a tag the agent does not speak (`ar` here)
   joins in its first language. Each of the helper's replies follows the language its turn's
   transcript is in. Whisper is told the call's language, so speech in the other one is mostly
   written in the call's own, and the reply follows it there (plan 006's run X). A classifier
   of each turn's language is off by default, measured before it is promised (plan 007's run
   H; [languages.md](languages.md)). To ask in English, pick English in the client.

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

## An action on a spoken yes

[callback.py](../../examples/minimal/src/minimal_example/callback.py) gives the helper one
action, `request_callback`: a branch calls the caller back. The talker collects the branch and
what the call is about; the library reads the request back aloud, books it only after the
caller's clear yes, then says how it ended from the desk's real answer. The desk is made up and
held in memory (`CallbackDesk`), so the example reaches no real system. How the parts fit
together is in [concepts.md](concepts.md) ("Confirmed actions").

### The draft

What the talker gives, from
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
class CallbackRequest(BaseModel):
    """What the talker gives to ask a branch to call the caller back: the branch, a fixed value
    the read-back says by its label, and the reason, in a few of the caller's own words."""

    branch: Annotated[
        Literal["olaya", "malaz"],
        Spoken({"olaya": {"en": "Olaya", "ar": OLAYA}, "malaz": {"en": "Malaz", "ar": MALAZ}}),
        Field(description="The branch that calls back."),
    ]
    reason: Annotated[
        str,
        Field(min_length=1, max_length=120, description="What the call is about, briefly."),
    ]
```

- **A draft** is a pydantic model, and the only schema the talker sees for the action. A field
  it does not hold is refused, so no argument can say the caller agreed (a `confirmed` field,
  say).
- **`branch`** is a fixed set: a branch outside it is told back to the talker, the field named,
  before anything is read back. `Spoken` gives the label the read-back says for each value, in
  each language: "Olaya" in English, «العليا» in Arabic (`OLAYA`, written above it in the file).
- **`reason`** is free text, at most 120 characters, which the read-back says as the talker
  wrote it.

### The action

From [callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
def callback_action(desk: CallbackDesk) -> Action:
    """The action, booking at `desk`, which it reaches by a closure: read back aloud, booked
    only after the caller's yes, and looked up by its request ID when the desk's reply was
    lost."""

    @action(
        description=(
            "Ask a branch to call the caller back. Collect the branch and what the call is "
            "about first."
        ),
        read_back=ReadBack(
            {
                "en": (
                    "I'll ask the {branch} branch to call you back about: {reason}.",
                    "Shall I send it?",
                ),
                "ar": (SAUDI_SUMMARY, SAUDI_QUESTION),
            }
        ),
        done=Say(en="Done, your callback number is {number:id}.", ar=SAUDI_DONE),
        claims=Claims(
            {
                "en": ["callback is booked", "booked your callback", "asked the branch to call"],
                "ar": SAUDI_CLAIMS,
            }
        ),
    )
    async def request_callback(ctx: ActionContext, draft: CallbackRequest) -> CallbackBooked:
        return desk.book(ctx.request_id, draft)

    @request_callback.lookup
    async def find_callback(ctx: ActionContext, request_id: str) -> CallbackBooked | None:
        return desk.find(request_id)

    return request_callback
```

- **`@action`** reads the draft and the result from the function's signature: the `draft`
  parameter's model, and the return annotation, `CallbackBooked`, the desk's answer (a
  four-digit `number`). Its `ActionContext` gives what a tool's `CallContext` does (the caller,
  the call's ID, the language), and `request_id`, the words that confirmed it (`consent`, for
  your audit) and what each side said in the call (`conversation`).
- **`description`**, in English, tells the talker when to call it, as a tool's does.
- **`read_back`** gives each language a pair, the summary then the closing question, filled from
  the draft. A text keyed `ar` serves both Arabic presets, so the helper's `ar-SA` calls read it.
  Each closing question holds a send word ("send it"; «أرسل», send): a yes said over the
  question needs one too (below). Nothing is shown: the caller only hears it.
- **`done`** is said once the desk really booked it, filled from its real answer, never from the
  model's words: `{number:id}` says the number digit by digit.
- **`claims`** are the ways the agent might say it has booked one. The output guard blocks a
  sentence holding one until the call's record holds a booking ([concepts.md](concepts.md),
  "Confirmed actions").
- **The function** books at the desk, which it reaches by a closure, `callback_action(desk)`:
  your action reaches your system the same way. It gives the desk `ctx.request_id`, the ID the
  library gives each write, and the desk books each ID once (`CallbackDesk.book`): pass it to
  your system as an idempotency key.
- **`@request_callback.lookup`** finds a booking by its request ID. When the desk's answer is
  lost (the function raises anything but `ActionRejected` or `ActionNotSent`, or runs past
  `timeout_s`, 20 s by default), the library looks the write up before it says anything: found,
  the caller hears `done`; not found, the `unknown` line.
- **It leaves to the library** the `sending` line, said while the write runs, the `failed`,
  `unknown` and `declined` lines and the line that asks again, each in the reply's language; and
  `max_per_call`, 1, so one callback a call.

The Saudi texts, in the same
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
# The Saudi read-back, "baTlub min far' {branch} yittaSil 'alek bikhuSuuS: {reason}. arsil
# aT-Talab?": I'll ask the {branch} branch to call you about: {reason}. Shall I send the request?
SAUDI_SUMMARY = "بطلب من فرع {branch} يتصل عليك بخصوص: {reason}."
SAUDI_QUESTION = "أرسل الطلب؟"
# "tamm, raqm Talabak {number}": done, your request's number is {number}, said digit by digit.
SAUDI_DONE = "تم، رقم طلبك {number:id}."
# The Saudi claims, "Talabt minhum yittaSluun" and "sajjalt Talab al-ittiSaal": I asked them to
# call, I booked the callback.
SAUDI_CLAIMS = [
    "طلبت منهم يتصلون",
    "سجلت طلب الاتصال",
]
```

### The agent

From [callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
# What the helper with callbacks does, for the talker.
CALLBACK_INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches, and have a branch call a caller "
    "back. When the caller names a branch, look its hours up with opening_hours and say them in "
    "one short sentence. When the caller wants a branch to call them back, ask what it is about "
    "if they have not said, then call request_callback with the branch and a few words on why. "
    "For anything else, say plainly that you can only tell the hours or have a branch call."
)


def make_callback_helper(desk: CallbackDesk) -> VoiceAgent:
    """The helper with its callbacks booked at `desk`: the quickstart's helper, its languages
    and its read tool, and the action."""
    return VoiceAgent(
        name="minimal-callback",
        languages=helper.languages,
        instructions=CALLBACK_INSTRUCTIONS,
        tools=[opening_hours, callback_action(desk)],
    )
```

- **It builds on `app.py`**: it takes the helper's languages, greetings included, and its read
  tool, `opening_hours`, from there, and puts the action beside the tool in `tools`.
- **Its instructions** say when to call the action, and to ask what the call is about first.
  They need not say the rest: for an agent with an action, the library's prompt already says
  that the call is read back and done only after the caller's yes, to write nothing after it, and
  never to say it is done unless the system said so.
- **Each agent made books at a desk of its own**, so each test gets a fresh one.
- **`app.py` is unchanged**: its `make_runtime` serves the helper without the action, and the
  example has no runtime factory for this agent, so you meet it through its tests, below, not in
  the browser. A served runtime of an agent with an action keeps its outbox, a row for each
  write, in the agent's folder under the data folder (`outbox.sqlite3` in `var/<agent name>/`),
  which `t2v outbox list` reads.

### What the caller says and hears

The test holds the call in text: the real session, talker, yes rule, output guard and action
runner, a scripted model that calls the action, and typed words in place of speech, which the
yes rule takes only in a test (`env` `test`); a served call takes only words heard through
Whisper. Each language's lines, from
[test_callback.py](../../tests/minimal_example/test_callback.py):

```python
# Each language's call: the caller's request, the draft's reason, the branch's label, a yes, and
# a send word ("na'am" yes, "arsilha" send it), each a preset's word (checked below).
Tag = Literal["en", "ar-SA"]
CALLS: dict[Tag, tuple[str, str, str, str, str]] = {
    "en": ("Can Olaya call me back about my order?", DRAFT.reason, "Olaya", "yes", "send it"),
    # "mumkin far' al-olaya yittaSil 'alay? Talabi ma waSal": can the Olaya branch call me? My
    # order did not arrive.
    "ar-SA": (f"ممكن فرع {OLAYA} يتصل علي؟ {SAUDI_REASON}", SAUDI_REASON, OLAYA, "نعم", "أرسلها"),
}
```

`DRAFT.reason` is "my order did not arrive", and `SAUDI_REASON` «طلبي ما وصل», the same in Saudi
Arabic. The call, as the test plays it:

| Step | The caller | The agent, in English | The agent, in Saudi Arabic |
| --- | --- | --- | --- |
| 1 | Asks for a callback (the request above) | The talker calls `request_callback` with `branch="olaya"` and the reason, and the read-back plays: "I'll ask the Olaya branch to call you back about: my order did not arrive." then "Shall I send it?" | «بطلب من فرع العليا يتصل عليك بخصوص: طلبي ما وصل.» (I'll ask the Olaya branch to call you about: my order did not arrive.) then «أرسل الطلب؟» (shall I send the request?) |
| 2 | Says "yes", «نعم», over the summary | Nothing: the summary plays on, and the yes counts for nothing | The same |
| 3 | Says "yes", «نعم», alone, over the closing question | Asks again: "Sorry, I didn't catch that. Shall I go ahead?" | «المعذرة، ما وضح لي ردك. أسجل الطلب؟» (sorry, your answer wasn't clear to me. Shall I register the request?) |
| 4 | Once that line has played, says a yes with a send word: "yes send it", «نعم أرسلها» | The yes rule confirms, and the agent says "Sending it now, just a few seconds." while the desk books it | «ثواني، جالس أسجل طلبك.» (seconds, I'm registering your request.) |
| 5 | Waits | "Done, your callback number is 4101.", the number said "four one zero one" | «تم، رقم طلبك 4101.» (done, your request's number is 4101), the number said digit by digit |

- **A yes counts only when its speech began once the summary had played whole**: step 2 books
  nothing.
- **Over the closing question, only a yes with a send word confirms.** A bare yes there is asked
  again, at most twice (`max_attempts`); one more unclear answer, and the agent says it sent
  nothing. Once the closing question has played whole, a yes alone confirms too.
- **A no** ("no", «لا»), a change ("no, the Malaz branch") or a stop word ("stop", «وقف»)
  sends nothing: the talker answers in its own words, and for a change may call the action again,
  its new draft read back anew.
- **The agent never says it booked one before the desk answered**: what the talker writes after
  its call is dropped, the `sending` line claims nothing, and the `done` line comes from the
  desk's real answer, at the first pause after it (step 5).

### Its tests, with no key

[test_callback.py](../../tests/minimal_example/test_callback.py) plays the call above, in each
language:

<!-- fmt:off -->
```python
    # One answer only: each later turn goes to the read-back's confirming, never to the model.
    llm = ScriptedLLM([ScriptedLLM.call_tool("request_callback", branch="olaya", reason=reason)])

    async def scene() -> tuple[str, ...]:
        async with TextCall(make_callback_helper(desk), llm=llm, language=tag) as call:
            asked = await call.user(request)
            over = await call.user(yes, during="read_back")  # over the summary: it plays on
            over.expect.no_action()
            assert desk.booked == {}
            asked.expect.read_back(contains=label, branch="olaya", reason=reason)
            bare = await call.user(yes, during="closing_question")
            bare.expect.asked_again()
            bare.expect.no_action()
            assert desk.booked == {}
            await call.advance(10.0)
            sent = await call.user(f"{yes} {send}")
            await call.advance(30.0)
            sent.expect.confirmed("request_callback", branch="olaya", reason=reason)
            sent.expect.action_ended("request_callback", "done")
            sent.expect.action_completed("request_callback")
            assert [booked.number for _, booked in desk.booked.values()] == ["4101"]
            rows = await call.outbox.entries(action="request_callback")
            assert [row.state for row in rows] == ["done"]
            return call.violations

    assert asyncio.run(scene()) == ()
```
<!-- fmt:on -->

- **One scripted model entry**: the model calls the action once, and every later turn is the
  yes rule's, never the model's.
- **`during="read_back"`** and **`during="closing_question"`** say the words over the summary or
  the closing question as it plays; `call.user(text)` says them once the agent is silent, and
  `call.advance(seconds)` moves the call's clock on.
- **The expectations**: `read_back(contains=..., **values)` (the summary said whole, with those
  draft values), `no_action()`, `asked_again()`, `confirmed(name, **values)`,
  `action_ended(name, kind)` (the `sending` line said, then the outcome's) and
  `action_completed(name)`.
- **`call.outbox`** is the call's outbox, held in memory: its one row ended `done`.
- **`call.violations`** is empty: the output guard's rules and the yes rule's check found nothing
  wrong in what the agent said or in what was confirmed.

The same file checks that a branch outside the set, a reason past its bound and a field claiming
the caller's yes are each refused; that the read-back says the branch by its label, and that no
English line names a screen, a card, a page or a button; and that a write books once for its
request ID, which its lookup then finds.

[test_callback_safety.py](../../tests/minimal_example/test_callback_safety.py) runs the
library's safety suite, `ActionSafetySuite`, on the action, in each language:

```python
class TestRequestCallbackIsSafe(ActionSafetySuite):
    """The callback, in English: a fresh desk for each case's agent."""

    def make_agent(self) -> VoiceAgent:
        return make_callback_helper(CallbackDesk())

    def action_under_test(self) -> Action:
        (found,) = [t for t in self.make_agent().tools if isinstance(t, Action)]
        return found

    def sample_draft(self) -> BaseModel:
        return CallbackRequest(branch="olaya", reason="my order did not arrive")


class TestRequestCallbackIsSafeInSaudiArabic(TestRequestCallbackIsSafe):
    """The callback, in Saudi Arabic, the reason in the caller's words."""

    language = "ar-SA"

    def sample_draft(self) -> BaseModel:
        return CallbackRequest(branch="olaya", reason=SAUDI_REASON)
```

- **A subclass gives** `make_agent()`, a fresh agent with a fresh desk for each case;
  `action_under_test()`, the action by its name among the agent's; `sample_draft()`, a draft the
  action takes; and `language`, the call's, the agent's first unless it says.
- **It inherits every case**, each a `TextCall` of the agent: a yes over the summary, and a yes
  before any read-back, confirm nothing; a bare yes over the closing question is asked again;
  arguments that claim consent are refused; model text claiming the action is blocked, and so
  is the talker's text after its call; a status from a `reports_on` tool may be said, in a claim
  that names its number; a passage's number is never said in a claim; an ID in digit words or
  in Arabic-Indic digits counts as one; a lost reply is looked up and said done, or said unknown
  when nothing finds it; a refused or unsent write is said failed; the same request twice is
  written once; and the per-call cap holds. The cases for a chat model's judgement of the
  answers pass at once for an agent that does not ask for one, as this one does not. Run it on
  each action of yours ([testing.md](testing.md)).

Both run with the rest under `uv run poe test`, or alone:

```bash
uv run pytest tests/minimal_example/test_callback.py tests/minimal_example/test_callback_safety.py
```

## When the first call does not work

Start with `uv run t2v doctor`, then this list.

| What you see | What to do |
| --- | --- |
| `FAIL key` | The line names the setting: set `T2V_GROQ__API_KEY_FILE` to the full path of a file that holds only the key (or `T2V_GROQ__API_KEY`). The library never reads `GROQ_API_KEY`. |
| `FAIL model and voice <tag>` | The key cannot see that model: open the model to the key's organization in Groq's console, or ask Groq for access (the Arabic model). |
| `FAIL model and voice` for every language, each `(rejected)` with no FIX | Groq refused the key itself: check that the key's file holds the whole key and nothing else, and that the key is still active in Groq's console. |
| `FAIL synthesis <tag>` (with `--synthesize`) | The model's terms are not accepted: accept them in Groq's console, as the line's FIX says. |
| `FAIL onnx <file>` | The installed Pipecat is damaged: `uv sync --reinstall-package pipecat-ai`. |
| `FAIL clock` | This machine's clock is off Groq's by more than join tokens allow (`join.max_clock_skew_s`, with 1 s for the reading): set it, on Windows with Settings > Time & language > Date & time > **Sync now** (or `w32tm /resync`), elsewhere with NTP. A line saying the skew was not measured passes: no language check passed, or Groq's answers gave no readable `Date`. |
| The server stops as it starts | Its last line says why, with a FIX: `env` is not `dev`; another process holds the data folder (stop it, or give this one its own `T2V_STORAGE__VAR_DIR`); `PIPECAT_SETUP_FILES` or `PIPECAT_SMART_TURN_LOG_DATA` is set (unset it); or a fixed phrase could not be synthesized (run `t2v doctor --synthesize`). |
| `/voice/dev` answers 404 | The dev page answers only `t2v dev`, or a server with `T2V_SERVER__DEV_PAGE=true`, under `env` dev, to a browser on the same machine. |
| `microphone_refused`, `microphone_busy`, `microphone_missing` or `microphone_failed` on the page | Allow the microphone for the page in the browser's site settings; close the program that holds it; plug one in; or open the page at `http://127.0.0.1` or over HTTPS, where a browser allows a microphone. |
| The call never connects, or ends with `transport` | The browser and the backend found no media path over UDP within 20 s. On one machine nothing else is needed; a browser on another network needs an open UDP path or a TURN relay, which come with the deployment, not built yet. |
| No voice, but the captions come | Check the browser's output device and volume. |
| The echo works, but the helper says its error notice after every question | The chat model's request failed: the server logs `talker_failed`, and a runtime's observers get `ProviderFailed` with its kind. Check that the key can call `llm.model` in Groq's console, or set `T2V_LLM__MODEL` to a model it can call ([settings.md](../generated/settings.md) lists them). |
