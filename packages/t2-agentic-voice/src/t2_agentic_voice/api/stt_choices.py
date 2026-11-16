"""The dev console's choice of speech-to-text for one call (the owner, 2026-11-16: a quick way
for a developer to try and switch the providers and models): what this process offers, and the
settings a chosen call runs with. Only the console's routes take a choice (api/dev_stt.py).

- `SttMenu`: the closed set of choices, as `menu_of` builds it from the settings: each provider
  of `stt_kinds` (api/providers.py, the one place that names them) whose key is set, Groq's
  always, each with the models it takes; and the language modes `stt.live_language` has,
  `classified` only when the runtime loaded a classifier. It never holds a key, a key's file or
  its path: a provider's name and its models alone. A key file that cannot be read leaves its
  provider out, logged by the provider's name and the failure's kind.
- `SttChoice`: one call's provider, model and language mode, parsed strictly from the
  console's body; `SttMenu.allows` holds it to the menu.
- `chosen_settings`: the settings with the choice in place of `stt.provider`, the provider's
  model setting (Groq's `stt.model`; one that takes a single model has none) and
  `stt.live_language`, every other setting as it is.
- `heard_by`: the provider and model a call's turns are heard by, as the console's records name
  them.
"""

from __future__ import annotations

from typing import get_args

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.api.providers import SttKind, stt_kinds
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.stt import LiveLanguage

_log = get_logger(__name__)


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class SttChoice(_Strict):
    """One call's speech-to-text: its provider (an `stt.provider` name), its model, and the
    language mode (an `stt.live_language` value)."""

    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)
    live_language: str = Field(min_length=1, max_length=40)


class SttOption(_Strict):
    """One provider this process offers, with the models it takes, its default first."""

    provider: str
    models: tuple[str, ...]


class SttMenu(_Strict):
    """What the dev console may choose (the module's docstring): the providers, the language
    modes, and the choice the settings make, which a call with no choice runs."""

    providers: tuple[SttOption, ...]
    live_languages: tuple[str, ...]
    default: SttChoice

    def allows(self, choice: SttChoice) -> bool:
        """Whether `choice` is one of the menu's: a provider it offers, one of that provider's
        models, and one of its language modes."""
        offered = {option.provider: option.models for option in self.providers}
        models = offered.get(choice.provider, ())
        return choice.model in models and choice.live_language in self.live_languages


def menu_of(settings: VoiceSettings, *, classifier: bool) -> SttMenu:
    """The menu `settings` offer (the module's docstring); `classifier`: whether the runtime
    loaded the classifier `classified` needs. Reads each key's file, so it runs off the loop."""
    kinds = stt_kinds()
    default = SttChoice(
        provider=settings.stt.provider,
        model=kinds[settings.stt.provider].model_of(settings),
        live_language=settings.stt.live_language,
    )
    options = tuple(
        SttOption(provider=name, models=_models(kind, settings))
        for name, kind in kinds.items()
        if name in (default.provider, "groq") or _has_key(settings, name, kind)
    )
    modes = tuple(mode for mode in get_args(LiveLanguage) if mode != "classified" or classifier)
    if default.live_language not in modes:
        modes += (default.live_language,)
    return SttMenu(providers=options, live_languages=modes, default=default)


def chosen_settings(settings: VoiceSettings, choice: SttChoice) -> VoiceSettings:
    """`settings` with `choice` in place (the module's docstring); `choice` is the menu's."""
    kind = stt_kinds()[choice.provider]
    stt: dict[str, object] = {"provider": choice.provider, "live_language": choice.live_language}
    groups: dict[str, object] = {}
    if kind.model_setting is not None:
        group, field = kind.model_setting
        if group == "stt":
            stt[field] = choice.model
        else:
            groups[group] = getattr(settings, group).model_copy(update={field: choice.model})
    return settings.model_copy(update={"stt": settings.stt.model_copy(update=stt), **groups})


def heard_by(choice: SttChoice) -> dict[str, str]:
    """The provider and model `choice` hears a call's turns with, as a record names them."""
    return {"provider": choice.provider, "model": choice.model}


def _models(kind: SttKind, settings: VoiceSettings) -> tuple[str, ...]:
    """The models `kind` takes, the one the settings name first."""
    first = kind.model_of(settings)
    return (first, *(model for model in kind.models if model != first))


def _has_key(settings: VoiceSettings, name: str, kind: SttKind) -> bool:
    """Whether the provider's key is set, inline or in a file that can be read."""
    group = getattr(settings, kind.key_group, None)
    resolve = getattr(group, "resolved_api_key", None)
    if resolve is None:
        return False
    try:
        return resolve(settings.prefix) is not None
    except ConfigurationError as error:
        _log.warning("stt_choice_unavailable", provider=name, failure=type(error).__name__)
        return False
