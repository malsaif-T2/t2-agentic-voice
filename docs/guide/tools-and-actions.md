# Tools and actions: looking things up, and doing things on a spoken yes

The talker (the chat model that writes what the agent says) can call two kinds of function of
yours:

- a **read tool** looks something up and changes nothing. It runs inside the turn, as soon as
  the talker asks, and a stop may cancel it or throw its result away;
- an **action** changes one thing in your system: it books, opens or sends something. The talker
  only proposes it. The library reads the proposal back to the caller aloud, and carries it out
  only after the caller's spoken yes, as a job of its own that a stop never cuts in half. Then
  the library, never the talker, says how it ended.

This page shows how to write each kind, how to wrap a function you already have, what happens to
one action in a call, what the caller hears when something fails, what your system must do so a
write happens at most once, the caps, and lookups. How the yes rule and the output guard decide
is in [safety.md](safety.md); testing an action is in [testing.md](testing.md). The design is
the [package design](../design/package-design.md)'s sections 4.4, 6.4 and 8, and the reasons are
in [decisions.md](../design/decisions.md) (D-080 to D-082).

**Status.** Confirmed actions are built (plan 007): `@action`, the read-back, the yes rule, the
outbox, the record of completed actions and the output guard's claim rule. They are tested in
text calls with fake models, on the example's action below and on Ole5's. They have not been
heard in a live call yet: the owner's live calls come later in plan 007.

## The two kinds

| | A read tool (`@tool`, `Tool.from_function`) | An action (`@action`) |
| --- | --- | --- |
| What it may do | Read only. This is your promise: the library cannot check it | One change in your system |
| When it runs | Inside the turn, as soon as the talker asks | After the caller's yes, as a job outside the turn |
| What the talker gives | Arguments, parsed into the function's parameters | A draft, parsed into your pydantic model |
| Who the caller is | `bind=from_caller(...)`, or `CallContext.caller` | `ActionContext.caller` |
| On a stop | Cancelled (the default), or left to finish (`on_interrupt="finish"`) | Never cut in half: it runs to its end |
| Its timeout | `timeout_s`, 5 s by default; then "the tool failed" | `timeout_s`, 20 s by default; then a lookup, else "unknown" |
| What the caller hears of it | What the talker says from its result | The action's own lines, filled from the draft and the real result |
| Retries | The talker may call it again | Never blindly: a lookup by the request ID, or "unknown" |

Both go in the agent's `tools`, each name once.

## A read tool

[concepts.md](concepts.md) ("Tools") has the whole kit. In short:

- **`@tool(description=...)`** makes a read tool of an async or a sync function, as the
  quickstart's `opening_hours` ([quickstart.md](quickstart.md)). A sync one runs in a worker
  thread, so it never blocks the call.
- **Its parameters** come from the signature, and they are the only schema the talker sees.
  Each value is parsed and checked before the function runs; a wrong one goes back to the
  talker with its field named, never its value.
- **`bind=`** fills a parameter from the call's verified caller, never from the talker, and
  hides it from the schema: `from_caller("subject")`, `"display_name"`, `"locale"` or
  `"attributes.<key>"`. A parameter annotated `CallContext` gets the caller, the call's ID and
  the reply's language.
- **It returns** any value that is JSON, or a `ToolResult` (`data`, a `card` for a client with
  a screen, and `evidence` for the output guard). A `ToolError(message)` is a failure the talker
  reads; anything else, and the timeout, gives the talker only "the tool failed".
- **`progress=`** names a line said when the wait runs long; **`reports_on=`** makes its result
  evidence for claims about an action ("Lookups: a status tool", below).

### Wrapping a function you already have

`Tool.from_function` wraps a function without rewriting it. The function here is a team's
existing sync one; the caller's ID is bound in from the join token, so the talker never gives
it. From [test_guide_samples.py](../../tests/minimal_example/test_guide_samples.py):

```python
def list_requests(employee_id: str, status: Literal["open", "closed"] = "open") -> list[str]:
    """The employee's IT requests with `status`: a team's existing function, sync."""
    return REQUESTS.get(employee_id, {}).get(status, [])


my_requests = Tool.from_function(
    list_requests,
    name="my_requests",
    description="List the caller's own IT requests, open or closed.",
    bind={"employee_id": from_caller("subject")},
    timeout_s=3,
    progress="checking",
)
```

The talker sees one parameter, `status`. `list_requests` is called as it is, with
`employee_id` from the caller.

## An action

The example's action is `request_callback`: a branch calls the caller back. It is in
`examples/minimal`, beside the quickstart's helper, whose languages and read tool it reuses. The
desk it books at is made up and held in memory.

### The draft and the result

From [callback.py](../../examples/minimal/src/minimal_example/callback.py):

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


class CallbackBooked(BaseModel):
    """What the desk gives back: the callback's number, four digits."""

    number: Annotated[str, Field(pattern=r"^[0-9]{4}$")]
```

- **The draft** is a pydantic model: what the talker gives, and the only schema it sees. Give
  each field a `description`: the talker reads it to know what to collect from the caller.
- **Each value is checked before any read-back.** A missing field, a field the talker invents,
  a value outside its bounds or outside a fixed set: each is refused, and the talker is told
  which field was wrong, so it can ask the caller.
- **A fixed set of values** (a `Literal` or an enum) keeps the talker from inventing one. The
  read-back says a fixed value through its `Spoken` label in the reply's language, or as it is
  written in a language with no label. A fixed field the read-back names needs a label for each
  of its values.
- **No field may claim consent.** A field named like it (`confirmed`, `consent`, `approved`,
  `yes`, `agree` and the like, a nested one too) is refused when the action is built. Only the
  caller's own words say yes.
- **No field should say who the caller is.** The talker writes the draft from what the caller
  said, and a caller can say anything. Read who they are from `ctx.caller` in the function.
- **The result** is the model your function returns. The `done` line is filled from it, and its
  values are the evidence that lets the talker say the callback's number later. Here its
  pattern also refuses a number that is not four digits.

### The action itself

The Saudi lines are written in the file with their sound and meaning in a comment. From
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
# The Saudi read-back, "baTlub min far' {branch} yittaSil 'alek bikhuSuuS: {reason}. arsil
# aT-Talab?": I'll ask the {branch} branch to call you about: {reason}. Shall I send the request?
SAUDI_SUMMARY = "بطلب من فرع {branch} يتصل عليك بخصوص: {reason}."
SAUDI_QUESTION = "أرسل الطلب؟"
# "tamm, raqm Talabak {number}": done, your request's number is {number}, said digit by digit.
SAUDI_DONE = "تم، رقم طلبك {number:id}."
```

The action, built inside `callback_action(desk)`, which reaches the desk by a closure. From
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

<!-- fmt:off -->
```python
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
<!-- fmt:on -->

- **`@action(...)`** makes an `Action` of an async or a sync function (a sync one runs in a
  worker thread). The function takes `draft`, annotated with the draft's model, and may take a
  parameter annotated `ActionContext`; nothing else. Its return annotation is the result's
  model. Your system is reached by a closure (`desk` here), as `knowledge_tool` reaches a
  knowledge base.
- **`description`**, in English (models follow English descriptions more reliably): when the
  talker calls the action, and what it must collect first. The action's name is the function's,
  unless `name=` gives another.
- **`read_back`** gives each language a pair: the **summary**, which says what will be done
  with every value that matters, and the **closing question**. They are said one after the
  other, the summary first. The caller's yes counts only once the summary has played whole.
- **`done`** is said when the write returned or the lookup found it, filled from the real
  result.
- **`claims`** are the past-tense phrases that claim this action, in each language. The output
  guard blocks a sentence of the talker's that holds one until the action is really done
  ("Lookups: a status tool", below).
- **`@request_callback.lookup`** registers how to find a write whose reply was lost, by its
  request ID. It is optional, and only the library calls it ("Writing at most once", below).

The example leaves out the action's other parts. Each has a default:

| Part | Default | What it does |
| --- | --- | --- |
| `ReadBack(send_words=...)` | none | The action's own send words, by language code (`{"ar": [...], "en": [...]}`), added to the preset's for the yes rule |
| `ReadBack(max_attempts=...)` | 2 | How many times an unclear answer is asked again before the `declined` line |
| `ReadBack(asked_again=Say(...))` | the library's line | The line that asks again |
| `ReadBack(show_draft=...)` | False | Meant to show the draft as a card on a client with a screen (D-075). No part of the library reads it yet: setting it shows nothing |
| `sending`, `failed`, `unknown`, `declined` | the library's lines | The lines in the next table |
| `validate` | none | `validate(ctx, draft)`, async or sync, run when the talker calls the action, before the read-back: it returns None to keep the draft, a new draft of the same model to read back instead, or raises `ToolError(message)`, which the talker is told |
| `max_per_call` | 1 | How many times this action may be done in one call ("The caps", below) |
| `timeout_s` | 20 | Seconds the write may take before the library looks it up; `validate` and the lookup each have as long |

`validate` is called with the talker's `CallContext`, so it can check the draft against your
system's own lists (that the branch takes callbacks today, say). It runs inside the turn, and an
action names no progress line, so keep it quick: past `timeout_s` it is cancelled and the
talker is told "the tool failed".

### The lines an action speaks

| Line | When it is said | Filled from | The library's English line, when you leave it out |
| --- | --- | --- | --- |
| The summary (`read_back`) | After the talker calls the action, as its reply's next clauses | The draft | Required |
| The closing question (`read_back`) | Right after the summary | The draft | Required |
| `asked_again` (on `ReadBack`) | After an unclear answer, at most `max_attempts` times | The draft | "Sorry, I didn't catch that. Shall I go ahead?" |
| `declined` | When no clear answer came after the last ask-again | The draft | "I couldn't get a clear answer, so I haven't sent anything." |
| `sending` | As the answer to the caller's yes, while the write runs | The draft | "Sending it now, just a few seconds." |
| `done` | The write returned, or the lookup found it | The result | Required |
| `failed` | The write was definitely not done | The draft | "Sorry, I couldn't get that done. Nothing has changed." |
| `unknown` | No reply came, and no lookup found the write | The draft | "Sorry, I can't tell yet whether it went through. Our team will check on it." |

- **A placeholder** is `{field}`, or `{field:id}` to say it digit by digit, a run of 8 digits or
  more in groups of four. The caption shows the value as it is written: "4101", heard as "four
  one zero one".
- **A text is keyed by a language tag**, `ar-SA`, `ar` or `en`. A language reads its own tag
  first, then its primary code, so an `ar` text serves both Arabic presets unless `ar-SA` has
  its own; an `ar-SA` text never covers `ar`. Every line you give must cover every language
  the agent speaks. The library's own lines exist in each preset's register.
- **An MSA caller hears MSA.** The talker reads the register of the caller's Arabic from their
  words (Saudi once a turn holds a dialect form, MSA while none has). An `ar-SA` agent may
  give an `ar` text, MSA, beside each `ar-SA` one, and the agent need not speak `ar` for it:
  a read-back to an MSA caller reads each line's `ar` text, its `ar-SA` one where it has none,
  and the library's own lines in MSA; the outcome is read as its read-back was. Every line is
  still said in the `ar-SA` voice. Ole5's
  [lines.py](../../apps/ole5-voice-agent/src/ole5_voice/tickets/lines.py) gives one for each.
- **The output guard does not read these lines.** Their values come from the parsed draft or
  the real result, never from the talker, so they must say what is true: a summary that leaves
  out a value that matters asks the caller to agree to something they did not hear.
- **Keep the fixed lines free of the words a caller commands with**: stop, wait, repeat and
  listening words, and yes and send words. The agent's own voice, heard back through the
  speakers, could act on them. Only the closing question, and the line that asks again, should
  hold a send word. [writing-for-voice.md](writing-for-voice.md) has how to word fixed lines.
- **The agent is voice only.** No line may ask the caller to look at a screen: every value that
  matters is said.

### The agent

From [callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
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

- **The action goes in `tools`**, beside the read tools. Its instructions
  (`CALLBACK_INSTRUCTIONS`) tell the talker when to call it and what to ask first.
- **An agent with an action gets more.** The library adds its rules about actions to the prompt
  (`render_prompt(agent, "en")` shows them), and the output guard's claim rule runs on every
  sentence of the talker's. An agent with no action gets neither.
- **The runtime keeps the agent's outbox** in `storage.var_dir/<agent name>/outbox.sqlite3`. It
  holds each write's draft and result, so it holds call content.
- **`make_callback_helper` takes the desk**, so each test gets a fresh one.

### What is refused when it is built

Each of these is a `ConfigurationError` that names the field, with a FIX line, and never the
value it refused:

- a function with no `draft` parameter, a parameter other than its context and its draft, or a
  draft or return annotation that is not a pydantic model;
- a draft field named like consent, anywhere in its schema;
- a template that names a field its model does not have (`done` names the result's fields,
  every other line the draft's), or a placeholder other than `{field}` and `{field:id}`;
- a fixed field the read-back names with no `Spoken` label for each of its values;
- a text that is not one line of plain words;
- `max_per_call` below 1, or a `timeout_s` that is not above 0;
- an agent with a language one of the action's texts does not cover, two tools or actions with
  one name, or a tool whose `reports_on` names an action the agent does not declare.

## Wrapping a function you already have, as an action

There is no `Action.from_function`, since an action's function takes a draft model and returns
a result model. Write a short `@action` function that calls yours, as `request_callback` calls
`desk.book`:

- **The draft's fields** become your function's arguments (`draft.model_dump()` gives them as a
  dict).
- **Who the caller is** comes from `ctx.caller` (its `subject`, `display_name`, `locale` and
  `attributes`), never from the draft. An action has no `bind=`.
- **`ctx.request_id`** goes to your system as its idempotency key ("Writing at most once",
  below).
- **What your function returns** becomes the result model.
- **Your function's failures** become the library's meanings: raise `ActionRejected` when your
  system refused the write, and `ActionNotSent` when it failed before anything was sent. Any
  other exception means "it may have been done" ("The error table", below). The reason you give
  either one is never said to the caller, and the library logs only the action's name and the
  kind of failure: log the reason yourself if you need it.
- **`ctx.consent`** holds the words that confirmed the action (`words`, their `source` and
  `speech_at`, when the caller began saying them), for your own audit record. **`ctx.conversation`**
  holds what each side said in the call, as the caller heard it, for a record people read later
  (a handoff, say).

When your function is sync and may be slow, make the `@action` function sync too (`def`, not
`async def`): a sync action runs in a worker thread, while a slow sync call inside an
`async def` would hold up the call's audio.

## One action in a call

Under the default `interruptions.mode` (`two_step`), with the example's helper:

| Step | What happens | What the caller hears |
| --- | --- | --- |
| 1 | The caller asks Olaya to call them back. The talker collects what the draft needs and calls `request_callback`. **Nothing is written.** What the talker writes after the call, in that request, is dropped unspoken (the guard's rule C) | Whatever the talker said before the call |
| 2 | The library parses the draft, runs `validate`, checks the caps and renders the read-back in the reply's language. A refusal goes back to the talker, the field or the reason named, and the talker may speak again, to say why or to ask for what is missing | Nothing yet, or the talker's next words after a refusal |
| 3 | The reply ends with the read-back. The talker reads only that its call is being read back, never the draft, and says nothing more in this turn. Observers get `ConfirmationRequested` as the summary starts to play | The summary, then the closing question |
| 4 | Over the summary: a yes, a send word or a listening sound is ignored, and counts for nothing. A stop or pause word over the read-back ends it: nothing is sent, and the talker asks what to change, its draft kept. Other words that stop the summary decline it as a correction. A request to hear it again says it again | The read-back, playing on or said again; or the talker |
| 5 | The caller answers. A turn begun once the summary has played whole goes to the yes rule, not to the talker ("The caller's yes", below) | |
| 6 | **A yes.** The `sending` line is said, and the write starts as a job of its own: its outbox row is written, then your function is called with the draft the caller heard, within `timeout_s`. Neither a stop nor the call's end cuts it | `sending` |
| 7 | **The outcome**, once the write ends, said once at the next turn boundary: when no reply is playing, every turn of the caller's has closed, and no other action's read-back waits for its answer, so never over the caller, and never between a closing question and its answer, where a "yes" to the outcome would confirm the other action. Observers get `ActionCompleted` or `ActionUnconfirmed` | `done`, `failed` or `unknown` |

The answers that are not a yes:

- **A plain no.** Confirming ends, and the turn goes to the talker with a note that the caller
  said no and nothing was done. The talker answers in its own words (the owner's ruling, plan
  007): no fixed line is said.
- **A correction** ("no, the Malaz branch", or other words on none of the yes rule's lists).
  Confirming ends, and the turn goes to the talker with a note that the caller changed the
  read-back and that it should call the action again with the change. The new draft is read
  back from step 2, and only a yes to that new read-back counts.
- **Unclear, or no answer it can use.** The `asked_again` line, at most `max_attempts` times;
  after the last, the `declined` line, and confirming ends.

Each answer the yes rule decides reaches observers as `ConfirmationAnswered`, with its
`decision` (`yes`, `declined`, `correction` or `asked_again`) and `by` (`words`, or `model` for
the model check in [safety.md](safety.md)); a read-back ended by a stop or by words over its
summary sends none (TD-135). The events are in the `events` facade.

The example's own test walks through steps 3 to 7: a yes over the summary books nothing, a bare
yes over the closing question is asked again, and a yes with a send word, said once the question
has played, books once. From [test_callback.py](../../tests/minimal_example/test_callback.py):

```python
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
```

### While the write runs, and other edges

- **The call is no longer confirming**, so the caller's next turn goes to the talker. The talker
  cannot say the action is done: the claim rule blocks that until the call's record holds it.
  With the default `max_per_call` of 1, calling the same action again is refused.
- **A slow write** is heard as the `sending` line, then silence: there is no second progress
  line. Past `timeout_s` the library stops waiting and looks the write up. Your function goes on
  in the background, and what it returns then is discarded: its row stays `flagged` until
  `t2v outbox reconcile` finds it (TD-136). Set `timeout_s` above your system's slowest answer.
- **If the call ends first**, the write still runs to its end and its outbox row is marked, but
  no line is said.
- **A caller who stays silent** after the closing question is not asked again: the call stays
  confirming until they speak, or until `limits.idle_s` ends the call (TD-142).
- **The Stop button or Esc** of the browser client over a read-back ends it with no line said
  (TD-135).
- **One action at a time.** A second action call in the same model request is refused, and the
  talker is told to call it once the caller has answered the first. One read-back is current at
  a time.

## The caller's yes

The yes rule decides from the caller's own heard words and from what the caller heard of the
read-back. [safety.md](safety.md) has the rule in full; in brief:

- **Only heard words count**, from speech-to-text. Typed words count only when `env` is `test`,
  which a runtime refuses to serve and a test's `TextCall` runs under.
- **Only words begun once the summary has played whole count**: every clause of it played, none
  cut short. A yes said over the summary is ignored.
- **After the closing question has ended**, a plain yes ("yes", «نعم») confirms. **Over the
  closing question**, a yes needs a send word too ("yes, send it", «نعم أرسلها»); a bare yes
  there is asked again.
- **A no** is declined. A yes beside a no, or a yes asked as a question («نعم؟», "yes?"), is
  asked again. Words on none of the rule's lists make a correction.
- **For an agent that asks** (`VoiceAgent(ask_on_unlisted_answers=True)`, off by default), the
  words the lists cannot place go to a chat model first, and the rule takes its word only
  within rails (D-082).
- **Nothing the talker writes can stand in for a yes.** The draft holds no consent field, and
  the part that runs your function takes only what the yes rule issued.

What you provide: a read-back that says every value that matters, truthfully, with labels your
callers understand; a closing question whose verb is a send word, or that verb in the action's
`send_words` (callers often answer with the question's own verb, and a yes over the question
needs one); and the words your callers say that the presets miss, in `T2V_WORDS__YES` and
`T2V_WORDS__SEND`.

## The error table

### Before the read-back

Each is told to the talker as a failed tool result, and nothing is written. The caller hears
what the talker then says, under the output guard.

| What happened | What the talker is told | `failure`, in the trace |
| --- | --- | --- |
| The talker named an action the agent does not have | "there is no action named ...; the actions are: ..." | `no_such_action` |
| Its arguments are not JSON, or not a JSON object | "the arguments are not JSON: give a JSON object of the tool's parameters", or "the arguments are a JSON object of the tool's parameters" | `bad_arguments` |
| A field is missing, extra, of the wrong type, past its bounds or outside its fixed set | "invalid arguments: ...", each field at fault named (at most 5), never its value | `bad_arguments` |
| `validate` raised `ToolError(message)` | The message | `draft_rejected` |
| `validate` raised anything else, timed out, or returned something that is not the draft | "the tool failed" | `validate_failed` |
| The outbox could not be read to count the caps | "the tool failed" | `outbox_unread` |
| This call already holds `max_per_call` confirmed writes of the action that may have reached your system (`sending`, `done` or `flagged`) | "this cannot be done again in this call: tell the caller so, and do not call it again" | `cap_per_call` |
| The caller reached the daily cap for this action | "the caller has had this done as many times as one day allows: tell them so" | `cap_per_caller` |
| A read-back line cannot be filled from this draft | "the read-back cannot be said with this draft: give every field it reads" | `read_back_unsaid` |
| A second action call in the same model request | "one action at a time: call it again once the caller has answered the first" | `one_at_a_time` |

### After the yes

The caller has heard the `sending` line. Each outcome's line is said at the next turn boundary.

| What happened | The outbox row | What the caller hears | The event |
| --- | --- | --- | --- |
| Your function returned a value the result model parses | `done` | `done`, filled from the result | `ActionCompleted` |
| It raised `ActionRejected` | `rejected` | `failed` | `ActionUnconfirmed`, `kind` `failed` |
| It raised `ActionNotSent` | `not_sent` | `failed` | `ActionUnconfirmed`, `kind` `failed` |
| It timed out, raised anything else, or returned what the result model refuses, and the lookup found the write | `done`, its note `looked_up` | `done`, filled from what the lookup found | `ActionCompleted` |
| The same, and the lookup found nothing, failed or timed out, or the action has none | `flagged` | `unknown`, with no number | `ActionUnconfirmed`, `kind` `unknown` |
| The outbox row could not be written, so your function was never called | none | `failed` | `ActionUnconfirmed`, `kind` `failed` |

- A `done` line the result cannot fill is said as the library's `unknown` line, which claims
  nothing.
- A bug in the job itself is heard as the `error` notice.
- Only `done` adds the action to the call's record, which is what lets the talker speak of it
  afterwards.

## Writing at most once

**What the library does:**

- **A request ID.** Each confirmed action gets one, the same for the same confirmation: a UUID
  made from the call, the action, the read-back's reply, the turn that said yes and the draft.
  Your function reads it as `ctx.request_id`.
- **The outbox row first.** A row keyed by the request ID is written durably before your
  function is called. A second row with the same ID is never written, so one confirmation is
  never sent twice.
- **No retry, no cancel.** A write is never tried again by the library, and never cancelled at
  its timeout.
- **A lookup** asks your system by the request ID, when no reply says how the write ended,
  before anything is said.
- **At the runtime's start**, before any call, each row an earlier process left `sending` (it
  stopped mid-write) is looked up: found, it is `done`; else it is `flagged`. It is never sent
  again.
- **For a person who reconciles:** `t2v outbox list APP` (with `--state flagged`), `t2v outbox
  show APP REQUEST_ID`, and `t2v outbox reconcile APP`, which looks the `sending` and `flagged`
  rows up again and is refused while a server holds the same data folder. A row shows its
  request ID, action, state, note and times, never the draft, the result or the caller's
  subject.

**What your system must do:**

- **Take `ctx.request_id` as an idempotency key**: the same key twice makes one record and gives
  back the first one's result. The library never sends one confirmation twice, but your own
  retries, a proxy's, or a write that reaches you after its timeout can. The example's
  `CallbackDesk.book` books once per request ID.
- **Let the lookup find a write by that key alone.** At the runtime's start the lookup is called
  with the caller's subject and nothing else of the caller: no attributes, no consent words, the
  language `en` (TD-136). A lookup only reads.
- **Keep the request ID on the record**, so the person who reconciles a flagged row can find it
  in your system.
- **Read the flagged rows.** The `unknown` line tells the caller "Our team will check on it":
  someone must.
- **Decide on a second request.** A new read-back is a new confirmation, with a new request ID.
  With `max_per_call` above 1, a caller who confirms the same request in two read-backs makes
  two writes. If two are never wanted, refuse the second in your system or in `validate`.

## The caps

| | `max_per_call` | `limits.actions_per_caller_per_day` |
| --- | --- | --- |
| Where you set it | On the action: `@action(max_per_call=...)` | `T2V_LIMITS__ACTIONS_PER_CALLER_PER_DAY`, for every action of the agent |
| Default | 1 | 20 |
| What it counts | This action's outbox rows for this caller in this call | This action's outbox rows for this caller in the last 24 hours, in any call |

A cap bounds how much a misjudged, repeated or injected action can write, in one call and for
one caller in a day.

- **Both count outbox rows**, which only a confirmed action writes. A proposal, or a read-back
  the caller said no to, counts nothing.
- **Only a write that may have reached your system counts**: a row `sending` (under way, or its
  reply never came), `done`, or `flagged` (the caller heard `unknown`). A row `rejected`
  (`ActionRejected`) or `not_sent` (`ActionNotSent`) counts nothing, since the write was
  definitely not done: with the default of 1, a caller whose write was refused or never sent can
  try again in the same call, and hears a new read-back.
- **Both are checked when the talker calls the action**, before its read-back. The talker is told
  and says so; the caller hears no read-back.
- **The caller is the verified one**, `Caller.subject` from the join token, never anything said
  in the call.

## Lookups: a status tool

Two things look a write up, and they are not the same:

- **`@request_callback.lookup`** is called only by the library: when a write's reply was lost,
  and at the runtime's start. The talker never sees it.
- **A status tool** is a read tool of yours, for "did my callback go through?". Declare it with
  `reports_on=["request_callback"]`, so its result may back up what the talker says about the
  action.

What the output guard needs from a status tool (its claim rule, for an agent with an action):

- **A sentence that claims the action** ("booked your callback", or one of the library's
  default phrases such as "I have booked") is spoken only when this call's record holds the
  action, or a tool whose `reports_on` names it returned a result that succeeded and holds an
  ID-shaped number, so return each record's number, or its last digits. A failed result (a
  `ToolError`), a result that found nothing, a passage, or any other tool's result is no
  evidence of a claim.
- **A status backs only a clause that names one of its numbers**, or a clause with no number
  after an earlier one of the same reply named one (an Arabic comma ends a clause). The record
  backs any. So tell your talker to say the number (or its last digits) first, before what
  happened: "Your callback ending 4417 is booked." A caller with a callback from an earlier
  call who asks its status, then for a new one, does not hear "I have booked it" when no
  action ran, unless that reply already named one of the status's numbers.
- **Every ID-shaped number in such a sentence** must be in that evidence: the action's own
  results in this call, or the status tool's results. A number the caller said, or a passage
  holds, does not count there.
- **So its result must hold only values your tool read for the session's caller**, never an
  argument the talker chose: an echoed number would turn the talker's words into evidence. Find
  the caller's own records by `ctx.caller`; when the number they said matches none of them, say
  so without repeating it.
- **Both its `data` and its `evidence` texts** are evidence.
- **`ctx.past_actions("request_callback")`** gives the callbacks this caller has had done, in
  this call or before it, from the outbox's `done` rows: each a `RecordedAction`, with its
  `action`, `request_id` and `result`. `ctx.record` holds this call's.

The library's safety suite builds the smallest such tool, for a number it made up (`number`);
its case checks that the talker may then say the claim with that number. From
[action_safety.py](../../packages/t2-agentic-voice/src/t2_agentic_voice/testing/action_safety.py):

<!-- fmt:off -->
```python
async def status() -> ToolResult:
    return ToolResult(data={"request": number, "state": "open"}, evidence=(number,))

tool = Tool.from_function(
    status,
    name=STATUS_TOOL,
    description="The status of the caller's own request.",
    reports_on=[scene.action.name],
)
```
<!-- fmt:on -->

The claim rule is lexical. The phrases are each action's `claims` and a short default list per
language, which claims any action; add your own defaults with `T2V_GUARD__CLAIMS`. A claim
worded in no list ("all sorted for you") passes, so list the ways your callers' domain says it
is done.

## Testing your action

`TextCall` holds a call in text, with the real session, talker, yes rule, guard and outbox, on a
fake model: the test above is one. `ActionSafetySuite` runs the adversarial cases on your action
(a yes over the summary, a bare yes over the closing question, a draft that claims consent, a
claim with no record, a lost reply with and without a lookup, a refused write, the same request
twice, the per-call cap), as the example's `test_callback_safety.py` does in English and in Saudi
Arabic. [testing.md](testing.md) has the kit.

## What you provide

- A read tool for each lookup, with every identity parameter bound with `from_caller`.
- For each action: a draft that holds only what the talker should give, fixed sets where your
  system has them, with `Spoken` labels; a read-back that says every value that matters; a
  `done` line from the real result; claim phrases in each language; your own `sending`,
  `failed`, `unknown` and `declined` lines if the library's do not fit.
- A function that takes who the caller is from `ctx.caller`, sends `ctx.request_id` as the
  idempotency key, and raises `ActionRejected` or `ActionNotSent` when it knows the write was
  not done.
- A lookup by the request ID, where your system can find a write.
- A status tool with `reports_on`, whose results hold only what it read for the caller.
- A person who reads the flagged rows.

## The settings, in short

| Setting | Default | What it does |
| --- | --- | --- |
| `@action(timeout_s=...)` | 20 | Seconds the write, `validate` and the lookup may each take |
| `@action(max_per_call=...)` | 1 | How many times the action may be done in one call |
| `ReadBack(max_attempts=...)` | 2 | How many times an unclear answer is asked again |
| `ReadBack(send_words=...)` | none | The action's own send words, added to the preset's |
| `VoiceAgent(ask_on_unlisted_answers=...)` | False | Whether a chat model judges the answers the lists cannot place ([safety.md](safety.md)) |
| `T2V_LIMITS__ACTIONS_PER_CALLER_PER_DAY` | 20 | How many of one action one caller may have done in a day |
| `T2V_WORDS__YES`, `T2V_WORDS__SEND` | none | Your yes and send words, added to each language's, as a JSON map from a language's code to a list |
| `T2V_GUARD__CLAIMS` | none | Your phrases that claim any action, added to the defaults, as the same kind of map |
| `T2V_STORAGE__VAR_DIR` | `var` | The data folder; the outbox is `<agent name>/outbox.sqlite3` in it |
| `@tool(timeout_s=...)` | 5 | Seconds a read tool may take |

Every `T2V_` setting is in the generated [settings reference](../generated/settings.md).
