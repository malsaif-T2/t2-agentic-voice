"""The runtime that serves one agent's calls (the design's 4.5, 5.2 and 6.5): `VoiceRuntime`, and
the `Providers` its calls go through. Built by plan 003's Track F; until then signatures, each a
stub but `Providers`' fields and `replace`. The items cited are plan 003's appendix, "Changes to
the plan's interfaces"; what Track F builds:

- **Construction** is cheap and does no IO. It takes one identity source (`identity`), the
  providers (`providers`; by default the settings' own, built at start: the design's 6.1, an
  adapter passed in code beside one a setting picks), and the team's tracer provider
  (`tracer_provider`; by default a private one from `tracing.endpoint`, built inside the
  lifespan, never before it, so a server's forked worker gets its own: TD-014). It calls
  `settings.check_environment()` first: settings copied with a change
  (`model_copy(update=...)`) skip validation, so a `prod` copy with the dev page, logged call
  content or DEBUG would otherwise be served, and `voice` holds the transport loggers only
  while `logging.content` is off. Track F's test: a `staging` and a `prod` copy with each value
  `CHECKS` in tests/t2_agentic_voice/core/test_settings_checks.py refuses, each a
  ConfigurationError at construction. A test gives voice's entry point through `_calls`, a
  private parameter (no facade names its type): the runtime builds its calls with it in the
  lifespan, `VoiceCalls` unless given. Track F's tests give one that returns a
  `FakeCalls` (tests/t2_agentic_voice/fakes.py); step 16's gives one that builds `VoiceCalls`
  with a fake speech detector. A test gives the runtime's clock through `_clock`, private too
  (`SYSTEM_CLOCK` unless given): the router's records run on it, and the runtime passes it to
  `_calls` as the calls' `clock`.
- **The lifespan** does the IO. It takes an exclusive lock file under `storage.var_dir`, so a
  second process on the same folder is refused with a FIX line that points to the sidecar, on
  Windows and on Linux; resolves every secret the settings name in a file, so a short one stops
  the server at its start rather than at the first join; builds the providers and tracing;
  warms the adapters with no request (TD-012); has the phrase cache declare the agent's fixed
  phrases (`PhraseCache.declare(agent)`: domain/fixed_phrases.py, said through the agent's
  pronunciation map), which synthesizes those it lacks one request at a time, one longer than
  the text-to-speech's `max_chars` in requests packed up to it, so the runtime refuses none at
  its start (adapters/phrase_cache.py); opens the used-token store under
  `storage.var_dir`; and starts voice's entry point (`VoiceCalls.start`), which builds Silero
  and Smart Turn there, never at import (item 24). On its way out it ends every call, each
  peer's close bounded by a timeout (item 20), closes each adapter (`aclose`), the store and
  tracing, and releases the lock. No error it raises holds a secret: Starlette sends its
  traceback's text to uvicorn's error log (the appendix, step 4, bullet 5).
- **The router** serves, after its prefix, the `t2v/1` routes, `POST /join`, `POST` and
  `PATCH /offer` (each with the call's offer secret, in the `X-T2V-Offer-Secret` header or the
  body, never in a URL), and `GET /health` (only what the design's 10.5 lists), `GET /ready`
  and `GET /client/1/t2v-client.js` (the design's 4.5 and 5.5; the bodies are
  api/protocol.py's). `GET /dev` is no `t2v/1` route: it is mounted only with `env` dev, and a
  client that is not loopback gets the server's plain 404, as for a path it does not have.
  `/join` reads the client's protocol version first (below), verifies the token once, refuses a
  `SignedConsent` whose version is not `privacy.consent_version` when that is set (a plain
  `Consent`, as `DevIdentity` gives, is not compared: D-029), fixes the call's language
  (`agent.call_language(request.language, locale=caller.locale)`, kept to the call's end),
  mints the call's ID and offer secret, and the call's TURN credentials when the settings hold
  a TURN secret, inline or in a file (`server.resolved_turn_secret()`, which the lifespan read).
  `POST /offer` hands voice the call's caller, consent and language with the offer
  (`Calls.answer`). The offer secret stops working when ICE completes or the call ends, and
  the call's own secret then gets a 409, never a 403: a second offer `already_offered`, and a
  PATCH a quiet 409, logged at DEBUG with no value, `ice_completed` once the call's `phase` is
  `connected`, and `call_ended` once it is `ended`, or None once voice has forgotten it. A
  PATCH with the call's own secret before voice answered its offer (not yet, or refused) gets
  the quiet 409 `not_offered`; `forbidden` (403) is for a secret that is missing, wrong or not
  this call's. A client's `pc_id` never reaches Pipecat (item 10). Every `t2v/1` route answers
  "runtime not started" while the lifespan has not run. The router carries the lifespan, which
  FastAPI merges when the router is included (an app that includes it twice runs it twice). In
  the mount, the app's own CORS middleware answers, and the router says so at startup (the
  design's 5.5).
- **The record of each call.** The router keeps its own record of each call it joined (its
  offer secret, and its caller, consent and language until its offer), on the runtime's clock:
  a join never offered is dropped once its join token's window has passed, `join.ttl_s` plus
  twice `join.max_clock_skew_s` after the join; and an answered call's record
  `FORGOTTEN_KEPT_S` (60 s) after voice forgets the call (`phase` None), counted from the first
  sweep that finds it so. The router sweeps its records in the lifespan, on a period Track F
  sets and records, well under `FORGOTTEN_KEPT_S`. A request for a call whose record was
  dropped gets 403 `forbidden`, as for a call never joined, so the records stay bounded by one
  token window's joins and the calls voice holds.
- **Bodies.** Each `t2v/1` route first reads the request's `Content-Type` (api/protocol.py's
  `is_json`: `application/json`, a parameter such as `charset=utf-8` allowed, none at all
  refused) and answers any other 415 `unsupported_media_type` before it reads a byte, so a
  cross-site form or text/plain POST, which skips the CORS preflight, never reaches a route. It
  reads its raw body itself, never more than its route's cap (`BODIES`, `max_bytes`): a
  `Content-Length` over the cap is refused before a byte is read, and a body that streams past
  the cap (with no length, or a length that lies) is refused at the cap, each 413 `too_large`,
  so no body is buffered or parsed whole on the event loop that paces every call's audio.
  `/join` then reads the body as any JSON for its top-level `protocol` alone, before the strict
  parse (`version_mismatch`): any value but the integer 1 is answered 400 `protocol_mismatch`,
  with its notice, whatever else the body holds, and spends no token, so a client of any other
  version gets the notice (the design's 5.4). Each route then parses the body with the model's
  `model_validate_json` and answers a ValidationError with `refusal(error, reference=...)`,
  which holds pydantic's error types only. No route declares a model as a FastAPI body
  parameter: FastAPI answers that with its own 422, whose `errors()` carry the token, the offer
  secret or a candidate's address back to the client, and in the mount the app's handler
  answers it, since a router can install none.
- **Errors.** Every error of every `t2v/1` route, a crash included, answers api/protocol.py's
  `ErrorBody`, with a status and a code its `BODIES` entry lists (GP-19). Its reference is
  random, made for the request, and logged with the refusal's event; its message never holds a
  value the request sent. `/dev`'s refusal is the server's plain 404 (above).
- **Track F's tests** for the bodies and errors, through the router included in a plain FastAPI
  app, with `FakeCalls` as the calls and a `FakeClock` as `_clock`:
  - on each `t2v/1` route, a body over the cap sent with its true length, with none (chunked),
    and with a `Content-Length` that lies (under the cap, then a longer body) each answers 413
    in the one shape; and a valid JSON body sent as `text/plain`, as
    `application/x-www-form-urlencoded` or as `multipart/form-data`, or with no
    `Content-Type`, answers 415 `unsupported_media_type`, the body unread;
  - each body of `ADVERSARIAL` in tests/t2_agentic_voice/api/test_protocol.py, which its own
    test refuses as a route parses it (`model_validate_json` of its JSON text), answers 400
    (`invalid_request`, or `protocol_mismatch` for a `/join` body whose `protocol` is not the
    integer 1) with no value or key it sent anywhere in the response; and
    `{"token": "x", "protocol": 2, "capabilities": []}` answers 400 `protocol_mismatch` with
    its notice, the verifier never asked;
  - each route's errors match its `BODIES` entry, status and code;
  - a PATCH and a `POST /offer` with the call's own secret after `FakeCalls.connect` answer 409
    `ice_completed` and `already_offered`, and after `end`, and after `forget`, `call_ended` and
    `already_offered`, never 403; a PATCH before the call's offer, and after an offer voice
    refused (`FakeCalls(refused=...)`), answers 409 `not_offered`, each at DEBUG;
  - joins never offered, and calls ended and forgotten (`FakeCalls.end`, `forget`): once the
    clock has passed the token window and `FORGOTTEN_KEPT_S`, and a sweep's period, the router
    holds no record, and a PATCH and a `POST /offer` with each call's own secret answer 403
    `forbidden`;
  - with only `server.turn_secret_file` set (a file of 32 bytes or more), `/join`'s ICE servers
    carry a username and a credential for each `turn:` and `turns:` URL; and with
    `privacy.consent_version` set, a `DevIdentity` join in `dev` goes through, while a
    `SignedConsent` of another version is refused.
- **Observers** (`on`) run off the call's path: queued, with a timeout; one that raises is logged
  and the call goes on; none can change a call (the design's 6.6).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from fastapi import APIRouter

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.tracing import TracerProvider
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.identity import IdentityVerifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.calls import CallsFactory, VoiceCalls
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock

_STUB = "the runtime is built by plan 003's Track F"
# How long the router keeps an answered call's record once voice has forgotten the call, so a
# late PATCH still gets the quiet 409 `call_ended`; after it, a PATCH gets 403 `forbidden`.
FORGOTTEN_KEPT_S = 60.0


@dataclass(frozen=True, kw_only=True)
class Providers:
    """The providers a runtime's calls go through (the design's 5.2): speech-to-text and
    text-to-speech, each an adapter object; the chat model comes with the talker. A setting
    picks a built-in adapter (`from_settings`), and any other is passed in code (the design's
    6.1): `Providers.from_settings(settings).replace(stt=...)`."""

    stt: SpeechToText
    tts: TextToSpeech

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> Providers:
        """The built-in adapters the settings pick (`stt.provider`, `tts.provider`: Groq's),
        built from the settings; built in the runtime's lifespan when none are given."""
        raise NotImplementedError(_STUB)

    def replace(
        self, *, stt: SpeechToText | None = None, tts: TextToSpeech | None = None
    ) -> Providers:
        """These providers with each one given in place of its own."""
        return Providers(stt=self.stt if stt is None else stt, tts=self.tts if tts is None else tts)


class VoiceRuntime:
    """Runs one agent's calls (the design's 5.2): `agent` with `settings`, its callers verified
    by `identity` (one source; None only for `t2v dev`, which falls back to `DevIdentity`),
    through `providers`, traced on `tracer_provider`. Served by `serve()` or `t2v serve`, or
    mounted: `app.include_router(runtime.router(), prefix="/voice")`."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        settings: VoiceSettings,
        identity: IdentityVerifier | None = None,
        providers: Providers | None = None,
        tracer_provider: TracerProvider | None = None,
        _calls: CallsFactory = VoiceCalls,
        _clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        raise NotImplementedError(_STUB)

    def lifespan(self, app: object) -> AbstractAsyncContextManager[None]:
        """The runtime's lifespan, for the app that serves it (FastAPI's `lifespan` shape): the
        runtime is started inside it and stopped when it ends."""
        raise NotImplementedError(_STUB)

    def router(self) -> APIRouter:
        """The routes of `t2v/1`, carrying the lifespan. ConfigurationError, with a FIX line,
        under `env` test or with no identity source."""
        raise NotImplementedError(_STUB)

    def on[E: Event](
        self, event: type[E]
    ) -> Callable[[Callable[[E], Awaitable[None]]], Callable[[E], Awaitable[None]]]:
        """A decorator that registers a coroutine function as an observer of `event` and its
        subclasses: `@runtime.on(CallEnded)`."""
        raise NotImplementedError(_STUB)
