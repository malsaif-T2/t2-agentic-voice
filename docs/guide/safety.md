# Safety: the yes rule and the output guard

An agent with actions does things for the caller: it opens a ticket, books a callback, hands the
call to a person. Two rules keep it honest, and the library runs both in every call of such an
agent:

- **The yes rule.** An action runs only after the caller's own spoken yes to a read-back of it
  that played whole (invariant 1).
- **The output guard.** No sentence the talker writes says an ID-shaped number, or claims an
  action was done, without evidence from the call (invariant 2).

This page says how each rule decides, what the library guarantees, and what stays yours. The
invariants themselves are in [SECURITY.md](../SECURITY.md). How to declare an action, and what
happens around its write, is [tools-and-actions.md](tools-and-actions.md); testing your actions
is [testing.md](testing.md). Why each rule works as it does is D-080, D-081, D-082 and D-084
in [decisions.md](../design/decisions.md), and plan 007.

**Status.** Built and tested on fake models and fake backends: the yes rule, the model check of
the words its lists leave unplaced (off unless an agent asks for it), the guard's ID and claim
rules, and the stray-script filter before them. Plan 007's scenario runs and its live calls on
real speakers have not been made yet, so no rate on this page is measured on real callers.

## Words used on this page

- **The read-back**: what the runtime says before an action runs, filled from the draft the
  talker wrote. It has two parts, written apart: the **summary** ("I'll ask the Olaya branch to
  call you back about: my order did not arrive.") and the **closing question** ("Shall I send
  it?"). Both are your templates; the talker never writes them.
- **Heard words**: what speech-to-text wrote for one of the caller's turns.
- **The receipt**: the library's record that the summary played whole.
- **A clause**: one spoken piece of a reply ([concepts.md](concepts.md)).

## The yes rule

### Its two inputs

The rule decides from two things, and nothing else:

1. **The caller's heard words**: the text of the turn's own speech-to-text result, with the time
   the caller began to speak. Only the voice session builds them. Words typed in a test
   (`TextCall`) count only under `env` `test`, and a runtime refuses to be served under `test`.
2. **The read-back receipt**: built by the voice session only when the summary played whole:
   every clause of it reported played to its end by the audio transport (never by the
   browser), with audio, none cut short, and no speech over it still being judged. It holds the
   action and the exact draft that was read back.

Both are sealed: no tool argument, no text of the model's and no field of the draft can stand in
for either. An action whose draft has a field named like consent (`confirmed`, `approved`,
`caller_consent`) is refused when the action is built. The confirmed action the rule issues
copies the receipt's draft, so what runs is what the caller heard. A change needs a new
read-back.

### When an answer counts

What counts is when the caller **began** to speak, not when the transcript came back. Whisper
gives no partial transcripts, so a yes said over the summary arrives after the summary ended,
and only its start tells it apart.

| The caller began to speak | What it is |
| --- | --- |
| Before the summary's last clause finished playing | Never an answer. Yes words, send words, fillers and listening sounds only: ignored, and the summary plays on. A stop or pause word ("stop", «وقف», «خلاص», "wait"), alone or beside other words: the read-back stops, nothing is sent, and the talker asks what to change, keeping the draft; such words are never ignored, though «خلاص» is also a filler below. Words that stop it and are a plain no by the lists below (a no word, with only send words and fillers beside it: "No, cancel it, don't send it.", «لا لا، لا ترسلها»): declined as a no, handed to the talker, which answers in its own words. Other words that stop it (as the interruption rule decides, [concepts.md](concepts.md)): a correction, handed to the talker ("No, not Monday, since Thursday."). A single word that is no stop word is too few to stop it. A repeat request: the read-back is said again. A turn begun before the read-back's first audio, which then plays on over it: handed to the talker as a correction (or a no, for a plain no), so a later yes confirms nothing until a new read-back plays |
| After the summary, while the closing question plays | An answer **over the closing question**: a yes needs a send word beside it |
| After the closing question's last clause played | An answer: a yes word is enough |

A stop or pause word over the closing question, or said alone while the agent waits for the
answer, stops the read-back too, as over the summary. A read-back said again is a new one, and
only an answer to the new reading counts. When the summary never plays whole (a stop cut it, a
clause failed, the call ended), there is no receipt, and nothing can be confirmed until a new
read-back plays. A turn heard as nothing (silence, or text Whisper made up for noise) never
reaches the rule.

### The lists

The rule reads four lists in each language, keyed by its code (`ar` for both Arabic presets,
`en`). Words are compared in a normalized form (harakat dropped, the forms of alef made one,
punctuation read as a space), and a phrase of several words counts as one word, the longest
first. Some of each preset's words:

| List | English | Arabic |
| --- | --- | --- |
| Yes words | yes, yeah, yep, sure, of course, correct, absolutely | «نعم», «ايه», «ايوه», «اكيد», «طبعا», «موافق» |
| Send words | send, send it, submit, go ahead, do it, confirm, proceed | «أرسل», «أرسلها», «قدمها», «اعتمدها», «نفذها», «سجلها», «توكل» |
| No words | no, not, never, cancel, nope, never mind, no thanks | «لا», «مو», «بلاش», «ألغيها», «مابي», «لا ترسلها», «كلا» |
| Fillers | please, now, thanks, it, the, my request, and every listening sound ("okay", "mm-hmm") | «لو سمحت», «من فضلك», «الحين», «يلا», «خلاص», «شكرا», and every listening sound («تمام», «طيب») |

The English lists also hold the Latin spellings Whisper wrote for the Arabic yes and send words
in an English call ("aywa", "arsilha"). A send word may be written after waw (and): «وأرسلها».
A word on two lists counts as a no first, then a yes, then a send word, then a filler. The no
words and fillers start from the interruption rule's no words and listening sounds
([concepts.md](concepts.md), "The words"). «خلاص» ("enough") is a filler here and a stop word
of the interruption rule: once the read-back played, «ايه خلاص أرسلها» ("yes, that's it, send
it") is a yes, but «خلاص» said over the summary stops it, as any stop word does.

What you can add, and nothing else reaches these lists:

- **Yes words** your callers use: `T2V_WORDS__YES`, a JSON map from a language's code to its
  words, as `{"ar": ["..."], "en": ["..."]}`.
- **Send words**: `T2V_WORDS__SEND` for every action, or an action's own in its read-back,
  `ReadBack(..., send_words={"en": ["book it"]})`.

The no words and fillers are the presets' only: a word added to `T2V_WORDS__NO` or the
declaration's `phrases=` is read by the interruption rule, not by the yes rule.

### What the rule decides

The rule reads the turn's own heard words, never an earlier turn's or text from a tool or the
talker. The first step that applies decides:

| Step | The words | The answer |
| --- | --- | --- |
| 1 | Begun before the summary ended, or typed outside a test | asked again, as if nothing was heard |
| 2 | Any word on none of the lists | a **correction**: the words go to the talker |
| 3 | A no word | **declined**; asked again when a yes word is beside it |
| 4 | No yes word (send words or fillers only), or a question mark («نعم؟», "yes?") | asked again |
| 5 | A yes word over the closing question, with no send word beside it | asked again |
| 6 | A yes word, with only send words and fillers beside it | **yes** |

So, for an agent that does not ask a model (the next section):

- "yes, send it" and «نعم أرسلها» are a yes, over the closing question or after it.
- "yes please" and a bare "yes" are a yes once the question ended; over it, both are asked
  again.
- "send it" alone is asked again.
- «نعم بس غيّر العنوان» ("yes, but change the address") is a correction: «بس» and «غيّر» are on
  no list. So is "no, make it Malaz", which step 2 reaches before step 3.
- "pardon?" is a correction too, not asked again: "pardon" is on no list, and step 2 comes
  before step 4. Any other question with a word on no list is one as well ("How do I reset my
  password?"): the read-back ends, and the talker answers it. Only a question of listed words,
  such as "yes?", is asked again.
- "okay" or «تمام» alone is asked again: a listening sound is a filler, never a yes.

### Why a yes over the closing question needs a send word

Two things make a yes said while the closing question still plays doubtful:

- **An eager caller.** A caller who says "yes" before the question ends may be agreeing with the
  summary, not asking for it to be sent. "Yes, send it" says plainly that they want it sent.
- **The agent's own voice.** On a laptop's speakers, the agent's voice can come back through the
  microphone. The closing question holds a send word ("Shall I send it?", «أرسل الطلب؟»), so its
  echo is heard as a send word, never as a yes word. That is why the lists never take a send
  word without a yes word as a yes.

Write each closing question to ask to send, with a send word and no yes word ("Shall I send
it?"). A yes word heard back beside the question's own send word reads as the caller's "yes,
send it", and the lists confirm it: "Is that correct? Shall I send it?" heard back as "correct,
send it" is a yes. Keep yes words out of your `asked_again` line too: a bare yes said over it
counts as said after the closing question (TD-133), so its yes word heard back would confirm.
When your question uses another verb ("Shall I book it?"), add that verb to the action's
`send_words`, or a caller's "yes, book it" is a correction. Nothing checks the words of these
lines: not that a closing question holds a send word, nor that it holds no yes word.

### When any yes books: `interruptions.yes_over_read_back`

An app may turn on `interruptions.yes_over_read_back` (off by default; D-108, the owner's ruling
of 2026-11-17, "Any yes books"); the flight agent does. (Its lean agent, served when
`FLIGHT_VOICE_AGENT=lean`, has no read-back at all: it books from a tool once a booking check in
the app's code holds, a departure from "only actions act" for its mock airline alone, D-113; an
app that books for real declares an action.) Then:

- **A yes over the summary is held, not dropped.** A yes, a send word or the action's own send
  words, with only fillers beside them, said over the summary after its first audio ("yes",
  «إيه», «نعم», "book it"), lets the summary play on and is held. For an agent that asks, words
  the lists leave unplaced go to the chat model first: its yes is held the same way, and its no
  or change stops the read-back and declines it. Once the summary has played in full, with no
  other words begun since, the held yes books: the closing question is cut, or never said, and
  the `sending` line answers the caller's yes.
- **Other words drop it.** A second yes, a filler or a listening sound keeps it held; any other
  words after it (a single no, a question, a word on no list) drop it, and the caller answers
  after the question as before. Words that stop the summary decline it, as before.
- **A bare yes over the closing question books**, and so does «خلاص» beside a yes or a send
  word («خلاص أرسلها»), over the summary or the question. «خلاص» alone still stops it.

Its safety holds as before: only the caller's own heard words, read against a receipt of the
summary played in full; never words begun before the read-back's first audio, never the agent's
own lines heard back, and never a yes held on a read-back that a new one replaced. Keep the
closing question free of yes words, as above: the rule asks again a bare yes that is the
question's own words heard back, and a question with no yes word leaves nothing to mistake.

### What follows each answer

- **A yes**: the action's `sending` line is said ("Sending it now, just a few seconds.", unless
  you give one), then the write runs as a job outside the turn, so a stop never cuts it in half.
  The outcome line is said at the next pause in the call, from the write's real result
  ([tools-and-actions.md](tools-and-actions.md)).
- **Declined, or a correction**: the read-back ends and nothing is sent. The talker answers in
  its own words, told how the caller declined it (a no, a change, a stop). For a change, it
  calls the action again, and the new draft is read back from the start. After a no the caller
  can go on at once: ask another question, or ask for another action, which is read back anew.
- **Asked again**: the action's `asked_again` line ("Sorry, I didn't catch that. Shall I go
  ahead?", unless you give one), at most `max_attempts` times (2 by default). The next unclear
  answer ends the read-back with the `declined` line ("I couldn't get a clear answer, so I
  haven't sent anything."), and nothing is sent.

A runtime's observers get `ConfirmationRequested` as each read-back's first audio plays, and
`ConfirmationAnswered` for each answer the rule decides: its `decision` (`yes`, `declined`,
`correction` or `asked_again`) and `by` (`words` for the lists, `model` for the check below).
Both are in the `events` facade.

## The model check: words the lists cannot place

No list holds every way a caller agrees, and Whisper misspells words. An agent that sets
`ask_on_unlisted_answers=True` on its `VoiceAgent` has a chat model judge the words the lists
leave unplaced, within rails the yes rule keeps (D-082, the owner's rulings). It is off by
default: an agent that does not set it, and every test script written for one, sees no new
request.

**What goes to the model.** Only an answer heard once the summary played whole, and only one of
these:

- words with a word on none of the lists, which the lists alone make a correction: "go for it",
  "sure thing", "yes, but make it urgent", «صح» ("right"), a hesitation Whisper wrote as
  «امممم», a question such as "How do I reset my password?" (whose `send` or `yes` rail 1 below
  asks again), or a request for something else ("No thanks, I want to open another ticket.");
- send words among fillers, with no yes word and no question mark: "please send it", «يلا
  أرسلها» ("come on, send it");
- a send word said alone: «أرسلها», «توكل», "go ahead", "send it";
- a yes among fillers over the closing question, with no send word: "yes, please".

Everything else is the lists' answer, and no model is asked: a listed yes ("yes, send it",
«اكيد», "sure"), a listed no, a bare yes over the closing question, fillers or listening sounds
alone, a yes beside a no, a question mark among listed words only ("yes?"), and anything begun
over the summary.

**The request.** One a turn, holding as data only the read-back's summary and closing question
and the caller's heard words: no tool result, no text of the talker's and no history. It runs on
Groq as `openai/gpt-oss-120b` whatever `llm.model` says, at low reasoning effort, temperature 0
and at most 256 output tokens. It is counted in the call's usage, and logged by its outcome's
kind, never the words. The model answers one word:

| Word | Means | For example |
| --- | --- | --- |
| `send` | an outright go-ahead to send it | "go for it", «يلا أرسلها» |
| `yes` | agreement only, with no outright go-ahead | "sure thing", «صح» |
| `no` | a refusal or a cancel, or an answer that turns to something else instead: a question, about this action or anything else, or a request for something other than what was read back (another ticket, another topic) | "forget it", "How do I reset my password?", «أبي أفتح تذكرة ثانية» ("I want to open another ticket") |
| `change` | a wish to change, add or leave out anything, a yes with a change in it among them | "yes, but make it urgent" |
| `unclear` | a sound, a hesitation, a word that answers nothing, or the agent's own words heard back; that comes first, even for a question ("Shall I send it?" heard back) | «امممم» |

Any other answer counts as `unclear`. A question in answer to a read-back is a `no` (the owner's
answer of 2026-11-11): the read-back ends, nothing is sent, and the turn goes to the talker with
its words whole and the no note, so the talker answers the question, or reads back the new
action the caller asked for, in its own words, with no ask-again line. A model that still says
`unclear` has it asked again; one that fails or is too slow has it asked again too, unless the
words hold a no word ("No, forget that one, open a ticket about the signature instead"): then
the read-back ends the same way, handed to the talker, as the rails below say.

**The rails.** The model's word is never taken as it is: the yes rule decides what it makes.
First, whatever the model says, the receipt built when the words reached the rule must still
stand, or the answer is asked again. Then:

| The model says | The yes rule makes it |
| --- | --- |
| `no` | declined, unless the words are the agent's own, heard back (rail 3 below): asked again |
| `change` | a correction, unless the words are the agent's own, heard back (rail 3 below): asked again |
| `unclear`, or any other answer | asked again |
| nothing: a failed request, or no answer within 2.5 s on the call's clock, while the caller waits in silence | declined when the words hold a no word ("no", «لا», «ما»), unless they are the agent's own, heard back (rail 3 below): asked again; for any other words, asked again |
| `send` or `yes` | a yes, unless one of the rails below holds |

So the agent's own lines heard back never confirm, cancel or change a read-back, whatever the
model says, or when it says nothing.

A `send` or a `yes` is not a yes when:

1. the words hold a no word or a question mark: asked again;
2. the words hold a change marker ("but", "change", "instead", "except", "actually", "rather";
   «بس», «لكن», «غيّر», «عدّل», «بدّل», «بدال», «خلها», each also after waw): a correction, so
   "yes, but make it urgent" is never a yes;
3. the words are the agent's own, heard back: every word a word of the summary, the closing
   question or the asked-again line, or one letter off for a word of three letters or more
   ("send it", from "Shall I send it?"; "the printer is broken, shall I sent it", across the
   summary's end): asked again. This holds only for speech begun while one of those lines was playing, or
   within 300 ms after it ended (none after the client's Stop), while the agent's voice may
   still come back through the speakers: speech begun later cannot be its echo;
4. the answer was said over the closing question, and the model said `yes`, agreement only:
   there its `yes` confirms only when a listed send word stands beside other words ("yes, go
   ahead and send it to Malaz"). Its `yes` to a send word said alone («أرسلها», "go ahead") is
   asked again, as a bare «نعم» is. Over the question, only its `send` confirms a send word said
   alone.

**In the call.** The caller waits in silence while the check runs, 2.5 s at most, and the wait
counts in the turn's time to first audio. (The limit was 1.5 s until run A's second dev run,
where 3 of the check's 24 requests ran out and the caller was asked again: D-082.) A request
that fails or runs out of time is no answer: words that hold a no word are then declined, as
the model's `no` is, and the talker answers them; other words are asked again. (Until run A's
third dev run they were all asked again; there 5 of the check's 24 requests ran out, and twice
a caller's "No, forget that one. Open a ticket about the electronic signature instead" was
asked again, so their next "Yes, send it." made the ticket they had dropped: D-082.) A newer
answer from the caller, the client's Stop and the call's end cancel a request still waiting,
so only the newest answer decides. A word that lands when its read-back is no longer the
current one (said again, stopped, or the call ending) decides nothing, and nothing is said for
it.

Turn it on when your callers agree in words no list holds. It costs one chat request for each
unplaced answer, and a request that fails or times out asks the caller again, even for words
the lists alone would have made a correction, unless they hold a no word, which ends the
read-back as a no.

## The output guard

Every clause the talker writes is read before it goes to text-to-speech. The runtime's own lines
are not read: the greetings, the notices, the progress lines, and an action's read-back,
`sending`, outcome, asked-again and declined lines. They are templates, filled from the draft
(which the caller hears read back) or from the write's real result, so the `done` line may say
the number your system returned.

**What the guard reads** is the text as the stray-script filter left it (D-084;
[languages.md](languages.md), "Scripts a reply may hold"). Before anything reads what the talker
writes, each character of a script none of your agent's languages writes, and each emoji, is
taken out, and a fullwidth form or another script's digit is written as its plain form; a tool
call's string values get the same, never its keys. The guard then reads the text that is said,
so a stray character cannot hide a claim from it, and the order is a safety rule: «تم重 إنشاء
طلبك» would pass the claim rule as two words if the guard read it first, then be said as «تم
إنشاء طلبك». The same goes for numbers: "12重34重5" is read as 12345, and "４５：２１" as "45:21".
`T2V_GUARD__REMOVE_STRAY_SCRIPT=false` turns the filter off, and the guard reads the text as the
model wrote it.

A clause past the reply's question limit never reaches the guard (D-085;
[writing-for-voice.md](writing-for-voice.md), "One question at a time"): it is not said, so it
is neither checked nor blocked, and no notice is said in its place. A question the guard
blocked was not said, so it does not count toward the limit.

Nor does the model's reasoning written into its answer (D-089). gpt-oss now and then glues some
of it to a sentence of its answer with no space between («…الملاحظة.User: … Possibly they want
us to …»). Where a sentence glued so begins with a capital Latin letter in a reply in Arabic,
or with one of the reasoning's openings ("We need", "According to", "The user", …) in any
language, or any sentence begins with a speaker's label ("User:"), nothing of the model's text
from there on is said, and the reply stops as the question limit stops one. A glued sentence
that only starts the answer again is said, cut into a clause of its own. With
`T2V_GUARD__DROP_STAGE_NOTES=true` (off by default), a stage note or a tag is one too: in a reply
in Arabic, a parenthesis or bracket glued to a sentence's end with a capital Latin letter after
it; in any language, one that opens a stage word ("(Waiting", "[No output"); and a "<" that
opens a tag ("<action", "<data", or one of your tools' or actions' names). Arabic in
parentheses is said.

### The ID rule

An ID-shaped number is said only with evidence from this call. It runs for every agent, with or
without actions; [concepts.md](concepts.md) has it in full ("The output guard's ID rule").

- **ID-shaped** is `guard.min_id_digits` digits or more (3 by default), counted after digit
  words and Arabic-Indic digits are made digits, or a match of one of `guard.id_patterns`.
- **Evidence** is what this call has seen: the results of its tools (a passage's text and a
  `ToolResult`'s `evidence` included), the results of the actions completed in it, and the
  caller's own heard words.

### The claim rule

It runs only for an agent that declares at least one action.

**A claim phrase** is one of these, in any of your languages whatever the reply's (a model may
write a claim in its other language), matched as whole words on the normalized clause, and also
after waw or feh written onto its first word («وتم»):

- **the action's own `claims`**, which claim that action (the example's "callback is booked",
  "booked your callback");
- **the library's default list**, which claims any action: past-tense phrases, mostly first
  person, such as "I've created", "I have submitted", "has been registered", "successfully
  sent", «تم إنشاء» ("it was created"), «تم تسجيل طلبك» ("your request was registered") and
  «سجلت لك» ("I registered for you");
- **your additions to the default list**, `T2V_GUARD__CLAIMS`, a JSON map from a language's
  code to its phrases. A default phrase cannot be removed.

**Evidence of a claim** about an action is only:

- the result of that action's write, completed in this call (the call's record, whose entries
  only the library's action runner makes). It backs any claim about the action, with a number
  or none;
- a result that succeeded, in this call, of one of your tools declared with
  `reports_on=["that_action"]`, such as a status tool, when it holds an ID-shaped number (or a
  match of `guard.id_patterns`). A status that found nothing holds none, and backs no claim.
  A status backs fewer claims than the record: only a clause that names one of its numbers
  (the whole number, or the last digits it gives back), or a clause with no number after an
  earlier clause of the same reply named one. So "Your ticket ending 4417 is open. It has
  been escalated." is said whole, while "I've opened a ticket for you", after a status of an
  older ticket and with no action called, is blocked. "It has been escalated" alone, in a
  later reply that names no number, is blocked too. An Arabic comma ends a clause, so a claim
  written before the number («تم تصعيد طلبك، اللي ينتهي بـ 4417») is blocked: tell your talker
  to say the number first, before what happened to the ticket.

A passage, the caller's words, or any other tool's result is no evidence of a claim. A clause
with a default phrase passes when some action backs it.

**Its numbers.** Every ID-shaped number in a claiming clause must be in the claimed action's own
evidence: a number a passage holds, or the caller said, is no proof that the action made it. A
clause with no claim phrase goes to the ID rule.

**After an action call.** Once the talker calls an action in a model request, the text it writes
after the call is dropped, neither spoken nor blocked. The read-back ends the reply, so nothing
the talker writes is said until the turn after it. A call the runner refuses (a field that is
not valid, `validate`, a cap) reads nothing back, and the talker may speak again, under both
rules, to say why or ask for what is missing.

### A clause that breaks a rule

- It is never spoken. By `guard.on_block`, it and the rest of the reply are dropped
  (`drop_rest`, the default), or only it (`drop_clause`).
- The `error` notice is said in its place, or `cut_off` after words already said, once a reply.
- Observers get `GuardBlocked`, its `reason` `unsupported_claim` (the claim rule) or
  `unsupported_id` (the ID rule).
- The talker's next turn holds a note that a sentence was held back, never the sentence; for a
  claim, that it said an action was done that no record or status result holds.
- In a test, `turn.expect.blocked()` checks that a clause was held back, and `call.violations`
  lists any clause said that breaks a rule ([testing.md](testing.md)).

## What the library guarantees, and what stays yours

| The library guarantees | What stays yours |
| --- | --- |
| Only the yes rule issues a confirmed action, and the action runner runs no write without one | Your system's own checks and permissions: the yes rule proves the caller agreed, not that they may do it. Check in `validate`, before the read-back, and refuse in `execute` with `ActionRejected` |
| Consent is the caller's own speech, begun after the summary played whole; typed words only in a test | Who the caller is: an identity source that mints join tokens; for a tool, `bind=from_caller(...)` on every parameter that says who the caller is; for an action, which has no `bind=`, `ctx.caller` in `execute` and `validate`, never a draft field ([tools-and-actions.md](tools-and-actions.md), [serving.md](serving.md), invariant 3) |
| What runs is the draft the caller heard read back | Read-back templates that say every field that matters, truthfully: nothing checks that they describe what `execute` does |
| The model check, when you turn it on, never confirms what the lists refused, and a failure never confirms | Whether to turn it on, for its cost: one request and up to 2.5 s of silence for each unplaced answer |
| The talker's text after an action call is never spoken, and the outcome is said from the real result | Your instructions: what the talker collects before it calls the action ([writing-for-voice.md](writing-for-voice.md)) |
| No clause says an ID-shaped number without evidence, and, for an agent with actions, none claims an action without the record or a `reports_on` result | Claim phrases in your domain's words (each action's `claims`, and `T2V_GUARD__CLAIMS`); `reports_on` on your status tools, whose results hold only values read for the caller, never an argument the model chose |
| | A closing question with a send word and no yes word, `send_words` for your own verb, and the yes words your callers use |
| | Fixed lines with no yes word, and no send word except in the closing question and the asked-again line ([writing-for-voice.md](writing-for-voice.md)) |
| | Your tests: `ActionSafetySuite` on each action, in each language (below) |

## What the rules do not catch

- **The guard is lexical.** A claim worded in no list («خلصت الموضوع», "you're all set") passes.
  Add the phrases your simulated calls and traces show (`claims`, `T2V_GUARD__CLAIMS`).
- **A number said with no claim phrase** is not the claim rule's, and a number in a passage then
  passes the ID rule as a fact. When a passage may hold numbers of your records' shape, add the
  words that say a number is the caller's ("your ticket number is") to `T2V_GUARD__CLAIMS`, or
  to the settings in code: Ole5 adds «رقم تذكرتك» and "your ticket number is", so a number said
  so passes only when an action of the call or a status holds it, and its own lines say the
  number in other words.
- **An agent with no action** is not checked by the claim rule at all, so one with read tools
  alone can still say it made a ticket (D-081).
- **A claim phrase can block a true sentence**: a default one such as "has been created" in a
  knowledge answer that says how a thing is made; and a phrase that only introduces a number,
  with no record or status to back it, in a question that asks for one («وش رقم تذكرتك؟», "what
  is your ticket's number?") or in a number the caller said read back to them (TD-134). A phrase
  right after an Arabic negation claims nothing (D-089): «ما سجلت لك», "I did not register it
  for you", passes, but not after a word that makes «ما» a conjunction («بعد ما سجلت لك», "after
  I registered it for you"), nor with «إلا» or «غير» after it ("only"), nor in a question.
- **Over the asked-again line**, a bare yes counts as said after the closing question, so it
  confirms with no send word (TD-133).
- **A caller who stays silent** after the closing question leaves the agent waiting, with no
  ask-again (TD-142); the client's Stop over a read-back ends it with no line (TD-135).
- **The model check's rails are lexical.** The summary is the draft's own words, framed as data
  for the model; a draft written to steer the check could still sway it on words that hold no
  no word, change marker or echo (D-082).
- **A card**, an optional extra the browser client may show, gets the ID rule only, not the
  claim rule (TD-137).

## Testing your actions

`ActionSafetySuite`, in the `evals` facade, runs the adversarial cases on your own action: a yes
over the summary, a yes before any read-back, a bare yes over the closing question, a tool call
whose arguments claim consent, model text that claims the action, text after the action call, a
passage's number in a claim, lost replies with and without a lookup, refusals, a request sent
twice and the per-call cap. For an agent that asks a model, it adds the rails' cases, which pass
at once for one that does not. The example's subclass, from
[test_callback_safety.py](../../tests/minimal_example/test_callback_safety.py):

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
```

The timing rules, played in a `TextCall`: a yes over the summary, then a bare yes over the
closing question, book nothing, and a yes with a send word after it books once, from
[test_callback.py](../../tests/minimal_example/test_callback.py):

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
```

The read-back and claims it plays are the example's, from
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
claims=Claims(
    {
        "en": ["callback is booked", "booked your callback", "asked the branch to call"],
        "ar": SAUDI_CLAIMS,
    }
),
```
<!-- fmt:on -->

In a `TextCall` of an agent that asks, the fake model gets the check's request as one more
request. A `FunctionLLM` tells it apart with `is_consent_check` (the `evals` facade) and answers
one of the five words. A `ScriptedLLM` gives it the script's next entry, and a script with no
entry left makes the check fail, which asks the caller again rather than failing the test;
unless the words hold a no word, which declines, as the rails above say: the turn then goes to
the talker, whose request finds no entry either and fails the test.

## The settings and fields, in short

| Setting or field | Default | What it does |
| --- | --- | --- |
| `VoiceAgent(ask_on_unlisted_answers=...)` | False | A chat model judges the answers the yes rule's lists leave unplaced, within its rails |
| `ReadBack(..., send_words=...)` | none | The action's own send words, by language code, beside the presets' |
| `ReadBack(..., max_attempts=...)` | 2 | How many times an unclear answer is asked again |
| `ReadBack(..., asked_again=...)` and the action's `sending`, `declined` | the library's lines | The fixed lines said while confirming and sending |
| The action's `claims` | required, in every language | The phrases that claim this action |
| `@tool(..., reports_on=[...])` | none | The actions this tool's results may back a claim about |
| `T2V_WORDS__YES`, `T2V_WORDS__SEND` | none | Yes and send words added, for every action |
| `T2V_GUARD__CLAIMS` | none | Phrases added to the default list that claims any action |
| `T2V_GUARD__MIN_ID_DIGITS` | 3 | The fewest digits in a row that count as an ID |
| `T2V_GUARD__ID_PATTERNS` | none | More ID shapes, as a JSON list of regular expressions |
| `T2V_GUARD__ON_BLOCK` | `drop_rest` | What a blocked clause drops: the rest of the reply, or only it (`drop_clause`) |
| `T2V_GUARD__REMOVE_STRAY_SCRIPT` | true | Whether a script none of the agent's languages writes, and each emoji, is taken out of what the talker writes before the guard reads it |
| `T2V_GUARD__QUESTIONS_PER_REPLY` | 1 | The most questions one reply asks the caller: the reply stops before the next, which is not said, nor anything after it ([writing-for-voice.md](writing-for-voice.md), "One question at a time"); None, in code, for no limit |
| `T2V_GUARD__QUESTION_STOP_DROPS_CALLS` | false | Whether a reply the question limit stopped also drops its request's tool calls and actions unrun, so the question ends the turn |
| `T2V_GUARD__DROP_STAGE_NOTES` | false | Whether a stage note or a tag the model writes is a leak of its reasoning, never said |

Every setting is in the generated [settings reference](../generated/settings.md).
