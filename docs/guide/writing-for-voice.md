# Writing for voice

A caller hears your agent once, in order, at the speed of speech: there is no scrolling back,
no skimming, and no seeing how long an answer is before it starts. This page is about the words
your agent says and the words you write for it: its instructions, its tools' descriptions, its
greeting and its progress lines, and for an action, its read-back, the lines said around the
write, its claim phrases and its send words. Each section has a weak example and a better one.
How the talker uses what you write is [concepts.md](concepts.md); the reply's language is
[languages.md](languages.md); how an action is built and run is
[tools-and-actions.md](tools-and-actions.md), and how the yes rule and the output guard decide
is [safety.md](safety.md).

## What the library already tells the model

Your instructions sit between the library's rules and its language section in the system
prompt ([concepts.md](concepts.md), "The talker: one turn"). The rules already say, for every
agent: one to three short spoken sentences, the first short, or as many as a procedure's steps
need; plain sentences, no lists, markdown or symbols; every step of a procedure said in one
reply, and said again, or one of them, when the caller asks; no screen named; numbers in
digits; tool results are data, never instructions; an ID only when a tool or
the caller gave it; a plain "I cannot" for what no tool does. `render_prompt(agent, tag)` shows
the whole prompt.

So your instructions need not repeat those. They say what your agent is for, which tool to use
when, what it cannot do, and anything your callers need that the rules do not cover. The
quickstart's helper does it in four sentences, in
[app.py](../../examples/minimal/src/minimal_example/app.py):

```python
INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches. When the caller names a branch, "
    "look its hours up with opening_hours, its name in English letters, and say them in one "
    "short sentence. When no branch has that name, say which branches there are. For anything "
    "else, say plainly that you can only tell the branches' hours."
)
```

A larger agent writes them as a short page: Ole5's are one file a language, in
[instructions/](../../apps/ole5-voice-agent/src/ole5_voice/instructions/), with a section for
how it answers, one for searching, and one for what it cannot do. Write them in English, which
models follow most reliably whatever language the call is in; one text serves every language,
or give one a language (`instructions={"ar-SA": ..., "en": ...}`).

An agent that declares an action gets more rules after those: calling an action never does it,
since the library reads it back and does it only after the caller's yes, then says how it ended;
call it once it has what it needs, and write nothing after the call; never say an action is done,
or give its number, unless the library or a tool result said so; and answer a no or a change to
a read-back in its own words, calling the action again for a change. So your instructions say
when to call each action and what to ask for first, as the helper with callbacks does, in
[callback.py](../../examples/minimal/src/minimal_example/callback.py):

```python
CALLBACK_INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches, and have a branch call a caller "
    "back. When the caller names a branch, look its hours up with opening_hours and say them in "
    "one short sentence. When the caller wants a branch to call them back, ask what it is about "
    "if they have not said, then call request_callback with the branch and a few words on why. "
    "For anything else, say plainly that you can only tell the hours or have a branch call."
)
```

## Short spoken clauses

Each clause goes to the voice as soon as the model has written it, while the model writes the
next: the first clause is what the caller waits for, and a long one is long to wait for and long
to sit through before the caller can stop it. An English reply is cut at sentence ends (a comma
cuts only a clause already 120 characters long), since the English voice says each request as a
whole utterance and pieces cut at every comma sound out of breath; an Arabic reply is cut at
every comma and full stop. An arrow in a reply ("Inbox ← Archive") is said as "then".

- Weak: "To reset your password, which you can do from the portal's home page as long as you
  still have access to the mobile number you registered with, first open the portal."
- Better: "You can reset it from the portal. First open the portal's home page."

Start with the answer itself, not with "Great question" or a restatement of what the caller
asked: they know what they asked.

## Every step, by voice

The caller only hears the agent, and may have no screen at all, so never tell them to look at
one (D-075). A procedure is said whole in one reply, in order, each step in one short sentence:
the talker reads every step of the best passage, and keeps them for the rest of the call. The
caller can then ask for all of it again, for "only the second step", or for more about one
step, and can stop the reply by speaking. Write your instructions' line about steps the same
way, as Ole5's do.

- Weak: "Open Settings and choose Security. The full steps are on your screen."
- Better: "First open Settings. Then choose Security. Then press Change password. Enter your old
  password, then the new one twice. Last, press Save."

## Numbers as digits

Ask the model for every number in digits, and have your tools give numbers in digits too. The
output guard reads digits to check that an ID-shaped number was given by a tool or the caller
([concepts.md](concepts.md), "The output guard's ID rule"); a number in words ("twenty-one") it
cannot read. After the guard, the speaking rules say each number in the reply's language, and an
ID digit by digit ([languages.md](languages.md), "Numbers and IDs").

- Weak: "Your request number is four five two one."
- Better: "Your request number is 4521." (said only when a tool's result holds 4521)

## A plain "I cannot"

When no tool gives what the caller asks, the agent says so, in one sentence, and says what it
can do. A guess, or something close offered as if it were the answer, sends the caller away with
the wrong steps.

- Weak: "I think you can probably find that under Reports, maybe in the admin menu."
- Better: "I don't have that information. I can help with how to use the portal."

Say in your instructions what to do when a search finds nothing, and when it fails: Ole5's
instructions tell its talker to say plainly that it does not have that information, or that it
cannot look it up right now and the caller can ask again shortly.

## No promise the agent cannot keep

An agent that says "I've opened a ticket" when it cannot open one, or "someone will call you
back" when no one will, has lied to the caller: the prototype's model once said a ticket was
opened while it was still collecting the details. List in your instructions what the agent
cannot do, and how to say so.

- Weak: "I'll pass this on to the team, and they'll get back to you."
- Better: "I can't open a ticket or transfer the call. You can raise it with the IT desk."

An agent with an action has more help. The library says how the action ended itself, from your
backend's real answer, and the output guard blocks a sentence that holds one of the action's
claim phrases unless the call's record holds that action done, or a status tool reported it
("Claim phrases", below). The
guard checks claims only for an agent that declares an action: for an agent with read tools
alone, nothing stops "I've opened a ticket" but its instructions.

## Tool descriptions

A tool's description tells the talker when to call it, and it is read on every request, in
English. Say what it gives, when to call it, with what, and when not to. Give each parameter a
`description` too, and a fixed form where the caller's words vary (the helper's branch "in
English letters", whatever language the caller speaks).

- Weak: `description="Search."`
- Better: "Search the portal's user guide. Call it once for any question about using the
  portal, with the caller's question in a few words. Do not call it for a greeting or thanks."

Keep what a tool returns short and plain: it is read as data, every token of it paid on the
next request, and the talker speaks from it. An action's description says, beside what it does,
what to collect before calling it: the callback's is "Ask a branch to call the caller back.
Collect the branch and what the call is about first." ("An action's words", below).

## The greeting

The greeting is the first thing the caller hears, and says what the agent is for. End it with a
question, so the caller knows it is their turn.

- Weak: "Welcome to the branch information service of the bank. This line provides opening
  hours for all our branches across the city."
- Better: "Hi! Which branch's opening hours would you like to know?"

## Progress lines

A tool that may run long (a search) names a progress line, spoken when the caller has waited
`progress_after_s` (2.6 s by default) with no answer begun ([concepts.md](concepts.md), "Progress
lines"). Make it short and honest: it says the agent is at work, promises no time, asks
nothing, and is said once a reply, whatever else follows.

- Weak: "Okay, one moment please, I'll be right back with that."
- Better: "I'm checking that for you."

## An action's words

An action (`@action`, [tools-and-actions.md](tools-and-actions.md)) is read back to the caller
before it is done, and every line said around it is yours or the library's, never the model's.
Each is a template: `{field}` is filled from the draft the talker gave (in `done`, from your
backend's real result), a fixed value is said through its `Spoken` label, and `{field:id}` says
a value digit by digit. The output guard does not read these lines, so they must say only what
is true. Each text you give covers every language the agent speaks, or the declaration refuses
the agent; an `ar` text serves both Arabic presets. The minimal example's action asks a branch
to call the caller back, in [callback.py](../../examples/minimal/src/minimal_example/callback.py):

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
```

and its Saudi texts, from the same
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

- **`read_back`** is a pair for each language: the summary, then the closing question (the next
  two sections).
- **`done`** is said once the write succeeded, filled from the result your function returned.
- **`claims`** are the phrases that say the action was done ("Claim phrases", below).
- **The lines you may leave to the library:** `sending`, said while the write runs; `failed` and
  `unknown`, how a write ended other than done; `declined`, said when no clear answer came; and
  `asked_again`, given in `ReadBack(asked_again=...)`. Each is a `Say`, filled from the draft.
  The callback leaves all five to the library.
- **An MSA caller's lines.** A caller who speaks MSA in an `ar-SA` call hears your `ar-SA` lines
  unless a line gives an `ar` text beside its `ar-SA` one: then they hear that text, still in
  the `ar-SA` voice, and the library's own lines in MSA. The agent need not speak `ar` for it.
  Write it formal and as short, with no dialect form («تبي», «اللي», «الحين»), its closing
  question holding the same send word («هل أرسلها؟», hal ursiluha: shall I send it?). The
  callback's Saudi texts, keyed `ar`, are read for both; Ole5's
  [lines.py](../../apps/ole5-voice-agent/src/ole5_voice/tickets/lines.py) gives each line an
  MSA text of its own.

## The read-back's summary

The summary is everything the caller is asked to agree to. They must hear it whole before
their answer counts: a yes said over it counts for nothing, and other words over it stop it and
go to the talker, nothing sent and the draft declined. Nothing is shown either: the caller may
have no screen, `show_draft` is off by default, and no code reads it yet, so no card of the
draft appears whatever it says. Write it for the ear:

- **Every fact the caller must check**, each said plainly. A yes counts only once the summary
  has played whole, and the caller may answer over the closing question, so no fact goes in the
  question alone.
- **Fixed values by their labels.** A `Literal` field the summary names needs a `Spoken` label
  for each of its values, or `@action` refuses it; a language with no label for a value says
  it as written. Use the words a caller knows, never your system's codes. The callback's
  branch, from [callback.py](../../examples/minimal/src/minimal_example/callback.py):

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

- **Digits the caller can check.** `{field:id}` says a value digit by digit, a run of 8 digits
  or more in groups of four with a pause between, while the caption shows it as written. A plain
  `{field}` follows the speaking rules, which say a run of up to 4 digits that starts with no
  zero as a number: "4101" as "four thousand one hundred one" ([languages.md](languages.md),
  "Numbers and IDs"). Use `:id` for every number the caller reads off a card or a device, or
  will write down. Speech-to-text often gets a long number wrong, so a number the caller said is
  worth hearing back digit by digit before it is acted on.
- **Short.** The longer the summary, the longer the caller waits before an answer counts, and
  the likelier they speak before it ends. One Orpheus request holds 200 characters, numbers
  said in words counted, so a longer summary is said in pieces, and every piece must play whole.
  Bound the draft's free text (`max_length`), and ask for it in a few words in your instructions,
  as the callback does with its reason.

- Weak: "Okay, let me read that back: a callback request will be created for the branch you
  mentioned about the issue you described, and they will be in touch soon." It names neither the
  branch nor the reason, so the caller cannot check them; it promises a time; and "okay" is a
  listening sound and "read" a repeat word, so its own echo could make the agent say it again
  ("Why no fixed line may hold a command word", below).
- Better: "I'll ask the Olaya branch to call you back about: my order did not arrive." (the
  callback's summary, filled)

## The closing question

The closing question follows the summary as a clause of its own, and asks for the go-ahead.
Make it one short question that holds a send word, the verb a caller says back to send it
("send", «أرسل»: "Send words", below), and no yes word.

- **Over the question, a yes needs a send word.** A caller who knows the answer often gives it
  before the question ends. Said over it, "yes, send it" or «نعم أرسلها» sends, and a bare
  "yes" is asked again (invariant 1). Once the question has ended, a yes alone is enough, polite
  words beside it included ("yes, please").
- **What the lists never take as a yes.** A send word with no yes word ("send it", "okay, send
  it", «أرسلها») is asked again; so are a yes beside a no word, a yes asked back ("yes?"), and a
  listening sound alone ("okay", «تمام»), which is no yes word (TD-133). A word on none of the
  lists makes the answer a change, which goes to the talker. An agent that sets
  `ask_on_unlisted_answers` has a chat model judge first what the lists leave unplaced,
  «يلا أرسلها» (come on, send it) among them, within the yes rule's rails
  ([safety.md](safety.md)).
- **What the library says when it asks again.** An unclear answer hears the `asked_again`
  line: "Sorry, I didn't catch that. Shall I go ahead?", or in Saudi Arabic «المعذرة، ما وضح لي
  ردك. أسجل الطلب؟» (sorry, your answer wasn't clear to me; shall I register the request?). It is
  said at most `max_attempts` times (2 by default); after the last, the agent says `declined`
  and nothing is sent. Your own, `ReadBack(asked_again=Say(...))`, is a short question again,
  which may hold a send word as the closing question does, and no yes word: a bare yes said
  over it can count as said after the closing question (TD-133).
- **Other answers.** "Can you repeat that" has the whole read-back said again, and only a yes
  after that reading counts. A stop or pause word ("stop", «وقف», "wait") over the read-back
  ends it with nothing sent, and the talker asks what to change, keeping the draft. A no, or a
  change, goes to the talker, which answers in its own words.

- Weak: "Is that correct, or would you like to change anything?" It asks two things; "correct"
  is a yes word, which no fixed line may hold; and with no send word in it, an eager "yes,
  correct" said over it is asked again.
- Better: "Shall I send it?" (the callback's), or «أرسل الطلب؟» (shall I send the request?): one
  question, its verb a send word, so "yes, send it" said over it sends, and so does a "yes"
  once it has ended.

## While the write runs, and when nothing was decided

Once the caller's yes is heard, the agent says the `sending` line as its answer while the write
runs as a job of its own, and how it ended is said at the next turn boundary: `done`, `failed`
(definitely not done) or `unknown` (no reply, and no lookup found the write). The `sending` line
comes before any result, so it says the agent is at work and never that the action is done; it
may name the draft's fields. The library's is "Sending it now, just a few seconds.", in Saudi
Arabic «ثواني، جالس أسجل طلبك.» (seconds, I'm registering your request).

- Weak: "Done! The branch will call you shortly." The write may still fail, and the caller then
  hears "done", then that it failed.
- Better: "I'm asking the {branch} branch to call you now." (`sending=Say(...)`, with a text for
  each language, the branch said by its label)

The `declined` line is said only when no clear answer came after the last ask-again. After a
plain no or a change the talker answers in its own words, and after a stop it asks what to
change; `declined` is said where no talker turn follows, so it says plainly that nothing was
done. The library's is "I couldn't get a clear answer, so I haven't sent anything."

- Weak: "Alright, cancelled." "Alright" is a listening sound, and "cancelled" suggests something
  had been made.
- Better: "I didn't get a clear answer, so I haven't asked the branch to call you."

The library's `unknown` line tells the caller "Our team will check on it". Keep that true:
someone in your team reconciles the writes it flags (`t2v outbox`,
[tools-and-actions.md](tools-and-actions.md)), or give your own line.

## Claim phrases

An action's `claims` are the phrases that say it was done, in each language the agent speaks.
The output guard reads every clause the talker writes, and blocks one that holds a phrase of an
action unless the call's record holds that action done, or a tool declared with
`reports_on=["<action>"]` returned it; every ID-shaped number in that clause must then be found
in that action's own evidence, never in a passage or the caller's words. A short default list
of phrases ("I've created", "has been booked", «تم إنشاء», «سجلت لك» and the like) claims any
action; the `guard.claims` setting adds to it (`T2V_GUARD__CLAIMS`), and no default can be
removed. Phrases match as whole words, in the guard's normalized form, and also after «و» or
«ف» written onto the first word («وتم»).

- Weak: `Claims({"en": ["callback"]})`. It blocks "Would you like a callback?", said before any
  callback is booked, and says nothing about "I've arranged for Olaya to ring you".
- Better: the callback's own, past-tense claims that it was done, in the domain's words:
  "callback is booked", "booked your callback", "asked the branch to call", and «طلبت منهم
  يتصلون» (I asked them to call) and «سجلت طلب الاتصال» (I booked the callback).

The guard is lexical: a claim worded as no phrase is, such as "I've arranged for Olaya to ring
you", passes. Add the wordings your model writes as you find them in your tests and your calls'
transcripts. Give a phrase to one action only: a phrase on two actions' lists needs the record of
both before it passes, so put a phrase every action shares in `guard.claims` instead.

A phrase that only introduces a number, such as "your ticket number is", stops a passage's number
said as the caller's, but until a record or a status holds one it also blocks a question that
asks for the number and the caller's own number read back. List one only where a passage may
hold numbers of your records' shape, as Ole5 does, and keep it out of your own lines, `done`
among them: the talker reads them in the call's history and copies their words, and `TextCall`
reads a clause that copies a piece of one as the runtime's line, unchecked.

## Send words

A send word is a caller's go-ahead to send: over the closing question a yes needs one beside
it, and the closing question holds one, so the caller hears the word they can say back. The
presets' send words:

| Language | Send words |
| --- | --- |
| English | "send", "send it", "submit", "submit it", "go ahead", "do it", "confirm", "proceed", and the Latin spellings Whisper writes for «أرسلها» ("arsilha", "erselha" and others) |
| Arabic, both presets | «أرسل», «أرسلها», «أرسله» (send, send it); «قدمها», «قدمه» (submit it); «اعتمدها», «اعتمده» (approve it); «نفذها», «نفذه» (carry it out); «سجلها», «سجله» (register it); «توكل», «توكل على الله» (go ahead); «قم بإرساله» (send it, MSA) |

And the yes words a yes needs:

| Language | Yes words |
| --- | --- |
| English | "yes", "yeah", "yep", "yup", "sure", "of course", "correct", "that's right", "absolutely", "definitely", and «نعم» and «ايوه» as Whisper writes them in Latin letters ("naam", "aywa", "aiwa") |
| Arabic, both presets | «نعم», «ايه», «اي», «ايوه», «ايوا», «أكيد», «موافق», «طبعا», «بالتأكيد» |

Words are compared in a normalized form, so «ارسلها» written without its hamza still matches,
and a send word may follow «و» («وأرسلها»). When your closing question's verb is on no list,
add it: `ReadBack(..., send_words={"en": ["book it"], "ar": [...]})` gives the action's own,
keyed by `ar` for both Arabic presets or `en`; the `words` settings group adds send words and yes
words for every action with no code change, as a JSON map by the same codes:

```bash
T2V_WORDS__SEND='{"en": ["..."], "ar": ["..."]}'
T2V_WORDS__YES='{"en": ["..."]}'
```

- Weak: "Shall I book it?" with no send word added. "Yes, book it" said over it holds "book", a
  word on no list, so the lists take it as a change: the draft goes back to the talker and
  nothing is sent.
- Better: `send_words={"en": ["book it"]}` beside it, or a question whose verb is already a send
  word: "Shall I send it?"

The lists have no public view yet; they are the yes rule's own, in
[yes_words.py](../../packages/t2-agentic-voice/src/t2_agentic_voice/domain/yes_words.py), and
the rule itself is [safety.md](safety.md)'s.

## Why no fixed line may hold a command word

The greeting, the progress lines, the notices and every line of an action (its summary and
closing question, the line that asks again, `sending`, `done`, `failed`, `unknown` and
`declined`) are fixed lines, said as written while the caller's microphone is open. On a
laptop's speakers the agent's voice comes back into the microphone past the browser's echo
cancellation, and Whisper may hear part of a line as the caller's: a stop or wait word heard
that way stops the agent, a repeat word makes it say its last reply again, and a listening sound
is taken as the caller's. The rule lets the reply go on for the agent's own words it recognises
whole, but an echo heard only in part is not; so keep every word of the presets' stop, wait,
repeat and listening lists out of every fixed line. The weak progress line above fails twice:
"okay" is a listening sound, "one moment" a wait word.

Keep every yes word out of them too. The yes rule's lists cannot tell the agent's voice from the
caller's, so a yes word heard back beside the closing question's send word would read as the
caller's "yes, send it". Only the closing question, and the line that asks it again, hold a send
word: the caller needs one there, and the question heard back cannot confirm. On the lists, an
answer with a send word and no yes word is asked again, so the question heard back as "send
it" sends nothing; and for an agent that has a chat model judge what the lists leave unplaced,
the yes rule refuses the model's yes for words that copy the read-back's own lines, or the line
that asks it again, begun while they played or within 300 ms after ([safety.md](safety.md)).

The lists hold some words you would not guess, among them "read", "continue" and "ok" in
English, and «خلاص», «تمام», «طيب» and «زين» in Arabic, and the yes words "correct", "sure" and
«طبعا»: `Language.english(greeting=...).words` shows a preset's interruption lists, and the yes
and send words are listed above. The quickstart's helper is held to this by a
test, which reads each fixed line as the rule reads words, in
[test_helper.py](../../tests/minimal_example/test_helper.py):

```python
def _held(line: str, code: Code) -> list[str]:
    """The words of the helper's stop, wait, repeat and listening lists that `line` holds as
    whole words, compared in the interruption rule's form."""
    words = helper.phrases.words(code)
    listed = [*words.stop, *words.wait, *words.repeat, *words.backchannel]
    form = f" {normalize_arabic(provider_text(line))} "
    return [word for word in listed if f" {normalize_arabic(provider_text(word))} " in form]
```

Write one like it for your agent's greetings, progress lines, any notices you replace and your
actions' lines, with the yes words added and the send words allowed only in a closing question
and its ask-again line, and run it in your tests: `@action` does not check the words of your
lines. The library's own lines are held to the same rule by
[test_fixed_lines_words.py](../../tests/t2_agentic_voice/domain/test_fixed_lines_words.py).
