"""An agent declares its actions among its tools (the design's 4.3; plan 007, Block 0): each text
of an action in every language the agent speaks (an MSA text beside a Saudi one taken, though
the agent speaks no MSA), a tool's `reports_on` naming one of its own actions, and the settings
the actions read."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel
from t2_agentic_voice.actions.action import Action, action
from t2_agentic_voice.actions.tools import Tool, tool
from t2_agentic_voice.api import providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.talker_declaration import DeclaredAction, DeclaredTool
from t2_agentic_voice.testing import text_watch

ENGLISH = Language.english(greeting="Hi! How can I help?")
SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟")


class Draft(BaseModel):
    summary: str


class Result(BaseModel):
    id: str


def _action(
    *,
    name: str = "open_request",
    read_back: ReadBack | None = None,
    done: Say | None = None,
    claims: Claims | None = None,
    failed: Say | None = None,
) -> Action:
    async def do_it(draft: Draft) -> Result:
        return Result(id="1")

    return action(
        name=name,
        description="Open a made-up request.",
        read_back=read_back
        or ReadBack({"en": ("Open {summary}.", "Send?"), "ar": ("{summary}", "؟")}),
        done=done or Say(en="Done {id}.", ar="تم {id}"),
        claims=claims or Claims({"en": ["I've opened"], "ar": ["فتحت"]}),
        failed=failed,
    )(do_it)


@tool(description="A made-up search.")
async def search() -> str:
    return "x"


def test_an_agent_declares_its_actions_among_its_tools() -> None:
    made = _action()
    assert isinstance(made, DeclaredTool) and isinstance(made, DeclaredAction)
    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[search, made])
    assert agent.tools == (search, made)


def _texts_short_of_arabic() -> dict[str, dict[str, Any]]:
    return {
        "read_back": {"read_back": ReadBack({"en": ("s {summary}", "q")})},
        "done": {"done": Say(en="d {id}")},
        "claims": {"claims": Claims({"en": ["c"]})},
        "failed": {"failed": Say(en="f")},
    }


@pytest.mark.parametrize("field", ["read_back", "done", "claims", "failed"])
def test_every_text_of_an_action_is_given_in_every_language(field: str) -> None:
    short = _action(**_texts_short_of_arabic()[field])
    with pytest.raises(ConfigurationError, match="no text in a language") as caught:
        VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[short])
    assert caught.value.details["field"] == "tools" and "FIX:" in caught.value.message
    assert VoiceAgent(name="english-helper", languages=[ENGLISH], tools=[short]).tools == (short,)


def test_a_text_for_arabic_serves_both_arabic_presets_but_not_the_reverse() -> None:
    both = Language.arabic(greeting="مرحبا")
    made = _action(
        read_back=ReadBack({"ar-SA": ("سعودي {summary}", "؟"), "en": ("e {summary}", "q")}),
        done=Say({"ar-SA": "س {id}", "en": "e {id}"}),
        claims=Claims({"ar-SA": ["ف"], "en": ["c"]}),
    )
    with pytest.raises(ConfigurationError, match="no text in a language"):
        VoiceAgent(name="branch-helper", languages=[both], tools=[made])
    assert VoiceAgent(name="saudi-helper", languages=[SAUDI], tools=[made]).tools


def test_an_msa_text_beside_the_saudi_one_is_taken_by_an_agent_that_speaks_no_msa() -> None:
    """An `ar` text is the MSA its `ar-SA` agent says to a caller who speaks MSA, never a
    language the agent must declare."""
    made = _action(
        read_back=ReadBack(
            {
                "ar-SA": ("سعودي {summary}", "؟"),
                "ar": ("فصيح {summary}", "؟"),
                "en": ("e {summary}", "q"),
            }
        ),
        done=Say({"ar-SA": "س {id}", "ar": "ف {id}", "en": "e {id}"}),
        claims=Claims({"ar-SA": ["ف"], "en": ["c"]}),
    )
    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[made])
    assert agent.tools == (made,) and [language.tag for language in agent.languages] == [
        "en",
        "ar-SA",
    ]


def test_a_tool_may_report_only_on_its_agents_own_actions() -> None:
    made = _action()

    @tool(description="A made-up status.", reports_on=["open_request"])
    async def status() -> str:
        return "x"

    @tool(description="Another.", reports_on=["never_declared"])
    async def bad() -> str:
        return "x"

    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[status, made])
    assert agent.tools == (status, made)
    with pytest.raises(ConfigurationError, match="does not declare") as caught:
        VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[bad, made])
    assert "FIX:" in caught.value.message


def test_an_action_is_not_a_tool_the_runner_runs_and_nothing_else_is_taken_for_one() -> None:
    @dataclass(frozen=True)
    class Stranger:
        name: str = "stranger"
        description: str = "x"
        progress: str | None = None

    made = _action()
    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[search, made])
    for module in (providers, text_watch):
        assert module.tools_of(agent) == (search,)
        assert all(isinstance(each, Tool) for each in module.tools_of(agent))
    other = VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[Stranger()])
    for module in (providers, text_watch):
        with pytest.raises(ConfigurationError):
            module.tools_of(other)


def test_the_settings_an_action_reads_default_to_adding_nothing() -> None:
    settings = VoiceSettings(env="test")
    assert dict(settings.words.yes) == {} and dict(settings.words.send) == {}
    assert dict(settings.guard.claims) == {}
    assert settings.limits.actions_per_caller_per_day == 20
    filled = VoiceSettings.model_validate({"env": "test", "words": {"send": {"en": ["ship it"]}}})
    assert filled.words.send["en"] == ("ship it",)
