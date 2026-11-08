"""The seam between runs K and S and `TextCall` (talker_call.py), on a fake call with
`TextCall`'s signature: a variant said once in a call held on the system clock, a scenario's
turns each said when it says (the turn before a correction still being answered), every turn
read once the last reply has played, a moment the call never reaches given up on, and each
turn's data read into what a run keeps, its language from its own words."""

from __future__ import annotations

import asyncio
import inspect

import pytest
from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_call import CHARS_PER_SECOND_K, ask, heard, play
from ole5_voice.evals.talker_data import (
    Clause,
    HeardTurn,
    ToolUse,
    in_language,
    registers_held,
    script_of,
)
from t2_agentic_voice import Card, LlmSettings, VoiceSettings
from t2_agentic_voice.evals import BlockedClause, HeardClause, TextCall, TextToolCall
from t2_agentic_voice.ports import Usage

from tests.ole5_voice.evals.talker_fakes import (
    TOOL,
    Calls,
    FakeChat,
    FakeKnowledgeBase,
    FakeTurn,
    Scripted,
    agent,
)

SETTINGS = VoiceSettings(env="test", llm=LlmSettings(model="openai/gpt-oss-20b"))


def test_a_turns_data_is_read_as_a_run_keeps_it() -> None:
    turn = FakeTurn(
        fate="cut",
        clauses=(
            HeardClause(text="One.", language="ar-SA", fate="played", played_fraction=1.0),
            HeardClause(text="Two.", language="ar-SA", fate="cut", played_fraction=0.5),
            HeardClause(
                text="Wait.", language="ar-SA", fate="played", played_fraction=1.0, phrase=True
            ),
        ),
        tool_calls=(
            TextToolCall(
                call_id="c", tool=TOOL, arguments={"query": "q"}, outcome="cancelled", ms=3.0
            ),
        ),
        cards=(Card(title="T", steps=("a", "b"), source="S"),),
        blocked=(BlockedClause(text="x", language="en", unsupported=("123",)),),
        first_token_s=0.1,
        first_clause_s=0.3,
        model_requests=2,
        usage=Usage(input_tokens=50, output_tokens=7),
    )
    kept = heard(turn)
    assert kept.said == "One. Two." and kept.words == 2 and kept.written_in("en")
    assert kept.tools[0].arguments == {"query": "q"} and kept.tools[0].outcome == "cancelled"
    assert kept.searched(TOOL) and not kept.searched("other")
    assert kept.cards[0].steps == ("a", "b") and kept.blocked == 1
    assert (kept.input_tokens, kept.output_tokens, kept.model_requests) == (50, 7, 2)
    assert "Two. [cut, 50% of it heard]" in kept.heard_text() and "Wait." not in kept.heard_text()


def test_a_replys_language_is_read_from_its_own_words() -> None:
    assert script_of("افتح صفحة Settings واضغط Reset ثم احفظ") == "ar"  # product terms in it
    assert script_of("Open 'المراسلات' and press save.") == "en"  # a screen's label in it
    assert script_of("اضغط Save") is None and script_of("1, 2 ...") is None
    assert script_of("使用 设置") == "other"

    def turn(*texts: str, phrase: str = "") -> HeardTurn:
        said = [(text, False) for text in texts] + ([(phrase, True)] if phrase else [])
        return HeardTurn(
            fate="answered",
            clauses=tuple(
                Clause(text=t, language="ar-SA", fate="played", played_fraction=1, phrase=p)
                for t, p in said
            ),
        )

    # Every clause with a script in it, no word in another script, fixed phrases aside.
    assert turn("افتح الإعدادات.", "ثم اضغط حفظ.", phrase="One moment.").written_in("ar")
    assert not turn("افتح الإعدادات.", "Then press save.").written_in("ar")
    assert not turn("افتح 设置 الإعدادات.").written_in("ar")
    assert not turn().written_in("en") and not turn("اضغط Save").written_in("ar")
    # Held to a tag: its script, and held to Arabic, its register as the judge read it, by the
    # owner's Q24 (2026-11-08, "Either register right"): an MSA label's reply MSA; a Saudi or
    # mixed label's Saudi when the caller's words hold a dialect form, either when they hold
    # none, never no Arabic.
    reply = turn("افتح الإعدادات.")
    assert in_language(reply, "ar", "msa", words="كيف أفتح الإعدادات؟")
    assert not in_language(reply, "ar", "saudi", words="كيف أفتح الإعدادات؟")
    assert not in_language(reply, "ar-SA", "msa", words="وين الإعدادات؟")
    assert in_language(reply, "ar-SA", "saudi", words="وين الإعدادات؟")
    assert in_language(reply, "ar-SA", "msa", words="كيف أفتح الإعدادات؟")
    assert in_language(reply, "ar-SA", "saudi", words="كيف أفتح الإعدادات؟")
    assert not in_language(reply, "ar-SA", "none", words="كيف أفتح الإعدادات؟")
    assert not in_language(reply, "ar-SA", None, words="كيف أفتح الإعدادات؟")
    assert in_language(turn("Open the settings."), "en", None, words="How do I open it?")
    assert registers_held("ar-SA", "كيف أفتح الإعدادات؟") == {"saudi", "msa"}
    assert registers_held("ar-SA", "وين الإعدادات؟") == registers_held("ar-SA", "OK") == {"saudi"}
    assert registers_held("ar", "وين الإعدادات؟") == {"msa"}  # the label's, whatever the words
    assert registers_held("en", "How?") == {"none"}


def test_a_variant_is_read_once_its_reply_has_played() -> None:
    calls, chat = Calls(), FakeChat()
    calls.kb = FakeKnowledgeBase()
    calls.script["hello"] = Scripted(violations=1, search=False)
    held = asyncio.run(
        ask(agent(calls.kb), chat, SETTINGS, words="hello", language="ar", call=calls)
    )
    assert calls.said == [("hello", None, None, "ar")]
    assert chat.requests[0].model == "openai/gpt-oss-20b"
    # TextCall's `user` returns once the reply is written, still unplayed: the call goes on
    # until it has played, so its words and the guard's violations are the caller's.
    (turn,) = held.turns
    assert turn.fate == "answered" and {clause.fate for clause in turn.clauses} == {"played"}
    assert turn.said == "A short made-up answer." and turn.words == 4
    assert held.violations == 1 and calls.advanced
    # Played fast, so a variant never waits out its reply's speech on the wall clock.
    assert calls.given[0]["chars_per_second"] == CHARS_PER_SECOND_K


def test_a_reply_that_never_ends_is_given_up_on() -> None:
    calls = Calls()
    calls.kb = FakeKnowledgeBase()
    calls.script["hello"] = Scripted(never_ends=True, search=False)
    with pytest.raises(TimeoutError):
        asyncio.run(
            ask(
                agent(calls.kb),
                FakeChat(),
                SETTINGS,
                words="hello",
                language="en",
                call=calls,
                limit_s=0.05,
            )
        )


def test_a_scenarios_turns_are_each_said_when_they_say() -> None:
    calls = Calls()
    calls.kb = FakeKnowledgeBase()
    turns = [
        ScriptTurn(says="first", search=True),
        ScriptTurn(says="correction", when="tool_running", search=True),
        ScriptTurn(says="stop", when="agent_speaking", after_s=0.5, cuts_reply=True),
        ScriptTurn(says="go on", search=False),
    ]
    calls.script["stop"] = Scripted(cuts_earlier=True, search=False, said="Okay.")
    calls.script["go on"] = Scripted(search=False, violations=1)
    held = asyncio.run(
        play(agent(calls.kb), FakeChat(), SETTINGS, turns=turns, language="ar-SA", call=calls)
    )
    assert [said[:3] for said in calls.said] == [
        ("first", None, None),
        ("correction", None, "tool_running"),
        ("stop", "agent_speaking", None),
        ("go on", None, None),
    ]
    # The correction was said while the first turn's search ran, which stopped its reply.
    assert held.turns[0].fate == "rolled_back" and held.turns[0].tools[0].outcome == "ok"
    assert held.turns[1].fate == "cut" and calls.advanced[0] == 0.5
    # The last turn is read once its reply has played, and its violation with it.
    assert held.turns[3].fate == "answered" and held.turns[3].words == 4
    assert held.violations == 1
    # A scenario's replies play at TextCall's own pace, so words can be said over them.
    assert "chars_per_second" not in calls.given[0]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (Scripted(search=False), ScriptTurn(says="b", when="tool_running", search=True)),
        (
            Scripted(search=False, said="Hi."),
            ScriptTurn(says="b", when="agent_speaking", after_s=5),
        ),
    ],
)
def test_a_moment_the_call_never_reaches_is_given_up_on(
    first: Scripted, second: ScriptTurn
) -> None:
    calls = Calls()
    calls.kb = FakeKnowledgeBase()
    calls.script["a"] = first
    turns = [ScriptTurn(says="a", search=False), second]
    # TextCall's waits for a turn's moment raise AssertionError; a run reads that as stuck.
    with pytest.raises(TimeoutError, match="never came"):
        asyncio.run(
            play(agent(calls.kb), FakeChat(), SETTINGS, turns=turns, language="en", call=calls)
        )


def test_the_default_call_is_the_librarys_text_call() -> None:
    assert inspect.signature(ask).parameters["call"].default is TextCall
    assert inspect.signature(play).parameters["call"].default is TextCall


def _timed(first: float | None, *spans: tuple[float | None, float | None]) -> HeardTurn:
    tools = tuple(
        ToolUse(tool=TOOL, outcome="ok" if ms is not None else "running", ms=ms, began_s=began)
        for began, ms in spans
    )
    return HeardTurn(fate="answered", tools=tools, first_clause_s=first)


def test_the_models_own_time_to_the_first_clause_takes_its_tools_time_out() -> None:
    """Q15: the time to the first clause less each tool's time from its start to its end, the
    tools that ended before the first clause, time two ran at once counted once."""
    assert _timed(0.8).own_first_clause_s == pytest.approx(0.8)  # no tool
    assert _timed(1.4, (0.2, 700.0)).own_first_clause_s == pytest.approx(0.7)
    both = _timed(1.5, (0.2, 700.0), (0.5, 600.0))  # 0.2 to 0.9 and 0.5 to 1.1: 0.9 s ran
    assert both.own_first_clause_s == pytest.approx(0.6)
    said_first = _timed(0.4, (0.6, 800.0))  # it spoke first, then searched
    assert said_first.own_first_clause_s == pytest.approx(0.4)
    assert _timed(1.0, (0.3, None)).own_first_clause_s == pytest.approx(1.0)  # still running
    assert _timed(1.4, (None, 700.0)).own_first_clause_s is None  # its start unknown
    assert _timed(None, (0.2, 700.0)).own_first_clause_s is None


def test_a_tools_start_reaches_what_a_run_keeps() -> None:
    turn = FakeTurn(
        fate="answered",
        clauses=(),
        tool_calls=(TextToolCall(call_id="c", tool=TOOL, outcome="ok", ms=500.0, began_s=0.25),),
        cards=(),
        blocked=(),
        first_token_s=0.1,
        first_clause_s=1.0,
        model_requests=2,
        usage=Usage(input_tokens=0, output_tokens=0),
    )
    kept = heard(turn)
    assert kept.tools[0].began_s == 0.25 and kept.own_first_clause_s == pytest.approx(0.5)
