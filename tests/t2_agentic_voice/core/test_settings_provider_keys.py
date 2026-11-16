"""The keys of the providers measured beside Groq (D-100; docs/SECURITY.md, invariant 5): each
group's key inline or in its file, optional, named by its own setting in every error, and never
in a repr, a log line or an error."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import configure_logging, get_logger
from t2_agentic_voice.core.settings.provider_keys import ProviderKey

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import MADE_UP_KEY, PREFIX

GROUPS = [
    "elevenlabs",
    "speechmatics",
    "cohere",
    "soniox",
    "openai",
    "inworld",
    "telnyx",
    "humain",
    "nabrah",
]


def _group(settings: VoiceSettings, name: str) -> ProviderKey:
    group = getattr(settings, name)
    assert isinstance(group, ProviderKey)
    return group


def test_each_provider_key_is_optional_and_unset_by_default() -> None:
    settings = VoiceSettings(env="test")
    assert all(_group(settings, name).resolved_api_key() is None for name in GROUPS)
    assert (settings.speechmatics.region, settings.openai.base_url) == (
        "eu",
        "https://api.openai.com/v1",
    )
    assert settings.telnyx.stt_model == "humain/realtime"
    for streamed in (settings.telnyx, settings.nabrah):
        assert (streamed.turn_timeout_s, streamed.quiet_s) == (20.0, 1.5)


@pytest.mark.parametrize("name", GROUPS)
def test_a_provider_key_loads_from_its_variable_or_its_file(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The names the provider guide gives the owner: T2V_<VENDOR>__API_KEY or its _FILE form."""
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    monkeypatch.setenv(f"{PREFIX}{name.upper()}__API_KEY", f" {MADE_UP_KEY} ")
    inline = _group(VoiceSettings.from_env(), name).resolved_api_key()
    assert inline == SecretStr(MADE_UP_KEY)
    monkeypatch.delenv(f"{PREFIX}{name.upper()}__API_KEY")
    (path := tmp_path / f"{name}.key").write_bytes(b"\xef\xbb\xbf" + MADE_UP_KEY.encode() + b"\n")
    monkeypatch.setenv(f"{PREFIX}{name.upper()}__API_KEY_FILE", str(path))
    assert _group(VoiceSettings.from_env(), name).resolved_api_key() == SecretStr(MADE_UP_KEY)
    path.write_text("\n", encoding="utf-8")
    assert _group(VoiceSettings.from_env(), name).resolved_api_key() is None


@pytest.mark.parametrize("name", GROUPS)
def test_a_bad_provider_key_names_its_own_setting_never_the_key(name: str, tmp_path: Path) -> None:
    settings = VoiceSettings.model_validate({"env": "test", name: {"api_key": f"{MADE_UP_KEY} x"}})
    with pytest.raises(ConfigurationError) as raised:
        _group(settings, name).resolved_api_key()
    assert raised.value.details == {"setting": f"{PREFIX}{name.upper()}__API_KEY"}
    assert holding(MADE_UP_KEY, shown(raised.value)) == []
    missing = tmp_path / "nope.key"
    in_file = VoiceSettings.model_validate({"env": "test", name: {"api_key_file": missing}})
    with pytest.raises(ConfigurationError) as unreadable:
        _group(in_file, name).resolved_api_key("HELPDESK_VOICE_")
    assert unreadable.value.message.startswith(f"HELPDESK_VOICE_{name.upper()}__API_KEY_FILE")
    assert holding(str(missing), shown(unreadable.value)) == []


def test_the_speechmatics_region_and_the_openai_address_are_checked() -> None:
    with pytest.raises(ConfigurationError, match=f"{PREFIX}SPEECHMATICS__REGION"):
        VoiceSettings.model_validate({"env": "test", "speechmatics": {"region": "ksa"}})
    for bad in ("http://api.openai.com/v1", "https://api.openai.com/v1?x=1"):
        with pytest.raises(ConfigurationError, match=f"{PREFIX}OPENAI__BASE_URL"):
            VoiceSettings.model_validate({"env": "test", "openai": {"base_url": bad}})
    assert VoiceSettings.model_validate({"env": "test", "speechmatics": {"region": "us"}})


def test_the_telnyx_model_and_the_streamed_turns_bounds_are_checked() -> None:
    with pytest.raises(ConfigurationError, match=f"{PREFIX}TELNYX__STT_MODEL"):
        VoiceSettings.model_validate({"env": "test", "telnyx": {"stt_model": "humain/batch"}})
    for name, field, bad in (("nabrah", "quiet_s", 0), ("telnyx", "turn_timeout_s", 121)):
        with pytest.raises(ConfigurationError, match=f"{PREFIX}{name.upper()}__{field.upper()}"):
            VoiceSettings.model_validate({"env": "test", name: {field: bad}})
    model = "deepgram/nova-3"
    chosen = VoiceSettings.model_validate({"env": "test", "telnyx": {"stt_model": model}})
    assert chosen.telnyx.stt_model == model


def test_no_provider_key_appears_in_a_repr_or_a_log_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invariant 5 for every provider key, inline and in its file."""
    (key_file := tmp_path / "provider.key").write_text(MADE_UP_KEY, encoding="utf-8")
    inline = VoiceSettings.model_validate(
        {"env": "test", **{name: {"api_key": MADE_UP_KEY} for name in GROUPS}}
    )
    files = VoiceSettings.model_validate(
        {"env": "test", **{name: {"api_key_file": key_file} for name in GROUPS}}
    )
    configure_logging("DEBUG", "json", loggers=["tests"])  # tests/conftest.py undoes it
    log = get_logger("tests.provider_keys")
    caplog.set_level(logging.DEBUG)
    resolved = []
    for each in (inline, files):
        groups = [_group(each, name) for name in GROUPS]
        found = [group.resolved_api_key() for group in groups]
        resolved.append(found)
        log.info("settings_read", settings=each, groups=groups, keys=found)
        logging.getLogger("some.library").warning("settings %s %r", each, groups)
    surfaces = shown(caplog=caplog, capsys=capsys)
    for index, each in enumerate((inline, files)):
        texts = [repr(each), str(each), each.model_dump_json(), repr(each.model_dump())]
        surfaces[f"settings {index}"] = "\n".join([*texts, repr(resolved[index])])
    assert surfaces["stdout"].count("settings_read") == 2
    assert holding(MADE_UP_KEY, surfaces) == []
    assert all(key == SecretStr(MADE_UP_KEY) for found in resolved for key in found)
