# Tools in the background: a talker that stays available

Status: an idea to try in M5, for slow tools (the owner, 2026-11-08). Nothing here is built and
no decision rests on it. Every name below is PROPOSED. M5's plan takes it up, registers how it is
judged, and asks the owner what this page leaves open. Everything past the first section is the
agent's reasoning, not the owner's.

## The idea

The owner, 2026-11-08: make the talker "mimic a human in the other end when it comes to tool
calling": it should "invoke the tool on a background process (Like a human searching the
database) meanwhile the talker is fully available to interact with the caller". The result is
stored "like the results shown on the screen Infront of a human which he can look at whenever
convenient or simply ignore", and "the agent is fully aware that he is waiting for the results
meanwhile and can communicate that".

And on where it goes: "write this up to M5 as an idea to really try and have a go with,
especially with slow tools. Make sure it incorporates well with the "agent-led mode" later."

## What happens today

A tool runs inside the turn ([package-design.md](package-design.md), 6.4). The talker asks for
it, a progress line covers a long wait, the turn waits for the result, and the talker answers. If
the caller starts a new turn meanwhile, the reply is held, then dropped if the new turn has words
or played if it was only noise (plan 006, Q19). A stop cancels the search with the reply (D-060).
The agent says it is busy, but it is neither free to talk nor aware of a pending lookup.

## The proposal

A tool is marked to run in the background; inline stays the default, so a fast tool is unchanged.
Each call gets a **board**, the human's screen: one row per job, with its tool, what was asked,
its state (running, arrived, failed, told, dropped) and the conversation version when it started.

1. The talker asks for a background tool. The job starts outside the reply's cancel scope, and
   the tool's immediate result to the talker is only "started".
2. The talker says so in its own words, and the call goes on. Every turn is an ordinary turn,
   and every turn's prompt holds a short section with the board.
3. The result arrives and is stored on the board. It starts nothing while the caller speaks or
   a reply plays. At the next turn boundary the talker can read it; if the caller has gone quiet,
   its arrival starts a turn of its own.
4. The talker uses it, holds it for a better moment, or ignores it. A row is `told` only when the
   clause that carried it played, by the heard history (D-064).

### What must hold

- **Pending means "I don't know yet".** While a job runs, the talker may say it is looking, and
  may not answer from memory what the job was asked to find. Run K's first round showed the
  model following what it read over what the prompt said, so this is tested, not assumed.
- **Never over the caller.** Results reach the caller only at a turn boundary, the rule the
  thinker already has (the design's 6.2) and the one the held reply follows.
- **Evidence only on arrival.** A result is evidence for the guard's ID rule from the moment it
  arrives, and never before. It is data, never instructions (invariant 4).
- **A stop stops the voice, not the lookup.** A read job left running does no harm. Whether the
  talker can cancel a job the caller no longer wants is a question for the plan.
- **Stale results stay visible.** The thinker drops a result of an older version. A board keeps
  it, marked older, and the talker decides, as the owner's "or simply ignore" asks.
- **Actions keep their consent.** `@action` never starts on the talker's word: the read-back and
  the yes rule stay as they are (invariant 1). After the yes, the action already runs as a job
  outside the turn, so the outbox job reports to the same board and the talker stays available
  while it runs. The talker still never says the outcome. The runtime speaks the `done` template
  at a turn boundary, and only from the record (invariants 2 and 6).
- **A cap on jobs per call**, and each arrival turn counted against the model's limits.

### Where it pays, and where it does not

Knowledge search stays inline: it measured 0.32 s at the median (plan 006), and a slow search
is better made fast than run in the background (the design's open question 17). The idea is for
what cannot be made fast: the 17 to 45 s the prototype's search took through ragent2, the 12.5 to
44.3 s of Ole5's chat graph per knowledge turn, and a team's slow backend. How slow a tool must
be before this feels better than an honest wait is one of the things the try finds out.

## Built to fit the agent-led mode

The agent-led mode ([agent-led-mode.md](agent-led-mode.md), D-050) has one voice layer and two
brains, and its cost is "their latency comes back by design". A team's whole agent is the slowest
tool there is, so this idea matters most there. To keep one mechanism for both brains, M5 builds
only what is brain-neutral:

- **A job does not know what produced it.** In M5 a job comes from a `@tool` or the outbox. Later
  it can be a team's graph run. The board holds the same states for each.
- **Delivery belongs to the voice layer**, not to the talker: when a result may be surfaced is
  decided at the turn boundary, whichever brain then reads it.
- **What reads the board is a seam.** In the native mode the talker reads it. In relay, plain
  rules do.

How each front end would use it:

| Front end | While their agent runs | When the result arrives |
| --- | --- | --- |
| Relay (first) | Their run is a job on the board. Plain rules give the progress lines and handle stop, repeat, "hello?" and listening sounds | Their answer is shaped by rules and spoken at a boundary, as the page's "Speech" says |
| Talker plus one delegate | This idea exactly: "ask the agent" is the one background tool, and our talker stays free to talk | The talker sees it is ready. How the answer is then spoken is the phase's decision |

So M5's try gives first evidence on that page's first open decision, relay or delegate. It does
not replace the comparison on real sample agents.

Rules of that page the phase must reconcile with a board; M5 does not settle them:

- **One run at a time on the thread.** A new request from the caller during a run cannot enter
  their agent: it waits for the next run, or the run is cancelled.
- **A turn not heard is rolled back.** A result the caller never heard must be rolled back the
  same way, or their agent remembers an answer the caller did not get. The `told` state is what
  makes that readable.
- **Their answer is not rewritten by a model, and is never evidence.** A talker reading it must
  not paraphrase it unless the phase amends that.
- **A paused write is closed before new input is sent.** A pending read-back outranks anything
  else on the board.

The thinker (D-015, after M7) is the same pattern with one job at a time. If the board works, the
thinker would be one more job source; whether it is needed at all stays the owner's decision.

## The try in M5

- Behind a setting, off by default (GP-18). It does not change M5's *Done when* lines, and comes
  after the consent core, which it must not weaken.
- What it runs on: M5's `ticket_status` and the ticket action's job, if the T2 Ticket API turns
  out slow, and a stand-in tool with a set delay in any case, so the slow case is reproducible.
- `TextCall` scenarios on the virtual clock, against `ScriptedLLM` for the board's rules and
  against the real model for the pending rule. The caller talks on during a job, changes the
  subject, stops, or says nothing.
- A live call by the owner with the stand-in tool, inline against background: the owner's ear
  decides whether it is natural.
- M5's plan registers what is counted before any run: at least answers invented while pending,
  results spoken over the caller, results lost, and model requests per call minute.

## Open for M5's plan

- Whether an arrival starts a turn of its own, or waits for the caller's next turn.
- Several jobs at once, or one per tool; the cap.
- What a stop does to a job, and whether the talker can cancel one.
- How the board's section stays short in the prompt, and what it does to Groq's prompt cache.
- Where the board lives in the layers. The agent's first thought is `actions`, which already
  owns running things, with a read-only view for the talker and only an "arrived" event for
  `voice`, which never imports `actions` (D-003).
