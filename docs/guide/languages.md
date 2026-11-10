# Languages: the call's, each reply's, and the words in between

The library speaks Saudi Arabic, Modern Standard Arabic (MSA) and English. This page says which
language a call is held in, which language each reply is in, how Saudi Arabic and MSA are told
apart, what happens to an English product name inside an Arabic sentence, how numbers are said,
and what the agent's vocabulary is for. How to word what the agent says is
[writing-for-voice.md](writing-for-voice.md).

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
Arabic call is transcribed as Arabic speech. Whether English questions hold up
inside an Arabic call is measured before it is promised (plan 006's run X, on Ole5's golden
set); until then, a caller who will ask in English picks English in the client.

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
