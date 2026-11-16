# Languages: the call's, each reply's, and the words in between

The library speaks Saudi Arabic, Modern Standard Arabic (MSA) and English. This page says which
language a call is held in and each turn is heard in, which language each reply is in, how
Saudi Arabic and MSA are told
apart, what happens to an English product name inside an Arabic sentence, which scripts a reply
may hold, how numbers are said, and what the agent's vocabulary is for. How to word what the
agent says is [writing-for-voice.md](writing-for-voice.md).

## The presets

Each language an agent speaks is built from its preset, which gives its tag, the notices a
caller is told, the echo's frame and the word lists the interruption rule reads
([concepts.md](concepts.md), "The words"):

| Preset | Tag | The register of its notices | Its voice by default (`tts.languages`) |
| --- | --- | --- | --- |
| `Language.saudi_arabic(greeting=...)` | `ar-SA` | Saudi Arabic | `canopylabs/orpheus-arabic-saudi`, voice `abdullah` |
| `Language.arabic(greeting=...)` | `ar` | MSA | the same Saudi model and voice |
| `Language.english(greeting=...)` | `en` | English | `canopylabs/orpheus-v1-english`, voice `troy` |

The echo's frame is «سمعتك تقول:» in both Arabic presets. Both share the primary code `ar`: the
word lists, the pronunciation map and the speech-to-text request are keyed by it. An agent lists
its languages in order, each once, and the first is a call's when nothing picks another.

## The call's language

A call's language is fixed when it joins and kept to its end (D-038): the tag the caller picked
in the client, when the agent speaks it; else the join token's `locale`, its exact tag first,
then the first of the agent's languages with its primary code (`ar-SA` and `ar` both match
`ar`); else the agent's first language. It sets the greeting, the voice the call starts in, the
notices the session tells the caller, and what each turn's transcription is told.

A call tells Whisper its language (`stt.live_language = "session"`, the default, D-066): on
Ole5's golden set, letting Whisper detect it instead got 11 items worse and none better, the
Saudi items, listening sounds and confirmations most. The cost is that an English sentence in an
Arabic call is transcribed as Arabic speech: on Ole5's golden set, its English items were heard
right 0.813 of the time sent as English and 0.027 sent as Arabic (plan 006's run X). A third
value sends each turn in the language a classifier heard (next section); whether it holds up is
measured before it is promised (plan 007's run H). Until then, a caller who will ask in English
picks English in the client.

## The call follows the caller into the other language

`stt.live_language = "detected"` (D-038 as amended, provisional) lets a question or request in
the agent's other language move the call there, both ways, with no new provider: Whisper's own
detection decides. It is off by default (GP-18) until run H keeps it. Each request names the
call's current language as under `session`; a turn with `stt.detect_from_s` (1.2) seconds of
voiced speech or more, counted from where the speech detector heard it begin to where it last
heard it stop (never the silence after it, which the classifier's gate counted), is also sent
naming no language and with no prompt, at the same time, so the turn waits for no extra round
trip. The call moves when that second request hears the other of the agent's languages (Groq's
name of it mapped exactly, so "Armenian" is never Arabic) and the turn is a question or request:
two words or more, and not only short replies ("yes", "okay", "thanks", «ايه», «تمام», «طيب»,
in either script). Then the turn's heard words are that request's, its reply, voice and search
follow them, and every later request names the new language, so the next short "yes" is heard in
it. Otherwise the transcript in the current language stands and nothing moves. A shorter turn
never detects. The rule is `domain/language_switch.py`'s; each long turn costs a second Whisper
request. A provider that reports no language it heard (`speechmatics`, `cohere`, whose model is
always sent Arabic when no language is named) gets no second request, so on it only a switch
request or the talker's tool below moves the call.

A caller may also ask in words: a turn made only of a switch request ("English please",
«بالعربي لو سمحت», in either script, with how Whisper writes it told the other language) moves
the call too, and its reply is in the language asked for; said over a reply under `two_step`, it
moves the call whether the reply stops or goes on. Once the call has moved, the session's
notices, its fixed phrases, the echo and the interruption rule's words are the new language's
(`CallSetup.now`, `voice/session/call_language.py`), and the call report names a detected turn's
language with `language_by = "detected"`. Under `session` and `auto` the call never moves.

The list is a fast path only. For any other wording ("can we do this in English?", «ممكن نتكلم
بلغة ثانية») the talker is given the library's `switch_language` tool
(`actions/language_tool.py`), under `detected` and for an agent of two languages or more, unless
the agent declares a tool of that name. The model calls it with the code asked for (`en`, `ar`);
the rest of that reply is then in the new language (its prompt, its clauses' voice, its tools'
context), the call moves, and the speech-to-text bridge is told after the step. A language the
agent does not speak is refused to the model as a tool error, and the call stays where it is.

An action's read-back is never confirmed across a move. When the call moves while a read-back
waits for its answer, the turn that moved it is no answer: the read-back is read again in the
new language, from the same draft, and only a yes after that new read-back played in full
confirms it, with its own receipt (invariant 1; `voice/session/read_back_moved.py`). An action
with no lines in the new language is declined instead, and the talker answers the turn.

## Each turn's language from a classifier

`stt.live_language = "classified"` (D-086, provisional) sends each turn to Whisper in the
language a spoken-language classifier heard in it, chosen among the agent's languages, so an
English question in an Arabic call can be written as English. It is off by default: the default
stays `session` until a registered measurement keeps it (GP-18; plan 007's run H, on Ole5's
golden set, which has not run yet), and nothing here is promised before then. Turn it on only
when your callers change language within a call, and measure it on your own callers'
recordings first ([evaluation.md](evaluation.md)). An agent of one language runs no classifier.

**The rule.** Once a turn holds `stt.classifier_from_s` (2.0) seconds of audio from where the
speech detector heard its speech begin (pauses inside the turn count), those seconds go to the
classifier, once a turn, while the caller goes on speaking. The turn's language is decided when
its 600 ms hold begins ([concepts.md](concepts.md), "The end of a turn"), or at its end when
there is no hold, and the request never waits:

1. **short**: the turn's speech had not reached 2.0 s;
2. **late**: the classifier has not answered yet;
3. **busy**: the classifier was hearing another turn (one at a time in a process);
4. **failed**: it raised, or its answer did not parse;
5. **unsure**: its best share is under `stt.classifier_min_share` (0.7);
6. else **classified**: the language of its best share.

Every case but the last keeps the current language, which only a classified turn moves: the
call's own at first, then the language last classified. So after an English question, the short
"yes" to its English read-back goes to Whisper as English. A turn that overlaps the agent's
speech keeps the current language. The heard words, the reply's language and the read-back's
yes words follow the language the turn was sent in, as they follow the call's under `session`.
When a yes is heard in another language than the read-back's, the model's check of it reads the
no words and the change markers of every language the agent speaks ([safety.md](safety.md),
"The model check: words the lists cannot place"), so
"yes, but change the date" over an Arabic read-back is a change, never a yes.

**The two classifiers** (the `classifiers` facade; any other is passed in code,
`Providers.from_settings(settings).replace(classifier=...)`):

| `stt.classifier` | Model | Runs on | Install |
| --- | --- | --- | --- |
| `silero` (the default) | Silero's 95-language classifier | ONNX Runtime, already in the base install | nothing more |
| `ecapa` | ECAPA on VoxLingua107, through SpeechBrain | torch, on the CPU | the library's `ecapa` extra |

Both run in the call's process, on the CPU, on `stt.classifier_threads` (2) threads: no audio is
sent anywhere for them, and they keep none. On the developer's laptop, on 2.0 s clips at 2
threads (the download step's smoke, 2026-11-11), Silero took about 7 ms and ECAPA about 250 ms,
ECAPA's CPU time two to three times its wall time. ECAPA's load takes seconds at the runtime's start (5 to 20 s on the
developer's laptop, cold).

**The model files** are never downloaded at run time. Fetch them once by hand into a folder of
your own, outside every repository and `var/`, one folder a model (on Windows, for example
`%LOCALAPPDATA%\t2-agentic-voice\models\speechbrain__lang-id-voxlingua107-ecapa\`), and set
`T2V_STT__CLASSIFIER_DIR` to the folder of the classifier you run. Each file comes from
`https://huggingface.co/<repository>/resolve/<commit>/<file>`. The runtime checks every file's
size and SHA-256 at its start and refuses to start, with a FIX, when one is missing or changed;
`t2v doctor` checks them too.

- ECAPA, `speechbrain/lang-id-voxlingua107-ecapa` at commit
  `0253049ae131d6a4be1c4f0d8b0ff483a0f8c8e9` (Apache-2.0). Keep no `.py` file in its folder:
  SpeechBrain puts the folder on `sys.path`, and the runtime refuses one that holds a `.py` file.

  | File | Bytes | SHA-256 |
  | --- | --- | --- |
  | `embedding_model.ckpt` | 84,474,355 | `ab750d5c06d713477045fa798fab5d33e959dbc0dfe4de510a9a47844c79a19a` |
  | `classifier.ckpt` | 762,555 | `a50d9024ff58d317031c9787d4c6c614d454a87a8ef32f9d36338cd3ff57adbc` |
  | `normalizer.ckpt` | 1,063 | `c369e01dfa2e0d84c6b116f33c7b94f1fe28c061642086538e93cde3d97c26ef` |
  | `hyperparams.yaml` | 1,519 | `88fec9791a8416a152fb10834327e18d38e5bf7a351e9b714e08cdc4af05de6f` |
  | `label_encoder.txt` | 2,204 | `9f566d83c4f19168be4a0bf86c0c7dac7d3264a95105bcbf33a7c32b83ccc17f` |
  | `config.json` | 51 | `a861f8fbc2e23c0fc0823b3c0fd2b3d1e839563c2d4e3f9663a1237cce62bc89` |

- Silero, `deepghs/silero-lang95-onnx` at commit `bf21c4f59503dc182ab4d69328889b93c51bf70f`
  (MIT, Silero Team): a third party's copy of the file silero-vad v4.0 loads, whether it equals
  Silero's own not yet checked (TD-147).

  | File | Bytes | SHA-256 |
  | --- | --- | --- |
  | `lang_classifier_95.onnx` | 16,972,591 | `12a91f706ad6ca5a5eba4e84a96739d077e56f121ec71db86a752f62e218a227` |
  | `lang_dict_95.json` | 2,183 | `70b62ef4939d712b960a8ed8aaea9e0d7117b10877e917a97cc4e8bbb7bd340f` |

**The `ecapa` extra.** Add the library with it, `uv add "t2-agentic-voice[ecapa] @ git+..."`
(the install line of [quickstart.md](quickstart.md) with `[ecapa]` after the name); in this
repository, `uv sync --group language-id`. It brings SpeechBrain, torch and torchaudio (CPU
builds) and about 18 packages they need, well over a gigabyte installed. On Linux, PyPI's torch
wheel brings CUDA packages, so take torch and torchaudio from PyTorch's CPU index with these
lines in your own `pyproject.toml` (uv reads an index only inside the workspace that names it);
`t2v doctor` reports a CUDA or `triton` package it finds beside torch:

```toml
[tool.uv.sources]
torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]
torchaudio = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

Without the extra, `stt.classifier = "ecapa"` is refused at the runtime's start, its FIX naming
the extra. An exact `uv sync` without it removes it again.

**What a team sees.** Each turn's speech-to-text span names the language the turn was sent in
and how it was chosen (`stt.language_by`), and a classified turn's share
([tracing-and-logs.md](tracing-and-logs.md)); the call report's `TurnRecord.language` is the
tag of that language and `TurnRecord.language_by` how it was chosen (`session` under `session`).
What is left, said plainly: a turn under 2.0 s keeps the current language, so a short «لا» over
an English read-back, after an English turn moved the language, goes to Whisper as English; a
long Arabic turn the classifier wrongly gives English 0.7 is sent as English; and with several
calls in one process, a turn that finds the classifier busy keeps the current language
(TD-145).

## Each reply's language

With a talker, each reply follows the language of the caller's turn, not only the call's, so one
call may hold Saudi, MSA and English turns, each answered in its own. The rule, in order:

1. **Heard.** The language the turn's transcript names, which is most often the call's, since
   the call told Whisper its language.
2. **Written.** The script of the turn's words overrules it only when it plainly says
   otherwise: at least 3 words in the other script, and more than twice as many as in the heard
   language's. So an English question Whisper writes in Latin letters in an Arabic call is
   answered in English, while a Saudi sentence holding "VPN" and "Outlook" stays Arabic.
3. **The tag.** The reply is in the call's own tag when its language is the same (an `ar-SA`
   call's Arabic reply is `ar-SA`), else in the first of the agent's tags in that language, else
   in the call's: an agent that speaks no English answers an English turn in its own language.

The system prompt's language section, and the instructions of that tag when you give one a
language, follow the reply's tag; each clause is spoken in that tag's voice. A request that
follows a tool's result ends with a short line naming the reply's language, whatever language
the result is in, so an English question answered from Arabic passages is answered in English.
The output guard, the speaking rules and the pronunciation map read the clause in its own
language.

## Saudi Arabic and MSA

Saudi Arabic and MSA share a code, so a transcript cannot tell them apart, and the tag does not
decide the register: the caller's words do. The talker reads each Arabic turn against a small
list of Saudi and Gulf dialect forms (such as «أبي»، «أبغى»، «وش»، «وين»، «اللي»، «الحين»،
«بس»، «مو», and «ما» before a verb, which is Saudi's "not"; the library's `agent/language.py`
holds the list), over the caller's heard turns of the call so far, the one answered now among
them: the caller is Saudi once any of them held a form, MSA while none of the turns with Arabic
in them has, and Saudi by default while no turn held an Arabic word. So a short plain turn after
a Saudi one («تمام»، «كمل»، «ممكن تعيد؟») stays Saudi, while a call that opens with a plain
question («كيف أطبع الملف؟») is answered in MSA until the caller says a dialect form. An `ar-SA`
reply to an MSA caller gets a language section, and a line after a tool's result, that ask for
Modern Standard Arabic with no dialect word; any other `ar-SA` reply's section asks for the
Saudi dialect unless the caller speaks MSA, as an `ar` reply's does whatever the words. A turn
the drop rule judged the agent's own voice is not the caller's, and says nothing of their
register. The presets' own texts (the
notices, the echo's frame) are in the register of their tag: Saudi for `ar-SA`, MSA for `ar`.
Write your greetings and progress lines in the register of their tag too; Ole5's instructions
ask for the Saudi spoken register, and MSA for a caller who speaks it. An action's lines follow
the caller: an `ar-SA` reply to an MSA caller says each line's `ar` text where the action gives
one, and the library's own action lines in MSA, still in the `ar-SA` voice
([tools-and-actions.md](tools-and-actions.md)).

## Product terms inside Arabic

Callers say product names in English inside Arabic sentences ("أبي أسوي reset للـ password حق
Outlook"). The language section asks the model to keep product names as the caller says them,
and the reply's language rule keeps such a sentence Arabic (above). How the voice says a term is
the agent's pronunciation map: `pronounce=` gives each written form, as a text holds it, the way
each language says it, keyed by the primary code. A form is found as written, its case
included, so give each way your texts write it: Ole5's map holds `Ole5`, `OLE5` and `ole5`, said
«أو لي فايف» in Arabic and "Oh-lee five" in English. The map is applied to each clause in its language after the guard
and the speaking rules, and the caption keeps the written form.

## Scripts a reply may hold

A model sometimes writes a word of another language's script into a reply: in the owner's demo
call, `gpt-oss-120b` wrote «إ重新» (two Chinese characters) where it meant «إعادة». So
everything the talker writes, its text and the string values of its tool calls' arguments,
passes a filter before anything reads it (D-084). The caller hears, and the captions, the
history, the trace and the events hold, the text without the stray characters.

**Each preset's scripts.** `ar-SA` and `ar` write Arabic and Latin, so an Arabic agent keeps its
product names, codes, email addresses and links; `en` writes Latin. An agent keeps the scripts of
all its languages, whatever the reply's: Ole5, which speaks Saudi Arabic and English, keeps both
in every reply.

**What is kept:**

- every letter and mark of those scripts' blocks (Latin: Basic Latin to the combining marks,
  Latin Extended Additional, -C and -D, and the Latin ligatures; Arabic: the Arabic block, its
  Supplement, Extended-A and -B, and the Presentation Forms);
- General Punctuation (dashes, curly quotes, a zero-width space), and the Arabic-Indic (٠–٩) and
  Persian (۰–۹) digits;
- every other punctuation, symbol, space or format character: «», %, a currency or math sign,
  © ® ™, and the arrows the speaking rules say as "then" ("Inbox → Archive");
- a number sign that is no digit, such as ⅓ or ①;
- every character of a term the agent declares (below).

**What is rewritten, one character for one:** a fullwidth form as its plain form (`，１２３`
becomes `,123`); the ideographic space, comma and full stop as a space, a comma and a full stop
(`Restart it。Then` becomes `Restart it.Then`), so no two words are joined; and a digit of any
other script as its ASCII digit (a Devanagari five becomes `5`), so the output guard reads the
number.

**What is taken out:** every other letter or mark (Greek, Cyrillic, Hebrew, Devanagari, a
variation selector), every Chinese, Japanese and Korean character, a private-use character,
and every emoji and other pictograph (⭐, ▶, 😀). Each character is judged alone, so a word
loses only its stray characters: «إ重新» leaves «إ», and the library never guesses what was
meant. Once the filter has changed a reply's text, a clause left with no letter or digit is not
said; a reply left with nothing to say gets the `error` notice.

**What is never changed:** the caller's heard words, a tool's result, a card, and your own
lines (greetings, progress lines, notices, an action's read-back and outcome lines). They are
your text or the caller's, so write them as you mean them. The prompt and the tools' schemas
sent to the model are unchanged too.

**Keeping a term of another script.** A term your callers need in a third script ("μs", a
supplier's Chinese name) is taken out unless the agent declares it. Every character of a
declared term is kept: the written forms of `pronounce=`, the terms of `vocabulary=`, and the
`words.vocabulary` setting's (`T2V_WORDS__VOCABULARY`), which needs no code change. A declared
character is kept wherever it appears, not only inside that term.

**Seeing what went.** Each model request whose answer lost a character logs
`talker_stray_script_removed` with the count and the kinds alone, never a character, and the
turn's trace's root span holds `turn.stray_characters` and `turn.stray_scripts`
([tracing-and-logs.md](tracing-and-logs.md)).
In a test, a `TextCall` turn's `stray_characters` counts them. The `languages` facade's
`remove_stray_script(text, languages=["ar-SA", "en"], kept=terms)` shows what a text keeps:
it gives a `Kept`, with the text, how many characters changed and their labels ("CJK",
"PICTOGRAPH"), so your own measurement can read a reply as the talker says it.

**Turning it off.** `T2V_GUARD__REMOVE_STRAY_SCRIPT=false` keeps what the talker writes as
written. It is on by default: on every clause and search of Ole5's stored dev runs of the
talker, and on its knowledge snapshot, it changed nothing (D-084).

## Numbers and IDs

The talker writes numbers in digits, and the speaking rules say them in the reply's language
after the output guard has read them ([concepts.md](concepts.md), "The output guard's ID
rule"): a number as a number («واحد وعشرون», "twenty-one"), a decimal as its whole part,
"point" («فاصلة») and its digits, and an ID digit by digit. A run of digits is an ID when it has
five digits or more, starts with a zero, or follows a word that names a number's last digits;
any other run is a number. Arabic-Indic digits are read as well as ASCII ones, and an Arabic
prefix written onto a number stays on its first word («و٢١» is said «وواحد وعشرون»). The
`languages` facade's `speak_number` and `speak_id` say one alone; num2words gives the Arabic
forms, in MSA, and a native speaker's check of them is still to come (TD-058).

**Said in the caller's register.** `T2V_TTS__SPOKEN_NUMBERS=by_register` says a reply's numbers
in the register of the caller's Arabic (the talker gives each Arabic clause the call's register):
«ألفين وأربع مية وخمسين» for 2450 to a Saudi caller, «ألفان وأربعمئة وخمسون» to an MSA one; a
time written "09:10" as a clock says it, with its part of the day («تسع وعشر دقايق الصبح»,
"nine ten in the morning", the part said once when the reply already says it after the time);
and an ISO date "2026-12-17" with its weekday and month, never its year. IDs are still read
digit by digit, and captions keep the digits. The default, `as_written`, says them as above;
the setting is a change to what callers hear, so it moves only on a measured run (GP-18).

**Key combinations and spelled terms.** `T2V_TTS__SPOKEN_KEY_COMBINATIONS=true` says a key combination in a
reply as its keys, its plus signs left out: "Ctrl + Shift + R" is said "Control Shift R", and in
Arabic «كنترول شفت آر» (a Latin letter by its English name, as Saudi callers say it). It is off
by default, for the same reason. For a term your callers hear spelled, the `languages` facade's
`spell_letters("OTP", language="ar-SA")` gives «أو تي بي» ("O T P" in English), which your
pronunciation map can hold: `pronounce={"OTP": {"ar": spell_letters("OTP", language="ar"),
"en": "O T P"}}`.

**Numbers, times, dates and amounts in your own lines.** A line your code renders (a booking's
read-back, its `done`) is not the talker's, so you say its numbers yourself, in the reply's
register: the `languages` facade's `speak_time(time(9, 10), language="ar-SA")` gives «تسع وعشر
دقايق الصبح», `speak_date`, `speak_duration` and `speak_amount` (riyals) the same way, and
`speak_number(2450, language="ar-SA", register="saudi")` «ألفين وأربع مية وخمسين». Each takes
`register="saudi"` or `"msa"` for an Arabic reply: pass the call's (an `ar-SA` reply to an MSA
caller is said in MSA, as its words are); with none, `ar-SA` is Saudi and `ar` MSA, but
`speak_number` with no register keeps num2words' MSA. English is one form ("nine ten in the
morning", "Thursday the seventeenth of December", "two thousand four hundred fifty riyals").
The Arabic words come from the library's own tables (0 to 999 999); the Saudi ones are the
agent's until a native speaker checks them (TD-058).

## The vocabulary

An agent declares the product terms its callers say, as a transcript should write them:
`vocabulary=Vocabulary(terms=["Outlook", "VPN"])` (at most 200 terms, each one line of at most
64 characters), and the `words.vocabulary` setting adds terms after them with no code change.
They become the Whisper prompt, which can make Whisper write "Outlook" where it heard «أوتلوك».

Every speech-to-text request of a call, a turn's and an overlap's, sends the prompt of the
language it names: your terms, then that language's command words as a transcript should write
them («وقف», «ممكن تعيد», "stop", "can you repeat that"), each once, held to 224 bytes (the first
word that does not fit and every one after it are left out). The `languages` facade's
`whisper_prompt(terms, "ar")` shows a prompt. An agent that declares no vocabulary, the echo's
among them, sends the command words alone.

Whisper can write a prompt's words into silence, and a prompt can change how it writes the
command words the interruption rule reads, so the prompt was measured before calls sent it
(GP-18; plan 006's run W, on Ole5's golden set with Ole5's vocabulary): on dev the stop words
heard right rose from 0.69 to 0.92 and the repeat requests from 0.32 to 0.53, and on held-out
the share heard right rose from 0.382 to 0.420 and the word errors fell from 0.254 to 0.218.
Measure your own vocabulary on your callers' recordings ([evaluation.md](evaluation.md)).
`stt.send_prompt = false` sends no prompt, and a call under `stt.live_language = "auto"` names
no language, so it sends none either.
