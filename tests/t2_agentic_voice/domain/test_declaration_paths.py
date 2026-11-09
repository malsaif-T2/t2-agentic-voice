"""Every way to build a declaration fails the same way (domain/declaration.py): a team's subclass
of `Language`, and `model_validate_json` given a text that is not JSON, raise the
ConfigurationError the presets and `model_validate` raise, naming the field (None for an input
that is no object at all), with a FIX line, and never the value."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

ENGLISH = Language.english(greeting="Hello there.")


class Branded(Language):
    """A team's language with a helper of its own, as a subclass may add."""

    @property
    def shout(self) -> str:
        return self.greeting.upper()


class Extended(Language):
    """A team's language with a field of its own."""

    brand: str = "plain"


def test_a_subclass_of_language_builds_through_its_presets() -> None:
    branded = Branded.english(greeting="Hello there.")
    assert (type(branded), branded.shout) == (Branded, "HELLO THERE.")


@pytest.mark.parametrize("model", [Branded, Extended])
def test_a_subclass_fails_as_language_does(model: type[Language]) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        model.english(greeting="Hi\nthere")
    assert raised.value.details == {"field": "greeting"}
    assert str(raised.value).startswith("A language cannot run with its `greeting`")
    with pytest.raises(ConfigurationError, match="keeps the preset's text") as raised:
        model.english(greeting="Hi there", notices={"ended": ""})
    with pytest.raises(
        ConfigurationError, match="each of busy, error, cut_off and ended"
    ) as raised:
        model.model_validate(ENGLISH.model_dump() | {"notices": {}})
    with pytest.raises(ConfigurationError, match="build each language with its preset") as raised:
        model.model_validate("en")
    assert raised.value.details == {"field": None}


def test_a_field_a_subclass_adds_or_a_key_none_has_is_named() -> None:
    with pytest.raises(ConfigurationError) as raised:
        Extended.model_validate(ENGLISH.model_dump() | {"brand": 3})
    assert raised.value.details == {"field": "brand"}
    assert "FIX: correct `brand`, the field Extended adds to Language." in str(raised.value)
    with pytest.raises(ConfigurationError) as raised:
        Extended.model_validate(ENGLISH.model_dump() | {"voice": "troy"})
    assert raised.value.details == {"field": "voice"}
    assert "`notices`, `progress` and `brand`." in str(raised.value)


def test_a_declaration_round_trips_through_json() -> None:
    agent = VoiceAgent(name="helper", languages=[ENGLISH], pronounce={"LT-": {"en": "L T"}})
    assert VoiceAgent.model_validate_json(agent.model_dump_json()) == agent
    assert Language.model_validate_json(ENGLISH.model_dump_json()) == ENGLISH


@pytest.mark.parametrize(
    "text",
    [
        '{"name": "Secret',  # cut short
        '{"name": "x"} Secret',  # more after its object
        "",
        b'{"name": "\xffSecret"}',  # not UTF-8
        "[" * 100_000,  # nested past the parser's depth
        '{"name": "\\ud800Secret"}',  # a lone surrogate's escape
        "Secret",
    ],
)
@pytest.mark.parametrize("model", [Language, VoiceAgent])
def test_a_text_that_is_not_json_is_a_configuration_error(
    model: type[Language | VoiceAgent], text: Any
) -> None:
    with pytest.raises(ConfigurationError, match="FIX: give `model_validate_json`") as raised:
        model.model_validate_json(text)
    assert raised.value.details == {"field": None}
    assert "Secret" not in str(raised.value)
    assert raised.value.__context__ is None and raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("model", "text", "field"),
    [
        (VoiceAgent, '{"name": "Secret Name", "languages": []}', "name"),
        (VoiceAgent, '"Secret"', None),
        (Language, '{"tag": "en", "greeting": "Secret\\nline"}', "greeting"),
    ],
)
def test_json_that_parses_fails_as_model_validate_does(
    model: type[Language | VoiceAgent], text: str, field: str | None
) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        model.model_validate_json(text)
    assert raised.value.details == {"field": field}
    assert "Secret" not in str(raised.value)
