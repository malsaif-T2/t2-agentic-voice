"""The minimal example's helper (examples/minimal's app.py), on the public API alone: its read
tool, `opening_hours`, answers from its own table and refuses a branch name past its bound
before it runs; the talker, held in text through `TextCall` with `ScriptedLLM`, calls it with
the caller's branch and says the hours it gave, in English and in Saudi Arabic, with nothing
the output guard finds; and no fixed line of the helper holds a word the caller commands with.
No key and no network: the model is the script, and the tool reads no outside system."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

import pytest
from minimal_example.app import HOURS, INSTRUCTIONS, helper, opening_hours
from pydantic import ValidationError
from t2_agentic_voice import Tool, render_prompt
from t2_agentic_voice.evals import ScriptedLLM, TextCall, TextTurn
from t2_agentic_voice.languages import normalize_arabic, provider_text

# A call's language, as the library's declaration takes it, and a word list's primary code.
Tag = Literal["en", "ar-SA"]
Code = Literal["en", "ar"]
# The Saudi caller's question, "mata yaftah far' al-olaya al-yawm?": when does the Olaya branch
# open today? And the reply the script writes, "far' al-olaya yaftah al-yawm min 8 as-subh ila
# 4 al-asr": the Olaya branch opens today from 8 in the morning to 4 in the afternoon.
SAUDI_QUESTION = "متى يفتح فرع العليا اليوم؟"
SAUDI_REPLY = "فرع العليا يفتح اليوم من 8 الصبح إلى 4 العصر."
# "min 8 as-subh": from 8 in the morning.
SAUDI_HOURS = "من 8 الصبح"
# Each language's call: the question, the reply the script writes, and what of it the test
# expects the caller to have heard.
CASES: list[tuple[Tag, str, str, str]] = [
    ("en", "When does the Olaya branch open today?", "Olaya is open 8 am to 4 pm.", "8 am to 4 pm"),
    ("ar-SA", SAUDI_QUESTION, SAUDI_REPLY, SAUDI_HOURS),
]


def test_the_tool_answers_from_its_table_whatever_the_case_and_spaces() -> None:
    assert isinstance(opening_hours, Tool) and opening_hours.name == "opening_hours"
    assert asyncio.run(opening_hours.function(" OLAYA ")) == HOURS["olaya"]
    missing = asyncio.run(opening_hours.function("Diriyah"))
    assert missing == "No branch has that name. The branches are Olaya, Malaz."


def test_the_tool_tells_the_talker_its_bounded_argument_and_refuses_one_past_it() -> None:
    schema = json.loads(json.dumps(dict(opening_hours.tool_schema().parameters)))  # as sent
    branch = schema["properties"]["branch"]
    assert (schema["required"], branch["maxLength"], branch["minLength"]) == (["branch"], 40, 1)
    assert branch["description"] == "The branch's name, such as Olaya."
    assert opening_hours.parameters.model_validate({"branch": "x" * 40})
    for wrong in ({"branch": "x" * 41}, {"branch": ""}, {}, {"branch": "Olaya", "city": "x"}):
        with pytest.raises(ValidationError):
            opening_hours.parameters.model_validate(wrong)


def test_the_helper_runs_the_talker_with_its_instructions_and_its_tool() -> None:
    assert helper.instructed and helper.tools == (opening_hours,)
    assert [language.tag for language in helper.languages] == ["en", "ar-SA"]
    for language in helper.languages:
        assert INSTRUCTIONS in render_prompt(helper, language.tag)


async def _asked(
    tag: Tag, question: str, reply: str
) -> tuple[TextTurn, ScriptedLLM, tuple[str, ...]]:
    """The caller asks `question` in a `tag` call; the script calls the tool, then says
    `reply`. The turn once its reply has played, the model, and the guard's findings."""
    llm = ScriptedLLM(
        [  # one entry per model request: the tool call, then the answer from its result
            ScriptedLLM.call_tool("opening_hours", branch="Olaya"),
            ScriptedLLM.reply(reply),
        ]
    )
    async with TextCall(helper, llm=llm, language=tag) as call:
        turn = await call.user(question)
        await call.advance(10.0)  # the reply plays to its end
        return turn, llm, call.violations


@pytest.mark.parametrize(("tag", "question", "reply", "heard"), CASES)
def test_the_talker_calls_the_tool_and_says_its_answer(
    tag: Tag, question: str, reply: str, heard: str
) -> None:
    turn, llm, violations = asyncio.run(_asked(tag, question, reply))
    turn.expect.tool_call("opening_hours", branch="Olaya")
    turn.expect.said(contains=heard)
    turn.expect.language(tag)
    assert turn.fate == "answered" and violations == ()
    assert [call.outcome for call in turn.tool_calls] == ["ok"]
    assert [clause.fate for clause in turn.clauses] == ["played"]
    # The second request read the tool's result, framed as data, beside the caller's words.
    first, second = llm.requests
    assert [tool.name for tool in first.tools] == ["opening_hours"]
    result = second.messages[-1]
    assert result.role == "tool" and result.tool_call_id == turn.tool_calls[0].call_id
    assert result.content == f'<data tool="opening_hours">{json.dumps(HOURS["olaya"])}</data>'
    assert any(question in message.content for message in second.messages)


def _held(line: str, code: Code) -> list[str]:
    """The words of the helper's stop, wait, repeat and listening lists that `line` holds as
    whole words, compared in the interruption rule's form."""
    words = helper.phrases.words(code)
    listed = [*words.stop, *words.wait, *words.repeat, *words.backchannel]
    form = f" {normalize_arabic(provider_text(line))} "
    return [word for word in listed if f" {normalize_arabic(provider_text(word))} " in form]


def test_no_fixed_line_of_the_helper_holds_a_word_the_caller_commands_with() -> None:
    """Its echo, coming back through the speakers while the helper says it, could otherwise
    stop the helper or make it repeat."""
    for language in helper.languages:
        for line in (language.greeting, *language.progress.values()):
            assert _held(line, language.primary) == [], line
    assert _held("One moment, okay?", "en") == ["one moment", "okay"]  # the check finds them
