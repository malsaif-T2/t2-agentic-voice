"""What a turn says that is no words (voice/session/turn_book.py, echo.py): a transcript the
filter for text from silence takes for no words (domain/silence.py's `from_silence`, Track A's,
here a fake) is said back as nothing, the filter asked only when `stt.no_speech_max` or
`stt.caption_filter` turns it on; and a clause with no letter or digit (a symbol Whisper writes
on noise) is never sent to text-to-speech (TD-060)."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import UserTurnEnded
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.voice.session import turn_book
from t2_agentic_voice.voice.session.echo import said
from t2_agentic_voice.voice.session.session_events import Transcribed

from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    captions,
    emitted,
    greeted,
    report,
    speaks,
    turn,
)

CAPTION = "made-up caption of the noise"  # what the fake filter takes for text from silence


class FakeFilter:
    """Track A's `from_silence` as the test has it: text from silence when the text is
    `CAPTION`; every call kept."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, float | None, float | None, tuple[str, ...]]] = []

    def __call__(
        self,
        text: str,
        no_speech_prob: float | None,
        *,
        no_speech_max: float | None,
        captions: Collection[str],
    ) -> bool:
        self.asked.append((text, no_speech_prob, no_speech_max, tuple(captions)))
        return text == CAPTION


@pytest.fixture
def silence(monkeypatch: pytest.MonkeyPatch) -> FakeFilter:
    fake = FakeFilter()
    monkeypatch.setattr(turn_book, "from_silence", fake)
    return fake


@pytest.mark.parametrize(
    "stt",
    [SttSettings(no_speech_max=0.5), SttSettings(caption_filter=True)],
    ids=["no-speech-max", "caption-filter"],
)
def test_a_transcript_of_text_from_silence_is_said_back_as_nothing(
    settings: VoiceSettings, silence: FakeFilter, stt: SttSettings
) -> None:
    io, session = call(settings.model_copy(update={"stt": stt}))

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0)
        at = io.clock.now()
        transcript = Transcript(text=CAPTION, language="en", no_speech_prob=0.7)
        await session.handle(
            Transcribed(turn_id=0, at=at, audio_s=1.0, sent_at=at, transcript=transcript)
        )
        await io.clock.advance(1.0)
        await turn(io, 1, HEARD)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert silence.asked == [
        (CAPTION, 0.7, stt.no_speech_max, ()),
        (HEARD, None, stt.no_speech_max, ()),
    ]
    assert [s.turn_id for s in speaks(io) if s.clause == 0] == [None, 1]
    assert [c.turn_id for c in captions(io, "caller")] == [1]
    assert [e.heard for e in emitted(io, UserTurnEnded)] == ["", HEARD]
    assert report(io).turns[0].heard == "" and session.history.turns()[0].fate == "answered"


def test_with_the_filter_off_it_is_never_asked(
    settings: VoiceSettings, silence: FakeFilter
) -> None:
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, CAPTION)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert silence.asked == [] and speaks(io, 1)


def test_a_clause_with_no_letter_or_digit_is_never_sent(settings: VoiceSettings) -> None:
    io, _ = call(settings)
    setup = io.setup
    language, agent, max_chars = setup.language, setup.agent, setup.max_chars("en")
    assert said("♪ ♪", agent=agent, language=language, max_chars=max_chars) == []
    assert said("♪. Made-up words 7.", agent=agent, language=language, max_chars=max_chars)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "♪")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) == [] and report(io).turns[0].heard == "♪"
