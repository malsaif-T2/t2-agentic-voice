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
   full steps go to the screen as a card (`t2v/1`).
6. **Honest waits.** A search that runs past a set time gets a pre-recorded progress line. No
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
- [ ] **Progress lines**: spoken only when a tool runs past its progress time, from the phrase
  cache; a test that no fixed line of the library or of Ole5 holds a word of the presets' lists.
- [ ] **Knowledge**: `KnowledgeBase.search(query, *, language, caller, limit) -> list[Passage]`
  and `knowledge_tool(kb, description=..., progress=...)`: one search per question, short
  summaries to the talker, the full passage as a card.
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
13. K, the talker's model, retrieval and answers (text, the real knowledge base).
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

**W, the Whisper prompt and English in an Arabic call** (speech-to-text only, about $0.05 a run).
Arm W1 sends the vocabulary (Ole5's product terms and the presets' command words) as Whisper's
prompt; W0 sends none (today's). Arm X sends the golden set's English items with the Arabic
language, as an Arabic call would. *Metrics:* term recall, word errors, stop and pause words
heard, and text from silence, noise and echo, by stratum. *Keep W1* if term recall rises by the
sign test on items, with word errors and text from silence no worse than the noise (D-024), then
held-out once; Whisper can write a prompt's words into silence, which the silence items catch.
*X decides Q9:* English in an Arabic call is supported if X's word errors on the English items
are within the noise of the English language's.

**U, the uncertain middle** (offline on stored transcripts; about $0.05). For each overlap whose
rule verdict is a short output or too few words, a model reads the reply clause the caller heard
and the overlap's words and answers "go on" or "stop". Arms: U0 the rule (D-061), U1
`llama-3.1-8b-instant`, U2 the talker's model. *Metrics:* right verdicts, listening sounds that
stopped the agent, the model's time to its answer. *Keep* an arm that raises right verdicts by the
sign test on items, stops no more listening sounds than U0, and answers within 300 ms at the
median, then held-out once; otherwise the rule stays.

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

**T, the time to first audio** (the dev recordings of `n01` to `n28` replayed through `AudioCall`
with the real speech, model, knowledge and voice; about $0.80). Arms: T0 with
`tts.trim_silence` off (today's), T1 on (TD-090). *Metric:* from the labelled end of the caller's
speech to the first audible frame of the reply, for replies with and without a search, and to the
progress line where one plays. *Keep T1* if its median is lower and the owner hears no clipped
first syllable in ten of its replies. *Amended 2026-11-07, before any run (Q12):* every recorded
request needs a search, so the target for a reply with no search is read from one more pass, Tn:
the same recordings with the kept `tts.trim_silence` and the knowledge tool left out of the agent,
so every reply takes the path with no search; only its times are read (about $0.25).

**S, the scenarios** (text, the kept arm, each scenario three times; about $0.30). *Metric:* each
scenario's expectations (the tool called or not, the key facts said, by the judge, the language,
what was repeated or continued, no guard violation).

**The targets** (Q7; each holds on dev and on held-out's aggregates):
- the time to first audio, a reply with no search: a median of at most 1.6 s, a 90th percentile
  of at most 2.4 s;
- with a search: a median of at most 3.0 s, a 90th percentile of at most 4.0 s, and a progress
  line begun by 2.0 s whenever the answer has not;
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

## The owner's questions

Q1 to Q10 settled on 2026-11-06 ("Approve all"). Q11 to Q14, from the spike, Block 0 and the
knowledge set's review, asked on 2026-11-06 before any registered run and settled on 2026-11-07;
each answer that changes a run is a dated amendment to the registration.

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

## What the owner does

- Answer Q1 to Q10, and approve the plan (done 2026-11-06); answer Q11 to Q14 (done 2026-11-07).
- Copy the knowledge base's access into `.env` (Q4; done 2026-11-06, under the owner's names).
- Review the knowledge set's items (Q5, about 40 minutes), and check 24 judged answers (Q6, about
  20 minutes).
- Listen to ten replies of run T for clipped first syllables (about 5 minutes).
- Hold the live calls (about 20 minutes).
