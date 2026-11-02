# 003 · A call that listens and speaks, deployed

Status: active · Milestone: M2 · Started: 2026-11-02

## Goal

Make the first real call ([roadmap](../roadmap.md), M2): the owner opens Ole5's widget in Chrome,
starts a call, speaks Saudi Arabic, MSA or English, and hears each turn said back, on the laptop's
speakers and on a headset, locally and from other networks to a backend deployed on the owner's
host behind HTTPS, one of those networks blocking UDP. There is no talker yet: the agent says back
what it heard (echo mode). The call is built as a teammate would build one, on the library's public
API (D-013): Pipecat inside `voice` (its peer-to-peer WebRTC transport, Silero VAD and Smart Turn,
with our own speech bridges calling the ports), the `TextToSpeech` port and its Groq Orpheus
adapter with an Arabic and an English voice, `domain`'s rules for speaking numbers and IDs, signed
single-use join tokens, the router and `serve()`, the reference browser client and its protocol,
and the settings with a required `env` (the design's 16.1, M2 row). The plan measures what M2's
*Done when* asks, registered before any result: end-of-turn cut-offs and the time of each step on
the golden set, and requests per call minute for each Groq model; it settles the language a live
call sends Whisper, records the media path as a decision, and records the owner's calls with
consent, so that M3's targets are also checked on audio that came through WebRTC. Every number
describes one speaker, the owner (D-006).

## Acceptance criteria

**The call** (the library)

- [ ] `t2_agentic_voice.ports` exports `TextToSpeech` and `AudioChunk` in the shape of the
  design's 6.1, and `IdentityVerifier` and `UsedTokens` as its 6.5 has them; each port that holds
  connections has `aclose()` (TD-020).
- [ ] `t2_agentic_voice.groq.GroqTTS` speaks through `canopylabs/orpheus-arabic-saudi` and
  `canopylabs/orpheus-v1-english`, a model and a voice per language from `tts.languages`, and
  refuses text over the model's `max_chars` (200 for both). It reads the sample rate from each
  WAV's header, flags a take that came back cut short, and raises `ProviderError` for every
  failure, a model whose terms are not accepted named with its FIX. Its tests, against a fake
  transport, check the request's fields against Block 0's baseline, a cancel that stops within
  50 ms and leaves no task or connection, each failure kind, that the key appears in no repr, error
  or log line, and that `GROQ_*` variables change nothing in the request (the design's 7.3).
- [ ] No public signature names a type from `pipecat`, `aiortc`, `onnxruntime` or `groq` (the
  design's 5.3, a test over every public module).
- [ ] Fixed phrases (the greeting, the echo's frame, the notices) are synthesized once and cached
  under `var_dir`, keyed by a hash of text, model and voice (the design's 10.4); a cache hit sends
  no request.
- [ ] `t2_agentic_voice.languages` exports `speak_number` and `speak_id` in Arabic and English
  (numbers through num2words behind a `domain` function, IDs digit by digit from the library's own
  table), the clause splitter, which keeps every clause under the model's `max_chars`, and the
  pronunciation map; Ole5's entries ("Ole5" said «أُولِي فايف» and "Oh-lee five",
  `Ole5-chatbot/VOICE_LOG.md`, lines 35 and 45, the prototype's D26 and D37) are the app's data.
- [ ] `voice` runs one Pipecat pipeline per call: SmallWebRTC, Silero VAD and Smart Turn v3.2 on
  CPU with no torch, a speech-to-text bridge on `SegmentedSTTService`, a text-to-speech bridge on
  `TTSService` with `TextAggregationMode.TOKEN`, and a session bridge that is a plain
  `FrameProcessor`. Pipecat's interruptions are off, and none of its LLM services, context
  aggregators or function calls is used (the design's 13). The session's modules import no
  Pipecat (ARCH-BAN).
- [ ] The voice session in echo mode says back each turn in the voice of its language (one voice
  per reply), after the cached frame (Q3). The Stop button, Esc and `hangup` act at once: after a
  `stop`, no audio frame of that turn is sent (a test with a capturing output), and the session
  listens again.
- [ ] `HeardWords` is in `[[restricted]]`, built only in `voice`, from the commit that creates it
  ([SECURITY.md](../../SECURITY.md), invariant 1).
- [ ] Invariant 8: Pipecat's loguru output is off by default (Q2), and a test, in a child process
  with loguru's default sink in place, shows that a Pipecat DEBUG line holding a transcript
  reaches no output. Pipecat's error frames and its transport and ICE failures become library log
  lines with no call content, and `TransportFailed` or `ProviderFailed` events.
- [ ] One trace per turn, `session.id` set to the call ID, with the speech-to-text span and a
  text-to-speech span (characters, chunks, requests, time to first audio, cache hits) and the
  resource attributes of the design's 10.1. A test finds no key, join token, offer secret, TURN
  secret or access code in any exported span, and no audio.
- [ ] Each call's `CallReport` holds its usage per Groq model (requests, audio seconds sent and
  billed, TTS characters, cache hits) and its requests per call minute; `t2_agentic_voice.events`
  exports the events M2 emits (provisional, the design's 6.6).

**Call set-up** (the library)

- [ ] `t2_agentic_voice.identity.SignedJoinTokens` mints and verifies compact JWTs, HS256 only,
  with the claims, the key map and the lifetime of the design's 6.5, single use through
  `t2_agentic_voice.stores.SqliteUsedTokens`; `DevIdentity` serves only `env=dev` and loopback
  clients. Adversarial tests (invariant 7): a token used twice, expired, issued in the future
  beyond the skew, signed with another key, with an unknown `kid`, with `alg` none or any algorithm
  but HS256, with a changed claim, with no `jti`, with a lifetime over 120 s, and with a consent
  version other than `privacy.consent_version`; each is refused at `/join` in the one error shape,
  echoing no value (GP-19).
- [ ] The router serves `POST /join`, `POST` and `PATCH /offer` (both needing the call's offer
  secret), `GET /health`, `GET /ready`, `GET /client/1/t2v-client.js`, and `GET /dev` only with
  `env=dev` and only to loopback clients. A second offer gets 409; a client's `pc_id` never reaches
  Pipecat's request handler; the secret stops working when ICE completes or the call ends.
  Adversarial tests cover an offer with no secret, with another call's secret, a second offer, and
  a PATCH after the call ended (the design's 5.5). Every route answers "runtime not started" when
  the lifespan never ran.
- [ ] CORS answers only `server.allowed_origins`, with POST and PATCH listed. FastAPI's own
  tracing is off, so a global `TracerProvider` set in a test receives no FastAPI span (D-023).
- [ ] `VoiceRuntime`'s lifespan takes an exclusive lock file under `var_dir` (a second process is
  refused with a FIX line, on Windows and on Linux), warms VAD, Smart Turn and the adapters without
  a request (TD-012), builds tracing inside the lifespan (TD-014), and closes every adapter.
  `router()` and `serve()` refuse `env=test` and a runtime with no identity source.
- [ ] `t2v serve`, `t2v dev`, `t2v doctor` (the key; each language's model and voice and its
  terms; the ONNX files' SHA-256; the clock's skew) and `t2v settings show --redacted` run, and
  `--help` only prints help (GP-17).

**The browser**

- [ ] `api/static/t2v-client.js` (one ES module, no dependency, no build step) and
  `api/static/dev.html` speak `t2v/1`: every message carries `"v": 1` and comes from a closed list
  that the server parses strictly (invariant 4, GP-06), none named like Pipecat's reserved
  `signalling` messages or starting with "ping". The client sends the end-of-candidates PATCH, and
  `client_stats` (the selected candidate type, the time to connect, whether `echoCancellation`
  applied, when the first audio played).
- [ ] Ole5's widget in `apps/ole5-voice-agent/web/`: a consent screen before the microphone opens
  (Q7's wording and version), start and end, playback, captions, the Stop button and Esc, and a
  message for a microphone that is missing, busy or refused; checked by running it in Chrome, and
  in Edge as best effort (D-018, question 12).
- [ ] `.claude/launch.json` starts `t2v dev` on `examples/minimal` and the Ole5 app's dev server
  ([WORKING-RULES.md](../../../WORKING-RULES.md), "Seeing it run").

**The deployment**

- [ ] The Ole5 app runs on the owner's host behind HTTPS (Q8): `env=staging`, one worker,
  `var_dir` on a persistent volume, and Phoenix beside it with auth on and no public exposure; the
  widget is embedded in the website (Q10).
- [ ] The owner held a call from another network (a phone hotspot) and one from a network that
  blocks UDP (Q11), and heard each turn back; each call's `client_stats` shows its candidate type.
- [ ] Before M2 closes, the media path is recorded as a decision entry with the network test's
  outcome: UDP ports opened on the backend, a TURN service run as a small service, or another
  transport (Q9).
- [ ] If TURN is used, `/join` returns per-call TURN credentials minted from the shared secret
  (coturn's REST scheme); the TURN secret is a `SecretStr` that reaches no log, trace, event or
  error.

**The recordings**

- [ ] The owner's calls through the widget are recorded with `privacy.record_audio` on and the
  recording consent in the signed join token: per call, the caller's track, the agent's audio and
  the playback timeline, under `var_dir`. Adversarial tests: nothing is written with the setting
  off, with the token's consent false, or with both, and no client message turns it on
  (invariant 8). No audio is in git; each recorded call's manifest (its consent, each file's
  SHA-256 and length) is committed for M3.

**The library line**

- [ ] `VoiceSettings` as the design's 7: `env` required (`dev`, `test`, `staging` or `prod`); the
  environment read only inside `from_env(prefix=, env_file=, unknown=)`, with no singleton and no
  `.env` unless one is passed; an unknown key under the prefix an error; a `*_FILE` form for every
  secret; the groups `tts`, `turns`, `server`, `join`, `privacy`, `logging` and `storage`.
  `docs/generated/settings.md` and `.env.example` are generated from it, each with a freshness test.
- [ ] `examples/minimal` is an echo agent (`make_runtime()`), and its tests need no key and no
  network.
- [ ] The package root holds the design's 5.1 names that M2 builds, with `T2VoiceError` as the base
  error and `AppError` a deprecated alias for one minor release (TD-007); `identity`, `server`,
  `stores` and `events` are facades in `[package] public` and `facades`.
- [ ] ARCH-BAN runs in `poe arch` (the design's 12.4), with tests in `tests/harness/`. Inside
  `poe check`, while CI waits for a remote (TD-001): the torch check (no `torch` in `uv.lock`) and
  an import of every public module in a fresh subprocess (the design's 5.3 and 9.8).
- [ ] The guide's `README.md`, `is-this-for-you.md` (with the install's size measured),
  `quickstart.md` (the echo version), `serving.md`, `browser-client.md` (its M2 part),
  `tracing-and-logs.md` and `data-and-privacy.md` are written and linked from the
  [guide's index](../../guide/README.md), each code sample taken from a tested file.
- [ ] Decision entries record what the design's 16.3 lists for M2 (settings; serving and identity;
  GP-22 widened to an adapter object passed in code), Q2's logging answer (amending D-002's loguru
  bullet), ARCH-BAN and the new facades, the echo's shape (Q3), SECURITY.md's invariants 7 and 8
  brought to the design's 8.1 (amending D-007), the media path, the measured requests per call
  minute and the language a live call sends Whisper.

**The measurement** (the roadmap's *Done when* for M2)

- [ ] "The measurement, registered before any result" was complete, every owner's call settled and
  dated, before the run it affects; every departure is a `Deviation:` line in the progress log.
- [ ] `uv run poe eot` measures end of turn offline, with no spend, on the golden set's paused
  requests: cut-offs and each step's delay, by language and device; its `reference` answerer scores
  0 cut-offs and 0 ms inside `poe check`.
- [ ] The time of each step on the golden set (the VAD stop, Smart Turn's decision, Whisper, the
  echo ready, Orpheus's first byte and first sound) is measured in runs T1 and T2, and the network
  to the browser in the owner's calls.
- [ ] Requests per call minute for each Groq model, from the owner's calls, and the key's real
  limits (Q17) are recorded as a decision entry.
- [ ] The language a live call sends Whisper is set by the registered rule (runs R5 to R7), and the
  noise on another day (TD-032) is recorded.
- [ ] The owner held the calls of *Done when*: Chrome on the laptop's speakers and on a headset,
  locally and from another network to the deployed backend, each turn heard back.
- [ ] `uv run poe check` passes; the roadmap's M2 row, CLAUDE.md, ARCHITECTURE.md, SECURITY.md and
  this plan's logs are up to date.

## Plan

**Scope.** M2 is the roadmap's M2 and the design's 16.1 M2 row, with no talker: the voice session
runs in echo mode. **Left for M3:** the two-step interruption, `duck` and `unduck`, cancel scopes,
the history of what was heard, the stop, listening and echo rules and their presets, the filter
for text from silence and echo, the first window, tuning the turn defaults (Q14), `AudioCall` and
the parity test (the design's 9.5; M2 builds only an internal file-fed transport, the decision
log), and the push-to-talk fallback and the Bluetooth warning. **M4:** the talker, the chat-model
port, the vocabulary and the Whisper prompt (Q16), `TextCall` and the fakes as a public kit, the
latency target. **M5:** speaking dates, SECURITY.md generalized from tickets to actions (the
design's 16.3), and the verified identity ticket status needs, if open question 19 is still
unanswered (Q12). **M6:** the per-model limiter and the cool-off, admission control and the busy
notice, drain, the full `t2v doctor`, the deployment guide and runbook, CPU per call. **M0** keeps
CI (TD-001), `contract.md` and the app's five layers (the decision log). The public-API snapshot
(griffe) and the wheel job wait for the first teammate tag (the design's 3.1 and 13).

**From M1** (the roadmap's M2 bullet, from [plan 002's Future
improvements](../completed/002-golden-set-baseline.md#future-improvements)):
- **The prompt arm for product terms** is Q16: the agent recommends M4, where the vocabulary that
  becomes the prompt lands (the design's 3.1 and 3.3).
- **The language a live call sends Whisper** is measured here (runs R5 to R7, after the noise on
  another day), and the registered rule sets `stt.live_language`'s default (Q15).
- **Spoken numbers:** Track A speaks digits as words with num2words. TD-031, reading compound
  number words as digits when scoring, stays open: num2words turns digits into words, never words
  into digits, and none of large-v3's 11 ticket misses held a number in words (plan 002's Future
  improvements).

Blocks in the order they depend on each other. Each is built in its own worktree under
`.claude/worktrees/`, reviewed by an agent that did not write it, fixed, gated with
`uv run poe check`, and merged, with commits named `Plan 003: <what>`. Block 0 is built by one
agent and merged before any track starts; the tracks are built in parallel against Block 0's
interfaces and fakes, reviewed by concern (`## Tracks`), and merged through an integration branch,
`plan-003-integration` ([plans README](../README.md), "Parallel tracks").

**Before Block 0**

1. The garbage-collection round that another session started on 2026-11-02 (worktree
   `gc-round-1`) merges into the main branch first, so Block 0 is cut from a main branch that holds
   its fixes; the agent then re-reads the debt rows that round paid or changed (TD-006 and TD-019
   among them) before relying on them below.
2. The owner settles Q1 to Q6 ("The measurement, registered before any result"). The agent lists
   `docs/plans/active/`, `docs/plans/completed/` and [decisions.md](../../design/decisions.md),
   and asks the other sessions, before it takes the decision and debt numbers Block 0 writes
   ([WORKING-RULES.md](../../../WORKING-RULES.md), "Commits and parallel sessions").

**Block 0 · dependencies, Pipecat read, harness, settings, interfaces** (one agent)

3. **Dependencies.** One `uv add --package t2-agentic-voice ...` with exactly the packages of
   "Dependencies to install", as Q1 allows, then `uv lock`, in the same commit (CI runs
   `uv sync --locked`). Every package new to `uv.lock` is listed in the progress log with the
   licence its installed metadata declares (`importlib.metadata`), with the protobuf move (below)
   and the installed size of the environment (for `is-this-for-you.md`); a licence outside that
   section's tables stops the block and goes to the owner. `uv run poe types`, and a
   `[[tool.mypy.overrides]]` entry only for a package that ships no types (whether pipecat-ai,
   num2words and loguru do is UNVERIFIED).
4. **The installed packages, read as text** (file and line for each finding, in the progress log):
   - every environment variable that Pipecat, aiortc, aioice, uvicorn, loguru, onnxruntime and
     numba read, and which of them a value passed in code overrides (the design's 7.3, as plan 002
     read groq and OpenTelemetry); whether importing a Pipecat module calls python-dotenv's
     `load_dotenv` (UNVERIFIED; if one does, `voice` never imports it, since the library reads no
     `.env` it was not given: the design's 7.2); `PIPECAT_SCTP_MAX_CHUNK_SIZE` is read at import
     (the research step's reading of `connection.py`, 2026-11-02);
   - every Pipecat DEBUG line that holds call content (the TTS base class logs the text it
     speaks; the transport logs remote ICE candidates, which hold IP addresses; signalling
     messages), for invariant 8's test;
   - how the session bridge makes Pipecat drop queued output audio on a stop (the design's 13,
     **verify**); whether `VADProcessor`'s broadcast also travels upstream; `UserTurnProcessor`'s
     events and stop strategies without Pipecat's LLM aggregators; `SmallWebRTCRequestHandler`'s
     handling of `pc_id` and of a PATCH for an unknown one; the `TranscriptionFrame` fields
     (UNVERIFIED from the docs);
   - FastAPI's `telemetry=` argument and the span attributes it would record (UNVERIFIED), and
     uvicorn's `forwarded_allow_ips` and `proxy_headers` when passed in code.
5. **The spike, with no request to Groq.** In a scratch folder outside the repository, on the
   owner's Windows machine: a pipeline fed from a generated WAV (no golden file) through
   `VADProcessor` and `UserTurnProcessor` to a fake speech-to-text and a fake text-to-speech, and a
   SmallWebRTC answer to a local aiortc peer. It confirms the API the tracks build on (the names of
   1.15.0: `PipelineWorker`, `WorkerRunner`, `await runner.add_workers(...)`) and that asyncio's UDP
   works on Windows (UNVERIFIED). Findings go in the progress log; one that changes an interface
   below changes it before any track starts, never during one.
6. **Harness.** `[[owners]]`: `jwt` and `sqlite3` to `adapters`, `num2words` to `domain`, and
   `loguru` as Q2 rules. ARCH-BAN in a new helper, `scripts/arch_ban.py`, read from a new
   `[[bans]]` table: in the library, `pipecat.services.<vendor>` and Pipecat's LLM and
   context-aggregator modules, with `pipecat.services.stt_service`, `tts_service` and `ai_service`
   allowed in `voice`; in `voice/session/`, all of `pipecat`; in the apps and the examples,
   `pipecat` and `aiortc` (the design's 12.4). `[package] public` and `facades` gain `identity`,
   `server`, `stores` and `events`, and `tests/t2_agentic_voice/test_facades.py` their names.
   `[rules] output_allowed_files` gains `api/cli.py`. If TD-006 is still open, the `[package]`
   loading moves out of `scripts/harness_config.py` (388 of 400 lines) first.
   [ARCHITECTURE.md](../../../ARCHITECTURE.md) gains the owners' cells, ARCH-BAN in Enforcement,
   the logging convention as Q2 rules, and the widget's line in the flow (the app, not the
   library's `api`, serves its static files); CLAUDE.md gains the new facades, the widget's line and
   the new tasks, within its 120 lines. `tests/conftest.py` also removes every variable step 4
   finds that changes behaviour, and `tests/harness/test_isolation.py` checks it.
7. **Settings.** `core/config.py` becomes the design's `VoiceSettings` (7.2 to 7.6): `env`
   required, `staging` added, `from_env(prefix=, env_file=, unknown=)`, no `get_settings()`
   singleton, `extra` refused under the prefix, a `*_FILE` form for each secret (the join keys, the
   TURN secret), `storage.var_dir`, and the groups M2 needs: `tts` (`provider`, `languages`, each a
   model and a voice, from Q5; `timeout_s`; `cache_phrases` true; `trim_silence` false), `turns`
   (the starting values of the decision log), `stt.live_language` (`session` until R5 to R7 set it),
   `session.mode` (Q3), `server`, `join`, `privacy` (`record_audio` false, `consent_version` none)
   and `logging` (`content` false, `pipecat` off). The groups move into modules of their own to
   stay under ARCH-SIZE. A command, `uv run poe settings-ref`, writes `docs/generated/settings.md`
   and `.env.example` from the model, with a freshness test and a row in
   [docs/generated/README.md](../../generated/README.md). The change reaches `GroqSTT.from_settings`,
   the app's `evals/run.py` and `run_parts.py`, `tests/conftest.py` and the tests; a test proves a
   blank value still counts as unset, and every secret is a `SecretStr` in no repr or log line
   (invariant 5).
8. **Logging**, as Q2 rules (the agent's recommendation: the library's loggers sit under
   `t2_agentic_voice` on the standard library, with a `NullHandler`, while `get_logger` keeps its
   structured call shape; `configure_logging` stays a helper an app calls; `voice` owns loguru).
9. **Errors.** `T2VoiceError` as the base, `AppError` a deprecated alias (TD-007); `JoinRejected`;
   the code list in `tests/t2_agentic_voice/core/test_errors.py` grows with them.
10. **Interfaces, with stubs that raise `NotImplementedError`** (a test per stub, in the test file
    of the track that owns it, as plan 002 did):
    - the ports: `domain/ports/text_to_speech.py` (`TextToSpeech`, `AudioChunk`) and
      `domain/ports/identity.py` (`IdentityVerifier`, `UsedTokens`), and `aclose()` on
      `SpeechToText` (TD-020, the decision log);
    - `Caller` and `Consent` in `core/identity.py`; the events and `CallReport` in `core/events.py`
      (types every layer shares: ARCHITECTURE.md, "Conventions");
    - the declaration types Q3 settles (`VoiceAgent`, `Language` with its three presets and their
      greetings) in `domain/declaration.py`;
    - the `t2v/1` message models in `api/protocol.py`, which Tracks F and G both read;
    - `voice/session/io.py`: the commands and events between the session and the Pipecat modules
      (a user turn ended with its transcript; a clause played; speak, stop, hang up), so Tracks D
      and E build against it alone;
    - `VoiceRuntime`, `router()`, `serve()` and `combine_lifespans` as signatures;
    - the stubs each track fills (`## Tracks`), and the shared Groq client set-up (the header hook,
      the connection limits, `logging_unchanged` around `import groq`) moved from
      `adapters/groq_stt.py` into `adapters/groq_client.py`, so Track B builds `GroqTTS` on it
      without editing `GroqSTT`;
    - the facades with every name M2 adds and the module it lives in;
    - the fakes in `tests/t2_agentic_voice/fakes.py`: a fake `SpeechToText`, a fake
      `TextToSpeech`, a fake session I/O, a fake output transport that captures frames, and a fake
      clock.
11. **Baselines** the tracks are compared with byte for byte: the fields a `GroqTTS` call sends for
    a fixed text (`model`, `voice`, `input`, `response_format` = `wav`, passed explicitly), from
    Groq's Orpheus page (console.groq.com/docs/text-to-speech/orpheus, read 2026-11-02 by the
    research step: wav is the only format, at most 200 characters) and the prototype's call
    (`Ole5-chatbot/src/ole5_chat/voice/tts.py`, read, never run, D-010); the `t2v/1` message list
    as a fixture; the generated settings reference; `uv run poe arch` and `uv run poe docs` clean.
12. **The decision entries**, with the numbers checked in step 2: settings (precedence, the prefix,
    a required `env`); serving and identity (the sidecar and the mount, one process per `var_dir`
    with the lock file, one `identity=` source, the join token's format, the offer secret, consent
    in the token); GP-22 widened to "by a setting, or by passing an adapter object in code"; the
    logging and loguru (Q2, amending D-002's bullet); ARCH-BAN and the new facades; the echo's shape
    (Q3); and invariants 7 and 8 brought to the design's 8.1 (the offer secret and the lock file;
    the consent claim as the second condition for audio), which amends D-007. Each is written as
    Accepted where the approved design describes it, and Proposed where it goes beyond, as the
    owner ruled for M1 (plan 002, Q3).
13. Gate, review (the harness and security reviewers), fixes, merge into `plan-003-integration`.

**The tracks** (in parallel, after Block 0; each track's files, reads and tests are in `## Tracks`)

14. Track A: speech text. Track B: the Orpheus adapter and the phrase cache. Track C: identity,
    stores and TURN credentials. Track D: the voice session in echo mode, its usage, spans and
    recording. Track E: the Pipecat modules. Track F: `api`, the CLI and `examples/minimal`. Track G:
    the browser client, the widget and the Ole5 app's server. Track H: the measurement's tooling.
    Track I: the guide. Each track ends with a report: its progress-log lines (prototype sources,
    values chosen), its decision-log lines and any debt rows.
15. Merge in the order A, C, B, D, E, F, G, H, I (`Plan 003: merge track X`, then
    `Plan 003: review fixes, track X`), with the full gate after each merge. The integrator is the
    only writer of this plan and of `docs/plans/tech-debt.md`, and copies each track's report into
    them in the `merge track X` commit, as plan 002 did.
16. **The integration check, with no spend.** Inside `poe check`: an aiortc client in a test joins,
    offers, sends a generated signal through a fake speech detector (no audio file:
    `tests/ole5_voice/evals/test_no_audio.py`), and receives the echo's audio from the fake
    `TextToSpeech`; `poe eot --answerer reference --split dev` scores 0 cut-offs and 0 ms. By hand:
    the agent starts `t2v dev` on `examples/minimal` with fake providers and opens `/dev` on
    localhost in the browser pane: the page loads, ICE connects on host candidates, the data
    channel opens and `hello` arrives.
17. **The whole-plan review of the code**, by every reviewer. Then `plan-003-integration` merges into
    the main branch, with the full gate, so the owner's calls and the deployment run from it; from
    here, this plan's blocks merge into the main branch.

**The first live calls** (local; needs Q5 and Q7, and "What the owner does", steps 2 and 3)

18. The owner's first calls on the laptop, from the main checkout, through the Ole5 app's dev
    server on localhost: the laptop's speakers, then the wired headset, a few turns each, in the
    three languages. The agent reads each call's trace and `CallReport`; a fix is a block of its
    own. These calls are not recorded unless Q7 is settled first.

**The deployment** (needs Q8 to Q12)

19. **The deployment files**, written by the agent in `apps/ole5-voice-agent/deploy/`: the image,
    a compose file with the backend, Phoenix and, if Q9 picks it, coturn; the reverse proxy's and
    coturn's configuration as templates holding no secret; and the steps for the owner. Reviewed
    by the security reviewer. The owner runs them on the host; the agent never logs into it.
20. **The network spike on the host** (the design's 11, **verify**): what aiortc advertises behind
    Docker's NAT; whether coturn relays to a backend on the same host; a call relayed over TLS on
    443; each outcome in the progress log, before the network test.
21. **The website embed** (Q10) and the network test: a call from the phone hotspot and one from the
    network that blocks UDP (Q11), each on the laptop's speakers and on the headset.
22. **The media path**, recorded as a decision entry from the network test's outcome (the roadmap's
    M2: "Before M2 closes").

**The registered runs** (the registration below; a quiet machine: nothing else runs beside a run,
[WORKING-RULES.md](../../../WORKING-RULES.md), "Measurement runs")

23. Every open call settled and dated; the estimate and the budget cap approved by the owner (Q13).
    Before each run or call session that spends, the spend so far plus its own estimate is compared
    with the cap, and one that would pass it does not start; the running total goes into the
    progress log after each, as plan 002's step 20 did.
24. A clean run worktree at the measurement commit, where every run of steps 25 to 27 starts;
    `poe eval --show-settings` checks the resolved settings; each run's smoke test passes with no
    failed, retried or refused call.
25. **E1 and E2** (end of turn, offline, no spend): the dev paused requests and the secondary set,
    twice.
26. **R5, R7, R6** (the noise on another day and the live language), each history line carried to
    the main branch in its own commit before the next run, then the run worktree's file reset, as
    plan 002's step 23 did; the comparisons; the rule sets `stt.live_language`'s default in its own
    commit.
27. **T1 and T2** (the time of each step), on a day whose Orpheus requests leave room for them (the
    published 100 a day per model, Q17).
28. **C** (the owner's calls of Q18), recorded; the recordings copied to the owner's machine and
    their manifests committed; requests per call minute recorded as a decision entry, beside the
    key's real limits.
29. **Held-out:** E on held-out once, at the close, aggregates only. No held-out run spends in M2.

**Close**

30. The decision entries not yet written; the guide's pages finished; the design's factual slips
    that the research found (the design's 4.1 on Pipecat's `silero` extra, which exists with no
    requirements; its 3.2 on Groq's account team, where Groq's changelog gives terms acceptance as
    the gate; its 10.3's "No number is known yet") listed for the owner and corrected as facts, not
    design changes; `## Future improvements` in this plan, with a pointer from the roadmap's
    "Planned later"; the whole-plan review; the roadmap's M2 row set to `done` with a link; this plan
    moved to `completed/` with its Status line; the final gate.

## Progress log

- 2026-11-02: Plan written by the agent, at the owner's request to start M2, from three research
  reports made that day by a workflow of agents: what the repository's design and code require and
  what exists (the roadmap, the design, the decisions, SECURITY.md, harness.toml and the code); what
  the old prototype learned about a live call (read only, D-010); and the outside tools (Pipecat
  1.15.0, Smart Turn v3.2, loguru, Groq's text-to-speech and rate-limit pages, aiortc and aioice,
  coturn and hosted TURN, FastAPI, Starlette and uvicorn; every page read 2026-11-02, cited where
  used). The agent re-read at their source the facts the plan relies on: the roadmap's M2, the
  design's 3, 4.5, 5.1 to 5.5, 6.1, 6.5, 6.6, 7, 8.1, 10, 11, 12.2, 12.4, 13, 14, 16 and 17;
  D-002, D-005 and D-018 to D-025; SECURITY.md, evaluation.md, WORKING-RULES.md, harness.toml,
  ARCHITECTURE.md and tech-debt.md; plan 002's registration and Future improvements; the golden
  set's paused-request items, their split and their labels (counted: 10 items, 39 variants, one
  `turn_ends_ms` each; dev 6 items and 23 variants); `tests/ole5_voice/evals/test_no_item_in_source.py`;
  `poe eval`'s flags (`--language-hint auto` exists); the prototype's D24, D26, D29, D35, D37 and
  D43 (`Ole5-chatbot/VOICE_LOG.md`) and its voice settings (`Ole5-chatbot/src/ole5_chat/config.py`,
  lines 71-74). The agent also read on PyPI, 2026-11-02: PyJWT 2.15.1, num2words 0.5.14, soxr 1.0.0,
  av 17.0.0, loudness 0.2.0, onnxruntime 1.31.1, opencv-python-headless 4.12.0.88, aiortc 1.15.0,
  fastapi 0.162.0, uvicorn 0.54.0, pipecat-ai 1.15.0's requirements, opentelemetry-proto 1.45.2,
  googleapis-common-protos 1.76.0 and protobuf 6.33.5; and the pyav-ffmpeg README
  (github.com/pyav-org/pyav-ffmpeg). The future improvements M1 left were recorded at plan 002's
  close and placed under M2, M3 and M5 in the roadmap before this plan (commit 5f1c60a). Nothing is
  built, no package added and no request sent to Groq; the gate ran with `uv run --offline`, which
  built the worktree's environment from uv's cache. The roadmap's M2 row is changed to
  `in progress` with a link to this plan in the commit that adds it (DOC-PLAN fails until then).
  Next: the garbage-collection round's merge, then the owner's calls before Block 0 (Q1 to Q6).

## Decision log

All entries are the agent's choices of 2026-11-02, with the agent's reasons; the owner may overrule
any before the step it affects.

- 2026-11-02: One plan for M2, with Block 0 and nine tracks, as plan 002 was built: the tracks touch
  disjoint files once Block 0 holds the settings, the ports, the protocol and the session's I/O.
  Alternative: two plans (the call, then the deployment and measurement); set aside because the
  deployment and the measurement run on the same interfaces and the roadmap gives M2 one *Done when*.
- 2026-11-02: The echo is the only responder (the roadmap's "No talker yet"), so the plan builds no
  chat-model port and no prompt.
- 2026-11-02: M2 builds an internal file-fed transport in `voice` (`voice/file_transport.py`), which
  the tests, `poe eot` and runs T1 and T2 use, while the public `AudioCall` and the parity test stay
  in M3 (the design's 9.5 and 16.1). M2's *Done when* measures end of turn and each step "on the
  golden set", which needs the same `voice` modules fed from files; making it public is M3's choice.
- 2026-11-02: The measurement tooling reaches the file-fed pipeline through two provisional
  functions in `testing`, re-exported by the `evals` facade (`turn_ends` and `echo_timings`), since
  an app imports only public modules (ARCH-PUBLIC) and `testing` is not public yet (D-019's
  Proposed bullet).
- 2026-11-02: The turn settings start at these values, each a setting and none tuned in M2 (Q14):
  Silero's confidence 0.7, start 200 ms, stop 200 ms (the design's 7.6 `vad_stop_ms`) and minimum
  volume 0.6, Pipecat's `VADParams` defaults; Smart Turn v3.2 on, `stop_secs` 3.0, `pre_speech_ms`
  500 and `max_duration_secs` 8, as Pipecat's Smart Turn page gives them; `max_silence_ms` 3000,
  the same fallback (docs.pipecat.ai/server/utilities/turn-detection/smart-turn-overview and
  .../audio/silero-vad-analyzer, read 2026-11-02 by the research step). Smart Turn's stop strategy is
  set explicitly, since 1.15.0 made `StrategyMode.ALL` the default (the design's 13; Pipecat's
  changelog, read 2026-11-02).
- 2026-11-02: Speech that ends a turn while the echo plays is queued and said back after it, one turn
  at most; only Stop, Esc and `hangup` interrupt in M2, since the interruption rules are M3's. The
  recordings keep the overlap for M3.
- 2026-11-02: The echo's frame is a fixed phrase, cached, so the first audio after a turn plays from
  the cache while Orpheus synthesizes the heard words; one voice speaks each reply, the language's
  (the prototype's D35: mixed voices sound "like a different person", `Ole5-chatbot/VOICE_LOG.md`,
  line 43).
- 2026-11-02: Live calls send Whisper the session's language, from the language the caller picks in
  the widget (Arabic first) and the token's `locale`, through `stt.live_language = "session"`, until
  runs R5 to R7 decide: M1 measured only a language hint (D-024, D-025), and a default moves only on a
  registered measurement (GP-18). The widget's language buttons are built either way (Track G).
- 2026-11-02: Orpheus's audio is kept as it comes: trimming its silence (the prototype's D25, 0.4 to
  0.7 s before speech) lands behind `tts.trim_silence`, off, and runs T1 and T2 measure the leading
  silence, so M4's latency target can weigh it. A take that came back cut short (the prototype's
  ceilings of 24 characters a second for Arabic and 30 for English, `Ole5-chatbot/src/ole5_chat/voice/tts.py`,
  lines 24-36) is flagged on its span and in the report, not made again, in M2.
- 2026-11-02: Speaking rules in M2: a run of five or more digits is an ID, read digit by digit from
  the library's own table; a shorter run is a number, through num2words (MSA forms in Arabic, which
  num2words gives; Saudi forms are not in it). The agent's starting rule, revisited when M4's
  templates name `{x:id}` and `{x:number}` explicitly. Dates are spoken from M5, when status replies
  need them.
- 2026-11-02: The Ole5 app serves by mounting the library's router in its own FastAPI app, one
  worker, beside its token route and its widget's static files (the design's 4.5, "The mount");
  `serve()` is built too, and `examples/minimal` uses it (Core proof). The sidecar is the shape when
  the website mints tokens (open question 19), which waits on Q12.
- 2026-11-02: The deployed backend runs with `env=staging`: the production checks hold (no
  `DevIdentity`, no dev page, no `logging.content`, the design's 7.4) while no customer uses it.
- 2026-11-02: The widget is checked by running it in Chrome (the browser pane on localhost) and by
  the owner's calls; no headless-browser package is added, which TD-022 leaves to the owner, and the
  widget gets a debt row like the recorder's.
- 2026-11-02: The generated settings reference is `docs/generated/settings.md`, where GP-11 puts
  generated docs with their freshness tests, and the guide's index links to it; the design's 7.7
  (`docs/reference/settings.md`) and 14 (`reference/settings.md`) differ, and the guide's index
  names only `settings.md`.
- 2026-11-02: `reference/api.md` (griffe) waits for the first teammate tag, as the design's 3.1 and
  13 schedule the snapshot; its 14 says "M2 onward", which would add a dependency no reader needs
  yet.
- 2026-11-02: `contract.md` and the app's five layers stay with M0, as plan 002 left them: no M2 code
  depends on either, and the app's new code (its settings, token route and server) is small.
- 2026-11-02: `aclose()` joins `SpeechToText` and `TextToSpeech` now (TD-020), since M2's runtime
  owns the adapters' lifetimes; a change to stable ports beyond the design's 6.1, written as
  Proposed in its decision entry.
- 2026-11-02: Debt paid in M2: TD-007, TD-012, TD-014, TD-020, TD-026 (before R7, so the comparison
  refuses any setting but the language hint), TD-027 (httpx declared), TD-011 (read in R7's smoke
  step), TD-032 (R5 and R6), and TD-006 if still open. TD-004 follows Q8: with no proxy on the host,
  the clients turn `trust_env` off; with one, a proxy setting is added. TD-003, TD-005 and TD-015
  stay: `GroqTTS` imports groq inside `logging_unchanged` as `GroqSTT` does, the owner kept TD-005 as
  debt (2026-11-01), and the deployed Phoenix is reached on the host itself.
- 2026-11-02: FastAPI 0.162.0 depends on `opentelemetry-api` and traces itself through the global
  provider (fastapi.tiangolo.com/advanced/opentelemetry/, read 2026-11-02 by the research step), so
  `router()` and `serve()` pass its telemetry off: the library never instruments another library
  (D-023).
- 2026-11-02: `t2v/1` names no message `signalling` and none starting with "ping", which
  SmallWebRTC reserves on the data channel (Pipecat's `connection.py`, read 2026-11-02 by the
  research step).
- 2026-11-02: The client sends the empty end-of-candidates PATCH, because aioice 0.11.0 now waits for
  it before declaring ICE failed (its changelog, read 2026-11-02 by the research step); without it a
  failed call shows only at Pipecat's 60 s connection timeout.
- 2026-11-02: TURN is needed for the call from a network that blocks UDP whatever ports the host
  opens: aioice gathers UDP host candidates only and cannot pin its port range (its `ice.py`; the
  port-range pull request, github.com/aiortc/aioice/pull/112, is still open; both read 2026-11-02 by
  the research step). So Q9 asks how to run TURN, not whether, and the design's "only if the network
  test needs it" (its 3.1 and 11) is read as settled by the roadmap's own test.
- 2026-11-02: The recordings: the caller's track as the pipeline hears it, 16 kHz mono 16-bit WAV
  (the golden set's format, `ole5_voice/evals/audio.py`); the agent's audio as sent, 24 kHz mono
  WAV (the pipeline's output rate, `PipelineParams`); and a timeline JSON per call (each clause's
  text, when it was sent and when the browser reported it playing, each stop and each turn end).
  Under `var_dir/recordings/<call ID>/`; each call's manifest (consent, hashes, lengths, no audio)
  committed under `apps/ole5-voice-agent/evals/calls/`, so M3 imports them as golden items with
  references the owner confirms, as plan 002's import did.
- 2026-11-02: The access code of Q4, if chosen, lives in the Ole5 app, not the library: it is
  "whatever mints the token" (the design's 3.2), so `Authenticate` stays unbuilt unless open
  question 19's answer is the one-time email code.
- 2026-11-02: The session's language and voice, the Stop path and the recorder are library
  behaviour; Ole5's pronunciation entries, consent wording, access code and widget are the app's.
  ARCH-WORDS keeps "ole5" out of the library's `src/`.
- 2026-11-02: Two library names hold words that are golden references: the protocol's `stop`
  message and the client's `stop()` method (the design's 4.5 and 5.5) equal the English stop-word
  item "stop", and `tests/ole5_voice/evals/test_no_item_in_source.py` reads every string and every
  JS and HTML file under `packages/`. Only the owner adds an entry to `allowed_in_source.toml`, so
  this is Q6. Every other text avoids the one-word references (okay, wait, yeah, and the Arabic
  ones), as plan 002's tracks did.
- 2026-11-02: eot-bench (the design's 13, "Depend (dev)") is not added in M2: its Arabic slice is not
  Saudi speech, and the golden set's paused requests are the registered data.
- 2026-11-02: The runs are attended, made by the agent in this session one after another, as in M1;
  an unattended schedule only if the owner asks for one. Whisper runs pace at 10 requests a minute,
  as plan 002's did after the owner's "Something might", until Q17 says otherwise.
- 2026-11-02: The measured requests per call minute go into a decision entry, as D-024 recorded the
  noise, so M6 cites them when it sets the cap on live calls.

## The owner's decisions

What the owner has already said that binds M2, in the owner's words where they wrote them:

- 2026-11-02, the request that starts this plan: "If everything is good, record the "Future
  improvements" and start implementing M2".
- 2026-11-01: "Approve all", for the roadmap's M1 to M7 and the package design as amended (D-017),
  as plan 000 records it. So M2's goal and *Done when*, and the design's 16.1 M2 row, bind this plan.
- 2026-11-01, the owner's answers to the design's open questions (D-018) that M2 builds on: our own
  thin client and protocol (1); one install, with no extras (2); Python 3.12 (3); `T2V_` (4); one
  process per `var_dir` (5); our own spans (7); Pipecat's STT and TTS base classes wrapped, its model
  services and interruptions unused (8); one shared Groq key, each app setting its share (11); Chrome
  and Edge supported (12); JWT, HS256 only (18); the licence list of the design's 13 (20); the key's
  real limits read in M2, Groq asked to raise them if they are low, repeated phrases cached (21); the
  sidecar by default and the mount for one-worker apps (22). On teammates' audio sent to Groq (10):
  "Do not worry about this, I will explain this to anyone that wants to use the package." On how
  Ole5's website proves who the customer is (19): not known yet; "M2 builds sign-in only after the
  answer" (the design's 17).
- 2026-11-01, plan 002: "Yes, as Accepted", to whether "Approve all" covers the decision entries for
  what the approved design describes, with the agent's note that anything beyond the design is
  written as Proposed. This plan writes its entries the same way (step 12).
- 2026-11-01, plan 002, asked whether anything else uses the key during the runs: "Something might".
- 2026-11-01, plan 002, Q14: no auto-detect arm in M1 ("Yes, all recommended (Recommended)"), so M2
  decides how a live call sets the language.
- 2026-10-28 (D-005): "I can not host anything other than the website itself, the backend and some
  small services."
- 2026-10-28 (D-004): "Also for now I can only use the Groq API key, we can not try other models for
  now."
- 2026-10-28 (D-006): "For Phase 0, I do not have the ability to gather data other than my own. I am
  the only one working in this repo."

Earlier, in the prototype's own log (not a decision of this project): its D29, 2026-10-26, chose
the male voices `abdullah` for Arabic and `troy` for English, "User's choice from samples"
(`Ole5-chatbot/VOICE_LOG.md`, line 37). Q5 offers them as the recommendation.

## Dependencies to install

All go to the library's one install (D-018, question 2), in one command from the repository root,
with the lock in the same commit, once the owner allows them (Q1):

```
uv add --package t2-agentic-voice "pipecat-ai[webrtc]~=1.15.0" "fastapi>=0.162.0" "uvicorn>=0.54.0" "PyJWT>=2.15.1" "num2words>=0.5.14" "loguru>=0.7.3" "httpx>=0.28.1,<1"
```

| Package | Constraint | Version the lock should take | Licence | Owning layer (`[[owners]]`) | Why M2 needs it |
| --- | --- | --- | --- | --- | --- |
| `pipecat-ai[webrtc]` | `~=1.15.0` (the design's 5.4) | 1.15.0, uploaded 2026-10-29 | BSD-2-Clause (PyPI, read 2026-11-02) | `voice` (`pipecat`, already listed) | The pipeline, SmallWebRTC, Silero VAD and Smart Turn v3.2 (both ONNX files in its wheel), the STT and TTS base classes |
| `fastapi` | `>=0.162.0` (the floor the design's 4.5 leaves to this plan: router lifespans merged, checked in 0.162.0) | 0.162.0, 2026-10-23 | MIT (PyPI, read 2026-11-02) | `api` (already listed) | The router, the lifespan, CORS |
| `uvicorn` | `>=0.54.0` | 0.54.0, 2026-09-25 | BSD-3-Clause (PyPI, read 2026-11-02) | `api` (already listed) | `serve()`, `t2v serve` and `t2v dev` |
| `PyJWT` | `>=2.15.1` | 2.15.1, 2026-09-28; no dependency without its `crypto` extra | MIT (PyPI, read 2026-11-02) | `adapters` (`jwt`, a new row) | `SignedJoinTokens`, HS256 only |
| `num2words` | `>=0.5.14` (Pipecat requires the same) | 0.5.14, 2024-12-17; needs `docopt` | LGPL (PyPI's classifier, read 2026-11-02); accepted as LGPL-2.1, unmodified, behind a `domain` function (D-018, question 20) | `domain` (a new row) | `speak_number` |
| `loguru` | `>=0.7.3` (Pipecat requires `~=0.7.3`) | 0.7.3, 2024-12-06 | MIT (the research step, PyPI, read 2026-11-02) | `voice`, or `core` if Q2 says so (a new row) | `logger.disable("pipecat")` and the forward sink |
| `httpx` | `>=0.28.1,<1` | 0.28.1, already locked | BSD-3-Clause (plan 002, step 2) | `adapters` (already listed) | TD-027: the adapters name it, and it arrived only through groq |

**Indirect packages** that come with them; no layer imports them, so they get no `[[owners]]` row.
"Checked" marks a licence read on PyPI on 2026-11-02 (by the agent, or by the research step); the
rest are the agent's memory, UNVERIFIED until step 3 reads the installed metadata. Versions not
given are the ones `uv lock` resolves, listed in step 3.

| Package | Comes with | Licence |
| --- | --- | --- |
| `aiortc` 1.15.0 | Pipecat's `webrtc` extra | BSD-3-Clause (checked) |
| `aioice` 0.11.0 (uploaded 2026-11-01), `pylibsrtp` 1.0.0, `pyee`, `dnspython`, `ifaddr` | aiortc | BSD-3-Clause for aioice (checked); BSD-3-Clause, MIT, ISC and MIT for the others |
| `av` 17.0.0 (PyAV) | aiortc | BSD-3-Clause for PyAV itself (checked). Its binary wheels bundle FFmpeg built by pyav-ffmpeg, whose README lists x264 and x265 among the libraries built in (read 2026-11-02); both are GPL, so the bundled FFmpeg is likely GPL. UNVERIFIED: the README states no licence. Q1 |
| `opencv-python-headless` 4.12.0.88 | Pipecat's `webrtc` extra | Apache-2.0 for OpenCV, MIT for the packaging; "All wheels ship with FFmpeg", under LGPLv2.1 (checked). It caps numpy below 2.3 |
| `cryptography`, `pyopenssl`, `google-crc32c` 1.9.0, `cffi`, `pycparser` | aiortc, soundfile | Apache-2.0 or BSD-3-Clause; Apache-2.0; Apache-2.0; MIT; BSD-3-Clause |
| `onnxruntime` 1.31.1, `flatbuffers`, `packaging` | Pipecat | MIT (checked); Apache-2.0; Apache-2.0 or BSD-2-Clause |
| `numpy`, `numba` 0.68.1, `llvmlite` | Pipecat, resampy | BSD-3-Clause; BSD-2-Clause; BSD-2-Clause with LLVM's Apache-2.0 and its exceptions |
| `soxr` 1.0.0 | Pipecat | LGPL-2.1-or-later (checked). Q1 |
| `soundfile` | Pipecat | BSD-3-Clause; its wheels bundle libsndfile, LGPL-2.1. Q1 |
| `resampy`, `loudness` 0.2.0, `sentencex` 1.0.32 (Pipecat pins it) | Pipecat | ISC; MIT (checked); MIT (the design's 13) |
| `openai`, `jiter`, `tqdm` | Pipecat | Apache-2.0; MIT; MPL-2.0 and MIT. Q1 |
| `aiohttp` and `aiohappyeyeballs`, `aiosignal`, `attrs`, `frozenlist`, `multidict`, `propcache`, `yarl`; `aiofiles` | Pipecat | Apache-2.0 and MIT; PSF-2.0; Apache-2.0; MIT; Apache-2.0 (the last four); Apache-2.0 |
| `Pillow`, `Markdown`, `docstring_parser`, `websockets`, `PyYAML`, `python-dotenv`, `docopt` | Pipecat, num2words | MIT-CMU; BSD-3-Clause; MIT; BSD-3-Clause; MIT; BSD-3-Clause; MIT |
| `win32-setctime` (Windows only), `colorama` (already locked) | loguru | MIT; BSD-3-Clause |
| `starlette` (1.10.0, the research step), `annotated-doc`, `typing-inspection` (already locked) | FastAPI | BSD-3-Clause; MIT; MIT |
| `click`, `h11` (already locked) | uvicorn | BSD-3-Clause; MIT |

**A locked package that moves:** Pipecat 1.15.0 requires `protobuf<7,>=5.29.6`, and
googleapis-common-protos 1.76.0 (under the OTLP exporter) `protobuf>=6.33.5,<8` (both read on PyPI,
2026-11-02), so the lock moves protobuf from 7.36.2 down to a 6.33 release (6.33.5 exists, with an
abi3 wheel for Windows: PyPI, read 2026-11-02). Same licence, BSD-3-Clause; the tracing tests run on
it in step 3.

**Size.** The wheels are heavy: Pipecat's own is 12.2 MB (the design's 11), and onnxruntime, numba
with llvmlite, OpenCV, PyAV and numpy are each tens of megabytes (the agent's estimate, UNVERIFIED);
step 3 measures the installed size for `is-this-for-you.md`.

**Not installed:**

- **coturn** 4.18.0 (2026-09-08, BSD-3-Clause; github.com/coturn/coturn/releases, read 2026-11-02 by
  the research step), if Q9 picks it: run on the host as a small service from its own image or the
  host's packages, never added to a member.
- **Arize Phoenix** 21.0.0, run as in M1 (D-023), on the host for the deployment.
- Not used: Pipecat's `local-smart-turn` extra (torch and transformers), its `runner` extra, its
  client-js and small-webrtc-transport (which pull in daily-js), `openinference-instrumentation-pipecat`
  (D-018, question 7), a headless browser, griffe, eot-bench, and any download at runtime (the
  design's 11).

## Tracks

Each track builds in its own worktree against Block 0's interfaces and the fakes in
`tests/t2_agentic_voice/fakes.py`, never against another track's unfinished code. One owner per
file; the files every track needs (the `pyproject.toml` files, `uv.lock`, `harness.toml`,
ARCHITECTURE.md, CLAUDE.md, SECURITY.md, the settings, logging, errors, ports, `core/identity.py`,
`core/events.py`, `domain/declaration.py`, `api/protocol.py`, `voice/session/io.py`,
`adapters/groq_client.py`, the facades, `scripts/`, `.env.example`, `docs/generated/settings.md`,
`tests/conftest.py`, `tests/harness/` and the fakes) belong to Block 0, and this plan and
`docs/plans/tech-debt.md` to the integrator. A track that needs one changed asks the integrator.
Library paths are under `packages/t2-agentic-voice/src/t2_agentic_voice/`; library tests under
`tests/t2_agentic_voice/`. In every track, no source string and no JS or HTML text under `packages/`,
`apps/*/src` or `examples/` holds a golden reference as whole words (Q6 rules on `stop`).

**Track A · Speech text (library, `domain`).**
- Goal: `speak_number`, `speak_id`, the clause splitter and the pronunciation map.
- Owns: `domain/text/speaking.py`, `domain/text/clauses.py`, `domain/text/pronounce.py`; tests
  `domain/test_speaking.py`, `domain/test_clauses.py`, `domain/test_pronounce.py`.
- May read: `Ole5-chatbot/src/ole5_chat/voice/speakable.py` (digit words, "ending in", the shaping
  of text for speech, lines 7-41 and 109-157); num2words' documentation.
- Tests: digits and numbers in Arabic and English; a 16-digit ticket number read digit by digit;
  Arabic-Indic digits; the splitter on «،», «؟», «.» and English punctuation, every clause under
  `max_chars`, none cut inside a word; the pronunciation map whole words only.

**Track B · The Orpheus adapter and the phrase cache (library, `adapters`).**
- Goal: `GroqTTS` and the phrase cache.
- Owns: `adapters/groq_tts.py`, `adapters/wav_stream.py` (a streamed WAV parsed whatever its chunk
  boundaries, the leading silence measured and trimmed when `tts.trim_silence` is on),
  `adapters/phrase_cache.py`; tests `adapters/test_groq_tts.py`, `test_wav_stream.py`,
  `test_phrase_cache.py`.
- May read: the ports, the settings, `adapters/groq_client.py`; Groq's text-to-speech pages; the
  prototype's `tts.py` (its `WavStream`, the cut-short check) and `fillers.py` (the cache), read only.
- Behaviour: the key, base URL and timeout passed explicitly; SDK retries off; the 400
  `model_terms_required` error (quoted by a third party, github.com/langflow-ai/langflow/issues/11120,
  2025-12-21; Groq's docs do not give it, so UNVERIFIED) mapped to a rejected `ProviderError` whose
  FIX names the console's terms; the WAV's sample rate read, never assumed (Groq does not state it:
  24 kHz per Pipecat's Groq service and the Orpheus code, UNVERIFIED); cache files written whole to a
  temporary name and renamed.
- Tests: as the acceptance criteria; the cache key changes with text, model and voice; a cache hit
  sends nothing; `GROQ_LOG=debug` in a child process, as `GroqSTT`'s test does (TD-003).

**Track C · Identity, stores and TURN credentials (library, `adapters`).**
- Goal: `SignedJoinTokens`, `DevIdentity`, `SqliteUsedTokens`, `MemoryUsedTokens`, coturn's REST
  credentials.
- Owns: `adapters/join_tokens.py`, `adapters/dev_identity.py`, `adapters/used_tokens.py`,
  `adapters/turn_credentials.py`; tests under `adapters/`.
- May read: the identity port, `core/identity.py`, the settings; PyJWT's and coturn's documentation.
- Tests: invariant 7's adversarial cases (the acceptance criteria); the used-token store under two
  threads and after a restart; the TURN password the HMAC of coturn's scheme on a fixed vector, and
  the secret in no repr, log line or error.

**Track D · The voice session in echo mode (library, `voice/session/`, no Pipecat).**
- Goal: one call's session: turn order, the echo, Stop and `hangup`, the queued turn, heard words,
  playback bookkeeping, usage per model and per call minute, the `CallReport`, the turn and TTS
  spans, and the call recorder.
- Owns: `voice/session/call.py`, `echo.py`, `heard.py`, `playback.py`, `usage.py`, `recording.py`;
  `core/tracing_tts.py` (the TTS span and the resource attributes); tests under `voice/session/`
  and `core/test_tracing_tts.py`; the `[[restricted]]` row for `HeardWords` (applied by the
  integrator at the merge, `harness.toml` being Block 0's).
- May read: `voice/session/io.py`, the ports, `core/events.py`, `core/tracing.py`, Track A's
  signatures; the prototype's `capture.py` (one record per utterance, audio only when switched on)
  and `session.py`'s clock (lines 234-253), read only.
- Tests: with the fake session I/O, fake ports and the fake clock: the echo per language; Stop and
  `hangup`; a turn queued during the echo; usage counted per model; the recorder writes nothing with
  the setting off, with the consent false, or both, and a client message cannot change either; no
  secret in any span.

**Track E · The Pipecat modules (library, `voice`).**
- Goal: the pipeline per call and everything that touches Pipecat.
- Owns: `voice/pipeline.py`, `voice/transport.py`, `voice/turns.py`, `voice/stt_bridge.py`,
  `voice/tts_bridge.py`, `voice/session_bridge.py`, `voice/loguru_policy.py`,
  `voice/pipecat_events.py`, `voice/file_transport.py`; tests under `voice/`.
- May read: Block 0's reading of the installed Pipecat (step 4) and the spike's findings (step 5);
  Pipecat's documentation and examples (`p2p-webrtc/voice-agent/server.py` and `index.html`, read
  2026-11-02 by the research step).
- Tests: each bridge against fakes; a `stop` drops the turn's queued audio; no Pipecat interruption
  fires; invariant 8's test in a child process; an error frame becomes a `TransportFailed` or
  `ProviderFailed` event and a log line with no content; the file-fed transport at real-time pace.

**Track F · `api`, the CLI and `examples/minimal` (library).**
- Goal: `VoiceRuntime` and its lifespan, the lock file, the router, the offer secret, CORS, the
  error shape, `serve()`, `combine_lifespans`, `t2v`, and the minimal example as an echo agent.
- Owns: `api/runtime.py`, `api/lockfile.py`, `api/router.py`, `api/offers.py`, `api/http_errors.py`,
  `api/server.py`, `api/cli.py`, `api/doctor.py`; `examples/minimal/src/minimal_example/`; tests under
  `api/` and `tests/minimal_example/`.
- May read: the protocol models, the ports, the adapters' signatures, `voice`'s entry point,
  Pipecat's request handler as Block 0 read it.
- Tests: the acceptance criteria's set-up cases; the lock file across two processes; the loopback
  test of step 16; `--help` for each `t2v` command.

**Track G · The browser client, the widget and the Ole5 app's server.**
- Goal: `t2v-client.js`, `dev.html`, Ole5's widget, and the app's server: its settings
  (`OLE5_VOICE_` for its own, `T2V_` for the library's, the design's 7.3), its token route (Q4) and
  its static files.
- Owns: `api/static/t2v-client.js`, `api/static/dev.html`; `apps/ole5-voice-agent/web/`;
  `apps/ole5-voice-agent/src/ole5_voice/settings.py`, `server.py`, `token_route.py`; tests
  `tests/ole5_voice/test_server.py`, `test_token_route.py`; `.claude/launch.json`.
- May read: the protocol models; the recorder's page (`ole5_voice/evals/recorder_page/`: its consent
  screen, capture with echo cancellation, its microphone errors); the prototype's `web/voice.js`
  (starting audio inside a click, the microphone error map), read only.
- Tests: the token route's adversarial cases (a wrong code, compared in constant time; repeated tries
  from one address slowed; consent passed through into the token, never taken from a later message);
  the page checked in Chrome and in Edge.

**Track H · The measurement's tooling (library `testing`, app `evals`).**
- Goal: `poe eot`, the timing run, the recorded calls' manifests, and what runs R5 to R7 need.
- Owns: `testing/turns.py`, `testing/echo_timing.py`; in `apps/ole5-voice-agent/src/ole5_voice/evals/`,
  `eot.py`, `timing.py`, `call_manifests.py`, and the changes to `answerers.py` (split first,
  TD-019), `compare.py` (`--allow-setting`, TD-026), `runs.py` and `history.py` (the new run kinds);
  the poe tasks `eot` and `eval-timing` (asked of the integrator); tests under `tests/ole5_voice/evals/`
  and `testing/`.
- May read: the registration below, evaluation.md's "Running", the file-fed transport's interface.
- Tests: the `reference` answerer of `poe eot` at 0 cut-offs and 0 ms; the scorer on hand-made
  decision sequences (a cut-off, a miss, a late end); a timing run refusing the main checkout and a
  dirty tree; held-out writing aggregates only.

**Track I · The guide.**
- Goal: the pages of the acceptance criteria, and the library's `README.md` brought to M2.
- Owns: `docs/guide/README.md` and the new pages under `docs/guide/`;
  `packages/t2-agentic-voice/README.md`.
- May read: the design's 3, 4, 10, 11 and 14; every track's signatures; the generated settings
  reference.
- Tests: `poe docs`; each code sample compared with its source file by review (TD-024).

**Reviewers, by concern.** Each reviews every track for its concern; each finding is checked by an
agent told to refute it before it is acted on.
- **Security:** invariants 1, 5, 7 and 8; data-channel input parsed strictly (the browser is not
  trusted, SECURITY.md's trust boundaries); the offer secret, the TURN secret, the join keys and the
  access code; CORS; the token route; recordings gated by the setting and the token; Phoenix never
  public; no `.env` read; FastAPI's telemetry off.
- **Harness:** layers, owners, ARCH-BAN, facades, `[[restricted]]`, sizes, the coverage floor, the
  generated docs' freshness, test isolation (GP-15), LF endings, CLAUDE.md's cap.
- **Faithfulness:** each port beside its prototype source (`tts.py`, `speakable.py`, `fillers.py`,
  `capture.py`); the bridges against Pipecat's source as step 4 read it; the protocol against the
  design's 5.5; the request baseline.
- **Measurement:** the runs follow this registration; the arithmetic; each scorecard's totals
  recomputed from its rows; the one-speaker label.

## The measurement, registered before any result

Written on 2026-11-02, before any run. Amendments are dated and made before the result they
affect; every open question below is settled, in the owner's words and dated, before the step it
gates. Facts are cited with their source; the agent's proposals and expectations are marked as such.

**E · End of turn on the golden set (offline, no spend)**

- **Data.** The 10 paused-request items, 39 variants, each with one true turn end the owner marked on
  its waveform (`turn_ends_ms`, plan 002's recorder): dev 6 items, 23 variants (`n20` to `n23`,
  `n26`, `n28`: Saudi 3 items, MSA 1, English 1, mixed 1); held-out 4 items, 16 variants, run once at
  the close for aggregates only. A secondary set with no label: every other dev variant with speech
  (requests, short requests, stop words, repeat requests, listening sounds, confirmations, ticket
  numbers), where the end of the last speech Silero finds in the clip stands for the true end (the
  agent's proxy, reported apart).
- **Arm E1.** The file-fed pipeline with the turn settings of the decision log, a fake speech-to-text
  that answers at once (so the transcript adds no time: Whisper is timed in T), at real-time pace, so
  Pipecat's timers run as in a call. E2 is the same run again.
- **Metrics, per variant:** a **cut-off** when the first turn end falls more than 300 ms before the
  labelled end (the agent's tolerance for a mark clicked on a waveform); a **miss** when no turn end
  comes within 4 s after it; the **end-of-turn delay**, from the labelled end to the turn end, for the
  rest; and its parts, the **VAD stop delay** (to Silero's stop) and **Smart Turn's decision** (from
  that stop to the turn end). Reported: cut-offs and misses by variant and by item; the delay's median
  and 90th percentile (Hyndman and Fan's type 7, as plan 002); by language and by device.
- **The reference answerer** returns each labelled end as the turn end: 0 cut-offs, 0 ms, inside
  `poe check`.
- **The noise:** decisions that differ between E1 and E2, counted; the agent expects few or none
  (the same frames, the same models), with timing near a threshold the possible source.
- **Rule:** no default moves in M2 (Q14). E1 is the baseline M3 tunes against.
- **Expected (the agent's):** some cut-offs on the Arabic paused requests: the owner's pauses run
  about 0.83 s (`Ole5-chatbot/VOICE_LOG.md`, line 51, the prototype's D43), far past the 200 ms VAD
  stop, so each pause reaches Smart Turn, whose v3.2 benchmark gives Arabic 89.76% (6.97% false
  positives) against English 94.26% (3.75%)
  (huggingface.co/pipecat-ai/smart-turn-v3/raw/main/benchmarks/smart-turn-v3.2-cpu.md, read
  2026-11-02 by the research step; its Arabic dialect, and what its false positive means, are
  UNVERIFIED). Delays near 200 ms plus Smart Turn's inference when it says the turn is complete, and
  up to 3 s when it says it is not.
- **Cost and time:** none in money; about 4 minutes for the paused requests at real-time pace (the
  agent's estimate from their lengths), and about 10 for the secondary set.

**T · The time of each step on the golden set (spends)**

- **Data.** The 23 dev paused-request variants: 19 for the Arabic model (Saudi 11, MSA 4, mixed 4)
  and 4 for the English one.
- **Arm T1.** The echo on the file-fed pipeline at real-time pace with the real `GroqSTT`
  (`whisper-large-v3`, the item's label as the session's language, as `stt.live_language = "session"`
  sends it) and `GroqTTS` (Q5's voices), the frame cached before the run (its requests counted), trim
  off, untraced. T2 is the same run again, on the same commit.
- **Metrics, per variant, in ms:** the VAD stop delay; Smart Turn's decision; Whisper's request
  (sent to answered); the echo's text ready; Orpheus's first byte (sent to the first audio byte); its
  leading silence (to the first sample above the noise floor); the time to first audio (the labelled
  end to the cached frame's first frame) and to the heard words (the labelled end to Orpheus's first
  sound). Also: requests, billed seconds and characters per model. Medians and 90th percentiles by
  step and language; the median's change between T1 and T2 is the timing's noise. No keep rule: these
  numbers feed M3's and M4's targets (the design's 10.3).
- **Expected (the agent's):** Whisper near M1's medians of 271 to 396 ms (plan 002's R1 to R4), the
  process's first request slower without the lifespan's warm-up (run P's 1,258 ms, TD-012); Orpheus's
  first byte near the prototype's 249 ms (Arabic) and 262 ms (English) with connections kept open (the
  research step's count over five prototype logs in `voice-lab/`); a leading silence of 0.4 to 0.7 s
  (`Ole5-chatbot/VOICE_LOG.md`, line 34, the prototype's D25).
- **Cost:** per run, Whisper 24 requests at the 10 s minimum = 240 s = 0.067 h × $0.111 = $0.0074;
  Orpheus Arabic about 19 × 55 characters plus the frame ≈ 1,100 characters × $40 per million =
  $0.044; English about 4 × 60 = 240 × $22 per million = $0.005 (prices:
  console.groq.com/docs/model/canopylabs/orpheus-arabic-saudi and .../orpheus-v1-english, read
  2026-11-02 by the research step). About $0.06 a run, $0.12 for both. Orpheus requests: 20 Arabic
  (the smoke's included) and 4 English per run, and one per language for the frame the first time,
  inside the published 10 a minute and 100 a day per model
  (console.groq.com/docs/rate-limits, read 2026-11-02 by the research step) only if the day's calls
  leave room (Q17).

**L · The live language, and the noise on another day (spends)**

- **Arms.** A1 as plan 002 registered it (`whisper-large-v3`, the item's label as the language, no
  prompt, temperature 0, `verbose_json`, `--timeout-s 6`); A3, the same with `--language-hint auto`,
  so no language is sent.
- **Runs,** on the dev split (66 items, 231 variants), at one measurement commit, on a day other than
  2026-11-01: R5 (A1), R7 (A3), R6 (A1), in that order, so drift over the session falls on both arms.
  R5 against R6 is the noise on another day (TD-032); R7 against R5 is the comparison, and R7 against
  R6 its replication. The runner's settings are plan 002's as amended (`--max-attempts 4`,
  `--variant-timeout-s 120`, `--max-rpm 10` until Q17, `--price-per-hour 0.111`, `--cap-usd` from
  step 23), each on the command line.
- **The noise first:** if R5 and R6 differ by p < 0.05 (D-024's method), the runs are unreliable: this
  is said, the comparison is not read, and the larger noise is recorded (TD-032).
- **The rule for `stt.live_language`:** it stays `session` if A3 is worse beyond the noise in either
  comparison (p < 0.05, more items worse), or if it has more items worse than better in both. Any other
  outcome (A3 at least as good as A1 in either comparison) goes to the owner with its numbers, since a
  call that detects its language needs no language buttons (Q15). Its default moves in its own commit
  (GP-18). R7's smoke step reads the form of Groq's `language` (a code or a name, TD-011); if a name,
  the adapter maps it before any default moves.
- **Expected (the agent's):** A3 worse, most on mixed and short items: the prototype's auto-detection
  got 23 of 35 segments against 32 of 35 with a forced language and its own hint
  (`Ole5-chatbot/VOICE_LOG.md`, line 33, the prototype's D24), and its `language` field was found
  unreliable (line 172). R5 and R6 identical or nearly so (D-024: d = 0 on 2026-11-01).
- **Cost:** three dev runs of large-v3 at about $0.075 each (R1's history line) plus their smokes:
  about $0.23; at 10 requests a minute, about 23 minutes a run.

**C · The owner's calls (spends)**

- **The calls,** from the call script the owner approves (Q18): the agent's proposal is eight calls of
  at least three minutes and about ten turns each: local, on the laptop's speakers, the wired headset
  and a Bluetooth headset; deployed, from the phone hotspot on the speakers and on the headset, and
  from the network that blocks UDP on the speakers and on the headset; plus one deployed call on the
  speakers in Edge. The turns, in the owner's own words: requests that pause mid-sentence, one-clause
  requests with product terms, a number and a ticket number, English sentences, listening sounds, and
  the Stop button and Esc during the echo.
- **Metrics, per call:** per Groq model, the requests and the requests per call minute, the audio
  seconds sent and billed per minute, the TTS characters per minute; per turn, the server's time to
  first audio and, from `client_stats`, when it played (their difference is the network to the
  browser); the candidate type and the time to connect; whether the owner heard the turn back (after
  each call, the owner names any turn that did not come back, and the agent checks it against the
  call's trace and timeline). Reported per call and as medians over the calls.
- **Recorded:** the requests per call minute per model, beside the key's real limits (Q17), as a
  decision entry for M6.
- **Cost (the agent's estimate):** a turn every 10 s or so is about 6 Whisper requests a minute, each
  billed 10 s, so 60 billed seconds a minute ≈ $0.0019, and 6 Orpheus requests of about 60 characters
  ≈ $0.014 a minute in Arabic; eight calls of three minutes ≈ $0.40. **The limit, not the money,
  binds:** at the published 100 requests a day per Orpheus model, about 6 requests a minute leave
  roughly 16 call minutes of Arabic a day, less any T run's 20, so the calls span two or three days
  unless Groq raises the limits (Q17).

**The budget** (the agent's arithmetic): L $0.23, T $0.12, C about $0.40, the first local calls about
$0.05, and Q16's prompt arm $0.075 if it runs in M2: about $0.90 in all. Whether a refused request is
billed is UNVERIFIED (TD-021), and retries add requests.

**Open questions, each settled before the step it gates**

The owner's call before Block 0:

- **Q1. The dependencies and their licences.** May the agent download and install "Dependencies to
  install" (several hundred megabytes in all, the agent's estimate, UNVERIFIED), and accept the
  copyleft licences that come with them, each used unmodified, as certifi's MPL-2.0 was (plan 002,
  Q1)? They are: soxr (LGPL-2.1-or-later), soundfile's bundled libsndfile (LGPL-2.1), the FFmpeg that
  OpenCV's wheels bundle (LGPLv2.1), tqdm (MPL-2.0 and MIT), and the FFmpeg inside PyAV's wheels,
  likely GPL since x264 and x265 are built in (UNVERIFIED). Why: D-016 asks the owner's approval for a
  copyleft licence, and the design's 13 list did not name these. Options: (a) accept them all, used
  unmodified; aiortc needs PyAV, so there is no WebRTC in the backend without it; (b) accept all but
  PyAV's wheel and build PyAV from source against an LGPL FFmpeg, which needs a compiler and FFmpeg's
  development files on Windows and in the image, a large cost; (c) review each one. **The agent
  recommends (a):** the library never ships these binaries itself, each team installs them from
  PyPI, and the use is inside T2; if an image holding them is ever given outside T2, ask T2's legal
  team first. The agent is not giving legal advice.
- **Q2. The library's logging, and who owns loguru.** The approved design and the roadmap disagree.
  The design's 10.2 and 12.2 (change 3) have `voice` own loguru, switch Pipecat's namespace off with
  `logger.disable("pipecat")` by default, add or remove no sink, and have the library log through the
  standard library to `t2_agentic_voice` with a `NullHandler`, never touching the root logger. The
  roadmap's M2 bullet, D-002 and ARCHITECTURE.md's conventions have `core` own loguru and
  `configure_logging` remove loguru's default sink and forward its records; and today `get_logger`
  prints to standard output through structlog unless an app configures it, and `configure_logging`
  adds a bridge on the root logger. Why the owner: both were approved. Options: (a) the design: `voice` owns loguru, off by default, `forward`
  sending Pipecat's WARNING and above to `t2_agentic_voice.pipecat`; the library's own logs go to
  standard-library loggers with a `NullHandler`, `get_logger` keeping its structured call shape;
  `configure_logging` stays a helper an app calls (the Ole5 app does), so nothing prints until an app
  configures logging; D-002's bullet, the roadmap's M2 bullet, ARCHITECTURE.md and GP-03's last clause
  change with a decision entry; (b) the roadmap: `core` owns loguru and removes its default sink, a
  change to a process-wide logger a team's own code may use, and the library keeps printing by
  default; (c) (a) for loguru only, the library's own logging unchanged now and a debt row. **The
  agent recommends (a):** a teammate's process keeps its own logging and its own loguru sinks, which
  the design's personas say would otherwise end an evaluation, and invariant 8's test holds either
  way.
- **Q3. The echo's shape.** The design names "the voice session in echo mode" and `examples/minimal`
  "as an echo use case" (its 16.1), but not their public form, which is a design choice. Options:
  (a) `VoiceAgent(name, languages=[Language.saudi_arabic(greeting=...), ...])` built in M2 with only
  these fields, and a setting `session.mode`, with `echo` its only value in M2; M4 adds `talker`, and
  the talker's fields arrive as optional arguments, so echo stays a teammate's first audio check;
  (b) a runtime argument, `VoiceRuntime(agent, echo=True)`, which M4 would have to deprecate; (c) an
  internal stand-in with no public form, removed in M4, which leaves `examples/minimal` nothing to
  show. And its words: (i) a frame before the heard words, «سمعتك تقول: …» and "I heard: …", or
  (ii) the words alone. **The agent recommends (a) and (i):** the frame says the words are the
  caller's, so the echo never sounds like the agent answering or claiming an action (invariant 2),
  and as a cached phrase it plays at once.
- **Q4. Who reaches the deployed echo, and how the owner's calls get a join token before open
  question 19 is answered.** `DevIdentity` serves only `dev` on loopback, and the recording consent
  must ride in a signed token (invariant 8). Options: (a) the Ole5 app's own token route mints a
  `SignedJoinTokens` token only for a caller who types an access code the owner sets (a secret
  setting, compared in constant time, repeated tries slowed), so only the owner calls, from any
  network; (b) wait for open question 19, so the deployment waits on the website team; (c) a token
  minted on the laptop and pasted into the page, which lives at most 120 s (the design's 6.5), too
  short to carry to a phone; (d) open to anyone, set aside: Groq spend and limits, and no identity at
  all. **The agent recommends (a)**, replaced by 19's answer when it comes (Q12).
- **Q5. The voices and the register.** Which Saudi voice: `abdullah` (the default since 18 April,
  the prototype's pick), `fahad`, `sultan` (male), `lulwa`, `noura`, `aisha` (female); which English
  voice: `troy` (the prototype's pick), `austin`, `daniel` (male), `autumn`, `diana`, `hannah`
  (female) (Groq's model pages, read 2026-11-02 by the research step). Samples of `abdullah`, `fahad`,
  `sultan`, `noura`, `troy`, `austin`, `autumn` and `daniel` are in `voice-lab/voices/`, so no new
  request is needed to listen. And the register of M2's fixed phrases (the greeting, the frame, the
  notices): (a) Saudi dialect; (b) plain MSA. Why: the voices are the library's documented defaults
  and Ole5's settings (the design's 3.3, "chosen in M2"), and only the owner can judge them. **The
  agent recommends `abdullah` and `troy`, as library defaults and for Ole5, and (a)**, the talker's
  register being M4's with its prompts. Needed before Block 0 writes the defaults; it can wait until
  the first live call if the owner wants to listen first.
- **Q6. The word "stop" in the library's source.** The design names the protocol's `stop` message and
  the client's `call.stop()` (its 4.5 and 5.5), and the golden set has "stop" as a stop-word item;
  `test_no_item_in_source.py` fails on it in any string or JS file under `packages/`, unless
  `allowed_in_source.toml` lists it, which only the owner's ruling adds. Options: (a) one entry,
  "stop", for the protocol's message and method names, which no model or caller hears; (b) rename
  them (a `halt` message and `call.halt()`), so the list stays empty, the protocol departing from the
  design's names. **The agent recommends (a)**, noting that it also lets "stop" into M3's stop-word
  presets unflagged, so M3's plan rules on those presets explicitly.

The owner's call before the deployment (and, for Q7, before the first recorded call):

- **Q7. The consent screen, and keeping the recordings.** The widget shows a consent screen before
  the microphone opens and passes its version and the recording choice to the token (the design's
  3.2). Options for the wording: (a) the agent drafts it in Arabic and English for the owner's own
  test calls, version `m2-owner-test-1`, with a separate box for recording, and the owner approves or
  rewrites it, in the owner's words as plan 002's consent was; the wording customers see comes from
  T2 before any customer uses the widget; (b) the owner or T2 writes the customer wording now. For
  the recordings: (i) copied from the host to the owner's machine under `var/` after each session,
  then deleted on the host, and kept until the owner deletes them, as the golden set's audio is;
  (ii) kept on the host's `var_dir`. **The agent recommends (a) and (i):** call content stays on the
  owner's machine, as invariant 8 and the golden set have it.
- **Q8. The host.** Where the backend and Phoenix run, and its facts: the host and its operating
  system; the backend's domain name; the reverse proxy that ends TLS (nginx, Caddy, Traefik or
  another); Docker or not; its public IP address and which ports can be opened; whether its outbound
  traffic must go through a proxy (TD-004); who runs commands on it (the agent never logs in). **The
  agent recommends:** one container for the backend with `var_dir` on a volume, and Phoenix as a
  second container bound to 127.0.0.1 with auth on and a persistent volume, viewed through an SSH
  tunnel, never public (the design's 11, SECURITY.md's trust boundaries).
- **Q9. The media path for the network test.** aiortc's ports cannot be pinned and it offers no TCP
  candidates (the decision log), so a caller on a network that blocks UDP needs TURN over TLS on 443.
  Options: (a) coturn on the owner's host as a small service, TURN over TLS on 443 through its own
  hostname and IP address, or through SNI routing at the reverse proxy (a proxy that passes TLS on by
  name without ending it), relaying to the backend on the same host (UNVERIFIED for aiortc: the
  design's 11), with per-call credentials from a shared secret; free; (b) a hosted TURN service, such
  as Cloudflare's Realtime TURN (TLS on 443; 1,000 GB free, then $0.05 a GB; IPv4 only, no TCP
  relaying, no relay to private addresses, so the backend must still take UDP from it, or allocate a
  relay itself, which is UNVERIFIED; developers.cloudflare.com/realtime/turn/, read 2026-11-02 by the
  research step): a new outside service that relays the call's encrypted media, and a new key;
  (c) UDP ports opened on the backend alone: the whole ephemeral range, or a container with a narrowed
  range (Pipecat's Docker example, UNVERIFIED behind Docker's address translation), which cannot pass
  the roadmap's test from a network that blocks UDP. **The agent recommends (a)** if the host can give
  coturn port 443 on a second address or through SNI routing, otherwise (b). Cost does not decide:
  about 0.4 MB a call minute each way (the research step's estimate, UNVERIFIED) is a fraction of a
  cent on any of them.
- **Q10. The website embed.** Which page, who embeds it, and whether customers can see it during M2.
  Options: (a) a test page on the website, not linked from it, holding an iframe of the backend's
  widget page (`allow="microphone"`), so the website team adds one tag and CORS stays off; (b) the
  same page loading the widget's script, with the website's origin in `server.allowed_origins`;
  (c) the website's staging site; (d) the backend's own page only, which leaves "the widget embedded in
  the website" unmet (a `Deviation:` line). **The agent recommends (a)**, behind Q4's access code.
- **Q11. The network that blocks UDP.** Options: (a) a real network known to block UDP (T2's office
  or guest network, if it does); (b) the laptop's own firewall blocking outbound UDP, except DNS,
  while on the phone hotspot: a rule the owner adds and removes, since it changes the owner's security
  settings, with the commands from the agent; (c) both. **The agent recommends (c)** if such a network
  exists, otherwise (b).
- **Q12. Open question 19 at the deployment.** If the website team has answered: a login means the
  website's server mints the token (`SignedJoinTokens`, the claims in `serving.md`), website work for
  M4 or M5, with nothing more in M2; a one-time email code means `Authenticate` is built in M2 with an
  email-sending dependency of the app, a new outside service. If there is no answer by the deployment:
  (a) deploy with Q4's access code and carry 19 to M5, where ticket status first needs a verified
  identity (invariant 3); (b) hold the deployment until the answer. **The agent recommends (a)** when
  there is no answer.

The owner's call before the measurement runs:

- **Q13. The budget cap** for M2's paid runs and calls together, against the estimate of about $0.90
  ("The budget"). **The agent recommends $5**, as for M1.
- **Q14. The turn defaults.** Six dev items is D-024's floor (c = 6), so a tuned default could move
  only if all six paused requests improved. Options: (a) measure only in M2 (E1 is the baseline), and
  tune in M3 after more paused requests are recorded; (b) the owner records more paused requests now
  (say 20 more lines, about an hour on the three devices), then M2 tunes on dev; (c) tune on the six
  now. **The agent recommends (a).**
- **Q15. The language a live call sends Whisper, when the rule does not decide.** If A3 is not worse
  (the rule above): (a) auto-detect for live calls, and the widget's language buttons kept only as a
  preference; (b) the session's language anyway; (c) the prototype's double transcription, each clip
  sent as Arabic and as English (its D24), twice the requests at the 10 s minimum each, against 20
  Whisper requests a minute. **The agent recommends (a) in that case,** and (b) otherwise, as the rule
  already gives.
- **Q16. The prompt arm for product terms: in M2 or in M4.** Term recall was 0.333 for large-v3 on dev
  (plan 002's Future improvements). In M2 it costs one dev run (about $0.075) plus a `--prompt` flag
  in `poe eval` and TD-019's split, and it would change no default in M2, since the vocabulary that
  becomes the prompt is declared with the agent (the design's 3.1 and 3.3). **The agent recommends
  M4**, where the vocabulary lands and the result is used.
- **Q17. The key.** Its real limits from the console (console.groq.com/settings/limits), and whether
  Groq has been asked to raise Orpheus's 100 a day (the owner's answer to the design's question 21);
  whether anything else uses the key during M2's runs and calls; and Ole5's share of it (D-018,
  question 11), which M6's limiter enforces. **The agent recommends** pacing Whisper runs at half the
  key's per-minute limit while anything else might use it, as in M1, and holding the call days of C
  apart from T's day while the published limits hold.
- **Q18. The call script.** The calls of "C" above, or fewer or more; with or without the Bluetooth
  headset. **The agent recommends the script as proposed**, the Bluetooth call included, so that M3
  has its recordings for the Bluetooth warning.

Every question above gates the run as well as its own step, so each is also the owner's call before
the run it touches.

## What the owner does

1. **Before Block 0:** answer Q1 to Q6 (Q5 may wait until the first live call).
2. **In Groq's console, before the first live call:** accept the terms of `canopylabs/orpheus-arabic-saudi`
   and `canopylabs/orpheus-v1-english` as the organisation's admin (the design's 3.2; the Arabic model
   refuses a request until its terms are accepted, as a third party quotes Groq's error); read the
   key's real limits at console.groq.com/settings/limits and give them to the agent; if they are as
   published, ask Groq to raise them (the design's question 21); a spend limit in the console is the
   owner's choice. The key itself stays where M1 put it (`.env` in the main checkout, or its file).
3. **The first local calls** (step 18): from the main checkout, start the Ole5 app's dev server with
   the command the agent gives, open the address it prints in Chrome on this laptop, allow the
   microphone, and say a few lines on the laptop's speakers, then on the wired headset; say whether
   each turn came back.
4. **The host, before the deployment:** answer Q7 to Q12. Then, with the agent's deployment steps:
   the backend's domain name in DNS and its certificate at the reverse proxy; the firewall rules Q9
   needs (for coturn: TCP 443 on its own address or through SNI routing, 3478 over UDP and TCP, and its
   relay range of UDP ports, narrowed in its configuration); the secrets as files on the host, never in
   the image or the repository: the Groq key, the join key, the TURN secret and the access code; then
   the commands that start the backend, Phoenix and coturn. The agent never logs into the host.
5. **Phoenix on the host:** set its admin password on the first login; view it through an SSH tunnel
   (`ssh -L 6006:127.0.0.1:6006 <host>`), never on a public port, since it holds call content
   (SECURITY.md, trust boundaries).
6. **The website embed:** send the website team the snippet and the backend's address from
   `browser-client.md` for the page Q10 chose, and tell the agent when it is live.
7. **The calls** (step 21 and run C): with Q18's script, on each device and network; for the network
   that blocks UDP by the laptop's firewall (Q11), add the rule with the agent's commands before the
   call and remove it after. Use the access code on the page; tick the recording box only for the
   calls of C.
8. **After each recorded session:** copy the recordings from the host to `var/` on this laptop with
   the agent's command, then delete them on the host (Q7).
9. **Before the measurement runs:** answer Q13 to Q18; nothing else uses the key while a run goes.
