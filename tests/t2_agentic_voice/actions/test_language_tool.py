"""The talker's `switch_language` tool (actions/language_tool.py; D-038's amendment): the code
asked for mapped to the agent's tag, in any case, a language the agent lacks a `ToolError` to the
talker; given to the talker only under `stt.live_language = "detected"` with two languages or
more, never beside a team's own tool of that name, and never by default (GP-18); and
`switched_to` reading the last switch that succeeded, nothing else."""

from __future__ import annotations

import asyncio
import json

import pytest
from t2_agentic_voice.actions.agent_tools import talker_tools
from t2_agentic_voice.actions.language_tool import (
    NAME,
    language_tool,
    switched_to,
    with_language_tool,
)
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, ToolResult, tool
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

from tests.t2_agentic_voice.agent.chat_support import ENGLISH, MSA, SAUDI, agent
from tests.t2_agentic_voice.fakes import FakeClock

CTX = CallContext(caller=Caller(subject="made-up-subject"), call_id="call-1", language="ar-SA")
DETECTED = VoiceSettings(env="test", stt=SttSettings(live_language="detected"))


def _call(code: str, call_id: str = "c-1", name: str = NAME) -> ToolCallRequest:
    return ToolCallRequest(id=call_id, name=name, arguments=json.dumps({"language": code}))


def _switch(code: str, *languages: Language) -> ToolResult:
    made = language_tool(languages or (SAUDI, ENGLISH))
    return asyncio.run(ToolRunner([made]).run(_call(code), CTX, clock=FakeClock()))


@pytest.mark.parametrize(
    ("code", "tag"), [("en", "en"), ("EN", "en"), ("ar", "ar-SA"), ("ar-SA", "ar-SA")]
)
def test_the_code_asked_for_gives_the_agents_tag(code: str, tag: str) -> None:
    assert _switch(code) == ToolResult(data={"language": tag})


def test_the_first_of_two_arabic_languages_answers_ar() -> None:
    assert _switch("ar", MSA, SAUDI, ENGLISH) == ToolResult(data={"language": "ar"})


def test_a_language_the_agent_lacks_is_a_tool_error_naming_the_ones_it_speaks() -> None:
    result = _switch("fr")
    assert not result.ok and result.failure == "tool_error"
    assert result.data == {"error": "This agent speaks only these languages: ar, en."}


def test_a_code_of_no_language_shape_is_refused_before_the_tool_runs() -> None:
    result = _switch("english please")
    assert not result.ok and result.failure != "tool_error"


def test_the_talker_gets_it_only_under_detected_with_two_languages() -> None:
    two = agent(languages=(SAUDI, ENGLISH))
    assert [t.name for t in talker_tools(two, DETECTED)] == [NAME]
    assert talker_tools(two, VoiceSettings(env="test")) == ()  # the default: GP-18
    assert talker_tools(agent(languages=(ENGLISH,)), DETECTED) == ()
    auto = VoiceSettings(env="test", stt=SttSettings(live_language="auto"))
    assert talker_tools(two, auto) == ()


def test_a_teams_own_tool_of_that_name_is_kept_alone() -> None:
    @tool(description="A team's own switch.", name=NAME)
    def own(language: str) -> str:
        return language

    assert with_language_tool((own,), (SAUDI, ENGLISH), DETECTED) == (own,)


def test_switched_to_reads_the_last_switch_that_succeeded() -> None:
    calls = [_call("en", "c-1"), _call("ar", "c-2")]
    results = {"c-1": ToolResult(data={"language": "en"}), "c-2": ToolResult(data={"x": 1})}
    assert switched_to(calls, results) == "en"
    results["c-2"] = ToolResult(data={"language": "ar-SA"})
    assert switched_to(calls, results) == "ar-SA"


@pytest.mark.parametrize(
    "result",
    [
        ToolResult(data={"error": "no"}, ok=False, failure="tool_error"),
        ToolResult(data={"language": "fr"}),
        ToolResult(data="en"),
    ],
)
def test_switched_to_ignores_a_failed_or_odd_result(result: ToolResult) -> None:
    assert switched_to([_call("en")], {"c-1": result}) is None


def test_switched_to_ignores_another_tools_result() -> None:
    other = _call("en", name="search_knowledge")
    assert switched_to([other], {"c-1": ToolResult(data={"language": "en"})}) is None
    assert switched_to([_call("en")], {}) is None
