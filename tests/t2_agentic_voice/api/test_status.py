"""The status use case: a typed summary of the settings, refused for an unsafe production."""

from __future__ import annotations

import pytest
from t2_agentic_voice.api.status import Status, status
from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.core.errors import ConfigurationError


def test_status_summarizes_the_settings(settings: Settings) -> None:
    assert status(settings) == Status(env="test", log_level="INFO", var_dir=settings.var_dir)


def test_production_refuses_debug_logs(settings: Settings) -> None:
    unsafe = settings.model_copy(update={"env": "prod", "log_level": "DEBUG"})
    with pytest.raises(ConfigurationError) as raised:
        status(unsafe)
    assert raised.value.code == "configuration_error"
