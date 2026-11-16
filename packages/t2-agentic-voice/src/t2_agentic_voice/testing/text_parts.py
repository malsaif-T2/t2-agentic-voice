"""The parts a text call (testing/text_call.py) is built from: its settings, `env` test alone,
with a folder of its own (`text_settings`); its clock, on a pinned day when given one
(`text_clock`); its session, as the runtime builds one, on the
call's clock and the text side (`text_session`); and a typed turn handed to the session as heard
words (`hand_typed`)."""

from __future__ import annotations

import dataclasses
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path

from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock, DatedClock, day_shift
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.testing.text_reads import TurnSaid
from t2_agentic_voice.testing.text_side import (
    VIRTUAL_START,
    TextDriver,
    TextPhrases,
    TextSide,
    VirtualClock,
)
from t2_agentic_voice.testing.text_watch import RecordingJobs, WatchedTalker
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TranscriptPart,
    TurnClosed,
    TurnOpened,
)

# The most characters a text call's text-to-speech request takes: Orpheus's (the design's 3.1).
MAX_CHARS = 200
# The call's ID.
CALL_ID = "text-call"


def text_settings(
    settings: VoiceSettings | None,
) -> tuple[VoiceSettings, tempfile.TemporaryDirectory[str]]:
    """The call's settings (`env` test, the library's defaults, unless given), its storage a
    new folder of its own, and that folder; a ConfigurationError for any other `env`."""
    settings = settings or VoiceSettings(env="test")
    if settings.env != "test":
        raise ConfigurationError(
            f"A text call runs under env=test, not env={settings.env}: only there may typed "
            "text stand in for heard words. FIX: give it settings with env='test'."
        )
    folder = tempfile.TemporaryDirectory(prefix="t2v-text-call-")
    storage = StorageSettings(var_dir=Path(folder.name))
    return settings.model_copy(update={"storage": storage}), folder


class DatedVirtualClock(VirtualClock):
    """A virtual clock whose `wall` is moved by `shift`, whole days: on a pinned day, at the
    virtual clock's time of day."""

    def __init__(self, shift: timedelta) -> None:
        super().__init__()
        self._shift = shift

    def wall(self) -> datetime:
        return super().wall() + self._shift


def text_clock(virtual: bool, today: date | None, zone: tzinfo) -> Clock:
    """The call's clock: a virtual one, moved only by its `advance`, when `virtual`, else the
    system's; on `today` in `zone` when given (core/clock.py's `day_shift`), its time of day
    kept."""
    if virtual and today is not None:
        return DatedVirtualClock(day_shift(VIRTUAL_START, today, zone))
    if virtual:
        return VirtualClock()
    return SYSTEM_CLOCK if today is None else DatedClock(SYSTEM_CLOCK, today, zone)


def text_session(
    agent: VoiceAgent,
    *,
    settings: VoiceSettings,
    caller: Caller,
    language: Language,
    clock: Clock,
    side: TextSide,
    talker: WatchedTalker | None,
    llm: ChatModel,
    jobs: RecordingJobs | None,
    emit: Callable[[Event], None],
) -> CallSession:
    """The call's session, as the runtime builds one: `agent`'s, for `caller`, in `language`,
    on `clock` and `side`, its talker `talker` (none for the echo), its overlaps asked of `llm`
    and its actions' jobs `jobs`, its public events given to `emit`."""
    setup = CallSetup(
        call_id=CALL_ID,
        caller=caller,
        consent=Consent(version=None, record_audio=False),
        agent=agent,
        language=language,
        settings=settings,
        phrases=TextPhrases(agent),
        max_chars=lambda tag: MAX_CHARS,
        tracing=Tracing(),
        emit=emit,
        clock=clock,
        talker=talker,
        overlap_model=llm,
        action_jobs=jobs,
    )
    return CallSession(setup, side)


async def hand_typed(
    side: TextSide,
    session: CallSession,
    driver: TextDriver,
    clock: Clock,
    *,
    turn_id: int,
    text: str,
    chars_per_second: float,
) -> TurnSaid:
    """Hand the turn `turn_id`, `text` typed, to the session as heard words (text_call.py's
    injections): its speech for `len(text) / chars_per_second` seconds and the speech
    detector's stop delay, then its transcript at once, an overlap's whole overlap part first;
    the turn as said."""
    start = clock.now()
    first_reply = session.playback.next_id
    side.hand(TurnOpened(turn_id=turn_id, at=start, speech_at=start))
    await driver.quiet()
    speech_s = max(len(text), 1) / chars_per_second
    await driver.advance(speech_s + session.setup.settings.turns.vad_stop_ms / 1000)
    end = clock.now()
    heard = Transcript(text=text, language=session.setup.language.primary)
    own = Transcribed(
        turn_id=turn_id, at=end, audio_s=speech_s, sent_at=end, transcript=heard, source="typed"
    )
    closed = TurnClosed(turn_id=turn_id, at=end, speech_ended_at=end)
    if turn_id in side.overlaps:
        part: TranscriptPart = "overlap"
        side.hand(Transcribing(turn_id=turn_id, at=end, audio_s=speech_s, part=part))
        side.hand_all([dataclasses.replace(own, part=part), closed, own])
    else:
        side.hand_all([closed, Transcribing(turn_id=turn_id, at=end, audio_s=speech_s), own])
    return TurnSaid(
        turn_id=turn_id, text=text, handed_at=end, spoke_at=start, first_reply=first_reply
    )
