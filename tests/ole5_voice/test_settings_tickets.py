"""The Ole5 app's settings for its tickets (ole5_voice/settings.py; plan 007): the demo customer
every join token names (Q3), the mock's mode for its writes, its lookup and its folder, each
with its default and read under `OLE5_VOICE_`; a wrong one refused naming the setting, never
its value. The session's var dir is conftest's, so no test touches the developer's var/."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.settings import (
    APP_FOLDER,
    DEMO_CUSTOMER_EMAIL,
    TICKETS_FOLDER,
    AppSettings,
    Settings,
    load,
    tickets_folder,
)
from pydantic import SecretStr, ValidationError
from t2_agentic_voice import ConfigurationError, StorageSettings, VoiceSettings

from tests.leaks import holding, shown
from tests.ole5_voice.server_support import CODE


def test_the_ticket_settings_have_their_defaults(environment: pytest.MonkeyPatch) -> None:
    loaded = load()
    app = loaded.app
    assert app.demo_customer_email == DEMO_CUSTOMER_EMAIL == "ole5.test@example.com"
    assert (app.tickets_mode, app.tickets_lookup, app.tickets_dir) == ("answer", True, None)
    expected = loaded.voice.storage.var_dir / APP_FOLDER / TICKETS_FOLDER
    assert tickets_folder(loaded) == expected
    assert expected.parts[-2:] == ("ole5", "tickets")


def test_the_ticket_settings_load_from_the_environment(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.setenv("OLE5_VOICE_DEMO_CUSTOMER_EMAIL", " another.demo@example.com ")
    environment.setenv("OLE5_VOICE_TICKETS_MODE", "late")
    environment.setenv("OLE5_VOICE_TICKETS_LOOKUP", "false")
    environment.setenv("OLE5_VOICE_TICKETS_DIR", str(tmp_path / "kept"))
    loaded = load()
    app = loaded.app
    assert app.demo_customer_email == "another.demo@example.com"
    assert (app.tickets_mode, app.tickets_lookup) == ("late", False)
    assert tickets_folder(loaded) == tmp_path / "kept"
    assert not (tmp_path / "kept").exists()  # loading makes no folder


def test_a_blank_ticket_setting_keeps_its_default(environment: pytest.MonkeyPatch) -> None:
    for name in ("DEMO_CUSTOMER_EMAIL", "TICKETS_MODE", "TICKETS_LOOKUP", "TICKETS_DIR"):
        environment.setenv(f"OLE5_VOICE_{name}", "")
    app = load().app
    assert (app.demo_customer_email, app.tickets_mode) == (DEMO_CUSTOMER_EMAIL, "answer")
    assert (app.tickets_lookup, app.tickets_dir) == (True, None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OLE5_VOICE_DEMO_CUSTOMER_EMAIL", "not-an-email"),
        ("OLE5_VOICE_DEMO_CUSTOMER_EMAIL", "some one@example.com"),
        ("OLE5_VOICE_DEMO_CUSTOMER_EMAIL", "made-up@" + "x" * 250 + ".com"),
        ("OLE5_VOICE_TICKETS_MODE", "sometimes"),
        ("OLE5_VOICE_TICKETS_LOOKUP", "perhaps"),
    ],
)
def test_a_wrong_ticket_setting_is_refused_never_shown(
    environment: pytest.MonkeyPatch, name: str, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    environment.setenv(name, value)
    with pytest.raises(ConfigurationError, match=f"{name} ") as caught:
        load()
    assert caught.value.details == {"settings": [name]}
    assert "FIX:" in caught.value.message
    assert holding(value, shown(caught.value, caplog=caplog)) == []


def test_the_default_folder_follows_the_librarys_var_dir(tmp_path: Path) -> None:
    voice = VoiceSettings(env="dev", storage=StorageSettings(var_dir=tmp_path / "var"))
    built = Settings(app=AppSettings(access_code=SecretStr(CODE)), voice=voice)
    assert tickets_folder(built) == tmp_path / "var" / "ole5" / "tickets"
    with pytest.raises(ValidationError):
        AppSettings(access_code=SecretStr(CODE), demo_customer_email="nobody")
