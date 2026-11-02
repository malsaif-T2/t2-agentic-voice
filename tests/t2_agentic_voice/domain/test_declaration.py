"""The declaration of a use case (the design's 4.3 and 5.2; plan 003, Q3): an agent with a name and
its languages, each built from its preset with the team's greeting and the echo's frame."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟")
ENGLISH = Language.english(greeting="Hi! Which branch can I help you with?")


def test_each_preset_has_its_tag_and_the_frame_the_owner_chose() -> None:
    """Q3's frames: «سمعتك تقول: …» for both Arabic presets, "I heard: …" for English."""
    msa = Language.arabic(greeting="مرحبا بك")
    assert [(lang.tag, lang.echo_frame, lang.primary) for lang in (SAUDI, msa, ENGLISH)] == [
        ("ar-SA", "سمعتك تقول:", "ar"),
        ("ar", "سمعتك تقول:", "ar"),
        ("en", "I heard:", "en"),
    ]
    assert ENGLISH.greeting == "Hi! Which branch can I help you with?"


@pytest.mark.parametrize("greeting", ["", "   ", "Hi\nthere", "Hi\x00"])
def test_a_greeting_says_something_on_one_line(greeting: str) -> None:
    with pytest.raises(ValidationError):
        Language.english(greeting=greeting)


def test_a_language_is_frozen_and_takes_no_other_field() -> None:
    with pytest.raises(ValidationError):
        ENGLISH.greeting = "Hello"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Language.model_validate({"tag": "fr", "greeting": "Bonjour", "echo_frame": "J'ai entendu:"})
    with pytest.raises(ValidationError):
        Language.model_validate(ENGLISH.model_dump() | {"voice": "troy"})


def test_an_agent_has_a_name_and_its_languages_the_first_a_calls_own() -> None:
    agent = VoiceAgent(name="branch-helper", languages=[SAUDI, ENGLISH])
    assert (agent.name, agent.languages) == ("branch-helper", (SAUDI, ENGLISH))
    assert agent.languages[0].tag == "ar-SA"
    with pytest.raises(ValidationError):
        agent.name = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        VoiceAgent.model_validate({"name": "x", "languages": [ENGLISH], "tools": []})


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({"name": "Branch Helper", "languages": [ENGLISH]}, "name"),
        ({"name": "../var", "languages": [ENGLISH]}, "name"),
        ({"name": "9lives", "languages": [ENGLISH]}, "name"),
        ({"name": "a" * 65, "languages": [ENGLISH]}, "name"),
        ({"name": "helper", "languages": []}, "languages"),
        (
            {"name": "helper", "languages": [ENGLISH, Language.english(greeting="Hello")]},
            "languages",
        ),
    ],
)
def test_an_agent_it_cannot_run_is_a_configuration_error_with_a_fix(
    values: dict[str, Any], field: str
) -> None:
    """Its name names a folder under `storage.var_dir`, so nothing but a lowercase word."""
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        VoiceAgent.model_validate(values)
    assert raised.value.details == {"field": field}
