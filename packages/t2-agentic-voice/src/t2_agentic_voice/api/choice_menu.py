"""The call choices' menu and a choice's settings (`server.call_choices`; api/call_options.py
says what an app offers).

- **`check_options`** holds an app's offers to the settings when the runtime builds its router,
  so a wrong pair fails there, never at a call: a speech-to-text model its provider takes
  (api/providers.py's `stt_kinds`); a chat model with an effort it takes (`LlmSettings`' own
  checks, so OpenAI's models take `none` alone); a voice that fits its provider (`TtsSettings`'
  own checks) and speaks every language preset the settings hold. Each failure is a
  ConfigurationError naming the offer's group and id and its FIX, never a value.
- **`menu_of`** builds the menu a page reads (`ChoiceMenu`): each offer whose provider this
  server can use, in the app's order. Groq's are listed always (the runtime needs its key), and
  so is the settings' own provider of each group; another provider only when its key is set,
  inline or in a file that can be read (api/stt_choices.py's `has_key`; a file that cannot be
  read leaves it out, logged by the provider's name). Its default in each group is the offer
  that is the settings' own, None when none is. It never holds a key, a key's file, a path, nor
  a voice's ID: the voices are named by their models alone. It reads the keys' files, so the
  runtime builds it off the loop.
- **`settings_of`** is the one place a chosen call's settings are composed, so its session, its
  talker and its usage read one object: the runtime's settings with the chosen offers in place
  of `stt` (api/stt_choices.py's `chosen_settings`, the settings' `stt.live_language` kept),
  `llm` and `tts`, each group validated again; every other setting the runtime's.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, ValidationError

from t2_agentic_voice.api.call_options import (
    CallChoice,
    CallOptions,
    ModelOffer,
    SttOffer,
    VoiceOffer,
)
from t2_agentic_voice.api.providers import stt_kinds
from t2_agentic_voice.api.stt_choices import SttChoice, chosen_settings, has_key
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.core.settings.tts import TtsSettings

_UNAVAILABLE = "call_choice_unavailable"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class OfferedStt(_Strict):
    """A speech-to-text the menu lists: its id, provider and model."""

    id: str
    provider: str
    model: str


class OfferedModel(_Strict):
    """A chat model the menu lists: its id, provider, model and effort."""

    id: str
    provider: str
    model: str
    reasoning_effort: str


class OfferedVoice(_Strict):
    """A voice the menu lists: its id, provider and models, each once, in the presets' order;
    never a voice's ID."""

    id: str
    provider: str
    models: tuple[str, ...]


class ChoiceMenu(_Strict):
    """What a call's page may choose (the module's docstring), and each group's default."""

    stt: tuple[OfferedStt, ...]
    models: tuple[OfferedModel, ...]
    voices: tuple[OfferedVoice, ...]
    default: CallChoice

    def allows(self, choice: CallChoice) -> bool:
        """Whether each id `choice` gives is listed in its own group."""
        listed = (
            (choice.stt, {offer.id for offer in self.stt}),
            (choice.model, {offer.id for offer in self.models}),
            (choice.voice, {offer.id for offer in self.voices}),
        )
        return all(chosen is None or chosen in ids for chosen, ids in listed)

    def normalized(self, choice: CallChoice) -> CallChoice:
        """`choice` with each id that is its group's default as None: the settings' own."""
        default = self.default
        return CallChoice(
            stt=None if choice.stt == default.stt else choice.stt,
            model=None if choice.model == default.model else choice.model,
            voice=None if choice.voice == default.voice else choice.voice,
        )


def check_options(settings: VoiceSettings, options: CallOptions) -> None:
    """Hold `options` to `settings` (the module's docstring); a ConfigurationError otherwise."""
    kinds = stt_kinds()
    for stt in options.stt:
        if stt.model not in kinds[stt.provider].models:
            raise _refused(
                "stt", stt.id, f"give one of the models stt_kinds lists for {stt.provider}"
            )
    for model in options.models:
        try:
            _llm(settings, model)
        except ValidationError:
            fix = "give a model llm.model names with an effort it takes (OpenAI's take none alone)"
            raise _refused("models", model.id, fix) from None
    tags = set(settings.tts.languages)
    for voice in options.voices:
        try:
            _tts(settings, voice)
        except ValidationError:
            fix = "give each language the provider's own model and voice, as tts.languages does"
            raise _refused("voices", voice.id, fix) from None
        if not tags <= set(voice.languages):
            fix = "give a voice for every language tts.languages holds"
            raise _refused("voices", voice.id, fix)


def menu_of(settings: VoiceSettings, options: CallOptions) -> ChoiceMenu:
    """The menu `options` give on this server (the module's docstring). Reads the keys' files."""
    keyed: dict[str, bool] = {}

    def usable(provider: str, own: str) -> bool:
        if provider in ("groq", own):
            return True
        if provider not in keyed:
            keyed[provider] = has_key(settings, provider, event=_UNAVAILABLE)
        return keyed[provider]

    kinds = stt_kinds()
    stt = tuple(
        OfferedStt(id=o.id, provider=o.provider, model=o.model)
        for o in options.stt
        if usable(o.provider, settings.stt.provider)
    )
    models = tuple(
        OfferedModel(
            id=o.id, provider=o.provider, model=o.model, reasoning_effort=o.reasoning_effort
        )
        for o in options.models
        if usable(o.provider, settings.llm.provider)
    )
    voices = tuple(
        OfferedVoice(id=o.id, provider=o.provider, models=_models_of(o))
        for o in options.voices
        if usable(o.provider, settings.tts.provider)
    )
    own_stt = (settings.stt.provider, kinds[settings.stt.provider].model_of(settings))
    own_llm = (settings.llm.model, settings.llm.reasoning_effort)
    own_tts = (settings.tts.provider, dict(settings.tts.languages))
    listed = ({o.id for o in stt}, {o.id for o in models}, {o.id for o in voices})
    default = CallChoice(
        stt=_first(
            o.id for o in options.stt if (o.provider, o.model) == own_stt and o.id in listed[0]
        ),
        model=_first(
            o.id
            for o in options.models
            if (o.model, o.reasoning_effort) == own_llm and o.id in listed[1]
        ),
        voice=_first(
            o.id
            for o in options.voices
            if (o.provider, dict(o.languages)) == own_tts and o.id in listed[2]
        ),
    )
    return ChoiceMenu(stt=stt, models=models, voices=voices, default=default)


def settings_of(settings: VoiceSettings, options: CallOptions, choice: CallChoice) -> VoiceSettings:
    """The settings a call with `choice` runs with (the module's docstring); each id given is one
    of `options`' (the menu allowed it)."""
    chosen = settings
    if choice.stt is not None:
        stt = _offer(options.stt, choice.stt)
        live = settings.stt.live_language
        chosen = chosen_settings(
            chosen, SttChoice(provider=stt.provider, model=stt.model, live_language=live)
        )
    if choice.model is not None:
        chosen = chosen.model_copy(
            update={"llm": _llm(settings, _offer(options.models, choice.model))}
        )
    if choice.voice is not None:
        chosen = chosen.model_copy(
            update={"tts": _tts(settings, _offer(options.voices, choice.voice))}
        )
    return chosen


def _llm(settings: VoiceSettings, offer: ModelOffer) -> LlmSettings:
    """The `llm` group with `offer`'s model, provider and effort, validated."""
    given = {
        "provider": offer.provider,
        "model": offer.model,
        "reasoning_effort": offer.reasoning_effort,
    }
    return LlmSettings.model_validate(settings.llm.model_dump() | given)


def _tts(settings: VoiceSettings, offer: VoiceOffer) -> TtsSettings:
    """The `tts` group with `offer`'s provider and voices, validated."""
    voices = {tag: voice.model_dump() for tag, voice in offer.languages.items()}
    return TtsSettings.model_validate(
        settings.tts.model_dump() | {"provider": offer.provider, "languages": voices}
    )


def _offer[O: (SttOffer, ModelOffer, VoiceOffer)](offers: tuple[O, ...], offer_id: str) -> O:
    """The offer named `offer_id`."""
    return next(offer for offer in offers if offer.id == offer_id)


def _models_of(offer: VoiceOffer) -> tuple[str, ...]:
    """The voice's models, each once, in its presets' order."""
    return tuple(dict.fromkeys(voice.model for voice in offer.languages.values()))


def _first(ids: Iterable[str]) -> str | None:
    """The first of `ids`, None when there is none."""
    return next(iter(ids), None)


def _refused(group: str, offer_id: str, fix: str) -> ConfigurationError:
    """The ConfigurationError of an offer the settings refuse: its group and id, and the FIX."""
    return ConfigurationError(
        f"The call option {offer_id} of {group} does not fit the settings. FIX: {fix}.",
        details={"group": group, "offer": offer_id},
    )
