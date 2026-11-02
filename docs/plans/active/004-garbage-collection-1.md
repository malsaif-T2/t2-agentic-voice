# 004 · Garbage collection, round 1

Status: active · Milestone: none (maintenance) · Started: 2026-11-02

## Goal

Remove the duplicated patterns, drift, stale docs and payable debt that milestones M0 and M1 left,
before M2 starts building, and turn the mistakes the plans made more than once into checks, so
M2 builds on a cleaner base. As the first round, it also calibrates `harness.toml`'s `[gc]`
thresholds against what its read finds to be noise ([garbage-collection.md](../../harness/garbage-collection.md)).

## Acceptance criteria

- [ ] The inventory below is written before anything changes: duplications, drift, recurring
  mistakes, bugs, what was considered and kept (with why), and the debt payable now.
- [ ] Every fix preserves behavior; a bug found on the way gets a failing test first and is
  listed here, and a change a caller could notice is listed and covered by a test.
- [ ] A mistake seen twice becomes a check, a test or a doc, and golden-principles.md says which.
- [ ] The payable rows of [tech-debt.md](../tech-debt.md) are paid, and the others brought up to
  date.
- [ ] `harness.toml`'s `[gc]` values are calibrated, each choice in the decision log.
- [ ] After the gate, `uv run poe quality` is run and [quality.md](../../harness/quality.md)'s table
  and each layer's gaps are updated.
- [ ] garbage-collection.md's "Rounds" lists this round; `uv run poe check` passes, and the docs
  this plan touched are updated.

## Plan

1. **Measure:** `uv run poe gc` and `uv run pytest --durations=20` (done before the read).
2. **Read:** five readers, one area each (the library, the app, the harness with the
   thresholds, the living docs, the debt list with the quality grades), read only.
3. **Record:** the inventory below, from their findings, each checked before it is listed.
4. **Fix in blocks,** each in its own worktree, by area, checked by an agent that did not write
   it, gated by `uv run poe check`, and merged.
5. **Promote, pay debt, grade, close,** as garbage-collection.md's steps 5 to 8 say.

## Inventory

Written on 2026-11-02, before anything changed, from the five readers' findings (each id names
its reader: lib the library, app the Ole5 app, har the harness, doc the living docs, deb the debt
list). 143 findings: 8 bugs (app0, app7, app8, har20, har21, doc1 with deb18, doc8, and the
prefix gap of deb4), 13 recurring mistakes, 25 duplications, 17 restated definitions, 15 drifts,
28 stale docs, 18 payable debts, 8 thresholds and 11 noise. Where two readers found the same
thing, one decision covers both. Each block below is built in its own worktree, checked by an
agent that did not write it, gated and merged; Block R comes first since it touches every
layer, and Block D last since the docs describe the code the other blocks leave.

**Block R, first: the rename of `AppError` to `T2VoiceError` (the debt row on it, paid by D-026), every use, with the alias** (1)

- deb17 (payable debt, small, a change a caller could notice),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/errors.py:29`: The debt row on `AppError` (AppError where the
  design names T2VoiceError) is cheaper now than it will ever be again: nothing has been tagged or
  installed, and only the repository uses the name. Decision: the owner's answer: rename it now.

**Block L: the library, its tests, `tests/conftest.py`, `.env.example`** (21)

- lib3 (recurring mistake, medium), `tests/t2_agentic_voice/core/test_config.py:36`: A value leaking
  through error text, an exception chain or a third-party log line was fixed at least six times: the
  key file's decode chain, urllib's URL error, from_env's chain, GroqSTT's chain, the OTLP %0A
  header in requests' error, the SDK's header... Decision: with doc13.
- lib4 (duplication, small),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py:122,125,222-223`: The rule that
  turns a settings location into an environment name (PREFIX + group__FIELD, upper case) is written
  twice, in Settings.from_env and in groq_stt._checked.
- lib5 (duplication, small), `packages/t2-agentic-voice/src/t2_agentic_voice/domain/scoring.py:29
  and domain/text/spelling.py:15`: `_holds(text, phrase)` (whole-word containment of normalized
  texts, `f" {phrase} " in f" {text} "`) is defined twice in domain.
- lib6 (duplication, small), `tests/conftest.py:19,24,54-57`: The list of variables the suite drops
  is spelled twice in conftest itself (_DROPPED for pytest_configure, then two separate loops in the
  session fixture), and a third time in test_groq_stt's child shell, `dropped = ("GROQ_", "OTEL_",
  "PHOENIX_", "T2V_")`.
- lib7 (duplication, small), `tests/conftest.py`: structlog's configuration is process-wide and
  nothing in the shared conftest resets it between tests.
- lib8 (drift, small), `tests/t2_agentic_voice/adapters/test_groq_stt_checks.py:21`: The adapter
  tests share helpers by importing a test module (`from
  tests.t2_agentic_voice.adapters.test_groq_stt import CLIP, KEY, SETTING, FakeGroq, call, parts`).
- lib9 (stale doc, small),
  `packages/t2-agentic-voice/src/t2_agentic_voice/domain/ports/speech_to_text.py:56-57`:
  Transcript.confidence is documented as 'The provider's own confidence'.
- lib10 (stale doc, small, a change a caller could notice),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/redaction.py:5-6,36-43`: The docstring says
  'each stretch any of them matched becomes one replacement'.
- lib11 (stale doc, small), `packages/t2-agentic-voice/src/t2_agentic_voice/core/__init__.py:1`: The
  layer docstrings no longer list what the layers hold.
- lib12 (stale doc, small),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py:10-11,143`: Living docstrings still
  use plan-time wording or no longer match the code.
- lib13 (drift, small, a change a caller could notice),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py:229-230`: The ConfigurationError
  FIX lines say '.env.example lists every setting'.
- lib15 (drift, small), `packages/t2-agentic-voice/src/t2_agentic_voice/__init__.py:13-15`: The
  package root exports NotFoundError, which nothing uses, and InvalidRequestError, which only the
  app's worktree.py uses.
- lib17 (drift, small), `packages/t2-agentic-voice/pyproject.toml:8,11-13`: The adapter's security
  guarantees were read against groq 1.7.0 (and TD-005 against opentelemetry-sdk 1.45.2):
  GROQ_CUSTOM_HEADERS handling, GROQ_LOG on import, the request hook and the cause chain.
- lib18 (payable debt, small), `docs/plans/tech-debt.md:41`: TD-027 (httpx imported, and named in
  GroqSTT's public signatures, but not declared) can be paid now.
- lib19 (duplication, small), `tests/t2_agentic_voice/core/test_config.py:24,41`: There are two
  walks of the same settings tree in test_config: _keys (environment names) and _fields (dotted
  names and annotations).
- doc8 (bug, medium, a change a caller could notice), `.env.example:6,9-40`: .env.example tells the
  owner to copy it and says 'a blank value keeps the default', but it writes every non-secret
  default as a value (T2V_STT__MODEL=whisper-large-v3, T2V_STT__TIMEOUT_S=6, T2V_ENV=dev, ...).
  Decision: the file and its test are the library's.
- doc13 (recurring mistake, medium), `docs/harness/golden-principles.md:30`: A rejected or secret
  value echoed in an error, a warning or a log line was fixed at least four times in M1. Decision: a
  shared test helper for what an error may show, used by the library's tests (GP-19).
- deb4 (payable debt, small, a change a caller could notice),
  `packages/t2-agentic-voice/src/t2_agentic_voice/domain/text/spelling.py:15`: TD-025 is payable
  now. Decision: TD-025, a behavior change of a public helper, with a test per prefix.
- deb5 (payable debt, small), `packages/t2-agentic-voice/pyproject.toml:7`: TD-027 is still true and
  payable now. Decision: with lib18.
- deb7 (duplication, small), `packages/t2-agentic-voice/src/t2_agentic_voice/domain/scoring.py:29`:
  `_holds` is defined twice with the same body, in scoring.py and spelling.py. Decision: with lib5.
- deb12 (stale doc, small), `packages/t2-agentic-voice/src/t2_agentic_voice/core/tracing.py:11`: Two
  module docstrings say only OTEL_SDK_DISABLED and OTEL_PYTHON_CONTEXT are read whatever is passed.
  Decision: the tracing modules' docstrings.

**Block A: the Ole5 app's evals code, its tests and `examples/minimal`** (37)

- lib0 (restated definition, small),
  `packages/t2-agentic-voice/src/t2_agentic_voice/domain/scoring.py:22`: The form every scorer
  compares (normalize_arabic, then normalize_digits) is defined once in the library as scored_form,
  but no facade exports it. Decision: the owner's answer: tie the copies with tests, no new export;
  the app's three copies become one.
- lib1 (restated definition, medium), `apps/ole5-voice-agent/src/ole5_voice/evals/run.py:57-58,
  answerers.py:47, runs.py:109,123`: The app restates four more library definitions that the facades
  do not export, and only one of the copies is tied to the library by a test: MODELS =
  (whisper-large-v3, whisper-large-v3-turbo) copies SttModel; GROQ_BASE_URL copies
  GroqSettings.base_url's... Decision: the owner's answer: tie each copy to the library value with a
  test.
- app0 (bug, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/import_talkover.py:150`: The talk-over import's reader
  (`_read`) validates refs.json and takes.json through TypeAdapter(dict[str, LabSegment]) and puts
  the pydantic error text into GoldenSetError, which main logs.
- app1 (recurring mistake, medium),
  `apps/ole5-voice-agent/src/ole5_voice/evals/import_talkover.py:153`: "An error that quotes a
  refused value" has been fixed several times. Decision: the app's reader helper reports by fields
  only (with app2).
- app2 (duplication, medium, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/items.py:44`: "Read a strict model from a file and map
  its error" is re-implemented about 12 times, each with its own error class, message shape and
  chain handling.
- app3 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run_parts.py:52`:
  The scorers' normalized form, normalize_digits(normalize_arabic(text)), is written out three times
  in the app: run_parts.canonical (window words), scorecard.normalize_text (reference words) and
  matcher.normalize (the verdict). Decision: with lib0.
- app4 (duplication, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/recorder_load.py:39`: Whether a text is a models.Name
  is checked in about six places, with three different messages, none of which states the whole rule
  (a first letter or digit, at most 128 characters).
- app5 (duplication, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/golden.py:290`: `--audio ROOT=FOLDER` is parsed by
  three different functions, and the "each root once" check is repeated in each command.
- app6 (duplication, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run_parts.py:175`: The
  golden set's folder and file names are defined in items.py (EVALS, GOLDEN_DIR, MANIFESTS_DIR,
  SPLIT_FILE, SPELLING_FILE, SCRIPT_FILE) but restated as literals elsewhere.
- app7 (bug, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/run.py:375`: `poe eval` calls `_settings(args)` before
  `configure_logging`, so a refusal raised while loading settings (a bad --base-url or
  --tracing-endpoint, a broken .env) is logged as eval_refused by structlog's unconfigured defaults:
  local time, not UTC ISO, and...
- app8 (bug, medium, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/recorder_load.py:158`: The recorder refuses an --out
  "in the repository, outside its git-ignored var/" by comparing it with _REPO, derived from its own
  source file (EVALS.parents[2]).
- app9 (duplication, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/recorder_state.py:177`: The recorder page's review
  state (`_shown`) re-implements the Q9 rule that items.reviewed and items.unchecked define.
- app10 (drift, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/recorder_load.py:36`: The review file's name is built
  once (takes.review_file) but parsed by two different regexes.
- app11 (duplication, small), `apps/ole5-voice-agent/src/ole5_voice/evals/import_talkover.py:180`:
  "An item holds a product term as a whole word" is written twice.
- app12 (duplication, small), `apps/ole5-voice-agent/src/ole5_voice/evals/import_recordings.py:180`:
  A manifest's committed text (JSON, ensure_ascii off, indent 2, LF at the end) is written by two
  copies of the same expression.
- app13 (duplication, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run_parts.py:138`: "What
  counts as right for a variant" (its reference plus its item's alternatives) is written in two
  places.
- app14 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run.py:57`: run.py
  restates the core's literals instead of deriving them: `--split` choices ("dev", "held-out")
  restate models.Split (recorder.py uses get_args(Device) for the same job), MODELS restates core's
  SttModel, and GROQ_BASE_URL restates...
- app15 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run.py:100`: The
  run policy's defaults (20 requests a minute, 4 attempts, 120 s a variant) are written in
  answerers.Policy and again as run.py's argparse defaults and help texts.
- app16 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/answerers.py:47`:
  Groq's billing is restated in two ways. Decision: with lib1.
- app17 (restated definition, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/items.py:37`: Several app definitions restate a core
  one instead of reusing it: - items.Source = Literal["script", "typed", "none"] restates
  Variant.reference_source's literal, used again in import_talkover.
- app18 (payable debt, small), `apps/ole5-voice-agent/src/ole5_voice/evals/items.py:120`: Two
  production helpers are used only by tests, while production code re-implements them inline.
- app19 (stale doc, small), `apps/ole5-voice-agent/src/ole5_voice/evals/takes.py:63`: load_script's
  docstring says it exists "so the recorder and the import read it alike", but the import (and poe
  golden) read script.toml with items.read_toml(..., Script).
- app20 (duplication, small, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/run_parts.py:285`: Loading a scorecard is done twice:
  - compare.load_scorecard takes a run folder or a file, and reports with EvalDataError and
  first_problem.
- app21 (drift, medium, a change a caller could notice),
  `apps/ole5-voice-agent/src/ole5_voice/evals/history.py:208`: `poe eval-history` and `poe
  eval-compare` write their errors (and history its status line) straight to sys.stderr and
  sys.stdout, while every other command logs through get_logger.
- app22 (stale doc, small), `apps/ole5-voice-agent/src/ole5_voice/evals/run.py:13`: Code docstrings
  and comments still name plan 002's internal Tracks and Block 0, which mean nothing outside the
  completed plan, and some describe the build order rather than the code.
- app23 (stale doc, small), `tests/ole5_voice/evals/test_recorder_security.py:70`: The page's
  no-reference check is described as interim, "the golden set's rule, until Track D's test reads
  every file".
- app24 (stale doc, small), `apps/ole5-voice-agent/src/ole5_voice/evals/recorder_state.py:3`: The
  module docstring says each allow-listed file is sent only when its bytes "match the SHA-256
  recorded for them", but a reply has no recorded hash.
- app25 (stale doc, small), `apps/ole5-voice-agent/src/ole5_voice/__init__.py:1`: The app package's
  docstring says what it adds is "the talker's prompt, its tools, the knowledge base, and the ticket
  system", none of which exists yet.
- app26 (payable debt, small), `tests/ole5_voice/evals/recorder_support.py:190`: Slow tests for no
  reason.
- app27 (duplication, medium), `tests/ole5_voice/evals/test_run_parts.py:36`: Shared run-test
  helpers live inside test modules that other test files import, and small fixtures are copied per
  file: - World, FakeClock, make_world, golden_set, _parts and WHEN are imported from
  test_run_parts.py by test_answerers, test_run,...
- app28 (payable debt, small), `tests/ole5_voice/evals/test_items.py:1`: test_items.py is at the
  400-line cap (ARCH-SIZE), so the next test added fails the gate.
- app29 (payable debt, medium), `apps/ole5-voice-agent/src/ole5_voice/evals/compare.py:1`: Size
  watch.
- app30 (payable debt, small), `tests/ole5_voice/evals/test_no_item_in_source.py:30`: TD-017 can be
  paid now.
- deb1 (payable debt, small), `tests/ole5_voice/evals/test_no_item_in_source.py:29`: TD-017 is still
  true and payable now: the test folds text with its own copy of the library normalizer. Decision:
  with app30.
- deb16 (payable debt, medium), `apps/ole5-voice-agent/src/ole5_voice/evals/compare.py:181`: Only
  some of the modules near the 400-line cap are tracked, and the ones that are not block planned
  work. Decision: with app29.
- deb23 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/answerers.py:47`:
  The app restates the library's Groq billing minimum. Decision: with lib1.
- deb24 (restated definition, small), `apps/ole5-voice-agent/src/ole5_voice/evals/matcher.py:115`:
  The app's matcher.normalize rebuilds the library's scored_form (normalize_digits after
  normalize_arabic), because scored_form is not public. Decision: with lib0.

**Block H: the harness (`scripts/`, `tests/harness/`, `harness.toml`), the thresholds and the new checks** (38)

- har0 (threshold, small, a change a caller could notice), `harness.toml:198`: [gc] min_tokens = 35
  hides every real copy.
- har1 (threshold, small, a change a caller could notice), `harness.toml:206`: [gc] hooks lacks the
  framework hooks behind all 4 'unreferenced' entries.
- har2 (threshold, small, a change a caller could notice), `harness.toml:204`: [gc] path_ignored
  lacks the sibling prototype repo and the installed libraries.
- har3 (threshold, small, a change a caller could notice), `harness.toml:202`: [gc] path_bases lacks
  the app's member folder, so the app's data paths do not resolve.
- har6 (threshold, small, a change a caller could notice), `harness.toml:209`: foreign_names lacks
  the other libraries' names and the non-code words.
- har8 (threshold, small, a change a caller could notice), `scripts/gc_due.py:167`: The commit count
  includes merge commits, and, before the first round, the first commit itself.
- har9 (threshold, small), `harness.toml:199`: [gc] size_watch = 300 is not noise.
- har10 (restated definition, small, a change a caller could notice), `scripts/gc_report.py:195`:
  gc_report hard-codes which docs are history ('/completed/', '/generated/', 'decisions.md') instead
  of reading [docs] historical.
- har11 (duplication, small), `scripts/gc_report.py:230`: gc_report builds its doc set and its
  source map in place.
- har12 (duplication, small, a change a caller could notice), `scripts/gc_report.py:265`: Three
  commands handle a broken harness.toml with their own copy of the same code, and differently from
  the checks' run_check.
- har13 (duplication, small), `scripts/harness_config.py:257`: The package-name check and its
  message are written twice, for [package] and for [[apps]].
- har14 (restated definition, medium, a change a caller could notice), `scripts/doc_refs.py:98`: The
  register formats (TD rows, GP rows, decision headings, invariants) are parsed in two modules with
  separate regexes and separate section logic.
- har15 (duplication, small), `scripts/check_docs.py:57`: Code-fence detection is written twice: the
  regex and the toggle loop.
- har16 (restated definition, small), `scripts/gc_due.py:32`: gc_due re-parses the plan Status line
  and the round's file name with its own regexes, while doc_plans defines and enforces that shape so
  that 'poe gc reads it'.
- har17 (restated definition, small), `scripts/gc_due.py:36`: The quality.md grade table is written
  by quality.render and read by gc_due's own regex, with no test linking the two.
- har18 (restated definition, small, a change a caller could notice),
  `scripts/check_architecture.py:229`: ARCH-ENV's and ARCH-PRINT's FIX texts hard-code what
  harness.toml already says, and say it again with different wording.
- har19 (restated definition, small), `scripts/check_architecture.py:319`: Two HARNESS-CONFIG
  violations are built with literal strings instead of the constants harness_toml defines for them.
- har20 (bug, small, a change a caller could notice), `scripts/gc_report.py:142`: Async defs are
  missed twice: unused async methods are never reported, and async dunders count as duplication.
- har21 (bug, small, a change a caller could notice), `scripts/gc_report.py:39`: The path regex
  never sees .js/.html/.jsonl/.yaml files or dot folders, so stale links to them go unreported.
- har23 (stale doc, small), `docs/harness/golden-principles.md:12`: No golden principle names
  ARCH-PUBLIC, ARCH-FACADE or ARCH-WORDS, though CLAUDE.md's first non-negotiable rests on them.
- har24 (stale doc, small), `docs/harness/garbage-collection.md:31`: The descriptions of the
  report's sections in step 1 and in gc_report's docstring no longer match the code.
- har25 (recurring mistake, small), `docs/plans/README.md:10`: Modules are split only when ARCH-SIZE
  fails or is about to, and each split lands just under 400.
- har26 (payable debt, small), `scripts/harness_config.py:254`: TD-006 (harness_config.py at 388 of
  400) is accurate and payable now.
- har27 (payable debt, medium, a change a caller could notice), `scripts/check_docs.py:158`: TD-024
  (DOC-SAMPLE) is payable.
- har28 (payable debt, small, a change a caller could notice), `harness.toml:170`: TD-018 is a
  one-line change in this area.
- har29 (threshold, small, a change a caller could notice), `scripts/quality.py:136`: `poe quality`
  grades the library's layers and scripts/ but never the apps.
- doc1 (bug, small, a change a caller could notice), `scripts/gc_due.py:33,78-89`: The gc signal
  counts a milestone as completed whenever any completed plan's Status line names it. Decision: the
  milestone signal in gc_due.
- doc10 (stale doc, medium, a change a caller could notice),
  `docs/harness/garbage-collection.md:38`: The round's read and the grades still have the kit's
  one-package view, from before D-013's apps. Decision: with har29.
- doc16 (payable debt, medium), `docs/plans/tech-debt.md:38`: The guide's index says 'code samples
  on these pages are taken from tested files, so a page never shows code that does not run', but
  only review enforces that (TD-024). Decision: with har27.
- doc18 (threshold, small, a change a caller could notice), `harness.toml:200-211`: These `[gc]`
  values are too narrow for this repository's docs, which produces the doc-side noise above.
  Decision: with the calibration.
- doc19 (restated definition, small), `scripts/gc_report.py:196,215-216`: gc_report hard-codes which
  docs count as history ('/completed/', '/generated/', decisions.md) instead of reading `[docs]
  historical` from harness.toml, which is the definition DOC-REF and DOC-MILESTONE use
  (scripts/doc_refs.py:55,180). Decision: with har10.
- deb0 (payable debt, small), `scripts/harness_config.py:254`: TD-006 is still true (388 of 400
  lines) and payable now. Decision: with har26.
- deb2 (payable debt, small), `harness.toml:170`: TD-018 is still true and payable now with one
  line. Decision: with har28.
- deb3 (payable debt, small), `scripts/check_docs.py:1`: TD-024 (no DOC-SAMPLE rule) is still true
  and cheap. Decision: with har27.
- deb6 (recurring mistake, medium), `apps/ole5-voice-agent/pyproject.toml:6`: Code keeps importing a
  library it does not declare, relying on another package to bring it. Decision: the check
  (ARCH-DEPS) and the two missing declarations.
- deb18 (bug, small, a change a caller could notice), `scripts/gc_due.py:78`: poe gc reports
  'milestones completed: M0 (plan 001)' while the roadmap says M0 is in progress. Decision: with
  doc1.
- deb20 (threshold, small, a change a caller could notice), `scripts/quality.py:141`: poe quality
  grades only the library's layers and scripts/. Decision: with har29.
- deb21 (threshold, small, a change a caller could notice), `scripts/quality.py:106`: Two artefacts
  of the size and docstring signals. Decision: with har29.

**Block D, last: the living docs and the debt list** (30)

- lib2 (recurring mistake, medium), `docs/harness/golden-principles.md:31`: Copying a core rule
  instead of reusing it has happened at least three times: GroqSTT's copied _KEY and _https drifted
  (they missed port 0 and spaces) and were removed in the review of the merged tracks; TD-017's
  copied letter folding in... Decision: GP-20's enforcement names the tests that tie the copies
  (Block A).
- har22 (stale doc, small), `docs/harness/quality.md:30`: quality.md promises a table that the
  scaffold never filled. Decision: filled at the close after `poe quality`.
- doc4 (drift, small), `docs/guide/README.md:40`: `docs/guide/contract.md` is promised for M0
  ('fixed then', D-018 answer 23) by the guide's index, the design's documentation plan and the
  design's 16.1 M0 row.
- doc5 (stale doc, small), `docs/SECURITY.md:14-21`: The trust-boundary table lists only the
  product's runtime boundaries.
- doc6 (stale doc, small), `docs/SECURITY.md:61-65`: Invariant 5 is still in the future tense
  ('Enforced, once the first secret setting exists, by a test ...
- doc7 (stale doc, small), `docs/design/package-design.md:3, :1470-1471, :1487, :1649-1661,
  :778-795`: Statements about what is built and decided, made before M1, still stand: - The Status
  line says 'Nothing in it is built yet'.
- doc9 (duplication, small), `.env.example:18-21`: The provider variables to leave unset are listed
  in three places, and the lists differ.
- doc11 (stale doc, small), `CLAUDE.md:72-78`: The code map lists what domain/ will hold (the yes
  rule, interruptions) and leaves out what it holds now: the scorers' pure parts (recall.py,
  scoring.py, sign_test.py), Arabic and digit normalization, and the speech-to-text port.
- doc12 (recurring mistake, small), `docs/harness/golden-principles.md:27`: Hand-written counts and
  numbers in plans and docs were wrong again and again in M1.
- doc14 (recurring mistake, small, a change a caller could notice),
  `docs/harness/golden-principles.md:31`: Boundary code restating core's constraints instead of
  reusing them has now happened twice. Decision: with lib2.
- doc15 (recurring mistake, medium), `docs/guide/evaluation.md:39-49`: The guide's helper table
  restates each scorer's docstring in prose, and the copy drifted from the code in three review
  rounds.
- doc20 (stale doc, small), `docs/harness/quality.md:30`: 'Not measured yet: the first `uv run poe
  quality` after the scaffold fills it.' The scaffold era is long past and M1 closed without a
  recorded grade, so gc_due has nothing to compare against ('layers graded below quality.md: none').
  Decision: with har22.
- doc21 (stale doc, small), `docs/design/evaluation.md:37-41`: Two calls this doc leaves open were
  settled in plan 002: 'which wins is the owner's call before the first run' (the owner ruled 'the
  item wins', Q10, commit 362081e), and 'What serves as the independent check for each is fixed in
  the first measurement...
- doc22 (drift, small), `WORKING-RULES.md:63-64 against docs/plans/README.md:9`: WORKING-RULES says
  'One commit belongs to one plan, named in its subject (`Plan NNN: <what>`)', while the plans
  README allows a small change with no plan file, 'described in the commit'.
- doc23 (stale doc, small), `WORKING-RULES.md:172-175`: 'Seeing it run' says to add
  `.claude/launch.json` 'when the first such surface exists, with no machine-specific paths in it
  (or keep it uncommitted)'.
- doc24 (stale doc, small), `WORKING-RULES.md:190-192`: GP-16: 'files under %TEMP% ...
- doc25 (stale doc, small), `docs/plans/README.md:43-44`: The DOC-REF line lists "plan NNN", D-NNN,
  TD-NNN and GP-NN, but DOC-REF also checks 'invariant N'.
- doc26 (stale doc, small), `docs/plans/roadmap.md:254-272`: The Decided list stops at D-018 and the
  approvals of 2026-11-01.
- doc27 (drift, small), `docs/guide/README.md:48`: One future generated page goes by three paths:
  `settings.md` in the guide's index, `reference/settings.md` in the design's documentation plan,
  and `docs/reference/settings.md` in the design's 7.7, which would sit outside docs/guide/.
- doc28 (stale doc, small), `docs/harness/garbage-collection.md:32`: Step 1 says the report lists
  'unreferenced top-level definitions', but gc_report also lists methods. Decision: with har24.
- doc29 (recurring mistake, small), `docs/plans/roadmap.md:120,149,197`: Prose lines past the
  100-column wrap the docs keep were fixed once by hand (Track H: 'both paragraphs rewrapped to 100
  columns') and recur.
- deb8 (duplication, small), `docs/plans/tech-debt.md:25`: TD-009 and TD-028 are one debt and should
  be one row: an Arabic letter written onto a Latin or digit token (الword, بالPDF; و2026, ب48)
  hides that token from the recall scorers, and one fix covers both.
- deb9 (duplication, small), `docs/plans/tech-debt.md:26`: TD-010 (short and dialect digit names)
  and TD-031 (compound number words) are the same gap in the same function.
- deb10 (duplication, small), `docs/plans/tech-debt.md:37`: TD-023 is a consequence of TD-001: by
  its own words, the row is removed once CI runs the suite.
- deb11 (drift, small), `docs/plans/tech-debt.md:20`: TD-004 and TD-015 must be paid together but do
  not cite each other.
- deb13 (drift, small), `.env.example:19`: The repository has two lists of SDK variables to leave
  unset, and they disagree. Decision: with doc9.
- deb14 (stale doc, small), `docs/plans/tech-debt.md:27`: Several rows' triggers now fall in M2,
  whose roadmap entry is concrete, but the rows still name vague future plans.
- deb15 (stale doc, small), `docs/plans/tech-debt.md:35`: TD-021's fix begins 'After the runs', but
  the runs are done.
- deb19 (stale doc, small), `docs/harness/quality.md:30`: quality.md's grade table has never been
  filled. Decision: with har22, filled at the close after `poe quality`.
- deb22 (recurring mistake, medium), `docs/plans/tech-debt.md:19`: The environment variables the
  SDKs read were found piece by piece across reviews: rows were narrowed or corrected after merge 3
  times.

**Left for M2's plan** (4)

- lib14 (drift, small, a change a caller could notice),
  `packages/t2-agentic-voice/src/t2_agentic_voice/api/status.py:31-32`: The rule 'production never
  runs with DEBUG logs' is checked only when status() is called (the app's health route), not when
  the settings load. Decision: a load-time refusal is a behavior change for the composition root M2
  builds.
- lib16 (restated definition, medium),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py:38`: The library defines the
  setting that picks a speech-to-text provider (stt.provider), but only the app maps it to an
  adapter, `{"groq": GroqSTT.from_settings}`. Decision: the provider factory belongs to M2's
  composition root.
- doc0 (drift, large, a change a caller could notice), `docs/design/package-design.md:211`: The
  logging contract the owner fixed at M0 (D-017, D-018 Q23) says library logs go to the
  `t2_agentic_voice` logger with a NullHandler, 'nothing appears until the app configures logging',
  and the library never adds a root handler. Decision: the owner's answer, 2026-11-02: M2 builds the
  design's logging contract; a debt row records the gap now (Block D).
- doc2 (drift, small), `docs/plans/roadmap.md:101-103`: Three sources disagree on who owns Pipecat's
  loguru and what the policy is. Decision: who owns Pipecat's loguru is M2's to settle with that
  contract.

**Left for M4's plan (the owner's answer)** (1)

- doc3 (drift, small), `ARCHITECTURE.md:59,89`: The living docs and the owner rules still describe
  the library's adapters layer as holding the knowledge base and ticket system adapters, and give
  the library's `adapters` layer the `qdrant_client` module. Decision: the owner's answer: leave for
  M4.

**Noise: what the report flagged that is not a problem, which Block H's calibration silences** (11)

- lib20 (candidate noise, small),
  `packages/t2-agentic-voice/src/t2_agentic_voice/core/tracing_export.py:69`: Reported as
  unreferenced, but it is SpanProcessor's hook, which the SDK calls on every span.
- lib21 (candidate noise, small), `tests/t2_agentic_voice/core/test_errors.py:78,91`: Real, by the
  repository's rule: two `# noqa: S301` with no reason, where scripts/ and the app write '# noqa:
  S603 - git, with arguments built here'.
- lib22 (candidate noise, small), `tests/t2_agentic_voice/adapters/test_groq_stt.py:4-5`: The
  unresolved paths in the library's tests are the prototype's files (Ole5-chatbot/..., beside the
  repository, read as specs under D-010).
- app31 (candidate noise, small), `apps/ole5-voice-agent/src/ole5_voice/evals/recorder.py:85`: The
  gc report lists recorder.py's do_GET (:85), do_POST (:88) and log_message (:168) as unreferenced
  definitions.
- app32 (candidate noise, small), `apps/ole5-voice-agent/src/ole5_voice/evals/matcher.py:4`: All of
  the gc report's unresolved paths in this area are noise.
- har4 (candidate noise, small, a change a caller could notice), `scripts/gc_report.py:188`:
  unresolved_paths reads every line of tests/, so made-up fixture names in string literals are
  reported (19 of the 50).
- har5 (candidate noise, small), `docs/design/package-design.md:235`: Classification of the 50
  unresolved paths: 49 noise or planned, 1 real.
- har7 (candidate noise, small, a change a caller could notice), `scripts/gc_report.py:208`:
  Classification of the 307 'names the code does not have': nearly all are planned API in the
  forward-looking design.
- har30 (candidate noise, small), `tests/t2_agentic_voice/core/test_errors.py:78`: The report's two
  'noqa without a reason' entries are real: missing reasons, not detector noise.
- doc17 (candidate noise, small), `gc-report.md 'Names in docs'`: All the report's doc-side
  candidates are noise, and none is new drift: - 286 names in package-design.md: the planned API of
  M2 to M7, such as VoiceAgent, KnowledgeBase and TextCall.
- deb25 (candidate noise, small), `docs/plans/tech-debt.md:19`: The gc report's candidates in the
  tracker are all noise: 8 unresolved paths and 18 names the code lacks.

**Considered and kept** (98), so the next round need not redo them

- lib: adapters/groq_stt.py at 330 lines (size watch): one cohesive adapter (request, answer
  parsing, failure mapping, the constructor's checks).
- lib: tests/t2_agentic_voice/core/test_config.py (347) and core/test_tracing_export.py (304):
  single-subject files below the cap; keep.
- lib: App answerers._by_length vs groq_stt._by_length: look-alike, the inputs differ.
- lib: App audio.write_wav vs groq_stt._wav vs test_baselines.py:28-34: thin wrappers over the
  stdlib's wave with different inputs (bytes and a rate vs an AudioClip, which already checks
  evenness); the baseline test's copy is an independent oracle.
- lib: 'str instead of a sequence' guards in term_recall (scoring.py:41), scorers._pairs
  (scorers.py:21), Redactor (redaction.py:21) and the app's matcher.is_right: same shape, different
  inputs and messages; keep.
- lib: tests/harness/test_isolation.py:20-21 and test_import_isolation.py:17 restating the dropped
  prefixes: independent oracles of conftest, so they must not import its list.
- lib: Literal setting names in tests (test_groq_stt.py:38 SETTING, test_groq_stt_checks REFUSED,
  test_config._keys' naming rule): oracle copies of the setting-name rule; keep.
- lib: test_baselines.py:27's clip formula vs test_groq_stt.py:40's CLIP: a mismatch fails loudly on
  the fixture's sha256, so keep.
- lib: ExportSession.request and prepare_request both setting EXPORT_HEADERS: both are needed.
- lib: tracing_export.py:145 `# type: ignore[override]`: requests' Session.request has many
  positional parameters, and the override takes **kwargs because the exporter passes headers by
  keyword.
- lib: test_groq_stt.py's `imported` fixture (1.84 s setup, the only library entry among the 20
  slowest): four child processes started in parallel, needed to see what importing groq does to
  logging.
- lib: test_a_cancel_ends_the_request_at_once (`took < 0.05`): the design's 6.1 number; may flake on
  a loaded CI machine.
- lib: conftest's PREFIX read from Settings.model_config rather than imported from core.config: it
  reads the definition, not a copy; keep.
- lib: type(error).__name__ (config.py:129, groq_stt.py:265) vs __qualname__ (tracing): identical
  for the top-level exception classes involved; tracing keeps qualname for nested ones.
- lib: SpanQueue copying its module constants into instance attributes: lets tests monkeypatch the
  constants before building one; keep.
- lib: SpanQueue shutdown give-up race: an in-flight batch is not counted at shutdown but is counted
  if its export fails, which matches the dropped_spans docstring.
- lib: Correctness checks with no defect found: id_recall's readings search, normalize_digits' run
  joining, sign_test's exact integers, and silence_output's 'empty exactly when the scored form is'
  (normalize_digits never empties or fills a text).
- lib: Three builders of test Settings (conftest's settings fixture, test_groq_stt.settings(),
  tracing_support.settings_with()): different inputs (plain, a Groq key, a tracing group); keep, and
  rename only the shadowing one (in the drift finding).
- lib: Library debt rows TD-003, TD-004, TD-005, TD-008, TD-009, TD-010, TD-011, TD-012, TD-014,
  TD-015, TD-020, TD-025, TD-028, TD-031 and TD-032 are not payable now: each waits for a
  measurement, an SDK option, a second adapter, the composition root or the owner.
- app: audio.write_wav (Python) and recorder.js's wavFile (JS) write the same 44-byte header in two
  languages.
- app: items.EVALS against run_parts.DATA: their inputs differ.
- app: worktree.check_out (it asks git) against recorder_load's path-based --out guard: the recorder
  needs no git or worktree.
- app: The link checks differ on purpose.
- app: unchecked() is the shared rule for a checked variant, and golden.validate and
  run_parts.load_plan both call it.
- app: The test helpers _card and _result in test_compare, test_scorecard, test_held_out_groups and
  test_run_parts look alike but take different inputs: some build a Scorecard directly, others go
  through write_scorecard with fakes.
- app: fakes.FakeMatcher is deliberately simpler than GuideMatcher (no joined form), and
  FakeSpeechToText's max(10.0, ...) mimics Groq's billing.
- app: history's _percent, _cell and _row against compare's _number, _yes and _compared format two
  different reports in their registered formats (accuracy as a percentage with one decimal; rates to
  4 decimals).
- app: The `--evals` argument is repeated in golden, split, import_recordings and import_talkover:
  one line each, with the same default and help.
- app: golden, split, the imports and the recorder call configure_logging() with its defaults
  instead of the settings'.
- app: run._seconds restates SttSettings.timeout_s's constraint (above 0, finite) at the argparse
  boundary to give a message naming the flag; Settings checks it again.
- app: runs.Answer and SegmentAnswer restate ports.Transcript's fields: they are the scorecard's
  stored record, with their own life, and are read back strictly.
- app: TD-019 (answerers.py at 378 lines): its trigger, the commit that adds the next answerer,
  still holds.
- app: The commands' exit codes differ: golden, split, compare and history return 1; run and record
  return 2 when refused before acting.
- app: compare's Markdown report does not escape its cells, unlike history's page.
- app: golden._frozen reuses the name `found` inside a generator: cosmetic and harmless.
- app: items.load_manifests does not refuse a missing folder, as load_items does.
- app: examples/minimal reports only status(), and its docstring describes the target example (one
  tool, a short prompt) that grows with the library.
- app: recorder_state.add_review returns _shown(entry) outside the lock.
- har: arch_public._AppChecker.visit_Import/visit_ImportFrom vs check_architecture._ModuleChecker
  (31-token run at arch_public.py:33 = check_architecture.py:86): look-alike, but the inputs differ.
- har: harness_toml.Table.integer vs Table.number (27-token run at :86 = :93): different types,
  minimums and messages.
- har: quality.COUNTED vs gc_report.SUPPRESSIONS: COUNTED leaves out `# fmt: skip` on purpose, since
  it marks data tables (quality.py docstring).
- har: Python file listings in four places (gc_report.python_files, module_rules.check_support,
  doc_refs.code_files, check_docs.check_line_endings): the roots and exemptions differ (code_exempt
  applies to DOC-REF/DOC-MILESTONE only; DOC-EOL reads every file).
- har: gc_report._FIXTURE_FILES ('tests/harness/') vs [docs] code_exempt (two harness test files):
  they cover different things (paths vs citations) with different scopes.
- har: DOC-REF/DOC-MILESTONE read fenced blocks, while DOC-REGISTER skips them.
- har: ole5_voice/evals/runs.py:47 copies DOC-PLACEHOLDER's pattern, because an app may not import
  scripts/ (plan 002 decision log).
- har: check_docs.check_line_endings reads only root config files, not the member pyproject.toml
  files, evals data or JS.
- har:
  tests/harness/test_isolation.py::test_a_shell_that_sets_this_projects_variables_changes_no_test
  (3.73 s): starts a child pytest with a hostile shell on purpose (GP-15).
- har: tests/harness/test_commands.py::test_each_check_runs_as_a_command_and_says_how_it_went (1.62
  s): checks `python -m` wiring and exit codes as a caller meets them.
- har: tests/harness/test_gc_report.py::test_the_report_runs_on_this_repository (1.13 s) and
  test_gc_due's git tests (1.05 s): the only tests of the report on real input and of git behavior.
- har: Test constants that restate support.SYNTHETIC (test_quality WEIGHTS/LAYERS, test_check_docs
  SECTIONS, test_gc_due DUE_AFTER): they fail loudly if SYNTHETIC changes.
- har: size_watch 300 (see thresholds): measured against module growth, not noise.
- har: The names check's substring match (`last not in code` over all code text, comments included):
  cheap, and accepted.
- har: The Ole5-chatbot provenance citations themselves (D-010): keep the citations, and ignore
  their prefix in the report.
- har: The six planned paths in the design (docs/reference/settings.md, reference/settings.md,
  reference/api.md, cookbook/*.md, testing/audio.py): planned for M2 and later.
- har: arch_facade.py:8 and arch_words.py:11 cite D-020, while harness.toml:26 cites D-021 for
  facades.
- har: check_architecture.py at 343 lines: there is room for M2's ARCH-BAN only as a helper module,
  as ARCH-FACADE and ARCH-WORDS were done, never inline.
- har: unknown_names reads only root *.md and docs/**: no app or example README exists today.
- har: unresolved_paths uses `.exists()` rather than check_docs.exists_exact_case, so a path with
  the wrong case resolves on Windows but not on Linux.
- doc: package-design.md's 286 planned-API names and 10 planned paths: the design describes M2 to M7
  by milestone label, so its future names are intended.
- doc: The roadmap's M0 row 'in progress' and the design's 16.1 'M0 (in progress)' are correct: plan
  000 waits on CI (TD-001) and on the owner's review of WORKING-RULES.
- doc: SECURITY.md invariants 1-4 and 6-8 in the future tense, and ARCHITECTURE.md's ticket-specific
  wording for domain and actions: the code they protect lands in M2 to M5.
- doc: Every M1 number in docs/guide/evaluation.md and the roadmap traces to
  apps/ole5-voice-agent/evals/history.jsonl or plan 002: - R1 0.429, English 0.847, Saudi 0.370, MSA
  0.256, mixed 0.050; - 2,437.5 s and $0.0752; the cap 4.9996; max_rpm 10; - H1 0.387 and...
- doc: The guide's helper-table signatures match the evals and languages facades
  (inspect.signature), and both guide samples match their source tests today.
- doc: The roadmap's prototype numbers (about 1 s after «وقف», 400 requests a minute, ragent2 at
  20-45 s) cite VOICE_LOG.md with dates.
- doc: design/evaluation.md's method sections: every M1-specific claim matches the code.
- doc: The held-out pooling rule stated both in design/evaluation.md and in the guide: method
  against application.
- doc: The commands described in CLAUDE.md, in evaluation.md's 'Where the commands live' and in the
  guide's 'The commands': a one-line map, the method's location and a teammate's how-to, for
  different readers.
- doc: Rules duplicated between WORKING-RULES.md and the plans README (claiming numbers, review by
  another agent, worktrees): the first says how the agent works, the second the format.
- doc: `phoenix` in core's owners row, although D-023 says Phoenix is never imported: removing the
  row would let every layer import it.
- doc: GP-03's event names and GP-12's deterministic test data stay review-only.
- doc: GP-18 stays review-only: no default has moved yet (D-025 kept large-v3).
- doc: GP-22's 'no Pipecat provider service' part stays review-only until ARCH-BAN lands with the
  plan that installs Pipecat (M2; the design's 12.4).
- doc: GP-10, GP-21 and GP-01's 'reason in a decision' stay as judgment calls; there were no
  incidents in M1.
- doc: `python -m ole5_voice.evals.import_talkover` is not in the living docs: it is a one-off
  import of the prototype's set, recorded in plan 002, which needs no guide entry.
- doc: The design's 7.6 defaults that the M1 code does not follow yet (a required `env`,
  `groq.timeout_s`, `from_env(prefix=...)` from D-018 Q4): these are M2's work (`VoiceSettings`),
  not stale text.
- doc: PRINCIPLES.md: generic principles with no claim about the code to check.
- doc: docs/generated/README.md: accurate.
- doc: Library-code items seen on the way, outside this area: the docstrings of domain/__init__.py
  and adapters/__init__.py (they repeat the code-map drift reported above), config.py's comment on
  `stt.model` citing 'plan 002's registered baseline' rather than...
- deb: TD-001 stays: `git remote -v` is empty, and only the owner can create a remote.
- deb: TD-003 stays: groq 1.7.0 reads GROQ_LOG at _logs.py:17 on import (__init__.py:79).
- deb: TD-005 stays: lines 1278, 25, 1289-1300 and 680 verified in 1.45.2.
- deb: TD-008 stays: reproduced (e+U+0301 gives 'cafe', é is kept, U+FEFB is kept, ZWNJ gives WER
  2.0 and CER 0.0).
- deb: TD-012 stays, with today's re-measure noted.
- deb: TD-014 stays: SpanQueue starts its worker once (tracing_export.py:66-67) and has no
  register_at_fork.
- deb: TD-015 stays: TracingSettings has only endpoint, project, include_transcripts and redact.
- deb: TD-020 stays: answerers.py:192 still looks up aclose with getattr, and the port has only
  transcribe.
- deb: TD-021 stays: owner-blocked.
- deb: TD-022 stays: recorder.js has no automated test.
- deb: TD-026 stays: compare.py:185-195 refuses only on commit, digest or split, and _header lists
  the other settings.
- deb: TD-029 stays: the owner's rule, registered before the next held-out run.
- deb: TD-031 stays: the roadmap's M2 line cites it, and it should absorb TD-010.
- deb: TD-032 stays: the roadmap's M3 line cites it, and d = 0 and c = 6 trace to
  decisions.md:585-588.
- deb: Look-alike kept: the app's _by_length (answerers.py:332) and the library's (groq_stt.py:241)
  take different inputs.
- deb: Look-alike kept: the app's git helper in worktree.py:41 and gc_due.git (scripts/gc_due.py:52)
  live in packages that cannot import each other (an app never imports scripts/).
- deb: Kept: quality.py's suppression count.
- deb: Kept: tests/conftest.py does not drop proxy variables, and no test request leaves through a
  shell proxy.
- deb: Kept: the guide's two code samples match their sources today (probe), and the guide's
  spelling_issues and id_recall rows state TD-025's and TD-028's limits accurately.
- deb: Kept: every row's cited SDK file and line number is accurate for the installed versions, so
  no row needs its evidence corrected.

## Progress log

- 2026-11-02: The owner asked for the round before M2 ("yes do the cleaning round before M2"),
  since `uv run poe gc` said one was due: M0 (plan 001) and M1 (plan 002) completed, and 100
  commits landed with no round yet (40 make one due). The measurement, in the linked worktree
  `gc-round-1` at main 5f1c60a: no duplicate run of 35 or more tokens outside `tests/`; 4
  unreferenced definitions; 27 modules above the 300-line watch; 50 unresolved paths and 307
  names the docs cite that the code does not have, which the read sorts into real and noise. No
  test printed a warning; the slowest test (3.7 s) starts a child process on purpose.
- 2026-11-02: Step 2, the read, by five agents, read only (the library; the app; the harness with
  the thresholds; the living docs; the debt list with the quality grades): 143 findings and 98
  things considered and kept. Step 3: the inventory below, each finding with its block or the
  plan it is left for, and the owner's answers to the four calls it raised (the decision log).
  Next: Block R, then Blocks L, A and H in parallel, then Block D.
- 2026-11-02: Block R, the rename (`Plan 004: Block R, AppError becomes T2VoiceError`): the base
  error is `T2VoiceError` in `core/errors.py` and every use (the app's `compare.py`, `run.py` and
  `scorecard.py`, `harness.toml`'s FIX text, ARCHITECTURE.md, CLAUDE.md, GP-07); the package root
  exports it, and `t2_agentic_voice.AppError` still works with a `DeprecationWarning` until the
  next minor release (the design's 5.4), pinned by a new test in `test_errors.py`. D-026 records
  it, and the debt row is removed. `uv run --offline poe check` passes: 1217 tests and 1 skipped,
  100% coverage (3604 statements), mypy strict on 144 files, arch and docs clean.

## Decision log

- 2026-11-02: The owner's answers to the four calls the read raised ("The owner's decisions"
  is not a section of a maintenance plan, so they are quoted here): the library's logging, which
  does not meet the accepted design's contract (the design's 3.3 and 10.2): "Fix it in M2
  (Recommended)", with a debt row now; `AppError` against the design's `T2VoiceError` (the debt row on it, paid by D-026):
  "Rename it now (Recommended)", keeping `AppError` as a deprecated alias; the library values the
  app copies because no facade exports them: "Tie them with tests (Recommended)", the public API
  unchanged; the architecture docs and `harness.toml` that still give the library the knowledge
  base and ticket adapters, which D-017 placed in the app: "Leave for M4".
- 2026-11-02: This round takes 004, not the next free number: M2's execution plan, being drafted
  on its own branch for the owner's approval, already holds 003 there and keeps it. The agent's
  choice.
