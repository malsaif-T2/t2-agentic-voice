"""A progress line's wordings (domain/declared_phrases.py's `ProgressLine`; plan 010's 1.15): a
language gives a line as one text, as before, or as a few wordings, kept as a tuple, each a fixed
phrase of its own (domain/fixed_phrases.py); a list the declaration cannot say in turn is
refused naming `progress`, never the value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.declared_phrases import MAX_WORDINGS, wordings
from t2_agentic_voice.domain.fixed_phrases import FixedPhrase, fixed_phrases

SEARCHING = ("Let me check.", "Checking now.", "Looking that up.")


@dataclass(frozen=True)
class MadeUpTool:
    """The smallest tool shape the declaration reads (`DeclaredTool`)."""

    name: str
    description: str = "Search the help articles."
    progress: str | None = None


def test_one_text_stays_one_text_and_a_list_of_wordings_becomes_a_tuple() -> None:
    one = Language.english(greeting="Hi", progress={"searching": "One moment."})
    several = Language.english(greeting="Hi", progress={"searching": list(SEARCHING)})
    assert one.progress["searching"] == "One moment."
    assert several.progress["searching"] == SEARCHING
    assert wordings(one.progress["searching"]) == ("One moment.",)
    assert wordings(several.progress["searching"]) == SEARCHING


def test_a_language_with_wordings_round_trips_through_json() -> None:
    progress = {"searching": ("أشوف لك.", "أدور لك.")}
    several = Language.saudi_arabic(greeting="هلا", progress=progress)
    assert Language.model_validate_json(several.model_dump_json()) == several


@pytest.mark.parametrize(
    "line",
    [
        [],
        ["One."] * 2,
        [f"Line {n}." for n in range(MAX_WORDINGS + 1)],
        ["One.", 2],
        ["One.", "Secret\tline"],
        {"one": "One."},
    ],
)
def test_wordings_it_cannot_say_in_turn_are_refused_naming_progress(line: Any) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Language.english(greeting="Hi", progress={"searching": line})
    assert raised.value.details == {"field": "progress"}
    assert "Secret" not in str(raised.value)


def test_each_wording_of_a_line_a_tool_names_is_a_fixed_phrase_in_its_order() -> None:
    english = Language.english(greeting="Hi", progress={"searching": SEARCHING})
    saudi = Language.saudi_arabic(greeting="هلا", progress={"searching": "أشوف لك."})
    agent = VoiceAgent(
        name="branch-helper",
        languages=[english, saudi],
        tools=[MadeUpTool("search_help", progress="searching")],
    )
    progress = [phrase for phrase in fixed_phrases(agent) if phrase.kind == "progress"]
    assert progress == [
        *(FixedPhrase(text=t, language="en", kind="progress", key="searching") for t in SEARCHING),
        FixedPhrase(text="أشوف لك.", language="ar-SA", kind="progress", key="searching"),
    ]
