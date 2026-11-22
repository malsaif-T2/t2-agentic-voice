"""What an app offers its page to choose for a call (`server.call_choices`; the owner,
2026-11-22): the speech-to-text, the chat model and the voice, each a closed set the app gives
the runtime in code (`VoiceRuntime(call_options=CallOptions(...))`), since which providers and
models a product offers is the app's choice, not the environment's.

- **An offer** (`SttOffer`, `ModelOffer`, `VoiceOffer`) is named by the app's own id, a short
  lowercase name (`OfferId`), and says in the settings' own names what it runs: a provider
  `stt.provider` names with one of its models; a model `llm.model` names with an effort it
  takes; a provider `tts.provider` names with the model and voice of each language preset, as
  `tts.languages` holds them. The runtime checks each against the settings when it builds its
  router (api/choice_menu.py's `check_options`), so a wrong pair fails there, never at a call.
- **The menu** a page reads lists only the offers whose provider's key this server holds, and
  never a key, a key's file, a path or a voice's ID (api/choice_menu.py).
- **A choice** (`CallChoice`) is one call's, by its offers' ids, each None for the settings'
  own; the page's body is parsed strictly into it (api/choices_route.py), so only ids reach the
  server, never a provider's or a model's name.

Pure pydantic over core: the facade that gives these names stays cheap to import (GP-17).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.llm import LlmModel, LlmProvider, LlmSettings, ReasoningEffort
from t2_agentic_voice.core.settings.stt import SttProvider
from t2_agentic_voice.core.settings.tts_voices import LanguageTag, TtsProvider, TtsVoice

# An offer's id, as an app names it and its page sends it: lowercase letters, digits, `.`, `_`
# and `-`, at most 40 characters.
OfferId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,39}$")]


class _Offer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SttOffer(_Offer):
    """One speech-to-text an app offers: its id, a provider `stt.provider` names, and one of that
    provider's models (api/providers.py's `stt_kinds`); the call keeps the settings'
    `stt.live_language`."""

    id: OfferId
    provider: SttProvider
    model: str = Field(min_length=1, max_length=80)


class ModelOffer(_Offer):
    """One chat model an app offers: its id, a model `llm.model` names, and an effort that model
    takes (core/settings/llm.py's `EFFORTS`)."""

    id: OfferId
    model: LlmModel
    reasoning_effort: ReasoningEffort

    @property
    def provider(self) -> LlmProvider:
        """The provider that serves the model."""
        return LlmSettings.provider_of(self.model)


class VoiceOffer(_Offer):
    """One voice an app offers: its id, a provider `tts.provider` names, and the model and voice
    of each language preset, in that provider's own names (as `tts.languages` holds them)."""

    id: OfferId
    provider: TtsProvider
    languages: Annotated[Mapping[LanguageTag, TtsVoice], FROZEN, PLAIN]


class CallOptions(_Offer):
    """What an app offers its page to choose for a call (the module's docstring), each group in
    the order its menu shows; the ids unique within each group, and one offer at least."""

    stt: tuple[SttOffer, ...] = ()
    models: tuple[ModelOffer, ...] = ()
    voices: tuple[VoiceOffer, ...] = ()

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        for group, offers in (("stt", self.stt), ("models", self.models), ("voices", self.voices)):
            ids = [offer.id for offer in offers]
            if len(set(ids)) != len(ids):
                raise ValueError(f"two offers of {group} share an id")
        if not (self.stt or self.models or self.voices):
            raise ValueError("no offer is given: give one at least, or no call options")
        return self


class CallChoice(BaseModel):
    """One call's choice, by its offers' ids; None in a group: the settings' own. Parsed
    strictly from a page's body (api/choices_route.py)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    stt: OfferId | None = None
    model: OfferId | None = None
    voice: OfferId | None = None

    def none(self) -> bool:
        """Whether it chooses nothing: every group the settings' own."""
        return self.stt is None and self.model is None and self.voice is None
