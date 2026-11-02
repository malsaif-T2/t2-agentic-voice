"""VoiceSettings: built in code from defaults and arguments alone, or loaded with `from_env` from
the environment under a prefix and a `.env` only when given one; nested in groups, an unknown
name under the prefix refused, and no refused value ever shown (GP-19). How a setting that
cannot load fails: test_settings_errors.py; the checks each group's values take:
test_settings_checks.py; the secrets: test_settings_secrets.py; how .env.example lists them:
test_env_example.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from t2_agentic_voice.core.config import VoiceSettings, foreign_set
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.groq import KEY_FILE_SETTING, KEY_SETTING
from t2_agentic_voice.core.settings.stt import SttSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import MADE_UP_KEY, PREFIX, fields, names


@pytest.fixture(autouse=True)
def _env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """`env` has no default: every load here gives one, unless a test removes it."""
    monkeypatch.setenv(f"{PREFIX}ENV", "test")


def test_built_in_code_takes_the_defaults_and_its_arguments_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The design's 7.2: no environment variable and no `.env`, not even in the working folder."""
    monkeypatch.setenv(f"{PREFIX}STT__MODEL", "whisper-large-v3-turbo")
    (tmp_path / ".env").write_text(f"{PREFIX}LOGGING__LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    settings = VoiceSettings(env="dev")
    assert (settings.env, settings.logging.level, settings.logging.format) == (
        "dev",
        "INFO",
        "console",
    )
    assert (settings.groq.api_key, settings.groq.base_url) == (None, "https://api.groq.com")
    assert (settings.stt.provider, settings.stt.model, settings.stt.timeout_s) == (
        "groq",
        "whisper-large-v3",
        6.0,
    )
    assert (settings.stt.live_language, settings.storage.var_dir) == ("session", Path("var"))
    assert (settings.tracing.endpoint, settings.tracing.include_transcripts) == (None, True)
    assert settings.prefix == PREFIX


def test_env_is_required_and_takes_staging() -> None:
    with pytest.raises(ConfigurationError, match=f"{PREFIX}ENV \\(Field required\\)"):
        VoiceSettings()  # type: ignore[call-arg]
    assert {VoiceSettings(env=env).env for env in ("dev", "test", "staging", "prod")} == {
        "dev",
        "test",
        "staging",
        "prod",
    }


def test_from_env_needs_env_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(f"{PREFIX}ENV")
    with pytest.raises(ConfigurationError, match=f"{PREFIX}ENV \\(Field required\\)"):
        VoiceSettings.from_env()


def test_reads_each_group_nested_with_two_underscores(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "LOGGING__LEVEL": "DEBUG",
        "GROQ__API_KEY": MADE_UP_KEY,
        "STT__MODEL": "whisper-large-v3-turbo",
        "STT__TIMEOUT_S": "4.5",
        "TTS__LANGUAGES": '{"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}',
        "TURNS__VAD_STOP_MS": "250",
        "SERVER__FORWARDED_ALLOW_IPS": '["127.0.0.1"]',
        "TRACING__ENDPOINT": "http://127.0.0.1:6006/v1/traces",
        "TRACING__INCLUDE_TRANSCRIPTS": "false",
        "TRACING__REDACT": '["\\\\d{10}"]',
        "STORAGE__VAR_DIR": "elsewhere",
    }.items():
        monkeypatch.setenv(f"{PREFIX}{name}", value)
    settings = VoiceSettings.from_env()
    assert settings.groq.api_key is not None
    assert settings.groq.api_key.get_secret_value() == MADE_UP_KEY
    assert (settings.logging.level, settings.stt.model, settings.stt.timeout_s) == (
        "DEBUG",
        "whisper-large-v3-turbo",
        4.5,
    )
    assert list(settings.tts.languages) == ["en"]  # a map given replaces the whole map
    assert (settings.turns.vad_stop_ms, settings.server.forwarded_allow_ips) == (
        250,
        ("127.0.0.1",),
    )
    assert settings.tracing.endpoint == "http://127.0.0.1:6006/v1/traces"
    assert (settings.tracing.include_transcripts, settings.tracing.redact) == (False, (r"\d{10}",))
    assert settings.storage.var_dir == Path("elsewhere")


def test_names_are_read_in_any_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX.lower()}stt__model", "whisper-large-v3-turbo")
    assert VoiceSettings.from_env().stt.model == "whisper-large-v3-turbo"


def test_setting_name_is_the_variable_each_setting_is_read_from() -> None:
    """The name `from_env` and the Groq adapter put in an error is the variable to set."""
    assert {setting_name(*location) for location, _ in fields()} == set(names())
    assert (f"{PREFIX}GROQ__API_KEY", f"{PREFIX}GROQ__API_KEY_FILE") == (
        KEY_SETTING,
        KEY_FILE_SETTING,
    )
    assert setting_name("tracing", "redact", 0) == f"{PREFIX}TRACING__REDACT"  # the whole list
    assert setting_name("groq", "api_key", prefix="HELPDESK_VOICE_") == (
        "HELPDESK_VOICE_GROQ__API_KEY"
    )


def test_a_team_picks_its_own_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """The design's 7.3: under another prefix, the library's own names are not read, and every
    name the settings give is under the prefix they were loaded with."""
    monkeypatch.setenv("HELPDESK_VOICE_ENV", "staging")
    monkeypatch.setenv("HELPDESK_VOICE_STT__MODEL", "whisper-large-v3-turbo")
    monkeypatch.setenv(f"{PREFIX}STT__TIMEOUT_S", "nope")  # another prefix's: never read
    settings = VoiceSettings.from_env(prefix="HELPDESK_VOICE_")
    assert (settings.env, settings.stt.model, settings.stt.timeout_s) == (
        "staging",
        "whisper-large-v3-turbo",
        6.0,
    )
    assert settings.env_name("groq", "api_key") == "HELPDESK_VOICE_GROQ__API_KEY"
    monkeypatch.setenv("HELPDESK_VOICE_STT__TIMEOUT_S", "0")
    with pytest.raises(ConfigurationError, match="HELPDESK_VOICE_STT__TIMEOUT_S"):
        VoiceSettings.from_env(prefix="HELPDESK_VOICE_")


@pytest.mark.parametrize("prefix", ["", "T2V", "1T2V_", "T2V-", "T2 V_", "T2V_\n"])
def test_a_prefix_that_cannot_start_a_name_is_refused(prefix: str) -> None:
    with pytest.raises(ConfigurationError, match="FIX:") as raised:
        VoiceSettings.from_env(prefix=prefix)
    assert raised.value.details == {"setting": "prefix"}


def test_an_unknown_name_under_the_prefix_is_refused_never_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The design's 7.4: a misspelt name never falls back to a default silently, and the error
    says the prefix is the library's alone."""
    monkeypatch.setenv(f"{PREFIX}STT__MODLE", MADE_UP_KEY)
    monkeypatch.setenv(f"{PREFIX}MY_APP_SETTING", MADE_UP_KEY)
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    error = raised.value
    assert f"{PREFIX}MY_APP_SETTING, {PREFIX}STT__MODLE names no setting" in error.message
    assert "belongs to its settings alone" in error.message and "FIX:" in error.message
    assert holding(MADE_UP_KEY, shown(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)


@pytest.mark.parametrize("name", ["GROQ", "STT", "GROQ__API_KEY__X", "TTS__LANGUAGES__EN"])
def test_a_group_or_a_part_of_a_setting_names_no_setting(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(f"{PREFIX}{name}", "{}")
    with pytest.raises(ConfigurationError, match="names no setting"):
        VoiceSettings.from_env()


def test_a_name_from_before_the_groups_says_where_it_is_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}VAR_DIR", "elsewhere")
    monkeypatch.setenv(f"{PREFIX}LOG_LEVEL", "DEBUG")
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert f"{PREFIX}VAR_DIR is {PREFIX}STORAGE__VAR_DIR now" in raised.value.message
    assert f"{PREFIX}LOG_LEVEL is {PREFIX}LOGGING__LEVEL now" in raised.value.message


def test_with_unknown_warn_an_unknown_name_is_logged_and_left_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(f"{PREFIX}STT__MODLE", MADE_UP_KEY)
    settings = VoiceSettings.from_env(unknown="warn")
    assert settings.stt.model == "whisper-large-v3"
    out = capsys.readouterr().out
    assert "setting_unknown" in out and f"{PREFIX}STT__MODLE" in out and MADE_UP_KEY not in out


def test_a_blank_value_counts_as_unset_under_any_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank timeout would otherwise fail, and a blank key file would become the path `.`;
    a blank line left from an older .env.example (an old name) changes nothing either."""
    monkeypatch.setenv(f"{PREFIX}STT__TIMEOUT_S", "")
    monkeypatch.setenv(f"{PREFIX}GROQ__API_KEY_FILE", "")
    monkeypatch.setenv(f"{PREFIX}VAR_DIR", "")
    settings = VoiceSettings.from_env()
    assert (settings.stt.timeout_s, settings.groq.api_key_file) == (6.0, None)


def test_code_arguments_win_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The design's 7.2: code arguments sit above the environment, setting by setting. A group
    given as a dict changes only the keys it names, so the environment's others (a TURN
    secret, the public address) are kept; a group object holds every key, and replaces it."""
    monkeypatch.setenv(f"{PREFIX}STT__MODEL", "whisper-large-v3-turbo")
    monkeypatch.setenv(f"{PREFIX}STT__TIMEOUT_S", "4")
    monkeypatch.setenv(f"{PREFIX}SERVER__PUBLIC_URL", "https://voice.example")
    monkeypatch.setenv(f"{PREFIX}SERVER__TURN_TTL_S", "600")
    settings = VoiceSettings.from_env(env="dev", stt={"timeout_s": 9}, server={"dev_page": True})
    assert (settings.env, settings.stt.model, settings.stt.timeout_s) == (
        "dev",
        "whisper-large-v3-turbo",
        9.0,
    )
    server = settings.server
    assert (server.dev_page, server.public_url, server.turn_ttl_s) == (
        True,
        "https://voice.example",
        600,
    )
    whole = VoiceSettings.from_env(env="dev", stt=SttSettings(timeout_s=9))
    assert (whole.stt.model, whole.stt.timeout_s, whole.server.turn_ttl_s) == (
        "whisper-large-v3",
        9.0,
        600,
    )


def test_from_env_reads_an_env_file_only_when_given_and_the_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / "run.env"
    text = f"# a comment\n{PREFIX}STT__MODEL=whisper-large-v3-turbo\nexport {PREFIX}ENV=dev\n"
    dotenv.write_text(text + "OTHER_APP_SETTING=kept-out\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    assert VoiceSettings.from_env().stt.model == "whisper-large-v3"  # no file named: none read
    loaded = VoiceSettings.from_env(env_file=dotenv)
    assert (loaded.stt.model, loaded.env) == ("whisper-large-v3-turbo", "test")


def test_an_env_file_saved_with_a_byte_order_mark_reads_its_first_name(tmp_path: Path) -> None:
    """Notepad's "UTF-8 with BOM": the first name would otherwise not start with the prefix."""
    dotenv = tmp_path / "bom.env"
    dotenv.write_bytes(b"\xef\xbb\xbf" + f"{PREFIX}STT__MODEL=whisper-large-v3-turbo\n".encode())
    assert VoiceSettings.from_env(env_file=dotenv).stt.model == "whisper-large-v3-turbo"


@pytest.mark.parametrize("kind", ["a missing file", "a folder"])
def test_from_env_refuses_an_env_file_that_is_no_file(tmp_path: Path, kind: str) -> None:
    """A mistyped `env_file` would otherwise run on the defaults (GP-06)."""
    path = tmp_path / "missing.env" if kind == "a missing file" else tmp_path
    with pytest.raises(ConfigurationError, match="FIX:") as raised:
        VoiceSettings.from_env(env_file=path)
    assert raised.value.details == {"setting": "env_file"}
    assert holding(str(tmp_path), shown(raised.value)) == []


def test_a_setting_given_twice_in_one_source_is_refused(tmp_path: Path) -> None:
    """Names differ only in case in a file (or a Linux shell): which one wins is no guess."""
    dotenv = tmp_path / "twice.env"
    dotenv.write_text(f"{PREFIX}STT__MODEL=a\n{PREFIX.lower()}stt__model=b\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="set twice"):
        VoiceSettings.from_env(env_file=dotenv)


def test_foreign_set_names_the_variables_set_never_their_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What `voice` asks at start (voice/calls.py), whatever way the settings were built: by
    name, in any case, an empty value counting as unset."""
    names = ("PIPECAT_SETUP_FILES", "PIPECAT_SMART_TURN_LOG_DATA")
    assert foreign_set(names) == frozenset()
    monkeypatch.setenv("pipecat_setup_files", MADE_UP_KEY)
    monkeypatch.setenv("PIPECAT_SMART_TURN_LOG_DATA", "")
    found = foreign_set(names)
    assert found == {"PIPECAT_SETUP_FILES"} and MADE_UP_KEY not in repr(found)
    monkeypatch.setenv("PIPECAT_SMART_TURN_LOG_DATA", "1")
    assert foreign_set(names) == set(names)
