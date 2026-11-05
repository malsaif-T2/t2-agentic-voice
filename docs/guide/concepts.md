# Concepts: turns, interruptions and what the caller heard

How a call moves as the library runs it: the caller's turns and the agent's replies, what
happens when the caller speaks over the agent, how a stop cancels the work behind a reply, and
what the library keeps of what the caller heard. The talker, its tools and confirmed actions join
this page when they land (M4 and M5). Every setting named here is in the generated
[settings reference](../generated/settings.md), and why each works as it does in
[decisions.md](../design/decisions.md) (D-060 to D-067).

**Status.** What this page describes is in the library from M3, still with the echo agent: the
agent says back what it heard. The interruption that listens to the caller's words is behind a
setting, `interruptions.mode`, and off by default ("Choosing the mode", below).

## Turns and replies

- **The caller speaks in turns.** The speech detector (Silero VAD) hears speech start and stop.
  At each pause of `turns.vad_stop_ms` (200 ms), the end-of-turn model (Smart Turn v3.2) judges
  whether the caller has finished: "complete" ends the turn (after a hold, if one is set: "The
  end of a turn", below), "incomplete" lets it go on to the next pause, and
  `turns.smart_turn_stop_ms` (3 s) of silence ends it whatever was judged. Each turn goes to
  Whisper whole, in one request (D-034).
- **The agent speaks in replies.** The greeting is reply 0, and each answer (the echo, for now),
  each reply said again and each spoken notice is the next. A reply is spoken clause by clause:
  a fixed phrase (the greeting, the echo's "I heard:", a notice) from the phrase cache, the rest
  through Orpheus. Each clause's caption reaches the browser as it starts playing.
- Turns and replies are numbered apart (a caption's `turn_id` and `reply_id`), so a turn and the
  reply that answers it never share a number.

## One turn, and a stop over its reply

With `interruptions.mode` set to `two_step`, the caller asks something, hears the start of the
reply, and says "stop" over it:

| Step | What happens | What drives it |
| --- | --- | --- |
| 1 | The caller asks and pauses. 200 ms into the pause the speech detector hears it stop, and Smart Turn says "complete" | `turns` |
| 2 | The turn ends (after `turns.complete_hold_ms`, 0 by default), and its audio goes to Whisper in one request | `stt` |
| 3 | The transcript comes. Text Whisper wrote for silence counts as nothing heard | `stt.no_speech_max`, `stt.caption_filter` |
| 4 | The reply starts: "I heard:" from the phrase cache at once, then the heard words through Orpheus, clause by clause, each captioned as it plays. Its cancel scope opens | the session |
| 5 | The caller says "stop". About 0.34 s into the speech, the speech detector fires: the browser lowers the agent's voice to a quarter | `duck`, `interruptions.duck_level` |
| 6 | 200 ms after the word ends, the whole overlap goes to Whisper (a caller still speaking about 450 ms in has a first window sent before that) | `interruptions.first_window_ms`; at most two requests |
| 7 | The rule reads "stop": the reply is dropped and its scope cancelled, the voice comes back to full, the clause that was playing is captioned again as cut, and observers get `Interrupted` | `unduck`, a caption's `cut` |
| 8 | The history keeps what the caller heard: the clauses played, the one cut with the share of it that played, the rest unplayed. The "stop" turn is a command, never said back | the heard history |

Under `drop` (the default), steps 5 to 8 do not happen: the "stop" turn is not answered, the reply
plays on, and the caller stops it with the Stop button or Esc.

## Speech over a reply: `interruptions.mode`

A turn whose speech began while a reply played, or within 300 ms after its last clause played (the
agent's own voice may still be coming back through the speakers), is taken one of two ways:

- **`drop`, the default:** the turn is not answered. The agent never answers its own voice, and
  the caller stops it only with the Stop button or Esc.
- **`two_step`:** the turn is an overlap, and the agent stops only when the caller's words say
  so: the two-step interruption below.

Turn it on with `T2V_INTERRUPTIONS__MODE=two_step`, or in code, as the library's integration test
builds its settings, in
[test_loopback_interruptions.py](../../tests/t2_agentic_voice/test_loopback_interruptions.py):

```python
def two_step(tmp_path: Path) -> VoiceSettings:
    return VoiceSettings(
        env="dev",
        storage=StorageSettings(var_dir=tmp_path / "var"),
        interruptions=InterruptionSettings(mode="two_step"),
    )
```

`InterruptionSettings`, `WordSettings` and `TurnSettings` come from `t2_agentic_voice`, beside
`VoiceSettings`.

## The two-step interruption

**Step one: the voice lowered.** As soon as the speech detector hears the caller over a reply,
about 0.34 s into the speech, the session sends the browser `duck`, and the reference client
plays the agent at `interruptions.duck_level` (0.25) of its volume. The agent keeps talking,
quieter, while the library finds out what the caller said. Once that is decided, `unduck` brings
the volume back, whatever the verdict ([browser-client.md](browser-client.md)).

**Step two: the overlap transcribed.** Groq's Whisper gives no partial transcripts (D-004), so
the library sends the overlap itself, in at most two requests:

- **the window**, the first `interruptions.first_window_ms` (750 ms) of the overlap, counted from
  300 ms before the speech began, sent once that much is held while the caller still speaks
  (about 450 ms into the speech). A short stop word has often ended by then, and sends none;
- **the whole overlap**, sent the moment the speech detector hears the speech stop (after
  `turns.vad_stop_ms`, 200 ms), never waiting for Smart Turn, which may not hear a lone «وقف»
  ("stop") as a finished turn.

When nothing follows the overlap, the turn's own transcript reuses the whole overlap's, with no
third request; when the caller goes on talking after it, the rest of the turn is sent as any turn
is.

**The rule.** Each transcript is read by the rule, the window's first. A window's verdict counts
only when it stops the agent; otherwise the whole overlap's decides. The steps, in order, the
first that applies deciding:

| Step | The caller's words | The agent |
| --- | --- | --- |
| 1 | Nothing, or text from silence | goes on |
| 2 | A stop or wait word, anywhere ("stop", «وقف», "wait"), or the stop word as Whisper mishears it over the agent's voice | stops |
| 3 | A repeat request, with at most polite words and listening sounds beside it ("can you repeat that") | stops, then says its last reply again |
| 4 | Its own words coming back through the speakers: every word a word, or one letter off a word, of the clauses played in the last `interruptions.own_words_s` (5 s) or playing now | goes on |
| 5 | Only listening sounds ("mm-hmm", «اها», "okay") | goes on |
| 6 | A short output: at most `interruptions.short_words` (2) words in under `interruptions.short_s` (1.6 s), none a listed word, asking no question (often a listening sound Whisper misheard) | goes on |
| 7 | At least `interruptions.min_words` (2) real words | stops: new words, or a correction when the first is a no word |
| | Fewer | goes on |

What follows each verdict:

- **A stop or wait word** stops the reply, and the turn is a command: it is never said back.
- **New words or a correction** stop the reply, and the turn is answered (said back by the echo
  agent; from M4, answered by the talker).
- **A repeat request** stops the reply and says the last reply again ("The repeat", below), once
  the caller has finished speaking.
- **A turn that holds more after the command** ("stop, can you repeat that", "stop, what about my
  ticket") is read past it: a repeat request after a stop word says the last reply again, and
  other words are answered, the echo saying back only what followed the stop.
- **Going on** brings the voice back and leaves the turn unanswered. If the caller keeps talking
  in the same turn, the turn's own transcript is read again, and may still stop the agent.

Each decision reaches the runtime's observers as `Interrupted` (the `events` facade): its `kind`
(`stop`, `correction`, `new_words`, or `false` when the agent went on), its `reason` (the step
that decided: `no_words`, `stop_word`, `repeat_word`, `own_words`, `listening`, `short_output`,
`enough_words` or `too_few_words`), and its `turn_id`, the turn the cut reply answered. The Stop
button and Esc give `kind` `stop` with no `reason`.

### Whole commands said while the agent is silent

Under `two_step`, a turn said while the agent is not speaking is read whole too:

- a repeat request, with at most polite words and listening sounds beside it, says the last reply
  again;
- an utterance of only stop or pause words is not said back: there is nothing to stop, and
  nothing to echo;
- a sentence that holds one of those words ("the printer will not stop beeping") is answered like
  any turn.

If the caller began speaking just before a reply to an earlier turn started, so that no overlap
opened, such a command first stops that reply. Under `drop`, every such turn is said back.

## The words

Each language preset carries five lists the rule reads, by the language's primary code (`ar` for
both Arabic presets, `en`): `stop`; `wait`, words asking the agent to pause, which stop it as a
stop word does; `repeat`; `backchannel`, the listening sounds; and `no`. They are the public
`Words`, and `Language.english(greeting=...).words` shows a preset's. Add your own words in the
declaration (`phrases=`), or in the `words` settings group with no code change; a call's lists are
the preset's, then the declaration's, then the settings', none twice. Both, as the library's
tests build them, in
[test_overlap.py](../../tests/t2_agentic_voice/voice/session/test_overlap.py):

```python
phrases = Phrases.defaults().extend(stop={"en": ["made-up halt"], "ar": ["كلمة مختلقة"]})
english = Language.english(greeting="A made-up greeting")
agent = VoiceAgent(name="words-test", languages=[english], phrases=phrases)
added = WordSettings(stop={"en": ("made-up halt", "made-up cease")}, no={"en": ("nah-ish",)})
```

`added` is the `words` group (`VoiceSettings(words=added, ...)`). From the environment, each kind
is a JSON map from a language's code to its words:

```bash
T2V_WORDS__STOP='{"ar": ["..."], "en": ["..."]}'
T2V_WORDS__BACKCHANNEL='{"en": ["..."]}'
```

- Words are compared in the canonical normalizer's form, so one written with harakat or another
  alef still matches.
- Keep your fixed phrases (the greeting, your notices) free of stop, wait, repeat and listening
  words: the agent's own voice, coming back through the speakers while it says them, would stop
  it or make it repeat. The presets' own phrases are held to this by a test.

## The cancel scope

Each reply runs in a cancel scope of its own: the work that answers the caller's turn starts
inside it, and when the reply ends, however it ends, the scope cancels whatever still runs for
it. So a stop cancels at once everything working for the replies it drops: their speech (every
clause still queued; at most about 40 ms already in the WebRTC track still plays), their
text-to-speech requests, and from M4 the talker's model stream and its read-only lookups. Each
task is cancelled, then awaited at most 100 ms; one that will not end is logged by its name and
left to end on its own. Work started outside a scope is never cancelled by one: from M5 an
action's write runs as a job of its own, so a stop never cuts a write in half.

The echo agent runs no task of its own in a scope; the talker's work starts there in M4. The
library's own test shows what a stop does to a slow model stream, a slow lookup and a write
started elsewhere, in
[test_scope.py](../../tests/t2_agentic_voice/voice/session/test_scope.py):

```python
stream = scope.start(responder.read(), name="model")
lookup = scope.start(responder.lookup("made-up order"), name="lookup")
elsewhere = asyncio.create_task(outside.lookup("made-up write"))
await asyncio.sleep(0)  # each begins, and sleeps on the clock
await clock.advance(1.5)  # one chunk read, the lookup still waiting
assert (scope.running, scope.cancelled) == (2, False)
stopped_at = clock.now()
await scope.cancel()
assert (scope.running, scope.cancelled) == (0, True)
assert stream.cancelled() and lookup.cancelled()
assert responder.cancelled == {"stream": stopped_at, "lookup": stopped_at}
assert max(responder.cancelled.values()) - stopped_at <= CANCEL_WAIT_S
assert _others() == {elsewhere}  # no task of the scope is left
await clock.advance(1.0)
assert await elsewhere == "found for made-up write"  # work outside the scope goes on
```

## What the caller heard

The library keeps a history of what the caller heard, and only that, under either mode:

- **Each reply's clauses,** each `played` (it played to its end), `cut` (it was playing when a stop
  or the call's end came, with the share of its audio that played) or `unplayed`. A clause is
  never split into words: Orpheus gives no word times.
- **Each turn's heard words, and what became of it:** answered; its reply cut, or rolled back
  when the stop came before any clause had played whole; a command (a stop, pause or repeat
  request); an overlap the reply went on through; dropped, under `drop`; or unfinished, when the
  call ended first.

It is what `AgentSpeechEnded.played_fraction` and each turn's `said` in the `CallReport` read, and
what the talker will take its context from in M4, so it never assumes the caller heard a sentence
that was cut. The history itself is the session's: a team reads it through those events and the
call's report.

## The repeat

A repeat request, over a reply or said while the agent is silent, says again the last reply the
caller heard any of, the one just cut included, every clause of it: its fixed phrases from the
phrase cache, the rest through Orpheus, so it costs that reply's text-to-speech requests again.
It is the reply to the request's turn, which is a command and never said back. Before any reply
was heard, it says nothing.

## Text from silence

Whisper writes text for audio that holds no speech: captions it invents for silence or noise
("thank you for watching", «موسيقى», music) or a word made of noise. A transcript counts as no
words, for a turn and for an overlap, when it has no word at all, when Whisper's `no_speech_prob`
for it is above `stt.no_speech_max` (0.5), or when it is, whole, one of those captions
(`stt.caption_filter`, on). A turn so heard is said back as nothing; an overlap so heard lets the
reply go on. Leave `stt.no_speech_max` unset to turn the threshold off, and set
`stt.caption_filter` false to turn the list off. On Ole5's golden set (one speaker) the two
blanked 6 of the 9 clips where nothing was said and none of the 222 with speech (D-063).

## The end of a turn, and the hold after "complete"

Smart Turn can judge a pause inside a request complete, and the agent then answers half of it: on
Ole5's recordings of one speaker, the pauses inside a request (220 to 720 ms) scored as complete
as the true ends, so no threshold of Smart Turn's separates them. `turns.complete_hold_ms` holds a
turn Smart Turn judged finished for that long: if the caller speaks again within it, the turn goes
on, and Smart Turn judges again at the next pause, hearing the whole turn. Every turn's answer
comes that much later, but a stop over the agent does not: the hold acts after the speech
detector's stop, which the overlap's request waits on.

It is 0, no hold, by default. On those recordings a 600 ms hold left 9 of 51 paused requests cut
off instead of 50 or 51 (D-067), and 600 ms becomes the default only once Ole5's held-out set
confirms it. Until then an app sets it:

```bash
T2V_TURNS__COMPLETE_HOLD_MS=600
```

## Choosing the mode

- `interruptions.mode` stays `drop` by default until a registered measurement moves it: Ole5's,
  on its golden set's overlap clips and its call recordings, is under way. Callers whose voices
  and devices differ from those are worth measuring on their own recordings
  ([evaluation.md](evaluation.md)); the `evals` facade's `AudioCall` (provisional) replays a
  recorded clip over a reply through the real turn-taking and reports each overlap's verdict,
  its requests and its stop time.
- On a laptop's speakers the agent's voice can come back through the microphone past the
  browser's echo cancellation. The rule's own-words step lets the reply go on for what it
  recognises; when the echo stays high, push-to-talk keeps the microphone off except while a key
  or a button is held ([browser-client.md](browser-client.md)).
- In either mode, the Stop button and Esc stop the agent at once.

## The settings, in short

| Setting | Default | What it does |
| --- | --- | --- |
| `T2V_INTERRUPTIONS__MODE` | `drop` | `drop`: speech over a reply is not answered; `two_step`: the two-step interruption |
| `T2V_INTERRUPTIONS__DUCK_LEVEL` | 0.25 | How loud the reply plays while the overlap is judged, from 0 to 1 |
| `T2V_INTERRUPTIONS__FIRST_WINDOW_MS` | 750 | The window sent before the caller has finished |
| `T2V_INTERRUPTIONS__MIN_WORDS` | 2 | The fewest real words that stop the agent when none is a listed word |
| `T2V_INTERRUPTIONS__SHORT_WORDS`, `__SHORT_S` | 2, 1.6 | The short output the agent goes on through |
| `T2V_INTERRUPTIONS__OWN_WORDS_S` | 5 | How far back the agent's own words count |
| `T2V_WORDS__STOP`, `__WAIT`, `__REPEAT`, `__BACKCHANNEL`, `__NO` | none | Your words, added to each language's lists |
| `T2V_STT__NO_SPEECH_MAX` | 0.5 | Above this no-speech probability, a transcript is no words |
| `T2V_STT__CAPTION_FILTER` | true | Whisper's invented captions count as no words |
| `T2V_TURNS__VAD_STOP_MS` | 200 | The pause that ends speech, which a turn's end and an overlap's request wait on |
| `T2V_TURNS__COMPLETE_HOLD_MS` | 0 | The hold after Smart Turn's "complete" |
