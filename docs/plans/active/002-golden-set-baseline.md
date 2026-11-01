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
  repr, error or log line, and that `GROQ_API_KEY` and `GROQ_BASE_URL` in the environment change
  nothing (the design's 7.3: "Other names are never read"). No public signature names a `groq`
  type (the design's 5.3).
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
      a variant's result, a scorecard, a history line, and the answerer protocol;
    - `ole5_voice/evals/audio.py`, written in full here because Tracks D, E and G all need it:
      reading a WAV with `wave`, checking 16 kHz mono 16-bit, its SHA-256 and length, and cutting
      a leading window, with its tests in `tests/ole5_voice/evals/test_audio.py`;
    - the fakes tests build against, in `tests/ole5_voice/evals/fakes.py`: a fake
      `SpeechToText`, a fake normalizer, and a fake, or a callable passed in, for each piece one
      track calls in another: the matcher (D), the scorecard writer (F), `sign_test` and the
      spelling check (A), and the tracing span helpers (C);
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
    reference` over the whole committed set scores 100%. The agent writes
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
  it also reads `GROQ_CUSTOM_HEADERS` whatever is passed and adds its headers under the ones
  given (lines 93-100 and 306-313), and `GROQ_LOG` when `groq` is imported
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
  with the gaps the spelling guide rules on (ٱ, ی, ک, a lone ء, number words); camel-tools'
  normalizers are not vendored in M1 (the design's 13 allows it), since the port covers what the
  golden set needs and adds no notice file.
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

  Track C keeps out each one of the second group it can, and reports the rest as debt rows; the
  agent proposes those rows in Block 0's report, for the integrator to number.
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
| `googleapis-common-protos`, `requests` | the HTTP exporter | Apache-2.0 |
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
file; the files every track needs (settings, errors, ports, facades, `models.py`, `audio.py`,
poe tasks, CLAUDE.md, `harness.toml`, ARCHITECTURE.md) belong to Block 0, and this plan and
`docs/plans/tech-debt.md` to the integrator, which copies each track's report into them
(step 14). Library paths below are under `packages/t2-agentic-voice/src/t2_agentic_voice/`; app
paths under `apps/ole5-voice-agent/src/ole5_voice/evals/`.

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
  reference refused with a `ValueError` (with no reference words, jiwer 4.0.0 returns the
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
  clip's length (Groq's documented minimum); the `DataFlow` values of the design's 6.1.
- Tests (a fake transport, no network): the request's fields equal Block 0's baseline; the
  result's shape; a cancel stops within 50 ms with no pending task and the client closed; a 429
  with `retry-after`, a 5xx, a timeout, a lost connection, a 401 and a 400 each become the right
  `ProviderError`; the key appears in no repr, error or log line, even when the fake server
  echoes the request's headers in its body; `GROQ_API_KEY` and `GROQ_BASE_URL`, set with
  monkeypatch, change nothing in the request; an empty key raises the `ConfigurationError`.

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
  read from an `OTEL_*` variable passed explicitly (the decision log).
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
  twice each, `refs.json` read 2026-11-01), its takes as variants; the import reads the lab's
  files and writes only into this repository; `import_recordings.py` reads the take sidecars of
  `models.py`; the matcher's rulings each quote the owner's words and date (Q8), and its verdict
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
- May read: `models.py`, `audio.py`, the library's facades, the matcher's and the scorecard's
  interfaces (through Block 0's fakes until their tracks merge).
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
  worktree's `history.jsonl` and copied beside the scorecard.
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
- May read: `models.py`, the library's `evals` facade, evaluation.md's "Judging a change" and
  "Run history".
- Behaviour: accuracy, WER, CER (over variants with a non-empty reference only), term and ID
  recall, text from silence, cost, latency (median and 90th percentile), violations (always 0: no
  canary applies to speech-to-text), breakdowns by language, device, kind and split, the window
  metrics, and "one speaker" on every scorecard; `eval-compare` refuses two runs whose recorded
  commits or data digests differ, naming the difference.

**Track G · The recorder (app).**
- Goal: `poe record`, the page the owner records and listens with.
- Owns: `recorder.py`, `recorder_page/index.html`, `recorder_page/recorder.js`; tests
  `test_recorder.py`.
- May read: `script.toml`'s format, `models.py` (the script line and the take sidecar),
  `audio.py`; `voice-lab/assets/talkover/` (the six agent replies and `replies.json`, served read
  only for over-the-agent and echo-only items).
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
  `--out`, never replacing one.
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
