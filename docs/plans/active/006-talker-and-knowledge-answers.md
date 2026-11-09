# 006 · The talker and knowledge answers

Status: active · Milestone: M4 · Started: 2026-11-06

*Drafted on 2026-11-06 at the owner's word, and approved by the owner the same day with every
recommendation, Q1 to Q10 ("The owner's decisions").*

## Goal

Make the agent answer as a voice agent, not as a chat agent read aloud
([roadmap](../roadmap.md), M4; approach 3, D-012). The caller asks in their own words, in Saudi
Arabic, MSA or English, with English product terms in Arabic sentences, and hears a short spoken
answer from Ole5's knowledge base within a registered time, with the full steps on screen.
Whatever the caller says is the talker's to understand, in any wording: a question, a follow-up,
a correction, "say that again", "go on", "only the second step", a new request over a reply (the
owner, 2026-11-06: not "five or six command words"). The library keeps only what cannot wait for
a model: M3's instant stop, and never stopping for a listening sound, the agent's own echo or
silence. The talker reads what the caller heard, clause by clause (D-064), not what it meant to
say; it replies in the caller's language; its reply is spoken clause by clause while the model
still writes; a progress line covers a long search; and a stop cancels the model, the search
and the speech at once (D-060). It is library behaviour first: the `ChatModel` port and its Groq
adapter, the talker loop, `@tool`, the knowledge protocol and its tool, the output guard's ID
rule, `TextCall` with its fakes, and the time to first audio measured. Ole5 brings its knowledge
base adapter, its instructions and its search tool. The plan registers its targets before any
run (retrieval, answers, the reply language, the time to the first useful audio); the
rehearsal's password, archiving and English questions then pass in a live call, and so do its
repeat, mumble and correction steps, which are now the talker's. Every number describes one
speaker, the owner (D-006).

## What voice-first means here

The agent's reading of approach 3 for the talker. Each item is a design choice this plan builds
and measures; Q1 asks the owner to approve or change the list.

1. **Heard, not written.** The model's history holds each reply as the caller heard it: the
   clauses played, a cut clause marked with how much of it played, nothing unplayed. "As I said"
   then means what the caller heard.
2. **Any wording.** With a talker, the session hands it every turn and every overlap that is not
   an instant case. M3's rule keeps three jobs: lower the voice at once; stop at once on a stop
   or wait word or on real words over a reply; never stop for a listening sound, echo or
   silence. The overlap's whole words reach the talker, the stop word included, so «النظام
   توقف» said over a reply is answered, not lost (TD-103). A repeat request, "go on", "slower",
   a correction and a new request are the talker's, read with the history; M3's fixed repeat
   (D-064) stays only for a session with no talker (echo mode, and `examples/minimal`'s echo).
3. **Start while the turn settles.** When Smart Turn calls a turn complete, the session waits
   600 ms more before it replies (D-067). The transcription and the talker's first request start
   at the beginning of that hold, and nothing plays before it ends; if the caller goes on, that
   work is cancelled and the turn continues (Q2).
4. **Speak as it writes.** The model's text streams into the clause splitter, and each clause
   goes to text-to-speech as soon as it is whole; the instructions keep the first clause short.
5. **Short to the ear, whole on the screen.** One to three short spoken sentences; a passage's
   full steps go to the screen as a card (`t2v/1`). *Amended 2026-11-09 (Q30, D-075):* the caller
   only hears; every step is said in one reply, and no card is shown.
6. **Honest waits.** A reply that keeps the caller waiting past a set time, with a search
   under way or just done, gets a pre-recorded progress line (Q27). No
   fixed line holds a stop, wait, repeat, yes, send or listening word, so its echo cannot be
   heard as the caller's (the roadmap's M4, from the next phase's study).
7. **One reply, one scope.** The model's requests, the search and the speech of a reply run in
   its cancel scope (D-060). Words said while a search runs cancel it, and the talker starts
   again with both turns.
8. **The caller's language.** The reply follows the language of the caller's turn; an Arabic
   reply is in the Saudi register unless the caller speaks MSA. Whether English works inside an
   Arabic call is measured first (Q9).

## Acceptance criteria

**The library**

- [ ] **The `ChatModel` port** (`domain/ports/`): `stream(request) -> AsyncIterator[ChatEvent]`,
  with `TextDelta`, `ToolCallRequest`, `Usage` and `Done` (the design's 6.1). The request holds
  the messages, the tool schemas and the model's settings, each a pydantic model checked at the
  boundary (invariant 4).
- [ ] **The Groq chat adapter** (`adapters/`, beside `groq_client.py`): streaming; tool calls
  parsed into `ToolCallRequest`, an invalid one going back to the talker with its field named;
  usage on the span; `ProviderError` with its kind, `retryable` and `retry_after_s`; and the
  port's rule that a cancelled call stops within 50 ms and leaks no task or connection, tested
  as the speech adapters are. The `llm` settings group (the design's 7.6): `provider`, `model`,
  `reasoning_effort`, `max_output_tokens`, `timeout_s`; `llm.model`'s default is the arm run K
  keeps.
- [ ] **The talker loop** (`agent/`): one turn from the caller's heard words to clauses and tool
  calls; tool results framed as data, never as instructions; at most three model requests a
  turn; the system prompt composed from the library's rules, the team's instructions and the
  language section, shown by `agent.render_prompt()`. `VoiceAgent` gains `instructions` (per
  language), `tools` and `vocabulary` (the design's 4.3); `session.mode` gains `talker`, the
  mode of an agent that declares instructions.
- [ ] **The heard history as the model's context**: tests that an unplayed clause never reaches
  the model as said, that a cut clause reaches it marked as cut, and that a turn joined after a
  resumed hold reaches it as one turn.
- [ ] **Interruptions handed to the talker** (`voice/session/`): with a talker, real words over a
  reply stop it at once, as in M3, and reach the talker as the caller's turn, whole, beside the
  cut reply; a repeat request, alone or over a reply, goes to the talker. With no talker, M3's
  behaviour is unchanged and its tests pass untouched. A test that the stop's `StopSpeaking` goes
  out before any model request, so the talker adds nothing to the time a stop takes.
- [ ] **The early start** (Q2): the transcription and the first model request start at Smart
  Turn's "complete"; nothing plays before the hold ends; speech that resumes in the hold cancels
  them and joins the turn. Tested on the virtual clock.
- [ ] **Clauses streamed to speech**: the speaker takes a reply's clauses as they come (today
  `Playback.ask` takes every line up front), the reply's scope opened before its first clause and
  closed only when its last clause and its work are done.
- [ ] **Tools** (`actions/`): `@tool` on an async or a sync function (a sync one in a worker
  thread), `Tool.from_function`, `CallContext` with a read-only `ctx.caller`, `bind=` (filled
  from the session and hidden from the schema), a timeout, the barge-in policy (`cancel` for read
  tools), arguments parsed before the function runs, and `ToolError` and other exceptions as the
  design's 6.4 table says.
- [ ] **Progress lines**: spoken only when the caller has waited past the line's time with no
  answer begun (Q27), from the phrase
  cache; a test that no fixed line of the library or of Ole5 holds a word of the presets' lists.
- [ ] **Knowledge**: `KnowledgeBase.search(query, *, language, caller, limit) -> list[Passage]`
  and `knowledge_tool(kb, description=..., progress=...)`: one search per question, short
  summaries to the talker, the full passage as a card. *Amended 2026-11-07 (Q20):* the talker
  writes its own answer from each of the top k passages whole (cut near 1,500 characters), k
  kept by run K0; it never reads a passage out.
- [ ] **Cards** over `t2v/1` (a title and steps), shown by `t2v-client.js` and the dev page, and
  the `thinking` state while the talker or a tool works.
- [ ] **The output guard's ID rule** (rule B, the design's 8.2), with digit normalization, on
  every clause before text-to-speech and on a card's text; a blocked clause gives the fixed
  phrase, a `GuardBlocked` event and a developer note in the history. The talker's numbers are
  spoken by the speaking rules, with TD-058's cases the talker can reach fixed.
- [ ] **The reply language per turn**, tested with Saudi, MSA and English turns in one call.
- [ ] **`TextCall`** (`testing/`): the real voice session, talker, tools and guard with no audio,
  on a virtual clock, with `ScriptedLLM`, `FunctionLLM`, `FakeSTT`, `FakeTTS` and a fake
  knowledge base; the injections and expectations of the design's 9.2 that M4 needs
  (`during="agent_speaking"`, `at="tool_running"`, `advance`, `stop`; `tool_call`, `said`,
  `blocked`, `cancelled`, `language`).
- [ ] **The parity test** (moved from M3, plan 005): one scripted call run as `TextCall` and as
  `AudioCall` takes the same path through the session (the same verdicts, turns and replies).
- [ ] **The time to first audio**, per turn: from the caller's end of speech (a replay's label;
  in a live call the detector's stop less its delay) to the first audible frame of the reply
  sent, and to its playback in the browser (`client_stats`); progress lines counted apart; on the
  turn's span and in the call report (TD-063's `ttfa_ms`, TD-090's silent first chunks).
- [ ] **`examples/minimal`** gets a read tool, and its test runs the talker through `TextCall`
  with `ScriptedLLM` (Core proof).

**The Ole5 app**

- [ ] **The knowledge base adapter** behind `KnowledgeBase`: one query embedding from T2's
  embedding gateway and one search of Ole5's points in T2's Qdrant per question (D-002; Q4), its
  settings under the owner's general names (`QDRANT_*`, `EMBEDDING_URL`; only the tenant under
  the app's prefix), its tests offline on a fake transport.
- [ ] **The instructions**, per language: short spoken answers in the Saudi register, the steps
  to the card, numbers as digits, a plain "I cannot" for what no tool provides, and no promise of
  a ticket or a person before M5.
- [ ] **The progress lines**, rendered once into the phrase cache.
- [ ] **The vocabulary** that becomes the Whisper prompt, if run W keeps it.

**The measurement** (the roadmap's *Done when* for M4)

- [ ] The knowledge set (`evals/knowledge/`), reviewed by the owner (Q5), split by item.
- [ ] Runs W, K, U, T and S as registered below, held-out read once and only as aggregates, each
  target's result recorded, a default moved only by a keep rule (GP-18).
- [ ] The live calls: the rehearsal's steps 1, 2, 3, 4, 5 and 7
  ([DESCRIPTION.md](../../project/DESCRIPTION.md), "How success is measured") pass on the
  laptop's speakers and on the wired headset; step 6, the ticket, is M5's.

**Left out, for the owner's yes with this plan** (Q3): `simulate` (a model playing the caller;
the scripted scenarios of run S stand in for it); `t2v check` (to M7, with the guide);
`reports_on` (to M5, with ticket status); the guide's `providers.md` (M7).

- [ ] `uv run --offline poe check` passes, and the docs this plan touched are updated: the guide's
  `concepts.md` (the talker and tools), `writing-for-voice.md`, `languages.md` (the reply language
  and the vocabulary) and `latency.md` (the budget as measured), the design's lines the code
  contradicts corrected as facts, and the decision entries written.

## Plan

**Scope.** The roadmap's M4 and the design's 16.1 M4 row, held to what a call needs to answer
well and fast, and to M3's carry-overs: the talker reads what an interruption means (the owner,
2026-11-04 and 2026-11-06, plan 005), the parity test, and the prompt arm for product terms
(plan 003's Q16). The thinker stays after M7 (D-015). What Q3 leaves out is not built.

**What the prototype taught** (Ole5-chatbot's VOICE_LOG.md, read only, D-010): `openai/gpt-oss-120b`
at low reasoning was its model; its knowledge search through ragent2 took 17 to 45 s and was the
largest part of a 12 to 44 s answer; Groq's slow prompt-cache path hit 6 of 13 cached requests
at up to 10 s until a varying first prompt line avoided it (its D9); closing idle connections
put 1.1 to 1.3 s on the first sound after a search, against 0.23 to 0.25 s with connections
kept open (its D41); its first sound reached a 1.5 to 1.6 s median with the knowledge search
held apart; a model once said a ticket was opened while still collecting details (its O4); and
the language switched only on three or more words in the other script (its D27). Block 0's
spike checks the cache path and keeps connections open from the start.

**Before Block 0**

1. The owner's answers to Q1 to Q10, and the knowledge base's access in this repository's `.env`
   (Q4), copied by the owner from the prototype's under general names of the owner's choosing
   (`QDRANT_URL`, `QDRANT_LOGIN_EMAIL`, `QDRANT_LOGIN_PASSWORD`; amended 2026-11-06, "The owner's
   decisions"); the agent reads neither file.
2. **The spike** (paid, at most $0.10, by one agent alone on the machine): the chat models the
   key can call, read from Groq's model list; each candidate's time to its first token and to a
   tool call on three short prompts, five times each, with and without a varying first prompt
   line; one embedding and one search of Ole5's points from the laptop, ten times, with the
   connection kept open; the points' count and fields. Results in the progress log; nothing
   printed holds a secret.

**Block 0 · interfaces, settings, the knowledge set** (one agent; reviewed by one agent, one
skeptic per finding; merged into `plan-006-integration`)

3. The shared shapes, with stubs that raise: the `ChatModel` port and its request and events;
   `Tool`, `CallContext` and `ToolError`; `KnowledgeBase` and `Passage`; the session's view of a
   talker (one turn in, clauses and tool calls out, in a scope); `VoiceAgent`'s new fields;
   `t2v/1`'s `card` and `thinking`; the settings groups `llm` and `guard` and `session.mode`'s
   `talker`, with the generated reference; the fakes' signatures.
4. Baselines for what must not change by accident: M3's session tests in echo mode, `t2v/1`'s
   message list, the settings reference.
5. A snapshot of Ole5's points under `var/kb/` (outside git; Q4), and the knowledge set drafted
   from it (Q5): items in `evals/knowledge/`, each with its variants, its passages or `none`, its
   key facts and its split, for the owner's review.

**The tracks** (in parallel after Block 0; `## Tracks` gives each one's files and tests)

6. Track A, the model: the Groq chat adapter and the model fakes.
7. Track B, the talker and its tools: the loop, the prompt, the context from the history, the
   tools' runtime, knowledge, progress lines and the guard's ID rule.
8. Track C, the session: the talker in the call, the interruptions handed over, the early start,
   clauses streamed to speech, `TextCall`, the parity test and the time to first audio.
9. Track D, the browser: cards and `thinking` in `t2v-client.js`, the dev page and Ole5's widget.
10. Track E, Ole5 and the measurement's tooling: the knowledge base adapter, the instructions,
    the progress lines, the vocabulary, and the runners of runs K, T and S with their scorecards.

**Integration**

11. Each track merged into `plan-006-integration` with the gate after each merge; one review of
    the merged code for what breaks or hangs a call (the owner's rule of 2026-11-03), one skeptic
    per finding, the rest as debt rows; then `examples/minimal`'s read tool and the guide's pages.

**The registered runs** (a quiet machine, [WORKING-RULES.md](../../../WORKING-RULES.md), "Measurement
runs"; in this order, each with its smoke first)

12. W, the Whisper prompt and English in an Arabic call (speech-to-text only).
13. K0, the passages' depth (the real knowledge base only), then K, the talker's model,
    retrieval and answers (text, the real knowledge base).
14. U, the uncertain middle (offline, on M3's stored overlap transcripts; after K, whose kept
    model is one of its arms).
15. T, the time to first audio (the golden set's recorded requests replayed through `AudioCall`).
16. S, the scenarios (text, the real talker and knowledge base, each three times).

**The live calls**

17. The owner's calls on the laptop's speakers and the wired headset, the rehearsal's steps 1, 2,
    3, 4, 5 and 7, with tracing on (`T2V_TRACING__ENDPOINT` set to the local Phoenix) and a warm-up
    call first.

**Close**

18. The design's lines the code contradicts, corrected as facts; the decision entries; the
    `## Future improvements`; the plan moved to `completed/` and the roadmap's M4 row set to done.

## Progress log

- 2026-11-06: Drafted from the roadmap's M4, the design's sections 3.1, 6.1, 6.3, 6.4, 7.6, 8.2,
  9.2, 10.3 and 16.1, plan 005's Future improvements, the code as it stands at 396c523 (no talker,
  tool, knowledge or chat-model code yet; the seam is `CallSession._answer`, which calls the echo)
  and the prototype's VOICE_LOG.md. Groq's production chat models, read on 2026-11-06 from
  console.groq.com/docs/models: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`. Waits for the owner.
- 2026-11-06: The owner approved the plan with every recommendation ("Approve all"). Next: the
  knowledge base's setting names for the owner's `.env`, the spike's Groq part, and Block 0.
- 2026-11-06: The owner set the knowledge base's access in `.env` under general names rather than
  the Ole5-prefixed ones Block 0's brief gave: `QDRANT_URL`, `QDRANT_LOGIN_EMAIL` and
  `QDRANT_LOGIN_PASSWORD`, with no API key ("The owner's decisions"). The Ole5 app reads them with
  no prefix (479c4c8), with T2's defaults under `QDRANT_LOGIN_URL` and `EMBEDDING_URL`; only the
  tenant keeps `OLE5_VOICE_KB_TENANT`; the suite drops `QDRANT_*` and `EMBEDDING_URL` from the
  shell.
- 2026-11-06: The spike's Groq part, by one agent alone on the machine from main at 08f43f5: 120
  streamed requests and 3 diagnostic ones. The spend was $0.023 by the usage, and at most $0.03
  counting the requests that reported none. Prices were read that day from
  console.groq.com/docs/models: gpt-oss-120b $0.15 in and $0.60 out a million tokens,
  gpt-oss-20b $0.075 and $0.30. Both Llama models are now "Enterprise" there, priced on contact,
  and were estimated at their last published prices.
  - **Models.** All four candidates are on the key.
  - **First clause.** On a warm connection, a reply with no tool gave its first clause at a median
    of 0.25 to 0.35 s on every model. The 90th percentiles were 0.30 to 1.04 s, and 8.30 s for
    llama-3.1-8b.
  - **Tool calls.** Both gpt-oss models made 10 of 10 valid, their arguments complete at 0.28 to
    0.35 s. llama-3.3-70b made 4 of 10 and llama-3.1-8b 8 of 10. Every failure was Groq's own
    `tool_use_failed`, sent as an SSE error event: the model wrote its own function text.
  - **The Saudi register.** gpt-oss-120b was Saudi in 10 of 10 replies, with the facts right.
    gpt-oss-20b leaned to MSA, and on 5 of its 10 Saudi questions whose answer was in the prompt
    it searched instead of answering. The Llama models put Chinese, Greek or English words into 4
    and 6 of their 10 Arabic replies, some with wrong facts.
  - **The varying first line** changed no median. First clause, fixed against varying: 0.35 and
    0.31, 0.25 and 0.27, 0.32 and 0.31, 0.30 and 0.30. It removed every cache hit, and the 12
    hits were not slow (median 0.24 s).
  - **Slow requests.** 11 of the 120 waited more than 1.0 s for the response headers, in both
    conditions, outside the times Groq reports. Five were llama-3.1-8b, up to 13.4 s.
  - **Rate limits.** Two 429s asked for 1 s and passed on the next try.
- 2026-11-06: How the prototype reached the knowledge base, read from Ole5-chatbot and its ragent2
  (read only, D-010; no network).
  - **The collection.** One Qdrant collection, `default`, is shared by tenants. Ole5's points are
    selected by the payload field `group_id = "ole5"`, which every search must carry, since the
    index is built per tenant only.
  - **The vectors.** A named dense vector `dense` (bge-m3, 1024 dimensions, cosine, no query
    prefix) and a named sparse one `sparse` (BM25, computed locally by ragent2). ragent2 queried
    both and fused them (RRF), with no rerank.
  - **Sign-in.** The embedding service (`/v1/embed`) needs none. Qdrant needs the gateway's
    `ole5_session` cookie, and signs in again on a 401.
  - **The export.** The knowledge set was drafted from it: 126 chunks named by `chunk_id`, which
    repeats across documents. It skipped chunks under 10 words.
- 2026-11-06: Block 0 merged into `plan-006-integration` (9f5f5ec; bd426b4 to 479c4c8). Every
  stub raises until its track fills it. M3's 197 session tests pass untouched in echo mode.
  - **What it lays down:**
    - the `ChatModel` and `KnowledgeBase` ports;
    - the tools and their runner;
    - the talker's shapes and events, and the guard's rule B;
    - `VoiceAgent`'s `instructions`, `tools`, `vocabulary` and `version`;
    - the `llm` and `guard` settings and `words.vocabulary`;
    - `t2v/1`'s `card`, and the session's seams;
    - `GroqChat`'s shell;
    - the fakes' and `TextCall`'s signatures, with `FakeKnowledgeBase` built;
    - the Ole5 app's knowledge base settings.
  - **Its choices:**
    - `session.mode` is unset by default and follows the declaration; an explicit `echo` keeps its
      meaning.
    - The tool's barge-in field is `on_interrupt`, the design's name.
    - As the layers require: `render_prompt` is a function in `agent/`, the history's models live
      in `core/conversation.py`, and `domain` holds a `DeclaredTool` protocol.
  - **The review** (one reviewer, one skeptic a finding). Two findings stood, fixed in 70f2446:
    - The talker had no clock. The call's `Clock` moved to `core/clock.py` and goes to
      `ChatTalker` and `ToolRunner.run`.
    - A `TextCall` turn gave assertions but not its data. Read-only data stubs were added, with
      `clock="system"` for run K.
    - A third finding was refuted: the blocked clause needs no new phrase, since the presets'
      `error` notice is declared and cached.
  - **What is left** is TD-113 or in the tracks' briefs.
- 2026-11-06: The knowledge set, drafted for the owner's review, merged (a2d09d3, from 0e0259b).
  - **The items.** 64 in all: the 28 recorded requests with their splits, and 36 new ones split
    by the golden set's rule (salt `plan-006-2026-11-06`).

    | Split | Items | Variants | Answerable | `none` | Small talk | Out of scope |
    | --- | --- | --- | --- | --- | --- | --- |
    | dev | 42 | 124 | 32 | 6 | 2 | 2 |
    | held-out | 22 | 65 | 16 | 4 | 1 | 1 |

  - **Coverage.** At least 6 answerable dev items per language, by first variant alone. The items
    point at 93 of the export's 126 chunks.
  - **Its source.** It was drafted from the prototype's export, because the live points could not
    be read before the owner set the access. `points.toml` lists the export's chunks, and the
    validator runs in `poe check`.
  - **Its review** found nothing that breaks. Its debt is TD-114, and two points went to the owner
    (Q12, Q13).
  - **The gate** after both merges (a2d09d3): `TOTAL 13306 0 100%`, `4085 passed, 1 skipped, 1
    warning in 431.77s`.
- 2026-11-06: The spike's knowledge base part, from the laptop, alone on the machine, with the
  owner's access read from `.env` by the environment only, nothing of it printed. One kept-open
  client served T2's gateway, Qdrant and the embedding service.
  - **Sign-in.** One form post, 0.44 s; the gateway set `ole5_session`.
  - **The collection.** `default` holds 4,422 points, 128 of them Ole5's (`group_id = "ole5"`).
    Vectors: `dense` (1024, cosine) and `sparse` (`idf`); indexes on `group_id`,
    `metadata.document_name`, `metadata.file_hash`, `metadata.page_number` and
    `metadata.identifier_digit`; built per tenant only (`m = 0`, `payload_m = 16`).
  - **The snapshot.** All 128 points with their payload (no vectors) went to
    `var/kb/ole5-points.jsonl`, outside git (Q4). The 126 chunks of `points.toml` are all live.
    The two more are `features-001` and `procedures-001`, the short chunks the export skipped.
  - **Times.** For 10 dev questions, one embedding and one search, each with the question's raw
    words, gave these medians, with the 90th percentile in brackets: embedding 0.25 s (0.40),
    search 0.06 s (0.09), both 0.32 s (0.47). The prototype's ragent2 took 17 to 45 s a search.
    After 15 s idle, both took 0.34 s; after 65 s, 0.47 s.
  - **Retrieval, as a smoke only** (run K measures it from the talker's own query): an expected
    point in the top 5 for 8 of the 10. The scores sit close together, 0.50 to 0.74, so no cutoff
    by score is proposed.
- 2026-11-07: Tracks A to D built in parallel worktrees, each reviewed once with one skeptic a
  finding, and merged into `plan-006-integration` one at a time with the gate after each merge.
  - **Track A, the model** (576b104; 18393b9 to 6499f66).
    - `GroqChat` streams text and tool calls and ends with `Usage` and `Done`.
    - It sends `reasoning_effort` only to the gpt-oss models, and maps every failure to a
      `ProviderError`; an in-stream error such as `tool_use_failed` becomes `rejected`.
    - `llm.timeout_s` bounds the whole request. A cancel ends the stream within 50 ms and closes
      its connection, and an idle connection is kept five minutes.
    - `ScriptedLLM` and `FunctionLLM` are built.
    - The review's three findings were refuted: the deadline, the warm-up, and usage on the span.
    - Gate: `4181 passed`, `TOTAL 13537 0 100%`.
  - **Track B, the talker and its tools** (f4a3864; 53d8ef2 to d620ceb).
    - **The loop:** at most three requests, the last with no tools, and tool results framed as
      data.
    - **The history:** the heard history with a cut clause marked `[cut: about N% heard]`, and the
      tool exchanges of the last 4 turns kept, so "only the second step" can be answered.
    - **The reply language** is set per turn.
    - **The prompt and the tools:** the prompt and `render_prompt`; `@tool` and the runner, which
      checks a tool's arguments and refuses a bound one the model sends.
    - **Knowledge:** `knowledge_tool` (`search_knowledge`), and one progress line a reply.
    - **The guard and numbers:** the guard's rule B, and TD-058's five number cases.
    - The review found nothing that breaks. Gate: `4371 passed`, `TOTAL 14241 3 99%`.
  - **Track C, the session** (7909643; b5c8c63 to d637359).
    - **Interruptions:** the talker plays in the call, and real words over a reply reach it whole,
      the stop word included (TD-103). A whole stop or pause stays a command.
    - **The early start** runs through two new hold frames.
    - **Speech:** clauses are streamed to speech, one reply in one scope.
    - **The time to first audio** runs to the first audible frame (TD-090), with progress lines
      timed apart.
    - **Public events:** `ToolStarted`, `ToolFinished` and `GuardBlocked`, and token counts on
      `ModelUsage`.
    - **The test kit:** `TextCall` on the virtual clock, and the parity test (echo mode).
    - **The composition:** `Providers.chat`, and a talker for every call.
    - **The review.** One finding stood and was fixed in d637359: speech begun in a reply's tail
      reported a reply heard whole as cut. One was refuted: the chat model is not warmed at start,
      and no port method exists for it.
    - Gate: `4432 passed`, `TOTAL 15336 45 99%`, in 16 minutes under Track E's load.
  - **Track D, the browser** (b254e59; 819b03b and dd396ba).
    - The client, the dev page and Ole5's widget show `card` and `thinking`, as text only, with
      direction set per step.
    - Seen in the browser pane at 375 px.
    - The review found nothing that breaks. Gate: `4440 passed`, `TOTAL 15336 45 99%`.
  - **Still open:**
    - The chat model's connection is not warmed at start.
    - A model request's usage and first token reach the call report but no span.
    - The parity test covers echo mode only.
    - Ten items of the tracks' debt that can break a call or miscount a run go to the integration
      round; the rest are TD-115 to TD-118.
- 2026-11-07: The integration round's ten picked fixes, in two parts built in parallel worktrees
  from 7abb6b3, each reviewed once with one skeptic a finding, and merged one at a time with the
  gate after each merge.
  - **The talker and the guard** (f55bbac; dc52678 to 9751cf9).
    - **The guard** reads a time, a decimal, "24/7" and a date around a year one number at a time,
      so "8:00", "12.75" and the prompt's own date pass. A ticket number read in groups by spaces
      or hyphens still joins.
    - **Notes:** `[reply N]` and `[cut: about N% heard]` copied by the model are never spoken, even
      split across stream pieces.
    - **The talker** closes the model's stream with `aclosing`, and a `ScriptExhaustedError` goes
      through it.
    - **The port's docstring** says a cancel mid-answer closes the connection.
    - **The review.** One finding stood and was fixed in 9751cf9: a date written with a Unicode
      hyphen (U+2010 to U+2013, U+2212), as gpt-oss writes them, was still blocked, and a tool
      result's date said back that way was blocked where it had passed before the fix.
    - Gate: `4478 passed`, `TOTAL 15365 45 99%`.
  - **The session and the test kit** (71c14b0; 1b340e8 to aba9fcc).
    - **The held reply:** each held event is guarded, nothing held plays once the call ends or its
      `ended` notice plays, and a client stop in the hold cancels the work.
    - **Closing:** the talker's stream is closed in the reply's own task.
    - **The error notice** is said once a reply, after clauses too, in the reply's language. A
      failed transcript after words that stopped a reply now says it with a talker as without one.
    - **Usage:** the requests of a dropped early start are counted.
    - **The test kit:** `TextCall` sets a fake model's clock for every call; `Pause`,
      `ScriptExhaustedError` and `ScriptStep` are on the `evals` facade; and an AssertionError the
      talker raises fails the test from the next `user`, `advance`, `stop` or the call's end.
    - **The review.** One finding stood and was fixed in 2369857: after a stop word or a repeat
      request in a window, a failed transcript of new words stayed silent with a talker. The
      coordinator added aba9fcc for two points the parts left: a script that ran out was still
      only heard as the `error` notice, and a talker raising as `reply` is called left its reply
      open.
    - Gate: `4498 passed`, `TOTAL 15424 41 99%`.
  - The rest of the two reviews' debt is TD-119 and TD-120.
- 2026-11-07: Track E built in three parts in parallel worktrees from 92b2f80, each reviewed once
  with one skeptic a finding, and merged one at a time with the gate after each merge.
  - **E1, Ole5's agent and its knowledge base** (85b6bff; d0c3a85 to c184c66).
    - **The adapter:** `QdrantKnowledgeBase` behind `KnowledgeBase`: one embedding and one dense
      search with the tenant's filter, the session cookie sent to Qdrant only, one more sign-in on
      a 401, a 4 s deadline a search, the client kept open.
    - **The agent:** instructions per language (`instructions/ar-SA.md`, `en.md`), a progress
      line, 14 product terms as its vocabulary, and its version. The server runs the talker when
      the three `QDRANT_*` names are set, the echo when none is, and refuses to start with only
      some.
    - **The knowledge set:** the keep path, and the 6 `none` items of Q13 (`q37` to `q42`, 4 on dev
      and 2 on held-out), no earlier item moved.
    - **The review.** Its one finding was refuted: the declared vocabulary differs from run W's
      terms file, but no live call sends a prompt before run W decides (Q17 then settled it).
    - Gate: `4583 passed`, `TOTAL 15741 41 99%`.
  - **E2, the runners of runs K and S** (48526b3; aeac84e to bb75d5c).
    - **Run K** (`poe eval-talker`) with its comparison and keep rule, the judge, and the owner's
      check of 24 judged answers (`poe judge-check`).
    - **Run S** (`poe eval-scenarios`): ten scripted calls, six of them the rehearsal's steps.
    - Both are paced under the key's limits, with the cap checked before the run and before each
      request.
    - **The review.** Three findings stood and were fixed in bb75d5c:
      - a turn was read before its reply had played, so run K would have counted no words spoken
        and no violation;
      - a correction said while a search ran crashed run S;
      - the reply's language was read from the tag the caller's words set, so every MSA variant
        scored wrong. It is now read from the reply's own words and the judge's register.
    - Two were refuted: the keep rule's time (Q15 then settled it) and a long `retry-after`.
    - Gate: `4754 passed`, `TOTAL 17804 42 99%`.
  - **E3, the runners of runs W, U and T** (9e09517; b3af622 to 2197e6e).
    - **Run W:** its arms in `poe eval` (W1's prompt, X's language hint).
    - **Run U:** `poe uncertain`.
    - **Run T:** `poe first-audio`, and the owner's listen (`poe first-audio-listen`).
    - **The review.** Three findings stood and were fixed in 2197e6e:
      - run T refused Ole5's own agent for its MSA recordings; each is now held in the language
        the agent gives that caller;
      - a reply that sent no audio was dropped from T's numbers unseen. It is now counted as
        `no_audio` and ranked slowest, with the tail sized to the slowest answer (47 s);
      - U0 read the verdicts O1 and O2 gave before D-068's revision. The stored overlaps are now
        replayed through `AudioCall` on their stored transcripts, under the rule of today.
    - Two were refuted: run T's shared phrase cache, and U's held-out pass (Q16 then settled it).
    - Gate: `4830 passed`, `TOTAL 19087 42 99%`.
  - **Still open:** the runners are joined to the merged code in the integration's next round,
    with Q15 to Q18 built into them; their debt is written once that round is done.
- 2026-11-07: The integration's second round, built in two parts in parallel worktrees from
  b96a5ae, each reviewed once with one skeptic a finding, fixed, and merged one at a time with the
  gate after each merge.
  - **Wiring, the runners joined to the merged code** (3ff04ea; f551909 to eeb9979).
    - **One way to build Ole5's agent and knowledge base** for runs K, S and T:
      `--agent ole5_voice.agent:talker_agent`, and
      `--knowledge ole5_voice.knowledge_base:knowledge_base`, which reads only the knowledge
      base's access (`KnowledgeSettings`, no access code). Tn is `talker_agent(None)`. The knowledge base and
      the chat model are closed at every end, a refusal after they are built included.
    - **The history** takes K's and S's lines. U and T got lines of their own, since the borrowed
      ones could not hold U0's right count or T's targets and starts of time.
    - **Run T's replay** goes through the library's `AudioCall.turn`; `TurnReplay` gains
      `opening`, the reply's first 3 s, for the owner's listen.
    - **Q15:** the keep rule reads the time to the first clause less the time the tools ran
      (overlapping tools counted once); the scorecard shows both medians and names the one read.
    - **Q17:** `whisper_prompt` (`domain/whisper_prompt.py`, on the `languages` facade) builds the
      prompt from the agent's vocabulary, then a tuple of proper spellings of the command words,
      trimmed to 224 bytes; a test shows no mishearing of the presets' lists can reach it. W1 is
      `--prompt-agent`; no live call sends a prompt yet.
    - **Q16:** U's refusal of a held-out source says the pass replays H3's clips and is built once
      an arm passes on dev. **Q18:** the targets already read both groups together; the held-out
      scorecard now shows them apart too, as aggregates.
    - **Checked:** a stalled call is a `stuck` variant or play in K and S, never a crash (a bug,
      its tests written first); S's injections on the real `TextCall` with Ole5's talker; the
      adapter's passage IDs and the judge's text agree for every committed point.
    - **The review.** One finding stood and was fixed in eeb9979: a failed greeting request in
      run T's replay ended the run with no scorecard or history line. It is now a failed
      recording (a `rate_limited` one retried), and the card and history lines are written at
      every end. One was refuted: run T never reads the chat model's day headroom, but the key's
      day limits are far out of reach (D-040).
    - Gate: `4894 passed`, `TOTAL 19522 36 99%`.
  - **Guide, the minimal example and the guide's pages** (63dc256; d806a15 to 8ac4b62).
    - **`examples/minimal`'s helper:** the talker with one read tool, `opening_hours` (`@tool`),
      served by `make_runtime` and tested through `TextCall` with `ScriptedLLM` in English and
      Saudi Arabic; the echo stays, served by `make_echo_runtime`.
    - **The guide's pages:** `writing-for-voice.md`, `languages.md` and `latency.md` are new;
      `concepts.md`, `browser-client.md`, `serving.md`, the guide's `evaluation.md`, the
      quickstart and the README are brought to the talker. The samples beyond the quickstart's
      come from a tested file.
    - **The review.** One finding stood and was fixed in 8ac4b62: the quickstart and
      `concepts.md` promised an English answer to English words in a Saudi call, which run X
      measures first.
    - Then the library's README and three stale lines (bdc5422).
    - Gate: `4905 passed`, `TOTAL 19531 36 99%`.
  - **Debt:** TD-121 to TD-124, what Track E and this round leave.
  - **Next:** the review of the whole merged code (step 11), then the live smoke of the talker
    with the real model and knowledge base, then the registered runs.
- 2026-11-07: Step 11's review of the whole merged code (at e24337d), in four areas (the session,
  the talker and the model, the Ole5 app as served, the registered runs), each reviewer in a
  worktree of its own with probe tests, one skeptic a finding; merged with the gate (be34263).
  - **TD-120's open question, answered:** a talker reply playing when the call's limit asks for
    its `ended` notice does end, and the call hangs up; the caller hears no clause asked after
    the notice, but the notice waits behind the clauses asked before it (TD-125).
  - **Three findings stood and were fixed** (ad6fa94, 22336f6, 3f9420c):
    - a held-out run of K or T printed the library's `talker_replied` line beside each count,
      which showed each held-out variant's search, blocks and language; held-out runs now hold
      the library's lines below ERROR;
    - a reply the model ends with no clause (an empty answer, a `length` end with nothing
      written) was silence and read `answered`; the session now says the `error` notice, once a
      reply, and a `length` end is logged by its model;
    - run K's pacer waited inside the talker's request, so a wait for room in the minute landed
      in both first-clause times (Q15's included); K now waits for room for a variant's requests
      before its call, and a variant that still waits inside is left untimed.
  - Two of these were promoted by the lead from the reviewers' debt lines, each then checked by a
    skeptic; two others promoted were refuted (Ole5's cross-language lines, run U's card on a
    bug) and are debt.
  - **Refuted, to the owner instead:** words begun during a search and outlasting it are talked
    over until their turn closes; the skeptic found it the recorded rule (D-068's amendment 7), a
    design question, so it went to the owner as Q19. The lead's own reading of the knowledge tool
    went to the owner as Q20.
  - Gate: `4916 passed`, `TOTAL 19563 35 99%`.
  - **Debt:** TD-125 and TD-126.
  - **Next:** Q19 and Q20 built (in their own worktrees), then the live smoke and the registered
    runs, K0 before K.
- 2026-11-07: The owner's Q19 and Q20, built in parallel worktrees from be34263, each reviewed
  once (neither review found what breaks a call), merged one at a time with the gate after each.
  - **Q20, the top k passages whole** (80f8b52; a42848b to e9f2ceb).
    - `knowledge_tool` gives the talker each passage's whole text (`text`), cut at a line near
      the new optional `passage_chars` (1,500); the card, the guard's evidence and the steps are
      unchanged.
    - Ole5's agent reads one named k (`SEARCH_LIMIT`, 5 until K0 keeps another; its version
      `2026-11-07.2`).
    - Run K0 is `poe knowledge-depth`: one search per answerable dev variant with a limit of 8,
      no chat request, the shares and characters per k, the keep rule reckoned in exact
      fractions, held-out refused, a smoke search first, a history line of its own.
    - Gate: `4957 passed`, `TOTAL 19871 36 99%`.
  - **Q19, the reply held while the caller speaks** (fb5df3f; eaa44d5, 74e933c).
    - A talker reply none of which played when a newer turn's speech began is kept, its events
      in the early start's `pending`, until that turn is taken. Words in it stop the reply as
      before; a turn heard as nothing lets it play in order; a stop or the call's end plays
      nothing of it. The client shows `thinking` while it waits; the echo is unchanged.
    - Per-event playing moved to `talker_play.py`, so `talking.py` stays under the size cap.
    - A kept reply waits about 1.1 s after a turn heard as nothing when Smart Turn says
      complete, about 3.5 s when it says incomplete.
    - Gate: `4973 passed`, `TOTAL 19926 36 99%`.
  - **Debt:** TD-127.
  - **Before the runs:** once K0 keeps a k, `SEARCH_LIMIT`, Ole5's `VERSION` and the test that pins
    5 change together, and run K's `--input-budget-tokens` (6,000) is checked against K0's
    characters. Before the live rehearsal of step 5, TD-117's early start rebuilds its turn after
    the stop.
- 2026-11-07: The live smoke, before any registered run: the real knowledge base,
  `openai/gpt-oss-120b` at low reasoning, and Ole5's talker through `TextCall` on the system
  clock; then two probes (about 40 model requests in all, about a cent).
  - **The knowledge base** answered 8 passages for a limit of 8, none unreadable, their IDs in
    `points.toml`'s form (`<document>/chunk_NNN`): 1.11 s for the process's first search, its
    sign-in included, then 0.34 s on the kept connection.
  - **Groq took a `system` message mid-history** (the guard's note, TD-116): finish `stop`, a
    sensible reply.
  - **The rehearsal's step 1** («نسيت كلمة المرور كيف أستعيدها؟»): one search (0.34 s), two
    requests, the first token at 0.26 s and the first clause at 0.82 s on the wall clock (about
    0.48 s of the model's own), four clauses in the Saudi register, no block, no violation. The
    follow-up («طيب وش الخطوة الثانية؟») was answered with no new search.
  - **The screen promised with nothing on it.** Both replies told the caller the full steps were
    on the screen, and no card was shown: the best passage of the talker's own query lists no
    steps, and the library's rule and Ole5's instructions named the screen whatever was shown.
    Fixed and merged (e94a7df; d57f379, 39cb81b, then e67142a): the knowledge tool's
    `shown_on_screen` always says what is shown (`"nothing"` when no card), and the rules name
    the screen only when it holds the steps. Rechecked live: the reply no longer names it.
  - **A follow-up took 7.8 s to its first token** in the recheck. A probe of Ole5's real prompt,
    24 short requests alternated: with the same prompt, 8 of 12 were served from Groq's cache
    and 3 of those 8 took 1.03, 1.25 and 5.71 s; with a first line varied per request, none was
    cached and all 12 came in 0.15 to 0.30 s. The prototype's slow cache path (its D9), which
    Block 0's spike did not see: the owner's Q21.
  - **Tn's talker was refused.** Ole5's talker with no tool (`talker_agent(None)`, run T's Tn)
    keeps the instructions to search first; four Ole5 questions sent with no tools gave three
    Groq refusals (`tool_use_failed`: the model wrote a tool call no request offered) and one
    empty answer. Tn would have timed the `error` notice; its talker gets instructions with no
    search (built in its own worktree).
  - TextCall's system-clock test failed once alone as well as under load: a 0.05 s sleep on the
    loop's clock, which ticks every 15.6 ms on Windows, ended 0.033 s later by the finer counter;
    its bound now allows the tick (3cc3eb7). Gate: `4976 passed`, `TOTAL 19927 35 99%`.
  - **Debt:** TD-128; paid from TD-116 (the mid-history `system` message), TD-120 (the
    system-clock test) and TD-121 (the adapter against the live service).
- 2026-11-07: The live probes' two fixes, built in parallel worktrees from 3cc3eb7, each reviewed
  once (neither review found what breaks a call), merged one at a time with the gate after each.
  - **Q21, a first line of its own** (d547e1b; aaf7b34, 8725872, then 7011d09). Every request the
    talker sends opens its system message with `Request <id>.`, the ids from a counter with a
    random start; `llm.vary_first_line` (on by default) turns it off; `render_prompt` shows the
    prompt without it; `latency.md` says why. Gate: `4987 passed`, `TOTAL 19938 35 99%`.
  - **Tn's talker with no search** (48185bb; 74ec2bc to e90d7b9). `talker_agent(None)` swaps
    each language's "Searching:" section for one saying there is no knowledge base or tool, and
    carries its own version (`+no-search`); the served talker's prompt is unchanged byte for
    byte. Gate: `4992 passed`, `TOTAL 19951 35 99%`.
  - **Rechecked live** (about a cent):
    - Tn's talker: 6 Ole5 questions with no tools, 0 refused, 0 empty; it said twice that it
      cannot look it up and answered 4 times from its own knowledge, which Tn does not read.
    - The served talker: 4 turns, 8 requests offering the search, 0 cached tokens; the first
      token at a median of 0.36 s, the slowest 0.49 s. A call's requests grow with the passages
      kept from its last 4 turns: 3,927 input tokens over the first turn's two requests,
      12,892 over the fourth's.
  - **Debt:** TD-129; TD-121 narrowed (Tn's search instructions paid).
- 2026-11-07: **Run W, on dev** (W0, W1, X: 292 variants of 98 items each, no failure; $0.0941
  each, $0.28 in all; the history's lines 3635f1e, 86c0a17, 6469d5e).
  - **W1, Ole5's Whisper prompt (Q17):** not kept by the registered rule, since term recall did
    not rise (0.333 in both). It did raise the right count beyond the noise: 12 items better, 3
    worse (p = 0.035); accuracy 0.390 to 0.442, word errors 0.259 to 0.223. The stop words went
    from 0.69 to 0.92 and the repeat requests from 0.32 to 0.53; Saudi Arabic rose by 0.117,
    beyond the noise. Text from silence, raw, rose from 104 to 156 characters: Whisper's own
    captions («ترجمة نانسي قنقر», «اشتركوا في القناة»), never a word of the prompt; after the live
    filter (`stt.no_speech_max` 0.55 and the captions), W1 leaves 1 of the 12 silence, noise and
    echo variants' text, W0 5. Held-out is not read.
  - **X, every variant sent as Arabic (Q9):** English in an Arabic call is not supported. The
    English items' accuracy fell from 0.813 to 0.027 (22 items worse, none better, p < 0.0001),
    as the guide's `languages.md` already says: a caller who will speak English picks English.
  - **How it was compared.** Each run's history line was committed before the next arm ran, so
    W1 and X ran at commits one history line after W0's (`git diff` shows only
    `evals/history.jsonl`), and `poe eval-compare` refused their commits. They were compared as
    copies of their scorecards with W0's commit, the data digest checked equal. The runs of one
    comparison keep their history lines aside until the last has run, as M3's did.
- 2026-11-07: **Run W1 on held-out, by Q22's rule** (W0 and W1 at 23d887c, 131 variants of 42
  items each, no failure, aggregates only; $0.0416 each; the history's lines 8eb7ebf).
  - Accuracy 0.382 to 0.420 (higher: met); word errors 0.254 to 0.218 (no higher: met); the
    `stop_word` kind 0.778 to 0.889 (no lower: met).
  - **Two conditions cannot be read as registered:** held-out's aggregates show no
    `repeat_request` kind (a kind shows only over 3 items or more in both runs), and a held-out
    run stores no answer, so the live filter cannot be applied to its silence, noise and echo
    variants. Their nearest aggregates: text from silence 69 and 67 characters, the share the
    same (1.0). The rule should have named aggregates a held-out run keeps.
  - Also: term recall 0.65 to 0.60, the `request` kind 0.462 to 0.410, Saudi Arabic 0.303 to
    0.364, MSA 0.474 to 0.526, English unchanged at 0.773.
  - **Settled by the owner (Q23): W1 kept.** Live calls send the prompt `whisper_prompt` builds
    from the agent's vocabulary, a setting turning it off; the live calls show whether it holds.
- 2026-11-07: **Q23 built: live calls send the Whisper prompt** (2c06b13; ef19162, 515fe9a,
  a6e58f0, then the agent's docstring), reviewed once (nothing that breaks a call).
  - `call_prompts` builds `whisper_prompt` once a call for `ar` and `en`, from the agent's
    vocabulary (then `words.vocabulary`'s terms), byte for byte W1's for Ole5's talker (sha256
    `7b52b432c4bd5ae3`). Every request of a call sends its language's: the turn's transcript,
    the held one, each window and overlap. A request that names no language sends none.
  - `stt.send_prompt` (on by default) turns it off. `AudioCall` takes the same path, so run T
    measures what ships. The echo, with no vocabulary, sends the command words alone.
  - The history page that run W's commits had left stale was rendered again (a6e58f0).
  - Tests: `5000 passed`, `TOTAL 19964 35 99%`; lint failed on one line of Ole5's agent
    docstring, which the lead read past, wrapped in 55a0929.
  - **Debt:** TD-130.
- 2026-11-07: **The knowledge set's review (Q5)**, before any run read it. The owner: "Ok It seems
  good to me, but to be fair I am not very familiar with the knowledge-base myself, so just make
  sure the information are there in the knowledge-base to back the answers." So the agent checked
  every item against the snapshot's text (four readers in parallel, read only):
  - each answerable item's key facts against its expected passages, and the other passages for
    one a right answer needs; each `none` item against all 128 passages;
  - 61 of 70 were backed as written. Nine were corrected to what the passages say (96e5061):
    - key facts: `n12` (no "kept up to date" for notifications), `n21` (extra attachments when
      archiving, not after), `n22` (the knowledge base ties no app update to notifications),
      `n25` (or that setting turned off), `q16` (the sign-in check's other ways), `q19` (the
      roles' sub-tabs, and a shared department role's type);
    - expected passages: `n17` gains `rules-004` (the view screen's attachments), `q12` gains
      `rules-021` and `rules-017` (a department's and the account's space), `q15` loses
      `procedures-019` (nothing on the label's date).
  - No item changed kind or split; every `none` item is absent from the knowledge base.
  - The tests of the set pass (23); the whole gate ran at the k of 7 below.
- 2026-11-07: **Run K0 on dev** (Q20; at 55a0929, 96 variants of 32 answerable items, no failure,
  no Groq request; the history's line 5299725). From the raw words, for each k: the share of
  items with an expected passage in the top k, then the share of their expected passages found:

  | k | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | An expected passage in the top k | 0.698 | 0.771 | 0.833 | 0.844 | 0.854 | 0.865 | 0.875 | 0.896 |
  | Expected passages found | 0.281 | 0.391 | 0.463 | 0.517 | 0.564 | 0.596 | 0.621 | 0.651 |
  | Characters read, median | 647 | 1,405 | 2,352 | 3,127 | 4,039 | 4,825 | 5,928 | 6,852 |

  - **k = 7 kept**: the smallest within 0.05 of k = 8's 0.651 (k = 6 is 0.005 short). At k = 7
    the talker reads a median of 5,928 characters of passages, 7,596 at the 90th percentile,
    8,822 at most. Ole5's `SEARCH_LIMIT` is 7, its version `2026-11-07.4` (bf7793a).
  - From the raw words, an expected passage is in the top 5 for 0.854 of the items, under K's
    90% target; K reads the talker's own query too. If K misses it, a sparse query beside the
    dense one is the first amendment to propose (the decision log, 2026-11-06).
- 2026-11-07: **Run K's first dev round, exploratory** (K1 `gpt-oss-120b` and K3 `gpt-oss-20b`,
  twice each, at dfc6953, 136 variants each, `--call-language first`, k = 7; $0.75; the history's
  lines 7a52c20). The keep rule kept K3: both within 1.0 s (the model's own medians 0.600 and
  0.550 s; wall 0.959 and 0.907 s), K3 better on 17 items, worse on 9 (p = 0.17), a tie to the
  faster. Every target but the guard's failed:

  | Run | Right (items) | Honest `none` | Language | Retrieval, top 5 |
  | --- | --- | --- | --- | --- |
  | k1-dev-a | 0.302 | 0.400 | 0.301 | 0.885 |
  | k1-dev-b | 0.281 | 0.400 | 0.293 | 0.885 |
  | k3-dev-a | 0.292 | 0.800 | 0.359 | 0.865 |
  | k3-dev-b | 0.333 | 0.833 | 0.377 | 0.854 |

  Read on dev, before any decision rests on the round, it showed four faults:
  - **English questions answered in Arabic** (26 of 42 English variants in k1-dev-a, 17 in
    k3-dev-a): the reply's tag and the prompt's language section said English, and the model
    wrote Arabic, following the seven Arabic passages. A live English call would have the
    English voice read Arabic (the rehearsal's step 7). A bug.
  - **The judge's register is wrong.** The lead labelled 20 replies by hand: the verdict
    prompt's register agreed with 7 (54 of 59 Saudi-marked replies in k1-dev-a called `msa`); a
    register question of its own agreed with 17 (`llama-3.3-70b`) and 18 (`gpt-oss-120b`).
  - **MSA callers answered in Saudi Arabic** (8 of the 10 MSA replies labelled), against Ole5's
    instructions and the plan's item 8.
  - **One cause given where the knowledge base has several**: most `partly_right` verdicts name
    one of an item's two to four key facts (a median of 25 words), such as one of `n02`'s three
    causes; three fit in one spoken sentence.
  The round decides nothing: the talker and the judge are fixed, and the four dev runs run again.
- 2026-11-08: **The fixes from run K's first dev round** (d2cf04d; bc24e35 to b1322cc), built by
  one agent, reviewed once; the review's one finding fixed (026c746). Gate: `5091 passed`, `TOTAL 20062 39 99%`, exit 0.
  - **The reply's language held over the passages':** every request that follows a tool exchange
    of the turn ends with a `system` line naming the reply's language (`prompt.reply_line`), for
    that request only, never kept in the history.
  - **The reply's register read from the caller's words, over the call** (`register_of`,
    `call_register` in `agent/language.py`): Saudi once any turn of the call has held a dialect form
    (`DIALECT_WORDS`, and ما before a word shaped as a verb), MSA while none has; the language
    section and the line after a tool then say MSA. The review found that a turn read alone
    turned a Saudi caller's «تمام» or «كمل» to MSA and had a repeat reworded; it is read over the
    call.
  - **The judge's register asked on its own**, of the judge's model, with the lead's probe prompt
    (a reply with no Arabic costs no request; an unclear answer is asked once more, then a judge
    failure); runs K and S read it under Q24's rule.
  - **Ole5's instructions** name each of several causes, places or conditions briefly, up to
    three, in one sentence; its version `2026-11-07.5`.
  - The Ole5 app's README says how to try the agent on this machine (d87aefd).
  - **Debt:** TD-131.
- 2026-11-08: **Run K's second dev round** (at 6f820da, the fixes in; 136 variants each, no
  failure; $0.79; the history's lines 2768bfe). **The keep rule kept K3, `gpt-oss-20b`**: both
  within 1.0 s (the model's own medians 0.519 and 0.559 s; wall 0.845 and 0.892 s), K3 better
  on 18 items, worse on 5 (p = 0.0106, beyond the noise). Every target but the guard's still
  fails:

  | Run | Right (items) | Honest `none` | Language | Retrieval, top 5 |
  | --- | --- | --- | --- | --- |
  | k1-dev-c | 0.302 | 0.400 | 0.808 | 0.875 |
  | k1-dev-d | 0.333 | 0.300 | 0.841 | 0.844 |
  | k3-dev-c | 0.396 | 0.800 | 0.808 | 0.854 |
  | k3-dev-d | 0.333 | 0.800 | 0.750 | 0.854 |

  - **Language** rose from about 0.33 to about 0.80; 15 of k3-dev-c's 26 misses are Saudi replies
    («هلا، أقدر أساعدك… إذا ما وصلتك») the register question still calls MSA.
  - **Answers:** of k3-dev-c's 96 answerable variants, 38 right, 40 partly right (19 with a card),
    13 wrong, 4 invented. The judge's reasons for `partly_right` name a key fact the spoken
    answer left out.
  - **`none` items:** 6 of 30 got an invented answer (an export to PDF, a scheduled sending).
  - The owner's check of 24 judged answers (Q6) is drawn from k3-dev-c (`judge-sheet.toml` in its
    run folder), before the held-out pass.
- 2026-11-08: **The owner's ruling: `gpt-oss-120b`** over the keep rule's K3 ("The owner's
  decisions"). Run T's first T0 pass, begun on K3, was stopped at 7 of 72 recordings (about
  $0.09, no history line, its folder `t0-dev` left as it is), to run again on K1. The owner's
  check of the judge is drawn again from `k1-dev-c`.
- 2026-11-08: **An exploratory dev pass of `gpt-oss-120b` at medium reasoning** (k1m-dev-a, at
  8e12024, 136 variants, no failure, no reply cut at the token limit; $0.23), against the two
  at low (k1-dev-c and d):

  | | Right (items) | Honest `none` | Invented | Language | Own first clause, median, p90 |
  | --- | --- | --- | --- | --- | --- |
  | low | 0.302, 0.333 | 0.400, 0.300 | 19, 18 | 0.808, 0.841 | 0.52, 0.61 s |
  | medium | 0.375 | 0.733 | 6 | 0.870 | 0.85, 1.24 s |

  The owner ruled for medium (Q26): `llm.reasoning_effort` defaults to `medium`; K's held-out
  and runs T, U and S use it.
- 2026-11-08: **Run T's T0 and T1 on dev** (`gpt-oss-120b` at medium reasoning, at b5ff7e8; 72
  recordings each, no failure, every reply heard; $0.60 and $0.57; history lines a9ad02e):

  | | No search, median, p90 (turns) | Search, median, p90 (turns) | Past 3.0 s | Progress lines | Late |
  | --- | --- | --- | --- | --- | --- |
  | T0, trim off | 1.38, 1.55 s (3) | 2.40, 3.01 s (67) | 7 | 0 | 59 |
  | T1, trim on | 1.97, 3.55 s (2) | 2.47, 4.75 s (69) | 17 | 10 | 58 |

  - **The trim is not kept.** T1's median is not lower than T0's, so the keep rule leaves
    `tts.trim_silence` off and the owner's listen is not needed. T1's long tail comes with slow
    searches (10 past the tool's 1.0 s, none in T0); on the 57 turns with no progress line in T1,
    the median pair differs by +36 ms, so the trim gains nothing on like turns.
  - **With a search, T0 holds both times** (targets 3.0 s and 4.0 s). The times with no search
    wait for Tn; these are the few turns the model chose not to search.
  - **The progress line's target fails, by how the line is built.** 59 of 67 search turns began
    after 2.0 s with no line before it. The line's clock is the tool's own: 1.0 s from the tool's
    start, stopped when the tool ends, and the search took under 1.0 s on every T0 turn. The
    wait is the speech-to-text and the first model request before the tool, and the second model
    request and the voice after it. Its target is the owner's call (Q27).
- 2026-11-08: **The progress line by the caller's wait (Q27).** `Tool.progress_after_s` now
  reads from the end of the caller's speech (2.6 s by default, so the line is heard by 3.0 s),
  whether the tool or the model holds the reply up; the talker gives `ProgressDue` as the tool begins, with its
  `after_s`, and the session says the line at that time unless a clause was asked for, the reply
  is kept or a notice took its place. A tool's `progress_after_s` is no longer tied to its
  timeout. Run T's target reads 3.0 s (`PROGRESS_BY_MS`), and T0's dev pass is run again on it.
- 2026-11-08: **The owner's word: only the runs that matter** ("Lets skip any unnecessary runs.
  Only do the important ones"). The agent's reading, each for what it still decides:
  - **Still to run:** S, the only automated check of the multi-turn behaviour; T's held-out pass,
    once, with the progress line, the one full pass of the code that ships; K's held-out pass,
    once, after the owner's check of the judge; and the live calls.
  - **Dropped:** Tn, stopped at 12 of 72 recordings (3 items, all with no search, median 1.36 s,
    p90 1.48 s against 1.6 s and 2.4 s; no scorecard or history line, about $0.05, its folder
    `tn-dev-120b` left as it is), which decides nothing; T0's second dev pass, which held-out's
    pass replaces; and run U, whose rule (D-061) stays, a model for the uncertain middle left
    for later (brought back the same day, Q28).
- 2026-11-08: **Run S, first pass** (`gpt-oss-120b` at medium, at b69071f; 30 plays, no failure,
  no guard violation; $0.08; an earlier start stopped at its smoke test, the knowledge base's
  embedding timing out once, $0.001, no line kept): 5 of 10 scenarios met. Met: s01 stop and go
  on, s03 English, s04 mumble, s07 change of language, s08 not in the knowledge base (2 of 3).
  Not met, each 0 of 3:
  - **s09, a request for a person over a reply:** «أبغى موظف» went on unanswered, the rule's
    `short_output` (two words under 1.2 s), a real fault (Q28).
  - **s02** only on the last turn's register, plain Arabic to a caller who used «بس»; **s05** only
    on `search`, the correction answered from the passages already found (and once on its key
    facts): the behaviour right, the checks stricter than a short spoken answer.
  - **s06 and s10** on a key fact a short answer left out ("permission or options differ").
  The owner (Q29): loosen the register and the correction's search, keep the key facts.
- 2026-11-08: **Run U on dev** (on O1's 35 uncertain overlaps of 19 items, 15 that should stop;
  at aedce08, history lines kept; $0.003), brought back by Q28:

  | | Right | Stops of the 15 | Listening sounds stopped | Answer, median | Kept |
  | --- | --- | --- | --- | --- | --- |
  | U0, the rule | 20 | 0 | 0 | none | |
  | U1, `llama-3.1-8b-instant` | 20 | 0 | 0 | 180 ms | no |
  | U2, `gpt-oss-120b` at low | 25 | 8 | 3 | 177 ms | no |

  U2 fails the keep rule on the sign test (3 items better, 2 worse) and on the listening sounds
  (three single words, «إيه؟» twice and a garbled one). The owner's ruling (Q28) over the keep
  rule: U2, on overlaps of two or more words only (5 of the 15 stopped, none wrongly, on this
  data); single words keep the rule.
- 2026-11-08: **The model on short overlaps of two or more words (Q28)**, built by one agent,
  reviewed once with no finding (51a4a75, 85525d4; D-069); `VoiceAgent.ask_on_uncertain_overlaps`,
  on for Ole5's talker. Gate: 5136 passed.
- 2026-11-08: **Run S's second and third passes**, $0.09 and $0.08, no failure, no guard
  violation. The second (s-120b-3, at 85525d4): «أبغى موظف» stopped the reply and was answered
  in all 3 plays, s09 failing only on the offer to go on helping. Ole5's instructions then gained
  a line to say when an action needs a permission and to offer to go on helping (d169991).
  The third (s-120b-4, at b5be04d), the record:

  | Scenario | Passed | Needed | Met |
  | --- | --- | --- | --- |
  | s01 stop and go on | 3 | 3 | yes |
  | s02 archive, repeat, one part | 2 | 3 | no |
  | s03 English | 2 | 3 | no |
  | s04 mumble | 3 | 3 | yes |
  | s05 correction | 3 | 3 | yes |
  | s06 follow-up | 0 | 2 | no |
  | s07 change of language | 1 | 2 | no |
  | s08 not in the knowledge base | 3 | 2 | yes |
  | s09 a person, over a reply | 3 | 3 | yes |
  | s10 a new request, over a reply | 3 | 2 | yes |

  6 of 10 met. s06's first answer leaves out that printing needs a permission (the key fact the
  owner kept, Q29). s02 once mixed up which step was second. s03 and s07 failed on language: an
  English reply naming Arabic buttons in Arabic script, which the English voice cannot read, and
  once a reply wholly in Arabic. Ole5's instructions now say English names in an English reply;
  no further pass is run for it, K's held-out reading the language.
- 2026-11-09: **Run T on held-out, once** (t-held-out-120b, at 319c5d4: trim off, the progress
  line at 2.6 s; 11 items, 44 variants; $0.43; no failure, no reply unheard; 4 variants cut in
  two and left out, so 40 timed replies, all with a search):

  | Target | Result | Bound | Held |
  | --- | --- | --- | --- |
  | With a search, median | 2,532 ms | 3,000 ms | yes |
  | With a search, 90th percentile | 3,044 ms | 4,000 ms | yes |
  | No search, median and 90th percentile | no held-out item answers without one | 1,600 and 2,400 ms | not measured |
  | Replies not begun by 3.0 s with no line by then | 5 of 40 | 0 | **no** |

  The line played in none of the 40. It is withheld once a clause was asked of the voice (Q27),
  so the likely reading is that in those 5 a clause had been asked by 2.6 s and its audio came
  just past 3.0 s; a held-out run keeps aggregates only, so the run does not confirm it. The
  result stands, held-out being run once. The six session tests of the line pass; T's dev passes
  predate the timer, so no run has yet heard the line at its new time, and the live calls are
  where it is first heard. The no-search times stand on dev's 12 recordings (median 1.36 s,
  90th percentile 1.48 s).
- 2026-11-09: **TD-117's early start, before the live calls.** A turn held while a reply to an
  earlier turn is in progress no longer starts early, so its transcript takes `answer`'s path,
  which stops that reply first: the talker reads the reply as cut and its turn as rolled back.
  This replaces the rebuild the debt row named, which would have spent a model request to reach
  the same place. A test failed on the old code and passes now; the other debt in TD-117 stays.
- 2026-11-09: **The close's documents, as far as they stand without the owner:** the design's
  lines on the Whisper prompt, the knowledge tool and the chat settings corrected as facts;
  decision entries D-070 to D-074 (Q19, Q20, Q21, Q27, and Q23 with Q26). The `## Future
  improvements`, the plan's move and the roadmap's row wait for the judge check, K's held-out
  pass and the live calls.
- 2026-11-09: **The caller only hears (Q30 to Q32, D-075), from the owner's listening.** «أبشر»
  opened 22 of run S's last 48 Arabic replies, since Ole5's instructions gave it as the first
  example of the Saudi register: taken out of the examples, and forbidden as an opener. 23 of
  the 48 pointed the caller at the screen: the library's rules, Ole5's instructions and
  `knowledge_tool` now have every step said in one reply, repeated whole or in part on request,
  and no card shown. The judge reads only what was said aloud. Ole5's version `2026-11-09.1`.
- 2026-11-09: **Run S after D-075** (s-120b-5, at 4dc35ac; 30 plays, no guard violation, one
  failure; $0.09). Gate at that commit: 5138 passed. 5 of 10 scenarios met: s01, s04, s05, s07
  and s08. s02 had 2 of the 2 plays it could judge, its third play failing on a provider's
  `rejected` when a third request, which offers no tools, was answered with a tool call. s03 2 of
  3 (an English reply naming Arabic buttons), s06 1 of 3 (the permission left out of the first
  answer), s09 2 of 3 («أبغى موظف» read as referring a correspondence to an employee), s10 0 of
  3: each failed on its first turn's last fact, which the script's own interruption keeps from
  being said, a check that spoken-only scoring makes impossible; that turn's item is now taken
  out of s10, and two of the three plays would have met it. Against the last pass: «أبشر» in 0
  of 46 Arabic replies (was 22 of 48); no reply pointing the caller at a screen (17 name "the top
  of the screen" as where a button is); replies a median of 178 characters, 500 at most, 4
  clauses, 11 at most, and at most 763 output tokens of the 1,024. One reply wrote its steps
  twice; 4 of 57 replies copy the knowledge base's `←` arrows, for the live calls to hear.
- 2026-11-09: **Run K on dev after D-075** (k1-dev-spoken, at a9693bc; 136 variants; $0.23; the
  owner's Q31 and Q32). Beside k1m-dev-a, the last pass at medium (8e12024), which scored the card
  too, so not like for like:

  | | k1m-dev-a | k1-dev-spoken |
  | --- | --- | --- |
  | Passed | 0.500 | 0.594 |
  | Language right | 0.868 | 0.752 |
  | First clause, median and 90th percentile | 1.10 and 1.51 s | 1.27 and 1.82 s |
  | Words, median and 90th percentile | | 26 and 48 |
  | Failures | 0 | 3 |

  Of 136: right 56, partly right 38, wrong 8, invented 8, not in knowledge 23. Retrieval 0.849.
  The language check reads a reply in imperatives as not Saudi, «أبشر» having been the only dialect
  word in many; the first clause is later with no short opener.
  - **The check of the judge (Q32): not passed.** An agent blind to the judge's verdicts checked
    the 24 drawn answers against the knowledge base: 17 of 24 agree, 7 disagree, and the registered
    limit is 3 (`MOST_DISAGREEMENTS`). Four of the 7 change pass or fail, two each way, and the
    agent marked all four as close calls. By the registered rule
    the run's verdicts are not to be compared or kept on.
  - **The 3 failures** were one fault, as in run S's one: after two searches the third request
    offers no tool, the model writes a tool call anyway, and Groq refuses it, so the caller hears
    the `error` notice. D-075's longer answers made it likelier (8 of the 136 turns reached a
    third request). Telling the model no tool is left took a replay of those 8 questions three
    times from 3 of 8 to 2 of 24 failed; the last request now also holds the results with the calls
    that asked for them dropped (`_without_calls`, agent/turn.py): 0 of 24 failed, 11 of them
    reaching a third request (about 3 cents).
- 2026-11-09: **Run K on held-out, once** (k1-held-out-spoken, at 4529f32: `gpt-oss-120b` at
  medium, k = 7, spoken words only; 24 items, 71 variants; $0.12; no failure, no guard block).
  The judge's check having failed (7 of 24), the owner ruled the pass run with its answer scores
  marked unverified (Q33).

  | Target | Result | Bound | Held |
  | --- | --- | --- | --- |
  | An expected passage retrieved | 0.816 | 0.90 | no |
  | Right answers (unverified) | 0.408 | 0.80 | no |
  | Honest when not in the knowledge base (unverified) | 0.941 | 0.90 | yes |
  | Language and register | 0.690 | 0.95 | no |
  | Guard: no blocked or violating reply | 0 | 0 | yes |

  A search was made in all 71. Language by the caller's speech: English 0.905, MSA 0.857, Saudi
  0.50, mixed 0.50: a reply in plain imperatives reads as not Saudi. Verdicts: right 25, partly
  right 22, wrong 2, invented 4, not in knowledge 18. First clause: median 1.31 s, 90th
  percentile 1.90 s; words: median 26, 90th percentile 55. The result stands, held-out being run
  once. Retrieval is under target as on dev, so a sparse query stays the first amendment to
  propose. The spend is about $4.83 of the $7 cap.
- 2026-11-09: **No consent screen on Ole5's page (Q34, D-076).** The page goes straight to the
  access code, with one box, off by default, to keep the call's audio. The library's recording
  rule (invariant 8) and the widget's version value are unchanged, so no setting moves.
- 2026-11-09: **The owner's first live calls, and what they changed (Q35, D-077).** Three calls
  (Arabic, English, Arabic), judged good, with notes the entry in D-077 lists. They were not
  traced, so only their timings are known: replies with no search began at a median of 3.0, 2.1
  and 2.3 s, those with a search at 5.1, 5.6 and 4.9 s. Seven of the ten progress lines ended
  within 0.1 s of the answer's start. Three replies waited over 4 s with no line. Three
  times the voice took 1.9 to 2.8 s to start where 0.25 s is usual. Eight spellings of the name
  were said by the real voice and read back by Whisper: only the unmarked one came back whole.
  English pieces averaged 32 characters; one reply cut at its commas ran 13.3 s, at its
  sentences 10.7 s. Ole5's version `2026-11-09.2`. A replay through the real model and knowledge
  base (a script, no run recorded; under $0.10): 1 of 23 dev questions asked back, all 4 vague
  requests did, all 6 archiving questions were answered from the knowledge base, and 0 of 11
  English replies held Arabic letters. The owner's own archiving question stays unexplained.
- 2026-11-09: **The owner's second round of calls (Q36, D-078).** English sounds better, with a
  pause between sentences the owner finds tolerable (left as it is). The Arabic name is still
  wrong: of ten more spellings said by the voice the owner found two best, and «أو لي فايف» went
  in (Ole5's version `2026-11-09.3`). One Arabic turn at 15:57 said the
  search could not be done, the first search since the server started; a search now tries twice
  within its deadline, the server signs in at its start, and each tool call has a span.
- 2026-11-09: **Traces hold what was said (Q37, D-079).** Each turn's root span now holds what
  was heard and what its reply said, each reply's span its text, each tool call's span the
  arguments the model wrote and what the tool gave back, under `tracing.include_transcripts`.
  Invariant 8 changed with it.

## Decision log

- 2026-11-06: The knowledge base is reached directly, one embedding and one search per question
  (D-002, the roadmap's "Later" line), not through ragent2, which took 17 to 45 s a search in the
  prototype. The agent recommends plain HTTP for both calls over the `qdrant-client` package D-002
  named: one search request needs no client, and no new package is installed (Q4).
- 2026-11-06: Scripted scenarios stand in for `simulate`'s model-played caller: they are
  repeatable, cost less, and cover the rehearsal's steps one by one (Q3).
- 2026-11-06: The candidate models are Groq's production chat models of that day, not its
  preview ones, which may change or go without notice.
- 2026-11-06: No varying first prompt line (the prototype's D9 cure): the spike saw no slow cache
  path, and the varying line removed every cache hit, which halves the price of the input cached.
  *Reversed 2026-11-07 (Q21):* the live probe saw the slow path on Ole5's real prompt.
- 2026-11-06: The knowledge base adapter sends a plain dense search (the `dense` vector with the
  tenant's filter), not ragent2's hybrid one, whose BM25 query vector is computed by a package the
  library does not have (Q4: no new package). Run K's retrieval measures what that costs; if
  retrieval misses its target, a sparse query is the first amendment to propose.
- 2026-11-06: The knowledge base's settings carry the owner's general names, so a second team
  reaching T2's service needs no renaming.
- 2026-11-07: The knowledge base adapter stays in the Ole5 app (Q14, the owner's (b)); the
  library gives every team the general way, the `KnowledgeBase` protocol and `knowledge_tool`, so
  no `knowledge` facade or decision entry is added for an adapter.
- 2026-11-07: With a talker, every stop or repeat verdict hands the turn's own words to the
  talker, and only a stop or pause said whole stays a command: a bare «وقف» stays silent while
  «النظام توقف» said over a reply is answered (Track C).
- 2026-11-07: The reply's language follows the turn's heard language. The reply's script overrides
  it only with at least 3 words in the other script and more than twice their count, so English
  product terms keep a Saudi sentence Arabic (Track B).
- 2026-11-07: One progress line a reply, however many tools or requests, so the caller never hears
  "let me check" twice (Track B).
- 2026-11-07: The session, not the talker, makes a clause speakable after the guard: digits
  spoken, then the pronunciation map, then the voice's length; a clause said in one piece is
  captioned as written (Track C).
- 2026-11-06: The Whisper prompt from the vocabulary reaches the live session only if run W keeps
  W1 (GP-18), so no track wires `voice/stt_bridge.py` before then.
- 2026-11-07: With a talker, a reply is held while a newer turn of the caller's that is no
  overlap of it is open (Q19), which narrows D-068's amendment 7 for the talker only; the echo
  keeps M3's rule. A decision entry is written at the plan's close.
- 2026-11-08: The progress line's timer is the session's, not the talker's: only the session
  knows when the caller stopped speaking and whether a clause was asked for, and the talker
  could time past the tool only by iterating the model's stream from a second task, which a
  stream of the reply's scope must not be (D-060). Its default is 2.6 s, not 3.0 s: the cached
  lines open with up to about 0.25 s of their own silence (measured on the phrase cache), and
  a clause asked of the voice by 2.6 s is heard by about 3.0 s, so the two meet near the target.
  A clause already asked of the voice counts as the answer begun: it plays first in any case,
  since a reply's audio is in the order asked. Found by the review of the change (b69071f),
  which read 2.8 s as past the target.

## The owner's decisions

- 2026-11-06 (plan 005's close): "The thing is that we don't really want to rely on "five or six
  command words" to interact with the system, our next step should be understanding the user
  request flexibly, but I think this is out of M3 scope."
- 2026-11-06: "Ok, now lets start with M4. Our goal is to make a voice oriented agent, so it needs
  to be seamless and flexible a true implementation of approach 3."
- 2026-11-06, to "Approve plan 006 with the recommended answers to Q1–Q10?": "Approve all". So
  Q1 to Q9 are settled as (a) and Q10's cap of $5 holds.
- 2026-11-06, on the knowledge base's setting names, after the agent proposed Ole5-prefixed
  ones: "I have setted them as: QDRANT_URL= QDRANT_LOGIN_EMAIL= QDRANT_LOGIN_PASSWORD= ... Ole5
  naming is not general enough."
- 2026-11-07, to Q11 to Q14: Q11 "Drop K2"; Q12 "Replay without tool"; Q13 "Add 6 more"; Q14
  "It should be on the Ole5 app, the library should provide a general way to access
  knowledge-bases through a tool or an object". So the knowledge base adapter stays the Ole5
  app's, and the library's general way is the `KnowledgeBase` protocol with `knowledge_tool`.
- 2026-11-07, to Q15 to Q18: Q15 "Model's own time"; Q16 "Replay H3's clips"; Q17 "Proper
  spellings only"; Q18 "Pool both, report apart".
- 2026-11-07, to Q19 and Q20, from the whole-code review: Q19 "Hold the reply". Q20, first:
  "I believe it should formulate the answer itself from the retrieved passages and not read
  them exactly. Almost all knowledge-bases are made to be read and not voiced. If you see this
  approach problematic then we can do/try a different one"; then, asked how much of each
  passage the model writes from: "Use the full first few passages found, determined by k
  (top-k), find the best k for our case".
- 2026-11-07, to Q21, from the live smoke: "Vary the first line".
- 2026-11-07, to Q22, after run W on dev: "Test it on held-out".
- 2026-11-07, to Q23, after W1's held-out pass: "Keep the prompt".
- 2026-11-08, to Q24, after run K's first dev round: "Either register right".
- 2026-11-08, to Q25, after run T's smoke: "Raise it to $7".
- 2026-11-08, on run K's result (the keep rule had kept K3): "use "gpt-oss-120b" instead, it
  has more reasoning power and more capable to hold conversations longer". So K1 ships,
  `llm.model` stays `openai/gpt-oss-120b`, and K's held-out and runs T, U and S use it.
- 2026-11-08, to Q26, after an exploratory dev pass at medium reasoning: "Medium reasoning".
- 2026-11-08, to Q27, after run T's T0: "Line at 3.0 s".
- 2026-11-08, to Q28, after run S's first pass: "Let a model decide"; after run U: "Model on 2+
  words".
- 2026-11-09, unprompted, after listening: "I don't have enough knowledge about the
  knowledge-base to judge how good the answers are, but I can say that the agent uses the word
  'أبشر' a lot, and most of it seems out-of-context. Also We shouldn't rely on a screen to show
  information, the agent is voice oriented, and potentially will run on voice only channels, so
  'look at the screen' thing is not encouraged."
- 2026-11-09, to Q30: "It should give all the steps in one reply, but be able to repeat all,
  repeat a specific step, or get in detail about one under the caller request. No card or screen
  is needed."; to Q31: "Only spoken words"; to Q32: "An agent, against the KB".
- 2026-11-09, to Q33, after the judge's check: "Run it, marked unverified".
- 2026-11-09, unprompted: "Do we really need consent? I think that any developer having access
  to and running this has already consented. it is tiring to manage that every time"; to Q34:
  "Yes, remove the screen".
- 2026-11-09, after three live calls: "both did good, but my notes would be that both pronounce
  Ole5 wrongly, I have noticed that '←' is not well handled in Arabic [...] The English speech
  is kind of odd, like it is out of breath"; to Q35: "Yes, make them. 'Ole5' is said ok in
  English but in Arabic even the greeting is wrong. Fix them and I will try it again once you
  finish."
- 2026-11-09, after the next calls: "The Ole5 in Arabic is till wrong. English sound better but
  there is this strange pause between sentences, it is tolerable"; to Q36: "Yes add them."; of
  the samples: "'Ole5-sample-02.wav' and 'Ole5-sample-03.wav' sounds the best, either would be
  good"; of the traces: "Why not? make it do so to ease our job" (Q37); "make what the tool returned is traced too".
- 2026-11-08, to Q29, after run S's first pass: "Loosen them, except 'you need permission to
  print'".

## Tracks

Each track owns its files (one owner per file; a file two tracks need is Block 0's) and builds
against Block 0's fakes, never against another track's unfinished code. Paths under the library
are relative to `packages/t2-agentic-voice/src/t2_agentic_voice/`.

**Track A · The model (`adapters/`, `testing/`).** Owns the Groq chat adapter (a new module beside
`groq_client.py`, which it reuses), `ScriptedLLM` and `FunctionLLM`. Tests: streaming, tool calls
and their parsing, usage, errors and `retry-after`, cancellation within 50 ms with no leaked task,
the connection kept open between requests; all offline on a fake transport.

**Track B · The talker and its tools (`agent/`, `actions/`, `domain/`).** Owns the talker loop,
the prompt's composition and `render_prompt`, the history's messages, `@tool` and its runtime,
`knowledge_tool`, progress lines and the guard's rule B. Reads the history (`voice/session/history.py`)
through Block 0's view only. Tests: a turn with and without a tool, three requests at most, tool
results as data, bound parameters hidden, a timeout, a tool error, a blocked ID, the reply
language.

**Track C · The session (`voice/session/`, `voice/turn_hold.py`, `testing/`).** Owns `call.py`'s
talker path, the speaker's streamed clauses, the interrupter's hand-off, the early start, the
call report's time to first audio, `TextCall` and the parity test. Tests: M3's tests untouched in
echo mode; a stop before any model request; a cut reply in the context; words during a search; a
resumed hold; the parity of `TextCall` and `AudioCall`.

**Track D · The browser (`api/static/`, `apps/ole5-voice-agent/web/`).** Owns the client's `card`
and `thinking`, the dev page's and the widget's card. Tests: the protocol's messages; the page in
the browser pane with a silent stream.

**Track E · Ole5 and the runners (`apps/ole5-voice-agent/`).** Owns the knowledge base adapter,
the app's settings, the declaration's instructions, progress lines and vocabulary, and the
runners of K, T and S under `ole5_voice/evals/` with their `poe` tasks and scorecards. Tests: the
adapter on a fake transport, the instructions rendered, the runners on fakes; the knowledge set's
validation inside `poe check`.

## The measurement, registered before any result

*Registered on 2026-11-06, before any run; every target, arm and keep rule below is the agent's
proposal until the owner rules (Q6 to Q10). Amendments are dated and made before the result they
affect.*

**Data.**
- *The knowledge set* (`evals/knowledge/`, new; Q5): about 60 items. The golden set's 28 recorded
  requests (`n01` to `n28`) keep their ids and splits, so their recordings serve run T; about 32
  more are written from Ole5's points so that every topic of the knowledge base has an item; about
  8 ask what the knowledge base does not hold, and about 6 are small talk or out of scope. Each
  item has two to four variants (Saudi, MSA, English, Arabic with English product terms), its
  expected points or `none`, two to four key facts, and whether it needs a search. Split by item,
  dev about two thirds; held-out read only as aggregates. *Amended 2026-11-07, before any run
  (Q13):* 6 more `none` items, placed by the split's rule with every item drafted before them
  keeping its side, so that one miss does not fail the `none` target on dev.
- *The scenarios* (run S): ten scripted calls, from the rehearsal and from the owner's word on
  flexibility: the password question, then «وقف», then «كمّل»; the archiving question, then a
  repeat request, then "only the second step"; an English question; a mumble; a correction of a
  misheard word; a follow-up that needs the last answer; a change of language; a question the
  knowledge base cannot answer; a request for a person (said plainly not possible before M5); and
  a new request over a reply.
- *M3's stored overlap transcripts* (O1 and O2 on dev, H3 on held-out; plan 005) for run U, and
  the golden set's speech items for run W.

*Amended 2026-11-07, before any run (Q21):* every request the talker sends opens with a short
line that differs on every request (`llm.vary_first_line`, on by default), so no request is
served from Groq's prompt cache, whose slow path took up to 5.7 s in the live probe; runs K, T
and S measure with it (K0 sends no chat request).

**W, the Whisper prompt and English in an Arabic call** (speech-to-text only, about $0.05 a run).
Arm W1 sends the vocabulary (Ole5's product terms and the presets' command words) as Whisper's
prompt; W0 sends none (today's). Arm X sends the golden set's English items with the Arabic
language, as an Arabic call would. *Metrics:* term recall, word errors, stop and pause words
heard, and text from silence, noise and echo, by stratum. *Keep W1* if term recall rises by the
sign test on items, with word errors and text from silence no worse than the noise (D-024), then
held-out once; Whisper can write a prompt's words into silence, which the silence items catch.
*X decides Q9:* English in an Arabic call is supported if X's word errors on the English items
are within the noise of the English language's. *Amended 2026-11-07, before any run (Q17):*
W1's prompt holds Ole5's declared vocabulary, then each command word as it should be written,
never a mishearing the presets keep for what Whisper writes (such as «وكيف» for «وقف»), which a
prompt could make Whisper write; it is built by the one function a live call would use, so
W1 measures the prompt the agent would ship. Term recall is still scored on `evals/terms.toml`.
*Amended 2026-11-07, after W's dev runs and before held-out is read (Q22):* W1, not kept on dev
by the rule above, is tested once on held-out by a rule registered now: W0 and W1 run on
held-out at one commit, read as aggregates only; *keep W1* if its accuracy is higher than
W0's, its word errors no higher, its accuracy on the `stop_word` and `repeat_request` kinds no
lower, and the live filter (`stt.no_speech_max` 0.55 and the captions) keeps the text of no
more silence, noise and echo variants than W0's. If kept, live calls send the prompt
`whisper_prompt` builds (Q17).

**U, the uncertain middle** (offline on stored transcripts; about $0.05). For each overlap whose
rule verdict is a short output or too few words, a model reads the reply clause the caller heard
and the overlap's words and answers "go on" or "stop". Arms: U0 the rule (D-061), U1
`llama-3.1-8b-instant`, U2 the talker's model. *Metrics:* right verdicts, listening sounds that
stopped the agent, the model's time to its answer. *Keep* an arm that raises right verdicts by the
sign test on items, stops no more listening sounds than U0, and answers within 300 ms at the
median, then held-out once; otherwise the rule stays. *Amended 2026-11-07, before any run
(Q16):* M3's held-out run H3 stored aggregates only, so U's held-out pass replays H3's held-out
clips live, the kept arm deciding each uncertain overlap as it comes, and writes aggregates
only (about $0.03 of Whisper and the chat requests); it is built once an arm passes on dev.
*Amended 2026-11-08 (the owner, "only the important ones"):* run U is not run; the rule stays.
*Amended 2026-11-08, after run S's first pass (Q28):* run U is run on dev after all, U2 at low
reasoning. The owner ruled over the keep rule, for U2 on overlaps of two or more words, with no
held-out replay: the scenarios and the live calls check it.

**K0, the passages' depth** (*added 2026-11-07, before any run, Q20*; the real knowledge base
only, no chat model, no Groq request). Before K, on dev only, each answerable variant's raw
words are searched once, as K's reference search, with a limit of 8. *Metrics, for each k from
1 to 8:* the share of the answerable items with an expected point in the top k; the share of
each item's expected points found in the top k, averaged over the answerable items; the
characters the talker would read (the top k passages, each cut near 1,500). *Keep:* the
smallest k whose share of expected points found is within 0.05 of k = 8's; Ole5's agent then
reads that k, and K, T and S run with it. Held-out is never read by K0; K's retrieval target
still reads the top 5.

*Amended 2026-11-08, after run K's first dev round (which decides nothing) and before its
dev runs run again (Q24):* the reply's register is judged by a question of its own, of the
judge's model. A reply to a variant or scenario turn labelled MSA must be in MSA; one labelled
Saudi or mixed whose words hold a dialect form (the library's `register_of`) must be in the
Saudi register; one labelled Saudi or mixed whose words hold none is right in either.

**K, the talker's model, retrieval and answers** (text through `TextCall` with the real model and
knowledge base; about $1.50 for both dev runs of every arm). Arms: K1 `openai/gpt-oss-120b` at low
reasoning (the design's default), K2 `llama-3.3-70b-versatile`, K3 `openai/gpt-oss-20b` at low
reasoning (Q8). *Amended 2026-11-07, before any run (Q11):* K2 is dropped, so K compares K1 and
K3. *Metrics, per variant:* retrieval (an expected point in the top 5, from the
talker's own query, and from the variant's raw words as a reference); the answer's verdict
(right, partly right, wrong, invented, or an honest "not in my knowledge" for `none` items), by
the judge (Q6); a search made when needed and not otherwise; the reply language; spoken words;
the guard's blocks; the time from the request to the first clause, on the wall clock (the
model's own time; `TextCall`'s virtual clock times the rest). *The noise:* every arm run twice on dev; a
variant whose verdict differs between the two counts as noisy. *Keep:* among the arms whose first
clause comes within 1.0 s at the median after the transcript, the one with the most right answers
by the sign test on items; a tie goes to the faster. Then held-out once with the kept arm.
*Amended 2026-11-07, before any run (Q15):* the keep rule's 1.0 s reads the model's own time,
a reply's time to its first clause less the time its tools ran (each tool's start to its end),
so the knowledge base's search is not counted; the wall clock's time is reported beside it.

**T, the time to first audio** (the dev recordings of `n01` to `n28` replayed through `AudioCall`
with the real speech, model, knowledge and voice; about $0.80). Arms: T0 with
`tts.trim_silence` off (today's), T1 on (TD-090). *Metric:* from the labelled end of the caller's
speech to the first audible frame of the reply, for replies with and without a search, and to the
progress line where one plays. *Keep T1* if its median is lower and the owner hears no clipped
first syllable in ten of its replies. *Amended 2026-11-07, before any run (Q12):* every recorded
request needs a search, so the target for a reply with no search is read from one more pass, Tn:
the same recordings with the kept `tts.trim_silence` and the knowledge tool left out of the agent,
so every reply takes the path with no search; only its times are read (about $0.25).
*Amended 2026-11-08 (the owner, "only the important ones"):* Tn stopped at 12 of 72 recordings
and read as it stood; T0's dev pass is not run again with the progress line (Q27), held-out's
pass measuring that code.
*Amended 2026-11-07, before any run (Q18):* the time starts at the owner's marked end for `n19`
to `n28` and at the speech detector's stop for `n01` to `n18`; the targets read both together,
and the scorecard shows the two groups apart.
*Amended 2026-11-07, before any run (from the live probe):* Tn's talker is also told it has no
knowledge base, its instructions' "Searching:" section replaced, and carries its own version
(`+no-search`): with that section and no tool, Groq refused 3 of 4 Ole5 questions
(`tool_use_failed`), so Tn would have timed the `error` notice.

**S, the scenarios** (text, the kept arm, each scenario three times; about $0.30). *Metric:* each
scenario's expectations (the tool called or not, the key facts said, by the judge, the language,
what was repeated or continued, no guard violation).

**The targets** (Q7; each holds on dev and on held-out's aggregates):
- the time to first audio, a reply with no search: a median of at most 1.6 s, a 90th percentile
  of at most 2.4 s;
- with a search: a median of at most 3.0 s, a 90th percentile of at most 4.0 s, and a progress
  line begun by 3.0 s whenever the answer has not (*amended 2026-11-08, Q27, from 2.0 s*);
- retrieval: an expected point in the top 5 for at least 90% of the answerable items;
- answers: at least 80% of the answerable items right, and at least 90% of the `none` items
  answered with an honest "not in my knowledge" and no invented steps;
- the reply language right in at least 95% of the variants;
- the guard: no ID spoken without evidence (zero);
- the scenarios: each passes in at least 2 of 3 runs, and the rehearsal's in 3 of 3;
- the stop: M3's time from the end of a stop word to silence still within its target (D-068).

**Expected (the agent's):** without the early start, a reply with no search about 1.9 s after the
caller's end (the 0.93 s turn end with the hold, then the transcript, the first clause and the
voice's first audio); with it, about 1.3 to 1.5 s; a search adds the tool's request, the
embedding, the search and a second request, about 0.8 to 1.2 s. The prototype measured a 1.5 to
1.6 s median for its first sound, its search apart.

**Cost and limits.** About $3 in all at Groq's published prices, read at Block 0; the cap is $5
(Q10), checked before each run. The pacer holds every run under the key's limits a minute.
*Amended 2026-11-07 (Q11, Q12):* about $2.75 in all, K2 dropped and Tn added; each runner also
reads the key's daily request limit from Groq's headers and spreads a run over days rather than
pass it.
*Amended 2026-11-08 (Q25):* the cap is $7. Run T costs about $0.95 a dev pass, not the
$0.40 estimated: each recording's greeting and reply are spoken by the Saudi voice, $40 a
million characters (Groq's models page, read that day; the English voice $22).

## The owner's questions

Q1 to Q10 settled on 2026-11-06 ("Approve all"). Q11 to Q14, from the spike, Block 0 and the
knowledge set's review, asked on 2026-11-06 before any registered run and settled on 2026-11-07;
Q15 to Q18, from Track E's review, asked and settled on 2026-11-07 before any registered run;
Q19 and Q20, from the whole-code review, and Q21, from the live smoke, asked and settled on
2026-11-07 before any registered run; Q22, after run W's dev runs and before its held-out;
Q23, after that held-out pass; Q24, after run K's first dev round and before its dev runs again;
Q25, after run T's smoke; Q26, after an exploratory pass of run K; Q27, after run T's T0;
Q28 and Q29, after run S's first pass.
Each answer that changes a run is a dated amendment to the registration.

- **Q1. What voice-first means here.** *Settled: (a).* The eight choices above. Options: (a) approve them; (b)
  change some. **The agent recommends (a).**
- **Q2. Starting during the hold.** *Settled: (a).* The 600 ms hold after Smart Turn's "complete" (D-067) adds
  600 ms to every reply. Options: (a) the transcription and the talker's first request start at
  "complete", nothing plays before the hold ends, and the work is cancelled if the caller goes on
  (about 0.4 to 0.6 s sooner a reply; a model request wasted on each resumed turn); (b) the
  transcription only (about 0.3 s sooner); (c) neither. **The agent recommends (a).**
- **Q3. What M4 leaves out.** *Settled: (a).* `simulate` (scripted scenarios instead), `t2v check` (M7, with the
  guide), `reports_on` (M5, with ticket status), `providers.md` (M7). Options: (a) leave them out;
  (b) build some of them. **The agent recommends (a).**
- **Q4. The knowledge base.** *Settled: (a).* Options: (a) T2's Qdrant and embedding gateway directly, by plain
  HTTP, one embedding and one search per question, connections kept open, no new package; (b) the
  same with the `qdrant-client` package (one install); (c) ragent2. Either (a) or (b) needs the
  Qdrant address, its key, Ole5's collection and filter, and the gateway's address, key and
  model, copied by the owner into this repository's `.env` under the names Block 0 gives. A
  snapshot of the points is kept under `var/kb/`, outside git, for drafting the knowledge set.
  **The agent recommends (a).**
- **Q5. The knowledge set.** *Settled: (a).* Options: (a) the agent drafts about 60 items from the knowledge base,
  the 28 recorded requests among them, and the owner reviews them (about 40 minutes); (b) the
  owner writes them; (c) the 28 recorded requests alone (too few for answers by language).
  **The agent recommends (a).** No new recording is needed.
- **Q6. Who judges an answer.** *Settled: (a).* Options: (a) a judge model other than the talker's reads each
  answer beside its item's points and key facts, and the owner checks 24 judged answers drawn at
  random; if they disagree on more than 3, the owner judges that run's answers; (b) the owner
  judges every answer; (c) the key facts by their words alone (misses paraphrase). **The agent
  recommends (a).**
- **Q7. The targets.** *Settled: (a).* The list under "The targets", set for Q2's (a): without the early start,
  the 1.6 s median for a reply with no search is not expected to hold. Options: (a) accept them;
  (b) change some. **The agent recommends (a).**
- **Q8. The models compared.** *Settled: (a).* K1 `openai/gpt-oss-120b`, K2 `llama-3.3-70b-versatile`, K3
  `openai/gpt-oss-20b`, and for run U `llama-3.1-8b-instant`. Options: (a) these; (b) others the
  key can call. **The agent recommends (a).**
- **Q9. English inside an Arabic call.** *Settled: (a).* A call sends Whisper its language (D-066), so an English
  question in an Arabic call is transcribed as Arabic. Options: (a) run X decides: if English
  holds under the Arabic language, the talker answers it in English; if not, the widget's
  language is switched before an English question, and the rehearsal's step 7 is an English call;
  (b) English calls only, from the start. **The agent recommends (a).**
- **Q10. The spend.** *Settled: yes.* A cap of $5 for M4's runs (about $3 expected; M3 spent $0.46 of its $5).
  **The agent recommends it.**
- **Q11. Run K's arm K2.** *Settled 2026-11-07: (a).* In the spike, llama-3.3-70b failed 6 of 10 tool calls in
  Groq's own parser and put Chinese characters into some Saudi replies, and Groq now sells both
  Llama models on contact only. Options: (a) drop K2, so K compares K1 and K3 (about $0.50 less);
  (b) keep K2 as registered. **The agent recommends (a).** Run U's U1 (llama-3.1-8b, no tools, a
  one-word verdict) stays either way.
- **Q12. Run T's reply with no search.** *Settled 2026-11-07: (a).* All 28 recorded requests need a search (26
  answerable, 2 `none`), so the target "a reply with no search" has no data unless the talker
  wrongly skips one. Options: (a) T replays the same recordings once more with the knowledge tool
  left out of the agent, so every reply takes the path with no search, and only its time is read
  (about $0.25); (b) the owner records 6 to 8 short turns (a greeting, thanks, "who are you"),
  about 10 minutes; (c) the target leaves T. **The agent recommends (a).**
- **Q13. The `none` items.** *Settled 2026-11-07: (a).* Dev holds 6 and held-out 4, so "at least 90% honest" fails on
  one miss on dev. Options: (a) the agent writes 6 more `none` items before the owner's review,
  split by the set's rule; (b) keep 6, so the target needs all of them. **The agent recommends
  (a).**
- **Q14. Where the knowledge base adapter lives.** *Settled 2026-11-07: (b), with the library's general way kept ("The owner's decisions").* The design keeps it in the Ole5 app
  until a second team needs it (its 6.3); T2's gateway and Qdrant serve every team, and the owner
  named its settings generally. Options: (a) the library, reached from the design's `knowledge`
  facade (5.1, with `knowledge_tool`), configured by the app with its address, account and tenant;
  (b) the Ole5 app, as the design says. **The agent recommends (a).** A new facade gets a decision
  entry, as D-032's did.
- **Q15. Run K's 1.0 s.** *Settled 2026-11-07: (a).* The keep rule reads "the first clause within
  1.0 s at the median", and the metric calls that time "the model's own time" but measures it on
  the wall clock, so a reply that searches first counts the knowledge base's search too.
  Options: (a) the model's own time, the tools' time taken out; (b) the wall clock, search
  included. **The agent recommends (a).**
- **Q16. Run U's held-out pass.** *Settled 2026-11-07: (a).* M3's held-out run H3 stored
  aggregates only, so no held-out overlap's words exist to read. Options: (a) replay H3's
  held-out clips live, the kept arm deciding each overlap as it comes, aggregates only (about
  $0.03 and the chat requests); (b) dev only. **The agent recommends (a).**
- **Q17. Run W1's command words.** *Settled 2026-11-07: (a).* The presets' lists also hold the
  mishearings the rule must catch («وكيف», "stopp"). Options: (a) the prompt carries each
  command word as it should be written; (b) the presets' lists whole. **The agent recommends
  (a).**
- **Q18. Run T's start of time.** *Settled 2026-11-07: (a).* `n19` to `n28` have the owner's
  marked end of speech, `n01` to `n18` the speech detector's stop. Options: (a) the targets
  read both together, the scorecard showing the groups apart; (b) only the marked ends.
  **The agent recommends (a).**
- **Q19. Words begun during a search.** *Settled 2026-11-07: (a).* A turn the caller begins
  while nothing of the reply plays is no overlap of it (D-068's amendment 7), so when the search
  ends while the caller still speaks, the progress line and the first clauses play over them
  until their turn closes. Options: (a) hold the reply while a newer turn is open: with words,
  the earlier reply is dropped and both turns answered; heard as nothing, the held reply plays;
  (b) keep today's rule and judge it on the live calls. **The agent recommended (a).**
- **Q20. What the model writes from.** *Settled 2026-11-07: the top k passages whole, k
  measured (K0).* The tool gave the talker each passage's first 3 lines, cut near 400
  characters, and the best passage's steps: about 92% of the best passage's words, about 26% of
  each other passage's text (122 of Ole5's 128 points cut). The agent recommended each passage
  whole, cut near 1,500 characters; the owner chose the full top k with k found for Ole5.
- **Q21. Groq's prompt cache.** *Settled 2026-11-07: (a).* In the live probe, 3 of 8 requests
  Groq served from its cache took 1.03 to 5.71 s to the first token, and none of 12 with a
  varying first line took over 0.30 s. Options: (a) every request's first line varies, a
  setting to turn it off; (b) keep the cache and let K and T measure how often the slow path
  hits. **The agent recommended (a).**
- **Q22. Run W1 after dev.** *Settled 2026-11-07: (a).* On dev, W1 failed its rule (term recall
  0.333 in both) but raised the right count beyond the noise, mostly on the command words, and
  wrote no word of the prompt into silence. Options: (a) a rule registered now, tested once on
  the unread held-out; (b) no prompt, as the rule decided. **The agent recommended (a).**
- **Q23. W1 after held-out.** *Settled 2026-11-07: (a).* Three of Q22's five conditions met; the
  other two cannot be read from held-out's aggregates, whose nearest aggregates are no worse.
  Options: (a) keep the prompt, live calls sending it; (b) read the two as unmet. **The agent
  recommended (a).**
- **Q24. The register of a reply to plain Arabic.** *Settled 2026-11-08: (a).* 18 variants of
  the knowledge set labelled Saudi or mixed hold no dialect word, plain MSA as written (and 7
  of run S's turns held to Saudi), and the fixed talker answers plain Arabic in MSA. Options:
  (a) for words with no dialect form, either register is right; (b) relabel them MSA. **The
  agent recommended (a).**
- **Q25. The cap.** *Settled 2026-11-08: (a).* $2.01 spent of $5 by run T's smoke, about $3.70
  left to run. Options: (a) raise it to $7; (b) keep $5 and run T's Tn and held-out on fewer
  recordings. **The agent recommended (a).**
- **Q26. `gpt-oss-120b`'s reasoning.** *Settled 2026-11-08: (a).* An exploratory dev pass at
  medium against the two at low. Options: (a) medium; (b) low. **The agent recommended (a).**
- **Q27. The progress line.** *Settled 2026-11-08: (a).* 59 of T0's 67 search turns began
  after 2.0 s with no line: the line's clock was the tool's own, and the wait is mostly the
  model. Options: (a) the line 3.0 s after the caller stops if no answer has begun, whatever the
  wait (7 of T0's 67 turns); (b) the same clock at 2.0 s (about nine in ten search answers open
  with the line, and one ready at 2.4 s is heard at about 4 s); (c) as built, the target
  reworded (silence when the model is the slow part, 6.3 s at the longest). **The agent
  recommended (a).**
- **Q28. A short request over a reply.** *Settled 2026-11-08: (b), then (a).* Run S's s09: a
  two-word request over a reply is ignored by the rule's `short_output`. Options: (a) request
  words stop it; (b) a model decides (run U); (c) leave it. **The agent recommended (a); the
  owner chose (b).** After run U: (a) the model on two or more words; (b) on every short
  overlap; (c) the rule as it is. **The agent recommended (a), and the owner chose it.**
- **Q29. Run S's strict checks.** *Settled 2026-11-08: (a), but for the key facts.* A reply in
  plain Arabic marked wrong for a caller with one dialect word; a correction answered from the
  passages it had; a short answer without a listed key fact. Options: (a) loosen them;
  (b) keep them. **The agent recommended (a).**
- **Q30. How a voice-only caller gets the steps.** *Settled 2026-11-09: the owner's own answer.*
  Options: (a) step by step, the card silent; (b) step by step, no cards; (c) all in one reply.
  **The agent recommended (a); the owner chose all the steps in one reply, repeated whole or in
  part, or one in detail, on request, with no card.**
- **Q31. What the judge counts.** *Settled 2026-11-09: (a).* Options: (a) only spoken words;
  (b) spoken and screen. **The agent recommended (a).**
- **Q32. Who checks the 24 judged answers.** *Settled 2026-11-09: (a).* The owner does not know
  the knowledge base well enough. Options: (a) an agent, against it, recorded as an agent's
  check; (b) no check; (c) a person who knows Ole5. **The agent recommended (a).**
- **Q33. K's held-out after the judge's check failed.** *Settled 2026-11-09: (a).* An agent and
  the judge differed on 7 of 24 answers, the limit 3; 4 of the 7 change pass or fail, two each
  way. Options: (a) run it once, the answer scores marked unverified; (b) skip it. **The agent
  recommended (a).**
- **Q34. The consent screen.** *Settled 2026-11-09: remove it.* It is one step of Ole5's page,
  before every call, and its text had gone stale. The agent proposed removing it and keeping the
  library's recording rule, with a note for the deployment; the owner agreed.
- **Q35. The fixes from the owner's calls.** *Settled 2026-11-09: all, as the agent recommended.*
  The name in every capitalization; arrows said as a word; English cut at sentence ends; a beat
  beside fixed lines and a new line for a reply cut off; a shorter progress line; a button's
  meaning and Arabic sound in an English reply; one narrow rule for asking back.
- **Q36. A search that failed in a call.** *Settled 2026-11-09: all three, as the agent
  recommended.* Ask a failed search once more within its deadline; sign in as the server starts;
  record each tool call and what failed in the trace.
- **Q37. What a trace holds.** *Settled 2026-11-09: the agent's words and the search's text
  too.* The owner asked for it directly, against invariant 8 as it stood; the setting that turns
  transcripts off and the redaction hook cover the new text.

## What the owner does

- Answer Q1 to Q10, and approve the plan (done 2026-11-06); answer Q11 to Q14, Q15 to Q18,
  Q19 and Q20, Q21, Q22 and Q23 (done 2026-11-07), Q24 to Q29 (done 2026-11-08), and Q30 to Q37 (done 2026-11-09).
- Copy the knowledge base's access into `.env` (Q4; done 2026-11-06, under the owner's names).
- Review the knowledge set's items (Q5, about 40 minutes; done 2026-11-07, checked by the agent
  against the knowledge base), and check 24 judged answers (Q6, about 20 minutes).
- Listen to ten replies of run T for clipped first syllables: not needed, T1 was not kept (2026-11-08).
- Hold the live calls (about 20 minutes).
