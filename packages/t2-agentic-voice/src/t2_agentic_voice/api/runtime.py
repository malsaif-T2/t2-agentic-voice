"""The runtime that serves one agent's calls (the design's 4.5, 5.2 and 6.5): `VoiceRuntime`, and
the `Providers` its calls go through. The items cited are plan 003's appendix, "Changes to the
plan's interfaces".

- **Construction** is cheap and does no IO. It takes one identity source (`identity`), the
  providers (`providers`; by default the settings' own, built at start: the design's 6.1, an
  adapter passed in code beside one a setting picks), and the team's tracer provider
  (`tracer_provider`; by default a private one from `tracing.endpoint`, built inside the
  lifespan, never before it, so a server's forked worker gets its own: TD-014). It calls
  `settings.check_environment()` first: settings copied with a change
  (`model_copy(update=...)`) skip validation, so a `prod` copy with the dev page, logged call
  content or DEBUG would otherwise be served. A test gives voice's entry point through `_calls`,
  a private parameter (no facade names its type): the runtime builds its calls with it in the
  lifespan, `VoiceCalls` unless given; and the runtime's clock through `_clock`, private too
  (`SYSTEM_CLOCK` unless given): the router's records run on it, and the runtime passes it to
  `_calls` as the calls' `clock`. This module imports FastAPI, so the package root imports it
  only when `VoiceRuntime` or `Providers` is first named: FastAPI costs seconds at import.
- **The lifespan** does the IO. It takes an exclusive lock file under `storage.var_dir`
  (api/lockfile.py), so a second process on the same folder is refused with a FIX line that
  points to the sidecar, on Windows and on Linux; resolves every secret the settings name in a
  file (the Groq key, the join keys, the TURN secret), so a short one stops the server at its
  start rather than at the first join; builds the providers (the chat model among them, whose
  connection pool it keeps open for every call's requests and closes on its way out) and
  tracing; warms the adapters with no request (the platform detection the Groq SDK runs before
  its first request, TD-012, the chat adapter's included);
  has the phrase cache declare the agent's fixed phrases (`PhraseCache.declare(agent)`, under
  `storage.var_dir/<agent name>/phrases`), which synthesizes those it lacks one request at a
  time; opens the used-token store (`storage.var_dir/<agent name>/used_tokens.sqlite3`); for an
  agent that declares actions, opens its one action runner on its outbox there and reconciles
  the rows left `sending` (api/actions.py), each call's talker given it, and each call's record
  let go as the call ends (`CallEnded`); and
  starts voice's entry point (`VoiceCalls.start`), which builds Silero and Smart Turn there,
  never at import (item 24). On its way out it ends every call (`Calls.aclose`, each peer's
  close bounded by voice: item 20), gives the observers the events still queued (at most
  `OBSERVER_TIMEOUT_S`), closes the store, tracing and each adapter (`aclose`), and releases the
  lock; what it opened before a failure at start is closed the same way. It runs once at a time:
  a second entry while it runs (a router included twice) is a ConfigurationError. No error it
  raises holds a secret: Starlette sends its traceback's text to uvicorn's error log.
- **The router** (api/router.py) serves, after its prefix, the `t2v/1` routes, `POST /join`,
  `POST` and `PATCH /offer` (each with the call's offer secret, in the `X-T2V-Offer-Secret`
  header or the body, never in a URL), and `GET /health` (what the design's 10.5 lists that is
  built: the environment and the live calls), `GET /ready` and `GET /client/1/t2v-client.js`.
  `GET /dev` is no `t2v/1` route: it is mounted only with `env` dev and the dev page on
  (`server.dev_page`, or `t2v dev`), and a client that is not loopback, or any `env` but dev,
  checked before the client's address is read, gets the server's plain 404. `/join` reads the
  client's protocol version first, verifies the token once, refuses a `SignedConsent` whose
  version is not `privacy.consent_version` when that is set (a plain `Consent`, as `DevIdentity`
  gives, is not compared: D-029), fixes the call's language
  (`agent.call_language(request.language, locale=caller.locale)`, kept to the call's end), and
  mints the call's ID and offer secret. It answers `server.ice_servers` as they are set, with no
  user name or credential: no TURN credentials are minted until the deployment (the owner,
  2026-11-03; TD-048). `POST /offer` hands voice the call's caller, consent and language with
  the offer (`Calls.answer`). A call takes one offer: a second, or one after voice refused the
  first, gets 409 `already_offered`. The offer secret stops working when ICE completes or the call
  ends, and the call's own secret then gets a 409, never a 403: a PATCH a quiet 409, logged at
  DEBUG with no value, `ice_completed` once the call's `phase` is `connected`, and `call_ended`
  once it is `ended`, or None once voice has forgotten it. A PATCH with the call's own secret
  before voice answered its offer (not yet, or refused) gets the quiet 409 `not_offered`;
  `forbidden` (403) is for a secret that is missing, wrong or not this call's. A client's
  `pc_id` never reaches Pipecat (item 10). Every route the router serves, `/health`, `/ready`,
  the client script and `/dev` included, answers "runtime not started" (503 `not_started`) while
  the lifespan has not run (the decision log, 2026-11-03). The router carries the lifespan,
  which FastAPI merges when the router is included. In the mount, the app's own CORS
  middleware answers, and the runtime says so at startup (the design's 5.5).
- **The record of each call** (api/offers.py). The router keeps its own record of each call it
  joined, on the runtime's clock: a join never offered is dropped once its join token's window
  has passed, `join.ttl_s` plus twice `join.max_clock_skew_s` after the join; and an offered
  call's record `FORGOTTEN_KEPT_S` (60 s) after voice holds it no longer (`phase` None), counted
  from the first sweep that finds it so. The lifespan sweeps every `SWEEP_PERIOD_S`. A request
  for a call whose record was dropped gets 403 `forbidden`, as for a call never joined.
- **Bodies and errors** (api/http_errors.py). Each `t2v/1` route answers a `Content-Type` other
  than JSON 415 `unsupported_media_type` before it reads a byte, reads its raw body itself under
  its route's cap (`BODIES`, 413 `too_large`), and parses it with `model_validate_json`; no
  route declares a FastAPI body parameter. `/join` answers a body of another protocol version
  400 `protocol_mismatch`, with its notice, before the strict parse and before the token is
  verified. Every error of every route, a crash included, answers api/protocol.py's
  `ErrorBody`, with a status and a code its `BODIES` entry lists (GP-19); its reference is
  random and logged with the refusal's event, and its message never holds a value the request
  sent.
- **Observers** (`on`) run off the call's path: queued (at most `OBSERVER_QUEUE` events; past
  it an event is dropped and logged), each with a timeout (`OBSERVER_TIMEOUT_S`); one that raises
  or runs over is logged by its type and the call goes on; none can change a call (the design's
  6.6).
"""

from __future__ import annotations

import asyncio
import platform
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
    suppress,
)
from typing import Any, Final

from fastapi import APIRouter

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.api import router as routing
from t2_agentic_voice.api.actions import open_actions
from t2_agentic_voice.api.lockfile import LockFile
from t2_agentic_voice.api.offers import FORGOTTEN_KEPT_S, CallRecords
from t2_agentic_voice.api.providers import Providers, talkers
from t2_agentic_voice.api.router import Running
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import CallEnded, Event
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing import TracerProvider, Tracing
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.identity import IdentityVerifier
from t2_agentic_voice.voice.calls import Calls, CallsFactory, VoiceCalls
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock

__all__ = ["FORGOTTEN_KEPT_S", "Providers", "VoiceRuntime"]

# How often the lifespan sweeps the router's records, well under FORGOTTEN_KEPT_S.
SWEEP_PERIOD_S: Final = 5.0
# The most events queued for the observers, and how long one observer may take with one event.
OBSERVER_QUEUE: Final = 1000
OBSERVER_TIMEOUT_S: Final = 10.0
_FIX_IDENTITY = (
    "FIX: pass identity=SignedJoinTokens.from_settings(settings.join) (from "
    "t2_agentic_voice.identity), or DevIdentity() for env=dev on this machine; or serve it "
    "with `t2v dev APP`, which falls back to DevIdentity."
)

Observer = Callable[[Any], Awaitable[None]]

log = get_logger(__name__)


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
        settings.check_environment()
        self._agent = agent
        self._settings = settings
        self._identity = identity
        self._providers = providers
        self._tracer_provider = tracer_provider
        self._calls = _calls
        self._clock = _clock
        join = settings.join
        self._records = CallRecords(window_s=join.ttl_s + 2 * join.max_clock_skew_s)
        self._observers: list[tuple[type[Event], Observer]] = []
        self._events: asyncio.Queue[Event] | None = None
        self._actions: ActionRunner | None = None  # the agent's, set as the lifespan starts
        self._running: Running | None = None
        self._entered = False
        # Set by `serve()`, whose app answers CORS for `server.allowed_origins`.
        self._served = False

    def lifespan(self, app: object) -> AbstractAsyncContextManager[None]:
        """The runtime's lifespan, for the app that serves it (FastAPI's `lifespan` shape): the
        runtime is started inside it and stopped when it ends."""
        return self._lifespan()

    def router(self) -> APIRouter:
        """The routes of `t2v/1`, carrying the lifespan. ConfigurationError, with a FIX line,
        under `env` test or with no identity source."""
        return self._router(dev=False)

    def on[E: Event](
        self, event: type[E]
    ) -> Callable[[Callable[[E], Awaitable[None]]], Callable[[E], Awaitable[None]]]:
        """A decorator that registers a coroutine function as an observer of `event` and its
        subclasses: `@runtime.on(CallEnded)`."""

        def register(observer: Callable[[E], Awaitable[None]]) -> Callable[[E], Awaitable[None]]:
            self._observers.append((event, observer))
            return observer

        return register

    def _router(self, *, dev: bool) -> APIRouter:
        """The router; with `dev` (`t2v dev`), the dev page on and `DevIdentity` when the runtime
        has no identity source, under `env` dev only."""
        env = self._settings.env
        if env == "test":
            raise ConfigurationError(
                "A runtime is not served under env=test. FIX: give env dev, staging or prod; "
                "a test drives the runtime's parts, never a server.",
                details={"setting": self._settings.env_name("env")},
            )
        if dev and env != "dev":
            raise ConfigurationError(
                f"t2v dev serves only env=dev, not env={env}. FIX: set "
                f"{self._settings.env_name('env')}=dev, or serve it with `t2v serve APP`.",
                details={"setting": self._settings.env_name("env")},
            )
        identity = self._identity
        if identity is None and not dev:
            raise ConfigurationError(f"The runtime has no identity source. {_FIX_IDENTITY}")
        if identity is None:
            from t2_agentic_voice.adapters.dev_identity import DevIdentity

            log.warning("dev_identity", fix="pass identity= to serve real callers")
            identity = DevIdentity()
        served = routing.Served(
            agent=self._agent,
            settings=self._settings,
            identity=identity,
            records=self._records,
            clock=self._clock,
            running=lambda: self._running,
            static=routing.STATIC,
            dev_page=env == "dev" and (dev or self._settings.server.dev_page),
        )
        return routing.build_router(served, lifespan=self.lifespan)

    @asynccontextmanager
    async def _lifespan(self) -> AsyncIterator[None]:
        if self._entered:
            raise ConfigurationError(
                "The runtime's lifespan is running already. FIX: include its router in one "
                "app, once, or serve it with serve()."
            )
        self._entered = True
        try:
            async with AsyncExitStack() as stack:
                await self._start(stack)
                try:
                    yield
                finally:
                    self._running = None
                    log.info("runtime_stopping", agent=self._agent.name)
        finally:
            self._entered = False

    async def _start(self, stack: AsyncExitStack) -> None:
        """Start the runtime, each part's close pushed on `stack` as it is opened."""
        from t2_agentic_voice.adapters.phrase_cache import PhraseCache
        from t2_agentic_voice.adapters.used_tokens import SqliteUsedTokens

        settings, agent = self._settings, self._agent
        lock = LockFile.take(settings.storage.var_dir)
        stack.callback(lock.release)
        await asyncio.to_thread(_resolve_secrets, settings)
        providers = self._providers or Providers.from_settings(settings)
        stack.push_async_callback(providers.stt.aclose)
        stack.push_async_callback(providers.tts.aclose)
        if providers.chat is not None:
            stack.push_async_callback(providers.chat.aclose)
        tracing = Tracing.from_settings(settings, tracer_provider=self._tracer_provider)
        stack.push_async_callback(asyncio.to_thread, tracing.shutdown)
        await asyncio.to_thread(_warm)
        folder = settings.storage.var_dir / agent.name
        phrases = PhraseCache.from_settings(settings, providers.tts, folder=folder / "phrases")
        requests = await phrases.declare(agent)
        used_tokens = await SqliteUsedTokens.open(folder / "used_tokens.sqlite3")
        stack.push_async_callback(used_tokens.aclose)
        self._events = asyncio.Queue(OBSERVER_QUEUE)
        observing = asyncio.create_task(self._observe(self._events))
        stack.push_async_callback(_drained, self._events, observing)
        actions = await open_actions(agent, settings, clock=self._clock, stack=stack)
        self._actions = actions
        talker = talkers(agent, settings, providers.chat, actions)  # each call's, for the talker
        talking: dict[str, Any] = {}
        if talker is not None:
            talking = {"talker": talker, "chat": providers.chat}
        calls = self._calls(
            agent=agent,
            settings=settings,
            stt=providers.stt,
            tts=providers.tts,
            phrases=phrases,
            tracing=tracing,
            emit=self._emit,
            clock=self._clock,
            **talking,
        )
        stack.push_async_callback(calls.aclose)
        await calls.start()
        sweeping = asyncio.create_task(self._sweep(calls))
        stack.push_async_callback(_cancelled, sweeping)
        self._running = Running(calls=calls, used_tokens=used_tokens)
        log.info("runtime_started", agent=agent.name, phrase_requests=requests)
        if not self._served:
            log.info(
                "router_mounted",
                cors="the app's own CORS middleware answers; server.allowed_origins applies "
                "under serve() alone",
            )

    def _emit(self, event: Event) -> None:
        """Queue `event` for the observers of its kind, at once; never raises (voice's
        `EventSink`). A call's end lets its record of actions go."""
        if isinstance(event, CallEnded) and self._actions is not None:
            self._actions.forget(event.call_id)
        queue = self._events
        if queue is None or not any(isinstance(event, kind) for kind, _ in self._observers):
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("observer_queue_full", kind=type(event).__name__)

    async def _observe(self, queue: asyncio.Queue[Event]) -> None:
        """Hand each queued event to each observer of its kind, in order, each with a timeout."""
        while True:
            event = await queue.get()
            try:
                for kind, observer in list(self._observers):
                    if isinstance(event, kind):
                        await _observed(observer, event)
            finally:
                queue.task_done()

    async def _sweep(self, calls: Calls) -> None:
        """Sweep the router's records every SWEEP_PERIOD_S on the runtime's clock."""
        while True:
            await self._clock.sleep(SWEEP_PERIOD_S)
            try:
                dropped = self._records.sweep(calls.phase, now=self._clock.now())
            except Exception as error:  # the next sweep tries again
                log.error("sweep_failed", error=type(error).__name__)
            else:
                if dropped:
                    log.debug("records_dropped", count=dropped, kept=len(self._records))


def _resolve_secrets(settings: VoiceSettings) -> None:
    """Read every secret the settings name, inline or in a file, so one that is short or cannot
    be read stops the start: a ConfigurationError naming its setting, never its value."""
    prefix = settings.prefix
    settings.groq.resolved_api_key(prefix)
    settings.join.resolved_keys(prefix)
    settings.server.resolved_turn_secret(prefix)


def _warm() -> None:
    """What the Groq SDK detects on a process's first request, in a thread, which the standard
    library then keeps: so the first call's first request does not pay it (TD-012)."""
    platform.system()
    platform.platform()


async def _observed(observer: Observer, event: Event) -> None:
    """Run one observer with one event, within OBSERVER_TIMEOUT_S; a failure is logged by its
    type, never the event, which holds what was said."""
    name = getattr(observer, "__qualname__", type(observer).__name__)
    try:
        async with asyncio.timeout(OBSERVER_TIMEOUT_S):
            await observer(event)
    except TimeoutError:
        log.warning("observer_timed_out", observer=name, kind=type(event).__name__)
    except Exception as error:
        log.warning(
            "observer_failed", observer=name, kind=type(event).__name__, error=type(error).__name__
        )


async def _drained(queue: asyncio.Queue[Event], task: asyncio.Task[None]) -> None:
    """Give the observers the events still queued, at most OBSERVER_TIMEOUT_S, then stop."""
    try:
        async with asyncio.timeout(OBSERVER_TIMEOUT_S):
            await queue.join()
    except TimeoutError:
        log.warning("observers_not_drained", left=queue.qsize())
    await _cancelled(task)


async def _cancelled(task: asyncio.Task[None]) -> None:
    """Cancel `task`, returning once it has ended."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
