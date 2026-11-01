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
    `poe check`. Since the review of the merged tracks a run scores only the variants the owner
    has confirmed, as `poe golden` accepts them, and none is confirmed before step 18: the test
    gives every committed variant a made-up confirmation, and the command-line run, refused until
    the owner's confirmations are imported, is made again at step 19 (the progress log's
    deviation).
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
    commits the split (`split --check`) and the strata table, gates and commits, and runs step
    15's two reference runs on the command line, now on the confirmed set. The item set is
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
  as the `GROQ_CUSTOM_HEADERS` row (paid since) and TD-003 to TD-007:
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
  - Track B's hook also sets `Authorization` to the settings' key after dropping the headers outside
    its allow-list, and its test uses a lowercase `authorization` line: passing `default_headers`
    alone left a lowercase line's value in the request beside the key (a probe of groq 1.7.0,
    made-up keys). The groq entry of the decision log and its debt row (paid since) say so.
  - D-023's Proposed bullet names `requests` and its `[[owners]]` row; D-020's says ARCH-WORDS
    reads the text of the listed types and the path of every file below `[package] root`
    (step 5 points to it).
  - TD-004 names no track; the OpenTelemetry entry of the decision log says the review wrote the
    debt rows as the `GROQ_CUSTOM_HEADERS` row (paid since) and TD-003 to TD-007; the reference
    answerer's held-out runs are outside Q18's cap and append no history line; `## Tracks` lists
    Block 0's test files, which no track edits.

  `uv run poe check` passes: 349 tests, 100% coverage, mypy strict on 126 files, `uv lock
  --check` clean. Next, the merge into `plan-002-integration`, by the integrating session.
- 2026-11-01: Block 0 is merged into `plan-002-integration` (`Plan 002: merge Block 0 into
  plan-002-integration`). In all, 44 findings were raised: 38 held and are fixed, 6 were refuted by
  the agent that checked them, and none goes to the owner; the debt they left is the
  `GROQ_CUSTOM_HEADERS` row (paid since) and TD-003 to TD-007. The second round's check found one
  slip, the entry above naming the first round's commit as its own, corrected here. After the merge
  `uv run poe check` passes (349 tests, 100% coverage, mypy strict on 126 files) and `uv lock
  --check` is clean. Next, Tracks A to H, each in its own worktree cut from `plan-002-integration`.
- 2026-11-01: Track A, text and scorers, is merged into `plan-002-integration` (`Plan 002: merge
  track A`), the first track to merge. It was built on `plan-002-track-a`, cut from 44aa043, in four
  commits, each gated on its own tree: 70a2490 (the Arabic normalizer and digit normalization),
  2f2ec10 (the spelling-guide check), d1a11aa (the sign test by item) and 38b2cae (recall, text from
  silence, WER and CER). Every stub Track A owns is replaced, with its stub test:
  `normalize_arabic`, `normalize_digits`, `spelling_issues`, `term_recall`, `id_recall`,
  `silence_output`, `sign_test`, `wer` and `cer`. From the track's report:
  - Deviation: the owner chose a lighter review on 2026-11-01 ("Yes, go lighter"): the tracks are
    merged with the gate after each and no review before the merge; one review of the merged code by
    three concerns (security; measurement; harness and faithfulness), each reviewer's high and
    medium findings checked by one agent told to refute them, one fix round and a check, replaces
    step 14's reviews by track and stands as step 16's review of the code.
  - `normalize_arabic` (`domain/text/arabic.py`) is ported from
    `Ole5-chatbot/src/ole5_chat/voice/rules.py`, lines 11-19 (`TASHKEEL`, `NOT_WORD`, `FOLD`,
    `normalize`), read as text. It runs the same steps in the same order: the marks removed, the
    seven letter forms folded, lower case (`str.lower`, as the prototype), `_` as a space, every
    character that is neither a word character nor a space read as a space, then runs of space
    joined and the ends trimmed. `TASHKEEL`'s class, read as code points, is U+0610-U+061A,
    U+064B-U+065F, U+0670, U+06D6-U+06ED and U+0640, written with `\u` escapes, each named in a
    comment. It passes all 37 rows of Block 0's characterization table, and the prototype's own
    normalizer test (`Ole5-chatbot/tests/test_voice_rules.py`, lines 10-14) is ported into
    `tests/t2_agentic_voice/domain/test_arabic.py`.
  - `normalize_digits` (`domain/text/digits.py`) reads Arabic-Indic and Persian digits as ASCII, as
    the prototype's `DIGITS` table does (`Ole5-chatbot/scripts/stt_eval.py`, lines 1059-1066), and
    the verdict's form (normalize, then digits, then spaces removed) is that file's `norm`. The one
    departure is the table's: on its two `gap` rows («خمسة سبعة», "five seven") Track A's verdict
    string is 57, the spelling guide's (Q8), where the prototype's `norm` keeps the words (خمسهسبعه,
    fiveseven); a test asserts both that the gap rows give the guide's string and that they differ
    from the prototype's.
  - Not ported: the prototype's `lev` and `text_score` (`Ole5-chatbot/scripts/stt_eval.py`, lines
    1069-1086), whose CER is capped at 1 per variant and taken against the closest accepted
    reference. `cer` is jiwer's, pooled over a stratum and uncapped, as the decision log's verdict
    entry says.
  - The plan's UNVERIFIED reading of jiwer holds for the installed jiwer 4.0.0: in
    `jiwer/process.py`, `process_words` has a "special edge-case for empty references" that sets the
    WER to the number of insertions when the pooled references hold no word. Probed: `jiwer.wer("",
    "a b")` is 2 (an int) and `jiwer.wer(["", "a"], ["x y", "a"])` is 2.0. A test in
    `tests/t2_agentic_voice/testing/test_scorers.py` pins both, so `wer` and `cer` refuse a
    reference that is empty after normalization with a ValueError.
  - The tests cover the track's list: the characterization table (37 rows, against both
    `normalize_arabic` and the verdict's form); each ruling of Q8 (the seven letter folds, the other
    forms kept, diacritics and tatweel, lower case, punctuation, spaces ignored in the verdict,
    contractions as said, and in `test_spelling.py` product terms in Latin script, numbers as digits
    and listening sounds); Arabic-Indic and Persian digits; digits spelled one word each, in Arabic
    and in English; WER and CER against hand-computed cases, empty output included; an empty
    reference refused (ValueError); a bare str for `references`, `outputs` or `terms` refused
    (TypeError); and the sign test at b = 6, w = 0 (2/64 = 0.03125), b = 5, w = 0 (0.0625) and b = w
    (1). Adversarial tests: invisible format characters (bidirectional marks, zero-width characters,
    a byte-order mark) never change a verdict (one inside a word holding a digit's name did, until
    the review of the merged tracks gave the matcher the texts' joined form); an avoided spelling is
    text, never a pattern; malformed counts and inputs are refused.
  - The Arabic string constants Track A adds to `packages/` are the eleven digit names in
    `domain/text/digits.py`, and the marks class and the single letters of the fold table in
    `domain/text/arabic.py`, all as `\u` escapes (Track D's test, merged after it, finds no
    reference among them; corrected by the review of the merged tracks); its docstrings and messages
    hold none of okay, stop, wait or yeah, and no Arabic.
  - Its debt rows are TD-008 to TD-010 (the normalizer's missing Unicode composition step, term
    recall on a Latin term with an Arabic prefix, and the digit names left out). It changed no row,
    asked for no change to Block 0 and left no question for the owner.
  - Not done by Track A: whether a one-word talk-over reference is one of the eleven digit names,
    since `refs.json` is outside its May read; Track D's no-item-in-source test checks it when Track
    D merges.
  - After the merge `uv run --offline poe check` passes: 740 tests, 100% coverage (990 statements),
    mypy strict on 126 files, arch and docs clean.
- 2026-11-01: Track B, the Groq speech-to-text adapter, is merged (`Plan 002: merge track B`), from
  one commit on `plan-002-track-b`, cut from 44aa043: 0a628d5 (`Plan 002: track B, the Groq
  speech-to-text adapter`). `adapters/groq_stt.py` (324 lines) replaces Block 0's stub, and
  `tests/t2_agentic_voice/adapters/test_groq_stt.py` (397 lines, 72 tests: 70 pass, 2 xfail strict)
  its stub test. `GroqSTT` wraps the clip's PCM16 as WAV with `wave` and sends it as `audio/wav`;
  always passes the key, `groq.base_url` and the timeout, with the SDK's retries off and redirects
  not followed; replaces every header in a request hook with its own eight, `Authorization` the
  settings' key; turns every failure into a `ProviderError` with no exception chain; bounds the
  whole request by `stt.timeout_s`; bills the larger of 10 s and the clip's length; weights the
  confidence and the no-speech estimate by segment length, as the prototype did; and gives the
  design's 6.1 `DataFlow`. `from_settings` raises the `ConfigurationError` naming
  `T2V_GROQ__API_KEY` when no key is set (a blank one included; `GROQ_API_KEY` is never read). The
  tests check the request against Block 0's baseline (not edited), the result, a cancel on a real
  127.0.0.1 connection (under 50 ms, no task left, the connection closed), 27 failure cases each
  asked once, the key in no repr, error, traceback, log or captured output while the fake server
  echoes the request's headers, `GROQ_API_KEY` and `GROQ_BASE_URL` together and four
  `GROQ_CUSTOM_HEADERS` variants changing nothing (counts corrected by the review of the merged
  tracks), and no groq type in a public signature. From the track's report:
  - Prototype sources, read as text, never run (D-010). `Ole5-chatbot/src/ole5_chat/voice/stt.py`,
    lines 221-252, the call: the file as ("speech.wav", wav); `language`; `response_format`
    `verbose_json`; `temperature` 0; `prompt` only when given; the text stripped; `_by_length`, the
    mean of each segment's `avg_logprob` and `no_speech_prob` weighted by `max(1e-3, end - start)`,
    a missing time read as 0; lines 110-119, a short timeout and no retry.
    `Ole5-chatbot/src/ole5_chat/voice/groqhttp.py`, lines 1-16: the pool of 20 connections, 10 kept
    alive for 300 s. `Ole5-chatbot/tests/test_voice_stt_v2.py`, lines 21-30 (the WAV writer) and
    324-337 (the timeout and no retry), as behaviour specs.
  - The installed groq 1.7.0, read as text: `groq/_client.py`, lines 294-313 (`AsyncGroq` reads
    `GROQ_API_KEY` and `GROQ_BASE_URL` only when none is passed, and always reads
    `GROQ_CUSTOM_HEADERS`); `groq/_base_client.py`, lines 435-461 (the headers), line 522 (a
    multipart Content-Type without a boundary is dropped), line 1556 (a platform probe on a client's
    first request, in a worker thread), lines 1587-1655 (an httpx timeout becomes `APITimeoutError`
    and any other send failure `APIConnectionError`, both `from err`) and lines 775-807
    (`_should_retry`); `groq/resources/audio/transcriptions.py`, lines 448-462 (the path and
    multipart); `groq/_utils/_logs.py` (`GROQ_LOG`). httpx 0.28.1: `httpx/_client.py`, lines
    1679-1691 (request hooks run on every request of a redirect chain); `httpx/_models.py`, lines
    413 and 441-446 (the multipart boundary is read from a content-type header, and passed headers
    win over Host and Content-Length).
  - Probes of groq 1.7.0 against `httpx.MockTransport` and a 127.0.0.1 socket, with made-up keys, in
    the session's scratch folder: a `GROQ_CUSTOM_HEADERS` line naming Host or Content-Length reaches
    the request before any hook, so the hook pins every header's value; a lowercase `content-type:
    multipart/form-data; boundary=zzz` line makes httpx encode the body with that boundary;
    `X-Stainless-Raw-Response: stream` changes nothing; a cancel during a request ended in 2.5 ms,
    and httpcore closed the connection.
  - Values chosen: 10.0 s billed at least; a pool of 20 connections, 10 kept alive for 300 s (the
    prototype's); the SDK's own User-Agent, `AsyncGroq/Python 1.7.0`; Accept-Encoding `gzip,
    deflate` and Connection `keep-alive`, httpx's defaults; `name` `groq`; the design's 6.1
    `DataFlow` strings word for word; the cancel test's bound of 50 ms (the design's 6.1); a 0.2 s
    timeout in the failure tests, so a hung reply exercises the adapter's own deadline. Measured
    cold on the owner's laptop: `import groq` 3.2 s, `platform.system()` 0.38 s and
    `platform.platform()` 0.15 s, so the four `GROQ_LOG` child processes run side by side from one
    module fixture (about 6.6 s rather than 20 s).
  - Deviation: `GROQ_LOG`'s effect is not undone in the adapter, which the track allows ("or the
    case reported against TD-003"): ARCH-OWNER keeps `logging` in `core`, so two tests pin the case
    as xfail strict, and the track asked for a `core/logging.py` helper that would undo it (applied
    in the following commit, `Plan 002: review fixes, track B`).
  - Deviation: the request hook does more than the plan's "drops every header outside an allow-list,
    then sets Authorization": it rebuilds the eight headers it allows with its own values, since a
    `GROQ_CUSTOM_HEADERS` line naming an allowed header (Host, Content-Length, User-Agent) would
    otherwise change that header's value.
  - Deviation: a `ProviderError` is raised after the except block as well as `from None`, so its
    `__context__` is None too; the plan says only "raised from None", which still leaves
    `__context__` pointing at the SDK's error.
  - Deviation: `transcribe` adds a total deadline, `asyncio.timeout(stt.timeout_s)`, on top of the
    explicit SDK and httpx timeout the plan names.
  - Deviation: `__init__` and `from_settings` both take a `transport` keyword, and the constructor
    refuses invalid values with a `ConfigurationError` naming each setting; the plan allowed one
    keyword argument for the fake transport and gave the constructor no checks.
  - Its debt rows are TD-011 (the form of Groq's `language` when none is named) and TD-012 (the
    SDK's platform probe on a process's first request). It narrows the `GROQ_CUSTOM_HEADERS` row
    (paid since) to the multipart boundary a `content-type` line can still choose, rewrites TD-003
    with what its child-process tests confirm, and leaves TD-004 unchanged (the adapter's httpx
    client keeps `trust_env` on, as Block 0's second review ruled). It left no question for the
    owner.
  - Not done: not checked against Groq itself (no network): the form of `verbose_json`'s `language`
    (a code or a name), whether Groq sends `retry-after` as seconds or as an HTTP date, and whether
    Groq accepts a request without the X-Stainless headers the hook drops. The first live smoke
    request (step 21) is where these are seen.
  - After the merge `uv run --offline poe check` passes: 809 tests and 2 xfailed (the two `GROQ_LOG`
    cases), 100% coverage (1105 statements), mypy strict on 126 files, arch and docs clean.
- 2026-11-01: Review fixes, track B (`Plan 002: review fixes, track B`). The track's one request for
  a change to Block 0 is applied, since it is small, within the plan (TD-003's fix: undo the effect
  after `import groq` if that fits the design's 10.2) and needed for invariant 8: `core/logging.py`
  gains `logging_unchanged`, with two tests in `tests/t2_agentic_voice/core/test_logging.py` written
  first (they failed on the missing helper); `adapters/groq_stt.py` imports `groq` inside it and its
  docstring says so; the xfail mark of the two `GROQ_LOG` cases in
  `tests/t2_agentic_voice/adapters/test_groq_stt.py` is removed, and both pass. TD-003 is narrowed
  to what the helper cannot undo. `uv run --offline poe check` passes: 813 tests, 100% coverage,
  mypy strict on 126 files, arch and docs clean.
- 2026-11-01: Track C, the tracing helpers, is merged (`Plan 002: merge track C`), from four commits
  on `plan-002-track-c`, cut from 44aa043: ddb84bf (the Redactor), 83b1a30 (the tracing helpers),
  b820fb6 (no header variable quoted in a log line) and bf1e5ef (a `.netrc` login reaches no export
  request). Block 0's stubs `core/redaction.py` and `core/tracing.py` are real code, and their stub
  tests are replaced by 9 tests in `tests/t2_agentic_voice/core/test_redaction.py` and 11 in
  `test_tracing.py` (13 with its parametrized cases; corrected by the review of the merged tracks).
  The `Redactor` finds every match of every pattern in the original text and turns each stretch any
  pattern matched into one marker; it refuses a bare str, and its repr shows no pattern. `Tracing`
  uses the team's `TracerProvider` if one is given, otherwise a private one built from
  `tracing.endpoint`, otherwise it is off, and never sets a provider globally. `turn()` is a CHAIN
  root span carrying `session.id`; `speech_to_text(parent, ...)` is an LLM span carrying
  `llm.model_name`, `stt.audio_seconds` and `stt.language_sent`, and its `record()` adds
  `output.value` (only when `include_transcripts` is on), `stt.language` and `stt.billed_seconds`.
  Every text value, what a team sets on the yielded turn span included, goes through the `Redactor`;
  bytes and mappings are dropped; an exception is recorded by its type only. From the track's
  report:
  - No prototype file was ported (its May read names none): it was built from the design's 10.1,
    SECURITY.md's invariants 5 and 8, and the installed packages read as text: OpenTelemetry 1.45.2
    (the API, the SDK and the HTTP exporter, with the indirect
    `opentelemetry-exporter-http-transport` and `opentelemetry-exporter-otlp-common` 0.66b2) and
    `openinference-semantic-conventions` 0.1.43.
  - Its reading of OpenTelemetry 1.45.2, which differs from the 1.45.1 lines the decision log cites:
    `TracerProvider.__init__` calls `Resource.create` when given no resource and reads the sampler
    from the environment when given none (`opentelemetry/sdk/trace/__init__.py`, lines 1271 and
    1275), and reads `OTEL_SDK_DISABLED` at line 1278; the Tracer reads the internal-metrics
    variable at line 1094; the exporter resolves its endpoint, compression, session, timeout and
    headers in `exporter/otlp/proto/http/trace_exporter/__init__.py`, lines 139-159, and reads the
    internal-metrics variable at line 169; `_resolve_headers` and `_build_transport` are at
    `exporter/otlp/proto/http/_common/__init__.py`, lines 137-149 and 182-211. The transport now
    lives in `opentelemetry-exporter-http-transport` and sets `session.verify` and `session.cert`
    from the certificate variables (`opentelemetry/exporter/http/transport/_requests.py`, lines
    64-80). An export's retries end at the timeout's deadline (`exporter/otlp/common/http.py`, lines
    185-187). `BatchSpanProcessor.shutdown` passes no timeout (`sdk/trace/export/__init__.py`, lines
    217-218), so the shared `BatchProcessor.shutdown` waits 30000 ms
    (`sdk/_shared_internal/__init__.py`, line 207), and its queue-full drop is counted only through
    the metrics `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED` turns on (line 201). `parse_env_headers`
    logs a malformed header entry with its text (`opentelemetry/util/re.py`, lines 68 and 83).
  - Its values: the private provider's queue holds 512 spans (`_QUEUE_SPANS`; the SDK's default
    is 2048) and sends batches of 128 (`_BATCH_SPANS`; SDK 512); a span sits at most 1 s in the
    queue (`_DELAY_S`; SDK 5 s); one export may take 2 s, the exporter's own retries included
    (`_EXPORT_TIMEOUT_S`, passed as the OTLP exporter's `timeout`; the exporter's default 10 s, the
    SDK processor's 30 s); `shutdown` gives the last batch 3 s (`_CLOSE_S`) and then counts what is
    still queued as dropped. Span limits: the SDK's own 128 for the six count limits, and 8192
    characters for both value-length limits, all eight passed. The reasons: a turn or a golden-set
    variant makes two spans, so 512 holds minutes of a slow backend at a bounded memory cost; a
    local Phoenix answers in milliseconds, so 2 s is generous and still short; 1 s shows the traced
    smoke request in Phoenix almost at once; 3 s is one export plus a second, so a hung exporter
    delays an app's exit by at most 3 s.
  - Its attribute names: the turn span has `openinference.span.kind` CHAIN and `session.id`; the
    speech-to-text span has `openinference.span.kind` LLM, `llm.model_name`, `output.value` with
    `output.mime_type` `text/plain` (only when `include_transcripts` is on), and four names of the
    library's own, `stt.audio_seconds`, `stt.billed_seconds`, `stt.language_sent` and
    `stt.language`, since OpenInference 0.1.43 has none for them (they mirror Block 0's
    `FakeTracing` keys). On a failure the span gets `error.type` and status ERROR. The resource
    holds `service.name` `t2-agentic-voice` and `openinference.project.name` from `tracing.project`;
    the instrumentation scope is `t2_agentic_voice` with the library's version.
  - Its probes, in the scratch folder with made-up values and a collector on 127.0.0.1: built on a
    plain `requests.Session`, the exporter sent `authorization: Bearer <made-up>` and `x-made-up: 1`
    from `OTEL_EXPORTER_OTLP_HEADERS`, and its `session.verify` was the made-up certificate path; a
    plain session given a made-up `NETRC` also added `Authorization: Basic ...`. The library's
    session sends only Content-Type, User-Agent (`t2-agentic-voice/0.1.0`) and Content-Length, plus
    the Host and `Accept-Encoding: identity` the transport adds, with `verify` True and `cert` None.
    The header test fails when the verify and cert reset, the header clearing or the log filter is
    removed (each checked, then restored).
  - The tests prove that `OTEL_EXPORTER_OTLP_HEADERS` (both forms, and a malformed entry the SDK
    would log with its text) reaches no request and no log line, nor does a `.netrc` login; that the
    certificate, client key, endpoint, timeout, compression and credential-provider variables change
    nothing; and so do `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SERVICE_NAME`, `OTEL_BSP_*`, the sampler
    and limit variables and `OTEL_PYTHON_METER_PROVIDER`.
  - Deviation: the private provider's batch processor is the library's own (`_Queue` in
    `core/tracing.py`), not the SDK's `BatchSpanProcessor`, which the decision log assumes ("passes
    the batch processor's sizes and timeouts, which otherwise come from `OTEL_BSP_*`"): the SDK's
    processor counts no dropped span unless `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED` turns its
    metrics on, and its `shutdown` passes no timeout, so a hung exporter holds it for 30 s. The four
    `OTEL_BSP_*` variables are now never read, which the tests check.
  - Its debt rows are the size-cap row of `core/tracing.py` and its test file (paid by the
    review of the merged tracks), TD-014 (the
    worker thread not restarted in a forked child) and TD-015 (no setting for a CA file, a client
    certificate or an export header). It narrows TD-005 to `OTEL_SDK_DISABLED` and
    `OTEL_PYTHON_CONTEXT`, and TD-004 by its `.netrc` part. It asked for no change to Block 0.
  - Its question for the owner: should the library override `OTEL_SDK_DISABLED` by setting the SDK's
    private `_disabled` flag on its own provider (a test would guard it, but it can break without
    warning on an SDK upgrade), or should it stay as debt (TD-005), with the guide saying to leave
    the variable unset? The library now logs `tracing_disabled_by_sdk` when it happens, and nothing
    leaves the process.
  - Not done: the traced request to a real Phoenix (step 22), since the track's rules forbid every
    outside call; the OTLP path was checked only against a collector on 127.0.0.1, which parsed the
    protobuf body (one `turn` span and one `speech_to_text` span, the resource exact, `run-1`
    present, no made-up key). The guide's text that `OTEL_SDK_DISABLED` and `OTEL_PYTHON_CONTEXT`
    stay unset (TD-005's fix) and that `Tracing` is built after a fork (TD-014) is not written,
    since `docs/guide/` is Track H's.
  - After the merge `uv run --offline poe check` passes: 833 tests, 100% coverage (1345 statements),
    mypy strict on 126 files, arch and docs clean.
- 2026-11-01: Track D, the golden set's items, matcher, validation and split, is merged (`Plan 002:
  merge track D`), from five commits on `plan-002-track-d`, cut from 44aa043: 5c13483 (the matcher,
  Ole5's spelling guide, the items and their TOML writer), fd4eb2f (the two imports and the
  talk-over items), be0069e (the deterministic split and the draft script), 4925b46 (`poe golden`,
  the frozen answers and the strata) and 948f482 (the tests that keep items and audio out of the
  product). It replaces Block 0's stubs `items.py`, `toml_write.py`, `import_talkover.py`,
  `import_recordings.py`, `matcher.py`, `golden.py` and `split.py`, and adds the data under
  `apps/ole5-voice-agent/evals/`: `spelling.toml` (quoting the owner's Q8 answer, "Use these rules",
  2026-11-01, in each ruling), `terms.toml`, the draft `script.toml`, `split.json`, `strata.toml`,
  `frozen.json`, an empty `allowed_in_source.toml`, `manifests/talkover.json` and 43 talk-over items
  under `golden/`. No audio is in the repository. From the track's report:
  - The talk-over sources, read as text or data only (D-010), in the lab's folder beside
    `Ole5-chatbot/` (`voice-lab/`, not inside it): `voice-lab/recordings/talkover/refs.json` has 124
    segments; `takes.json` has 124 takes, 116 with one segment, 4 with two and 4 with none
    (r02_ghalat__pause__speakers__184559, s01_archive__pause__headset__185344,
    y01_naam_irsilha__duck__speakers__182152, y03_yes_submit__duck__speakers__183225); there are 43
    phrase IDs, and every take has the same `mic_label` (the laptop's microphone array). The 40
    scripted phrases of `voice-lab/static/talkover.js` (the `PHRASES` table, lines 35-80) equal
    `refs.json`'s text, kind, want and language for every take, and the 3 unscripted ones agree on
    kind, want and language (a scratch script outside the repository); the import reads `refs.json`
    and `takes.json`, not the script.
  - An unscripted take's reference is the text the owner typed in the lab, its spaces collapsed as
    `voice-lab/server.py` does (lines 329-344, `talkover_ref`); its variant's `reference_source` is
    `typed`, and its item's `text` is empty, since the phrase has no scripted words.
  - The matcher's verdict follows the prototype's `norm` and `text_score`
    (`Ole5-chatbot/scripts/stt_eval.py`, lines 1062-1066 and 1079-1086): both texts go through
    `normalize_arabic`, then `normalize_digits`, then every space is removed, and the output is
    right when it equals any accepted reference. A word split in two counts as right («لو سمحت»
    against «لوسمحت», «تمام تمام» against «تمامتمام», tested with the fake normalizer), and a test
    checks the verdict against every row of Block 0's characterization table, with "57" on the two
    gap rows.
  - The talk-over import's output: 43 items, 120 variants and 124 files in `manifests/talkover.json`
    (session talkover-2026-10-27, device laptop, consent null), all 16 kHz. Items by language:
    english 9, mixed 4, msa 7, saudi 23. Variants by tag: duck 63, pause 57, over-assistant 108,
    playback-speakers 117, playback-headset 3, which agree with the registration's segment counts
    (duck 65 and pause 59 once the 4 split takes count twice); `strata.toml` registers them.
  - Golden's validation was run once with the talk-over audio root, on the lab's folder, outside any
    test, with a no-op spelling check standing in for Track A's stub: all 124 files match the
    manifest's hash, rate and length, and no problem was found. `frozen.json` is fresh: 0 variants
    accepted and 120 left out, since the owner has confirmed none yet (Q9), the 6 typed ones waiting
    on their second confirmation.
  - The split is by item, stratified by language and kind, from the salt plan-002-2026-11-01: it
    holds out 13 of the 43 items and 36 of the 120 variants, and `python -m ole5_voice.evals.split
    --check` passes on the committed `split.json`.
  - The draft script (`script.toml`) holds the 52 lines of the registration's proposal: 18
    one-clause requests, 10 paused requests, 6 stop words, 4 repeat requests, 5 listening sounds and
    4 ticket numbers, with 1 silence, 2 noises and 2 echo-only lines, which use the lab's replies
    ar_inbox and en_signature (`voice-lab/assets/talkover/replies.json`). It is marked as a draft
    for Q4, Q5 and Q9; the ticket lines use `TICKET_KIND`, and the two full-number lines hold no
    number until Q5. Its fixed list of listening sounds is the talk-over's ten plus "mm-hmm" and
    "uh-huh". Each Arabic item's language is the agent's proposal, marked as a draft in its file
    (Q7).
  - The test that no item is in the product folds 90 references (every item's reference and
    alternatives, and every script line) and searches 932 string constants and text files in 58
    files under `packages/`, `apps/*/src` and `examples/`, finding none; its self-tests find pasted
    text and ignore words that only contain a reference. At this merge it also reads Tracks A to C's
    code (Track A's eleven digit names among it), and still finds none.
  - Deviation: the recordings import's tests are in
    `tests/ole5_voice/evals/test_import_recordings.py`, a file Track D's Owns line does not name;
    with them `test_items.py` would pass ARCH-SIZE's 400 lines (it holds the items, the writer and
    the talk-over import in 393). No other track owns the new file.
  - Deviation: the talk-over import, not only `poe golden --audio`, hashes the lab's 124 WAV files
    and reads their format with `audio.read_wav`, since a manifest needs each file's hash. It was
    run once from the agent's shell, reading the lab's folder; the lab was not written. No test
    reads audio: the import and `golden` take the reader as an argument, and tests pass a fake.
  - Deviation: the lab is at `voice-lab/` beside `Ole5-chatbot/`, not at `Ole5-chatbot/voice-lab` as
    the track's task said; it was read there, as text or data only.
  - Deviation: `test_matcher.py`'s check of the verdict against the characterization table skipped
    while Track A's normalizer raised NotImplementedError. Track A merged first, so it runs at this
    merge, and its skip is removed in the following commit.
  - Its debt rows are TD-016 (the dialect labels as a table in code) and TD-017 (the
    no-item-in-source test's own copy of the letter folding). It changed no row and asked for no
    change to Block 0.
  - Its questions for the owner: Q4, Q5, Q7 and Q9 are still open, and nothing in the files answers
    them (`script.toml` and the Arabic items' languages are drafts, the two full-number ticket lines
    wait on the shape of an Ole5 ticket number, and every variant waits on the owner's listen);
    `terms.toml` adds Ole5, the product's own name, as a product term beside Outlook, PDF, Word and
    English: keep it or drop it with the script's approval (Q4)?; the talk-over manifest has no
    consent record, since the decision log asks for consent only for the new recordings and the
    talk-over takes are the owner's own from the prototype: should the owner's consent for the
    talk-over set also be recorded, in words and dated?
  - Not done: the new recordings are not imported, since none exist before Q4, Q5, Q9 and the
    owner's sessions; the final talk-over import with the owner's dialect labels (Q7) and the import
    of the reviews belong to step 19, when `strata.toml` and `split.json` change with Q10. No
    variant is accepted (`frozen.json`: 0 accepted, 120 left out) until the owner confirms each one
    (Q9); `items.accepted()` gives the checked variants. Whether the runner scores only those, and
    whether step 15's reference-answerer check runs on every committed variant meanwhile, is left by
    the track to Track E or the integrator.
  - At the merge, `uv run --offline poe golden --check` runs end to end with Track A's real spelling
    check (`golden_valid`, the frozen file checked, 120 variants left out), and `python -m
    ole5_voice.evals.split --check` passes. After the merge `uv run --offline poe check` passes: 912
    tests (the characterization check among them, no longer skipped), 100% coverage (2004
    statements), mypy strict on 130 files, arch and docs clean.
- 2026-11-01: Review fixes, track D (`Plan 002: review fixes, track D`): the skip in
  `tests/ole5_voice/evals/test_matcher.py` that waited on Track A's normalizer is removed, with its
  helper and the import only it used, since the characterization check ran and passed at the merge;
  it now runs on every gate. `uv run --offline poe check` passes: 912 tests, none skipped, 100%
  coverage, mypy strict on 130 files, arch and docs clean.
- 2026-11-01: Track F, scorecards, comparison and history, is merged (`Plan 002: merge track F`),
  before Track E as step 14 orders, from three commits on `plan-002-track-f`, cut from 44aa043:
  489248a (the scorecard), 8aebf45 (the run history and its generated page) and 15296e2
  (`eval-compare`), each gated before it was made. It replaces Block 0's stubs `scorecard.py`
  (`write_scorecard`, a `ScorecardWriter`), `history.py` (`read_history`, `append_line`, `line_of`,
  `render_history`, `poe eval-history`) and `compare.py` (`poe eval-compare`), with their tests in
  `tests/ole5_voice/evals/test_scorecard.py`, `test_history.py` (the freshness test among them) and
  `test_compare.py`, and adds an empty `apps/ole5-voice-agent/evals/history.jsonl`,
  `docs/generated/eval-history.md` and its row in `docs/generated/README.md`. The scorecard holds
  accuracy, WER and CER, term and ID recall, text from silence, requests and retries, latency
  (median and 90th percentile), billed seconds and cost; breakdowns by language, device, kind and
  split; the window measures as `WindowMetrics`; violations, always 0, with the reason; and "one
  speaker". A held-out scorecard holds aggregates only. `eval-compare` reports fixed, broken and
  net, variant by variant, the sign test by item, the registered stratum guard by language and by
  device (a stratum that cannot reach p < 0.05 marked too small to guard), the smallest change one
  run can detect, `--focus` items apart, and the infrastructure failures and variants found in one
  run only, left out of both and listed; held-out runs are compared by aggregates only. It refuses
  two runs whose commits, data digests or splits differ, naming each difference. From the track's
  report:
  - Its sources: its May read names no prototype file, so it followed the plan and evaluation.md
    only: the registration's "The metrics" and evaluation.md's "Judging a change" for the scorecard;
    "Judging a change" and the registration's "The noise" and "The stratum guard, exactly" for
    `eval-compare`; evaluation.md's "Run history" for the history and its page.
  - Its values: p < 0.05 is beyond the noise (evaluation.md). Latency's median and 90th percentile
    are interpolated linearly between ranks (Hyndman and Fan type 7, numpy's default), so 0.5 gives
    the median. A stratum is too small to guard when even all of its changed items on one side could
    not reach p < 0.05 by the sign test, which with evaluation.md's formula is fewer than 6 changed
    items, as the registration says. The smallest detectable change c is searched from 1 up to the
    items the noise left unchanged: with no noise it is 6, as registered; with 3 items changed and
    20 compared it is 9 (b = 10, w = 2 gives p = 0.0386, while c = 8 gives 0.0654). Report numbers:
    rates to 4 decimals and counts as whole numbers; on the history page, accuracy as a percentage
    with one decimal and cost to $0.0001.
  - Its hand checks: `test_every_metric_is_recomputed_by_hand` recomputes all 15 numbers (cost from
    the billed seconds) for the totals and all 11 stratum values of a made-up dev run of 8 results
    across 4 languages, 3 devices and 3 kinds, one provider failure, two empty references and two
    ticket numbers among them (for example 3 right of 7 judged, latency median 290 ms and p90 314
    ms, 72.5 billed seconds). The pooled WER and CER arguments are checked for the totals, English,
    mixed and dev pools, and the rest by their call count (both corrected by the review of the
    merged tracks), the window sums for 5 window groups, and the sign-test counts against an oracle
    written from evaluation.md's formula (6 better and 0 worse gives 2/64; 5 and 0 gives 0.0625).
  - Two tests run the library's own defaults on cases worked by hand: the scorers (WER 1/5 and CER
    3/22, with spaces removed) and the sign test (six items better and none worse gives p = 0.0312).
    They skipped on the track's branch while Track A's stubs raised NotImplementedError; Track A
    merged first, so both run and pass at this merge, and their try and skip are removed in the
    following commit. The debt row the track wrote for them is therefore not numbered: its own fix
    ("the row goes with it") is done at this merge.
  - Deviation: Track F created `apps/ole5-voice-agent/evals/history.jsonl` (empty, committed in
    8aebf45), which its Goal names but no track's Owns line lists. Without it `poe eval-history` and
    the freshness test would have no committed source, unless a missing file were read as an empty
    history, which would let a mistyped `--history` render "No runs yet" silently.
  - Deviation: `eval-compare` also refuses two runs whose splits differ, beyond the commits and data
    digests the track names: a run covers one split (the decision log), and a dev run and a held-out
    run share no variant, so their comparison would be empty or misleading.
  - Its debt row is TD-018 (`docs/generated/eval-history.md` read as a living doc). It changed no
    row and left no question for the owner. Its request for a change to Block 0 (`harness.toml`'s
    `[docs] historical` to list `docs/generated/eval-history.md`) is not applied at this merge (the
    decision log).
  - Not done: `poe eval-history`, a refused `poe eval-compare` and both commands' `--help` were run
    through poe, and the comparison report was rendered with an exact sign test in a scratch script;
    no real history line or scorecard exists yet, so `docs/generated/eval-history.md` shows "No runs
    yet", and the page with runs was seen only as rendered from made-up lines. Appending each run's
    line is Track E's (it calls `history.append_line`, and may use `line_of`).
  - After the merge `uv run --offline poe check` passes: 948 tests, none skipped, 100% coverage
    (2334 statements), mypy strict on 130 files, arch and docs (24 files) clean.
- 2026-11-01: Review fixes, track F (`Plan 002: review fixes, track F`): the try and skip around the
  two tests of the library's defaults (`test_the_librarys_scorers_score_a_case_worked_by_hand` in
  `tests/ole5_voice/evals/test_scorecard.py` and `test_the_librarys_sign_test_judges_a_run` in
  `test_compare.py`) are removed, with their docstrings' note, since both ran and passed at the
  merge on Track A's scorers and sign test. `uv run --offline poe check` passes: 948 tests, none
  skipped, 100% coverage, mypy strict on 130 files, arch and docs clean.
- 2026-11-01: Track E, the runner, is merged (`Plan 002: merge track E`), after Track F, from three
  commits on `plan-002-track-e`, cut from 44aa043: 06ba75f (the window measures and the worktree
  checks), 2b8d0fa (the answerers and the run's plan) and 45a6c60 (`poe eval`), each gated before it
  was made. It replaces Block 0's stubs `run.py`, `answerers.py`, `windows.py` and `worktree.py`,
  and adds `run_parts.py`, with their tests in `tests/ole5_voice/evals/` (`test_run.py`,
  `test_run_parts.py`, `test_answerers.py`, `test_windows.py`, `test_worktree.py`). `poe eval` takes
  every flag the plan lists, and `--clips-from`; `--split` is always required, and
  `--price-per-hour` and `--cap-usd` when the answerer calls Groq. The settings load through
  `Settings.from_env`, whose error is the only one reported, and `--show-settings` prints each
  setting resolved (the Groq base URL included, the key only as set or not set), the worktree's
  state and every path. Before any call it refuses the main checkout, a dirty tree (untracked files
  count), an `--out` that exists, lies inside the run's own or another linked worktree, or inside
  the main checkout where git would track it, and audio that is not the file its manifest hashed.
  The smoke test sends one dev variant and must pass with no failed, retried or refused request.
  Requests go one at a time, paced to `--max-rpm`; a request turned away is asked again after a
  pause, up to `--max-attempts`, and then the variant is a provider failure; a variant still running
  at `--variant-timeout-s` is stuck; the cap is checked before each request, and a request that
  would pass it is never sent. A dev run writes each result to `results.jsonl` as it finishes, with
  a progress line of identifiers, verdicts and timings, never a transcript; Track F's writer writes
  the scorecard; a run that calls Groq appends its history line to the worktree's `history.jsonl`
  and copies it beside the scorecard. A held-out run has no per-variant output, counts-only lines
  and no tracing, and an interrupted one keeps no result; Ctrl+C or the cap leaves a run incomplete
  (exit 1). From the track's report:
  - Prototype sources, read as text, never run (D-010): the pause after a rate limit is the larger
    of `retry-after` and 20 s, and 3 s after another failure that may pass
    (`Ole5-chatbot/scripts/stt_eval.py`, lines 575-585, at lines 581 and 585); up to 4 attempts per
    utterance, hence `--max-attempts 4` by default (the same file, lines 708-711); the mean of a
    value over a take's segments is weighted by segment length, for the confidence and the no-speech
    estimate of a variant of several segments (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, lines
    249-252).
  - Its defaults are the registration's: `--max-rpm 20`, `--max-attempts 4`, `--variant-timeout-s
    120`, and the language hint from the item's label (`ar` for Saudi, MSA, mixed and none; `en` for
    English). Every request is charged the larger of Groq's 10 s minimum and the clip's length ("The
    cost and the time"; the design's 10.4), and pacing keeps the starts of requests at least 60 /
    `--max-rpm` seconds apart.
  - It was built against Block 0's fakes only (`FakeSpeechToText`, `FakeMatcher`, `FakeGoldenSet`,
    `FakeScorecardWriter`, `FakeHistory`, `FakeTracing`, `fake_normalize`); every other track's
    piece is called by its Block 0 signature, through a `Parts` dataclass whose defaults are the
    real functions: `items.load_items`, `split.load_split`, `matcher.load_matcher`,
    `scorecard.write_scorecard`, `history.append_line`, `GroqSTT.from_settings` (picked through
    `stt.provider`), `Tracing.from_settings`, and `normalize_digits(normalize_arabic(...))`. No
    request was sent and nothing was spent.
  - The worktree checks were tested with a fake `git`, and once with the real git 2.51 in a
    temporary repository (a main checkout and a worktree added with `git worktree add`), with
    `GIT_CONFIG_GLOBAL` pointing at an empty file and `GIT_CONFIG_NOSYSTEM` and
    `GIT_CEILING_DIRECTORIES` set, so no user or system configuration is read. An interrupt is
    tested as Ctrl+C delivers it, `signal.raise_signal(SIGINT)` inside the fake making asyncio's
    runner cancel the run; a probe on this Windows machine showed both that and a raised
    KeyboardInterrupt end in the runner's handler.
  - No talk-over reference appears in its source strings: a scratch check outside the repository
    compared every string constant of its five modules with the 46 normalized references and
    alternates of `voice-lab/recordings/talkover/refs.json` (read as data), and none matched. The
    verdict words in progress lines are `right`, `wrong`, `unjudged`, `provider` and `stuck`. Module
    sizes: `run.py` 365, `run_parts.py` 327, `answerers.py` 378, `worktree.py` 152 and `windows.py`
    78 lines.
  - Deviation: Track E adds two files its Owns line does not name,
    `apps/ole5-voice-agent/src/ole5_voice/evals/run_parts.py` (the run's `Parts`, its `Plan` with
    the audio checks and the digest, the `--clips-from` clip answers, each variant's result and the
    progress lines) and `tests/ole5_voice/evals/test_run_parts.py`: with all of that in `run.py`,
    the file was 693 lines after `ruff format`, over ARCH-SIZE's 400. Only Track E owns the two
    files. The test helpers its test files share are in `test_run_parts.py` (`World`, `FakeClock`,
    `golden_set`) and `test_worktree.py` (`FakeGit`).
  - Deviation: `poe eval` has a flag the plan's list does not name, `--clips-from <scorecard.json>`:
    the same model's first dev run's scorecard, checked to be dev, of this model and at this commit.
    The registration's "A window at least as long as its clip is not sent again; that clip's result
    from the same model's first dev run is used and marked so" needs that run's answers, and no
    listed flag supplies them. Without the flag, and always for held-out clips, such a window is
    sent as the whole clip and marked not reused (the owner's question below).
  - Its debt rows are TD-019 (`answerers.py` near the size cap), TD-020 (the port names no way to
    close an adapter) and TD-021 (every request counted as billed). It changed no row and asked for
    no change to Block 0.
  - Its question for the owner, under Q15: if the windows are taken on all 124 talk-over clips, a
    held-out window at least as long as its clip cannot reuse the clip's answer, since a held-out
    scorecard holds no per-variant answer, so the runner sends the whole clip as that window, marked
    not reused: at most a few requests (only clips under 1 s, at 1000 ms), within the estimate,
    which counts every window as sent. Accept this, or should something else happen for those clips?
  - Not done: the optional `prototype-cache` answerer is not built: it would read
    `voice-lab/eval/_cache/calls.jsonl` by the key `Ole5-chatbot/scripts/stt_eval.py` builds at
    lines 551-552 (the SHA-1 of the WAV bytes, plus the request's JSON with `sort_keys` and
    `ensure_ascii` off, plus `|run<n>`), it does not fit beside the other two (TD-019), and the dry
    run comes only at step 19, so it would go in a module of its own. Nothing was checked against
    the real pieces of Tracks A to D and F, nor live: no request was sent and `poe eval` did not run
    on the real golden set, which steps 15, 21 and 22 do first.
  - At the merge, Track E's one request to the integrator is checked: `run.py` gives Track F's real
    `write_scorecard` an empty sequence of results when the smoke test fails or a held-out run does
    not finish, and the writer takes it, for a dev and a held-out run (a probe in the scratch
    folder: a scorecard of no variant, every rate none, complete false). The history line takes its
    billed seconds and cost from the run's budget, not from the scorecard, so a held-out run's spend
    is counted. Left for step 15 and the review: the runner scores every committed variant
    (`items.load_items`), not only the checked ones `items.accepted()` gives, while the registration
    leaves out a variant the owner has not confirmed; with none confirmed yet, scoring only those
    would leave step 15's reference runs with no variant.
  - After the merge `uv run --offline poe check` passes: 1034 tests, 100% coverage (2959
    statements), mypy strict on 132 files, arch and docs clean.
- 2026-11-01: After Track E's merge, with the tree clean, the runner ran once on the real pieces of
  Tracks A to F in this linked worktree, with no spend: `uv run --offline poe eval --answerer
  reference --split dev` (an empty `--env-file` in the scratch folder, `--out` outside the
  repository) scored 84 of 84 variants right, WER and CER 0, term recall 1, no violation, "one
  speaker"; the same with `--split held-out` scored 36 of 36, its scorecard holding no variant. No
  history line was appended. This is a check at the merge, not step 15, whose test is still to be
  written.
- 2026-11-01: Track G, the recorder, is merged (`Plan 002: merge track G`), from one commit on
  `plan-002-track-g`, cut from 44aa043: 505e753 (`Plan 002: track G, the recorder (poe record) and
  its page`). It replaces Block 0's stub `recorder.py` and adds `recorder_load.py`,
  `recorder_state.py` and the page (`recorder_page/index.html`, `recorder_page/recorder.js`), with
  the tests `tests/ole5_voice/evals/test_recorder.py`, `test_recorder_security.py` and
  `recorder_support.py`; `## Tracks` now names the four files Track G's Owns line lacked, and the
  files the Owns lines of Tracks D, E and F lacked (their deviations). `poe record --out <folder>
  [--session <name> --device <laptop|wired|bluetooth>] [--script] [--replies <folder>] [--audio
  <root>=<folder> ...] [--golden] [--manifests] [--port]` serves the page (plain HTML, CSS and JS,
  nothing from another address) on 127.0.0.1 under a new token each run, and logs the address once,
  in its `recorder_ready` line. From the track's report:
  - The page asks for the speaker's consent first (their name, their own words and an agreement box,
    written as `takes.SessionRecord` in `<session>/session.json`). It records each script line as 16
    kHz mono 16-bit WAV through an AudioWorklet in an `AudioContext` of 16 kHz, requesting echo
    cancellation, noise suppression, gain control and one channel, and plays the agent's reply
    through the chosen output while recording an over-the-agent or echo-only line (the take ending
    with the reply for an echo-only line, and after `seconds` for a fixed-length line). It plays the
    take back from memory, takes each true turn end of a several-clause take (a line with more than
    one clause in `say`) from clicks on its waveform, and saves the take as `<take>.wav` with its
    `TakeSidecar` (the microphone's and the output's labels, the track's settings as the browser
    reports them, kept or discarded); the server refuses any other format with `audio.parse_wav`.
    Its review mode plays each kept take, and each golden-set variant the manifests name below the
    `--audio` roots given, beside its reference; the owner confirms it (`Review`, verdict
    `confirmed`) or types what it says (`typed`), written as `<session>/<take>.review-<pass>.json`.
  - The server answers only its own Host and paths under its token; it takes a POST only from its
    own Origin, as JSON, with a bounded body; it serves only its allow-list, each file looked up by
    ID and sent only when no link leads to it, its bytes are WAV and they match the recorded
    SHA-256; and it writes only new files below `--out`, named by `takes.py`'s helpers.
  - Its sources: the agent replies are read only from `voice-lab/assets/talkover/replies.json` (6
    replies, each with `id`, `lang`, `topic`, `ms` and `file`; the files are 24 kHz mono 16-bit WAV,
    read 2026-11-01), in the lab's folder beside `Ole5-chatbot/`, which the owner gives as
    `--replies`; the six replies pass the recorder's checks (a read-only load). The lab's own
    recorder (`voice-lab/server.py`, `voice-lab/static/`) was neither read nor used, as the decision
    log says. The capture settings are the decision log's; `takes.json` is not on the track's read
    list, so it was not read.
  - Its values, each a constant in the code: the token, 32 random bytes
    (`secrets.token_urlsafe(32)`, 43 characters), compared with `hmac.compare_digest`; `MAX_BODY` 16
    MiB, a take of about six and a half minutes as base64 in JSON; each request's socket timeout 30
    s; `--port` 0 by default, a free port the OS picks; field limits of 200 characters for the
    speaker, 4000 for the consent's words, 500 for device labels and 4000 for a typed text.
  - Its tests, all on made-up WAV bytes and a temporary tree, with a real server on a free port of
    127.0.0.1 in a thread and no device: `test_recorder.py` covers the behaviour (a take saved with
    its sidecar and played back, the consent first and written once, no file replaced, turn ends,
    the review passes, the variants beside their references, review-only, 13 startup refusals, and
    the command); `test_recorder_security.py` the adversarial cases (GP-08): the bind address and
    the token, no outside address and none of the four one-word English references in the page or
    the code, 7 wrong Hosts, 10 wrong or missing tokens, 6 foreign or missing Origins and a doubled
    one, non-JSON POSTs, a body too large or of no or a short length, 7 files that are not 16 kHz
    mono 16-bit and bad base64, POST fields naming paths, 16 GETs off the allow-list, and 70
    traversal targets (encoded and plain `..`, backslashes, absolute paths, absolute-form targets)
    from every route. In the tree a made-up `.env` sits in the checkout above `--out`
    (`var/golden-audio/../../.env`), in the old repository's folder, in each served folder and in
    every folder above them; it is never read, through a folder link (a junction on Windows), a file
    link (skipped on this account) or a hard link. 97 tests in all, 28 test functions (corrected
    by the review of the merged tracks).
  - Its check in a browser, partial: the page was loaded once in the browser pane, with a scratch
    `script.toml` and `--out` in the agent's scratch folder and the lab's replies read only, nothing
    recorded or submitted. It rendered the script from `api/state` with no console error (the
    consent panel shown, Record disabled until the consent, the echo-only cue, the review tab). The
    pane blocks the microphone, so capture, playback and saving through the page wait for a check in
    Chrome.
  - Deviation: the recorder is three modules, not one: `recorder.py` holds the server and the
    command (272 lines), `recorder_load.py` what it reads at start (196) and `recorder_state.py`
    what it holds, writes and serves (364), since one module came to 539 lines after formatting,
    past ARCH-SIZE's 400. For the same reason the tests are three files: `test_recorder.py` (the
    behaviour, 385), `test_recorder_security.py` (the adversarial tests, 399) and
    `recorder_support.py` (the shared tree and client, 282).
  - Deviation: the allow-list also holds the takes below `--out`, each looked up by its take ID
    through its sidecar and sent only when its bytes match the sidecar's SHA-256: the page must play
    a saved take back and review the new takes before step 19's import writes their manifests. The
    plan's allow-list names only the replies `replies.json` names and the variants the manifests
    name.
  - Its debt rows are TD-022 (the page has no automated test) and TD-023 (the symbolic-link case
    skips on the owner's account). It changed no row and asked for no change to Block 0.
  - Its question for the owner: should the recorder refuse a take when the browser reports echo
    cancellation, noise suppression or gain control off for the chosen microphone, instead of saving
    it with the page's warning and the sidecar's record (the agent's choice)? Refusing would block a
    sitting on a device whose browser reports one off.
  - Not done: the page in Chrome (WORKING-RULES.md, "Seeing it run"): recording a take, playing it
    back through the chosen output, the waveform's marks, and saving the consent, a take and a
    review through the page are unchecked, and so are whether Chrome runs the microphone through an
    `AudioContext` of 16 kHz and the worklet (UNVERIFIED) and `setSinkId` on the output.
    `.claude/launch.json` for the recorder was left to the integrator (the following commit). The
    no-item-in-source rule was checked by the track only for the four one-word English references;
    Track D's test, merged first, now reads the recorder's files too, and passes. Reviewing real
    golden-set variants needed Track D's `items.load_items`, merged first: the recorder's default.
  - At the merge, the committed `script.toml`'s echo-only lines name the lab's replies ar_inbox and
    en_signature, so `poe record` refuses to start without `--replies` ("give --replies"), which the
    owner's step 4 below did not give (a probe of `load_recorder`, which starts with the lab's
    folder given; fixed in the following commit).
  - After the merge `uv run --offline poe check` passes: 1129 tests and 1 skipped (the symbolic-link
    case), 100% coverage (3423 statements), mypy strict on 136 files, arch and docs clean.
- 2026-11-01: Review fixes, track G (`Plan 002: review fixes, track G`):
  - "What the owner does", steps 4 and 5, give `poe record` the `--replies` folder it needs to start
    (the lab's `voice-lab\assets\talkover`, beside the main checkout), and step 5 gives the review
    mode's command, with `--audio talkover=` the lab's recordings folder, so the talk-over variants
    are reviewed too; the commands were checked by loading the recorder with the committed script,
    which starts with the lab's replies folder given and refuses without it.
  - `.claude/launch.json` is added, as WORKING-RULES.md's "Seeing it run" asks with the first such
    surface and Track G left to the integrator: `git check-ignore` does not ignore it, so it is
    committed. Its one configuration, `recorder`, runs `uv run --offline poe record --out
    var/recorder-preview --session preview --device laptop --replies ../voice-lab/assets/talkover
    --port 8765` from the main checkout (a folder under the git-ignored `var/`, and the lab's
    replies by a path relative to the checkout, so no drive or user name), and opens
    `http://127.0.0.1:8765`; the page itself is at the address with the token that the
    `recorder_ready` line logs, since the server answers nothing else.
  - Not done here: the page in Chrome (Track G's report), which needs the microphone: recording,
    playing back, the waveform's marks and saving through the page are still unchecked.
  - `uv run --offline poe check` passes: 1129 tests and 1 skipped (the symbolic-link case), 100%
    coverage, mypy strict on 136 files, arch and docs clean.
- 2026-11-01: Track H, the docs, is merged (`Plan 002: merge track H`), the last track, from three
  commits on `plan-002-track-h`, cut from 44aa043: 560a1c2 (the guide's evaluation page), 179634a
  (the method doc's paths) and c7caa0c (the evaluation page's review fixes), each gated before it
  was made. `docs/guide/evaluation.md` is new (219 lines): the evaluation helpers of
  `t2_agentic_voice.languages` and `t2_agentic_voice.evals`, with what each takes and gives, pooling
  and the inputs they refuse; recording a set with every speaker's consent; keeping audio out of
  git; writing a team's own spelling guide, with Ole5's as the example; and noise and the sign test.
  The guide's index links it (its `evaluation.md` row), and its status line says M1 builds the first
  public modules instead of "designed but not built". In `docs/design/evaluation.md`, the paragraph
  "Nothing here is built yet" becomes "Where it is built": the scorers in the library, and Ole5's
  golden set in the app, with its code (`apps/ole5-voice-agent/src/ole5_voice/evals/`), data
  (`apps/ole5-voice-agent/evals/`, the `evals/` of the doc's paths) and tests
  (`tests/ole5_voice/evals/`), its commands in CLAUDE.md, and the guide's page; in the suggested
  layout, `scripts/eval/` becomes the app's own package (`ole5_voice.evals`), as the decision log's
  first entry asks. From the track's report:
  - Its sources: the design's 9.7, 14 and 15; evaluation.md; D-006, D-021 and D-022; Track A's
    signatures as Block 0's stubs and their docstrings give them (`domain/text/arabic.py`,
    `digits.py`, `spelling.py`, `rulings.py`, `domain/scoring.py`, `domain/recall.py`,
    `domain/sign_test.py`, `testing/scorers.py`, and the `languages` and `evals` facades);
    `models.py` and `takes.py` for the manifest, the consent and the session record; this plan's
    decision log (the verdict with spaces removed, the consent entry, one speaker), its registration
    (the smallest detectable change, c = 6 with no noise) and Q8 (Ole5's spelling rules). No
    prototype file was read: its May read names none.
  - Its two code samples are copied word for word, with their indentation removed, from
    `tests/ole5_voice/evals/test_models.py`, lines 119-139
    (`test_a_manifest_holds_its_consent_and_files`, a manifest with its consent), and
    `tests/t2_agentic_voice/domain/test_rulings.py`, lines 11-17 (`RULING`). A scratch script
    outside the repository checked each block against its source file, with the line lengths (prose
    at most 100 characters), LF endings, and the page's lines against the four one-word English
    references: 0 problems. Values on the page: the sign test table (b = 6, w = 0: 2/64 = 0.03125; b
    = 5, w = 0: 2/32 = 0.0625; b = w: 1), worked from evaluation.md's formula, which matches Track
    A's tests; c = 6 with no noise, the registration's. At the merge both samples still match their
    sources, at the same lines (a scratch check).
  - Deviation: Track H's Goal asks for a link to Ole5's `spelling.toml`; on the track's branch the
    page named it in backticks, since Track D creates the file and a link to it would have failed
    DOC-LINK there. Track D merged first, so the link, and one to Track D's `test_no_audio.py`, is
    made in the following commit, as the track's report gives it.
  - Its debt row is TD-024 (code samples compared with their sources by review only), the row the
    decision log's sample-check entry says is written at Track H's merge. It changed no row, asked
    for no change to Block 0 and left no question for the owner.
  - Not done: the page was not checked against Track A's built helpers (it describes Block 0's
    contracts, the stubs' docstrings and the plan's Track A test cases), so the review of the merged
    code compares its helper table and sign test values with Track A's code and tests; and its text
    was not checked against every talk-over reference, since `refs.json` is outside the track's May
    read (Track D's test does not read `docs/`).
  - After the merge `uv run --offline poe check` passes: 1129 tests and 1 skipped (the symbolic-link
    case), 100% coverage (3423 statements), mypy strict on 136 files, arch and docs (25 files)
    clean.
- 2026-11-01: Review fixes, track H (`Plan 002: review fixes, track H`): `docs/guide/evaluation.md`
  links Ole5's `spelling.toml` and `test_no_audio.py`, Track D's files, as Track H's report gave the
  change, with both paragraphs rewrapped to 100 columns; and its `normalize_digits` row says that a
  run of single digits with only spaces between them becomes one number (`4 5 2 1` reads `4521`), as
  Track A's decision log entry has it, which the row, written from Block 0's docstring, left out.
  The rest of the helper table is left to the review of the merged code (Track H's report). `uv run
  --offline poe check` passes: 1129 tests and 1 skipped (the symbolic-link case), 100% coverage
  (3423 statements), mypy strict on 136 files, arch and docs (25 files) clean; `uv lock --check` is
  clean. All eight tracks are merged into `plan-002-integration`. Next: the one review of the merged
  code by three concerns, its fix round and check (step 16, as the owner chose), and step 15's
  `test_reference_answerer.py`.
- 2026-11-01: Review fixes, the merged tracks (`Plan 002: review fixes, the merged tracks`), the
  one review of the merged code the owner chose ("Yes, go lighter"), which stands as step 16's
  review of the code before the main branch. Three agents reviewed `plan-002-integration` at
  5791767 by concern: security; measurement; harness and faithfulness. They raised 43 findings.
  The 13 high and medium ones (3 high, 10 medium) and 4 low ones were checked by an agent told to
  refute them: all 17 held, none was refuted. Three findings were raised by two or three reviewers
  (the owner's commands, the unchecked variants, the multipart boundary), so the 17 come to 13
  distinct defects. 16 are fixed here; one, on ID recall, goes to the owner (below). The other 26
  low findings, unverified, were each checked against the code here: all 26 are real; 22 are
  fixed, 2 in part with the rest as debt rows, 1 is a debt row only, and 1 goes to the owner. The
  fixes, each with its tests (a failing test first for each bug, adversarial ones for the security
  fixes) and each choice in the decision log:
  - The owner's recording and review commands ("What the owner does", steps 4 and 5) held control
    characters where Track G's fix wrote backslashes; they are written with forward slashes, and a
    docs rule, DOC-CONTROL, now refuses a control character in a doc (the byte scan of the merged
    plan gives its lines 2916, 2930 and 2931).
  - `poe eval` scores only the variants the owner has checked, as `poe golden` accepts them, and
    logs how many it left out as a count (`run_parts.load_plan`). Step 15's
    `tests/ole5_voice/evals/test_reference_answerer.py` is written: the reference answerer over
    each split of the committed set, with made-up confirmations, scores 84 of 84 dev and 36 of 36
    held-out variants right, inside `poe check`.
  - A `groq` run names `--model` and `--timeout-s`, and its base URL is `--base-url` or the SDK's
    own, whatever the environment holds; the runner times requests with `time.perf_counter`, since
    `time.monotonic` moves in 15.6 ms steps on this machine; a run's note may hold no install
    placeholder; `history.line_of` is the one definition of a history line, with the run's spend.
  - The matcher also counts a variant right on the texts' joined form (spaces removed before the
    digits are read), so "some one" is "someone" again, as Q8 rules; text from silence counts the
    letters of a digit's name; `normalize_digits` reads a vowelled digit name on its own.
  - `GroqSTT` cuts every body with its own random boundary and refuses one cut by a
    `GROQ_CUSTOM_HEADERS` content-type line, so audio can add no form field; its constructor
    validates through core's `GroqSettings` and `SttSettings`, so it refuses what the settings
    refuse, with their messages.
  - The OTLP exporter's session replaces the headers before requests checks them, so a `%0A` in
    `OTEL_EXPORTER_OTLP_HEADERS` no longer puts a token in an ERROR line and drops every batch; the
    private provider moved to `core/tracing_export.py`, with its tests in `test_tracing_export.py`
    (now also the 1 s delay, the 2 s export timeout, a turn's empty parent context and all eight
    limit variables); attribute keys are redacted too.
  - The re-checks of a scorecard and a history line serialize with pydantic's warnings off, whose
    text quoted a refused value on stderr; a scorecard listing a variant twice is refused as it is
    read; the suite drops requests' CA bundle variables and gives requests an empty `.netrc`.
  - Corrected in place, each marked so: Track A's lines on format characters, its Arabic
    constants and a lone digit name; Track B's counts (27 failure cases, four `GROQ_CUSTOM_HEADERS`
    variants); Track C's (11 test functions); Track F's (11 stratum values, the WER and CER calls
    checked) and its decision line on its errors; Track G's (97 tests, 28 functions); the guide's
    rows for `normalize_arabic`, `spelling_issues` and `silence_output`; the citations of the two
    rows paid.
  - The registration gains its first three amendments, dated and before any run: the arms' command
    lines name `--model` and `--timeout-s 6` (values unchanged); the verdict's joined form, the
    characters of text from silence and the definition of latency; and that a run scores the
    checked variants only.
  - Deviation: step 15's command-line runs on the committed set are now refused ("the run has no
    variant the owner has checked") until the owner's confirmations are imported, so they are made
    again at step 19 (its text says so); the integrator's check after Track E's merge scored every
    committed variant, unconfirmed ones included.
  - Debt: the `GROQ_CUSTOM_HEADERS` row (the multipart boundary) and the size-cap row of
    `core/tracing.py` and its test file are paid and removed; TD-004 gains the Windows registry
    proxy, TD-005 the fork-time read of `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` and the corrected
    header sentence, TD-008 the format characters that raise WER (pinned by a test), and TD-014 the
    queue's new place. New rows: TD-025 (`spelling_issues` misses an avoided spelling with an Arabic
    prefix; the guide says so), TD-026 (`eval-compare` refuses no other differing setting) and
    TD-027 (httpx imported but not declared, which needs a `uv add` this round may not run).
  - To the owner: (1) When the speech-to-text writes a ticket number in pairs, for example "48 21"
    or "48-21" for 4821, should ID recall count the number as heard? The verdict already counts it
    right, but Track A's rule treats "45 21" as two numbers, so ID recall counts it as missed. And
    may the thousands-separator case ("4,821", «٤٬٨٢١»), which the checker proposed fixing now, be
    fixed as proposed? (2) A held-out scorecard's breakdown value or window group of one item (the
    committed split has held-out `mixed`, `confirmation` and `short_request` strata of one item
    each, and the finding counts 7 of 9 held-out window groups so) publishes that item's accuracy in
    the committed history: should such groups be pooled or left out below a registered size, say 3
    items, in a dated amendment before H1?
  - `uv run --offline poe check` passes: 1176 tests and 1 skipped (the symbolic-link case), 100%
    coverage (3471 statements), mypy strict on 143 files, arch and docs (25 files) clean. Next:
    the owner's answers above and step 16's merge into the main branch.
- 2026-11-01: Step 15, the integration check with no spend (`Plan 002: the integration check with
  no spend (step 15)`), in this linked worktree at cb8e87d with the tree clean, each run with an
  empty `--env-file` and its `--out` in the agent's scratch folder, outside the repository:
  - `uv run --offline poe eval --answerer reference --split dev`, and the same with `--split
    held-out`, are refused before any folder is made (exit 2, "the run has no variant the owner
    has checked"), as step 15's deviation says: `unchecked_left_out` gives 84 of 84 dev and 36 of
    36 held-out variants left out, since the owner has confirmed none yet (Q9).
  - The same two runs through the runner's own `Parts`, as step 15's test makes them: a scratch
    script outside the repository calls `run.main` with the same arguments and a `load_items` that
    gives each committed variant a made-up confirmation in memory (no file written, no variant
    accepted), with the real worktree checks, items, split, matcher and scorecard writer. Dev: 84
    of 84 variants of 30 items right, accuracy 1, WER and CER 0, term recall 1, ID recall none (no
    committed item is a ticket number), 0 failures, 0 requests, cost 0, no violation, "one
    speaker", complete. Held-out: 36 of 36 variants of 13 items right, the same totals, its
    scorecard holding no variant. Together they cover the 120 committed variants of the 43 items.
    Neither run appended a history line (`history.jsonl` byte for byte as committed, as the plan
    and `run.py`'s `spends` say), so there was nothing to restore.
  - `tests/ole5_voice/evals/test_reference_answerer.py`, written by the review of the merged
    tracks, now also fails when the run reads an audio file (`read_wav` replaced in `audio`,
    `answerers` and `run_parts`; a scratch mutant of the reference answerer that reads one fails
    it, reverted) and checks that no history line is written beside the scorecard either.
  - No bug was found and no code changed. The command-line runs on the confirmed set are made at
    step 19, as step 15 says.
  - `uv run --offline poe check` passes: 1176 tests and 1 skipped (the symbolic-link case), 100%
    coverage (3471 statements), mypy strict on 143 files, arch and docs (25 files) clean.
- 2026-11-01: The integrator's own check of the merged branch, and the recorder's page in a
  browser (`Plan 002: review fixes, the check and the recorder's page`):
  - The gate, run again by the integrator at 2644858, passes as the check said (1176 tests and 1
    skipped, 100% coverage), and `uv lock --check` is clean.
  - The page, served by `poe record` from this worktree with `--out` in the agent's scratch folder,
    opened in the desktop app's browser pane, which gives the page no microphone. It loads with no
    console error and lists the script's 52 lines; the consent form saves `session.json`; the
    lines, their clauses and cues show; the server answers a request with no token, another `Host`
    or another `Origin` with 403. In review mode (`--audio talkover=` the lab's recordings), 120
    variants are due; a click on Play fetches the variant's WAV, and "It says this" and a typed
    text each write their `review-1.json` under `--out` and update the count. Not checked, since
    the pane has no microphone: recording, playback of the reply while recording, saving a take,
    the turn-end marks and the device lists. The owner's first sitting (step 17) is their check.
  - Fixed from the page: a playback the browser refused (also a `NotAllowedError`) was reported as
    the microphone being refused; it now says the browser did not let the page play it. The two
    echo-only lines' cue in `script.toml` ("Say nothing while the reply plays.") repeated the
    sentence the page writes from the line's reply, so the cue is removed (the script is still the
    draft Q4 approves).
  - Fixed from the check of the review's fixes (its three lows): DOC-CONTROL now also refuses a
    lone carriage return, the escape that split step 5's line, reading the doc's bytes rather than
    its text with universal newlines (a test case added); a setting's name or value and the model,
    which go into the committed history as the note does, are refused when they hold an install
    placeholder, by the models (`runs.Shown`, `runs.Plain`) and by `poe eval` before anything is
    sent (tests in `test_history.py` and `test_run_pinned.py`, each failing on a mutant first);
    and a test comment named a file that does not exist.
  - Deviation: the step to start the page with `.claude/launch.json` was not used. The desktop
    app's preview started the `ole5` entry of the launch file in the folder above the repository
    (the chatbot, read-only under D-010) instead of `recorder`; it ran for 8 seconds and was
    stopped, and the chatbot's checkout and the Phoenix folder show no change. The page was started
    with `poe record` itself and opened at the address its `recorder_ready` line gives.
  - `uv run --offline poe check` passes: 1180 tests and 1 skipped (the symbolic-link case), 100%
    coverage (3476 statements), mypy strict on 143 files, arch and docs (25 files) clean; `uv lock
    --check` is clean. Next: the owner's answers and step 16's merge into the main branch.
- 2026-11-01: The owner answered the eight questions of the merged tracks and their review, and
  Q4, Q5 and Q9 ("The owner's decisions"); Q7 is put again, as a list. Three answers change code
  and are built in linked worktrees cut from `plan-002-integration` at 736c3f1, each checked by
  an agent told to refute it: ID recall over a number's groups (`plan-002-answers-idrecall`),
  held-out groups under 3 items pooled (`plan-002-answers-heldout`), and the approved script with
  the ticket shape plus the guide's note on the variables to leave unset
  (`plan-002-answers-script`). The rest is recorded in the decision log. The owner's consent for
  the talk-over set waits on the owner's sentence.

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
  report. Block 0's review wrote the debt rows it found as the `GROQ_CUSTOM_HEADERS` row (paid
  since) and TD-003 to TD-007 (no other session had taken a number: the main branch's
  `docs/plans/tech-debt.md` ends at TD-001); the integrator keeps those numbers at the merge, or
  renumbers them and every citation in this plan in the same commit (step 14).
- 2026-11-01: Step 2 read the installed groq 1.7.0 as text for every `GROQ_*` variable it reads,
  the counterpart of the list above; Track B works from it (added in Block 0's review).
  - **Kept out by passing a value:** `GROQ_API_KEY` and `GROQ_BASE_URL` (`groq/_client.py`,
    lines 80-91 and 293-304).
  - **Read whatever is passed:** `GROQ_CUSTOM_HEADERS`, on every client built (lines 93-100 and
    306-313), whose headers sit under any `default_headers` given but over the `Authorization`
    header the SDK builds from the key (`groq/_base_client.py`, lines 672-680), so a value naming
    `Authorization` replaces the key, and any other header it names goes with every request (its
    debt row, paid since); and `GROQ_LOG`, read when `groq` is imported (`groq/_utils/_logs.py`,
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
  reports, narrowing the `GROQ_CUSTOM_HEADERS` row (paid since) and TD-003.
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
  - The debt rows keep the numbers the first fixes gave them, the `GROQ_CUSTOM_HEADERS` row (paid
    since) and TD-003 to TD-007, since the main branch's tracker ends at TD-001; step 14's rule,
    that the integrator numbers a track's rows, still holds for the tracks.
  - `## Tracks` names Block 0's test files one by one, the ones the first fixes added
    (`test_runs.py`, `test_takes.py`, `tests/harness/test_import_isolation.py`) with the rest,
    so a track that needs one changed asks the integrator, as for `models.py`.
  - `requests` is recorded in D-023's Proposed bullet, which is new on this branch, as jiwer's
    owner row is in D-019, since CLAUDE.md's first non-negotiable puts a rule's reason in a
    decision.
- 2026-11-01: Track A's digit names: `normalize_digits` reads English zero to nine and Arabic صفر،
  واحد، اثنين، اثنان، ثلاثة، أربعة، خمسة، ستة، سبعة، ثمانية، تسعة. Each is matched as a whole word
  after `normalize_arabic`, so case and the folded letter forms do not matter. These are the forms a
  digit is read by, one at a time. The short forms (ثلاث، أربع، خمس، ست، سبع، ثمان، تسع) and dialect
  spellings (اتنين، تلاتة، تمنية) are left out: several short forms are also everyday words (ست,
  سبع, تسع, خمس), so adding any is a ruling for the owner or a measured change (GP-18). The agent's
  choice (TD-010).
- 2026-11-01: Track A: a run of single digits, each a digit name or one written digit (any mix),
  with only whitespace between them, becomes one number: «أربعة خمسة اثنين واحد», "four five two
  one" and "4 5 2 1" all read 4521. This extends the design's 8.2 ("runs of digit words ...
  collapsed into digits") to written single digits, so that a provider's "4 5 2 1" matches a
  reference's 4521 in WER and in ID recall, as it already does in the verdict, which removes spaces.
  A number of two or more digits is never joined to its neighbour ("45 21" stays two numbers): that
  is a number said as a number, not digit by digit. The agent's choice.
- 2026-11-01: Track A: a digit name on its own becomes its digit too ("one moment" reads "1
  moment"), on both sides of every comparison, since the guide writes numbers as digits (Q8). The
  verdict counts a lone name as its digit; that reading also made a word written in two another text
  ("some one" against "someone"), against Q8's spaces ruling, which this line first said it left
  unchanged, so the matcher now also compares the texts' joined form (the review of the merged
  tracks, its decision entry). ID recall then counts such a digit as an ID, but it is reported over
  the ticket-number items only. The agent's choice.
- 2026-11-01: Track A: `normalize_digits` changes only the digits and the digit names, leaving every
  other character, space and punctuation as written. The scorers call `normalize_arabic` first
  (`scored_form` in `domain/scoring.py`, internal to the library and in no facade, since Block 0's
  facade names are fixed), so punctuation between digits ("5, 7") is a space by then and the run
  joins. Track D's matcher composes `normalize_arabic`, `normalize_digits` and the removal of spaces
  itself, through `languages`.
- 2026-11-01: Track A: `spelling_issues` returns one issue per avoided spelling found, however often
  the reference holds it, ordered by rule and then by the rule's own spellings, the shape of Block
  0's `FakeSpellingCheck`. `found` is the spelling as the rule writes it; when several of a rule's
  spellings normalize alike (`test_rulings.py`'s أوتلوك and اوتلوك), it is the first of them. Every
  rule is checked on every call. A ValueError naming the rule's id is raised for an avoided spelling
  that is empty after normalization (it could never be found), and for one that the rule's own
  `write` holds after normalization (a case-only ruling such as pdf to PDF, or ة to ه, would flag
  every reference that follows it). The agent's choice: GP-06, a guide no reference can follow fails
  loudly.
- 2026-11-01: Track A: `term_recall` counts each distinct term once, matched as whole words in the
  scored form, however often a text holds it and however many listed terms normalize to it; it
  raises TypeError for a term that is not a str, and ValueError for a term that is empty after
  normalization. `id_recall`'s IDs are the runs of [0-9] in the scored form (`normalize_arabic`,
  then `normalize_digits`; Block 0's stub docstring named only `normalize_digits`), digits inside a
  word included (t1234), counted as a multiset: an ID the reference holds twice is expected twice.
  `silence_output` is the length of the scored form with its spaces removed. The agent's choices.
- 2026-11-01: Track A: `wer` and `cer` also refuse with a ValueError an empty pair of sequences
  (jiwer would return 0 for ([], [])), two sequences of different lengths and any non-str inside
  them. So Track F calls them only for a stratum with at least one reference that is non-empty after
  normalization, and reports no rate otherwise. A reference of only punctuation counts as empty; a
  caller can test this with `silence_output(reference) == 0`, which uses the same form. The agent's
  choice.
- 2026-11-01: Track A: `sign_test` sums the binomial terms exactly in integers (each C(n, i + 1)
  from C(n, i)) and divides once, so every case up to 40 by 40 equals evaluation.md's formula in
  exact fractions rounded to a float. Very lopsided large counts underflow to 0.0 (5000 better and
  none worse). A count that is not an int, or is a bool, raises TypeError; a negative count raises
  ValueError. The agent's choice.
- 2026-11-01: Track A: `normalize_arabic` keeps the prototype's behaviour exactly, including what it
  does not do: no Unicode composition step, `str.lower` rather than `casefold`, and invisible format
  characters read as spaces. The characterization table rules the port, and folding more would be a
  new ruling or a measured change (the decision log's normalizer entry). The cases are pinned by
  tests and listed as debt (TD-008).
- 2026-11-01: Track B: the request hook rebuilds every request's headers from scratch, eight of
  them, each with the adapter's own value: Host from the URL; Accept `application/json`;
  Accept-Encoding `gzip, deflate`; Connection `keep-alive`; User-Agent the SDK's own; Content-Type
  and Content-Length read from the multipart body itself (it opens with `--<boundary>`, RFC 2046);
  and Authorization `Bearer` with the settings' key. The plan's version only dropped names outside
  an allow-list and then set Authorization, which would leave a `GROQ_CUSTOM_HEADERS` line free to
  change an allowed header's value: Host, Content-Length and User-Agent all reached the request in a
  probe with made-up values. The SDK's X-Stainless-* telemetry headers (OS, architecture, Python
  version, retry count, read timeout) are dropped as not needed. The agent's choice.
- 2026-11-01: Track B: a `ProviderError` is raised after the except block, and `from None`, so it
  has no `__cause__` and no `__context__` either (`from None` alone still leaves `__context__`
  pointing at the SDK's error, which holds the request and its headers). Its details hold only the
  failure's class name and the HTTP status, if any. The agent's choice, the same pattern as
  `Settings.from_env`.
- 2026-11-01: Track B: how failures map to kinds, following the SDK's own retry rule
  (`_should_retry`): 429 is `rate_limited`; 408 is `timeout`; 409 and 5xx are `server_error`,
  retryable; every other status is `rejected`, 3xx included, since redirects are not followed. An
  httpx timeout, or the adapter's own deadline, is `timeout`; any other connection failure is
  `connection_lost`. An answer the adapter cannot read is `server_error`, not retryable: one that is
  not JSON, has no text, or gives a no-speech estimate outside 0 to 1 or a value that is not a
  number. Any other exception is mapped the same way. `retry_after_s` is read from `retry-after`
  only when it is a finite number of seconds, 0 or more; an HTTP date or anything else gives None,
  and the runner's 20 s floor applies. The agent's choices.
- 2026-11-01: Track B: the whole request is bounded by `asyncio.timeout(stt.timeout_s)`, on top of
  httpx's timeout (the same value, passed to the SDK as the baseline requires): httpx's timeout is
  per phase, and the setting is documented as the longest one transcription request may take. The
  agent's reading.
- 2026-11-01: Track B: `follow_redirects=False` on the adapter's httpx client, since httpx runs
  request hooks on every request of a redirect chain, so the hook would put the key on a request to
  another host.
- 2026-11-01: Track B: the constructor refuses what the settings refuse, for a team that builds the
  adapter in code, each as a `ConfigurationError` naming the setting, never the value: a blank key;
  a key with a character no key holds; a model other than the two; a base URL that is not https with
  a host, or that holds a user name, password, query, fragment or bad port; a timeout that is not
  finite and above 0. The agent's choice: the key travels with every request, and settings
  validation does not run on direct construction.
- 2026-11-01: Track B: the fake-transport keyword the plan allowed is `transport:
  httpx.AsyncBaseTransport | None = None`, on `__init__` and on `from_settings`. It names an httpx
  type, not a groq one, so the design's 5.3 holds; a test checks that no public signature names a
  groq type.
- 2026-11-01: Track B: what the `Transcript` holds. `text` is Whisper's text with the space around
  it removed (the prototype's `.strip()`). `language` is the language the request named, or else
  Groq's `language` as it comes (TD-011). `confidence` and `no_speech_prob` are weighted over only
  the segments that give each value, and are None when none does, where the prototype used -1.0 for
  a missing confidence: the port asks for the provider's confidence "when it gives one".
  `no_speech_prob` is not rounded, where the prototype rounded it to 3 places, so the silence rule
  can be rescored (Q2). An empty `language` or `prompt` counts as none and is not sent. The agent's
  choices.
- 2026-11-01: Track B: `GroqSTT.__repr__` shows the model, the base URL and the timeout, never the
  key.
- 2026-11-01: Track B: `GROQ_LOG` is not undone in the adapter, since `harness.toml`'s `[[owners]]`
  gives `logging` to `core` alone (ARCH-OWNER). Track B tests it in child processes instead: a
  control (importing `groq` with `GROQ_LOG=debug` adds a root handler and sets both loggers to
  DEBUG), the adapter imported without the variable (nothing changes), and the adapter imported with
  `debug` and `info`. The last two are `xfail(strict=True)` naming TD-003, so they fail the run once
  the fix lands and their mark is removed. The fix is the track's request for a change to Block 0's
  `core/logging.py`.
- 2026-11-01: Track B's request for Block 0, applied at its merge: `core/logging.py` gains
  `logging_unchanged(*names)`, a context manager that removes and closes a handler added to the root
  logger inside it and puts each named logger's level back, even when the block raises; the adapter
  imports `groq` inside it, naming `groq` and `httpx`. It fits the design's 10.2: the library still
  never adds a root handler or calls `basicConfig`, and only a handler added during the import is
  removed. An app that imports `groq` before the library, or sets its root logger to DEBUG, still
  gets the SDK's logging (TD-003). The integrator's choice, as the track proposed.
- 2026-11-01: Track C: the private provider's queue and timeouts (the plan left the values to the
  track): a queue of 512 spans, batches of 128, at most 1 s in the queue, 2 s per export with the
  exporter's retries included, and 3 s for `shutdown`. A span that cannot be queued (the queue is
  full, or `shutdown` has run), a batch whose export fails or raises, and what is still queued when
  `shutdown` gives up are all counted in `dropped_spans`, and never raised. The failure is logged
  once per run of failures, as `span_export_failed`, by the failure's type only. The agent's choice;
  the reasons are in the progress log.
- 2026-11-01: Track C: the batch processor is the library's own (`_Queue` in `core/tracing.py`: a
  bounded deque and one daemon worker thread), not the SDK's `BatchSpanProcessor`, since the SDK's
  processor counts no dropped span unless `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED` turns its
  metrics on, and its `shutdown` passes no timeout, so a hung exporter holds it for 30 s. The
  library's processor reads no `OTEL_BSP_*` variable at all (GP-10: built for correctness and
  observability). Alternative: the SDK's processor with its private
  `_batch_processor.shutdown(timeout_millis=...)` and private queue length, set aside because both
  are private. The agent's choice.
- 2026-11-01: Track C: span kinds. The turn is CHAIN and speech-to-text is LLM: OpenInference 0.1.43
  has no speech kind, and LLM carries `llm.model_name`, which Phoenix shows. The audio seconds,
  billed seconds, language sent and language returned use the library's own `stt.*` names, mirroring
  Block 0's `FakeTracing` keys. The agent's choice.
- 2026-11-01: Track C: the span `turn` yields is a wrapper of the library's own (`_RedactedSpan`),
  so the team's own attributes, event names and attributes, link attributes, name changes and status
  descriptions on it pass through the `Redactor` too ("every text attribute", the design's 10.1). A
  bytes value (audio, say), a mapping and a nested or mixed sequence are dropped. The agent's
  choice.
- 2026-11-01: Track C: an exception leaving a span sets status ERROR, described only by the
  exception's type name, and sets `error.type`; `record_exception` on the yielded span adds an
  `exception` event holding only `exception.type`. The exception's message and stack trace are never
  exported, since they may hold a secret or what was said (invariants 5 and 8), and the exception
  reaches the caller unchanged. The agent's choice.
- 2026-11-01: Track C: the `Redactor` collects every match of every pattern in the original text and
  replaces each stretch that any pattern matched with one marker, so overlapping patterns leave no
  piece behind, the replacement is never matched again or expanded as a template, and an empty match
  hides nothing; applying `re.sub` pattern by pattern would let a four-digit pattern leave two
  digits of a ten-digit number. It refuses a bare str with a TypeError, a pattern that does not
  compile raises `re.error`, and its repr shows no pattern. The agent's choices.
- 2026-11-01: Track C: `Tracing` gains a keyword-only constructor, `Tracing(tracer_provider=None,
  exporter=None, project=None, redactor=None, include_transcripts=True)`. `Tracing()` is off, as
  Block 0's stub test and `FakeTracing` assume. An `exporter` gets the private provider and its
  bounded queue, which is also how the tests reach that path with the in-memory exporter; giving
  both a provider and an exporter is a ValueError. The signatures in Block 0's decision entry
  (`from_settings`, `turn`, `speech_to_text`, `record`, `dropped_spans`, `shutdown`) are unchanged.
  A team's own provider is used as given, never shut down, and given no resource or processor by the
  library. The agent's choice.
- 2026-11-01: Track C: the exporter's own `requests.Session` replaces every request's headers with
  Content-Type `application/x-protobuf` and User-Agent `t2-agentic-voice/<version>`, then recomputes
  Content-Length (in `prepare_request`), since the exporter adds `OTEL_EXPORTER_OTLP_HEADERS` (or
  its `_TRACES_` form) under the headers it is given, and requests adds a `.netrc` login. After the
  exporter is built, requests' defaults (`verify` True, `cert` None) are put back on the session,
  because the exporter's transport sets them from the certificate and client key variables.
  `trust_env` is left as it is (TD-004). The agent's choice.
- 2026-11-01: Track C: while the library builds its OTLP exporter, a logging filter of that call's
  own on the `opentelemetry.util.re` logger drops that logger's records, and is removed afterwards:
  the SDK logs a malformed header-variable entry with its text, a token among them, and the session
  sends none of those headers anyway. This is a filter on a third-party logger for the length of one
  constructor call, not a handler, and no root logger is touched (the design's 10.2). The agent's
  choice.
- 2026-11-01: Track C: `OTEL_SDK_DISABLED` is not overridden, since only the SDK's private
  `_disabled` flag could do it. When the private provider gives a no-op tracer, the library logs
  `tracing_disabled_by_sdk` with `fix="unset OTEL_SDK_DISABLED"`, and the variable stays in TD-005.
  Its effect fails safe: no span leaves the process. The agent's choice, for the owner to rule on
  (the progress log's question).
- 2026-11-01: Track C: the private provider passes `ParentBased(ALWAYS_ON)`, the SDK's own default,
  explicitly, so a library span under a team's unsampled span is not sampled either. The turn span
  is started on an empty `Context()`, so an app's current span never becomes its parent. The agent's
  choice.
- 2026-11-01: Track D: the lab's kinds map to the golden set's, so the kind breakdown lines up with
  the new recordings: `sentence` and `unscripted` become `request`; `backchannel` becomes
  `listening_sound`; `command` becomes `stop_word`, for wait commands too; `confirm` becomes
  `confirmation`; the lab's `request` becomes `repeat_request` when its want is `repeat`, otherwise
  `short_request`. The lab's `want` label is kept in `Item.want`. No kind holds a reference's words.
  The agent's choice.
- 2026-11-01: Track D: a talk-over variant is one take, and its ID is the take's name. Its device is
  `laptop` (the microphone, as the decision log rules), and its session is `talkover-<date of
  recorded_at>`. Its tags are its condition (`duck` or `pause`), `playback-<speakers|headset>`, and
  `over-assistant` when its first segment began over the assistant: the first segment holds the
  take's start and its windows. The agent's choice.
- 2026-11-01: Track D: the independent check, the agent's encoding of Q9's proposal. A variant is
  checked once it has at least one confirmation. A typed review makes its text the reference and
  drops every earlier confirmation, and only a confirmation in a later pass counts, so the typing is
  a typed reference's first act and its confirmation the second. A text the owner typed in the lab
  counts as typed before any recorder pass, so one later confirmation checks it. Two reviews of one
  take in one pass are refused, and so is an empty typed text.
- 2026-11-01: Track D: the talk-over's reviews are read from the recorder's `--out` as
  `takes.review_file(variant.session, variant.id, pass)`, that is
  `<out>/talkover-2026-10-27/<variant>.review-<n>.json`, through `import_talkover`'s `--reviews`
  option; Track G's review mode writes them there. `import_recordings` skips a folder that holds
  only reviews, and refuses one that holds takes or WAVs with no `session.json` (the consent).
- 2026-11-01: Track D: each language of an Arabic talk-over phrase is the agent's proposal, written
  as `PROPOSED_LANGUAGE` in `import_talkover.py` (TD-016): 23 saudi, 7 msa and 4 mixed. msa: s01,
  s05, s09, k03, r04, y01, y04; mixed (Arabic with a Latin product term): s03, s04, s11, s12. Each
  Arabic item file carries a DRAFT comment until the owner rules (Q7). English phrases are
  `english`, from the lab's label.
- 2026-11-01: Track D: `spelling.toml` has two parts. `[[rulings]]` holds Q8's rules split into five
  comparison rulings (letter-forms, digits, english-case, punctuation, spaces) and four on
  references (product-terms, numbers, contractions, listening-sounds), each with the agent's
  approved wording, the owner's words "Use these rules" and 2026-11-01; the matcher refuses a guide
  without one of its five comparison rulings. `[[spellings]]` holds the avoid lists `poe golden`
  checks, the agent's reading of the rulings: the Arabic-script spellings of Outlook, PDF and Word,
  and the digit words 0 to 9, for ticket_number items only. The contractions ruling has no list.
- 2026-11-01: Track D: `terms.toml` lists English, Ole5, Outlook, PDF and Word. An item holds a term
  when the term is a whole word, case-sensitive, in its text or a variant's reference. Ole5 is the
  agent's addition, for the owner to keep or drop with Q4.
- 2026-11-01: Track D: the split algorithm, with integer arithmetic. Each (language, kind) stratum
  holds out floor(30% of its items); the items left over to reach round(30% of the set) go to the
  strata with the largest remainders, ties broken by the salted hash of the stratum's name; inside a
  stratum, items are taken in order of sha256(salt + ID). The salt is committed in `split.json`;
  `--check` keeps it, and `--salt` with `--check` is refused.
- 2026-11-01: Track D: `frozen.json` holds each accepted variant's expected answers, not normalized:
  its reference, then its item's alternatives. Each item there carries its split, kind, language,
  want and terms, and a `left_out` list gives each unchecked variant with its reason. A normalizer
  change therefore never changes the frozen file, and confirming a variant shows as a diff.
- 2026-11-01: Track D: the manifests. `manifests/talkover.json` has root `talkover` and no consent.
  Each recording session gets `manifests/<root>-<session>.json` (root `owner` by default), with that
  session's consent. A new recording's hash and length come from its sidecar, and its sample rate
  from `audio.SAMPLE_RATE`. `poe golden` refuses a new recording whose manifest holds no consent,
  and any manifest file named by no segment or by two.
- 2026-11-01: Track D: the talk-over import hashes each segment, and reads its length and rate, with
  `audio.read_wav` as it writes the manifest, since a manifest needs each file's hash; `golden
  --audio` repeats the check. Both take the reader as an argument, so tests pass a fake and never
  read audio.
- 2026-11-01: Track D: the checks `poe golden` runs, besides the acceptance criteria:
  - a scripted reference equals its item's text, or its script line's for a new recording;
  - an empty reference is exactly one with no speech, and an item of language `none` is exactly one
    whose references are empty;
  - a listening sound is in the script's list;
  - the terms are in `terms.toml` and in the text;
  - `split.json` names exactly the items, and `strata.toml`'s three tables equal the counts.

  With `--audio`, a length may differ from the manifest's by up to 1e-4 s, and a path that resolves
  outside its root's folder, through a link or a junction, is refused before it is read.
- 2026-11-01: Track D: how the no-item-in-source test reads the source. It searches Python string
  constants, docstrings and f-string parts included, and the whole text of text files; comments are
  not searched. Both sides are folded with the test's own copy of the guide's letter folding
  (TD-017), Arabic-Indic and Persian digits are read, and case and punctuation are ignored. An
  underscore stays part of a word, so `stop_word` or `k05_stop` never holds `stop`. It searches the
  script's lines as well as the items' references. The no-audio test finds a file by its extension
  or by its first 12 bytes.
- 2026-11-01: Track D: `load_matcher` keeps Block 0's signature and adds a keyword-only `normalize`,
  for tests; by default it uses the library's normalizers. `golden.validate` takes the spelling
  check and the audio reader as arguments, and `main` passes the library's `spelling_issues` and
  `audio.read_wav`, so the tests ran on the track's branch with Block 0's fakes.
- 2026-11-01: Track F: latency is taken over answered requests only (`outcome` `ok`), because a
  refused or timed-out request's time measures the refusal or the timeout, not an answer. Requests,
  retries (attempt above 1) and billed seconds count every request, so the spend adds up. The
  agent's choice.
- 2026-11-01: Track F: a reference counts as empty when it holds no word after
  `normalize_digits(normalize_arabic(...))`, the normalization the scorers use, so WER and CER never
  receive a reference that Track A's `wer` would refuse with a ValueError, and such a variant is
  scored for text from silence instead. The agent's choice.
- 2026-11-01: Track F: WER and CER are taken against each variant's reference only, never its
  alternatives, as the registration's pooled rates say; only the verdict uses the alternatives. The
  agent's reading.
- 2026-11-01: Track F: a run's unjudged variants (a run that sent only the windows) and its
  infrastructure failures are left out of every rate, but their requests and billed seconds still
  count. A failed variant's windows are also left out of the window measures. The agent's choice.
- 2026-11-01: Track F: in `WindowMetrics`, `one_word_clips` and `holds_word` are counted from each
  `Window`'s `holds_word`, which Track E's `windows.py` sets only for a one-word reference, so the
  counts match Track E's measures; `reference_words` comes from the normalized reference. The
  agent's choice.
- 2026-11-01: Track F: the scorecard breaks its numbers down only by the four strata the track
  names: language, device, kind and split. Tags such as duck, pause and over-assistant are not
  broken down: a dev scorecard keeps each variant's tags, and a held-out breakdown by a tag that
  only three segments carry would read close to item by item. The agent's choice; a tag breakdown
  may be added later.
- 2026-11-01: Track F: how `write_scorecard` writes, the agent's choices:
  - it checks the run and every result again through JSON before scoring, because pydantic does not
    re-check nested model instances;
  - it refuses results of another split and a variant scored twice;
  - it creates `out` if needed and replaces an earlier `scorecard.json` of the same run atomically
    (written to a partial file, then moved), as `FakeScorecardWriter` does, so a Track E built
    against the fake keeps working.
- 2026-11-01: Track F: the scorers and the normalizer are passed in as `scorers=` and `normalize=`.
  The defaults are the `evals` facade module itself (which mypy accepts as the `Scorers` protocol)
  and `normalize_digits(normalize_arabic(text))`; tests pass `FakeScorers`. `compare.main` takes
  `sign_test=`, defaulting to `evals.sign_test`. These extra keyword arguments still fit the
  `ScorecardWriter` protocol. The agent's choice.
- 2026-11-01: Track F: what `eval-compare` refuses and shows, the agent's choices:
  - A is the baseline and B the candidate: fixed means wrong in A and right in B;
  - it refuses runs whose splits differ, as well as commits and data digests: a run covers one
    split, and two splits share no variant;
  - settings may differ, since the registered baseline compares two models at one commit; every
    setting that differs is named in the report;
  - commits are compared as the strings recorded, with no matching of prefixes.
- 2026-11-01: Track F: `eval-compare` leaves a variant out of both runs, and lists it by ID with the
  reason, when either run had an infrastructure failure on it ("a provider failure" or "stuck past
  its time limit", in A or in B), when it was not judged, or when it appears in one run only. The
  agent's choice.
- 2026-11-01: Track F: the stratum guard's readings are "better in B beyond the noise", "worse in B
  beyond the noise", "within the noise" and "too small to guard"; "too small to guard" is tested
  with the sign test itself rather than a fixed 6. The smallest detectable change is printed in
  every dev comparison, worded as applying when A and B ran the same code. The agent's choices.
- 2026-11-01: Track F: `--focus FILE` takes one item ID per line; blank lines and `#` comments are
  skipped. An ID found in neither run is refused, and `--focus` is refused for held-out runs, which
  are compared by aggregates only. The agent's choice: evaluation.md names the flag but not its
  form.
- 2026-11-01: Track F: the commands write their report to standard output and refusals to standard
  error, as `<command>: <message> [<code>]` with exit status 1. ARCH-PRINT covers only the library,
  and a report is the command's output, not a log event; it holds identifiers and numbers only. The
  app's two errors are `AppError` subclasses: `EvalDataError` (`eval_data_invalid`) and
  `ComparisonError` (`comparison_refused`); `EvalDataError` names the file and the failing field,
  never a value read from it, `ComparisonError` the commits, data digests or splits that differ,
  as the plan asks, never a transcript (corrected by the review of the merged tracks); they are
  raised outside the handler, so no exception chain holds the refused input. The agent's choice, for
  the harness reviewer, against GP-03's "no print".
- 2026-11-01: Track F: the history file is committed empty, so a mistyped `--history` fails instead
  of rendering a page that says "No runs yet". The agent's choice:
  - reading is strict: UTF-8, LF endings only, every line a valid `HistoryLine`;
  - `append_line` checks the line and the existing file first, and creates the file when it is
    missing (for Track E's copy beside the scorecard).
- 2026-11-01: Track F: `line_of(scorecard, items=)` builds the history line: its time is the run's
  `started_at` (no clock, GP-12), its breakdowns are each stratum's accuracy, and its scorecard is
  `SCORECARD_FILE`. `items` is passed in because a held-out scorecard holds no variant. It is there
  for Track E to use at its merge. The agent's choice.
- 2026-11-01: Track F: the layout of `eval-history.md`, the agent's choice:
  - the spend so far: runs, billed seconds and cost summed over every line, as step 20 needs;
  - one row per run;
  - for each run, tables of its reason, data digest, scorecard, price, settings and accuracy by
    stratum;
  - a run's own text has Markdown's characters (the backslash, the backtick, the asterisk, brackets,
    parentheses, braces, angle brackets, the pipe, the tilde and the ampersand) escaped and its line
    breaks removed, so a note never makes a link, HTML, a placeholder or an extra table cell;
  - the `--history` and `--out` defaults are paths worked out from the module's place in the
    repository.
- 2026-11-01: Track F's request for a change to Block 0, adding `docs/generated/eval-history.md` to
  `harness.toml`'s `[docs] historical`, is not applied at its merge: nothing fails while the history
  is empty, and it changes which docs DOC-REF and DOC-MILESTONE read, a harness rule rather than an
  integration fix. It stays as TD-018's fix, for the review of the merged code or the owner. The
  integrator's choice.
- 2026-11-01: Track E: a run's name is the name of its `--out` folder, checked as a `models.Name`.
  It is the run's `RunInfo.name`, its history line's `run` and its traces' `session.id`, so all
  three come from one place and no `--name` flag is needed. The agent's choice.
- 2026-11-01: Track E: a run is traced only when `--tracing-endpoint` is given. The runner sets
  `tracing.endpoint` from the flag alone, so a `T2V_TRACING__ENDPOINT` in the shell or a `.env`
  never traces a run. A held-out run refuses the flag, and a test checks that a held-out run with
  that variable set opens no span. The agent's choice.
- 2026-11-01: Track E: `--out` is a new folder outside every worktree that may be removed: refused
  inside the run's own worktree, even where git ignores it (its `var/`), and inside another linked
  worktree; inside the main checkout it is accepted only where `git check-ignore` says ignored;
  outside the repository, any new folder. This follows the acceptance criterion's "a new folder
  outside the worktree that git does not track". The agent's choice.
- 2026-11-01: Track E: the tree counts as clean when `git status --porcelain` is empty, so an
  untracked file that is not ignored (a new item not yet committed) is a change, and the run is
  refused. The agent's choice.
- 2026-11-01: Track E: retries. A rate limit pauses the larger of `retry_after_s` and 20 s;
  `timeout`, `connection_lost` and `server_error` pause 3 s; `rejected` is never asked again. Pacing
  is a minimum gap between request starts, stricter than a per-minute window. The agent's choice.
- 2026-11-01: Track E: each request is charged the larger of 10 s and the clip's length before it is
  sent, whatever its outcome, since whether a refused request is billed is UNVERIFIED (TD-021). So
  the cap, the history line's `billed_seconds` and its `cost_usd` are upper bounds. Each `Request`
  records the seconds charged. The history line counts every request of the run, the smoke test's
  and a cut-off variant's included, so step 20's spend from the history covers them. The agent's
  choice.
- 2026-11-01: Track E: the smoke test sends the run's first variant (dev), or for a held-out run the
  first dev variant, as a whole clip with no windows. It is answered again in the run, as the
  registration's estimate counts smoke requests apart. It passes when every request ended `ok` on
  its first attempt and the answer is no failure. If it fails, the run writes a scorecard of no
  result (complete false) and, having spent, a history line. The agent's choice.
- 2026-11-01: Track E: `--smoke-only` takes `--split dev` and no `--windows-ms`. Its scorecard holds
  the smoke variant's result, and a run that spends appends its history line, as step 21 says. The
  agent's choice.
- 2026-11-01: Track E: Ctrl+C ends a run incomplete (exit 1). A dev run keeps `results.jsonl` and
  writes a scorecard of the results so far, complete false. A held-out run writes a scorecard of no
  result, complete false, and still appends its history line (0 variants, no accuracy) so its spend
  is counted: "keeps nothing" is read as no result kept, and evaluation.md's "Every attempt is
  recorded" still holds. The agent's choice.
- 2026-11-01: Track E: `--cap-usd` is checked before each request. A run that reaches it ends
  between requests, incomplete, and the variant in progress is dropped unanswered, its sent requests
  still counted. The agent's choice.
- 2026-11-01: Track E: the per-variant wall-clock limit lives in the `groq` answerer, which keeps
  the variant's request log. A stuck variant's answer lists its requests, the one in flight as
  `stuck`. A stuck or provider-failed variant is an infrastructure failure of a run that still
  completes. The agent's choice.
- 2026-11-01: Track E: `--windows-ms` sends only the windows, of the split's talk-over items (the
  registration's "each registered talk-over clip"), so Q15's answer of dev only or all 124 needs no
  other flag. Its results are unjudged (`judged` false). `--questions` narrows a dev run further.
  The agent's choice.
- 2026-11-01: Track E: a window's measures are taken against the variant's reference (the
  registration says "the reference"), normalized with `normalize_digits(normalize_arabic(text))`.
  Leading words are the words both texts begin with, in order. `holds_word` is set only for a
  one-word reference: true when the matcher judges any run of the window's words to be it, so the
  spelling guide's rulings and a word split in two count. The agent's choice.
- 2026-11-01: Track E: the verdict is `Matcher.is_right(answer text, [variant.reference,
  *item.alternatives])`. The agent's choice.
- 2026-11-01: Track E: `--questions` is refused with `--split held-out`, since a held-out run covers
  its whole split. Its lines are `item/variant`; blank lines are skipped, and an entry the split
  does not hold is refused, the refusal giving a count. The agent's choice.
- 2026-11-01: Track E: the data digest is the SHA-256 of canonical JSON over the run's (item without
  its variants, variant) pairs, the committed split file and the SHA-256 of `spelling.toml`. The
  model and settings are left out, so R1 and R2 at one commit share a digest, and a screen or
  windows run gets its own. The agent's choice.
- 2026-11-01: Track E: a run records (`RunInfo.settings` and the history line) every library setting
  by dotted name except `var_dir`, a local path that changes no result (shown by `--show-settings`).
  `groq.api_key` and `groq.api_key_file` are recorded as set or not set, and `tracing.redact` as a
  count of patterns. The run's flags are recorded as `run.language_hint`, `run.max_rpm`,
  `run.max_attempts`, `run.variant_timeout_s`, `run.cap_usd`, `run.windows_ms` and `run.smoke_only`.
  Audio root folders are shown but not recorded. The agent's choice.
- 2026-11-01: Track E: `--language-hint` takes `label` (the default: `en` for English, `ar`
  otherwise, as arm A1) or `auto` (no language sent, for Q14's arm if the owner adds it). The
  agent's choice.
- 2026-11-01: Track E: `--price-per-hour` and `--cap-usd` are required with `--answerer groq`, so a
  forgotten price is never a cost of 0 and no run that spends is uncapped; for `reference` they
  default to 0 and none. The agent's choice.
- 2026-11-01: Track E: every refusal names counts and audio roots, never a variant ID, in every run,
  so a held-out run's refusal reveals nothing of its items; `poe golden --audio`, which the FIX line
  names, lists the files. The agent's choice.
- 2026-11-01: Track E: `poe eval` exits 0 when complete, 1 when incomplete (a failed smoke test, the
  cap, an interrupt), and 2 when refused before anything is sent (argparse's usage errors also exit
  2). The agent's choice.
- 2026-11-01: Track E: `make_answerer(name, settings)` keeps Block 0's signature and adds
  keyword-only options (`stt`, `policy`, `budget`, `measure`, `reuse`, `tracing`, `run_name`,
  `clock`, `sleep`). It returns a `RunAnswerer`, an `Answerer` that also says whether it spends,
  whether it reads audio, and how it closes. The `groq` answerer's default adapter is the one
  `stt.provider` names (GP-22). The agent's choice.
- 2026-11-01: Track E: `run.py` calls Track F's `write_scorecard` with an empty sequence of results
  when the smoke test fails or a held-out run does not finish, which Track F's writer accepts
  (checked at the merge, the progress log). The agent's choice.
- 2026-11-01: Track G: the recorder's token is the first part of every path
  (`http://127.0.0.1:<port>/<token>/...`), not a query string or a cookie, so every relative address
  on the page (its script, the audio worklet, each fetch, each audio file) carries it with no script
  code, and no other site can hold it, since the cookies of 127.0.0.1 are shared across ports.
  `Referrer-Policy: no-referrer` keeps it out of any Referer. The agent's choice.
- 2026-11-01: Track G: `Host` must be one header exactly `127.0.0.1:<port>`. A POST must carry one
  `Origin` exactly `http://127.0.0.1:<port>` (a POST with none is refused too) and the type
  `application/json`, which a form from another page cannot send without a preflight the server
  never answers. A POST's body is read before any refusal, so a refused POST leaves no unread bytes
  on the connection, except one refused for its length (411, 413). The agent's choices.
- 2026-11-01: Track G: every answer sends `Content-Security-Policy: default-src 'none'; script-src
  'self'; style-src 'unsafe-inline'; media-src 'self' blob:; connect-src 'self'; img-src data:;
  base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, plus `Cross-Origin-Resource-Policy:
  same-origin` (no other page can even embed its audio), `Cache-Control: no-store` and
  `X-Content-Type-Options: nosniff`; inline styles are allowed for the page's one style block. What
  `http.server` refuses itself (an unknown method, a bad request line) gets only its status's
  phrase, never the request's text. No line is logged per request, since the path holds the token.
  The agent's choices.
- 2026-11-01: Track G: the address with the token is logged once, through the library's `get_logger`
  (GP-03: no `print`), as the `recorder_ready` line on the owner's terminal. That one line is the
  plan's "prints in the address", and the token is in no other line. The agent's reading.
- 2026-11-01: Track G: `RecorderServer` turns off `allow_reuse_address`, since on Windows
  SO_REUSEADDR would let another socket bind the same port. `--port` defaults to 0, a free port, so
  Chrome asks for the microphone again in each new run. The agent's choices.
- 2026-11-01: Track G: the allow-list's files are looked up by ID only: a reply by its ID in
  `replies.json`, a take by its ID among the sidecars below `--out`, a variant's segment by the
  variant's ID and the segment's index. A file is sent only when (1) resolving its path, links and
  junctions included, gives the path itself, (2) its bytes start as RIFF/WAVE, and (3) they match
  the SHA-256 its sidecar or manifest records (replies have no recorded hash, so they get the
  RIFF/WAVE check only), so even a hard link to a `.env` is never sent. A reply's `file` must be a
  plain `.wav` name beside `replies.json`. The agent's choices, from the decision log's recorder
  entry.
- 2026-11-01: Track G: the server names each take `<line>-<session>-<n>`, with n the first number
  that names no take, no WAV and no sidecar yet; a request never names a file. A session's folder
  below `--out` that is a link is neither read nor written. An `--out` inside this repository but
  outside its git-ignored `var/` is refused at start, so no take can land where git would track it.
  The agent's choices.
- 2026-11-01: Track G: a review pass is one run of `poe record`, numbered one past the highest pass
  found below `--out`. A take or a variant has at most one review a pass, since its file's name
  `<take>.review-<pass>.json` holds the pass and is never replaced. An entry is due when it has no
  review in this pass and its latest review, if any, is `typed`, so a text typed in pass n comes
  back, as its reference, in pass n+1 or later, for a separate listen (Q9). The items' own
  `confirmations` are not read for the queue: the review files below `--out` decide it. The agent's
  choices.
- 2026-11-01: Track G: a golden-set variant's review is written at `<out>/<the variant's
  session>/<variant>.review-<pass>.json`; for the talk-over variants, that is a folder with no
  `session.json`. Track D's `import_recordings` reads these reviews, and skips a folder that holds
  only reviews (Track D's entry above), so its refusal of a session without one does not apply. The
  agent's choice.
- 2026-11-01: Track G: a variant enters the review mode only when every segment's root is among the
  `--audio` roots given, and each (root, path) is named by a manifest with the same SHA-256;
  otherwise it is left out and logged as `recorder_left_out`, as is a take whose line left the
  script. A take of the recorder's own comes before a variant of the same ID. An `--audio` root that
  no manifest names is refused at start. The items come from `items.load_items` (Track D); the tests
  inject `FakeGoldenSet.load_items`. The agent's choices.
- 2026-11-01: Track G: a kept take of a several-clause line must carry at least one true turn end,
  and every turn end must lie within the take (`TurnEnds`: distinct, in order); a discarded take
  needs none. The agent's choices.
- 2026-11-01: Track G: the track's settings are recorded as the browser reports them, and a take is
  not refused when the browser reports echo cancellation, noise suppression or gain control off: the
  page warns, and the sidecar says so. The agent's choice, since some headsets may report one off
  and refusing would block a sitting for a reason the owner cannot change (the owner's question in
  the progress log).
- 2026-11-01: Track G: without both `--session` and `--device`, the page only reviews, and the
  consent and take POSTs are refused (409). A session's `session.json` fixes its device: a later run
  of that session with another `--device` is refused at start. The consent's `on` is the local date,
  and every `recorded_at` and review `at` is local time with its offset. The agent's choices.
- 2026-11-01: Track G: `recorder.js` is both the page's script and its audio worklet; in the
  worklet's scope it only registers the processor that passes each block of samples to the page, so
  `script-src 'self'` covers the worklet with no `blob:`. The page refuses to record when the
  browser will not run an `AudioContext` at 16 kHz. MediaStreamTrack's method that ends a track is
  named after a one-word talk-over reference, so the page looks it up by its parts, and no page text
  holds the word. Text from the script, the replies and the files is set as text, never as HTML. The
  agent's choices.
- 2026-11-01: Track H: each code sample on the guide's `evaluation.md` is preceded by a Markdown
  link to its source file, and names the test or constant it comes from, so DOC-LINK fails when a
  source file is moved or renamed, and a later sample check can find each block's source. Blocks are
  copied word for word, with only their indentation removed. No import line is copied: the tests
  import from the library's layers, while an app imports only from the facades (ARCH-PUBLIC), so the
  page names the facade in prose instead. The agent's choice.
- 2026-11-01: Track H: the guide's samples come only from Block 0's tests (`test_models.py`,
  `test_rulings.py`), since on the track's branch the evaluation helpers were Track A's stubs and no
  tested file called them. The page therefore gives each helper's contract as a table taken from
  Block 0's docstrings, which Track A keeps, rather than as a code sample; a sample that calls the
  helpers can be copied from Track A's tests later. The agent's choice.
- 2026-11-01: Track H did not read `refs.json`, which is not on its May read, so the guide's text
  could not be checked against every talk-over reference. To stay clear of them, the page avoids the
  four one-word English references (okay, stop, wait, yeah) as whole words, and quotes no utterance
  except the product-term ruling of `test_rulings.py` (اوتلوك, Outlook), no listening sound, and
  none of the references the plan quotes. Track D's test does not read `docs/`; a reviewer with
  `refs.json` can run the matcher's normalization over `docs/guide/evaluation.md` to confirm. The
  agent's choice.
- 2026-11-01: Track H: the method doc keeps its paths `evals/golden/`, `evals/screens/<name>.txt`
  and `evals/history.jsonl` as written; its opening paragraph now says that `evals/` there is the
  app's data folder, `apps/ole5-voice-agent/evals/`, where this plan puts them. Only `scripts/eval/`
  and `tests/evals/` changed. The paragraph says "plan 002 builds", in the present tense, so it
  holds both during the plan and after it; step 28 may put it in the past tense at the close. The
  agent's choice.
- 2026-11-01: Track H: the guide index's status line said the public API was "designed but not
  built"; it now says M1 builds its first public modules (`ports`, `groq`, `languages`, `evals`,
  `tracing`), since Track H owns that file and the old line would be false after M1's merge. The
  rest of the paragraph is only rewrapped to 100 columns, and text outside Track H's parts is left
  as it was (the index's `browser-client.md` row and the method doc's "stop word" and "waits"). The
  agent's choice.
- 2026-11-01: The review of the merged tracks: a run scores only the variants the owner has
  checked, by the rule `poe golden` accepts a variant by (`items.unchecked` is None: a confirmation,
  and for a typed reference one in a later pass), as the registration's independent check says.
  `load_plan` keeps the split check on the whole set, applies `--questions` to the split's variants,
  then drops the unchecked ones from the run's variants and from the dev variants the smoke test is
  taken from, so the digest covers only what is scored. It logs `unchecked_left_out` as two counts,
  never an ID, so a held-out run names nothing; a run left with no checked variant is refused,
  naming the review and `poe golden`. No field is added to `RunInfo` or `Scorecard` (Block 0's
  models): `frozen.json`'s `left_out` lists the variants, and `eval-compare`'s digest check already
  keeps two compared runs on one checked set. Step 15's test gives each committed variant a made-up
  confirmation, since none is confirmed before step 18. Alternative: a `--unchecked` flag for the
  reference answerer, set aside as a second way to score a set nobody checked. The agent's choice.
- 2026-11-01: The review of the merged tracks: the runner's clock is `time.perf_counter` (in
  `Parts` and `make_answerer`), monotonic and finer than a microsecond here, since `time.monotonic`
  is `GetTickCount64` on Windows, 15.6 ms steps, coarser than the 292 against 295 ms medians the
  registration cites; the pacer and the progress lines share it. No doc fixed `time.monotonic`. The
  agent's choice, registered as an amendment before R1.
- 2026-11-01: The review of the merged tracks: a `groq` run needs `--model` and `--timeout-s` (a
  finite number of seconds above 0) on its command line, and its `groq.base_url` is `--base-url` or
  the SDK's own `https://api.groq.com`, whatever the environment holds, as `--tracing-endpoint`
  already is for tracing, so no `T2V_` variable in the shell or `.env` changes a registered arm
  (evaluation.md, "Running"). A bad `--base-url` is refused naming the flag, never its value. A
  reference run keeps the loaded settings, which change nothing it measures. Alternative: refusing a
  run whose resolved base URL is not the default unless a flag names it, set aside as one more
  refusal for the same guarantee. The agent's choice; the registration's arms gain both flags as an
  amendment, with their values unchanged.
- 2026-11-01: The review of the merged tracks: the matcher also counts a variant right when the
  output and a reference are equal in their joined form, `normalize_arabic` with every space
  removed and only then `normalize_digits`: the prototype's `norm`, but for a whole text that is
  one digit's name. Reading a lone digit name as its digit (Track A's decision) made a word written
  in two another text ("some one" against "someone", "five 7" against "five7", or a zero-width
  character inside a word), against Q8's "spaces ignored in the verdict"; the second form keeps
  every verdict that was right ("one" against "1") and adds only the cases Q8 counts. A matcher
  built with a test's normalizer compares by `key` alone. Alternative: reading digit names only in
  runs of two or more, set aside since a provider's lone "one" against a reference's "1" would then
  be wrong. The agent's choice, registered as an amendment before R1.
- 2026-11-01: The review of the merged tracks: text from silence counts the characters of the
  output after `normalize_arabic` alone, spaces removed, not its scored form, so a digit's name
  ("one", «واحد») counts its letters as produced rather than one digit; an output is empty in one
  form exactly when it is in the other, so the share and the empty-reference test of Track A's
  `wer` entry are unchanged. It replaces the last sentence of Track A's `term_recall` entry above.
  The agent's choice, registered as an amendment before R1.
- 2026-11-01: The review of the merged tracks: `normalize_digits` reads a word with the marks
  `normalize_arabic` removes inside it (its word pattern takes the marks class of
  `domain/text/arabic.py`), so a vowelled digit name is read whole, as its docstring and the guide
  say; the scorers call `normalize_arabic` first, so no score changes. The agent's choice.
- 2026-11-01: The review of the merged tracks: each `GroqSTT` draws its own multipart boundary
  (`secrets.token_hex(16)`) and passes it in every request's `Content-Type` through `extra_headers`;
  the request hook refuses a body that does not open with it, which a `GROQ_CUSTOM_HEADERS`
  content-type line in another case than the SDK's makes httpx cut, so such a line can only fail a
  request, as a `rejected`, non-retryable `ProviderError` with the detail `foreign_boundary`, never
  shape it, and audio holding a known boundary adds no form field. The hook's exception holds no
  value, since the SDK logs it at DEBUG with its traceback. A `Content-Type` line in the SDK's own
  case is replaced by the adapter's. Pays the `GROQ_CUSTOM_HEADERS` row as it proposed. The agent's
  choice.
- 2026-11-01: The review of the merged tracks: `GroqSTT`'s constructor validates its values
  through core's own `GroqSettings` and `SttSettings` (plain models, which read no environment)
  and takes the key as `resolved_api_key` gives it, the space around it removed (GP-20): it refuses
  what the settings refuse (port 0, a space or a tab in the URL, which the copied rules missed), by
  the same messages, the bad key's FIX line included, each naming the `T2V_` setting and never the
  value, before any client is built. The copied `_KEY` and `_https` are gone. The agent's choice.
- 2026-11-01: The review of the merged tracks: the private provider (`SpanQueue`,
  `private_provider`, `ExportSession`, `otlp_exporter` and their constants) moves to
  `core/tracing_export.py`, its tests to `tests/t2_agentic_voice/core/test_tracing_export.py`, and
  what both test files share to `tracing_support.py`, as the size-cap row proposed (paid). The names
  are public within `core`, which no facade re-exports. `ExportSession` also overrides `request`,
  which the exporter's transport calls with its headers as a keyword, and replaces them with its own
  before requests checks them: a `%0A` in `OTEL_EXPORTER_OTLP_HEADERS` decodes to a line break that
  requests refused, quoting the header (a token) in an error the exporter logged at ERROR, every
  batch lost. `prepare_request` still clears the `.netrc` login. The agent's choice.
- 2026-11-01: The review of the merged tracks: the redaction hook runs on each attribute's key as
  well as its value, on a span, an event and a link, since a team may name a key after what was
  said. A redacted key is kept as redacted, not dropped. The agent's choice.
- 2026-11-01: The review of the merged tracks: the re-checks of a run, a result and a history line
  (`write_scorecard`, `append_line`) serialize with pydantic's warnings off, whose
  `PydanticSerializationUnexpectedValue` text quotes a wrongly typed value (a bytes key put in by
  `model_copy`) and is printed to stderr before the check refuses it. The agent's choice.
- 2026-11-01: The review of the merged tracks: a run's note holding an install placeholder is
  refused: `poe eval --note` by the parser, before anything is sent, and `RunInfo.note` and
  `HistoryLine.note` (a `Note` type in `runs.py`) as the backstop, since the docs check reads the
  committed `history.jsonl`, which is never edited, and would fail the gate for good. The pattern is
  DOC-PLACEHOLDER's, written again in `runs.py` (an app does not import `scripts/`). Alternative:
  `history.jsonl` in `[docs] placeholders_allowed_in`, set aside as an exemption where a refusal
  costs nothing. TD-018 is left as it is. The agent's choice.
- 2026-11-01: The review of the merged tracks: the `Scorecard` model refuses a variant listed
  twice, as `write_scorecard` already did, so `eval-compare` never pairs a hand-edited file whose
  later copy would silently replace the earlier. The agent's choice.
- 2026-11-01: The review of the merged tracks: `history.line_of` is the one definition of a run's
  history line, and the runner calls it with the run's spend from its budget (every request sent,
  the smoke test's and a capped variant's included), as Track E's merge chose; a scorecard's billed
  seconds and cost cover the requests of the variants it scores, and its docstring says so. The
  agent's choice.
- 2026-11-01: The review of the merged tracks: a docs rule, DOC-CONTROL, refuses a control
  character other than a tab and the line ends in a doc, since the owner's recording commands
  (steps 4 and 5 below) reached the plan with their backslashes read as escapes and `poe docs`
  passed; the commands are written with forward slashes, as `.claude/launch.json` writes them. The
  agent's choice.
- 2026-11-01: The review of the merged tracks: the suite drops `REQUESTS_CA_BUNDLE` and
  `CURL_CA_BUNDLE` from the shell and points `NETRC` at an empty file of its own
  (`tests/conftest.py`, checked by `tests/harness/test_isolation.py`), so the OTLP tests pass on a
  machine behind a TLS-inspecting proxy and requests never opens the developer's `~/.netrc`. The
  agent's choice.
- 2026-11-01: The review of the merged tracks: the finding that ID recall counts a ticket number
  written in pairs ("48 21") or with a thousands separator ("4,821", «٤٬٨٢١») as missed goes to the
  owner (its checker marked it for the owner): the pairs case is Track A's recorded decision ("45
  21" stays two numbers). The checker's proposal for the separator case, a `,` or U+066C between
  digits and followed by exactly three digits removed in `id_recall` alone, is put to the owner with
  it rather than applied. The agent's choice.
- 2026-11-01: The integrator's check: nothing a run writes into the committed history may hold an
  install placeholder (the note, each setting's name and value, the model), refused by the models
  and, before anything is sent, by `poe eval`, rather than listing `history.jsonl` among the files
  where the docs check allows one: the history then stays checked like any other file. The agent's
  choice.
- 2026-11-01: `OTEL_SDK_DISABLED` still turns the library's private tracing off (TD-005); the
  library does not override it through the SDK's private `_disabled` flag, which could break
  silently on an SDK upgrade, and the guide tells a teammate to leave it unset, with
  `OTEL_PYTHON_CONTEXT` and `GROQ_LOG` (TD-003). The owner's answer ("The owner's decisions").
- 2026-11-01: The recorder saves a take whose browser reports echo cancellation, noise
  suppression or gain control off, with a warning on the page and the settings in its sidecar,
  rather than refusing it, which would block a sitting on a device whose browser reports one
  off. The owner's answer.
- 2026-11-01: Q15 with `--clips-from`: a held-out window at least as long as its clip cannot
  reuse the clip's answer, so the runner sends the whole clip as that window, marked not reused
  (at most a few requests, within the estimate). The owner's answer.
- 2026-11-01: "Ole5" stays a product term in `terms.toml`, beside Outlook, PDF, Word and English.
  The owner's answer, with the script's approval (Q4).
- 2026-11-01: No `--unchecked` flag for the reference answerer: a run scores the checked
  variants only, and step 15's command-line runs are made at step 19 on the confirmed set, with
  `test_reference_answerer.py` covering the check until then. The owner's answer.

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

On 2026-11-01, after the merged tracks were reviewed, the owner's answers to the eight questions
they raised, each put with the agent's recommendation: "Go with the recommended with all of
them". So, in the agent's words of each recommendation:

1. ID recall counts a ticket number the speech-to-text writes in groups ("48 21" or "48-21" for
   4821) as heard, and the thousands-separator case ("4,821", «٤٬٨٢١») is fixed too.
2. In a held-out run's results, a group covering fewer than 3 items is merged into one group
   named "other" (left out when "other" still covers fewer than 3), registered before H1.
3. `OTEL_SDK_DISABLED` stays debt (TD-005), with the guide saying to leave it unset; the SDK's
   private `_disabled` flag is not overridden.
4. The recorder keeps saving a take whose browser reports echo cancellation, noise suppression or
   gain control off, with a warning on the page and in the take's sidecar; it does not refuse it.
5. Q15 with `--clips-from`: a held-out window at least as long as its clip sends the whole clip,
   marked not reused. Accepted.
6. The owner's consent for the talk-over set is recorded in words and dated; the owner's own
   sentence is asked for, and written here when given.
7. "Ole5" stays a product term in `terms.toml`.
8. No `--unchecked` flag for the reference answerer: step 15's command-line runs are made at
   step 19, on the confirmed set.

The same day, the owner's answers to the calls before recording:

- Q4, the script: "I Approve the recording script, I haven't rally tried it but if you see it
  good then it is fine". The agent reviewed it before marking it approved (the progress log).
- Q5, the ticket number's shape: the owner gave three examples of Ole5 ticket numbers (not
  copied here, since they may be real tickets). Their shape: 16 digits, the date as YYYYMMDD,
  then 82, then a 6-digit counter. The script's full numbers are made up in that shape.
- Q7, the talk-over items' dialect: "I am not sure I understand the question correctly". The
  agent put it again, as a list of the phrases with the label proposed for each; still open.
- Q9, the independent check: "I can listen and judge, just give the samples and I can do that",
  so (a): the owner listens to every variant and confirms it, in the recorder's review mode.

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
  one (the decision log's groq list). Every exception the SDK raises, not only its
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
  `test_no_audio.py`, and `test_import_recordings.py`, added at the merge).
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
  `windows.py`, `worktree.py` (the linked-worktree and clean-tree checks, through `git`), and
  `run_parts.py`, added at the merge; tests `tests/ole5_voice/evals/` (`test_run.py`,
  `test_answerers.py`, `test_windows.py`, `test_worktree.py`, and `test_run_parts.py`, added at
  the merge).
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
  in `docs/generated/README.md`; `apps/ole5-voice-agent/evals/history.jsonl` (added at the
  merge); tests `test_scorecard.py`, `test_compare.py`, `test_history.py` (the freshness test).
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
- Owns: `recorder.py`, `recorder_page/index.html`, `recorder_page/recorder.js`, and
  `recorder_load.py` and `recorder_state.py`, added at the merge; tests `test_recorder.py`, and
  `test_recorder_security.py` and `recorder_support.py`, added at the merge.
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

The owner's call before recording (Q4, Q5 and Q9 settled on 2026-11-01: "The owner's
decisions"; Q7 still open):
- **Q4.** *Settled: the script is approved, as proposed.* The script: the counts above; ticket-number and echo-only items; whether to add
  over-the-agent items on the two headsets (a reply plays while the owner speaks), which would
  give M3 overlap clips on every device.
- **Q5.** *Settled: 16 digits, the date as YYYYMMDD, then 82, then a 6-digit counter.* The
  shape of a ticket number a customer reads out, for the script's ticket items. No
  source gives Ole5's real format: the prototype's tickets were mocks, `T-MOCK-` with a time and
  a counter (`Ole5-chatbot/src/ole5_chat/tickets/mock.py`, line 20), and its log says "the real
  OTRS format is unknown" (`Ole5-chatbot/VOICE_LOG.md`, line 21, D12). The prototype's agent
  says only a number's last four digits aloud (D12), so a customer may repeat those, or read the
  full number from the screen or an email. The agent proposes both: two items of four digits,
  and two of a full number in the shape the owner gives (the website team may know it).
- **Q7.** The dialect of the talk-over Arabic items: the agent proposes Saudi, MSA or mixed for
  each phrase from its text; the owner confirms or changes each.
- **Q9.** *Settled: (a).* The independent check: (a) the owner listens to every variant and confirms it (the
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

**Amendments** (each dated, and made before any run):

- 2026-11-01, from the review of the merged tracks, before any result: every `groq` run names its
  arm's model and timeout on its command line, `--model whisper-large-v3` (A1) or
  `--model whisper-large-v3-turbo` (A2), and `--timeout-s 6`, and sends to `--base-url` or the
  SDK's own `https://api.groq.com`, whatever the environment or the env file holds; the values
  are those registered above, so no measurement changes.
- 2026-11-01, the same review, "The metrics": the verdict is also right when the output equals
  the reference (or an accepted alternative) with every space removed before the digits are read
  (`normalize_arabic`, spaces removed, then `normalize_digits`), so that a digit's name inside a
  word written in two ("some one") never makes it another text, as Q8's spaces ruling and the
  prototype's `norm` have it. Text from silence counts the characters of the output after
  `normalize_arabic` alone, spaces removed, so a digit's name counts its letters, as produced.
  Latency per request is taken over the answered requests (outcome `ok`) only, its median and
  90th percentile interpolated linearly between ranks (Hyndman and Fan's type 7), timed with a
  monotonic clock finer than a millisecond (`time.perf_counter`); requests, attempts, billed
  seconds and cost still count every request.
- 2026-11-01, the same review, "The independent check of each reference": a run scores only the
  variants `poe golden` accepts (confirmed by the owner's listen, a typed one in a later pass),
  and logs how many it left out as a count; `frozen.json`'s `left_out` lists them.

## What the owner does

1. **Before Block 0:** answer Q1 to Q3 and Q8 (done on 2026-11-01).
2. **The Groq key, any time before the runs.** Put it in `.env` in the main checkout
   (`t2-agentic-voice\.env`) as `T2V_GROQ__API_KEY=<the key>`, or put the key alone in a file
   outside the repository and set `T2V_GROQ__API_KEY_FILE=<its full path>` there. The library
   reads only these names, never `GROQ_API_KEY` (the design's 7.3). The agent never opens `.env`:
   a run reads it through `Settings` when given `--env-file`, and `poe eval --show-settings` says
   only whether the key is set.
3. **Before recording:** answer Q4, Q5, Q7 and Q9 and approve the script (all but Q7 done on
   2026-11-01). The check of step 5 can start now on the 120 talk-over variants, before any new
   recording: run step 5's command with `--out var/golden-audio`, the folder step 4 then uses.
4. **Recording**, one sitting per device, in a quiet room except for the noise items:
   - From the main checkout, `uv run poe record --out <a folder under var/, such as
     var/golden-audio> --session <a name> --device <laptop, wired or bluetooth> --replies
     ../voice-lab/assets/talkover` (the lab's six agent replies, read only: the script's
     echo-only lines play two of them, and the recorder does not start without them); open the
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
5. **The check (Q9):** in the recorder's review mode (`uv run poe record --out <the same
   folder> --replies ../voice-lab/assets/talkover --audio
   talkover=../voice-lab/recordings/talkover`, with no `--session`, reviews the new takes and
   the talk-over variants), listen to each variant beside its reference and confirm it, or type
   what was said; a variant you typed comes back in a later review pass (a later run of the same
   command), to be confirmed against your text.
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
