# Voice for a team's existing agent: the agent-led mode

Status: the next phase, after M7, agreed in direction (the owner, 2026-11-02, D-050). Nothing
here is built. M2 to M7 build the native mode and the Ole5 Voice Agent first; this page records
the design so that the next phase starts from it. Every name below is PROPOSED, and the open
choices in "Decisions to take" are settled when the phase gets its plan.

## Why

A manager set the library's ultimate goal, in a meeting the owner relayed on 2026-11-02: teams
install the package, plug in their existing LangChain or LangGraph agent, and talk to it live
(approach 3's interactive voice), without rebuilding it. The agents vary in design and
complexity, some take real actions, and the library should be "fairly simple to use and
adopt". Zero code is not required; changing their agent is not wanted.

The owner's points, 2026-11-02:
- Lifting a team's tools into our talker does not preserve their agent: "some agents use their
  in an agentic way to arrive to a result that our talker with the same tools wouldn't be able
  to", and some are workflows built on a specific design. So "we need to use the agent as is".
- "if we can not reliably let their agent execute actions with the user permission then we
  didn't do it as we should." Read, search and answer agents are the floor.
- Pure voice agents, with no other agent behind them, must stay possible.
- The order: "finish the first mode (pure voice with its tools) first and finish our use-case
  Ole5", then this mode as the next phase.

## The shape: one voice layer, two brains

- **The voice layer** is the one M2 to M6 build: WebRTC, end of turn, the two-step
  interruption and cancel scopes, a history of only what was heard, speech-to-text,
  text-to-speech, the output guard, read-back receipts and the yes rule, the call's record and
  the outbox. It does not change for this mode.
- **The native brain** stays the default: our fast talker with a few tools and `@action`, as
  [package-design.md](package-design.md) describes. Ole5, `examples/minimal` and every new voice
  agent use it. It never imports LangChain or LangGraph.
- **The agent-led brain** is a team's compiled LangGraph graph (a `create_agent` agent or a
  custom `StateGraph`), run as is on one thread per call behind the voice layer. The library
  runs a copy of the graph on its own checkpointer, so the team's object is untouched, and
  imports LangGraph only when a team uses this mode, from the team's own install (one install,
  no extras: D-018, answer 2).

Two front ends were weighed. **Relay** comes first: no model on the content path; plain rules
handle stop, repeat, "hello?", listening sounds and speech heard with low confidence, and
every other turn goes to their agent. **Talker plus one delegate** (our talker with a single
"ask the agent" tool on the same thread) is built only if a measured comparison on real sample
agents shows fewer misroutes and better fidelity than the routing time it adds.

## What a team writes

One new file beside the agent; the agent's module is not edited:

```python
from t2_agentic_voice import VoiceAgent, ReadBack, Say, Claims, from_caller
from t2_agentic_voice.langgraph import LangGraphAgent, Act

brain = LangGraphAgent(
    their_compiled_graph,
    reads=["search_kb", "ticket_status"],  # everything not listed is denied
    acts={
        "create_ticket": Act(  # omit acts for a read-only agent
            read_back=ReadBack(en="A {priority} ticket titled {title}. Shall I send it?", ar="..."),
            identity={"requester": from_caller("email")},  # where the tool reads who the caller is
            outcome=parse_ticket,  # its tool result -> done, not sent, unknown
            done=Say(en="Done, ticket ending {number:last4}.", ar="..."),
            claims=Claims(en=["ticket created"], ar=["..."]),
        )
    },
    progress={"search_kb": Say(en="Searching the guides.", ar="أبحث في الأدلة.")},
)
agent = VoiceAgent(name="it-helpdesk", languages=[...], brain=brain)
```

A team learns four things: reads, acts (each with a read-back, an outcome parser and spoken
done and claim phrases in each language), where identity comes from, and deny by default.
`t2v check` prints every tool and node it found with its label, refuses unsafe setups with a
FIX line, and always lists what it cannot see.

## Their actions: the permission layer

Their agent makes its own writes, but only through a pause the library controls, released by
our yes rule:

| Level | How | Shapes it covers | Caveats |
| --- | --- | --- | --- |
| L0 read-only (the floor, first) | Every node or tool not labelled read is denied; a pending write gets "not available by voice" as its tool result, so their agent stays coherent | Any graph | A tool labelled read that writes cannot be detected: the label is the team's promise |
| L1 gated tool call | The run pauses before every tool step. Reads continue; a write's exact pending arguments become the read-back. A yes resumes the run, which executes exactly those calls with no model call in between; a no or a correction goes back to their agent as the tool's result | `create_agent`, and graphs whose writes go through a tool node | Invariant 6 holds fully only if their write tool accepts our request ID; otherwise a lost reply ends as "could not confirm" |
| L2 their human-in-the-loop | Their HumanInTheLoopMiddleware is answered with our verified yes, so the caller is asked once | `create_agent` with that middleware, when the approver is the caller | Refused when the approver is someone else, or when the middleware decides by a condition |
| L3 declared writes | A pause before the team's own write node, or at their `interrupt()`; the team declares how to read the draft and that the code before the write gives the same result each time | Writes inside custom nodes (Ole5's `submit`) | Holds only as far as that promise holds; multi-step writes are not atomic |

- **Agents that confirm in plain text** ("Shall I submit?"): their question is spoken and the
  caller's answer goes back to it; the real write then pauses at L1 or L3 and our read-back
  plays. The caller is asked twice.
- **Never shipped, at any level: relying on their agent's own permission design alone.** A
  chat confirmation assumes a typed yes; by voice their model would judge consent from
  speech-to-text. Ole5's own chatbot needed a voice-only re-confirm guard for this
  (`_unconfirmed_voice_yes` in its `agent/handlers.py`), and approach 2 once said "Your ticket
  has been created" while it was still collecting the details (`voice-lab/server_1028_0146.log`).
- **Cannot be gated from outside**, so the team changes something or the agent stays read-only:
  writes inside sub-agents or subgraphs (the pause does not reach them), in middleware, in
  provider-side tools or the store, and steps that decide and write at once.

One action, end to end:
1. Their model emits the write call and the run pauses before the tool step. Any text in that
   same message is dropped: never spoken, shown or used as evidence.
2. The arguments are parsed against the tool's schema, the caller's identity is set from the
   join token (a mismatch is refused), and a ledger stops repeats: an identical declined call is
   declined again, and an action whose earlier outcome is unknown cannot run again.
3. The runtime speaks the team's read-back from those arguments; the yes rule issues a
   single-use approval bound to the thread, the checkpoint, the call's ID and its arguments.
4. The run resumes as a job outside the turn, never cancelled by barge-in or a deadline, and
   stops again right after the write.
5. The outcome is read from the tool's result. Only a parsed success is recorded, and only then
   may the voice say it is done; anything else is "unknown" by default, said with no number,
   followed by the team's lookup if there is one.

## The sustained thread

- One thread per call on the library's checkpointer, never on the team's own saver in
  production: their chat app could otherwise resume a paused write with no pause in place. Their
  earlier messages may be copied in at call start, read only.
- Only the library's wrapper runs or resumes the thread, one run at a time.
- A turn the caller stopped or corrected before hearing its answer is rolled back, so their
  agent never remembers it. Rolling back past an approved write is refused.
- A paused action is closed before any new input is sent, so no call is left dangling.
- The thread is deleted at call end, after any write in progress has finished.

## Speech

Their final answer is spoken once the run ends, sentence by sentence through the output guard,
shaped by rules, not rewritten by a model: markdown, lists and links removed, the team's spoken
forms for IDs and its pronunciation map applied. By default the first two sentences are spoken
and "The full steps are on your screen" follows, since Orpheus's limits are tight; the screen
gets the full text. Their text is never evidence for a claim. No rewrite and no translation in
the first version.

## What it costs

- **Their latency comes back by design.** Ole5's chat graph took 12.5-44.3 s per knowledge
  turn in the 28 Oct rehearsal, most of it in its knowledge search (median 23.9 s); its graph
  took a median 2.9 s around it. The promise is an honest, interruptible wait with fixed
  progress lines, not a short one.
- **Capacity.** Orpheus is limited per organization (10 requests a minute and 100 a day per
  voice model, and tokens per minute and day: package-design.md, 10.4), and their
  agent's own model calls do not pass through our limiter. Agent-led agents probably need their
  own Groq organization or provider, and one agent-led call at a time until the real limits are
  read (M2's Q17).
- **Work per write**: a label, a read-back that covers every argument, an outcome parser, an
  identity source, and the spoken phrases in each language.
- **Version churn.** The gate rests on LangGraph's pause-before-a-node, which its own docs call
  "not recommended for human-in-the-loop workflows", and on how it resumes. The phase supports
  only tested versions, refuses others at startup, and runs contract tests (approve, decline,
  correct, unknown) against them in CI.
- Invariant 8 is partial in every level: their model provider sees the transcripts. LangSmith
  tracing is turned off around every run.

## Not chosen, and why

- **Lifting a team's tools into our talker as the main path**: it loses their agent's routing,
  grounding and workflow (the owner's point). Reusing a LangChain read tool in a native agent
  stays possible.
- **Their whole agent as one tool with a fresh thread per question**: agents whose logic lives
  in thread state (slot filling, ticket phases, as in Ole5's chatbot) break.
- **Building our talker on LangChain or LangGraph**: it would not handle the voice-specific
  plumbing (cancelling mid-sentence, a history of only what was heard, the per-sentence guard,
  the yes rule and its receipts, the outbox), several of its defaults work against it, and no
  voice framework checked (LiveKit, Pipecat, the OpenAI Agents SDK) builds its talker loop on
  it; they adapt it as a backend, as this mode does. A LangGraph talker holding their agent as a
  subgraph would also lose the pauses the gate needs. New voice agents use the native API.
- **The earlier blanket rejection of approve-and-resume**: retired for writes paused before a
  tool step, where nothing has run and the arguments are fixed; kept for `interrupt()` steps
  whose code before the pause can change, and for steps that decide and write at once.

## Decisions to take when the phase is planned

- Relay first, or our talker with one delegate, after the comparison on sample agents.
- Whether a write tool must accept our request ID before it may be labelled act in production,
  or "could not confirm" is accepted after a lost reply.
- The double ask for agents that confirm in plain text, or a way to ask once.
- How much of an answer is spoken by default, the rest on screen.
- Capacity: a separate Groq organization or provider for agent-led agents.
- English-only agents with Arabic callers: forward and speak English, or a fixed "English only"
  line; no translation until it is measured.
- The amendments this mode needs, each with its own entry: D-012's "not a voice shell around a
  chat agent" for this mode, the contract's rows (D-018, answer 23), D-014's later options, and
  whether the thinker (D-015, D-018 answer 16) is still needed beside this mode.

## Before building

Sample agents from the owner: one `create_agent` agent with a write tool; one custom graph with
a write inside a node or a phase machine; one using HumanInTheLoopMiddleware or plain-text
confirmations. For each write: where it lives, any retries on it, where identity comes from,
whether the backend could take our request ID, and the agent's model provider and languages.

Experiments, each under a day, outside the gated tree: the pause, approve, decline and correct
cycle on a stand-in `create_agent` graph (the key one); cancelling a run mid-token and mid-tool;
whether pauses reach subgraphs; a crash during an approved write; their human-in-the-loop with
our pause active; a timing run of ten questions per sample agent, split into tool time and
graph time; what an Orpheus "token" counts; and the guard's block rate on each agent's real chat
answers.

## What the native mode takes from this now

- M5's consent core (read-back, receipt, yes rule, outbox, record) is built so that a second
  executor, one that resumes a team's paused agent, can be added later
  ([roadmap](../plans/roadmap.md), M5).
- Fixed spoken lines carry no stop, wait, repeat, yes, send or listening word: an echo through
  the speakers could otherwise be heard as the caller's own. The design's own progress-line
  example used «لحظة» and "One moment", both wait words in the prototype's lists; it is fixed.
- The talker's tool list stays small: Groq advises 3-5 tools a request, 10-15 at most for
  capable models (console.groq.com/docs/tool-use/local-tool-calling, read 2026-11-02).

## Evidence

- Approach 2's record (read only): the prototype's `VOICE_LOG.md` and its `agent/` code in the
  Ole5 chatbot repository; `voice-lab/server_1028_0146.log` (the 28 Oct rehearsal's timings and
  the false ticket line) and `voice-lab/kb_cp2c.log`.
- LangGraph 1.2.19, langgraph-prebuilt 1.1.1 and langchain 1.4.7, read in their source on
  2026-11-02; none of it was run. LangGraph's interrupts page
  (docs.langchain.com/oss/python/langgraph/interrupts, read 2026-11-02): a run paused at a
  breakpoint resumes with `None`, a checkpointer is required, and static breakpoints are "not
  recommended for human-in-the-loop workflows".
- Four studies by the agent on 2026-11-02, each checked by a red team and a fact-checker. Their
  reports were working files and are not kept; this page is their record.
