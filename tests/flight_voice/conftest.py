"""Fixtures the flight agent's tests share; the suite's own are in `tests/conftest.py`."""

from __future__ import annotations

import pytest

from tests.flight_voice.server_support import CODE, KEY


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The variables the app's server needs, made up (`server_support`'s code and key); the
    session's var dir is tests/conftest.py's."""
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_JOIN__KEYS", f'{{"k1": "{KEY}"}}')
    monkeypatch.setenv("T2V_JOIN__CURRENT_KID", "k1")
    monkeypatch.setenv("FLIGHT_VOICE_ACCESS_CODE", CODE)
    return monkeypatch
