"""Fixtures for the session's tests.

The session cuts and says the heard words with the library's own clause splitter and
pronunciation map (`domain/text/clauses.py`, `pronounce.py`), and the tests compute what they
expect through the session's `echo.said`.

The rules the session calls are the tests' fakes, patched where the session calls them, so these
tests pin the session's side alone (the rules have tests of their own under domain/): a test
that judges an overlap takes `rule`, the interruption rule's `judge` as the test scripts it; a
test of what is said over a read-back takes `consent`, the yes rule's words; and a test of the
caller's answer to a read-back takes `yes_rule`, the yes rule's `decide`.

Every step the session takes is guarded (it logs a failure by its kind and goes on, as the
`Session` protocol asks), so a test would not see a bug that raised inside it: every test here
fails on a `session_step_failed` line unless it takes `step_failures`, which allows them; and on
an `action_flow_refused` line (a move the lifecycle's table refuses, read_back_flow.py) unless it
takes `flow_refusals`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.voice.session import overlap, read_back, yes_turns

from tests.t2_agentic_voice.voice.session.overlap_support import FakeRule
from tests.t2_agentic_voice.voice.session.read_back_support import CONSENT
from tests.t2_agentic_voice.voice.session.yes_support import FakeYesRule


@pytest.fixture
def rule(monkeypatch: pytest.MonkeyPatch) -> FakeRule:
    """The interruption rule as the test scripts it (overlap_support.py's `FakeRule`), in place
    of `judge` where the session calls it (overlap.py)."""
    fake = FakeRule()
    monkeypatch.setattr(overlap, "judge", fake)
    return fake


@pytest.fixture
def consent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The yes rule's words as the read-back's tests give them (read_back_support.py's
    `CONSENT`), in place of `consent_words` where the session calls it (read_back.py). Each
    call's arguments are kept."""
    calls: list[dict[str, Any]] = []

    def words(code: str, **given: Any) -> ConsentWords:
        calls.append({"code": code, **given})
        return CONSENT

    monkeypatch.setattr(read_back, "consent_words", words)
    return calls


@pytest.fixture
def yes_rule(monkeypatch: pytest.MonkeyPatch, consent: list[dict[str, Any]]) -> FakeYesRule:
    """The yes rule as the tests give it (yes_support.py's `FakeYesRule`), in place of `decide`
    where the session calls it (yes_turns.py), with the tests' words (`consent`)."""
    fake = FakeYesRule()
    monkeypatch.setattr(yes_turns, "decide", fake)
    return fake


@pytest.fixture
def step_failures() -> None:
    """A test that takes this allows the session to log a step's failure."""


@pytest.fixture
def flow_refusals() -> None:
    """A test that takes this allows the session to log a move the table refuses."""


@pytest.fixture(autouse=True)
def _no_step_failed(
    caplog: pytest.LogCaptureFixture, request: pytest.FixtureRequest
) -> Iterator[None]:
    caplog.set_level(logging.INFO)
    yield
    for line, allowed in (
        ("session_step_failed", "step_failures"),
        ("action_flow_refused", "flow_refusals"),
    ):
        if allowed in request.fixturenames:
            continue
        failed = [r for r in caplog.records if r.getMessage() == line]
        assert not failed, [getattr(r, "fields", None) for r in failed]
