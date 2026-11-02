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
  ConfigurationError at construction.
- **The lifespan** does the IO. It takes an exclusive lock file under `storage.var_dir`, so a
  second process on the same folder is refused with a FIX line that points to the sidecar, on
  Windows and on Linux; resolves every secret the settings name in a file, so a short one stops
  the server at its start rather than at the first join; builds the providers and tracing;
  warms the adapters with no request (TD-012); declares the agent's fixed phrases to the phrase
  cache, which synthesizes those it lacks; opens the used-token store under `storage.var_dir`;
  and starts voice's entry point (`VoiceCalls.start`), which builds Silero and Smart Turn there,
  never at import (item 24). On its way out it ends every call, each peer's close bounded by a
  timeout (item 20), closes each adapter (`aclose`), the store and tracing, and releases the
  lock. No error it raises holds a secret: Starlette sends its traceback's text to uvicorn's
  error log (the appendix, step 4, bullet 5).
- **The router** serves, after its prefix, `POST /join`, `POST` and `PATCH /offer` (each with
  the call's offer secret, in the `X-T2V-Offer-Secret` header or the body, never in a URL),
  `GET /health` (only what the design's 10.5 lists), `GET /ready`,
  `GET /client/1/t2v-client.js`, and `GET /dev` only with `env` dev and only to loopback clients
  (the design's 4.5 and 5.5; the bodies are api/protocol.py's). `/join` verifies the token once,
  refuses a consent version other than `privacy.consent_version`, mints the call's ID and offer
  secret, and the call's TURN credentials when `server.turn_secret` is set. A second offer gets
  409; the offer secret stops working when ICE completes or the call ends, and a PATCH after
  that gets a quiet 409, logged at DEBUG with no value; a client's `pc_id` never reaches
  Pipecat (item 10). Every route answers "runtime not started" while the lifespan has not run,
  and every error has one shape (GP-19). The router carries the lifespan, which FastAPI merges
  when the router is included (an app that includes it twice runs it twice). In the mount, the
  app's own CORS middleware answers, and the router says so at startup (the design's 5.5).
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

_STUB = "the runtime is built by plan 003's Track F"


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
