"""The talker's settings (plan 006): the `llm` and `guard` groups, `words.vocabulary` and
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
        "max_requests_per_turn": 3,
        "retry_rejected": False,
    }
    assert settings.guard.model_dump() == {
        "id_patterns": (),
        "min_id_digits": 3,
        "on_block": "drop_rest",
        "claims": {},
        "remove_stray_script": True,
        "questions_per_reply": 1,
        "question_stop_drops_calls": False,
        "drop_stage_notes": False,
        "plain_speech": False,
        "retry_claims": False,
    }
    assert (settings.words.vocabulary, settings.session.mode) == ((), None)


def test_the_new_settings_load_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T2V_ENV", "test")
    monkeypatch.setenv("T2V_LLM__MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("T2V_LLM__REASONING_EFFORT", "medium")
    monkeypatch.setenv("T2V_LLM__VARY_FIRST_LINE", "false")
    monkeypatch.setenv("T2V_LLM__MAX_REQUESTS_PER_TURN", "4")
    monkeypatch.setenv("T2V_LLM__RETRY_REJECTED", "true")
    monkeypatch.setenv("T2V_GUARD__ID_PATTERNS", '["LT-\\\\d{5}"]')
    monkeypatch.setenv("T2V_GUARD__ON_BLOCK", "drop_clause")
    monkeypatch.setenv("T2V_GUARD__QUESTIONS_PER_REPLY", "2")
    monkeypatch.setenv("T2V_GUARD__QUESTION_STOP_DROPS_CALLS", "true")
    monkeypatch.setenv("T2V_GUARD__DROP_STAGE_NOTES", "true")
    monkeypatch.setenv("T2V_WORDS__VOCABULARY", '["VPN", "Outlook"]')
    monkeypatch.setenv("T2V_SESSION__MODE", "talker")
    settings = VoiceSettings.from_env()
    assert (settings.llm.model, settings.llm.reasoning_effort, settings.llm.vary_first_line) == (
        "llama-3.3-70b-versatile",
        "medium",
        False,
    )
    assert (settings.guard.id_patterns, settings.guard.on_block) == (("LT-\\d{5}",), "drop_clause")
    assert settings.guard.questions_per_reply == 2
    assert settings.guard.question_stop_drops_calls and settings.guard.drop_stage_notes
    assert settings.llm.max_requests_per_turn == 4 and settings.llm.retry_rejected
    assert (settings.words.vocabulary, settings.session.mode) == (("VPN", "Outlook"), "talker")


def test_no_question_limit_is_set_in_code() -> None:
    """None, given in code, sets no limit; an environment variable left blank keeps 1."""
    assert GuardSettings(questions_per_reply=None).questions_per_reply is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM__PROVIDER", "azure"),
        ("LLM__MODEL", "gpt-4o"),
        ("LLM__REASONING_EFFORT", "max"),
        ("LLM__MAX_OUTPUT_TOKENS", "0"),
        ("LLM__TIMEOUT_S", "-1"),
        ("LLM__VARY_FIRST_LINE", "maybe"),
        ("LLM__MAX_REQUESTS_PER_TURN", "1"),  # the only request would offer no tool
        ("LLM__MAX_REQUESTS_PER_TURN", "6"),
        ("GUARD__ID_PATTERNS", '["("]'),  # no regular expression
        ("GUARD__ID_PATTERNS", '["\\\\d*"]'),  # matches every clause
        ("GUARD__MIN_ID_DIGITS", "0"),
        ("GUARD__ON_BLOCK", "drop_call"),
        ("GUARD__QUESTIONS_PER_REPLY", "0"),
        ("GUARD__QUESTIONS_PER_REPLY", "one"),
        ("GUARD__QUESTION_STOP_DROPS_CALLS", "maybe"),
        ("GUARD__DROP_STAGE_NOTES", "maybe"),
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
