"""The guide's samples of the talker's kit beyond the quickstart's (docs/guide/concepts.md and
evaluation.md), each a teammate's code on the public API alone, run here so the pages never show
code that does not work: a team's existing sync function wrapped as a tool, the caller's ID
bound in from the join token and a progress line named; a tool's expected failure, which the
talker reads; the knowledge tool over a fake knowledge base, its steps for the talker to say;
and an agent tested with `FunctionLLM`, which answers by what each request holds rather than by
their count. No key and no network: every backend is a made-up one written for the test."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Annotated, Literal

import pytest
from pydantic import Field, JsonValue
from t2_agentic_voice import (
    Caller,
    Language,
    Tool,
    ToolError,
    VoiceAgent,
    from_caller,
    knowledge_tool,
    tool,
)
from t2_agentic_voice.evals import (
    FakeKnowledgeBase,
    FunctionLLM,
    ScriptedLLM,
    ScriptStep,
    TextCall,
    TextTurn,
)
from t2_agentic_voice.ports import ChatRequest, Passage

# A made-up backend: each employee's IT requests, and each printer's status by its asset tag.
REQUESTS = {"u-1": {"open": ["The laptop's screen flickers."], "closed": []}}
PRINTERS = {"LT-00423": "out of toner"}
NO_PRINTER = "no printer has that asset tag"


def list_requests(employee_id: str, status: Literal["open", "closed"] = "open") -> list[str]:
    """The employee's IT requests with `status`: a team's existing function, sync."""
    return REQUESTS.get(employee_id, {}).get(status, [])


my_requests = Tool.from_function(
    list_requests,
    name="my_requests",
    description="List the caller's own IT requests, open or closed.",
    bind={"employee_id": from_caller("subject")},
    timeout_s=3,
    progress="checking",
)


@tool(description="The status of one office printer, by its asset tag.")
async def printer_status(
    asset_tag: Annotated[str, Field(pattern=r"^LT-\d{5}$", description="Such as LT-00423.")],
) -> str:
    status = PRINTERS.get(asset_tag)
    if status is None:
        raise ToolError(NO_PRINTER)
    return status


RESET = Passage(
    id="made-up-reset",
    title="Reset your password",
    text="Open the portal and choose Forgot password. A code comes by text message.",
    steps=("Open the portal.", "Choose Forgot password.", "Enter the code from the message."),
    score=0.82,
    source="The made-up user guide",
)
kb = FakeKnowledgeBase([RESET])
search = knowledge_tool(
    kb,
    description=(
        "Search the portal's user guide. Call it once for any question about using the portal, "
        "with the caller's question in a few words. Do not call it for a greeting or thanks."
    ),
    progress="checking",
)

helpdesk = VoiceAgent(
    name="guide-helpdesk",
    languages=[
        Language.english(
            greeting="Hi, this is the IT helpdesk. How can I help?",
            progress={"checking": "I'm checking that for you."},
        )
    ],
    instructions=(
        "You answer questions about the portal from its user guide, and tell the caller their "
        "own IT requests and a printer's status with your tools."
    ),
    tools=[search, my_requests, printer_status],
)


def test_a_wrapped_function_keeps_its_bound_parameter_out_of_the_talkers_schema() -> None:
    schema = json.loads(json.dumps(dict(my_requests.tool_schema().parameters)))
    assert list(schema["properties"]) == ["status"]
    assert (my_requests.timeout_s, my_requests.progress) == (3, "checking")


def answer(request: ChatRequest) -> Iterable[ScriptStep]:
    """A fake model that searches on the caller's question, then answers from what it found."""
    if request.messages[-1].role == "user":
        return ScriptedLLM.call_tool("search_knowledge", query="reset my password")
    return ScriptedLLM.reply("Choose Forgot password in the portal. The steps are on your screen.")


def test_the_talker_searches_once_and_says_the_answer() -> None:
    kb.searches.clear()  # the fake keeps every search it was asked

    async def scene() -> None:
        async with TextCall(helpdesk, llm=FunctionLLM(answer)) as call:
            turn = await call.user("How do I reset my password?")
            turn.expect.tool_call("search_knowledge", query="reset my password")
            turn.expect.said(contains="Forgot password")
        assert [search.query for search in kb.searches] == ["reset my password"]
        assert call.violations == ()

    asyncio.run(scene())


@pytest.mark.parametrize(
    ("name", "arguments", "outcome", "data"),
    [
        ("my_requests", {}, "ok", ["The laptop's screen flickers."]),
        ("printer_status", {"asset_tag": "LT-99999"}, "failed", {"error": NO_PRINTER}),
    ],
)
def test_a_tool_gives_the_talker_its_result_or_its_error(
    name: str, arguments: dict[str, str], outcome: str, data: JsonValue
) -> None:
    """The caller's ID comes from the join token, never from the talker; a `ToolError`'s
    message reaches the talker, which says what it can."""
    llm = ScriptedLLM([ScriptedLLM.call_tool(name, **arguments), ScriptedLLM.reply("Here it is.")])

    async def scene() -> TextTurn:
        async with TextCall(helpdesk, llm=llm, caller=Caller(subject="u-1")) as call:
            turn = await call.user("What do you have for me?")
            await call.advance(5.0)
            return turn

    turn = asyncio.run(scene())
    assert [call.outcome for call in turn.tool_calls] == [outcome]
    [result] = [message for message in llm.requests[1].messages if message.role == "tool"]
    assert result.content == f'<data tool="{name}">{json.dumps(data)}</data>'
