"""`TextCall` (testing/text_call.py): the real session and its talker held in text on a virtual
clock: a turn's reply as the caller hears it, its tool calls, cards, blocked clauses, times,
requests and usage; a turn said over the reply playing, or while a search runs; the client's Stop;
the guard's checks of the call; an echo agent's call; and what it refuses. The talker is the tests'
scripted one (text_call_support.py), but where a fake model's clock is tested: the library's talker
on a `ScriptedLLM`, whose pauses run on each call's own clock, and whose script, once it has run
out, fails the test."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.actions.knowledge import knowledge_tool
from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ReplyDone,
    ShownCard,
    SpokenClause,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.guard import IdVerdict
from t2_agentic_voice.domain.ports.chat_model import Done, ToolCallRequest
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.evals import (
    FakeKnowledgeBase,
    Pause,
    ScriptedLLM,
    ScriptExhaustedError,
    TextCall,
    TextTurn,
)
from t2_agentic_voice.testing import text_checks

from tests.t2_agentic_voice.testing.text_call_support import (
    AGENT,
    NoModel,
    Ran,
    ScriptedCall,
    Step,
    Work,
    answer,
)

SEARCH = ToolCallRequest(id="t-1", name="search_help", arguments='{"query": "password"}')
CARD = Card(title="Reset a password", steps=("Open Settings.", "Press Reset."))


def _reset(turn: TalkerTurn) -> list[Step]:
    if turn.turn_id == 0:
        return [
            ToolBegan(call_id="t-1", tool="search_help"),
            Ran(SEARCH, ToolResult(data="passages", card=CARD, evidence=("Open Settings.",))),
            ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=120.0),
            ShownCard(card=CARD),
            *answer("Open Settings, then press Reset.", "Anything else?"),
        ]
    return answer("Made-up answer.")


def test_a_turn_is_answered_by_the_real_session_and_read_as_the_caller_heard_it() -> None:
    async def scene() -> TextTurn:
        async with ScriptedCall(_reset) as call:
            turn = await call.user("How do I reset my password?")
            assert turn.fate == "pending" and turn.clauses[0].fate == "unplayed"  # still to play
            turn.expect.said(contains="Open Settings")
            await call.advance(10.0)
            return turn

    turn = asyncio.run(scene())
    assert turn.fate == "answered"
    assert [(c.text, c.fate, c.language, c.phrase) for c in turn.clauses] == [
        ("Open Settings, then press Reset.", "played", "en", False),
        ("Anything else?", "played", "en", False),
    ]
    turn.expect.tool_call("search_help", query="password")
    turn.expect.language("en")
    (call,) = turn.tool_calls
    assert (call.outcome, call.ms, dict(call.arguments)) == ("ok", 120.0, {"query": "password"})
    assert turn.cards == (CARD,) and turn.blocked == ()
    assert (turn.model_requests, turn.usage.input_tokens, turn.usage.output_tokens) == (1, 100, 20)
    assert turn.first_clause_s == 0.0 and turn.first_token_s == pytest.approx(0.2)
    with pytest.raises(AssertionError, match="made no call of archive"):
        turn.expect.tool_call("archive")
    with pytest.raises(AssertionError, match="said"):
        turn.expect.said(contains="Archive")
    with pytest.raises(AssertionError, match="not ar-SA"):
        turn.expect.language("ar-SA")
    with pytest.raises(AssertionError, match="blocked no clause"):
        turn.expect.blocked()
    with pytest.raises(AssertionError, match="cancelled no search_help"):
        turn.expect.cancelled("search_help")


def test_a_stop_said_over_the_reply_cuts_it_and_the_turn_is_a_command() -> None:
    stop = PRESET_WORDS["en"].stop[0]

    async def scene() -> tuple[TextTurn, TextTurn]:
        async with ScriptedCall(_reset) as call:
            first = await call.user("How do I reset my password?")
            second = await call.user(stop, during="agent_speaking")
            return first, second

    first, second = asyncio.run(scene())
    assert second.fate == "command"
    assert [c.fate for c in first.clauses] == ["cut", "unplayed"]
    first.expect.said(contains="Open Settings")
    with pytest.raises(AssertionError):
        first.expect.said(contains="Anything else")  # cut away, never heard


def test_words_said_while_a_search_runs_cancel_it_and_the_talker_hears_both() -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:
            return [
                ToolBegan(call_id="t-1", tool="search_help"),
                Work(3.0),
                ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=3000.0),
                ReplyDone(),
            ]
        return answer("Archiving is under Tickets.")

    async def scene() -> tuple[ScriptedCall, TextTurn, TextTurn]:
        async with ScriptedCall(script) as call:
            first = await call.user("How do I reset my password?")
            second = await call.user("actually, archiving", at="tool_running")
            await call.advance(5.0)
            return call, first, second

    call, first, second = asyncio.run(scene())
    first.expect.cancelled("search_help")
    second.expect.said(contains="Archiving")
    assert call.talker is not None and call.talker.turns[1].cut_reply == 1
    assert [t.fate for t in call.talker.turns[1].conversation.turns] == ["rolled_back"]


def test_the_clients_stop_stops_the_reply_and_its_work() -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [SpokenClause(text="Let me check that.", language="en"), Work(5.0), ReplyDone()]

    async def scene() -> TextTurn:
        async with ScriptedCall(script) as call:
            turn = await call.user("Where is my ticket?")
            await call.advance(0.5)
            await call.stop()
            return turn

    turn = asyncio.run(scene())
    assert [c.fate for c in turn.clauses] == ["cut"]  # cut while it played
    assert turn.fate == "rolled_back"  # no clause of it played whole


def test_the_guards_checks_run_on_every_clause_the_talker_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule B (the guard's `check_ids`) stood in for: the stand-in passes a token found in the
    evidence (the caller's words, the tools' evidence, the cards) and fails any other."""

    def check(clause: str, *, evidence: Any, settings: Any, year: int) -> IdVerdict:
        tokens = [w.strip(".") for w in clause.split() if w.strip(".").isdigit()]
        seen = " ".join(evidence)
        missing = tuple(t for t in tokens if t not in seen)
        return IdVerdict(passed=not missing, unsupported=missing)

    monkeypatch.setattr(text_checks, "check_ids", check)

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ClauseBlocked(text="It is 77123.", language="en", unsupported=("77123",)),
            *answer(f"Your ticket {turn.words.split()[-1]} is open.", "Call 55501 later."),
        ]

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script) as call:
            turn = await call.user("Where is ticket 88231")
            turn.expect.blocked()
            assert turn.blocked[0].unsupported == ("77123",)
            await call.advance(10.0)
            return call.violations

    (found,) = asyncio.run(scene())
    assert "55501" in found and "88231" not in found


def test_an_agent_with_no_instructions_runs_the_echo() -> None:
    agent = VoiceAgent(name="echo-text", languages=[Language.english(greeting="Hi.")])

    async def scene() -> TextTurn:
        async with TextCall(agent, llm=NoModel()) as call:
            turn = await call.user("check the line please")
            await call.advance(10.0)
            return turn

    turn = asyncio.run(scene())
    turn.expect.said(contains="check the line please")
    assert turn.tool_calls == () and turn.model_requests == 0 and turn.first_token_s is None


def test_a_text_call_refuses_another_env_and_use_outside_its_block(settings: VoiceSettings) -> None:
    staging = settings.model_copy(update={"env": "staging"})
    with pytest.raises(ConfigurationError, match="env=test"):
        asyncio.run(TextCall(AGENT, llm=NoModel(), settings=staging).__aenter__())
    with pytest.raises(RuntimeError, match="async with"):
        asyncio.run(TextCall(AGENT, llm=NoModel()).user("hello"))


def test_talker_set_for_an_agent_with_no_instructions_names_the_setting_under_its_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As the runtime's error does (agent/talker.py's `chat_talkers`): the variable to change,
    under the prefix the settings were loaded with."""
    monkeypatch.setenv("HELPDESK_VOICE_ENV", "test")
    monkeypatch.setenv("HELPDESK_VOICE_SESSION__MODE", "talker")
    settings = VoiceSettings.from_env(prefix="HELPDESK_VOICE_")
    echo = VoiceAgent(name="echo", languages=[Language.english(greeting="Hello.")])
    with pytest.raises(ConfigurationError, match="HELPDESK_VOICE_SESSION__MODE is talker"):
        asyncio.run(TextCall(echo, llm=NoModel(), settings=settings).__aenter__())


def test_on_the_system_clock_a_turn_returns_once_its_reply_is_written() -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [Work(0.05), *answer("Done.")]

    async def scene() -> TextTurn:
        async with ScriptedCall(script, clock="system", chars_per_second=2000.0) as call:
            turn = await call.user("Is it done?")
            # The 0.05 s of work is slept on the loop's clock, which on Windows ticks every
            # 15.6 ms, while the turn's times read the finer counter: the sleep can end up to
            # one tick early by it (0.033 s was seen), so the bound allows that tick.
            assert turn.first_clause_s is not None and turn.first_clause_s >= 0.03
            await call.advance(0.05)
            return turn

    turn = asyncio.run(scene())
    assert turn.fate == "answered"


def test_a_fake_model_pauses_on_each_calls_own_clock_even_when_reused() -> None:
    """A `ScriptedLLM`'s pause waits on the call's virtual clock, set for every call: its reply
    comes once the clock has moved past the pause, and the same fake in a second call waits on
    that call's clock, never on the first call's, which no longer moves."""
    llm = ScriptedLLM(
        [
            [Pause(2.0), *ScriptedLLM.reply("First answer.")],
            [Pause(2.0), *ScriptedLLM.reply("Second answer.")],
        ]
    )

    async def scene(words: str, answer: str) -> None:
        async with TextCall(AGENT, llm=llm, language="en") as call:
            turn = await call.user(words)
            assert turn.clauses == ()  # the model still pauses, on the call's clock
            await call.advance(2.5)
            turn.expect.said(contains=answer)

    asyncio.run(scene("Hello?", "First answer"))
    asyncio.run(scene("Hello again?", "Second answer"))
    assert len(llm.requests) == 2


def test_a_fake_model_whose_script_ran_out_fails_the_test_never_heard_as_the_error_notice() -> None:
    """The library's talker on a `ScriptedLLM` of one answer: the call's second turn asks for a
    second, which the script does not hold, and that turn raises `ScriptExhaustedError` (an
    AssertionError), where the call alone would have said its `error` notice and passed."""
    llm = ScriptedLLM([list(ScriptedLLM.reply("First answer."))])

    async def scene() -> None:
        async with TextCall(AGENT, llm=llm, language="en") as call:
            (await call.user("Hello?")).expect.said(contains="First answer")
            with pytest.raises(ScriptExhaustedError):
                await call.user("And then?")

    asyncio.run(scene())
    assert len(llm.requests) == 2


@pytest.mark.parametrize(
    "script",
    [
        [[Done(finish_reason="length")]],
        [
            list(ScriptedLLM.call_tool("search_knowledge", query="password")),
            list(ScriptedLLM.reply("")),
        ],
    ],
    ids=["cut-at-its-limit", "empty-after-a-search"],
)
def test_a_reply_the_model_ends_with_no_word_is_heard_as_the_error_notice(
    script: list[list[Any]],
) -> None:
    """The library's talker on a `ScriptedLLM` whose answer ends with no word written: cut at
    the model's limit (`length`) before any, or empty after a search. The caller hears the
    `error` notice, once, never silence after asking."""
    passage = Passage(id="p-1", title="Reset a password", text="Open Settings.", score=0.9)
    search = knowledge_tool(FakeKnowledgeBase([passage]), description="Search the help.")
    agent = VoiceAgent(
        name="text-test", languages=AGENT.languages, instructions="Answer.", tools=[search]
    )
    llm = ScriptedLLM(script)

    async def scene() -> TextTurn:
        async with TextCall(agent, llm=llm, language="en") as call:
            turn = await call.user("How do I reset my password?")
            await call.advance(10.0)
            return turn

    turn = asyncio.run(scene())
    error = AGENT.languages[0].notices["error"]
    assert [(c.text, c.phrase) for c in turn.clauses] == [(error, True)]
    assert turn.first_clause_s is None and len(llm.requests) == len(script)


def _model_then_search(turn: TalkerTurn) -> list[Step]:
    """The model's first request takes 0.4 s, its search 0.9 s, then it answers after 0.3 s."""
    return [
        Work(0.4),
        ToolBegan(call_id="t-1", tool="search_help"),
        Work(0.9),
        ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=900.0),
        Work(0.3),
        *answer("Open Settings."),
    ]


def test_a_tool_call_says_when_it_began_so_its_time_can_be_taken_out_of_the_replys() -> None:
    async def scene() -> TextTurn:
        async with ScriptedCall(_model_then_search) as call:
            turn = await call.user("How do I reset my password?")
            await call.advance(10.0)
            return turn

    turn = asyncio.run(scene())
    (search,) = turn.tool_calls
    assert search.began_s == pytest.approx(0.4) and search.ms == 900.0
    assert turn.first_clause_s == pytest.approx(1.6)  # the search's time in it
