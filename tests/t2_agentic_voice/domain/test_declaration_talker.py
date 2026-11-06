"""The declaration's talker parts (domain/talker_declaration.py, domain/declaration.py; plan 006,
Block 0): `instructions`, `tools`, `vocabulary` and `version` on `VoiceAgent`, and the progress
lines on `Language`, all optional, so an agent declared before the talker loads unchanged and
runs the echo; an agent with instructions runs the talker. Each refusal a ConfigurationError
naming the field, with a FIX line, never the value. And a card (domain/cards.py), and the
output guard's ID rule's shape (domain/guard.py)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.guard import IdVerdict, check_ids
from t2_agentic_voice.domain.talker_declaration import DeclaredTool, Vocabulary

ENGLISH = Language.english(greeting="Hi! How can I help?", progress={"searching": "One moment."})
SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟", progress={"searching": "لحظة"})


@dataclass(frozen=True)
class MadeUpTool:
    """The smallest tool shape the declaration reads (`DeclaredTool`)."""

    name: str
    description: str = "Search the help articles."
    progress: str | None = None


def test_an_agent_declared_before_the_talker_loads_unchanged_and_runs_the_echo() -> None:
    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH])
    assert (agent.instructions, agent.tools, agent.vocabulary, agent.version) == (
        None,
        (),
        Vocabulary(),
        None,
    )
    assert not agent.instructed
    assert dict(Language.english(greeting="Hi").progress) == {}


def test_an_agent_with_instructions_tools_and_a_vocabulary_runs_the_talker() -> None:
    search = MadeUpTool(name="search_help", progress="searching")
    agent = VoiceAgent(
        name="branch-helper",
        languages=[SAUDI, ENGLISH],
        instructions={"ar-SA": "جاوب باختصار.", "en": "Answer briefly."},
        tools=[search],
        vocabulary=Vocabulary(terms=["VPN", "Outlook"]),
        version="2026-11-06.1",
    )
    assert agent.instructed and agent.tools == (search,)
    assert isinstance(search, DeclaredTool)
    assert agent.vocabulary.terms == ("VPN", "Outlook")
    with pytest.raises(TypeError):
        agent.instructions["en"] = "x"  # type: ignore[index]
    one = VoiceAgent(name="helper", languages=[ENGLISH], instructions="Answer briefly.")
    assert one.instructed and one.instructions == "Answer briefly."


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({"instructions": ""}, "instructions"),
        ({"instructions": "   "}, "instructions"),
        ({"instructions": {"en": "x"}}, "instructions"),  # none for ar-SA
        ({"instructions": {"en": "x", "ar-SA": "y", "ar": "z"}}, "instructions"),  # not spoken
        ({"tools": ["search_help"]}, "tools"),  # not a tool
        ({"tools": [MadeUpTool("a"), MadeUpTool("a")]}, "tools"),
        ({"tools": [MadeUpTool("a", progress="waiting")]}, "tools"),  # no language gives it
        ({"vocabulary": ["VPN"]}, "vocabulary"),
        ({"vocabulary": {"terms": [" VPN"]}}, "terms"),
        ({"vocabulary": {"terms": ["V\nPN"]}}, "terms"),
        ({"version": "made up"}, "version"),
        ({"version": ""}, "version"),
    ],
)
def test_a_talker_part_it_cannot_run_with_is_a_configuration_error(
    values: dict[str, Any], field: str
) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        VoiceAgent.model_validate({"name": "helper", "languages": [SAUDI, ENGLISH]} | values)
    assert raised.value.details == {"field": field}


@pytest.mark.parametrize(
    "progress", [{"Searching": "x"}, {"searching": ""}, {"searching": "one\nmoment"}, ["x"]]
)
def test_a_progress_line_is_a_lowercase_key_to_a_phrase(progress: Any) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Language.english(greeting="Hi", progress=progress)
    assert raised.value.details == {"field": "progress"}


def test_a_vocabulary_fails_as_the_declaration_does_and_never_repeats_a_value() -> None:
    with pytest.raises(ConfigurationError, match="The vocabulary cannot run") as raised:
        Vocabulary(terms=["Secret\tterm"])
    assert "Secret" not in str(raised.value) and raised.value.details == {"field": "terms"}
    with pytest.raises(ConfigurationError, match=r"takes `terms`\."):
        Vocabulary.model_validate({"words": []})
    with pytest.raises(ConfigurationError) as raised:
        VoiceAgent.model_validate(
            {"name": "helper", "languages": [ENGLISH], "instructions": {"en": "", "fr": "Secret"}}
        )
    assert "Secret" not in str(raised.value)


def test_a_card_holds_a_title_its_steps_and_its_source() -> None:
    card = Card(title="Reset a password", steps=("Open Settings", "Press Reset"), source="Help")
    assert (card.steps, card.source) == (("Open Settings", "Press Reset"), "Help")
    for values in [{"title": ""}, {"title": "  "}, {"title": "x", "steps": [""]}, {"x": 1}]:
        with pytest.raises(ValidationError):
            Card.model_validate(values)


def test_the_id_rules_verdict_loads_and_is_given() -> None:
    """Its behaviour: tests/t2_agentic_voice/domain/test_guard.py."""
    assert IdVerdict(passed=False, unsupported=("4521",)).unsupported == ("4521",)
    verdict = check_ids("Your number is 4521.", evidence=(), settings=GuardSettings(), year=2026)
    assert verdict == IdVerdict(passed=False, unsupported=("4521",))
