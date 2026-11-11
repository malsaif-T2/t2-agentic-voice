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
6. **Blocks G, H and I** (the owner's rulings of 2026-11-10, "Tracks"), each approved before it
   is built: Block G after the ruling on TD-144 and before the scenario runs, since it changes
   the talker's text; Blocks H and I after run A, each measured by its own registered run (runs
   H and I) before a default moves.
7. **The scenario runs**, dev then held-out once ("The measurement").
8. **The live calls**, by the owner.
9. **The background try** (Q8), behind a setting, off by default, after everything above.
10. **The close:** the logs, `## Future improvements`, the plan moved, the roadmap's row, the gate.

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

**Block G, no stray script in what the agent says or shows** (built 2026-11-11, D-084; the
owner's ruling of 2026-11-10, the roadmap's *No stray script*: "not only spoken, make it not appear as the llm response if we
hook up a screen"), built after the owner's ruling on TD-144 and before the scenario runs, since
it changes the talker's text; by one builder, for the library, with Ole5's one test and run A's
count through the public API; reviewed by the owner's rule (one reviewer a block, one skeptic a
finding). In the owner's demo call (report `0qPpF2-C`), `gpt-oss-120b` wrote «أيقونة "إ重新 كلمة
مرور المستخدم"» where the passage holds «إعادة كلمة مرور المستخدم». Nothing stops it today: the
guard checks claims and IDs only (`agent/speech_guard.py`), and the library reads a script only
to choose a reply's language from the caller's words (`agent/language.py:84-93`).

- **Where it sits.** Every piece the model writes enters `Turn._asked` at one place, its
  `TextDelta` branch (`agent/turn.py:308-311`), before `answer.text` (the same turn's next
  request), `Unnoted`, the clause splitter and the guard (`turn.py:354`). Every tool call is kept
  at `turn.py:318`, before `ToolCalls.run` traces it (`ToolBegan`, `agent/tool_calls.py:164`,
  which the session sends on as the public `ToolStarted` and `ToolFinished`,
  `voice/session/talker_play.py:120-148`, D-083) and proposes an action's. The filter runs at
  those two points, so one filtered text feeds the guard, the voice, the captions, the history
  the next turn reads, the trace, the public events and the test console: the ruling's "one
  filtered text feeds everything after".
- **The rule, pure** (new `domain/text/scripts.py`, shaped as `domain/text/invisible.py`, each
  range a constant with its comment). An agent's scripts are those of all its languages, never
  the reply's alone: `ar-SA` and `ar` write Arabic and Latin, `en` Latin (Q13), so Ole5 keeps
  both. Each character is judged alone, so a streamed text gives piece by piece what it gives
  whole, and nothing is held back.
  - *Kept:* the blocks of the agent's scripts (Latin U+0000-036F, U+1E00-1EFF, U+2C60-2C7F,
    U+A720-A7FF, U+FB00-FB06; Arabic U+0600-06FF, U+0750-077F, U+0870-08FF, U+FB50-FDFF,
    U+FE70-FEFF); General Punctuation (U+2000-206F); the Arabic-Indic and Persian digits; every
    character of a term the agent declares (its pronunciation map's written forms,
    `agent.vocabulary.terms` and `settings.words.vocabulary`, as `voice/stt_bridge.py:114`
    gathers the last two); any other punctuation, symbol, space, control or format character
    («», %, currency, math, and the arrows the speaking rules say as "then", U+2190-21FF,
    U+27F0-27FF, U+2794 and U+279C, `domain/text/speaking.py:203`); and a code point Python's
    tables leave unassigned outside the ranges taken out.
  - *Rewritten one for one:* a fullwidth form (U+FF01-FF5E) as its ASCII form; U+3000 as a
    space, U+3001 as "," and U+3002 as ".", so no two words are joined; a decimal digit of any
    other script as its ASCII digit.
  - *Taken out:* any other letter or mark (Cyrillic, Greek, Hebrew, Devanagari, a variation
    selector) and any private-use or surrogate code point; whatever its category, a character of
    the CJK and Hangul ranges (U+2E80-A4CF, U+AC00-D7FF, U+F900-FAFF, U+FE30-FE4F,
    U+20000-3FFFF), so one newer than Python 3.12's Unicode 15.0 tables goes too; and the
    pictographs (Q12): U+1F000-1FAFF, U+2600-27BF but the two heavy arrows, and a fixed set of the
    emoji below U+1F000 in other blocks (U+231A-231B, U+2328, U+23CF, U+23E9-23F3, U+23F8-23FA,
    U+24C2, U+25AA-25AB, U+25B6, U+25C0, U+25FB-25FE, U+2934-2935, U+2B05-2B07, U+2B1B-2B1C,
    U+2B50, U+2B55: the agent's reading of Unicode's emoji data, © ® ™ ‼ ⁉ left as symbols).
  - *The result*, `Kept` (frozen): the text, how many characters were taken out or rewritten,
    and a label for each kind (the first word of its Unicode name, "PICTOGRAPH", "FULLWIDTH", or
    its category for a code point with no name), at most eight, sorted; no text of the reply.
  - *How:* `str.translate` over a table that keeps each verdict once found (a `dict` with
    `__missing__`), one table per pair of scripts and declared terms, so two agents in one
    process never share a term's verdict; the text itself when nothing changed. Only
    `unicodedata`, its `name` called with a default; every code point gets a verdict, so it
    never raises.
  - *Public:* `remove_stray_script(text: str, *, languages: Iterable[LanguageTag], kept:
    Iterable[str] = ()) -> Kept`, with `Kept`, through the `languages` facade (provisional,
    D-021), so a team's measurement can read a reply as the talker says it.
- **One reply's filter** (new `agent/stray_script.py`), `StrayScript`, built in `Turn.__init__`
  beside the guard (`turn.py:184-191`). `text(piece)` filters a piece. `call(request)` filters
  every tool call's arguments (Q11): parsed as JSON, each string value filtered and never a key,
  written back (`ensure_ascii=False`) only when one changed, so a call with nothing to change
  keeps its exact text; arguments that are not JSON are kept as written, for the runner to refuse
  as it does. `take()` gives the count and the labels since the last take. With
  `guard.remove_stray_script` off, each returns its input and counts nothing.
- **In the turn** (`agent/turn.py`). The `TextDelta` branch filters each piece once and feeds
  that to `answer.text`, `Unnoted` and the splitter; `turn.py:318` keeps `self.scripts.call(event)`.
  The guard reads the text after the filter, a safety rule: the other way round, «تم重 إنشاء»
  would pass rule A as two words and be spoken as «تم إنشاء». Once the filter has taken a
  character out of a reply, a clause left with no letter or digit is given as no
  `SpokenClause`: it would be neither said nor captioned (`speak_arrows` drops a lone arrow,
  `speaking.py:208-216`; `said` keeps only clauses with a letter or digit,
  `voice/session/echo.py:84-103`), yet the session counts every `SpokenClause` said
  (`talker_play.py:115-117`) and then skips the `error` notice (`talker_play.py:168-170`), so
  «重置 → 确认» alone would be silence. A reply left with nothing to say gets the `error` notice,
  as an empty answer does. `_without_calls` (`turn.py:114-126`) moves to `agent/context.py` as
  `without_calls`, so `turn.py` does not grow.
- **The count.** `ModelReplied` (`agent/events.py:102-108`, internal) gains `stray_characters:
  int = 0` and `stray_scripts: tuple[str, ...] = ()`, filled from `take()` as each request ends
  (`turn.py:234-236`). `TalkPlayer` (`talker_play.py:162-167`) adds them to the turn's `TurnLog`
  (`voice/session/report.py:65`) and logs `talker_stray_script_removed` with the call, the turn,
  the count and the labels, never a character or the reply's text; `TurnLog.outcome()`
  (`report.py:164`) gives the turn's root span `turn.stray_characters` and `turn.stray_scripts`
  only when the count is above zero. `TextTurn` (`testing/text_turn.py`) gains
  `stray_characters`, summed from `ModelReplied` as its `usage` is (`text_turn.py:211-224`), and
  run A's runner records it: each dev scenario's count in its results, the run's total on its
  history line, held-out's too.
- **The setting:** `guard.remove_stray_script` (`core/settings/guard.py`), a bool, **on**
  (Q10): "Whether each character of a script none of the agent's languages writes (a Chinese
  character in an Arabic reply), and each pictograph, is taken out of what the talker writes,
  its tool calls' arguments included, before the guard reads it, and a digit of another script
  written as its ASCII digit; the voice, the captions, the history, the trace and the events then
  hold the text without it. Off: kept as written." `uv run poe settings-ref` writes
  `T2V_GUARD__REMOVE_STRAY_SCRIPT`.
- **What observers see:** the said text wherever it went before (`AgentSpeechEnded`,
  `CallEnded`'s report, the spans' said text under `tracing.include_transcripts`), without the
  stray characters; every tool call's arguments as filtered, in its span (D-079), in
  `ToolStarted.arguments` and `ToolFinished.arguments` (D-083), on the test console and in its
  files; `ConfirmationRequested.draft`, built from the filtered call. The turn's span gains its
  two attributes. No new public event; `TurnRecord`, `CallReport` and `t2v/1`'s messages keep
  their fields.
- **What it never does:** change the caller's heard words (the yes rule's input, the guard's
  evidence, the reply-language rule's input); change a tool's result, a card, a template or a
  fixed phrase (the team's declared text, the design's 8.2); change what the model is sent
  (`test_no_action_baseline.py` pins the prompt, the schemas, the turn's message and the word
  lists); guess at what a removed character meant («إ重新» leaves «إ», the model's start of
  «إعادة», Q14); hold text back; ask a model.
- **The invariants.** *Invariant 2* holds because the guard reads the filtered text, which is
  the text spoken: a stray character no longer hides a claim from rule A («تم重 إنشاء طلبك» and
  "I've 重created your ticket" pass rule A today and are caught once filtered). For rule B, a
  rewritten fullwidth colon, point or slash is read as its ASCII form is read today, keeping
  numbers apart ("45：21：33", blocked today as one run, is then read as "45:21:33" is, which
  passes); fullwidth and other-script digits, which rule B reads as no number today
  ("１２３４５" passes unchecked), are now checked; and "12重34重5", which passes today as three
  short runs, is checked as 12345. The guard's own files are not changed. *Invariant 1:* the
  heard words and the receipt are untouched, and the draft is filtered before it is proposed, so
  the read-back, the receipt's draft (D-080), the `ConfirmedAction` and the outbox row hold one
  text. *Invariant 4:* arguments are still parsed into the draft, after the filter; keys are
  never changed, so a field named like consent is refused as before; one change, said in
  `docs/SECURITY.md`'s invariant 4: a fixed-set value that differs from a member only by a stray
  character ("Technical重") parses as that member and is read back as it. *GP-18:* behind a
  setting, on by default because no measured outcome moves: the filter changes none of the
  stored measured texts (the check below), and characterization tests pin text in the agent's
  scripts unchanged; evaluation.md's exception for a reliability fix covers keeping it on, and
  run A, the first run after it, records each removal. *GP-19:* counts and labels only. *D-033:*
  fixed phrases untouched; Block I keys on the filtered text. D-066 and D-067 untouched.
- **The check, before the default stays on.** Already run by the agent on 2026-11-10 and 11,
  read only, with a scan stricter than the rule (it flags any character outside a fixed list of
  ranges, so its zero implies the rule's; `scan_scripts.py`, `latin_in_arabic.py` and
  `inventory.py` in the drafting session's scratchpad, run with the worktree's Python): none of
  the 5,747 clauses the talker wrote in the stored dev runs of K and S (k1-dev-a to d,
  k1-dev-spoken, k1-smoke, k1m-dev-a, k3-dev-a to d, s-120b-2 to 5; 4,098 Arabic, 1,649 English)
  changes, none of the 1,415 `search_knowledge` calls' arguments in them (the review's
  `scan_args.py`), and none of the knowledge snapshot's 226,809 characters. The non-ASCII marks
  the stored replies hold are all kept: the Arabic comma (1,687), curly quotes (704 pairs), «»
  (183 pairs), → and ← (257), the no-break hyphen (52), en and em dashes, two zero-width spaces
  and one soft hyphen; no emoji. Of the Arabic clauses, 266 hold Latin ("Ole5", "Ctrl", "PDF");
  of the English, 351 hold Arabic letters. Registered here, and run on 2026-11-11 (the progress
  log): the builder runs the same data through the built `remove_stray_script` with Ole5's
  scripts and terms, read only, and names the command and its counts in the progress log
  (GP-16); the default stays on when it changes none, and any change is listed to the owner by
  run and item, with its code points, before it does. It changed none. Then run A's count. The agent's reasoning, not measured: run T's times do not
  move, since the filter is one `translate` of each piece with no hold-back.
- **Tests**, each in its code's commit; every existing talker, session and `TextCall` test
  passes unchanged, the characterization GP-18 asks.
  - `tests/t2_agentic_voice/domain/test_scripts.py`: every code point of each preset's blocks,
    of General Punctuation, the Arabic-Indic and Persian digits and every arrow the speaking
    rules read (U+2190-21FF, U+27F0-27FF, U+2794, U+279C) kept; the demo phrase gives «أيقونة
    "إ كلمة مرور المستخدم"», 2 characters, labelled CJK; an English agent takes out Arabic letters
    and keeps Arabic-Indic digits; an Arabic preset keeps "Ole5", "Ctrl+Shift+R", an email and a
    link; "，１２３" gives ",123" and "Restart it。Then" gives "Restart it.Then"; a Devanagari five
    gives "5", U+3000 a space, and "10²" and "½" stay; a pictograph of each removed range, ⭐ and
    ▶ among them, goes, and a variation selector after an arrow goes while the arrow stays; a CJK
    code point unassigned in Python 3.12's tables goes; a Greek letter goes unless declared by
    the pronunciation map, the vocabulary or `words.vocabulary`; two agents with other declared
    terms in one process get their own verdicts; piece by piece equals whole for every cut of the
    samples; filtering twice equals once, and nothing raises, for every code point of the first
    plane.
  - `tests/t2_agentic_voice/agent/test_talker_scripts.py` (the talker on the fake chat model): a
    stray character in a piece of its own or cut across two is in no `SpokenClause`, and the
    turn's next request holds the filtered text. *Adversarial, invariant 2,* in an agent with an
    action and an empty record: «تم重 إنشاء طلبك» and "I've 重created your ticket" blocked as
    `unsupported_claim`; "12重34重5" with no evidence blocked as `unsupported_id` (it passes
    today); "12重345" with "12345" in a tool's result said as "12345" (blocked if the guard ran
    first, so it pins the order); "４５：２１：３３" judged as "45:21:33" is. *Adversarial,
    invariants 1 and 4:* a summary with a stray character read back without it, the receipt's
    draft, the `ConfirmedAction` and the outbox row holding the same text; a fixed-set value
    with one parsed as the member; a key holding one refused as an extra field; arguments that
    are not JSON refused as before. A read tool's string values filtered and its keys kept; a
    tool's result, a card and the heard words reaching their consumers as written;
    `ModelReplied`'s count and labels, 0 and () when nothing went; with the setting off, every
    event as today.
  - `tests/t2_agentic_voice/voice/session/test_talker_scripts.py`: the caption, the heard
    history, `AgentSpeechEnded.text`, the turn span's said text and `ToolStarted.arguments` hold
    the filtered text; the root span's two attributes only on a turn with a removal; the log line
    holds counts and labels only (`tests/leaks.py`'s `holding`); «重置 → 确认» alone, and a reply
    wholly in a stray script, each give the `error` notice.
  - `tests/t2_agentic_voice/testing/test_parity.py` (amended): a scripted call with a stray
    character says the same clauses through `TextCall` and the audio session, and
    `TextTurn.stray_characters` counts them.
  - `tests/ole5_voice/test_agent_scripts.py` (the public API only): the demo's answer, scripted
    through `TextCall` on Ole5's agent, says and captions no CJK character and keeps "Ole5" and a
    menu path's arrow; `tests/ole5_voice/evals/test_action_score.py` reads a scenario's count.
  - `tests/t2_agentic_voice/core/test_settings_talker.py` (its guard defaults, lines 28-33, gain
    `"remove_stray_script": True`); `tests/t2_agentic_voice/test_facades.py` (the `languages`
    facade gains `Kept` and `remove_stray_script`); `test_env_example.py` and
    `test_settings_ref.py` after `poe settings-ref`. Unchanged: `test_no_action_baseline.py` and
    `test_baselines.py`.
- **Size** (ARCH-SIZE, 400 lines a module; recounted at `4dc1f23`): `agent/turn.py` 379 ends
  near 376 (about +12, and −15 for `_without_calls`). The others it changes have room:
  `agent/context.py` 231, `agent/events.py` 140, `core/settings/guard.py` 74,
  `voice/session/talker_play.py` 171, `voice/session/report.py` 337, `testing/text_turn.py`
  298, `languages.py` 36, Ole5's `evals/action_score.py` 263 and `action_history.py` 116; new
  `scripts.py` (about 150) and `stray_script.py` (about 80). Not touched: `talking.py` 397,
  `call.py` 396, `voice/calls.py` 395, `testing/text_call.py` 396, `interrupter.py` 388,
  `speaker.py` 387, `api/runtime.py` 393, `read_back.py` 391, `core/config.py` 392, and the
  guard's files (`speech_guard.py`, `claims.py`, `guard_ids.py`), which rule A's work edits; if
  that work touches `turn.py`, Block G is rebased on it. The filter only removes or rewrites one
  for one, so no text grows past Orpheus' 200 characters a request or the trace's 32,768 a value.
- **Risks:** a filter that raised would end the reply (every code point gets a verdict,
  malformed JSON is kept, and a test covers the first plane); a term a team needs in a third
  script ("μs", a supplier's Chinese name) goes unless declared; a letter Unicode adds after 15.0
  outside the removed ranges is unassigned in Python 3.12's tables and kept, and a later symbol
  (the riyal sign, U+20C1) kept; the settings' digest gains the key, and no registered comparison
  spans Block G (run A runs after it); `ModelReplied` gains two fields with defaults, the turn
  span two attributes, `TextTurn` one read, the `languages` facade two names.
- **Docs:** Block G's decision (D-084); the design's 8.2 (opens with the filter), 8.1's row for invariant 2, 5.2's
  presets with their scripts, 10.1's turn attributes; `docs/SECURITY.md`'s invariants 2 and 4;
  the guide's `languages.md` (a section "Scripts a reply may hold": each preset's scripts, what
  is kept, rewritten and taken out, how a team keeps a term), `safety.md`'s "The output guard",
  `tracing-and-logs.md`'s "What a trace holds", `writing-for-voice.md`; the generated settings;
  the roadmap's item, marked built.

**Block H, each turn's language from a classifier** (the owner's ruling of 2026-11-10 in the
roadmap: "We should implement both of them and see their effectiveness and the latency
improvements or delays they bring"; to this draft: "Yes, and I agree to download the
dependencies and models"), built after run A, since `TextCall` sends no audio and nothing here
can move it; by one builder for the library and one for Ole5's run commands, each part reviewed
by the owner's rule. It adds a third value to D-066's setting: under `stt.live_language =
"classified"`, each turn is sent to Whisper in the language a classifier heard, chosen among the
agent's languages; a short, unsure, late, busy or failed turn keeps the current one. `session`
stays the default until run H's keep rule (GP-18). For a reader new to this: Whisper writes a
turn in the language it is told, and today it is told the call's, fixed at join (D-038, D-066),
so an English question in an Arabic call is written as Arabic sounds (plan 006's run X: the
English items' accuracy 0.813 sent as English, 0.027 as Arabic). A spoken-language classifier
hears a few seconds of speech and says which language it is. With a talker, the early start
(D-067) sends a turn's speech to Whisper the moment its 600 ms hold begins, so the language must
be known by then. The agent's offline check of 2026-11-10 (another session's scratchpad,
`C:/Users/m7ms/AppData/Local/Temp/claude/8fb745428e63359b/d39ce14f-8cf9-4755-9d54-6da2f7bf6e54/scratchpad/lid/`,
read, not run; the times recomputed by the review from its `results.jsonl`), on the 280 dev variants that hold
speech, whole clips, Arabic against English: ECAPA right on 261 (93%), Silero on 234 (84%); in
wall time at 4 torch threads, ECAPA's median 735 ms a clip (about 257 ms a second of audio, p90
381), Silero's about 12 ms a second; every ECAPA miss a clip of 2.31 s or less. A rule keeping
the call's language under 2.0 s and switching on a share of 0.7 would have found 45 of the 75
English clips in an Arabic call with ECAPA and kept all 205 Arabic ones; Silero 47, sending 11
Arabic clips as English, four of them requests. In-sample, whole clips, one speaker (D-006): they
shaped this block and prove nothing.

- **Where it hooks in.** The session names the call's language once (`voice/session/call.py:92`,
  sent by `ListenIn` at `call.py:229`); the bridge keeps it (`voice/stt_bridge.py:165-168`) and
  every request names it with that language's prompt (`stt_bridge.py:320-321`). The language
  named moves the transcript (`adapters/groq_stt.py:145-148`), the heard words
  (`voice/session/heard.py:24`), the reply's language (`agent/language.py:84-93`) and the
  read-back's yes words (`voice/session/read_back.py:173-183`) together; `call_prompts` already
  holds a prompt for each code (`stt_bridge.py:107-116`, D-074).
- **The port** (new `domain/ports/language_classifier.py`, public through `ports`,
  provisional): `LanguageClassifier`, with `name`, `async load(among)` (the model loaded off the
  event loop, once a process; a ConfigurationError, before any call, when it cannot hear a code
  of `among`), `async classify(clip, *, among)` and `aclose()`; and `LanguageScores`, parsed at
  the port: a share for each code asked, each from 0 to 1, summing to 1, and `mass`, the share of
  the whole output those codes held. A busy classifier returns None; a failure raises
  `ProviderError`; an answer that does not parse is a failure.
- **The rule** (new `domain/turn_language.py`, pure): `LanguageRule(from_s, min_share)` and
  `choose_language(current, verdict, *, speech_s, rule) -> LanguageChoice(language, by)`, in
  order: `short` when the turn's speech had not reached `from_s` when its request went, then
  `late`, `busy`, `failed`, `unsure` (the best share under `min_share`), else `classified`. Only
  `classified` moves the call's current language (Q17). `speech_s` is the audio held from where
  the speech detector heard the speech begin (`HeldTurn.speech`, `voice/stt_turn.py:28-46`)
  when the request goes, counted in bytes, never on the clock; it may hold pauses.
- **In the bridge** (new `voice/stt_language.py`, `TurnLanguages`, about 150 lines;
  `stt_bridge.py` calls it at a few places). Built with the agent's codes, it holds, by turn, the
  bytes held at each request. *While the caller speaks:* once a turn holds `from_s` from its
  speech's first byte, those seconds go to the classifier, once a turn, on a task of
  `TurnLanguages`' own set (the adapter works on a thread), so the verdict has the rest of the
  turn, the detector's stop and Smart Turn's decision to arrive. *Never waiting:* each request
  names the language in hand when it goes (`named(turn_id, part)`), decided before its
  `Transcribing` is handed (`stt_bridge.py:316`, which today comes before the language is read,
  at 320), so the event carries it. The held request decides at the hold's start
  (`stt_bridge.py:240-249`); the turn's own request, after `_close` has cleared the turn
  (`stt_bridge.py:271-272`), names the same, so a reused held result (`stt_turn.py:78-87`)
  agrees with it; speech that resumes in the hold cancels the held request and its decision
  (`stt_bridge.py:250-253`). The bridge tells `TurnLanguages` a hold began whatever `early` is
  (before `_hold`'s return at `stt_bridge.py:243-244`), so a call with no talker records it too,
  with no new event. *Overlaps:* the `window` and `overlap` parts always name the current
  language (`by = "overlap"`), their timing being the two-step rule's (D-061). *The call's end:*
  `drop` (`stt_bridge.py:349-356`) cancels `TurnLanguages`' tasks too, and a late result is
  dropped unread.
- **The two adapters** (new, `adapters`; reached by apps through a new provisional facade,
  `classifiers`, which re-exports them as `groq.py` re-exports Groq's, so run H builds them as
  the runtime does; any other passed in code, `Providers.replace(classifier=...)`, GP-22).
  - `adapters/silero_language.py`, `SileroLanguage`: onnxruntime on `lang_classifier_95.onnx`
    with its label map (code 55 `ar`, 30 `en`), the caller's PCM16 as float32, the softmax
    renormalized over `among`, `stt.classifier_threads` intra-op threads. It imports onnxruntime
    and numpy, which Pipecat brings today; ARCH-DEPS refuses a borrowed import (GP-24), so both
    are declared in the library's `[project] dependencies` at the locked versions (`uv add
    --package t2-agentic-voice onnxruntime numpy`).
  - `adapters/ecapa_language.py`, `EcapaLanguage`: SpeechBrain's `EncoderClassifier`, loaded only
    inside `load` and only through `importlib.import_module` with literal names, which ARCH-OWNER
    and ARCH-BAN read (`scripts/arch_module.py:234-272`); ARCH-DEPS reads only `[project]
    dependencies` (`scripts/arch_deps.py:153`) and every import statement, so an `import
    torch` in a body would fail `poe arch` whether or not the extra is installed. It loads by
    exactly `from_hparams(source=folder, savedir=folder, overrides={"pretrained_path": folder},
    local_strategy=LocalStrategy.NO_LINK, run_opts={"device": "cpu"})`, which the download step's
    smoke must prove on 1.1.2 writes nothing into the folder and reaches no host (the offline
    check loaded otherwise, with a separate save folder and `COPY`, and its model folder gained a
    0-byte `custom.py`). The folder must hold no `.py` file, since SpeechBrain puts it on
    `sys.path`; `load` refuses one. Then `torch.set_num_threads(stt.classifier_threads)` and
    `classify_batch`, its log-probabilities exponentiated and renormalized over `among` (`ar:
    Arabic` at 3, `en: English` at 20). Without the extra, `load` is a ConfigurationError whose
    fix names `uv sync --group language-id`.
  - Both: one classification at a time a process (a second while one runs is `busy`); every file
    checked against its pinned size and SHA-256 at `load` (new `adapters/model_files.py`), a
    missing or changed file a ConfigurationError naming the file and the guide's page.
- **The settings** (the `stt` group, `core/settings/stt.py`, 79 lines, so `core/config.py` is
  not touched): `stt.live_language` gains `classified`; `stt.classifier`, `silero` by default, or
  `ecapa`, which needs the extra; `stt.classifier_dir`, no default, the folder of the model
  files, fetched once by hand and each checked at start, never under a repository (Q16);
  `stt.classifier_from_s`, 2.0, "the seconds of a turn's audio, from where the speech detector
  heard its speech begin, that the classifier hears; pauses inside the turn count";
  `stt.classifier_min_share`, 0.7; `stt.classifier_threads`, 2. An agent with one primary code
  runs no classifier. `uv run poe settings-ref` regenerates the docs.
- **The wiring.** `Providers` (`api/providers.py`) gains `classifier`, built by `from_settings`
  only under `classified`; the runtime's `_start` (`api/runtime.py:255-309`) loads it off the
  loop, pushes its `aclose` and passes `classifier=` to `self._calls(...)` (`runtime.py:286`);
  the `CallsFactory` protocol (`voice/calls.py:178-193`) and `VoiceCalls` take it and hand it to
  each call's `CallPipeline` (`voice/pipeline.py:96-103`). `t2v doctor` (`api/doctor.py`) gains
  a section under `classified`: each file's SHA-256 against its pin, as it checks Pipecat's ONNX
  files, and, under `ecapa`, whether torch is installed and any `nvidia-*` or `triton`
  distribution beside it, found without importing torch.
- **The install.** `packages/t2-agentic-voice/pyproject.toml` gains `[project.optional-dependencies]
  ecapa = ["speechbrain>=1.1.2", "torch>=2.11", "torchaudio>=2.11"]`; the root's
  `[dependency-groups]` gains `language-id = ["t2-agentic-voice[ecapa]"]`, so this workspace
  installs it with one command and no app depends on it. On Linux, torch and torchaudio come from
  PyTorch's CPU index (an explicit index for those two, Linux only), so this workspace's lock
  holds no CUDA package; a team that adds the extra from the git tag on Linux needs the same lines
  in its own `pyproject.toml`, since uv reads a dependency's index only inside its own workspace,
  and the guide gives them. `harness.toml` gains an owner rule giving `torch`, `torchaudio` and
  `speechbrain` to `adapters` alone and a ban keeping `huggingface_hub` out of the library's own
  code (ARCHITECTURE.md with it, ARCH-DOC); the Smart Turn v2 ban's fix text says "the base
  install"; `test_public_types.py`'s `FRAMEWORKS` gains `torch` and `speechbrain`; mypy reads
  torch through a small protocol, so `poe types` gives one answer either way. The torch check
  (`tests/harness/test_install.py:37-51`) walks `uv.lock` from each member's base dependencies,
  refusing any `torch*`, `nvidia-*`, `cuda-*` or `triton` package there, and proves torch comes
  only through `t2-agentic-voice[ecapa]` (Q15).
- **What observers see.** `Transcribing` (`voice/session/session_events.py:88-96`, internal)
  gains the language its request named, `by` (`session`, `classified`, `short`, `unsure`,
  `late`, `busy`, `failed`, `overlap`) and, with a verdict in hand, its best share and when it
  came. `TurnBook.transcribing` (`voice/session/turn_book.py:117-126`) reads them from the turn's
  first `Transcribing`, whatever its part, before its return for parts other than `turn`: in a
  talker call the held request decides the turn, and a reused result hands no `turn` request
  (`stt_bridge.py:277-279`). It traces them on the turn's speech-to-text span
  (`stt.language_sent`, `core/tracing.py:56`) instead of the call's language. The call report's
  `TurnRecord.language` (`core/events.py:163`, today the call's tag on every turn,
  `voice/session/report.py:187-195`) becomes the tag of the language the turn was sent in, its
  code mapped to the agent's tag as `reply_language` does, and `TurnRecord` gains
  `language_by`; under `session` both read as today (the call's tag, and `session`). No new
  public event, no audio, no score of a turn not classified.
- **The yes rule with a turn in another language.** The yes rule's rails read only the
  read-back's language (`read_back.py:173-183`; `domain/yes_rule.py:333-338`), and
  `classified` makes a turn in the other language routine: an English "yes, but change the date"
  over an Arabic read-back, put to the model under Block F, would confirm on its `yes` with no
  rail reading "but". So whenever the heard words' language is not the read-back's, `judged`'s
  rails (the no words and the change markers) read those of every language the agent speaks,
  the lists that place a yes staying the read-back's; built in `voice/session/yes_turns.py`
  (269 lines), so `read_back.py` does not grow. A rail only asks again or corrects, so this never
  confirms what today's rule refuses.
- **What it never does:** send a turn's audio anywhere but Whisper (the classifier runs in the
  process); keep audio (the seconds it hears live in memory with the turn, invariant 8); make a
  request, the hold or a turn's end wait on the classifier (its CPU's effect on the turn ends is
  condition 4's, below); pick a language the agent does not speak; classify an overlap's parts;
  change the call's language at join, its greeting, its notices or the phrase cache's language;
  download at run time; import torch unless `stt.classifier = "ecapa"` under `classified`.
- **Ole5** (the app's builder). Its live calls change nothing until the keep rule and Q19: the
  owner's `.env`, which no agent reads, sets `stt.live_language`. The app gains run H's commands:
  `poe eval-languages` (new `apps/ole5-voice-agent/src/ole5_voice/evals/languages_run.py` and
  `languages_score.py`), on a provisional `evals` helper, `turn_languages` (new
  `testing/turn_languages.py`, shaped as `testing/turns.py`'s `turn_ends` for an agent of two
  languages, taking a `LanguageClassifier`); and `poe eval --language-from <H1 pass>` (new
  `language_arms.py`, so `run.py`, 343 lines, grows by its option alone). Runs O and the echo
  timing keep refusing any `stt.live_language` but `session` (`evals/overlap.py:207-211`,
  `evals/timing.py:161-165`).
- **The one download step** (the list under "Downloads to approve"). The only step that may
  reach the network, run once in the build session and named in the progress log with what it
  fetched. In order: `uv lock`; the diff of `uv.lock` compared with the approved list, and any
  package not on it, or any `nvidia-*`, `cuda-*` or `triton` package, stops the step and goes to
  the owner before `uv sync`; `uv sync --group language-id`; the model files copied from the
  offline check's folder (the pinned files only, never its `custom.py` or `.cache`) or fetched
  from the pinned commits, each size and SHA-256 checked; the smoke, offline (`uv run
  --offline`, the `HF_*` variables unset, `HF_HUB_OFFLINE=1`, and the proxy variables pointed at
  a closed local port so any request fails): each adapter loads from the folder, the folder's
  listing and every file's SHA-256 the same after as before, and classifies three dev variants
  (an English request, a Saudi one, an MSA one) as their items' languages; and it times ECAPA and
  Silero on 2.0 s clips at the registered 2 threads, in wall time and the process's CPU time,
  which become run H's expected lines before H1 runs. If torch 2.15.0 and torchaudio 2.11.1 fail
  together, the lock takes torch 2.11.0, the version torchaudio 2.11 was made for, an amendment
  shown to the owner. A failed smoke stops the block and is reported.
- **Tests with no model and no network.** Every test of the session and the bridge uses a fake
  `LanguageClassifier` (scripted verdicts, a delay, a failure, busy); each adapter's tests inject
  its runner and check the label maps, the renormalization and the PCM conversion with no model
  file; the file check runs on small files the test writes. `poe check` never loads a model or
  imports torch, and gives the same answer whether or not the `language-id` group is installed;
  `uv run --offline` stays the rule for everything but the step.
  - `tests/t2_agentic_voice/domain/test_turn_language.py`: each branch of the rule and its edges
    (speech exactly `from_s`, a share exactly `min_share`); the current language moves only on
    `classified`; under `session` the call's language whatever the verdict.
  - `tests/t2_agentic_voice/domain/test_language_scores.py` (adversarial, GP-08): a share of NaN,
    -0.1 or 1.2, shares summing to 0.9, a code not asked, an empty answer, each refused at the
    port, the turn keeping its language; a classifier sure of a third language still chooses
    only between the agent's, its low `mass` recorded.
  - `tests/t2_agentic_voice/domain/test_yes_rule_languages.py` (new; `test_yes_rule_judged.py` is
    at 379; adversarial, a fake model answering `yes`): "yes, but change the date" heard as
    English over an Arabic read-back and «نعم بس غيّر الموعد» heard as Arabic over an English one
    are each a `Correction`; "no, send it" heard as English over an Arabic read-back is never a
    yes; with the languages the same, every answer of today's tests stands. `ActionSafetySuite`
    gains the two mixed-language cases (`testing/action_judged.py`, 174 lines), played on Ole5's
    `create_ticket` both ways.
  - `tests/t2_agentic_voice/voice/test_stt_language.py` (new), the bridge with a fake classifier
    and a fake speech-to-text: classification starts once the turn's audio holds `from_s` from
    the speech's first byte, never on the clock, at most once a turn; a shorter turn never asks;
    the held request names the verdict in hand and its `Transcribing` carries it; a verdict still
    running is `late`, and the held request goes in the same step as `TurnHeld`; a classifier
    that blocks 2 s delays no frame and no request (a 20 ms ticker); an overlap's parts name the
    current language with a verdict in hand; the turn's own request reuses the held language;
    resumed speech decides again; an echo call's hold is recorded; `drop` cancels the task and a
    late result is never used; a busy classifier keeps the language.
  - `tests/t2_agentic_voice/voice/session/test_turn_language.py` (new): the trace and the call
    report name each turn's language and `by`, a reused held result among them; under `session`,
    the report as today.
  - `tests/t2_agentic_voice/adapters/test_silero_language.py` and `test_ecapa_language.py`
    (new): with injected runners, the label maps, the renormalization, the PCM16 conversion and
    the thread count; the ECAPA module imports alone in a new process without torch; `load`
    without the extra names the group; the load call is given the folder, `NO_LINK` and the
    override; a folder holding a `.py` file is refused.
    `tests/t2_agentic_voice/adapters/test_model_files.py` (new): a missing file, a wrong size and
    a wrong hash each refused, naming the file and never its bytes (`tests/leaks.py`).
  - `tests/t2_agentic_voice/api/test_providers.py`, `test_runtime.py`, `test_doctor.py`: the
    classifier built only under `classified`, loaded at start and closed once; `classified`
    with no `stt.classifier_dir` refused at start with a fix; the doctor's section.
  - `tests/harness/test_install.py`: no member's base install holds a torch, CUDA or triton
    package; torch only through the extra; its self-test on a made-up lock. New
    `tests/harness/test_arch_models.py` (`test_check_architecture.py` is at 361): torch imported
    outside `adapters` and `huggingface_hub` in the library each reported with its fix; every
    module the ECAPA adapter loads is provided by a requirement of the `ecapa` extra.
  - Ole5 (`tests/ole5_voice/evals/`): `test_languages_run.py` and `test_languages_score.py`
    (new), as `test_eot.py` and `test_eot_score.py` are; `test_run_arms.py` gains
    `--language-from`.
- **The invariants.** *Invariant 1:* the classifier changes only the language a request names;
  the heard words are still built only by `voice`; a yes in another language is on none of the
  read-back's lists, so it is asked again or put to the model, whose `yes` then meets every
  language's no words and change markers (above); short turns, where most yeses are, keep the
  current language. Said plainly, what is left: an unlisted word heard in the read-back's own
  language is judged as today (D-082), so a short «لا» over an English read-back, after an
  English turn moved the current language, goes to Whisper as English and the model's word on
  what it writes decides, under today's rails. *Invariant 4:* a classifier's answer is parsed at
  the port, and one that does not parse is a failure. *Invariant 8:* the classifier hears a
  turn's first seconds in memory and keeps nothing; traces hold codes, shares and times, never
  audio (`core/tracing.py:60-64`). *The design's 11:* the files are fetched by hand, the adapters
  load only from `stt.classifier_dir`, and `huggingface_hub` is banned from the library's code.
  *GP-18:* `session` stays the default (`tests/t2_agentic_voice/core/test_config.py:48`), and
  the existing tests of `session` and `auto` are the characterization. *GP-22*, *GP-24*:
  above. *D-066* is amended by Block H's decision, a third value; *D-067*'s hold and early start never wait
  on the classifier; *D-034*, *D-038*, *D-061*, *D-074* unchanged; *D-018*'s one install and
  *D-032*'s torch check amended only by the owner's ruling on Q15.
- **Size** (recounted at `4dc1f23`): `voice/calls.py` 395: `_detectors` (`calls.py:327-336`)
  moves to `voice/turns.py` first, in a commit of its own, before the parameter, the attribute,
  the protocol's parameter and the keyword to `CallPipeline`, so it ends near 390;
  `api/runtime.py` 393 to about 397 (the load, the close, the keyword), and if it would pass
  400, a part of `_start` moves out first, in a commit of its own; `voice/session/call.py` 396:
  line 92 rewritten in place, no new case in `_take`; `voice/stt_bridge.py` 356 to about 366, the
  logic in `stt_language.py`; `core/events.py` 361 and `core/tracing_tts.py` 344 a few lines
  each. Not touched: `talking.py` 397, `text_call.py` 396, `interrupter.py` 388, `read_back.py`
  391, `agent/turn.py` 379, `speaker.py` 387, `core/config.py` 392.
- **Risks:** the torch check fails as soon as the lock holds torch (`test_install.py:42-51`), so
  it is rewritten with the extra, after Q15; CPU (ECAPA shares the CPU with every call's speech
  detector and Smart Turn, bounded by one classification at a time and the thread setting;
  condition 4 measures one call, and how many calls the CPU holds is the reliability work's
  count); late verdicts on turns a little over 2 s; a wrong switch on a long Arabic turn
  (`min_share`, condition 2); text from silence sent as English (`domain/silence.py:100-110`,
  condition 3); the model's load and memory, not measured (the smoke times the load, H1 records
  the process's peak where it can); torch 2.15.0 is 14 days old and torchaudio is in its
  maintenance phase (the smoke proves the three, torch 2.11.0 the fallback); Silero's file is a
  third party's re-upload of a model deprecated upstream, pinned by commit and hash, whether it
  equals Silero's own not checked; an exact `uv sync` without the group removes the extra, after
  which ECAPA's `load` refuses with its fix; public names gained, all provisional
  (`Providers.classifier`, the port, the `classifiers` facade, `TurnRecord.language_by` and the
  new meaning of `TurnRecord.language`).
- **Docs:** Block H's decision (D-066's consequences point to it; D-018's open question 2 and D-032's torch
  check amended by Q15's ruling); the design's 4.1, 6.1, 7.6, 9.8 and 13 (the licence rows);
  `docs/design/evaluation.md`'s "Running"; the guide's `languages.md` (the third value, the rule,
  the files with their sources, sizes and hashes, a Linux team's index lines, run H's result),
  `concepts.md` and `quickstart.md` (their "measured before it is promised" sentences),
  `is-this-for-you.md` ("No GPU and no torch"), `serving.md`; `docs/SECURITY.md`'s invariant 8;
  ARCHITECTURE.md and `harness.toml` together; CLAUDE.md's `eot` · `overlap` · `eval-timing` row
  gains `eval-languages` within its line (CLAUDE.md is at its 120-line cap, DOC-ENTRY); the
  generated settings; debt rows for several calls classifying one at a time, the CPU index
  checked at the deployment, and Silero's file kept by a third party.

**Block I, every clause the agent says kept on disk by its exact text** (the owner's rulings of
2026-11-10 in the roadmap, amending D-033: "we should cache everything we can, because all of it
is what the agent generated and we have full access to it and since we would an exact match, no
user will hear the info of another"; "make it on disk without consent, because this what our
agent produced"), built after run A, by one builder for the library and one for Ole5's run T
arm, each part reviewed by the owner's rule. It touches text-to-speech only, lands behind a
setting, off, until run I's keep rule (GP-18), and downloads nothing. For a reader new to this:
each clause of a reply is one request to Orpheus, Groq's text-to-speech, which streams its audio
back (`voice/tts_bridge.py:181-203`); only the fixed phrases (greetings, notices, progress lines)
are made once and played from disk (the phrase cache, `adapters/phrase_cache.py`). A clause said
again costs a request again. This block keeps every clause's audio, keyed by its exact text, so
the same clause in the same voice plays from disk: one Orpheus request saved (Groq publishes 10
a minute a model, the design's 10.4) and that request's wait for its first audio (about 0.25 s,
plan 003).

- **The settings** (`core/settings/tts.py`, beside `cache_phrases`): `tts.cache_clauses`,
  **False**: "Whether every clause the agent speaks in a call with a talker is kept on disk
  under the storage folder by its exact text, its language, its voice and the adapter that made
  it, so the same clause plays again with no request; the echo's words said back are never
  kept." `tts.clause_cache_mb`, at least 1, **512** (Q23): "The most disk the clause cache keeps,
  in megabytes; past it, the clauses played longest ago are removed." No folder setting: the
  cache is `storage.var_dir/<agent name>/clauses/`, beside `phrases/`.
- **A protocol beside the port** (`domain/ports/text_to_speech.py`): `HeldSpeech`,
  runtime-checkable, one method, `async def held(self, text: str, *, language: str) ->
  AudioChunk | None`. Not in the `ports` facade; the port itself is unchanged, so `GroqTTS`, a
  team's adapter and every fake stay as they are.
- **The clause cache** (new `adapters/clause_cache.py`, about 250 lines), `ClauseCache`: a
  `TextToSpeech` that wraps another and meets `HeldSpeech`. Built with no IO
  (`ClauseCache(tts, *, folder, voices, trim_silence, max_mb)`, and `from_settings`); `async
  open()` reads its folder; `aclose()` drains its own writer for at most 5 s (the agent's
  number) and drops the rest, and never closes the adapter it wraps: whoever built that closes
  it, as run T's `CountedVoice` does, the runtime already closing the providers' text-to-speech
  (`api/runtime.py:266`), which the port says is closed once.
  - *The key:* a SHA-256 of the cache's format tag, the wrapped adapter's `name`, the language
    tag, that language's model and voice from `tts.languages`, `tts.trim_silence`, and the text
    exactly as the provider is sent it, cut to 32 hex characters as `phrase_key` is
    (`phrase_cache.py:250-254`). The text sent comes after the speaking rules, the pronunciation
    map and `provider_text`, so a change to any of them that changes a clause's words changes its
    key; no "speaking rules' version" exists in the code, and the key needs none (Q24). With the
    adapter's name in it, takes one adapter made are never played for another passed in code.
  - *Keeping a take:* each chunk is passed on at once, unchanged, and a copy kept in memory; only
    once the stream has ended whole (after the loop, never in a `finally`) is the take kept: one
    rate, some audio, no chunk cut short. A take that raised, came back cut short, gave no audio
    or was stopped is never kept. `synthesize` never serves a held take: the bridge asks `held`
    first.
  - *Writing:* one writer task, its queue at most 64 takes (the agent's number; when full, the
    take is dropped), each write in a thread to `<key>.<random>.part`, then renamed onto
    `<key>.wav`, as the phrase cache writes. `_read`'s body (`phrase_cache.py:217`) and `_wav`
    (`phrase_cache.py:277`) move into a new `adapters/wav_files.py` that both caches use.
  - *The index:* at `open`, in a thread, each `<key>.wav` of its own pattern is an entry, its
    size and its file's time its last use; each `.part` of its own pattern is removed; nothing
    else in the folder is read, touched or removed (GP-21). It lives in memory on the event
    loop, so a miss is a dictionary look-up.
  - *Reading:* a key in the index is read in a thread within 100 ms (the agent's number), else it
    is a miss and the clause is requested as today; the file is a take only when it reads as the
    cache writes one (a mono 16-bit WAV, its frames matching its data, at most 4 MB); anything
    else is a miss, the entry dropped and the file removed by the writer. `held` never raises.
  - *The bound:* past `clause_cache_mb`, the writer removes the entries used longest ago until
    under nine tenths of it; a hit refreshes its entry and its file's time; a file Windows will
    not let go of stays for the next round, and a rename it refuses drops its `.part`.
  - *`clear()`:* removes every take it keeps (its own files, in its own folder) and resets its
    counts; run I calls it once its smoke call has passed.
  - *Its counts* (`counts()`, and `taken()`, which also resets them): hits, misses, takes kept,
    takes not kept by why, unreadable files, failed writes, entries removed, the entries and
    megabytes held, each look-up's seconds, hits' and misses' apart; a frozen `ClauseCounts`, no
    text and no key.
  - *Public:* `ClauseCache` and `ClauseCounts` in the `stores` facade beside `PhraseCache`, so
    run T builds the cache as the runtime does (`testing` never imports `adapters`); D-032's
    sentence that `PhraseCache` is the one public name no public signature names
    (`docs/design/decisions.md:1195-1197`) is amended.
- **The bridge, the hook point** (`voice/tts_bridge.py`, 249 lines). `ClauseTTSBridge._speak`
  (`tts_bridge.py:181-203`) plays a fixed phrase's audio, marks an empty clause, fails when the
  service is unusable, or sends the request. Block I adds one branch after the empty clause:
  when the bridge's text-to-speech meets `HeldSpeech` (checked once, in `__init__`) and `held`
  gives a take, the bridge checks again that no stop dropped the clause while it was read (as
  `_speak` checks at `tts_bridge.py:183`), then plays it through `_play` (`tts_bridge.py:204`),
  the fixed phrase's path: no `Synthesizing`, no request. `ClauseTake` (`voice/tts_output.py`)
  gains `held`, and `ClauseQueued` (`voice/session/session_events.py`) `held: bool = False`.
  With any other text-to-speech the bridge does exactly what it does today.
- **The session's counts** (`voice/session`). A held clause is a cache hit but never a fixed
  phrase: `Clause.cached` (`playback.py:53-73`) means a phrase, which a reply said again looks up
  in the phrase cache (`echo.py`'s `again`), where a talker's clause is not found and would go
  unsaid. So `Clause` gains `held`, set by `Playback.queued` (`playback.py:232`) from the event;
  `Reply.numbers()` counts `cached or held` as the span's `cache_hits` (`playback.py:130`);
  `Speaker.queued` (`speaker.py:283-295`) counts the hit in the call's usage. A held clause sends
  no characters.
- **A reply said again says what was sent**, folded in, since a repeat must make the same key.
  Today `Speaker.repeat` sends each clause's caption (`speaker.py:274`), in the call's language
  (`voice/session/echo.py:133-157`). A clause that fits one request is captioned as the talker
  wrote it (`open_reply.py:86-87`), and an action's line with its `text` while its `spoken` form
  was sent (`open_reply.py:148-149`), so a repeat skips the speaking rules and the pronunciation
  map (a ticket number's digits go to Orpheus raw), says an English clause of an Arabic call in
  the Arabic voice, and could never hit the cache. `Clause` gains `sent`, the request's text
  (`line.speak.text`, set where `playback.py` builds a clause, lines 167-171 and 192-199);
  `speaker.py:274` passes each clause's caption, `sent`, language and `cached`, rewritten in
  place; `again` sends `sent` in the clause's language, the call's when it has none. A reply said
  again then says each clause as it was first said, and finds its held takes.
- **The composition** (`api`). A new `api/voices.py` (about 60 lines) takes the phrase cache's
  lines out of the runtime's `_start` (`api/runtime.py:257` and `272-274`): it declares the
  phrase cache on the providers' text-to-speech, then, with `tts.cache_clauses` on and an agent
  whose calls run the talker (`settings.session.mode_for(...)`, as `api/providers.py` reads it),
  builds and opens the clause cache over it under `<agent>/clauses` and pushes the cache's own
  `aclose`; otherwise it hands the providers' text-to-speech on unchanged. An echo agent's calls
  never have one: the echo says the caller's words back, which the owner's reason ("what our
  agent produced") does not cover.
- **Ole5's part:** run T's arm only (run I, below). `first_audio.py` (329) gains `--clause-cache
  on|off`, off by default; `AudioReplay` (`first_audio_replay.py`, 242) builds the cache over its
  counting voice in `__init__`, opens it in `start` before `call_of.start()`, takes its counts
  for each recording's attempt, and drains it in `aclose`; the run clears it once the smoke call
  has passed (`first_audio.py:167-171`), which also clears the takes of the replay's own
  progress lines (`AudioCall.start` says them through its text-to-speech,
  `testing/audio_call.py:150-156`); `FirstAudioLine` (`evals/measure_lines.py`, 157) gains
  `clause_cache: ... | None = None`. Ole5 sets nothing in its own settings or server until the
  keep rule says so.
- **What observers see.** No new public event. The call report's `ModelUsage`
  (`core/events.py`) gives, for each Orpheus model, fewer `requests` and `characters` and more
  `cache_hits`, its docstring widened from the phrases to the phrases and the clauses; each
  reply's span gives its `cache_hits` and `requests`. A turn's time to first audio counts a held
  first clause's audio as it counts a phrase's (`voice/session/turn_book.py:202-211`); the
  turn's `tts_first_audio_ms` is the first *requested* clause's, so a held first clause moves it
  to the next or leaves it empty (`playback.py:115-121`). Logs: `clause_cache_opened`,
  `clause_cache_closed`, `clause_unreadable`, `clause_write_failed` (the error's type),
  `clause_cache_trimmed`: never a text and never a key, since a key is a hash of a short text
  that can be guessed back (GP-19).
- **What it never does:** keep the caller's audio or the echo's words; keep a take that failed,
  was cut short, gave no audio or was stopped; play a take for any text but the one it was made
  from, in the same language, voice, adapter and trimming; send a request of its own; fail or
  delay a clause on a disk error (a miss, then the request); write outside its folder, or remove
  a file not of its own naming (GP-21); ask consent (the owner's ruling); log a text or a key.
- **"No user will hear the info of another."** The audio is a function of the key alone, and
  the key holds the whole text, so a hit says exactly the words the agent is saying to this
  caller now. A passage is the knowledge base's, the same for every caller. A ticket number
  reaches speech only in an outcome line, unique to its ticket, so a hit only when that line is
  said again in the call, and in a status's last four digits of the caller's own tickets
  (invariant 3). A read-back renders the model's summary of what the caller asked: kept as
  audio, it is heard again only by a caller whose read-back is the same word for word. Said
  plainly: a hit starts sooner than a request (no first byte to wait for), so a caller who can
  make the agent say a clause exactly, a read-back of a summary they dictate among them, could
  tell whether that clause was said in some call since it was last removed; the guard keeps the
  talker from saying an ID it has no evidence for, and a free-text clause must match to the
  character. The agent judges it negligible and proposes nothing (the owner's rule of 2026-11-03,
  no hardening rounds). At rest the cache keeps the agent's words from calls as audio,
  read-backs of callers' requests among them; the traces keep the same text already (D-079).
- **The invariants.** *D-033* is amended: "Text built from heard words never reaches the phrase
  cache" stays true of the phrase cache, which holds only the declared phrases; Block I's decision adds the
  clause cache, for every clause a talker call speaks (a read-back too), never the echo's words,
  and closes the sentence that left caching talker clauses for later. D-033's rule of keying on
  the text sent, never the text written, is the clause cache's too. *Invariant 8*
  (`docs/SECURITY.md:151`) gains a sentence: the agent's own synthesized voice (the phrase cache
  and the clause cache) is not call audio and is kept with no consent (the owner, 2026-11-10),
  though the clause cache's takes say the agent's words of a call; SECURITY.md's trust
  boundaries gain a row for call content at rest under `storage.var_dir` (the clause cache's
  takes beside the outbox and the test console's files), not only in Phoenix. *Invariant 2*
  holds: the guard reads each clause before it is asked for, and a hit plays exactly that
  text's audio; Block G's filter sits before both. *Invariant 3* holds: the cache gives no tool
  or caller anything. *Invariant 7*'s lock file keeps one writer a folder. *GP-18:* off by
  default, a characterization test proving the off path unchanged; the repeat's fix is not
  behind the setting, since it corrects what a caller hears and no registered run says a reply
  again. *GP-19*, *GP-21*, *GP-22*: above. D-066 and D-067 are not touched.
- **Tests** (new files where a test file is near the cap):
  - `tests/t2_agentic_voice/adapters/test_clause_cache.py` (new), on a fake text-to-speech and a
    `tmp_path` folder. *The key* (adversarial): a take kept for a text is never given for another
    (one character more, a space more, one digit changed, the other Arabic preset, the other
    voice, the other model, `trim_silence` flipped, another adapter's name), and is given for the
    same text, language, voice and adapter in a later cache over the same folder. *What is kept:*
    a whole take, as it came; nothing for a take that raised mid-stream, came back cut short,
    gave no audio or was closed after its first chunk, and no `.part` left. *The files:* a
    truncated file, a stereo or 8-bit WAV, a file that is no WAV, a header counting more frames
    than its data, a file over 4 MB, each a miss, removed, counted, and kept anew by the next
    take; a `.part` left from a crash removed at `open`, and a file of another name left
    untouched (GP-21). *The bound*, *at once* (two takes of one key, a refused rename, a refused
    write), *slow or gone*, `aclose` draining and never closing the wrapped adapter, `clear()`,
    and leaks (`tests/leaks.py`).
  - `tests/t2_agentic_voice/adapters/test_phrase_cache.py` and `test_phrase_cache_files.py`
    unchanged and passing once the WAV helpers move.
  - `tests/t2_agentic_voice/voice/test_tts_bridge_held.py` (new; `test_tts_bridge.py` is at
    377): a held clause plays with no request (no `Synthesizing`; `ClauseQueued` `held`,
    `requested_at` None; then `ClausePlayed`); a miss as today; a stop that lands while the take
    is read drops it unplayed; a text-to-speech that is no `HeldSpeech` gives today's events in
    today's order (the characterization test).
  - `tests/t2_agentic_voice/voice/session/test_held_clauses.py` (new;
    `test_call_report.py` is at 359): a held clause is a cache hit in the call's usage and the
    reply's numbers, with no characters; a reply said again that holds a held clause says it,
    never looking it up as a phrase; a repeat sends each clause's text as sent and in its own
    language (a caption with digits sent as the speaking rules said it; an English clause of an
    Arabic call in the English voice); the existing repeat tests that read the text sent are
    updated.
  - `tests/t2_agentic_voice/api/test_runtime.py`: with the setting off, the calls get the
    providers' text-to-speech itself; on, for a talker agent, a clause cache under
    `var_dir/<agent>/clauses`; for an echo agent, none; the fixed phrases declared on the
    unwrapped one; the providers' text-to-speech closed once.
  - `tests/t2_agentic_voice/testing/test_audio_call_clauses.py` (new): two `AudioCall` calls of a
    talker agent saying the same reply over one clause cache; the first sends each clause's
    request, the second none for them (the requests counted, not the times: `AudioCall` runs on
    the system clock).
  - `tests/t2_agentic_voice/core/test_settings_clause_cache.py` (new; `test_settings_checks.py`
    is at 375): the two settings' defaults and bounds; `test_facades.py`: `stores`' two new
    names.
  - Ole5, `tests/ole5_voice/evals/test_first_audio_cache.py` (new; `test_first_audio.py` is at
    388): the flag builds the cache in the run's folder over the counting voice; it is cleared
    once the smoke call passed; a repeated attempt's counts are kept apart; the history line
    holds the counts; the hits are split between each item's first variant and the rest.
- **Size** (recounted at `4dc1f23`): `voice/session/speaker.py` 387: +2 in `queued`, line 274
  rewritten in place, its module docstring reflowed so it stays at 387; `api/runtime.py` 393:
  the phrase cache's lines move to `api/voices.py`, net −1 or −2. Not touched: `talking.py` 397,
  `call.py` 396 (its `ClauseQueued` case unchanged), `testing/text_call.py` 396 (`TextCall`
  never synthesizes), `voice/calls.py` 395 (it passes the text-to-speech it is given),
  `interrupter.py` 388, `read_back.py` 391, `agent/turn.py` 379. With room:
  `voice/tts_bridge.py` 249, `voice/tts_output.py` 73, `session_events.py` 263, `playback.py`
  319, `echo.py` 157, `usage.py` 123, `domain/ports/text_to_speech.py` 85,
  `core/settings/tts.py` 75, `phrase_cache.py` 285 (shrinks), `stores.py` 13; Ole5's
  `first_audio.py` 329, `first_audio_replay.py` 242, `measure_lines.py` 157,
  `first_audio_score.py` 253. New: `clause_cache.py` (about 250, under `size_watch`'s 300),
  `wav_files.py` (about 60), `api/voices.py` (about 60), and the new test files above. The disk:
  a take is mono 16-bit at 24 kHz, 48 KB a second; run T's dev requests averaged 39 characters
  in Arabic and 46 in English, so at about 14 characters a second with Orpheus's 0.4-0.7 s of
  leading silence a clause is about 0.17 MB (the agent's estimate), and 512 MB holds about 3,000.
- **Risks:** a repeat said wrong if a held clause were marked `cached` (pinned by a test); a stop
  during the read (pinned); one bad take, clipped or mispronounced but not flagged cut short,
  played to every caller who gets that text until it is removed, and the same if Groq changes a
  model under its name (the remedy: delete the folder; no command proposed); disk at rest
  (invariant 8's text, `data-and-privacy.md` and the roadmap's item on what callers who are not
  the developers must be told gain it); `ModelUsage.cache_hits` (public) now counts clauses too
  and `tts_first_audio_ms` skips a held first clause, so run T's reading allows for both;
  `stores` gains two names; `ClauseQueued` gains a field with a default, so `TextCall`'s
  hand-made events (`testing/text_side.py:220`) need no change; H and I both regenerate the
  settings docs, made again after the second merges.
- **Docs:** Block I's decision (D-033 amended; D-032's sentence on `stores`); `docs/SECURITY.md`'s invariant
  8 and its trust-boundary row; the design's 10.4 ("TTS caching") and its storage row; the
  guide's `data-and-privacy.md` (a row for `<agent name>/clauses/`, and "It deletes none of it"
  amended, since the cache removes its own takes past its bound), `latency.md` and `concepts.md`
  (a reply said again); `docs/design/evaluation.md` (run T's `--clause-cache`); the module
  docstrings that say only declared phrases are kept (`adapters/phrase_cache.py:8-10`,
  `voice/session/io.py:149-157`, `domain/fixed_phrases.py:40-43`, `voice/session/echo.py:13-16`);
  the generated settings; the roadmap's item on what callers must be told gains the agent's words
  kept on disk; a debt row, the phrase cache's key leaving out `tts.trim_silence`
  (`phrase_cache.py:250-254`).

## The measurement, registered before any result

- **Data:** scenarios in `apps/ole5-voice-agent/evals/actions/`, Saudi, MSA and English, split by
  scenario into dev and held-out before any run: a plain ticket, an eager yes, a bare yes, a yes
  over the summary, a correction inside the read-back, a no, a mumble, a refusal, a timeout with
  and without a lookup, status of one's own tickets, a request for another's, a handoff over an
  answer, a handoff asked for by mistake, and a passage carrying a fake number; and, added with
  Block F before any run, four the yes rule's lists leave unplaced (D-082): an unlisted yes once
  the closing question ended, an unlisted go-ahead over it, a yes with a change, and a
  hesitation in an unlisted spelling; and, by the owner's ruling of 2026-11-10 before any run, a
  note on a ticket made in the call (`ticket_note`: a39, dev, English; a40, held-out, MSA).
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
  Block F's scenarios passed it; "The owner's decisions"), its dry estimate with the note pair
  at most $1.76 for dev and $1.73 for held-out; M7 takes up `simulate`. No default moves except by a registered keep rule
  (GP-18).

- **Run H, each turn's language** (Block H; its folders named apart from the history's
  `h1-large-v3`, `h2-turbo` and `h3-held-out`, for example `lid1-dev-silero`).
  - *Data:* the golden set's dev split, 292 variants of 98 items (Saudi 128, MSA 51, mixed 26,
    English 75, and 12 of silence, noise or echo), each fed as a fresh call; held-out, 131
    variants of 42 items (8 English items, 22 variants), read once, by aggregates, after dev.
    Three call languages for every variant: (a) the ordinary call, the item's own language
    (English items in an English call, the rest in an Arabic one), where `session` is right by
    construction; (b) an Arabic call, run X's condition; (c) an English call. Every pass at one
    commit, each alone, its history line kept aside until the last has run; a one-variant smoke
    first.
  - *H1, the classifier, no spend* (`poe eval-languages`): the file-fed pipeline at real-time
    pace with Ole5's two languages and a speech-to-text that answers at once and records the
    language each request named. Passes, in order: off (`session`), Silero, ECAPA, off again, at
    the registered `from_s` 2.0 s, `min_share` 0.7 and 2 threads (Q20). Each turn's verdict, when
    it was asked and came, when its hold began and when the turn ended are recorded; each call
    language's choice is computed from that record with the library's pure rule, as a talker
    call makes it, when the held request goes at the hold's start, so a verdict counts as in time
    only when it came before. One call at a time, so no turn finds the classifier busy.
  - *H2, Whisper* (`poe eval --language-from <H1 pass>`): `whisper-large-v3` with the prompt (run
    W's W1 settings), at H1's commit. On dev, three baselines, (a) every variant in its item's
    language, (b) every variant as Arabic, (c) every variant as English; then, for each
    classifier and call language, only the variants whose language H1's rule changed are sent,
    the rest taken from that call language's baseline (Whisper's noise on dev was d = 0 twice,
    D-024 and D-066). A variant is sent whole, in the language the rule named for its first turn;
    a variant whose turns got different languages is counted and reported.
  - *Held-out*, once after dev, aggregates only: whole runs, every variant sent: baselines (a) and
    (b), and the kept arm in calls (a) and (b), 4 runs at about $0.042 each. H1's held-out passes
    (off, the kept arm, off) keep each variant's language code in their run folder for those runs
    to read, never printed, scored or shown by variant. Each held-out line keeps the accuracy, the
    English stratum's accuracy and, from H1, the paused requests' cut-offs; a condition whose
    aggregate a line does not show is recorded as not read, never guessed.
  - *Metrics:* the matcher's accuracy by item and by stratum; text from silence on the 12
    silence, noise and echo variants after the live filter; from H1, the share of each `by`, the
    verdict's time (median, p90), the share in time and how late the late ones were; against the
    two off passes, the paused requests' cut-offs, and the turn-end delay as the median of paired
    differences (same clip, same turn) against the mean of the two off passes.
  - *The keep rule.* An arm passes on dev when all hold: (1) *English in an Arabic call:* the
    English items better beyond the noise against baseline (b) (the sign test by item, p < 0.05,
    more better); (2) *the ordinary call:* at most 2 items worse than baseline (a), none a
    `request`, `paused_request` or `ticket_number` item; (3) *text from silence:* no more
    characters than baseline (a)'s; (4) *time:* no more paused cut-offs than the worse off pass
    plus one (D-067's measured noise, 1 verdict of 51), and a median paired turn-end difference
    that is not both over 50 ms and over the two off passes' own. Of two arms that pass, the one
    with more English items right in an Arabic call; within 2 items of each other, Silero, which
    needs no torch. Arabic in an English call (c) is reported, no condition. Held-out then
    confirms once: the English stratum's accuracy in an Arabic call above baseline (b)'s, the
    ordinary call's accuracy no lower than baseline (a)'s, and condition 4 from H1's held-out
    passes. Only then does the arm become the setting Q19 names, recorded in Block H's decision. A miss is
    recorded and goes to Future improvements, not re-run.
  - *Check the conditions first:* each baseline against its recorded run (W1's dev accuracy
    0.442; run X's English items 0.027); one that moved beyond the noise makes the run
    unreliable: said, and nothing else read.
  - *Expected,* from the offline check, and from the download step's smoke, whose timings are
    added here before H1 runs: ECAPA passes 1 to 3, the English accuracy in an Arabic call near
    0.5 against 0.027, the 1 to 2 s English turns still Arabic by design; Silero fails 2
    (in-sample it sent four Arabic requests as English); ECAPA's verdict comes late on turns a
    little longer than 2 s; whether its CPU moves the turn ends is condition 4's.
  - *No time-to-first-audio run:* the block adds no wait, so the first audio moves only through
    the turn ends, which H1 reads; a run T pass is added, as a dated amendment, only if condition
    4 fails or is near its bound.
  - *Cost and time:* H1 spends nothing, about 30 minutes a dev pass at real-time pace (the
    agent's estimate), so about 2 hours for four, and about 40 minutes for held-out's three; H2
    on dev at most 9 runs' worth of requests, about $0.85 at run W's $0.094 a full dev run, in
    practice the three baselines and the changed variants, about an hour at 20 requests a minute;
    held-out about $0.17 and 30 minutes. A cap of $3 (the owner, 2026-11-10: "I don't care about
    the money as much as I care about wasted time and useless runs"). Read once: held-out.
- **Run I, the clause cache** (Block I; its folder `i1-dev-120b`).
  - *The question* (the owner's "their effectiveness and the latency improvements or delays they
    bring"): how many clauses repeat in Ole5's calls, how many Orpheus requests that saves, how
    much sooner a held clause plays, and whether looking up and keeping takes delays anything.
    The roadmap's count, before any run: with today's spoken prompt, about 5% of model-written
    clauses repeat across questions in run K's dev replies, mostly short openers ("I'm sorry,",
    "Yes,", «نعم،»).
  - *Which run:* run T (`poe first-audio`), the only run that speaks; runs K, S and A are text
    calls that never synthesize, and run E's echo agent never has the cache: none of their
    baselines moves.
  - *Data:* run T's dev split as plan 006 registered it, 17 items and 72 variants (t0-dev-120b's
    history line), each a fresh call, in the run's order. Held-out is not run: the rule and the
    bound are set here, nothing is fitted to results, so nothing waits to be confirmed fresh
    (evaluation.md, "Fitted, then fresh").
  - *The arm, I1:* the block's commit; Ole5's talker with its tools; `gpt-oss-120b` at medium, as
    T0's dev run; `tts.trim_silence` off; `--clause-cache on`, the cache in `<out>/clauses`, new,
    and cleared once the smoke call has passed (the smoke plays dev's first recording, which the
    run then plays again, `first_audio.py:226-239`), so the first measured call starts cold; a
    recording replayed after a rate limit (`first_audio_run.py`) has its look-ups counted apart
    and left out of the shares.
  - *What is read:* the hits as a share of the clauses asked for, in each item's first variant
    (which can hit only another question's clauses, the roadmap's "across questions") and in the
    rest (the same question again in other words) apart; Orpheus requests per call minute, sent,
    and with each hit added back; each look-up's time, hits' and misses' apart (median, p90,
    most); Orpheus's own first audio in the same run, beside a hit's read; the time to first audio
    by path, as run T scores it; the turns whose first answer clause was held, their count and
    their time to first audio against the other turns'; the takes kept, not kept by why, files
    unreadable, writes failed, megabytes at the end.
  - *The keep rule.* `tts.cache_clauses` becomes True by default (Q25) only when I1 shows all
    five, each number the agent's own: (1) no call failed, no clause failed, and no clause went
    unsaid because of the cache; (2) the hits in the first variants at least 2% of their clauses
    asked for (the agent's reasoning: a cache that starts empty hits only the later sayings of a
    clause, so its share is below the roadmap's count of clauses that repeat; the share over
    every variant is reported, not gated); (3) a miss's look-up at most 2 ms at p90 and 20 ms in
    every case; (4) a hit's read at most 50 ms at p90; (5) every run T target T0's dev run met
    (`no_search_median_ms`, `no_search_p90_ms`, `search_median_ms`, `search_p90_ms`, its history
    line) still met. Otherwise the default stays off, the result is recorded, and the cache stays
    for a team to turn on.
  - *Expected* (the agent's): hits about 5 to 10% over every variant, fewer in the first ones;
    requests per call minute down by about the same share; a miss's look-up in microseconds and a
    hit's read a few milliseconds, against Orpheus's first byte of about 0.25 s; the time to
    first audio by path within the spread of plan 006's T runs, since hits are few and the chat
    model's time dominates.
  - *Cost and time:* about T0's dev run, $0.60 (t0-dev-120b's `cost_usd` 0.597), less each hit's
    characters, under the cap the run is given; its time bounded by Orpheus's pacing at
    `run.tts_rpm` 5 (T0's dev sent 351 Orpheus requests, about 70 minutes of pacing alone), and I1
    sends fewer. About 60 MB of takes in `<out>/clauses` (the agent's estimate). Run once and read
    once; a miss of the keep rule is recorded, not re-run.

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
  - **Left**: TD-142, its first item the owner's call (Ole5's ticket-number wording), since
    paid by the owner's ruling (the rulings' build, below).
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
- 2026-11-10: Two of the whole-code review's consent findings fixed, each test first. A turn
  begun in the gap before a read-back's first audio, the summary playing whole over it, reached
  the talker with no decline and left the read-back current, so a later bare yes confirmed the
  old draft: a turn handed to the talker while a read-back is current now declines it as a
  `correction` (`Confirming.handed`; `test_yes_turns.py`, the question played or still playing).
  The echo rail read only an exact run of one line's words, so an echo across the summary's end
  into the question, or a word one letter off («سجل الطلب» for «أسجل الطلب»), confirmed on the
  model's `send`: it now reads the lines heard as the interruption rule reads its own words
  (`interruptions.own_words`; `test_yes_rule_send_alone.py`). D-081, D-082, the design's 8.3 and
  the guide's `safety.md` and `testing.md` updated.
- 2026-11-10: Two of the whole-code review's claim findings fixed, each test first. A
  `reports_on` result that succeeded backed any claim about its actions, so after a status that
  found nothing (Ole5's `ticket_status` with no ticket, or digits that match none) "I've opened a
  ticket" or «تم فتح التذكرة» was said with no ticket: such a result now backs a claim only when
  it holds an ID-shaped token (`claims.holds_an_id`, in `SpeechGuard` and `TextCall`'s checks
  alike). Rule A read only the reply language's phrases, so a claim the model wrote in its other
  language passed with no record, a passage's made-up ticket number with it: both now read every
  language's (`claims.every_language`, `any_action_claims`), and `SpeechGuard` takes no
  language. `test_talker_claim_evidence.py`, `test_text_call_claims.py`,
  `test_action_call_claims.py`, `test_claims.py` and Ole5's `test_ticket_claims.py`, in both
  languages; D-081, the design's 8.2 and the guide's `safety.md`, `concepts.md` and
  `tools-and-actions.md` updated. The stricter rule the review proposed, a status backing only a
  claim that names a number it holds, is the owner's call: TD-144 (since ruled, "Number or same
  reply", below).
- 2026-11-10: Two of the whole-code review's session findings fixed, each test first, on the real
  yes rule (`test_yes_turns_between.py`). The gap turn's decline (`Confirming.handed`, above) is
  now tested on the real rules with its early start too: a turn begun before the read-back's
  first audio whose `held` transcript starts the talker once the read-back ended declines it as
  a correction. An earlier action's outcome landing while a second read-back waited for its
  answer was said straight after that read-back's closing question, so the caller's "yes" or
  "yeah thank you" to the outcome confirmed the second action: an outcome now waits for no
  read-back being current too (`ActionJob._boundary`, given the call's `Confirming`), and is said
  once the answer's reply has played. The guide's `tools-and-actions.md` and `concepts.md` and
  the design's action flow updated.
- 2026-11-10: The whole-code review's run A scoring finding confirmed: Ole5's read-back and
  action lines are Saudi only (TD-139), and run A asks the judge the register of a reply's every
  clause but the fixed phrases, so each MSA turn answered by a read-back (a07, a13 and a37 in
  dev; a02, a12, a20 and a26 in held-out) fails its register whatever the model wrote, and the
  language target cannot be met. The owner had already ruled on it (MSA read-backs, the check as
  registered: The owner's decisions), so the fixer's change to the scoring, the register asked
  of the talker's words alone, was withdrawn; Ole5's MSA lines are built with the rulings. Kept
  from it: `TextTurn.clauses` marks each line of the runtime's own for an action
  (`HeardClause.template`, read as the call's checks read them, `text_actions.own_lines`;
  `test_text_turn_lines.py`), and the guide's `testing.md` names it.
- 2026-11-10: The owner's four rulings built, one builder a ruling in turn, each test first, then
  one reviewer a ruling and one skeptic a finding, and a last pass for what was missed (D-081):
  - **The caps count only real writes**: both caps leave out `rejected` and `not_sent` rows
    (`ports.outbox.NOT_WRITTEN`, in both stores and the runner), so a refused or never-sent write
    leaves the caller a second try; a `flagged` one (`unknown`) still holds its place
    (`test_action_caps.py`, `test_outbox.py`). TD-143's second item paid.
  - **MSA lines**: an `ar-SA` reply to an MSA caller reads an action's texts in `ar`
    (`language.wording`, `action_declaration.read_in`), the library's own lines in MSA, the
    outcome as its read-back was (`ReadBackPlan.wording`), every line still in the `ar-SA` voice;
    Ole5 gives every line of its three actions an MSA text, its closing question «هل أرسلها؟».
    Run A's oracle reads the register as the withdrawn patch did, and with the old lines a02,
    a07, a12, a13, a20, a26 and a37 failed; with the MSA lines all pass
    (`test_ticket_calls_msa.py`, `test_action_wording.py`, `test_action_call_registers.py`).
    TD-139's MSA item paid; the session's notices, the guard's line and Ole5's search line are
    still Saudi for an MSA caller, outside the ruling.
  - **The ticket number as a claim**: `NUMBER_CLAIMS` through `guard.claims`
    (`tickets/tools.py`'s `with_ticket_claims`, in the server, run A and the call tests; runs K,
    S and T unchanged, GP-18), and Ole5's `done` lines reworded so none holds a phrase
    (`test_ticket_claims.py`, `test_lines.py`, a29 and a30's blocked number in
    `test_action_play.py`). TD-142's first item paid; the question «وش رقم تذكرتك؟» blocked while
    no ticket is held, in TD-134.
  - **Run A's note pair**: the kind `ticket_note`, a39 and a40, a scenario's `noted`, a note
    counted from the mock and one beyond its confirmed writes a violation; 40 scenarios, the dry
    estimate above (`test_action_scenarios.py`, `test_action_play.py`, `test_action_score.py`).
  - **The review**: one finding, «رقم تذكرتك» with bi-, li- or ka- written onto it read as no
    claim; refuted as a widening of the owner's two phrases (the design's 8.4: a wording on no
    list passes), and run A's a29 and a30 still fail a turn that says such a number. Ole5's
    `VERSION` stays `2026-11-10.1`: no measured run was stamped with it before these changes,
    and a bump would move the version of runs K, S and T, whose talker did not change. With the
    caps' change a talker that calls `create_ticket` again after a refusal (a15, a16) now hears a
    second read-back, not `cap_per_call`; their `made = 0` holds with no yes.
- 2026-11-10: The owner's ruling on TD-144 built, "Number or same reply" (D-081), test first,
  one reviewer and one skeptic a finding. Rule A tells a status's evidence from the record's
  (`ActionEvidence.source`): the record backs any claim about its action as before; a status
  backs only a clause that holds one of its numbers (its last four digits too, as Ole5's
  `ends_in` gives them), or a clause with no number after an earlier clause of the same reply
  that the guard passed named one (`check_claims`'s `earlier`; `SpeechGuard` keeps the clauses
  it passed, `TextCall`'s check the same for each turn's talker reply). The TD-144 case, "I've
  opened a ticket for your reports page" after a status of an older ticket, is blocked
  (`test_claims.py`, `test_talker_claim_evidence.py`, `test_text_call_claims.py`, Ole5's
  `test_ticket_claims.py`, in English and Saudi Arabic). Ole5's instructions tell the talker to
  say a ticket's last four digits first, before what happened to it, since an Arabic comma
  ends a clause; run A's oracle already does, so all 40 scenarios play as before. The review's
  three findings were refuted (the ruling accepts each); the guide's "sentence" became
  "clause" from the first. TD-144 keeps its other part, evidence keyed by the action's name
  alone. `VERSION` stays `2026-11-10.1`, for the reason the rulings' line gives.
- 2026-11-11: The test console (D-083, its own session's branch `test-console`) merged here at
  the owner's word ("also merge the test-console so I can use it to test"), through the side
  branch `merge-test-console` (its two doc conflicts resolved there, both sides kept, its gate
  green). It observes the runtime the app builds, so Ole5's served talker keeps
  `with_ticket_claims`.
- 2026-11-11: Blocks G, H and I drafted for the owner's approval ("Tracks", runs H and I in "The
  measurement", Q10 to Q25 and the downloads in "The owner's decisions"): one drafter a block,
  read only, each checked against the code by one skeptic, then one synthesis. Block G's check of
  the stored texts already ran: none of run K's and run S's 5,747 dev clauses, their 1,415
  searches or the knowledge snapshot holds a character it would take out. Nothing built and
  nothing downloaded.
- 2026-11-11: Block G built at the owner's approval ("Approve Block G"; Q10 to Q14 each (a)),
  as "Tracks" drafts it (D-084): by one builder for the library and one for Ole5, the docs and
  the stored-data check, each test first; one reviewer, who found nothing that breaks a call or
  a contract, so no skeptic and no fix ran; then a check of every bullet against the diff, which
  found nothing missing and fixed four small doc lines. The stored-data check through the built
  rule (GP-16), read only: `uv run --offline python -I <scratchpad>/block_g/stored_check.py
  <main checkout>/var`, with Ole5's languages (`ar-SA`, `en`) and its 17 declared terms, over the
  15 dev runs the check above names and the snapshot: 5,747 clauses (205,751 characters), 1,415
  `search_knowledge` argument values, and 128 snapshot records (1,528 texts, 226,809
  characters), none changed, so the default stays on. `agent/turn.py` ends at 378 lines; Ole5's
  `evals/action_run.py` at 379.
- 2026-11-11: Tracing the owner's question "can he cancel the ticket all together and start to
  ask another question or open another ticket?" (one reader a path, one skeptic a claimed gap,
  read only): a plain no after the read-back cancels it with nothing sent, the talker answering
  in its own words, and a cancelled draft counts toward no cap, so another question or ticket
  follows. Three gaps confirmed and put to the owner with fixes, none built: a question, or a
  new request the model reads as unclear, in answer to the read-back is asked again (the
  consent check's instruction names "a question" as unclear, the agent's wording, not a
  ruling), its words never reaching the talker; «خلاص» alone over the summary is ignored, being
  both a stop word and a filler; and a cancel said over the summary reaches the talker as a
  correction. Run A holds no bare question to a read-back. A false claim after a cap's refusal
  joined TD-144's row.

## Decision log

- 2026-11-11: What Block G's build chose where the spec left it open (D-084): `Kept(text,
  changed, labels)`, the log line's `characters` and `scripts`, and the turn span's
  `turn.stray_scripts` as one comma-separated string, since a span attribute holds no tuple; a
  number sign that is no decimal digit (⅓, ①) kept, as a symbol is, unless in a removed range;
  a fullwidth form whose ASCII form the agent's scripts would not keep taken out, so filtering
  twice equals once; `remove_stray_script` refuses a tag that is not a preset's, and no text
  makes it raise (arguments too deeply nested for Python's reader are kept as written); the
  empty-clause rule keyed on the reply's text alone, not a tool call's arguments; run A's count
  carried through `action_call.py`, `action_play.py` and `action_card.py` as well, each dev
  scenario's on the scorecard, every new field 0 by default; and the fixed-set example "Bug重",
  since "Technical" is no ticket type of Ole5's.

- 2026-11-11: The roadmap's three M5 items as Blocks G, H and I of this plan, not a plan of
  their own: each is small beside the actions, Block G must land before run A, and H and I share
  run A's branch and the owner's approvals. Block G is ordered first; H and I wait for run A,
  since neither changes a text call.
- 2026-11-10: The owner's four rulings before run A ("The owner's decisions"), built as one
  change: Ole5's MSA lines for its three actions, a run A pair for `add_ticket_note`, «رقم
  تذكرتك» and "your ticket number is" as Ole5's claim phrases, and the library's caps counting
  only writes that may have reached the system. The whole-code review's change to run A's
  scoring (the register asked of the talker's words alone) was withdrawn for the first. What the
  build chose (D-081 holds it):
  - *The number's phrases claim any action* (`guard.claims`), not each maker's list, since rule
    A asks evidence of every action a phrase names; Ole5's `done` lines hold none, since the
    talker copies them and `TextCall` reads a copy of a runtime line as that line.
  - *MSA is a wording, not a language*: Ole5 still declares `ar-SA` and `en`, its `ar` texts read
    for an MSA caller and spoken in the `ar-SA` voice; an action with no `ar` text says its
    `ar-SA` one.
  - *The caps leave out what was surely not written* (`NOT_WRITTEN`) rather than list what
    counts, so a state added later counts.
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
    (TD-142). Since ruled: the any-action phrases, the cut answer accepted (the rulings' entry
    above, TD-134).
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
- 2026-11-10, before run A, four questions put with the agent's recommendations:
  - *MSA read-backs.* Ole5's read-back, sending and outcome lines exist in Saudi Arabic and
    English only, so in run A's MSA scenarios an MSA caller hears a Saudi read-back, and those
    turns fail the registered check of the reply's register. The owner chose "Add MSA
    read-backs (Recommended)": Ole5 gets MSA versions of those lines, so an MSA caller hears
    MSA, as the talker already answers them, and the check stays as registered.
  - *A run A pair for `add_ticket_note`.* Asked whether to add one before any run, the owner
    answered "What is the difference between create_ticket and hand_off? And Yes add a pair"
    (the question answered in chat).
  - *The ticket number as a claim* (TD-142's first item). The owner chose "Yes, make them a
    claim (Recommended)": «رقم تذكرتك» and "your ticket number is" become Ole5's claim phrases,
    blocked unless a ticket was made in the call, and Ole5's done lines are reworded so none
    holds them.
  - *What counts toward the caps* (TD-143's second item). Asked whether a refused or never-sent
    write counts toward the one-action-per-call cap, the owner first asked "Explain to me why
    the cap exist in first place"; told that a cap bounds how much a misjudged, repeated or
    injected action can write, per call and per caller a day, they answered "Count only real
    writes": only rows whose write may have reached the system count (`sending`, `done`,
    `flagged`), not one the system refused or that was never sent, so the caller can try again.
- 2026-11-10, after the rulings' build, on TD-144: a status result that lists any ticket backed
  every claim about the actions its tool reports on, so after a caller asked about a ticket from
  an earlier call, "I've opened a ticket for your reports page" passed with none made. Put with
  two options, the agent's recommendation first ("Number or same reply": a status backs only a
  claim that names one of its numbers, or one in a reply that already said one; "Number always":
  every claim a status backs names a number), the owner chose "Number or same reply". A claim
  the call's record backs is unchanged.
- 2026-11-10, on the roadmap's three M5 items no block held yet (a per-turn language
  classifier, every clause cached on disk, no stray script): asked "Should I draft these three
  as new blocks in plan 007 for your approval, with the script filter first so it lands before
  run A?", the owner answered "Yes, and I agree to download the dependencies and models". So
  Blocks G, H and I ("Tracks") and runs H and I ("The measurement") are drafted, each block
  built only once approved, with Q10 to Q25 and the exact downloads below.
- 2026-11-11, on Block G: asked "Approve Block G with the agent's recommendations for Q10 to
  Q14?", the owner answered "Approve Block G". So Q10 to Q14 are settled as the agent
  recommended, (a) each, and Block G is built before run A. Blocks H and I, Q15 to Q25 and the
  downloads still wait for their own approval, after run A.

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

- **Q10. Block G on by default.** *Settled 2026-11-11: (a).* The filter changes nothing written in the agent's scripts, and
  none of the stored measured texts (5,747 clauses, 1,415 search calls, the snapshot). Options:
  (a) on by default, `guard.remove_stray_script` to turn it off; (b) on always, with no setting;
  (c) off by default until a run measures it. **The agent recommends (a):** it fixes the defect
  the owner saw from the next call on; no measured outcome moves, and run A records each
  removal; the setting is the off arm a later run can compare and a team's way out. (c) leaves
  the demo's defect in run A.
- **Q11. What the filter covers.** *Settled 2026-11-11: (a).* Options: (a) everything the talker writes: its text and the
  string values of every tool call's arguments, a search's query among them (never a key), so
  the trace, the public `ToolStarted` and `ToolFinished` events and the test console show what
  the voice and the captions do; (b) its text and its action calls' drafts only, a search's
  query kept as the model wrote it, so the trace, the events and the test console can still show
  a stray character; (c) its text only, so a ticket summary holding one is read back, captioned
  and written to the ticket with it. A tool's result and a card stay the team's text under all
  three. **The agent recommends (a):** it is the ruling's "every text the talker writes passes a
  script filter before it goes anywhere", and none of the 1,415 stored searches would change.
- **Q12. Emoji and other pictographs.** *Settled 2026-11-11: (a).* The ruling keeps "digits and punctuation" beside the
  scripts; arrows, quotes, %, currency and math signs stay either way, since the speaking rules
  say an arrow as "then" and the stored replies hold 257. Options: (a) pictographs taken out and
  counted with the stray script; (b) left as written, to the prompt, which already asks for "no
  lists, markdown, emoji or symbols" (`agent/prompt.py:71-72`). **The agent recommends (a):** a
  voice cannot say one, the owner asked that it never be shown, and no stored reply held one.
- **Q13. Latin in the Arabic presets.** *Settled 2026-11-11: (a).* Options: (a) `ar-SA` and `ar` write Arabic and Latin, so
  an agent that speaks only Arabic keeps its product names, codes, email addresses and links;
  (b) Arabic only, Latin coming only with an English preset. **The agent recommends (a):** 266
  of the 4,098 stored Arabic clauses hold Latin ("Ole5", "Ctrl", "PDF"). Ole5 declares both
  languages, so neither option changes Ole5.
- **Q14. What a removal leaves.** *Settled 2026-11-11: (a).* In the demo, «إ重新» leaves «إ», the start of the word «إعادة»
  the model meant, which no filter can restore. Options: (a) each character judged alone, as the
  ruling says; (b) the whole word that held a stray character taken out, so «إ重新» leaves
  nothing but «Outlook重启» loses "Outlook" too, and each word is held until it ends. **The agent
  recommends (a):** it is the ruling's words, it never loses a word of the agent's scripts, and it
  holds nothing back.
- **Q15. Where torch may live.** *Open.* ECAPA runs on PyTorch through SpeechBrain; the library installs
  no torch today (the torch check), and the owner chose one install with no extras (D-018).
  Silero's classifier needs nothing new. Options: (a) an optional extra of the library,
  `t2-agentic-voice[ecapa]` (SpeechBrain 1.1.2, torch 2.15.0, torchaudio 2.11.1 and the
  packages listed under "Downloads to approve"), installed here through a root dependency group
  and by no app; the torch check rewritten to every member's base install; on Linux, torch from
  PyTorch's CPU index, a promise this workspace's lock keeps and a team adding the extra keeps
  with the guide's lines; D-018's one install amended for this one extra; (b) ECAPA converted
  once to ONNX outside the repository and run on onnxruntime: no torch in any install, but a
  converted model whose verdicts must first be shown equal to the original's on the dev clips;
  (c) ECAPA measured only from a throwaway environment (`uv run --with`, nothing in the lock),
  built in only if it wins run H. **The agent recommends (a):** it is what the owner asked for
  ("implement both of them"), and it costs the base install nothing. With it, accepting the
  licences, the owner's call by the design's 13: SpeechBrain Apache-2.0, PyTorch's BSD-3-style
  set, torchaudio BSD, the rest BSD, MIT and Apache-2.0 but tqdm's MPL-2.0 AND MIT, the ECAPA
  model Apache-2.0, Silero's classifier MIT.
- **Q16. Where the model files are kept.** *Open.* Options: (a) a folder `stt.classifier_dir` names, with
  no default, outside every repository and `var/` (on the laptop, for example
  `%LOCALAPPDATA%\t2-agentic-voice\models\`), fetched once by hand and checked by SHA-256 at each
  start and by `t2v doctor`; (b) under `var/`, which git ignores, as the owner allows by name;
  (c) SpeechBrain's and Hugging Face's own caches, filled on first use, which reaches the network
  at a server's start, a host the design's 11 does not list. **The agent recommends (a).**
- **Q17. The language a short or unsure turn keeps.** *Open.* Options: (a) the language the call's last
  confidently classified turn was sent in, the call's own until one is: after an English
  question, the "yes" to its English read-back goes to Whisper as English; (b) always the call's
  language at join, so that "yes" goes as Arabic and the English read-back's yes words do not
  match it. **The agent recommends (a):** the owner asked that a call can change language
  mid-call, and the yes rule reads the read-back's language.
- **Q18. A verdict not in when the turn's request goes.** *Open.* Options: (a) the request never waits:
  the turn keeps the current language, counted `late`; (b) it waits up to a bound, for example
  300 ms, every wait added to the time to first audio. **The agent recommends (a):** run H
  records how late each late verdict was, so a bound can be weighed on numbers later.
- **Q19. What a kept arm changes.** *Open.* The library's default cannot need files no install brings.
  Options: (a) the library's default stays `session`; a kept arm becomes the setting Ole5's live
  calls run with, which the owner sets in their `.env` (`T2V_STT__LIVE_LANGUAGE=classified` and
  the classifier's keys), recorded in Block H's decision, the guide saying when a team should; (b) the
  library's default moves to `classified` with Silero, falling back to `session` with a warning
  when the files are missing. **The agent recommends (a):** a default that changes with the files
  on a disk is not one a measurement can stand behind.
- **Q20. The rule's two numbers.** *Open.* Options: (a) one registered pair (`from_s` 2.0 s,
  `min_share` 0.7), not tuned on dev, which has 75 English clips of one speaker; a failure on dev
  is reported, and another pair is a dated amendment before any further run; (b) a grid on dev
  with no spend (`from_s` 1.5 to 3.0 s, `min_share` 0.6 to 0.9), the best pair confirmed on
  held-out ("Fitted, then fresh"). **The agent recommends (a):** fewer runs, and nothing fitted to
  one speaker's 75 clips.
- **Q21. What the clause cache keeps.** *Open.* Options: (a) every clause a talker call speaks: the
  talker's clauses, a passage it reads, an action's read-back, its sending line and its outcome
  with a ticket number; never the echo's words; (b) the talker's own clauses only, not an
  action's lines, which hold a caller's details and seldom repeat; (c) as (a), but no clause that
  holds an ID or an email. **The agent recommends (a),** the owner's "cache everything we can":
  the same text is the same audio, and with the repeat's fix a reply said again within a call,
  an outcome line among them, is a hit.
- **Q22. How the cache is measured.** *Open.* Options: (a) one run T arm, the cache on and cleared after
  the smoke call, its mechanism read directly (each hit is a request not sent; each look-up and
  read timed), about $0.60 and the time of a T dev run; (b) two arms at one commit, the cache off
  and on, the time to first audio compared by path, about $1.20 and twice the time; (c) no run
  now, the default left off until the live rehearsal. **The agent recommends (a):** hits are a few
  percent of the clauses and the chat model's time varies by hundreds of milliseconds between
  runs, so a second arm would most likely answer nothing ("useless runs"); (a)'s fifth condition
  still reads the time to first audio against T0's targets.
- **Q23. Where the cache lives and how big it grows.** *Open.* Options: (a)
  `storage.var_dir/<agent>/clauses`, beside the phrase cache, no folder setting, at most 512 MB
  (`tts.clause_cache_mb`), the clauses played longest ago removed past it; (b) the same with
  128 MB; (c) a folder setting of its own; (d) no bound. **The agent recommends (a):** about
  3,000 clauses (the agent's estimate), and the short openers that repeat stay, since each hit
  keeps its clause; (d) would grow by about 0.17 MB for nearly every clause said.
- **Q24. The key's "speaking rules' version".** *Open.* Options: (a) none: the key holds the text sent,
  after the speaking rules and the pronunciation map, so a change that alters a clause's words
  gives it a new key; the language, model, voice, adapter and trimming are in it too; (b) a
  version constant in `domain/text/speaking.py`, hashed into every key and raised by hand, which
  empties the cache at every raise. **The agent recommends (a):** the roadmap lists the version,
  but no such version exists in the code, and the text sent already carries what it would mark.
- **Q25. Whose default run I's keep rule moves.** *Open.* Options: (a) the library's:
  `tts.cache_clauses` becomes True for every team; held-out is not run, since nothing is fitted;
  (b) Ole5's only: the library's default stays off and Ole5 turns it on. **The agent recommends
  (a):** the bound caps the disk, an echo agent never has the cache, and a team can turn it off.
- **Downloads to approve (Block H; Blocks G and I download nothing).** The owner agreed to the
  downloads in principle ("Yes, and I agree to download the dependencies and models"); this is
  the exact list, read from PyPI's JSON and Hugging Face on 2026-11-10 and 11, none fetched yet.
  Packages are kept in uv's cache (`%LOCALAPPDATA%\uv\cache`) and the worktree's `.venv`,
  through `uv sync --group language-id`, pinned in `uv.lock`; never in git. Sizes are the
  Windows cp312 wheels the laptop takes; the 21 new packages' wheels total 182,176,173 bytes,
  and installed they take far more (torch 2.5.1+cpu took 1,136 MB, scipy 99 MB and sympy 29 MB
  in the offline check's environment).
  - **The extra's three** (PyPI):
    - `speechbrain` 1.1.2 (uploaded 2026-10-14): `speechbrain-1.1.2-py3-none-any.whl`, 912,709
      bytes, sha256 `9fea4144c917ea58bcf13f17a1a1759179ed7472a30ec8416e7c7c8cf21d9c9a`;
      Apache-2.0.
    - `torch` 2.15.0 (2026-10-28): `torch-2.15.0-cp312-cp312-win_amd64.whl`, CPU only,
      126,738,207 bytes, sha256 `f2bd0a3709a7493a6ef2ac5a654111242a854439f7558f910b6b653b56f7504d`;
      `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0
      AND ISC AND MIT AND Zlib`. For Linux, later, from PyTorch's CPU index
      (`https://download.pytorch.org/whl/cpu`): `torch-2.15.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl`,
      209,530,490 bytes, recorded in the lock, not fetched on the laptop; PyPI's Linux wheel
      (539,172,785 bytes) would pull CUDA packages (cuDNN 9.26.0.51, `cuda-toolkit` 13.2.2,
      `triton` 3.9), which the step refuses. Fallback if the smoke fails: torch 2.11.0
      (114,556,047 bytes on Windows).
    - `torchaudio` 2.11.1 (2026-10-28): `torchaudio-2.11.1-py3-none-win_amd64.whl`, 334,360 bytes,
      sha256 `46ea71634d181f797370f046075ea982043c228b38d674fd7d9fc1c855a37b6a`; BSD; requires
      torch 2.11 or later; in a maintenance phase. Linux, later: `torchaudio-2.11.1+cpu-py3-none-
      manylinux_2_28_x86_64.whl` from the CPU index, 348,141 bytes.
  - **What they bring** (PyPI, each the newest its requirers allow; the lock's diff is checked
    against this list before `uv sync`):
    - `scipy` 1.18.1: 36,658,278 bytes; BSD (its wheel bundles OpenBLAS, LAPACK and the GCC
      runtime). For SpeechBrain.
    - `sympy` 1.14.0: 6,299,353 bytes; BSD. For torch.
    - `mpmath` 1.3.0: 536,198 bytes; BSD. For sympy, which takes under 1.4.
    - `networkx` 3.7: 2,142,205 bytes; BSD-3-Clause. For torch.
    - `jinja2` 3.1.6: 134,899 bytes; BSD. For torch.
    - `markupsafe` 3.0.4: 14,303 bytes; BSD-3-Clause. For jinja2.
    - `fsspec` 2026.9.0: 221,738 bytes; BSD-3-Clause. For torch and huggingface-hub.
    - `filelock` 4.2.10: 218,040 bytes; MIT. For torch and huggingface-hub.
    - `setuptools` 84.2.1: 876,263 bytes; MIT. For torch.
    - `sentencepiece` 0.2.3: 1,655,435 bytes; Apache-2.0. For SpeechBrain.
    - `tqdm` 4.70.1: 80,199 bytes; MPL-2.0 AND MIT. For SpeechBrain and huggingface-hub.
    - `joblib` 1.6.0: 306,115 bytes; BSD-3-Clause. For SpeechBrain.
    - `cloudpickle` 3.1.2: 22,228 bytes; BSD-3-Clause. For joblib.
    - `huggingface-hub` 2.4.0: 857,021 bytes; Apache-2.0. For SpeechBrain (which takes 0.8 or
      later); the library's own code may not import it (Block H's ban).
    - `hf-xet` 1.8.0: 3,911,559 bytes, a compiled package; Apache-2.0. For huggingface-hub on
      x86_64.
    - `hyperpyyaml` 1.2.3: 16,456 bytes; Apache (its classifier names no version). For
      SpeechBrain.
    - `ruamel.yaml` 0.18.17: 121,594 bytes; MIT. For hyperpyyaml, which takes under 0.19.
    - `ruamel.yaml.clib` 0.2.15: 119,013 bytes; MIT. For ruamel.yaml on CPython.
    - Already in `uv.lock`, nothing to fetch: `numpy` 2.5.4, `onnxruntime` 1.31.1 (both now
      declared by the library itself), `packaging` 26.3, `requests` 2.34.2, `soundfile` 0.13.1,
      `pyyaml` 6.0.3, `click` 8.5.0, `httpx2` 2.16.0, `typing-extensions` 4.16.0, `colorama` 0.4.6.
  - **The models** (Hugging Face, each pinned by its repository's commit, size and SHA-256; kept
    in the folder `stt.classifier_dir` names, outside every repository and `var/`, Q16; copied from
    the offline check's `models/` folder once each hash matches, or fetched from
    `https://huggingface.co/<repo>/resolve/<commit>/<file>`):
    - *ECAPA on VoxLingua107:* `speechbrain/lang-id-voxlingua107-ecapa` at
      `0253049ae131d6a4be1c4f0d8b0ff483a0f8c8e9`: `embedding_model.ckpt` 84,474,355 bytes (sha256
      `ab750d5c06d713477045fa798fab5d33e959dbc0dfe4de510a9a47844c79a19a`), `classifier.ckpt`
      762,555 (`a50d9024ff58d317031c9787d4c6c614d454a87a8ef32f9d36338cd3ff57adbc`),
      `normalizer.ckpt` 1,063 (`c369e01dfa2e0d84c6b116f33c7b94f1fe28c061642086538e93cde3d97c26ef`),
      `hyperparams.yaml` 1,519, `label_encoder.txt` 2,204, `config.json` 51; 85,241,747 bytes in
      all; Apache-2.0 (its card, which says it is weaker on foreign accents, female and children's
      speech). The three small files' SHA-256 are taken and pinned at the step.
    - *Silero's 95-language classifier:* `deepghs/silero-lang95-onnx` at
      `bf21c4f59503dc182ab4d69328889b93c51bf70f`: `lang_classifier_95.onnx` 16,972,591 bytes
      (sha256 `12a91f706ad6ca5a5eba4e84a96739d077e56f121ec71db86a752f62e218a227`),
      `lang_dict_95.json` 2,183, `lang_group_dict_95.json` 1,626; MIT (silero-vad's licence,
      "Copyright (c) 2020-present Silero Team"). A third party's re-upload of the file silero-vad
      v4.0 loads from `https://models.silero.ai/vad_models/lang_classifier_95.onnx`, deprecated
      upstream; whether the two are byte-equal was not checked. It runs on the onnxruntime already
      locked.

## What the owner does

- Answer Q1 to Q9, and approve the plan (done 2026-11-09).
- Rule on the yes words that are whole golden items, and on the read-back's edges (done
  2026-11-10, "The owner's decisions").
- Approve Block G and answer Q10 to Q14 before run A (done 2026-11-11); approve Blocks H and I,
  Q15 to Q25 and the downloads before they are built, after run A.
- Hold the live calls, against the mock ticket system, on the laptop's speakers and the wired
  headset (about 20 minutes).
