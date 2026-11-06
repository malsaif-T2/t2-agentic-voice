"""The Ole5 app's settings (ole5_voice/settings.py): its own under `OLE5_VOICE_`, the library's
under `T2V_`, from the environment and a `.env` given; an access code under 16 characters is
refused as the settings load, and no error shows a value it refused."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice import settings as app_settings
from ole5_voice.settings import MIN_ACCESS_CODE_CHARS, PREFIX, AppSettings, load
from pydantic import SecretStr
from t2_agentic_voice import ConfigurationError

from tests.isolation import APP_PREFIX
from tests.leaks import holding, shown

CODE = "made-up-access-code-0123"  # 24 characters
KEY = "a-made-up-join-key-of-forty-bytes-0123456"


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The variables the app's server needs, made up; the session's var dir is conftest's."""
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_JOIN__KEYS", f'{{"k1": "{KEY}"}}')
    monkeypatch.setenv("T2V_JOIN__CURRENT_KID", "k1")
    monkeypatch.setenv("OLE5_VOICE_ACCESS_CODE", CODE)
    return monkeypatch


def test_the_apps_prefix_is_the_one_the_suite_drops() -> None:
    assert PREFIX == APP_PREFIX == "OLE5_VOICE_"
    assert MIN_ACCESS_CODE_CHARS == 16


def test_both_settings_load_from_the_environment(environment: pytest.MonkeyPatch) -> None:
    loaded = load()
    assert loaded.app.access_code.get_secret_value() == CODE
    assert loaded.app.website_origin is None
    assert loaded.voice.env == "dev"
    assert loaded.voice.join.current_kid == "k1"
    assert CODE not in repr(loaded.app)


def test_a_dotenv_file_is_read_only_when_given(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.delenv("OLE5_VOICE_ACCESS_CODE")
    dotenv = tmp_path / "app.env"
    dotenv.write_text(
        f"OLE5_VOICE_ACCESS_CODE={CODE}x\nOLE5_VOICE_WEBSITE_ORIGIN=https://www.example.com\n"
        "T2V_LOGGING__LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    loaded = load(dotenv)
    assert loaded.app.access_code.get_secret_value() == f"{CODE}x"
    assert loaded.app.website_origin == "https://www.example.com"
    assert loaded.voice.logging.level == "DEBUG"
    environment.setenv("OLE5_VOICE_ACCESS_CODE", CODE)
    assert load(dotenv).app.access_code.get_secret_value() == CODE  # the environment wins
    assert load().app.website_origin is None  # no file: the environment alone


@pytest.mark.parametrize("code", ["short-code-15ch", "   padded-to-16-  ", "x" * 15])
def test_an_access_code_under_16_characters_is_refused_at_load(
    environment: pytest.MonkeyPatch, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    environment.setenv("OLE5_VOICE_ACCESS_CODE", code)
    with pytest.raises(ConfigurationError) as caught:
        load()
    assert "OLE5_VOICE_ACCESS_CODE holds fewer than 16 characters" in caught.value.message
    assert "FIX:" in caught.value.message
    assert caught.value.details == {"settings": ["OLE5_VOICE_ACCESS_CODE"]}
    assert holding(code.strip(), shown(caught.value, caplog=caplog)) == []


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_missing_or_blank_access_code_is_refused(
    environment: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        environment.delenv("OLE5_VOICE_ACCESS_CODE")
    else:
        environment.setenv("OLE5_VOICE_ACCESS_CODE", value)
    with pytest.raises(
        ConfigurationError, match=r"OLE5_VOICE_ACCESS_CODE (is not set|holds fewer)"
    ):
        load()


@pytest.mark.parametrize(
    "origin",
    ["https://www.example.com/widget", "HTTPS://WWW.EXAMPLE.COM", "https://www.example.com:443"],
)
def test_a_website_origin_not_written_as_a_browser_sends_it_is_refused(
    environment: pytest.MonkeyPatch, origin: str, caplog: pytest.LogCaptureFixture
) -> None:
    environment.setenv("OLE5_VOICE_WEBSITE_ORIGIN", origin)
    with pytest.raises(ConfigurationError, match="OLE5_VOICE_WEBSITE_ORIGIN is not an origin"):
        load()
    with pytest.raises(ConfigurationError) as caught:
        load()
    assert holding(origin, shown(caught.value, caplog=caplog)) == []


def test_the_join_key_that_signs_is_required(environment: pytest.MonkeyPatch) -> None:
    environment.delenv("T2V_JOIN__CURRENT_KID")
    with pytest.raises(ConfigurationError, match="T2V_JOIN__CURRENT_KID is not set") as caught:
        load()
    assert caught.value.details == {"settings": ["T2V_JOIN__CURRENT_KID"]}


def test_the_librarys_own_refusals_come_first(environment: pytest.MonkeyPatch) -> None:
    environment.delenv("T2V_ENV")
    with pytest.raises(ConfigurationError, match="T2V_ENV"):
        load()


def test_settings_built_in_code_keep_their_checks() -> None:
    built = AppSettings(access_code=SecretStr(f"  {CODE}  "))
    assert built.access_code.get_secret_value() == CODE  # the space around it dropped
    with pytest.raises(ValueError, match="fewer than 16"):
        AppSettings(access_code=SecretStr("x"))
    assert app_settings.GENERATOR.startswith("python -c")


def test_the_knowledge_bases_settings_have_t2s_defaults_and_none_is_needed(
    environment: pytest.MonkeyPatch,
) -> None:
    """Plan 006, Q4: the names the owner copies the values under; with none of them set the app
    still loads (its agent the echo)."""
    app = load().app
    assert (app.kb_login_email, app.kb_login_password, app.kb_api_key) == (None, None, None)
    assert (app.kb_qdrant_url, app.kb_login_url, app.kb_embedding_url, app.kb_tenant) == (
        "https://ds.t2.sa:443/ole5_agent/qdrant",
        "https://ds.t2.sa/ole5_agent/api/login",
        "https://ds.t2.sa/text_embed",
        "ole5",
    )


def test_the_knowledge_bases_access_loads_from_the_environment_kept_secret(
    environment: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    password, key = "made-up-kb-password-0123", "made-up-kb-key-4567"
    environment.setenv("OLE5_VOICE_KB_LOGIN_EMAIL", " someone@example.com ")
    environment.setenv("OLE5_VOICE_KB_LOGIN_PASSWORD", password)
    environment.setenv("OLE5_VOICE_KB_API_KEY", key)
    environment.setenv("OLE5_VOICE_KB_TENANT", "ole5-test")
    app = load().app
    assert app.kb_login_email == "someone@example.com"
    assert app.kb_login_password is not None and app.kb_api_key is not None
    assert (app.kb_login_password.get_secret_value(), app.kb_api_key.get_secret_value()) == (
        password,
        key,
    )
    surfaces = {"repr": repr(app), "dump": repr(app.model_dump())}
    assert holding(password, surfaces) == [] and holding(key, surfaces) == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KB_LOGIN_EMAIL", "not-an-email"),
        ("KB_LOGIN_EMAIL", "some one@example.com"),
        ("KB_QDRANT_URL", "http://made-up.example/qdrant"),  # the key would travel in clear text
        ("KB_LOGIN_URL", "https://user:made-up@made-up.example/login"),
        ("KB_EMBEDDING_URL", "https://made-up.example:0/embed"),
        ("KB_EMBEDDING_URL", "https://made-up.example:notaport/embed"),
        ("KB_EMBEDDING_URL", "made-up.example/embed"),
        ("KB_TENANT", "two words"),
    ],
)
def test_a_wrong_knowledge_base_setting_is_refused_never_shown(
    environment: pytest.MonkeyPatch, name: str, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    environment.setenv(f"OLE5_VOICE_{name}", value)
    with pytest.raises(ConfigurationError, match=f"OLE5_VOICE_{name} ") as caught:
        load()
    assert caught.value.details == {"settings": [f"OLE5_VOICE_{name}"]}
    assert holding(value, shown(caught.value, caplog=caplog)) == []
