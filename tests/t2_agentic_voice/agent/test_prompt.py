"""The talker's system prompt (agent/prompt.py; the design's 3.1): the library's rules, the
date, the team's instructions for the reply language, then the language section, in that order
and nothing else; the rules short; `render_prompt` the same prompt today."""

from __future__ import annotations

from datetime import date

import pytest
from t2_agentic_voice.agent.prompt import (
    CUT_MARK,
    DATA_TAG,
    LANGUAGE_SECTIONS,
    RULES,
    compose_prompt,
    render_prompt,
)
from t2_agentic_voice.core.clock import SYSTEM_CLOCK
from t2_agentic_voice.domain.declaration import VoiceAgent

from tests.t2_agentic_voice.agent.chat_support import ENGLISH, SAUDI, agent

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
        "on the screen",
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


def test_the_rules_name_the_screen_only_when_a_tool_result_shows_the_steps() -> None:
    """The live smoke of 2026-11-07: the rule said the full steps were on the screen whatever
    was shown, and the caller was told of steps no card showed. Its one line names the screen
    only as the condition of a result's `shown_on_screen` (actions/knowledge.py), never
    otherwise."""
    [line] = [line for line in RULES.splitlines() if "on the screen" in line]
    assert line.startswith("- Never read steps out one by one: give the gist or the first")
    assert "on the screen only when a tool result's shown_on_screen holds them" in line
    assert line.endswith("; otherwise never mention the screen.")


def test_the_language_section_asks_for_the_saudi_register_unless_the_caller_speaks_msa() -> None:
    assert LANGUAGE_SECTIONS["ar-SA"] == LANGUAGE_SECTIONS["ar"]
    assert (
        "Saudi dialect, unless the caller speaks Modern Standard Arabic" in LANGUAGE_SECTIONS["ar"]
    )
    assert LANGUAGE_SECTIONS["en"].startswith("Reply in English.")


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
