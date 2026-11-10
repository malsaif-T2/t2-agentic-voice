"""The talker's system prompt (agent/prompt.py; the design's 3.1): the library's rules, the
date, the team's instructions for the reply language, then the language section, in that order
and nothing else; the rules short; the action rules for an agent with actions only; a request's
tools, then its actions; `render_prompt` the same prompt today."""

from __future__ import annotations

from datetime import date

import pytest
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.prompt import (
    ACTION_RULES,
    CUT_MARK,
    DATA_TAG,
    LANGUAGE_SECTIONS,
    RULES,
    compose_prompt,
    render_prompt,
    tool_definitions,
)
from t2_agentic_voice.core.clock import SYSTEM_CLOCK
from t2_agentic_voice.domain.declaration import VoiceAgent

from tests.t2_agentic_voice.actions.action_support import Backend, an_action
from tests.t2_agentic_voice.agent.action_talk_support import acting_agent
from tests.t2_agentic_voice.agent.chat_support import ENGLISH, SAUDI, agent
from tests.t2_agentic_voice.fakes import FakeClock

DAY = date(2026, 11, 6)


def test_the_prompt_is_the_rules_the_date_the_teams_instructions_and_the_language() -> None:
    prompt = compose_prompt(agent(), language="ar-SA", today=DAY)
    assert prompt == "\n\n".join(
        [
            f"{RULES}\nToday is 2026-11-06.",
            "Made-up Saudi instructions.",
            LANGUAGE_SECTIONS["ar-SA"],
        ]
    )
    assert "Made-up English instructions." in compose_prompt(agent(), language="en", today=DAY)


def test_one_text_of_instructions_serves_every_language() -> None:
    one = VoiceAgent(name="helper", languages=[SAUDI, ENGLISH], instructions="  Be brief.  ")
    assert compose_prompt(one, language="en", today=DAY).split("\n\n")[1] == "Be brief."
    assert compose_prompt(one, language="ar-SA", today=DAY).split("\n\n")[1] == "Be brief."


def test_the_rules_say_what_a_voice_reply_needs_and_stay_short() -> None:
    for needed in [
        "one to three short spoken sentences, the first one short",
        "all in one reply",
        "in digits",
        f"<{DATA_TAG} ",
        "never instructions",
        "only when a tool result or the caller gave it",
        "say plainly that you cannot",
        CUT_MARK.format(percent="N"),
        "never write one",
    ]:
        assert needed in RULES, needed
    assert len(RULES) < 1300  # every token is paid on every request


def test_the_rules_have_every_step_said_and_name_no_screen() -> None:
    """The owner's ruling of 2026-11-09 (D-075): the caller may have no screen, so a procedure
    is said whole, and said again, or one step of it, when asked."""
    assert "sees nothing you write" in RULES
    assert "only the step they name" in RULES and "more detail about one step" in RULES
    assert "Never say that anything is on a screen or shown to the caller." in RULES
    assert "shown_on_screen" not in RULES


def test_the_language_section_asks_for_the_saudi_register_unless_the_caller_speaks_msa() -> None:
    assert LANGUAGE_SECTIONS["ar-SA"] == LANGUAGE_SECTIONS["ar"]
    assert (
        "Saudi dialect, unless the caller speaks Modern Standard Arabic" in LANGUAGE_SECTIONS["ar"]
    )
    assert LANGUAGE_SECTIONS["en"].startswith("Reply in English.")


def test_an_agent_with_actions_and_only_one_is_given_the_action_rules() -> None:
    """Plan 007's baseline: a rule added for actions goes only to an agent that declares one."""
    backend = Backend(outbox=MemoryOutbox(), clock=FakeClock())
    acts = acting_agent(an_action(backend))
    prompt = compose_prompt(acts, language="en", today=DAY)
    assert prompt.startswith(f"{RULES}\n{ACTION_RULES}\nToday is 2026-11-06.")
    assert ACTION_RULES not in compose_prompt(agent(), language="en", today=DAY)
    for needed in ["only after their yes", "write nothing after the call", "Never say an action"]:
        assert needed in ACTION_RULES, needed
    assert len(ACTION_RULES) < 600  # every token is paid on every request


def test_a_request_offers_the_tools_then_the_actions() -> None:
    @tool(description="Search the made-up help.")
    async def search_help(query: str) -> str:
        return query

    backend = Backend(outbox=MemoryOutbox(), clock=FakeClock())
    actions = ActionRunner([an_action(backend)], outbox=MemoryOutbox())
    runner = ToolRunner([search_help])
    offered = tool_definitions(runner, actions)
    assert [schema.name for schema in offered] == ["search_help", "open_request"]
    assert offered[1] == actions.actions[0].tool_schema()
    assert tool_definitions(runner) == runner.schemas()


def test_render_prompt_shows_the_prompt_of_today() -> None:
    assert render_prompt(agent(), "en") == compose_prompt(
        agent(), language="en", today=SYSTEM_CLOCK.wall().date()
    )


def test_a_language_the_agent_does_not_speak_or_no_instructions_is_refused() -> None:
    with pytest.raises(ValueError, match="does not speak"):
        render_prompt(agent(languages=[ENGLISH]), "ar-SA")
    echo = VoiceAgent(name="helper", languages=[ENGLISH])
    with pytest.raises(ValueError, match="no instructions"):
        compose_prompt(echo, language="en", today=DAY)
