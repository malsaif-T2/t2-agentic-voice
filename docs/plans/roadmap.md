# Roadmap

Depth-first: each milestone produces a verified building block that the next one relies on.
When a milestone starts, it gets an execution plan in [active/](active/) (see
[README](README.md)). The owner sets the milestones and their order; the agent proposes them
from [DESCRIPTION.md](../project/DESCRIPTION.md) and records the owner's answer here. Each
milestone builds the Ole5 app's work and the library work it forces together, so the app
consumes the library through its public API as it grows (D-013). Milestones
carry no delivery dates: work moves by plan and by what is verified
([WORKING-RULES.md](../../WORKING-RULES.md)).

Milestone numbers change when the roadmap is re-planned, so code never cites them: it cites
decisions (`D-NNN`), which are permanent. Living docs cite only milestones in the table below.
`uv run poe docs` enforces both (DOC-MILESTONE).

| # | Milestone | Status |
| --- | --- | --- |
| M0 | Scaffold and harness | in progress ([000](active/000-project-scaffold.md); [001](completed/001-library-and-app.md) done) |
| M1 | The measurement first: the owner's voice as a golden set | done ([002](completed/002-golden-set-baseline.md)) |
| M2 | A call that listens and speaks | done ([003](completed/003-call-listens-and-speaks.md)) |
| M3 | Interruptions and cancellation | done ([005](completed/005-interruptions-and-cancellation.md)) |
| M4 | The talker and knowledge answers | done ([006](completed/006-talker-and-knowledge-answers.md)); its live calls moved to M7 |
| M5 | Tickets, ticket status, and handoff | done ([007](completed/007-tickets-status-handoff.md)); its background try moved to its Future improvements |
| M6 | Reliability and operations | planned |
| M7 | The rehearsal: the owner's script passes | planned |
| M9 | The voice experience at the level of top-tier voice agents | in progress ([010](active/010-top-tier-voice-experience.md)) |

Status is `planned`, `in progress` (with links to its active plans) or `done` (with links to
its completed plans). Between milestones, [garbage-collection rounds](../harness/garbage-collection.md)
keep entropy down; they and other side work get a plan but no row. While such a plan is active,
it is linked from the line below (DOC-PLAN fails on an active plan the roadmap does not link),
and the link is removed when it completes.

Outside the milestones: garbage collection, round 1 ([004](completed/004-garbage-collection-1.md))
and round 2 ([008](completed/008-garbage-collection-2.md)), both completed.

## Milestones

M1 to M7 are the agent's proposal of 2026-10-28, at the owner's request ("write your proposed
design as milestones in the roadmap"). They come from the architecture proposal the agent wrote
earlier that day ([Ole5 Voice Agent Architecture](https://claude.ai/artifact/WVGaY7fH8mckPgGn45oMzJ),
a Claude Docs document in the owner's account), adapted to the owner's messages of that day:
Groq only (D-004), the hosting limits (D-005), the owner's own voice as the only data for
Phase 0 (D-006), and a handoff that is a ticket (D-009). The owner approved them on
2026-11-01 (plan 000).

On 2026-10-31 the project became T2 Agentic Voice, a library and the Ole5 app built on it
(D-013). Each milestone now also lists, under *Library*, the library work its Ole5 work
forces, from the package design ([package-design.md](../design/package-design.md), section 16,
D-017), proposed with it. The goals and the *Done when* lines are unchanged. A first version
for teammates is not a milestone: it is tagged when a real teammate is ready to install it
(the design's section 16.1).

On 2026-11-01 the owner answered the design's open questions (D-018): M4's background
troubleshooting moved to the thinker, after M7, and M5's handoff is read back and confirmed
like any action, which changes M5's *Done when* line.

On 2026-11-03 the agent asked "Move the deployment and network tests to when the server is
available?" and the owner answered "Yes, move them"
([plan 003](completed/003-call-listens-and-speaks.md)). So M2's calls stay on the owner's laptop,
which changes M2's name, its deployment bullet and its *Done when* line, and the deployment
becomes a plan of its own (M6's section).

Later on 2026-11-03 the owner asked to finish M2 faster, on the package's fundamentals, and answered
"Yes, cut them" to the agent's cuts (plan 003). So M2's *Done when* line reads the time of each step
and requests per call minute from the owner's recorded call session in Chrome rather than from runs
on the golden set, M3 takes the language a live call sends Whisper, and M4 the prompt arm for
product terms.

**M0 · Scaffold and harness.**
- The project's idea in [DESCRIPTION.md](../project/DESCRIPTION.md), written with the owner.
- The layers chosen for this domain, in `harness.toml` and [ARCHITECTURE.md](../../ARCHITECTURE.md).
- The stack recorded as a decision, and the gate green locally and in CI.
- The workspace of the library, the Ole5 app and `examples/minimal`, with ARCH-PUBLIC keeping
  the app on the library's public API (plan 001, done).
- The package design reviewed by the owner: what the library provides and what an app must
  provide (D-017), with the teammate guide's index in [docs/guide/](../guide/README.md).

*Done when* `uv run poe check` passes on the project's own package and layers, CI runs the same
gate, and the owner has approved the layers, the stack, the package design, and the first
milestones after this one.

**M1 · The measurement first: the owner's voice as a golden set.**
- The golden set ([evaluation.md](../design/evaluation.md), D-011): the 124 talk-over segments
  recorded for the prototype (read from their folder, D-010), and new recordings of the owner on
  each target device. They cover Saudi Arabic, MSA, English, and Arabic with English product
  terms; stop words, repeat requests, and listening sounds; requests of several clauses that
  pause mid-sentence, recorded as whole takes with every true turn end labelled; and silence and
  noise. References follow one spelling guide.
- The commands `golden`, `eval`, and `eval-compare`, with the prototype's scorer ported to this
  repository's layers.
- The speech-to-text port in `domain` and its Groq adapter (Whisper large-v3 and turbo), so the
  first baseline can be measured. Whisper is also scored on the first 0.5–1.0 s of each
  talk-over clip, so M3's interruption window is chosen from data.
- `core`'s tracing helpers sending spans to Phoenix: they take the turn's span as an argument,
  and a test proves no secret reaches a trace ([SECURITY.md](../SECURITY.md), invariant 5).
- *Library:* the `SpeechToText` port and the Groq Whisper adapter above; the canonical
  Arabic normalizer and digit normalization; the scorers as library functions (`wer`, `cer`,
  term and ID recall, the sign test), while the golden-set runner stays in the app; the guide's
  `evaluation.md`.

*Done when* `poe eval` writes a baseline scorecard for Groq Whisper on the owner's voice, by
language and by device; the noise (the same run twice) is recorded as a decision; and the gate
passes. *Done* on 2026-11-02 ([002](completed/002-golden-set-baseline.md)): Whisper was scored
on the first 0.5–1.0 s of the 90 dev talk-over clips only, not of each talk-over clip (plan
002's `Deviation:` line on Q15).

**M2 · A call that listens and speaks.**
- The web widget: start and end a call, the microphone, playback, captions, the Stop button
  and Esc.
- `api`: the join token (invariant 7), the offer route (`voice` answers the offer), health.
- `voice`: the Pipecat pipeline over its peer-to-peer WebRTC transport, Silero VAD, and Smart
  Turn, with our own processors calling the speech-to-text and text-to-speech ports (Groq
  Orpheus, an Arabic and an English voice), and `domain`'s rules for speaking numbers and ticket
  IDs. Pipecat's loguru switched off by `voice`, which owns it in `[[owners]]` (the design's
  12.2; plan 003's Q2), and a test that a debug line holding a transcript does not reach the
  output (invariant 8); the library's own logging is the design's contract (its 3.3 and 10.2)
  since plan 003's step 8.
- No talker yet: the agent says back what it heard. One trace per turn in Phoenix, with the
  requests and audio seconds each Groq model uses per call minute.
- The calls held on the owner's laptop, through the Ole5 app's dev server on localhost, with
  Phoenix as M1's on 127.0.0.1 (the owner, 2026-11-02 and 2026-11-03, plan 003). The deployment,
  the calls from other networks and the media path moved out of M2 (M6's section).
- The owner's call session through the widget, in Chrome, recorded with the recording setting on
  (invariant 8), each call keeping the caller's track and the agent's playback timeline, so M3's
  targets are also checked on audio that came through WebRTC (one session: the owner, 2026-11-03,
  plan 003).
- *Library:* everything above that is not Ole5's: Pipecat inside `voice` (the transport,
  VAD, Smart Turn, the speech bridges), the `TextToSpeech` port and the Orpheus
  adapter, the call session in echo mode, signed single-use join tokens, the router and
  `serve()`, the reference browser client and its protocol, the settings with a required `env`
  and their generated reference; `examples/minimal` as an echo agent; the guide's
  quickstart, serving, browser-client, settings, tracing and data pages. The widget is
  Ole5's, built on the reference client.
- *From M1* ([plan 002's Future improvements](completed/002-golden-set-baseline.md#future-improvements)),
  for M2's plan to weigh: a prompt arm that keeps product terms in Latin script (term recall
  was 0.333 on dev for large-v3); how a live call sets the language Whisper is sent, since M1's
  arms sent each item's label, which a call does not know (TD-011); and, when numbers are
  spoken, whether compound number words and the short and dialect digit names count as digits
  (TD-031). Each is measured on the golden set (D-024's floor of 6 items) before it changes a
  default. On 2026-11-03 the prompt arm moved to M4 and the live language to M3 (the owner,
  plan 003). Several debt rows name M2's plan as their trigger ([tech-debt.md](tech-debt.md)).

*Done when* the owner holds a recorded call session in Chrome on laptop speakers and on a headset,
locally, and hears each turn back; end-of-turn cut-offs are measured on the golden set, offline; and
the time of each step and requests per call minute for each Groq model are recorded from that
session's traces and call reports. *Done* on 2026-11-04 ([003](completed/003-call-listens-and-speaks.md)):
six calls, three on the laptop's speakers and three on a headset, each turn said while the agent was
quiet said back; the cut-offs measured by E1, E2 and held-out E (TD-094); the session's calls held
no trace, so the time of each step and the requests per call minute (D-040) were read from their
reports and timelines, which the owner accepted, and the test that no credential reaches a span
was left as debt (TD-095).

**M3 · Interruptions and cancellation.**
- The cancel scope of every turn: a stop, a correction, or new words cancel the model, the
  speech, and read-only lookups at once, and the widget's captions mark the cut (nothing the caller
  needs relies on a screen: D-075, M4).
- The two-step interruption. Step one: when the backend's speech detection fires over the
  agent, the widget lowers the agent's voice. Step two: Groq's Whisper gives no partial
  transcripts, so the decision comes from transcribing the overlap itself, a first window of a
  registered length and then the rest when the speech ends. The agent stops on a stop word or
  two real words, and goes on for a listening sound, its own words, or no words. The plan
  registers the window length, the Whisper requests per interruption, and a target for the time
  from the end of «وقف» to silence; the prototype's baseline was about 1 s after the word
  (Ole5-chatbot VOICE_LOG.md, 2026-10-26 19:20).
- The history keeps only what the user heard, clause by clause.
- The fallback when echo stays high on laptop speakers (Stop, Esc, and push-to-talk), and the
  warning for a Bluetooth hands-free microphone.
- *Library:* the cancel scopes, the two-step interruption and the history of what was heard,
  as library behaviour with Ole5's word additions as settings; audio replay for tests, and a
  test that text-mode calls follow the same path as audio calls; the guide's concepts and
  audio-troubleshooting pages.
- *From M1* ([plan 002's Future improvements](completed/002-golden-set-baseline.md#future-improvements)),
  for M3's plan to weigh: a filter for text from silence and the agent's echo (every silent,
  noise and echo clip came back with text, such as Whisper's invented captions); how its rule
  hears short Saudi words (often misheard even as whole clips); its first window (at 500 ms none
  of the 4 Saudi words asking the agent to halt was heard; large-v3 at 750 ms held the most);
  and the noise runs repeated on another day before its first comparison (done: D-066).
- *From M2* (plan 003, moved by the owner on 2026-11-03): the language a live call sends Whisper, by
  the rule plan 003 registered (its runs R5 to R7, after the noise runs above, and its Q15 when the
  rule does not decide; TD-011), taken up or registered again in M3's plan; until then
  `stt.live_language` stays `session`.

*Done when* the targets registered in its plan hold on the golden set's overlap clips and on
M2's call recordings: a normal-volume «وقف» stops the agent within its target, the agent's own
voice does not interrupt it, and listening sounds do not; and the rehearsal's stop and repeat
steps pass in a live call. *Done* on 2026-11-06 ([005](completed/005-interruptions-and-cancellation.md)),
at a plateau (evaluation.md, "Closing at a plateau"): the owner made the two-step interruption the
default with targets still failing (D-068). The stop time, the requests per interruption and no
stop for echo, silence or noise held; stop and pause words held on dev and failed on held-out (10
of 18), listening sounds the reverse (5 of 38 on dev), requests over a reply failed on both (15 of
18 on held-out), a normal-volume «وقف» stopped the agent in 5 of 6 dev variants, and the agent's
own words went unmeasured; the live calls passed the rehearsal's stop and repeat steps. The cancel
scope is one per reply (D-060), the parity test moved to M4, the Bluetooth warning and its page
were left out, and Ole5 needed no word additions (plan 005).

**M4 · The talker and knowledge answers.**
- The chat-model port and its Groq adapter; the talker's prompt, its few tools, and its reply
  language per turn; `api` injects into it only the chat-model port and `actions`' tool runner,
  with a test of that wiring.
- `actions`: one knowledge search per question (T2's Qdrant and embedding gateway, D-002), a
  short spoken answer with the full steps on screen, and a pre-recorded progress line while a
  tool runs. D-075 replaced the short answer and the screen inside M4: every step is said, and
  said again, whole or one step, when the caller asks; no screen is relied on. Deeper troubleshooting in the background moved to the thinker, after M7 (D-018).
- The output guard on every sentence (invariant 2), and tool arguments parsed at the boundary
  (invariant 4).
- Simulated calls for knowledge questions in Arabic and English, each scenario repeated.
- *Library:* the `ChatModel` port and the Groq chat adapter, the talker loop, `@tool` with
  its context and bound parameters, the output guard's ID rule, progress lines, a knowledge
  protocol and helper tool, the text-call testing kit and its fakes, with the test that text-mode
  calls follow the same path as audio calls (moved from M3, plan 005), `t2v check`, and the
  latency measurement; the Qdrant adapter and the prompts stay Ole5's.
- *For M4's plan to weigh*, from the next phase's study
  ([agent-led-mode.md](../design/agent-led-mode.md)): fixed spoken lines carry no stop, wait,
  repeat, yes, send or listening word, since an echo through the speakers could be heard as
  the caller's own; and the talker's tool list stays small (Groq advises 3-5 tools a request,
  10-15 at most).
- *From M2* (plan 003's Q16, the owner, 2026-11-03): the prompt arm that keeps product terms in
  Latin script (term recall was 0.333 on dev for large-v3), measured on the golden set (D-024's
  floor of 6 items) once the vocabulary that becomes the Whisper prompt lands.
- *From M3* ([plan 005](completed/005-interruptions-and-cancellation.md), the owner, 2026-11-04: "Ok
  record that to be tried in M4"): the talker takes what an interruption means, while the
  library keeps the fast stop. The library still stops at once on a clear stop word and never
  for a listening sound, its own echo or silence; the talker reads the rest with the history of
  what the caller heard (repeat, pause, say it slower or again in part, a correction, a request
  after a stop), so most of M3's repeat and pause word handling can move to it. A small
  classifier for the uncertain middle (a short utterance over the agent that is neither a listed
  word nor clearly a request) is tried as a registered arm against M3's rule, scored offline on
  the overlap runs' stored transcripts. Each moves a default only on a registered measurement.
  On 2026-11-06 the owner added that the system should not rely on "five or six command words":
  understanding the caller's request in any wording is the next step, first in [plan 005's
  Future improvements](completed/005-interruptions-and-cancellation.md#future-improvements), and
  how much the talker may add to the time a stop takes is M4's plan's question.

*Done when* retrieval (the right passage in the top 5) and answer correctness are measured; the
time to the first useful audio meets a target registered in its plan before any run; and the
rehearsal's password, archiving, and English questions pass. *Done* on 2026-11-09
([006](completed/006-talker-and-knowledge-answers.md)), with registered targets missed and its
live calls moved to M7, by the owner's word: on held-out, the share with an expected passage
retrieved was 0.816 (bound 0.90) and right answers read 0.408 (bound 0.80, unverified, since the
judge's check failed); with a search, the first audio's median and 90th percentile held (2,532
and 3,044 ms), but 5 of 40 replies had not begun by 3.0 s with no progress line. `t2v check` was
not built (TD-143).

**M5 · Tickets, ticket status, and handoff.**
- `domain`: the ticket flow's states and the yes rule, issuing the confirmed draft only from
  the heard words and the read-back receipt `voice` builds (invariant 1); each class added to
  `[[restricted]]`.
- `actions`: the call's record of completed actions, added to `[[restricted]]` (invariant 2);
  the outbox, a durable store behind a `domain` port, from which ticket writes run as jobs with
  a request ID and are never repeated blindly (invariant 6); a correction after creation added
  as a note to the same ticket; ticket status by the session's verified identity only
  (invariant 3); the handoff ticket with the call's summary (D-009), read back and made only
  after a clear yes, like any action (D-018); the cap on creates per caller, read from the
  outbox.
- Adversarial tests for invariants 1, 2, 3, 4, and 6, against a fake ticket system that refuses,
  times out, and replies late, with and without a lookup by request ID.
- *Library:* `@action` for any side effect, with the read-back, the yes rule and its receipts,
  the outbox and lookups, the record, the guard's claim rule, the caps, and the safety suite
  teams run on their own actions; the T2 Ticket API adapter and the ticket action stay Ole5's.
  The handoff takes consent like any action: a read-back, then a clear yes (D-018).
- *The ticket system:* the owner has no access to the real one (2026-11-09), so M5 builds a mock
  in the app, for the demo and to prove the actions; its adapter waits for access
  ([plan 007](completed/007-tickets-status-handoff.md), Q2). The T2 Ticket API lines here and in
  the *Library* line above describe that later adapter.
- *From M1* ([plan 002's Future improvements](completed/002-golden-set-baseline.md#future-improvements)),
  for M5's plan to weigh: a ticket number heard is read back before it is acted on, never taken
  as heard (large-v3 got 4 of the 12 full 16-digit readings right, each miss a digit error), and
  the ticket is found by the session's verified identity.
- *For the next phase* (D-050): the consent core (read-back, receipt, yes rule, outbox, record)
  is built so that a second executor can be added later, one that resumes a team's paused
  agent instead of calling an `@action`. Nothing else in M5 changes.
- *To try in M5* (the owner, 2026-11-08: "an idea to really try and have a go with, especially
  with slow tools"): a slow tool runs in the background while the talker stays free to talk,
  knows it is waiting, and reads the result from a board when convenient, as a person reads a
  screen. Behind a setting, off by default, after the consent core; the *Done when* lines do not
  change. It is built so that the agent-led mode can use the same board
  ([background-tools.md](../design/background-tools.md)). The same try covers the talker saying,
  in one short clause, what it is about to look up. Moved to plan 007's Future improvements by
  the owner on 2026-11-12, since the rest of M5 ran long.
- *To build in M5* (the owner, 2026-11-10: "We should implement both of them and see their
  effectiveness and the latency improvements or delays they bring. Lets not delay them to M6 or
  M7, they can reasonably be implemented in M5"), each behind a setting and measured on a
  registered rule before a default changes (GP-18); the *Done when* lines do not change:
  - *Each turn's language from a classifier* (built: D-086, plan 007's Block H, behind
    `stt.live_language = "classified"`; run H kept no arm, so `session` stays and the rule for a
    call held in English is in plan 007's Future improvements), so a
    call can change language mid-call, in place of
    `stt.live_language = "session"` (D-066): Whisper is sent the classifier's language, chosen
    from the agent's languages only. The two candidates, by the owner: SpeechBrain's ECAPA
    (VoxLingua107) and Silero's 95-language classifier. The agent's offline check of 2026-11-10,
    on the 280 dev recordings, Arabic against English, outside the repository with neither model
    installed in it: ECAPA right on 93% (Saudi 98%, MSA 100%, English 79%, every request and
    paused request), 740 ms of CPU a clip at the median; Silero right on 84% (Saudi 80%, English
    79%), 36 ms. Every English clip ECAPA missed was a 1–2 s listening sound, stop word or yes,
    so a rule that keeps the current language on a short or unsure turn goes with it, and
    ECAPA's time must fit before the hold starts Whisper (D-067), for example by classifying the
    turn's first seconds while the caller still speaks. Measured: transcripts against D-066's
    `session`, English inside an Arabic call (run X: 0.813 sent as English, 0.027 as Arabic), and
    the time each adds.
  - *Every clause the agent says cached by its exact text,* not only the fixed phrases (amending
    D-033's "Text built from heard words never reaches the phrase cache"; built: D-087, plan
    007's Block I, `tts.cache_clauses`, on by default by the owner's ruling after run I). The owner: "we
    should cache everything we can, because all of it is what the agent generated and we have
    full access to it and since we would an exact match, no user will hear the info of
    another." The key holds the text sent, the language, the voice, the model, the adapter and
    the trimming; no speaking rules' version is needed, since the text sent changes with the
    rules (plan 007's Q24).
    The agent's count of 2026-11-10 on run K's dev replies: with the current spoken prompt about
    5% of model-written clauses repeat across questions, mostly short openers ("I'm sorry,",
    "Yes,", «نعم،»); under the earlier prompts 15–31%. Measured: hits, Orpheus requests per call
    minute, and the time to first audio. The cache is kept on disk, with no consent asked (the
    owner, 2026-11-10: "make it on disk without consent, because this what our agent
    produced"): it holds only the agent's own voice, so invariant 8's consent rule for call
    audio does not apply to it.
  - *No stray script in what the agent says or shows* (built: D-084, on by default since
    2026-11-11, `guard.remove_stray_script`; run A records each removal). In the owner's demo
    call of 2026-11-10 (report `0qPpF2-C`), `gpt-oss-120b` wrote «أيقونة "إ重新 كلمة مرور
    المستخدم"» where the passage holds «إعادة كلمة مرور المستخدم», and no passage of the
    snapshot holds a Chinese character. Nothing stopped it then: the output guard checks claims
    and IDs only, and the reply's language was read from its scripts but nothing was removed.
    So every text the talker writes passes a script filter before it goes anywhere: characters
    outside the scripts of the agent's languages are removed (for Ole5, Arabic and Latin, which
    carries English and the product names, besides digits and punctuation), and each removal is
    counted in the trace.
    The owner, 2026-11-10: "not only spoken, make it not appear as the llm response if we hook
    up a screen". So the filter sits where the talker's text leaves it, before the guard, and
    one filtered text feeds everything after: the voice, the captions and any text a client
    shows, the history the next turn reads, and the trace.

*Done when* simulated calls create the right tickets with zero false action claims; the
rehearsal's ticket flow passes, where an eager «نعم أرسلها» over the closing question creates the
ticket once the summary has played and a bare «نعم» there is asked again; and «أبغى موظف»
spoken over an answer stops the answer, reads the handoff back, and makes the handoff ticket
after a clear yes. *Done* on 2026-11-12 ([007](completed/007-tickets-status-handoff.md)), against
the app's mock ticket system: run A's held-out scripted calls met every target, with no claim the
record did not hold and no action without a yes in its 72 plays; the rehearsal's two steps are
end-to-end tests (`tests/ole5_voice/tickets/test_ticket_calls.py`), and the owner's ten live calls
on the dev console (D-089) made 4 of their 9 read-backs on a yes, a handoff among them, but did not
take those steps one by one, which M7's rehearsal does. The background try moved to plan 007's
Future improvements.

**M6 · Reliability and operations.**
- A time limit and a visible fallback for every part: speech-to-text, the model,
  text-to-speech, the knowledge base, the ticket system, a dropped connection, and a Groq rate
  limit (429).
- Limits per caller: one live call, a maximum call length, and a cap on ticket creates.
- Every trace records the versions of the models, prompts, flows, and word lists; Phoenix views
  for the owner's call reviews.
- How many calls one Groq key carries: the requests and audio seconds per call minute for each
  model, counted in the traces since M2, compared with the key's limits (the prototype found the
  key on Groq's on-demand tier, 400 requests a minute: Ole5-chatbot VOICE_LOG.md, 2026-10-27).
  The cap on live calls is set below that limit. Then how many calls the backend's CPU holds.
- Before callers who are not the developers use it: what they must be told, their voice going
  to Groq, an outside company, the agent's words of their calls kept on disk as audio once the
  clause cache is on (read-backs of what they asked among them, D-087), and whether the law
  asks for more (D-076, which removed Ole5's consent screen for developers).
- The deployment, moved from M2 on 2026-11-03 (the owner, plan 003): the Ole5 app on the owner's
  server behind HTTPS, the widget embedded in the website, calls from another network and from one
  that blocks UDP, and the media path recorded as a decision. It becomes a plan of its own as soon
  as the owner has access to the server, whichever milestone is then in progress, and at the latest
  in M6 ([plan 003, "The deployment, moved out of M2"](completed/003-call-listens-and-speaks.md#the-deployment-moved-out-of-m2)).
- *Library:* timeouts and spoken fallbacks per provider, 429 handling with one limiter per
  model, admission control with a busy notice, drain, usage in each call's report; the guide's
  deployment and runbook pages.

*Done when* every failure is reproduced in a test with a fake that fails, and the latency
targets hold at the cap on live calls.

**M7 · The rehearsal: the owner's script passes.**
- The owner's rehearsal of 28 Oct 2026 ([DESCRIPTION.md](../project/DESCRIPTION.md), "How
  success is measured"), on laptop speakers, a wired headset, and a Bluetooth headset, against
  the deployed backend. It holds M4's live calls, moved here when M4 closed on 2026-11-09 (the
  owner, Q1 of M5's plan), and the first hearing of the Arabic name of D-077 if no earlier call has.
- A report for the owner, every number with its source
  ([docs/project/README.md](../project/README.md)).
- *Library:* the guide completed (cookbooks with no Ole5 code, safety, troubleshooting); the
  public API reviewed, each provisional module promoted or kept; versions stay `0.x` (D-018).

*Done when* the script passes on every device and the owner accepts the report.

**M9 · The voice experience at the level of top-tier voice agents.** On 2026-11-12, with M5 done,
the owner asked to "skip M6 and M7 for now"; on 2026-11-15, after testers' calls, they asked to
take the voice experience to the level of top-tier voice agents, Arabic first, and ruled to build
it on main without a team's own agent; on 2026-11-16 they approved plan 010 as M9, with M6 and M7
after it (D-099).
- Each new question answered on its own, a search before any "I don't know", no reply said twice
  unless asked; "Ole5" and its terms said the owner's way; the silence timer and the first connect
  no longer the slow part of a call; a graceful ending.
- The call's language following the caller: any question or request in the other language
  switches it (the owner, 2026-11-16).
- STT, voice and talker candidates measured against Whisper, Orpheus and `gpt-oss-120b` on our own
  voices and calls; a half-cascade speech-to-speech trial, never the product path while every
  sentence is checked before it is spoken.
- *Library:* the fixes in the talker, the speaking rules and the session, each behind a setting
  where it moves a measured outcome; each new provider an adapter behind its port.

*Done when* plan 010's acceptance criteria hold: the long-call scenarios and run A pass, and two
tester days read by the calls report meet its targets.

## The next phase, after M7

- **Voice for a team's existing agent: the agent-led mode** (D-050). A team plugs in its
  existing LangChain or LangGraph agent, unchanged, and talks to it live. Its writes run only
  through a pause our yes rule releases, after a read-back; read-only agents come first. The
  owner chose to finish the native mode and the Ole5 Voice Agent first (2026-11-02). The
  design agreed in direction, the decisions still to take, the experiments and the sample
  agents it needs are in [agent-led-mode.md](../design/agent-led-mode.md). It gets a milestone
  and a plan once M7 is done.

## Planned later (not yet scheduled)

- The thinker: the talker hands a complex task to a slower reasoning agent in the background;
  optional and off by default (D-015), planned after M7 (the design's section 6.2 and open
  question 16). Once the agent-led mode exists, the owner decides whether it is still needed.
- For teammates: the drop-in web widget, the server configured without Python, and an agent
  plugged in over HTTP (D-014, later options).
- Typed chat in the widget (D-009: a bonus).
- Other providers, and a profile hosted in Saudi Arabia, as new adapters once the owner has other
  keys (D-004).
- Smart Turn fine-tuned on the owner's turns, then on more speakers if any become available.
- Phone calls (SIP).
- What M1 left for later, ordered by expected value:
  [plan 002's Future improvements](completed/002-golden-set-baseline.md#future-improvements)
  (first a filter for text from silence and echo, how M3 hears short Saudi words, a prompt arm
  for product terms, M3's first window, the language a live call sends and the noise on another
  day; then ticket numbers read back and compound number words).
- What M2 left for later, ordered by expected value: [plan 003's Future
  improvements](completed/003-call-listens-and-speaks.md#future-improvements) (first a caller who
  pauses mid-request, cut by Smart Turn, and what the caller waits for against what the report says,
  both M3's; then the stop's own latency, product terms and paraphrase, the first call after a
  start, traces in every recorded run, and the key's limits a minute before M6 sets its cap).
- What M3 left for later, ordered by expected value: [plan 005's Future
  improvements](completed/005-interruptions-and-cancellation.md#future-improvements) (first
  understanding the caller's request in any wording, M4's, by the owner's word; then hearing short
  command words on the fast path, by a Whisper prompt, a keyword detector, another provider or a
  better microphone; requests and repeats over a reply, the turn hold, a Bluetooth sitting, the
  agent's own words, and requests per overlap against Groq's limits a minute).
- What M4 left for later, ordered by expected value: [plan 006's Future
  improvements](completed/006-talker-and-knowledge-answers.md#future-improvements) (first a judge
  that can be trusted and better retrieval; then the Saudi register, one-word questions, the first
  audio after a search, and slow starts of the voice).
- What M5 left for later, ordered by expected value: [plan 007's Future
  improvements](completed/007-tickets-status-handoff.md#future-improvements) (first another
  speech-to-text model for Arabic, the live calls' one clear bottleneck, with the API key the
  owner will give; then the background try, the handoff's summary, the yes rule's model check in
  time, each turn's language for a call held in English, and the clause cache across callers).

## Decided

- The way of working is harness engineering: the owner steers, the agent writes everything
  ([D-001](../design/decisions.md)).
- Groq is the only provider for now, and each can be swapped later (D-004).
- Only the website, the backend, and some small services are hosted (D-005).
- For Phase 0, the only data is the owner's own voice (D-006).
- Traces go to Arize Phoenix (D-008).
- A handoff is a ticket; typed chat is a bonus (D-009).
- The Ole5 chatbot repository is a read-only source (D-010).
- Approach 3, a dedicated voice agent (D-012).
- T2 Agentic Voice: a shared library and the Ole5 app in one workspace (D-013).
- Teammates use the library from Python first (D-014).
- The thinker is optional and off by default (D-015).
- Open-source code and projects may be used (D-016).
- The owner's answers to the package design's open questions (D-018).
- Approved by the owner on 2026-11-01: the stack (D-002), the layers (D-003), SECURITY.md
  (D-007), evaluation.md (D-011), the description, the milestones M1 to M7, and the package
  design as amended (D-017).
- From M1 (plan 002): the library's `testing` layer (D-019), the checks ARCH-FACADE and
  ARCH-WORDS (D-020), the first public facades and their stability (D-021), the scorers in the
  library and the golden-set runner in the app (D-022), plain OTLP tracing to Phoenix (D-023),
  the speech-to-text noise on the dev split (D-024), and `stt.model` stays `whisper-large-v3`
  (D-025).
- From garbage collection round 1 (plan 004): the library's base error is `T2VoiceError`
  (D-026), and the checks ARCH-DEPS and DOC-SAMPLE (D-027).
- From M2 (plan 003): the settings' precedence, prefix and required `env` (D-028); serving and
  identity, with signed join tokens and the offer secret (D-029); a provider swapped by a setting
  or an adapter passed in code (D-030); the library's logging and Pipecat's loguru (D-031);
  ARCH-BAN, M2's owners and the facades `identity`, `server`, `stores` and `events` (D-032); the
  echo's shape (D-033); SECURITY.md's invariants 7 and 8 brought to the design's 8.1 (D-035);
  `t2v/1`'s data-channel messages parsed strictly (D-039); the calls on the owner's laptop for now,
  Phoenix as M1's; and the voices, `abdullah` (Saudi Arabic) and `troy` (English), with the fixed
  phrases in Saudi dialect (the owner, 2026-11-02, plan 003's Q5). The agent's, still Proposed: one
  Whisper request per user turn (D-034), the ports beyond the design's 6.1 (D-036), agent speech
  keyed on replies (D-037), a call's language fixed at join (D-038), and the requests per call
  minute measured for M6's cap (D-040).
- The next phase: voice for a team's existing agent, as a second, agent-led mode after the
  Ole5 Voice Agent, and the talker stays our own (D-050).
- From M3 (plan 005): one cancel scope per reply (D-060), the two-step interruption, its settings
  and rule (D-061), the presets' words (D-062), the filter for text from silence (D-063), the
  history of what the caller heard and the repeat (D-064), `duck`, `unduck`, a caption's `cut` and
  push-to-talk (D-065), `stt.live_language` stays `session` (D-066), the hold after Smart Turn's
  "complete" (D-067), and the registered results with `two_step` the default at a plateau
  (D-068).
- From M4 (plan 006): the knowledge base reached directly, Qdrant and T2's embedding gateway with
  one search a question, as D-002 proposed (ragent2 not used); a chat model decides the short
  overlaps the rule would let go on (D-069); a reply kept while a newer turn is open (D-070); the
  top k passages whole (D-071); each chat request's own first line (D-072); the progress line by
  the caller's wait (D-073); the Whisper prompt in live calls and `gpt-oss-120b` at medium
  (D-074); every step said, no screen relied on (D-075); no consent screen on Ole5's page (D-076);
  what the live calls changed in how the agent sounds (D-077); a failed search asked once more
  (D-078); and traces that hold what the agent said and searched for (D-079).
- From M5 (plan 007): the sealed consent objects (D-080); the yes rule refined and the guard split
  (D-081); a chat model's word on the answers the yes rule's lists leave unplaced (D-082); the test
  console (D-083); no stray script in what the talker writes (D-084); a spoken reply stops before
  its second question (D-085); each turn's language from a classifier, off until a run keeps it
  (D-086); every clause kept on disk by its exact text (D-087); the gate on every core (D-088); and
  four fixes from the owner's live calls (D-089).

## Open questions (need a human decision)

- WORKING-RULES.md: which of its rules to keep, change, or add (plan 000).
- A remote repository, so that CI runs the gate on every push (plan 000, TD-001).
- Where the contract is written: plan 000 writes the guide's `contract.md` from the design's
  section 3 before M0 closes, as the guide's index and the design's 14 and 16.1 promise (D-018,
  answer 23); or the design's section 3, accepted with D-017, stays the fixed contract and the
  page is written with the guide's README in M2 (found in plan 004's read: neither plan 000's
  criteria nor M0's lines here list the page).
- Whether T2's package index exists and can host the library (the design's open question 9;
  the owner asks T2).
- How teammates are supported: left until someone starts using the library (the design's
  open question 14).

To decide with the deployment, in its own plan (M6's section):

- How the website proves who the customer is: its server mints the join token for a logged-in
  customer, signed with a key the backend verifies, or the customer confirms a one-time code
  sent to their email. An email typed in the widget is only a contact address: a ticket made
  with it is marked unverified for support staff, and it never unlocks ticket status. The
  owner is asking the website team whether customers log in (D-018). Until then the calls get
  their tokens from the Ole5 app's access-code route (plan 003's Q4; its Q12, moved out of M2 on
  2026-11-03).
- How WebRTC media reaches the backend from customers' networks (UDP ports, a TURN service, or
  another transport), decided on the server as soon as the owner has access to it (the owner,
  2026-11-03, [plan 003](completed/003-call-listens-and-speaks.md)).

Later:

- The ticket API's gaps, asked of T2 when the real ticket system's adapter is built (M5 built a
  mock, the owner having no access: plan 007's Q2): a request ID stored on the ticket with a
  lookup by it, a list of a customer's tickets, and creation with all fields in one call.
- When Phase 0 ends, can recordings from other speakers be gathered?
