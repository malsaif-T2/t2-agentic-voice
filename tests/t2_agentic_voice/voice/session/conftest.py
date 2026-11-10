"""Fixtures for the session's tests (plan 003's Track D, plan 005's Track B).

The session cuts and says the heard words with Track A's clause splitter and pronunciation map
(`domain/text/clauses.py`, `pronounce.py`). Until Track A merges they are Block 0's stubs, so
these tests build against stand-ins of the same contract (every track builds against Block 0's
interfaces, never another track's unfinished code): each is used only while the real function
is a stub, and the tests compute what they expect through the session's own `echo.said`, so
they hold with Track A's functions too.

The interruption rule (domain/interruptions.py's `judge`) is plan 005's Track A's, built in
parallel: a test that judges an overlap takes `rule`, a fake the test scripts, patched where the
session calls it, and never runs Track A's code. So for the yes rule's words (plan 007's Track
A's `consent_words`): a test of what is said over a read-back takes `consent`.

Every step the session takes is guarded (it logs a failure by its kind and goes on, as the
`Session` protocol asks), so a test would not see a bug that raised inside it: every test here
fails on a `session_step_failed` line unless it takes `step_failures`, which allows them.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text import clauses, pronounce
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.voice.session import echo, overlap, read_back

from tests.t2_agentic_voice.voice.session.overlap_support import FakeRule
from tests.t2_agentic_voice.voice.session.read_back_support import CONSENT

# Where a clause may end: the Arabic comma and question mark, and the Latin punctuation.
_ENDS = re.compile(r"(?<=[،؟.,!?;:])\s+")


def _split(text: str, *, max_chars: int | None) -> tuple[str, ...]:
    """Track A's contract, for the tests: cut at punctuation, then pack words up to
    `max_chars`, a longer word cut every `max_chars` characters."""
    found: list[str] = []
    for part in _ENDS.split(text.strip()):
        line = ""
        for word in part.split():
            while max_chars is not None and len(word) > max_chars:
                if line:
                    found.append(line)
                    line = ""
                found.append(word[:max_chars])
                word = word[max_chars:]
            joined = f"{line} {word}".strip()
            if max_chars is not None and len(joined) > max_chars:
                found.append(line)
                line = word
            else:
                line = joined
        if line:
            found.append(line)
    return tuple(found)


def _pronounce(
    text: str, pronunciations: Mapping[str, Mapping[str, str]], *, language: LanguageTag
) -> str:
    """Track A's contract, for the tests: each written form standing as whole words replaced
    by how the language's primary code says it."""
    code = "en" if language == "en" else "ar"
    for form, said in pronunciations.items():
        if code in said:
            text = re.sub(rf"(?<!\w){re.escape(form)}(?!\w)", said[code], text)
    return text


def _stub(call: object) -> bool:
    try:
        call()  # type: ignore[operator]
    except NotImplementedError:
        return True
    return False


@pytest.fixture(autouse=True)
def _speech_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stand-ins, each only while Track A's function is Block 0's stub."""
    if _stub(lambda: clauses.split_clauses("a", max_chars=None)):
        monkeypatch.setattr(echo, "split_clauses", _split)
    if _stub(lambda: pronounce.pronounce("a", {}, language="en")):
        monkeypatch.setattr(echo, "pronounce", _pronounce)


@pytest.fixture
def rule(monkeypatch: pytest.MonkeyPatch) -> FakeRule:
    """The starting rule as the test scripts it (overlap_support.py's `FakeRule`), standing in
    for Track A's `judge` where the session calls it: these tests never run Track A's code."""
    fake = FakeRule()
    monkeypatch.setattr(overlap, "judge", fake)
    return fake


@pytest.fixture
def consent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The yes rule's words as the read-back's tests give them (read_back_support.py's
    `CONSENT`), standing in for Track A's `consent_words` where the session calls it
    (read_back.py): these tests never run Track A's code. Each call's arguments are kept."""
    calls: list[dict[str, Any]] = []

    def words(code: str, **given: Any) -> ConsentWords:
        calls.append({"code": code, **given})
        return CONSENT

    monkeypatch.setattr(read_back, "consent_words", words)
    return calls


@pytest.fixture
def step_failures() -> None:
    """A test that takes this allows the session to log a step's failure."""


@pytest.fixture(autouse=True)
def _no_step_failed(
    caplog: pytest.LogCaptureFixture, request: pytest.FixtureRequest
) -> Iterator[None]:
    caplog.set_level(logging.INFO)
    yield
    if "step_failures" in request.fixturenames:
        return
    failed = [r for r in caplog.records if r.getMessage() == "session_step_failed"]
    assert not failed, [getattr(r, "fields", None) for r in failed]
