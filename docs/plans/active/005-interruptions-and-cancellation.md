# 005 · Interruptions and cancellation

Status: active · Milestone: M3 · Started: 2026-11-03

*Approved by the owner on 2026-11-03 in the answers to Q1 to Q7 ("The owner's decisions"); not
started: the owner gives the start once M2 is finished, and nothing is built before then.*

## Goal

Make the agent stop when the caller tells it to, and only then ([roadmap](../roadmap.md), M3).
While the agent speaks, the caller's speech lowers its voice at once (`duck`), and the overlap
is transcribed, since Groq's Whisper gives no partial transcripts (D-004): a first window of a
registered length, then the whole overlap when the speech stops. The agent stops on a stop word
or two real words, and goes on (`unduck`) for a listening sound, its own voice coming back
through the speakers, or no words. Every reply runs in one cancel scope, so a stop cancels at
once everything working for it: in M3 its speech and the echo's requests, from M4 the model and
the read-only lookups. The session keeps a history of only what the caller heard, clause by
clause, which a repeat request uses and M4's talker reads. It is library behaviour, still in
echo mode, with Ole5's word additions as settings. The plan registers its targets before any
result and checks them on the golden set's overlap clips and on M2's call recordings; the
rehearsal's stop and repeat steps then pass in a live call. It also settles, from M2, the
language a live call sends Whisper and the speech-to-text noise on another day, and it tunes when
a turn ends (the owner, Q6). Every number describes one speaker, the owner (D-006).

## Acceptance criteria

**The library**

- [ ] **The cancel scope** (`voice/session/scope.py`): each reply opens one scope, and the work
  that answers a turn starts inside it. A stop cancels the scope at once: `StopSpeaking`, every
  task of the scope cancelled and awaited, one `Interrupted` event, and the widget told (`state`
  and the cut caption). A test with a fake responder holding a slow model stream and a slow
  lookup: after a stop both are cancelled within 100 ms on the fake clock and no task of the call
  is left; work started outside the scope (M5's writes, the design's 6.4) is not cancelled.
- [ ] **The two-step interruption**, behind `interruptions.mode`: a turn that opens while a
  reply plays, or within 300 ms after its last clause played (D-037), is an overlap. The session
  sends `duck` at once. The speech-to-text bridge sends a window, the first `first_window_ms`
  (750) of the overlap counted from 300 ms before the speech detector's onset, if the speech is
  still going then; and the whole overlap when the detector hears the speech stop, never waiting
  for Smart Turn. At most two Whisper requests decide one overlap (a test), and an overlap the
  session answers reuses the second transcript when no speech followed it. The rule ("The
  starting rule" below) stops on a stop or wait word or on `min_words` (2) real words, and goes
  on (`unduck`, the turn not answered) for listening sounds, the agent's own words, no words or
  text from silence. A stop or wait word is never said back; new words are answered; a repeat
  request stops the reply and says the last reply again.
- [ ] **The words:** each `Language` preset (`ar-SA`, `ar`, `en`) carries stop, wait, repeat,
  listening and no words (the design's 3.1), as the owner rules (Q1); a team adds its own through
  the declaration (`phrases=`, the design's 4.3) or the `words` settings group, and Ole5 sets its
  additions as settings. A test: no preset's fixed phrase (greeting, echo frame, notices) holds a
  word of its stop, wait, repeat or listening list, since the agent's echo would stop it.
- [ ] **The filter for text from silence:** a transcript whose `no_speech_prob` is above
  `stt.no_speech_max`, or that is one of Whisper's invented captions (`stt.caption_filter`),
  counts as no words, for an overlap and for a turn, with the defaults the registered rule F
  sets. A clause with no letter or digit is never sent to text-to-speech (TD-060).
- [ ] **The heard history** (`voice/session/history.py`): each turn's heard words and what became
  of it, and each reply's clauses as `played` (its `ClausePlayed` came), `cut` (playing at the
  stop, with the fraction played) or `unplayed`. The repeat, the `CallReport` and
  `AgentSpeechEnded(played_fraction)` read it.
- [ ] **`t2v/1`** gains `duck` (with its level) and `unduck` (the design's 5.5) and a caption's
  `cut` mark (Proposed); the protocol's fixture changes in the same commit (D-039).
- [ ] **Settings:** the `interruptions` group (`mode`: `drop`, M2's rule and the default until
  the registered runs move it, or `two_step`; `duck_level`; `first_window_ms`; `min_words`), the
  `words` group, `stt.no_speech_max` and `stt.caption_filter`; the generated reference
  regenerated. With `mode = "drop"`, M2's session scenes give the same commands (GP-18).
- [ ] **The replay** the measurement needs (`testing/audio_call.py`, the design's 9.5
  `AudioCall`, provisional): it plays a golden WAV file over a reply on the file-fed transport
  and records each overlap's verdict, its Whisper requests and the time from a labelled word end
  to the last agent audio frame sent; the app reaches it through the `evals` facade, as it
  reaches `turn_ends` (D-019's Proposed bullet).
- [ ] **Debt M3's stops would turn into failures, paid:** TD-060; TD-064's stop part (a clause's
  context never opened, dropped at a stop); TD-068's rule on `Commands.run` and the lock in
  `FakeSession`; TD-055 (a request's report still counted after a stop).

**The browser**

- [ ] `t2v-client.js` lowers the agent's playback to the `duck` level as the message arrives,
  restores it on `unduck`, and shows a cut caption as cut; Ole5's widget has a push-to-talk switch
  (the microphone on only while a key or the button is held), the fallback when the echo on the
  laptop's speakers stays high. Checked in the agent's browser pane with a silent stream, and by
  the owner in the live calls.

**The measurement** (the roadmap's *Done when* for M3)

- [ ] "The measurement, registered before any result" was complete, every owner's call settled
  and dated, before the run it affects; every departure is a `Deviation:` line in the progress
  log.
- [ ] The language a live call sends Whisper is set by the registered rule (runs R5 to R7), and
  the noise on another day (TD-032) is recorded.
- [ ] The turn defaults are tuned by the registered rule E, offline with `uv run poe eot`, on the
  paused requests with Q2's new ones: a default moves only where E's keep rule holds on dev and
  held-out confirms it.
- [ ] `uv run poe overlap` measures the overlap clips through the replay; its `reference`
  answerer scores every verdict right and 0 ms inside `poe check`.
- [ ] The targets hold on dev (O1, with O2 its noise), on held-out once (H3, aggregates only) and
  on M2's call recordings imported as golden items (C3).
- [ ] In live calls in Chrome, on the laptop's speakers and on the wired headset: the
  rehearsal's stop and repeat steps (DESCRIPTION.md, steps 1 and 2) pass; on the speakers, with
  the owner silent through five replies, the agent is never interrupted; Whisper's requests stay
  at or under 10 a call minute.
- [ ] `uv run poe check` passes; the guide's `concepts.md` and `browser-client.md`'s M3 part are
  written; the decision entries, the roadmap's M3 row, CLAUDE.md, ARCHITECTURE.md and this plan's
  logs are up to date.

## Plan

**Scope.** The roadmap's M3 and the design's 16.1 M3 row, in echo mode, held to what a call and
M4 need. **Left out, for the owner's yes with this plan:** the parity test between text and audio
calls, which needs `TextCall` and so moves to M4 with it; the Bluetooth hands-free warning, since
M1 found no Bluetooth gap (plan 002's Future improvements) and the live calls show whether one is
needed; the guide's `audio-troubleshooting.md`, written with the Bluetooth warning. **Out:** the
talker (M4), so the scope's model and lookup parts are tested with fakes; the pacing of
text-to-speech across turns (TD-066, M6); Smart Turn fine-tuned on the owner's turns (the
roadmap's "Planned later"): E tunes its settings only.

**From M1 and M2.** Plan 002's Future improvements give M3 the filter (F), the rule's handling of
short Saudi words (Q4), the first window (750 ms from run W3) and the noise on another day
(TD-032). Plan 003's "Left for M3" is this plan's library list; its debt rows that name M3,
TD-060 and TD-068, are paid, and TD-070 is checked when run C's recordings are imported (step
11).

**Moved from M2** when the owner cut M2 to its fundamentals (2026-11-03, "The owner's
decisions"): runs R5 to R7, the language a live call sends Whisper, with its open choice (plan
003's Q15, Q5 here) and TD-011's reading; and the noise on another day (TD-032). They keep
[plan 003](003-call-listens-and-speaks.md)'s registration, restated below as L, and run first
(step 13). The timing runs T1 and T2 left M2 without coming to M3, and the prompt arm for
product terms (plan 003's Q16) went to M4.

**Order with plan 003.** M3 starts when the owner gives the start, once M2 is finished. Its
Block 0 is cut from the main branch, which then holds `plan-003-integration` (merged after plan
003's step 16); M3 builds on `plan-005-integration` and merges into the main branch only after
plan 003's recorded session (its step 18, run C), whose calls run from the main checkout on M2's
echo.

Each block is built in its own worktree under `.claude/worktrees/`, with commits named
`Plan 005: <what>`. Under the owner's rule of 2026-11-03 ("The owner's decisions"), each block or
track has one reviewer, an agent that did not write it, each finding checked by one skeptic, and a
review reports only what would break, hang or crash a call; garble, cut, overlap or lose its
audio; leak a task, connection or memory per call; send Groq more than the limits allow or fail
on a 429 it could wait out; refuse valid Arabic or English text; or leave a later track or
milestone a contract it cannot build on. Everything else becomes a row in
`docs/plans/tech-debt.md`, with no second fix round unless a high finding stands.

**Before Block 0**

1. M2 is finished and the owner has given the start. Before Block 0 takes a decision or debt
   number, the agent lists `docs/plans/active/`, `docs/plans/completed/` and
   [decisions.md](../../design/decisions.md), and asks the other sessions
   ([WORKING-RULES.md](../../../WORKING-RULES.md)).
2. `plan-005-integration` is cut from the main branch, and this plan, merged with it, cites the
   agent-led mode by its decision number.

**Block 0 · interfaces, settings, splits** (one agent)

3. **Interfaces, with stubs that raise** (a test per stub, in the file of the track that owns
   it): in the session's I/O, a command that marks a turn an overlap (with the window's length),
   `Transcribing` and `Transcribed` naming their part (`window`, `overlap` or `turn`), `duck` and
   `unduck` as urgent `Send` messages, and `Commands.run`'s contract on what it may not wait on
   (TD-068); `domain/words.py`, `domain/interruptions.py` (an overlap's text, `no_speech_prob`,
   length, the clauses that played and the language's words in, a verdict out) and
   `domain/silence.py`; `voice/session/scope.py`, `history.py` and `overlap.py`; the protocol's
   new messages; the settings groups, with the generated reference, and the `turns` key E's arms
   need, `smart_turn_threshold` (0.5, a turn's end unchanged at the default: Pipecat 1.15.0's
   `LocalSmartTurnAnalyzerV3` fixes it at 0.5, line 174, so it needs a subclass reading the
   probability the base class hands on, `base_smart_turn.py` line 258, which Block 0 confirms);
   `testing/audio_call.py`; the fakes, with a slow responder and a lock in `FakeSession`.
4. **Splits before the tracks grow the files** (`[gc] size_watch` 300): `domain/declaration.py`
   (374 lines) keeps only the `phrases=` field, the lists living in `domain/words.py`;
   `voice/session/call.py` (372) hands overlaps to `overlap.py`; `voice/session/playback.py`
   (340) moves `Speaker` to `speaker.py`; `voice/tts_bridge.py` (303) moves `_OutputChunks` and
   `_Clause` to `tts_output.py`. Code moves only, the gate green before and after.
5. **Baselines:** M2's session scenes unchanged under `mode = "drop"`; the `t2v/1` fixture; the
   settings reference; `allowed_in_source.toml` gains the entries Q1 settles.
6. Gate, review, fixes, merge into `plan-005-integration`.

**The tracks** (in parallel after Block 0; `## Tracks` gives each one's files and tests)

7. Track A: the words and the rule. Track B: the session. Track C: the Pipecat side. Track D: the
   browser. Track E: the measurement's tooling. Each ends with a report: its progress-log and
   decision-log lines and any debt rows.
8. Merge in the order A, B, C, D, E (`Plan 005: merge track X`, then `Plan 005: review fixes,
   track X`), the full gate after each. The integrator is the only writer of this plan and of
   `docs/plans/tech-debt.md`.
9. **The integration check, with no spend,** inside `poe check`: an aiortc client built with
   `RTCConfiguration(iceServers=[])` hears a long reply from the fake `TextToSpeech`; a stop word
   fed through a fake speech detector and a fake `SpeechToText` brings `duck`, then no agent audio
   frame more than 40 ms after `StopSpeaking`; a listening sound brings `duck`, `unduck` and the
   reply played to its end; `poe overlap --answerer reference` scores every verdict right and
   0 ms.
10. **The whole-plan review**, one reviewer, one skeptic per finding, under the same rule.

**The recordings**

11. As Q2 and Q6 settled: the owner records M3's lines with `poe record` on the three devices
    (the recorder plays a reply while the owner speaks over it) and about 20 new paused requests,
    confirms each in its review mode, and marks the end of each stop and wait word and each true
    turn end (`turn_ends_ms`), and the stop words' ends on the dev talk-over clips; `poe golden`
    freezes; the new items are split, each existing item keeping its side (whether the
    split script keeps them is read first: UNVERIFIED). After plan 003's run C: its alignment
    checked (TD-070), each turn that opened over a reply becomes a variant cut from the caller's
    track, carrying the text of the clauses that played over it, and the owner confirms each
    reference and stop word's end.

**The registered runs** (a quiet machine, [WORKING-RULES.md](../../../WORKING-RULES.md),
"Measurement runs")

12. Every open call settled and dated; the budget cap approved (Q7); plan 003's spending rule
    before each run or call session that spends, the running total in the progress log.
13. **L:** R5, R7 and R6, before O1, since they set the language M3's requests name; each history
    line carried to the main branch in its own commit before the next run; the rule sets
    `stt.live_language`'s default in its own commit, or Q5 does.
14. **F** (no spend): the filter scored on R1's and R3's stored scorecards; its defaults move in
    their own commit (GP-18).
15. **E** (no spend): `poe eot` on dev's paused requests, the base twice, then each arm; a kept
    arm's defaults move in their own commit, before O1, so O1 measures stops with the turn
    defaults M3 keeps; held-out E once, at step 17.
16. **O1 and O2:** `poe overlap` on dev, twice at one commit, at least an hour apart, history
    lines carried to the main branch in their own commits; at most one dated amendment of the
    rule, scored offline on their stored transcripts, before H3 and C3.
17. **H3 and C3:** held-out once (aggregates only), with held-out E, and run C's overlaps with
    M3's new held-out lines. If every target holds, `interruptions.mode` defaults to `two_step`
    in its own commit; if one fails, it goes to the owner with its numbers.

**The live calls**

18. From the main checkout after M3's merge, through the Ole5 app's dev server, in Chrome: the
    rehearsal's steps 1 and 2 on the laptop's speakers, then on the wired headset; a call on the
    speakers with the owner silent through five replies; push-to-talk tried on the speakers. The
    agent reads each call's trace and `CallReport`.

**Close**

19. The guide's `concepts.md` (the two-step interruption, the cancel scope, the heard history, a
    diagram of one turn) and `browser-client.md`'s M3 part (voice lowering, push-to-talk), each
    sample from a tested file; the decision entries (the cancel scope; the two-step interruption,
    its settings and rule; the presets' words and Q1's ruling; the filter; the heard history and
    the repeat; `t2v/1`'s new messages; the live language and the turn defaults; the registered
    results); `## Future improvements`, with a
    pointer from the roadmap's "Planned later"; the roadmap's M3 row; this plan moved to
    `completed/`; the final gate.

## Progress log

- 2026-11-03: Drafted by the agent at the plan-003 session's request, from the roadmap's M3
  section, the package design (its 3.1, 4.3, 5.5, 6.4, 6.6, 7.6, 9.5, 13, 14 and 16),
  evaluation.md, D-028 to D-039, the main branch's decision 50 and `agent-led-mode.md` (not yet
  on this branch), plan 002's Future improvements and window runs, plan 003, the debt rows TD-055
  to TD-083, the M2 code on `plan-003-integration` at 2c34d3e, the golden items' tags, and, read
  only (D-010), the prototype's `VOICE_LOG.md` (D23, D30, D53, 2026-10-26 19:20) and
  `src/ole5_chat/voice/rules.py`. The agent's count of the overlap clips, from each item's `tags`
  and `split.json`: dev's talk-over has 90 variants in 33 items, 82 tagged `over-assistant` in 31
  items (stop words 2 items and 4 variants, wait words 2 and 5, listening sounds 8 and 18,
  requests 15 and 43, short requests 2 and 7, a repeat request 1 and 4, a confirmation 1 and 1),
  all on the laptop's microphone; «وقف» is in 2 dev variants. Held-out's talk-over has 28
  variants, 24 over the assistant. Later the same day, the owner, on the draft: "Too not stretch
  the plan, make it focused on the fundamentals and quality, and not about extra unnecessary
  things." So the parity test moved to M4 with `TextCall`, the Bluetooth warning and its guide
  page were left out for the owner's yes, and a push-to-talk suggestion message was dropped.
- 2026-11-03: At the plan-003 session's request, the draft moved to a worktree and branch of its
  own, `plan-005-draft`, cut from `plan-003-integration` at 128f152, with M3's roadmap row linking
  it, which DOC-PLAN needs of an active plan; the cut of M2 that session relayed (R5 to R7 and the
  noise on another day moved here, T1 and T2 dropped, plan 003's Q16 to M4) is written in.
- 2026-11-03: The owner answered Q1 to Q7 ("The owner's decisions"): the agent's recommendations
  for Q1 to Q5 and Q7, and for Q6 the tuning in M3, asking the agent to say if it fits a later
  milestone better. The agent's answer, given to the owner the same day: M3 fits it, for three
  reasons. Silero's stop delay (`vad_stop_ms`) is one value per pipeline, which both a turn's end
  and an overlap's second request wait on, so tuning it in a later milestone would move M3's
  registered stop times; E therefore tunes only what ends a turn after that delay. `poe eot`
  runs offline with no spend, on E1, M2's baseline. And Q2's recording session takes the new
  paused requests too (plan 003's estimate for about 20 of them: about an hour on the three
  devices). E's registration is added below. Plan 003's cut, read on `plan-003-integration`
  (818d27d): `plan-003-integration` merges into the main branch after its step 16, and run C is
  part of its step 18's session (four calls in Chrome, a listening sound in each Arabic call
  during an echo, no Bluetooth call); Q2's (b), a few «وقف» over an echo in that session, is the
  plan-003 session's to add. Nothing built; M3 starts on the owner's word once M2 is finished.

## Decision log

The agent's choices, each dated with its reasons; the owner may overrule any before the step it
affects.

- 2026-11-03: One plan, Block 0 and five tracks; the guide written at the close by the
  integrator. Plan 003's nine tracks set aside: M3 is smaller and the owner asked for speed.
- 2026-11-03: The two-step interruption lands behind `interruptions.mode`, `drop` (M2's rule)
  by default until H3 and C3 hold, then `two_step` in its own commit (GP-18).
- 2026-11-03: The second request goes when the detector hears the overlap's speech stop, not at
  the turn's end: a lone «وقف» may not sound complete to Smart Turn, whose fallback is 3 s. It
  holds the whole overlap, not what followed the window: Whisper bills 10 s a request whatever
  its length (the design's 16.4) and hears the words with their context.
- 2026-11-03: The window counts from 300 ms before `speech_at`, so a 750 ms window holds what
  run W3's held (plan 002 cut its windows from the file's start, 300 ms of padding before
  speech). Counting from `speech_at`, as W5 at 1000 ms approximates, is set aside: no better on
  M1's numbers (large-v3: 18 of 28 one-word clips at 750 ms, 16 at 1000 ms) and slower.
- 2026-11-03: A turn in D-037's 300 ms tail after a reply is an overlap, judged by the rule; after
  a client's `stop` there is no tail, since nothing of the agent's plays to echo (TD-060).
- 2026-11-03: The browser lowers the agent's voice, as the roadmap says, at the detector's onset
  (about 0.34 s into the speech: D-034's spike). The prototype found ducking better than pausing
  for what Whisper hears (Arabic character errors 0.16 against 0.31 on the speakers:
  `Ole5-chatbot/VOICE_LOG.md`, D53).
- 2026-11-03: A repeat says the last reply again from its text: the frame from the phrase cache,
  the heard words through text-to-speech. Keeping the reply's audio to replay it is set aside:
  a new store of agent audio, while a cut reply's audio was never all made; a debt row if the
  Orpheus limits bind in the live calls.
- 2026-11-03: A clause counts as heard at its `ClausePlayed`, as D-037's tail counts; a clause
  playing at a stop is `cut`, with the fraction of its audio played; a clause's words are never
  split, Orpheus giving no word times.
- 2026-11-03: The cancel scope takes any awaitable work, not only the talker's, and the history
  marks a turn whose reply was cut before any clause played: the agent-led mode (the main
  branch's decision 50) cancels a team's agent mid-run behind this same voice layer and rolls
  back a turn the caller stopped before hearing its answer.
- 2026-11-03: The replay keeps the design's name, `AudioCall`, and is reached through the `evals`
  facade until M4 makes the testing kit public with `TextCall`.
- 2026-11-03: `turns.vad_stop_ms` stays 200 ms and is no arm of E: an overlap's second request
  waits on it, so a longer stop would slow every stop by as much. E's arms act only after it:
  Smart Turn's threshold and its fallback.

## The owner's decisions

What the owner has already said that binds M3:

- 2026-11-03, the answers to this plan's questions: "Go with your recommendation for Q1, Q2, Q3,
  Q4, Q5 and Q7. But for Q6 do the tuning in M3, if you see the turn-ending tuning more suitable
  and better implemented in later milestones tell me. I will give the start permission for M3 once
  M2 finish." So Q1 (a), Q2 (a) and (b), Q3 the targets as written, Q4 (a), Q5 (a) if L's rule
  leaves it open, Q6 (b), Q7 $5; and M3 starts only on the owner's word, once M2 is finished.
- 2026-11-03, on this draft: "Too not stretch the plan, make it focused on the fundamentals and
  quality, and not about extra unnecessary things."
- 2026-11-03, to the agent's cuts of M2 in plan 003: "Yes, cut them" (plan 003 and the roadmap
  on `plan-003-integration`, 818d27d, not yet on this branch). So R5 to R7
  (the live language, with plan 003's Q15) and TD-032's noise runs moved to M3, T1 and T2 left M2,
  and the prompt arm for product terms (plan 003's Q16) went to M4.
- 2026-11-03, in plan 003: "This is taking longer than I expected. Focus on things that matter
  for the next milestones and that we will need to build the voice agent. A consent for my or my
  team recordings is not a concern." So the review rule above, and the owner's own recordings
  need no new consent work.
- 2026-11-02, plan 003's Q6, "(a)": "stop" may stand in the source for the protocol's names, with
  the agent's note that M3's plan rules on the presets' words (Q1).
- 2026-11-02, recorded on the main branch with the agent-led mode: "I have decided to finish the
  first mode (pure voice with its tools) first and finish our use-case Ole5."
- 2026-11-01, "Approve all" (D-017): M3's goal, *Done when* and the design's 16.1 M3 row bind
  this plan, but for what "Scope" leaves out for the owner's yes.
- 2026-11-01 (D-018, answer 8): Pipecat's interruptions stay off; only the session interrupts.

## Tracks

Each track builds in its own worktree against Block 0's interfaces and fakes. One owner per
file; Block 0 owns the files every track needs (the session's I/O, the protocol, the settings,
the facades, the fakes and fixtures, `harness.toml`, `allowed_in_source.toml`), and the
integrator this plan, `docs/plans/tech-debt.md` and step 9's test. Library paths are under
`packages/t2-agentic-voice/src/t2_agentic_voice/`, its tests under `tests/t2_agentic_voice/`.

**Track A · The words and the rule (`domain`).** Owns `domain/words.py`'s lists,
`domain/interruptions.py`, `domain/silence.py` and their tests. May read the prototype's
`src/ole5_chat/voice/rules.py` (its lists and the noisy «وقف» spellings, lines 11-116 and
132-200) and `stt.py` (its caption list and no-speech rule, lines 35-75), read only (D-010).
Tests: each step of the starting rule on texts written for the test, never an item's; the
no-fixed-phrase test.

**Track B · The session (`voice/session/`, no Pipecat).** Owns `scope.py`, `overlap.py`,
`history.py`, and the changes to `call.py`, `echo.py`, `speaker.py`, `playback.py`, `report.py`
and `usage.py`. Tests, with the fake I/O, the slow responder and the fake clock: each verdict's
commands and events; a stop cancelling the scope within 100 ms, no task left; a repeat; the
history's marks; a turn in the tail; `mode = "drop"` unchanged; TD-055 and TD-060.

**Track C · The Pipecat side (`voice`).** Owns `stt_bridge.py` (the window and the overlap),
`session_bridge.py`, `tts_bridge.py` and `tts_output.py` (TD-064's stop part),
`file_transport.py` (a clip fed over a reply) and `turns.py` (Smart Turn's threshold, a turn's
end unchanged at its default). Tests: at most two requests decide an overlap; the
second sent at the detector's stop; no window for an overlap whose speech stops first; the second
transcript reused when no speech followed; a stop leaves no context of a clause never opened; no
Pipecat interruption fires.

**Track D · The browser.** Owns `api/static/t2v-client.js`, `api/static/dev.html` and
`apps/ole5-voice-agent/web/`. Tests: `duck` and `unduck` applied; a cut caption; push-to-talk
enabling the microphone only while held; no `innerHTML` or its kin.

**Track E · The measurement's tooling.** Owns `testing/audio_call.py`; in
`apps/ole5-voice-agent/src/ole5_voice/evals/`, `overlap.py`, `overlap_score.py`,
`import_calls.py` and the history's new run kind; the new lines of `evals/script.toml` (Q2); the
poe task `overlap` (asked of the integrator). Tests: the `reference` answerer; the scorer on
hand-made verdicts (a stop missed, a false stop, a stop timed from a labelled end); the pacer at
10 Whisper requests a minute; held-out writing aggregates only; a run refusing the main checkout
and a dirty tree.

## The measurement, registered before any result

Written on 2026-11-03, before any run. Amendments are dated and made before the result they
affect; every open question is settled, in the owner's words and dated, before the step it gates.

**Data.** The golden set's variants tagged `over-assistant` (dev: 31 items, 82 variants); the
script's stop, repeat and listening items recorded alone, fed over a reply (dev: 4 items and 15
variants, 3 and 11, 3 and 13); silence, noise and the agent's echo alone (dev: 3 items, 9
variants); M3's new lines (Q2); run C's overlaps (C3). What each should do: a stop or wait word,
or a request, a repeat request or a confirmation over a reply, stops the agent (a repeat request
also repeats); a listening sound, silence, noise or the agent's echo does not.

**The arm, O.** The replay at real-time pace with the real `GroqSTT` (`whisper-large-v3`; the
item's label as the call's language, as plan 003's T1 sends it), a fake `TextToSpeech` whose
reply outlasts the clip, the clip 1 s into the reply, a 4.5 s tail, a fresh call per variant,
`interruptions.mode = "two_step"`, every setting on the command line. The reply's clauses are
the texts that played over the clip where they are known (M3's new lines, run C's overlaps),
otherwise a text no clip holds. O2 is O1 again at the same commit.

**The starting rule** (the agent's, from plan 002's Future improvements and the prototype's D30
and D53), applied to the window's text, then to the overlap's when the window did not stop the
agent, after the canonical normalization:
1. no words, or text from silence (F): go on;
2. a stop or wait word, or the prototype's noisy «وقف» (one or two short words ending in «قف»,
   «كف» or «غف», no question or no word: its `rules.py`, lines 54-56): stop;
3. a repeat word: stop, then repeat;
4. the agent's own words (each word within one edit of a word of the clauses that played in the
   last 5 s): go on;
5. listening sounds only: go on;
6. a short output (at most 2 words and under 1.6 s of speech, none a stop, wait, repeat, no or
   question word): go on (Q4);
7. at least `min_words` (2) words: stop; fewer: go on.

**Metrics, per variant:** the verdict and whether it is right; the part that decided; the
overlap's Whisper requests; for a stop, the time from the owner's mark of the word's end
(`turn_ends_ms`) to the last agent audio frame sent, and, with no mark, from the detector's stop,
reported apart. Medians and 90th percentiles (type 7, as plan 002), by kind, language and
device. The scorecards keep each part's transcript, `no_speech_prob`, length and times, so a
revised rule is scored again offline with no request (evaluation.md, "Fitted, then fresh").

**The targets** (the agent's proposals, Q3; each holds on O1's dev variants, on H3's aggregates
and on C3):
- **The window:** 750 ms, from run W3 (large-v3 held 18 of 28 one-word clips at 750 ms, 13 at
  500 and 16 at 1000; Saudi halt words 2 of 4 at 750 and 1000, none at 500).
- **Whisper requests per interruption:** at most 2 for every overlap, in code and in every run
  (expected mean about 1.4: 1 when the speech stops before the window). In the live calls, at
  most 10 a call minute, half the published 20 (plan 003's registration).
- **From the end of «وقف» to silence:** on the marked stop and wait variants that stopped, a
  median of at most 700 ms, a 90th percentile of at most 1,000 ms, none over 1,500 ms; every
  «وقف» at normal volume stops. The prototype's baseline was about 1 s after the word
  (`Ole5-chatbot/VOICE_LOG.md`, 2026-10-26 19:20).
- **Stops heard:** at least 90% of the stop and wait variants, and of the requests over a reply,
  stop the agent.
- **False interruptions:** at most 10% of the listening-sound variants stop the agent; no echo,
  silence or noise variant does, nor the agent's own words where their text is known.

**The noise:** verdicts that differ between O1 and O2, and the change of the stop time's median;
the agent expects few or none (d = 0 for Whisper on 2026-11-01, D-024).

**The rule's revision:** if a target fails on O1, the agent may revise the word lists, the
short-output and own-words bounds and F's threshold once, as a dated amendment scored offline on
O1 and O2, before H3 and C3. A target still failing there goes to the owner with its numbers.

**F, the filter** (no spend): on R1's and R3's stored scorecards, `stt.no_speech_max` = 0.5 and
the caption list (the prototype's, `stt.py` lines 35-54, with «موسيقى») are on by default if, on
both runs, they blank at least 3 of the 9 empty-reference variants and none of the 222 speech
variants (plan 002 expects 3 of 9 for the threshold and 7 of 9 for the list).

**Expected (the agent's):** a stop about 0.45 to 0.65 s after the word, at the median: the
detector's 200 ms stop, Whisper's request (the window runs' medians: 211, 372 and 227 ms) and up
to about 40 ms of the stop path (io.py); Saudi halt words the weakest (large-v3 heard Saudi stop
words in 9 of 11 whole clips); misheard listening sounds (9 of 22 right on whole clips) held by
steps 5 and 6; requests over a reply stopping it nearly always.

**L, the language a live call sends Whisper, and the noise on another day** (plan 003's
registration, moved here unchanged):
- **Arms:** A1 as plan 002 registered it (`whisper-large-v3`, the item's label as the language,
  no prompt, temperature 0, `verbose_json`, `--timeout-s 6`); A3, the same with
  `--language-hint auto`, so no language is sent.
- **Runs** on the dev split (66 items, 231 variants), at one measurement commit, on a day other
  than 2026-11-01: R5 (A1), R7 (A3), R6 (A1), in that order, with plan 002's runner settings as
  amended (`--max-attempts 4`, `--variant-timeout-s 120`, `--max-rpm 10`, `--price-per-hour
  0.111`, `--cap-usd` from Q7) on the command line; each at least 15 minutes after the last, and
  no other Whisper use within the hour around it. R7's smoke step reads the form of Groq's
  `language` (TD-011); a name is mapped to a code in the adapter before any default moves.
- **The noise first:** if R5 and R6 differ by p < 0.05 (D-024's method), the runs are
  unreliable: this is said, the comparison is not read, and the larger noise is recorded
  (TD-032).
- **The rule for `stt.live_language`:** it stays `session` if A3 is worse beyond the noise in
  either comparison (R7 against R5, and against R6; p < 0.05, more items worse), or has more items
  worse than better in both; any other outcome goes to the owner with its numbers (Q5).
  `eval-compare` takes `--allow-setting run.language_hint` for these comparisons.
- **Expected (plan 003's):** A3 worse, most on mixed and short items (the prototype's
  auto-detection got 23 of 35 segments against 32 of 35 with a forced language:
  `Ole5-chatbot/VOICE_LOG.md`, D24); R5 and R6 identical or nearly so (D-024).

**E, the turn defaults** (offline, no spend; Q6, settled):
- **Data:** the paused requests, each true turn end marked by the owner: dev's 6 items (23
  variants) with Q2's new ones (about 20 lines on the three devices, split by item), and
  held-out's 4 items with the new held-out ones, once at step 17 (aggregates only); the secondary
  set of plan 003's E (every other dev variant with speech) for cut-offs only.
- **Arms,** each `poe eot` on the file-fed pipeline as plan 003's E1 runs it, every setting on the
  command line: **E0**, the defaults (E1's: Silero's 200 ms stop; Smart Turn v3.2 at its 0.5
  threshold, its 3.0 s fallback), run twice at one commit for the noise; **Ea**,
  `smart_turn_threshold` 0.7; **Eb**, 0.8; **Ec**, 0.7 with the fallback (`smart_turn_stop_ms`)
  at 2,000 ms, so a finished turn the higher threshold misses waits 2 s rather than 3. A floor of
  silence is no arm: the owner's pauses run about 0.83 s (`Ole5-chatbot/VOICE_LOG.md`, the
  prototype's D43), so a floor that bridges them would add about 0.7 s to every turn.
- **Metrics,** as plan 003's E: cut-offs (a first turn end more than 300 ms before the marked
  end), misses (none within 4 s after it), and the end-of-turn delay's median and 90th
  percentile, by item, language and device.
- **Keep rule:** an arm replaces the defaults if, against E0 on dev, more items have fewer
  cut-offs than more beyond the noise (the sign test by item, p < 0.05, at least D-024's floor of
  6 items more better than worse), no item gains a miss, and its median delay rises by at most
  300 ms (the agent's bound: every turn waits it); of several, the one with the smaller median
  delay. Held-out confirms it by its aggregates (no more cut-offs than E0's) before the default
  moves; if it does not, the defaults stay and the numbers go to the owner.
- **Expected (the agent's):** E0's cut-offs fall on Arabic paused requests (Smart Turn v3.2's
  published accuracy is 89.76% for Arabic against 94.26% for English, plan 003's registration);
  a higher threshold removes some of them, at the cost of finished turns that wait for the
  fallback, which Ec shortens; whether Smart Turn's probabilities on the owner's pauses sit
  between 0.5 and 0.8 is UNVERIFIED until E0. If E0 shows almost no cut-offs, no arm can pass the
  floor and the defaults stay.

**Cost and limits** (the agent's arithmetic, $0.111 an hour of billed audio, 10 s a request): L
about $0.23 (plan 003's estimate) and about 100 minutes with its pauses; O on about 160 dev
variants, at most 2 requests each, about $0.10 a run, $0.20 for O1 and O2; H3 about $0.04; C3
about $0.02; the live calls, about 8 call minutes, about $0.14 with Orpheus's Arabic model; E
and F nothing. About $0.63 in all. An O run takes about 40 minutes at the pacer's 10 requests a minute; O1 and O2 run
an hour apart with no other Whisper use around them, under the published 7,200 audio seconds an
hour. Orpheus's published 100 requests a day bind only the live calls.

**Words the questions use.** *Overlap:* the caller speaking while the agent speaks. *Duck:*
lowering the agent's voice meanwhile. *Window:* the first part of the overlap, sent to Whisper
before the caller has finished. *Listening sound:* «اها», "mm-hmm": "I am listening", not "stop".
*Own echo:* the agent's voice coming back into the microphone from the speakers. *Text from
silence:* words Whisper writes for audio that holds none.

**The owner's questions, all settled on 2026-11-03** ("The owner's decisions")

Before Block 0:

- **Q1. The presets' words and "No item in the product."** *Settled: (a).* The presets need words
  that are also one-word items of the golden set («وقف», «تمام», "okay", "wait"), which the test
  that no item's text is in the source refuses; plan 003's Q6 left this to M3. Options: (a) one
  ruling covers the lists Track A writes from the prototype's, each word an entry of
  `allowed_in_source.toml` quoting it; those items then measure how the rule meets Whisper's
  mishearings, not whether the word is listed; (b) a ruling per word; (c) the held-out words left
  out of the presets, which keeps held-out blind but leaves the agent deaf to them. **The agent
  recommended (a).**
- **Q2. New recordings.** *Settled: (a) and (b); (a)'s session also takes Q6's paused requests,
  and (b) is the plan-003 session's to add to its step 18.* Dev holds «وقف» over a reply in 2
  variants, every overlap clip is on the laptop's microphone, and no word's end is marked.
  Options: (a) a recorder session of M3's lines, the recorder playing a reply, on the laptop's
  speakers, the wired headset and the Bluetooth headset: «وقف» three times at normal volume, the
  other stop and wait words, the rehearsal's repeat requests, a few listening sounds and silence
  over a reply (about 30 to 45 minutes), then the review with each word's end marked (about 15
  minutes); (b) a few overlap lines added to plan 003's run C; (c) the existing clips only, timed
  from the detector's own stop. **The agent recommended (a), and (b) too,** so the check on M2's
  recordings tests stops, not only the echo.
- **Q3. The targets** as registered. *Settled: as written.* "Listening sounds do not interrupt"
  is read as at most 10%, since a misheard listening sound can come back as two words of a
  request.
- **Q4. A short output that is no listed word** (Whisper heard «ايوه» as «هل تريد؟»). *Settled:
  (a).* Options: (a) at most two words under 1.6 s, with no stop, wait, repeat, no or question
  word: the agent goes on (the prototype's D30), so a misheard listening sound does not stop it,
  and a misheard short request is missed until the caller repeats it or presses Stop; (b) any two
  words stop it. **The agent recommended (a).**

Before the runs:

- **Q5. The language a live call sends Whisper, when L's rule does not decide** (plan 003's Q15,
  moved here). *Settled: (a) if L's rule leaves it open.* If A3 is not worse: (a) auto-detect for
  live calls, the widget's language buttons kept only as a preference; (b) the session's language
  anyway; (c) the prototype's double transcription, each turn sent as Arabic and as English (its
  D24), twice the requests at 10 s each against Whisper's 20 a minute. **The agent recommended
  (a) in that case,** and (b) otherwise, as the rule already gives.
- **Q6. The turn defaults,** which plan 003's Q14 left to M3. *Settled: (b), tuned in M3 by E's
  registration; the agent's view that M3 fits it is in the progress log.* Options: (a) not tuned
  in M3, E1's baseline standing until M4's talker makes a cut-off costly; (b) about 20 more paused
  requests recorded in Q2's session and tuned in M3. The agent had recommended (a), unless E1
  showed cut-offs on at least 2 of its 6 dev items.
- **Q7. The budget cap** for M3's paid runs and calls, against about $0.63. *Settled: $5,* M1's
  cap, as the agent recommended.

## What the owner does

1. **The start:** once M2 is finished, give the start of M3.
2. **After Block 0:** record M3's lines and about 20 paused requests with `poe record` on the
   three devices (Q2, Q6, about 1.5 to 2 hours), then confirm each in the review, marking the end
   of each stop and wait word and each paused request's true turn end.
3. **After plan 003's run C:** confirm the imported overlaps' references and stop words' ends.
4. **Before the first paid run:** say whether anything else uses the key during the runs; Q5's
   answer applies only if L's rule leaves it open.
5. **The live calls** (step 18): in Chrome, the rehearsal's steps 1 and 2 on the laptop's
   speakers and on the wired headset, a call on the speakers staying silent through five replies,
   and push-to-talk on the speakers; say whether each stop and repeat worked.
