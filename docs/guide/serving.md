# Serving: the sidecar or the mount, and who may call

How a runtime serves calls (D-029): in a process of its own, the sidecar, or mounted in your own
FastAPI app; how it knows who is calling, through signed join tokens; and what crosses the wire,
the protocol `t2v/1`; and which agent a served app runs, the talker or the echo. The deployment
(a server, a reverse proxy, TURN, drain) is not built yet: it has a plan of its own once a server
is available.

## Two shapes, one worker each

A call's peer connection and session live in one process's memory, and the store of used join
tokens is a SQLite file in the data folder, so **one process with one worker serves one data
folder** (`storage.var_dir`). The runtime's lifespan locks the folder (`runtime.lock`); a second
process on it stops at its start, with a FIX line.

- **The sidecar**, the default for any service with more than one worker or replica: a process
  that runs only the runtime and imports your agent and your backend clients; your app, with
  any number of workers, mints the join tokens with the key the two share. Run it with
  `serve(make_runtime)` from `t2_agentic_voice.server`, or with the command below.
- **The mount**, for an app that runs one worker on one instance: your FastAPI app includes the
  runtime's router, `app.include_router(runtime.router(), prefix="/voice")`, which carries the
  runtime's lifespan (FastAPI merges it). An app that mounts the router's app as a
  sub-application combines the lifespans itself with `combine_lifespans` (from `server`).

**Each turn's language at start.** Under `stt.live_language = "classified"`, the runtime
builds the classifier `stt.classifier` names (`Providers.from_settings`) and loads it at its
start, off the event loop, once a process, with the agent's languages, before any call: it
refuses to start, with a FIX, when `stt.classifier_dir` is unset, a model file is missing or
changed, or `ecapa` runs without the library's `ecapa` extra. ECAPA's load takes seconds and
its model stays in the process's memory. One classification runs at a time in a process, so
the calls of one runtime share it (TD-145). [languages.md](languages.md) says how to fetch
the files.

### The sidecar

```bash
uv run t2v serve your_package.voice:make_runtime --host 127.0.0.1 --port 7860 --prefix /voice
```

`t2v serve APP` imports `APP` (`module:function`, a function that returns a `VoiceRuntime`),
sets up logging from its settings ([tracing-and-logs.md](tracing-and-logs.md)), and runs
`serve()`, which builds its own app: FastAPI's telemetry off and no docs pages; CORS for
`server.allowed_origins` alone; uvicorn with one worker, no access log, no server header, no
logging configuration of its own, and proxy headers trusted only from
`server.forwarded_allow_ips` (none by default), on a selector event loop. It binds 127.0.0.1
unless `--host` says otherwise. `examples/minimal` starts itself the same way, in
[\_\_main\_\_.py](../../examples/minimal/src/minimal_example/__main__.py):

```python
    serve(partial(make_runtime, settings))
```

Both refuse `env` test, and a runtime with no identity source, with a FIX line. `t2v dev`
serves `env` dev only, on 127.0.0.1, with the dev page, and gives a runtime with no identity
source the dev caller.

### The mount

A mounted router cannot reach your app's object, so your app does three things `serve()` does
for its own. The Ole5 app's server does each, in
[server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py):

```python
TELEMETRY_OFF: Final[TelemetryConfig] = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "auto_configure": False,
}
```

1. **Turn FastAPI's telemetry off.** FastAPI 0.162.0 traces, measures and logs every request
   through OpenTelemetry's global providers unless the app is built with `telemetry` off, as
   above; the library instruments no other library (D-023).
2. **Set CORS on your app**, for the pages of other origins that call the runtime, with `POST`
   and `PATCH`, and the headers `content-type` and `X-T2V-Offer-Secret`. In the mount the
   router does not answer CORS, and `server.allowed_origins` applies under `serve()` alone; the
   runtime logs `router_mounted` at its start to say so. From
   [server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py)'s `build_app`:

   ```python
       app = FastAPI(telemetry=TELEMETRY_OFF, openapi_url=None)
       app.add_middleware(
           CORSMiddleware,
           allow_origins=list(settings.voice.server.allowed_origins),
           allow_methods=["POST", "PATCH"],
           allow_headers=["content-type", OFFER_SECRET_HEADER],
       )
       customer = settings.app.demo_customer_email
       guard = AccessCodeGuard(clock=clock, tokens_per_day=TOKENS_PER_DAY)
       app.include_router(
           access_code_router(
               settings.app.access_code, minter, caller=lambda: demo_caller(customer), guard=guard
           )
       )
       if tickets is not None:
           app.include_router(tickets_router(tickets, headers=page_headers(None)))
       app.include_router(router, prefix=VOICE_PREFIX)
   ```

3. **Trust proxy headers from your proxy only.** uvicorn's defaults trust `X-Forwarded-For`
   from 127.0.0.1 and ::1, so any local client could set its own address. Pass
   `forwarded_allow_ips` yourself, with `proxy_headers` off when it is empty, and one worker,
   as [server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py)'s `server_config` does:

   ```python
       trusted = list(voice.server.forwarded_allow_ips)
       return uvicorn.Config(
           app,
           host=host,
           port=port,
           workers=1,
           proxy_headers=bool(trusted),
           forwarded_allow_ips=trusted,
           access_log=False,
           server_header=False,
           log_config=None,
           env_file=None,
           loop=SELECTOR_LOOP,
           lifespan="on",
       )
   ```

   `SELECTOR_LOOP` is `"asyncio:SelectorEventLoop"`: on Windows' default event loop, the
   WebRTC stack's sockets stopped receiving and some call closes hung.

## Who is calling: one identity source

A runtime takes exactly one identity source, `identity=`, from the `identity` facade. It gives
each call its `Caller` and `Consent` once, at join, and nothing said or sent in the call changes
either.

- **`SignedJoinTokens`** verifies the join tokens your website or app mints for its signed-in
  users. Build it from the `join` settings, as the Ole5 app's `make_app` does in
  [server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py), and pass it to the runtime
  as `identity=` ("Which agent a served app runs", below):

  ```python
      voice = settings.voice
      tokens = SignedJoinTokens.from_settings(voice.join, prefix=voice.prefix)
  ```

- **`DevIdentity()`** is the dev caller (`Caller(subject="dev")`, consent to nothing): it joins
  only a server whose `env` is `dev`, and only from a loopback address. A dev call is never
  recorded.

A verifier of your own, written to the `IdentityVerifier` port (the `ports` facade), works too,
but the consent it returns never lets a call be recorded: only a verified signed token's can. A
runtime with no identity source is refused at serving, with a FIX line; `t2v dev` alone falls
back to `DevIdentity`. A sign-in the runtime runs itself (`Authenticate`) is not built.

### Join tokens

A join token is a compact JWT, signed with HS256 and nothing else, read by the runtime once, at
`POST /join`. It is signed, not encrypted: the caller can read every claim, so none holds a
secret.

| Part | What it holds |
| --- | --- |
| header `kid` | The ID of the key that signed it, one of `join.keys` |
| `sub` | Required: the caller's stable ID in your system (`Caller.subject`), printable text of at most 256 characters |
| `name` | Optional: how the caller is named (`display_name`) |
| `locale` | Optional: a BCP 47 tag, such as `ar-SA`; it picks the call's language when the page sends none |
| `attrs` | Optional: at most 16 short names to texts (a department, a role) |
| `consent` | Required: `{"version": <text or null>, "record_audio": <true or false>}`, what the caller chose on your consent screen, with both keys and no other; `version` 1 to 64 printable ASCII characters with no space, and `record_audio` a JSON boolean |
| `jti` | Required: an ID used once, 1 to 128 printable ASCII characters with no space |
| `iat`, `exp` | Required: whole seconds since 1970; `exp` minus `iat` at most `join.ttl_s` |

No other claim is taken (`nbf`, `aud` and `iss` are refused), each key holds at least 32 bytes,
and a token is used once: the used-token store refuses its `jti` again. Its times may be off
the runtime's clock by `join.max_clock_skew_s` (30 s by default, 60 s at most), and
`t2v doctor` measures the runtime's machine's clock against Groq's; it lives
`join.ttl_s` (60 s by default, 120 s at most), so mint it just before the call starts. With
`privacy.consent_version` set, `/join` refuses a token whose consent names another version.

The keys are settings: `T2V_JOIN__KEYS`, a JSON object from key ID to secret (or
`T2V_JOIN__KEYS_FILE`, a file holding it), and `T2V_JOIN__CURRENT_KID`, the key that signs. Make
a secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Any listed key
verifies, so a new key can be added before it signs.

**Minting.** In Python, `SignedJoinTokens.mint(caller, consent=...)` mints one with the key
`current_kid` names; any JWT library that writes the claims above works as well.

**A demo page's access code.** For a page of your own app that has no sign-in yet (a demo, a
tester day), the `server` facade gives the token route the Ole5 app uses:
`access_code_router(access_code, minter, caller=..., guard=...)` serves `POST /token`, which
mints a token with `minter` (your `SignedJoinTokens`) for a page that sends
`{"code": "<access code>", "consent": {"version": ..., "record_audio": ...}}`. The token's
caller is the one your `caller` function builds, never one the request names; its consent is
the one the page's box sent. The body is JSON alone, at most 1 KiB, parsed strictly. Its
`AccessCodeGuard` compares the code in constant time, slows an address after each wrong code (1
s, doubling, at most 60 s), closes the route until a restart at the hour's `wrong_per_hour`-th
wrong code (20 by default), and mints at most `tokens_per_day` tokens a day (10 by default);
each count lives in the process. `page_headers(website_origin)` gives the headers for the
page's own files: a Content-Security-Policy with no inline script or style and `frame-ancestors`
only `website_origin` (`'none'` when it is `None`), `nosniff`, no referrer, and the microphone
for the page's origin alone. The Ole5 app's
[server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py) builds both, as in step 2
above, its caller the owner as the demo customer the settings name
(`OLE5_VOICE_DEMO_CUSTOMER_EMAIL`), at 10 tokens a day.

## The routes

Under the prefix (`/voice` above), the runtime serves:

| Route | What it does |
| --- | --- |
| `POST /join` | A join token, the client's protocol version and the language picked, if any, in; the call's ID, its offer secret, the ICE servers and the protocol version out. |
| `POST /offer` | The call's SDP offer, with its offer secret; the SDP answer out. One offer a call. |
| `PATCH /offer` | The browser's ICE candidates, with the offer secret; an empty one marks their end. |
| `GET /health` | The environment and the calls held live. |
| `GET /ready` | 200 once the runtime has started. |
| `GET /client/1/t2v-client.js` | The reference browser client ([browser-client.md](browser-client.md)). |
| `GET /dev` | The dev page: `env` dev, with the dev page on (`t2v dev`, or `server.dev_page`), to loopback clients only; any other client gets a plain 404. |
| `GET /dev/console` | The test console, with `dev/feed`, `dev/setup` and its script and style: mounted with the dev page, answering only a loopback client that names a loopback host ([browser-client.md](browser-client.md), "The test console"). |
| `GET /dev/stt` · `POST /dev/stt` | The test console's choice of a call's speech-to-text: the menu of the providers this server has a key for, with their models and the language modes, never a key; then one joined call's `{"call_id", "offer_secret", "provider", "model", "live_language"}` before its offer, 204, or 400 for a choice not on the menu. Under the console's guard alone ([browser-client.md](browser-client.md), "Trying speech-to-text providers in the dev console"). |
| `POST /dev/token` | The test console's join token: `{"record_audio": false}` in, `{"token": ...}` out, a signed token for the dev caller the app declares (`server.dev_caller`), never one the request names. Under the console's guard alone; a plain 404 when no dev caller is declared or no join key signs. |

- Every body is JSON, sent as `application/json` (anything else gets 415), under a size cap
  (413).
- The offer secret is random, for one call, and goes in the `X-T2V-Offer-Secret` header or the
  body's `offer_secret`, never in a URL. It stops working when ICE completes or the call ends.
- Every refusal answers one body, `{"code", "message", "notice", "reference"}`: a code from a
  closed list (`join_rejected`, `forbidden`, `protocol_mismatch` and the rest), a message safe to
  show, and a reference the server logs. A `PATCH` that comes once the call has moved on gets a
  quiet 409 (`not_offered`, `ice_completed`, `call_ended`), which the client ignores.
- Until the lifespan has run, every route answers 503 `not_started`.
- `/join` answers `server.ice_servers`, each TURN server with the call's own credentials when
  `server.turn_secret` is set (coturn's `use-auth-secret`: the user name the expiry and the
  call's ID, the password its HMAC-SHA1 under the secret; D-128), so a browser on any network
  reaches the backend through the relay, over TLS on 443 with a `turns:` URL; with no TURN
  server, a call needs a direct UDP path between the browser and the backend.

## Which agent a served app runs

A runtime runs the agent it is given. An agent that declares instructions runs the talker, the
chat model answering with the agent's tools; one that declares none runs the echo
([concepts.md](concepts.md)); `session.mode` overrides that, `echo` for any agent and `talker`
for one with instructions. The runtime builds the chat model as it starts, from the `llm`
settings, beside the speech providers, and keeps its connection open between requests
([latency.md](latency.md)). A model of your own, written to the `ChatModel` port (the `ports`
facade), is passed in code: `VoiceRuntime(agent, ..., providers=Providers.from_settings(settings).replace(chat=model))`.

The Ole5 app chooses at its start. With the knowledge base's access set (`QDRANT_URL`,
`QDRANT_LOGIN_EMAIL` and `QDRANT_LOGIN_PASSWORD`) it runs Ole5's talker, which searches that
knowledge base and acts on the mock ticket system (its four ticket tools, `tickets/tools.py`);
with none of them set, the echo; with only some, it refuses to start, naming the rest. One log line says which agent runs. Its `make_app`, in
[server.py](../../apps/ole5-voice-agent/src/ole5_voice/server.py):

```python
    access = knowledge_access(settings.app)
    voice = settings.voice
    tokens = SignedJoinTokens.from_settings(voice.join, prefix=voice.prefix)
    tickets = MockTicketSystem(
        tickets_folder(settings),
        mode=settings.app.tickets_mode,
        lookup=settings.app.tickets_lookup,
    )
    if access is None:
        log.info("knowledge_base_not_set", agent="echo", fix=f"set {', '.join(ACCESS)}")
        runtime = VoiceRuntime(ECHO_AGENT, settings=voice, identity=tokens)
        return build_app(settings, router=runtime.router(), minter=tokens, tickets=tickets)
    kb = QdrantKnowledgeBase(access)
    talker = talker_agent(kb, tickets=tickets)
    runtime = VoiceRuntime(talker, settings=with_ticket_claims(voice), identity=tokens)
    log.info("knowledge_base_set", agent="talker")
    return build_app(
        settings,
        router=runtime.router(),
        minter=tokens,
        tickets=tickets,
        closing=(kb,),
        warming=(kb.warm_up,),
    )
```

- **The knowledge base** is the app's own adapter behind the library's `KnowledgeBase` port,
  and `talker_agent` makes the agent's search tool of it with the library's `knowledge_tool`
  ([concepts.md](concepts.md), "Knowledge").
- **Its client is the app's to close.** The runtime closes what it built (the providers, the
  chat model among them) as its lifespan ends; the knowledge base's client, which the app
  opened, `build_app` closes after it (`closing`), and signs in once the runtime has started
  (`warming`), so the first caller's search does not have to.
- **The log line names no value**: the agent it runs and, for the echo, the settings to set.
- **The mock ticket system** is built from the settings with no IO; the talker's actions and
  the page at `/tickets` (loopback clients only) share that one instance, so the page shows
  what the calls made.
- **The talker's settings** are the loaded ones with Ole5's phrases for a ticket's number
  added to `guard.claims` (`with_ticket_claims`, `tickets/tools.py`), so a number said as the
  caller's ticket number is a claim ([safety.md](safety.md)); the echo, with no action, runs
  on the settings as loaded.

## Pages on another origin

A page served from another origin than the runtime lists that origin, scheme, host and port, in
`server.allowed_origins` under `serve()`, or in your own CORS middleware in the mount. The page
itself is HTTPS, or on localhost, for the browser to open a microphone.

## The protocol `t2v/1`

`t2v/1` is the set-up over HTTP above, then JSON messages on the call's WebRTC data channel,
each with `"v": 1` and a `type` from a closed list. The client sends `hello`, `stop`, `hangup`,
`client_stats` (its connection's view: the candidate type, the time to connect, whether echo
cancellation applied, when the first audio played) and `playback` (when each clause of the
agent's reply started and ended playing); the session sends `hello` (the call's ID and
languages), `state` (`thinking` while the talker or a tool works), `caption`, `card` (an extra
a tool of your own returned, for a client with a screen), `duck` and `unduck` (the agent's
voice lowered while the caller speaks over it, and brought back), `notice` and `ended`. The session parses every client message
strictly, and no message can set the caller or their consent (D-039). The reference client
speaks all of it: [browser-client.md](browser-client.md).
