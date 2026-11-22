"""Each call's speech-to-text, chat model and voice an app's page chose (`server.call_choices`;
api/call_options.py's offers, api/choice_menu.py's menu, api/choices_route.py's routes):
`CallChoices`, which the runtime makes with the setting on, and `chosen_calls`, which hands
voice the lookup of each call's `ChosenCall` (voice/entry.py), the dev console's and the app's.

- **At the runtime's start** (`open`) the menu is built, off the loop, since it reads the keys'
  files, and nothing else: the start sends no request for a choice.
- **A choice** is kept for a joined call until its offer takes it (`take`, once); one that is
  the settings' own in every group is kept as none, and the call runs as every other. At most
  `MOST_PENDING` choices wait for their offer; the oldest goes first past it. One whose offer
  came while its voice was opening is not kept (`already_offered`): that offer found none and
  runs on the server's own, so a choice kept then would name what the call never ran on.
- **A voice** is opened on its first choice, once per process, while that choice's request
  waits (its phrases declared on its own text-to-speech, under the agent's `phrases` folder,
  whose files are keyed by model and voice; its clause cache in `<agent>/choices/<id>/clauses`,
  since a clause cache indexes and trims its whole folder). A second choice of it waits for the
  same opening, which a client that goes away does not cancel. One that cannot be opened refuses
  the choice (`voice_unavailable`), logged by the error's kind or type, never its message; the
  next choice of it tries again.
- **The adapters** are built at the offer, with no IO, and kept for the later calls that choose
  them: one speech-to-text per offer; the runtime's chat model for a model of its provider (an
  adapter serves every model of its provider: the request names the model), else one per
  provider (under OpenAI a `ChatRoute`, so the library's own checks stay on Groq's gpt-oss-120b);
  one talker factory per combination, on that combination's settings (api/choice_menu.py's
  `settings_of`). A ConfigurationError while building (a key file removed since the menu was
  built) never fails the call: it runs on the server's own, logged as `call_choice_failed`.
- **What a call ran on** (`call_choice`): the choice its offer took, kept for the last
  `MOST_KEPT` calls, so an app's records name it after the call ends.
- **At the runtime's stop** (`aclose`) every voice opened, and every adapter built for a
  choice, is closed; the runtime's own are never among them.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.agent.talker import chat_talkers
from t2_agentic_voice.api.call_options import CallChoice, CallOptions
from t2_agentic_voice.api.choice_menu import ChoiceMenu, check_options, menu_of, settings_of
from t2_agentic_voice.api.lockfile import agent_folder
from t2_agentic_voice.api.providers import Providers, stt_model_of
from t2_agentic_voice.api.stt_calls import CallStts
from t2_agentic_voice.api.voices import Voices, open_voices
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.entry import ChosenCall
from t2_agentic_voice.voice.talkers import TalkerFactory

# The most choices kept for calls not yet offered, and the most calls whose choice is kept.
MOST_PENDING: Final = 100
MOST_KEPT: Final = 200

# What `choose` says: kept (as none, too), not one the menu offers, a voice not opened, or an
# offer that came while the voice opened.
Chosen = Literal["kept", "not_offered", "voice_unavailable", "already_offered"]

_log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChoiceBuilders:
    """How a choice's adapters are built from its settings, with no IO: `Providers`' own unless
    a test gives fakes."""

    stt: Callable[[VoiceSettings], SpeechToText] = field(default=Providers.speech_to_text)
    tts: Callable[[VoiceSettings], TextToSpeech] = field(default=Providers.text_to_speech)
    chat: Callable[[VoiceSettings], ChatModel] = field(default=Providers.chat_model)


@dataclass(frozen=True, kw_only=True)
class ChoiceParts:
    """What the runtime's start opened that a choice builds on: the agent, the runtime's
    providers, its talker factory (None for an echo agent) and its action runner."""

    agent: VoiceAgent
    providers: Providers
    talker: TalkerFactory | None = None
    actions: ActionRunner | None = None


class CallChoices:
    """An app's page's choices, call by call (the module's docstring), among `options`, for a
    runtime run with `settings`; the offers are checked here (a ConfigurationError when one does
    not fit the settings), the menu built at the runtime's start (`open`)."""

    def __init__(
        self,
        settings: VoiceSettings,
        options: CallOptions,
        *,
        builders: ChoiceBuilders | None = None,
    ) -> None:
        check_options(settings, options)
        self._settings, self._options = settings, options
        self._builders = builders or ChoiceBuilders()
        self.menu: ChoiceMenu | None = None
        self._parts: ChoiceParts | None = None
        self._pending: OrderedDict[CallId, CallChoice] = OrderedDict()
        self._kept: OrderedDict[CallId, CallChoice] = OrderedDict()
        self._opening: dict[str, asyncio.Task[Voices | None]] = {}
        self._built: dict[tuple[str | None, str | None, str | None], ChosenCall] = {}
        self._stts: dict[str, SpeechToText] = {}
        self._chats: dict[str, ChatModel] = {}
        self._stack = AsyncExitStack()  # each opened voice's clause cache, then its adapter

    async def open(self, parts: ChoiceParts) -> None:
        """Build the menu, off the event loop, and keep `parts` for the choices' adapters."""
        self._parts = parts
        self.menu = await asyncio.to_thread(menu_of, self._settings, self._options)
        _log.info(
            "call_choices_offered",
            stt=[offer.id for offer in self.menu.stt],
            models=[offer.id for offer in self.menu.models],
            voices=[offer.id for offer in self.menu.voices],
        )

    async def choose(
        self, call_id: CallId, choice: CallChoice, *, unoffered: Callable[[], bool]
    ) -> Chosen:
        """Keep `choice` for the joined call `call_id`, in place of any it had, a voice it names
        opened first (the module's docstring), while `unoffered` says its offer has not come;
        nothing new kept unless it says `kept`."""
        menu = self.menu
        if menu is None or not menu.allows(choice):
            return "not_offered"
        choice = menu.normalized(choice)
        if choice.voice is not None and await self._voice(choice.voice) is None:
            return "voice_unavailable"
        if not unoffered():
            return "already_offered"
        self._pending.pop(call_id, None)
        if not choice.none():
            self._pending[call_id] = choice
            while len(self._pending) > MOST_PENDING:
                self._pending.popitem(last=False)
        return "kept"

    def take(self, call_id: CallId) -> ChosenCall | None:
        """The call's `ChosenCall`, once, as voice answers its offer; None for a call with no
        choice, or one whose providers could not be built (it runs on the server's own)."""
        choice = self._pending.pop(call_id, None)
        parts = self._parts
        if choice is None or parts is None:
            return None
        key = (choice.stt, choice.model, choice.voice)
        chosen = self._built.get(key)
        if chosen is None:
            try:
                chosen = self._build(choice, parts)
            except ConfigurationError as error:
                _log.warning("call_choice_failed", call_id=call_id, error=type(error).__name__)
                return None
            self._built[key] = chosen
        self._kept[call_id] = choice
        while len(self._kept) > MOST_KEPT:
            self._kept.popitem(last=False)
        return chosen

    def call_choice(self, call_id: CallId) -> CallChoice | None:
        """The choice the call's offer took, its ids none of them the settings' own; None for a
        call with none, one not yet offered, or one past the last MOST_KEPT."""
        return self._kept.get(call_id)

    async def aclose(self) -> None:
        """Stop the voices still opening, close every voice opened and every adapter built for a
        choice."""
        opening, self._opening = list(self._opening.values()), {}
        for task in opening:
            task.cancel()
        await asyncio.gather(*opening, return_exceptions=True)
        await self._stack.aclose()
        adapters: list[SpeechToText | ChatModel] = [*self._stts.values(), *self._chats.values()]
        self._stts, self._chats, self._built = {}, {}, {}
        for adapter in adapters:
            await adapter.aclose()

    async def _voice(self, voice_id: str) -> Voices | None:
        """The voice `voice_id`, opened once (the module's docstring); None when it cannot be."""
        task = self._opening.get(voice_id)
        if task is None or (task.done() and _voices_of(task) is None):
            task = asyncio.create_task(self._opened(voice_id), name=f"t2v-voice-{voice_id}")
            self._opening[voice_id] = task
        return await asyncio.shield(task)

    async def _opened(self, voice_id: str) -> Voices | None:
        """Open the voice `voice_id`: its adapter, its phrases, its clause cache."""
        parts = self._parts
        if parts is None:
            return None
        settings = settings_of(self._settings, self._options, CallChoice(voice=voice_id))
        folder = agent_folder(self._settings, parts.agent) / "choices" / voice_id / "clauses"
        try:
            tts = self._builders.tts(settings)
            self._stack.push_async_callback(tts.aclose)
            voices = await open_voices(
                parts.agent, settings, tts, stack=self._stack, clauses=folder
            )
        except (ProviderError, ConfigurationError, OSError) as error:
            failure = error.kind if isinstance(error, ProviderError) else type(error).__name__
            _log.warning("call_voice_unavailable", voice=voice_id, failure=failure)
            return None
        _log.info("call_voice_opened", voice=voice_id, phrase_requests=voices.phrase_requests)
        return voices

    def _build(self, choice: CallChoice, parts: ChoiceParts) -> ChosenCall:
        """The call's providers for `choice` (the module's docstring), with no IO."""
        settings = settings_of(self._settings, self._options, choice)
        stt, stt_model = parts.providers.stt, None
        if choice.stt is not None:
            if choice.stt not in self._stts:
                self._stts[choice.stt] = self._builders.stt(settings)
            stt, stt_model = self._stts[choice.stt], stt_model_of(settings)
        chat = parts.providers.chat
        talker = None
        if parts.talker is not None:
            provider = settings.llm.provider
            if provider != self._settings.llm.provider:
                if provider not in self._chats:
                    self._chats[provider] = self._builders.chat(settings)
                chat = self._chats[provider]
            talker = chat_talkers(parts.agent, settings, chat, parts.actions)
        voices = None
        if choice.voice is not None:
            voices = _voices_of(self._opening[choice.voice])
            if voices is None:  # cannot happen after `choose`; the server's own then
                raise ConfigurationError("The chosen voice is not open.")
        return ChosenCall(
            settings=settings,
            stt=stt,
            stt_model=stt_model,
            tts=None if voices is None else voices.tts,
            phrases=None if voices is None else voices.phrases,
            talker=talker,
            chat=chat if parts.talker is not None else None,
        )


def call_choices_of(
    settings: VoiceSettings, options: CallOptions | None, builders: ChoiceBuilders | None = None
) -> CallChoices | None:
    """The runtime's call choices under `server.call_choices`, the offers checked; None with
    it off, `options` then ignored (logged once). A ConfigurationError when it is on with no
    options."""
    name = settings.env_name("server", "call_choices")
    if not settings.server.call_choices:
        if options is not None:
            _log.info("call_choices_off", setting=name)
        return None
    if options is None:
        raise ConfigurationError(
            "server.call_choices is on, but the runtime was given no call options. FIX: pass "
            f"call_options=CallOptions(...) to VoiceRuntime, or set {name}=false.",
            details={"setting": name},
        )
    return CallChoices(settings, options, builders=builders)


def _voices_of(task: asyncio.Task[Voices | None]) -> Voices | None:
    """The voice a finished opening gave; None while it runs, or when it failed or stopped."""
    if not task.done() or task.cancelled() or task.exception() is not None:
        return None
    return task.result()


async def chosen_calls(
    stts: CallStts | None,
    choices: CallChoices | None,
    parts: ChoiceParts,
    *,
    classifier: bool,
    stack: AsyncExitStack,
) -> dict[str, Any]:
    """What voice's calls are given for the choices: `chosen`, the lookup of each call's
    `ChosenCall`, the dev console's (`stts`, with its menu built: `classifier`, whether the
    runtime loaded one) and an app's page's (`choices`), each opened and its close pushed on
    `stack`; nothing when neither is made (today's calls, as before: GP-18). A call both chose
    for runs on the app's choice, both taken, so none is left over."""
    if stts is None and choices is None:
        return {}
    if stts is not None:
        await stts.open(classifier=classifier)
        stack.push_async_callback(stts.aclose)
    if choices is not None:
        await choices.open(parts)
        stack.push_async_callback(choices.aclose)

    def chosen(call_id: CallId) -> ChosenCall | None:
        dev = stts.take(call_id) if stts is not None else None
        app = choices.take(call_id) if choices is not None else None
        return app or dev

    return {"chosen": chosen}
