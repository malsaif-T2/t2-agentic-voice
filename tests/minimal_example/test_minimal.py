"""The minimal example runs on the public API alone."""

from __future__ import annotations

from minimal_example import run
from t2_agentic_voice import Settings


def test_runs_with_the_public_api(settings: Settings) -> None:
    assert run(settings).var_dir == settings.var_dir
