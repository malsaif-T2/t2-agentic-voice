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
- [x] `uv run --offline poe check` passes; the guide's `tools-and-actions.md`, `safety.md` and
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
| A | The yes rule, the flow's states, the yes and send words, the guard's rule A | `domain/yes_rule.py`, `domain/yes_words.py`, `domain/action_flow.py`, `domain/claims.py`, `domain/action_lines.py`, `domain/guard.py`, new `domain/guard_ids.py` (rule B, moved out of `guard.py`), `domain/fixed_phrases.py`, `domain/presets.py`; `tests/t2_agentic_voice/domain/test_stubs_track_a.py`, `test_guard.py`, `test_fixed_phrases.py`, `test_fixed_lines_words.py`, and new `test_yes_rule.py`, `test_yes_words.py`, `test_action_flow.py`, `test_claims.py`, `test_action_lines.py` | `decide`, `consent_words`, `advance`, `check_claims`, `default_claims`, `default_action_lines` (`sending` among its Saudi, MSA and English texts); the yes and send presets (the owner's word first, below) | Block 0's types; `domain/words.py` and `domain/interruptions.py` (unchanged, D-080) |
| B | `@action`'s lifecycle, the outbox, the jobs, the record, the caps, the error meanings, rule C on the talker's turn, `t2v outbox` | `actions/action_runner.py`, `actions/record.py`, `actions/memory_outbox.py`, `actions/runner.py`, `actions/tools.py`, `actions/action.py`, `actions/action_checks.py`, `actions/knowledge.py`, `adapters/outbox.py`, `agent/turn.py`, `agent/tool_calls.py`, `agent/context.py`, `agent/prompt.py`, `agent/talker.py`, `api/providers.py`, `api/runtime.py`, `api/cli.py`, new `actions/` and `api/` modules; `tests/t2_agentic_voice/actions/`, `tests/t2_agentic_voice/adapters/test_outbox.py`, `tests/t2_agentic_voice/agent/`, `tests/t2_agentic_voice/api/` | `ActionRunner.propose`, `run`, `reconcile`; `ActionRecord.add`, `entries`; `MemoryOutbox`, `SqliteOutbox`; `CallContext.past_actions`; rendering the read-back, `sending` and the outcome lines from `Say` and `ReadBack` in `propose` | Block 0's types; the `ActionJobs` and `Outbox` ports; `domain/claims.py`'s signature against a fake, never Track A's unfinished code |
| C | The confirming state, the read-back and its receipt, the heard words routed to the yes rule, the outcome spoken at a turn boundary | `voice/session/read_back.py`, `call.py`, `interrupter.py`, `overlap.py`, `talking.py`, `talker_play.py`, `speaker.py`, `playback.py`, `open_reply.py`, `turn_book.py`, `history.py`, `heard.py`, `io.py`, `session_events.py`, `voice/calls.py`; `tests/t2_agentic_voice/voice/` | The read-back (`ReadBackRequested`), the receipt's preconditions before `played_receipt`, the turn routing, `Speaker.show_state`'s `confirming`, `ReadBackPlan.sending` spoken once the `ConfirmedAction` is issued, the outcome's flush; `Calls` takes and passes `action_jobs` | Block 0's types; the talker through its events, the yes rule through `decide`'s signature, the job through the `ActionJobs` port |
| D | `TextCall`'s additions, `ActionSafetySuite`, the example's action | `testing/text_call.py`, `testing/text_side.py`, `testing/text_turn.py`, `testing/text_watch.py`, `testing/turn_data.py`, `testing/llm_fakes.py`, `testing/action_safety.py`, `evals.py`; `examples/minimal/`, `tests/minimal_example/`, `tests/t2_agentic_voice/testing/`, `tests/t2_agentic_voice/test_facades.py` | `during="read_back"` and `"closing_question"`, the expectations, the armed fault for a read-back, `MemoryOutbox` in `TextCall`, `violations` with rules A and C, the safety suite's cases; `TextCall` passes `action_jobs` as `Calls` does | Block 0's types; the session through `Playback`'s read of the read-back's parts, `Action.replaced`; nothing of the other tracks' unfinished code |
| E | The mock ticket system and its page, the actions, the status tool, the handoff, the instructions, the scenarios | `apps/ole5-voice-agent/`, `tests/ole5_voice/` | The app's own: `@action`s over the mock, `ticket_status` with `reports_on`, the token's `customer_email` attribute | Only the library's public API |

The modules the tracks added in their own folders: B's `actions/action_job.py`,
`actions/action_writes.py`, `actions/spoken_lines.py`, `agent/speech_guard.py` and
`api/actions.py`; C's `voice/session/yes_turns.py`, `action_job.py`, `talker_progress.py` and
`overlap_follow.py` (the last two split out for size); D's `testing/text_actions.py`,
`text_checks.py`, `text_moments.py`, `text_read_back.py`, `text_reads.py`, `action_faults.py`,
`action_scenes.py` and `examples/minimal/`'s `callback.py`. The integration changed files no track
owns, or another track's after its merge: `core/conversation.py` (Block 0's), `agent/context.py`,
`api/runtime.py`, `testing/audio_call.py`, `testing/text_call.py`, `testing/text_watch.py`,
`voice/protocol.py`, `voice/session/__init__.py`, `read_back.py`, `interrupter.py`,
`talker_play.py` and `docs/guide/serving.md` (the Progress log, 2026-11-10).

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
  no yes and no talker turn answers it. `DeclinedAction.kind` (`no`, `correction`, `stopped`,
  `unclear`) tells the talker a no from a correction and from a stop. `stopped` is the
  integration's amendment, for the owner's stop ruling: a stop or pause word over the read-back
  (either part, or a line that asked again), or said whole while confirming; the talker's note
  (`agent/context.py`'s `DECLINED`) tells it nothing was done and to ask what to change, keeping
  the draft. Real words over the summary stay a `correction`.
- `@action` takes `sending`, a `Say` checked as the outcome lines are (its fields the draft's,
  every language covered), and `ActionLines` gains the library's `sending`.
  `ReadBackPlan.sending` is required: Track B's `propose` renders it from the action's
  `sending`, or the library's line; Track C's session speaks it once the yes rule issues the
  `ConfirmedAction`, before the job's outcome. A fixed line, never a claim.
- **The flow's events** (Track A's amendment). `FlowEvent` gained `stop`, `repeat`,
  `asked_again` and `unclear`. From `confirming`, the yes rule's `yes` goes to `confirmed`; `no`,
  `correction`, `stop` and `unclear` (no clear answer after the last ask-again) go to
  `declined`, nothing sent and the draft left with the talker; `repeat` and `asked_again` stay
  `confirming`, so only a yes to the new reading counts. `confirmed` with `refused` (the outbox
  row not written, nothing sent) goes to `failed`. `sending` takes no stop, and `advance` refuses
  any move its table lacks with a ValueError. No runtime code calls `advance` yet (TD-141).
- **The guard's split** (Track A's amendment). Rule B moved to `domain/guard_ids.py`
  (`check_ids`, and `guard_form`, the normalized form rule A matches on too); `domain/guard.py`
  re-exports it and adds `check_clause`, rule A then rule B, its `GuardVerdict` carrying the
  reason (`unsupported_claim` or `unsupported_id`), as `ClauseBlocked` and, since the
  integration, `GuardBlocked` do. The talker's turn composes the same two rules in
  `agent/speech_guard.py`, and `TextCall` in `testing/text_checks.py`, each from `check_claims`
  and `check_ids`; only `check_clause`'s tests call it (TD-141).
- **The runner** (Track B, its review, the integration). One `ActionRunner` per agent serves
  every call (`CallSetup.action_jobs`), each call's `ActionRecord` kept by its call ID
  (`record`, and `forget` when the call ends). It keeps Block 0's `record=`, which `TextCall`
  passes so that every job fills that call's one record. The runtime builds it with no `emit`:
  the session alone sends `ActionCompleted` and `ActionUnconfirmed`, from the `ActionOutcome` it
  is returned (`voice` builds the events, core/events.py), so an observer hears each outcome
  once; `TextCall` and `AudioCall` build theirs the same way, `AudioCall` over a `MemoryOutbox`
  (its `outbox=`) for an agent with actions. `VoiceCalls` takes `action_jobs` and the runtime
  passes it.
- **Rule A's scope** (the integration). Rule A runs only for an agent that declares an action,
  as every rule added for actions does (`test_no_action_baseline.py`); `TextCall.violations`
  runs rules A and C and the yes-rule check on the same terms, so the measured runs of an agent
  with none (Ole5's talker with no tickets, in runs K, S and T) do not move.

**Block F, the yes rule's model check** (the owner's ruling of 2026-11-10, "The owner's
decisions"), built after the integration and before the guide, by one builder for the library
and one for Ole5, each block reviewed by the owner's rule. It amends invariant 1: a chat model
may judge a yes in words no list holds, within rails the yes rule keeps.

- **The lists first, unchanged.** `decide` answers as before whatever its lists place: a forged
  or untimed answer, speech begun before the summary's last clause played, nothing heard,
  fillers alone, a yes beside a no, a yes with a question mark, a listed yes
  (with a listed send word when said before the closing question ended), a listed no. None of
  these asks a model.
- **The rest, for an agent that asks** (`VoiceAgent.ask_on_unlisted_answers`, False by default
  as `ask_on_uncertain_overlaps` is, D-069's precedent, so no agent that does not ask and no
  existing test script sees a new request; Ole5 sets it): a turn holding a word on none of the
  lists, until now a correction, is put to a chat model. The request (new `domain/consent_check.py`,
  pure, as `domain/uncertain_overlaps.py` is: the prompt, `openai/gpt-oss-120b` at low effort,
  temperature 0, at most 256 output tokens, a timeout of 1.5 s on the call's clock) holds, as
  data, the read-back's summary and closing question as the caller heard them and the caller's
  heard words, never a tool's result or the talker's text, and asks for one word: `send` (an
  explicit go-ahead to send: "go for it", «يلا أرسلها», «توكل»), `yes` (agreement only: "sure",
  «اكيد»), `no`, `change` ("yes, but change ..." among them) or `unclear` (a sound, anything
  else, and the agent's own read-back or question heard back, so its echo never sends).
- **The model's word, decided by the yes rule** (a pure function beside `decide`, still the only
  builder of a `ConfirmedAction`). Its `send` or `yes` is a yes only when the words hold no
  listed no word and no question mark (else asked again), no change marker (a new list a
  language in `domain/yes_words.py`: "but", "change", "instead", «بس», «لكن», «غيّر» among them;
  else a correction), and the receipt built when the turn began still stands. Said once the
  closing question ended, both confirm; said over it, only `send` (or a listed send word) does,
  and `yes` alone is asked again, as a bare «نعم» is (the owner's second ruling). `no` is a no,
  `change` a correction, and `unclear`, any other answer, a failure and a timeout are asked
  again: a model's word never confirms what the lists refused, and an error never confirms.
- **In the session** (new `voice/session/yes_ask.py`, shaped as `overlap_ask.py`): a task of a
  cancel scope of its own, holding no lock; its verdict applied as a session step only while the
  same read-back is current and no newer turn answered it; a stop or the call's end cancels it
  and decides nothing; its usage counted; logged by its outcome's kind alone.
- **What observers see:** `ConfirmationAnswered.by`, `words` or `model`.
- **Tests and runs:** the rails each tested (GP-08); `TextCall` and Ole5's end-to-end calls with
  unlisted yes words, "yes, but change", an unlisted hesitation, and a failing check; run A gains
  scenarios for those before any run, its oracle talker answering the check and its estimate
  counting it.
- **Docs:** `docs/SECURITY.md`'s invariant 1, the design's 8.3, D-082.
- **Part 2, a send word said alone** (the owner's third ruling, "The owner's decisions"):
  «أرسلها», «توكل», "go ahead" or "send it" with no yes word, which the lists ask again, is put
  to the model too, as send words among fillers are, under the same rails; the echo rail (the
  words a run of one of the read-back's lines) holds only for speech begun while one of those
  lines was playing, since speech begun when the agent was silent cannot be its echo. An agent
  that does not ask is unchanged, and the rehearsal's step 6 («نعم أرسلها», listed) asks
  nothing.

## The measurement, registered before any result

- **Data:** scenarios in `apps/ole5-voice-agent/evals/actions/`, Saudi, MSA and English, split by
  scenario into dev and held-out before any run: a plain ticket, an eager yes, a bare yes, a yes
  over the summary, a correction inside the read-back, a no, a mumble, a refusal, a timeout with
  and without a lookup, status of one's own tickets, a request for another's, a handoff over an
  answer, a handoff asked for by mistake, and a passage carrying a fake number; and, added with
  Block F before any run, four the yes rule's lists leave unplaced (D-082): an unlisted yes once
  the closing question ended, an unlisted go-ahead over it, a yes with a change, and a
  hesitation in an unlisted spelling.
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
- **Cost:** about $1 (Q9), a run capped at $10 (the owner's, 2026-11-10, raised from $1.50 once
  Block F's scenarios passed it; "The owner's decisions"); M7 takes up `simulate`. No default moves except by a registered keep rule
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
- 2026-11-10: Tracks A to E built, each on its own branch against fakes, reviewed by the owner's
  rule of 2026-11-03 (one reviewer, one skeptic a finding), and merged in turn into
  `plan-007-integration`:
  - **A** (merge `abe3f8c`): `decide`, `consent_words` and the presets' yes, send, no and filler
    words; the flow's moves; rule A (`check_claims`, `default_claims`) and `check_clause`, rule B
    moved to `guard_ids.py`; the library's action lines (`sending`, `failed`, `unknown`,
    `declined`, `asked_again`) in Saudi, MSA and English. Its review confirmed no finding.
  - **B** (`efe74d5`): the runner's `propose`, `run` and `reconcile`, the record, `MemoryOutbox`
    and `SqliteOutbox`, the read-back's lines rendered, the talker's side (rules A and C in its
    turn, one action per request, the declined notes), `past_actions`, the composition and
    `t2v outbox`. Its review confirmed two findings: the runner had dropped Block 0's `record=`,
    which `TextCall` passes, and each outcome's event reached the observers twice, from the
    runner and from the session. Fixed in `9be6739`: `record=` kept, and the runtime's runner
    built with no `emit`.
  - **C** (`402ff77`): the read-back in the session and its receipt, what is heard over it, the
    yes rule's routing, the job and its outcome said at a turn boundary, `VoiceCalls`'
    `action_jobs`. Its review refuted one finding, the agent's own voice over the closing
    question reaching the yes rule: no shipped line is made only of yes, send and filler words,
    and plans 003 and 005 measured no echo of the agent opening an overlap.
  - **D** (`1862a60`): `TextCall`'s read-back turns, its fault, expectations and checks;
    `ActionSafetySuite`; the minimal example's `request_callback`. Its review confirmed one
    finding, its action tests relying on the session ignoring `ReadBackRequested`, fixed in
    `b765d0f` (their scripted talker keeps the plan from the session, so they test `TextCall`'s
    reads apart from the session's confirming). It refuted one: the suite's "no lookup" case
    installs a lookup that finds nothing, which ends `unknown` as no lookup does (TD-138).
  - **E** (`b5acd77`): the mock ticket system and its page, the demo customer on the token,
    `create_ticket`, `add_ticket_note`, `hand_off` and `ticket_status`, the instructions, and 30
    scenarios (`a01` to `a30`), split before any run. Its review confirmed one finding:
    `ticket_status` gave the caller's digits back when none of their tickets matched, so another
    customer's last four could back a claim; fixed in `118b10f`, given back only on a match. It
    refuted one, a lookup raising `ActionNotSent` in the start's reconcile, whose row is flagged
    anyway (TD-136).
  - **The integration's wiring** (`c85ecfa`): the runtime hands `VoiceCalls` the runner;
    `TextCall`'s and `AudioCall`'s talkers get it, and `AudioCall` builds one over a
    `MemoryOutbox` for an agent with actions; `GuardBlocked` carries the blocked clause's own
    reason; `DeclineKind` gains `stopped`, which the session's stop paths send, with a note of
    its own; the session's and the wire's docstrings; `serving.md`'s samples copied again from
    `server.py` and `token_route.py`. The tracks' debt is TD-133 to TD-141, their decisions
    D-081. Next: the end-to-end calls through `TextCall` and the audio session, and the gate
    (the Plan's step 4).
- 2026-11-10: The end-to-end calls, on the real parts with no stand-ins (the talker on a fake
  model, the session's read-back and confirming, the yes rule, the guard, the interruption rule
  and the runner over an outbox in memory), and run A's runner:
  - **The library's** (`tests/t2_agentic_voice/testing/test_action_calls.py`,
    `test_action_call_answers.py`, `test_action_call_claims.py`): the design's 9.2 flow in
    English and Saudi Arabic; a stop or pause word over the summary, over the closing question
    and said whole; a repeat; a plain no; a yes with a change; the declined line only after the
    last unclear answer; `fault_read_back`; rule A in the real talker; a hang-up while the write
    runs, its outcome sent once and never said.
  - **The minimal example's**: `ActionSafetySuite` on `request_callback` in both languages, and
    a call as the quickstart makes it.
  - **Ole5's** (`tests/ole5_voice/tickets/test_ticket_calls.py`, `test_actions_runner.py`,
    `test_ticket_safety.py`, `tests/ole5_voice/test_server_tickets.py`): the rehearsal's step 6
    (a bare «نعم» asked again, «نعم أرسلها» over the closing question making one ticket, its
    number said in four groups) and step 3 («أبغى موظف» over an answer, the handoff read back and
    made); the stop ruling; status of one's own ticket and of another's, and in a later call; a
    passage's number in a claim; a note on this call's ticket; the runner's mock modes and a
    restart with a row left `sending`; the suite on `create_ticket` and `hand_off` in both
    languages; the served runtime's outbox under `var/` and the tickets page.
  - **Parity** (`test_parity_actions.py`,
    `tests/t2_agentic_voice/api/test_runtime_calls_actions.py`): one scripted call with an
    action takes the same path through `TextCall` and the audio session; a served call over
    WebRTC is confirmed and written once.
  - **Run A's runner**, `poe eval-actions` (`ole5_voice/evals/action_*.py`): every committed
    scenario plays to its expected outcomes on fakes; the dry estimate is at most $1.24 for dev
    and $1.22 for held-out, each within the $1.50 cap, both together over it; it refuses before
    sending anything, and reads held-out once. Its review confirmed one finding, a stuck or
    failed play losing its violations, fixed before the merge.
  - **The defects the calls found, fixed here**: `TextTurn.tool_calls` gave an action call's
    arguments empty (now the model's own text); `TextCall`'s yes-rule check took a stop over the
    closing question for a broken summary, unlike the session's receipt; its rule B read the
    tools' evidence texts but not their data, nor a record entry's result whole, both of which
    the guard reads, so a status's last four digits counted as unsupported; `ActionSafetySuite`
    gave its calls no caller, so every case of an action that reads the caller, as Ole5's do,
    was refused before the read-back (`caller` added); «اممم» was on none of the yes rule's lists,
    so it was a correction, not asked again (a13);
    a14's third turn waited over a closing question that no ask-again line brings, and the
    format now refuses that order; the shared history did not take run A's line, nor its page
    render it; the talker logged dropped text after every action call, even when none was
    written; and `read_back.py`'s docstring still said a stop declines as a correction.
  - **The review of these fixes** (one reviewer for the code, one for the design docs, a
    skeptic a finding) confirmed three, fixed here: `TextCall`'s rule B still missed what an
    action's call gave back (a refusal holding a number), which the guard reads; the design's
    4.6 sample checked the done line's number on the yes turn, though the outcome answers no
    turn; and `TextCall` and `AudioCall` built the runner without the settings' daily cap per
    caller (`tests/t2_agentic_voice/testing/test_text_call_as_served.py`). It refuted two.
  - **Left**: TD-142, its first item the owner's call (Ole5's ticket-number wording).
- 2026-11-10: Block F, the library's part (D-082): `domain/consent_check.py` (the request, the
  model and its bounds, the answer's reader, `is_consent_check`); `decide` marks what its lists
  cannot place `askable` (a word on none of them, send words among fillers with no yes, a yes
  among fillers over the closing question), every answer it gave before unchanged; `judged`, the
  rails, an echo rail of the agent's own among them (the words a run of one of the read-back's
  lines); the change markers in `domain/yes_words.py`; `VoiceAgent.ask_on_unlisted_answers` (a
  Block F amendment to Block 0's declaration); `ConfirmationAnswered.by`;
  `voice/session/yes_ask.py`, wired from `yes_turns.py`, cancelled by a newer answer, the
  client's stop (`Talking.stopped`) and the call's end, `talking.py` reflowed so it does not
  grow; the `evals` facade's `consent_check_request`, `consent_check_answer` and
  `is_consent_check`; `ActionSafetySuite`'s five judged cases (`testing/action_judged.py`, its
  shared helpers moved to `action_scenes.py`). Tests: the domain's rails in both languages
  (`test_consent_check.py`, `test_yes_rule_judged.py`), the session's
  (`test_yes_ask.py`), the brief's table through `TextCall` in English and Saudi Arabic, once
  the question ended and over it (`test_action_call_judged.py`), and the suite on an agent that
  asks (`test_action_safety_judged.py`); `test_no_action_baseline.py` unchanged. Next: Ole5's
  part (the flag, its calls, run A's scenarios and oracle).
- 2026-11-10: Block F, Ole5's part: the served talker asks (`ask_on_unlisted_answers`, set only
  with its tickets, so the talker of runs K, S and T, which has no action, is declared as
  before); the ticket calls' fake model and run A's oracle answer the check; the suite's judged
  cases play on `create_ticket` and `hand_off` in both languages; `test_ticket_calls_judged.py`
  plays the brief's table on `create_ticket` in Saudi Arabic and English, once the closing
  question ended and over it («اكيد» and "sure" are listed yes words, so they ask no model;
  «صح» and "sure thing" are the model's yes), a yes with a change read back at priority High and
  then sent, and a hesitation or a failed check asked again, then a yes. Run A gains eight
  scenarios before any run (`a31` to `a38`; four kinds, each in both splits: an unlisted yes
  once the question ended, an unlisted go-ahead over it, a yes with a change, a hesitation in
  an unlisted spelling), and its dry estimate counts one check for each turn that answers a
  read-back: at most $1.65 for dev and $1.58 for held-out, each past the $1.50 cap, which the
  owner then raised to $10 ("The owner's decisions"). Found: a turn put to the model is marked
  answered before its verdict lands, so a play hangs up before a judged no's reply plays
  (`a27`, `a28`) and `TextCall` on the system clock returns before the verdict; fixed in the
  library by the review's fix (the next line).
- 2026-11-10: Block F's review, one reviewer a part and one skeptic a finding. The library's
  part: one confirmed, a judged turn settled before its verdict's reply, so its public
  `TurnMetrics` carried no time to first audio and its trace ended with no reply; fixed test
  first (`TurnBook.judging` and `judged`: the turn takes no fate and does not settle while its
  check is in flight, and settles after the reply its verdict says; a check the call's end
  cancels leaves the turn unfinished; `test_yes_ask_turns.py`), which also cleared Ole5's
  `a27` and `a28`. Ole5's part: one confirmed, run A's estimate past the $1.50 cap, the
  owner's to rule (the cap raised to $10, `action_run.CAP_USD`, its tests and the task's help).
- 2026-11-10: Block F's part 2, the owner's third ruling (D-082): `decide` marks a send word said
  alone `askable` too, its answer unchanged; `judged` takes `SaidLines` and holds the echo rail
  only over a line that was playing (the session's `Confirming.over_follow_up` for the ask-again
  lines); over the closing question the model's `yes` on a send word said alone is asked again,
  its `send` confirms it, and a `yes` on a send word beside other words («يلا أرسلها») confirms as
  before; `ActionSafetySuite` gains a sixth judged case, the closing question heard back as it
  plays. No run A scenario holds a send word said alone, so none moved. Its review: two findings,
  both refuted as the brief's words, but they showed a real gap: speech copying the agent's line
  begun within the 0.3 s the library already counts as its own voice after a reply ends
  (`playback.DROP_AFTER_S`) was judged as the caller's. Fixed (the next line).
- 2026-11-10: The echo rail takes a reply's tail, test first: words copying the read-back's
  summary or closing question, or an ask-again line, are the agent's echo when the speech began
  while that reply played or within its tail after it ended (`DROP_AFTER_S`, none after the
  caller's stop), the drop rule's own window (`Reply.over`; `Confirming.over_read_back` and
  `over_follow_up`; `SaidLines.over_read_back`); when a turn is said over the closing question
  for the send rule is unchanged (`question_ended_at`, no tail). `test_yes_ask_tail.py` (an echo
  0.1 s and 0.25 s after the line asked again, 0.4 s after judged as the caller's words, in
  English and Saudi Arabic); D-082, invariant 1, the design's 8.3 and the guide updated. Its
  review confirmed two, both fixed: a guide sample's fake reply the agent's lead had shortened
  to one clause, not yet played when `call.user` returned, and six guide excerpts `ruff format`
  would rewrite, now between `<!-- fmt:off -->` and `<!-- fmt:on -->`.
- 2026-11-10: The guide pages for actions, by five writers, each reviewed against the code with one
  skeptic a finding: `tools-and-actions.md`, `safety.md` and `testing.md` new (the text call's
  section of `evaluation.md` moved to `testing.md`, a pointer left); `concepts.md` gains confirmed
  actions, `quickstart.md` the example's callback on a spoken yes, `writing-for-voice.md`
  read-backs, claim phrases and send words, `README.md` its status, contract and pages tables;
  `browser-client.md` the `confirming` state. Four findings confirmed and fixed, all in
  `safety.md` and `testing.md` (the closing question's yes rail, "pardon?" a correction, no yes
  word in a closing question, an action's caller from `ctx.caller`; a check that runs out fails
  no test, the echo rail's condition). What the writers found in the code and the design: TD-143.

## Decision log

- 2026-11-10: The end-to-end calls' choices (D-081 holds them).
  - *`TextCall`'s checks read what the live guard reads*: a tool result's data and evidence
    texts, what an action's call gave back, a record entry's result whole and its texts; and a
    summary played whole stands though a stop cut its reply after it, as for the session's
    receipt. A check stricter than the guard fails a run for what a call did right. `TextCall`'s
    and `AudioCall`'s runners take the caps from the settings, as the runtime's does.
  - *`ActionSafetySuite.caller`*: the session's caller each case's call runs as, `TextCall`'s
    made-up one unless a subclass gives one, since invariant 3 asks a ticket action to read it.
  - *Ole5's claim phrases stay as Track E wrote them.* A phrase for "your ticket number" in both
    `create_ticket`'s and `hand_off`'s lists would block a true number after either, rule A
    asking evidence of every action a phrase names, and an any-action phrase (`guard.claims`)
    would cut a knowledge answer that says it in a call with no ticket: the owner's call
    (TD-142).
  - *The scenario format refuses a turn said over a read-back after one asked again once it
    ended*, the ask-again line being no read-back. «اممم» is one of the yes rule's fillers, not
    a listening sound of the interruption rule's, so no agent without actions changes (GP-18).
- 2026-11-10: What the tracks settled that the design left open, and the integration's choices;
  D-081 holds them for the design, whose 4.6, 6.4, 6.6, 8.2, 8.3, 9.2, 9.3 and 9.5 now say them.
  - *Track A, the yes rule.* Words begun before the summary ended, or with no `speech_at`,
    count for nothing, a no or a correction too. A send word with no yes word is asked again
    (the closing question holds one, and its echo must confirm nothing), and so are a yes with a
    question mark («نعم؟», pardon) and a yes beside a no. Any word on none of the lists makes a
    correction. A word on two lists counts as no, then yes, then send, then filler.
  - *Track A, the guard.* Rule A, then rule B, which counts the record's and the status
    results' texts as evidence. The default claim phrases are past-tense, mostly first person,
    and none only introduces a number ("your request number"), which would block reading a
    caller's own number back. The library's lines say "your request" («طلبك»), to fit any
    action.
  - *Track B.* Rule C drops the text after an action call in its request; a read-back ends the
    reply, and after a refused call the next request may speak, under rules A and B. The model
    reads only that its call is read back, never the draft, and one action is taken a request.
    A declined read-back reaches it as a note on the turn's message, naming the action and the
    kind; the note repeats neither the caller's words nor the draft. The request ID is derived
    from the confirmed action, so it is written once; the caps count outbox rows, never
    proposals; a write past its timeout runs on, never cancelled. `past_actions` reads the
    outbox's done rows for the verified caller. `t2v outbox` shows no draft, result or subject.
  - *Track C.* A turn is the yes rule's when its speech began once the summary's last clause
    played; the receipt is built then, and a turn with none is asked again. Real words that stop
    the closing question keep the receipt, so a yes with a send word there counts (the
    rehearsal's step 6). A repeat says the read-back again as a new reply. An unclear answer is
    asked again at most `max_attempts` times, then `declined` is said. A turn heard as nothing
    changes nothing while confirming. `sending` answers the yes turn; the outcome is said once,
    at a turn boundary.
  - *Track D.* `ActionSafetySuite` takes `make_agent()`, `action_under_test()`,
    `sample_draft()` and `language`. `TextCall` finds a read-back's parts by its captions, and
    exempts the runtime's own lines from its checks as the guard does. The example's action is
    in `callback.py`, so the guide's samples of `app.py` stand.
  - *Track E.* The mock never dedupes a request ID (a strict witness of invariant 6) and scopes
    every read and note by the session's customer. `ticket_status` gives the last four digits
    only, and the caller's digits back only on a match: a `reports_on` tool's result is
    evidence, so it may echo no argument the model chose. The handoff is a Request with the
    call's transcript, one a call.
  - *The integration.* Rule A runs only for an agent that declares actions, as Tracks A, B and D
    asked the lead to settle: the plan's baseline, so no measured run of an agent with none moves
    (GP-18), `TextCall.violations` likewise; the cost is that an agent with read tools alone can
    say "I've created your ticket" unblocked. The kind `stopped`, so the talker tells a stop from a
    correction and asks what to change. The session is the only sender of the outcome events.
- 2026-11-10: The owner's rulings after Block 0 ("The owner's decisions"), and what they change.
  A plain no goes to the talker as a `DeclinedAction` of kind `no`, and it answers in its own
  words; the guard's rule A holds over that reply as over any. A correction goes to it as kind
  `correction`, and a new read-back follows the new draft. `ReadBackPlan.declined` is spoken by
  the session only where no talker turn can answer: nothing usable heard after the last
  ask-again. A stop or pause word over the read-back ends the confirming state with no receipt,
  the draft kept. The progress line while the write runs is a Block 0 amendment: `@action` takes
  `sending`, a `Say` like the outcome lines, with the library's line per language when it is
  left out; `ReadBackPlan.sending` carries it rendered (Track B's `propose`), and Track C's
  session speaks it once the yes rule issues the `ConfirmedAction`, before the job's outcome.
  The four yes words are listed in `allowed_in_source.toml`, its pin in
  `test_no_item_in_source.py` updated (Block 0's, before Track A merges).
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

Each was put with the agent's recommendation; the owner took every one but run A's cap, where
they set a figure of their own.

- 2026-11-09, on starting: "I won't take the calls now, but since M4 is essentially done, lets
  start with M5"; "If it is necessary to close and merge M4 first tell me"; to the draft and its
  nine questions: "Approve all"; then, on the ticket system: "I don't have aceess to the real
  ticket system, so lets build a mock one for a demo sake and to prove that actions work as
  intended in the package and agent."
- 2026-11-10, after Block 0, four questions put with the agent's recommendations; the owner chose
  the words quoted here:
  - *The yes words* «نعم», «ايه», «ايوه» and "yeah", whole golden items: "Allow them, as in M3
    (Recommended)". They are listed in `allowed_in_source.toml`, as plan 005's Q1 listed the
    presets' words; a longer item that holds one stays searched.
  - *A stop word over the read-back*: "Stop, keep the draft (Recommended)". No receipt, the
    confirming state ends, nothing is sent, and the agent asks what to change; the draft is kept,
    and only a new read-back played in full can earn a yes.
  - *After a plain no*: "The model always answers". This is not the agent's recommendation (the
    action's fixed `declined` line, and the talker only for a correction): the talker answers any
    no in its own words.
  - *While the write runs*: "A short progress line (Recommended)". A fixed line, such as "One
    moment, I'm opening the ticket.", spoken as the search's progress line is, then the outcome;
    it never claims the ticket is made.
  - Not put as a question, since the yes rule already settles it: a request to hear it again while
    confirming says the read-back again, and only a yes after that reading counts.
- 2026-11-10, after the integration's report that «اممم» had been read as a correction for want
  of a list entry, the owner wrote: "We should be more flexiable, we shouldn't just have a list
  and rely on it, there are things a caller might say (or STT might hear) that no list can
  cover, so the agent should handle this itself". Put three options, the agent's recommendation
  first ("Model sorts the rest (Recommended)": the lists a fast path, a model sorting what they
  miss into unclear, no or change, never yes), the owner chose it with an addition: "Lets do the
  model sorts the rest. But I would also want it to recognize different words of confirmation
  like ("go for it", "اكيد" etc.. While also capable of knowing that "Yes, but change.." is a
  request for change and not only confirmation)". The agent had advised against a model's yes
  ("a misjudged 'yes, but change X' would send a ticket the caller never approved"); the ruling
  amends invariant 1, and Block F keeps the rails the Tracks section lists.
- 2026-11-10, on the first draft of Block F, whose rail made a judged yes over the closing
  question still need a listed send word, the owner asked (in a side session): "Over the closing
  question: a judged yes still needs a send word, as a listed yes does. Doesn't this defeat the
  purpose of a judged confirmation in first place?" The agent agreed in part (the rail brought a
  list back where eager callers speak) and proposed that the model tell an explicit go-ahead to
  send (`send`: "go for it", «يلا أرسلها») from plain agreement (`yes`: «اكيد», "sure"), only
  `send` counting over the question and both after it, the agent's own words heard back being
  `unclear`; the owner answered "Yes, send it".
- 2026-11-10, after Block F's build, two questions. On run A's dry estimate passing its $1.50
  cap ($1.65 for dev, $1.58 for held-out, with the eight new scenarios), put with three options,
  the agent's recommendation first ("Cap $1.70 a split (Recommended)"; a smaller input budget;
  two repeats), the owner chose a figure of their own: "Increase the budget to 10$, I don't care
  about the money as much as I care about wasted time and useless runs". So a run of a split is
  capped at $10, and no repeat or token budget is cut to save spend. On a send word said alone
  («أرسلها», «توكل», "go ahead", "send it"), which the lists still always asked again while
  "go for it" and «يلا أرسلها» could send through the model: "A send word said alone ... is
  still always asked again and never goes to the model, as in M3. Meanwhile "go for it" and
  «يلا أرسلها» do go to the model and can send. Should a send word alone go to the model too?"
  The owner chose "Yes, let the model judge (Recommended)": a send word alone goes to the model
  as any unplaced answer does, under the same rails, and words that copy one of the agent's own
  lines count as its echo only when heard while the agent was speaking (Block F's part 2).

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
- Rule on the yes words that are whole golden items, and on the read-back's edges (done
  2026-11-10, "The owner's decisions").
- Hold the live calls, against the mock ticket system, on the laptop's speakers and the wired
  headset (about 20 minutes).
