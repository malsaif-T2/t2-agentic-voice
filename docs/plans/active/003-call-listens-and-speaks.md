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
  WAV's header, flags a take that came back cut short, keeps each response's
  `x-ratelimit-remaining-requests` and `x-ratelimit-remaining-tokens` for the call's usage, and
  raises `ProviderError` for every failure, a model whose terms are not accepted named with its
  FIX. Its tests, against a fake transport, check the request's fields against Block 0's baseline,
  a cancel that stops within 50 ms and leaves no task or connection, each failure kind, that the
  key appears in no repr, error or log line, and that `GROQ_*` variables change nothing in the
  request (the design's 7.3).
- [ ] No public signature names a type from `pipecat`, `aiortc`, `onnxruntime` or `groq` (the
  design's 5.3, a test over every public module).
- [ ] The fixed phrases declared at lifespan start (the greeting, the echo's frame, the notices)
  are synthesized once and cached under `var_dir`, keyed by a hash of text, model and voice (the
  design's 10.4); a cache hit sends no request. In M2 no text built from heard words reaches the
  cache: after an echo turn the cache folder holds no new file and the cache was never asked for
  the heard text (a test; invariant 8).
- [ ] `t2_agentic_voice.languages` exports `speak_number` and `speak_id` in Arabic and English
  (numbers through num2words behind a `domain` function, IDs digit by digit from the library's own
  table), the clause splitter, which keeps every clause under the model's `max_chars`, and the
  pronunciation map; Ole5's entries ("Ole5" said «أُولِي فايف» and "Oh-lee five",
  `Ole5-chatbot/VOICE_LOG.md`, lines 35 and 45, the prototype's D26 and D37) are the app's data.
- [ ] `voice` runs one Pipecat pipeline per call: SmallWebRTC, Silero VAD and Smart Turn v3.2 on
  CPU with no torch, a speech-to-text bridge on Pipecat's STT base class that sends Whisper one
  request per user turn (the decision log; Block 0's read and spike confirm it can), Smart Turn's
  stop strategy with `wait_for_transcript` off so that a turn's end is the analyzer's alone, a
  text-to-speech bridge on `TTSService` with `TextAggregationMode.TOKEN`, and a session bridge that
  is a plain `FrameProcessor`. Pipecat's interruptions are off, and none of its LLM services,
  context aggregators or function calls is used (the design's 13). The session's modules import no
  Pipecat (ARCH-BAN).
- [ ] The voice session in echo mode says back each turn in the voice of its language (one voice
  per reply): the cached frame (Q3) plays once the turn's transcript is in, while Orpheus
  synthesizes the heard words; an empty transcript is said back as nothing and kept on the
  timeline. Speech that starts while the echo plays, or within 300 ms after it, is not said back
  (a test), so the agent never echoes its own voice. The Stop button, Esc and `hangup` act at once:
  after a `stop`, no audio frame of that turn is sent (a test with a capturing output), and the
  session listens again.
- [ ] `HeardWords` is in `[[restricted]]`, built only in `voice`, from the commit that creates it
  ([SECURITY.md](../../SECURITY.md), invariant 1).
- [ ] Invariant 8: Pipecat's loguru output is off by default (Q2), switched off before `voice`
  first imports Pipecat, so its import banner never prints: in a child process,
  `import t2_agentic_voice` and `t2v --help` write nothing to stderr. A test, in a child process
  with loguru's default sink in place, shows that a Pipecat DEBUG line holding a transcript
  reaches no output. Pipecat's error frames and its transport and ICE failures become library log
  lines with no call content, and `TransportFailed` or `ProviderFailed` events.
- [ ] One trace per turn, `session.id` set to the call ID, with the speech-to-text span and a
  text-to-speech span (characters, chunks, requests, time to first audio, cache hits) and the
  resource attributes of the design's 10.1, whose settings digest leaves out every secret and its
  `_file` path (a test: changing a secret leaves the digest unchanged). A test finds no Groq key,
  join token, offer secret, TURN secret or password, or access code in any exported span, and no
  audio.
- [ ] Each call's `CallReport` holds its usage per Groq model (requests, audio seconds sent and
  billed, TTS characters, cache hits, the last remaining requests and tokens Groq reported) and its
  requests per call minute. Its numbers, with no heard or spoken text, also go on the call's root
  span and into a JSON file per call under `var_dir/reports/` (a test that the file holds no text
  of the call). `t2_agentic_voice.events` exports the events M2 emits (provisional, the design's
  6.6).

**Call set-up** (the library)

- [ ] `t2_agentic_voice.identity.SignedJoinTokens` mints and verifies compact JWTs, HS256 only,
  with the claims, the key map and the lifetime of the design's 6.5, single use through
  `t2_agentic_voice.stores.SqliteUsedTokens`. Every join key is at least 32 bytes (RFC 7518's
  3.2 for HS256: rfc-editor.org/rfc/rfc7518#section-3.2, read 2026-11-02 by the security review),
  and the claims are parsed strictly (`consent.record_audio` a JSON boolean, the consent version a
  bounded string). `DevIdentity` serves only `env=dev` and loopback clients, refuses any other
  `env` before it reads the client's address, and always returns
  `Consent(version=None, record_audio=False)`. Adversarial tests (invariant 7): a token used twice,
  expired, issued in the future beyond the skew, signed with another key, with an unknown `kid`,
  with `alg` none or any algorithm but HS256, with a changed claim, with no `jti`, with a lifetime
  over 120 s, with a consent version other than `privacy.consent_version`, and with `record_audio`
  given as "true", "false", 1 or null; each is refused at `/join` in the one error shape, echoing
  no value (GP-19). A key under 32 bytes is refused at settings load and at verify.
- [ ] The router serves `POST /join`, `POST` and `PATCH /offer` (both needing the call's offer
  secret, carried in a request header or the JSON body, never in a URL), `GET /health` (only what
  the design's 10.5 lists, no path), `GET /ready`, `GET /client/1/t2v-client.js`, and `GET /dev`
  only with `env=dev` and only to loopback clients. A second offer gets 409; a client's `pc_id`
  never reaches Pipecat's request handler; the secret stops working when ICE completes or the call
  ends, and a PATCH after ICE completed gets a quiet 409, logged at DEBUG with no value, which the
  client ignores once connected. Adversarial tests cover an offer with no secret, with another
  call's secret, with the secret in the query string, a second offer, and a PATCH after ICE
  completed and after the call ended (the design's 5.5). Every route answers "runtime not started"
  when the lifespan never ran.
- [ ] With `serve()`, CORS answers only `server.allowed_origins`, with POST and PATCH listed; in
  the mount, the app's own CORS middleware answers and the router says so at startup (the design's
  5.5), as the Ole5 app's server does. FastAPI's own telemetry is off in both shapes: `serve()`
  builds its app with `telemetry` tracing, metrics and logs off and `auto_configure` false, and the
  Ole5 app's server builds its own app the same way, since in the mount `router()` cannot reach the
  app's object. A test in a child process, with a global tracer, meter and logger provider and
  `FASTAPI_OTEL_AUTO_CONFIGURE=true`, finds no span, metric or log record from FastAPI in either
  shape (D-023). `serve()` and the Ole5 app's server run uvicorn trusting proxy headers only from
  `server.forwarded_allow_ips` (`*` refused); `t2v dev` binds 127.0.0.1 with proxy headers off; a
  test shows that an `X-Forwarded-For` from an untrusted peer is ignored.
- [ ] `VoiceRuntime`'s lifespan takes an exclusive lock file under `var_dir` (a second process is
  refused with a FIX line, on Windows and on Linux), warms VAD, Smart Turn and the adapters without
  a request (TD-012), builds tracing inside the lifespan (TD-014), and closes every adapter.
  `router()` and `serve()` refuse `env=test` and a runtime with no identity source.
- [ ] `t2v serve`, `t2v dev`, `t2v doctor` (the key and the model list, with no synthesis; the
  ONNX files' SHA-256; the clock's skew; and, only with `--synthesize`, one short request per
  language that checks its voice and terms, counted in the budget, since Groq documents no other
  way to learn whether terms are accepted) and `t2v settings show --redacted` run, and `--help`
  only prints help, importing no Pipecat (GP-17).

**The browser**

- [ ] `api/static/t2v-client.js` (one ES module, no dependency, no build step) and
  `api/static/dev.html` speak `t2v/1`: every message carries `"v": 1` and comes from a closed list
  that the server parses strictly (invariant 4, GP-06), none named like Pipecat's reserved
  `signalling` messages or starting with "ping". The client sends the end-of-candidates PATCH, and
  `client_stats` (the selected candidate type and, for a relay, its `relayProtocol` and the TURN
  URL's port; the time to connect; whether `echoCancellation` applied; when the first audio
  played). Captions and notices are inserted as text only (`textContent`): a test reads the
  client's, the dev page's and the widget's scripts and finds no `innerHTML`, `outerHTML`,
  `insertAdjacentHTML` or `document.write`.
- [ ] Ole5's widget in `apps/ole5-voice-agent/web/`: a consent screen before the microphone opens
  (Q7's wording and version), start and end, playback, captions, the Stop button and Esc, and a
  message for a microphone that is missing, busy or refused. Its page is served with a
  Content-Security-Policy (`script-src 'self'` with no inline script, and `frame-ancestors` only the
  website's origin, from an `OLE5_VOICE_` setting), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` and `Permissions-Policy: microphone=(self)`, and `/dev` with
  `frame-ancestors 'none'`, each header tested. Checked in Chrome and in Edge, both supported
  (D-018, the design's open question 12): the agent checks in its browser pane what needs no
  microphone (the page, the consent screen, the missing-microphone and refused messages, the data
  channel), and the owner checks the microphone, playback, Stop and Esc in both browsers in
  step 18, each result in the progress log.
- [ ] `.claude/launch.json` starts `t2v dev` on `examples/minimal` and the Ole5 app's dev server
  ([WORKING-RULES.md](../../../WORKING-RULES.md), "Seeing it run").

**The deployment**

*Amended 2026-11-02 ("The owner's decisions"): all hosting is on this machine for now, and Phoenix
is M1's, on 127.0.0.1 with no authentication. These criteria, steps 19 to 22, Q9 to Q12 and Q7's
host parts are re-planned for this machine before step 19, as a dated amendment the owner approves;
until then they stand as drafted.*

- [ ] The Ole5 app runs on the owner's host behind HTTPS (Q8): `env=staging`, one worker,
  `var_dir` on a persistent volume, its image built from `git archive` of the merged commit with an
  allow-list `.dockerignore` (a test that it lets in no `.env*`, `var/`, `.claude/` or `*.wav`).
  Publicly open are only 443/tcp and the TURN ports Q9 keeps; the backend's HTTP port and Phoenix
  sit on 127.0.0.1 or the compose network only, checked from the phone hotspot (step 20). Phoenix
  runs beside it with auth on, its retention set by Q7, and never public; the backend sends
  Phoenix's system API key from a host file (`tracing.api_key_file`), so a deployed call's turn
  traces arrive there, and an exporter refusal (401) is counted and logged with no content. The
  widget is embedded in the website (Q10).
- [ ] The owner held a call from another network (a phone hotspot) and one from a network that
  blocks UDP (Q11), and heard each turn back; each call's `client_stats` shows its candidate type,
  and the call from the network that blocks UDP a relay over TLS on 443.
- [ ] Before M2 closes, the media path is recorded as a decision entry with the network test's
  outcome: UDP ports opened on the backend, a TURN service run as a small service, or another
  transport (Q9).
- [ ] If TURN is used, `/join` returns per-call TURN credentials minted from the shared secret
  (coturn's REST scheme), the username `<expiry>:<call ID>` holding no claim of the token, valid
  for `server.turn_ttl_s` (3600 by default, refused above 86400); the TURN secret, at least 32
  bytes, is a `SecretStr` that reaches no log, trace, event or error, and so is each per-call
  password. coturn runs as step 19 configures it, and step 20 shows that a minted credential
  reaches no loopback, private or metadata address and gets no TCP relay.
- [ ] The guard on the shared Groq key that Q4 settles is in place before the first deployed call.

**The recordings**

- [ ] The owner's calls through the widget are recorded with `privacy.record_audio` on and the
  recording consent in the signed join token: per call, the caller's track, the agent's audio and
  the playback timeline, under `var_dir`. Only a consent from a verified signed token counts.
  Adversarial tests: nothing is written with the setting off, with the token's consent false, with
  both, or under `DevIdentity` with the setting on, and no client message turns it on
  (invariant 8). No audio is in git; each recorded call's manifest (its consent, each file's
  SHA-256 and length) is committed for M3.

**The library line**

- [ ] `VoiceSettings` as the design's 7: `env` required (`dev`, `test`, `staging` or `prod`); the
  environment read only inside `from_env(prefix=, env_file=, unknown=)`, with no singleton and no
  `.env` unless one is passed; an unknown key under the prefix an error; a `*_FILE` form for every
  secret, each key and secret held to its minimum length; the groups `tts`, `turns`, `session`,
  `server`, `join`, `privacy`, `logging`, `tracing` and `storage`, and the
  `limits` keys Q4 brings forward; every check that holds in `prod` holds in `staging` too (a test
  per check). `docs/generated/settings.md` and `.env.example` are generated from it, each with a
  freshness test.
- [ ] `examples/minimal` is an echo agent (`make_runtime()`), and its tests need no key and no
  network.
- [ ] The package root holds the design's 5.1 names that M2 builds, on the base error
  `T2VoiceError` that the garbage-collection round brings (step 1); `identity`, `server`, `stores`
  and `events` are facades in `[package] public` and `facades`.
- [ ] ARCH-BAN runs in `poe arch` (the design's 12.4), with tests in `tests/harness/`. Inside
  `poe check`, while CI waits for a remote (TD-001): the torch check (no `torch` in `uv.lock`) and
  an import of every public module in a fresh subprocess (the design's 5.3 and 9.8).
- [ ] The guide's `README.md`, `is-this-for-you.md` (with the install's size measured),
  `quickstart.md` (the echo version), `serving.md`, `browser-client.md` (its M2 part),
  `tracing-and-logs.md` and `data-and-privacy.md` are written and linked from the
  [guide's index](../../guide/README.md), each code sample taken from a tested file.
- [ ] Decision entries record what the design's 16.3 lists for M2 (settings; serving and identity;
  GP-22 widened to an adapter object passed in code), the library's logging contract (the owner's
  answer of 2026-11-02) with Q2's loguru answer (amending D-002's loguru bullet), ARCH-BAN and the
  new facades, the echo's shape (Q3), how Whisper is cut, the settings keys beyond the design's 7.6
  (as Proposed), SECURITY.md's invariants 7 and 8 brought to the design's 8.1 (amending D-007), the
  media path, the measured requests per call minute and the language a live call sends Whisper.

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
  locally and from another network to the deployed backend, and one deployed call in Edge, each
  turn heard back.
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

1. The garbage-collection round ([plan 004](../completed/004-garbage-collection-1.md)) merged into
   the main branch on 2026-11-02 (750d90a), so Block 0 is cut from a main branch that holds its
   fixes: the base error is `T2VoiceError`, with `AppError` a deprecated alias (D-026); the library
   declares httpx, `scripts/harness_config.py` is split, and ARCH-DEPS refuses an import its project
   does not declare and DOC-SAMPLE a guide sample that is not its source's lines (D-027, Accepted
   2026-11-02); the library's logging is TD-033. This plan's text was brought up to date at that
   merge: no removed row is cited, the round's work is dropped from the steps below, and the rows it
   left for M2's plan are in the decision log. This plan's decision numbers start after D-027.
2. The owner settles Q1 to Q6 ("The measurement, registered before any result"). The agent lists
   `docs/plans/active/`, `docs/plans/completed/` and [decisions.md](../../design/decisions.md),
   and asks the other sessions, before it takes the decision and debt numbers Block 0 writes
   ([WORKING-RULES.md](../../../WORKING-RULES.md), "Commits and parallel sessions").

**Block 0 · dependencies, Pipecat read, harness, settings, interfaces** (one agent)

3. **Dependencies.** The two `uv add` commands of "Dependencies to install" (the library's and the
   Ole5 app's), with exactly their packages, as Q1 allows, then `uv lock`, in the same commit (CI
   runs `uv sync --locked`). Every package new to `uv.lock` is listed in the progress log with its
   version, the licence its installed metadata declares (`importlib.metadata`), and the licence
   files bundled in its wheel (each `*.dist-info/licenses/*` and `LICENSE*` file, and every
   `*.libs/` folder of shared libraries), since a declared licence does not cover a library bundled
   inside the wheel (soundfile's libsndfile and the FFmpeg in OpenCV's and PyAV's wheels are such
   libraries); with the protobuf move (below) and the installed size of the environment (for
   `is-this-for-you.md`). A licence outside that section's tables, or a bundled copyleft library Q1
   does not list, stops the block and goes to the owner. `uv run poe types`, and a
   `[[tool.mypy.overrides]]` entry only for a package that ships no types (whether pipecat-ai,
   num2words and loguru do is UNVERIFIED).
4. **The installed packages, read as text** (file and line for each finding, in the progress log):
   - every environment variable that Pipecat, aiortc, aioice, FastAPI, Starlette, uvicorn, loguru,
     onnxruntime and numba read, and which of them a value passed in code overrides (the design's
     7.3, as plan 002 read groq and OpenTelemetry), FastAPI's `FASTAPI_OTEL_AUTO_CONFIGURE` and the
     `OTEL_*` variables it reads among them; whether importing a Pipecat module calls
     python-dotenv's `load_dotenv` (`pipecat/__init__.py` does not:
     raw.githubusercontent.com/pipecat-ai/pipecat/v1.15.0/src/pipecat/__init__.py, read 2026-11-02;
     the other modules UNVERIFIED; if one does, `voice` never imports it, since the library reads no
     `.env` it was not given: the design's 7.2); `PIPECAT_SCTP_MAX_CHUNK_SIZE` is read at import
     (the research step's reading of `connection.py`, 2026-11-02); aiortc's default ICE servers
     (Google's STUN server when a peer is given none: `aiortc/rtcicetransport.py`, read 2026-11-02
     by the security review), which `tests/conftest.py` then blocks (step 6);
   - every Pipecat log line that holds call content or prints by default: the INFO banner
     `pipecat/__init__.py` logs at import (the same page), the TTS base class's DEBUG line with the
     text it speaks, the transport's remote ICE candidates, which hold IP addresses, and
     signalling messages, for invariant 8's tests;
   - how `SegmentedSTTService` cuts the audio (one request per VAD segment, its source at
     reference-server.pipecat.ai/en/latest/_modules/pipecat/services/stt_service.html, read
     2026-11-02) and how a bridge on the STT base class sends one request per user turn instead:
     which turn frames reach the bridge's place in the pipeline, and how
     `TurnAnalyzerUserTurnStopStrategy`'s `wait_for_transcript` (on by default:
     docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies.md, read
     2026-11-02) is turned off;
   - how the session bridge makes Pipecat drop queued output audio on a stop (the design's 13,
     **verify**); whether `VADProcessor`'s broadcast also travels upstream; `UserTurnProcessor`'s
     events and stop strategies without Pipecat's LLM aggregators; `SmallWebRTCRequestHandler`'s
     handling of `pc_id` and of a PATCH for an unknown one; the `TranscriptionFrame` fields
     (UNVERIFIED from the docs);
   - FastAPI's `telemetry=` argument (its keys `tracing`, `metrics`, `logs`, `operation_spans`,
     `exclude` and `auto_configure`: fastapi.tiangolo.com/advanced/opentelemetry/, read 2026-11-02
     by the reviews) and the attributes it would record (UNVERIFIED); uvicorn's
     `forwarded_allow_ips` and `proxy_headers` when passed in code; PyJWT's minimum key length
     option (`enforce_minimum_key_length` in its changelog, pyjwt.readthedocs.io/en/stable/changelog.html,
     read 2026-11-02 by the security review; UNVERIFIED for 2.15.1 until read).
5. **The spike, with no request to Groq.** In a scratch folder outside the repository, on the
   owner's Windows machine: a pipeline fed from a generated WAV (no golden file) through
   `VADProcessor` and `UserTurnProcessor` to a fake speech-to-text and a fake text-to-speech, and a
   SmallWebRTC answer to a local aiortc peer built with `RTCConfiguration(iceServers=[])`. It
   confirms:
   - the API the tracks build on (the names of 1.15.0: `PipelineWorker`, `WorkerRunner`,
     `await runner.add_workers(...)`);
   - that a speech-to-text bridge gets one request per user turn with `wait_for_transcript` off;
     if it cannot, the bridge cuts per VAD segment, step 12's entry says so, and the registration's
     request counts take their upper bounds;
   - that asyncio's UDP works on Windows (UNVERIFIED);
   - the frame rate a file fed against absolute `time.perf_counter` deadlines keeps over 60 s,
     since Python 3.12's `time.monotonic`, and so asyncio's clock and Pipecat's timers, tick at
     about 15.6 ms on Windows (docs.python.org/3/whatsnew/3.13.html, read 2026-11-02 by the
     feasibility review: 3.13 moved it to the performance counter);
   - with aioice 0.11.0 (uploaded 2026-11-01), a call whose ICE fails and one whose candidates
     trickle, the client's empty PATCH reaching aioice as the end of candidates; if 0.11.0
     misbehaves, a constraint below it goes to the owner under Q1.

   Findings go in the progress log; one that changes an interface below changes it before any
   track starts, never during one.
6. **Harness.** `[[owners]]`: `jwt` and `sqlite3` to `adapters`, `num2words` to `domain`, and
   `loguru` to `voice` (Q2). ARCH-BAN in a new helper, `scripts/arch_ban.py`, read from a new
   `[[bans]]` table: in the library, `pipecat.services.<vendor>` and Pipecat's LLM and
   context-aggregator modules, with `pipecat.services.stt_service`, `tts_service` and `ai_service`
   allowed in `voice`; in `voice/session/`, all of `pipecat`; in the apps and the examples,
   `pipecat` and `aiortc` (the design's 12.4). `[package] public` and `facades` gain `identity`,
   `server`, `stores` and `events`, and `tests/t2_agentic_voice/test_facades.py` their names.
   `[rules] output_allowed_files` gains `api/cli.py`.
   [ARCHITECTURE.md](../../../ARCHITECTURE.md) gains the owners' cells, ARCH-BAN in Enforcement,
   the logging convention as Q2 settled it, and the widget's line in the flow (the app, not the
   library's `api`, serves its static files); CLAUDE.md gains the new facades, the widget's line and
   the new tasks, within its 120 lines. `tests/conftest.py` also removes every variable step 4
   finds that changes behaviour, and makes aiortc's default ICE-server list raise, so a peer built
   without its own list fails the gate rather than reach a STUN server; `tests/harness/test_isolation.py`
   checks both. `tests/ole5_voice/evals/test_no_item_in_source.py`'s scan gains `apps/*/web`, the
   widget's folder, since its self-test already counts a page's label (Q6 rules on the labels).
7. **Settings.** `core/config.py` becomes the design's `VoiceSettings` (7.2 to 7.6): `env`
   required, `staging` added, every check that holds in `prod` today (`api/status.py`'s refusal of
   DEBUG among them) holding in `staging` too, `from_env(prefix=, env_file=, unknown=)`, no
   `get_settings()` singleton, `extra` refused under the prefix, a `*_FILE` form for each secret
   (the join keys and the TURN secret), each join key and the TURN secret at least
   32 bytes (a shorter one a `ConfigurationError` whose FIX line gives the generator command),
   `storage.var_dir`, and the groups M2 needs: `tts` (`provider`, `languages`, each a model and a
   voice, from Q5; `timeout_s`; `cache_phrases` true; `trim_silence` false), `turns` (the starting
   values of the decision log), `stt.live_language` (`session` until R5 to R7 set it),
   `session.mode` (Q3), `server` (with `turn_ttl_s`, 3600, refused above 86400, and
   `forwarded_allow_ips`, `*` refused), `join`, `privacy` (`record_audio` false, `consent_version`
   none), `logging` (`content` false, `pipecat` off) and the `limits` keys Q4 brings
   forward. The groups move into modules of their own to stay under ARCH-SIZE. A command,
   `uv run poe settings-ref`, writes `docs/generated/settings.md`
   and `.env.example` from the model, with a freshness test and a row in
   [docs/generated/README.md](../../generated/README.md). The change reaches `GroqSTT.from_settings`,
   the app's `evals/run.py` and `run_parts.py`, `tests/conftest.py` and the tests; a test proves a
   blank value still counts as unset, and every secret is a `SecretStr` in no repr or log line
   (invariant 5).
8. **Logging.** The owner settled the library's own logging on 2026-11-02 ("Fix it in M2
   (Recommended)", in plan 004's read): its loggers sit under
   `t2_agentic_voice` on the standard library, with a `NullHandler`, never touching the root
   logger, while `get_logger` keeps its structured call shape and `configure_logging` stays a
   helper an app calls, writing to a stream it can choose; this step pays TD-033. `voice` owns
   loguru (Q2).
9. **Errors.** `JoinRejected`, on the base error `T2VoiceError` (D-026); the
   code list in `tests/t2_agentic_voice/core/test_errors.py` grows with it.
10. **Interfaces, with stubs that raise `NotImplementedError`** (a test per stub, in the test file
    of the track that owns it, as plan 002 did):
    - the ports: `domain/ports/text_to_speech.py` (`TextToSpeech`, `AudioChunk`) and
      `domain/ports/identity.py` (`IdentityVerifier`, `UsedTokens`), and `aclose()` on
      `SpeechToText` (TD-020, the decision log);
    - `Caller` and `Consent` in `core/identity.py`; the events and `CallReport` in `core/events.py`
      (types every layer shares: ARCHITECTURE.md, "Conventions");
    - the declaration types Q3 settles (`VoiceAgent`, `Language` with its three presets and their
      greetings) in `domain/declaration.py`;
    - the `t2v/1` message models: the HTTP bodies (`/join`, `/offer`) in `api/protocol.py`, and the
      data-channel messages in `voice/protocol.py`, plain pydantic with no Pipecat, since `voice`
      cannot import `api` (`harness.toml`'s `[layers]`) and the session reads them; Tracks D, E, F
      and G read them;
    - `voice/session/io.py`: the commands and events between the session and the Pipecat modules,
      so Tracks D and E build against it alone: a user turn started and ended (each with its
      time), the turn's transcript, a clause queued and played, speak, stop and hang up; the
      input-audio and output-audio taps the recorder needs (PCM chunks with their sample rate and a
      monotonic timestamp); the client's messages in (`stop`, `hangup`, `client_stats`, the
      playback reports) and the session's out (`hello`, `caption`, `state`, `notice`), as
      `voice/protocol.py`'s models;
    - `voice`'s entry point that `api` calls (`voice/calls.py`): answer a call's SDP offer with its
      `Caller`, `Consent` and settings, add trickled candidates, end the call; and the file-fed
      transport's signature (`voice/file_transport.py`), which Track H builds on;
    - `VoiceRuntime`, `router()`, `serve()` and `combine_lifespans` as signatures;
    - the stubs each track fills (`## Tracks`), and the shared Groq client set-up (the header hook,
      the connection limits, `logging_unchanged` around `import groq`) moved from
      `adapters/groq_stt.py` into `adapters/groq_client.py`, so Track B builds `GroqTTS` on it
      without editing `GroqSTT`;
    - the facades with every name M2 adds and the module it lives in;
    - the fakes in `tests/t2_agentic_voice/fakes.py`: a fake `SpeechToText`, a fake
      `TextToSpeech`, a fake session I/O with every event, tap and message above, a fake `voice`
      entry point for `api`'s tests, a fake output transport that captures frames, and a fake
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
    logging and loguru (the owner's answer and Q2, amending D-002's bullet); ARCH-BAN and the new
    facades; the echo's shape (Q3); how Whisper is cut (per user turn, or per VAD segment if the
    spike shows the turn cannot be had); the settings keys beyond the design's 7.6
    (`stt.live_language`, the `session` group, `tts.trim_silence`,
    `server.forwarded_allow_ips`), as Proposed; and invariants 7 and 8 brought to the design's 8.1
    (the offer secret and the lock file; the consent claim as the second condition for audio),
    which amends D-007. Each is written as Accepted where the approved design describes it, and
    Proposed where it goes beyond, as the owner ruled for M1 (plan 002, Q3).
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
16. **The integration check, with no spend.** Inside `poe check`, a test the integrator writes and
    owns after the merges of D, E and F, since it needs the real pipeline, the echo session and the
    routes: an aiortc client, built with `RTCConfiguration(iceServers=[])`, joins, offers, sends a
    generated signal through a fake speech detector (no audio file:
    `tests/ole5_voice/evals/test_no_audio.py`), and receives the echo's audio from the fake
    `TextToSpeech`; `poe eot --answerer reference --split dev` scores 0 cut-offs and 0 ms. By hand:
    the agent starts `t2v dev` on `examples/minimal` with fake providers and opens `/dev` on
    localhost in its browser pane, which is not Chrome and may give no microphone: the page loads,
    ICE connects on whatever candidates the pane offers, the data channel opens and `hello`
    arrives; the microphone, playback and Stop wait for the owner's Chrome and Edge (step 18).
17. **The whole-plan review of the code**, by every reviewer. Then `plan-003-integration` merges into
    the main branch, with the full gate, so the owner's calls and the deployment run from it; from
    here, this plan's blocks merge into the main branch.

**The first live calls** (local; needs Q5, Q13 and Q17, and "What the owner does", steps 2 and 3;
recorded only if Q4 and Q7 are settled)

18. Step 23's spending rule applies first. The owner's first calls on the laptop, from the main
    checkout, through the Ole5 app's dev server on localhost: the laptop's speakers, then the wired
    headset, a few turns each, in the three languages, in Chrome and then in Edge, the owner
    checking the microphone, playback, Stop and Esc in each browser. They join through the Ole5
    app's token route with a local access code if Q4 is settled, and otherwise through
    `DevIdentity`, which never records. The agent reads each call's trace and `CallReport`; a fix
    is a block of its own.

**The deployment** (needs Q8 to Q12; re-planned for this machine before step 19, as the deployment's
criteria say)

19. **The deployment files**, written by the agent in `apps/ole5-voice-agent/deploy/` and reviewed
    by the security reviewer before the owner runs them on the host; the agent never logs into it:
    - the image, built from `git archive` of the merged commit (tracked files only, never a copy of
      a checkout, whose `.env` and `var/` hold the key and the owner's voice), with an allow-list
      `.dockerignore` (deny everything, then allow `packages/`, `apps/*/src`, `apps/*/web`,
      `examples/`, the `pyproject.toml` files, `uv.lock` and `.python-version`) and a test that it
      lets in no `.env*`, `var/`, `.claude/` or `*.wav`; the owner's steps end with a command that
      finds no `.env` or WAV file in the built image;
    - a compose file with the backend, Phoenix and, if Q9 picks it, coturn, and its port table:
      publicly only 443/tcp and the TURN ports Q9 keeps; the backend's HTTP port published only on
      127.0.0.1, or reached by the proxy over the compose network (Docker publishes on every
      address by default and its published ports bypass ufw: docs.docker.com/engine/network/port-publishing/
      and .../packet-filtering-firewalls/, read 2026-11-02 by the security review); Phoenix with
      `PHOENIX_ENABLE_AUTH=true`, its secret and initial admin password from host files, its
      retention from Q7, published on 127.0.0.1:6006 only and its gRPC port 4317 never;
    - the reverse proxy's configuration as a template holding no secret: TLS, the widget's and the
      router's routes, `X-Forwarded-For` overwritten rather than appended, and, if Q9 routes TURN
      by SNI, the PROXY protocol, so the backend still sees each caller's address;
    - coturn's configuration as a template holding no secret: `use-auth-secret` with the secret
      read from a host file at start; a realm; no TCP relay; no multicast peers; every
      special-purpose IPv4 and IPv6 range denied as a peer (loopback, private, link-local and
      metadata, carrier-grade NAT, unique-local, IPv4-mapped); only the backend's own address
      allowed, so the backend runs on a fixed non-loopback address and loopback peers are never
      allowed; user and total quotas and a bandwidth cap; its CLI off; its own certificate and key
      as host files. coturn 4.18.0 pinned by its image digest, or a host package no older than
      4.16.0, which fixes a denied-peer bypass (CVE-2026-73213: fieldguide.lutrasecurity.com/CVE-2026-73213/,
      read 2026-11-02 by the security review; UNVERIFIED against coturn's own advisory); each
      option checked against 4.18.0's example configuration
      (raw.githubusercontent.com/coturn/coturn/master/examples/etc/turnserver.conf, read 2026-11-02
      by the security review), which turns TCP relays on and sets no quota by default;
    - the settings: `T2V_PRIVACY__CONSENT_VERSION` set to Q7's version, and
      `T2V_PRIVACY__RECORD_AUDIO` false except during run C's sessions; and the owner's steps.
20. **The network spike on the host** (the design's 11, **verify**): what aiortc advertises behind
    Docker's NAT; whether coturn relays to a backend on the same host; a call relayed over TLS on
    443, and whether Chrome sends SNI on a `turns:` connection (UNVERIFIED); a call held past a
    short TURN lifetime (120 s), to see whether coturn drops its allocation before
    `server.turn_ttl_s`'s default is fixed; and two checks the owner runs with the agent's commands:
    with a minted credential, a permission to 127.0.0.1, 169.254.169.254 and the Docker gateway is
    refused, and so is a TCP allocation; from the phone hotspot, the backend's HTTP port, 6006 and
    4317 are refused. Each outcome in the progress log, before the network test.
21. **The website embed** (Q10) and the network test, under step 23's spending rule: a short call
    (a few turns) from the phone hotspot and one from the network that blocks UDP (Q11), each on the
    laptop's speakers and on the headset, not recorded, each call's report copied to the owner's
    machine with the agent's command. They are not C's calls, which come after every open call of
    the registration is settled.
22. **The media path**, recorded as a decision entry from the network test's outcome (the roadmap's
    M2: "Before M2 closes").

**The registered runs** (the registration below; a quiet machine: nothing else runs beside a run,
[WORKING-RULES.md](../../../WORKING-RULES.md), "Measurement runs")

23. Every open call settled and dated; the estimate and the budget cap approved by the owner (Q13).
    The spending rule, which also governs steps 18 and 21: before each run or call session that
    spends, the spend so far plus its own estimate is compared with the cap, and each model's
    requests, tokens and audio seconds that day with Q17's limits; one that would pass either does
    not start; the running total goes into the progress log after each, as plan 002's step 20 did.
24. A clean run worktree at the measurement commit, where every run of steps 25 to 27 starts;
    `poe eval --show-settings` checks the resolved settings; each run's smoke test passes with no
    failed, retried or refused call.
25. **E1 and E2** (end of turn, offline, no spend): the dev paused requests and the secondary set,
    twice.
26. **R5, R7, R6** (the noise on another day and the live language), each history line carried to
    the main branch in its own commit before the next run, then the run worktree's file reset, as
    plan 002's step 23 did; the comparisons; the rule sets `stt.live_language`'s default in its own
    commit.
27. **T1 and T2** (the time of each step), on a day with no call, since together they may take most
    of a day's published Orpheus requests and tokens for the Arabic model (Q17).
28. **C** (the owner's calls of Q18), recorded; the recordings copied to the owner's machine and
    their manifests committed; requests per call minute recorded as a decision entry, beside the
    key's real limits.
29. **Held-out:** E on held-out once, at the close, aggregates only. No held-out run spends in M2.

**Close**

30. The decision entries not yet written; the guide's pages finished; the design's factual slips
    that the research found (the design's 4.1 on Pipecat's `silero` extra, which exists with no
    requirements; its 10.3's "No number is known yet") listed for the owner and corrected as facts,
    not design changes. Its 3.2 on Groq's account team is listed as not confirmed either way: a
    third party quotes Groq's error asking the organisation's admin to accept a model's terms
    (github.com/langflow-ai/langflow/issues/11120, UNVERIFIED), and Groq's changelog says nothing of
    terms (read 2026-11-02 by the plan review), so it is corrected only from what the console shows
    the owner ("What the owner does", step 2). Then `## Future improvements` in this plan, with a
    pointer from the roadmap's "Planned later"; the whole-plan review; the roadmap's M2 row set to
    `done` with a link; this plan moved to `completed/` with its Status line; the final gate.

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
- 2026-11-02: Three reviews of the draft (feasibility, security, and the plan's form), each finding
  checked before it was acted on: against the repository (the golden set's items and split, the
  no-item test, the app's `pyproject.toml`, `api/status.py`, the design, the debt list, the
  prototype's log and `speakable.py`, and the garbage-collection round's branch), and, for the
  outside facts the main changes rest on, re-read by the agent the same day (Pipecat's
  `SegmentedSTTService` source and its user-turn strategies page, `pipecat/__init__.py` at v1.15.0,
  Phoenix's authentication page, Groq's rate-limits page). What changed: Whisper is cut once per
  user turn and Smart Turn waits for no transcript; the deployed Phoenix gets its API key; the
  deployment gains its image rules, port table and coturn hardening; FastAPI's telemetry is turned
  off on each app object; the session's I/O and `voice`'s entry point are laid down in Block 0;
  the registration pads each clip, times on `perf_counter`, counts Orpheus's token limits and
  Whisper's audio seconds an hour, and budgets the cut-offs; the echo drops speech heard while it
  plays; ticket endings are read digit by digit; the Ole5 app declares its own packages; Q2 is
  narrowed to loguru, since the owner had settled the library's logging; Q13 and Q17 move before
  the first live call. Two versions in the indirect table were stale (OpenCV's and PyAV's): the lock
  takes newer ones, so the table now names the constraint and step 3 records the version. Narrowed
  rather than taken as written: a reviewer's "mark FastAPI's `opentelemetry-api` dependency
  UNVERIFIED", since the other two reviews read it in its PyPI metadata; "the app's server ends a
  call after a fixed length", since an app cannot end a call (observers cannot change behaviour,
  the design's 6.6), so Q4 offers the library's own `limits` keys early; "client messages as
  `api/protocol.py` models", since `voice` cannot import `api`, so the data-channel models sit in
  `voice/protocol.py`; and citations of the round's plan and decision by number, which DOC-REF
  refuses until that round merges (step 1 adds them then).
- 2026-11-02: Rebased onto the main branch after plan 004 merged (750d90a), and brought up to date
  as step 1 says: no row the round removed is cited (ten were); httpx leaves the first `uv add`
  and the dependency table, since the library declares it; step 6 no longer splits `harness_config.py`;
  steps 8 and 9 cite TD-033 and D-026; the guide's samples are checked by DOC-SAMPLE; the rows the
  round left for M2's plan are in the decision log, and TD-037's row follows this plan's choice for
  `reference/api.md`. `uv run --offline poe docs`: 'check_docs: OK (27 files checked)'. Next: the
  owner's calls before Block 0 (Q1 to Q6), then Block 0.
- 2026-11-02: The owner's answer to Q1 to Q6 is recorded ("The owner's decisions"), each question
  marked settled, with Q8 settled in part: all hosting is on this machine for now, and Phoenix is
  M1's with no SSH tunnel and no authentication, so `tracing.api_key` leaves Block 0's settings and
  the debt it would have paid, and the deployment is re-planned for this machine before step 19.
  D-027 is marked Accepted, and the roadmap's open questions on the host and the voices are
  answered. Step 2: `docs/plans/active/` holds 000 and 003, `completed/` 001, 002 and 004, and
  decisions.md ends at D-027; of the other sessions, the one at work answered that it holds no plan,
  decision or debt number and claims none, so Block 0 takes the next numbers after D-027 and
  TD-040. Next: this plan merges into the main branch, then Block 0.
- 2026-11-02: The plan merged into the main branch (69353de); `plan-003-integration` was cut there,
  and Block 0 is built in the worktree `plan-003-block-0`, cut from it. Step 3, the dependencies, as
  Q1 allows:
  - The two commands of "Dependencies to install", exactly as written. `uv lock` added 53 packages
    and moved protobuf from 7.36.2 to 6.33.6, a later 6.33 release than the 6.33.5 the plan read.
    Each new package, with the licence its installed metadata declares (its License-Expression, else
    its License field, else its classifier): aiofiles 25.1.0 (Apache-2.0); aiohappyeyeballs 2.7.1
    (PSF-2.0); aiohttp 3.14.5 (Apache-2.0 AND MIT); aioice 0.11.0 (BSD-3-Clause); aiortc 1.15.0
    (BSD-3-Clause); aiosignal 1.4.0 (Apache 2.0); annotated-doc 0.0.5 (MIT); attrs 26.1.0 (MIT); av
    17.1.0 (BSD-3-Clause); cffi 2.1.1 (MIT-0); cryptography 50.0.2 (Apache-2.0 OR BSD-3-Clause);
    dnspython 2.9.1 (ISC); docopt 0.6.2 (MIT); docstring-parser 0.18.0 (MIT); fastapi 0.162.0 (MIT);
    flatbuffers 25.12.19 (Apache 2.0); frozenlist 1.8.0 (Apache-2.0); google-crc32c 1.9.0
    (Apache-2.0); httpcore2 2.16.0 (BSD-3-Clause); httpx2 2.16.0 (BSD-3-Clause); ifaddr 0.2.0 (MIT);
    jiter 0.18.0 (MIT); llvmlite 0.50.0 (BSD-2-Clause AND Apache-2.0 WITH LLVM-exception); loguru
    0.7.3 (MIT License); loudness 0.2.0 (MIT); markdown 3.11.2 (BSD-3-Clause); multidict 7.2.1
    (Apache-2.0); num2words 0.5.14 (LGPL); numba 0.68.1 (BSD); numpy 2.5.4 (BSD-3-Clause AND 0BSD
    AND MIT AND Zlib AND CC0-1.0); onnxruntime 1.31.1 (MIT License); openai 3.42.1 (Apache-2.0);
    opencv-python-headless 4.14.0.94 (Apache 2.0); pillow 13.0.0 (MIT-CMU); pipecat-ai 1.15.0
    (BSD-2-Clause); propcache 0.5.4 (Apache-2.0); pycparser 3.12 (BSD-3-Clause); pyee 16.0.1 (MIT);
    pyjwt 2.15.1 (MIT); pylibsrtp 1.0.0 (BSD-3-Clause); pyopenssl 26.4.0 (Apache License, Version
    2.0); resampy 0.4.3 (ISC); sentencex 1.0.32 (MIT); soundfile 0.13.1 (BSD 3-Clause License); soxr
    1.0.0 (LGPL-2.1-or-later); starlette 1.10.0 (BSD-3-Clause); truststore 0.10.5 (MIT); uvicorn
    0.54.0 (BSD-3-Clause); websockets 17.4 (BSD-3-Clause); win32-setctime 1.2.1 (MIT license); yarl
    1.25.1 (Apache-2.0). audioop-lts 0.2.2 (for Python 3.13 and later) and httpx2-jsfetch 1.0 (for
    emscripten) are in the lock but not installed on Python 3.12 or on Windows; their licences are
    UNVERIFIED.
  - Against the plan's tables: httpx2 and httpcore2 (BSD-3-Clause) and truststore (MIT) were not
    listed; openai 3.42.1 requires httpx2, which requires the other two (`uv.lock`). tqdm did not
    come. The declared licences outside the tables' words are permissive (D-016): numpy's 0BSD, Zlib
    and CC0-1.0 parts, cffi's MIT-0 and aiohappyeyeballs's PSF-2.0. No licence stops the block.
  - What the wheels bundle (each `*.dist-info/licenses/` and `LICENSE*` file, each `*.libs/`
    folder): PyAV's `av.libs/` holds FFmpeg's libraries (avcodec-62, avformat-62 and the rest) with
    libx264 and libx265 (GPL), libmp3lame and libiconv (LGPL), libvpx, libdav1d, libopus, SVT-AV1,
    libwebp, opencore-amr, zlib and the MinGW runtime (libgcc_s, libstdc++, libwinpthread); the
    wheel's only licence files are PyAV's own (`LICENSE.txt`, BSD-3-Clause, and its authors' lists),
    which name none of them. soundfile bundles `_soundfile_data/libsndfile_x64.dll` with its
    `COPYING` (the LGPL). OpenCV bundles `cv2/opencv_videoio_ffmpeg4140_64.dll`, and its
    `LICENSE-3RD-PARTY.txt` says FFmpeg is redistributed within all opencv-python packages. soxr's
    licence files are `COPYING.LGPL`, `LICENSE-libsoxr.txt` and `LICENSE-PFFFT.txt`. numpy's
    `numpy.libs/` holds OpenBLAS (scipy-openblas) and the MSVC runtime, and llvmlite's
    `llvmlite.libs/` the MSVC runtime. Every copyleft library here is one Q1 lists, or sits inside
    PyAV's FFmpeg bundle, which Q1 accepts whole; each is used unmodified.
  - Types: pipecat-ai, loguru and PyJWT ship `py.typed`; num2words does not, so `pyproject.toml`
    gains its `[[tool.mypy.overrides]]` entry. `uv run --offline poe types`: 'Success: no issues
    found in 172 source files'.
  - Size, for `is-this-for-you.md`: the 51 new packages installed on Windows take 483.8 MB (llvmlite
    121.5, OpenCV 115.9, PyAV 68.6, onnxruntime 43.7, numpy 42.0, pipecat-ai 20.6), summed from each
    distribution's file list; the worktree's whole `.venv` is 505 MB (`du -sm`).
  - `uv lock --check --offline`: 'Resolved 107 packages in 3ms'. `uv run --offline poe check` on the
    new lock, before the override: 'Total coverage: 100.00%', '1377 passed, 1 skipped in 92.66s'.
    Steps 4 and 5 run next, as a workflow of agents: five readers of the installed sources, each
    checked by an agent that re-opens every cited line, and the two spikes.

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
  `CHANGELOG.md` on GitHub at v1.15.0, read 2026-11-02 by the research step; the user-turn
  strategies page below gives the same default), with `wait_for_transcript` off: it is on by default
  (docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies.md, read
  2026-11-02), and then a turn's end would wait for Whisper, so T could not time Smart Turn's
  decision apart; the session waits for the transcript itself.
- 2026-11-02: Whisper gets one request per user turn: the speech-to-text bridge holds the turn's
  audio from its start to its end and sends it whole. Pipecat's `SegmentedSTTService` sends one per
  VAD segment (its source, read 2026-11-02: step 4), and with a 200 ms VAD stop and the owner's
  pauses of about 0.83 s a paused request would become two requests or more, each billed at least
  10 s, of fragments Whisper hears without their context, which M1's whole-clip baseline never
  measured. Alternative: per segment, which hides the earlier segments' time inside the caller's
  speech; set aside for the requests per call minute (the published 20 a minute for
  `whisper-large-v3`) and for M1's baseline. If the spike (step 5) shows the turn cannot be had,
  the bridge cuts per segment, the session joins the segments' transcripts and waits for the last,
  and the registration's request counts take their upper bounds.
- 2026-11-02: Speech that starts while the echo plays, or within 300 ms after it ends, is not said
  back: the turn is dropped, and kept on the recording and the timeline for M3, as the prototype's
  first hands-free step was half-duplex (its D23, `Ole5-chatbot/VOICE_LOG.md`, line 32). Only Stop,
  Esc and `hangup` interrupt in M2, since the interruption rules are M3's. Alternative: queue the
  turn and say it back after the echo; set aside because on the laptop's speakers any of the echo
  that leaks past Chrome's echo cancellation would end a turn and be said back, so the agent could
  keep echoing itself (the prototype saw its own echo taken as the customer's words, line 360).
- 2026-11-02: The echo's frame is a fixed phrase, cached, played once the turn's transcript is in,
  so the first audio after a turn plays from the cache while Orpheus synthesizes the heard words;
  an empty transcript is said back as nothing (the filter for text from silence is M3's). One voice
  speaks each reply, the language's (the prototype's D35: mixed voices sound "like a different
  person", `Ole5-chatbot/VOICE_LOG.md`, line 43).
- 2026-11-02: Live calls send Whisper the session's language, from the language the caller picks in
  the widget (Arabic first) and the token's `locale`, through `stt.live_language = "session"`, until
  runs R5 to R7 decide: M1 measured only a language hint (D-024, D-025), and a default moves only on a
  registered measurement (GP-18). The widget's language buttons are built either way (Track G).
- 2026-11-02: Orpheus's audio is kept as it comes: trimming its silence (the prototype's D25, 0.4 to
  0.7 s before speech) lands behind `tts.trim_silence`, off, and runs T1 and T2 measure the leading
  silence, so M4's latency target can weigh it. A take that came back cut short (the prototype's
  ceilings of 24 characters a second for Arabic and 30 for English, `Ole5-chatbot/src/ole5_chat/voice/tts.py`,
  lines 24-36) is flagged on its span and in the report, not made again, in M2.
- 2026-11-02: Speaking rules in M2: a run of digits is an ID, read digit by digit from the
  library's own table, when it has five digits or more, starts with a zero, or follows a cue that
  names a number's end ("ending in", «آخرها», «ينتهي بـ»), as the golden set's ticket items say
  their last four digits and the prototype read them (`Ole5-chatbot/src/ole5_chat/voice/speakable.py`,
  lines 7-18); any other run is a number, through num2words (MSA forms in Arabic, which num2words
  gives; Saudi forms are not in it). Alternative: every run digit by digit, set aside because a
  count or an amount ("3 tickets") would read wrong. The agent's starting rule, revisited when M4's
  templates name `{x:id}` and `{x:number}` explicitly. Dates are spoken from M5, when status replies
  need them.
- 2026-11-02: The Ole5 app serves by mounting the library's router in its own FastAPI app, one
  worker, beside its token route and its widget's static files (the design's 4.5, "The mount"); its
  `server.py` runs uvicorn and sets the app's CORS and FastAPI's telemetry itself. `serve()` is built
  too, and `examples/minimal` uses it (Core proof). Alternative for M2: the sidecar, set aside since
  the token route and the widget would then need a second process and port, and CORS between them;
  it is the shape when the website mints tokens (open question 19), which waits on Q12.
- 2026-11-02: The deployed backend runs with `env=staging`: every production check holds in it too
  (no `DevIdentity`, no dev page, no `logging.content`, no DEBUG; the design's 7.4) while no
  customer uses it. Alternative: `env=prod`, set aside while the backend serves only the owner.
- 2026-11-02: The widget is checked in the agent's browser pane on localhost for what needs no
  microphone, and by the owner in Chrome and in Edge for the rest (step 18) and in the owner's
  calls; the pane is not Chrome, and the agent has no tool that drives Edge. No headless-browser
  package is added, which TD-022 leaves to the owner, and the widget gets a debt row like the
  recorder's.
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
- 2026-11-02: Debt paid in M2: TD-012, TD-014, TD-020, TD-026 (before R7, so the comparison refuses
  any setting but the language hint), TD-011 (read in R7's smoke step), TD-032 (R5 and R6), and the
  logging (TD-033, step 8). TD-015 stays whole: the owner's Phoenix runs on this machine with no
  authentication ("The owner's decisions"), so no trace needs an API key in M2. TD-004 follows Q8:
  with no proxy on the host, the clients turn `trust_env` off; with one, a proxy setting is added.
  TD-003 and TD-005 stay: `GroqTTS` imports groq inside `logging_unchanged` as `GroqSTT` does, and
  the owner kept TD-005 as debt (2026-11-01).
- 2026-11-02: The rows plan 004 left for M2's plan, beyond those above. TD-038's test, which records
  the variables groq and OpenTelemetry read in a child process against a committed list, lands where
  TD-004 changes the clients, so the change and a later version move show in the gate; step 4's
  reading of the new packages adds their variables to the guide's "Variables to leave unset", which
  the test's list follows. TD-005's fork part goes with TD-014, as its row proposes: the track that
  builds tracing inside the lifespan tests whether the SDK's fork hook still runs for a provider
  built after a worker forks, and the row is narrowed or paid on what that test shows. TD-037 waits
  with `reference/api.md` for the first tag a teammate installs (above), and its row says so. TD-034
  (two exports nothing raises) and TD-039 (ARCH-PRINT over the apps) stay: neither is M2's work, and
  TD-039 is a rule for the owner. TD-022 stays with the owner (above). The agent's.
- 2026-11-02: FastAPI 0.162.0 requires `opentelemetry-api` (its metadata,
  pypi.org/pypi/fastapi/0.162.0/json, read 2026-11-02 by the reviews) and by default sends request
  traces, metrics and logs through OpenTelemetry's global providers, adding exporters when
  `FASTAPI_OTEL_AUTO_CONFIGURE` is true (fastapi.tiangolo.com/advanced/opentelemetry/, read
  2026-11-02 by the research step and the reviews). Its switch is an argument of the `FastAPI`
  object, so `serve()` turns it off on its app and the Ole5 app's server on its own, a mounted
  router being unable to reach the app it is mounted in; the library never instruments another
  library (D-023), and `serving.md` tells a team that mounts the router to do the same.
  Alternative: leave it to the guide alone, set aside because a mount would then trace, measure and
  log every request by default.
- 2026-11-02: `t2v/1` names no message `signalling` and none starting with "ping", which
  SmallWebRTC reserves on the data channel (Pipecat's `connection.py`,
  raw.githubusercontent.com/pipecat-ai/pipecat/main/src/pipecat/transports/smallwebrtc/connection.py,
  read 2026-11-02 by the research step and the security review; step 4 re-reads it at 1.15.0).
- 2026-11-02: The client sends the empty end-of-candidates PATCH, because aioice 0.11.0 now waits for
  it before declaring ICE failed (its changelog, github.com/aiortc/aioice/blob/main/docs/changelog.rst,
  read 2026-11-02 by the research step and the feasibility review); without it a failed call shows
  only at Pipecat's 60 s connection timeout. A PATCH that arrives after ICE completed gets a quiet
  409 (the router criterion), since the secret has stopped working by then.
- 2026-11-02: TURN is needed for the call from a network that blocks UDP whatever ports the host
  opens: aioice gathers UDP host candidates only and cannot pin its port range (its `ice.py`,
  `src/aioice/ice.py` on github.com/aiortc/aioice's main branch; the
  port-range pull request, github.com/aiortc/aioice/pull/112, is still open; both read 2026-11-02 by
  the research step). So Q9 asks how to run TURN, not whether, and the design's "only if the network
  test needs it" (its 3.1 and 11) is read as settled by the roadmap's own test.
- 2026-11-02: The recordings: the caller's track as the pipeline hears it, 16 kHz mono 16-bit WAV
  (the golden set's format, `ole5_voice/evals/audio.py`); the agent's audio as sent, 24 kHz mono
  WAV (the pipeline's output rate, `PipelineParams`); and a timeline JSON per call (each clause's
  text, when it was sent and when the browser reported it playing, each stop and each turn end).
  Under `var_dir/recordings/<call ID>/`; each call's manifest (consent, hashes, lengths, no audio)
  committed under `apps/ole5-voice-agent/evals/calls/`, so M3 imports them as golden items with
  references the owner confirms, as plan 002's import did. Alternative: one compressed file (Opus)
  per call, set aside since an encoder would be a new dependency and M3 imports WAV as the golden
  set's.
- 2026-11-02: In M2 only the phrases declared at lifespan start are cached; text built from heard
  words never reaches the cache, since an echo clause is the caller's speech and caching it would
  keep call content by default (invariant 8). The design's caching of talker clauses that repeat
  exactly (its 10.4) is M4's to decide, with its own note on invariant 8. Alternative: cache a
  repeated echo clause, set aside for that reason.
- 2026-11-02: Each call's report numbers (usage per model, requests per call minute, `client_stats`
  with the candidate type and relay protocol, the timings), with no heard or spoken text, go on the
  call's root span and into a JSON file per call under `var_dir/reports/`, which the agent reads,
  beside the call's traces in the Phoenix on this machine (D-023; "The owner's decisions").
  Alternative: log the `CallReport`, set aside because it holds what was heard and said (the
  design's 6.6) and INFO carries no call content (its 10.2).
- 2026-11-02: The data-channel messages of `t2v/1` are modelled in `voice/protocol.py` and the HTTP
  bodies in `api/protocol.py`: the session parses and sends the data-channel messages, and `voice`
  cannot import `api` (`harness.toml`'s `[layers]`). Alternative: one module in `core`, set aside
  because the messages are the call's, not shared by every layer.
- 2026-11-02: Every aiortc peer the repository builds (the spike's, the integration test's client,
  any the file-fed transport needs) passes `RTCConfiguration(iceServers=[])`, and
  `tests/conftest.py` makes aiortc's default list raise: given none, aiortc asks Google's STUN
  server (`aiortc/rtcicetransport.py`, read 2026-11-02 by the security review), while the design's
  11 says the library contacts nothing beyond its outbound hosts.
- 2026-11-02: The file-fed transport paces frames against absolute deadlines (its start plus n
  frames) on `time.perf_counter`, and Track H times each step with `time.perf_counter`: on Windows,
  Python 3.12's `time.monotonic`, which asyncio's clock and Pipecat's timers use, ticks at about
  15.6 ms (step 5), and relative sleeps drift. Alternative: Python 3.13, set aside since the owner
  chose 3.12 (D-018, question 3); the registration states the resolution instead.
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
  this is Q6, which also rules on the widget's labels once the widget's folder is scanned (step 6).
  Every other text avoids the one-word references (okay, wait, yeah, and the Arabic ones), as plan
  002's tracks did.
- 2026-11-02: eot-bench is not added in M2, a departure from the design's 13 ("Depend (dev)") for the
  owner to confirm with Q1, though the design's M2 row does not list it: its Arabic slice is not
  Saudi speech, and the golden set's paused requests are the registered data. Alternative: add it
  as a dev dependency for an English cross-check, set aside as a download no M2 result needs.
- 2026-11-02: The runs are attended, made by the agent in this session one after another, as in M1;
  an unattended schedule only if the owner asks for one. Whisper's requests are paced at 10 a
  minute and each Orpheus model's at 5, half the published limits, as plan 002's runs did after the
  owner's "Something might", until Q17 says otherwise; and no hour holds more than about 5,000
  billed Whisper seconds (the published 7.2K audio seconds an hour).
- 2026-11-02: The measured requests per call minute go into a decision entry, as D-024 recorded the
  noise, so M6 cites them when it sets the cap on live calls.

## The owner's decisions

What the owner has already said that binds M2, in the owner's words where they wrote them:

- 2026-11-02, the request that starts this plan: "If everything is good, record the "Future
  improvements" and start implementing M2".
- 2026-11-02, the owner's answer to Q1 to Q6, each put with the agent's recommendation: "Yes go with
  the recommended. Except that phoenix needing an SSH tunnel, Phonies will be hosted locally so no
  need for too much security. Also I have no access to the server during this stage, all hosting
  should be in this machine meanwhile. If everything is set start implementing M2". So, in the
  agent's words of each recommendation:
  - Q1: every package of "Dependencies to install" is downloaded, and the copyleft licences that
    come with them are accepted, each used unmodified: soxr, soundfile's libsndfile, the FFmpeg in
    OpenCV's wheels, tqdm, and the FFmpeg in PyAV's wheels. The same answer covers the Ole5 app's
    command and a constraint keeping `aioice` below 0.11 if the spike needs one (step 5). eot-bench
    is not added.
  - Q2: `voice` owns loguru. Pipecat's namespace is switched off before `voice` first imports
    Pipecat, and again at runtime start; `logging.pipecat = "forward"` forwards its WARNING and
    above to `t2_agentic_voice.pipecat`; no sink is added or removed.
  - Q3: `VoiceAgent(name, languages=[...])` with the `Language` presets, and the setting
    `session.mode`, `echo` its only value in M2; the cached frame «سمعتك تقول: …» or "I heard: …"
    plays before the heard words.
  - Q4: the Ole5 app's token route mints a join token only for a caller who types the owner's access
    code (at least 16 characters, compared in constant time, repeated tries slowed, at most 20
    failed tries an hour); the route mints at most 10 tokens a day; the library builds
    `limits.max_call_s` (600) and `limits.idle_s` (120) early; the owner runs the backend only
    during call sessions and rotates the code after run C; the risk left is a debt row for M6.
  - Q5: `abdullah` and `troy`, as the library's defaults and Ole5's, and M2's fixed phrases in Saudi
    dialect.
  - Q6: one entry in `allowed_in_source.toml`, "stop", for the protocol's message and method names,
    and the widget's labels «إيقاف» and «أوافق».
  - D-027 (ARCH-DEPS and DOC-SAMPLE), Proposed since plan 004, which the agent's message said
    approving this plan would cover: Accepted.
  - The exception, and the host: Phoenix runs on this machine as M1's does (D-023), on 127.0.0.1,
    with no SSH tunnel and no authentication, so M2 builds no `tracing.api_key` and TD-015 stays
    whole. All hosting is on this machine while the owner has no access to the server, so Q8 is
    answered as this machine for now. The deployment (steps 19 to 22, its criteria, Q9 to Q12, and
    Q7's host parts) is re-planned for this machine before step 19, as a dated amendment the owner
    approves; no step before 19 depends on it.
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
- 2026-11-02, the garbage-collection round's read (quoted in [plan
  004](../completed/004-garbage-collection-1.md)'s decision log): on the library's logging, which does not meet the design's contract (its
  3.3 and 10.2), "Fix it in M2 (Recommended)", with a debt row now; on `AppError` against the
  design's `T2VoiceError`, "Rename it now (Recommended)", keeping `AppError` as a deprecated alias.
  So M2 builds the design's logging contract (step 8), and only who owns loguru is left (Q2).
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

Two commands from the repository root, with the lock in the same commit, once the owner allows
them (Q1): the library's, to its one install (D-018, question 2), and the Ole5 app's, for the
packages its own code imports (its server, its settings and its token route), so the app relies on
no package another member brings (ARCH-DEPS refuses it, D-027). The app's three are the versions
the library's command locks or already locked, so the second command downloads nothing.

```
uv add --package t2-agentic-voice "pipecat-ai[webrtc]~=1.15.0" "fastapi>=0.162.0" "uvicorn>=0.54.0" "PyJWT>=2.15.1" "num2words>=0.5.14" "loguru>=0.7.3"
uv add --package ole5-voice-agent "fastapi>=0.162.0" "uvicorn>=0.54.0" "pydantic-settings>=2.15.0"
```

| Package | Constraint | Version the lock should take | Licence | Owning layer (`[[owners]]`) | Why M2 needs it |
| --- | --- | --- | --- | --- | --- |
| `pipecat-ai[webrtc]` | `~=1.15.0` (the design's 5.4) | 1.15.0, uploaded 2026-10-29 | BSD-2-Clause (PyPI, read 2026-11-02) | `voice` (`pipecat`, already listed) | The pipeline, SmallWebRTC, Silero VAD and Smart Turn v3.2 (both ONNX files in its wheel), the STT and TTS base classes |
| `fastapi` | `>=0.162.0` (the floor the design's 4.5 leaves to this plan: router lifespans merged, checked in 0.162.0) | 0.162.0, 2026-10-23; requires `opentelemetry-api>=1.44.0` (pypi.org/pypi/fastapi/0.162.0/json, read 2026-11-02 by the reviews) | MIT (PyPI, read 2026-11-02) | `api` (already listed) | The router, the lifespan, CORS |
| `uvicorn` | `>=0.54.0` | 0.54.0, 2026-09-25 | BSD-3-Clause (PyPI, read 2026-11-02) | `api` (already listed) | `serve()`, `t2v serve` and `t2v dev` |
| `PyJWT` | `>=2.15.1` | 2.15.1, 2026-09-28; no dependency without its `crypto` extra | MIT (PyPI, read 2026-11-02) | `adapters` (`jwt`, a new row) | `SignedJoinTokens`, HS256 only |
| `num2words` | `>=0.5.14` (Pipecat requires the same) | 0.5.14, 2024-12-17; needs `docopt` | LGPL (PyPI's classifier, read 2026-11-02); accepted as LGPL-2.1, unmodified, behind a `domain` function (D-018, question 20) | `domain` (a new row) | `speak_number` |
| `loguru` | `>=0.7.3` (Pipecat requires `~=0.7.3`) | 0.7.3, 2024-12-06 | MIT (the research step, PyPI, read 2026-11-02) | `voice`, or `core` if Q2 says so (a new row) | `logger.disable("pipecat")` and the forward sink |
| `fastapi`, `uvicorn`, `pydantic-settings` for `ole5-voice-agent` | as the library's; `>=2.15.0` for pydantic-settings, the library's own constraint | the library's versions; pydantic-settings 2.16.2, already locked | as above; MIT for pydantic-settings | none: the owner rules do not apply to an app (`harness.toml`, `[[apps]]`) | The Ole5 app's server (its own `FastAPI` object, uvicorn run with proxy headers), its `OLE5_VOICE_` settings and its token route |

**Indirect packages** that come with them; no layer imports them, so they get no `[[owners]]` row.
"Checked" marks a licence read on PyPI on 2026-11-02 (by the agent, or by the research step); the
rest are the agent's memory, UNVERIFIED until step 3 reads the installed metadata. Versions not
given are the ones `uv lock` resolves, listed in step 3.

| Package | Comes with | Licence |
| --- | --- | --- |
| `aiortc` 1.15.0 | Pipecat's `webrtc` extra | BSD-3-Clause (checked) |
| `aioice` 0.11.0 (uploaded 2026-11-01, a day before this plan and after aiortc 1.15.0 of 2026-07-13, which allows `>=0.10.2,<1.0.0`; the spike tests it, step 5), `pylibsrtp` 1.0.0, `pyee`, `dnspython`, `ifaddr` | aiortc | BSD-3-Clause for aioice (checked); BSD-3-Clause, MIT, ISC and MIT for the others |
| `av` (PyAV), the version `uv lock` resolves under aiortc's `<18` (17.1.0 the newest on PyPI on 2026-11-02, per the plan review; the research step read 17.0.0) | aiortc | BSD-3-Clause for PyAV itself (checked for 17.0.0). Its binary wheels bundle FFmpeg built by pyav-ffmpeg, whose README lists x264 and x265 among the libraries built in (read 2026-11-02); both are GPL, so the bundled FFmpeg is likely GPL. UNVERIFIED: the README states no licence; step 3 reads the resolved version's bundled files. Q1 |
| `opencv-python-headless`, the version `uv lock` resolves under Pipecat's `<5` (4.14.0.94 the newest 4.x on 2026-11-02, requiring `numpy>=2` with no cap, per the plan review; the research step read 4.12.0.88) | Pipecat's `webrtc` extra | Apache-2.0 for OpenCV, MIT for the packaging; "All wheels ship with FFmpeg", under LGPLv2.1 (checked for 4.12.0.88; step 3 re-reads the notice for the resolved version) |
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
  the research step), if Q9 picks it: run on the host as a small service from its own image pinned
  by digest, or from a host package no older than 4.16.0 (step 19), never added to a member.
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
`core/events.py`, `domain/declaration.py`, `api/protocol.py`, `voice/protocol.py`,
`voice/session/io.py`, the stubs' signatures (`voice/calls.py`, `voice/file_transport.py`),
`adapters/groq_client.py`, the facades, `scripts/`, `.env.example`, `docs/generated/settings.md`,
`tests/conftest.py`, `tests/harness/`, `tests/ole5_voice/evals/test_no_item_in_source.py` and the
fakes) belong to Block 0, and this plan and `docs/plans/tech-debt.md` to the integrator, who also
writes and owns step 16's loopback test. A track that needs one changed asks the integrator.
Library paths are under `packages/t2-agentic-voice/src/t2_agentic_voice/`; library tests under
`tests/t2_agentic_voice/`. In every track, no source string and no JS or HTML text under `packages/`,
`apps/*/src`, `apps/*/web` or `examples/` holds a golden reference as whole words (Q6 rules on
`stop` and on the widget's labels), and no test text copies an item's.

**Track A · Speech text (library, `domain`).**
- Goal: `speak_number`, `speak_id`, the clause splitter and the pronunciation map.
- Owns: `domain/text/speaking.py`, `domain/text/clauses.py`, `domain/text/pronounce.py`; tests
  `domain/test_speaking.py`, `domain/test_clauses.py`, `domain/test_pronounce.py`.
- May read: `Ole5-chatbot/src/ole5_chat/voice/speakable.py` (digit words, "ending in", the shaping
  of text for speech, lines 7-41 and 109-157); num2words' documentation.
- Tests: digits and numbers in Arabic and English; a 16-digit ticket number read digit by digit;
  a run with a leading zero, and a four-digit run after each ending cue, read digit by digit in
  Arabic and in English, in texts written for the test, not taken from an item; a short run with no
  cue read as a number; Arabic-Indic digits; the splitter on «،», «؟», «.» and English
  punctuation, every clause under `max_chars`, none cut inside a word; the pronunciation map whole
  words only.

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
  24 kHz per Pipecat's Groq service and the Orpheus code, UNVERIFIED); each response's
  remaining-requests and remaining-tokens headers passed to the usage; the cache asked only for the
  phrases declared at lifespan start; cache files written whole to a temporary name and renamed.
- Tests: as the acceptance criteria; the cache key changes with text, model and voice; a cache hit
  sends nothing; `GROQ_LOG=debug` in a child process, as `GroqSTT`'s test does (TD-003).

**Track C · Identity, stores and TURN credentials (library, `adapters`).**
- Goal: `SignedJoinTokens`, `DevIdentity`, `SqliteUsedTokens`, `MemoryUsedTokens`, coturn's REST
  credentials.
- Owns: `adapters/join_tokens.py`, `adapters/dev_identity.py`, `adapters/used_tokens.py`,
  `adapters/turn_credentials.py`; tests under `adapters/`.
- May read: the identity port, `core/identity.py`, the settings; PyJWT's and coturn's documentation.
- Behaviour: the claims parsed into a strict pydantic model (`StrictBool` for `record_audio`, a
  bounded `version`); PyJWT's minimum key length turned on for encode and decode if 2.15.1 has it
  (step 4); a consent marked as a verified signed token's only by `SignedJoinTokens`, so the
  recorder can tell it apart; `DevIdentity` always `Consent(version=None, record_audio=False)`;
  TURN usernames `<expiry>:<call ID>`, valid for `server.turn_ttl_s`.
- Tests: invariant 7's adversarial cases (the acceptance criteria); the used-token store under two
  threads and after a restart; the TURN password the HMAC of coturn's scheme on a fixed vector; the
  TTL honoured; the username holding no `sub` or `name`; the secret and each per-call password in
  no repr, log line, span or error.

**Track D · The voice session in echo mode (library, `voice/session/`, no Pipecat).**
- Goal: one call's session: turn order, the echo, Stop and `hangup`, speech dropped while the echo
  plays, heard words, playback bookkeeping, usage per model and per call minute, the `CallReport`
  and its content-free file, the turn and TTS spans, and the call recorder.
- Owns: `voice/session/call.py`, `echo.py`, `heard.py`, `playback.py`, `usage.py`, `recording.py`,
  `report.py`; `core/tracing_tts.py` (the TTS span and the resource attributes, the settings digest
  with no secret); tests under `voice/session/` and `core/test_tracing_tts.py`; the `[[restricted]]`
  row for `HeardWords` (applied by the integrator at the merge, `harness.toml` being Block 0's).
- May read: `voice/session/io.py`, the ports, `core/events.py`, `core/tracing.py`, Track A's
  signatures; the prototype's `capture.py` (one record per utterance, audio only when switched on)
  and `session.py`'s clock (lines 234-253), read only.
- Tests: with the fake session I/O, fake ports and the fake clock: the echo per language; Stop and
  `hangup`; a turn whose speech starts during the echo, or within 300 ms after it, not said back; a
  turn end that arrives before its transcript; an empty transcript; usage counted per model; the
  recorder writes nothing with the setting off, with the consent false, with both, or under
  `DevIdentity` with the setting on, and a client message cannot change either; after an echo turn
  the phrase cache was never asked for the heard text; the report file holds no text of the call;
  the settings digest unchanged when a secret changes; no secret in any span.

**Track E · The Pipecat modules (library, `voice`).**
- Goal: the pipeline per call and everything that touches Pipecat, `voice`'s entry point for
  `api` included; Pipecat's loguru namespace switched off before `voice` first imports Pipecat.
- Owns: `voice/pipeline.py`, `voice/transport.py`, `voice/turns.py`, `voice/stt_bridge.py` (one
  request per user turn), `voice/tts_bridge.py`, `voice/session_bridge.py`,
  `voice/loguru_policy.py`, `voice/pipecat_events.py`, `voice/calls.py`, `voice/file_transport.py`
  (frames paced against absolute `time.perf_counter` deadlines); tests under `voice/`.
- May read: Block 0's reading of the installed Pipecat (step 4) and the spike's findings (step 5);
  Pipecat's documentation and examples (`p2p-webrtc/voice-agent/server.py` and `index.html`, read
  2026-11-02 by the research step).
- Tests: each bridge against fakes; the speech-to-text bridge sends one request for a turn with a
  pause in it; a `stop` drops the turn's queued audio; no Pipecat interruption fires; invariant 8's
  tests in a child process (the DEBUG line, and no banner on import); an error frame becomes a
  `TransportFailed` or `ProviderFailed` event and a log line with no content; the file-fed
  transport plays 60 s of frames within 100 ms of real time (the agent's tolerance); every aiortc
  peer it builds has no ICE server.

**Track F · `api`, the CLI and `examples/minimal` (library).**
- Goal: `VoiceRuntime` and its lifespan, the lock file, the router, the offer secret, CORS, the
  error shape, `serve()`, `combine_lifespans`, `t2v`, and the minimal example as an echo agent.
- Owns: `api/runtime.py`, `api/lockfile.py`, `api/router.py`, `api/offers.py`, `api/http_errors.py`,
  `api/server.py`, `api/cli.py`, `api/doctor.py`; `examples/minimal/src/minimal_example/`; tests under
  `api/` and `tests/minimal_example/`.
- May read: the protocol models, the ports, the adapters' signatures, `voice`'s entry point as
  Block 0 defines it, Pipecat's request handler as Block 0 read it.
- Tests, with the fake `voice` entry point (the real call is step 16's): the acceptance criteria's
  set-up cases (the offer secret in a header or the body only, a PATCH after ICE completed,
  `/health`'s fields, `/dev` and `DevIdentity` refusing any `env` but `dev` before the client's
  address is read); `serve()`'s telemetry off and its proxy headers; every `prod` check in
  `staging`; the lock file across two processes; `--help` for each `t2v` command, importing no
  Pipecat; `t2v doctor --synthesize` against a fake.

**Track G · The browser client, the widget and the Ole5 app's server.**
- Goal: `t2v-client.js`, `dev.html`, Ole5's widget, and the app's server: its settings
  (`OLE5_VOICE_` for its own, `T2V_` for the library's, the design's 7.3), its own `FastAPI` object
  with FastAPI's telemetry off and its CORS, uvicorn run with proxy headers trusted only from
  `server.forwarded_allow_ips`, its token route (Q4, with the guard Q4 settles), and its static
  files with the widget page's headers.
- Owns: `api/static/t2v-client.js`, `api/static/dev.html`; `apps/ole5-voice-agent/web/`;
  `apps/ole5-voice-agent/src/ole5_voice/settings.py`, `server.py`, `token_route.py`; tests
  `tests/ole5_voice/test_server.py`, `test_token_route.py`; `.claude/launch.json`.
- May read: the protocol models; the recorder's page (`ole5_voice/evals/recorder_page/`: its consent
  screen, capture with echo cancellation, its microphone errors); the prototype's `web/voice.js`
  (starting audio inside a click, the microphone error map), read only.
- Tests: the token route's adversarial cases (a wrong code, compared in constant time; repeated tries
  from one address slowed, the address taken from `X-Forwarded-For` only from a trusted proxy; the
  hourly cap on failed tries; an access code under 16 characters refused at settings load; consent
  passed through into the token, never taken from a later message); each header of the widget page
  and of `/dev`; no `innerHTML` or its kin in any script (the browser criteria); a global tracer,
  meter and logger provider receives nothing from the Ole5 app's FastAPI; the page checked by the
  agent in its browser pane and by the owner in Chrome and in Edge (step 18).

**Track H · The measurement's tooling (library `testing`, app `evals`).**
- Goal: `poe eot`, the timing run, the recorded calls' manifests, and what runs R5 to R7 need.
- Owns: `testing/turns.py`, `testing/echo_timing.py`; in `apps/ole5-voice-agent/src/ole5_voice/evals/`,
  `eot.py`, `timing.py`, `call_manifests.py`, and the changes to `answerers.py` (split first,
  TD-019), `compare.py` (`--allow-setting`, TD-026), `runs.py` and `history.py` (the new run kinds);
  the poe tasks `eot` and `eval-timing` (asked of the integrator); tests under `tests/ole5_voice/evals/`
  and `testing/`.
- May read: the registration below, evaluation.md's "Running", the file-fed transport's interface
  as Block 0 defines it.
- Behaviour: each step timed with `time.perf_counter`; the padding, the fresh call per variant, the
  timed turn and the pacers as the registration says.
- Tests: the `reference` answerer of `poe eot` at 0 cut-offs and 0 ms; the scorer on hand-made
  decision sequences (a cut-off, a miss, a late end, a variant cut into two turns); the pacers
  holding 10 Whisper and 5 Orpheus requests a minute; a timing run refusing the main checkout and a
  dirty tree; held-out writing aggregates only.

**Track I · The guide.**
- Goal: the pages of the acceptance criteria, and the library's `README.md` brought to M2.
- Owns: `docs/guide/README.md` and the new pages under `docs/guide/`;
  `packages/t2-agentic-voice/README.md`.
- May read: the design's 3, 4, 10, 11 and 14; every track's signatures; the generated settings
  reference.
- Content beyond the design's 14: `serving.md` tells a team that mounts the router to turn
  FastAPI's telemetry off and set CORS on its own app, and to trust proxy headers from its proxy
  only; `data-and-privacy.md` says how long Phoenix keeps transcripts (Q7).
- Tests: `poe docs`, which also checks that a code sample after a link to a `.py` file is a run
  of that file's lines (DOC-SAMPLE, D-027).

**Reviewers, by concern.** Each reviews every track for its concern; each finding is checked by an
agent told to refute it before it is acted on.
- **Security:** invariants 1, 5, 7 and 8; data-channel input parsed strictly (the browser is not
  trusted, SECURITY.md's trust boundaries); the offer secret, the TURN secret, the join keys and the
  access code, each held to its minimum length; CORS; the token route and the guard on the shared
  key; recordings gated by the setting and the token, never by `DevIdentity`; the phrase cache and
  the report file holding no call content; the widget page's headers and captions as text; Phoenix
  never public; no `.env` read; FastAPI's telemetry off in both shapes; no aiortc
  peer reaching a STUN server; and, at step 19, the image and its `.dockerignore`, the compose
  file's ports, and the coturn and proxy templates.
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
  Pipecat's timers run as in a call. Each variant is fed as a fresh call (the models loaded once per
  run), with 1 s of digital silence (zeros) before the clip and 4.5 s after it, the same for every
  variant: the dev paused variants end 0.20 to 0.80 s after their labelled end (their WAV headers,
  measured on 2026-11-02 by the feasibility review), so the padding covers the 4 s miss window and
  Smart Turn's 3 s fallback after a VAD stop, and nothing is a miss for want of audio. Real-time
  pace is kept against `time.perf_counter` deadlines; Pipecat's own timers run on asyncio's clock,
  which ticks at about 15.6 ms on Windows under Python 3.12 (the decision log), so the delays have
  that resolution unless the spike (step 5) shows otherwise. E2 is the same run again.
- **Metrics, per variant:** a **cut-off** when the first turn end falls more than 300 ms before the
  labelled end (the agent's tolerance for a mark clicked on a waveform); a **miss** when no turn end
  comes within 4 s after it; the **end-of-turn delay**, from the labelled end to the turn end, for the
  rest; and its parts, the **VAD stop delay** (to Silero's stop) and **Smart Turn's decision** (from
  that stop to the turn end). Reported: cut-offs and misses by variant and by item; the delay's median
  and 90th percentile (Hyndman and Fan's type 7, as plan 002); by language and by device. For the
  secondary set, whose reference end is Silero's own, only cut-offs, misses and Smart Turn's
  decision are reported: its VAD stop delay would measure Silero against itself.
- **The reference answerer** returns each labelled end as the turn end: 0 cut-offs, 0 ms, inside
  `poe check`.
- **The noise:** decisions that differ between E1 and E2, counted; the agent expects few or none
  (the same frames, the same models), with timing near a threshold the possible source.
- **Rule:** no default moves in M2 (Q14). E1 is the baseline M3 tunes against. If the owner picks
  Q14's (b) or (c), its arms, its data and its keep rule are registered as a dated amendment
  before E1.
- **Expected (the agent's):** some cut-offs on the Arabic paused requests: the owner's pauses run
  about 0.83 s (`Ole5-chatbot/VOICE_LOG.md`, line 51, the prototype's D43), far past the 200 ms VAD
  stop, so each pause reaches Smart Turn, whose v3.2 benchmark gives Arabic 89.76% (6.97% false
  positives) against English 94.26% (3.75%)
  (huggingface.co/pipecat-ai/smart-turn-v3/raw/main/benchmarks/smart-turn-v3.2-cpu.md, read
  2026-11-02 by the research step; its Arabic dialect, and what its false positive means, are
  UNVERIFIED). Delays near 200 ms plus Smart Turn's inference when it says the turn is complete, and
  up to 3 s when it says it is not.
- **Cost and time:** none in money. At real-time pace with the padding: about 4 minutes for the paused
  requests (1.86 minutes of audio and 23 × 5.5 s) and about 27 for the secondary set (8.61 minutes
  of audio in 202 variants and 202 × 5.5 s; the lengths from the WAV headers, by the feasibility
  review), so E1 and E2 take about an hour.

**T · The time of each step on the golden set (spends)**

- **Data.** The 23 dev paused-request variants: 19 for the Arabic model (Saudi 11, MSA 4, mixed 4)
  and 4 for the English one.
- **Arm T1.** The echo on the file-fed pipeline at real-time pace with the real `GroqSTT`
  (`whisper-large-v3`, the item's label as the session's language, as `stt.live_language = "session"`
  sends it, Whisper cut as step 12 records: per user turn, the agent's proposal) and `GroqTTS`
  (Q5's voices), the frame cached before the run (its requests counted), trim off, untraced, with
  E's padding and a fresh call per variant. Between variants the runner waits until its pacers
  allow the next: at most 10 Whisper requests and 5 requests per Orpheus model in any minute (the
  decision log). T2 is the same run again, on the same commit.
- **The timed turn:** per variant, the first turn that ends at or after its labelled end minus
  300 ms (E's tolerance). A variant cut off into two turns or more is reported apart, with the count
  of such variants, and left out of the medians.
- **Metrics, per variant, in ms** (each timed on `time.perf_counter`, at about 16 ms resolution for
  Pipecat's own steps, as E says): the VAD stop delay; Smart Turn's decision; Whisper's request (sent
  to answered; if Whisper is cut per segment, the last segment's, the one the turn waits on); the
  echo's text ready; Orpheus's first byte (sent to the first audio byte); its leading silence (to the
  first sample above the noise floor); the time to first audio (the labelled end to the cached
  frame's first frame) and to the heard words (the labelled end to Orpheus's first sound). Also:
  requests, billed seconds and characters per model, and the remaining requests and tokens Groq
  reports after the smoke request, which show what a TTS token counts (Q17). Medians and 90th
  percentiles by step and language; the median's change between T1 and T2 is the timing's noise. No
  keep rule: these numbers feed M3's and M4's targets (the design's 10.3).
- **Expected (the agent's):** Whisper near large-v3's medians of 271 and 323 ms (plan 002's R3 and
  R1), the process's first request slower without the lifespan's warm-up (run P's 1,258 ms, TD-012); Orpheus's
  first byte near the prototype's 249 ms (Arabic) and 262 ms (English) with connections kept open (the
  research step's count over five prototype logs in `voice-lab/`); a leading silence of 0.4 to 0.7 s
  (`Ole5-chatbot/VOICE_LOG.md`, line 34, the prototype's D25).
- **Cost,** budgeted at up to two turns a variant (a cut-off splits one in two) and, if Whisper is
  cut per segment, up to three Whisper requests a variant: per run, Whisper up to 70 requests at the
  10 s minimum = 700 s = 0.194 h × $0.111 = $0.022; Orpheus Arabic about 19 × 55 characters plus the
  frame ≈ 1,100 characters (a cut changes the requests more than the characters) × $40 per million
  = $0.044; English about 4 × 60 = 240 × $22 per million = $0.005 (prices:
  console.groq.com/docs/model/canopylabs/orpheus-arabic-saudi and .../orpheus-v1-english, read
  2026-11-02 by the research step). About $0.07 a run, $0.14 for both.
- **Limits** (console.groq.com/docs/rate-limits, read 2026-11-02 by the research step and the
  agent): up to 40 Arabic and 8 English Orpheus requests a run, the smoke's and the frame's
  included, so T1 and T2 take up to 80 of the published 100 a day for the Arabic model, with the
  pacer under its 10 a minute. Each Orpheus model also has a published 1.2K tokens a minute and
  3.6K a day; what a TTS token counts is UNVERIFIED (the page does not say): if it is one character,
  T1 and T2 take about 2,200 of the Arabic model's 3,600, and a run's minute stays under 1.2K at 5
  requests of about 60 characters. Whisper's 700 billed seconds a run sit far inside its published
  7.2K audio seconds an hour. So T runs on a day with no call (step 27, Q17).

**L · The live language, and the noise on another day (spends)**

- **Arms.** A1 as plan 002 registered it (`whisper-large-v3`, the item's label as the language, no
  prompt, temperature 0, `verbose_json`, `--timeout-s 6`); A3, the same with `--language-hint auto`,
  so no language is sent.
- **Runs,** on the dev split (66 items, 231 variants), at one measurement commit, on a day other than
  2026-11-01: R5 (A1), R7 (A3), R6 (A1), in that order, so drift over the session falls on both arms.
  R5 against R6 is the noise on another day (TD-032); R7 against R5 is the comparison, and R7 against
  R6 its replication. The runner's settings are plan 002's as amended (`--max-attempts 4`,
  `--variant-timeout-s 120`, `--max-rpm 10` until Q17, `--price-per-hour 0.111`, `--cap-usd` from
  step 23), each on the command line. A run starts at least 15 minutes after the last one ended,
  and no other Whisper use (a T run, a call) falls within the hour around a run, so no hour holds
  more than about 5,000 billed seconds against the published 7.2K audio seconds an hour for
  `whisper-large-v3` (console.groq.com/docs/rate-limits, read 2026-11-02; whether billed or sent
  seconds count is UNVERIFIED); the three runs bill about 7,300 s, inside its 28.8K a day.
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
  about $0.23; at 10 requests a minute, about 23 minutes a run, and about 100 minutes for the three
  with the pauses.

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
  browser); the candidate type, for a relay its protocol and port, and the time to connect; whether
  the owner heard the turn back (after each call, the owner names any turn that did not come back,
  and the agent checks it against the call's trace and timeline). Reported per call and as medians
  over the calls.
- **Recorded:** the requests per call minute per model, beside the key's real limits (Q17), as a
  decision entry for M6.
- **Cost (the agent's estimate):** a turn every 10 s or so is about 6 Whisper requests a minute with
  Whisper cut per turn, up to about 12 with cut-offs, and up to about 20 for a caller who pauses
  often if it is cut per segment, against the published 20 a minute; each is billed 10 s, so 60 to
  120 billed seconds a minute ≈ $0.002 to $0.004; and 6 Orpheus requests of about 60 characters
  ≈ $0.014 a minute in Arabic; eight calls of three minutes ≈ $0.45. **The limits, not the money,
  bind:** at the published 100 requests a day per Orpheus model, about 6 requests a minute leave
  roughly 16 call minutes of Arabic a day; at its published 3.6K tokens a day, if a token is one
  character (UNVERIFIED), about 360 characters a minute leave about 10. The lower holds until Q17's
  reading says otherwise, so C's calls span about three days, none on T's day, unless Groq raises
  the limits (Q17).

**The budget** (the agent's arithmetic): L $0.23, T $0.14, C about $0.45, the first local calls and
the network-test calls about $0.05 each, and Q16's prompt arm $0.075 if it runs in M2: about $1.00 in
all; `t2v doctor --synthesize` adds a fraction of a cent each time it runs. Whether a refused request
is billed is UNVERIFIED (TD-021), and retries add requests.

**Words the questions use**

- **VAD** (voice activity detection; Silero here): finds where speech starts and stops in the
  audio. **Smart Turn:** a small model that judges, at each pause, whether the caller has finished.
- **ICE:** how the browser and the backend find a network path for the call's audio. Each address
  it tries is a **candidate**: a *host* candidate is the machine's own address, *srflx* the address
  a home or office router shows the outside, *relay* an address on a TURN server.
- **STUN:** a server that tells a machine its outside address. **TURN:** a relay server that
  carries the call's audio when no direct path works. **TURN over TLS on 443** looks to a network
  like ordinary secure web traffic, the one kind most closed networks let through.
- **SNI routing:** a proxy reads the name a secure connection asks for and passes the connection,
  still encrypted, to the server of that name, so two services can share port 443 on one address.
- **Sink** (loguru): where a logger writes; loguru's default sink prints to the screen.
  **`NullHandler`:** a standard-library handler that drops records until the app adds its own.
- **D-024's floor** (c = 6): with the noise measured, a change counts only if at least 6 more items
  get better than worse.

**Open questions, each settled before the step it gates**

The owner's call before Block 0:

- **Q1. The dependencies and their licences.** *Settled on 2026-11-02: (a), and eot-bench is not
  added.* May the agent download and install "Dependencies to install" (several hundred megabytes in
  all, the agent's estimate, UNVERIFIED), and accept the copyleft licences that come with them, each
  used unmodified, as certifi's MPL-2.0 was (plan 002, Q1)? They are: soxr (LGPL-2.1-or-later),
  soundfile's bundled libsndfile (LGPL-2.1), the FFmpeg that OpenCV's wheels bundle (LGPLv2.1), tqdm
  (MPL-2.0 and MIT), and the FFmpeg inside PyAV's wheels, likely GPL since x264 and x265 are built
  in (UNVERIFIED). Why: D-016 asks the owner's approval for a copyleft licence, and the design's 13
  list did not name these. Options: (a) accept them all, used unmodified; aiortc needs PyAV, so
  there is no WebRTC in the backend without it; (b) accept all but PyAV's wheel and build PyAV from
  source against an LGPL FFmpeg, which needs a compiler and FFmpeg's development files on Windows
  and in the image, a large cost; (c) review each one. **The agent recommends (a):** the library
  never ships these binaries itself, each team installs them from PyPI, and the use is inside T2; if
  an image holding them is ever given outside T2, ask T2's legal team first. The agent is not giving
  legal advice. The same approval covers the Ole5 app's own command, which adds no package the
  library's does not; a constraint keeping `aioice` below 0.11, if the spike finds 0.11.0 misbehaves
  (step 5); and, for the owner to confirm, that eot-bench is not added (the decision log).
- **Q2. Who switches Pipecat's own log messages off, and where they go when a team wants them.**
  *Settled on 2026-11-02: (a).* Pipecat writes its log through loguru, one logger shared by the
  whole process, and its debug lines can hold what the caller said. The library's own logging is
  settled (the owner's answer of 2026-11-02, step 8): standard-library loggers under
  `t2_agentic_voice` with a `NullHandler`, so nothing prints until an app configures logging. Still
  open, because the approved design and the roadmap disagree on it: who owns loguru, and what it
  does by default. Options: (a) the design's 10.2 and 12.2 (change 3): `voice` owns it; Pipecat's
  namespace is switched off with `logger.disable("pipecat")` when `voice` is first imported, before
  Pipecat prints its import banner (a small step past the design's "at runtime start"), and again at
  runtime start; `logging.pipecat = "forward"` re-enables it and forwards Pipecat's WARNING and
  above to `t2_agentic_voice.pipecat`; no sink is added or removed; (b) the roadmap's M2 bullet,
  D-002 and ARCHITECTURE.md's conventions: `core` owns it, and `configure_logging` removes loguru's
  default sink and forwards its records, a change to a process-wide logger a team's own code may
  use. Either way D-002's bullet, the roadmap's M2 bullet, ARCHITECTURE.md and GP-03's last clause
  change with a decision entry. **The agent recommends (a):** a teammate's process keeps its own
  loguru sinks, which the design's personas say would otherwise end an evaluation, and invariant 8's
  test holds either way.
- **Q3. The echo's shape.** *Settled on 2026-11-02: (a) and (i).* The design names "the voice
  session in echo mode" and `examples/minimal` "as an echo use case" (its 16.1), but not their
  public form, which is a design choice. Options: (a) `VoiceAgent(name,
  languages=[Language.saudi_arabic(greeting=...), ...])` built in M2 with only these fields, and a
  setting `session.mode`, with `echo` its only value in M2; M4 adds `talker`, and the talker's
  fields arrive as optional arguments, so echo stays a teammate's first audio check; (b) a runtime
  argument, `VoiceRuntime(agent, echo=True)`, which M4 would have to deprecate; (c) an internal
  stand-in with no public form, removed in M4, which leaves `examples/minimal` nothing to show. And
  its words: (i) a frame before the heard words, «سمعتك تقول: …» and "I heard: …", or (ii) the words
  alone. **The agent recommends (a) and (i):** the frame says the words are the caller's, so the
  echo never sounds like the agent answering or claiming an action (invariant 2), and as a cached
  phrase it plays as soon as the transcript is in. Speech heard while the echo plays is not said
  back (the decision log), so on speakers the agent never echoes itself.
- **Q4. Who reaches the deployed echo, how the owner's calls get a join token before open question
  19 is answered, and what guards the shared key meanwhile.** *Settled on 2026-11-02: (a) and (i).*
  `DevIdentity` serves only `dev` on loopback, and the recording consent must ride in a signed token
  (invariant 8). Options: (a) the Ole5 app's own token route mints a `SignedJoinTokens` token only
  for a caller who types an access code the owner sets (a secret setting of at least 16 characters,
  generated with the agent's command; compared in constant time; repeated tries from one address
  slowed, and at most 20 failed tries an hour in all, after which the route refuses until it
  restarts), so only the owner calls, from any network; (b) wait for open question 19, so the
  deployment waits on the website team; (c) a token minted on the laptop and pasted into the page,
  which lives at most 120 s (the design's 6.5), too short to carry to a phone; (d) open to anyone,
  set aside: Groq spend and limits, and no identity at all. And a guard, since M2 puts on the
  internet a backend that spends T2's one shared key while the limits wait for M6, and an access
  code that leaks, or a tab left open, holds calls (SECURITY.md's threats: "endless calls, very long
  calls"): (i) the token route mints at most 10 tokens a day; the library builds two keys of the
  design's 7.6 `limits` group early, `max_call_s` (its default, 600) and `idle_s` (the agent's
  proposal, 120), so a call ends after 10 minutes or after 2 minutes with no turn (an app cannot end
  a call itself: observers cannot change behaviour, the design's 6.6); the owner runs the backend
  only during call sessions; the access code is rotated after run C; and the risk left is a debt row
  for M6; (ii) only the last three, with no limit in code. **The agent recommends (a) and (i)**, (a)
  replaced by 19's answer when it comes (Q12).
- **Q5. The voices and the register.** *Settled on 2026-11-02: `abdullah` and `troy`, and (a).*
  Which Saudi voice: `abdullah` (the default, as an "Apr 18" entry of Groq's changelog says, with no
  year shown: console.groq.com/docs/changelog.md, read 2026-11-02 by the plan review; the
  prototype's pick), `fahad`, `sultan` (male), `lulwa`, `noura`, `aisha` (female); which English
  voice: `troy` (the prototype's pick), `austin`, `daniel` (male), `autumn`, `diana`, `hannah`
  (female) (Groq's Orpheus page, console.groq.com/docs/text-to-speech/orpheus, which names both
  models' voices, read 2026-11-02 by the research step and the plan review). Samples of `abdullah`,
  `fahad`, `sultan`, `noura`, `troy`, `austin`, `autumn` and `daniel` are in `voice-lab/voices/`, so
  no new request is needed to listen. And the register of M2's fixed phrases (the greeting, the
  frame, the notices): (a) Saudi dialect; (b) plain MSA. Why: the voices are the library's
  documented defaults and Ole5's settings (the design's 3.3, "chosen in M2"), and only the owner can
  judge them. **The agent recommends `abdullah` and `troy`, as library defaults and for Ole5, and
  (a)**, the talker's register being M4's with its prompts. Needed before Block 0 writes the
  defaults; it can wait until the first live call if the owner wants to listen first.
- **Q6. The word "stop" in the library's source.** *Settled on 2026-11-02: (a), with the labels
  «إيقاف» and «أوافق».* The design names the protocol's `stop` message and the client's
  `call.stop()` (its 4.5 and 5.5), and the golden set has "stop" as a stop-word item;
  `test_no_item_in_source.py` fails on it in any string or JS file under `packages/`, unless
  `allowed_in_source.toml` lists it, which only the owner's ruling adds. Options: (a) one entry,
  "stop", for the protocol's message and method names, which no model or caller hears; (b) rename
  them (a `halt` message and `call.halt()`), so the list stays empty, the protocol departing from
  the design's names. The item whose whole text is "stop" (`k05_stop`) is in the held-out split: the
  entry exempts that one reference everywhere, while longer references holding the word, such as
  "stop, please" (`n34_halt_please`), stay searched. The widget's labels come under the same test,
  its folder now scanned (step 6): the Stop button and the consent screen's yes would equal items in
  Arabic («وقف», «نعم»), so the agent proposes labels that are no item («إيقاف» and «أوافق»), the
  English "Stop" being covered by (a)'s entry. **The agent recommends (a)** and those labels, noting
  that (a) also lets "stop" into M3's stop-word presets unflagged, so M3's plan rules on those
  presets explicitly.

The owner's call before the deployment (and, for Q7, before the first recorded call):

- **Q7. The consent screen, and keeping the recordings.** The widget shows a consent screen before
  the microphone opens and passes its version and the recording choice to the token (the design's
  3.2). Options for the wording: (a) the agent drafts it in Arabic and English for the owner's own
  test calls, version `m2-owner-test-1`, with a separate box for recording, and the owner approves or
  rewrites it, in the owner's words as plan 002's consent was; the wording customers see comes from
  T2 before any customer uses the widget; (b) the owner or T2 writes the customer wording now. For
  the recordings: (i) copied from the host to the owner's machine under `var/` after each session,
  then deleted on the host, and kept until the owner deletes them, as the golden set's audio is;
  (ii) kept on the host's `var_dir`. For the transcripts in the host's Phoenix (on by default, the
  design's 10.1), which Phoenix keeps forever unless told otherwise
  (`PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` defaults to 0, infinite:
  arize.com/docs/phoenix/self-hosting/configuration.md, read 2026-11-02 by the security review):
  (iii) a retention of N days on the host (the agent's proposal: 30); (iv) kept until the owner
  deletes the project. **The agent recommends (a), (i) and (iii):** the audio stays on the owner's
  machine, as invariant 8 and the golden set have it, and the transcripts stay in the host's Phoenix
  for 30 days; the value goes into step 19's compose file and `data-and-privacy.md`.
- **Q8. The host.** *Settled in part on 2026-11-02: this machine for now, with Phoenix as M1's on
  127.0.0.1, no SSH tunnel and no authentication ("The owner's decisions"); the rest is re-planned
  with the deployment before step 19.* Where the backend and Phoenix run, and its facts: the host
  and its operating system; the backend's domain name; the reverse proxy that ends TLS (nginx,
  Caddy, Traefik or another), and whether it can pass a TLS connection on by name (SNI) without
  ending it; Docker or not; its public IP address, whether it has a second public IPv4 address, and
  which ports can be opened; whether its outbound traffic must go through a proxy (TD-004); who runs
  commands on it (the agent never logs in). The second address and the SNI pass-through decide Q9's
  (a). **The agent recommends:** one container for the backend with `var_dir` on a volume, and
  Phoenix as a second container on 127.0.0.1 only, with auth on, its API key given to the backend as
  a file, and a persistent volume, viewed through an SSH tunnel, never public (the design's 11,
  SECURITY.md's trust boundaries).
- **Q9. The media path for the network test.** Callers on networks that let through only web
  traffic need a relay server (TURN) that carries the call's audio over the same port as secure web
  pages (443): where should it run? aiortc's ports cannot be pinned and it offers no TCP candidates
  (the decision log), so a caller on a network that blocks UDP needs TURN over TLS on 443. Options:
  (a) coturn on the owner's host as a small service, TURN over TLS on 443 through its own hostname
  and IP address, or through SNI routing at the reverse proxy (nginx's stream module with
  `ssl_preread` and Traefik's TCP routers route by name, while standard Caddy needs a plugin: the
  feasibility review's reading, UNVERIFIED), relaying to the backend on the same host (UNVERIFIED
  for aiortc: the design's 11), with per-call credentials from a shared secret; it needs its own
  DNS name and certificate; free; (b) a hosted TURN service, such as
  Cloudflare's Realtime TURN (TLS on 443; 1,000 GB free, then $0.05 a GB; IPv4 only, no TCP
  relaying, no relay to private addresses, so the backend must still take UDP from it, or allocate a
  relay itself, which is UNVERIFIED; developers.cloudflare.com/realtime/turn/faq/, read 2026-11-02 by
  the reviews): a new outside service that relays the call's encrypted media and receives the
  callers' IP addresses. Its credentials come from an HTTP call per credential to
  rtc.live.cloudflare.com with a bearer API token, not from coturn's shared-secret scheme
  (developers.cloudflare.com/realtime/turn/generate-credentials/, read 2026-11-02 by the security
  review), so (b) needs a second credential adapter at `/join` with its own timeout and failure
  event, the API token as a secret setting with its `_FILE` form, rtc.live.cloudflare.com added to
  the design's outbound hosts, and Cloudflare on SECURITY.md's trust boundaries; Track C's scope and
  the TURN criterion change before Track C starts;
  (c) UDP ports opened on the backend alone: the whole ephemeral range, or a container with a narrowed
  range (Pipecat's Docker example, UNVERIFIED behind Docker's address translation), which cannot pass
  the roadmap's test from a network that blocks UDP. **The agent recommends (a)** if the host can give
  coturn port 443 on a second address or through SNI routing, otherwise (b). Cost does not decide:
  about 0.4 MB a call minute each way (the research step's estimate, UNVERIFIED) is a fraction of a
  cent on any of them.
- **Q10. The website embed.** Which page, who embeds it, and whether customers can see it during M2.
  Options: (a) a test page on the website, not linked from it, holding an iframe of the backend's
  widget page with `allow="microphone"`, so CORS stays off; the widget page names the website's
  origin in its `frame-ancestors`, and if the website's pages send a Permissions-Policy header it
  must allow the microphone for the backend's origin (`microphone=(self "https://<backend host>")`),
  since a parent policy of `microphone=()` blocks it whatever the tag says (MDN's
  Permissions-Policy: microphone page, read 2026-11-02 by the security review); (b) the same page
  loading the widget's script, with the website's origin in `server.allowed_origins`;
  (c) the website's staging site; (d) the backend's own page only, which leaves "the widget embedded in
  the website" unmet (a `Deviation:` line). **The agent recommends (a)**, behind Q4's access code.
- **Q11. The network that blocks UDP.** Options: (a) a real network known to block UDP (T2's office
  or guest network, if it does); (b) the laptop's own firewall blocking all outbound traffic except
  TCP 443 and DNS, while on the phone hotspot, so the call can pass only by TURN over TLS on 443 and
  not by TURN on port 3478: a rule the owner adds and removes, since it changes the owner's security
  settings, with the commands from the agent; (c) both. **The agent recommends (c)** if such a network
  exists, otherwise (b).
- **Q12. Open question 19 at the deployment.** If the website team has answered: a login means the
  website's server mints the token (`SignedJoinTokens`, the claims in `serving.md`), website work for
  M4 or M5, with nothing more in M2; a one-time email code means `Authenticate` is built in M2 with an
  email-sending dependency of the app, a new outside service. If there is no answer by the deployment:
  (a) deploy with Q4's access code and carry 19 to M5, where ticket status first needs a verified
  identity (invariant 3); (b) hold the deployment until the answer. **The agent recommends (a)** when
  there is no answer.

The owner's call before the measurement runs, except Q13 and Q17, which come before the first live
call (step 18), since those calls spend the same money and limits:

- **Q13. The budget cap** for M2's paid runs and calls together, against the estimate of about $1.00
  ("The budget"). **The agent recommends $5**, the cap the owner set for M1 (the agent had
  recommended $2 then).
- **Q14. The turn defaults.** Should M2 change the settings that decide when the caller has
  finished speaking? With only 6 paused requests in dev and D-024's floor of 6, a change could be
  shown to help only if all 6 got better. Options: (a) measure only in M2 (E1 is the baseline), and
  tune in M3 after more paused requests are recorded; (b) the owner records more paused requests now
  (say 20 more lines, about an hour on the three devices), then M2 tunes on dev; (c) tune on the six
  now. (b) and (c) would be registered as a dated amendment before E1. **The agent recommends
  (a).**
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
- **Q17. The key**, before the first live call. Its real limits from the console
  (console.groq.com/settings/limits): for each Orpheus model the requests and tokens a minute and a
  day (published: 10, 100, 1.2K and 3.6K) and what a TTS token counts; for `whisper-large-v3` the
  requests a minute and the audio seconds an hour and a day (published: 20, 7.2K and 28.8K); whether
  Groq has been asked to raise Orpheus's limits (the owner's answer to the design's question 21);
  whether anything else uses the key during M2's runs and calls; and Ole5's share of it (D-018,
  question 11), which M6's limiter enforces. One live call may need about 6 to 12 Whisper requests
  a minute, and up to about 20 if Whisper is cut per segment ("C" above). **The agent recommends**
  pacing runs at half the key's per-minute limits while anything else might use it, as in M1, and
  holding C's call days apart from T's day while the published limits hold.
- **Q18. The call script.** The calls of "C" above, or fewer or more; with or without the Bluetooth
  headset. **The agent recommends the script as proposed**, the Bluetooth call included, so that M3
  has its recordings for the Bluetooth warning.

Every question above gates the run as well as its own step, so each is also the owner's call before
the run it touches.

## What the owner does

1. **Before Block 0:** answer Q1 to Q6 (Q5 may wait until the first live call).
2. **In Groq's console, before the first live call:** accept the terms of `canopylabs/orpheus-arabic-saudi`
   and `canopylabs/orpheus-v1-english` as the organisation's admin (the design's 3.2; the Arabic model
   refuses a request until its terms are accepted, as a third party quotes Groq's error), and tell
   the agent what the console showed, which is what step 30 corrects the design from; read the key's
   real limits at console.groq.com/settings/limits (requests, tokens and audio seconds, Q17) and give
   them to the agent; if they are as published, ask Groq to raise them (the design's question 21); a
   spend limit in the console is the owner's choice. The key itself stays where M1 put it (`.env` in
   the main checkout, or its file).
3. **The first local calls** (step 18): first answer Q13 and Q17, and Q5 if it waited. Then, from the
   main checkout, start the Ole5 app's dev server with the command the agent gives, open the address
   it prints in Chrome on this laptop, allow the microphone, and say a few lines on the laptop's
   speakers, then on the wired headset, pressing Stop and Esc during an echo; then the same in Edge.
   Say whether each turn came back, and whether the microphone, playback, Stop and Esc worked in each
   browser.
4. **The host, before the deployment** (steps 4 to 8 are re-planned with it for this machine):
   answer Q7 to Q12. Then, with the agent's deployment steps:
   - the backend's domain name in DNS and its certificate at the reverse proxy; if Q9 picks coturn,
     its own DNS name, its certificate and key as files on the host (and who renews them), and its
     second address or the proxy's SNI rule;
   - the firewall rules of step 19's port table: publicly only TCP 443 and, for coturn, its relay
     range of UDP ports, narrowed in its configuration, with 3478 over UDP and TCP only if the
     decision of step 22 keeps it;
   - the secrets as files on the host, never in the image or the repository, each made with the
     agent's command (32 random bytes or more for the join key and the TURN secret, at least 16
     characters for the access code): the Groq key, the join key, the TURN secret, the access code,
     Phoenix's secret and its initial admin password, and (step 5) Phoenix's system API key;
   - the code moved to the host only as `git archive` of the merged commit, never as a copy of a
     checkout; then the commands that build the image, check that it holds no `.env` or WAV file,
     and start the backend, Phoenix and coturn.

   The agent never logs into the host.
5. **Phoenix on the host:** log in once and change its admin password; create a system API key in
   its settings and put it in the host file the backend reads, before the first deployed call; view
   it through an SSH tunnel on a local port the laptop's own Phoenix does not use
   (`ssh -L 16006:127.0.0.1:6006 <host>`), never on a public port, since it holds call content
   (SECURITY.md, trust boundaries).
6. **The website embed:** send the website team the snippet from `browser-client.md` (the iframe
   with `allow="microphone"`, and the Permissions-Policy line if their pages send one) and the
   backend's address, for the page Q10 chose, and tell the agent when it is live.
7. **The calls** (step 21 and run C): with Q18's script, on each device and network; for the network
   that blocks UDP by the laptop's firewall (Q11), add the rule (all outbound traffic blocked except
   TCP 443 and DNS) with the agent's commands before the call and remove it after. Use the access
   code on the page; switch recording on at the host with the agent's command only for C's sessions,
   off after, and tick the recording box only in C's calls; stop the backend between sessions if Q4
   says so.
8. **After each session:** copy the call reports, and after a recorded session the recordings, from
   the host to `var/` on this laptop with the agent's command, then delete the recordings on the
   host (Q7).
9. **Before the measurement runs:** answer Q14 to Q16 and Q18, and say again whether anything else
   uses the key during the runs.
