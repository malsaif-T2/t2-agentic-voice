"""The lean instructions written for the airline's today (lean/agent.py's `dated`, D-135): the
library asks for them on each request; they are built once a day for both languages and kept,
so a request pays a lookup, not a build, and a server left running past midnight prompts with
the new day's calendar (the owner's calls of 2026-11-22 heard 19 November's)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import pytest
from flight_voice.airline.system import Airline
from flight_voice.lean import prompt
from flight_voice.lean.agent import declare

from tests.flight_voice.lean.lean_support import lean_deps
from tests.flight_voice.scenario_dates import TODAY

_TODAY_LINE = re.compile(r"Today is [^\n]*\((\d{4}-\d{2}-\d{2})\)\.")


def test_the_instructions_follow_the_airlines_today_and_are_built_once_a_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"today": TODAY}
    built: list[date] = []
    write = prompt.instructions

    def counted(*args: Any, **kwargs: Any) -> Any:
        built.append(args[1])
        return write(*args, **kwargs)

    monkeypatch.setattr(prompt, "instructions", counted)
    agent = declare(lean_deps(Airline(today=lambda: clock["today"])))
    written = agent.instructions
    assert callable(written)
    for _ in range(50):  # every request of the day: one build, at the declaration
        for tag in ("ar-SA", "en"):
            assert written(clock["today"], tag)
    assert built == [TODAY]
    later = TODAY + timedelta(days=3)
    clock["today"] = later  # the server left running past midnight
    en = written(later, "en")
    assert built == [TODAY, later]
    found = _TODAY_LINE.search(en)
    assert found is not None and found.group(1) == later.isoformat()
