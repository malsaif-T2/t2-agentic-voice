"""What the tests of a yes over a reply's closing question share (test_yes_over_question.py,
test_yes_over_question_never.py and test_yes_over_question_dropped.py): the made-up reply, its
summary and closing question in English and Saudi Arabic, a call under the setting, its moments,
and how long a held yes waits once the reply ended."""

from __future__ import annotations

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.held_yes import LAG_S
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part, two_step
from tests.t2_agentic_voice.voice.session.session_support import greeted
from tests.t2_agentic_voice.voice.session.talker_support import (
    FakeTalker,
    Script,
    Step,
    answer,
    settle,
    talked,
    talker_call,
)

SUMMARY = "Made-up trip for one traveler, 4521 riyals in all."
QUESTION = "Shall I book it?"
SAUDI_SUMMARY = "رحلة مختلقة لمسافر واحد، 4521 ريال."
SAUDI_QUESTION = "أحجزها لك؟"
SAUDI_YES = "ايه"  # eeh, yes (Saudi): alef, yeh, heh
SAUDI_NO = "لا"  # la, no: lam, alef
REQUEST = "Made-up request for a trip."
# How long after the reply ended a held yes waits before it is answered: the reply's tail, the
# speech detector's start and the pipeline's lag (yes_over_question.py's Answered).
ANSWER_WAIT_S = DROP_AFTER_S + TurnSettings().vad_start_ms / 1000 + LAG_S


def two_clauses(summary: str, question: str, language: LanguageTag) -> Script:
    """Turn 0's reply (reply 1) says `summary`, then `question`; a later turn's one clause."""

    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:
            return answer(summary, question, language=language)
        return answer("Made-up answer.")

    return script


def call(
    settings: VoiceSettings,
    *,
    on: bool = True,
    question: str = QUESTION,
    summary: str = SUMMARY,
    language: LanguageTag = "en",
) -> tuple[FakeSessionIO, CallSession, FakeTalker]:
    """A talker's call under `two_step`, the setting `on` or off, whose turn 0's reply says
    `summary`, then `question` (`two_clauses`)."""
    group = two_step(settings, answer_yes_over_question=on)
    return talker_call(group, two_clauses(summary, question, language))


async def summary_played(io: FakeSessionIO) -> None:
    """The call is greeted, turn 0 is answered (reply 1), its summary plays whole, and its
    closing question's first audio is queued 0.2 s ago."""
    await greeted(io)
    await talked(io, 0, REQUEST)
    await io.synthesizing(1, 0)
    await io.clause_queued(1, 0)
    await io.clock.advance(1.0)
    await io.clause_played(1, 0, audio_s=1.0)
    await io.synthesizing(1, 1)
    await io.clause_queued(1, 1)
    await io.clock.advance(0.2)


async def said(
    io: FakeSessionIO,
    turn_id: int,
    text: str,
    *,
    language: str = "en",
    speech_at: float | None = None,
) -> None:
    """The caller says `text` now (its speech begun at `speech_at`, by default now), over the
    reply or its tail: its whole overlap heard, then the turn closes and its own transcript
    reuses it."""
    await io.turn_opened(turn_id, speech_at=speech_at)
    await overlap_part(io, turn_id, text)
    await io.turn_closed(turn_id)
    await io.transcribed(turn_id, text, language=language)
    await settle()


async def question_ends(io: FakeSessionIO) -> None:
    """Reply 1's closing question plays whole now; the reply ends."""
    await io.clause_played(1, 1, audio_s=1.0)
    await settle()


async def waited(io: FakeSessionIO) -> None:
    """The wait of a yes held over the question passes (`ANSWER_WAIT_S`), a step woken then."""
    await io.clock.advance(ANSWER_WAIT_S)
    await settle()


def handed(talker: FakeTalker) -> list[tuple[int, str]]:
    return [(turn.turn_id, turn.words) for turn in talker.turns]


def fate(session: CallSession, turn_id: int) -> str:
    return next(t.fate for t in session.history.turns() if t.turn_id == turn_id)
