# 008 · Garbage collection, round 2

Status: active · Milestone: none (maintenance) · Started: 2026-11-13

*Asked for by the owner on 2026-11-13, after M5 closed and before the next phase is planned: "But
before all of that, lets do a round of cleaning and garbage collection, its been long overdue".*

## Goal

Remove the duplicated patterns, drift, stale docs and payable debt that milestones M2 to M5 left
(451 commits since round 1), and turn the mistakes made more than once into checks, so the next
phase (a voice for a team's own text agent) builds on a cleaner base. Every fix preserves
behaviour; the owner's rule holds: what breaks a call or misleads a reader, not hardening.

## Acceptance criteria

- [ ] The inventory below is written before anything changes: duplications, drift, recurring
  mistakes, bugs, what was considered and kept (with why), and the debt payable now.
- [ ] Every fix preserves behaviour; a bug found on the way gets a failing test first and is
  listed here, and a change a caller could notice is listed and covered by a test.
- [ ] A mistake seen twice becomes a check, a test or a doc, and golden-principles.md says which.
- [ ] The payable rows of [tech-debt.md](../tech-debt.md) are paid, and the others brought up to
  date.
- [ ] `harness.toml`'s `[gc]` values are checked against what this round's read found to be noise,
  each change in the decision log.
- [ ] After the gate, `uv run poe quality` is run and [quality.md](../../harness/quality.md)'s
  table and each layer's gaps are updated.
- [ ] garbage-collection.md's "Rounds" lists this round; `uv run poe check` passes, and the docs
  this plan touched are updated.

## Plan

1. **Measure:** `uv run poe gc` (done on 2026-11-13, before the read: a round is due, 451
   commits and M2 to M5 completed; 861 duplicate runs, 588 of them in Ole5's evals; 134 modules
   above the 300-line watch; 59 unresolved paths; 40 doc names the code lacks).
2. **Read:** six readers, one area each, read only: core and domain; agent and actions; voice;
   adapters, api, testing and the minimal example; the Ole5 app, its evals and the harness with
   the `[gc]` calibration; the living docs, the debt list, the grades, the tests' helpers, slow
   tests and the gate's warnings.
3. **Record:** the inventory below, from their findings, each checked before it is listed.
4. **Fix in blocks,** by area, each gated by `uv run poe check`.
5. **Promote, pay debt, grade, close,** as garbage-collection.md's steps 5 to 8 say.

## Inventory

Written on 2026-11-13, before anything changed, from the six readers' findings. Each ID names its
reader's area: agt/act agent and actions, voi voice, core/dom/fac core, domain and the facades,
tst/ada/api testing, adapters and api, app/evl/har the app, its evals and the harness, doc/deb/qua/tes
the living docs, the debt list, the grades and the tests. About 180 findings: 5 bugs (agt-1, core-1,
evl-1, evl-3, TD-065), each to get a failing test first; about 60 copies that must change together;
about 60 stale docs and docstrings; 13 modules at the 400-line cap with a seam to split along; the
`poe gc` noise (59 unresolved paths, of which 2 are real; 40 unknown names, of which 8 are real; 6
unreferenced definitions, all framework hooks); and about 35 debt rows paid, payable or stale.
Where two readers found the same thing, one entry covers both. The blocks split the work by files,
so that they can be built apart: W1 to W5 by layer, W6 (the docs) last, since the docs describe the
code the others leave. Each block is gated by `uv run poe check`; a fix changes no behaviour unless
its line says what changes.

**The bugs (each with a failing test first, in its block)**

- agt-1 (W1), `agent/leaked_reasoning.py:110`: `_give` rescans from `_given - 2`, so a speaker's label
  after an end mark and two or more spaces or line breaks, streamed apart («Okay.\n\n» then «User:
  hi»), is never checked and is spoken; in one piece it is caught. Reproduced. Fix: rescan from the
  last end mark before the given text. Change: such a label stops the reply, as in one piece.
- core-1 (W1), `core/settings/guard.py:85-96`: `guard.id_patterns`' validator catches only
  `re.error`; `a{4294967296}` raises a bare `OverflowError` out of `VoiceSettings(...)` and
  `from_env`. Reproduced. `tracing.redact`'s `_compiles` catches every error. Fix: one `_compiles` in
  `core/settings/base.py`, used by both. Change: a `ConfigurationError` naming the setting.
- evl-1 (W4), `evals/talker_run.py:313-319`: run K's `Session.variants` counts every variant so far,
  not the session's (`done + found.results`); runs S and A count their own. Fix: count
  `found.results`. Change: `sessions[].variants` in a resumed or unfinished run K's scorecard and
  `sessions.jsonl` (no history line carries it).
- evl-3 (W4), the run commands: "a run needs --x" is checked as falsy in three commands and as `None`
  in seven, so `--note ""` passes the parser and fails later in the run model with a traceback.
  Fix: one `require` in `evals/cli.py`. Change: an empty required flag is refused, exit 2.
- TD-065 (W3), `adapters/used_tokens.py:106-116`: `BEGIN` and `COMMIT` sit outside the rollback's
  try, so a failed `COMMIT` leaves the connection in a transaction and every later join is refused
  until a restart. Fix: the transaction inside the try. Change: a failed commit refuses that one
  join only.

**Block W1: core, domain, agent, actions (and the one-line reuses they bring to other layers)**

- agt-7, dom-1, dom-2, tst-11 (copies): the rule "a tag's primary code" (`"en" if tag == "en" else
  "ar"`) in 10 places across six layers, `agent/language.py`'s `Code` restating core's
  `LanguageCode`, `declaration.py`'s `_CODES`, and a provider's language name read in two ways
  (`agent/language.py:58-66`, `domain/yes_words.py:250-254`). One `primary_code(tag)` beside
  `LanguageCode` in core, one heard-language reader in domain, each copy using them.
- agt-5 (copy, TD-125): the models that take `reasoning_effort` listed in `agent/turn.py:121` and
  `adapters/groq_chat.py:83-86`: one `REASONING_MODELS` in `core/settings/llm.py`.
- agt-6 (copy): the sentence-end marks and the glued-mark lookbehind in `agent/leaked_reasoning.py`
  and `domain/text/clauses.py`: `clauses.py` exports `SENTENCE_ENDS`, both build from it.
- agt-8, tst-10 (copies): a card's texts (`agent/turn.py:382`, `testing/text_checks.py:92`) and a
  tool result's evidence texts (`agent/tool_calls.py:86`, `testing/text_watch.py:177`,
  `testing/text_checks.py:126`): `Card.texts()` and `ToolResult.texts()`, used by both sides.
- dom-3, dom-4 (copies): the longest-phrase-first tokenizer three times (`interruptions._tokens`,
  `yes_rule._kinds`, `yes_words.covered`) and `yes_rule._marked` restating `holds_words`: one
  `phrase_tokens` in `domain/text/words.py`; `holds_words` reused.
- dom-5 (restated definition): `action` and `draft_json`'s constraints on five models a draft passes
  through: `ActionName` and `DraftJson` types in core, reused.
- dom-6 (copy): the `pcm16` whole-samples validator and `seconds` in the speech-to-text and
  text-to-speech ports: one shared validator.
- dom-7 (copy): the arrows said as "then" in `text/scripts.py:104` and `text/speaking.py:203`:
  exported by `speaking.py`, imported by `scripts.py`.
- dom-8, dom-9 (drift): private names read across modules (`_DIGIT_CHARACTERS`, `_MARKS`) made
  public; `1 + 1e-6` replaced by `SUM_TOLERANCE`.
- core-2 (copy): the clause-fraction rule in `core/conversation.py:54-59` and
  `testing/turn_data.py:49-54`: one check function both validators call (a public model cannot
  subclass an internal one, so the models stay two).
- act-1 (dead code): `ActionRunner`'s `emit=` path, `EventSink` and the event branch of
  `action_job._ended` have no production caller (voice builds the outcome events): removed, and the
  tests that read the events assert on the returned `ActionOutcome`. `ActionRunner` is not public.
- act-2, act-3, ada-1's port part (copies): the timed read on the call's clock in `actions/runner.py`
  and `actions/action_writes.py` (one `within`); the outbox's `NO_ROW` and the aware-`since` check in
  both stores (moved to `domain/ports/outbox.py`, with the port's "result kept" rule written down).
- act-5, act-7 (drift, copy): the tool timeout default 5.0 written three times and the knowledge
  tool's FIX literals (one `TIMEOUT_S`, one `LIMIT`); the digit class in `actions/spoken_lines.py:40`
  and `domain/text/speaking.py:64` (one public `DIGIT`).
- act-6, core-7 (suppressions): `actions/knowledge.py:96`'s `type: ignore` removed by typing the dict;
  `core/tracing_export.py:147`'s given its reason.
- agt-9, core-8 (splits): `agent/turn.py` (386) loses the per-clause gate (`_said`, `_shown`, the
  guard, question limit and block note they own) to `agent/clause_gate.py`; `core/events.py` (371)
  loses the call report's models to `core/call_report.py`, re-exported by the `events` facade.
- Docstrings: agt-2, agt-3, agt-4 (the turn's steps without the leak filter; the leak filter said to
  stop "as the question limit" does, which it does not; pointers to `agent/talker.py` that belong to
  `tool_calls.py`; plan-time wording); act-4 (a tool timeout said to be logged at ERROR, logged at
  WARNING as `tool_timed_out`); core-4, core-5, dom-10, dom-11, fac-1 (`core/events.py`'s "declared
  for plan 007's tracks" and other promises now kept; the layer maps of core, domain and domain/text;
  plan-time wording in `action_lines.py`, `clauses.py`, `declaration.py:298`, `settings/stt.py:4-5`,
  `settings/llm.py:2-3`; the ports with `aclose()`; `languages.py` saying `register_of` gives MSA for
  a turn with no Arabic, where it gives Saudi).
- core-9 (watch): `core/config.py` (392) and `domain/yes_rule.py` (380), with their seams, go to
  TD-140, split at the next addition.
- TD-141 (the owner's answer: wire them in): `agent/speech_guard.py` and `testing/text_checks.py`
  build on `domain/guard.py`'s `check_clause`, which gains the `earlier` clauses rule A reads, so the
  rules' order and evidence are written once; each action's state in `actions/action_job.py` moves
  through `domain/action_flow.py`'s `advance`, and a move the table refuses is logged as
  `action_flow_refused` (a bug), never raised into a call. W2 does the same for the session's
  `Confirming` (`voice/session/read_back.py`, `yes_turns.py`). No decision changes: the table is the
  code's own, so a call goes as before.

**Block W2: voice**

- voi-3 (copy, a security rail): the check that a yes is the receipt's, in both the model path and
  the lists path of `voice/session/yes_turns.py`: one `_checked`.
- voi-6 (copy, already drifted): the timed chat request and its whole-answer read in `overlap_ask.py`
  and `yes_ask.py` (one counts the request before checking for a model, the other after): one
  `voice/session/model_word.py`, each module keeping its own rules.
- voi-2, voi-7 (copies): the re-judging after a go-on in `interrupter._take` and `_hand_over`; "the
  replies in progress to earlier turns" in `interrupter.py:316-326` and `talking.py:311-328`: one
  `_judged_again`, one `Playback.earlier`.
- voi-4, voi-5 (restated definitions): the stop-word, repeat and go-on verdicts voice rebuilds by
  hand, named by domain and reused; `_LANGUAGE_CHARS` restating core's `_Heard`, a core helper.
- voi-8, voi-9, voi-10 (copies): `AUDIBLE_FLOOR` and testing's `NOISE_FLOOR`, both 328 (testing
  imports voice's); two phrase-cache lookups logging `phrase_not_declared` (one, with the reply's
  number kept); a reply's scope, heard entry and span opened twice in `speaker.py` (one `_opened`).
- voi-11, voi-12 (dead code): `Talk.task` and `ducked_at` removed; `OpenReply`'s optional `writer` and
  `setup` and `_parts` made required, their test-only path gone. The test-only state
  (`OverlapState.window`, `Reply.failed`, `TurnLanguages.classifies`) is kept: the tests read it.
- TD-141's session part (with W1's): the confirming state's moves through `advance`, a refused move
  logged as `action_flow_refused`.
- voi-21, voi-22, voi-23 (placement): `TICKER_BOUND_S` moves to the tests' kit; the `Guarded` alias to
  `io.py`; `session_bridge.py`'s `CallEvents` is renamed `EventStream` (two classes shared a name).
- Splits, so the next change lands without squeezing: voi-24 (`talking.py` 397: the run loop of one
  `Talk` to `talker_play.py` as `TalkRunner`), voi-25 (`call.py` 396: `_hold` and `_held` to
  `Talking`, the docstring to a map), voi-26 (`speaker.py` 387: the cut clause's share to
  `cut_share.py`), voi-27 (`interrupter.py` 388: voi-2, voi-7 and its docstring's repeated bullets as
  pointers), voi-28 (`read_back.py` 381: the decline bookkeeping to `read_back_declines.py`; the
  receipt stays, as `[[restricted]]` names this file), voi-29 (`calls.py` 395: the api-facing
  protocol to its own module).
- Docstrings: voi-1 (`talking.py` says `error` where the code says `cut_off` after a clause, D-077),
  voi-13 (the layer maps), voi-14 (the parity test that "comes later" exists), voi-15 (the reply
  kinds said wrongly in six places; one list in `io.py`), voi-16 (a repeat said to find clause-cache
  takes, on a path that never has them), voi-17 (`DROP_AFTER_S` and `OVERLAP_LEAD_S` written as
  numbers; TD-060's no-tail rule missing from `io.py`), voi-18 (`VoiceCalls`' chat said to judge
  overlaps only; it judges read-back answers too, D-082), voi-19 (Pipecat paths written as
  `pipecat/transports/...`).

**Block W3: adapters, api, testing, the minimal example**

- TD-065 (bug, above).
- tst-1, tst-2 (copies, already drifted): the talker built three times (`api/providers.py`,
  `testing/text_watch.py`, `testing/text_call.py`, one without the settings' prefix) and the agent's
  action runner three times (`api/actions.py`, `testing/text_call.py`, `testing/audio_call.py`): one
  factory in `agent/`, `tools_of` and `actions_of` and one runner builder in `actions/`, used by the
  runtime and both calls. Change: `TextCall`'s "session.mode is talker" error names the variable with
  the settings' prefix, as the runtime's does.
- tst-3 (copy): `TextCall(agent, llm=model, language=scene.tag, caller=scene.caller)` 14 times in the
  safety suite: `Scene.call(agent, model)`.
- tst-5, tst-6, tst-7 (restated definitions): Groq's 10 s billing minimum written three times (one
  constant in core, the app's tie test pointed at it); `RequestPart` and `TranscriptPart` untied (a
  test); `CLIP_RATE` restating `file_transport.RATE` (imported).
- ada-1, ada-2, ada-3, ada-4, ada-5, ada-6 (copies): the SQLite helpers of the outbox and the
  used-token store (`adapters/sqlite_files.py`); the Groq key resolution three times and the
  mid-stream httpx error mapping twice (`groq_client.py`); a WAV written in `groq_stt.py` and
  `wav_files.py`; the key-ID pattern restated in `join_tokens.py`; the one-classification-at-a-time
  lock in both classifiers (`model_files.py`).
- api-1 (copy of a security rule): "a loopback client" defined in `api/router.py` and
  `adapters/dev_identity.py`, the dev page using one and the console the other (measured equal on
  every case): one, `is_loopback`.
- api-2, api-3, api-6 (copies): the route-registration loop; the agent's folder under `var_dir`; the
  four providers listed twice to close them (and `t2v doctor` stops at the first that raises).
- api-4 (latent trap): `protocol_mismatch` has an entry in `MESSAGES` that `error_body` cannot build
  (it needs the notice); `invalid_request` has two wordings: one place for each.
- api-5 (drift): `t2v doctor` imports `Providers` through `api/runtime.py`, which pulls in FastAPI.
  Change: `t2v doctor` starts about 0.75 s faster.
- Splits: tst-9 (`testing/text_call.py` 396: the clock driver to `text_side.py`), api-7
  (`api/runtime.py` 391: its docstring's restated router, records and error sections to pointers),
  api-8 (`api/dev_console.py` 391: the feed and its disk store to `api/dev_feed.py`).
- Docstrings: tst-12, tst-13, ada-7, ada-8, ada-9, api-9, api-10, api-11 (the layer maps of testing,
  adapters and api; the clause cache's log lines; `status.py`'s pointer to a health route that does
  not use it, which says now what uses it: the owner keeps `status` and `Status`; plan-time track
  names).
- tes-2 (copy): the same task-waiting helper in two adapter test modules.
- Kept: tst-4 (run T's usage re-derived from the events instead of the session's report): the copy
  differs in how headroom is kept, and taking the session's would change run T's scorecard; a debt
  row instead. tst-8 (the text and audio calls declare every progress line, the runtime only the
  ones a tool names): no line is spoken today, so the parity holds in practice; a debt row.

**Block W4: the Ole5 app and its evals**

- evl-1, evl-3 (bugs, above).
- E1, the command line (evl-2, evl-4, evl-5, evl-12): one set of argparse types (`count`, `amount`,
  `seconds`, a model price) and one `require` in `evals/cli.py`; `EFFORTS` read from the library's
  literal. Changes: a timeout of 0 refused at parse time (exit 2); one message for a bad
  `--tts-price`.
- E2, settings loading (evl-6, a privacy rule): the `.env` fallback four times: one `env_file_of`, one
  loader for `poe eot` and the language run.
- E3, held-out rules and history lines (evl-7, evl-8, evl-13): the held-out group check eight times
  and the pooling into "other" four times (one `check_groups`, one public pooling helper); one
  `ModelName`; the spend helpers beside `Session`. No line's shape or field order changes.
- E4, outputs (evl-9, evl-17): one atomic JSON writer and one "record the line twice" helper; the
  history page's tables built with `table()`.
- E6, readers and reports (evl-14, evl-15, evl-16): one TOML folder reader, one wording of the
  comparison sentences, one paused request's true end.
- evl-18, app-2 (docstrings, map): run A missing from `run_lines.py`'s list; `talker_args.py` naming
  runs K and S only; CLAUDE.md's table saying which runs refuse the main checkout (every run does).
- tes-1 (copy): the same `environment` fixture in four of the app's test modules: one in
  `tests/ole5_voice/conftest.py`.
- E5, the spending runs' session loop (evl-10, evl-11; the owner's answer: this round): one
  `evals/session_runner.py` for runs K, S and A, with K0 and T sharing its closing wrapper, `main` and
  the held-out silencing of the library's logs. Change: a library error raised after a run began
  exits 1 in every run, as run T does (2 in runs K, S, A and K0 before).

**Block W5: the harness**

- har-1 to har-5, har-14 (calibration): `poe gc`'s path bases gain the package and app roots, the
  app's data folder and `tests/t2_agentic_voice`; `[gc] path_ignored` gains the prototype's files
  (`voice/rules.py`, `voice/stt.py`, `voice/tts.py`, `web/voice.js`, `agent/handlers.py`) and
  `pipecat/`; `[gc] hooks` gains `model_post_init` and `process_audio_frame`. Measured: unresolved
  paths 59 to 2, unreferenced definitions 6 to 0.
- har-9 to har-12 (calibration): `[gc] name_files` gains the library's and the widget's JavaScript and
  the tests' `.mjs` and the golden set's `split.json`; `foreign_names` gains 12 names of LangGraph,
  Phoenix, Python, uvicorn, the browser, Pipecat, httpx and the prototype; a placeholder name is
  skipped. Measured: names 40 to 8.
- har-17 (display): the duplicates are printed one line per repeated run with every place it starts
  (861 lines to 375), `min_tokens` kept at 25 since real copies run 29 to 49 tokens.
- har-15 (suppressions): every test `noqa` without a reason gets one.
- tes-3, tes-4, tes-5 (slow tests): the two architecture tests that each import the whole library in a
  child become one child (about 30 s of a worker); the gc report's test runs on a small project, as
  D-088 did for the commands; the tickets server test gets test detectors instead of warming Silero
  and Smart Turn.
- deb-1 (debt, a row now paid and removed): the stand-ins in `tests/t2_agentic_voice/voice/session/conftest.py` are
  removed, and the gate's only warning (Pipecat's own `AudioContextTTSService` deprecation, 8 times)
  is filtered in `pyproject.toml` beside the audioop filter.
- Promote (step 5), each seen twice: plan-time names ("Track C", "Block 0") in the library's and the
  app's living docstrings (round 1's app22 and this round's agt-4, dom-10, tst-13, ada-9, api-11)
  become a check, `DOC-PLANWORDS`; the layer maps that list each module and drift (round 1's lib11
  and this round's voi-13, core-5, ada-8, api-9, tst-12) become one map, ARCHITECTURE.md's, with each
  layer's `__init__` describing the layer and pointing at it.

**Block W6: the docs, the debt list, the grades (last)**

- doc-1 to doc-3 (against D-075): agent-led-mode.md's "Speech" puts the full steps "on your screen";
  browser-client.md's "Cards" and serving.md call a card the answer "for the screen"; the roadmap's
  M3 and M4 lines promise a screen. Each says what D-075 settled: every step is said, nothing relies
  on a screen. How a team agent's long answer is spoken stays the next phase's question.
- doc-4 (wrong default): concepts.md gives `T2V_LLM__REASONING_EFFORT` a default of `low`; it is
  `medium` (D-074).
- doc-5 to doc-12, doc-14, doc-15, doc-17 to doc-19 (stale): run T's numbers in latency.md and the
  guide's README; the guide's "still to come (plan 007)"; evaluation.md's "no tooling yet";
  ARCHITECTURE.md's and CLAUDE.md's "later" for what is built (within CLAUDE.md's 120 lines); the
  roadmap's Decided list (stops at D-068), its settled questions and its missing *Done* lines for M2,
  M4 and M5; SECURITY.md's invariant 3 naming the plan instead of its tests; GP-19's test pointers;
  WORKING-RULES.md's launch.json (three entries, one of which spends); the guide's one-line slips (a debt row, now paid and removed);
  latency.md's 0.94 and 0.93 s for one quantity; package-design.md's "built so far" notes;
  garbage-collection.md's serial `--durations`.
- doc-16 (untraced numbers, GP-16): the Ole5 README's "about 15 s" first start and latency.md's
  3,617-character prompt and "medians 0.20 and 0.18 s": measured again or removed.
- deb-1 to deb-18, core-6, har-6, har-7 (the debt list): paid rows removed (GP-19's pointer, the suite's stand-ins,
  the guide's slips, the cards' screen, and the parts of others paid); stale rows brought up to date (TD-034, TD-048, TD-056,
  TD-058, TD-059, TD-063, TD-090, TD-095, TD-104, TD-121, TD-124, TD-125, TD-127, TD-129, TD-130);
  the rows whose trigger passed given their next real trigger (TD-005, TD-014, TD-022, TD-068, TD-070,
  TD-075, TD-080, TD-081, TD-083, TD-087, TD-093, TD-103, TD-111); module sizes kept in TD-140 alone,
  with today's list; the rows due "at the next round" (TD-049, TD-051, TD-062, TD-106, TD-117, TD-120)
  paid or given a new trigger, TD-065 paid in W3.
- qua-1, qua-2: quality.md's table and every layer's gaps, after the round's gate.

**For the owner** (answered on 2026-11-13; the decision log has each answer)

1. E5 (evl-10): the spending runs K, S, A, K0 and T share one session loop copied five times. It is
   the largest block and touches the commands that spend (tested with the fakes, no live run).
   Recommendation: this round.
2. evl-11: a library error raised after a spending run started exits 2, "refused", in runs K, S, A and
   K0, and 1 in run T. Recommendation: 1 everywhere (no known trigger today).
3. `api/status.py`'s `status` and `Status`, public at the package root: nothing in the runtime uses
   them, only the app's `app.py` (itself used only by its test). Recommendation: remove both, with
   `app.py` (nothing is released yet).
4. TD-141: `domain/action_flow.py` and `domain/guard.py`'s `check_clause` have no runtime reader,
   while their docstrings describe them as the flow and the guard. Recommendation: remove them and
   their tests, and point the docstrings at the code that runs (`voice/session/read_back.py`,
   `agent/speech_guard.py`).
5. Two working rules held only in completed plans and the agent's memory, for WORKING-RULES.md:
   "Focus on things that matter" (2026-11-03: review only what breaks a call, no hardening rounds)
   and "I don't care about the money as much as I care about wasted time and useless runs"
   (2026-11-10). Recommendation: add both, quoting the owner.
6. `[gc] due_after_commits` 40 to 100 (about one milestone: M2 to M5 took 119, 105, 169 and 58
   commits), and the duplication score in `poe quality`, at zero for 8 of 11 units since 10 runs
   score zero. Recommendation: 100, and the duplication floor scaled by a unit's size.

**Considered and kept** (so the next round need not redo them): protocols restated by their
implementations (ports, `ReplyWriter`, `Calls`, `ReplyScope`); look-alikes whose inputs differ (the
Groq adapters' constructors, the classifiers, the safety suite's case scripts, the count models
projected from the metric models, the per-run parts, `tts_bridge`'s played and failed paths); the
two `model_validate_json` overrides with different error builders; `SignedConsent` apart from
`SealedModel` (D-032); the test doubles of the clock, the chat model and the sample actions; the
child-process and real-time tests that are slow for what they test (D-088); `size_watch` 300 and
`min_tokens` 25; TD-061 (it would re-key every phrase file); the debt rows spot-checked and still
open as written (TD-001, 011, 036, 039, 041, 042, 044, 047, 053, 055, 064, 089, 102, 117, 118).

## Progress log

- 2026-11-13: Branch `garbage-collection-2` from main fdb4040, worktree `.claude/worktrees/gc-2`;
  `uv run poe gc` measured; six readers started.
- 2026-11-13: The inventory recorded (8b82900). Blocks W1, W4 and W5 started from it, each in its
  own worktree and branch (`gc2-w1`, `gc2-w4`, `gc2-w5`).
- 2026-11-13: W5 merged (7ec3be6, from a021b09, 9e68f23, ca1d2e4): the calibration in the decision
  log. `poe gc` after it: 13 unresolved paths, 11 of them this plan's and 2 outside it (the guide's
  planned `reference/api.md`, and tech-debt.md's `agent/clauses.py`, real, for W6); 14 names, 7 of
  them this plan's and 7 outside it (tech-debt.md's `SessionSetup`, real, for W6; the rest a row's
  proposed or missing names); 0 unreferenced; 1 `noqa` without a reason (27 before), another
  block's. tes-3: one child imports the whole library for both architecture tests, 9.3 s alone
  (the two took 8.0 and 8.4 s). tes-4: the report's test on a small project, 15.4 s to 0.20 s.
- 2026-11-13: W1 merged (391dba3, seven commits e19e480 to 00de0aa). agt-1 and core-1 fixed, each
  with a failing test first; the copies made one; act-1's unused event path removed (the tests
  assert on the returned `ActionOutcome`); TD-141's guard and action-job parts; `agent/turn.py`
  386 to 344 lines with `agent/clause_gate.py`, `core/events.py` 371 to 229 with
  `core/call_report.py` and `core/ids.py`. Gate on W1 and W5: 7823 passed, 1 skipped, coverage
  99.24%.
- 2026-11-13: W4 merged (9648cf6, nine commits b09e759 to c010cba). evl-1 and evl-3 fixed with
  failing tests first; E1 to E6 with `evals/session_runner.py`; tes-1, and tes-5 (the tickets
  server test 12.0 s to 0.3 s). Changes a caller notices beyond the inventory's, each tested: a
  scenario file holding another ID says "holds the scenario '<id>', not '<stem>'", as items did;
  run S logs `run_resumable` as K and A do; `run_failed` carries `of=` in every run; the session
  lines come from the `session_runner` logger. Gate on W1, W4 and W5: lint, types, arch and docs
  OK, 7870 passed, 2 failed, coverage 99.26%; the two failed only their real-time bound under
  the load of the two blocks starting (0.229 s for 0.03 s, 0.215 s for 0.1 s) and passed alone.
- 2026-11-13: Real-time tests failed under load in W1's, W4's and W5's gates and on the merged
  branch (the clause cache's 0.1 s reads, the chat deadline, `test_stt_language.py`, a loopback
  duck): a mistake seen more than twice, so W2 and W3 make each independent of the machine's
  speed, and W6 records the rule (step 5). W2 and W3 started from 9648cf6.

## Decision log

- 2026-11-13: The owner's answers to the inventory's questions. (1) E5, "Merge them now": the
  spending runs share one session loop this round, and a library error after a run began exits 1
  everywhere. (2) `api/status.py`, "Keep them": `status` and `Status` stay public, and the Ole5 app's
  `app.py` with them; only the docstring pointing at the runtime's health route is fixed. (3) TD-141,
  "Wire them in": the live guard and `TextCall`'s check build on `check_clause`, and each action's
  state moves through `advance`. (4) The two working rules, "Leave them out": WORKING-RULES.md is not
  changed. The agent took its own recommendation on (6): `[gc] due_after_commits` goes to 100, about
  one milestone, and the duplication score is looked at in W5.
- 2026-11-13: How the blocks run. W1 (core, domain, agent, actions, with the cross-layer reuses it
  introduces) first, since W2 and W3 build on its definitions; W4 (the app's evals) and W5 (the
  harness) beside it, as they touch none of its files; then W2 (voice) and W3 (adapters, api,
  testing); W6 (the docs and the debt list) last, then the grades. Each block in its own worktree
  from `garbage-collection-2`, gated by `uv run poe check`, read by the agent before it is merged.
  The plan-time-words check (`DOC-PLANWORDS`, promoted in W6) comes after the code blocks have
  removed those words, so no block's gate fails on another's files. Each layer's `__init__`
  docstring describes its layer and points at ARCHITECTURE.md's map, in that layer's block.
- 2026-11-13: W5's `[gc]` and `[quality]` values, each measured with `poe gc` on its branch (the
  counts outside this plan, which cites paths and names to come). `path_bases` gains the source
  roots (in `gc_docs.path_bases`), `apps/ole5-voice-agent/evals` and `tests/t2_agentic_voice`;
  `path_ignored` gains the prototype's five files, `pipecat/`, and `transports/smallwebrtc/`
  until W2 writes voice's Pipecat paths as `pipecat/transports/...`: unresolved paths 59 to 2.
  `name_files` gains the library's and the widget's JavaScript, the tests' `.mjs` and the golden
  sets' `split.json`, `foreign_names` 12 names, and a placeholder (`NNN`) is skipped: names 40 to
  7. `hooks` gains `model_post_init` and `process_audio_frame`: unreferenced 6 to 0.
  `due_after_commits` 40 to 100. `min_tokens` 25 and `size_watch` 300 kept. The duplicates print
  one line per repeated run (861 lines to 375 runs, 100 of them in three or more places; the
  pairs `poe quality` counts are unchanged). `[quality] duplication_floor` 10 pairs to 10.0 pairs
  per 1,000 lines, as suppressions are scored: units scoring zero 8 of 11 to 2 (testing 33.3,
  ole5_voice 24.3); a small unit is now as sensitive as its suppressions score already was.
  Each kind of noise silenced is tested to leave a stale path or name beside it reported.
- 2026-11-13: The blocks' departures from the inventory, read before each merge. W1: `primary_code`
  takes a `str`, since the text-to-speech port passes the language as one; `core/ids.py` holds the
  ID types, so `core/events.py` and `core/call_report.py` do not import each other; `within` and
  `called` are public, as another module imports them; the session's read-back moves through a
  pure helper of `domain/action_flow.py`, since voice may not import actions (W2). W4: the TOML
  folder reader is in `items.py` and `table()` in `history_tables.py`, each to avoid an import
  cycle; the comparison helpers are `change_counts`, `changed_ids`, `sign_verdict`; the server
  tests' constants are in `tests/ole5_voice/server_support.py`, not a conftest.
