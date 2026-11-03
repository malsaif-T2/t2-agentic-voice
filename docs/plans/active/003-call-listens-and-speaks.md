# 003 · A call that listens and speaks

Status: active · Milestone: M2 · Started: 2026-11-02

## Goal

Make the first real call ([roadmap](../roadmap.md), M2): the owner opens Ole5's widget in Chrome,
starts a call, speaks Saudi Arabic, MSA or English, and hears each turn said back, on the laptop's
speakers and on a headset, through the Ole5 app's dev server on this laptop (the deployment
moved out of M2: the owner, 2026-11-03). There is no talker yet: the agent says back
what it heard (echo mode). The call is built as a teammate would build one, on the library's public
API (D-013): Pipecat inside `voice` (its peer-to-peer WebRTC transport, Silero VAD and Smart Turn,
with our own speech bridges calling the ports), the `TextToSpeech` port and its Groq Orpheus
adapter with an Arabic and an English voice, `domain`'s rules for speaking numbers and IDs, signed
single-use join tokens, the router and `serve()`, the reference browser client and its protocol,
and the settings with a required `env` (the design's 16.1, M2 row). The plan measures what M2's
*Done when* asks, registered before any result and cut to the fundamentals on 2026-11-03 ("The
owner's decisions"): end-of-turn cut-offs on the golden set, offline; and the time of each step and
requests per call minute for each Groq model, from the traces and call reports of the owner's one
recorded call session in Chrome. That session is recorded with consent, so that M3's targets are
also checked on audio that came through WebRTC; the language a live call sends Whisper moved to M3.
Every number describes one speaker, the owner (D-006).

## Acceptance criteria

**The call** (the library)

- [ ] `t2_agentic_voice.ports` exports `TextToSpeech` and `AudioChunk` in the shape of the
  design's 6.1, and `IdentityVerifier` and `UsedTokens` as its 6.5 has them; each port that holds
  connections has `aclose()`.
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
  table), the clause splitter, which keeps every clause within the model's `max_chars`, cutting
  inside a word only a word longer than that, and the pronunciation map; Ole5's entries ("Ole5" said
  «أُولِي فايف» and "Oh-lee five", `Ole5-chatbot/VOICE_LOG.md`, lines 35 and 45, the prototype's D26
  and D37) are the app's data.
- [ ] `voice` runs one Pipecat pipeline per call: SmallWebRTC, Silero VAD and Smart Turn v3.2 on
  CPU with no torch, a speech-to-text bridge on Pipecat's STT base class that sends Whisper one
  request per user turn (the decision log; Block 0's read and spike confirm it can), Smart Turn's
  stop strategy with `wait_for_transcript` off so that a turn's end is the analyzer's alone, a
  text-to-speech bridge on `TTSService` with `TextAggregationMode.TOKEN`, and a session bridge that
  is a plain `FrameProcessor`. Pipecat's interruptions are off, and none of its LLM services,
  context aggregators or function calls is used (the design's 13). The session's modules import no
  Pipecat (ARCH-BAN).
- [ ] The voice session in echo mode says back each turn in the voice of its language (one voice per
  reply): the cached frame (Q3) plays once the turn's transcript is in, while Orpheus synthesizes
  the heard words; an empty transcript is said back as nothing and kept on the timeline. Speech that
  starts while the echo plays, or within 300 ms after it, is not said back (a test), so the agent
  never echoes its own voice. The Stop button, Esc and `hangup` act at once: after a `stop`, no
  audio frame of a reply it dropped is sent, a stop dropping every clause asked for so far, the
  greeting's and a queued notice's included (a test with a capturing output), and the session
  listens again.
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
  join token, offer secret, TURN secret or access code in any exported span, and no
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
  refused with a FIX line, on Windows and on Linux: M2 checks Windows, on this laptop, and the Linux
  case runs in CI once TD-001 is paid, or else in "The deployment, moved out of M2"), warms VAD,
  Smart Turn and the adapters without a request (TD-012), builds tracing inside the lifespan
  (TD-014), and closes every adapter.
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
  URL's port, which no M2 call shows, every call being local: the deployment's plan checks them;
  the time to connect; whether `echoCancellation` applied; when the first audio played). Captions
  and notices are inserted as text only (`textContent`): a test reads the client's, the dev page's
  and the widget's scripts and finds no `innerHTML`, `outerHTML`, `insertAdjacentHTML` or
  `document.write`.
- [ ] Ole5's widget in `apps/ole5-voice-agent/web/`: a consent screen before the microphone opens
  (Q7's wording and version: the agent's draft, `m2-owner-test-1`, with a one-line recording box),
  start and end, playback, captions, the Stop button and Esc, and a message for a microphone that
  is missing, busy or refused. Its page is served with a Content-Security-Policy
  (`script-src 'self'` with no inline script, and `frame-ancestors` only the website's origin, from
  an `OLE5_VOICE_` setting, and `'none'` while it is empty, as in M2, whose calls are local: the
  embed moved out of M2), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and
  `Permissions-Policy: microphone=(self)`, and `/dev` with `frame-ancestors 'none'`, each header
  tested. Checked in Chrome: the agent checks in its browser pane what needs no microphone (the
  page, the consent screen, the missing-microphone and refused messages, the data channel), and the
  owner checks the microphone, playback, Stop and Esc in step 18's recorded session, each result in
  the progress log. *Amended 2026-11-03 ("The owner's decisions"): Edge, supported (D-018, the
  design's open question 12), is not checked in M2, the roadmap's M2 naming Chrome only.*
- [ ] `.claude/launch.json` starts `t2v dev` on `examples/minimal` and the Ole5 app's dev server
  ([WORKING-RULES.md](../../../WORKING-RULES.md), "Seeing it run").

**The deployment** moved out of M2 on 2026-11-03 ("The owner's decisions"). Its five criteria, as
drafted, are in "The deployment, moved out of M2", for the plan that deploys to the owner's server;
every call of M2 is on this laptop.

**The recordings**

- [ ] The calls of the owner's recorded session (step 18) through the widget are recorded with
  `privacy.record_audio` on and the recording consent in the signed join token: per call, the
  caller's track, the agent's audio and the playback timeline, under `var_dir`. Only a consent from
  a verified signed token counts.
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
- [ ] Decision entries record what the design's 16.3 lists for M2 (settings; serving and identity,
  but for Ole5's identity answer, open question 19, which moved with Q12 to the deployment's plan;
  GP-22 widened to an adapter object passed in code), the library's logging contract (the owner's
  answer of 2026-11-02) with Q2's loguru answer (amending D-002's loguru bullet), ARCH-BAN and the
  new facades, the echo's shape (Q3), how Whisper is cut, the settings keys beyond the design's 7.6
  (as Proposed), SECURITY.md's invariants 7 and 8 brought to the design's 8.1 (amending D-007), and
  the measured requests per call minute; the language a live call sends Whisper moved to M3 on
  2026-11-03 ("The owner's decisions").

**The measurement** (the roadmap's *Done when* for M2)

- [ ] "The measurement, registered before any result" was complete, every owner's call settled and
  dated, before the run it affects: the runs left in M2, E1 and E2 and held-out E at the close, and
  the owner's recorded session, C; every departure is a `Deviation:` line in the progress log.
  *Amended 2026-11-03 ("The owner's decisions"): T and L left M2, their registered text kept, each
  with its amendment.*
- [ ] `uv run poe eot` measures end of turn offline, with no spend, on the golden set's paused
  requests: cut-offs and each step's delay, by language and device; its `reference` answerer scores
  0 cut-offs and 0 ms inside `poe check`.
- [ ] The time of each step is read from the owner's recorded session (step 18), whose calls'
  reports and traces record each turn: from the end of the caller's speech (Silero's last stop) to
  its transcript (`stt_ms`: Smart Turn's decision and Whisper's request together); Whisper's
  request, sent to answered (its speech-to-text span, with the audio seconds sent and billed); to
  the echo ready (`ttfa_ms`, the cached frame's first audio queued, not yet heard: TD-063); and the
  echo's Orpheus request to its first audio queued (`tts_first_audio_ms`, the text-to-speech span's
  `tts.first_audio_ms`). Per call, the report holds the time to connect and from connecting to the
  first audio played (`client_stats`), and the recording's timeline holds when each clause played in
  the browser (approximately: TD-070). The VAD stop delay and Smart Turn's decision alone are E1's,
  offline. *Amended 2026-11-03 ("The owner's decisions"): runs T1 and T2, the time of each step on
  the golden set, are dropped.*
- [ ] Requests per call minute for each Groq model, from the owner's recorded session (each call's
  report and root span hold them), are recorded as a decision entry, beside the published limits, or
  beside the key's real limits if the owner reads them (Q17, optional since 2026-11-03).
- *Moved to M3 on 2026-11-03 ("The owner's decisions"): the language a live call sends Whisper, set
  by the registered rule (runs R5 to R7), and the noise on another day (TD-032), with Q15. M2 keeps
  `stt.live_language`'s default, `session`.*
- [ ] The owner held the calls of *Done when* in one recorded session (step 18): in Chrome, on the
  laptop's speakers and then on the wired headset, through the Ole5 app's dev server on this laptop,
  each turn heard back, Stop and Esc each pressed once during an echo. *Amended 2026-11-03 ("The
  owner's decisions"): Edge dropped, the roadmap's M2 naming Chrome only.*
- [ ] `uv run poe check` passes; the roadmap's M2 row, CLAUDE.md, ARCHITECTURE.md, SECURITY.md and
  this plan's logs are up to date.

## Plan

**Scope.** M2 is the roadmap's M2 and the design's 16.1 M2 row, without the deployment and with no
talker: every call is on this laptop, and the voice session runs in echo mode.
**Left for M3:** the two-step interruption, `duck` and `unduck`, cancel scopes,
the history of what was heard, the stop, listening and echo rules and their presets, the filter
for text from silence and echo, the first window, tuning the turn defaults (Q14), `AudioCall` and
the parity test (the design's 9.5; M2 builds only an internal file-fed transport, the decision
log), the push-to-talk fallback and the Bluetooth warning, and, since the owner's ruling of
2026-11-03, the language a live call sends Whisper and the noise on another day (runs R5 to R7, Q15,
TD-032). **M4:** the talker, the chat-model port, the vocabulary and the Whisper prompt (Q16,
settled on 2026-11-03), `TextCall` and the fakes as a public kit, the latency target. **M5:**
speaking dates, SECURITY.md generalized from tickets to actions (the
design's 16.3), and the verified identity ticket status needs, if open question 19 is still
unanswered (Q12, now in "The deployment, moved out of M2"). **M6:** the per-model limiter and the
cool-off, admission control and the busy notice, drain, the full `t2v doctor`, the deployment guide
and runbook, CPU per call. **The deployment** (the owner's host behind HTTPS, the calls from other
networks and from one that blocks UDP, the media path, TURN credentials, Phoenix on the host and
the website embed): a plan of its own as soon as the owner has access to the server, whichever
milestone is then in progress, and at the latest in M6 (the owner, 2026-11-03); its text, as
drafted, is in "The deployment, moved out of M2". **M0** keeps
CI (TD-001), `contract.md` and the app's five layers (the decision log). The public-API snapshot
(griffe) and the wheel job wait for the first teammate tag (the design's 3.1 and 13).

**From M1** (the roadmap's M2 bullet, from [plan 002's Future
improvements](../completed/002-golden-set-baseline.md#future-improvements)):
- **The prompt arm for product terms** is Q16, settled on 2026-11-03: M4, where the vocabulary that
  becomes the prompt lands (the design's 3.1 and 3.3).
- **The language a live call sends Whisper** moved to M3 on 2026-11-03 ("The owner's decisions"),
  with its runs R5 to R7, after the noise on another day (TD-032), and Q15; M2 keeps
  `stt.live_language`'s default, `session`.
- **Spoken numbers:** Track A speaks digits as words with num2words. TD-031, reading compound
  number words as digits when scoring, stays open: num2words turns digits into words, never words
  into digits, and none of large-v3's 11 ticket misses held a number in words (plan 002's Future
  improvements).

Blocks in the order they depend on each other. Each is built in its own worktree under
`.claude/worktrees/`, reviewed by one agent that did not write it, each finding checked by one
skeptic, fixed, gated with `uv run poe check`, and merged, with commits named
`Plan 003: <what>`. Block 0 is built by one agent and merged before any track starts; the tracks
are built in parallel against Block 0's interfaces and fakes, each reviewed the same way
(`## Tracks`), and merged through an integration branch, `plan-003-integration`
([plans README](../README.md), "Parallel tracks"). From 2026-11-03 ("The owner's decisions"), a
review (Block 0's last round, each track's, and step 17's, dropped on 2026-11-03) reports only what
would break, hang or crash a call; garble, cut, overlap or lose its audio; leak a task, connection
or memory per call; send Groq more than the limits allow or fail on a 429 it could wait out; refuse
valid Arabic or English text; or leave a later track or milestone a contract it cannot build on.
Everything else becomes a row in `docs/plans/tech-debt.md`, and there is no second fix round unless
a high finding stands.

**Before Block 0**

1. The garbage-collection round ([plan 004](../completed/004-garbage-collection-1.md)) merged into
   the main branch on 2026-11-02 (750d90a), so Block 0 is cut from a main branch that holds its
   fixes: the base error is `T2VoiceError`, with `AppError` a deprecated alias (D-026); the library
   declares httpx, `scripts/harness_config.py` is split, and ARCH-DEPS refuses an import its project
   does not declare and DOC-SAMPLE a guide sample that is not its source's lines (D-027, Accepted
   2026-11-02); the library's logging is step 8. This plan's text was brought up to date at that
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
   helper an app calls, writing to a stream it can choose; this step pays that debt. `voice` owns
   loguru (Q2).
9. **Errors.** `JoinRejected`, on the base error `T2VoiceError` (D-026); the
   code list in `tests/t2_agentic_voice/core/test_errors.py` grows with it.
10. **Interfaces, with stubs that raise `NotImplementedError`** (a test per stub, in the test file
    of the track that owns it, as plan 002 did):
    - the ports: `domain/ports/text_to_speech.py` (`TextToSpeech`, `AudioChunk`) and
      `domain/ports/identity.py` (`IdentityVerifier`, `UsedTokens`), and `aclose()` on
      `SpeechToText` (the decision log);
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
    The second fix round ran long, so the owner ruled on 2026-11-03 ("The owner's decisions"):
    Block 0's round 2 drops the harness builder (more loader forms in the architecture checks) and
    the full recheck, and what round 2 found for the harness builder is a row in
    `docs/plans/tech-debt.md` (TD-049); Block 0's last round has one reviewer, each finding
    checked by one skeptic, and reports only what the rule of "Blocks in the order they depend on
    each other" names.

**The tracks** (in parallel, after Block 0; each track's files, reads and tests are in `## Tracks`)

14. Track A: speech text. Track B: the Orpheus adapter and the phrase cache. Track C: identity
    and stores. Track D: the voice session in echo mode, its usage, spans and
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
    `TextToSpeech`; `poe eot --answerer reference --split dev` scores 0 cut-offs and 0 ms. It also
    checks what no track could check alone (the decision log, 2026-11-03): the phrase cache's folder
    holds no new file after an echo turn, no join token, offer secret or access code is in an
    exported span, and a token the Ole5 app's `/token` mints is verified at `/join`, its consent
    recording only with `privacy.record_audio` on. By hand: the agent starts `t2v dev` on
    `examples/minimal` with fake providers and opens `/voice/dev` on localhost in its browser pane,
    which is not Chrome and gives a page no microphone (plan 002), so it first replaces
    `navigator.mediaDevices.getUserMedia` there with a silent stream, since the client opens the
    microphone before it joins (Track G): the page loads, ICE connects on whatever candidates the
    pane offers, the data channel opens and `hello` arrives; the microphone, playback and Stop wait
    for the owner's session in Chrome (step 18; Edge dropped on 2026-11-03).

**Step 17, the whole-plan review of the code, dropped** on 2026-11-03 ("The owner's decisions"):
each track had its review, and step 16's end-to-end test and the owner's session (step 18) check the
whole; for this plan, this replaces the plans README's review of the whole plan before the
integration branch merges ("Parallel tracks", item 5). After step 16, `plan-003-integration` merges
into the main branch, with the full gate, so the owner's session runs from it; from here, this
plan's blocks merge into the main branch.

**The owner's recorded session** (local; needs Q5, Q13 and Q18, settled, and "What the owner does",
steps 2 and 3; Q4 and Q7 settled; since 2026-11-03, "The owner's decisions", the first calls and
run C, which was step 28, are this one session)

18. Step 23's spending rule applies first. Run C of the registration: one recorded session of about
    20 to 30 minutes, from the main checkout, through the Ole5 app's dev server on localhost, in
    Chrome, on the laptop's speakers, then on the wired headset, with Q18's script ("What the owner
    does", step 3): a few turns in each language (Saudi Arabic, MSA and English), Stop and Esc
    pressed once each during an echo, and in each Arabic call a listening sound during another echo,
    which is transcribed and kept on the timeline but, by the drop rule, never said back, so M3's
    check that listening sounds do not interrupt the agent has M2's recordings to run on; and in
    each Arabic call «وقف» at normal volume during a third echo, never said back either, for M3's
    stop targets (plan 005's Q2 (b), "The owner's decisions", 2026-11-03); the owner
    checks the microphone and playback and says whether each turn came back. The session is four
    calls, an Arabic and an English call on each device, each under `limits.max_call_s` (600 s);
    each joins through the Ole5 app's token route with the access code (Q4), the recording box
    ticked, so its recording consent rides in a signed join token (Q7's (a));
    `T2V_PRIVACY__CONSENT_VERSION` is Q7's version (`m2-owner-test-1`) and
    `T2V_PRIVACY__RECORD_AUDIO` is on only for the session; the recordings stay under `var/` on this
    laptop (Q7's (i)) and their manifests are committed. Ole5's widget offers Arabic (`ar-SA`, whose
    call also hears MSA, said back in the Saudi voice) and English, and its token route mints at
    most 10 tokens in a rolling day, every start that got past the microphone counted, in the
    server's memory: a restart of the server begins the count again. The agent reads each call's
    trace and `CallReport`: the time of each step, each reply's `tts.cut_short` (TD-063's ceilings),
    and each model's requests per call minute (the measurement criteria), the latter recorded as a
    decision entry beside the published limits, or the real ones if the owner read them (Q17). A fix
    is a block of its own, and a call after it spends under step 23's rule.

**Steps 19 to 22, the deployment, moved out of M2** on 2026-11-03 ("The owner's decisions"): the
owner has no access to the server yet, so the deployment files, the network spike on the host, the
website embed with the network test, and the media path wait for a plan of their own, made as soon
as the owner has access to the server and re-planned for it (its host facts, Q8 to Q12), and at the
latest in M6. Their text, as drafted, is in "The deployment, moved out of M2". Steps 23 to 30 keep
their numbers.

**The registered runs** (the registration below; a quiet machine: nothing else runs beside a run,
[WORKING-RULES.md](../../../WORKING-RULES.md), "Measurement runs")

23. Every open call settled and dated (Q13 to Q18, on 2026-11-03); the estimate, about $0.34, and
    the budget cap, $1, approved by the owner (Q13, "The budget"). The spending rule, which governs
    step 18's session: before the session, a call after a fix, or any run that spends, the spend so
    far plus its own estimate is compared with the cap, and each model's requests, tokens and audio
    seconds that day with the published limits, or the real ones if the owner read them (Q17); one
    that would pass either does not start; the running total goes into the progress log after each,
    as plan 002's step 20 did.
24. A clean run worktree at the measurement commit, where E1, E2 and held-out E start (steps 25 and
    29; since 2026-11-03 no run of M2 spends); `poe eval --show-settings` checks the resolved
    settings, the turn settings among them; `poe eot` refuses the main checkout and a dirty tree.
25. **E1 and E2** (end of turn, offline, no spend): the dev paused requests and the secondary set,
    twice.

**Steps 26 and 27, moved or dropped** on 2026-11-03 ("The owner's decisions"): R5, R7 and R6 (the
noise on another day, TD-032, and the language a live call sends Whisper, with Q15) move to M3,
whose plan needs the noise runs anyway, and M2 keeps `stt.live_language`'s default, `session`; T1
and T2 (the time of each step on the golden set) are dropped, the time of each step coming from
step 18's session and, for the VAD stop and Smart Turn's decision, from E1. Their registered text
stays in "The measurement, registered before any result", each with its amendment.

**Step 28, run C, merged into step 18** on 2026-11-03 ("The owner's decisions"): the owner's
recorded calls are step 18's one session, recorded as step 28 had them (Q7's version, and the
recording setting on only for the session; the recordings under `var/` on this laptop and their
manifests committed), and requests per call minute are recorded from it as a decision entry. Steps
29 and 30 keep their numbers.

29. **Held-out:** E on held-out once, at the close, aggregates only. No held-out run spends in M2.

**Close**

30. The decision entries not yet written; the guide's pages finished; and, by an agent while the
    owner holds step 18's session (the owner, 2026-11-03), the design's factual slips
    that the research found (the design's 4.1 on Pipecat's `silero` extra, which exists with no
    requirements; its 10.3's "No number is known yet") listed for the owner and corrected as facts,
    not design changes. Its 3.2 on Groq's account team is listed as not confirmed either way: a
    third party quotes Groq's error asking the organisation's admin to accept a model's terms
    (github.com/langflow-ai/langflow/issues/11120, UNVERIFIED), and Groq's changelog says nothing of
    terms (read 2026-11-02 by the plan review), so it is corrected only from what the console shows
    the owner ("What the owner does", step 2): on 2026-11-03 the owner reported accepting the
    Orpheus terms, not who could accept them, so 3.2 stays listed as not confirmed. The design's
    lines that give M2 the deployment, which
    moved out of M2 on 2026-11-03 ("The owner's decisions"), are corrected as facts too, each to
    name the deployment's own plan (the roadmap's M6): its 1.2 serving bullet and 3.1's
    TURN-credentials row ("only if Ole5's M2 network test needs TURN"); 3.1's and 6.5's
    `Authenticate`, built in M2 if Ole5 picks the one-time email code (open question 19, which Q12
    took to the deployment); 11's TURN-credentials, TURN-beside-the-backend, Docker, "For Ole5" and
    small-services lines; 13's coturn row; 16.1's M2 row ("deployed" in its title, the deployment to
    the owner's host, the network test and the media-path decision, the identity decision, and TURN
    credentials in its library column); and 16.4's aiortc networking unknowns "until the M2 spike".
    The design's slips that Block 0's fixes found are corrected as facts too: its status line's list
    of the sections holding a note in italics names 3.3, which holds none since Block 0; 5.1's note
    on the package root's names lacks the twelve settings group classes, `TtsVoice` and
    `StructuredLogger` (D-032); 12.5's "ARCH-BAN would keep them away from Pipecat (proposed)" is
    built (step 6); and 16.3's "Written since" lacks D-036 to D-039 and the entries after them. The
    sections that Block 0's entries go beyond as Proposed get no note (the decision log,
    2026-11-03). Then `## Future improvements` in this plan, with a pointer from the roadmap's
    "Planned later" (the whole-plan review, step 17, was dropped on 2026-11-03); the roadmap's M2
    row set to `done` with a link; this plan moved to `completed/` with its Status line; the final
    gate.

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
  as step 1 says: no row the round removed is cited (ten were); httpx leaves the first `uv add` and
  the dependency table, since the library declares it; step 6 no longer splits `harness_config.py`;
  steps 8 and 9 cite the logging debt and D-026; the guide's samples are checked by DOC-SAMPLE; the
  rows the round left for M2's plan are in the decision log, and TD-037's row follows this plan's
  choice for `reference/api.md`. `uv run --offline poe docs`: 'check_docs: OK (27 files checked)'.
  Next: the owner's calls before Block 0 (Q1 to Q6), then Block 0.
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
- 2026-11-02: Steps 4 and 5, by a workflow of 13 agents in about 56 minutes: five readers of the
  installed sources, each checked by an agent that re-opened every cited line, two spikes on this
  machine with no request to Groq and no packet beyond it, and a write-up. The findings, with file
  and line, are the appendix "Block 0's reading of the installed packages"; the counts per reader,
  as the write-up printed them, head it, and no finding was judged wrong. What changes the plan is
  in the decision log's entries of this date: one Whisper request per user turn works; the runner's
  names stand (`PipelineWorker`, `WorkerRunner`); what "Pipecat's interruptions are off" means; the
  end-of-candidates PATCH; aioice 0.11.0's hang on one offer, met by a guard in `voice` rather than
  a constraint; the event loop on Windows; proxy headers while no proxy exists; and media on the LAN
  addresses. The interface details are the appendix's "Changes to the plan's interfaces", which the
  tracks read. Q2's `forward` cannot hold as it was worded, so Q19 goes to the owner; Block 0 builds
  `logging.pipecat` with `off` only meanwhile. Next: steps 6 to 12.
- 2026-11-02: Steps 7, 8 and 9, and step 6 but for its facades, by a workflow of three builders, one
  after another, each gated before its commits: the settings (41057da `VoiceSettings`, 2c659b3
  `JoinRejected`), the library's logging (a271648) and the harness (8d2ce05, 2abcf31, db8001a,
  bc25c8b). `Settings` and `get_settings` are gone, with no alias: `VoiceSettings` built in code
  reads nothing, and `VoiceSettings.from_env()` is the only reader of the environment, and of a
  `.env` only when it is passed one. Its 12 groups are one module each under `core/settings/`, and
  `uv run poe settings-ref` writes docs/generated/settings.md and `.env.example` from them (`grep -c
  "^T2V_" .env.example`: '49'). The library logs through the standard library under
  `t2_agentic_voice`, with a `NullHandler`, which pays the logging debt plan 004 found: its row is
  removed, and the design's notes, quality.md and the roadmap's M2 line no longer cite it. ARCH-BAN
  (`scripts/arch_ban.py`, harness.toml's `[[bans]]`) keeps Pipecat's provider services, LLM context,
  runner, torch and numba modules, loggers and DTMF out of the library, all of Pipecat out of
  `voice/session`, and Pipecat and aiortc out of the apps; `[[owners]]` gives jwt and sqlite3 to
  `adapters`, num2words to `domain` and loguru to `voice`. A test refuses any torch package in the
  lock and imports each public module alone in a fresh process, which must print nothing; the tests
  drop the new packages' variables before any import and make an aiortc peer without its own ICE
  list raise; the no-item scan reads `apps/*/web`, and `allowed_in_source.toml` holds Q6's "stop".
  Every commit's gate failed on one file alone, this plan, whose appendix's Python samples `ruff
  format` reflows; the integrator committed that formatting, and with it `uv run --offline poe
  check` printed '1614 passed, 1 skipped in 87.72s (0:01:27)' and 'Total coverage: 100.00%'. The
  integrator also declared aiortc in the root's dev group, which the tests reach (it was locked as
  pipecat-ai[webrtc]'s; nothing was downloaded). What the builders chose is in the decision log; the
  debt they found is TD-041 to TD-043, and the row on `eval-compare`'s settings (paid and
  removed since) named the keys an M1 run lacks. Left for step 10: step 6's facades (identity,
  server, stores, events), their tests and CLAUDE.md's lines for them. Next: steps 10 to 12.
- 2026-11-02: Steps 10, 11 and 12, by a workflow of four builders, one after another, each gated
  before its commits. The types (b44a575, e1e2f1d): the ports `TextToSpeech` with `AudioChunk`, and
  `IdentityVerifier` with `UsedTokens` and `JoinContext`; `aclose()` on every port that holds
  connections, which pays the close debt plan 002 found, so its row is removed; `Caller`, `Consent`
  and `SignedConsent` in `core/identity.py`; the events and `CallReport` in `core/events.py`;
  `VoiceAgent` and `Language` with Q3's presets in `domain/declaration.py`; the `t2v/1` models in
  `voice/protocol.py` and `api/protocol.py`; and step 11's message list,
  `tests/t2_agentic_voice/fixtures/t2v_protocol.json`, which a test holds the models to. The
  signatures (c6d8c73, 7eae285, 8b1bd40): `adapters/groq_client.py`, with GroqSTT's 93 tests passing
  unchanged; step 11's GroqTTS baseline, `tests/t2_agentic_voice/fixtures/groq_tts_request.json`,
  which the installed SDK reproduces byte for byte; `voice/session/io.py`; the stubs of
  `voice/calls.py`, `voice/file_transport.py`, `voice/session/call.py`, `api/runtime.py` and
  `api/server.py`, whose docstrings state each track's contract; and every other module a track
  fills, as a stub with its test in that track's file. The facades (ae9d849, b3ccca1, 4d00a15):
  `identity`, `server`, `stores` and `events` join the five, the root gains `VoiceAgent`,
  `Language`, `Caller`, `Consent`, `VoiceRuntime` and `Providers`, a test checks the design's 5.3
  point 1 over every public annotation (`tests/t2_agentic_voice/test_public_types.py`), and the
  fakes are `tests/t2_agentic_voice/fakes.py` and `session_fakes.py`, two modules under ARCH-SIZE;
  the child shells, `join.keys` in the eval history's secret pattern and aiortc's plain import in
  the tests were tidied. The decision entries (3ccdfe8): D-028 to D-035, with D-002, D-003 and D-007
  pointing at the entries that amend them, GP-22 widened, and SECURITY.md's invariants 7 and 8
  brought to the design's 8.1 with the tests that enforce them today. The integrator recorded the
  reports, wrote TD-044 to TD-047, and corrected the design's status line, 5.1's note and 16.3's
  lists as fact; `uv run --offline poe check` on 3ccdfe8 printed 'Success: no issues found in 257
  source files', '1936 passed, 1 skipped in 107.10s (0:01:47)' and 'Total coverage: 100.00%'. The
  builders' gate runs took 316 to 382 s while other sessions ran on this machine, against 89 to 105
  s otherwise, and one took 5676 s (TD-040's hang, or the machine; no stacks were kept). Next: step
  13, the review, then the fixes the integrator listed in the decision log of this date.
- 2026-11-02: Step 13, the review of Block 0, by a workflow of 131 agents: six reviewers (security,
  the harness, the interfaces the tracks build on, correctness, the tests, and the decisions and
  docs) and a completeness critic, each finding checked by skeptics told to refute it (three for a
  high finding, two for a medium, one for a low). Of 81 findings (the reviewers' 74 and the critic's
  7), 70 stood (64 and 6): 5 high, 29 medium and 36 low. The integrator ruled on each and gave 64 to
  seven builders by part, with the fixes the decision log's entry before the review queued; the
  other six were slips in this plan's text, the integrator's: two are corrected with this record
  (the spike run the decision log names, and the guide's logging page it gave Track G), and four
  that nothing builds on are left, under the owner's ruling of 2026-11-03.
- 2026-11-03: Step 13's first fix round, by seven builders, one after another, each gated before its
  commits, in 11 commits (22474ce to 7f24068): `SignedConsent` sealed (22474ce); the settings'
  bounds and errors (19f6048, 9edbd3c); the `t2v/1` error body and the serving contracts (bd6fe67);
  the session's I/O split into its events, its commands and the rest, agent speech keyed on replies,
  the drop rule over every reply, the call's language fixed at join, and `Transcript`'s headroom
  (f945dcd, 9235382, 2b12f50); the pronunciation map, each preset's notice texts, a long fixed
  phrase spoken whole, and the names Windows keeps for devices refused as an agent's (244401e);
  ARCH-BAN following the library's own imports, and every type a public signature names made public
  (6483f9c, ac6a10f); and D-036 to D-039 written, with D-028 to D-035 and SECURITY.md brought to the
  fixes (7f24068). Of the 64 findings, 63 were fixed, and the design's status line was left to
  step 30. The last gate, the docs builder's on 7f24068's tree: 'Success: no issues found in 261
  source files', 'check_architecture: OK (261 files checked)', '2140 passed, 1 skipped in 156.88s
  (0:02:36)' and 'Total coverage: 100.00%'. The builders' choices are in the decision log, with the
  second round's; of the ten debt rows they proposed, the second round paid five, and the rest are
  TD-050, TD-051 and TD-049.
- 2026-11-03: The check of the first round, by a workflow of 309 agents: one or two checkers for
  each of the 63 fixed findings, told to show it was not fixed (45 still had a gap, and 93 gaps
  stood); seven reviewers of the round's commits alone (security, correctness, the contracts, the
  tests, the harness, the docs and the spoken texts: 48 findings, 34 stood); and a completeness
  critic (3, all stood); each checked by skeptics as the review's were. 130 stood: 6 high, 28 medium
  and 96 low. The integrator gave 125 to the second round's builders by part and kept 5, all this
  plan's text: four are corrected with this record (Block 0's files in "## Tracks", Track A's test
  and the language criterion on a clause's length, Track E's stop test, and the appendix's item 4
  with step 4's bullet on held audio at the end), and one is left, step 7's wording of a short
  secret's FIX line, step 7 being done.
- 2026-11-03: Step 13's second fix round, trimmed by the owner's ruling of this date (the next
  entry): five builders, one after another, each gated before its commit, then the docs builder, in
  6 commits (52e7efb to ff235a8): a `SignedConsent` allows recording only as the instance sealed
  (52e7efb); the settings after the check (7ed5a15); `t2v/1` after the check: the version read
  first, `not_offered`, 415 for a body not sent as JSON, each call's record dropped in time, and
  Whisper's headroom read (72f482c); the fixed phrases packed and paced, said through the
  pronunciation map and public through `stores` (ebe45de); the stop, the end and every request
  counted (9974a2c); and D-028 to D-039 brought to the round (ff235a8). Of the 99 findings the six
  were given, 96 were fixed and 3 left as the docs builder's brief said (SECURITY.md and a register:
  TD-056 and TD-057); of the integrator's 43 rulings, 42 were done, and one found no line to change.
  The harness builder's 26 findings were dropped by the ruling (TD-049). The last gate, the docs
  builder's on ff235a8's tree: 'Success: no issues found in 274 source files', 'check_architecture:
  OK (274 files checked)', 'check_docs: OK (28 files checked)', '2408 passed, 1 skipped in 142.66s
  (0:02:22)' and 'Total coverage: 100.00%'. The builders' choices are in the decision log; the debt
  they found is TD-051 (with the first round's) and TD-052 to TD-054, and the gap the session
  builder named at a stop is TD-055.
- 2026-11-03: The owner's two rulings of this date are recorded ("The owner's decisions"), with
  the decision log's lines for them, and the plan is amended to them before any run. From Block 0's
  last round on, a review reports only what would break a call or leave a later track or milestone
  a contract it cannot build on, one reviewer per block or track and one skeptic per finding, the
  rest becoming debt rows; Q7 is settled as (a), (i) and (iv), on this laptop. The deployment moved
  out of M2: its criteria, steps 19 to 22 and the packages they run, Q7 and Q8 as drafted, Q9 to
  Q12, the owner's steps 4 to 8 as drafted, and the registration's C and its budget as drafted are
  in "The deployment, moved out of M2"; C is now five local calls and the budget about $0.80,
  amended before any run. The title, the goal, the Scope, the criteria that named the host, TURN
  or Linux, steps 13, 14, 17, 28 and 30, Tracks C, F and I, the review rule and Q4 changed with
  them. The roadmap's M2 is "A call that listens and speaks", and its M6 names the deployment;
  TD-004, TD-015 and TD-038 wait for the deployment's plan, and quality.md's line on them says so;
  Block 0's unused TURN settings and stub are TD-048, and the harness findings Block 0's round 2
  dropped are TD-049. The design is not edited: step 30 lists its lines. Next: Block 0's last
  review round, under the new rule.
- 2026-11-03: Block 0's last review round, under the new rule: one light review of the second
  round's commits by two reviewers, one more than the rule names (one read them as a live call would
  run them, the other read the contracts the tracks build on), each finding checked by one skeptic.
  Its 3 medium findings were all refuted, each judged low: a take the phrase cache keeps cut short,
  whose flag the port carries to `ClausePlayed` for Track B to keep; and, named by both reviewers, a
  clause whose audio is empty, as `turn_ends`' silent phrases are, for which `voice/session/io.py`
  named no event. No high finding stood, so no fix round follows.
- 2026-11-03: The skeptics read io.py's rule that every clause reports an outcome as covering an
  empty clause, but Track E could build either reading, and a `ClausePlayed` that never came would
  leave a file-fed call feeding silence: so the integrator added one sentence to
  `voice/session/io.py`'s Replies bullet, with this record: a clause whose audio is empty reports
  `ClauseQueued`, then `ClausePlayed`, at its place in the output, sending no frame and opening no
  text-to-speech context, since Pipecat 1.15.0 reports a context that ends with no audio as an
  error.
- 2026-11-03: A merge-tree of this branch and the main branch (their base 69353de) shows one
  conflict for when `plan-003-integration` merges into the main branch (step 17): the end of
  decisions.md, where the main branch's entry on the agent-led mode (c83747b, docs only) follows
  D-027, and this plan's D-028 to D-039 go before it, as the decision log's step-12 entry says;
  package-design.md and the roadmap merge cleanly. Next: the gate, then Block 0 merges into
  `plan-003-integration` (step 13), and the tracks start.
- 2026-11-03: Track A, speech text, in 3 commits (c5909f5 to fc9c46d), merged as 491b7bc:
  `speak_number`, `speak_id` and `speak_digits` (`domain/text/speaking.py`), the clause splitter
  (`clauses.py`) and the pronunciation map (`pronounce.py`). Read: the prototype's `speakable.py`,
  lines 7-41 and 109-157, and num2words 0.5.14's output (MSA Arabic, its waw a word of its own, an
  OverflowError from 10**51; English thousands with a comma; 0.45 s to import). Values: an ID is a
  run of 5 digits or more, a run with a leading zero, or a run after a cue ("ending in", «آخرها»,
  «ينتهي بـ»); the digit names are the prototype's MSA table; a punctuation mark, Arabic or English,
  ends a clause only where it ends a word. Gate: 'TOTAL 5595 0 100%', '2469 passed, 1 skipped in
  371.47s (0:06:11)'. Review: one finding, A-1 (an Orpheus request for each clause the splitter
  cuts), refuted as Track A's, its contract asking for the cuts; the same cost stood in Track D as
  D-1.
- 2026-11-03: Track C, identity and stores, in 3 commits (44384d2 to 43625aa), merged as ba8ff9c:
  `SignedJoinTokens` (`adapters/join_tokens.py`), `DevIdentity` (`adapters/dev_identity.py`), and
  `SqliteUsedTokens` with `MemoryUsedTokens` (`adapters/used_tokens.py`), tested on invariant 7's
  adversarial cases, a replay after a prune and after a restart, and two threads on one store and on
  two stores of one file. No prototype source (it has no join tokens); PyJWT 2.15.1 read: its claim
  checks call `datetime.now` themselves, and its minimum key length (32 bytes for HS256) holds when
  it signs and when it verifies, as the appendix's item 25 says. Values: a `jti` of 1 to 128
  printable ASCII characters, minted as `secrets.token_urlsafe(16)`; `iat` and `exp` JSON integers;
  one `BEGIN IMMEDIATE` transaction a `use`, in a worker thread; loopback as 127.0.0.0/8, ::1 and
  IPv4 loopback mapped into IPv6. Gate: 'TOTAL 5669 0 100%', '2508 passed, 1 skipped in 388.67s
  (0:06:28)'. Review: one low finding, C-1 (a failed COMMIT leaves the store's transaction open,
  refusing every later join), refuted, as nothing in the system makes a COMMIT fail: TD-065.
- 2026-11-03: Track B, the Orpheus adapter and the phrase cache, in 4 commits (1c29fa1 to 111d66f),
  merged as 08c0ab6: the streamed WAV reader (`adapters/wav_stream.py`), `GroqTTS` on `groq_client`
  (`adapters/groq_tts.py`) and `PhraseCache` (`adapters/phrase_cache.py`). Read as specs, never run:
  the prototype's `tts.py` (its `WavStream`, cut-short check, trimmer and stream) and `fillers.py`
  (the cache), and groq 1.7.0's streamed speech path, which decides to stream before the request
  hook runs. Values: mono 16-bit PCM only, the rate read from the fmt chunk; the leading silence in
  40 ms frames under an RMS of 0.006 (about -44 dBFS, the prototype's), its last 40 ms kept when
  trimmed; the prototype's cut-short ceilings (24 characters a second in Arabic, 30 in English, a
  text under 30 characters never flagged), read from the first sound; a phrase's file keyed on
  sha256(format, model, voice, text sent)[:32]; a 429 waited out for at most 60 s and sent again at
  most twice. Gate: 'TOTAL 5829 0 100%', '2556 passed, 1 skipped in 416.38s (0:06:56)'. Review: one
  low finding, B-1 (a silent take of a short fixed phrase is written to the cache), refuted, as no
  such take from Groq is known and an empty clause plays as nothing: TD-061.
- 2026-11-03: Track D, the voice session in echo mode, in 6 commits (3fdb2a1 to 6560f6d, the review
  fix last), merged as c052e64: `CallSession` (`voice/session/call.py`) with the echo (`echo.py`),
  the heard words (`heard.py`), the replies as they play and the speaker (`playback.py`), usage per
  model (`usage.py`), the report and its file (`report.py`) and `CallRecorder` (`recording.py`);
  and, in `core/tracing_tts.py`, the settings digest, the resource attributes, the text-to-speech
  span and `CallTrace`. Read: the prototype's `capture.py` (a record per utterance, audio only when
  on, files written on a thread of their own, a failure logged and never raised) and `session.py`'s
  clock (lines 234-253: its stages run from an utterance's arrival, the session's from the end of
  the caller's speech). Values: `DROP_AFTER_S` 0.3 s; `WHISPER_MIN_BILLED_S` 10 s; the report at
  `var_dir/reports/<call ID>.json`; the recording at `var_dir/recordings/<call ID>/` (`caller.wav`,
  `agent.wav` and `timeline.jsonl`, whose first line holds the consent version), each track padded
  with silence to its place on the call's clock. Gate after the fix: 'TOTAL 6438 0 100%', '2476
  passed, 1 skipped in 128.25s (0:02:08)'. Review: two medium findings. D-2 (the session holds its
  lock while `Commands.run` waits) was refuted, `Session.handle` having to return soon and Block 0's
  `FakeSession.handle` awaiting `run`; the rule `run`'s contract leaves unsaid is in TD-068. D-1
  stood: the echo asked for one Orpheus request a clause, all at once, so a punctuated turn could
  pass Groq's published 10 a minute; fixed in 6560f6d, the echo packs its clauses into requests of
  at most `max_chars`, at most 3 an echo (`MAX_ECHO_REQUESTS`), with five tests that fail on the old
  `echo.py`.
- 2026-11-03: Track E, the Pipecat modules, in 10 commits (ae69cf7 to ec58326, the review fix last),
  merged as c159c62: Pipecat's loguru namespace off (`voice/loguru_policy.py`); Silero and Smart
  Turn v3.2, built only when a call needs them (`turns.py`); the speech bridges (`stt_bridge.py`,
  one request a user turn; `tts_bridge.py`, in TOKEN mode) and the session bridge
  (`session_bridge.py`); the WebRTC peer through a request handler of each call's own, with the F7
  refusal, bounded closes and the taps (`transport.py`); Pipecat's failures as the library's
  (`pipecat_events.py`); one worker and one runner a call (`pipeline.py`); `VoiceCalls`
  (`calls.py`); and `feed_file` (`file_transport.py`). Read: the appendix's items 1 to 26, and
  Pipecat 1.15.0's speech services, transports, processors, worker, runner and turns. Values: a
  pre-roll of the detector's start delay plus 0.5 s; 0.3 s kept after the last VAD stop; at most
  30 s a request; 20 s from offer to connected; 5 s for a peer's close and for the pipeline's
  cancel; 1 s for the session to hang up after an `Ending`, and 10 s for it to drain. Measured: a
  local aiortc offer answered in 29 ms, a client's close ending its call in about 40 ms, onnxruntime
  with both models built in 8.7 to 9.8 s, and 60 s of fed frames within 100 ms. Gate after the fix:
  'TOTAL 6467 0 100%', '2480 passed, 1 skipped, 1 warning in 232.86s (0:03:52)', the warning
  Pipecat's own for `AudioContextTTSService`. Review: E-1, high, judged medium, stood: each clause's
  `TTSStoppedFrame` made Pipecat's output clear the part chunk it held of the next clause, still
  streaming, losing up to 40 ms inside it; fixed in ec58326, the bridge resamples to the pipeline's
  rate and hands the output whole 1920-byte chunks only, the take's last padded with silence (the
  new test lost 400 samples before it). E-2 (a hung `pc.close()` keeps a call's tasks for the life
  of the process) was refuted: Pipecat's own bound ends them in about 20 s.
- 2026-11-03: Track F, `api`, the CLI and `examples/minimal`, in 6 commits (add8113 to bd2af48; two
  are its asks, committed to Block 0's files: the package root's lazy names, add8113, and the `t2v`
  console script, b1e724f), merged as 6100fe6: `VoiceRuntime`, its lifespan and
  `Providers.from_settings` (`api/runtime.py`); the lock file (`lockfile.py`); the router, its
  records of the calls and its one error shape (`router.py`, `offers.py`, `http_errors.py`);
  `serve()` and `combine_lifespans` (`server.py`); `t2v serve`, `dev`, `doctor` and `settings show`
  (`cli.py`, `doctor.py`); and `examples/minimal` as an echo agent in English and Saudi Arabic. No
  prototype source. Values: the records swept every 5 s; at most 1000 events queued for the
  observers, 10 s each; a call ID of 96 random bits and an offer secret of 256; the lock at
  `var_dir/runtime.lock`, the phrase cache under `var_dir/<agent>/phrases` and the used tokens in
  `var_dir/<agent>/used_tokens.sqlite3`. Shown: a running `serve()` takes the selector loop, in a
  child process (D-029's UNVERIFIED item); its app records no span, metric or log record with
  `FASTAPI_OTEL_AUTO_CONFIGURE=true`; the debt on the package root's FastAPI import is paid (its
  row removed since), `import t2_agentic_voice` loading no FastAPI, Pipecat, onnxruntime, groq
  or uvicorn and taking 1.55 s with `python -I`, against 4.42 s before; and TD-012's warm-up is
  built. Gate: 'TOTAL 6287 0 100%', '2590 passed, 1 skipped in 197.20s
  (0:03:17)'. Review: one low finding, F-1 (`t2v doctor` prints the clock without measuring its
  skew), refuted as outside the rule: a criterion reading of this date, and TD-067.
- 2026-11-03: Track G, the browser client, the widget and the Ole5 app's server, in 6 commits
  (499ffda to cca13ed), merged as 120d39b: `t2v-client.js` and `dev.html` (`api/static/`); Ole5's
  widget (`apps/ole5-voice-agent/web/`); the app's settings, token route and server
  (`ole5_voice/settings.py`, `token_route.py`, `server.py`); and `.claude/launch.json`'s
  `minimal-dev` (port 7860) and `ole5-dev` (port 7861). Read only: the prototype's `web/voice.js`,
  lines 213-235 (audio started inside the click, the capture's constraints), and `web/t2-chat.js`'s
  microphone error map, which the widget's messages adapt; the recorder's page; Pipecat 1.15.0's
  Small WebRTC connection (only raw text starting with `ping` refreshes its keep-alive, so the
  client sends none), uvicorn 0.54.0's config and FastAPI 0.162.0's `telemetry=`. Values: the Ole5
  server on 127.0.0.1:7861; Q4's guard counted in memory, an address held back 1 s after its first
  wrong code in the hour and doubling to 60 s, 20 wrong codes an hour, 10 tokens in a rolling day;
  the client's playback watch every 50 ms, sound above an RMS of 0.01, a clause ended by 300 ms of
  quiet; a hangup waiting at most 3 s for `ended`. Gate: 'TOTAL 5756 0 100%', '2473 passed, 1
  skipped in 156.29s (0:02:36)'. Review: two findings, refuted as outside the rule: G-1 (the client
  opens the microphone before it joins, so the agent's browser pane, which has none, never reaches
  the data channel), which step 16 now meets with a silent stream, and G-2 (`/dev`'s headers, which
  no track's section gave), a criterion reading of this date.
- 2026-11-03: Track H, the measurement's tooling, in 8 commits (f4023f4 to 54d66fb; c868760 alone
  fails ARCH-SIZE, which 73a099d fixes), merged as 8aa3417: `turn_ends` (`testing/turns.py`) and
  `echo_timings` (`testing/echo_timing.py`, `timed_speech.py`) on the file-fed pipeline; `poe eot`
  (`evals/eot.py`, `eot_score.py`); `poe eval-timing` (`timing.py`, `timing_run.py`,
  `timing_score.py`, `pacers.py`); the recorded calls' manifests (`call_manifests.py`); the
  history's end-of-turn and timing lines; the debt on `answerers.py`'s size paid (each answerer
  in its own module) and that on `eval-compare`'s settings (`eval-compare` refuses runs whose
  settings differ, but for `stt.model`, `run.cap_usd` and `run.smoke_only`, with
  `--allow-setting NAME`: R7 against R5 takes `run.language_hint`); and `poe
  eval`'s smoke line naming the language the provider reported (TD-011, R7's smoke step). No
  prototype source. Values: a cut-off is a first turn end more than 300 ms before the true end, else
  a miss when none comes within 4 s after it; `LEAD_S` 1.0 s and `TAIL_S` 4.5 s; `NOISE_FLOOR` 328
  of 32768 (about -40 dBFS, UNVERIFIED until T1); pacers of 10 Whisper and 5 Orpheus requests a
  model in any minute, a variant budgeted 2 of each; a rate-limited call run again after 60 s, at
  most 3 calls. The reference answerer scores the committed golden set at 0 cut-offs, 0 misses and
  0 ms, on dev (23 variants) and held-out (16). Gate: 'TOTAL 6638 0 100%', '2476 passed, 1 skipped
  in 187.57s (0:03:07)'. Review: one medium finding, H-1 (a timing run goes on after a 429 its three
  calls could not wait out), refuted, as the pacers hold the minute and T runs on a day with no
  call: its budget points are in TD-082.
- 2026-11-03: Tracks A to H, by a workflow of 29 agents: 8 builders, each in a worktree of its own
  (`plan-003-track-a` to `plan-003-track-h`, cut from `plan-003-integration` at Block 0's merge,
  8271b54) and gated before its commits; 8 reviewers, one a track, under the owner's rule of
  2026-11-03; 11 skeptics, one a finding; and 2 fixers, for Tracks D and E. Of the 11 findings (1
  high, 6 medium and 4 low as reported), 2 stood, D-1 and E-1, each judged medium, and were fixed
  (6560f6d, ec58326); no high finding stood, so no second round ran. Each gate's one skip is the
  recorder's file-link case (TD-001). The integrator departed from step 15 twice: the eight merges,
  in the order A, C, B, D, E, F, G, H (491b7bc to 8aa3417), were made within 4 s, the full gate
  running once, on the merged branch, rather than after each merge; and, to keep the merges moving,
  these records are written in one commit after the merges, rather than in each `merge track X`
  commit. That gate passed: 'TOTAL 10172 1 99%', 'Total coverage: 99.99%', '3172 passed, 1 skipped,
  1 warning in 294.49s (0:04:54)', the warning Pipecat's own for `AudioContextTTSService`; its one
  uncovered line, `voice/session/echo.py` line 79, was the echo's check for a blank clause, which no
  text reaches since Track A's splitter keeps only clauses with a letter, a digit or a symbol,
  removed in 2e0cc54. The tracks' debt is TD-058 to TD-083; the criteria they met differently, or
  could not meet alone, are read in the decision log of this date, and steps 16 and 18 and Track I's
  section are brought to what the tracks built.
- 2026-11-03: The integrator's commits after the merges, before these records: d4cadca,
  `harness.toml`'s `[[restricted]]` row for `HeardWords` (Track D's ask; the decision log's reading
  of this date); b99a0c3 and fb81f8b, `voice/__init__.py`'s and `api/__init__.py`'s docstrings
  naming what is built (Track D's and Track F's asks), `voice/calls.py` no longer calling itself a
  stub; 6838e97, the poe tasks `eot` and `eval-timing`, their row in CLAUDE.md's Commands table and
  their bullets in evaluation.md's "Where the commands live" (Track H's asks), which the end-of-turn
  criterion's `uv run poe eot` needs; d69bac8, one sender of the public failure events (the decision
  log's reading of invariant 8); 8551a74, `t2v doctor --synthesize` printing a provider's FIX line
  from `details["fix"]` (Track B's ask); and 2e0cc54, the gate's uncovered line.
  `.claude/launch.json`'s `minimal-dev` line stands as Track G wrote it, Track F's factory being
  `minimal_example.app:make_runtime`. The debts on `answerers.py`'s size, on `eval-compare`'s
  settings and on the package root's FastAPI import are paid, and TD-012 for a call, its row now
  naming a run's first request only; the three rows go in the integrator's next commit, with
  their citations in the code, the tests, this plan and the docs, which DOC-REF reads. Next: that
  commit; `/dev`'s headers, Track G's policy sent by the router, with a test through it (Track G's
  ask); then Track I, and step 16.
- 2026-11-03: The owner's ruling to finish M2 faster is recorded ("The owner's decisions"), with the
  decision log's entry for its readings, and the plan, the roadmap and `docs/plans/tech-debt.md` are
  amended to it before any run. T1 and T2 are dropped; R5 to R7, Q15 and the noise on another day
  (TD-032) move to M3, and Q16 to M4; the first calls and run C are one recorded session in Chrome
  (step 18, with Q18's script in "What the owner does", step 3), Edge dropped; step 17 is dropped,
  so `plan-003-integration` merges into the main branch after step 16, with the full gate. Q13 is $1
  against an estimate of about $0.34; Q14 keeps the defaults; Q17 is optional. The owner accepted
  the Orpheus terms in Groq's console and has not read the key's limits. Amended with them: the
  goal; the criteria on the widget, the recordings, the decision entries and the measurement; the
  Scope and "From M1"; the two review rules and Track G's tests, each with a dated pointer where it
  named step 17 or Edge; steps 16, 17, 18, 23, 24, 26 to 28 and 30; the registration's T, L and C
  and the budget, each with a dated amendment, the registered text kept; Q13 to Q18; and the owner's
  steps 2, 3 and 7 to 9. The roadmap's M2 reads its *Done when* from the session, its M3 takes the
  live language and its M4 the prompt arm; the debt rows TD-011, TD-032, TD-063, TD-066, TD-070,
  TD-071, TD-081 and TD-082 name their new triggers, and no row is removed. Next: Track I and
  step 16, then the merge into the main branch and the owner's session, while an agent corrects the
  design's factual slips (step 30); E1 and E2 at the measurement commit.
- 2026-11-03: Track I, the guide, in 2 commits (0ab8e1b, f38a4be), merged at 33c0644. The guide's
  index is brought to M2 and the six pages the criteria name are written: is-this-for-you.md,
  quickstart.md (the echo agent, ending with a checklist driven by `t2v doctor`'s lines),
  serving.md, browser-client.md (its M2 part), tracing-and-logs.md and data-and-privacy.md;
  `packages/t2-agentic-voice/README.md` is brought to M2. Its 9 Python samples are runs of their
  files' lines (DOC-SAMPLE), the logging one `examples/minimal`'s `__main__.py`. The install's size,
  on Windows 11 x64 with Python 3.12.13: 89 distributions, 509.1 MB (llvmlite 121.5 MB,
  opencv-python-headless 115.9, av 68.6, onnxruntime 43.7, numpy 42.0, pipecat-ai 20.6; no torch or
  transformers). Gate: 'check_docs: OK (34 files checked)', 'TOTAL 10174 0 100%', '3176 passed, 1
  skipped'. Its review (one reviewer, one skeptic): one low finding, the join token's table leaving
  out constraints the verifier holds, refuted under the 2026-11-03 rule and kept as debt with the
  reviewer's notes on the guide (below).
- 2026-11-03: Step 16's automated part, `tests/t2_agentic_voice/test_loopback_call.py` (15d2cbb,
  54b374a), merged at 128f152. An aiortc peer (`iceServers=[]`, max-bundle) joins the minimal
  example's echo agent through the runtime's router (`DevIdentity`, `env` dev, fake providers, the
  tone detector), trickles its candidates after the answer, sends a 0.6 s sine and hears its words
  said back once at their own pitch (0.74 to 0.76 s of 0.75 s), the phrases from the cache (1.46 to
  1.54 s of 1.50 s); the call takes about 3.9 s. It checks what the tracks left to it: the phrase
  cache, declared at the start (8 requests, 8 files), has no new file and was never asked for the
  heard words; one of each public event and of each named session message; a report file with no
  heard text; the peer closed and no task left. `uv run poe eot --answerer reference --split dev`
  printed 'run_finished complete=True cut_offs=0 delay_median_ms=0.0 misses=0 variants=23'. Gate:
  '3177 passed, 1 skipped', 100%. Its review: one low finding (the test's cleanup unbounded on a
  failure path), refuted, kept as debt.
- 2026-11-03: Step 16's part by hand, by the integrator. No factory serves `examples/minimal` with
  fake providers for `t2v dev` (debt below), so a scratch script, never committed, served its agent
  with the tests' fakes through `serve_dev` on 127.0.0.1:7870, its `var_dir` a temporary folder. In
  the browser pane, `getUserMedia` replaced by a silent stream (the pane has no microphone, and the
  client opens it before it joins): `/voice/dev` loaded under Track G's policy with no console
  message; Start connected (call WIEYf8YnXNqCGt_H), the greeting's caption arrived and the agent was
  listening; Hang up showed 'Ended: hangup'. After the end the page still showed 'Connection:
  connected · Agent: listening' (debt below). The microphone, playback, Stop and Esc wait for the
  owner's session.
- 2026-11-03: The gate on 128f152, everything merged: 1 failed, 3176 passed, 1 skipped.
  `test_calls.py`'s `test_a_peer_that_fails_or_closes_ends_its_call` waited out its 60 s; alone it
  passed 5 times of 5 in 3 to 9 s. Its two runners with real peers ran on Windows' default Proactor
  loop, where an aiortc close can hang (the appendix, item 20), while `serve()` and the loopback
  test use the selector loop: 7491cfe runs them on the selector loop, and gives Track B's timeout
  test one 15.6 ms tick of the loop's clock, after it measured 0.2919 s against 0.3 s once in step
  16's gate.

## Decision log

The entries are the agent's choices, each dated, with the agent's reasons; the owner may overrule
any before the step it affects. An entry that records an owner's ruling says so, and the ruling
itself, in the owner's words, is in "The owner's decisions".

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
- 2026-11-02: `aclose()` joins `SpeechToText` and `TextToSpeech` now, since M2's runtime
  owns the adapters' lifetimes; a change to stable ports beyond the design's 6.1, written as
  Proposed in its decision entry.
- 2026-11-02: Debt paid in M2: TD-012, TD-014, the debt on `eval-compare`'s settings (before R7,
  so the comparison refuses any setting but the language hint), TD-011 (read in R7's smoke
  step), TD-032 (R5 and R6), the logging debt (step 8) and the ports' close (step 10). TD-015 stays whole: the owner's Phoenix runs on this
  machine with no authentication ("The owner's decisions"), so no trace needs an API key in M2.
  TD-004 follows Q8: with no proxy on the host, the clients turn `trust_env` off; with one, a proxy
  setting is added. TD-003 and TD-005 stay: `GroqTTS` imports groq inside `logging_unchanged` as
  `GroqSTT` does, and the owner kept TD-005 as debt (2026-11-01).
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
- 2026-11-02, after Block 0's read and spike (the appendix): Whisper's cut stays one request per
  user turn. The spike's bridge, on Pipecat's `STTService` after `UserTurnProcessor`, held a turn
  with a 0.86 s pause and sent it once (its run A; run C, the same file looped, sent one request a
  turn), with `wait_for_transcript` off; with it on, the turn ended only at the 5 s stop timeout
  (run D). The bridge subclasses `STTService`, not the `SegmentedSTTService` the design's 13 names.
  Whether a paused request is one turn is Smart Turn's verdict at the pause: a first clause that
  sounds complete ends the turn (run B: two turns, two requests), so the registration's request
  counts keep their upper bounds.
- 2026-11-02, amending the entry on the end-of-candidates PATCH: the PATCH reaches aioice 0.11.0,
  but it makes a failure show sooner only when no candidate pair is still being checked (33 ms in
  the spike's F8). A call whose candidates are unreachable ends at Pipecat's 60 s timeout either
  way, as `closed` with no `failed`, since aioice gives up on a check only after about 63.5 s
  (`aioice/stun.py`, lines 20-21). The client still sends the PATCH; a faster failure comes from
  `voice`'s own deadline from offer to connected (Track E), which also meets the next entry.
- 2026-11-02: aioice 0.11.0 hangs on one offer: with `a=end-of-candidates` and no candidate, the
  server's peer drops its only component and stays `new`, with no event and no timeout
  (`aioice/ice.py`, line 1101; the spike's F7). Q1 allowed a constraint below 0.11 if the spike
  needed one. The agent adds none, since whether 0.10 differs is UNVERIFIED and a browser's trickled
  offer carries no such mark; `voice` refuses that offer and closes any call not connected within
  its deadline instead (Track E). The owner may still ask for the constraint.
- 2026-11-02: On Windows the servers run uvicorn on a selector event loop, and every peer's close is
  bounded by a timeout. On the default proactor loop, aioice's UDP sockets stopped receiving after a
  WinError 10054, and 2 or 3 of 16 call closes hung, against 0 of 16 on a selector loop (the spike;
  the standard library's `asyncio/proactor_events.py`, lines 541 and 108). Whether uvicorn takes
  that loop in a running server is UNVERIFIED until Track F runs it. With all hosting on this
  machine for now, this holds for every M2 call.
- 2026-11-02: While no proxy is in front of the backend, `serve()` and the Ole5 app's server run
  uvicorn with `proxy_headers=False`, and `server.forwarded_allow_ips` is empty by default (`*`
  refused): uvicorn's defaults trust 127.0.0.1 and ::1, so any local client could set its address
  through `X-Forwarded-For`. uvicorn also runs with one worker, no access log, no server header and
  no `env_file`.
- 2026-11-02: A browser and the backend on this machine meet over its private network addresses, not
  loopback: aioice never offers 127.0.0.1 (`aioice/ice.py`, line 88), so `t2v dev` bound to
  127.0.0.1 still opens UDP sockets on the LAN addresses, and a browser's `.local` candidates send
  mDNS on the LAN. SECURITY.md's trust boundaries say so (step 12).
- 2026-11-02: "Pipecat's interruptions are off" means: the turn start strategies are exactly
  `VADUserTurnStartStrategy(enable_interruptions=False)` (its default broadcasts an interruption at
  every turn start), RTVI is off (`enable_rtvi=False`), and no DTMF aggregator runs. Stop, Esc and
  `hangup` use Pipecat's interruption path on purpose, through the session bridge's
  `broadcast_interruption()`, which drops queued audio up to the output transport; up to about 40 ms
  already in the WebRTC track still plays, so the capture test checks the output transport, not the
  wire.
- 2026-11-02: Importing onnxruntime took 8 to 12 s per process on this machine (the spike), so
  `import t2_agentic_voice` and `t2v --help` import no module that loads it (GP-17), the lifespan
  builds Silero and Smart Turn, and few tests import `voice` in a child process.
- 2026-11-02, step 7 (the settings builder's choices; step 13's review reads them): `VoiceSettings`
  is a frozen pydantic `BaseModel` that refuses extra keys, not a `BaseSettings`, so settings built
  in code cannot read anything. `from_env` reads `os.environ` itself, only the names under the
  prefix, matched in any case (two names in one source that differ only in case are refused, GP-06),
  and a `.env` through pydantic-settings' `DotEnvSettingsSource`. It also takes code values
  (`**values`), above the environment and the file, as the design's 7.2 orders its layers, though
  the design's signature lists only `prefix`, `env_file` and `unknown`: the Ole5 eval commands pass
  `env="dev"` that way. A blank value counts as unset under any name, since a `.env` copied from the
  old `.env.example` holds blank keys; M1's names (`T2V_VAR_DIR`, `T2V_LOG_LEVEL`, `T2V_LOG_FORMAT`)
  set to a value are refused with the name to use now. Set aside: `BaseSettings` with a loader
  subclass, under which an unknown name inside a group still fails with `unknown="warn"`.
- 2026-11-02, step 7: The environment checks follow the design's 7.4 to the letter:
  `server.dev_page` and `logging.content` are refused in test as in staging and prod, and DEBUG in
  staging and prod; they run at every load and again in `status()`. A join key and the TURN secret
  hold at least 32 bytes of printable ASCII with no space. An inline one is refused at load, one in
  a file (`join.keys_file`, `server.turn_secret_file`, as `groq.api_key_file`) when it is resolved,
  since loading settings reads no file: so Track F's lifespan resolves every configured secret at
  start, and a short secret in a file stops the server there, not at the first join. The join key
  file is one JSON object from key ID to secret, the form `T2V_JOIN__KEYS` takes, and a key ID
  matches `^[A-Za-z0-9._-]{1,64}$`. The values nobody gave are the builder's: `tts.timeout_s` 6.0,
  as `stt.timeout_s`; the limits in float seconds; a voice name `^[a-z][a-z0-9_-]{0,31}$`;
  `ice_servers` as stun:, turn: or turns: URLs with no credentials; each of `allowed_origins` a
  scheme, a host and a port only; and `*` refused in `forwarded_allow_ips`.
- 2026-11-02, step 7: The Ole5 eval commands pass the working folder's `.env` to `from_env` when
  `--env-file` names none, as M1's settings read it, so the owner's M1 command lines still work, and
  a run is always `env="dev"`, given in code, since it serves no caller. A run's history records
  every library setting (a secret or a file as set or not set), and `logging.level` and
  `logging.format` replace `log_level` and `log_format`, so comparing an M1 run with a new one lists
  those keys (the debt on `eval-compare`'s settings, paid before R7). `JoinRejected` carries the code `join_rejected` and no HTTP
  status, as every error below the outermost layer (GP-07); Track F's `api` maps it. The settings
  reference is docs/generated/settings.md, not the design's 7.7 path, as an earlier entry here says.
- 2026-11-02, step 8 (the logging builder's choices): `get_logger` returns a small
  `StructuredLogger` of the library's own on the standard library (`debug`, `info`, `warning`,
  `error`, each taking an event and its fields), and structlog is only the formatter of the handler
  `configure_logging` installs, so the console line is M1's byte for byte. The fields travel in one
  `extra` key, `record.fields`: a `LogRecord` refuses an extra key named like one of its own
  attributes, and the Ole5 app's events use `name` and `message` (the design's 10.2 now says so).
  `configure_logging(level, fmt, *, stream=None, loggers=(), content=False)` puts one handler on
  `t2_agentic_voice` and on each logger named, replaces the one an earlier call put, writes to the
  standard output of the moment unless given a stream, and unless `content` is on holds aiortc and
  aioice at WARNING through `hold_transport_loggers()`, which `voice` calls at start too, since it
  may not import `logging`. It never touches the root logger or `propagate`. `take_over` is removed:
  nothing called it. A command run with `python -m` logs as `__main__`, so the Ole5 app's loggers
  are `ole5_voice.LOGGERS = ("ole5_voice", "__main__")`; the guide's logging page (Track I's
  `tracing-and-logs.md`) tells a team to pass its package and `__main__`, and `examples/minimal`
  shows it. `serve()` runs uvicorn with `log_config=None`. No `exception`, `critical` or `bind`: a
  traceback is content-shaped.
- 2026-11-02, step 6 (the harness builder's choices): a `[[bans]]` entry names its scope by module
  prefixes in `within` (the library, a part of it, or an app), and ARCH-BAN reads `from a import b`
  as the module `a.b`, reporting every ban an import breaks, each with its own FIX; the library's
  bans are six tables, one per thing to do instead. From `pipecat.services` the library may import
  only `ai_service`, `settings`, `stt_latency`, `stt_service`, `tts_service` and
  `websocket_service`, what `stt_service` and `tts_service` themselves import in 1.15.0, which a
  test recomputes from the installed source. ARCH-BAN sees only the library's own imports (TD-043).
  The tests drop the new packages' variables by prefix where a package owns one (`PIPECAT_`,
  `LOGURU_`, `WEBSOCKETS_`, `UVICORN_`, `NUMBA_`, `LLVMLITE_`, `OPENAI_`) and by name otherwise, set
  `PYTHON_DOTENV_DISABLED=1`, and import nothing of the library before they drop them. A session
  fixture makes every aiortc peer built without its own ICE list raise, so a test builds one with
  `RTCConfiguration(iceServers=[])` (0.46 s more for a one-file session, as the builder measured
  it).
- 2026-11-02, step 10 (the types builder's choices, recorded in D-029 and D-035 or, for the ports,
  in the entry the fixes add after D-035): one close for every port that holds connections
  (`aclose()` on `SpeechToText`, `TextToSpeech` and `UsedTokens`). `AudioChunk` is mono 16-bit PCM
  and carries a response's usage, the rate-limit remainders on its first chunk and `cut_short` on
  its last, since one adapter serves every call at once; `check_language` sends no request, so a
  model whose terms are not accepted shows only at the first synthesis, which `t2v doctor
  --synthesize` checks. `IdentityVerifier.verify(token, *, join: JoinContext)`: the context carries
  `env`, the client's host and the runtime's used-token store, since the verifier is built with no
  IO before the runtime opens the store; `UsedTokens.use` is async and gives one True for two joins
  at once. `SignedConsent`, which only adapters may build (harness.toml's first `[[restricted]]`
  row), is the only consent that can let audio be kept. `UserTurnEnded.heard` is the transcript as
  text, since `core` cannot import `voice`.
- 2026-11-02, step 10: `t2v/1` follows the design's 5.5 where the step's list was shorter: the
  client's `hello` and the session's `ended` are added, duck, unduck and card wait for their
  milestones, the playback reports are one `playback` message, and an agent caption carries its
  `clause`. Inbound messages are parsed strictly (exact fields and JSON types, `v` the integer 1,
  client text at most 1024 bytes), and a refusal lists only pydantic's error types, never the
  client's text. The HTTP bodies are strict and bounded, carry no `pc_id`, and take the offer secret
  in the body or the `X-T2V-Offer-Secret` header; a secret is a `SecretStr`, revealed only when a
  response is serialized. A change to `t2v/1` changes the message list in the same commit.
- 2026-11-02, step 10 (the signatures builder's choices): `adapters/groq_client.py` holds all the
  set-up the Groq adapters share (the import inside `logging_unchanged` with the SDK's names
  re-exported, the limits, the user agent, the data flow, the request hook, the client, the failure
  mapping, the missing-key error and the settings' checks), so Track B copies none of it. The
  GroqTTS baseline is one Arabic text in ar-SA, pinning UTF-8 JSON with nothing escaped.
  `voice/session/io.py`'s events and commands are frozen dataclasses (internal, about 50 a second
  each way), and go beyond the step's list where Tracks D and E need it to build apart: `ListenIn`,
  `Connected`, `Ending`, `ClauseFailed`, a `Clock` with `SystemClock`, the phrase protocol,
  `EventSink` and `CallSetup`; `TurnOpened` carries the speech onset, so the 300 ms rule measures
  from speech, not from the turn's opening about 0.34 s later. `VoiceCalls` takes the agent, the
  settings and the services once and answers each call; `serve()` defaults to 127.0.0.1:7860 under
  `/voice`, and proxy headers are off while `server.forwarded_allow_ips` is empty and trusted only
  from those addresses otherwise. No deadline from offer to connected is written: Track E sets it
  and records it.
- 2026-11-02, step 10 (the facades builder's choices, in D-032): a name beyond the design's 5.1 is
  public only where a public signature names its type (`JoinContext`, `Event`, `ModelUsage`,
  `TurnRecord`, `TurnTimes`, `ClientConnection`, `TurnEnd`, `TurnTiming`, `EchoTiming`);
  `speak_digits`, `split_clauses`, `Pronunciations` and `pronounce` stay private until a public type
  takes them, since adding a name later breaks nothing. `test_facades.py` pins the root's names too.
  The fakes import no Pipecat at their top, and `capturing_output` subclasses Pipecat's
  `BaseOutputTransport`, so the stop test sees what a real transport sends; Pipecat 1.15.0's
  `audioop` DeprecationWarning is ignored for `pipecat.audio.utils` only.
- 2026-11-02, step 12: the entries are D-028 to D-035 (settings; serving and identity; GP-22, which
  also amends D-003's bullet on how a provider is chosen; the logging and loguru, with Q19 written
  as open; ARCH-BAN, the owners and the facades; the echo's shape; Whisper per user turn, Proposed
  whole, since the design's 13 names `SegmentedSTTService`; invariants 7 and 8 with
  `SignedConsent`'s row), each with one Proposed bullet. This plan holds the decision numbers 028 to
  049: another session's entry on the agent-led mode took the next number after that range on the
  main branch on 2026-11-02 (c83747b), so when this plan merges into the main branch, decisions.md
  keeps this plan's entries before it, and past 049 this plan takes numbers after it.
- 2026-11-02, the integrator's calls on the builders' open points, before the review: the `/join`
  consent-version check is Track F's: after `verify`, a `SignedConsent` whose version differs from
  `privacy.consent_version`, when that is set, is refused with `JoinRejected`; a plain `Consent`
  never records, so its version is not compared, and DevIdentity joins still work in dev; Track C's
  case "a consent version other than `privacy.consent_version`" is tested at `/join`.
  `core/tracing.py` is Track D's, with `core/tracing_tts.py`: it sets the design's 10.1 resource
  attributes. `api/static/` (`t2v-client.js` and the dev page) is Track G's: Track F's router serves
  it from a path its tests point at a folder of their own, and Track G tests that the built wheel
  ships the files. The FastAPI import at the package root is Track F's to remove. Track H's
  task rows share one line of CLAUDE.md, which holds 119 of 120. Before any track starts, Block 0's
  fixes split `voice/session/io.py` (375 lines) into its events, its commands and the rest, rename
  its phrase protocol so it is never taken for the design's root `Phrases`, give the declaration
  what Tracks A, D and F need from it (the design's 4.3 pronunciation map on `VoiceAgent`, and each
  preset's notice texts in Q5's register), and write the entry after D-035 for the ports' Proposed
  shapes, which step 12 left out.
- 2026-11-03, step 13's fix rounds, recording consent (D-035, Proposed beyond the design's 8.1): the
  review built a `SignedConsent`, which turns recording on, outside `adapters` in seven ways
  `poe arch` passed, so invariant 8 gets a seal checked at run time beside the static check. The
  seal, `CONSENT_SEAL` in `core/identity.py`, reaches the class as pydantic's validation context
  (`SignedConsent.model_validate(claim, context=CONSENT_SEAL)`, `SignedJoinTokens`' only way to
  build one) and is checked after every validation (`model_post_init`); the constructor,
  `model_construct` and a copy with an update always refuse, since a constructor keyword turns on
  pydantic's custom-init mode, under which `model_validate` calls `__init__` again without it, and
  pydantic validates neither of the others. The check of those fixes found five more ways, so the
  second round made `allows_recording` fail closed: it is true only for the very instance the seal
  validated, alive and unchanged since (a module-private registry of weak references and the fields
  as they were), so every copy, even one with no change, allows nothing, reversing the first round's
  "a copy with no change is the same consent". A `[[restricted]]` table also takes `files`, and a
  `names` row holds `CONSENT_SEAL` to `adapters/join_tokens.py` and `core/identity.py`, read from
  every token and literal in the library and the apps. `voice` asks `allows_recording(consent)` and
  never names the class. Set aside: a private flag on `Consent`, which no check sees. Under the
  owner's ruling of this date nothing more is built for consent.
- 2026-11-03, step 13's fix rounds, the settings (D-028 and D-029, Proposed beyond the design's 7):
  `server.forwarded_allow_ips` refuses a network wider than /8 (IPv4) or /32 (IPv6), and an entry
  with host bits set, and holds each IPv6 range that carries IPv4 addresses to IPv4's /8 inside it
  (/104 in `::ffff:0:0/96`, `::ffff:0:0:0/96`, `64:ff9b::/96`, `64:ff9b:1::/48` and `::/96`, /24 in
  `2002::/16`), since `0.0.0.0/0`, `::/0` or a whole mapped range trusts every peer's
  `X-Forwarded-For`, as `*` does. `join.max_clock_skew_s` is at most 60 (`MAX_CLOCK_SKEW_S`), since
  the allowance lengthens a token's life at both ends, and the used-token store keeps a token's
  `jti` until its `exp` plus that bound, whatever allowance is set, so a restart with a larger one
  reopens no replay, and never records as a first use a token past its last instant (Track C). Every
  load fails as `from_env` does, for settings built in code, `model_validate_json`, malformed JSON
  and an unreadable file too: one `ConfigurationError` naming each failing setting, with a FIX line,
  chaining nothing and echoing no value; a group built alone keeps pydantic's `ValidationError`, and
  assigning to or deleting a field of built settings raises a `TypeError` of fixed text with a FIX,
  the design's 7.4 read as covering loads. A group given to `from_env` as a dict merges key by key
  into what the environment and the file gave, and a group object, validated again, replaces its
  group. An origin is written as a browser sends it (a lowercase scheme and host, the host a DNS
  name, a dotted quad or a bracketed IPv6, no default port), its FIX stating that rule, not the
  canonical origin the ruling asked for, which would repeat the value (GP-19). The map settings are
  read-only `Mapping`s, hashable, since a `MappingProxyType` broke the copy and pickle of settings
  handed to a spawned process. `VoiceRuntime` checks the environment when it is built (Track F),
  since `model_copy(update=...)` skips validation.
- 2026-11-03, step 13's fix rounds, serving and `t2v/1`'s HTTP side (D-029, Proposed beyond the
  design's 4.5 and 5.5; D-031 and D-036): each `t2v/1` route (`/join`, `/offer`) answers 415
  `unsupported_media_type` to a body not sent as `application/json`, before it reads a byte, since a
  cross-site form or `text/plain` POST skips the CORS preflight; reads its raw body under a cap in
  bytes (413), each cap tied to its fields' bounds by a test that builds the largest valid body,
  every field it counts printable ASCII, so JSON writes each character in at most two bytes; and
  parses the body itself with `model_validate_json`, never as a FastAPI body parameter, whose 422
  echoes the input, a refusal naming pydantic's error types only. `/join` first reads the body's
  `protocol` alone, leniently: any value but 1 answers 400 `protocol_mismatch`, with its notice, and
  spends no token. Every error is one `ErrorBody` (a code from a closed list of twelve, a message
  safe to show, a notice only for a protocol mismatch, a random reference the router logs), listed
  per route and status in `BODIES` and the `t2v/1` fixture, so Tracks F and G build against one
  shape; set aside: FastAPI's `{"detail": ...}`, with no code or reference. 400, not 422, since the
  route parses; no 404, since the secret is checked first and no answer shows whether a call exists.
  The call's own secret gets a 409, never a 403: `already_offered`, and the quiet `not_offered`
  before voice answered, `ice_completed` and `call_ended`; `forbidden` is for a secret missing,
  wrong or not this call's. The router drops a join never offered once its token's window has
  passed, and an answered call's record `FORGOTTEN_KEPT_S` (60 s) after voice forgets the call, so
  its records stay bounded. `serve()`'s CORS allows `content-type` and `X-T2V-Offer-Secret`. The
  Groq request hook checks a body only on a request that carries one, so the model list's GET
  (`check_language`, `t2v doctor`) goes through the one client, and keeps the SDK's raw-response
  marker only for the adapter's own raw call, so `GroqSTT` fills `Transcript`'s headroom (D-036),
  which the first round could not. A log field named like a line key is written `field_<name>`, and
  the console line writes a value holding a control, format or separator character as its repr, so a
  log call never raises and no value forges a line (D-031).
- 2026-11-03, step 13's fix rounds, the session (D-037 and D-038, Proposed beyond the design's 5.5
  and 6.6; D-039), amending the entries above on speech that starts while the echo plays and on the
  language live calls send Whisper: `voice/session/io.py` (375 lines) is split into
  `session_events.py`, `commands.py` and `io.py` (the protocols, the clock, `CallSetup` and the
  rules both sides meet by), its phrase protocol named `PhraseAudio`. The agent speaks in replies,
  which the session numbers from 0 apart from the caller's turns (the greeting, said once connected,
  is reply 0; each echo and each spoken notice the next), so the greeting and turn 0's echo never
  share a key; set aside: one numbering for both. A reply names the turn it answers in `Speak` and
  the agent's caption only, since the session knows the rest. The drop rule covers every reply: a
  turn whose speech began while any reply played, the greeting included, or within 300 ms after a
  reply's last `ClausePlayed`, is not answered, but is still closed, transcribed and kept; so a
  file-fed call feeds silence until its greeting has played, then the clip's lead. Set aside: the
  echo alone, under which the greeting leaking past the browser's echo cancellation on laptop
  speakers would be said back; and the browser's playback report as the 300 ms's start, a jitter
  buffer later and never in a file-fed call. A stop drops every clause asked for so far, whatever
  its reply, as Pipecat's interruption drops every queued frame; no event of them follows, a
  request's report the Pipecat side still held included (TD-055), and a dropped `ended` notice hangs
  up at once. A call's language is fixed at join: the caller's pick (`JoinRequest.language`), else
  the token's `locale` (its exact tag, then its primary subtag), else the agent's first language;
  set aside: a `t2v/1` message to switch in the middle of a call, which the echo cannot use. When
  the call ends (an `Ending`, a `TransportFailure` or the session's `HangUp`) the Pipecat side drops
  an open turn's audio and cancels a request in flight, the turn kept as unfinished; set aside:
  flushing it, which bills a request and hands an event after `HangUp`. Every request is counted
  from its report as it goes (`Transcribing`, `Synthesizing`), a cancelled one included, and the
  call's stream ends with `Session.aclose`, which writes the report. `voice` forgets an ended call
  once its peer has closed, `api` keeping its own record, rather than after a time nobody gave
  (GP-16). A client message's 1024 bytes are counted on the message as the session gets it: on a
  call's path, the object Pipecat parsed, written back as compact JSON, a key held twice keeping its
  last value (TD-054).
- 2026-11-03, step 13's first fix round, the declaration (D-033, Proposed beyond the design and Q3):
  `VoiceAgent` takes the design's 4.3 pronunciation map (`pronounce=`, its inner keys `ar` or `en`
  checked at run time, so a map built in a plain `dict` type-checks), public in `languages` with
  `pronounce`, `split_clauses` and `Pronunciations`, which the step-10 entry on the facades had kept
  private until a public type took them. Each preset gives the echo's frame and each notice's text
  (`busy`, `error`, `ended`): `ar-SA`'s in the Saudi register Q5 chose for M2's fixed phrases,
  `ar`'s in Modern Standard Arabic, the register that preset names (the design's 5.2), and `en`'s in
  English; the Arabic frame, shared by both Arabic presets, stays Saudi. This is the agent's reading
  of Q5, which `domain/presets.py` cites; the owner may ask for Saudi notices on `ar` too. A call
  speaks `error` and `ended` from the phrase cache as its next reply, so they play even when
  text-to-speech is rate-limited (the design's 10.4), and never `busy`, which admission control
  answers at join. An agent's name, which names its folder under `storage.var_dir`, refuses the
  names Windows keeps for devices (`con`, `prn`, `aux`, `nul`, `com1` to `com9`, `lpt1` to `lpt9`),
  since the owner develops on Windows, where the review found a folder named `nul` cannot be
  written. A failure to build a declaration is a `ConfigurationError` naming its first failing
  field, never its value, with a FIX line, since a declaration is code the team reruns at once; set
  aside: the settings' collected shape.
- 2026-11-03, step 13's second fix round, the fixed phrases (D-033, Proposed; D-032 for `stores`):
  at the runtime's start `PhraseCache.declare(agent)` says each fixed phrase (each language's
  greeting, echo frame, and `error` and `ended` notices) through the agent's pronunciation map, and
  sends only `provider_text`'s form of it (`domain/text/invisible.py`: the no-break spaces U+00A0
  and U+202F sent as spaces, the joiners U+200C and U+200D and the marks U+200E, U+200F and U+061C
  dropped), keying its file on that text, the model and the voice and keeping it under the phrase as
  written, which captions show; a phrase holding any other control or format character, a line or
  paragraph separator, a lone surrogate, or a space but U+0020 and the no-break spaces, is refused
  at declaration, since pasted text carries such characters unseen. A phrase longer than `max_chars`
  is cut with the clause splitter and packed greedily into requests of at most `max_chars`, about n
  / `max_chars` for n characters, sent one at a time, so the runtime refuses no greeting or notice.
  A request refused as rate-limited waits the delay the provider asked for, at most 60 s
  (`MAX_RETRY_DELAY_S`, and that bound when it asked none), and is sent again at most twice
  (`RETRIES`), the agent's bounds; the next refusal fails `declare` with a `ProviderError`
  (`rate_limited`) naming the phrase's kind and language, never its text. The session applies the
  same map to a reply before it cuts it, and the agent's caption shows the said form. `PhraseCache`
  is public through `stores`, so a timing run builds the phrase audio its file-fed calls play as the
  runtime does, `testing` never importing `adapters`. Set aside: one request a clause, a burst at
  start that Groq's published 10 a minute refuses; refusing a long phrase at start; a default delay
  of the cache's own, a number nobody gave (GP-16); and the text-to-speech adapter applying the map,
  as the design's 3.1 gives it, under which a request could pass `max_chars` after the map.
- 2026-11-03, step 13's first fix round, the harness (D-032, Proposed beyond the design): a
  `[[bans]]` row on part of a package follows that package's own imports through the modules the ban
  does not cover, `TYPE_CHECKING` imports included, so `voice/session/` cannot reach Pipecat through
  another `voice` module (Track D: no session module imports `voice/calls.py`, whose factories name
  Pipecat's types); set aside: a list of what the session may import, which breaks at its first new
  import. A `within` that names no module is a HARNESS-CONFIG problem at load. The library also bans
  Pipecat's other LLM machinery and, in a table of their own, its modules that reach an outside host
  (`pipecat.transports` whole, Small WebRTC and what it imports allowed), and RTVI beside DTMF;
  `tests/harness/test_installed_pipecat.py` requires every installed Pipecat module that imports an
  HTTP or websocket client or a banned module to be banned or reviewed with its reason. Every
  library class a public signature names is public: the twelve settings groups, `TtsVoice` and
  `StructuredLogger` join the package root, beside `VoiceSettings` and `get_logger` (the design's
  5.1), so a team builds typed settings from one module; set aside: a split by topic, which leaves
  some groups with no facade, and a new `settings` facade, a design change for the owner. The second
  round's harness fixes were dropped by the owner's ruling of this date (TD-049).
- 2026-11-03, the owner's ruling on what matters ("The owner's decisions"): from Block 0's last
  round on, a review reports only what would break, hang or crash a call; garble, cut, overlap or
  lose its audio; leak a task, connection or memory per call; send Groq more than the limits
  allow or fail on a 429 it could wait out; refuse valid Arabic or English text; or leave a later
  track or milestone a contract it cannot build on. One reviewer per block or track, each finding
  checked by one skeptic; everything else is a row in `docs/plans/tech-debt.md`, and there is no
  second fix round unless a high finding stands. Step 17's whole-plan review, neither a block nor
  a track, also has one reviewer: the agent's reading. Block 0's round 2 drops the harness
  builder (more loader forms in the architecture checks) and the full recheck, and the findings
  the harness builder would have fixed are TD-049. The consent the join token carries,
  `privacy.record_audio` and what Block 0 built for them stay as they are, and nothing more is
  built for them; Q7 is settled as (a), (i) and (iv). The Proposed security rules beyond the
  design (the 32-byte floor, the 60 s skew cap and the rest) stay Proposed in their decision
  entries and are not put to the owner in M2.
- 2026-11-03, the owner's ruling on the deployment ("The owner's decisions"), amending the entry on
  one plan for M2: the deployment leaves M2, and its text, as drafted, is kept in "The deployment,
  moved out of M2", a plan of its own once the owner has the server, and at the latest in M6.
  Every M2 call is local, on this laptop, through the Ole5 app's dev server on localhost. Track C
  builds identity and stores; `adapters/turn_credentials.py` stays a stub and Block 0's TURN
  settings stay in the code, unused, both in TD-048. So Track F's `/join` mints no TURN
  credentials and returns `server.ice_servers` as set, since a join that reached the stub would
  fail. TD-004 followed Q8's host (the entry on the debt paid in M2), so it waits for the
  deployment's plan, with TD-015, whole, and TD-038's test, which lands where TD-004 changes the
  clients. The entries on the deployed backend's `env=staging` and on TURN for a network that
  blocks UDP stand for that plan, as do two texts of D-029, which decisions.md, append-only, keeps
  as written: `/join` answers the ICE servers "with per-call TURN credentials when a TURN secret
  is set, inline or in its file", which M2's `/join` does not mint (TD-048), and plan 003's
  network test decides the media path.
  The agent's choices in applying the ruling: the registration's C is five local calls (the
  Bluetooth headset in Chrome, as Q18 recommends, and the speakers and the wired headset in Chrome
  and in Edge) and the budget about $0.80, both amended before any run; the widget page's
  `frame-ancestors` is `'none'` while no website origin is set; Q4's access code and guard serve
  the local calls; and three things wait for the deployment's plan: the decision entry on Ole5's
  identity answer (Q12), `client_stats`'s relay fields, which no local call shows, and the lock
  file's Linux case, unless CI (TD-001) runs it first.
- 2026-11-03, Q19, under the owner's ruling of this date ("The owner's decisions"): Track E does not
  wait for Q19. `off`, the default, behaves as Q2 settled it whatever the answer, and Block 0's
  settings take only `off` (`core/settings/logs.py` refuses `forward`), so Track E builds only
  `off`; `forward` is built only on the owner's answer, in a block of its own: as (a) if the owner
  picks it, or, under (b), the agent's recommendation, when a team asks. The question stays the
  owner's, and D-031 keeps `forward` waiting on it.
- 2026-11-03, the integrator's rulings on what step 13's builders left to it, beyond the entries
  above:
  - Every route the router serves answers "runtime not started" while the lifespan has not run,
    `/health`, `/ready`, the client script and `/dev` included, as the design's 4.5, D-029 and the
    router criterion say; the second round's router contract (`api/runtime.py`) says it of the
    `t2v/1` routes alone, so Track F widens it (its section).
  - A request's report the Pipecat side still held when a stop dropped its clause is not handed, as
    `voice/session/io.py`'s stop path, `StopSpeaking` and `FakeSessionIO` say, so that request goes
    uncounted, though after the call's end such a report still comes (the gap the session builder
    named). It breaks no call and blocks no track, and the fakes are Block 0's, so Tracks D and E
    build to the contract as merged, and TD-055 holds the fix, a request's report exempt from a
    stop's drop as from the end's, for before M6's cap reads the counts.
  - Track B's 429 test wraps `FakeTextToSpeech`, whose `failures` fail every request for a text, in
    a fake of its own that fails once, so Block 0's fakes stay as they are and no debt row is
    needed.
  - `check_language` sends no synthesis request and asks Groq for the model list (a GET), as the
    port's docstring and D-036 say; the step-10 entry above, "sends no request", means no synthesis.
  - The session's half of the pronunciation map is in `voice/session/call.py`'s contract, which wins
    over `domain/text/pronounce.py`'s docstring (the rule of "## Tracks"); a reply's clauses are
    captioned as said, a fixed phrase as written.
  - `voice/file_transport.py`'s, `testing/turns.py`'s and `testing/echo_timing.py`'s words that the
    models load once for every call or clip predate the per-call detectors of `voice/calls.py`,
    which win; Tracks E and H bring their stubs' words to it.
  - Accepted as built, each wider than its ruling in the same direction, or a means the ruling left
    open: a star import from any module of the seal's files or layers reported, and the seal's names
    scan run over the apps; a lone surrogate refused in a fixed phrase, which no UTF-8 request can
    carry; `turn_ends`' call given silent phrase audio rather than an option for a call with no
    greeting, so D-037's set-aside holds; `Session.aclose()`, which ends the call's stream once the
    Pipecat side has handed the last request report that went before the end: after the end only
    request reports come, and after `aclose` nothing; SECURITY.md brought to the settings fixes at
    the three places their findings named; and the consent tests split under ARCH-SIZE.
  - Two criteria are brought to Block 0's contracts, which a docstring never overrides (the rule of
    "## Tracks"): the languages criterion keeps a clause within `max_chars`, cutting inside only a
    word longer than that (`domain/text/clauses.py`), and the echo-session criterion's stop drops
    every reply asked for so far, the greeting's and a queued notice's included
    (`voice/session/io.py`).
  - Step 30 corrects only the design's factual slips: the sections D-028 to D-039 go beyond as
    Proposed get no note in italics, since the entries hold each departure until the owner rules
    ("The owner's decisions"), and 16.3 names the entries.
- 2026-11-03, Track A (speech text), the builder's choices:
  - A mark ends a clause only where it ends a word: "3.5", "12:30" and "t2.example" stay whole.
  - A word is a run between any Unicode spaces, joined by one: a clause is measured as sent.
  - A clause with no letter, number or symbol is dropped: its request would say nothing.
  - The splitter only cuts; packing is the phrase cache's and, since D-1's fix, the echo's.
  - `speak_number` drops English commas and joins Arabic's lone waw: a number stays one clause.
  - The ID cues are whole words; the Arabic ones match with or without tatweel, after waw or feh.
  - `speak_digits` spaces a letter its run touched ("T2" says "T two"); no M2 path calls it.
  - The map's whole-word rule reads a form's ends, so the design's "LT-" is found in "LT-00423".
  - The map matches case as written ("us" never takes "US"'s entry): a team lists each form.
  - The map runs in one pass, longest form first, so a said form is never mapped again.
- 2026-11-03, Track C (identity and stores), the builder's choices:
  - A token's times are checked on the verifier's own clock, PyJWT's being one no test can set.
  - A lifetime over the verifier's `join.ttl_s` is refused, so a website mints within it.
  - Claims parse with `extra="forbid"`: `nbf`, `aud`, `iss` and a team's own claims are refused.
  - The `kid` header is required: a token with none is `unknown_key`, never tried on every key.
  - The claims are checked before the store is asked: a token they fail spends no `jti`.
  - Each refusal has a fixed message and a `reason`, from `malformed` to `used`, chaining nothing.
  - Each store prunes inside every `use`: no background task per call or per runtime.
  - SQLite in a worker thread, one `BEGIN IMMEDIATE` a `use`: one True across threads and files.
  - `mint` leaves out an unset `name`, `locale` and `attrs`.
  - `DevIdentity`'s loopback is 127.0.0.0/8, ::1 and mapped IPv4; a name (`localhost`) is refused.
- 2026-11-03, Track B (the Orpheus adapter and the phrase cache), the builder's choices:
  - `tts.timeout_s` bounds each phase of a request, not the whole take, which a deadline could cut.
  - Audio is yielded as it comes, an empty last chunk only to carry a flag or the headroom.
  - The cut-short rate is read from the first sound: Orpheus's 0.4 to 0.7 s lead would hide cuts.
  - Every byte after the WAV's data head is audio, as in the prototype: a stream has no size.
  - The terms' FIX goes in `details["fix"]` and a note, a `ProviderError`'s message being fixed.
  - A language with no voice fails `synthesize` as rejected, which a call sees as `ClauseFailed`.
  - `PhraseCache` takes `keep_files`, set from `tts.cache_phrases`, which the stub could not say.
  - A take cut short is kept in memory, never on disk, where it would cut that phrase in every call.
  - `declare` counts every request sent, a refused one sent again included, as Groq's limits do.
  - A phrase file that is not a readable WAV is synthesized again and replaced, rather than failing
    the start.
- 2026-11-03, Track D (the voice session in echo mode), the builder's choices and its fix's:
  - The 10.1 resource attributes go on each trace's root span, a team's provider keeping its own.
  - The settings digest leaves out each field whose type holds a `SecretStr`, and its `_file`.
  - `CallTrace` lives in `core/tracing_tts.py`, so `voice` names no OpenTelemetry type.
  - A turn's times run from the end of the caller's speech (the design's 10.3), clamped at 0.
  - The echo starts once the transcript is in, whether `TurnClosed` came before it or after.
  - The drop window runs from a reply's first `ClauseQueued` to its end plus 0.3 s.
  - A dropped turn stays in the report and timeline, with no caption, `UserTurnEnded` or metrics.
  - A notice shows only as its `notice` message; heard clauses are captioned as said.
  - `played_fraction` counts characters: a clause not yet synthesized has no known length.
  - An echo gives at most one `error` notice; with `ended` pending, no new turn is answered.
  - `limits.idle_s` counts from the last `TurnOpened` or `TurnClosed`; an open turn holds it off.
  - `ended` goes before `HangUp`, but not after `caller_left` or a transport failure: no channel.
  - The `state` messages are worked out from what happens and sent only when they change.
  - Usage reports both models, zeros when unused; a report after the end or a cut still counts.
  - A fixed phrase the cache lacks is logged `phrase_not_declared` and unsaid, never requested.
  - The report file is `var_dir/reports/<call ID>.json`, under no agent's folder.
  - Under ARCH-SIZE, `Speaker` went to `playback.py`, and the docstring's test list to the tests.
  - D-1's fix: the echo packs its clauses greedily into requests of at most `max_chars`.
  - D-1's fix: at most `MAX_ECHO_REQUESTS` (3) an echo, about 40 s of English; the rest is unsaid.
  - D-1's fix: `call.py`'s contract says so, one `Speak` and one caption for each packed request.
- 2026-11-03, Track E (the Pipecat modules), the builder's choices and its fix's:
  - Each call has its own `WorkerRunner` and `PipelineWorker`: no call's end reaches another.
  - The peer is built through a request handler of each call's own, so `voice` imports no aiortc.
  - The F7 guard refuses an offer with no UDP `a=candidate:` line; the 20 s deadline ends the rest.
  - With `turns.smart_turn` off, every pause the detector hears ends the turn.
  - `speech_ended_at` is the detector's last stop, so registration E's steps are read from it.
  - An exception that is not a `ProviderError` fails its turn or clause as `server_error`.
  - A clause's context opens at its first audio: Pipecat 1.15.0 errors on a context with none.
  - `ClausePlayed` comes when the clause's stop frame leaves the output, seen by a tap after it.
  - `Send` goes straight to the output's `send_message`, so Pipecat's CancelFrame at a hang-up never
    discards `ended` (its SCTP stop still can: TD-075).
  - After an `Ending` or a `TransportFailure`, the session has 1 s to hang up before teardown.
  - Voice emitted `ProviderFailed` and `TransportFailed` for what its bridges and transport saw;
    superseded by d69bac8, the session sending the events of what it is handed and voice only a
    speech bridge's error frame's `ProviderFailed`.
  - `VoiceCalls.start` warms the factories it is given, so a test's fakes load no ONNX model.
  - The file-fed pacer keeps one `asyncio.sleep` a frame, not the spike's at 43% of a core.
  - E-1's fix: the bridge, not Pipecat's output, cuts the audio into whole 40 ms chunks.
- 2026-11-03, Track F (`api`, the CLI and `examples/minimal`), the builder's choices:
  - A call takes one offer: a second `POST /offer` gets 409 even after voice refused the first.
  - An offer that crashes `Calls.answer` gets 500, and the call is ended: none is half-started.
  - `/dev` is served in `dev` only with `server.dev_page` on or under `t2v dev`; else a plain 404.
  - `/dev` sends `frame-ancestors 'none'`, nosniff, no referrer, the microphone policy, no-store.
  - `/health` answers `{env, calls}`, the calls counted from the router's records.
  - The offer secret may be in the header and the body only if both agree, compared as bytes.
  - `join_rejected`'s message is fixed, so a team's verifier never puts a value in a response.
  - One lock per `var_dir`, a second runtime of the same process refused too (D-029).
  - The lifespan resolves every secret at start, and imports the adapters only there.
  - The observers run in order on one task, each event within 10 s, at most 1000 queued.
  - `serve()` always adds CORS, runs `lifespan="on"` and passes `forwarded_allow_ips` as a list.
  - `t2v APP` is `module:function`; `settings show` is always redacted, each `_file` path too.
  - `t2v doctor` takes no APP and checks each `tts.languages` tag; its clock line is unmeasured.
  - `examples/minimal`'s `make_runtime` passes `DevIdentity()`, since `serve()` needs a source.
  - The package root's FastAPI import is gone, by lazy names there: `test_public_types` reads
    `APIRouter`.
- 2026-11-03, Track G (the browser client, the widget and the Ole5 app's server), the builder's
  choices:
  - The dev page holds no script or style of its own, so any policy `/dev` sends keeps it working.
  - The client opens the microphone before it asks for a token: a missing one spends none.
  - Candidates go by PATCH once `/offer` answered, the end marker last; the secret in the body.
  - `playback` reports are read from the agent audio's level after each caption, approximately.
  - The client ends the call when the session closes the channel, freeing the microphone at once.
  - Q4's guard lives in the app's process, so a restart begins every count again.
  - The token's caller is `Caller(subject="owner")`; the body takes only `code` and `consent`.
  - The Ole5 server has no `DevIdentity` fallback: it refuses to start without the access code.
  - The app's settings read `OLE5_VOICE_` with `extra="ignore"`, one `.env` holding both prefixes.
  - uvicorn runs the app on `asyncio:SelectorEventLoop` (item 20), UNVERIFIED in a running server.
  - Ole5's agent is declared in `server.py`: `ole5`, `ar-SA` then `en`, its map holding "Ole5".
  - The consent screen is the agent's draft of Q7's (a), `m2-owner-test-1`, its box unchecked.
- 2026-11-03, Track H (the measurement's tooling), the builder's choices:
  - Orpheus's first sound is when the chunk with its first sample above the floor came.
  - The noise floor is 328 of 32768 on one sample, the agent's value, UNVERIFIED until T1.
  - The frame's first audio is the first output frame at or after its `ClauseQueued`.
  - `echo_timings` counts usage from the call's events: `feed_file` may return before the report.
  - The secondary set runs only with the pipeline on dev, its true end the last speech stop.
  - A pipeline run of `poe eot` appends an end-of-turn line; a reference run appends none.
  - A timing run calls `echo_timings` once a variant, so its pacers and retries act between them.
  - The phrase cache's one request count goes on every Orpheus model's pacer, conservatively.
  - A timing run is dev only, refusing `tts.trim_silence` on and a live language but `session`.
  - Its agent is the app's `ole5-timing`: Saudi and mixed items held in `ar-SA`, MSA in `ar`.
  - Compared runs may always differ in `stt.model`, `run.cap_usd` and `run.smoke_only`, no other.
  - A manifest's consent version comes from the command line, the recorder's layout no contract.
- 2026-11-03, the criteria a track could not meet alone, and who meets them (the rule of
  "## Tracks"; the agent's reading, which the owner may overrule):
  - "The fixed phrases declared at lifespan start": Track B tests that only `declare` writes and
    that a heard text sends and writes nothing, Track D that the session asks the phrase audio for
    fixed phrases only; that the cache's folder holds no new file after an echo turn is step 16's
    test.
  - "Invariant 8: Pipecat's loguru output is off": Track E tests `import t2_agentic_voice`, the
    banner and the DEBUG line; `t2v --help` writing nothing to stderr is Track F's child-process
    test of every command's help (`tests/t2_agentic_voice/api/test_cli.py`, an empty stderr
    asserted), met with F's merge.
  - "Ole5's widget in `apps/ole5-voice-agent/web/`": `/dev`'s headers are the router's (Track F),
    and Track G asked for its policy; after the merges of F and G the integrator sends Track G's
    `default-src 'none'; script-src 'self'; connect-src 'self'; img-src data:; base-uri 'none';
    form-action 'none'; frame-ancestors 'none'` with Track F's other headers, and tests each through
    the real router.
  - "The owner's calls through the widget are recorded": the token's round trip, a token from the
    Ole5 app's `/token` verified at `/join`, its consent recording only with `privacy.record_audio`
    on, is step 16's (Track G tested `/token` against a fake minter, Track F `/join` against a fake
    identity).
  - "One trace per turn": no join token, offer secret or access code in an exported span is
    step 16's, end to end; the session receives none of the three, so Track D tested the settings'
    secrets.
  - "`uv run poe eot` measures end of turn offline": `turn_ends` and `echo_timings` are tested
    against a fake `VoiceCalls` and `feed_file`; one check through the real `feed_file`, possible
    since E's merge, is TD-081.
- 2026-11-03, criteria read as the tracks built them (the rule of "## Tracks"; the agent's reading,
  which the owner may overrule):
  - "`t2v serve`, `t2v dev`, `t2v doctor`": doctor prints this machine's UTC time and
    `join.max_clock_skew_s` without measuring the skew while every join token is minted on this
    laptop; the deployment's plan measures it (TD-067).
  - "One trace per turn": the design's 10.1 resource attributes, on each trace's root span, carry
    the agent's name in place of its fingerprint and version until the talker builds them (TD-069).
  - "The router serves `POST /join`": `/dev` also needs `server.dev_page` on, the setting whose
    description says the router serves it, or `t2v dev`, which turns it on; with the setting off,
    `/dev` is a plain 404.
  - "Invariant 8: Pipecat's loguru output is off": its failures become `TransportFailed` or
    `ProviderFailed` events once each. Track E's `voice/pipecat_events.py` and Track D's session
    both sent them, which d69bac8 settled: the session sends the event of every failure it is
    handed, and voice's Pipecat side logs each failure and sends only a speech bridge's error
    frame's `ProviderFailed`, which reaches no session event.
  - "`HeardWords` is in `[[restricted]]`, built only in `voice`, from the commit that creates it":
    Track D created it (b1187b1), but `harness.toml` is Block 0's file, so its row came with the
    integrator's d4cadca, after the merges, where `poe arch` passes on all eight tracks' code; the
    criterion is met from d4cadca.
  - "The voice session in echo mode": each turn is said back in at most `MAX_ECHO_REQUESTS` (3)
    requests of `max_chars`, about 40 s of English, the rest unsaid (D-1's fix, in
    `voice/session/call.py`'s contract).
  - "Ole5's widget in `apps/ole5-voice-agent/web/`": the pane's check of the data channel gives the
    page a silent stream in place of the microphone, which the client opens before it joins
    (Track G; step 16).
  - Not a criterion: registration T's Orpheus count, one request a heard turn and 40 Arabic a run,
    holds since D-1's fix, a dev paused request being one packed request; it is not amended.
- 2026-11-03, the owner's ruling to finish M2 faster ("The owner's decisions"): what replaces each
  dropped measurement and where each moved item goes, the agent's reading, which the owner may
  overrule:
  - The time of each step: T1 and T2 are dropped. Each turn's report and trace in the owner's
    session give `stt_ms` (the speech's end, Silero's last stop, to the transcript: Smart Turn's
    decision and Whisper together), Whisper's request (its speech-to-text span, sent to answered),
    `ttfa_ms` (to the echo ready, not heard: TD-063) and `tts_first_audio_ms` (the echo's Orpheus
    request to its first audio); E1 gives the VAD stop delay and Smart Turn's decision, offline. No
    M2 number is left for Orpheus's first sound or leading silence, which no report holds, or for
    the timing's noise between two runs: M4's latency target is registered on its own plan's data.
  - Requests per call minute: from the session's reports (`CallReport.requests_per_minute`, in each
    report file and on each call's root span), recorded as a decision entry beside the published
    limits, or the real ones if the owner reads them. D-018's answer 21, the key's real limits read
    in M2, becomes the owner's option (Q17); M6 compares the rates with the key's limits when it
    sets the cap on live calls (the roadmap's M6).
  - The language a live call sends Whisper: R5 to R7 and Q15 go to M3, whose plan repeats the noise
    on another day anyway (TD-032, the roadmap's M3), with TD-011's reading of Groq's `language`; M2
    keeps `stt.live_language = "session"`, so a call sends Whisper the language its caller picked.
    The prompt arm for product terms (Q16) goes to M4, with the vocabulary that becomes the prompt.
  - The calls: the first calls and run C are one recorded session (step 18), in Chrome. Edge stays
    supported (D-018), but M2 does not check it; the Bluetooth headset, which no criterion names,
    goes with the five calls, so M3's plan records its own call if the Bluetooth warning needs one.
    C's listening sounds stay, one in each Arabic call during an echo, so M3's check that listening
    sounds do not interrupt the agent has M2's recordings to run on.
  - The whole-plan review (step 17) is dropped for this plan, against the plans README's default of
    a review of the whole plan before the integration branch merges ("Parallel tracks", item 5):
    each track had its review, and step 16's end-to-end test and the owner's session check the
    whole.
  - The budget: about $0.34 against Q13's $1 ("The budget"). `poe eval-timing` and its pacers stay
    in the code, unrun: TD-063's first byte and noise floor, TD-071 and TD-082 wait for a timing
    run, if one is ever run, and TD-081 keeps its E1 part as its trigger. TD-063's cut-short
    ceilings do not: `GroqTTS` flags live takes with them and the phrase cache keeps no flagged
    take, so they are recalibrated when a take of the session, or of a later call, shows one wrong,
    or in M4's plan.
  - Step 30's corrections of the design run beside the session, by an agent. The design's 3.2 stays
    listed as not confirmed: the owner reported accepting the terms, not who could accept them.
- 2026-11-03, the integrator, after Track I and step 16:
  - Step 16's by-hand check ran with the tests' fakes from a scratch script, since `t2v dev` takes a
    factory and none builds fake providers; a dev factory is debt, not built now, the owner's
    session being the check that counts.
  - A test that runs real aiortc peers runs on the selector loop, as `serve()` does: the Proactor
    loop's hanging closes are not the served path's.
  - For step 30's list of the design's factual slips: its 4.2 says `t2v dev` reloads on a change and
    prints a trace link per turn; `serve_dev` does neither (Track I's gap).

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
    approves; no step before 19 depends on it. The owner's ruling of 2026-11-03 (below) moved
    it out of M2 instead.
- 2026-11-03, after Block 0's second fix round had run long: "This is taking longer than I
  expected. Focus on things that matter for the next milestones and that we will need to build
  the voice agent. A consent for my or my team recordings is not a concern." So, in the agent's
  reading:
  - Reviews from now on (Block 0's last round, each track, the whole-plan review at step 17)
    report only what would break, hang or crash a call; garble, cut, overlap or lose its audio;
    leak a task, connection or memory per call; send Groq more than the limits allow or fail on a
    429 it could wait out; refuse valid Arabic or English text; or leave a later track or
    milestone a contract it cannot build on. One reviewer per block or track, each finding checked
    by one skeptic; everything else becomes a row in `docs/plans/tech-debt.md`, and there is no
    second fix round unless a high finding stands.
  - Block 0's round 2 drops the harness builder (more loader forms in the architecture checks)
    and the full recheck; what it found goes to a debt row (TD-049).
  - Recording consent: the consent the join token carries, the `privacy.record_audio` setting and
    what Block 0 built stay as they are, and nothing more is built for them. Q7 is settled as the
    agent's (a), with a one-line recording box the agent drafts (version `m2-owner-test-1`); the
    recordings kept under `var/` on this laptop, its (i), the laptop being the host now; and the
    local Phoenix kept as M1's, with no retention setting, its (iv).
  - The Proposed security rules beyond the design (the 32-byte floor, the 60 s skew cap and the
    rest) are not put to the owner in M2: they stay Proposed in their decision entries.
- 2026-11-03, the agent's question "Move the deployment and network tests to when the server is
  available?", answered "Yes, move them". So, in the agent's reading:
  - The deployment leaves M2: its criteria (all five, the TURN credentials and the guard on the
    shared key before the first deployed call among them), steps 19 to 22, Q7's host parts, Q8's
    remaining parts, Q9 to Q12, "What the owner does" steps 4 to 6 and 8 and the network parts of
    step 7, and every registration or measurement text that needs a call from another network or
    the host. Their text, as drafted, is kept in "The deployment, moved out of M2", which becomes
    a plan of its own as soon as the owner has access to the server, re-planned for that server
    (its host facts, Q8 to Q12), and at the latest in M6.
  - TURN credentials leave Track C, since they depend on Q9: Track C is identity and stores.
    Block 0's TURN settings stay in the code, unused until the deployment, as a debt row
    (TD-048), which also names the stub `adapters/turn_credentials.py`.
  - The calls stay local, on this laptop, through the Ole5 app's dev server on localhost: the calls
    of step 18, and run C's recorded calls (Q18's script on each device, the laptop's speakers and
    the wired headset, in Chrome and Edge), with no network variants. The owner's ruling of
    2026-11-03 (below) made them one recorded session in Chrome.
  - The roadmap's M2 is "A call that listens and speaks", its *Done when* without the deployment
    and the other networks, and its M6 names the move. The design, approved, is not edited now:
    step 30 corrects each of its lines that names M2's deployment, as a fact.
- 2026-11-03, after the tracks' merges: "I do accept the Groq agreement, and I don't know about the
  real key limits. But I want to finish with M2 Faster than you stated. Can we drop unnecessary
  things in the plan and focus on the fundamentals for the package?" To the cuts the agent then
  proposed, the owner answered "Yes, cut them". So, in the agent's reading:
  - T1 and T2, the time of each step on the golden set, are dropped: the time of each step comes
    from the traces and call reports of the owner's recorded session, which record each turn.
  - R5 to R7 (the language a live call sends Whisper) and the noise on another day (TD-032) move to
    M3, which needs the noise runs anyway, with Q15; M2 keeps `stt.live_language`'s default,
    `session`. Q16's prompt arm for product terms moves to M4.
  - The first calls (step 18) and run C become one recorded session of about 20 to 30 minutes:
    Chrome, the laptop's speakers then the wired headset, a few turns in each language (Saudi
    Arabic, MSA, English), Stop and Esc once each, recorded (`privacy.record_audio` on, a signed
    join token with the consent, through the Ole5 app's dev server and its token route with the
    access code, Q4 and Q7 as settled). Edge is dropped, the roadmap's M2 naming Chrome only.
  - Step 17, the whole-plan review of the code, is dropped: each track had its review, and step 16's
    end-to-end test and the owner's session check the whole. `plan-003-integration` merges into the
    main branch after step 16, with the full gate.
  - Q13: $1, the agent's proposal, approved with the cuts. Q14: the defaults stay. Q15 moves to M3
    with R5 to R7, and Q16 to M4. Q17: optional, the published limits being enough for one session;
    the real ones are recorded if the owner reads them. Q18: the agent's short script.
  - The owner accepted the Orpheus terms in Groq's console ("What the owner does", step 2) and has
    not read the key's limits. Kept: E (E1 and E2, offline with `poe eot`, no spend) and held-out E
    at the close (aggregates only, no spend); step 30's corrections of the design's factual slips,
    made by an agent while the owner holds the session.
- 2026-11-03, in plan 005's session (M3), its Q2 settled as "(a) and (b)": (b) adds a few «وقف»
  over an echo to this plan's step 18 session, so M3's stop targets are also checked on M2's
  recordings. In M2's echo mode such a «وقف» is transcribed and kept on the timeline but, by the
  drop rule, never said back. Step 18 and "What the owner does", step 3, carry it.
- 2026-11-01: "Approve all", for the roadmap's M1 to M7 and the package design as amended (D-017),
  as plan 000 records it. So M2's goal and *Done when*, and the design's 16.1 M2 row, bind this
  plan, as the owner's rulings of 2026-11-03 (above) amend them: the deployment and the other
  networks left M2, and step 30 corrects the design's lines that name them, as facts; and the time
  of each step and requests per call minute come from the owner's recorded session, the end-of-turn
  cut-offs from the golden set, offline.
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

- **Arize Phoenix** 21.0.0, run as in M1 (D-023), on this laptop, on 127.0.0.1 with no
  authentication ("The owner's decisions"); on the host only with the deployment ("The
  deployment, moved out of M2").
- Not used: Pipecat's `local-smart-turn` extra (torch and transformers), its `runner` extra, its
  client-js and small-webrtc-transport (which pull in daily-js), `openinference-instrumentation-pipecat`
  (D-018, question 7), a headless browser, griffe, eot-bench, and any download at runtime (the
  design's 11).

## Tracks

Each track builds in its own worktree against Block 0's interfaces and the fakes in
`tests/t2_agentic_voice/fakes.py` and `session_fakes.py`, never against another track's unfinished
code. One owner per file; the files every track needs (the `pyproject.toml` files, `uv.lock`,
`harness.toml`, ARCHITECTURE.md, CLAUDE.md, SECURITY.md, the settings, logging, errors, ports,
`core/identity.py`, `core/events.py`, `domain/declaration.py` with `domain/presets.py` and
`domain/fixed_phrases.py`, `domain/text/invisible.py`, `api/protocol.py`, `voice/protocol.py`,
`voice/session/io.py` with `voice/session/session_events.py` (the events) and
`voice/session/commands.py` (the commands), the stubs' signatures (`voice/calls.py`,
`voice/file_transport.py`), `adapters/groq_client.py`, the facades, `scripts/`, `.env.example`,
`docs/generated/settings.md`, `tests/conftest.py`, `tests/harness/`,
`tests/ole5_voice/evals/test_no_item_in_source.py`, the fakes and the fixtures) belong to Block 0,
and this plan and `docs/plans/tech-debt.md` to the integrator, who also writes and owns step 16's
loopback test. A track that needs one changed asks the integrator. A track builds on the docstrings
of Block 0's stubs and contracts as Block 0 merges them, which its fixes after the review brought to
the decision log of 2026-11-03 and to D-028 to D-039: where the track's section here or the appendix
and such a docstring differ, the docstring wins, unless this section names the change, and where two
docstrings differ, the one of the module that does the work wins (`voice/calls.py` on the detectors,
`voice/session/io.py` on the session's events and commands). A docstring never overrides an
acceptance criterion: where they differ, the track tells the integrator, who amends the criterion
with a dated line in the decision log, or asks the owner where the change is more than a reading of
it. Library paths are under `packages/t2-agentic-voice/src/t2_agentic_voice/`; library tests under
`tests/t2_agentic_voice/`. In every track, no source string and no JS or HTML text under
`packages/`, `apps/*/src`, `apps/*/web` or `examples/` holds a golden reference as whole words (Q6
rules on `stop` and on the widget's labels), and no test text copies an item's.

**Track A · Speech text (library, `domain`).**
- Goal: `speak_number`, `speak_id`, the clause splitter and the pronunciation map.
- Owns: `domain/text/speaking.py`, `domain/text/clauses.py`, `domain/text/pronounce.py`; tests
  `domain/test_speaking.py`, `domain/test_clauses.py`, `domain/test_pronounce.py`.
- May read: `Ole5-chatbot/src/ole5_chat/voice/speakable.py` (digit words, "ending in", the shaping
  of text for speech, lines 7-41 and 109-157); num2words' documentation.
- Tests: digits and numbers in Arabic and English; a 16-digit ticket number read digit by digit; a
  run with a leading zero, and a four-digit run after each ending cue, read digit by digit in Arabic
  and in English, in texts written for the test, not taken from an item; a short run with no cue
  read as a number; Arabic-Indic digits; the splitter on «،», «؟», «.» and English punctuation,
  every clause at most `max_chars`, none cut inside a word but a word longer than `max_chars`, which
  is cut every `max_chars` characters (`"x" * 201` at 200 gives 200 and 1); the pronunciation map
  whole words only.

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
  sends nothing; `GROQ_LOG=debug` in a child process, as `GroqSTT`'s test does (TD-003); the phrase
  cache's 429 test wraps `FakeTextToSpeech`, whose `failures` fail every request for a text, in a
  fake of its own that fails once (the decision log, 2026-11-03).

**Track C · Identity and stores (library, `adapters`).**
- Goal: `SignedJoinTokens`, `DevIdentity`, `SqliteUsedTokens` and `MemoryUsedTokens`. TURN
  credentials left M2 with the deployment (the owner, 2026-11-03), since they depend on Q9:
  `adapters/turn_credentials.py` stays Block 0's stub and Block 0's TURN settings stay unused,
  both named in one debt row (TD-048).
- Owns: `adapters/join_tokens.py`, `adapters/dev_identity.py`, `adapters/used_tokens.py`; tests
  `adapters/test_join_tokens.py`, `test_dev_identity.py`, `test_used_tokens.py`.
- May read: the identity port, `core/identity.py`, the settings; PyJWT's documentation.
- Behaviour: the claims parsed into a strict pydantic model (`StrictBool` for `record_audio`, a
  bounded `version`); PyJWT's minimum key length turned on for encode and decode if 2.15.1 has it
  (step 4); a consent marked as a verified signed token's only by `SignedJoinTokens`, so the
  recorder can tell it apart; `DevIdentity` always `Consent(version=None, record_audio=False)`.
- Tests: invariant 7's adversarial cases (the acceptance criteria); the used-token store under two
  threads and after a restart.

**Track D · The voice session in echo mode (library, `voice/session/`, no Pipecat).**
- Goal: one call's session: turn order, the echo, Stop and `hangup`, speech dropped while the echo
  plays, heard words, playback bookkeeping, usage per model and per call minute, the `CallReport`
  and its content-free file, the turn and TTS spans, and the call recorder.
- Owns: `voice/session/call.py`, `echo.py`, `heard.py`, `playback.py`, `usage.py`, `recording.py`,
  `report.py`; `core/tracing_tts.py` (the TTS span and the resource attributes, the settings digest
  with no secret); tests under `voice/session/` and `core/test_tracing_tts.py`; the `[[restricted]]`
  row for `HeardWords` (applied by the integrator at the merge, `harness.toml` being Block 0's).
- May read: `voice/session/io.py`, `session_events.py` and `commands.py`, the ports,
  `core/events.py`, `core/tracing.py`, Track A's signatures; the prototype's `capture.py` (one
  record per utterance, audio only when switched on) and `session.py`'s clock (lines 234-253), read
  only.
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
  pause in it; a `stop` drops every clause the session has asked for so far, whatever its reply, the
  greeting's and a notice queued behind an echo included (`voice/session/commands.py`'s
  `StopSpeaking`), and no event of them follows, a request's report the bridge still held included
  (TD-055); a clause whose audio is empty (`turn_ends`' silent phrases) reports `ClauseQueued`, then
  `ClausePlayed`, never `ClauseFailed`, at its place in the output, sending no frame; no Pipecat
  interruption fires; invariant 8's tests in a child process (the DEBUG line, and no banner on
  import); an error frame becomes a `TransportFailed` or `ProviderFailed` event and a log line with
  no content; the file-fed transport plays 60 s of frames within 100 ms of real time (the agent's
  tolerance); every aiortc peer it builds has no ICE server.

**Track F · `api`, the CLI and `examples/minimal` (library).**
- Goal: `VoiceRuntime` and its lifespan, the lock file, the router, the offer secret, CORS, the
  error shape, `serve()`, `combine_lifespans`, `t2v`, and the minimal example as an echo agent.
- Owns: `api/runtime.py`, `api/lockfile.py`, `api/router.py`, `api/offers.py`, `api/http_errors.py`,
  `api/server.py`, `api/cli.py`, `api/doctor.py`; `examples/minimal/src/minimal_example/`; tests under
  `api/` and `tests/minimal_example/`.
- May read: the protocol models, the ports, the adapters' signatures, `voice`'s entry point as
  Block 0 defines it, Pipecat's request handler as Block 0 read it.
- Behaviour: `/join` mints no TURN credentials in M2 (the owner, 2026-11-03): Block 0's TURN
  settings stay unused and `adapters/turn_credentials.py` a stub until the deployment (TD-048), so
  `/join` returns `server.ice_servers` as set, with no username or credential, and
  `api/runtime.py`'s docstring loses its TURN clause and its case with `server.turn_secret_file`
  set, which wait with the deployment. Every route the router serves answers "runtime not started"
  (503 `not_started`) while the lifespan has not run, `/health`, `/ready`, the client script and
  `/dev` (to a loopback client in `dev`) included, as the design's 4.5 and the router criterion say,
  so `api/runtime.py`'s "Every `t2v/1` route" widens to every route (the decision log, 2026-11-03).
  `examples/minimal` passes `configure_logging` its package and `__main__` as `loggers` where it
  starts, as `ole5_voice.LOGGERS` does (the decision log, step 8): the sample Track I's
  `tracing-and-logs.md` takes.
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
- Behaviour: `t2v-client.js` sends each body as `application/json` (any other gets 415), sends its
  candidates only once `POST /offer` has answered (before that a PATCH gets the quiet 409
  `not_offered`), ignores the quiet 409s once connected, and shows a `protocol_mismatch` refusal's
  notice (`api/protocol.py`'s `ErrorCode` and `CandidatesRequest`).
- Tests: the token route's adversarial cases (a wrong code, compared in constant time; repeated tries
  from one address slowed, the address taken from `X-Forwarded-For` only from a trusted proxy; the
  hourly cap on failed tries; an access code under 16 characters refused at settings load; consent
  passed through into the token, never taken from a later message); each header of the widget page
  and of `/dev`; no `innerHTML` or its kin in any script (the browser criteria); a global tracer,
  meter and logger provider receives nothing from the Ole5 app's FastAPI; the page checked by the
  agent in its browser pane and by the owner in Chrome and in Edge (step 18; Chrome only since
  2026-11-03, "The owner's decisions").

**Track H · The measurement's tooling (library `testing`, app `evals`).**
- Goal: `poe eot`, the timing run, the recorded calls' manifests, and what runs R5 to R7 need.
- Owns: `testing/turns.py`, `testing/echo_timing.py`; in `apps/ole5-voice-agent/src/ole5_voice/evals/`,
  `eot.py`, `timing.py`, `call_manifests.py`, and the changes to `answerers.py` (split first, each
  answerer in its own module), `compare.py` (`--allow-setting`, refusing runs whose settings
  differ), `runs.py` and `history.py` (the new run kinds);
  the poe tasks `eot` and `eval-timing` (asked of the integrator); tests under `tests/ole5_voice/evals/`
  and `testing/`.
- May read: the registration below, evaluation.md's "Running", the file-fed transport's interface as
  Block 0 defines it, and the phrase cache's (`adapters/phrase_cache.py`, public through `stores`),
  whose phrase audio `echo_timings` takes.
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
- Content beyond the design's 14: `serving.md` tells a team that mounts the router to turn FastAPI's
  telemetry off and set CORS on its own app, and to trust proxy headers from its proxy only;
  `tracing-and-logs.md` tells a team to pass `configure_logging` its own package and `__main__` as
  `loggers`, since a command run with `python -m` logs as `__main__` (the decision log, step 8), its
  sample taken from `examples/minimal` (Track F); `data-and-privacy.md` says how long Phoenix keeps
  transcripts: forever unless a retention is set (`PHOENIX_DEFAULT_RETENTION_POLICY_DAYS`, 0 by
  default), and for Ole5 in M2 Q7's (iv), settled on 2026-11-03: the local Phoenix, M1's, with no
  retention setting. From the tracks' reports of 2026-11-03: `serving.md` gives the join token's
  claims as `SignedJoinTokens` verifies them (a `kid` header and HS256; `sub` required; `name`,
  `locale` and `attrs` optional, each may be null; `consent` with both its keys, `version` null or 1
  to 64 printable ASCII characters with no space, and `record_audio` a JSON boolean; a `jti` of 1 to
  128 printable ASCII characters with no space; `iat` and `exp` JSON integers, `exp - iat` within
  the runtime's `join.ttl_s`; no claim beyond these eight, so `nbf`, `aud` and `iss` are refused),
  and tells a team that mounts the router on Windows to run uvicorn on the selector loop, as the
  Ole5 app's server does (`loop="asyncio:SelectorEventLoop"`), since uvicorn's default there is the
  Proactor loop (the appendix's item 20).
- Tests: `poe docs`, which also checks that a code sample after a link to a `.py` file is a run
  of that file's lines (DOC-SAMPLE, D-027).

**Review** (the owner's rule of 2026-11-03, "The owner's decisions"). One reviewer per track, an
agent that did not write it, reads the track for each concern below that it touches, and the
whole-plan review at step 17 (dropped on 2026-11-03) was to follow the same rule; for this plan,
this replaces the plans README's reviewers named by concern ("Parallel tracks", item 4). A review
reports only what would break, hang or crash a call; garble, cut, overlap or lose its audio; leak a
task, connection or memory per call; send Groq more than the limits allow or fail on a 429 it could
wait out; refuse valid Arabic or English text; or leave a later track or milestone a contract it
cannot build on. Each finding is checked by one skeptic, an agent told to refute it, before it is
acted on; everything else becomes a row in `docs/plans/tech-debt.md`, and there is no second fix
round unless a high finding stands.
- **Security:** invariants 1, 5, 7 and 8; data-channel input parsed strictly (the browser is not
  trusted, SECURITY.md's trust boundaries); the offer secret, the TURN secret, the join keys and the
  access code, each held to its minimum length; CORS; the token route and the guard on the shared
  key; recordings gated by the setting and the token, never by `DevIdentity`; the phrase cache and
  the report file holding no call content; the widget page's headers and captions as text; Phoenix
  never public; no `.env` read; FastAPI's telemetry off in both shapes; no aiortc
  peer reaching a STUN server.
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

*Amended 2026-11-03, before any run: Block 0's fixes declare every fixed phrase before a run (each
language's greeting, the echo's frame, and the `error` and `ended` notices), not the frame alone,
and a file-fed call plays its greeting before the clip's lead (D-037); Arm T1, the cost and the
limits below count them.*

*Amended 2026-11-03, before any run ("The owner's decisions"): T1 and T2 are dropped, and nothing
below runs in M2. The time of each step comes from the owner's recorded session (C), whose calls'
reports and traces record each turn, and the VAD stop delay and Smart Turn's decision from E1,
offline. The text below stays as registered; `poe eval-timing` stays in the code, unrun (TD-071,
TD-082, TD-063's first byte and noise floor, and TD-081's timing part wait for a timing run, if one
is ever run).*

- **Data.** The 23 dev paused-request variants: 19 for the Arabic model (Saudi 11, MSA 4, mixed 4)
  and 4 for the English one.
- **Arm T1.** The echo on the file-fed pipeline at real-time pace with the real `GroqSTT`
  (`whisper-large-v3`, the item's label as the session's language, as
  `stt.live_language = "session"` sends it, Whisper cut as step 12 records: per user turn, the
  agent's proposal) and `GroqTTS` (Q5's voices), every fixed phrase declared before the run by
  `PhraseCache.declare` (each language's greeting, the echo's frame, and the `error` and `ended`
  notices; its requests counted as it returns them, none for a phrase already cached), each call
  playing its greeting before the clip's lead, which starts at the greeting's last `ClausePlayed`
  (D-037), trim off, untraced, with E's padding and a fresh call per variant. Between variants the
  runner waits until its pacers allow the next: at most 10 Whisper requests and 5 requests per
  Orpheus model in any minute (the decision log). T2 is the same run again, on the same commit.
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
  frame ≈ 1,100 characters (a cut changes the requests more than the characters) × $40 per million =
  $0.044; English about 4 × 60 = 240 × $22 per million = $0.005 (prices:
  console.groq.com/docs/model/canopylabs/orpheus-arabic-saudi and .../orpheus-v1-english, read
  2026-11-02 by the research step). On a cold cache, each language's greeting and two notices, three
  phrases within 200 characters each, add at most 600 characters, once: at most $0.024 for each
  Arabic language and $0.013 for English, up to $0.06 with both Arabic presets. About $0.07 a run,
  $0.14 for both, plus that once.
- **Limits** (console.groq.com/docs/rate-limits, read 2026-11-02 by the research step and the
  agent): up to 40 Arabic and 8 English Orpheus requests a run, the smoke's and the frame's
  included, and on a cold cache up to three more for each language the agent declares (its greeting
  and its two spoken notices, while each is within 200 characters), which `PhraseCache.declare`
  sends one at a time with no pacer of its own, so the run's pacer counts them before the first
  variant: T1 and T2 take up to 83 of the published 100 a day for the Arabic model with one Arabic
  language declared, and 86 with both Arabic presets, with the pacer under its 10 a minute. Each
  Orpheus model also has a published 1.2K tokens a minute and 3.6K a day; what a TTS token counts is
  UNVERIFIED (the page does not say): if it is one character, T1 and T2 take about 2,200 of the
  Arabic model's 3,600, a cold cache up to 600 more for each Arabic language declared, and a run's
  minute stays under 1.2K at 5 requests of at most 200 characters. Whisper's 700 billed seconds a
  run sit far inside its published 7.2K audio seconds an hour. So T runs on a day with no call (step
  27, Q17).

**L · The live language, and the noise on another day (spends)**

*Amended 2026-11-03, before any run ("The owner's decisions"): R5, R7 and R6 move to M3, whose plan
needs the noise on another day (TD-032) anyway, with Q15; M2 keeps `stt.live_language`'s default,
`session` (`core/settings/stt.py`). The text below stays as registered, for M3's plan to take up or
register again.*

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

*Amended 2026-11-03, before any run ("The owner's decisions"): the deployment left M2, so every
call of C is local, on this laptop, through the Ole5 app's dev server on localhost, with no network
variant. C and the budget as drafted are in "The deployment, moved out of M2".*

*Amended 2026-11-03, before any run ("The owner's decisions"): C is one recorded session of about 20
to 30 minutes, which also holds the first calls (step 18): Q18's script in Chrome, on the laptop's
speakers, then the wired headset; Edge and the Bluetooth headset are dropped. Each bullet below
keeps its registered text and ends with its amendment.*

- **The calls,** from the call script the owner approves (Q18): the agent's proposal is five calls
  of at least three minutes and about ten turns each, all local: in Chrome on the laptop's speakers,
  the wired headset and a Bluetooth headset, and in Edge on the speakers and the wired headset. The
  turns, in the owner's own words: requests that pause mid-sentence, one-clause requests with
  product terms, a number and a ticket number, English sentences, listening sounds, and the Stop
  button and Esc during the echo.
  *Amended 2026-11-03 (Q18): one session in four calls, none past `limits.max_call_s` (600 s): on
  each device an Arabic call, three Saudi turns then three MSA turns, and an English call of three
  turns, about 18 turns in all, with Stop pressed once on the speakers and Esc once on the headset,
  and in each Arabic call one listening sound during an echo, transcribed but never said back (the
  drop rule), for M3's check that listening sounds do not interrupt the agent ("What the owner
  does", step 3).*
- **Metrics, per call:** per Groq model, the requests and the requests per call minute, the audio
  seconds sent and billed per minute, the TTS characters per minute; per turn, the server's time to
  first audio and, from `client_stats`, when it played (their difference is the network to the
  browser); the candidate type and the time to connect; whether
  the owner heard the turn back (after each call, the owner names any turn that did not come back,
  and the agent checks it against the call's trace and timeline). Reported per call and as medians
  over the calls.
  *Amended 2026-11-03: the server's steps per turn are those the call's report and trace hold (the
  measurement criteria), and when a turn played comes from the recording's timeline (approximately,
  TD-070); reported per call and over the session.*
- **Recorded:** the requests per call minute per model, beside the key's real limits (Q17), as a
  decision entry for M6.
  *Amended 2026-11-03 (Q17): beside the published limits, or the real ones if the owner reads them.*
- **Cost (the agent's estimate):** a turn every 10 s or so is about 6 Whisper requests a minute with
  Whisper cut per turn, up to about 12 with cut-offs, and up to about 20 for a caller who pauses
  often if it is cut per segment, against the published 20 a minute; each is billed 10 s, so 60 to
  120 billed seconds a minute ≈ $0.002 to $0.004; and 6 Orpheus requests of about 60 characters
  ≈ $0.014 a minute in Arabic; five calls of three minutes ≈ $0.28. **The limits, not the money,
  bind:** at the published 100 requests a day per Orpheus model, about 6 requests a minute leave
  roughly 16 call minutes of Arabic a day; at its published 3.6K tokens a day, if a token is one
  character (UNVERIFIED), about 360 characters a minute leave about 10. The lower holds until Q17's
  reading says otherwise, so C's calls span about two days, none on T's day, unless Groq raises
  the limits (Q17).
  *Amended 2026-11-03: the session keeps the estimate of C and the first calls ("The budget"),
  $0.28 + $0.05 = $0.33, as a ceiling for its script: about 18 turns, 12 on the Arabic model and 6
  on the English one, and 2 listening sounds, each up to 2 Whisper requests (a cut-off); each turn
  one packed Orpheus request (up to 3 past 200 characters, D-1's fix), a listening sound none; at
  C's 60 characters a turn they cost about $0.05. On the published limits, which hold while Q17 is
  unread, the session fits one day: at most 40 Whisper requests, 400 billed seconds of the 7.2K an
  hour; for the Arabic model, 12 requests and, on a cold cache, Ole5's four `ar-SA` phrases, 16 of
  the 100 a day (40 if every turn passed 200 characters), and about 12 × 60 + 150 ≈ 870 characters
  of its 3.6K tokens a day (2,550 if every turn took a full 200), if a token is a character
  (UNVERIFIED); at a turn every 10 s or slower, no minute passes 20 Whisper or 10 Orpheus requests.
  There is no T day to keep apart.*

**The budget** (the agent's arithmetic, amended 2026-11-03 with C and with Block 0's fixed phrases):
L $0.23, T $0.14 and up to $0.06 more once on a cold phrase cache (T's cost), C about $0.28, the
first local calls about $0.05, and Q16's prompt arm $0.075 if it runs in M2: about $0.80 in all,
$0.84 on a cold cache; `t2v doctor --synthesize` adds a fraction of a cent each time it runs.
Whether a refused request is billed is UNVERIFIED (TD-021), and retries add requests.

*Amended 2026-11-03, before any run, with the owner's ruling and Q13's cap ("The owner's
decisions"): L, T and Q16's prompt arm leave M2, $0.23 + $0.14 + $0.075 = $0.445, so about $0.80
less $0.445 leaves about $0.35: the session, which holds C ($0.28) and the first calls' share
($0.05), $0.33, its estimate kept as a ceiling (C's cost). The cold phrase cache, which T's first
run would have paid, falls on the session's first start: Ole5's four `ar-SA` phrases (its greeting
with the name said out, the frame, the `error` and `ended` notices) hold about 150 characters and
its four `en` ones about 190, so 150 × $40 + 190 × $22 a million ≈ $0.01 (T's cost had bounded it at
$0.024 and $0.013). About $0.34 in all, against Q13's cap of $1; `t2v doctor --synthesize` adds a
fraction of a cent each time it runs.*

**Words the questions use**

- **VAD** (voice activity detection; Silero here): finds where speech starts and stops in the
  audio. **Smart Turn:** a small model that judges, at each pause, whether the caller has finished.
- **ICE:** how the browser and the backend find a network path for the call's audio. Each address
  it tries is a **candidate**: a *host* candidate is the machine's own address, *srflx* the address
  a home or office router shows the outside, *relay* an address on a TURN server.
- **STUN:** a server that tells a machine its outside address. **TURN:** a relay server that
  carries the call's audio when no direct path works.
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
  19 is answered, and what guards the shared key meanwhile.** *Settled on 2026-11-02: (a) and (i).
  Amended 2026-11-03 ("The owner's decisions"): no call of M2 is deployed, so the token route and
  its access code serve the local calls (steps 18 and 28); the check that (i)'s guard is in place
  before the first deployed call, (a)'s replacement by 19's answer (Q12), and the debt row for M6
  that (i) leaves, for a backend on the internet, moved with the deployment ("The deployment,
  moved out of M2").*
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

The owner's call before the first recorded call, and the host:

- **Q7. The consent screen, and keeping the recordings.** *Settled on 2026-11-03: (a), (i) and
  (iv), on this laptop ("The owner's decisions"); its host parts, as drafted, moved with the
  deployment ("The deployment, moved out of M2").* The widget shows a consent screen before the
  microphone opens and passes its version and the recording choice to the token (the design's 3.2).
  (a): the agent drafts it in Arabic and in English, with a one-line recording box, version
  `m2-owner-test-1`, set as the dev server's `privacy.consent_version`, for the owner's own test
  calls; the token's consent and `privacy.record_audio` stay as Block 0 built them, and nothing
  more is built for them. The wording customers see comes from T2 before any customer uses the
  widget. (i): the recordings are kept under `var/` on this laptop, the host now, until the owner
  deletes them, as the golden set's audio is. (iv): the transcripts stay in the local Phoenix, M1's
  on 127.0.0.1, with no retention setting, so until the owner deletes the project
  (`PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` defaults to 0, infinite:
  arize.com/docs/phoenix/self-hosting/configuration.md, read 2026-11-02 by the security review).
  `data-and-privacy.md` says both.
- **Q8. The host.** *Settled on 2026-11-02: this machine for now, with Phoenix as M1's on
  127.0.0.1, no SSH tunnel and no authentication ("The owner's decisions"). Its other parts moved
  with the deployment on 2026-11-03, to be re-planned for the server ("The deployment, moved out of
  M2").*
- **Q9 to Q12** (the media path, the website embed, the network that blocks UDP, and open question
  19 at the deployment) moved with the deployment on 2026-11-03; as drafted, they are in "The
  deployment, moved out of M2".

The owner's call before the measurement runs, except Q13 and Q17, which come before the first live
call (step 18), since those calls spend the same money and limits:

- **Q13. The budget cap** for M2's paid runs and calls together, against the estimate of about $0.80
  ("The budget"). **The agent recommends $5**, the cap the owner set for M1 (the agent had
  recommended $2 then).
  *Settled on 2026-11-03: $1, which the agent proposed with the cuts, against about $0.34 ("The
  budget", amended; "The owner's decisions").*
- **Q14. The turn defaults.** *Settled on 2026-11-03: (a), the defaults stay ("The owner's
  decisions").*
  Should M2 change the settings that decide when the caller has
  finished speaking? With only 6 paused requests in dev and D-024's floor of 6, a change could be
  shown to help only if all 6 got better. Options: (a) measure only in M2 (E1 is the baseline), and
  tune in M3 after more paused requests are recorded; (b) the owner records more paused requests now
  (say 20 more lines, about an hour on the three devices), then M2 tunes on dev; (c) tune on the six
  now. (b) and (c) would be registered as a dated amendment before E1. **The agent recommends
  (a).**
- **Q15. The language a live call sends Whisper, when the rule does not decide.** *Moved to M3 on
  2026-11-03, with runs R5 to R7 ("The owner's decisions"); M2 keeps `stt.live_language`'s default,
  `session`.*
  If A3 is not worse
  (the rule above): (a) auto-detect for live calls, and the widget's language buttons kept only as a
  preference; (b) the session's language anyway; (c) the prototype's double transcription, each clip
  sent as Arabic and as English (its D24), twice the requests at the 10 s minimum each, against 20
  Whisper requests a minute. **The agent recommends (a) in that case,** and (b) otherwise, as the rule
  already gives.
- **Q16. The prompt arm for product terms: in M2 or in M4.** *Settled on 2026-11-03: M4 ("The
  owner's decisions").*
  Term recall was 0.333 for large-v3 on dev
  (plan 002's Future improvements). In M2 it costs one dev run (about $0.075) plus a `--prompt` flag
  in `poe eval` and the answerers' split, and it would change no default in M2, since the vocabulary that
  becomes the prompt is declared with the agent (the design's 3.1 and 3.3). **The agent recommends
  M4**, where the vocabulary lands and the result is used.
- **Q17. The key**, before the first live call. *Settled on 2026-11-03: optional; the published
  limits are enough for one session (C's cost, amended), and the real ones are recorded if the owner
  reads them ("The owner's decisions").*
  Its real limits from the console
  (console.groq.com/settings/limits): for each Orpheus model the requests and tokens a minute and a
  day (published: 10, 100, 1.2K and 3.6K) and what a TTS token counts; for `whisper-large-v3` the
  requests a minute and the audio seconds an hour and a day (published: 20, 7.2K and 28.8K); whether
  Groq has been asked to raise Orpheus's limits (the owner's answer to the design's question 21);
  whether anything else uses the key during M2's runs and calls; and Ole5's share of it (D-018,
  question 11), which M6's limiter enforces. One live call may need about 6 to 12 Whisper requests
  a minute, and up to about 20 if Whisper is cut per segment ("C" above). **The agent recommends**
  pacing runs at half the key's per-minute limits while anything else might use it, as in M1, and
  holding C's call days apart from T's day while the published limits hold.
- **Q18. The call script.** *Settled on 2026-11-03: the agent's short script, in "What the owner
  does", step 3: one recorded session in Chrome, an Arabic and an English call on each device, three
  turns a language, a listening sound in each Arabic call, Stop once and Esc once ("The owner's
  decisions").*
  The calls of "C" above, or fewer or more; with or without the Bluetooth
  headset. **The agent recommends the script as proposed**, the Bluetooth call included, so that M3
  has its recordings for the Bluetooth warning.
- **Q19. Pipecat's log lines when a team asks for them (`logging.pipecat = "forward"`).** *Asked on
  2026-11-02, after Block 0's read; open, and since 2026-11-03 no longer needed before Track E (the
  decision log): Track E builds `off` only, as Block 0 did, and `forward` waits for the answer.*
  Q2's (a) said that `forward` switches Pipecat's namespace back on and forwards WARNING and above
  to `t2_agentic_voice.pipecat`, with no sink added or removed. The read shows that cannot hold: a
  namespace switched off reaches no sink at all (`loguru/_logger.py`, line 1995), so `forward` must
  switch it on and add a forwarding sink, and loguru's default sink, which prints to the screen,
  then prints every Pipecat DEBUG line, call content included, unless it is removed. Options: (a)
  `forward` switches the namespace on, adds a sink that forwards WARNING and above with the record's
  level and module but never its text, and removes loguru's default sink if it is still installed: a
  process-wide change a team makes only by choosing `forward`, which the guide says; (b) M2 builds
  only `off`, the default, and `forward` waits for a team that asks, built then as (a); (c)
  `forward` leaves the sinks alone, set aside because the default sink would print call content
  (invariant 8). **The agent recommends (b):** M2 needs only `off`, a forwarded record carries no
  text and so says little, and adding the value later breaks nothing. `off` behaves as Q2 settled it
  either way.

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
   *Done on 2026-11-03 ("The owner's decisions"): the owner accepted the Orpheus terms in Groq's
   console and reported the acceptance, not who could accept; the key's limits were not read, and
   reading them is optional (Q17).*
3. **The recorded session** (step 18, run C; amended 2026-11-03, "The owner's decisions"): Q5, Q13
   and Q18 are answered. From the main checkout, start the Ole5 app's dev server with the agent's
   command, which sets Q7's consent version and switches recording on; open the address it prints in
   Chrome on this laptop; on the consent screen, tick the recording box and agree, then type the
   access code; start each call with Start, its language picked at the top first, allow the
   microphone if Chrome asks, and end the call with End. The box and the code stay set for the later
   calls (the consent screen shows once per page load). Say whether anything else will use the key
   meanwhile. The script, about 20 to 30 minutes in four calls (a call ends at 10 minutes):
   - on the laptop's speakers, an Arabic call (`ar-SA`): three Saudi turns (one that pauses
     mid-sentence, one with a product term, one with a number or a ticket number), then three MSA
     turns; press Stop once during an echo, during another echo say a listening sound («اها» or
     «ايوه») once, and during a third echo say «وقف» once at normal volume (plan 005's Q2 (b));
   - on the speakers, an English call: three turns, one with a product term;
   - on the wired headset, the Arabic call again, its listening sound and «وقف» included, pressing
     Esc once during an echo instead of Stop;
   - on the headset, the English call again.

   After each call, say which turn, if any, did not come back, and whether the microphone, playback,
   Stop and Esc worked; after the last, switch recording off with the agent's command and stop the
   backend (Q4).

**Steps 4 to 6, and the host's and the other networks' parts of steps 7 and 8, moved with the
deployment** on 2026-11-03 ("The owner's decisions"); as drafted, they are in "The deployment,
moved out of M2". Steps 7 to 9 keep their numbers.

**Steps 7 to 9, folded into step 3** on 2026-11-03 ("The owner's decisions"): run C's calls are
step 3's session (7); after it there is nothing to copy, its call reports and recordings being under
`var/` on this laptop (8, Q7); and Q14 to Q16 and Q18 were answered that day, the question of the
key's other users asked with step 3 (9).

## The deployment, moved out of M2

On 2026-11-03 the owner moved the deployment out of M2 ("The owner's decisions"): the owner has no
access to the server yet, and every M2 call runs on this laptop, through the Ole5 app's dev server.
The text below is the deployment as drafted on 2026-11-02, kept as it was written but for its
checkboxes, made plain bullets: the acceptance criteria, steps 19 to 22 and the packages they run,
the registration's C and its budget as drafted for the deployed calls, the words and the questions
the deployment needs (Q7 and Q8 as drafted, Q9 to Q12), and "What the owner does", steps 4 to 8 as
drafted. It becomes a plan of its own as soon as the owner has access to the server, whichever
milestone is then in progress, re-planned for that server (its host facts, Q8 to Q12), and at the
latest in M6. This replaces the note of 2026-11-02 below, which had it re-planned for this machine
before step 19. That plan also re-reads what Block 0's reading found for this machine alone (the
appendix's "Changes to the plan's interfaces", items 19, 20 and 22: proxy headers, the event loop,
media on the LAN); checks what M2's local calls cannot show: `client_stats`'s relay fields on a
relayed call, and the lock file's Linux case unless CI (TD-001) has run it; records Ole5's identity
answer (Q12, the design's open question 19) in a decision entry; and pays TD-004, TD-015, TD-038
and TD-048.

### The acceptance criteria, as drafted

**The deployment**

*Amended 2026-11-02 ("The owner's decisions"): all hosting is on this machine for now, and Phoenix
is M1's, on 127.0.0.1 with no authentication. These criteria, steps 19 to 22, Q9 to Q12 and Q7's
host parts are re-planned for this machine before step 19, as a dated amendment the owner approves;
until then they stand as drafted.*

- The Ole5 app runs on the owner's host behind HTTPS (Q8): `env=staging`, one worker,
  `var_dir` on a persistent volume, its image built from `git archive` of the merged commit with an
  allow-list `.dockerignore` (a test that it lets in no `.env*`, `var/`, `.claude/` or `*.wav`).
  Publicly open are only 443/tcp and the TURN ports Q9 keeps; the backend's HTTP port and Phoenix
  sit on 127.0.0.1 or the compose network only, checked from the phone hotspot (step 20). Phoenix
  runs beside it with auth on, its retention set by Q7, and never public; the backend sends
  Phoenix's system API key from a host file (`tracing.api_key_file`), so a deployed call's turn
  traces arrive there, and an exporter refusal (401) is counted and logged with no content. The
  widget is embedded in the website (Q10).
- The owner held a call from another network (a phone hotspot) and one from a network that
  blocks UDP (Q11), and heard each turn back; each call's `client_stats` shows its candidate type,
  and the call from the network that blocks UDP a relay over TLS on 443.
- Before M2 closes, the media path is recorded as a decision entry with the network test's
  outcome: UDP ports opened on the backend, a TURN service run as a small service, or another
  transport (Q9).
- If TURN is used, `/join` returns per-call TURN credentials minted from the shared secret
  (coturn's REST scheme), the username `<expiry>:<call ID>` holding no claim of the token, valid
  for `server.turn_ttl_s` (3600 by default, refused above 86400); the TURN secret, at least 32
  bytes, is a `SecretStr` that reaches no log, trace, event or error, and so is each per-call
  password. coturn runs as step 19 configures it, and step 20 shows that a minted credential
  reaches no loopback, private or metadata address and gets no TCP relay.
- The guard on the shared Groq key that Q4 settles is in place before the first deployed call.

### Steps 19 to 22, as drafted

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

### The packages they run, as drafted

**Not installed:**

- **coturn** 4.18.0 (2026-09-08, BSD-3-Clause; github.com/coturn/coturn/releases, read 2026-11-02 by
  the research step), if Q9 picks it: run on the host as a small service from its own image pinned
  by digest, or from a host package no older than 4.16.0 (step 19), never added to a member.
- **Arize Phoenix** 21.0.0, run as in M1 (D-023), on the host for the deployment.

### The owner's calls, the words and the questions, as drafted

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

- **STUN:** a server that tells a machine its outside address. **TURN:** a relay server that
  carries the call's audio when no direct path works. **TURN over TLS on 443** looks to a network
  like ordinary secure web traffic, the one kind most closed networks let through.
- **SNI routing:** a proxy reads the name a secure connection asks for and passes the connection,
  still encrypted, to the server of that name, so two services can share port 443 on one address.

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

### What the owner does, steps 4 to 8, as drafted

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

## Block 0's reading of the installed packages

Written by Block 0's workflow on 2026-11-02 (steps 4 and 5) and kept here as it wrote it, for
the agents that build steps 6 to 12 and the tracks; the decision log records what it changed.

For the agents that build Block 0 (steps 6 to 12) and the tracks. Every path below is relative to
the Block 0 worktree's `.venv/Lib/site-packages`,
with a 1-based line in the installed file, unless it starts with `stdlib:` (CPython 3.12.13 at
uv's CPython 3.12 for Windows, `Lib/`).
Versions: pipecat-ai 1.15.0, aiortc 1.15.0, aioice 0.11.0, av 17.1.0, fastapi 0.162.0, starlette
1.10.0, uvicorn 0.54.0, loguru 0.7.3, onnxruntime 1.31.1, numba 0.68.1, llvmlite 0.50.0, pyjwt
2.15.1, num2words 0.5.14, openai 3.42.1, websockets 17.4.

Marks: a plain line is a reader's finding a checker confirmed. **[corrected]** replaces a finding
the checker judged partly right. **[from the check]** is a fact the checker found that the reader
missed. **UNVERIFIED** means the source read does not show it.

Counts (confirmed / corrected / wrong, then missed facts added): env 36 / 4 / 0, +6; logs 33 / 4 / 0,
+6; turns 42 / 3 / 0, +6; output 47 / 5 / 0, +6; web 35 / 2 / 0, +6.

---

### Step 4, bullet 1: environment variables, `load_dotenv`, SCTP, aiortc's default ICE servers

#### Pipecat

- `PIPECAT_SCTP_MAX_CHUNK_SIZE` is read at import, module level (default 1100), and written
  process-wide to `aiortc.rtcsctptransport.USERDATA_MAX_LENGTH` (aiortc's own default 1200 at
  `aiortc/rtcsctptransport.py:28`): `pipecat/transports/smallwebrtc/connection.py:77-79`. A non-int
  raises ValueError at import; no parameter overrides it. conftest pops it at module top.
- `PIPECAT_SMART_TURN_LOG_DATA` is read in `LocalSmartTurnAnalyzerV3.__init__` via `env_truthy`;
  when true every analysed turn's caller audio is written as WAV under `./smart_turn_audio_log`
  (`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:46`, dir at :97, write at :176-178). No
  constructor override (only the private `_log_data`). Breaks invariant 8: conftest removes it,
  `voice` refuses or clears it.
- **[from the check]** `env_truthy` raises `InvalidEnvVarValueError` outside its true/false sets
  (`pipecat/utils/env.py:49`), so a malformed `PIPECAT_SMART_TURN_LOG_DATA` makes the analyzer's
  constructor raise; its WAV names use `%H:%M:%S` (`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:96`), Windows effect
  UNVERIFIED.
- `PIPECAT_SETUP_FILES` is read at each `PipelineWorker` set-up (`pipecat/pipeline/worker.py:1805`)
  and `WorkerRunner` start (`pipecat/workers/runner.py:454`); each listed file is executed and its
  `setup_pipeline_worker(worker)` / `setup_worker_runner(runner)` called (`pipecat/utils/startup.py:40`,
  exec at :57). Code injection into every call: conftest removes it, `voice` refuses it.
- `PIPECAT_LOG_LLM_CONTEXT` is read once at the first `LLMService` construction
  (`pipecat/services/llm_service.py:429`) and cached (`pipecat/utils/log_config.py:71`). Only matters
  if an LLMService is built (M2 builds none).
- `PIPECAT_ALLOWED_ORIGINS` is the default factory of the WebSocket transports' `allowed_origins`
  (`pipecat/utils/security/allowed_origins.py:18`; `pipecat/transports/websocket/fastapi.py:87`,
  `pipecat/transports/websocket/server.py:65`); SmallWebRTC does not read it.
- **[corrected]** `PIPECAT_ALLOWED_FILE_URL_NETWORKS` (`pipecat/utils/security/ssrf.py:40`) is read
  at every `LLMService.__init__` through `self._file_resolver = file_resolver or FileResolver()`
  (`pipecat/services/llm_service.py:433` -> `pipecat/utils/file_resolver.py:117-118`); override with
  `file_resolver=FileResolver(allowed_url_networks=[])`. Off the M2 path.
- `HOSTNAME` and `ENVIRONMENT` are read only by `pipecat.utils.tracing.setup.setup_tracing()`
  (`pipecat/utils/tracing/setup.py:70`). **[from the check]** that function's `Resource.create` also
  merges `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` (`opentelemetry/sdk/resources/__init__.py:333`, `:350`).
- The other env reads under `pipecat/` sit in `pipecat/runner/*.py` (DAILY_*, LIVEKIT_*, TWILIO_*,
  `PIPECAT_ICE_SERVERS` at `pipecat/runner/run.py:2033`, ...), `pipecat/cli/hub_status.py`,
  `pipecat/evals` (`pipecat/evals/suite.py:1252` setdefaults `OMP_NUM_THREADS`), Krisp and Tavus; `pipecat/services/stt_service.py`,
  `pipecat/services/tts_service.py` and the other service base modules read none.
- **[corrected]** `pipecat/__init__.py` reads no env var; the banner is gated only on `sys.argv[0]`
  (`pipecat/__init__.py:24-25`, `:53-54`), but `LOGURU_AUTOINIT` and `LOGURU_LEVEL`
  (`loguru/_defaults.py:30`, `:40`) decide whether it reaches the autoinit stderr sink;
  `logger.disable("pipecat")` must run before the first pipecat import.

#### `load_dotenv` through Pipecat imports

- **[corrected]** `pipecat.runner.run` calls `load_dotenv(override=True)` at import, module level,
  then sets `os.environ["ENV"] = "local"` (`pipecat/runner/run.py:171-172`). `find_dotenv` walks up
  from the caller file, or from `os.getcwd()` in a REPL, a debugger or whenever `sys.gettrace()` is
  set (coverage) (`dotenv/main.py:361-363`); both walks pass the worktree and the main checkout
  root, so either can load the main checkout's `.env`. `voice` never imports it; a harness test
  asserts `'pipecat.runner.run' not in sys.modules` after importing `voice`.
- No other pipecat module imports `pipecat.runner.run` (self-references at :39 and :210 are
  docstrings). A probe of 25 modules in fresh processes (pipeline worker/task/runner, STT/TTS/LLM
  base, groq stt/tts/llm, smallwebrtc connection/transport/request_handler, silero, smart turn v3,
  rtvi, numbers transform, runner.utils, runner.types, resampy resampler, fastapi, uvicorn, aiortc)
  made no dotenv call; checker re-probed 8 of them. `request_handler` imports `pipecat.runner.utils`
  lazily, only in esp32 mode (`pipecat/transports/smallwebrtc/request_handler.py:231`).
- `pipecat.cli.commands.eval` calls `load_dotenv(find_dotenv(usecwd=True))` only in the `pipecat eval`
  CLI callback (`pipecat/cli/commands/eval.py:117`).
- **[corrected]** `PYTHON_DOTENV_DISABLED` (evidence at `dotenv/main.py:26`) gates only
  `load_dotenv` (`dotenv/main.py:418-422`), not `dotenv_values` (:438) or `find_dotenv`;
  pydantic-settings reads an `env_file` through `dotenv_values`
  (`pydantic_settings/sources/providers/dotenv.py:92`), so the flag does not stop the library's own
  settings from reading one. Usable only as an extra guard in conftest.
- **[from the check]** Pipecat's JSON bus deserializer imports any module named in a message's
  `__type__` (`pipecat/bus/serializers/json.py:209`), the default of the network buses
  (`pipecat/bus/network/redis.py:63`, `pipecat/bus/network/pgmq.py:128`, `pipecat/workers/proxy/websocket/client.py:96`):
  a data-driven path to `pipecat.runner.run`. Off the M2 path.

#### uvicorn

- `env_file=` loads a dotenv file (`uvicorn/config.py:356`); through the CLI it can also come from
  `UVICORN_ENV_FILE` (`uvicorn/main.py:61`). Never pass `env_file`.
- `FORWARDED_ALLOW_IPS` is read at `Config()` only when `forwarded_allow_ips` is None, default
  `'127.0.0.1,::1'` (`uvicorn/config.py:363`); with `proxy_headers` on by default (:225) it becomes
  `ProxyHeadersMiddleware`'s trusted hosts (:543-544). A value in code wins.
- `WEB_CONCURRENCY` sets `workers` when `workers` is None (`uvicorn/config.py:359`).
  **[from the check]** With it set, `uvicorn.run` with an app object (not an import string) exits
  with STARTUP_FAILURE (`uvicorn/main.py:614-617`): pass `workers=1` explicitly.
- The click CLI takes every option from `UVICORN_*` (`uvicorn/main.py:61`); `uvicorn.run()`/`Config`
  do not.

#### FastAPI and `OTEL_*`

- `FASTAPI_OTEL_AUTO_CONFIGURE` is read at `FastAPI()` construction; an explicit
  `telemetry={'auto_configure': False}` overrides it (`fastapi/applications.py:1019`, user dict
  spread after the default at :1022). When true, lifespan start attaches OTLP exporters from the env
  (`fastapi/telemetry/_runtime.py:217`, providers at :157-171). **[from the check]** It also adds its
  OTLP exporter to an already configured global provider such as Phoenix's
  (`fastapi/telemetry/_runtime.py:186-202`), and configures only the signals whose flag is True (:105-109).
- With auto_configure on it reads `OTEL_{TRACES,METRICS,LOGS}_EXPORTER`, the per-signal and generic
  `OTEL_EXPORTER_OTLP_*_ENDPOINT` and `*_PROTOCOL` (`fastapi/telemetry/_runtime.py:43-58`); only otlp
  with http/protobuf (or exporter `none`) is accepted, validation runs only when an endpoint is set
  (:49), and a failure is a logged warning that includes the exception text (:218-222).
- `OTEL_SDK_DISABLED=true` skips FastAPI's auto-configuration (`fastapi/telemetry/_runtime.py:96`).
  **[from the check]** The SDK `TracerProvider` reads it too (`opentelemetry/sdk/trace/__init__.py:1278`)
  and would quietly disable `voice`'s own Phoenix provider: conftest removes it.
- `OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS` is read at `FastAPI()` construction, no override
  (`fastapi/telemetry/_asgi.py:160`).
- Native telemetry (tracing, metrics, logs on by default, `fastapi/applications.py:1015-1017`) turns
  on per request once any global OTel provider is configured (`fastapi/telemetry/_asgi.py:181`), each
  signal decided at :251-273, no metrics for WebSocket scopes (:260). A provider can also come from
  `OTEL_PYTHON_TRACER_PROVIDER` (`opentelemetry/trace/__init__.py:569`).
- **[from the check]** Importing fastapi imports `opentelemetry.propagate` (`fastapi/applications.py:29`
  -> `fastapi/telemetry/_asgi.py:17`), which reads `OTEL_PROPAGATORS` at import
  (`opentelemetry/propagate/__init__.py:108`, run at :151) and loads the named entry points; an
  unknown name raises ValueError at import.
- `FASTAPI_ENV` is read only by `_resolve_frontend_check_dir` (`fastapi/routing.py:1953`), reached
  **[corrected]** from both `FastAPI.frontend` (`fastapi/applications.py:1333`) and `APIRouter.frontend`
  (`fastapi/routing.py:2773`). Irrelevant unless `.frontend()` is used.

#### Starlette, loguru, onnxruntime, numba, llvmlite, PyJWT, num2words, av, websockets

- Starlette reads `os.environ` only through `starlette.config.Config` built by app code
  (`starlette/config.py:19`); pipecat, fastapi, uvicorn never import it.
- loguru reads at import `LOGURU_AUTOINIT`, `_FORMAT`, `_FILTER`, `_LEVEL`, `_COLORIZE`, `_SERIALIZE`,
  `_BACKTRACE`, `_DIAGNOSE`, `_ENQUEUE`, `_CONTEXT`, `_CATCH` and `LOGURU_{level}_{NO,COLOR,ICON}`
  (`loguru/_defaults.py:30-75`); a bad bool/int raises at import (:17-26); defaults LEVEL=DEBUG,
  DIAGNOSE=True. conftest pops `LOGURU_*` at module top.
- Autoinit adds a stderr sink from those defaults (`loguru/__init__.py:31`); `logger.add()` kwargs
  default to the env values (`loguru/_logger.py:247-256`), explicit kwargs win. `logger.level()`
  refuses to change an existing level's severity (`loguru/_logger.py:1608`), so a `LOGURU_*_NO` set
  at import cannot be undone in code.
- With `colorize=None`, colour is decided from `CI`, `TRAVIS`, ..., `PYCHARM_HOSTED` and on Windows
  `TERM` (`loguru/_colorama.py:32`), only for `sys.__stdout__`/`sys.__stderr__` sinks (:24). Pass
  `colorize=False`.
- `ORT_LOAD_CONFIG_FROM_MODEL=1` is read at `InferenceSession` construction
  (`onnxruntime/capi/onnxruntime_inference_collection.py:677`); the kwarg override (:674-675) is never
  passed by Silero (`pipecat/audio/vad/silero.py:70-74`) or Smart Turn
  (`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:76`). conftest removes it.
- onnxruntime reads `SystemRoot` at import on Windows only for a DLL warning
  (`onnxruntime/capi/_pybind_state.py:23`); its other reads are in backend/quantization/tools/
  transformers, off the path; `print_debug_info()` prints PATH (`onnxruntime/__init__.py:338`).
- numba reads every `NUMBA_*` and a `.numba_config.yaml` in the cwd at import
  (`numba/core/config.py:144`, yaml :28, :129-141) and before each compile
  (`numba/core/compiler.py:394`). Only `pipecat/audio/resamplers/resampy_resampler.py:14`
  (`import resampy`) pulls numba/llvmlite in; no other probed module does.
- llvmlite reads `LLVMLITE_ENABLE_IR_LAYER_TYPED_POINTERS` at import (`llvmlite/__init__.py:20`).
- PyJWT reads `SPHINX_BUILD` at import (`jwt/api_jwt.py:25`, `jwt/algorithms.py:104`), typing only;
  num2words reads none; av's Python reads only `PYAV_TESTDATA_DIR` (`av/datasets.py:13`).
- websockets reads `WEBSOCKETS_*` tunables at import (`websockets/http11.py:33-53`, `websockets/frames.py:143`,
  `websockets/asyncio/messages.py:19`, `websockets/client.py:409-412`, `websockets/legacy/client.py:601-604`); pipecat's STT/TTS/LLM
  base modules import websockets at import (`pipecat/services/stt_service.py:16`). conftest pops
  `WEBSOCKETS_*` at module top.

#### openai and groq (reached only through Pipecat's vendor services, which ARCH-BAN bans)

- pipecat imports openai at module level only in `pipecat/adapters/llm/services/*_adapter.py`
  (`pipecat/adapters/llm/services/open_ai_adapter.py:11`), under TYPE_CHECKING in `pipecat/processors/aggregators/llm_context.py:61-62`, and lazily from
  `pipecat/services/llm_service.py:521`. Groq STT subclasses the Whisper base, which imports `AsyncOpenAI`
  (`pipecat/services/whisper/base_stt.py:17`).
- Importing openai reads `OPENAI_LOG` (`openai/_utils/_logs.py:38`, via `openai/__init__.py:164`),
  `OPENAI_API_TYPE`, `OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT` (`openai/__init__.py:212-216`),
  `DEFER_PYDANTIC_BUILD` (`openai/_models.py:150`).
- Pipecat's Groq STT client (`pipecat/services/whisper/base_stt.py:244`) leaves `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`,
  `OPENAI_ADMIN_KEY`, `OPENAI_WEBHOOK_SECRET` and `OPENAI_CUSTOM_HEADERS` to the env
  (`openai/lib/_client_auth.py:654-676`, `:702-717`); org/project become request headers
  (`openai/_client.py:1090-1091`).
- **[from the check]** Pipecat's Groq TTS builds `AsyncGroq(api_key=...)` with no base_url
  (`pipecat/services/groq/tts.py:171`, no base_url parameter at :95), so `GROQ_BASE_URL`
  (`groq/_client.py:302`) redirects every request, key included; `GROQ_CUSTOM_HEADERS`
  (`groq/_client.py:306`) adds headers.
- **[from the check]** Importing groq runs `setup_logging` (`groq/__init__.py:79`), which reads
  `GROQ_LOG` (`groq/_utils/_logs.py:17`); `debug`/`info` lowers the groq and httpx loggers at import.

#### aiortc and aioice

- aiortc falls back to `stun:stun.l.google.com:19302` in `RTCIceGatherer.getDefaultIceServers()`
  (`aiortc/rtcicetransport.py:226`), called only at :193 when `iceServers is None`: no
  configuration (`aiortc/rtcpeerconnection.py:297`) or `RTCConfiguration()` with its default None
  (`aiortc/rtcconfiguration.py:62`). The gatherer is built at addTransceiver, createDataChannel or
  setRemoteDescription (`aiortc/rtcpeerconnection.py:1130`, `:1135`). `iceServers=[]` never reaches it.
- Fixture point (re-probed by the checker with non-loopback sockets blocked): monkeypatch
  `aiortc.rtcicetransport.RTCIceGatherer.getDefaultIceServers` (same object as
  `aiortc.RTCIceGatherer`) with a raising classmethod; `RTCPeerConnection().addTransceiver('audio')`
  and `RTCPeerConnection(RTCConfiguration()).createDataChannel(...)` then raise synchronously,
  `RTCConfiguration(iceServers=[])` does not (`aiortc/rtcicetransport.py:193`).
- `SmallWebRTCConnection` turns a falsy `ice_servers` into `[]` (`pipecat/transports/smallwebrtc/connection.py:279-280`)
  and builds `RTCConfiguration(iceServers=self.ice_servers, bundlePolicy=MAX_BUNDLE)` (:335-336).
- aiortc and aioice read no env var. aioice resolves a remote `.local` mDNS candidate by multicast to
  224.0.0.251:5353 (`aioice/ice.py:502`, `aioice/mdns.py:18-19`): LAN traffic the STUN patch does not
  block; browsers commonly send such candidates.

---

### Step 4, bullet 2: Pipecat log lines with call content, or printed by default

- The banner `ᓚᘏᗢ Pipecat {__version__} (Python ...)` is INFO under name `pipecat`, version only
  (`pipecat/__init__.py:54`); it fires on the first import of any `pipecat.*` module, and a probe
  with `logger.disable("pipecat")` first captured nothing (gate at :53). An ERROR fires at import if
  `pipecat_flows` is installed (:45); it is not installed here.
- loguru's default sink is DEBUG (`loguru/_defaults.py:40`): every Pipecat DEBUG+ line prints by
  default unless the namespace is disabled; TRACE does not.
- **[from the check]** A disabled name returns before any sink sees the record
  (`loguru/_logger.py:1995`; emit at :2066): while `pipecat` is disabled no sink, a forwarder included,
  gets any Pipecat record. Forwarding WARNING+ needs the namespace enabled and per-sink filtering, and
  then the default stderr sink (`loguru/__init__.py:32`, DEBUG) prints every Pipecat DEBUG line unless
  removed.
- Name and disable coverage: the record name is the defining module's `__name__`
  (`loguru/_logger.py:1974`); the check matches `name + "."` against `"pipecat."` (:1989-1991), so it
  covers `pipecat` and `pipecat.*`, not `pipecat_flows`; a later disable updates cached names
  (:1809-1811). Exception: `LLMService._log_llm_event` uses `opt(depth=2)`
  (`pipecat/services/llm_service.py:576`), unused in M2.
- TTS spoken text at DEBUG when not streamed: `Generating TTS [{text}]`
  (`pipecat/services/tts_service.py:1971`); at TRACE per call when streamed (:1969).
- **[corrected]** The DEBUG line with `self._streamed_text` (`pipecat/services/tts_service.py:1424`)
  is in `_handle_llm_response_end`, run on `LLMFullResponseEndFrame` or `EndFrame` (:1184,
  :1393-1394), not at a turn end. In TOKEN mode `TTSSpeakFrame` text builds up in `_streamed_text`
  (:1744-1745), `_handle_tts_speak` (:1464) never flushes it, so it is logged at the next such frame
  or at `EndFrame`, several utterances in one line; an interruption clears it unlogged (:1531). Call
  text reaches DEBUG in both aggregation modes.
- Unspoken text at WARNING when the TTS is unusable (`pipecat/services/tts_service.py:1982`); stale
  word times at TRACE (:1016). Content-bearing "examples" at `pipecat/services/tts_service.py:155-167`, :2364,
  `pipecat/services/stt_service.py:81-89` and the observers are docstrings that never run.
- `STTService` logs no transcript (`pipecat/services/stt_service.py:456` is the content-free empty-audio
  warning); neither does `SegmentedSTTService` (from :795).
- Remote ICE candidates at DEBUG with IP, port, relatedAddress
  (`pipecat/transports/smallwebrtc/connection.py:853`; repr from `aiortc/rtcicetransport.py:38`),
  once per PATCHed candidate (`pipecat/transports/smallwebrtc/request_handler.py:260`). Signalling messages at DEBUG as raw dicts
  (`pipecat/transports/smallwebrtc/connection.py:837`). Import-time DEBUG `[SCTP] USERDATA_MAX_LENGTH ...` (`pipecat/transports/smallwebrtc/connection.py:80`).
- **[corrected]** `logger.error(f"Error parsing JSON message {message}, {e}")`
  (`pipecat/transports/smallwebrtc/connection.py:389`) logs the raw data-channel message at ERROR on a
  `json.loads` failure, a missing `"type"` (:380), a non-dict JSON value, or an error in
  `_handle_signalling_message` incl. pydantic validation (:839); bytes messages appear as a bytes repr
  (`aiortc/rtcsctptransport.py:1822`). App-message handler exceptions never reach it: they are logged
  at ERROR by `pipecat/utils/base_object.py:285-290`. Holding loguru at INFO does not hide it.
- `print("Warning: _queue does not exist or has changed in aiortc.")` goes to stdout outside loguru
  (`pipecat/transports/smallwebrtc/connection.py:191`); no content.
- On an offer error the request handler logs ERROR (`pipecat/transports/smallwebrtc/request_handler.py:239`) then the whole
  `SmallWebRTCRequest` at DEBUG, SDP (IPs, ice-pwd, fingerprint) and `request_data` included
  (`pipecat/transports/smallwebrtc/request_handler.py:240`; dataclass :37-41). Never put a token in
  `request_data`.
- INFO lines: pc_id on reuse (`pipecat/transports/smallwebrtc/request_handler.py:200`) and discard (:212); "Connecting/Disconnecting
  to Small WebRTC" (`pipecat/transports/smallwebrtc/transport.py:544`, `:551`); inbound app messages
  only at TRACE (`pipecat/transports/smallwebrtc/transport.py:811`).
- RTVI is on by default (`pipecat/pipeline/worker.py:521-522`); its processor logs every inbound
  non-RTVI message's full content at WARNING (`pipecat/processors/frameworks/rtvi/processor.py:293`),
  validation errors at WARNING (:302, :385); the default RTVI observer sends user transcriptions and
  bot text to the client (`pipecat/processors/frameworks/rtvi/observer.py:227`, `:234`). `system_logs_enabled` defaults False
  (`pipecat/processors/frameworks/rtvi/observer.py:238`); when True it adds a loguru sink (:332).
- Worker start lines are DEBUG and name-only (`pipecat/pipeline/worker.py:1327`, :1344;
  `pipecat/workers/runner.py:230`, :273, :459).
- **[corrected]** `pipecat/pipeline/worker.py:1642-1648` has three branches: fatal ErrorFrame at ERROR
  with the frame (:1643); a no-longer-usable processor logged at ERROR with its name only (:1645-1646,
  :1666); the rest at WARNING with the frame (:1648). `ErrorFrame.__str__` holds the error text
  (`pipecat/frames/frames.py:1360`). `push_error` (:983/:985) goes through `push_error_frame`, which logs
  `error.error` at ERROR (`pipecat/processors/frame_processor.py:1032`).
- **[from the check]** Any exception a processor raises in `process_frame` becomes
  `push_error("Error processing frame: {e}")` (`pipecat/processors/frame_processor.py:1346`), logged at
  ERROR and again at WARNING by the worker; `push_frame` failures as "Uncaught exception: {e}" (:1250).
  A bridge's unhandled SDK error text is logged even if it never calls `push_error`.
- Event-handler exceptions (the app's own handlers included) are logged at ERROR with `str(e)`
  (`pipecat/utils/base_object.py:288`).
- **[from the check]** An exception from the app's `webrtc_connection_callback` is logged at ERROR
  with `str(callback_error)` and swallowed; the SDP answer is still returned
  (`pipecat/transports/smallwebrtc/request_handler.py:222`).
- `FrameLogger` logs every frame at DEBUG (`pipecat/processors/logger.py:69`); `TranscriptionFrame`'s
  str holds `user_id` and text (`pipecat/frames/frames.py:624`). `TranscriptionLogObserver`
  (`pipecat/observers/loggers/transcription_log_observer.py:56`), `DebugLogObserver`
  (`pipecat/observers/loggers/debug_log_observer.py:216`), `LLMLogObserver` (`pipecat/observers/loggers/llm_log_observer.py:64`, :76) log content; all
  opt-in.
- **[corrected]** Observers added by default without RTVI: `TurnTrackingObserver` (TRACE turn counts,
  `pipecat/observers/turn_tracking_observer.py:186`; `pipecat/pipeline/worker.py:302`) and `IdleFrameObserver`, since `idle_timeout_secs`
  defaults to 300 (`pipecat/pipeline/worker.py:105`, :313, :566-571); the worker then logs "Idle
  timeout detected." at WARNING (:1781).
- **[from the check]** OpenTelemetry is installed, so `is_tracing_available()` is True
  (`pipecat/utils/tracing/setup.py:23`) and `@traced_tts/@traced_stt` are real
  (`pipecat/utils/tracing/service_decorators.py:285-286`); `enable_tracing` defaults False (`pipecat/pipeline/worker.py:301`); turned on it
  adds `UserBotLatencyObserver` and `TurnTraceObserver` (`pipecat/pipeline/worker.py:488-502`).
- VAD/turn path: `VADProcessor` logs only "User started/stopped speaking" (`pipecat/processors/audio/vad_processor.py:73`, :81),
  `UserTurnProcessor` only strategy names (`pipecat/turns/user_turn_processor.py:237`, :255, :279),
  Smart Turn "End of Turn result: {state}" (`pipecat/audio/turn/smart_turn/base_smart_turn.py:167`): no transcript. Transcript lines
  exist only in unused strategies (`pipecat/turns/user_stop/classifier_user_turn_stop_strategy.py:279`,
  `pipecat/turns/user_stop/eager_user_turn_stop_strategy.py:191`, `pipecat/turns/eager_end_of_turn_mixin.py:132` TRACE).
- Smart Turn's audio-to-disk (`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:46`, :97) is outside loguru: the namespace
  disable does not stop it.
- Pipecat's only stdlib logging: module-level `logging.warning/error` in
  `pipecat/utils/tracing/service_decorators.py:303` (root logger), only inside the `@traced_*`
  decorators, which the base classes do not apply; `stdlib: logging/__init__.py:2199-2200` calls
  `basicConfig()` there when root has no handler.
- No pipecat module calls `logger.enable`; `logger.remove/add` only in the CLI, evals, the RTVI log
  sink, and `pipecat/runner/run.py:2211` (`logger.remove()`, then stderr at DEBUG, :2212).
- aiortc: `logging.getLogger(__name__)` per module and a NullHandler on `aiortc`
  (`aiortc/__init__.py:56`); prints nothing by default. Full local and remote SDP at DEBUG
  (`aiortc/rtcpeerconnection.py:804-814`, `:886-890`); RTP and SCTP reprs carry no payload
  (`aiortc/rtp.py:664-669`, `aiortc/rtcsctptransport.py:210-214`).
- aioice: loggers `aioice.ice`, `aioice.turn`, NullHandler on `aioice` (`aioice/__init__.py:10`). INFO
  already holds IPs: "Check %s %s -> %s" (`aioice/ice.py:988`, via :220), prflx (:833), mDNS (:510),
  invalid host (:523), bind failure (:1028), TURN channel (`aioice/turn.py:105`); DEBUG logs every STUN
  message (`aioice/ice.py:272`, :326; `aioice/stun.py:266`).
- uvicorn loggers `uvicorn.error`, `uvicorn.access`, `uvicorn.asgi`, `uvicorn`; default
  `LOGGING_CONFIG` sends `uvicorn` to stderr and `uvicorn.access` to stdout at INFO, propagate False,
  `disable_existing_loggers` False (`uvicorn/config.py:85`, `:112`), applied when `log_config` is not
  None (:398).
- Access log: client `ip:port`, method, path with query, INFO (`uvicorn/protocols/http/h11_impl.py:477-484`,
  `uvicorn/protocols/http/httptools_impl.py:484`), only if `uvicorn.access` has handlers (`uvicorn/protocols/http/h11_impl.py:57`).
  **[from the check]** uvicorn 0.54's zttp protocol has its own access line
  (`uvicorn/protocols/http/zttp_impl.py:464`, `uvicorn/protocols/http/zttp_h2_impl.py:477`); `access_log=False` covers all
  (`uvicorn/config.py:427-429`).
- WebSocket handshakes on `uvicorn.error` at INFO with client and path
  (`uvicorn/protocols/websockets/websockets_impl.py:281`, `uvicorn/protocols/websockets/websockets_sansio_impl.py:440`, `uvicorn/protocols/websockets/wsproto_impl.py:385`); TRACE adds
  connect/lose lines and `MessageLoggerMiddleware` (`uvicorn/protocols/http/h11_impl.py:103-105`, `uvicorn/config.py:541-542`). Never
  run with `log_level="trace"`.

---

### Step 4, bullet 3: how `SegmentedSTTService` cuts, and one request per user turn

- `STTService.process_frame` reacts to `InputAudioRawFrame`, VAD start/stop (TTFB), `UserStoppedSpeakingFrame`
  (deferred reconnect), `STTUpdateSettingsFrame`, `STTMuteFrame`, `InterruptionFrame`,
  `LLMContextAssistantTurnFrame`; all else pushed on unchanged (`pipecat/services/stt_service.py:487`).
- **[corrected]** Base `process_audio_frame`: during a reconnect audio is buffered
  (`pipecat/services/stt_service.py:434`) and replayed after (:717-718); dropped while muted (:437-438), not usable
  (:442-443) or empty (:454-459); otherwise `run_stt` once per frame (:463).
- `run_stt(self, audio: bytes)` is the only abstract method, an async generator of `Frame | None`
  (`pipecat/services/stt_service.py:335`); the base calls it only from :463, so a bridge may call it once per turn.
- `STTMuteFrame` is consumed and only sets `_muted` (`pipecat/services/stt_service.py:506`); a bridge overriding
  `process_audio_frame` must check `self._muted` itself.
- `SegmentedSTTService` keeps a rolling 1 s pre-roll before VAD start, unbounded during speech
  (`pipecat/services/stt_service.py:1013`, size :864); on each `VADUserStoppedSpeakingFrame` it pads
  `trailing_silence_secs` (0.5, :828), wraps WAV only when `wants_wav_segments` (:958-959), queues
  `(audio, segment number)` (:965) to one in-order task (:967-978): one request per VAD segment;
  if not usable it clears and queues nothing (:945-947). `finalized` = latest segment (:925).
- `AIService.process_generator` pushes run_stt's frames downstream, `ErrorFrame` via
  `push_error_frame`, which sends it UPSTREAM (`pipecat/services/ai_service.py:270`;
  `pipecat/processors/frame_processor.py:1033`): a downstream session never sees a failed request as a frame.
- **[corrected]** `validate_complete()` logs ONE ERROR line naming every field left NOT_GIVEN
  (`pipecat/services/settings.py:249-251`); `model` (:97) and `STTSettings.language` (:403) both
  default to NOT_GIVEN. Pass `STTSettings(model=None, language=None)`.
- Without `ttfs_p99_latency` (and `supports_ttfs` True) a WARNING and `DEFAULT_TTFS_P99`
  (`pipecat/services/stt_service.py:572`); the `STTMetadataFrame` is broadcast both ways right after StartFrame
  (`pipecat/services/ai_service.py:104`, :234-236).
- `TurnAnalyzerUserTurnStopStrategy(*, turn_analyzer, wait_for_transcript=True)`
  (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:53`; setter :95-97); with False it
  reports the stop as soon as the analyzer says COMPLETE (:336-342). Only the LLM aggregator's
  realtime mode flips it (`pipecat/processors/aggregators/llm_response_universal.py:1101-1104`), never `UserTurnProcessor`.
- It awaits `analyze_end_of_turn` on each VAD stop (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:232`,
  COMPLETE at :269) and treats a COMPLETE from `append_audio` (silence fallback) as the end
  (:206-210). It does not override `decision_scheduled` (base False,
  `pipecat/turns/user_stop/base_user_turn_stop_strategy.py:167`), so the 5 s stop timeout stays armed.
- `UserTurnStrategies` with no or empty lists uses start `[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy()]`
  and stop `[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]`
  (`pipecat/turns/user_turn_strategies.py:137`, :416, :427); defaults `start_mode FIRST`, `stop_mode ALL`
  (:92-93; ALL ends when every stop strategy decided, `pipecat/turns/user_turn_controller.py:646`). Pass both lists.
- Start strategies: Base, External, KrispVivaIP, MinWords, Transcription, VAD, WakePhrase;
  `VADUserTurnStartStrategy` fires on every `VADUserStartedSpeakingFrame`
  (`pipecat/turns/user_start/vad_user_turn_start_strategy.py:27`). `TranscriptionUserTurnStartStrategy`
  fires on any `TranscriptionFrame` (`pipecat/turns/user_start/transcription_user_turn_start_strategy.py:36`), with no bot-state
  check despite its docstring (:34-37).
- **[corrected]** Stop strategies: Base, Classifier, Deferred, Eager, ExternalUserTurnCompletion,
  External, LLMTurnCompletion, SpeechTimeout, TurnAnalyzer; the TurnAnalyzer import is at
  `pipecat/turns/user_stop/__init__.py:16`; SpeechTimeout's `user_speech_timeout=0.6` and
  `wait_for_transcript=True` at `pipecat/turns/user_stop/speech_timeout_user_turn_stop_strategy.py:51-52`.
- Smart Turn defaults `STOP_SECS = 3`, `PRE_SPEECH_MS = 500`, `MAX_DURATION_SECONDS = 8`
  (`pipecat/audio/turn/smart_turn/base_smart_turn.py:27`, params :41-43). The silence fallback returns
  COMPLETE once silence reaches `stop_secs` and clears the buffer (:133); the analysed segment starts
  `pre_speech_ms + start_secs` before speech, capped at 8 s (:215, :233-236): nothing caps the bridge's
  held audio.
- **[from the check]** After a fallback COMPLETE the buffer is already cleared (`pipecat/audio/turn/smart_turn/base_smart_turn.py:138`),
  so the follow-up `analyze_end_of_turn` (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:207`) returns
  `(INCOMPLETE, None)` (`pipecat/audio/turn/smart_turn/base_smart_turn.py:211-212`): fallback turns carry no MetricsFrame or probability.
- **[from the check]** The fallback counts silence per arriving chunk from the strategy's VAD flag
  (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:199`, `pipecat/audio/turn/smart_turn/base_smart_turn.py:130-131`): it resets on speech and
  freezes if audio stops arriving; then only the 5 s stop timeout ends the turn
  (`pipecat/turns/user_turn_controller.py:719-723`).
- Smart Turn v3.2: `LocalSmartTurnAnalyzerV3(*, smart_turn_model_path=None, cpu_count=1, **kwargs)`
  loads `smart-turn-v3.2-cpu.onnx` (8,679,182 bytes) from the wheel
  (`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:50`), session built in `__init__` (:76); imports numpy, onnxruntime, soxr,
  loguru (:15-18); features are vendored numpy (`pipecat/audio/turn/smart_turn/_whisper_features.py:26-27`); torch/transformers only
  in `pipecat/audio/turn/smart_turn/local_smart_turn_v2.py:22-25`. Last 8 s kept, short audio zero-padded at the start (:151, :161),
  COMPLETE when probability > 0.5 (:174).
- Silero: `silero_vad.onnx` (2,327,524 bytes) from `pipecat.audio.vad.data`, CPU provider, 16000 or
  8000 Hz only (`pipecat/audio/vad/silero.py:171`, rate check :209), loaded in `__init__` (:187).
- `VADParams` defaults confidence 0.7, start 0.2, stop 0.2, min_volume 0.6
  (`pipecat/audio/vad/vad_analyzer.py:25`): the plan's starting values.
- **[from the check]** `UserTurnProcessor` passes frames of either direction to its controller
  (`pipecat/turns/user_turn_processor.py:200`), so the bridge's upstream `STTMetadataFrame` reaches the stop strategy
  as its STT timeout (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:170`); harmless with
  `wait_for_transcript=False`.
- **[from the check]** A permanent error marks a processor unusable (`pipecat/processors/frame_processor.py:1016-1017`);
  the base then drops audio (`pipecat/services/stt_service.py:442`). A per-turn bridge needs its own unusable branch that
  still emits one result per turn.
- **[from the check]** `EndFrame`/`CancelFrame` only stop `UserTurnProcessor`'s controllers
  (`pipecat/turns/user_turn_processor.py:204-214`): no `UserStoppedSpeakingFrame` for a turn open at
  hang-up. The bridge drops held audio itself when the call ends, never flushing it
  (`voice/session/io.py`'s end, D-037), unlike `SegmentedSTTService.stop`, which drains
  (`pipecat/services/stt_service.py:875-885`).

### Step 4, bullet 4: Stop, broadcasts, `UserTurnProcessor`, `pc_id`, `TranscriptionFrame`

#### Stop path (the design's 13, **verify**)

- 1.15.0 has no `StartInterruptionFrame`; the frame is `InterruptionFrame(SystemFrame)`, no fields
  (`pipecat/frames/frames.py:1425`). `PipelineParams` has no `allow_interruptions`
  (`pipecat/pipeline/worker.py:197`; no hit in `pipecat/`).
- `UserTurnProcessor` broadcasts an interruption on turn start when the start strategy's
  `enable_interruptions` is true (`pipecat/turns/user_turn_processor.py:244-245`), default True
  (`pipecat/turns/user_start/base_user_turn_start_strategy.py:69`); `VADUserTurnStartStrategy` has no own `__init__`.
  **[corrected]** Other sources also interrupt: `DTMFAggregator` on the first digit
  (`pipecat/processors/aggregators/dtmf_aggregator.py:106`), `RTVIProcessor.interrupt_bot` on
  `send-text`/`send-file` with `run_immediately` (`pipecat/processors/frameworks/rtvi/processor.py:481`, `:569`), voicemail and
  speech-to-speech LLM services.
- Any processor can call `broadcast_interruption()`: resets its own process queue, stops metrics,
  pushes `InterruptionFrame` downstream and upstream (`pipecat/processors/frame_processor.py:1048`).
- Every `FrameProcessor` handles `InterruptionFrame` unconditionally: cancels and recreates its
  process task, keeping only `interruptible=False` frames (`pipecat/processors/frame_processor.py:868-869`, :1179-1180;
  `pipecat/utils/frame_queue.py:74-83`). An overriding `process_frame` must call `super()` and push it on.
- `TTSService` on `InterruptionFrame` resets its aggregators and drops every interruptible audio
  context (`pipecat/services/tts_service.py:1179`); `run_tts` runs in the process task, which the
  interruption cancels.
- `BaseOutputTransport` pushes the frame on and calls the media sender's `handle_interruptions`
  (`pipecat/transports/base_output.py:379`), which resets the audio queue, keeps only uninterruptible
  audio, and emits `BotStoppedSpeakingFrame` if none is left (:621).
- `InterruptionWorkerFrame`, pushed either way, makes the worker queue an `InterruptionFrame` at the
  pipeline head (`pipecat/pipeline/worker.py:1637`): for a stopper downstream of the TTS.
- `OutputTransportMessageFrame` (DataFrame) is queued in the audio queue behind audio
  (`pipecat/transports/base_output.py:702`, sent at :914-915) and dropped by a Stop; `OutputTransportMessageUrgentFrame`
  (SystemFrame) is sent at once (:382-383).
- **[from the check]** `Frame.interruptible` is `field(default=True, init=False)`
  (`pipecat/frames/frames.py:106`): set it on the instance after construction, as
  `pipecat/transports/base_output.py:665` does.
- SmallWebRTC's `write_audio_frame` awaits `add_audio_bytes` until `RawAudioTrack.recv()` consumed the
  last 10 ms piece (`pipecat/transports/smallwebrtc/transport.py:503`); only the chunk being written
  (`audio_out_10ms_chunks=4`, 40 ms) sits in the track, and an interruption does not clear it.

#### Broadcast directions and frame order

- `VADProcessor` pushes each frame first, then runs the VAD (`pipecat/processors/audio/vad_processor.py:126`,
  :134); it emits `VADUserStartedSpeakingFrame(start_secs)`, `VADUserStoppedSpeakingFrame(stop_secs)`,
  `UserSpeakingFrame` (at most every 0.2 s) and `SpeechControlParamsFrame` (`pipecat/audio/vad/vad_controller.py:142`).
- `broadcast_frame` pushes a copy downstream then upstream (`pipecat/processors/frame_processor.py:1085`); same for
  `UserTurnProcessor`'s user frames and `InterruptionFrame`. Both directions share one `__input_queue`
  (`pipecat/processors/frame_processor.py:749`), so the upstream copy arrives after audio already passed.
- With no audio for `audio_idle_timeout` (1.0 s) while SPEAKING, `VADController` forces QUIET and
  fires `on_speech_stopped` (`pipecat/audio/vad/vad_controller.py:220`).
- `UserTurnProcessor` pushes every frame but Start, End, Cancel and Proposed* in its own direction
  first (`pipecat/turns/user_turn_processor.py:198`; Start/End :178, :183), then feeds the controllers (:200).
- On turn start: `UserStartedSpeakingFrame` (when `enable_user_speaking_frames`), then
  `InterruptionFrame` if enabled (`pipecat/turns/user_turn_processor.py:240`, :245); on stop
  `UserStoppedSpeakingFrame` (:258), also after the 5 s `user_turn_stop_timeout` (:92;
  `pipecat/turns/user_turn_controller.py:723`); a cancelled speculation broadcasts `UserTurnResponseCancelFrame` (:229).
- Inside an open turn, new speech fires only `on_user_turn_resumed` (no frame)
  (`pipecat/turns/user_turn_controller.py:453`, start guard :500); no stop while the user speaks (:685).
  In ALL mode `on_user_turn_inference_triggered` fires before the stop (:638).
- `UserTurnProcessor` events: `on_user_turn_started(proc, strategy)`, `_stopped(proc, strategy)`,
  `_resumed(proc, UserTurnResumedParams)`, `_stop_timeout(proc)`, `_idle(proc)`,
  `_inference_triggered(proc, strategy)` (`pipecat/turns/user_turn_processor.py:112`). **[from the check]** They are
  registered without `sync=True` (:112-117), so each handler runs in its own task
  (`pipecat/utils/base_object.py:261`), not ordered against frames: key turns on the frames.
- Queue tiers: StartFrame, then SystemFrames, then data/control, arrival order within a tier
  (`pipecat/processors/frame_processor.py:143-145`); SystemFrames on the input task, data on the process task (:1369-1372).
  A turn's `TranscriptionFrame` (data) can be overtaken by the next turn's `UserStartedSpeakingFrame`.
- A transcript waiting in the session's queue is dropped by an `InterruptionFrame` unless pushed with
  `interruptible=False` (`pipecat/utils/frame_queue.py:75`); Whisper must run on the bridge's own task.
- Order after `UserTurnProcessor` (source-derived, matched by spike run A): audio, `VADUserStartedSpeakingFrame`,
  `UserStartedSpeakingFrame`, `InterruptionFrame` (if on), then `UserSpeakingFrame` (`pipecat/audio/vad/vad_controller.py:183-184`);
  a pause judged INCOMPLETE gives VAD stop + MetricsFrame, audio, VAD start, no turn frame; turn end
  gives VAD stop, `MetricsFrame` (SystemFrame, `pipecat/frames/frames.py:1671`), `UserStoppedSpeakingFrame`.
- Bridge place: `transport.input() -> VADProcessor -> UserTurnProcessor -> STT bridge -> session`
  (`pipecat/processors/audio/vad_processor.py:134`); the bridge's transcripts go downstream only, so they never reach
  `UserTurnProcessor` and cannot open phantom turns.
- Turn frames carry no ID; `Frame.metadata` is a free dict (`pipecat/frames/frames.py:103`), `TranscriptionFrame.result`
  is `Any`. The bridge numbers turns and stamps the number. FIFO counting also works if exactly one
  transcript per turn is pushed with `interruptible=False`.

#### Frames

- `VADUserStartedSpeakingFrame` carries `start_secs` and `timestamp = time.time()`
  (`pipecat/frames/frames.py:1580-1581`); the stopped frame `stop_secs` and `timestamp` (:1595-1596).
- `UserStartedSpeakingFrame` (:1437), `UserStoppedSpeakingFrame` (:1448), `UserSpeakingFrame` (:1518)
  are field-less SystemFrames; `ProposedUserStoppedSpeakingFrame` is a ControlFrame (:1619).
- `TranscriptionFrame(TextFrame)`: `text`, `user_id: str` and `timestamp: str` required,
  `language: Language | None`, `result: Any | None`, `finalized: bool = False`, kw-only `perception`
  (`pipecat/frames/frames.py:616`); TextFrame is a DataFrame (:349); Frame adds `id`, `metadata`,
  `interruptible`.
- `InputAudioRawFrame(SystemFrame, AudioRawFrame)`: `audio`, `sample_rate`, `num_channels`, computed
  `num_frames` (`pipecat/frames/frames.py:1896`); SmallWebRTC sends plain `InputAudioRawFrame` (`pipecat/services/stt_service.py:451`).
- `TTSAudioRawFrame(OutputAudioRawFrame)`: positional `audio`, `sample_rate`, `num_channels`, then
  `context_id: str | None = None` (`pipecat/frames/frames.py:287`, :197-199).
- `ErrorFrame(SystemFrame)`: `error: str` (secrets redacted in `__post_init__`), `fatal` (deprecated
  since 1.8.0), `processor`, `exception`, `category` (`pipecat/frames/frames.py:1296`); `FatalErrorFrame` deprecated.

#### `PipelineWorker`, `WorkerRunner`, the TTS base

- `class PipelineWorker(BaseWorker)` (`pipecat/pipeline/worker.py:211`); `PipelineTask` is a deprecated
  alias (decorator :1830), `pipecat/pipeline/task.py` only re-exports.
- `WorkerRunner` in `pipecat/workers/runner.py`; `async def add_workers(self, *workers)` (:197);
  `PipelineRunner` deprecated (`pipecat/pipeline/runner.py:27`). `run(worker=None, *, auto_end=True)`
  (:235); passing a worker is deprecated; `auto_end=False` keeps a long-lived host up.
- `handle_sigint=True` by default; on Windows it falls back to a process-wide `signal.signal(SIGINT)`
  (`pipecat/workers/runner.py:545`). Pass `handle_sigint=False` (Pipecat's own server does,
  `pipecat/runner/types.py:182`).
- `WorkerRunner.__init__` uses `asyncio.get_running_loop()` (`pipecat/workers/runner.py:142`): build it
  inside a running loop.
- `PipelineParams`: `audio_in_sample_rate=16000`, `audio_out_sample_rate=24000`, `enable_metrics=False`,
  ... (`pipecat/pipeline/worker.py:197`).
- `idle_timeout_secs=300`, `cancel_on_idle_timeout=True`, `cancel_runner_on_idle_timeout=True`
  (`pipecat/pipeline/worker.py:295`): one idle call would cancel a shared runner.
- `enable_rtvi=None` means on unless bridged; an `RTVIProcessor` is prepended and an `RTVIObserver`
  added (`pipecat/pipeline/worker.py:610`); RTVI accepts `disconnect-bot` (`pipecat/processors/frameworks/rtvi/processor.py:324-325`) and turns every
  ErrorFrame into a message to the browser (:234). **[from the check]** It also lets the browser inject
  `send-text` (:367), `raw-audio` (:373), `dtmf` (:375), `llm-function-call-result` (:364).
- `pipecat/runner/` is the dev runner (`pipecat/runner/run.py:7`), not the pipeline runner.
- `run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]`
  (`pipecat/services/tts_service.py:808`); yield `TTSAudioRawFrame(pcm, self.sample_rate, 1, context_id=context_id)`.
- `TextAggregationMode` StrEnum `SENTENCE`/`TOKEN` (`pipecat/services/tts_service.py:96`), default SENTENCE (:326-327);
  TOKEN yields each incoming text at once (`pipecat/utils/text/simple_text_aggregator.py:83-85`), so `run_tts` once per
  TextFrame.
- TTS sample rate = constructor `sample_rate` or `PipelineParams.audio_out_sample_rate`
  (`pipecat/services/tts_service.py:601`); the output transport resamples a mismatched frame (`pipecat/transports/base_output.py:654`).
- `push_start_frame` and `push_stop_frames` default False (`pipecat/services/tts_service.py:185`); stop frame on
  completion for HTTP services (:911-914) or after `stop_frame_timeout_s=3.0` (:2256-2257); OpenAI TTS
  sets both True (`pipecat/services/openai/tts.py:217-218`); `TTSStoppedFrame` ends BotSpeaking
  (`pipecat/transports/base_output.py:918-923`).
- **[corrected]** The docstring says `run_tts` must create its audio context (`pipecat/services/tts_service.py:867`),
  but `append_to_audio_context` recreates a missing one when `context_id == self._turn_context_id`
  (:1061, :1064), the turn id being reused by default (`reuse_context_id_within_turn=True`, :219, :845).
  Without `push_start_frame` what is lost is `TTSStartedFrame` and the timeout `TTSStoppedFrame`
  (:2236, :2256).
- `max_consecutive_zero_audio_contexts=3` (`pipecat/services/tts_service.py:199`): three silent contexts in a row mark
  the service unusable.

#### SmallWebRTC transport, `pc_id`, PATCH, data channel, failures

- `SmallWebRTCConnection(ice_servers=None, connection_timeout_secs: int = 60)`
  (`pipecat/transports/smallwebrtc/connection.py:267`, :279).
- The answer: setRemoteDescription, forced sendrecv, createAnswer, setLocalDescription, which awaits
  gathering (`aiortc/rtcpeerconnection.py:859`); `get_answer` returns `{sdp, type, pc_id}`
  (`pipecat/transports/smallwebrtc/connection.py:594`). The server never trickles.
- `pc_id = f"{self.name}-{uuid.uuid4().hex}"`, name `SmallWebRTCConnection#N`
  (`pipecat/transports/smallwebrtc/connection.py:341`; `pipecat/utils/base_object.py:72`): server-chosen, contains `#`.
- `SmallWebRTCRequest` dataclass: `sdp`, `type`, `pc_id`, `restart_pc`, `request_data`;
  `IceCandidate`: `candidate`, `sdp_mid`, `sdp_mline_index` (snake_case, required);
  `SmallWebRTCPatchRequest`: `pc_id`, `candidates` (`pipecat/transports/smallwebrtc/request_handler.py:61`).
- A known `pc_id` renegotiates that connection; an unknown or absent one (MULTIPLE, default) makes a new
  connection keyed by the server's id (`pipecat/transports/smallwebrtc/request_handler.py:235`); SINGLE answers 400 on mismatch.
- The connection callback runs before the answer returns; its exception is logged and swallowed
  (`pipecat/transports/smallwebrtc/request_handler.py:221`).
- PATCH for an unknown `pc_id` raises `HTTPException(404, "Peer connection not found")`
  (`pipecat/transports/smallwebrtc/request_handler.py:248`); the map is filled only after the answer; the `closed` handler pops it
  (:210-213).
- Empty candidate becomes None (`pipecat/transports/smallwebrtc/request_handler.py:259`). **[corrected]** aiortc's condition at
  `aiortc/rtcpeerconnection.py:420-422` sends None to every transceiver's transport, bundled or not,
  and to SCTP (:427); `aiortc/rtcicetransport.py:305-308` passes it once per ICE transport; aioice
  0.11.0 prunes components and sets `_remote_candidates_end` (`aioice/ice.py:491-499`).
- A non-empty candidate goes through `candidate_from_sdp`, taking `bits[0]` as foundation without
  stripping `candidate:` (`aiortc/sdp.py:104`). **[from the check]** A malformed one fails
  `assert len(bits) >= 8` (`aiortc/sdp.py:100`), uncaught by `handle_patch_request`
  (`pipecat/transports/smallwebrtc/request_handler.py:252`): a 500.
- `renegotiate(restart_pc=True)` closes the peer and re-initialises with a new pc_id; the old key stays
  in the map (`pipecat/transports/smallwebrtc/connection.py:484`).
- `SmallWebRTCTransport(webrtc_connection, params: TransportParams, input_name=None, output_name=None)`;
  `audio_in_enabled=False`, `audio_out_enabled=False` by default, `audio_out_10ms_chunks=4`,
  `audio_out_write_timeout_secs=10.0`, no `vad_analyzer` field (`pipecat/transports/base_transport.py:113`);
  rates fall back to `PipelineParams` (`pipecat/transports/smallwebrtc/transport.py:529-530`), input resampled by PyAV
  (`pipecat/transports/smallwebrtc/transport.py:468-473`).
- `RawAudioTrack.add_audio_bytes` raises unless whole 10 ms pieces (`pipecat/transports/smallwebrtc/transport.py:136`).
- Inbound: a str starting with `"ping"` is a keepalive (`pipecat/transports/smallwebrtc/connection.py:376`); other messages must be
  JSON with `"type"`; `type "signalling"` with a `message` is consumed (only `trackStatus`).
- `is_connected()` trusts aiortc until the first ping, then needs one within 3 s
  (`pipecat/transports/smallwebrtc/connection.py:708`); app messages arriving while false are parked, flushed only by `connect()`.
  **[from the check]** Bot audio is also dropped then: `_can_send` is `is_connected and not is_closing`
  (`pipecat/transports/smallwebrtc/transport.py:502`, `:629`).
- Inbound app messages: `InputTransportMessageFrame` (SystemFrame) broadcast both ways, and transport
  event `on_app_message(transport, message, sender)` (`pipecat/transports/smallwebrtc/transport.py:1078`); the docstring's
  `on_client_message` does not exist.
- Outbound: `send_app_message(json.dumps)` (`pipecat/transports/smallwebrtc/connection.py:795`) queues up to 50 until the channel
  opens, drops after 10 s without one; nothing is sent while the client is closing
  (`pipecat/transports/smallwebrtc/transport.py:568-575`). The server sends `{"type":"signalling","message":{"type":"peerLeft"}}` on
  disconnect (`pipecat/transports/smallwebrtc/connection.py:566`) and `renegotiate` when video exists.
- ICE `failed` -> `failed` handler, then `_close()` (`pipecat/transports/smallwebrtc/connection.py:685`); `SmallWebRTCClient`
  subscribes only to connected/disconnected/closed/app-message/track-status (`pipecat/transports/smallwebrtc/transport.py:268-293`), so
  a failure surfaces as `closed` -> `on_client_disconnected` (:620-621); no ErrorFrame.
- **[corrected]** A peer stuck in `connecting` is closed after 60 s (`pipecat/transports/smallwebrtc/connection.py:611`); aiortc has no
  `disconnected` state (`aiortc/rtcpeerconnection.py:1272`). After connect, a dropped path fails in
  about 30 s: aioice's consent checks close after `CONSENT_FAILURES=6` failures about 5 s apart
  (`aioice/ice.py:1124-1127`), aiortc maps that to `failed` (`aiortc/rtcicetransport.py:364-366`).
- **[from the check]** aioice 0.11.0 never reports ICE failure before end-of-candidates
  (`aioice/ice.py:877-878`); the marker comes as an empty PATCH or `a=end-of-candidates` in the offer
  (`aiortc/rtcpeerconnection.py:179-180`).
- An output write not returning within 10 s -> `push_error(..., force_treat_as_permanent=True)`
  (`pipecat/transports/base_output.py:1074`); a write while not connected returns False silently (`pipecat/transports/smallwebrtc/transport.py:502-505`).
  Input: a 2 s receive timeout only warns, a `MediaStreamError` clears the track (`pipecat/transports/smallwebrtc/transport.py:453`).
- `push_error_frame` marks unusable on a permanent category, pushes upstream; at the source it fires
  `on_pipeline_error` (`pipecat/pipeline/worker.py:1639`); `ProcessorUnusablePolicy` defaults to CONTINUE (`pipecat/pipeline/worker.py:316`).

---

### Step 4, bullet 5: FastAPI `telemetry=`, uvicorn proxy headers, PyJWT (and num2words)

#### FastAPI 0.162.0

- `telemetry=` defaults: `tracer_provider/meter_provider/logger_provider=None`, `tracing/metrics/logs=True`,
  `operation_spans=True`, `auto_configure` from the env, `exclude=None`; caller keys merged over them
  (`fastapi/applications.py:1019`); probe confirmed.
- Server span attributes: `url.scheme`, `http.request.method`, `network.protocol.version`,
  `server.address/port`, `url.path`, `url.query` (only X-Amz-*, `sig`, X-Goog-Signature redacted,
  `fastapi/telemetry/_asgi.py:44-52`), `http.route`, status, `error.type`
  (`fastapi/telemetry/_asgi.py:306`); also `http.request.method_original` for unknown methods (:320-321).
  No client address or headers. Operation spans carry only `code.function.name` (`fastapi/telemetry/_api.py:213`).
- WebSocket spans: `network.protocol.name='websocket'`, no `url.path`/`url.query` (`fastapi/telemetry/_asgi.py:303`).
- A client's `traceparent`/baggage becomes the server span's parent
  (`fastapi/telemetry/_asgi.py:299`).
- With a logger provider, unhandled exceptions become OTel log records with the exception
  (`fastapi/telemetry/_asgi.py:102`); validation failures log only a count and the route (`fastapi/telemetry/_api.py:162-173`).
- `telemetry={'tracing': False, 'metrics': False, 'logs': False, 'auto_configure': False}` makes
  `enabled()` False; a probe with a global SDK TracerProvider produced 0 spans
  (`fastapi/applications.py:1192`). Alternatives: `exclude=lambda scope: True` (`fastapi/telemetry/_asgi.py:238`) or
  explicit providers. fastapi always imports opentelemetry-api.
- `APIRouter(lifespan=...)` is merged at `include_router`: parent entered first, exits reversed, parent
  state wins (`fastapi/routing.py:3422`, :253; `fastapi/applications.py:1675`). **[from the check]** It
  merges again on every include, and copies `on_startup/on_shutdown` (`fastapi/routing.py:3418-3425`):
  including a router twice runs its lifespan twice.
- Starlette's lifespan sends `startup.failed`/`shutdown.failed` with `traceback.format_exc()`
  (`starlette/routing.py:661`, :669-675); uvicorn logs that message at ERROR on `uvicorn.error`
  (`uvicorn/lifespan/on.py:121`): lifespan errors must hold no secret.

#### uvicorn 0.54.0

- `forwarded_allow_ips` in code wins over `FORWARDED_ALLOW_IPS` (`uvicorn/config.py:363`, probe).
- `proxy_headers=True` by default wraps the app in `ProxyHeadersMiddleware(trusted_hosts=forwarded_allow_ips)`
  (`uvicorn/config.py:544`).
- XFF and X-Forwarded-Proto are honoured only from a trusted peer (`uvicorn/middleware/proxy_headers.py:35`);
  then the client becomes the rightmost untrusted XFF entry (port 0); with `*` the leftmost
  (:176-177; `*` at :109). Probe: peer 127.0.0.1 + XFF 1.2.3.4 -> client `('1.2.3.4', 0)`.
- **[from the check]** Access and WS log lines print the rewritten client
  (`uvicorn/protocols/utils.py:51-55`): a forged XFF from 127.0.0.1 lands in the logs.
- `server_header=True` prepends `server: uvicorn` (`uvicorn/config.py:499`); `date_header` only switch
  for Date (`uvicorn/server.py:257`).
- **[corrected]** HTTP access lines hold the client and the raw path+query
  (`uvicorn/protocols/http/h11_impl.py:476-481`; h11 is the default since httptools is not installed,
  `uvicorn/protocols/http/auto.py:7-10`). The default WS protocol is `websockets_sansio_impl`
  (`uvicorn/protocols/websockets/auto.py:19-21`), whose accepted/403 lines go to `uvicorn.error` at INFO
  (`uvicorn/protocols/websockets/websockets_sansio_impl.py:70`, :440-443), with client and raw query, not gated by `uvicorn.access`.
- **[corrected]** `access_log=False` empties `uvicorn.access` handlers and sets propagate False
  (`uvicorn/config.py:428`): HTTP lines stop; WS handshake lines do not (`uvicorn.error` keeps its
  handler via `uvicorn`, `uvicorn/config.py:110-111`).
- `configure_logging` with the default `log_config` touches only the uvicorn loggers, not root (probe);
  `log_config=None` lets them propagate to the app's root setup (`uvicorn/config.py:398`; levels :419-426).

#### PyJWT 2.15.1

- `enforce_minimum_key_length` (default False) exists in both PyJWS and PyJWT options; enforced, a short
  key raises `InvalidKeyError`, otherwise `InsecureKeyLengthWarning` (`jwt/api_jws.py:206`; probe).
- `encode` checks only the instance's options; module-level `jwt.encode` uses the global PyJWS with
  defaults (`jwt/api_jwt.py:592`). `jwt.PyJWT(options={'enforce_minimum_key_length': True})` builds its
  own PyJWS with it (:49, :67-73); probe: strict encode refuses a 14-byte key, a 32-byte key works.
- `decode` takes the option from merged instance + call options (`jwt/api_jwt.py:263`).
  **[from the check]** `verify_signature` is taken only from per-call options (`jwt/api_jwt.py:242-245`);
  a future `iat` beyond leeway raises `ImmatureSignatureError` (:482-483).
- HMAC minimum = digest size: 32 bytes HS256, 48 HS384, 64 HS512, on the key's UTF-8 bytes
  (`jwt/algorithms.py:483`); empty key always refused (:349-350); PEM/SSH/DER refused as HMAC (:352-360).
- `InsecureKeyLengthWarning(UserWarning)` (`jwt/warnings.py:7`); `InvalidKeyError` subclasses
  `PyJWTError`, not `InvalidTokenError` (`jwt/exceptions.py:59`).
- With verification on, decode raises `DecodeError` without `algorithms` (`jwt/api_jws.py:249`); a header
  `alg` outside the list -> `InvalidAlgorithmError` (:415-416); only PyJWS takes an allowlist in its
  constructor (:39-52).
- `algorithm=None` means `none` (`jwt/api_jws.py:141-145`); `headers['alg']` overrides the argument
  (:153).
- `none` never verifies (`jwt/algorithms.py:303`, :290-297); `verify_signature=False` skips the check
  and defaults the claim checks off (`jwt/api_jws.py:277`; `jwt/api_jwt.py:82-89`).
- `kid` is only type-checked as str (`jwt/api_jws.py:460`); never chooses a key.
- `require` lists claims that must be present and non-null (`jwt/api_jwt.py:432`); exp/iat/nbf/sub/jti
  are checked only if present (:403-410).
- `leeway` loosens iat/nbf/exp (`jwt/api_jwt.py:512`); a token with `aud` and no `audience` raises
  `InvalidAudienceError` (:522-527); `iss` only when `issuer` passed (:568-569).

#### num2words 0.5.14 (Track A)

- `num2words(n, lang='ar')` works (`num2words/__init__.py:32`); `ar_SA` falls back to `ar` (:94-96); an
  unknown language raises `NotImplementedError`; Arabic currency default SR.
- `en` supports cardinal, ordinal, ordinal_num, year, currency (`num2words/__init__.py:40`, :89); English
  ordinals raise `TypeError` for negatives/non-integers (`num2words/base.py:196-200`).
- Arabic ordinals are a table for `number <= 19` (`num2words/lang_AR.py:385`): 0 gives `''`, negatives
  index from the end, 20+ return cardinal-style text; no article, no gender. `ordinal_num` returns the
  same words (:400-401).
- Arabic `to_cardinal` sets `separator = ','` (`num2words/lang_AR.py:409`); 10**51+ raises
  `OverflowError` (:48, :351-353). **[from the check]** The fraction is padded/truncated to 2 digits and
  read as hundredths (:58, :137-149): 2.345 reads "thirty-four".
- Converters are module-level instances mutated per call (`num2words/lang_AR.py:404`; English
  `self.precision` at `num2words/base.py:125`): keep calls on one thread.
- Import loads 56 language modules plus `lang_EU` indirectly and builds every converter
  (`num2words/__init__.py:20`); no I/O or logging at import.

---

### Step 5: the spikes (no Groq request, no network beyond this machine)

All scripts were in the agent's scratch folder (not kept in the repository),
run with `.venv/Scripts/python.exe -I` and every `GROQ_*`/`T2V_*` variable unset (Python 3.12.13,
isolated). Network guards refused 0 sends in every run.

#### Pipeline spike (`spike-pipeline\`)

- **(a) Runner API: confirmed.** 7-processor pipeline (head, VAD, turns, STT bridge, echo, fake TTS,
  tail) ran in runs A, B, C sleep, C hybrid, D; `runner.run()` returned 3-8 ms after `EndFrame` was
  queued, `has_finished()` True, `on_pipeline_finished` fired, no dangling-task line.
- **(b) Input WAVs** from Windows System.Speech (Microsoft David Desktop, 22050 Hz), resampled to 16 kHz
  mono 16-bit, 0.5 s lead and 3.0 s tail silence: `speech_two_16k.wav` (gap 0.88 s),
  `speech_break_16k.wav` (AppendBreak(800 ms) gave 1.30 s), `speech_frag_16k.wav` (first part ends
  mid-phrase, Smart Turn p=0.012; gap 0.86 s; 8.993 s).
- **(b) Frames, run A** (frag file, default start strategy; times from frame 0, speech at 0.52 s):
  VAD start 0.858; bridge gets `UserStartedSpeakingFrame` and `InterruptionFrame` 0.859; VAD stop 3.278
  (INCOMPLETE); VAD start 4.176 -> `on_user_turn_resumed` only; VAD stop 6.177 (COMPLETE);
  `UserStoppedSpeakingFrame` 6.251 (74 ms after the VAD stop); fake STT answers 6.558; TTS emits
  `TTSStartedFrame`, 10 `TTSAudioRawFrame`, `TTSTextFrame`, `LLMAssistantPushAggregationFrame`,
  `TTSStoppedFrame`. Bridge downstream counts: audio 449, VAD start/stop 2/2, `UserSpeakingFrame` 21,
  user start/stop 1/1, `MetricsFrame` 2, `SpeechControlParamsFrame` 2, `InterruptionFrame` 1. Copies of
  the VAD, user and interruption frames reach `head` upstream. With
  `VADUserTurnStartStrategy(enable_interruptions=False)` (runs B, C, D) no `InterruptionFrame`.
- **(c) One request per user turn: confirmed** with `wait_for_transcript=False`. Run A: 1 request,
  file 0.38-6.22 s (5.84 s: both parts and the pause), answered in 306 ms. Run C (frag file looped,
  62.86 s): 7 requests, one per turn; twice Smart Turn scored the whole utterance 0.441 and the turn
  ended by the 3.0 s fallback (`pipecat/audio/turn/smart_turn/base_smart_turn.py:133`), adding about 3 s of trailing silence
  (request 3: 8.88 s). Run B (two complete clauses, 0.88 s gap): Smart Turn said COMPLETE at the pause
  (p=0.942), so 2 turns and 2 requests (2.58 s, 2.52 s); the turn itself ended, the bridge did not
  cut. Run D (`wait_for_transcript=True`): COMPLETE at 6.286, turn ended only by
  `on_user_turn_stop_timeout` at 11.191 (5.0 s, `pipecat/turns/user_turn_controller.py:154`), 1 request of 8.60 s.
  `UserStartedSpeakingFrame` arrives about 0.34 s after speech onset, so a 0.5 s pre-roll is needed.
- **(d) Clocks:** `time.monotonic`, `loop.time()` and `loop._clock_resolution` are `GetTickCount64()`
  at 0.015625 s (64 steps/s, ProactorEventLoop); `perf_counter` is QPC at 1e-07 s; `time.time` 0.015625 s.
  `asyncio.sleep(0.02)` median 30.9 ms (min 22.1, p99 35.8, max 41.1); `asyncio.sleep(0.001)` median
  15.4 ms; `time.sleep(0.02)` median 20.37 ms (max 23.7). Relative sleeps: 32.27 frames/s, +5484 ms
  drift in 10 s.
- **(d) Absolute deadlines** (`t0 + n*0.02` on `perf_counter`, one `asyncio.sleep(deadline - now)`):
  no pipeline, 60 s / 3000 frames: 49.9935 fps, end drift +7.8 ms, lateness median 8.3, p99 16.4,
  max 61.9, min -5.1 ms, 0.59 s CPU. In the pipeline, 62.84 s / 3143 frames: 50.015 fps, end drift
  -4.9 ms, lateness at `queue_frame` median -0.97, p99 19.1, max 28.0 ms, 1613 frames early (earliest
  -30.2 ms); at the STT bridge median 1.8, p99 48.9, max 150.4 ms, peaks at VAD stops.
  Hybrid (sleep to 16 ms before the deadline, then `asyncio.sleep(0)` until past): no pipeline
  50.0000 fps, drift +0.001 ms, p99 0.148, max 1.8 ms but 26.0 s CPU in 60 s; in the pipeline 50.000
  fps, drift +0.115 ms, queue p99 0.239, max 13.5 ms, 0 early; bridge p99 74.5, max 152 ms.
  Early wake-ups come from the stdlib: `loop.time()` is `time.monotonic()`
  (`stdlib: asyncio/base_events.py:745`) and a timer is due within one clock resolution (:1967).
- **(e) Models on CPU, no torch:** `import torch` fails (not installed; never in `sys.modules`);
  onnxruntime 1.31.1 device CPU, providers available `['AzureExecutionProvider', 'CPUExecutionProvider']`,
  both sessions got only CPU. Silero load 62-130 ms (83-92 rerun, 105-242 in pipelines), first
  `voice_confidence` (512 samples) 1.38 ms then median 0.263 ms, inline on the loop. Smart Turn load
  119-147 ms (101-157 in pipelines), `_predict_endpoint` first 150 ms then 95-163 ms (cpu_count=1),
  in-pipeline `e2e_processing_time_ms` 68.8-167.8, run in a thread pool (`pipecat/audio/turn/smart_turn/base_smart_turn.py:162`).
  `import onnxruntime` alone took 8.2-12.3 s per process (8.6 s self time on
  `onnxruntime.capi.onnxruntime_pybind11_state`); cause UNVERIFIED.
- Other spike observations: Smart Turn's inference is awaited inline at each VAD stop
  (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:232`), stalling audio downstream 100-163 ms; Pipecat's own
  timestamps step at 15.625 ms (`pipecat/clocks/system_clock.py:37` monotonic_ns, `pipecat/frames/frames.py:1581`,
  `:1596` time.time, `pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:239`); `STTSettings(model=None,
  language=None)` and `TTSSettings(model=None, voice=None, language=None)` clear the
  `pipecat/services/settings.py:251` ERROR; `TTSSpeakFrame.append_to_context` defaults True (`pipecat/frames/frames.py:1071`), so text
  frames holding spoken text flow downstream of the TTS.

**Exact API the pipeline spike used** (`pipeline_spike.py`):

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies, UserTurnStrategiesParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.services.stt_service import STTService
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.utils.time import time_now_iso8601
from pipecat.frames.frames import (
    EndFrame,
    InputAudioRawFrame,
    MetricsFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import TurnMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

vad = VADProcessor(
    vad_analyzer=SileroVADAnalyzer(
        params=VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6)
    )
)
turns = UserTurnProcessor(
    user_turn_strategies=UserTurnStrategies(
        start=[VADUserTurnStartStrategy(enable_interruptions=False)],
        stop=[
            TurnAnalyzerUserTurnStopStrategy(
                turn_analyzer=LocalSmartTurnAnalyzerV3(
                    params=SmartTurnParams(stop_secs=3.0, pre_speech_ms=500, max_duration_secs=8)
                ),
                wait_for_transcript=False,
            )
        ],
    ),
    user_turn_strategies_params=UserTurnStrategiesParams(),
)
pipeline = Pipeline([vad, turns, stt_bridge, echo, tts])
worker = PipelineWorker(
    pipeline,
    params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
    enable_rtvi=False,
    cancel_on_idle_timeout=False,
)
# @worker.event_handler("on_pipeline_started") -> feed only after it fires; "on_pipeline_finished"
runner = WorkerRunner(handle_sigint=False)
await runner.add_workers(worker)
await asyncio.gather(runner.run(), feeder())  # run(auto_end=True)
# feeder: await worker.queue_frame(InputAudioRawFrame(audio=<640 bytes>, sample_rate=16000,
#         num_channels=1)) at perf_counter deadlines t0 + n*0.02; then await worker.queue_frame(EndFrame())
```

- STT bridge: `class TurnSTTBridge(STTService)`, `super().__init__(audio_passthrough=True,
  ttfs_p99_latency=0.3, settings=STTSettings(model=None, language=None))`; overrides
  `process_audio_frame(frame, direction)` to buffer (0.5 s pre-roll ring, then the whole turn) and never
  call `run_stt` per frame; in `process_frame`, `await super().process_frame(frame, direction)`, then on
  a DOWNSTREAM `UserStartedSpeakingFrame` open, on `UserStoppedSpeakingFrame` close and
  `self.create_task(self.process_generator(self.run_stt(audio)), name=...)`; `run_stt` yields
  `TranscriptionFrame(text=..., user_id="", timestamp=time_now_iso8601(), finalized=True)`.
- Fake TTS: `class FakeTTS(TTSService)`, `super().__init__(push_start_frame=True, push_stop_frames=True,
  stop_frame_timeout_s=0.5, sample_rate=24000, settings=TTSSettings(model=None, voice=None,
  language=None))` (default aggregation, SENTENCE); `run_tts(text, context_id)` yields
  `TTSAudioRawFrame(audio=..., sample_rate=24000, num_channels=1, context_id=context_id)`; driven by a
  downstream `TTSSpeakFrame(text=...)`.
- Turn events used: `on_user_turn_started/stopped/resumed/inference_triggered/stop_timeout`; Smart
  Turn's result read from `MetricsFrame` with `TurnMetricsData(is_complete, probability,
  e2e_processing_time_ms)`.

#### WebRTC spike (`spike-webrtc\`)

- **(a) asyncio UDP on Windows: works, with stdlib flaws.** Default loop ProactorEventLoop; 200/200
  echoes on 127.0.0.1, RTT min 0.106 / median 0.115 / max 1.213 ms. Two or more datagrams to a closed
  port in one loop step: the endpoint gets WinError 10054 via `error_received` and never reads again,
  5/5 (sends spaced 5 ms: 0/5; SelectorEventLoop kept reading in every case)
  (`stdlib: asyncio/proactor_events.py:541`; `stdlib: asyncio/windows_events.py:477`). `transport.close()` never calls
  `connection_lost` while a datagram is in flight or buffered (`stdlib: asyncio/proactor_events.py:108`).
  uvicorn uses Proactor on win32 (`uvicorn/loops/asyncio.py:10`).
- **(b) Answer to a local aiortc peer with `iceServers=[]`: 5/5 connected.** Offer and answer 2
  m-lines, 4 host candidates on this machine's 2 private IPv4 addresses, `a=end-of-candidates` per
  m-line (aiortc adds it, `aiortc/rtcpeerconnection.py:157`). `handle_web_request` 14.0-18.4 ms;
  Pipecat `connected` 285/127/142/111/142 ms after the client pc was built (78-166 ms after the
  answer); first audio 50-60 ms later; 97-100 frames in 2 s, each `s16`, **stereo**, 48000 Hz, 960
  samples; tone peak 440.0 Hz; data-channel echo RTT median 0.76-2.03 ms over 20. Also connected on
  SelectorEventLoop (196, 111 ms). `connected` and `app-message` fire only after `conn.connect()`
  (`pipecat/transports/smallwebrtc/connection.py:680`).
- **(c) Trickle: connects, and the empty candidate reaches aioice** (`_remote_candidates_end` False ->
  True on that PATCH; `pipecat/transports/smallwebrtc/request_handler.py:259`). T2 (client blocked, only trickled candidates):
  connected 43 ms after the candidate PATCH on host->host. T1/T5: connects through a prflx candidate
  before any PATCH. T3: connects with no end-of-candidates. A second empty PATCH or a candidate after
  the end returns None, adds nothing (`aiortc/rtcicetransport.py:305`): Pipecat never answers 409.
  T4: candidates with `sdp_mid='1'` (bundled data m-line) dropped silently
  (`aiortc/rtcpeerconnection.py:422`); the call failed 0 ms after the end PATCH.
- **(c) Failure under aioice 0.11.0** (12 variants, candidates rewritten to a closed or silent port).
  Through the request handler (F1-F6), with the end in the SDP, by an empty PATCH at 1 s, or never:
  always ICE checking, then Pipecat's 60 s timeout closed the call 60.0 s after `connecting`
  (`server_ice_closed=60425ms`), event `closed` with no `failed`, WARNING "Timeout establishing the
  connection to the remote peer. Closing." (`pipecat/transports/smallwebrtc/connection.py:612`); no aioice "ICE failed". A direct
  `SmallWebRTCConnection(connection_timeout_secs=120)` (F10-F12): aioice "ICE failed" 63.6 s after
  checking began, end in SDP or via `add_ice_candidate(None)` at 1 s alike; order iceConnectionState
  failed, connectionState failed, Pipecat `failed`, WARNING "Connection failed, closing peer
  connection.", `closed`. 63.6 s = one STUN check's 7 sends at 0.5 s doubling (`aioice/stun.py:20`
  `RETRY_MAX = 6`, :21 `RETRY_RTO = 0.5`). No candidates + empty PATCH (F8): failed 33 ms after the
  PATCH; no candidates, no end (F9): only the 60 s close. The handler cannot change the timeout
  (`pipecat/transports/smallwebrtc/request_handler.py:207`).
- **(c) aioice 0.11.0 misbehaves (F7):** an offer with no candidates but `a=end-of-candidates` makes
  aioice drop component 1 before gathering (`aioice/ice.py:1101`), gather over no components (:551),
  answer with 0 candidates; aiortc never starts ICE (`aiortc/rtcpeerconnection.py:1077`); Pipecat's
  monitor starts only on `connecting` (`pipecat/transports/smallwebrtc/connection.py:672`). At 62 s and 75 s: server pc `new`, no
  Pipecat event, no warning, handler map size 1; the client failed at once. Whether aioice < 0.11
  differs, and whether a browser sends such an offer: UNVERIFIED.
- **(c) Sockets on Windows:** 8 calls with checks to closed ports: after WinError 10054, 2 of 32 and 4
  of 32 aioice sockets stopped reading (Proactor). Closes hung: 2, 3 and 3 of 16 still pending after
  4 s over 3 Proactor runs, one hung over 3 minutes, in `aioice/ice.py:293` `await self.__closed`
  under `aiortc/rtcpeerconnection.py:532` from Pipecat's `disconnect()`; each hung socket had a
  datagram buffered after WinError 1231, which appears on every call here (the pair across the 2
  adapters). SelectorEventLoop: 0 of 16 in each of 3 runs. uvicorn accepts a custom loop import string
  (`uvicorn/config.py:560`); a running uvicorn on Selector was not tested.
- **(d) `pc_id`:** d1 client-chosen unknown id ignored, server id returned, callback once. d2 same id
  again: renegotiated in place, INFO "Reusing existing connection" (`pipecat/transports/smallwebrtc/request_handler.py:200`), callback
  not rerun. d3 a DIFFERENT peer with a live id: answered, no check; live call kept audio (551 frames
  in 1 s); second peer stuck `connecting`. d4 `restart_pc=True`: original call closed, new pc under a
  NEW id, both keys -> same object; d4b the old id still accepts PATCHes. d5 unknown id PATCH:
  `HTTPException 404` (`pipecat/transports/smallwebrtc/request_handler.py:248`), no log. d5b malformed candidate: `AssertionError`
  (`aiortc/sdp.py:100`). d7 SINGLE: 400 "Cannot create new connection with existing connection active"
  or 400 "PC ID mismatch with existing connection", each WARNING + ERROR (`pipecat/transports/smallwebrtc/request_handler.py:142`,
  :239). d8 `type='answer'`: `InvalidStateError`. d9 `SmallWebRTCRequest.from_dict` with an extra key:
  `TypeError` (`pipecat/transports/smallwebrtc/request_handler.py:48`).
- **(e) Reserved data-channel names:** raw text starting `ping` (`ping`, `ping 123`, `pingpong`) is
  swallowed and sets `_last_received_time` (`pipecat/transports/smallwebrtc/connection.py:376`); JSON `{"type":"ping"}` is an ordinary
  app-message. After one raw ping, an app-message more than 3 s later is queued, not delivered
  (`pipecat/transports/smallwebrtc/connection.py:708`, :386), and stays queued when pings resume. `{"type":"signalling","message":
  {"type":"trackStatus",...}}` raises `track-status`, not app-message; any other inner type is dropped
  with an ERROR holding the raw message (`pipecat/transports/smallwebrtc/connection.py:380`, :389); `signalling` with no or empty
  `message` is an app-message. Non-JSON text, JSON without `type`, a JSON array: dropped with that ERROR.
  A bytes payload holding JSON is delivered. On `disconnect()` the client gets `peerLeft`
  (`pipecat/transports/smallwebrtc/connection.py:566`).

**Exact API the WebRTC spike used:**

```python
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequestHandler,
    SmallWebRTCRequest,
    SmallWebRTCPatchRequest,
    IceCandidate,
    ConnectionMode,
)
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

handler = SmallWebRTCRequestHandler()  # (ice_servers=None, esp32_mode=False, host=None,
#  connection_mode=ConnectionMode.MULTIPLE)
answer = await handler.handle_web_request(
    SmallWebRTCRequest(sdp=offer_sdp, type="offer", pc_id=None, restart_pc=None, request_data=None),
    callback,
)  # -> {"sdp": str, "type": "answer", "pc_id": "SmallWebRTCConnection#<n>-<uuid4hex>"}
# callback(conn) runs only for a NEW connection: register @conn.event_handler(name) for "connected",
# "connecting", "failed", "closed", "disconnected", "new", "app-message" (conn, message),
# "track-started", "track-ended", "track-status" (conn, receiver_index, enabled); then await conn.connect()
await handler.handle_patch_request(
    SmallWebRTCPatchRequest(
        pc_id=answer["pc_id"],
        candidates=[
            IceCandidate(
                candidate="candidate:<foundation> 1 udp <prio> <ip> <port> typ host",
                sdp_mid="0",
                sdp_mline_index=0,
            )
        ],
    )
)  # -> None; candidate="" is the end
await handler.close()
# conn.audio_input_track() -> SmallWebRTCTrack; await track.recv() -> av.AudioFrame (s16, stereo, 48000, 960)
# conn.send_app_message(dict); conn.is_connected(); await conn.disconnect();
# await conn.add_ice_candidate(None); conn.pc (aiortc RTCPeerConnection)
# Shorter connect timeout, bypassing the handler:
conn = SmallWebRTCConnection(ice_servers=None, connection_timeout_secs=120)
await conn.initialize(sdp=..., type="offer")
await conn.connect()
conn.get_answer()
```

- Client (aiortc 1.15.0): `RTCPeerConnection(RTCConfiguration(iceServers=[],
  bundlePolicy=RTCBundlePolicy.MAX_BUNDLE))`, `pc.addTrack(ToneTrack())` before
  `dc = pc.createDataChannel("chat")`; `ToneTrack(aiortc.mediastreams.MediaStreamTrack)`, `kind="audio"`,
  `recv()` returns `av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")`,
  `sample_rate=48000`, `pts=n*960`, `time_base=Fraction(1, 48000)`, paced on `perf_counter`;
  `await pc.setLocalDescription(await pc.createOffer())`, offer = `pc.localDescription.sdp`;
  `await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))`;
  `dc.on("open")`, `dc.on("message")`, `dc.send(str)`.
- Loop: `asyncio.run(main())` (Proactor); `asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)`.
- Probe internals only (not API): `conn.pc.getTransceivers()[0].receiver.transport.transport._connection`
  is the `aioice.Connection` (`_remote_candidates_end`, `_remote_candidates`, `_check_list`,
  `_nominated`, `_protocols[i].transport._read_fut`).

---

### Changes to the plan's interfaces

Each item contradicts or sharpens the text of steps 4 to 10 (and the criteria and tracks that rest on
them). Owner-level items are repeated under "For the owner".

1. **Runner names stand**: `PipelineWorker`, `WorkerRunner`, `await runner.add_workers(...)` (spike a).
   Track E must also pass `PipelineWorker(..., enable_rtvi=False)`, turn Pipecat's idle cancel off
   (`idle_timeout_secs=None` or `cancel_runner_on_idle_timeout=False`; `limits.idle_s` is the
   library's), and register `on_pipeline_error` or set `processor_unusable_policy`; build
   `WorkerRunner(handle_sigint=False)` inside the running loop; `run(auto_end=False)` if calls share a
   runner. Never `PipelineTask`, `PipelineRunner` or `run(worker)`.
2. **"Pipecat's interruptions are off"** means: start list exactly
   `[VADUserTurnStartStrategy(enable_interruptions=False)]` (no `TranscriptionUserTurnStartStrategy`),
   `enable_rtvi=False` (RTVI's `send-text` interrupts and injects input), no `DTMFAggregator`.
   `PipelineParams` has no `allow_interruptions`; nothing named `StartInterruptionFrame` exists.
3. **One request per user turn works** (spike c): the decision entry of step 12 says "per user turn".
   The STT bridge subclasses `STTService` (not `SegmentedSTTService`, which the design's 13 still names)
   and sits after `UserTurnProcessor`: `transport.input -> VADProcessor -> UserTurnProcessor -> STT
   bridge -> session bridge -> TTS bridge -> transport.output`. `TurnAnalyzerUserTurnStopStrategy` gets
   `wait_for_transcript=False` explicitly, else the turn ends only at the 5 s stop timeout (run D).
4. **The STT bridge's contract** (Track E): pre-roll of at least 0.5 s; open on the downstream
   `UserStartedSpeakingFrame`, close on `UserStoppedSpeakingFrame`; trim at the last VAD stop plus
   padding (a fallback turn otherwise carries about 3 s of silence, billed); its own maximum turn
   length (Pipecat caps none); check `self._muted`; Whisper on its own task; exactly one result per
   turn, empty, failed and unusable included, stamped with the bridge's turn number,
   `finalized=True` and `interruptible=False` (set after construction); when the call ends
   (`voice/session/io.py`'s end: an `Ending`, a `TransportFailure` or the session's `HangUp`;
   D-037), drop held audio and cancel a request in flight, never flush, and hand a `Transcribing` as
   each request goes; `STTSettings(model=None, language=None)` and `ttfs_p99_latency` set.
5. **Registration effect:** whether a paused request is one request is Smart Turn's verdict at the
   pause, not the bridge's: in run B a complete-sounding first clause and a 0.88 s pause gave 2 turns
   and 2 requests. The paused items' request counts should be bounded with that in mind.
6. **`voice/session/io.py`:** turns are keyed on the frames, never on `UserTurnProcessor`'s events
   (unordered tasks). A turn ID is needed on turn start, turn end and transcript: the next turn's start
   can reach the session before the previous turn's transcript. Track D adds that ordering to its
   "turn end before transcript" test. Turn times come from the processors' own `perf_counter` stamps,
   not from Pipecat's `timestamp` fields (time.time, 15.625 ms).
7. **Stop path (design 13, verified):** the session bridge (upstream of the TTS) calls
   `self.broadcast_interruption()`; every processor drops queued interruptible frames, `TTSService`
   drops its contexts, `MediaSender` resets its audio queue. A stopper downstream of the TTS pushes
   `InterruptionWorkerFrame`. Up to 40 ms already in `RawAudioTrack`, plus RTP in flight and the
   browser's jitter buffer, still plays: "no audio frame of a dropped reply is sent" holds at the
   output transport (the capture test), not on the wire.
8. **Outbound `t2v/1` messages** (`hello`, `state`, `caption`, `notice`) go as
   `OutputTransportMessageUrgentFrame`, or with `interruptible=False` set on the instance; a plain
   `OutputTransportMessageFrame` waits behind audio and a Stop drops it.
9. **TTS bridge in `TextAggregationMode.TOKEN`** stands only if the session pushes whole clauses (one
   text frame or `TTSSpeakFrame` per clause from Track A's splitter): TOKEN calls `run_tts` once per
   incoming text. Pass `push_start_frame=True`, `push_stop_frames=True`,
   `TTSSettings(model=None, voice=None, language=None)`; `TTSSpeakFrame.append_to_context` defaults True
   and spoken-text frames flow to the output side. The fake TTS in `fakes.py` yields audio or passes
   `max_consecutive_zero_audio_contexts=0`. TOKEN with `TTSSpeakFrame` was not run (UNVERIFIED).
10. **`pc_id` and the router** (`voice/calls.py`, Track F): Pipecat's handler cannot give the plan's
    answers: a holder of a `pc_id` renegotiates a live call (d3), `restart_pc=True` closes it and leaves
    a stale key (d4), SINGLE mode answers 400 with an ERROR log, a PATCH after the end returns None (no
    409), a malformed candidate is a 500, `type='answer'` raises. So `voice` keeps the `pc_id` behind
    the call ID, always passes `pc_id=None`, `restart_pc=None` and `type="offer"`; `api` itself answers
    409 to a second offer and to a late PATCH, maps the handler's 404, and parses each candidate before
    Pipecat. The `pc_id` holds `#`: never in a URL. The handler swallows callback exceptions, so `voice`
    checks the worker started. Option: build `SmallWebRTCConnection` directly
    (`initialize`/`connect`/`get_answer`/`add_ice_candidate`), which owns the timeout and the map.
11. **Decision-log entry on the end-of-candidates PATCH (aioice 0.11.0):** the PATCH does reach aioice,
    but a call whose candidates are unreachable reports at about 60 s either way (Pipecat's timeout,
    event `closed`, no `failed`), because aioice's check gives up at about 63.6 s; the PATCH speeds
    failure only when no pair is pending (F8: 33 ms). The handler cannot shorten the 60 s. The client
    still sends the PATCH; the entry's reason changes, and a faster failure needs `voice`'s own
    deadline or a direct `SmallWebRTCConnection(connection_timeout_secs=...)`.
12. **`TransportFailed`** comes from connection events (`failed`, and `closed` via
    `on_client_disconnected`), not from error frames: ICE failure pushes no `ErrorFrame`. A path dropped
    after connect fails in about 30 s (consent checks). `voice` also needs its own offer-to-connected
    deadline for the F7 hang (item 21).
13. **`voice/protocol.py`:** every data-channel message is a JSON object with a `"type"` key (Pipecat
    drops anything else and logs it whole at ERROR), `type` never `signalling`; the client never sends
    raw text starting with `ping` (else app messages queue and bot audio stops after 3 s). Inbound comes
    through the transport event `on_app_message` (not `on_client_message`) or
    `InputTransportMessageFrame`; the client ignores `{"type":"signalling"}` (`peerLeft` at hang-up).
14. **Client PATCH body:** snake_case `sdp_mid` and `sdp_mline_index`, both required, `candidate: ""`
    for the end; add the audio track before the data channel so the first bundled m-line is mid `"0"`;
    a candidate on a bundled non-first mid is dropped silently (T4 failed).
15. **Input audio:** the server's aiortc track yields stereo s16 48 kHz frames of 960 samples; the
    transport resamples to `audio_in_sample_rate`, which must be 16000 (Silero takes only 16000 or
    8000). The recorder's input tap is taken after the transport. `TransportParams` needs
    `audio_in_enabled=True` and `audio_out_enabled=True` explicitly.
16. **Logging (step 8, Q2):** `logger.disable("pipecat")` must run before the first import of any
    `pipecat.*` module, transitive ones included. `logging.pipecat = "forward"` cannot work with "no
    sink is added or removed" (owner item). Forwarded records must carry no message text
    (content-bearing WARNING/ERROR lines: `pipecat/services/tts_service.py:1982`, `pipecat/transports/smallwebrtc/connection.py:389`,
    `pipecat/processors/frameworks/rtvi/processor.py:293`, `pipecat/pipeline/worker.py:1648`, `pipecat/processors/frame_processor.py:1032`/`:1346`, `pipecat/utils/base_object.py:288`,
    `pipecat/transports/smallwebrtc/request_handler.py:222`). The library's stdlib set-up keeps `aiortc` and `aioice` at WARNING or
    above with no handler (aioice INFO holds IPs, aiortc DEBUG holds SDP).
17. **`tests/conftest.py` (step 6)**, popped at module top before any import: `PIPECAT_SCTP_MAX_CHUNK_SIZE`,
    `PIPECAT_SMART_TURN_LOG_DATA`, `PIPECAT_SETUP_FILES`, `PIPECAT_LOG_LLM_CONTEXT`,
    `PIPECAT_ALLOWED_ORIGINS`, `PIPECAT_ALLOWED_FILE_URL_NETWORKS`, `LOGURU_*`, `WEBSOCKETS_*`,
    `FORWARDED_ALLOW_IPS`, `WEB_CONCURRENCY`, `UVICORN_*`, `FASTAPI_OTEL_AUTO_CONFIGURE`, `FASTAPI_ENV`,
    `OTEL_*` (exporters, endpoints, protocols, `SDK_DISABLED`, `PROPAGATORS`, `RESOURCE_ATTRIBUTES`,
    `SERVICE_NAME`, `PYTHON_TRACER_PROVIDER`, `PYTHON_CONTEXT`, `INSTRUMENTATION_HTTP_KNOWN_METHODS`),
    `ORT_LOAD_CONFIG_FROM_MODEL`, `NUMBA_*`, `LLVMLITE_*`, `OPENAI_*`, `GROQ_*`; optionally
    `PYTHON_DOTENV_DISABLED=1` (guards `load_dotenv` only). `voice` refuses `PIPECAT_SETUP_FILES` and
    `PIPECAT_SMART_TURN_LOG_DATA` at start. The aiortc fixture monkeypatches
    `RTCIceGatherer.getDefaultIceServers` with a raising classmethod.
18. **ARCH-BAN (step 6) gains:** `pipecat.runner` (`load_dotenv(override=True)`, `logger.remove()`),
    `pipecat.cli`, `pipecat.evals`, `pipecat.bus`, `pipecat.audio.turn.smart_turn.local_smart_turn_v2`
    (torch), `pipecat.audio.resamplers.resampy_resampler` (numba), `pipecat.processors.logger`,
    `pipecat.observers.loggers`, `pipecat.processors.aggregators.dtmf_aggregator`; and a harness test
    that `pipecat.runner.run` is not in `sys.modules` after importing `voice`.
19. **Settings and serving (steps 7 and 10) for hosting on this machine:** with no proxy, uvicorn's
    defaults (`proxy_headers=True`, trusting `127.0.0.1,::1`) let every local client forge its address,
    into the access log too: `serve()` and the Ole5 server run with `proxy_headers=False` until a proxy
    exists, `server.forwarded_allow_ips` empty by default (`*` refused). `uvicorn.run` gets
    `workers=1`, `access_log=False`, `server_header=False`, no `env_file`; the app gets
    `FastAPI(telemetry={'tracing': False, 'metrics': False, 'logs': False, 'auto_configure': False})`.
    Tokens and secrets never in a query string (logged and traced).
20. **Event loop on Windows (owner item):** on Proactor, aioice sockets go deaf after WinError 10054 and
    2-3 of 16 call closes hang; Selector had 0 of 16. `serve()`, `t2v dev` and the Ole5 server should
    run uvicorn on a Selector loop on Windows (UNVERIFIED in a running server), and every
    `disconnect()`/`pc.close()` is bounded by a timeout so a hung close cannot leak the call.
21. **F7 guard:** an offer with `a=end-of-candidates` and no usable candidate hangs the server pc in
    `new` with no event; `voice` refuses such an offer or closes any call not `connected` within its own
    deadline.
22. **Media is not on loopback:** aioice never offers 127.0.0.1 (`aioice/ice.py:88`); a browser and the
    server on this machine connect over its private LAN addresses, so `t2v dev` binding HTTP to
    127.0.0.1 still opens UDP sockets on the LAN addresses. Browser `.local` candidates trigger mDNS
    multicast on the LAN.
23. **File-fed transport (Track E, step 10):** absolute `perf_counter` deadlines with one
    `asyncio.sleep` hold 60 s within the 100 ms tolerance (end drift -4.9 ms) but send frames up to 30 ms
    early and p99 19 ms late; the hybrid pacer is exact at about 43% of a core. Smart Turn stalls audio
    100-163 ms at each VAD stop, which Track H's timings must allow for.
24. **Warm-up and imports:** `import onnxruntime` costs 8.2-12.3 s per process; the lifespan warm-up
    builds `SileroVADAnalyzer` and `LocalSmartTurnAnalyzerV3` (each loads its model in `__init__`), and
    `import t2_agentic_voice` and `t2v --help` import neither (GP-17), or each child-process test pays
    about 10 s.
25. **Track C (PyJWT):** one module-level `jwt.PyJWT(options={'enforce_minimum_key_length': True})` for
    encode and decode; `algorithm='HS256'` explicit, never `None`, no caller data in `headers`; decode
    with `algorithms=['HS256']`, `require=['exp', 'iat', 'jti', ...]`, small `leeway`, `audience`/`issuer`
    if used, `verify_signature` never passed False; catch `PyJWTError` (`InvalidKeyError` is not an
    `InvalidTokenError`).
26. **Track A (num2words):** cardinals only through num2words; Arabic ordinals outside 1-19 and every
    decimal handled by the library itself; calls on one thread.

### Unresolved

- Env reads in native code (onnxruntime's C++ core, FFmpeg in PyAV, LLVM in llvmlite): UNVERIFIED.
- httpx's proxy and TLS variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`,
  `SSL_CERT_FILE`, `SSL_CERT_DIR`) under `trust_env`: not read (TD-004).
- Whether the library's own groq clients override `GROQ_CUSTOM_HEADERS` (`groq/_client.py:306`) when
  they pass headers explicitly: UNVERIFIED; Track B's "GROQ_* change nothing" test must cover it.
- OpenTelemetry exporter variables (headers, timeouts, certificates) beyond those cited: not read.
  Whether `Resource(...)` built directly reads any variable: UNVERIFIED.
- Whether the project's Phoenix/OTel set-up installs global tracer, meter or logger providers, and
  whether any installed span processor copies inbound baggage onto spans: not in scope.
- Whether a `.env` sits at the worktree or main checkout root: not checked (reading `.env` is forbidden).
- Whether each `WEBSOCKETS_*` has a per-call override, and whether uvicorn's websockets protocol sends
  `WEBSOCKETS_SERVER` as its Server header: UNVERIFIED.
- Lazily imported modules (`pipecat/services/llm_service.py:521`, `pipecat/transports/smallwebrtc/request_handler.py:231`) checked by reading only.
- Whether aiortc's SDP-candidate path always goes through aioice's mDNS resolution, and whether
  aioice resolves a browser's `.local` candidates on Windows: UNVERIFIED (mDNS was not run; it leaves
  the machine).
- Whether pydantic's `ValidationError` text includes the input value (logged at `pipecat/processors/frameworks/rtvi/processor.py:302`,
  :385; `pipecat/transports/smallwebrtc/connection.py:389`, :839): UNVERIFIED.
- Whether aiortc's `setRemoteDescription` errors quote SDP fragments (logged at
  `pipecat/transports/smallwebrtc/request_handler.py:239`): UNVERIFIED.
- Whether `SmallWebRTCTransport`'s input resampler also downmixes stereo to mono: the spike read the raw
  track only; UNVERIFIED.
- TOKEN aggregation with `TTSSpeakFrame` (one `run_tts` per frame): the spike used SENTENCE; UNVERIFIED.
- Whether an in-flight HTTP `run_tts` is cancelled at once by an `InterruptionFrame` (how the client's
  streamed response closes on cancel): not traced.
- How much audio plays after a Stop beyond the 40 ms in `RawAudioTrack` (RTP, jitter buffer): needs a
  browser measurement.
- `STTService`'s TTFB metrics with one request per turn (started at each VAD stop,
  `pipecat/services/stt_service.py:644`, 2 s `stt_ttfb_timeout`): UNVERIFIED; the plan's timings should not rely on it.
- Whether a `TranscriptionFrame` with empty text is mishandled by a Pipecat processor downstream: only
  relevant if one is added later.
- Smart Turn v3.2 on Saudi Arabic and MSA; why the same utterance scored 0.441 and 0.568 on different
  repetitions (its buffer is time-stamped with `time.monotonic()`, `pipecat/audio/turn/smart_turn/base_smart_turn.py:118`): UNVERIFIED.
- Why `import onnxruntime` takes 8.2-12.3 s (a socket watch saw none in 4 polls; native code is invisible
  to the audit hook): UNVERIFIED.
- A thread-based feeder with `time.sleep(0.02)` (median 20.37 ms) as a cheaper exact pacer: UNVERIFIED.
- uvicorn on a Selector loop through `loop=` in a running server: UNVERIFIED.
- Whether a call connects on this machine with no network adapter up (no loopback candidates):
  UNVERIFIED, not tested (it would change system settings).
- aioice below 0.11 on the F7 offer, and whether a browser can send such an offer (a plausible trigger:
  only unresolvable `.local` candidates): UNVERIFIED.
- Windows effect of the colons in Smart Turn's WAV log names: UNVERIFIED.
- An `APIRouter` using `on_startup` included into an app without its own lifespan: whether handlers run
  twice beyond the double-include case: UNVERIFIED.
- Arabic num2words quality and gender agreement for TTS (needs a native speaker); thread safety inferred
  from source only.
- A child process with piped stderr encodes as cp1256 here; loguru wrote the banner's characters as
  `\u` escapes (observed): tests decoding the child's stderr must allow for it.

### For the owner

- **aioice 0.11.0 hang (Q1's aioice clause):** an offer with no candidates but `a=end-of-candidates`
  leaves the server peer in `new` with no event or timeout (`aioice/ice.py:1101`; seen for 75 s).
  Whether aioice < 0.11 behaves better is UNVERIFIED, so the agent's view is no constraint and a guard in
  `voice` (item 21); the owner may still ask for the `aioice<0.11` constraint Q1 allowed.
- **Q2's "no sink is added or removed" vs `logging.pipecat = "forward"`:** a disabled `pipecat`
  namespace reaches no sink (`loguru/_logger.py:1995`), so "forward" must enable it and add a forwarding
  sink, and then loguru's default stderr sink prints every Pipecat DEBUG line (transcripts, spoken
  text) unless the app removes it. "off", the default, is unaffected. Needs a re-decision on forward.
- **Windows hosting:** with all hosting on this machine, uvicorn's default Windows loop (Proactor)
  lets aioice sockets go deaf and 2-3 of 16 call closes hang (`stdlib: asyncio/proactor_events.py:541`,
  :108); proposal: run on a Selector loop on Windows and bound every close.
- No licence item: licences were not the subject of these reads and spikes, and none came up.
