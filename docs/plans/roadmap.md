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
| M2 | A call that listens and speaks, deployed | planned |
| M3 | Interruptions and cancellation | planned |
| M4 | The talker and knowledge answers | planned |
| M5 | Tickets, ticket status, and handoff | planned |
| M6 | Reliability and operations | planned |
| M7 | The rehearsal: the owner's script passes | planned |

Status is `planned`, `in progress` (with links to its active plans) or `done` (with links to
its completed plans). Between milestones, [garbage-collection rounds](../harness/garbage-collection.md)
keep entropy down; they and other side work get a plan but no row. While such a plan is active,
it is linked from the line below (DOC-PLAN fails on an active plan the roadmap does not link),
and the link is removed when it completes.

Outside the milestones: none active.

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

**M2 · A call that listens and speaks, deployed.**
- The web widget: start and end a call, the microphone, playback, captions, the Stop button
  and Esc.
- `api`: the join token (invariant 7), the offer route (`voice` answers the offer), health.
- `voice`: the Pipecat pipeline over its peer-to-peer WebRTC transport, Silero VAD, and Smart
  Turn, with our own processors calling the speech-to-text and text-to-speech ports (Groq
  Orpheus, an Arabic and an English voice), and `domain`'s rules for speaking numbers and ticket
  IDs. Pipecat's loguru routed through `core/logging.py`, given to `core` in `[[owners]]` with a
  decision, and a test that a debug line holding a transcript does not reach the output
  (invariant 8).
- No talker yet: the agent says back what it heard. One trace per turn in Phoenix, with the
  requests and audio seconds each Groq model uses per call minute.
- Deployed on the owner's host behind HTTPS, the widget embedded in the website, and a call
  held from another network (a phone hotspot) and from one that blocks UDP. Before M2 closes,
  the media path is recorded as a decision: UDP ports opened on the backend, a TURN service run
  as a small service, or another transport.
- The owner's calls through the widget recorded with the recording setting on (invariant 8),
  each keeping the caller's track and the agent's playback timeline, so M3's targets are also
  checked on audio that came through WebRTC.
- *Library:* everything above that is not Ole5's: Pipecat inside `voice` (the transport,
  VAD, Smart Turn, the speech bridges), the `TextToSpeech` port and the Orpheus
  adapter, the call session in echo mode, signed single-use join tokens, the router and
  `serve()`, the reference browser client and its protocol, the settings with a required `env`
  and their generated reference; `examples/minimal` as an echo agent; the guide's
  quickstart, serving, browser-client, settings, tracing and data pages. The widget is
  Ole5's, built on the reference client.

*Done when* the owner holds a call in Chrome on laptop speakers and on a headset, locally and
from another network to the deployed backend, and hears each turn back; end-of-turn cut-offs
and the time of each step are measured on the golden set; and requests per call minute for each
Groq model are recorded.

**M3 · Interruptions and cancellation.**
- The cancel scope of every turn: a stop, a correction, or new words cancel the model, the
  speech, and read-only lookups at once, and the screen shows it.
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

*Done when* the targets registered in its plan hold on the golden set's overlap clips and on
M2's call recordings: a normal-volume «وقف» stops the agent within its target, the agent's own
voice does not interrupt it, and listening sounds do not; and the rehearsal's stop and repeat
steps pass in a live call.

**M4 · The talker and knowledge answers.**
- The chat-model port and its Groq adapter; the talker's prompt, its few tools, and its reply
  language per turn; `api` injects into it only the chat-model port and `actions`' tool runner,
  with a test of that wiring.
- `actions`: one knowledge search per question (T2's Qdrant and embedding gateway, D-002), a
  short spoken answer with the full steps on screen, and a pre-recorded progress line while a
  tool runs. Deeper troubleshooting in the background moved to the thinker, after M7 (D-018).
- The output guard on every sentence (invariant 2), and tool arguments parsed at the boundary
  (invariant 4).
- Simulated calls for knowledge questions in Arabic and English, each scenario repeated.
- *Library:* the `ChatModel` port and the Groq chat adapter, the talker loop, `@tool` with
  its context and bound parameters, the output guard's ID rule, progress lines, a knowledge
  protocol and helper tool, the text-call testing kit and its fakes, `t2v check`, and the
  latency measurement; the Qdrant adapter and the prompts stay Ole5's.

*Done when* retrieval (the right passage in the top 5) and answer correctness are measured; the
time to the first useful audio meets a target registered in its plan before any run; and the
rehearsal's password, archiving, and English questions pass.

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

*Done when* simulated calls create the right tickets with zero false action claims; the
rehearsal's ticket flow passes, where an eager «نعم أرسلها» over the closing question creates the
ticket once the summary has played and a bare «نعم» there is asked again; and «أبغى موظف»
spoken over an answer stops the answer, reads the handoff back, and makes the handoff ticket
after a clear yes.

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
- *Library:* timeouts and spoken fallbacks per provider, 429 handling with one limiter per
  model, admission control with a busy notice, drain, usage in each call's report; the guide's
  deployment and runbook pages.

*Done when* every failure is reproduced in a test with a fake that fails, and the latency
targets hold at the cap on live calls.

**M7 · The rehearsal: the owner's script passes.**
- The owner's rehearsal of 28 Oct 2026 ([DESCRIPTION.md](../project/DESCRIPTION.md), "How
  success is measured"), on laptop speakers, a wired headset, and a Bluetooth headset, against
  the deployed backend.
- A report for the owner, every number with its source
  ([docs/project/README.md](../project/README.md)).
- *Library:* the guide completed (cookbooks with no Ole5 code, safety, troubleshooting); the
  public API reviewed, each provisional module promoted or kept; versions stay `0.x` (D-018).

*Done when* the script passes on every device and the owner accepts the report.

## Planned later (not yet scheduled)

- The thinker: the talker hands a complex task to a slower reasoning agent in the background;
  optional and off by default (D-015), planned after M7 (the design's section 6.2 and open
  question 16).
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

## Open questions (need a human decision)

- WORKING-RULES.md: which of its rules to keep, change, or add (plan 000).
- A remote repository, so that CI runs the gate on every push (plan 000, TD-001).
- Whether T2's package index exists and can host the library (the design's open question 9;
  the owner asks T2).
- How teammates are supported: left until someone starts using the library (the design's
  open question 14).

To decide before M2, which builds the call set-up and deploys it:

- How the website proves who the customer is: its server mints the join token for a logged-in
  customer, signed with a key the backend verifies, or the customer confirms a one-time code
  sent to their email. An email typed in the widget is only a contact address: a ticket made
  with it is marked unverified for support staff, and it never unlocks ticket status. The
  owner is asking the website team whether customers log in (D-018).
- Where the backend and Phoenix run, and how WebRTC media reaches the backend from customers'
  networks (UDP ports, a TURN service, or another transport).
- The voices: which Groq Orpheus Saudi Arabic voice and which English voice, and the register
  (Saudi dialect or plain MSA).

Later:

- How the knowledge base is reached (M4): the agent recommends Qdrant and the embedding gateway
  directly, with one embedding and one search per question, since the prototype measured
  ragent2 at 20–45 s per answerable search (Ole5-chatbot VOICE_LOG.md, D28). ragent2 is used
  only if the owner chooses it.
- The ticket API's gaps, asked of T2 now so that M5's design follows the answer: a request ID
  stored on the ticket with a lookup by it, a list of a customer's tickets, and creation with all
  fields in one call.
- When Phase 0 ends, can recordings from other speakers be gathered?
