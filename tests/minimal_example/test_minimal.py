"""The minimal example runs on the public API alone."""

from __future__ import annotations

from minimal_example import run
from t2_agentic_voice import VoiceSettings


def test_runs_with_the_public_api(settings: VoiceSettings) -> None:
    assert run(settings).var_dir == settings.storage.var_dir
