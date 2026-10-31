# Roadmap

Depth-first: each milestone produces a verified building block that the next one relies on.
When a milestone starts, it gets an execution plan in [active/](active/) (see
[README](README.md)). The owner sets the milestones and their order; the agent proposes them
from [DESCRIPTION.md](../project/DESCRIPTION.md) and records the owner's answer here. Milestones
carry no delivery dates: work moves by plan and by what is verified
([WORKING-RULES.md](../../WORKING-RULES.md)).

Milestone numbers change when the roadmap is re-planned, so code never cites them: it cites
decisions (`D-NNN`), which are permanent. Living docs cite only milestones in the table below.
`uv run poe docs` enforces both (DOC-MILESTONE).

| # | Milestone | Status |
| --- | --- | --- |
| M0 | Scaffold and harness | in progress ([000](active/000-project-scaffold.md)) |
| M1 | The measurement first: the owner's voice as a golden set | planned |
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
Phase 0 (D-006), and a handoff that is a ticket (D-009). They await the owner's approval
(plan 000).

**M0 · Scaffold and harness.**
- The project's idea in [DESCRIPTION.md](../project/DESCRIPTION.md), written with the owner.
- The layers chosen for this domain, in `harness.toml` and [ARCHITECTURE.md](../../ARCHITECTURE.md).
- The stack recorded as a decision, and the gate green locally and in CI.

*Done when* `uv run poe check` passes on the project's own package and layers, CI runs the same
gate, and the owner has approved the layers, the stack, and the first milestones after this
one.

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

*Done when* `poe eval` writes a baseline scorecard for Groq Whisper on the owner's voice, by
language and by device; the noise (the same run twice) is recorded as a decision; and the gate
passes.

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

*Done when* the targets registered in its plan hold on the golden set's overlap clips and on
M2's call recordings: a normal-volume «وقف» stops the agent within its target, the agent's own
voice does not interrupt it, and listening sounds do not; and the rehearsal's stop and repeat
steps pass in a live call.

**M4 · The talker and knowledge answers.**
- The chat-model port and its Groq adapter; the talker's prompt, its few tools, and its reply
  language per turn; `api` injects into it only the chat-model port and `actions`' tool runner,
  with a test of that wiring.
- `actions`: one knowledge search per question (T2's Qdrant and embedding gateway, D-002), a
  short spoken answer with the full steps on screen, a pre-recorded progress line while a tool
  runs, and deeper troubleshooting as a background job.
- The output guard on every sentence (invariant 2), and tool arguments parsed at the boundary
  (invariant 4).
- Simulated calls for knowledge questions in Arabic and English, each scenario repeated.

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
  (invariant 3); the handoff ticket with the call's summary (D-009); the cap on creates per
  caller, read from the outbox.
- Adversarial tests for invariants 1, 2, 3, 4, and 6, against a fake ticket system that refuses,
  times out, and replies late, with and without a lookup by request ID.

*Done when* simulated calls create the right tickets with zero false action claims; the
rehearsal's ticket flow passes, where an eager «نعم أرسلها» over the closing question creates the
ticket once the summary has played and a bare «نعم» there is asked again; and «أبغى موظف»
spoken over an answer makes a handoff ticket at once.

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

*Done when* every failure is reproduced in a test with a fake that fails, and the latency
targets hold at the cap on live calls.

**M7 · The rehearsal: the owner's script passes.**
- The owner's rehearsal of 28 Oct 2026 ([DESCRIPTION.md](../project/DESCRIPTION.md), "How
  success is measured"), on laptop speakers, a wired headset, and a Bluetooth headset, against
  the deployed backend.
- A report for the owner, every number with its source
  ([docs/project/README.md](../project/README.md)).

*Done when* the script passes on every device and the owner accepts the report.

## Planned later (not yet scheduled)

- Typed chat in the widget (D-009: a bonus).
- Other providers, and a profile hosted in Saudi Arabia, as new adapters once the owner has other
  keys (D-004).
- Smart Turn fine-tuned on the owner's turns, then on more speakers if any become available.
- Phone calls (SIP).

## Decided

- The way of working is harness engineering: the owner steers, the agent writes everything
  ([D-001](../design/decisions.md)).
- Groq is the only provider for now, and each can be swapped later (D-004).
- Only the website, the backend, and some small services are hosted (D-005).
- For Phase 0, the only data is the owner's own voice (D-006).
- Traces go to Arize Phoenix (D-008).
- A handoff is a ticket; typed chat is a bonus (D-009).
- The Ole5 chatbot repository is a read-only source (D-010).

## Open questions (need a human decision)

- Approve, change, or reject: the stack (D-002), the layers (D-003), SECURITY.md (D-007),
  evaluation.md (D-011), the description, the milestones M1 to M7, and WORKING-RULES.md
  (plan 000).

To decide before M2, which builds the call set-up and deploys it:

- How the website proves who the customer is: its server mints the join token for a logged-in
  customer, signed with a key the backend verifies, or the customer confirms a one-time code
  sent to their email. An email typed in the widget is only a contact address: a ticket made
  with it is marked unverified for support staff, and it never unlocks ticket status.
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
