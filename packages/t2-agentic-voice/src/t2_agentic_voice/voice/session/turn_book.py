"""The caller's turns as one call's session keeps them (voice/session/call.py), by number, each a
`TurnLog` (report.py): when its speech began and ended, whether it began over the agent's speech
(io.py's drop rule), its request and its words heard, each counted (`usage`), traced (`trace`),
recorded (`recorder`) and told to the observers (`events`: a failed request's `ProviderFailed`,
and the heard words of a turn not dropped); and each settled once it has closed, been heard and
had its reply played, its trace ended then and its times sent (none for a dropped turn's).
"""

from __future__ import annotations

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.tracing_tts import CallTrace
from t2_agentic_voice.voice.session.heard import HeardWords, heard_words
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import CallEvents, TurnLog
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)
from t2_agentic_voice.voice.session.usage import Usage


class TurnBook:
    """Every turn of one call, by its number; `listen` is the language the speech-to-text
    bridge names to the provider (none under `stt.live_language = "auto"`)."""

    def __init__(
        self,
        setup: CallSetup,
        *,
        listen: str | None,
        usage: Usage,
        trace: CallTrace,
        recorder: CallRecorder,
        events: CallEvents,
        playback: Playback,
    ) -> None:
        self._model, self._listen = setup.settings.stt.model, listen
        self._usage, self._trace, self._recorder, self._events = usage, trace, recorder, events
        self._playback = playback
        self._turns: dict[TurnId, TurnLog] = {}

    def turn(self, turn_id: TurnId) -> TurnLog:
        return self._turns.setdefault(turn_id, TurnLog(turn_id=turn_id))

    def opened(self, event: TurnOpened) -> TurnLog:
        """The turn opened: when its speech began, and whether that was over the agent's
        speech (the drop rule)."""
        turn = self.turn(event.turn_id)
        turn.speech_at = event.speech_at
        turn.dropped = self._playback.heard_over(event.speech_at)
        self._trace.turn_opened(event.turn_id)
        return turn

    def closed(self, event: TurnClosed) -> None:
        turn = self.turn(event.turn_id)
        turn.closed, turn.speech_ended_at = True, event.speech_ended_at
        self.settle(turn)

    def transcribing(self, event: Transcribing) -> None:
        """The turn's request went: counted, and its span opened."""
        self._usage.transcribing(event)
        self.turn(event.turn_id).requested = True
        self._trace.stt_sent(
            event.turn_id, model=self._model, language=self._listen, audio_seconds=event.audio_s
        )

    def transcribed(self, event: Transcribed) -> tuple[TurnLog, HeardWords | None]:
        """The turn's transcript came: counted, traced and recorded, a failure told, and the
        heard words told for a turn not dropped; the turn, and its heard words (None when
        nothing was heard)."""
        turn, transcript = self.turn(event.turn_id), event.transcript
        turn.transcribed_at = event.at
        self._usage.transcribed(event)
        self._trace.stt_heard(
            event.turn_id,
            text="" if transcript is None else transcript.text,
            language=None if transcript is None else transcript.language,
            billed_seconds=None if transcript is None else transcript.billed_seconds,
        )
        heard = heard_words(event)
        turn.heard = "" if heard is None else heard.text
        self._recorder.heard(event.at, event.turn_id, turn.heard, dropped=turn.dropped)
        if event.failure is not None:
            self._events.failed(event.failure, event.retryable, event.turn_id)
        if not turn.dropped:
            self._events.heard(turn.turn_id, turn.heard)
        return turn, heard

    def first_audio(self, reply: Reply, at: float) -> None:
        """A clause of `reply` began playing at `at`: its turn's first audio, the first time."""
        if reply.turn_id is not None:
            turn = self.turn(reply.turn_id)
            turn.first_audio_at = turn.first_audio_at or at

    def reply_ended(self, reply: Reply) -> None:
        """`reply` ended, however: the turn it answers settles."""
        if reply.turn_id is not None:
            turn = self.turn(reply.turn_id)
            turn.stopped = turn.stopped or reply.stopped
            turn.tts_first_audio_s = reply.first_audio_s
            self.settle(turn)

    def settle(self, turn: TurnLog) -> None:
        """Once a turn has closed, been heard and had its reply played, its trace ends and its
        times go out (none for a dropped turn)."""
        reply = None if turn.reply_id is None else self._playback.reply(turn.reply_id)
        if turn.done or not (turn.closed and turn.transcribed):
            return
        if reply is not None and reply.ended_at is None:
            return
        turn.done = True
        self._trace.turn_ended(turn.turn_id, turn.outcome())
        if not turn.dropped:
            self._events.metrics(turn)

    @property
    def all_closed(self) -> bool:
        return all(turn.closed for turn in self._turns.values())

    @property
    def awaited(self) -> bool:
        """Whether a turn to be answered has closed with its transcript still to come."""
        return any(turn.awaited for turn in self._turns.values())

    def end(self) -> None:
        """The call ended: every turn not yet heard is unfinished."""
        for turn in self._turns.values():
            turn.unfinished = not turn.transcribed

    def close(self) -> list[TurnLog]:
        """The call's stream ended: each turn's trace not yet ended ends, with how it ended;
        every turn, for the report."""
        for turn in self._turns.values():
            if not turn.done:
                self._trace.turn_ended(turn.turn_id, turn.outcome())
        return list(self._turns.values())
