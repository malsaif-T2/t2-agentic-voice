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
| `stt_ms` | the speech detector's stop | the turn's transcript |
| `llm_first_token_ms` | the end of the caller's speech | the chat model's first token, the talker's first request |
| `tts_first_audio_ms` | a text-to-speech request | its first audio |

- **The end of the caller's speech** is, in a live call, the speech detector's stop less its
  stop delay (`turns.vad_stop_ms`, 200 ms), so the time counts from the caller's last sound,
  not from when the detector was sure; in a replay of a recording, its label.
- **The first audible frame**: a voice may send silence before its first word, which the caller
  does not hear as an answer, so a silent first chunk is not counted (TD-090). Where nothing
  taps the output's audio (a test's call, `TextCall`), the first audio queued is timed instead.
- **A progress line is not the answer.** "I'm checking that for you" tells the caller the agent
  is at work, so it is timed apart (`progress_ms`), and `ttfa_ms` waits for the answer itself.

Each turn's times reach a runtime's observers as `TurnMetrics` (the `events` facade), and the
call's `CallReport` (on `CallEnded`) holds them for every turn. The report's numbers, with no
text of the call, are also written to a file per call under the data folder's `reports/`.

## Where the time goes in a turn

For a reply with no tool, in order:

1. **The pause that ends speech**: the detector hears the speech stop after `turns.vad_stop_ms`
   (200 ms) of silence, and Smart Turn judges whether the turn is complete.
2. **The hold after "complete"**: `turns.complete_hold_ms` (600 ms), so a pause inside a request
   does not end it ([concepts.md](concepts.md), "The end of a turn"). On Ole5's recordings a
   turn then ended a median of about 0.94 s after the caller's own end (D-067).
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
  cancels it too.
- **Speech while the model writes.** Each clause goes to the voice as soon as it is whole, so
  the caller hears the first while the model writes the rest; the library's rules ask the model
  for a short first sentence ([writing-for-voice.md](writing-for-voice.md)).
- **Connections kept open.** Each Groq adapter, the chat model's included, keeps its connections
  open five minutes between requests, so a request seldom pays a new connection's handshake:
  the prototype that came before the library put 1.1 to 1.3 s on its first sound after a search
  by closing idle connections, against 0.23 to 0.25 s with them kept open. A runtime's first
  answer still opens the chat model's connection: it is not warmed at the start.
- **A first line new on every request.** Each request's system message opens with a line of its
  own (such as `Request 7f3a9c21.`), so no two requests share a prefix Groq has cached, for its
  cache can be the slow path. In 24 short requests to `openai/gpt-oss-120b` with Ole5's system
  prompt (3,617 characters), alternated: with the same prompt every time, Groq served 8 of 12
  from its cache, and 3 of those 8 took 1.03, 1.25 and 5.71 s to the first token; with a first
  line of their own, none was cached and all 12 took 0.15 to 0.30 s (medians 0.20 and 0.18 s).
  A live follow-up turn the same day waited 7.8 s for its first token. Turning the line off
  (`llm.vary_first_line`) lets requests share a cached prefix again, and with it that slow path.
- **A progress line for a long wait.** A reply with a tool that has a progress line, with no
  answer begun `progress_after_s` (2.8 s by default) after the caller stopped speaking, gets the
  line from the phrase cache, with no request, so the caller hears that the agent is at work
  ([concepts.md](concepts.md), "Progress lines"). It is kept for the long waits: the line takes
  about two seconds to say and the answer waits behind it, so a line on every search would make
  most answers later.
- **A stop costs no model time.** The interruption rule stops the reply before any model request
  is sent, so the talker adds nothing to the time a stop takes.

## The budget

Ole5's registered measurement (plan 006, "The measurement, registered before any result") set
its targets before any run, for one speaker on the laptop:

| Reply | Median | 90th percentile |
| --- | --- | --- |
| With no search | at most 1.6 s | at most 2.4 s |
| With a search | at most 3.0 s | at most 4.0 s, and a progress line begun by 3.0 s whenever the answer has not |

What the plan expects, before any measurement: without the early start, a reply with no search
about 1.9 s after the caller's end (the 0.93 s turn end with the hold, then the transcript, the
first clause and the voice's first audio); with it, about 1.3 to 1.5 s. A search adds the tool's
request, the embedding, the search and a second request, about 0.8 to 1.2 s. The prototype
measured a 1.5 to 1.6 s median for its first sound, its search apart. Its spike measured two of
the parts on the laptop: the chat models' first clause, on a warm connection, at a median of
0.25 to 0.35 s; and one embedding and one search of Ole5's knowledge base at a median of 0.32 s
(0.47 s at the 90th percentile).

The measured numbers go here once Ole5's run of the time to first audio (plan 006's run T) has
run.

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
