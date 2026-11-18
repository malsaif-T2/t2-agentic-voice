# Latency: the time to first audio

A caller who stops speaking and hears nothing wonders whether the agent heard them. The number
that says how long they wait is the **time to first audio**: from the end of the caller's
speech to the first sound of the reply. This page says how the library measures it, where the
time goes in a turn, what the library does to shorten it, the budget Ole5's measurement expects,
and how to measure your own.

## What is measured, from where to where

Each turn's times, in milliseconds, each empty when its step did not happen:

| Time | From | To |
| --- | --- | --- |
| `ttfa_ms`, the time to first audio | the end of the caller's speech | the first audible frame of the reply the backend sends |
| `played_ms` | the end of the caller's speech | the reply's playback in the browser, from the client's `playback` report |
| `progress_ms` | the end of the caller's speech | the first audible frame of a progress line, timed apart from the answer |
| `stt_ms` | the speech detector's stop | the turn's transcript: its own request's, or, in a call with a talker, the early start's request it took as its own |
| `end_of_turn_ms` | the end of the caller's speech | the turn's end, as the turn analyzer closed it: the stop delay, Smart Turn's judgement and the hold after it |
| `turn_complete_ms` | the end of the caller's speech | Smart Turn's "complete", where the hold began (in a call with a talker, for a turn said while the agent was silent) |
| `llm_first_token_ms` | the end of the caller's speech | the chat model's first token, the talker's first request |
| `tts_first_audio_ms` | a text-to-speech request, or a clause sent on the call's socket | its first audio |

- **The end of the caller's speech** is, in a live call, the speech detector's stop less its
  stop delay (`turns.vad_stop_ms`, 200 ms), so the time counts from the caller's last sound,
  not from when the detector was sure; in a replay of a recording, its label.
- **The first audible frame**: a voice may send silence before its first word, which the caller
  does not hear as an answer, so a silent first chunk is not counted (TD-090). Where nothing
  taps the output's audio (a test's call, `TextCall`), the first audio queued is timed instead.
- **A progress line is not the answer.** "I'm checking that for you" tells the caller the agent
  is at work, so it is timed apart (`progress_ms`), and `ttfa_ms` waits for the answer itself.

Each turn's times reach a runtime's observers as `TurnMetrics` (the `events` facade), with each
model's usage in the call so far, and the call's `CallReport` (on `CallEnded`) holds them for
every turn; the test console shows them turn by turn, as bars
([browser-client.md](browser-client.md), "The test console"). The report's numbers, with no
text of the call, are also written to a file per call under the data folder's `reports/`.

## Where the time goes in a turn

For a reply with no tool, in order:

1. **The pause that ends speech**: the detector hears the speech stop after `turns.vad_stop_ms`
   (200 ms) of silence, and Smart Turn judges whether the turn is complete.
2. **The hold after "complete"**: `turns.complete_hold_ms` (600 ms), so a pause inside a request
   does not end it ([concepts.md](concepts.md), "The end of a turn"). On Ole5's recordings a
   turn then ended a median of 0.94 s after the caller's own end on the dev split (D-067).
3. **The transcript**: the turn's audio, whole, in one Whisper request.
4. **The first clause**: the chat model's request, to the end of its first clause.
5. **The voice**: the first clause's text-to-speech request, to its first audio.

A reply that searches adds the model's request for the tool, the tool itself (for Ole5's
knowledge base, one embedding and one search) and a second request that answers from the
result, before step 5.

## What the library does about it

- **The early start during the hold.** With a talker, the turn's transcription and the
  talker's first request start as the hold begins, not as it ends: what the talker gives is
  kept, and nothing goes to the voice before the hold has passed. If the caller speaks again within the
  hold, that work is cancelled and the turn goes on, so a resumed turn costs a model request
  (counted in the call's usage), never a reply to half a question. A client's Stop in the hold
  cancels it too. While a reply to an earlier turn is still in progress the turn has no early
  start, so the model reads the call after that reply is stopped.
- **The early start from the detector's stop** (`T2V_TURNS__EARLY_AT_STOP=true`, off by
  default). The turn's speech goes to speech-to-text as the speech detector hears the caller
  stop, Smart Turn's time before its verdict (on the flight agent's calls of 2026-11-17, about
  230 ms at the median), so the transcript is in hand that much sooner on every turn. Its answer
  is kept only when Smart Turn then calls the turn complete; when it calls the pause unfinished,
  or the caller speaks again, its answer is never used, and the next pause sends again with the
  whole turn. The dropped request is left to run out, never cancelled, since a request cancelled
  in flight closes its connection and the next one would pay a new handshake. So each turn's words are answered once, and a pause
  Smart Turn calls unfinished costs one more speech-to-text request. Under
  `stt.live_language = "classified"` the turn's language is decided at the stop, so the
  classifier's verdict has Smart Turn's time less to come. It needs a hold
  (`turns.complete_hold_ms` above 0).
- **The early start over a reply** (`T2V_SESSION__EARLY_OVER_REPLY=true`, off by default). A turn
  held while a reply to an earlier turn is still in progress (nothing of it playing as the turn
  began: a search, say) starts early too: its held words stop that reply first, as its answer
  would, so the model reads the call as it then stands, and its reply waits for the hold's end.
  Speech resumed in the hold drops the early work, the earlier reply staying stopped. While the
  call is confirming an action, such a turn starts nothing early.
- **Speech while the model writes.** Each clause goes to the voice as soon as it is whole, so
  the caller hears the first while the model writes the rest; the library's rules ask the model
  for a short first sentence ([writing-for-voice.md](writing-for-voice.md)).
- **Connections kept open.** Each Groq adapter, the chat model's included, keeps its connections
  open five minutes between requests, so a request seldom pays a new connection's handshake:
  the prototype that came before the library put 1.1 to 1.3 s on its first sound after a search
  by closing idle connections, against 0.23 to 0.25 s with them kept open. By default a call's
  first transcript and first answer each still open their connection. With
  `T2V_WARMUP__AT_JOIN=true` each call, as it joins, sends in the background one request that
  costs nothing to its speech-to-text (a GET of the provider's model list: ElevenLabs' and
  Groq's adapters have one, `warm_up()`), to its text-to-speech (its `check_language`, which
  synthesizes nothing) and, when its connection is not kept warm, to the chat model; a failed
  one is logged and never fails the call. Your own adapter takes part by defining
  `async def warm_up(self) -> None`. A cancelled answer (a barge-in, an early start dropped)
  closes the chat model's connection; with `T2V_WARMUP__AFTER_CANCEL=true` the Groq chat adapter
  opens a fresh one in the background. Each warm request is logged as `call_warmed` (the target,
  the provider, the time, the outcome), each reopen as `chat_reopened` or `chat_reopen_failed`.
  Whatever the settings, each chat request says whether it went out on a connection already
  open, read from the model just before it went (a model that does not say gives none): the
  call report's `TurnRecord.warm_connection` and its turn's `turn.warm_connection` attribute for
  the turn's first request, its `talker_replied` line too, and `model_word_sent` for the
  session's own requests (an uncertain overlap's or a yes's word).
- **The first call after a restart.** By default the first offer imports Pipecat's pipeline and
  aiortc's peer on the server's event loop (2 to 4 s), and each call's offer builds its own
  speech detector and turn analyzer (about 0.1 s each). With `T2V_WARMUP__AT_START=true` the
  server's start imports them in a thread and keeps one call's detectors made ahead, the next
  built in the background as each call takes one: a slower start and a little more memory, for
  a first call that waits for none of it. Its `calls_warmed` log line gives the start's times;
  each call's `call_answered` gives its offer's server steps (the detectors, the peer's answer,
  the pipeline's start) and `call_connected` the time from the offer to the connection, times
  alone, never an address or a candidate.
- **A first line new on every request.** Each request's system message opens with a line of its
  own (such as `Request 7f3a9c21.`), so no two requests share a prefix Groq has cached, for its
  cache can be the slow path. In 24 short requests to `openai/gpt-oss-120b` with Ole5's system
  prompt, alternated: with the same prompt every time, Groq served 8 of 12 from its cache, and 3
  of those 8 took 1.03, 1.25 and 5.71 s to the first token; with a first line of their own, none
  was cached and all 12 took 0.15 to 0.30 s (plan 006's probe of 2026-11-07, D-072).
  A live follow-up turn the same day waited 7.8 s for its first token. Turning the line off
  (`llm.vary_first_line`) lets requests share a cached prefix again, and with it that slow path.
- **A progress line for a long wait.** A reply with a tool that has a progress line, with no
  answer begun `progress_after_s` (2.6 s by default) after the caller stopped speaking, gets the
  line from the phrase cache, with no request, so the caller hears that the agent is at work
  ([concepts.md](concepts.md), "Progress lines"). By default it is kept for the long waits: a
  line of two to three seconds, then a beat of 0.4 s, holds up an answer ready behind it. A
  short line (under a second) can be said as the search starts instead (a small
  `progress_after_s`), with `session.progress_beat_ms` counting the beat from the end of its
  speech, so the caller hears something at the tool call and the answer follows it at once; the
  flight agent does so (plan 010's 1.15).
- **The fallback end of a turn.** A pause Smart Turn judges unfinished ends the turn after
  `turns.max_silence_ms` (3 s by default) of silence. With `turns.read_back_silence_ms` set, a
  turn said while an action's read-back awaits its answer waits that long instead, so a
  shorter fallback for every other turn does not cut "yes, [pause] but change ..." after the
  yes; it needs the hold after "complete" above 0.
- **Smart Turn's own time.** Each judgement is logged as `smart_turn_judged`: the verdict, the
  model's own time (`model_ms`, Pipecat's measure) and where the rest went (the wait for the
  model's thread, the audio joined in it, the event loop taking the verdict back). On an idle
  laptop the model took about 60 ms on one thread and 40 ms on two
  (`turns.smart_turn_threads`); with every core busy, 140 to 180 ms on either, the waits around
  it staying under 3 ms.
- **One socket a call for the voice** (`T2V_TTS__STREAM_REPLIES=true`, off by default; D-121).
  With ElevenLabs' v4 Turbo (the default voice) or another of its v3 and v4 models, the talker's
  replies go on ElevenLabs' Text-to-Dialogue socket, opened as the call starts and kept alive
  under its 20 s idle limit, instead of one HTTPS request a clause. Each clause goes as the
  talker writes it, flushed so its audio is made at once, and each reply is one turn of the
  voice. In the study of 2026-11-17 a line's clauses sent into one turn, flushed once at its
  end, kept the voice's intonation across them («للندن» came out right on the socket and wrong
  in both HTTPS takes); a flush a clause, as here, is for the owner's listen to judge. The
  first audio of a clause came
  at 0.17 / 0.18 s (p50 / p95, 20 clauses, a library voice) against 0.21 / 0.23 s over HTTPS;
  in the owner's voice, a smoke of five clauses each gave 0.16 to 0.19 s against 0.20 to
  0.23 s. Fixed lines, an action's lines and the clause cache's takes keep to one request a
  clause. A stop cuts the clause in flight: v4 has no socket that can drop one clause, so the
  socket is closed and a new one opens at once in the background, ready long before the
  caller's next turn is answered. A reply that moves to the other language opens that
  language's socket at its first clause, one handshake. A socket's failure turns it off for the
  rest of the call, logged once as `tts_stream_fell_back`, and the clause is requested over
  HTTPS in its place when none of its audio had come. Each call holds one of the account's
  dialogue sessions for as long as it lasts, from a pool of their own (14 on ElevenLabs' free
  plan, 105 on Scale). The flight app leaves it off until it is measured and heard.
- **A stop costs no model time.** The interruption rule stops the reply before any model request
  is sent, so the talker adds nothing to the time a stop takes.
- **A clause said before plays from disk** (`tts.cache_clauses`, on by default by the
  owner's ruling after Ole5's run I, plan 007). Every clause a talker call speaks is kept in the clause cache by its
  exact text, language and voice, so the same clause said again, in this call or a later one,
  plays with no Orpheus request: no wait for its first audio (about 0.25 s) and one request of
  the key's minute saved. A miss is a look-up in memory, then the request as before. Most of a
  reply is new words, so few clauses hit: short openers ("I'm sorry,", "Yes,") and a reply said
  again. A held first clause is not an Orpheus request, so it leaves a turn's
  `tts_first_audio_ms` to the next requested clause, or empty. What the cache keeps is in
  [data-and-privacy.md](data-and-privacy.md).

## The budget

Ole5's registered measurement (plan 006, "The measurement, registered before any result") set
its targets before any run, for one speaker on the laptop:

| Reply | Median | 90th percentile |
| --- | --- | --- |
| With no search | at most 1.6 s | at most 2.4 s |
| With a search | at most 3.0 s | at most 4.0 s, and a progress line begun by 3.0 s whenever the answer has not |

What the plan expects, before any measurement: without the early start, a reply with no search
about 1.9 s after the caller's end (the dev split's 0.94 s turn end with the hold, then the transcript, the
first clause and the voice's first audio); with it, about 1.3 to 1.5 s. A search adds the tool's
request, the embedding, the search and a second request, about 0.8 to 1.2 s. The prototype
measured a 1.5 to 1.6 s median for its first sound, its search apart. Its spike measured two of
the parts on the laptop: the chat models' first clause, on a warm connection, at a median of
0.25 to 0.35 s; and one embedding and one search of Ole5's knowledge base at a median of 0.32 s
(0.47 s at the 90th percentile).

What Ole5's run of the time to first audio measured (plan 006's run T on held-out, once, on
2026-11-09: `gpt-oss-120b`, the progress line at 2.6 s, 40 timed replies, each with a search): a
median of 2,532 ms and a 90th percentile of 3,044 ms, both within their targets; but 5 of the 40
had not begun by 3.0 s and had no progress line by then, so that target failed. No held-out
request is answered without a search; on dev's 12 recordings, the replies with no search took a
median of 1.36 s and a 90th percentile of 1.48 s.

## Measuring yours

- **In a live call**, read each turn's times from `TurnMetrics` or the call's report, as above;
  `played_ms` adds what the network and the browser cost.
- **In a test**, a `TextCall` turn gives `first_token_s` and `first_clause_s`, from the moment its
  words were handed to the session, on the call's virtual clock: a fake model's `Pause` stands for
  the model's time ([evaluation.md](evaluation.md), "Testing an agent in text"). With a real
  model and `clock="system"`, they are real times, and every request is paid for.
- **Compare like with like.** One speaker, one machine and one network give one set of numbers
  (D-006); measure a change against the noise, as [evaluation.md](evaluation.md) says, before
  you trust it.
