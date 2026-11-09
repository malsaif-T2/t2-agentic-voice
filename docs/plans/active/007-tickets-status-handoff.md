# 007 · Tickets, ticket status and handoff

Status: active · Milestone: M5 · Started: 2026-11-09

*Drafted on 2026-11-09 at the owner's word ("lets start with M5"). A draft: no code is written
until the owner has answered "The owner's decisions".*

## Goal

Let the agent do something for the caller, and never claim it did what it did not
([roadmap](../roadmap.md), M5). The caller asks for a ticket in their own words; the agent
collects the details, reads them back aloud, and creates the ticket only after a clear yes it
heard. It says the number the ticket system returned, and only that number. The caller can ask
about their own tickets, and only their own. «أبغى موظف» spoken over an answer stops the answer,
reads a handoff back and makes the handoff ticket after a yes (D-009, D-018). A write that gets no
reply is never repeated blindly.

It is library behaviour first (`@action`, the yes rule, the outbox, the record, the guard's claim
rules, the safety suite), so any team's action gets the same protection. Ole5 brings its ticket
adapter, its actions and their wording. The caller only hears the agent (D-075): a read-back is
spoken whole, and a draft card is off by default.

## What is known about the ticket system

Read on 2026-11-09 from the prototype (`Ole5-chatbot`, read only) and this repository.

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

- [ ] **The ticket adapter** in the app, on httpx, its contract as inferred above, written in one
  place so a correction from T2 touches one file; and **a fake ticket system** that can answer,
  refuse, time out and answer late, with and without a lookup, used by the tests and by live calls.
- [ ] **No write reaches a real ticket system by accident:** with no `TICKET_API_URL` set, the
  fake answers and its numbers say so; a real URL is set only by the owner (Q2).
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
- [ ] Live, against the fake ticket system, on the laptop's speakers and the wired headset: the
  rehearsal's step 6, where «نعم أرسلها» over the closing question creates the ticket once the
  summary has played and a bare «نعم» there is asked again; and step 3's «أبغى موظف» over an
  answer, which stops it, reads the handoff back and makes the ticket after a yes.
- [ ] `uv run --offline poe check` passes; the guide's `tools-and-actions.md`, `safety.md` and
  `testing.md` written, `concepts.md` and `quickstart.md` extended; the decision entries written.

**Left out**, for the owner's yes with this plan: a real ticket written (Q2); how the website
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

| Track | Owns | Goal |
| --- | --- | --- |
| A | `domain` | The yes rule, the flow's states, the yes, no and send words, the guard's rules A and C |
| B | `actions`, `stores` | `@action`'s lifecycle, the outbox, the jobs, the record, the caps, the error meanings, `t2v outbox` |
| C | `voice/session` | The confirming state, the read-back and its receipt, the heard words routed to the yes rule, the outcome spoken at a turn boundary |
| D | `testing`, `examples/minimal` | `TextCall`'s additions, `ActionSafetySuite`, the example's action |
| E | `apps/ole5-voice-agent` | The adapter, the fake, the actions, the status tool, the handoff, the instructions, the scenarios |

## The measurement, registered before any result

- **Data:** scenarios in `apps/ole5-voice-agent/evals/actions/`, Saudi, MSA and English, split by
  scenario into dev and held-out before any run: a plain ticket, an eager yes, a bare yes, a yes
  over the summary, a correction inside the read-back, a no, a mumble, a refusal, a timeout with
  and without a lookup, status of one's own tickets, a request for another's, a handoff over an
  answer, a handoff asked for by mistake, and a passage carrying a fake number.
- **Run A:** `gpt-oss-120b` at medium, against the fake ticket system, each scenario three times.
- **Hard constraint:** no unrecorded claim and no action without a yes, in **every** run. One
  violation fails the run, whatever else it scored.
- **Targets, on held-out:** the right action taken or rightly not taken ≥ 0.95; the ticket's type
  right ≥ 0.85; the summary judged faithful ≥ 0.85; the reply's language right ≥ 0.90. M4's
  held-out showed how far targets can be from results, and held-out is read once, so a miss is
  recorded and goes to Future improvements, not re-run.
- **The judge** of a summary is a model, checked first on a sample by an agent blind to its
  verdicts, as in plan 006; a failed check marks that score unverified.
- **Cost:** a cap of $3, the owner's call (Q9). No default moves except by a registered keep rule
  (GP-18).

## Progress log

- 2026-11-09: Drafted from the roadmap's M5, the design's 4.4, 6.3, 6.4 and 8, `docs/SECURITY.md`,
  and a read of the prototype's ticket code. Nothing built.

## Decision log

- 2026-11-09: Written shorter than plan 006, whose length came from what was measured along the
  way. The draft is proposed as tracks because `domain`, `actions`, `voice` and the app divide
  cleanly around the ports Block 0 lays down.

## The owner's decisions

Each has the agent's recommendation. None is settled yet.

- 2026-11-09, on starting: "I won't take the calls now, but since M4 is essentially done, lets
  start with M5"; "If it is necessary to close and merge M4 first tell me".

- **Q1. M4 and the base of this work.** Not necessary: M5 can branch from M4's branch. Options:
  (a) close M4 first, its live calls moved to M7's rehearsal and its missed targets recorded, and
  merge it to `main`; (b) leave M4 open and branch from it. **The agent recommends (a).**
- **Q2. The real ticket system.** No documentation, no sandbox, and no sign of a real call.
  Options: (a) build on the inferred contract and the fake, and ask T2 now for the documentation,
  a test environment and the three gaps; one controlled real ticket only when the owner says;
  (b) wait for T2. **The agent recommends (a).** What can be learned only from the real API then
  touches one file.
- **Q3. Who the caller is, for the owner's tests.** Every token carries one fixed subject today.
  Options: (a) the server maps it to one test customer's email, from a setting, which nothing said
  in the call can change; (b) wait for the website's answer. **The agent recommends (a).** The
  real mapping comes with the deployment.
- **Q4. What ticket status can see.** The API has no list by customer. Options: (a) the outbox is
  the list: only tickets made through the agent, each read with `TicketGet`, and the agent says
  so when asked; (b) wait for T2. **The agent recommends (a).** A number the caller says is only
  ever matched among their own tickets, and read back first (plan 002's finding).
- **Q5. What the caller is asked.** The prototype asked for seven fields. Options: (a) only what a
  caller can answer: what is wrong, and how urgent if they say so. The model writes a summary of
  at most 200 characters and picks one of the 11 types, both read back; the priority defaults to
  Medium; the queue follows the type; subtype and reason are left to support staff, so no second
  call exists to fail; (b) all seven, as the prototype did. **The agent recommends (a).**
- **Q6. Saying a ticket number.** Sixteen digits take about ten seconds. Options: (a) the whole
  number digit by digit in groups when the ticket is made, again on request; in status, its last
  four digits; (b) always whole; (c) always the last four. **The agent recommends (a).**
- **Q7. What a handoff ticket holds.** Options: (a) a summary read back to the caller, with what
  both sides said in the call attached for support staff; (b) the summary alone. **The agent
  recommends (a):** staff should not have to ask again.
- **Q8. The background try** ([background-tools.md](../../design/background-tools.md)): a slow tool
  runs while the talker stays free, and the talker says what it is about to look up. Options:
  (a) last in this plan, behind a setting, off by default, judged on a fake slow tool and the
  owner's ear; (b) its own plan after M5. **The agent recommends (a)**, as the owner asked on
  2026-11-08, and it is dropped first if the rest runs long.
- **Q9. The scenario runs.** Options: (a) three repeats a scenario with the model scripted by
  each scenario's lines, plus the design's `simulate` with a model playing the caller, cap $3;
  (b) scripted only, about $1, `simulate` left to M7. **The agent recommends (b):** the scripted
  run holds the hard constraint, and the owner asked to skip runs that are not important.
