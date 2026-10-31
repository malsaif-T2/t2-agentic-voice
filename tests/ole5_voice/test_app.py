"""The Ole5 app composes the library through its public API."""

from __future__ import annotations

from ole5_voice.app import health
from t2_agentic_voice import Settings


def test_health_reports_the_library_status(settings: Settings) -> None:
    assert health(settings).env == "test"
