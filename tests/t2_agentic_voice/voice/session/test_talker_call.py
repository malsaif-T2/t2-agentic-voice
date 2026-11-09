"""The talker in the call (voice/session/talking.py; plan 006, Track C): a turn answered by the
talker instead of the echo, from the heard history, its reply opened before its first clause and
spoken clause by clause as the talker writes it, in the reply's scope; each of the talker's
events played (a card, a tool's start and end, a progress line, a blocked clause, the model's
usage); the reply language per clause; and a talker's failure told, in the turn's reply
language, after any clause already said too. The fake talker is the tests' own
(talker_support.py)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ProgressDue,
    ReplyDone,
    ShownCard,
    SpokenClause,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    GuardBlocked,
    ProviderFailed,
    ToolFinished,
    ToolStarted,
)
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.voice.protocol import ShowCard, State
from t2_agentic_voice.voice.session.echo import BEAT_S

from tests.t2_agentic_voice.voice.session.session_support import (
    captions,
    emitted,
    greeted,
    play,
    report,
    sent,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    MODEL,
    PROGRESS,
    Fail,
    Step,
    Work,
    answer,
    ended,
    settle,
    talked,
    talker_call,
)

CARD = Card(title="Reset a password", steps=("Open Settings.", "Press Reset."), source="Guide")


def test_a_turn_is_answered_by_the_talker_clause_by_clause_from_the_heard_history(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ModelRequested(model=MODEL),
            ModelReplied(
                model=MODEL,
                usage=Usage(input_tokens=900, output_tokens=40, cached_tokens=500),
                first_token_s=0.3,
            ),
            SpokenClause(text="Open Settings first.", language="en"),
            ShownCard(card=CARD),
            SpokenClause(text="Then press Reset.", language="en"),
            ReplyDone(),
        ]

    io, session, talker = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I reset my password?", language="en")
        assert sent(io, State)[-1].state == "thinking"  # nothing of the reply plays yet
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (handed,) = talker.turns
    assert (handed.turn_id, handed.words, handed.language) == (
        0,
        "How do I reset my password?",
        "en",
    )
    assert (handed.over_reply, handed.cut_reply) == (None, None)
    (greeting,) = handed.conversation.replies  # what the caller heard before the turn
    assert [c.fate for c in greeting.clauses] == ["played"] and handed.conversation.turns == ()
    assert [(s.reply_id, s.clause, s.turn_id, s.text) for s in speaks(io, 1)] == [
        (1, 0, 0, "Open Settings first."),
        (1, 1, 0, "Then press Reset."),
    ]
    assert [c.text for c in captions(io) if c.reply_id == 1] == [
        "Open Settings first.",
        "Then press Reset.",
    ]
    assert sent(io, ShowCard) == [ShowCard(title=CARD.title, steps=CARD.steps, source=CARD.source)]
    (said,) = [e for e in emitted(io, AgentSpeechEnded) if e.turn_id == 0]
    assert (said.text, said.played_fraction) == ("Open Settings first. Then press Reset.", 1.0)
    assert [t.fate for t in session.history.turns()] == ["answered"]
    record = report(io).turns[0]
    assert record.said == "Open Settings first. Then press Reset."
    chat = {u.model: u for u in report(io).usage}[MODEL]
    assert (chat.requests, chat.input_tokens, chat.output_tokens, chat.cached_tokens) == (
        1,
        900,
        40,
        500,
    )
    assert record.times.llm_first_token_ms is not None


def test_a_reply_stays_open_while_its_talker_works_and_ends_once_it_is_done(
    settings: VoiceSettings,
) -> None:
    """The reply's first clause plays while the talker's work runs in the reply's scope; with
    nothing left to play the agent is thinking, and the reply ends only after its last clause,
    written once the work is done."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            SpokenClause(text="Let me check.", language="en"),
            ToolBegan(call_id="t-1", tool="search_help"),
            Work(2.0),
            ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=2000.0),
            SpokenClause(text="Found it.", language="en"),
            ReplyDone(),
        ]

    io, session, talker = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)
        assert sent(io, State)[-1].state == "speaking"
        await io.clause_played(1, 0, audio_s=0.5)
        assert not ended(session, 1)  # still being written
        assert sent(io, State)[-1].state == "thinking"
        assert session._speaker.scope(1).running == 2  # the talker and its work, in the scope
        await io.clock.advance(2.0)
        await settle()
        assert [s.text for s in speaks(io, 1)] == ["Let me check.", "Found it."]
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)
        await io.clause_played(1, 1, audio_s=0.5)
        assert ended(session, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [type(e) for e in io.emitted if isinstance(e, ToolStarted | ToolFinished)] == [
        ToolStarted,
        ToolFinished,
    ]
    started, finished = [e for e in io.emitted if isinstance(e, ToolStarted | ToolFinished)]
    assert (started.turn_id, started.tool, started.tool_call_id) == (0, "search_help", "t-1")
    assert isinstance(finished, ToolFinished) and (finished.ok, finished.ms) == (True, 2000.0)
    assert talker.cancelled == []


def test_a_progress_line_and_a_blocked_clause_are_said_from_the_phrase_cache(
    settings: VoiceSettings,
) -> None:
    """A progress line due is said from the phrase cache in its language; a blocked clause is
    never said: the call language's `error` notice in its place, once a reply, and one
    `GuardBlocked` for each."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ProgressDue(tool="search_help", key="looking", language="en"),
            ClauseBlocked(text="Your number is 4521.", language="en", unsupported=("4521",)),
            ClauseBlocked(text="It is 4522.", language="en", unsupported=("4522",)),
            SpokenClause(text="Anything else?", language="en"),
            ReplyDone(),
        ]

    io, _, _ = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "What is my number?", language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    error = AGENT.languages[0].notices["error"]
    said = speaks(io, 1)
    assert [(s.text, s.audio is not None) for s in said] == [
        (PROGRESS["en"], True),
        (error, True),
        ("Anything else?", False),
    ]
    assert all("4521" not in s.text and "4522" not in s.text for s in speaks(io))
    assert [e.reason for e in emitted(io, GuardBlocked)] == ["unsupported_id"] * 2
    assert report(io).turns[0].times.progress_ms is not None


def test_each_clause_is_said_in_the_language_the_talker_wrote_it_in(
    settings: VoiceSettings,
) -> None:
    """Saudi, MSA and English turns in one call: each reply in its own turn's language, counted
    under that language's voice, its digits spoken by the speaking rules and captioned as
    written."""
    texts: dict[int, tuple[str, LanguageTag]] = {
        0: ("أهلين، كيف أخدمك؟", "ar-SA"),
        1: ("You have 3 tickets.", "en"),
    }

    def script(turn: TalkerTurn) -> list[Step]:
        text, language = texts[turn.turn_id]
        return answer(text, language=language)

    io, _, _ = talker_call(settings, script, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "السلام عليكم", language="ar")
        await play(io, 1)
        await talked(io, 1, "How many tickets do I have?", language="en")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    first, second = speaks(io, 1)[0], speaks(io, 2)[0]
    assert (first.language, second.language) == ("ar-SA", "en")
    assert "3" not in second.text and "three" in second.text  # spoken, after the guard read it
    assert captions(io)[-1].text == "You have 3 tickets."  # shown as the talker wrote it
    models = {u.model: u for u in report(io).usage}
    english = settings.tts.languages["en"].model
    assert models[english].requests == 1 and models[english].characters == len(second.text)


def test_a_talkers_failure_is_told_and_its_reply_closed(settings: VoiceSettings) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        raise ProviderError("rate_limited", True)

    io, session, _ = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Hello?", language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [s.text for s in speaks(io, 1)] == [AGENT.languages[0].notices["error"]]
    (failed,) = emitted(io, ProviderFailed)
    assert (failed.turn_id, failed.kind, failed.retryable) == (0, "rate_limited", True)
    assert ended(session, 1)


@pytest.mark.parametrize("said", [False, True], ids=["before-a-clause", "after-a-clause"])
def test_a_talkers_failure_is_told_in_the_turns_reply_language(
    settings: VoiceSettings, said: bool
) -> None:
    """A Saudi call, an English turn: the talker fails before any clause, or after one it said
    in English; one notice is said either way, `error` before any clause and `cut_off` after
    one, in English, the language of the clauses given, else of the turn as heard."""

    def script(turn: TalkerTurn) -> list[Step]:
        first: list[Step] = [SpokenClause(text="Let me check.", language="en")] if said else []
        return [*first, Fail(ProviderError("timeout", True))]

    io, session, _ = talker_call(settings, script, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    english = AGENT.languages[0]
    told = [("Let me check.", "en")] if said else []
    assert [(s.text, s.language) for s in speaks(io, 1)] == [
        *told,
        (english.notices["cut_off" if said else "error"], "en"),
    ]
    assert ended(session, 1)


_ASKED: list[Step] = [
    ModelRequested(model=MODEL),
    ModelReplied(model=MODEL, usage=None, first_token_s=None),
]
_BLOCKED = ClauseBlocked(text="It is 4521.", language="en", unsupported=("4521",))


@pytest.mark.parametrize(
    ("given", "phrases"),
    [
        ([], 0),
        ([ProgressDue(tool="search_help", key="looking", language="en")], 1),
        ([_BLOCKED], 0),
    ],
    ids=["nothing", "a-progress-line-only", "a-blocked-clause-only"],
)
def test_a_reply_that_ends_with_no_clause_is_told_the_error_notice_once(
    settings: VoiceSettings, given: list[Step], phrases: int
) -> None:
    """A talker whose reply ends (`ReplyDone`) with no clause said, as a model's empty answer or
    one cut at its limit ends: the caller hears the `error` notice in its place, once a reply
    (after a progress line, and never again after a blocked clause's), never silence."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [*_ASKED, *given, ReplyDone()]

    io, session, _ = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    said = [s.text for s in speaks(io, 1)]
    assert said == [*([PROGRESS["en"]] * phrases), AGENT.languages[0].notices["error"]]
    assert ended(session, 1)


def test_a_talker_that_refuses_the_turn_at_once_is_told_and_its_reply_closed(
    settings: VoiceSettings,
) -> None:
    """A team's talker whose `reply` raises as it is called, before any stream: the `error`
    notice is said and the reply closes, as for a failure inside the stream."""
    io, session, talker = talker_call(settings)

    def refuse(turn: TalkerTurn, *, scope: object) -> None:
        raise RuntimeError("a team's talker refused the turn")

    talker.reply = refuse  # type: ignore[assignment,method-assign]

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [s.text for s in speaks(io, 1)] == [AGENT.languages[0].notices["error"]]
    assert ended(session, 1)


def test_a_clause_that_fails_after_one_played_is_told_at_the_replys_end_after_a_beat(
    settings: VoiceSettings,
) -> None:
    """D-077: no clause of the reply follows the line, which says the answer was cut off and is
    longer than its phrase by the beat before it."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [*answer("First.", "Second.", "Third.")]

    io, _, _ = talker_call(settings, script, language="en")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await io.clause_queued(1, 0)
        await io.clause_played(1, 0)
        await io.clause_failed(1, 1)
        assert len(speaks(io)) == 4  # the greeting and the three clauses: nothing told yet
        await io.clause_queued(1, 2)
        await io.clause_played(1, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    english = AGENT.languages[0]
    [told] = speaks(io, 2)
    assert told.text == english.notices["cut_off"]
    phrase = io.setup.phrases.audio(told.text, language="en")
    assert told.audio is not None
    assert len(told.audio.pcm16) - len(phrase.pcm16) == 2 * round(BEAT_S * phrase.sample_rate)
