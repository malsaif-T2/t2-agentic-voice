"""How long the session tells the yes rule's echo rail that a line is still heard (read_back.py's
`Confirming.over_read_back` and `over_follow_up`, yes_ask.py; D-082): from its reply's first
audio until the reply's tail after it ended (playback.py's `DROP_AFTER_S`, the drop rule's own,
0.3 s), the agent's voice leaked past the browser's echo cancellation. So words that copy the
closing question or the ask-again line, begun 0.1 s or 0.25 s after that line ended, are its echo
and asked again whatever the model says; the same words begun 0.4 s after it ended are the
caller's, and the model's `send` confirms them, the question having ended.

On the real yes rule, its words and a fake chat model that says `send` to every check, for an
agent that asks, in English and in Saudi Arabic. The closing questions are made up, "Shall I
send it?" and «تبيني أرسلها؟» (tabeeni arsilha: do you want me to send it?), each holding a send
word alone; the ask-again lines are the library's (domain/presets.py): "... Shall I go ahead?"
and «... أسجل الطلب؟» (asajjil aT-Talab: shall I register the request?). Adversarial (GP-08):
the agent's own line heard back just after it ended, judged a go-ahead."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import ReplyDone
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.presets import ACTION_LINES
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    Step,
    answer,
    settle,
    talked,
)
from tests.t2_agentic_voice.voice.session.yes_support import FakeJobs, confirm_call, play_reply

ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
# How long after the line ended the caller's speech began: within its reply's tail, and past it.
GAPS = [0.1, 0.25, 0.4]


@dataclass(frozen=True)
class Lines:
    """One language's call: the read-back, the caller's request and a filler alone (asked
    again by the lists, with no model), and the words that copy its closing question and its
    ask-again line."""

    plan: ReadBackPlan
    request: str
    filler: str
    copies_question: str
    copies_asked: str

    @property
    def heard_in(self) -> str:
        return primary_code(self.plan.language)


def _plan(tag: LanguageTag, summary: str, question: str) -> ReadBackPlan:
    def line(text: str) -> SpokenLine:
        return SpokenLine(text=text, spoken=text)

    library = ACTION_LINES[tag]
    return ReadBackPlan(
        action="open_made_up_request",
        tool_call_id="call-1",
        draft_json='{"issue": "made-up issue"}',
        summary=line(summary),
        question=line(question),
        asked_again=line(library["asked_again"]),
        declined=line(library["declined"]),
        sending=line(library["sending"]),
        language=tag,
        max_attempts=2,
    )


LINES = {
    "en": Lines(
        _plan("en", "Made-up summary of the draft for the printer.", "Shall I send it?"),
        request="made-up request for the agent to act",
        filler="please",
        copies_question="send it",
        copies_asked="go ahead",
    ),
    "ar-SA": Lines(
        # baftaH lak Talab liT-Taabi'a: I'll open you a request for the printer
        _plan("ar-SA", "بفتح لك طلب للطابعة.", "تبيني أرسلها؟"),
        request="ابغى افتح طلب للطابعة",  # abgha aftaH Talab liT-Taabi'a: I want a request opened
        filler="لو سمحت",  # law samaht: please
        copies_question="أرسلها",  # arsilha: send it
        copies_asked="أسجل الطلب",  # asajjil aT-Talab: shall I register the request
    ),
}


def _call(
    settings: VoiceSettings, lines: Lines
) -> tuple[FakeSessionIO, CallSession, ScriptedLLM, FakeJobs]:
    """A call in `lines`' language whose turn 0 reads its plan back, of an agent that asks,
    whose chat model says `send` to every check."""

    def reads_back(turn: TalkerTurn) -> Sequence[Step]:
        if turn.turn_id == 0:
            return [ReadBackRequested(plan=lines.plan), ReplyDone()]
        return answer("Made-up answer.")

    llm, jobs = ScriptedLLM([ScriptedLLM.reply("send") for _ in range(3)]), FakeJobs()
    io, session, _ = confirm_call(
        settings, jobs, reads_back, agent=ASKS, overlap_model=llm, language=lines.plan.language
    )
    llm.clock = io.clock
    return io, session, llm, jobs


async def _said(
    io: FakeSessionIO, session: CallSession, turn_id: int, text: str, *, language: str
) -> None:
    """The caller says `text` now, heard in `language`: over the reply it began within, its
    tail included, the transport handing its whole overlap first (as read_back_support.py's
    `over` does); or as a turn said while the agent is silent."""
    if session._playback.over(io.clock.now()) is None:
        await talked(io, turn_id, text, language=language)
        return
    await io.turn_opened(turn_id)
    await io.transcribing(turn_id, audio_s=0.9, part="overlap")
    await io.clock.advance(0.2)
    await io.transcribed(turn_id, text, language=language, part="overlap")
    await io.turn_closed(turn_id)
    await io.transcribed(turn_id, text, language=language)
    await settle()


def _answered(io: FakeSessionIO) -> list[tuple[int | None, str, str]]:
    return [(e.turn_id, e.decision, e.by) for e in emitted(io, ConfirmationAnswered)]


def _decided(gap: float) -> str:
    """The model's `send` on words that copy the line, begun `gap` after it ended."""
    return "asked_again" if gap <= DROP_AFTER_S else "yes"


@pytest.mark.parametrize("gap", GAPS)
@pytest.mark.parametrize("tag", list(LINES))
def test_the_closing_question_heard_back_within_its_replys_tail_is_its_echo(
    settings: VoiceSettings, tag: str, gap: float
) -> None:
    lines = LINES[tag]
    io, session, llm, jobs = _call(settings, lines)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, lines.request, language=lines.heard_in)
        await play_reply(io, 1)  # the summary, then the closing question, played whole
        await io.clock.advance(gap)
        await _said(io, session, 1, lines.copies_question, language=lines.heard_in)
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [(1, _decided(gap), "model")]
    assert len(llm.requests) == 1
    assert [run.confirmed.words for run in jobs.runs] == (
        [] if gap <= DROP_AFTER_S else [lines.copies_question]
    )


@pytest.mark.parametrize("gap", GAPS)
@pytest.mark.parametrize("tag", list(LINES))
def test_the_ask_again_line_heard_back_within_its_replys_tail_is_its_echo(
    settings: VoiceSettings, tag: str, gap: float
) -> None:
    lines = LINES[tag]
    io, session, llm, jobs = _call(settings, lines)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, lines.request, language=lines.heard_in)
        await play_reply(io, 1)
        await io.clock.advance(1.0)  # past the read-back's tail
        await talked(io, 1, lines.filler, language=lines.heard_in)  # asked again: reply 2
        await play_reply(io, 2)
        await io.clock.advance(gap)
        await _said(io, session, 2, lines.copies_asked, language=lines.heard_in)
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [(1, "asked_again", "words"), (2, _decided(gap), "model")]
    assert len(llm.requests) == 1
    assert [run.confirmed.words for run in jobs.runs] == (
        [] if gap <= DROP_AFTER_S else [lines.copies_asked]
    )
