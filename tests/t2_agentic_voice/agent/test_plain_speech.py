"""Plain speech (agent/plain_speech.py, under `guard.plain_speech`; D-111, after the owner's
English call of 2026-11-17, whose reply of markdown, zero-width spaces and a broken note was said
whole, and whose two questions joined by a run of dots were both said).

- **The rules**: a run of dots after a sentence's mark is taken out, and one after a word made
  one ellipsis, however the text is cut into pieces; a clause is not speech when under half of
  its characters, spaces aside, are letters, marks or digits, or it holds a bracket, a brace or
  a tag's opening, Arabic harakat counted as letters; the invisible and markdown marks are taken
  out of what is said.
- **In the talker**: a request that is not speech and said nothing is sent once more, and its
  retry said cleanly; a retry that is not speech either says nothing, and no request follows;
  a dot run's second question is dropped by the question limit; a clause that is not speech
  after one said ends its request, with no retry and no tool of it run; the marks are taken out
  of a clause said; with the setting off, each is said as written (GP-18).
Every text is made up but for the owner's reply, the diagnosis' quoted junk."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.plain_speech import DotRuns, is_speech, spoken
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import Done, TextDelta
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.evals import ScriptedLLM, TextCall, TextTurn

from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    Step,
    call,
    kinds,
    reply,
    said,
    talker,
)
from tests.t2_agentic_voice.testing.text_call_support import AGENT

ELLIPSIS = "\u2026"
ZWSP, JOINER, BOM = "\u200b", "\u2060", "\ufeff"
# The owner's turn 6, as the diagnosis quotes it: markdown bold around a zero-width space, two
# more, an ellipsis, an em dash, and a broken copy of the history's cut mark.
JUNK = f"The **{ZWSP}** {ZWSP} {ZWSP} {ELLIPSIS} \u2014 The ... This {ELLIPSIS} [cut ..."
TWO_QUESTIONS = f"When would you like to come back?{'.' * 21}Could you tell me the day?"
TURN = TalkerTurn(turn_id=1, words="I want to fly to a made-up city.", language="en")


def _runs(text: str, size: int) -> str:
    dots = DotRuns()
    return "".join(dots.feed(text[at : at + size]) for at in range(0, len(text), size)) + (
        dots.close()
    )


@pytest.mark.parametrize("size", [1, 2, 3, 10_000])
@pytest.mark.parametrize(
    ("text", "made"),
    [
        ("back?.....Could", "back?Could"),
        (f"back?{ELLIPSIS}{ELLIPSIS}Could", "back?Could"),
        ("بالضبط؟....وش", "بالضبط؟وش"),
        ("Sunday.........Which", f"Sunday{ELLIPSIS}Which"),
        ("So... what now", f"So{ELLIPSIS} what now"),
        ("the end....", f"the end{ELLIPSIS}"),
        ("Done.", "Done."),  # a single mark is none of a run
        (f"Well{ELLIPSIS} yes", f"Well{ELLIPSIS} yes"),
        ("3.5 and t2.example", "3.5 and t2.example"),
        ("The ... This", "The ... This"),  # after a space: neither a mark nor a word
    ],
)
def test_a_dot_run_is_made_one_mark_however_the_text_is_cut(
    text: str, made: str, size: int
) -> None:
    assert _runs(text, size) == made
    off = DotRuns(on=False)
    assert off.feed(text) + off.close() == text


def test_two_questions_joined_by_a_dot_run_are_two_sentences_once_made_one_mark() -> None:
    assert len(split_clauses(TWO_QUESTIONS, max_chars=None)) == 1  # as the owner heard it
    assert split_clauses(_runs(TWO_QUESTIONS, 10_000), max_chars=None) == (
        "When would you like to come back?",
        "Could you tell me the day?",
    )


@pytest.mark.parametrize(
    "clause",
    [
        *(split_clauses(JUNK, max_chars=None)[at] for at in (0, 1, 3)),  # the third is "This ..."
        '{"cabin": "economy", "travelers": 1}',
        "<action>",
        "see [note]",
        "** ** --",
        "... !! ?",
    ],
)
def test_a_clause_mostly_not_words_or_holding_a_bracket_is_not_speech(clause: str) -> None:
    assert not is_speech(clause)


@pytest.mark.parametrize(
    "clause",
    [
        "عذرًا،",  # 'udhran: sorry, with tanween
        "(جدة،",  # (jidda: Jeddah, a parenthesis's opening
        f"للـ{ZWSP}شخص",  # lil-shakhS: for the person, a zero-width space inside
        "The 09:10 is the cheapest, at 2,450 SAR.",
        "Riyadh -> London.",
        "OK.",
        "١٢:٣٠",
    ],
)
def test_real_clauses_are_speech(clause: str) -> None:
    assert is_speech(clause)


def test_the_invisible_and_markdown_marks_are_taken_out_of_what_is_said() -> None:
    assert spoken(f"**Sure**, the {ZWSP}flight is at `9:10`{JOINER}.{BOM}") == (
        "Sure, the flight is at 9:10."
    )
    assert spoken("Plain words.") == "Plain words."


@tool(description="Do a made-up quick thing.")
async def quick() -> dict[str, bool]:
    return {"ok": True}


def _settings(on: bool, *, most: int = 3) -> VoiceSettings:
    return VoiceSettings(
        env="test",
        guard=GuardSettings(plain_speech=on),
        llm=LlmSettings(max_requests_per_turn=most),
    )


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, SpokenClause)]


def test_a_request_that_is_not_speech_is_sent_once_more_and_its_retry_said() -> None:
    model = FakeChat(said(JUNK), said("Which day would you like?"))
    events = reply(talker(model, settings=_settings(True)), TURN)
    assert _spoken(events) == ["Which day would you like?"]
    assert len(model.requests) == 2
    first, retry = model.requests
    assert first.messages[1:] == retry.messages[1:]  # the same request, nothing of it kept
    assert first.messages[0].content != retry.messages[0].content  # a new first line
    assert kinds(events).count("ModelReplied") == 2


def test_a_retry_that_is_not_speech_either_says_nothing_and_no_request_follows() -> None:
    model = FakeChat(said(JUNK), said('{"note": "made up"}'), said("Never asked for."))
    events = reply(talker(model, settings=_settings(True, most=4)), TURN)
    assert _spoken(events) == [] and kinds(events)[-1] == "ReplyDone"
    assert len(model.requests) == 2  # once more, never twice


def test_the_last_request_that_is_not_speech_is_never_sent_again() -> None:
    first: list[Step] = [TextDelta(text="One moment. "), call("quick")]
    first.append(Done(finish_reason="tool_calls"))
    model = FakeChat(first, said(JUNK), said("Never asked for."))
    events = reply(talker(model, quick, settings=_settings(True, most=2)), TURN)
    assert _spoken(events) == ["One moment."] and len(model.requests) == 2


def test_a_dot_runs_second_question_is_dropped_by_the_question_limit() -> None:
    pieces = ("When would you like to come back?...", "....Could you tell me the day?")
    events = reply(talker(FakeChat(said(*pieces)), settings=_settings(True)), TURN)
    assert _spoken(events) == ["When would you like to come back?"]
    off = reply(talker(FakeChat(said(*pieces)), settings=_settings(False)), TURN)
    assert len(_spoken(off)) == 1 and _spoken(off)[0].endswith("the day?")  # both said, as before


def test_not_speech_after_a_clause_said_ends_its_request_with_no_retry_nor_tool() -> None:
    steps: list[Step] = [TextDelta(text="Fine, one moment. "), TextDelta(text="[cut ... ")]
    steps.append(call("quick"))
    model = FakeChat([*steps, Done(finish_reason="tool_calls")], said("Never asked for."))
    events = reply(talker(model, quick, settings=_settings(True)), TURN)
    assert _spoken(events) == ["Fine, one moment."]
    assert "ToolBegan" not in kinds(events) and len(model.requests) == 1


def test_a_request_not_speech_runs_none_of_its_tools_and_its_retry_runs_them() -> None:
    junk: list[Step] = [TextDelta(text=JUNK), call("quick"), Done(finish_reason="tool_calls")]
    again: list[Step] = [call("quick", call_id="c-2"), Done(finish_reason="tool_calls")]
    model = FakeChat(junk, again, said("Done, it is set."))
    events = reply(talker(model, quick, settings=_settings(True)), TURN)
    assert kinds(events).count("ToolEnded") == 1  # the retry's, never the junk's
    assert _spoken(events) == ["Done, it is set."]


def test_the_marks_are_taken_out_of_a_clause_said() -> None:
    text = f"**Sure**, the {ZWSP}flight is at `9:10`."
    events = reply(talker(FakeChat(said(text)), settings=_settings(True)), TURN)
    assert _spoken(events) == ["Sure, the flight is at 9:10."]


def test_with_the_setting_off_each_is_said_as_written() -> None:
    model = FakeChat(said(JUNK), said("Never asked for."))
    events = reply(talker(model, settings=_settings(False)), TURN)
    assert _spoken(events) == list(split_clauses(JUNK, max_chars=None))
    assert len(model.requests) == 1
    text = f"**Sure**, the {ZWSP}flight is at `9:10`."
    events = reply(talker(FakeChat(said(text)), settings=_settings(False)), TURN)
    assert "".join(_spoken(events)).count("*") == 4


@pytest.mark.parametrize("retry", [JUNK, '{"note": "made up"}'], ids=["junk", "json"])
def test_in_a_call_a_retry_not_speech_either_is_heard_as_the_error_notice(retry: str) -> None:
    """The library's talker through the session (`TextCall`): neither request is said, and the
    caller hears the `error` notice once, never the junk nor silence."""
    agent = VoiceAgent(name="plain-test", languages=AGENT.languages, instructions="Answer.")
    llm = ScriptedLLM([ScriptedLLM.reply(JUNK), ScriptedLLM.reply(retry)])

    async def scene() -> TextTurn:
        async with TextCall(agent, llm=llm, language="en", settings=_settings(True)) as call:
            turn = await call.user("I want to fly to a made-up city.")
            await call.advance(10.0)
            return turn

    turn = asyncio.run(scene())
    error = AGENT.languages[0].notices["error"]
    assert [(c.text, c.phrase) for c in turn.clauses] == [(error, True)]
    assert len(llm.requests) == 2
