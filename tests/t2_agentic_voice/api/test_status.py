"""The status use case: a typed summary of the settings, refused for settings their `env`
refuses (each check in each environment: test_settings_checks.py)."""

from __future__ import annotations

import pytest
from t2_agentic_voice.api.status import Status, status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.logs import LoggingSettings


def test_status_summarizes_the_settings(settings: VoiceSettings) -> None:
    var_dir = settings.storage.var_dir
    assert status(settings) == Status(env="test", log_level="INFO", var_dir=var_dir)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_staging_and_production_refuse_debug_logs(settings: VoiceSettings, env: str) -> None:
    debug = LoggingSettings(level="DEBUG")
    unsafe = settings.model_copy(update={"env": env, "logging": debug})
    with pytest.raises(ConfigurationError) as raised:
        status(unsafe)
    assert raised.value.code == "configuration_error"
