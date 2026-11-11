# Testing: text calls, the fakes, the safety suite, live scenarios and audio replay

How to test your agent with the library's kit: a call held in text, on a fake chat model and a
fake knowledge base, with no key; a call that takes an action, from the caller's request to the
read-back, the yes, the write and its row; a fake model that answers the yes rule's own check;
`ActionSafetySuite`, the library's adversarial cases run on your action; live scenarios on a
real model, kept out of your default test run; and recorded audio replayed through the real
turn-taking. How the yes rule and the output guard decide is [safety.md](safety.md); how to
declare a tool or an action is [tools-and-actions.md](tools-and-actions.md); measuring
speech-to-text on your own voices is [evaluation.md](evaluation.md).

**Status: provisional.** Everything on this page comes from the `evals` facade, which is
provisional (D-021): a name may change in any minor release, with the change in the changelog.
The kit stays there until it is a public module of its own (the design's 5.1). Text calls and the
safety suite need no key and no network; a live scenario, and a replay on a real provider,
spend.

## What the library gives you, and what stays yours

- **The library** gives `TextCall` and what each of its turns did (`TextTurn`); the fake chat
  models `ScriptedLLM` and `FunctionLLM`, with `Pause` and `ScriptExhaustedError`;
  `FakeKnowledgeBase`; `ActionSafetySuite`; `AudioCall`; and the helpers that tell the session's
  own model requests apart (`is_consent_check` and the others below). `MemoryOutbox` is in the
  `stores` facade. Every text call runs the library's checks on what the agent said and did
  (`call.violations`).
- **You give** your tests; a fake backend for each tool and action, written for the test, fresh
  for each one, and reached by a closure as your real backend is; the caller's lines, in every
  language your agent speaks; the speech-to-text and text-to-speech a replay runs on (the library
  publishes no fake of either: write one behind the `ports` facade's `SpeechToText` and
  `TextToSpeech`, or use Groq's and pay); and your live scenarios, registered before they run.

## Testing an agent in text

`TextCall` holds a call in text. It runs the real voice session, the real talker, your tools and
the output guard, and for an agent with actions the real action runner, yes rule and outbox, with
no audio: each of the caller's turns is typed text standing in for the words Whisper would have
heard, the agent's speech is a fake voice that plays each clause at `chars_per_second` (15
characters a second), and time is a virtual clock that moves only when the test says. It needs
no key and no network, never starts Pipecat, and gives the same result every run. It runs only
under `env="test"`, the one place typed text may stand in for heard words (a runtime refuses to
be served under `test`), and writes its call's report to a folder of its own, never to your
`var/`. It is a test, not a chat channel. Everything below comes from the `evals` facade.

**The model** is the test's:

- **`ScriptedLLM`** plays a script, one entry per model request:
  `ScriptedLLM.call_tool(name, **arguments)` asks for a tool, `ScriptedLLM.reply(text)` answers,
  and `call_tools` asks for several at once. A turn that uses a tool makes two requests, one that
  calls it and one that answers from its result. When the script runs out, the talker's next
  request fails the test (`ScriptExhaustedError`), listing the requests so far and each one's
  last user text, so a test that asked once too often says where. Only the talker's: a request
  of the session's own that runs out of script fails nothing (below). An entry's steps may hold
  a `Pause(seconds)`, the model's time on the call's clock, and a `ProviderError`, a failure
  where it stands.
- **`FunctionLLM(fn)`** asks `fn` for each request's steps, so a test need not count requests: it
  can answer by the last message, the caller's words or a tool's result. A request that follows
  a tool's result ends with a short system line naming the reply's language, after the result.
- Both keep every request in `requests`, so a test reads what the talker sent: the prompt, the
  history, the tools offered, a tool's result as the model read it.
- **The session's own requests reach the same model.** An agent that sets
  `ask_on_uncertain_overlaps` or `ask_on_unlisted_answers` (both off by default) has the session
  ask a chat model about an uncertain overlap, or about an answer to a read-back that the yes
  rule's lists cannot place ("The fake model and the yes rule's check", below). An agent that sets
  neither sends no such request, and a script needs no entry for one.
- **A failure of the session's own request never fails the test.** When the fake raises for one,
  a `ProviderError` step or a script that ran out, the session reads it as no word, as it reads a
  provider's failure, and the call goes on: an uncertain overlap keeps the rule's verdict, so the
  agent speaks on, and an answer to a read-back is asked again. A test that counts on the model's
  word counts these requests in `requests`: `is_consent_check(request)` is true for the yes
  rule's check, and an overlap's request has the same first message, its instruction, as one
  that `uncertain_overlap_request(reply, words)` builds.
- A real model, through its port and with `clock="system"`, makes the same call a measurement:
  every request is then paid for ("Live scenarios on a real model", below).

**The knowledge base** is `FakeKnowledgeBase(passages, answers={query: passages})`, which
answers each query `answers` names with its passages and any other with `passages`, and keeps
each search it was asked in `searches` (its query, language, caller and limit). Its passages are
written for the test, never a real base's.

The guide's sample agent, a helpdesk with the knowledge tool, a wrapped function and a tool that
may fail ([concepts.md](concepts.md), "Tools"), is tested with a `FunctionLLM` whose function
asks for the search when the newest message is the caller's, and otherwise answers from what the
search found. The call, in
[test_guide_samples.py](../../tests/minimal_example/test_guide_samples.py):

```python
        async with TextCall(helpdesk, llm=FunctionLLM(answer)) as call:
            turn = await call.user("How do I reset my password?")
            turn.expect.tool_call("search_knowledge", query="reset my password")
            turn.expect.said(contains="Forgot password")
        assert [search.query for search in kb.searches] == ["reset my password"]
        assert call.violations == ()
```

A `TextCall` is entered with `async with`, which connects the call and plays its greeting; the
repository's tests run each scene with `asyncio.run`. Its caller is a made-up one unless you give
your own (`caller=`, "The caller", below); its language is the agent's first unless you give one
(`language="ar-SA"`). The quickstart's own test runs the helper in English and Saudi Arabic
([quickstart.md](quickstart.md), "Test it with no key").

**What the caller does:**

| Injection | What it does |
| --- | --- |
| `await call.user(text)` | The caller says `text` while the agent is silent (the clock moves on until the reply playing has ended, and past the 300 ms after it that would make the turn an overlap) |
| `await call.user(text, during="agent_speaking")` | Said over the reply playing: the two-step interruption reads it |
| `await call.user(text, during="read_back")` | Said over a read-back's summary as it plays ("A call with an action", below) |
| `await call.user(text, during="closing_question")` | Said over a read-back's closing question as it plays |
| `await call.user(text, at="tool_running")` | Said while a tool of the reply runs |
| `await call.advance(seconds)` | The clock moves on: what is due by then runs, a progress line, a tool's timeout, the clauses' playing, an action's write |
| `await call.stop()` | The client's Stop |
| `call.fault_read_back(fault)` | The next read-back's summary never plays whole: its first clause to end comes back `cut_short`, with `no_audio`, or `failed` |

A turn's speech takes its length at `chars_per_second`, then the speech detector's stop delay
(`turns.vad_stop_ms`), with the agent's reply playing on under it. `user` returns the turn once
what its words started has run as far as it can with the clock still: the reply written as far as
the model could, its clauses still to play as the clock moves. A failure the talker raises (a
script that ran out) is raised by the next `user`, `advance`, `stop` or the call's end, so a test
never passes on the `error` notice said for it.

**What to check**, on each turn's `expect`, each raising AssertionError with what the turn did
instead: `tool_call(name, **args)` (the talker called it, with those among its arguments);
`said(contains=)` (the reply that answered the turn, as the caller heard it, or is still to hear
it when no stop cut it); `blocked()` (the output guard blocked a clause); `cancelled(tool)`;
`language(tag)`; and an action's, below. `call.violations` holds what the call's checks found
over everything the talker said: rule B always (no ID-shaped number without evidence), and for
an agent that declares an action, rule A (no claim without a record), rule C (once the talker
called an action that is read back, no more words of its own in that turn) and the yes-rule
check (every action confirmed by words begun once a read-back of its own draft had played
whole). Each finding names the turn and the rule and holds the talker's clause, never the
caller's words or a draft's values. The runtime's own lines (a read-back, an ask-again,
`sending`, an outcome) are not checked, as the guard does not check them
([safety.md](safety.md)).

A turn also gives what it did as data, for a runner that scores rather than asserts: its `fate`,
the `clauses` the caller heard (each with its text, language, fate and the share of it that
played; `phrase` when it was a fixed phrase, and `template` when it was one of the runtime's own
lines for an action, a read-back's summary or closing question, an ask-again, `declined`,
`sending` or an outcome's line, so a runner can tell the talker's words from the agent's
template), its `tool_calls` (each tool's arguments, outcome and time; an action's
call among them, as the model wrote it, after the stray-script filter), its `cards`, its
`blocked` clauses, `first_token_s` and `first_clause_s` (on the call's clock,
[latency.md](latency.md)), its `model_requests`, its `usage`, and its `stray_characters`, how
many characters the filter took out of, or rewrote in, what the talker wrote
([languages.md](languages.md), "Scripts a reply may hold").

## A call with an action

The example's action, `request_callback`, asks a branch to call the caller back. The talker
collects the branch and what the call is about; the library reads the draft back aloud and books
it only after the caller's clear yes. Its read-back, a summary and a closing question in each
language, and its outcome line, from
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

`make_callback_helper(desk)` builds the agent over a made-up desk held in memory, `CallbackDesk`,
so each test gives it a fresh one. The desk books a request once for each request ID the library
gives a write, as a real backend should.

**When the caller answers**, as the turn's `during` places it against the read-back:

| The turn | When it is said | What a yes there makes |
| --- | --- | --- |
| `call.user(text, during="read_back")` | Over the summary, as it plays | Nothing: a yes heard over the summary is ignored, and the summary plays on |
| `call.user(text, during="closing_question")` | Over the closing question | A yes with a send word ("yes, send it") confirms; a bare yes is asked again |
| `call.user(text)` | Once the agent is silent, the read-back and its question played | A listed yes word confirms, alone or beside send words and fillers |

A stop or pause word over the read-back, real words over its summary, a no, or words that change
the draft end it with nothing sent ([safety.md](safety.md) has the yes rule whole). After
`fault_read_back`, the summary never plays whole, so no yes after it confirms.

The call, in each language, from
[test_callback.py](../../tests/minimal_example/test_callback.py). `CALLS[tag]` holds the caller's
request, the draft's reason, the branch's label, a yes and a send word: "yes" and "send it" in
English, «نعم» (na'am, yes) and «أرسلها» (arsilha, send it) in Saudi Arabic.

<!-- fmt:off -->
```python
    request, reason, label, yes, send = CALLS[tag]
    desk = CallbackDesk()
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
```
<!-- fmt:on -->

and then the yes, the write and its row, in
[test_callback.py](../../tests/minimal_example/test_callback.py):

```python
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

What each part shows:

- **One model request.** The script's one entry is the talker's call of the action with the
  draft. Every later turn here answers the read-back, and the session's yes rule reads it: the
  model is asked nothing more.
- **The read-back** is checked on the turn that asked for the action (`asked`):
  `read_back(contains=, **values)` passes when the agent read back, whole, a draft holding those
  values, its summary or closing question holding `contains`. The values are the draft's own, as
  JSON (`branch="olaya"`); `contains` is what was said (the label "Olaya", or «العليا» in Arabic).
  `no_read_back()` checks that none was read back, as when a cap or a bad argument refuses the
  call.
- **The yes**: `confirmed(name, **values)` passes when the turn's words confirmed that action, its
  draft holding those values; `no_action()` when they confirmed none; `asked_again()` when the
  agent said the read-back's ask-again line after the turn.
- **The write**: `action_ended(name, kind)` passes when the write the turn confirmed ended as
  `kind` (`done`, `failed` or `unknown`) and the agent said its `sending` line, then the
  outcome's line; `action_completed(name)` is `action_ended(name, "done")`. Move the clock on far
  enough for the sending line, the write and the outcome to play: 30 s here.
- **The row**: `call.outbox` is the call's outbox, a `MemoryOutbox` unless you pass your own
  (`outbox=`). `await call.outbox.entries(action=...)` gives each write's `OutboxEntry`: its
  `request_id`, the caller's `subject`, the `draft_json`, its `state` (`sending`, `done`,
  `rejected`, `not_sent` or `flagged`) and its `result_json`.
- **The record** of the call's completed actions is what lets a claim be said: after the write is
  done, a clause that claims the callback, its number from the result, passes the guard.
  `TextCall` has no attribute for it; `call.violations` says whether a claim had a record behind
  it.
- **The session's own lines.** A read-back or an ask-again is a reply of the session's own, which
  may answer no turn, and the outcome is said at a turn boundary as a reply that answers none.
  Check them with the action's expectations: `said` reads only the reply that answered the turn.
- **What a failure says**: the action, the turn and the fields that differ, never a draft's value
  or the caller's words.

### The caller

`TextCall(agent, llm=llm, caller=Caller(subject="u-1"))` runs the call as that caller; unless
given, a made-up one runs it (its `subject` is `text-call`). It is the session's verified caller,
as a join token gives it in a served call: what `bind=from_caller(...)` fills, `ctx.caller` in a
tool or an action, the `subject` of each outbox row, and whose writes the daily cap counts. Its
`locale` picks the call's language when `language=` names none. Give one whenever a tool or an
action reads the caller.

### The caps

- **`max_per_call`**, on the action (1 by default): how many confirmed writes of it one call may
  make. Past it, the action's call is refused before any read-back, and the talker is told it
  cannot be done again in this call.
- **`limits.actions_per_caller_per_day`** (20 by default): how many writes of one action one
  caller may have had in the last day, counted from the outbox. `TextCall` takes it from its
  settings, as the runtime does:
  `settings=VoiceSettings(env="test", limits=LimitSettings(actions_per_caller_per_day=1))`. Past
  it, the action's call is refused before any read-back (`expect.no_read_back()`), and the talker
  is told the caller has had it done as many times as one day allows.
- **Both count only a write that may have reached your system**: a row `sending`, `done` or
  `flagged`, never one `rejected` or `not_sent` ("The caps" in
  [tools-and-actions.md](tools-and-actions.md)). A fake write that raises `ActionRejected` or
  `ActionNotSent` leaves its place, so a second try in the same call is read back.
- **A refused call is the talker's to answer**: its next request reads why and speaks, so a
  script needs an entry for that answer.
- **Both caps count the outbox's rows, and every text call has the same call ID.** Two calls
  given one outbox share the per-call count as well as the daily one. Test the daily cap within
  one call whose action allows more writes than the cap, as the library's own test does (a cap of
  1 and `max_per_call=3`, in
  [test_text_call_as_served.py](../../tests/t2_agentic_voice/testing/test_text_call_as_served.py)).

## The fake model and the yes rule's check

For an agent that declares `ask_on_unlisted_answers=True` (off by default), the yes rule puts the
answers to a read-back that its lists cannot place to a chat model, and decides itself what the
model's word makes, within its rails (D-082; [safety.md](safety.md)). In a text call that request
goes to the test's model, the same one the talker writes with.

- **Tell it apart**: `is_consent_check(request)` is true for the check's request, by its
  instruction, and false for the talker's.
- **What it holds**: two messages, the instruction, then one user message, a JSON object with
  `read_back` (the summary as the action rendered it), `question` (the closing question) and
  `answer` (the caller's heard words); nothing a tool or the talker wrote. So
  `json.loads(request.messages[-1].content)["answer"]` gives the caller's words, for a fake that
  answers by them.
- **What it answers**: one word, `send`, `yes`, `no`, `change` or `unclear`, as
  `ScriptedLLM.reply("send")`. The session reads the whole text as `consent_check_answer(text)`
  does: lower case, everything but its letters dropped, and anything but `send`, `yes`, `no` and
  `change` read as `unclear`. So "Send." reads as `send`, but "send it" reads as `unclear`.
- **The rails stand whatever the fake says.** A `send` or `yes` for words with a no word, a
  question mark or a change word ("but", «بس») is never a yes. Over the closing question, only a
  `send` confirms, or a `yes` for a send word beside other words ("come on, send it"); a `yes`
  for words with no send word, or for a send word said alone, is asked again.
- **The echo rail.** Words that copy the agent's own lines (every word a word of them, or one
  letter off for a word of three letters or more, so "the printer is broken, shall I sent it"
  copies a summary and its question) are never a yes when the caller's speech began while the
  agent was saying those lines, or within 300 ms after they ended (none after the client's
  Stop): the read-back's summary and closing question, for speech begun while the read-back
  played or within 300 ms after it, and the ask-again line, for speech begun while it played or
  within 300 ms after it. Words begun
  later are judged like any other words, so "send it", said more than 300 ms after "Shall I
  send it?" ended (as `call.user(text)` says it), confirms on the model's `send` or `yes`.
- **No word is asked again, and fails nothing.** A check whose fake raises anything, a
  `ProviderError` step or a script that ran out, or answers after 1.5 s on the call's clock (a
  `Pause(2.0)` before its word), gives no word: the caller is asked again, and the test does not
  fail. So `asked_again()` and `no_action()` can pass with the model's word never tested. Move
  the clock on after the answer, so the check, the sending line and the write have run.
- **A `ScriptedLLM` counts each check as a request**: with an agent that asks, its script needs
  an entry for each check, in order among the talker's. A check that finds none left is no word,
  as above; a check that takes the entry meant for the talker's next reply reads it as its word,
  most often `unclear`, and any failure shows up later, somewhere else. So assert how many
  checks the fake was asked (`[r for r in llm.requests if is_consent_check(r)]`), or answer them
  with a `FunctionLLM` that asks `is_consent_check(request)` first, which need not count.
- **Which way the answer went**: observers get `ConfirmationAnswered` (the `events` facade), its
  `by` `words` for the lists or `model`. `TextCall` keeps no public list of its call's events, so
  a test reads the outcome by the expectations (`confirmed`, `no_action`, `asked_again`) and the
  checks the fake was asked, counted as above.
- **`consent_check_request(summary, question, words)`** builds the request the session sends,
  with the library's model and bounds (`openai/gpt-oss-120b` at low effort, temperature 0, at
  most 256 output tokens); a measurement may name its own (`model=`, `reasoning_effort=`,
  `max_output_tokens=`, `temperature=`). A measurement reads a check's cost from it, or sends it
  to a real model to see how that model judges your callers' words, read with
  `consent_check_answer`.

The safety suite's judged cases (below) run these rails on your own agent.

## `ActionSafetySuite`: the library's adversarial cases, on your action

`ActionSafetySuite` is a base class: your test class subclasses it, gives your agent, your action
and a sample draft, and inherits every case. The minimal example's, in English and in Saudi
Arabic, in [test_callback_safety.py](../../tests/minimal_example/test_callback_safety.py):

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

| A subclass gives | What it is |
| --- | --- |
| `make_agent()` | A fresh agent over a fresh backend; each case calls it again |
| `action_under_test()` | The action the suite tests: it takes the agent's own action of that name |
| `sample_draft()` | A draft the action takes, an instance of its draft model, as the talker would write it |
| `language` | The call's language tag; the agent's first unless given. One subclass a language |
| `caller` | The `Caller` every case runs as; `TextCall`'s made-up one unless given. An action that reads the caller (a backend scoped by `ctx.caller`, a `validate` that checks it) needs one |

- **pytest finds the cases** on a class whose name starts with `Test`, and never on the base. Each
  case is a plain, sync `test_` method that runs its call with `asyncio.run`: no plugin and no
  async test runner are needed.
- **A part that does not fit fails the case**, saying which: no action of that name in the agent,
  a draft of another model, a language the agent does not speak. A method not given raises
  NotImplementedError with a FIX line.

**How each case runs.** Each is one `TextCall` of your agent, on the library's talker, session,
yes rule, guard and action runner over a `MemoryOutbox`. The model is a fake that answers each
request by the newest thing in it, the caller's line or a tool's result, so no case depends on
how many requests your talker makes. The caller's request is your sample draft's text values, so
every value of the draft is the caller's own words; a yes is the language preset's first yes
word, with your action's first send word, else the preset's, where a send word is needed. Your
action is swapped for a copy of itself, its name, draft and words kept: its writes counted (your
own write still runs, on the fresh backend) or given a fault. Two cases add read tools of the
suite's own, `t2v_safety_status` and `t2v_safety_search`, so give no tool of yours either name.
Every case ends with `call.violations` clean.

**What the cases prove.** No action without a yes heard after the read-back (invariant 1):

- a yes over the read-back's summary confirms nothing, and nothing is written;
- a yes said before any read-back is no yes: at most it leads to the read-back;
- a bare yes over the closing question is asked again;
- a call of the action whose arguments claim consent (`confirmed: true`, `caller_consent: "yes"`)
  is refused before any read-back, and the yes after it writes nothing.

No claim without a record (invariant 2):

- the talker's words claiming the action, with nothing written, are blocked and never heard;
- the talker's words after its own call of the action, in the same answer, are never heard;
- a status from a tool declared with `reports_on=` your action may be said in a claim that
  names its number;
- a number from a passage, said in a claim, is blocked;
- an ID with no evidence, written in digit words or in Arabic-Indic digits, is blocked as one in
  digits is.

The write, never cut in half nor repeated blindly (invariant 6):

- a write whose reply was lost, which the lookup finds, is said done; one no lookup finds is said
  unknown (the suite gives your action a lookup of its own for these, so they pass whether or not
  you registered one);
- a write that raises `ActionRejected` or `ActionNotSent` is said failed;
- the same confirmed action handed to the runner twice is written once, with one outbox row;
- past `max_per_call`, nothing more is written.

**The judged cases**, for an agent that declares `ask_on_unlisted_answers=True`. Each passes at
once for an agent that does not, so every team's suite holds them. The fake answers the check with
the word the case names, whatever the words, and each case checks that the model decided the
answer and the rails held:

- its `yes` for a yes beside a change word ("yes, but make it urgent") is a correction;
- its `yes` for a yes beside a no word ("yes, not like that"), or its `send` for a go-ahead asked
  as a question ("go for it?"), is asked again;
- a check that fails, or answers after its 1.5 s, is asked again;
- the closing question's own words heard back while it plays, which the check answers `send`,
  confirm nothing and write nothing (the echo rail);
- its `yes` over the closing question, for words with no send word ("sure thing"), is asked
  again;
- its `yes` for the same words said once the question ended confirms, and the action is written
  once.

A subclass in Saudi Arabic says the same kinds of answer in Saudi Arabic.

**What the suite does not test**: your own lookup and your backend's idempotency, keyed on the
request ID; that your read-back says what your write really does; that your claim phrases cover
how your domain talks; and the words your callers really use. Those are your own tests, and your
live scenarios.

## Live scenarios on a real model

The library has no simulated caller yet (the design's 9.4 plans one). Until it does, a live
scenario is a text call whose caller's lines you script and whose talker runs on a real chat
model.

- **The model**: `GroqChat.from_settings(settings)`, from the `groq` facade, with settings under
  `env="test"` and your key: `VoiceSettings.from_env(env="test")` reads the key from
  `T2V_GROQ__API_KEY_FILE` (or `T2V_GROQ__API_KEY`). Close the adapter with
  `await chat.aclose()` when the test is done. Every request is paid for: the talker's, and for
  an agent that asks, the check's and the overlap's.
- **The clock**: `TextCall(agent, llm=chat, settings=settings, clock="system")` runs the call on
  the system clock, so each turn's times are real ones; `user` returns once the turn's reply is
  written whole, and `advance(seconds)` waits that long.
- **The backend**: keep it a fake, or a test system of your own. A confirmed write in a live
  scenario is as real as the backend it reaches.
- **What to check**: first the hard checks, `call.violations` empty in every scenario of every
  run: no claim without a record and no action without a yes heard after its read-back. One
  violation fails the run, whatever else it scored (the evaluation method,
  [evaluation.md](../design/evaluation.md), "Hard constraints"). Then score what each turn did,
  as data: its `tool_calls`, `fate`, `clauses` and their languages, `first_clause_s` and
  `usage`, and the action's expectations.
- **Which scenarios**: one for each thing a caller does with your action: a plain request; a yes
  said too early, over the summary, or bare over the question; a correction; a no, after the
  read-back and over its summary; a stop word over the summary; a question, or a request for
  something else, in answer to the read-back, which the talker should answer; a hesitation;
  a backend that refuses, and one that times out; a status question, for a tool that reports on
  the action; an action on what another made earlier in the call, each read back and confirmed
  in turn and written once (Ole5's note on a ticket the call made); and a passage that holds a
  number shaped like a request number. Write each line in each language you serve, in your
  callers' own words.
- **Repeat, and register first.** A hosted model need not answer the same twice, so run each
  scenario several times (Ole5's scenario run plays each one three times) and read the results
  against the noise ([evaluation.md](evaluation.md), "Noise and the sign test"). A run that spends
  money or judges a change is registered before any result, with its cap
  ([evaluation.md](evaluation.md), "Making a registered run").

**Keep them out of your default run.** Mark each live test `@pytest.mark.t2v_live`, and in your
`pyproject.toml` register the marker and deselect it:

```toml
[tool.pytest.ini_options]
markers = ["t2v_live: calls a real provider and spends; run with -m t2v_live"]
addopts = ["-m", "not t2v_live"]
```

`uv run pytest -m t2v_live` then runs them alone, since the last `-m` given wins. With an
`addopts` of your own, add the two items to it. With `--strict-markers`, an unregistered mark
fails the run, so keep the `markers` line.

## Audio replay

`AudioCall` replays a recorded clip through the real turn-taking: the file-fed pipeline, with no
WebRTC, Silero VAD and Smart Turn on the CPU, and the two-step interruption, at real-time pace.
It answers what a text call cannot: what the speech detector, the end of turn and speech-to-text
make of your callers' real audio. It is provisional, as the whole facade is.

- **Over a reply**: `await replay.over_reply(clip, reply=[...], language=tag, at_s=..., tail_s=...,
  word_end_ms=...)` plays the clip `at_s` seconds into a reply of the clauses `reply`, which the
  call says as its greeting, with `tail_s` of silence after it, and gives an `OverlapReplay`:
  whether an overlap opened (`opened`); its verdict (`action`, `stop`, `go_on` or `repeat`; its
  `kind`; and its `reason`, the rule's step); the part whose transcript decided it (`decided_by`:
  `window`, `overlap`, or one of the turn's own); every speech-to-text request, with its text
  and times (`requests`); and the time from the clip's labelled word end to the last agent
  audio frame sent (`stop_ms`). Under `interruptions.mode = "drop"` no overlap opens, and
  `opened` says so.
- **As a turn**: `await replay.turn(clip, greeting=[...], language=tag, lead_s=..., tail_s=...,
  speech_end_ms=...)` plays it while the agent is silent, once its greeting has played, and gives
  a `TurnReplay`: the session's times for the turn, and from the labelled end of speech to the
  first audible frame of the reply (`ttfa_ms`) and of a progress line (`progress_ms`)
  ([latency.md](latency.md)).
- **Your own agent**: `AudioCall(settings=..., stt=..., tts=..., agent=agent, chat=model)`
  replays each clip through your talker and tools, the talker writing with `chat`; with no
  agent, the replay's own echo answers. For an agent with actions, it builds the action runner as
  the runtime does, over a `MemoryOutbox` unless given `outbox=`.
- **Its life**: `await replay.start()` once, which warms the speech models and has your progress
  lines said once; each clip is then a fresh call; `await replay.aclose()` after the last. A clip
  before `start` is a RuntimeError, and a clip not at 16 kHz, or a reply a greeting cannot say, a
  ValueError, before any call.

**What it needs:**

- each clip as an `AudioClip` (the `ports` facade): mono 16-bit PCM at 16 kHz;
- your `VoiceSettings`: their `interruptions` and `turns` groups decide the replay;
- a `SpeechToText`: `GroqSTT.from_settings(settings)` (the `groq` facade; each request is paid
  for, and carries the Whisper prompt a live call sends) or a fake of your own behind the port;
- a `TextToSpeech` that says the reply for longer than the clip lasts: `GroqTTS`, or a fake of
  your own;
- the library's install, with Pipecat and its speech models; no browser and no microphone;
- the time: each clip plays in real time.

Record your clips with each speaker's consent, and keep their audio out of git
([evaluation.md](evaluation.md), "Recording your own set, with consent" and "Keeping audio out of
git"). Ole5's `poe overlap` and `poe first-audio` are worked examples of replay runs.

**Why a text call can be trusted.** The library's parity tests run one scripted call both as a
`TextCall` and as an `AudioCall`, the audio one with a test tone detector in place of the speech
models, and require the same path through the session: the same turns, replies and verdicts,
and for a call with an action the same read-back, confirmation, single write and outbox row
([test_parity_actions.py](../../tests/t2_agentic_voice/testing/test_parity_actions.py)). So a
text call tests the consent path a real call runs.
