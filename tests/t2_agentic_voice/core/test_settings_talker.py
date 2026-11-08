"""The talker's settings (plan 006, Block 0): the `llm` and `guard` groups, `words.vocabulary` and
`session.mode`'s `talker`, each with the design's 7.6 default, refused when wrong under its own
name, and `session.mode` left unset so that no setting changes its meaning: an echo agent still
runs the echo, `echo` still runs it, and only an agent that declares instructions runs the
talker unless told."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.session import SessionSettings

PREFIX = "T2V_"


def test_the_llm_and_guard_defaults_are_the_designs() -> None:
    settings = VoiceSettings(env="test")
    assert settings.llm.model_dump() == {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "reasoning_effort": "medium",
        "max_output_tokens": 1024,
        "timeout_s": 8.0,
        "vary_first_line": True,
    }
    assert settings.guard.model_dump() == {
        "id_patterns": (),
        "min_id_digits": 3,
        "on_block": "drop_rest",
    }
    assert (settings.words.vocabulary, settings.session.mode) == ((), None)


def test_the_new_settings_load_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T2V_ENV", "test")
    monkeypatch.setenv("T2V_LLM__MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("T2V_LLM__REASONING_EFFORT", "medium")
    monkeypatch.setenv("T2V_LLM__VARY_FIRST_LINE", "false")
    monkeypatch.setenv("T2V_GUARD__ID_PATTERNS", '["LT-\\\\d{5}"]')
    monkeypatch.setenv("T2V_GUARD__ON_BLOCK", "drop_clause")
    monkeypatch.setenv("T2V_WORDS__VOCABULARY", '["VPN", "Outlook"]')
    monkeypatch.setenv("T2V_SESSION__MODE", "talker")
    settings = VoiceSettings.from_env()
    assert (settings.llm.model, settings.llm.reasoning_effort, settings.llm.vary_first_line) == (
        "llama-3.3-70b-versatile",
        "medium",
        False,
    )
    assert (settings.guard.id_patterns, settings.guard.on_block) == (("LT-\\d{5}",), "drop_clause")
    assert (settings.words.vocabulary, settings.session.mode) == (("VPN", "Outlook"), "talker")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM__PROVIDER", "openai"),
        ("LLM__MODEL", "gpt-4o"),
        ("LLM__REASONING_EFFORT", "none"),
        ("LLM__MAX_OUTPUT_TOKENS", "0"),
        ("LLM__TIMEOUT_S", "-1"),
        ("LLM__VARY_FIRST_LINE", "maybe"),
        ("GUARD__ID_PATTERNS", '["("]'),  # no regular expression
        ("GUARD__ID_PATTERNS", '["\\\\d*"]'),  # matches every clause
        ("GUARD__MIN_ID_DIGITS", "0"),
        ("GUARD__ON_BLOCK", "drop_call"),
        ("WORDS__VOCABULARY", '[""]'),
        ("SESSION__MODE", "auto"),
    ],
)
def test_a_wrong_value_is_refused_under_its_name(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("T2V_ENV", "test")
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ConfigurationError, match=f"{PREFIX}{name} "):
        VoiceSettings.from_env()


def test_a_pattern_error_names_the_pattern_by_its_place_never_its_text() -> None:
    with pytest.raises(ValueError, match="pattern 1 is not a regular expression") as raised:
        GuardSettings(id_patterns=("\\d{4}", "made-up-secret(("))
    assert "made-up-secret" not in str(raised.value)


def test_the_mode_unset_follows_the_declaration_and_changes_no_setting() -> None:
    unset = SessionSettings()
    assert (unset.mode_for(instructed=False), unset.mode_for(instructed=True)) == (
        "echo",
        "talker",
    )
    echo = SessionSettings(mode="echo")
    assert (echo.mode_for(instructed=False), echo.mode_for(instructed=True)) == ("echo", "echo")
    assert SessionSettings(mode="talker").mode_for(instructed=True) == "talker"


def test_the_talker_is_refused_for_an_agent_with_no_instructions() -> None:
    with pytest.raises(
        ConfigurationError, match="HELPDESK_VOICE_SESSION__MODE is talker"
    ) as raised:
        SessionSettings(mode="talker").mode_for(instructed=False, prefix="HELPDESK_VOICE_")
    assert "FIX: " in str(raised.value)
    assert raised.value.details == {"setting": "HELPDESK_VOICE_SESSION__MODE"}
