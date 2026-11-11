"""The test console's dev caller (`server.dev_caller`, D-083): the caller an app declares for the
console's own join tokens, in code or as JSON in `T2V_SERVER__DEV_CALLER`, parsed strictly as
the library's `Caller` and read-only once loaded; none unless declared. A shape a caller cannot
take is refused, naming the setting and never the value it was given."""

from __future__ import annotations

import json

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import PREFIX

NAME = f"{PREFIX}SERVER__DEV_CALLER"
CALLER = Caller(subject="owner", attributes={"customer_email": "demo@example.com"})
MARK = "zx-refused-value@example.com"  # a value no error may repeat


def test_no_dev_caller_is_declared_unless_one_is_given() -> None:
    assert ServerSettings().dev_caller is None
    assert VoiceSettings(env="dev").server.dev_caller is None


def test_an_app_declares_one_in_code_and_nothing_changes_it() -> None:
    settings = VoiceSettings(env="dev", server=ServerSettings(dev_page=True, dev_caller=CALLER))
    declared = settings.server.dev_caller
    assert declared == CALLER
    assert declared is not None
    with pytest.raises(TypeError):
        declared.attributes["customer_email"] = MARK  # type: ignore[index]
    with pytest.raises(TypeError):
        settings.server.dev_caller = None  # type: ignore[misc]


def test_the_environment_gives_one_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}ENV", "dev")
    monkeypatch.setenv(NAME, json.dumps(CALLER.model_dump()))
    assert VoiceSettings.from_env().server.dev_caller == CALLER


@pytest.mark.parametrize(
    "given",
    [
        {"subject": "owner", "role": MARK},  # no field of a caller's
        {"subject": "owner", "attributes": {"customer_email": 7}},
        {"subject": "owner", "attributes": {"customer email": MARK}},
        {"subject": " "},
        {"attributes": {"customer_email": MARK}},  # no subject
        {"subject": 7},
        MARK,
    ],
)
def test_a_shape_a_caller_cannot_take_is_refused_never_its_value(given: object) -> None:
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.model_validate({"env": "dev", "server": {"dev_caller": given}})
    assert NAME in raised.value.message
    assert holding(MARK, shown(raised.value)) == []


def test_the_environment_giving_text_that_is_no_json_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}ENV", "dev")
    monkeypatch.setenv(NAME, MARK)
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert f"{NAME} (is not valid JSON)" in raised.value.message
    assert holding(MARK, shown(raised.value)) == []
