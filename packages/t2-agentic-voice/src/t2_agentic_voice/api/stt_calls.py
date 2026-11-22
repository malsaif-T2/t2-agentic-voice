"""Each call's speech-to-text the dev console chose (api/stt_choices.py's menu, api/dev_stt.py's
route): `CallStts`, which the runtime makes with the dev page alone and hands voice, beside an
app's page's choices, as the lookup of each call's `ChosenCall` (voice/entry.py;
api/choice_calls.py's `chosen_calls`).

- **A choice** is kept for a joined call until its offer takes it (`take`, once): the call is
  then heard by the chosen provider and model, with `chosen_settings`; a call with no choice,
  or one whose choice is the settings' own, takes none and runs as every other call. At most
  `MOST_PENDING` choices wait for their offer; the oldest goes first past it.
- **The adapters** are built on a call's offer, one per provider and model, from the chosen
  settings with no IO, and kept for the later calls that choose them, every one closed with the
  runtime (`aclose`); the runtime's own speech-to-text is never one of them.
- **At the runtime's start** (api/choice_calls.py's `chosen_calls`), the menu is built and the
  adapters' close pushed on its stack, and voice is given `take`; with no dev page, nothing.
- **Who heard a call** (`heard_by`): the chosen provider and model, else the settings' own,
  kept for the last `MOST_HEARD` calls, so the console's records name it after the call ends.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Final

from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.api.stt_choices import (
    SttChoice,
    SttMenu,
    chosen_settings,
    heard_by,
    menu_of,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.voice.entry import ChosenCall

# The most choices kept for calls not yet offered, and the most calls whose hearer is kept.
MOST_PENDING: Final = 100
MOST_HEARD: Final = 200

_log = get_logger(__name__)


class CallStts:
    """The dev console's choices of speech-to-text, call by call (the module's docstring), for a
    runtime run with `settings`; its menu is built at the runtime's start (`open`)."""

    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings
        self.menu: SttMenu | None = None
        self._pending: OrderedDict[CallId, SttChoice] = OrderedDict()
        self._heard: OrderedDict[CallId, dict[str, str]] = OrderedDict()
        self._adapters: dict[tuple[str, str], SpeechToText] = {}

    async def open(self, *, classifier: bool) -> None:
        """Build the menu, off the event loop, since it reads the keys' files; `classifier`:
        whether the runtime loaded the classifier `classified` needs."""
        self.menu = await asyncio.to_thread(menu_of, self._settings, classifier=classifier)
        offered = [option.provider for option in self.menu.providers]
        _log.info("stt_choices_offered", providers=offered, modes=list(self.menu.live_languages))

    def choose(self, call_id: CallId, choice: SttChoice) -> bool:
        """Keep `choice` for the joined call `call_id`, in place of any it had; False, keeping
        nothing new, when the menu does not offer it (or is not built yet). The settings' own
        choice is kept as none."""
        menu = self.menu
        if menu is None or not menu.allows(choice):
            return False
        self._pending.pop(call_id, None)
        if choice != menu.default:
            self._pending[call_id] = choice
            while len(self._pending) > MOST_PENDING:
                self._pending.popitem(last=False)
        return True

    def take(self, call_id: CallId) -> ChosenCall | None:
        """The call's `ChosenCall`, once, as voice answers its offer; None for a call with no
        choice. Its adapter is built here (no IO) the first time its provider and model are."""
        choice = self._pending.pop(call_id, None)
        if choice is None:
            return None
        settings = chosen_settings(self._settings, choice)
        key = (choice.provider, choice.model)
        if key not in self._adapters:
            self._adapters[key] = Providers.speech_to_text(settings)
        self._heard[call_id] = heard_by(choice)
        while len(self._heard) > MOST_HEARD:
            self._heard.popitem(last=False)
        return ChosenCall(settings=settings, stt=self._adapters[key], stt_model=choice.model)

    def heard_by(self, call_id: CallId) -> dict[str, str] | None:
        """The provider and model the call's turns were heard by: its choice's, else the
        settings' own; None before the menu is built."""
        if call_id in self._heard:
            return dict(self._heard[call_id])
        return None if self.menu is None else heard_by(self.menu.default)

    async def aclose(self) -> None:
        """Close every adapter built for a choice."""
        adapters, self._adapters = list(self._adapters.values()), {}
        for adapter in adapters:
            await adapter.aclose()
