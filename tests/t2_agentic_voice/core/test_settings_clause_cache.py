"""The clause cache's two settings (core/settings/tts.py, plan 007): `tts.cache_clauses`, on by
default by the owner's ruling of 2026-11-12 after run I ("it helps and never costs anything
except space"; D-087), and `tts.clause_cache_mb`, the most disk the cache keeps, 512 by default
and at least 1; each loads from the environment, so a team turns the cache off with
`T2V_TTS__CACHE_CLAUSES=false`, and each is refused under its own name when wrong."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.tts import TtsSettings

PREFIX = "T2V_"


def test_the_clause_cache_is_on_and_bounded_at_512_mb_by_default() -> None:
    settings = VoiceSettings(env="test")
    assert (settings.tts.cache_clauses, settings.tts.clause_cache_mb) == (True, 512)
    assert (settings.tts.cache_phrases, settings.tts.trim_silence) == (True, False)


def test_both_load_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    monkeypatch.setenv(f"{PREFIX}TTS__CACHE_CLAUSES", "false")
    monkeypatch.setenv(f"{PREFIX}TTS__CLAUSE_CACHE_MB", "64")
    settings = VoiceSettings.from_env()
    assert (settings.tts.cache_clauses, settings.tts.clause_cache_mb) == (False, 64)


@pytest.mark.parametrize("megabytes", [0, -1])
def test_a_bound_under_one_megabyte_is_refused(megabytes: int) -> None:
    with pytest.raises(ValidationError, match=r"clause_cache_mb\s+Input should be greater than"):
        TtsSettings(clause_cache_mb=megabytes)


def test_a_bad_value_from_the_environment_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    monkeypatch.setenv(f"{PREFIX}TTS__CLAUSE_CACHE_MB", "0")
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert f"{PREFIX}TTS__CLAUSE_CACHE_MB (" in raised.value.message
    assert "FIX:" in raised.value.message
