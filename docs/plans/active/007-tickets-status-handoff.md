# 007 · Tickets, ticket status and handoff

Status: active · Milestone: M5 · Started: 2026-11-09

*Drafted on 2026-11-09 at the owner's word ("lets start with M5"), and approved by the owner the
same day with every recommendation, Q1 to Q9 ("The owner's decisions").*

## Goal

Let the agent do something for the caller, and never claim it did what it did not
([roadmap](../roadmap.md), M5). The caller asks for a ticket in their own words; the agent
collects the details, reads them back aloud, and creates the ticket only after a clear yes it
heard. It says the number the ticket system returned, and only that number. The caller can ask
about their own tickets, and only their own. «أبغى موظف» spoken over an answer stops the answer,
reads a handoff back and makes the handoff ticket after a yes (D-009, D-018). A write that gets no
reply is never repeated blindly.

It is library behaviour first (`@action`, the yes rule, the outbox, the record, the guard's claim
rules, the safety suite), so any team's action gets the same protection. Ole5 brings a mock ticket
system, its actions and their wording: the owner has no access to the real one, so the mock is
what the demo runs on and what proves the actions work as intended (Q2). The caller only hears the agent (D-075): a read-back is
spoken whole, and a draft card is off by default.

## What is known about the ticket system

Read on 2026-11-09 from the prototype (`Ole5-chatbot`, read only) and this repository. The owner
has no access to the real system (2026-11-09), so this is kept for whoever writes its adapter
later, and shapes the mock.

- **No documentation of the T2 Ticket API exists in any repository here, and nothing shows the
  real API was ever called.** The prototype's tests build only its mock; the four voice-lab logs
  that made tickets say "using the mock Ticket API"; all 17 rows of its `tickets.xlsx` are
  `T-MOCK-…`. Everything below is **inferred from the prototype's code**, whose comments say its
  payloads are "as the requirements show them"; that document is not in any repository.
- **Calls:** `POST <url>/TicketAPI/<operation>`, JSON, with `UserLogin` and `Password` in every
  body. `TicketCreate` (`Ticket` and `Article`; answers `TicketID`, `TicketNumber`),
  `TicketUpdate` (`TicketID`, `DynamicField`, `Article`), `TicketGet` (`TicketID`; answers a list
  whose first item holds `State` and `Queue`). A failure is a non-200, or an `Error` in a 200 body
  of a shape nobody has seen.
- **Values:** from a stand-in spreadsheet. For Ole5: queues Ole5 Support and Ole5 Technical; 11
  types; 17 subtypes tied to types; priorities Low, Medium, High, Critical; nine statuses. The
  prototype sends `State: "new"` where the sheet says "New"; whether the API cares is unknown.
- **Numbers:** the owner's three examples are 16 digits: a date, `82`, a six-digit counter
  (plan 002). Whisper got 4 of 12 such full readings right.
- **The gaps, asked of T2 and not answered:** no request ID stored on a ticket and no lookup by
  it; no list of a customer's tickets; classification is a second call after creation.
- **Who the caller is:** unresolved. The website's proof of identity waits for the deployment.
  Today every call's token carries one fixed subject from the access-code route.
- **No handoff code exists anywhere**, and nothing for tickets exists in this repository but the
  guard's reading of a spaced ticket number and the golden set's number items.

## Acceptance criteria

**The library**

- [ ] **`@action`** and its lifecycle (the design's 6.4): the draft parsed, `validate`, the caps,
  the read-back rendered from a template, the yes rule, the write as a job outside the turn, the
  outcome spoken from `done`, `failed`, `unknown` or `declined`. A stop never cuts a write in half.
- [ ] **The yes rule** (`domain`, the design's 8.3): the only thing that builds a confirmed action,
  from heard words and a read-back receipt only `voice` can build, each in `[[restricted]]`.
  Yes, no and send words in each language preset.
- [ ] **The outbox** behind a port, SQLite and in memory: a row with its request ID written before
  the write; at start, rows left "sending" are looked up or flagged, never sent again; `t2v
  outbox list`, `show` and `reconcile`.
- [ ] **The record** of completed actions (`[[restricted]]`), and **the guard's rules A and C**:
  no claim or ticket number without a record or a `reports_on` result; the talker's text after an
  action call is dropped. `reports_on` on tools.
- [ ] **The caps** per call and per caller.
- [ ] **`TextCall`** gains `during="read_back" | "closing_question"` and its expectations;
  **`ActionSafetySuite`** runs the design's 9.3 cases on any team's action; `examples/minimal`
  gets an action.
- [ ] Tools keep working as they do; the parity of a scripted call through `TextCall` and through
  the audio session holds for a call with an action.

**The Ole5 app**

- [ ] **A mock ticket system** in the app, behind one small interface (create, get, add a note,
  and a lookup by request ID that can be switched off): its tickets kept under the app's `var/`
  folder across restarts, its numbers in the real shape (16 digits: the date, `82`, a counter), and
  able to answer, refuse, time out and answer late, for the tests and for a demo. An adapter for
  the real system, when someone has access, implements the same interface in one file. No code of
  this plan can reach a real ticket system (Q2).
- [ ] **A read-only page** that lists the mock's tickets, so a demo can show what a call made.
- [ ] **`create_ticket`**, **`ticket_status`** (`reports_on`, bound to the session's caller), a
  **note on a ticket made in this call** for a correction after creation, and **the handoff**,
  each read back and confirmed like any action.
- [ ] Ole5's instructions and templates in Saudi Arabic and English, in the register the owner
  has heard; the line that says it cannot open a ticket removed.

**The adversarial tests** (GP-08), in the commit of the code each protects

- [ ] Invariant 1: a yes over the summary, an eager yes, a bare yes over the closing question, a
  tool call that claims a yes, «نعم بس غيّر العنوان».
- [ ] Invariant 2: model text claiming a ticket, a passage holding a fake number, text after the
  action call, a number never issued.
- [ ] Invariant 3: a caller naming another customer's email or number gets nothing of theirs.
- [ ] Invariant 4: a value outside a fixed set, a field named like consent.
- [ ] Invariant 6: a fake that refuses, times out and replies late, with and without a lookup; a
  restart with a row left "sending".

**The roadmap's *Done when***

- [ ] The scenario runs below: the right tickets, **zero false action claims in every run**.
- [ ] Live, against the mock ticket system, on the laptop's speakers and the wired headset: the
  rehearsal's step 6, where «نعم أرسلها» over the closing question creates the ticket once the
  summary has played and a bare «نعم» there is asked again; and step 3's «أبغى موظف» over an
  answer, which stops it, reads the handoff back and makes the ticket after a yes.
- [ ] `uv run --offline poe check` passes; the guide's `tools-and-actions.md`, `safety.md` and
  `testing.md` written, `concepts.md` and `quickstart.md` extended; the decision entries written.

**Left out**, for the owner's yes with this plan: the real ticket system's adapter and any real
ticket (Q2); how the website
proves who the caller is (the deployment); per-call state beyond the record; retries of a write
that was definitely not sent (the design: none in v1).

## Plan

1. **The base.** Branch from M4's latest work (Q1).
2. **Block 0**, by one agent, merged first: the types and ports (the draft, heard words and
   receipt, the confirmed and completed action, `Outbox`), `@action`'s declaration and its
   checks, the settings, the wire's `confirming` state, each new class in `[[restricted]]`, stubs
   that raise.
3. **Tracks A to E** ("Tracks"), each against fakes, each reviewed and merged in turn.
4. **The integration:** one scripted ticket call end to end through `TextCall` and the audio
   session; the gate.
5. **The whole-code review**, kept to what breaks a call or an invariant; the rest are debt rows.
6. **The scenario runs**, dev then held-out once ("The measurement").
7. **The live calls**, by the owner.
8. **The background try** (Q8), behind a setting, off by default, after everything above.
9. **The close:** the logs, `## Future improvements`, the plan moved, the roadmap's row, the gate.

## Tracks

Reviews follow the owner's rule of 2026-11-03: one reviewer a block, one skeptic a finding, only
what breaks a call or a contract, no hardening rounds. An invariant is a contract.

Paths are under `packages/t2-agentic-voice/src/t2_agentic_voice/` unless they start with `apps/`,
`examples/` or `tests/`. One owner per file; a file two tracks need is Block 0's and no track
changes it. Each track builds against fakes of the protocols, and deletes its
`test_stubs_track_*.py` as it fills what that file names.

Block 0 keeps: `core/` (`seal.py`, `yes_inputs.py`, `events.py`, `conversation.py`, `errors.py`,
the settings), `domain/action_declaration.py`, `domain/completed_action.py`,
`domain/talker_declaration.py`, `domain/declaration.py`, `domain/declaration_errors.py`,
`domain/ports/`, `agent/events.py`, the facades but `evals.py`, `harness.toml`,
`ARCHITECTURE.md`, `docs/generated/settings.md` and `.env.example`; and the tests
`tests/t2_agentic_voice/core/test_seals.py`, `tests/t2_agentic_voice/test_no_action_baseline.py`
with its fixture, `tests/t2_agentic_voice/domain/test_action_contracts.py` and
`test_declaration_actions.py`. Once the owner rules on the golden items (below), the change to
`apps/ole5-voice-agent/evals/allowed_in_source.toml` and its pin in
`tests/ole5_voice/evals/test_no_item_in_source.py` is Block 0's too, made before Track A merges.
A change any track needs in a Block 0 file is a Block 0 amendment, logged here.

| Track | Goal | Owns | Fills | May read |
| --- | --- | --- | --- | --- |
| A | The yes rule, the flow's states, the yes and send words, the guard's rule A | `domain/yes_rule.py`, `domain/yes_words.py`, `domain/action_flow.py`, `domain/claims.py`, `domain/action_lines.py`, `domain/guard.py`, `domain/fixed_phrases.py`, `domain/presets.py`; `tests/t2_agentic_voice/domain/test_stubs_track_a.py`, `test_guard.py`, `test_fixed_phrases.py`, `test_fixed_lines_words.py`, and new `test_yes_rule.py`, `test_yes_words.py`, `test_action_flow.py`, `test_claims.py` | `decide`, `consent_words`, `advance`, `check_claims`, `default_claims`, `default_action_lines`; the yes and send presets (the owner's word first, below) | Block 0's types; `domain/words.py` and `domain/interruptions.py` (unchanged, D-080) |
| B | `@action`'s lifecycle, the outbox, the jobs, the record, the caps, the error meanings, rule C on the talker's turn, `t2v outbox` | `actions/action_runner.py`, `actions/record.py`, `actions/memory_outbox.py`, `actions/runner.py`, `actions/tools.py`, `actions/action.py`, `actions/action_checks.py`, `actions/knowledge.py`, `adapters/outbox.py`, `agent/turn.py`, `agent/tool_calls.py`, `agent/context.py`, `agent/prompt.py`, `agent/talker.py`, `api/providers.py`, `api/runtime.py`, `api/cli.py`, new `actions/` and `api/` modules; `tests/t2_agentic_voice/actions/`, `tests/t2_agentic_voice/adapters/test_outbox.py`, `tests/t2_agentic_voice/agent/`, `tests/t2_agentic_voice/api/` | `ActionRunner.propose`, `run`, `reconcile`; `ActionRecord.add`, `entries`; `MemoryOutbox`, `SqliteOutbox`; `CallContext.past_actions`; rendering the read-back and the outcome lines from `Say` and `ReadBack` | Block 0's types; the `ActionJobs` and `Outbox` ports; `domain/claims.py`'s signature against a fake, never Track A's unfinished code |
| C | The confirming state, the read-back and its receipt, the heard words routed to the yes rule, the outcome spoken at a turn boundary | `voice/session/read_back.py`, `call.py`, `interrupter.py`, `overlap.py`, `talking.py`, `talker_play.py`, `speaker.py`, `playback.py`, `open_reply.py`, `turn_book.py`, `history.py`, `heard.py`, `io.py`, `session_events.py`, `voice/calls.py`; `tests/t2_agentic_voice/voice/` | The read-back (`ReadBackRequested`), the receipt's preconditions before `played_receipt`, the turn routing, `Speaker.show_state`'s `confirming`, the outcome's flush; `Calls` takes and passes `action_jobs` | Block 0's types; the talker through its events, the yes rule through `decide`'s signature, the job through the `ActionJobs` port |
| D | `TextCall`'s additions, `ActionSafetySuite`, the example's action | `testing/text_call.py`, `testing/text_side.py`, `testing/text_turn.py`, `testing/text_watch.py`, `testing/turn_data.py`, `testing/llm_fakes.py`, `testing/action_safety.py`, `evals.py`; `examples/minimal/`, `tests/minimal_example/`, `tests/t2_agentic_voice/testing/`, `tests/t2_agentic_voice/test_facades.py` | `during="read_back"` and `"closing_question"`, the expectations, the armed fault for a read-back, `MemoryOutbox` in `TextCall`, `violations` with rules A and C, the safety suite's cases; `TextCall` passes `action_jobs` as `Calls` does | Block 0's types; the session through `Playback`'s read of the read-back's parts, `Action.replaced`; nothing of the other tracks' unfinished code |
| E | The mock ticket system and its page, the actions, the status tool, the handoff, the instructions, the scenarios | `apps/ole5-voice-agent/`, `tests/ole5_voice/` | The app's own: `@action`s over the mock, `ticket_status` with `reports_on`, the token's `customer_email` attribute | Only the library's public API |

**What Block 0 settled**, beyond the design, and which the tracks follow:

- The yes rule takes no draft: `ReadBackReceipt` holds the action and the draft as JSON text, and
  the `ConfirmedAction` copies them, so a receipt for one draft cannot confirm another (D-080).
- `HeardWords.speech_at` is when the caller began speaking; `at` remains when the transcript
  arrived. The receipt's `question_ended_at` is the question's last `ClausePlayed`, no 300 ms
  tail, None until it plays; the session builds the receipt when the yes rule is called, so a
  verdict landing late can deny it.
- A template is a pair (summary, closing question) for each language, and a key serves its tag,
  then its primary code. `show_draft` is False (D-075).
- `Literal` fields a read-back names need `Spoken` labels, one per value; a language with no
  label says the value as written.
- No `deps`: a backend is reached by a closure, as `knowledge_tool` does; `ActionSafetySuite`
  takes `make_agent()`.
- Caps count `ConfirmedAction`s, never proposals; `ReadBack.max_attempts`, `max_per_call` and
  `timeout_s` stay on the action; `limits.actions_per_caller_per_day` is the only group key the
  actions added beyond `words.yes`, `words.send` and `guard.claims`.
- A tool's `reports_on` names only the agent's own actions. `ActionContext.consent` and
  `CallContext.record` are plain views, which prove nothing.
- `ReadBackPlan.declined` is the action's `declined` line, or the library's, rendered by Track
  B's `propose` beside `asked_again`; Track C's session speaks it when the read-back ends with
  no yes and no talker turn answers it. `DeclinedAction.kind` (`no`, `correction`, `unclear`)
  tells the talker a no from a correction.

## The measurement, registered before any result

- **Data:** scenarios in `apps/ole5-voice-agent/evals/actions/`, Saudi, MSA and English, split by
  scenario into dev and held-out before any run: a plain ticket, an eager yes, a bare yes, a yes
  over the summary, a correction inside the read-back, a no, a mumble, a refusal, a timeout with
  and without a lookup, status of one's own tickets, a request for another's, a handoff over an
  answer, a handoff asked for by mistake, and a passage carrying a fake number.
- **Run A:** `gpt-oss-120b` at medium, against the mock ticket system, each scenario three
  times, the caller's lines scripted (Q9).
- **Hard constraint:** no unrecorded claim and no action without a yes, in **every** run. One
  violation fails the run, whatever else it scored.
- **Targets, on held-out:** the right action taken or rightly not taken ≥ 0.95; the ticket's type
  right ≥ 0.85; the summary judged faithful ≥ 0.85; the reply's language right ≥ 0.90. M4's
  held-out showed how far targets can be from results, and held-out is read once, so a miss is
  recorded and goes to Future improvements, not re-run.
- **The judge** of a summary is a model, checked first on a sample by an agent blind to its
  verdicts, as in plan 006; a failed check marks that score unverified.
- **Cost:** about $1, capped at $1.50 (Q9); M7 takes up `simulate`. No default moves except by a registered keep rule
  (GP-18).

## Progress log

- 2026-11-09: Drafted, and approved (Q1 to Q9). Drafted from the roadmap's M5, the design's 4.4, 6.3, 6.4 and 8, `docs/SECURITY.md`,
  and a read of the prototype's ticket code. Nothing built.
- 2026-11-10: Block 0 built, on `plan-007-integration`: the sealed consent types (`HeardWords`,
  moved to `core`, `ReadBackReceipt`, `ConfirmedAction`, `CompletedAction`, D-080), the yes rule's
  signature, the flow's states, the `Outbox` and `ActionJobs` ports, `@action`, `ReadBack`, `Say`,
  `Claims`, `Spoken`, `ActionContext`, `ActionRejected`, `ActionNotSent`, `reports_on`, the
  settings (`words.yes`, `words.send`, `guard.claims`, `limits.actions_per_caller_per_day`), the
  actions' events, and stubs naming their tracks. The wire's `confirming` state was already there
  (`CallState`, the client, the widget, the fixture); only its comment changed. The Tracks table
  now names each track's files.

## Decision log

- 2026-11-10: Block 0 amendment, from its review: nothing that reached the session or the talker
  carried an action's `declined` line. After the last ask-again with nothing heard there is no
  talker turn (a `TalkerTurn` needs words) and `voice` cannot render a template, so the team's
  `declined` would never be spoken; and a `DeclinedAction` could not say a no from a
  correction. `ReadBackPlan` gains `declined` and `DeclinedAction` gains `kind` (the Tracks
  section). `domain/action_lines.py` is listed as Track A's, but the change is Block 0's. Who
  speaks after a plain no is still the owner's to rule; both fields serve either ruling.
- 2026-11-10: Block 0's choices where the design and the code disagreed are in the Tracks
  section and D-080. Left to the owner, below: the four golden items and how the read-back
  behaves over a stop word, a repeat and a plain no.
- 2026-11-09: After approving the plan, the owner ruled out the real ticket system: no access.
  The adapter on the inferred contract is dropped, and the mock becomes what the demo runs on,
  with a page to show its tickets. Nothing is lost for later: the interface is the seam.
- 2026-11-09: Written shorter than plan 006, whose length came from what was measured along the
  way. The draft is proposed as tracks because `domain`, `actions`, `voice` and the app divide
  cleanly around the ports Block 0 lays down.

## The owner's decisions

Each was put with the agent's recommendation; the owner took every one.

- 2026-11-09, on starting: "I won't take the calls now, but since M4 is essentially done, lets
  start with M5"; "If it is necessary to close and merge M4 first tell me"; to the draft and its
  nine questions: "Approve all"; then, on the ticket system: "I don't have aceess to the real
  ticket system, so lets build a mock one for a demo sake and to prove that actions work as
  intended in the package and agent."

- **Q1. M4 and the base of this work.** *Settled 2026-11-09: (a).* Not necessary: M5 can branch from M4's branch. Options:
  (a) close M4 first, its live calls moved to M7's rehearsal and its missed targets recorded, and
  merge it to `main`; (b) leave M4 open and branch from it. **The agent recommended (a).**
- **Q2. The real ticket system.** *Settled 2026-11-09: a mock only, by the owner's word after the
  draft.* The draft offered (a) building on the inferred contract and a fake, asking T2 for the
  documentation, a test environment and the three gaps, and (b) waiting for T2. The owner has no
  access: the mock is what the demo runs on and what proves the actions, and no real adapter is
  written here.
- **Q3. Who the caller is, for the owner's tests.** *Settled 2026-11-09: (a).* Every token carries one fixed subject today.
  Options: (a) the server maps it to one demo customer's email, a default the owner may change in
  a setting, which nothing said in the call can change; (b) wait for the website's answer. **The agent recommended (a).** The
  real mapping comes with the deployment.
- **Q4. What ticket status can see.** *Settled 2026-11-09: (a).* The API has no list by customer. Options: (a) the outbox is
  the list: only tickets made through the agent, each read with `TicketGet`, and the agent says
  so when asked; (b) wait for T2. **The agent recommended (a).** A number the caller says is only
  ever matched among their own tickets, and read back first (plan 002's finding).
- **Q5. What the caller is asked.** *Settled 2026-11-09: (a).* The prototype asked for seven fields. Options: (a) only what a
  caller can answer: what is wrong, and how urgent if they say so. The model writes a summary of
  at most 200 characters and picks one of the 11 types, both read back; the priority defaults to
  Medium; the queue follows the type; subtype and reason are left to support staff, so no second
  call exists to fail; (b) all seven, as the prototype did. **The agent recommended (a).**
- **Q6. Saying a ticket number.** *Settled 2026-11-09: (a).* Sixteen digits take about ten seconds. Options: (a) the whole
  number digit by digit in groups when the ticket is made, again on request; in status, its last
  four digits; (b) always whole; (c) always the last four. **The agent recommended (a).**
- **Q7. What a handoff ticket holds.** *Settled 2026-11-09: (a).* Options: (a) a summary read back to the caller, with what
  both sides said in the call attached for support staff; (b) the summary alone. **The agent
  recommends (a):** staff should not have to ask again.
- **Q8. The background try** ([background-tools.md](../../design/background-tools.md)). *Settled 2026-11-09: (a).* A slow tool
  runs while the talker stays free, and the talker says what it is about to look up. Options:
  (a) last in this plan, behind a setting, off by default, judged on a fake slow tool and the
  owner's ear; (b) its own plan after M5. **The agent recommended (a)**, as the owner asked on
  2026-11-08, and it is dropped first if the rest runs long.
- **Q9. The scenario runs.** *Settled 2026-11-09: (b).* Options: (a) three repeats a scenario with the model scripted by
  each scenario's lines, plus the design's `simulate` with a model playing the caller, cap $3;
  (b) scripted only, about $1, `simulate` left to M7. **The agent recommended (b):** the scripted
  run holds the hard constraint, and the owner asked to skip runs that are not important.

## What the owner does

- Answer Q1 to Q9, and approve the plan (done 2026-11-09).
- Rule on the yes words: «نعم», «ايه», «ايوه» and "yeah" are whole golden items (y04, b02, b05,
  m15, n41, b10), and the golden set's source check fails once a preset holds them unless
  `allowed_in_source.toml` lists them, as it did for M3's lists (D-062). Track A waits on this.
- Rule on the read-back's edges, each with the agent's recommendation: a stop or pause word over
  the read-back (no receipt, confirming ends, the talker keeps the draft); a repeat request
  while confirming (say the read-back again and earn a new receipt); who speaks after a plain no
  (the `declined` template, and the talker for a correction); and what the caller hears while
  the write runs (nothing yet; a progress line, if the owner wants one).
- Hold the live calls, against the mock ticket system, on the laptop's speakers and the wired
  headset (about 20 minutes).
