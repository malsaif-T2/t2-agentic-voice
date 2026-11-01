# 002 · The measurement first: the owner's voice as a golden set

Status: active · Milestone: M1 · Started: 2026-11-01

## Goal

Build the measurement before the features it measures
([evaluation.md](../../design/evaluation.md), D-011): a golden set of the owner's voice; the
commands that validate it (`golden`), run an answerer over it (`eval`) and judge one run
against another (`eval-compare`); and the library pieces those commands stand on, built as a
teammate would use them: the speech-to-text port and its Groq Whisper adapter, the canonical
Arabic normalizer and digit normalization, the scorers, and `core`'s tracing helpers
([roadmap](../roadmap.md), M1). The plan ends with the first registered measurement: a
baseline scorecard for Groq Whisper large-v3 and turbo on the owner's voice, by language and by
device, with the noise of two identical runs recorded as a decision, so that every later change
to speech-to-text, end of turn and interruptions (M2, M3) is judged against numbers. Every
number describes one speaker, the owner, and is never reported as Saudi speakers in general
(D-006).

## Acceptance criteria

**The golden set**

- [ ] Its items are committed under `apps/ole5-voice-agent/evals/`: the 124 talk-over segments
  recorded for the prototype, read in place from `voice-lab/recordings/talkover/` (D-010), one
  item per scripted phrase with its takes as variants; and the owner's new recordings on the
  laptop's speakers and microphone, a wired headset and a Bluetooth headset. Together they
  cover Saudi Arabic, MSA, English, and Arabic with English product terms; stop words, repeat
  requests and listening sounds; requests of several clauses that pause mid-sentence, recorded
  as whole takes with every true turn end labelled; and silence and noise (plus ticket numbers
  and the agent's own echo, if the owner keeps them: Q4).
- [ ] No audio file is in git. Manifests hold each audio file's path under a named root, its
  SHA-256, length, sample rate, device and session; a test fails when an audio file sits under
  `apps/`, `packages/`, `examples/`, `docs/` or `tests/`.
- [ ] References follow Ole5's spelling guide, `apps/ole5-voice-agent/evals/spelling.toml`, each
  ruling with the owner's words and date (Q8); `poe golden` names every reference that breaks it.
  The guide's `docs/guide/evaluation.md` says how a team writes its own and links to Ole5's.
- [ ] `uv run poe golden` validates every item (its reference and its independent check agree;
  with `--audio` roots given, every file's hash and format match its manifest) and freezes the
  expected answers into one JSON file; a changed item shows as a diff of that file.
- [ ] Tests in `tests/ole5_voice/evals/`, inside `poe check`: the `reference` answerer scores
  100% with zero violations; the committed split is fresh (`split --check`); the strata hold
  their registered counts; no item's reference appears in a package's source (evaluation.md,
  "No item in the product"), except an entry of the allow-list file, which starts empty and grows
  only by the owner's ruling; with a self-test that finds pasted text.

**The commands**

- [ ] `uv run poe eval` runs an answerer (`reference`, `groq`) as evaluation.md's "Running"
  says: it refuses the main checkout and a dirty tree; takes every setting and data path on its
  command line and shows them resolved (the Groq base URL included), a secret only as set or not
  set, without printing `.env`; runs a one-item smoke test first; writes per-variant results as
  they finish, with a progress line and a wall-clock limit per variant; waits and asks again when
  Groq turns a request away, and marks a provider failure after the last attempt; and writes its
  scorecard into `--out`, a new folder outside the worktree that git does not track (under the
  main checkout's git-ignored `var/`, or outside the repository). A held-out run writes
  aggregates only, shows only counts in its progress lines, and refuses tracing.
- [ ] `uv run poe eval-compare A B` gives fixed, broken and net per variant, the two-sided sign
  test by item, `--focus`, provider failures left out of both runs and listed, and held-out runs
  compared by aggregates only; it refuses two runs whose recorded commits or data digests differ.
- [ ] Every `poe eval` run appends one line to `apps/ole5-voice-agent/evals/history.jsonl` (LF
  endings), with a copy beside its scorecard; the line reaches the main branch as step 23 says;
  `uv run poe eval-history` renders the file into `docs/generated/eval-history.md`, with a
  freshness test and a row in [docs/generated/README.md](../../generated/README.md).
- [ ] CLAUDE.md's command table lists `golden`, `eval`, `eval-compare`, `eval-history` and
  `record`.

**The library** (the roadmap's *Library* line for M1, and the M1 row of the design's 16.1)

- [ ] `t2_agentic_voice.ports` exports `SpeechToText`, `AudioClip`, `Transcript` and `DataFlow`
  in the shape of the design's 6.1, and the package root exports
  `ProviderError(kind, retryable, retry_after_s)`.
- [ ] `t2_agentic_voice.groq.GroqSTT` transcribes with `whisper-large-v3` or
  `whisper-large-v3-turbo` (the `stt.model` setting). Its tests, against a fake transport, check
  the request's fields against Block 0's baseline, the result's shape, a cancel that stops within
  50 ms and leaves no task behind, each failure as a `ProviderError`, that the key appears in no
  repr, error or log line, and that `GROQ_API_KEY`, `GROQ_BASE_URL` and `GROQ_CUSTOM_HEADERS` in
  the environment change nothing in the request (the design's 7.3: "Other names are never
  read"). No public signature names a `groq` type (the design's 5.3).
- [ ] `t2_agentic_voice.languages` exports `normalize_arabic`, `normalize_digits` (Arabic-Indic,
  Persian and spelled-out digits) and the spelling-guide check, which takes a team's rulings as
  data; each port's prototype source is named in the progress log (D-010).
- [ ] `t2_agentic_voice.evals` exports `wer` and `cer` (after normalization, on jiwer in the
  `testing` layer), `term_recall`, `id_recall`, `silence_output`, and `sign_test`, which matches
  evaluation.md's formula on hand-computed cases.
- [ ] `t2_agentic_voice.tracing` sets up tracing from settings: the team's `TracerProvider` if
  given, otherwise a private one built from `tracing.endpoint`, never installed globally; span
  helpers that take the parent span as an argument; speech-to-text spans carrying audio seconds,
  billed seconds, model and language; the redaction hook on every text attribute; no audio
  exported; an exporter that fails never raises into the caller; every value the OpenTelemetry
  SDK would read from an `OTEL_*` variable passed explicitly, and any it reads regardless listed
  as debt (the decision log). Tests prove that no secret value reaches any exported span, and
  that every secret setting is a `SecretStr` that appears in no repr and no log line
  ([SECURITY.md](../../SECURITY.md), invariant 5).
- [ ] A traced request (run P in the registration) reaches a Phoenix the owner runs locally:
  one trace for its variant, holding the speech-to-text span, with `session.id` set to the
  run's name.
- [ ] `harness.toml` and [ARCHITECTURE.md](../../../ARCHITECTURE.md) agree on a new `testing`
  layer that owns `jiwer`; the facades `ports`, `groq`, `languages`, `evals` and `tracing` are
  listed in `[package] facades` and `public`; ARCH-FACADE and ARCH-WORDS run in `poe arch`, with
  tests in `tests/harness/`.
- [ ] Decision entries record the `testing` layer (amending D-003), ARCH-FACADE and ARCH-WORDS,
  the public facades, and evaluation's split between the library and the app (following D-011),
  as the design's 16.3 lists them; and an entry amends D-002's tracing bullet to plain OTLP
  through the OpenTelemetry SDK (the design's 10.1).
- [ ] The library's settings gain the groups `groq`, `stt` and `tracing` under `T2V_`, nested
  with `__`; `.env.example` lists every key, its test reads the groups, and a `.env` copied from
  it with only the key filled in leaves every other setting at its default.
- [ ] The guide's `docs/guide/evaluation.md` is written and linked from the
  [guide's index](../../guide/README.md).

**The measurement** (the roadmap's *Done when* for M1)

- [ ] The section "The measurement, registered before any result" below was complete, with
  every owner's call settled and dated, before the first run that spends; every departure is a
  `Deviation:` line in the progress log.
- [ ] `poe eval` wrote a baseline scorecard for Groq Whisper (large-v3 and turbo) on the owner's
  voice, by language and by device, labelled one speaker.
- [ ] The noise (the same run twice, for each model) is recorded as a decision and as a
  tech-debt row ("one run is one sample; repeated runs are the lasting fix", evaluation.md).
- [ ] `stt.model`'s default is set by the registered rule (the design's 7.6: "chosen by the M1
  baseline").
- [ ] Whisper is scored on the first 500, 750 and 1000 ms of each registered talk-over clip, and
  every window's transcript is kept in the scorecards, so M3 chooses its window from data.
- [ ] `uv run poe check` passes; the roadmap's M1 row, evaluation.md's paragraph on where the
  commands live, and this plan's logs are up to date.

## Plan

Blocks in the order they depend on each other. Each block is built in its own worktree under
`.claude/worktrees/`, reviewed by an agent that did not write it, fixed, gated with
`uv run poe check`, and merged, with commits named `Plan 002: <what>`. Block 0 is built by one
agent and merged before any track starts; the tracks are built in parallel against Block 0's
interfaces and fakes, reviewed by concern (`## Tracks`), and merged through an integration
branch, `plan-002-integration` ([plans README](../README.md), "Parallel tracks").

**Before Block 0**

1. The owner settles the calls marked "the owner's call before Block 0" (Q1 to Q3 and Q8, in
   the registration below). The agent lists `docs/plans/active/`,
   `docs/plans/completed/` and [decisions.md](../../design/decisions.md) and asks any other
   session before it takes the decision numbers Block 0 writes
   ([WORKING-RULES.md](../../../WORKING-RULES.md), "Commits and parallel sessions").

**Block 0 · interfaces, settings, harness and dependencies** (one agent)

2. **Dependencies.** One `uv add --package t2-agentic-voice ...` with exactly the packages of
   "Dependencies to install", which the owner allowed (certifi as Q1 rules), then `uv lock` (the
   lock goes in the same commit, since CI runs `uv sync --locked`). List every package new to
   `uv.lock` with the licence its installed metadata declares (`importlib.metadata`), in the
   progress log; a licence outside that section's table stops the block and goes to the owner.
   Run `uv run poe types`, and add a
   `[[tool.mypy.overrides]]` entry only for a package that ships no types (whether jiwer and
   openinference do is UNVERIFIED). Read the installed groq SDK's client as text, and record its
   default base URL and whether it falls back to `GROQ_API_KEY` or `GROQ_BASE_URL` when none is
   passed: groq 0.37.1, in the old repository's `venv`, does both, with the default
   `https://api.groq.com` (`groq/_client.py`, lines 77-87, read 2026-11-01); 1.7.x is
   UNVERIFIED until this step. Read the OpenTelemetry SDK and exporter the same way for the
   `OTEL_*` variables they read (the decision log).
3. **The `testing` layer.** `testing = ["core", "domain", "actions", "agent", "voice"]` in
   `[layers]`, `testing` added to `api`'s list (the design's 12.2: `api` imports every layer),
   `[[owners]] modules = ["jiwer"] layers = ["testing"]`, and
   `packages/t2-agentic-voice/src/t2_agentic_voice/testing/__init__.py` with its docstring.
   ARCHITECTURE.md gains its table row (ARCH-DOC compares the cells), its place in the diagram
   and its line in "Why these layers"; CLAUDE.md's code map gains its line.
4. **Facades and ARCH-FACADE.** A `[package] facades` key, read and checked by
   `scripts/harness_config.py` (each facade sits directly under the package root, its file
   exists, and it is in `public`); `check_file` treats a listed facade as the package root,
   which may import every layer while ARCH-OWNER still applies. ARCH-FACADE goes in a new helper,
   `scripts/arch_facade.py`, since `scripts/check_architecture.py` has 393 of its 400 lines: a
   facade holds a docstring, imports and the `__all__` assignment, nothing else. The same step
   moves ARCH-PUBLIC (`_AppChecker` and `check_app`, lines 226-289, about 65 lines) into its own
   helper, `scripts/arch_public.py`, so the facade changes, the new imports and the docstring's
   two new rule lines leave the module room under ARCH-SIZE. ARCH-PUBLIC also
   checks `from t2_agentic_voice import <facade>` as a module import (today only a layer name is
   treated so). `tests/harness/support.py`'s SYNTHETIC config gains the new keys, since every key
   is required.
5. **ARCH-WORDS.** A key `[package] banned_words = ["ole5", "otrs", "ds.t2.sa"]` (the agent's
   name for it; the design's 12.4 names none), checked case-insensitively over the source and
   text files under the library's `src/` (`*.py`, `*.md`, `*.toml`, `*.json`, `*.txt`, `*.js`,
   `*.html`, `*.css`) by a new helper, `scripts/arch_words.py`, skipping `__pycache__/`: a
   bytecode file holds its module's absolute path, and the owner's checkout sits under a folder
   named `OTRS-voice-agent`. Its tests include a `.pyc` holding a banned word, which is ignored.
   A grep of `packages/` on 2026-11-01 found none of the three, so it passes from the start.
   Since Block 0's review it also reads the path below `src/` of every file there, whatever its
   type (the progress log's review entry; D-020's Proposed bullet).
6. **Small harness fixes.** The stale FIX text at `harness.toml` line 38 names
   `ole5_voice.core.logging`; it becomes `t2_agentic_voice.core.logging`. `.gitattributes` marks
   `*.wav`, `*.webm`, `*.ogg`, `*.mp3`, `*.m4a` and `*.flac` binary. Ruff's RUF001 to RUF003 flag
   Arabic letters and digits in strings and comments (the research step's probe with ruff
   0.17.3, 2026-11-01): the library's tables use `\u` escapes with a comment naming each
   character, and `tests/**` ignores those three rules. ARCHITECTURE.md's Enforcement list and
   public-API paragraph name the new checks and the facades.
7. **The decision entries**, with the numbers checked in step 1: the `testing` layer (amends
   D-003); the harness checks ARCH-FACADE and ARCH-WORDS; the public facades and their stability
   (the design's 5.1); evaluation's split, with the scorers in the library, the golden-set
   runner in the app, and audio kept out of git (follows D-011); and tracing as plain OTLP to
   Phoenix through the OpenTelemetry SDK (the design's 10.1), which amends D-002's tracing bullet
   ("Arize Phoenix through `arize-phoenix-otel` and OpenInference"), with D-002's heading status
   updated to point at it. They are written as Accepted, as the owner ruled (Q3); anything an
   entry adds beyond the approved design is written as Proposed, for the owner to rule on.
8. **Settings.** In `core/config.py`, `env_nested_delimiter="__"`, `env_ignore_empty=True` and
   three groups: `groq` (`api_key`, a `SecretStr` or none; `api_key_file`, a path whose contents
   are the key; `base_url`, `https://api.groq.com`, the SDK's own default as step 2 reads it, so
   the adapter never passes none), `stt` (`provider` = `groq`; `model`, starting at
   `whisper-large-v3` until the registered rule sets it at the close; `timeout_s` = 6, the
   design's 7.6), and `tracing`
   (`endpoint`, none; `project`, none; `include_transcripts`, true; `redact`, empty).
   `var_dir` stays at the top level (moving it to `storage.var_dir`, as the design's 7.6 does,
   would break `tests/conftest.py`). `.env.example` lists every key (`T2V_GROQ__API_KEY`,
   `T2V_GROQ__API_KEY_FILE`, `T2V_GROQ__BASE_URL`, `T2V_STT__PROVIDER`, `T2V_STT__MODEL`,
   `T2V_STT__TIMEOUT_S`, `T2V_TRACING__ENDPOINT`, `T2V_TRACING__PROJECT`,
   `T2V_TRACING__INCLUDE_TRANSCRIPTS`, `T2V_TRACING__REDACT`), and
   `tests/t2_agentic_voice/core/test_config.py` walks the nested models to check it; without the
   delimiter, `extra="ignore"` would drop `T2V_GROQ__API_KEY` silently. A test also loads
   `Settings(_env_file=".env.example")` and finds the defaults: `.env.example` says "Copy to
   `.env` and fill in", and without `env_ignore_empty` a blank `T2V_STT__TIMEOUT_S=` fails
   validation and a blank `T2V_GROQ__API_KEY_FILE=` becomes the path `.` (the feasibility
   review's probe; the agent's own probe of the blank timeout, pydantic-settings 2.16.2,
   2026-11-01). The invariant 5 test goes
   in the same file: every key field is a `SecretStr`, and a made-up key appears in no repr and no
   log line. `tests/conftest.py` also removes every `GROQ_*`, `OTEL_*` and `PHOENIX_*` variable,
   and `tests/harness/test_isolation.py` checks it.
9. **Errors.** `ProviderError(kind, retryable, retry_after_s)` in `core/errors.py`, with a stable
   code and a closed list of kinds (rate limited, timeout, lost connection, server error, and
   rejected: an authentication or request error, never retryable); the code list in
   `tests/t2_agentic_voice/core/test_errors.py` grows with it; the package root exports it.
10. **Interfaces, with stubs that raise `NotImplementedError`** (a test per stub says so, which
    keeps the coverage floor; each stub's test sits in the test file of the track that owns the
    stub, as `## Tracks` lists them, so the track replaces it in its own file):
    - `domain/ports/__init__.py` and `domain/ports/speech_to_text.py`: `DataFlow`, `AudioClip`,
      `Transcript` (plus an optional `no_speech_prob`, as the owner ruled: Q2) and the
      `SpeechToText` protocol, as in the design's 6.1;
    - the stubs each track fills: `domain/text/arabic.py`, `domain/text/digits.py`,
      `domain/text/spelling.py`, `domain/scoring.py`, `domain/sign_test.py`,
      `testing/scorers.py` (Track A); `adapters/groq_stt.py` (Track B); `core/tracing.py` and
      `core/redaction.py` (Track C); in the app, `ole5_voice/evals/` modules named in `## Tracks`;
    - the facades `ports.py`, `groq.py`, `languages.py`, `evals.py` and `tracing.py` at the
      package root, with every public name M1 adds and the module it lives in (`Redactor` in
      `core/redaction.py` included), so no track edits a facade;
    - the app's shared models in `apps/ole5-voice-agent/src/ole5_voice/evals/models.py`: an item,
      a variant, an audio reference (root name, path, SHA-256), a manifest (and
      its consent record), a script line (`script.toml`'s format), the recorder's take
      sidecar (device label, session, track settings, turn ends, kept or discarded), an answer,
      a variant's result, a scorecard, a history line, and the answerer protocol (split by the
      review into `models.py`, `runs.py` and `takes.py`, each under ARCH-SIZE: the decision
      log);
    - `ole5_voice/evals/audio.py`, written in full here because Tracks D, E and G all need it:
      reading a WAV with `wave`, checking 16 kHz mono 16-bit, its SHA-256 and length, and cutting
      a leading window, with its tests in `tests/ole5_voice/evals/test_audio.py`;
    - the fakes tests build against, in `tests/ole5_voice/evals/fakes.py`: a fake
      `SpeechToText`, a fake normalizer, and a fake, or a callable passed in, for each piece one
      track calls in another: the matcher, the items and the split (D), the scorecard writer and
      the history (F), `sign_test`, the spelling check and the scorers (A), and the tracing span
      helpers (C);
    - the poe tasks `golden`, `eval`, `eval-compare`, `eval-history` and `record` in the root
      `pyproject.toml`, each running `python -m ole5_voice.evals.<module>`, whose `main` parses
      its arguments with argparse (GP-17); GP-17's test (`tests/harness/test_commands.py`, which
      today reads only `scripts/`, lines 38-55) extended to every module a poe task runs with
      `python -m`; and the tasks' rows in CLAUDE.md (107 of 120 lines today).
11. **Baselines** the tracks are compared with byte for byte:
    - the fields a `GroqSTT` call must send for a fixed clip: the model, the language,
      `response_format` = `verbose_json`, `temperature` = 0, no prompt, the file name, and the
      media type `audio/wav`, passed explicitly, from the prototype's call
      (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, lines 221-246) and Groq's API reference (read
      2026-11-01), as a test fixture. The prototype passes no media type (`("speech.wav", wav)`,
      line 231), so httpx guesses one with `mimetypes` (httpx 0.28.1, `_multipart.py`, line 52,
      in the old repository's `venv`), which gives `audio/wav` on this Windows machine and
      `audio/x-wav` from Python's own table (a probe, 2026-11-01): a guessed value would differ
      between the owner's machine and CI;
    - the normalizer's characterization table: inputs and expected outputs written from reading
      `Ole5-chatbot/src/ole5_chat/voice/rules.py` (lines 11-19, `normalize`) and
      `Ole5-chatbot/scripts/stt_eval.py` (lines 1059-1066, `norm`), as a fixture; the
      prototype's code is read, never run (D-010);
    - `uv run poe arch` and `uv run poe docs` clean.
12. Gate, review (the harness and security reviewers), fixes, merge into
    `plan-002-integration`.

**The tracks** (in parallel, after Block 0; each track's files, reads and tests are in
`## Tracks`)

13. Track A: text and scorers. Track B: the Groq speech-to-text adapter. Track C: the tracing
    helpers. Track D: the golden set's items, matcher, validation and split. Track E: the runner.
    Track F: scorecards, comparison and history. Track G: the recorder. Track H: the docs. Each
    track ends with a report: its progress-log lines (prototype sources, values chosen), its
    decision-log lines and any debt rows.
14. Merge in the order A, B, C, D, F, E, G, H (`Plan 002: merge track X`, then
    `Plan 002: review fixes, track X`), with the full gate after each merge. The integrator (the
    agent that merges) is the only writer of this plan and of `docs/plans/tech-debt.md`: it copies
    each track's report into them, numbering the debt rows, in the `merge track X` commit.
15. **The integration check, with no spend.** In a linked worktree, `poe eval --answerer
    reference --split dev` and `--split held-out` over the whole committed set each score 100%
    (a run covers one split: the decision log). The agent writes
    `tests/ole5_voice/evals/test_reference_answerer.py`, which does the same inside
    `poe check`.
16. **The whole-plan review of the code**, by every reviewer, before the owner records. Then
    `plan-002-integration` merges into the main branch, with the full gate, so that the owner
    records from the main checkout ("What the owner does", step 4); from here, this plan's
    blocks merge into the main branch.

**The owner's recordings** (needs "What the owner does", steps 3 to 5)

17. Track D's script of new items, built from the agent's proposal in the registration, goes to
    the owner with Q4, Q5, Q7 and Q9; the owner approves or changes it.
18. The owner records on each device with `poe record`, then listens to and confirms each
    variant (the independent check, Q9; a variant whose text the owner typed is confirmed again
    in a later review pass), and marks the true turn ends of each several-clause take.
19. With Q10 settled, the agent imports the new takes' manifests and hashes (no audio)
    into `apps/ole5-voice-agent/evals/`, labels the talk-over items' dialect as the owner ruled
    (Q7), runs `poe golden --audio talkover=<path> --audio owner=<path>` to validate and freeze,
    commits the split (`split --check`) and the strata table, gates and commits. The item set is
    fixed from here until the close. Then, optionally (the agent's proposal), a dry run with no
    spend: a `prototype-cache` answerer replays the prototype's stored Groq answers
    (`voice-lab/eval/_cache/calls.jsonl`, looked up by the key that
    `Ole5-chatbot/scripts/stt_eval.py` builds at lines 551-552) over the dev talk-over items only,
    to run the whole path on real Whisper output without a request. It runs only once the split
    is committed, so that no held-out item's output is read. A dry run is never a baseline: the
    code that made the cache is unidentified, and dry runs append no history line.

**The registered runs** (the registration below; a quiet machine: nothing else runs beside a
run, [WORKING-RULES.md](../../../WORKING-RULES.md), "Measurement runs")

20. Every open call settled and dated; the estimate and the budget cap approved by the owner; a
    `## Schedule (unattended)` section approved first if the owner will be away. Before each run
    that spends, the spend so far (each earlier run's billed seconds times its price, from its
    history line) plus the run's own estimate is compared with the cap, and a run that would pass
    it does not start; the run is also given what is left of the cap as `--cap-usd`; the running
    total goes into the progress log after each run ([WORKING-RULES.md](../../../WORKING-RULES.md),
    "Unattended sessions": "the session stops a step that would cross it").
21. A clean run worktree at the measurement commit (the commit of step 19), where every run of
    steps 22 to 27 starts, whatever the main branch gains meanwhile. `poe eval --show-settings`
    checks the resolved settings and paths; the smoke test passes with no failed, retried or
    refused call. A `--smoke-only` run calls the provider, so its history line is carried over as
    in step 23 before the next run.
22. The tracing check: one traced smoke request with `--tracing-endpoint` pointing at the
    owner's Phoenix ("What the owner does", step 7); its trace is seen in Phoenix's page at
    `http://127.0.0.1:6006`, and Phoenix's listening socket is bound to 127.0.0.1 only
    (`Get-NetTCPConnection -LocalPort 6006 -State Listen`); its history line is carried over as in
    step 23.
23. Runs R1 to R4 on dev, in the order large-v3, turbo, large-v3, turbo, untraced, each with the
    command line registered under "The arms". After each run, before the next: its history line
    is carried to the main branch in its own commit (`Plan 002: history, run R1`), with
    `poe eval-history` regenerating `docs/generated/eval-history.md` in the same commit (GP-11);
    then the run worktree's file is reset
    (`git checkout -- apps/ole5-voice-agent/evals/history.jsonl`), so the next run starts clean
    at the measurement commit (WORKING-RULES.md, "Measurement runs": "carry its new lines over
    first, then reset it"). Full scorecards stay in the persistent folder given as `--out`.
24. The noise: for each model, its two runs by `eval-compare` (R1 against R3 for large-v3, R2
    against R4 for turbo); the counts and the smallest detectable change, as registered, become
    a decision entry and a tech-debt row (numbers checked as in step 1).
25. The baseline: R2 against R1 (and R4 against R3 as a replication) by `eval-compare`; the
    registered rule sets `stt.model`'s default in `core/config.py` and `.env.example`, in its
    own commit on the main branch. The run worktree stays at the measurement commit: W1 to W6,
    H1 and H2 run there, with the model on their command line.
26. The windows: runs W1 to W6 on the registered talk-over clips (Q15), each model at each
    window length, untraced; their scorecards keep every window's transcript. Each history line
    is carried over as in step 23.
27. Held-out: one run per model, aggregates only, untraced, within the cap (Q18), each history
    line carried over as in step 23.

**Close**

28. The decision entries not yet written; the guide's `evaluation.md` finished; evaluation.md's
    paragraph on where the commands live; `## Future improvements` in this plan, ordered by
    expected value, with a pointer from the roadmap's "Planned later"; the whole-plan review;
    the roadmap's M1 row set to `done` with a link; this plan moved to `completed/` with its
    Status line; the final gate.

## Progress log

- 2026-11-01: Plan written by the agent from four research reports made that day by a workflow
  of agents: the method's requirements (evaluation.md, the roadmap, the design, the decisions),
  an inventory of the prototype's recordings and scorer (read only, D-010), external facts
  (Groq's speech-to-text, models and rate-limit pages; PyPI metadata for groq, OpenTelemetry,
  OpenInference, jiwer and Phoenix; Phoenix's self-hosting page), and the harness's constraints.
  The agent re-read at their source the facts the plan relies on: the talk-over manifests
  (`voice-lab/recordings/talkover/refs.json` and `takes.json`), the prototype's normalizer,
  scorer and Groq call, its run reports (`voice-lab/eval/talk1/report.md`,
  `voice-lab/eval/final-talk/report.md`) and log lines, and this repository's harness and
  settings. Nothing is built, no package installed, and no request sent to Groq. The roadmap's M1
  row is changed to `in progress` with a link to this plan in the commit that adds it (DOC-PLAN
  fails until then). The same day, two agents that did not write the plan reviewed it (one for
  feasibility and the harness; one for faithfulness, measurement and safety), and each of their
  36 findings (five raised by both) was checked against its cited source: all 36 held and were
  applied, and none was rejected. Next: the owner's calls marked "before Block 0", then Block 0.
- 2026-11-01: The agent checked the plan against its sources before committing it, and changed
  four things. The owner's answer on the downloads is in this session's record of the question,
  so it is quoted under "The owner's decisions" and Q21 is withdrawn. Q20 is withdrawn: the
  owner chose one install, with no extras (D-018). Q6 became the agent's choice (the decision
  log). Q5 moved to before recording, where the owner approves the script's ticket items with
  Q4: Block 0 and the tracks need no ticket shape, since `id_recall` is tested on made-up digit
  strings. Next: Q1 to Q3 and Q8, then Block 0.
- 2026-11-01: The owner settled Q1 to Q3 and Q8, each with the agent's recommended answer
  ("The owner's decisions"). Every call before Block 0 is settled; Block 0 starts.
- 2026-11-01: Block 0, step 1's check done by the integrating session (every linked session
  idle; `active/` holds 000 and 002, `completed/` 001; decisions.md ends at D-018), so Block 0's
  entries take the numbers after D-018. Block 0 is built in a linked worktree cut from the main
  branch at 0f44056.
- 2026-11-01: Block 0, step 2. The `uv add` line of "Dependencies to install", as written, then
  `uv lock` (no change). 26 packages are new to `uv.lock`, each with the licence its installed
  metadata declares (`importlib.metadata`: `License-Expression`, else `License`):
  - Apache-2.0: `groq` 1.7.0, `jiwer` 4.0.0, `openinference-semantic-conventions` 0.1.43,
    `opentelemetry-api`, `-sdk`, `-proto`, `-exporter-otlp-proto-http` and
    `-exporter-otlp-proto-common` 1.45.2, `opentelemetry-semantic-conventions`,
    `-exporter-http-transport` and `-exporter-otlp-common` 0.66b2, `googleapis-common-protos`
    1.76.0, `requests` 2.34.2, `distro` 1.9.0;
  - BSD-3-Clause: `httpx` 0.28.1, `httpcore` 1.0.9, `idna` 3.20, `click` 8.5.0, `protobuf`
    7.36.2 ("3-Clause BSD License");
  - MIT: `anyio` 4.15.1, `h11` 0.16.0, `rapidfuzz` 3.14.6, `urllib3` 2.8.0,
    `charset-normalizer` 3.5.2; MIT or Apache-2.0: `sniffio` 1.3.1;
  - MPL-2.0: `certifi` 2026.10.23, accepted by the owner (Q1).

  Every licence is in the section's tables; the two exporter packages the tables do not name,
  `opentelemetry-exporter-http-transport` and `opentelemetry-exporter-otlp-common`, fall under
  "the exporter's other `opentelemetry-*` packages". None pulls numpy. All six packages ship
  `py.typed`: `poe types` passes, and so does a strict probe outside the repository that imports
  each, so no `[[tool.mypy.overrides]]` entry is added. The installed groq 1.7.0, read as text:
  its default base URL is `https://api.groq.com`; with no key it reads `GROQ_API_KEY`, with no
  base URL `GROQ_BASE_URL` (`groq/_client.py`, lines 80-91 for `Groq`, 293-304 for `AsyncGroq`);
  it also reads `GROQ_CUSTOM_HEADERS` whatever is passed (lines 93-100 and 306-313) and adds its
  headers under any `default_headers` given but over the `Authorization` header it builds from
  the key passed (`groq/_base_client.py`, lines 672-680; corrected in the review: so such a
  variable naming `Authorization` replaces the key), and `GROQ_LOG` when `groq` is imported
  (`groq/_utils/_logs.py`, line 17, called from `groq/__init__.py`, line 79), which sets the
  `groq` and `httpx` loggers to DEBUG or INFO; its defaults are a 60 s timeout (5 s to connect)
  and 2 retries (`groq/_constants.py`, lines 9-10). The OpenTelemetry reading is in the decision
  log.
- 2026-11-01: Block 0, steps 3 to 6, and step 7's first two entries. The `testing` layer:
  `[layers]` (and `api`'s list), its `[[owners]]` row for jiwer,
  `packages/t2-agentic-voice/src/t2_agentic_voice/testing/__init__.py`, its row, place in the
  diagram and line in "Why these layers" in ARCHITECTURE.md, and its line in CLAUDE.md's code
  map. `[package] facades`, read and checked by `scripts/harness_config.py` (directly under the
  package root, in `public`, not a layer's name, its module file present), stays empty until
  step 10 lists the five facades with their modules. `check_file` treats a listed facade as the
  package root. ARCH-FACADE is in `scripts/arch_facade.py`; ARCH-PUBLIC moved into
  `scripts/arch_public.py` and treats a facade's name as a module import, which leaves
  `scripts/check_architecture.py` at 343 lines; ARCH-WORDS is in `scripts/arch_words.py`, with
  `[package] banned_words`, and passes on the library from the start. Tests:
  `tests/harness/test_arch_facade.py`, `tests/harness/test_arch_words.py` (a `.pyc` holding a
  banned word under a checkout folder named with one, ignored) and three in
  `tests/harness/test_harness_config.py`; `tests/harness/support.py`'s SYNTHETIC gains both keys,
  empty. Step 6: `harness.toml`'s FIX text names `t2_agentic_voice.core.logging`;
  `.gitattributes` marks the six audio types binary; `tests/**` ignores RUF001 to RUF003;
  ARCHITECTURE.md's Enforcement list names ARCH-FACADE and ARCH-WORDS (its public-API paragraph
  names the facades in step 10, with them). D-019 (the `testing` layer, amending D-003, whose
  heading now points at it) and D-020 (the two checks), each Accepted with one bullet Proposed.
- 2026-11-01: Block 0, step 7's other entries: D-021 (the first public facades and their
  stability), D-022 (evaluation's split between the library and the app, following D-011) and
  D-023 (tracing as plain OTLP through the OpenTelemetry SDK, amending D-002's tracing bullet;
  D-002's heading now points at it). Each is Accepted as the design describes it, with one
  bullet Proposed for what it adds (Q3).
- 2026-11-01: Block 0, steps 8 and 9. `core/config.py` gains `env_nested_delimiter="__"`,
  `env_ignore_empty=True` and the groups `groq` (`api_key`, `api_key_file`, `base_url`), `stt`
  (`provider`, `model`, `timeout_s`) and `tracing` (`endpoint`, `project`,
  `include_transcripts`, `redact`), with the plan's defaults; `var_dir` stays at the top level.
  `.env.example` lists all ten new keys. `tests/t2_agentic_voice/core/test_config.py` walks the
  nested models against `.env.example`, loads `.env.example` as a `.env` (the defaults) and a
  copy with only the key filled in (the key, and every other default), and holds the invariant
  5 tests: the one secret setting, `groq.api_key`, is a `SecretStr`, and a made-up key, given
  directly or in a key file, appears in no repr, dump or log line (structured and standard
  library). `tests/conftest.py` removes every `GROQ_*`, `OTEL_*` and `PHOENIX_*` variable, and
  `tests/harness/test_isolation.py` checks it, in this run and in a child run whose shell sets
  some. `ProviderError(kind, retryable, retry_after_s)` in `core/errors.py`, code
  `provider_error`, kinds `rate_limited`, `timeout`, `connection_lost`, `server_error` and
  `rejected`; the package root exports it, and `tests/t2_agentic_voice/core/test_errors.py`'s
  code list has it.
- 2026-11-01: Block 0, step 10, the library's part. The port: `domain/ports/__init__.py` and
  `domain/ports/speech_to_text.py` (`DataFlow`, `AudioClip` with its `seconds`, `Transcript`
  with `no_speech_prob`, and the `SpeechToText` protocol), with
  `tests/t2_agentic_voice/domain/test_ports.py`. The stubs, each raising `NotImplementedError`
  that names its track, each with a test in its track's file: Track A's `domain/text/arabic.py`,
  `digits.py` and `spelling.py`, `domain/scoring.py`, `domain/sign_test.py` and
  `testing/scorers.py`; Track B's `adapters/groq_stt.py`; Track C's `core/tracing.py` and
  `core/redaction.py`. Two modules more, with their own tests, hold the types two tracks share:
  `domain/text/rulings.py` (`SpellingRule`, `SpellingIssue`: Tracks A and D) and
  `domain/recall.py` (`Recall`: Tracks A and F). The facades `ports.py`, `groq.py`,
  `languages.py`, `evals.py` and `tracing.py`, now in `[package] facades` and `public`, with
  `tests/t2_agentic_voice/test_facades.py` holding each one's names; ARCHITECTURE.md's
  public-API paragraph and CLAUDE.md's code map name them.
- 2026-11-01: Block 0, step 10, the app's part, in `apps/ole5-voice-agent/src/ole5_voice/evals/`.
  `models.py`: the item, the variant, the audio reference, the manifest with its consent
  record, the script line, the take sidecar (with the track's settings) and the review, the
  request, the window, the answer and the answer request, the variant's result, the metrics,
  the run, the scorecard, the history line, and the protocols `Answerer`, `Matcher` and
  `ScorecardWriter`; tested in `tests/ole5_voice/evals/test_models.py`. `audio.py`, in full:
  reading a WAV with `wave`, refusing all but 16 kHz mono 16-bit PCM and a file cut short, the
  SHA-256 of the bytes and of a file read in chunks, the length, a leading window, and writing
  a WAV; tested in `tests/ole5_voice/evals/test_audio.py` on made-up clips. The stubs: Track D's
  `items.py`, `toml_write.py`, `import_talkover.py`, `import_recordings.py`, `matcher.py`,
  `golden.py` and `split.py`; Track E's `run.py`, `answerers.py`, `windows.py` and
  `worktree.py`; Track F's `scorecard.py`, `compare.py` and `history.py`; Track G's
  `recorder.py`; each stub's test in its track's file. `tests/ole5_voice/evals/fakes.py` (a
  fake `SpeechToText`, a fake normalizer, a fake matcher, scorecard writer, sign test, spelling
  check and tracing helpers) with `test_fakes.py`, and `samples.py` (valid made-up models).
  The poe tasks `golden`, `eval`, `eval-compare`, `eval-history` and `record`, each running
  `python -m ole5_voice.evals.<module>`; GP-17's test (`tests/harness/test_commands.py`) now
  reads every module a poe task runs with `python -m`, the apps' included, and fails a task's
  module with no `main`; `tests/ole5_voice/evals/test_commands.py` runs each command's `--help`
  as `python -m` would. CLAUDE.md gains two rows for the five tasks and a code-map line (112 of
  its 120 lines).
- 2026-11-01: Block 0, step 11, the baselines, in `tests/t2_agentic_voice/fixtures/`:
  - `groq_stt_request.json`: for a fixed made-up clip (1 s at 16 kHz, its samples given by a
    formula, its WAV written with `wave`, 32,044 bytes, with its SHA-256) and the default
    settings, the request `GroqSTT` must send: a POST to
    `https://api.groq.com/openai/v1/audio/transcriptions` with the multipart fields `model`
    `whisper-large-v3`, `language` `ar`, `response_format` `verbose_json` and `temperature`
    `0` (the SDK sends a form value as `str(value)`,
    `groq/_qs.py`, lines 120-128), no `prompt`, and the file `speech.wav` as `audio/wav`; the
    client with `max_retries` 0 and a 6 s timeout. From the prototype's call
    (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, lines 221-246), the plan's reading of Groq's
    reference, and the installed SDK (`groq/resources/audio/transcriptions.py`, lines 236 and
    454, the path).
  - `arabic_normalizer_characterization.json`: 37 rows, each an input with what the
    prototype's `rules.normalize` (`Ole5-chatbot/src/ole5_chat/voice/rules.py`, lines 11-19)
    and `stt_eval.norm` (`Ole5-chatbot/scripts/stt_eval.py`, lines 1059-1066) make of it,
    written by reading the code, never by running it (D-010): each folded letter form, the
    diacritics, tatweel and annotation marks, Arabic and Latin punctuation, Arabic-Indic and
    Persian digits, spaces, mixed text with product terms, and a word split in two. Two rows
    (digits said one by one, in Arabic and in English) carry a `gap`, where Q8 rules otherwise
    than the prototype and Track A's output is the guide's (`57`). The forms the prototype leaves
    unfolded (alef wasla, Farsi yeh, keheh, a lone hamza) are kept, since Q8 folds only the
    prototype's letter forms; the first version marked these four as gaps too, which the review
    found Q8 never ruled. Before it was written, each hand-written row was checked against an
    independent reading of the two functions, in a scratch script outside the repository; the
    check caught one wrong row.

  `tests/t2_agentic_voice/test_baselines.py` keeps both consistent: the clip rebuilds to its
  hash, and every row's `norm` is its `normalize` with the digits read and the spaces removed.
  `uv run poe arch` and `uv run poe docs` are clean. Block 0 is built; next, the review (step
  12) and the merge into `plan-002-integration`, by the integrating session.
- 2026-11-01: Block 0 reviewed (step 12) by five agents that did not write it, one for each
  concern: the harness, security, faithfulness to the plan and its sources, correctness, and the
  tracks' readiness. Their 38 findings, 25 distinct issues (8 raised by more than one reviewer),
  were each checked by an agent told to refute it: all 38 held, some at a lower severity or with
  a corrected fix; none was rejected; none goes to the owner, since no fix changes the design, a
  decision's substance, the registered measurement or an owner's ruling. All 25 are fixed in one
  commit (`Plan 002: review fixes, Block 0`), each choice a fix makes in the decision log, and
  what belongs to a later track is in that track's lines under `## Tracks`, with the debt left
  as TD-002 to TD-007:
  - Harness: `tests/conftest.py` drops the shell's `GROQ_*`, `OTEL_*`, `PHOENIX_*` and `T2V_*`
    variables before collection, since `groq` and `opentelemetry.context` read `GROQ_LOG` and
    `OTEL_PYTHON_CONTEXT` on import (`tests/harness/test_import_isolation.py`, also in the child
    run, whose shell now sets both); ARCH-WORDS reads the path of every file below the library's
    `src/`, whatever its type; CLAUDE.md, ARCHITECTURE.md, `harness.toml`'s comments, the
    library's README and its `__init__.py` name the facades as public API.
  - Security: a key holding a space, a line break, a control or a non-ASCII character is refused
    as it is read, naming its setting, and a key file's byte-order mark is dropped; a URL setting
    with a bad port or `[host]`, a base URL with a query, and an infinite timeout are refused,
    with no error text from urllib; `Settings.from_env` loads the settings and reports every
    failure as a `ConfigurationError` that names settings only; `parse_wav` raises only
    `AudioFormatError` (a chunk that claims more bytes than the file holds, an empty file); a
    path below a root refuses Windows device names, trailing dots and spaces, control
    characters and `.`; the models refuse a traced held-out run, a held-out scorecard with a
    variant, a variant of another split, and a secret setting shown as anything but set or not
    set; the Groq SDK's `GROQ_CUSTOM_HEADERS` and `GROQ_LOG` reach Track B's lines.
  - Faithfulness: the four letter-form rows Q8 never ruled are no longer gaps (step 11's entry
    above is corrected); D-021's Proposed bullet adds `AudioClip.seconds` and the port types'
    input checks.
  - Correctness: `ProviderError` pickles and copies; the consent test changes only the flag;
    the config tests cover a missing and an undecodable key file and every error's traceback;
    `wer`, `cer` and `term_recall` say a bare str raises TypeError.
  - The tracks' readiness: the library's strings no longer hold a talk-over reference ("stop",
    "wait"); the models gain each window's measures and `WindowMetrics`, the `want` label, the
    item's terms on each result, the ticket kind's name, a run's price per hour, the
    scorecard's file name, the not-judged state of a window-only run, Whisper's confidence and
    each segment's answer, the split file, the script with its listening sounds, the session
    record that carries the consent, and the recorder's file names; the fakes gain the items and
    the split, the history and the scorers; `requests` is declared and owned by `core`; a run
    covers one split (step 15).

  The models moved out of `models.py` into `runs.py` (what a run produces) and `takes.py` (the
  recorder's files), so each stays under ARCH-SIZE. `uv run poe check` passes: 347 tests,
  100% coverage, mypy strict on 126 files, `uv lock --check` clean. Next, the merge into
  `plan-002-integration`, by the integrating session.
- 2026-11-01: Block 0's review, second round. After the five agents by concern (the harness,
  security, faithfulness, correctness and the tracks' readiness) and the first fixes, a check of
  those fixes raised 8 findings; each was checked by an agent told to refute it, and all 8 held
  and are fixed in commit `Plan 002: review fixes, Block 0 (second round)`; none was rejected,
  and none goes to the owner. The fixes:
  - `Settings.from_env` refuses an `env_file` that is no file, with a test of a missing file and
    of a folder (`tests/t2_agentic_voice/core/test_config.py`), since pydantic-settings skips a
    missing one silently.
  - Track B's hook also sets `Authorization` to the settings' key after dropping the headers
    outside its allow-list, and its test uses a lowercase `authorization` line: passing
    `default_headers` alone left a lowercase line's value in the request beside the key (a probe
    of groq 1.7.0, made-up keys). The groq entry of the decision log and TD-002 say so.
  - D-023's Proposed bullet names `requests` and its `[[owners]]` row; D-020's says ARCH-WORDS
    reads the text of the listed types and the path of every file below `[package] root`
    (step 5 points to it).
  - TD-004 names no track; the OpenTelemetry entry of the decision log says the review wrote the
    debt rows as TD-002 to TD-007; the reference answerer's held-out runs are outside Q18's cap
    and append no history line; `## Tracks` lists Block 0's test files, which no track edits.

  `uv run poe check` passes: 349 tests, 100% coverage, mypy strict on 126 files, `uv lock
  --check` clean. Next, the merge into `plan-002-integration`, by the integrating session.
- 2026-11-01: Block 0 is merged into `plan-002-integration` (`Plan 002: merge Block 0 into
  plan-002-integration`). In all, 44 findings were raised: 38 held and are fixed, 6 were
  refuted by the agent that checked them, and none goes to the owner; the debt they left is
  TD-002 to TD-007. The second round's check found one slip, the entry above naming the first
  round's commit as its own, corrected here. After the merge `uv run poe check` passes (349
  tests, 100% coverage, mypy strict on 126 files) and `uv lock --check` is clean. Next, Tracks
  A to H, each in its own worktree cut from `plan-002-integration`.

## Decision log

All entries are the agent's choices of 2026-11-01, with the agent's reasons.

- 2026-11-01: The runner's code lives in `apps/ole5-voice-agent/src/ole5_voice/evals/`, its data
  (items, frozen answers, split, strata, manifests, screens, history) in
  `apps/ole5-voice-agent/evals/`, and its tests in `tests/ole5_voice/evals/`, because the design
  puts the golden-set machinery in the app (its 9.7 and 12.1). evaluation.md's suggested
  `evals/golden/`, `scripts/eval/` and `tests/evals/` are updated to match (Track H).
  Alternative: a top-level `scripts/eval/`, set aside for the same reason; the gate would
  type-check and cover it too (`pyproject.toml`, the `types` task, lists `scripts`;
  `harness.toml`, coverage `source`, lists `scripts`).
- 2026-11-01: The `testing` layer owns jiwer, as the approved design's 12.2 and 13 place it.
  Alternative: our own edit distance in `domain` (as the prototype's `lev`), with no new layer;
  set aside because GP-10 prefers a well-known library, and the layer is needed for the testing
  kit later anyway (the design's 12.2).
- 2026-11-01: The Arabic normalizer is ported from the prototype's `rules.normalize` and `norm`,
  with the gap the spelling guide rules on (number words: digits said one by one count as those
  digits, Q8); ٱ, ی, ک and a lone ء are kept, as the prototype keeps them, since Q8 folds only
  the prototype's letter forms (this entry, written before Q8 was settled, named them as gaps
  too; corrected in Block 0's review). camel-tools' normalizers are not vendored in M1 (the
  design's 13 allows it), since the port covers what the golden set needs and adds no notice
  file. Folding more forms (ی to ي, ک to ك, ٱ to ا) would be a new ruling for the owner, or a
  measured change later (GP-18).
- 2026-11-01: No num2words in M1. Spelled-out digits are read one digit word at a time; numbers
  said as number words follow the spelling guide; num2words comes with spoken numbers, in M2.
- 2026-11-01: Items are TOML files read with the standard library's `tomllib`, and written by a
  small writer for their fixed shape, tested by a round trip, so no TOML-writing package is
  added.
- 2026-11-01: `GroqSTT` turns the SDK's own retries off and maps every failure to a
  `ProviderError`; the runner waits and asks again, so every retry is counted and the smoke test
  can require none. The wait on a rate limit is the larger of `retry-after` and 20 s, ported from
  `Ole5-chatbot/scripts/stt_eval.py` lines 575-582.
- 2026-11-01: The runner sends one request at a time, paced by `--max-rpm`, 20 by default: the
  lowest Whisper limit Groq publishes (its rate-limits page, read 2026-11-01). Score and order
  then never depend on the number of workers.
- 2026-11-01: The app picks the adapter from `stt.provider` (only `groq` exists), so GP-22's "by
  configuration" holds as written and M1 needs no entry widening it.
- 2026-11-01: The new dependencies get lower bounds, like the three the library has
  (`packages/t2-agentic-voice/pyproject.toml`), and `uv.lock` pins the exact versions: the
  agent's reading of D-002's "pinned". Alternative: `~=` ranges, as the design gives Pipecat.
- 2026-11-01: No live pytest test in M1. `tests/conftest.py` removes every `T2V_*` variable, so a
  live test would need new machinery to see the key; the live check is `poe eval`'s smoke step,
  as evaluation.md's "Running" asks. Async code is tested with `asyncio.run`, so no pytest
  plugin is added.
- 2026-11-01: "No audio under `apps/`" is a test inside `poe check`, not only a CI step: CI waits
  for a remote (TD-001), and CI will run the same gate.
- 2026-11-01: The `reference` answerer inside `poe check` is a test: it reads no `var/` (GP-15)
  and appends no history line. "Every run appends" a line means every `poe eval` run that calls
  a provider; dry runs (the reference and cache answerers) append nothing. A run refuses a dirty
  tree, so the `+` evaluation.md allows on a commit never appears; the field stays in the schema.
  Since a run's own line makes its worktree dirty, the line is carried to the main branch after
  each run and the worktree's file reset (step 23), as WORKING-RULES.md's "Measurement runs"
  says, so every run starts clean at the measurement commit and its line records that commit.
  Alternative: the runner writes its line only under `--out`; set aside because evaluation.md's
  "Run history" has every run append to the committed file.
- 2026-11-01: The no-item-in-source test searches for every item's reference, normalized and as
  whole words, in every text file and every Python string constant under `packages/`,
  `apps/*/src` and `examples/`, as evaluation.md's "No item in the product" says. 24 of the 43
  talk-over references are one or two words (`refs.json`, read 2026-11-01), such as «نعم أرسلها»
  and "stop", and the library's preset words (M3) may hold some of them, so the test exempts
  only the entries of one allow-list file, `apps/ole5-voice-agent/evals/allowed_in_source.toml`,
  each with its reason. It starts empty; each entry narrows a rule the owner approved (D-011), so
  it is added only on the owner's ruling, quoted and dated. The app's own labels avoid the words
  of one-word references (a kind is `stop_word`, not `stop`). The first draft searched only
  references of three or more words, which the review found narrowed the rule without the owner.
- 2026-11-01: A talk-over take that the lab's detector split into two segments is one variant,
  scored on its segments' transcripts joined, as the prototype did
  (`Ole5-chatbot/scripts/stt_eval.py` lines 400-442): both segments carry the whole phrase as
  their reference (`refs.json`, read 2026-11-01), so a segment alone has no reference. Its
  windows are cut from its first segment file, which holds the take's start. The agent's choice,
  which the owner may overrule before the import (it was Q11 until the review).
- 2026-11-01: The four talk-over takes with no segment, the lab's `discarded/` takes, and the
  earlier mic-lab recordings (`voice-lab/recordings/*.wav`) stay out of M1's golden set: the
  roadmap names the 124 segments and new recordings.
- 2026-11-01: Every talk-over segment was captured by the laptop's microphone array, the three
  labelled `headset` included (`refs.json`, `mic_label`); the device stratum is the microphone
  used, and the playback device becomes a tag. The agent's choice, which the owner may overrule
  before the import (it was Q12 until the review).
- 2026-11-01: Speech-to-text runs are untraced; the tracing check is one traced smoke request.
  A local Phoenix is load on the machine during a measurement, held-out runs are never traced,
  and the dev runs' per-variant results are in their scorecards anyway.
- 2026-11-01: The recorder is a page served by the standard library's `http.server` on
  127.0.0.1, capturing 16 kHz mono 16-bit WAV in the browser, with Chrome's echo cancellation,
  noise suppression and gain control on, as the talk-over takes were captured (`takes.json`,
  `mic_settings`). No audio package is added, and the lab's recorder is not used: the lab is
  read-only (D-010) and its server reads the old repository's `.env`
  (`voice-lab/server.py`, line 46).
- 2026-11-01: `stt.model` starts at `whisper-large-v3`: the prototype's runbook sent Arabic to it
  (`Ole5-chatbot/VOICE_LOG.md`, lines 93-94), and turbo was the weaker model on Arabic with echo
  (`Ole5-chatbot/VOICE_V2_PLAN.md`, lines 30-44). The registered rule sets the default at the
  close.
- 2026-11-01: A variant's verdict is an exact match after normalization, the prototype's
  `text_score` exact (`stt_eval.py` lines 1079-1086), so fixed, broken and net are defined; WER
  and CER are reported beside it. As in the prototype's `norm` (lines 1062-1066), the verdict
  compares the normalized strings with every space removed, so a word split differently (two
  words written as one) is still right; Track D adds a characterization case for it. CER also
  removes spaces first, so such a split is not counted twice. WER and CER are pooled per stratum
  over the variants with a non-empty reference, so they are not comparable with the prototype's
  CER, which is capped at 1 per variant and taken against the closest accepted reference.
- 2026-11-01: `groq.timeout_s` is left out of M1: the design's 7.6 gives it no default, and
  `stt.timeout_s` covers the only Groq call M1 makes.
- 2026-11-01: The facades M1 adds are the design's 5.1 modules that hold M1's names (`ports`,
  `groq`, `languages`, `evals`, `tracing`); the design names no list for M1.
- 2026-11-01: The adapter returns Whisper's text as it comes. The prototype's filters (its
  never-said list, the large-v3 no-speech rule, `stt.py` lines 36-54 and 68-72) change a
  measured outcome, so each would land later behind a setting and be measured (GP-18).
- 2026-11-01: Two M0 items stay with M0, since no M1 code depends on them: the guide's
  `contract.md` and the app's five layers (the design's 16.1). The runner moves into the app's
  layers when the plan that gives the app its layers runs.
- 2026-11-01: In the tracks, the integrator is the only writer of this plan and of
  `docs/plans/tech-debt.md` (step 14): parallel tracks would otherwise edit one file and take one
  debt number. A track's own commits leave this plan's logs to the `merge track X` commit, the one
  departure in this plan from the plans README's "How work moves" ("with that plan's logs updated
  in the same commit").
- 2026-11-01: `plan-002-integration` merges into the main branch after the code's whole-plan
  review (step 16), not at the close, so the owner records from the main checkout and the
  measurement commit is on the main branch. The agent reads the plans README's "once the whole
  plan's review is done" as that review: what follows adds data and runs, not tracks.
  Alternative: the owner records from an integration worktree; set aside to keep the owner's
  commands in the main checkout.
- 2026-11-01: Nothing a provider SDK would read from its own environment variables is left to it
  (the design's 7.3: "Other names are never read"). `GroqSTT` always passes the key,
  `groq.base_url` and the timeout: groq 0.37.1 falls back to `GROQ_API_KEY` and `GROQ_BASE_URL`
  (`groq/_client.py`, lines 77-87). `core/tracing.py` builds its `Resource` directly, never with
  `Resource.create`, whose detectors read `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME`, and
  passes the batch processor's sizes and timeouts, which otherwise come from `OTEL_BSP_*`. The
  HTTP exporter adds `OTEL_EXPORTER_OTLP_HEADERS` (or its `_TRACES_` form) to any headers it is
  given (`_resolve_headers`, `opentelemetry/exporter/otlp/proto/http/_common/__init__.py`, lines
  137-149), so passing headers does not keep them out: Track C's tests set these variables with
  monkeypatch, and one that still reaches the exporter is kept out by the track or reported as a
  debt row. All read on 2026-11-01 in the old repository's `venv` (OpenTelemetry 1.45.1); the
  versions M1 installs are read again in step 2.
- 2026-11-01: Ole5's spelling guide, with the owner's rulings (Q8), lives in the app's
  `apps/ole5-voice-agent/evals/spelling.toml` (Track D), which the matcher and `poe golden` read,
  since golden data stays in each team's repository (the design's 9.7). The guide's
  `evaluation.md` says how a team writes its own and links to Ole5's as an example.
- 2026-11-01: The design's 14 has a doc check that fails when a sample block no longer matches
  its source file; none exists in `scripts/` (a grep, 2026-11-01), and the guide's
  `evaluation.md` is the first page with code samples. The check is deferred: a debt row, written
  at Track H's merge, and until it exists a reviewer compares each sample with its source file.
  Alternative: build it in Track H; set aside to keep M1's harness changes to Block 0's list.
- 2026-11-01: The recorder is a local server holding the owner's voice, a few folders from two
  `.env` files: the main checkout's (where "What the owner does", step 2, puts the key; from
  `var/golden-audio`, `../../.env`) and the old repository's, which the lab's server reads
  (`voice-lab/server.py`, line 46). So it serves only an allow-list (the replies `replies.json`
  names and the variants the manifests name), each looked up by its ID, never by a path from the
  request; it answers only a `Host` of `127.0.0.1:<port>` and requests that carry the session's
  token, which `poe record` prints in the address; and it refuses a POST from another `Origin`.
  The agent's reasoning, from the review, not tested: without these, a page open in Chrome could
  send a form POST to it, or read its audio through DNS rebinding.
- 2026-11-01: Invariant 8 ("Call audio is not stored unless a setting turns it on for the
  owner's own recordings") governs call audio in the product. The recorder is not a call: it is
  an evaluation command the owner runs on purpose, in the app and never on a call's path, writing
  only under the `--out` the owner gives, so the invariant's test of the default settings is
  unchanged. This is the agent's reading, for the security reviewer, and the owner may rule
  otherwise; the consent for these recordings is the next entry.
- 2026-11-01: Each manifest of the owner's new recordings records who spoke, that they agreed to
  the recordings' use in this golden set, and the date, as the owner confirms it in
  `poe record`; the guide's `evaluation.md` asks a team to record the same for every speaker.
  The agent's choice (it was Q6), which the owner may overrule before Block 0 fixes `models.py`.
- 2026-11-01: The six packages go into the library's one install, with no optional extras: the
  owner chose "No, one install" (D-018). D-018 leaves the owner free to choose extras for the
  exporter and the scorers later, which would change step 2's `uv add` line and make `tracing`
  and `testing` work without them (it was Q20).
- 2026-11-01: Step 2 read the installed OpenTelemetry API and SDK 1.45.2 and the HTTP exporter
  1.45.2 as text, for every `OTEL_*` variable on the tracing path; Track C works from this list.
  - **Kept out by passing a value:** `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG` (a
    sampler); `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SERVICE_NAME` and
    `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` (a `Resource` built directly, never
    `Resource.create`, which `TracerProvider` also calls when given none); the eight span limits
    `OTEL_ATTRIBUTE_COUNT_LIMIT`, `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT`,
    `OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT`, `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT`,
    `OTEL_SPAN_EVENT_COUNT_LIMIT`, `OTEL_SPAN_LINK_COUNT_LIMIT`,
    `OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT` and `OTEL_LINK_ATTRIBUTE_COUNT_LIMIT` (a `SpanLimits`
    given all eight); `OTEL_BSP_SCHEDULE_DELAY`, `OTEL_BSP_MAX_QUEUE_SIZE`,
    `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` and `OTEL_BSP_EXPORT_TIMEOUT` (all four passed to the batch
    processor); `OTEL_PYTHON_METER_PROVIDER` (read by the global `get_meter_provider`, which the
    tracer, the batch processor and the exporter call when given no meter provider); the
    exporter's `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and `OTEL_EXPORTER_OTLP_ENDPOINT`, its
    `_TIMEOUT` and `_COMPRESSION` pairs; and `OTEL_PYTHON_EXPORTER_OTLP_HTTP_CREDENTIAL_PROVIDER`
    and its `_TRACES_` form, which load an entry point unless a `requests.Session` is passed.
  - **Read whatever is passed:** `OTEL_SDK_DISABLED` (`TracerProvider.__init__`,
    `opentelemetry/sdk/trace/__init__.py`, line 1278); `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED`
    (the tracer, line 1094; the batch processor, `sdk/trace/export/__init__.py`, line 197; the
    exporter, `exporter/otlp/proto/http/trace_exporter/__init__.py`, line 169), which turns on
    the SDK's own metrics on the meter provider in use; `OTEL_PYTHON_CONTEXT`, read when
    `opentelemetry.context` is imported (`opentelemetry/context/__init__.py`, line 25), which can
    load an entry point; `OTEL_EXPORTER_OTLP_TRACES_HEADERS` or `OTEL_EXPORTER_OTLP_HEADERS`,
    added under the headers passed (`_resolve_headers`,
    `exporter/otlp/proto/http/_common/__init__.py`, lines 137-149, as in 1.45.1); and
    `OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE`, `OTEL_EXPORTER_OTLP_CERTIFICATE` and the client key
    and client certificate pairs (`_build_transport`, lines 191-204 of the same file), which a
    value keeps out only by naming a file: verifying against the default bundle cannot be passed.
  - **Off the path unless called:** `OTEL_PYTHON_TRACER_PROVIDER` (only the global
    `get_tracer_provider`), `OTEL_PROPAGATORS` (read when `opentelemetry.propagate` is imported,
    which nothing on the path imports) and the auto-configuration's variables
    (`opentelemetry/sdk/_configuration`).

  Track C keeps out each one of the second group it can, and narrows TD-005 to the rest in its
  report. Block 0's review wrote the debt rows it found as TD-002 to TD-007 (no other session
  had taken a number: the main branch's `docs/plans/tech-debt.md` ends at TD-001); the
  integrator keeps those numbers at the merge, or renumbers them and every citation in this plan
  in the same commit (step 14).
- 2026-11-01: Step 2 read the installed groq 1.7.0 as text for every `GROQ_*` variable it reads,
  the counterpart of the list above; Track B works from it (added in Block 0's review).
  - **Kept out by passing a value:** `GROQ_API_KEY` and `GROQ_BASE_URL` (`groq/_client.py`,
    lines 80-91 and 293-304).
  - **Read whatever is passed:** `GROQ_CUSTOM_HEADERS`, on every client built (lines 93-100 and
    306-313), whose headers sit under any `default_headers` given but over the `Authorization`
    header the SDK builds from the key (`groq/_base_client.py`, lines 672-680), so a value
    naming `Authorization` replaces the key, and any other header it names goes with every
    request (TD-002); and `GROQ_LOG`, read when `groq` is imported (`groq/_utils/_logs.py`,
    line 17, from `groq/__init__.py`, line 79), which calls `logging.basicConfig` and sets the
    `groq` and `httpx` loggers to DEBUG or INFO, and at DEBUG logs the request's options, audio
    included (`_base_client.py`, lines 483-496) (TD-003).

  Track B passes `default_headers` naming `Authorization`, but that alone keeps out only a line
  of the same case: the SDK merges the two as dicts whose keys keep their case
  (`{**parsed, **default_headers}`, `groq/_client.py`, lines 100 and 313), so a lowercase
  `authorization` line stays beside it and httpx sends both values (corrected in Block 0's
  second review: a probe of groq 1.7.0 against `httpx.MockTransport`, with made-up keys). So
  the request hook on the `httpx.AsyncClient` it passes drops every header outside an
  allow-list and then sets `request.headers["Authorization"]` to `Bearer` and the settings' key,
  which removes every case variant (httpx's `Headers.__setitem__`): the request carries one
  value, the key (the same probe). A hook keeps it out, so this is not left as debt. `GROQ_LOG`
  is read on import, so the tests drop it before collection (`tests/conftest.py`), and Track B
  tests it in a child process that imports `t2_agentic_voice.groq`; what it cannot keep out it
  reports, narrowing TD-002 and TD-003.
- 2026-11-01: A facade's module file is checked when `harness.toml` is loaded, as a
  HARNESS-CONFIG problem, like the rest of `[package]`; so every check, not only `poe arch`,
  refuses a facade with no module. The agent's choice: the plan names `harness_config.py` as
  the place. `[package] facades` holds full module names (`t2_agentic_voice.ports`), as
  `public` does.
- 2026-11-01: `t2_agentic_voice.testing` is not added to `[package] public` in M1: the plan's
  facades are the five public modules M1 adds, and the scorers reach apps through `evals`. When
  it becomes public is the Proposed bullet of D-019.
- 2026-11-01: The tracing entry is a new one, D-023, rather than D-002's heading pointing at
  D-018. The design's 16.3 says "The tracing path: done in D-018", and D-018 does settle the
  design's question 7 (our own spans, in OpenInference's format, rather than an instrumentor);
  but it names no package or exporter, and its consequences amend only D-002's Pipecat bullet,
  so D-002's tracing bullet ("Arize Phoenix through `arize-phoenix-otel` and OpenInference")
  still stood. The agent's reading.
- 2026-11-01: The settings' validation, the agent's choices in step 8, each for the security
  reviewer: a group's misspelt key is an error (`extra="forbid"`; the top level still ignores
  unknown keys, as before); no settings error echoes the value it rejected
  (`hide_input_in_errors`, GP-19), so a key pasted into the wrong setting is never printed;
  `groq.base_url` is HTTPS only, since the key travels with every request, and neither URL may
  hold a user name or password; `stt.model` is one of the two Whisper models; `tracing.redact`
  holds regular expressions, each compiled when the settings load; `tracing.endpoint` may be
  plain HTTP, for a Phoenix on 127.0.0.1.
- 2026-11-01: Reading the key file is a settings method, `GroqSettings.resolved_api_key()`: the
  key, else the key file's contents, with the space around them removed, else none (a blank
  value counts as unset); a file that cannot be read raises `ConfigurationError` naming
  `T2V_GROQ__API_KEY_FILE`, with neither its path nor its contents. Track B's `from_settings`
  calls it and raises the `ConfigurationError` naming `T2V_GROQ__API_KEY` when it returns none.
  The agent's choice: the design's 7.3 gives every secret a `_FILE` form, so the reading belongs
  with the settings, and `poe eval --show-settings` (Track E) shows set or not set from it.
- 2026-11-01: `ProviderError` has one stable code, `provider_error`, and its `kind`; its
  message is fixed per kind and never holds the provider's text, which may echo the request;
  it refuses a retryable `rejected`, and a `retry_after_s` that is negative, not finite, or on
  an error that is not retryable. The agent's choices.
- 2026-11-01: Block 0's library signatures, the agent's choices, which the tracks build to; a
  track that needs one changed asks the integrator, since another track builds against it:
  - `wer(references, outputs)` and `cer(references, outputs)` take two sequences and pool
    them, since a stratum's rates are pooled (errors over all its references' length); one pair
    is a list of one.
  - `term_recall(reference, output, terms)` and `id_recall(reference, output)` return a
    `Recall(expected, found)`, counts that add up over a stratum; `silence_output(output)` is
    the characters produced, after normalization and with spaces removed.
  - `spelling_issues(reference, rules)` takes the team's `SpellingRule`s (an id, the spellings
    to avoid, what to write, the ruling's words and date) and returns `SpellingIssue`s.
  - `sign_test(better, worse)` returns the two-sided p-value.
  - `GroqSTT(api_key=, model=, base_url=, timeout_s=)`, `GroqSTT.from_settings(settings)`,
    `transcribe` as the port's, and `aclose()`; Track B may add a keyword argument for its fake
    transport.
  - `Tracing.from_settings(settings, tracer_provider=None)`; `turn(session_id=, name="turn")`,
    a context manager giving the root span; `speech_to_text(parent, model=, language=,
    audio_seconds=)`, giving a `SpeechToTextSpan` whose `record(text=, language=,
    billed_seconds=)` adds what came back; `dropped_spans`; `shutdown()`. The parent is an
    OpenTelemetry `Span`, so a team's own span can be one.
  - `Redactor(patterns, replacement="[redacted]")`, called on a text.
- 2026-11-01: The types two tracks share live in modules of Block 0's own,
  `domain/text/rulings.py` and `domain/recall.py`, not in the tracks' files the plan names, so
  every file keeps one owner ("Parallel tracks": a file two tracks need goes into Block 0).
- 2026-11-01: `models.py`'s choices, the agent's, which Tracks D to G build to (a change goes
  through the integrator; since the review, the models sit in `models.py`, `runs.py` and
  `takes.py`, and the review's additions are its entry at the end of this log):
  - an item's `kind` is a snake_case name, not a closed list, since Track D maps the lab's
    kinds (`sentence`, `backchannel`, `command`, `confirm`, `request`, `unscripted`: `refs.json`,
    read 2026-11-01) and Q4 may change the script's; `strata.toml` and its test hold the kinds
    used. `language` is one of `saudi`, `msa`, `english`, `mixed` and `none`, `device` (the
    microphone) one of `laptop`, `wired` and `bluetooth`, and `split` `dev` or `held-out`;
  - a variant holds one or more segments (a take the detector split in two), its reference
    and where it came from (`script`, `typed`, `none`), its confirmations (each with its
    review pass), its turn ends and its tags;
  - every path below a root is relative, with `/` and no `..`, refused otherwise as it is read,
    so no manifest or request names a file outside its root (for the recorder's allow-list);
  - a review is a model of its own, `Review`, written as a new file, since the recorder never
    rewrites a file, and a take's sidecar cannot then take its confirmations;
  - a request's `outcome` is `ok`, `stuck` or one of `ProviderError`'s kinds, which a test keeps
    equal to the library's list;
  - a scorecard says `one speaker` in a field that can hold nothing else (D-006), and a held-out
    run's holds no variant;
  - a history line holds the run's billed seconds as well as its cost, since step 20 adds up
    the spend so far from the history.
- 2026-11-01: The recorder's page files (`recorder_page/index.html`, `recorder.js`) get no stub:
  they are not Python, and no other track reads them; Track G creates them.
- 2026-11-01: A stub whose constructor raises is tested past it with `__new__`, and each
  command's `if __name__ == "__main__"` line is run by its `--help` test through `runpy`, so the
  coverage floor holds with no `pragma: no cover`. `FakeTracing` subclasses `Tracing`, so a
  runner typed with the library's class takes it.
- 2026-11-01: Block 0's review fixes, the agent's choices, each from a finding checked by an
  agent told to refute it (the progress log):
  - The shell's variables are dropped in a `pytest_configure` hook of `tests/conftest.py`, which
    runs before any test module is imported, as well as by the session fixture; a check placed
    above the conftest's imports would trip ruff's E402, and the conftest's one import loads
    neither SDK.
  - ARCH-WORDS reads the path below `[package] root` of every file outside `__pycache__/`, and
    the text of the listed types only (`.pyi` is not added), so a module, folder or asset named
    after an app is caught whatever its type, as ARCHITECTURE.md says.
  - Settings, adding to step 8's choices: a key, from the setting or its file, is printable
    ASCII with no space, else a `ConfigurationError` naming the setting it came from, never the
    value (a key with a line break fails in the HTTP client, whose error holds the whole header
    and reads as a lost connection); a key file is read as `utf-8-sig`, so a byte-order mark is
    dropped; a URL setting's port is checked at load (1 to 65535), and a bad port or `[host]`
    gives fixed text, since urllib's repeats the value; `groq.base_url` holds no query or
    fragment, since the SDK puts its path after it; `stt.timeout_s` is finite. A key file that
    cannot be read, and a URL urllib refuses, fail after the handler, so no exception chain
    holds the file's bytes (a decode error keeps them) or the value, even out of sight.
  - `Settings.from_env(env_file=None)`, the name the design's 7.4 gives the loader: it loads the
    settings, and any failure is a `ConfigurationError` naming each failing setting and why,
    with a FIX line, raised after the handler, so no exception chain leads to the
    ValidationError; `get_settings()` loads through it. This narrows step 8's entry above: a
    ValidationError's text and repr never show the rejected value, but its `errors()` and
    `json()` still do by default, so a command reports settings errors only through `from_env`
    (Track E's `--env-file` included). An `env_file` given that is no file (after `~` is
    expanded, as pydantic-settings expands it) is a `ConfigurationError` with fixed text and a
    FIX line, `details` `{"setting": "env_file"}`, raised before loading: pydantic-settings
    skips a missing env file silently, so a mistyped `--env-file` would run on the defaults
    (GP-06; added in Block 0's second review).
  - `ProviderError` rebuilds through its constructor when pickled or copied, keeping every
    attribute, notes included.
  - `parse_wav` turns `wave`'s bare RuntimeError (a chunk past the RIFF chunk's end) into
    `AudioFormatError`, and refuses a file with no samples, as the models' `seconds > 0` would
    later.
  - A path below a root also refuses an empty or dot-only part, a part ending in a dot or a
    space, a control character, `*?"<>|`, and Windows' device names with any extension, from a
    list kept by hand (`os.path.isreserved` needs Python 3.13).
  - The app's models are split, so each module stays under ARCH-SIZE: `models.py` (the golden
    set: items, variants, manifests, the split file, and the field types), `runs.py` (what a
    run produces, and the answerer, matcher and scorecard-writer protocols) and `takes.py` (the
    recorder's files). All three are Block 0's, as `models.py` was. Every model hides the input
    it refuses (`hide_input_in_errors`).
  - Held-out and secrets in the models: a held-out run is never traced (`RunInfo`), a held-out
    scorecard holds no variant and every scorecard's variants are of its run's split
    (`Scorecard`, which also catches a run made by `model_copy`, as reading does); a setting
    whose dotted name ends in `key`, `api_key`, `secret`, `token` or `password` is shown only as
    `set` or `not set`, in a run and in its history line, by a pattern kept private in
    `runs.py`, since the app's code never imports the tests.
  - What the tracks pass each other, named in the models: each `Window` carries its measures
    (empty, words heard, leading words, whether a one-word reference is held), which Track E
    takes with `windows.py`; `WindowMetrics`, one per window length, language and `want`, as
    sums, on `Scorecard.windows` (a held-out run keeps these); `want` on `Item` and
    `VariantResult` (a `Name`, never a list of its values, one of which is a one-word
    reference); the item's terms on each `VariantResult`; `TICKET_KIND = "ticket_number"`; a
    run's `price_per_hour_usd`, required on `RunInfo` and `HistoryLine`, so step 20's spend has
    a named source and a forgotten price is an error, not a cost of 0; `SCORECARD_FILE`; a
    window-only run's results have `judged` false and no verdict, `Answer.text` None, and are
    not failures; `Answer` keeps Whisper's confidence and each segment's own answer (for a
    variant of several segments, the top-level values are the segments', weighted by length,
    as the prototype weights Whisper's segments, `stt.py`, `_by_length`), so the prototype's
    silence rule can be scored again offline (Q2's purpose).
  - The committed split's shape is `models.SplitFile`, read by `split.load_split` (Track D);
    `script.toml` is `takes.Script` (`listening_sounds`, then `[[lines]]`), read by
    `takes.load_script`; each recording session writes `session.json` (`takes.SessionRecord`,
    the speaker's consent), which the import copies into the manifest; below `--out`, a
    session's folder holds `session.json` and each take's `<take>.wav`, `<take>.json` and
    `<take>.review-<pass>.json`, named by `takes.py`'s helpers, which refuse a name that is no
    plain file.
  - The fakes add `FakeGoldenSet` (the items and the split), `FakeHistory` and `FakeScorers`
    (preset values, scoring nothing themselves, so they cannot drift from Track A's).
  - A run covers one split: `poe eval` takes `--split dev` or `--split held-out`, as every
    registered run does, and step 15 runs the reference answerer once on each, rather than adding
    a whole-set scope no registered run uses. The reference answerer sends no request and
    measures no model, so its held-out runs, in step 15 and in `test_reference_answerer.py`
    inside every `poe check`, are not among the held-out runs Q18 caps; it appends no history
    line (the entry on the `reference` answerer above), and `test_reference_answerer.py` writes
    only into temporary folders, so no held-out line of step 15 reaches the committed
    `history.jsonl`.
  - `requests` is a direct dependency of the library (`uv add --package t2-agentic-voice
    "requests>=2.34.2"`, already locked at that version, Apache-2.0: no new package or licence)
    with an `[[owners]]` row of its own for `core`, since only a `requests.Session` passed to
    the exporter keeps the credential-provider variable out (the OpenTelemetry list above).
  - The library's strings hold no talk-over reference as a whole word: `ProviderError`'s
    messages say "delay", `Tracing.shutdown` says "close", and `domain`'s docstring describes
    stop words in other words. The no-item-in-source test would otherwise fail on files Track D
    does not own.
  - `wer`, `cer` and `term_recall` keep their signatures and raise TypeError on a bare str
    (Track A builds the guard and its test); so does a `Matcher`.
- 2026-11-01: Block 0's second review, the agent's choices (the rest are in the entries they
  change: the groq list, `from_env`, a run covering one split):
  - TD-004's fix names no track and stays the owner's or a later plan's: no Track B or C line
    asks for `trust_env=False`, and turning off the proxy variables may break a run on a network
    that needs a proxy, so it comes with a proxy setting or not at all. The lines of Tracks B
    and C are unchanged.
  - The debt rows keep the numbers the first fixes gave them, TD-002 to TD-007, since the main
    branch's tracker ends at TD-001; step 14's rule, that the integrator numbers a track's rows,
    still holds for the tracks.
  - `## Tracks` names Block 0's test files one by one, the ones the first fixes added
    (`test_runs.py`, `test_takes.py`, `tests/harness/test_import_isolation.py`) with the rest,
    so a track that needs one changed asks the integrator, as for `models.py`.
  - `requests` is recorded in D-023's Proposed bullet, which is new on this branch, as jiwer's
    owner row is in D-019, since CLAUDE.md's first non-negotiable puts a rule's reason in a
    decision.

## The owner's decisions

On 2026-11-01, in the owner's words:

- "If everything is set lets start with the first milestone".
- "Approve all": the stack (D-002), the layers (D-003), SECURITY.md (D-007), evaluation.md
  (D-011), DESCRIPTION.md, the roadmap's M1 to M7, and the package design as amended (D-017),
  as plan 000 records it.
- "Start M1, CI later": CI waits for a remote (TD-001).
- "Yes, as the plan lists", to the agent's question "M1 needs new packages from PyPI: the Groq
  SDK, the OpenTelemetry SDK and exporter, the OpenInference conventions, jiwer (word error
  rate), and a reader for audio files; plus Phoenix to see the traces. All are on the licence
  list you accepted. May I download them?" The answer's stated meaning: "M1's plan names each
  package and its version before it is installed; installing them needs no further question."
  So step 2 installs "Dependencies to install" with no further question, and the owner runs
  Phoenix through `uvx`. No audio reader is installed (the standard library's `wave` does it).
  A package whose licence is outside that section's table, certifi among them (Q1), goes to the
  owner first, since the question said every package was on the accepted list.

On 2026-11-01, the owner's answers to the calls before Block 0 (the option each chose, in the
agent's words of the question):

- Q1, certifi under MPL-2.0, used unmodified: "Accept it".
- Q2, keeping Whisper's `no_speech_prob` as an optional field of `Transcript`: "Keep it".
- Q3, whether "Approve all" covers the decision entries for what the approved design already
  describes: "Yes, as Accepted", with the agent's note that anything beyond the design is
  written as Proposed.
- Q8, Ole5's spelling guide: "Use these rules", for these rules as the agent put them:
  - Before comparing, both texts are normalized: the Arabic letter forms folded as the
    prototype did (أ إ آ to ا, ة to ه, ى to ي, ؤ to و, ئ to ي); no diacritics and no tatweel;
    Arabic-Indic digits read as 0 to 9; English lowercase; punctuation ignored; spaces ignored
    in the verdict, so two words written as one still count.
  - References are written with product terms in Latin script, as the product writes them
    (Outlook, PDF, Word); numbers as digits, and digits said one by one («خمسة سبعة») count as
    those digits; English contractions as said ("don't" stays "don't"); listening sounds from
    a fixed list that comes with the script (such as «اها», «امم», "mm-hmm").

Earlier words this plan rests on, all of 2026-10-28 (D-004, D-006, D-010):

- "Also for now I can only use the Groq API key, we can not try other models for now."
- "For Phase 0, I do not have the ability to gather data other than my own. I am the only one
  working in this repo."
- "You can use the old (Jooris) repo to help you initiate the new one."

## Dependencies to install

All go to the library's one install (D-018), in one command from the repository root, with the
lock in the same commit; the owner allowed them on 2026-11-01 ("The owner's decisions"):

```
uv add --package t2-agentic-voice "groq>=1.7.0" "opentelemetry-api>=1.45.2" "opentelemetry-sdk>=1.45.2" "opentelemetry-exporter-otlp-proto-http>=1.45.2" "openinference-semantic-conventions>=0.1.43" "jiwer>=4.0.0"
```

| Package | Constraint | Licence | Member | Owning layer (`[[owners]]`) | Why M1 needs it |
| --- | --- | --- | --- | --- | --- |
| `groq` | `>=1.7.0` | Apache-2.0 (the design's 13, checked on 1.7.0; PyPI, read 2026-11-01) | `t2-agentic-voice` | `adapters` (`groq`, already in `harness.toml`) | `GroqSTT` calls Whisper through it |
| `opentelemetry-api` | `>=1.45.2` | Apache-2.0 (the design's 13; PyPI, read 2026-11-01) | `t2-agentic-voice` | `core` (`opentelemetry`, already listed) | The span helpers |
| `opentelemetry-sdk` | `>=1.45.2` | Apache-2.0 (as above) | `t2-agentic-voice` | `core` (`opentelemetry`) | The private `TracerProvider` and its bounded batch processor; tests use its in-memory exporter |
| `opentelemetry-exporter-otlp-proto-http` | `>=1.45.2` | Apache-2.0 (as above) | `t2-agentic-voice` | `core` (`opentelemetry`) | Plain OTLP over HTTP to Phoenix (`/v1/traces` on port 6006) |
| `openinference-semantic-conventions` | `>=0.1.43` | Apache-2.0 (the design's 13; PyPI, read 2026-11-01) | `t2-agentic-voice` | `core` (`openinference`, already listed) | The attribute names of our own spans (D-018, question 7) |
| `jiwer` | `>=4.0.0` | Apache-2.0 (the design's 13; PyPI, read 2026-11-01) | `t2-agentic-voice` | `testing` (a new `[[owners]]` row, step 3) | `wer` and `cer` |
| `requests` | `>=2.34.2` | Apache-2.0 (installed metadata, step 2) | `t2-agentic-voice` | `core` (its own `[[owners]]` row, Block 0's review) | The exporter's `requests.Session`, which keeps the credential-provider variable out; locked with the exporter before it was declared (the decision log) |

Facts read on PyPI on 2026-11-01 by the research step: groq 1.7.0 (uploaded 2026-08-26) needs
anyio, distro, httpx (below 1), pydantic (below 3), sniffio and typing-extensions; the three
OpenTelemetry packages are at 1.45.2 and move in lockstep (the SDK pins the API, and the HTTP
exporter, uploaded 2026-10-29, pins its own protocol packages and needs requests and
googleapis-common-protos); openinference-semantic-conventions 0.1.43 (uploaded 2026-10-29) has
no dependencies; jiwer 4.0.0 (uploaded 2025-06-19) needs click and rapidfuzz. All support
Python 3.12. None of them pulls numpy.

**Indirect packages** that come with them. No layer imports them, so they get no `[[owners]]`
row. Their licences below are the agent's memory, as written before step 2; the installed
metadata, read in step 2, agrees with each (the progress log):

| Package | Comes with | Licence (checked in step 2) |
| --- | --- | --- |
| `httpx`, `httpcore`, `idna` | groq | BSD-3-Clause |
| `anyio`, `h11`, `sniffio` | groq | MIT (`sniffio`: MIT or Apache-2.0) |
| `distro` | groq | Apache-2.0 |
| `certifi` | httpx, requests | MPL-2.0: accepted by the owner on 2026-11-01, used unmodified (Q1) |
| `click` | jiwer | BSD-3-Clause |
| `rapidfuzz` | jiwer | MIT |
| `opentelemetry-semantic-conventions`, `opentelemetry-proto`, `opentelemetry-exporter-otlp-proto-common` and the exporter's other `opentelemetry-*` packages | the OpenTelemetry packages | Apache-2.0 |
| `protobuf` | opentelemetry-proto, googleapis-common-protos | BSD-3-Clause |
| `googleapis-common-protos` | the HTTP exporter | Apache-2.0 |
| `urllib3`, `charset-normalizer` | requests | MIT |

Already locked and unchanged: pydantic, typing-extensions, colorama (`uv.lock`, read
2026-11-01).

**Not installed:**

- **Arize Phoenix** is run, never imported or added to a member (the design's 13: "Run"; Elastic
  License 2.0, accepted on 2026-11-01, D-018 question 20). It is a separate download, listed
  here so that the owner's answer covers it: `arize-phoenix` 21.0.0 (released 2026-10-30,
  Python 3.11 to 3.15; PyPI, read 2026-11-01), fetched by `uvx` into uv's own tool cache,
  outside the repository and its lock, so its heavy dependencies (numpy, pandas, pyarrow,
  grpcio and sqlalchemy among them) never reach the library's install. The owner starts it
  ("What the owner does", step 7). If it does not start natively on Windows (UNVERIFIED), the
  fallback is Phoenix's Docker image `arizephoenix/phoenix`.
- No dev tool (no pytest plugin), no audio package (the standard library's `wave` reads and
  writes the 16 kHz mono 16-bit WAV files), no num2words, no camel-tools.

## Tracks

Each track builds in its own worktree against Block 0's interfaces and the fakes in
`tests/ole5_voice/evals/fakes.py`, never against another track's unfinished code. One owner per
file; the files every track needs (settings, errors, ports, facades, `models.py`, `runs.py`,
`takes.py`, `audio.py`, poe tasks, CLAUDE.md, `harness.toml`, ARCHITECTURE.md) belong to Block
0, and this plan and `docs/plans/tech-debt.md` to the integrator, which copies each track's
report into them (step 14). Block 0's own tests and fixtures belong to it too, and no track
edits them: `tests/conftest.py` and `tests/harness/` (`test_import_isolation.py` among them);
in `tests/t2_agentic_voice/`, `core/test_config.py`, `core/test_errors.py`,
`domain/test_ports.py`, `domain/test_rulings.py`, `domain/test_recall.py`, `test_facades.py`,
`test_baselines.py` and the two files under `fixtures/`; in `tests/ole5_voice/evals/`,
`fakes.py`, `samples.py`, `test_models.py`, `test_runs.py`, `test_takes.py`, `test_audio.py`,
`test_fakes.py` and `test_commands.py`. A track that needs one changed asks the integrator.
Library paths below are under `packages/t2-agentic-voice/src/t2_agentic_voice/`; app paths under
`apps/ole5-voice-agent/src/ole5_voice/evals/`. In every track, no item's reference appears as a
whole word in a source string or page text (Track D's test reads every string constant under
`packages/`, `apps/*/src` and `examples/`): the one-word English ones are okay, stop, wait and
yeah, and `refs.json` and Track D's test hold the rest. The likely places: Track B's rate-limit
message, Track C's docstrings, Track E's progress lines, and Track G's control labels (no
"Stop" button).

**Track A · Text and scorers (library).**
- Goal: `normalize_arabic`, `normalize_digits`, the spelling-guide check (`spelling_issues`,
  which takes a team's rulings as data), `term_recall`, `id_recall`, `silence_output`,
  `sign_test`, `wer` and `cer`.
- Owns: `domain/text/arabic.py`, `domain/text/digits.py`, `domain/text/spelling.py`,
  `domain/scoring.py`, `domain/sign_test.py`, `testing/scorers.py`; tests
  `tests/t2_agentic_voice/domain/` (`test_arabic.py`, `test_digits.py`, `test_spelling.py`,
  `test_scoring.py`, `test_sign_test.py`) and `tests/t2_agentic_voice/testing/test_scorers.py`.
- May read: Block 0's stubs and characterization table;
  `Ole5-chatbot/src/ole5_chat/voice/rules.py` (lines 11-19),
  `Ole5-chatbot/scripts/stt_eval.py` (lines 1059-1086),
  `Ole5-chatbot/tests/test_voice_rules.py` (lines 10-14); evaluation.md's "Judging a change";
  jiwer's documentation.
- Tests: the characterization table; each gap the spelling guide rules on (Q8, settled before
  Block 0); Arabic-Indic and Persian digits; digits spelled one word each, in Arabic and in
  English; WER and CER against hand-computed cases, empty output included, and an empty
  reference refused with a `ValueError`, and a bare str for `references`, `outputs` or `terms`
  refused with a TypeError (with no reference words, jiwer 4.0.0 returns the
  insertion count as the WER: the feasibility review's reading of jiwer's `process.py`,
  UNVERIFIED in this repository, where jiwer is not installed yet); the sign test against
  evaluation.md's formula: b = 6, w = 0 gives 2/64 = 0.03125; b = 5, w = 0 gives 0.0625; b = w
  gives 1.

**Track B · The Groq speech-to-text adapter (library).**
- Goal: `GroqSTT`, with `GroqSTT.from_settings(settings)` raising `ConfigurationError` that
  names `T2V_GROQ__API_KEY` when neither the key nor its file is set (the design's 7.3).
- Owns: `adapters/groq_stt.py`; tests `tests/t2_agentic_voice/adapters/test_groq_stt.py`.
- May read: the ports, settings and errors; Groq's speech-to-text reference; the installed SDK as
  text; `Ole5-chatbot/src/ole5_chat/voice/stt.py` (lines 221-252: the call and the confidence
  weighted by segment length) and `Ole5-chatbot/src/ole5_chat/voice/groqhttp.py`;
  `Ole5-chatbot/tests/test_voice_stt_v2.py` as behaviour specs.
- Behaviour: PCM16 wrapped as WAV with `wave`, sent with the media type `audio/wav`; the key,
  base URL (`groq.base_url`) and timeout always passed explicitly, never none; an empty key or
  key-file value treated as unset; SDK retries off; `billed_seconds` is the larger of 10 s and the
  clip's length (Groq's documented minimum); the `DataFlow` values of the design's 6.1. The key
  also goes in `default_headers` as `Authorization`, and a request hook on the
  `httpx.AsyncClient` passed as `http_client` drops every header outside an allow-list, then
  sets `request.headers["Authorization"]` to `Bearer` and the settings' key, which removes every
  case variant, so no `GROQ_CUSTOM_HEADERS` line, in any case, replaces the key or adds a second
  one (the decision log's groq list; TD-002). Every exception the SDK raises, not only its
  `APIError`s, becomes a `ProviderError` raised `from None`, never `from error`: the SDK's
  exception chain can hold the request's headers.
- Tests (a fake transport, no network): the request's fields equal Block 0's baseline; the
  result's shape; a cancel stops within 50 ms with no pending task and the client closed; a 429
  with `retry-after`, a 5xx, a timeout, a lost connection, a 401 and a 400 each become the right
  `ProviderError`; the key appears in no repr, error or log line, even when the fake server
  echoes the request's headers in its body; `GROQ_API_KEY` and `GROQ_BASE_URL`, set with
  monkeypatch, change nothing in the request; `GROQ_CUSTOM_HEADERS`, set with monkeypatch to a
  lowercase `authorization: Bearer <made-up key>` line and an `X-Made-Up: 1` line, changes no
  header (`request.headers.get_list("authorization")` is exactly `Bearer` and the settings' key,
  and `x-made-up` is absent), and so does the same with a capitalized `Authorization` line;
  `GROQ_LOG=debug`, read on import, in a child process that imports `t2_agentic_voice.groq`: no
  root handler added and the `groq` and `httpx` loggers' levels unchanged, or the case reported
  against TD-003; an empty key raises the `ConfigurationError`.

**Track C · The tracing helpers (library, `core`).**
- Goal: tracing set up from settings, the `Redactor`, and span helpers that take the parent span.
- Owns: `core/tracing.py` and `core/redaction.py` (the `Redactor`), both stubs from Block 0;
  tests `tests/t2_agentic_voice/core/test_tracing.py` and `test_redaction.py`.
- May read: settings; the design's 10.1; [SECURITY.md](../../SECURITY.md), invariants 5 and 8;
  the OpenTelemetry and OpenInference documentation.
- Behaviour: the team's `TracerProvider` if given, otherwise a private one from
  `tracing.endpoint`, otherwise none; never `set_tracer_provider`; OpenInference attribute names;
  a speech-to-text span with audio seconds, billed seconds, model and language; transcripts only
  when `include_transcripts` is on; the redaction hook on every text attribute; a bounded queue
  and short export timeouts, whose values the track gives in its report for this plan's decision
  log; the `Resource` built directly, and every value the SDK and the exporter would otherwise
  read from an `OTEL_*` variable passed explicitly (the decision log), the exporter given its own
  `requests.Session` (`core` owns `requests`); what cannot be kept out narrows TD-005.
- Tests (the SDK's in-memory exporter): no made-up secret in any span attribute, event, status or
  resource; redaction applied; transcripts dropped when the setting is off; the global provider
  unchanged; an exporter that raises or hangs never reaches the caller, and dropped spans are
  counted; `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SERVICE_NAME` and an `OTEL_BSP_*` variable, set
  with monkeypatch, change no span, resource or queue size; `OTEL_EXPORTER_OTLP_HEADERS` reaches
  no export request, or, if the SDK cannot be kept from adding it, the track's report gives it as
  a debt row.

**Track D · The golden set: items, matcher, validation, split (app).**
- Goal: the item format, the talk-over import, the draft script of new items, the matcher, `poe
  golden`, the deterministic split, and the tests that guard the set.
- Owns: `items.py`, `toml_write.py`, `import_talkover.py`, `import_recordings.py`,
  `matcher.py`, `golden.py`, `split.py`; data under `apps/ole5-voice-agent/evals/`
  (`golden/*.toml`, `frozen.json`, `split.json`, `strata.toml`, `terms.toml`, `script.toml`,
  `spelling.toml`, `allowed_in_source.toml`, `manifests/*.json`); tests
  `tests/ole5_voice/evals/` (`test_items.py`, `test_matcher.py`,
  `test_golden.py`, `test_split.py`, `test_strata.py`, `test_no_item_in_source.py`,
  `test_no_audio.py`).
- May read: `voice-lab/recordings/talkover/refs.json` and `takes.json` (read only, D-010);
  `voice-lab/static/talkover.js` (the scripted phrases); evaluation.md's "The golden set",
  "Writing items" and "Splits".
- Behaviour: one item per talk-over phrase (43 phrase IDs: 40 scripted, 3 unscripted recorded
  twice each, `refs.json` read 2026-11-01), its takes as variants, each phrase's `want` label in
  `Item.want`; the import reads the lab's files and writes only into this repository;
  `import_recordings.py` reads the files of `takes.py` (each session's `session.json`, whose
  consent goes into the manifest, a session without one refused; the take sidecars; the
  reviews); `script.toml` is `takes.Script`, with its listening sounds, read by
  `takes.load_script`; `split.json` is `models.SplitFile`, read by `split.load_split`; the
  script's ticket items have the kind `models.TICKET_KIND`; the matcher's rulings each quote the
  owner's words and date (Q8), and its verdict
  compares the normalized strings with every space removed, as the prototype's `norm` does;
  a variant whose reference the owner typed counts as checked only after its second
  confirmation; `golden` hashes and checks audio with Block 0's `audio.py`, only when given
  `--audio` roots, so no test reads audio.
- Tests: as in the acceptance criteria, all on committed files and temporary folders; a word
  split in two counted right; a typed reference with no second confirmation left out and listed.

**Track E · The runner (app).**
- Goal: `poe eval` as evaluation.md's "Running" and this registration say.
- Owns: `run.py`, `answerers.py` (`reference`, `groq`, and optionally `prototype-cache`),
  `windows.py`, `worktree.py` (the linked-worktree and clean-tree checks, through `git`); tests
  `tests/ole5_voice/evals/` (`test_run.py`, `test_answerers.py`, `test_windows.py`,
  `test_worktree.py`).
- May read: `models.py`, `runs.py`, `audio.py`, the library's facades, the matcher's, the
  items', the split's, the scorecard's and the history's interfaces (through Block 0's fakes
  until their tracks merge).
- Behaviour: flags for the answerer, split, model, language hint, `--env-file`, `--var-dir`,
  `--audio`, `--out` (refused if it exists, or if it lies inside the repository and git would
  not ignore it), `--max-rpm`, `--max-attempts`, `--variant-timeout-s`, `--price-per-hour`,
  `--cap-usd` (stops between requests before the run's billed total would pass it, and marks the
  run incomplete), `--windows-ms`, `--questions`, `--tracing-endpoint`, `--note`,
  `--show-settings` (each setting resolved, the Groq base URL included, a secret only as set or
  not set) and `--smoke-only`; progress lines through `get_logger` carry identifiers, verdicts
  and timings, never a transcript (WORKING-RULES.md: "Never log secrets or user data beyond
  identifiers"), and in a held-out run only counts, with no item ID or verdict; a held-out run
  that is interrupted keeps nothing and is run again whole; the history line is appended to the
  worktree's `history.jsonl` and copied beside the scorecard. `--split` is required (a run covers
  one split); the settings load through `Settings.from_env` (`--env-file` included), whose
  error is the only one reported, never a ValidationError's `errors()`; each `VariantResult`
  carries its item's `terms` and `want`; each `Window` carries its measures, from `windows.py`;
  a run that sends only the windows marks its results `judged` false, with no verdict;
  `--price-per-hour` is the run's and the history line's `price_per_hour_usd`; the history
  line's `scorecard` is `runs.SCORECARD_FILE`.
- Tests: with the fake `SpeechToText`, a fake `git`, and temporary folders: refusal of the main
  checkout and of a dirty tree; the smoke gate; results kept after an interruption; a stuck
  variant scored as an infrastructure failure; retries and provider failures; a held-out run with
  no per-variant output, no item ID in its progress lines, and no tracing. With a made-up key, a
  temporary env file and a fake transcript: `--show-settings` prints only whether the key is set,
  never its value or the file's contents; no log or progress line of a run holds the transcript's
  text; an `--out` that exists, or that git would track, is refused before any call; `--cap-usd`
  stops a run between requests.

**Track F · Scorecards, comparison and history (app).**
- Goal: the scorecard, `poe eval-compare`, `history.jsonl` and its generated doc.
- Owns: `scorecard.py`, `compare.py`, `history.py`; `docs/generated/eval-history.md` and its row
  in `docs/generated/README.md`; tests `test_scorecard.py`, `test_compare.py`, `test_history.py`
  (the freshness test).
- May read: `models.py`, `runs.py`, the library's `evals` facade (through Block 0's
  `FakeScorers` until Track A merges), evaluation.md's "Judging a change" and "Run history".
- Behaviour: accuracy, WER, CER (over variants with a non-empty reference only), term and ID
  recall, text from silence, cost, latency (median and 90th percentile), violations (always 0: no
  canary applies to speech-to-text), breakdowns by language, device, kind and split, the window
  metrics, and "one speaker" on every scorecard; `eval-compare` refuses two runs whose recorded
  commits or data digests differ, naming the difference. Term recall from each result's
  `terms`, ID recall over the `models.TICKET_KIND` results, the cost from the run's
  `price_per_hour_usd`, the window metrics as `Scorecard.windows` (`WindowMetrics`, summed from
  each `Window`'s measures); the scorecard written as `out / runs.SCORECARD_FILE`, built with
  the constructor or `model_validate`, never `model_copy(update=...)`; a held-out run's
  scorecard holds aggregates only, which `runs.py` refuses otherwise.

**Track G · The recorder (app).**
- Goal: `poe record`, the page the owner records and listens with.
- Owns: `recorder.py`, `recorder_page/index.html`, `recorder_page/recorder.js`; tests
  `test_recorder.py`.
- May read: `takes.py` (the script, the session record, the take sidecar, the review, and the
  files' names below `--out`), `models.py`, `audio.py`; `voice-lab/assets/talkover/` (the six
  agent replies and `replies.json`, served read only for over-the-agent and echo-only items).
- Behaviour: serves on 127.0.0.1 only, answers only a `Host` of `127.0.0.1:<port>` and requests
  carrying the session's token, which `poe record` prints in the address, and refuses a POST from
  another `Origin`; serves only an allow-list (the replies `replies.json` names, the variants the
  manifests name), each looked up by its ID, never by a path from the request; picks the
  microphone and the output device; records 16 kHz mono 16-bit WAV with echo cancellation, noise
  suppression and gain control on, refusing any other format with `audio.py`'s check; stores the
  device label and the track's settings in the take sidecar; plays each take back; after a
  several-clause take, the owner marks each true turn end on its waveform; a review mode plays
  any variant beside its reference for the owner's check (Q9), and a variant whose text the owner
  typed comes back in a later pass for its second confirmation; writes new files only, under
  `--out`, never replacing one, each named by `takes.py`'s helpers; at a session's start, asks
  for the speaker's consent in their words and writes it as the session's `session.json`.
- Tests: a real server on a free port in a thread: a take saved with its sidecar; path
  traversal, an existing name, an oversized body and a file that is not 16 kHz mono 16-bit WAV
  refused; a GET for anything off the allow-list refused, and traversal from each served folder
  (an encoded `..`, an absolute path, a symlink) never reading a made-up `.env` placed where the
  two real ones sit in a temporary tree; a wrong `Host`, a missing or wrong token, and a POST from
  another `Origin` refused. The page itself is checked by running it in Chrome (WORKING-RULES.md,
  "Seeing it run"), and by the owner's first take.

**Track H · Docs.**
- Goal: the guide's `evaluation.md` (the evaluation helpers; recording your own set with
  consent; keeping audio out of git; writing your own spelling guide, with a link to Ole5's
  `spelling.toml` as an example; noise and the sign test) and the method doc's paths.
- Owns: `docs/guide/evaluation.md`, `docs/guide/README.md` (its `evaluation.md` row becomes a
  link, or DOC-ORPHAN fails), `docs/design/evaluation.md` (its paragraph on where the commands
  and tests live).
- May read: the design's 9.7 and 14, evaluation.md, Track A's signatures.
- Tests: `poe docs`; code samples on the page come from tested files (the design's 14), compared
  with them by review until a sample check exists (the decision log; a debt row in the track's
  report).

**Reviewers, by concern.** Each reviews every track for its concern; each finding is checked by
an agent told to refute it before it is acted on.
- **Security:** invariants 5 and 8 (the key only from settings, a `SecretStr`, in no repr, log,
  trace or error; transcripts the only content in traces); held-out never traced, and its
  progress lines counts only; the recorder bound to 127.0.0.1, checking its `Host`, token and
  `Origin`, serving only its allow-list, and writing only new files under its `--out`; no
  `GROQ_*` or `OTEL_*` variable read; Phoenix bound to 127.0.0.1; no audio in git; tests that
  never see `.env`, `var/` or a `GROQ_*`, `OTEL_*` or `PHOENIX_*` variable from the shell (a
  test sets made-up ones with monkeypatch); adversarial tests present (GP-08).
- **Harness:** layers, owners, facades, ARCH-FACADE, ARCH-WORDS and ARCH-PUBLIC; DOC-REF and
  DOC-MILESTONE; test isolation (GP-15); the coverage floor; module sizes; LF endings; CLAUDE.md
  within its cap.
- **Faithfulness:** each port beside its prototype source (the normalizer, CER, the Groq call,
  the confidence, the rate-limit wait); the runner against evaluation.md's "Running", "Splits",
  "Judging a change" and "Run history"; the request baseline.
- **Measurement:** the runs follow this registration as written; the arithmetic; each
  scorecard's totals recomputed from its per-variant rows; the one-speaker label.

## The measurement, registered before any result

Written on 2026-11-01, before any run. Amendments are dated and made before the result they
affect; every open question below is settled, in the owner's words and dated, before the run it
affects. Facts are cited with their source; the agent's proposals and expectations are marked
as such.

**The data**

- **Talk-over (T).** The 124 segments in `voice-lab/recordings/talkover/`, read in place:
  16 kHz mono 16-bit WAV, 0.928 to 4.352 s each, 251.6 s in all, from 120 takes (116 with one
  segment, 4 split into two), recorded in one session on 2026-10-27 between 18:18 and 18:54
  (`refs.json`, read 2026-11-01; `Ole5-chatbot/VOICE_LOG.md`, lines 363-364). Labels: Arabic
  103, English 21; 43 phrases (34 Arabic, 9 English); 110 segments over the assistant, 14 not;
  condition "duck" 65, "pause" 59; every segment from the laptop's microphone array, 121 with
  the assistant on the laptop speakers and 3 on a headset (`mic_label`, `device`). Segment files
  begin with the detector's 300 ms of padding before speech (`takes.json`, `preSpeechPadMs`).
  Twelve Arabic segments hold an English product term in Latin script (Outlook, PDF, Word, and
  the word English).
- **New recordings (N).** The items of the approved script (Q4), each recorded once on each of
  three devices: the laptop's speakers and microphone, a wired headset, a Bluetooth headset. The
  agent's proposal, for the owner to change:

  | Kind | Saudi | MSA | English | Mixed | Items |
  | --- | --- | --- | --- | --- | --- |
  | A request of one clause, some with product terms | 6 | 4 | 4 | 4 | 18 |
  | A request of several clauses that pauses mid-sentence (a whole take, turn ends labelled) | 4 | 2 | 2 | 2 | 10 |
  | A stop word | 3 | 1 | 2 | — | 6 |
  | A repeat request | 2 | 1 | 1 | — | 4 |
  | A listening sound | 3 | — | 2 | — | 5 |
  | A ticket number read out (for ID recall) | 2 | 1 | 1 | — | 4 |
  | Silence, or a noise with no speech | — | — | — | — | 3 |
  | The agent's own echo only (a reply plays; the owner says nothing) | — | — | — | — | 2 |

  That is 52 items, 156 clips. Ticket numbers and echo-only items are not in the roadmap's list,
  but evaluation.md measures "recall of product terms and ticket numbers" and "text produced
  from silence or from the agent's own echo" (its "In this project"), so the agent adds them.
- **Strata:** language (Saudi Arabic, MSA, English, mixed, none), device (by microphone), kind,
  and for T the condition and whether the assistant was playing. The registered counts per
  stratum go into `strata.toml` once the script is approved, and a test enforces them.

**Items, variants and the split**

- An item is one scripted utterance (a talk-over phrase, or a script line); its variants are its
  recordings on each device and in each take (evaluation.md, "Items and splits here").
- About 30% of the items are held out, stratified by language and kind, split by item with a
  salted order, committed with a `--check` mode. Session hold-out cannot apply to T, which is one
  session; whether the item or the session wins for N is Q10.
- Tuning on dev only. Held-out runs write aggregates only and are never traced.

**The independent check of each reference**

- The reference is the variant's transcript under the spelling guide: the script's text for a
  scripted item, the owner's typed text for an unscripted one (`voice-lab/server.py`, lines
  329-344), and the empty string for silence, noise and echo-only items.
- The check, written another way: the owner listens to the variant and confirms that it says the
  reference (the agent's proposal, Q9). When the owner types what was said instead, the typed
  text becomes the variant's new reference, and its check is a second, separate listen against
  that text in a later review pass; a variant not confirmed so is left out and listed, since a
  reference and a check made in one act would agree by construction. `poe golden` accepts a
  variant only when the two agree. The whole talk-over set is 251.6 s of audio, so one listening
  pass is short.

**The arms**

- **A1:** `GroqSTT` with `whisper-large-v3`; `language` from the item's label (`ar` for Saudi,
  MSA and mixed, and for items with no speech; `en` for English); no prompt; `temperature` 0;
  `response_format` `verbose_json`; SDK retries off; `stt.timeout_s` 6.
- **A2:** the same with `whisper-large-v3-turbo`.
- Both at one commit (the measurement commit, after step 19), each run alone, with every setting
  on the command line; every run, W and H included, starts from the run worktree at that commit
  (step 21), whatever the main branch gains meanwhile, step 25's default included. The language
  hint from the label is close to what the prototype found best (forced language with its own
  prompt hint: 32 of 35 against 23 of 35 with auto-detection, `Ole5-chatbot/VOICE_LOG.md`,
  line 33, D24), though the arms send no prompt, and a live call does not know the label;
  whether to add an auto-detect arm is Q14.
- **The runner's settings, the same for every run** (the agent's proposal): `--max-attempts 4`,
  as the prototype's `transcribe_one` tried each utterance up to 4 times
  (`Ole5-chatbot/scripts/stt_eval.py`, lines 708-711); `--variant-timeout-s 120`, above 4
  attempts of 6 s plus 3 rate-limit waits of 20 s (84 s), so only a longer `retry-after` or a
  hang reaches it; `--max-rpm 20`, or the key's own per-minute Whisper limit if the owner reads
  one in the console (Q16), registered as a dated amendment before R1; `--price-per-hour 0.111`
  for large-v3 and `0.04` for turbo ("The cost and the time"); `--cap-usd` as step 20 sets it;
  `--split dev` for R and W runs and `--split held-out` for H; `--windows-ms` with the run's one
  length (500, 750 or 1000) for W1 to W6 only; no `--tracing-endpoint` except in run P. Any
  change is a dated amendment before the run it affects.
- No vocabulary prompt in M1: a prompt is tuning, and evaluation.md's "Noise" measures the noise
  before anything is tuned. A prompt arm is registered later as an amendment, before its run.

**The metrics**

- **The verdict per variant:** right when the output equals the reference (or an accepted
  alternative) after `normalize_arabic` and `normalize_digits` and the matcher's rulings, both
  compared with every space removed, as the prototype's `norm` does (`stt_eval.py`, lines
  1062-1066 and 1085). For an item with an empty reference, right when the output is empty after
  normalization.
- **Per item:** its net over its variants between two runs, for the sign test.
- **Reported beside it,** overall and by language, device, kind and split: the exact-match rate;
  WER and CER pooled over the stratum's variants with a non-empty reference (errors over
  reference length; CER after removing spaces), so the `none` language and the silence, noise and
  echo-only items have none and are reported by text from silence alone; the pooled CER is not
  comparable with the prototype's, which is capped at 1 per variant and taken against the closest
  accepted reference (lines 1079-1086); term recall over items with product terms
  (`terms.toml`); ID recall over ticket-number items; text from silence (the share of
  empty-reference variants with any output, and its characters); requests, attempts and provider
  failures; latency per request (median and 90th percentile); billed seconds and cost.
- **The hard constraint:** none applies to speech-to-text; violations are reported as 0, with
  that reason on the scorecard.
- **Windows:** for each registered talk-over clip, model and window length W of 500, 750 and
  1000 ms, cut from the start of the segment file (so about W − 300 ms after the detector's
  speech start), the transcript is kept, with: empty or not; words heard after normalization;
  how many leading words match the reference in order; and, for references of one word, whether
  the window holds it. For a take split into two segments, the window is cut from its first
  segment file. A window at least as long as its clip is not sent again; that clip's
  result from the same model's first dev run is used and marked so. A held-out clip's window
  results, if Q15 takes all 124, are written as aggregates only. M1 reports these by window
  length, language and the segment's `want` label; M3 chooses its window from them, and confirms
  it on a fresh run (evaluation.md, "Fitted, then fresh").

**The runs**

| Run | Arm | Data | Purpose |
| --- | --- | --- | --- |
| S (before each run) | the run's arm | one dev variant | the smoke test: no failed, retried or refused call |
| P | A1 | one dev variant, traced | the tracing check in Phoenix |
| R1 | A1 | dev (T and N) | the baseline |
| R2 | A2 | dev | the baseline |
| R3 | A1 | dev | the noise of A1 (with R1) |
| R4 | A2 | dev | the noise of A2 (with R2) |
| W1 to W6 | A1 and A2 at 500, 750, 1000 ms | the registered talk-over clips (Q15) | the window data for M3 |
| H1, H2 | A1, A2 | held-out (T and N) | aggregates for the report; the cap is these two (Q18) |

The order A1, A2, A1, A2 lets any drift over the session fall on both models alike. The
baseline comparison is R2 against R1, its replication R4 against R3, and the noise R1 against
R3 (A1) and R2 against R4 (A2).

**The noise**

- For each model, its two identical runs are compared variant by variant: the variants whose
  verdict changed, and the items better (b) and worse (w) by their net.
- The smallest change one run can detect: the smallest number c of items that, added on one side
  to the measured noise split evenly, gives p < 0.05 by the sign test: b = c + ⌊d/2⌋ and
  w = ⌈d/2⌉, where d is the number of items the noise changed. With no noise, c = 6: b = 6,
  w = 0 gives p = 2/64 = 0.031, while b = 5, w = 0 gives 2/32 = 0.0625. Both numbers, per model,
  become a decision entry and a tech-debt row ("one run is one sample; repeated runs are the
  lasting fix").
- **The check before reading a comparison:** a model change reaches every clip, so there is no
  untouched slice; the identical-run comparison plays its part. If either model's two runs
  differ by p < 0.05, the runs are unreliable: this is said, and the model comparison is not
  read.

**The keep and reject rule for `stt.model`**

- The comparison: R2 (turbo) against R1 (large-v3) on dev with `eval-compare`; R4 against R3 as
  the replication. Provider failures are left out of both runs and listed.
- First, the check above: if either model's two runs differ by p < 0.05, the default stays
  `whisper-large-v3`, the owner is told, and any rerun is registered as a dated amendment, within
  the cap, before it runs.
- turbo is better beyond the noise (p < 0.05 in its favour in both comparisons) and no language
  or device stratum is worse beyond the noise: the default becomes `whisper-large-v3-turbo`.
- large-v3 is better beyond the noise in both comparisons: the default stays
  `whisper-large-v3`.
- Anything else (no difference beyond the noise, or the two comparisons disagree): Q13.
- **The stratum guard, exactly** (the agent's proposal): for a language stratum, the sign test by
  item over that stratum's items, each item's net taken over all its variants; for a device
  stratum, over the items with a variant on that device, each item's net taken over its variants
  on that device only. "Worse beyond the noise" is p < 0.05 with more items worse under turbo
  than better, in either comparison. A stratum with fewer than 6 changed items cannot reach
  p < 0.05 (b = 5, w = 0 gives 0.0625), so the scorecard lists it as too small to guard; if such
  a stratum has more items worse under turbo than better in both comparisons, the case goes to
  the owner (Q13) instead of moving the default.
- The default moves in its own commit, citing this rule and the history lines (GP-18).

**Expected outcomes** (the agent's expectations from the prototype's runs, whose code is
unidentified: sizes are indicative)

- large-v3 ahead of turbo on Arabic over the assistant. The prototype's D52 route
  (`Ole5-chatbot/VOICE_LOG.md`, line 60) sent the Arabic call on clips of 1.8 s or more, and both
  calls on shorter clips begun over the assistant, to large-v3, kept English on turbo, and made
  two calls per segment with prompt hints (D24, line 33), so it is not arm A1. On the Arabic
  sentences over the assistant, its exact matches went from 3 to 8 of 57 takes and CER from
  0.301 to 0.285 (`voice-lab/eval/final-talk/report.md`, lines 73-74); over its whole talk-over
  set, from 46 to 56 of the report's 141 judgements and CER from 0.337 to 0.309 (lines 79-80),
  about 7 more right of every 100 judgements. On English and on quiet new recordings, no
  difference beyond the noise: the prototype found both models "fine on clean Arabic and on
  English" (`Ole5-chatbot/VOICE_V2_PLAN.md`, line 32).
- Exact matches on talk-over well under half: 46 of 141 judgements for the prototype's baseline,
  its defaults on turbo with two calls and hints ("Every default in code is still turbo", D52),
  where the report counts "120 takes (141 judged with the conversation language)"
  (`voice-lab/eval/talk1/report.md`, lines 6 and 79).
- The Bluetooth headset worst on Arabic (`Ole5-chatbot/VOICE_LOG.md`, lines 112-114).
- Few verdicts change between identical runs: 3 segments changed their words or outcome between
  the prototype's two baseline runs, a count the report gives with no denominator
  (`voice-lab/eval/talk1/report.md`, line 86); so c near its floor of 6 items.
- Short words often misheard, and short windows often empty or partial: «وقف» came back
  as «وغف» and «تمام» as "Tama" in the prototype's mic lab
  (`Ole5-chatbot/VOICE_LOG.md`, lines 167-173).
- Some text from silence and noise: the prototype saw short noises come back as «شكرا» and
  "Thank you." (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, line 73).

**The cost and the time** (the arithmetic of the agent's estimate)

Facts used:
- Groq bills at least 10 s per transcription request; whisper-large-v3 costs $0.111 and
  whisper-large-v3-turbo $0.04 per hour of audio (console.groq.com/docs/speech-to-text and
  console.groq.com/docs/models, read 2026-11-01; the 10 s minimum also in the design's 10.4).
- Every talk-over segment is under 10 s (`refs.json`), so each is billed 10 s; so are the
  windows.
- Rate limits: 20 requests a minute per Whisper model, with 2K requests a day, 7.2K audio
  seconds an hour and 28.8K a day, in the table of console.groq.com/docs/rate-limits (read
  2026-11-01; which plan it belongs to is UNVERIFIED); the prototype's key was on Groq's
  on-demand tier, 400 requests a minute (`Ole5-chatbot/VOICE_LOG.md`, line 361). The key's real
  limits are read in the console (Q16).
- Latency per request in the prototype's stored calls: median 292 ms for turbo and 295 ms for
  large-v3 (`voice-lab/eval/_cache/calls.jsonl`, 1555 answers, computed by the inventory on
  2026-11-01).

Requests, with T = 124 segments and N = 156 clips (the proposed script), so 280 requests for the
whole set, of which dev is about 0.7 × 280 = 196 and held-out about 84 (exact once the split is
committed):
- R1 to R4: 4 × 196 = 784.
- W1 to W6 on dev talk-over: about 0.7 × 124 ≈ 87 clips × 3 lengths × 2 models = 522.
- H1, H2: 2 × 84 = 168.
- Smoke tests: one before each of the 12 runs = 12; the tracing check: 1.
- In all: 784 + 522 + 168 + 12 + 1 = 1,487 requests, 743 or 744 per model.

Cost, every request billed the 10 s minimum: 743 × 10 s = 7,430 s = 2.064 h per model; large-v3
2.064 × $0.111 = $0.229, turbo 2.064 × $0.04 = $0.083; with the tracing check's one request,
about **$0.31**. The ten several-clause items may run past 10 s: if each of their 30 clips were
billed 30 s (an assumption for the estimate; the longest talk-over raw take is 27.65 s, measured
by the inventory with `wave`), they add at most 30 × 4 runs × 20 s = 2,400 s = 0.667 h, half per
model: $0.037 + $0.013 = $0.05, so about **$0.36** at most. Whether a refused request is billed
is UNVERIFIED, and retries after a 429 add requests, so spend may pass this estimate. The owner
sets the budget cap before the first run that spends (Q17), and step 20's check and `--cap-usd`
hold it.

Time:
- At 20 requests a minute: 1,487 / 20 ≈ 74 min of pacing in all; a dev run 196 / 20 ≈ 10 min.
- If the 7.2K audio seconds an hour count billed seconds (UNVERIFIED): 7,200 / 10 = 720 requests
  an hour, 12 a minute; then 1,487 / 12 ≈ 124 min in all, and one dev run ≈ 16 min. The daily
  limits hold either way: 744 requests and at most 744 × 10 + 1,200 = 8,640 billed seconds per
  model, under 2K requests and 28.8K seconds.
- At 400 requests a minute, pacing does not bind: about 1,487 × 0.295 s ≈ 7 min of request time
  in all, plus waits.

**Open questions, each settled before the step it gates**

The owner's call before Block 0:
- **Q1.** *Settled on 2026-11-01: accepted.* certifi (MPL-2.0) would come in with httpx, which the
  groq SDK requires (PyPI, read 2026-11-01), and with requests, which the HTTP exporter requires;
  that httpx and requests need it, and its licence, are the agent's memory, UNVERIFIED until step 2
  reads the lock. Its licence is not in the design's 13 list, and D-016 asks the owner's approval
  for a copyleft licence; MPL-2.0 is a weak copyleft one (the agent's reading). Accept it as an
  indirect dependency, used unmodified? The agent recommends yes.
- **Q2.** *Settled on 2026-11-01: kept.* Add an optional `no_speech_prob` to `Transcript` (a change
  to the approved port of the design's 6.1)? It is Whisper's own estimate that a clip holds no
  speech; keeping it lets M3 try a silence filter later on the stored scorecards, without new
  requests. The agent recommends yes: the prototype's silence rule used it (`stt.py`, lines 68-72).
- **Q3.** *Settled on 2026-11-01: written as Accepted.* Does "Approve all" (2026-11-01) cover the
  decision entries the design's 16.3 lists for the `testing` layer, the new checks, the public
  facades and evaluation's split, so Block 0 writes them as Accepted? Or are they written as
  Proposed, for the owner to rule on each?
- **Q8.** *Settled on 2026-11-01: the rules under "The owner's decisions".* The spelling guide's
  rulings, in the owner's words, for `apps/ole5-voice-agent/evals/spelling.toml`: product terms in
  Latin script as the product writes them (the talk-over references already do); numbers as digits
  or words; ة and ه, ى and ي, and the hamza forms (folded by the prototype's normalizer); the
  spelling of each listening sound; English case and contractions. Before Block 0, since Track A
  tests these rulings and Track D's matcher quotes them.
- **Q6, Q20 and Q21:** withdrawn on 2026-11-01, before Block 0 (the progress log). Q6, the
  consent note, is the agent's choice in the decision log; Q20, optional extras, was settled by
  the owner's "No, one install" (D-018); Q21, the downloads, by the owner's answer quoted in
  "The owner's decisions".

The owner's call before recording:
- **Q4.** The script: the counts above; ticket-number and echo-only items; whether to add
  over-the-agent items on the two headsets (a reply plays while the owner speaks), which would
  give M3 overlap clips on every device.
- **Q5.** The shape of a ticket number a customer reads out, for the script's ticket items. No
  source gives Ole5's real format: the prototype's tickets were mocks, `T-MOCK-` with a time and
  a counter (`Ole5-chatbot/src/ole5_chat/tickets/mock.py`, line 20), and its log says "the real
  OTRS format is unknown" (`Ole5-chatbot/VOICE_LOG.md`, line 21, D12). The prototype's agent
  says only a number's last four digits aloud (D12), so a customer may repeat those, or read the
  full number from the screen or an email. The agent proposes both: two items of four digits,
  and two of a full number in the shape the owner gives (the website team may know it).
- **Q7.** The dialect of the talk-over Arabic items: the agent proposes Saudi, MSA or mixed for
  each phrase from its text; the owner confirms or changes each.
- **Q9.** The independent check: (a) the owner listens to every variant and confirms it (the
  agent's recommendation); or (b) something lighter, such as only the unscripted variants, which
  would leave every scripted variant with no independent check: a departure from evaluation.md
  ("Proven twice"), logged as a `Deviation:` line.

The owner's call before the import (step 19), which fixes the split and the strata:
- **Q10.** For N: does the item win over the session in the held-out split? An item is one
  scripted line and a session one recording sitting: with the item winning, every recording of a
  held-out line stays out of tuning, while each sitting has lines on both sides. The agent
  recommends the item: T is one session, and one session per device would hold out a device.
- **Q11 and Q12** (a split take as one variant; the device stratum by microphone): withdrawn on
  2026-11-01 after the review, as labelling choices the agent makes and records (the decision
  log); the owner may overrule either before the import.

The owner's call before the run:
- **Q13.** When neither model is better beyond the noise: keep `whisper-large-v3` (no default
  moves without a gain beyond the noise, the agent's reading of GP-18), or take turbo for its
  lower price ($0.04 against $0.111 an hour).
- **Q14.** An auto-detect arm (`language` unset)? One more dev run per model is 392 requests,
  196 × 10 s = 0.544 h per model: about $0.060 + $0.022 = $0.08 more at the 10 s minimum. The
  agent recommends not in M1: M2 decides how a live call sets the language.
- **Q15.** The windows on dev talk-over clips only (the agent's recommendation: M3 tunes on them,
  and held-out stays unread), or on all 124, as the roadmap's "each talk-over clip" says, in
  which case the held-out clips' windows are reported as aggregates only; and cut from the file's
  start (the agent's proposal) or from the detector's speech start. Every segment file begins
  with 300 ms of the detector's padding before speech (`meta.vad.preSpeechPadMs` is 300 for
  every one of the 124 takes in `takes.json`, read 2026-11-01), so a 500 ms window cut from the
  file's start holds only about 200 ms of speech.
- **Q16.** The key's real limits (console.groq.com/settings/limits), or the 20-a-minute pacing;
  and confirmation that nothing else uses the key during the runs: the prototype's runbook says
  "No test or scoring runs on the Groq key during the trial" (`Ole5-chatbot/VOICE_LOG.md`,
  line 96).
- **Q17.** The budget cap, against the estimate above.
- **Q18.** The cap on held-out runs: H1 and H2 only, at the close (the agent's proposal).
- **Q19.** Attended or unattended runs; if unattended, a schedule the owner approves first.

Every question above gates the run as well as its own step, so each is also the owner's call
before the run.

**Amendments:** none yet.

## What the owner does

1. **Before Block 0:** answer Q1 to Q3 and Q8 (done on 2026-11-01).
2. **The Groq key, any time before the runs.** Put it in `.env` in the main checkout
   (`t2-agentic-voice\.env`) as `T2V_GROQ__API_KEY=<the key>`, or put the key alone in a file
   outside the repository and set `T2V_GROQ__API_KEY_FILE=<its full path>` there. The library
   reads only these names, never `GROQ_API_KEY` (the design's 7.3). The agent never opens `.env`:
   a run reads it through `Settings` when given `--env-file`, and `poe eval --show-settings` says
   only whether the key is set.
3. **Before recording:** answer Q4, Q5, Q7 and Q9 and approve the script.
4. **Recording**, one sitting per device, in a quiet room except for the noise items:
   - From the main checkout, `uv run poe record --out <a folder under var/, such as
     var/golden-audio> --session <a name> --device <laptop, wired or bluetooth>`; open the
     address it prints in Chrome (it holds a token for that session, so use it as printed).
   - Pick the microphone and the output for the device: the laptop's own microphone and
     speakers; the wired headset; the Bluetooth headset (its microphone, as a caller would use it,
     although the prototype found Arabic far worse on it: `Ole5-chatbot/VOICE_LOG.md`, lines
     112-114).
   - Say each line as you would to a support agent; play the take back; keep it or record it
     again (an earlier take is kept and marked discarded, never overwritten).
   - Several-clause requests: pause where the line shows a pause; after the take, click each
     true turn end on its waveform (the end of the request, not the pauses).
   - Echo-only items: say nothing while the page plays the agent's reply. Silence: say nothing
     for the take's length. Noise: make the noise the item names and say nothing.
5. **The check (Q9):** in the recorder's review mode, listen to each variant beside its
   reference and confirm it, or type what was said; a variant you typed comes back in a later
   review pass, to be confirmed against your text.
6. **Before the import and the runs:** answer Q10 before the import (step 19) and Q13 to Q19
   before the runs; read the key's limits in the Groq console, make sure nothing else uses
   the key, and approve the estimate and a budget cap.
7. **For the tracing check (step 22):** start Phoenix on this machine, in PowerShell:
   `$env:PHOENIX_WORKING_DIR = "<a persistent folder, such as var\phoenix>"` and
   `$env:PHOENIX_HOST = "127.0.0.1"`, then `uvx --from "arize-phoenix==21.0.0" phoenix serve`;
   its page is at `http://127.0.0.1:6006`. Without `PHOENIX_HOST`, Phoenix listens on every
   network interface with no login (`HOST = "0.0.0.0"`, and `PHOENIX_ENABLE_AUTH` off by
   default, in arize-phoenix 20.26.0's `phoenix/config.py`, read 2026-11-01 in the old
   repository's `venv`; 21.0.0 is UNVERIFIED), so anyone on the same network could read the
   traced transcript. Phoenix holds call content, so it stays on this machine, never public
   ([SECURITY.md](../../SECURITY.md), trust boundaries). Stop it after the check, before the
   runs.
