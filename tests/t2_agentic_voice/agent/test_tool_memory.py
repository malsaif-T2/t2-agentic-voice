"""What a call's talker keeps between turns (agent/tool_calls.py's `Memory`): the tool calls and
results of its last `KEPT_TURNS` turns only, the oldest let go first, and every result's data and
evidence as the guard's evidence."""

from __future__ import annotations

from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.agent.tool_calls import KEPT_TURNS, Memory, framed
from t2_agentic_voice.domain.ports.chat_model import ChatMessage


def test_the_calls_of_the_last_turns_only_are_kept() -> None:
    memory = Memory()
    for turn_id in range(KEPT_TURNS + 2):
        memory.keep(turn_id, [ChatMessage.tool_result(f"c-{turn_id}", "<data>{}</data>")])
    assert sorted(memory.exchanges) == list(range(2, KEPT_TURNS + 2))
    memory.keep(5, [ChatMessage.tool_result("c-5b", "<data>{}</data>")])
    assert len(memory.exchanges[5]) == 2  # a turn's later request adds to its own


def test_a_result_is_kept_as_evidence_and_framed_as_data() -> None:
    memory = Memory()
    result = ToolResult(data={"code": "8841"}, evidence=("passage text 7788",))
    memory.took(result)
    assert memory.evidence == ['{"code": "8841"}', "passage text 7788"]
    assert framed("search_help", result) == '<data tool="search_help">{"code": "8841"}</data>'


def test_a_result_that_succeeded_is_kept_as_evidence_of_the_actions_its_tool_reports_on() -> None:
    """Rule A's evidence (invariant 2): only a `reports_on` tool's result that succeeded."""
    memory = Memory()
    memory.took(ToolResult(data={"number": "7788"}), reports_on=("open_request",))
    memory.took(ToolResult(data={"error": "none"}, ok=False), reports_on=("open_request",))
    memory.took(ToolResult(data={"number": "9911"}))
    assert memory.reports == {"open_request": ['{"number": "7788"}']}
    assert len(memory.evidence) == 3  # rule B's evidence takes them all
